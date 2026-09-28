"""Windows notification-tray battery monitor."""

from __future__ import annotations

import threading

import pystray
from PIL import Image, ImageDraw

from .protocol import enumerate_devices, is_v2_candidate, probe_v2
from .startup import is_startup_enabled, set_startup_enabled

ICON_SIZE = 64


def _battery_color(percent: int) -> tuple[int, int, int, int]:
    if percent > 50:
        return (46, 204, 113, 255)
    if percent > 20:
        return (241, 196, 15, 255)
    return (231, 76, 60, 255)


def create_battery_icon(percent: int | None) -> Image.Image:
    """Draw a small battery icon suitable for the Windows notification area."""

    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    outline = (185, 190, 196, 255) if percent is None else (245, 245, 245, 255)
    draw.rounded_rectangle((4, 12, 53, 52), radius=7, outline=outline, width=4)
    draw.rounded_rectangle((54, 24, 62, 40), radius=2, fill=outline)

    if percent is None:
        draw.line((14, 22, 43, 43), fill=(231, 76, 60, 255), width=6)
        draw.line((43, 22, 14, 43), fill=(231, 76, 60, 255), width=6)
        return image

    clamped = min(100, max(0, percent))
    fill_width = round(41 * clamped / 100)
    if fill_width:
        draw.rounded_rectangle(
            (8, 16, 8 + fill_width, 48),
            radius=4,
            fill=_battery_color(clamped),
        )
    return image


class BatteryTrayApp:
    def __init__(
        self,
        *,
        check_seconds: float,
        retry_seconds: float,
        timeout_ms: int,
        listen_ms: int,
    ) -> None:
        self.check_seconds = check_seconds
        self.retry_seconds = retry_seconds
        self.timeout_ms = timeout_ms
        self.listen_ms = listen_ms
        self.status = "Checking Corsair VOID Wireless V2..."
        self.stop_event = threading.Event()
        self.refresh_event = threading.Event()
        self.icon = pystray.Icon(
            "corsair-void-battery",
            create_battery_icon(None),
            self.status,
            menu=pystray.Menu(
                pystray.MenuItem(lambda _item: self.status, None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Refresh now", self._refresh),
                pystray.MenuItem(
                    "Start with Windows",
                    self._toggle_startup,
                    checked=lambda _item: is_startup_enabled(),
                ),
                pystray.MenuItem("Exit", self._exit),
            ),
        )

    def _set_status(self, status: str, percent: int | None) -> None:
        self.status = status
        self.icon.title = status[:127]
        self.icon.icon = create_battery_icon(percent)
        self.icon.update_menu()

    def _read_battery(self) -> tuple[int | None, str]:
        try:
            devices = enumerate_devices()
            candidates = [device for device in devices if is_v2_candidate(device)]
            if not candidates:
                return None, "Corsair VOID Wireless V2 receiver disconnected"

            for device in candidates:
                result = probe_v2(device, self.timeout_ms, self.listen_ms)
                if result.battery_percent is not None:
                    return (
                        result.battery_percent,
                        f"Corsair VOID Wireless V2: {result.battery_percent}%",
                    )
                if result.error:
                    return None, f"Corsair battery unavailable: {result.error}"
            return None, "Corsair headset unavailable"
        except (OSError, RuntimeError) as exc:
            return None, f"Corsair battery error: {exc}"

    def _monitor(self) -> None:
        while not self.stop_event.is_set():
            percent, status = self._read_battery()
            self._set_status(status, percent)
            delay = self.check_seconds if percent is not None else self.retry_seconds
            self.refresh_event.wait(delay)
            self.refresh_event.clear()

    def _setup(self, icon: pystray.Icon) -> None:
        icon.visible = True
        threading.Thread(target=self._monitor, name="battery-monitor", daemon=True).start()

    def _refresh(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.refresh_event.set()

    def _toggle_startup(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        set_startup_enabled(not is_startup_enabled())
        self.icon.update_menu()

    def _exit(self, icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.stop_event.set()
        self.refresh_event.set()
        icon.stop()

    def run(self) -> None:
        self.icon.run(setup=self._setup)


def run_tray(
    *,
    check_seconds: float,
    retry_seconds: float,
    timeout_ms: int,
    listen_ms: int,
) -> None:
    BatteryTrayApp(
        check_seconds=check_seconds,
        retry_seconds=retry_seconds,
        timeout_ms=timeout_ms,
        listen_ms=listen_ms,
    ).run()
