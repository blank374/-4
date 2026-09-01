"""Compare weighted-seed candidates with epsilon=.20 search on the fixed 9 queries."""
import argparse
import csv
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent


def median(values):
    return statistics.median(values) if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT/"docs/task3_validation/comparison.csv")
    parser.add_argument("--output", type=Path, default=ROOT/"docs/task3_validation/seed_baseline_comparison.csv")
    args = parser.parse_args()
    with args.input.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    selected = [r for r in rows if r["method"] == "weighted_seeds" or
                (r["method"] == "NAMOA_dr_goal_epsilon" and float(r["epsilon"]) == .2 and r["query_id"] in {"0001", "0015", "0030"})]
    detail = []
    for r in selected:
        detail.append({"dataset": r["dataset"], "query_id": r["query_id"], "objective_count": int(r["objective_count"]),
                       "method": "weighted_seeds" if r["method"] == "weighted_seeds" else "epsilon_0.20",
                       "certified": r["certified"], "paths": int(r["paths"]),
                       "empirical_epsilon": r["empirical_epsilon"], "reference_kind": r["reference_kind"],
                       "total_seconds": float(r["total_seconds"]), "peak_rss_mb": float(r["peak_rss_mb"])})
    keys = {(r["dataset"], r["query_id"], r["objective_count"]) for r in detail}
    assert len(keys) == 27 and len(detail) == 54
    summary = []
    for m in (2, 3, 5):
        for method in ("weighted_seeds", "epsilon_0.20"):
            group = [r for r in detail if r["objective_count"] == m and r["method"] == method]
            empirical = [float(r["empirical_epsilon"]) for r in group if r["empirical_epsilon"] != ""]
            summary.append({"objective_count": m, "method": method, "groups": len(group),
                            "certified_groups": sum(r["certified"] == "True" for r in group),
                            "candidate_paths": sum(r["paths"] for r in group),
                            "median_paths": median([r["paths"] for r in group]),
                            "median_empirical_epsilon": median(empirical),
                            "max_empirical_epsilon": max(empirical) if empirical else None,
                            "median_total_seconds": median([r["total_seconds"] for r in group]),
                            "median_peak_rss_mb": median([r["peak_rss_mb"] for r in group])})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0])); writer.writeheader(); writer.writerows(summary)
    print("objective method groups certified paths median_paths median_empirical max_empirical median_seconds median_MiB")
    for r in summary:
        print(r["objective_count"], r["method"], r["groups"], r["certified_groups"], r["candidate_paths"],
              r["median_paths"], r["median_empirical_epsilon"], r["max_empirical_epsilon"],
              r["median_total_seconds"], r["median_peak_rss_mb"])


if __name__ == "__main__":
    main()
