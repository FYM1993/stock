"""
Qlib 因子模型回测 — 多方案对比

核心发现：LightGBM是树模型，不需要特征标准化（RobustZScoreNorm反而降低性能）。
CSI500成分股列表截至2022年，只能用全市场。

方案对比(不同TopK + 标签周期)，通过命令行 --period 切换回测区间。
"""

import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["MPLCONFIGDIR"] = "/tmp/mpl"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import warnings
warnings.filterwarnings("ignore")

import qlib
from qlib.config import REG_CN
from qlib.data.dataset import DatasetH
from qlib.contrib.data.handler import Alpha158
from qlib.backtest import backtest as qlib_backtest
from qlib.backtest import executor as qlib_executor
from qlib.utils import init_instance_by_config

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import argparse

PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "qlib_data" / "cn_data"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

PERIODS = {
    "2025": {
        "train_start": "2023-01-01",
        "train_end": "2025-03-31",
        "valid_start": "2025-04-01",
        "valid_end": "2025-04-30",
        "test_start": "2025-05-01",
        "test_end": "2025-08-31",
    },
    "2026": {
        "train_start": "2025-05-01",
        "train_end": "2025-10-31",
        "valid_start": "2025-11-01",
        "valid_end": "2025-12-31",
        "test_start": "2026-01-02",
        "test_end": "2026-03-11",
    },
}

TRAIN_START = ""
TRAIN_END   = ""
VALID_START = ""
VALID_END   = ""
TEST_START  = ""
TEST_END    = ""


def build_dataset(market="all", label_expr=None):
    """Alpha158: 158个量价因子, 不做特征标准化(树模型不需要)"""
    infer_processors = [
        {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
    ]
    learn_processors = [
        {"class": "DropnaLabel"},
        {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
    ]

    label_kwarg = {}
    if label_expr:
        label_kwarg["label"] = ([label_expr], ["LABEL0"])

    handler = Alpha158(
        instruments=market,
        start_time=TRAIN_START,
        end_time=TEST_END,
        fit_start_time=TRAIN_START,
        fit_end_time=TRAIN_END,
        infer_processors=infer_processors,
        learn_processors=learn_processors,
        **label_kwarg,
    )

    dataset = DatasetH(
        handler=handler,
        segments={
            "train": (TRAIN_START, TRAIN_END),
            "valid": (VALID_START, VALID_END),
            "test":  (TEST_START, TEST_END),
        },
    )
    return dataset


def train_model(dataset):
    """LightGBM — 参数针对A股短期因子调优"""
    model_config = {
        "class": "LGBModel",
        "module_path": "qlib.contrib.model.gbdt",
        "kwargs": {
            "loss": "mse",
            "colsample_bytree": 0.8879,
            "learning_rate": 0.0421,
            "subsample": 0.8789,
            "lambda_l1": 205.6999,
            "lambda_l2": 580.9768,
            "max_depth": 8,
            "num_leaves": 210,
            "num_threads": 1,
            "n_estimators": 1000,
            "early_stopping_rounds": 100,
            "verbosity": -1,
        },
    }
    model = init_instance_by_config(model_config)
    model.fit(dataset)
    return model


def run_backtest(pred, topk=30, n_drop=5):
    """回测"""
    test_pred = pred.loc[pred.index.get_level_values("datetime") >= pd.Timestamp(TEST_START)]

    strategy_config = {
        "class": "TopkDropoutStrategy",
        "module_path": "qlib.contrib.strategy",
        "kwargs": {
            "signal": test_pred,
            "topk": topk,
            "n_drop": n_drop,
        },
    }
    strategy = init_instance_by_config(strategy_config)
    executor_obj = qlib_executor.SimulatorExecutor(
        time_per_step="day", generate_portfolio_metrics=True,
    )

    portfolio_metric_dict, _ = qlib_backtest(
        start_time=TEST_START,
        end_time=TEST_END,
        strategy=strategy,
        executor=executor_obj,
        benchmark="000300.SH",
        account=1_000_000,
        exchange_kwargs={
            "freq": "day",
            "limit_threshold": 0.095,
            "deal_price": "close",
            "open_cost": 0.0005,
            "close_cost": 0.0015,
            "min_cost": 5,
        },
    )
    return portfolio_metric_dict


def analyze(portfolio_metric_dict, name=""):
    """提取回测指标"""
    report, positions = portfolio_metric_dict.get("1day", (None, None))
    if report is None or report.empty:
        print(f"  [{name}] 未生成有效报告")
        return None

    rets = report["return"].fillna(0)
    cum = (1 + rets).cumprod()
    total_ret = cum.iloc[-1] - 1
    peak = cum.cummax()
    max_dd = (cum / peak - 1).min()
    ann_ret = (1 + total_ret) ** (252 / len(rets)) - 1
    excess_rets = rets - 0.03 / 252
    sharpe = excess_rets.mean() / excess_rets.std() * (252 ** 0.5) if excess_rets.std() > 0 else 0
    win_rate = (rets > 0).mean()
    avg_win = rets[rets > 0].mean() if (rets > 0).any() else 0
    avg_loss = abs(rets[rets < 0].mean()) if (rets < 0).any() else 1
    plr = avg_win / avg_loss if avg_loss > 0 else float("inf")

    bench = report.get("bench", None)
    bench_total = (1 + bench.fillna(0)).prod() - 1 if bench is not None else None

    report["month"] = report.index.to_period("M")
    monthly = report.groupby("month")["return"].apply(lambda x: (1 + x).prod() - 1)

    return {
        "name": name,
        "total_return": total_ret,
        "ann_return": ann_ret,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "win_rate": win_rate,
        "plr": plr,
        "bench_return": bench_total,
        "excess_return": total_ret - bench_total if bench_total is not None else None,
        "monthly": monthly,
        "report": report,
    }


def print_comparison(results_list):
    """打印对比表"""
    valid = [r for r in results_list if r is not None]
    if not valid:
        print("所有实验均失败")
        return

    print("\n" + "=" * 90)
    print(f"多方案对比 ({TEST_START} ~ {TEST_END})")
    print("=" * 90)
    print(f"{'方案':<32} {'总收益':>8} {'年化':>8} {'回撤':>8} {'夏普':>6} {'胜率':>6} {'盈亏比':>6} {'超额':>8}")
    print("-" * 90)
    for r in valid:
        exc = f"{r['excess_return']*100:>+7.2f}%" if r['excess_return'] is not None else "    N/A"
        print(
            f"{r['name']:<32}"
            f" {r['total_return']*100:>+7.2f}%"
            f" {r['ann_return']*100:>+7.2f}%"
            f" {r['max_drawdown']*100:>7.2f}%"
            f" {r['sharpe']:>6.2f}"
            f" {r['win_rate']*100:>5.1f}%"
            f" {r['plr']:>6.2f}"
            f" {exc}"
        )

    print()
    for r in valid:
        mstr = "  ".join(f"{m}={v*100:+.1f}%" for m, v in r["monthly"].items())
        print(f"  [{r['name'][:20]}] 月度: {mstr}")

    best = max(valid, key=lambda x: x["excess_return"] or -999)
    print(f"\n★ 超额最高: {best['name']} (超额 {best['excess_return']*100:+.2f}%)")


def run_one(name, dataset, model, topk, n_drop):
    """用已有数据集+模型跑一个topk配置"""
    print(f"  回测 {name} (topk={topk}, n_drop={n_drop})...")
    pm = run_backtest(model._pred, topk=topk, n_drop=n_drop)
    result = analyze(pm, name=name)
    if result:
        print(f"    → 收益 {result['total_return']*100:+.2f}%, "
              f"回撤 {result['max_drawdown']*100:.2f}%, "
              f"超额 {(result['excess_return'] or 0)*100:+.2f}%")
    return result


def main():
    global TRAIN_START, TRAIN_END, VALID_START, VALID_END, TEST_START, TEST_END

    parser = argparse.ArgumentParser(description="Qlib Alpha158 因子模型回测")
    parser.add_argument("--period", choices=list(PERIODS.keys()), default="2026",
                        help="回测区间 (default: 2026)")
    args = parser.parse_args()

    p = PERIODS[args.period]
    TRAIN_START = p["train_start"]
    TRAIN_END   = p["train_end"]
    VALID_START = p["valid_start"]
    VALID_END   = p["valid_end"]
    TEST_START  = p["test_start"]
    TEST_END    = p["test_end"]

    print("=" * 60)
    print(f"Qlib Alpha158 因子模型 — 多方案对比 [{args.period}]")
    print("=" * 60)

    qlib.init(provider_uri=str(DATA_PATH), region=REG_CN)
    print(f"数据: {DATA_PATH}")
    print(f"训练: {TRAIN_START}~{TRAIN_END} | 验证: {VALID_START}~{VALID_END} | 测试: {TEST_START}~{TEST_END}")

    all_results = []

    # ========== 2日标签 (默认) ==========
    print("\n" + "=" * 60)
    print("[组1] Alpha158 + 2日标签 + 不同TopK")
    print("=" * 60)

    print("  构建数据集(158因子, label=2日收益)...")
    ds_2d = build_dataset(market="all")
    print("  训练LightGBM...")
    model_2d = train_model(ds_2d)

    pred_2d = model_2d.predict(ds_2d)
    n_test = pred_2d.loc[pred_2d.index.get_level_values("datetime") >= pd.Timestamp(TEST_START)].shape[0]
    print(f"  预测信号: {pred_2d.shape[0]}条 (测试期{n_test}条)")

    # 给model挂上预测结果，方便后面复用
    model_2d._pred = pred_2d

    for topk, n_drop, suffix in [(30, 5, "Top30"), (15, 3, "Top15"), (10, 2, "Top10"), (5, 1, "Top5")]:
        r = run_one(f"A: 2日标签+{suffix}", ds_2d, model_2d, topk, n_drop)
        all_results.append(r)

    # ========== 5日标签 ==========
    print("\n" + "=" * 60)
    print("[组2] Alpha158 + 5日标签 + 不同TopK")
    print("=" * 60)

    print("  构建数据集(158因子, label=5日收益)...")
    ds_5d = build_dataset(market="all", label_expr="Ref($close, -5)/Ref($close, -1) - 1")
    print("  训练LightGBM...")
    model_5d = train_model(ds_5d)

    pred_5d = model_5d.predict(ds_5d)
    model_5d._pred = pred_5d
    n_test = pred_5d.loc[pred_5d.index.get_level_values("datetime") >= pd.Timestamp(TEST_START)].shape[0]
    print(f"  预测信号: {pred_5d.shape[0]}条 (测试期{n_test}条)")

    for topk, n_drop, suffix in [(15, 3, "Top15"), (10, 2, "Top10"), (5, 1, "Top5")]:
        r = run_one(f"B: 5日标签+{suffix}", ds_5d, model_5d, topk, n_drop)
        all_results.append(r)

    # ========== 10日标签 ==========
    print("\n" + "=" * 60)
    print("[组3] Alpha158 + 10日标签 + 不同TopK")
    print("=" * 60)

    print("  构建数据集(158因子, label=10日收益)...")
    ds_10d = build_dataset(market="all", label_expr="Ref($close, -10)/Ref($close, -1) - 1")
    print("  训练LightGBM...")
    model_10d = train_model(ds_10d)

    pred_10d = model_10d.predict(ds_10d)
    model_10d._pred = pred_10d
    n_test = pred_10d.loc[pred_10d.index.get_level_values("datetime") >= pd.Timestamp(TEST_START)].shape[0]
    print(f"  预测信号: {pred_10d.shape[0]}条 (测试期{n_test}条)")

    for topk, n_drop, suffix in [(15, 3, "Top15"), (10, 2, "Top10"), (5, 1, "Top5")]:
        r = run_one(f"C: 10日标签+{suffix}", ds_10d, model_10d, topk, n_drop)
        all_results.append(r)

    # ========== 对比输出 ==========
    print_comparison(all_results)

    # 保存最优
    valid = [r for r in all_results if r is not None]
    if valid:
        best = max(valid, key=lambda x: x["excess_return"] or -999)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        best["report"].to_csv(RESULTS_DIR / f"qlib_best_{ts}.csv")
        print(f"\n最优方案报告已保存: results/qlib_best_{ts}.csv")

    print("\n完成!")


if __name__ == "__main__":
    main()
