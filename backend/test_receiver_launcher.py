import io
from types import SimpleNamespace
import unittest

from scripts.monitor_receiver import monitor, select_receiver


class ReceiverLauncherTests(unittest.TestCase):
    def test_wrong_and_ambiguous_adapters_refused(self):
        bench = SimpleNamespace(device="COM1", vid=0x10c4, pid=0xea60)
        receiver = SimpleNamespace(device="COM3", vid=0x1a86, pid=0x7523)
        second = SimpleNamespace(device="COM4", vid=0x1a86, pid=0x7523)
        self.assertEqual(select_receiver([bench, receiver]), "COM3")
        self.assertEqual(select_receiver([receiver, second], "COM4"), "COM4")
        for ports, requested in [([bench], None), ([receiver, second], None), ([bench, receiver], "COM1")]:
            with self.assertRaises(ValueError):
                select_receiver(ports, requested)

    def test_no_data_is_distinguished_from_no_pwm(self):
        class Device:
            reads = 0
            def readline(self):
                self.reads += 1
                if self.reads == 1:
                    return b""
                if self.reads == 2:
                    return b"OUT0 NO SIGNAL\n"
                raise KeyboardInterrupt()
        messages = []
        capture = io.StringIO()
        clock = iter([0, 6, 7])
        with self.assertRaises(KeyboardInterrupt):
            monitor(Device(), capture, clock=lambda: next(clock), output=lambda text, **kw: messages.append(text))
        self.assertIn("No serial data", messages[0])
        self.assertEqual(messages[1], "OUT0 NO SIGNAL")
        self.assertIn("OUT0 NO SIGNAL", capture.getvalue())
