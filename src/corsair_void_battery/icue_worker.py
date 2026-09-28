"""Isolated process for the optional native iCUE SDK."""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import asdict
from typing import Any

from cuesdk import (
    CorsairDeviceFilter,
    CorsairDevicePropertyId,
    CorsairDeviceType,
    CorsairError,
    CorsairSessionState,
    CueSdk,
)

from .icue import coerce_battery_percent
from .models import BatteryReading, IcueResult


def read_icue_battery_direct(timeout_seconds: float = 5.0) -> IcueResult:
    """Read the headset property in-process. Only called by this worker."""

    result = IcueResult()
    state_ready = threading.Event()
    connected = False
    sdk: Any = None

    def on_state_changed(event: Any) -> None:
        nonlocal connected
        result.session_state = str(event.state)
        connected = event.state == CorsairSessionState.CSS_Connected
        if connected or event.state in {
            CorsairSessionState.CSS_Closed,
            CorsairSessionState.CSS_Timeout,
            CorsairSessionState.CSS_ConnectionRefused,
            CorsairSessionState.CSS_ConnectionLost,
        }:
            state_ready.set()

    try:
        sdk = CueSdk()
        connect_error = sdk.connect(on_state_changed)
        if connect_error != CorsairError.CE_Success:
            result.error = f"iCUE SDK connection failed: {connect_error}"
            return result

        if not state_ready.wait(timeout_seconds):
            result.error = "timed out waiting for iCUE SDK"
            return result
        if not connected:
            result.error = f"iCUE SDK is not connected ({result.session_state or 'unknown state'})"
            return result

        device_filter = CorsairDeviceFilter(CorsairDeviceType.CDT_Headset)
        devices, devices_error = sdk.get_devices(device_filter)
        if devices_error != CorsairError.CE_Success:
            result.error = f"could not enumerate iCUE headsets: {devices_error}"
            return result
        if not devices:
            result.error = "iCUE reported no Corsair headsets"
            return result

        devices.sort(key=lambda device: "VOID" not in device.model.upper())
        property_id = CorsairDevicePropertyId(CorsairDevicePropertyId.CDPI_BatteryLevel)
        errors: list[str] = []
        for device in devices:
            prop, property_error = sdk.read_device_property(device.device_id, property_id)
            if property_error != CorsairError.CE_Success or prop is None:
                errors.append(f"{device.model}: {property_error}")
                continue

            percent = coerce_battery_percent(prop.value)
            if percent is None:
                errors.append(f"{device.model}: invalid value {prop.value!r}")
                continue

            result.device_id = device.device_id
            result.model = device.model
            result.reading = BatteryReading(percent, percent, "icue-sdk")
            return result

        result.error = "battery property unavailable"
        if errors:
            result.error += f" ({'; '.join(errors)})"
        return result
    except (OSError, RuntimeError, ValueError) as exc:
        result.error = f"iCUE SDK error: {exc}"
        return result
    finally:
        if sdk is not None and connected:
            sdk.disconnect()


def main() -> None:
    timeout_seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    print(json.dumps(asdict(read_icue_battery_direct(timeout_seconds))))


if __name__ == "__main__":
    main()
