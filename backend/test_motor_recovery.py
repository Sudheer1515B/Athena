from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.motor_replay import MotorReplay
from backend.test_motor_replay import Bench, profile


CONTEXT = {"max_us": 1100, "tcp": ["127.0.0.1", 3333, "SIM"],
           "capabilities": {"proto": "1", "team": "SIM", "ch": "4", "maxframes": "8000"},
           "profile_sha256": "hash"}


class MotorRecoveryTests(unittest.TestCase):
    def test_lost_partial_frame_is_durable_and_resumes_only_remaining_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "motor.json"
            motor, bench, canonical = MotorReplay(path), Bench(), profile()
            motor.reserve("profile", 2, frames_per_pass=2, rate_hz=50, requested_passes=1, context=CONTEXT)
            bench.lose_at = 10  # Initial four lows, first frame, part of second.
            motor.run(bench, canonical, 1)
            recovery = motor.recovery()
            self.assertEqual(recovery["acknowledged_frames"], 1)
            self.assertEqual(recovery["in_flight_frame"], 1)
            self.assertTrue(recovery["partial_frame_uncertain"])
            restored = MotorReplay(path)
            self.assertFalse(restored.active)
            self.assertEqual(restored.recovery()["acknowledged_frames"], 1)
            # Asking for low must not erase the interrupted profile.
            idle = Bench()
            restored.reserve(None, 0)
            restored.run(idle, None, 1)
            self.assertEqual(restored.recovery()["run_id"], recovery["run_id"])
            restored.reserve("profile", 2, frames_per_pass=2, rate_hz=50, requested_passes=1,
                context=CONTEXT, resume=recovery)
            resumed = Bench()
            restored.run(resumed, canonical, 1, start_frame=1)
            self.assertEqual(resumed.commands[4:-4], [f"SET {i} {value}" for i, value in enumerate(canonical["frames"][1])])
            self.assertEqual(restored.snapshot()["acknowledged_frames"], 2)
            self.assertTrue(restored.snapshot()["low_signal_confirmed"])
            self.assertIsNone(restored.recovery())

    def test_backend_crash_restores_approval_required_without_sending_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "motor.json"
            motor = MotorReplay(path)
            motor.reserve("profile", 2, frames_per_pass=2, rate_hz=50, requested_passes=1, context=CONTEXT)
            motor.update(acknowledged_frames=1, in_flight_frame=1)
            restored = MotorReplay(path)
            self.assertFalse(restored.active)
            self.assertEqual(restored.snapshot()["phase"], "INTERRUPTED")
            self.assertEqual(restored.recovery()["acknowledged_frames"], 1)
            self.assertFalse(restored.snapshot()["low_signal_confirmed"])

    def test_checkpoint_failure_still_requests_low_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            motor, bench = MotorReplay(Path(directory) / "motor.json"), Bench()
            motor.reserve("profile", 2, frames_per_pass=2, rate_hz=50, requested_passes=1, context=CONTEXT)
            with patch.object(motor.journal, "save", side_effect=OSError("disk full")):
                motor.run(bench, profile(), 1)
            self.assertEqual(motor.snapshot()["phase"], "FAILED")
            self.assertTrue(motor.snapshot()["low_signal_confirmed"])
            self.assertIn("disk full", motor.snapshot()["checkpoint_error"])
            self.assertEqual(bench.status["us"], "1000,1000,1000,1000")


if __name__ == "__main__":
    unittest.main()
