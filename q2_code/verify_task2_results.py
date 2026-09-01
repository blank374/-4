"""Independently verify all 90 output groups and their checkpoint contents.

This validates the deliverable, not a new proof of search completeness.
Completeness is certified by the exact solver's exhausted-OPEN checkpoints.
"""
import csv
import hashlib
import json
from pathlib import Path
import sys

CODE_DIR = Path(__file__).resolve().parent
ROOT = CODE_DIR.parent
OUT = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT / "q2_output"


def check_frontier(costs):
    assert costs == sorted(costs), "cost vectors not in canonical order"
    assert len(costs) == len(set(costs)), "duplicate vector"
    ys = sorted({c[1] for c in costs})
    rank = {v: i+1 for i, v in enumerate(ys)}
    tree = [float("inf")] * (len(ys)+1)
    for c in costs:
        assert all(v>=0 for v in c), "negative cost"
        i = rank[c[1]]; minimum = float("inf")
        while i:
            minimum = min(minimum, tree[i]); i -= i & -i
        assert minimum > c[2], f"dominated vector {c}"
        i = rank[c[1]]
        while i < len(tree):
            tree[i] = min(tree[i], c[2]); i += i & -i


def check_group(key, costs, queries, statuses):
    source, target = queries[key]
    status = statuses[key]
    cp = OUT / ".task2_exact" / f"{key[0]}_{key[1]}.exact"
    with cp.open(encoding="utf-8") as stream:
        header = stream.readline().split()
        assert len(header)==7 and header[:3]==["TASK2_EXACT_V1", *key]
        assert (int(header[3]),int(header[4]))==(source,target)
        assert int(header[6])==len(costs)==int(status["solutions"])
        stream.readline()  # metrics
        checkpoint_costs = [tuple(map(int,line.split())) for line in stream if line.strip()]
    assert costs==checkpoint_costs, f"CSV/checkpoint mismatch {key}"
    if not costs:
        assert status["status"]=="unreachable"
    else:
        assert status["status"]=="complete"
        check_frontier(costs)
    canonical = "".join(",".join(map(str,c))+"\n" for c in costs)
    return {"dataset":key[0],"query_id":key[1],"solutions":len(costs),
            "sha256":hashlib.sha256(canonical.encode()).hexdigest(),
            "objective_minima":[min(c[j] for c in costs) for j in range(3)] if costs else None}


def main():
    queries = {}
    for ds in ("NY","BAY","COL"):
        p=ROOT/"data"/f"dimacs5_{ds.lower()}"/"queries_problem2.csv"
        with p.open(newline="",encoding="utf-8") as f:
            rows=list(csv.DictReader(f))
        assert len(rows)==30
        for r in rows: queries[ds,r["query_id"]]=(int(r["source"]),int(r["target"]))
    assert len(queries)==90
    with (OUT/"task2_status.csv").open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    statuses={(r["dataset"],r["query_id"]):r for r in rows}
    assert len(rows)==90 and statuses.keys()==queries.keys()
    assert all(r["status"] in {"complete","unreachable"} for r in rows), "some queries are incomplete"
    files=list(OUT.glob("result2_*.csv"))
    files=[p for p in files if not p.name.endswith(".partial.csv")]
    assert len(files)==1, "expected one formal CSV"
    report=[];seen=set();key=None;costs=[];total=0
    with files[0].open(newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f)
        assert reader.fieldnames==["dataset","query_id","source","target","solution_id","c1","c2","c3"]
        for row in reader:
            current=row["dataset"],row["query_id"]
            assert current in queries
            if current!=key:
                if key is not None: report.append(check_group(key,costs,queries,statuses))
                assert current not in seen, "noncontiguous query group"
                seen.add(current);key=current;costs=[]
            assert (int(row["source"]),int(row["target"]))==queries[key]
            assert int(row["solution_id"])==len(costs)+1
            costs.append(tuple(int(row[f"c{j}"]) for j in (1,2,3)));total+=1
    if key is not None: report.append(check_group(key,costs,queries,statuses))
    for missing in queries.keys()-seen: report.append(check_group(missing,[],queries,statuses))
    report.sort(key=lambda r:(r["dataset"],r["query_id"]))
    h=hashlib.sha256()
    with files[0].open("rb") as stream:
        for chunk in iter(lambda:stream.read(1<<20),b""): h.update(chunk)
    result={"queries":90,"rows":total,"formal_csv":files[0].name,"csv_sha256":h.hexdigest(),
            "all_checks_passed":True,"groups":report}
    (OUT/"verification_report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"VERIFIED: 90 queries; {total} cost vectors; SHA256={h.hexdigest()}",flush=True)


if __name__=="__main__": main()
