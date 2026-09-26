# Athena resilience and demo improvements

Scope: implement the improvements agreed on 26 September 2026, one phase at a time. Preserve the fixed WDR firmware and existing bench counters. Physical tests need a confirmed signal-only setup; actuator-load and 16-channel tests require hardware not currently supplied to Athena. Simulator testing uses isolated data and ports, never the physical bench's SQLite records or Wi-Fi address.

## R1 — Backend-owned monitoring (first)

Problem: GET /snapshot currently triggers STATUS/COUNTERS and reconnects. Closing the browser stops recording. Uploads hold the transport lock and can block snapshot requests.

Implementation:
- Add a lifespan-managed monitor thread with a one-second observation interval, one serialized bench I/O lock, bounded command/connect timeouts and an interruptible shutdown event.
- Keep API snapshot reads independent of bench I/O: return a cached authoritative observation, its real receive time, age and connection state. Never turn the API response time into a new bench-observation timestamp.
- Serialize explicit connect/disconnect/control/upload with the monitor. Skip polling while a mutation owns the I/O lock, rather than queueing overlapping command batches.
- Record observations and terminal session state without browser requests. Use a separate SQLite connection for the synchronized HistoryRecorder so background writes cannot join profile-import transactions on the API connection.
- Backend startup remains disconnected. Explicit disconnect cancels automatic retry. Shutdown closes the transport without implicitly stopping bench playback.

Acceptance: a supplied-simulator finite run completes and is persisted while no snapshot requests are made; repeated reads do not create duplicate bench observations; shutdown leaves no worker; existing protocol/API tests pass.

## R2 — Clear stale/disconnected UI

- Expose last successful observation, age, retry attempt/next retry, last connection error, and last-known state separately from live state.
- Show “Connection lost — bench may still be running”; stale values are labeled and cannot enable Start/Pause/Resume/manual SET. Stop may be attempted only over a connected transport and failure must not imply outputs stopped.
- Detect loss of the browser-to-backend link separately from backend-to-bench loss. Retain the last-known display only with a visible stale label.
- Use capped retry backoff (approximately 1, 2, 4, 8, then 10 seconds, with small jitter), reset after success, and let explicit disconnect cancel it.

Acceptance: widget tests cover stale state, backend outage, reconnect status and disabled mutation controls; snapshot response stays fast during upload/reconnect.

## R3 — Recovery identity and reboot checks

- Pin protocol/team/channel count/frame capacity after an explicit connection. Validate them before accepting a recovered connection; changed capabilities require an explicit new connection/review.
- Compare reported uptime with previous uptime to detect an observed reboot. Record that observation and mark affected session timing/outcome uncertain.
- Re-read INFO/STATUS/COUNTERS, acknowledge TIME, and reconcile state; never send LOAD, START, RESUME or CLEAR automatically.
- Profile identity is unknown after reconnect/restart/takeover. Matching frame count is not a checksum or identity proof. A deliberate verified upload is required before a new Start.

Acceptance: changed identity/capabilities are rejected, reboot is represented honestly, continuing runs are observed without another Start. WDR v1 lacks a unique hardware identity and profile readback; document that limit.

## R4 — Interrupted command outcomes

- Persist a start request and counter baseline before sending START. Distinguish requested, acknowledged and unconfirmed outcomes; never retry START blindly.
- On timeout, close the socket so a late reply cannot be assigned to the next command. Reconcile a possible run through bench state/counter observations.
- Failed upload invalidates local upload verification. Do not resume at a guessed frame or automatically replace the profile; require an explicit whole-upload retry.
- Failed Stop is labeled “Stop not confirmed — bench may still be running”. Pause/Resume errors are likewise explicit.

Acceptance: tests drop START/STOP replies and interrupt upload; only one START is sent, failed upload never enables Start, and same old cycle index without new lifetime-counter evidence cannot falsely confirm completion.

## R5 — History across observation gaps

- Retain pre-gap and recovered counter snapshots and link-loss/recovery events. Use counter deltas only within a consistent counter epoch.
- Record reboot/capability mismatch and unconfirmed command outcomes as explicit events, including the affected session where known.
- Keep exact bench event times unknown during an outage. Session start/end labels are controller observation times. Missing intermediate cycles are summarized, not fabricated.
- Show uncertainty in expandable History details and CSV, even if final counters establish that the finite target was reached.

Acceptance: complete/restarted/continuing/lost-ack sessions have appropriate status and warnings; no duplicate cycles, negative deltas or invented channel hours.

## R6 — Measured upload progress

- Track frames acknowledged / total, phase (preparing/sending/verifying/completed/failed), elapsed time, and checksum-confirmed status using monotonic time.
- Publish progress through the nonblocking snapshot path while the upload HTTP request remains pending. Frames sent are not the same as frames acknowledged.
- Show percentage during sending; 100% frames acknowledged still says verifying until COMMIT's checksum is checked. Estimate remaining transfer time only after enough measured acknowledgements, clearly labeled estimated.
- Keep the current cross-tab “Uploading…” banner and duplicate-operation guards. Preserve the error and actual elapsed duration after failure.

Acceptance: a deliberately slowed simulator upload yields intermediate progress; status reaches complete only after checksum verification; timing is measured, not inferred from playback duration.

## R7 — Restore the intended profile draft

- Find the newest compiled profile matching the restored source, rather than comparing only the globally newest profile.
- If the supplied RCOU source has no matching saved draft, default to its known continuous 40–100-second, 50-fps demonstration segment. Other source defaults remain bounded by their duration and known gaps.
- Preserve deliberate saved trim/rate/mapping settings, including intentionally short profiles. Clearly show compiled duration/frame count before upload.

Acceptance: matching older-global profile restores correctly; supplied source without a draft defaults to 60 seconds; explicit 0–4-second saved drafts are preserved.

## R8 — Windows receiver launcher

- Add a receiver-only Python launcher plus a Windows .cmd wrapper using .venv/Scripts/python.exe. Auto-detect exactly one CH340 1a86:7523 receiver, allow an explicitly selected matching port, refuse ambiguity or a bench adapter, and open at 115200 with DTR/RTS unasserted.
- Print identified port and raw receiver lines, write a timestamped local capture, and explain no-data versus NO SIGNAL. Ctrl-C closes only the receiver monitor. Never flash, open the bench port or send serial commands.
- Document Python/pySerial prerequisites and Mac-dashboard/Windows-receiver separation.

Acceptance: mocked port tests cover receiver discovery, wrong/ambiguous adapters and no-data handling; existing firmware remains untouched. Windows execution still requires the user's Windows machine and must be labeled untested until run there.

## R9 — Validation and hardware follow-up

- Add a controllable TCP fault proxy for the supplied simulator: close/block the connection, delay a reply, and drop one acknowledgement without stopping the simulator's bench clock.
- Run isolated end-to-end cases: browser absent, link absent for at least six seconds mid-run, run finishing while disconnected, lost START reply, interrupted upload, reboot, and identity mismatch. Save commands, counter bounds and session outcomes as artifacts.
- Add a read-only/preflight-first hardware checklist and a finite signal-only test procedure that requires explicit execution. Do not run the organizer's scorer on the real bench: it uploads, starts and can clear counters.
- Longer actual actuator-load and 16-channel tests remain pending until the appropriate bench, power, loads and clearance are available. Independent receiver data verifies electrical PWM, not mechanical motion or actuator wear.

Acceptance: simulator evidence and meaningful backend/widget tests pass; release build works; implementation log states precisely which hardware tests remain pending. Activate the new backend only after checking the real bench is stopped; activation does not upload or start it.

## Execution log

| Phase | Status | Evidence |
| --- | --- | --- |
| R1 | Complete | 21 backend tests; supplied-simulator one-cycle run persisted with no browser polling, +1 cycle/+4 run_s. |
| R2 | Complete | 22 backend and 11 Flutter tests; capped retry delay, stale warning and disabled Start verified. |
| R3 | Complete | 24 backend tests; changed capacity rejected and observed reboot saved with uncertain stop time. |
| R4 | In progress | Persist start request before command and report unconfirmed outcomes next. |
| R5–R8 | Planned | Execute after the preceding acceptance checks. |
| R9 | Planned / hardware conditional | Supplied simulator available; physical servo and 16-channel equipment unverified. |

Before beginning, save the already-tested upload indicator and receiver documentation as a Git checkpoint. Keep `IMPLEMENTATION_PLAN.md.zip` untouched and local history backups ignored. Update IMPLEMENTATION_LOG.md after each verified phase; do not describe unperformed tests as passing.
