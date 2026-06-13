"""droidpilot — drive Android over ADB/UIAutomator, expose it to an agent via MCP."""
from .adb import Adb, DeviceInfo, resolve_adb
from .device import Device
from .transport import AdbTransport, BeamTransport, Transport
from .errors import (
    AdbNotFound,
    AssertionFailed,
    DroidPilotError,
    ElementNotFound,
    NoDeviceError,
)
from .ui import UiNode, by_desc, by_resource_id, by_text, parse_hierarchy, summarize

__version__ = "0.1.0"

__all__ = [
    "Device",
    "Transport",
    "AdbTransport",
    "BeamTransport",
    "Adb",
    "DeviceInfo",
    "resolve_adb",
    "UiNode",
    "parse_hierarchy",
    "summarize",
    "by_text",
    "by_resource_id",
    "by_desc",
    "DroidPilotError",
    "AdbNotFound",
    "NoDeviceError",
    "ElementNotFound",
    "AssertionFailed",
]
