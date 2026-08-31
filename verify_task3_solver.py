"""Independent exhaustive simple-path oracle for the task-3 executable."""
import argparse
import json
import math
from pathlib import Path
import random
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent


def dominates(a, b):
    return all(x <= y for x, y in zip(a, b))


def frontier(costs, m):
    result = []
    for cost in sorted({tuple(c[:m]) for c in costs}):
        if not any(dominates(a, cost) for a in result):
            result.append(cost)
    return set(result)


def brute(edges, source, target):
    adj = {}
    for u, v, *cost in edges:
        adj.setdefault(u, []).append((v, cost))
    result = []

    def dfs(u, visited, cost):
        if u == target:
            result.append(cost)
            return
        for v, c in adj.get(u, []):
            if v not in visited:
                dfs(v, visited | {v}, tuple(a + b for a, b in zip(cost, c)))

    dfs(source, {source}, (0,) * 5)
    return result


def validate_paths(result, edges):
    csr = sorted(edges, key=lambda e: e[0])  # stable, preserves parallel-edge identity
    costs = []
    for path in result["paths"]:
        vs, ids = path["vertices"], path["edge_indices"]
        assert vs[0] == result["source"] and vs[-1] == result["target"]
        assert len(set(vs)) == len(vs) and len(ids) + 1 == len(vs)
        cost = [0] * 5
        for u, v, k in zip(vs, vs[1:], ids):
            e = csr[k]
            assert (u, v) == tuple(e[:2])
            cost = [a + b for a, b in zip(cost, e[2:])]
        assert cost == path["cost"]
        costs.append(cost)
    m = result["objective_count"]
    assert len(frontier(costs, m)) == len(costs), "duplicates or dominated output"
    return costs


def run(exe, folder, edges, s, t, m, eps, extra=()):
    graph, output = folder / "edges.txt", folder / "result.json"
    graph.write_text("\n".join(" ".join(map(str, e)) for e in edges), encoding="utf-8")
    output.unlink(missing_ok=True)
    cmd = [str(exe), "--edges", str(graph), "--source", str(s), "--target", str(t),
           "--objectives", str(m), "--epsilon", str(eps), "--seeds", str(m + 2),
           "--max-seconds", "0", "--output", str(output), *extra]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    costs = validate_paths(result, edges)
    return result, costs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", nargs="?", default=ROOT / "task3_solver.exe")
    parser.add_argument("--cases", type=int, default=160)
    parser.add_argument("--algorithm", choices=("apex", "baseline"), default="apex")
    parser.add_argument("--order", default="21345")
    args = parser.parse_args()
    rng = random.Random(3405)
    count = 0
    merges = 0
    common = ["--algorithm", args.algorithm, "--order", args.order]
    (ROOT / "tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="task3_oracle_", dir=ROOT / "tmp") as temporary:
        folder = Path(temporary)
        for case in range(args.cases):
            n = rng.randrange(2, 8)
            edges = []
            for u in range(n):
                for v in range(n):
                    if rng.random() < .23:
                        edges.append([u, v, *[rng.randrange(0, 10) for _ in range(5)]])
                        if rng.random() < .15:
                            edges.append([u, v, *[rng.randrange(0, 10) for _ in range(5)]])
            # Retain isolated endpoints; include all-zero cycles and parallel edges.
            edges.extend([[n-1, n-1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0]])
            if case % 4 == 0:
                edges.extend([[0, 1, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0]])
            s, t = rng.randrange(n), rng.randrange(n)
            oracle = brute(edges, s, t)
            for m in (2, 3, 5):
                exact = frontier(oracle, m)
                for eps in ("0", "0.05", "0.2"):
                    result, costs = run(Path(args.executable).resolve(), folder, edges, s, t, m, eps, common)
                    assert result["certified"]
                    if eps == "0":
                        assert frontier(costs, m) == exact, (case, m, exact, costs)
                    num, den = result["epsilon_numerator"], result["epsilon_denominator"]
                    for b in exact:
                        assert any(all(a[j]*den <= (den+num)*b[j] for j in range(m)) for a in costs)
                    count += 1
                    merges += result.get("merged", 0)
        # Layered parallel-edge graphs force OPEN mergers and representative
        # replacement; random tiny graphs alone are often solved by the seeds.
        for case in range(18):
            edges = []
            for u in range(8):
                for _ in range(2):
                    distance = rng.randrange(1, 100)
                    edges.append([u, u+1, distance, 100-distance, rng.randrange(40), rng.randrange(1, 10), 1])
            oracle = brute(edges, 0, 8)
            for m in (2, 3, 5):
                exact = frontier(oracle, m)
                for eps in ("0", "0.000001", "0.05", "0.2"):
                    result, costs = run(Path(args.executable).resolve(), folder, edges, 0, 8, m, eps, [*common, "--seeds", str(m)])
                    assert result["certified"]
                    if eps == "0":
                        assert frontier(costs, m) == exact
                    num, den = result["epsilon_numerator"], result["epsilon_denominator"]
                    assert all(any(all(a[j]*den <= (den+num)*b[j] for j in range(m)) for a in costs) for b in exact)
                    count += 1
                    merges += result.get("merged", 0)
        # Resource caps must never be advertised as a completed cover.
        edges = [[0, 1, 1, 20, 1, 1, 1], [0, 1, 20, 1, 1, 1, 1],
                 [0, 1, 12, 12, 1, 1, 1], [1, 2, 1, 1, 1, 1, 1]]
        for extra, status in [(["--max-labels", "1"], "label_limit"),
                              (["--max-expanded", "1"], "expansion_limit"),
                              (["--max-seconds", "0.000000001"], "time_limit"),
                              (["--seed-only"], "seed_only")]:
            for eps in ("0", "0.05"):
                result, _ = run(Path(args.executable).resolve(), folder, edges, 0, 2, 2, eps, [*common, *extra])
                assert result["status"] == status and not result["certified"], result
                count += 1
    print(f"PASS: {count} independent oracle / coverage / resource-limit checks")
    if args.algorithm == "apex":
        assert merges > 100, "coverage tests did not exercise enough merges"
        print(f"Merges exercised by independent oracle tests: {merges}")
    from verify_task3_results import epsilon_indicator
    for _ in range(1000):
        points = sorted(frontier([(rng.randrange(10), rng.randrange(10)) for _ in range(10)], 2))
        reference = sorted(frontier([(rng.randrange(10), rng.randrange(10)) for _ in range(10)], 2))
        worst = 1.
        for b in reference:
            best = math.inf
            for a in points:
                ratio = 1.
                for x, y in zip(a, b):
                    if y == 0:
                        if x > 0:
                            ratio = math.inf
                    else:
                        ratio = max(ratio, x / y)
                best = min(best, ratio)
            worst = max(worst, best)
        assert epsilon_indicator(points, reference) == worst - 1.
    print("PASS: 1000 independent epsilon-indicator comparisons (including zeros)")


if __name__ == "__main__":
    main()
