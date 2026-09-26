import unittest
from backend.motor_monitoring import motor_monitoring


def live(widths="1000,1200,1300,1400", fresh=True):
    return {"connection": {"state": "CONNECTED"}, "observation": {"fresh": fresh, "age_s": .2},
            "bench_state": {"state": "STOPPED", "us": widths}}


class MotorMonitoringTests(unittest.TestCase):
    def test_without_receiver_only_bench_commands_are_known(self):
        result = motor_monitoring(live(), {"active": True}, None)
        self.assertTrue(result["command_fresh"])
        self.assertFalse(result["physical_motor_telemetry_available"])
        self.assertFalse(result["receiver_fresh"])
        self.assertEqual([channel["bench_reported_us"] for channel in result["channels"]], [1000, 1200, 1300, 1400])
        self.assertEqual([channel["bench_gpio"] for channel in result["channels"]], [25, 26, 27, 33])
        self.assertTrue(all(channel["physical_pwm_state"] == "UNKNOWN" and channel["motor_rpm"] is None for channel in result["channels"]))

    def test_current_low_does_not_reuse_historical_success(self):
        history = {"low_signal_confirmed": True, "phase": "COMPLETED"}
        self.assertTrue(motor_monitoring(live("1000,1000,1000,1000"), history, None)["current_all_low_reported"])
        self.assertFalse(motor_monitoring(live("1500,1500,1500,1500"), history, None)["current_all_low_reported"])
        self.assertIsNone(motor_monitoring(live(fresh=False), history, None)["current_all_low_reported"])

    def test_stale_bench_hides_widths_without_hiding_independent_receiver(self):
        receiver = {"fresh": True, "configured": True, "channels": [{"signal": True, "width_us": 1500, "period_us": 20000}] * 4}
        result = motor_monitoring(live(fresh=False), None, receiver)
        self.assertFalse(result["command_fresh"])
        self.assertIsNone(result["channels"][0]["bench_reported_us"])
        self.assertEqual(result["channels"][0]["measured_us"], 1500)

    def test_no_signal_and_stale_receiver_are_distinct(self):
        receiver = {"fresh": True, "configured": True, "channels": [{"signal": False, "width_us": None}] * 4}
        result = motor_monitoring(live(), None, receiver)
        self.assertEqual(result["channels"][0]["physical_pwm_state"], "NO_SIGNAL")
        receiver["fresh"] = False
        result = motor_monitoring(live(), None, receiver)
        self.assertEqual(result["channels"][0]["physical_pwm_state"], "UNKNOWN")

    def test_invalid_readback_never_becomes_low_or_invented_values(self):
        for raw in ("1000,1000", "0,1000,1000,1000", "x,1000,1000,1000", None):
            result = motor_monitoring(live(raw), None, None)
            self.assertFalse(result["command_fresh"])
            self.assertIsNone(result["current_all_low_reported"])
        result = motor_monitoring(live("800,1000,1000,1000"), None, None)
        self.assertEqual(result["channels"][0]["command_state"], "OUTSIDE_CONFIRMED_RANGE")


if __name__ == "__main__":
    unittest.main()
