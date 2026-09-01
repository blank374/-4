"""Linux server runner: isolated per-query workers, durable checkpoints, final audit."""
import csv
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

CODE_DIR=Path(__file__).resolve().parent
ROOT=CODE_DIR.parent
EXE=CODE_DIR/"task2_exact"
OUT=ROOT/"q2_output"
STATE=OUT/".task2_exact"
WORK=OUT/".workers"
WORKERS=int(os.environ.get("TASK2_WORKERS","16"))
ORDER="213"


def emit(message):
    print(time.strftime("[%Y-%m-%d %H:%M:%S] ")+message,flush=True)


def atomic_json(path,value):
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(temporary,path)


def copy_atomic(source,target):
    temporary=target.with_suffix(target.suffix+".tmp")
    shutil.copy2(source,temporary)
    os.replace(temporary,target)


def cp_path(base,job):
    return base/".task2_exact"/(job[0]+"_"+job[1]+".exact")


def complete_header(path,job):
    if not path.exists(): return False
    with path.open() as stream: head=stream.readline().split()
    return len(head)==7 and head[:3]==["TASK2_EXACT_V1",*job]


def available_gb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"): return int(line.split()[1])/1024**2
    return 0


def progress_line(log):
    with log.open("rb") as stream:
        stream.seek(max(0,log.stat().st_size-8192))
        lines=stream.read().decode("utf-8","replace").splitlines()
    selected=[line.strip() for line in lines if "search_s=" in line or "status=" in line]
    return selected[-1] if selected else "loading/heuristics"


def main():
    if not 1<=WORKERS<=32: raise RuntimeError("TASK2_WORKERS must be between 1 and 32")
    STATE.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
    lock=(OUT/"server_runner.lock").open("a")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    job_info={}
    for ds in ("NY","BAY","COL"):
        p=ROOT/"data"/f"dimacs5_{ds.lower()}"/"queries_problem2.csv"
        with p.open(newline="",encoding="utf-8") as stream:
            for row in csv.DictReader(stream): job_info[ds,row["query_id"]]=row
    if len(job_info)!=90: raise RuntimeError("expected exactly 90 queries")
    done={job for job in job_info if complete_header(cp_path(OUT,job),job)}
    queues={ds:[j for j in job_info if j[0]==ds and j not in done] for ds in ("NY","BAY","COL")}
    pending=[]
    while any(queues.values()):
        for ds in queues:
            if queues[ds]: pending.append(queues[ds].pop(0))
    active={};failures=[];last_report=0;started=time.time()
    emit(f"start complete={len(done)}/90 queued={len(pending)} workers={WORKERS} order={ORDER}")
    while pending or active:
        stop_requested=(OUT/"STOP_AFTER_CURRENT").exists()
        while pending and len(active)<WORKERS and available_gb()>2 and not stop_requested:
            job=pending.pop(0);ds,qid=job
            if complete_header(cp_path(OUT,job),job): done.add(job);continue
            worker=WORK/(ds+"_"+qid);worker.mkdir(parents=True,exist_ok=True)
            log=worker/"run.log";stream=log.open("a")
            cmd=[str(EXE),"--dataset",ds,"--query-id",qid,"--order",ORDER,
                 "--output-dir",str(worker),"--resume"]
            process=subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                                     preexec_fn=lambda:os.nice(10))
            active[process.pid]=(process,stream,job,worker,log,time.time())
            emit(f"launched {ds}/{qid} pid={process.pid}")
        time.sleep(1)
        for pid,item in list(active.items()):
            process,stream,job,worker,log,begin=item
            code=process.poll()
            if code is None: continue
            stream.close();del active[pid]
            source=cp_path(worker,job)
            if code==0 and complete_header(source,job):
                copy_atomic(source,cp_path(OUT,job));done.add(job)
                emit(f"complete {job[0]}/{job[1]} total={len(done)}/90 wall_s={time.time()-begin:.1f}")
            else:
                failures.append({"dataset":job[0],"query_id":job[1],"exit":code,"log":str(log)})
                emit(f"FAILED {job[0]}/{job[1]} exit={code} log={log}")
        if time.time()-last_report>=15:
            details=[{"dataset":v[2][0],"query_id":v[2][1],"pid":pid,"elapsed_seconds":round(time.time()-v[5],1),
                      "progress":progress_line(v[4])} for pid,v in active.items()]
            atomic_json(OUT/"server_progress.json",{
                "phase":"running","complete":len(done),"total":90,"queued":len(pending),"workers":WORKERS,
                "active":details,"failures":failures,"available_ram_gb":round(available_gb(),1),
                "elapsed_seconds":round(time.time()-started,1),"updated_at":time.strftime("%Y-%m-%d %H:%M:%S")})
            emit(f"progress complete={len(done)}/90 active={len(active)} queued={len(pending)} available_GB={available_gb():.1f}")
            last_report=time.time()
        if stop_requested and not active:
            emit("stopped after current queries; checkpoints preserved")
            return 2
    if failures:
        atomic_json(OUT/"server_failures.json",failures)
        emit("some queries failed; no formal success marker")
        return 1
    emit("all 90 checkpoints complete; aggregating and verifying")
    with (OUT/"aggregate.log").open("w") as stream:
        subprocess.run([str(EXE),"--order",ORDER,"--output-dir",str(OUT),"--resume","--quiet"],
                       cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)
    with (OUT/"verification.log").open("w") as stream:
        subprocess.run([sys.executable,str(ROOT/"verify_task2_results.py"),str(OUT)],cwd=ROOT,
                       stdout=stream,stderr=subprocess.STDOUT,check=True)
    report=json.loads((OUT/"verification_report.json").read_text())
    atomic_json(OUT/"server_progress.json",{
        "phase":"verified_complete","complete":90,"total":90,"rows":report["rows"],
        "csv_sha256":report["csv_sha256"],"elapsed_seconds":round(time.time()-started,1),
        "finished_at":time.strftime("%Y-%m-%d %H:%M:%S")})
    emit(f"VERIFIED COMPLETE 90/90 rows={report['rows']} sha256={report['csv_sha256']}")
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        emit(f"ERROR {error!r}")
        raise
