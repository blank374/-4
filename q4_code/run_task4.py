"""Task 4: recommend from task-3 candidates, then replan on the disrupted graph."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "q3_code"))
from run_task3 import ROOT, atomic_json, queries, sha256
from task4_common import SCHEMES, HEADER, candidate_front, closed_pairs, coefficients, load_candidates, scales, scalar, select, sensitivity, survives


def candidate_files(folder):
    result = {}
    for file in sorted((folder / "checkpoints").glob("*.json")):
        # Certified export has one selected configuration per query/dimension.
        parts = file.name.split("_")
        key = parts[0], parts[1]
        result.setdefault(key, []).append(file)
    return result


def write_job(file, source, target, configs):
    lines = ["TASK4_JOB_V1", f"{source} {target}", str(len(configs))]
    for name, config in configs.items():
        lines.extend([name, " ".join(map(str, config["coefficients"]))])
        for kind in ("original", "warm_start"):
            p = config[kind]
            lines.append("-1" if p is None else " ".join(map(str, [len(p["edge_indices"]), *p["edge_indices"]])))
    file.write_text("\n".join(lines)+"\n", encoding="utf-8")


def aggregate(root, out, researcher):
    if not researcher or any(c in researcher for c in '/\\:*?"<>|'):
        raise ValueError("invalid researcher identifier")
    expected = {(q["dataset"], q["query_id"]): q for q in queries(root)}
    records = {}
    for file in sorted((out / "checkpoints").glob("*.json")):
        r = json.loads(file.read_text(encoding="utf-8")); key = r["dataset"], r["query_id"]
        if key in records or key not in expected or not r.get("complete"):
            raise ValueError("duplicate, unexpected or incomplete checkpoint")
        q = expected[key]
        if (r["source"], r["target"]) != (q["source"], q["target"]):
            raise ValueError("wrong official endpoints")
        if [s["name"] for s in r["schemes"]] != list(SCHEMES):
            raise ValueError("wrong scheme set")
        records[key] = r
    complete = set(records) == set(expected)
    name = f'result4_研{researcher}{"" if complete else ".partial"}.csv'
    target = out / name; temporary = target.with_suffix(".csv.tmp")
    count = 0
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(HEADER)
        for key, q in expected.items():
            if key not in records:
                continue
            for scheme in records[key]["schemes"]:
                for state in ("original", "disrupted"):
                    p = scheme[state]
                    prefix = [*key, q["source"], q["target"], scheme["name"], state, "True" if p else "False"]
                    writer.writerow(prefix + ([*p["cost"], "->".join(map(str, p["vertices"]))] if p else [""]*6)); count += 1
    os.replace(temporary, target)
    atomic_json(out / "aggregation.json", {"queries": len(records), "expected_queries": 90,
                "complete": complete, "rows": count, "file": name, "sha256": sha256(target)})
    print(f"aggregate {len(records)}/90 queries, {count} rows, complete={complete}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--task3-dir", type=Path, default=ROOT / "q3_output")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "q4_output")
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--datasets", default="NY,BAY,COL")
    parser.add_argument("--query-ids", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--researcher", default="XXX")
    args = parser.parse_args(); root=args.root.resolve();out=args.output_dir.resolve();task3=args.task3_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.aggregate:
        aggregate(root, out, args.researcher); return
    if not 1 <= args.workers <= 32:
        parser.error("workers must be between 1 and 32")
    code_dir = Path(__file__).resolve().parent
    exe = (args.executable or code_dir / ("task4_solver.exe" if os.name == "nt" else "task4_solver")).resolve()
    ds_set = set(args.datasets.split(",")); ids=set(args.query_ids.split(",")) if args.query_ids else set()
    if not ds_set <= {"NY", "BAY", "COL"}:
        parser.error("invalid datasets")
    jobs=[q for q in queries(root) if q["dataset"] in ds_set and (not ids or q["query_id"] in ids)]
    if not jobs or ids-{q["query_id"] for q in jobs}:
        parser.error("unknown query selection")
    files=candidate_files(task3)
    manifest=json.loads((task3/"aggregation.json").read_text(encoding="utf-8"))
    if not manifest["complete"] or manifest["certified_groups"]!=270:
        raise ValueError("a complete certified task3 export is required")
    selection=json.loads((task3/"selection.json").read_text(encoding="utf-8"))
    selected_hash={s["checkpoint"]:s["sha256"] for s in selection}
    data={}
    for ds in ds_set:
        closure=root/"data"/f"dimacs5_{ds.lower()}"/"closed_edges_problem4.csv"
        data[ds]={"closed":closed_pairs(closure), "edges_sha256":sha256(root/"data"/"edges"/f"edges_{ds}_5obj.txt"),
                  "closures_sha256":sha256(closure),"queries_sha256":sha256(root/"data"/f"dimacs5_{ds.lower()}"/"queries_problem34.csv")}
    cp=out/"checkpoints";work=out/"workers";cp.mkdir(exist_ok=True);work.mkdir(exist_ok=True)
    software={"binary_sha256":sha256(exe),"source_sha256":sha256(code_dir/"task4_solver.cpp"),"decision_source_sha256":sha256(code_dir/"task4_common.py")}

    def worker(q):
        ds,qid=q["dataset"],q["query_id"];source_files=files.get((ds,qid),[])
        if len(source_files)!=3:
            raise ValueError(f"{ds}/{qid}: expected three task3 dimensions")
        hashes={p.name:sha256(p) for p in source_files}
        if any(selected_hash.get(name)!=h for name,h in hashes.items()):
            raise ValueError("task3 checkpoint differs from certified selection")
        meta={**q,**software,**{k:v for k,v in data[ds].items() if k!="closed"},"task3_checkpoints":hashes,"weights":{k:list(v) for k,v in SCHEMES.items()}}
        ident=hashlib.sha256(json.dumps(meta,sort_keys=True).encode()).hexdigest()[:16];name=f"{ds}_{qid}_{ident}";target=cp/(name+".json")
        if target.exists():
            if not args.resume:
                raise ValueError("checkpoint exists; use --resume or a new output directory")
            r=json.loads(target.read_text(encoding="utf-8"))
            if any(r.get(k)!=v for k,v in meta.items()) or not r["complete"]:
                raise ValueError("checkpoint metadata mismatch")
            return name,r,True
        tick=time.perf_counter();raw,inputs=load_candidates(source_files)
        if {r["objective_count"] for r in inputs}!={2,3,5}:
            raise ValueError("invalid candidate dimensions")
        for r in inputs:
            if (r["dataset"],r["query_id"],r["source"],r["target"],r["edges_sha256"],r["queries_sha256"])!=(ds,qid,q["source"],q["target"],meta["edges_sha256"],meta["queries_sha256"]):
                raise ValueError("task3 provenance mismatch")
        front=candidate_front(raw);low,span,common=scales(front);closed=data[ds]["closed"]
        available=[p for p in front if survives(p,closed)]
        # A dominated original candidate can be the only surviving route after
        # closures; keep the ENTIRE original union for feasible warm starts.
        available_raw=[p for p in raw if survives(p,closed)]
        configs={}
        for scheme,weights in SCHEMES.items():
            coeff=coefficients(weights,span,common)
            configs[scheme]={"coefficients":coeff,"original":select(front,coeff),"warm_start":select(available_raw,coeff)}
        sensitivity_rows=sensitivity(front,span,common)
        decision_seconds=time.perf_counter()-tick
        job=work/(name+".job");temporary=work/(name+".worker.tmp");log=work/(name+".log")
        if temporary.exists():
            raise ValueError("stale or active worker temporary file")
        write_job(job,q["source"],q["target"],configs)
        cmd=[str(exe),"--edges",str(root/"data"/"edges"/f"edges_{ds}_5obj.txt"),"--closed",str(root/"data"/f"dimacs5_{ds.lower()}"/"closed_edges_problem4.csv"),"--job",str(job),"--output",str(temporary)]
        started=time.perf_counter()
        with log.open("w",encoding="utf-8") as stream:
            result=subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"solver failed: {name}; see log")
        r=json.loads(temporary.read_text(encoding="utf-8"))
        if (r["source"],r["target"])!=(q["source"],q["target"]):
            raise ValueError("solver endpoints mismatch")
        for scheme in r["schemes"]:
            config=configs[scheme["name"]]
            if list(map(int,scheme["coefficients"]))!=config["coefficients"]:
                raise ValueError("scalarization mismatch")
            for kind in ("original","warm_start"):
                p,expected=scheme[kind],config[kind]
                if bool(p)!=bool(expected) or (p and any(p[k]!=expected[k] for k in ("cost","vertices","edge_indices"))):
                    raise ValueError("solver path differs from selected task3 candidate")
        r.update(meta);r.update({"complete":True,"normalization_low":low,"normalization_span":span,"common_denominator":str(common),
                   "raw_candidate_records":len(raw),"candidate_front_size":len(front),"surviving_front_size":len(available),
                   "surviving_raw_records":len(available_raw),"decision_seconds":decision_seconds,
                   "wall_seconds":time.perf_counter()-started,"sensitivity":sensitivity_rows})
        atomic_json(target,r);temporary.unlink();return name,r,False

    failures=[];started=time.perf_counter();print(f"start task4 queries={len(jobs)} workers={args.workers}",flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending=[pool.submit(worker,q) for q in jobs]
        for i,future in enumerate(as_completed(pending),1):
            try:
                name,r,resumed=future.result()
                print(f'{i}/{len(jobs)} {name} disrupted_feasible={sum(bool(s["disrupted"]) for s in r["schemes"])}/4 total_s={r["total_seconds"]:.3f} resumed={resumed}',flush=True)
            except Exception as exc:
                failures.append(str(exc));print(f"FAIL: {exc}",flush=True)
    atomic_json(out/"run_summary.json",{"queries":len(jobs),"failures":failures,"wall_seconds":time.perf_counter()-started,
                "workers":args.workers,"hardware":f"{platform.system()} {platform.machine()}, logical CPUs={os.cpu_count()}"})
    if failures:
        raise RuntimeError("task4 workers failed; inspect run_summary.json")
    aggregate(root,out,args.researcher)


if __name__=="__main__":
    main()
