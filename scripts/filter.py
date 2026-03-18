"""
过滤模块 — 股票池过滤
单一职责: ST/科创板/北交所/次新排除、一字板/低流动性日度过滤
"""
import pandas as pd
from qlib.data import D

import config


def load_excluded_stocks() -> tuple:
    """
    从 stock_info.csv 加载需排除的股票。
    返回 (excluded_set, reasons_dict)
    """
    path = config.DATA_PATH / "stock_info.csv"
    if not path.exists():
        print(f"  ⚠ 股票信息文件不存在: {path}")
        print(f"    请先运行: python scripts/update_vwap_data.py --info-only")
        return set(), {}

    info = pd.read_csv(path)
    excluded = set()
    reasons = {}

    for _, row in info.iterrows():
        sym = row["symbol"]
        r = []
        if row.get("is_st", False):
            r.append("ST")
        if row.get("is_kcb", False):
            r.append("科创板")
        if row.get("is_bj", False):
            r.append("北交所")
        list_date = row.get("list_date")
        if pd.notna(list_date):
            try:
                ld = pd.Timestamp(list_date)
                if (pd.Timestamp.now() - ld).days < 180:
                    r.append("次新股")
            except Exception:
                pass
        if r:
            excluded.add(sym)
            reasons[sym] = f"{row.get('short_name', '')}({','.join(r)})"
    return excluded, reasons


def build_stock_filter(instruments, start: str, end: str) -> tuple:
    """
    构建过滤掩码。
    返回 (bad_mask, excluded_stocks)
    """
    excluded_stocks, reasons = load_excluded_stocks()  # noqa: F841
    n_st = sum(1 for v in reasons.values() if "ST" in v)
    n_kcb = sum(1 for v in reasons.values() if "科创板" in v)
    n_bj = sum(1 for v in reasons.values() if "北交所" in v)
    n_new = sum(1 for v in reasons.values() if "次新" in v)
    print(f"  股票池排除: {len(excluded_stocks)} 只 "
          f"(ST={n_st}, 科创板={n_kcb}, 北交所={n_bj}, 次新={n_new})")

    try:
        data = D.features(
            instruments,
            ["$close/Ref($close,1)-1", "$volume*$close", "$close", "$open", "$high", "$low"],
            start_time=start, end_time=end, freq="day",
        )
        data.columns = ["daily_ret", "turnover", "close", "open", "high", "low"]
    except Exception as e:
        print(f"    过滤数据查询失败: {e}")
        return None, excluded_stocks

    # 一字板：涨跌停且开盘=收盘（无盘中成交，买不到）
    at_limit = data["daily_ret"].abs() > 0.095
    no_intraday = (data["high"] - data["low"]).abs() / data["close"].replace(0, 1) < 0.001
    limit_mask = at_limit & no_intraday
    dt_level = data.index.names.index("datetime") if data.index.names and "datetime" in data.index.names else (1 if data.index.nlevels > 1 else 0)
    daily_q10 = data.groupby(level=dt_level)["turnover"].transform(lambda x: x.quantile(0.10))
    try:
        low_liq_mask = data["turnover"] < daily_q10
    except ValueError:
        low_liq_mask = pd.Series(data["turnover"].values < daily_q10.values, index=data.index)
    bad_mask = limit_mask | low_liq_mask
    return bad_mask, excluded_stocks


def filter_predictions(pred, bad_mask, excluded_stocks=None):
    """对预测结果应用股票过滤"""
    if pred.empty:
        return pred
    n_before = len(pred)

    if excluded_stocks:
        inst_mask = pred.index.get_level_values("instrument").isin(excluded_stocks)
        pred = pred[~inst_mask]
        n_removed = n_before - len(pred)
        if n_removed > 0:
            print(f"    股票池过滤: 移除 {n_removed} 条 (ST/科创板/北交所/次新)")

    if bad_mask is not None and not pred.empty:
        common_bad = pred.index.intersection(bad_mask[bad_mask].index)
        pred = pred.drop(index=common_bad, errors="ignore")

    n_after = len(pred)
    if n_before > n_after:
        print(f"    总过滤: {n_before} -> {n_after} (移除 {n_before - n_after} 条, {(n_before - n_after) / n_before * 100:.1f}%)")
    return pred
