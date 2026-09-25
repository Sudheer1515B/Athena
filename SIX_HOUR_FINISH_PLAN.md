# Athena six-hour finish plan

**Date:** 26 September 2026. This is the timeboxed delivery order for the working controller. The detailed architecture and protocol rules remain in `IMPLEMENTATION_PLAN.md`; this plan chooses what to ship first.

## What the organizer actually asks for

The Competition A brief requires imported flight data, trace preview, live per-channel pulse widths, cycle progress, cycle and hour counters, controls, time sync, and browsable session/event history. It does **not** explicitly require an animated live graph, but the supplied dashboard mockup has a “Live traces · this cycle” graph. Build it after the authoritative backend state and history work, using measured/reported STATUS values rather than a decorative animation.

## Honest longer demonstration

Use the supplied, unmodified `RCOU.csv`, not a fabricated flight. Its only large gap is near 14.9–38.4 s. The continuous **40–100 s** window at **50 frames/s** maps C1–C4 to OUT0–OUT3 and compiles to **3,000 frames**, **60 seconds per cycle**, **SUM16 23174**. This is below the simulator's reported 8,000-frame capacity. One-minute replay is long enough to watch a graph move and see the counters accrue. Keep the earlier 40–44 s, 200-frame fixture as a fast smoke test. Never upload this profile to the physical USB bench while preserving its existing 100-frame profile.

## Delivery order and time caps

| Time | Work | Exit check |
| --- | --- | --- |
| 0–1 h | Backend protocol hardening: explicit TCP host/port for venue Wi-Fi, capability validation, correct simulator versus real-bench identity, clear failure states. | Supplied simulator still connects; invalid target/version/channel capacity fails clearly; no hardware upload. |
| 1–2.5 h | Durable accounting: record authoritative counter snapshots, start/stop/done sessions and events in existing SQLite tables; expose bounded history APIs. | One simulator cycle leaves a session and counter observations after backend restart; lifetime values come only from bench. |
| 2.5–3.5 h | Backend trace API: bounded recent STATUS pulse samples tagged with frame/cycle/time; avoid fabricated intermediate samples. | A 60-second simulator run yields changing four-channel samples; disconnect/stale state is explicit. |
| 3.5–4.5 h | Flutter: draw the live trace with a current-frame marker, make current-run progress and per-channel active time clear, show persisted sessions/events. | Browser visibly moves during a 60-second run, and History survives refresh. |
| 4.5–5.5 h | End-to-end against official `serve-sim`: import, compile, upload, run, pause/resume/stop, reconnect, restart and inspect history. | Exact 3,000-frame checksum, live counters, no false cycles, no silent replay or loss of prior history. |
| 5.5–6 h | Release build, one-command demo instructions, final regression checks, honest limits and push. | Fresh-machine instructions and 2-minute plus 60-second demo variants work. |

## Cut line

If time slips, protect the verified import→upload→run→counter path first. Next protect durable history and real Wi-Fi TCP connectivity. Keep a simple live graph only if it uses real STATUS observations. Defer PDF reports, life prediction, multi-bench support, raw `.bin`/`.ulg` import and visual flourishes. Do not expose a counter reset to the physical bench during this sprint; it would destroy the preserved lifetime totals.

## Checkpoint after backend-first work

The backend now records durable sessions, events and bench counter snapshots, marks interrupted sessions uncertain, accepts configurable WDR TCP targets, acknowledges `TIME`, and exposes stopped-only manual `SET`. Flutter shows actual one-second STATUS samples in a live graph, a cycle target/progress, dynamically sized output mapping, and a dated history view. The official simulator completed the full 60-second profile with the expected checksum and one added cycle. Backend tests, Flutter analysis/tests, and the web build pass.

The built app's connected live graph has been visually checked during a full simulator replay. History detail and CSV APIs were verified against saved simulator observations; the hours chart, channel filter and uncertainty display passed Flutter widget tests. The user later reported a connection-only reference-bench Wi-Fi check at `10.178.45.105:3333` with valid INFO and TIME acknowledgement. A separate finite replay of the **existing** physical profile captured all 100 reported frame widths without upload; the saved profile remained unchanged and lifetime cycles advanced from 21 to 24. Wi-Fi replay of Athena's **newly compiled flight-log profile** remains unverified.

## Safety and truthfulness gates

- The simulator is the primary long-run integration target. It is not proof of servo movement or 16-channel physical output.
- The real bench currently has a 100-frame saved profile and existing lifetime counts. `LOAD` replaces that profile; do not run a real-bench upload without a new explicit decision to replace it.
- Real Wi-Fi support can be implemented and simulator-tested now; connection to venue hardware remains unverified until a reachable bench and its address/network are available.
- The graph may show only sampled command pulse widths reported by `STATUS`; label it as sampled command output, not oscilloscope measurement or mechanical feedback.
