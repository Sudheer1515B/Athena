# 16-channel Wi-Fi PWM bench protocol, simulator, and safety

## What was actually provided in the workspace?

### Takeaway
The workspace was empty at the start of this research pass. No simulator, protocol specification, sample flight logs, source tree, hidden project files, or `AGENTS.md` were present under `/Users/krisdreemur/Developer/SSN`, so the design below is a proposed compatibility target rather than an interpretation of supplied artifacts.

### Cited Findings
- Local inspection ran both `rg --files -uu .` and `find . -maxdepth 4 -type f`; each returned no file paths. This is direct workspace evidence, not a web-sourced claim.

### Inferences
- Treat the proposed `pwm-bench.v1` protocol below as an MVP contract. When the real simulator/spec/logs appear, first write an adapter to their formats rather than changing the UI, state machine, and life-accounting semantics at the same time.
- The most consequential unknowns are the supplied log schema and the supplied bench protocol. They determine channel mapping, timestamp units, whether values are normalized commands or pulse widths, and whether the existing simulator already defines safety behavior.

### Gaps
- Missing: simulator command, source, or URL.
- Missing: protocol specification, including transport and message framing.
- Missing: sample logs and their units, time base, channel names, arming records, and missing-data rules.
- Missing: actuator/servo model numbers, allowed frame rates, pulse ranges, neutral or failsafe behavior, supply voltage, stall current, load fixture, and intended life-cycle definition.

## What browser and local-network constraints shape the design?

### Takeaway
For a hackathon, serve the web UI from the simulator/controller origin and open a same-origin WebSocket. A cloud-hosted HTTPS UI talking to a bare `ws://192.168.x.x` device encounters mixed-content and evolving Local Network Access restrictions; cross-origin HTTP also requires CORS, while a WebSocket server must separately validate the browser-supplied `Origin`.

### Cited Findings
- Cross-origin `fetch()` defaults to `mode: "cors"`; request and response bodies are streams, and response bodies are exposed as `ReadableStream` objects. — [MDN: Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
- The standard browser `WebSocket` constructor accepts a URL and optional subprotocol list. It does not expose a general custom-header argument, so an `Authorization` header cannot be attached by normal browser JavaScript. — [MDN: WebSocket constructor](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/WebSocket); [WHATWG WebSockets](https://websockets.spec.whatwg.org/)
- Browser WebSocket handshakes include an `Origin`; RFC 6455 says a server that does not validate it accepts connections from anywhere, and may reject an unacceptable origin with HTTP 403 before upgrading. — [RFC 6455, sections 4.1 and 4.2.2](https://www.rfc-editor.org/rfc/rfc6455.html)
- MDN advises against an insecure WebSocket from an HTTPS page; production HTTPS pages should normally use `wss:`. — [MDN: Writing WebSocket client applications](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications)
- Chrome's Local Network Access work gates public-site access to local/loopback destinations on a user permission restricted to secure contexts. The associated draft says WebSocket handshakes should be subject to the same permission model. Browser rollout and constructor support have changed over time, so this is not a sound cross-browser MVP dependency. — [Chrome: Local Network Access](https://developer.chrome.com/blog/local-network-access); [WICG Local Network Access draft](https://wicg.github.io/local-network-access/); [MDN: Local network access](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Local_network_access)
- Browser timers are allowed to fire late when the main thread or operating system is busy, and inactive tabs are throttled. — [MDN: `setTimeout()` late timeouts and inactive tabs](https://developer.mozilla.org/en-US/docs/Web/API/Window/setTimeout); [MDN: Page Visibility API](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)
- The classic `WebSocket` API has no automatic backpressure; `bufferedAmount` reports data queued by `send()` but not yet transmitted. — [MDN: WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API); [MDN: `bufferedAmount`](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/bufferedAmount)
- ESP-IDF includes a lightweight HTTP server with WebSocket support and pre-handshake callbacks suitable for authentication or authorization checks. — [ESP-IDF HTTP Server](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/protocols/esp_http_server.html)

### Inferences

Recommended deployment order:

1. **Simulator demo:** run one local server such as `http://127.0.0.1:8080`; it serves the SPA, `POST /api/v1/profiles`, and `ws://127.0.0.1:8080/api/v1/ws`. This removes CORS, TLS certificate, mixed-content, and discovery issues from the demo.
2. **Bench demo:** have the controller serve the same static SPA and API at `http://pwm-bench.local/` or its AP address. Navigate to it as a top-level page and keep API/WS same-origin.
3. **Later hosted UI:** use a signed local gateway/native helper or a controller with a trusted TLS identity. If cross-origin HTTP is unavoidable, return an exact `Access-Control-Allow-Origin`, handle `OPTIONS`, and allow only the required methods/headers. Validate `Origin` independently on the WebSocket handshake.

Authentication recommendation for the MVP: place a short-lived pairing token in the first application `HELLO`, because the browser cannot attach an arbitrary WebSocket authorization header. Do not put a long-lived secret in the WebSocket URL, where it can enter logs and history. Until `HELLO` succeeds, the device must accept no control messages. A device-hosted same-origin UI can instead use an `HttpOnly`, `SameSite=Strict` session cookie issued by a pairing POST.

Transport comparison:

| Choice | Strength | Limitation | MVP use |
|---|---|---|---|
| HTTP request/response | Simple upload, explicit status codes, size limits, and resumable chunks | Polling for live state is clumsy | Upload profiles and fetch capabilities/results |
| HTTP response streaming/SSE | Simple one-way event feed; Fetch exposes a readable response stream | Commands still need separate requests; reconnect semantics need event IDs | Acceptable fallback for telemetry |
| WebSocket | Ordered, full-duplex command/ack/telemetry channel with broad support | No built-in backpressure; browser auth headers are constrained | Control, acknowledgement, faults, and status |
| Device-timed batch replay | Network jitter cannot move individual PWM deadlines after validation | Requires device storage, validation, and a scheduler | Required execution model; combine with HTTP upload and WebSocket supervision |

### Gaps
- Browser/version matrix for the hackathon machines is unknown. Test the exact Chrome/Safari/Firefox version and network topology before Saturday.
- Controller discovery is unspecified. `.local` requires mDNS support; a fixed AP address is simpler but less friendly.
- It is unknown whether the supplied simulator already binds a port or serves a web UI.

## Where should replay timing live, and how should a profile be scheduled?

### Takeaway
Upload and validate the whole replay profile before arming, then execute it from the controller's monotonic clock. The browser should render status and send coarse control commands; it must never stream one servo frame at a time as the timing source.

### Cited Findings
- `esp_timer_get_time()` returns microseconds since ESP Timer initialization, and ESP Timer exposes alarms on that same time base. — [ESP-IDF ESP Timer](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/esp_timer.html)
- ESP-IDF GPTimer supports dynamically updated alarm values in its interrupt callback. Its documentation warns that flash operations can defer the interrupt unless the IRAM-safe option is enabled. — [ESP-IDF GPTimer](https://docs.espressif.com/projects/esp-idf/en/v5.1/esp32/api-reference/peripherals/gptimer.html)
- ESP-IDF NVS provides wear leveling and atomic updates under sudden power loss, but its documented recommended use is configuration that changes infrequently rather than frequent, large logging. — [ESP-IDF file-system considerations](https://docs.espressif.com/projects/esp-idf/en/v5.5-rc1/esp32/api-guides/file-system-considerations.html); [ESP-IDF NVS internals](https://docs.espressif.com/projects/esp-idf/en/latest/esp32c6/api-reference/storage/nvs_flash.html)

### Inferences

Use an **absolute-offset, step-hold profile**, not browser arrival times and not a chain of relative delays:

```json
{
  "schema": "pwm-profile/1",
  "profile_id": "6d7a3d96-7b31-4b23-9db8-51721ebad18e",
  "name": "sample-flight-A",
  "pwm_hz": 50,
  "cycle_duration_us": 120000000,
  "repeat_count": 100,
  "disconnect_policy": "neutral_stop",
  "channels": [
    {"index": 0, "enabled": true, "min_us": 1100, "neutral_us": 1500, "max_us": 1900, "max_step_us": 30}
  ],
  "frames": [
    {"at_us": 0, "pulse_us": [1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500]},
    {"at_us": 20000, "pulse_us": [1510,1490,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500,1500]}
  ]
}
```

Required validation before the profile becomes `READY`:

- Schema and protocol versions are supported; exactly 16 channel definitions and 16 pulse entries per full frame.
- `at_us` values are unsigned, strictly increasing, first value is zero, and last value is less than `cycle_duration_us`.
- Every enabled pulse is finite and within both the device hard limit and the narrower per-actuator configured limit. Disabled channels must use `null`, not a magic pulse width.
- `pwm_hz`, profile duration, repeat count, frame count, upload size, and projected total runtime are within advertised capabilities.
- Adjacent commands obey each channel's configured slew/step limit, including the last-to-first transition when repeating. Either reject a violation or expand it into bounded intermediate frames during conversion; never silently clamp it on the controller.
- The server computes a SHA-256 digest over the exact stored bytes and returns it with a normalized summary. `ARM` names that digest, preventing a validated profile from being replaced between review and start.
- Reject duplicate JSON keys, unknown safety-critical fields, integer overflow, timestamps that exceed 64-bit arithmetic, and trailing or incomplete upload data.

Scheduler recommendation:

```text
start_us = monotonic_now_us + 500_000
for cycle k and frame i:
    deadline = start_us + k * cycle_duration_us + frames[i].at_us
    arm one-shot hardware timer for deadline
    on alarm, hand the prevalidated frame index to a high-priority PWM writer
    record applied_us - deadline
    if lateness exceeds the configured safe threshold: FAULT and apply failsafe
```

Derive every deadline from `start_us`; do not compute the next deadline as `now + delta`, because that accumulates scheduler delay. Decode/validate before `ARM`, prefetch the next frame, keep network/JSON/flash writes out of the timing callback, and expose `late_frame_count`, `max_lateness_us`, and `last_applied_at_us` in telemetry.

The converter should resample raw log values into pulse widths before upload. It should make channel mapping, units, interpolation, missing-sample behavior, clipping, and sign inversion visible in a conversion report. The controller implements step-hold only for the MVP so that the file fully determines the output.

For life accounting, maintain 64-bit microsecond counters in RAM and checkpoint them on full-cycle completion, pause/abort/fault, graceful shutdown, and at a coarse interval such as 60 seconds. The interval bounds power-loss undercount while avoiding flash writes at servo-frame frequency. Store a version, monotonic journal sequence, counters, and CRC/commit marker; NVS supplies the underlying atomic update and wear distribution.

Define metrics precisely:

- `completed_profile_cycles`: increment only when an entire `cycle_duration_us` finishes. An aborted or faulted partial cycle does not count.
- `partial_cycle_elapsed_us`: retained separately for diagnostics.
- `channel_commanded_us`: time while that channel was enabled and valid pulses were actually being emitted; exclude `PAUSED`, `FAULT`, `ESTOP`, and output-disabled time.
- `channel_powered_us`: only claim this if actuator-rail or per-channel power feedback exists.
- `motion_cycles`: optional offline metric derived from a declared rule, such as a full low-high-low excursion with hysteresis. Do not equate one uploaded-log repeat with one mechanical reversal cycle.

### Gaps
- The allowed playback acceleration is unknown. Real hardware should default to 1×; accelerated time belongs in the simulator unless the fixture and actuator limits explicitly permit it.
- The required timestamp fidelity and acceptable application jitter are unspecified.
- It is unknown whether logs contain actuator commands, mixer outputs, normalized `[-1,1]` values, angles, or measured positions.

## Which 16-channel PWM hardware path is practical?

### Takeaway
The lowest-risk weekend build is an ESP32 plus a PCA9685 breakout if roughly 4.88 microsecond pulse granularity at 50 Hz is acceptable. A classic ESP32 can expose 16 LEDC PWM channels directly with potentially finer granularity, but other ESP32 variants expose fewer channels. RMT is excellent for precisely timed waveforms but the classic ESP32 has only eight RMT channels. A Mini Maestro 18 is a strong fallback when one is available.

### Cited Findings
- Espressif's current Arduino-ESP32 documentation lists 16 LEDC channels on the original ESP32, 8 on ESP32-S2/S3/P4, and 6 on ESP32-C3/C5/C6/H2; frequency and duty resolution share timer resources. — [Espressif Arduino-ESP32 LEDC](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html)
- ESP-IDF documents that LEDC frequency and duty resolution are interdependent and supplies `ledc_find_suitable_duty_resolution()` for a requested frequency and clock. — [ESP-IDF LEDC for ESP32](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/ledc.html)
- ESP-IDF's original ESP32 RMT documentation describes eight channels; the newer driver can synchronize the start of multiple allocated TX channels and lets the application choose tick resolution. — [ESP-IDF RMT legacy channel count](https://docs.espressif.com/projects/esp-idf/en/v4.3.4/esp32/api-reference/peripherals/rmt.html); [ESP-IDF RMT driver](https://docs.espressif.com/projects/esp-idf/en/v5.1.5/esp32/api-reference/peripherals/rmt.html)
- The PCA9685 provides 16 channels, 12-bit PWM, one shared programmable frequency, approximately 24–1526 Hz output frequency, a 1 MHz Fast-mode Plus I²C interface, and an asynchronous active-low Output Enable pin. Changes can be latched at the I²C STOP condition, and each channel uses 12-bit ON/OFF counts. — [NXP PCA9685 datasheet](https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf)
- The PCA9685 datasheet rates `LEDn` as logic/LED-driver outputs, with per-pin and total-package current limits; it is not a sixteen-servo power supply. — [NXP PCA9685 datasheet, limiting/static characteristics](https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf)
- Pololu's Mini Maestro 18 has 18 channels, 0.25 microsecond pulse-width resolution, configurable pulse rate, USB/TTL serial control, a multiple-target command, and startup/error output behavior. — [Pololu Maestro User's Guide](https://www.pololu.com/docs/0j40/all)
- Servo timing is model-specific: one published digital servo accepts 800–2200 microseconds with a 2 microsecond dead band, while Futaba documentation includes servo combinations using 1520 or 760 microsecond centers and frame rates from 70 to 570 Hz. — [D65HB servo specification](https://www.pololu.com/file/0J544/DS65HB.pdf); [Futaba GY701 manual](https://futabausa.com/wp-content/uploads/2018/09/GY701.pdf)

### Inferences

| Path | Why choose it | Main caveat | Weekend verdict |
|---|---|---|---|
| ESP32 + PCA9685 | Exactly 16 outputs, two signal wires, hardware OE, synchronized multi-register update | 12-bit pulse granularity and one frequency for all channels | Best default if measured resolution is acceptable |
| Original ESP32 LEDC direct | 16 native channels and no I²C write window | Must select the original ESP32, allocate 16 safe GPIOs, and test cross-group update skew | Good when finer timing matters and wiring is ready |
| ESP32 RMT direct | Explicit waveform symbols, tick resolution, synchronized TX groups | Eight channels on original ESP32; target variants differ | Do not choose as the sole 16-channel generator for this weekend |
| ESP32 + Mini Maestro 18 | Fine 0.25 microsecond resolution, multiple-target serial command, mature servo controls | Additional board and serial integration; safety/persistence still belong in the ESP32/gateway | Best fallback if already on hand |

At 50 Hz, the PCA9685 period is 20,000 microseconds, so one of 4096 counts is `20,000 / 4096 = 4.8828125 microseconds`. A 1000–2000 microsecond command span therefore has only about 205 distinct steps. That can be coarser than the dead band of some digital servos, so measure the actual output and actuator response before committing. The internal oscillator's nominal value should also be calibrated with an oscilloscope or logic analyzer; if absolute pulse accuracy is important, use the PCA9685 external clock or calibration value.

For PCA9685 updates, enable auto-increment and configure update-on-STOP, write all channel registers in one transaction, and hold every `LEDn_ON` at zero unless intentional phase staggering is required. At 400 kbit/s, a roughly 65-byte register transaction consumes about 1.5 ms before software overhead; this fits a 20 ms frame but must be scheduled and measured. The chip itself supports 1 MHz I²C, but the complete board, pull-ups, wiring, and MCU driver must all support the selected bus rate.

Treat logic and actuator power as separate domains: controller/PCA `VDD` powers logic, while a separately fused supply sized from the actual actuators powers the servo rail. Join signal grounds deliberately, use short ground returns or a distribution board, add bulk capacitance near servo banks, and never route aggregate servo current through the ESP32 or PCA9685 logic rail. Size the supply from measured peak/stall behavior with margin; the actuator datasheets and fixture determine the correct value.

Hardware selection gate before coding:

1. Confirm each servo's accepted center, min/max pulse, frame rate, signal voltage, operating voltage, and stall current from its datasheet.
2. Put one real channel on a scope/logic analyzer; verify frequency, min/neutral/max pulse, startup, pause, abort, watchdog reset, and Wi-Fi-loss behavior.
3. Then load all 16 channels and observe rail droop, reset/brownout events, temperature, and pulse jitter.

### Gaps
- Exact bench controller board and PWM device are absent, so pin mapping, I²C address, OE wiring, and achievable bus rate are unknown.
- Required pulse resolution cannot be judged without actuator models and the original log quantization.
- Supply and fuse sizing cannot be specified without voltage and peak/stall-current data for all attached actuators.

## Which operational and electrical safety controls are essential?

### Takeaway
Use layered safety: physical guarding and a hardwired energy-removing stop, hardware output disable, controller-side bounds and watchdogs, explicit arming, and no automatic restart. A web `ABORT` button is a useful command but is not the emergency stop.

### Cited Findings
- OSHA's general machine-guarding guidance says machines exposing a person to injury at the point of operation must be guarded so body parts cannot enter the danger zone during the operating cycle. — [OSHA machine-guarding general requirements](https://www.osha.gov/etools/machine-guarding/introduction/general-requirements)
- ISO 13850 specifies functional requirements and design principles for emergency-stop functions independent of the form of energy; it remains current according to ISO's catalog. — [ISO 13850:2015](https://www.iso.org/standard/59970.html)
- OSHA-hosted hazardous-energy training material summarizes emergency-stop principles: the stop overrides other functions, removes power to actuators that can create a hazard as quickly as possible without creating another hazard, and reset must not initiate restart. — [OSHA-hosted LOTO manual](https://obis.osha.gov/dte/grant_materials/fy11/sh-22230-11/LOTOManual.pdf)
- The PCA9685 active-low OE input asynchronously disables outputs into a configured logic/high-impedance state, providing a hardware-level signal inhibit independent of I²C traffic. — [NXP PCA9685 datasheet](https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf)
- ESP-IDF provides interrupt and task watchdogs; the task watchdog can monitor selected tasks and detect a task that stops yielding. — [ESP-IDF Watchdogs](https://docs.espressif.com/projects/esp-idf/en/v5.4.2/esp32/api-reference/system/wdts.html)
- ESP32 has a built-in brownout detector enabled by default in ESP-IDF and can reset when supply voltage drops below a safe level. — [ESP-IDF fatal errors: brownout](https://docs.espressif.com/projects/esp-idf/en/release-v5.4/esp32/api-guides/fatal-errors.html)

### Inferences

Minimum bench controls:

- Remove propellers and flight-critical linkages. Clamp the actuator/load fixture, cover pinch/sweep zones with a guard, strain-relieve every cable, and keep people outside the motion envelope.
- Wire a normally-closed mushroom E-stop and guard/interlock chain so opening it de-energizes the actuator rail through a suitable relay/contactor or load switch **and** drives PCA9685 OE inactive. Feed an auxiliary contact back to the controller for telemetry. A controller crash must not defeat this path.
- E-stop release only permits transition to `SAFE`; it never returns to `ARMED` or resumes. Require deliberate `RESET_FAULT`, then a fresh `ARM`, then `START`.
- Make the safe action configurable by actuator: immediate power cut, stop pulses, or bounded ramp to a declared neutral followed by output disable. A ramp is inappropriate if continuing motion is hazardous or controller power is failing; the hardwired stop always wins.
- Require hardware signals `estop_ok`, `guard_closed`, `actuator_power_ok`, and optionally `fixture_ready` before `ARM`. Add a physical keyed enable or hold-to-arm input if movement can hurt someone.
- Enforce pulse min/max, frame rate, maximum change per update, maximum cycle count/runtime, and channel enable mask in firmware. The web app may preview these checks but is not the authority.
- Use a high-priority control task and watchdog. On missed scheduler deadline, I²C error, invalid internal state, overcurrent, overtemperature, brownout/reset cause, or corrupt profile: assert OE/power stop, enter a latched fault, persist the reason, and require manual re-arm.
- Fuse the actuator supply and, preferably, servo banks or individual channels. Add reverse-polarity protection, a main disconnect, visible power/armed/run indicators, and current/temperature monitoring. Put the E-stop within reach but outside the sweep zone.
- Run the first test with no actuator power and a logic analyzer; then one unloaded actuator behind a guard; then all channels at reduced limits; only then the intended load profile.

Life-data honesty:

- PWM commands prove that the bench asked an actuator to run; they do not prove shaft motion, delivered torque, or energized time. Label command-only metrics `commanded hours`.
- For stronger evidence, record actuator-rail presence and total current. True per-channel powered hours require per-channel switching/current feedback or an equivalent sensor. Mechanical-cycle validation requires position/encoder feedback or a defined offline command-based proxy.
- Log the profile digest, firmware version, bench ID, actuator serial/channel mapping, bounds, supply voltage, start/end UTC supplied by the client, controller monotonic duration, pause/fault intervals, completed cycles, and timing-error statistics. These fields make results auditable.

### Gaps
- A competent local safety review is still required for the actual fixture, energy level, and workplace rules. The cited standards do not by themselves validate a hackathon assembly.
- Actuator fail-on-signal-loss behavior is unknown; some actuators may hold, coast, or behave differently.
- There is no information about load cells, encoders, current sensors, thermal sensors, guard switches, or power contactors in the provided bench.

## What small, complete wire protocol and state machine can be built over a weekend?

### Takeaway
Use HTTP for immutable profile upload and results, plus one WebSocket subprotocol (`pwm-bench.v1`) for session handshake, idempotent commands, acknowledgements, telemetry, and faults. A single controller owns the bench; all safety checks and run state live on the device/simulator.

### Cited Findings
- RFC 6455 provides ordered messages over the WebSocket connection, an application subprotocol negotiation mechanism, ping/pong control frames, a closing handshake, and an origin-based browser security model. Application meaning, acknowledgements, and replay semantics must be defined above it. — [RFC 6455](https://www.rfc-editor.org/rfc/rfc6455.html)
- The WebSocket server may choose exactly one offered subprotocol, which the browser exposes as `WebSocket.protocol`. — [MDN: Writing WebSocket servers](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_servers)

### Inferences

HTTP surface:

```text
GET  /api/v1/capabilities
POST /api/v1/profiles                 body: pwm-profile/1 JSON; returns digest + validation summary
GET  /api/v1/profiles/{sha256}        returns summary, not necessarily all frames
GET  /api/v1/runs/{run_id}            returns final or current counters/faults
GET  /api/v1/runs/{run_id}/trace      NDJSON or CSV trace
GET  /api/v1/ws                       WebSocket upgrade; require subprotocol pwm-bench.v1
```

Capabilities example:

```json
{
  "api": 1,
  "device_id": "bench-01",
  "firmware": "0.1.0",
  "channels": 16,
  "pwm_hz": {"min": 24, "max": 333, "selected": 50},
  "pulse_us": {"hard_min": 500, "hard_max": 2500, "quantum_us": 4.8828125},
  "max_frames": 250000,
  "max_profile_bytes": 8388608,
  "clock": {"unit": "us", "width_bits": 64},
  "features": ["pause", "profile-sha256", "estop-input", "oe-output", "sim-fault-injection"]
}
```

All WebSocket application messages are one UTF-8 JSON object. Common envelope fields:

```json
{
  "v": 1,
  "type": "COMMAND",
  "session_id": "b95f...",
  "msg_id": "client-42",
  "sent_at_ms": 1789990000000,
  "body": {}
}
```

Rules:

- `msg_id` is unique per client session. The server caches the last bounded set of command outcomes; a repeated `msg_id` returns the same `ACK` without executing twice.
- `ACK` includes `reply_to`, `ok`, current `state`, `boot_id`, and either `result` or a stable error `{code, detail}`.
- Server events include increasing `event_seq` scoped to `boot_id`. A reconnect sends `last_event_seq`; the server returns retained events or `snapshot_required`.
- WebSocket/TCP ordering is useful but not a substitute for idempotency across reconnects. Never resend a non-idempotent `START` under a new ID merely because its ACK was lost; reconnect and read the snapshot first.
- Accept exactly one control lease. Other sessions are read-only observers. Lease acquisition returns `lease_id` and expires on the stated heartbeat policy.

Handshake:

```json
-> {"v":1,"type":"HELLO","msg_id":"c1","body":{"client_id":"web-7","versions":[1],"token":"pairing-token","last_boot_id":null,"last_event_seq":null}}
<- {"v":1,"type":"WELCOME","reply_to":"c1","session_id":"s1","boot_id":"boot-93","body":{"selected_version":1,"role":"controller","heartbeat_ms":1000,"state":"SAFE","capabilities_url":"/api/v1/capabilities"}}
<- {"v":1,"type":"SNAPSHOT","event_seq":1,"boot_id":"boot-93","body":{"state":"SAFE","interlocks":{"estop_ok":true,"guard_closed":true},"active_run":null,"counters":{}}}
```

Commands and required conditions:

| Command | Allowed state/condition | Result |
|---|---|---|
| `SELECT_PROFILE {sha256}` | `SAFE`, valid stored digest | `READY` |
| `ARM {sha256, run_config}` | `READY`, all physical interlocks true, control lease held | `ARMED`; issues `arm_token` expiring in 10 s |
| `START {arm_token}` | `ARMED`, token/profile digest match | `RUNNING`; returns authoritative `run_id` and `start_us` |
| `PAUSE` | `RUNNING`, profile permits pause | Apply configured pause-safe action, then `PAUSED` |
| `RESUME` | `PAUSED`, interlocks true | `RUNNING` with deadlines rebased; no missed frames are burst out |
| `ABORT {reason}` | `ARMED`, `RUNNING`, `PAUSED` | Apply failsafe, persist partial result, then `SAFE` |
| `RESET_FAULT` | `FAULT`, fault source cleared, outputs disabled | `SAFE` |
| `RESET_ESTOP` | `ESTOP`, physical E-stop released and interlocks true | `SAFE`; never resumes |
| `PING` | Authenticated session | `ACK` including controller monotonic time |

State machine:

```text
BOOT --self-test, outputs disabled--> SAFE
SAFE --select validated digest------> READY
READY --ARM + all interlocks--------> ARMED
ARMED --START before token expiry---> RUNNING
ARMED --expiry/ABORT----------------> SAFE
RUNNING --PAUSE---------------------> PAUSED
PAUSED --RESUME---------------------> RUNNING
RUNNING --cycle target reached------> COMPLETE --acknowledge--> SAFE
RUNNING/PAUSED/ARMED --ABORT--------> SAFE
ANY --hardware E-stop--------------> ESTOP
ARMED/RUNNING/PAUSED --fault--------> FAULT
FAULT/ESTOP --source clear + reset--> SAFE
ANY --reboot------------------------> BOOT (outputs disabled; never auto-resume)
```

Telemetry at 2–5 Hz is enough for the UI and should contain:

```json
{
  "v": 1,
  "type": "TELEMETRY",
  "boot_id": "boot-93",
  "event_seq": 302,
  "body": {
    "state": "RUNNING",
    "run_id": "run-a4",
    "profile_sha256": "...",
    "controller_us": 123456789,
    "cycle_index": 12,
    "cycle_elapsed_us": 3420000,
    "completed_profile_cycles": 12,
    "commanded_us": [1234,1234,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    "output_us": [1510,1490,null,null,null,null,null,null,null,null,null,null,null,null,null,null],
    "timing": {"late_frames": 0, "max_lateness_us": 31},
    "interlocks": {"estop_ok": true, "guard_closed": true, "power_ok": true},
    "electrical": {"bus_mv": 6000, "total_ma": 820, "board_c": 41.2}
  }
}
```

Reconnect and heartbeat policy:

- The controller run never depends on browser timer cadence. A hardware/control-task watchdog always remains active.
- Make supervision policy explicit in `run_config`: `neutral_stop` for attended demos and `continue_bounded` only for an approved guarded endurance rig with a working physical E-stop. Do not infer policy from a dropped socket.
- With `neutral_stop`, missing three 1-second application heartbeats asserts the configured failsafe and latches `FAULT(SUPERVISION_LOST)`. With `continue_bounded`, the run continues locally and the reconnecting UI only observes; it never restarts or rewinds.
- On reconnect, compare `boot_id`, retrieve a snapshot, and show whether the original run is still active. A changed `boot_id` proves a reboot; the controller comes up `SAFE` and marks any interrupted run incomplete.

Stable error codes for the MVP: `UNAUTHENTICATED`, `FORBIDDEN_ORIGIN`, `LEASE_HELD`, `BAD_STATE`, `BAD_VERSION`, `PROFILE_NOT_FOUND`, `PROFILE_HASH_MISMATCH`, `PROFILE_INVALID`, `INTERLOCK_OPEN`, `ARM_EXPIRED`, `DUPLICATE_CONFLICT`, `LIMIT_VIOLATION`, `TIMING_OVERRUN`, `PWM_IO`, `SUPERVISION_LOST`, `OVERCURRENT`, `OVERTEMP`, `ESTOP_ACTIVE`, and `INTERNAL`.

### Gaps
- If the provided protocol uses UDP, MQTT, protobuf, CBOR, or a fixed binary packet format, implement this state machine above that transport but preserve the simulator-facing semantics.
- Authentication strength and threat model are not specified. An isolated bench AP and a corporate LAN need different provisioning.
- Pause semantics are actuator-dependent. The safest pause value might be last value, neutral, disabled signal, or removed power.

## How should the simulator mirror the bench, and what is the Saturday MVP plan?

### Takeaway
The simulator should be a drop-in implementation of the same HTTP/WS contract, state machine, validators, counters, and faults. Build against it first, then replace only the PWM and interlock adapters when hardware arrives.

### Cited Findings
- ESP-IDF's own WebSocket server support includes an echo-server example on a local network, so matching a conventional HTTP/WebSocket simulator surface to firmware is supported by the platform. — [ESP-IDF HTTP Server](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/protocols/esp_http_server.html)

### Inferences

Simulator contract:

- Serve the SPA and API from one process/origin.
- Implement real-time mode and deterministic accelerated virtual time (`1x`, `10x`, `100x`). Accelerated time affects only the simulated actuator clock, not protocol timeouts.
- Use the exact same profile JSON Schema and validation error codes as firmware. If possible, generate validators from one schema and keep golden request/response fixtures in both projects.
- Model 16 commanded outputs, PWM quantization, controller clock, state, interlocks, cycle counters, running-time counters, persistence checkpoints, and `boot_id` changes.
- Write an append-only trace with `applied_controller_us`, expected deadline, lateness, cycle index, 16 requested widths, 16 quantized/applied widths, state, and fault flags. Allow CSV/NDJSON download.
- Add simulator-only `POST /api/v1/sim/faults` for deterministic injection: `estop`, `guard_open`, `power_loss`, `reboot`, `overcurrent`, `overtemp`, `i2c_nack`, `late_tick`, and `wifi_drop`. Advertise this only through the `sim-fault-injection` capability.
- Seed any random jitter and return the seed with results so failures replay exactly.
- Never let simulator-only endpoints exist in production firmware builds.

Contract tests that provide the most value:

1. Invalid pulse or non-monotonic timestamp is rejected and cannot be armed.
2. Duplicate `START` with the same `msg_id` yields one run and the same ACK.
3. Lost ACK + reconnect returns the existing `run_id`; it does not start again.
4. E-stop from every state disables outputs and reset returns only to `SAFE`.
5. Releasing E-stop, reconnecting Wi-Fi, or rebooting never auto-resumes.
6. A two-cycle profile increments the full-cycle counter exactly twice; abort halfway leaves two complete cycles plus partial elapsed time.
7. Disabled/paused/fault time is excluded from per-channel commanded time.
8. A deliberately late scheduler event records lateness and crosses the configured fault threshold.
9. Profile digest selected at `ARM` is the digest executed at `START`.
10. A simulated power cycle loses no completed-cycle checkpoint and reports the interrupted run.

Saturday build order:

1. **Freeze the contract:** capabilities, profile schema, states, command envelopes, and five safety error codes. Do not start with charts.
2. **Make the simulator pass one happy path:** upload → validate → select → arm → start → telemetry → complete. Add abort and E-stop immediately afterward.
3. **Build the log converter:** parse one known sample format, map columns to 16 channels, resample, enforce bounds/slew, preview min/max and duration, and emit `pwm-profile/1` plus a conversion report.
4. **Build the controller page:** connection/interlock banner, file conversion summary, per-channel bounds, profile plot/table, arm/start/pause/abort controls, current cycle, elapsed time, timing health, and 16 running-hour counters. Make `ARMED`, `FAULT`, and `ESTOP` visually unmistakable.
5. **Add persistence/results:** final run record and downloadable trace. Checkpoint counters at cycle and state boundaries.
6. **Swap in hardware:** keep HTTP/WS/state code, replace the simulator output adapter with PCA9685/LEDC/Maestro and real interlock reads. Verify on a logic analyzer before connecting actuators.
7. **Demo faults:** show bounds rejection, Wi-Fi loss policy, E-stop, reconnect without duplicate start, and persistent completed cycles. These prove the design more convincingly than a decorative dashboard.

Definition of done for the hackathon:

- One supplied/sample log deterministically converts to a reviewed 16-channel profile.
- A profile hash is uploaded and cannot run until validation, explicit arm, and start.
- Replay timing continues from the controller/simulator clock while the UI tab is busy or disconnected according to the declared policy.
- Abort, E-stop, fault, and reboot all disable outputs and never auto-resume.
- The UI reconnects to the authoritative active run without double-starting.
- Completed cycles and per-channel **commanded** time survive a simulated reboot; measured/powered time is only shown when corresponding feedback exists.
- Trace output proves frame order, applied pulse quantization, deadline error, state changes, and the exact profile digest.

### Gaps
- The real simulator's invocation and acceleration/fault controls are unavailable, so the proposed simulator endpoints may need an adapter.
- The actual sample log may require a different parser and channel calibration workflow.
- Hardware-in-loop success criteria need a measured jitter bound, current/temperature limits, and actuator-specific safe action.
