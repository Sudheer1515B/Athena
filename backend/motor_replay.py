"""Host-timed SET playback for PWM ESCs; never uses firmware STOP/START.

This is not bench-native replay: four outputs change sequentially, network
timing is not deterministic, and SET does not increment WDR replay counters.
"""
from copy import deepcopy
from datetime import datetime, timezone
import threading
import time
from uuid import uuid4

from .bench_usb import BenchError
from .motor_journal import MotorJournal


class MotorReplay:
    def __init__(self, checkpoint_path=None):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread = None
        self._state = None
        self._recovery = None
        self._shutdown = False
        self.journal = MotorJournal(checkpoint_path) if checkpoint_path else None
        saved = self.journal.load() if self.journal else None
        if saved:
            self._state, self._recovery = saved.get("state"), saved.get("recovery")
            if self._state and (self._state.get("active") or
                    not self._recovery and self._state.get("profile_id") and self._state.get("phase") in {"FAILED", "INTERRUPTED"}):
                self._state.update(active=False, phase="INTERRUPTED", low_signal_confirmed=False,
                    error="Backend restarted during motor commands. Output and partial-frame delivery are uncertain.")
                if self._state.get("profile_id"):
                    self._recovery = deepcopy(self._state)
                self._persist()

    def _persist(self):
        if self.journal:
            self.journal.save(self._state, self._recovery)

    def snapshot(self):
        with self._lock:
            if self._state is None:
                return None
            return {**deepcopy(self._state), "recovery": deepcopy(self._recovery)}

    def recovery(self):
        with self._lock:
            return deepcopy(self._recovery)

    @property
    def active(self):
        return bool((self.snapshot() or {}).get("active"))

    def update(self, **values):
        with self._lock:
            self._state.update(values)
            try:
                self._persist()
            except OSError as error:
                self._state["checkpoint_error"] = str(error)
                if values.get("phase") != "LOWERING":
                    raise

    def finish(self, **values):
        with self._lock:
            self._state.update(active=False, **values)
            self._state["partial_frame_uncertain"] = self._state.get("partial_frame_uncertain", False) or self._state.get("in_flight_frame") is not None
            if self._state.get("profile_id") and (self._state["phase"] in {"FAILED", "INTERRUPTED"} or self._shutdown):
                self._recovery = deepcopy(self._state)
            try:
                self._persist()
            except OSError as error:
                self._state["checkpoint_error"] = str(error)

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

    def reserve(self, profile_id, total_frames, *, frames_per_pass=None, rate_hz=None, requested_passes=None,
                context=None, resume=None):
        with self._lock:
            if self._state and self._state["active"]:
                raise BenchError("Motor commands are already being sent")
            self._cancel.clear()
            self._shutdown = False
            if profile_id:
                self._recovery = None
            self._state = {"active": True, "phase": "PREPARING", "profile_id": profile_id,
                           "total_frames": total_frames, "acknowledged_frames": 0,
                           "elapsed_s": 0, "max_lateness_s": 0,
                           "low_signal_confirmed": False, "error": None,
                           "mode": "HOST_SET", "bench_counters_track_this_run": False}
            self._state.update(frames_per_pass=frames_per_pass, rate_hz=rate_hz,
                               requested_passes=requested_passes,
                               started_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                               ended_at=None, last_low_readback_at=None)
            self._state.update(run_id=str(uuid4()), context=context,
                               in_flight_frame=None, partial_frame_uncertain=False)
            if resume:
                self._state.update(run_id=resume["run_id"], acknowledged_frames=resume["acknowledged_frames"],
                    started_at=resume["started_at"], elapsed_s=resume.get("elapsed_s", 0),
                    context=resume["context"], partial_frame_uncertain=resume.get("in_flight_frame") is not None,
                    resumed_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
            self._persist()

    def launch(self, runner):
        self._thread = threading.Thread(target=runner, name="athena-motor-replay", daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancel.set()
        if self.active:
            self.update(phase="CANCELLING")

    def close(self):
        self._shutdown = True
        self.cancel()
        if self._thread:
            self._thread.join(20)
            if self._thread.is_alive():
                raise RuntimeError("Motor output return is unconfirmed; disconnect motor power")

    def run(self, bench, canonical, cycles, observe=lambda: None, *, start_frame=0):
        started = time.monotonic()
        base_elapsed = (self.snapshot() or {}).get("elapsed_s", 0)
        phase, error = "COMPLETED", None
        low_errors = []
        eligible = False
        try:
            bench.refresh()
            if int((bench.info or {}).get("ch", 0)) != 4 or (bench.status or {}).get("state") != "STOPPED":
                # A failed preflight must not alter outputs belonging to another run.
                self.finish(phase="FAILED", error="Motor sending requires a stopped four-channel bench",
                            ended_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
                return
            observe()
            eligible = True
            for channel in range(4):
                bench.command(f"SET {channel} 1000")
            frames = canonical["frames"] if canonical else []
            period = 1 / canonical["rate_hz"] if frames else 0
            self.update(phase="RUNNING" if frames else "LOWERING")
            schedule = time.monotonic()
            acknowledged, worst = start_frame, 0
            last_observed = schedule
            previous_up = int((bench.info or {}).get("up", "0"))
            for absolute_frame in range(start_frame, len(frames) * cycles):
                frame = frames[absolute_frame % len(frames)]
                if self._cancel.is_set():
                    phase = "CANCELLED"
                    break
                deadline = schedule + (acknowledged - start_frame) * period
                if self._cancel.wait(max(0, deadline - time.monotonic())):
                    phase = "CANCELLED"
                    break
                lateness = max(0, time.monotonic() - deadline)
                worst = max(worst, lateness)
                if lateness > max(.1, 2 * period):
                    raise BenchError("Wi-Fi cannot maintain this profile's timing; lower the frame rate and recompile")
                self.update(in_flight_frame=absolute_frame)
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
                self.update(acknowledged_frames=acknowledged, in_flight_frame=None,
                            elapsed_s=round(base_elapsed + time.monotonic() - started, 3), max_lateness_s=round(worst, 4))
                if completion_lateness > max(.1, 2 * period):
                    raise BenchError("Wi-Fi cannot maintain this profile's timing; lower the frame rate and recompile")
                if time.monotonic() - last_observed >= .5:
                    bench.refresh()
                    current_up = int((bench.info or {}).get("up", "0"))
                    if current_up < previous_up:
                        raise BenchError("Bench reboot detected during motor replay")
                    previous_up = current_up
                    observe()
                    last_observed = time.monotonic()
            if frames and phase == "COMPLETED":
                if self._cancel.wait(max(0, schedule + (acknowledged - start_frame) * period - time.monotonic())):
                    phase = "CANCELLED"
        except Exception as failure:
            phase, error = "FAILED", str(failure)
        if not eligible:
            self.finish(phase="FAILED", error=error or "Preflight failed; no output commands sent",
                        ended_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
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
        self.finish(phase=phase, error=error, low_signal_confirmed=confirmed,
                    elapsed_s=round(base_elapsed + time.monotonic() - started, 3),
                    ended_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    last_low_readback_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds") if confirmed else None)
