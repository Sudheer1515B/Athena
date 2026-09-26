"""Read only the independent CH340 PWM receiver; never command or flash a bench."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

from serial import Serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parent.parent
RECEIVER_ID = (0x1A86, 0x7523)


def select_receiver(ports, requested=None):
    matches = [p for p in ports if (p.vid, p.pid) == RECEIVER_ID
               and (requested is None or p.device == requested)]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one CH340 receiver (1a86:7523); found {len(matches)}. "
                         "Use --port COM3 only if that port is the receiver. Bench adapters are refused.")
    return matches[0].device


def monitor(device, capture, *, clock=time.monotonic, output=print):
    last_line = clock()
    warned = False
    while True:
        raw = device.readline()
        if raw:
            line = raw.decode("utf-8", errors="replace").strip()
            stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            output(line, flush=True)
            capture.write(f"{stamp} {line}\n")
            capture.flush()
            last_line, warned = clock(), False
        elif clock() - last_line >= 5 and not warned:
            output("No serial data for 5 seconds. Close other serial monitors; check receiver USB/port. "
                   "NO SIGNAL lines instead mean the firmware is running but PWM input is absent.", flush=True)
            warned = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Explicit matching CH340 receiver, for example COM3")
    args = parser.parse_args()
    port = select_receiver(list_ports.comports(), args.port)
    directory = ROOT / "var" / "demo"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"receiver-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.log"
    device = Serial(port=None, baudrate=115200, timeout=.25)
    device.port = port
    device.dtr = device.rts = False
    try:
        device.open()
        print(f"Receiver {port}, USB 1a86:7523, 115200 baud. Capture: {path}\nCtrl-C stops this monitor.", flush=True)
        with path.open("w", encoding="utf-8") as capture:
            monitor(device, capture)
    except KeyboardInterrupt:
        print("\nReceiver monitor stopped.")
    finally:
        device.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Receiver monitor: {error}", file=sys.stderr)
        sys.exit(1)
