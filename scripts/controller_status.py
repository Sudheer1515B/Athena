"""Read current Athena state without connecting or issuing motor commands."""
import json
import urllib.request


if __name__ == "__main__":
    with urllib.request.urlopen("http://127.0.0.1:8080/api/v1/snapshot", timeout=5) as response:
        snapshot = json.load(response)
    print(json.dumps({key: snapshot.get(key) for key in
        ("connection", "bench_state", "motor_replay", "motor_monitoring", "receiver", "observation")}, indent=2))
