# v15 核心修复：统计区间逻辑

## 🔥 问题根源

### v14的致命错误
```python
# line 139 - 每天都执行这行代码！
self.tracking_start_date = (current_date - pd.Timedelta(days=15)).strftime('%Y-%m-%d')
```

**结果**：
- 每天都重置统计起点
- 统计区间永远只有11-12天
- 真龙头涨幅展现不充分

### 实际数据证明
**新易盛 6月30日**：
```
统计天数：11天（因为每天重置）
累计涨幅：19.0% → 20分
提前启动：5.9% → 10分
量比：1.05 → 0分
总分：30分 → 排名第4（牛市只买Top1，买不到）
```

**如果统计完整周期（30天）**：
```
统计天数：30天
累计涨幅：50%+ → 50分
提前启动：20%+ → 30分
量比：3倍+ → 20分
总分：100分 → 排名Top1 ✅
```

---

## ✅ v15正确逻辑

### 1. 统计区间应该自动增长

**根据`龙头低吸.md`第34行**：
> "择时解决的问题就是区间统计从哪个点开始统计的问题"

**正确理解**：
- 择时信号 → 设置统计起点
- 之后每天 → 区间自动增长
- 新择时出现 → 重置起点

```
Day 1: 择时触发（情绪冰点） → tracking_start_date = 2025-05-01
       统计区间: 2025-05-01 → 2025-05-01 (1天)
       
Day 2: 无择时信号 → tracking_start_date 保持不变
       统计区间: 2025-05-01 → 2025-05-02 (2天)
       
Day 10: 无择时信号 → tracking_start_date 保持不变
        统计区间: 2025-05-01 → 2025-05-10 (10天)
        
Day 30: 无择时信号 → tracking_start_date 保持不变
        统计区间: 2025-05-01 → 2025-05-30 (30天) ← 完整周期！
        
Day 31: 新择时触发（前龙见顶30天重置）→ tracking_start_date = 2025-05-31
        统计区间: 2025-05-31 → 2025-05-31 (1天，重新开始)
```

### 2. 指数择时应该极少触发

**v14错误**：
```python
# 几乎每天都满足！
if pct_change < 0 or abs(pct_change) < 0.5:
    return True
```

**v15正确**：
```python
# 只在大行情启动时触发（如去年5-9月）
# 条件：单日涨幅>3% 且 成交量放大2倍
if pct_change > 3.0 and volume_ratio > 2.0:
    return True
```

**用户说明**：
> "指数择时很少用到的 只有去年这种 大盘上涨到3w亿了 而且3，4月份大盘还是1w亿左右吧 这种大行情才用得到"

### 3. 择时信号优先级

**主要使用**：
- 情绪择时（冰点）：震荡/熊市日常使用
- 前龙见顶（30天重置）：避免统计区间过长

**极少使用**：
- 指数择时：仅在大牛市（成交量3万亿级别）

---

## 📝 代码变更

### 变更1：统计区间逻辑（line 120-138）
```python
# ❌ v14 错误
if market_regime == 'strong':
    lookback_days = 60
elif market_regime == 'weak':
    lookback_days = 20
else:
    lookback_days = 30
self.tracking_start_date = (current_date - pd.Timedelta(days=lookback_days)).strftime('%Y-%m-%d')
# 每天都重置！

# ✅ v15 正确
if has_timing_signal:
    # 择时触发 → 重置起点为今天
    self.tracking_start_date = date_str
    logger.info(f"📍 出现择时信号，重置统计起点: {self.tracking_start_date}")
else:
    # 无择时信号 → 保持原起点，区间自然增长
    if self.tracking_start_date:
        days_diff = (pd.Timestamp(date_str) - pd.Timestamp(self.tracking_start_date)).days
        logger.debug(f"📊 统计区间: {self.tracking_start_date} → {date_str} ({days_diff}天)")
```

### 变更2：指数择时条件（line 230-280）
```python
# ❌ v14 错误（太频繁）
if pct_change < 0 or abs(pct_change) < 0.5:
    return True

# ✅ v15 正确（大行情专用）
index_data = self._get_index_data(date, window=10)
if 'volume' in index_data.columns:
    today_volume = index_data['volume'].iloc[-1]
    avg_volume = index_data['volume'].iloc[-11:-1].mean()
    volume_ratio = today_volume / avg_volume
    
    # 条件：单日涨幅>3% 且 成交量放大2倍以上
    if pct_change > 3.0 and volume_ratio > 2.0:
        logger.info(f"📍 择时信号: 指数大行情启动 (涨幅{pct_change:.2f}%, 量比{volume_ratio:.2f})")
        return True
```

### 变更3：周期重置时间（line 267）
```python
# v14: 15天重置
if days_diff >= 15:

# v15: 30天重置
if days_diff >= 30:
```

---

## 🎯 预期效果

### 回测验证点

1. **统计区间是否自动增长**
   - 查看日志：连续几天无择时信号时，统计天数应该递增
   - 预期：`📊 统计区间: 2025-05-01 → 2025-05-10 (10天)` → 第二天变成11天

2. **真龙头评分是否提高**
   - 查看新易盛5-6月评分
   - 预期：从30-50分 → 提升到70-100分

3. **是否进入Top3**
   - 查看候选池排名
   - 预期：新易盛排名从第4 → Top3

4. **择时触发频率**
   - 统计全年择时信号次数
   - 预期：指数择时<5次（极少），情绪择时10-20次（主要），周期重置若干次

---

## 📊 测试计划

### 测试1：短期回测（5-6月）
```bash
python scripts/run_backtest.py leader_low_absorption --start-date 2025-05-01 --end-date 2025-06-30
```
**验证**：
- 新易盛是否进入Top3
- 统计区间是否正常增长

### 测试2：全年回测
```bash
python scripts/run_backtest.py leader_low_absorption
```
**验证**：
- 全年收益表现
- 择时信号分布
- 真龙头捕获率
