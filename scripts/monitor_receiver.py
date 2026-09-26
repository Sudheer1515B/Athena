"""Read only the independent CH340 PWM receiver; never command or flash a bench."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

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


def monitor(device, capture, *, clock=time.monotonic, output=print, on_line=None):
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
            if on_line:
                on_line(line)
            last_line, warned = clock(), False
        elif clock() - last_line >= 5 and not warned:
            output("No serial data for 5 seconds. Close other serial monitors; check receiver USB/port. "
                   "NO SIGNAL lines instead mean the firmware is running but PWM input is absent.", flush=True)
            warned = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Explicit matching CH340 receiver, for example COM3")
    parser.add_argument("--serve", action="store_true", help="Share receiver measurements with Athena over the local network")
    parser.add_argument("--listen-port", type=int, default=8766)
    args = parser.parse_args()
    port = select_receiver(list_ports.comports(), args.port)
    directory = ROOT / "var" / "demo"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"receiver-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.log"
    device = Serial(port=None, baudrate=115200, timeout=.25)
    device.port = port
    device.dtr = device.rts = False
    server = None
    bridge = MeasurementBridge() if args.serve else None
    try:
        if bridge:
            server = ThreadingHTTPServer(("0.0.0.0", args.listen_port), bridge.handler())
            threading.Thread(target=server.serve_forever, daemon=True).start()
            print(f"Receiver bridge listening on port {args.listen_port}.\nPairing token: {bridge.token}\n"
                  "In Athena Settings enter this computer's Wi-Fi IPv4 address, port and token.\n"
                  "On Windows allow this receiver bridge on the private network if prompted.", flush=True)
        device.open()
        print(f"Receiver {port}, USB 1a86:7523, 115200 baud. Capture: {path}\nCtrl-C stops this monitor.", flush=True)
        with path.open("w", encoding="utf-8") as capture:
            monitor(device, capture, on_line=bridge.accept if bridge else None)
    except KeyboardInterrupt:
        print("\nReceiver monitor stopped.")
    finally:
        device.close()
        if server:
            server.shutdown()
            server.server_close()


class MeasurementBridge:
    def __init__(self):
        self.token = secrets.token_urlsafe(24)
        self.instance_id = str(uuid4())
        self.lock = threading.Lock()
        self.line = None
        self.received = None
        self.sequence = 0

    def accept(self, line):
        sys.path.insert(0, str(ROOT)) if str(ROOT) not in sys.path else None
        from backend.receiver import parse_measurement
        try:
            parse_measurement(line)
        except ValueError:
            return
        with self.lock:
            self.line, self.received = line, time.monotonic()
            self.sequence += 1

    def handler(self):
        bridge = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/measurement":
                    self.send_error(404)
                    return
                if not secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {bridge.token}"):
                    self.send_error(401)
                    return
                with bridge.lock:
                    payload = {"protocol": 1, "receiver": "WDR_PWM_RECEIVER", "instance_id": bridge.instance_id,
                               "sequence": bridge.sequence, "line": bridge.line,
                               "sample_age_s": None if bridge.received is None else time.monotonic() - bridge.received}
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        return Handler


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Receiver monitor: {error}", file=sys.stderr)
        sys.exit(1)
