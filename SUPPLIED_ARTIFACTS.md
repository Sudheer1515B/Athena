# Supplied Artifact Findings

This file records the concrete inputs supplied by Welkinrim Technologies for Athena. Treat the original files as immutable evidence and use their SHA-256 values below to detect accidental changes.

**Updated 25 September 2026:** the official tool is now present and verified. Current implementation decisions are in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md); execution evidence is in [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).

## Authority order

When the files disagree, use this order:

1. [`WDR_Manual_and_Protocol.pdf`](WDR_Manual_and_Protocol.pdf) for the actual wire protocol and bench behavior. It labels WDR Protocol v1 as frozen for Hackinfinity 2026.
   [`wdr_tool.py`](wdr_tool.py) is the executable simulator/conformance reference; source quirks are documented below and in the plan, rather than silently overriding the published contract.
2. [`one_pager_A_controller.pdf`](one_pager_A_controller.pdf) for the competition problem, required product features, and judging rubric.
3. The four HTML files for visual and interaction references. They are static mockups, not a protocol definition.
4. [`RCOU.csv`](RCOU.csv) as the supplied source-log example.

Athena should discover the connected bench's channel count and storage limit from `INFO`; do not hard-code either the one-pager's 16 channels or the manual's example values.

## Artifact inventory and hashes

| File | Purpose | SHA-256 |
|---|---|---|
| `wdr_tool.py` | Official simulator and conformance/client utilities | `3059c64229a677d40d5f1e6d63081a277ebe01934809099f17acb1fcdf6971e4` |
| `WDR_Manual_and_Protocol.pdf` | Frozen WDR protocol v1 and user manual | `50fb853c38c2684e70130f139747504d1f2b7174200bdcdb6fd3a702b566bdbc` |
| `one_pager_A_controller.pdf` | Competition A problem statement and judging rubric | `2e81590b1c141fe1754e735d3ac5f3a4ce9f940004daf435d2b0d2cb6df2e4f2` |
| `RCOU.csv` | Sample ArduPilot-style servo-output log | `8b9d117be6e4c6f9c316d880e06ba4c5c5a7d736807206b49a6a0c10209dfc1f` |
| `01_dashboard.html` | Static dashboard design reference | `47d9af57aff2871b7de181920111458b9c93c4fab6d3a08fff2f915ac4918bf0` |
| `02_profile_import.html` | Static import/mapping design reference | `ea431d7d4a08e612a48b8c9208621f5c04fb2869b4d1eda9585fd1067f5d943a` |
| `03_history.html` | Static history/report design reference | `47567723f5185a198afca1f4aafc83512f214a8355f0337abe2850bd76d6d208` |
| `04_oled_and_wiring.html` | Firmware OLED and hardware wiring reference | `91dc90996f217ccad0d6ad2a78d97f651aaea5a699afdc634b0ed8a39b6cdb23` |

The archives under `reports/` and `research_notes/` contain copies of our earlier research, not additional organizer inputs.

## Competition requirements

The one-page brief defines the controller challenge:

> Build a web-based controller that converts recorded drone flight logs into servo command profiles, replays them over Wi-Fi on a 16-channel PWM test bench, and tracks cycles completed and per-channel running hours so engineers can quantify actuator life. A bench simulator, protocol spec and sample logs are provided; teams demo on real hardware.

Required product areas:

- Import a flight log, select 1–16 channels, resample it, preview it, and upload it.
- Start, pause, stop, clear counters, set a cycle target, and manually set outputs while stopped.
- Show connection/run state, completed cycles, current-cycle progress, and live channel pulse widths.
- Show per-channel bench hours and active hours and sync wall-clock time with the bench.
- Store sessions and events in a database and browse by date range. Exports appear in the HTML references; a test report is a stretch goal in the brief.

Stretch goals are ArduPilot/PX4 import, link-loss alerts, multiple benches, and an exportable test report.

Judging is 100 points:

- Functional completeness: 40
- Correctness and robustness, including reconnect, power-cycle counter survival, and time sync: 25
- GUI usability on the real bench: 20
- Code quality, README, and ease of running: 15

Any framework is allowed, but the GUI must run in a browser. Firmware is fixed for this competition.

## WDR Protocol v1

### Transport and framing

- The bench is a Wi-Fi station on the event's 2.4 GHz network.
- It exposes a plain TCP server on port `3333`; this is not a WebSocket endpoint.
- USB serial provides the same commands at `115200 8N1` for bring-up and debug.
- Send one uppercase command per line, terminated by `\n`; `\r` is ignored.
- Words are separated by one space and a line may be at most 128 characters.
- An empty line is ignored. An overlong line is discarded and answered with `ERR ARGS`.
- Every nonempty command gets exactly one `OK...` or `ERR...` reply. Send one command, wait up to one second for its reply, then send the next.
- `TEL` and `EVT` lines may arrive before the command reply. Route incoming lines by their first word.
- Lines that do not begin with `OK`, `ERR`, `TEL`, or `EVT` are debug output and must be ignored by the parser.

### Connection behavior

- One TCP controller is allowed. A new connection closes the old one.
- The bench keeps playing and counting if the client disappears. It accepts a new client automatically.
- Telemetry is disabled on boot and whenever a new TCP client connects. Send `TEL 1` after every connection/reconnection.
- The bench prints `EVT IP <address>` over USB when it gets or changes its IP.
- `INFO` includes uptime. A lower uptime after reconnect means the bench rebooted.
- After reset/power loss the bench returns `STOPPED`, restores saved counters, and never resumes motion automatically. It should rejoin Wi-Fi within 20 seconds.

### Capabilities and PWM behavior

- Query `INFO` rather than assuming a bench shape: `OK INFO proto=1 team=<name> ch=<N> maxframes=<M> up=<s>`.
- Protocol v1 documents `N` as 1–8, usually 4. The high-level challenge describes a 16-channel final bench. Athena must support up to 16 in its data model and adapt to the `ch` actually reported.
- Channels are zero-indexed on the wire: `0..N-1`.
- Servo pulses are 500–2500 microseconds at 50 Hz.
- Playback profiles run at 10–100 frames/s.
- A committed profile has `frames × N` pulse widths. Every frame must provide exactly `N` values.
- The bench supports at least 500 frames; `INFO.maxframes` is the real limit. The manual's simulator example reports 2,000.
- All outputs go to the fixed 1500-microsecond idle value after boot and `STOP`.

### States and commands

The actual state machine is:

```text
STOPPED --START [cycles]--> RUNNING --PAUSE--> PAUSED
   ^                            ^                |
   |                            +----RESUME------+
   +------------- STOP from any state ----------+
   +---- cycle target reached / EVT DONE --------+
```

Commands:

| Command | Allowed state | Successful reply / meaning |
|---|---|---|
| `PING` | any | `OK PONG` |
| `INFO` | any | Protocol, team, channel count, frame limit, uptime |
| `SET <ch> <us>` | STOPPED | Set one live output, 500–2500 microseconds |
| `LOAD <rate> <frames>` | STOPPED | Begin upload and discard the old profile |
| `F <i> <us0> ...` | after LOAD | Upload zero-based frame `i`, strictly in order |
| `COMMIT` | after all frames | `OK SUM=<s>`, sum of all pulse values modulo 65536 |
| `START [cycles]` | STOPPED | Start at frame 0; missing or 0 target means forever |
| `PAUSE` | RUNNING | Hold outputs and save counters |
| `RESUME` | PAUSED | Continue from the same frame |
| `STOP` | any | Save counters, set every channel to 1500, reset frame to 0 |
| `STATUS` | any | State, current-run cycles/target, frame count, live values |
| `COUNTERS` | any | Lifetime cycles, running seconds, per-channel active seconds |
| `CLEAR` | STOPPED | Set all lifetime counters to zero and save |
| `TEL <0|1>` | any | Disable/enable telemetry |
| `TIME <unix>` | any | Optional Unix-time synchronization |

Upload is `LOAD`, every frame from `F 0` through `F n-1`, then `COMMIT`, waiting for each reply. Any bad frame index, value count, or pulse range aborts the upload, so restart with `LOAD`. Athena must calculate and verify `SUM` before allowing `START`.

Errors are `ERR UNKNOWN`, `ERR ARGS`, `ERR RANGE`, `ERR STATE`, `ERR NOPROFILE`, and `ERR FULL`. Software should branch on the code word; trailing text is for people.

### Telemetry and events

- After `TEL 1`, telemetry arrives every `500 ms ± 100 ms`:
  `TEL state=RUNNING cycle=3 frame=120 us=1500,1620,...`
- `EVT BOOT` appears once on USB when firmware starts.
- `EVT IP <addr>` appears on USB when Wi-Fi gets an address.
- `EVT CYCLE <n>` means a cycle finished, where `n` is cycles completed in the current run.
- `EVT DONE` means the target was reached and the bench is now `STOPPED`.

### Counter semantics

- `cycles`: lifetime completed profile passes.
- `run_s`: lifetime whole seconds in `RUNNING`.
- `active_s` per channel: lifetime whole seconds in `RUNNING` while that channel is more than 25 microseconds from the fixed 1500-microsecond idle value.
- Counters are saved at least once per minute while running and on `STOP`, `PAUSE`, and `DONE`.
- A sudden power cut can therefore lose up to 60 seconds even though saved counters survive reboot.

The bench counters are authoritative for total cycles and hours. Athena's database records snapshots, deltas, sessions, and events for browsing. During a link outage the bench continues running; after reconnect Athena must use `INFO`, `STATUS`, and `COUNTERS` to reconcile instead of estimating.

### Command safety rules for Athena

WDR v1 has no request IDs or idempotency keys. Athena therefore must:

- maintain exactly one bench connection and allow only one outstanding command;
- never blindly retry an ambiguously timed-out mutating command;
- reconnect and inspect `INFO`, `STATUS`, and `COUNTERS` before deciding what happened;
- restart an aborted profile upload from `LOAD`;
- use `COMMIT SUM` as the upload integrity check;
- treat `STOP` as the safe recovery command;
- store the last observed uptime and detect reboots;
- resend `TEL 1` after every reconnect.

## Supplied `RCOU.csv`

The file has the header `TimeUS,C1,...,C14` and 9,074 data rows.

- SHA-256: `8b9d117be6e4c6f9c316d880e06ba4c5c5a7d736807206b49a6a0c10209dfc1f`
- First timestamp: `143523182 us`
- Last timestamp: `1074223191 us`
- Wall-clock span: `930.700009 s` (15 minutes 30.7 seconds)
- Timestamps are strictly increasing.
- Median sample interval is `99,995 us`, approximately 10 Hz.
- There is one large gap of `23,499,649 us` between CSV data rows 150 and 151 (file lines 151 and 152 after accounting for the header).
- `C1..C6` are populated throughout, with observed values between 1050 and 1746 microseconds.
- `C7`, `C8`, and `C11..C14` are zero for the whole file.
- `C9` and `C10` are zero for the initial 150 rows and then remain at 1050. Their transition coincides with the large timestamp gap.

Zero is outside WDR's allowed pulse range. Treat it as unavailable/inactive for compilation; its precise aircraft-side meaning is not documented in the supplied CSV. Never upload zero as a servo command. Leave those source channels unmapped; a selected invalid zero blocks compilation in v1.

At a 10 Hz profile rate the full timestamp span would need roughly 9,308 frames, which exceeds a 2,000-frame simulator example. Athena must fetch `maxframes` first and expose a trim window whose compiled frame count fits. The long gap must be shown to the user and rejected or trimmed out by default.

The input CSV is not the same as WDR's upload CSV example. Athena must convert:

```text
input:  TimeUS,C1,C2,...,C14
output: t_ms,ch0,ch1,...,chN-1
```

Selected outputs should be resampled deterministically with zero-order hold. Every output frame sent through `F` must contain exactly the connected bench's `N` legal pulse widths.

## Static UI references

The four HTML files are static desktop mockups with no scripts or working connection logic. Implement their compatible functionality in Flutter with a custom Athena layout; the user does not require matching their exact layout.

- Dashboard: connection/time/run chips, run state, target progress, cycle progress, total hours, per-channel live/idle/bench/active values, controls, traces, and recent events.
- Profile: source importer, trim/rate controls, channel mapping, preview, validation, and upload.
- History: date/channel filters, active-hours chart, sessions, events, CSV export, and PDF-report affordance.
- OLED/wiring: reference only; it describes the firmware team's Competition B hardware and on-device states.

Mockup values are illustrative and sometimes conflict with frozen protocol v1. Examples: 50–400 Hz in the mockup versus 10–100 frames/s in WDR v1, configurable per-channel idle values versus a fixed 1500-microsecond protocol idle, and 16 channels versus `INFO`-reported 1–8 in the manual. Use live capabilities and the frozen protocol, not mock values.

## Hardware reference

The wiring reference describes:

- ESP32-S3 DevKit (7semi N16R8), 16 MB flash, 8 MB PSRAM, 3.3 V logic.
- PCA9685 at I2C address `0x40`, driven over I2C0 at 400 kHz; GPIO 8 SDA, GPIO 9 SCL.
- PCA9685 `OE` on GPIO 4 with a 10-kilohm pull-up to 3.3 V so outputs stay disabled during boot.
- SSD1306 128×64 OLED at `0x3C` on a separate I2C controller; GPIO 17 SDA, GPIO 18 SCL.
- Separate 5–6 V servo supply with common ground, never powered from the ESP board.
- USB UART at 115200 for logs and the same command interface.

Hardware details are useful for explaining the system and diagnosing bench behavior, but Competition A must not modify the fixed firmware.

## Official tool findings and verification

The 1,796-line `wdr_tool.py` is now present and fully inspected. Its `test`, `upload`, `term`, `soak`, `serve-sim`, and `makecsv` commands are available. In-process and TCP simulator use require only Python; pyserial is loaded lazily for actual serial ports.

- Default simulator: four channels, 2,000 frames, team SIM.
- `serve-sim` exposes TCP 3333 and test-only virtual USB 3334, bound to loopback. `--listen` and `--usb-port` select alternate ports. Virtual USB accepts `!RESET`.
- `--port sim` creates its own device; it does not connect to a serve-sim process.
- Counters persist in `tempfile.gettempdir()/wdr_sim_counters.json`. Use isolated TMPDIR values and sequential tests to avoid shared-state interference.
- Reboot loses the profile. STOP retains the committed profile and any partial upload buffer; future cancelled/failed uploads must begin with a fresh LOAD.
- Counter reporting/save rounds whole seconds. TIME returns OK without implementing a clock.
- Built-in upload ignores t_ms and uses --rate; it also sends STOP automatically. Athena must compile source timestamps itself and implement its own controlled adapter.
- Actual seven-level scorer totals 85; the six-level header comment is stale. Check JSON results because exit zero alone does not imply success.
- Code inspection found that an extra F after all frames can index outside the buffer. Correct controllers send exactly the declared frame count and never blindly retry timed-out frames. Do not modify the vendor source to hide this.

Both official baseline runs passed **85/85**, with 36 checks each, on 25 September 2026. See [in-process JSON](planning_evidence/wdr-inprocess-2026-09-25.json) and [TCP JSON](planning_evidence/wdr-tcp-2026-09-25.json). The scorer saves before its reboot check, so this does not prove zero-loss abrupt power cuts. Athena itself is not implemented or tested yet.

No mandatory development artifact is missing. Raw ArduPilot `.bin` and PX4 `.ulg` examples remain absent and optional for later importer extensions; physical bench/actuator verification remains a venue task.
