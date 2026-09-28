import json
import unittest
from unittest.mock import Mock, patch

from corsair_void_battery.icue import coerce_battery_percent, read_icue_battery


class IcueTests(unittest.TestCase):
    def test_coerce_rejects_invalid_values(self) -> None:
        for value in (True, False, "80", -1, 101, None):
            self.assertIsNone(coerce_battery_percent(value))

    def test_read_reports_missing_optional_sdk(self) -> None:
        with patch("corsair_void_battery.icue.importlib.util.find_spec", return_value=None):
            result = read_icue_battery()
        self.assertIn("not installed", result.error or "")

    def test_read_reports_worker_timeout(self) -> None:
        with (
            patch("corsair_void_battery.icue.importlib.util.find_spec", return_value=Mock()),
            patch(
                "corsair_void_battery.icue.subprocess.run",
                side_effect=__import__("subprocess").TimeoutExpired("worker", 7),
            ),
        ):
            result = read_icue_battery()
        self.assertEqual(result.error, "iCUE SDK worker timed out")

    def test_read_reports_worker_exit_code(self) -> None:
        completed = Mock(returncode=-1073741795, stdout="", stderr="")
        with (
            patch("corsair_void_battery.icue.importlib.util.find_spec", return_value=Mock()),
            patch("corsair_void_battery.icue.subprocess.run", return_value=completed),
        ):
            result = read_icue_battery()
        self.assertIn("use direct HID mode", result.error or "")
        self.assertIn("0xC000001D", result.error or "")

    def test_read_parses_worker_response(self) -> None:
        payload = {
            "reading": {"percent": 82, "raw": 82, "protocol": "icue-sdk"},
            "model": "VOID V2",
            "device_id": "device",
        }
        completed = Mock(returncode=0, stdout=json.dumps(payload), stderr="")
        with (
            patch("corsair_void_battery.icue.importlib.util.find_spec", return_value=Mock()),
            patch("corsair_void_battery.icue.subprocess.run", return_value=completed),
        ):
            result = read_icue_battery()
        self.assertEqual(result.reading.percent, 82)
        self.assertEqual(result.model, "VOID V2")
        self.assertEqual(result.device_id, "device")

    def test_read_rejects_invalid_worker_response(self) -> None:
        for stdout in ("not json", json.dumps({"reading": "invalid"})):
            completed = Mock(returncode=0, stdout=stdout, stderr="")
            with (
                patch("corsair_void_battery.icue.importlib.util.find_spec", return_value=Mock()),
                patch("corsair_void_battery.icue.subprocess.run", return_value=completed),
            ):
                result = read_icue_battery()
            self.assertIn("invalid iCUE SDK worker response", result.error or "")


if __name__ == "__main__":
    unittest.main()
