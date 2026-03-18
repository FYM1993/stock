"""
策略模块 — 信号融合、回测、收益分析
单一职责: 多标签融合、Qlib 回测、策略评估
"""
import pandas as pd
import numpy as np
from qlib.backtest import backtest as qlib_backtest
from qlib.backtest import executor as qlib_executor
from qlib.data import D
from qlib.utils import init_instance_by_config

import config


def ensemble_predictions(pred_list: list, weights: list) -> pd.Series:
    """多标签信号加权融合"""
    if len(pred_list) == 1:
        return pred_list[0]

    def _dedupe(s: pd.Series) -> pd.Series:
        if s.index.duplicated().any():
            return s.groupby(level=list(range(s.index.nlevels))).last()
        return s

    preds_deduped = [_dedupe(p) for p in pred_list]
    common_idx = preds_deduped[0].index
    for p in preds_deduped[1:]:
        common_idx = common_idx.intersection(p.index)
    combined = pd.Series(0.0, index=common_idx)
    total_weight = sum(weights)
    for pred, w in zip(preds_deduped, weights):
        combined += pred.reindex(common_idx).fillna(0) * w
    combined /= total_weight
    return combined


def has_vwap_data() -> bool:
    """检查 Qlib 数据中是否有 vwap 字段"""
    sample_dirs = list((config.DATA_PATH / "features").iterdir())[:5]
    for d in sample_dirs:
        if (d / "vwap.day.bin").exists():
            return True
    return False


def run_backtest(
    pred,
    test_start: str,
    test_end: str,
    topk: int = 30,
    n_drop: int = 5,
    use_predicted_vwap: bool = True,
    train_start: str = None,
    train_end: str = None,
    valid_start: str = None,
    valid_end: str = None,
    features: str = "extra",
    vwap_lgb_kwargs: dict | None = None,
    capital: float | None = None,
) -> dict:
    """
    运行回测。当 use_predicted_vwap=True 且有 VWAP 数据时，使用预测 VWAP 替代实际 VWAP，
    使回测结果与实盘一致、更可信。
    """
    if use_predicted_vwap and has_vwap_data() and all([train_start, train_end, valid_start, valid_end]):
        return _run_backtest_with_predicted_vwap(
            pred, test_start, test_end, topk, n_drop,
            train_start, train_end, valid_start, valid_end, features,
            vwap_lgb_kwargs=vwap_lgb_kwargs,
            capital=capital,
        )
    return _run_backtest_qlib(pred, test_start, test_end, topk, n_drop)


def _run_backtest_qlib(pred, test_start: str, test_end: str, topk: int, n_drop: int) -> dict:
    """Qlib 原生回测（使用实际 VWAP/close）"""
    test_pred = pred.loc[pred.index.get_level_values("datetime") >= pd.Timestamp(test_start)]
    strategy_config = {
        "class": "TopkDropoutStrategy",
        "module_path": "qlib.contrib.strategy",
        "kwargs": {
            "signal": test_pred,
            "topk": topk,
            "n_drop": n_drop,
        },
    }
    strat = init_instance_by_config(strategy_config)
    executor_obj = qlib_executor.SimulatorExecutor(
        time_per_step="day", generate_portfolio_metrics=True,
    )
    deal_price = "vwap" if has_vwap_data() else "close"
    portfolio_metric_dict, _ = qlib_backtest(
        start_time=test_start,
        end_time=test_end,
        strategy=strat,
        executor=executor_obj,
        benchmark="000300.SH",
        account=1_000_000,
        exchange_kwargs={
            "freq": "day",
            "limit_threshold": 0.095,
            "deal_price": deal_price,
            "open_cost": 0.0010,
            "close_cost": 0.0020,
            "min_cost": 5,
            "trade_unit": 100,
        },
    )
    return portfolio_metric_dict


def _run_backtest_with_predicted_vwap(
    pred,
    test_start: str,
    test_end: str,
    topk: int,
    n_drop: int,
    train_start: str,
    train_end: str,
    valid_start: str,
    valid_end: str,
    features: str,
    vwap_lgb_kwargs: dict | None = None,
    capital: float | None = None,
) -> dict:
    """使用预测 VWAP 的自定义回测，与实盘逻辑一致。
    capital: 资金约束。若指定，则 BUY 时跳过 100*price > capital/topk 的股票，模拟小资金实盘。
    """
    import trades as tr
    import vwap_model as vwap

    test_pred = pred.loc[pred.index.get_level_values("datetime") >= pd.Timestamp(test_start)]
    if test_pred.empty:
        return {"1day": (pd.DataFrame(), None)}

    trade_list, daily_port = tr.simulate_trades(test_pred, test_start, topk=topk, n_drop=n_drop)
    pred_price_dict = vwap.build_predicted_price_dict(
        trade_list, test_start, test_end,
        train_start, train_end, valid_start, valid_end, features,
        vwap_lgb_kwargs=vwap_lgb_kwargs,
    )
    completed = tr.compute_trade_returns(
        trade_list, test_start, test_end, price_dict_override=pred_price_dict
    )

    # 用 close 做日度市值，构建 report
    cal = sorted(D.calendar(start_time=test_start, end_time=test_end, freq="day"))
    account = capital if capital is not None else 1_000_000
    trade_unit = 100

    date_to_idx = {d: i for i, d in enumerate(cal)}

    def exec_date(signal_date):
        idx = date_to_idx.get(signal_date)
        if idx is not None and idx + 1 < len(cal):
            return cal[idx + 1]
        return signal_date

    # 构建 (date, stock) -> price，预测 VWAP 覆盖执行日，其余用 close
    price_dict = dict(pred_price_dict)
    all_stocks = list(set(t["stock"] for t in trade_list))
    if all_stocks:
        try:
            close_df = D.features(all_stocks, ["$close"], start_time=test_start, end_time=test_end, freq="day")
            close_df.columns = ["close"]
            for idx, row in close_df.iterrows():
                inst = idx[0] if idx[0] in all_stocks else idx[1]
                dt = idx[1] if idx[0] in all_stocks else idx[0]
                if isinstance(dt, pd.Timestamp) and (dt, inst) not in price_dict:
                    price_dict[(dt, inst)] = float(row["close"])
        except Exception:
            pass

    positions = {}
    daily_values = []
    prev_value = account

    for i, date in enumerate(cal):
        date_str = date.strftime("%Y-%m-%d")
        signal_d = cal[i - 1] if i > 0 else date
        port = daily_port.get(signal_d, daily_port.get(date, []))
        if not port:
            daily_values.append({"date": date, "value": prev_value, "return": 0})
            continue

        # 处理当日执行的交易（信号 T 日 → 执行 T+1 日）
        day_trades = [t for t in trade_list if exec_date(t["date"]) == date]
        for t in day_trades:
            stock, action = t["stock"], t["action"]
            price = price_dict.get((date, stock), 0)
            if price <= 0:
                continue
            min_cost = trade_unit * price
            cap_per_stock = account / topk
            if action == "BUY":
                # 资金约束：买不起 100 股则跳过，模拟小资金实盘
                if min_cost > cap_per_stock:
                    continue
            shares = max(trade_unit, int((account / topk / price) // trade_unit) * trade_unit)
            if action == "BUY":
                positions[stock] = {"shares": shares, "cost": price}
            else:
                positions.pop(stock, None)

        # 当日市值：持仓 * close；若尚未建仓（交易 T+1 执行），保持现金
        value = 0
        for stock in port:
            if stock in positions:
                p = price_dict.get((date, stock), 0)
                if p <= 0:
                    try:
                        r = D.features([stock], ["$close"], start_time=date_str, end_time=date_str, freq="day")
                        p = float(r.iloc[0, 0]) if not r.empty else 0
                    except Exception:
                        p = positions[stock]["cost"]
                value += positions[stock]["shares"] * p

        # 首日或尚未执行任何交易时，positions 为空，value=0 会错误导致 -100% 收益
        if value == 0 and prev_value > 0:
            value = prev_value

        ret = (value - prev_value) / prev_value if prev_value > 0 else 0
        daily_values.append({"date": date, "value": value, "return": ret})
        prev_value = value

    if not daily_values:
        return {"1day": (pd.DataFrame(), None)}

    report = pd.DataFrame(daily_values).set_index("date")[["return"]]
    report["return"] = report["return"].fillna(0)
    try:
        bench = D.features(
            ["000300.SH"], ["$close/Ref($close,1)-1"],
            start_time=test_start, end_time=test_end, freq="day",
        )
        bench = bench.droplevel(0, axis=0) if hasattr(bench.index, "nlevels") and bench.index.nlevels > 1 else bench
        report["bench"] = bench.reindex(report.index).fillna(0)
    except Exception:
        report["bench"] = 0
    return {"1day": (report, None)}


def analyze(portfolio_metric_dict, name: str = "") -> dict | None:
    """分析回测结果，返回指标字典"""
    report, _ = portfolio_metric_dict.get("1day", (None, None))
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

    report = report.copy()
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


def run_strategy(
    name: str,
    pred,
    test_start: str,
    test_end: str,
    topk: int,
    n_drop: int,
    bad_mask=None,
    excluded_stocks=None,
    train_start: str = None,
    train_end: str = None,
    valid_start: str = None,
    valid_end: str = None,
    features: str = "extra",
    vwap_lgb_kwargs: dict | None = None,
    capital: float | None = None,
) -> tuple:
    """运行策略: 过滤 + 回测 + 分析。有 VWAP 时默认用预测 VWAP 使回测与实盘一致"""
    import filter as flt
    pred = flt.filter_predictions(pred, bad_mask, excluded_stocks)
    pm = run_backtest(
        pred, test_start, test_end, topk=topk, n_drop=n_drop,
        use_predicted_vwap=True,
        train_start=train_start, train_end=train_end,
        valid_start=valid_start, valid_end=valid_end,
        features=features,
        vwap_lgb_kwargs=vwap_lgb_kwargs,
        capital=capital,
    )
    result = analyze(pm, name=name)
    if result:
        print(f"    -> 收益 {result['total_return']*100:+.2f}%, "
              f"回撤 {result['max_drawdown']*100:.2f}%, "
              f"超额 {(result['excess_return'] or 0)*100:+.2f}%")
    return result, pred
