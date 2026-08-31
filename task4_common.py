"""Task-4 decision rules. Weights and original-network scales stay fixed after closure."""
from bisect import bisect_right
import csv
from fractions import Fraction
import json
import math
from pathlib import Path

SCHEMES = {
    "time_priority": (10, 60, 10, 10, 10),
    "stable_priority": (10, 15, 35, 25, 15),
    "balanced": (20, 20, 20, 20, 20),
    "time_shortest": (0, 100, 0, 0, 0),
}
HEADER = ["dataset", "query_id", "source", "target", "scheme", "network_state", "feasible",
          "c1", "c2", "c3", "c4", "c5", "path"]


def closed_pairs(file, expected_count=50):
    with Path(file).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["closed_from", "closed_to"]:
            raise ValueError("invalid closure header")
        rows = [(int(r["closed_from"]), int(r["closed_to"])) for r in reader]
    if len(rows) != len(set(rows)) or (expected_count is not None and len(rows) != expected_count):
        raise ValueError("closure table must contain the expected number of unique directed pairs")
    return set(rows)


def load_candidates(files):
    paths = []
    records = []
    for file in files:
        r = json.loads(Path(file).read_text(encoding="utf-8"))
        if not r["certified"]:
            raise ValueError("task4 expects the certified task3 export")
        paths.extend(r["paths"]); records.append(r)
    return paths, records


def candidate_front(paths):
    unique = {}
    for p in paths:
        c = tuple(p["cost"])
        if c not in unique or (p["vertices"], p["edge_indices"]) < (unique[c]["vertices"], unique[c]["edge_indices"]):
            unique[c] = p
    kept, by_second, values = [], [], []
    # Sorted c1 means only predecessors with c2 <= current c2 can dominate.
    # This avoids a quadratic scan of the large exact two-objective front.
    for c in sorted(unique):
        end = bisect_right(by_second, c[1])
        if any(p[2] <= c[2] and p[3] <= c[3] and p[4] <= c[4] for p in values[:end]):
            continue
        kept.append(unique[c]); by_second.insert(end, c[1]); values.insert(end, c)
    return kept


def scales(paths):
    if not paths:
        return [0]*5, [1]*5, 1
    low = [min(p["cost"][j] for p in paths) for j in range(5)]
    span = [max(1, max(p["cost"][j] for p in paths)-low[j]) for j in range(5)]
    return low, span, math.lcm(*span)


def coefficients(weights, span, common):
    return [w * (common // r) for w, r in zip(weights, span)]


def scalar(cost, coeff):
    return sum(c*a for c, a in zip(cost, coeff))


def select(paths, coeff):
    return min(paths, key=lambda p: (scalar(p["cost"], coeff), p["cost"], p["vertices"], p["edge_indices"])) if paths else None


def survives(path, closed):
    return not any((u, v) in closed for u, v in zip(path["vertices"], path["vertices"][1:]))


def score(cost, coeff, low, common, weight_sum=100):
    return Fraction(scalar(cost, coeff)-scalar(low, coeff), weight_sum*common)


def sensitivity(paths, span, common):
    rows = []
    for family in ("time_share", "stability_share"):
        for k in range(11):
            if family == "time_share":
                weights = [10-k, 4*k, 10-k, 10-k, 10-k]
            else:
                weights = [6*(10-k), 9*(10-k), 14*k, 10*k, 9*(10-k)]
            coeff = coefficients(weights, span, common)
            p = select(paths, coeff)
            rows.append({"family": family, "parameter": k/10, "weights": weights,
                         "selected_cost": p["cost"] if p else None})
    return rows
