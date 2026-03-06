# v17 市场状态机设计

## 🎯 核心发现

**同一个买点（如情绪冰点），在不同市场环境下操作逻辑完全不同！**

当前v16的致命问题：
- 没有区分市场环境
- 所有情况都用"找未来涨幅最高龙头"的逻辑
- 但震荡市/弱势市的冰点应该是**超跌反弹套利**，不是找新龙头！

---

## 📊 三种市场环境对比

### 1️⃣ 强势市场（牛市）

#### 特征
- 指数上升或企稳
- **主线清晰、龙头明确**
- 成交量持续放大

#### 操作逻辑
- **重仓参与主升**
- 做最强板块的最强个股
- 追求连续性和持续性

#### 统计区间起点
- **第一优先级：指数爆发日**
- 持续有效直到：
  - 大盘量能萎缩
  - 龙头开始缩量筑顶

#### 买点
1. 情绪冰点低吸（找最强板块最强个股）
2. 板块分歧低吸
3. 弱为强之胆买点
4. 板块爆发后第一次回流买点

#### 卖点
- 板块高潮（后排股大涨）
- 中位股亏钱效应扩散
- 板块内大盘股补涨
- 龙头股跌破五日线

---

### 2️⃣ 震荡市场

#### 特征
- 指数稳定，无连续大跌风险
- **市场无主线或同时异动的板块较多**
- 主线不清晰

#### 操作逻辑
- **降低仓位博弈弹性**
- 利用多个热点间的跷跷板效应
- **持仓以隔日超短为主，见好就收**
- 不追求连续性

#### 统计区间起点
**第一优先级：前龙见顶日**
- 判定标准：
  - 爆量分歧后持续下跌
  - 转震荡，继续下跌（震荡下行）
- 见顶后特征：
  - 市场快速轮动（每天拉很多方向）
  - 第二天就转绿/小涨小跌（无持续性）
  - ⚠️ **快速轮动期：不适合操作！等下一个持续性板块**

**第二优先级：情绪冰点日**
- 触发场景：龙头下跌→市场恐慌→板块效应消失
- ⚠️ **操作逻辑特殊**：
  - 博弈的是"前龙头的修复"（超跌反弹）
  - **不是选当天涨幅高的新票！**
  - 套利：前龙头修复后马上卖

#### 买点
1. **情绪冰点低吸**（前龙头修复套利）
2. 个股缩量回踩低吸
3. 盘中分时急跌低吸
4. 尾盘低吸

#### 卖点
- 情绪高潮
- 板块高潮
- 分时急拉均线不跟
- 跌破5日线

#### 注意事项
- 无指数和板块联动，题材股不可重仓
- 弱势环境容易杀尾盘，切不可早盘追高

---

### 3️⃣ 弱势市场（熊市）

#### 特征
- 指数下跌呈空头排列
- 市场无主线板块
- 部分抱团的独立板块和个股无连续性
- 闪崩、补跌、A杀现象频发
- 前一个主线板块处在主跌浪

#### 操作逻辑
- **空仓休息或轻仓试错**
- 轻仓参与冰点后的反弹行情
- 试错提前于指数启动且抗跌的潜在主线板块

#### 买点
- 大票：超跌+止跌信号低吸；冰点日低吸；大阴线次日二次探底低吸
- 小票：情绪冰点低吸；人气股绝对低位低吸

#### 卖点
- 情绪高潮
- 个股大涨
- 跌破五日线或绝对止损点

#### 注意事项
- **只可低吸套利不能格局**
- 不追求持续性
- 绝对低位低吸，**次日兑现，不黏股**
- 盈亏都要快速离场
- 坚决回避突破形态

---

## 🔧 v17需要实现的功能

### 1. 市场状态判断模块
```python
class MarketRegime:
    STRONG = "strong"      # 强势市场
    OSCILLATE = "oscillate"  # 震荡市场
    WEAK = "weak"          # 弱势市场
```

#### 判断逻辑
**强势市场→震荡市场**：
- 大盘量能萎缩
- 龙头开始缩量筑顶
- 主线变得不清晰

**震荡市场→弱势市场**：
- 指数开始空头排列
- 闪崩、补跌频发
- 强势股亏钱效应明显

**弱势市场→强势市场**：
- 指数企稳或上升
- 成交量放大
- 出现清晰主线板块

---

### 2. 前龙头跟踪模块
```python
class LeaderTracker:
    current_leader: str = None      # 当前龙头
    leader_peak_date: str = None    # 龙头见顶日
    leader_status: str = "unknown"  # running/peaking/dead
```

#### 见顶判断
- 爆量分歧（成交量暴增但涨幅不及预期）
- 分歧后持续下跌
- 转震荡，继续下跌

---

### 3. 统计区间起点优先级
```python
def _determine_tracking_start(self):
    if self.market_regime == MarketRegime.STRONG:
        # 优先级1：指数爆发日
        if self._detect_index_breakout():
            return breakout_date
    
    elif self.market_regime == MarketRegime.OSCILLATE:
        # 优先级1：前龙见顶日
        if self.leader_tracker.leader_peak_date:
            return self.leader_tracker.leader_peak_date
        
        # 优先级2：情绪冰点日
        if self._detect_emotion_ice():
            return ice_date
    
    elif self.market_regime == MarketRegime.WEAK:
        # 空仓或轻仓
        pass
```

---

### 4. 选股逻辑分支
```python
def _select_stocks(self):
    if self.market_regime == MarketRegime.STRONG:
        # 找最强板块最强个股（当前逻辑）
        return self._find_leader_in_hot_sector()
    
    elif self.market_regime == MarketRegime.OSCILLATE:
        # 判断是否在快速轮动期
        if self._is_fast_rotation_period():
            logger.info("⚠️ 快速轮动期，不操作")
            return []
        
        # 情绪冰点：前龙头修复套利
        if self._is_ice_point_day():
            return self._find_previous_leader_for_rebound()
        
        # 其他买点：隔日超短
        return self._find_short_term_bounce()
    
    elif self.market_regime == MarketRegime.WEAK:
        # 空仓或轻仓试错
        if self._is_ice_point_day():
            return self._find_oversold_rebound(max_position=0.2)
        return []
```

---

### 5. 卖出逻辑分支
```python
def _generate_sell_signals(self):
    if self.market_regime == MarketRegime.STRONG:
        # 追求连续性，等板块高潮或龙头跌破五日线
        return self._check_sector_climax_or_break_ma5()
    
    elif self.market_regime == MarketRegime.OSCILLATE:
        # 隔日超短，见好就收
        if holding_days >= 2:
            return "sell"  # 不黏股
        if profit > 0.05:
            return "sell"  # 见好就收
        if break_ma5:
            return "sell"
    
    elif self.market_regime == MarketRegime.WEAK:
        # 次日兑现，不黏股
        if holding_days >= 1:
            return "sell"  # 快速离场
```

---

### 6. 仓位管理分支
```python
def _calculate_position_size(self):
    if self.market_regime == MarketRegime.STRONG:
        return 1.0  # 重仓
    elif self.market_regime == MarketRegime.OSCILLATE:
        return 0.5  # 降低仓位
    elif self.market_regime == MarketRegime.WEAK:
        return 0.2  # 轻仓或空仓
```

---

## 🎯 v17实现路线图

### Phase 1: 市场状态判断（基础版）
1. 实现简化版市场状态判断（基于指数MA、成交量、涨停数）
2. 添加状态转换日志
3. 测试状态切换是否合理

### Phase 2: 前龙头跟踪
1. 实现龙头识别和记录
2. 实现见顶判断（爆量分歧+持续下跌）
3. 识别快速轮动期

### Phase 3: 选股逻辑分支
1. 强势市场：保持现有逻辑
2. 震荡市场：实现前龙头修复套利
3. 弱势市场：实现超跌反弹

### Phase 4: 卖出逻辑分支
1. 强势市场：板块高潮+龙头跌破五日线
2. 震荡市场：隔日超短，见好就收
3. 弱势市场：次日兑现，不黏股

### Phase 5: 仓位管理
1. 根据市场状态调整仓位
2. 实现快速轮动期的空仓

---

## 📋 待确认问题

1. **市场状态判断的具体指标**：
   - 强势→震荡：量能萎缩多少算萎缩？
   - 龙头筑顶：连续几天缩量？
   - 震荡→弱势：闪崩如何量化？

2. **前龙见顶的量化标准**：
   - 爆量分歧：量比多少？涨幅不及预期怎么判断？
   - 持续下跌：连续几天？跌幅多少？

3. **快速轮动期的识别**：
   - 如何判断"每天拉很多方向"？
   - 如何判断"无持续性"？

4. **前龙头修复套利的选股**：
   - 是选前一个龙头？还是前几个龙头？
   - 修复的标准是什么（超跌+止跌信号）？

---

## 💭 思考

这个重构的复杂度远超之前所有版本！需要：
- 新增约500-800行代码
- 重构现有选股逻辑
- 重构现有卖出逻辑
- 大量的状态管理和判断

建议分阶段实现，先实现Phase 1（基础的市场状态判断），跑一个回测看看状态切换是否合理，再继续后续功能。

你觉得呢？
