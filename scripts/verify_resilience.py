"""Isolated integration checks against the supplied simulator, never real hardware."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import socket
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
import backend.app as module
from handout_controller_teams import wdr_tool as official


class SimulatorHarness:
    """Official SimDevice and socket client, with transport-only fault injection."""
    def __init__(self):
        self.device = official.SimDevice()
        self.device.start()
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(4)
        self.server.settimeout(.1)
        self.port = self.server.getsockname()[1]
        self.closed = threading.Event()
        self.blocked = False
        self.commands = []
        self.clients = []
        self.delay_frames_s = 0
        self.drop_reply_for = None
        self.thread = threading.Thread(target=self.accept, daemon=True)
        self.thread.start()

    def accept(self):
        while not self.closed.is_set():
            try:
                sock, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if self.blocked or not self.device.net_up.is_set():
                sock.close()
                continue
            threading.Thread(target=self.handle, args=(sock,), daemon=True).start()

    def handle(self, sock):
        client = official._SockClient(sock)
        harness = self
        class Replies(queue.Queue):
            def put(self, line, *args, **kwargs):
                if getattr(client, "drop_ack", False) and line.startswith(("OK", "ERR")):
                    client.drop_ack = False
                    harness.close_client(client)
                    return
                super().put(line, *args, **kwargs)
        client.q = Replies()
        self.clients.append(client)
        self.device.connect_client(client)
        threading.Thread(target=client.pump_out, daemon=True).start()
        for line in client.read_lines():
            self.commands.append(line)
            if line.startswith("F ") and self.delay_frames_s:
                time.sleep(self.delay_frames_s)
            if self.drop_reply_for and line.startswith(self.drop_reply_for):
                self.drop_reply_for = None
                client.drop_ack = True
            self.device.handle(line, client)
        self.device.disconnect_client(client)

    @staticmethod
    def close_client(client):
        client.closed = True
        try:
            client.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        client.sock.close()

    def drop_link(self):
        self.blocked = True
        for client in self.clients:
            self.close_client(client)

    def close(self):
        self.closed.set()
        self.drop_link()
        self.server.close()
        self.thread.join(2)
        self.device.stop()
        self.device.clock_thread.join(2)
        self.device.tel_thread.join(2)


def request(client, method, path, **kwargs):
    response = getattr(client, method)(f"/api/v1/{path}", **kwargs)
    assert response.is_success, (path, response.status_code, response.text)
    return response.json()


def wait_session(recorder, session_id, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        detail = recorder.session_detail(session_id)
        if detail["ended_at"]:
            return detail
        time.sleep(.05)
    raise AssertionError("Session did not finish/reconcile")


def verify(output):
    original_dir, original_state = module.DATA_DIR, official.STATE_FILE
    results = {}
    with tempfile.TemporaryDirectory(prefix="athena-resilience-") as directory:
        module.DATA_DIR = Path(directory) / "athena"
        official.STATE_FILE = str(Path(directory) / "sim-counters.json")
        simulator = SimulatorHarness()
        try:
            with TestClient(module.app) as client:
                request(client, "post", "bench/simulator/connect", json={"port": simulator.port})
                source = request(client, "post", "sources", files={"file": ("RCOU.csv", (ROOT / "RCOU.csv").read_bytes(), "text/csv")})
                profile = request(client, "post", "profiles", json={
                    "source_id": source["id"], "start_us": 40_000_000, "end_us": 44_000_000,
                    "rate_hz": 50, "channel_count": 4, "maxframes": 8000,
                    "mapping": [{"output": i, "source": f"C{i+1}"} for i in range(4)],
                })
                request(client, "post", f"bench/upload/{profile['id']}")
                request(client, "post", "bench/start", json={"cycles": 1})
                recorder = module.app.state.history
                session_id = recorder.sessions()[0]["id"]
                # Deliberately no snapshot/dashboard requests while the run executes.
                completed = wait_session(recorder, session_id)
                assert completed["status"] == "COMPLETED", completed
                assert completed["delta"]["cycles"] == 1, completed
                assert completed["delta"]["run_s"] == 4, completed
                results["browser_absent"] = completed
                assert len([c for c in simulator.commands if c.startswith("START ")]) == 1
                results["command_counts"] = {verb: sum(c.split()[0] == verb for c in simulator.commands)
                                             for verb in ("START", "LOAD", "COMMIT", "CLEAR")}
        finally:
            simulator.close()
            module.DATA_DIR, official.STATE_FILE = original_dir, original_state
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("PASS:", ", ".join(results), "evidence:", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "var/resilience" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    verify(parser.parse_args().output_dir)
