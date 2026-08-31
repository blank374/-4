"""Audit task-4 provenance, paths, decisions, and exact scalar optima.

The independent optimizer is Python bidirectional Dijkstra with arbitrary-size
integers; it does not use the C++ solver's reverse potentials or A* search.
"""
import argparse
from array import array
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from fractions import Fraction
import heapq
import json
import math
from pathlib import Path
import time

from run_task3 import ROOT, atomic_json, queries, sha256
from task4_common import HEADER, SCHEMES, candidate_front, closed_pairs
from verify_task3_results import read_csr

_CACHE = None


def graph(root, ds):
    global _CACHE
    if _CACHE is not None and _CACHE[0] == (str(root), ds):
        return _CACHE[1]
    file = root / "data" / "edges" / f"edges_{ds}_5obj.txt"
    closure = root / "data" / f"dimacs5_{ds.lower()}" / "closed_edges_problem4.csv"
    closed = closed_pairs(closure)
    off, col = read_csr(file); n = len(off)-1; m = len(col[0])
    origin = array("I", [0])*m; counts = array("I", [0])*n
    blocked = bytearray(m); found = set()
    for u in range(n):
        for k in range(off[u], off[u+1]):
            v = col[0][k]; origin[k] = u; counts[v] += 1
            if (u, v) in closed:
                blocked[k] = 1; found.add((u, v))
    assert found == closed, "closure pair absent from original graph"
    rev = array("I", [0])
    for count in counts:
        rev.append(rev[-1]+count)
    cursor = array("I", rev[:-1]); rk = array("I", [0])*m
    for k, v in enumerate(col[0]):
        rk[cursor[v]] = k; cursor[v] += 1
    result = (off, col, origin, rev, rk, blocked, {
        "edges_sha256": sha256(file), "closures_sha256": sha256(closure),
        "queries_sha256": sha256(root / "data" / f"dimacs5_{ds.lower()}" / "queries_problem34.csv")})
    _CACHE = ((str(root), ds), result)
    return result


def audit_path(p, g, source, target, disrupted=False, coeff=None):
    if p is None:
        return 0
    off, col, _, _, _, blocked, _ = g
    vs, es = p["vertices"], p["edge_indices"]
    assert vs and vs[0] == source and vs[-1] == target
    assert len(vs) == len(es)+1 and len(vs) == len(set(vs)), "non-simple path"
    cost = [0]*5
    for u, v, k in zip(vs, vs[1:], es):
        assert 0 <= u < len(off)-1 and off[u] <= k < off[u+1]
        assert col[0][k] == v and (not disrupted or not blocked[k]), "invalid/closed arc"
        for j in range(5):
            cost[j] += col[j+1][k]
    assert cost == p["cost"], "five edge sums disagree"
    if coeff is not None:
        assert int(p["scalar"]) == sum(a*c for a, c in zip(coeff, cost))
    return 1


def bidirectional(g, edge_cost, source, target, disrupted, upper=None):
    """Exact distance; upper must be the value of an independently audited path."""
    if source == target:
        return 0
    off, col, origin, rev, rk, blocked, _ = g; n = len(off)-1
    dist = [[None]*n, [None]*n]; done = [bytearray(n), bytearray(n)]
    dist[0][source] = 0; dist[1][target] = 0
    heaps = [[(0, source)], [(0, target)]]
    while True:
        for d in (0, 1):
            h = heaps[d]
            while h and (done[d][h[0][1]] or dist[d][h[0][1]] != h[0][0]):
                heapq.heappop(h)
        if not heaps[0] or not heaps[1]:
            return upper
        if upper is not None and heaps[0][0][0]+heaps[1][0][0] >= upper:
            return upper
        d = 0 if heaps[0][0][0] <= heaps[1][0][0] else 1
        value, u = heapq.heappop(heaps[d]); done[d][u] = 1
        arcs = range(off[u], off[u+1]) if d == 0 else (rk[i] for i in range(rev[u], rev[u+1]))
        for k in arcs:
            if disrupted and blocked[k]:
                continue
            v = col[0][k] if d == 0 else origin[k]; nd = value+edge_cost[k]
            other = dist[1-d][v]
            if other is not None and (upper is None or nd+other < upper):
                upper = nd+other
            if not done[d][v] and (dist[d][v] is None or nd < dist[d][v]):
                dist[d][v] = nd; heapq.heappush(heaps[d], (nd, v))


def choose(paths, weights, span):
    a = [Fraction(w, r) for w, r in zip(weights, span)]
    return min(paths, key=lambda p: (sum(c*x for c, x in zip(p["cost"], a)),
                                    p["cost"], p["vertices"], p["edge_indices"])) if paths else None


def same_path(p, q):
    return (p is None and q is None) or (p is not None and q is not None and
        all(p[k] == q[k] for k in ("cost", "vertices", "edge_indices")))


def audit_query(args):
    root, task3, file, full = args
    root, task3, file = Path(root), Path(task3), Path(file)
    started = time.perf_counter(); r = json.loads(file.read_text(encoding="utf-8"))
    ds = r["dataset"]; g = graph(root, ds); source, target = r["source"], r["target"]
    assert r["schema"] == "TASK4_V1" and r["complete"]
    assert all(r[k] == v for k, v in g[-1].items())
    assert r["closed_pairs"] == 50 and r["removed_edges"] == sum(g[5])
    selected = {s["checkpoint"]: s["sha256"] for s in json.loads((task3/"selection.json").read_text(encoding="utf-8"))}
    raw = []; dimensions = set(); checked = 0
    for name, expected_hash in r["task3_checkpoints"].items():
        p = task3/"checkpoints"/name
        assert p.name == name and sha256(p) == expected_hash == selected[name]
        c = json.loads(p.read_text(encoding="utf-8")); dimensions.add(c["objective_count"])
        assert c["certified"] and (c["dataset"], c["query_id"], c["source"], c["target"]) == (ds, r["query_id"], source, target)
        assert c["edges_sha256"] == r["edges_sha256"] and c["queries_sha256"] == r["queries_sha256"]
        raw.extend(c["paths"])
    assert dimensions == {2, 3, 5} and len(r["task3_checkpoints"]) == 3
    for p in raw:
        checked += audit_path(p, g, source, target)
    front = candidate_front(raw)
    low = [min(p["cost"][j] for p in front) for j in range(5)] if front else [0]*5
    span = [max(1, max(p["cost"][j] for p in front)-low[j]) for j in range(5)] if front else [1]*5
    common = math.lcm(*span)
    assert low == r["normalization_low"] and span == r["normalization_span"] and common == int(r["common_denominator"])
    available = [p for p in raw if not any(g[5][k] for k in p["edge_indices"])]
    assert len(raw) == r["raw_candidate_records"] and len(front) == r["candidate_front_size"]
    assert len(available) == r["surviving_raw_records"]
    assert sum(not any(g[5][k] for k in p["edge_indices"]) for p in front) == r["surviving_front_size"]
    assert r["weights"] == {k: list(v) for k, v in SCHEMES.items()}
    assert [s["name"] for s in r["schemes"]] == list(SCHEMES)
    optimality_checks = 0
    for s in r["schemes"]:
        weights = SCHEMES[s["name"]]
        coeff = [int(Fraction(w, x)*common) for w, x in zip(weights, span)]
        assert list(map(int, s["coefficients"])) == coeff
        assert same_path(s["original"], choose(front, weights, span))
        assert same_path(s["warm_start"], choose(available, weights, span))
        for kind in ("original", "original_optimal", "warm_start", "disrupted"):
            checked += audit_path(s[kind], g, source, target, kind in ("warm_start", "disrupted"), coeff)
        orig, opt, dis = s["original"], s["original_optimal"], s["disrupted"]
        assert bool(orig) == bool(opt)
        if orig:
            assert int(opt["scalar"]) <= int(orig["scalar"])
            assert 5*int(orig["scalar"]) <= 6*int(opt["scalar"]), "candidate exceeds epsilon=.2 scalar bound"
            if s["name"] == "time_shortest":
                assert int(orig["scalar"]) == int(opt["scalar"])
        if dis:
            assert opt and int(dis["scalar"]) >= int(opt["scalar"])
        if full:
            divisor = math.gcd(*coeff); a = [x//divisor for x in coeff]
            cols = g[1][1:]
            edge_cost = [sum(x*c for x, c in zip(a, cs)) for cs in zip(*cols)]
            for kind, disrupted in (("original_optimal", False), ("disrupted", True)):
                expected = int(s[kind]["scalar"])//divisor if s[kind] else None
                actual = bidirectional(g, edge_cost, source, target, disrupted, expected)
                assert actual == expected, f"independent optimum mismatch: {s['name']}/{kind}"
                optimality_checks += 1
    for state in ("original", "disrupted"):
        assert len({bool(s[state]) for s in r["schemes"]}) == 1
    assert len(r["sensitivity"]) == 22
    for i, row in enumerate(r["sensitivity"]):
        family, k = ("time_share" if i < 11 else "stability_share"), i % 11
        weights = [10-k, 4*k, 10-k, 10-k, 10-k] if i < 11 else [6*(10-k), 9*(10-k), 14*k, 10*k, 9*(10-k)]
        assert row["family"] == family and row["parameter"] == k/10 and row["weights"] == weights
        p = choose(front, weights, span)
        assert row["selected_cost"] == (p["cost"] if p else None)
    return {"dataset": ds, "query_id": r["query_id"], "checkpoint": file.name,
            "sha256": sha256(file), "checked_paths": checked, "optimality_checks": optimality_checks,
            "seconds": time.perf_counter()-started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--task3-dir", type=Path, default=ROOT/"results_task3_certified")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--paths-only", action="store_true")
    args = parser.parse_args(); started = time.perf_counter()
    if not 1 <= args.workers <= 32:
        parser.error("workers must be between 1 and 32")
    out = args.output_dir.resolve(); files = sorted((out/"checkpoints").glob("*.json"))
    assert files, "no checkpoints"
    expected = {(q["dataset"], q["query_id"]): q for q in queries(args.root)}
    records = {}; csv_rows = []
    for file in files:
        r = json.loads(file.read_text(encoding="utf-8")); key = r["dataset"], r["query_id"]
        assert key in expected and key not in records
        assert (r["source"], r["target"]) == (expected[key]["source"], expected[key]["target"])
        records[key] = r
    manifest = json.loads((out/"aggregation.json").read_text(encoding="utf-8"))
    assert manifest["complete"] == (set(records) == set(expected))
    assert manifest["queries"] == len(records) and manifest["rows"] == 8*len(records)
    csv_file = out/manifest["file"]
    assert sha256(csv_file) == manifest["sha256"]
    for key in expected:
        if key not in records:
            continue
        r = records[key]
        for s in r["schemes"]:
            for state in ("original", "disrupted"):
                p = s[state]
                csv_rows.append(list(map(str, [*key, r["source"], r["target"], s["name"], state, bool(p)]))+
                                (list(map(str, p["cost"]))+["->".join(map(str, p["vertices"]))] if p else [""]*6))
    with csv_file.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        assert next(reader) == HEADER and list(reader) == csv_rows, "CSV differs from audited checkpoints"
    checks = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(audit_query, (str(args.root.resolve()), str(args.task3_dir.resolve()), str(f), not args.paths_only)) for f in files]
        for future in as_completed(pending):
            row = future.result(); checks.append(row)
            print(f"{len(checks)}/{len(files)} {row['dataset']}/{row['query_id']} paths={row['checked_paths']} optima={row['optimality_checks']}", flush=True)
    report = {"complete": manifest["complete"], "full_optimality": not args.paths_only,
              "queries": len(checks), "csv_rows": len(csv_rows), "csv_sha256": sha256(csv_file),
              "checked_paths": sum(c["checked_paths"] for c in checks),
              "optimality_checks": sum(c["optimality_checks"] for c in checks),
              "seconds": time.perf_counter()-started,
              "checks": sorted(checks, key=lambda c: (c["dataset"], c["query_id"]))}
    atomic_json(out/("path_verification_report.json" if args.paths_only else "verification_report.json"), report)
    print(f"PASS: {report['queries']} queries, {report['csv_rows']} rows, {report['optimality_checks']} independent optima", flush=True)


if __name__ == "__main__":
    main()
