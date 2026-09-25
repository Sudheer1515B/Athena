# Athena backend

The backend is a local FastAPI service. M1–M2 provide the database schema, health and snapshot endpoints, a live snapshot WebSocket, flight CSV import/inspection, deterministic profile compilation/preview/export, and serving of the Flutter web build. It does **not yet** connect to the bench or report fabricated counters.

From the workspace root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080
```

The SQLite file is created at `var/athena.sqlite3`; source originals are stored under `var/sources/`. Set `ATHENA_DATA_DIR` to use a separate directory. API checks: `/api/v1/health`, `/api/v1/snapshot`, `/api/v1/sources`, `/api/v1/profiles`, and WebSocket `/api/v1/live`.

Run one server worker. M3 adds bench connection and upload; later milestones add run controls and durable accounting.

For backend development checks:

```sh
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m unittest backend.test_app
```
