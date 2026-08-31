"""Independent simple-path enumeration for directed closures and scalar A*."""
import argparse
import json
from pathlib import Path
import random
import subprocess
import tempfile

from run_task4 import write_job
from task4_common import SCHEMES, candidate_front
from verify_task4_results import bidirectional

ROOT=Path(__file__).resolve().parent


def enumerate_paths(edges,s,t):
    csr=sorted(edges,key=lambda e:e[0]);adj={}
    for k,(u,v,*c) in enumerate(csr):
        adj.setdefault(u,[]).append((k,v,c))
    paths=[]
    def visit(u,vertices,ids,cost):
        if u==t:
            paths.append({"vertices":vertices,"edge_indices":ids,"cost":cost});return
        for k,v,c in adj.get(u,[]):
            if v not in vertices:
                visit(v,vertices+[v],ids+[k],[a+b for a,b in zip(cost,c)])
    visit(s,[s],[],[0]*5)
    return csr,paths


def value(p,coeff):
    return sum(a*b for a,b in zip(p["cost"],coeff))


def allowed(p,closed):
    return all((u,v) not in closed for u,v in zip(p["vertices"],p["vertices"][1:]))


def oracle_graph(csr, closed):
    n = max(max(e[:2]) for e in csr)+1
    off = [0]*(n+1); rev = [0]*(n+1)
    for u, v, *_ in csr:
        off[u+1] += 1; rev[v+1] += 1
    for u in range(n):
        off[u+1] += off[u]; rev[u+1] += rev[u]
    cursor = rev[:]; rk = [0]*len(csr)
    for k, e in enumerate(csr):
        rk[cursor[e[1]]] = k; cursor[e[1]] += 1
    return off, list(zip(*(e[1:] for e in csr))), [e[0] for e in csr], rev, rk, bytearray(tuple(e[:2]) in closed for e in csr), {}


def check(p,csr,s,t,coeff,closed):
    if p is None:return
    vs,ids=p["vertices"],p["edge_indices"]
    assert vs[0]==s and vs[-1]==t and len(vs)==len(ids)+1 and len(set(vs))==len(vs)
    total=[0]*5
    for u,v,k in zip(vs,vs[1:],ids):
        assert (u,v)==tuple(csr[k][:2]) and (u,v) not in closed
        total=[a+b for a,b in zip(total,csr[k][2:])]
    assert total==p["cost"] and value(p,coeff)==int(p["scalar"])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable",nargs="?",type=Path,default=ROOT/"task4_solver.exe")
    parser.add_argument("--cases",type=int,default=160)
    args=parser.parse_args();rng=random.Random(4405);cases=[]
    for _ in range(args.cases):
        n=rng.randrange(2,8);edges=[]
        for u in range(n):
            for v in range(n):
                if rng.random()<.25:
                    edges.append([u,v,*[rng.randrange(13) for _ in range(5)]])
                    if rng.random()<.15:edges.append([u,v,*[rng.randrange(13) for _ in range(5)]])
        edges.extend([[0,0,0,0,0,0,0],[n-1,n-1,0,0,0,0,0]])
        closed={tuple(e[:2]) for e in edges if rng.random()<.2}
        cases.append((edges,rng.randrange(n),rng.randrange(n),closed))
    edge=lambda u,v,c:[u,v,c,c,c,c,c]
    cases.extend([
        ([edge(0,1,1),edge(1,0,2)],1,0,{(0,1)}),
        ([edge(0,1,1),edge(0,1,2),edge(0,2,3),edge(2,1,3)],0,1,{(0,1)}),
        ([edge(0,1,1),edge(1,2,1)],0,2,{(1,2)}),
        ([edge(0,1,0),edge(1,0,0)],0,0,{(0,1),(1,0)}),
    ])
    checks=0;(ROOT/"tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="task4_oracle_",dir=ROOT/"tmp") as temporary:
        folder=Path(temporary)
        for case,(edges,s,t,closed) in enumerate(cases):
            csr,all_paths=enumerate_paths(edges,s,t)
            oracle = oracle_graph(csr, closed)
            candidates=rng.sample(all_paths,min(12,len(all_paths)))
            disrupted=[p for p in all_paths if allowed(p,closed)]
            configs={}
            for name,w in SCHEMES.items():
                coeff=[x*(2**70+33 if case%3==0 else 1) for x in w]
                choose=lambda paths:min(paths,key=lambda p:value(p,coeff)) if paths else None
                warm=choose([p for p in candidates if allowed(p,closed)]) if case%2 else None
                configs[name]={"coefficients":coeff,"original":choose(candidates),"warm_start":warm}
            graph=folder/"edges.txt";closures=folder/"closed.csv";job=folder/"job.txt";output=folder/"result.json"
            graph.write_text("\n".join(" ".join(map(str,e)) for e in edges)+"\n",encoding="utf-8")
            closures.write_text("closed_from,closed_to\n"+"".join(f"{u},{v}\n" for u,v in sorted(closed)),encoding="utf-8")
            write_job(job,s,t,configs);output.unlink(missing_ok=True)
            r=subprocess.run([str(args.executable.resolve()),"--edges",str(graph),"--closed",str(closures),"--job",str(job),"--output",str(output)],capture_output=True,text=True)
            assert r.returncode==0,(case,r.stderr)
            result=json.loads(output.read_text(encoding="utf-8"))
            assert result["removed_edges"]==sum(tuple(e[:2]) in closed for e in edges)
            for row in result["schemes"]:
                coeff=configs[row["name"]]["coefficients"]
                for field,paths,forbidden in [("original_optimal",all_paths,set()),("disrupted",disrupted,closed)]:
                    p=row[field];assert bool(p)==bool(paths),(case,field)
                    check(p,csr,s,t,coeff,forbidden)
                    if p:assert int(p["scalar"])==min(value(q,coeff) for q in paths),(case,field)
                    optimum = min((value(q, coeff) for q in paths), default=None)
                    costs = [sum(a*b for a,b in zip(e[2:], coeff)) for e in csr]
                    # Test the auditor both without and with a feasible upper bound.
                    for upper in (None, max((value(q, coeff) for q in paths), default=None)):
                        assert bidirectional(oracle, costs, s, t, field == "disrupted", upper) == optimum
                    checks+=1
                check(row["original"],csr,s,t,coeff,set());check(row["warm_start"],csr,s,t,coeff,closed)
        # Independent Pareto filtering checks, including equal vectors.
        for _ in range(500):
            points=[tuple(rng.randrange(10) for _ in range(5)) for _ in range(40)]
            expected={p for p in points if not any(q!=p and all(x<=y for x,y in zip(q,p)) for q in points)}
            dummy=[{"cost":list(p),"vertices":[0],"edge_indices":[]} for p in points]
            assert {tuple(p["cost"]) for p in candidate_front(dummy)}==expected
    print(f"PASS: {len(cases)} graph/closure cases, {checks} C++ and {2*checks} Python optimum checks, 500 Pareto-filter checks")


if __name__=="__main__":
    main()
