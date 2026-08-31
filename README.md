# 城市道路网络多目标路径规划

任务一、二的正式求解与验证代码。任务三、四尚未实现，不包含在本仓库的完成范围内。

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
| `data/` | 原始图、合并边表、固定查询和关闭边表 |
| `examples/` | 题目规定的四种结果格式示例 |
| `docs/` | 模型说明、运行方法及验证记录 |

生成结果放在 `results_task1/` 或 `results_task2_exact/`，不纳入 Git。旧方法、临时实验和含实际服务器信息的历史说明归档在本机 `_local_archive/`，同样不上传。

## 环境

- Python 3.10 或更高版本，仅使用标准库。
- 支持 C++17 的 GCC；Windows 使用 MinGW-w64 g++，Linux 使用 g++。
- Windows 编译依赖系统 `psapi`、`shell32` 库。

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

## 结果与验证

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

完整结果CSV约144MB，不随源码提交。仓库保留小体积的 [验证记录](docs/validation.md)、[逐查询核验报告](docs/validation/verification_report.json) 和 [运行统计](docs/validation/task2_status.csv)。

`XXX` 为队号占位符。题目附件和原始数据保持来源不变，本仓库没有为这些附件额外授予转载许可。

## 上传前

```bash
git status --short
git diff --check
```

只提交正式源码、文档、题目及所需数据，不要强制添加被忽略的归档、EXE、运行日志、断点或完整结果CSV。此次整理不改写已有 Git 历史。
