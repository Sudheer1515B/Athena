"""Protocol-level checks for the USB prototype without moving hardware."""

from __future__ import annotations

import unittest

from backend.bench_usb import BenchError, UsbBench


class FakeSerial:
    def __init__(self) -> None:
        self.is_open = True
        self.pending = bytearray()
        self.commands: list[str] = []

    def write(self, data: bytes) -> None:
        command = data.decode("ascii").strip()
        self.commands.append(command)
        if command == "PING":
            response = b"boot noise \xff OK PONG\n"
        elif command == "INFO":
            response = b"OK INFO proto=1 team=WDR_REFERENCE ch=4 maxframes=8000 up=100\n"
        elif command == "STATUS":
            response = b"OK STATUS state=STOPPED cycle=0 target=0 frame=0 frames=2 us=1500,1500,1500,1500\n"
        elif command == "COUNTERS":
            response = b"OK COUNTERS cycles=21 run_s=24 active_s=23,23,23,6\n"
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


if __name__ == "__main__":
    unittest.main()
