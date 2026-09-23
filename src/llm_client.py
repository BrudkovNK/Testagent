from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any

from .config import CONFIG
from .tools import TOOLS


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    raw: Any = None


class LLMClient:
    def call(self, system: str, messages: list[dict]) -> LLMResponse:
        raise NotImplementedError

    def build_user_message(self, text: str, screenshot_b64: str | None) -> dict:
        raise NotImplementedError

    @staticmethod
    def assistant_message(response: LLMResponse) -> dict:
        raise NotImplementedError

    @staticmethod
    def tool_result_message(tool_call_id: str, content: str, is_error: bool = False) -> dict:
        raise NotImplementedError

class AnthropicClient(LLMClient):
    def __init__(self, cfg=CONFIG):
        import anthropic
        self.client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        self.model = cfg.anthropic_model

    def call(self, system: str, messages: list[dict]) -> LLMResponse:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=messages,
            tools=TOOLS,
        )
        text_parts = []
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input or {}))
        return LLMResponse(text="\n".join(text_parts), tool_calls=tool_calls, raw=resp)

    def build_user_message(self, text: str, screenshot_b64: str | None) -> dict:
        if screenshot_b64:
            content = [
                {"type": "text", "text": text},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64}},
            ]
        else:
            content = text
        return {"role": "user", "content": content}

    @staticmethod
    def assistant_message(response: LLMResponse) -> dict:
        return {"role": "assistant", "content": response.raw.content}

    @staticmethod
    def tool_result_message(tool_call_id: str, content: str, is_error: bool = False) -> dict:
        block = {"type": "tool_result", "tool_use_id": tool_call_id, "content": content}
        if is_error:
            block["is_error"] = True
        return {"role": "user", "content": [block]}

class OpenAIClient(LLMClient):
    def __init__(self, cfg=CONFIG):
        import openai
        kwargs = {"api_key": cfg.openai_api_key or "not-needed-for-local-ollama"}
        if cfg.openai_base_url:
            kwargs["base_url"] = cfg.openai_base_url
        self.client = openai.OpenAI(**kwargs)
        self.model = cfg.openai_model

    @staticmethod
    def _to_openai_tools():
        return [
            {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in TOOLS
        ]

    def call(self, system: str, messages: list[dict]) -> LLMResponse:
        oa_messages = [{"role": "system", "content": system}] + messages
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=oa_messages,
            tools=self._to_openai_tools(),
        )
        choice = resp.choices[0].message
        tool_calls = []
        for tc in (choice.tool_calls or []):
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=json.loads(tc.function.arguments or "{}")))
        return LLMResponse(text=choice.content or "", tool_calls=tool_calls, raw=resp)

    def build_user_message(self, text: str, screenshot_b64: str | None) -> dict:
        if screenshot_b64:
            content = [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
            ]
        else:
            content = text
        return {"role": "user", "content": content}

    @staticmethod
    def assistant_message(response: LLMResponse) -> dict:
        msg = {"role": "assistant", "content": response.text or None}
        if response.tool_calls:
            msg["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.input, ensure_ascii=False)}}
                for tc in response.tool_calls
            ]
        return msg

    @staticmethod
    def tool_result_message(tool_call_id: str, content: str, is_error: bool = False) -> dict:
        prefix = "[ERROR] " if is_error else ""
        return {"role": "tool", "tool_call_id": tool_call_id, "content": prefix + content}

class GeminiClient(LLMClient):
    def __init__(self, cfg=CONFIG):
        import google.generativeai as genai
        genai.configure(api_key=cfg.gemini_api_key)
        self._genai = genai
        self.model_name = cfg.gemini_model
        self._tools = [{"function_declarations": [
            {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}
            for t in TOOLS
        ]}]

    def call(self, system: str, messages: list[dict]) -> LLMResponse:
        model = self._genai.GenerativeModel(
            self.model_name, system_instruction=system, tools=self._tools,
        )
        resp = model.generate_content(messages)
        text_parts, tool_calls = [], []
        candidate = resp.candidates[0]
        for i, part in enumerate(candidate.content.parts):
            if getattr(part, "text", None):
                text_parts.append(part.text)
            fc = getattr(part, "function_call", None)
            if fc and fc.name:
                tool_calls.append(ToolCall(id=f"{fc.name}#{i}", name=fc.name, input=dict(fc.args)))
        return LLMResponse(text="\n".join(text_parts), tool_calls=tool_calls, raw=resp)

    def build_user_message(self, text: str, screenshot_b64: str | None) -> dict:
        parts = [{"text": text}]
        if screenshot_b64:
            parts.append({"inline_data": {"mime_type": "image/png", "data": screenshot_b64}})
        return {"role": "user", "parts": parts}

    @staticmethod
    def assistant_message(response: LLMResponse) -> dict:
        parts = []
        if response.text:
            parts.append({"text": response.text})
        for tc in response.tool_calls:
            parts.append({"function_call": {"name": tc.name, "args": tc.input}})
        return {"role": "model", "parts": parts}

    @staticmethod
    def tool_result_message(tool_call_id: str, content: str, is_error: bool = False) -> dict:
        name = tool_call_id.rsplit("#", 1)[0]
        payload = {"error": content} if is_error else {"result": content}

        return {"role": "user", "parts": [{"function_response": {"name": name, "response": payload}}]}


def get_llm_client(cfg=CONFIG) -> LLMClient:
    if cfg.llm_provider == "openai":
        return OpenAIClient(cfg)
    if cfg.llm_provider == "gemini":
        return GeminiClient(cfg)
    return AnthropicClient(cfg)
