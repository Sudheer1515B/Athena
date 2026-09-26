from __future__ import annotations

import sqlite3
import threading
import tempfile
import unittest
from pathlib import Path
from hashlib import sha256

from fastapi.testclient import TestClient

from backend.app import app, bounded_indices
from backend.profiles import ProfileIssue, compile_profile, inspect_csv
from backend.storage import SCHEMA_VERSION, database_summary, open_database


class StorageTests(unittest.TestCase):
    def test_schema_reopens_without_losing_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "athena.sqlite3"
            connection = open_database(path)
            connection.execute(
                "INSERT INTO source_logs "
                "(id, original_name, sha256, managed_path, byte_count, inspection_json, created_at) "
                "VALUES ('source-1', 'flight.csv', 'abc', 'sources/flight.csv', 10, '{}', '2026-09-25T00:00:00Z')"
            )
            connection.commit()
            connection.close()

            reopened = open_database(path)
            try:
                version = reopened.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0]
                self.assertEqual(version, SCHEMA_VERSION)
                self.assertEqual(database_summary(reopened)["source_logs"], 1)
                self.assertEqual(
                    reopened.execute("PRAGMA journal_mode").fetchone()[0].lower(),
                    "wal",
                )
                self.assertEqual(reopened.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            finally:
                reopened.close()

    def test_newer_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "future.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute(
                "CREATE TABLE schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO schema_migrations VALUES (?, '2026-09-25T00:00:00Z')",
                (SCHEMA_VERSION + 1,),
            )
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(RuntimeError, "newer"):
                open_database(path)


class ApiTests(unittest.TestCase):
    def test_health_snapshot_and_initial_live_message_are_honest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_data_dir = app.router.lifespan_context

            # The application path is module-configured, so install a test
            # lifespan that uses an isolated database without changing global
            # developer data under var/.
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def isolated_lifespan(application):
                application.state.data_dir = Path(directory)
                application.state.database = open_database(
                    Path(directory) / "athena.sqlite3"
                )
                application.state.instance_id = "test-instance"
                try:
                    yield
                finally:
                    application.state.database.close()

            app.router.lifespan_context = isolated_lifespan
            try:
                with TestClient(app) as client:
                    health = client.get("/api/v1/health")
                    self.assertEqual(health.status_code, 200)
                    self.assertEqual(health.json()["schema_version"], SCHEMA_VERSION)

                    snapshot = client.get("/api/v1/snapshot").json()
                    self.assertEqual(snapshot["connection"], {
                        "state": "DISCONNECTED",
                        "bench": None,
                    })
                    self.assertIsNone(snapshot["counters"])
                    self.assertEqual(snapshot["history_counts"]["sessions"], 0)

                    with client.websocket_connect("/api/v1/live") as websocket:
                        message = websocket.receive_json()
                        self.assertEqual(message["type"], "snapshot")
                        self.assertEqual(message["sequence"], 0)
                        self.assertEqual(
                            message["payload"]["connection"]["state"],
                            "DISCONNECTED",
                        )
            finally:
                app.router.lifespan_context = original_data_dir


class ProfileTests(unittest.TestCase):
    def test_supplied_log_golden_profile_and_api_persistence(self) -> None:
        data = (Path(__file__).resolve().parent.parent / "RCOU.csv").read_bytes()
        flight = inspect_csv(data)
        self.assertEqual(flight.inspection["row_count"], 9074)
        self.assertEqual(flight.inspection["median_interval_us"], 99995)
        self.assertEqual(len(flight.inspection["gaps"]), 1)
        mapping = [{"output": i, "source": f"C{i + 1}"} for i in range(4)]
        canonical, summary = compile_profile(
            flight, sha256(data).hexdigest(), start_us=40_000_000,
            end_us=44_000_000, rate_hz=50, channel_count=4,
            maxframes=8000, mapping=mapping,
        )
        self.assertEqual((summary["frame_count"], summary["sum16"]), (200, 16982))
        self.assertEqual(summary["first_frame"], [1050] * 4)
        self.assertEqual(summary["last_frame"], [1219, 1208, 1185, 1201])
        second, second_summary = compile_profile(
            flight, sha256(data).hexdigest(), start_us=40_000_000,
            end_us=44_000_000, rate_hz=50, channel_count=4,
            maxframes=8000, mapping=mapping,
        )
        self.assertEqual(canonical, second)
        self.assertEqual(summary["sha256"], second_summary["sha256"])

        with tempfile.TemporaryDirectory() as directory:
            original = app.router.lifespan_context

            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def isolated(application):
                application.state.data_dir = Path(directory)
                application.state.database = open_database(Path(directory) / "db.sqlite3")
                application.state.instance_id = "profile-test"
                application.state.upload_lock = threading.Lock()
                try:
                    yield
                finally:
                    application.state.database.close()

            app.router.lifespan_context = isolated
            try:
                with TestClient(app) as client:
                    imported = client.post(
                        "/api/v1/sources", files={"file": ("RCOU.csv", data, "text/csv")}
                    )
                    self.assertEqual(imported.status_code, 201, imported.text)
                    source_id = imported.json()["id"]
                    request = {
                        "source_id": source_id, "start_us": 40_000_000,
                        "end_us": 44_000_000, "rate_hz": 50,
                        "channel_count": 4, "maxframes": 8000, "mapping": mapping,
                    }
                    created = client.post("/api/v1/profiles", json=request)
                    self.assertEqual(created.status_code, 201, created.text)
                    profile_id = created.json()["id"]
                    application_lock = app.state.upload_lock
                    application_lock.acquire()
                    try:
                        duplicate = client.post(f"/api/v1/bench/upload/{profile_id}")
                        self.assertEqual(duplicate.status_code, 409)
                        self.assertIn("already in progress", duplicate.json()["detail"])
                    finally:
                        application_lock.release()
                    self.assertEqual(created.json()["summary"]["sum16"], 16982)
                    self.assertEqual(client.get("/api/v1/sources").json()["items"][0]["id"], source_id)
                    self.assertEqual(client.get("/api/v1/profiles").json()["items"][0]["id"], profile_id)
                    self.assertEqual(
                        client.post("/api/v1/profiles", json=request).json()["id"],
                        profile_id,
                    )
                    exported = client.get(f"/api/v1/profiles/{profile_id}/export.csv")
                    self.assertEqual(exported.status_code, 200)
                    self.assertEqual(len(exported.text.splitlines()), 201)
                    self.assertEqual(exported.text.splitlines()[0], "t_ms,ch0,ch1,ch2,ch3")
                    self.assertEqual(
                        client.get(f"/api/v1/sources/{source_id}").json()["sha256"],
                        sha256(data).hexdigest(),
                    )
            finally:
                app.router.lifespan_context = original

    def test_invalid_selected_data_and_gaps_do_not_get_hidden_by_resampling(self) -> None:
        source = b"TimeUS,C1,C2\n0,1500,0\n100000,1600,0\n200000,1700,0\n2000000,1800,0\n2100000,1900,0\n"
        flight = inspect_csv(source)
        valid = [{"output": 0, "source": "C1"}]
        compile_profile(flight, "x", start_us=0, end_us=200000,
                        rate_hz=10, channel_count=1, maxframes=8000, mapping=valid)
        with self.assertRaises(ProfileIssue) as gap_error:
            compile_profile(flight, "x", start_us=100000, end_us=2050000,
                            rate_hz=10, channel_count=1, maxframes=8000, mapping=valid)
        self.assertEqual(gap_error.exception.code, "gap")
        with self.assertRaises(ProfileIssue) as pulse_error:
            compile_profile(flight, "x", start_us=0, end_us=200000,
                            rate_hz=10, channel_count=1, maxframes=8000,
                            mapping=[{"output": 0, "source": "C2"}])
        self.assertEqual(pulse_error.exception.code, "pulse_range")
        compile_profile(flight, "x", start_us=2000000, end_us=2100000,
                        rate_hz=10, channel_count=1, maxframes=8000, mapping=valid)

    def test_csv_structure_errors_are_precise(self) -> None:
        for data, code in [
            (b"TimeUS,C1,C1\n0,1500,1500\n1,1600,1600\n", "duplicate_header"),
            (b"TimeUS,C1\n0,1500\n0,1600\n", "invalid_timestamp"),
            (b"TimeUS,C1\n0,1500\n1,nope\n", "invalid_integer"),
            (b"TimeUS,C1\n0,1500\n1\n", "ragged_row"),
        ]:
            with self.subTest(code=code), self.assertRaises(ProfileIssue) as raised:
                inspect_csv(data)
            self.assertEqual(raised.exception.code, code)

    def test_thirty_hertz_uses_integer_time_and_capacity_is_exact(self) -> None:
        flight = inspect_csv(
            b"TimeUS,C1\n0,1000\n30000,1100\n60000,1200\n90000,1300\n120000,1400\n"
        )
        mapping = [{"output": 0, "source": "C1"}]
        canonical, summary = compile_profile(
            flight, "x", start_us=0, end_us=100000, rate_hz=30,
            channel_count=1, maxframes=3, mapping=mapping,
        )
        self.assertEqual(summary["frame_count"], 3)
        self.assertEqual(canonical["frames"], [[1000], [1100], [1200]])
        with self.assertRaises(ProfileIssue) as full:
            compile_profile(flight, "x", start_us=0, end_us=100000,
                            rate_hz=30, channel_count=1, maxframes=2,
                            mapping=mapping)
        self.assertEqual(full.exception.code, "capacity")

    def test_preview_keeps_short_spikes_within_point_budget(self) -> None:
        series = [1000] * 1000
        series[499] = 2400
        picks = bounded_indices([series], 20)
        self.assertLessEqual(len(picks), 20)
        self.assertIn(499, picks)
        self.assertEqual((picks[0], picks[-1]), (0, 999))


if __name__ == "__main__":
    unittest.main()
