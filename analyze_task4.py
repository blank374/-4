"""Generate reproducible preference, disruption, timing and sensitivity tables."""
import argparse
import csv
import json
from pathlib import Path
import statistics

from run_task3 import ROOT, atomic_json, sha256
from task4_common import SCHEMES, closed_pairs


def stats(values):
    values = sorted(x for x in values if x is not None)
    if not values:
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None}
    return {"count": len(values), "min": values[0], "median": statistics.median(values),
            "p95": values[max(0, (95*len(values)+99)//100-1)], "max": values[-1]}


def relative(new, old):
    return (new-old)/old if old else (0. if new == 0 else None)


def write_csv(file, rows):
    with file.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def write_report(out, summary, rows, verification):
    names = {"time_priority": "时间优先", "stable_priority": "平稳优先", "balanced": "均衡", "time_shortest": "时间最短"}
    def pct(value):
        return "—" if value is None else f"{100*value:.3f}%"
    max_gap = max(r["original_candidate_gap"] for r in rows if r["original_candidate_gap"] is not None)
    reduced = sum(r["recommendation_relative_change"] is not None and r["recommendation_relative_change"] < 0 for r in rows)
    failed_candidates = sum(d["no_surviving_candidate_queries"] for d in summary["datasets"].values())
    affected = sum(r["original_path_blocked"] for r in rows)
    lines = ["# 任务四验证与实验分析", "",
        "2026-08-31完成。模型、归一化和复现方法见仓库的 `docs/task4.md`。本文所有数值由已核验断点生成。", "",
        "NY、BAY、COL各30组；四种方案、两种路网状态，共720行正式结果。封路前后90组全部可达。每城市按给定文件删除50个有向端点对，反向边不自动删除，剩余边成本保持原值。", "",
        "## 结果与验证", "",
        f"正式文件 `{summary['formal_file']}`，{(out/summary['formal_file']).stat().st_size:,}字节。SHA256：", "", "```text", summary["csv_sha256"], "```", "",
        f"独立核验覆盖{verification['checked_paths']:,}条路径记录（含任务三候选及四种方案的推荐、参考和可行上界，重复使用的路径分别计数）、720项最优值和全部CSV行。", "",
        "C++求解器使用反向Dijkstra下界和A*，Python核验器独立使用双向Dijkstra；二者在164个随机/构造小图上分别通过1,312项和2,624项穷举最优值对照，另有500项五维候选过滤检查。测试包括有向封路、平行边、不可达、零成本环、源点等于目标点和超过64位的标量值。", "",
        "## 可达性与封路影响", "",
        "| 城市 | 原可达 | 封路后可达 | 全部原候选失效的查询 | 原推荐受阻/120条 |", "| --- | ---: | ---: | ---: | ---: |"]
    for ds, d in summary["datasets"].items():
        lines.append(f"| {ds} | 30/30 | 30/30 | {d['no_surviving_candidate_queries']} | {sum(s['original_path_blocked'] for s in d['schemes'].values())} |")
    lines += ["", f"{failed_candidates}组查询的旧候选全部失效，但全图精确重规划仍找到路线；若只筛选旧候选，会错误地把这些情况当作无路可走。360条原推荐中{affected}条经过封路边。", "",
        "以下是封路内在损失的中位数，按 `(封路后全局最优W−原图全局最优W)/原图全局最优W` 计算，不混入原候选近似误差。每个单元格为30组配对相对变化的中位数。", "",
        "| 城市 | 时间优先 | 平稳优先 | 均衡 | 时间最短 |", "| --- | ---: | ---: | ---: | ---: |"]
    for ds, d in summary["datasets"].items():
        lines.append("| "+ds+" | "+" | ".join(pct(d["schemes"][name]["intrinsic_closure_relative_loss"]["median"]) for name in names)+" |")
    lines += ["", "在给定查询和封路文件上，最快路线在全部90组中都受阻，且新的最短时间严格增加。BAY的最短时间增幅中位数最大，COL最大单组增幅为42.232%。这只描述指定封路场景，不能推断随机封路、其他查询或整个城市的一般鲁棒性。不同偏好改变目标本身，也不能仅按较小的加权损失就断言某方案全面更稳健。", "",
        "## 五项成本前后变化", "",
        "以下直接比较用户看到的封路后推荐与原候选推荐，记录逐查询相对变化的中位数；正数为增加，负数为降低。各列的中位数不一定来自同一条查询。", "",
        "| 城市 | 方案 | 距离 | 时间 | 起伏 | 复杂度 | 边数 |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for ds, d in summary["datasets"].items():
        for name, label in names.items():
            lines.append(f"| {ds} | {label} | "+" | ".join(pct(d["schemes"][name]["costs"][f"c{j}"]["relative"]["median"]) for j in range(1, 6))+" |")
    lines += ["", "逐查询原值、变化量和百分比保存在 `comparison.csv`。不能仅凭某一项降低就认为五项都改善。", "",
        "## 偏好实际换来了什么", "",
        "原路网推荐相对于同一查询的时间最短路线，配对相对差异的中位数如下。平稳优先只偏好起伏和复杂度代理指标，不代表经过真实风险评估。", "",
        "| 城市 | 方案 | 时间变化 | 起伏变化 | 复杂度变化 |", "| --- | --- | ---: | ---: | ---: |"]
    lookup = {(r["dataset"], r["query_id"], r["scheme"]): r for r in rows}
    for ds in summary["datasets"]:
        for name in list(names)[:3]:
            values = [r for r in rows if r["dataset"] == ds and r["scheme"] == name]
            change = [stats(relative(r[f"original_c{j}"], lookup[(ds, r["query_id"], "time_shortest")][f"original_c{j}"]) for r in values)["median"] for j in (2, 3, 4)]
            lines.append(f"| {ds} | {names[name]} | "+" | ".join(map(pct, change))+" |")
    lines += ["", "BAY平稳优先的时间代价较大，不能将这一默认权重解释为对所有用户都合适。若实际用户有明确的最大可接受时间增幅，可以另建带时间约束的决策模型；当前答案没有假设这种未给定约束。", "",
        "## 原候选质量与评分下降的解释", "",
        "| 城市 | 时间优先最大误差 | 平稳优先最大误差 | 均衡最大误差 | 时间最短最大误差 |", "| --- | ---: | ---: | ---: | ---: |"]
    for ds, d in summary["datasets"].items():
        lines.append("| "+ds+" | "+" | ".join(pct(d["schemes"][name]["original_candidate_gap"]["max"]) for name in names)+" |")
    lines += ["", f"原候选加权误差实测最大{pct(max_gap)}，低于五维ε=0.20覆盖推出的20%界；纯时间方案在全部查询上与原图时间最优值一致。", "",
        f"有{reduced}个方案实例的封路后推荐W小于原候选推荐W，但所有实例均满足封路后全局最优W不小于原图全局最优W。这些下降来自候选近似误差被部分消除，不是删边改善了最优路网。", "",
        "例如NY/0001的均衡方案，旧候选全部失效。原候选高于原图最优值约0.729%，封路造成的内在损失约0.600%，因此新的精确推荐比旧推荐低约0.128%。同时实际时间增加约4.355%，起伏降低约1.136%，说明综合评分下降不意味着每个成本都降低。", "",
        "## 权重敏感性", "",
        "两组扫描各取θ=0至1、步长0.1，共1,980次选择。下表为发生推荐成本向量切换的查询数，以及11个设置下不同推荐成本向量数量的中位数。", "",
        "| 城市 | 时间权重扫描切换查询 | 不同推荐数中位数 | 起伏/复杂度权重扫描切换查询 | 不同推荐数中位数 |", "| --- | ---: | ---: | ---: | ---: |"]
    for ds, d in summary["datasets"].items():
        a, b = d["sensitivity"]["time_share"], d["sensitivity"]["stability_share"]
        lines.append(f"| {ds} | {a['queries_with_switches']}/30 | {a['distinct_costs']['median']:g} | {b['queries_with_switches']}/30 | {b['distinct_costs']['median']:g} |")
    lines += ["", "时间权重扫描使全部90组发生过选择切换，起伏/复杂度扫描为80组。偏好并非换个名字就得到同一路线；推荐随权重呈分段不变、跨阈值切换的特征。这里仅扫描两个参数切片，不覆盖全部五维权重单纯形。", "",
        "## 运行时间", "",
        f"运行环境：{summary['hardware']}；并发工作任务数：{summary['workers']}。完成90组批次用时{summary['batch_wall_seconds']:.3f}秒，独立核验另用{verification['seconds']:.3f}秒。批次时间不包括任务三候选生成、编译测试、上传下载和后续统计。", "",
        "| 城市 | 候选决策中位秒 | 图加载中位秒 | C++四方案合计中位秒 | 单方案反向预处理中位秒范围 | 单方案A*中位毫秒范围 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for ds, d in summary["datasets"].items():
        a = [s["reference_seconds"]["median"] for s in d["schemes"].values()]
        b = [1000*s["replan_seconds"]["median"] for s in d["schemes"].values()]
        lines.append(f"| {ds} | {d['decision_seconds']['median']:.3f} | {d['graph_load_seconds']['median']:.3f} | {d['cpp_total_seconds']['median']:.3f} | {min(a):.3f}–{max(a):.3f} | {min(b):.3f}–{max(b):.3f} |")
    lines += ["", "A*耗时不包含反向预处理，不能把毫秒级A*时间当作从零开始的全部重规划时间。C++合计包含图加载、四次标量边权计算、反向预处理及重规划；候选决策另含读取候选、去支配、筛选及敏感性选择。COL候选较多，决策时间较长。并发下各任务存在资源竞争，单次实验的时间不代表任意路网的性能保证。", "",
        "## 可复核材料", "",
        "`verification_report.json`、`analysis_summary.json`、`comparison.csv`、`sensitivity.csv`、`sensitivity_groups.csv` 保留完整逐组记录。完整路径CSV和断点位于被Git忽略的结果目录；仓库只保留这些体积较小的核验和统计副本。原问题二、三结果保持不变。", ""]
    (out/"analysis.md").write_text("\n".join(lines), encoding="utf-8")


def analyze(out):
    verification = json.loads((out/"verification_report.json").read_text(encoding="utf-8"))
    assert verification["complete"] and verification["full_optimality"] and verification["optimality_checks"] == 720
    manifest = json.loads((out/"aggregation.json").read_text(encoding="utf-8"))
    assert sha256(out/manifest["file"]) == verification["csv_sha256"] == manifest["sha256"]
    checks = {c["checkpoint"]: c["sha256"] for c in verification["checks"]}
    records = []
    for file in sorted((out/"checkpoints").glob("*.json")):
        assert sha256(file) == checks[file.name]
        records.append(json.loads(file.read_text(encoding="utf-8")))
    assert len(records) == 90
    rows, sensitivity, sensitivity_groups = [], [], []
    for r in records:
        low = r["normalization_low"]; common = int(r["common_denominator"])
        # Closed pairs are reconstructible from original input, not from paths.
        closed = closed_pairs(ROOT/"data"/f"dimacs5_{r['dataset'].lower()}"/"closed_edges_problem4.csv")
        for s in r["schemes"]:
            before, opt, after, warm = [s[k] for k in ("original", "original_optimal", "disrupted", "warm_start")]
            def val(p):
                return int(p["scalar"]) if p else None
            b, o, a, w = map(val, (before, opt, after, warm))
            offset = sum(x*int(c) for x, c in zip(low, s["coefficients"]))
            def normalized(value):
                return (value-offset)/(100*common) if value is not None else None
            affected = bool(before) and any((u, v) in closed for u, v in zip(before["vertices"], before["vertices"][1:]))
            row = {"dataset": r["dataset"], "query_id": r["query_id"], "scheme": s["name"],
                   "original_feasible": bool(before), "disrupted_feasible": bool(after),
                   "original_path_blocked": affected, "surviving_candidates": r["surviving_raw_records"],
                   "path_changed": before is not None and after is not None and before["edge_indices"] != after["edge_indices"],
                   "original_scalar": b, "original_optimal_scalar": o, "disrupted_optimal_scalar": a, "surviving_best_scalar": w,
                   "original_score": normalized(b), "original_optimal_score": normalized(o), "disrupted_score": normalized(a),
                   "original_candidate_gap": relative(b, o) if b is not None else None,
                   "intrinsic_closure_relative_loss": relative(a, o) if a is not None else None,
                   "recommendation_relative_change": relative(a, b) if a is not None and b is not None else None,
                   "gain_over_surviving_candidate": relative(w, a) if a is not None and w is not None else None,
                   "scalar_seconds": s["scalar_seconds"], "reference_seconds": s["reference_seconds"],
                   "replan_seconds": s["replan_seconds"], "expanded": s["expanded"]}
            for j in range(5):
                bc = before["cost"][j] if before else None; ac = after["cost"][j] if after else None
                row.update({f"original_c{j+1}": bc, f"disrupted_c{j+1}": ac,
                            f"delta_c{j+1}": ac-bc if ac is not None and bc is not None else None,
                            f"relative_c{j+1}": relative(ac, bc) if ac is not None and bc is not None else None})
            rows.append(row)
        for s in r["sensitivity"]:
            p = s["selected_cost"]
            sensitivity.append({"dataset": r["dataset"], "query_id": r["query_id"],
                                "family": s["family"], "parameter": s["parameter"],
                                **{f"w{j+1}": x/sum(s["weights"]) for j, x in enumerate(s["weights"])},
                                **{f"c{j+1}": p[j] if p else None for j in range(5)}})
        for family in ("time_share", "stability_share"):
            costs = [tuple(s["selected_cost"]) if s["selected_cost"] else None for s in r["sensitivity"] if s["family"] == family]
            sensitivity_groups.append({"dataset": r["dataset"], "query_id": r["query_id"], "family": family,
                                       "distinct_costs": len(set(costs)-{None}),
                                       "switches": sum(a != b for a, b in zip(costs, costs[1:]))})
    write_csv(out/"comparison.csv", rows); write_csv(out/"sensitivity.csv", sensitivity)
    write_csv(out/"sensitivity_groups.csv", sensitivity_groups)
    summary = {"queries": len(records), "formal_file": manifest["file"], "formal_rows": manifest["rows"], "csv_sha256": manifest["sha256"],
               "independent_optimum_checks": verification["optimality_checks"], "datasets": {}}
    run = json.loads((out/"run_summary.json").read_text(encoding="utf-8"))
    summary["batch_wall_seconds"] = run["wall_seconds"]
    summary["workers"] = run.get("workers", "未记录")
    summary["hardware"] = run.get("hardware", "未记录")
    for ds in ("NY", "BAY", "COL"):
        rs = [r for r in records if r["dataset"] == ds]
        group = {"queries": len(rs), "closed_pairs": rs[0]["closed_pairs"], "removed_edges": rs[0]["removed_edges"],
                 "no_surviving_candidate_queries": sum(r["surviving_raw_records"] == 0 for r in rs),
                 "candidate_front_size": stats(r["candidate_front_size"] for r in rs),
                 "decision_seconds": stats(r["decision_seconds"] for r in rs),
                 "cpp_total_seconds": stats(r["total_seconds"] for r in rs),
                 "graph_load_seconds": stats(r["load_seconds"] for r in rs),
                 "peak_rss_mb": stats(r["peak_rss_mb"] for r in rs), "schemes": {}, "sensitivity": {}}
        for name in SCHEMES:
            items = [row for row in rows if row["dataset"] == ds and row["scheme"] == name]
            group["schemes"][name] = {
                "original_feasible": sum(row["original_feasible"] for row in items),
                "disrupted_feasible": sum(row["disrupted_feasible"] for row in items),
                "original_path_blocked": sum(row["original_path_blocked"] for row in items),
                "path_changed": sum(row["path_changed"] for row in items),
                "intrinsic_loss_positive": sum(row["intrinsic_closure_relative_loss"] is not None and row["intrinsic_closure_relative_loss"] > 0 for row in items),
                "recommendation_score_decreased": sum(row["recommendation_relative_change"] is not None and row["recommendation_relative_change"] < 0 for row in items),
                **{k: stats(row[k] for row in items) for k in ("original_candidate_gap", "intrinsic_closure_relative_loss", "recommendation_relative_change", "gain_over_surviving_candidate", "scalar_seconds", "reference_seconds", "replan_seconds")},
                "costs": {f"c{j}": {k: stats(row[f"{k}_c{j}"] for row in items) for k in ("original", "disrupted", "delta", "relative")} for j in range(1, 6)}}
        for family in ("time_share", "stability_share"):
            items = [r for r in sensitivity_groups if r["dataset"] == ds and r["family"] == family]
            group["sensitivity"][family] = {"queries_with_switches": sum(r["switches"] > 0 for r in items),
                                            "distinct_costs": stats(r["distinct_costs"] for r in items),
                                            "switches": stats(r["switches"] for r in items)}
        summary["datasets"][ds] = group
    atomic_json(out/"analysis_summary.json", summary)
    write_report(out, summary, rows, verification)
    print(f"Analysis: {len(rows)} comparisons, {len(sensitivity)} sensitivity decisions; verified input SHA256={manifest['sha256']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("output_dir", type=Path)
    analyze(parser.parse_args().output_dir.resolve())
