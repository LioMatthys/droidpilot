"""Minimal CLI for manual use / smoke testing the control library."""
from __future__ import annotations

import argparse
import sys

from .adb import Adb
from .device import Device
from .errors import DroidPilotError
from .transport import BeamTransport


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="droidpilot", description="Drive an Android device.")
    p.add_argument("-s", "--serial", help="target device serial (adb backend)")
    p.add_argument(
        "-b", "--beam", nargs="?", const="127.0.0.1:8788", metavar="HOST:PORT",
        help="drive over the wireless Beam relay instead of adb (default 127.0.0.1:8788)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("devices", help="list connected devices")
    sp = sub.add_parser("launch", help="launch app by package"); sp.add_argument("package")
    sp = sub.add_parser("tap", help="tap x y"); sp.add_argument("x", type=int); sp.add_argument("y", type=int)
    sp = sub.add_parser("tap-text", help="tap element by text"); sp.add_argument("text")
    sp = sub.add_parser("type", help="type text"); sp.add_argument("text")
    sp = sub.add_parser("key", help="press key (back/home/enter/...)"); sp.add_argument("key")
    sp = sub.add_parser("swipe", help="swipe direction"); sp.add_argument("direction")
    sp = sub.add_parser("screenshot", help="save screenshot"); sp.add_argument("path")
    sub.add_parser("screen", help="print on-screen elements")
    sub.add_parser("dump", help="print raw UIAutomator XML")
    sp = sub.add_parser("assert-text", help="assert text on screen"); sp.add_argument("text")

    args = p.parse_args(argv)

    try:
        if args.cmd == "devices":
            for d in Adb(serial=args.serial).list_devices():
                print(f"{d.serial}\t{d.state}\t{d.model or ''}")
            return 0

        if args.beam:
            host, _, port = args.beam.partition(":")
            dev = Device(transport=BeamTransport(host=host or "127.0.0.1", port=int(port) if port else 8788))
        else:
            dev = Device(serial=args.serial)
        dev.connect()

        if args.cmd == "launch":
            dev.launch_app(args.package); print(f"launched {args.package}")
        elif args.cmd == "tap":
            dev.tap(args.x, args.y); print(f"tapped {args.x},{args.y}")
        elif args.cmd == "tap-text":
            n = dev.tap_text(args.text); print(f'tapped "{n.label}" @{n.center}')
        elif args.cmd == "type":
            dev.type_text(args.text); print("typed")
        elif args.cmd == "key":
            dev.press_key(args.key); print(f"pressed {args.key}")
        elif args.cmd == "swipe":
            dev.swipe_dir(args.direction); print(f"swiped {args.direction}")
        elif args.cmd == "screenshot":
            dev.screenshot(args.path); print(f"saved {args.path}")
        elif args.cmd == "screen":
            print(dev.screen_summary())
        elif args.cmd == "dump":
            print(dev.dump_xml())
        elif args.cmd == "assert-text":
            dev.assert_text(args.text); print(f'PASS: "{args.text}"')
        return 0
    except DroidPilotError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
