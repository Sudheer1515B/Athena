# Athena — Implementation Log

**Last updated:** 26 September 2026 (Asia/Kolkata).

This is the execution record for [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Record actual work and verification here; planned features are not completed features. Preserve prior entries and append corrections/new evidence rather than rewriting history to look successful.

## Current status

**Application implementation: IN PROGRESS; M1–M2 COMPLETE.** Athena imports and compiles the supplied CSV, persists originals and immutable profiles, previews traces and exports compiled CSV. Its USB, local-simulator and generic WDR TCP adapters can upload profiles and run finite cycles. A full 60-second Athena API replay completed against the supplied simulator. A later Athena Wi-Fi run uploaded the 200-frame flight-log profile to the physical reference bench, completed one finite cycle, persisted its history, and was independently observed by the wired receiver ESP32. No servos were attached.

**Artifact review and official-tool baseline: COMPLETE.** The official simulator is available. No replacement simulator is needed. The original tool conformance runs passed, and Athena now connects to its real TCP service.

## Milestone tracker

| ID | Milestone | Status | Evidence / remaining work |
|---|---|---|---|
| M0 | Artifact inspection, supplied-tool baselines, detailed plan/log | Complete | Entry 001 and planning_evidence |
| M1 | Backend skeleton/schema, Flutter shell, interfaces | Complete | Backend tests, Flutter analyze/tests/build and 1440×900 visual review pass |
| M2 | CSV importer and deterministic compiler | Complete | Golden case and API persistence/export pass; Flutter analyze/tests/build pass |
| M3 | WDR adapter, uploads and operations | In progress | USB read path, simulator replay, and physical Wi-Fi 200-frame upload/finite replay pass; remaining recovery cases and longer physical run untested |
| M4 | First browser-to-simulator workflow | In progress | Full 40–100 s workflow passed through Athena API against supplied TCP simulator; live browser walkthrough remains |
| M5 | Controls, recovery, accounting | In progress | Start/pause/resume/stop, manual SET, live counters, durable sessions and uncertain disconnect state exist; recovery edge cases remain |
| M6 | History/filtering/charts/CSV | In progress | Sessions/events, UTC and channel filters, per-channel hours chart, expanded persisted details and CSV pass tests; browser visual review of populated History remains |
| M7 | PDF, finish estimate, production build/README/demo | In progress | Web build and 60-second simulator demo runbook exist; report/estimate and final polish remain |
| M8 | Venue hardware verification | In progress | Real Wi-Fi upload of compiled 200-frame flight profile and one finite cycle passed; receiver independently saw four PWM outputs; 16-channel/servo-load tests remain |

## Entry 001 — 25 September 2026 — Inspection and planning only

### Request and scope

User supplied `wdr_tool.py` and asked to review it and all provided material, write a detailed implementation-plan file and an implementation-log file, and not start coding. Work was restricted to reading, diagnostic calculations, running the provided tool, saving its test results, and updating documentation.

### Inputs reviewed

- Entire 1,796-line `wdr_tool.py`: transports, simulator, frame scheduler, counters/storage, command handlers, reply parser, all seven scorer levels, upload/term/soak/server/sample generator and argument parser.
- Frozen four-page WDR protocol manual and one-page Competition A brief.
- All four supplied HTML references, including their controls, static values, charts and firmware wiring description.
- Sample RCOU CSV structure, row counts, timestamps, channel ranges/zero values and gap.
- Existing project context, artifact findings, Flutter manifest/README and earlier research proposals relevant to protocol/accounting conflicts.
- Workspace file inventory and Git status. No applicable AGENTS.md was found in the inspected project paths. Existing staged/unstaged user changes were preserved.

### Verified findings

1. Official simulator is WDR v1, team SIM, four channels, 2,000 frames.
2. Real TCP and virtual USB default to localhost ports 3333/3334; custom ports are supported.
3. Virtual USB accepts `!RESET`; production TCP does not expose that reset command.
4. A new controller displaces the previous one and disables telemetry; playback continues through link loss.
5. Reboot returns STOPPED with idle outputs, reloads saved counters and discards the profile.
6. STOP retains a committed profile and does not clear an in-progress upload buffer; LOAD replaces the old profile.
7. TIME acknowledges an integer but does not store/use it in this simulator.
8. Counter seconds are rounded on reporting/save. Reboot persistence tests save first with PAUSE and cannot establish zero-loss abrupt-power-cut persistence.
9. CSV upload utility ignores its timestamp column and plays rows at --rate. It does not import/resample the supplied RCOU dialect.
10. Executable scorer has seven levels totaling 85, despite a stale six-level source banner; cmd_test may exit zero on failed checks.
11. The tool's default temp-directory counter file is shared, so tests need isolation and sequential execution.
12. Original simulator behavior was retained; no edits were made to wdr_tool.py.

### Executed checks and evidence

Environment: supplied tool run with system Python 3.14.7; simulator/TCP paths need only the standard library. No dependency installation was performed.

Isolated state directory used for both sequential checks: `/private/tmp/athena-wdr-review.keaPZM`. Test-specific TCP ports: 43333 and 43334. No connection to physical hardware occurred.

| Check | Result | Durable evidence |
|---|---|---|
| `python3 wdr_tool.py --help` | Available subcommands confirmed | Commands recorded here; no application effect |
| `python3 wdr_tool.py serve-sim --help` | --listen and --usb-port confirmed | Source and command inspection |
| In-process full conformance | 85/85, all checks passed | [JSON results](planning_evidence/wdr-inprocess-2026-09-25.json) |
| TCP plus virtual USB full conformance | 85/85, all checks passed | [JSON results](planning_evidence/wdr-tcp-2026-09-25.json) |
| Source CSV statistics | 9,074 rows; expected ranges; one 23.499649 s gap | Plan §2.5 |
| Diagnostic golden-window calculation | 200 frames; first/last/ranges calculated; SUM16=16982 | Plan §2.5 and §4.4 |
| Simulator process cleanup | Inspection server stopped after tests | Tool process exited 0 following interrupt |
| Documentation QA | Local links resolve; Markdown fences balanced; git diff --check clean | Plan/log/context/artifact notes/README checked |
| Evidence QA | Both JSON files parse, all 36 checks per run pass, totals 85/85 | planning_evidence; original vendor SHA-256 unchanged |

Exact baseline commands, run from workspace root:

```sh
env TMPDIR=/private/tmp/athena-wdr-review.keaPZM python3 -u wdr_tool.py test --port sim --json /private/tmp/athena-wdr-review.keaPZM/inprocess-results.json
env TMPDIR=/private/tmp/athena-wdr-review.keaPZM python3 -u wdr_tool.py serve-sim --listen 43333 --usb-port 43334
env TMPDIR=/private/tmp/athena-wdr-review.keaPZM python3 -u wdr_tool.py test --host 127.0.0.1 --tcp-port 43333 --serial tcp://127.0.0.1:43334 --json /private/tmp/athena-wdr-review.keaPZM/tcp-results.json
```

Initial server binding and TCP-client attempts were blocked by sandbox permissions. The same operations were rerun with approved escalation and passed. This was an environment restriction, not a protocol failure. Final success was established from JSON check flags and point totals, not merely process exit status.

Actual level breakdown for both runs:

| Level | Area | Result |
|---|---|---:|
| 1 | Hello/USB | 5/5 |
| 2 | Wi-Fi link/takeover/telemetry default | 10/10 |
| 3 | Manual PWM | 5/5 |
| 4 | Profile upload | 10/10 |
| 5 | Player | 20/20 |
| 6 | Counters/power-loss test | 15/15 |
| 7 | Resilience | 20/20 |

### Decisions recorded

- Latest manual controls the wire contract; supplied source documents actual simulator behavior; HTML examples do not override either.
- Flutter remains the frontend, FastAPI the TCP bridge/coordinator, SQLite local persistent history.
- No substitute simulator, no new wire protocol, no firmware changes.
- Separate bench-reported totals from local session observations and disclose reboot/reset/connection uncertainty.
- Plan contains exact profile arithmetic, source validation, state/control rules, API contracts, database entities, per-screen behaviors, milestone gates, test scenarios, and demo procedure.
- Original reports remain historical research, with current documentation clearly overriding speculative ARM/watchdog/watermark/per-channel energized-time proposals.

### Documentation outputs

- `IMPLEMENTATION_PLAN.md`: authoritative current implementation specification.
- `IMPLEMENTATION_LOG.md`: this execution record and milestone tracker.
- `planning_evidence/`: unedited JSON outputs from the supplied scorer and evidence notes.
- `PROJECT_CONTEXT.md`, `SUPPLIED_ARTIFACTS.md`, and `athena/README.md`: refreshed pointers/status so a future compacted session does not think the simulator is still missing or start a replacement simulator.

### Not performed / limitations

- No application source, Flutter manifest, test source, firmware, or vendor-tool code was edited.
- No Athena integration test can be claimed: Athena has not been implemented.
- No real hardware, physical PWM timing, actuator safety limits, 16-channel firmware, or event network was verified.
- No 30-minute soak was run. The supplied scorer's own short resilience/timing checks did run.
- No Flutter build/analyze/test or backend installation was run during this documentation task. A prior Flutter version check was blocked by global SDK cache write permissions; address that normally when coding begins.
- Source findings such as the extra-F indexing risk were identified statically, not exercised destructively against hardware.

### Next action

Continue M1 under the user's implementation authorization. Keep M0 complete; do not build another simulator. Use the newest `handout_controller_teams` artifacts and rerun targeted checks when implementation changes justify them.

## Entry 002 — 25 September 2026 — New controller-team handout reconciliation and M1 start

### Authorization and timebox

The user authorized M0, then the next implementation phase, specified roughly four hours for a prototype and 12–15 hours for the full submission, and requested that the supplied HTML plus `mock.css` be treated as the exact UI target. The user then supplied `handout_controller_teams` and asked for it to be reviewed before continuing.

### New organizer inputs reviewed

- Six-page `WDR_Bench_User_Manual.pdf`, three-page `WDR_Controller_Guide.pdf`, newest frozen protocol PDF.
- Minimal Python and JavaScript clients stated to be tested on the physical bench.
- New 1,815-line `wdr_tool.py`, compared against the earlier 1,796-line root copy.

### Corrections and decisions

- Reference bench and newest simulator are four channels with `maxframes=8000`, not 2,000.
- A real committed profile is flash-persistent across a normal reboot. The supplied simulator still clears its profile on reboot; Athena must tolerate both and never auto-start.
- Protocol reply target remains one second; tested clients wait two seconds. Athena uses a two-second deadline and reconnect/reconciliation after timeout.
- Uploads are sequential round trips; the guide estimates about 13 ms/frame, making progress/cancellation/ETA necessary.
- Profile rates 10–100 are legal, but values above 50 produce at most 50 distinct servo pulses per second.
- The backend owns the single bench TCP connection and durable database; Flutter uses HTTP/WebSocket only.
- Explicit invalid-range rejection remains the safe default. Any later clipping option must be explicit and recorded.

### M1 work present

- Added FastAPI health/snapshot/live endpoints and static Flutter build fallback.
- Added SQLite schema version 1 with source, profile, bench, operation, session, counter epoch/snapshot, event and cycle-observation tables.
- Replaced the default Flutter counter page with Dashboard/Profile/History/Settings shell using the supplied visual tokens and honest empty states.
- Added typed Flutter HTTP/WebSocket service state; no fake bench values are emitted.
- Added pinned backend dependencies and ignored local runtime/virtual-environment data.

### Verification

- New handout tool: built-in simulator reports `proto=1 team=SIM ch=4 maxframes=8000` and passes 85/85 across all seven levels.
- FastAPI 0.118.0 and Uvicorn 0.37.0 import successfully from `.venv`.
- `.venv/bin/python -m unittest -v backend.test_app`: 3/3 pass, covering schema reopen/data retention, future-schema rejection, health, honest snapshot and first WebSocket snapshot.
- `flutter analyze`: no issues.
- `flutter test`: 2/2 widget tests pass, covering disconnected/disabled empty state and four-stage Profile navigation.
- `flutter build web --release`: succeeds; Wasm dry run also succeeds.
- Temporary 1440×900 golden render reviewed against the supplied CSS structure; header, four tiles, channel/control/trace columns and event card align with the target. The temporary capture/test were removed after review.
- `git diff --check`: clean before final documentation update.

### M1 result and next action

M1 acceptance gate is complete: health/snapshot work, the database reopens without loss, shell navigation works, no fake live values are shown, and a release web build is available. M2 is next: parse the supplied `RCOU.csv`, persist source/profile records, implement deterministic trim/map/resample compilation, and prove the 200-frame/SUM16 16982 fixture.

## Entry 003 — 25 September 2026 — M2 CSV import and profile compilation

### Changes made

- Added strict `TimeUS,C1…C16` CSV inspection with line-specific structural errors, per-channel invalid/zero counts, median interval, effective sample rate and detected gaps.
- Added exact integer-time zero-order-hold compilation, full selected-sample validation, mapping/limit checks, frame-capacity checks, immutable canonical JSON/SHA-256, SUM16, output ranges and loop-step diagnostics.
- Added source/profile HTTP import, list, detail, bounded preview and compiled CSV export endpoints. Original uploads and profile content persist in SQLite/managed files. Database schema migrated from version 1 to 2.
- Added Flutter Profile import, trim/rate controls, four-output mapping, source/compiled trace preview, checksum and CSV export, matching the supplied two-column layout. Recent source/profile state is restored after refresh.
- Chose the documented four-channel/8,000-frame reference capability only as an explicitly labeled offline draft target. M3 must compare live `INFO` before upload.

### Verification

- Backend `python -m unittest -v backend.test_app`: eight tests passed, covering the supplied 9,074-row log, the single gap, exact 200-frame golden output and SUM16 **16982**, persistent HTTP import/profile retrieval/export, invalid values, gap rejection, 30 fps timestamp choice, capacity boundaries and preview spike retention.
- `flutter analyze`: no issues. `flutter test`: 2/2 pass. `flutter build web --release`: success.
- New Flutter dependencies resolved: `file_picker` 9.2.3 and `url_launcher` 6.3.2.

### Remaining work

M3 owns the real TCP connection, capability reconciliation, serialized commands and upload. No Athena bench upload or physical PWM verification has occurred yet.

### Known handout discrepancy

The new manuals say `serve-sim` behaves like the real bench and that committed profiles survive power loss, but the supplied simulator's `_do_reboot` clears `profile` and `profile_len`. Real-firmware behavior takes precedence for product semantics; simulator behavior remains the integration-test expectation.

## Entry 004 — 25 September 2026 — Time-boxed USB prototype path

### Authorization and scope

The user prioritized an immediate prototype and chose USB control before Wi-Fi. The fixed ESP32 firmware was already connected to this Mac. This is a USB prototype slice of M3; it does not satisfy the final challenge's Wi-Fi transport requirement.

### Hardware evidence before implementation

- The USB device is `/dev/cu.usbserial-0001`. A read-only 115200-baud probe received `OK PONG`, `INFO proto=1 team=WDR_REFERENCE ch=4 maxframes=8000`, and `STATUS state=STOPPED ... us=1500,1500,1500,1500`.
- The real bench reported lifetime `cycles=21 run_s=24 active_s=23,23,23,6`. Those counters predate Athena and must not be cleared or presented as new prototype output.
- No profile upload, `START`, or physical PWM motion was performed during this verification. The board had a pre-existing 100-frame profile.
- A later read-only `UsbBench.connect()` check reached the physical board and returned the same counters and STOPPED state. It also observed `EVT BOOT` and `up=1`: opening this Mac's USB serial port appears to reset the ESP32 despite pre-setting DTR/RTS low. The committed 100-frame profile and lifetime counters survived. Connect only when an automatic stop/reset is acceptable; do not use reconnection as a running-session recovery mechanism until this is resolved.

### Changes made

- Added `UsbBench`, a serialized WDR v1 command transport using pyserial at 115200 baud. It avoids deliberate DTR/RTS reset, ignores debug text, captures events, reads live `INFO`/`STATUS`/`COUNTERS`, checks channel count, frame limit, pulse range and SUM16, and uploads only a fully compiled stored profile. It refuses `START` until this backend session has verified an upload; start always has a finite target.
- Added local USB connect/disconnect, upload, start/pause/resume/stop API endpoints. `CLEAR` is intentionally not exposed.
- Wired Settings to the Mac's USB port, Profile to upload, and Dashboard to bench state, lifetime counters, per-channel active hours, finite-cycle controls and recent events. The browser polls authoritative bench snapshots every second.
- Added `pyserial==3.5` to backend requirements and updated the local run instructions.

### Verification and remaining work

- Protocol fake-serial tests cover interleaved events/debug text, ordered frame upload, checksum gating and finite start. Backend suite: 10/10 pass. Flutter widget tests: 2/2 pass. `flutter analyze`: no issues. `flutter build web`: success.
- The new Athena USB connection/read path was exercised against the physical ESP32; upload/playback has not. A physical run requires the user to verify separate 5–6 V servo power, common ground and mechanical clearance, then explicitly click the upload/start controls. The current backend stores neither run history nor counter snapshots; it only displays current board totals.
- Wi-Fi can be addressed after this prototype. The supplied firmware is fixed to the event network and WDR v1 exposes no runtime SSID/password command. The Mac can join the board's network, or an access point can use the configured credentials, without changing firmware.

## Entry 005 — 25 September 2026 — Independent PWM receiver programmed

### Device identification

- The fixed WDR bench remains `/dev/cu.usbserial-0001`, CP2102 VID:PID `10c4:ea60`, USB serial `0001`. Athena previously received `team=WDR_REFERENCE` from this port. No esptool command or flash upload was directed to it.
- The newly attached device is `/dev/cu.usbserial-10`, CH340 VID:PID `1a86:7523`. Espressif esptool queried **only this port** and reported `ESP32-D0WD-V3`, a classic ESP32, despite the initial description as an ESP32-S3. The user authorized programming the verified new device. Device identity and wiring are recorded in `pwm_receiver/README.md`.

### Receiver firmware and verification

- Added `pwm_receiver/pwm_receiver.ino`. It captures rising/falling edges on four GPIO inputs, reports each output's HIGH width, full period and pulse count every 250 ms at 115200 baud, and labels a channel `NO SIGNAL` after 100 ms without a pulse. It does not drive an output or communicate with the WDR bench.
- Compiled with the installed Arduino ESP32 core 3.3.12 for `esp32:esp32:esp32`. The bundled Arduino ctags executable is x86-only on this Apple Silicon Mac, so the build used a temporary no-prototype ctags shim; this sketch defines all functions before use. The compiled image identified as classic ESP32.
- The first upload to the receiver at 921600 baud failed before flash verification. Retrying the **same `/dev/cu.usbserial-10` device** at 115200 baud succeeded, with esptool hash verification. A small timestamp-label correction was recompiled and verified by a second upload.
- Readback of the receiver's own serial output showed `t=9251ms | OUT0 NO SIGNAL | OUT1 NO SIGNAL | OUT2 NO SIGNAL | OUT3 NO SIGNAL`, as expected before connecting the signal wires. No physical PWM measurement has yet been made.
- The observed classic ESP32 receiver uses inputs GPIO32, GPIO33, GPIO34 and GPIO35, not the previously suggested S3 GPIO4–7. On a classic ESP32, GPIO6/7 are flash pins and must not be connected as receiver inputs.

### Next physical step

With USB unplugged, wire bench OUT0 GPIO25 → receiver GPIO32, OUT1 GPIO26 → receiver GPIO33, OUT2 GPIO27 → receiver GPIO34, OUT3 GPIO33 → receiver GPIO35, and GND → GND. Reconnect both USB cables to the Mac. Do not join 3V3/5V rails or attach servos for the first signal-only check. Open `/dev/cu.usbserial-10` at 115200 in a terminal; keep Athena on `/dev/cu.usbserial-0001`. Verify idle near 1500 µs HIGH and ~20,000 µs period, then replay one finite profile cycle.

## Entry 006 — 25 September 2026 — Four physical PWM paths verified without profile loss

- Both boards were powered from separate Mac USB ports, with four signal jumpers and one ground jumper; no servos were attached.
- Read-only receiver output at bench idle showed OUT0–OUT3 around `1499–1500us/20000us`, with pulse counts increasing.
- The proposed flight-profile upload was stopped before execution when the user asked what it would replace. A read-only `STATUS` confirmed the original 100-frame profile and all lifetime counters were still present.
- With the user's explicit no-loss constraint, sent only `SET 0 1100`, `SET 1 1300`, `SET 2 1700`, `SET 3 1900`, then `STOP`. The independent receiver measured `1100,1297,1694,1891` µs respectively, each with a 20,000 µs period. After STOP, all live outputs were 1500 µs, profile length remained 100, and counters remained `cycles=21 run_s=24 active_s=23,23,23,6`.
- Replaced an unexecuted upload-and-replay demo script with `pwm_receiver/check_pwm.py`, which performs only the reversible `SET`/`STOP` check with port-identity guards. No `LOAD`, `COMMIT`, `START`, `CLEAR`, or firmware flash occurred during this check.
- A full log-profile replay would replace the bench's committed profile because WDR v1 has no readback command. It remains unperformed pending the user's decision about that loss.

## Entry 007 — 25 September 2026 — Supplied simulator becomes the primary prototype demo

### Reason and scope

The supplied `serve-sim` process already exposes WDR v1 over local TCP. It supports a full log-to-profile-to-replay demonstration without replacing the real bench's existing 100-frame profile. The two-ESP wiring remains an optional, independent proof of physical PWM output.

### Changes made

- Added a loopback-only TCP transport to the existing serialized WDR controller. It checks the live `INFO` response for `team=SIM` and reuses the same upload, checksum and finite-cycle control code as USB.
- Added simulator connect and general disconnect API routes, plus **Connect local simulator** in Flutter Settings. Profile upload names the active target, and Dashboard identifies simulator versus USB.
- Made `PROTOTYPE_DEMO.md` a simulator-first two-minute runbook and documented how to start both local services.

### Verification

- Started the organizer's actual `handout_controller_teams/wdr_tool.py serve-sim` on isolated loopback ports 43333/43334 and an isolated temporary counter directory.
- Exercised Athena's API end to end against that simulator: imported supplied `RCOU.csv`, compiled C1–C4 from 40–44 s at 50 Hz, produced 200 frames/SUM16 **16982**, uploaded and checksum-verified the profile, then started one finite cycle. Simulator reported STOPPED with `cycles=1 run_s=4 active_s=4,4,4,4` on the fresh instance.
- Backend unit tests: 10/10 pass. Flutter widget tests: 2/2 pass. `flutter analyze`: no issues. `flutter build web`: success. Neither physical ESP32 was contacted during this integration test.

### Limits

The simulator proves protocol and app integration, not electrical output or actual servo wear. The earlier independent receiver check supplies the separate four-channel PWM evidence. Real Wi-Fi control, 16-channel hardware, durable per-run history and real-bench replay of this compiled profile remain outside this prototype slice. The original real-bench profile and counters were preserved.

## Entry 008 — 26 September 2026 — Remove repeated live reconnect warning

- The Flutter app opened a WebSocket that received only one initial snapshot; the backend then waited for client text while the dashboard separately polled `/api/v1/snapshot` every second. When the idle socket closed, the UI showed “Live updates disconnected. Reconnecting…” even though snapshot polling could still be healthy.
- Removed the redundant WebSocket connection from Flutter state. The existing one-second HTTP snapshot polling remains the live dashboard source, including simulator state and counters. A transient polling error now clears after the next successful snapshot.
- `flutter analyze`: no issues; `flutter test`: 2/2 pass; `flutter build web`: success. The backend WebSocket endpoint is unchanged. No ESP32, simulator, or saved profile was touched.

## Entry 009 — 26 September 2026 — Six-hour finish slice: real flight segment, durable history, live trace

- Added `SIX_HOUR_FINISH_PLAN.md` to prioritize backend reliability, authoritative accounting and the live dashboard under the remaining time. The competition brief calls for live pulse widths and trace preview; the sample dashboard also depicts a live graph. The graph is labeled as sampled command output, not mechanical or oscilloscope feedback.
- Used the **unmodified** supplied `RCOU.csv` from 40–100 s at 50 frames/s. It deterministically compiles to **3,000 frames**, **60 seconds per cycle**, **SUM16 23174**. The Flutter sample preset selects this window; the earlier 4-second fixture remains available.
- Added protocol-capability validation, configurable WDR TCP host/port for venue Wi-Fi, TCP_NODELAY, automatic acknowledged `TIME`, and stopped-only manual `SET`. The real bench was not contacted, uploaded to, cleared or reflashed.
- Persisted bench-reported counter snapshots, counter epochs, sessions and events in SQLite. An unfinished session becomes UNCONFIRMED after link loss or backend restart; new observations reconcile it without sending START. Added session/event APIs with UTC date-range filtering.
- Added up to 180 recent sampled `STATUS` pulse readings to snapshots and a Flutter live trace, finite-cycle target input, progress display, shared bench hours and per-output active hours, basic saved History view, and Wi-Fi host control. A 16-channel INFO can now size the profile mapping UI; physical 16-channel operation remains unverified.
- Against the organizer's actual TCP simulator, Athena uploaded the 3,000-frame profile in approximately **0.11 s** on local loopback. A six-second partial run produced changing live pulses, seven trace samples and a durable manually stopped session. A full one-minute run completed with a **+1 cycle**, **+60 run_s**, **+32,+59,+56,+60 active_s** and 61 trace samples; the saved session was COMPLETED with matching deltas. Both used isolated temporary Athena data and did not touch either ESP32.
- Backend suite: 16 tests passed after history, time-sync, manual-control, simulator-only reset and TCP reconnect additions. Flutter analysis: no issues; Flutter widget tests: 3 passed; Flutter web release build succeeded. A 1440×900 headless Chrome screenshot verified the built app's disconnected dashboard layout and the server's static/API routes. The connected live-graph browser walkthrough and venue Wi-Fi hardware test remain outstanding.
- Added bounded automatic reconnection for a previously connected simulator/Wi-Fi TCP bench. It reads INFO/STATUS/COUNTERS/TIME only; it does not re-upload or send START. Explicit disconnect cancels retries. USB remains manual to avoid the observed reset-on-open behavior. The 4-second official-simulator API smoke test passed again after this change.
- Added a confirmed simulator-only counter reset. The backend refuses CLEAR for USB and physical Wi-Fi benches, preserving the reference bench's pre-existing lifetime totals. The reset was exercised only against a fake transport in a unit test; no real or supplied-simulator counters were cleared during this entry.

## Entry 010 — 26 September 2026 — Browser replay and export check

- Added a History **Export CSV** button and `/api/v1/history/export.csv`, applying the same inclusive UTC date-range filter as the list. Export contains all matching session and event records, labeled counter deltas in seconds, a JSON array of per-channel active seconds, confidence, and event details. User-provided text is escaped to avoid spreadsheet formula execution. A backend route test checks rows and filtering.
- Visually inspected the built Flutter dashboard in headless Chrome while a 3,000-frame official-simulator replay was RUNNING. The 1440×900 capture showed bench connection, 23% current-cycle progress, four distinct live pulse widths, lifetime and per-channel hours, and a four-line sampled pulse graph. This is browser/rendering evidence, not physical PWM measurement.
- The replay finished automatically; the saved session was COMPLETED with **+1 cycle, +60 running seconds, +32,+60,+56,+60 per-channel active seconds**. A real HTTP CSV download returned that session and four events. The one-second difference from the earlier OUT1 active delta reflects observation boundaries; bench counters remain the authority.
- Backend suite: 17 tests passed. Flutter analysis: no issues; widget tests: 3 passed; web release build succeeded. All this work used a local simulator and isolated temporary Athena data. The physical USB reference bench and receiver were not contacted. Venue Wi-Fi remains unverified because its address/network are not yet available.

## Entry 011 — 26 September 2026 — Persisted History details and per-channel hours

- Implemented a saved session-detail API exposing the persisted bench identity/capabilities, source/profile IDs and hashes, source window, per-output mapping and pulse limits, checksum, cycle target, observation receive-time bounds, recorded stop cause, individual lifetime counter observations, and associated session events. It excludes profile frame arrays from the detail response. A missing profile/source is shown as unknown rather than borrowed from the current dashboard.
- A session with fewer than two saved counter observations now has an unknown delta instead of a misleading zero. Detail responses flag link loss and counter-epoch changes; the History UI warns that intermediate events are unknown during a disconnect even when later bench totals bracket the gap.
- Replaced the minimal History rows with expandable session details, a per-channel active-hours chart summing known deltas for the loaded sessions, a channel selector that filters the chart/mappings/observations, and a structured events table. UTC date filtering and CSV download remain. The CSV now also carries source/profile provenance, stop cause, observation count and link-gap status, while retaining explicit seconds units and formula-safe text cells.
- Backend suite: 19 tests passed, including saved-profile provenance, single-observation unknown delta, disconnect uncertainty, counter-epoch reset uncertainty, details/CSV, and date filtering. Flutter analysis and five widget tests pass, including chart values, detail expansion, channel filtering, and explicit unknown/uncertain displays after disconnect. The Flutter web release build succeeds. A separate isolated API replay using the **supplied simulator** compiled the unmodified 40–44 s `RCOU.csv` window (200 frames, SUM16 16982), completed one cycle, and returned a COMPLETED session with **+1 cycle, +4 run_s, +4 active_s on each output**, nine saved observations and five CSV rows. No physical device was contacted by this test.
- The user separately confirmed Athena reached the reference bench over Wi-Fi at `10.178.45.105:3333` and received `proto=1`, `team=WDR_REFERENCE`, `ch=4`, `maxframes=8000`, plus a TIME acknowledgement. This is user-reported connection evidence only; no profile upload, START or counter CLEAR was performed. Physical Wi-Fi replay remains unverified.

## Entry 012 — 26 September 2026 — Preserve the pre-existing reference profile through replay

- The user asked whether the bench's original 100-frame profile could be replayed and stored. WDR v1 has no direct readback command; the existing receiver sketch reports only every 250 ms and cannot preserve each frame. Added `scripts/capture_existing_profile.py` to sample Wi-Fi `STATUS` frame index/pulse widths during finite `START 1` runs. It refuses unexpected protocol/team/channel/frame count or an already running bench. It sends no `LOAD`, `F`, `COMMIT`, `CLEAR`, firmware flash, or USB command. The receiver and reference board firmware were not changed.
- First tested on the **supplied simulator** with a known 100-frame, 50 Hz profile. One finite run captured all indices and the saved CSV matched all 400 original pulse values exactly. A frame-index/time fit estimated 49.98 Hz on the simulator.
- The user confirmed only the four signal wires and common ground were attached to the independent receiver ESP32, with no servos, and that Athena's backend/dashboard were off. A read-only Wi-Fi preflight of `10.178.45.105:3333` reported `proto=1`, `team=WDR_REFERENCE`, four channels, 8,000-frame capacity, STOPPED, 100 committed frames, and lifetime counters `cycles=21 run_s=24 active_s=23,23,23,6`.
- Three finite replays of the **existing** real-bench profile observed all 100 frame indices with no conflicting values. All 100 frames report `OUT0–3 = 1100,1300,1700,1900` µs. [Capture artifacts](captures/reference_100frame_20260926/) include raw STATUS lines (271 observations), a manifest, frame CSV, and an Athena-compatible approximate TimeUS source. A linear fit estimated 50.06 Hz, so the import file uses 50 Hz. Athena's compiler reproduced the same 100 frames and computed SUM16 **10176** from the captured widths; the original uploaded checksum/source/labels remain unknown. The bench stopped normally with the original 100-frame profile still committed. Its authoritative lifetime counters advanced to `cycles=24 run_s=30 active_s=29,29,29,12`. This captures bench-reported commanded widths, not independent physical PWM measurements.

## Entry 013 — 26 September 2026 — Physical Wi-Fi flight-profile replay with receiver evidence

- The user reconnected both USB boards and confirmed only four signal wires plus common ground between the WDR and receiver ESP32s, with no servos. Device enumeration identified the WDR CP2102 as `/dev/cu.usbserial-0001` (serial `0001`) and the independent CH340 receiver as `/dev/cu.usbserial-10`. Opened **only the receiver** serial port; all four idle inputs measured 1499–1500 µs at a 19,999–20,000 µs period. Neither board was flashed and the WDR USB port was not opened.
- A read-only Wi-Fi preflight at `10.178.45.105:3333` found WDR protocol 1, `team=WDR_REFERENCE`, four channels, 8,000-frame capacity, STOPPED, the archived 100-frame profile, and `cycles=24 run_s=30 active_s=29,29,29,12`.
- Ran Athena's actual API with its persistent local SQLite data: imported the unmodified supplied `RCOU.csv`, compiled C1–C4 over 40–44 seconds at 50 Hz to **200 frames / SUM16 16982**, uploaded over Wi-Fi, and confirmed STOPPED with `frames=200` before sending a finite `START 1`. This replaced the archived 100-frame profile by the user's accepted decision. No `CLEAR` or firmware update was sent.
- The physical bench automatically completed after four seconds. Athena saved a COMPLETED session with **+1 cycle, +4 run_s, +4 active_s on each output**. Authoritative lifetime counters advanced to `cycles=25 run_s=34 active_s=33,33,33,16`. Seventeen Athena STATUS samples showed changing commanded pulse values. The separate receiver logged 21 valid four-channel samples during the run; 16 active samples had periods 19,999–20,000 µs and each channel's measured widths were within 2, 3, 7, and 7 µs respectively of a value in the uploaded profile. This nearest-value check establishes compatible physical output ranges, not frame-perfect time alignment.
- [Saved run evidence](captures/real_wifi_flight_20260926.json) includes bench INFO, before/after counters, compiled profile summary/hash, sampled status, persisted session/detail and raw/parsed receiver readings. A separate read-only Wi-Fi check after disconnect confirmed STOPPED at idle with the 200-frame profile still committed and counters unchanged from the completed run. The user's in-progress edits to `athena/lib/main.dart` and `athena/lib/theme.dart` were left untouched.

## Entry 014 — 26 September 2026 — Dark dashboard and rising tile hover

- Saved and pushed the user's existing `main.dart` and `theme.dart` edits first as commit `e1fb600`, leaving `IMPLEMENTATION_PLAN.md.zip` untouched.
- Restyled the Flutter web dashboard with a near-black background, squared dark panels, high-contrast white text, a yellow ATHENA title and yellow primary controls. The header now adapts to narrower windows. Profile import and error panels were updated to remain legible in the dark palette.
- Added a bottom-up white reveal to the four read-only dashboard metric tiles. Each tile shows a dark-text copy of its content over the rising panel on hover; other tiles remain dark. The animation reverses on pointer exit and excludes the overlay copy from accessibility semantics.
- Flutter analysis reported no issues; seven widget tests passed, including mouse enter/exit reveal behavior and compact-header layout. The release web build succeeded. A 1440×900 local browser screenshot confirmed the dashboard layout and contrast while the backend was offline. No bench was contacted or modified for this styling work.

## Entry 015 — 26 September 2026 — Double-click Mac demo launchers

- Added executable `Start Simulator Demo.command` and `Start Wi-Fi Hardware Proof.command`, backed by `scripts/demo_launcher.py`. Both check prerequisites/occupied ports, start Athena locally, open its browser page, show where logs are saved, and stop only their own child processes on exit.
- The simulator launcher also starts the supplied WDR simulator and connects Athena to the verified `team=SIM` service. The hardware launcher detects the CH340 receiver USB identity and streams only its serial PWM measurements; the WDR may use an external USB power supply. Wi-Fi connection, profile upload, and finite START remain explicit Athena UI actions. Neither launcher flashes firmware or clears counters.
- Updated `PROTOTYPE_DEMO.md` with double-click instructions and close keys. Shell syntax and Python compilation checks passed. A simulator smoke run started both services, connected to SIM, passed backend health, and shut down cleanly. A hardware-mode smoke run identified `/dev/cu.usbserial-10`, started/stopped Athena, and did not open the WDR bench or start a replay. The interactive receiver monitor and browser-open step were not exercised in the smoke check.

## Entry 016 — 26 September 2026 — Diagnose disabled Start after real Wi-Fi upload

- Read the running Athena backend and inspected the user's current dashboard without sending bench controls. The live snapshot showed `WDR_REFERENCE` connected over Wi-Fi, STOPPED, a committed **2,500-frame** profile, and unchanged lifetime counters `cycles=25 run_s=34 active_s=33,33,33,16`. The browser later visibly showed **Start 1 cycle enabled**. The grey state occurred while upload was still in progress; no replay was initiated in this investigation.
- The backend log also showed repeated upload POSTs and a transient 500 from simultaneous use of its shared SQLite connection. Added frontend guards against duplicate bench operations and repeat upload clicks, a nonblocking server-side upload lock that returns 409 for a concurrent upload, and serialized recording/summary reads on the recorder lock.
- Backend suite: 19 tests passed, including concurrent-upload rejection. Flutter analysis: no issues; eight widget/unit tests passed, including a pending-upload duplicate-operation check. The Flutter web release build succeeded. The currently running backend was **not restarted**, because that would discard its in-memory uploaded-profile association and require another upload before Start; the fixes apply on the next launcher start.

## Entry 017 — 26 September 2026 — Verify persisted 2,500-frame real-bench replay

- Re-examined Athena's persistent SQLite history after initially reporting that the 2,500-frame profile had only been uploaded. The physical `WDR_REFERENCE` bench at `10.178.45.105:3333` has a **COMPLETED**, one-cycle session for profile `f18819b3-df2d-4f9a-9040-2ef425115537` (2,500 frames, 50 Hz, SUM16 2518). The session ran from `2026-09-26T01:16:03.898+00:00` to `01:16:54.073+00:00` and records `cycle_complete` and `cycle_target_reached` as observed events.
- Saved bench counter observations for that session rose from `cycles=25 run_s=34 active_s=33,33,33,16` to `cycles=26 run_s=84 active_s=61,82,79,65`: **+1 cycle, +50 running seconds, +28,+49,+46,+49 active seconds**. These are bench-reported counters, not independently measured servo motion. No receiver capture from this exact 2,500-frame run was found; the independent receiver evidence in Entry 013 is for the earlier 200-frame profile.
- A fresh read-only Wi-Fi preflight found the bench STOPPED with **3,000 frames** and `cycles=27 run_s=144 active_s=93,142,135,125`. A separate persisted session shows the 3,000-frame profile also completed one cycle. The preflight refused a requested 2,500-frame replay because the bench's committed profile had changed. The receiver USB monitor was read-only and still reported all four idle PWM inputs near 1500 µs at a 20,000 µs period. No START, upload, STOP, CLEAR, or firmware change was sent during this verification.

## Entry 018 — 26 September 2026 — Windows receiver monitor instructions

- Added `pwm_receiver/WINDOWS_MONITOR.md` for the already-programmed receiver attached to a Windows laptop, with Python/pySerial setup, CH340 COM-port identification, 115200-baud monitoring, expected readings, exit keys and wiring. Linked it from the receiver README and demo guide.
- Documented the separate Mac backend startup because the hardware launcher requires a local Mac receiver. Explicitly recorded that backend restart requires another verified upload before Start, that upload replaces the bench's committed profile, and that quitting the receiver monitor does not stop replay. Updated the demo guide's historical counter/profile wording to include the later persisted 50/60-second physical sessions.
- Reviewed commands against the existing launcher/backend behavior and the official pySerial documentation. These instructions have not been executed on the user's Windows laptop; no Windows compatibility test, firmware change, bench command or new replay occurred in this documentation step.

## Entry 019 — 26 September 2026 — Visible upload progress and fresh local History

- Added an upload-specific AppState flag and a visible `Uploading profile…` banner with indeterminate progress above every tab. The Profile upload button displays a spinner and `Uploading…` until its upload future finishes. Existing duplicate-operation guards remain; progress clears on confirmation or failure, and failures retain the error message. No invented percentage or elapsed-duration claim is shown.
- Flutter analysis reported no issues; all ten Flutter tests passed, including duplicate-upload guarding, upload-banner visibility while switching tabs, and progress cleanup after failure. The optimized release web build succeeded. No physical upload was performed to test the indicator; tests use a pending fake API response.
- At the user's explicit request, stopped the local backend while the real bench was already STOPPED. Created and integrity-checked a complete SQLite backup at `var/backups/athena-before-history-clear-20260926T023209Z.sqlite3`, then cleared only local history tables in one foreign-key-checked transaction: seven sessions, 40 events, 3,012 counter snapshots and two counter epochs (operation/cycle-observation tables were empty). Kept four source logs, six compiled profiles and two bench identity records. The ignored backup stays on this Mac and is not part of Git.
- Restarted Athena and reconnected over Wi-Fi with no upload, START, STOP, CLEAR or firmware change. The snapshot confirmed History has zero sessions/events, the 3,000-frame bench profile remains STOPPED, and hardware counters are unchanged at `cycles=29 run_s=208 active_s=129,205,195,189`. New bench observations may now accumulate locally. Backend restart requires a fresh verified upload before another Athena START.

## Entry 020 — 26 September 2026 — Silent Windows monitor: verify receiver after return to Mac

- The user reported a miniterm heading on Windows COM3 with no receiver lines, then connected both boards to the Mac for diagnosis. Fresh enumeration identified the CH340 receiver as `/dev/cu.usbserial-110` (`1a86:7523`) and the WDR CP2102 bench as `/dev/cu.usbserial-0001` (`10c4:ea60`, serial `0001`). The receiver port had changed from its earlier Mac name.
- Opened only the verified receiver at 115200 baud, with DTR/RTS unasserted and no serial commands written. A six-second read returned 38 lines including ESP32 boot text, the intact `WDR PWM receiver` firmware banner and periodic measurements on all four inputs. HIGH widths were 1499–1500 µs and periods 19,999–20,000 µs. This verifies receiver firmware, USB readout and idle PWM wiring on the Mac; the specific Windows failure remains unconfirmed, so no definitive driver/COM/reset cause is claimed.
- Athena was running but disconnected. A read-only Wi-Fi check reached `WDR_REFERENCE` at `10.178.45.105:3333`, now STOPPED with 660 committed frames and counters `cycles=32 run_s=307 active_s=194,305,287,289`. Its low reported uptime indicated a recent restart. The expected-3,000-frame check rejected the changed profile; no replay was attempted. Reconnected Athena through its normal Wi-Fi API. Neither firmware was flashed, the bench USB port was not opened, and no upload, START, STOP or counter CLEAR was sent.
- Updated receiver documentation with the new observed Mac port and explicit unasserted DTR/RTS monitor settings, plus the distinction between the laptop's miniterm heading and receiver output. Windows instructions have not been re-tested on Windows.

## Entry 021 — 26 September 2026 — R1 backend-owned monitoring

- Saved the previously verified upload indicator/receiver diagnostics and `RESILIENCE_IMPLEMENTATION_PLAN.md` in checkpoint commit `6f8b5b8`. The plan covers monitoring, stale UI, identity/reboot recovery, interrupted commands, gap accounting, measured upload progress, draft restoration, Windows receiver launcher and simulator/hardware validation.
- Added a lifespan-managed one-second backend monitor. Snapshot requests return cached bench observations without network polling; bench mutations and monitoring share a serialized I/O lock, with busy mutations rejected instead of queued. A separate synchronized SQLite HistoryRecorder connection avoids background recording inside profile-import transactions. Startup remains disconnected; shutdown ends the worker without commanding a bench stop.
- All 21 backend tests passed, including recording completion without browser requests and nonblocking snapshots while another thread holds bench I/O. `scripts/verify_resilience.py` ran the supplied official SimDevice/socket bridge on an isolated loopback port and temporary database: the 200-frame supplied-log profile completed with no snapshot requests, persisted COMPLETED with +1 cycle/+4 run_s, and only one START was sent. Evidence: `/private/tmp/athena-resilience-r1/results.json`. No real bench was connected or changed; the running demo backend has not yet been replaced.

## Entry 022 — 26 September 2026 — R2 stale state and retry feedback

- Added last successful bench receive time, observation age, retry count/delay and separate last-known data to cached snapshots. Retry delays increase approximately 1/2/4/8 seconds with jitter and cap at ten seconds. Explicit disconnect removes the retry target.
- Flutter now labels stale/disconnected observations, warns that the bench may still be running, labels old traces, and disables Start/Pause/Resume/manual SET/upload when readings are stale. Browser snapshot requests time out after five seconds; browser-to-backend failure is distinguished from a bench reconnect. A connected Stop remains available as an explicit attempt.
- All 22 backend tests and 11 Flutter tests passed, including capped retry scheduling and stale observations not enabling Start. No physical connection, upload or replay was used for these checks. The previous demo backend remains running with the old release until final activation.

## Entry 023 — 26 September 2026 — R3 recovery identity and reboot observation

- Explicit connections now pin protocol/team/channel count/frame capacity for recovery. A changed capability set blocks automatic recovery, records an identity-mismatch event, and requires deliberate reconnection. Recovery still sends only connection/observation/time-sync commands; matching frame count does not restore verified profile identity.
- An observed uptime decrease records a reboot, invalidates upload verification and ends an affected open session as REBOOT_OBSERVED with uncertain exact stop time. The UI exposes the reboot/recovery warning. WDR v1 still cannot uniquely identify a physical board or prove an unchanged profile after takeover; a reboot whose uptime has already exceeded the prior observation may also be undetectable.
- All 24 backend tests passed, including changed-capacity rejection and reboot-session uncertainty. These were controlled fake-transport checks; full supplied-simulator fault scenarios remain in R9. No real bench command or firmware change was performed.

## Entry 024 — 26 September 2026 — R4 interrupted commands

- Persist Start requests and bench counter baselines before transmitting START. Lost acknowledgements are reported as unconfirmed and never automatically retried; completion requires new lifetime-cycle evidence, not the previous run's cycle index. Rejected Starts and failed Stop/Pause/Resume outcomes are recorded explicitly. Interrupted uploads invalidate local verification; changed reported frame counts invalidate it too.
- All 26 backend tests passed. Supplied-simulator integration verified completion without browser polling, a deliberately lost START acknowledgement reconciled to +1 cycle, and an interrupted frame upload that could not enable Start. Command counts show no automatic START retry. Evidence: `/private/tmp/athena-resilience-r1/results.json`. Lost STOP acknowledgement coverage remains pending in R9. No physical commands were sent.

## Entry 025 — 26 September 2026 — paused resilience checkpoint

- User redirected work to independent receiver feedback, stale/power-loss display and explicit recovery approval. Preserve current resilience work as a WIP checkpoint; it is not a claim of completed hardware validation.
- Last established functional prototype checkpoint: `6f8b5b8` (before background-monitor resilience phases); earlier published prototype: `177aaf7`. Preserve these commits and create a rollback branch. Do not reset/delete the working tree or firmware to demonstrate rollback.
- Current checks before interruption: 30 backend tests, 14 Flutter tests passed; shorter supplied-simulator fault integration passed (upload progress, browser absence, lost START/STOP replies, interrupted upload, gap recovery). Ten-minute simulator test and final release checks were running; results must be inspected before claiming success. R5–R8 code is saved, native Windows launcher execution unverified. No physical upload/start/clear/flash performed.

## Entry 026 — 26 September 2026 — independent signal feedback and approved power recovery

- User put other improvements aside to fix misleading command-only graphs, detect pulled PWM signal wires, remove stale graphs after bench power loss and require approval on return. Saved paused work in `dee4d7f`; created `prototype-rollback-20260926` at functional prototype `6f8b5b8`. No reset/deletion was used to prove rollback; the original untracked ZIP remains untouched.
- Added independent CH340 receiver reads at 115200 with DTR/RTS unasserted and strict USB VID/PID selection. The CP2102 bench adapter is refused. Added an authenticated, receiver-only Windows measurement bridge as an optional alternative. Receiver NO SIGNAL produces null widths and graph gaps; stale/unavailable feedback becomes UNKNOWN. All missing signals remove the measured graph. Commanded PWM is separately labeled and hidden when bench observations are not live. Channel table labels command widths explicitly.
- During a known active run, observed bench reboot/profile loss offers review, restart approval or keep stopped. Only explicit approval re-uploads the saved immutable profile, checks COMMIT and starts a new finite session. WDR v1 cannot seek to an exact frame: interrupted cycles restart at frame 0. Remaining cycles use recovered lifetime observations with checkpoint uncertainty disclosed. Duplicate approval is refused and a lost Start reply cannot offer another blind Start. Recovery context currently requires the same backend process; changed capabilities block recovery and changed IP requires manual connection.
- Checks: 33 backend tests and 19 Flutter tests passed, Flutter analyze clean; release web build passed. Initial widget checks exposed a missing Material ancestor and dialog-controller disposal issue; both were fixed before the passing run. Supplied-simulator integration power-cycled during playback, verified no automatic LOAD/START, approved restart, completed a separate session and rejected duplicate approval. Evidence: `/private/tmp/athena-resilience-r1/results.json`. The earlier interrupted ten-minute outage test also finished successfully: 600 s link loss, +1 cycle/+4 running seconds after recovery, no automatic control replay; this is simulator evidence only.
- Activated backend on local port 8080 after finding no previous backend there. Receiver-only connection opened `/dev/cu.usbserial-10` (CH340 1a86:7523); independent physical readings were fresh, all four channels 1499–1500 us HIGH / 20,000 us period. The WDR USB port was not opened and no physical upload, Start, Stop, Clear or firmware change was sent. Actual jumper-removal/power-cut rehearsal remains user-operated, not yet observed here. Native Windows bridge execution also remains unverified.
- Added `PHYSICAL_FEEDBACK_AND_RECOVERY.md` with startup, wiring, physical demo expectations, approval limits and rollback references. Mac hardware launcher now lets the backend own receiver serial and displays its measurements, avoiding two serial readers.

## Entry 027 — 26 September 2026 — preparing four real actuators

- User reports the hardware team is connecting four actual motors/actuators to the bench outputs. Treat this as a transition from signal-only testing to loaded hardware; previous signal-only motion authorization does not establish model-specific compatibility.
- Added `ACTUATOR_BRINGUP.md`: device/driver/power/limit questions, output-to-receiver/actuator signal mapping, independent supply/common ground, initial finite test sequence, actual STOP=1500 us behavior, recovery approval and measurement coverage limits. Asked for device models/type and supply ratings before model-specific profile settings or motion.
- No code/firmware changes, bench commands, upload, replay, reset or counter clear were performed. Loaded operation remains unverified. The receiver detects loss at its input; it cannot detect a separate actuator branch being unplugged while its own signal remains present.

## Entry 028 — 26 September 2026 — drone motor clarification

- User confirms drone motors; exact ESCs, supply and signal compatibility remain unknown. Asked the hardware team for ESC model, ordinary 50-Hz PWM support and the meaning of 1500 us.
- Updated bring-up notes with the fixed-firmware compatibility gate: boot/STOP/completion idle is 1500 us and upload sends STOP, whereas typical unidirectional PWM ESCs use roughly 1000–2000 us for zero–full throttle. A frontend Stop change would not fix all firmware states. Confirmed common behavior against primary ArduPilot PWM/ESC documentation linked in the bring-up file; no model-specific assumptions made.
- No motor commands, firmware change, ESC calibration or playback performed. Model-specific motion remains pending compatibility confirmation.

## Entry 029 — 26 September 2026 — tentative Readytosky 40A identification

- User suggests Readytosky 40A. Checked manufacturer product pages: both 2–4S/5V3A-BEC and 2–6S OPTO/no-BEC variants exist. Exact variant, zero/arming pulse and 3.3-V compatibility remain unconfirmed; added primary-source links and unresolved details to `ACTUATOR_BRINGUP.md`.
- No software changes, firmware changes, calibration or motor commands. A tentative brand/current rating does not resolve WDR's 1500-us idle/STOP/completion mismatch.

## Future entry template

Copy this structure for each implementation session; do not fill it with unperformed work:

```text
Entry NNN — date/time — milestone/summary
Authorization/scope:
Changes made:
Protocol or design decisions changed (and why):
Checks executed (exact commands and outputs/evidence):
Result: passed / failed / partial / not tested
Known issues and limitations:
Milestone status changes:
Next concrete action:
```

Use statuses Not started / In progress / Blocked / Complete for milestones. A complete milestone requires its acceptance gate, not just committed code. Record test failures and corrections even when a later rerun passes. Distinguish application tests from vendor-simulator tests and simulator evidence from hardware evidence.
