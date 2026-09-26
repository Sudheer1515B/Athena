from types import SimpleNamespace
from datetime import datetime, timezone
import tempfile
import time
import unittest
from pathlib import Path

from backend.history import HistoryRecorder
from backend.monitor import BenchMonitor
from backend.storage import open_database


class AdvancingBench:
    def __init__(self):
        self.connected = True
        self.reads = 0
        self.sampled_at = datetime.now(timezone.utc).isoformat()

    def refresh(self):
        self.reads += 1
        self.sampled_at = datetime.now(timezone.utc).isoformat()
        return self.snapshot()

    def disconnect(self):
        self.connected = False

    def snapshot(self):
        done = self.reads >= 2
        return {
            "connection": {"state": "CONNECTED" if self.connected else "DISCONNECTED",
                           "transport": "SIMULATOR", "port": "127.0.0.1:3333",
                           "bench": {"proto": "1", "team": "SIM", "ch": "4", "maxframes": "8000", "up": "10"}},
            "bench_state": {"state": "STOPPED" if done else "RUNNING", "cycle": "1" if done else "0", "frame": "0", "frames": "100", "us": "1500,1500,1500,1500"},
            "counters": {"cycles": "1" if done else "0", "run_s": str(min(self.reads, 2)), "active_s": ",".join([str(min(self.reads, 2))] * 4)},
            "profile": None, "trace": [{"sampled_at": self.sampled_at}],
        }


class MonitorTests(unittest.TestCase):
    def test_reconnect_rejects_changed_capabilities_without_mutating_bench(self):
        with tempfile.TemporaryDirectory() as directory:
            database = open_database(Path(directory) / "history.sqlite3")
            original = AdvancingBench()
            recorder = HistoryRecorder(database)
            state = SimpleNamespace(database=database, bench=original, history=recorder,
                                    desired_tcp=("127.0.0.1", 3333, "SIM"), reconnect_after=0)
            replacement = AdvancingBench()
            normal = replacement.snapshot
            def changed():
                live = normal()
                live["connection"]["bench"]["maxframes"] = "4000"
                return live
            replacement.snapshot = changed
            replacement.connect = lambda host, port: None
            monitor = BenchMonitor(state, lambda **kwargs: replacement)
            monitor.pin_identity()
            monitor.capture()
            original.disconnect()
            monitor.tick()
            self.assertFalse(replacement.connected)
            self.assertIn("capabilities changed", monitor.blocked_reason)
            self.assertTrue(any(e["kind"] == "identity_mismatch" for e in recorder.events()))
            database.close()

    def test_reboot_closes_affected_session_with_uncertain_time(self):
        with tempfile.TemporaryDirectory() as directory:
            database = open_database(Path(directory) / "history.sqlite3")
            original = AdvancingBench()
            recorder = HistoryRecorder(database)
            recorder.observe(original.snapshot(), action="start", target_cycles=1)
            state = SimpleNamespace(database=database, bench=original, history=recorder,
                                    desired_tcp=("127.0.0.1", 3333, "SIM"), reconnect_after=0)
            replacement = AdvancingBench()
            replacement.reads = 2
            normal = replacement.snapshot
            def rebooted():
                live = normal()
                live["connection"]["bench"]["up"] = "0"
                return live
            replacement.snapshot = rebooted
            replacement.connect = lambda host, port: None
            monitor = BenchMonitor(state, lambda **kwargs: replacement)
            monitor.pin_identity()
            monitor.capture()
            original.disconnect()
            monitor.tick()
            session = recorder.sessions()[0]
            self.assertEqual(session["status"], "REBOOT_OBSERVED")
            self.assertEqual(session["identity_confidence"], "uncertain")
            self.assertIn("reboot observed", monitor.snapshot()["observation"]["recovery_warning"])
            database.close()

    def test_retry_delay_is_capped_and_explicit_disconnect_disables_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            database = open_database(Path(directory) / "history.sqlite3")
            bench = AdvancingBench()
            bench.connected = False
            state = SimpleNamespace(database=database, bench=bench,
                                    history=HistoryRecorder(database), desired_tcp=None, reconnect_after=0)
            monitor = BenchMonitor(state, None)
            for _ in range(20):
                monitor.schedule_retry()
                self.assertLessEqual(state.reconnect_after - time.monotonic(), 10)
            monitor.tick()  # No target: must never attempt a connection.
            self.assertFalse(state.bench.connected)
            database.close()

    def test_background_records_completion_without_browser_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            database = open_database(Path(directory) / "history.sqlite3")
            bench = AdvancingBench()
            recorder = HistoryRecorder(database)
            recorder.observe(bench.snapshot(), action="start", target_cycles=1)
            state = SimpleNamespace(database=database, bench=bench, history=recorder,
                                    desired_tcp=None, reconnect_after=0)
            monitor = BenchMonitor(state, None, interval_s=.02)
            monitor.start()
            try:
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    sessions = recorder.sessions()
                    if sessions[0]["status"] == "COMPLETED":
                        break
                    time.sleep(.01)
                self.assertEqual(sessions[0]["status"], "COMPLETED")
                self.assertEqual(sessions[0]["delta"]["cycles"], 1)
                self.assertEqual(sessions[0]["delta"]["run_s"], 2)
                before_reads = bench.reads
                for _ in range(20):
                    monitor.snapshot()
                self.assertLessEqual(bench.reads - before_reads, 1)
            finally:
                monitor.stop()
                self.assertFalse(monitor._thread.is_alive())
                database.close()

    def test_snapshot_does_not_wait_for_bench_io(self):
        with tempfile.TemporaryDirectory() as directory:
            database = open_database(Path(directory) / "history.sqlite3")
            state = SimpleNamespace(database=database, bench=AdvancingBench(),
                                    history=HistoryRecorder(database), desired_tcp=None, reconnect_after=0)
            monitor = BenchMonitor(state, None)
            import threading
            ready, release = threading.Event(), threading.Event()
            def hold():
                with monitor.operation():
                    ready.set()
                    release.wait(2)
            thread = threading.Thread(target=hold)
            thread.start()
            self.assertTrue(ready.wait(1))
            started = time.monotonic()
            monitor.snapshot()
            self.assertLess(time.monotonic() - started, .1)
            release.set()
            thread.join(2)
            database.close()


if __name__ == "__main__":
    unittest.main()
