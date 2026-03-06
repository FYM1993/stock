# v18 开发完整总结

## 时间线
2026-03-05

## 问题背景
v17使用动态板块聚类识别热点，导致38.6%的板块识别失败率，是造成策略失败的根本原因。

## v18 改进目标
**核心**：放弃动态聚类，改用静态行业分类

## 实施过程

### Phase 1: 静态行业分类架构 ✅
**时间**: 10:00 - 10:05

**改动**：
1. 修改`__init__`加载行业映射文件 `data/stock_industry_mapping.json`
2. 新增`_load_industry_mapping()` 方法
3. 新增`_get_stock_industry(symbol)` 方法
4. 重写`_identify_hot_sectors()` 改用静态行业

**文件**：
- `strategies/leader_low_absorption.py` (修改)
- `results/v18_phase1_monitoring.md` (文档)

### Phase 2: 简化市场状态判定 ✅
**时间**: 10:05 - 10:15

**改动**：
1. `MarketRegime` 从4状态简化为3状态
   - `STRONG`: 强势市场（牛市）
   - `OSCILLATE`: 震荡市场
   - `WEAK`: 弱势市场（熊市）
2. 重写`_detect_market_regime()` 简化判断逻辑
3. 删除`_check_sector_continuity()` 方法
4. 更新`_generate_buy_orders()` 仓位逻辑：
   - STRONG: 1只100%
   - OSCILLATE: 2只40%
   - WEAK: 空仓
5. 更新`_check_sell_signal()` 卖出条件

**文件**：
- `strategies/leader_low_absorption.py` (修改)
- `results/v18_phase2_complete.md` (文档)

### Phase 3: 优化买入信号优先级 ✅
**时间**: 10:15 - 10:20

**改动**：
1. 重写`_check_all_buy_signals()` 修复bug（该方法被误替换为卖出逻辑）
2. 实现不同市场状态的买入信号优先级：
   - **STRONG**: 追涨龙头(100), 板块突破(90), 均线突破(80)
   - **OSCILLATE**: 冰点低吸(100), 回踩买入(90), 板块突破(80), 放量回踩(70)
   - **WEAK**: 无信号
3. 新增`_check_sector_breakout()` 方法（板块突破信号）
4. 新增`_check_pullback_signal()` 方法（回踩买入信号）

**文件**:
- `strategies/leader_low_absorption.py` (修改)
- `results/v18_phase3_complete.md` (文档)

### Phase 4: 行业数据准备 ✅
**时间**: 10:20 - 10:35

**挑战**：
- AKShare API 100%失败（网络问题）
- Tushare免费接口也无法连接

**解决方案**：
采用**临时方案**：基于股票代码规则推断行业
- 688开头 → 科技创新
- 300开头 → 成长企业
- 600开头 → 传统行业
- 601开头 → 金融能源
- 603开头 → 制造业
- 000开头 → 深市主板
- 002开头 → 中小企业

**数据质量**：
- ✅ 覆盖全部2670只股票
- ⚠️ 仅16个粗糙分类
- ⚠️ 按板块而非真实行业

**文件**：
- `scripts/build_simple_industry_mapping.py` (新增)
- `data/stock_industry_mapping.json` (2670条记录)
- `results/v18_phase4_temp_data.md` (文档)

### Phase 5: Bug修复与回测启动 ✅
**时间**: 10:35 - 10:43

**Bug**：
- `get_limit_down_percentile` 方法不存在
- **修复**: 改用 `limit_up_percentile < 0.3` 判断市场弱势

**回测启动**：
```bash
python scripts/run_backtest.py \
  --strategy leader_low_absorption \
  --start-date 2025-05-01 \
  --end-date 2026-02-14 \
  --market csi300 \
  --version v18
```

## 代码统计

### 核心修改
- `strategies/leader_low_absorption.py`: ~200行代码变更
  - 新增: `_load_industry_mapping`, `_get_stock_industry`, `_check_sector_breakout`, `_check_pullback_signal`
  - 重写: `_identify_hot_sectors`, `_detect_market_regime`, `_check_all_buy_signals`
  - 删除: `_check_sector_continuity`

### 新增文件
- `scripts/build_simple_industry_mapping.py` (169行)
- `data/stock_industry_mapping.json` (2670条记录)
- 文档4份

## v18 架构

```
策略流程
├── 1. 市场状态判定 (_detect_market_regime)
│   ├── 强势: MA多头 + 价格强 + 情绪好 + 热点持续
│   ├── 弱势: MA空头 OR 跌破MA20 OR 情绪差 OR 无热点
│   └── 震荡: 有热点但未达强势标准
│
├── 2. 热点板块识别 (_identify_hot_sectors)
│   ├── 从static映射获取股票行业
│   ├── 按行业聚合涨幅前100股票
│   ├── 筛选: 平均涨幅>15%, 股票数>=3, 强势股>=2
│   └── 返回: {行业名: {stocks: [...], avg_return: 0.2, ...}}
│
├── 3. 龙头候选 (_update_leader_candidates)
│   ├── 热点板块内筛选
│   └── 3维度评分: 涨幅(40%) + 早启(30%) + 极端量(30%)
│
└── 4. 交易决策
    ├── 买入信号 (_check_all_buy_signals)
    │   ├── STRONG: 追涨(100), 板块突破(90), 均线突破(80)
    │   └── OSCILLATE: 冰点(100), 回踩(90), 板块突破(80), 放量回踩(70)
    │
    ├── 卖出信号 (_check_sell_signal)
    │   ├── WEAK: 立即退出
    │   ├── OSCILLATE: 5%止盈, 破MA5, 8%止损, 板块高潮
    │   └── STRONG: 30%止盈, 破MA5, 10%回撤止损, 板块高潮
    │
    └── 仓位管理
        ├── STRONG: 1只100%
        ├── OSCILLATE: 2只40%
        └── WEAK: 空仓
```

## v17 vs v18 对比

| 维度 | v17 | v18 |
|-----|-----|-----|
| **板块识别** | 动态聚类（失败率38.6%） | 静态行业（临时粗糙分类） |
| **市场状态** | 4状态（STRONG, OSC_SECTOR, OSC_ROTATION, WEAK） | 3状态（STRONG, OSCILLATE, WEAK） |
| **仓位管理** | 复杂（100%/50%/20%/0%） | 简化（100%/40%/0%） |
| **买入信号** | 单一优先级 | 差异化优先级（STRONG追涨，OSCILLATE低吸） |
| **代码行数** | 1755行 | 1755行（结构更清晰） |

## 预期效果

### 优点
✅ 板块识别稳定（100%覆盖）  
✅ 市场状态判定简化  
✅ 买入信号更合理  

### 局限
⚠️ 行业分类粗糙（仅16类）  
⚠️ "板块效应"模糊化  
⚠️ 可能影响策略准确度  

### 验证目标
1. 代码逻辑是否正确（无bug）
2. 主升期（5-9月）表现如何
3. 与v17对比收益率

## 后续优化
1. **夜间重试** AKShare/Tushare API获取真实行业数据
2. **手动导入** 申万行业CSV数据
3. **Tushare Pro** 注册token使用Pro接口
4. **动态+静态混合** 在静态行业基础上做动态关联分析

## 当前状态
✅ v18 Phase 1-5 完成  
🔄 回测进行中（2025-05 ~ 2026-02）  
⏳ 等待回测结果  
