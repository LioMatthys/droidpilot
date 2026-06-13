"""MCP server: exposes the Android device as tools an AI agent (e.g. Claude Code)
can call to run user tests. Transport is stdio (Claude Code launches it).
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP, Image

from .device import Device
from .errors import DroidPilotError

mcp = FastMCP(
    "droidpilot",
    instructions=(
        "Drive a connected Android phone to run user tests. "
        "Typical loop: call screen() or screenshot() to see the screen, decide the "
        "next action, then tap_text()/tap()/type_text()/press_key(), and verify with "
        "assert_text(). Prefer tap_text and the screen() element list over raw "
        "coordinates. Requires USB debugging enabled on the device."
    ),
)

_device: Device | None = None


def _dev() -> Device:
    """Return a connected Device, (re)validating the connection each call."""
    global _device
    if _device is None:
        _device = Device()
    _device.connect()  # raises a clear NoDeviceError if not ready
    return _device


@mcp.tool()
def list_devices() -> str:
    """List connected Android devices and their state (device/unauthorized/offline)."""
    devices = Device().adb.list_devices()
    if not devices:
        return "No devices connected. Plug in the phone and enable USB debugging."
    return "\n".join(
        f"{d.serial}  state={d.state}  model={d.model or '?'}" for d in devices
    )


@mcp.tool()
def launch_app(package: str) -> str:
    """Launch an app by its Android package name (e.g. 'life.overture.beam')."""
    _dev().launch_app(package)
    return f"Launched {package}."


@mcp.tool()
def stop_app(package: str) -> str:
    """Force-stop an app by package name."""
    _dev().stop_app(package)
    return f"Stopped {package}."


@mcp.tool()
def screen() -> str:
    """Return a compact text list of the on-screen elements (label, tap point, id).
    Cheaper than a screenshot; use this to choose what to tap."""
    return _dev().screen_summary()


@mcp.tool()
def screenshot() -> Image:
    """Capture the current screen as a PNG so you can visually inspect it."""
    return Image(data=_dev().screenshot(), format="png")


@mcp.tool()
def tap(x: int, y: int) -> str:
    """Tap at absolute screen coordinates."""
    _dev().tap(x, y)
    return f"Tapped ({x}, {y})."


@mcp.tool()
def tap_text(text: str, exact: bool = False) -> str:
    """Tap the first element whose text/description contains `text`
    (set exact=True to match the whole label)."""
    node = _dev().tap_text(text, exact=exact)
    x, y = node.center
    return f'Tapped "{node.label}" at ({x}, {y}).'


@mcp.tool()
def type_text(text: str) -> str:
    """Type text into the currently focused field."""
    _dev().type_text(text)
    return f"Typed: {text}"


@mcp.tool()
def press_key(key: str) -> str:
    """Press a key: back, home, enter, tab, delete, menu, app_switch, or a raw KEYCODE_*."""
    _dev().press_key(key)
    return f"Pressed {key}."


@mcp.tool()
def swipe(direction: str) -> str:
    """Swipe up, down, left, or right from the center of the screen."""
    _dev().swipe_dir(direction)
    return f"Swiped {direction}."


@mcp.tool()
def wait_for_text(text: str, timeout: float = 10.0) -> str:
    """Wait until an element containing `text` appears (up to `timeout` seconds)."""
    node = _dev().wait_for_text(text, timeout=timeout)
    return f'Found "{node.label}".'


@mcp.tool()
def assert_text(text: str) -> str:
    """Assert that an element containing `text` is on screen. Raises if absent."""
    _dev().assert_text(text)
    return f'PASS: "{text}" is on screen.'


@mcp.tool()
def screen_size() -> str:
    """Return the device screen size as 'WIDTHxHEIGHT'."""
    w, h = _dev().screen_size()
    return f"{w}x{h}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
