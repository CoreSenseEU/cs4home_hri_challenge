#!/usr/bin/env python3
"""Plot modular CPU attribution across runtime phases."""

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

DESC_CSV = DATA_DIR / "modular_phase_cpu_attribution_descriptive_stats.csv"
FIG_BASE = PLOT_DIR / "modular_phase_cpu_attribution"

CAPABILITY_ORDER = ["greeting", "grab_bag"]
CAPABILITY_LABELS = {"greeting": "Greeting", "grab_bag": "GrabBag"}
PHASE_ORDER = ["lifecycle_activation", "execution", "lifecycle_deactivation"]
PHASE_LABELS = {
    "lifecycle_activation": "Activation",
    "execution": "Execution",
    "lifecycle_deactivation": "Deactivation",
}
ROLE_ORDER = ["cognitive_module", "hri_challenge_master"]
ROLE_LABELS = {
    "cognitive_module": "Cognitive Module",
    "hri_challenge_master": "Master",
}
ROLE_COLORS = {
    "cognitive_module": "#9DB8D2",
    "hri_challenge_master": "#D8C49A",
}


def load_data() -> pd.DataFrame:
    df = pd.read_csv(INPUT_CSV)
    cpu_col = "mean_cpu_percent" if "mean_cpu_percent" in df.columns else "mean_cpu"
    df = df[
        (df["architecture"] == "modular")
        & (df["capability"].isin(CAPABILITY_ORDER))
        & (df["phase"].isin(PHASE_ORDER))
        & (df["process_role"].isin(ROLE_ORDER))
    ].copy()
    df["mean_cpu_percent"] = pd.to_numeric(df[cpu_col], errors="coerce")
    df = df.dropna(subset=["mean_cpu_percent"])
    df["capability_label"] = df["capability"].map(CAPABILITY_LABELS)
    df["phase_label"] = df["phase"].map(PHASE_LABELS)
    df["role_label"] = df["process_role"].map(ROLE_LABELS)
    return df


def write_descriptive_stats(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = df.groupby(["capability", "phase", "process_role"], sort=False)
    for (capability, phase, role), values_df in grouped:
        values = values_df["mean_cpu_percent"].to_numpy(dtype=float)
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
                "process_role": role,
                "process_role_label": ROLE_LABELS[role],
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
    stats["process_role"] = pd.Categorical(stats["process_role"], ROLE_ORDER, ordered=True)
    stats = stats.sort_values(["capability", "phase", "process_role"])
    DESC_CSV.parent.mkdir(parents=True, exist_ok=True)
    stats.to_csv(DESC_CSV, index=False)
    return stats


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor("white")
    ax.grid(axis="y", color="0.88", linewidth=0.6)
    ax.grid(axis="x", visible=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("0.2")
    ax.spines["bottom"].set_color("0.2")
    ax.tick_params(axis="both", labelsize=9, color="0.2")


def draw_boxplot(ax: plt.Axes, data: pd.DataFrame, y_max: float, panel_label: str) -> None:
    phase_positions = np.arange(len(PHASE_ORDER), dtype=float)
    offsets = {"cognitive_module": -0.17, "hri_challenge_master": 0.17}
    rng = np.random.default_rng(20260819)

    for role in ROLE_ORDER:
        positions = phase_positions + offsets[role]
        series = [
            data.loc[
                (data["phase"] == phase) & (data["process_role"] == role),
                "mean_cpu_percent",
            ].to_numpy(dtype=float)
            for phase in PHASE_ORDER
        ]
        violin = ax.violinplot(
            series,
            positions=positions,
            widths=0.30,
            showmeans=False,
            showmedians=False,
            showextrema=False,
        )
        for body in violin["bodies"]:
            body.set_facecolor(ROLE_COLORS[role])
            body.set_edgecolor("none")
            body.set_alpha(0.18)
            body.set_zorder(1)

        box = ax.boxplot(
            series,
            positions=positions,
            widths=0.24,
            patch_artist=True,
            showfliers=False,
            whis=1.5,
            medianprops={"color": "0.0", "linewidth": 1.8},
            boxprops={"edgecolor": "black", "linewidth": 1.0},
            whiskerprops={"color": "black", "linewidth": 0.9},
            capprops={"color": "black", "linewidth": 0.9},
        )
        for patch in box["boxes"]:
            patch.set_facecolor(ROLE_COLORS[role])
            patch.set_alpha(0.72)
            patch.set_zorder(2)

        for xpos, values in zip(positions, series):
            jitter = rng.normal(0.0, 0.025, size=len(values))
            ax.scatter(
                np.full(len(values), xpos) + jitter,
                values,
                s=12,
                marker="o",
                facecolor=ROLE_COLORS[role],
                edgecolor="0.15",
                linewidth=0.45,
                alpha=0.72,
                zorder=3,
            )

    ax.set_xticks(phase_positions)
    ax.set_xticklabels([PHASE_LABELS[phase] for phase in PHASE_ORDER])
    ax.set_ylim(0, y_max)
    ax.text(
        0.015,
        0.965,
        panel_label,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        fontweight="bold",
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
    y_max = float(np.ceil(df["mean_cpu_percent"].max() / 10.0) * 10.0 + 5.0)
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.1), sharey=True, constrained_layout=True)

    for ax, capability, label in zip(axes, CAPABILITY_ORDER, ["(a) Greeting", "(b) GrabBag"]):
        draw_boxplot(ax, df[df["capability"] == capability], y_max, label)

    axes[0].set_ylabel("Mean CPU utilization (%)")
    for ax in axes:
        ax.set_xlabel("Runtime phase")

    legend_handles = [
        mpl.patches.Patch(facecolor=ROLE_COLORS["cognitive_module"], edgecolor="black", label="Cognitive Module", alpha=0.72),
        mpl.patches.Patch(facecolor=ROLE_COLORS["hri_challenge_master"], edgecolor="black", label="Master", alpha=0.72),
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
        raise SystemExit("No rows matched the requested modular phase CPU filters.")
    write_descriptive_stats(df)
    plot(df)
    print(f"Wrote {FIG_BASE.with_suffix('.pdf')}")
    print(f"Wrote {FIG_BASE.with_suffix('.svg')}")
    print(f"Wrote {FIG_BASE.with_suffix('.png')}")
    print(f"Wrote {DESC_CSV}")


if __name__ == "__main__":
    main()
