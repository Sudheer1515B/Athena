# Drone Actuator Life Test Bench — Simple Brief

## Problem statement

> Build a web-based controller that converts recorded drone flight logs into servo command profiles, replays them over Wi-Fi on a 16-channel PWM test bench, and tracks cycles completed and per-channel running hours so engineers can quantify actuator life. A bench simulator, protocol spec and sample logs are provided.

**Provider:** Welkinrim Technologies  
**Hackathon:** Saturday, 26 September 2026

## What are we building?

A drone flight log records the commands sent to its motors or servos. Our app turns those commands into a repeatable bench test.

```text
Flight log → Flutter website → FastAPI server → Wi-Fi → 16-channel test bench
                              ↓
                    Cycles and running hours
```

The engineer uploads a log, maps its outputs to bench channels, checks the movement preview and starts the test. The app then shows progress and saves the history of each actuator.

## Technology

- **Flutter Web:** screens, charts and controls
- **FastAPI:** reads logs, builds profiles and talks to the bench
- **SQLite:** saves tests, faults, cycles and running hours
- **WebSocket:** carries live commands and status

The complete command profile should be uploaded before the test. The simulator or bench must play it using its own clock because browser and Wi-Fi timing can lag. Flutter only sends commands such as **Arm**, **Start**, **Pause** and **Stop**.

## Minimum hackathon version

1. Import one supplied flight-log format.
2. Map commands to as many as 16 channels.
3. Preview the profile and block unsafe values.
4. Replay it through the supplied simulator.
5. Show live values and connection status.
6. Count completed cycles and confirmed running time.
7. Preserve results after refresh, restart or Wi-Fi loss.

A cycle counts only after the bench confirms the whole profile was completed. If Wi-Fi fails halfway through, save the confirmed running time but do not count a completed cycle. Store totals against an actuator ID or serial number because an actuator can move to another channel.

## Demo idea

Import a log and map four actuators. First enter an unsafe limit so the app blocks the run. Correct it, start three cycles and disconnect Wi-Fi during cycle two. Show that the app keeps one completed cycle and the confirmed partial running time without inventing data. Reconnect, complete the test and show the saved history.

> We turn real flights into repeatable bench tests and make every command, test cycle, running hour and fault traceable to its source log and actuator.

Call the result **traceable command exposure**. It does not certify actuator lifetime unless physical movement, current, temperature and load are also measured.

## Safety

Secure and guard moving parts, remove propellers, set a safe range for every actuator and use a physical emergency stop that works without the app. Test channel order and PWM signals with actuator power disconnected first.

## Missing inputs

The promised simulator, protocol specification and sample logs are not currently in the workspace. They are required to confirm the real message format, units, limits and channel numbering.

For implementation details, see the [full technical report](</Users/krisdreemur/Developer/SSN/reports/Drone actuator life test bench.md>).
