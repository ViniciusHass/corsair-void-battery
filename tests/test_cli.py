import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from corsair_void_battery.cli import _replace_status_line, _run_once, build_parser, main
from corsair_void_battery.models import BatteryReading, IcueResult, ProbeResult


def args(*values: str):
    return build_parser().parse_args(list(values))


class CliTests(unittest.TestCase):
    def test_run_once_icue_json_and_error(self) -> None:
        success = IcueResult(reading=BatteryReading(71, 71, "icue-sdk"), model="VOID V2")
        output = io.StringIO()
        with patch("corsair_void_battery.cli.read_icue_battery", return_value=success), redirect_stdout(output):
            code, status = _run_once(args("--icue", "--json"))
        self.assertEqual(code, 0)
        self.assertIn('"percent": 71', output.getvalue())
        self.assertIn("iCUE", status)

        failure = IcueResult(error="SDK unavailable")
        output = io.StringIO()
        with patch("corsair_void_battery.cli.read_icue_battery", return_value=failure), redirect_stdout(output):
            code, status = _run_once(args("--icue", "--diagnostic"))
        self.assertEqual(code, 1)
        self.assertIn("SDK unavailable", output.getvalue())
        self.assertIn("SDK unavailable", status)

    def test_run_once_hid_json_diagnostic_and_errors(self) -> None:
        device = {"path": b"hid-path", "product_id": 0x2A08}
        success = ProbeResult("hid-path", 0x2A08, 4, 0xFF42, 1, [], [], battery_raw=800, battery_percent=80)
        with (
            patch("corsair_void_battery.cli.enumerate_devices", return_value=[device]),
            patch("corsair_void_battery.cli.is_v2_candidate", return_value=True),
            patch("corsair_void_battery.cli.probe_v2", return_value=success),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                code, status = _run_once(args("--json"))
            self.assertEqual(code, 0)
            self.assertIn('"battery_percent": 80', output.getvalue())
            self.assertIn("80%", status)

            output = io.StringIO()
            with redirect_stdout(output):
                code, _ = _run_once(args("--diagnostic"))
            self.assertEqual(code, 0)
            self.assertIn("Found 1 Corsair HID interface", output.getvalue())

        with patch("corsair_void_battery.cli.enumerate_devices", return_value=[]):
            code, status = _run_once(args())
        self.assertEqual(code, 1)
        self.assertIn("not found", status)

        failed = ProbeResult("hid-path", 0x2A08, 4, 0xFF42, 1, [], [], error="no response")
        with (
            patch("corsair_void_battery.cli.enumerate_devices", return_value=[device]),
            patch("corsair_void_battery.cli.is_v2_candidate", return_value=True),
            patch("corsair_void_battery.cli.probe_v2", return_value=failed),
        ):
            code, status = _run_once(args())
        self.assertEqual(code, 1)
        self.assertIn("no response", status)

    def test_probe_all_includes_non_candidate_interfaces(self) -> None:
        device = {"path": b"other"}
        result = ProbeResult("other", None, None, None, None, [], [], error="unsupported")
        with (
            patch("corsair_void_battery.cli.enumerate_devices", return_value=[device]),
            patch("corsair_void_battery.cli.is_v2_candidate", return_value=False),
            patch("corsair_void_battery.cli.probe_v2", return_value=result) as probe,
        ):
            code, _ = _run_once(args("--probe-all"))
        self.assertEqual(code, 1)
        probe.assert_called_once()

    def test_replace_status_line_erases_previous_text(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            width = _replace_status_line("long status", 0)
            new_width = _replace_status_line("short", width)
        self.assertEqual(width, 11)
        self.assertEqual(new_width, 5)
        self.assertIn("short      ", output.getvalue())

    def test_parser_accepts_monitoring_options(self) -> None:
        parsed = args("--timeout", "10", "--listen-ms", "20", "--watch", "30", "--retry-seconds", "40", "--once")
        self.assertEqual((parsed.timeout, parsed.listen_ms, parsed.watch, parsed.retry_seconds), (10, 20, 30, 40))

    def test_main_build_startup_tray_and_validation(self) -> None:
        output = io.StringIO()
        with (
            patch("corsair_void_battery.build.build_tray_executable", return_value=Path("dist/app.exe")),
            redirect_stdout(output),
        ):
            main(["--build-executable"])
        self.assertIn("Built tray executable", output.getvalue())

        with (
            patch(
                "corsair_void_battery.build.build_tray_executable",
                side_effect=ModuleNotFoundError("PyInstaller", name="PyInstaller"),
            ),
            redirect_stderr(io.StringIO()) as error,
            self.assertRaises(SystemExit) as raised,
        ):
            main(["--build-executable"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("PyInstaller is not installed", error.getvalue())

        with patch("corsair_void_battery.startup.set_startup_enabled") as set_startup:
            main(["--install-startup"])
            main(["--remove-startup"])
        self.assertEqual(set_startup.call_args_list[0].args, (True,))
        self.assertEqual(set_startup.call_args_list[1].args, (False,))

        with self.assertRaises(SystemExit) as raised:
            main(["--timeout", "0"])
        self.assertEqual(raised.exception.code, 2)

        with patch("corsair_void_battery.tray.run_tray") as run_tray:
            main(["--tray", "--watch", "2", "--retry-seconds", "3"])
        run_tray.assert_called_once_with(check_seconds=2, retry_seconds=3, timeout_ms=250, listen_ms=1000)

    def test_main_once_and_keyboard_interrupt(self) -> None:
        with patch("corsair_void_battery.cli._run_once", return_value=(0, "ok")), self.assertRaises(SystemExit) as raised:
            main(["--once"])
        self.assertEqual(raised.exception.code, 0)

        with (
            patch("corsair_void_battery.cli._run_once", return_value=(0, "ok")),
            patch("corsair_void_battery.cli.time.sleep", side_effect=KeyboardInterrupt),
            self.assertRaises(SystemExit) as raised,
        ):
            main([])
        self.assertEqual(raised.exception.code, 130)


if __name__ == "__main__":
    unittest.main()
