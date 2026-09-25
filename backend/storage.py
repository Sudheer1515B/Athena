"""The first durable schema for Athena's local run history."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    migrate(connection)
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        current = row[0] or 0
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema {current} is newer than this service supports"
            )
        if current == 0:
            connection.executescript(
            """
            CREATE TABLE source_logs (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                managed_path TEXT NOT NULL,
                byte_count INTEGER NOT NULL CHECK(byte_count >= 0),
                inspection_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE profiles (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES source_logs(id),
                sha256 TEXT NOT NULL UNIQUE,
                canonical_json TEXT NOT NULL,
                sum16 INTEGER NOT NULL CHECK(sum16 BETWEEN 0 AND 65535),
                rate_hz INTEGER NOT NULL CHECK(rate_hz BETWEEN 10 AND 100),
                frame_count INTEGER NOT NULL CHECK(frame_count > 0),
                channel_count INTEGER NOT NULL CHECK(channel_count BETWEEN 1 AND 16),
                created_at TEXT NOT NULL
            );
            CREATE TABLE benches (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL CHECK(port BETWEEN 1 AND 65535),
                mode TEXT NOT NULL CHECK(mode IN ('simulator', 'hardware')),
                capabilities_json TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                bench_id TEXT NOT NULL REFERENCES benches(id),
                profile_id TEXT REFERENCES profiles(id),
                target_cycles INTEGER NOT NULL CHECK(target_cycles >= 0),
                status TEXT NOT NULL,
                identity_confidence TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE operations (
                request_id TEXT PRIMARY KEY,
                body_sha256 TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                bench_id TEXT REFERENCES benches(id),
                session_id TEXT REFERENCES sessions(id),
                profile_id TEXT REFERENCES profiles(id),
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE counter_epochs (
                id TEXT PRIMARY KEY,
                bench_id TEXT NOT NULL REFERENCES benches(id),
                cause TEXT NOT NULL,
                first_observed_at TEXT NOT NULL
            );
            CREATE TABLE counter_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bench_id TEXT NOT NULL REFERENCES benches(id),
                epoch_id TEXT NOT NULL REFERENCES counter_epochs(id),
                session_id TEXT REFERENCES sessions(id),
                observed_at TEXT NOT NULL,
                uptime_s INTEGER NOT NULL,
                cycles INTEGER NOT NULL,
                run_s INTEGER NOT NULL,
                active_s_json TEXT NOT NULL
            );
            CREATE INDEX snapshots_by_bench_time
                ON counter_snapshots(bench_id, observed_at);
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bench_id TEXT REFERENCES benches(id),
                session_id TEXT REFERENCES sessions(id),
                request_id TEXT REFERENCES operations(request_id),
                kind TEXT NOT NULL,
                received_at TEXT NOT NULL,
                raw_line TEXT,
                details_json TEXT NOT NULL,
                confidence TEXT NOT NULL
            );
            CREATE INDEX events_by_time ON events(received_at);
            CREATE TABLE cycle_observations (
                session_id TEXT NOT NULL REFERENCES sessions(id),
                cycle_number INTEGER NOT NULL CHECK(cycle_number > 0),
                event_id INTEGER NOT NULL UNIQUE REFERENCES events(id),
                PRIMARY KEY (session_id, cycle_number)
            );
            """
        )
            connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) "
            "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
            (1,),
            )
            current = 1
        if current < 2:
            connection.execute("ALTER TABLE profiles ADD COLUMN summary_json TEXT NOT NULL DEFAULT '{}'")
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) "
                "VALUES (2, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
            )


def database_summary(connection: sqlite3.Connection) -> dict[str, int]:
    counts = {}
    for table in ("source_logs", "profiles", "sessions", "events"):
        counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return counts
