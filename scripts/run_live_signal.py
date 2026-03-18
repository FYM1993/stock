"""
实盘信号脚本 — 轻量级，仅预测最新一日并输出 TopK + 仓位 + 建议价

用法:
  python scripts/run_live_signal.py                    # 默认预测最新交易日
  python scripts/run_live_signal.py --date 2026-03-12  # 指定信号日
  python scripts/run_live_signal.py --topk 15          # 输出 Top15
  python scripts/run_live_signal.py --capital 10       # 总资金10万，过滤买不起的股票
  python scripts/run_live_signal.py --capital 10 --auto-best  # 按回测收益选最佳标签

输出: 排名 | 仓位(等权) | 收盘价 | 建议价(预测次日VWAP)
逻辑: 信号日 T 的预测 → 执行日 T+1
  例如 3/12 收盘后预测 → 3/13 买入
  建议价 = LightGBM 回归预测次日 VWAP (label=Ref($vwap,-1)/$close)
"""
import os
from datetime import datetime, timedelta

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["MPLCONFIGDIR"] = "/tmp/mpl"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import qlib
from qlib.config import REG_CN
from qlib.data import D

import config
import factors
import filter as flt
import train
import strategy
import output
import vwap_model


def main():
    import argparse
    parser = argparse.ArgumentParser(description="实盘信号 — 输出最新一日 TopK")
    parser.add_argument("--date", type=str, default=None, help="信号日 (YYYY-MM-DD)，默认最新交易日")
    parser.add_argument("--topk", type=int, default=10)
    parser.add_argument("--capital", type=float, default=None,
                        help="总资金(万)，用于输出每只建议金额；同时会过滤掉买不起的股票")
    parser.add_argument("--auto-best", action="store_true",
                        help="根据回测收益自动选用最佳方案（2日/5日/10日单标签 or 融合，需配合 --capital，回测近40交易日）")
    parser.add_argument("--model", choices=["lgb", "ensemble"], default="lgb")
    parser.add_argument("--features", choices=["extra", "alpha158_only"], default="alpha158_only")
    parser.add_argument("--use-cache", action="store_true", default=True)
    parser.add_argument("--no-cache", action="store_true", help="禁用因子缓存")
    args = parser.parse_args()

    qlib.init(provider_uri=str(config.DATA_PATH), region=REG_CN)

    # 训练期与验证期（与回测一致）
    p = config.PERIODS["2025-10-2026-03"]
    train_start = p["train_start"]
    train_end = p["train_end"]
    valid_start = p["valid_start"]
    valid_end = p["valid_end"]

    # 确定信号日：有 --date 用指定日；否则取数据中最新交易日
    if args.date:
        signal_date = args.date
    else:
        end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        cal = list(D.calendar(start_time="2026-01-01", end_time=end, freq="day"))
        if not cal:
            print("无法获取交易日历")
            return
        signal_date = cal[-1].strftime("%Y-%m-%d")

    use_cache = not args.no_cache
    capital_yuan = int(args.capital * 10000) if args.capital else None

    label_configs = [
        ("2日", None),
        ("5日", "Ref($close, -5)/Ref($close, -1) - 1"),
        ("10日", "Ref($close, -10)/Ref($close, -1) - 1"),
    ]

    # 确定预测范围：auto-best 需回测近 40 交易日选最佳标签
    cal_full = list(D.calendar(start_time=train_start, end_time=signal_date, freq="day"))
    n_backtest = 40
    if args.auto_best and capital_yuan and len(cal_full) > n_backtest:
        backtest_start = cal_full[-n_backtest].strftime("%Y-%m-%d")
        backtest_end = signal_date
        test_start_roll = backtest_start
        test_end_roll = signal_date
    else:
        test_start_roll = test_end_roll = signal_date

    test_start = test_end = signal_date

    print("=" * 60)
    print(f"实盘信号 — 信号日 {signal_date} → 执行日 T+1")
    print("=" * 60)
    print(f"数据: {config.DATA_PATH}")
    print(f"训练: {train_start}~{train_end} | 验证: {valid_start}~{valid_end}")
    print(f"预测日: {signal_date} | TopK: {args.topk}")
    if args.auto_best and capital_yuan and len(cal_full) > n_backtest:
        print(f"模式: 回测选最佳方案 (单标签 or 融合, 资金 {args.capital}万, 回测 {test_start_roll}~{signal_date})")
    else:
        print(f"模式: 固定融合 (2日×0.5 + 5日×0.3 + 10日×0.2)")

    handlers = {}
    for label_name, label_expr in label_configs:
        handlers[label_name] = factors.build_handler(
            train_start, train_end, test_end_roll,
            extra_features=args.features,
            label_expr=label_expr,
        )

    test_instruments = D.instruments(market="all")
    bad_mask, excluded_stocks = flt.build_stock_filter(test_instruments, test_start, test_end)

    rolling_preds = {}
    for label_name, label_expr in label_configs:
        pred, _, _ = train.rolling_train_predict(
            handlers[label_name],
            train_start, train_end, valid_start, valid_end,
            test_start_roll, test_end_roll,
            step=20, model_type=args.model, features=args.features,
            label_name=label_name, use_cache=use_cache,
            label_expr=label_expr,
        )
        rolling_preds[label_name] = pred

    # 选用最佳方案（单标签 or 融合），与回测一致，有回测数据支撑
    if args.auto_best and capital_yuan and len(cal_full) > n_backtest:
        best_scheme = None  # "2日" | "5日" | "10日" | "融合"
        best_ret = -999.0
        n_drop = max(1, args.topk // 5)
        for label_name, _ in label_configs:
            pred = rolling_preds[label_name]
            result, _ = strategy.run_strategy(
                f"选最佳|{label_name}", pred,
                backtest_start, backtest_end, args.topk, n_drop,
                bad_mask=bad_mask, excluded_stocks=excluded_stocks,
                train_start=train_start, train_end=train_end,
                valid_start=valid_start, valid_end=valid_end,
                features=args.features,
                capital=capital_yuan,
            )
            if result and (result.get("total_return") or -999) > best_ret:
                best_ret = result["total_return"]
                best_scheme = label_name
        pred_ensemble = strategy.ensemble_predictions(
            [rolling_preds[lc[0]] for lc in label_configs],
            [0.5, 0.3, 0.2],
        )
        result, _ = strategy.run_strategy(
            "选最佳|融合", pred_ensemble,
            backtest_start, backtest_end, args.topk, n_drop,
            bad_mask=bad_mask, excluded_stocks=excluded_stocks,
            train_start=train_start, train_end=train_end,
            valid_start=valid_start, valid_end=valid_end,
            features=args.features,
            capital=capital_yuan,
        )
        if result and (result.get("total_return") or -999) > best_ret:
            best_ret = result["total_return"]
            best_scheme = "融合"
        if best_scheme == "融合":
            print(f"\n  -> 最佳方案: 融合 (2日×0.5+5日×0.3+10日×0.2, 回测收益 {best_ret*100:+.2f}%)")
            filtered_pred = flt.filter_predictions(pred_ensemble, bad_mask, excluded_stocks)
        elif best_scheme:
            print(f"\n  -> 最佳方案: {best_scheme} (回测收益 {best_ret*100:+.2f}%)")
            filtered_pred = flt.filter_predictions(rolling_preds[best_scheme], bad_mask, excluded_stocks)
        else:
            filtered_pred = flt.filter_predictions(pred_ensemble, bad_mask, excluded_stocks)
    else:
        pred_ensemble = strategy.ensemble_predictions(
            [rolling_preds[lc[0]] for lc in label_configs],
            [0.5, 0.3, 0.2],
        )
        filtered_pred = flt.filter_predictions(pred_ensemble, bad_mask, excluded_stocks)

    # 执行日 = 信号日 T+1 的下一个交易日
    cal = list(D.calendar(start_time=signal_date, end_time="2026-12-31", freq="day"))
    exec_date = cal[1].strftime("%Y-%m-%d") if len(cal) > 1 else "T+1"

    # 获取 TopK 股票，用于查询价格
    test_pred = filtered_pred.loc[
        filtered_pred.index.get_level_values("datetime") >= pd.Timestamp(test_start)
    ]
    if test_pred.empty:
        print("无有效预测")
        return

    latest = test_pred.index.get_level_values("datetime").max()
    day_pred = test_pred.loc[latest].sort_values(ascending=False)
    if isinstance(day_pred, pd.DataFrame):
        day_pred = day_pred.iloc[:, 0]
    top_stocks = day_pred.head(args.topk).index.tolist()

    # 次日 VWAP 预测：LightGBM 回归模型 (label=Ref($vwap,-1)/$close)
    prices_df = None
    try:
        if strategy.has_vwap_data():
            vwap_model.ensure_model(train_start, train_end, valid_start, valid_end, args.features)
            vwap_handler = factors.build_vwap_handler(
                train_start, train_end, signal_date, extra_features=args.features
            )
            ratios = vwap_model.predict_vwap_ratios(top_stocks, signal_date, vwap_handler)
            if ratios:
                raw = D.features(
                    top_stocks, ["$close"],
                    start_time=signal_date, end_time=signal_date, freq="day",
                )
                raw.columns = ["close"]
                rows = []
                for stock in top_stocks:
                    try:
                        if hasattr(raw.index, "get_level_values"):
                            s = raw.loc[raw.index.get_level_values(0) == stock]
                        else:
                            s = raw.loc[stock] if stock in raw.index else pd.DataFrame()
                        if isinstance(s, pd.Series):
                            s = s.to_frame().T
                        if len(s) > 0:
                            close_val = float(s["close"].iloc[-1])
                            ratio = ratios.get(stock, 1.0)
                            pred_vwap = close_val * ratio
                            rows.append({
                                "instrument": stock,
                                "datetime": latest,
                                "close": close_val,
                                "vwap": pred_vwap,
                            })
                        else:
                            rows.append({
                                "instrument": stock,
                                "datetime": latest,
                                "close": np.nan,
                                "vwap": np.nan,
                            })
                    except Exception:
                        rows.append({
                            "instrument": stock,
                            "datetime": latest,
                            "close": np.nan,
                            "vwap": np.nan,
                        })
                if rows:
                    prices_df = pd.DataFrame(rows).set_index(["instrument", "datetime"])
        else:
            raw = D.features(
                top_stocks, ["$close"],
                start_time=signal_date, end_time=signal_date, freq="day",
            )
            raw.columns = ["close"]
            rows = []
            for stock in top_stocks:
                try:
                    if hasattr(raw.index, "get_level_values"):
                        s = raw.loc[raw.index.get_level_values(0) == stock]
                    else:
                        s = raw.loc[stock] if stock in raw.index else pd.DataFrame()
                    if isinstance(s, pd.Series):
                        s = s.to_frame().T
                    if len(s) > 0:
                        last = s.iloc[-1]
                        rows.append({
                            "instrument": stock,
                            "datetime": latest,
                            "close": last["close"],
                            "vwap": last["close"],
                        })
                except Exception:
                    pass
            if rows:
                prices_df = pd.DataFrame(rows).set_index(["instrument", "datetime"])
    except Exception as e:
        print(f"  价格/VWAP预测失败: {e}")

    print(f"\n{'='*60}")
    print(f"今日股票排名 (基于 {signal_date} 收盘预测，{exec_date} 执行)")
    print(f"{'='*60}")
    df_out = output.print_live_signal_with_position(
        filtered_pred, test_start, args.topk, prices_df, exec_date,
        capital_wan=args.capital,
        capital_yuan=capital_yuan,
    )

    # 保存到 CSV（含仓位、建议价）
    if not df_out.empty:
        path = config.RESULTS_DIR / f"live_signal_{signal_date}.csv"
        df_out.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"\n已保存: {path}")

    print("\n完成!")


if __name__ == "__main__":
    main()
