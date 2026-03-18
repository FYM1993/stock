"""
Qlib 因子模型回测 v3 — 模块化版

用法:
  python run_qlib_strategy.py --period 2026 --mode rolling
  python run_qlib_strategy.py --period 2026 --mode rolling --model ensemble
  python run_qlib_strategy.py --period 2025-10-2026-03 --mode rolling --use-cache  # 启用因子缓存
  python run_qlib_strategy.py --period 2026 --mode both --no-cache
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["MPLCONFIGDIR"] = "/tmp/mpl"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import qlib
from qlib.config import REG_CN
from qlib.data import D

import config
import factors
import filter as flt
import train
import strategy
import trades
import output
import vwap_model


def main():
    parser = __import__("argparse").ArgumentParser(
        description="Qlib Alpha158 v3 — 滚动训练 + 信号融合 + 交易明细"
    )
    parser.add_argument("--period", choices=list(config.PERIODS.keys()), default="2026")
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--step", type=int, default=20)
    parser.add_argument("--mode", choices=["rolling", "static", "both"], default="both")
    parser.add_argument("--model", choices=["lgb", "ensemble"], default="lgb")
    parser.add_argument("--topk", type=int, default=10)
    parser.add_argument("--features", choices=["extra", "alpha158_only"], default="alpha158_only")
    parser.add_argument("--use-cache", action="store_true", help="启用因子缓存 (默认开启，滚动训练时生效)")
    parser.add_argument("--no-cache", action="store_true", help="禁用因子缓存")
    parser.add_argument("--capital", type=float, default=None,
                        help="资金约束(元)。指定后回测会跳过买不起的股票，模拟小资金实盘")
    args = parser.parse_args()

    p = config.PERIODS[args.period]
    train_start = p["train_start"]
    train_end = p["train_end"]
    valid_start = p["valid_start"]
    valid_end = p["valid_end"]
    test_start = p["test_start"]
    test_end = p["test_end"]
    if args.start and args.end:
        test_start, test_end = args.start, args.end

    use_cache = not args.no_cache  # 默认开启缓存，--no-cache 可禁用
    model_name = "LightGBM" if args.model == "lgb" else "DoubleEnsemble"
    feat_name = "Alpha158+自定义(~200)" if args.features == "extra" else "Alpha158(158)"

    print("=" * 70)
    print(f"Qlib v3 [{args.period}] — {model_name} | {feat_name}")
    print("=" * 70)

    qlib.init(provider_uri=str(config.DATA_PATH), region=REG_CN)
    print(f"数据: {config.DATA_PATH}")
    print(f"训练: {train_start}~{train_end} | 验证: {valid_start}~{valid_end}")
    print(f"测试: {test_start}~{test_end}")
    print(f"模型: {model_name} | 因子: {feat_name}")
    print(f"模式: {args.mode} | 步长: {args.step}天 | TopK: {args.topk}")
    if args.capital is not None:
        print(f"资金约束: {args.capital:,.0f} 元 (模拟小资金实盘)")
    if use_cache:
        print(f"因子缓存: 启用 (cache/factors/)")

    label_configs = [
        ("2日", None, 0.5),
        ("5日", "Ref($close, -5)/Ref($close, -1) - 1", 0.3),
        ("10日", "Ref($close, -10)/Ref($close, -1) - 1", 0.2),
    ]

    print(f"\n构建因子处理器 ({feat_name} x 3 标签)...")
    handlers = {}
    for label_name, label_expr, _ in label_configs:
        print(f"  计算 {label_name}标签 因子...")
        handlers[label_name] = factors.build_handler(
            train_start, train_end, test_end,
            extra_features=args.features,
            label_expr=label_expr,
        )

    print("\n构建股票过滤条件...")
    test_instruments = D.instruments(market="all")
    bad_mask, excluded_stocks = flt.build_stock_filter(test_instruments, test_start, test_end)
    if bad_mask is not None:
        n_bad, n_total = bad_mask.sum(), len(bad_mask)
        print(f"  日度过滤 (一字板+低流动性): {n_total} 条中 {n_bad} 条 ({n_bad/n_total*100:.1f}%)")
    print(f"  成交价: {'VWAP (预测，与实盘一致)' if strategy.has_vwap_data() else 'Close (收盘价)'}")

    all_results = []
    best_pred = None
    best_name = ""
    best_excess = -999
    topk = args.topk
    n_drop = max(1, topk // 5)

    if args.mode in ("static", "both"):
        print(f"\n{'='*70}")
        print(f"[对照组] v1 固定训练 — {model_name}")
        print(f"{'='*70}")
        for label_name, _, _ in label_configs:
            print(f"\n  训练 {label_name}标签 (固定)...")
            pred, importance, feat_names = train.static_train_predict(
                handlers[label_name],
                train_start, train_end, valid_start, valid_end, test_start, test_end,
                model_type=args.model,
            )
            n_test = pred.loc[pred.index.get_level_values("datetime") >= pd.Timestamp(test_start)].shape[0]
            print(f"  预测: {pred.shape[0]} 条 (测试期 {n_test} 条)")
            result, filtered_pred = strategy.run_strategy(
                f"v1固定|{label_name}+Top{topk}", pred,
                test_start, test_end, topk, n_drop,
                bad_mask=None, excluded_stocks=excluded_stocks,
                train_start=train_start, train_end=train_end,
                valid_start=valid_start, valid_end=valid_end,
                features=args.features,
                capital=args.capital,
            )
            all_results.append(result)
            if result and (result.get("excess_return") or -999) > best_excess:
                best_excess = result["excess_return"] or -999
                best_pred = pred
                best_name = result["name"]

    if args.mode in ("rolling", "both"):
        print(f"\n{'='*70}")
        print(f"[实验组] v2 滚动训练 — {model_name} (step={args.step})")
        print(f"{'='*70}")
        rolling_preds = {}
        reported_importance = False

        for label_name, _, weight in label_configs:
            print(f"\n  {label_name}标签 滚动训练...")
            pred, importance, feat_names = train.rolling_train_predict(
                handlers[label_name],
                train_start, train_end, valid_start, valid_end, test_start, test_end,
                step=args.step, model_type=args.model, features=args.features,
                label_name=label_name, use_cache=use_cache,
            )
            rolling_preds[label_name] = pred
            print(f"  {label_name} 预测: {len(pred)} 条")
            if not reported_importance and importance is not None:
                output.print_feature_importance(importance, feat_names)
                reported_importance = True
            result, filtered_pred = strategy.run_strategy(
                f"v2滚动|{label_name}+Top{topk}", pred,
                test_start, test_end, topk, n_drop,
                bad_mask=bad_mask, excluded_stocks=excluded_stocks,
                train_start=train_start, train_end=train_end,
                valid_start=valid_start, valid_end=valid_end,
                features=args.features,
                capital=args.capital,
            )
            all_results.append(result)
            if result and (result.get("excess_return") or -999) > best_excess:
                best_excess = result["excess_return"] or -999
                best_pred = filtered_pred
                best_name = result["name"]

        print(f"\n{'='*70}")
        print("[信号融合] 2日x0.5 + 5日x0.3 + 10日x0.2")
        print(f"{'='*70}")
        preds_list = [rolling_preds[lc[0]] for lc in label_configs]
        weights = [lc[2] for lc in label_configs]
        pred_ensemble = strategy.ensemble_predictions(preds_list, weights)
        print(f"  融合信号: {len(pred_ensemble)} 条")
        for tk, nd in [(topk, n_drop), (5, 1), (15, 3)]:
            result, filtered_pred = strategy.run_strategy(
                f"v2融合|Top{tk}", pred_ensemble,
                test_start, test_end, tk, nd,
                bad_mask=bad_mask, excluded_stocks=excluded_stocks,
                train_start=train_start, train_end=train_end,
                valid_start=valid_start, valid_end=valid_end,
                features=args.features,
                capital=args.capital,
            )
            all_results.append(result)
            if result and (result.get("excess_return") or -999) > best_excess:
                best_excess = result["excess_return"] or -999
                best_pred = filtered_pred
                best_name = result["name"]

    output.print_comparison(all_results, test_start, test_end)

    if best_pred is not None:
        print(f"\n  RankIC 监控 (预测与未来收益相关性):")
        output.print_rank_ic(best_pred, test_start, test_end, name=best_name)

    if best_pred is not None:
        print(f"\n{'='*70}")
        print(f"最优方案交易明细: {best_name}")
        print(f"{'='*70}")
        best_topk = topk
        for tk_val in [5, 10, 15, 20, 30]:
            if f"Top{tk_val}" in best_name:
                best_topk = tk_val
                break
        best_ndrop = max(1, best_topk // 5)
        trade_list, daily_port = trades.simulate_trades(best_pred, test_start, topk=best_topk, n_drop=best_ndrop)
        pred_price_dict = {}
        if strategy.has_vwap_data():
            pred_price_dict = vwap_model.build_predicted_price_dict(
                trade_list, test_start, test_end,
                train_start, train_end, valid_start, valid_end,
                args.features,
            )
        completed = trades.compute_trade_returns(
            trade_list, test_start, test_end,
            price_dict_override=pred_price_dict if pred_price_dict else None,
        )
        trades.print_trade_log(completed, name=best_name)
        trades.print_daily_portfolio(daily_port)
        output.print_daily_signal(best_pred, test_start, topk=best_topk)
        output.save_trade_log(completed, best_name)
        valid = [r for r in all_results if r is not None]
        if valid:
            best_result = max(valid, key=lambda x: x.get("excess_return") or -999)
            output.save_best_report(best_result)

    print("\n完成!")


if __name__ == "__main__":
    main()
