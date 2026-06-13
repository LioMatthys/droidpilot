"""Verify BeamTransport's control RPC end to end against a fake relay/phone
(no device, no Electron) — proves the laptop side speaks the wire correctly."""
import json
import socket
import threading

import pytest

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
                    resp = {"id": req["id"], "ok": True, "result": {"width": 1080, "height": 2400}}
                elif op == "tap":
                    resp = {"id": req["id"], "ok": True, "result": None}
                else:
                    resp = {"id": req["id"], "ok": False, "error": f"unknown op {op}"}
                conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))

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


def test_beam_transport_surfaces_phone_error():
    relay = FakeRelay()
    t = BeamTransport(host="127.0.0.1", port=relay.port)
    t.connect()
    with pytest.raises(DroidPilotError):
        t.launch_app("com.nope")  # FakeRelay replies ok:false for unknown op
    t.close()
    relay.close()


def test_beam_transport_local_unsupported_ops():
    t = BeamTransport(host="127.0.0.1", port=1)  # no connect needed; raises locally
    with pytest.raises(DroidPilotError):
        t.dump_xml()
    with pytest.raises(DroidPilotError):
        t.screenshot()
