# 论文与独立复核资料

2026-08-31按“保留正式答案及论文证据、忽略临时产物”的规则整理。这里只修改本地纳入版本管理的范围，尚未因此自动提交或推送GitHub，也没有重新上传到已清理的计算服务器。

开放纳入Git的现有结果文件共1,280个，原始内容合计约1.09GB。逐文件大小、SHA256、是否使用Git LFS见 [资料清单](research_artifacts.json)。文件原始内容不做换行转换，保证Windows与Linux取得同样的哈希。

| 位置 | 保留内容 | 用于复核 |
| --- | --- | --- |
| `results_task1/` | 正式答案CSV | 单目标路线与五项累计成本 |
| `results_task2_exact/` | 正式CSV、90个`.exact`断点、状态表、验证报告、输入哈希清单 | 三目标结果完整性记录、内部非支配性及CSV与断点一致性 |
| `results_task3_certified/` | 正式CSV、270个已认证断点、selection、aggregation、验证报告 | 最终二维精确/三五维ε覆盖答案与来源；任务四候选输入 |
| `results_task4/` | 正式CSV、90个断点、验证报告、逐方案对照、权重扫描、汇总和分析 | 原推荐来源、封路可行性、精确标量最优值、敏感性与时间统计 |
| `results_task3/` | 初版441个断点与比较、运行、验证记录 | 优化前的质量与资源消耗 |
| `results_task3_optimized/` | 优化版360个断点与比较和优化汇总 | 优化后的同条件对照 |
| `results_task3_order31245_server/` | 最后1组换序试验的断点及报告 | 最终认证来源、额外试验开销的可追溯性 |

历史对照断点包含未认证或被资源上限截断的实验，这是解释算法表现的证据，**不能作为正式已认证答案**。问题三最终答案只认 `results_task3_certified/`。旧版大型 `.partial.csv` 不重复保存；质量对照脚本直接读取原始断点。

继续忽略：`_local_archive/`（包括云端清理前完整备份及可能含连接信息的历史文件）、`tmp/`、EXE与Linux二进制、缓存、日志、锁和PID、workers目录、`.partial.csv`、未被选入论文主对照的零散试跑、新复现实验目录。新结果不会仅因目录名类似就自动被纳入，需要重新核对其用途。

## 大文件与下载

问题二正式CSV约144MB、问题三约136MB，超过GitHub普通Git的100MiB文件限制。因此这两个文件及问题三各组原始路径JSON使用Git LFS；小文件与其他复核资料使用普通Git。[GitHub大文件规则](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

本机已为此仓库启用Git LFS。其他电脑克隆后执行：

```bash
git lfs install --local
git lfs pull
python verify_research_artifacts.py
```

若文件内容只有三行 `version`、`oid`、`size`，说明拿到的是LFS指针，需要先下载实际内容。网页源码ZIP不一定包含LFS实体，建议使用Git克隆与 `git lfs pull`。[Git LFS说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)

后续提交应同时包含 `.gitignore`、`.gitattributes` 和这些结果文件。不要仅上传LFS指针而跳过LFS推送钩子；实际上传是否成功还取决于远端权限和LFS存储/流量额度。此次整理没有消耗远端LFS上传额度，也不改写Git历史。

## 复核顺序

先运行 `verify_research_artifacts.py` 核对1,280个文件的字节数和哈希。这只证明取得了同一份资料，不等同于重新证明算法正确。之后按任务复核：

```bash
python verify_task2_results.py results_task2_exact
python verify_task3_results.py results_task3_certified
python verify_task4_results.py results_task4 --workers 4
```

问题四核验器会读取问题三原始候选和输入图，所以不能只下载问题四CSV。任务一可重新运行 `task1_solver.py --output-dir results_task1_reproduction --researcher XXX` 对照正式结果。

论文中的任务三优化前后对照可由保存的原始断点重新计算：

```bash
python compare_task3_optimization.py results_task3 results_task3_optimized --overrides results_task3_order31245_server
```

比较脚本与各任务验证器可能重新写出对应统计或验证报告，运行时长也会变化。建议在另一份克隆或复制目录中执行；若已在当前工作区运行，哈希清单可用于识别哪些结果报告发生了变化，不要把合法的重算报告变化误认为路径答案变化。

正式数据、图、查询和封路输入仍在 `data/`；源码、算法说明、轻量统计表仍在仓库原位置。`XXX`为队号占位符。将来修改队号或重新生成答案后，需要同步更新相应验证报告和资料清单。
