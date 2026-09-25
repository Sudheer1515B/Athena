# Flight-log ingestion and deterministic 16-channel PWM profiles

## What inputs are actually present in the workspace?

### Takeaway
There are no supplied simulator files, protocol specification, or sample flight logs in the workspace as inspected on 2026-09-22. Build the importer and replay engine behind adapters, because the exact bench messages, acknowledgements, timing limits, safe-state behavior, and sample-log variants cannot yet be verified.

### Cited Findings
- Local inspection of `/Users/krisdreemur/Developer/SSN` found only `research_notes/`, `research_notes/Drone actuator life test bench/`, and `reports/`; all three directories contained no files before these research notes were written.
- PX4 defines ULog as a self-describing format containing the logged message definitions, and its parser requirements include ignoring unknown messages, rejecting unknown incompatibility bits, and tolerating a file cut off in the middle of a message. This supports schema discovery rather than filename/version-specific parsing. — [PX4 ULog format specification](https://docs.px4.io/main/en/dev_log/ulog_file_format)
- ArduPilot DataFlash logs contain `FMT` records that define message identifier, byte length, name, storage-format string, and column labels; `FMTU`, `UNIT`, and `MULT` records supply units and scaling. — [ArduPilot log-message reference](https://ardupilot.org/copter/docs/logmessages.html); [ArduPilot AP_Logger format README](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_Logger/README.md)

### Inferences
- **Recommended design:** define three replaceable boundaries now: `LogImporter -> CanonicalProfile -> BenchTransport`. When the missing assets appear, only the format-specific importer or bench adapter should need changes.
- **Recommended immediate action when assets arrive:** inventory filenames and hashes, run an importer dry-run that lists every topic/message and its fields, capture a simulator handshake, and add the supplied examples as immutable regression fixtures before changing conversion logic.

### Gaps
- Missing bench protocol: transport (HTTP/WebSocket/TCP/UDP), framing, endianness, PWM representation, maximum frame rate/profile size, clock ownership, ACK/NACK rules, CRC, retry semantics, abort/safe command, watchdog, and completion event are unknown.
- Missing simulator: connection setup, fault modes, timing tolerance, and whether it accepts an uploaded profile or requires live streaming are unknown.
- Missing sample logs: actual PX4/ArduPilot firmware versions, vehicle types, topics enabled, output buses, logging rates, dropouts, parameter records, and corrupt/truncated examples are unknown.

## How do PX4 ULog files represent actuator/servo commands and time?

### Takeaway
Prefer hardware `actuator_outputs` when it is present and demonstrably contains PWM microseconds: it is closest to the physical driver command. Use `actuator_servos` only as a normalized logical-command fallback with an explicit function-to-bench mapping and per-channel calibration; never treat `actuator_outputs_sim` as PWM.

### Cited Findings
- ULog is little-endian and self-describing. Every subscribed message has a `timestamp`; in the current specification it is `uint64_t` microseconds and must increase monotonically within the same subscription. The subscription also has a `multi_id`, because one message format can have multiple instances. — [PX4 ULog format specification](https://docs.px4.io/main/en/dev_log/ulog_file_format)
- ULog records logger dropouts explicitly with a duration in milliseconds; the format also exposes software version metadata such as `ver_sw`, `ver_sw_branch`, and `ver_sw_release`, as well as initial and changed parameters. — [PX4 ULog format specification](https://docs.px4.io/main/en/dev_log/ulog_file_format)
- `actuator_outputs` has `timestamp`, `noutputs`, and `float32[16] output`; only the first `noutputs` entries are valid and values are in the output driver's “natural output units.” The separate `actuator_outputs_sim` topic is documented as normalized `[-1, 1]` for SITL/HITL/SIH. — [PX4 ActuatorOutputs message](https://docs.px4.io/main/en/msg_docs/ActuatorOutputs)
- Current `actuator_servos` is the control allocator's normalized logical servo setpoint: up to 15 values in `[-1,1]`, with `1` maximum positive, `-1` maximum negative, and `NaN` disarmed. It includes command publication time and the source-sample time. — [PX4 ActuatorServos message](https://docs.px4.io/main/en/msg_docs/ActuatorServos)
- Firmware layout changed: PX4 v1.13 documented only eight entries in `actuator_servos`, while the current message has 15. PX4 v1.13 also described control allocation as supported but disabled by default, with mixer allocation as the alternative. — [PX4 v1.13 ActuatorServos](https://docs.px4.io/v1.13/en/msg_docs/actuator_servos); [PX4 v1.13 payload/control-allocation notes](https://docs.px4.io/v1.13/en/payloads/)
- Older PX4 actuator-control topics are intermediate controls, not physical PWM channels: v1.12's `actuator_controls` schema defines roll, pitch, yaw, throttle and other control indices and multiple control groups. — [PX4 v1.12 actuator_controls source schema](https://raw.githubusercontent.com/PX4/PX4-Autopilot/v1.12.3/msg/actuator_controls.msg)
- PX4 output functions map logical Motor 1…12 and Servo 1…15 to physical outputs; current PWM parameters include per-output min, max, center, disarmed value, function, and a reversal mask. PX4 specifically describes servo center as a bilinear-curve neutral point. — [PX4 actuator configuration](https://docs.px4.io/main/en/config/actuators); [PX4 parameter reference](https://docs.px4.io/main/en/advanced_config/parameter_reference)
- The official `pyulog` package parses ULog, exposes datasets by message name and `multi_id`, surfaces `data_list`, initial parameters and dropouts, and includes tools such as `ulog_info`, `ulog_params`, and `ulog2csv`. — [PX4 pyulog README](https://github.com/PX4/pyulog/blob/main/README.md); [PX4 pyulog core](https://github.com/PX4/pyulog/blob/main/pyulog/core.py)

### Inferences
- **Source ranking:** (1) real-hardware `actuator_outputs` whose values and bus configuration establish PWM microseconds; (2) `actuator_servos` plus logged `PWM_*_FUNCx`, min/center/max, reversal and user-confirmed bench wiring; (3) legacy intermediate `actuator_controls_*` only through a version/airframe-specific mixer implementation. Reject an automatic import if only option 3 exists.
- “Natural units” is intentionally broader than PWM. Detect a plausible PWM distribution (usually integer-like values within the bench's allowed microsecond range), show the units decision in the UI, and require the user to choose a conversion for DShot/CAN/normalized outputs. The message schema alone is insufficient evidence that the values are PWM.
- Treat each `actuator_outputs` `multi_id` as a separate source stream until the user or logged configuration identifies its bus and physical pins. Never concatenate instances merely by encounter order.
- Discover array width and field names from each log. Record `ver_sw*`, selected topic, `multi_id`, and relevant output parameters in profile provenance so a result is reviewable across PX4 versions.
- `actuator_outputs` and `actuator_servos` are commanded outputs, not feedback from the servo shaft. Life metrics derived from them quantify commanded/energized exposure; they do not prove motion, torque, stall, temperature, or mechanical travel.

```python
# Minimal PX4 extraction shape; production code must inspect all matching multi_ids.
from pyulog import ULog

ulog = ULog(path)
datasets = [d for d in ulog.data_list if d.name == "actuator_outputs"]
for d in datasets:
    t_us = d.data["timestamp"].astype("uint64")
    n = d.data["noutputs"].astype("uint32")
    # pyulog flattens arrays as output[0], output[1], ... in its data dict.
    rows = [[d.data[f"output[{ch}]"][i] for ch in range(min(int(n[i]), 16))]
            for i in range(len(t_us))]
```

### Gaps
- PX4 does not guarantee that hardware `actuator_outputs.output` is PWM microseconds; “natural output units” depends on the driver. The supplied logs and hardware/output configuration are needed to prove the conversion.
- The physical meaning of each `actuator_outputs` ULog `multi_id`, and whether the intended 16 channels span MAIN, AUX, CAN, or a simulator topic, cannot be determined without the actual log and configuration.
- It is unknown whether the sample logs contain final outputs, normalized allocator outputs, relevant parameters, or dropout records.

## How do ArduPilot DataFlash BIN/LOG files represent output commands and time?

### Takeaway
Use `RCOU.C1…C14` and `RCO2.C15…C16` as the first 16 physical output commands. They are already expressed as PWM pulse width in microseconds; parse column names and units from the log rather than assuming a fixed binary layout, and use `SERVOn_*` parameters to label and sanity-check the wiring.

### Cited Findings
- Current ArduPilot documents `RCOU` as servo output channels 1–14 and `RCO2` as channels 15–18. Each record has `TimeUS` in microseconds since system startup, and each channel field is in microseconds. `RCO3` extends the scheme to channels 19–32. — [ArduPilot Copter log-message reference](https://ardupilot.org/copter/docs/logmessages.html); [ArduPilot Plane log-message reference](https://ardupilot.org/plane/docs/logmessages.html)
- The ArduPilot source structure uses unsigned 16-bit channel fields for `RCOU` and `RCO2`, and its metadata calls them “Servo channel output values.” — [ArduPilot LogStructure.h](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_Logger/LogStructure.h)
- ArduPilot `.bin` logging is self-describing: `FMT` messages define records; `FMTU` connects fields to `UNIT` and `MULT` records. The AP_Logger documentation explicitly warns tools not to infer numeric scaling from the unit name. — [ArduPilot log-message reference](https://ardupilot.org/copter/docs/logmessages.html); [ArduPilot AP_Logger format README](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_Logger/README.md)
- DataFlash logs can use `.bin` or `.log`; the official `pymavlink` repository contains `DFReader.py` for log analysis, including binary and text DataFlash readers, field multipliers, parameter collection, and timestamp reconstruction. — [ArduPilot log-analysis documentation](https://ardupilot.org/dev/docs/common-downloading-and-analyzing-data-logs-in-mission-planner.html); [pymavlink DFReader.py](https://github.com/ArduPilot/pymavlink/blob/master/DFReader.py)
- `PARM` records contain `TimeUS`, parameter name, value, and board/config default. ArduPilot maps physical outputs through `SERVOn_FUNCTION`, and each output has configurable min/max/trim/reversal. — [ArduPilot LogStructure.h](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_Logger/LogStructure.h); [ArduPilot output-function mapping](https://ardupilot.org/plane/docs/common-rcoutput-mapping.html); [ArduPilot RC input/output architecture](https://ardupilot.org/dev/docs/learning-ardupilot-rc-input-output.html)
- The official `pymavlink` tools use `mavutil.mavlink_connection(...)` and `recv_match(...)` for log iteration, while the repository describes pymavlink as including tools for flight-log analysis. — [pymavlink repository](https://github.com/ArduPilot/pymavlink); [pymavlink mavgraph example](https://github.com/ArduPilot/pymavlink/blob/master/tools/mavgraph.py)

### Inferences
- Merge the two message streams by timestamp and channel number: `RCOU.C1…C14 -> bench 1…14`; `RCO2.C15,C16 -> bench 15,16`. A missing `RCO2` means channels 15–16 are unavailable, not zero.
- Preserve the recorded PWM values for wire-for-wire stress replay, then clamp them to both the bench hard limits and the engineer-approved per-channel envelope. `SERVOn_MIN/MAX/TRIM/REVERSED` are useful validation metadata; applying them a second time to `RCOU` would distort an already-scaled output.
- A zero, missing field, or value outside the bench's legal PWM range should become `invalid`, not a physical zero-microsecond pulse. Require a chosen safe/disabled behavior.
- Parse by record/column names because vehicle releases may add records or fields. Use the log's FMT/FMTU/UNIT/MULT metadata and retain firmware/vehicle metadata in provenance.
- Like PX4 outputs, `RCOU/RCO2` records are output commands. They are not actuator position/current/temperature feedback.

```python
# Minimal ArduPilot extraction shape.
from pymavlink import mavutil

log = mavutil.mavlink_connection(path)
events = []
while True:
    m = log.recv_match(type=["RCOU", "RCO2"])
    if m is None:
        break
    first, last = (1, 14) if m.get_type() == "RCOU" else (15, 16)
    events.append({
        "t_us": int(m.TimeUS),
        "values": {ch: int(getattr(m, f"C{ch}")) for ch in range(first, last + 1)}
    })
```

### Gaps
- No supplied ArduPilot log is available to confirm whether it is binary DataFlash, text DataFlash, or a telemetry log with a misleading extension. Detect content and emit a precise format error; do not route solely by extension.
- The actual output logging cadence, gaps, unused-channel encoding, firmware metadata, and presence of `RCO2`/`PARM` records remain unknown.

## How should recorded values become a safe, deterministic 16-channel PWM profile?

### Takeaway
Keep time as integer microseconds, normalize all imports to explicit physical-channel events, then resample with zero-order hold at the bench frame period. Interpolation, calibration, clamping, gaps, disabled channels, and safe state must all be visible decisions stored with the profile.

### Cited Findings
- PX4 requires per-subscription timestamps to be monotonic, expresses them in microseconds, and records logger dropouts in milliseconds. — [PX4 ULog format specification](https://docs.px4.io/main/en/dev_log/ulog_file_format)
- PX4 normalized servo values are `[-1,1]`, and `NaN` means disarmed; PWM min/max/center are individually configurable, with center supporting a bilinear output curve. — [PX4 ActuatorServos message](https://docs.px4.io/main/en/msg_docs/ActuatorServos); [PX4 actuator configuration](https://docs.px4.io/main/en/config/actuators)
- ArduPilot `RCOU`/`RCO2` values and `TimeUS` use microseconds, while its output layer has configurable min/max/trim/reversal. — [ArduPilot log-message reference](https://ardupilot.org/copter/docs/logmessages.html); [ArduPilot RC input/output architecture](https://ardupilot.org/dev/docs/learning-ardupilot-rc-input-output.html)

### Inferences
- **Canonical event input:** represent every observation as `{t_us:uint64, source_stream, updates:{physical_channel_1_based:pwm_us_or_invalid}}`. Sort by `(t_us, stable_source_order)`, reject decreasing time within a source, and resolve duplicate `(time,channel)` values with a documented “last source record wins” rule while emitting a warning.
- **Time origin:** after an engineer-selected crop, subtract the first included timestamp so `t_us=0`. Use integer arithmetic everywhere. Generate target ticks as `k * period_us`; never accumulate floating-point seconds, which can drift.
- **Normalized-to-PWM mapping:** for normalized servo command `x`, first apply `x = -x` when reversed, clamp to `[-1,1]`, then use the logged/configured asymmetric center:

```text
if x < 0: pwm = center_us + x * (center_us - min_us)
else:     pwm = center_us + x * (max_us - center_us)
```

  Round once to integer microseconds after mapping. Reject missing calibration. Treat `NaN` as disabled/safe, never as zero or as a point to interpolate through.
- **Resampling:** use zero-order hold (the most recent command at or before the target tick) because flight-controller output commands are held between updates. Linear interpolation invents intermediate commands and can hide steps; expose it only as an explicit experimental option, never the default. Fill time before a channel's first valid sample with its configured safe PWM or disabled state.
- **Alignment:** preserve asynchronous source updates as events, then sample all 16 channels onto the same target ticks. Do not match rows by array index across `RCOU`, `RCO2`, or PX4 multi-instances.
- **Gaps:** flag a source gap when it exceeds a configurable multiple (for example 3×) of that stream's median interval. Default to aborting profile generation across a recorded PX4 dropout or a large unmarked gap; if the engineer elects to continue, record whether the command is held or changed to safe state.
- **Clamping:** validate in layers: finite number; source-declared range; engineer-approved channel range; bench protocol range. Show every changed sample and the maximum correction. Reject a profile by default if clamping changes data; allow an explicit saved override for expected small excursions.
- **Channel mapping UI:** show logical name, source stream/field, physical source output, bench channel, function parameter, min/center/max, reversed flag, first/last/min/max value, invalid count and update rate. Provide a 16-lane step plot plus a cursor table before replay.
- **Profile identity:** hash the original file, canonical mapping/configuration, crop range, resampling method/period, and serialized frame bytes. Use that profile hash with every run record so life totals are auditable.

Recommended canonical profile (bench-wire serialization should remain a separate adapter until the protocol spec arrives):

```json
{
  "schema_version": 1,
  "profile_id": "sha256:...",
  "source": {
    "format": "px4_ulog|ardupilot_dataflash",
    "sha256": "...",
    "firmware": "...",
    "streams": ["actuator_outputs#0"],
    "start_source_us": 123456,
    "warnings": []
  },
  "timing": {
    "period_us": 20000,
    "duration_us": 4000000,
    "resample": "zero_order_hold"
  },
  "channels": [
    {
      "bench_channel": 1,
      "source": "RCOU.C1",
      "enabled": true,
      "safe_us": 1500,
      "min_us": 1000,
      "center_us": 1500,
      "max_us": 2000,
      "reversed": false
    }
  ],
  "frames": [
    {"seq": 0, "t_us": 0, "pwm_us": [1500, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null]}
  ]
}
```

- **Execution model:** prefer uploading the complete, hashed profile to the bench/simulator and issuing a scheduled `start`, so a bench monotonic clock owns PWM timing. If the protocol only streams frames, the server—not the browser—should use a monotonic scheduler, bounded look-ahead, sequence numbers, ACKs, a watchdog, and an explicit abort-to-safe message.
- **Life counters:** define a “completed cycle” as one bench-confirmed traversal of the entire profile under a unique `(run_id, loop_index)`. Increment exactly once after a completion ACK and make the operation idempotent. For each enabled channel, accumulate `running_us += acknowledged_interval_us` only for intervals the bench reports as executed with a valid PWM; derive hours as `running_us / 3_600_000_000`. Also store optional commanded travel `sum(abs(delta_pwm_us))`, motion time above a deadband, min/max PWM, and direction reversals; those are more informative wear proxies than wall time alone.
- **Failure behavior:** a disconnect, NACK, missed watchdog, simulator error, or user abort ends the current loop without incrementing cycles. Persist acknowledged progress and the reason. On reconnect, require a fresh start unless the protocol explicitly supports resume with verified bench state.

### Gaps
- The correct target period and legal PWM range must come from the protocol and attached actuators; `20,000 us`/50 Hz and `1000–2000 us` in the example are illustrative, not inferred requirements.
- Whether the bench supports per-channel disable, a neutral/safe value, onboard profile storage, timestamps, acknowledgements, execution telemetry, CRC, and resume is unknown.
- “Running hours” and “cycle” require product definitions. Energized time, commanded-motion time, full profile loops, and direction reversals answer different life questions; the UI should name each rather than silently choosing one.

## What web stack, fixtures, and acceptance criteria are credible for a Saturday hackathon?

### Takeaway
A small React/Vite UI with a Python FastAPI service is the lowest-risk route because the maintained parsers are Python packages. Keep the browser for upload, mapping, preview and status; let the service parse logs, build profiles, persist counters, and own the bench Wi-Fi link.

### Cited Findings
- `pyulog` is PX4's official Python ULog package and provides both a parser and conversion tools; `pymavlink` is ArduPilot's Python MAVLink/log-analysis package. — [PX4 pyulog](https://github.com/PX4/pyulog); [ArduPilot pymavlink](https://github.com/ArduPilot/pymavlink)
- FastAPI `UploadFile` uses a spooled file and exposes a file-like object, which is appropriate for potentially large binary uploads; FastAPI also supports sending/receiving text, binary and JSON over WebSockets. — [FastAPI file uploads](https://fastapi.tiangolo.com/tutorial/request-files/); [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- The browser File API can read user-selected files as binary, and it is available in workers. Transferable `ArrayBuffer` objects can move large binary data to a worker without copying. — [MDN File API](https://developer.mozilla.org/en-US/docs/Web/API/File_API); [MDN transferable objects](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Transferable_objects)
- Browser WebSocket provides bidirectional client/server communication but has no backpressure; MDN recommends `wss` for an HTTPS page and warns against mixed secure/insecure WebSocket content. — [MDN WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API); [MDN WebSocket client security](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications)

### Inferences
- **Hackathon architecture:**

```text
React/Vite UI
  POST /api/logs/import  -> FastAPI -> pyulog / pymavlink
  POST /api/profiles     -> validate, map, resample, hash
  POST /api/runs         -> bench adapter -> Wi-Fi simulator/test bench
  WS   /api/runs/{id}    <- ACK/progress/fault/completion events
                              |
                            SQLite
                  profiles, runs, per-channel totals
```

- Use one Python process for the demo: FastAPI + `pyulog` + `pymavlink` + built-in `sqlite3`; a React/Vite front end can be built into static files served by the same service. Avoid reimplementing either binary log parser in TypeScript during a short hackathon.
- Keep bench transport behind an interface such as `connect()`, `capabilities()`, `upload(profile_bytes)`, `start(run_id, loops)`, `abort()`, and an async event stream. Implement both `SimulatorAdapter` and `ProtocolAdapter`; contract-test them against the same expected events.
- Minimal database tables: `source_log(hash, metadata_json)`, `profile(id/hash, source_hash, config_json, frame_blob)`, `run(run_id, profile_id, requested_loops, completed_loops, status, started_at, ended_at, fault)`, and `channel_totals(channel, running_us, completed_profiles, travel_pwm_us, reversals)`. Update completion plus all channel totals in one SQLite transaction keyed by `(run_id, loop_index)`.
- The UI's critical path is: drop log -> choose detected output stream -> map up to 16 channels -> inspect warnings and plot -> dry run in simulator -> arm bench session -> run/pause/abort -> view cycles and hours. Keep parsing and profile creation usable without any bench connection.

Minimal fixtures that expose likely mistakes:

1. **Identity pulse:** all 16 channels have unique fixed values (`1101…1116 us`) so off-by-one and channel swaps are obvious.
2. **Boundary staircase:** exact min, center, max and one intentionally out-of-range value per channel; proves mapping, rounding and clamp/reject behavior.
3. **Asymmetric normalized servo:** `min=900, center=1470, max=2100`, samples `[-1,-0.5,0,0.5,1,NaN]`, plus reversed=true; catches incorrect midpoint and NaN handling.
4. **Irregular time:** timestamps `0, 7 ms, 21 ms, 21 ms, 58 ms` resampled at a known period; catches floating drift, duplicate policy and accidental linear interpolation.
5. **Split ArduPilot:** `RCOU` gives 1–14 and `RCO2` updates 15–16 at different times; catches row-index joins and missing-channel-to-zero bugs.
6. **PX4 multi-instance:** two `actuator_outputs` instances with distinct signatures and different `noutputs`; catches silent bus concatenation and reading array entries beyond `noutputs`.
7. **Gap/dropout:** a PX4 dropout or a large timestamp hole while outputs differ on each side; proves the importer blocks or records the chosen hold/safe policy.
8. **Corrupt/truncated/wrong format:** cut a valid log mid-record, mutate magic bytes, and provide a `.tlog` renamed `.bin`; proves content detection, bounded failure, and useful errors.
9. **Replay faults:** delayed ACK, duplicate ACK, NACK, disconnect mid-loop, reconnect, and duplicate completion; proves watchdog, abort-to-safe, and idempotent counters.

Acceptance criteria for the demo:

- Import reports source type, firmware metadata when present, chosen message/topic and instance, discovered channel count, source time range/rate, invalid values, gaps/dropouts, and all automatic decisions before enabling replay.
- A golden fixture converts byte-for-byte to a checked-in canonical profile; profile generation is deterministic across repeated runs.
- For every generated tick, each output equals the latest valid source command at or before that tick under zero-order hold; no enabled output exceeds its approved microsecond range; no disabled or missing value silently becomes `0 us`.
- Channels 1, 14, 15 and 16 pass unique-value end-to-end simulator assertions, covering the `RCOU`/`RCO2` boundary and 1-based/0-based mapping.
- Scheduled frame timestamps differ from `k*period_us` by zero in the serialized profile; simulator-observed dispatch should meet the tolerance supplied by the protocol spec and display measured jitter rather than claiming hard real-time behavior.
- The bench/simulator reports the same profile hash before start. Sequence gaps, stale run IDs, and unexpected ACKs stop the run.
- Completed cycles increment only after a unique completion ACK. Duplicate completion is ignored; abort/disconnect/NACK does not increment it. Per-channel `running_us` equals acknowledged execution time, survives restart, and is updated atomically with completion.
- Abort and watchdog fixtures produce the defined safe/disabled output within the simulator's specified deadline and leave a durable fault record.

### Gaps
- Dependency versions and operating system are not present in the workspace; pin them after the first successful parse of the supplied logs and simulator session.
- The protocol's real timing tolerance is unavailable, so an honest pass/fail threshold for Wi-Fi jitter cannot yet be stated.
- Browser-only direct bench control may be possible if the bench exposes HTTP/WebSocket, but a custom raw TCP/UDP protocol generally requires the server adapter; the missing protocol determines the answer.
