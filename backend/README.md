# Athena backend

The backend is a local FastAPI service. It provides the database schema, health and snapshot endpoints, flight CSV import/inspection, deterministic profile compilation/preview/export, and serves the Flutter web build. The prototype speaks WDR v1 to either the organizer's local TCP simulator or the reference ESP32 over USB serial. It reads counters from the connected device; it does not invent cycle or running-hour totals.

From the workspace root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080
```

The SQLite file is created at `var/athena.sqlite3`; source originals are stored under `var/sources/`. Set `ATHENA_DATA_DIR` to use a separate directory. API checks: `/api/v1/health`, `/api/v1/snapshot`, `/api/v1/sources`, `/api/v1/profiles`, and WebSocket `/api/v1/live`.

For the recommended software demo, run the supplied simulator in a second terminal:

```sh
mkdir -p var/sim-tmp
TMPDIR="$PWD/var/sim-tmp" .venv/bin/python -u handout_controller_teams/wdr_tool.py serve-sim --listen 3333 --usb-port 3334
```

Open **Settings → Connect local simulator**, then **Profile → import/compile → Upload to simulator**, then **Dashboard → Start 1 cycle**. The backend connects to loopback TCP port 3333 and accepts only `team=SIM`. See `PROTOTYPE_DEMO.md` for the exact demo script. Simulator upload and replay do not touch either ESP32 or the real bench's saved profile.

The optional physical path is **Settings → Connect USB bench** on `/dev/cu.usbserial-0001`. `STOP` is available while connected; `CLEAR` is intentionally absent. Verify external 5–6 V actuator power, common ground, and mechanical clearance before starting a run with servos. On this Mac, opening USB serial caused an `EVT BOOT` despite pre-setting DTR/RTS low, so connect only when the bench may safely reset to STOPPED. USB access needs the supplied reference firmware but does not require Wi-Fi or reflashing. **Uploading a profile to the real bench replaces its existing 100-frame profile**, so preserve it by using the simulator demo. The connection and uploaded-profile identity are in backend memory and must be re-established after a backend restart; lifetime counters remain on the board or simulator. Durable session accounting and Wi-Fi control remain later milestones.

For backend development checks:

```sh
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m unittest backend.test_app
```
