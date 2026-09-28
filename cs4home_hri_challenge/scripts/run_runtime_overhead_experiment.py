#!/usr/bin/env python3
"""Run capability-level runtime overhead experiments for BT vs modular HRI."""

from __future__ import annotations

import argparse
import csv
import math
import os
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path


def package_dir() -> Path:
    source_layout = Path(__file__).resolve().parents[1]
    if (source_layout / "bt_xml").exists():
        return source_layout
    from ament_index_python.packages import get_package_share_directory
    return Path(get_package_share_directory("cs4home_hri_challenge"))


PACKAGE = package_dir()
DEFAULT_OUTPUT_DIR = PACKAGE / "data" / "hri_runtime_eval"
RUNTIME_BT_DIR = PACKAGE / "bt_xml" / "runtime_instrumented"

CAPABILITIES = {
    "greeting": {"label": "Greeting", "module": "greeting_guest_cognitive_module", "executable": "greeting_guest_cognitive_module", "bt_file": "greeting_guest.xml"},
    "describe_person": {"label": "Describe / Invite", "module": "describe_person_cognitive_module", "executable": "describe_person_cognitive_module", "bt_file": "describe_person.xml"},
    "introduce_guest": {"label": "Introduce Guest", "module": "introduce_guest_cognitive_module", "executable": "introduce_guest_cognitive_module", "bt_file": "introduce_guest.xml"},
    "find_seat": {"label": "Find Seat", "module": "find_seat_cognitive_module", "executable": "find_seat_cognitive_module", "bt_file": "find_seat.xml"},
    "grab_bag": {"label": "Grab Bag", "module": "grab_bag_cognitive_module", "executable": "grab_bag_cognitive_module", "bt_file": "grab_bag.xml"},
    "transport_bag": {"label": "Transport Bag", "module": "transport_bag_cognitive_module", "executable": "transport_bag_cognitive_module", "bt_file": "transport_bag.xml"},
    "recovery": {"label": "Recovery", "module": "recovery_cognitive_module", "executable": "recovery_cognitive_module", "bt_file": "recovery.xml"},
}

TIMESTAMP_FIELDS = [
    "experiment_start_ts_ns",
    "capability_request_ts_ns",
    "lifecycle_activation_request_ts_ns",
    "capability_executable_ts_ns",
    "first_bt_action_start_ts_ns",
    "last_bt_action_finish_ts_ns",
    "capability_completion_ts_ns",
    "deactivation_or_success_ts_ns",
    "experiment_end_ts_ns",
    "failure_detected_ts_ns",
    "recovery_requested_ts_ns",
    "recovery_started_ts_ns",
    "recovery_completed_ts_ns",
]

METRIC_FIELDS = [
    "orchestrated_capability_startup_time_ms",
    "pure_lifecycle_activation_time_ms",
    "capability_initialization_time_ms",
    "capability_execution_time_ms",
    "completion_deactivation_overhead_ms",
    "total_capability_duration_ms",
    "experiment_total_duration_ms",
    "failure_detection_latency_ms",
    "recovery_activation_latency_ms",
    "recovery_execution_time_ms",
    "total_recovery_duration_ms",
]

INVALID_RUN_FIELDS = [
    "run_id",
    "architecture",
    "capability",
    "reason",
    "diagnostic",
    *TIMESTAMP_FIELDS,
]

MEASUREMENT_FIELDS = [
    "run_id",
    "architecture",
    "capability",
    "capability_label",
    "module_name",
    "failure_mode",
    "completed",
    "return_code",
    *TIMESTAMP_FIELDS,
    *METRIC_FIELDS,
]

SUMMARY_FIELDS = [
    "architecture",
    "capability",
    "metric",
    "count",
    "mean_ms",
    "median_ms",
    "stddev_ms",
    "min_ms",
    "max_ms",
    "ci95_low_ms",
    "ci95_high_ms",
]

RESOURCE_SAMPLE_FIELDS = [
    "run_id", "architecture", "capability", "stamp_ns", "process_name", "pid",
    "cpu_percent", "rss_mb", "thread_count", "ros2_process_count",
]

RESOURCE_SUMMARY_FIELDS = [
    "run_id", "architecture", "capability", "scope", "process_name", "pid", "sample_count",
    "mean_cpu_percent", "peak_cpu_percent", "mean_rss_mb", "peak_rss_mb",
    "mean_thread_count", "peak_thread_count", "mean_ros2_process_count", "peak_ros2_process_count",
]


def ns_delta_ms(start: int | None, end: int | None) -> float | str:
    if start is None or end is None:
        return ""
    return (end - start) / 1_000_000.0


def ensure_csv_schema(path: Path, fieldnames: list[str]) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open(newline="") as f:
        header = next(csv.reader(f), [])
    if header == fieldnames:
        return
    backup = path.with_name(f"{path.name}.bak-{int(time.time())}")
    path.rename(backup)
    print(f"Archived incompatible CSV schema: {backup}", flush=True)


def append_csv(path: Path, fieldnames: list[str], row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_csv_schema(path, fieldnames)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_total_jiffies() -> int:
    with Path("/proc/stat").open() as f:
        return sum(int(value) for value in f.readline().split()[1:])


def read_process_sample(pid: int) -> dict[str, object] | None:
    proc_dir = Path("/proc") / str(pid)
    try:
        stat_parts = (proc_dir / "stat").read_text().split()
        comm = (proc_dir / "comm").read_text().strip()
        status = (proc_dir / "status").read_text().splitlines()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None

    rss_kb = 0
    threads = 0
    for line in status:
        if line.startswith("VmRSS:"):
            rss_kb = int(line.split()[1])
        elif line.startswith("Threads:"):
            threads = int(line.split()[1])

    return {
        "pid": pid,
        "process_name": comm,
        "cpu_jiffies": int(stat_parts[13]) + int(stat_parts[14]),
        "rss_mb": rss_kb / 1024.0,
        "thread_count": threads,
    }


def process_parent_map() -> dict[int, int]:
    parents: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            for line in (entry / "status").read_text().splitlines():
                if line.startswith("PPid:"):
                    parents[int(entry.name)] = int(line.split()[1])
                    break
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return parents


def descendant_pids(root_pids: list[int]) -> set[int]:
    parents = process_parent_map()
    children: dict[int, list[int]] = defaultdict(list)
    for pid, ppid in parents.items():
        children[ppid].append(pid)
    result = set(root_pids)
    stack = list(root_pids)
    while stack:
        parent = stack.pop()
        for child in children.get(parent, []):
            if child not in result:
                result.add(child)
                stack.append(child)
    return result


class ResourceMonitor:
    def __init__(self, output_dir: Path, run_id: str, architecture: str, capability: str, sample_period_sec: float):
        self.output_dir = output_dir
        self.run_id = run_id
        self.architecture = architecture
        self.capability = capability
        self.sample_period_sec = sample_period_sec
        self.previous_total = read_total_jiffies()
        self.previous_proc: dict[int, int] = {}
        self.last_sample_sec = 0.0
        self.samples: list[dict[str, object]] = []

    def maybe_sample(self, root_pids: list[int]) -> None:
        now = time.monotonic()
        if now - self.last_sample_sec >= self.sample_period_sec:
            self.last_sample_sec = now
            self.sample(root_pids)

    def sample(self, root_pids: list[int]) -> None:
        cpu_count = os.cpu_count() or 1
        stamp_ns = time.time_ns()
        current_total = read_total_jiffies()
        total_delta = max(1, current_total - self.previous_total)
        current_proc: dict[int, int] = {}
        samples = []
        for pid in sorted(descendant_pids(root_pids)):
            sample = read_process_sample(pid)
            if sample is not None:
                samples.append(sample)
        ros2_process_count = len(samples)

        for sample in samples:
            pid = int(sample["pid"])
            current_proc[pid] = int(sample["cpu_jiffies"])
            prev_jiffies = self.previous_proc.get(pid, current_proc[pid])
            cpu_percent = ((current_proc[pid] - prev_jiffies) / total_delta) * cpu_count * 100.0
            row = {
                "run_id": self.run_id,
                "architecture": self.architecture,
                "capability": self.capability,
                "stamp_ns": stamp_ns,
                "process_name": sample["process_name"],
                "pid": pid,
                "cpu_percent": max(0.0, cpu_percent),
                "rss_mb": sample["rss_mb"],
                "thread_count": sample["thread_count"],
                "ros2_process_count": ros2_process_count,
            }
            append_csv(self.output_dir / "resource_samples.csv", RESOURCE_SAMPLE_FIELDS, row)
            self.samples.append(row)

        self.previous_total = current_total
        self.previous_proc = current_proc

    def write_summary(self) -> None:
        if not self.samples:
            return
        path = self.output_dir / "resource_summary.csv"
        by_timestamp: dict[int, list[dict[str, object]]] = defaultdict(list)
        by_process: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
        for sample in self.samples:
            by_timestamp[int(sample["stamp_ns"])].append(sample)
            by_process[(str(sample["process_name"]), int(sample["pid"]))].append(sample)

        def write(scope: str, process_name: str, pid: object, rows: list[dict[str, object]]) -> None:
            cpus = [float(row["cpu_percent"]) for row in rows]
            rss = [float(row["rss_mb"]) for row in rows]
            threads = [int(row["thread_count"]) for row in rows]
            process_counts = [int(row["ros2_process_count"]) for row in rows]
            append_csv(path, RESOURCE_SUMMARY_FIELDS, {
                "run_id": self.run_id,
                "architecture": self.architecture,
                "capability": self.capability,
                "scope": scope,
                "process_name": process_name,
                "pid": pid,
                "sample_count": len(rows),
                "mean_cpu_percent": statistics.mean(cpus),
                "peak_cpu_percent": max(cpus),
                "mean_rss_mb": statistics.mean(rss),
                "peak_rss_mb": max(rss),
                "mean_thread_count": statistics.mean(threads),
                "peak_thread_count": max(threads),
                "mean_ros2_process_count": statistics.mean(process_counts),
                "peak_ros2_process_count": max(process_counts),
            })

        for (process_name, pid), rows in sorted(by_process.items()):
            write("process", process_name, pid, rows)

        totals = []
        for rows in by_timestamp.values():
            totals.append({
                "cpu_percent": sum(float(row["cpu_percent"]) for row in rows),
                "rss_mb": sum(float(row["rss_mb"]) for row in rows),
                "thread_count": sum(int(row["thread_count"]) for row in rows),
                "ros2_process_count": max(int(row["ros2_process_count"]) for row in rows),
            })
        write("run_total", "all_relevant_processes", "", totals)


def terminate_processes(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 5.0
    for process in processes:
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
    for process in processes:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def read_run_events(output_dir: Path, run_id: str) -> list[dict[str, str]]:
    path = output_dir / "runtime_events.csv"
    if not path.exists():
        return []
    with path.open(newline="") as f:
        rows = [row for row in csv.DictReader(f) if row.get("run_id") == run_id]
    rows.sort(key=lambda row: int(row["stamp_ns"]))
    return rows


def first_event_ts(events: list[dict[str, str]], names: set[str], capability_label: str | None = None) -> int | None:
    for event in events:
        if event.get("event") not in names:
            continue
        if capability_label is not None and event.get("capability") != capability_label:
            continue
        return int(event["stamp_ns"])
    return None


def last_event_ts(events: list[dict[str, str]], names: set[str], capability_label: str | None = None) -> int | None:
    for event in reversed(events):
        if event.get("event") not in names:
            continue
        if capability_label is not None and event.get("capability") != capability_label:
            continue
        return int(event["stamp_ns"])
    return None


def matching_events(
    events: list[dict[str, str]],
    names: set[str],
    capability_label: str | None = None,
) -> list[dict[str, str]]:
    return [
        event for event in events
        if event.get("event") in names and
        (capability_label is None or event.get("capability") == capability_label)
    ]


def set_invalid(row: dict[str, object], reason: str, diagnostic: str) -> None:
    row["completed"] = "false"
    row["_invalid_reason"] = reason
    row["_invalid_diagnostic"] = diagnostic


def validate_row(row: dict[str, object], events: list[dict[str, str]], args: argparse.Namespace) -> None:
    label = str(row["capability_label"])
    architecture = str(row["architecture"])
    errors: list[str] = []

    required = [
        ("first_bt_action_start", {"first_bt_action_start"}, label),
    ]
    if architecture == "modular":
        required.extend([
            ("lifecycle_activation_request", {"lifecycle_activation_request"}, label),
            ("lifecycle_activated", {"lifecycle_activated"}, label),
        ])
    else:
        required.append(("capability_executable", {"capability_executable"}, label))

    if args.failure_mode:
        required.extend([
            ("failure_detected", {"failure_detected"}, label),
            ("recovery_requested", {"recovery_requested", "recovery_start"}, label),
            ("recovery_started", {"lifecycle_activated", "first_bt_action_start"}, "Recovery"),
            ("recovery_completion", {"recovery_completion"}, "Recovery"),
        ])
    else:
        required.append(("last_bt_action_finish", {"last_bt_action_finish", "capability_finished_marker"}, label))
        if architecture == "modular":
            required.extend([
                ("capability_finished", {"capability_finished"}, label),
                ("capability_completion", {"completion_received"}, label),
                ("deactivation_or_success", {"lifecycle_deactivated"}, label),
            ])
        else:
            required.extend([
                ("capability_completion", {"capability_finished"}, label),
                ("deactivation_or_success", {"transition_to_next"}, label),
            ])

    for field, names, capability in required:
        matches = matching_events(events, names, capability)
        if len(matches) != 1:
            errors.append(
                f"{field}: expected exactly 1 event in {sorted(names)} for capability {capability}, got {len(matches)}"
            )

    ordered_fields = [
        "experiment_start_ts_ns",
        "capability_request_ts_ns",
    ]
    if architecture == "modular":
        ordered_fields.append("lifecycle_activation_request_ts_ns")
    ordered_fields.extend([
        "capability_executable_ts_ns",
        "first_bt_action_start_ts_ns",
    ])
    if args.failure_mode:
        ordered_fields.extend([
            "failure_detected_ts_ns",
            "recovery_requested_ts_ns",
            "recovery_started_ts_ns",
            "recovery_completed_ts_ns",
            "experiment_end_ts_ns",
        ])
    else:
        ordered_fields.extend([
            "last_bt_action_finish_ts_ns",
            "capability_completion_ts_ns",
            "deactivation_or_success_ts_ns",
            "experiment_end_ts_ns",
        ])

    seen: list[tuple[str, int]] = []
    for field in ordered_fields:
        value = row.get(field)
        if value in (None, ""):
            errors.append(f"missing timestamp {field}")
            continue
        seen.append((field, int(value)))
    for (prev_field, prev_ts), (field, ts) in zip(seen, seen[1:]):
        if ts < prev_ts:
            errors.append(f"chronology violation: {field}={ts} < {prev_field}={prev_ts}")

    for metric in METRIC_FIELDS:
        value = row.get(metric)
        if value in (None, ""):
            continue
        if float(value) < 0.0:
            errors.append(f"negative duration: {metric}={value}")

    if errors:
        event_dump = "; ".join(
            f"{event.get('event')}[{event.get('capability')}]={event.get('stamp_ns')}"
            for event in events
        )
        set_invalid(row, "validation_failed", " | ".join(errors) + f" | events: {event_dump}")


def build_row(
    args: argparse.Namespace,
    run_id: str,
    architecture: str,
    start_ns: int,
    request_ns: int,
    end_ns: int,
    return_code: int | str,
    completed: bool,
    events: list[dict[str, str]],
) -> dict[str, object]:
    info = CAPABILITIES[args.capability]
    label = info["label"]
    events = [
        event for event in events
        if start_ns <= int(event["stamp_ns"]) <= end_ns
    ]
    executable = first_event_ts(events, {"capability_executable"}, label)
    lifecycle_activation_request = None
    if architecture == "modular":
        lifecycle_activation_request = first_event_ts(events, {"lifecycle_activation_request"}, label)
        executable = first_event_ts(events, {"lifecycle_activated"}, label) or executable
    first_action = first_event_ts(events, {"first_bt_action_start"}, label)
    last_action = last_event_ts(events, {"last_bt_action_finish", "capability_finished_marker"}, label)
    if architecture == "modular":
        completion = first_event_ts(events, {"completion_received"}, label)
        deactivation = last_event_ts(events, {"lifecycle_deactivated"}, label)
    else:
        completion = first_event_ts(events, {"capability_finished"}, label)
        deactivation = last_event_ts(events, {"transition_to_next"}, label)
    failure = first_event_ts(events, {"failure_detected"}, label)
    recovery_requested = first_event_ts(events, {"recovery_requested", "recovery_start"}, label)
    recovery_started = first_event_ts(events, {"lifecycle_activated", "first_bt_action_start"}, "Recovery")
    recovery_done = first_event_ts(events, {"recovery_completion"}, "Recovery")

    row: dict[str, object] = {
        "run_id": run_id,
        "architecture": architecture,
        "capability": args.capability,
        "capability_label": label,
        "module_name": info["module"],
        "failure_mode": str(args.failure_mode).lower(),
        "completed": str(completed and deactivation is not None).lower(),
        "return_code": return_code,
        "experiment_start_ts_ns": start_ns,
        "capability_request_ts_ns": request_ns,
        "lifecycle_activation_request_ts_ns": lifecycle_activation_request or "",
        "capability_executable_ts_ns": executable or "",
        "first_bt_action_start_ts_ns": first_action or "",
        "last_bt_action_finish_ts_ns": last_action or "",
        "capability_completion_ts_ns": completion or "",
        "deactivation_or_success_ts_ns": deactivation or "",
        "experiment_end_ts_ns": end_ns,
        "failure_detected_ts_ns": failure or "",
        "recovery_requested_ts_ns": recovery_requested or "",
        "recovery_started_ts_ns": recovery_started or "",
        "recovery_completed_ts_ns": recovery_done or "",
    }
    row["orchestrated_capability_startup_time_ms"] = ns_delta_ms(request_ns, executable)
    row["pure_lifecycle_activation_time_ms"] = ns_delta_ms(lifecycle_activation_request, executable)
    row["capability_initialization_time_ms"] = ns_delta_ms(executable, first_action)
    row["capability_execution_time_ms"] = ns_delta_ms(first_action, last_action)
    row["completion_deactivation_overhead_ms"] = ns_delta_ms(last_action, deactivation)
    row["total_capability_duration_ms"] = ns_delta_ms(request_ns, deactivation)
    row["experiment_total_duration_ms"] = ns_delta_ms(start_ns, end_ns)
    row["failure_detection_latency_ms"] = ns_delta_ms(first_action, failure)
    row["recovery_activation_latency_ms"] = ns_delta_ms(recovery_requested, recovery_started)
    row["recovery_execution_time_ms"] = ns_delta_ms(recovery_started, recovery_done)
    row["total_recovery_duration_ms"] = ns_delta_ms(failure, recovery_done)
    validate_row(row, events, args)
    return row


def stats(values: list[float]) -> dict[str, float | int]:
    count = len(values)
    mean = statistics.mean(values)
    stddev = statistics.stdev(values) if count > 1 else 0.0
    ci = 1.96 * stddev / math.sqrt(count) if count > 1 else 0.0
    return {
        "count": count,
        "mean_ms": mean,
        "median_ms": statistics.median(values),
        "stddev_ms": stddev,
        "min_ms": min(values),
        "max_ms": max(values),
        "ci95_low_ms": mean - ci,
        "ci95_high_ms": mean + ci,
    }


def read_completed_measurements(output_dir: Path) -> list[dict[str, str]]:
    path = output_dir / "capability_runtime_measurements.csv"
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("completed") == "true"]


def assert_reportable_measurements(rows: list[dict[str, str]]) -> None:
    ordered = [
        "experiment_start_ts_ns",
        "capability_request_ts_ns",
        "lifecycle_activation_request_ts_ns",
        "capability_executable_ts_ns",
        "first_bt_action_start_ts_ns",
        "last_bt_action_finish_ts_ns",
        "capability_completion_ts_ns",
        "deactivation_or_success_ts_ns",
        "experiment_end_ts_ns",
    ]
    for row in rows:
        missing_columns = [field for field in [*TIMESTAMP_FIELDS, *METRIC_FIELDS] if field not in row]
        if missing_columns:
            raise RuntimeError(
                f"Cannot generate report: run {row.get('run_id')} uses an incompatible measurement schema; "
                f"missing columns {missing_columns}. Use a fresh output directory or archive old CSVs."
            )
        for metric in METRIC_FIELDS:
            value = row.get(metric)
            if value in (None, ""):
                continue
            if float(value) < 0.0:
                timestamps = {field: row.get(field, "") for field in TIMESTAMP_FIELDS}
                raise RuntimeError(
                    f"Cannot generate report: negative metric {metric}={value} in run {row.get('run_id')}. "
                    f"timestamps={timestamps}"
                )
        seen = [(field, int(row[field])) for field in ordered if row.get(field) not in (None, "")]
        for (prev_field, prev_ts), (field, ts) in zip(seen, seen[1:]):
            if ts < prev_ts:
                timestamps = {name: row.get(name, "") for name in TIMESTAMP_FIELDS}
                raise RuntimeError(
                    f"Cannot generate report: chronological inconsistency in run {row.get('run_id')}: "
                    f"{field}={ts} < {prev_field}={prev_ts}. timestamps={timestamps}"
                )


def write_metric_summary(output_dir: Path) -> list[dict[str, object]]:
    rows = read_completed_measurements(output_dir)
    assert_reportable_measurements(rows)
    summary_rows: list[dict[str, object]] = []
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["architecture"], row["capability"])].append(row)

    for (architecture, capability), items in sorted(grouped.items()):
        for metric in METRIC_FIELDS:
            values = [float(item[metric]) for item in items if item.get(metric) not in (None, "")]
            if values:
                summary_rows.append({"architecture": architecture, "capability": capability, "metric": metric, **stats(values)})

    summary_path = output_dir / "capability_runtime_summary.csv"
    with summary_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary_rows)
    return summary_rows


def write_resource_overall_summary(output_dir: Path) -> list[dict[str, object]]:
    path = output_dir / "resource_summary.csv"
    if not path.exists():
        return []
    with path.open(newline="") as f:
        rows = [row for row in csv.DictReader(f) if row.get("scope") == "run_total"]
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["architecture"], row["capability"])].append(row)
    fields = ["architecture", "capability", "metric", "count", "mean", "peak"]
    out_rows: list[dict[str, object]] = []
    metric_pairs = [
        ("cpu_percent", "mean_cpu_percent", "peak_cpu_percent"),
        ("rss_mb", "mean_rss_mb", "peak_rss_mb"),
        ("thread_count", "mean_thread_count", "peak_thread_count"),
        ("ros2_process_count", "mean_ros2_process_count", "peak_ros2_process_count"),
    ]
    for (architecture, capability), items in sorted(grouped.items()):
        for label, mean_field, peak_field in metric_pairs:
            out_rows.append({
                "architecture": architecture,
                "capability": capability,
                "metric": label,
                "count": len(items),
                "mean": statistics.mean(float(row[mean_field]) for row in items),
                "peak": max(float(row[peak_field]) for row in items),
            })
    out = output_dir / "resource_overall_summary.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out_rows)
    return out_rows


def generate_plots(output_dir: Path) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return []
    rows = read_completed_measurements(output_dir)
    if not rows:
        return []
    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    overhead_metrics = [
        "orchestrated_capability_startup_time_ms",
        "pure_lifecycle_activation_time_ms",
        "capability_initialization_time_ms",
        "completion_deactivation_overhead_ms",
        "total_capability_duration_ms",
    ]
    for metric in overhead_metrics:
        labels = []
        data = []
        for architecture in ["bt", "modular"]:
            values = [float(row[metric]) for row in rows if row["architecture"] == architecture and row.get(metric) not in (None, "")]
            if values:
                labels.append(architecture)
                data.append(values)
        if not data:
            continue
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.boxplot(data, labels=labels, showmeans=True)
        ax.set_ylabel("ms")
        ax.set_title(metric)
        ax.grid(axis="y", alpha=0.3)
        path = plot_dir / f"{metric}.png"
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)
        paths.append(str(path.relative_to(output_dir)))
    return paths


def write_report(output_dir: Path, args: argparse.Namespace) -> None:
    summary_rows = write_metric_summary(output_dir)
    resource_rows = write_resource_overall_summary(output_dir) if args.resource_monitoring else []
    plot_paths = generate_plots(output_dir)
    measurements = read_completed_measurements(output_dir)
    completed_for_config = [
        row for row in measurements
        if row["architecture"] == args.architecture and row["capability"] == args.capability
    ]
    lines = [
        "# Capability Runtime Overhead Report",
        "",
        "## Experiment Configuration",
        "",
        f"- Architecture: `{args.architecture}`",
        f"- Capability: `{args.capability}`",
        f"- Requested runs: `{args.runs}`",
        f"- Completed runs for this configuration: `{len(completed_for_config)}`",
        f"- Failure mode: `{args.failure_mode}`",
        f"- Resource monitoring: `{args.resource_monitoring}`",
        f"- Output directory: `{output_dir}`",
        "",
        "Timing metrics separate orchestration startup, pure lifecycle activation, capability initialization, functional capability execution, and completion/deactivation. Robot navigation, speech synthesis, perception, user waiting, and task-specific waiting are bracketed by the executable BT action markers and contribute only to `capability_execution_time_ms`.",
        "",
        "Resource measurements report resource usage overhead for the selected architecture during each capability run; they are not timing metrics.",
        "",
        "## Metric Definitions",
        "",
        "- `orchestrated_capability_startup_time_ms`: experiment capability request to capability executable. In modular runs this includes master configure/activate, lifecycle client setup, service waits, module state lookup, and module activation until ACTIVE. In BT runs this is request to first tick entering the selected capability subtree.",
        "- `pure_lifecycle_activation_time_ms`: modular-only interval from immediately before sending `ChangeState(TRANSITION_ACTIVATE)` to the selected module until the `lifecycle_activated` event is emitted. This excludes master startup and orchestration preparation.",
        "- `capability_initialization_time_ms`: ACTIVE/executable boundary to first executable BT action.",
        "- `capability_execution_time_ms`: first executable BT action to last executable BT action. This is functional robot behavior, not architectural overhead.",
        "- `completion_deactivation_overhead_ms`: last executable BT action to completion/deactivation/control release.",
        "",
        "## Metric Summary",
        "",
        "| Architecture | Capability | Metric | N | Mean ms | Median ms | Stddev ms | Min ms | Max ms | 95% CI ms |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            f"| `{row['architecture']}` | `{row['capability']}` | `{row['metric']}` | {row['count']} | "
            f"{float(row['mean_ms']):.3f} | {float(row['median_ms']):.3f} | {float(row['stddev_ms']):.3f} | "
            f"{float(row['min_ms']):.3f} | {float(row['max_ms']):.3f} | "
            f"[{float(row['ci95_low_ms']):.3f}, {float(row['ci95_high_ms']):.3f}] |"
        )

    lines.extend(["", "## BT vs Modular Comparison", "", "| Capability | Metric | BT mean ms | Modular mean ms | Modular - BT ms |", "|---|---|---:|---:|---:|"])
    by_key = {(row["architecture"], row["capability"], row["metric"]): row for row in summary_rows}
    capabilities = sorted({row["capability"] for row in summary_rows})
    for capability in capabilities:
        for metric in METRIC_FIELDS:
            bt = by_key.get(("bt", capability, metric))
            mod = by_key.get(("modular", capability, metric))
            if not bt and not mod:
                continue
            bt_mean = float(bt["mean_ms"]) if bt else math.nan
            mod_mean = float(mod["mean_ms"]) if mod else math.nan
            delta = mod_mean - bt_mean if bt and mod else math.nan
            lines.append(f"| `{capability}` | `{metric}` | {bt_mean:.3f} | {mod_mean:.3f} | {delta:.3f} |")

    if resource_rows:
        lines.extend(["", "## Resource Summary", "", "| Architecture | Capability | Metric | N | Mean | Peak |", "|---|---|---|---:|---:|---:|"])
        for row in resource_rows:
            lines.append(f"| `{row['architecture']}` | `{row['capability']}` | `{row['metric']}` | {row['count']} | {float(row['mean']):.3f} | {float(row['peak']):.3f} |")

    invalid_path = output_dir / "invalid_runtime_runs.csv"
    if invalid_path.exists():
        with invalid_path.open(newline="") as f:
            invalid_rows = list(csv.DictReader(f))
        if invalid_rows:
            lines.extend(["", "## Invalid Runs", "", "| Run | Architecture | Capability | Reason | Diagnostic |", "|---|---|---|---|---|"])
            for row in invalid_rows[-20:]:
                diagnostic = str(row.get("diagnostic", "")).replace("|", "\\|")
                lines.append(f"| `{row.get('run_id', '')}` | `{row.get('architecture', '')}` | `{row.get('capability', '')}` | `{row.get('reason', '')}` | {diagnostic} |")

    if plot_paths:
        lines.extend(["", "## Plots", ""])
        for path in plot_paths:
            lines.append(f"![{path}]({path})")

    lines.extend([
        "",
        "## Interpretation",
        "",
        "Use `orchestrated_capability_startup_time_ms` for end-to-end capability startup from the experiment request to executability. Use `pure_lifecycle_activation_time_ms` for the isolated ROS 2 lifecycle activation service cost. Use `capability_initialization_time_ms` to quantify initialization after the module/subtree is executable but before behavior starts. Use `completion_deactivation_overhead_ms` for completion signaling and control release. Use `capability_execution_time_ms` only to compare equivalent functional robot behavior boundaries; it is not architectural overhead.",
    ])
    (output_dir / "summary_report.md").write_text("\n".join(lines) + "\n")


def ensure_runtime_bts() -> None:
    generator = PACKAGE / "scripts" / "generate_runtime_instrumented_bts.py"
    subprocess.run([sys.executable, str(generator), "--output-dir", str(RUNTIME_BT_DIR)], check=True)


def write_isolated_params(path: Path, capability_key: str, failure_mode: bool) -> None:
    info = CAPABILITIES[capability_key]
    module_name = info["module"]
    text = (PACKAGE / "config" / "params.yaml").read_text()
    text = text.replace("flows: [flow_1]", "flows: [runtime_flow]")
    text = text.replace(
        "flow_1: [greeting_guest_cognitive_module, find_seat_cognitive_module, describe_person_cognitive_module]",
        f"runtime_flow: [{module_name}]",
    )
    text = text.replace("on_startup: [greeting_guest_cognitive_module]", f"on_startup: [{module_name}]")
    if failure_mode:
        text = text.replace("module_retries_before_recovery: 2", "module_retries_before_recovery: 0")
    for cap in CAPABILITIES.values():
        text = text.replace(f"bt_name: '{cap['bt_file']}'", f"bt_name: 'runtime_instrumented/runtime_{cap['bt_file']}'")
    path.write_text(text)


def ros_env(output_dir: Path, run_id: str, architecture: str, failure_mode: bool) -> dict[str, str]:
    env = os.environ.copy()
    env["HRI_RUNTIME_EVAL_RUN_ID"] = run_id
    env["HRI_RUNTIME_EVAL_ARCHITECTURE"] = architecture
    env["HRI_RUNTIME_EVAL_DIR"] = str(output_dir)
    env["HRI_RUNTIME_EVAL_FAILURE_MODE"] = "1" if failure_mode else "0"
    return env


def run_bt(args: argparse.Namespace, run_id: str, output_dir: Path) -> dict[str, object]:
    env = ros_env(output_dir, run_id, "bt", args.failure_mode)
    bt_name = f"runtime_instrumented/runtime_bt_{args.capability}.xml"
    command = ["ros2", "run", "cs4home_hri_challenge", "hri_challenge_bt", "--ros-args", "-p", f"bt_xml_file:={bt_name}", "--params-file", str(PACKAGE / "config" / "params.yaml")]
    start_ns = time.time_ns()
    request_ns = time.time_ns()
    process = subprocess.Popen(command, env=env, start_new_session=True)
    monitor = ResourceMonitor(output_dir, run_id, "bt", args.capability, args.sample_period_sec) if args.resource_monitoring else None
    try:
        deadline = time.monotonic() + args.timeout_sec
        while process.poll() is None and time.monotonic() < deadline:
            if monitor:
                monitor.maybe_sample([process.pid])
            time.sleep(0.05)
        if process.poll() is None:
            terminate_processes([process])
    finally:
        end_ns = time.time_ns()
        if monitor:
            monitor.sample([process.pid])
            monitor.write_summary()
        if process.poll() is None:
            terminate_processes([process])
    events = read_run_events(output_dir, run_id)
    return build_row(args, run_id, "bt", start_ns, request_ns, end_ns, process.returncode, process.returncode == 0, events)


def wait_for_event(output_dir: Path, run_id: str, event_names: set[str], capability_label: str | None = None) -> bool:
    return first_event_ts(read_run_events(output_dir, run_id), event_names, capability_label) is not None


def run_modular(args: argparse.Namespace, run_id: str, output_dir: Path) -> dict[str, object]:
    info = CAPABILITIES[args.capability]
    env = ros_env(output_dir, run_id, "modular", args.failure_mode)
    with tempfile.TemporaryDirectory(prefix="hri_runtime_") as tmp:
        params_path = Path(tmp) / "isolated_params.yaml"
        write_isolated_params(params_path, args.capability, args.failure_mode)
        module_process = subprocess.Popen(["ros2", "run", "cs4home_hri_challenge", info["executable"], "--ros-args", "--params-file", str(params_path)], env=env, start_new_session=True)
        master_process = subprocess.Popen(["ros2", "run", "cs4home_hri_challenge", "hri_challenge_master", "--ros-args", "--params-file", str(params_path)], env=env, start_new_session=True)
        processes = [module_process, master_process]
        monitor = ResourceMonitor(output_dir, run_id, "modular", args.capability, args.sample_period_sec) if args.resource_monitoring else None
        start_ns = time.time_ns()
        completed = False
        failure_injected = False
        return_code: int | str = ""
        try:
            time.sleep(args.startup_wait_sec)
            request_ns = time.time_ns()
            subprocess.run(["ros2", "lifecycle", "set", "/hri_challenge_master", "configure"], env=env, timeout=10, check=False)
            subprocess.run(["ros2", "lifecycle", "set", "/hri_challenge_master", "activate"], env=env, timeout=10, check=False)
            deadline = time.monotonic() + args.timeout_sec
            while time.monotonic() < deadline:
                if monitor:
                    monitor.maybe_sample([p.pid for p in processes])
                if args.failure_mode and not failure_injected and wait_for_event(output_dir, run_id, {"lifecycle_activated"}, info["label"]):
                    subprocess.run(["ros2", "lifecycle", "set", f"/{info['module']}", "deactivate"], env=env, timeout=10, check=False)
                    failure_injected = True
                done_events = {"recovery_completion"} if args.failure_mode else {"lifecycle_deactivated"}
                done_label = None if args.failure_mode else info["label"]
                if wait_for_event(output_dir, run_id, done_events, done_label):
                    completed = True
                    break
                if any(p.poll() not in (None, 0) for p in processes):
                    break
                time.sleep(0.1)
            return_code = 0 if completed else next((p.returncode for p in processes if p.returncode not in (None, 0)), "timeout")
        finally:
            end_ns = time.time_ns()
            if monitor:
                monitor.sample([p.pid for p in processes])
                monitor.write_summary()
            terminate_processes(processes)
    events = read_run_events(output_dir, run_id)
    return build_row(args, run_id, "modular", start_ns, request_ns, end_ns, return_code, completed, events)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run capability-level architecture overhead experiments.")
    parser.add_argument("--architecture", required=True, choices=["bt", "modular"])
    parser.add_argument("--capability", required=True, choices=sorted(CAPABILITIES))
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--failure-mode", action="store_true")
    parser.add_argument("--resource-monitoring", action="store_true")
    parser.add_argument("--resource-monitor", dest="resource_monitoring", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--timeout-sec", type=float, default=300.0)
    parser.add_argument("--startup-wait-sec", type=float, default=2.0)
    parser.add_argument("--sample-period-sec", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_runtime_bts()

    completed_rows = 0
    interrupted = False
    session_id = time.strftime("%Y%m%d_%H%M%S")
    try:
        for run_index in range(args.runs):
            run_id = f"{args.architecture}_{args.capability}_{session_id}_{run_index:03d}"
            print(f"[{run_index + 1}/{args.runs}] {args.architecture} {args.capability}", flush=True)
            row = run_bt(args, run_id, output_dir) if args.architecture == "bt" else run_modular(args, run_id, output_dir)
            if row.get("_invalid_reason"):
                invalid_row = {
                    **{field: row.get(field, "") for field in INVALID_RUN_FIELDS},
                    "reason": row.get("_invalid_reason", ""),
                    "diagnostic": row.get("_invalid_diagnostic", ""),
                }
                append_csv(output_dir / "invalid_runtime_runs.csv", INVALID_RUN_FIELDS, invalid_row)
                print(f"Invalid run excluded: {run_id}: {row.get('_invalid_diagnostic')}", flush=True)
            else:
                append_csv(output_dir / "capability_runtime_measurements.csv", MEASUREMENT_FIELDS, row)
                if row["completed"] == "true":
                    completed_rows += 1
            write_report(output_dir, args)
    except KeyboardInterrupt:
        interrupted = True
        print("Interrupted. Preserving collected runs and generating summaries...", flush=True)
    finally:
        write_report(output_dir, args)
        status = "interrupted" if interrupted else "finished"
        print(f"Experiment {status}. Completed rows this invocation: {completed_rows}", flush=True)
        print(f"Results: {output_dir}", flush=True)


if __name__ == "__main__":
    main()
