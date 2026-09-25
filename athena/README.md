# Athena Dashboard

Athena is the Flutter Web dashboard for Welkinrim Technologies' drone-actuator life-test hackathon challenge.

It will let an engineer import a recorded drone flight log, map actuator commands to a 16-channel PWM bench, preview and validate the resulting profile, control replay through a FastAPI service, and review confirmed cycles and per-channel running hours.

## Current status

This directory is intentionally a fresh project created with `flutter create`. It still contains the default counter application. Welkinrim's frozen WDR Protocol v1, challenge brief, sample `RCOU.csv`, UI/hardware references and official `wdr_tool.py` have been inspected. The supplied simulator passed 85/85 both in-process and over TCP; Athena itself is not implemented. The current user request is documentation only, so do not begin coding without a subsequent instruction.

## Intended boundary

Flutter owns presentation and operator interaction:

- import and log inspection;
- 16-channel mapping and profile preview;
- profile validation/upload and Start/Pause/Resume/Stop controls;
- live state, telemetry and faults;
- run history and evidence export.

FastAPI will own binary log parsing, deterministic profile generation, simulator/bench communication, the run state machine and SQLite persistence. It bridges Flutter HTTP/WebSocket traffic to the bench's line-based TCP protocol on port 3333. The simulator or hardware controller must generate real-time PWM playback from an uploaded profile; Flutter must not schedule individual servo frames.

## Before coding

Read [`../IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) for the current detailed specification and [`../IMPLEMENTATION_LOG.md`](../IMPLEMENTATION_LOG.md) for actual progress. [`../PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md) and [`../SUPPLIED_ARTIFACTS.md`](../SUPPLIED_ARTIFACTS.md) preserve context and source facts. Use the official simulator and live `INFO` capabilities; older research proposals are superseded where they conflict.

## Basic Flutter commands

```sh
flutter pub get
flutter run -d chrome
flutter test
flutter analyze
flutter build web
```
