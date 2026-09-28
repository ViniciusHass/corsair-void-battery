"""Opt-in access to battery data through Corsair's official iCUE SDK."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

from .models import BatteryReading, IcueResult


def coerce_battery_percent(value: object) -> int | None:
    """Convert an SDK property value to a validated percentage."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    percent = round(value)
    return percent if 0 <= percent <= 100 else None


def read_icue_battery(timeout_seconds: float = 5.0) -> IcueResult:
    """Run the optional native SDK in an isolated child process."""

    if importlib.util.find_spec("cuesdk") is None:
        return IcueResult(
            error="optional SDK is not installed; run `uv sync --extra icue`",
        )

    command = [
        sys.executable,
        "-m",
        "corsair_void_battery.icue_worker",
        str(timeout_seconds),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds + 2,
        )
    except subprocess.TimeoutExpired:
        return IcueResult(error="iCUE SDK worker timed out")

    if completed.returncode != 0:
        windows_code = completed.returncode & 0xFFFFFFFF
        return IcueResult(
            error=f"iCUE SDK worker exited with 0x{windows_code:08X}; use direct HID mode",
        )

    try:
        payload = json.loads(completed.stdout)
        reading_data = payload.pop("reading", None)
        reading = BatteryReading(**reading_data) if reading_data is not None else None
        return IcueResult(reading=reading, **payload)
    except (json.JSONDecodeError, TypeError) as exc:
        return IcueResult(error=f"invalid iCUE SDK worker response: {exc}")
