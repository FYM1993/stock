"""
因子模块 — 因子定义与 Handler 构建
单一职责: 定义因子表达式、构建 DataHandler
"""
from qlib.contrib.data.handler import Alpha158
from qlib.data.dataset.handler import DataHandlerLP


def get_extra_feature_config():
    """
    Alpha158 缺失的追加因子 (~40个)
    1. 中长期动量/反转 2. 波动率结构 3. 量价关系
    4. 价格位置 5. 均线系统 6. 趋势强度 7. K线形态
    """
    fields, names = [], []

    for d in [20, 40, 60]:
        fields.append(f"Ref($close,{d})/$close - 1")
        names.append(f"REVS{d}")
    for d in [20, 60]:
        fields.append(f"Mean($close,{d})/$close - 1")
        names.append(f"MA_RATIO{d}")

    fields.append("Std($close/Ref($close,1)-1, 5) / (Std($close/Ref($close,1)-1, 20) + 1e-8)")
    names.append("VOL_RATIO_5_20")
    fields.append("Std($close/Ref($close,1)-1, 10) / (Std($close/Ref($close,1)-1, 60) + 1e-8)")
    names.append("VOL_RATIO_10_60")
    fields.append("Std($high-$low, 5) / (Mean($close, 5) + 1e-8)")
    names.append("RANGE_VOL5")
    fields.append("Std($high-$low, 20) / (Mean($close, 20) + 1e-8)")
    names.append("RANGE_VOL20")

    for d in [5, 10, 20]:
        fields.append(f"Corr($close, $volume, {d})")
        names.append(f"PRICE_VOL_CORR{d}")
    fields.append("Mean($volume, 5) / (Mean($volume, 20) + 1e-8)")
    names.append("VOL_MA_RATIO_5_20")
    fields.append("Mean($volume, 5) / (Mean($volume, 60) + 1e-8)")
    names.append("VOL_MA_RATIO_5_60")
    fields.append("$volume / (Mean($volume, 20) + 1e-8)")
    names.append("VOL_SURGE")

    for d in [10, 20, 60]:
        fields.append(f"($close - Min($low, {d})) / (Max($high, {d}) - Min($low, {d}) + 1e-8)")
        names.append(f"PRICE_POS{d}")
    fields.append("$close / (Max($high, 60) + 1e-8)")
    names.append("DIST_HIGH60")
    fields.append("$close / (Min($low, 60) + 1e-8)")
    names.append("DIST_LOW60")

    fields.append("(Mean($close,5) - Mean($close,20)) / (Mean($close,20) + 1e-8)")
    names.append("MA_CROSS_5_20")
    fields.append("(Mean($close,10) - Mean($close,60)) / (Mean($close,60) + 1e-8)")
    names.append("MA_CROSS_10_60")
    fields.append("(Mean($close,20) - Mean($close,60)) / (Mean($close,60) + 1e-8)")
    names.append("MA_CROSS_20_60")

    fields.append("Abs(Mean($close/Ref($close,1)-1, 20)) / (Std($close/Ref($close,1)-1, 20) + 1e-8)")
    names.append("TREND_STRENGTH20")
    fields.append("Abs(Mean($close/Ref($close,1)-1, 60)) / (Std($close/Ref($close,1)-1, 60) + 1e-8)")
    names.append("TREND_STRENGTH60")

    fields.append("($close - $open) / ($high - $low + 1e-8)")
    names.append("CANDLE_BODY")
    fields.append("($high - Greater($open, $close)) / ($high - $low + 1e-8)")
    names.append("UPPER_SHADOW")
    fields.append("(Less($open, $close) - $low) / ($high - $low + 1e-8)")
    names.append("LOWER_SHADOW")

    return fields, names


def build_handler(
    train_start: str,
    train_end: str,
    test_end: str,
    extra_features: str = "extra",
    market: str = "all",
    label_expr=None,
):
    """
    构建因子 Handler。
    extra_features: "alpha158_only" | "extra"
    """
    label_kwarg = {}
    if label_expr:
        label_kwarg["label"] = ([label_expr], ["LABEL0"])

    if extra_features == "alpha158_only":
        return Alpha158(
            instruments=market,
            start_time=train_start,
            end_time=test_end,
            fit_start_time=train_start,
            fit_end_time=train_end,
            infer_processors=[{"class": "Fillna", "kwargs": {"fields_group": "feature"}}],
            learn_processors=[
                {"class": "DropnaLabel"},
                {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
            ],
            **label_kwarg,
        )

    base = Alpha158(
        instruments=market,
        start_time=train_start,
        end_time=test_end,
        fit_start_time=train_start,
        fit_end_time=train_end,
        infer_processors=[{"class": "Fillna", "kwargs": {"fields_group": "feature"}}],
        learn_processors=[
            {"class": "DropnaLabel"},
            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
        ],
        **label_kwarg,
    )
    try:
        base_fields, base_names = base.get_feature_config()
    except Exception:
        return base

    extra_fields, extra_names = get_extra_feature_config()
    all_fields = list(base_fields) + extra_fields
    all_names = list(base_names) + extra_names

    default_label = (["Ref($close, -2)/Ref($close, -1) - 1"], ["LABEL0"])
    return DataHandlerLP(
        instruments=market,
        start_time=train_start,
        end_time=test_end,
        process_type=DataHandlerLP.PTYPE_A,
        infer_processors=[{"class": "Fillna", "kwargs": {"fields_group": "feature"}}],
        learn_processors=[
            {"class": "DropnaLabel"},
            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
        ],
        data_loader={
            "class": "QlibDataLoader",
            "kwargs": {
                "config": {
                    "feature": (all_fields, all_names),
                    "label": label_kwarg.get("label", default_label),
                },
                "freq": "day",
            },
        },
    )


def build_handler_inference(
    train_start: str,
    train_end: str,
    test_end: str,
    extra_features: str = "extra",
    market: str = "all",
    label_expr=None,
):
    """
    构建仅用于推理的 Handler：不 DropnaLabel，保留末日期（无未来 label 的日期）用于预测。
    """
    label_kwarg = {}
    if label_expr:
        label_kwarg["label"] = ([label_expr], ["LABEL0"])

    if extra_features == "alpha158_only":
        return Alpha158(
            instruments=market,
            start_time=train_start,
            end_time=test_end,
            fit_start_time=train_start,
            fit_end_time=train_end,
            infer_processors=[{"class": "Fillna", "kwargs": {"fields_group": "feature"}}],
            learn_processors=[],  # 不 DropnaLabel，保留末日期
            **label_kwarg,
        )

    base = Alpha158(
        instruments=market,
        start_time=train_start,
        end_time=test_end,
        fit_start_time=train_start,
        fit_end_time=train_end,
        infer_processors=[{"class": "Fillna", "kwargs": {"fields_group": "feature"}}],
        learn_processors=[],
        **label_kwarg,
    )
    try:
        base_fields, base_names = base.get_feature_config()
    except Exception:
        return base

    extra_fields, extra_names = get_extra_feature_config()
    all_fields = list(base_fields) + extra_fields
    all_names = list(base_names) + extra_names

    default_label = (["Ref($close, -2)/Ref($close, -1) - 1"], ["LABEL0"])
    return DataHandlerLP(
        instruments=market,
        start_time=train_start,
        end_time=test_end,
        process_type=DataHandlerLP.PTYPE_A,
        infer_processors=[{"class": "Fillna", "kwargs": {"fields_group": "feature"}}],
        learn_processors=[],
        data_loader={
            "class": "QlibDataLoader",
            "kwargs": {
                "config": {
                    "feature": (all_fields, all_names),
                    "label": label_kwarg.get("label", default_label),
                },
                "freq": "day",
            },
        },
    )


def build_vwap_handler(train_start: str, train_end: str, test_end: str, extra_features: str = "extra"):
    """
    构建 VWAP 预测用 Handler。
    Label = Ref($vwap, -1) / $close，即次日 VWAP 与当日 close 的比值。
    回归任务，不使用 CSRankNorm。
    """
    label_expr = "Ref($vwap, -1) / $close"
    label_kwarg = {"label": ([label_expr], ["LABEL0"])}

    base = Alpha158(
        instruments="all",
        start_time=train_start,
        end_time=test_end,
        fit_start_time=train_start,
        fit_end_time=train_end,
        infer_processors=[{"class": "Fillna", "kwargs": {"fields_group": "feature"}}],
        learn_processors=[{"class": "DropnaLabel"}],
        **label_kwarg,
    )
    try:
        base_fields, base_names = base.get_feature_config()
    except Exception:
        return base

    extra_fields, extra_names = get_extra_feature_config()
    all_fields = list(base_fields) + extra_fields
    all_names = list(base_names) + extra_names

    return DataHandlerLP(
        instruments="all",
        start_time=train_start,
        end_time=test_end,
        process_type=DataHandlerLP.PTYPE_A,
        infer_processors=[{"class": "Fillna", "kwargs": {"fields_group": "feature"}}],
        learn_processors=[{"class": "DropnaLabel"}],
        data_loader={
            "class": "QlibDataLoader",
            "kwargs": {
                "config": {
                    "feature": (all_fields, all_names),
                    "label": ([label_expr], ["LABEL0"]),
                },
                "freq": "day",
            },
        },
    )
