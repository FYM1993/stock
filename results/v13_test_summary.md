# v13测试总结（2026-02-25）

## 测试目标
验证新增的动态热点板块识别和龙头选股逻辑

## 主要问题与修复历程

### 问题1：板块识别始终失败
**表现：** 所有回测日志显示"未识别到热点板块，回退到全市场选股"

**根本原因：**
1. `tracking_start_date`每天都被重置为当天（line 126：`self.tracking_start_date = date_str`）
2. 导致统计区间只有1天，无法计算收益率
3. 板块识别的涨幅阈值太高（15%）

**修复历程：**
- **v13.1-13.2**: 发现`tracking_start_date`重置问题
- **v13.3**: 改为固定15天回溯期：`self.tracking_start_date = (current_date - pd.Timedelta(days=15)).strftime('%Y-%m-%d')`
- **v13.4**: 发现Qlib返回2636只股票，但2398只被过滤（数据不足5天）
- **v13.5**: 降低数据要求到3天，仍然失败（收益率不足）
- **v13.6**: 降低到2天，**终于成功**！

### 问题2：回测中途中断
**表现：** v13测试只跑到20%（4月29日）就停止

**原因：** 未确定（可能是数据问题或Qlib内部错误），在v13.6修复板块识别后未再出现

## v13.6 测试结果（2025-05-01至2025-05-31）

### 板块识别效果
```
板块识别成功: 15次
板块识别失败: 6次
成功率: 71.4%
```

**成功识别示例：**
```
sector_0: 9只股票, 平均涨幅10.4%
sector_1: 18只股票, 平均涨幅14.6%
sector_2: 14只股票, 平均涨幅9.0%
```

### 交易情况
```
买入信号: 3次
卖出信号: 0次
```
⚠️ **交易次数偏少**，可能原因：
1. 5月数据可能不完整（需检查）
2. 择时信号太严格
3. 买点条件太苛刻

## 关键代码修改

### 1. 固定统计回溯期（line 124-134）
```python
# 修改前：每次择时信号就重置
if self._timing_signal(date_str):
    self.tracking_start_date = date_str
    
# 修改后：固定15天回溯
has_timing_signal = self._timing_signal(date_str)
lookback_days = 15
current_date = pd.Timestamp(date_str)
self.tracking_start_date = (current_date - pd.Timedelta(days=lookback_days)).strftime('%Y-%m-%d')
```

### 2. 降低数据点要求（line 408-424）
```python
# 修改前：至少5个数据点
if len(stock_data) < 5:
    continue
if len(returns) >= 5:
    returns_dict[symbol] = returns
    
# 修改后：至少2个数据点
if len(stock_data) < 2:
    continue
if len(returns) >= 2:
    returns_dict[symbol] = returns
```

### 3. 动态涨幅阈值（line 445-456）
```python
# 修改前：固定15%阈值
if avg_return > 15:

# 修改后：根据统计周期动态调整
days = max(1, (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days)
if days <= 5:
    threshold = 3
elif days <= 10:
    threshold = 5
else:
    threshold = 8
    
if avg_return > threshold:
```

## 下一步计划

1. ✅ **板块识别已修复** - v13.6成功识别热点板块
2. ⚠️ **需要调查交易次数少的原因**
   - 检查5月数据完整性
   - 审查择时和买点逻辑是否过于严格
3. 📊 **需要完整回测**
   - 完整跑2025-05至2025-09（5个月）
   - 对比v11的+63.89%收益
   - 验证是否能选中真龙头（中际旭创、新易盛等）
