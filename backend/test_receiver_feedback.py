import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.receiver import ReceiverMonitor, parse_measurement

LINE = "t=1000ms | OUT0 1500us/20000us #20 | OUT1 NO SIGNAL | OUT2 1700us/20000us #20 | OUT3 1900us/20000us #20"


class ReceiverFeedbackTests(unittest.TestCase):
    def test_missing_signal_is_not_an_invented_width(self):
        channels = parse_measurement(LINE)
        self.assertTrue(channels[0]["signal"])
        self.assertEqual(channels[0]["width_us"], 1500)
        self.assertFalse(channels[1]["signal"])
        self.assertIsNone(channels[1]["width_us"])
        with self.assertRaises(ValueError):
            parse_measurement("OK STATUS us=1500,1500,1500,1500")
        with self.assertRaises(ValueError):
            parse_measurement(LINE.replace("OUT2", "OUT1"))

    def test_receiver_stale_and_wire_loss_clear_current_readings(self):
        class Device:
            def readline(self):
                return LINE.encode()
        receiver = ReceiverMonitor()
        receiver.config = ("USB fake", None)
        receiver.serial = Device()
        receiver.poll()
        snapshot = receiver.snapshot()
        self.assertTrue(snapshot["fresh"])
        self.assertIsNone(snapshot["trace"][-1]["us"][1])
        receiver.last_received = time.monotonic() - 3
        snapshot = receiver.snapshot()
        self.assertFalse(snapshot["fresh"])
        self.assertIsNone(snapshot["channels"])
        self.assertEqual(snapshot["trace"], [])

    def test_bench_adapter_is_never_opened_as_receiver(self):
        receiver = ReceiverMonitor()
        bench = SimpleNamespace(device="bench", vid=0x10c4, pid=0xea60)
        with patch("serial.tools.list_ports.comports", return_value=[bench]), patch("serial.Serial") as serial:
            with self.assertRaises(ValueError):
                receiver.connect_usb()
            serial.assert_not_called()

