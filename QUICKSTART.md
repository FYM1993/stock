# 快速开始指南

## 🚀 最快开始（推荐）

```bash
./start.sh
```

**运行流程：**
1. 输入回测时间（格式：YYYYMMDD，如 20240101）
2. 自动检测数据完整性
3. 如有缺失，自动下载补充
4. 数据完整后，开始回测

**时间管理说明：**
- 📅 格式：YYYYMMDD（如 20240101 表示 2024年1月1日）
- ✅ 自动检测：脚本会检查数据库中是否有该时间段的数据
- 📊 显示现有数据范围（如：2020-01-01 ~ 2020-09-25）
- ⚠️ 显示缺失数据范围（如需要）
- 💾 按需下载：只下载缺失部分，不重复下载
- ⚙️ 自动配置：回测时间会自动写入 `configs/strategy_config.yaml`

**示例：**
```
回测开始日期 [默认: 20250214]: 20240101
回测结束日期 [默认: 20260214]: 20241231

检查数据完整性...
⚠️  数据不完整
现有数据: 2020-01-01 ~ 2020-09-25
缺失数据: 2024-01-01 ~ 2024-12-31

是否下载缺失的数据？[Y/n]: y
```

---

## 📋 详细步骤

### 一、环境准备

#### 安装依赖

**如果你有 Anaconda（推荐）：**
```bash
cd /Users/yimin.fu/GolandProjects/stock
pip install -r requirements.txt
```

**如果没有 Anaconda：**
```bash
# 1. 创建虚拟环境（可选）
python3 -m venv venv
source venv/bin/activate  # Mac/Linux

# 2. 安装依赖
pip install -r requirements.txt
```

#### 验证安装

```bash
python -c "import qlib, akshare; print('✓ 安装成功')"
```

---

### 二、数据管理

#### 检查数据完整性

```bash
python scripts/check_data.py --start 2024-01-01 --end 2024-12-31
```

**输出示例：**
```
请求时间范围: 2024-01-01 ~ 2024-12-31

【价格数据】
  现有数据: 2020-01-01 ~ 2020-09-25
  股票数量: 981 只
  状态: ✗ 需要补充
    缺失: 2024-01-01 ~ 2024-12-31

【情绪数据】
  状态: ✗ 无数据
```

#### 手动下载数据

**下载股票价格数据：**
```bash
# 指定时间范围
python scripts/update_data.py --auto --start 20240101 --end 20241231

# 最近1年（快速）
python scripts/update_data.py --auto --recent
```

**下载市场情绪数据：**
```bash
# 指定时间范围
python scripts/download_emotion_data.py --start 2024-01-01 --end 2024-12-31

# 最近1年（快速）
python scripts/download_emotion_data.py --recent
```

#### 后台下载

```bash
# 后台下载股票数据
nohup python scripts/update_data.py --auto --start 20240101 --end 20241231 > logs/stock_data.log 2>&1 &

# 后台下载情绪数据
nohup python scripts/download_emotion_data.py --start 2024-01-01 --end 2024-12-31 > logs/emotion_data.log 2>&1 &

# 查看进度
tail -f logs/stock_data.log
```

---

### 三、运行回测

**方式1：使用 start.sh（推荐）**
```bash
./start.sh
# 输入回测时间 → 自动检测 → 下载数据 → 开始回测
```

**方式2：直接运行**
```bash
python scripts/run_backtest.py
# 使用 configs/strategy_config.yaml 中的配置
```

---

## 🎯 常用操作

### 修改回测参数

编辑 `configs/strategy_config.yaml`：

```yaml
strategy:
  topk: 10                    # 龙头候选数量
  max_positions: 3            # 最大持仓数
  position_size: 0.3          # 单只持仓比例
  ice_point_threshold: 1000   # 情绪冰点阈值
  climax_threshold: 3500      # 情绪高潮阈值
```

**注意**：`start_time` 和 `end_time` 会被 `start.sh` 自动更新，无需手动修改。

### 查看回测结果

```bash
# 查看最新结果
ls -lt results/ | head

# 启动 Jupyter 分析
jupyter notebook notebooks/strategy_analysis.ipynb
```

### 常用命令

```bash
# 检查数据
python scripts/check_data.py --start 2024-01-01 --end 2024-12-31

# 下载数据
python scripts/update_data.py --auto --start 20240101 --end 20241231
python scripts/download_emotion_data.py --start 2024-01-01 --end 2024-12-31

# 转换数据
python scripts/convert_data.py

# 运行回测
python scripts/run_backtest.py

# 查看日志
tail -f logs/stock_data.log
```

---

## ❓ 常见问题

### 数据相关

**Q: 如何修改回测时间？**  
A: 运行 `./start.sh`，输入新的时间范围即可。格式：YYYYMMDD（如 20240101）

**Q: 数据下载很慢怎么办？**  
A: 使用后台下载模式（默认启用活跃度过滤，节省80%时间）

**Q: 如何查看下载进度？**  
A: `tail -f logs/stock_data.log` 和 `tail -f logs/emotion_data.log`

**Q: 配置文件需要手动改吗？**  
A: 不需要！`start.sh` 会自动更新 `configs/strategy_config.yaml` 中的回测时间

**Q: 什么是活跃度过滤？**  
A: 只下载成交额前20%的活跃股票，节省约80%时间。详见 [ACTIVE_FILTER.md](ACTIVE_FILTER.md)

**Q: 可以使用任意时间段的数据吗？**  
A: 可以！输入任意 YYYYMMDD 格式的日期，系统会自动下载需要的数据

**Q: 会重复下载已有数据吗？**  
A: 不会。系统会自动检测数据缺口，只下载缺失的部分

---

### 策略相关

**Q: 如何修改策略参数？**  
A: 编辑 `configs/strategy_config.yaml`，然后重新运行回测。

**Q: 如何实现自己的策略？**  
A: 
1. 在 `strategies/` 创建新策略文件
2. 继承 `qlib.strategy.BaseStrategy`
3. 实现 `generate_trade_decision()` 方法
4. 在配置文件中引用

**Q: 回测结果不理想怎么办？**  
A:
1. 检查数据质量和完整性
2. 调整策略参数
3. 优化特征工程
4. 使用 Jupyter 进行详细分析

### 技术问题

**Q: NumPy 兼容性错误？**  
A: 运行 `pip install --force-reinstall --no-cache-dir numexpr bottleneck numpy`

**Q: 权限错误？**  
A: 数据目录使用项目内的 `./qlib_data/`，避免访问系统目录。

**Q: SSL 证书错误？**  
A: 使用 `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org`

---

## 📁 项目结构

```
├── data/          # 数据层：数据源适配、市场情绪统计
├── features/      # 特征工程：因子计算、技术指标
├── strategies/    # 策略层：交易策略实现
├── configs/       # 配置文件：策略参数、回测设置
├── scripts/       # 工具脚本：数据采集、回测执行
├── notebooks/     # Jupyter：策略分析、可视化
└── qlib_data/     # 数据存储（自动创建）
```

---

## 🎓 进阶使用

### 自定义策略开发

1. 在 `strategies/` 创建策略文件
2. 继承 `BaseStrategy` 类
3. 实现核心方法
4. 配置回测参数
5. 运行验证

示例见 `strategies/leader_low_absorption.py`

### 数据分析

使用 Jupyter Notebook 进行深入分析：

```bash
jupyter notebook notebooks/strategy_analysis.ipynb
```

### 性能优化

- 调整回测参数
- 优化特征计算
- 使用并行处理
- 缓存中间结果

---

## 📚 相关文档

- [README.md](README.md) - 项目概述
- [ACTIVE_FILTER.md](ACTIVE_FILTER.md) - 活跃度过滤详解
- [VERSION_HISTORY.md](VERSION_HISTORY.md) - 版本迭代记录
- [Qlib 官方文档](https://qlib.readthedocs.io/)
- [AKShare 文档](https://akshare.akfamily.xyz/)

---

## ⚡ 快速命令参考

```bash
# 一键启动（推荐）
./start.sh

# 补充数据（手动）
python scripts/update_data.py

# 运行回测
python scripts/run_backtest.py

# 每日更新
python scripts/collect_data.py --mode daily

# 启动 Jupyter
jupyter notebook

# 查看帮助
./HELP.sh
```

---

## 🎉 开始使用

```bash
./start.sh
```

智能判断，自动引导！
