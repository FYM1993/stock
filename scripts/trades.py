"""
交易模块 — 交易模拟与收益计算
含涨跌停校验、交易成本
"""
import pandas as pd
import numpy as np
from qlib.data import D

import config
import strategy

OPEN_COST = 0.0010
CLOSE_COST = 0.0020
LIMIT_THRESHOLD = 0.095


def _build_limit_mask(all_stocks: list, test_start: str, test_end: str) -> dict:
    """构建 (date, stock) -> (is_limit_up, is_limit_down)"""
    limit_dict = {}
    if not all_stocks:
        return limit_dict
    try:
        data = D.features(
            all_stocks,
            ["$close/Ref($close,1)-1"],
            start_time=test_start,
            end_time=test_end,
            freq="day",
        )
        data.columns = ["ret"]
        for idx, row in data.iterrows():
            inst = idx[0] if idx[0] in all_stocks else idx[1]
            dt = idx[1] if idx[0] in all_stocks else idx[0]
            if isinstance(dt, pd.Timestamp):
                ret = float(row["ret"]) if pd.notna(row["ret"]) else 0
                limit_dict[(dt, inst)] = (ret > LIMIT_THRESHOLD, ret < -LIMIT_THRESHOLD)
    except Exception:
        pass
    return limit_dict


def simulate_trades(pred, test_start: str, topk: int = 10, n_drop: int = 2) -> tuple:
    """模拟 TopkDropoutStrategy 交易过程，返回 (trades, daily_portfolio)"""
    test_pred = pred.loc[pred.index.get_level_values("datetime") >= pd.Timestamp(test_start)]
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

        def _get_score(stock, default=0.0):
            v = day_pred.get(stock, default)
            return float(v.iloc[0]) if isinstance(v, pd.Series) else float(v)

        if len(day_pred) < topk:
            daily_portfolio[date] = sorted(current_holdings)
            continue

        topk_stocks = set(day_pred.head(topk).index.tolist())

        if not current_holdings:
            current_holdings = topk_stocks.copy()
            for stock in sorted(current_holdings):
                trades.append({"date": date, "stock": stock, "action": "BUY", "score": _get_score(stock)})
        else:
            sell_candidates = current_holdings - topk_stocks
            buy_candidates = topk_stocks - current_holdings
            sell_sorted = sorted(sell_candidates, key=lambda s: _get_score(s, float("-inf")))
            buy_sorted = sorted(buy_candidates, key=lambda s: _get_score(s, float("-inf")), reverse=True)
            n_trade = min(n_drop, len(sell_sorted), len(buy_sorted))
            for i in range(n_trade):
                stock = sell_sorted[i]
                trades.append({"date": date, "stock": stock, "action": "SELL", "score": _get_score(stock)})
                current_holdings.discard(stock)
            for i in range(n_trade):
                stock = buy_sorted[i]
                trades.append({"date": date, "stock": stock, "action": "BUY", "score": _get_score(stock)})
                current_holdings.add(stock)

        daily_portfolio[date] = sorted(current_holdings)

    return trades, daily_portfolio


def compute_trade_returns(
    trades: list,
    test_start: str,
    test_end: str,
    price_dict_override: dict = None,
) -> list:
    """
    配对买卖，计算每笔收益。信号 T 日 → 执行 T+1 日。
    price_dict_override: 可选，{(exec_date, stock): price} 用于使用预测 VWAP 等自定义价格
    """
    all_stocks = list(set(t["stock"] for t in trades))
    if not all_stocks:
        return []

    cal_sorted = sorted(D.calendar(start_time=test_start, end_time=test_end, freq="day"))
    date_to_idx = {d: i for i, d in enumerate(cal_sorted)}

    def exec_date(signal_date):
        idx = date_to_idx.get(signal_date)
        if idx is not None and idx + 1 < len(cal_sorted):
            return cal_sorted[idx + 1]
        return signal_date

    price_dict = {}
    if price_dict_override:
        for k, p in price_dict_override.items():
            price_dict[k] = float(p)
        try:
            close_df = D.features(
                all_stocks, ["$close"],
                start_time=test_start, end_time=test_end, freq="day",
            )
            close_df.columns = ["close"]
            for idx, row in close_df.iterrows():
                inst = idx[0] if idx[0] in all_stocks else idx[1]
                dt = idx[1] if idx[0] in all_stocks else idx[0]
                if isinstance(dt, pd.Timestamp):
                    k = (dt, inst)
                    if k not in price_dict:
                        price_dict[k] = float(row["close"])
        except Exception:
            pass
    else:
        use_vwap = strategy.has_vwap_data()
        try:
            if use_vwap:
                prices_df = D.features(
                    all_stocks, ["$vwap", "$close"],
                    start_time=test_start, end_time=test_end, freq="day",
                )
                prices_df.columns = ["vwap", "close"]
                prices_df["price"] = prices_df["vwap"].fillna(prices_df["close"])
            else:
                prices_df = D.features(
                    all_stocks, ["$close"],
                    start_time=test_start, end_time=test_end, freq="day",
                )
                prices_df.columns = ["price"]
            for idx, row in prices_df.iterrows():
                inst, dt = idx[0], idx[1]
                price_dict[(dt, inst)] = float(row["price"])
        except Exception as e:
            print(f"  价格数据查询失败: {e}")
            return []

    limit_mask = _build_limit_mask(all_stocks, test_start, test_end)

    def get_price(date, stock):
        return price_dict.get((date, stock), 0)

    def get_exec_price(date, stock, is_buy: bool):
        """涨跌停校验：涨停买不到用 close，跌停卖不出用 close（限价）"""
        p = get_price(date, stock)
        lim = limit_mask.get((date, stock), (False, False))
        is_limit_up, is_limit_down = lim
        if is_buy and is_limit_up:
            return p  # 涨停买不到，用 close 表示无法成交；调用方会 skip
        if not is_buy and is_limit_down:
            return p  # 跌停卖不出，用 close（跌停价）保守估计
        return p

    open_positions = {}
    completed = []

    for trade in sorted(trades, key=lambda t: t["date"]):
        stock = trade["stock"]
        if trade["action"] == "BUY":
            open_positions[stock] = trade
        elif trade["action"] == "SELL" and stock in open_positions:
            buy = open_positions.pop(stock)
            buy_exec = exec_date(buy["date"])
            sell_exec = exec_date(trade["date"])
            bp = get_exec_price(buy_exec, stock, True) or get_exec_price(buy["date"], stock, True)
            sp = get_exec_price(sell_exec, stock, False) or get_exec_price(trade["date"], stock, False)
            ret = sp / bp - 1 if bp > 0 else 0
            # 交易成本：买入 0.1%，卖出 0.2%
            ret_net = ret - OPEN_COST - CLOSE_COST
            completed.append({
                "stock": stock,
                "buy_date": buy_exec.strftime("%Y-%m-%d"),
                "sell_date": sell_exec.strftime("%Y-%m-%d"),
                "buy_price": round(bp, 2),
                "sell_price": round(sp, 2),
                "return": ret_net,
                "holding_days": (sell_exec - buy_exec).days,
            })

    for stock, buy in open_positions.items():
        buy_exec = exec_date(buy["date"])
        bp = get_price(buy_exec, stock) or get_price(buy["date"], stock)
        stock_prices = sorted(
            [(dt, p) for (dt, inst), p in price_dict.items() if inst == stock],
            key=lambda x: x[0],
        )
        if stock_prices:
            latest_date, lp = stock_prices[-1]
            ret = (lp / bp - 1 - OPEN_COST) if bp > 0 else 0  # 已付买入成本，未卖出
        else:
            latest_date, lp, ret = buy_exec, bp, 0
        completed.append({
            "stock": stock,
            "buy_date": buy_exec.strftime("%Y-%m-%d"),
            "sell_date": f"(持仓至{latest_date.strftime('%Y-%m-%d')})",
            "buy_price": round(bp, 2),
            "sell_price": round(lp, 2),
            "return": ret,
            "holding_days": -1,
        })

    return completed


def print_trade_log(completed_trades: list, name: str = ""):
    """打印交易明细"""
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
            print(f"  {t['stock']:<14} {t['buy_date']:<12} {t['sell_date']:<18} "
                  f"{t['buy_price']:>8.2f} {t['sell_price']:>8.2f} {t['return']*100:+.2f}%   {'持仓中':>8}")

    if closed:
        wins = [t for t in closed if t["return"] > 0]
        avg_ret = np.mean([t["return"] for t in closed])
        avg_hold = np.mean([t["holding_days"] for t in closed])
        best = max(closed, key=lambda t: t["return"])
        worst = min(closed, key=lambda t: t["return"])
        print(f"\n  已平仓 {len(closed)} 笔 | 盈利 {len(wins)} 笔 | 胜率 {len(wins)/len(closed)*100:.1f}% | "
              f"平均收益 {avg_ret*100:+.2f}% | 平均持仓 {avg_hold:.0f}天")
        print(f"  最佳: {best['stock']} {best['return']*100:+.2f}% | 最差: {worst['stock']} {worst['return']*100:+.2f}%")


def print_daily_portfolio(daily_portfolio: dict):
    """打印每日持仓"""
    if not daily_portfolio:
        return
    prev_holdings = set()
    for date in sorted(daily_portfolio.keys()):
        stocks = daily_portfolio[date]
        stock_set = set(stocks)
        added = stock_set - prev_holdings
        removed = prev_holdings - stock_set
        change_str = ""
        if added:
            change_str += f" +{','.join(sorted(added))}"
        if removed:
            change_str += f" -{','.join(sorted(removed))}"
        stocks_display = ", ".join(stocks[:8])
        if len(stocks) > 8:
            stocks_display += f" ...+{len(stocks)-8}"
        print(f"  {date.strftime('%Y-%m-%d')} [{len(stocks):2d}只] {stocks_display}{change_str}")
        prev_holdings = stock_set
