#!/usr/bin/env python3
"""Plot modular runtime phase latencies."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "runtime_phase_benchmark"
INPUT_CSV = DATA_DIR / "phase_resource_summary.csv"
PLOT_DIR = DATA_DIR / "plots"

DESC_CSV = DATA_DIR / "modular_phase_latency_descriptive_stats.csv"
FIG_BASE = PLOT_DIR / "modular_phase_latencies"

CAPABILITY_ORDER = ["greeting", "grab_bag"]
CAPABILITY_LABELS = {"greeting": "Greeting", "grab_bag": "GrabBag"}
PHASE_ORDER = [
    "lifecycle_activation",
    "initialization",
    "execution",
    "completion_propagation",
    "lifecycle_deactivation",
]
PHASE_LABELS = {
    "lifecycle_activation": "Activation",
    "initialization": "Init.",
    "execution": "Execution",
    "completion_propagation": "Completion",
    "lifecycle_deactivation": "Deactivation",
}
BOX_COLOR = "#AFC4D6"


def load_data() -> pd.DataFrame:
    df = pd.read_csv(INPUT_CSV)
    df = df[
        (df["architecture"] == "modular")
        & (df["capability"].isin(CAPABILITY_ORDER))
        & (df["phase"].isin(PHASE_ORDER))
    ].copy()
    df["duration_ms"] = pd.to_numeric(df["duration_ms"], errors="coerce")
    df = df.dropna(subset=["duration_ms"])

    # Durations are phase-level measurements repeated across process-role rows.
    df = df.drop_duplicates(subset=["run_id", "capability", "phase", "duration_ms"])
    df["capability_label"] = df["capability"].map(CAPABILITY_LABELS)
    df["phase_label"] = df["phase"].map(PHASE_LABELS)
    return df


def write_descriptive_stats(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = df.groupby(["capability", "phase"], sort=False)
    for (capability, phase), values_df in grouped:
        values = values_df["duration_ms"].to_numpy(dtype=float)
        q1 = float(np.percentile(values, 25))
        q3 = float(np.percentile(values, 75))
        mean = float(np.mean(values))
        std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        rows.append(
            {
                "capability": capability,
                "capability_label": CAPABILITY_LABELS[capability],
                "phase": phase,
                "phase_label": PHASE_LABELS[phase],
                "n": int(len(values)),
                "mean": mean,
                "standard_deviation": std,
                "median": float(np.median(values)),
                "Q1": q1,
                "Q3": q3,
                "IQR": q3 - q1,
                "min": float(np.min(values)),
                "max": float(np.max(values)),
                "coefficient_of_variation": std / mean if mean else np.nan,
            }
        )
    stats = pd.DataFrame(rows)
    stats["capability"] = pd.Categorical(stats["capability"], CAPABILITY_ORDER, ordered=True)
    stats["phase"] = pd.Categorical(stats["phase"], PHASE_ORDER, ordered=True)
    stats = stats.sort_values(["capability", "phase"])
    DESC_CSV.parent.mkdir(parents=True, exist_ok=True)
    stats.to_csv(DESC_CSV, index=False)
    return stats


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor("white")
    ax.grid(axis="y", which="major", color="0.84", linewidth=0.7)
    ax.grid(axis="y", which="minor", color="0.94", linewidth=0.3)
    ax.grid(axis="x", visible=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("0.2")
    ax.spines["bottom"].set_color("0.2")
    ax.tick_params(axis="both", labelsize=8.5, color="0.2")


def draw_panel(ax: plt.Axes, data: pd.DataFrame, y_limits: tuple[float, float], panel_label: str) -> None:
    positions = np.arange(len(PHASE_ORDER), dtype=float)
    rng = np.random.default_rng(20260819)
    series = [
        data.loc[data["phase"] == phase, "duration_ms"].to_numpy(dtype=float)
        for phase in PHASE_ORDER
    ]

    box = ax.boxplot(
        series,
        positions=positions,
        widths=0.34,
        patch_artist=True,
        showfliers=False,
        whis=1.5,
        medianprops={"color": "black", "linewidth": 1.7},
        boxprops={"edgecolor": "black", "linewidth": 1.0},
        whiskerprops={"color": "black", "linewidth": 0.9},
        capprops={"color": "black", "linewidth": 0.9},
    )
    for patch in box["boxes"]:
        patch.set_facecolor(BOX_COLOR)
        patch.set_alpha(0.72)
        patch.set_zorder(2)

    for xpos, values in zip(positions, series):
        jitter = rng.normal(0.0, 0.035, size=len(values))
        ax.scatter(
            np.full(len(values), xpos) + jitter,
            values,
            s=10,
            marker="o",
            facecolor=BOX_COLOR,
            edgecolor="0.15",
            linewidth=0.45,
            alpha=0.72,
            zorder=3,
        )

    ax.set_xticks(positions)
    ax.set_xticklabels([PHASE_LABELS[phase] for phase in PHASE_ORDER], rotation=18, ha="right")
    ax.set_yscale("log")
    ax.set_ylim(*y_limits)
    ax.text(
        0.015,
        0.965,
        panel_label,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8.5,
        fontweight="semibold",
    )
    style_axis(ax)


def plot(df: pd.DataFrame) -> None:
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.labelsize": 10,
            "axes.titlesize": 10,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    positive = df.loc[df["duration_ms"] > 0, "duration_ms"]
    y_min = float(10 ** np.floor(np.log10(positive.min() * 0.7)))
    y_max = float(10 ** np.ceil(np.log10(positive.max() * 1.25)))

    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.35), sharey=True, constrained_layout=True)
    for ax, capability, label in zip(axes, CAPABILITY_ORDER, ["(a) Greeting", "(b) GrabBag"]):
        draw_panel(ax, df[df["capability"] == capability], (y_min, y_max), label)

    axes[0].set_ylabel("Duration (ms)")
    for ax in axes:
        ax.set_xlabel("Runtime phase")

    for ext in ("pdf", "svg", "png"):
        kwargs = {"bbox_inches": "tight"}
        if ext == "png":
            kwargs["dpi"] = 600
        fig.savefig(FIG_BASE.with_suffix(f".{ext}"), **kwargs)
    plt.close(fig)


def main() -> None:
    df = load_data()
    if df.empty:
        raise SystemExit("No rows matched the requested modular phase latency filters.")
    write_descriptive_stats(df)
    plot(df)
    print(f"Wrote {FIG_BASE.with_suffix('.pdf')}")
    print(f"Wrote {FIG_BASE.with_suffix('.svg')}")
    print(f"Wrote {FIG_BASE.with_suffix('.png')}")
    print(f"Wrote {DESC_CSV}")


if __name__ == "__main__":
    main()
