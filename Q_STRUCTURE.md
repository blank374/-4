# Q1-Q4 Organized Structure

This folder keeps the original project layout, and adds a submission-friendly
view with one code folder and one output folder for each problem.

| Folder | Contents |
| --- | --- |
| `q1_code/` | Task 1 solver, task 1 documentation, and result format example. |
| `q1_output/` | Formal task 1 CSV output. |
| `q2_code/` | Task 2 exact solver, build script, server runner, validators, documentation, and result format example. |
| `q2_output/` | Formal task 2 CSV output plus status, input manifest, and verification report. |
| `q3_code/` | Task 3 solver, run/assembly/optimization scripts, validators, documentation, and result format example. |
| `q3_output/` | Certified formal task 3 CSV output plus aggregation, selection, and verification report. |
| `q4_code/` | Task 4 solver, common Python utilities, run/analysis scripts, validators, documentation, and result format example. |
| `q4_output/` | Formal task 4 CSV output plus verification, comparison, sensitivity, summary, and analysis files. |

The original `data/`, `docs/`, and `examples/` folders are kept in place for
full reproduction. Experimental result folders such as `results_task2_bigopt*`,
`results_task3`, `results_task3_optimized`, and
`results_task3_order31245_server` are not part of the formal Q1-Q4 submission
view.

Files ending with `.partial.csv` are intermediate outputs and should not be
submitted as final answers.
