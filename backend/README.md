# Athena backend

The backend is a local FastAPI service. It provides flight CSV import/inspection, deterministic profile compilation/preview/export, durable session/event/counter observations, a bounded live pulse trace, and serves the Flutter web build. It speaks WDR v1 to the organizer's local TCP simulator, a WDR bench over TCP/Wi-Fi, or the reference ESP32 over USB serial. The connected bench remains authoritative for cycle and running-hour totals.

From the workspace root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080
```

The SQLite file is created at `var/athena.sqlite3`; source originals are stored under `var/sources/`. Set `ATHENA_DATA_DIR` to use a separate directory. API checks: `/api/v1/health`, `/api/v1/snapshot`, `/api/v1/sources`, `/api/v1/profiles`, `/api/v1/history/sessions`, `/api/v1/history/sessions/{id}`, `/api/v1/history/events`, and `/api/v1/history/export.csv` (optional UTC `from_date`/`through_date`). Session detail contains saved profile/source provenance, bench capabilities, mapping, counter observations, stop cause and coverage warnings. The CSV includes all matching sessions and events, with duration deltas in seconds and per-channel active seconds as a JSON array. The dashboard samples `STATUS` over HTTP each second; the snapshot includes the most recent 180 reported pulse samples for its live graph. The older `/api/v1/live` WebSocket endpoint still provides an initial snapshot but is not used by Flutter.

For the recommended software demo, run the supplied simulator in a second terminal:

```sh
mkdir -p var/sim-tmp
TMPDIR="$PWD/var/sim-tmp" .venv/bin/python -u handout_controller_teams/wdr_tool.py serve-sim --listen 3333 --usb-port 3334
```

Open **Settings → Connect local simulator**, then **Profile → import/compile → Upload to simulator**, then **Dashboard → Start 1 cycle**. The backend connects to loopback TCP port 3333 and accepts only `team=SIM`. The supplied `RCOU.csv` has a 40–100 s continuous segment that makes a 3,000-frame, one-minute cycle (SUM16 23174) without fabricating a log. See `PROTOTYPE_DEMO.md` for the exact demo script. Simulator upload and replay do not touch either ESP32 or the real bench's saved profile. A successful connection sends `TIME` and records only acknowledgement; it does not claim measured clock accuracy.

The optional physical path is **Settings → Connect USB bench** on `/dev/cu.usbserial-0001`, or **Connect Wi-Fi bench** with a reachable WDR TCP host/port (normally 3333). The user reports a connection-only Wi-Fi check at `10.178.45.105:3333`: Athena received reference-bench INFO and a TIME acknowledgement. Physical Wi-Fi profile upload/replay has not been tested. After an explicitly established TCP connection drops, Athena retries connection every three seconds and re-reads the bench state/counters; it never automatically uploads or sends START. USB does not reconnect automatically because reopening this Mac's serial port caused an `EVT BOOT` despite pre-setting DTR/RTS low. `STOP` is available while connected. Counter reset is exposed **only for the simulator**, with a confirmation dialog; the backend refuses `CLEAR` on physical benches. Verify external 5–6 V actuator power, common ground, and mechanical clearance before starting a run with servos. **Uploading a profile to the real bench replaces its existing 100-frame profile**, so preserve it by using the simulator demo. The connection and uploaded-profile identity are in backend memory and must be re-established after a backend restart. Session, event and counter observations persist in SQLite; a session interrupted by a backend restart is marked UNCONFIRMED until a fresh bench observation. Lifetime counters remain on the board or simulator.

For backend development checks:

```sh
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m unittest backend.test_app
```
