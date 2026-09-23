from __future__ import annotations
import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


@dataclass
class Config:
    # --- LLM ---
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    headless: bool = _bool("HEADLESS", False)
    user_data_dir: str = os.getenv("USER_DATA_DIR", "./browser_profile")
    viewport_width: int = _int("VIEWPORT_WIDTH", 1440)
    viewport_height: int = _int("VIEWPORT_HEIGHT", 900)
    default_start_url: str = os.getenv("DEFAULT_START_URL", "about:blank")
    slow_mo_ms: int = _int("SLOW_MO_MS", 50)
    max_steps: int = _int("MAX_STEPS", 40)
    action_timeout_ms: int = _int("ACTION_TIMEOUT_MS", 15000)
    nav_wait_ms: int = _int("NAV_WAIT_MS", 800)

    # --- Context management ---
    max_elements_per_state: int = _int("MAX_ELEMENTS_PER_STATE", 120)
    max_history_steps: int = _int("MAX_HISTORY_STEPS", 8)
    max_text_field_chars: int = _int("MAX_TEXT_FIELD_CHARS", 200)
    use_screenshots: bool = _bool("USE_SCREENSHOTS", True)
    screenshot_max_width: int = _int("SCREENSHOT_MAX_WIDTH", 1280)

    require_confirmation: bool = _bool("REQUIRE_CONFIRMATION", True)

    def validate(self) -> list[str]:
        problems = []
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            problems.append("ANTHROPIC_API_KEY не задан (нужен для LLM_PROVIDER=anthropic)")
        if self.llm_provider == "openai" and not self.openai_api_key:
            problems.append(
                "OPENAI_API_KEY не задан (нужен для LLM_PROVIDER=openai; "
                "если это локальный Ollama — впишите туда любую непустую строку, например 'ollama')"
            )
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            problems.append(
                "GEMINI_API_KEY не задан (нужен для LLM_PROVIDER=gemini; "
                "бесплатный ключ: https://aistudio.google.com/apikey)"
            )
        if self.llm_provider not in ("anthropic", "openai", "gemini"):
            problems.append(f"Неизвестный LLM_PROVIDER='{self.llm_provider}' (допустимо: anthropic | openai | gemini)")
        return problems


CONFIG = Config()
