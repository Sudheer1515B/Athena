"""Host-timed SET playback for PWM ESCs; never uses firmware STOP/START.

This is not bench-native replay: four outputs change sequentially, network
timing is not deterministic, and SET does not increment WDR replay counters.
"""
from copy import deepcopy
import threading
import time

from .bench_usb import BenchError


class MotorReplay:
    def __init__(self):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread = None
        self._state = None

    def snapshot(self):
        with self._lock:
            return deepcopy(self._state)

    @property
    def active(self):
        return bool((self.snapshot() or {}).get("active"))

    def update(self, **values):
        with self._lock:
            self._state.update(values)

    @staticmethod
    def validate(canonical, expected_sum, max_us):
        frames = canonical["frames"]
        if canonical["channel_count"] != 4 or not frames:
            raise BenchError("Motor replay requires a nonempty four-output profile")
        mapping = canonical.get("mapping", [])
        if len(mapping) != 4 or sorted(item.get("output", -1) for item in mapping) != list(range(4)) or any(not item.get("source") for item in mapping):
            raise BenchError("Map all four motor outputs; unmapped 1500-us outputs are not allowed")
        if not 1000 <= max_us <= 2000:
            raise BenchError("Motor ceiling must be 1000–2000 us")
        if any(len(frame) != 4 or any(type(value) is not int or not 1000 <= value <= max_us for value in frame) for frame in frames):
            raise BenchError(f"Profile contains motor commands outside 1000–{max_us} us; commands are rejected, never clipped")
        if sum(map(sum, frames)) % 65536 != expected_sum:
            raise BenchError("Motor profile checksum mismatch")
        if type(canonical["rate_hz"]) is not int or not 10 <= canonical["rate_hz"] <= 100:
            raise BenchError("Motor profile frame rate must be 10–100 Hz")

    def reserve(self, profile_id, total_frames):
        with self._lock:
            if self._state and self._state["active"]:
                raise BenchError("Motor commands are already being sent")
            self._cancel.clear()
            self._state = {"active": True, "phase": "PREPARING", "profile_id": profile_id,
                           "total_frames": total_frames, "acknowledged_frames": 0,
                           "elapsed_s": 0, "max_lateness_s": 0,
                           "low_signal_confirmed": False, "error": None,
                           "mode": "HOST_SET", "bench_counters_track_this_run": False}

    def launch(self, runner):
        self._thread = threading.Thread(target=runner, name="athena-motor-replay", daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancel.set()
        if self.active:
            self.update(phase="CANCELLING")

    def close(self):
        self.cancel()
        if self._thread:
            self._thread.join(20)
            if self._thread.is_alive():
                raise RuntimeError("Motor output return is unconfirmed; disconnect motor power")

    def run(self, bench, canonical, cycles, observe=lambda: None):
        started = time.monotonic()
        phase, error = "COMPLETED", None
        low_errors = []
        eligible = False
        try:
            bench.refresh()
            if int((bench.info or {}).get("ch", 0)) != 4 or (bench.status or {}).get("state") != "STOPPED":
                # A failed preflight must not alter outputs belonging to another run.
                self.update(active=False, phase="FAILED", error="Motor sending requires a stopped four-channel bench")
                return
            observe()
            eligible = True
            for channel in range(4):
                bench.command(f"SET {channel} 1000")
            frames = canonical["frames"] if canonical else []
            period = 1 / canonical["rate_hz"] if frames else 0
            self.update(phase="RUNNING" if frames else "LOWERING")
            schedule = time.monotonic()
            acknowledged, worst = 0, 0
            last_observed = schedule
            for _ in range(cycles):
                for frame in frames:
                    if self._cancel.is_set():
                        phase = "CANCELLED"
                        break
                    deadline = schedule + acknowledged * period
                    if self._cancel.wait(max(0, deadline - time.monotonic())):
                        phase = "CANCELLED"
                        break
                    lateness = max(0, time.monotonic() - deadline)
                    worst = max(worst, lateness)
                    if lateness > max(.1, 2 * period):
                        raise BenchError("Wi-Fi cannot maintain this profile's timing; lower the frame rate and recompile")
                    for channel, width in enumerate(frame):
                        if self._cancel.is_set():
                            phase = "CANCELLED"
                            break
                        bench.command(f"SET {channel} {width}")
                    if phase == "CANCELLED":
                        break
                    acknowledged += 1
                    completion_lateness = max(0, time.monotonic() - deadline - period)
                    worst = max(worst, completion_lateness)
                    self.update(acknowledged_frames=acknowledged,
                                elapsed_s=round(time.monotonic() - started, 3), max_lateness_s=round(worst, 4))
                    if completion_lateness > max(.1, 2 * period):
                        raise BenchError("Wi-Fi cannot maintain this profile's timing; lower the frame rate and recompile")
                    if time.monotonic() - last_observed >= .5:
                        bench.refresh()
                        observe()
                        last_observed = time.monotonic()
                    self.update(acknowledged_frames=acknowledged,
                                elapsed_s=round(time.monotonic() - started, 3), max_lateness_s=round(worst, 4))
                if phase == "CANCELLED":
                    break
            if frames and phase == "COMPLETED":
                if self._cancel.wait(max(0, schedule + acknowledged * period - time.monotonic())):
                    phase = "CANCELLED"
        except Exception as failure:
            phase, error = "FAILED", str(failure)
        if not eligible:
            self.update(active=False, phase="FAILED", error=error or "Preflight failed; no output commands sent")
            return
        self.update(phase="LOWERING")
        for channel in range(4):
            try:
                # Never reconnect/retry commands after a lost reply.
                if not bench.connected:
                    raise BenchError("Connection lost")
                bench.command(f"SET {channel} 1000")
            except Exception as failure:
                low_errors.append(f"OUT{channel}: {failure}")
        try:
            bench.refresh()
            observe()
            confirmed = bench.connected and (bench.status or {}).get("us") == "1000,1000,1000,1000" and not low_errors
        except Exception as failure:
            low_errors.append(str(failure))
            confirmed = False
        if not confirmed:
            phase = "FAILED"
            error = (error or "") + " Low output NOT confirmed; disconnect motor power. " + "; ".join(low_errors)
        self.update(active=False, phase=phase, error=error, low_signal_confirmed=confirmed,
                    elapsed_s=round(time.monotonic() - started, 3))
