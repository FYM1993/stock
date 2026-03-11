# A股量化选股系统

基于 Qlib + LightGBM 的 A股量化选股回测系统。用 Alpha158 量价因子训练机器学习模型，预测股票未来收益，按排名选股持有。

数据源使用 [adata](https://github.com/1nchaos/adata)，多数据源融合，比 akshare 更稳定。

## 最新回测结果 (2025-05 ~ 2025-08)

| 方案 | 总收益 | 年化 | 最大回撤 | 夏普 | 超额(vs沪深300) |
|------|:------:|:----:|:-------:|:----:|:--------------:|
| **2日标签+Top10** | **+25.84%** | +100.9% | -2.94% | 5.95 | **+6.58%** |
| 5日标签+Top10 | +22.77% | +86.4% | -2.65% | 5.84 | +3.51% |
| 2日标签+Top30 | +17.65% | +63.8% | -2.10% | 4.78 | -1.61% |

## 项目结构

```
stock/
├── scripts/
│   ├── run_qlib_strategy.py      # 核心回测脚本（因子+模型+回测）
│   ├── collect_data.py           # 采集全量数据（adata → Qlib格式）
│   ├── update_data.py            # 增量更新数据
│   └── check_data.py             # 数据完整性检查
├── data/
│   ├── adata_provider.py         # adata数据接口封装
│   └── data_converter.py         # CSV → Qlib二进制格式转换
├── qlib_data/cn_data/            # Qlib行情数据（git忽略）
├── results/                      # 回测结果（git忽略）
└── logs/                         # 运行日志（git忽略）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 准备数据

如果 `qlib_data/cn_data/` 已有数据，跳过此步。否则：

```bash
# 全量采集（2020年至今，约需数小时）
python scripts/collect_data.py

# 或只采集近2年（更快）
python scripts/collect_data.py --start 2023-01-01

# 或先测试100只股票
python scripts/collect_data.py --start 2023-01-01 --max 100
```

### 3. 运行回测

```bash
python scripts/run_qlib_strategy.py
```

自动完成：因子计算 → 模型训练 → 多方案回测对比 → 输出最优结果。

## 技术方案

### 因子

Alpha158：Qlib 内置的 158 个量价技术因子，覆盖 K线形态、动量/反转、波动率、量价关系等。

### 模型

LightGBM 梯度提升树：
- 标签：未来2日收益率（cross-sectional rank normalized）
- 训练期：2023-01 ~ 2025-03（2年3个月）
- 验证期：2025-04（1个月，用于 early stopping）
- 测试期：2025-05 ~ 2025-08（4个月）

### 选股

TopkDropoutStrategy：
- 每日按模型预测分数排名，持有 Top10
- 每日最多替换 2 只（n_drop=2），减少换手
- 交易成本：买入万五，卖出千一点五

## 数据更新

```bash
# 增量更新（默认近1年）
python scripts/update_data.py

# 指定时间范围
python scripts/update_data.py --start 2025-01-01

# 检查数据完整性
python scripts/check_data.py
```
