class DroidPilotError(Exception):
    """Base error for droidpilot."""


class AdbNotFound(DroidPilotError):
    """The adb executable could not be located."""


class NoDeviceError(DroidPilotError):
    """No usable Android device is connected/authorized."""


class ElementNotFound(DroidPilotError):
    """A UI element matching the selector was not found (within the timeout)."""


class AssertionFailed(DroidPilotError):
    """An expectation about the screen was not met."""
