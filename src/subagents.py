from __future__ import annotations
import hashlib

from .llm_client import LLMClient


PLANNER_SYSTEM = (
    "Ты — планировщик для автономного браузерного AI-агента. Тебе дают задачу "
    "пользователя в свободной форме. Составь короткий план из 3-6 абстрактных "
    "шагов верхнего уровня для её решения. НЕ придумывай конкретные селекторы, "
    "названия кнопок, URL или пошаговый UI конкретного сайта — ты не знаешь, "
    "как выглядит сайт заранее. План должен описывать ЛОГИКУ решения задачи "
    "в общем виде (например: 'открыть нужный сервис', 'найти релевантный раздел/выполнить поиск', "
    "'проанализировать найденные элементы по критериям из задачи', 'выполнить нужное действие для каждого подходящего элемента', "
    "'подтвердить у пользователя необратимые шаги', 'сформировать итоговый отчёт'). "
    "Отвечай только списком шагов, без вступлений."
)


class Planner:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def make_plan(self, task: str) -> str:
        try:
            resp = self.llm.call(
                system=PLANNER_SYSTEM,
                messages=[{"role": "user", "content": f"Задача пользователя: {task}"}],
            )
            return resp.text.strip() or "(план не сформирован, действуй по обстановке)"
        except Exception:
            # план — это оптимизация, а не критический путь; при сбое просто продолжаем без него
            return "(план не сформирован из-за ошибки планировщика, действуй по обстановке шаг за шагом)"


class StagnationDetector:
    def __init__(self, patience: int = 2):
        self.patience = patience
        self._last_fingerprint: str | None = None
        self._stagnant_count = 0

    @staticmethod
    def _fingerprint(url: str, elements_text: str) -> str:
        h = hashlib.sha256((url + "||" + elements_text).encode("utf-8", "ignore")).hexdigest()
        return h

    def observe(self, url: str, elements_text: str) -> str | None:
        fp = self._fingerprint(url, elements_text)
        if fp == self._last_fingerprint:
            self._stagnant_count += 1
        else:
            self._stagnant_count = 0
        self._last_fingerprint = fp

        if self._stagnant_count >= self.patience:
            return (
                "ВНИМАНИЕ: несколько последних действий не изменили состояние страницы "
                "(тот же URL и тот же набор элементов). Вероятно, предыдущее действие не "
                "сработало (элемент невидим/перекрыт, координаты устарели, нужен scroll, "
                "открылась модалка/попап, требуется другой элемент). Не повторяй то же самое "
                "действие вслепую — проанализируй текущее состояние заново и попробуй другой подход "
                "(например: сначала прокрути, проверь наличие всплывающих окон, выбери другой элемент)."
            )
        return None
