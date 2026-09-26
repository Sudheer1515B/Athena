from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.app as module


class FakeTcpBench:
    connects = 0

    def __init__(self, *, expected_team=None) -> None:
        self.connected = False
        self.transport = "SIMULATOR"

    def connect(self, host: str, port: int) -> None:
        type(self).connects += 1
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def refresh(self) -> dict:
        return self.snapshot()

    def snapshot(self) -> dict:
        return {
            "connection": {
                "state": "CONNECTED" if self.connected else "DISCONNECTED",
                "transport": self.transport if self.connected else None,
                "port": "127.0.0.1:3333" if self.connected else None,
                "bench": {"proto": "1", "team": "SIM", "ch": "4",
                          "maxframes": "8000", "up": "10"} if self.connected else None,
            },
            "bench_state": {"state": "RUNNING", "cycle": "0",
                            "frame": "10", "frames": "3000",
                            "us": "1600,1600,1600,1600"} if self.connected else None,
            "counters": {"cycles": "2", "run_s": "10",
                         "active_s": "10,10,10,10"} if self.connected else None,
            "profile": None,
            "recent_events": [],
            "trace": [],
        }


class ReconnectTests(unittest.TestCase):
    def test_tcp_reconnect_only_reads_status_and_explicit_disconnect_stops_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_data_dir = module.DATA_DIR
            module.DATA_DIR = Path(directory)
            FakeTcpBench.connects = 0
            try:
                with TestClient(module.app) as client, patch.object(module, "TcpBench", FakeTcpBench):
                    module.app.state.desired_tcp = ("127.0.0.1", 3333, "SIM")
                    module.app.state.monitor.tick()
                    response = client.get("/api/v1/snapshot")
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["connection"]["state"], "CONNECTED")
                    self.assertEqual(response.json()["bench_state"]["state"], "RUNNING")
                    self.assertEqual(FakeTcpBench.connects, 1)
                    self.assertEqual(client.post("/api/v1/bench/disconnect").status_code, 200)
                    self.assertEqual(client.get("/api/v1/snapshot").json()["connection"]["state"],
                                     "DISCONNECTED")
                    self.assertEqual(FakeTcpBench.connects, 1)
            finally:
                module.DATA_DIR = old_data_dir


if __name__ == "__main__":
    unittest.main()
