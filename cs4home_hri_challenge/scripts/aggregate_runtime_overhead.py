#!/usr/bin/env python3
"""Aggregate runtime trace events into capability measurements and summaries."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "hri_runtime_eval"


TIMESTAMP_FIELDS = [
    "decision_ts_ns",
    "first_bt_action_start_ts_ns",
    "capability_finish_ts_ns",
    "transition_to_next_ts_ns",
    "failure_detection_ts_ns",
    "recovery_start_ts_ns",
    "recovery_completion_ts_ns",
]

DURATION_FIELDS = [
    "activation_latency_ms",
    "capability_execution_time_ms",
    "completion_transition_latency_ms",
    "recovery_activation_latency_ms",
    "recovery_duration_ms",
    "total_mission_time_ms",
]

EVENT_TO_FIELD = {
    "capability_decision": "decision_ts_ns",
    "first_bt_action_start": "first_bt_action_start_ts_ns",
    "capability_finished": "capability_finish_ts_ns",
    "completion_received": "capability_finish_ts_ns",
    "transition_to_next": "transition_to_next_ts_ns",
    "failure_detected": "failure_detection_ts_ns",
    "recovery_start": "recovery_start_ts_ns",
    "recovery_completion": "recovery_completion_ts_ns",
}


def ns_to_ms(value: int | None) -> float | str:
    if value is None:
        return ""
    return value / 1_000_000.0


def delta_ms(start: int | None, end: int | None) -> float | str:
    if start is None or end is None:
        return ""
    return (end - start) / 1_000_000.0


def read_events(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: (r["run_id"], r["architecture"], int(r["stamp_ns"])))
    return rows


def build_measurements(events: list[dict[str, str]]) -> list[dict[str, object]]:
    by_run = defaultdict(list)
    for event in events:
        by_run[(event["run_id"], event["architecture"])].append(event)

    measurements: list[dict[str, object]] = []
    for (run_id, architecture), rows in by_run.items():
        mission_start = int(rows[0]["stamp_ns"]) if rows else None
        mission_end = int(rows[-1]["stamp_ns"]) if rows else None
        open_rows: dict[str, dict[str, object]] = {}
        occurrence = defaultdict(int)

        def current(capability: str, module_name: str, flow_name: str) -> dict[str, object]:
            if capability not in open_rows:
                occurrence[capability] += 1
                open_rows[capability] = {
                    "run_id": run_id,
                    "architecture": architecture,
                    "flow_name": flow_name,
                    "capability": capability,
                    "module_name": module_name,
                    "occurrence_index": occurrence[capability],
                }
            return open_rows[capability]

        for event in rows:
            capability = event["capability"]
            if not capability:
                continue
            item = current(capability, event["module_name"], event["flow_name"])
            field = EVENT_TO_FIELD.get(event["event"])
            if field:
                item.setdefault(field, int(event["stamp_ns"]))
            if event["event"] in {"transition_to_next", "recovery_completion"}:
                measurements.append(item)
                open_rows.pop(capability, None)

        for item in open_rows.values():
            measurements.append(item)

        for item in measurements:
            if item.get("run_id") != run_id or item.get("architecture") != architecture:
                continue
            decision = item.get("decision_ts_ns")
            first = item.get("first_bt_action_start_ts_ns")
            finish = item.get("capability_finish_ts_ns")
            transition = item.get("transition_to_next_ts_ns")
            failure = item.get("failure_detection_ts_ns")
            recovery_start = item.get("recovery_start_ts_ns")
            recovery_done = item.get("recovery_completion_ts_ns")
            item["activation_latency_ms"] = delta_ms(decision, first)
            item["capability_execution_time_ms"] = delta_ms(first, finish)
            item["completion_transition_latency_ms"] = delta_ms(finish, transition)
            item["recovery_activation_latency_ms"] = delta_ms(failure, recovery_start)
            item["recovery_duration_ms"] = delta_ms(recovery_start, recovery_done)
            item["total_mission_time_ms"] = delta_ms(mission_start, mission_end)

    for item in measurements:
        for field in TIMESTAMP_FIELDS:
            item.setdefault(field, "")
        for field in DURATION_FIELDS:
            item.setdefault(field, "")
    return measurements


def write_measurements(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "run_id",
        "architecture",
        "flow_name",
        "capability",
        "module_name",
        "occurrence_index",
        *TIMESTAMP_FIELDS,
        *DURATION_FIELDS,
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_summary(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["architecture"], row["capability"])].append(row)

    fields = ["architecture", "capability", "metric", "count", "mean_ms", "median_ms", "stddev_ms", "min_ms", "max_ms"]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for (architecture, capability), items in sorted(grouped.items()):
            for metric in DURATION_FIELDS:
                values = [float(item[metric]) for item in items if item.get(metric) != ""]
                if not values:
                    continue
                writer.writerow(
                    {
                        "architecture": architecture,
                        "capability": capability,
                        "metric": metric,
                        "count": len(values),
                        "mean_ms": statistics.mean(values),
                        "median_ms": statistics.median(values),
                        "stddev_ms": statistics.stdev(values) if len(values) > 1 else 0.0,
                        "min_ms": min(values),
                        "max_ms": max(values),
                    }
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", default=str(DEFAULT_OUTPUT_DIR / "runtime_events.csv"))
    parser.add_argument("--measurements", default=str(DEFAULT_OUTPUT_DIR / "capability_runtime_measurements.csv"))
    parser.add_argument("--summary", default=str(DEFAULT_OUTPUT_DIR / "capability_runtime_summary.csv"))
    args = parser.parse_args()

    events = read_events(Path(args.events))
    measurements = build_measurements(events)
    write_measurements(measurements, Path(args.measurements))
    write_summary(measurements, Path(args.summary))


if __name__ == "__main__":
    main()
