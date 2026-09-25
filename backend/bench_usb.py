"""Small WDR v1 USB controller for the time-boxed bench prototype."""

from __future__ import annotations

import re
import threading
import time
from collections import deque


class BenchError(Exception):
    pass


def fields(line: str) -> dict[str, str]:
    return dict(re.findall(r"([a-z_]+)=([^ ]+)", line))


class UsbBench:
    def __init__(self) -> None:
        self._serial = None
        self._lock = threading.RLock()
        self.port: str | None = None
        self.info: dict[str, str] | None = None
        self.status: dict[str, str] | None = None
        self.counters: dict[str, str] | None = None
        self.profile_id: str | None = None
        self.events: deque[str] = deque(maxlen=30)

    @property
    def connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self, port: str) -> None:
        import serial

        with self._lock:
            self.disconnect()
            device = serial.Serial()
            device.port = port
            device.baudrate = 115200
            device.bytesize = 8
            device.parity = "N"
            device.stopbits = 1
            device.timeout = 0.05
            # ESP32 boards often wire these lines to reset and boot mode.
            device.dtr = False
            device.rts = False
            try:
                device.open()
                self._serial = device
                self.port = port
                for _ in range(3):
                    try:
                        self.command("PING")
                        break
                    except BenchError:
                        time.sleep(0.2)
                else:
                    raise BenchError("The USB port opened but the bench did not answer PING")
                self.refresh()
            except Exception:
                self.disconnect()
                raise

    def disconnect(self) -> None:
        with self._lock:
            if self._serial is not None:
                self._serial.close()
            self._serial = None
            self.port = None
            self.info = None
            self.status = None
            self.counters = None
            self.profile_id = None

    def _line(self, deadline: float) -> str | None:
        if self._serial is None:
            raise BenchError("USB bench is disconnected")
        buffer = bytearray()
        while time.monotonic() < deadline:
            byte = self._serial.read(1)
            if not byte:
                continue
            if byte == b"\n":
                raw = buffer.decode("ascii", errors="replace").replace("\r", "")
                # Some USB adapters put boot noise ahead of a valid reply.
                match = re.search(r"(?:^|[^A-Z])(OK(?: |$)|ERR(?: |$))", raw)
                if match:
                    return raw[match.start(1):]
                return raw.strip()
            if len(buffer) < 4096:
                buffer.extend(byte)
        return None

    def command(self, value: str) -> str:
        with self._lock:
            if self._serial is None:
                raise BenchError("USB bench is disconnected")
            try:
                self._serial.write((value + "\n").encode("ascii"))
                self._serial.flush()
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    line = self._line(deadline)
                    if line is None:
                        break
                    if line.startswith("EVT "):
                        self.events.appendleft(line)
                    elif line.startswith("TEL "):
                        continue
                    elif line.startswith("OK"):
                        return line
                    elif line.startswith("ERR"):
                        raise BenchError(f"{value.split()[0]}: {line}")
                raise BenchError(f"No reply to {value.split()[0]} within 2 seconds")
            except (OSError, UnicodeError) as error:
                self.disconnect()
                raise BenchError(f"USB connection failed: {error}") from error

    def refresh(self) -> dict:
        with self._lock:
            if not self.connected:
                return self.snapshot()
            try:
                info = fields(self.command("INFO"))
                status = fields(self.command("STATUS"))
                counters = fields(self.command("COUNTERS"))
            except BenchError:
                self.info = self.status = self.counters = None
                raise
            self.info, self.status, self.counters = info, status, counters
            return self.snapshot()

    def upload(self, profile_id: str, canonical: dict, expected_sum: int) -> dict:
        with self._lock:
            self.refresh()
            channel_count = int(self.info["ch"])
            frames = canonical["frames"]
            rate = int(canonical["rate_hz"])
            if canonical["channel_count"] != channel_count:
                raise BenchError(f"Profile has {canonical['channel_count']} channels; bench has {channel_count}")
            if not frames or len(frames) > int(self.info["maxframes"]):
                raise BenchError("Profile exceeds the bench frame capacity")
            if any(len(frame) != channel_count or any(not 500 <= int(us) <= 2500 for us in frame)
                   for frame in frames):
                raise BenchError("Profile has invalid frame widths")
            if sum(sum(frame) for frame in frames) % 65536 != expected_sum:
                raise BenchError("Stored profile checksum does not match its frames")
            self.command("STOP")
            # LOAD destroys the prior committed profile. Do not claim that a
            # profile is ready until every frame and COMMIT are acknowledged.
            self.profile_id = None
            self.command(f"LOAD {rate} {len(frames)}")
            for index, frame in enumerate(frames):
                self.command(f"F {index} {' '.join(map(str, frame))}")
            reply = self.command("COMMIT")
            if reply != f"OK SUM={expected_sum}":
                raise BenchError(f"Bench checksum mismatch: {reply}")
            self.profile_id = profile_id
            return self.refresh()

    def control(self, action: str, cycles: int = 1) -> dict:
        with self._lock:
            if action == "start":
                if self.profile_id is None:
                    raise BenchError("Upload a profile in this session before starting")
                if not 1 <= cycles <= 100000:
                    raise BenchError("Enter a finite cycle target between 1 and 100000")
                command = f"START {cycles}"
            elif action in {"pause", "resume", "stop"}:
                command = action.upper()
            else:
                raise BenchError("Unsupported bench control")
            self.command(command)
            return self.refresh()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "connection": {"state": "CONNECTED" if self.connected else "DISCONNECTED",
                               "transport": "USB" if self.connected else None,
                               "port": self.port, "bench": self.info},
                "bench_state": self.status,
                "counters": self.counters,
                "profile": {"id": self.profile_id} if self.profile_id else None,
                "recent_events": list(self.events),
            }
