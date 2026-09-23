"""
agent.py

Главный цикл автономного браузерного агента (Executor), опирающийся на:
  - browser_controller.py — глаза и руки (состояние страницы + действия по индексу)
  - llm_client.py          — мозг (Claude/OpenAI, tool calling)
  - tools.py                - словарь доступных действий
  - memory.py               - управление контекстом/токенами
  - security.py             - перехват деструктивных действий
  - subagents.py             - Planner (декомпозиция) + StagnationDetector (адаптация к ошибкам)

Никакой логики, специфичной под конкретный сайт или сценарий (почта/еда/вакансии),
здесь нет и быть не должно — агент одинаково стартует для любой текстовой задачи.
"""
from __future__ import annotations

from dataclasses import dataclass

from .browser_controller import BrowserController, ActionError, PageState
from .config import CONFIG
from .llm_client import LLMClient, ToolCall
from .memory import Memory, Step
from .security import element_looks_destructive, looks_destructive, ask_confirmation, ConfirmationDenied
from .subagents import Planner, StagnationDetector
from . import tools as T


SYSTEM_PROMPT_TEMPLATE = """Ты — автономный AI-агент, управляющий реальным веб-браузером через набор инструментов, \
чтобы выполнить задачу пользователя от начала до конца без лишних вопросов.

ПРАВИЛА:
1. Ты видишь страницу только через список пронумерованных интерактивных элементов (и, если доступен, аннотированный \
скриншот с такими же номерами) — никаких селекторов ты не знаешь и не должен придумывать. Действуй ТОЛЬКО через индексы \
из последнего показанного тебе состояния.
2. Ты не знаешь заранее структуру сайта, названия кнопок, URL разделов и т.п. — определяй всё это сам по ходу дела, \
анализируя реальную страницу на каждом шаге.
3. Работай полностью автономно: сама планируй следующий шаг, сама проверяй результат предыдущего шага по новому состоянию \
страницы, сама исправляйся при ошибках (страница не изменилась, элемент не найден, всплыло модальное окно и т.п.).
4. Задавай вопрос пользователю (ask_user) ТОЛЬКО когда без ответа реально невозможно продолжить (неоднозначность в задаче, \
неожиданная капча/2FA, отсутствие нужных данных). Не спрашивай "можно ли продолжать" на рутинных шагах.
5. ОБЯЗАТЕЛЬНО вызови request_confirmation перед любым необратимым действием: финальная оплата/покупка, безвозвратное \
удаление, окончательная отправка отклика/заявки/сообщения — и дождись результата, прежде чем кликать по такому элементу.
6. Когда задача выполнена (или объективно невыполнима) — вызови finish с кратким, но информативным summary для пользователя \
(что сделано, какие цифры/факты нашёл, что не удалось и почему).
7. За один ход вызывай ОДИН инструмент (кроме случаев, когда несколько действий тривиально независимы) — так проще \
проверять результат каждого шага перед следующим.
8. Если несколько шагов подряд ничего не меняется на странице — не повторяй слепо то же самое действие, проанализируй \
ситуацию заново.

{context_block}
"""


@dataclass
class AgentResult:
    success: bool
    summary: str
    steps_taken: int


class CLIBridge:
    def ask_yes_no(self, prompt: str) -> bool:
        while True:
            ans = input(prompt).strip().lower()
            if ans in ("y", "yes", "д", "да"):
                return True
            if ans in ("n", "no", "н", "нет", ""):
                return False
            print("Введите y/n")

    def ask_question(self, question: str) -> str:
        print(f"\nАгенту нужна дополнительная информация:\n    {question}")
        return input("Ваш ответ: ")

    def log(self, msg: str):
        print(msg)


class BrowserAgent:
    def __init__(self, task: str, browser: BrowserController, llm: LLMClient,
                 cli: CLIBridge, cfg=CONFIG):
        self.task = task
        self.browser = browser
        self.llm = llm
        self.cli = cli
        self.cfg = cfg
        self.stagnation = StagnationDetector(patience=2)

    def run(self) -> AgentResult:
        plan = Planner(self.llm).make_plan(self.task)
        self.cli.log(f"План (ориентир):\n{plan}\n")
        memory = Memory(task=self.task, plan=plan, cfg=self.cfg)

        raw_messages: list[dict] = []

        for step_num in range(1, self.cfg.max_steps + 1):
            state = self._get_state_safely()
            if state is None:
                return AgentResult(False, "Не удалось получить состояние страницы (браузер закрыт?).", step_num)

            warning = self.stagnation.observe(state.url, state.elements_text())

            observation_text = self._render_observation_text(state, warning)
            raw_messages.append(self.llm.build_user_message(observation_text, state.screenshot_b64))

            system = SYSTEM_PROMPT_TEMPLATE.format(context_block=memory.system_context_block())
            windowed = self._windowed_messages(raw_messages)

            try:
                response = self.llm.call(system=system, messages=windowed)
            except Exception as e:
                self.cli.log(f"Ошибка вызова LLM: {e}")
                return AgentResult(False, f"Остановлено из-за ошибки вызова модели: {e}", step_num)

            raw_messages.append(self.llm.assistant_message(response))
            if response.text:
                self.cli.log(f"{response.text.strip()}")

            if not response.tool_calls:
                raw_messages.append(self.llm.build_user_message("Продолжай: выбери и вызови следующий инструмент.", None))
                memory.add_step(Step("(модель ответила текстом без действия)", "продолжаем"))
                continue

            for call in response.tool_calls:
                result = self._execute(call, state)
                raw_messages.append(self.llm.tool_result_message(call.id, result.content, is_error=not result.ok))
                memory.add_step(Step(T.describe_call(call.name, call.input), result.content[:200]))

                self.cli.log(f"⚙{T.describe_call(call.name, call.input)} → {result.content[:160]}")

                if result.finished:
                    return AgentResult(bool(result.finish_success), result.content, step_num)

        return AgentResult(False, f"Достигнут лимит шагов ({self.cfg.max_steps}) без завершения задачи.", self.cfg.max_steps)

    def _get_state_safely(self) -> PageState | None:
        try:
            return self.browser.get_state()
        except Exception as e:
            self.cli.log(f"Ошибка чтения состояния страницы: {e}")
            return None

    def _render_observation_text(self, state: PageState, warning: str | None) -> str:
        return (
            f"Текущая страница: {state.title}\nURL: {state.url}\n"
            + (f"Заголовки на странице: {', '.join(state.headings)}\n" if state.headings else "")
            + f"\nИнтерактивные элементы (показано {len(state.elements)} из {state.total_found} найденных):\n"
            + state.elements_text()
            + (f"\n\n{state.scroll_hint()}" if state.scroll_hint() else "")
            + (f"\n\n{warning}" if warning else "")
        )

    def _windowed_messages(self, raw_messages: list[dict]) -> list[dict]:
        max_msgs = self.cfg.max_history_steps * 3 + 2
        if len(raw_messages) <= max_msgs:
            return raw_messages
        return raw_messages[-max_msgs:]

    def _execute(self, call: ToolCall, state: PageState) -> T.ToolResult:
        name, inp = call.name, call.input
        try:
            if name == "get_page_state":
                fresh = self.browser.get_state()
                return T.ToolResult(True, fresh.elements_text())

            if name == "navigate":
                self.browser.navigate(inp["url"])
                return T.ToolResult(True, f"Открыт URL: {inp['url']}")

            if name == "click":
                idx = int(inp["index"])
                target = next((e for e in state.elements if e.index == idx), None)
                if target and element_looks_destructive(target.name, target.role, target.tag):
                    if not ask_confirmation(self.cli, f'Клик по элементу "{target.name}" ({target.tag})'):
                        return T.ToolResult(False, "Пользователь ОТКЛОНИЛ это действие. Не повторяй его.")
                self.browser.click(idx)
                return T.ToolResult(True, f"Клик по #{idx} выполнен.")

            if name == "type_text":
                self.browser.type_text(
                    int(inp["index"]), inp["text"],
                    clear=inp.get("clear", True), press_enter=inp.get("press_enter", False),
                )
                return T.ToolResult(True, f"Текст введён в #{inp['index']}.")

            if name == "select_option":
                self.browser.select_option(int(inp["index"]), inp["value"])
                return T.ToolResult(True, f"Опция '{inp['value']}' выбрана в #{inp['index']}.")

            if name == "scroll":
                self.browser.scroll(inp.get("direction", "down"), inp.get("amount", 1.0))
                return T.ToolResult(True, "Прокрутка выполнена.")

            if name == "go_back":
                self.browser.go_back()
                return T.ToolResult(True, "Возврат на предыдущую страницу выполнен.")

            if name == "read_element":
                text = self.browser.get_element_full_text(int(inp["index"]))
                return T.ToolResult(True, text[:3000])

            if name == "wait":
                self.browser.wait(float(inp.get("seconds", 1)))
                return T.ToolResult(True, "Пауза выполнена.")

            if name == "request_confirmation":
                desc = inp["action_description"]
                ok = ask_confirmation(self.cli, desc)
                if ok:
                    return T.ToolResult(True, "Пользователь ПОДТВЕРДИЛ действие. Можно продолжать.")
                return T.ToolResult(False, "Пользователь ОТКЛОНИЛ действие. Не выполняй его, выбери другой путь или заверши задачу с пояснением.")

            if name == "ask_user":
                answer = self.cli.ask_question(inp["question"])
                return T.ToolResult(True, f"Ответ пользователя: {answer}", needs_user_input=True)

            if name == "finish":
                return T.ToolResult(True, inp.get("summary", ""), finished=True, finish_success=bool(inp.get("success")))

            return T.ToolResult(False, f"Неизвестный инструмент: {name}")

        except ActionError as e:
            return T.ToolResult(False, f"Ошибка действия: {e}")
        except Exception as e:
            return T.ToolResult(False, f"Непредвиденная ошибка: {e}")
