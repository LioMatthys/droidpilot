"""High-level device control: launch, tap, type, swipe, screenshot, UI queries."""
from __future__ import annotations

import re
import time
from typing import Callable

from .adb import Adb, DeviceInfo
from .errors import AssertionFailed, ElementNotFound
from . import ui
from .ui import UiNode

_SIZE_RE = re.compile(r"(\d+)x(\d+)")

_KEY_ALIASES = {
    "back": "KEYCODE_BACK",
    "home": "KEYCODE_HOME",
    "enter": "KEYCODE_ENTER",
    "tab": "KEYCODE_TAB",
    "delete": "KEYCODE_DEL",
    "backspace": "KEYCODE_DEL",
    "menu": "KEYCODE_MENU",
    "search": "KEYCODE_SEARCH",
    "power": "KEYCODE_POWER",
    "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
    "app_switch": "KEYCODE_APP_SWITCH",
}

_SPECIAL = set("()&|;<>*?[]$`\"'\\#~")


def _escape_text(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch == " ":
            out.append("%s")
        elif ch in _SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


class Device:
    """A connected Android device. All actions go through adb."""

    def __init__(self, serial: str | None = None, adb_path: str | None = None):
        self.adb = Adb(serial=serial, adb_path=adb_path)
        self._size: tuple[int, int] | None = None

    def connect(self) -> DeviceInfo:
        info = self.adb.require_device()
        return info

    # --- info ---------------------------------------------------------------
    def screen_size(self) -> tuple[int, int]:
        if self._size is None:
            out = self.adb.shell("wm size")
            # "Physical size: 1080x2400" (and maybe an Override size line)
            m = _SIZE_RE.search(out.split("Override size:")[-1] if "Override" in out else out)
            self._size = (int(m.group(1)), int(m.group(2))) if m else (1080, 1920)
        return self._size

    def current_app(self) -> str:
        """Best-effort foreground package name."""
        out = self.adb.shell(
            "dumpsys activity activities | grep -E 'mResumedActivity|ResumedActivity' | head -1"
        )
        m = re.search(r"\s([a-zA-Z0-9_.]+)/", out)
        return m.group(1) if m else ""

    # --- actions ------------------------------------------------------------
    def launch_app(self, package: str) -> None:
        self.adb.shell(
            f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
        )

    def stop_app(self, package: str) -> None:
        self.adb.shell(f"am force-stop {package}")

    def tap(self, x: int, y: int) -> None:
        self.adb.shell(f"input tap {int(x)} {int(y)}")

    def long_press(self, x: int, y: int, duration_ms: int = 600) -> None:
        self.adb.shell(f"input swipe {int(x)} {int(y)} {int(x)} {int(y)} {duration_ms}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.adb.shell(f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {duration_ms}")

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
        self.swipe(*moves[direction], duration_ms=duration_ms)

    def type_text(self, text: str) -> None:
        self.adb.shell(f"input text {_escape_text(text)}")

    def press_key(self, key: str) -> None:
        code = _KEY_ALIASES.get(key.lower(), key)
        self.adb.shell(f"input keyevent {code}")

    def back(self) -> None:
        self.press_key("back")

    def home(self) -> None:
        self.press_key("home")

    def enter(self) -> None:
        self.press_key("enter")

    # --- vision -------------------------------------------------------------
    def screenshot(self, path: str | None = None) -> bytes:
        data = self.adb.exec_out("screencap -p")
        if path:
            with open(path, "wb") as f:
                f.write(data)
        return data

    def dump_xml(self) -> str:
        # Dump to a file on the device, then read it back (most reliable path).
        self.adb.shell("uiautomator dump /sdcard/dp_dump.xml >/dev/null 2>&1 || uiautomator dump")
        raw = self.adb.exec_out("cat /sdcard/dp_dump.xml")
        return raw.decode("utf-8", "replace")

    def dump_ui(self) -> UiNode:
        return ui.parse_hierarchy(self.dump_xml())

    def screen_summary(self, max_nodes: int = 80) -> str:
        return ui.summarize(self.dump_ui(), max_nodes=max_nodes)

    # --- queries / waits ----------------------------------------------------
    def find(self, pred: Callable[[UiNode], bool]) -> UiNode | None:
        return self.dump_ui().find(pred)

    def find_by_text(self, text: str, exact: bool = False) -> UiNode | None:
        return self.dump_ui().find(ui.by_text(text, exact=exact))

    def tap_text(self, text: str, exact: bool = False) -> UiNode:
        node = self.find_by_text(text, exact=exact)
        if node is None:
            raise ElementNotFound(f"No element matching text {text!r}")
        x, y = node.center
        self.tap(x, y)
        return node

    def wait_for(
        self,
        pred: Callable[[UiNode], bool],
        timeout: float = 10.0,
        interval: float = 0.5,
    ) -> UiNode:
        deadline = time.monotonic() + timeout
        last_exc: Exception | None = None
        while time.monotonic() < deadline:
            try:
                node = self.dump_ui().find(pred)
            except Exception as e:  # transient dump failure during transitions
                last_exc = e
                node = None
            if node is not None:
                return node
            time.sleep(interval)
        if last_exc:
            raise ElementNotFound(f"Element not found within {timeout}s ({last_exc})")
        raise ElementNotFound(f"Element not found within {timeout}s")

    def wait_for_text(self, text: str, timeout: float = 10.0, exact: bool = False) -> UiNode:
        return self.wait_for(ui.by_text(text, exact=exact), timeout=timeout)

    def assert_text(self, text: str, exact: bool = False) -> None:
        if self.find_by_text(text, exact=exact) is None:
            raise AssertionFailed(f"Expected text {text!r} on screen, not found.")
