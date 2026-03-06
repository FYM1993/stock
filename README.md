# A股量化策略框架

基于微软 Qlib 的 A股量化交易框架，智能数据管理，40分钟快速开始。

## 项目特点

- 🆓 **零成本** - 使用 AKShare 免费数据源
- ⚡ **智能管理** - 自动检测数据缺口，按需下载
- 🏭 **工业级** - 基于微软 Qlib 量化平台，成熟稳定
- 🔧 **易扩展** - 模块化设计，轻松实现自定义策略
- 📊 **完整回测** - 考虑交易成本、滑点等真实因素
- 🚀 **开箱即用** - 内置示例策略，立即可用
- 🎯 **智能过滤** - 支持活跃度过滤，节省80%时间
- 📅 **灵活时间** - 自定义回测时间范围

## 内置策略

**龙头低吸策略**（示例）
- 基于市场情绪周期识别龙头股
- 在情绪冰点和技术回调时低吸
- 适合短线波段交易

*可基于此框架实现自己的策略*

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 一键启动（自动询问时间、检测数据、下载补充）
./start.sh
```

**运行流程：**
1. 输入回测时间（如：20240101 ~ 20241231）
2. 自动检测数据完整性
3. 如有缺失，自动下载补充
4. 数据完整后，开始回测

详细说明：
- 完整指南：[QUICKSTART.md](QUICKSTART.md)
- 时间管理：[TIME_MANAGEMENT_GUIDE.md](docs/TIME_MANAGEMENT_GUIDE.md)

## 智能数据管理

**核心优势：**
- ✅ 自定义回测时间范围
- ✅ 自动检测数据缺口
- ✅ 按需下载，不重复
- ✅ 支持后台下载（40分钟）
- ✅ 活跃度过滤（节省80%）

**数据来源：**
- **AKShare**：A股实时数据（免费）
- **价格数据**：开高低收量，前复权
- **情绪数据**：涨跌家数、涨跌停统计

**使用示例：**
```bash
# 方式1：使用 start.sh（推荐）
./start.sh
# → 自动询问时间
# → 自动检测和下载

# 方式2：手动检查数据
python scripts/check_data.py --start 2024-01-01 --end 2024-12-31

# 方式3：手动下载数据
python scripts/update_data.py --auto --start 20240101 --end 20241231
python scripts/download_emotion_data.py --start 2024-01-01 --end 2024-12-31
```

## 项目结构

```
├── data/                    # 数据层
│   ├── akshare_provider.py  # AKShare 数据源
│   ├── emotion_data.py      # 市场情绪统计
│   └── data_converter.py    # 数据格式转换（CSV→二进制）
├── features/                # 特征工程
│   └── leader_features.py   # 龙头股特征计算
├── strategies/              # 策略层
│   └── leader_low_absorption.py  # 龙头低吸策略
├── configs/                 # 配置文件
│   └── strategy_config.yaml # 策略参数（⚠️ 自动更新）
├── scripts/                 # 工具脚本
│   ├── check_data.py        # 数据完整性检查
│   ├── update_data.py       # 下载股票数据（纯下载）
│   ├── download_emotion_data.py  # 下载情绪数据（纯下载）
│   ├── convert_data.py      # 数据格式转换（CSV→二进制）
│   └── run_backtest.py      # 运行回测
├── docs/                    # 文档
├── notebooks/               # Jupyter 分析
├── qlib_data/               # 数据存储（自动创建）
├── logs/                    # 日志目录（自动创建）
├── start.sh                 # 🚀 智能启动脚本（调度器）
└── requirements.txt         # Python 依赖
```

**设计原则**：单一职责
- `update_data.py` → 只负责下载
- `convert_data.py` → 只负责转换  
- `start.sh` → 负责调度和协调

## 自定义策略

1. 在 `strategies/` 创建策略文件
2. 继承 `qlib.strategy.BaseStrategy`
3. 实现 `generate_trade_decision()` 方法
4. 运行 `./start.sh` 选择回测时间
5. 查看回测结果

示例：`strategies/leader_low_absorption.py`

## 技术栈

- **框架**：Qlib (微软开源)
- **数据**：AKShare（A股免费数据）
- **语言**：Python 3.8+
- **依赖**：pandas, numpy, matplotlib, qlib

## 注意事项

⚠️ **股票范围**：
- 包含：主板、中小板、创业板
- 排除：科创板（688）、北交所（8/4开头）

⚠️ **数据说明**：
- 数据源：AKShare（免费）
- 前复权价格数据
- 市场情绪数据（涨跌家数、涨停统计）
- 支持活跃度过滤（节省80%时间）

⚠️ **回测时间**：
- 格式：YYYYMMDD（如 20240101）
- 由 `start.sh` 自动管理
- 配置文件自动更新

⚠️ **风险提示**：
- 历史回测不代表未来
- 实盘前充分测试
- 注意交易成本和滑点

## 相关文档

- [QUICKSTART.md](QUICKSTART.md) - 详细使用指南（含时间管理说明）
- [ACTIVE_FILTER.md](ACTIVE_FILTER.md) - 活跃度过滤说明

## 常用命令

```bash
# 启动（推荐）
./start.sh

# 数据管理
python scripts/check_data.py --start 2024-01-01 --end 2024-12-31  # 检查数据
python scripts/update_data.py --auto --start 20240101 --end 20241231  # 下载价格
python scripts/download_emotion_data.py --start 2024-01-01 --end 2024-12-31  # 下载情绪
python scripts/convert_data.py  # 转换数据为 Qlib 格式

# 手动回测
python scripts/run_backtest.py

# 查看日志
tail -f logs/stock_data.log
tail -f logs/emotion_data.log
```

## FAQ

**Q: 如何修改回测时间？**
A: 运行 `./start.sh`，输入新的时间范围即可。不需要手动修改配置文件。

**Q: 数据下载很慢怎么办？**
A: 启用活跃度过滤（默认开启），节省80%时间；或使用后台下载模式。

**Q: 可以使用其他时间段的数据吗？**
A: 可以！输入任意 YYYYMMDD 格式的日期，系统会自动下载需要的数据。

**Q: 配置文件需要手动改吗？**
A: 不需要！`start.sh` 会自动更新 `configs/strategy_config.yaml`。

---

**🚀 立即开始**：`./start.sh`
