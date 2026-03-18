"""
输出模块 — 结果对比、信号输出、报告保存
单一职责: 打印与保存回测结果
"""
import numpy as np
import pandas as pd
from datetime import datetime
from scipy import stats

import config


def compute_rank_ic(pred: pd.Series, test_start: str, test_end: str, forward_days: int = 2) -> dict | None:
    """
    计算预测与未来收益的 RankIC、ICIR。
    pred: 预测分数，index=(datetime, instrument)
    forward_days: 未来 N 日收益
    """
    if pred.empty:
        return None
    try:
        from qlib.data import D
        instruments = pred.index.get_level_values("instrument").unique().tolist()
        if not instruments:
            return None
        ret_expr = f"Ref($close, -{forward_days})/Ref($close, -1) - 1"
        ret_df = D.features(
            instruments,
            [ret_expr],
            start_time=test_start,
            end_time=test_end,
            freq="day",
        )
        ret_df.columns = ["ret"]
        ret_sr = ret_df["ret"]
        common = pred.index.intersection(ret_sr.index)
        if hasattr(common, "drop_duplicates"):
            common = common.drop_duplicates()
        if len(common) < 10:
            return None
        p_vals = pred.reindex(common).dropna()
        r_vals = ret_sr.reindex(common).dropna()
        valid = p_vals.index.intersection(r_vals.index)
        if len(valid) < 10:
            return None
        p_vals = pred.loc[valid].values
        r_vals = ret_sr.loc[valid].values
        ic, _ = stats.spearmanr(p_vals, r_vals)
        ic = float(ic) if not np.isnan(ic) else 0.0
        return {"rank_ic": ic, "icir": ic, "n": len(valid)}
    except Exception as e:
        print(f"  RankIC 计算失败: {e}")
        return None


def print_rank_ic(pred, test_start: str, test_end: str, name: str = ""):
    """打印 RankIC（2日/5日/10日）"""
    for fd, label in [(2, "2日"), (5, "5日"), (10, "10日")]:
        res = compute_rank_ic(pred, test_start, test_end, forward_days=fd)
        if res:
            ic_str = f"RankIC={res['rank_ic']:.4f}"
            if res["rank_ic"] < -0.05:
                ic_str += " ⚠️ 负相关，可尝试预测取反"
            print(f"  [{name}] {label}标签 {ic_str} ICIR={res['icir']:.2f} n={res['n']}")
        else:
            print(f"  [{name}] {label}标签 RankIC 计算跳过")


def print_feature_importance(importance, feature_names=None, top_n: int = 20):
    """打印因子重要性"""
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


def print_comparison(results_list: list, test_start: str, test_end: str):
    """打印多方案对比"""
    valid = [r for r in results_list if r is not None]
    if not valid:
        print("所有实验均失败")
        return

    print(f"\n{'='*115}")
    print(f"多方案对比 ({test_start} ~ {test_end})")
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


def print_daily_signal(pred, test_start: str, topk: int = 10):
    """输出最新交易日选股信号"""
    test_pred = pred.loc[pred.index.get_level_values("datetime") >= pd.Timestamp(test_start)]
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


def print_live_signal_with_position(
    pred, test_start: str, topk: int, prices_df: pd.DataFrame | None, exec_date: str,
    capital_wan: float | None = None,
    capital_yuan: float | None = None,
):
    """
    输出实盘信号：排名 + 仓位建议 + 建议价格（含次日 VWAP 预测参考）
    prices_df: 来自 D.features 的 close/vwap，index=(instrument, datetime)
    capital_yuan: 资金约束(元)。指定后仅显示 100*price<=capital/topk 的可买股票
    """
    test_pred = pred.loc[pred.index.get_level_values("datetime") >= pd.Timestamp(test_start)]
    if test_pred.empty:
        return pd.DataFrame()
    latest_date = test_pred.index.get_level_values("datetime").max()
    day_pred = test_pred.loc[latest_date].sort_values(ascending=False)
    if isinstance(day_pred, pd.DataFrame):
        day_pred = day_pred.iloc[:, 0]
    top = day_pred.head(topk)

    position_pct = 100.0 / topk  # 等权仓位 %

    rows = []
    for i, (stock, score) in enumerate(top.items()):
        close_val = np.nan
        ref_price = np.nan
        vwap_pred = np.nan
        if prices_df is not None:
            try:
                idx = (stock, latest_date)
                if idx in prices_df.index:
                    row = prices_df.loc[idx]
                else:
                    mask = (prices_df.index.get_level_values(0) == stock)
                    if mask.any():
                        row = prices_df.loc[mask].iloc[-1]
                    else:
                        row = None
                if row is not None:
                    close_val = float(row.get("close", row.get("price", np.nan)))
                    if "vwap" in row.index and pd.notna(row.get("vwap")):
                        vwap_pred = float(row["vwap"])
                    elif "ref_price" in row.index:
                        vwap_pred = float(row["ref_price"])
                    else:
                        vwap_pred = close_val
                    ref_price = vwap_pred if not np.isnan(vwap_pred) else close_val
            except Exception:
                pass

        row_dict = {
            "rank": i + 1,
            "symbol": stock,
            "score": float(score),
            "position_pct": position_pct,
            "close": close_val,
            "ref_price": ref_price,
        }
        if capital_wan is not None and capital_wan > 0:
            row_dict["amount_wan"] = round(capital_wan * position_pct / 100, 2)
        rows.append(row_dict)

    df = pd.DataFrame(rows)
    df["ref_price"] = df["ref_price"].fillna(df["close"])

    # 资金约束：仅保留 100*price <= capital/topk 的可买股票
    if capital_yuan is not None and capital_yuan > 0:
        cap_per_stock = capital_yuan / topk
        df["affordable"] = (100 * df["ref_price"].fillna(np.inf)) <= cap_per_stock
        n_skip = (~df["affordable"]).sum()
        df = df[df["affordable"]].copy()
        df = df.drop(columns=["affordable"])
        df["rank"] = range(1, len(df) + 1)
        if n_skip > 0:
            print(f"\n  [资金约束] {capital_yuan:,.0f}元 Top{topk} 可买 {len(df)} 只 (跳过 {n_skip} 只买不起)")

    header = f"  {'排名':<4} {'股票':<14} {'信号分':>8} {'仓位':>8} {'收盘价':>8} {'建议价(预测VWAP)':>14}"
    if capital_wan is not None and capital_wan > 0:
        header += f" {'建议金额(万)':>10}"
    print(f"\n{header}")
    sep_len = 65 + (12 if capital_wan and capital_wan > 0 else 0)
    print(f"  {'-'*sep_len}")
    for _, r in df.iterrows():
        pos_str = f"{r['position_pct']:.1f}%"
        close_str = f"{r['close']:.2f}" if pd.notna(r["close"]) and r["close"] > 0 else "  -"
        ref_str = f"{r['ref_price']:.2f}" if pd.notna(r["ref_price"]) and r["ref_price"] > 0 else "  -"
        line = f"  {int(r['rank']):<4d} {r['symbol']:<14} {r['score']:>8.4f} {pos_str:>8} {close_str:>8} {ref_str:>14}"
        if capital_wan is not None and capital_wan > 0 and "amount_wan" in r:
            line += f" {r['amount_wan']:>10.2f}"
        print(line)

    print(f"\n  说明: 仓位为等权分配 | 建议价=LightGBM预测次日VWAP，供T+1挂单参考")
    return df


def save_trade_log(completed_trades: list, name: str) -> str | None:
    """保存交易明细到 CSV"""
    if not completed_trades:
        return None
    import pandas as pd
    df = pd.DataFrame(completed_trades)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = config.RESULTS_DIR / f"trades_{ts}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n  交易明细已保存: {path}")
    return str(path)


def save_best_report(best_result: dict) -> str | None:
    """保存最优方案收益报告"""
    if not best_result:
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = config.RESULTS_DIR / f"qlib_v3_best_{ts}.csv"
    best_result["report"].to_csv(path)
    print(f"  收益报告已保存: {path}")
    return str(path)
