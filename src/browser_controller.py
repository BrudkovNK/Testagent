from __future__ import annotations
import base64
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError as PWTimeout

from .config import CONFIG

_JS_PATH = Path(__file__).parent / "dom_extractor.js"


class ActionError(Exception):
    """Ошибка выполнения действия в браузере — ловится agent-циклом для retry/адаптации."""

@dataclass
class ElementInfo:
    index: int
    tag: str
    role: str
    name: str
    in_viewport: bool
    extra: dict = field(default_factory=dict)

    def to_line(self) -> str:
        bits = [f"[{self.index}] <{self.tag}> role={self.role}"]
        if self.name:
            bits.append(f'"{self.name}"')
        for k in ("inputType", "href", "checked", "selected"):
            if k in self.extra and self.extra[k] not in (None, ""):
                bits.append(f"{k}={self.extra[k]}")
        if not self.in_viewport:
            bits.append("(вне текущей области экрана — нужен scroll)")
        return " ".join(bits)


@dataclass
class PageState:
    url: str
    title: str
    elements: list[ElementInfo]
    headings: list[str]
    scroll_y: int
    scroll_height: int
    viewport_height: int
    total_found: int
    screenshot_b64: Optional[str] = None

    def elements_text(self) -> str:
        if not self.elements:
            return "(интерактивных элементов не найдено)"
        return "\n".join(e.to_line() for e in self.elements)

    def scroll_hint(self) -> str:
        if self.scroll_height <= self.viewport_height + 50:
            return ""
        pct_seen = min(100, round((self.scroll_y + self.viewport_height) / max(self.scroll_height, 1) * 100))
        return f"Прокрутка: показано ~{pct_seen}% страницы по высоте. Если нужного элемента нет в списке — используй scroll."


class BrowserController:
    def __init__(self, config=CONFIG):
        self.cfg = config
        self._pw = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._extractor_js = _JS_PATH.read_text(encoding="utf-8")
        self._last_state: Optional[PageState] = None

    def start(self):
        self._pw = sync_playwright().start()
        Path(self.cfg.user_data_dir).mkdir(parents=True, exist_ok=True)
        self.context = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.cfg.user_data_dir,
            headless=self.cfg.headless,
            slow_mo=self.cfg.slow_mo_ms,
            viewport={"width": self.cfg.viewport_width, "height": self.cfg.viewport_height},
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(self.cfg.action_timeout_ms)
        if self.cfg.default_start_url and self.cfg.default_start_url != "about:blank":
            self.navigate(self.cfg.default_start_url)
        return self

    def stop(self):
        try:
            if self.context:
                self.context.close()
        finally:
            if self._pw:
                self._pw.stop()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    def _inject(self):
        self.page.evaluate(self._extractor_js)

    def get_state(self, with_screenshot: Optional[bool] = None) -> PageState:
        self._settle()
        self._inject()
        raw = self.page.evaluate(
            "window.__agentExtract(%s)"
            % json.dumps({
                "maxElements": self.cfg.max_elements_per_state,
                "textCap": self.cfg.max_text_field_chars,
            })
        )
        data = json.loads(raw)

        elements = []
        for e in data["elements"]:
            extra = {k: v for k, v in e.items() if k not in ("index", "tag", "role", "name", "inViewport", "rect")}
            elements.append(ElementInfo(
                index=e["index"], tag=e["tag"], role=e["role"], name=e["name"],
                in_viewport=e["inViewport"], extra=extra,
            ))

        screenshot_b64 = None
        use_shot = self.cfg.use_screenshots if with_screenshot is None else with_screenshot
        if use_shot:
            screenshot_b64 = self._marked_screenshot()

        state = PageState(
            url=data["url"], title=data["title"], elements=elements,
            headings=data.get("headings", []), scroll_y=data["scrollY"],
            scroll_height=data["scrollHeight"], viewport_height=data["viewportHeight"],
            total_found=data["totalInteractiveFound"], screenshot_b64=screenshot_b64,
        )
        self._last_state = state
        return state

    def _marked_screenshot(self) -> Optional[str]:
        try:
            self.page.evaluate("window.__agentMark()")
            png = self.page.screenshot(type="png")
            self.page.evaluate("window.__agentUnmark()")
            png = _maybe_resize(png, self.cfg.screenshot_max_width)
            return base64.b64encode(png).decode("ascii")
        except Exception:
            return None

    def _settle(self):
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=self.cfg.action_timeout_ms)
        except PWTimeout:
            pass
        time.sleep(self.cfg.nav_wait_ms / 1000)


    def _resolve(self, index: int):
        handle = self.page.evaluate_handle(f"window.__agentElements[{int(index)}]")
        el = handle.as_element()
        if el is None:
            raise ActionError(
                f"Элемент #{index} не найден (возможно, страница изменилась). "
                f"Сначала получи актуальное состояние страницы."
            )
        return el

    def click(self, index: int):
        el = self._resolve(index)
        try:
            el.scroll_into_view_if_needed(timeout=self.cfg.action_timeout_ms)
            el.click(timeout=self.cfg.action_timeout_ms)
        except PWTimeout as e:
            raise ActionError(f"Не удалось кликнуть по элементу #{index}: таймаут ({e})")
        except Exception as e:
            raise ActionError(f"Не удалось кликнуть по элементу #{index}: {e}")

    def type_text(self, index: int, text: str, clear: bool = True, press_enter: bool = False):
        el = self._resolve(index)
        try:
            el.scroll_into_view_if_needed(timeout=self.cfg.action_timeout_ms)
            el.click(timeout=self.cfg.action_timeout_ms)
            if clear:
                el.fill("")
            el.type(text, delay=15)
            if press_enter:
                el.press("Enter")
        except Exception as e:
            raise ActionError(f"Не удалось ввести текст в элемент #{index}: {e}")

    def select_option(self, index: int, value: str):
        el = self._resolve(index)
        try:
            el.select_option(label=value)
        except Exception:
            try:
                el.select_option(value=value)
            except Exception as e:
                raise ActionError(f"Не удалось выбрать опцию '{value}' в элементе #{index}: {e}")

    def scroll(self, direction: str = "down", amount: float = 1.0):
        delta = int(self.cfg.viewport_height * amount)
        if direction == "up":
            delta = -delta
        self.page.mouse.wheel(0, delta)
        time.sleep(0.3)

    def go_back(self):
        self.page.go_back()

    def navigate(self, url: str):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=self.cfg.action_timeout_ms)
        except PWTimeout:
            pass

    def press_key(self, key: str):
        self.page.keyboard.press(key)

    def wait(self, seconds: float):
        time.sleep(max(0.0, min(seconds, 20.0)))

    def get_element_full_text(self, index: int) -> str:
        el = self._resolve(index)
        try:
            return el.inner_text()
        except Exception as e:
            raise ActionError(f"Не удалось прочитать текст элемента #{index}: {e}")

    def raw_screenshot_b64(self) -> str:
        png = self.page.screenshot(type="png")
        png = _maybe_resize(png, self.cfg.screenshot_max_width)
        return base64.b64encode(png).decode("ascii")


def _maybe_resize(png_bytes: bytes, max_width: int) -> bytes:
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(png_bytes))
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        return png_bytes
