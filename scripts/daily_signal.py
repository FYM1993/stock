#!/usr/bin/env python3
"""
每日交易信号生成器
==================

每天运行一次，输出当天的买卖信号。
基于已训练好的模型，对当前股票池生成预测排名。

使用方式：
    # 首次：需要先训练模型并保存
    python scripts/daily_signal.py --train

    # 每日运行（直接加载已训练模型，生成今日信号）
    python scripts/daily_signal.py

    # 指定配置文件
    python scripts/daily_signal.py --config config.yaml

    # 指定持仓文件（跟踪当前持仓）
    python scripts/daily_signal.py --portfolio portfolio.json
"""

import sys
import json
import yaml
import argparse
from pathlib import Path
from datetime import datetime, timedelta

import qlib
from qlib.utils import init_instance_by_config
from qlib.workflow import R
from qlib.data import D


# ============ 配置 ============
CONFIG_PATH = "config.yaml"
MODEL_SAVE_DIR = "models"
PORTFOLIO_FILE = "portfolio.json"


def load_config(config_path: str) -> dict:
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_today_str():
    """获取今天的日期字符串"""
    return datetime.now().strftime("%Y-%m-%d")


def load_portfolio(portfolio_file: str) -> dict:
    """加载当前持仓"""
    pf_path = Path(portfolio_file)
    if pf_path.exists():
        with open(pf_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"holdings": [], "cash": 100000, "updated": ""}


def save_portfolio(portfolio_file: str, portfolio: dict):
    """保存当前持仓"""
    portfolio["updated"] = get_today_str()
    with open(portfolio_file, 'w', encoding='utf-8') as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)


def train_and_save(config: dict):
    """训练模型并保存"""
    print("=" * 60)
    print("🎯 训练模型并保存")
    print("=" * 60)

    qlib.init(**config["qlib_init"])

    model = init_instance_by_config(config["model"])
    dataset = init_instance_by_config(config["dataset"])

    print("📊 正在训练...")
    model.fit(dataset)

    # 保存模型
    model_dir = Path(MODEL_SAVE_DIR)
    model_dir.mkdir(exist_ok=True)
    model_path = model_dir / "latest_model.pkl"

    import pickle
    with open(model_path, 'wb') as f:
        pickle.dump(model, f)

    print(f"✅ 模型已保存到: {model_path}")
    return model, dataset


def load_model():
    """加载已保存的模型"""
    import pickle
    model_path = Path(MODEL_SAVE_DIR) / "latest_model.pkl"
    if not model_path.exists():
        print(f"❌ 模型不存在: {model_path}")
        print("   请先运行: python scripts/daily_signal.py --train")
        sys.exit(1)

    with open(model_path, 'rb') as f:
        return pickle.load(f)


def generate_signals(config: dict, model=None, dataset=None):
    """
    生成今日交易信号
    返回: [(stock_code, score, rank), ...] 按预测分数降序
    """
    qlib.init(**config["qlib_init"])

    if model is None:
        model = load_model()

    # 获取股票池最新数据
    instruments = config["dataset"]["kwargs"]["handler"]["kwargs"]["instruments"]

    # 使用今天作为预测日期（如果是非交易日会自动取最近交易日）
    today = get_today_str()

    print(f"\n📅 生成信号日期: {today}")
    print(f"📈 股票池: {instruments}")

    # 获取特征数据并预测
    if dataset is None:
        dataset = init_instance_by_config(config["dataset"])

    # 生成预测
    pred = model.predict(dataset)
    if pred is None or len(pred) == 0:
        print("❌ 预测结果为空，请检查数据和模型")
        return []

    # 取最新一天的预测结果
    if hasattr(pred, 'index'):
        # 如果是 Series/DataFrame
        latest_date = pred.index.get_level_values(0).max() if hasattr(pred.index, 'get_level_values') else pred.index.max()
        latest_pred = pred.loc[latest_date] if hasattr(pred, 'loc') else pred[pred.index == latest_date]
    else:
        latest_pred = pred

    # 排序，取 top-k
    topk = config["port_analysis_config"]["strategy"]["kwargs"]["topk"]
    n_drop = config["port_analysis_config"]["strategy"]["kwargs"]["n_drop"]

    # 转为 list 排序
    if hasattr(latest_pred, 'sort_values'):
        sorted_pred = latest_pred.sort_values(ascending=False)
        top_stocks = [(str(idx), float(val), rank+1)
                      for rank, (idx, val) in enumerate(sorted_pred.head(topk).items())]
        bottom_stocks = [(str(idx), float(val), len(sorted_pred) - rank)
                         for rank, (idx, val) in enumerate(sorted_pred.tail(n_drop).items())]
    else:
        # 如果是 ndarray 等
        import numpy as np
        if hasattr(latest_pred, 'values'):
            vals = latest_pred.values
            idxs = latest_pred.index
        else:
            vals = latest_pred
            idxs = list(range(len(vals)))

        ranked = sorted(zip(idxs, vals), key=lambda x: x[1], reverse=True)
        top_stocks = [(str(idx), float(val), rank+1)
                      for rank, (idx, val) in enumerate(ranked[:topk])]
        bottom_stocks = [(str(idx), float(val), len(ranked) - rank)
                         for rank, (idx, val) in enumerate(ranked[-n_drop:])]

    return top_stocks, bottom_stocks


def generate_trade_plan(config: dict, top_stocks, bottom_stocks, portfolio: dict) -> dict:
    """
    根据信号和当前持仓，生成具体的交易计划
    """
    topk = config["port_analysis_config"]["strategy"]["kwargs"]["topk"]
    total_capital = portfolio.get("cash", 100000) + sum(
        h.get("value", 0) for h in portfolio.get("holdings", [])
    )

    current_holdings = {h["code"]: h for h in portfolio.get("holdings", [])}
    target_codes = {s[0] for s in top_stocks}

    buys = []
    sells = []

    # 卖出：当前持仓中不在 target 里的，且在 bottom 中的
    bottom_codes = {s[0] for s in bottom_stocks}
    for code, holding in current_holdings.items():
        if code in bottom_codes:
            sells.append({
                "action": "SELL",
                "code": code,
                "reason": f"排名跌出，预测分数={dict(bottom_stocks).get(code, 'N/A')}",
            })

    # 买入：target 中当前未持仓的
    for code, score, rank in top_stocks:
        if code not in current_holdings:
            alloc = total_capital / topk
            buys.append({
                "action": "BUY",
                "code": code,
                "score": round(score, 6),
                "rank": rank,
                "suggest_amount": round(alloc, 0),
            })

    return {
        "date": get_today_str(),
        "total_capital": round(total_capital, 2),
        "current_holdings_count": len(current_holdings),
        "target_holdings_count": topk,
        "sells": sells,
        "buys": buys,
    }


def print_signal_report(top_stocks, bottom_stocks, trade_plan):
    """打印信号报告"""
    print("\n" + "=" * 60)
    print(f"📋 交易信号报告 - {get_today_str()}")
    print("=" * 60)

    print(f"\n🟢 买入信号 (Top {len(top_stocks)}):")
    print(f"{'排名':>4}  {'股票代码':<12}  {'预测分数':>12}")
    print("-" * 35)
    for code, score, rank in top_stocks[:10]:  # 只显示前10
        print(f"{rank:>4}  {code:<12}  {score:>12.6f}")
    if len(top_stocks) > 10:
        print(f"      ... 还有 {len(top_stocks) - 10} 只")

    print(f"\n🔴 卖出信号 (Bottom {len(bottom_stocks)}):")
    print(f"{'股票代码':<12}  {'预测分数':>12}")
    print("-" * 30)
    for code, score, _ in bottom_stocks:
        print(f"{code:<12}  {score:>12.6f}")

    # 交易计划
    print(f"\n📝 交易计划:")
    print(f"  总资金: ¥{trade_plan['total_capital']:,.0f}")
    print(f"  当前持仓: {trade_plan['current_holdings_count']} 只")
    print(f"  目标持仓: {trade_plan['target_holdings_count']} 只")

    if trade_plan["sells"]:
        print(f"\n  ⬇️ 需要卖出 ({len(trade_plan['sells'])} 只):")
        for s in trade_plan["sells"]:
            print(f"    SELL {s['code']}  ({s['reason']})")

    if trade_plan["buys"]:
        print(f"\n  ⬆️ 需要买入 ({len(trade_plan['buys'])} 只):")
        for b in trade_plan["buys"]:
            print(f"    BUY  {b['code']}  排名#{b['rank']}  建议金额:¥{b['suggest_amount']:,.0f}")

    if not trade_plan["sells"] and not trade_plan["buys"]:
        print("\n  ✅ 今日无需调仓，持仓与目标一致")

    print("\n" + "=" * 60)


def update_portfolio_after_trade(portfolio: dict, trade_plan: dict):
    """
    根据交易计划更新持仓（简化版，实际执行后手动确认）
    """
    # 移除卖出的
    sell_codes = {s["code"] for s in trade_plan["sells"]}
    portfolio["holdings"] = [
        h for h in portfolio["holdings"] if h["code"] not in sell_codes
    ]

    # 添加买入的
    for b in trade_plan["buys"]:
        portfolio["holdings"].append({
            "code": b["code"],
            "score": b["score"],
            "rank": b["rank"],
            "buy_date": get_today_str(),
            "amount": b["suggest_amount"],
            "value": b["suggest_amount"],
        })

    # 更新现金
    sell_amount = sum(b.get("suggest_amount", 0) for b in trade_plan["buys"])
    buy_amount = sum(s.get("suggest_amount", 0) for s in trade_plan["sells"])
    portfolio["cash"] = portfolio.get("cash", 100000) - sell_amount + buy_amount

    return portfolio


def main():
    parser = argparse.ArgumentParser(description="每日交易信号生成器")
    parser.add_argument("--config", default=CONFIG_PATH, help="配置文件路径")
    parser.add_argument("--portfolio", default=PORTFOLIO_FILE, help="持仓文件路径")
    parser.add_argument("--train", action="store_true", help="重新训练模型")
    parser.add_argument("--top", type=int, default=None, help="只显示前N只股票")
    parser.add_argument("--output", default=None, help="输出信号到文件")
    parser.add_argument("--hold-days", type=int, default=5,
                        help="调仓间隔（交易日），只有每N天才生成信号。设为1表示每天调仓")
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 是否需要训练
    if args.train:
        model, dataset = train_and_save(config)
    else:
        model = None
        dataset = None

    # 加载持仓
    portfolio = load_portfolio(args.portfolio)

    # 检查是否是调仓日
    if args.hold_days > 1:
        last_rebalance = portfolio.get("last_rebalance", "")
        today = get_today_str()

        if last_rebalance:
            from datetime import datetime as dt
            last_date = dt.strptime(last_rebalance, "%Y-%m-%d")
            today_date = dt.strptime(today, "%Y-%m-%d")
            elapsed_days = (today_date - last_date).days

            # 简单估算：大约1.4个交易日/自然日
            # A股一年约244个交易日，365自然日，比例≈0.67
            trading_days_est = int(elapsed_days * 0.67)

            if trading_days_est < args.hold_days and elapsed_days > 0:
                remaining = args.hold_days - trading_days_est
                print(f"⏸️  今天不是调仓日")
                print(f"   上次调仓: {last_rebalance}")
                print(f"   已过约 {trading_days_est} 个交易日（自然日 {elapsed_days} 天）")
                print(f"   距下次调仓还剩约 {remaining} 个交易日")
                print(f"   持仓保持不变，不生成新信号")
                print(f"\n   如需强制调仓：删除 portfolio.json 中的 last_rebalance 字段")
                return
            else:
                print(f"📅 今天是调仓日（距上次 {elapsed_days} 自然日，约 {trading_days_est} 个交易日）")
        else:
            print("📅 首次运行，今日作为调仓日")

    # 生成信号
    top_stocks, bottom_stocks = generate_signals(config, model, dataset)

    if not top_stocks:
        print("❌ 未能生成信号，请检查配置和数据")
        return

    # 生成交易计划
    trade_plan = generate_trade_plan(config, top_stocks, bottom_stocks, portfolio)

    # 打印报告
    print_signal_report(top_stocks, bottom_stocks, trade_plan)

    # 输出到文件
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump({
                "signals": {
                    "top": [(c, s, r) for c, s, r in top_stocks],
                    "bottom": [(c, s, r) for c, s, r in bottom_stocks],
                },
                "trade_plan": trade_plan,
            }, f, ensure_ascii=False, indent=2)
        print(f"\n📁 信号已保存到: {args.output}")

    # 询问是否更新持仓
    print(f"\n💾 持仓文件: {args.portfolio}")
    print(f"   调仓间隔: 每 {args.hold_days} 个交易日")
    print(f"   执行完交易后，更新 portfolio.json 并记录 last_rebalance 日期")

    # 自动记录调仓日期到 portfolio
    if trade_plan["sells"] or trade_plan["buys"]:
        portfolio["last_rebalance"] = get_today_str()
        save_portfolio(args.portfolio, portfolio)
        print(f"   ✅ 已自动记录调仓日期: {get_today_str()}")


if __name__ == "__main__":
    main()
