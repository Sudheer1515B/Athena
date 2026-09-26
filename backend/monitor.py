"""Backend-owned bench observations; browser requests never drive the clock."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import threading
import time
import random

from .bench_usb import BenchError


class IdentityMismatch(BenchError):
    pass


class BenchMonitor:
    def __init__(self, state, tcp_factory, *, interval_s: float = 1.0) -> None:
        self.state = state
        self.tcp_factory = tcp_factory
        self.interval_s = interval_s
        self.api_database = state.database
        self.io_lock = threading.RLock()
        self._local = threading.local()
        self._cache_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="athena-bench-monitor", daemon=True)
        self._live = state.bench.snapshot()
        self._last_seen_at = None
        self._last_seen_mono = None
        self.last_error = None
        self.last_known = None
        self.retry_attempts = 0
        self.expected_capabilities = None
        self.blocked_reason = None
        self.recovery_warning = None

    def reset_identity(self) -> None:
        self.expected_capabilities = None
        self.blocked_reason = None
        self.recovery_warning = None
        self.retry_attempts = 0
        self.state.reconnect_after = 0

    def pin_identity(self) -> None:
        info = self.state.bench.snapshot().get("connection", {}).get("bench") or {}
        self.expected_capabilities = {key: info.get(key) for key in ("proto", "team", "ch", "maxframes")}
        if self.state.desired_tcp is not None:
            host, port, _ = self.state.desired_tcp
            self.state.desired_tcp = (host, port, info.get("team"))
        self.last_known = None
        self._last_seen_at = self._last_seen_mono = None
        self.blocked_reason = self.recovery_warning = None

    def validate_identity(self, live) -> None:
        info = live.get("connection", {}).get("bench") or {}
        observed = {key: info.get(key) for key in ("proto", "team", "ch", "maxframes")}
        if self.expected_capabilities is not None and observed != self.expected_capabilities:
            raise IdentityMismatch(f"Bench identity/capabilities changed: expected {self.expected_capabilities}, observed {observed}. Review and explicitly reconnect.")

    def observed_reboot(self, live) -> bool:
        if self.last_known is None:
            return False
        try:
            before = int(self.last_known["connection"]["bench"]["up"])
            after = int(live["connection"]["bench"]["up"])
            return after < before
        except (KeyError, TypeError, ValueError):
            return False

    def schedule_retry(self) -> None:
        delay = min(10, 2 ** min(self.retry_attempts, 4) * random.uniform(.9, 1.1))
        self.retry_attempts += 1
        self.state.reconnect_after = time.monotonic() + delay

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            raise RuntimeError("Bench monitor did not shut down within its timeout")

    @contextmanager
    def operation(self):
        if not self.io_lock.acquire(blocking=False):
            raise BenchError("Bench is busy with another operation; wait for it to finish")
        try:
            self._local.active = True
            try:
                yield
            finally:
                self.capture()
                self._local.active = False
        finally:
            self.io_lock.release()

    def capture(self) -> dict:
        live = self.state.bench.snapshot()
        connected = live.get("connection", {}).get("state") == "CONNECTED"
        self.state.history.observe(live)
        with self._cache_lock:
            self._live = deepcopy(live)
            if connected:
                trace = live.get("trace") or []
                sampled_at = trace[-1]["sampled_at"] if trace else datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                if sampled_at != self._last_seen_at:
                    self._last_seen_at = sampled_at
                    self._last_seen_mono = time.monotonic()
                self.last_known = deepcopy(live)
                self.last_error = None
                self.retry_attempts = 0
        return live

    def snapshot(self) -> dict:
        if getattr(self._local, "active", False):
            self.capture()
        with self._cache_lock:
            live = deepcopy(self._live)
            age = None if self._last_seen_mono is None else max(0, time.monotonic() - self._last_seen_mono)
            live["observation"] = {
                "last_seen_at": self._last_seen_at,
                "age_s": None if age is None else round(age, 3),
                "fresh": live.get("connection", {}).get("state") == "CONNECTED" and age is not None and age <= 3,
                "last_error": self.last_error,
                "retry_attempts": self.retry_attempts,
                "retry_in_s": round(max(0, self.state.reconnect_after - time.monotonic()), 1) if self.state.desired_tcp is not None else None,
                "blocked_reason": self.blocked_reason,
                "recovery_warning": self.recovery_warning,
            }
            live["last_known"] = deepcopy(self.last_known) if not live["observation"]["fresh"] else None
        return live

    def tick(self) -> None:
        if self._stop.is_set() or not self.io_lock.acquire(blocking=False):
            return
        try:
            bench = self.state.bench
            if bench.connected:
                try:
                    bench.refresh()
                    self.validate_identity(bench.snapshot())
                    if self.observed_reboot(bench.snapshot()):
                        live = bench.snapshot()
                        live["reboot_detected"] = True
                        self.state.history.observe(live, action="bench_reboot_observed")
                        self.recovery_warning = "Bench reboot observed. Profile identity and the exact stop time are unknown; verify a new upload before Start."
                except IdentityMismatch as error:
                    self.blocked_reason = self.last_error = str(error)
                    self.state.history.notice("identity_mismatch", {"reason": str(error)})
                    bench.disconnect()
                except (BenchError, OSError, ValueError) as error:
                    self.last_error = str(error)
                    bench.disconnect()
                    self.schedule_retry()
            desired = self.state.desired_tcp
            if desired is not None and not self.blocked_reason and not self.state.bench.connected and time.monotonic() >= self.state.reconnect_after:
                host, port, expected_team = desired
                replacement = self.tcp_factory(expected_team=expected_team)
                try:
                    replacement.connect(host, port)
                    recovered = replacement.snapshot()
                    self.validate_identity(recovered)
                    if self._stop.is_set():
                        replacement.disconnect()
                    else:
                        self.state.bench = replacement
                        self.state.reconnect_after = 0
                        if self.observed_reboot(recovered):
                            recovered["reboot_detected"] = True
                            self.state.history.observe(recovered, action="bench_reboot_observed")
                            self.recovery_warning = "Bench reboot observed. Profile identity and the exact stop time are unknown; verify a new upload before Start."
                except IdentityMismatch as error:
                    replacement.disconnect()
                    self.blocked_reason = self.last_error = str(error)
                    self.state.history.notice("identity_mismatch", {"reason": str(error)})
                except (BenchError, OSError, ValueError) as error:
                    replacement.disconnect()
                    self.last_error = str(error)
                    self.schedule_retry()
            self.capture()
        finally:
            self.io_lock.release()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                self.tick()
            except Exception as error:
                # An observation error must not silently kill monitoring.
                self.last_error = f"Observation failed: {error}"
