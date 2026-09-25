# Athena backend

The backend is a local FastAPI service. It provides the database schema, health and snapshot endpoints, flight CSV import/inspection, deterministic profile compilation/preview/export, and serves the Flutter web build. The time-boxed prototype also controls the reference ESP32 over USB serial. It reads the bench's real counters; it does not invent cycle or running-hour totals.

From the workspace root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080
```

The SQLite file is created at `var/athena.sqlite3`; source originals are stored under `var/sources/`. Set `ATHENA_DATA_DIR` to use a separate directory. API checks: `/api/v1/health`, `/api/v1/snapshot`, `/api/v1/sources`, `/api/v1/profiles`, and WebSocket `/api/v1/live`.

Run one server worker. Open **Settings → Connect USB bench**, then **Profile → import/compile → Upload to USB bench**, then **Dashboard → Start 1 cycle**. `STOP` is always available while connected; `CLEAR` is intentionally absent. Verify external 5–6 V actuator power, common ground, and mechanical clearance before starting a physical run. On this Mac, opening USB serial caused an `EVT BOOT` despite pre-setting DTR/RTS low, so connect only when the bench may safely reset to STOPPED. USB access needs the supplied reference firmware but does not require Wi-Fi or reflashing. The USB connection and uploaded-profile identity are in memory and must be re-established after a backend restart; lifetime counters remain on the board. Durable session accounting and Wi-Fi control remain later milestones.

For backend development checks:

```sh
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m unittest backend.test_app
```
