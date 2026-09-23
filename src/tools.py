from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TOOLS = [
    {
        "name": "get_page_state",
        "description": (
            "Получить актуальное состояние текущей страницы: список видимых интерактивных "
            "элементов (пронумерованных), заголовки, URL. Вызывай, если подозреваешь, что "
            "страница изменилась (после ожидания, после действия стороннего скрипта), хотя "
            "обычно состояние уже автоматически обновляется после каждого твоего действия."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "navigate",
        "description": "Открыть указанный URL в браузере.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Полный URL, например https://mail.yandex.ru"}},
            "required": ["url"],
        },
    },
    {
        "name": "click",
        "description": "Кликнуть по интерактивному элементу с указанным индексом из последнего состояния страницы.",
        "input_schema": {
            "type": "object",
            "properties": {"index": {"type": "integer", "description": "Индекс элемента, например 7"}},
            "required": ["index"],
        },
    },
    {
        "name": "type_text",
        "description": (
            "Ввести текст в поле ввода/textarea с указанным индексом. По умолчанию поле "
            "предварительно очищается."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "text": {"type": "string"},
                "press_enter": {"type": "boolean", "description": "Нажать Enter после ввода (например, для поиска)"},
                "clear": {"type": "boolean", "description": "Очистить поле перед вводом (по умолчанию true)"},
            },
            "required": ["index", "text"],
        },
    },
    {
        "name": "select_option",
        "description": "Выбрать значение в выпадающем списке <select> по видимому тексту опции.",
        "input_schema": {
            "type": "object",
            "properties": {"index": {"type": "integer"}, "value": {"type": "string"}},
            "required": ["index", "value"],
        },
    },
    {
        "name": "scroll",
        "description": "Прокрутить страницу, чтобы увидеть элементы за пределами текущей видимой области.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"]},
                "amount": {"type": "number", "description": "Сколько высот экрана прокрутить, по умолчанию 1"},
            },
            "required": ["direction"],
        },
    },
    {
        "name": "go_back",
        "description": "Вернуться на предыдущую страницу браузерной истории.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_element",
        "description": (
            "Прочитать полный текст элемента (и его дочерних узлов) по индексу — полезно, "
            "когда в компактном списке элементов текст обрезан, а нужно прочитать письмо, "
            "описание вакансии, состав заказа и т.п. целиком."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"index": {"type": "integer"}},
            "required": ["index"],
        },
    },
    {
        "name": "wait",
        "description": "Подождать указанное число секунд (максимум 20) — например, пока догрузится динамический контент.",
        "input_schema": {
            "type": "object",
            "properties": {"seconds": {"type": "number"}},
            "required": ["seconds"],
        },
    },
    {
        "name": "request_confirmation",
        "description": (
            "ОБЯЗАТЕЛЬНО вызови перед любым необратимым/деструктивным действием "
            "(финальная оплата, безвозвратное удаление, окончательная отправка отклика/заявки/сообщения) — "
            "ДО того как кликнуть по соответствующему элементу. Опиши, что именно "
            "собираешься сделать, простым языком. Если пользователь откажет — не повторяй это действие "
            "и предложи альтернативу или заверши задачу с пояснением."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"action_description": {"type": "string"}},
            "required": ["action_description"],
        },
    },
    {
        "name": "ask_user",
        "description": (
            "Задать пользователю вопрос и дождаться ответа — используй, только если задачу "
            "объективно нельзя продолжить без дополнительной информации от пользователя "
            "(двусмысленность, отсутствие нужных данных, неожиданная ошибка/капча и т.п.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
    {
        "name": "finish",
        "description": "Завершить работу над задачей: либо она выполнена, либо дальнейшее выполнение невозможно.",
        "input_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "summary": {"type": "string", "description": "Итоговый отчёт для пользователя"},
            },
            "required": ["success", "summary"],
        },
    },
]


@dataclass
class ToolResult:
    ok: bool
    content: str
    finished: bool = False
    finish_success: bool | None = None
    needs_user_input: bool = False


def describe_call(name: str, inp: dict[str, Any]) -> str:
    if name == "click":
        return f"click(#{inp.get('index')})"
    if name == "type_text":
        return f"type_text(#{inp.get('index')}, \"{str(inp.get('text',''))[:40]}\")"
    if name == "navigate":
        return f"navigate({inp.get('url')})"
    if name == "scroll":
        return f"scroll({inp.get('direction')}, {inp.get('amount', 1)})"
    if name == "select_option":
        return f"select_option(#{inp.get('index')}, \"{inp.get('value')}\")"
    if name == "read_element":
        return f"read_element(#{inp.get('index')})"
    if name == "wait":
        return f"wait({inp.get('seconds')}s)"
    if name == "request_confirmation":
        return f"request_confirmation(\"{str(inp.get('action_description',''))[:60]}\")"
    if name == "ask_user":
        return f"ask_user(\"{str(inp.get('question',''))[:60]}\")"
    if name == "finish":
        return f"finish(success={inp.get('success')})"
    return f"{name}({inp})"
