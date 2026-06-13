# DroidPilot

Drive an Android phone over **ADB + UIAutomator** and expose it to an AI agent over
**MCP** — Playwright-style, for native-app user testing.

The idea: while you build an Android app with **Claude Code on your computer**, that
same Claude can **drive your phone to run the user tests** — tap, type, read the
screen, and assert outcomes — by calling DroidPilot's tools over MCP. DroidPilot is
the hands and eyes; Claude is the brain.

```
Claude Code (your computer, the test agent)
        │  MCP (stdio)
        ▼
DroidPilot MCP server  ──►  adb / UIAutomator  ──►  Android phone (USB)
   tap · type · swipe · screenshot · dump UI · wait · assert
```

## Requirements

- **Python 3.10+**
- **adb** (Android platform-tools) on PATH or under `ANDROID_HOME`/the default SDK
- A phone with **USB debugging enabled** and authorized (unavoidable for controlling
  taps — unlike screen mirroring, driving the device needs adb)

## Install

```bash
pip install -e .          # from a clone
# or:  pip install git+https://github.com/LioMatthys/droidpilot
```

## Use it three ways

### 1. With Claude Code (the point) — MCP

Register the server once:

```bash
claude mcp add droidpilot -- droidpilot-mcp
# (equivalently:  claude mcp add droidpilot -- python -m droidpilot.mcp_server)
```

Then just ask Claude Code, e.g.:

> Plug-in check: my phone is connected. Test that Beam (`life.overture.beam`) shows a
> 6-digit code after I start sharing. Launch it, start sharing, accept the capture
> prompt, and confirm a code appears — screenshot the result.

Claude will call `screen` / `screenshot` to see the phone, `tap_text` / `type_text` to
act, and `assert_text` to verify — running the test like a human would.

### 2. As a CLI (manual / smoke testing)

```bash
droidpilot devices
droidpilot launch life.overture.beam
droidpilot screen                 # list on-screen elements
droidpilot tap-text "Start sharing"
droidpilot screenshot out.png
droidpilot assert-text "Code"
```

### 3. As a Python library (scripted tests)

```python
from droidpilot import Device

dev = Device(); dev.connect()
dev.launch_app("life.overture.beam")
dev.wait_for_text("Beam", timeout=15)
dev.tap_text("Start sharing")
dev.assert_text("Code")
dev.screenshot("beam.png")
```

See [`examples/test_beam_flow.py`](examples/test_beam_flow.py).

## MCP tools

| Tool | What it does |
|---|---|
| `list_devices` | connected devices + state |
| `launch_app(package)` / `stop_app(package)` | start/stop an app |
| `screen()` | compact text list of on-screen elements (label, tap point, id) |
| `screenshot()` | PNG of the current screen (visual inspection) |
| `tap(x,y)` / `tap_text(text)` | tap by coordinates or by element text |
| `type_text(text)` | type into the focused field |
| `press_key(key)` | back / home / enter / … or a raw `KEYCODE_*` |
| `swipe(direction)` | up / down / left / right |
| `wait_for_text(text, timeout)` | wait for an element to appear |
| `assert_text(text)` | pass/fail check that text is on screen |
| `screen_size()` | `WIDTHxHEIGHT` |

`screen()` (cheap text) + `screenshot()` (image) give the agent both a structured and a
visual view; it usually picks targets from `screen()` and uses `tap_text`.

## Limits (v0.1)

- One device at a time (pass a serial to target a specific one).
- System dialogs are **localized** — "Start now" vs "Démarrer maintenant". The agent
  reads the screen, so it adapts; scripted tests should match your device locale.
- No video recording yet; screenshots only.
- `type_text` escapes spaces/specials for `adb shell input`; exotic Unicode may not type.

## Why not Appium/Maestro?

Both are great, but heavier (a server + drivers, or YAML flows). DroidPilot is a thin,
agent-shaped surface: a handful of tools an LLM can call directly, built on the same
ADB/UIAutomator primitives Google ships. Use Appium/Maestro for big scripted suites;
use DroidPilot when you want **Claude to test the app for you**.
