"""Local HTTP and live-state entry points; bench control follows in M3."""

from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

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
    try:
        yield
    finally:
        app.state.database.close()


app = FastAPI(title="Athena controller", version="0.1.0", lifespan=lifespan)


def current_snapshot(connection: sqlite3.Connection, instance_id: str) -> dict:
    return {
        "api_version": 1,
        "server_instance_id": instance_id,
        "observed_at": utc_now(),
        "connection": {"state": "DISCONNECTED", "bench": None},
        "bench_state": None,
        "profile": None,
        "session": None,
        "counters": None,
        "operation": None,
        "history_counts": database_summary(connection),
    }


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
    return current_snapshot(app.state.database, app.state.instance_id)


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
