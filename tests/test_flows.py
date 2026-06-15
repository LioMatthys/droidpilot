"""Recorded-flow engine: record → save/load → replay → report, with a fake device."""
from droidpilot.errors import AssertionFailed, ElementNotFound
from droidpilot.flows import Flow, FlowRunner, RecordingDevice, Step


class FakeDevice:
    """A device stub that records calls and can be told to fail specific ops."""

    def __init__(self, fail_ops=None, missing_text=None):
        self.calls = []
        self.fail_ops = fail_ops or {}
        self.missing_text = set(missing_text or [])

    def tap_text(self, text, exact=False):
        self.calls.append(("tap_text", text))
        if text in self.missing_text:
            raise ElementNotFound(f"No element matching text {text!r}")

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        self.calls.append(("swipe", x1, y1, x2, y2))

    def back(self):
        self.calls.append(("back",))

    def assert_text(self, text, exact=False):
        self.calls.append(("assert_text", text))
        if text in self.missing_text:
            raise AssertionFailed(f"Expected text {text!r} on screen, not found.")

    def wait_for_text(self, text, timeout=10.0, exact=False):
        self.calls.append(("wait_for_text", text))
        if text in self.missing_text:
            raise ElementNotFound(f"Element not found within {timeout}s")


def test_record_then_replay_round_trip(tmp_path):
    dev = FakeDevice()
    rec = RecordingDevice(dev, name="login")
    rec.tap_text("Email")
    rec.type_text("user@example.com")
    rec.tap_text("Next")

    flow = rec.flow()
    assert [s.op for s in flow.steps] == ["tap_text", "type_text", "tap_text"]
    # positional args were bound to names so the step is serializable
    assert flow.steps[1].args == {"text": "user@example.com"}

    # save + load preserves the flow
    path = tmp_path / "login.json"
    flow.save(str(path))
    reloaded = Flow.load(str(path))
    assert reloaded.name == "login"
    assert reloaded.steps[0].args["text"] == "Email"

    # replay drives a fresh device with the same calls
    dev2 = FakeDevice()
    report = FlowRunner(dev2).run(reloaded)
    assert report.passed
    assert report.passed_count == 3
    assert dev2.calls == [
        ("tap_text", "Email"),
        ("type_text", "user@example.com"),
        ("tap_text", "Next"),
    ]


def test_report_marks_failed_step_and_stops():
    dev = FakeDevice(missing_text={"Dashboard"})
    flow = Flow("verify").add("tap_text", text="Open").add("assert_text", text="Dashboard").add("back")
    report = FlowRunner(dev).run(flow)

    assert not report.passed
    assert report.passed_count == 1
    assert report.results[1].op == "assert_text"
    assert not report.results[1].ok
    assert "not found" in report.results[1].error.lower()
    # stopped after the failure: 'back' never ran
    assert len(report.results) == 2
    assert ("back",) not in dev.calls


def test_continue_on_error_runs_all_steps():
    dev = FakeDevice(missing_text={"Nope"})
    flow = Flow("f").add("assert_text", text="Nope").add("back")
    report = FlowRunner(dev, continue_on_error=True).run(flow)
    assert len(report.results) == 2
    assert ("back",) in dev.calls


def test_unknown_op_is_reported_not_raised():
    dev = FakeDevice()
    flow = Flow("f", [Step(op="frobnicate", args={})])
    report = FlowRunner(dev).run(flow)
    assert not report.passed
    assert "non-replayable" in report.results[0].error
