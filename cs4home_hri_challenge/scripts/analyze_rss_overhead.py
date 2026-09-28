#!/usr/bin/env python3
"""Generate RSS memory overhead statistics and plots from per-run measurements."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "hri_runtime_eval"
INPUT_CSV = DATA_DIR / "resource_summary.csv"
PLOT_DIR = DATA_DIR / "plots"

DESC_CSV = DATA_DIR / "rss_mean_memory_descriptive_stats.csv"
STATS_CSV = DATA_DIR / "rss_mean_memory_statistical_tests.csv"
FIG_BASE = PLOT_DIR / "rss_mean_memory_boxplot"

CAPABILITY_LABELS = {"greeting": "Greeting", "grab_bag": "GrabBag"}
ARCH_LABELS = {"bt": "BT baseline", "modular": "Modular"}
CAPABILITY_ORDER = ["greeting", "grab_bag"]
ARCH_ORDER = ["bt", "modular"]
METRIC = "mean_rss_mb"


def cliffs_delta(x: np.ndarray, y: np.ndarray) -> float:
    comparisons = np.sign(x[:, None] - y[None, :])
    return float(comparisons.sum() / comparisons.size)


def effect_label(delta: float) -> str:
    magnitude = abs(delta)
    if magnitude < 0.147:
        size = "negligible"
    elif magnitude < 0.33:
        size = "small"
    elif magnitude < 0.474:
        size = "medium"
    else:
        size = "large"

    if delta > 0:
        direction = "Modular > BT"
    elif delta < 0:
        direction = "Modular < BT"
    else:
        direction = "no direction"
    return f"{size}; {direction}"


def holm_adjust(p_values: list[float]) -> list[float]:
    indexed = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [0.0] * len(p_values)
    previous = 0.0
    m = len(p_values)
    for rank, (idx, p_value) in enumerate(indexed):
        value = min(1.0, (m - rank) * p_value)
        value = max(previous, value)
        adjusted[idx] = value
        previous = value
    return adjusted


def load_rss_data() -> pd.DataFrame:
    df = pd.read_csv(INPUT_CSV)
    df = df[
        (df["scope"] == "run_total")
        & (df["architecture"].isin(ARCH_ORDER))
        & (df["capability"].isin(CAPABILITY_ORDER))
    ].copy()
    df["capability_label"] = df["capability"].map(CAPABILITY_LABELS)
    df["architecture_label"] = df["architecture"].map(ARCH_LABELS)
    return df


def write_descriptive_stats(df: pd.DataFrame) -> None:
    rows = []
    for capability in CAPABILITY_ORDER:
        for architecture in ARCH_ORDER:
            values = df.loc[
                (df["capability"] == capability) & (df["architecture"] == architecture), METRIC
            ].to_numpy(dtype=float)
            q1, q3 = np.percentile(values, [25, 75])
            mean = float(np.mean(values))
            sd = float(np.std(values, ddof=1))
            rows.append(
                {
                    "capability": CAPABILITY_LABELS[capability],
                    "architecture": ARCH_LABELS[architecture],
                    "n": int(values.size),
                    "mean_rss_mb": mean,
                    "sd_rss_mb": sd,
                    "median_rss_mb": float(np.median(values)),
                    "q1_rss_mb": float(q1),
                    "q3_rss_mb": float(q3),
                    "iqr_rss_mb": float(q3 - q1),
                    "min_rss_mb": float(np.min(values)),
                    "max_rss_mb": float(np.max(values)),
                    "cv_percent": float(sd / mean * 100.0),
                }
            )

    pd.DataFrame(rows).to_csv(DESC_CSV, index=False, quoting=csv.QUOTE_MINIMAL)


def write_statistical_tests(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    raw_p_values = []
    for capability in CAPABILITY_ORDER:
        bt = df.loc[
            (df["capability"] == capability) & (df["architecture"] == "bt"), METRIC
        ].to_numpy(dtype=float)
        modular = df.loc[
            (df["capability"] == capability) & (df["architecture"] == "modular"), METRIC
        ].to_numpy(dtype=float)

        test = mannwhitneyu(bt, modular, alternative="two-sided", method="auto")
        p_value = float(test.pvalue)
        delta = cliffs_delta(modular, bt)
        bt_mean = float(np.mean(bt))
        modular_mean = float(np.mean(modular))
        absolute_difference = modular_mean - bt_mean
        overhead = absolute_difference / bt_mean * 100.0
        raw_p_values.append(p_value)
        rows.append(
            {
                "capability": CAPABILITY_LABELS[capability],
                "bt_mean_rss_mb": bt_mean,
                "modular_mean_rss_mb": modular_mean,
                "absolute_difference_rss_mb": absolute_difference,
                "rss_overhead_percent": overhead,
                "mann_whitney_u_statistic": float(test.statistic),
                "raw_p_value": p_value,
                "holm_adjusted_p_value": np.nan,
                "cliffs_delta_modular_vs_bt": delta,
                "effect_interpretation": effect_label(delta),
            }
        )

    adjusted = holm_adjust(raw_p_values)
    for row, p_adjusted in zip(rows, adjusted):
        row["holm_adjusted_p_value"] = p_adjusted

    stats = pd.DataFrame(rows)
    stats.to_csv(STATS_CSV, index=False, quoting=csv.QUOTE_MINIMAL)
    return stats


def plot_boxplot(df: pd.DataFrame) -> None:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    positions = {
        ("greeting", "bt"): 0.82,
        ("greeting", "modular"): 1.18,
        ("grab_bag", "bt"): 1.82,
        ("grab_bag", "modular"): 2.18,
    }
    colors = {"bt": "#f2f2f2", "modular": "#7f7f7f"}
    hatches = {"bt": "", "modular": "///"}

    fig, ax = plt.subplots(figsize=(6.2, 4.0), constrained_layout=True)

    data = []
    pos = []
    keys = []
    for capability in CAPABILITY_ORDER:
        for architecture in ARCH_ORDER:
            values = df.loc[
                (df["capability"] == capability) & (df["architecture"] == architecture), METRIC
            ].to_numpy(dtype=float)
            data.append(values)
            pos.append(positions[(capability, architecture)])
            keys.append((capability, architecture))

    box = ax.boxplot(
        data,
        positions=pos,
        widths=0.28,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "black", "linewidth": 1.4},
        boxprops={"edgecolor": "black", "linewidth": 1.0},
        whiskerprops={"color": "black", "linewidth": 1.0},
        capprops={"color": "black", "linewidth": 1.0},
    )
    for patch, (_, architecture) in zip(box["boxes"], keys):
        patch.set_facecolor(colors[architecture])
        patch.set_hatch(hatches[architecture])

    rng = np.random.default_rng(20260818)
    for capability, architecture in keys:
        values = df.loc[
            (df["capability"] == capability) & (df["architecture"] == architecture), METRIC
        ].to_numpy(dtype=float)
        jitter = rng.uniform(-0.045, 0.045, size=values.size)
        ax.scatter(
            np.full(values.size, positions[(capability, architecture)]) + jitter,
            values,
            s=20,
            marker="o",
            facecolors="white" if architecture == "bt" else "black",
            edgecolors="black",
            linewidths=0.7,
            zorder=3,
        )

    ax.set_xlim(0.5, 2.5)
    ax.set_xticks([1.0, 2.0], ["Greeting", "GrabBag"])
    ax.set_ylabel("Mean RSS (MB)")
    ax.set_xlabel("Capability")
    ax.yaxis.grid(True, color="#d9d9d9", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    handles = []
    for architecture in ARCH_ORDER:
        handles.append(
            plt.Rectangle(
                (0, 0),
                1,
                1,
                facecolor=colors[architecture],
                edgecolor="black",
                hatch=hatches[architecture],
                label=ARCH_LABELS[architecture],
            )
        )
    ax.legend(handles=handles, frameon=False, loc="upper left")

    for ext, kwargs in {"pdf": {}, "svg": {}, "png": {"dpi": 600}}.items():
        fig.savefig(FIG_BASE.with_suffix(f".{ext}"), **kwargs)
    plt.close(fig)


def main() -> None:
    df = load_rss_data()
    expected = len(CAPABILITY_ORDER) * len(ARCH_ORDER) * 10
    if len(df) != expected:
        raise RuntimeError(f"Expected {expected} per-run rows, found {len(df)}")

    write_descriptive_stats(df)
    stats = write_statistical_tests(df)
    plot_boxplot(df)

    print(f"Wrote {DESC_CSV}")
    print(f"Wrote {STATS_CSV}")
    print(f"Wrote {FIG_BASE.with_suffix('.pdf')}")
    print(f"Wrote {FIG_BASE.with_suffix('.svg')}")
    print(f"Wrote {FIG_BASE.with_suffix('.png')}")
    print(stats.to_string(index=False))


if __name__ == "__main__":
    main()
