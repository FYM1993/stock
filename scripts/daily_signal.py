#!/usr/bin/env python3
"""
每日交易信号生成器
==================

职责：盘后运行，输出明天的候选股票池
- 加载 run_strategy.py 训练好的模型
- 增量更新数据
- 纯推理，不做训练

使用方式：
    # 第一步：先用 run_strategy.py 训练并回测，确认效果 OK
    python scripts/run_strategy.py

    # 第二步：每天盘后跑这个（会自动增量更新数据）
    python scripts/daily_signal.py
"""

import sys
import json
import yaml
import argparse
from pathlib import Path
from datetime import datetime

import qlib
from qlib.workflow import R
from qlib.utils import init_instance_by_config


# ============ 配置 ============
CONFIG_PATH = "config.yaml"
PORTFOLIO_FILE = "portfolio.json"


def load_config(config_path=CONFIG_PATH):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_portfolio(portfolio_file=PORTFOLIO_FILE):
    pf_path = Path(portfolio_file)
    if pf_path.exists():
        with open(pf_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"holdings": [], "cash": 100000, "updated": ""}


def save_portfolio(portfolio, portfolio_file=PORTFOLIO_FILE):
    portfolio["updated"] = datetime.now().strftime("%Y-%m-%d")
    with open(portfolio_file, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)


# ================================================================
#  核心：从 mlruns 加载 run_strategy.py 训练好的模型
# ================================================================
def load_trained_model(experiment_name=None):
    """
    从 qlib mlruns 中加载最近一次训练好的模型
    experiment_name: 指定实验名，默认取最近一次
    """
    with R.start(experiment_name=experiment_name or "load_model", recorder_id=None):
        pass  # 只初始化，不训练

    # 获取最近的实验记录
    if experiment_name:
        exp = R.get_exp(experiment_name=experiment_name)
    else:
        # 遍历所有实验，找最近的
        from mlflow.tracking import MlflowClient
        client = MlflowClient()
        experiments = client.search_experiments()
        if not experiments:
            print("❌ 没有找到任何实验，请先运行: python scripts/run_strategy.py")
            sys.exit(1)

        # 按最近修改时间排序
        exp = None
        latest_time = 0
        for e in experiments:
            runs = client.search_runs(experiment_ids=[e.experiment_id],
                                      order_by=["attributes.start_time DESC"],
                                      max_results=1)
            if runs and runs[0].info.start_time > latest_time:
                latest_time = runs[0].info.start_time
                exp = e

        if exp is None:
            print("❌ 没有找到训练记录，请先运行: python scripts/run_strategy.py")
            sys.exit(1)

    # 获取最近一次 run
    recorder = R.get_recorder(experiment_name=exp.name)
    model = recorder.load_object("models/model.pkl")

    if model is None:
        print(f"❌ 实验 [{exp.name}] 中没有保存的模型")
        print("   请先运行: python scripts/run_strategy.py")
        sys.exit(1)

    print(f"✅ 模型已加载 (实验: {exp.name})")
    return model


# ================================================================
#  信号生成
# ================================================================
def generate_signals(config, model):
    """
    用已训练好的模型对最新数据生成预测
    返回: (top_stocks, bottom_stocks)
    """
    qlib.init(**config["qlib_init"])

    instruments = config["dataset"]["kwargs"]["handler"]["kwargs"]["instruments"]
    print(f"📈 股票池: {instruments}")

    # 构建 dataset（只用最新数据，不需要训练集）
    dataset = init_instance_by_config(config["dataset"])
    pred = model.predict(dataset)

    if pred is None or len(pred) == 0:
        print("❌ 预测结果为空，请检查数据和 end_time 配置")
        return [], []

    # 取最新一天的预测
    if hasattr(pred.index, "get_level_values"):
        latest_date = pred.index.get_level_values(0).max()
        latest_pred = pred.loc[latest_date]
    else:
        latest_pred = pred

    topk = config["port_analysis_config"]["strategy"]["kwargs"]["topk"]
    n_drop = config["port_analysis_config"]["strategy"]["kwargs"]["n_drop"]

    sorted_pred = latest_pred.sort_values(ascending=False)
    top_stocks = [
        (str(idx), float(val), rank + 1)
        for rank, (idx, val) in enumerate(sorted_pred.head(topk).items())
    ]
    bottom_stocks = [
        (str(idx), float(val), rank + 1)
        for rank, (idx, val) in enumerate(sorted_pred.tail(n_drop).items())
    ]

    return top_stocks, bottom_stocks


# ================================================================
#  交易计划
# ================================================================
def generate_trade_plan(config, top_stocks, bottom_stocks, portfolio):
    topk = config["port_analysis_config"]["strategy"]["kwargs"]["topk"]
    total_capital = portfolio.get("cash", 100000) + sum(
        h.get("value", 0) for h in portfolio.get("holdings", [])
    )

    current_holdings = {h["code"]: h for h in portfolio.get("holdings", [])}
    target_codes = {s[0] for s in top_stocks}
    bottom_codes = {s[0] for s in bottom_stocks}

    sells = [
        {"action": "SELL", "code": code, "reason": "排名跌出"}
        for code in current_holdings
        if code in bottom_codes
    ]

    buys = [
        {
            "action": "BUY",
            "code": code,
            "score": round(score, 6),
            "rank": rank,
            "suggest_amount": round(total_capital / topk, 0),
        }
        for code, score, rank in top_stocks
        if code not in current_holdings
    ]

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_capital": round(total_capital, 2),
        "current_holdings": len(current_holdings),
        "target": topk,
        "sells": sells,
        "buys": buys,
    }


# ================================================================
#  输出报告
# ================================================================
def print_report(top_stocks, bottom_stocks, trade_plan):
    today = datetime.now().strftime("%Y-%m-%d")
    print("\n" + "=" * 60)
    print(f"📋 交易信号报告 — {today}")
    print("=" * 60)

    print(f"\n🟢 买入候选 (Top {len(top_stocks)}):")
    print(f"{'排名':>4}  {'股票代码':<12}  {'预测分数':>12}")
    print("-" * 35)
    for code, score, rank in top_stocks:
        print(f"{rank:>4}  {code:<12}  {score:>12.6f}")

    print(f"\n🔴 卖出候选 (Bottom {len(bottom_stocks)}):")
    for code, score, rank in bottom_stocks:
        print(f"  {code:<12}  {score:>12.6f}")

    print(f"\n📝 交易计划:")
    print(f"  总资金: ¥{trade_plan['total_capital']:,.0f}")
    print(f"  当前持仓: {trade_plan['current_holdings']} → 目标: {trade_plan['target']}")

    if trade_plan["sells"]:
        print(f"\n  ⬇️ 卖出:")
        for s in trade_plan["sells"]:
            print(f"    SELL {s['code']}  ({s['reason']})")

    if trade_plan["buys"]:
        print(f"\n  ⬆️ 买入:")
        for b in trade_plan["buys"]:
            print(f"    BUY  {b['code']}  #{b['rank']}  ¥{b['suggest_amount']:,.0f}")

    if not trade_plan["sells"] and not trade_plan["buys"]:
        print("\n  ✅ 无需调仓")

    print("\n" + "=" * 60)


# ================================================================
#  主入口
# ================================================================
def main():
    parser = argparse.ArgumentParser(description="每日交易信号（纯推理，不训练）")
    parser.add_argument("--config", default=CONFIG_PATH)
    parser.add_argument("--experiment", default=None,
                        help="指定实验名（默认取最近一次训练）")
    parser.add_argument("--output", default=None,
                        help="输出信号到 JSON 文件")
    args = parser.parse_args()

    config = load_config(args.config)

    # ---- Step 1: 增量更新数据 ----
    print("=" * 60)
    print("📦 Step 1: 增量更新 qlib 数据")
    print("=" * 60)
    from scripts.update_daily_data import update_daily
    latest_date = update_daily(
        qlib_dir=config["qlib_init"]["provider_uri"],
    )

    # 动态更新 config 的 end_time
    if latest_date:
        config["dataset"]["kwargs"]["handler"]["kwargs"]["end_time"] = str(latest_date)
        config["port_analysis_config"]["backtest"]["end_time"] = str(latest_date)
        print(f"📅 end_time 已更新为: {latest_date}\n")

    # ---- Step 2: 加载模型 ----
    print("=" * 60)
    print("🧠 Step 2: 加载模型")
    print("=" * 60)
    model = load_trained_model(experiment_name=args.experiment)

    # ---- Step 3: 生成信号 ----
    print("\n" + "=" * 60)
    print("📊 Step 3: 生成预测信号")
    print("=" * 60)
    top_stocks, bottom_stocks = generate_signals(config, model)

    if not top_stocks:
        print("❌ 没有生成任何信号")
        sys.exit(1)

    # ---- Step 4: 交易计划 ----
    portfolio = load_portfolio()
    trade_plan = generate_trade_plan(config, top_stocks, bottom_stocks, portfolio)

    # ---- 输出 ----
    print_report(top_stocks, bottom_stocks, trade_plan)

    # 保存到文件
    if args.output:
        result = {
            "top_stocks": top_stocks,
            "bottom_stocks": bottom_stocks,
            "trade_plan": trade_plan,
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n💾 信号已保存到: {args.output}")


if __name__ == "__main__":
    main()
