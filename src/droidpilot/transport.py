"""Pluggable backends for driving the device.

- AdbTransport: the default — drives the phone over adb/UIAutomator (USB or
  wireless-adb), exactly as DroidPilot has always done.
- BeamTransport: drives the phone over the wireless Beam control channel by
  talking newline-delimited control JSON to the Beam (Electron) localhost relay,
  which forwards it to the on-phone AccessibilityService. See ../../PROTOCOL.md.

Device (device.py) is transport-agnostic: it composes these primitives into the
high-level API (tap_text, wait_for_text, assert_text, …).
"""
from __future__ import annotations

import json
import re
import socket
from typing import Protocol, runtime_checkable

from .adb import Adb, DeviceInfo
from .errors import DroidPilotError

_SIZE_RE = re.compile(r"(\d+)x(\d+)")

_KEY_ALIASES = {
    "back": "KEYCODE_BACK", "home": "KEYCODE_HOME", "enter": "KEYCODE_ENTER",
    "tab": "KEYCODE_TAB", "delete": "KEYCODE_DEL", "backspace": "KEYCODE_DEL",
    "menu": "KEYCODE_MENU", "search": "KEYCODE_SEARCH", "app_switch": "KEYCODE_APP_SWITCH",
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


@runtime_checkable
class Transport(Protocol):
    """Low-level device primitives. AdbTransport implements all; BeamTransport
    implements the MVP subset (connect/screen_size/tap) and will grow."""

    def connect(self) -> object: ...
    def screen_size(self) -> tuple[int, int]: ...
    def launch_app(self, package: str) -> None: ...
    def stop_app(self, package: str) -> None: ...
    def tap(self, x: int, y: int) -> None: ...
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None: ...
    def type_text(self, text: str) -> None: ...
    def press_key(self, key: str) -> None: ...
    def dump_xml(self) -> str: ...
    def screenshot(self) -> bytes: ...


class AdbTransport:
    """Drives the device via adb shell + UIAutomator (the original backend)."""

    name = "adb"

    def __init__(self, serial: str | None = None, adb_path: str | None = None):
        self.adb = Adb(serial=serial, adb_path=adb_path)

    def connect(self) -> DeviceInfo:
        return self.adb.require_device()

    def screen_size(self) -> tuple[int, int]:
        out = self.adb.shell("wm size")
        m = _SIZE_RE.search(out.split("Override size:")[-1] if "Override" in out else out)
        return (int(m.group(1)), int(m.group(2))) if m else (1080, 1920)

    def launch_app(self, package: str) -> None:
        self.adb.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")

    def stop_app(self, package: str) -> None:
        self.adb.shell(f"am force-stop {package}")

    def tap(self, x: int, y: int) -> None:
        self.adb.shell(f"input tap {int(x)} {int(y)}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.adb.shell(f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {duration_ms}")

    def type_text(self, text: str) -> None:
        self.adb.shell(f"input text {_escape_text(text)}")

    def press_key(self, key: str) -> None:
        self.adb.shell(f"input keyevent {_KEY_ALIASES.get(key.lower(), key)}")

    def dump_xml(self) -> str:
        self.adb.shell("uiautomator dump /sdcard/dp_dump.xml >/dev/null 2>&1 || uiautomator dump")
        return self.adb.exec_out("cat /sdcard/dp_dump.xml").decode("utf-8", "replace")

    def screenshot(self) -> bytes:
        return self.adb.exec_out("screencap -p")


class BeamTransport:
    """Drives the device over the wireless Beam control channel via the Beam
    localhost relay. Speaks newline-delimited control JSON (same message shape as
    PROTOCOL.md's CONTROL channel; newline-framed for this localhost hop)."""

    name = "beam"
    DEFAULT_PORT = 8788  # the Beam (Electron) localhost relay

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT, timeout: float = 15.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buf = b""
        self._id = 0

    def connect(self) -> dict:
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._sock.settimeout(self.timeout)
        return {"transport": "beam", "relay": f"{self.host}:{self.port}"}

    def _rpc(self, op: str, args: dict | None = None):
        if self._sock is None:
            self.connect()
        assert self._sock is not None
        self._id += 1
        msg = {"id": self._id, "op": op, "args": args or {}}
        self._sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        line = self._read_line()
        resp = json.loads(line)
        if not resp.get("ok"):
            raise DroidPilotError(f"control op {op} failed: {resp.get('error', 'unknown error')}")
        return resp.get("result")

    def _read_line(self) -> str:
        while b"\n" not in self._buf:
            assert self._sock is not None
            chunk = self._sock.recv(65536)
            if not chunk:
                raise DroidPilotError("Beam relay closed the connection.")
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return line.decode("utf-8", "replace")

    # --- MVP ops ---
    def screen_size(self) -> tuple[int, int]:
        r = self._rpc("screen_size")
        return (int(r["width"]), int(r["height"]))

    def tap(self, x: int, y: int) -> None:
        self._rpc("tap", {"x": int(x), "y": int(y)})

    # --- not in the MVP yet (grow as the on-phone executor gains ops) ---
    def launch_app(self, package: str) -> None:
        self._rpc("launch_app", {"package": package})

    def stop_app(self, package: str) -> None:
        self._rpc("stop_app", {"package": package})

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._rpc("swipe", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration_ms": duration_ms})

    def type_text(self, text: str) -> None:
        self._rpc("type_text", {"text": text})

    def press_key(self, key: str) -> None:
        self._rpc("press_key", {"key": key})

    def dump_xml(self) -> str:
        raise DroidPilotError("dump_xml not available over Beam yet (coming in control v1).")

    def screenshot(self) -> bytes:
        raise DroidPilotError("screenshot not available over Beam yet (use the live cast).")

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            finally:
                self._sock = None
