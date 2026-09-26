# Drone motor command demo

This is a motor-specific command path. The reference bench's native STOP, boot and replay completion produce **1500 µs**, which is incompatible with assuming motors stop at 1000 µs. Native servo endurance replay remains available separately.

The hardware team/user confirmed the drone is secured, propellers are removed, an attended motor-power cutoff is available, **1000 µs stops these motors**, and **2000 µs is full power**. Exact Readytofly 40A variant/manual remains unverified. Do not treat a successful `SET` reply as physical motor monitoring.

## Run from Athena

1. Close `nc` and any other bench command clients. Keep the Mac awake and Wi-Fi connected. Have someone attend the motor-power cutoff throughout the test.
2. Start the ordinary backend if needed: `.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080`. Open <http://127.0.0.1:8080> and refresh after installing a new release build. In Settings connect Wi-Fi to **10.178.45.105**, port **3333**. Connection alone does not drive outputs.
3. Open **Profile**. Import/select the flight CSV, use a short initial trim, and map the correct motor log columns to all four outputs. GPIO mapping is OUT0=25, OUT1=26, OUT2=27, OUT3=33. Confirm the actual motor order with the hardware team; source channel labels alone do not establish drone motor order.
4. Set the profile limits for each output. The **Use confirmed motor range · 1000–2000 µs** button supplies the team's reported electrical endpoints, not a recommendation to run full throttle. Narrower limits such as 1000–1100 are supported for mapped channels. Compile & validate. Values outside the configured limits are rejected rather than clipped or scaled.
5. Use **Motor commands · 4 outputs**, below the native upload card. Review the actual minimum/maximum for every output. The allowed ceiling defaults to **1100 µs**; it is an additional rejection limit. If the extracted profile exceeds it, choose a lower-throttle source segment or deliberately approve an appropriate higher ceiling. Do not simply choose 2000 to bypass review.
6. Select **1 pass** initially, confirm the displayed conditions and mapping review, and click **Send extracted commands to motors**. **Do not use native Upload or the dashboard's native Start for powered ESC testing.** Motor sending reads the persisted compiled profile directly; no bench upload is required.
7. Watch acknowledged-frame progress. **Cancel & request 1000 µs** interrupts host playback and requests low on all four channels. Completion does the same. Wait for **1000 µs readback: confirmed by bench**. If output return is unconfirmed, disconnect motor power immediately. A readback confirms the bench's reported command, not motor motion or genuine ESC disarming.
8. When idle, **Set all four to 1000 µs** sends only four low SET commands and verifies STATUS. Native **Stop · 1500 µs** is not the motor stop button.

## How it works and limits

- Backend validates the complete persisted profile and checksum before issuing motor commands: four mapped outputs, every pulse between 1000 and the approved ceiling (maximum 2000), and 10–100 Hz frame rate. No synthetic replacement values are inserted into the extracted frames.
- A backend worker first requests all four outputs at 1000 µs, then sends four acknowledged `SET channel width` commands per frame at the compiled profile's timing, for a finite number of passes. The final frame is held until its scheduled interval ends, then low is requested and read back.
- Four SET commands are **sequential**, not atomic. This is host-timed replay, not deterministic bench-native playback. If schedule lateness exceeds the larger of 100 ms or two frame periods, replay aborts and requests low rather than silently skipping frames or claiming the requested timing was maintained. Local simulator success does not establish real Wi-Fi throughput.
- Upload, native Start/Stop/Pause/Resume, connection changes and manual SET are blocked in this backend while motor playback is active. Another external client can still interfere; close it. Cancel remains available, and playback continues if only the browser is closed while the backend remains alive.
- Lost acknowledgement terminates replay. It is not retried or automatically resumed after reconnection. If the connection is lost, software cannot guarantee low: the bench can hold its last throttle. Backend shutdown requests cancellation/low, but process kill, Mac power loss, network loss and bench reset cannot be made safe by this host-only feature. **Bench reset still produces 1500 µs.** An independent hardware cutoff or motor-compatible bench firmware is needed for a hardware failsafe.
- Native bench remains STOPPED during SET playback. Native cycle counters, run hours and active hours do **not** track this mode. UI shows acknowledged frames/host timing separately; history stores `motor_set_requested`/`motor_set_finished` audit events without inventing native cycles or mechanical life measurements.
- Receiver/motor monitoring integration is deferred. No ESC calibration, firmware flashing, motor-order discovery or flight controller stabilization is performed. This is a secured, propeller-free bench experiment, never a flight mode.

## APIs and files

- `POST /api/v1/motors/start`: `{ "profile_id": "...", "cycles": 1, "max_us": 1100, "safety_confirmed": true }`.
- `POST /api/v1/motors/cancel`: requests cancellation; inspect `snapshot.motor_replay` until terminal and low readback confirmed.
- `POST /api/v1/motors/idle`: requests all four at 1000 µs, requires an already STOPPED four-channel bench.
- `GET /api/v1/snapshot`: `motor_replay` includes phase, active, profile identity, acknowledged/total frames, elapsed seconds, observed maximum lateness, low confirmation, error and explicit `bench_counters_track_this_run=false`.
- `backend/motor_replay.py`: command sequencing/timing/cancellation. `backend/app.py`: persisted-profile checks, serialized ownership, audit events and APIs. `athena/lib/motor_send.dart`: reviewed command controls. `athena/lib/profile_page.dart`: editable/restored limits and compiled profile selection.
- `.venv/bin/python -u scripts/motor_preflight.py`: reconnects Athena to the known Wi-Fi bench and prints status/saved profile ranges. Only PING/INFO/STATUS/COUNTERS/TIME are used; it does not SET/upload/start/clear.
- `.venv/bin/python -u scripts/verify_motor_replay.py`: **local supplied simulator only**, isolated temporary data/counters. Tests exact 50 Hz frames, cancellation, acknowledgement loss, blocked competing controls, unchanged native counters and absence of native motion/upload/reset commands. Evidence: `/private/tmp/athena-motor-replay-verification.json`.

## Current saved profile and real-bench check

Read-only check on 2026-09-26: WDR_REFERENCE reachable, STOPPED, 1200 stored bench frames, reported outputs **800,800,800,800 µs**. Those values were observed, not set by this implementation. Current persisted Athena profile `17627305-cc4e-42ae-a1ab-8f06cd2424db` is 60 s at 50 Hz, C1→OUT0 through C4→OUT3, ranges **1050–1652**, **1050–1657**, **1050–1665**, **1050–1718 µs**. It will be rejected by the default 1100-µs motor ceiling. Do not increase the ceiling without reviewing the connected motors and intended throttle. No real throttle profile has been executed by automation in this implementation step.

Rollback: existing remote branch `prototype-rollback-20260926` at `6f8b5b8` remains unchanged. That older prototype has native 1500-us behavior and should not be mistaken for this motor sending mode.
