# v17完整设计（根据用户细化需求）

## 🎯 市场状态机（3大类 + 震荡细分）

### 1️⃣ 强势市场（STRONG - 牛市）
```
判断依据：
- 指数均线多头排列（MA5 > MA10 > MA20）
- 价格在MA5上方
- 涨停数 >= 50分位

仓位：满仓（100%）
统计起点：指数初次爆量大涨日
买点：追涨、回踩都可以
操作：重仓最强板块最强个股
卖点：板块高潮、跌破五日线
```

### 2️⃣ 震荡市场（OSCILLATE - 需细分）

#### 2A. 震荡-有板块效应（OSCILLATE_SECTOR）
```
判断依据：
- 某个板块龙头连续强势（连续3天以上）
- 板块内个股联动性强

仓位：4层以上（40%+）
统计起点：前龙见顶日
买点：追涨、龙头回踩都可以
操作：重仓板块最强个股
卖点：见好就收，不黏股
```

#### 2B. 震荡-板块轮动（OSCILLATE_ROTATION）
```
判断依据：
- 每天拉不同板块
- 龙头频繁换手
- 第二天就转绿（无持续性）

仓位：2层（20%）
统计起点：前龙见顶日
操作：看哪些板块被轮动到，等板块下去后套利
卖点：快速离场，不黏股
```

### 3️⃣ 弱势市场（WEAK - 熊市）
```
判断依据：
- 指数均线空头排列（MA5 < MA10 < MA20）
- 或 价格跌破MA20
- 或 涨停数 < 25分位

仓位：空仓（0%）
操作：不参与
```

---

## 🔧 实现路线图

### Phase 1（当前）：基础市场状态判断 ✅
- [x] 实现STRONG/OSCILLATE/WEAK三分类
- [x] 状态切换日志
- [ ] 验证状态切换时机是否合理

### Phase 2：震荡市场细分
```python
class MarketRegime:
    STRONG = "strong"                    # 强势市场
    OSCILLATE_SECTOR = "oscillate_sector"  # 震荡-有板块效应
    OSCILLATE_ROTATION = "oscillate_rotation"  # 震荡-板块轮动
    WEAK = "weak"                        # 弱势市场
```

需要实现：
- 板块连续性判断（龙头是否连续强势）
- 板块轮动识别（每天不同板块）

### Phase 3：前龙头跟踪
- 识别当前龙头
- 判断龙头见顶（爆量分歧+持续下跌）
- 记录前龙见顶日

### Phase 4：选股逻辑分支
```python
def _select_stocks(self):
    if self.market_regime == MarketRegime.STRONG:
        # 满仓，找最强板块最强个股
        position_size = 1.0
        return self._find_leader_in_hot_sector()
    
    elif self.market_regime == MarketRegime.OSCILLATE_SECTOR:
        # 4层仓位，重仓板块最强个股
        position_size = 0.4
        return self._find_leader_in_hot_sector()
    
    elif self.market_regime == MarketRegime.OSCILLATE_ROTATION:
        # 2层仓位，套利被轮动的板块
        position_size = 0.2
        return self._find_rotation_arbitrage()
    
    elif self.market_regime == MarketRegime.WEAK:
        # 空仓
        return []
```

### Phase 5：卖出逻辑分支
```python
def _generate_sell_signals(self):
    if self.market_regime == MarketRegime.STRONG:
        # 追求连续性，等板块高潮或龙头跌破五日线
        return self._check_sector_climax_or_break_ma5()
    
    elif self.market_regime in [MarketRegime.OSCILLATE_SECTOR, MarketRegime.OSCILLATE_ROTATION]:
        # 见好就收，不黏股
        if holding_days >= 2 or profit > 0.05:
            return "sell"
        if break_ma5:
            return "sell"
    
    elif self.market_regime == MarketRegime.WEAK:
        # 不应该有持仓
        return "sell_all"
```

---

## 🔍 关键判断逻辑

### 1. 如何区分"有板块效应" vs "板块轮动"？

#### 板块连续性指标
```python
def _check_sector_continuity(self, sector_id, date, window=3):
    """
    检查板块连续性
    
    Args:
        sector_id: 板块ID
        date: 当前日期
        window: 连续天数窗口（默认3天）
    
    Returns:
        True: 板块有连续性（有板块效应）
        False: 板块无连续性（轮动）
    """
    # 检查过去window天，该板块龙头是否持续强势
    # 标准：同一板块龙头连续出现在候选池前列
```

#### 龙头换手率
```python
def _check_leader_turnover_rate(self, window=5):
    """
    检查龙头换手率
    
    Args:
        window: 统计窗口（默认5天）
    
    Returns:
        turnover_rate: 换手率（0-1）
        - 接近1：每天都换龙头（轮动）
        - 接近0：龙头稳定（有板块效应）
    """
    # 统计过去window天，每天的龙头是否相同
```

### 2. 前龙见顶判断

#### 见顶信号
```python
def _check_leader_peak(self, leader_symbol, date):
    """
    判断龙头是否见顶
    
    Args:
        leader_symbol: 龙头股票代码
        date: 当前日期
    
    Returns:
        True: 龙头见顶
        False: 龙头继续强势
    """
    # 1. 爆量分歧：成交量暴增但涨幅不及预期
    volume_spike = self._check_volume_spike(leader_symbol, date)
    price_weakness = self._check_price_weakness(leader_symbol, date)
    
    if volume_spike and price_weakness:
        # 2. 确认下跌：分歧后连续下跌
        is_declining = self._check_consecutive_decline(leader_symbol, date, days=3)
        
        if is_declining:
            return True  # 见顶
    
    return False
```

### 3. 统计起点优先级

#### 强势市场
```python
if self.market_regime == MarketRegime.STRONG:
    # 优先级：指数爆发日
    if self._detect_index_breakout(date):
        self.tracking_start_date = date
        logger.info("📍 指数爆发，重置统计起点")
```

#### 震荡市场
```python
elif self.market_regime.startswith('oscillate'):
    # 优先级1：前龙见顶日
    if self.leader_tracker.leader_peak_date:
        self.tracking_start_date = self.leader_tracker.leader_peak_date
        logger.info("📍 前龙见顶，使用见顶日作为统计起点")
    
    # 优先级2：情绪冰点日
    elif self._timing_signal(date):
        self.tracking_start_date = date
        logger.info("📍 情绪冰点，重置统计起点")
```

---

## 📊 仓位管理矩阵

| 市场状态 | 仓位 | 说明 |
|---------|------|------|
| 强势市场 | 100% | 满仓，重仓最强个股 |
| 震荡-板块效应 | 40%+ | 4层以上，重仓板块最强 |
| 震荡-轮动 | 20% | 2层，套利 |
| 弱势市场 | 0% | 空仓休息 |

---

## 🎯 验证目标

### Phase 1验证（当前）
- [ ] 5-9月牛市期间：应判定为STRONG
- [ ] 其他时期：应合理判定为OSCILLATE或WEAK
- [ ] 状态切换时机是否合理

### Phase 2验证
- [ ] 震荡市场细分是否准确
- [ ] 板块连续性判断是否合理

### Phase 3-5验证
- [ ] 前龙头跟踪是否准确
- [ ] 选股逻辑是否按市场状态分支
- [ ] 仓位管理是否按矩阵执行
- [ ] 最终收益是否提升
