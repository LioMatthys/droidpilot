"""Recorded flows: capture a sequence of device actions, replay it, and report.

A Flow is an ordered list of Steps. Each Step is a device method name plus its
kwargs (tap_text, type_text, swipe, wait_for_text, assert_text, ...). FlowRunner
dispatches each step to the Device and produces a FlowReport (per-step pass/fail
+ timing) so a flow doubles as a test.

Recording wraps a Device: every action call is appended as a Step and then
delegated, so you can drive the phone once (by agent or by hand through the API)
and save the result as a re-runnable script.
"""
from __future__ import annotations

import inspect
import json
import time
from dataclasses import asdict, dataclass, field

from .errors import DroidPilotError

# Device methods that mutate the screen or assert about it — the recordable /
# replayable surface. Read-only helpers (dump_ui, find_*) are intentionally excluded.
ACTION_METHODS = frozenset(
    {
        "tap",
        "tap_text",
        "type_text",
        "swipe",
        "swipe_dir",
        "long_press",
        "press_key",
        "back",
        "home",
        "enter",
        "wait_for_text",
        "assert_text",
        "launch_app",
        "stop_app",
    }
)


@dataclass
class Step:
    op: str
    args: dict = field(default_factory=dict)
    label: str = ""


@dataclass
class StepResult:
    op: str
    args: dict
    ok: bool
    error: str = ""
    duration_ms: int = 0


@dataclass
class FlowReport:
    name: str
    results: list[StepResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.ok)

    def summary(self) -> str:
        lines = [f"=== FLOW: {self.name} ==="]
        for r in self.results:
            mark = "PASS" if r.ok else "FAIL"
            detail = f"  — {r.error}" if r.error else ""
            arg_str = f"({', '.join(f'{k}={v!r}' for k, v in r.args.items())})" if r.args else ""
            lines.append(f"{mark}  {r.op}{arg_str}  [{r.duration_ms}ms]{detail}")
        lines.append(f"\n{self.passed_count}/{len(self.results)} steps passed")
        return "\n".join(lines)


class Flow:
    """An ordered, serializable list of steps."""

    def __init__(self, name: str, steps: list[Step] | None = None):
        self.name = name
        self.steps: list[Step] = steps or []

    def add(self, op: str, label: str = "", **args) -> "Flow":
        self.steps.append(Step(op=op, args=args, label=label))
        return self

    def to_dict(self) -> dict:
        return {"name": self.name, "steps": [asdict(s) for s in self.steps]}

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "Flow":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Flow":
        steps = [Step(op=s["op"], args=s.get("args", {}), label=s.get("label", "")) for s in data["steps"]]
        return cls(name=data.get("name", "flow"), steps=steps)


class FlowRunner:
    """Replays a Flow against a Device and reports per-step results.

    A failed step (raised DroidPilotError, e.g. assert_text / wait_for_text timeout)
    is recorded and, by default, stops the run — a later step usually depends on the
    earlier one having succeeded. Set continue_on_error=True to run every step.
    """

    def __init__(self, device, continue_on_error: bool = False):
        self.device = device
        self.continue_on_error = continue_on_error

    def run(self, flow: Flow) -> FlowReport:
        report = FlowReport(name=flow.name)
        for step in flow.steps:
            result = self._run_step(step)
            report.results.append(result)
            if not result.ok and not self.continue_on_error:
                break
        return report

    def _run_step(self, step: Step) -> StepResult:
        if step.op not in ACTION_METHODS:
            return StepResult(step.op, step.args, ok=False, error=f"unknown/non-replayable op: {step.op}")
        method = getattr(self.device, step.op, None)
        if method is None:
            return StepResult(step.op, step.args, ok=False, error=f"device has no method {step.op!r}")
        start = time.monotonic()
        try:
            method(**step.args)
            ok, err = True, ""
        except DroidPilotError as e:
            ok, err = False, str(e)
        except Exception as e:  # noqa: BLE001 — surface any device error as a step failure
            ok, err = False, f"{type(e).__name__}: {e}"
        dur = int((time.monotonic() - start) * 1000)
        return StepResult(step.op, step.args, ok=ok, error=err, duration_ms=dur)


class RecordingDevice:
    """Proxies a Device, recording every action call as a Step. Read-only calls
    pass through untouched. Use .flow(name) to get the captured Flow.

        rec = RecordingDevice(device)
        rec.tap_text("Settings"); rec.type_text("hello")
        rec.flow("login").save("login.json")
    """

    def __init__(self, device, name: str = "recording"):
        self._device = device
        self._steps: list[Step] = []
        self._name = name

    def flow(self, name: str | None = None) -> Flow:
        return Flow(name=name or self._name, steps=list(self._steps))

    def __getattr__(self, attr: str):
        target = getattr(self._device, attr)
        if attr not in ACTION_METHODS or not callable(target):
            return target

        def wrapper(*a, **kw):
            # Bind positional + keyword args to parameter names so the Step is
            # fully serializable (JSON has no positional concept).
            try:
                bound = inspect.signature(target).bind(*a, **kw)
                bound.apply_defaults()
                args = {k: v for k, v in bound.arguments.items() if k != "self"}
            except TypeError:
                args = dict(kw)
            self._steps.append(Step(op=attr, args=args))
            return target(*a, **kw)

        return wrapper
