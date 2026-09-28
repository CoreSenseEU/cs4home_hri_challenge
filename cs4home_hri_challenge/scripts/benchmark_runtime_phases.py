#!/usr/bin/env python3
"""Benchmark runtime phases and resources for BT and modular capabilities.

The script does not modify capability behavior. It runs the existing runtime-
instrumented BT artifacts, records trace timestamps emitted by the application,
and assigns resource samples to the resulting phase windows.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


def package_dir() -> Path:
    source_layout = Path(__file__).resolve().parents[1]
    if (source_layout / "bt_xml").exists():
        return source_layout
    from ament_index_python.packages import get_package_share_directory
    return Path(get_package_share_directory("cs4home_hri_challenge"))


PACKAGE = package_dir()
DEFAULT_OUTPUT_DIR = PACKAGE / "data" / "runtime_phase_benchmark"
RUNTIME_BT_DIR = PACKAGE / "bt_xml" / "runtime_instrumented"

CAPABILITIES = {
    "greeting": {
        "label": "Greeting",
        "module": "greeting_guest_cognitive_module",
        "executable": "greeting_guest_cognitive_module",
        "bt_file": "greeting_guest.xml",
    },
    "describe_person": {
        "label": "Describe / Invite",
        "module": "describe_person_cognitive_module",
        "executable": "describe_person_cognitive_module",
        "bt_file": "describe_person.xml",
    },
    "introduce_guest": {
        "label": "Introduce Guest",
        "module": "introduce_guest_cognitive_module",
        "executable": "introduce_guest_cognitive_module",
        "bt_file": "introduce_guest.xml",
    },
    "find_seat": {
        "label": "Find Seat",
        "module": "find_seat_cognitive_module",
        "executable": "find_seat_cognitive_module",
        "bt_file": "find_seat.xml",
    },
    "grab_bag": {
        "label": "Grab Bag",
        "module": "grab_bag_cognitive_module",
        "executable": "grab_bag_cognitive_module",
        "bt_file": "grab_bag.xml",
    },
    "transport_bag": {
        "label": "Transport Bag",
        "module": "transport_bag_cognitive_module",
        "executable": "transport_bag_cognitive_module",
        "bt_file": "transport_bag.xml",
    },
    "recovery": {
        "label": "Recovery",
        "module": "recovery_cognitive_module",
        "executable": "recovery_cognitive_module",
        "bt_file": "recovery.xml",
    },
}

RAW_FIELDS = [
    "run_id",
    "architecture",
    "capability",
    "window_type",
    "phase",
    "process_role",
    "timestamp_ns",
    "cpu_percent",
    "rss_mb",
    "pss_mb",
    "energy_j",
    "energy_source",
    "pid",
    "process_name",
    "process_count",
    "thread_count",
    "sample_reliable",
]

SUMMARY_FIELDS = [
    "run_id",
    "architecture",
    "capability",
    "phase",
    "window_type",
    "process_role",
    "start_timestamp",
    "end_timestamp",
    "duration_ms",
    "mean_cpu",
    "peak_cpu",
    "mean_rss",
    "peak_rss",
    "mean_pss",
    "peak_pss",
    "energy_j",
    "energy_source",
    "process_count",
    "thread_count",
    "sample_count",
    "sample_reliable",
]

EVENT_FIELDS = ["run_id", "architecture", "capability", "event", "timestamp_ns", "relative_ms"]


def append_csv(path: Path, fields: list[str], row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})


def read_total_jiffies() -> int:
    with Path("/proc/stat").open() as f:
        return sum(int(value) for value in f.readline().split()[1:])


def read_process_sample(pid: int, include_pss: bool) -> dict[str, object] | None:
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

    pss_kb: int | None = None
    if include_pss:
        try:
            for line in (proc_dir / "smaps_rollup").read_text().splitlines():
                if line.startswith("Pss:"):
                    pss_kb = int(line.split()[1])
                    break
        except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
            pass

    return {
        "pid": pid,
        "process_name": comm,
        "cpu_jiffies": int(stat_parts[13]) + int(stat_parts[14]),
        "rss_mb": rss_kb / 1024.0,
        "pss_mb": pss_kb / 1024.0 if pss_kb is not None else "",
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


def descendant_role_map(root_roles: dict[int, str]) -> dict[int, str]:
    parents = process_parent_map()
    children: dict[int, list[int]] = defaultdict(list)
    for pid, ppid in parents.items():
        children[ppid].append(pid)

    roles: dict[int, str] = {}
    for root_pid, role in root_roles.items():
        stack = [root_pid]
        while stack:
            pid = stack.pop()
            if pid in roles:
                continue
            roles[pid] = role
            stack.extend(children.get(pid, []))
    return roles


@dataclass
class EnergyReading:
    timestamp_ns: int
    joules: float


@dataclass(frozen=True)
class Window:
    name: str
    start_ns: int
    end_ns: int
    window_type: str = "phase"


class EnergyMeter:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.power_path: Path | None = None
        self.battery_dir: Path | None = None
        self.name = "disabled"
        self.reason = "No readable processor or battery energy interface found."
        self.max_joules: float | None = None
        self.source_kind = "disabled"
        self._battery_last_timestamp_ns: int | None = None
        self._battery_last_power_w: float | None = None
        self._integrated_last_timestamp_ns: int | None = None
        self._integrated_last_power_w: float | None = None
        self._integrated_consumed_j = 0.0
        self._discover()

    def _discover(self) -> None:
        if self._discover_powercap():
            return
        if self._discover_hwmon_processor():
            return
        self._discover_battery()

    def _discover_battery(self) -> bool:
        root = Path("/sys/class/power_supply")
        if not root.exists():
            self.reason = "No power_supply sysfs interface found."
            return False

        for path in sorted(root.iterdir()):
            try:
                supply_type = (path / "type").read_text().strip()
            except (FileNotFoundError, PermissionError, OSError):
                continue
            if supply_type != "Battery":
                continue
            if self._read_battery_power_w(path) is None:
                self.reason = f"Battery interface exists but cannot provide discharge power: {path}"
                continue

            self.battery_dir = path
            self.name = f"laptop_battery_total:{path.name}"
            self.source_kind = "battery_total"
            self.reason = "enabled"
            return True
        return False

    def _discover_hwmon_processor(self) -> bool:
        root = Path("/sys/class/hwmon")
        if not root.exists():
            return False

        processor_names = ("amd_energy", "zenpower", "k10temp", "rapl", "cpu", "processor", "coretemp")
        excluded_names = ("amdgpu", "gpu", "iwlwifi", "nvme", "asus", "battery", "ucsi")
        for hwmon in sorted(root.iterdir()):
            try:
                name = (hwmon / "name").read_text().strip().lower()
            except (FileNotFoundError, PermissionError, OSError):
                continue
            if any(token in name for token in excluded_names):
                continue
            if not any(token in name for token in processor_names):
                continue

            for energy_path in sorted(hwmon.glob("energy*_input")):
                try:
                    int(energy_path.read_text().strip())
                except (FileNotFoundError, PermissionError, ValueError, OSError):
                    continue
                self.path = energy_path
                self.name = f"processor_hwmon:{name}:{energy_path.name}"
                self.source_kind = "processor"
                self.reason = "enabled"
                return True

            power_candidates = sorted(hwmon.glob("power*_average")) + sorted(hwmon.glob("power*_input"))
            for power_path in power_candidates:
                try:
                    int(power_path.read_text().strip())
                except (FileNotFoundError, PermissionError, ValueError, OSError):
                    continue
                label_path = power_path.with_name(power_path.name.replace("_average", "_label").replace("_input", "_label"))
                label = ""
                if label_path.exists():
                    try:
                        label = label_path.read_text().strip().lower()
                    except OSError:
                        pass
                self.power_path = power_path
                self.name = f"processor_hwmon:{name}:{label or power_path.name}"
                self.source_kind = "processor_power_integrated"
                self.reason = "enabled"
                return True
        return False

    def _discover_powercap(self) -> bool:
        candidates = []
        for root in [Path("/sys/class/powercap"), Path("/sys/devices/virtual/powercap")]:
            if root.exists():
                candidates.extend(root.rglob("energy_uj"))

        for path in sorted(set(candidates)):
            try:
                int(path.read_text().strip())
            except PermissionError:
                self.reason = f"Energy interface exists but is not readable: {path}"
                continue
            except (FileNotFoundError, ValueError, OSError):
                continue

            name_path = path.with_name("name")
            max_path = path.with_name("max_energy_range_uj")
            name = path.parent.name
            if name_path.exists():
                try:
                    name = name_path.read_text().strip()
                except OSError:
                    pass
            max_joules = None
            if max_path.exists():
                try:
                    max_joules = int(max_path.read_text().strip()) / 1_000_000.0
                except (ValueError, OSError):
                    pass
            self.path = path
            self.name = f"processor:{name}"
            self.max_joules = max_joules
            self.source_kind = "processor"
            self.reason = "enabled"
            return True
        return False

    @property
    def enabled(self) -> bool:
        return self.path is not None or self.power_path is not None or self.battery_dir is not None

    def _integrate_power(self, timestamp_ns: int, power_w: float) -> EnergyReading:
        if self._integrated_last_timestamp_ns is not None and self._integrated_last_power_w is not None:
            elapsed_sec = (timestamp_ns - self._integrated_last_timestamp_ns) / 1_000_000_000.0
            if elapsed_sec >= 0:
                self._integrated_consumed_j += ((self._integrated_last_power_w + power_w) / 2.0) * elapsed_sec
        self._integrated_last_timestamp_ns = timestamp_ns
        self._integrated_last_power_w = power_w
        return EnergyReading(timestamp_ns, self._integrated_consumed_j)

    def _read_battery_power_w(self, battery_dir: Path) -> float | None:
        try:
            status = (battery_dir / "status").read_text().strip()
        except (FileNotFoundError, PermissionError, OSError):
            return None
        if status != "Discharging":
            return None

        power_path = battery_dir / "power_now"
        if power_path.exists():
            try:
                return int(power_path.read_text().strip()) / 1_000_000.0
            except (FileNotFoundError, PermissionError, ValueError, OSError):
                return None

        try:
            voltage_v = int((battery_dir / "voltage_now").read_text().strip()) / 1_000_000.0
            current_a = int((battery_dir / "current_now").read_text().strip()) / 1_000_000.0
        except (FileNotFoundError, PermissionError, ValueError, OSError):
            return None
        return voltage_v * current_a

    def read(self) -> EnergyReading | None:
        if self.battery_dir is not None:
            timestamp_ns = time.time_ns()
            power_w = self._read_battery_power_w(self.battery_dir)
            if power_w is None:
                return None
            return self._integrate_power(timestamp_ns, power_w)

        if self.power_path is not None:
            timestamp_ns = time.time_ns()
            try:
                power_w = int(self.power_path.read_text().strip()) / 1_000_000.0
            except (FileNotFoundError, PermissionError, ValueError, OSError):
                return None
            return self._integrate_power(timestamp_ns, power_w)

        if self.path is None:
            return None
        try:
            return EnergyReading(time.time_ns(), int(self.path.read_text().strip()) / 1_000_000.0)
        except (FileNotFoundError, PermissionError, ValueError, OSError):
            return None

    def delta(self, start: EnergyReading | None, end: EnergyReading | None) -> float | str:
        if start is None or end is None:
            return ""
        value = end.joules - start.joules
        if value < 0 and self.max_joules is not None:
            value = (self.max_joules - start.joules) + end.joules
        return max(0.0, value)


class ResourceMonitor:
    def __init__(
        self,
        sample_period_sec: float,
        pss_period_sec: float,
        energy_meter: EnergyMeter,
        root_roles: dict[int, str] | None = None,
    ) -> None:
        self.sample_period_sec = sample_period_sec
        self.pss_period_sec = pss_period_sec
        self.energy_meter = energy_meter
        self.previous_total = read_total_jiffies()
        self.previous_proc: dict[int, int] = {}
        self.previous_pss: dict[int, object] = {}
        self.last_pss_sample_sec = 0.0
        self.root_roles = dict(root_roles or {})
        self.samples: list[dict[str, object]] = []
        self.energy_samples: list[EnergyReading] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def set_root_roles(self, root_roles: dict[int, str]) -> None:
        with self._lock:
            self.root_roles = dict(root_roles)

    def start(self) -> None:
        self.sample()
        self._thread = threading.Thread(target=self._run, name="resource-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.sample_period_sec * 2.0))
        self.sample()

    def _run(self) -> None:
        while not self._stop.wait(self.sample_period_sec):
            self.sample()

    def sample(self) -> None:
        stamp_ns = time.time_ns()
        now = time.monotonic()
        include_pss = now - self.last_pss_sample_sec >= self.pss_period_sec
        if include_pss:
            self.last_pss_sample_sec = now
        cpu_count = os.cpu_count() or 1
        current_total = read_total_jiffies()
        total_delta = max(1, current_total - self.previous_total)
        current_proc: dict[int, int] = {}
        energy = self.energy_meter.read()
        with self._lock:
            root_roles = dict(self.root_roles)
        pid_roles = descendant_role_map(root_roles)
        sample_rows = []

        for pid, role in sorted(pid_roles.items()):
            sample = read_process_sample(pid, include_pss)
            if sample is None:
                continue
            if sample["pss_mb"] == "":
                sample["pss_mb"] = self.previous_pss.get(pid, "")
            elif include_pss:
                self.previous_pss[pid] = sample["pss_mb"]
            current_proc[pid] = int(sample["cpu_jiffies"])
            prev_jiffies = self.previous_proc.get(pid, current_proc[pid])
            cpu_percent = ((current_proc[pid] - prev_jiffies) / total_delta) * cpu_count * 100.0
            sample_rows.append(
                {
                    "timestamp_ns": stamp_ns,
                    "pid": pid,
                    "process_role": role,
                    "process_name": sample["process_name"],
                    "cpu_percent": max(0.0, cpu_percent),
                    "rss_mb": sample["rss_mb"],
                    "pss_mb": sample["pss_mb"],
                    "thread_count": sample["thread_count"],
                }
            )

        with self._lock:
            if energy is not None:
                self.energy_samples.append(energy)
            self.samples.extend(sample_rows)
            self.previous_total = current_total
            self.previous_proc = current_proc

    def snapshot(self) -> tuple[list[dict[str, object]], list[EnergyReading]]:
        with self._lock:
            return list(self.samples), list(self.energy_samples)

    def energy_at_or_after(self, timestamp_ns: int) -> EnergyReading | None:
        _, energy_samples = self.snapshot()
        for reading in energy_samples:
            if reading.timestamp_ns >= timestamp_ns:
                return reading
        return None

    def energy_at_or_before(self, timestamp_ns: int) -> EnergyReading | None:
        _, energy_samples = self.snapshot()
        for reading in reversed(energy_samples):
            if reading.timestamp_ns <= timestamp_ns:
                return reading
        return None


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


def first_event_ts(events: list[dict[str, str]], names: set[str], capability: str | None = None) -> int | None:
    for event in events:
        if event.get("event") not in names:
            continue
        if capability is not None and event.get("capability") != capability:
            continue
        return int(event["stamp_ns"])
    return None


def last_event_ts(events: list[dict[str, str]], names: set[str], capability: str | None = None) -> int | None:
    for event in reversed(events):
        if event.get("event") not in names:
            continue
        if capability is not None and event.get("capability") != capability:
            continue
        return int(event["stamp_ns"])
    return None


def phase_windows(
    architecture: str,
    capability_label: str,
    events: list[dict[str, str]],
    idle_start_ns: int,
    activation_start_ns: int,
    end_ns: int,
) -> list[Window]:
    executable = first_event_ts(events, {"capability_executable"}, capability_label)
    lifecycle_request = None
    lifecycle_activated = None
    if architecture == "modular":
        lifecycle_request = first_event_ts(events, {"lifecycle_activation_request"}, capability_label)
        lifecycle_activated = first_event_ts(events, {"lifecycle_activated"}, capability_label)
        executable = lifecycle_activated or executable
    first_action = first_event_ts(events, {"first_bt_action_start"}, capability_label)
    last_action = last_event_ts(events, {"last_bt_action_finish", "capability_finished_marker"}, capability_label)
    completion_received = first_event_ts(events, {"completion_received"}, capability_label)
    capability_finished = first_event_ts(events, {"capability_finished"}, capability_label)
    completion = completion_received or capability_finished
    lifecycle_deactivated = last_event_ts(events, {"lifecycle_deactivated"}, capability_label)
    transition_to_next = last_event_ts(events, {"transition_to_next"}, capability_label)
    run_end = lifecycle_deactivated or transition_to_next or completion or end_ns

    boundaries = []
    if architecture == "modular":
        boundaries.append(("modular_idle_footprint", idle_start_ns, activation_start_ns))
        boundaries.append(("lifecycle_activation", lifecycle_request, lifecycle_activated))
        boundaries.append(("initialization", lifecycle_activated, first_action))
    else:
        boundaries.append(("bt_setup_pre_execution", activation_start_ns, first_action or executable))
    boundaries.extend(
        [
            ("execution", first_action, last_action),
            ("completion_propagation", last_action, completion),
        ]
    )
    if architecture == "modular":
        boundaries.append(("lifecycle_deactivation", completion_received, lifecycle_deactivated))
    else:
        boundaries.append(("post_completion", completion, transition_to_next))
    windows = [Window(name, start, end, "phase") for name, start, end in boundaries if start is not None and end is not None and end >= start]
    if first_action is not None and first_action >= activation_start_ns:
        windows.append(Window("pre_execution", activation_start_ns, first_action, "comparable"))
    if run_end >= activation_start_ns:
        windows.append(Window("e2e_active", activation_start_ns, run_end, "e2e"))
    if first_action is not None and completion is not None and completion >= first_action:
        windows.append(Window("e2e_capability", first_action, completion, "e2e"))
    if architecture == "modular" and run_end >= idle_start_ns:
        windows.append(Window("e2e_with_modular_idle", idle_start_ns, run_end, "e2e"))
    return windows


def write_phase_outputs(
    output_dir: Path,
    run_id: str,
    architecture: str,
    capability: str,
    monitor: ResourceMonitor,
    windows: list[Window],
    energy_meter: EnergyMeter,
) -> None:
    raw_path = output_dir / "phase_resource_samples.csv"
    summary_path = output_dir / "phase_resource_summary.csv"
    min_samples_for_cpu = 2
    all_samples, energy_samples = monitor.snapshot()

    def energy_at_or_after(timestamp_ns: int) -> EnergyReading | None:
        for reading in energy_samples:
            if reading.timestamp_ns >= timestamp_ns:
                return reading
        return None

    def energy_at_or_before(timestamp_ns: int) -> EnergyReading | None:
        for reading in reversed(energy_samples):
            if reading.timestamp_ns <= timestamp_ns:
                return reading
        return None

    for window in windows:
        phase = window.name
        start_ns = window.start_ns
        end_ns = window.end_ns
        phase_samples = [s for s in all_samples if start_ns <= int(s["timestamp_ns"]) <= end_ns]
        by_process: dict[str, list[dict[str, object]]] = defaultdict(list)
        for sample in phase_samples:
            by_process[str(sample["process_role"])].append(sample)
            append_csv(
                raw_path,
                RAW_FIELDS,
                {
                    "run_id": run_id,
                    "architecture": architecture,
                    "capability": capability,
                    "window_type": window.window_type,
                    "phase": phase,
                    "process_role": sample["process_role"],
                    "timestamp_ns": sample["timestamp_ns"],
                    "cpu_percent": sample["cpu_percent"],
                    "rss_mb": sample["rss_mb"],
                    "pss_mb": sample["pss_mb"],
                    "energy_j": "",
                    "energy_source": energy_meter.name if energy_meter.enabled else "disabled",
                    "pid": sample["pid"],
                    "process_name": sample["process_name"],
                    "process_count": 1,
                    "thread_count": sample["thread_count"],
                    "sample_reliable": str(len({int(s["timestamp_ns"]) for s in phase_samples}) >= min_samples_for_cpu).lower(),
                },
            )

        timestamps = sorted({int(s["timestamp_ns"]) for s in phase_samples})
        role_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
        for role in sorted({str(s["process_role"]) for s in phase_samples}):
            for timestamp in timestamps:
                rows = [s for s in phase_samples if int(s["timestamp_ns"]) == timestamp and str(s["process_role"]) == role]
                if not rows:
                    continue
                pss_values = [float(row["pss_mb"]) for row in rows if row["pss_mb"] != ""]
                role_rows[role].append(
                    {
                        "timestamp_ns": timestamp,
                        "cpu_percent": sum(float(row["cpu_percent"]) for row in rows),
                        "rss_mb": sum(float(row["rss_mb"]) for row in rows),
                        "pss_mb": sum(pss_values) if pss_values else "",
                        "process_count": len({int(row["pid"]) for row in rows}),
                        "thread_count": sum(int(row["thread_count"]) for row in rows),
                    }
                )
        by_process = role_rows

        total_rows = []
        for timestamp in timestamps:
            rows = [s for s in phase_samples if int(s["timestamp_ns"]) == timestamp]
            pss_values = [float(row["pss_mb"]) for row in rows if row["pss_mb"] != ""]
            total_rows.append(
                {
                    "timestamp_ns": timestamp,
                    "cpu_percent": sum(float(row["cpu_percent"]) for row in rows),
                    "rss_mb": sum(float(row["rss_mb"]) for row in rows),
                    "pss_mb": sum(pss_values) if pss_values else "",
                    "process_count": len({int(row["pid"]) for row in rows}),
                    "thread_count": sum(int(row["thread_count"]) for row in rows),
                }
            )
        if total_rows:
            by_process["total_measured_processes"] = total_rows
            energy_start = energy_at_or_after(start_ns)
            energy_end = energy_at_or_before(end_ns)
            energy_delta = energy_meter.delta(energy_start, energy_end)
            for sample in total_rows:
                append_csv(
                    raw_path,
                    RAW_FIELDS,
                    {
                        "run_id": run_id,
                        "architecture": architecture,
                        "capability": capability,
                        "window_type": window.window_type,
                        "phase": phase,
                        "process_role": "total_measured_processes",
                        "timestamp_ns": sample["timestamp_ns"],
                        "cpu_percent": sample["cpu_percent"],
                        "rss_mb": sample["rss_mb"],
                        "pss_mb": sample["pss_mb"],
                        "energy_j": "",
                        "energy_source": energy_meter.name if energy_meter.enabled else "disabled",
                        "pid": "",
                        "process_name": "",
                        "process_count": sample["process_count"],
                        "thread_count": sample["thread_count"],
                        "sample_reliable": str(len(total_rows) >= min_samples_for_cpu).lower(),
                    },
                )
        else:
            energy_delta = ""

        for process, rows in sorted(by_process.items()):
            reliable = len(rows) >= min_samples_for_cpu
            cpus = [float(row["cpu_percent"]) for row in rows]
            rss = [float(row["rss_mb"]) for row in rows]
            pss = [float(row["pss_mb"]) for row in rows if row["pss_mb"] != ""]
            process_count = max((int(row.get("process_count", 1)) for row in rows), default=0)
            thread_count = max((int(row.get("thread_count", 0)) for row in rows), default=0)
            append_csv(
                summary_path,
                SUMMARY_FIELDS,
                {
                    "run_id": run_id,
                    "architecture": architecture,
                    "capability": capability,
                    "phase": phase,
                    "window_type": window.window_type,
                    "process_role": process,
                    "start_timestamp": start_ns,
                    "end_timestamp": end_ns,
                    "duration_ms": (end_ns - start_ns) / 1_000_000.0,
                    "mean_cpu": sum(cpus) / len(cpus) if reliable else "",
                    "peak_cpu": max(cpus) if reliable else "",
                    "mean_rss": sum(rss) / len(rss) if reliable else "",
                    "peak_rss": max(rss) if reliable else "",
                    "mean_pss": sum(pss) / len(pss) if reliable and pss else "",
                    "peak_pss": max(pss) if reliable and pss else "",
                    "energy_j": energy_delta if process == "total_measured_processes" and reliable else "",
                    "energy_source": energy_meter.name if energy_meter.enabled else "disabled",
                    "process_count": process_count,
                    "thread_count": thread_count,
                    "sample_count": len(rows),
                    "sample_reliable": str(reliable).lower(),
                },
            )

        if not by_process:
            energy_window_samples = [s for s in energy_samples if start_ns <= s.timestamp_ns <= end_ns]
            reliable = len(energy_window_samples) >= min_samples_for_cpu
            energy_delta = energy_meter.delta(energy_at_or_after(start_ns), energy_at_or_before(end_ns)) if reliable else ""
            append_csv(
                summary_path,
                SUMMARY_FIELDS,
                {
                    "run_id": run_id,
                    "architecture": architecture,
                    "capability": capability,
                    "phase": phase,
                    "window_type": window.window_type,
                    "process_role": "total_measured_processes",
                    "start_timestamp": start_ns,
                    "end_timestamp": end_ns,
                    "duration_ms": (end_ns - start_ns) / 1_000_000.0,
                    "mean_cpu": "",
                    "peak_cpu": "",
                    "mean_rss": "",
                    "peak_rss": "",
                    "mean_pss": "",
                    "peak_pss": "",
                    "energy_j": energy_delta,
                    "energy_source": energy_meter.name if energy_meter.enabled else "disabled",
                    "process_count": 0,
                    "thread_count": 0,
                    "sample_count": len(energy_window_samples),
                    "sample_reliable": str(reliable).lower(),
                },
            )


def write_phase_events(output_dir: Path, run_id: str, architecture: str, capability: str, windows: list[Window]) -> None:
    if not windows:
        return
    origin = min(window.start_ns for window in windows)
    event_points: list[tuple[str, int]] = []
    for window in windows:
        event_points.append((f"{window.name}_start", window.start_ns))
        event_points.append((f"{window.name}_end", window.end_ns))
    seen = set()
    for event, timestamp in sorted(event_points, key=lambda item: item[1]):
        key = (event, timestamp)
        if key in seen:
            continue
        seen.add(key)
        append_csv(
            output_dir / "phase_events.csv",
            EVENT_FIELDS,
            {
                "run_id": run_id,
                "architecture": architecture,
                "capability": capability,
                "event": event,
                "timestamp_ns": timestamp,
                "relative_ms": (timestamp - origin) / 1_000_000.0,
            },
        )


def ensure_runtime_bts() -> None:
    generator = PACKAGE / "scripts" / "generate_runtime_instrumented_bts.py"
    subprocess.run([sys.executable, str(generator), "--output-dir", str(RUNTIME_BT_DIR)], check=True)


def write_isolated_params(path: Path, capability_key: str) -> None:
    info = CAPABILITIES[capability_key]
    text = (PACKAGE / "config" / "params.yaml").read_text()
    text = text.replace("flows: [flow_1]", "flows: [runtime_flow]")
    text = text.replace(
        "flow_1: [greeting_guest_cognitive_module, find_seat_cognitive_module, describe_person_cognitive_module]",
        f"runtime_flow: [{info['module']}]",
    )
    text = text.replace("on_startup: [greeting_guest_cognitive_module]", f"on_startup: [{info['module']}]")
    for cap in CAPABILITIES.values():
        text = text.replace(f"bt_name: '{cap['bt_file']}'", f"bt_name: 'runtime_instrumented/runtime_{cap['bt_file']}'")
    path.write_text(text)


def ros_env(output_dir: Path, run_id: str, architecture: str) -> dict[str, str]:
    env = os.environ.copy()
    env["HRI_RUNTIME_EVAL_RUN_ID"] = run_id
    env["HRI_RUNTIME_EVAL_ARCHITECTURE"] = architecture
    env["HRI_RUNTIME_EVAL_DIR"] = str(output_dir)
    env["HRI_RUNTIME_EVAL_FAILURE_MODE"] = "0"
    return env


def run_bt(args: argparse.Namespace, run_id: str, output_dir: Path, energy_meter: EnergyMeter) -> None:
    info = CAPABILITIES[args.capability]
    env = ros_env(output_dir, run_id, "bt")
    bt_name = f"runtime_instrumented/runtime_bt_{args.capability}.xml"
    command = [
        "ros2", "run", "cs4home_hri_challenge", "hri_challenge_bt",
        "--ros-args", "-p", f"bt_xml_file:={bt_name}", "--params-file", str(PACKAGE / "config" / "params.yaml"),
    ]
    monitor = ResourceMonitor(args.sample_period_sec, args.pss_period_sec, energy_meter)
    activation_start_ns = time.time_ns()
    process = subprocess.Popen(command, env=env, start_new_session=True)
    monitor.set_root_roles({process.pid: "bt_executor"})
    monitor.start()
    try:
        deadline = time.monotonic() + args.timeout_sec
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(args.poll_period_sec)
        if process.poll() is None:
            terminate_processes([process])
    finally:
        end_ns = time.time_ns()
        monitor.stop()
        if process.poll() is None:
            terminate_processes([process])

    events = read_run_events(output_dir, run_id)
    windows = phase_windows("bt", info["label"], events, activation_start_ns, activation_start_ns, end_ns)
    write_phase_events(output_dir, run_id, "bt", args.capability, windows)
    write_phase_outputs(output_dir, run_id, "bt", args.capability, monitor, windows, energy_meter)


def run_modular(args: argparse.Namespace, run_id: str, output_dir: Path, energy_meter: EnergyMeter) -> None:
    info = CAPABILITIES[args.capability]
    env = ros_env(output_dir, run_id, "modular")
    with tempfile.TemporaryDirectory(prefix="hri_phase_bench_") as tmp:
        params_path = Path(tmp) / "isolated_params.yaml"
        write_isolated_params(params_path, args.capability)
        module_process = subprocess.Popen(
            ["ros2", "run", "cs4home_hri_challenge", info["executable"], "--ros-args", "--params-file", str(params_path)],
            env=env,
            start_new_session=True,
        )
        master_process = subprocess.Popen(
            ["ros2", "run", "cs4home_hri_challenge", "hri_challenge_master", "--ros-args", "--params-file", str(params_path)],
            env=env,
            start_new_session=True,
        )
        processes = [module_process, master_process]
        roles = {module_process.pid: "cognitive_module", master_process.pid: "hri_challenge_master"}
        monitor = ResourceMonitor(args.sample_period_sec, args.pss_period_sec, energy_meter, roles)
        idle_start_ns = time.time_ns()
        activation_start_ns = idle_start_ns
        try:
            time.sleep(args.startup_wait_sec)
            idle_start_ns = time.time_ns()
            monitor.start()
            time.sleep(args.idle_sec)
            activation_start_ns = time.time_ns()
            subprocess.run(["ros2", "lifecycle", "set", "/hri_challenge_master", "configure"], env=env, timeout=10, check=False)
            subprocess.run(["ros2", "lifecycle", "set", "/hri_challenge_master", "activate"], env=env, timeout=10, check=False)
            deadline = time.monotonic() + args.timeout_sec
            while time.monotonic() < deadline:
                events = read_run_events(output_dir, run_id)
                if first_event_ts(events, {"lifecycle_deactivated"}, info["label"]) is not None:
                    break
                if any(p.poll() not in (None, 0) for p in processes):
                    break
                time.sleep(args.poll_period_sec)
        finally:
            end_ns = time.time_ns()
            monitor.stop()
            terminate_processes(processes)

    events = read_run_events(output_dir, run_id)
    windows = phase_windows("modular", info["label"], events, idle_start_ns, activation_start_ns, end_ns)
    write_phase_events(output_dir, run_id, "modular", args.capability, windows)
    write_phase_outputs(output_dir, run_id, "modular", args.capability, monitor, windows, energy_meter)


def write_energy_report(output_dir: Path, energy_meter: EnergyMeter) -> None:
    lines = [
        "# Energy Measurement Status",
        "",
        f"- Enabled: `{str(energy_meter.enabled).lower()}`",
        f"- Source: `{energy_meter.name}`",
        f"- Reason/status: {energy_meter.reason}",
        "",
        "Energy is reported only for `total_measured_processes` because processor RAPL/powercap and battery readings are global measurements, not per-process energy attribution. Per-process CPU/RSS/PSS are still reported separately.",
        "The script prioritizes processor hardware counters from Linux RAPL/powercap `energy_uj` when readable, including AMD processor powercap interfaces if exposed by the kernel. It then checks CPU/processor `hwmon` energy or power sensors and integrates power over time when only instantaneous power is available.",
        "If processor energy is unavailable and the laptop battery is discharging, energy is estimated by integrating `/sys/class/power_supply/BAT*/power_now` or `voltage_now * current_now` over time. This fallback is labelled `laptop_battery_total:*` and represents total laptop battery draw, not CPU/package energy.",
    ]
    (output_dir / "energy_measurement_status.md").write_text("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark BT vs modular runtime phases with synchronized resources.")
    parser.add_argument("--architecture", required=True, choices=["bt", "modular", "both"])
    parser.add_argument("--capability", required=True, choices=sorted(CAPABILITIES))
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--timeout-sec", type=float, default=300.0)
    parser.add_argument("--startup-wait-sec", type=float, default=2.0)
    parser.add_argument("--idle-sec", type=float, default=3.0)
    parser.add_argument("--sample-period-sec", type=float, default=0.1)
    parser.add_argument("--pss-period-sec", type=float, default=1.0)
    parser.add_argument("--poll-period-sec", type=float, default=0.02)
    parser.add_argument("--energy-check-only", action="store_true")
    parser.add_argument("--run-order-seed", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    energy_meter = EnergyMeter()
    write_energy_report(output_dir, energy_meter)
    if args.energy_check_only:
        print((output_dir / "energy_measurement_status.md").read_text(), end="")
        return

    ensure_runtime_bts()
    architectures = ["bt", "modular"] if args.architecture == "both" else [args.architecture]
    schedule = [(architecture, idx) for idx in range(args.runs) for architecture in architectures]
    if len(architectures) > 1:
        random.Random(args.run_order_seed).shuffle(schedule)
    for architecture, idx in schedule:
        run_id = f"phase_{architecture}_{args.capability}_{time.strftime('%Y%m%d_%H%M%S')}_{idx:03d}"
        print(f"Running {run_id}", flush=True)
        if architecture == "bt":
            run_bt(args, run_id, output_dir, energy_meter)
        else:
            run_modular(args, run_id, output_dir, energy_meter)

    print(f"Wrote {output_dir / 'phase_resource_samples.csv'}")
    print(f"Wrote {output_dir / 'phase_resource_summary.csv'}")
    print(f"Wrote {output_dir / 'phase_events.csv'}")
    print(f"Wrote {output_dir / 'energy_measurement_status.md'}")


if __name__ == "__main__":
    main()
