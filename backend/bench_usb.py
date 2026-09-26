"""Small WDR v1 USB and local TCP controllers for the bench prototype."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import socket
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
        self.trace: deque[dict] = deque(maxlen=180)
        self.transport = "USB"
        self.time_synced_at: str | None = None
        self.verified_frame_count: int | None = None
        self.last_control: dict | None = None
        self._progress_lock = threading.Lock()
        self._upload_progress: dict | None = None
        self._upload_started = None

    def upload_progress(self) -> dict | None:
        # Intentionally independent of the transport lock held by upload().
        with self._progress_lock:
            if self._upload_progress is None:
                return None
            progress = dict(self._upload_progress)
            elapsed = progress.get("elapsed_s", time.monotonic() - self._upload_started)
            progress["elapsed_s"] = round(elapsed, 2)
            acknowledged = progress["acknowledged_frames"]
            progress["estimated_transfer_remaining_s"] = (
                round(elapsed / acknowledged * (progress["total_frames"] - acknowledged), 1)
                if progress["phase"] == "SENDING" and acknowledged >= 10 and elapsed > 0 else None
            )
            return progress

    def _progress(self, **fields) -> None:
        with self._progress_lock:
            self._upload_progress.update(fields)

    def _validate_info(self) -> None:
        info = self.info or {}
        if info.get("proto") != "1":
            raise BenchError("Bench does not report WDR protocol version 1")
        try:
            channels = int(info["ch"])
            maxframes = int(info["maxframes"])
        except (KeyError, ValueError) as error:
            raise BenchError("Bench INFO is missing valid channel or frame capacity") from error
        if not 1 <= channels <= 16 or maxframes < 1:
            raise BenchError("Bench reports unsupported channel or frame capacity")

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
                self._validate_info()
                self.sync_time()
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
            self.verified_frame_count = None
            self.trace.clear()
            self.time_synced_at = None

    def _line(self, deadline: float) -> str | None:
        if self._serial is None:
            raise BenchError("Bench is disconnected")
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
                raise BenchError("Bench is disconnected")
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
                self.disconnect()
                raise BenchError(f"No reply to {value.split()[0]} within 2 seconds")
            except (OSError, UnicodeError) as error:
                self.disconnect()
                raise BenchError(f"Bench connection failed: {error}") from error

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
            previous_info = self.info or {}
            if previous_info and (any(info.get(key) != previous_info.get(key) for key in ("proto", "team", "ch", "maxframes"))
                                  or int(info.get("up", "0")) < int(previous_info.get("up", "0"))):
                self.profile_id = None
            if self.verified_frame_count is not None and int(status.get("frames", "0")) != self.verified_frame_count:
                self.profile_id = None
            self.info, self.status, self.counters = info, status, counters
            try:
                widths = [int(value) for value in status["us"].split(",")]
                if len(widths) == int(info["ch"]):
                    self.trace.append({
                        "sampled_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                        "state": status.get("state"),
                        "cycle": int(status.get("cycle", "0")),
                        "frame": int(status.get("frame", "0")),
                        "us": widths,
                    })
            except (KeyError, ValueError):
                pass
            return self.snapshot()

    def upload(self, profile_id: str, canonical: dict, expected_sum: int) -> dict:
        with self._progress_lock:
            self._upload_started = time.monotonic()
            self._upload_progress = {"kind": "upload", "phase": "PREPARING", "acknowledged_frames": 0,
                                     "total_frames": len(canonical["frames"]), "checksum_confirmed": False}
        try:
            result = self._upload(profile_id, canonical, expected_sum)
            self._progress(phase="COMPLETED", elapsed_s=time.monotonic() - self._upload_started)
            return result
        except Exception as error:
            self._progress(phase="FAILED", error=str(error), elapsed_s=time.monotonic() - self._upload_started)
            raise

    def _upload(self, profile_id: str, canonical: dict, expected_sum: int) -> dict:
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
            self.trace.clear()
            self.command(f"LOAD {rate} {len(frames)}")
            self._progress(phase="SENDING")
            for index, frame in enumerate(frames):
                self.command(f"F {index} {' '.join(map(str, frame))}")
                self._progress(acknowledged_frames=index + 1)
            self._progress(phase="VERIFYING")
            reply = self.command("COMMIT")
            if reply != f"OK SUM={expected_sum}":
                raise BenchError(f"Bench checksum mismatch: {reply}")
            self.profile_id = profile_id
            self._progress(checksum_confirmed=True)
            self.verified_frame_count = len(frames)
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
            self.last_control = {"action": action, "acknowledged": False, "rejected": False}
            try:
                self.command(command)
            except BenchError as error:
                self.last_control["rejected"] = f"{command.split()[0]}: ERR" in str(error)
                raise
            self.last_control["acknowledged"] = True
            if action == "start":
                self.trace.clear()
            return self.refresh()

    def set_pulse(self, channel: int, width_us: int) -> dict:
        with self._lock:
            self.refresh()
            if (self.status or {}).get("state") != "STOPPED":
                raise BenchError("Manual pulse setting requires a stopped bench")
            if not 0 <= channel < int(self.info["ch"]):
                raise BenchError("Channel is outside the bench output range")
            if not 500 <= width_us <= 2500:
                raise BenchError("Pulse width must be 500–2500 µs")
            self.command(f"SET {channel} {width_us}")
            return self.refresh()

    def sync_time(self) -> dict:
        with self._lock:
            self.command(f"TIME {int(time.time())}")
            self.time_synced_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return self.snapshot()

    def clear_simulator_counters(self) -> dict:
        with self._lock:
            if not self.simulator_reset_allowed:
                raise BenchError("Counter reset is disabled on physical benches")
            self.refresh()
            if (self.info or {}).get("team") != "SIM":
                raise BenchError("Counter reset requires the supplied simulator")
            if (self.status or {}).get("state") != "STOPPED":
                raise BenchError("Counter reset requires a stopped simulator")
            self.command("CLEAR")
            return self.refresh()

    @property
    def simulator_reset_allowed(self) -> bool:
        return (isinstance(self, TcpBench)
                and self.expected_team == "SIM"
                and self.port is not None
                and self.port.startswith("127.0.0.1:"))

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "connection": {"state": "CONNECTED" if self.connected else "DISCONNECTED",
                               "transport": self.transport if self.connected else None,
                               "port": self.port, "bench": self.info},
                "bench_state": self.status,
                "counters": self.counters,
                "profile": {"id": self.profile_id} if self.profile_id else None,
                "recent_events": list(self.events),
                "trace": list(self.trace),
                "time_sync": {"status": "ACKNOWLEDGED", "at": self.time_synced_at}
                    if self.time_synced_at else None,
                "simulator_reset_allowed": self.simulator_reset_allowed,
            }


class SocketStream:
    """The same byte-stream operations used by UsbBench, backed by TCP."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.is_open = True

    def write(self, data: bytes) -> int:
        self.sock.sendall(data)
        return len(data)

    def flush(self) -> None:
        pass

    def read(self, amount: int) -> bytes:
        try:
            data = self.sock.recv(amount)
        except socket.timeout:
            return b""
        if not data:
            raise OSError("Bench TCP connection closed")
        return data

    def close(self) -> None:
        self.is_open = False
        self.sock.close()


class TcpBench(UsbBench):
    """WDR simulator or Wi-Fi bench over TCP, reusing the command scheduler."""

    def __init__(self, *, expected_team: str | None = "SIM") -> None:
        super().__init__()
        self.expected_team = expected_team
        self.transport = "SIMULATOR" if expected_team == "SIM" else "WIFI"

    def connect(self, host: str = "127.0.0.1", port: int = 3333) -> None:
        with self._lock:
            self.disconnect()
            sock = socket.create_connection((host, port), timeout=3.0)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(0.05)
            self._serial = SocketStream(sock)
            self.port = f"{host}:{port}"
            try:
                self.command("PING")
                self.refresh()
                self._validate_info()
                if self.expected_team is not None and (self.info or {}).get("team") != self.expected_team:
                    raise BenchError(f"Connected TCP service is not the expected {self.expected_team} bench")
                if (self.info or {}).get("team") == "SIM":
                    self.transport = "SIMULATOR"
                self.sync_time()
            except Exception:
                self.disconnect()
                raise
