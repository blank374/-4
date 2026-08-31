"""Select certified results only, preserving every experiment and its metadata.

Sources are ordered: use the first certified configuration for each group.
Defaults require exact 2D and epsilon=0.2 for 3D/5D, all 270 official groups.
"""
import argparse
import json
from pathlib import Path
import shutil

from run_task3 import ROOT, aggregate, atomic_json, queries, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results_task3_certified")
    parser.add_argument("--epsilon", type=float, default=.2)
    parser.add_argument("--researcher", default="XXX")
    args = parser.parse_args()
    expected = {(q["dataset"], q["query_id"], m): q for q in queries(args.root) for m in (2, 3, 5)}
    chosen = {}
    for source in args.sources:
        for file in sorted((source / "checkpoints").glob("*.json")):
            r = json.loads(file.read_text(encoding="utf-8"))
            key = r["dataset"], r["query_id"], r["objective_count"]
            if key not in expected or r["seed_only"] or not r["certified"]:
                continue
            if r["epsilon"] != (0. if key[2] == 2 else args.epsilon):
                continue
            q = expected[key]
            if (r["source"], r["target"]) != (q["source"], q["target"]):
                raise ValueError("official endpoints changed")
            if key not in chosen:
                chosen[key] = (file, {"dataset": key[0], "query_id": key[1], "objective_count": key[2],
                    "source_directory": source.name, "checkpoint": file.name, "sha256": sha256(file),
                    "algorithm": r.get("algorithm", "baseline"), "order": r.get("order", "21345"),
                    "epsilon": r["epsilon"], "max_seconds": r["max_seconds"], "max_labels": r["max_labels"]})
    if set(chosen) != set(expected):
        missing = sorted(set(expected)-set(chosen))
        raise ValueError(f"not all groups have certificates; missing: {missing}")
    out = args.output_dir.resolve(); cp = out / "checkpoints"; cp.mkdir(parents=True, exist_ok=True)
    expected_files = {entry[0].name for entry in chosen.values()}
    if {f.name for f in cp.iterdir()} - expected_files:
        raise ValueError("output directory contains other configurations; choose a new directory")
    for file, info in chosen.values():
        target = cp / file.name
        if target.exists():
            if sha256(target) != info["sha256"]:
                raise ValueError("existing selected checkpoint changed")
        else:
            shutil.copy2(file, target)
    atomic_json(out / "selection.json", [chosen[key][1] for key in expected])
    aggregate(args.root.resolve(), out, args.epsilon, args.researcher, exact_2d=True)
    print("PASS: all 270 groups certified; original experiments unchanged", flush=True)


if __name__ == "__main__":
    main()
