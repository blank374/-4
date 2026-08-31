"""Verify the exact bytes of the published paper/review artifacts after Git LFS pull."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / "docs/research_artifacts.json").read_text(encoding="utf-8"))
    failed = []
    for entry in manifest["files"]:
        p = ROOT / entry["path"]
        if not p.resolve().is_relative_to(ROOT) or not p.is_file() or p.is_symlink():
            failed.append((entry["path"], "missing or invalid path")); continue
        if p.stat().st_size != entry["bytes"]:
            failed.append((entry["path"], "size mismatch; run git lfs pull if this is an LFS pointer")); continue
        h = hashlib.sha256()
        with p.open("rb") as stream:
            for block in iter(lambda: stream.read(1024*1024), b""):
                h.update(block)
        if h.hexdigest() != entry["sha256"]:
            failed.append((entry["path"], "SHA256 mismatch"))
    if failed:
        for path, reason in failed:
            print(f"FAIL {path}: {reason}")
        raise SystemExit(1)
    print(f"PASS: {len(manifest['files'])} research artifacts; exact sizes and SHA256 hashes match.")
    print("This checks file integrity only; use the task-specific verifiers to audit results.")


if __name__ == "__main__":
    main()
