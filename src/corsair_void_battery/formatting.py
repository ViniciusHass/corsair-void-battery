from __future__ import annotations

from typing import Any

from .models import IcueResult, ProbeResult


def hex_value(value: Any) -> str:
    if value is None:
        return "-"
    return f"0x{int(value):04X}"


def path_text(path: Any) -> str:
    if isinstance(path, bytes):
        return path.decode(errors="replace")
    return str(path)


def report_text(report: list[int] | bytes | None) -> str:
    if not report:
        return "<no report>"
    return " ".join(f"{byte:02X}" for byte in report)


def battery_bar(percent: int, width: int = 20) -> str:
    """Build a fixed-width battery bar containing its numeric percentage."""

    clamped = min(100, max(0, percent))
    filled = (clamped * width + 50) // 100
    return f"[{'#' * filled}{'-' * (width - filled)}] {clamped:3d}%"


def battery_status(percent: int, source: str = "HID") -> str:
    return f"Corsair VOID Wireless V2 {battery_bar(percent)} ({source})"


def print_inventory(devices: list[dict[str, Any]]) -> None:
    if not devices:
        print("No Corsair HID interfaces found.")
        return

    print(f"Found {len(devices)} Corsair HID interface(s):")
    for index, info in enumerate(devices):
        print(f"\n[{index}] {info.get('product_string') or '<unknown product>'}")
        vendor_id = hex_value(info.get("vendor_id"))
        product_id = hex_value(info.get("product_id"))
        print(f"  VID:PID       {vendor_id}:{product_id}")
        print(f"  interface     {info.get('interface_number', '-')}")
        print(f"  usage page/id {hex_value(info.get('usage_page'))}/{hex_value(info.get('usage'))}")
        print(f"  serial        {info.get('serial_number') or '-'}")
        print(f"  path          {path_text(info.get('path'))}")


def print_probe(result: ProbeResult, *, diagnostic: bool = False) -> None:
    if diagnostic:
        print(
            f"\nProbe PID={hex_value(result.product_id)} "
            f"interface={result.interface_number} usage_page={hex_value(result.usage_page)}"
        )
        for index, (source, report) in enumerate(
            zip(result.report_sources, result.v2_reports, strict=True), start=1
        ):
            print(f"  report {index} ({source}): {report_text(report)}")

    if result.battery_percent is not None:
        if diagnostic:
            print(
                f"  battery: {result.battery_percent}% "
                f"(raw={result.battery_raw}, protocol={result.battery_protocol})"
            )
        else:
            print(f"Corsair VOID Wireless V2 battery: {result.battery_percent}%")
    elif result.error:
        prefix = "  error" if diagnostic else "Battery read failed"
        print(f"{prefix}: {result.error}")
    else:
        message = "  battery: no valid response" if diagnostic else "Battery unavailable."
        print(message)


def print_icue_result(result: IcueResult) -> None:
    if result.reading is not None:
        model = result.model or "Corsair headset"
        print(f"{model} battery: {result.reading.percent}% (iCUE SDK)")
    elif result.error:
        print(f"iCUE battery unavailable: {result.error}")
