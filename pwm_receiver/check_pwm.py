"""Check four physical PWM wires without changing the bench's saved profile.

Only SET and STOP are sent to the bench. No upload, replay, counter clear, or
firmware write occurs. The receiver ESP32 independently measures each output.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.bench_usb import UsbBench  # noqa: E402

EXPECTED_US = (1100, 1300, 1700, 1900)


def verify_ports(bench_name: str, receiver_name: str) -> None:
    ports = {port.device: port for port in list_ports.comports()}
    bench = ports.get(bench_name)
    receiver = ports.get(receiver_name)
    if bench is None or (bench.vid, bench.pid, bench.serial_number) != (0x10C4, 0xEA60, "0001"):
        raise RuntimeError("Bench USB identity mismatch; refusing to send commands")
    if receiver is None or (receiver.vid, receiver.pid) != (0x1A86, 0x7523):
        raise RuntimeError("Receiver USB identity mismatch; refusing to send commands")
    if bench_name == receiver_name:
        raise RuntimeError("Bench and receiver port cannot be the same")
    print(f"Bench: {bench_name} (CP2102, WDR)")
    print(f"Receiver: {receiver_name} (CH340, classic ESP32)")


def read_measurement(receiver: serial.Serial, timeout_s: float = 4.0) -> tuple[str, list[int]]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        line = receiver.readline().decode("ascii", errors="replace").strip()
        widths = []
        for channel in range(4):
            match = re.search(rf"OUT{channel} (\d+)us/(\d+)us", line)
            if match is None:
                break
            widths.append(int(match.group(1)))
        if len(widths) == 4:
            return line, widths
    raise RuntimeError("Receiver did not report all four PWM channels")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", default="/dev/cu.usbserial-0001")
    parser.add_argument("--receiver", default="/dev/cu.usbserial-10")
    args = parser.parse_args()
    verify_ports(args.bench, args.receiver)

    receiver = serial.Serial(args.receiver, 115200, timeout=0.25)
    bench = UsbBench()
    original_frames: str | None = None
    original_counters: dict[str, str] | None = None
    set_attempted = False
    try:
        bench.connect(args.bench)
        if (bench.info or {}).get("team") != "WDR_REFERENCE":
            raise RuntimeError("Unexpected firmware on the bench port")
        if (bench.status or {}).get("state") != "STOPPED":
            raise RuntimeError("Bench must be STOPPED before this check")
        original_frames = bench.status["frames"]
        original_counters = dict(bench.counters or {})
        for channel, width in enumerate(EXPECTED_US):
            set_attempted = True
            bench.command(f"SET {channel} {width}")
        receiver.reset_input_buffer()
        line, measured = read_measurement(receiver)
        print(line)
        for channel, (actual, expected) in enumerate(zip(measured, EXPECTED_US)):
            if abs(actual - expected) > 30:
                raise RuntimeError(f"OUT{channel}: expected {expected} us, measured {actual} us")
        print("PASS: four physical PWM outputs match the four receiver inputs.")
    finally:
        try:
            if bench.connected:
                try:
                    if set_attempted:
                        bench.command("STOP")
                        bench.refresh()
                        print(f"After STOP: {bench.status}; counters={bench.counters}")
                        if original_frames is not None and bench.status["frames"] != original_frames:
                            raise RuntimeError("Saved profile frame count changed unexpectedly")
                        if original_counters is not None and bench.counters != original_counters:
                            raise RuntimeError("Lifetime counters changed unexpectedly")
                finally:
                    bench.disconnect()
        finally:
            receiver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
