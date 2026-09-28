import io
import unittest
from contextlib import redirect_stdout

from corsair_void_battery.formatting import (
    battery_bar,
    battery_status,
    hex_value,
    path_text,
    print_icue_result,
    print_inventory,
    print_probe,
    report_text,
)
from corsair_void_battery.models import BatteryReading, IcueResult, ProbeResult


def probe_result(**overrides: object) -> ProbeResult:
    values: dict[str, object] = {
        "path": "hid-path",
        "product_id": 0x2A08,
        "interface_number": 4,
        "usage_page": 0xFF42,
        "usage": 1,
        "v2_reports": [],
        "report_sources": [],
    }
    values.update(overrides)
    return ProbeResult(**values)


class FormattingTests(unittest.TestCase):
    def test_scalar_formatters(self) -> None:
        self.assertEqual(hex_value(None), "-")
        self.assertEqual(hex_value(0x2A08), "0x2A08")
        self.assertEqual(path_text(b"device"), "device")
        self.assertEqual(path_text("device"), "device")
        self.assertEqual(report_text(None), "<no report>")
        self.assertEqual(report_text([]), "<no report>")
        self.assertEqual(report_text(bytes([0x01, 0xAF])), "01 AF")

    def test_battery_bar_clamps_values(self) -> None:
        self.assertEqual(battery_bar(-10, width=4), "[----]   0%")
        self.assertEqual(battery_bar(101, width=4), "[####] 100%")
        self.assertEqual(battery_status(42, "test"), "Corsair VOID Wireless V2 [########------------]  42% (test)")

    def test_inventory_output(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            print_inventory([])
        self.assertIn("No Corsair HID interfaces found.", output.getvalue())

        device = {
            "product_string": "Receiver",
            "vendor_id": 0x1B1C,
            "product_id": 0x2A08,
            "interface_number": 4,
            "usage_page": 0xFF42,
            "usage": 1,
            "serial_number": "serial",
            "path": b"path",
        }
        output = io.StringIO()
        with redirect_stdout(output):
            print_inventory([device])
        text = output.getvalue()
        self.assertIn("Found 1 Corsair HID interface(s):", text)
        self.assertIn("Receiver", text)
        self.assertIn("0x1B1C:0x2A08", text)
        self.assertIn("path", text)

    def test_probe_output_variants(self) -> None:
        reading_result = probe_result(
            v2_reports=[[1, 2]],
            report_sources=["request"],
            battery_raw=750,
            battery_percent=75,
            battery_protocol="void-v2",
        )
        output = io.StringIO()
        with redirect_stdout(output):
            print_probe(reading_result, diagnostic=True)
            print_probe(reading_result)
        text = output.getvalue()
        self.assertIn("Probe PID=0x2A08", text)
        self.assertIn("report 1 (request): 01 02", text)
        self.assertIn("battery: 75%", text)
        self.assertIn("Corsair VOID Wireless V2 battery: 75%", text)

        error_result = probe_result(error="device disconnected")
        output = io.StringIO()
        with redirect_stdout(output):
            print_probe(error_result, diagnostic=True)
            print_probe(error_result)
        self.assertIn("device disconnected", output.getvalue())

        empty_result = probe_result()
        output = io.StringIO()
        with redirect_stdout(output):
            print_probe(empty_result, diagnostic=True)
            print_probe(empty_result)
        self.assertIn("no valid response", output.getvalue())

    def test_icue_output_variants(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            print_icue_result(
                IcueResult(
                    reading=BatteryReading(80, 80, "icue-sdk"),
                    model="VOID V2",
                )
            )
            print_icue_result(IcueResult(error="not connected"))
        self.assertIn("VOID V2 battery: 80%", output.getvalue())
        self.assertIn("not connected", output.getvalue())


if __name__ == "__main__":
    unittest.main()
