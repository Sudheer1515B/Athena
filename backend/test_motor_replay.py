import threading
import time
import unittest

from backend.bench_usb import BenchError
from backend.motor_replay import MotorReplay
from backend.profiles import compile_profile, inspect_csv, ProfileIssue


def profile():
    return {"channel_count": 4, "rate_hz": 50,
            "mapping": [{"output": i, "source": f"C{i+1}"} for i in range(4)],
            "frames": [[1020, 1040, 1060, 1080], [1080, 1060, 1040, 1020]]}


class Bench:
    def __init__(self):
        self.connected = True
        self.info = {"ch": "4"}
        self.status = {"state": "STOPPED", "us": "1500,1500,1500,1500"}
        self.commands = []
        self.delay = 0
        self.lose_at = None

    def refresh(self):
        pass

    def command(self, command):
        self.commands.append(command)
        if len(self.commands) == self.lose_at:
            self.connected = False
            raise BenchError("Lost acknowledgement")
        time.sleep(self.delay)
        _, channel, width = command.split()
        widths = self.status["us"].split(",")
        widths[int(channel)] = width
        self.status["us"] = ",".join(widths)
        return "OK"


class MotorTests(unittest.TestCase):
    def test_compile_supports_mapped_low_throttle_limits_without_clipping(self):
        flight = inspect_csv(b"TimeUS,C1,C2,C3,C4\n0,1020,1040,1060,1080\n100000,1080,1060,1040,1020\n")
        mapping = [{"output": i, "source": f"C{i+1}", "min_us": 1000, "max_us": 1100} for i in range(4)]
        canonical, summary = compile_profile(flight, "hash", start_us=0, end_us=100000,
            rate_hz=50, channel_count=4, maxframes=8000, mapping=mapping)
        self.assertEqual(canonical["frames"][0], [1020, 1040, 1060, 1080])
        self.assertEqual(canonical["compiler_version"], 2)
        MotorReplay.validate(canonical, summary["sum16"], 1100)
        mapping[3]["source"] = None
        with self.assertRaisesRegex(ProfileIssue, "Unmapped"):
            compile_profile(flight, "hash", start_us=0, end_us=100000,
                rate_hz=50, channel_count=4, maxframes=8000, mapping=mapping)

    def test_full_profile_validation_rejects_unmapped_and_excess_throttle(self):
        canonical = profile()
        checksum = sum(map(sum, canonical["frames"])) % 65536
        MotorReplay.validate(canonical, checksum, 1100)
        with self.assertRaisesRegex(BenchError, "outside"):
            MotorReplay.validate(canonical, checksum, 1050)
        canonical["mapping"][3]["source"] = None
        with self.assertRaisesRegex(BenchError, "Map all four"):
            MotorReplay.validate(canonical, checksum, 1100)

    def test_complete_replay_sends_exact_frames_and_returns_low_without_stop(self):
        motor, bench, canonical = MotorReplay(), Bench(), profile()
        motor.reserve("profile", 4)
        motor.run(bench, canonical, 2)
        state = motor.snapshot()
        self.assertEqual(state["phase"], "COMPLETED")
        self.assertEqual(state["acknowledged_frames"], 4)
        self.assertTrue(state["low_signal_confirmed"])
        self.assertFalse(state["bench_counters_track_this_run"])
        self.assertEqual(bench.commands[4:-4], [f"SET {i} {width}" for frame in canonical["frames"] * 2 for i, width in enumerate(frame)])
        self.assertTrue(all(command.startswith("SET ") for command in bench.commands))

    def test_cancel_returns_all_outputs_low(self):
        motor, bench = MotorReplay(), Bench()
        motor.reserve("profile", 200)
        thread = threading.Thread(target=motor.run, args=(bench, profile(), 100))
        thread.start()
        time.sleep(.03)
        motor.cancel()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(motor.snapshot()["phase"], "CANCELLED")
        self.assertTrue(motor.snapshot()["low_signal_confirmed"])

    def test_lost_reply_never_retries_or_claims_idle(self):
        motor, bench = MotorReplay(), Bench()
        bench.lose_at = 6
        motor.reserve("profile", 2)
        motor.run(bench, profile(), 1)
        self.assertEqual(len(bench.commands), 6)
        self.assertEqual(motor.snapshot()["phase"], "FAILED")
        self.assertFalse(motor.snapshot()["low_signal_confirmed"])
        self.assertIn("disconnect motor power", motor.snapshot()["error"])

    def test_timing_failure_aborts_and_returns_low(self):
        motor, bench = MotorReplay(), Bench()
        bench.delay = .04
        motor.reserve("profile", 2)
        motor.run(bench, profile(), 1)
        self.assertEqual(motor.snapshot()["phase"], "FAILED")
        self.assertIn("timing", motor.snapshot()["error"])
        self.assertEqual(motor.snapshot()["acknowledged_frames"], 1)
        self.assertTrue(motor.snapshot()["low_signal_confirmed"])

    def test_running_preflight_does_not_change_any_output(self):
        motor, bench = MotorReplay(), Bench()
        bench.status["state"] = "RUNNING"
        motor.reserve("profile", 2)
        motor.run(bench, profile(), 1)
        self.assertEqual(bench.commands, [])
        self.assertEqual(motor.snapshot()["phase"], "FAILED")


if __name__ == "__main__":
    unittest.main()
