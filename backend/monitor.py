"""Backend-owned bench observations; browser requests never drive the clock."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import threading
import time

from .bench_usb import BenchError


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
                except (BenchError, OSError, ValueError) as error:
                    self.last_error = str(error)
                    bench.disconnect()
                    self.state.reconnect_after = time.monotonic() + 3
            desired = self.state.desired_tcp
            if desired is not None and not self.state.bench.connected and time.monotonic() >= self.state.reconnect_after:
                host, port, expected_team = desired
                replacement = self.tcp_factory(expected_team=expected_team)
                try:
                    replacement.connect(host, port)
                    if self._stop.is_set():
                        replacement.disconnect()
                    else:
                        self.state.bench = replacement
                        self.state.reconnect_after = 0
                except (BenchError, OSError, ValueError) as error:
                    replacement.disconnect()
                    self.last_error = str(error)
                    self.state.reconnect_after = time.monotonic() + 3
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
