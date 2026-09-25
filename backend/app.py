"""Local HTTP and live-state entry points; bench control follows in M3."""

from __future__ import annotations

import os
import csv
import io
import sqlite3
import hashlib
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .profiles import MAX_SOURCE_BYTES, ProfileIssue, compile_profile, inspect_csv
from .bench_usb import BenchError, TcpBench, UsbBench
from .history import HistoryRecorder
from .storage import SCHEMA_VERSION, database_summary, open_database

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("ATHENA_DATA_DIR", ROOT / "var"))
WEB_DIR = ROOT / "athena" / "build" / "web"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database = open_database(DATA_DIR / "athena.sqlite3")
    app.state.instance_id = str(uuid4())
    app.state.bench = UsbBench()
    app.state.history = HistoryRecorder(app.state.database)
    app.state.desired_tcp = None
    app.state.reconnect_after = 0.0
    app.state.reconnect_lock = threading.RLock()
    try:
        yield
    finally:
        app.state.bench.disconnect()
        app.state.database.close()


app = FastAPI(title="Athena controller", version="0.1.0", lifespan=lifespan)


class MappingEntry(BaseModel):
    output: int
    source: str | None = None
    label: str | None = None
    serial: str | None = None
    min_us: int = 500
    max_us: int = 2500


class CompileRequest(BaseModel):
    source_id: str
    start_us: int
    end_us: int
    rate_hz: int = 50
    channel_count: int = Field(ge=1, le=16)
    maxframes: int = Field(ge=1)
    mapping: list[MappingEntry]


class UsbConnectRequest(BaseModel):
    port: str = Field(min_length=1)


class SimulatorConnectRequest(BaseModel):
    port: int = Field(default=3333, ge=1, le=65535)


class TcpConnectRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=3333, ge=1, le=65535)


class StartRequest(BaseModel):
    cycles: int = Field(ge=1, le=100000)


class SetPulseRequest(BaseModel):
    channel: int = Field(ge=0, le=15)
    width_us: int = Field(ge=500, le=2500)


def bench_error(error: Exception) -> HTTPException:
    return HTTPException(status_code=409, detail=str(error))


def issue_response(error: ProfileIssue) -> HTTPException:
    return HTTPException(status_code=422, detail=error.as_json())


def source_row(source_id: str) -> sqlite3.Row:
    row = app.state.database.execute("SELECT * FROM source_logs WHERE id = ?", (source_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Source log not found")
    return row


def data_dir() -> Path:
    return getattr(app.state, "data_dir", DATA_DIR)


def profile_row(profile_id: str) -> sqlite3.Row:
    row = app.state.database.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return row


def source_response(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "filename": row["original_name"],
        "sha256": row["sha256"], "byte_count": row["byte_count"],
        "created_at": row["created_at"],
        "inspection": json.loads(row["inspection_json"]),
    }


def profile_response(row: sqlite3.Row) -> dict:
    canonical = json.loads(row["canonical_json"])
    frames = canonical.pop("frames")
    summary = json.loads(row["summary_json"])
    return {
        "id": row["id"], "source_id": row["source_id"],
        "created_at": row["created_at"], "settings": canonical,
        "summary": summary, "preview_frames": frames[: min(200, len(frames))],
    }


def current_snapshot(connection: sqlite3.Connection, instance_id: str) -> dict:
    bench = getattr(app.state, "bench", None)
    live = bench.snapshot() if bench is not None else {}
    recorder = getattr(app.state, "history", None)
    if recorder is not None and recorder.database is connection:
        recorder.observe(live)
    result = {
        "api_version": 1,
        "server_instance_id": instance_id,
        "observed_at": utc_now(),
        "connection": live.get("connection", {"state": "DISCONNECTED", "bench": None}),
        "bench_state": live.get("bench_state"),
        "profile": live.get("profile"),
        "session": None,
        "counters": live.get("counters"),
        "operation": None,
        "recent_events": live.get("recent_events", []),
        "trace": live.get("trace", []),
        "time_sync": live.get("time_sync"),
        "simulator_reset_allowed": live.get("simulator_reset_allowed", False),
        "history_counts": database_summary(connection),
    }
    if getattr(app.state, "desired_tcp", None) is not None and \
            result["connection"]["state"] == "DISCONNECTED":
        result["connection"]["state"] = "RECONNECTING"
    return result


@app.get("/api/v1/health")
def health() -> dict:
    connection = app.state.database
    connection.execute("SELECT 1").fetchone()
    return {
        "status": "ok",
        "api_version": 1,
        "schema_version": SCHEMA_VERSION,
        "database": "ok",
    }


@app.get("/api/v1/snapshot")
def snapshot() -> dict:
    bench = getattr(app.state, "bench", None)
    if bench is not None and bench.connected:
        try:
            bench.refresh()
        except BenchError as error:
            if getattr(app.state, "desired_tcp", None) is None:
                raise HTTPException(status_code=503, detail=f"Bench did not respond: {error}") from error
            bench.disconnect()
            app.state.reconnect_after = time.monotonic() + 3
    desired = getattr(app.state, "desired_tcp", None)
    if desired is not None and not app.state.bench.connected and \
            time.monotonic() >= app.state.reconnect_after:
        with app.state.reconnect_lock:
            if not app.state.bench.connected and time.monotonic() >= app.state.reconnect_after:
                host, port, expected_team = desired
                replacement = TcpBench(expected_team=expected_team)
                try:
                    replacement.connect(host, port)
                    app.state.bench = replacement
                    app.state.reconnect_after = 0.0
                except (BenchError, OSError, ValueError):
                    app.state.reconnect_after = time.monotonic() + 3
    return current_snapshot(app.state.database, app.state.instance_id)


@app.post("/api/v1/bench/usb/connect")
def connect_usb(request: UsbConnectRequest) -> dict:
    try:
        app.state.desired_tcp = None
        app.state.bench.disconnect()
        app.state.bench = UsbBench()
        app.state.bench.connect(request.port)
    except (BenchError, OSError, ValueError) as error:
        raise bench_error(error) from error
    return current_snapshot(app.state.database, app.state.instance_id)


@app.post("/api/v1/bench/simulator/connect")
def connect_simulator(request: SimulatorConnectRequest) -> dict:
    try:
        app.state.desired_tcp = None
        app.state.bench.disconnect()
        app.state.bench = TcpBench()
        app.state.bench.connect("127.0.0.1", request.port)
        app.state.desired_tcp = ("127.0.0.1", request.port, "SIM")
    except (BenchError, OSError, ValueError) as error:
        raise bench_error(error) from error
    return current_snapshot(app.state.database, app.state.instance_id)


@app.post("/api/v1/bench/tcp/connect")
def connect_tcp(request: TcpConnectRequest) -> dict:
    try:
        app.state.desired_tcp = None
        app.state.bench.disconnect()
        app.state.bench = TcpBench(expected_team=None)
        app.state.bench.connect(request.host.strip(), request.port)
        app.state.desired_tcp = (request.host.strip(), request.port, None)
    except (BenchError, OSError, ValueError) as error:
        raise bench_error(error) from error
    return current_snapshot(app.state.database, app.state.instance_id)


@app.post("/api/v1/bench/usb/disconnect")
def disconnect_usb() -> dict:
    app.state.desired_tcp = None
    app.state.bench.disconnect()
    return current_snapshot(app.state.database, app.state.instance_id)


@app.post("/api/v1/bench/disconnect")
def disconnect_bench() -> dict:
    return disconnect_usb()


@app.post("/api/v1/bench/upload/{profile_id}")
def upload_to_bench(profile_id: str) -> dict:
    row = profile_row(profile_id)
    canonical = json.loads(row["canonical_json"])
    try:
        app.state.bench.upload(profile_id, canonical, row["sum16"])
    except (BenchError, OSError) as error:
        raise bench_error(error) from error
    app.state.history.observe(app.state.bench.snapshot(), action="profile_uploaded")
    return current_snapshot(app.state.database, app.state.instance_id)


@app.post("/api/v1/bench/start")
def start_bench(request: StartRequest) -> dict:
    try:
        app.state.bench.control("start", request.cycles)
    except BenchError as error:
        raise bench_error(error) from error
    app.state.history.observe(app.state.bench.snapshot(), action="start",
                              target_cycles=request.cycles)
    return current_snapshot(app.state.database, app.state.instance_id)


@app.post("/api/v1/bench/set")
def set_pulse(request: SetPulseRequest) -> dict:
    try:
        app.state.bench.set_pulse(request.channel, request.width_us)
    except BenchError as error:
        raise bench_error(error) from error
    app.state.history.observe(app.state.bench.snapshot(), action="set_pulse")
    return current_snapshot(app.state.database, app.state.instance_id)


@app.post("/api/v1/bench/time-sync")
def time_sync() -> dict:
    try:
        app.state.bench.sync_time()
    except BenchError as error:
        raise bench_error(error) from error
    app.state.history.observe(app.state.bench.snapshot(), action="time_sync")
    return current_snapshot(app.state.database, app.state.instance_id)


@app.post("/api/v1/bench/simulator/clear-counters")
def clear_simulator_counters() -> dict:
    try:
        app.state.bench.clear_simulator_counters()
    except BenchError as error:
        raise bench_error(error) from error
    app.state.history.observe(app.state.bench.snapshot(), action="simulator_counters_cleared")
    return current_snapshot(app.state.database, app.state.instance_id)


@app.post("/api/v1/bench/{action}")
def control_bench(action: str) -> dict:
    if action not in {"pause", "resume", "stop"}:
        raise HTTPException(status_code=404, detail="Unknown bench control")
    try:
        app.state.bench.control(action)
    except BenchError as error:
        raise bench_error(error) from error
    app.state.history.observe(app.state.bench.snapshot(), action=action)
    return current_snapshot(app.state.database, app.state.instance_id)


def history_bounds(from_date: str | None, through_date: str | None) -> tuple[str | None, str | None]:
    try:
        start = date.fromisoformat(from_date) if from_date else None
        through = date.fromisoformat(through_date) if through_date else None
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Use YYYY-MM-DD for history dates") from error
    if start is not None and through is not None and start > through:
        raise HTTPException(status_code=422, detail="History start date is after end date")
    first = datetime.combine(start, datetime.min.time(), timezone.utc).isoformat(timespec="milliseconds") if start else None
    end = datetime.combine(through + timedelta(days=1), datetime.min.time(), timezone.utc).isoformat(timespec="milliseconds") if through else None
    return first, end


@app.get("/api/v1/history/sessions")
def history_sessions(limit: int = Query(50, ge=1, le=100),
                     from_date: str | None = None,
                     through_date: str | None = None) -> dict:
    start, end = history_bounds(from_date, through_date)
    return {"items": app.state.history.sessions(limit, start_at=start, end_at=end)}


@app.get("/api/v1/history/sessions/{session_id}")
def history_session_detail(session_id: str) -> dict:
    detail = app.state.history.session_detail(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


@app.get("/api/v1/history/events")
def history_events(limit: int = Query(100, ge=1, le=200),
                   from_date: str | None = None,
                   through_date: str | None = None) -> dict:
    start, end = history_bounds(from_date, through_date)
    return {"items": app.state.history.events(limit, start_at=start, end_at=end)}


def _csv_cell(value: object) -> object:
    """Keep exported labels/details inert when opened in a spreadsheet."""
    if value is None:
        return ""
    result = str(value)
    if result.lstrip().startswith(("=", "+", "-", "@")) or result.startswith(("\t", "\r", "\n")):
        return "'" + result
    return result


@app.get("/api/v1/history/export.csv")
def export_history(from_date: str | None = None,
                   through_date: str | None = None) -> Response:
    start, end = history_bounds(from_date, through_date)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "record_type", "timestamp_utc", "bench_label", "bench_id", "session_id",
        "profile_id", "status_or_event", "target_cycles", "cycles_delta",
        "run_seconds_delta", "active_seconds_delta_by_channel", "confidence", "details",
        "bench_mode", "source_name", "source_sha256", "profile_sha256",
        "stop_cause", "counter_observation_count", "link_gap_observed",
    ])
    for session in app.state.history.sessions(-1, start_at=start, end_at=end):
        delta = session.get("delta") or {}
        writer.writerow([_csv_cell(value) for value in [
            "session", session["started_at"], session["bench_label"],
            session["bench_id"], session["id"], session["profile_id"],
            session["status"], session["target_cycles"], delta.get("cycles"),
            delta.get("run_s"), json.dumps(delta.get("active_s")) if delta else None,
            session["identity_confidence"],
            f"ended_at_utc={session['ended_at'] or ''}",
            session["bench_mode"], session["source_name"], session["source_sha256"],
            session["profile_sha256"], session["stop_cause"],
            session["observation_count"], session["has_link_gap"],
        ]])
    for event in app.state.history.events(-1, start_at=start, end_at=end):
        writer.writerow([_csv_cell(value) for value in [
            "event", event["received_at"], "", event["bench_id"],
            event["session_id"], "", event["kind"], "", "", "", "",
            event["confidence"], json.dumps(event["details"], sort_keys=True),
            "", "", "", "", "", "", "",
        ]])
    return Response(
        content=output.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="athena-history.csv"'},
    )


@app.post("/api/v1/sources", status_code=201)
async def import_source(file: UploadFile = File(...)) -> dict:
    data = await file.read(MAX_SOURCE_BYTES + 1)
    try:
        flight = inspect_csv(data)
    except ProfileIssue as error:
        raise issue_response(error) from error
    digest = hashlib.sha256(data).hexdigest()
    source_id = str(uuid4())
    managed = data_dir() / "sources" / f"{source_id}.csv"
    managed.parent.mkdir(parents=True, exist_ok=True)
    managed.write_bytes(data)
    created_at = utc_now()
    filename = Path(file.filename or "flight.csv").name
    with app.state.database:
        app.state.database.execute(
            "INSERT INTO source_logs (id, original_name, sha256, managed_path, byte_count, inspection_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (source_id, filename, digest, str(managed), len(data),
             json.dumps(flight.inspection, separators=(",", ":")), created_at),
        )
    return source_response(source_row(source_id))


@app.get("/api/v1/sources/{source_id}")
def get_source(source_id: str) -> dict:
    return source_response(source_row(source_id))


@app.get("/api/v1/sources")
def list_sources(limit: int = Query(20, ge=1, le=100)) -> dict:
    rows = app.state.database.execute(
        "SELECT * FROM source_logs ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {"items": [source_response(row) for row in rows]}


def bounded_indices(series: list[list[int] | tuple[int, ...]], max_points: int) -> list[int]:
    """Keep per-channel bucket extremes and both ends for display only."""
    length = len(series[0])
    if length <= max_points:
        return list(range(length))
    if max_points < 2 + 2 * len(series):
        return sorted({round(i * (length - 1) / (max_points - 1))
                       for i in range(max_points)})
    bucket_count = max(1, (max_points - 2) // (2 * len(series)))
    picks = {0, length - 1}
    for bucket in range(bucket_count):
        start = bucket * length // bucket_count
        end = min(length, (bucket + 1) * length // bucket_count)
        for channel in series:
            picks.add(min(range(start, end), key=channel.__getitem__))
            picks.add(max(range(start, end), key=channel.__getitem__))
    return sorted(picks)


@app.get("/api/v1/sources/{source_id}/preview")
def source_preview(
    source_id: str, channels: str = "", start_us: int = 0,
    end_us: int | None = None, max_points: int = Query(1000, ge=2, le=2000),
) -> dict:
    row = source_row(source_id)
    flight = inspect_csv(Path(row["managed_path"]).read_bytes())
    requested = [name for name in channels.split(",") if name] or list(flight.columns[:4])
    if any(name not in flight.columns for name in requested):
        raise HTTPException(status_code=422, detail="Unknown source channel")
    if end_us is None:
        end_us = flight.inspection["duration_us"]
    selected = [i for i, t in enumerate(flight.times)
                if start_us <= t - flight.times[0] <= end_us]
    if not selected:
        return {"channels": requested, "points": []}
    picks = [selected[i] for i in bounded_indices(
        [[flight.values[name][j] for j in selected] for name in requested], max_points
    )]
    return {
        "channels": requested,
        "points": [{"time_us": flight.times[i] - flight.times[0],
                    "values": {name: flight.values[name][i] for name in requested}}
                   for i in picks],
    }


@app.post("/api/v1/profiles", status_code=201)
def create_profile(request: CompileRequest) -> dict:
    source = source_row(request.source_id)
    flight = inspect_csv(Path(source["managed_path"]).read_bytes())
    try:
        canonical, summary = compile_profile(
            flight, source["sha256"], start_us=request.start_us,
            end_us=request.end_us, rate_hz=request.rate_hz,
            channel_count=request.channel_count, maxframes=request.maxframes,
            mapping=[item.model_dump() for item in request.mapping],
        )
    except ProfileIssue as error:
        raise issue_response(error) from error
    existing = app.state.database.execute(
        "SELECT * FROM profiles WHERE sha256 = ?", (summary["sha256"],)
    ).fetchone()
    if existing is not None:
        return profile_response(existing)
    profile_id = str(uuid4())
    with app.state.database:
        app.state.database.execute(
            "INSERT INTO profiles (id, source_id, sha256, canonical_json, summary_json, sum16, rate_hz, frame_count, channel_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (profile_id, request.source_id, summary["sha256"],
             json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
             json.dumps(summary, separators=(",", ":")), summary["sum16"],
             request.rate_hz, summary["frame_count"], request.channel_count, utc_now()),
        )
    return profile_response(profile_row(profile_id))


@app.get("/api/v1/profiles/{profile_id}")
def get_profile(profile_id: str) -> dict:
    return profile_response(profile_row(profile_id))


@app.get("/api/v1/profiles")
def list_profiles(limit: int = Query(20, ge=1, le=100)) -> dict:
    rows = app.state.database.execute(
        "SELECT * FROM profiles ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {"items": [profile_response(row) for row in rows]}


@app.get("/api/v1/profiles/{profile_id}/preview")
def profile_preview(profile_id: str, max_points: int = Query(1000, ge=2, le=2000)) -> dict:
    canonical = json.loads(profile_row(profile_id)["canonical_json"])
    frames = canonical["frames"]
    series = [[frame[channel] for frame in frames]
              for channel in range(canonical["channel_count"])]
    return {
        "frame_count": len(frames), "rate_hz": canonical["rate_hz"],
        "points": [{"frame": i, "values": frames[i]}
                   for i in bounded_indices(series, max_points)],
    }


@app.get("/api/v1/profiles/{profile_id}/export.csv")
def export_profile(profile_id: str) -> Response:
    canonical = json.loads(profile_row(profile_id)["canonical_json"])
    from io import StringIO
    import csv

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["t_ms", *[f"ch{i}" for i in range(canonical["channel_count"])]])
    for i, frame in enumerate(canonical["frames"]):
        t_ms = i * 1000 / canonical["rate_hz"]
        writer.writerow([f"{t_ms:.6f}".rstrip("0").rstrip("."), *frame])
    return Response(output.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="athena-{profile_id}.csv"'
    })


@app.websocket("/api/v1/live")
async def live(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json(
        {
            "api_version": 1,
            "server_instance_id": app.state.instance_id,
            "sequence": 0,
            "type": "snapshot",
            "received_at": utc_now(),
            "payload": current_snapshot(app.state.database, app.state.instance_id),
        }
    )
    try:
        while True:
            # No bench exists yet. Reading keeps the stream alive until the
            # browser disconnects; M3 will also publish bench state changes.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if not WEB_DIR.is_dir():
        return {"detail": "Flutter build not available; use the Flutter dev server"}
    requested = (WEB_DIR / path).resolve()
    if path and requested.is_relative_to(WEB_DIR.resolve()) and requested.is_file():
        return FileResponse(requested)
    return FileResponse(WEB_DIR / "index.html")
