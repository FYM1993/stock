"""
缓存模块 — 因子数据预计算与缓存
单一职责: 因子数据的保存、加载、校验
"""
from pathlib import Path
import hashlib
import pickle
import pandas as pd

import config


def _cache_key(features: str, label_name: str, train_start: str, test_end: str) -> str:
    """生成缓存唯一标识"""
    raw = f"{features}|{label_name}|{train_start}|{test_end}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _cache_path(cache_key: str) -> Path:
    """缓存文件路径"""
    path = config.CACHE_DIR / f"factors_{cache_key}.pkl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def exists(features: str, label_name: str, train_start: str, test_end: str) -> bool:
    """检查缓存是否存在"""
    key = _cache_key(features, label_name, train_start, test_end)
    return _cache_path(key).exists()


def save(
    features: str,
    label_name: str,
    train_start: str,
    test_end: str,
    data: dict,
) -> Path:
    """
    保存因子数据到缓存。
    data: {"df": DataFrame with (datetime, instrument) index, "feature_cols": list, "label_col": str}
    """
    key = _cache_key(features, label_name, train_start, test_end)
    path = _cache_path(key)
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(data, f, protocol=4)
    return path


def load(
    features: str,
    label_name: str,
    train_start: str,
    test_end: str,
) -> dict | None:
    """从缓存加载因子数据，不存在返回 None"""
    key = _cache_key(features, label_name, train_start, test_end)
    path = _cache_path(key)
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def slice_by_dates(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """按日期范围切片 DataFrame，index 为 (datetime, instrument)"""
    if df.empty:
        return df
    idx = df.index
    if isinstance(idx, pd.MultiIndex):
        dates = idx.get_level_values(0)
    else:
        dates = idx
    mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
    return df.loc[mask]
