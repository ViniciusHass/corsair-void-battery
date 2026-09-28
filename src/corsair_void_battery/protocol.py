from __future__ import annotations

import time
from typing import Any

import hid

from .constants import (
    CORSAIR_VENDOR_ID,
    HEADSET_ENDPOINT,
    RECEIVER_ENDPOINT,
    REPORT_SIZE,
    V2_INPUT_REPORT_ID,
    V2_OUTPUT_REPORT_ID,
    V2_USAGE_PAGE,
    V2_WRITE_SIZE,
    VOID_WIRELESS_V2_PRODUCT_ID,
)
from .formatting import path_text
from .models import BatteryReading, ProbeResult


def enumerate_devices() -> list[dict[str, Any]]:
    """Return all Corsair HID interfaces visible to hidapi."""

    return list(hid.enumerate(CORSAIR_VENDOR_ID, 0))


def is_v2_candidate(device: dict[str, Any]) -> bool:
    """Identify the receiver's battery-capable vendor collection."""

    return (
        device.get("product_id") == VOID_WIRELESS_V2_PRODUCT_ID
        and device.get("interface_number") == 4
        and device.get("usage_page") == V2_USAGE_PAGE
        and device.get("usage") == 1
    )


def build_packet(command: list[int], *, endpoint: int) -> bytes:
    """Build a Windows-compatible V2 output report.

    The V2 ``0xFF42`` collection declares output report ID ``2`` and a total
    report size of 64 bytes. On Windows, hidapi expects the report ID in byte
    zero, followed immediately by the endpoint and command payload.
    """

    data = bytearray(V2_WRITE_SIZE)
    data[0] = V2_OUTPUT_REPORT_ID
    data[1] = endpoint
    data[2 : 2 + len(command)] = bytes(command)
    return bytes(data)


def parse_battery_report(report: list[int]) -> BatteryReading | None:
    """Parse a V2 response or the older VOID status notification."""

    # A direct V2 command response does not echo the physical endpoint or
    # command. Battery replies use this generic response header; callers only
    # pass responses correlated with a battery request to this parser.
    if len(report) >= 6 and report[:4] == [V2_INPUT_REPORT_ID, 0x01, 0x02, 0x00]:
        raw = report[4] | (report[5] << 8)
        if 1 <= raw <= 1000:
            return BatteryReading(percent=raw // 10, raw=raw, protocol="void-v2")

    # The receiver can also publish an asynchronous battery event. This is the
    # layout used by the V2 dongle listener when charge changes while connected.
    if len(report) >= 7 and report[0:2] == [0x03, 0x01] and report[3] == 0x0F:
        raw = report[5] | (report[6] << 8)
        if 1 <= raw <= 1000:
            return BatteryReading(percent=raw // 10, raw=raw, protocol="void-v2-event")

    # Older VOID devices report ID 0x64 and store percentage in byte 2.
    if len(report) >= 5 and report[0] == 0x64:
        status = report[4]
        level = report[2] & 0x7F
        if status in {1, 2, 3, 4, 5} and 0 <= level <= 100:
            return BatteryReading(percent=level, raw=level, protocol="void-legacy")

    return None


def _flush(device: hid.device, timeout_ms: int = 5) -> None:
    while device.read(REPORT_SIZE, timeout_ms):
        pass


def _write(device: hid.device, report: bytes) -> None:
    written = device.write(report)
    if written < 0:
        error = device.error() or "unknown HID write error"
        raise OSError(str(error))


def _read_until(
    device: hid.device,
    timeout_ms: int,
    listen_ms: int,
) -> list[list[int]]:
    reports: list[list[int]] = []
    deadline = time.monotonic() + listen_ms / 1000
    while time.monotonic() < deadline:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        report = list(device.read(REPORT_SIZE, min(timeout_ms, remaining_ms)))
        if report:
            reports.append(report)
    return reports


def _transact(
    device: hid.device,
    result: ProbeResult,
    label: str,
    command: list[int],
    endpoint: int,
    timeout_ms: int,
) -> list[list[int]]:
    """Send one command and retain every response seen before its deadline."""

    _flush(device)
    _write(device, build_packet(command, endpoint=endpoint))
    reports = _read_until(device, timeout_ms, timeout_ms)
    for report in reports:
        result.v2_reports.append(report)
        result.report_sources.append(label)
    return reports


def probe_v2(
    device_info: dict[str, Any],
    timeout_ms: int,
    listen_ms: int,
) -> ProbeResult:
    """Wake the receiver and request the paired headset battery status."""

    result = ProbeResult(
        path=path_text(device_info["path"]),
        product_id=device_info.get("product_id"),
        interface_number=device_info.get("interface_number"),
        usage_page=device_info.get("usage_page"),
        usage=device_info.get("usage"),
        v2_reports=[],
        report_sources=[],
    )
    device = hid.device()
    try:
        device.open_path(device_info["path"])
        device.set_nonblocking(False)

        receiver_in_software_mode = False
        headset_in_software_mode = False
        try:
            _transact(
                device,
                result,
                "receiver software mode",
                [0x01, 0x03, 0x00, 0x02],
                RECEIVER_ENDPOINT,
                timeout_ms,
            )
            receiver_in_software_mode = True
            _transact(
                device,
                result,
                "headset heartbeat",
                [0x12],
                HEADSET_ENDPOINT,
                timeout_ms,
            )
            _transact(
                device,
                result,
                "headset firmware",
                [0x02, 0x13],
                HEADSET_ENDPOINT,
                timeout_ms,
            )
            _transact(
                device,
                result,
                "headset software mode",
                [0x01, 0x03, 0x00, 0x02],
                HEADSET_ENDPOINT,
                timeout_ms,
            )
            headset_in_software_mode = True

            for attempt in range(1, 4):
                reports = _transact(
                    device,
                    result,
                    f"battery request {attempt}",
                    [0x02, 0x0F],
                    HEADSET_ENDPOINT,
                    timeout_ms,
                )
                reading = next(
                    (parsed for report in reports if (parsed := parse_battery_report(report))),
                    None,
                )
                if reading is not None:
                    result.battery_raw = reading.raw
                    result.battery_percent = reading.percent
                    result.battery_protocol = reading.protocol
                    break

            if result.battery_percent is None and listen_ms:
                for report in _read_until(device, timeout_ms, listen_ms):
                    result.v2_reports.append(report)
                    result.report_sources.append("unsolicited")
                    reading = parse_battery_report(report)
                    if reading is not None:
                        result.battery_raw = reading.raw
                        result.battery_percent = reading.percent
                        result.battery_protocol = reading.protocol
                        break
        finally:
            # Restore hardware mode so a one-shot query does not retain control
            # of the receiver or interfere with iCUE after this process exits.
            if headset_in_software_mode:
                _transact(
                    device,
                    result,
                    "headset hardware mode",
                    [0x01, 0x03, 0x00, 0x01],
                    HEADSET_ENDPOINT,
                    timeout_ms,
                )
            if receiver_in_software_mode:
                _transact(
                    device,
                    result,
                    "receiver hardware mode",
                    [0x01, 0x03, 0x00, 0x01],
                    RECEIVER_ENDPOINT,
                    timeout_ms,
                )
    except OSError as exc:
        result.error = str(exc)
    finally:
        device.close()
    return result
