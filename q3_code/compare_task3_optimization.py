"""Compare identical task-3 queries, precision and budgets across two runs."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import statistics

from run_task3 import atomic_json
from verify_task3_results import epsilon_indicator, nondominated


def load(folder):
    records = {}
    for file in sorted((folder / "checkpoints").glob("*.json")):
        r = json.loads(file.read_text(encoding="utf-8"))
        r["costs"] = [p["cost"][:r["objective_count"]] for p in r.pop("paths")]
        r["file"] = file.name
        key = r["dataset"], r["query_id"], r["objective_count"], r["epsilon"], r["seed_only"]
        if key in records:
            raise ValueError(f"ambiguous configuration: {key}")
        records[key] = r
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("optimized", type=Path)
    parser.add_argument("--overrides", nargs="*", type=Path, default=[], help="certified rescue results for previously uncertified groups")
    args = parser.parse_args()
    before, after = load(args.baseline), load(args.optimized)
    rescue_groups = []
    for folder in args.overrides:
        for key, r in load(folder).items():
            if key in after and not after[key]["certified"] and r["certified"]:
                after[key] = r
                rescue_groups.append({"group": list(key[:3]), "source_directory": folder.name, "order": r.get("order", "21345")})
    rows, unresolved = [], []
    for key, b in sorted(after.items()):
        if key[3:] != (0.2, False):
            continue
        a = before[key]
        for field in ("source", "target", "edges_sha256", "queries_sha256", "seed_count", "max_seconds", "max_labels"):
            if a[field] != b[field]:
                raise ValueError(f"unmatched {field}: {key}")
        group = key[:3]
        exact = before.get((*group, 0., False))
        if exact and exact["status"] == "exact":
            reference = nondominated(exact["costs"], group[2]); reference_kind = "exact"
        else:
            reference = nondominated([c for k, r in before.items() if k[:3] == group for c in r["costs"]] + b["costs"], group[2])
            reference_kind = "pooled_empirical"
        old_e = epsilon_indicator(a["costs"], reference)
        new_e = epsilon_indicator(b["costs"], reference)
        if b["certified"] and new_e > .2 + 1e-9:
            raise ValueError(f"observed coverage counterexample: {key}")
        if a["certified"] and old_e > .2 + 1e-9:
            raise ValueError(f"baseline certificate contradicted by a new path: {key}")
        row = {"dataset": key[0], "query_id": key[1], "objective_count": key[2],
               "before_status": a["status"], "after_status": b["status"],
               "before_paths": len(a["costs"]), "after_paths": len(b["costs"]),
               "before_search_seconds": a["search_seconds"], "after_search_seconds": b["search_seconds"],
               "before_total_seconds": a["total_seconds"], "after_total_seconds": b["total_seconds"],
               "before_peak_rss_mb": a["peak_rss_mb"], "after_peak_rss_mb": b["peak_rss_mb"],
               "before_labels": a["labels"], "after_labels": b["labels"], "merged": b.get("merged", 0),
               "before_order": a.get("order", "21345"), "after_order": b.get("order", "21345"),
               "reference_kind": reference_kind, "before_empirical_epsilon": old_e, "after_empirical_epsilon": new_e}
        rows.append(row)
        if not b["certified"]:
            unresolved.append({"dataset": key[0], "query_id": key[1], "objective_count": key[2],
                               "source": b["source"], "target": b["target"], "file": b["file"],
                               "status": b["status"], "labels": b["labels"], "expanded": b["expanded"],
                               "merged": b.get("merged", 0), "peak_rss_mb": b["peak_rss_mb"]})
    if len(rows) != 270:
        raise ValueError("expected all 270 epsilon=0.2 comparison groups")
    exact_checks = 0
    for key, r in after.items():
        if key[2:] == (2, 0., False) and r["status"] == "exact":
            if {tuple(c) for c in r["costs"]} != {tuple(c) for c in before[key]["costs"]}:
                raise ValueError("two-objective exact front changed")
            exact_checks += 1
    stats = {}
    for m in (2, 3, 5):
        selected = [r for r in rows if r["objective_count"] == m]
        stats[str(m)] = {"groups": len(selected),
                        "before_status": dict(Counter(r["before_status"] for r in selected)),
                        "after_status": dict(Counter(r["after_status"] for r in selected))}
        for column in ("before_search_seconds", "after_search_seconds", "before_total_seconds", "after_total_seconds", "before_peak_rss_mb", "after_peak_rss_mb", "before_labels", "after_labels"):
            stats[str(m)]["median_" + column] = statistics.median(r[column] for r in selected)
        print(m, json.dumps(stats[str(m)]), flush=True)
    report = {"epsilon": .2, "search_budget_seconds": 30, "max_labels": 12000000,
              "exact_2d_matches": exact_checks, "observed_coverage_checks": len(rows),
              "dimensions": stats, "unresolved": unresolved}
    report["rescued_groups"] = rescue_groups
    atomic_json(args.optimized / "optimization_report.json", report)
    with (args.optimized / "comparison_baseline.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print("unresolved", json.dumps(unresolved), flush=True)


if __name__ == "__main__":
    main()
