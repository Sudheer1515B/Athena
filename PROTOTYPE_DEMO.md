# Athena working demo — official simulator first

The main demo uses the organizer's **supplied simulator** and Flutter dashboard. It proves the flight-log → profile → WDR upload → replay → live pulse graph → durable session/counter history flow without changing either physical ESP32 or the real bench's saved 100-frame profile. The two-board PWM check is optional independent hardware evidence.

## Start two local services

From the workspace root, in Terminal A:

```sh
mkdir -p var/sim-tmp
TMPDIR="$PWD/var/sim-tmp" .venv/bin/python -u handout_controller_teams/wdr_tool.py serve-sim --listen 3333 --usb-port 3334
```

Leave it running. It serves WDR v1 on localhost TCP port 3333. Simulated counters stay in `var/sim-tmp`, isolated from other simulator runs.

In Terminal B:

```sh
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080` in a browser. Run only one backend and one simulator on these ports. Do not run the organizer's scorer against the same simulator during the live app demo; it takes over the TCP connection and may clear counters.

## One-minute replay sequence

1. **Settings:** Click **Connect local simulator**. Show `team=SIM`, four channels, `maxframes=8000`, and acknowledged `TIME`. The browser talks to Athena; Athena owns the simulator TCP connection.
2. **Profile:** Import the supplied, unchanged `RCOU.csv`. The sample preset selects 40–100 s, 50 fps, C1–C4 → OUT0–OUT3. Click **Compile & validate**. Show source/command previews, **3,000 frames**, **60 seconds per cycle**, and **SUM16 23174**. If an older 4-second draft restores, click **Use supplied 60 s flight segment** before compiling.
3. Click **Upload to simulator**. Athena sends `STOP`, `LOAD 50 3000`, all 3,000 frames, and `COMMIT`, checking the returned checksum. This changes **only the simulator**.
4. **Dashboard:** Click **Start 1 cycle**. Watch current-frame progress, live pulse widths, and the **sampled command-pulse graph** move for a minute. These are `STATUS` samples, not an oscilloscope or actuator feedback. You can demonstrate Pause/Resume while the run is active; leave it running to observe automatic completion.
5. Show the lifetime cycle count and per-channel active hours. Then open **History** and refresh: the completed session and events are stored in SQLite and survive a backend restart. Click **Export CSV** to download the dated session/event record; the date fields use UTC. Two verified 60-second runs each added **1 cycle and 60 running seconds**. Per-channel active-time deltas differed slightly at the sampling boundary (for example **32, 59, 56, 60** seconds and **32, 60, 56, 60** seconds). If the simulator has prior runs, compare deltas rather than expecting specific lifetime totals.

For a fast smoke test, the earlier 40–44 s window remains valid: 200 frames, 4 seconds, SUM16 16982. The one-minute run is better for judging because the live graph and hour meters visibly change.

Suggested line: “Athena converts an unmodified recorded flight into an exact PWM command profile, uploads it before motion, and lets the bench clock replay it. It shows sampled live commands and saves the bench's own cycle and per-channel active-time counters. Our second ESP separately verified that the physical reference bench generates four 50 Hz PWM outputs.”

## Optional real-output proof

The two ESP32 boards can remain wired and powered. They are **not used** by the simulator demo. If asked whether physical outputs exist, run this only after closing any serial monitor and ensuring Athena is **not** connected to the physical USB bench:

```sh
.venv/bin/python -u pwm_receiver/check_pwm.py
```

The receiver previously measured commanded widths `1100,1300,1700,1900` as `1100,1297,1694,1891` µs, each at a 20,000 µs period. The script sends only reversible `SET`/`STOP` commands and confirms the real bench's original 100-frame profile and lifetime counters remain unchanged. See `pwm_receiver/README.md` for port identities and wiring.

## What is proven and what remains

- **Proven in Athena against the supplied simulator:** log import, deterministic 3,000-frame compilation, checksum-verified upload, full 60-second finite replay, a connected browser view of the sampled pulse graph, authoritative counters, a completed durable session, history CSV export, and TIME acknowledgement. The end-to-end run added one cycle, 60 running seconds, and distinct per-channel active time. A 4-second smoke test also passed.
- **Proven electrically on the reference bench:** four distinct physical PWM outputs arrive on the independent receiver at the intended channels, then return to 1500 µs idle without profile or counter loss.
- **Not yet proven:** replay of the newly compiled profile on the real bench, physical servo movement/life, and final Wi-Fi hardware integration. Athena now accepts a WDR TCP host/port for the venue bench, but that path has not been exercised against venue hardware. Uploading the compiled profile to the real bench would replace its saved 100-frame profile; do not do that during this preservation demo. Counter reset is available only on the simulator; the backend refuses it on physical benches to preserve their lifetime totals.
