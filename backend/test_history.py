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
    def test_lost_start_reply_does_not_confirm_previous_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            database = open_database(Path(directory) / "db.sqlite3")
            recorder = HistoryRecorder(database)
            before = bench_snapshot(state="STOPPED", cycle=1, cycles=10, run_s=40)
            recorder.observe(before, action="start_requested", target_cycles=1)
            recorder.observe({"connection": {"state": "DISCONNECTED"}})
            before["trace"] = [{"sampled_at": "2026-09-26T00:01:00Z"}]
            recorder.observe(before)
            session = recorder.sessions()[0]
            self.assertEqual(session["status"], "COMMAND_UNCONFIRMED")
            self.assertEqual(session["delta"]["cycles"], 0)
            database.close()

    def test_lost_start_reply_can_reconcile_finished_run_without_another_start(self):
        with tempfile.TemporaryDirectory() as directory:
            database = open_database(Path(directory) / "db.sqlite3")
            recorder = HistoryRecorder(database)
            recorder.observe(bench_snapshot(state="STOPPED", cycle=0, cycles=10, run_s=40), action="start_requested", target_cycles=1)
            recorder.observe({"connection": {"state": "DISCONNECTED"}})
            recorder.observe(bench_snapshot(state="STOPPED", cycle=1, cycles=11, run_s=44))
            session = recorder.sessions()[0]
            self.assertEqual(session["status"], "COMPLETED")
            self.assertEqual(session["delta"]["cycles"], 1)
            self.assertTrue(session["has_link_gap"])
            self.assertEqual(session["identity_confidence"], "uncertain")
            self.assertTrue(any("exact stop time" in reason for reason in session["uncertainty_reasons"]))
            self.assertTrue(any(e["kind"] == "start_requested" for e in recorder.events()))
            database.close()

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

    def test_session_detail_uses_saved_profile_counters_and_link_gap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_data_dir = app_module.DATA_DIR
            app_module.DATA_DIR = Path(directory)
            try:
                with TestClient(app_module.app) as client:
                    with (Path(__file__).resolve().parent.parent / "RCOU.csv").open("rb") as stream:
                        source = client.post("/api/v1/sources", files={
                            "file": ("flight.csv", stream, "text/csv"),
                        }).json()
                    profile = client.post("/api/v1/profiles", json={
                        "source_id": source["id"], "start_us": 40_000_000,
                        "end_us": 44_000_000, "rate_hz": 50,
                        "channel_count": 4, "maxframes": 8000,
                        "mapping": [{"output": index, "source": f"C{index + 1}"}
                                    for index in range(4)],
                    }).json()
                    recorder = app_module.app.state.history

                    def observed(state: str, cycle: int, cycles: int, run_s: int) -> dict:
                        live = bench_snapshot(state=state, cycle=cycle,
                                              cycles=cycles, run_s=run_s)
                        live["profile"] = {"id": profile["id"]}
                        return live

                    recorder.observe(observed("RUNNING", 0, 0, 0),
                                     action="start", target_cycles=1)
                    session_id = recorder.sessions()[0]["id"]
                    first = client.get(f"/api/v1/history/sessions/{session_id}").json()
                    self.assertIsNone(first["delta"])
                    self.assertEqual(len(first["counter_observations"]), 1)
                    recorder.observe({"connection": {"state": "DISCONNECTED"}})
                    uncertain = client.get(f"/api/v1/history/sessions/{session_id}").json()
                    self.assertEqual(uncertain["status"], "UNCONFIRMED")
                    self.assertTrue(uncertain["has_link_gap"])
                    recorder.observe(observed("RUNNING", 0, 0, 3))
                    recorder.observe(observed("STOPPED", 1, 1, 4))
                    detail = client.get(f"/api/v1/history/sessions/{session_id}")
                    self.assertEqual(detail.status_code, 200)
                    body = detail.json()
                    self.assertEqual(body["profile_sha256"], profile["summary"]["sha256"])
                    self.assertEqual(body["source_name"], "flight.csv")
                    self.assertEqual(body["profile_settings"]["mapping"][0]["source"], "C1")
                    self.assertEqual(body["profile_sum16"], 16982)
                    self.assertEqual(body["target_cycles"], 1)
                    self.assertEqual(body["delta"]["active_s"], [4, 4, 4, 4])
                    self.assertEqual(body["stop_cause"], "Cycle target reached; stopped state observed")
                    self.assertTrue(body["has_link_gap"])
                    self.assertTrue(any(event["kind"] == "link_lost" for event in body["events"]))
                    self.assertEqual(len(body["counter_observations"]), 3)
                    export = client.get("/api/v1/history/export.csv")
                    exported = list(csv.DictReader(io.StringIO(export.text)))
                    session_row = next(row for row in exported if row["record_type"] == "session")
                    self.assertEqual(session_row["source_sha256"], source["sha256"])
                    self.assertEqual(session_row["profile_sha256"], profile["summary"]["sha256"])
                    self.assertEqual(session_row["link_gap_observed"], "True")
                    self.assertEqual(client.get("/api/v1/history/sessions/missing").status_code, 404)
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

    def test_counter_epoch_change_makes_session_delta_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = open_database(Path(directory) / "db.sqlite3")
            try:
                recorder = HistoryRecorder(database)
                recorder.observe(bench_snapshot(state="RUNNING", cycle=0,
                                                cycles=5, run_s=10),
                                 action="start", target_cycles=2)
                recorder.observe(bench_snapshot(state="RUNNING", cycle=0,
                                                cycles=0, run_s=0))
                session = recorder.sessions()[0]
                detail = recorder.session_detail(session["id"])
                self.assertIsNone(session["delta"])
                self.assertIsNone(detail["delta"])
                self.assertTrue(detail["counter_epoch_changed"])
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
