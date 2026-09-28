from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from typing import Any

from .formatting import battery_status, path_text, print_icue_result, print_inventory, print_probe
from .icue import read_icue_battery
from .protocol import enumerate_devices, is_v2_candidate, probe_v2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Enumerate and probe a Corsair VOID Wireless V2 HID receiver."
    )
    parser.add_argument(
        "--icue",
        action="store_true",
        help="use the optional iCUE SDK instead of the default direct HID protocol",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="run as a Windows notification-tray application",
    )
    startup_group = parser.add_mutually_exclusive_group()
    startup_group.add_argument(
        "--install-startup",
        action="store_true",
        help="start tray mode automatically when the current user signs in",
    )
    startup_group.add_argument(
        "--remove-startup",
        action="store_true",
        help="remove the current user's automatic tray startup entry",
    )
    parser.add_argument(
        "--build-executable",
        action="store_true",
        help="build a standalone no-console tray executable for this Windows system",
    )
    parser.add_argument(
        "--probe-all",
        action="store_true",
        help="probe every Corsair HID interface instead of V2-looking interfaces only",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="show every HID interface and raw response",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=250,
        metavar="MS",
        help="HID read timeout in milliseconds (default: 250)",
    )
    parser.add_argument(
        "--listen-ms",
        type=int,
        default=1000,
        metavar="MS",
        help="listen for unsolicited battery reports after querying (default: 1000)",
    )
    parser.add_argument(
        "--watch",
        type=float,
        default=60,
        metavar="SECONDS",
        help="seconds between successful battery checks (default: 60)",
    )
    parser.add_argument(
        "--retry-seconds",
        type=float,
        default=600,
        metavar="SECONDS",
        help="wait before re-enumerating after disconnect/no battery (default: 600)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="probe once and exit instead of monitoring continuously",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    return parser


def _run_once(args: argparse.Namespace) -> tuple[int, str]:
    if args.icue:
        icue_result = read_icue_battery()
        if args.json:
            print(json.dumps({"icue": asdict(icue_result)}, indent=2, default=str))
        elif args.diagnostic:
            print_icue_result(icue_result)
        if icue_result.reading is not None:
            return 0, battery_status(icue_result.reading.percent, "iCUE")
        return 1, f"iCUE battery unavailable: {icue_result.error or 'unknown error'}"

    devices: list[dict[str, Any]] = enumerate_devices()
    candidates = [device for device in devices if args.probe_all or is_v2_candidate(device)]
    results = [probe_v2(device, args.timeout, args.listen_ms) for device in candidates]
    hid_succeeded = any(result.battery_percent is not None for result in results)

    if args.json:
        payload: dict[str, Any] = {
            "devices": [{**device, "path": path_text(device.get("path"))} for device in devices],
            "probes": [asdict(result) for result in results],
        }
        print(json.dumps(payload, indent=2, default=str))
    elif args.diagnostic:
        if devices:
            print_inventory(devices)
        if not results:
            print("Corsair VOID Wireless V2 receiver battery interface not found.")
        for probe_result in results:
            print_probe(probe_result, diagnostic=True)

    if hid_succeeded:
        percent = next(
            result.battery_percent for result in results if result.battery_percent is not None
        )
        return 0, battery_status(percent)
    if not results:
        return 1, "Corsair VOID Wireless V2 receiver not found"
    error = next((result.error for result in results if result.error), None)
    return 1, f"Battery unavailable{f': {error}' if error else ''}"


def _replace_status_line(message: str, previous_width: int) -> int:
    """Redraw one console line and erase any remainder of the previous text."""

    padding = " " * max(0, previous_width - len(message))
    print(f"\r{message}{padding}", end="", flush=True)
    return len(message)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.build_executable:
        from .build import build_tray_executable

        try:
            executable = build_tray_executable()
        except ModuleNotFoundError as exc:
            if exc.name == "PyInstaller":
                print(
                    "PyInstaller is not installed; run `uv sync --extra build` first.",
                    file=sys.stderr,
                )
                raise SystemExit(2) from None
            raise
        print(f"Built tray executable: {executable}")
        return

    if args.install_startup or args.remove_startup:
        from .startup import set_startup_enabled

        enabled = args.install_startup
        set_startup_enabled(enabled)
        state = "installed" if enabled else "removed"
        print(f"Windows startup entry {state}.")
        return

    if args.timeout <= 0 or args.listen_ms < 0 or args.retry_seconds <= 0 or args.watch <= 0:
        print(
            "--timeout, --watch, and --retry-seconds must be positive; "
            "--listen-ms cannot be negative",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if args.tray:
        from .tray import run_tray

        run_tray(
            check_seconds=args.watch,
            retry_seconds=args.retry_seconds,
            timeout_ms=args.timeout,
            listen_ms=args.listen_ms,
        )
        return

    compact_output = not args.diagnostic and not args.json
    status_width = 0
    try:
        while True:
            exit_code, status = _run_once(args)
            delay = args.watch if exit_code == 0 else args.retry_seconds

            if compact_output:
                suffix = "next check" if exit_code == 0 else "retry"
                line = status if args.once else f"{status} | {suffix} in {delay:g}s"
                status_width = _replace_status_line(line, status_width)

            if args.once:
                if compact_output:
                    print()
                raise SystemExit(exit_code)

            time.sleep(delay)
    except KeyboardInterrupt:
        if compact_output:
            print()
        raise SystemExit(130) from None
