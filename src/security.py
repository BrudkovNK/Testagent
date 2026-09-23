from __future__ import annotations
import re

from .config import CONFIG

_DESTRUCTIVE_PATTERNS = [
    # оплата / покупка
    r"\bопла", r"\bкупить\b", r"\bкупит\b", r"\bподтверд.*заказ", r"\bpay\b",
    r"\bcheckout\b", r"\bplace order\b", r"\bconfirm order\b", r"\bpurchase\b",
    # удаление
    r"\bудал", r"\bdelete\b", r"\bremove\b", r"\bочистить\b",
    # безвозвратная отправка
    r"\bотправ.*отклик", r"\bотправ.*заявк", r"\bоткликнуться\b",
    r"\bsubmit\b", r"\bsend\b", r"\bapply\b", r"\bприменить\b",
    # аккаунт / деньги / необратимые операции
    r"\bперевести\b", r"\btransfer\b", r"\bподтвердить\b", r"\bconfirm\b",
    r"\bunsubscribe\b", r"\bотписаться\b", r"\bзаблокировать\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _DESTRUCTIVE_PATTERNS]


def looks_destructive(text: str) -> bool:
    text = text or ""
    return any(p.search(text) for p in _COMPILED)


def element_looks_destructive(element_name: str, role: str, tag: str) -> bool:
    if role not in ("button", "link") and tag not in ("button", "a", "input"):
        return False
    return looks_destructive(element_name)


class ConfirmationDenied(Exception):
    """Пользователь отклонил действие — агент должен остановиться и не повторять его."""
def ask_confirmation(cli, description: str) -> bool:
    if not CONFIG.require_confirmation:
        return True
    return cli.ask_yes_no(
        f"\n⚠️  ПОДТВЕРЖДЕНИЕ ТРЕБУЕТСЯ: агент хочет выполнить действие:\n"
        f"    {description}\n"
        f"Это похоже на необратимое/деструктивное действие. Разрешить? [y/N]: "
    )
