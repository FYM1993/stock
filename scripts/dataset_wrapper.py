"""
Dataset 包装器 — 从缓存的 DataFrame 构建 Dataset 兼容对象
单一职责: 提供与 qlib Dataset 兼容的 prepare() 接口
"""
import pandas as pd


class CachedDataset:
    """
    包装缓存的因子数据，提供与 qlib Dataset 兼容的 prepare() 接口。
    用于滚动训练时从缓存切片，避免重复计算因子。
    """

    def __init__(self, full_df: pd.DataFrame, segments: dict, feature_cols: list, label_col: str):
        """
        full_df: 完整因子 DataFrame，index=(datetime, instrument)
        segments: {"train": (start, end), "valid": (...), "test": (...)}
        feature_cols: 特征列名列表
        label_col: 标签列名
        """
        self._full_df = full_df
        self._segments = segments
        self._feature_cols = feature_cols
        self._label_col = label_col

    @property
    def segments(self):
        """qlib 模型 fit 时需要 dataset.segments"""
        return self._segments

    def _slice(self, seg_name: str) -> pd.DataFrame:
        """按 segment 日期范围切片"""
        if seg_name not in self._segments:
            return pd.DataFrame()
        start, end = self._segments[seg_name]
        idx = self._full_df.index
        dates = idx.get_level_values(0) if isinstance(idx, pd.MultiIndex) else idx
        mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
        return self._full_df.loc[mask].copy()

    def _to_handler_format(self, df: pd.DataFrame):
        """转换为 Handler 返回格式，支持 df['feature'] 和 df['label']"""

        class _SegmentData:
            def __init__(self, feature_df, label_series):
                self._feature = feature_df
                self._label = label_series

            @property
            def empty(self):
                return self._feature.empty if hasattr(self._feature, "empty") else len(self._feature) == 0

            def __getitem__(self, key):
                if key == "feature":
                    return self._feature
                if key == "label":
                    return self._label
                raise KeyError(key)

        if df.empty:
            return _SegmentData(pd.DataFrame(), pd.Series(dtype=float))

        feats = [c for c in self._feature_cols if c in df.columns]
        feature_df = df[feats] if feats else pd.DataFrame(index=df.index)
        label_sr = df[self._label_col] if self._label_col in df.columns else pd.Series(dtype=float, index=df.index)
        # qlib LGBModel 要求 label 为 2D (n,1)，否则报 multi-label
        if hasattr(label_sr, "values") and label_sr.values.ndim == 1:
            label_sr = pd.DataFrame({self._label_col: label_sr.values}, index=label_sr.index)
        elif hasattr(label_sr, "to_frame"):
            label_sr = label_sr.to_frame()
        return _SegmentData(feature_df, label_sr)

    def prepare(self, segments, col_set=None, data_key=None):
        """
        兼容 qlib Dataset.prepare() 接口。
        segments: ["train", "valid"] 或 ["test"] 等
        col_set: "feature" 时返回 DataFrame；["feature","label"] 时返回 _SegmentData
        """
        if isinstance(segments, str):
            segments = [segments]
        result = []
        for seg in segments:
            sliced = self._slice(seg)
            seg_data = self._to_handler_format(sliced)
            if col_set == "feature" or (isinstance(col_set, list) and col_set == ["feature"]):
                result.append(seg_data["feature"])
            else:
                result.append(seg_data)
        return result[0] if len(result) == 1 else tuple(result)
