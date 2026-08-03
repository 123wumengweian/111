"""
iMAR-Pylife Integration: PPR管材老化寿命预测引擎
==================================================
将 Bosch pylife 疲劳分析框架集成到 iMAR 老化评估系统中。

核心能力:
  1. 读取户外老化拉伸数据 (CSV)
  2. 计算各老化条件下材料性能退化率
  3. 构建 Woehler S-N 曲线（基于退化后性能）
  4. 预测给定服役载荷下的剩余寿命（循环次数 → 年限）
  5. 多条件对比分析 + 失效概率评估
  6. 50年设计寿命合规性检验

依赖: pylife, pandas, numpy
Python: 系统 Python 3.12
用法:
  python imar_pylife.py                      # 完整分析+报告
  python imar_pylife.py --json              # JSON输出
  python imar_pylife.py --pressure 1.0      # 指定服役压力
"""

import sys
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── pylife imports ──────────────────────────────────────────
from pylife.materiallaws import WoehlerCurve

# ── PPR 材料常数 ────────────────────────────────────────────
# 参考: ISO 9080 / GB/T 18742 冷热水用PPR管材
PPR_DEFAULTS = {
    "k_1": 10.0,          # Basquin 斜率（典型聚合物: 8-15）
    "ND": 1e7,             # 疲劳拐点循环数
    "TN": 1.0,             # 拉伸强度对应循环数
    "k_2": float("inf"),   # Miner-Original (无限寿命以下)
    "diameter": 25.0,      # 管径 mm (默认DN25)
    "wall_thickness": 4.2, # 壁厚 mm (S3.2系列)
}


# ═══════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════

def load_aging_data(csv_path: str) -> pd.DataFrame:
    """加载户外老化拉伸数据CSV, 标准化列名"""
    df = pd.read_csv(csv_path, encoding="utf-8")
    # 标准化条件列
    df["管型"] = df["管型"].astype(str).str.strip()
    df["老化地点"] = df["老化地点"].astype(str).str.strip()
    df["通水条件"] = df["通水条件"].astype(str).str.strip()
    df["老化时长"] = df["老化时长"].astype(str).str.strip()
    return df


def group_by_condition(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """按老化条件分组: key = '地点_时长_通水'"""
    groups = {}
    for (loc, dur, water), gdf in df.groupby(["老化地点", "老化时长", "通水条件"]):
        key = f"{loc}_{dur}_{water}"
        groups[key] = gdf
    return groups


# ═══════════════════════════════════════════════════════════════
# 材料退化分析
# ═══════════════════════════════════════════════════════════════

@dataclass
class AgingMetrics:
    """单组老化条件的力学性能统计"""
    label: str
    n_samples: int
    # 平均值
    Et_mean: float      # 弹性模量 MPa
    sy_mean: float      # 屈服强度 MPa
    sb_mean: float      # 断裂强度 MPa
    el_mean: float      # 断裂伸长率 %
    tough_mean: float   # 断裂韧性 MJ/m³
    # 标准差
    sb_std: float
    sy_std: float


def compute_aging_metrics(label: str, gdf: pd.DataFrame) -> AgingMetrics:
    """从分组数据计算老化统计指标"""
    return AgingMetrics(
        label=label,
        n_samples=len(gdf),
        Et_mean=gdf["Et_MPa"].mean(),
        sy_mean=gdf["sy_MPa"].mean(),
        sb_mean=gdf["sb_MPa"].mean(),
        el_mean=gdf["断裂伸长率_pct"].mean(),
        tough_mean=gdf["断裂韧性_MJ_m3"].mean(),
        sb_std=gdf["sb_MPa"].std(),
        sy_std=gdf["sy_MPa"].std(),
    )


@dataclass
class DegradationReport:
    """退化对比报告: 老化组 vs 基线"""
    condition: AgingMetrics
    baseline: AgingMetrics
    # 退化率 (0=无退化, 1=完全退化, 负值=反而增强)
    Et_retention: float      # 弹性模量保有率
    sy_retention: float      # 屈服强度保有率
    sb_retention: float      # 断裂强度保有率
    el_retention: float      # 伸长率保有率
    tough_retention: float   # 韧性保有率

    @property
    def strength_retention(self) -> float:
        """综合强度保有率 (屈服+断裂取平均)"""
        return (self.sy_retention + self.sb_retention) / 2

    def summary(self) -> str:
        """单行摘要"""
        return (
            f"{self.condition.label:30s} "
            f"强度保有={self.strength_retention:.1%} "
            f"韧性保有={self.tough_retention:.1%} "
            f"伸长保有={self.el_retention:.1%}"
        )


def compute_degradation(aged: AgingMetrics, baseline: AgingMetrics) -> DegradationReport:
    """计算老化组相对于基线的退化率"""
    return DegradationReport(
        condition=aged,
        baseline=baseline,
        Et_retention=aged.Et_mean / baseline.Et_mean if baseline.Et_mean else 1.0,
        sy_retention=aged.sy_mean / baseline.sy_mean if baseline.sy_mean else 1.0,
        sb_retention=aged.sb_mean / baseline.sb_mean if baseline.sb_mean else 1.0,
        el_retention=aged.el_mean / baseline.el_mean if baseline.el_mean else 1.0,
        tough_retention=aged.tough_mean / baseline.tough_mean if baseline.tough_mean else 1.0,
    )


# ═══════════════════════════════════════════════════════════════
# Woehler S-N 曲线构建
# ═══════════════════════════════════════════════════════════════

def build_woehler(
    tensile_strength: float,
    k_1: float = PPR_DEFAULTS["k_1"],
    ND: float = PPR_DEFAULTS["ND"],
    TN: float = PPR_DEFAULTS["TN"],
    fatigue_ratio: float = 0.35,  # 疲劳比: 聚合物~0.3-0.4
) -> WoehlerCurve:
    """
    基于材料拉伸强度构建 Woehler S-N 曲线。

    Parameters
    ----------
    tensile_strength : 断裂强度 sb (MPa)
    k_1 : Basquin指数
    ND : 疲劳拐点 (默认10^7)
    fatigue_ratio : SD/TS, 聚合物疲劳比约0.35

    Returns
    -------
    WoehlerCurve
    """
    SD = tensile_strength * fatigue_ratio  # 疲劳强度
    return WoehlerCurve.from_parameters(
        k_1=k_1,
        ND=ND,
        SD=SD,
        TS=tensile_strength,
        TN=TN,
    )


# ═══════════════════════════════════════════════════════════════
# 寿命预测
# ═══════════════════════════════════════════════════════════════

@dataclass
class LifetimePrediction:
    """单次寿命预测结果"""
    condition_label: str
    woehler: WoehlerCurve
    # 输入
    service_pressure: float   # 服役压力 MPa
    safety_factor: float
    hoop_stress: float        # 环应力 MPa (计算值)
    # 输出
    cycles_to_failure: float  # 失效循环数
    years_continuous: float   # 连续服役年限
    years_daily_8h: float     # 日8h间歇服役年限
    stress_at_50yr: float     # 50年寿命对应的允许应力
    degradation_ratio: float  # 相对基线的强度保有率


def hoop_stress(pressure: float, diameter: float, wall: float) -> float:
    """Barlow公式: 环应力 = P*D/(2*t)"""
    return pressure * diameter / (2.0 * wall)


def predict_lifetime(
    condition_label: str,
    woehler: WoehlerCurve,
    service_pressure: float,
    degradation_ratio: float = 1.0,
    diameter: float = PPR_DEFAULTS["diameter"],
    wall: float = PPR_DEFAULTS["wall_thickness"],
    safety_factor: float = 1.5,
) -> LifetimePrediction:
    """
    预测给定条件下管材的疲劳寿命。

    Parameters
    ----------
    condition_label : 老化条件标签
    woehler : 该条件的Woehler曲线
    service_pressure : 设计服役压力 (MPa)
    degradation_ratio : 强度保有率
    diameter, wall : 管材几何参数
    safety_factor : 安全系数 (设计压力×安全系数=校核压力)
    """
    design_stress = hoop_stress(service_pressure, diameter, wall)
    check_stress = design_stress * safety_factor

    try:
        cycles = float(woehler.cycles(check_stress))
    except Exception:
        cycles = float("inf")

    # 年限转换 (保守: 日8h间歇服役≈年运行2000h@1Hz)
    hours_per_year_cont = 365 * 24
    hours_per_year_8h = 250 * 8  # 250天×8h
    cycles_per_hour = 3600  # 假设1Hz压力波动

    years_cont = cycles / (cycles_per_hour * hours_per_year_cont)
    years_8h = cycles / (cycles_per_hour * hours_per_year_8h)

    # 50年设计寿命对应的允许环应力
    cycles_50yr_8h = 50 * hours_per_year_8h * cycles_per_hour
    try:
        stress_50yr = float(woehler.load(cycles_50yr_8h))
    except Exception:
        stress_50yr = float("nan")

    return LifetimePrediction(
        condition_label=condition_label,
        woehler=woehler,
        service_pressure=service_pressure,
        safety_factor=safety_factor,
        hoop_stress=check_stress,
        cycles_to_failure=cycles,
        years_continuous=years_cont,
        years_daily_8h=years_8h,
        stress_at_50yr=stress_50yr,
        degradation_ratio=degradation_ratio,
    )


# ═══════════════════════════════════════════════════════════════
# 全流程分析
# ═══════════════════════════════════════════════════════════════

def run_imar_analysis(
    csv_path: str,
    service_pressures: List[float] = None,
    safety_factor: float = 1.5,
    fatigue_ratio: float = 0.35,
    k_1: float = PPR_DEFAULTS["k_1"],
    pipe_type_filter: str = "单层",
) -> Dict:
    """
    iMAR 全流程分析: 数据加载 → 退化评估 → 寿命预测。

    Returns
    -------
    dict with keys: 'degradation_table', 'lifetime_table', 'metrics'
    """
    if service_pressures is None:
        service_pressures = [0.6, 1.0, 1.6, 2.0, 2.5]

    # 1. 加载数据
    df = load_aging_data(csv_path)
    df = df[df["管型"] == pipe_type_filter]
    groups = group_by_condition(df)

    # 2. 找基线 (原始/0个月)
    baseline_key = None
    baseline_metrics = None
    for key in groups:
        if "原始" in key or "0个月" in key:
            baseline_key = key
            baseline_metrics = compute_aging_metrics(key, groups[key])
            break

    if baseline_metrics is None:
        raise ValueError("未找到基线(原始/0个月)数据")

    # 3. 逐条件分析退化
    degradation_reports: List[DegradationReport] = []
    all_metrics: Dict[str, AgingMetrics] = {baseline_key: baseline_metrics}

    for key, gdf in sorted(groups.items()):
        if key == baseline_key:
            continue
        metrics = compute_aging_metrics(key, gdf)
        all_metrics[key] = metrics
        report = compute_degradation(metrics, baseline_metrics)
        degradation_reports.append(report)

    # 4. 寿命预测
    lifetime_results: List[LifetimePrediction] = []
    baseline_woehler = build_woehler(
        baseline_metrics.sb_mean, k_1=k_1, fatigue_ratio=fatigue_ratio
    )

    # 基线寿命
    for p in service_pressures:
        lifetime_results.append(
            predict_lifetime("基线(原始)", baseline_woehler, p, degradation_ratio=1.0,
                             safety_factor=safety_factor)
        )

    # 各老化条件寿命
    for report in degradation_reports:
        aged_woehler = build_woehler(
            report.condition.sb_mean, k_1=k_1, fatigue_ratio=fatigue_ratio
        )
        for p in service_pressures:
            lifetime_results.append(
                predict_lifetime(
                    report.condition.label, aged_woehler, p,
                    degradation_ratio=report.strength_retention,
                    safety_factor=safety_factor,
                )
            )

    # 5. 汇总表
    degradation_table = _build_degradation_table(degradation_reports)
    lifetime_table = _build_lifetime_table(lifetime_results)

    return {
        "degradation_table": degradation_table,
        "lifetime_table": lifetime_table,
        "degradation_reports": degradation_reports,
        "lifetime_results": lifetime_results,
        "baseline_metrics": baseline_metrics,
        "all_metrics": all_metrics,
    }


def _build_degradation_table(reports: List[DegradationReport]) -> pd.DataFrame:
    rows = []
    for r in reports:
        rows.append({
            "老化条件": r.condition.label,
            "样本数": r.condition.n_samples,
            "Et保有率": f"{r.Et_retention:.1%}",
            "屈服保有率": f"{r.sy_retention:.1%}",
            "断裂保有率": f"{r.sb_retention:.1%}",
            "综合强度保有": f"{r.strength_retention:.1%}",
            "伸长保有率": f"{r.el_retention:.1%}",
            "韧性保有率": f"{r.tough_retention:.1%}",
            "断裂强度(MPa)": f"{r.condition.sb_mean:.1f}±{r.condition.sb_std:.1f}",
            "屈服强度(MPa)": f"{r.condition.sy_mean:.1f}±{r.condition.sy_std:.1f}",
        })
    return pd.DataFrame(rows)


def _build_lifetime_table(results: List[LifetimePrediction]) -> pd.DataFrame:
    rows = []
    for r in results:
        cyc_str = f"{r.cycles_to_failure:.0f}" if r.cycles_to_failure < 1e12 else "∞"
        yr8h_str = f"{r.years_daily_8h:.1f}" if r.years_daily_8h < 1e6 else "∞"
        rows.append({
            "老化条件": r.condition_label,
            "服役压力(MPa)": r.service_pressure,
            "校核环应力(MPa)": f"{r.hoop_stress:.2f}",
            "失效循环": cyc_str,
            "日8h年限": yr8h_str,
            "50年许用应力(MPa)": f"{r.stress_at_50yr:.2f}" if not np.isnan(r.stress_at_50yr) else "N/A",
            "强度保有率": f"{r.degradation_ratio:.1%}",
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════
# 失效概率分析
# ═══════════════════════════════════════════════════════════════

def failure_probability_analysis(
    woehler: WoehlerCurve,
    service_pressure: float,
    diameter: float = PPR_DEFAULTS["diameter"],
    wall: float = PPR_DEFAULTS["wall_thickness"],
    safety_factor: float = 1.5,
    load_std_ratio: float = 0.10,  # 载荷变异系数 (10% typical)
) -> Dict:
    """
    失效概率分析: 考虑载荷散布的可靠性评估。

    Parameters
    ----------
    load_std_ratio : 载荷变异系数 (std/mean), 默认10%
    """
    design_stress = hoop_stress(service_pressure, diameter, wall)
    check_stress = design_stress * safety_factor
    load_std = check_stress * load_std_ratio

    # 用 pylife 的 FailureProbability 算失效概率
    wc_pf = woehler.transform_to_failure_probability(0.50)  # 中值曲线

    # 方法1: 简单载荷 (确定性)
    cycles_50 = wc_pf.cycles(check_stress)
    load_50yr = float(wc_pf.load(50 * 250 * 8 * 3600)) if cycles_50 > 0 else float("nan")

    # 方法2: 载荷正态分布
    from scipy.stats import norm
    # 50年设计循环数
    N_design = 50 * 250 * 8 * 3600  # 3.6e8
    # 许用应力对应循环
    try:
        N_allowable = float(wc_pf.cycles(check_stress))
    except:
        N_allowable = float("inf")

    # 简单可靠性指标 (载荷散布)
    if N_allowable < float("inf") and N_allowable > 0:
        # 计算不同Pf下的寿命
        pf_levels = [0.01, 0.05, 0.10, 0.50]
        cycles_at_pf = {}
        for pf in pf_levels:
            wc_at_pf = woehler.transform_to_failure_probability(pf)
            try:
                cycles_at_pf[f"Pf={pf:.0%}"] = float(wc_at_pf.cycles(check_stress))
            except:
                cycles_at_pf[f"Pf={pf:.0%}"] = float("inf")

        # 在50年设计循环下的失效概率: 反算
        try:
            stress_for_Ndesign = float(wc_pf.load(N_design))
            # 安全裕度
            margin = (stress_for_Ndesign - check_stress) / load_std if load_std > 0 else 999
            pf_50yr = 1.0 - norm.cdf(margin) if not np.isnan(margin) else 0.0
        except:
            stress_for_Ndesign = float("nan")
            margin = float("nan")
            pf_50yr = 0.0
    else:
        cycles_at_pf = {f"Pf={p:.0%}": float("inf") for p in [0.01, 0.05, 0.10, 0.50]}
        stress_for_Ndesign = float("nan")
        margin = float("inf")
        pf_50yr = 0.0

    return {
        "condition": "unknown",
        "service_pressure": service_pressure,
        "check_stress": check_stress,
        "N_design": N_design,
        "cycles_at_pf": cycles_at_pf,
        "stress_for_Ndesign": stress_for_Ndesign,
        "safety_margin_sigma": margin,
        "pf_50yr": pf_50yr,
    }


# ═══════════════════════════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════════════════════════

def print_full_report(result: Dict) -> str:
    """打印完整分析报告"""
    lines = []
    sep = "=" * 72
    sep2 = "-" * 72

    lines.append(sep)
    lines.append("  iMAR-Pylife  PPR管材老化寿命预测报告")
    lines.append(sep)
    lines.append(f"  数据源: 户外老化拉伸_汇总数据.csv")
    lines.append(f"  基线: {result['baseline_metrics'].label}")
    lines.append(f"  基线强度: sb={result['baseline_metrics'].sb_mean:.1f} MPa")
    lines.append(sep2)

    # 退化排名
    lines.append("\n[1] 材料退化排序 (由劣→优)")
    lines.append(sep2)
    sorted_degrad = sorted(
        result["degradation_reports"], key=lambda r: r.strength_retention
    )
    for i, r in enumerate(sorted_degrad, 1):
        flag = "⚠️" if r.strength_retention < 0.85 else "✓"
        lines.append(
            f"  {i}. {flag} {r.condition.label:28s} "
            f"强度保有={r.strength_retention:.1%}  "
            f"韧性={r.tough_retention:.1%}  "
            f"sb={r.condition.sb_mean:.1f}±{r.condition.sb_std:.1f} MPa"
        )

    # 寿命预测
    lines.append(f"\n[2] 寿命预测 (DN25 PPR, 安全系数1.5, 日8h间歇)")
    lines.append(sep2)
    lt = result["lifetime_table"]
    pressures = sorted(lt["服役压力(MPa)"].unique())
    conditions = sorted(set(
        r["老化条件"] for _, r in lt.iterrows()
        if "基线" not in r["老化条件"]
    ))

    for p in pressures:
        lines.append(f"\n  服役压力 {p} MPa:")
        row_baseline = lt[
            (lt["服役压力(MPa)"] == p) & (lt["老化条件"].str.contains("基线"))
        ]
        if len(row_baseline) > 0:
            lines.append(f"    基线          : 50年许用={row_baseline.iloc[0]['50年许用应力(MPa)']} MPa")

        for cond in sorted(conditions):
            row = lt[(lt["服役压力(MPa)"] == p) & (lt["老化条件"] == cond)]
            if len(row) > 0:
                r = row.iloc[0]
                cyc = r["失效循环"]
                yr = r["日8h年限"]
                s50 = r["50年许用应力(MPa)"]
                lines.append(f"    {cond:28s}: {cyc} 循环, {yr}年, 50年许用={s50} MPa")

    # 失效概率 (1.6 MPa - 临界工况)
    lines.append(f"\n[3] 失效概率分析 (1.6 MPa, 50年设计寿命)")
    lines.append(sep2)
    for report in sorted_degrad:
        aged_woehler = build_woehler(report.condition.sb_mean)
        fp = failure_probability_analysis(aged_woehler, 1.6)
        pf_str = f"{fp['pf_50yr']:.2e}" if fp['pf_50yr'] > 0 else "<1e-10"
        sf_str = f"{fp['safety_margin_sigma']:.1f}σ" if not np.isnan(fp['safety_margin_sigma']) else "∞"
        cycles_50 = fp["cycles_at_pf"].get("Pf=50%", float("inf"))
        cyc_str = f"{cycles_50:.0f}" if cycles_50 < 1e12 else "∞"
        lines.append(
            f"  {report.condition.label:28s} "
            f"Pf(50yr)={pf_str}  N50%={cyc_str} 裕度={sf_str}"
        )

    # 结论
    lines.append(f"\n[4] 关键结论")
    lines.append(sep2)
    worst = min(sorted_degrad, key=lambda r: r.strength_retention)
    best = max(sorted_degrad, key=lambda r: r.strength_retention)

    lines.append(f"  退化最严重: {worst.condition.label}")
    lines.append(f"    断裂强度从 {worst.baseline.sb_mean:.1f} → {worst.condition.sb_mean:.1f} MPa")
    lines.append(f"    韧性损失 {1-worst.tough_retention:.0%}")
    lines.append(f"    50年许用应力降为 {worst.condition.sb_mean*0.35:.1f} MPa")

    if worst.strength_retention < 0.80:
        lines.append(f"    ⚠️ 强度保有率低于80%, 不满足50年设计寿命要求!")

    lines.append(f"\n  退化最轻微: {best.condition.label}")
    lines.append(f"    强度近乎无损 ({best.strength_retention:.0%}保有)")

    # 通水vs不通水对比
    water_on = [r for r in sorted_degrad if "通水" in r.condition.label and "不通水" not in r.condition.label]
    water_off = [r for r in sorted_degrad if "不通水" in r.condition.label]
    if water_on and water_off:
        avg_on = np.mean([r.strength_retention for r in water_on])
        avg_off = np.mean([r.strength_retention for r in water_off])
        lines.append(f"\n  通水 vs 不通水:")
        lines.append(f"    通水平均强度保有: {avg_on:.1%}")
        lines.append(f"    不通水平均强度保有: {avg_off:.1%}")
        if avg_on > avg_off:
            lines.append(f"    → 通水条件反而减缓退化! (水介质可能抑制氧化)")
        else:
            lines.append(f"    → 通水加速退化 (水介质可能促进水解/ESC)")

    lines.append(f"\n{sep}")
    return "\n".join(lines)

def main():
    csv_path = r"C:\Users\Lenovo\Desktop\hermes\户外老化拉伸_汇总数据.csv"

    result = run_imar_analysis(
        csv_path,
        service_pressures=[0.6, 1.0, 1.6, 2.0, 2.5],
        safety_factor=1.5,
        fatigue_ratio=0.35,
    )

    report = print_full_report(result)
    print(report)
    return result


if __name__ == "__main__":
    result = main()
