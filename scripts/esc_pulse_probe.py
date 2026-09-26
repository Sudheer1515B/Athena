"""Explicit, propeller-free PWM ESC probe; does not use WDR STOP or replay."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.bench_usb import TcpBench


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="10.178.45.105")
    parser.add_argument("--channel", type=int, choices=range(4), default=0, help="Bench output: 0=GPIO25, 1=GPIO26, 2=GPIO27, 3=GPIO33")
    parser.add_argument("--run", action="store_true", help="Props removed, motors secured, power cutoff attended: issue the pulse probe")
    parser.add_argument("--set-only", action="store_true", help="With --run, set only the selected output to 1000 us; do not perform the 1100-us test")
    args = parser.parse_args()
    bench = TcpBench(expected_team="WDR_REFERENCE")
    armed = False
    try:
        bench.connect(args.host, 3333)
        snapshot = bench.snapshot()
        print(json.dumps({"connection": snapshot["connection"], "state": snapshot["bench_state"]}), flush=True)
        if int(bench.info["ch"]) != 4 or bench.status["state"] != "STOPPED":
            raise RuntimeError("Requires four-channel WDR_REFERENCE already STOPPED; no Stop will be sent")
        if not args.run:
            print("Read-only preflight complete. No output command sent.", flush=True)
            return
        if args.set_only:
            bench.set_pulse(args.channel, 1000)
            print(f"OUT{args.channel} set to 1000 us. Other channels untouched; no STOP sent.", flush=True)
            bench.refresh()
            print("Reported state: " + json.dumps(bench.status), flush=True)
            return
        armed = True
        bench.set_pulse(args.channel, 1000)
        print(f"OUT{args.channel} commanded to 1000 us; waiting 3 seconds. Other channels are untouched. This is a typical PWM ESC low input, not a verified model-specific stop.", flush=True)
        time.sleep(3)
        bench.set_pulse(args.channel, 1100)
        print(f"OUT{args.channel} commanded to 1100 us for 2 seconds. Other channels are untouched.", flush=True)
        time.sleep(2)
    finally:
        if armed:
            try:
                if not bench.connected:
                    raise RuntimeError("Bench connection lost")
                bench.set_pulse(args.channel, 1000)
                print(f"Returned OUT{args.channel} to 1000 us. Other channels untouched. Disconnect motor power before bench reset, upload, STOP or profile playback: those can produce 1500 us.", flush=True)
            except Exception as error:
                print(f"OUTPUT RETURN NOT CONFIRMED: {error}. Disconnect motor power now.", file=sys.stderr, flush=True)
        bench.disconnect()


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(f"Probe stopped: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
