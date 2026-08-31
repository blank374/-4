#!/usr/bin/env bash
# Run from the repository root. No host, login, or private-key details belong here.
set -euo pipefail
OUT="${TASK3_BASELINE_OUTPUT:-results_task3_baseline_reproduction}"
g++ -O3 -DNDEBUG -std=c++17 -Wall -Wextra task3_solver.cpp -o task3_solver
python3 verify_task3_solver.py ./task3_solver
# Fixed 90 queries x 3 dimensions; never replace difficult queries.
python3 run_task3.py --algorithm baseline --epsilons 0.2 --workers "${TASK3_WORKERS:-16}" --max-seconds 30 --max-labels 12000000 --output-dir "$OUT" --resume
# Stratified pilot: first, middle, last official query in each city.
python3 run_task3.py --algorithm baseline --query-ids 0001,0015,0030 --epsilons 0.05,0.1,0.2 --baseline --exact-2d --workers "${TASK3_WORKERS:-16}" --max-seconds 30 --max-labels 12000000 --output-dir "$OUT" --resume
python3 run_task3.py --algorithm baseline --dimensions 2 --epsilons 0 --workers "${TASK3_WORKERS:-16}" --max-seconds 30 --max-labels 12000000 --output-dir "$OUT" --resume
python3 verify_task3_results.py "$OUT"
python3 run_task3.py --aggregate --exact-2d --export-epsilon 0.2 --output-dir "$OUT"
