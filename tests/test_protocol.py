import unittest
from unittest.mock import Mock, patch

from corsair_void_battery.models import ProbeResult
from corsair_void_battery.protocol import (
    _flush,
    _read_until,
    _transact,
    _write,
    enumerate_devices,
    is_v2_candidate,
    probe_v2,
)


def base_device() -> dict[str, object]:
    return {
        "path": b"hid-path",
        "product_id": 0x2A08,
        "interface_number": 4,
        "usage_page": 0xFF42,
        "usage": 1,
    }


class ProtocolTests(unittest.TestCase):
    def test_enumeration_and_candidate_filter(self) -> None:
        with patch("corsair_void_battery.protocol.hid.enumerate", return_value=[base_device()]) as mocked:
            self.assertEqual(enumerate_devices(), [base_device()])
        mocked.assert_called_once_with(0x1B1C, 0)
        self.assertTrue(is_v2_candidate(base_device()))
        for key, value in (("product_id", 1), ("interface_number", 3), ("usage_page", 1), ("usage", 2)):
            device = base_device()
            device[key] = value
            self.assertFalse(is_v2_candidate(device))

    def test_flush_and_write(self) -> None:
        device = Mock()
        device.read.side_effect = [[1], []]
        _flush(device)
        self.assertEqual(device.read.call_count, 2)

        device.write.return_value = 64
        _write(device, b"packet")
        device.write.assert_called_once_with(b"packet")

        device.write.return_value = -1
        device.error.return_value = "write failed"
        with self.assertRaisesRegex(OSError, "write failed"):
            _write(device, b"packet")

    def test_read_until_collects_reports_until_deadline(self) -> None:
        device = Mock()
        device.read.return_value = [1, 2]
        with patch(
            "corsair_void_battery.protocol.time.monotonic",
            side_effect=[0.0, 0.05, 0.05, 0.06, 0.06, 0.11],
        ):
            reports = _read_until(device, timeout_ms=50, listen_ms=100)
        self.assertEqual(reports, [[1, 2], [1, 2]])
        self.assertEqual(device.read.call_count, 2)

    def test_transact_records_reports(self) -> None:
        device = Mock()
        result = ProbeResult("path", None, None, None, None, [], [])
        with (
            patch("corsair_void_battery.protocol._flush") as flush,
            patch("corsair_void_battery.protocol._write") as write,
            patch("corsair_void_battery.protocol._read_until", return_value=[[1, 2]]) as read,
        ):
            reports = _transact(device, result, "test", [2, 15], 9, 100)
        self.assertEqual(reports, [[1, 2]])
        self.assertEqual(result.v2_reports, [[1, 2]])
        self.assertEqual(result.report_sources, ["test"])
        flush.assert_called_once_with(device)
        write.assert_called_once()
        read.assert_called_once_with(device, 100, 100)

    def test_probe_success_restores_hardware_mode(self) -> None:
        device = Mock()
        device_factory = Mock(return_value=device)
        response = [1, 1, 2, 0, 0x58, 0x02]
        with (
            patch("corsair_void_battery.protocol.hid.device", device_factory),
            patch("corsair_void_battery.protocol._transact", side_effect=[[], [], [], [], [response], [], []]) as transact,
        ):
            result = probe_v2(base_device(), 100, 0)
        self.assertEqual(result.battery_percent, 60)
        self.assertEqual(result.battery_raw, 600)
        self.assertEqual(result.battery_protocol, "void-v2")
        device.open_path.assert_called_once_with(b"hid-path")
        device.set_nonblocking.assert_called_once_with(False)
        device.close.assert_called_once_with()
        self.assertEqual(transact.call_count, 7)

    def test_probe_handles_open_error(self) -> None:
        device = Mock()
        device.open_path.side_effect = OSError("disconnected")
        with patch("corsair_void_battery.protocol.hid.device", return_value=device):
            result = probe_v2(base_device(), 100, 0)
        self.assertEqual(result.error, "disconnected")
        device.close.assert_called_once_with()

    def test_probe_accepts_unsolicited_battery_event(self) -> None:
        device = Mock()
        event = [3, 1, 0, 0x0F, 0, 0x58, 0x02]
        with (
            patch("corsair_void_battery.protocol.hid.device", return_value=device),
            patch("corsair_void_battery.protocol._transact", return_value=[]),
            patch("corsair_void_battery.protocol._read_until", return_value=[event]),
        ):
            result = probe_v2(base_device(), 100, 10)
        self.assertEqual(result.battery_percent, 60)
        self.assertEqual(result.battery_protocol, "void-v2-event")


if __name__ == "__main__":
    unittest.main()
