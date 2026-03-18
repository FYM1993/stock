"""
以预测 VWAP 回测收益为目标的超参优化

使用 Optuna 搜索 Alpha 模型 + VWAP 模型参数，使预测 VWAP 回测收益最大化。
与实盘逻辑一致，避免「用实际价格回测虚高」的问题。

用法:
  python scripts/optimize_predicted_vwap.py --period 2026-full --n-trials 20
  python scripts/optimize_predicted_vwap.py --period 2026-full --n-trials 50 --timeout 7200
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
import vwap_model


def run_full_pipeline(
    train_start: str,
    train_end: str,
    valid_start: str,
    valid_end: str,
    test_start: str,
    test_end: str,
    alpha_override: dict,
    vwap_override: dict,
    topk: int = 10,
    n_drop: int = 2,
    features: str = "alpha158_only",
    step: int = 20,
    verbose: bool = False,
    capital: float | None = None,
) -> float:
    """
    运行完整流程：滚动训练 -> 融合 -> 过滤 -> 预测 VWAP 回测
    返回总收益率
    """
    label_configs = [
        ("2日", None, 0.5),
        ("5日", "Ref($close, -5)/Ref($close, -1) - 1", 0.3),
        ("10日", "Ref($close, -10)/Ref($close, -1) - 1", 0.2),
    ]

    handlers = {}
    for label_name, label_expr, _ in label_configs:
        handlers[label_name] = factors.build_handler(
            train_start, train_end, test_end,
            extra_features=features,
            label_expr=label_expr,
        )

    test_instruments = D.instruments(market="all")
    bad_mask, excluded_stocks = flt.build_stock_filter(test_instruments, test_start, test_end)

    rolling_preds = {}
    for label_name, _, _ in label_configs:
        pred, _, _ = train.rolling_train_predict(
            handlers[label_name],
            train_start, train_end, valid_start, valid_end, test_start, test_end,
            step=step, model_type="lgb", features=features,
            label_name=label_name, use_cache=True,
            model_config_override=alpha_override,
        )
        rolling_preds[label_name] = pred

    pred_ensemble = strategy.ensemble_predictions(
        [rolling_preds[lc[0]] for lc in label_configs],
        [lc[2] for lc in label_configs],
    )

    result, _ = strategy.run_strategy(
        "opt", pred_ensemble,
        test_start, test_end, topk, n_drop,
        bad_mask=bad_mask, excluded_stocks=excluded_stocks,
        train_start=train_start, train_end=train_end,
        valid_start=valid_start, valid_end=valid_end,
        features=features,
        vwap_lgb_kwargs=vwap_override,
        capital=capital,
    )

    if result is None:
        return -999.0
    ret = result.get("total_return")
    if ret is None:
        return -999.0
    if verbose:
        print(f"    总收益: {ret*100:+.2f}%")
    return ret


def main():
    import argparse
    parser = argparse.ArgumentParser(description="以预测 VWAP 回测收益为目标优化超参")
    parser.add_argument("--period", default="2026-full", choices=list(config.PERIODS.keys()))
    parser.add_argument("--n-trials", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=3600, help="总超时秒数")
    parser.add_argument("--features", default="alpha158_only")
    parser.add_argument("--baseline", action="store_true", help="仅跑一次 baseline（无 override）验证流程")
    parser.add_argument("--capital", type=float, default=None,
                        help="资金约束(元)。指定后回测会跳过买不起的股票，优化目标基于小资金实盘")
    args = parser.parse_args()

    p = config.PERIODS[args.period]
    train_start = p["train_start"]
    train_end = p["train_end"]
    valid_start = p["valid_start"]
    valid_end = p["valid_end"]
    test_start = p["test_start"]
    test_end = p["test_end"]

    if not strategy.has_vwap_data():
        print("无 VWAP 数据，无法优化。请先运行 update_vwap_data.py")
        return

    qlib.init(provider_uri=str(config.DATA_PATH), region=REG_CN)

    print("=" * 60)
    print(f"预测 VWAP 回测超参优化 — {args.period}")
    print(f"  测试期: {test_start} ~ {test_end}")
    print(f"  目标: 最大化预测 VWAP 回测总收益（与实盘一致）")
    if args.capital is not None:
        print(f"  资金约束: {args.capital:,.0f} 元（模拟小资金实盘）")
    if args.baseline:
        print("  模式: baseline（无 override）")
    else:
        print(f"  试验数: {args.n_trials} | 超时: {args.timeout}s")
    print("=" * 60)

    if args.baseline:
        # 与 run_qlib_strategy 一致：尝试 Top10 和 Top15
        for tk, nd in [(10, 2), (15, 3)]:
            ret = run_full_pipeline(
                train_start, train_end, valid_start, valid_end,
                test_start, test_end,
                alpha_override={},
                vwap_override={},
                topk=tk, n_drop=nd, features=args.features, step=20,
                verbose=True,
                capital=args.capital,
            )
            print(f"  Top{tk}: {ret*100:+.2f}%")
        print(f"\nBaseline 总收益: {ret*100:+.2f}%")
        return

    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        alpha_override = {
            "learning_rate": trial.suggest_float("alpha_lr", 0.01, 0.1, log=True),
            "max_depth": trial.suggest_int("alpha_max_depth", 4, 10),
            "num_leaves": trial.suggest_int("alpha_num_leaves", 31, 256),
            "n_estimators": trial.suggest_int("alpha_n_est", 500, 1500, step=100),
        }
        vwap_override = {
            "learning_rate": trial.suggest_float("vwap_lr", 0.02, 0.15, log=True),
            "max_depth": trial.suggest_int("vwap_max_depth", 4, 8),
            "num_leaves": trial.suggest_int("vwap_num_leaves", 32, 128),
            "n_estimators": trial.suggest_int("vwap_n_est", 300, 800, step=100),
        }
        return run_full_pipeline(
            train_start, train_end, valid_start, valid_end,
            test_start, test_end,
            alpha_override, vwap_override,
            topk=10, n_drop=2, features=args.features, step=20,
            verbose=False,
            capital=args.capital,
        )

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=args.n_trials, timeout=args.timeout, show_progress_bar=True)

    print("\n" + "=" * 60)
    print("优化完成")
    print("=" * 60)
    print(f"  最佳收益: {study.best_value*100:+.2f}%")
    print(f"  最佳参数:")
    for k, v in study.best_params.items():
        print(f"    {k}: {v}")

    # 保存最佳参数供后续使用
    import json
    out_path = config.RESULTS_DIR / "optimize_predicted_vwap_best.json"
    bp = study.best_params
    alpha_cfg = {
        "learning_rate": bp.get("alpha_lr"),
        "max_depth": bp.get("alpha_max_depth"),
        "num_leaves": bp.get("alpha_num_leaves"),
        "n_estimators": bp.get("alpha_n_est"),
    }
    vwap_cfg = {
        "learning_rate": bp.get("vwap_lr"),
        "max_depth": bp.get("vwap_max_depth"),
        "num_leaves": bp.get("vwap_num_leaves"),
        "n_estimators": bp.get("vwap_n_est"),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"alpha": alpha_cfg, "vwap": vwap_cfg, "best_return": study.best_value}, f, indent=2)
    print(f"\n  已保存: {out_path}")
    print("  TODO: 将最佳参数合并进 config.py / vwap_model.py 后重新回测")


if __name__ == "__main__":
    main()
