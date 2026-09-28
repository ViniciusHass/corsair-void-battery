import sys
import unittest
from unittest.mock import Mock, patch

from corsair_void_battery import startup


class StartupTests(unittest.TestCase):
    def test_startup_command_uses_pythonw_for_source_checkout(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            command = startup.startup_command()
        self.assertIn("pythonw.exe", command)
        self.assertIn("-m corsair_void_battery --tray", command)

    def test_startup_command_uses_executable_when_frozen(self) -> None:
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", r"C:\App\CorsairVoidBattery.exe"),
        ):
            command = startup.startup_command()
        self.assertIn("CorsairVoidBattery.exe", command)
        self.assertIn("--tray", command)

    def test_is_startup_enabled_reads_registry(self) -> None:
        key = Mock()
        key.__enter__ = Mock(return_value=key)
        key.__exit__ = Mock(return_value=None)
        with (
            patch("corsair_void_battery.startup.winreg.OpenKey", return_value=key) as open_key,
            patch("corsair_void_battery.startup.winreg.QueryValueEx", return_value=("command", 1)),
        ):
            self.assertTrue(startup.is_startup_enabled())
        open_key.assert_called_once()

        with patch(
            "corsair_void_battery.startup.winreg.OpenKey",
            side_effect=FileNotFoundError,
        ):
            self.assertFalse(startup.is_startup_enabled())

    def test_set_startup_enabled_writes_and_deletes_registry_value(self) -> None:
        key = Mock()
        key.__enter__ = Mock(return_value=key)
        key.__exit__ = Mock(return_value=None)
        with (
            patch("corsair_void_battery.startup.winreg.CreateKeyEx", return_value=key) as create_key,
            patch("corsair_void_battery.startup.winreg.SetValueEx") as set_value,
            patch("corsair_void_battery.startup.startup_command", return_value="command"),
        ):
            startup.set_startup_enabled(True)
        create_key.assert_called_once()
        set_value.assert_called_once()

        with (
            patch("corsair_void_battery.startup.winreg.OpenKey", return_value=key) as open_key,
            patch("corsair_void_battery.startup.winreg.DeleteValue") as delete_value,
        ):
            startup.set_startup_enabled(False)
        open_key.assert_called_once()
        delete_value.assert_called_once_with(key, startup.APP_NAME)

        with patch("corsair_void_battery.startup.winreg.OpenKey", side_effect=FileNotFoundError):
            startup.set_startup_enabled(False)


if __name__ == "__main__":
    unittest.main()
