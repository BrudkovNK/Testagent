from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from .config import CONFIG


@dataclass
class Step:
    """Один шаг агента: что решил сделать и что получилось."""
    action_summary: str   # короткое текстовое описание действия ("клик по #7 'Купить'")
    result_summary: str   # короткое текстовое описание результата/наблюдения
    raw_message: dict | None = None  # полное сообщение (assistant tool_use / tool_result), для "свежих" шагов


class Memory:
    def __init__(self, task: str, plan: str, cfg=CONFIG):
        self.task = task
        self.plan = plan
        self.cfg = cfg
        self.steps: list[Step] = []
        self.progress_log: list[str] = []  # сжатая история старых шагов, по одной строке

    def add_step(self, step: Step):
        self.steps.append(step)
        self._compact_if_needed()

    def _compact_if_needed(self):
        overflow = len(self.steps) - self.cfg.max_history_steps
        if overflow <= 0:
            return
        for _ in range(overflow):
            old = self.steps.pop(0)
            line = f"- {old.action_summary} → {old.result_summary}"
            self.progress_log.append(line)
        # не даём и самому логу расти бесконечно на очень длинных эпизодах
        if len(self.progress_log) > 40:
            self.progress_log = self.progress_log[-40:]

    def progress_text(self) -> str:
        if not self.progress_log:
            return "(ещё не было выполненных шагов)"
        return "\n".join(self.progress_log)

    def recent_raw_messages(self) -> list[dict]:
        return [s.raw_message for s in self.steps if s.raw_message is not None]

    def system_context_block(self) -> str:
        return (
            f"ЗАДАЧА ПОЛЬЗОВАТЕЛЯ: {self.task}\n\n"
            f"ПЛАН ВЫСОКОГО УРОВНЯ (ориентир, можно отклоняться при необходимости):\n{self.plan}\n\n"
            f"ЖУРНАЛ ПРОГРЕССА (сжатая история более ранних шагов):\n{self.progress_text()}"
        )
