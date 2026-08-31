# Linux并行运行

服务器连接地址、账号和SSH密钥由使用者自行配置，不写入仓库。把仓库和完整输入数据放入服务器上的项目目录后，在该目录执行以下命令。

## 编译和测试

```bash
g++ -O3 -DNDEBUG -std=c++17 -Wall -Wextra task2_exact.cpp -o task2_exact
./task2_exact --self-test
python3 verify_task2_exact.py ./task2_exact
```

## 后台运行

```bash
TASK2_WORKERS=16 nohup python3 -u run_task2_server.py > server.log 2>&1 < /dev/null &
```

默认16个独立查询并行，可通过 `TASK2_WORKERS` 设置为1～32。每个工作进程降低调度优先级，使用独立目录；不要直接启动多个求解器共同写同一个结果目录。

控制器有文件锁，避免重复启动。内存余量不足时暂停派发。默认不限制搜索时间，不采用近似结果。后台进程不依赖持续保持SSH连接。

## 查看进度

```bash
cat results_task2_exact/server_progress.json
tail -n 20 server.log
```

`phase=running` 表示仍在计算；`phase=verified_complete` 才表示90组完整并通过最终文件核验。进度文件约15秒更新一次。

运行期间以进度JSON为准，正式状态表和CSV在全部查询结束后汇总。每组详细日志位于 `results_task2_exact/.workers/<城市>_<查询>/run.log`。

## 中断与续算

需要让当前查询完成后停止派发时，可以创建 `results_task2_exact/STOP_AFTER_CURRENT` 标记。控制器停止后保留完成断点。下次运行前移走该标记。

意外退出后，确认旧控制器已结束，再用同一后台命令启动即可续算。已经完成的查询会跳过；没有完整断点的查询重新计算。

新机器迁移断点时，须同时保持完全相同的边表、查询表和兼容求解器版本。仅复制 `.task2_exact/` 中完整断点及版本文件，不把临时文件当作完成结果。

## 正式结果

完整结束后自动生成：

- `results_task2_exact/result2_研XXX.csv`
- `results_task2_exact/task2_status.csv`
- `results_task2_exact/verification_report.json`

还可以再次手工核验：

```bash
python3 verify_task2_results.py results_task2_exact
```

结果和断点均被 `.gitignore` 排除，另行下载或归档，不作为源码提交。
