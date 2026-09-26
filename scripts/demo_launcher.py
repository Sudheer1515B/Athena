"""Launch the local Athena demo from a macOS .command file.

This starts only local software and, in hardware mode, reads the independent
receiver's serial output. Bench connection, upload and replay remain UI actions.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from serial.tools import list_ports


ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "bin" / "python"
WEB_INDEX = ROOT / "athena" / "build" / "web" / "index.html"
DEMO_DIR = ROOT / "var" / "demo"
URL = "http://127.0.0.1:8080"
RECEIVER_USB_ID = (0x1A86, 0x7523)


def require_free_port(port: int) -> None:
    with socket.socket() as check:
        try:
            check.bind(("127.0.0.1", port))
        except PermissionError as error:
            raise RuntimeError(
                f"This environment does not allow a local port check on {port}."
            ) from error
        except OSError as error:
            raise RuntimeError(
                f"Port {port} is already in use. Close the existing demo/server first."
            ) from error


def find_receiver() -> str:
    matches = [
        port.device
        for port in list_ports.comports()
        if (port.vid, port.pid) == RECEIVER_USB_ID
    ]
    if len(matches) != 1:
        raise RuntimeError(
            "Expected one CH340 PWM receiver (USB 1a86:7523); found "
            f"{len(matches)}. Connect the receiver ESP32 to this Mac."
        )
    return matches[0]


def preflight(mode: str) -> str | None:
    if not PYTHON.is_file():
        raise RuntimeError("Missing .venv/bin/python; see PROTOTYPE_DEMO.md.")
    if not WEB_INDEX.is_file():
        raise RuntimeError(
            "Flutter web build missing. Run 'cd athena && flutter build web' once."
        )
    require_free_port(8080)
    if mode == "simulator":
        require_free_port(3333)
        require_free_port(3334)
        return None
    return find_receiver()


def wait_for(name: str, process: subprocess.Popen[bytes], probe) -> None:
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited early; check its log in {DEMO_DIR}.")
        try:
            probe()
            return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise RuntimeError(f"{name} did not become ready; check its log in {DEMO_DIR}.")


def probe_simulator() -> None:
    with socket.create_connection(("127.0.0.1", 3333), timeout=0.5):
        pass


def probe_backend() -> None:
    with urllib.request.urlopen(f"{URL}/api/v1/health", timeout=0.5) as response:
        if response.status != 200:
            raise OSError(f"Athena health returned {response.status}")


def connect_simulator() -> None:
    request = urllib.request.Request(
        f"{URL}/api/v1/bench/simulator/connect",
        data=b'{"port":3333}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        snapshot = json.load(response)
    connection = snapshot.get("connection", {})
    if connection.get("state") != "CONNECTED" or \
            (connection.get("bench") or {}).get("team") != "SIM":
        raise RuntimeError("Athena did not confirm the supplied simulator identity")


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=4)


def launch(mode: str, receiver: str | None, *, smoke: bool) -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    processes: list[subprocess.Popen[bytes]] = []
    log_files = []
    try:
        if mode == "simulator":
            sim_dir = ROOT / "var" / "sim-tmp"
            sim_dir.mkdir(parents=True, exist_ok=True)
            sim_log = DEMO_DIR / f"simulator-{stamp}.log"
            sim_output = sim_log.open("wb")
            log_files.append(sim_output)
            sim_env = os.environ.copy()
            sim_env["TMPDIR"] = str(sim_dir)
            simulator = subprocess.Popen(
                [
                    str(PYTHON), "-u", "handout_controller_teams/wdr_tool.py",
                    "serve-sim", "--listen", "3333", "--usb-port", "3334",
                ],
                cwd=ROOT,
                env=sim_env,
                stdout=sim_output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            processes.append(simulator)
            wait_for("Simulator", simulator, probe_simulator)
            print(f"Simulator ready; log: {sim_log}", flush=True)

        backend_log = DEMO_DIR / f"backend-{stamp}.log"
        backend_output = backend_log.open("wb")
        log_files.append(backend_output)
        backend = subprocess.Popen(
            [
                str(PYTHON), "-m", "uvicorn", "backend.app:app",
                "--host", "127.0.0.1", "--port", "8080",
            ],
            cwd=ROOT,
            stdout=backend_output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes.append(backend)
        wait_for("Athena backend", backend, probe_backend)
        print(f"Athena ready; log: {backend_log}", flush=True)
        if mode == "simulator":
            connect_simulator()
            print("Athena connected to the supplied simulator (team=SIM).", flush=True)

        if smoke:
            print("Smoke check passed. Closing demo services.", flush=True)
            return

        subprocess.run(["open", URL], check=False)
        print(f"Opened {URL}", flush=True)
        if mode == "simulator":
            print(
                "In Athena: Profile → import/compile/upload; "
                "Dashboard → Start. The simulator is already connected."
            )
            input("Press Enter here to stop Athena and the simulator...\n")
        else:
            assert receiver is not None
            print(
                "In Athena: Settings → Connect Wi-Fi bench using its current IP; "
                "then upload and Start a finite profile."
            )
            print(
                "Only the receiver USB port is being opened. The WDR bench may "
                "use a separate USB power supply; its USB serial port is untouched."
            )
            print(f"Receiver: {receiver} at 115200 baud. Press Ctrl-C to stop.\n")
            request = urllib.request.Request(URL + "/api/v1/receiver/usb/connect", data=b"", method="POST")
            with urllib.request.urlopen(request, timeout=5) as response:
                json.load(response)
            # Athena owns serial; a second reader would steal lines from its graph.
            last_sample = None
            while True:
                with urllib.request.urlopen(URL + "/api/v1/snapshot", timeout=5) as response:
                    feedback = json.load(response)["receiver"]
                trace = feedback.get("trace") or []
                if feedback["fresh"] and trace and trace[-1]["sampled_at"] != last_sample:
                    last_sample = trace[-1]["sampled_at"]
                    print(" | ".join(f"OUT{c['channel']} {c['width_us']}us/{c['period_us']}us" if c["signal"] else f"OUT{c['channel']} NO SIGNAL" for c in feedback["channels"]), flush=True)
                elif not feedback["fresh"]:
                    print("Receiver readings unavailable/stale", flush=True)
                time.sleep(.25)
    finally:
        for process in reversed(processes):
            stop(process)
        for output in log_files:
            output.close()
        if processes:
            print("Demo services stopped.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("simulator", "hardware"))
    parser.add_argument("--check", action="store_true", help="Validate setup without launching")
    parser.add_argument("--smoke", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        receiver = preflight(args.mode)
        print(f"{args.mode.capitalize()} demo preflight passed.", flush=True)
        if receiver:
            print(f"Receiver identified: {receiver} (CH340).", flush=True)
        if not args.check:
            launch(args.mode, receiver, smoke=args.smoke)
        return 0
    except KeyboardInterrupt:
        print("\nStopping demo...", flush=True)
        return 0
    except (OSError, RuntimeError) as error:
        print(f"Demo could not start: {error}", file=sys.stderr, flush=True)
        return 1


def interrupt(_signum, _frame) -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGHUP, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    raise SystemExit(main())
