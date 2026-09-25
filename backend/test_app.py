from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
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


if __name__ == "__main__":
    unittest.main()
