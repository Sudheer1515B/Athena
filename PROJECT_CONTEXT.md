# Athena Project Context

This file is the compact-proof handoff for the Welkinrim Technologies hackathon project. Read it before continuing work.

**Current source of implementation decisions:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). **Actual progress/evidence:** [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md). These supersede earlier speculative research. Application implementation is authorized and underway.

## Problem statement

> Build a web-based controller that converts recorded drone flight logs into servo command profiles, replays them over Wi-Fi on a 16-channel PWM test bench, and tracks cycles completed and per-channel running hours so engineers can quantify actuator life. A bench simulator, protocol spec and sample logs are provided.

- Challenge provider: **Welkinrim Technologies**
- Hackathon: **Saturday, 26 September 2026**
- Project/dashboard name: **Athena**
- Workspace: `/Users/krisdreemur/Developer/SSN`

## Current state as of 25 September 2026

- `athena/` is a brand-new project created with `flutter create`.
- It is intentionally still the default Flutter counter app.
- No dashboard features, backend, database, protocol adapter or log parser have been implemented yet.
- Welkinrim's one-page brief, frozen WDR Protocol v1 manual, `RCOU.csv` sample, UI mockups, OLED states and wiring reference are now present and inspected.
- The official `wdr_tool.py` is present and fully inspected. It passed 85/85 both in-process and over real localhost TCP with virtual USB. Results are in `planning_evidence/`.
- No mandatory development input is missing. Raw ArduPilot `.bin` and PX4 `.ulg` samples are absent and remain stretch inputs.
- Use the official simulator; the user explicitly declined building a replacement simulator. M1 application implementation is in progress.
- The newest source of truth is `handout_controller_teams/`. Its reference bench and simulator report four channels and 8,000 frames.
- Reproduce the supplied controller HTML/`mock.css` desktop UI in Flutter, using real values or explicit empty states instead of illustrative mock data.
- Timebox: about four hours for the prototype and 12–15 hours for the full submission.

## Files to read

1. [`reports/Drone actuator life test bench simple.md`](<reports/Drone actuator life test bench simple.md>) — short plain-language brief.
2. [`reports/Drone actuator life test bench.md`](<reports/Drone actuator life test bench.md>) — full implementation report, protocol proposal, formulas, safety and demo plan.
3. [`research_notes/Drone actuator life test bench/flight_logs.md`](<research_notes/Drone actuator life test bench/flight_logs.md>) — PX4/ArduPilot parsing research.
4. [`research_notes/Drone actuator life test bench/bench_protocol.md`](<research_notes/Drone actuator life test bench/bench_protocol.md>) — Wi-Fi/PWM protocol, hardware and safety research.
5. [`research_notes/Drone actuator life test bench/lifecycle_hackathon.md`](<research_notes/Drone actuator life test bench/lifecycle_hackathon.md>) — lifecycle metrics, persistence, UX and pitch research.
6. [`SUPPLIED_ARTIFACTS.md`](SUPPLIED_ARTIFACTS.md) — authoritative inventory and concrete findings from the organizer-supplied files.
7. [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — detailed current specification, source precedence, contracts, milestones and tests.
8. [`IMPLEMENTATION_LOG.md`](IMPLEMENTATION_LOG.md) — completed inspection, verification evidence and future implementation tracker.

The full report contains pre-artifact research and primary-source links. Where it conflicts with `SUPPLIED_ARTIFACTS.md`, the frozen WDR Protocol v1 rules recorded there take precedence.

## Confirmed technical direction

### Stack

- **Flutter Web** for the dashboard.
- **FastAPI/Python** for log parsing, profile compilation, protocol handling and run coordination.
- **SQLite** on the backend for local events, sessions and observed counter snapshots; the bench owns its reported lifetime totals.
- **HTTP/WebSocket** between Flutter and FastAPI.
- **Plain line-based TCP on port 3333** between FastAPI and the WDR bench; USB serial at 115200 is an optional bring-up path.
- Serve Flutter's `build/web` output and FastAPI from one local origin for the demo.

Do not move PX4/ArduPilot binary parsing or authoritative lifecycle accounting into Flutter. Python already has the relevant parsing libraries (`pyulog` and `pymavlink`), and browser storage is not the system of record.

### Component boundaries

Keep these interfaces separate so the supplied artifacts can replace assumptions without rewriting the product:

- `LogParser`: source log bytes → timestamped actuator commands and metadata.
- `ProfileCompiler`: commands + mapping + limits → deterministic immutable profile.
- `BenchTransport`: simulator or real bench protocol adapter.
- `RunRepository`: source/profile provenance, operations, sessions, counter snapshots/epochs and events.

```text
Flight log
    ↓
Flutter Web: Import → Map/Preview → Verify/Upload → Run/History
    ↓ HTTP/WebSocket
FastAPI: parser + compiler + run state machine + persistence
    ↓ Wi-Fi / WDR v1 TCP port 3333
Simulator or 16-channel PWM controller
    ↓ acknowledgements/telemetry
SQLite event ledger and summaries
```

## Critical design rules

1. **The browser must not generate servo timing.** Browser timers and Wi-Fi can pause or jitter. Upload the complete profile first and let the simulator/controller execute it against a monotonic clock.
2. **The provided bench owns frame timing.** Athena does not implement a playback clock or firmware scheduler.
3. **Unknown units or mappings block compilation/upload.** Never guess whether a future PX4 field is microseconds or normalized output.
4. **Profiles are immutable.** Hash the source log, conversion settings, mapping, limits and serialized profile. Editing any creates a new revision, separate from the previously uploaded profile.
5. **Counters come from acknowledged execution.** Flutter progress is display-only and must never increment official totals.
6. **WDR v1 has no idempotency keys.** Keep one command outstanding, never blindly retry a timed-out mutating command, and reconcile with `INFO`, `STATUS`, and `COUNTERS`.
7. **A lost connection does not stop the bench.** Playback and counting continue. Reconnect, detect reboot from uptime, re-enable telemetry, and use bench counters rather than estimating.
8. **Do not overstate channel totals as asset lifetime.** Store optional label/serial metadata in profiles; cross-bench asset lifecycle tracking is deferred.

## Log conversion essentials

### ArduPilot

- The first 16 output commands are normally `RCOU.C1` through `RCOU.C14` plus `RCO2.C15` and `RCO2.C16`.
- Values are output PWM commands in microseconds.
- `RCOU` and `RCO2` may have different timestamps; merge by timestamp and channel rather than row number.
- Use the self-described `FMT`, `FMTU`, `UNIT` and `MULT` metadata.
- A missing channel is disabled/unknown, not a zero-microsecond command.

### PX4

- Prefer `actuator_outputs` only after proving its driver-specific natural units are PWM microseconds.
- Respect `multi_id` and read only the first `noutputs` values.
- `actuator_outputs_sim` and some other topics are normalized rather than PWM.
- `actuator_servos` requires logged/calibrated min, centre, max, reversal and function mapping; `NaN` means disarmed.
- Do not treat intermediate roll/pitch/yaw/throttle controls as physical output channels without the exact mixer/configuration.

### Compilation policy

- Store time as integer microseconds relative to the selected start.
- Resample with **zero-order hold**: each output tick uses the latest valid source command at or before that tick.
- Reject decreasing timestamps and unresolved large gaps by default.
- Use per-output min/max bounds that include the protocol's fixed 1500 µs idle. Scaling/reversal/configurable idle are not core features.
- Reject unsafe values by default and show the exact channel, time, requested value and permitted range. Do not silently clamp.
- Display adjacent and last-to-first step sizes. Without actuator-specific slew limits these are informational, not invented safety thresholds.
- Disabled channels use `null`, never `0`.
- For WDR upload, materialize exactly `INFO.ch` legal values in every frame. Any unused bench output receives the protocol's fixed 1500-microsecond idle value.
- Fetch `INFO.maxframes` before final compilation and require `frames <= maxframes`.

The canonical profile uses exactly the connected bench's channel count, a rate and ordered pulse frames. Exact deterministic serialization and rational timestamp arithmetic are specified in IMPLEMENTATION_PLAN.md §4; do not implement the older research schema.

## Confirmed WDR v1 state machine and protocol

```text
STOPPED --START [cycles]--> RUNNING --PAUSE--> PAUSED
   ^                            ^                |
   |                            +----RESUME------+
   +------------- STOP from any state ----------+
   +---- cycle target reached / EVT DONE --------+
```

- Open one TCP connection to port 3333, send newline-terminated uppercase commands, and allow only one outstanding command.
- Route interleaved `OK`, `ERR`, `TEL`, `EVT`, and debug lines by whole first token. The protocol expects replies within one second; the organizer's tested clients use a two-second application deadline, which Athena adopts before closing/reconciling the socket.
- Handshake with `PING`, `INFO`, `STATUS`, and `COUNTERS`, then send `TIME <unix>` and `TEL 1`.
- `INFO` supplies `proto`, `team`, `ch`, `maxframes`, and `up`; a lower `up` after reconnect indicates a reboot.
- Upload with `LOAD <rate> <frames>`, ordered `F` lines, and `COMMIT`. Verify the returned pulse-value sum modulo 65536.
- Control with `START [cycles]`, `PAUSE`, `RESUME`, and `STOP`. `STOP` is always accepted and returns every output to 1500 microseconds.
- `SET <ch> <us>` and `CLEAR` are accepted only while `STOPPED`.
- Telemetry is off after boot and every new TCP connection; resend `TEL 1` after reconnect.
- The full command, reply, error, telemetry, and event reference is in `SUPPLIED_ARTIFACTS.md`.

## Metric definitions

- A **profile cycle** is one complete replay of the selected profile.
- The bench increments a cycle after one complete profile pass and emits `EVT CYCLE <n>`.
- A partially executed loop does not count as a completed cycle.
- `COUNTERS.cycles` is the authoritative lifetime completed-cycle count.
- `COUNTERS.run_s` is authoritative lifetime whole seconds in `RUNNING`.
- Each `COUNTERS.active_s[i]` is authoritative lifetime whole seconds in `RUNNING` while channel `i` was more than 25 microseconds from the fixed 1500-microsecond idle value.
- Paused time does not accrue because the definition requires `RUNNING`, even though outputs hold their last values.
- Counters persist at least once per minute and on `STOP`, `PAUSE`, and `DONE`; a sudden power cut can lose up to 60 seconds.
- Unknown activity during a network disconnect is resolved from the next bench counter snapshot rather than estimated.
- Keep separate optional metrics for moving time, command travel and reversals; do not confuse them with completed profile loops.
- Display bench totals from COUNTERS; derive local session observations from compatible snapshots. Never sum lifetime snapshots, bridge counter reset/reboot boundaries, or invent missing cycle timestamps.

The correct product claim is **traceable command exposure**. Command replay does not prove mechanical movement, remaining useful life, MTBF or formal qualification without sensors and a proper reliability test plan.

## Persistence model

SQLite entities are source logs, immutable profiles, configured benches, deduplicated local operations, sessions, counter epochs/snapshots, events, cycle observations and schema migrations. See IMPLEMENTATION_PLAN.md §6 for fields and constraints. WDR does not expose per-channel enabled intervals or unique ACK IDs.

Event processing and counter snapshots/deltas should occur transactionally. On app restart or reconnect, compare `INFO.up`, `STATUS`, and `COUNTERS` with the last snapshot before updating the local session history.

## Flutter dashboard scope

Build four screens with one consistent 16-channel identity:

1. **Import and inspect** — file upload, hash, detected format/firmware, topics, duration, rates, gaps and warnings.
2. **Map and preview** — 16-row source-to-bench-to-actuator map, limits, status and synchronized waveform preview.
3. **Verify and upload** — clear PASS/WARN/FAIL checks, live `INFO` capabilities, active channels, profile hash, loop duration/count, projected exposure, checksum and simulator/real-bench badge.
4. **Run and review** — state, connection, visible Stop control, current/completed loop, reported channel values/hours, observation freshness, history and evidence export. Do not invent hardware timing-health metrics.

Flutter should use one typed API client, one WebSocket connection manager, typed protocol models and one application state store. Coalesce high-rate display telemetry before rebuilding widgets, but process every ACK and state transition.

## Safety boundaries

- Remove propellers and dangerous flight linkages.
- Clamp the fixture and guard the entire movement/pinch zone.
- Use actuator datasheet limits; `1000–2000 µs` and `50 Hz` are common examples, not universal requirements.
- Use a physical normally closed emergency stop that removes hazardous actuator power independently of the browser/app and asserts hardware output disable where available.
- Physical emergency-stop behavior belongs to provided firmware/hardware and must be checked at the venue; WDR has no SAFE or ARM wire state.
- Use a fused actuator supply sized for measured simultaneous peak/stall current. Do not power 16 servos through an ESP32/PCA9685 logic board.
- Verify ground strategy, pulse width, frequency, channel order, watchdog, startup, abort and reboot with actuator power disconnected using a scope or logic analyser.
- Commission in stages: signals only, one unloaded actuator, all channels at reduced limits, then intended loads.
- The web button is **Stop**, not E-stop. It centers outputs rather than proving power removal.

If building new hardware, ESP32 + PCA9685 is the simplest 16-channel option only when its shared frequency and approximately 4.88 µs pulse resolution at 50 Hz are adequate. Use the provided bench if one already exists.

## Supplied sample facts

- `RCOU.csv` contains 9,074 rows with `TimeUS` and `C1..C14`.
- It spans 930.700009 seconds and is sampled at approximately 10 Hz.
- One 23.499649-second gap separates rows 150 and 151 of the data.
- `C1..C6` contain valid PWM values from 1050 to 1746 microseconds.
- `C7`, `C8`, and `C11..C14` are always zero; `C9` and `C10` become a constant 1050 only after the gap.
- Zero is not a legal WDR PWM value and must be treated as inactive/missing source data, not uploaded.
- At 10 Hz the full log needs about 9,308 frames and does not fit the newest 8,000-frame reference bench. Query `maxframes` and require trimming or a compatible lower-rate/window choice.

## P0 hackathon scope

Must ship:

- one supplied log format parsed correctly;
- deterministic profile and hash;
- mapping for up to 16 outputs;
- simulator connection through `BenchTransport`;
- profile validation and visible safety limits;
- exact STOPPED/RUNNING/PAUSED state behavior;
- serialized WDR commands, routed interleaved lines, timeout reconciliation, and upload checksum verification;
- completed profile-loop counting;
- global bench running hours and per-channel active hours from the reported counters;
- SQLite history that survives refresh/restart;
- Wi-Fi disconnect/reconnect and bench-reboot detection;
- source/profile/run evidence export;
- clear `SIMULATOR` badge.

Defer cloud accounts, mobile polish, arbitrary log formats, multi-bench control, firmware updates, AI life prediction, MTBF/RUL claims and formal qualification analytics.

## Recommended demo

1. Import the supplied log and show its source hash and detected output stream.
2. Map four distinctive outputs to four named actuator assets.
3. Show the source gap and zero-only channels, then trim/select a valid window that fits `maxframes`.
4. Upload it, verify `COMMIT SUM`, and start a three-loop simulator run.
5. Interrupt Wi-Fi during the second loop.
6. Show that the bench continued running and that Athena does not invent local totals while disconnected.
7. Reconnect, resend `TEL 1`, reconcile `STATUS`/`COUNTERS`, and show the authoritative delta.
8. Restart/refresh, open history and export the traceable run evidence.

Suggested pitch:

> Welkinrim builds hardware to survive the mission. Athena preserves the mission as a repeatable test stimulus and makes every delivered command, completed replay, exposure hour and fault traceable to the actuator and test configuration.

This is a **fault-resilience demonstration**, not an “honest failure story.” The product is expected to handle an intentionally injected communication or validation fault correctly.

## Official tool now available

The newest `handout_controller_teams/wdr_tool.py` is present: SHA-256 `1881ed14d12e7e277b890233aaf3c84b60fcb5c49af6f93d8f9a68459c5b82d5`. It serves four channels with 8,000 frames at TCP 3333, virtual USB at 3334. Pyserial is only needed for actual serial ports. Its simulator reboot discards the profile even though the physical-bench manual says committed profiles survive; STOP retains it; TIME is acknowledgement-only; rounded counters persist in a shared temp JSON file. Isolate test state with TMPDIR. Preserve organizer sources unchanged. No raw `.bin`/`.ulg` is needed for core delivery.

## Acceptance checks that matter most

- Identical input/configuration produces byte-identical profile and hash.
- Distinct test values reach source-to-bench mappings without zero/one-based indexing errors, up to the channel count reported by `INFO`.
- Out-of-range values, gaps and duplicate mappings block compilation/upload; step size is informational without a specified limit.
- Stopping before `EVT CYCLE` does not add a cycle locally.
- Interleaved `TEL`/`EVT` lines do not get mistaken for a command reply.
- A wrong frame or value aborts upload and Athena restarts it with `LOAD`.
- `COMMIT SUM` mismatch blocks `START`.
- Wi-Fi loss/reboot never creates estimated runtime or a partial cycle in local history.
- A lost `START` reply triggers `STATUS` reconciliation rather than a blind second `START`.
- Backend crash around a transaction leaves results wholly committed or absent.
- Browser refresh shows the same authoritative run.
- Multiple tabs share one backend socket and serialized, revalidated actions; there is no WDR lease.
- Explicit Stop from any connected state centers outputs and records the observed result or uncertainty.

## Next coding step

Continue M1 onward in IMPLEMENTATION_PLAN.md; the first complete workflow is:

```text
RCOU.csv, relative 40–44 s, C1–C4, 50 frames/s
→ parse one actuator stream
→ detect the source gap and compile the selected valid window: 200 frames, SUM16=16982
→ upload through WDR `LOAD`/`F`/`COMMIT` and verify `SUM`
→ `START 1`
→ receive `EVT CYCLE 1` and `EVT DONE`
→ persist the run, events, and bench counter snapshots
→ display them in Flutter
```

Use the supplied serve-sim for integration. The baseline vendor checks are already complete, but Athena's end-to-end checks have not begun. Update IMPLEMENTATION_LOG.md at each milestone; never treat an official-tool score as proof of implemented application features.
