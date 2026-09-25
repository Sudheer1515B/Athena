# Independent PWM receiver

This sketch measures the physical signal from each of the WDR bench's four PWM outputs and prints HIGH width / full period / pulse count at 115200 baud. It does not command the bench and requires no servos. It supports classic ESP32 and ESP32-S3, choosing input pins at compile time.

## Device identity observed on this Mac, 25 September 2026

| Role | USB port | USB adapter | Verified identity | Flash policy |
| --- | --- | --- | --- | --- |
| WDR bench/controller | `/dev/cu.usbserial-0001` | CP2102, VID:PID `10c4:ea60`, serial `0001` | WDR `INFO`: `team=WDR_REFERENCE`, 4 channels, 8,000 frames | **Never flash**; fixed competition firmware |
| PWM receiver | `/dev/cu.usbserial-10` | CH340, VID:PID `1a86:7523` | esptool reports `ESP32-D0WD-V3`, a **classic ESP32**, not ESP32-S3 | Receiver sketch uploaded at 115200 baud; verified serial output |

USB port names can change after reconnection. Re-check both the adapter identity and chip before uploading. The chip-ID probe was performed only on `/dev/cu.usbserial-10`; the bench port was not probed with esptool.

The first upload attempt at 921600 baud failed before flash verification; retrying at 115200 baud completed and verified hashes. Opening the receiver serial port then printed `NO SIGNAL` for all four inputs, which is expected until the jumper wires are attached. The WDR bench firmware has not been changed.

## Wiring after confirming the receiver board

If the receiver is the observed **classic ESP32**:

| WDR classic ESP32 output | Receiver classic ESP32 input |
| --- | --- |
| OUT0 GPIO25 | GPIO32 |
| OUT1 GPIO26 | GPIO33 |
| OUT2 GPIO27 | GPIO34 |
| OUT3 GPIO33 | GPIO35 |
| GND | GND |

If the receiver is instead a real **ESP32-S3**, use receiver GPIO4, GPIO5, GPIO6, GPIO7 in the same OUT0–OUT3 order. Do not use GPIO6 or GPIO7 on the observed classic ESP32 receiver: those pins belong to flash.

Power both boards over separate Mac USB cables. Do not join their 3V3 or 5V pins, and do not apply servo power to the receiver. Wire while USB is unplugged. For this first signal-only demo, leave servos and external servo supply disconnected. After uploading, open only the **receiver** serial port at 115200 baud; Athena keeps the **bench** serial port.

To monitor the receiver from this Mac after wiring:

```sh
.venv/bin/python -m serial.tools.miniterm /dev/cu.usbserial-10 115200
```

The output reports `OUTn <high width>us/<period>us #<pulse count>` every 250 ms. Expected idle is around `1500us/20000us`. A `NO SIGNAL` line means no valid pulse arrived on that input in the last 100 ms. Quit miniterm with Ctrl-]. Do not open `/dev/cu.usbserial-0001` in this terminal; that port belongs to the WDR bench and Athena uses it.

## Verified no-loss physical check

On 25 September 2026, with no servos attached, the receiver measured all four bench outputs at idle near `1499–1500us/20000us`. We then sent only `SET` with unique target widths `1100,1300,1700,1900` and read `1100,1297,1694,1891` µs on OUT0–OUT3, all with 20,000 µs periods. `STOP` returned every output to 1500 µs. The bench still reported its original **100-frame committed profile** and unchanged lifetime counters `cycles=21 run_s=24 active_s=23,23,23,6`.

The repeatable [check_pwm.py](check_pwm.py) script verifies the USB identities before sending only `SET` and `STOP`. It neither uploads a profile nor starts playback. Run it only while the bench is STOPPED and the receiver is wired as above:

```sh
.venv/bin/python -u pwm_receiver/check_pwm.py
```

Uploading a new flight-log profile would discard the bench's existing committed profile, and WDR v1 has no profile-readback command. Do not upload until replacing that profile is explicitly acceptable.
