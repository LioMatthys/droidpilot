"""Scripted example: drive the Beam app and verify the sharing screen.

This is the library-only path (no agent). Run with a phone connected:
    python examples/test_beam_flow.py

The Beam app: https://github.com/LioMatthys/Beam
Note: the system screen-capture dialog ("Start now") is localized — on a French
phone it reads "Démarrer maintenant". Adjust the strings to your device locale.
"""
from droidpilot import Device

PACKAGE = "life.overture.beam"


def main() -> None:
    dev = Device()
    info = dev.connect()
    print(f"Connected: {info.serial} ({info.model})")

    dev.launch_app(PACKAGE)
    dev.wait_for_text("Beam", timeout=15)
    print("Beam launched.")

    # Start sharing -> system consent dialog -> Start now
    dev.tap_text("Start sharing")
    try:
        dev.wait_for_text("Start now", timeout=8)
        dev.tap_text("Start now")
    except Exception:
        print("(no system consent dialog matched — check device locale)")

    # The sharing screen shows IP / port / a 6-digit code
    dev.wait_for_text("Code", timeout=10)
    print("Sharing screen reached. Elements:")
    print(dev.screen_summary())
    dev.screenshot("beam_sharing.png")
    print("Saved beam_sharing.png — PASS")


if __name__ == "__main__":
    main()
