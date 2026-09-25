"""Reconstruct a committed WDR profile from repeated STATUS observations.

This never sends LOAD, F, COMMIT or CLEAR. With --replay it sends finite
START 1 runs, which drive PWM outputs and increase the bench's lifetime
counters. STATUS exposes commanded widths, not measured electrical PWM.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from handout_controller_teams.bench_client import Bench, kv  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def reply_fields(bench: Bench, command: str) -> dict[str, str]:
    reply = bench.cmd(command)
    if reply is None or not reply.startswith(f"OK {command}"):
        raise RuntimeError(f"{command} failed: {reply!r}")
    return kv(reply)


def observed_status(bench: Bench, channels: int, frames: int) -> dict:
    fields = reply_fields(bench, "STATUS")
    try:
        current_frames = int(fields["frames"])
        frame = int(fields["frame"])
        widths = [int(value) for value in fields["us"].split(",")]
    except (KeyError, ValueError) as error:
        raise RuntimeError(f"Malformed STATUS: {fields}") from error
    if current_frames != frames or len(widths) != channels:
        raise RuntimeError(f"STATUS capability changed: {fields}")
    if any(not 500 <= width <= 2500 for width in widths):
        raise RuntimeError(f"Invalid STATUS pulse width: {fields}")
    return {"received_at_utc": utc_now(), "monotonic_s": time.monotonic(),
            "state": fields.get("state"), "cycle": fields.get("cycle"),
            "frame": frame, "us": widths}


def estimated_frame_rate(observations: list[dict]) -> float | None:
    """Fit frame index against receive time; cycle duration includes protocol lag."""
    rates = []
    for run in sorted({sample["run"] for sample in observations}):
        first_seen: dict[int, float] = {}
        for sample in observations:
            if sample["run"] == run and sample["state"] == "RUNNING":
                first_seen.setdefault(sample["frame"], sample["monotonic_s"])
        if len(first_seen) < 20:
            continue
        xs = list(first_seen)
        ys = [first_seen[index] for index in xs]
        average_x = statistics.mean(xs)
        average_y = statistics.mean(ys)
        denominator = sum((x - average_x) ** 2 for x in xs)
        slope = sum((x - average_x) * (y - average_y)
                    for x, y in zip(xs, ys)) / denominator
        if slope > 0:
            rates.append(1 / slope)
    return round(statistics.median(rates), 2) if rates else None


def capture(bench: Bench, *, frames: int, channels: int, max_runs: int,
            poll_ms: float, output_dir: Path, info: dict,
            counters_before: dict) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    observations: list[dict] = []
    by_frame: dict[int, set[tuple[int, ...]]] = defaultdict(set)
    cycle_durations: list[float] = []
    error: str | None = None
    started = False
    try:
        for run in range(1, max_runs + 1):
            preflight = observed_status(bench, channels, frames)
            if preflight["state"] != "STOPPED":
                raise RuntimeError(f"Bench is not stopped: {preflight['state']}")
            reply = bench.cmd("START 1")
            if reply != "OK":
                raise RuntimeError(f"START 1 failed: {reply!r}")
            started = True
            run_start = time.monotonic()
            # WDR accepts 10-100 Hz, so a 100-frame cycle can last 1-10 s.
            deadline = run_start + frames / 10 + 5
            saw_running = False
            while time.monotonic() < deadline:
                sample = observed_status(bench, channels, frames)
                sample["run"] = run
                observations.append(sample)
                if sample["state"] == "RUNNING":
                    saw_running = True
                    frame = sample["frame"]
                    if not 0 <= frame < frames:
                        raise RuntimeError(f"Invalid reported frame index {frame}")
                    by_frame[frame].add(tuple(sample["us"]))
                elif sample["state"] == "STOPPED" and saw_running:
                    cycle_durations.append(time.monotonic() - run_start)
                    started = False
                    break
                elif sample["state"] not in {"RUNNING", "STOPPED"}:
                    raise RuntimeError(f"Unexpected state {sample['state']}")
                time.sleep(poll_ms / 1000)
            else:
                raise RuntimeError("Finite replay did not finish before timeout")
            print(f"Run {run}: observed {len(by_frame)}/{frames} frame indices", flush=True)
            if len(by_frame) == frames:
                break
    except BaseException as caught:
        error = str(caught)
        raise
    finally:
        if started:
            try:
                bench.cmd("STOP")
            except Exception as caught:
                error = f"{error or 'capture interrupted'}; STOP failed: {caught}"
        try:
            status_after = reply_fields(bench, "STATUS")
            counters_after = reply_fields(bench, "COUNTERS")
        except Exception as caught:
            status_after = {"error": str(caught)}
            counters_after = {"error": str(caught)}
        conflicts = {index: [list(row) for row in sorted(rows)]
                     for index, rows in by_frame.items() if len(rows) != 1}
        complete = len(by_frame) == frames and not conflicts
        estimated_rate = estimated_frame_rate(observations)
        candidate_rate = round(estimated_rate) if estimated_rate is not None else None
        source_rate = (candidate_rate if candidate_rate is not None
                       and 10 <= candidate_rate <= 100
                       and abs(estimated_rate - candidate_rate) <= 0.5
                       else None)
        manifest = {
            "captured_at_utc": utc_now(), "host": info.get("host"),
            "info_before": {key: value for key, value in info.items() if key != "host"},
            "expected_frames": frames, "observed_frame_indices": len(by_frame),
            "complete_width_sequence": complete,
            "conflicting_frame_indices": conflicts,
            "counter_before": counters_before, "counter_after": counters_after,
            "status_after": status_after, "cycle_durations_s": cycle_durations,
            "estimated_rate_hz": estimated_rate,
            "rate_estimation_method": "linear fit of reported frame index against STATUS receive time",
            "candidate_import_rate_hz": source_rate,
            "reconstructed_sum16": (
                sum(sum(next(iter(by_frame[index]))) for index in range(frames)) % 65536
                if complete else None),
            "error": error,
            "provenance_note": "Reconstructed from STATUS during finite replays. "
                "Pulse widths are bench-reported commands, not physical measurements. "
                "Original labels, source log, checksum and exact upload rate are unknown.",
        }
        with (output_dir / "status_observations.jsonl").open("w") as stream:
            for sample in observations:
                stream.write(json.dumps(sample, sort_keys=True) + "\n")
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        if complete:
            with (output_dir / "reconstructed_frames.csv").open("w", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(["frame", *[f"OUT{index}_us" for index in range(channels)]])
                for index in range(frames):
                    writer.writerow([index, *next(iter(by_frame[index]))])
            if source_rate is not None:
                with (output_dir / "reconstructed_approx_TimeUS.csv").open("w", newline="") as stream:
                    writer = csv.writer(stream, lineterminator="\n")
                    writer.writerow(["TimeUS", *[f"C{index + 1}" for index in range(channels)]])
                    for index in range(frames + 1):
                        source_index = min(index, frames - 1)
                        writer.writerow([
                            round(index * 1_000_000 / source_rate),
                            *next(iter(by_frame[source_index])),
                        ])
        print(f"Saved capture evidence in {output_dir}; complete={complete}", flush=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=3333)
    parser.add_argument("--expected-team", default="WDR_REFERENCE")
    parser.add_argument("--expected-frames", type=int, default=100)
    parser.add_argument("--max-runs", type=int, default=3)
    parser.add_argument("--poll-ms", type=float, default=5)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--replay", action="store_true",
                        help="Send finite START 1 runs; changes lifetime counters")
    args = parser.parse_args()
    if not 1 <= args.expected_frames <= 8000 or not 1 <= args.max_runs <= 10:
        parser.error("Expected frames must be 1-8000 and max runs 1-10")
    if not 1 <= args.poll_ms <= 100:
        parser.error("Poll interval must be 1-100 ms")
    bench = Bench(args.host, args.port)
    try:
        info = reply_fields(bench, "INFO")
        status = reply_fields(bench, "STATUS")
        counters = reply_fields(bench, "COUNTERS")
        print("INFO", info, "STATUS", status, "COUNTERS", counters, flush=True)
        if info.get("proto") != "1" or info.get("team") != args.expected_team:
            raise RuntimeError("Unexpected protocol or bench identity; refusing replay")
        if int(info["ch"]) != 4 or int(status["frames"]) != args.expected_frames:
            raise RuntimeError("Unexpected channel count or saved profile length; refusing replay")
        if status.get("state") != "STOPPED":
            raise RuntimeError("Bench must be STOPPED before replay")
        if not args.replay:
            print("Read-only check complete. Add --replay to capture finite runs.")
            return 0
        output_dir = args.output_dir or Path("captures") / (
            "reference_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        if output_dir.exists():
            raise RuntimeError(f"Output directory already exists: {output_dir}")
        manifest = capture(
            bench, frames=args.expected_frames, channels=4,
            max_runs=args.max_runs, poll_ms=args.poll_ms,
            output_dir=output_dir, info={**info, "host": args.host},
            counters_before=counters,
        )
        return 0 if manifest["complete_width_sequence"] else 2
    finally:
        bench.sock.close()


if __name__ == "__main__":
    raise SystemExit(main())
