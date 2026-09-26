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
