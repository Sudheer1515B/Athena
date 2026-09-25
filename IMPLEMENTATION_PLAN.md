# Athena — Detailed Implementation Plan

**Revision:** 1.0 · **Date:** 25 September 2026 · **Status:** specification only; application implementation has not begun.

This is the current implementation specification for Welkinrim's Competition A PC controller. It replaces conflicting recommendations in the earlier research reports and chat plans. Use [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) to record execution evidence and changes as implementation proceeds. Do not interpret this document as authorization to start coding: the user's current request is inspection and documentation only.

## 1. Objective, scope, and source authority

### 1.1 Problem statement

> Build a web-based controller that converts recorded drone flight logs into servo command profiles, replays them over Wi-Fi on a 16-channel PWM test bench, and tracks cycles completed and per-channel running hours so engineers can quantify actuator life. A bench simulator, protocol spec and sample logs are provided; teams demo on real hardware.

Athena is the Flutter Web dashboard; the backend runs on the engineer's PC. The supplied firmware owns PWM playback and lifetime counters. The deliverable is a usable controller with reproducible conversion, correct WDR integration, persistent history, and documented limitations. It measures commanded exposure, not mechanical motion or remaining actuator life.

### 1.2 Source precedence and agreed preferences

1. The supplied frozen [WDR manual](WDR_Manual_and_Protocol.pdf) specifies the wire contract.
2. The supplied [wdr_tool.py](wdr_tool.py) is the executable simulator and conformance reference. Record implementation quirks explicitly; do not silently turn simulator bugs into required firmware behavior.
3. The [competition brief](one_pager_A_controller.pdf) defines product objectives and judging.
4. The four HTML files define desired functionality and provide visual references. Athena need not copy their exact layout.
5. Older research is background only when it conflicts with these artifacts.

User decisions: use Flutter; follow the newest supplied requirements; use the official simulator, not a substitute; cover the HTML functionality with a custom layout; do not start application code during this documentation task.

### 1.3 Completion tiers

**Core delivery:** supplied RCOU CSV import; trim/map/resample/preview; validated profile upload; Start/Pause/Resume/Stop; cycle target; manual output setting; counter reset; dashboard; time-sync acknowledgement; reconnect/reboot handling; SQLite sessions/events; date/channel filtering; CSV export; reproducible setup and tests.

**After core passes, complete the remaining compatible HTML functionality:** printable PDF test report, improved comparison charts, finite-run finish estimate. These have explicit work items below and must not appear as working controls until implemented. If the hackathon deadline requires deferral, record that in the implementation log and README.

**Deferred extensions:** raw ArduPilot `.bin` and PX4 `.ulg` import, multi-bench control, cloud deployment, accounts, firmware changes, mobile-native builds, cross-bench actuator asset management, life prediction. No corresponding raw logs are supplied. Optional actuator serial text may be stored in a mapping, but do not present a global asset-lifetime ledger in v1.

### 1.4 Judging alignment

| Category | Points | Evidence Athena should demonstrate |
|---|---:|---|
| Functional completeness | 40 | Import through replay, manual control, meters, history |
| Correctness and robustness | 25 | Reconnect, saved counters across reboot, TIME handling, no duplicate Start |
| Usability | 20 | Clear state, understandable errors, useful preview, accessible controls |
| Code/README/ease of running | 15 | Separated modules, tests, one documented startup path |

The tool's 85-point firmware scorer is a different assessment. An 85/85 simulator result is not an Athena score or evidence that Athena exists.

## 2. Verified inputs and implementation consequences

### 2.1 Inventory

| Input | Findings |
|---|---|
| `wdr_tool.py` | 1,796 lines; official simulator, TCP/serial clients, scorer, uploader, sample generator, soak utility |
| `WDR_Manual_and_Protocol.pdf` | Four-page frozen WDR v1 contract |
| `one_pager_A_controller.pdf` | Competition A brief, required features, rubric |
| `RCOU.csv` | 9,074 samples, TimeUS plus C1–C14, approximately 10 Hz |
| `01_dashboard.html` | Dashboard, controls, channel meters, traces, recent events |
| `02_profile_import.html` | Source selection, trim/rate/map, preview, upload |
| `03_history.html` | Filters, sessions, events, CSV/PDF exports |
| `04_oled_and_wiring.html` | Competition B hardware/OLED reference; not a UI implementation requirement |
| `athena/` | Default Flutter counter app; Dart SDK constraint `^3.13.4` |

Tool SHA-256: `3059c64229a677d40d5f1e6d63081a277ebe01934809099f17acb1fcdf6971e4`. Other source hashes are in [SUPPLIED_ARTIFACTS.md](SUPPLIED_ARTIFACTS.md). Preserve originals unchanged.

### 2.2 WDR facts to implement

- Plain TCP on port 3333; USB serial 115200 8N1 is for optional diagnostics. Browser WebSocket traffic terminates at FastAPI, not at the bench.
- ASCII uppercase commands, single spaces, newline terminator, maximum 128 characters before the newline; ignore carriage returns on receive.
- Exactly one OK/ERR reply per nonempty command; one outstanding command; one-second reply timeout.
- TEL and EVT can precede replies. Debug lines must not disrupt parsing.
- States: STOPPED, RUNNING, PAUSED. No ARM, ABORT, FAULT_RESET, boot UUID, request UUID, profile digest query, rate query, per-frame execution ACK, or watchdog-stop command exists in WDR v1.
- Channel indices are zero-based. Manual describes 1–8; simulator reports four. Athena's structures support up to 16, but output controls are sized from INFO. Reject unsupported protocol versions or channel counts outside 1–16.
- Pulses 500–2500 µs; idle fixed at 1500 µs; physical servo PWM 50 Hz; profile update rate 10–100 frames/s. These are different rates.
- Simulator limit is 2,000 frames; always use INFO.maxframes. At 50 frames/s this permits 40 seconds; at 10, 200 seconds; at 100, 20 seconds.
- New TCP client displaces the previous client and turns telemetry off. Link loss does not stop motion or accounting.
- Telemetry nominally every 500 ms. Cycle and done events contain no bench timestamps.
- COUNTERS returns lifetime cycles, run_s, and active_s for each channel. Active means RUNNING and absolute distance from 1500 strictly greater than 25 µs.
- Pause holds PWM but stops counter accrual. Manual SET while stopped does not accrue running/active time.
- STOP centers outputs, resets frame to zero, and saves counters. Target completion also stops, centers, and saves.
- Saves occur at least every minute while running and on STOP/PAUSE/DONE. Power loss may roll back unsaved time and completed cycles; do not promise zero loss.

### 2.3 Source-code details absent or easy to miss in the manual

| Detail | Evidence | Consequence |
|---|---|---|
| Defaults: CH=4, MAXFRAMES=2000, TEAM=SIM | Tool constants near line 374 | Discover capabilities, do not hard-code examples |
| Persistent state is `tempfile.gettempdir()/wdr_sim_counters.json` | Tool line 378 | Isolate TMPDIR for tests; simultaneous independent simulators must not share it |
| `--port sim` creates a new in-process device | Bench constructor | It does not connect to an existing serve-sim process |
| Real TCP server and virtual USB | cmd_serve_sim, line 1654 | Default 3333/3334; both bind only 127.0.0.1 |
| `!RESET` is accepted on virtual USB only | usb_client | Keep it out of the production controller command set |
| Simulator reboot clears the profile | _do_reboot | Re-upload before the next Start; no automatic restart |
| STOP retains committed profile and upload buffer | _dispatch | Stopped is not equivalent to profile absent or upload cleared |
| LOAD discards a previously committed profile | _dispatch | Failed replacement must invalidate local upload verification |
| COUNTERS and saved seconds use Python round() | _dispatch/save_counters | Allow integer quantization in tests; do not assume truncation or subsecond precision |
| TIME validates an integer and returns OK, but stores nothing | _dispatch | Show acknowledgement, not verified clock accuracy or measured offset |
| Built-in CSV uploader ignores t_ms and uses --rate | cmd_upload, line 1441 | Athena must handle timestamps itself; uploader cannot resample RCOU.csv |
| Uploader sends STOP automatically | cmd_upload | Athena must not use it as its runtime adapter or silently stop an existing run on import |
| Source banner describes an old six-level split | Actual LEVELS table near line 1369 | Executable levels 1–7 total 85; use actual results |
| cmd_test returns zero even if checks fail | cmd_test | Inspect every JSON check and totals, not exit code alone |
| A repeated F after all expected frames can index outside load_buf | Static inspection of F handler | Never send beyond n−1 or blindly retry a frame; do not modify vendor tool |

Static quirks above are source findings; passing the official scorer does not prove every edge case. The scorer's reboot case saves with PAUSE first, so its passing result does not establish zero-loss abrupt-power-cut behavior.

### 2.4 Baseline already executed

On 25 September 2026, the original tool passed **85/85 in-process and 85/85 over real localhost TCP plus virtual USB**. Tests used an isolated temporary directory and ports 43333/43334. The inspection server was stopped afterward. JSON evidence is stored under [planning_evidence](planning_evidence/). No real hardware was exercised.

### 2.5 Sample log and first integration fixture

Source timestamps run from 143523182 to 1074223191 µs, a 930.700009-second span. Median delta is 99,995 µs. The one large gap is from relative time 14.900308 to 38.399957 seconds, between file lines 151 and 152.

| Channels | Observation |
|---|---|
| C1–C6 | Nonzero throughout; overall range 1050–1746 µs |
| C7, C8, C11–C14 | Always zero |
| C9, C10 | First 150 rows zero, then constant 1050 |

Use this exact first integration case, calculated during inspection without writing a compiler implementation:

- Relative trim [40.000000, 44.000000) seconds; 50 frames/s; C1→OUT0, C2→OUT1, C3→OUT2, C4→OUT3.
- 200 frames, 4 seconds/cycle, zero-order hold.
- First frame `[1050,1050,1050,1050]`; last `[1219,1208,1185,1201]`.
- Channel ranges: `[1050,1223]`, `[1050,1208]`, `[1050,1199]`, `[1050,1214]`.
- WDR checksum **16982**. This is a deterministic conversion fixture, not proof of suitability for a particular physical actuator.

## 3. Architecture and runtime choices

### 3.1 Data flow

```text
Browser: Flutter Web
  import → inspect → map/trim/preview → upload → control → history/export
          HTTP /api/v1 + WebSocket /api/v1/live
PC: FastAPI, single process/worker
  importer → compiler → bench coordinator → WDR TCP client
                  SQLite + original files + immutable profiles
          one TCP connection, newline WDR v1, port 3333
Provided simulator OR provided ESP32 bench
  owns frame timing, physical outputs, lifetime counters
```

No browser timer or PC task sends one frame per playback tick. All frames upload before START. No firmware development or PCA9685 driver is part of Athena.

### 3.2 Backend boundaries

Use `backend/` for a Python package with API, typed models, importer, compiler, bench coordinator, WDR transport, repository, and tests. Use standard-library csv/hashlib/sqlite3/asyncio for the corresponding functions. FastAPI/Pydantic handle validation and HTTP models; Uvicorn hosts; python-multipart handles uploads. Add pytest and async test support as development dependencies. Use reportlab only at the report milestone.

Create a project-local virtual environment and pin resolved dependencies when implementation starts. Existing Python 3.14.7 was sufficient for the supplied tool; FastAPI was not installed in the interpreter previously inspected. Do not assume backend dependencies are already available. Keep the vendor tool a separate process, not an imported production dependency.

- Importer: source bytes → validated timestamp/channel series and inspection summary.
- Compiler: series + settings + capabilities → immutable profile and diagnostics.
- WDR transport: framed connection, parser, pending reply, disconnect notification.
- Coordinator: serialized bench operations, snapshots, command outcomes, recovery.
- Repository: transactional local history and durable operation identity.
- API: typed requests/responses; no raw arbitrary WDR endpoint.

SQLite uses foreign keys, WAL, and synchronous FULL. Serialize repository writes; use a single dedicated DB worker so disk work does not block socket reads. Full profile conversion runs outside the connection reader's event-loop path.

### 3.3 Flutter boundaries

Retain `athena/`; replace the starter only when coding is authorized. Use Material 3, a single ChangeNotifier application store, typed models, an HTTP client, and one web_socket_channel connection manager. Use file_picker for browser file selection and fl_chart for step/line and bar charts; pin compatible package versions after resolving against the installed Flutter SDK. Use go_router for Dashboard/Profile/History/Settings navigation.

Store canonical state on the backend. Keep only editing drafts and UI preferences in Flutter. A new page/tab or refresh requests a complete snapshot. Do not persist authoritative counters in localStorage.

### 3.4 Deployment shape

- Production demo: FastAPI bound to 127.0.0.1:8080 serves Flutter's build/web and API from one origin.
- Development: Flutter on a fixed localhost port with an explicit backend base URL; allow only that origin in development CORS/WebSocket checks.
- One Uvicorn worker; a second instance using the same data directory must fail clearly through a process lock.
- Runtime data under ignored `var/`: SQLite, originals, compiled profiles, diagnostic logs. Do not place runtime counters or sample-generated output among immutable supplied inputs.
- Backend startup does not connect or start playback automatically. Restore local history, display disconnected, and let the engineer connect. Automatic reconnect applies only after an explicitly established connection is interrupted.
- Closing the browser does not stop the backend or bench. Disconnect and backend shutdown do not implicitly STOP. Communicate continued-playback behavior in the disconnect action.

## 4. Import and deterministic profile compilation

### 4.1 CSV contract

Initial supported source dialect is UTF-8 CSV (optional BOM), with TimeUS and C-numbered columns C1 through C16. The supplied file has only C1–C14. Use header names, not fixed column positions. Ignore extra columns after reporting them. Reject duplicate headers, absent time/channel columns, ragged rows, non-integer values, missing cells, negative timestamps, duplicate/decreasing timestamps, and fewer than two data rows. Permit blank lines and preserve original file-line numbers in diagnostics. Limit source upload to 50 MiB and 500,000 data rows; report explicit limits on violation.

PWM cells must parse as integers, but zero/out-of-range numeric cells do not prevent inspecting the whole file. Classify them by channel and time. They block compilation only if selected in the chosen window, including the preceding sample that supplies its first frame. Unselected invalid channels must not prevent use of valid C1–C4.

Do not infer aircraft functions such as aileron/throttle from C1/C2. Default labels are source channel names; users can rename them.

### 4.2 Inspection output

Return source ID/hash, filename, bytes, row count, columns, first/last timestamp, relative duration, median sample interval, effective rate, per-channel ranges/zero-invalid counts, gaps, and bounded preview series. Show all errors with code, message, line/channel and value where applicable.

Initial gap policy: interval greater than five times median positive delta. This is an Athena policy, not a firmware rule. Store the policy/version with the profile and show detected gaps; do not silently bridge them. For supplied input this threshold is 499,975 µs and flags the single 23.499649-second gap.

### 4.3 Draft settings and defaults

- Trim is relative to the first source sample, integer microseconds, end-exclusive, 0 ≤ start < end ≤ last relative timestamp.
- Default rate 50; permit any integer 10–100.
- Bench outputs numbered OUT0…OUT(N−1) in mapping; dashboard can show CH1…CHN with the wire number in details.
- Suggest the first N valid nonzero source channels in source order; engineer reviews before compile/upload. No automatic upload or motion.
- Each output has an optional source column, label, optional serial text, min_us, max_us. Default range 500–2500; require 500 ≤ min ≤ 1500 ≤ max ≤ 2500 because STOP/idle centers every output.
- One source per destination and initially no duplicate source assignments. Unmapped means constant idle 1500, not electrically disabled.
- No scaling, reversal, configurable idle, interpolation selection, or hidden zero substitution in core v1.
- Offline inspection is allowed; final compilation/upload requires known connected capabilities. A capability change invalidates compatibility and requires recompilation where shape/limit differs.
- Do not silently truncate the full source to fit; show required frames and maximum allowed duration and ask the engineer to select a trim.

### 4.4 Exact compilation algorithm

1. Check settings, mapping uniqueness, pulse limits, connected proto/channel count/frame capacity, and at least one mapped output.
2. Let A=start_us, B=end_us, R=rate. Compute F=floor((B−A)×R/1,000,000). Require 1 ≤ F ≤ maxframes. Report actual replay duration F/R and discarded sub-frame remainder.
3. Reject any chosen window intersecting the interior of a detected gap. Starting at the first sample after a gap is allowed; starting inside the gap is not. No extrapolation after the source's final timestamp.
4. Validate all selected source samples inside the chosen window plus the sample providing the initial value. Do not hide an invalid source sample merely because downsampling would skip it.
5. For frame k=0…F−1, choose the largest source timestamp t satisfying t×R ≤ A×R + k×1,000,000. This is exact zero-order hold using integer arithmetic even at 30 Hz.
6. Write mapped values in output-index order and 1500 for every unmapped output. Each row has exactly N integer values. Validate all serialized WDR lines fit the 128-character limit.
7. Compute per-output preview/ranges, maximum adjacent-frame step, and last-to-first loop step. Steps are informational without an actuator-specific slew specification; do not invent a universal safe limit.
8. Serialize the canonical profile and compute SHA-256 plus SUM16. Preserve source/configuration provenance.

Canonical JSON content: schema_version=1, compiler_version, source_sha256, source_dialect, start_us, end_us, rate_hz, channel_count, ordered mapping with labels/limits/serials, gap policy, frames. Serialize with sorted object keys, compact separators, UTF-8, integers, and no creation timestamp/profile ID/hash field inside the hashed content. IDs, creation time, reported maxframes and hashes live in the outer database record. Changing a label produces a new revision; SUM16 can remain identical because it covers pulse values only.

The checksum is sum of every frame value modulo 65536. SHA-256 is local identity; the bench neither receives nor proves that hash. WDR SUM is a weak transfer check, not cryptographic verification.

### 4.5 Preview and output

Plot source and compiled step traces with distinct legend labels. For large source previews, retain per-bucket minima/maxima and boundary points; never use downsampled preview data to compile. Cap browser preview to 2,000 points per selected trace; allow exact frame-table inspection for the compiled profile.

Offer compiled CSV export with t_ms,ch0…chN−1 and a companion metadata record. t_ms is display/export timing; use decimal milliseconds when necessary. WDR upload uses rate and pulse frames, never CSV timestamp scheduling. Do not claim the official upload subcommand validates these times.

## 5. WDR connection, operation, and state behavior

### 5.1 Connection lifecycle

Use asyncio TCP streams with TCP_NODELAY. Connect timeout three seconds, command reply timeout one second, bounded receive-line size 4 KiB (larger than command limit to accommodate diagnostics). Discard bounded debug lines; oversized/unbounded or malformed protocol lines trigger a recorded protocol error and reconnect. Match whole first tokens, not arbitrary prefix strings.

Handshake serially: PING → INFO → STATUS → COUNTERS → TIME unix_seconds → TEL 1. Validate required keys and numeric/vector shapes. Preserve unknown fields for diagnostics; ignore unknown EVT types after recording them. TIME ERR UNKNOWN leaves time-sync unsupported with a visible warning; valid control can continue because time sync is optional. Other handshake failures leave connection unsynchronized.

Connection states: DISCONNECTED, CONNECTING, SYNCHRONIZING, CONNECTED, RECONNECTING, ERROR. Bench states are separate STOPPED/RUNNING/PAUSED; unknown is represented as absent/stale, not STOPPED.

Every fresh socket increments a local connection generation. Use a single reader for replies and async events; one serialized scheduler for writes. An unexpected reply with no pending command invalidates correlation and forces reconnect.

### 5.2 Scheduling and polling

- One outstanding command only. Each action is validated when submitted and again before transmission.
- Routine STATUS, COUNTERS and INFO queries run every five seconds when idle/running/paused; coalesce missed polls instead of queuing a backlog. Query on important state transitions too.
- Consume telemetry at its supplied approximately 2 Hz rate. After two seconds without telemetry, mark it stale and request STATUS. A read-only query timeout triggers reconnect; an explicitly successful STATUS can refresh state while a telemetry warning remains.
- Upload is exclusive: no routine polls or unrelated mutating commands between LOAD and COMMIT. Continue reading TEL/EVT throughout.
- Stop has priority after the current outstanding command. Never inject a second command before its reply. On upload cancellation, stop scheduling F/COMMIT, send STOP, mark upload unverified. Because STOP does not clear the simulator's upload buffer, any future upload starts with a new LOAD.
- Do not auto-resume an interrupted upload, replay a queued mutation after reconnect, or automatically retry an uncertain frame.

### 5.3 Upload procedure

Require stopped, connected, fresh status and compatible immutable profile. Mark previous local upload verification invalid before LOAD, because a successful LOAD destroys the previous bench profile. Send LOAD R F, ordered F 0…F−1, and COMMIT with one reply per line. Record acknowledged progress, but do not store a history event for every frame.

On OK SUM=s matching local SUM16, mark the profile verified for the current connection generation and store the observed upload operation. On ERR, timeout, disconnect, malformed checksum or mismatch, mark failed/uncertain and prohibit Start from that profile. No automatic fallback to the former profile. User may retry a complete upload while stopped.

### 5.4 Commands and UI eligibility

| Action | Preconditions | Postcondition and follow-up |
|---|---|---|
| START n | Connected, stopped, no active operation, verified profile this connection | Create pending session before send; record OK; fetch STATUS/COUNTERS |
| PAUSE | Running | Expect paused/hold; refresh state and saved counter snapshot |
| RESUME | Paused | Expect running; refresh state |
| STOP | Synchronized connection, any bench state | Always available independent of local profile; center outputs; refresh counters/status |
| SET ch us | Stopped, no upload | Validate wire index/range and configured limits; explicit Apply sends one command |
| CLEAR | Stopped, no upload; user confirms reset | Snapshot before; send; verify counters afterward; create reset boundary |
| TIME sync retry | Connected, no exclusive upload | Send backend Unix seconds; record acknowledgement time, not measured offset |
| Cycle target edit | Stopped, before START | Local setting only; no live-target update command exists |

Target is integer 0…2,147,483,647, with 0 shown as Continuous. Use finite three-cycle target as the demo default. No ARM or ABORT command/button. Stop is a software command, not a physical E-stop or proof of de-energization.

Manual sliders update only a draft; transmit on Apply/release-confirmed action, not every pixel movement. Keep local limits applicable to SET too. Do not use a fake disabled-channel toggle: mapping on/off affects a new profile and idle output, not hardware power.

### 5.5 Timeout and reconnection policy

A timeout means an unknown outcome, not definite rejection. Close that socket so a late OK cannot satisfy a later command. Persist the uncertain operation. Cancel unsent queued mutations. Reconnect after 1, 2, 4, then 5 seconds between attempts; each attempt retains the three-second connect timeout. Explicit Disconnect cancels retries. After three post-handshake disconnections within 30 seconds, stop automatic retry and show possible competing-controller/network instability to avoid an endless takeover loop.

On reconnect repeat the handshake, re-enable TEL, and reconcile INFO/STATUS/COUNTERS. Never implicitly STOP, START, RESUME, CLEAR or upload. Show stale last-known values during loss with the observation time and message that playback may continue.

- START uncertain: observe whether bench is running or has completed; do not repeat. Record attribution confidence; identical target/frame count is supporting evidence, not unique identity.
- STOP uncertain: report unknown until status is observed. If still running, leave Stop available for explicit retry, rather than claim it stopped.
- Upload uncertain: invalidate upload verification; start a new LOAD when the user retries.
- CLEAR uncertain: compare before/after counters and stopped status; if reset cannot be established, record ambiguity and a new accounting boundary.

### 5.6 Reboot and profile identity limitations

Use uptime decrease as positive reboot evidence. During one backend process, compare uptime progression to local monotonic elapsed time (allow two seconds for integer quantization/latency) to detect likely discontinuity even if new uptime exceeds the last old value. Backend restarts and long gaps may remain ambiguous; no boot UUID exists.

Any new connection invalidates the permission to issue a new Start based on an old upload verification. Re-upload while stopped before a new run. A currently running/paused bench may still be observed, paused/resumed/stopped; do not destroy it just to regain profile certainty.

Associate an ongoing run with the previous session as provisional when uptime, frame count, target and counters are compatible. Mark its identity unverified across the gap. On contradiction/reboot, end the old session with an uncertain end interval and create an observed external session if appropriate. On backend startup, persisted RUNNING is historical last-known state until connection reconciliation.

## 6. Persistence, accounting, and public interfaces

### 6.1 Durable entities

| Entity | Minimum fields and constraints |
|---|---|
| source_logs | UUID, original name, SHA-256, managed path, bytes, inspection JSON, created UTC |
| profiles | UUID, source FK, SHA-256 unique, canonical content/path, SUM16, rate, F, N, created UTC |
| benches | Local UUID, label, host, port, last reported team/proto/capabilities; team is not a globally unique identity |
| operations | request UUID unique, canonical request digest, action, status, timestamps, response/error, session/profile references |
| sessions | UUID, bench/profile optional FK, target, pending/active/completed/stopped/interrupted/uncertain status, start/end observation bounds, identity confidence |
| counter_epochs | UUID, bench, boundary cause (initial/reset/reboot/discontinuity), first observation |
| counter_snapshots | Increasing ID, bench/epoch/session optional, received UTC and process-monotonic time, uptime, cycles, run_s, active_s vector |
| events | Increasing ID, bench/session/operation optional, type, received UTC, raw line/structured details, confidence |
| cycle_observations | Session and run-cycle number unique when association is trustworthy; references raw event |
| schema_migrations | Applied integer schema version |

Start uses a persisted pending session before socket transmission so a crash cannot erase the attempt. Operations transition queued → sending → succeeded/failed/uncertain/cancelled. On backend restart, sending operations become uncertain; queued unsent operations are cancelled. Never resend automatically after a crash.

Commit related event, operation result and accounting update together. Publish successful durable updates to Flutter only after the transaction commits. For a DB write failure, block new uploads/starts/sets/clears, report degraded history, but continue attempting an explicitly requested Stop even if its audit write fails. Keep the error visible.

### 6.2 Counter rules

1. Dashboard lifetime values are the latest bench COUNTERS, with age. Do not sum snapshots or add EVT CYCLE to the lifetime value.
2. Current-run cycles come from STATUS/TEL/EVT. Deduplicate cycle events within a confidently associated session. Missing events can be recovered as an aggregate count, not invented exact event times.
3. Derive time as seconds/3600 only for display; retain integers in storage. Optional seconds display makes short demos intelligible.
4. Active threshold is strictly greater than 25: 1475 and 1525 are inactive; 1474 and 1526 are active while running. Paused/manual-stopped time is excluded.
5. Maintain separate quantities: bench-reported current lifetime totals, and locally observed session deltas. Never relabel locally observed totals as a complete actuator lifetime.
6. For compatible same-epoch snapshots, differences are observed increments over that interval. Store/refer to the interval once; no duplicate accumulation on refresh/reconnect.
7. Known CLEAR, reboot, an unexplained counter decrease, or uncertain continuity creates an epoch boundary. Preserve all old observations. The first new snapshot is a baseline, not newly earned exposure; do not bridge/subtract across the boundary.
8. Reboot can lower bench totals. Show the rollback and last pre-reboot observation without rewriting old evidence or adding an artificial correction to the bench's counter. Post-reboot increments represent new observed exposure.
9. Use observations around START/STOP/DONE to summarize sessions, with integer quantization and observation gaps disclosed. Do not promise exact subsecond intervals.
10. A run discovered already active is an observed external session with unknown start/profile unless evidence establishes more. Do not allocate pre-observation lifetime totals to it.

The protocol exposes global bench running time and per-channel active time, not independent channel-enable timers. If the channel table repeats bench hours, label it Shared bench running hours with an explanation. Unmapped outputs at 1500 accrue bench time but not active time. Do not copy the mockup's implied independently measured disabled-channel bench hours.

### 6.3 Date-range history

Use UTC storage, local-time UI date pickers, and start-inclusive/end-exclusive query bounds. List overlapping sessions and events in the selected range. For active-hour charts sum only nonnegative, same-epoch observation deltas whose entire observation interval lies inside the range. List excluded boundary/gap intervals and label coverage partial; do not prorate unknown activity across dates. An interval spanning a network outage may supply a confirmed aggregate when both endpoints lie inside the range, but its internal event timing stays unknown.

For a complete local session, use its boundary snapshots. Avoid extrapolating the final active interval of a still-running session. Display last updated time.

### 6.4 HTTP API, all under /api/v1

| Method/path | Request | Response |
|---|---|---|
| GET /health | none | Service/schema/version and DB health |
| GET /snapshot | none | Complete connection/bench/profile/session/counter/operation state |
| POST /sources | Multipart file | 201 SourceInspection |
| GET /sources/{id} | none | Inspection and provenance |
| GET /sources/{id}/preview | channels, start_us, end_us, max_points | Bounded source traces |
| POST /profiles | source_id, trim, rate, mapping, expected capability generation | 201 immutable ProfileSummary or validation issues |
| GET /profiles/{id} | none | Profile settings, hashes, summary |
| GET /profiles/{id}/preview | channels, max_points | Compiled traces/frame information |
| GET /profiles/{id}/export.csv | none | Download of compiled profile |
| POST /bench/connect | request_id, configured bench_id/host/port, mode simulator/hardware | 202 Operation |
| POST /bench/disconnect | request_id | 202 Operation; explicitly no STOP |
| POST /bench/upload | request_id, profile_id, expected connection generation | 202 Operation |
| POST /bench/actions | request_id, action start/pause/resume/stop/set/clear/time_sync, action-specific fields, generation | 202 Operation |
| GET /operations/{id} | none | Queued/progress/result/error/uncertain |
| GET /sessions | date bounds, status, cursor, limit (default 50, max 200) | Paginated summaries |
| GET /sessions/{id} | none | Session, provenance, counter boundaries and uncertainty |
| GET /events | date/session filters, cursor, limit | Paginated durable events |
| GET /history/summary | date bounds, channels | Observed deltas, coverage flags, chart data |
| GET /history/export.csv | same filters, kind sessions/events/counters | Exact filtered rows with units and confidence |
| GET /sessions/{id}/report.pdf | none | Report milestone only |
| WS /live | Same-origin connection | Initial snapshot, subsequent typed updates |

Every bench mutation uses a client-generated UUID request_id. Same UUID and same canonical body returns the stored operation without another WDR send; same UUID with different content returns 409. This is local deduplication, not a claim of exactly-once execution on the bench. Validate backend state again at dispatch. Reject ordinary conflicting operations with 409 rather than building an unbounded mutation queue. Stop cancels pending upload frames as specified above.

Validation errors use a common object with code, message, details and field/line/channel pointers; HTTP 422 for invalid content, 409 for state/generation conflicts, 413 for file limit, 503 for disconnected/degraded service. Wire ERR codes are preserved inside operation errors. Do not leak arbitrary filesystem paths to the UI.

### 6.5 WebSocket contract and concurrency

Messages contain api_version=1, server_instance_id, increasing stream sequence, received_at UTC, type and payload. Types: snapshot, connection, bench_state, telemetry, counters, operation, session, event, service_error. Durable events additionally include the SQLite event ID. After a stream sequence gap/new server instance, Flutter refreshes /snapshot and history; do not require replay of transient telemetry.

Register subscriber and enqueue initial snapshot atomically with respect to the coordinator's updates. For a slow browser coalesce latest telemetry; if durable-update buffering overflows, close its WebSocket so it resynchronizes. Do not drop durable database events. WebSocket disconnection alone never stops the bench.

All tabs share one backend connection and state. Serialize and revalidate actions; record which local client submitted them. No multi-user auth or bench control lease is introduced in core. Restrict production service to localhost, validate Origin for mutation/WebSocket requests, and avoid wildcard CORS. A second external TCP client can still take over; WDR provides no mechanism to prevent that.

## 7. Flutter screens and interaction specification

### 7.1 Shared shell

Use an Athena Material 3 shell with Dashboard, Profile, History, Settings. Desktop/laptop first (verify 1280×720 and 1440×900); collapse navigation on narrow viewports, allow wide tables to scroll. Use text/icons as well as colors for states. No external fonts/assets required at runtime.

Connection strip: selected bench/mode, address, link state, bench state, observation age, last TIME acknowledgement. Separate backend connection from bench connection. MODE is user configuration; `team=SIM` is supporting information, not secure detection. No invented signal strength, flash-free space, physical current/position, clock offset or hardware interlock state.

### 7.2 Profile screen

Four stages within one flow: Source → Trim/map → Preview/validate → Upload. Display inspection before requiring a bench; show capabilities when connected. Gap shading, invalid channel badges and trim fields use source-relative time. Show connected output rows, source selector, name/serial, min/max, unmapped idle explanation. Show frame count versus capacity, actual replay duration, discarded remainder, checksum and short hash with copyable full value. Rate edits/mapping edits invalidate the draft preview; an existing compiled/uploaded profile remains visibly distinct from unsaved edits.

Upload card reports acknowledged frames, elapsed upload time, checksum result, Cancel/Stop behavior and errors. Do not automatically start after upload. A whole-log failure should lead directly to trim controls, not a generic error modal.

### 7.3 Dashboard

- Cards: bench state; current-run completed cycles/target; current frame progress; lifetime completed cycles; total bench running hours.
- Channel table: label, source mapping when known, commanded µs, fixed idle, shared bench hours, channel active hours, latest observation time. Unknown mappings remain unknown after takeover.
- Controls: Start, Pause or Resume, Stop, stopped-only target edit, stopped-only manual Apply, Reset counters with clear confirmation.
- Waveforms: compiled commanded profile with reported frame cursor when identity/rate known; received pulse samples over time otherwise. Label sparse telemetry; do not imply it captures every output frame.
- Current cycle progress = frame/frames, clamped to valid range. Completion is shown separately when target done resets frame to zero. Do not show 0% as a failed completion.
- Optional remaining-time estimate uses known profile rate, remaining frames/cycles and current state; label approximate; omit for continuous/unknown profile and pause the estimate when paused. STATUS does not supply rate.
- Recent events show receive time and clear descriptions: upload verified, started, paused, stopped, cycle observed, target reached, link lost/regained, reboot suspected, counters reset.

### 7.4 History and reports

Date and channel filters, sessions table, active-hour bar chart, events table, expandable session details, CSV export. Session details show source/profile identity, mapping/limits, checksum, target, counter observations, start/end bounds, stop cause and uncertainty. Export CSV fields include units and provenance; escape spreadsheet-formula-leading text cells in user labels/filenames.

Report milestone: generate a backend PDF for one session with source/profile hashes, bench capabilities, selected mappings, observed cycle/time results, command trace summary, date/coverage and reboot/reset limitations. Reports must use persisted data, not the current dashboard. Verify report layout and pagination with the PDF workflow when that feature is implemented.

### 7.5 Settings

Bench label, host, port default 3333, mode simulator/hardware, connect/disconnect. Show INFO fields and protocol version read-only. Last TIME request and acknowledgement, with a Retry time-sync action using the command scheduler. No serial-reset or virtual-USB !RESET button in the production UI. Keep test reset instructions in developer documentation.

## 8. Implementation milestones and acceptance gates

| ID | Work | Dependencies | Acceptance gate |
|---|---|---|---|
| M0 | Inspect artifacts, run supplied baselines, write plan/log | Supplied inputs | Completed in documentation phase; evidence linked |
| M1 | Backend skeleton, dependency lock, schema v1, Flutter shell, API conventions | User authorization to code | Health/snapshot work, DB reopens, shell navigation works; no fake live values |
| M2 | CSV importer/compiler, profile persistence and preview | M1 | Supplied inspection matches; golden 200-frame case gives 16982; deterministic tests pass |
| M3 | WDR parser/client/coordinator, serialized upload and operations | M1 | Official serve-sim receives exact profile; checksums/errors/state behavior pass |
| M4 | First real end-to-end path, session/counter records | M2+M3 | Flutter imports supplied log, compiles 40–44 s, uploads, START 1, observes completion and saved history |
| M5 | Full controls, reconnect/reboot/timeout handling, accounting boundaries | M4 | No repeated mutations, stale values explicit, counter history survives refresh/backend restart |
| M6 | History filters, charts, CSV export, usability | M5 | Filtered values match snapshots; incomplete coverage is visible |
| M7 | PDF report, finite ETA, production startup/README, demo rehearsal | M6 | Report verified; clean startup from documented commands; all core acceptance checks pass |
| M8 | Venue hardware compatibility and final demo | M7 + hardware slot | Read live INFO, run bounded test, compare OLED/STATUS, confirm Stop/reconnect/counters |

At each gate, update IMPLEMENTATION_LOG with changed areas, exact checks/results, failures, unresolved issues and next action. Do not mark a milestone complete merely because its UI exists. No speculative firmware changes if real hardware differs: document the discrepancy and adapt only within the published contract or explicit organizer clarification.

### 8.1 Test matrix

| ID | Scenario | Expected |
|---|---|---|
| C01 | Supplied file inspection | 9,074 rows, 14 channels, known duration/gap/channel classes |
| C02 | Duplicate/decreasing times, missing/ragged/non-numeric cells | Precise line/field error, no compiled profile |
| C03 | Unselected zero-only channels | Inspection warning; valid selected C1–C4 still compile |
| C04 | Selected zero/out-of-range/intermediate invalid sample | Compilation blocked even if resampling skips that sample |
| C05 | Trim inside/crossing gap; starting at post-gap sample | First two fail; last succeeds if otherwise valid |
| C06 | 30 Hz timing, exact boundaries, sub-frame window | Rational ZOH correct; no drift; <1 frame rejected |
| C07 | F=M and F=M+1; channels 1,4,8,16 in compiler fixtures | Exact capacity accepted, overflow blocked, index order correct |
| C08 | Golden sample [40,44), 50 Hz, C1–C4 | 200 frames, known first/last, SUM16=16982 |
| C09 | Repeat compile; change config/source | Stable hash for identical content, new revision otherwise |
| P01 | Fragmented/coalesced lines, CRLF, debug text | Correct framing and ordered dispatch |
| P02 | TEL/EVT before OK, DONE before START reply handling | Reply routed correctly; session evidence not lost/reordered backward |
| P03 | Delayed reply after timeout | Socket invalidated; late reply never attributed to next command |
| P04 | Bad/short vectors, malformed numbers, unexpected reply | Clear protocol failure, no corrupt state |
| P05 | Upload checksum mismatch, out-of-order F error, link loss | Start blocked; no automatic frame retry; fresh LOAD on retry |
| P06 | Stop during upload | Cancel remaining frames, await current reply/timeout, STOP after synchronization |
| R01 | One/three finite cycles and continuous mode | Bench count exact; DONE only finite; stopped centered outputs |
| R02 | Pause/Resume/SET/START invalid state | UI and backend agree; ERR STATE preserved if race occurs |
| R03 | 1475/1525 vs 1474/1526 µs profiles | Strict deadband; paused/manual time excluded; allow ~1–2 s rounding/timing tolerance |
| R04 | Link absent for ≥6 s during running | Playback/counters advance; TEL must be re-enabled on reconnect |
| R05 | Lost START reply, including short run completed before reconnect | No second START; success or uncertainty based on observations |
| R06 | Saved reboot via virtual USB | STOPPED, centered, saved counters retained, profile absent |
| R07 | Abrupt reset before checkpoint | Unsaved rollback visible; no automatic restart; old local observations preserved |
| R08 | Counter reset and ambiguous CLEAR | New boundary; no negative hours or deletion of history |
| D01 | Same request UUID/body twice; changed body same UUID | Single send/reused operation; conflict for changed body |
| D02 | Backend crash before/after send/DB commit | Pending outcome reconciled; never automatically resend |
| D03 | Browser refresh/multiple tabs/slow WebSocket | Same server state; serialized actions; resync after gaps |
| D04 | Date filter crossing a gap/reset/epoch | No prorating or cross-epoch negative deltas; coverage disclosed |
| D05 | Database unavailable during running | New risky mutations blocked; explicit Stop still attempted; audit failure visible |
| U01 | Laptop sizes, large table, validation navigation | No clipped critical controls; errors lead to editable field |
| U02 | CSV/PDF exports with unusual labels and unknown session fields | Valid outputs, no invented values, legible report |

Unit parser fixtures and controlled fake byte streams are allowed as test fixtures; do not build a replacement bench simulator. Use supplied serve-sim for integration, including real TCP and virtual USB resets. Keep fault injection helpers confined to tests.

### 8.2 Validation commands and isolation

Run the provided scorer in its own temporary directory, sequentially. Set a unique TMPDIR on macOS/Linux (or suitable temp environment on Windows) before starting each independent simulator. Reuse that directory only when intentionally testing persistence of that same bench. The default shared temp counter file must not cause cross-test pollution.

Reference commands from the workspace root, with output paths selected by the implementation test runner:

```text
python3 wdr_tool.py test --port sim --json <results.json>
python3 wdr_tool.py serve-sim --listen 3333 --usb-port 3334
python3 wdr_tool.py test --host 127.0.0.1 --serial tcp://127.0.0.1:3334 --json <results.json>
python3 wdr_tool.py soak --host 127.0.0.1 --minutes 30
```

The scorer/soak performs STOP, LOAD, START and possibly CLEAR/reset; it must not run concurrently with Athena on the same bench. It takes over the single TCP client. Hardware scorer/reset actions require a deliberate diagnostic session, not an automatic application startup check. Pyserial is needed for actual serial ports, not in-process/TCP simulator paths.

During implementation run backend unit/integration checks, flutter analyze, flutter test, flutter build web, then browser workflow checks. A soak is a later endurance check, not a substitute for application integration tests. Inspect JSON pass fields and totals even on exit code zero.

## 9. Demonstration, risks, and definition of done

### 9.1 Demo sequence

1. Start the official simulator and Athena; connect and show four channels/2,000-frame capacity from INFO.
2. Import RCOU.csv, show its zero channels and 23.5-second gap.
3. Select C1–C4 and relative 40–44 seconds at 50 Hz; show 200 frames and checksum 16982.
4. Upload, verify checksum, start three cycles. Show live commands and bench/active meters in seconds as well as hours.
5. In a separate endurance run, disconnect the controller long enough for cycles to continue; reconnect and reconcile counters without issuing another Start.
6. Pause and show held outputs with stable counters. Resume, then Stop; show 1500 µs and history.
7. Use a deliberate simulator reset through virtual USB after a saved checkpoint; show stopped state, retained saved counters and missing profile requiring upload.
8. Refresh/restart the dashboard/backend, reconnect, inspect persisted sessions/events and export evidence. Never claim a reboot automatically resumes the run.

### 9.2 Remaining constraints

- No missing mandatory development artifact remains. Physical bench availability, actuator-specific limits, event-network access and hardware INFO are venue checks.
- WDR cannot prove profile identity across takeover, exact event times during an outage, physical motion, or independent per-channel energized time. Preserve uncertainty rather than inventing missing fields.
- The newest manual defines 1–8 outputs and 10–100 frames/s. The simulator exercises only four channels. Compiler/UI fixtures can cover 16, but 16-channel real-protocol compatibility remains unverified until such firmware is supplied.
- Motor/ESC idle may not equal 1500 µs. The fixed WDR STOP behavior must be reviewed with the organizers before attaching unsuitable loads; the PC controller cannot override firmware idle semantics.
- Initial Flutter command inspection was sandbox-blocked while attempting to update the global SDK cache; resolve access normally when implementation requires Flutter checks. No SDK/package changes were made in this planning task.

### 9.3 Definition of done

Core is complete only when the supplied sample completes the browser-to-official-simulator workflow; all core acceptance tests pass; disconnect/restart/reset results remain honest; history survives app restart; exports reproduce stored observations; production build and startup instructions work; and the implementation log states exactly what was tested on simulator versus real hardware. Remaining optional scope and any protocol discrepancies must be explicit. The original supplied artifacts must retain their recorded hashes.
