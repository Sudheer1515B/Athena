"""Durable observations of bench-reported runs and counters."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from uuid import uuid4

STOP_CAUSES = {
    "COMPLETED": "Cycle target reached; stopped state observed",
    "MANUAL_STOP": "Manual Stop command",
    "STOPPED_OBSERVED": "Stopped state observed; cause unknown",
    "SUPERSEDED": "Controller started another session",
    "REBOOT_OBSERVED": "Bench reboot observed; exact stop time unknown",
    "START_REJECTED": "Start rejected by bench; no replay started by this request",
    "COMMAND_UNCONFIRMED": "Start outcome could not be established from bench observations",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _numbers(counters: dict) -> tuple[int, int, list[int]]:
    cycles = int(counters["cycles"])
    run_s = int(counters["run_s"])
    active = [int(part) for part in counters["active_s"].split(",")]
    if cycles < 0 or run_s < 0 or not active or any(part < 0 for part in active):
        raise ValueError("Invalid bench counters")
    return cycles, run_s, active


class HistoryRecorder:
    """Records observations only; the bench remains the counter authority."""

    def __init__(self, database: sqlite3.Connection) -> None:
        self.database = database
        self._lock = threading.RLock()
        self._last_sample: dict[str, str] = {}
        self._last_run_cycle: dict[str, int] = {}
        self._connected_bench_id: str | None = None
        self._last_bench_id: str | None = None
        with self.database:
            self.database.execute(
                "UPDATE sessions SET status='UNCONFIRMED',identity_confidence='uncertain' "
                "WHERE ended_at IS NULL",
            )

    def observe(self, live: dict, *, action: str | None = None,
                target_cycles: int | None = None) -> None:
        connection = live.get("connection") or {}
        info = connection.get("bench") or {}
        counters = live.get("counters") or {}
        status = live.get("bench_state") or {}
        if connection.get("state") != "CONNECTED":
            with self._lock, self.database:
                if self._connected_bench_id is not None:
                    bench_id = self._connected_bench_id
                    stamp = now_utc()
                    active = self.database.execute(
                        "SELECT id FROM sessions WHERE bench_id=? AND ended_at IS NULL "
                        "ORDER BY created_at DESC LIMIT 1", (bench_id,),
                    ).fetchone()
                    session_id = active["id"] if active else None
                    if session_id is not None:
                        self.database.execute(
                            "UPDATE sessions SET status='UNCONFIRMED',"
                            "identity_confidence='uncertain' WHERE id=?",
                            (session_id,),
                        )
                    self._event(bench_id, session_id, "link_lost", stamp,
                                {"reason": "controller_disconnected_or_link_loss"},
                                "observed")
                    self._last_bench_id = bench_id
                    self._connected_bench_id = None
            return
        if not info or not counters:
            return
        try:
            cycles, run_s, active_s = _numbers(counters)
            uptime = int(info["up"])
            if len(active_s) != int(info["ch"]):
                return
        except (KeyError, ValueError, TypeError):
            return
        transport = connection.get("transport") or "UNKNOWN"
        address = connection.get("port") or "unknown"
        identity = f"{transport}|{address}|{info.get('team', '')}"
        bench_id = hashlib.sha256(identity.encode()).hexdigest()
        stamp = now_utc()
        trace = live.get("trace") or []
        sampled_at = trace[-1]["sampled_at"] if trace else stamp
        with self._lock, self.database:
            self.database.execute(
                "INSERT INTO benches(id,label,host,port,mode,capabilities_json,updated_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "capabilities_json=excluded.capabilities_json,updated_at=excluded.updated_at",
                (bench_id, info.get("team", "WDR"), address,
                 int(address.rsplit(":", 1)[-1]) if ":" in address else 115200,
                 "simulator" if transport == "SIMULATOR" else "hardware",
                 json.dumps(info, separators=(",", ":")), stamp),
            )
            if self._connected_bench_id != bench_id:
                if self._connected_bench_id is not None:
                    old_id = self._connected_bench_id
                    old_session = self.database.execute(
                        "SELECT id FROM sessions WHERE bench_id=? AND ended_at IS NULL "
                        "ORDER BY created_at DESC LIMIT 1", (old_id,),
                    ).fetchone()
                    if old_session is not None:
                        self.database.execute(
                            "UPDATE sessions SET status='UNCONFIRMED',"
                            "identity_confidence='uncertain' WHERE id=?",
                            (old_session["id"],),
                        )
                    self._event(old_id, old_session["id"] if old_session else None,
                                "link_lost", stamp,
                                {"reason": "controller_switched_connection"},
                                "observed")
                if self._last_bench_id == bench_id:
                    self._event(bench_id, None, "link_regained", stamp,
                                {"state": status.get("state")}, "observed")
                self._connected_bench_id = bench_id
            active_session = self.database.execute(
                "SELECT * FROM sessions WHERE bench_id=? AND ended_at IS NULL "
                "ORDER BY created_at DESC LIMIT 1", (bench_id,),
            ).fetchone()
            if action in {"start", "start_requested"}:
                if active_session is not None:
                    self._end_session(active_session["id"], "SUPERSEDED", stamp, "uncertain")
                session_id = str(uuid4())
                profile = live.get("profile") or {}
                self.database.execute(
                    "INSERT INTO sessions(id,bench_id,profile_id,target_cycles,status,"
                    "identity_confidence,started_at,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (session_id, bench_id, profile.get("id"), target_cycles or 0,
                     "START_UNCONFIRMED" if action == "start_requested" else "RUNNING",
                     "uncertain" if action == "start_requested" else "observed", stamp, stamp),
                )
                active_session = self.database.execute(
                    "SELECT * FROM sessions WHERE id=?", (session_id,),
                ).fetchone()
                self._last_run_cycle[bench_id] = 0
            session_id = active_session["id"] if active_session is not None else None

            previous = self.database.execute(
                "SELECT * FROM counter_snapshots WHERE bench_id=? ORDER BY id DESC LIMIT 1",
                (bench_id,),
            ).fetchone()
            old_active = json.loads(previous["active_s_json"]) if previous else []
            new_epoch = (previous is None or cycles < previous["cycles"]
                         or run_s < previous["run_s"]
                         or len(active_s) != len(old_active)
                         or any(new < old for new, old in zip(active_s, old_active)))
            if new_epoch:
                epoch_id = str(uuid4())
                self.database.execute(
                    "INSERT INTO counter_epochs(id,bench_id,cause,first_observed_at) "
                    "VALUES(?,?,?,?)",
                    (epoch_id, bench_id,
                     "first_observation" if previous is None else "counter_reset_or_replacement",
                     stamp),
                )
            else:
                epoch_id = previous["epoch_id"]
            if action is not None or self._last_sample.get(bench_id) != sampled_at:
                self.database.execute(
                    "INSERT INTO counter_snapshots(bench_id,epoch_id,session_id,observed_at,"
                    "uptime_s,cycles,run_s,active_s_json) VALUES(?,?,?,?,?,?,?,?)",
                    (bench_id, epoch_id, session_id, stamp, uptime, cycles, run_s,
                     json.dumps(active_s, separators=(",", ":"))),
                )
                self._last_sample[bench_id] = sampled_at

            if action is not None:
                self._event(bench_id, session_id, action, stamp, {
                    "state": status.get("state"), "cycles": cycles,
                    "run_s": run_s, "target_cycles": target_cycles,
                }, "observed")
            if action == "start_acknowledged" and active_session is not None:
                self.database.execute("UPDATE sessions SET identity_confidence='observed' WHERE id=?", (session_id,))
            if active_session is not None:
                try:
                    reported_cycle = int(status.get("cycle", "0"))
                except ValueError:
                    reported_cycle = 0
                previous_cycle = self._last_run_cycle.get(bench_id)
                if previous_cycle is not None and reported_cycle > previous_cycle:
                    if reported_cycle == previous_cycle + 1:
                        self._event(bench_id, session_id, "cycle_complete", stamp,
                                    {"run_cycle": reported_cycle}, "observed")
                    else:
                        self._event(bench_id, session_id, "cycles_advanced", stamp,
                                    {"from": previous_cycle, "to": reported_cycle},
                                    "aggregate")
                self._last_run_cycle[bench_id] = reported_cycle
            state = status.get("state")
            if active_session is not None:
                if live.get("reboot_detected"):
                    self._end_session(session_id, "REBOOT_OBSERVED", stamp, "uncertain")
                elif action == "stop":
                    self._end_session(session_id, "MANUAL_STOP", stamp, "observed")
                elif state == "STOPPED" and action not in {"start", "start_requested"}:
                    samples = self._session_snapshots(session_id)
                    delta = self._delta(samples)
                    completed = (active_session["target_cycles"] > 0
                                 and int(status.get("cycle", "0")) >= active_session["target_cycles"]
                                 and delta is not None and delta["cycles"] >= active_session["target_cycles"])
                    ending = "COMPLETED" if completed else "COMMAND_UNCONFIRMED" if active_session["status"] in {"START_UNCONFIRMED", "UNCONFIRMED"} else "STOPPED_OBSERVED"
                    self._end_session(session_id, ending,
                                      stamp, "observed" if completed else "inferred")
                    self._event(bench_id, session_id,
                                "cycle_target_reached" if completed else "run_ended_observed",
                                stamp, {"cycles": cycles, "run_s": run_s},
                                "observed" if completed else "inferred")
                elif state in {"RUNNING", "PAUSED"} and active_session["status"] != state:
                    self.database.execute(
                        "UPDATE sessions SET status=? WHERE id=?", (state, session_id),
                    )

    def notice(self, kind: str, details: dict) -> None:
        with self._lock, self.database:
            bench_id = self._connected_bench_id or self._last_bench_id
            if bench_id is None:
                return
            active = self.database.execute(
                "SELECT id FROM sessions WHERE bench_id=? AND ended_at IS NULL ORDER BY created_at DESC LIMIT 1", (bench_id,),
            ).fetchone()
            self._event(bench_id, active["id"] if active else None, kind, now_utc(), details, "uncertain")

    def reject_start(self, reason: str) -> None:
        self.notice("start_rejected", {"reason": reason})
        with self._lock, self.database:
            active = self.database.execute("SELECT id FROM sessions WHERE bench_id=? AND ended_at IS NULL ORDER BY created_at DESC LIMIT 1", (self._connected_bench_id,)).fetchone()
            if active:
                self._end_session(active["id"], "START_REJECTED", now_utc(), "observed")

    def _end_session(self, session_id: str, status: str, stamp: str,
                     confidence: str) -> None:
        self.database.execute(
            "UPDATE sessions SET status=?,ended_at=?,identity_confidence=? WHERE id=?",
            (status, stamp, confidence, session_id),
        )

    def _event(self, bench_id: str, session_id: str | None, kind: str,
               stamp: str, details: dict, confidence: str) -> None:
        self.database.execute(
            "INSERT INTO events(bench_id,session_id,kind,received_at,details_json,confidence) "
            "VALUES(?,?,?,?,?,?)",
            (bench_id, session_id, kind, stamp,
             json.dumps(details, separators=(",", ":")), confidence),
        )

    def sessions(self, limit: int = 50, *, start_at: str | None = None,
                 end_at: str | None = None) -> list[dict]:
        with self._lock:
            rows = self.database.execute(
                "SELECT s.*,b.label AS bench_label,b.host AS bench_host,"
                "b.mode AS bench_mode,b.capabilities_json AS bench_capabilities_json,"
                "p.sha256 AS profile_sha256,"
                "src.original_name AS source_name,src.sha256 AS source_sha256 "
                "FROM sessions s "
                "JOIN benches b ON b.id=s.bench_id "
                "LEFT JOIN profiles p ON p.id=s.profile_id "
                "LEFT JOIN source_logs src ON src.id=p.source_id "
                "WHERE (? IS NULL OR COALESCE(s.ended_at,?)>=?) "
                "AND (? IS NULL OR s.started_at<?) "
                "ORDER BY s.created_at DESC LIMIT ?",
                (start_at, now_utc(), start_at, end_at, end_at, limit),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                capabilities = json.loads(item.pop("bench_capabilities_json") or "{}")
                item["channel_count"] = int(capabilities["ch"]) if "ch" in capabilities else None
                item["stop_cause"] = STOP_CAUSES.get(item["status"])
                samples = self._session_snapshots(row["id"])
                item["delta"] = self._delta(samples)
                item["observation_count"] = len(samples)
                item["has_link_gap"] = bool(self.database.execute(
                    "SELECT 1 FROM events WHERE session_id=? AND kind='link_lost' LIMIT 1",
                    (row["id"],),
                ).fetchone())
                result.append(item)
            return result

    def session_detail(self, session_id: str) -> dict | None:
        with self._lock:
            row = self.database.execute(
                "SELECT s.*,b.label AS bench_label,b.host AS bench_host,"
                "b.port AS bench_port,b.mode AS bench_mode,"
                "b.capabilities_json AS bench_capabilities_json,"
                "p.sha256 AS profile_sha256,p.sum16 AS profile_sum16,"
                "p.rate_hz AS profile_rate_hz,p.frame_count AS profile_frame_count,"
                "p.canonical_json AS profile_canonical_json,"
                "src.id AS source_id,src.original_name AS source_name,"
                "src.sha256 AS source_sha256 FROM sessions s "
                "JOIN benches b ON b.id=s.bench_id "
                "LEFT JOIN profiles p ON p.id=s.profile_id "
                "LEFT JOIN source_logs src ON src.id=p.source_id WHERE s.id=?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            capabilities = item.pop("bench_capabilities_json")
            canonical_json = item.pop("profile_canonical_json")
            canonical = json.loads(canonical_json) if canonical_json else None
            item["bench_capabilities"] = json.loads(capabilities) if capabilities else None
            item["profile_settings"] = (
                {key: value for key, value in canonical.items() if key != "frames"}
                if canonical else None
            )
            samples = self._session_snapshots(session_id)
            item["counter_observations"] = [
                {**dict(sample), "active_s": json.loads(sample["active_s_json"])}
                for sample in samples
            ]
            for sample in item["counter_observations"]:
                sample.pop("active_s_json")
            item["delta"] = self._delta(samples)
            item["events"] = self.events(-1, session_id=session_id)
            item["has_link_gap"] = any(
                event["kind"] == "link_lost" for event in item["events"]
            )
            item["counter_epoch_changed"] = len({sample["epoch_id"] for sample in samples}) > 1
            item["stop_cause"] = STOP_CAUSES.get(item["status"])
            return item

    def _session_snapshots(self, session_id: str) -> list[sqlite3.Row]:
        return self.database.execute(
            "SELECT * FROM counter_snapshots WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()

    @staticmethod
    def _delta(samples: list[sqlite3.Row]) -> dict | None:
        if len(samples) < 2 or samples[0]["epoch_id"] != samples[-1]["epoch_id"]:
            return None
        first, last = samples[0], samples[-1]
        start_active = json.loads(first["active_s_json"])
        end_active = json.loads(last["active_s_json"])
        if len(start_active) != len(end_active):
            return None
        return {
            "cycles": max(0, last["cycles"] - first["cycles"]),
            "run_s": max(0, last["run_s"] - first["run_s"]),
            "active_s": [max(0, end - start)
                         for start, end in zip(start_active, end_active)],
        }

    def events(self, limit: int = 100, *, start_at: str | None = None,
               end_at: str | None = None,
               session_id: str | None = None) -> list[dict]:
        with self._lock:
            rows = self.database.execute(
                "SELECT * FROM events WHERE (? IS NULL OR received_at>=?) "
                "AND (? IS NULL OR received_at<?) "
                "AND (? IS NULL OR session_id=?) ORDER BY id DESC LIMIT ?",
                (start_at, start_at, end_at, end_at, session_id, session_id, limit),
            ).fetchall()
            return [{**dict(row), "details": json.loads(row["details_json"])}
                    for row in rows]
