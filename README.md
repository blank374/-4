# 城市道路网络多目标路径规划

任务一至四的求解与验证代码，包含精确/近似路径集、偏好推荐、封路重规划和实验分析。

任务二已完整求解 NY、BAY、COL 各30组查询，共 **90组、3,023,770条 Pareto 目标向量记录**。正式求解器是 `task2_exact.cpp`；旧的 KD 树、双向搜索和分区实验不再作为运行入口。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `task1_solver.py` | 任务一：五种单目标 Dijkstra |
| `task2_exact.cpp` | 任务二：三目标完整精确 Pareto 前沿 |
| `build_task2_exact.ps1` | Windows 编译与内置验证 |
| `verify_task2_exact.py` | 独立穷举与 CLI 集成测试 |
| `verify_task2_results.py` | 90组最终结果文件核验 |
| `run_task2_server.py` | Linux 多进程批量求解与自动核验 |
| `task3_solver.cpp` | 任务三：2/3/5维搜索、完整路径与ε覆盖认证 |
| `run_task3.py` / `run_task3_batch.sh` | 任务三固定查询实验、断点与汇总 |
| `run_task3_optimized.sh` / `assemble_task3_certified.py` | 标签合并优化、未认证组换序重试、认证答案汇集 |
| `verify_task3_solver.py` / `verify_task3_results.py` | 穷举验证、路径核验与质量比较 |
| `task4_solver.cpp` / `task4_common.py` | 任务四固定偏好、候选选择、封路后的精确标量A* |
| `run_task4.py` / `run_task4_batch.sh` | 四种方案、两种路网状态的全量运行与复现 |
| `verify_task4_solver.py` / `verify_task4_results.py` | 小图穷举、逐边核验、独立双向Dijkstra最优值复核 |
| `analyze_task4.py` | 偏好敏感性、封路损失与运行统计 |
| `data/` | 原始图、合并边表、固定查询和关闭边表 |
| `examples/` | 题目规定的四种结果格式示例 |
| `docs/` | 模型说明、运行方法及验证记录 |

正式答案、认证断点、来源清单、验证报告及论文所需的任务三优化前后对照已从忽略规则中放出；大型CSV和任务三原始路径JSON使用Git LFS。详见 [论文与复核资料](docs/research_artifacts.md) 和 [逐文件哈希清单](docs/research_artifacts.json)。旧方法归档、临时实验、日志、二进制和含服务器连接信息的历史文件继续忽略。

## 环境

- Python 3.10 或更高版本，仅使用标准库。
- 支持 C++17 的 GCC；Windows 使用 MinGW-w64 g++，Linux 使用 g++。
- Windows 编译依赖系统 `psapi`、`shell32` 库。
- 下载完整答案和原始路径需安装Git LFS；克隆后执行 `git lfs pull`，再用 `python verify_research_artifacts.py` 检查文件完整性。

原始数据和题目附件保留原样。运行正式数据实验需要完整的 `data/edges/` 与各城市查询表；内置随机测试和 CLI 构造图测试不依赖大图数据。

## 任务一

```bash
python task1_solver.py --output-dir results_task1 --researcher XXX
```

模型和算法见 [任务一说明](docs/task1.md)。

## 任务二

Windows PowerShell：

```powershell
.\build_task2_exact.ps1
python verify_task2_exact.py
.\task2_exact.exe --order 213 --output-dir results_task2_exact --resume
```

Linux：

```bash
g++ -O3 -DNDEBUG -std=c++17 -Wall -Wextra task2_exact.cpp -o task2_exact
./task2_exact --self-test
python3 verify_task2_exact.py ./task2_exact
./task2_exact --order 213 --output-dir results_task2_exact --resume
```

`--resume` 在新输出目录也可以使用，已有输出目录必须使用它。完整数据集计算可能耗时较长。先运行一组可使用：

```bash
./task2_exact --dataset NY --query-id 0001 --order 213 --output-dir results_task2_exact --resume
```

Windows 将 `./task2_exact` 换成 `.\task2_exact.exe`。内部目标顺序不改变输出列含义，`c1,c2,c3` 始终是距离、时间、起伏。排序213已实际完成全量验证，但不保证对所有新数据都最快。

算法与正确性说明见 [任务二说明](docs/task2.md)。并行计算见 [Linux批量运行](docs/server.md)。

## 任务三

最新结果：**270/270组合均取得保证**，共20,669条路径。二维90组为完整精确前沿；三维、五维各90组为ε=0.20覆盖。默认排序完成269组，最后1组换内部排序完成，没有放宽精度。最终文件为 `results_task3_certified/result3_研XXX.csv`，旧版实验保留。

```powershell
.\build_task3.ps1
python verify_task3_solver.py
python run_task3.py --query-ids 0001 --algorithm apex --baseline --exact-2d --output-dir results_task3_apex_pilot
python verify_task3_results.py results_task3_apex_pilot
```

Linux新版完整流程使用 `TASK3_WORKERS=16 bash run_task3_optimized.sh`。使用任务三专用固定查询表，输出所有五项成本和完整路径；触顶仍只返回未认证候选，汇集脚本只接受取得证书的结果。

详见 [最新优化与复现说明](docs/task3_optimization.md)、[基线模型](docs/task3.md) 与 [初版实验记录](docs/task3_validation.md)。

## 任务四

已完成 **90组查询、四种偏好、封路前后共720行结果**，全部通过逐边核验和独立最优值检查。原始推荐从任务三候选选择；封路后在完整剩余路网求给定偏好的精确最优路径，不枚举完整五维Pareto集。

```powershell
.\build_task4.ps1
python verify_task4_solver.py
python run_task4.py --output-dir results_task4_reproduction --workers 4 --resume
python verify_task4_results.py results_task4_reproduction --workers 4
python analyze_task4.py results_task4_reproduction
```

Linux完整复现：`TASK4_WORKERS=16 TASK4_VERIFY_WORKERS=16 bash run_task4_batch.sh`。需要任务三的已认证结果。正式文件为 `results_task4/result4_研XXX.csv`，包含时间优先、平稳优先、均衡、单纯时间最短四种方案。

模型、正确性与复现细节见 [任务四方法](docs/task4.md)，实测结果见 [任务四验证与分析](docs/task4_validation.md)。

## 任务二结果与验证

全部90组完成后，正式文件为 `results_task2_exact/result2_研XXX.csv`；只完成部分查询时，程序只生成 `.partial.csv`，不能作为全题答案。

```bash
python verify_task2_results.py results_task2_exact
```

| 数据集 | 完成查询数 | 目标向量记录数 |
| --- | ---: | ---: |
| NY | 30 | 1,640,101 |
| BAY | 30 | 556,813 |
| COL | 30 | 826,856 |
| 合计 | **90** | **3,023,770** |

完整结果CSV约144MB，已配置Git LFS；90个精确断点和核验所需状态表也纳入保留范围。另有便于阅读的 [验证记录](docs/validation.md)、[逐查询核验报告](docs/validation/verification_report.json) 和 [运行统计](docs/validation/task2_status.csv)。

`XXX` 为队号占位符。题目附件和原始数据保持来源不变，本仓库没有为这些附件额外授予转载许可。

## 上传前

```bash
git status --short
git diff --check
```

提交正式源码、文档、题目、所需输入及白名单内的答案和复核资料；大文件必须连同 `.gitattributes` 使用Git LFS。不要强制添加仍被忽略的归档、EXE、日志、临时断点或 `.partial.csv`。此次整理不自动提交、推送或改写已有Git历史。
