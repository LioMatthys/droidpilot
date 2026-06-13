"""Low-level adb: locate the binary, run commands, list devices."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import AdbNotFound, NoDeviceError


def resolve_adb() -> str:
    """Find adb: ANDROID_HOME / default SDK location / PATH."""
    candidates: list[Path] = []
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(env)
        if root:
            candidates.append(Path(root) / "platform-tools" / "adb")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Android" / "Sdk" / "platform-tools" / "adb")
    home = Path.home()
    candidates.append(home / "Library" / "Android" / "sdk" / "platform-tools" / "adb")  # macOS
    candidates.append(home / "Android" / "Sdk" / "platform-tools" / "adb")  # Linux

    for c in candidates:
        for p in (c, c.with_suffix(".exe")):
            if p.exists():
                return str(p)

    found = shutil.which("adb")
    if found:
        return found
    raise AdbNotFound(
        "adb not found. Install Android platform-tools or set ANDROID_HOME."
    )


@dataclass
class DeviceInfo:
    serial: str
    state: str  # "device", "unauthorized", "offline", ...
    model: str | None = None

    @property
    def ready(self) -> bool:
        return self.state == "device"


class Adb:
    """Thin wrapper around the adb executable, optionally pinned to one serial."""

    def __init__(self, serial: str | None = None, adb_path: str | None = None):
        self.adb_path = adb_path or resolve_adb()
        self.serial = serial

    def _base(self) -> list[str]:
        base = [self.adb_path]
        if self.serial:
            base += ["-s", self.serial]
        return base

    def run(self, args: list[str], timeout: float = 30.0, binary: bool = False):
        """Run `adb <args>`. Returns str (text) or bytes (binary=True)."""
        proc = subprocess.run(
            self._base() + args,
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(f"adb {' '.join(args)} failed: {err}")
        return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")

    def shell(self, command: str, timeout: float = 30.0) -> str:
        return self.run(["shell", command], timeout=timeout)

    def exec_out(self, command: str, timeout: float = 30.0) -> bytes:
        """exec-out keeps binary output intact (e.g. screencap)."""
        return self.run(["exec-out", command], timeout=timeout, binary=True)

    def list_devices(self) -> list[DeviceInfo]:
        out = self.run(["devices", "-l"])
        devices: list[DeviceInfo] = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            serial, state = parts[0], parts[1]
            model = None
            for tok in parts[2:]:
                if tok.startswith("model:"):
                    model = tok[len("model:"):].replace("_", " ")
            devices.append(DeviceInfo(serial=serial, state=state, model=model))
        return devices

    def require_device(self) -> DeviceInfo:
        """Pick the pinned serial, or the single ready device. Raise otherwise."""
        devices = self.list_devices()
        ready = [d for d in devices if d.ready]
        if self.serial:
            for d in devices:
                if d.serial == self.serial:
                    if not d.ready:
                        raise NoDeviceError(f"Device {self.serial} is '{d.state}'.")
                    return d
            raise NoDeviceError(f"Device {self.serial} not connected.")
        if not ready:
            if any(d.state == "unauthorized" for d in devices):
                raise NoDeviceError(
                    "Device unauthorized — unlock the phone and accept the USB-debugging prompt."
                )
            raise NoDeviceError(
                "No device. Connect the phone by USB with USB debugging enabled."
            )
        if len(ready) > 1:
            raise NoDeviceError(
                "Multiple devices connected; pass a serial. Ready: "
                + ", ".join(d.serial for d in ready)
            )
        self.serial = ready[0].serial
        return ready[0]
