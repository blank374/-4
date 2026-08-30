#!/usr/bin/env python3
"""Check duplicate-free and mutually non-dominated result2 output."""
import argparse, csv
from collections import defaultdict
from pathlib import Path

def dominates(a, b): return all(x <= y for x, y in zip(a, b)) and a != b

def main():
    p = argparse.ArgumentParser(); p.add_argument("csv_file", type=Path); a = p.parse_args()
    groups = defaultdict(list)
    with a.csv_file.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["dataset"], row["query_id"])
            x = tuple(float(row[f"c{i}"]) for i in range(1, 4))
            groups[key].append((int(row["solution_id"]), x))
    checked = 0
    for key, rows in groups.items():
        ids = [i for i, _ in rows]
        if ids != list(range(1, len(ids) + 1)): raise AssertionError(f"non-contiguous solution_id: {key}")
        vectors = [x for _, x in rows]
        if len(vectors) != len(set(vectors)): raise AssertionError(f"duplicate vector: {key}")
        for i, x in enumerate(vectors):
            if any(dominates(y, x) for j, y in enumerate(vectors) if i != j): raise AssertionError(f"dominated vector: {key} {x}")
        checked += len(rows)
    print(f"OK: {len(groups)} query groups, {checked} Pareto vectors; no duplicates or internal dominance")

if __name__ == "__main__": main()
