import unittest

from corsair_void_battery.cli import build_parser
from corsair_void_battery.formatting import battery_bar, battery_status
from corsair_void_battery.icue import coerce_battery_percent
from corsair_void_battery.protocol import build_packet, parse_battery_report
from corsair_void_battery.startup import startup_command
from corsair_void_battery.tray import create_battery_icon


class BatteryProtocolTests(unittest.TestCase):
    def test_icue_is_opt_in(self) -> None:
        default_args = build_parser().parse_args([])
        self.assertFalse(default_args.icue)
        self.assertFalse(default_args.once)
        self.assertFalse(default_args.tray)
        self.assertEqual(default_args.watch, 60)
        self.assertTrue(build_parser().parse_args(["--icue"]).icue)
        self.assertTrue(build_parser().parse_args(["--build-executable"]).build_executable)

    def test_battery_bar(self) -> None:
        self.assertEqual(battery_bar(0, width=10), "[----------]   0%")
        self.assertEqual(battery_bar(54, width=10), "[#####-----]  54%")
        self.assertEqual(battery_bar(100, width=10), "[##########] 100%")
        self.assertEqual(
            battery_status(54),
            "Corsair VOID Wireless V2 [###########---------]  54% (HID)",
        )

    def test_tray_icon_and_startup_command(self) -> None:
        self.assertEqual(create_battery_icon(54).size, (64, 64))
        self.assertEqual(create_battery_icon(None).size, (64, 64))
        command = startup_command()
        self.assertIn("pythonw.exe", command)
        self.assertIn("--tray", command)

    def test_icue_battery_value(self) -> None:
        self.assertEqual(coerce_battery_percent(73), 73)
        self.assertEqual(coerce_battery_percent(72.6), 73)
        self.assertIsNone(coerce_battery_percent(True))
        self.assertIsNone(coerce_battery_percent(101))

    def test_v2_battery_report(self) -> None:
        report = [0x01, 0x01, 0x02, 0x00, 0x58, 0x02]

        reading = parse_battery_report(report)

        self.assertIsNotNone(reading)
        assert reading is not None
        self.assertEqual(reading.percent, 60)
        self.assertEqual(reading.raw, 600)
        self.assertEqual(reading.protocol, "void-v2")

    def test_legacy_battery_report(self) -> None:
        report = [0x64, 0x00, 0x37, 0xB1, 0x01]

        reading = parse_battery_report(report)

        self.assertIsNotNone(reading)
        assert reading is not None
        self.assertEqual(reading.percent, 55)
        self.assertEqual(reading.protocol, "void-legacy")

    def test_heartbeat_is_not_battery(self) -> None:
        self.assertIsNone(parse_battery_report([0x01, 0x01, 0x12, 0x00, 0x00, 0x00]))

    def test_v2_battery_event(self) -> None:
        reading = parse_battery_report([0x03, 0x01, 0x00, 0x0F, 0x00, 0x58, 0x02])

        self.assertIsNotNone(reading)
        assert reading is not None
        self.assertEqual(reading.percent, 60)
        self.assertEqual(reading.protocol, "void-v2-event")

    def test_firmware_response_is_not_battery(self) -> None:
        self.assertIsNone(parse_battery_report([0x01, 0x01, 0x02, 0x00, 0x00, 0x11]))

    def test_v2_packet_matches_windows_report_size(self) -> None:
        packet = build_packet([0x02, 0x0F], endpoint=0x09)

        self.assertEqual(len(packet), 64)
        self.assertEqual(packet[:5], bytes([0x02, 0x09, 0x02, 0x0F, 0x00]))


if __name__ == "__main__":
    unittest.main()
