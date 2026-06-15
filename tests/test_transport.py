"""Verify BeamTransport's control RPC end to end against a fake relay/phone
(no device, no Electron) — proves the laptop side speaks the wire correctly."""
import json
import socket
import threading

import pytest

from droidpilot import ui
from droidpilot.errors import DroidPilotError
from droidpilot.transport import BeamTransport


class FakeRelay:
    """A localhost server that speaks the newline-JSON control protocol the
    Beam relay exposes: reads {"id","op","args"}, replies {"id","ok","result"}."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.requests: list[dict] = []
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        conn, _ = self.sock.accept()
        buf = b""
        with conn:
            while True:
                while b"\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                line, _, buf = buf.partition(b"\n")
                req = json.loads(line)
                self.requests.append(req)
                op = req["op"]
                if op == "screen_size":
                    result = {"width": 1080, "height": 2400}
                elif op in ("tap", "swipe", "back", "home", "type_text", "long_press"):
                    result = None
                elif op == "scroll_to_element":
                    result = {"found": True, "bounds": [40, 2200, 200, 2280]}
                elif op == "wait_for_text":
                    result = {"found": True}
                elif op == "dump":
                    result = {
                        "nodes": [
                            {
                                "text": "Settings",
                                "cls": "android.widget.TextView",
                                "clickable": True,
                                "bounds": [40, 2200, 200, 2280],
                            },
                            {
                                "desc": "Start sharing",
                                "cls": "android.widget.Button",
                                "clickable": True,
                                "bounds": [100, 1000, 980, 1120],
                            },
                        ]
                    }
                else:
                    conn.sendall(
                        (json.dumps({"id": req["id"], "ok": False, "error": f"unknown op {op}"}) + "\n").encode()
                    )
                    continue
                conn.sendall((json.dumps({"id": req["id"], "ok": True, "result": result}) + "\n").encode())

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def test_beam_transport_screen_size_and_tap():
    relay = FakeRelay()
    t = BeamTransport(host="127.0.0.1", port=relay.port)
    t.connect()
    assert t.screen_size() == (1080, 2400)
    t.tap(540, 1060)
    t.close()
    relay.thread.join(timeout=2)

    # wire-level assertions: monotonic ids, correct ops + args
    assert relay.requests[0]["op"] == "screen_size"
    assert relay.requests[0]["id"] == 1
    assert relay.requests[1]["op"] == "tap"
    assert relay.requests[1]["id"] == 2
    assert relay.requests[1]["args"] == {"x": 540, "y": 1060}
    relay.close()


def test_beam_transport_swipe_and_keys_wire():
    relay = FakeRelay()
    t = BeamTransport(host="127.0.0.1", port=relay.port)
    t.connect()
    t.swipe(10, 20, 30, 40, duration_ms=200)
    t.press_key("back")
    t.press_key("home")
    t.close()
    relay.thread.join(timeout=2)

    assert relay.requests[0]["op"] == "swipe"
    # the on-phone executor reads camelCase durationMs
    assert relay.requests[0]["args"] == {"x1": 10, "y1": 20, "x2": 30, "y2": 40, "durationMs": 200}
    assert relay.requests[1]["op"] == "back"
    assert relay.requests[2]["op"] == "home"
    relay.close()


def test_beam_transport_dump_xml_is_parseable():
    relay = FakeRelay()
    t = BeamTransport(host="127.0.0.1", port=relay.port)
    t.connect()
    xml = t.dump_xml()
    t.close()
    relay.thread.join(timeout=2)

    # The synthesized XML must parse with the same UIAutomator parser adb uses,
    # and elements must be findable by text/desc with correct centers.
    root = ui.parse_hierarchy(xml)
    settings = root.find(ui.by_text("Settings"))
    assert settings is not None
    assert settings.center == (120, 2240)
    assert settings.clickable is True
    assert root.find(ui.by_desc("Start sharing")) is not None
    relay.close()


def test_beam_transport_surfaces_phone_error():
    relay = FakeRelay()
    t = BeamTransport(host="127.0.0.1", port=relay.port)
    t.connect()
    with pytest.raises(DroidPilotError):
        t._rpc("totally_unknown_op")  # FakeRelay replies ok:false
    t.close()
    relay.close()


def test_beam_transport_local_unsupported_ops():
    t = BeamTransport(host="127.0.0.1", port=1)  # no connect; these raise locally
    for call in (
        t.screenshot,
        lambda: t.launch_app("com.x"),
        lambda: t.stop_app("com.x"),
        lambda: t.press_key("enter"),
    ):
        with pytest.raises(DroidPilotError):
            call()
