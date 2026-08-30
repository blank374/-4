"""赛题任务一：三个有向道路网上的五目标单目标最短路。

用法（在项目根目录运行）：
    python task1_solver.py
    python task1_solver.py --researcher 123 --output-dir results

边文件格式：src dst distance travel_time elevation avg_degree hop_count
查询格式：query_id,source,target
"""
from __future__ import annotations

import argparse
import csv
import heapq
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


OBJECTIVES = ("distance", "travel_time", "elevation", "avg_degree", "hop_count")
FIELDS = ("distance", "travel_time", "elevation", "avg_degree", "hop_count")


@dataclass(frozen=True, slots=True)
class Edge:
    dst: int
    costs: tuple[float, float, float, float, float]


def fmt_number(x: float) -> str:
    if math.isfinite(x) and x.is_integer():
        return str(int(x))
    return format(x, ".15g")


class RoadGraph:
    def __init__(self) -> None:
        self.adj: dict[int, list[Edge]] = {}
        self.edge_pairs: set[tuple[int, int]] = set()
        self.edge_count = 0

    @classmethod
    def from_edge_file(cls, path: Path) -> "RoadGraph":
        graph = cls()
        with path.open("r", encoding="utf-8") as f:
            for line_no, raw in enumerate(f, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 7:
                    raise ValueError(f"{path}:{line_no}: expected 7 fields, got {len(parts)}")
                src, dst = int(parts[0]), int(parts[1])
                costs = tuple(float(v) for v in parts[2:7])
                if any(v < 0 for v in costs):
                    raise ValueError(f"{path}:{line_no}: edge weights must be non-negative")
                graph.adj.setdefault(src, []).append(Edge(dst, costs))
                graph.adj.setdefault(dst, [])
                graph.edge_pairs.add((src, dst))
                graph.edge_count += 1
        return graph

    def shortest_path(self, source: int, target: int, objective_index: int) -> tuple[list[int], list[Edge]] | None:
        """Exact Dijkstra; predecessor stores the actual selected edge (parallel-safe)."""
        if source not in self.adj or target not in self.adj:
            return None
        if source == target:
            return [source], []
        inf = math.inf
        dist: dict[int, float] = {source: 0.0}
        predecessor: dict[int, tuple[int, Edge]] = {}
        settled: set[int] = set()
        heap: list[tuple[float, int]] = [(0.0, source)]
        while heap:
            current_distance, node = heapq.heappop(heap)
            if node in settled or current_distance != dist.get(node, inf):
                continue
            settled.add(node)
            if node == target:
                break
            for edge in self.adj[node]:
                if edge.dst in settled:
                    continue
                candidate = current_distance + edge.costs[objective_index]
                if candidate < dist.get(edge.dst, inf):
                    dist[edge.dst] = candidate
                    predecessor[edge.dst] = (node, edge)
                    heapq.heappush(heap, (candidate, edge.dst))
        if target not in settled:
            return None
        nodes: list[int] = [target]
        edges: list[Edge] = []
        node = target
        while node != source:
            prev, edge = predecessor[node]
            if edge.dst != node:
                raise AssertionError("predecessor edge does not end at current node")
            nodes.append(prev)
            edges.append(edge)
            node = prev
        nodes.reverse()
        edges.reverse()
        return nodes, edges


def read_queries(path: Path) -> list[tuple[str, int, int]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"query_id", "source", "target"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"{path}: missing query columns {required}")
        return [(str(row["query_id"]), int(row["source"]), int(row["target"])) for row in reader]


def validate_and_sum(graph: RoadGraph, nodes: list[int], edges: list[Edge]) -> tuple[float, ...]:
    if not nodes or len(edges) != len(nodes) - 1:
        raise AssertionError("invalid path/edge count")
    if len(nodes) != len(set(nodes)):
        raise AssertionError("path contains repeated nodes")
    totals = [0.0] * 5
    for i, edge in enumerate(edges):
        if edge.dst != nodes[i + 1] or (nodes[i], nodes[i + 1]) not in graph.edge_pairs:
            raise AssertionError(f"missing directed edge {nodes[i]}->{nodes[i + 1]}")
        for j, value in enumerate(edge.costs):
            totals[j] += value
    return tuple(totals)


def solve_dataset(dataset: str, root: Path, output_path: Path, write_header: bool) -> tuple[float, int]:
    edge_path = root / "data" / "edges" / f"edges_{dataset}_5obj.txt"
    query_path = root / "data" / f"dimacs5_{dataset.lower()}" / "queries_problem1.csv"
    graph_start = time.perf_counter()
    graph = RoadGraph.from_edge_file(edge_path)
    load_seconds = time.perf_counter() - graph_start
    queries = read_queries(query_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    run_start = time.perf_counter()
    with output_path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        if write_header:
            writer.writerow(["dataset", "query_id", "source", "target", "objective", *[f"c{i}" for i in range(1, 6)], "path"])
        for query_id, source, target in queries:
            for objective_index, objective in enumerate(OBJECTIVES):
                result = graph.shortest_path(source, target, objective_index)
                if result is None:
                    raise RuntimeError(f"no legal path for {dataset}/{query_id}: {source}->{target}")
                nodes, edges = result
                totals = validate_and_sum(graph, nodes, edges)
                writer.writerow([dataset, query_id, source, target, objective,
                                 *[fmt_number(v) for v in totals], "->".join(map(str, nodes))])
                rows += 1
    elapsed = time.perf_counter() - run_start
    print(f"{dataset}: nodes={len(graph.adj):,}, edges={graph.edge_count:,}, "
          f"queries={len(queries)}, rows={rows}, load={load_seconds:.3f}s, solve={elapsed:.3f}s")
    return load_seconds + elapsed, rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Solve problem 1 for NY, BAY and COL")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--researcher", default="XXX", help="result1_研XXX.csv 中的编号")
    args = parser.parse_args()
    root = args.root.resolve()
    total_start = time.perf_counter()
    output_dir = (args.output_dir or root).resolve()
    output_path = output_dir / f"result1_研{args.researcher}.csv"
    if output_path.exists():
        output_path.unlink()
    outputs = []
    for dataset in ("NY", "BAY", "COL"):
        outputs.append(solve_dataset(dataset, root, output_path, not outputs))
    print(f"finished: file={output_path}, rows={sum(x[1] for x in outputs)}, total={time.perf_counter()-total_start:.3f}s")


if __name__ == "__main__":
    main()
