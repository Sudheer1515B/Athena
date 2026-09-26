# Drone motor command demo

This is a motor-specific command path. The reference bench's native STOP, boot and replay completion produce **1500 µs**, which is incompatible with assuming motors stop at 1000 µs. Native servo endurance replay remains available separately.

The hardware team/user confirmed the drone is secured, propellers are removed, an attended motor-power cutoff is available, **1000 µs stops these motors**, and **2000 µs is full power**. Exact Readytofly 40A variant/manual remains unverified. Do not treat a successful `SET` reply as physical motor monitoring.

Latest update: the user confirms there is **no receiver connected** and asserts motors stop when the ESP loses power. Athena now provides command monitoring and saved-frame recovery below. Missing-signal stopping remains a hardware/ESC behavior; Athena cannot act while the ESP is unpowered. Fixed firmware's 1500-µs boot output remains unchanged.

## Dashboard monitoring and power recovery

The **Dashboard → Drone motor monitoring** card shows all four bench-reported commands and their GPIO mapping, sampled command graph, readback age, current all-four-1000 status, motor action phase, acknowledged frames, current pass, profile frame rate, elapsed attempt time, maximum scheduling delay and profile/start/end identity. `motor_monitoring` is included in `/api/v1/snapshot`. Stale Wi-Fi or unavailable backend hides current widths and the command graph instead of reusing old values. A historical successful low request is labeled historical and does not establish the current output state.

With no receiver, electrical PWM, RPM, motor current and temperature are **unknown/not measured**. A pulled motor signal wire cannot be detected by bench STATUS. If the existing receiver is later connected, its independent measured widths/NO SIGNAL appear separately; these still do not establish mechanical motion.

New motor runs persist an atomic, fsynced journal at `var/motor-checkpoint.json`: immutable profile identity, original passes/rate/approved ceiling, bench endpoint/capabilities, acknowledged full-frame count and a frame-in-flight marker. Each frame intent is saved before its four SET commands; after all four acknowledgements, its successor cursor is saved. Journal failure aborts playback and still attempts low; monitoring reports the checkpoint error. Checkpoints concern command delivery, not actual PWM edges or motor position.

For an interruption during **Motor commands** replay:

1. Athena stops sending the profile and preserves the cursor. Command widths become unknown when bench observations go stale. An ESC stopping on missing PWM is the hardware team's asserted behavior, not something the dashboard independently verifies.
2. Keep motor power isolated through the bench's boot output. When the same Wi-Fi bench returns, the backend automatically reconnects using the pinned endpoint/capabilities. For a pending motor recovery, it requests **only 1000 µs on all four outputs** and reads STATUS; no throttle frames or native START/upload are automatic. This low request happens after network reconnection and **cannot prevent the preceding 1500-µs boot transient**.
3. A **Motor replay interrupted · approval required** banner appears across tabs with saved next pass/frame. Native servo upload/start/stop/manual SET are blocked while this motor recovery waits. A manually requested motor low action preserves the saved recovery cursor.
4. Once the bench is fresh, STOPPED and reports all four at1000, click **Review saved motor resume…**. Confirm the same hardware/wiring, missing-PWM failsafe and protection against boot throttle, props removed/secured drone/attended cutoff, and the stated uncertainty; then **Approve motor resume**.
5. The backend verifies profile hash/checksum, limits, bench capabilities/endpoint and cursor bounds, consumes the approval, and sends only the remaining frames of the original finite run. It continues at the saved absolute command cursor; outage time is excluded from the profile clock. Duplicate approval is rejected. A lost reply/failed resume does not automatically send throttle again.

The saved frame cursor can survive browser/backend restart. On backend startup, an interrupted journal restores observation/reconnection and a pending review, never automatic throttle replay. A frame interrupted after some channels received SET is resent in full after approval. If the final complete-frame acknowledgement reached the bench before a checkpoint could be persisted, that frame may also be repeated. The last frame's physical dwell and motor behavior through power loss are unknown. This is **saved command-frame continuation**, not guaranteed exact physical continuity. Native WDR servo replay still has no seek command and its existing recovery starts a whole cycle from frame0.

API: `POST /api/v1/motors/recovery/resume` with `{ "run_id": "...", "hardware_recovery_confirmed": true, "uncertainty_acknowledged": true }`. Cursor/proposal is exposed in `snapshot.motor_replay.recovery`; monitoring telemetry is `snapshot.motor_monitoring`.

Rollback before this monitoring/recovery work: `pre-motor-monitoring-20260926` → `5ec8aca`. Durable journal recovery is a new feature; older versions did not store a per-frame cursor. Prior completed action summaries remain in History audit events even if their old in-memory dashboard state is cleared by the upgrade.

## Run from Athena

1. Close `nc` and any other bench command clients. Keep the Mac awake and Wi-Fi connected. Have someone attend the motor-power cutoff throughout the test.
2. Start the ordinary backend if needed: `.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080`. Open <http://127.0.0.1:8080> and refresh after installing a new release build. In Settings connect Wi-Fi to **10.178.45.105**, port **3333**. Connection alone does not drive outputs.
3. Open **Profile**. Import/select the flight CSV, use a short initial trim, and map the correct motor log columns to all four outputs. GPIO mapping is OUT0=25, OUT1=26, OUT2=27, OUT3=33. Confirm the actual motor order with the hardware team; source channel labels alone do not establish drone motor order.
4. Set the profile limits for each output. The **Use confirmed motor range · 1000–2000 µs** button supplies the team's reported electrical endpoints, not a recommendation to run full throttle. Narrower limits such as 1000–1100 are supported for mapped channels. Compile & validate. Values outside the configured limits are rejected rather than clipped or scaled.
5. Use **Motor commands · 4 outputs**, below the native upload card. Review the actual minimum/maximum for every output. The allowed ceiling defaults to **1100 µs**; it is an additional rejection limit. If the extracted profile exceeds it, choose a lower-throttle source segment or deliberately approve an appropriate higher ceiling. Do not simply choose 2000 to bypass review.
6. Select **1 pass** initially, confirm the displayed conditions and mapping review, and click **Send extracted commands to motors**. **Do not use native Upload or the dashboard's native Start for powered ESC testing.** Motor sending reads the persisted compiled profile directly; no bench upload is required.
7. Watch acknowledged-frame progress. **Cancel & request 1000 µs** interrupts host playback and requests low on all four channels. Completion does the same. Check the action's confirmed low readback and **Dashboard → Bench currently reports all four outputs at1000 µs** with fresh command data. If output return is unconfirmed, disconnect motor power immediately. A readback confirms the bench's reported command, not motor motion or genuine ESC disarming.
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
