# Athena Project Context

This file is the compact-proof handoff for the Welkinrim Technologies hackathon project. Read it before continuing work.

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
- The promised simulator, protocol specification and sample logs are not present in the workspace.
- Research and implementation planning are complete enough to start as soon as those inputs arrive.
- Real actuator/bench specifications and the judging rubric would help, but they do not block simulator-first development.

## Files to read

1. [`reports/Drone actuator life test bench simple.md`](<reports/Drone actuator life test bench simple.md>) — short plain-language brief.
2. [`reports/Drone actuator life test bench.md`](<reports/Drone actuator life test bench.md>) — full implementation report, protocol proposal, formulas, safety and demo plan.
3. [`research_notes/Drone actuator life test bench/flight_logs.md`](<research_notes/Drone actuator life test bench/flight_logs.md>) — PX4/ArduPilot parsing research.
4. [`research_notes/Drone actuator life test bench/bench_protocol.md`](<research_notes/Drone actuator life test bench/bench_protocol.md>) — Wi-Fi/PWM protocol, hardware and safety research.
5. [`research_notes/Drone actuator life test bench/lifecycle_hackathon.md`](<research_notes/Drone actuator life test bench/lifecycle_hackathon.md>) — lifecycle metrics, persistence, UX and pitch research.

The full report contains primary-source links to PX4, ArduPilot, Flutter, FastAPI, RFC 6455, Espressif, NXP, SQLite, NIST, OSHA and Welkinrim.

## Confirmed technical direction

### Stack

- **Flutter Web** for the dashboard.
- **FastAPI/Python** for log parsing, profile compilation, protocol handling and run coordination.
- **SQLite** on the backend for authoritative events, completed cycles and channel exposure time.
- **HTTP** for file/profile/run resources.
- **WebSocket** for commands, acknowledgements, state, telemetry and faults.
- Serve Flutter's `build/web` output and FastAPI from one local origin for the demo.

Do not move PX4/ArduPilot binary parsing or authoritative lifecycle accounting into Flutter. Python already has the relevant parsing libraries (`pyulog` and `pymavlink`), and browser storage is not the system of record.

### Component boundaries

Keep these interfaces separate so the supplied artifacts can replace assumptions without rewriting the product:

- `LogParser`: source log bytes → timestamped actuator commands and metadata.
- `ProfileCompiler`: commands + mapping + limits → deterministic immutable profile.
- `BenchTransport`: simulator or real bench protocol adapter.
- `RunRepository`: append-only events, intervals, completions, faults and summaries.

```text
Flight log
    ↓
Flutter Web: Import → Map/Preview → Verify/Arm → Run/History
    ↓ HTTP/WebSocket
FastAPI: parser + compiler + run state machine + persistence
    ↓ Wi-Fi/provided protocol
Simulator or 16-channel PWM controller
    ↓ acknowledgements/telemetry
SQLite event ledger and summaries
```

## Critical design rules

1. **The browser must not generate servo timing.** Browser timers and Wi-Fi can pause or jitter. Upload the complete profile first and let the simulator/controller execute it against a monotonic clock.
2. **Use absolute deadlines.** Derive each frame deadline from the run start time so lateness does not accumulate.
3. **Unknown units or mappings block arming.** Never guess whether a PX4 field is microseconds or normalized output.
4. **Profiles are immutable.** Hash the source log, conversion settings, mapping, limits and serialized profile. Editing any of them creates a new revision and disarms the run.
5. **Counters come from acknowledged execution.** Flutter progress is display-only and must never increment official totals.
6. **Commands are idempotent.** Retrying `START` or receiving duplicate ACKs must not repeat motion or double-count results.
7. **A lost connection never creates optimistic data.** Preserve proven partial exposure, mark uncertain state and require safe recovery.
8. **Track physical actuator assets.** Totals belong to an actuator ID/serial number as well as the bench channel because actuators may move between channels.

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
- Require explicit per-channel `min_us`, `center_us`, `max_us`, `safe_us`, reversal and optional maximum step/slew.
- Reject unsafe values by default and show the exact channel, time, requested value and permitted range. Do not silently clamp.
- Validate the last-to-first transition when looping.
- Disabled channels use `null`, never `0`.

The canonical profile should include schema/version, source hash and metadata, compiler settings, sample period, loop duration, 16 channel definitions, timestamped frames and a profile SHA-256 digest. The full schema is in the detailed report.

## Run state machine and protocol intent

Recommended states:

```text
DISCONNECTED → SAFE → READY → ARMED → RUNNING
                         ↑       ↓        ↓
                         └──── PAUSED   STOPPING
                                    ↘   ↙
                                     SAFE
Any active state → FAULT or RECOVERY_REQUIRED
```

Core operations:

- Capabilities/handshake and protocol version negotiation.
- Upload and validate a hashed profile.
- Select profile and reserve a unique run ID.
- `ARM` with frozen mapping/limits and a short-lived arm token.
- `START`, `PAUSE`, `RESUME`, `ABORT` and `RESET_FAULT`.
- Sequence-numbered ACKs, telemetry, loop watermarks and faults.
- Heartbeat/watchdog, controller `boot_id`, reconnect snapshot and one controller lease.
- A repeated message ID with identical content returns the cached result; the same ID with different content is an error.

The provided protocol specification takes precedence over the proposed wire format. Implement it behind `BenchTransport`.

## Metric definitions

- A **profile cycle** is one complete replay of the selected profile.
- Count a global completed cycle only after the bench acknowledges the final watermark for every required active channel.
- A partially executed loop does not count as a completed cycle.
- **Per-channel running time** is the sum of controller-confirmed intervals during which that channel's output was enabled.
- If a pause holds an energized output, active time continues; if pause disables output, active time stops. The policy must be visible.
- Unknown time after disconnect/reboot is not estimated.
- Keep separate optional metrics for moving time, command travel and reversals; do not confuse them with completed profile loops.
- Derive totals from unique persisted completion/interval rows rather than trusting mutable display counters.

The correct product claim is **traceable command exposure**. Command replay does not prove mechanical movement, remaining useful life, MTBF or formal qualification without sensors and a proper reliability test plan.

## Persistence model

SQLite should contain at least:

- source logs and hashes;
- immutable profile revisions and hashes;
- actuator assets/serials;
- bench-channel mappings and limits;
- runs and run attempts;
- append-only run events with unique event/ACK keys;
- per-channel enabled intervals;
- unique loop-completion rows;
- faults and recovery decisions;
- optional manually entered baseline adjustments with operator, reason and timestamp.

ACK processing, interval closure, loop completion and summary checkpointing should occur in one transaction. On restart, active runs become `RECOVERY_REQUIRED` until the bench snapshot proves the exact run/profile/sequence/output state.

## Flutter dashboard scope

Build four screens with one consistent 16-channel identity:

1. **Import and inspect** — file upload, hash, detected format/firmware, topics, duration, rates, gaps and warnings.
2. **Map and preview** — 16-row source-to-bench-to-actuator map, limits, status and synchronized waveform preview.
3. **Verify and arm** — clear PASS/WARN/FAIL checks, active channels, profile hash, loop duration/count, projected exposure and simulator/real-bench badge.
4. **Run and review** — state, connection, large Stop/Abort control, current/completed loop, 16 channel values/hours, timing health, faults, history and evidence export.

Flutter should use one typed API client, one WebSocket connection manager, typed protocol models and one application state store. Coalesce high-rate display telemetry before rebuilding widgets, but process every ACK and state transition.

## Safety boundaries

- Remove propellers and dangerous flight linkages.
- Clamp the fixture and guard the entire movement/pinch zone.
- Use actuator datasheet limits; `1000–2000 µs` and `50 Hz` are common examples, not universal requirements.
- Use a physical normally closed emergency stop that removes hazardous actuator power independently of the browser/app and asserts hardware output disable where available.
- Releasing the emergency stop returns only to `SAFE`; it must never restart motion automatically.
- Use a fused actuator supply sized for measured simultaneous peak/stall current. Do not power 16 servos through an ESP32/PCA9685 logic board.
- Verify ground strategy, pulse width, frequency, channel order, watchdog, startup, abort and reboot with actuator power disconnected using a scope or logic analyser.
- Commission in stages: signals only, one unloaded actuator, all channels at reduced limits, then intended loads.
- The web button should be called **Stop/Abort**, not E-stop.

If building new hardware, ESP32 + PCA9685 is the simplest 16-channel option only when its shared frequency and approximately 4.88 µs pulse resolution at 50 Hz are adequate. Use the provided bench if one already exists.

## P0 hackathon scope

Must ship:

- one supplied log format parsed correctly;
- deterministic profile and hash;
- mapping for up to 16 outputs;
- simulator connection through `BenchTransport`;
- profile validation and visible safety limits;
- arm/start/pause/abort state machine;
- idempotent commands and ACKs;
- completed profile-loop counting;
- per-channel confirmed running hours;
- SQLite history that survives refresh/restart;
- Wi-Fi disconnect/fault injection;
- source/profile/run evidence export;
- clear `SIMULATOR` badge.

Defer cloud accounts, mobile polish, arbitrary log formats, multi-bench control, firmware updates, AI life prediction, MTBF/RUL claims and formal qualification analytics.

## Recommended demo

1. Import the supplied log and show its source hash and detected output stream.
2. Map four distinctive outputs to four named actuator assets.
3. Enter one unsafe limit and show that Athena blocks arming with the exact channel/time/value.
4. Correct it, show the changed profile hash and start a three-loop simulator run.
5. Interrupt Wi-Fi during the second loop.
6. Show one completed loop, preserved confirmed partial exposure and no fabricated second cycle.
7. Reconnect through snapshot/recovery; inject or resend a duplicate ACK and show no double-counting.
8. Restart/refresh, open history and export the traceable run evidence.

Suggested pitch:

> Welkinrim builds hardware to survive the mission. Athena preserves the mission as a repeatable test stimulus and makes every delivered command, completed replay, exposure hour and fault traceable to the actuator and test configuration.

This is a **fault-resilience demonstration**, not an “honest failure story.” The product is expected to handle an intentionally injected communication or validation fault correctly.

## Required incoming artifacts

Ask for:

1. Simulator source/binary, supported OS, launch command, ports, dependencies, reset behavior, acceleration and fault controls.
2. Protocol spec covering transport, framing, byte order, versioning, authentication, channel indexing, units/ranges, rate, ACK/retry rules, sequence IDs, heartbeat/watchdog, pause/abort/safe-state/reboot/reconnect/completion semantics.
3. Original sample logs with log family, firmware/vehicle version, expected actuator topics, mapping, units and a short known-good expected output window.
4. Bench/controller and actuator information: hardware/firmware, wiring, serials, signal/supply voltage, peak/stall current, pulse limits, frame rate, loss-of-signal behavior, sensors, interlocks and E-stop.
5. Judging rubric and organizer definition of “cycle” and “running hours.”

When the artifacts arrive:

1. Preserve original bytes and record SHA-256 hashes.
2. Launch the simulator unchanged and capture its handshake/capabilities.
3. Convert every protocol requirement into fixtures and tests.
4. Inspect every log topic/message and hand-check channels 1, 14, 15 and 16.
5. Freeze confirmed metric definitions and protocol assumptions.
6. Implement the real `LogParser` and `BenchTransport` adapters, then build the vertical slice.

## Acceptance checks that matter most

- Identical input/configuration produces byte-identical profile and hash.
- Distinct test values reach channels 1, 14, 15 and 16 without indexing errors.
- Unsafe values, steps, gaps and duplicate mappings block arming.
- Stopping one ACK before the final watermark does not count a cycle.
- Duplicate/reordered ACKs never duplicate time or completions.
- Wi-Fi loss/reboot never creates estimated runtime or a partial cycle.
- A lost `START` ACK and reconnect recover the existing run rather than starting twice.
- Backend crash around a transaction leaves results wholly committed or absent.
- Browser refresh shows the same authoritative run.
- A second tab cannot take control while another holds the lease.
- Fault/abort from every active state applies the declared safe action and remains in history.

## Next coding step

Do not replace Athena's starter screen with speculative protocol code before inspecting the supplied artifacts. Once they arrive, create the backend skeleton and implement the shortest vertical slice:

```text
known sample log
→ parse one actuator stream
→ compile a short deterministic profile
→ upload to simulator
→ arm/start one loop
→ receive final ACK
→ persist one completion and channel intervals
→ display them in Flutter
```

Then add safety validation, restart recovery, fault injection and full 16-channel UI.
