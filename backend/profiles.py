"""Inspect flight CSVs and compile deterministic WDR v1 pulse profiles."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import statistics
from bisect import bisect_right
from dataclasses import dataclass

MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_SOURCE_ROWS = 500_000
IDLE_US = 1500
COMPILER_VERSION = 1
CHANNEL_NAME = re.compile(r"C(?:[1-9]|1[0-6])\Z")


class ProfileIssue(ValueError):
    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def as_json(self) -> dict:
        return {"code": self.code, "message": str(self), **self.details}


@dataclass(frozen=True)
class FlightLog:
    columns: tuple[str, ...]
    times: tuple[int, ...]
    values: dict[str, tuple[int, ...]]
    inspection: dict


def _parse_integer(value: str | None, line: int, column: str) -> int:
    if value is None or not re.fullmatch(r"[+-]?\d+", value.strip()):
        raise ProfileIssue(
            "invalid_integer", f"Line {line}: {column} must be an integer",
            line=line, column=column, value=value,
        )
    return int(value)


def inspect_csv(data: bytes) -> FlightLog:
    if len(data) > MAX_SOURCE_BYTES:
        raise ProfileIssue("source_too_large", "CSV exceeds the 50 MiB limit")
    try:
        source = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ProfileIssue("invalid_encoding", "CSV must be UTF-8") from error
    reader = csv.reader(io.StringIO(source, newline=""), strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as error:
        raise ProfileIssue("missing_header", "CSV has no valid header") from error
    if len(header) != len(set(header)):
        raise ProfileIssue("duplicate_header", "CSV header contains duplicate names")
    if "TimeUS" not in header:
        raise ProfileIssue("missing_time", "CSV needs a TimeUS column")
    columns = tuple(name for name in header if CHANNEL_NAME.fullmatch(name))
    if not columns:
        raise ProfileIssue("missing_channels", "CSV needs at least one C1–C16 column")
    extra = [name for name in header if name != "TimeUS" and name not in columns]
    times: list[int] = []
    values: dict[str, list[int]] = {name: [] for name in columns}
    try:
        for row in reader:
            line = reader.line_num
            if not row or (len(row) == 1 and not row[0].strip()):
                continue
            if len(row) != len(header):
                raise ProfileIssue(
                    "ragged_row", f"Line {line}: expected {len(header)} fields, got {len(row)}",
                    line=line,
                )
            fields = dict(zip(header, row, strict=True))
            t = _parse_integer(fields["TimeUS"], line, "TimeUS")
            if t < 0 or (times and t <= times[-1]):
                raise ProfileIssue(
                    "invalid_timestamp", f"Line {line}: TimeUS must be nonnegative and increasing",
                    line=line, value=t,
                )
            times.append(t)
            for name in columns:
                values[name].append(_parse_integer(fields[name], line, name))
            if len(times) > MAX_SOURCE_ROWS:
                raise ProfileIssue("too_many_rows", "CSV exceeds the 500,000-row limit")
    except csv.Error as error:
        raise ProfileIssue("invalid_csv", f"CSV syntax error near line {reader.line_num}") from error
    if len(times) < 2:
        raise ProfileIssue("too_few_rows", "CSV needs at least two data rows")

    deltas = [right - left for left, right in zip(times, times[1:])]
    median_us = int(statistics.median(deltas))
    gap_limit = median_us * 5
    gaps = [
        {"before_index": i, "after_index": i + 1,
         "start_us": times[i] - times[0], "end_us": times[i + 1] - times[0],
         "duration_us": delta}
        for i, delta in enumerate(deltas) if delta > gap_limit
    ]
    channel_stats = {}
    for name in columns:
        series = values[name]
        channel_stats[name] = {
            "min_us": min(series), "max_us": max(series),
            "zero_count": sum(value == 0 for value in series),
            "invalid_count": sum(not 500 <= value <= 2500 for value in series),
        }
    inspection = {
        "dialect": "timeus_csv_v1", "row_count": len(times),
        "columns": list(columns), "extra_columns": extra,
        "first_time_us": times[0], "last_time_us": times[-1],
        "duration_us": times[-1] - times[0], "median_interval_us": median_us,
        "effective_rate_hz": round(1_000_000 / median_us, 4),
        "gap_threshold_us": gap_limit, "gaps": gaps,
        "channels": channel_stats,
    }
    return FlightLog(columns, tuple(times), {k: tuple(v) for k, v in values.items()}, inspection)


def compile_profile(
    flight: FlightLog,
    source_sha256: str,
    *,
    start_us: int,
    end_us: int,
    rate_hz: int,
    channel_count: int,
    maxframes: int,
    mapping: list[dict],
) -> tuple[dict, dict]:
    if not 1 <= channel_count <= 16 or maxframes < 1:
        raise ProfileIssue("capabilities", "Invalid bench channel count or frame limit")
    if not 10 <= rate_hz <= 100:
        raise ProfileIssue("rate", "Frame rate must be 10–100 per second")
    duration = flight.times[-1] - flight.times[0]
    if not 0 <= start_us < end_us <= duration:
        raise ProfileIssue("trim", "Trim must lie inside the source and have positive duration")
    frame_count = (end_us - start_us) * rate_hz // 1_000_000
    if frame_count < 1:
        raise ProfileIssue("short_window", "Trim contains less than one complete frame")
    if frame_count > maxframes:
        raise ProfileIssue(
            "capacity", f"{frame_count} frames exceed bench limit {maxframes}",
            frame_count=frame_count, maxframes=maxframes,
        )
    if len(mapping) != channel_count:
        raise ProfileIssue("mapping", "Provide one mapping entry for every bench output")
    ordered = sorted(mapping, key=lambda item: item.get("output", -1))
    if [item.get("output") for item in ordered] != list(range(channel_count)):
        raise ProfileIssue("mapping", "Bench outputs must be numbered 0 through N−1 once each")
    assigned: set[str] = set()
    for item in ordered:
        source = item.get("source")
        if source is not None:
            if source not in flight.columns or source in assigned:
                raise ProfileIssue("mapping", f"Invalid or duplicate source {source}")
            assigned.add(source)
        low, high = item.get("min_us", 500), item.get("max_us", 2500)
        if not isinstance(low, int) or not isinstance(high, int) or not 500 <= low <= 1500 <= high <= 2500:
            raise ProfileIssue("limits", f"Invalid pulse limits for OUT{item['output']}")
        for key in ("label", "serial"):
            if item.get(key) is not None and (not isinstance(item[key], str) or len(item[key]) > 120):
                raise ProfileIssue("mapping", f"Invalid {key} for OUT{item['output']}")
    if not assigned:
        raise ProfileIssue("mapping", "Map at least one source channel")
    for gap in flight.inspection["gaps"]:
        if start_us > gap["start_us"] and start_us < gap["end_us"]:
            raise ProfileIssue("gap", "Trim starts inside a source gap", gap=gap)
        if start_us < gap["end_us"] and end_us > gap["start_us"]:
            raise ProfileIssue("gap", "Trim crosses a source gap", gap=gap)

    absolute_start = flight.times[0] + start_us
    absolute_end = flight.times[0] + end_us
    initial_index = bisect_right(flight.times, absolute_start) - 1
    if initial_index < 0:
        raise ProfileIssue("trim", "No source sample at trim start")
    final_index = bisect_right(flight.times, absolute_end - 1)
    for item in ordered:
        source = item.get("source")
        if source is None:
            continue
        low, high = item.get("min_us", 500), item.get("max_us", 2500)
        for index in range(initial_index, final_index):
            value = flight.values[source][index]
            if not low <= value <= high:
                raise ProfileIssue(
                    "pulse_range", f"{source} has {value} µs outside OUT{item['output']} limits",
                    source=source, output=item["output"], sample_index=index,
                    time_us=flight.times[index] - flight.times[0], value=value,
                )
    frames: list[list[int]] = []
    for k in range(frame_count):
        target_scaled = absolute_start * rate_hz + k * 1_000_000
        lo, hi = initial_index, len(flight.times)
        while lo < hi:
            mid = (lo + hi) // 2
            if flight.times[mid] * rate_hz <= target_scaled:
                lo = mid + 1
            else:
                hi = mid
        sample_index = lo - 1
        frame = [
            flight.values[item["source"]][sample_index] if item.get("source") else IDLE_US
            for item in ordered
        ]
        line = f"F {k} " + " ".join(map(str, frame))
        if len(line) > 128:
            raise ProfileIssue("wire_length", "WDR frame command exceeds 128 characters")
        frames.append(frame)
    canonical_mapping = [
        {"output": item["output"], "source": item.get("source"),
         "label": item.get("label") or item.get("source") or f"OUT{item['output']}",
         "serial": item.get("serial") or None,
         "min_us": item.get("min_us", 500), "max_us": item.get("max_us", 2500)}
        for item in ordered
    ]
    canonical = {
        "schema_version": 1, "compiler_version": COMPILER_VERSION,
        "source_sha256": source_sha256, "source_dialect": flight.inspection["dialect"],
        "start_us": start_us, "end_us": end_us, "rate_hz": rate_hz,
        "channel_count": channel_count, "mapping": canonical_mapping,
        "gap_policy": {"kind": "median_multiplier", "multiplier": 5},
        "frames": frames,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    step_max = [max((abs(frames[i][ch] - frames[i - 1][ch]) for i in range(1, frame_count)), default=0) for ch in range(channel_count)]
    summary = {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "sum16": sum(sum(frame) for frame in frames) % 65536,
        "frame_count": frame_count, "rate_hz": rate_hz,
        "channel_count": channel_count,
        "duration_s": frame_count / rate_hz,
        "discarded_us": (end_us - start_us) - frame_count * 1_000_000 // rate_hz,
        "first_frame": frames[0], "last_frame": frames[-1],
        "ranges": [{"min_us": min(row[ch] for row in frames),
                    "max_us": max(row[ch] for row in frames),
                    "max_step_us": step_max[ch],
                    "loop_step_us": abs(frames[-1][ch] - frames[0][ch])}
                   for ch in range(channel_count)],
    }
    return canonical, summary
