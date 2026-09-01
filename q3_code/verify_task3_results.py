"""Audit task-3 paths against input edges and compare configurations.

Coverage certificates come from exhaustive search, not from this path audit.
The empirical reference is an exact frontier when available, otherwise the
nondominated union of the tested configurations (never called the true frontier).
"""
import argparse
from array import array
import csv
import json
import math
from pathlib import Path

from run_task3 import ROOT, HEADER, atomic_json, queries, sha256


def edge_rows(file):
    with file.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            row = tuple(map(int, line.split()))
            if len(row) != 7 or min(row) < 0:
                raise ValueError("malformed edge input")
            yield row


def read_csr(file):
    counts = []
    for u, v, *_ in edge_rows(file):
        n = max(u, v) + 1
        if len(counts) < n:
            counts.extend([0] * (n - len(counts)))
        counts[u] += 1
    offsets = array("I", [0])
    for count in counts:
        offsets.append(offsets[-1] + count)
    columns = [array("I", [0]) * offsets[-1] for _ in range(6)]
    cursor = array("I", offsets[:-1])
    for u, v, *cost in edge_rows(file):
        k = cursor[u]; cursor[u] += 1
        columns[0][k] = v
        for j in range(5):
            columns[j+1][k] = cost[j]
    return offsets, columns


def nondominated(costs, m):
    result = []
    for point in sorted(set(tuple(c[:m]) for c in costs)):
        if m == 2:
            if not result or point[1] < result[-1][1]:
                result.append(point)
            continue
        if not any(all(a <= b for a, b in zip(p, point)) for p in result):
            result.append(point)
    return result


def factor(a, b):
    return max([1.] + [(x/y if y else (1. if x == 0 else math.inf)) for x, y in zip(a, b)])


def epsilon_indicator(points, reference):
    if not reference:
        return 0.
    if not points:
        return math.inf
    # A 2D skyline is ordered increasingly in x, decreasingly in y. The minimum
    # max(x/rx,y/ry) is attained next to their crossing; avoid a quadratic scan.
    if len(reference[0]) == 2:
        points = sorted(points)
        worst = 1.
        for r in reference:
            lo, hi = 0, len(points)
            while lo < hi:
                mid = (lo + hi) // 2
                if points[mid][0] * r[1] < points[mid][1] * r[0]:
                    lo = mid + 1
                else:
                    hi = mid
            candidates = points[max(0, lo-1):min(len(points), lo+1)]
            worst = max(worst, min(factor(p, r) for p in candidates))
        return worst - 1.
    return max(min(factor(p, r) for p in points) for r in reference) - 1.


def audit(root, out, evaluate=True):
    expected = {(q["dataset"], q["query_id"]): (q["source"], q["target"]) for q in queries(root)}
    files = sorted((out / "checkpoints").glob("*.json"))
    if not files:
        raise ValueError("no checkpoints")
    entries = [(file, json.loads(file.read_text(encoding="utf-8"))) for file in files]
    checks, groups = [], {}
    for ds in ("NY", "BAY", "COL"):
        selected = [(f, r) for f, r in entries if r["dataset"] == ds]
        if not selected:
            continue
        graphfile = root / "data" / "edges" / f"edges_{ds}_5obj.txt"
        graphhash = sha256(graphfile)
        queryhash = sha256(root / "data" / f"dimacs5_{ds.lower()}" / "queries_problem34.csv")
        offsets, columns = read_csr(graphfile)
        checked_paths = 0
        for file, r in selected:
            key = ds, r["query_id"]
            if r["schema"] != "TASK3_V1" or key not in expected:
                raise ValueError(f"invalid checkpoint: {file.name}")
            if (r["source"], r["target"]) != expected[key]:
                raise ValueError("wrong official endpoints")
            if r["edges_sha256"] != graphhash or r["queries_sha256"] != queryhash:
                raise ValueError("input fingerprint mismatch")
            if r["objective_count"] not in (2, 3, 5):
                raise ValueError("invalid dimensions")
            if r["certified"] != (r["status"] in ("exact", "epsilon_cover", "unreachable")):
                raise ValueError("certificate/status mismatch")
            if r["status"] == "exact" and r["epsilon"] != 0:
                raise ValueError("invalid exact status")
            costs = []
            for p in r["paths"]:
                vs, ids = p["vertices"], p["edge_indices"]
                if not vs or (vs[0], vs[-1]) != expected[key] or len(vs) != len(ids)+1 or len(set(vs)) != len(vs):
                    raise ValueError(f"invalid path: {file.name}")
                total = [0] * 5
                for u, v, k in zip(vs, vs[1:], ids):
                    if not 0 <= u < len(offsets)-1 or not offsets[u] <= k < offsets[u+1] or columns[0][k] != v:
                        raise ValueError("directed edge or CSR identity mismatch")
                    for j in range(5):
                        total[j] += columns[j+1][k]
                if total != p["cost"]:
                    raise ValueError("path cost mismatch")
                costs.append(total)
            m = r["objective_count"]
            points = nondominated(costs, m)
            if len(points) != len(costs):
                raise ValueError("duplicate or dominated candidate")
            if r["status"] == "unreachable" and costs:
                raise ValueError("unreachable result has paths")
            if r["status"] != "unreachable" and not costs:
                raise ValueError("reachable result has no path")
            checked_paths += len(costs)
            groups.setdefault((*key, m), []).append((file, r, points))
            checks.append({"file": file.name, "sha256": sha256(file), "paths": len(costs),
                           "status": r["status"], "path_audit": "pass"})
        del offsets, columns
        print(f"path audit: {ds} {len(selected)} runs, {checked_paths} paths PASS", flush=True)
    if len(checks) != len(entries):
        raise ValueError("unknown dataset")
    report = {"runs": len(checks), "groups": len(groups), "paths": sum(c["paths"] for c in checks),
              "passed": True, "checks": checks}
    atomic_json(out / "verification_report.json", report)
    if not evaluate:
        return report
    quality = []
    for key, configs in sorted(groups.items()):
        exact = [p for _, r, p in configs if r["status"] == "exact"]
        if exact:
            reference = exact[0]
            if any(p != reference for p in exact[1:]):
                raise ValueError("exact frontiers disagree")
            reference_kind = "exact"
        else:
            reference = nondominated([p for _, _, points in configs for p in points], key[2])
            reference_kind = "pooled_empirical" if len(configs) > 1 else "unavailable_single_config"
        for file, r, points in configs:
            value = epsilon_indicator(points, reference)
            if r["certified"] and value > r["epsilon"] + 1e-9:
                raise ValueError(f"coverage counterexample against observed paths: {file.name}")
            quality.append({"dataset": key[0], "query_id": key[1], "objective_count": key[2],
                            "method": "weighted_seeds" if r["seed_only"] else ("apex_open_merge" if r.get("algorithm")=="apex" and r["epsilon"]>0 else "NAMOA_dr_goal_epsilon"),
                            "epsilon": r["epsilon"], "status": r["status"], "certified": r["certified"],
                            "paths": len(points), "reference_kind": reference_kind,
                            "reference_size": len(reference), "reference_configurations": len(configs),
                            "empirical_epsilon": value if reference_kind != "unavailable_single_config" else "",
                            "load_seconds": r["load_seconds"], "preprocess_seconds": r["preprocess_seconds"],
                            "search_seconds": r["search_seconds"], "total_seconds": r["total_seconds"],
                            "peak_rss_mb": r["peak_rss_mb"], "expanded": r["expanded"],
                            "labels": r["labels"], "merged": r.get("merged", 0),
                            "file": file.name})
    target = out / "comparison.csv"
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(quality[0])); writer.writeheader(); writer.writerows(quality)
    print(f"quality comparison: {len(quality)} configurations; exact/pooled references explicitly distinguished", flush=True)
    return report


def verify_export(root, out):
    manifest_file = out / "aggregation.json"
    if not manifest_file.exists():
        return
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    file = out / manifest["file"]
    if file.parent != out or sha256(file) != manifest["sha256"]:
        raise ValueError("export path/hash mismatch")
    records = {}
    for checkpoint in (out / "checkpoints").glob("*.json"):
        r = json.loads(checkpoint.read_text(encoding="utf-8"))
        eps = manifest.get("epsilon_by_dimension", {}).get(str(r["objective_count"]), manifest["epsilon"])
        if not r["seed_only"] and r["epsilon"] == eps:
            key = r["dataset"], r["query_id"], r["objective_count"]
            if key in records:
                raise ValueError("duplicate export configuration")
            records[key] = r
    certified = sum(r["certified"] for r in records.values())
    complete = len(records) == 270 and certified == 270
    if manifest["groups"] != len(records) or manifest["certified_groups"] != certified or manifest["complete"] != complete:
        raise ValueError("export completion metadata mismatch")
    if not complete and not file.name.endswith(".partial.csv"):
        raise ValueError("uncertified export masquerades as complete")
    rows = 0
    with file.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        if next(reader) != HEADER:
            raise ValueError("incorrect result3 header")
        for q in queries(root):
            for m in (2, 3, 5):
                key = q["dataset"], q["query_id"], m
                if key not in records:
                    continue
                for i, p in enumerate(records[key]["paths"], 1):
                    expected = [*key[:2], q["source"], q["target"], m, i, *p["cost"], "->".join(map(str, p["vertices"]))]
                    if next(reader, None) != list(map(str, expected)):
                        raise ValueError("CSV row/path/cost differs from audited checkpoint")
                    rows += 1
        if next(reader, None) is not None:
            raise ValueError("unexpected extra CSV records")
    print(f"CSV audit: {len(records)} groups, {rows} paths PASS", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--paths-only", action="store_true")
    args = parser.parse_args()
    audit(args.root.resolve(), args.output_dir.resolve(), not args.paths_only)
    verify_export(args.root.resolve(), args.output_dir.resolve())


if __name__ == "__main__":
    main()
