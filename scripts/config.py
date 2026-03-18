"""
配置模块 — 回测周期、路径、模型参数
单一职责: 集中管理所有配置常量
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "qlib_data" / "cn_data"
RESULTS_DIR = PROJECT_ROOT / "results"
CACHE_DIR = PROJECT_ROOT / "cache" / "factors"
RESULTS_DIR.mkdir(exist_ok=True)

PERIODS = {
    "2025": {
        "train_start": "2023-01-01",
        "train_end": "2025-03-31",
        "valid_start": "2025-04-01",
        "valid_end": "2025-04-30",
        "test_start": "2025-05-01",
        "test_end": "2025-08-31",
    },
    "2026": {
        "train_start": "2025-05-01",
        "train_end": "2025-10-31",
        "valid_start": "2025-11-01",
        "valid_end": "2025-12-31",
        "test_start": "2026-03-01",
        "test_end": "2026-03-11",
    },
    "2026-full": {
        "train_start": "2025-05-01",
        "train_end": "2025-10-31",
        "valid_start": "2025-11-01",
        "valid_end": "2025-12-31",
        "test_start": "2026-01-02",
        "test_end": "2026-03-11",
    },
    "2025-04-2026-03": {
        "train_start": "2023-01-01",
        "train_end": "2025-03-31",
        "valid_start": "2025-02-01",
        "valid_end": "2025-03-31",
        "test_start": "2025-04-01",
        "test_end": "2026-03-11",
    },
    "2025-10-2026-03": {
        "train_start": "2023-01-01",
        "train_end": "2025-08-31",
        "valid_start": "2025-09-01",
        "valid_end": "2025-09-30",
        "test_start": "2025-10-01",
        "test_end": "2026-03-11",
    },
}


def get_lgb_config():
    """LightGBM 模型配置"""
    return {
        "class": "LGBModel",
        "module_path": "qlib.contrib.model.gbdt",
        "kwargs": {
            "loss": "mse",
            "colsample_bytree": 0.8879,
            "learning_rate": 0.0421,
            "subsample": 0.8789,
            "lambda_l1": 205.6999,
            "lambda_l2": 580.9768,
            "max_depth": 8,
            "num_leaves": 210,
            "num_threads": 1,
            "n_estimators": 1000,
            "early_stopping_rounds": 100,
            "verbosity": -1,
        },
    }


def get_double_ensemble_config():
    """DoubleEnsemble 模型配置"""
    return {
        "class": "DEnsembleModel",
        "module_path": "qlib.contrib.model.double_ensemble",
        "kwargs": {
            "base_model": "gbm",
            "num_models": 6,
            "enable_sr": True,
            "enable_fs": True,
            "alpha1": 1,
            "alpha2": 1,
            "bins_sr": 10,
            "bins_fs": 5,
            "decay": 0.5,
        },
    }


def get_model_config(model_type: str, **override):
    """根据模型类型返回配置，override 会合并进 kwargs"""
    if model_type == "ensemble":
        cfg = get_double_ensemble_config()
    else:
        cfg = get_lgb_config()
    if override:
        cfg = {**cfg, "kwargs": {**cfg.get("kwargs", {}), **override}}
    return cfg
