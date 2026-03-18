# A股量化选股系统

基于 Qlib + LightGBM 的 A股量化选股回测与实盘信号系统。用 Alpha158 量价因子训练模型，预测股票未来收益，按排名选股持有。支持预测 VWAP 成交价，与实盘逻辑一致。

数据源使用 [adata](https://github.com/1nchaos/adata)，多数据源融合，比 akshare 更稳定。

## 项目结构

```
stock/
├── scripts/
│   ├── run_qlib_strategy.py      # 核心回测（因子+模型+滚动训练+信号融合）
│   ├── run_live_signal.py        # 实盘信号（输出次日 TopK + 建议价）
│   ├── collect_data.py           # 全量采集（adata → Qlib 格式）
│   ├── update_data.py            # 增量更新行情
│   ├── update_vwap_data.py       # 增量更新 amount/vwap 字段
│   ├── daily.sh                  # 每日任务（更新数据 + 实盘信号）
│   ├── strategy.py               # 回测逻辑、预测 VWAP 回测
│   ├── trades.py                 # 交易模拟、收益计算
│   ├── vwap_model.py             # VWAP 预测模型
│   ├── factors.py / train.py / filter.py / output.py
│   └── config.py                 # 周期、路径、模型参数
├── data/
│   ├── adata_provider.py         # adata 数据接口
│   └── data_converter.py         # CSV → Qlib 二进制
├── qlib_data/cn_data/           # Qlib 行情数据（git 忽略）
├── cache/factors/               # 因子缓存（git 忽略）
├── results/                     # 回测结果（git 忽略）
└── logs/                        # 运行日志（git 忽略）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 准备数据

若 `qlib_data/cn_data/` 已有数据，可跳过或只做增量更新。

**collect_data.py 参数：**

| 参数 | 含义 | 默认 |
|------|------|------|
| `--start` | 开始日期 YYYY-MM-DD | 2020-01-01 |
| `--end` | 结束日期 | 至今 |
| `--max` | 最大下载股票数（测试用） | 全部 |
| `--delay` | 请求间隔（秒） | 0.2 |
| `--index-only` | 只下载指数，不下载股票 | 否 |
| `--no-convert` | 只下载 CSV，不转为 Qlib 二进制 | 否 |
| `--skip-excluded` | 跳过科创板、北交所 | 是 |
| `--with-vwap` | 包含 amount/vwap（预测 VWAP 回测、实盘建议价需此字段） | 是 |
| `--no-vwap` | 不包含 amount/vwap，节省存储；后续可用 update_vwap_data.py 补充 | 否 |

示例：

```bash
# 全量采集 2020 年至今，含 amount/vwap（约数小时）
python scripts/collect_data.py

# 只采集近 2 年
python scripts/collect_data.py --start 2023-01-01

# 测试：只下载前 100 只
python scripts/collect_data.py --start 2023-01-01 --max 100

# 不包含 amount/vwap，后续再补充
python scripts/collect_data.py --start 2023-01-01 --no-vwap
```

**VWAP 说明**：默认 `--with-vwap` 已包含 amount/vwap。若采集时用了 `--no-vwap`，或已有数据缺少该字段，可运行 `update_vwap_data.py` 补充。

### 3. 运行回测

支持参数：`--period`（见 config.PERIODS）、`--start`/`--end`（自定义区间）、`--step`（默认 20）、`--mode`（rolling/static/both）、`--model`（lgb/ensemble）、`--topk`（默认 10）、`--features`（alpha158_only/extra）、`--no-cache`、`--capital`（元，资金约束）。

示例：

```bash
# 默认 2026 周期，滚动训练
python scripts/run_qlib_strategy.py --period 2026 --mode rolling

# 指定周期、TopK=10
python scripts/run_qlib_strategy.py --period 2026-full --mode rolling --topk 10

# 10 万资金约束，模拟小资金实盘
python scripts/run_qlib_strategy.py --period 2026 --mode rolling --capital 100000

# 自定义区间 2025-10-01 ~ 2026-03-11
python scripts/run_qlib_strategy.py --start 2025-10-01 --end 2026-03-11 --mode rolling

# 禁用因子缓存（首次或数据更新后建议）
python scripts/run_qlib_strategy.py --period 2026 --no-cache
```

### 4. 实盘信号

支持参数：`--date`（信号日，默认最新）、`--topk`（默认 10）、`--capital`（总资金，万）、`--auto-best`（按回测选最佳标签，需配合 `--capital`）、`--model`（lgb/ensemble）、`--features`（alpha158_only/extra）、`--no-cache`。

示例：

```bash
# 默认：最新交易日次日 TopK + 建议价（预测 VWAP）
python scripts/run_live_signal.py

# 指定信号日 2026-03-17，10 万资金，按回测选最佳标签
python scripts/run_live_signal.py --date 2026-03-17 --capital 10 --auto-best

# Top15，20 万资金
python scripts/run_live_signal.py --topk 15 --capital 20
```

## 技术方案

### 因子

- **Alpha158**：Qlib 内置 158 个量价技术因子
- **extra**：Alpha158 + 自定义因子（约 200 维）

### 模型

- **LightGBM**：梯度提升树，默认
- **DoubleEnsemble**：`--model ensemble`

### 训练与信号

- **滚动训练**：每 20 个交易日重训，适应市场变化
- **标签**：2日、5日、10日（预测未来 N 日收益）
- **实盘模式**：`--auto-best` 时按近 40 交易日回测收益选最佳标签；否则固定融合 2日×0.5 + 5日×0.3 + 10日×0.2
- **股票过滤**：一字板（买不到）、低流动性、次新股、ST、科创板、北交所

### 选股与成交价

- **TopkDropoutStrategy**：每日持有 TopK，最多替换 n_drop 只
- **成交价**：有 VWAP 数据时用预测 VWAP（与实盘一致），否则用收盘价

### 最新回测（2026-03-17 daily 运行）

| 标签 | 收益 | 回撤 | 超额 |
|------|------|------|------|
| 2日（最佳） | -14.73% | -15.08% | -14.61% |
| 5日 | - | - | - |
| 10日 | - | - | - |

- 区间：2026-01-13 ~ 2026-03-17（近 40 交易日）
- 资金：10 万，TopK=10
- 注：实盘信号当日因「无有效预测」未生成 CSV，可能为末日期特征或过滤导致

## 数据更新

`update_data.py` 支持：`--start`、`--end`（默认近 1 年）、`--max`、`--delay`。若目标结束日期已有数据则跳过下载。

示例：

```bash
# 增量更新近 1 年
python scripts/update_data.py

# 指定时间范围
python scripts/update_data.py --start 2026-03-01 --end 2026-03-17
```

**update_vwap_data.py**：为已有数据补充 amount/vwap（适用于采集时用了 `--no-vwap` 或历史数据缺字段）。参数：`--start`、`--end`、`--max`、`--delay`、`--info-only`（只更新股票信息）。

**check_data.py**：检查数据完整性。参数：`--start`、`--end`（必填）、`--json`。

## 超参优化（预测 VWAP 回测）

以**预测 VWAP 回测收益**为目标优化 Alpha 模型和 VWAP 模型参数，使回测与实盘一致。需先安装：`pip install optuna`。

支持参数：`--period`（默认 2026-full）、`--n-trials`（默认 20）、`--timeout`（秒）、`--features`、`--baseline`（仅跑 baseline）、`--capital`（元，资金约束）。

示例：

```bash
# 20 次试验（每次约 2–5 分钟）
python scripts/optimize_predicted_vwap.py --period 2026-full --n-trials 20

# 10 万资金约束下优化
python scripts/optimize_predicted_vwap.py --period 2026-full --n-trials 20 --capital 100000

# 50 次试验，总超时 2 小时
python scripts/optimize_predicted_vwap.py --period 2026-full --n-trials 50 --timeout 7200
```

最佳参数保存到 `results/optimize_predicted_vwap_best.json`，可手动合并进 `config.py` 和 `vwap_model.py`。

## 每日任务

收盘后自动更新数据并输出次日信号。环境变量：`CAPITAL_WAN`（资金，万，默认 10）。

示例：

```bash
# 默认 10 万资金，回测选最佳标签
./scripts/daily.sh

# 20 万资金
CAPITAL_WAN=20 ./scripts/daily.sh

# 加入 crontab（周一到周五 16:05）
crontab -e
# 添加: 5 16 * * 1-5 /path/to/stock/scripts/daily.sh >> /tmp/stock_daily.log 2>&1
```

流程：1）更新近 3 天数据（若已有则跳过）；2）运行 `run_live_signal.py --no-cache --capital $CAPITAL_WAN --auto-best`。预计 30–50 分钟，日志输出到 `/tmp/stock_daily.log`。
