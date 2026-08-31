#!/usr/bin/env bash
# New output directory preserves the original no-merging baseline experiments.
set -euo pipefail
OUT="${TASK3_OUTPUT:-results_task3_apex_reproduction}"
FINAL="${TASK3_FINAL:-results_task3_certified_reproduction}"
g++ -O3 -DNDEBUG -std=c++17 -Wall -Wextra task3_solver.cpp -o task3_solver
python3 verify_task3_solver.py ./task3_solver --cases 200
python3 run_task3.py --algorithm apex --order 21345 --epsilons 0.2 --workers "${TASK3_WORKERS:-16}" --max-seconds 30 --max-labels 12000000 --output-dir "$OUT" --resume
python3 run_task3.py --algorithm apex --order 21345 --dimensions 2 --epsilons 0 --workers "${TASK3_WORKERS:-16}" --max-seconds 30 --max-labels 12000000 --output-dir "$OUT" --resume
python3 run_task3.py --algorithm apex --order 31245 --epsilons 0.2 --exact-2d --retry-from "$OUT" --workers "${TASK3_WORKERS:-16}" --max-seconds 30 --max-labels 12000000 --output-dir "$OUT/order31245" --resume
python3 verify_task3_results.py "$OUT"
python3 assemble_task3_certified.py "$OUT" "$OUT/order31245" --output-dir "$FINAL"
