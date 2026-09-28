import threading
import unittest
from unittest.mock import Mock, patch

from corsair_void_battery.models import ProbeResult
from corsair_void_battery.tray import BatteryTrayApp, _battery_color, create_battery_icon


class TrayTests(unittest.TestCase):
    def test_battery_colors(self) -> None:
        self.assertEqual(_battery_color(80), (46, 204, 113, 255))
        self.assertEqual(_battery_color(40), (241, 196, 15, 255))
        self.assertEqual(_battery_color(10), (231, 76, 60, 255))
        self.assertEqual(create_battery_icon(10).size, (64, 64))

    def make_app(self) -> BatteryTrayApp:
        app = BatteryTrayApp.__new__(BatteryTrayApp)
        app.check_seconds = 60
        app.retry_seconds = 600
        app.timeout_ms = 100
        app.listen_ms = 0
        app.status = "initial"
        app.stop_event = threading.Event()
        app.refresh_event = threading.Event()
        app.icon = Mock()
        return app

    def test_read_battery_success_and_failures(self) -> None:
        app = self.make_app()
        success = ProbeResult("path", 0x2A08, 4, 0xFF42, 1, [], [], battery_percent=75)
        with (
            patch("corsair_void_battery.tray.enumerate_devices", return_value=[{"path": "path"}]),
            patch("corsair_void_battery.tray.is_v2_candidate", return_value=True),
            patch("corsair_void_battery.tray.probe_v2", return_value=success),
        ):
            self.assertEqual(app._read_battery(), (75, "Corsair VOID Wireless V2: 75%"))

        with patch("corsair_void_battery.tray.enumerate_devices", return_value=[]):
            self.assertIn("disconnected", app._read_battery()[1])

        failed = ProbeResult("path", 0x2A08, 4, 0xFF42, 1, [], [], error="no response")
        with (
            patch("corsair_void_battery.tray.enumerate_devices", return_value=[{"path": "path"}]),
            patch("corsair_void_battery.tray.is_v2_candidate", return_value=True),
            patch("corsair_void_battery.tray.probe_v2", return_value=failed),
        ):
            self.assertIn("no response", app._read_battery()[1])

        with (
            patch("corsair_void_battery.tray.enumerate_devices", return_value=[{"path": "path"}]),
            patch("corsair_void_battery.tray.is_v2_candidate", return_value=True),
            patch("corsair_void_battery.tray.probe_v2", return_value=ProbeResult("path", 1, 1, 1, 1, [], [])),
        ):
            self.assertIn("headset unavailable", app._read_battery()[1])

        with patch("corsair_void_battery.tray.enumerate_devices", side_effect=OSError("USB error")):
            self.assertIn("USB error", app._read_battery()[1])

    def test_status_refresh_startup_and_exit_actions(self) -> None:
        app = self.make_app()
        app._set_status("Battery: 50%", 50)
        self.assertEqual(app.status, "Battery: 50%")
        app.icon.update_menu.assert_called()
        app._refresh(app.icon, Mock())
        self.assertTrue(app.refresh_event.is_set())

        with (
            patch("corsair_void_battery.tray.is_startup_enabled", return_value=False),
            patch("corsair_void_battery.tray.set_startup_enabled") as set_startup,
        ):
            app._toggle_startup(app.icon, Mock())
        set_startup.assert_called_once_with(True)

        app._exit(app.icon, Mock())
        self.assertTrue(app.stop_event.is_set())
        app.icon.stop.assert_called_once_with()

    def test_monitor_uses_retry_when_read_fails(self) -> None:
        app = self.make_app()
        app._read_battery = Mock(return_value=(None, "disconnected"))
        app._set_status = Mock()

        def stop_after_wait(delay: float) -> bool:
            self.assertEqual(delay, 600)
            app.stop_event.set()
            return True

        app.refresh_event.wait = stop_after_wait
        app._monitor()
        app._set_status.assert_called_once_with("disconnected", None)


if __name__ == "__main__":
    unittest.main()
