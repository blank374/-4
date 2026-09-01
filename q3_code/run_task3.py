"""Reproducible task-3 experiments, one isolated process per query/configuration.

Checkpoints are tied to the executable, input files, endpoints and parameters.
Only --aggregate with all 270 certified query/dimension groups creates a formal CSV.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

CODE_DIR = Path(__file__).resolve().parent
ROOT = CODE_DIR.parent
HEADER = ["dataset", "query_id", "source", "target", "objective_count", "solution_id",
          "c1", "c2", "c3", "c4", "c5", "path"]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def queries(root):
    result = []
    for ds in ("NY", "BAY", "COL"):
        file = root / "data" / f"dimacs5_{ds.lower()}" / "queries_problem34.csv"
        with file.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != 30 or len({r["query_id"] for r in rows}) != 30:
            raise ValueError(f"{ds}: expected 30 unique official queries")
        for row in rows:
            result.append({"dataset": ds, "query_id": row["query_id"],
                           "source": int(row["source"]), "target": int(row["target"])})
    return result


def aggregate(root, out, eps, researcher, exact_2d=False):
    if not researcher or any(c in researcher for c in '/\\:*?"<>|'):
        raise ValueError("invalid researcher identifier")
    from verify_task3_results import audit, verify_export
    audit(root, out, evaluate=False)
    records = {}
    epsilon_by_dimension = {str(m): (0. if exact_2d and m == 2 else float(eps)) for m in (2, 3, 5)}
    for file in sorted((out / "checkpoints").glob("*.json")):
        r = json.loads(file.read_text(encoding="utf-8"))
        if r["epsilon"] == epsilon_by_dimension[str(r["objective_count"])] and not r["seed_only"]:
            key = r["dataset"], r["query_id"], r["objective_count"]
            if key in records:
                raise ValueError(f"duplicate configuration for {key}")
            records[key] = r
    all_queries = queries(root)
    expected = {(q["dataset"], q["query_id"], m): q for q in all_queries for m in (2, 3, 5)}
    if set(records) - set(expected):
        raise ValueError("unexpected query in checkpoints")
    complete = len(records) == 270 and all(r["certified"] for r in records.values())
    suffix = "" if complete else ".partial"
    target = out / f"result3_研{researcher}{suffix}.csv"
    temp = target.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(HEADER)
        for key, q in expected.items():
            if key not in records:
                continue
            r = records[key]
            if (r["source"], r["target"]) != (q["source"], q["target"]):
                raise ValueError(f"wrong endpoints: {key}")
            for i, p in enumerate(r["paths"], 1):
                writer.writerow([*key[:2], q["source"], q["target"], key[2], i,
                                 *p["cost"], "->".join(map(str, p["vertices"]))])
    os.replace(temp, target)
    atomic_json(out / "aggregation.json", {"groups": len(records), "expected": 270,
                "certified_groups": sum(r["certified"] for r in records.values()),
                "complete": complete, "epsilon": float(eps), "file": target.name,
                "epsilon_by_dimension": epsilon_by_dimension,
                "sha256": sha256(target), "path_audit_passed": True})
    verify_export(root, out)
    print(f"aggregate {len(records)}/270 groups; complete={complete}; {target.name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "q3_output")
    parser.add_argument("--datasets", default="NY,BAY,COL")
    parser.add_argument("--query-ids", default="", help="comma-separated official IDs; empty means all")
    parser.add_argument("--dimensions", default="2,3,5")
    parser.add_argument("--epsilons", default="0.05,0.1,0.2")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--algorithm", choices=("apex", "baseline"), default="apex")
    parser.add_argument("--order", default="21345", help="full objective priority, filtered to participating dimensions")
    parser.add_argument("--retry-from", type=Path, help="run only uncertified configurations recorded in this directory")
    parser.add_argument("--exact-2d", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seeds", type=int, default=12)
    parser.add_argument("--max-seconds", type=float, default=60)
    parser.add_argument("--max-labels", type=int, default=2000000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--aggregate", action="store_true", help="aggregate only; do not start jobs")
    parser.add_argument("--export-epsilon", default="0.1")
    parser.add_argument("--researcher", default="XXX")
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not args.researcher or any(c in args.researcher for c in '/\\:*?"<>|'):
        parser.error("invalid researcher identifier")
    if args.aggregate:
        aggregate(root, out, args.export_epsilon, args.researcher, args.exact_2d)
        return
    exe = (args.executable or CODE_DIR / ("task3_solver.exe" if os.name == "nt" else "task3_solver")).resolve()
    ds_set = set(args.datasets.split(","))
    dims = sorted(set(map(int, args.dimensions.split(","))))
    if not ds_set <= {"NY", "BAY", "COL"} or not set(dims) <= {2, 3, 5}:
        parser.error("invalid datasets/dimensions")
    if not 1 <= args.workers <= 32:
        parser.error("workers must be between 1 and 32")
    all_queries = queries(root)
    ids = set(args.query_ids.split(",")) if args.query_ids else set()
    selected = [q for q in all_queries if q["dataset"] in ds_set and (not ids or q["query_id"] in ids)]
    if not selected or (ids - {q["query_id"] for q in selected}):
        parser.error("unknown or empty query selection")
    fingerprints = {"binary_sha256": sha256(exe), "solver_source_sha256": sha256(CODE_DIR / "task3_solver.cpp")}
    data_hash = {ds: {"edges_sha256": sha256(root / "data" / "edges" / f"edges_{ds}_5obj.txt"),
                     "queries_sha256": sha256(root / "data" / f"dimacs5_{ds.lower()}" / "queries_problem34.csv")}
                 for ds in ds_set}
    cp = out / "checkpoints"; cp.mkdir(exist_ok=True)
    logs = out / "logs"; logs.mkdir(exist_ok=True)
    jobs = []
    for q in selected:
        for m in dims:
            configs = [(str(float(e)), False) for e in args.epsilons.split(",")]
            if args.exact_2d and m == 2:
                configs.append(("0.0", False))
            if args.baseline:
                configs.append(("0.0", True))
            for eps, baseline in dict.fromkeys(configs):
                meta = {**q, "objective_count": m, "epsilon": float(eps), "seed_only": baseline,
                        "algorithm": args.algorithm,
                        "order": args.order,
                        "seed_count": args.seeds, "max_seconds": args.max_seconds, "max_labels": args.max_labels,
                        **fingerprints, **data_hash[q["dataset"]]}
                ident = hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()[:16]
                name = f'{q["dataset"]}_{q["query_id"]}_m{m}_{"seed" if baseline else "e"+eps}_{ident}'
                jobs.append((name, meta))

    if args.retry_from:
        retry = set()
        for file in (args.retry_from / "checkpoints").glob("*.json"):
            r = json.loads(file.read_text(encoding="utf-8"))
            if not r["certified"] and not r["seed_only"]:
                retry.add((r["dataset"], r["query_id"], r["objective_count"], r["epsilon"]))
        jobs = [(name, meta) for name, meta in jobs if not meta["seed_only"] and
                (meta["dataset"], meta["query_id"], meta["objective_count"], meta["epsilon"]) in retry]

    def worker(job):
        name, meta = job
        file = cp / (name + ".json")
        if file.exists():
            if not args.resume:
                raise RuntimeError(f"checkpoint exists; use --resume: {file.name}")
            r = json.loads(file.read_text(encoding="utf-8"))
            if any(r.get(k) != v for k, v in meta.items()):
                raise RuntimeError("checkpoint metadata mismatch")
            return name, r, True
        temp = cp / (name + ".worker.tmp")
        if temp.exists():
            raise RuntimeError(f"stale or active worker temporary file: {temp.name}")
        cmd = [str(exe), "--edges", str(root / "data" / "edges" / f'edges_{meta["dataset"]}_5obj.txt'),
               "--algorithm", args.algorithm,
               "--order", args.order,
               "--source", str(meta["source"]), "--target", str(meta["target"]),
               "--objectives", str(meta["objective_count"]), "--epsilon", format(meta["epsilon"], ".6f"),
               "--seeds", str(args.seeds), "--max-seconds", str(args.max_seconds),
               "--max-labels", str(args.max_labels), "--output", str(temp)]
        if meta["seed_only"]:
            cmd.append("--seed-only")
        start = time.perf_counter()
        with (logs / (name + ".log")).open("w", encoding="utf-8") as stream:
            result = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"worker failed: {name}; see log")
        r = json.loads(temp.read_text(encoding="utf-8"))
        for k in ("source", "target", "objective_count", "epsilon", "seed_only", "seed_count", "algorithm", "order"):
            if r[k] != meta[k]:
                raise RuntimeError(f"solver metadata mismatch: {name}/{k}")
        r.update(meta); r["wall_seconds"] = time.perf_counter() - start
        atomic_json(file, r); temp.unlink()
        return name, r, False

    failures = []
    started = time.perf_counter()
    print(f"start jobs={len(jobs)} workers={args.workers}", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(worker, job): job[0] for job in jobs}
        for i, future in enumerate(as_completed(pending), 1):
            try:
                name, r, resumed = future.result()
                print(f'{i}/{len(jobs)} {name} status={r["status"]} paths={len(r["paths"])} '
                      f'search_s={r["search_seconds"]:.3f} resumed={resumed}', flush=True)
            except Exception as exc:
                failures.append(str(exc)); print(f"FAIL: {exc}", flush=True)
    atomic_json(out / "run_summary.json", {"requested_jobs": len(jobs), "failures": failures,
                "wall_seconds": time.perf_counter()-started})
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
