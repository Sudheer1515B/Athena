# Athena Dashboard

Athena is the Flutter Web dashboard for Welkinrim Technologies' drone-actuator life-test hackathon challenge.

It will let an engineer import a recorded drone flight log, map actuator commands to a 16-channel PWM bench, preview and validate the resulting profile, control replay through a FastAPI service, and review confirmed cycles and per-channel running hours.

## Current status

This directory is intentionally a fresh project created with `flutter create`. It still contains the default counter application. The simulator, protocol specification and sample flight logs have not yet been supplied, so product implementation has not begun.

## Intended boundary

Flutter owns presentation and operator interaction:

- import and log inspection;
- 16-channel mapping and profile preview;
- readiness checks and arm/start/pause/abort controls;
- live state, telemetry and faults;
- run history and evidence export.

FastAPI will own binary log parsing, deterministic profile generation, simulator/bench communication, the run state machine and SQLite persistence. The simulator or hardware controller must generate real-time PWM playback from an uploaded profile; Flutter must not schedule individual servo frames.

## Before coding

Read [`../PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md) and the reports linked from it. When the supplied artifacts arrive, inspect and hash them before choosing message models, packages or screen behavior tied to the protocol.

## Basic Flutter commands

```sh
flutter pub get
flutter run -d chrome
flutter test
flutter analyze
flutter build web
```
