"""Independent PWM observations. Never infer physical feedback from STATUS."""
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import ipaddress
import json
import re
import threading
import time
from urllib.request import Request, urlopen


def parse_measurement(line):
    if not re.match(r"^t=\d+ms\s*\|", line):
        raise ValueError("Not a receiver measurement")
    parts = line.split("|")[1:]
    if len(parts) != 4:
        raise ValueError("Expected four receiver channels")
    channels = []
    for index, part in enumerate(parts):
        missing = re.fullmatch(rf"\s*OUT{index} NO SIGNAL\s*", part)
        measured = re.fullmatch(rf"\s*OUT{index} (\d+)us/(\d+)us #(\d+)\s*", part)
        finding = re.fullmatch(rf"\s*OUT{index} (\d+)us \(finding period\)\s*", part)
        if missing:
            channels.append({"channel": index, "signal": False, "width_us": None, "period_us": None})
        elif measured or finding:
            match = measured or finding
            width = int(match[1])
            period = int(match[2]) if measured else None
            if not 100 <= width <= 5000 or (period is not None and not 5000 <= period <= 100000):
                raise ValueError("Invalid measured PWM range")
            channels.append({"channel": index, "signal": True, "width_us": width, "period_us": period})
        else:
            raise ValueError("Malformed receiver channel")
    return channels


class ReceiverMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name="athena-receiver")
        self.config = None
        self.trace = deque(maxlen=240)
        self.last_received = None
        self.last_key = None
        self.channels = None
        self.error = None
        self.generation = 0
        self.serial = None

    def connect(self, host, port, token):
        address = ipaddress.ip_address(host)
        if address.version != 4 or not (address.is_private or address.is_loopback):
            raise ValueError("Use the receiver computer's local IPv4 address")
        self.disconnect()
        with self.lock:
            self.config = (f"http://{address}:{port}/measurement", token)
            self.generation += 1
            self.trace.clear()
            self.last_received = self.last_key = self.channels = self.error = None

    def connect_usb(self):
        from serial import Serial
        from serial.tools import list_ports
        matches = [p for p in list_ports.comports() if (p.vid, p.pid) == (0x1a86, 0x7523)]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one CH340 PWM receiver (1a86:7523); found {len(matches)}. Bench adapter will not be opened.")
        self.disconnect()
        device = Serial(port=None, baudrate=115200, timeout=.1)
        device.port = matches[0].device
        device.dtr = device.rts = False
        try:
            device.open()
        except Exception:
            device.close()
            raise
        with self.lock:
            self.serial = device
            self.config = (f"USB {device.port}", None)
            self.generation += 1

    def disconnect(self):
        with self.lock:
            device, self.serial = self.serial, None
            self.config = None
            self.generation += 1
            self.last_received = self.channels = None
            self.trace.clear()
        if device is not None:
            device.close()

    def snapshot(self):
        with self.lock:
            age = None if self.last_received is None else time.monotonic() - self.last_received
            fresh = self.config is not None and age is not None and age <= 2 and self.error is None
            return {"configured": self.config is not None, "fresh": fresh,
                    "source": self.config[0] if self.config else None,
                    "age_s": None if age is None else round(age, 2), "error": self.error,
                    "channels": deepcopy(self.channels) if fresh else None,
                    "trace": deepcopy(list(self.trace)) if fresh else []}

    def poll(self):
        with self.lock:
            config, generation = self.config, self.generation
            device = self.serial
        if config is None:
            return
        try:
            if device is not None:
                raw = device.readline()
                if not raw:
                    return
                try:
                    channels = parse_measurement(raw.decode("ascii", errors="replace").strip())
                except ValueError:
                    return  # Firmware banners are not measurements.
                with self.lock:
                    if generation != self.generation:
                        return
                    self.last_received = time.monotonic()
                    self.channels = channels
                    self.error = None
                    self.trace.append({"sampled_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                                       "us": [c["width_us"] for c in channels]})
                return
            request = Request(config[0], headers={"Authorization": f"Bearer {config[1]}"})
            with urlopen(request, timeout=1) as response:
                payload = json.loads(response.read(8193))
            if payload.get("protocol") != 1 or payload.get("receiver") != "WDR_PWM_RECEIVER":
                raise ValueError("Not the Athena receiver bridge")
            age = float(payload["sample_age_s"])
            if not 0 <= age <= 1.5:
                raise ValueError("Receiver serial measurement is stale")
            channels = parse_measurement(payload["line"])
            key = (payload["instance_id"], int(payload["sequence"]))
            with self.lock:
                if generation != self.generation:
                    return
                if key != self.last_key:
                    self.last_key = key
                    self.last_received = time.monotonic() - age
                    self.channels = channels
                    self.trace.append({"sampled_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                                       "us": [c["width_us"] for c in channels]})
                self.error = None
        except Exception as error:
            with self.lock:
                if generation == self.generation:
                    self.error = str(error)

    def run(self):
        while not self.stop_event.is_set():
            with self.lock:
                interval = .02 if self.serial is not None else .25
            if self.stop_event.wait(interval):
                break
            self.poll()

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(2)
        self.disconnect()
