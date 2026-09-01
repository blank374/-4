"""Generate reproducible figures for the task-4 section of the paper."""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
COMPARISON_CSV = ROOT / "q4_output" / "comparison.csv"
SENSITIVITY_CSV = ROOT / "q4_output" / "sensitivity.csv"
SENSITIVITY_GROUPS_CSV = ROOT / "q4_output" / "sensitivity_groups.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "figures"

DATASETS = ("NY", "BAY", "COL")
SCHEMES = ("time_priority", "stable_priority", "balanced", "time_shortest")
SCHEME_LABELS = {
    "time_priority": "时间优先",
    "stable_priority": "平稳优先",
    "balanced": "均衡",
    "time_shortest": "时间最短",
}
CITY_COLORS = {"NY": "#2F6B9A", "BAY": "#D97941", "COL": "#3F8F6B"}
METRIC_COLORS = {"time": "#D97941", "elevation": "#4C78A8", "complexity": "#3F8F6B"}


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def plot_closure_and_tradeoff(comparison_rows):
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.8), constrained_layout=True)

    grouped = defaultdict(list)
    by_query = defaultdict(dict)
    for row in comparison_rows:
        dataset = row["dataset"]
        scheme = row["scheme"]
        grouped[(dataset, scheme)].append(
            100 * float(row["intrinsic_closure_relative_loss"])
        )
        by_query[(dataset, row["query_id"])][scheme] = row

    base_positions = np.arange(len(SCHEMES), dtype=float)
    offsets = {"NY": -0.24, "BAY": 0.0, "COL": 0.24}
    rng = np.random.default_rng(20260901)
    for dataset in DATASETS:
        values = [grouped[(dataset, scheme)] for scheme in SCHEMES]
        positions = base_positions + offsets[dataset]
        box = axes[0].boxplot(
            values,
            positions=positions,
            widths=0.19,
            patch_artist=True,
            showfliers=False,
            medianprops={"color": "#222222", "linewidth": 1.2},
            whiskerprops={"linewidth": 0.9},
            capprops={"linewidth": 0.9},
        )
        for patch in box["boxes"]:
            patch.set_facecolor(CITY_COLORS[dataset])
            patch.set_alpha(0.70)
        for position, part in zip(positions, values):
            jitter = rng.uniform(-0.045, 0.045, size=len(part))
            axes[0].scatter(
                position + jitter,
                part,
                s=10,
                alpha=0.45,
                color=CITY_COLORS[dataset],
                linewidth=0,
                zorder=3,
            )

    axes[0].set_xticks(base_positions, [SCHEME_LABELS[item] for item in SCHEMES])
    axes[0].set_ylabel("封路内在相对损失（%）")
    axes[0].set_title("指定封路下的损失分布")
    axes[0].grid(axis="y", alpha=0.25)
    legend_handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            linestyle="",
            markerfacecolor=CITY_COLORS[dataset],
            markeredgecolor="none",
            markersize=6,
            label=dataset,
        )
        for dataset in DATASETS
    ]
    axes[0].legend(handles=legend_handles, frameon=False, ncol=3, loc="upper left")

    labels = []
    tradeoff = []
    for dataset in DATASETS:
        for scheme in ("time_priority", "stable_priority"):
            changes = {"time": [], "elevation": [], "complexity": []}
            for (city, _query_id), schemes in by_query.items():
                if city != dataset:
                    continue
                baseline = schemes["time_shortest"]
                selected = schemes[scheme]
                changes["time"].append(
                    100
                    * (float(selected["original_c2"]) / float(baseline["original_c2"]) - 1)
                )
                changes["elevation"].append(
                    100
                    * (float(selected["original_c3"]) / float(baseline["original_c3"]) - 1)
                )
                changes["complexity"].append(
                    100
                    * (float(selected["original_c4"]) / float(baseline["original_c4"]) - 1)
                )
            labels.append(f"{dataset}-{'\u65f6间优先' if scheme == 'time_priority' else '\u5e73稳优先'}")
            tradeoff.append({key: statistics.median(value) for key, value in changes.items()})

    y = np.arange(len(labels), dtype=float)
    height = 0.23
    for offset, key, label in (
        (-height, "time", "时间"),
        (0.0, "elevation", "起伏"),
        (height, "complexity", "复杂度"),
    ):
        axes[1].barh(
            y + offset,
            [item[key] for item in tradeoff],
            height=height * 0.88,
            color=METRIC_COLORS[key],
            alpha=0.86,
            label=label,
        )
    axes[1].axvline(0, color="#333333", linewidth=0.9)
    axes[1].set_yticks(y, labels)
    axes[1].invert_yaxis()
    axes[1].xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))
    axes[1].set_xlabel("相对同查询时间最短路线的中位变化")
    axes[1].set_title("偏好推荐的收益与时间代价")
    axes[1].grid(axis="x", alpha=0.25)
    axes[1].legend(frameon=False, ncol=3, loc="lower right")

    fig.savefig(OUTPUT_DIR / "q4_closure_and_tradeoff.png", dpi=320, bbox_inches="tight")
    plt.close(fig)


def choose_sensitivity_examples(group_rows):
    chosen = {}
    for dataset in DATASETS:
        part = [
            row
            for row in group_rows
            if row["dataset"] == dataset and row["family"] == "time_share"
        ]
        median_count = statistics.median(int(row["distinct_costs"]) for row in part)
        chosen[dataset] = min(
            part,
            key=lambda row: (
                abs(int(row["distinct_costs"]) - median_count),
                row["query_id"],
            ),
        )
    return chosen


def plot_sensitivity(sensitivity_rows, group_rows):
    chosen = choose_sensitivity_examples(group_rows)
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 3.9), constrained_layout=True)
    styles = (
        ("c2", "时间", METRIC_COLORS["time"]),
        ("c3", "起伏", METRIC_COLORS["elevation"]),
        ("c4", "复杂度", METRIC_COLORS["complexity"]),
    )

    for ax, dataset in zip(axes, DATASETS):
        query_id = chosen[dataset]["query_id"]
        part = sorted(
            (
                row
                for row in sensitivity_rows
                if row["dataset"] == dataset
                and row["query_id"] == query_id
                and row["family"] == "time_share"
            ),
            key=lambda row: float(row["parameter"]),
        )
        theta = np.asarray([float(row["parameter"]) for row in part])
        for key, label, color in styles:
            values = np.asarray([float(row[key]) for row in part])
            normalized = values / values.min()
            ax.step(theta, normalized, where="post", linewidth=1.8, color=color, label=label)
            ax.scatter(theta, normalized, s=18, color=color, edgecolor="white", linewidth=0.35)
        ax.set_title(
            f"{dataset} / 查询 {query_id} / "
            f"{chosen[dataset]['distinct_costs']} 种推荐",
            fontsize=10.5,
        )
        ax.set_xlabel(r"时间权重占比 $\theta$")
        ax.set_xticks(np.arange(0, 1.01, 0.2))
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("相对该项扫描最小值的比值")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 1.11),
    )
    fig.savefig(OUTPUT_DIR / "q4_sensitivity_examples.png", dpi=320, bbox_inches="tight")
    plt.close(fig)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [
                "Microsoft YaHei",
                "SimHei",
                "Noto Sans CJK SC",
                "DejaVu Sans",
            ],
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "font.size": 9.5,
        }
    )
    comparison_rows = read_csv(COMPARISON_CSV)
    sensitivity_rows = read_csv(SENSITIVITY_CSV)
    group_rows = read_csv(SENSITIVITY_GROUPS_CSV)
    plot_closure_and_tradeoff(comparison_rows)
    plot_sensitivity(sensitivity_rows, group_rows)
    chosen = choose_sensitivity_examples(group_rows)
    print(
        "sensitivity representatives:",
        ", ".join(
            f"{dataset}/{chosen[dataset]['query_id']} "
            f"({chosen[dataset]['distinct_costs']} recommendations)"
            for dataset in DATASETS
        ),
    )


if __name__ == "__main__":
    main()
