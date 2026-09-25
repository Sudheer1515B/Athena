# Lifecycle metrics, traceability, UX, validation, and hackathon execution

Research current as of 2026-09-22. Recommendations below assume a simulator-first hackathon MVP. “Product decision” marks a proposed behavior rather than a requirement from a standard.

## What is actually available in the workspace?

### Takeaway

No bench simulator, protocol specification, sample flight log, application source, or project configuration was present when this research slice was performed. The implementation plan must therefore keep the log parser and bench transport behind adapters and must not assume a message format, timing unit, PWM range, device acknowledgement behavior, or safe-state command.

### Cited Findings

- A local `rg --files -g '!research_notes/**' -g '!.git/**' .` scan returned no files; only the coordinator-created research-notes directory was visible — [Local workspace](/Users/krisdreemur/Developer/SSN).
- A representative commercial servo controller uses configurable pulse widths, pulse periods, per-channel speed and acceleration settings, error/startup positions, and optional CRC, showing why these details must come from the supplied bench specification rather than be guessed. Its defaults are device-specific rather than universal — [Pololu Maestro user guide](https://www.pololu.com/docs/0j40/all).
- A servo position-control signal is pulse-width encoded; Pololu explicitly cautions that calling it ordinary duty-cycle PWM is misleading because pulse width, not duty-cycle percentage, carries the position — [Pololu servo-control interface explanation](https://www.pololu.com/blog/17/servo-control-interface-in-detail).

### Inferences

- **Product decision:** Define four interfaces before importing real files: `LogParser`, `ProfileCompiler`, `BenchTransport`, and `RunRepository`. Give the simulator the same `BenchTransport` contract as the real adapter.
- **Product decision:** Add a visible “Protocol assumptions” panel. Until the real specification is loaded, it must say `Simulator protocol v1`, simulated units, acknowledgement policy, heartbeat timeout, channel indexing, and safe state.
- **Product decision:** Fail closed on unknown fields, units, time bases, channel numbers, protocol versions, or output ranges. Never infer microseconds, degrees, normalized `[-1,1]`, or channel numbering from column names alone.

### Gaps

- The actual log schema, sample rate, timestamp semantics, actuator fields, bench URL/discovery method, command and acknowledgement frames, checksum/CRC rules, safe-state behavior, retry rules, and channel limits cannot be determined until the missing artifacts are supplied.
- The bench may stream individual frames, accept an uploaded profile for local execution, or expose a different control model. Local profile execution is safer for timing and network interruptions, but it cannot be claimed without the protocol specification.

## How should cycles and per-channel running hours be defined?

### Takeaway

Define one completed **profile loop** as the primary cycle, and define **command-active time** as the primary per-channel running-hour metric. Keep optional motion reversals, moving time, and commanded travel separate because an arbitrary flight trace has no universally correct fatigue-cycle count, and command exposure is not proof of physical movement or electrical power consumption.

### Cited Findings

- IEC’s common-data definition of “number of operating cycles” is the number of successions from one position to another and back to the first position — [IEC Common Data Dictionary](https://www.electropedia.org/cdd/iec61360/iec61360.nsf/bf7bfcc7a73006aec1257552003e602d/927fd9f8712daf12c1258407003de894?OpenDocument=).
- An ISO definition describes an operating cycle more generally as the complete set of stages carried out in a specified sequence — [ISO 15883-1:2024 terms](https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A15883%3A-1%3Aed-2%3Av1%3Aen).
- NIST distinguishes clock time from operating time and notes that laboratory life testing records operating time or number of cycles — [NIST life-cycle performance methodology](https://nvlpubs.nist.gov/nistpubs/Legacy/IR/nbsir76-1157.pdf).
- For random load histories, NIST states that a cycle has no single set definition; different cycle-counting methods can produce different counts. The purpose of methods such as rainflow is to reduce complex histories for comparison with fatigue curves — [NIST cycle-counting guide](https://nvlpubs.nist.gov/nistpubs/Legacy/IR/nbsir86-3055.pdf); [publication record](https://www.nist.gov/publications/cycle-counting-methods-fatigue-analysis-random-load-histories-fortran-users-guide).
- IEC defines operating time to failure as operating time accumulated from first use or restoration until failure — [IEC Electropedia, IEV 192-05-01](https://ieclib17.iec.ch/iev/iev.nsf/IEVref_xref/en%3A192-05-01).
- A servo controller’s reported “position” may only be the pulse width currently being transmitted, including controller-side speed/acceleration effects; it does not establish actual shaft position — [Pololu Maestro `Get Position`](https://www.pololu.com/docs/0j40/all).

### Inferences

#### Canonical metric names

- **Product decision — `completed_profile_loops`:** A run-level count. One loop completes only when the final profile frame/segment for that loop has been accepted and acknowledged for every channel in the run’s immutable `required_channel_mask`. Insert exactly one durable `LOOP_COMPLETED(loop_index)` record. The displayed total is `COUNT(LOOP_COMPLETED)`, not a mutable integer that can drift.
- **Product decision — `channel_completed_loops`:** Optional per-channel exposure. Increment only when that channel’s final command for the loop is acknowledged. This can differ from the global count during a partial-channel fault, so the UI must label the two explicitly.
- **Product decision — `command_active_seconds`:** The primary “running hours” numerator for each channel. Integrate acknowledged intervals during which the channel output is enabled and included in the run. Divide by 3600 for display. This measures commanded exposure.
- **Product decision — `moving_seconds`:** A derived metric. Integrate only intervals where the delivered command changes beyond a configured deadband. Label it “commanded moving time,” because there is no position feedback.
- **Product decision — `reversal_count`:** An optional derived metric. Count a sign change in command slope only after the command has moved at least `reversal_min_excursion` from the last accepted extremum, with hysteresis and an optional minimum dwell/sample count. Store the algorithm version and thresholds with the result. Do not call this a qualification cycle.
- **Product decision — `commanded_travel`:** Sum of absolute changes in delivered command units. This helps compare harsh and gentle profiles but is not mechanical travel unless the actuator calibration is known.
- **Product decision — `powered_seconds`, `actual_position`, `torque`, `current`, and `temperature`:** Show as unavailable unless the bench reports measured, timestamped telemetry. Pulse output alone cannot establish these quantities.

#### Boundaries and interruptions

- **Start boundary:** Time begins at the bench’s acknowledgement that the channel output became enabled, not when the operator clicked Start or when the command was queued.
- **Stop boundary:** Time ends at acknowledged disable/safe-state transition. If a pause policy keeps pulses enabled at a held position, command-active time continues while moving time stops. The selected policy must appear in run details.
- **Normal loop boundary:** The loop counter changes only after the final acknowledgement watermark. A command sent, a browser animation reaching 100%, or a timeout is insufficient.
- **Interrupted loop:** Preserve acknowledged exposure and partial-loop progress, but add zero completed loops for unfinished channels. Store `last_applied_command_seq`, `last_completed_loop`, and active-time intervals.
- **Reconnect:** Resume in place only if the bench reports the same `run_uuid`, profile hash, loop index, last applied sequence, channel mask, and output state. Otherwise mark the prior run `FAULTED_UNKNOWN_STATE`, require re-arming, and start a linked child run from a safe boundary. Do not invent elapsed time during an unknown interval.
- **Browser/server crash while an autonomous bench continues:** Correct reconciliation requires a bench-side persistent sequence/telemetry journal. If the protocol lacks that capability, the MVP must stop the simulator on heartbeat loss and classify any real-bench interval after loss as unknown.
- **Duplicate/reordered acknowledgements:** Accept an acknowledgement only once using a unique `(run_uuid, command_seq, channel)` key. Ignore earlier sequence numbers after recording a diagnostic event. Never add time or cycles from duplicate frames.
- **Profile with a static channel:** It accrues command-active time while enabled, zero moving time, zero reversals, and may accrue a channel profile loop only if it is deliberately in the required mask. The mapping UI should warn that it has no motion exposure.
- **Loop restart after fault:** A restarted partial loop does not retroactively complete. The new attempt either continues with a verified sequence or begins a new loop attempt; attempt number and completed loop index are separate fields.

#### Threshold and reset semantics

- **Product decision:** Version and snapshot all conversion inputs: scale, offset, inversion, neutral, min/max, slew limit, deadband, reversal excursion, interpolation method, missing-data policy, and sample period.
- **Product decision:** Reject a profile containing non-finite values, non-monotonic time, unresolved gaps, an unsupported sample rate, or out-of-range commands. Runtime hard limits remain a final guard; if they clamp a command, emit a fault and record both requested and delivered values.
- **Product decision:** Avoid silent filtering. If smoothing/resampling is enabled, create a new immutable profile revision with its own hash and a before/after preview.
- **Product decision:** Lifetime totals are never destructively reset. A “Set baseline” operation appends `BASELINE_SET` with operator, reason, UTC time, prior value, and new display offset. Show both “since baseline” and “all recorded” totals.
- **Product decision:** Replacing an actuator creates a new `asset_id`. Physical output channel and actuator identity are separate dimensions. Historical exposure remains attributed to the actuator that was mapped at run start.

### Gaps

- Without actual position, current, voltage, temperature, torque/load, and fixture/environment telemetry, the system can quantify **command exposure** but cannot prove that an actuator moved, was energized continuously, carried the intended load, or experienced the intended thermal stress.
- There is no supplied actuator manufacturer definition of a rated life cycle, permitted duty cycle, temperature derating, pulse range, load profile, or failure threshold. These must be attached to each actuator type before using the metrics for engineering decisions.
- Rainflow analysis would require an engineering choice of physical quantity and an appropriate fatigue/damage model. Running it on raw command pulse widths would look sophisticated without establishing material damage.

## What persistent data model is crash-safe, auditable, and easy to demo?

### Takeaway

Use a small local backend with one SQLite database as the record of truth. Store immutable inputs and mappings, an append-only run event ledger, idempotent command acknowledgements, and rebuildable summaries. The browser should render state and cache drafts, while the bench or backend owns execution timing and authoritative acknowledgements.

### Cited Findings

- SQLite transactions provide atomic commit: either all changes within a transaction occur or none do, including when interrupted by an operating-system crash or power failure subject to its documented filesystem assumptions — [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html).
- In WAL mode, commits append to a write-ahead log, readers and writers can proceed concurrently, and recovery is performed when a new connection opens after a crash. WAL must remain on one host and is not intended for a network filesystem — [SQLite WAL documentation](https://www.sqlite.org/wal.html).
- SQLite documents `synchronous=FULL` in WAL mode as ACID and performs an additional WAL sync after each transaction commit — [SQLite PRAGMA synchronous](https://sqlite.org/pragma.html#pragma_synchronous).
- SQLite UPSERT can turn an insert into an update or no-op when a uniqueness constraint is violated; uniqueness can come from a primary key, `UNIQUE`, or unique index — [SQLite UPSERT](https://www.sqlite.org/lang_UPSERT.html).
- IndexedDB transactions atomically write all changes or none, and its `strict` durability hint asks the user agent to verify that outstanding changes reached persistent storage before considering the transaction committed — [W3C IndexedDB 3.0](https://www.w3.org/TR/IndexedDB/).
- Browser storage is best-effort by default and may be evicted under storage pressure; an origin can request persistent storage, while writes can still fail with `QuotaExceededError` — [MDN storage quotas and eviction](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria).
- `performance.now()` is monotonic and not subject to wall-clock adjustments, but browsers differ on whether it advances during operating-system sleep — [MDN `performance.now()`](https://developer.mozilla.org/en-US/docs/Web/API/Performance/now).
- Background-tab timers are throttled, with browser-dependent behavior — [MDN `setTimeout()` throttling](https://developer.mozilla.org/en-US/docs/Web/API/Window/setTimeout); [MDN Page Visibility](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API).
- The standard `WebSocket` interface has broad support but no backpressure, so an application must bound or coalesce high-rate telemetry rather than assuming the browser can consume it indefinitely — [MDN WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API).

### Inferences

#### Recommended schema

| Table | Minimum fields | Purpose |
|---|---|---|
| `source_logs` | `id`, `sha256`, original filename, bytes, imported UTC, parser name/version, detected schema, parse warnings | Proves which input produced a profile; deduplicate by hash. |
| `profiles` | `id`, `source_log_id`, `profile_sha256`, compiler version, transform JSON, duration, frame count, time base, channel names, immutable payload/blob | Content-addressed replay artifact. |
| `actuator_assets` | `id`, serial/label, manufacturer/model when known, installed UTC, retired UTC, notes | Keeps actuator life separate from output-channel life. |
| `channel_map_snapshots` | `id`, profile hash, bench channel, source field, asset ID, units, min/max/neutral, inversion, slew/deadband/reversal thresholds | Immutable run configuration and limits. |
| `runs` | `run_uuid`, parent/campaign ID, profile ID/hash, map snapshot ID/hash, bench ID/protocol version, requested loops, required mask, state, pause policy, created/armed/started/ended UTC | One state-machine instance. |
| `run_events` | `event_uuid`, `run_uuid`, monotonically increasing event sequence, host UTC, host monotonic delta, bench tick/sequence when available, type, channel, payload JSON, previous-event hash | Append-only audit trail; hash chain is tamper-evident, not tamper-proof. |
| `command_acks` | `run_uuid`, `command_seq`, loop index, frame index, channel/mask, requested value, delivered value, bench tick, receive time | Authoritative delivered-command watermark. Unique command keys make retries idempotent. |
| `active_intervals` | `run_uuid`, channel, start-ack ID/time, end-ack ID/time, close reason, duration | Explicit, inspectable running-time contributions. |
| `loop_completions` | `run_uuid`, loop index, required mask, completion event/ack watermark, completed UTC | Primary source for cycle totals; unique `(run_uuid, loop_index)`. |
| `faults` | `id`, run/event, source, code, severity, first/last seen, state snapshot, acknowledged by/time, resolution | Searchable fault evidence. |
| `counter_adjustments` | `id`, asset/channel scope, metric, prior lifetime value, baseline/display offset, operator, reason, UTC | Append-only reset/baseline ledger. |
| `channel_summaries` | run/asset/channel keys, completed loops, active/moving seconds, travel, reversals, last rebuilt event | Disposable projection that can be rebuilt from immutable rows. |

#### Transaction and idempotency rules

- **Product decision:** In one SQLite transaction, insert an acknowledgement, close/open any active interval, insert a loop completion if its final watermark was reached, update the run checkpoint, and refresh the materialized summary. A crash yields the whole transition or none.
- **Product decision:** Give every browser request a `request_id`, every run a UUID created before transmission, and every bench command a strictly increasing `command_seq`. Put unique constraints on each natural idempotency boundary. Retrying then returns the prior result rather than repeating motion or double-counting.
- **Product decision:** Derive loop count with `COUNT(*)` over unique loop-completion rows and running time with `SUM(duration)` over closed intervals plus at most one displayed live interval. Do not trust a separately incremented counter.
- **Product decision:** Use SQLite on a local disk with `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON`, a busy timeout, regular checkpoints/backups, and `integrity_check` in a maintenance/test path. Keep the database, `-wal`, and `-shm` files together.
- **Product decision:** Record both UTC wall time for human traceability and monotonic/bench ticks for duration. Reset the monotonic origin on each process/controller session and never subtract monotonic timestamps from different origins.
- **Product decision:** High-frequency telemetry is bounded. Keep the latest value for live display, aggregate charts at a chosen resolution, and persist chunked raw telemetry only if the protocol supplies it and storage is budgeted. Command acknowledgements and state transitions are never dropped.
- **Product decision:** On boot, recover runs left in `ARMED`, `RUNNING`, `PAUSING`, or `STOPPING` to `RECOVERY_REQUIRED`; query bench state before allowing continuation. If the bench state cannot be proven, close no active interval speculatively and show an unknown-exposure gap.
- **Product decision:** Export a portable evidence bundle containing run JSON, source/profile hashes, mapping and threshold snapshot, ordered events, command/ack watermark summary, interval and loop tables, faults, application/protocol versions, and a CSV summary.

#### Browser-only fallback

- **Product decision:** If the weekend stack cannot include a backend, use IndexedDB transactions with `durability: 'strict'` when supported, request persistent storage, show storage status/quota, and export after every important run. This is a fallback because site data can be cleared/evicted and browser shutdown can abort in-flight transactions.
- **Product decision:** Never use `localStorage` for the ledger or use DOM timers as the command clock. A Web Worker can keep UI computation responsive, but it does not remove browser lifecycle or device-safety constraints.

### Gaps

- True exactly-once physical actuation cannot be guaranteed by a web client alone. It requires bench firmware that recognizes run/command sequence identifiers, returns applied-state acknowledgements, and exposes state after reconnect.
- Hash chaining detects accidental or later modifications only when the chain root is protected. It is not a signature and does not establish operator identity or regulatory-grade non-repudiation.
- A database on the controller computer cannot preserve events produced while that computer is down unless the bench buffers and later reports them.

## What UI makes mapping, preview, readiness, live progress, faults, and history obvious?

### Takeaway

Use a four-step workflow—Import, Map & Preview, Verify & Arm, Run & Review—with the same channel identity everywhere. Put the 16-channel map and small-multiple waveforms at the center, make readiness failures actionable, and reserve a persistent top status bar for connection, run state, last acknowledgement age, and Stop.

### Cited Findings

- WCAG says color must not be the only visual means of conveying information or status; text, shape, or another cue should accompany it — [W3C Understanding SC 1.4.1](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color).
- W3C recommends explicit labels for form controls so their purpose is visible and programmatically associated — [W3C labeling controls](https://www.w3.org/WAI/tutorials/forms/labels/).
- Dynamic progress, completion, and error messages should be programmatically exposed as status messages without requiring a focus change — [W3C Understanding SC 4.1.3](https://www.w3.org/WAI/WCAG21/Understanding/status-messages); [`role=status` technique](https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA22.html).

### Inferences

#### 1. Import and inspect

- Drop zone/file picker plus visible provenance: filename, SHA-256 prefix, parser and version, row count, start/end timestamp, duration, source fields, units, duplicates, missing samples, time reversals, and warnings.
- Show a short raw-data preview and the detected mapping. Require explicit unit/time-base confirmation when the parser cannot prove them.
- Keep errors specific: “Row 814 timestamp is 42 ms earlier than row 813” is actionable; “Invalid log” is not.

#### 2. Map and preview

- Use one 16-row mapping table: physical channel label/index, enabled/required state, source log field, actuator asset, conversion, invert, neutral, min/max, slew limit, preview range, and validation status.
- Use drag/select mapping with duplicate-source and duplicate-output warnings. Include “disable channel” as a deliberate selection.
- Use synchronized small-multiple waveforms, one per active channel, with the same horizontal time scale. Each plot shows requested source, compiled command, min/max band, clipped/rejected points, and start/end values. Small multiples remain readable when 16 colored lines would overlap.
- Add a shared playhead and scrub control. Hover/focus reports time, source value, delivered command, channel, and asset. A summary strip shows duration, update rate, active channels, maximum simultaneous motion, limit violations, and gaps.
- Preview loop closure: show the difference between last and first command per channel and warn about a discontinuity when replay wraps.

#### 3. Verify and arm

- Present a checklist with `PASS`, `WARN`, `FAIL`, or `NOT REPORTED`, always with text/icon as well as color. Include simulator/bench connection, protocol version, 16-channel capability, safe-state/watchdog support, source/profile hash, mapping uniqueness, limits, rate/buffer fit, storage writable, no other active run, and optional physical attestations.
- Treat hardware-only facts such as enclosure closed, E-stop released, power/current capacity, and actuator attachment as manual attestations unless the bench reports sensors. Never show a green automated check for unobserved hardware.
- Keep `Start` disabled on any failure. Warnings require a recorded acknowledgement and reason. Arming freezes the profile/mapping hashes; edits disarm the run.
- Use a two-stage action: `Arm test` followed by a distinct `Start N loops`. Show exact consequences: active channel count, duration per loop, requested loops, projected command-active hours, pause policy, and simulator/real-bench badge.

#### 4. Run and review

- Persistent status bar: `SIMULATOR` or `REAL BENCH`, connection state, state-machine state, run ID, last acknowledgement age, and a large Stop button. A web Stop is an operational command, not a physical emergency stop; label it accurately.
- Hero metrics: completed loops/requested, current loop and percentage, elapsed wall time, delivered profile time, estimated remaining time, active faults, and persistence/checkpoint state.
- Compact channel grid: channel/asset, current requested and acknowledged value, enabled/moving/held/fault label, command-active hours, commanded moving hours, channel completed loops, last ack age, and a tiny trace. Sort/focus faults first while preserving physical channel number.
- Fault state is a full-width banner with code, first seen time, affected channels, output state (`disabled`, `held`, or `unknown`), counter consequences, and one safe next action. Never replace fault history after recovery.
- Pause and Stop must show their bench-acknowledged outcome. While waiting, show `PAUSING`/`STOPPING`, not `PAUSED`/`STOPPED`.
- History is a filterable table by run/campaign, actuator, profile, date, result, and fault. Each run opens a timeline of state/events plus mapping snapshot, hashes, loops, active hours, partial-loop exposure, faults, and export button.
- Analytics for the MVP: cumulative command-active hours and completed loops by actuator; active-time balance across channels; faults per 1,000 completed loops (descriptive only); max/min/mean command; command travel and reversals; and planned-versus-delivered completion. Label all units and metric definitions in a glossary drawer.

### Gaps

- Physical readiness inputs available from the real bench are unknown. The UI must distinguish “not reported” from “failed” and from “operator attested.”
- The protocol may not acknowledge individual channels or frames. If it only acknowledges batches, display and persist the resolution actually proven; do not fabricate channel-level delivery evidence.
- Accessibility conformance requires testing the finished interface; following these patterns alone is not a conformance claim.

## What acceptance tests and demo prove correctness and responsible safety behavior?

### Takeaway

The most convincing proof is a deterministic end-to-end run whose expected cycles and channel seconds can be calculated by hand, followed by injected duplicate messages, disconnects, process death, refresh/restart, and an out-of-range profile. The demo should show that totals remain correct and that uncertain bench state becomes a visible fault rather than optimistic progress.

### Cited Findings

- ISO 12100 supplies a methodology for identifying machine hazards, estimating/evaluating risks, reducing them, and documenting/validating the process. Referencing it is useful guidance but does not itself establish conformity — [ISO 12100:2010](https://www.iso.org/standard/51528.html).
- OSHA notes that servicing workers can be injured by unexpected energization/startup or release of stored energy and describes isolation and energy-control practices — [OSHA lockout/tagout tutorial](https://www.osha.gov/etools/lockout-tagout/tutorial).
- OSHA’s testing guidance describes clearing tools/materials and people before temporary re-energization, then de-energizing and reapplying energy controls after testing — [OSHA testing of machines](https://www.osha.gov/etools/lockout-tagout/tutorial/testing-machines).
- NASA’s lesson from an actuator failure recommends life-cycle testing of mission-critical rotating equipment under realistic conditions for credible lifetime forecasts — [NASA Lessons Learned 394](https://llis.nasa.gov/lesson/394).
- SQLite itself uses simulated crashes and I/O failures, then reopens databases and checks whether transactions occurred completely or not at all — [SQLite testing](https://sqlite.org/testing.html).

### Inferences

#### Deterministic fixture

- **Product decision:** Create a 4-second, 4-channel profile with simple piecewise values and two loops. Keep channels 5–16 disabled. Write the expected sequence, loop boundaries, active seconds, moving seconds, travel, and reversals in a golden fixture beside the test.
- **Product decision:** The simulator must expose deterministic time or a speed multiplier and named fault injections: drop next ACK, duplicate ACK, delay ACK, reorder ACK, disconnect, protocol mismatch, channel fault, watchdog stop, and bench reboot.

#### Acceptance matrix

| Area | Test | Required result |
|---|---|---|
| Parsing | Known sample/golden fixture | Field names, units, duration, rows, and hash match. |
| Parsing | Duplicate, missing, non-monotonic, non-finite timestamps | Deterministic documented handling; unsafe ambiguity blocks compile. |
| Compilation | Scale/invert/resample/profile wrap | Expected commands and new profile hash; input remains immutable. |
| Limits | One out-of-range point and one slew-rate violation | Readiness fails with exact channel/time/value; no command sent. |
| Mapping | Duplicate output, missing required channel, static mapped channel | Correct fail/warn behavior; map hash changes on any edit. |
| Loop count | Stop one ACK before final watermark | Zero additional completed loop. |
| Loop count | Duplicate/reordered final ACK | Exactly one completion row and one count. |
| Channel count | One channel misses final ACK | Its channel loop does not increment; global loop does not increment; successful channels retain their proven exposure. |
| Time | Start delay, pause with outputs disabled, resume | Only acknowledged active intervals contribute. |
| Time | Pause while held/enabled | Active time continues, moving time stops, and policy is visible. |
| Disconnect | Loss during a loop | State becomes fault/unknown as designed; no extrapolated time or cycle. |
| Reconnect | Matching state vs mismatching run/profile/sequence | Verified match can resume; mismatch requires re-arm/new linked run. |
| Idempotency | Retry Start and command requests with same IDs | No duplicate run, motion, interval, or loop. |
| Persistence | Kill backend between ACK receipt and transaction completion at several points | On restart the transition is wholly present or absent; derived summaries rebuild identically. |
| Persistence | Browser refresh and second tab | Same authoritative run; second controller cannot arm concurrently. |
| Recovery | Database reopen/integrity check | No corrupt/half-applied run state; unresolved run enters recovery-required. |
| Faults | Simulated channel, watchdog, protocol, and storage faults | Safe/fault state and counter consequences are explicit; fault remains in history. |
| Export | Export and re-import evidence bundle | Hashes and totals reproduce; no hidden mutable dependency. |
| UI | Keyboard-only, 200% zoom, color-blind review | All controls/statuses remain operable and understandable without color alone. |

#### Safety evidence to show without overstating it

- Profile validation rejects unknown units, invalid time, limit violations, and incompatible protocol/rate before arming.
- Server-side validation repeats critical checks; browser validation is not the only guard.
- Arming freezes hashes and mappings, and any edit disarms.
- The simulator demonstrates watchdog timeout to disabled outputs. For hardware, only claim this if the protocol and bench test prove it.
- Runtime hard limits log requested and delivered values and fault the run; they are not silent profile editing.
- A connection loss moves the UI to `FAULTED`/`OUTPUT UNKNOWN` until the bench proves state.
- The app never labels the software Stop button “E-stop.” A physical, independent emergency stop, guarding, power/current protection, and documented energy isolation belong in the real rig risk assessment.
- Real-bench commissioning should begin unloaded/decoupled, then one channel at conservative limits, then a guarded low-energy fixture, and only then multiple channels under the actuator manufacturer’s limits. This is a proposed commissioning sequence, not a substitute for the lab’s procedure.

#### Ninety-second judging demo

1. Import the deterministic sample log; point to file hash, duration, and parser warnings.
2. Map four log fields to four named actuator assets. Deliberately set one limit too low so Preview shows the exact violation and blocks Start; correct it and show a new map/profile hash.
3. Pass readiness in `SIMULATOR`, arm three loops, and start. Show acknowledgement-backed loop count and per-channel hours increasing.
4. During loop two, inject Wi-Fi loss. Show that the run faults, only loop one counts, partial active seconds remain, output state is safe or explicitly unknown, and the fault timeline persists.
5. Reconnect. If exact state cannot be proven, create a linked recovery run for the remaining two loops. Inject a duplicate final ACK and show no double-count.
6. Refresh or restart the backend, open History, and show three campaign loops, two run attempts, the partial exposure, stable per-actuator totals, hashes, and an exportable evidence bundle.

### Gaps

- Software/simulator tests do not demonstrate electrical limits, current capacity, fixture strength, guarding effectiveness, thermal behavior, RF resilience, or a real actuator’s safe operating envelope.
- Formal safety, reliability, environmental, or flight qualification requires requirements, calibrated instrumentation, controlled conditions, test-article identity, sample-size/statistical rationale, and the applicable organization/industry standards. A hackathon demo cannot establish those outcomes.

## Which reliability standards and vendor guidance matter, and what may be claimed?

### Takeaway

Standards support disciplined terminology, test planning, risk assessment, and evidence capture. They do not turn command-cycle totals into a qualified actuator lifetime. The responsible claim is that the controller produces traceable command-exposure records and a foundation for a test plan; actual durability conclusions require realistic loads, environment, measurements, failure criteria, and enough test articles.

### Cited Findings

- IEC 61124:2023 addresses compliance tests for constant failure rate/intensity, MTTF, and MTBF under an assumption of independent exponentially distributed failure/operating times except where stated — [IEC 61124:2023](https://webstore.iec.ch/en/publication/65838).
- NIST says reliability-test planning begins with what the test should discover or prove, then chooses duration, number of units, stresses, models, and acceptable decision risk — [NIST reliability test planning](https://www.itl.nist.gov/div898/handbook/apr/section3/apr31.htm).
- A NIST actuator study monitored degradation across one million cumulative cycles, illustrating that meaningful actuator-fatigue testing records both exposure and a performance/degradation response — [NIST PZT actuator study](https://www.nist.gov/publications/characterizing-reliability-multilayer-pzt-actuators).
- NASA reports that realistic permutations of position and load profiles, fault severity, and run-to-failure experiments were used to validate electro-mechanical actuator prognostics, while also noting that a more robust validation would require many more experiments under the same conditions — [NASA actuator prognostics dataset](https://data.nasa.gov/dataset/experimental-validation-of-a-prognostic-health-management-system-for-electro-mechanical-ac).
- ISO 12100 provides machine risk-assessment and risk-reduction principles but is not a product-specific actuator life-test procedure — [ISO 12100:2010](https://www.iso.org/standard/51528.html).
- A representative controller vendor tells users to size the servo supply within each servo’s operating voltage and for all current drawn, and to consult each servo’s datasheet — [Pololu Maestro power guidance](https://www.pololu.com/docs/0j40/all).

### Inferences

- **Permitted hackathon claim:** “The app converts a versioned log into a bounded, reviewable command profile; replays it against a simulator using acknowledged, idempotent commands; and preserves completed profile loops, per-channel command-active hours, faults, mappings, and provenance.”
- **Permitted forward-looking claim:** “With the real protocol and measured telemetry, this architecture can support controlled actuator endurance campaigns.”
- **Avoid:** “certifies actuator life,” “predicts remaining useful life,” “measures actual servo movement,” “proves MTBF,” “meets ISO/IEC qualification,” “flight qualified,” or “safe for unattended hardware operation.” None follows from command logs and a simulator.
- **Product decision:** Treat failures/suspensions as censored/test-state data rather than deleting them. Record failure definition, symptom, channel/asset, exposure at event, environment/load notes, disposition, and whether the test article was repaired or replaced.
- **Product decision:** Before real life testing, write a test plan containing objective, population/test articles, realistic use profile, load/environment, measurement calibration, failure/degradation thresholds, stop rules, inspection intervals, sample size/statistical method, and reporting rules. The controller can store references to that plan but cannot supply missing engineering rationale.
- **Product decision:** Do not calculate MTBF from a few demo runs. IEC 61124’s constant-rate model is a specific assumption and may be inappropriate for wear-out/fatigue behavior.

### Gaps

- No actuator model/datasheet, expected field environment, load/torque, mounting, temperature, supply, rated life, failure criteria, sample size, or target confidence was supplied.
- No product-specific safety or qualification standard was identified from the available task description. Applicability depends on the actual actuator, fixture, workplace, industry, and jurisdiction.

## What does Welkinrim Technologies appear to value, and how should the demo be tailored?

### Takeaway

Welkinrim publicly presents itself as an electric-propulsion and power-systems company serving UAV/eVTOL, marine, land, and robotics markets, with emphasis on validation, real mission loads, integrated systems, manufacturing/testing, and end-to-end traceability. Tailor the demo as engineering validation infrastructure that converts field evidence into reproducible, attributable bench evidence—not as a generic dashboard or an unsupported life-prediction product.

### Cited Findings

- Welkinrim’s official site describes precision electric propulsion for UAV, marine, land, and robotics; lists motors, ESCs, intelligent power systems, and an autopilot among its product lines; and presents its UAV/eVTOL range as “simulation-validated” — [Welkinrim official site](https://www.welkinrim.com/).
- The official site highlights “100% traceability end-to-end” in a process that includes order/specification lock, manufacturing, assembly, testing/QC, documentation, and shipment — [Welkinrim official site, process section](https://www.welkinrim.com/).
- Welkinrim’s LinkedIn company page describes its work as electrical-machine design, motor-drive electronics, firmware, UAV/drone motors, ESCs, and autopilot in aviation/aerospace component manufacturing — [Welkinrim Technologies on LinkedIn](https://in.linkedin.com/company/welkinrimtechnologies).
- In first-party LinkedIn posts, the company emphasizes sustained-load thermal constraints, integrated motors/ESCs/power distribution and conversion, predictable field performance, in-house design/prototyping/assembly/validation, and testing under real-world or extreme conditions — [Welkinrim Technologies on LinkedIn](https://in.linkedin.com/company/welkinrimtechnologies).
- Welkinrim’s site displays claims including MIL-STD-810G, JSS 55555, and 5,000 m qualification. These are company claims visible on the product site; this research did not inspect the supporting test reports or certification scope — [Welkinrim official site](https://www.welkinrim.com/).

### Inferences

- **Pitch framing:** “This is a traceability layer between flight behavior and bench validation.” Begin with a recorded mission/log, show the exact compiled stimulus and asset/channel mapping, then end with acknowledged exposure, faults, hashes, and a reproducible run bundle.
- **Use their observable priorities:** Put asset serial/label, profile provenance, configuration/version, limits, delivered sequence, fault history, and test result on one run record. That aligns the demo with the company’s public traceability and validation language.
- **Lead with realistic-profile replay:** Explain that a square-wave exercise can miss mission-specific dwell, reversal, and simultaneous-channel patterns. The product preserves the recorded temporal profile while making conversions and limits reviewable. Avoid claiming that command replay alone recreates aerodynamic load or thermal environment.
- **Make sustained exposure visible:** Alongside cycles and command-active hours, reserve explicit `NOT REPORTED` fields for current, voltage, temperature, torque/load, and measured position. Their public emphasis on thermal and continuous-load behavior makes honest telemetry boundaries more persuasive than a fabricated health score.
- **Show system behavior during failure:** Inject Wi-Fi loss and a duplicate acknowledgement. Demonstrate safe/unknown-state handling, no double counting, restart persistence, and an audit trail. This supports “predictable performance” more directly than a polished happy-path animation.
- **Connect to production without overreaching:** Position the same run bundle as useful for engineering endurance tests, incoming/outgoing QC evidence, prototype comparisons, and customer/OEM traceability. State that production deployment would require the actual bench protocol, actuator/ESC limits, calibrated sensors, access controls, and test-plan approvals.
- **Keep the challenge’s actuator scope:** Welkinrim’s public product emphasis is propulsion and power electronics, while this challenge specifies a 16-channel PWM actuator bench. Do not silently rebrand servo command hours as motor or ESC endurance. Say that the adapter/event-ledger pattern could extend to propulsion benches only with appropriate protocols and measured power/thermal/load data.
- **Anticipate judge questions:** Be ready to show (1) the exact cycle/hour formulas, (2) how real hardware replaces the simulator adapter, (3) how duplicates and reconnects remain idempotent, (4) why limits are snapshotted, (5) how an actuator replacement preserves history, and (6) which conclusions are impossible without sensors.
- **Suggested close:** “Welkinrim builds hardware to survive the mission. This controller preserves the mission as a repeatable test stimulus and makes every delivered command, completed loop, exposure hour, and fault traceable to the actuator and test configuration.”

### Gaps

- The company sources do not establish that this specific hackathon problem maps to an existing Welkinrim product roadmap, manufacturing process, or customer program.
- Public marketing references to standards and qualification are not enough to determine exact test methods, laboratories, configurations, pass criteria, or certification applicability. The hackathon solution should not imply it inherits those qualifications.
- No first-party material found in this quick search defines Welkinrim’s preferred web stack, bench protocol, data-retention policy, access-control requirements, or scoring rubric for this hackathon.

## What should be built Friday and Saturday, what can be cut, and how should it be pitched?

### Takeaway

Build one thin, persistent, simulator-backed path first: import one known log, compile and preview it, map a few of 16 channels, run two loops, survive a fault/restart, and show correct history. Add breadth only after that slice works. The judging story is trustworthy evidence under failure, not the number of widgets.

### Cited Findings

- Browser background timing is throttled, so an architecture that depends on a visible tab for command cadence creates avoidable demo risk — [MDN Page Visibility](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API).
- Browser storage is best-effort unless persistence is granted, supporting a local backend database as the easier hackathon record of truth — [MDN storage quotas and eviction](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria).
- NIST’s reliability guidance starts from the decision or proof sought rather than accumulating undirected test time — [NIST reliability test planning](https://www.itl.nist.gov/div898/handbook/apr/section3/apr31.htm).

### Inferences

#### Friday: get the vertical slice to survive a restart

| Timebox | Build in this order | “Done” evidence |
|---|---|---|
| 0:00–0:45 | Inventory supplied artifacts; write protocol/log assumptions and golden fixture | Fixture parses; missing facts are visible, not hidden constants. |
| 0:45–1:45 | SQLite schema, migrations, event append, run state enum | Create run, append event, restart, read same timeline. |
| 1:45–2:45 | Parser and profile compiler for exactly one sample format | Immutable source/profile hashes and deterministic compiled frames. |
| 2:45–4:15 | Simulator transport, handshake, run UUID/sequence ACKs, start/stop/watchdog | CLI/API can execute two loops and inject a disconnect. |
| 4:15–5:30 | Server run state machine plus transactional loop/interval accounting | Hand-calculated totals match; duplicate ACK has no effect. |
| 5:30–7:00 | Minimal web flow: Import → Map → Preview → Arm/Run → History | Full happy path works without database editing. |
| 7:00–8:00 | Kill/restart/refresh test and a tagged checkpoint/demo recording | Same totals after restart; known-good fallback is preserved. |

#### Saturday: fault proof, usability, and the pitch

| Timebox | Build in this order | “Done” evidence |
|---|---|---|
| 0:00–1:30 | Readiness gate, limits, mapping snapshot, clear state/fault banner | Unsafe profile cannot start; edit disarms. |
| 1:30–3:00 | Disconnect, duplicate/drop/reorder ACK, recovery-required flow | Fault demo yields exact expected cycles/hours. |
| 3:00–4:00 | 16-channel small multiples/table and live progress | All channel identities are consistent and scan-friendly. |
| 4:00–5:00 | History, campaign totals, JSON/CSV evidence export | Demo run is explainable after refresh. |
| 5:00–6:00 | Deterministic acceptance script; keyboard/zoom/color pass | One command/checklist reproduces judge demo. |
| 6:00–7:00 | Rehearse 90-second story; capture local backup video/screens | Pitch fits; Wi-Fi failure has an intentional path. |
| 7:00 onward | Buffer only; fix correctness or demo blockers | No architectural expansion. |

#### Scope cut line

- **P0, must ship:** one known log format; immutable compiled profile; mapping for 16 outputs; simulator; handshake plus sequence ACKs; bounded commands; start/stop/fault state machine; global completed loops; per-channel command-active hours; SQLite history; disconnect injection; export; visible simulator badge.
- **P1, only after P0:** moving time, command travel/reversals, campaign grouping, rich waveform hover, baseline events, multi-tab lock, CSV summary, compare view.
- **P2, defer:** real hardware if its artifacts arrive late, arbitrary log auto-detection, user accounts/cloud sync, multi-bench orchestration, firmware update, actual RUL/MTBF models, rainflow fatigue, current/temperature analytics, report designer, mobile polish.
- **Fallback A:** If the protocol files remain absent, present a complete simulator product and a clearly documented adapter contract. Do not improvise real-bench frames.
- **Fallback B:** If waveform work slips, use a validated channel table plus a single selected-channel plot; retain provenance, limits, state machine, counters, and history.
- **Fallback C:** If live streaming is unstable, run the deterministic simulator locally and keep a 30-second backup capture. Judges can still inject a fault and inspect persisted evidence.

#### Judging pitch

- **Problem:** Flight logs are useful stimulus, but a life test is only credible when engineers know exactly what was commanded, to which actuator, for how long, how many complete replays finished, and what happened during faults.
- **Demo promise:** “We turn one recorded flight into an immutable 16-channel test profile, prove its limits before motion, execute it with acknowledged sequence numbers, and keep exposure correct through duplicates, disconnects, and restarts.”
- **Differentiator:** Lead with the Wi-Fi failure. Many demos show a chart moving; this one shows that uncertainty does not become fake lifecycle data.
- **Evidence:** Profile and mapping hashes, acknowledgement watermark, loop completion rows, active intervals, fault timeline, restart persistence, and an exportable run bundle.
- **Responsible close:** “Today this quantifies command exposure in a bench simulator. With the supplied hardware protocol and measured feedback, the same ledger can support controlled actuator endurance campaigns.”

#### Risk register

| Risk | Likelihood / impact | Mitigation | Demo fallback |
|---|---|---|---|
| Simulator/spec/logs remain missing | High / High | Adapters, golden fixture, assumptions panel; request artifacts early | Simulator protocol v1 only; no hardware claim. |
| “Cycle” remains ambiguous | High / High | Metric glossary, immutable algorithm version, separate loop/reversal metrics | Show loop completion rows and formula. |
| Browser timer/background throttling | Medium / High | Bench/backend scheduler; browser renders ACK state | Local deterministic simulator. |
| Wi-Fi loss causes double commands/counts | Medium / High | Run UUID, sequence IDs, unique constraints, state query before resume | Fault and restart from safe loop boundary. |
| Hardware state cannot be proven after loss | Medium / High | Watchdog and bench journal if supported; otherwise unknown-state fault | Simulator stops on heartbeat loss. |
| Out-of-range profile damages hardware | Medium / High | Compile-time reject, frozen limits, runtime hard guard/fault, staged commissioning | Simulator only. |
| Supply/current/thermal limits unknown | High / High | Require datasheet/test-plan values and instrumentation | Do not energize real actuators. |
| Counter drift after crash | Medium / High | Append-only completion/interval rows, atomic transaction, rebuild summaries | Restart proof in demo. |
| Telemetry overwhelms socket/UI/storage | Medium / Medium | Bounded queues, coalesced live values, downsampled chunks, never drop ACKs | Lower simulator rate. |
| Multiple tabs/operators contend | Medium / Medium | Server-side single active-run lease; optional Web Lock/BroadcastChannel UI warning | Close extra tabs; server remains authority. |
| 16 traces become unreadable | High / Medium | Small multiples, shared playhead, focus/fault filtering | Selected-channel plot plus table. |
| Team spends time on advanced analytics | High / Medium | Enforce P0/P1/P2 cut line; analytics derive after correctness | Show cycles, hours, faults only. |
| Formal qualification is implied | Medium / High | Simulator badge and explicit limitations in UI/pitch/export | Use “command exposure,” never “certified life.” |

### Gaps

- The exact hours available, team size, preferred web stack, and hardware-access window are unknown; the timeboxes are an order of operations, not a staffing estimate.
- Integration time cannot be estimated until the protocol specification and simulator are present and executable.
