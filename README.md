# A股量化研究项目

基于 Qlib 的 A 股量化研究和回测系统。使用高质量的历史数据进行策略开发和验证。

## 项目结构

```
stock/
├── scripts/                      # 策略和分析脚本
├── qlib_data/cn_data/            # Qlib 数据目录
│   ├── instruments/              # 股票基础数据（CSV格式）
│   ├── features/                 # 特征数据（Qlib bin格式）
│   └── calendars/day.txt         # 交易日历
└── requirements.txt
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 获取数据

使用 [chenditc/investment_data](https://github.com/chenditc/investment_data) 提供的高质量A股数据：

```bash
# 访问 https://github.com/chenditc/investment_data/releases/latest
# 下载最新的 qlib_bin.tar.gz

# 解压到项目目录
tar -zxvf qlib_bin.tar.gz -C ~/GolandProjects/stock/qlib_data/cn_data --strip-components=1
```

**数据特点：**
- ✅ 每日更新（由项目维护者自动发布）
- ✅ 多数据源交叉验证（TuShare, Yahoo等）
- ✅ 包含退市股票数据
- ✅ 覆盖2008年至今的完整历史数据
- ✅ Qlib官方推荐使用

**更新频率建议：**
- 研究和训练：每月更新一次即可
- 如需最新数据：从releases页面下载最新版本

## 数据格式

- **instruments/**：每只股票一个 CSV，字段 `date, open, close, high, low, volume, amount`
- **features/**：Qlib bin 格式，每字段一个 `.day.bin`
- **calendars/day.txt**：交易日历（包含所有交易日）

## 下一步

### 1. 运行量化策略

编辑 `config.yaml` 配置文件，然后运行：

```bash
# 使用默认配置（config.yaml）
python scripts/run_strategy.py

# 使用自定义配置文件
python scripts/run_strategy.py my_config.yaml
```

**配置文件说明（`config.yaml`）：**

```yaml
# 时间配置
segments:
  train: ["2018-01-01", "2022-12-31"]  # 训练集
  valid: ["2023-01-01", "2023-12-31"]  # 验证集
  test:  ["2024-01-01", "2024-12-31"]  # 测试集（回测期）

# 股票池配置
market: "csi300"        # csi300/csi500/csi800/csi1000/all
benchmark: "SH000300"   # 基准指数

# 策略配置
topk: 30               # 持仓数量
n_drop: 5              # 每次最多卖出数量

# 回测配置
account: 1000000       # 初始资金（元）
```

### 2. 策略特点

- ✅ **Alpha158因子集**: 158个技术指标和量价因子
- ✅ **LightGBM模型**: 梯度提升树，适合特征工程
- ✅ **TopkDropout策略**: Top-K选股 + 渐进式调仓
- ✅ **真实交易成本**: 包含手续费、印花税、滑点
- ✅ **涨跌停处理**: 模拟真实市场限制

### 3. 进阶使用

编辑 `config.yaml` 可以：
- 调整训练周期，观察模型稳定性
- 尝试不同股票池（沪深300 vs 中证500）
- 修改LightGBM超参数（learning_rate, max_depth等）
- 调整持仓数量和换手率
- 修改交易成本假设
