# Athena Dashboard

Athena is the Flutter Web dashboard for Welkinrim Technologies' drone-actuator life-test hackathon challenge.

It will let an engineer import a recorded drone flight log, map actuator commands to a 16-channel PWM bench, preview and validate the resulting profile, control replay through a FastAPI service, and review confirmed cycles and per-channel running hours.

## Current status

M1 and M2 are complete. The dashboard shell follows the supplied HTML and `mock.css`. The Profile page imports a `TimeUS,C1…C16` CSV, shows source statistics and gaps, maps channels, compiles a deterministic WDR pulse profile, previews source and compiled traces, and exports the compiled CSV. It restores the most recent source/profile after refresh. Until M3, the compile target is clearly labeled as the reference bench's provisional four channels and 8,000 frames; live `INFO` must match before upload.

## Intended boundary

Flutter owns presentation and operator interaction:

- import and log inspection;
- 16-channel mapping and profile preview;
- profile validation/upload and Start/Pause/Resume/Stop controls;
- live state, telemetry and faults;
- run history and evidence export.

FastAPI will own binary log parsing, deterministic profile generation, simulator/bench communication, the run state machine and SQLite persistence. It bridges Flutter HTTP/WebSocket traffic to the bench's line-based TCP protocol on port 3333. The simulator or hardware controller must generate real-time PWM playback from an uploaded profile; Flutter must not schedule individual servo frames.

## Project references

Read [`../IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) for the current detailed specification and [`../IMPLEMENTATION_LOG.md`](../IMPLEMENTATION_LOG.md) for actual progress. [`../PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md) and [`../SUPPLIED_ARTIFACTS.md`](../SUPPLIED_ARTIFACTS.md) preserve context and source facts. Use `../handout_controller_teams/` and live `INFO` capabilities; older root copies and research proposals are superseded where they conflict.

## Basic Flutter commands

```sh
flutter pub get
flutter run -d chrome
flutter test
flutter analyze
flutter build web
```
