# Windows receiver monitor with Athena on the Mac

Use the Windows laptop to display the already-programmed receiver ESP32's physical PWM measurements. Keep Athena on the Mac and control the WDR bench over Wi-Fi. No firmware upload, Arduino build, Flutter installation, or backend is needed on Windows for this arrangement.

## Connections

- Receiver ESP32 → Windows laptop by USB.
- WDR bench → a separate USB power source or computer.
- Keep the existing signal wiring: bench GPIO25 → receiver GPIO32, GPIO26 → GPIO33, GPIO27 → GPIO34, GPIO33 → GPIO35, and GND → GND. This receiver was verified as a classic ESP32, not an S3.
- Do not connect the boards' 5V or 3V3 pins together. For this signal-only proof, leave servos disconnected. Disconnect power before changing wires.
- The Mac and WDR bench must share a reachable Wi-Fi network. Windows does not need network access to the bench to read the receiver's USB output.

## Start the receiver monitor on Windows

Install Python if `py --version` does not work. Open PowerShell in the cloned repository's root folder, then run these commands once:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install pyserial==3.5
```

Find the receiver port:

```powershell
.\.venv\Scripts\python.exe -m serial.tools.list_ports -v
```

Look for CH340 / USB Serial and hardware ID `VID:PID=1A86:7523`. Note its COM number. If identification is unclear, unplug and reconnect only the receiver and compare the port list. Do not select a bench serial port. If no COM port appears, check the data cable and Windows Device Manager for a missing CH340 driver before proceeding.

Replace `COM5` below with the identified receiver port:

```powershell
.\.venv\Scripts\python.exe -m serial.tools.miniterm COM5 115200
```

Close other serial monitors before opening this port. Expected idle output is approximately:

```text
t=...ms | OUT0 1500us/20000us #... | OUT1 1500us/20000us #... | OUT2 1500us/20000us #... | OUT3 1500us/20000us #...
```

The first number is pulse HIGH time, the second is full period, and `#` is the received pulse count. `NO SIGNAL` means that input has not received a valid recent pulse; check bench power, signal wiring and common ground. Uploading a profile does not itself change the PWM widths: replay starts after START. Values that remain constant can also be correct for a constant segment of the profile.

Press **Ctrl + ]** to exit miniterm. Exiting this monitor does not stop a bench replay; use Athena's **Stop** button for that.

Port discovery, miniterm syntax and exit shortcut are documented in the [official pySerial tools reference](https://pyserial.readthedocs.io/en/latest/tools.html).

## Start Athena on the Mac

The existing `Start Wi-Fi Hardware Proof.command` launcher expects the receiver USB port to be on the Mac, so use the backend directly when the receiver is on Windows. From the Mac's repository root:

```sh
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080
```

Use the existing Mac virtual environment and Flutter web build. If the web build is missing, build it from `athena` with `flutter pub get` followed by `flutter build web`, then return to the repository root. Do not start a second backend if one is already using port 8080.

1. Open `http://127.0.0.1:8080` on the Mac.
2. In Settings, connect to the current Wi-Fi bench address. Last verified: `10.178.45.105`, TCP port `3333`; its address can change. Confirm `team=WDR_REFERENCE`, four channels, and STOPPED.
3. Select the intended CSV/profile, compile and validate, then upload once and wait for completion. **Uploading replaces the bench's committed profile.** A restarted backend must verify an upload in its own session before enabling Start; it cannot recover the saved profile's identity from frame count alone.
4. Start **one finite cycle**. Watch Athena's progress and sampled command graph alongside the Windows terminal's independently measured PWM widths and periods.
5. Wait for automatic completion, then refresh History and inspect the recorded session and bench counter deltas. Use Stop if you need to end the run early.

Stop the bench before closing Athena so the final observation can be saved. Press Ctrl-C in the Mac backend terminal to stop the server. Neither monitor startup nor backend startup flashes either ESP32 or clears counters. The Mac `.command` launchers and `check_pwm.py` with its Mac USB identities are not the Windows receiver-monitor path.
