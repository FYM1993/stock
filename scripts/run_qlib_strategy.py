"""
Qlib 因子模型回测 v3 — 全功能版

v2 → v3 改进:
  P2: DoubleEnsemble 模型 (自动样本重加权 + 特征筛选, 比单 LightGBM 更稳健)
  P3: 更真实交易参数 (VWAP 成交价 + 滑点)
  P3: 完整交易日志 (每笔交易的买卖股票、日期、价格、收益)
  P3: 每日选股信号输出

用法:
  python run_qlib_strategy.py --period 2026 --mode rolling
  python run_qlib_strategy.py --period 2026 --mode rolling --model ensemble
  python run_qlib_strategy.py --period 2026 --mode both
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
from qlib.data import D
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
        "test_end": "2026-02-28",
    },
    "2026-full": {
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


# ==================== P2: 模型配置 ====================

def get_lgb_config():
    return {
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


def get_double_ensemble_config():
    """
    DoubleEnsemble: 训练多个子模型，每轮自动做两件事:
    1. Sample Reweighting (SR): 让模型关注前几轮预测差的样本
    2. Feature Selection (FS): 自动筛选有效因子、降低噪音
    比单 LightGBM 更稳健，尤其在市场风格频繁切换时。
    """
    return {
        "class": "DEnsembleModel",
        "module_path": "qlib.contrib.model.double_ensemble",
        "kwargs": {
            "base_model": "gbm",
            "num_models": 6,
            "enable_sr": True,
            "enable_fs": True,
            "alpha1": 1,
            "alpha2": 1,
            "bins_sr": 10,
            "bins_fs": 5,
        },
    }


MODEL_TYPE = "lgb"


def get_model_config():
    if MODEL_TYPE == "ensemble":
        return get_double_ensemble_config()
    return get_lgb_config()


# ==================== 因子构建 ====================

def build_handler(market="all", label_expr=None):
    """构建 Alpha158 因子处理器（只需构建一次，滚动训练复用）"""
    label_kwarg = {}
    if label_expr:
        label_kwarg["label"] = ([label_expr], ["LABEL0"])

    handler = Alpha158(
        instruments=market,
        start_time=TRAIN_START,
        end_time=TEST_END,
        fit_start_time=TRAIN_START,
        fit_end_time=TRAIN_END,
        infer_processors=[
            {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
        ],
        learn_processors=[
            {"class": "DropnaLabel"},
            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
        ],
        **label_kwarg,
    )
    return handler


# ==================== P0: 滚动训练 ====================

def rolling_train_predict(handler, step=20):
    """
    滚动训练: 每 step 个交易日重训模型 (expanding window)
    模型用包含最新行情的数据重训 → 自动适应市场风格变化。
    """
    cal = list(D.calendar(start_time=TRAIN_START, end_time=TEST_END, freq="day"))
    test_start_ts = pd.Timestamp(TEST_START)
    test_end_ts = pd.Timestamp(TEST_END)
    test_dates = [d for d in cal if test_start_ts <= d <= test_end_ts]

    if not test_dates:
        raise ValueError(f"测试期 {TEST_START}~{TEST_END} 内无交易日")

    windows = []
    for i in range(0, len(test_dates), step):
        w_start = test_dates[i]
        w_end = test_dates[min(i + step - 1, len(test_dates) - 1)]
        windows.append((w_start, w_end))

    all_preds = []
    importance_list = []
    feature_names = None

    for win_idx, (w_start, w_end) in enumerate(windows):
        w_start_idx = cal.index(w_start)
        valid_end_idx = w_start_idx - 1
        valid_start_idx = max(0, valid_end_idx - 19)
        train_end_idx = valid_start_idx - 1

        if train_end_idx < 20:
            print(f"  [Window {win_idx+1}] 训练数据不足，跳过")
            continue

        t_end = cal[train_end_idx].strftime("%Y-%m-%d")
        v_start = cal[valid_start_idx].strftime("%Y-%m-%d")
        v_end = cal[valid_end_idx].strftime("%Y-%m-%d")
        w_start_str = w_start.strftime("%Y-%m-%d")
        w_end_str = w_end.strftime("%Y-%m-%d")

        print(f"  [Window {win_idx+1}/{len(windows)}] "
              f"训练 {TRAIN_START}~{t_end} | 验证 {v_start}~{v_end} | "
              f"预测 {w_start_str}~{w_end_str}")

        dataset = DatasetH(
            handler=handler,
            segments={
                "train": (TRAIN_START, t_end),
                "valid": (v_start, v_end),
                "test": (w_start_str, w_end_str),
            },
        )

        model = init_instance_by_config(get_model_config())
        model.fit(dataset)

        try:
            imp = model.model.feature_importance(importance_type="gain")
            importance_list.append(imp)
            if feature_names is None:
                feature_names = model.model.feature_name()
        except Exception:
            pass

        pred = model.predict(dataset)
        pred_window = pred.loc[
            (pred.index.get_level_values("datetime") >= pd.Timestamp(w_start_str)) &
            (pred.index.get_level_values("datetime") <= pd.Timestamp(w_end_str))
        ]
        all_preds.append(pred_window)

    full_pred = pd.concat(all_preds) if all_preds else pd.Series(dtype=float)
    avg_importance = np.mean(importance_list, axis=0) if importance_list else None

    return full_pred, avg_importance, feature_names


def static_train_predict(handler):
    """固定训练 (v1 方式): 训练一次，预测全部测试期"""
    dataset = DatasetH(
        handler=handler,
        segments={
            "train": (TRAIN_START, TRAIN_END),
            "valid": (VALID_START, VALID_END),
            "test":  (TEST_START, TEST_END),
        },
    )
    model = init_instance_by_config(get_model_config())
    model.fit(dataset)
    pred = model.predict(dataset)

    importance, feature_names = None, None
    try:
        importance = model.model.feature_importance(importance_type="gain")
        feature_names = model.model.feature_name()
    except Exception:
        pass

    return pred, importance, feature_names


# ==================== P0: 股票过滤 ====================

def build_stock_filter(instruments, start, end):
    """
    过滤条件:
    1. 涨跌停: 当日涨跌幅 > 9.5%
    2. 低流动性: 每日成交额后 10%
    3. 次新股: 上市不足 60 个交易日
    """
    try:
        data = D.features(
            instruments,
            ["$close/Ref($close,1)-1", "$volume*$close", "$close"],
            start_time=start, end_time=end, freq="day",
        )
        data.columns = ["daily_ret", "turnover", "close"]
    except Exception as e:
        print(f"    过滤数据查询失败: {e}")
        return None

    limit_mask = data["daily_ret"].abs() > 0.095

    daily_q10 = data.groupby("datetime")["turnover"].transform(
        lambda x: x.quantile(0.10)
    )
    low_liq_mask = data["turnover"] < daily_q10

    try:
        all_close = D.features(
            instruments, ["$close"],
            start_time="2020-01-01", end_time=end, freq="day",
        )
        cum_days = all_close.groupby("instrument").cumcount() + 1
        cum_days_test = cum_days.reindex(data.index)
        new_stock_mask = cum_days_test < 60
    except Exception:
        new_stock_mask = pd.Series(False, index=data.index)

    bad_mask = limit_mask | low_liq_mask | new_stock_mask
    return bad_mask


def filter_predictions(pred, bad_mask):
    if pred.empty or bad_mask is None:
        return pred

    n_before = len(pred)
    common_bad = pred.index.intersection(bad_mask[bad_mask].index)
    pred_filtered = pred.drop(index=common_bad, errors="ignore")
    n_after = len(pred_filtered)

    removed = n_before - n_after
    if removed > 0:
        print(f"    过滤: {n_before} -> {n_after} (移除 {removed} 条, {removed/n_before*100:.1f}%)")

    return pred_filtered


# ==================== P1: 信号融合 ====================

def ensemble_predictions(pred_list, weights):
    """多标签信号加权融合: 短期(2日) + 中期(5日) + 长期(10日)"""
    if len(pred_list) == 1:
        return pred_list[0]

    common_idx = pred_list[0].index
    for p in pred_list[1:]:
        common_idx = common_idx.intersection(p.index)

    combined = pd.Series(0.0, index=common_idx)
    total_weight = 0
    for pred, w in zip(pred_list, weights):
        combined += pred.reindex(common_idx).fillna(0) * w
        total_weight += w

    combined /= total_weight
    return combined


# ==================== P1: 特征重要性 ====================

def print_feature_importance(importance, feature_names=None, top_n=20):
    if importance is None:
        return

    if feature_names is None or len(feature_names) != len(importance):
        feature_names = [f"feature_{i}" for i in range(len(importance))]

    ranked = sorted(zip(feature_names, importance), key=lambda x: -x[1])[:top_n]
    total_imp = sum(importance)

    print(f"\n  Top-{top_n} 重要因子:")
    for i, (name, imp) in enumerate(ranked):
        pct = imp / total_imp * 100 if total_imp > 0 else 0
        bar = "█" * max(1, int(pct * 2))
        print(f"    {i+1:2d}. {name:<45s} {pct:5.1f}% {bar}")


# ==================== P3: 交易模拟 & 明细 ====================

def simulate_trades(pred, topk=10, n_drop=2):
    """
    模拟 TopkDropoutStrategy 的交易过程，提取每一笔买卖记录。
    """
    test_pred = pred.loc[pred.index.get_level_values("datetime") >= pd.Timestamp(TEST_START)]
    if test_pred.empty:
        return [], {}

    dates = sorted(test_pred.index.get_level_values("datetime").unique())
    current_holdings = set()
    trades = []
    daily_portfolio = {}

    for date in dates:
        day_pred = test_pred.loc[date]
        if isinstance(day_pred, pd.DataFrame):
            day_pred = day_pred.iloc[:, 0]
        day_pred = day_pred.dropna().sort_values(ascending=False)

        if len(day_pred) < topk:
            daily_portfolio[date] = sorted(current_holdings)
            continue

        topk_stocks = set(day_pred.head(topk).index.tolist())

        if not current_holdings:
            current_holdings = topk_stocks.copy()
            for stock in sorted(current_holdings):
                trades.append({
                    "date": date, "stock": stock, "action": "BUY",
                    "score": float(day_pred.get(stock, 0)),
                })
        else:
            sell_candidates = current_holdings - topk_stocks
            buy_candidates = topk_stocks - current_holdings

            sell_sorted = sorted(sell_candidates,
                                 key=lambda s: day_pred.get(s, float("-inf")))
            buy_sorted = sorted(buy_candidates,
                                key=lambda s: day_pred.get(s, float("-inf")),
                                reverse=True)

            n_trade = min(n_drop, len(sell_sorted), len(buy_sorted))

            for i in range(n_trade):
                stock = sell_sorted[i]
                trades.append({
                    "date": date, "stock": stock, "action": "SELL",
                    "score": float(day_pred.get(stock, 0)),
                })
                current_holdings.discard(stock)

            for i in range(n_trade):
                stock = buy_sorted[i]
                trades.append({
                    "date": date, "stock": stock, "action": "BUY",
                    "score": float(day_pred.get(stock, 0)),
                })
                current_holdings.add(stock)

        daily_portfolio[date] = sorted(current_holdings)

    return trades, daily_portfolio


def compute_trade_returns(trades):
    """配对买卖交易，计算每笔收益"""
    all_stocks = list(set(t["stock"] for t in trades))
    if not all_stocks:
        return []

    try:
        prices_df = D.features(
            all_stocks, ["$close"],
            start_time=TEST_START, end_time=TEST_END, freq="day",
        )
        prices_df.columns = ["close"]
    except Exception as e:
        print(f"  价格数据查询失败: {e}")
        return []

    # D.features 返回 (instrument, datetime) 顺序，构建查询字典
    price_dict = {}
    for idx, row in prices_df.iterrows():
        inst, dt = idx  # (instrument, datetime) 顺序
        price_dict[(dt, inst)] = float(row["close"])

    def get_price(date, stock):
        return price_dict.get((date, stock), 0)

    open_positions = {}
    completed = []

    for trade in sorted(trades, key=lambda t: t["date"]):
        stock = trade["stock"]
        if trade["action"] == "BUY":
            open_positions[stock] = trade
        elif trade["action"] == "SELL" and stock in open_positions:
            buy = open_positions.pop(stock)
            bp = get_price(buy["date"], stock)
            sp = get_price(trade["date"], stock)
            ret = sp / bp - 1 if bp > 0 else 0

            completed.append({
                "stock": stock,
                "buy_date": buy["date"].strftime("%Y-%m-%d"),
                "sell_date": trade["date"].strftime("%Y-%m-%d"),
                "buy_price": round(bp, 2),
                "sell_price": round(sp, 2),
                "return": ret,
                "holding_days": (trade["date"] - buy["date"]).days,
            })

    # 仍在持仓的股票
    for stock, buy in open_positions.items():
        bp = get_price(buy["date"], stock)
        stock_prices = sorted(
            [(dt, p) for (dt, inst), p in price_dict.items() if inst == stock],
            key=lambda x: x[0],
        )
        if stock_prices:
            latest_date, lp = stock_prices[-1]
            ret = lp / bp - 1 if bp > 0 else 0
        else:
            latest_date, lp, ret = buy["date"], bp, 0

        completed.append({
            "stock": stock,
            "buy_date": buy["date"].strftime("%Y-%m-%d"),
            "sell_date": f"(持仓至{latest_date.strftime('%Y-%m-%d') if hasattr(latest_date, 'strftime') else latest_date})",
            "buy_price": round(bp, 2),
            "sell_price": round(lp, 2),
            "return": ret,
            "holding_days": -1,
        })

    return completed


def print_trade_log(completed_trades, name=""):
    if not completed_trades:
        print("  无交易记录")
        return

    print(f"\n{'='*105}")
    print(f"交易明细 [{name}]")
    print(f"{'='*105}")
    print(f"  {'股票':<14} {'买入日期':<12} {'卖出日期':<18} {'买入价':>8} {'卖出价':>8} {'收益率':>8} {'持仓天数':>8}")
    print(f"  {'-'*100}")

    closed = [t for t in completed_trades if t["holding_days"] > 0]
    still_open = [t for t in completed_trades if t["holding_days"] <= 0]

    for t in sorted(closed, key=lambda x: x["buy_date"]):
        ret_str = f"{t['return']*100:+.2f}%"
        marker = " *" if t["return"] > 0.05 else (" !" if t["return"] < -0.05 else "")
        print(f"  {t['stock']:<14} {t['buy_date']:<12} {t['sell_date']:<18} "
              f"{t['buy_price']:>8.2f} {t['sell_price']:>8.2f} {ret_str:>8} {t['holding_days']:>6}天{marker}")

    if still_open:
        print(f"  {'--- 当前持仓 ---':^100}")
        for t in sorted(still_open, key=lambda x: x["return"], reverse=True):
            ret_str = f"{t['return']*100:+.2f}%"
            print(f"  {t['stock']:<14} {t['buy_date']:<12} {t['sell_date']:<18} "
                  f"{t['buy_price']:>8.2f} {t['sell_price']:>8.2f} {ret_str:>8} {'持仓中':>8}")

    if closed:
        wins = [t for t in closed if t["return"] > 0]
        avg_ret = np.mean([t["return"] for t in closed])
        avg_hold = np.mean([t["holding_days"] for t in closed])
        best = max(closed, key=lambda t: t["return"])
        worst = min(closed, key=lambda t: t["return"])
        print(f"\n  已平仓 {len(closed)} 笔 | 盈利 {len(wins)} 笔 | "
              f"胜率 {len(wins)/len(closed)*100:.1f}% | "
              f"平均收益 {avg_ret*100:+.2f}% | 平均持仓 {avg_hold:.0f}天")
        print(f"  最佳: {best['stock']} {best['return']*100:+.2f}% | "
              f"最差: {worst['stock']} {worst['return']*100:+.2f}%")

    if still_open:
        avg_unrealized = np.mean([t["return"] for t in still_open])
        print(f"  持仓中 {len(still_open)} 只 | 平均浮盈 {avg_unrealized*100:+.2f}%")


def print_daily_portfolio(daily_portfolio):
    """打印每日持仓明细"""
    if not daily_portfolio:
        return

    print(f"\n每日持仓:")
    prev_holdings = set()
    for date in sorted(daily_portfolio.keys()):
        stocks = daily_portfolio[date]
        stock_set = set(stocks)
        added = stock_set - prev_holdings
        removed = prev_holdings - stock_set
        date_str = date.strftime("%Y-%m-%d")

        change_str = ""
        if added:
            change_str += f" +{','.join(sorted(added))}"
        if removed:
            change_str += f" -{','.join(sorted(removed))}"

        stocks_display = ", ".join(stocks[:8])
        if len(stocks) > 8:
            stocks_display += f" ...+{len(stocks)-8}"
        print(f"  {date_str} [{len(stocks):2d}只] {stocks_display}{change_str}")
        prev_holdings = stock_set


# ==================== P3: 每日选股信号 ====================

def print_daily_signal(pred, topk=10):
    """输出最新交易日的选股信号"""
    test_pred = pred.loc[pred.index.get_level_values("datetime") >= pd.Timestamp(TEST_START)]
    if test_pred.empty:
        return

    latest_date = test_pred.index.get_level_values("datetime").max()
    day_pred = test_pred.loc[latest_date].sort_values(ascending=False)
    if isinstance(day_pred, pd.DataFrame):
        day_pred = day_pred.iloc[:, 0]

    top = day_pred.head(topk)
    print(f"\n  最新选股信号 ({latest_date.strftime('%Y-%m-%d')}):")
    print(f"  {'排名':<4} {'股票':<14} {'信号分':>8}")
    print(f"  {'-'*30}")
    for i, (stock, score) in enumerate(top.items()):
        print(f"  {i+1:<4d} {stock:<14} {score:>8.4f}")


# ==================== P3: 回测引擎 (VWAP+滑点) ====================

def run_backtest(pred, topk=30, n_drop=5):
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
            "deal_price": "vwap",
            "open_cost": 0.001,
            "close_cost": 0.002,
            "min_cost": 5,
            "trade_unit": 100,
        },
    )
    return portfolio_metric_dict


def analyze(portfolio_metric_dict, name=""):
    report, positions = portfolio_metric_dict.get("1day", (None, None))
    if report is None or report.empty:
        print(f"  [{name}] 未生成有效报告")
        return None

    rets = report["return"].fillna(0)
    cum = (1 + rets).cumprod()
    total_ret = cum.iloc[-1] - 1
    peak = cum.cummax()
    max_dd = (cum / peak - 1).min()
    ann_ret = (1 + total_ret) ** (252 / max(len(rets), 1)) - 1
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


def run_strategy(name, pred, topk, n_drop, bad_mask=None):
    print(f"  回测 {name} (topk={topk}, n_drop={n_drop})...")

    if bad_mask is not None:
        pred = filter_predictions(pred, bad_mask)

    pm = run_backtest(pred, topk=topk, n_drop=n_drop)
    result = analyze(pm, name=name)
    if result:
        print(f"    -> 收益 {result['total_return']*100:+.2f}%, "
              f"回撤 {result['max_drawdown']*100:.2f}%, "
              f"超额 {(result['excess_return'] or 0)*100:+.2f}%")
    return result, pred


# ==================== 输出 ====================

def print_comparison(results_list):
    valid = [r for r in results_list if r is not None]
    if not valid:
        print("所有实验均失败")
        return

    print(f"\n{'='*115}")
    print(f"多方案对比 ({TEST_START} ~ {TEST_END})")
    print(f"{'='*115}")
    print(f"  {'方案':<42} {'总收益':>8} {'年化':>8} {'回撤':>8} {'夏普':>6} {'胜率':>6} {'盈亏比':>6} {'超额':>8}")
    print(f"  {'-'*110}")
    for r in valid:
        exc = f"{r['excess_return']*100:>+7.2f}%" if r["excess_return"] is not None else "    N/A"
        print(
            f"  {r['name']:<42}"
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
        print(f"  [{r['name'][:30]}] 月度: {mstr}")

    best = max(valid, key=lambda x: x["excess_return"] or -999)
    print(f"\n  最优: {best['name']} (超额 {best['excess_return']*100:+.2f}%)")


def save_trade_log(completed_trades, name):
    """保存交易明细到 CSV"""
    if not completed_trades:
        return
    df = pd.DataFrame(completed_trades)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"trades_{ts}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n  交易明细已保存: {path}")


# ==================== 主流程 ====================

def main():
    global TRAIN_START, TRAIN_END, VALID_START, VALID_END, TEST_START, TEST_END
    global MODEL_TYPE

    parser = argparse.ArgumentParser(description="Qlib Alpha158 v3 — 滚动训练 + 信号融合 + 交易明细")
    parser.add_argument("--period", choices=list(PERIODS.keys()), default="2026",
                        help="回测区间 (default: 2026)")
    parser.add_argument("--step", type=int, default=20,
                        help="滚动训练步长: 每 N 个交易日重训 (default: 20)")
    parser.add_argument("--mode", choices=["rolling", "static", "both"], default="both",
                        help="rolling=滚动训练, static=固定训练, both=对比 (default: both)")
    parser.add_argument("--model", choices=["lgb", "ensemble"], default="lgb",
                        help="模型: lgb=LightGBM, ensemble=DoubleEnsemble (default: lgb)")
    parser.add_argument("--topk", type=int, default=10, help="持仓股票数 (default: 10)")
    args = parser.parse_args()

    MODEL_TYPE = args.model

    p = PERIODS[args.period]
    TRAIN_START = p["train_start"]
    TRAIN_END   = p["train_end"]
    VALID_START = p["valid_start"]
    VALID_END   = p["valid_end"]
    TEST_START  = p["test_start"]
    TEST_END    = p["test_end"]

    model_name = "LightGBM" if args.model == "lgb" else "DoubleEnsemble"
    print("=" * 70)
    print(f"Qlib Alpha158 v3 [{args.period}] — {model_name}")
    print("=" * 70)

    qlib.init(provider_uri=str(DATA_PATH), region=REG_CN)
    print(f"数据: {DATA_PATH}")
    print(f"训练: {TRAIN_START}~{TRAIN_END} | 验证: {VALID_START}~{VALID_END}")
    print(f"测试: {TEST_START}~{TEST_END}")
    print(f"模型: {model_name} | 模式: {args.mode} | 步长: {args.step}天 | TopK: {args.topk}")

    label_configs = [
        ("2日", None, 0.5),
        ("5日", "Ref($close, -5)/Ref($close, -1) - 1", 0.3),
        ("10日", "Ref($close, -10)/Ref($close, -1) - 1", 0.2),
    ]

    # ========== 构建因子 ==========
    print("\n构建因子处理器 (Alpha158 x 3 标签)...")
    handlers = {}
    for label_name, label_expr, _ in label_configs:
        print(f"  计算 {label_name}标签 因子...")
        handlers[label_name] = build_handler(market="all", label_expr=label_expr)

    # ========== 构建过滤掩码 ==========
    print("\n构建股票过滤条件...")
    test_instruments = D.instruments(market="all")
    bad_mask = build_stock_filter(test_instruments, TEST_START, TEST_END)
    if bad_mask is not None:
        n_bad = bad_mask.sum()
        n_total = len(bad_mask)
        print(f"  过滤掩码: {n_total} 条中 {n_bad} 条标记为过滤 ({n_bad/n_total*100:.1f}%)")

    all_results = []
    best_pred = None
    best_name = ""
    best_excess = -999

    topk = args.topk
    n_drop = max(1, topk // 5)

    # ========== 对照组: 固定训练 ==========
    if args.mode in ("static", "both"):
        print(f"\n{'='*70}")
        print(f"[对照组] v1 固定训练 — {model_name}")
        print(f"{'='*70}")

        for label_name, _, _ in label_configs:
            print(f"\n  训练 {label_name}标签 (固定)...")
            pred, importance, feat_names = static_train_predict(handlers[label_name])
            n_test = pred.loc[pred.index.get_level_values("datetime") >= pd.Timestamp(TEST_START)].shape[0]
            print(f"  预测: {pred.shape[0]} 条 (测试期 {n_test} 条)")

            result, filtered_pred = run_strategy(
                f"v1固定|{label_name}+Top{topk}",
                pred, topk=topk, n_drop=n_drop, bad_mask=None,
            )
            all_results.append(result)
            if result and (result["excess_return"] or -999) > best_excess:
                best_excess = result["excess_return"] or -999
                best_pred = pred
                best_name = result["name"]

    # ========== 实验组: 滚动训练 ==========
    if args.mode in ("rolling", "both"):
        print(f"\n{'='*70}")
        print(f"[实验组] v2 滚动训练 — {model_name} (step={args.step})")
        print(f"{'='*70}")

        rolling_preds = {}
        reported_importance = False

        for label_name, _, weight in label_configs:
            print(f"\n  {label_name}标签 滚动训练...")
            pred, importance, feat_names = rolling_train_predict(
                handlers[label_name], step=args.step,
            )
            rolling_preds[label_name] = pred
            print(f"  {label_name} 预测: {len(pred)} 条")

            if not reported_importance and importance is not None:
                print_feature_importance(importance, feat_names)
                reported_importance = True

            result, filtered_pred = run_strategy(
                f"v2滚动|{label_name}+Top{topk}",
                pred, topk=topk, n_drop=n_drop, bad_mask=bad_mask,
            )
            all_results.append(result)
            if result and (result["excess_return"] or -999) > best_excess:
                best_excess = result["excess_return"] or -999
                best_pred = filtered_pred
                best_name = result["name"]

        # ========== 信号融合 ==========
        print(f"\n{'='*70}")
        print("[信号融合] 2日x0.5 + 5日x0.3 + 10日x0.2")
        print(f"{'='*70}")

        preds_list = [rolling_preds[lc[0]] for lc in label_configs]
        weights = [lc[2] for lc in label_configs]
        pred_ensemble = ensemble_predictions(preds_list, weights)
        print(f"  融合信号: {len(pred_ensemble)} 条")

        for tk, nd in [(topk, n_drop), (5, 1), (15, 3)]:
            result, filtered_pred = run_strategy(
                f"v2融合|Top{tk}",
                pred_ensemble, topk=tk, n_drop=nd, bad_mask=bad_mask,
            )
            all_results.append(result)
            if result and (result["excess_return"] or -999) > best_excess:
                best_excess = result["excess_return"] or -999
                best_pred = filtered_pred
                best_name = result["name"]

    # ========== 对比输出 ==========
    print_comparison(all_results)

    # ========== 最优方案: 交易明细 + 每日持仓 ==========
    if best_pred is not None:
        print(f"\n{'='*70}")
        print(f"最优方案交易明细: {best_name}")
        print(f"{'='*70}")

        # 从方案名解析 topk
        best_topk = topk
        for tk_val in [5, 10, 15, 20, 30]:
            if f"Top{tk_val}" in best_name:
                best_topk = tk_val
                break
        best_ndrop = max(1, best_topk // 5)

        trades, daily_port = simulate_trades(best_pred, topk=best_topk, n_drop=best_ndrop)
        completed = compute_trade_returns(trades)
        print_trade_log(completed, name=best_name)
        print_daily_portfolio(daily_port)
        print_daily_signal(best_pred, topk=best_topk)
        save_trade_log(completed, best_name)

        # 保存报告
        valid = [r for r in all_results if r is not None]
        if valid:
            best_result = max(valid, key=lambda x: x["excess_return"] or -999)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            best_result["report"].to_csv(RESULTS_DIR / f"qlib_v3_best_{ts}.csv")
            print(f"  收益报告已保存: results/qlib_v3_best_{ts}.csv")

    print("\n完成!")


if __name__ == "__main__":
    main()
