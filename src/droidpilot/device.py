"""High-level device control, composed over a Transport (adb or Beam).

The primitives (tap, type_text, screen_size, dump_xml, screenshot, …) come from
the Transport; the high-level helpers (tap_text, wait_for_text, assert_text, …)
are transport-agnostic and live here.
"""
from __future__ import annotations

import time
from typing import Callable

from . import ui
from .errors import AssertionFailed, ElementNotFound
from .transport import AdbTransport, Transport
from .ui import UiNode


class Device:
    def __init__(
        self,
        serial: str | None = None,
        adb_path: str | None = None,
        transport: Transport | None = None,
    ):
        self.t: Transport = transport or AdbTransport(serial=serial, adb_path=adb_path)
        self._size: tuple[int, int] | None = None

    @property
    def transport(self) -> Transport:
        return self.t

    def connect(self) -> object:
        return self.t.connect()

    # --- info ---
    def screen_size(self) -> tuple[int, int]:
        if self._size is None:
            self._size = self.t.screen_size()
        return self._size

    # --- actions (delegate to transport) ---
    def launch_app(self, package: str) -> None:
        self.t.launch_app(package)

    def stop_app(self, package: str) -> None:
        self.t.stop_app(package)

    def tap(self, x: int, y: int) -> None:
        self.t.tap(x, y)

    def long_press(self, x: int, y: int, duration_ms: int = 600) -> None:
        self.t.swipe(x, y, x, y, duration_ms)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.t.swipe(x1, y1, x2, y2, duration_ms)

    def swipe_dir(self, direction: str, duration_ms: int = 300) -> None:
        w, h = self.screen_size()
        cx, cy = w // 2, h // 2
        dx, dy = int(w * 0.35), int(h * 0.35)
        moves = {
            "up": (cx, cy + dy, cx, cy - dy),
            "down": (cx, cy - dy, cx, cy + dy),
            "left": (cx + dx, cy, cx - dx, cy),
            "right": (cx - dx, cy, cx + dx, cy),
        }
        if direction not in moves:
            raise ValueError(f"direction must be up/down/left/right, got {direction!r}")
        self.t.swipe(*moves[direction], duration_ms=duration_ms)

    def type_text(self, text: str) -> None:
        self.t.type_text(text)

    def press_key(self, key: str) -> None:
        self.t.press_key(key)

    def back(self) -> None:
        self.t.press_key("back")

    def home(self) -> None:
        self.t.press_key("home")

    def enter(self) -> None:
        self.t.press_key("enter")

    # --- vision ---
    def screenshot(self, path: str | None = None) -> bytes:
        data = self.t.screenshot()
        if path:
            with open(path, "wb") as f:
                f.write(data)
        return data

    def dump_xml(self) -> str:
        return self.t.dump_xml()

    def dump_ui(self) -> UiNode:
        return ui.parse_hierarchy(self.dump_xml())

    def screen_summary(self, max_nodes: int = 80) -> str:
        return ui.summarize(self.dump_ui(), max_nodes=max_nodes)

    def read_screen(self, max_nodes: int = 80) -> dict:
        """Read the screen, preferring the element tree. Falls back to a screenshot
        (PNG bytes) when the accessibility tree is empty (games, WebViews, custom
        canvases), so a vision-capable agent can still see what's on screen.

        Returns {"mode": "elements", "summary": str} or {"mode": "image", "png": bytes}.
        """
        try:
            root = self.dump_ui()
            has_labeled = any(n.text or n.content_desc or n.clickable for n in root.walk())
        except Exception:
            has_labeled = False
        if has_labeled:
            return {"mode": "elements", "summary": ui.summarize(root, max_nodes=max_nodes)}
        return {"mode": "image", "png": self.screenshot()}

    # --- queries / waits ---
    def find(self, pred: Callable[[UiNode], bool]) -> UiNode | None:
        return self.dump_ui().find(pred)

    def find_by_text(self, text: str, exact: bool = False) -> UiNode | None:
        return self.dump_ui().find(ui.by_text(text, exact=exact))

    def tap_text(self, text: str, exact: bool = False) -> UiNode:
        node = self.find_by_text(text, exact=exact)
        if node is None:
            raise ElementNotFound(f"No element matching text {text!r}")
        x, y = node.center
        self.t.tap(x, y)
        return node

    def wait_for(
        self, pred: Callable[[UiNode], bool], timeout: float = 10.0, interval: float = 0.5
    ) -> UiNode:
        deadline = time.monotonic() + timeout
        last_exc: Exception | None = None
        while time.monotonic() < deadline:
            try:
                node = self.dump_ui().find(pred)
            except Exception as e:
                last_exc = e
                node = None
            if node is not None:
                return node
            time.sleep(interval)
        raise ElementNotFound(
            f"Element not found within {timeout}s" + (f" ({last_exc})" if last_exc else "")
        )

    def wait_for_text(self, text: str, timeout: float = 10.0, exact: bool = False) -> UiNode:
        return self.wait_for(ui.by_text(text, exact=exact), timeout=timeout)

    def assert_text(self, text: str, exact: bool = False) -> None:
        if self.find_by_text(text, exact=exact) is None:
            raise AssertionFailed(f"Expected text {text!r} on screen, not found.")
