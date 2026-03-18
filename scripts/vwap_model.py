"""
VWAP 预测模型 — LightGBM 回归预测次日 VWAP/Close 比值

Label: Ref($vwap, -1) / $close
预测: pred_ratio，则 pred_vwap_T1 = close[T] * pred_ratio

用法:
  python scripts/vwap_model.py train   # 训练模型
  python scripts/vwap_model.py eval    # 评估预测误差
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import pandas as pd
import numpy as np
from pathlib import Path
from qlib.data.dataset import DatasetH
from qlib.data import D
from qlib.utils import init_instance_by_config

import config
import factors
import strategy


VWAP_MODEL_PATH = config.PROJECT_ROOT / "cache" / "vwap_model.txt"
VWAP_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)


def _get_lgb_regression_config(**override):
    """VWAP 回归用 LGB 配置，override 会合并进 kwargs"""
    base = {
        "class": "LGBModel",
        "module_path": "qlib.contrib.model.gbdt",
        "kwargs": {
            "loss": "mse",
            "num_threads": 1,
            "n_estimators": 500,
            "early_stopping_rounds": 50,
            "verbosity": -1,
            "max_depth": 6,
            "num_leaves": 64,
            "learning_rate": 0.05,
        },
    }
    if override:
        base["kwargs"] = {**base["kwargs"], **override}
    return base


def train_vwap_model(
    train_start: str,
    train_end: str,
    valid_start: str,
    valid_end: str,
    features: str = "extra",
    model_path: Path | None = None,
    lgb_kwargs: dict | None = None,
) -> bool:
    """训练 VWAP 预测模型，保存到 model_path"""
    if not strategy.has_vwap_data():
        print("  [VWAP] 无 VWAP 数据，无法训练")
        return False

    model_path = model_path or VWAP_MODEL_PATH
    handler = factors.build_vwap_handler(train_start, train_end, valid_end, extra_features=features)

    dataset = DatasetH(
        handler=handler,
        segments={
            "train": (train_start, train_end),
            "valid": (valid_start, valid_end),
        },
    )

    model = init_instance_by_config(_get_lgb_regression_config(**(lgb_kwargs or {})))
    model.fit(dataset)

    try:
        model.model.save_model(str(model_path))
        print(f"  [VWAP] 模型已保存: {model_path}")
        return True
    except Exception as e:
        # LightGBM booster save
        model.model.booster_.save_model(str(model_path))
        print(f"  [VWAP] 模型已保存: {model_path}")
        return True


def load_model(model_path: Path | None = None):
    """加载 LGB 模型"""
    import lightgbm as lgb
    path = model_path or VWAP_MODEL_PATH
    if not path.exists():
        return None
    return lgb.Booster(model_file=str(path))


def predict_vwap_ratios(
    stocks: list,
    signal_date: str,
    handler,
    model_path: Path | None = None,
) -> dict:
    """
    预测指定股票在 signal_date 的次日 VWAP/Close 比值。
    返回 {stock: pred_ratio}，用于 pred_vwap = close * pred_ratio
    """
    model = load_model(model_path)
    if model is None:
        return {}

    # 获取 signal_date 当日的特征（handler 需覆盖到 signal_date）
    dataset = DatasetH(
        handler=handler,
        segments={
            "train": (signal_date, signal_date),
            "valid": (signal_date, signal_date),
            "test": (signal_date, signal_date),
        },
    )
    try:
        prepared = dataset.prepare(["test"], col_set=["feature"])
    except TypeError:
        prepared = dataset.prepare(["test"], col_set=["feature"], data_key=0)

    if isinstance(prepared, (list, tuple)):
        seg = prepared[0]
    else:
        seg = prepared

    feat = seg["feature"] if hasattr(seg, "__getitem__") else seg
    if feat is None or (hasattr(feat, "empty") and feat.empty):
        return {}

    # 过滤到 stocks，处理 (datetime, instrument) 或 (instrument, datetime)
    idx = feat.index
    if hasattr(idx, "get_level_values") and idx.nlevels >= 2:
        inst_idx = 1 if (idx.names[0] == "datetime" or "datetime" in str(idx.names[0])) else 0
        inst_level = idx.get_level_values(inst_idx)
        mask = inst_level.isin(stocks)
        feat = feat.loc[mask]
    else:
        feat = feat[feat.index.isin(stocks)] if hasattr(feat.index, "isin") else feat

    if feat.empty:
        return {}

    pred_arr = model.predict(feat)
    if isinstance(pred_arr, pd.Series):
        pred_arr = pred_arr.values

    result = {}
    for i, idx_val in enumerate(feat.index):
        if isinstance(idx_val, tuple):
            stock = idx_val[0] if idx_val[0] in stocks else idx_val[1]
        else:
            stock = idx_val
        if stock in stocks:
            ratio = float(pred_arr[i])
            result[stock] = max(0.5, min(1.5, ratio))  # 裁剪到合理范围

    return result


def build_predicted_price_dict(
    trades: list,
    test_start: str,
    test_end: str,
    train_start: str,
    train_end: str,
    valid_start: str,
    valid_end: str,
    features: str = "extra",
    vwap_lgb_kwargs: dict | None = None,
) -> dict:
    """
    为交易列表构建 (exec_date, stock) -> pred_vwap 的字典。
    用于回测时使用预测 VWAP 替代实际 VWAP。
    """
    from qlib.data import D

    if not strategy.has_vwap_data() or not trades:
        return {}

    ensure_model(train_start, train_end, valid_start, valid_end, features, lgb_kwargs=vwap_lgb_kwargs)
    handler = factors.build_vwap_handler(train_start, train_end, test_end, extra_features=features)

    cal = sorted(D.calendar(start_time=test_start, end_time=test_end, freq="day"))
    date_to_idx = {d: i for i, d in enumerate(cal)}

    def exec_date(signal_date):
        idx = date_to_idx.get(signal_date)
        if idx is not None and idx + 1 < len(cal):
            return cal[idx + 1]
        return signal_date

    # 收集所有 (exec_date, stock) 对
    exec_pairs = set()
    for t in trades:
        ed = exec_date(t["date"])
        exec_pairs.add((ed, t["stock"]))

    # 按 exec_date 分组，批量预测
    by_date = {}
    for (ed, stock) in exec_pairs:
        by_date.setdefault(ed, set()).add(stock)

    price_dict = {}
    for exec_d in sorted(by_date.keys()):
        try:
            idx = cal.index(exec_d)
            if idx <= 0:
                continue
            signal_d = cal[idx - 1]
        except (ValueError, TypeError):
            continue
        stocks = list(by_date[exec_d])
        ratios = predict_vwap_ratios(stocks, signal_d.strftime("%Y-%m-%d"), handler)
        if not ratios:
            continue
        try:
            close_df = D.features(
                stocks, ["$close"],
                start_time=signal_d.strftime("%Y-%m-%d"),
                end_time=signal_d.strftime("%Y-%m-%d"),
                freq="day",
            )
            close_df.columns = ["close"]
            for stock in stocks:
                try:
                    if hasattr(close_df.index, "get_level_values") and close_df.index.nlevels >= 2:
                        lev0 = close_df.index.get_level_values(0)
                        lev1 = close_df.index.get_level_values(1)
                        mask = lev0.isin([stock]) | lev1.isin([stock])
                        s = close_df.loc[mask]
                    else:
                        s = close_df.loc[stock] if stock in close_df.index else pd.DataFrame()
                    if isinstance(s, pd.Series):
                        s = s.to_frame().T
                    if len(s) > 0:
                        close_val = float(s["close"].iloc[-1])
                        ratio = ratios.get(stock, 1.0)
                        price_dict[(exec_d, stock)] = close_val * ratio
                except Exception:
                    pass
        except Exception:
            pass

    return price_dict


def ensure_model(
    train_start: str,
    train_end: str,
    valid_start: str,
    valid_end: str,
    features: str = "extra",
    force_retrain: bool = False,
    lgb_kwargs: dict | None = None,
) -> bool:
    """确保模型存在，不存在则训练"""
    if lgb_kwargs:
        force_retrain = True  # 参数变化需重训
    if force_retrain or not VWAP_MODEL_PATH.exists():
        print("  [VWAP] 训练 VWAP 预测模型...")
        return train_vwap_model(train_start, train_end, valid_start, valid_end, features, lgb_kwargs=lgb_kwargs)
    return True


def eval_vwap_model(
    train_start: str,
    train_end: str,
    valid_start: str,
    valid_end: str,
    test_start: str,
    test_end: str,
    features: str = "extra",
):
    """评估 VWAP 模型在测试集上的误差"""
    import qlib
    from qlib.config import REG_CN

    qlib.init(provider_uri=str(config.DATA_PATH), region=REG_CN)

    if not strategy.has_vwap_data():
        print("无 VWAP 数据")
        return

    ensure_model(train_start, train_end, valid_start, valid_end, features)

    handler = factors.build_vwap_handler(train_start, train_end, test_end, extra_features=features)
    dataset = DatasetH(
        handler=handler,
        segments={
            "train": (train_start, train_end),
            "valid": (valid_start, valid_end),
            "test": (test_start, test_end),
        },
    )

    model = load_model()
    if model is None:
        print("模型加载失败")
        return

    prepared = dataset.prepare(["test"], col_set=["feature", "label"])
    if isinstance(prepared, (list, tuple)):
        seg = prepared[0]
    else:
        seg = prepared

    feat = seg["feature"]
    lab = seg["label"]
    if feat is None or lab is None:
        print("无测试数据")
        return

    pred = model.predict(feat)
    lab_arr = np.asarray(lab).flatten()
    pred_arr = np.asarray(pred).flatten()

    valid_mask = np.isfinite(lab_arr) & np.isfinite(pred_arr)
    lab_arr = lab_arr[valid_mask]
    pred_arr = pred_arr[valid_mask]

    mae = np.abs(lab_arr - pred_arr).mean()
    mse = np.mean((lab_arr - pred_arr) ** 2)
    mape = np.mean(np.abs((lab_arr - pred_arr) / (lab_arr + 1e-8))) * 100

    print(f"\n  [VWAP] 测试集评估 ({test_start} ~ {test_end}):")
    print(f"    MAE(ratio):  {mae:.6f}")
    print(f"    RMSE:        {np.sqrt(mse):.6f}")
    print(f"    MAPE:        {mape:.2f}%")
    print(f"    样本数:      {len(lab_arr)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["train", "eval"])
    parser.add_argument("--features", default="alpha158_only")
    args = parser.parse_args()

    import qlib
    from qlib.config import REG_CN
    qlib.init(provider_uri=str(config.DATA_PATH), region=REG_CN)

    p = config.PERIODS["2025-10-2026-03"]
    if args.cmd == "train":
        train_vwap_model(
            p["train_start"], p["train_end"],
            p["valid_start"], p["valid_end"],
            features=args.features,
        )
    else:
        eval_vwap_model(
            p["train_start"], p["train_end"],
            p["valid_start"], p["valid_end"],
            p["test_start"], p["test_end"],
            features=args.features,
        )
