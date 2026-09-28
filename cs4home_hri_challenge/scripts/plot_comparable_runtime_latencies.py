#!/usr/bin/env python3
"""Plot comparable BT vs modular runtime latency windows."""

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

DESC_CSV = DATA_DIR / "comparable_runtime_latency_descriptive_stats.csv"
FIG_BASE = PLOT_DIR / "comparable_runtime_latencies_bt_vs_modular"

CAPABILITY_ORDER = ["greeting", "grab_bag"]
CAPABILITY_LABELS = {"greeting": "Greeting", "grab_bag": "GrabBag"}
ARCH_ORDER = ["bt", "modular"]
ARCH_LABELS = {"bt": "BT baseline", "modular": "Modular"}
WINDOW_ORDER = ["pre_execution", "execution", "e2e_active"]
WINDOW_LABELS = {
    "pre_execution": "Pre-execution",
    "execution": "Execution",
    "e2e_active": "End-to-end",
}
ARCH_COLORS = {"bt": "#B7C9A8", "modular": "#AFC4D6"}


def load_data() -> pd.DataFrame:
    df = pd.read_csv(INPUT_CSV)
    df = df[
        (df["architecture"].isin(ARCH_ORDER))
        & (df["capability"].isin(CAPABILITY_ORDER))
        & (df["phase"].isin(WINDOW_ORDER))
    ].copy()
    df["duration_ms"] = pd.to_numeric(df["duration_ms"], errors="coerce")
    df = df.dropna(subset=["duration_ms"])

    # Durations are window-level measurements repeated across process-role rows.
    df = df.drop_duplicates(subset=["run_id", "architecture", "capability", "phase", "duration_ms"])
    df["capability_label"] = df["capability"].map(CAPABILITY_LABELS)
    df["architecture_label"] = df["architecture"].map(ARCH_LABELS)
    df["window_label"] = df["phase"].map(WINDOW_LABELS)
    return df


def write_descriptive_stats(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = df.groupby(["capability", "phase", "architecture"], sort=False)
    for (capability, phase, architecture), values_df in grouped:
        values = values_df["duration_ms"].to_numpy(dtype=float)
        q1 = float(np.percentile(values, 25))
        q3 = float(np.percentile(values, 75))
        rows.append(
            {
                "capability": capability,
                "capability_label": CAPABILITY_LABELS[capability],
                "window": phase,
                "window_label": WINDOW_LABELS[phase],
                "architecture": architecture,
                "architecture_label": ARCH_LABELS[architecture],
                "n": int(len(values)),
                "mean": float(np.mean(values)),
                "SD": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "median": float(np.median(values)),
                "Q1": q1,
                "Q3": q3,
                "IQR": q3 - q1,
                "min": float(np.min(values)),
                "max": float(np.max(values)),
            }
        )

    stats = pd.DataFrame(rows)
    stats["capability"] = pd.Categorical(stats["capability"], CAPABILITY_ORDER, ordered=True)
    stats["window"] = pd.Categorical(stats["window"], WINDOW_ORDER, ordered=True)
    stats["architecture"] = pd.Categorical(stats["architecture"], ARCH_ORDER, ordered=True)
    stats = stats.sort_values(["capability", "window", "architecture"])

    comparison_rows = []
    for capability in CAPABILITY_ORDER:
        for window in WINDOW_ORDER:
            subset = stats[(stats["capability"] == capability) & (stats["window"] == window)]
            bt = subset[subset["architecture"] == "bt"]
            modular = subset[subset["architecture"] == "modular"]
            if bt.empty or modular.empty:
                continue
            bt_mean = float(bt["mean"].iloc[0])
            modular_mean = float(modular["mean"].iloc[0])
            comparison_rows.append(
                {
                    "capability": capability,
                    "window": window,
                    "modular_minus_bt_mean_ms": modular_mean - bt_mean,
                    "modular_vs_bt_mean_relative_percent": ((modular_mean - bt_mean) / bt_mean * 100.0) if bt_mean else np.nan,
                }
            )
    comparisons = pd.DataFrame(comparison_rows)
    stats = stats.merge(comparisons, on=["capability", "window"], how="left")

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
    ax.tick_params(axis="both", labelsize=8.7, color="0.2")


def draw_panel(ax: plt.Axes, data: pd.DataFrame, y_limits: tuple[float, float], panel_label: str) -> None:
    window_positions = np.arange(len(WINDOW_ORDER), dtype=float)
    offsets = {"bt": -0.17, "modular": 0.17}
    rng = np.random.default_rng(20260819)

    for architecture in ARCH_ORDER:
        positions = window_positions + offsets[architecture]
        series = [
            data.loc[
                (data["phase"] == window) & (data["architecture"] == architecture),
                "duration_ms",
            ].to_numpy(dtype=float)
            for window in WINDOW_ORDER
        ]
        box = ax.boxplot(
            series,
            positions=positions,
            widths=0.26,
            patch_artist=True,
            showfliers=False,
            whis=1.5,
            medianprops={"color": "black", "linewidth": 1.7},
            boxprops={"edgecolor": "black", "linewidth": 1.0},
            whiskerprops={"color": "black", "linewidth": 0.9},
            capprops={"color": "black", "linewidth": 0.9},
        )
        for patch in box["boxes"]:
            patch.set_facecolor(ARCH_COLORS[architecture])
            patch.set_alpha(0.74)
            patch.set_zorder(2)

        for xpos, values in zip(positions, series):
            jitter = rng.normal(0.0, 0.026, size=len(values))
            ax.scatter(
                np.full(len(values), xpos) + jitter,
                values,
                s=10,
                marker="o",
                facecolor=ARCH_COLORS[architecture],
                edgecolor="0.15",
                linewidth=0.45,
                alpha=0.72,
                zorder=3,
            )

    ax.set_xticks(window_positions)
    ax.set_xticklabels([WINDOW_LABELS[window] for window in WINDOW_ORDER])
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
            "legend.fontsize": 8.5,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    positive = df.loc[df["duration_ms"] > 0, "duration_ms"]
    y_min = float(10 ** np.floor(np.log10(positive.min() * 0.75)))
    y_max = float(10 ** np.ceil(np.log10(positive.max() * 1.20)))

    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.25), sharey=True, constrained_layout=True)
    for ax, capability, label in zip(axes, CAPABILITY_ORDER, ["(a) Greeting", "(b) GrabBag"]):
        draw_panel(ax, df[df["capability"] == capability], (y_min, y_max), label)

    axes[0].set_ylabel("Duration (ms)")
    for ax in axes:
        ax.set_xlabel("Runtime interval")

    legend_handles = [
        mpl.patches.Patch(facecolor=ARCH_COLORS["bt"], edgecolor="black", label="BT baseline", alpha=0.74),
        mpl.patches.Patch(facecolor=ARCH_COLORS["modular"], edgecolor="black", label="Modular", alpha=0.74),
    ]
    axes[1].legend(
        handles=legend_handles,
        loc="upper right",
        frameon=True,
        framealpha=1.0,
        facecolor="white",
        edgecolor="0.85",
        borderpad=0.35,
        handlelength=1.4,
    )

    for ext in ("pdf", "svg", "png"):
        kwargs = {"bbox_inches": "tight"}
        if ext == "png":
            kwargs["dpi"] = 600
        fig.savefig(FIG_BASE.with_suffix(f".{ext}"), **kwargs)
    plt.close(fig)


def main() -> None:
    df = load_data()
    if df.empty:
        raise SystemExit("No rows matched the requested comparable latency filters.")
    write_descriptive_stats(df)
    plot(df)
    print(f"Wrote {FIG_BASE.with_suffix('.pdf')}")
    print(f"Wrote {FIG_BASE.with_suffix('.svg')}")
    print(f"Wrote {FIG_BASE.with_suffix('.png')}")
    print(f"Wrote {DESC_CSV}")


if __name__ == "__main__":
    main()
