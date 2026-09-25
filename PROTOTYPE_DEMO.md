# Athena prototype demo — official simulator first

The main demo uses the organizer's **supplied simulator** and Flutter dashboard. It proves the flight-log → profile → WDR upload → replay → counters flow without changing either physical ESP32 or the real bench's saved 100-frame profile. The two-board PWM check is optional independent hardware evidence.

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

## Two-minute live sequence

1. **Settings:** Click **Connect local simulator**. Show `team=SIM`, four channels, and `maxframes=8000` from live `INFO`. The browser talks to Athena; Athena owns the simulator TCP connection.
2. **Profile:** Import `RCOU.csv`. Use the 40–44 s window, 50 fps, C1–C4 → OUT0–OUT3. Click **Compile & validate**. Show source/command traces, **200 frames**, a 4-second cycle, and **SUM16 16982**.
3. Click **Upload to simulator**. Athena sends `STOP`, `LOAD 50 200`, all 200 frames, and `COMMIT`, checking the simulator's returned checksum. This changes **only the simulator**.
4. **Dashboard:** Click **Start 1 cycle**. Watch the state go RUNNING → STOPPED. Point to the authoritative lifetime cycle count and each channel's active hours. A fresh simulator run adds **1 cycle, 4 running seconds, and 4 active seconds per channel**. If the simulator has prior runs, compare before/after deltas instead of expecting a total of one.

Suggested line: “Athena converts a recorded drone flight into an exact PWM command profile, uploads it before motion, and lets the bench clock replay it. The browser reads cycle and per-channel active-time counters back from the WDR simulator. This is the complete software prototype; our second ESP separately verified that the physical reference bench generates four 50 Hz PWM outputs.”

## Optional real-output proof

The two ESP32 boards can remain wired and powered. They are **not used** by the simulator demo. If asked whether physical outputs exist, run this only after closing any serial monitor and ensuring Athena is **not** connected to the physical USB bench:

```sh
.venv/bin/python -u pwm_receiver/check_pwm.py
```

The receiver previously measured commanded widths `1100,1300,1700,1900` as `1100,1297,1694,1891` µs, each at a 20,000 µs period. The script sends only reversible `SET`/`STOP` commands and confirms the real bench's original 100-frame profile and lifetime counters remain unchanged. See `pwm_receiver/README.md` for port identities and wiring.

## What is proven and what remains

- **Proven in Athena against the supplied simulator:** log import, deterministic 200-frame compilation, checksum-verified upload, one finite replay, and authoritative cycle/active-time counters. An end-to-end API check returned `cycles=1 run_s=4 active_s=4,4,4,4` on a fresh simulator instance.
- **Proven electrically on the reference bench:** four distinct physical PWM outputs arrive on the independent receiver at the intended channels, then return to 1500 µs idle without profile or counter loss.
- **Not yet proven:** replay of the newly compiled profile on the real bench, physical servo movement/life, final Wi-Fi hardware integration, and durable per-run history in Athena. Uploading the compiled profile to the real bench would replace its saved 100-frame profile; do not do that during this preservation demo.
