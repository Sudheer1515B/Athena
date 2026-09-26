# Physical feedback and power-loss recovery

The primary measured PWM chart comes from the independent receiver ESP32. The separate commanded PWM chart comes from WDR STATUS and describes requested outputs: it cannot detect a broken signal wire or prove an actuator moved. Neither ESP32 firmware is changed by this feature.

## This Mac: start and connect

1. Keep the verified wiring: bench GPIO25 → receiver32, GPIO26 → receiver33, GPIO27 → receiver34, GPIO33 → receiver35, GND → GND. Leave servos disconnected for this signal-only demo. Do not pull common ground or join 5V/3V3 supplies.
2. Close miniterm and other receiver terminal monitors; Athena now owns the receiver's serial reader. Both boards may be USB-powered; the bench is controlled over Wi-Fi, not its USB serial port.
3. Start Athena using `.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080 --no-access-log` if it is not already running. Open `http://127.0.0.1:8080` and reload the updated release.
4. In Settings click **Connect USB receiver (CH340)**. Auto-selection requires exactly one adapter with VID:PID `1a86:7523`. The bench's CP2102 `10c4:ea60` adapter is refused. On this Mac the receiver was verified at `/dev/cu.usbserial-10`; names may change.
5. Connect the WDR bench over Wi-Fi in Settings (last known `10.178.45.105:3333`). Compile/verify a profile, upload, and deliberately start a finite run. The measured chart shows received HIGH widths/periods; the command chart shows bench requests.

## Demonstrate a missing signal

During the signal-only run, remove one **signal jumper** at the receiver input, keeping both boards powered and common ground attached. Only that channel should turn red with **NO SIGNAL**. Its measured curve breaks and its current width is unknown, rather than invented as zero. Other channels continue. Reattach the jumper to restore measurements. The separate command chart may correctly remain normal because the bench still commands that output.

The receiver reports every 250 ms and considers a pulse missing after 100 ms; Athena UI polls about once a second, so allow roughly one to two seconds for the displayed change. Unplugging the receiver USB gives **UNKNOWN/stale**, not an assertion that the bench signal is absent. If all four receiver inputs report NO SIGNAL, Athena removes the measured graph and shows **NO PWM SIGNAL**. Electrical signal feedback does not establish mechanical motion, position, load or actuator wear. Receiver input noise/wiring faults can affect measurements.

## Demonstrate bench power loss

Use a sufficiently long finite run (for example the 60-second profile with two cycles). Keep the receiver and Mac powered; cut only the bench's power. The receiver should report missing pulses. After the backend observes connection loss, command samples disappear instead of remaining presented as live. Keep Athena running and do not click Disconnect, which cancels automatic recovery.

Restore bench power/network reachability. Athena checks protocol/team/channel capacity and reported uptime. When an interrupted known run returns after an observed reboot or with no committed profile, it offers **Review restart…** and **Keep stopped**. Reconnection never automatically uploads or starts motion. Review the remaining whole-cycle count and explicitly click **Approve restart** to re-upload the saved profile, verify COMMIT, and begin a new finite session.

WDR v1 has **no seek/frame-resume command**. Exact-frame continuation after reboot cannot be promised. The interrupted cycle restarts at frame 0; lifetime counters can lose progress around firmware checkpoints, and History keeps the original interrupted session uncertain. Approval starts a separate recorded session. If a Start reply is lost, the proposal is consumed before transmission so it cannot offer another blind Start. A failed upload can be retried only through another deliberate approval. Changed capabilities block automatic recovery. Changed bench IP needs a deliberate new connection. Recovery context currently requires the same running Athena backend; backend restart is a separate limitation. Simply disconnecting Wi-Fi does not stop bench playback, and no restart approval is needed if the recovered bench is still running.

## Receiver on Windows instead

After Python/pySerial setup in `pwm_receiver/WINDOWS_MONITOR.md`, double-click **Start Windows Receiver.cmd** or run:

```powershell
.\.venv\Scripts\python.exe -u scripts\monitor_receiver.py --serve
```

The bridge streams to the terminal, saves a local capture, and prints a pairing token. Allow it on the private network if Windows asks. In Athena Settings expand **Receiver on another computer**, enter that computer's Wi-Fi IPv4 address and token, and connect on port 8766. The Mac reads only authenticated receiver measurements; it does not expose its own backend to the network. Stop with Ctrl-C. Native Windows execution of this new bridge has not been verified here.

## Rollback

- `prototype-rollback-20260926` points to functional prototype checkpoint **6f8b5b8**, before the resilience work.
- **dee4d7f** saves the paused resilience work before physical-feedback changes; it is a WIP checkpoint, not a hardware-validation claim.
- The previous published prototype is **177aaf7**.

These references preserve the old source without deleting or resetting current work. To inspect/run the prototype separately, use a separate Git worktree/checkout at `prototype-rollback-20260926` and rebuild its Flutter release. Do not share the same active bench connection between two backends. Stop the current backend before switching the demo; keep SQLite data/backups separate when comparing versions. No rollback changes either ESP32's firmware or clears bench counters.

## Validation

Backend parser/staleness/adapter-selection tests cover missing signals, no invented widths, and refusing the bench adapter. Widget tests cover NO SIGNAL/UNKNOWN, hiding stale physical readings and waiting for explicit recovery approval. Supplied-simulator integration power-cycles a running bench, proves no automatic LOAD/START, approves a restart, verifies completion in a new session and rejects duplicate approval. Actual Mac receiver idle measurements were read from the identified CH340 at 1499–1500 µs / 20,000 µs on all four channels. Physical jumper removal and bench power-cut/recovery must still be rehearsed with the updated dashboard; they were not performed by automation.
