"""Exercise motor SET playback against supplied simulator only, with no hardware."""
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
import backend.app as module
from scripts.verify_resilience import SimulatorHarness, request, official


def finished(client):
    until = time.monotonic() + 15
    while time.monotonic() < until:
        result = request(client, "get", "snapshot")["motor_replay"]
        if result and not result["active"]:
            return result
        time.sleep(.02)
    raise AssertionError("Motor playback did not finish")


def main():
    original_dir, original_file = module.DATA_DIR, official.STATE_FILE
    results = {}
    with tempfile.TemporaryDirectory(prefix="athena-motor-sim-") as directory:
        module.DATA_DIR = Path(directory) / "athena"
        official.STATE_FILE = str(Path(directory) / "sim-counters.json")
        simulator = SimulatorHarness()
        try:
            with TestClient(module.app) as client:
                request(client, "post", "bench/simulator/connect", json={"port": simulator.port})
                csv = "TimeUS,C1,C2,C3,C4\n" + "".join(f"{i*20000},{1020+i%5*10},1040,1060,1080\n" for i in range(201))
                source = request(client, "post", "sources", files={"file": ("motor-test.csv", csv.encode(), "text/csv")})
                profile = request(client, "post", "profiles", json={"source_id": source["id"], "start_us": 0, "end_us": 1_000_000,
                    "rate_hz": 50, "channel_count": 4, "maxframes": 8000,
                    "mapping": [{"output": i, "source": f"C{i+1}", "min_us": 1000, "max_us": 2000} for i in range(4)]})
                baseline = request(client, "get", "snapshot")["counters"]
                before = len(simulator.commands)
                assert client.post("/api/v1/motors/start", json={"profile_id": profile["id"]}).status_code == 422
                assert client.post("/api/v1/motors/start", json={"profile_id": profile["id"], "max_us": 1050, "safety_confirmed": True}).status_code == 409
                assert not any(c.startswith("SET ") for c in simulator.commands[before:])
                payload = {"profile_id": profile["id"], "max_us": 1100, "cycles": 1, "safety_confirmed": True}
                request(client, "post", "motors/start", json=payload)
                assert client.post("/api/v1/bench/stop").status_code == 409
                assert client.post("/api/v1/motors/start", json=payload).status_code == 409
                done = finished(client)
                assert done["phase"] == "COMPLETED" and done["acknowledged_frames"] == 50 and done["low_signal_confirmed"], done
                assert simulator.device.us == [1000]*4
                assert request(client, "get", "snapshot")["counters"] == baseline
                sent = [c for c in simulator.commands[before:] if c.startswith("SET ")]
                canonical = json.loads(module.profile_row(profile["id"])["canonical_json"])
                assert sent[4:-4] == [f"SET {ch} {value}" for frame in canonical["frames"] for ch, value in enumerate(frame)]
                results["completed_50hz_exact_values"] = done
                request(client, "post", "motors/start", json={**payload, "cycles": 3})
                time.sleep(.15)
                request(client, "post", "motors/cancel")
                cancelled = finished(client)
                assert cancelled["phase"] == "CANCELLED" and cancelled["low_signal_confirmed"], cancelled
                results["cancel_returns_low"] = cancelled
                request(client, "post", "motors/start", json=payload)
                time.sleep(.15)
                simulator.drop_reply_for = "SET 1 1040"
                failed = finished(client)
                assert failed["phase"] == "FAILED" and not failed["low_signal_confirmed"], failed
                recovery = failed["recovery"]
                assert recovery and 0 < recovery["acknowledged_frames"] < 50 and recovery["partial_frame_uncertain"], failed
                results["lost_ack_unknown_output"] = failed
                # Simulate bench power-cycle after losing the in-flight ACK.
                simulator.device.reboot()
                no_throttle_before_approval = len(simulator.commands)
                until = time.monotonic() + 15
                while time.monotonic() < until:
                    snap = request(client, "get", "snapshot")
                    if snap["motor_monitoring"]["current_all_low_reported"] is True:
                        break
                    time.sleep(.05)
                assert snap["motor_monitoring"]["current_all_low_reported"] is True, snap
                assert not module.app.state.motor_replay.active
                assert client.post("/api/v1/bench/stop").status_code == 409
                assert all(c.split()[2] == "1000" for c in simulator.commands[no_throttle_before_approval:] if c.startswith("SET "))
                resume_payload = {"run_id": recovery["run_id"], "hardware_recovery_confirmed": True, "uncertainty_acknowledged": True}
                assert client.post("/api/v1/motors/recovery/resume", json={"run_id": recovery["run_id"]}).status_code == 422
                # Reinitialize the backend: durable cursor/endpoint restored,
                # reconnects and waits for approval without throttle commands.
                restored_before = len(simulator.commands)
            with TestClient(module.app) as client:
                until = time.monotonic() + 10
                while time.monotonic() < until:
                    snap = request(client, "get", "snapshot")
                    if snap["motor_monitoring"]["current_all_low_reported"] is True:
                        break
                    time.sleep(.05)
                assert snap["motor_replay"]["recovery"]["acknowledged_frames"] == recovery["acknowledged_frames"]
                assert not snap["motor_replay"]["active"]
                assert all(c.split()[2] == "1000" for c in simulator.commands[restored_before:] if c.startswith("SET "))
                before_resume = len(simulator.commands)
                request(client, "post", "motors/recovery/resume", json=resume_payload)
                resumed = finished(client)
                assert resumed["phase"] == "COMPLETED" and resumed["acknowledged_frames"] == 50 and resumed["low_signal_confirmed"], resumed
                sent = [c for c in simulator.commands[before_resume:] if c.startswith("SET ")]
                assert sent[4:-4] == [f"SET {ch} {value}" for frame in canonical["frames"][recovery["acknowledged_frames"]:] for ch, value in enumerate(frame)]
                assert client.post("/api/v1/motors/recovery/resume", json=resume_payload).status_code == 409
                results["durable_power_loss_resume_exact_remaining_commands"] = resumed
                monitoring = request(client, "get", "snapshot")["motor_monitoring"]
                assert monitoring["current_all_low_reported"] is True
                assert all(c["physical_pwm_state"] == "UNKNOWN" and c["motor_rpm"] is None for c in monitoring["channels"])
                results["monitoring_honest_without_receiver"] = monitoring
                assert not any(c.split()[0] in {"STOP", "START", "LOAD", "F", "COMMIT", "CLEAR", "RESUME"} for c in simulator.commands[before:])
                results["no_native_motion_commands_or_counter_changes"] = True
        finally:
            simulator.close()
            module.DATA_DIR, official.STATE_FILE = original_dir, original_file
    output = Path("/private/tmp/athena-motor-replay-verification.json")
    output.write_text(json.dumps(results, indent=2) + "\n")
    print("PASS:", ", ".join(results), output)


if __name__ == "__main__":
    main()
