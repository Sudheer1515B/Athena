from __future__ import annotations

import tempfile
import unittest
import csv
import io
from pathlib import Path

from fastapi.testclient import TestClient

from backend.history import HistoryRecorder
from backend.app import history_bounds
import backend.app as app_module
from backend.storage import open_database


def bench_snapshot(*, state: str, cycle: int, cycles: int,
                   run_s: int) -> dict:
    return {
        "connection": {"state": "CONNECTED", "transport": "SIMULATOR",
                       "port": "127.0.0.1:3333",
                       "bench": {"proto": "1", "team": "SIM", "ch": "4",
                                 "maxframes": "8000", "up": "10"}},
        "bench_state": {"state": state, "cycle": str(cycle),
                        "frame": "0", "us": "1600,1600,1600,1600"},
        "counters": {"cycles": str(cycles), "run_s": str(run_s),
                     "active_s": ",".join([str(run_s)] * 4)},
        "profile": {"id": None},
        "trace": [{"sampled_at": f"2026-09-26T00:00:{run_s:02d}Z"}],
    }


class HistoryTests(unittest.TestCase):
    def test_history_csv_exports_session_and_events_with_utc_filter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_data_dir = app_module.DATA_DIR
            app_module.DATA_DIR = Path(directory)
            try:
                with TestClient(app_module.app) as client:
                    recorder = app_module.app.state.history
                    recorder.observe(bench_snapshot(state="STOPPED", cycle=0,
                                                    cycles=0, run_s=0))
                    recorder.observe(bench_snapshot(state="RUNNING", cycle=0,
                                                    cycles=0, run_s=0),
                                     action="start", target_cycles=1)
                    recorder.observe(bench_snapshot(state="STOPPED", cycle=1,
                                                    cycles=1, run_s=5))
                    response = client.get("/api/v1/history/export.csv")
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertIn("attachment;", response.headers["content-disposition"])
                    rows = list(csv.DictReader(io.StringIO(response.text)))
                    session = next(row for row in rows if row["record_type"] == "session")
                    self.assertEqual(session["cycles_delta"], "1")
                    self.assertEqual(session["run_seconds_delta"], "5")
                    self.assertEqual(session["active_seconds_delta_by_channel"], "[5, 5, 5, 5]")
                    self.assertTrue(any(row["record_type"] == "event" for row in rows))
                    empty = client.get("/api/v1/history/export.csv?from_date=2030-01-01")
                    self.assertEqual(len(list(csv.DictReader(io.StringIO(empty.text)))), 0)
            finally:
                app_module.DATA_DIR = old_data_dir

    def test_disconnect_marks_open_session_uncertain_until_observed_again(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = open_database(Path(directory) / "db.sqlite3")
            try:
                recorder = HistoryRecorder(database)
                recorder.observe(bench_snapshot(state="RUNNING", cycle=0,
                                                cycles=0, run_s=0),
                                 action="start", target_cycles=2)
                self.assertEqual(recorder.sessions(start_at="2030-01-01T00:00:00.000+00:00"), [])
                recorder.observe({"connection": {"state": "DISCONNECTED"}})
                self.assertEqual(recorder.sessions()[0]["status"], "UNCONFIRMED")
                recorder.observe(bench_snapshot(state="RUNNING", cycle=0,
                                                cycles=0, run_s=3))
                self.assertEqual(recorder.sessions()[0]["status"], "RUNNING")
                self.assertEqual([event["kind"] for event in recorder.events()[:2]],
                                 ["link_regained", "link_lost"])
            finally:
                database.close()

    def test_history_dates_are_utc_and_end_date_is_inclusive(self) -> None:
        start, end = history_bounds("2026-09-26", "2026-09-26")
        self.assertEqual(start, "2026-09-26T00:00:00.000+00:00")
        self.assertEqual(end, "2026-09-27T00:00:00.000+00:00")

    def test_completed_run_and_counter_reset_survive_database_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            database = open_database(path)
            recorder = HistoryRecorder(database)
            recorder.observe(bench_snapshot(state="STOPPED", cycle=0,
                                            cycles=0, run_s=0))
            recorder.observe(bench_snapshot(state="RUNNING", cycle=0,
                                            cycles=0, run_s=0),
                             action="start", target_cycles=1)
            recorder.observe(bench_snapshot(state="RUNNING", cycle=0,
                                            cycles=0, run_s=3))
            recorder.observe(bench_snapshot(state="STOPPED", cycle=1,
                                            cycles=1, run_s=5))
            session = recorder.sessions()[0]
            self.assertEqual(session["status"], "COMPLETED")
            self.assertEqual(session["delta"], {
                "cycles": 1, "run_s": 5, "active_s": [5, 5, 5, 5],
            })
            self.assertEqual([event["kind"] for event in recorder.events()],
                             ["cycle_target_reached", "cycle_complete", "start"])
            database.close()

            reopened = open_database(path)
            try:
                recorder = HistoryRecorder(reopened)
                self.assertEqual(recorder.sessions()[0]["delta"]["cycles"], 1)
                recorder.observe(bench_snapshot(state="STOPPED", cycle=0,
                                                cycles=0, run_s=0))
                self.assertEqual(reopened.execute(
                    "SELECT COUNT(*) FROM counter_epochs"
                ).fetchone()[0], 2)
                self.assertEqual(recorder.sessions()[0]["delta"]["cycles"], 1)
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
