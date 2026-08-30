#!/usr/bin/env python3
"""Exact three-objective Pareto shortest paths for NY/BAY/COL."""
from __future__ import annotations
import argparse, csv, heapq, math, time
from dataclasses import dataclass
from pathlib import Path

OBJ = ("distance", "travel_time", "elevation")
OUT = ("dataset", "query_id", "source", "target", "solution_id", "c1", "c2", "c3")
Label = tuple[float, float, float]

@dataclass(frozen=True, slots=True)
class Edge:
    dst: int
    cost: Label

class Graph:
    def __init__(self):
        self.adj: dict[int, list[Edge]] = {}
        self.rev: dict[int, list[Edge]] = {}
        self.m = 0

    @classmethod
    def load(cls, path: Path) -> "Graph":
        g = cls()
        with path.open(encoding="utf-8") as f:
            for no, raw in enumerate(f, 1):
                line = raw.strip()
                if not line or line.startswith("#"): continue
                p = line.split()
                if len(p) < 7: raise ValueError(f"{path}:{no}: expected 7 fields")
                u, v = int(p[0]), int(p[1]); c = tuple(float(x) for x in p[2:5])
                if any(x < 0 for x in c): raise ValueError(f"{path}:{no}: negative weight")
                e = Edge(v, c); g.adj.setdefault(u, []).append(e); g.adj.setdefault(v, [])
                g.rev.setdefault(v, []).append(Edge(u, c)); g.rev.setdefault(u, []); g.m += 1
        return g

def leq(a: Label, b: Label) -> bool: return a[0] <= b[0] and a[1] <= b[1] and a[2] <= b[2]
def strictly_better(a: Label, b: Label) -> bool: return leq(a, b) and a != b

def scalar_reverse_lb(g: Graph, target: int, component: int) -> dict[int, float]:
    d = {target: 0.0}; h = [(0.0, target)]
    while h:
        x, u = heapq.heappop(h)
        if x != d.get(u): continue
        for e in g.rev[u]:
            y = x + e.cost[component]
            if y < d.get(e.dst, math.inf): d[e.dst] = y; heapq.heappush(h, (y, e.dst))
    return d

def insert(labels: list[Label], seen: set[Label], x: Label) -> bool:
    """Insert x iff non-dominated; delete labels strictly dominated by x."""
    if x in seen: return False
    for old in labels:
        if leq(old, x): return False
    kept = [old for old in labels if not strictly_better(x, old)]
    removed = set(labels) - set(kept)
    labels[:] = kept; seen.difference_update(removed)
    labels.append(x); seen.add(x); return True

def exact_pareto(g: Graph, source: int, target: int) -> list[Label]:
    if source not in g.adj or target not in g.adj: return []
    lb = [scalar_reverse_lb(g, target, j) for j in range(3)]
    labels: dict[int, list[Label]] = {source: [(0.0, 0.0, 0.0)]}
    seen: dict[int, set[Label]] = {source: {(0.0, 0.0, 0.0)}}
    # A label whose componentwise scalar lower-bound completion is dominated
    # by a target label cannot lead to any new Pareto solution.
    target_labels: list[Label] = []
    target_seen: set[Label] = set()
    h = [(0.0, 0, source, (0.0, 0.0, 0.0))]
    while h:
        _, _, u, base = heapq.heappop(h)
        if base not in seen.get(u, set()): continue
        if u == target:
            insert(target_labels, target_seen, base)
            continue
        for e in g.adj[u]:
            x = (base[0] + e.cost[0], base[1] + e.cost[1], base[2] + e.cost[2])
            if e.dst not in lb[0] or e.dst not in lb[1] or e.dst not in lb[2]: continue
            completion = (x[0] + lb[0][e.dst], x[1] + lb[1][e.dst], x[2] + lb[2][e.dst])
            if any(leq(t, completion) for t in target_labels): continue
            arr = labels.setdefault(e.dst, []); ss = seen.setdefault(e.dst, set())
            if insert(arr, ss, x): heapq.heappush(h, (sum(x), len(h), e.dst, x))
    return sorted(target_labels)

def read_queries(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames or not {"query_id", "source", "target"}.issubset(r.fieldnames): raise ValueError(f"bad query file {path}")
        return [(row["query_id"], int(row["source"]), int(row["target"])) for row in r]

def solve(root: Path, output: Path, researcher: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists(): output.unlink()
    total_start = time.perf_counter(); total_rows = 0
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(OUT)
        for ds in ("NY", "BAY", "COL"):
            gf = root / "data" / "edges" / f"edges_{ds}_5obj.txt"
            qf = root / "data" / f"dimacs5_{ds.lower()}" / "queries_problem2.csv"
            t0 = time.perf_counter(); g = Graph.load(gf); qs = read_queries(qf); nrows = 0
            for qid, s, t in qs:
                front = exact_pareto(g, s, t)
                for i, x in enumerate(front, 1): w.writerow((ds, qid, s, t, i, *[fmt(v) for v in x])); nrows += 1
            total_rows += nrows
            print(f"{ds}: nodes={len(g.adj):,}, edges={g.m:,}, queries={len(qs)}, Pareto rows={nrows}, seconds={time.perf_counter()-t0:.3f}")
    print(f"finished: {output}, rows={total_rows}, total_seconds={time.perf_counter()-total_start:.3f}")

def fmt(x: float) -> str: return str(int(x)) if x.is_integer() else format(x, ".15g")

if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, default=Path(__file__).resolve().parent); p.add_argument("--output-dir", type=Path, default=None); p.add_argument("--researcher", default="XXX"); a = p.parse_args()
    solve(a.root.resolve(), ((a.output_dir or a.root).resolve() / f"result2_研{a.researcher}.csv"), a.researcher)
