"""
训练模块 — 滚动训练与固定训练
单一职责: 模型训练与预测逻辑
"""
import pandas as pd
import numpy as np
from qlib.data.dataset import DatasetH
from qlib.data import D
from qlib.utils import init_instance_by_config

import config
import cache
import factors
from dataset_wrapper import CachedDataset


def _get_windows(train_start: str, test_start: str, test_end: str, step: int) -> list:
    """计算滚动窗口列表"""
    cal = list(D.calendar(start_time=train_start, end_time=test_end, freq="day"))
    test_start_ts = pd.Timestamp(test_start)
    test_end_ts = pd.Timestamp(test_end)
    test_dates = [d for d in cal if test_start_ts <= d <= test_end_ts]
    if not test_dates:
        return []
    windows = []
    for i in range(0, len(test_dates), step):
        w_start = test_dates[i]
        w_end = test_dates[min(i + step - 1, len(test_dates) - 1)]
        windows.append((w_start, w_end))
    return windows


def _fetch_last_date_features(
    train_start: str,
    train_end: str,
    test_end: str,
    target_date: str,
    features: str,
    label_name: str,
    label_expr,
) -> pd.DataFrame | None:
    """用无 DropnaLabel 的 handler 获取指定日期的特征（预测日无未来 label 会被正常 handler 丢弃）"""
    if label_expr is None:
        label_expr = "Ref($close, -2)/Ref($close, -1) - 1"  # 2日默认
    inf_handler = factors.build_handler_inference(
        train_start, train_end, test_end,
        extra_features=features,
        label_expr=label_expr,
    )
    dataset = DatasetH(
        handler=inf_handler,
        segments={"test": (target_date, target_date)},
    )
    try:
        prepared = dataset.prepare(["test"], col_set=["feature", "label"])
    except TypeError:
        prepared = dataset.prepare(["test"], col_set=["feature", "label"], data_key=0)
    out = prepared[0] if isinstance(prepared, (list, tuple)) else prepared
    feat = out["feature"] if hasattr(out, "__getitem__") else out
    if feat is None or (hasattr(feat, "empty") and feat.empty):
        return None
    return feat.copy()


def _compute_full_dataset(handler, train_start: str, test_end: str) -> tuple:
    """计算全量因子数据（用于缓存）"""
    dataset = DatasetH(
        handler=handler,
        segments={
            "train": (train_start, test_end),
            "valid": (train_start, test_end),
            "test": (train_start, test_end),
        },
    )
    try:
        prepared = dataset.prepare(
            ["train", "valid", "test"],
            col_set=["feature", "label"],
        )
    except TypeError:
        prepared = dataset.prepare(
            ["train", "valid", "test"],
            col_set=["feature", "label"],
            data_key=0,
        )
    df_train = prepared[0] if isinstance(prepared, (list, tuple)) else prepared
    feat = df_train["feature"] if hasattr(df_train, "__getitem__") else df_train
    lab = df_train["label"] if hasattr(df_train, "__getitem__") else pd.Series(dtype=float)
    full = feat.copy()
    if lab is not None and not (hasattr(lab, "empty") and lab.empty):
        full["LABEL0"] = lab
    if full.index.duplicated().any():
        full = full[~full.index.duplicated(keep="last")]
    feature_cols = list(feat.columns) if hasattr(feat, "columns") else []
    return full, feature_cols, "LABEL0"


def rolling_train_predict(
    handler,
    train_start: str,
    train_end: str,
    valid_start: str,
    valid_end: str,
    test_start: str,
    test_end: str,
    step: int = 20,
    model_type: str = "lgb",
    features: str = "extra",
    label_name: str = "2日",
    use_cache: bool = True,
    model_config_override: dict | None = None,
    label_expr=None,
) -> tuple:
    """
    滚动训练: 每 step 天重训，支持因子缓存。
    返回 (full_pred, avg_importance, feature_names)
    """
    cal = list(D.calendar(start_time=train_start, end_time=test_end, freq="day"))
    windows = _get_windows(train_start, test_start, test_end, step)
    if not windows:
        raise ValueError(f"测试期 {test_start}~{test_end} 内无交易日")

    cached_data = None
    if use_cache and cache.exists(features, label_name, train_start, test_end):
        print(f"    [缓存] 加载 {label_name} 因子数据...")
        cached_data = cache.load(features, label_name, train_start, test_end)

    def _ensure_last_date_in_df(data: dict, last_date: str) -> None:
        """若末日期被 DropnaLabel 丢弃，用 inference handler 补回"""
        df = data["df"]
        idx = df.index
        dates = idx.get_level_values(0) if isinstance(idx, pd.MultiIndex) else idx
        if pd.Timestamp(last_date) in dates:
            return
        extra = _fetch_last_date_features(
            train_start, train_end, test_end, last_date, features, label_name, label_expr
        )
        if extra is not None and not extra.empty:
            extra["LABEL0"] = np.nan
            combined = pd.concat([df, extra]).sort_index()
            if combined.index.duplicated().any():
                combined = combined[~combined.index.duplicated(keep="last")]
            data["df"] = combined
            print(f"    [补全] 末日期 {last_date} 特征 (DropnaLabel 已丢弃)")

    all_preds = []
    importance_list = []
    feature_names = None
    def get_model():
        cfg = config.get_model_config(model_type, **(model_config_override or {}))
        return init_instance_by_config(cfg)

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
              f"训练 {train_start}~{t_end} | 验证 {v_start}~{v_end} | "
              f"预测 {w_start_str}~{w_end_str}")

        if cached_data is not None:
            _ensure_last_date_in_df(cached_data, w_end_str)
            dataset = CachedDataset(
                full_df=cached_data["df"],
                segments={
                    "train": (train_start, t_end),
                    "valid": (v_start, v_end),
                    "test": (w_start_str, w_end_str),
                },
                feature_cols=cached_data["feature_cols"],
                label_col=cached_data["label_col"],
            )
        else:
            if win_idx == 0:
                print(f"    [缓存] 预计算 {label_name} 因子 (仅首次)...")
                full_df, feature_cols, label_col = _compute_full_dataset(handler, train_start, test_end)
                cached_data = {"df": full_df, "feature_cols": feature_cols, "label_col": label_col}
                _ensure_last_date_in_df(cached_data, w_end_str)
                cache.save(features, label_name, train_start, test_end, cached_data)
            dataset = CachedDataset(
                full_df=cached_data["df"],
                segments={
                    "train": (train_start, t_end),
                    "valid": (v_start, v_end),
                    "test": (w_start_str, w_end_str),
                },
                feature_cols=cached_data["feature_cols"],
                label_col=cached_data["label_col"],
            )

        model = get_model()
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
    if isinstance(full_pred, pd.Series) and full_pred.index.duplicated().any():
        full_pred = full_pred[~full_pred.index.duplicated(keep="last")]
    avg_importance = np.mean(importance_list, axis=0) if importance_list else None
    return full_pred, avg_importance, feature_names


def static_train_predict(
    handler,
    train_start: str,
    train_end: str,
    valid_start: str,
    valid_end: str,
    test_start: str,
    test_end: str,
    model_type: str = "lgb",
) -> tuple:
    """固定训练: 训练一次，预测全部测试期"""
    dataset = DatasetH(
        handler=handler,
        segments={
            "train": (train_start, train_end),
            "valid": (valid_start, valid_end),
            "test": (test_start, test_end),
        },
    )
    model = init_instance_by_config(config.get_model_config(model_type))
    model.fit(dataset)
    pred = model.predict(dataset)

    importance, feature_names = None, None
    try:
        importance = model.model.feature_importance(importance_type="gain")
        feature_names = model.model.feature_name()
    except Exception:
        pass
    return pred, importance, feature_names
