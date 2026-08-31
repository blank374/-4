"""Independent CLI integration checks; artifacts remain under tmp/task2_tests_*."""
import csv
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
EXE = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT / "task2_exact.exe"


def run(*args, expected=0):
    result = subprocess.run([str(EXE), *map(str, args)], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=45)
    if result.returncode != expected:
        raise AssertionError((args, expected, result.returncode, result.stdout, result.stderr))
    return result


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    print(run("--self-test").stdout.strip(), flush=True)
    (ROOT / "tmp").mkdir(exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="task2_tests_", dir=ROOT / "tmp"))
    edge_path = base / "data/edges/edges_NY_5obj.txt"
    query_path = base / "data/dimacs5_ny/queries_problem2.csv"
    edge_path.parent.mkdir(parents=True)
    query_path.parent.mkdir(parents=True)
    edge_lines = []
    for node in range(8):
        weight = 1 << node
        edge_lines += [f"{node} {node+1} {weight} 0 {weight} 1 1",
                       f"{node} {node+1} 0 {weight} 0 1 1"]
    edge_lines += ["10 10 0 0 0 1 1"]
    original_edges = "\n".join(edge_lines) + "\n"
    edge_path.write_text(original_edges, encoding="utf-8")
    query_path.write_text("query_id,source,target\n0001,0,8\n0002,0,0\n0003,10,8\n", encoding="utf-8")
    out = base / "out"
    common = ["--root", base, "--dataset", "NY", "--output-dir", out]
    run(*common, "--max-expanded", 1, expected=2)
    assert not (out / "result2_研XXX.csv").exists(), "incomplete batch got formal filename"
    partial = rows(out / "result2_研XXX.partial.csv")
    assert {r["query_id"] for r in partial} == {"0002"}, "partial search vectors leaked"
    status = {r["query_id"]: r["status"] for r in rows(out / "task2_status.csv")}
    assert status == {"0001": "expansion_limit", "0002": "complete", "0003": "unreachable"}
    run(*common, "--resume", "--order", "213")
    formal = out / "result2_研XXX.csv"
    actual = rows(formal)
    got = {tuple(int(r[f"c{j}"]) for j in (1, 2, 3)) for r in actual if r["query_id"] == "0001"}
    expected = {(x, 255-x, x) for x in range(256)}
    assert got == expected and len(actual) == 257
    assert [int(r["solution_id"]) for r in actual if r["query_id"] == "0001"] == list(range(1, 257))
    before = digest(formal)
    run(*common, "--resume", "--order", "321")
    assert digest(formal) == before, "resume duplicated or changed results"
    run(*common, expected=1)
    assert digest(formal) == before, "existing output overwritten without resume"
    run("--root", base, "--dataset", "NY", "--output-dir", base / "order321", "--order", "321")
    assert rows(base / "order321/result2_研XXX.csv") == actual
    cp = out / ".task2_exact/NY_0001.exact"
    content = cp.read_bytes()
    cp.write_bytes(content[:len(content)//2])
    run(*common, "--resume", expected=1)
    assert digest(formal) == before, "bad checkpoint damaged aggregate output"
    cp.write_bytes(content)
    edge_path.write_text(original_edges + "# changed input\n", encoding="utf-8")
    run(*common, "--resume", expected=1)
    assert digest(formal) == before, "stale checkpoint accepted after input change"
    edge_path.write_text(original_edges, encoding="utf-8")
    run(*common, "--resume")
    for args in [("--order", "113"), ("--dataset", "BAD"), ("--seed-count", "0"),
                 ("--max-open", "-1"), ("--unknown",), ("--output-dir",)]:
        run(*args, expected=1)
    print("CLI TESTS OK: exact 256-vector set; limit/no partial publication; unreachable; s=t; "
          "resume; objective order; overwrite protection; truncated checkpoints; input fingerprints; invalid arguments")
    print(f"Evidence: {base}")


if __name__ == "__main__":
    main()
