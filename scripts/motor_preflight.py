"""Connect Athena to the known Wi-Fi bench and report readiness; no output commands."""
import json
import urllib.request


def main():
    base = "http://127.0.0.1:8080/api/v1/"
    request = urllib.request.Request(base + "bench/tcp/connect",
        data=json.dumps({"host": "10.178.45.105", "port": 3333}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=15) as response:
        snapshot = json.load(response)
    print(json.dumps({key: snapshot.get(key) for key in ("connection", "bench_state", "motor_replay")}, indent=2))
    with urllib.request.urlopen(base + "profiles", timeout=5) as response:
        profiles = json.load(response)["items"]
    for profile in profiles:
        settings, summary = profile["settings"], profile["summary"]
        if settings["channel_count"] == 4:
            print(json.dumps({"profile_id": profile["id"], "duration_s": summary["duration_s"],
                "rate_hz": settings["rate_hz"], "ranges": summary["ranges"],
                "mapping": [{"output": item["output"], "source": item["source"]} for item in settings["mapping"]]}))


if __name__ == "__main__":
    main()
