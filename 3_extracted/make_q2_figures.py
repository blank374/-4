"""Generate reproducible figures for the task-2 section of the paper."""

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
RESULT_CSV = ROOT / "results_task2_exact" / "result2_研XXX.csv"
STATUS_CSV = ROOT / "results_task2_exact" / "task2_status.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "figures"
DATASETS = ("NY", "BAY", "COL")
COLORS = {"NY": "#2F6B9A", "BAY": "#D97941", "COL": "#3F8F6B"}


def read_status():
    rows = []
    with STATUS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            row["solutions"] = int(row["solutions"])
            row["search_seconds"] = float(row["search_seconds"])
            rows.append(row)
    return rows


def choose_representative_queries(status_rows):
    chosen = {}
    for dataset in DATASETS:
        part = [row for row in status_rows if row["dataset"] == dataset]
        median_size = statistics.median(row["solutions"] for row in part)
        chosen[dataset] = min(
            part,
            key=lambda row: (abs(row["solutions"] - median_size), row["query_id"]),
        )
    return chosen


def read_selected_fronts(chosen):
    wanted = {(dataset, row["query_id"]) for dataset, row in chosen.items()}
    fronts = defaultdict(list)
    with RESULT_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["dataset"], row["query_id"])
            if key in wanted:
                fronts[key].append((int(row["c1"]), int(row["c2"]), int(row["c3"])))
    return {key: np.asarray(values, dtype=np.float64) for key, values in fronts.items()}


def plot_fronts(chosen, fronts):
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 3.8), constrained_layout=True)
    for ax, dataset in zip(axes, DATASETS):
        query = chosen[dataset]
        values = fronts[(dataset, query["query_id"])]
        normalized = values / values.min(axis=0, keepdims=True)
        points = ax.scatter(
            normalized[:, 0],
            normalized[:, 1],
            c=normalized[:, 2],
            cmap="viridis",
            s=2.2,
            alpha=0.32,
            linewidths=0,
            rasterized=True,
        )
        ax.set_title(
            f"{dataset} / 查询 {query['query_id']} / n={len(values):,}",
            fontsize=10.5,
            pad=6,
        )
        ax.set_xlabel(r"归一化距离 $C_1/C_1^{\min}$", fontsize=9)
        ax.set_ylabel(r"归一化时间 $C_2/C_2^{\min}$", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.grid(True, linewidth=0.45, alpha=0.28)
        colorbar = fig.colorbar(points, ax=ax, pad=0.015, fraction=0.05)
        colorbar.set_label(r"起伏比 $C_3/C_3^{\min}$", fontsize=8)
        colorbar.ax.tick_params(labelsize=7.5)
    fig.savefig(OUTPUT_DIR / "q2_pareto_front_examples.png", dpi=320, bbox_inches="tight")
    plt.close(fig)


def plot_scale_and_time(status_rows):
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.2), constrained_layout=True)

    grouped = [
        [row["solutions"] / 10_000 for row in status_rows if row["dataset"] == dataset]
        for dataset in DATASETS
    ]
    box = axes[0].boxplot(
        grouped,
        tick_labels=DATASETS,
        patch_artist=True,
        widths=0.58,
        showfliers=False,
        medianprops={"color": "#222222", "linewidth": 1.5},
        whiskerprops={"linewidth": 1.0},
        capprops={"linewidth": 1.0},
    )
    for patch, dataset in zip(box["boxes"], DATASETS):
        patch.set_facecolor(COLORS[dataset])
        patch.set_alpha(0.72)
    rng = np.random.default_rng(20260901)
    for index, (dataset, values) in enumerate(zip(DATASETS, grouped), start=1):
        jitter = rng.uniform(-0.10, 0.10, size=len(values))
        axes[0].scatter(
            index + jitter,
            values,
            s=18,
            alpha=0.72,
            color=COLORS[dataset],
            edgecolor="white",
            linewidth=0.3,
            zorder=3,
        )
    axes[0].set_ylabel("每组精确 Pareto 向量数（万）")
    axes[0].set_title("各城市精确前沿规模分布")
    axes[0].grid(axis="y", alpha=0.28)

    for dataset in DATASETS:
        part = [row for row in status_rows if row["dataset"] == dataset]
        axes[1].scatter(
            [row["solutions"] / 10_000 for row in part],
            [row["search_seconds"] for row in part],
            s=30,
            alpha=0.78,
            color=COLORS[dataset],
            edgecolor="white",
            linewidth=0.35,
            label=dataset,
        )
    axes[1].xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.1f}"))
    axes[1].set_xlabel("每组精确 Pareto 向量数（万）")
    axes[1].set_ylabel("精确搜索时间（秒）")
    axes[1].set_title("前沿规模与搜索时间")
    axes[1].grid(alpha=0.28)
    axes[1].legend(frameon=False)

    fig.savefig(OUTPUT_DIR / "q2_front_size_and_time.png", dpi=320, bbox_inches="tight")
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
        }
    )
    status_rows = read_status()
    chosen = choose_representative_queries(status_rows)
    fronts = read_selected_fronts(chosen)
    plot_fronts(chosen, fronts)
    plot_scale_and_time(status_rows)
    print(
        "representatives:",
        ", ".join(
            f"{dataset}/{chosen[dataset]['query_id']} (n={chosen[dataset]['solutions']})"
            for dataset in DATASETS
        ),
    )


if __name__ == "__main__":
    main()
