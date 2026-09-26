# Athena working demo — official simulator first

The main demo uses the organizer's **supplied simulator** and Flutter dashboard. It proves the flight-log → profile → WDR upload → replay → live pulse graph → durable session/counter history flow without requiring physical hardware during judging. A separate real Wi-Fi run has now verified a short 200-frame Athena profile and all four physical PWM outputs; its evidence is saved, so it need not be repeated live.

## Double-click launchers on this Mac

- Double-click [Start Simulator Demo.command](Start%20Simulator%20Demo.command) for the main demo. It starts the supplied simulator and Athena backend, connects Athena to `team=SIM`, then opens the dashboard. Follow the Profile and replay sequence below. Press **Enter in the launcher Terminal window** when finished; it stops only the processes it started.
- Double-click [Start Wi-Fi Hardware Proof.command](Start%20Wi-Fi%20Hardware%20Proof.command) for the physical proof. The second ESP32 (CH340 receiver) must be connected to the Mac by USB; the WDR bench may be powered by a separate USB supply. The launcher verifies the receiver identity, starts Athena, opens the dashboard, and shows measured PWM lines in its Terminal window. It does **not** open the WDR USB serial port, connect the WDR over Wi-Fi, upload, START, STOP, or clear counters. In Athena, choose **Settings → Connect Wi-Fi bench** using its current IP, then deliberately upload/start a finite profile. Press **Ctrl-C in the launcher Terminal window** to close the receiver monitor and backend.

Both launchers require the existing `.venv` and Flutter web build (`athena/build/web/index.html`). If the build is missing, run `cd athena && flutter build web` once. They refuse to start if their local ports are already occupied, and write backend/simulator logs under `var/demo/`. Use one launcher at a time, and wait until a run has stopped before closing its launcher window so Athena can save the final observation. On macOS, Finder may ask you to confirm opening a newly created `.command` file.

If the receiver USB is attached to a Windows laptop, use [Windows receiver monitor with Athena on the Mac](pwm_receiver/WINDOWS_MONITOR.md). Run the backend directly on the Mac instead of the hardware launcher, which expects the receiver locally. A fresh backend requires a verified upload before Start; uploading replaces the bench's committed profile.

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
   The **Start** button remains disabled while an upload is still running. Click Upload once, wait for it to finish, then check that Dashboard shows a stopped bench and the committed frame count.
4. **Dashboard:** Click **Start 1 cycle**. Watch current-frame progress, live pulse widths, and the **sampled command-pulse graph** move for a minute. These are `STATUS` samples, not an oscilloscope or actuator feedback. You can demonstrate Pause/Resume while the run is active; leave it running to observe automatic completion.
5. Show the lifetime cycle count and per-channel active hours. Then open **History** and refresh: the completed session and events are stored in SQLite and survive a backend restart. Show the active-hours bars, select an output to filter them, and expand the session to see the saved profile/mapping, stop cause and bench counter observations. Click **Export CSV** to download the dated session/event record; the date fields use UTC. Two verified 60-second runs each added **1 cycle and 60 running seconds**. Per-channel active-time deltas differed slightly at the sampling boundary (for example **32, 59, 56, 60** seconds and **32, 60, 56, 60** seconds). If the simulator has prior runs, compare deltas rather than expecting specific lifetime totals.

For a fast smoke test, the earlier 40–44 s window remains valid: 200 frames, 4 seconds, SUM16 16982. The one-minute run is better for judging because the live graph and hour meters visibly change.

Suggested line: “Athena converts an unmodified recorded flight into a PWM command profile, uploads it before motion, and lets the bench clock replay it. It shows sampled live commands and saves the bench's own cycle and per-channel active-time counters. We also replayed a short flight segment over Wi-Fi on the real bench, while a second ESP independently measured all four PWM outputs.”

## Optional real-output proof

### Ten-minute Wi-Fi recovery demo

Keep the bench powered from its separate USB supply/computer and the receiver powered on Windows. Keep all four signal wires and common ground connected; leave servos disconnected for this signal-only demonstration.

1. Start the receiver with **Start Windows Receiver.cmd** (setup in `pwm_receiver/WINDOWS_MONITOR.md`). On the Mac, start the updated backend and open Athena. Connect to the reachable bench Wi-Fi address, last known `10.178.45.105:3333`.
2. Compile the supplied 40–100 s flight segment at 50 fps: 3,000 frames, 60 seconds per cycle. Upload once and wait for checksum confirmation. Set **cycle target 12** and Start once: about 12 minutes total. This replaces the prior profile and increments bench counters.
3. Around 15 seconds into playback, turn **the Mac's Wi-Fi off for ten minutes**. Leave the backend and both ESP32s powered. Do not press Disconnect in Athena: that deliberately cancels recovery. Do not unplug PWM/ground wires or reset the bench.
4. Athena should warn that contact is lost, report retry timing/observation age, and stop presenting samples as live. The separate Windows terminal should continue printing PWM widths and pulse counts: playback runs on the bench, without needing a connected dashboard.
5. Turn Mac Wi-Fi back on and rejoin the same reachable network. Athena retries automatically, reads the current frame/state and lifetime counters, and does **not** issue another Start. Allow roughly one retry wait plus connection time; a changed bench IP requires manual reconnection to its new address.
6. Let the finite run finish. Refresh History and expand the session: it must retain the link gap/uncertainty warning and recovered aggregate counters. Exact intermediate cycle completion times cannot be recovered. If a shorter run finished during the outage, it should reconcile to completion from bench counter evidence after reconnect.

The backend must remain running for this automatic recovery. Stop cannot reach a disconnected bench; bench power loss/reboot is a different failure. Profile identity becomes unverified after reconnect, so a subsequent new Start requires another deliberate verified upload. A ten-minute supplied-simulator transport test is being recorded; a physical ten-minute outage has not yet been verified.


The two ESP32 boards can remain wired and powered. They are **not used** by the simulator demo. If asked whether physical outputs exist, run this only after closing any serial monitor and ensuring Athena is **not** connected to the physical USB bench:

```sh
.venv/bin/python -u pwm_receiver/check_pwm.py
```

The receiver first measured manual commands `1100,1300,1700,1900` as `1100,1297,1694,1891` µs, each at a 20,000 µs period. Later, during Athena's real Wi-Fi replay of a 200-frame flight-log profile, it recorded 21 valid four-channel readings with 19,999–20,000 µs periods; the active widths tracked the uploaded profile. [Saved evidence](captures/real_wifi_flight_20260926.json) is preferable to repeating a physical run live. Counters immediately after that run were `cycles=25 run_s=34 active_s=33,33,33,16`; subsequent saved 50-second and 60-second real-bench sessions advanced them further. See `pwm_receiver/README.md` for port identities and wiring, and Entry 017 in `IMPLEMENTATION_LOG.md` for the later verification.

## What is proven and what remains

- **Proven in Athena against the supplied simulator:** log import, deterministic 3,000-frame compilation, checksum-verified upload, full 60-second finite replay, a connected browser view of the sampled pulse graph, authoritative counters, a completed durable session, history CSV export, and TIME acknowledgement. The end-to-end run added one cycle, 60 running seconds, and distinct per-channel active time. A 4-second smoke test also passed.
- **Proven on the four-channel reference bench:** Athena uploaded a 200-frame profile from the supplied flight log over Wi-Fi, completed one finite four-second cycle, saved the bench-reported counter deltas, and the independent receiver saw four physical PWM signals matching the profile's value ranges. Persisted History also verifies completed one-cycle real-bench runs of 2,500 frames (50 seconds) and 3,000 frames (60 seconds). Those longer runs have bench-reported evidence, without a saved independent receiver capture. The latest read-only check found the bench STOPPED with the 3,000-frame profile committed. The original 100-frame width sequence was archived before replacement.
- **Not yet proven:** physical servo movement/life and operation on 16-channel hardware. Counter reset remains simulator-only; the backend refuses it on the physical bench.
