#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
g++ -O3 -DNDEBUG -std=c++17 -Wall -Wextra task4_solver.cpp -o task4_solver
python3 verify_task4_solver.py ./task4_solver
task4_output="${TASK4_OUTPUT:-results_task4_reproduction}"
task3_input="${TASK3_FINAL:-results_task3_certified}"
python3 run_task4.py --output-dir "$task4_output" --task3-dir "$task3_input" --workers "${TASK4_WORKERS:-4}" --resume
python3 verify_task4_results.py "$task4_output" --task3-dir "$task3_input" --workers "${TASK4_VERIFY_WORKERS:-4}"
python3 analyze_task4.py "$task4_output"
