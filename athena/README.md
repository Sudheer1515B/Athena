# Athena Dashboard

Athena is the Flutter Web dashboard for Welkinrim Technologies' drone-actuator life-test hackathon challenge.

It will let an engineer import a recorded drone flight log, map actuator commands to a 16-channel PWM bench, preview and validate the resulting profile, control replay through a FastAPI service, and review confirmed cycles and per-channel running hours.

## Current status

M1 is complete. The default counter application has been replaced by a tested Dashboard/Profile/History/Settings shell based on the supplied HTML and `mock.css`. It reads an honest empty snapshot from the FastAPI service over HTTP/WebSocket; bench transport, import, compilation and controls arrive in later milestones. The newest handout simulator reports four channels and 8,000 frames and passes its 85-point scorer.

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
