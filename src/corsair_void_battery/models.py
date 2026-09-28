from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProbeResult:
    path: str
    product_id: int | None
    interface_number: int | None
    usage_page: int | None
    usage: int | None
    v2_reports: list[list[int]]
    report_sources: list[str]
    battery_raw: int | None = None
    battery_percent: int | None = None
    battery_protocol: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class BatteryReading:
    percent: int
    raw: int
    protocol: str


@dataclass
class IcueResult:
    reading: BatteryReading | None = None
    device_id: str | None = None
    model: str | None = None
    session_state: str | None = None
    error: str | None = None
