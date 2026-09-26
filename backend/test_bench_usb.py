"""Protocol-level checks for the USB prototype without moving hardware."""

from __future__ import annotations

import unittest

from backend.bench_usb import BenchError, TcpBench, UsbBench


class FakeSerial:
    def __init__(self) -> None:
        self.is_open = True
        self.pending = bytearray()
        self.commands: list[str] = []
        self.status_state = "STOPPED"
        self.cleared = False
        self.team = "WDR_REFERENCE"

    def write(self, data: bytes) -> None:
        command = data.decode("ascii").strip()
        self.commands.append(command)
        if command == "PING":
            response = b"boot noise \xff OK PONG\n"
        elif command == "INFO":
            response = f"OK INFO proto=1 team={self.team} ch=4 maxframes=8000 up=100\n".encode()
        elif command == "STATUS":
            response = (f"OK STATUS state={self.status_state} cycle=0 target=0 frame=0 "
                        "frames=2 us=1500,1500,1500,1500\n").encode()
        elif command == "COUNTERS":
            response = (b"OK COUNTERS cycles=0 run_s=0 active_s=0,0,0,0\n"
                        if self.cleared else
                        b"OK COUNTERS cycles=21 run_s=24 active_s=23,23,23,6\n")
        elif command == "CLEAR":
            self.cleared = True
            response = b"OK\n"
        elif command == "START 1":
            response = b"OK\nEVT CYCLE 1\nEVT DONE\n"
        elif command == "COMMIT":
            response = b"OK SUM=12000\n"
        else:
            response = b"OK\n"
        self.pending.extend(response)

    def flush(self) -> None:
        pass

    def read(self, amount: int) -> bytes:
        if not self.pending:
            return b""
        result = bytes(self.pending[:amount])
        del self.pending[:amount]
        return result

    def close(self) -> None:
        self.is_open = False


class UsbBenchTests(unittest.TestCase):
    def test_upload_progress_stays_readable_while_transport_is_busy(self):
        import threading
        device = UsbBench()
        transport = FakeSerial()
        device._serial = transport
        ready, release = threading.Event(), threading.Event()
        original = device.command
        def delayed(value):
            if value == "COMMIT":
                ready.set()
                release.wait(2)
            return original(value)
        device.command = delayed
        errors = []
        def upload():
            try:
                device.upload("profile", {"channel_count": 4, "rate_hz": 50,
                              "frames": [[1500] * 4] * 2}, 12000)
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=upload)
        thread.start()
        try:
            self.assertTrue(ready.wait(1))
            progress = device.upload_progress()
            self.assertEqual(progress["acknowledged_frames"], 2)
            self.assertEqual(progress["phase"], "VERIFYING")
            self.assertFalse(progress["checksum_confirmed"])
        finally:
            release.set()
            thread.join(2)
        self.assertFalse(errors)
        self.assertEqual(device.upload_progress()["phase"], "COMPLETED")
        self.assertTrue(device.upload_progress()["checksum_confirmed"])

    def test_upload_verifies_checksum_and_one_finite_cycle(self) -> None:
        device = UsbBench()
        transport = FakeSerial()
        device._serial = transport
        device.port = "fake"
        self.assertEqual(device.command("PING"), "OK PONG")
        profile = {"channel_count": 4, "rate_hz": 50,
                   "frames": [[1500] * 4, [1500] * 4]}
        snapshot = device.upload("profile-1", profile, 12000)
        self.assertEqual(snapshot["profile"], {"id": "profile-1"})
        self.assertEqual(transport.commands[4:9], [
            "STOP", "LOAD 50 2", "F 0 1500 1500 1500 1500",
            "F 1 1500 1500 1500 1500", "COMMIT",
        ])
        self.assertEqual(device.control("start", 1)["counters"]["cycles"], "21")
        self.assertIn("START 1", transport.commands)
        self.assertIn("EVT DONE", device.snapshot()["recent_events"])

    def test_bad_profile_never_replaces_existing_profile(self) -> None:
        device = UsbBench()
        transport = FakeSerial()
        device._serial = transport
        device.port = "fake"
        device.profile_id = "existing"
        with self.assertRaisesRegex(BenchError, "checksum"):
            device.upload("bad", {"channel_count": 4, "rate_hz": 50,
                                  "frames": [[1500] * 4]}, 1)
        self.assertEqual(device.profile_id, "existing")
        self.assertNotIn("LOAD 50 1", transport.commands)

    def test_manual_set_requires_stopped_and_time_sync_is_acknowledged(self) -> None:
        device = UsbBench()
        transport = FakeSerial()
        device._serial = transport
        device.port = "fake"
        device.refresh()
        device.set_pulse(2, 1700)
        self.assertIn("SET 2 1700", transport.commands)
        device.sync_time()
        self.assertEqual(device.snapshot()["time_sync"]["status"], "ACKNOWLEDGED")
        self.assertTrue(any(command.startswith("TIME ") for command in transport.commands))
        transport.status_state = "RUNNING"
        with self.assertRaisesRegex(BenchError, "stopped"):
            device.set_pulse(2, 1700)

    def test_counter_reset_is_simulator_only(self) -> None:
        device = UsbBench()
        transport = FakeSerial()
        device._serial = transport
        device.port = "fake"
        with self.assertRaisesRegex(BenchError, "physical benches"):
            device.clear_simulator_counters()
        self.assertNotIn("CLEAR", transport.commands)
        simulator = TcpBench(expected_team="SIM")
        transport.team = "SIM"
        simulator._serial = transport
        simulator.port = "127.0.0.1:3333"
        self.assertEqual(simulator.clear_simulator_counters()["counters"]["cycles"], "0")
        self.assertIn("CLEAR", transport.commands)


if __name__ == "__main__":
    unittest.main()
