# Turn Flight Logs Into Traceable Endurance

## Problem statement

> Build a web-based controller that converts recorded drone flight logs into servo command profiles, replays them over Wi-Fi on a 16-channel PWM test bench, and tracks cycles completed and per-channel running hours so engineers can quantify actuator life. A bench simulator, protocol spec and sample logs are provided.

**Challenge provider:** Welkinrim Technologies  
**Hackathon date:** Saturday, 26 September 2026

**Executive recommendation.** Build the hackathon entry as a simulator-first, local web application with a Flutter Web front end, a FastAPI service, SQLite, and four strict adapters: `LogParser`, `ProfileCompiler`, `BenchTransport`, and `RunRepository`. Parse exactly one supplied log family well, compile it into an immutable 16-channel pulse-width profile, upload the complete hashed profile, and let the simulator or controller's monotonic clock replay it; browser timers are allowed to fire late and background tabs are throttled, so the browser must never be the servo-frame clock ([MDN timers](https://developer.mozilla.org/en-US/docs/Web/API/Window/setTimeout), [MDN Page Visibility](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)). Count a cycle only after the bench acknowledges the final watermark of one complete profile loop, and calculate per-channel hours only from acknowledged output-enabled intervals. The promised simulator, protocol specification, and sample logs are **not present in the workspace as of 22 September 2026**, so the current design is a proposed integration contract, not an analysis of those artifacts ([workspace](/Users/krisdreemur/Developer/SSN)). The strongest Saturday demo is an honest failure story: import and hash a log, reject one unsafe mapping, replay a corrected profile, drop Wi-Fi mid-loop, preserve partial exposure without inventing a cycle, reconnect without double-starting, and prove the totals survive a restart. This aligns with Welkinrim Technologies' public emphasis on validation, testing, integrated electric systems, and “100% traceability end-to-end,” while avoiding unsupported claims that command replay measures mechanical motion or formally qualifies actuator life ([Welkinrim](https://www.welkinrim.com/)).

## Missing artifacts make adapters the first deliverable

**Confirmed fact.** A fresh recursive inventory of `/Users/krisdreemur/Developer/SSN` found only the three research-note files used for this report. There is no simulator executable or source, protocol document, sample log, application source, package manifest, actuator datasheet, or project-level instruction file. Therefore no one can responsibly assert the real transport, PWM units, time base, channel numbering, acknowledgement behavior, safe-state command, or simulator fault interface yet.

Ask the organizer or Welkinrim contact for the following exact handoff before real integration. Record each file's SHA-256 digest immediately so the team can distinguish a changed artifact from a code regression.

| Artifact to request | Minimum information needed | First validation when it arrives |
|---|---|---|
| Bench simulator | Source or binary, OS/architecture, launch command, dependencies, bind address/ports, acceleration controls, reset behavior, fault-injection controls, example session | Launch from a clean checkout; capture capabilities/handshake; run one known command; deliberately disconnect and restart it |
| Protocol specification | Transport; framing; byte order; version negotiation; authentication; channel indexing; pulse representation and legal range; frame rate; profile size; clock owner; ACK/NACK and retry rules; sequence IDs; checksum/CRC; heartbeat/watchdog; pause, abort, safe state, reboot, reconnect, and completion semantics | Convert every normative field into a fixture; compare captured traffic with examples; document every mismatch before coding around it |
| Sample flight logs | Original binary files, log family and firmware/vehicle version, known-good and malformed examples, expected actuator topic/message, physical output mapping, units, start/end timestamps, dropouts, and expected converted values for a short window | List all topics/messages and instances; export the first known interval; hand-check channels 1, 14, 15, and 16 |
| Bench and actuator definition | Controller/PWM hardware, firmware, channel wiring, actuator manufacturer/model/serials, signal voltage, supply voltage, peak/stall current, pulse min/neutral/max, accepted frame rate, fail-on-signal-loss behavior, fixture/load, sensors, interlocks, and E-stop circuit | With actuator power removed, verify channel order, pulse width, frame rate, startup, watchdog, abort, and reboot on a scope or logic analyzer |
| Metric/test intent | What Welkinrim means by “cycle” and “running hour,” target test duration, pause policy, allowed acceleration, failure/degradation criteria, inspection interval, and whether totals belong to physical channels or replaceable actuator assets | Write a one-page metric glossary and get the challenge owner to accept the definitions before judges see totals |
| Hackathon constraints | Team size, judging rubric, required stack, network restrictions, hardware-access window, allowed packages, and expected deliverable | Freeze a P0 scope and rehearse on the actual presentation machine/network |

**Recommendation.** Keep a visible “Protocol assumptions” drawer in the app until those artifacts arrive. It should state `Simulator protocol v1`, channel indexing, command units, pulse/frame limits, acknowledgement granularity, heartbeat timeout, safe action, and any simulated-only behavior. Unknown units, protocol versions, message fields, channel numbers, or output ranges should block arming instead of being guessed.

### Welkinrim-specific positioning

**Sourced fact.** Welkinrim presents itself as an electric-propulsion and power-systems company serving UAV/eVTOL, marine, land, and robotics applications. Its public material emphasizes motors, ESCs, intelligent power systems, autopilot products, simulation validation, in-house testing, and end-to-end traceability ([Welkinrim](https://www.welkinrim.com/), [Welkinrim LinkedIn](https://in.linkedin.com/company/welkinrimtechnologies)). **Inference.** Frame the project as a traceability layer between recorded mission behavior and reproducible bench evidence. Put source-log hash, compiler version, asset serial, frozen limits, profile hash, delivered-command watermark, faults, and results on one run record. Do not rebrand servo command hours as motor or ESC endurance; extending the adapter/event-ledger pattern to propulsion systems would require the relevant power, thermal, torque/load, and speed measurements.

The pitch should say: **“Welkinrim builds hardware to survive the mission. This controller preserves the mission as a repeatable test stimulus and makes every delivered command, completed replay, exposure hour, and fault traceable to the actuator and test configuration.”** The responsible current claim is “traceable command exposure.” Avoid “certifies life,” “predicts remaining useful life,” “proves MTBF,” “measures shaft movement,” “flight qualified,” or “meets ISO/IEC qualification.” NIST reliability planning begins with the decision the test must support, then chooses test duration, units, stress, model, and decision risk; a few simulator runs cannot supply those missing elements ([NIST reliability planning](https://www.itl.nist.gov/div898/handbook/apr/section3/apr31.htm)).

## Deterministic conversion prevents false lifetime evidence

The narrow architecture below gives the team one complete vertical slice and isolates all unknowns behind replaceable boundaries.

```mermaid
flowchart LR
    UI [Flutter Web UI\nImport · Map · Arm · Review]
    API [FastAPI service\nRun coordinator + WebSocket]
    LP [LogParser\npyulog / pymavlink]
    PC [ProfileCompiler\nvalidate · resample · hash]
    DB [(SQLite\nevent ledger)]
    BT [BenchTransport interface]
    SIM [Provided or local simulator]
    HW [Real Wi-Fi bench]
    UI -->|same-origin HTTP/WS| API
    API --> LP --> PC
    API <--> DB
    API <--> BT
    BT --> SIM
    BT --> HW
```

**Recommendation.** Serve the UI and API from one local origin for the demo, such as `http://127.0.0.1:8080`, and use a same-origin WebSocket. A hosted HTTPS page connecting to `ws://192.168.x.x` encounters mixed-content and evolving browser local-network restrictions; cross-origin HTTP requires CORS, and a WebSocket server must separately validate the browser-supplied `Origin` ([RFC 6455](https://www.rfc-editor.org/rfc/rfc6455.html), [Chrome Local Network Access](https://developer.chrome.com/blog/local-network-access), [MDN WebSocket security](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications)). FastAPI is the lowest-risk weekend backend because the maintained PX4 and ArduPilot parsers are Python packages, it supports spooled uploads and WebSockets, and the built-in `sqlite3` module is enough for the ledger ([PX4 pyulog](https://github.com/PX4/pyulog), [ArduPilot pymavlink](https://github.com/ArduPilot/pymavlink), [FastAPI uploads](https://fastapi.tiangolo.com/tutorial/request-files/), [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)).

Flutter Web is a good fit for this dashboard-style application and supports HTTP plus bidirectional WebSocket communication; the official recipe uses `web_socket_channel` and exposes incoming messages as a Dart stream ([Flutter Web support](https://docs.flutter.dev/platform-integration/web), [Flutter WebSocket recipe](https://docs.flutter.dev/cookbook/networking/web-sockets)). Keep binary PX4/ArduPilot parsing and SQLite in FastAPI rather than rebuilding them in Dart or storing authoritative lifecycle totals in browser storage. In Flutter, use one API client, one WebSocket connection manager, typed protocol models, and a single application state store; coalesce high-rate telemetry before rebuilding widgets while processing every ACK and state transition. Build with `flutter build web` and serve `build/web` from the same FastAPI origin to simplify CORS, cookies, and local-bench access ([Flutter web deployment](https://docs.flutter.dev/deployment/web)).

### Flight-log traps to handle explicitly

| Source | Reliable starting point | Trap that must block or warn | Conversion decision |
|---|---|---|---|
| PX4 ULog | Prefer real-hardware `actuator_outputs` when its values and configuration prove PWM microseconds | Its values are in driver “natural output units,” not guaranteed microseconds; `multi_id` denotes separate instances; only the first `noutputs` entries are valid; `actuator_outputs_sim` is normalized `[-1,1]` | Keep each `multi_id` separate until mapped; require a units decision; never read beyond `noutputs` ([PX4 ActuatorOutputs](https://docs.px4.io/main/en/msg_docs/ActuatorOutputs)) |
| PX4 normalized servos | `actuator_servos` can be mapped with logged min/center/max, reversal, and output-function data | Current logs expose up to 15 values, older versions exposed eight; `NaN` means disarmed; these are logical setpoints, not measured positions | Discover the schema from the log, map by function, require calibration, treat `NaN` as disabled/safe ([PX4 ActuatorServos](https://docs.px4.io/main/en/msg_docs/ActuatorServos), [PX4 actuator configuration](https://docs.px4.io/main/en/config/actuators)) |
| PX4 legacy controls | Intermediate `actuator_controls_*` topics | Roll/pitch/yaw/throttle controls are not physical output channels and require the exact mixer/airframe behavior | Reject automatic import unless a version-specific mixer implementation and configuration are available |
| ArduPilot DataFlash | `RCOU.C1…C14` and `RCO2.C15…C16`, with `TimeUS`, are the first 16 output pulse commands in microseconds | `RCOU` and `RCO2` can update at different times; absent `RCO2` does not mean zero; binary layout and scaling come from `FMT/FMTU/UNIT/MULT` | Merge by timestamp and channel name, not row index; preserve pulse values; use `SERVOn_*` only to label and validate, not scale again ([ArduPilot log messages](https://ardupilot.org/copter/docs/logmessages.html), [AP_Logger format](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_Logger/README.md)) |
| Any log | Self-described timestamps, fields, units, and parameter records | Extension alone may be misleading; timestamps can duplicate, reverse, or contain gaps; a zero can mean invalid rather than a zero-width pulse | Detect by content, preserve integer microseconds, emit exact warnings, and require a selected missing-data policy |

PX4 ULog is self-describing, little-endian, and records logger dropouts; its timestamps are microseconds and must increase within a subscription. ArduPilot DataFlash similarly defines records through `FMT` and carries units/scaling metadata. That supports parser-driven schema discovery rather than hard-coded CSV column guesses ([PX4 ULog specification](https://docs.px4.io/main/en/dev_log/ulog_file_format), [ArduPilot AP_Logger](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_Logger/README.md)). In both ecosystems these fields are **commands**, not servo position, torque, temperature, or current feedback.

### One conversion pipeline should produce one immutable answer

Use this exact sequence:

1. Hash and store the original bytes; detect the format by content and record parser/version metadata.
2. Enumerate topics/messages, instances, fields, timestamp range, update rates, units, invalid values, and dropouts. Require the engineer to select the source stream when more than one plausible output exists.
3. Map source fields to 1-based physical outputs and then to bench channels and actuator assets. Disabled channels remain explicit `null`; they never become `0 us`.
4. Crop the selected interval, subtract the first included timestamp, and represent time as unsigned integer microseconds. Reject decreasing source time; resolve equal `(time, channel)` updates using one documented stable rule and emit a warning.
5. Convert normalized commands only with explicit per-channel calibration. For `x ∈ [-1,1]`, after optional reversal:

```text
if x < 0: pwm_us = center_us + x × (center_us - min_us)
else:     pwm_us = center_us + x × (max_us - center_us)
```

6. Resample onto `t_k = k × period_us` using zero-order hold: each tick takes the latest valid command at or before that tick. This matches held output commands and does not invent ramps. Linear interpolation should exist only as a named experimental profile revision.
7. Detect a gap using a configured rule such as `gap > 3 × median_source_interval`. Default to rejecting a recorded dropout or unresolved large gap. An engineer may create a new revision choosing hold-last or safe/disabled behavior, with that choice in the hash.
8. Validate finite values, source range, actuator min/max, bench hard limits, maximum step/slew, duration, frame count, and the last-to-first transition for looping. Report every affected `(channel, time, requested, permitted)` tuple. Reject by default rather than silently clamp.
9. Serialize deterministically and hash the exact stored profile bytes plus source hash, crop, mapping, calibration, sample period, missing-data policy, compiler version, and safety limits. Repeated conversion of the same inputs must be byte-identical.

The canonical representation should remain independent of the real bench's wire encoding:

```json
{
  "schema": "pwm-profile/1",
  "profile_sha256": "sha256:...",
  "source": {
    "format": "px4_ulog|ardupilot_dataflash",
    "sha256": "...",
    "firmware": "...",
    "streams": ["actuator_outputs#0"],
    "start_source_us": 123456,
    "warnings": []
  },
  "compiler": {
    "version": "0.1.0",
    "resample": "zero_order_hold",
    "gap_policy": "reject",
    "rounding": "nearest_integer_us"
  },
  "timing": {
    "period_us": 20000,
    "cycle_duration_us": 4000000
  },
  "channels": [
    {
      "index": 0,
      "enabled": true,
      "required": true,
      "source": "RCOU.C1",
      "asset_id": "servo-A-001",
      "safe_us": 1500,
      "min_us": 1000,
      "center_us": 1500,
      "max_us": 2000,
      "reversed": false,
      "max_step_us": 30
    }
  ],
  "frames": [
    {
      "seq": 0,
      "at_us": 0,
      "pulse_us": [1500, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null]
    }
  ]
}
```

The values above are illustrative; **50 Hz and 1000–2000 μs are not universal servo requirements**. Published products vary in pulse range, center, frame rate, and dead band, so the attached actuator's datasheet and the supplied protocol must define the real limits ([Pololu DS65HB specification](https://www.pololu.com/file/0J544/DS65HB.pdf), [Futaba GY701 manual](https://futabausa.com/wp-content/uploads/2018/09/GY701.pdf)).

### Playback must use absolute controller deadlines

Upload and validate the entire profile before arming. Let the bench or simulator schedule frame `i` of loop `k` from a monotonic origin:

```text
deadline_us(k, i) = start_us + k × cycle_duration_us + frame[i].at_us
lateness_us       = applied_controller_us - deadline_us(k, i)
```

Derive every deadline from `start_us`; never schedule the next frame as `now + delta`, which accumulates delay. Decode and validate before `ARM`, keep network/JSON/database work out of the timing callback, prefetch the next frame, and report late-frame count, maximum lateness, and last-applied sequence. ESP-IDF provides microsecond monotonic time and timer alarms suitable for a controller-side scheduler ([ESP Timer](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/esp_timer.html), [GPTimer](https://docs.espressif.com/projects/esp-idf/en/v5.1/esp32/api-reference/peripherals/gptimer.html)). If the supplied protocol only permits live streaming, the FastAPI service should own a monotonic scheduler with bounded look-ahead, explicit sequence numbers, acknowledgements, and a watchdog; the browser still only renders and sends coarse commands.

## Acknowledged events make cycles and hours auditable

**Recommendation.** Use HTTP for immutable resources and a single WebSocket subprotocol, `pwm-bench.v1`, for session state, idempotent commands, acknowledgements, telemetry, and faults. WebSocket supplies ordered messages and subprotocol negotiation, but application acknowledgements, idempotency, reconnect rules, and backpressure remain your responsibility ([RFC 6455](https://www.rfc-editor.org/rfc/rfc6455.html), [MDN WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)).

### Compact proposed protocol

```text
GET  /api/v1/capabilities
POST /api/v1/profiles                 # exact pwm-profile/1 bytes -> digest + validation
GET  /api/v1/profiles/{sha256}        # normalized summary
POST /api/v1/runs                     # reserve run UUID/config; idempotent request_id
GET  /api/v1/runs/{run_id}            # state, counters, faults
GET  /api/v1/runs/{run_id}/trace      # NDJSON or CSV
GET  /api/v1/ws                       # Upgrade: Sec-WebSocket-Protocol: pwm-bench.v1
POST /api/v1/sim/faults               # simulator build only
```

Every WebSocket application message is one UTF-8 JSON object:

```json
{
  "v": 1,
  "type": "COMMAND",
  "session_id": "session-uuid",
  "msg_id": "client-42",
  "sent_at_ms": 1789990000000,
  "body": {}
}
```

`msg_id` is unique per session. Repeating the same ID and body returns the cached `ACK` without executing again; reusing the ID with different content returns `DUPLICATE_CONFLICT`. An `ACK` contains `reply_to`, `ok`, `state`, `boot_id`, and either `result` or `{code, detail}`. Server events contain an increasing `event_seq` scoped to `boot_id`. A reconnect supplies the last `boot_id` and `event_seq`, then receives retained events or `snapshot_required`. Only one session holds the control lease; others may observe. A short-lived pairing token belongs in the first `HELLO`, because normal browser JavaScript cannot attach an arbitrary authorization header to the WebSocket constructor ([MDN WebSocket constructor](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/WebSocket)).

| Command | Preconditions | Acknowledged result |
|---|---|---|
| `HELLO {client_id, versions, token, last_boot_id, last_event_seq}` | New socket, permitted `Origin` | `WELCOME` with version, role, lease, heartbeat, state, `boot_id`; then `SNAPSHOT` or replay |
| `SELECT_PROFILE {sha256}` | `SAFE`; digest stored and valid | `READY` with profile summary |
| `ARM {sha256, run_config}` | `READY`; lease held; interlocks true; hashes frozen | `ARMED` and a single-use `arm_token` expiring in 10 seconds |
| `START {arm_token}` | `ARMED`; token, run UUID, and digest match | `RUNNING`, authoritative `run_id` and `start_us` |
| `PAUSE` | `RUNNING`; declared pause policy supported | Apply hold/neutral/disable policy, then `PAUSED` only after ACK |
| `RESUME` | `PAUSED`; interlocks true | Rebase future deadlines; never burst missed frames |
| `ABORT {reason}` | `ARMED`, `RUNNING`, or `PAUSED` | Apply configured safe action, persist partial exposure, then `SAFE` |
| `RESET_FAULT` | Cause cleared; outputs disabled | `SAFE`; never resumes |
| `RESET_ESTOP` | Physical E-stop released; other interlocks true | `SAFE`; never resumes |
| `PING` | Authenticated session | ACK with controller monotonic time |

```text
BOOT --self-test, outputs disabled--> SAFE
SAFE --validated digest selected----> READY
READY --ARM + all interlocks--------> ARMED
ARMED --START before expiry---------> RUNNING
RUNNING --PAUSE---------------------> PAUSED
PAUSED --RESUME---------------------> RUNNING
RUNNING --target loops complete-----> COMPLETE --acknowledge--> SAFE
ARMED/RUNNING/PAUSED --ABORT--------> SAFE
ANY --physical E-stop---------------> ESTOP
ARMED/RUNNING/PAUSED --fault--------> FAULT
FAULT/ESTOP --cause clear + reset---> SAFE
ANY --reboot------------------------> BOOT; outputs disabled; never auto-resume
```

Telemetry at 2–5 Hz is enough for the dashboard and should carry state, run/profile IDs, controller time, current/completed loop, cycle elapsed time, 16 requested and applied pulse values, last applied sequence, timing error, interlocks, and available electrical/thermal measurements. Coalesce display telemetry under load; never drop command acknowledgements or state transitions. With the recommended attended-demo policy, three missed one-second application heartbeats trigger the bench watchdog, safe action, and latched `FAULT(SUPERVISION_LOST)`. An unattended endurance policy that continues locally is a separate, explicitly approved configuration and requires a guarded rig and working physical E-stop.

### Cycles and running hours need exact formulas

There is no universal fatigue-cycle count for an arbitrary random load history; NIST notes that different counting methods produce different counts, with methods such as rainflow reducing histories for comparison with an appropriate fatigue model ([NIST cycle counting](https://nvlpubs.nist.gov/nistpubs/Legacy/IR/nbsir86-3055.pdf)). For the hackathon, define a **profile loop** as the product cycle and make the UI glossary unavoidable.

Let `R` be the immutable required-channel set, `W(k,c)` the acknowledged final command watermark for channel `c` in loop `k`, and `L` the set of unique durable loop-completion rows:

```text
loop_complete(k) = 1  iff  ∀ c ∈ R, W(k,c) is acknowledged
completed_profile_loops = |L|, where L has UNIQUE(run_uuid, loop_index)

channel_completed_loops(c)
  = count of loop indexes whose final command for channel c was acknowledged

command_active_us(c)
  = Σ over acknowledged enabled intervals j of max(0, end_us[j] - start_us[j])

command_active_hours(c)
  = command_active_us(c) / 3,600,000,000
```

The start boundary is the bench acknowledgement that channel output became enabled. The stop boundary is acknowledged disable/safe transition. If a pause holds valid pulses, active time continues while moving time stops; if pause disables output, neither advances. A disconnect, NACK, watchdog trip, user abort, or reboot preserves proven partial intervals but gives the incomplete loop zero global cycles. Never interpolate time across an unknown-state interval.

Optional wear descriptors can be computed without changing the main cycle definition: `commanded_moving_us` integrates intervals where delivered command changes beyond a declared deadband; `commanded_travel_us = Σ |pwm_n - pwm_(n-1)|`; a reversal counter uses slope-sign change plus minimum excursion and hysteresis. Store the algorithm version and thresholds. Call these **commanded** metrics. A pulse controller's reported position can merely be the pulse width being transmitted, not actual shaft position ([Pololu Maestro “Get Position”](https://www.pololu.com/docs/0j40/all)). `powered_hours`, actual position, current, torque, load, and temperature remain `NOT REPORTED` unless timestamped sensors measure them.

Actuator identity must be separate from physical output channel. Replacing a servo creates a new `asset_id`; past exposure stays with the old asset. “Reset” should append a baseline event with operator, reason, UTC time, prior total, and display offset; it should never erase lifetime history.

### An append-only ledger makes restarts explainable

Use SQLite on a local disk as the record of truth with `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON`, and unique idempotency constraints. SQLite transactions commit wholly or not at all, and WAL recovery occurs when the database reopens; WAL files must stay on the same host rather than a network filesystem ([SQLite atomic commit](https://www.sqlite.org/atomiccommit.html), [SQLite WAL](https://www.sqlite.org/wal.html), [SQLite synchronous](https://sqlite.org/pragma.html#pragma_synchronous)).

| Table | Essential fields and invariant |
|---|---|
| `source_logs` | `source_sha256 UNIQUE`, original name/bytes, imported UTC, parser/version, detected schema, warnings |
| `profiles` | `profile_sha256 UNIQUE`, source hash, compiler version, transform JSON, duration/frame count, immutable payload |
| `actuator_assets` | Asset ID/serial/model, installed/retired UTC, notes; identity never reused |
| `channel_map_snapshots` | Profile hash, bench channel, source field, asset ID, units, min/neutral/max, inversion, slew/deadband/reversal settings; immutable after arm |
| `runs` | `run_uuid`, campaign/parent, profile/map hashes, bench/protocol/firmware, requested loops, required mask, state, pause policy, boot IDs, UTC boundaries |
| `run_events` | `event_uuid`, run, monotonic `event_seq`, host UTC, host monotonic delta, bench tick/sequence, type/channel/payload, previous-event hash |
| `command_acks` | `UNIQUE(run_uuid, command_seq, channel)`, loop/frame, requested/applied value, bench tick, receipt time |
| `active_intervals` | Run/channel, start and end ACKs/ticks, close reason, duration; open intervals are explicit |
| `loop_completions` | `UNIQUE(run_uuid, loop_index)`, required mask, final ACK watermark, completed UTC |
| `faults` | Source/code/severity, first/last seen, state snapshot, affected channels, resolution |
| `counter_adjustments` | Asset/channel scope, metric, prior total, baseline offset, operator/reason/UTC |
| `channel_summaries` | Rebuildable projection of loops, active/moving time, travel, reversals, and last processed event |

Insert an ACK, close/open intervals, insert an eligible loop completion, update the checkpoint, and refresh summaries in one transaction. Derive cycles with `COUNT(*)` over unique completion rows and time with `SUM(duration_us)` over intervals; never trust a separately incremented display counter. On process start, move any persisted `ARMED/RUNNING/PAUSING/STOPPING` run to `RECOVERY_REQUIRED`, query the bench, and resume only if `run_uuid`, profile hash, loop, applied sequence, channel mask, `boot_id`, and output state all match. Otherwise apply/confirm safe state and create a linked recovery run. Export the source/profile hashes, mapping, thresholds, events, ACK watermarks, intervals, loop rows, faults, app/protocol versions, and CSV summary as one evidence bundle.

## Hardware safety defines the claim boundary

### Show four screens, not a generic dashboard

The UI should keep channel identity consistent across four screens and a persistent top bar.

| Screen | Minimum useful content |
|---|---|
| Import & inspect | Drop/file picker; original hash; parser/version; source type and firmware; topics/messages/instances; timestamps, rate, duration, units, gaps/dropouts, non-finite values; raw preview; actionable errors |
| Map & preview | One 16-row map: bench channel, source field, actuator asset, enabled/required, conversion, invert, neutral/min/max, slew, observed range, status; synchronized small-multiple step plots; shared cursor; gap/clip markers; last-to-first loop discontinuity |
| Verify & arm | Text-and-icon `PASS/WARN/FAIL/NOT REPORTED` checks for protocol/capabilities, hashes, uniqueness, limits, storage, rate/buffer fit, interlocks, and manual attestations; edits disarm; show active channels, loop duration/count, projected commanded hours, pause policy, and `SIMULATOR` or `REAL BENCH` badge |
| Run & review | Connection/state/run ID/last-ACK age/Stop; completed and current loop; 16-channel applied values and commanded hours; timing health; full-width fault banner with output state and counter consequence; event timeline, asset totals, hashes, and export after completion |

Use text or icons with color for status, label every control, and expose dynamic progress/errors as status messages; those patterns follow W3C accessibility guidance but do not by themselves establish conformance ([W3C color guidance](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color), [W3C form labels](https://www.w3.org/WAI/tutorials/forms/labels/), [W3C status messages](https://www.w3.org/WAI/WCAG21/Understanding/status-messages)). Label the web control **Stop/Abort**, not “E-stop.”

### Choose hardware only after measuring required resolution

If the supplied test bench already exists, use its documented adapter. If the team must assemble a bench, the weekend default is **an original ESP32 plus PCA9685** when its measured resolution is acceptable. The PCA9685 supplies 16 outputs, 12-bit PWM, one shared programmable frequency, update-on-STOP behavior, up to 1 MHz I²C, and an asynchronous active-low Output Enable pin ([NXP PCA9685 datasheet](https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf)). At 50 Hz its nominal pulse quantum is:

```text
20,000 us / 4096 = 4.8828125 us per count
```

| Hardware path | Advantage | Weekend decision |
|---|---|---|
| ESP32 + PCA9685 | Exactly 16 outputs, simple wiring, hardware OE, coherent multi-register update | **Default if a scope confirms pulse accuracy and ~4.88 μs resolution is adequate** |
| Original ESP32 LEDC | 16 native PWM channels and potentially finer resolution | Viable only with the original ESP32, 16 safe GPIOs, and measured cross-channel update behavior; Espressif lists fewer LEDC channels on several later variants ([Espressif LEDC](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html)) |
| ESP32 RMT | Precise waveform symbols and timer control | Do not choose as the sole 16-channel path; the classic ESP32 exposes eight RMT channels ([ESP-IDF RMT](https://docs.espressif.com/projects/esp-idf/en/v4.3.4/esp32/api-reference/peripherals/rmt.html)) |
| ESP32 + Mini Maestro 18 | 18 channels, 0.25 μs resolution, multiple-target serial command | Strong fallback if already available; still needs gateway, safety, and persistence integration ([Pololu Maestro](https://www.pololu.com/docs/0j40/all)) |

The PCA9685 is a logic/PWM driver, **not a 16-servo power supply**. Power controller logic and the actuator rail separately, join signal grounds deliberately, use a fused supply sized from measured simultaneous peak/stall current with margin, distribute current outside the ESP32/PCA board, and place bulk capacitance near the servo bank. Calibrate the PCA9685 oscillator or use a known external clock if absolute pulse accuracy matters. Verify one channel and then all 16 under load for pulse width, rail droop, reset/brownout, temperature, and jitter.

### Safety must remain independent of Wi-Fi and the browser

Machine guarding should prevent access to the actuator sweep/pinch zone, and an emergency stop should remove hazardous actuator energy independently of application software. OSHA's machine-guarding guidance requires guarding where a machine exposes people to injury, while ISO 13850 describes emergency-stop design principles; citing them guides the design but does not certify this rig ([OSHA guarding](https://www.osha.gov/etools/machine-guarding/introduction/general-requirements), [ISO 13850](https://www.iso.org/standard/59970.html)).

For real hardware, remove propellers and flight linkages, clamp the fixture, guard the motion envelope, strain-relieve cables, and place a normally closed mushroom E-stop outside the sweep zone. The E-stop/guard chain should de-energize the actuator rail through suitable switching **and** assert hardware Output Enable; an auxiliary contact should report its state. Releasing the E-stop only permits `SAFE`, followed by deliberate fault reset, arm, and start. Enforce pulse bounds, frame rate, step/slew, runtime/cycle maximums, channel mask, and watchdog in firmware. On missed deadline, I²C error, corrupt profile, overcurrent/temperature, brownout, or controller fault: disable output/power as designed, latch the fault, and require re-arm. ESP-IDF provides task/interrupt watchdogs and a brownout detector, but the finished behavior still needs bench testing ([ESP-IDF watchdogs](https://docs.espressif.com/projects/esp-idf/en/v5.4.2/esp32/api-reference/system/wdts.html), [ESP-IDF brownout behavior](https://docs.espressif.com/projects/esp-idf/en/release-v5.4/esp32/api-guides/fatal-errors.html)).

Commission in stages: logic analyzer with actuator power off; one unloaded actuator behind a guard at conservative limits; all channels at reduced limits while watching rail/current/temperature; then the intended load only after a competent local safety review. A web demo cannot prove fixture strength, current capacity, RF resilience, thermal margins, or formal life qualification.

## Friday-to-Saturday execution maximizes credible proof

### Friday: finish one path that survives restart

| Timebox | Build | Exit evidence |
|---|---|---|
| 0:00–0:45 | Inventory supplied artifacts; hash them; run/dump simulator; write assumption matrix and golden log fixture | Exact unknowns visible; one repeatable simulator launch |
| 0:45–1:45 | SQLite migrations, event append, run states, unique idempotency keys | Create run, append event, restart, read same ordered timeline |
| 1:45–2:45 | One real log parser and deterministic compiler | Same input/config produces identical profile bytes/hash |
| 2:45–4:15 | `BenchTransport`, simulator handshake, upload/select/arm/start/abort, sequence ACKs and watchdog | CLI/API runs two loops and injects a disconnect |
| 4:15–5:30 | Server state machine and transactional completion/interval accounting | Hand-calculated cycles and seconds match; duplicate ACK changes nothing |
| 5:30–7:00 | Minimal Import → Map/Preview → Arm/Run → History UI | Happy path completes without direct database edits |
| 7:00–8:00 | Kill/restart/refresh test; freeze known-good tag/build; record short fallback capture | Totals and faults are unchanged after restart |

### Saturday: make failure handling visible, then stop adding scope

| Timebox | Build | Exit evidence |
|---|---|---|
| 0:00–1:30 | Readiness checks, limits, frozen mapping/hash, explicit simulator badge | Unsafe profile cannot arm; edits disarm |
| 1:30–3:00 | Drop/duplicate/delay/reorder ACKs, Wi-Fi loss, reboot, recovery-required flow | Every fault yields the expected cycle/time and output-state label |
| 3:00–4:00 | 16-channel map/grid plus selected waveform or small multiples | Channels 1/14/15/16 remain identifiable end-to-end |
| 4:00–5:00 | Run history, asset totals, JSON/CSV evidence export | Judge can explain the run after a refresh |
| 5:00–6:00 | Run deterministic acceptance script; keyboard, 200% zoom, and color check | One command/checklist reproduces the evidence |
| 6:00–7:00 | Rehearse 90-second demo on presentation machine/network; capture backup video/screens | Pitch fits; local failure path works |
| 7:00 onward | Correctness/demo blockers only | No architecture expansion |

**P0 must ship:** one known log format; immutable profile/hash; 16-output mapping; simulator; idempotent command/ACK flow; limits; state machine; completed profile loops; per-channel commanded hours; SQLite history; disconnect injection; evidence export; simulator badge. **P1 only after P0:** moving time, command travel/reversals, campaign grouping, waveform hover, baseline events, comparison view. **Defer:** arbitrary log detection, multi-bench control, cloud accounts/sync, firmware updates, report designers, mobile polish, rainflow/fatigue damage, RUL/MTBF, and real hardware if its artifacts arrive too late.

### Acceptance and fault injection should be judge-visible

Create a four-second, four-channel golden profile with channels 5–16 disabled and two loops. Store the expected frames, loop watermarks, active seconds, moving seconds, travel, and reversals beside it. Add identity values `1101…1116 μs` for a separate channel-order fixture, an asymmetric normalized fixture, irregular timestamps, split `RCOU/RCO2`, PX4 multi-instances, a dropout, a truncated/wrong-format file, and deterministic replay faults.

| Test | Pass condition |
|---|---|
| Golden conversion repeated twice | Byte-identical profile and hash; every tick equals latest valid source value at or before the tick |
| Channels 1, 14, 15, and 16 | Unique values arrive at the matching simulator outputs, catching 0/1 indexing and `RCOU/RCO2` boundary bugs |
| Out-of-range point, excessive step, duplicate output mapping | Exact channel/time/value shown; readiness fails; no command reaches transport |
| Stop one ACK before loop watermark | No new global completed loop |
| Duplicate or reordered final ACK | Exactly one completion row and no duplicated interval/time |
| One required channel misses final ACK | No global loop; that channel has no channel-loop completion; all proven partial exposure remains |
| Pause with output disabled versus held | Disabled policy excludes active time; held policy includes active time but stops moving time; policy is visible |
| Lost `START` ACK and reconnect | Existing run is recovered from snapshot; no second motion/run is created |
| Wi-Fi loss or changed `boot_id` mid-loop | Safe/fault/unknown state shown; no extrapolated time; no partial cycle; fresh arm required unless exact state is proven |
| Backend killed around transaction commit | On reopen the transition is wholly present or absent; summaries rebuild to the same totals |
| Browser refresh and second control tab | Same authoritative run appears; second controller cannot acquire the active lease |
| E-stop/fault from every active state | Outputs disable according to simulator/verified bench deadline; reset returns only to `SAFE`; fault remains in history |
| Export and re-import evidence bundle | Hashes, events, loops, intervals, and totals reproduce without hidden mutable state |

SQLite itself tests atomicity with simulated crashes and I/O failures, which is the right mindset for this controller: the important demo is correctness around failure boundaries, not merely a moving chart ([SQLite testing](https://sqlite.org/testing.html)).

### The 90-second demo should lead with trustworthy failure

| Time | Script |
|---|---|
| 0–12 s | “A recorded flight is useful only if we can prove what was replayed, to which actuator, for how long, and what happened during faults.” Import the sample; show type, duration, source hash, parser, and warnings. |
| 12–27 s | Map four fields to four named assets. Set one maximum too low; show the exact offending channel/time/value and blocked Arm. Correct it; point out the new mapping/profile hash. |
| 27–43 s | “The simulator executes the immutable profile from its own monotonic clock.” Arm three loops and start. Show acknowledged values, completed loops, commanded hours, and timing health. |
| 43–58 s | Drop Wi-Fi during loop two. Show latched fault, safe or explicitly unknown output state, one completed loop, and preserved partial active time. |
| 58–73 s | Reconnect through snapshot/recovery. Inject a duplicate completion ACK; show that the unique ledger prevents double-counting. Finish remaining campaign loops in a linked run. |
| 73–86 s | Refresh/restart the service. Open History and show source/profile hashes, two attempts, fault timeline, exact actuator totals, and export bundle. |
| 86–90 s | “Today this quantifies traceable command exposure. With Welkinrim's real protocol and measured current, temperature, load, and position, the same ledger supports controlled actuator endurance campaigns.” |

The differentiator is uncertainty discipline: network loss never becomes optimistic lifecycle data. Judges should be able to ask for the exact formula, inspect the completion row, see how the simulator adapter becomes the real adapter, and understand why replacing an actuator preserves the old asset's totals.

### Risk register

| Risk | Likelihood / impact | Mitigation | Demo fallback |
|---|---|---|---|
| Simulator/spec/logs remain missing | High / High | Adapter boundaries, golden fixture, visible assumptions; request artifacts now | Complete local simulator contract; make no real-bench claim |
| “Cycle” remains ambiguous | High / High | Glossary, versioned formula, separate profile-loop and reversal metrics | Show unique loop-completion ledger rows |
| Browser timing/background throttling | Medium / High | Controller/backend monotonic scheduler | Local simulator runs independently of tab |
| Wi-Fi retry repeats motion/counts | Medium / High | Run UUID, `msg_id`, command sequence, unique ACK/completion keys, snapshot before resend | Fault and restart from safe loop boundary |
| Bench state cannot be proven after loss | Medium / High | Watchdog and bench journal if supported; otherwise unknown-state fault | Simulator stops on heartbeat loss |
| Unsafe conversion reaches hardware | Medium / High | Compile-time reject, frozen bounds, firmware hard limits, staged commissioning | Simulator only |
| Supply/current/thermal limits unknown | High / High | Require datasheet values and measurement before energizing | Do not connect actuators |
| Counter drift on crash | Medium / High | Append-only intervals/completions and atomic transaction | Restart proof during demo |
| Telemetry overwhelms UI/storage | Medium / Medium | Coalesce latest display value, bound queues, keep ACK/state lossless | Reduce simulator telemetry to 2 Hz |
| Multiple operators/tabs contend | Medium / Medium | One server-side control lease | Observers remain read-only |
| 16 traces are unreadable | High / Medium | Small multiples/shared cursor or one selected plot plus 16-row table | Selected-channel plot plus table |
| Team chases analytics | High / Medium | Enforce P0/P1/defer gate | Demo loops, hours, faults, and provenance only |
| Pitch implies qualification | Medium / High | Say “command exposure”; mark unmeasured fields `NOT REPORTED` | Include limitation in UI/export |

### Source-linked completion checklist

- [ ] Original simulator, protocol, logs, actuator data, and scoring rubric are received, hashed, and preserved; assumptions remain visible until verified.
- [ ] PX4 import discovers message definitions, timestamp/dropout records, `multi_id`, `noutputs`, and natural units from the file rather than filename guesses ([PX4 ULog](https://docs.px4.io/main/en/dev_log/ulog_file_format)).
- [ ] ArduPilot import uses `FMT/FMTU/UNIT/MULT`, merges `RCOU` and `RCO2` by timestamp, and never turns a missing channel into zero ([ArduPilot AP_Logger](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_Logger/README.md)).
- [ ] Profile generation uses integer microseconds, zero-order hold, explicit gap/NaN behavior, frozen per-channel limits, wrap validation, deterministic serialization, and a SHA-256 digest.
- [ ] Browser, API, and WebSocket share an origin for the demo; the server validates WebSocket `Origin` and requires a pairing/session credential ([RFC 6455](https://www.rfc-editor.org/rfc/rfc6455.html)).
- [ ] Timing runs from controller/simulator monotonic absolute deadlines; measured lateness is exported; DOM timers never drive servo frames ([MDN timers](https://developer.mozilla.org/en-US/docs/Web/API/Window/setTimeout)).
- [ ] `START`, command, ACK, and loop completion are idempotent across retry/reconnect; changed `boot_id` forces safe recovery.
- [ ] Completed loops and commanded hours are derived from unique ledger rows and acknowledged intervals; unknown time is never filled in; measured/powered fields stay unavailable without sensors.
- [ ] SQLite is local, transactional, recoverable, and restart-tested; source/profile/map hashes and fault history export with results ([SQLite WAL](https://www.sqlite.org/wal.html)).
- [ ] Hardware pulse range, frame rate, channel order, startup, pause, abort, watchdog, reboot, and Wi-Fi-loss behavior are verified with actuator power off before staged energization.
- [ ] The PWM driver does not carry aggregate actuator current; supply sizing, grounding, fusing, guarding, OE, physical E-stop, and reset-without-restart are independently reviewed ([NXP PCA9685](https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf), [OSHA guarding](https://www.osha.gov/etools/machine-guarding/introduction/general-requirements)).
- [ ] The demo proves rejection, disconnect, duplicate ACK, restart persistence, and evidence export; its claim remains “traceable command exposure,” not formal life qualification ([NIST reliability planning](https://www.itl.nist.gov/div898/handbook/apr/section3/apr31.htm)).

## Conclusion

The key engineering insight is that the lifecycle feature is not the counter on the dashboard; it is the chain of evidence from immutable source bytes through explicit conversion decisions to acknowledged output intervals and durable loop watermarks. That chain lets an engineer distinguish a finished test from a partial attempt, a physical actuator from a reused channel number, and measured behavior from commanded behavior even after a disconnect or crash.

For Saturday, breadth would weaken the entry. One log type, four visibly mapped actuators on a 16-channel-capable path, one correct profile compiler, one state machine, and one restart-proof ledger can demonstrate the architectural core. The supplied artifacts should change adapters and capability values, not the product's evidence semantics; if they arrive too late, the honest simulator-first implementation remains a coherent demo and a precise integration plan.
