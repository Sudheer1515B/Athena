# Four-actuator bring-up

Status: the team is preparing four real actuators. Models, power supply, driver/ESC requirements and safe pulse/travel limits are pending confirmation. Software already supports four PWM outputs and independent receiver measurements. Do not treat the prior signal-only validation as validation with real actuator loads.

Update: user confirms **drone motors**; ESC models and power details remain unknown. Assume this is not a positional-servo hookup until the hardware team confirms otherwise. Brushless drone motors need ESCs; the bench's ordinary servo PWM cannot be assumed compatible with DShot/OneShot-only ESC configurations.

**Compatibility gate:** WDR emits 1500 us on boot/STOP and automatic completion; upload also sends STOP. Typical unidirectional PWM ESCs use about 1000 us for zero and 2000 us for full throttle, so 1500 us may command substantial throttle. Changing the dashboard's Stop button alone cannot correct the fixed firmware's idle/completion behavior. Keep actuator power off and propellers removed until the ESC manual/team confirms signal protocol, period and 1500-us behavior. Do not automatically calibrate or arm an unknown ESC or replay the existing servo profile as throttle.

Primary references: [ArduPilot PWM ESC protocols](https://ardupilot.org/copter/docs/common-brushless-escs.html) explains typical zero/full pulse widths and distinct protocols; [ESC calibration](https://ardupilot.org/copter/docs/esc-calibration.html) requires model-specific setup and propeller removal. These describe common behavior, not identification of the team's unknown ESC.


## Confirm before playback

- Device type/model: ordinary PWM servo, continuous-rotation servo, ESC-controlled motor, or a motor needing a separate driver. Raw motors cannot be powered or driven directly by ESP32 GPIO.
- Required supply voltage, startup/stall current and an adequately rated separate actuator supply. Do not power actuator loads from ESP32 GPIO/3V3 or assume the Mac's USB supply can power four actuators. Positive actuator supply wiring depends on the actual device/driver; keep it out of receiver GPIO and ESP32 supply rails.
- Input compatibility with 3.3 V bench signals, accepted PWM period, safe HIGH-width range, neutral/stop behavior, arming procedure if applicable, and mechanical clearance.
- A reachable physical actuator-power cutoff. **WDR STOP produces 1500 µs on all outputs; it does not disconnect power.** That can center a positional servo and may not stop another device type. Upload also begins by sending STOP. Reconnection alone does not command playback, but powering the bench can present its idle output.

## Signal connections

For compatible PWM inputs, each bench output signal can feed both its actuator/driver signal input and the existing receiver input. The receiver monitors the bench signal electrically; it does not carry actuator current.

| Output | Bench GPIO | Receiver GPIO | Compatible actuator signal |
| --- | --- | --- | --- |
| OUT0 | 25 | 32 | Device 1 signal input |
| OUT1 | 26 | 33 | Device 2 signal input |
| OUT2 | 27 | 34 | Device 3 signal input |
| OUT3 | 33 | 35 | Device 4 signal input |

Common signal ground: bench GND, receiver GND and actuator/driver signal ground. Actuator return current should use suitably rated supply wiring, not receiver jumper wires. Change wiring with power removed. For rotating motors, remove propellers/other hazardous attachments before bring-up and secure the test assembly.

## Software sequence after compatibility is confirmed

1. Keep the known firmware on both ESP32s. Close other receiver serial readers, start Athena and connect the identified CH340 receiver in Settings. Connect the bench over Wi-Fi and inspect state/capabilities without starting playback.
2. Configure each output's source mapping and model-specific minimum/maximum pulse limits. The protocol's 500–2500 µs validation range is not a guarantee that a particular actuator can safely travel across that range. Existing full-range flight profiles must be reviewed against actual limits before upload.
3. Use a short, reviewed profile and one finite cycle for initial bring-up. Verify one actuator first, then all four, with the team controlling actuator power and mechanical clearance. Manual SET is also a motion command; use only model-confirmed values.
4. Compare commanded PWM, independently measured PWM and visibly observed actuator response. Watch supply behavior and bench resets under load. Receiver pulses alone do not prove motion, torque, position or actuator health.
5. After the short run, review bench-reported cycle/running/active-hour deltas. Those are WDR accounting values, not measurements of actual mechanical work or current. Proceed to longer endurance playback only after stable loaded operation is established.

## Fault demonstrations with actuators

- For a receiver-detection demo, disconnect only the receiver branch of a signal, keeping the actuator signal branch intact. Athena should show that receiver input as NO SIGNAL; the actuator may continue moving. This demonstrates measurement loss, not a stopped actuator.
- Pulling the actuator's own signal branch is not detected if the receiver still sees bench output. Motor-side connection/position/current feedback requires additional instrumentation. Do not claim fault coverage beyond where the receiver is connected.
- Wi-Fi loss does not stop bench playback. A disconnected dashboard cannot provide a working software Stop; use the physical power cutoff if motion must end.
- Reboot recovery asks permission before re-upload and a new finite run. WDR cannot resume at an exact frame; the interrupted cycle restarts. Re-check the mechanism before approving recovery with real loads.

## Current readiness

Source rollback is preserved on `prototype-rollback-20260926` at `6f8b5b8`. Current physical-feedback/recovery release is `21491aa`. The Mac receiver was verified on `/dev/cu.usbserial-10` (CH340 1a86:7523), with four idle PWM inputs at roughly 1500 µs / 20,000 µs. No loaded actuator run has been performed by automation. Model-specific setup and the team's loaded test remain pending.

## Tentative ESC identification: Readytosky 40A

User reports “Readytosky 40A?”; treat brand/current as tentative, not a confirmed variant. Manufacturer lists at least:

- [2–4S 40A with 5V/3A BEC](https://www.readytosky.com/e_productshow/?1223-NEW-40A-ESC-2-4S-5V3A-Brushless-ESC-Electronic-Speed-Controller-For-F450-S500-ZD550-RC-Helicopter-Quadcopter-1223.html=), product 2020831113544.
- [2–6S 40A OPTO, no BEC](https://www.readytosky.com/e_productshow/?301-Readytosky-2-6S-40A-Electronic-Speed-Controller-301.html=), product 201758105925; manufacturer describes throttle refresh rates up to 621 Hz, but does not establish the exact team's unit, its low-throttle endpoint or 1500-us stop behavior.

The manufacturer pages checked do not provide a verified model-specific arming/zero-throttle pulse or 3.3-V input threshold. Do not infer either from current rating or another manufacturer's manual. Obtain label/packaging details and the actual supplied instructions. Keep the fixed bench's 1500-us idle incompatibility unresolved until verified. No ESC calibration or live command was issued during research.

## Corrected identity and OUT0-only test

User corrected the brand to **Readytofly 40A**, superseding the tentative Readytosky identification above. Exact manufacturer instructions, voltage range and low/arming endpoints remain unverified; the Readytosky variant specifications do not apply to this unit.

User explicitly confirmed propellers removed, motors secured and an attended motor-power cutoff, then authorized an **OUT0-only** brief output probe. `scripts/esc_pulse_probe.py --run` now commands only OUT0: typical PWM low 1000 us for 3 s, 1100 us for 2 s, then 1000 us. OUT1–OUT3 are untouched, not guaranteed stopped. This is a limited compatibility trial using conventional PWM values, not a verified model-specific arming/calibration routine. It never uploads, flashes, clears counters or sends WDR STOP. Disconnect motor power before any bench reset/upload/Stop because firmware can output 1500 us. Do not run other controllers against the bench during this direct probe.

The first attempted connection to `10.178.45.105:3333` timed out **before any output command**. No motor test has occurred. Athena was not listening on local port 8080 and no ESP32 USB adapters were present on the Mac at that check. Current bench IP/reachability is required before retry.
