"""
龙头低吸策略 - 基于 Qlib 策略框架

实现"龙头低吸"的核心交易逻辑：
1. 市场环境判断（强势/震荡/弱势）
2. 龙头股识别
3. 买入信号识别（情绪冰点、板块分歧、技术回调）
4. 卖出信号识别（板块高潮、跌破均线）
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from loguru import logger
from datetime import datetime

from qlib.strategy.base import BaseStrategy
from qlib.backtest import Order
from qlib.backtest.decision import OrderDir, TradeDecisionWO
from qlib.data import D

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from data.emotion_data import EmotionDataManager

# v18: 添加AKShare支持
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    logger.warning("AKShare未安装，将使用动态相关性识别板块")


class MarketRegime:
    """市场状态枚举（v18简化版）"""
    STRONG = "strong"      # 强势市场（牛市）：满仓龙头
    OSCILLATE = "oscillate"  # 震荡市场：2只40%
    WEAK = "weak"          # 弱势市场（熊市）：空仓


class LeaderTracker:
    """前龙头跟踪器"""
    
    def __init__(self):
        self.current_leader = None        # 当前龙头股票代码
        self.current_leader_sector = None # 当前龙头所属板块
        self.leader_start_date = None     # 龙头启动日期
        self.leader_peak_date = None      # 龙头见顶日期
        self.leader_status = "unknown"    # running/peaking/dead
        
        # 龙头历史价格和成交量（用于判断见顶）
        self.leader_price_history = {}    # {date: price}
        self.leader_volume_history = {}   # {date: volume}


class LeaderLowAbsorptionStrategy(BaseStrategy):
    """龙头低吸策略"""
    
    def __init__(
        self,
        topk: int = 10,  # 龙头候选数量
        max_positions: int = 3,  # 最大持仓数
        position_size: float = 0.3,  # 单只持仓比例
        ice_point_percentile: float = 0.2,  # 冰点百分位阈值
        climax_percentile: float = 0.8,  # 高潮百分位阈值
        emotion_lookback_days: int = 60,  # 情绪回溯天数
        ma_period: int = 5,  # 均线周期
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self.topk = topk
        self.max_positions = max_positions
        self.position_size = position_size
        self.ice_point_percentile = ice_point_percentile
        self.climax_percentile = climax_percentile
        self.emotion_lookback_days = emotion_lookback_days
        self.ma_period = ma_period
        
        # 初始化情绪数据管理器
        self.emotion_manager = EmotionDataManager()
        
        # 追踪统计区间起点
        self.tracking_start_date = None
        
        # 龙头候选池
        self.leader_candidates = []
        
        # 动态热点板块（每个统计周期重新识别）
        # 格式：{sector_id: {'stocks': [symbols], 'avg_return': float, 'strength': float}}
        self.hot_sectors = {}
        
        # v18: 加载股票-行业映射（静态数据）
        self.stock_industry_mapping = self._load_industry_mapping()
        logger.info(f"v18: 加载行业映射 {len(self.stock_industry_mapping)} 只股票")
        
        # 市场状态跟踪
        self.market_regime = MarketRegime.OSCILLATE  # v18: 初始假设震荡
        self.regime_change_date = None  # 状态切换日期
        
        # 历史龙头跟踪（用于判断板块连续性）
        # 格式：{date: {'leader': symbol, 'sector': sector_name, 'score': float}}
        self.leader_history = {}
        
        # 前龙头跟踪器（用于判断龙头见顶和统计起点）
        self.leader_tracker = LeaderTracker()
        
        logger.info(f"策略初始化: topk={topk}, max_positions={max_positions}, "
                   f"position_size={position_size}, ice_point_percentile={ice_point_percentile}, "
                   f"climax_percentile={climax_percentile}")
    
    def _load_industry_mapping(self) -> dict:
        """
        v18: 加载股票-行业映射数据
        
        Returns:
            {股票代码: 行业名称} 字典
        """
        import json
        from pathlib import Path
        
        # 映射文件路径
        mapping_file = Path(__file__).parent.parent / "data" / "stock_industry_mapping.json"
        
        if not mapping_file.exists():
            logger.warning(f"v18: 行业映射文件不存在: {mapping_file}")
            return {}
        
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            logger.info(f"v18: 成功加载行业映射文件，包含 {len(mapping)} 只股票")
            return mapping
        except Exception as e:
            logger.error(f"v18: 加载行业映射失败: {e}")
            return {}
    
    def _get_stock_industry(self, symbol: str) -> Optional[str]:
        """
        v18: 获取股票所属行业
        
        Args:
            symbol: 股票代码，如 "300502.SZ"
            
        Returns:
            行业名称，如 "通信设备"，未找到返回 None
        """
        industry_info = self.stock_industry_mapping.get(symbol)
        if industry_info and isinstance(industry_info, dict):
            return industry_info.get('ind_name')
        return None
    
    def generate_trade_decision(
        self, 
        execute_result: Optional[List] = None
    ) -> List[Order]:
        """
        生成交易决策（Qlib 核心接口）- 增强风控版本
        
        Args:
            execute_result: 上一次交易执行结果
            
        Returns:
            订单列表
        """
        # 获取当前交易日期
        trade_step = self.trade_calendar.get_trade_step()
        current_date = self.trade_calendar.get_step_time(trade_step)
        # current_date 是 (start, end) 的元组，取开始时间
        if isinstance(current_date, tuple):
            current_date = current_date[0]
        date_str = pd.Timestamp(current_date).strftime('%Y-%m-%d')
        
        logger.info(f"\n{'='*60}")
        logger.info(f"日期: {date_str}")
        
        # ✅ 从trade_position获取当前持仓和资金状态
        current_positions = {}
        current_cash = 100000  # 默认初始资金
        total_value = 100000
        
        if hasattr(self, 'trade_position') and self.trade_position is not None:
            position_dict = dict(self.trade_position.position)
            current_cash = position_dict.get('cash', 100000)
            total_value = position_dict.get('now_account_value', 100000)
            
            # 提取股票持仓
            for key, value in position_dict.items():
                if key not in ['cash', 'now_account_value'] and isinstance(value, dict):
                    # value是股票持仓信息：{'amount': xxx, 'price': xxx, ...}
                    current_positions[key] = value.get('amount', 0)
        
        # 风控信息
        position_count = len([v for v in current_positions.values() if v > 0])
        used_cash_rate = 1 - (current_cash / total_value) if total_value > 0 else 1.0
        
        logger.info(f"💰 资金状态: 可用={current_cash:,.0f}, 总值={total_value:,.0f}, "
                   f"仓位={used_cash_rate*100:.1f}%, 持股={position_count}只")
        
        # 1. 判断市场环境并更新状态
        new_regime = self._detect_market_regime(date_str)
        if new_regime != self.market_regime:
            old_regime = self.market_regime
            self.market_regime = new_regime
            self.regime_change_date = date_str
            logger.info(f"🔄 市场状态切换: {old_regime} → {new_regime} (日期: {date_str})")
        else:
            logger.info(f"📊 市场状态: {self.market_regime}")
        
        # 2. 择时：判断是否有入场时机信号
        has_timing_signal = self._timing_signal(date_str)
        
        # 3. 设置统计区间：只在择时信号触发时重置起点，否则自然增长
        if has_timing_signal:
            # 择时触发 → 重置统计起点为今天
            self.tracking_start_date = date_str
            logger.info(f"📍 出现择时信号，重置统计起点: {self.tracking_start_date}")
        else:
            # 无择时信号 → 保持原起点，统计区间自然增长
            if self.tracking_start_date:
                days_diff = (pd.Timestamp(date_str) - pd.Timestamp(self.tracking_start_date)).days
                logger.debug(f"📊 统计区间: {self.tracking_start_date} → {date_str} ({days_diff}天)")
        
        # 4. 选股：更新龙头候选池
        if self.tracking_start_date:
            self._update_leader_candidates(date_str)
        
        # 5. 更新前龙头跟踪器（检查龙头见顶）
        self._update_leader_tracker(date_str)
        
        # 6. 生成订单
        orders = []
        
        # 4.1 卖出逻辑（先卖后买，释放资金）
        sell_orders = self._generate_sell_orders(date_str, self.market_regime, current_positions)
        orders.extend(sell_orders)
        
        # 4.2 买入逻辑（增加资金检查）
        buy_orders = self._generate_buy_orders(date_str, self.market_regime, current_positions,
                                               current_cash, total_value)
        orders.extend(buy_orders)
        
        logger.info(f"生成订单数: {len(orders)} (买入: {len(buy_orders)}, 卖出: {len(sell_orders)})")
        
        # 🐛 调试：打印订单详情
        if len(orders) > 0:
            for i, order in enumerate(orders[:3]):  # 只打印前3个
                logger.debug(f"订单{i+1}: {order.stock_id}, 方向={order.direction}, "
                           f"金额={order.amount}, 时间={order.start_time}")
        
        # 返回TradeDecisionWO对象
        return TradeDecisionWO(orders, self)
    
    def _detect_market_regime(self, date: str) -> str:
        """
        v18: 识别市场环境（简化版）
        
        3种状态：
        1. 强势市场（STRONG）：均线多头 + 价格强势 + 情绪好 + 热点持续
        2. 震荡市场（OSCILLATE）：有热点板块，但不满足强势条件
        3. 弱势市场（WEAK）：无热点或情绪极差
        
        Returns:
            MarketRegime.STRONG / OSCILLATE / WEAK
        """
        # 获取指数数据（上证指数）
        index_symbol = '000001.SH'
        try:
            # 获取最近30天数据（计算MA20需要）
            end_date = pd.Timestamp(date)
            start_date = end_date - pd.Timedelta(days=40)
            
            index_df = D.features(
                [index_symbol],
                ['$close', '$volume'],
                start_time=start_date.strftime('%Y-%m-%d'),
                end_time=date,
                freq='day'
            )
            
            if index_df.empty or len(index_df) < 20:
                logger.warning(f"v18: 指数数据不足，默认判定为震荡")
                return MarketRegime.OSCILLATE
            
            # 计算均线
            close = index_df['$close']
            ma5 = close.rolling(5).mean().iloc[-1]
            ma10 = close.rolling(10).mean().iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]
            ma60 = close.rolling(min(60, len(close))).mean().iloc[-1] if len(close) >= 20 else ma20
            current_close = close.iloc[-1]
            
            # 获取涨停数百分位（用于判断情绪）
            limit_up_percentile = self.emotion_manager.get_limit_up_percentile(date, 60)
            
            # 计算成交量变化
            volume = index_df['$volume']
            avg_volume_10 = volume.rolling(10).mean().iloc[-1]
            current_volume = volume.iloc[-1]
            volume_ratio = current_volume / avg_volume_10 if avg_volume_10 > 0 else 1.0
            
            # 输出详细判断信息
            logger.debug(f"v18: 市场状态判定")
            logger.debug(f"  均线: MA5={ma5:.2f}, MA10={ma10:.2f}, MA20={ma20:.2f}, 当前={current_close:.2f}")
            logger.debug(f"  涨停数百分位={limit_up_percentile:.2%}")
            logger.debug(f"  成交量比={volume_ratio:.2f}x")
            
            # 判断逻辑
            is_ma_bullish = (ma5 > ma10 > ma20)
            is_price_strong = (current_close > ma5)
            is_emotion_good = (limit_up_percentile >= 0.5) if limit_up_percentile is not None else False
            is_emotion_bad = (limit_up_percentile < 0.3) if limit_up_percentile is not None else False  # 涨停数很少=市场弱
            
            # 检查热点板块情况
            has_hot_sectors = len(self.hot_sectors) > 0
            
            # 检查热点持续性（过去3天的龙头历史）
            hot_sector_continuous = False
            if has_hot_sectors:
                # 简单检查：过去3天是否有热点记录
                check_dates = []
                for i in range(1, 4):
                    check_date = (end_date - pd.Timedelta(days=i)).strftime('%Y-%m-%d')
                    check_dates.append(check_date)
                
                continuous_count = sum(1 for d in check_dates if d in self.leader_history)
                hot_sector_continuous = (continuous_count >= 2)  # 3天中有2天以上有龙头
            
            logger.debug(f"  均线多头={is_ma_bullish}, 价格强势={is_price_strong}, 情绪好={is_emotion_good}")
            logger.debug(f"  有热点={has_hot_sectors}, 热点持续={hot_sector_continuous}")
            
            # 1. 弱势市场：优先判断（避免在弱势中乱买）
            is_ma_bearish = (ma5 < ma10 < ma20)
            is_price_very_weak = (current_close < ma20)
            
            if is_ma_bearish or is_price_very_weak or is_emotion_bad or not has_hot_sectors:
                reasons = []
                if is_ma_bearish:
                    reasons.append("均线空头")
                if is_price_very_weak:
                    reasons.append("跌破MA20")
                if is_emotion_bad:
                    reasons.append("跌停数多")
                if not has_hot_sectors:
                    reasons.append("无热点板块")
                logger.info(f"  → 弱势市场（{'+'.join(reasons)}）")
                return MarketRegime.WEAK
            
            # 2. 强势市场：严格判断（确保是真牛市）
            if (is_ma_bullish and is_price_strong and is_emotion_good and 
                has_hot_sectors and hot_sector_continuous):
                logger.info(f"  → 强势市场（均线多头+价格强+情绪好+热点持续）")
                return MarketRegime.STRONG
            
            # 3. 震荡市场：有热点但不满足强势条件
            if has_hot_sectors:
                logger.info(f"  → 震荡市场（有热点，但未达强势标准）")
                return MarketRegime.OSCILLATE
            
            # 默认：震荡
            logger.info(f"  → 震荡市场（默认）")
            return MarketRegime.OSCILLATE
            
        except Exception as e:
            logger.error(f"v18: 市场状态判断异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return MarketRegime.OSCILLATE
    
    def _update_leader_tracker(self, date: str):
        """
        更新前龙头跟踪器
        
        逻辑：
        1. 更新当前龙头
        2. 记录龙头价格和成交量历史
        3. 检查龙头是否见顶
        """
        try:
            # 如果没有候选龙头，清空跟踪器
            if not self.leader_candidates:
                return
            
            current_top_leader = self.leader_candidates[0]
            # v18: 使用行业映射获取板块
            current_sector = self._get_stock_industry(current_top_leader)
            
            # 获取当前龙头的价格和成交量
            stock_data = self._get_stock_data(current_top_leader, date, window=1)
            if stock_data is None or len(stock_data) == 0:
                return
            
            current_price = stock_data['close'].iloc[-1]
            current_volume = stock_data['volume'].iloc[-1]
            
            # 记录历史
            self.leader_tracker.leader_price_history[date] = current_price
            self.leader_tracker.leader_volume_history[date] = current_volume
            
            # 判断是否是新龙头（更换龙头）
            if self.leader_tracker.current_leader != current_top_leader:
                old_leader = self.leader_tracker.current_leader
                
                # 如果有旧龙头，检查旧龙头是否见顶
                if old_leader and self.leader_tracker.leader_status == "running":
                    is_peaked = self._check_leader_peak(old_leader, date)
                    if is_peaked:
                        self.leader_tracker.leader_peak_date = date
                        self.leader_tracker.leader_status = "dead"
                        logger.info(f"🔴 前龙见顶: {old_leader} (见顶日: {date})")
                
                # 更新为新龙头
                self.leader_tracker.current_leader = current_top_leader
                self.leader_tracker.current_leader_sector = current_sector
                self.leader_tracker.leader_start_date = date
                self.leader_tracker.leader_status = "running"
                
                logger.info(f"🔄 龙头切换: {old_leader} → {current_top_leader} (板块: {current_sector})")
            
            # 如果是当前龙头，检查是否正在见顶
            else:
                if self.leader_tracker.leader_status == "running":
                    is_peaking = self._check_leader_peaking(current_top_leader, date)
                    if is_peaking:
                        self.leader_tracker.leader_status = "peaking"
                        logger.warning(f"⚠️ 龙头疑似见顶: {current_top_leader}")
                
                elif self.leader_tracker.leader_status == "peaking":
                    # 检查是否确认见顶
                    is_peaked = self._check_leader_peak(current_top_leader, date)
                    if is_peaked:
                        self.leader_tracker.leader_peak_date = date
                        self.leader_tracker.leader_status = "dead"
                        logger.info(f"🔴 龙头确认见顶: {current_top_leader} (见顶日: {date})")
        
        except Exception as e:
            logger.error(f"更新龙头跟踪器异常: {e}")
    
    def _check_leader_peaking(self, symbol: str, date: str) -> bool:
        """
        检查龙头是否正在见顶（疑似见顶）
        
        见顶信号1：爆量分歧
        - 成交量暴增（>1.5倍近期平均）
        - 但涨幅不及预期（<3%）或开始下跌
        
        Args:
            symbol: 龙头股票代码
            date: 当前日期
        
        Returns:
            True: 疑似见顶
            False: 继续强势
        """
        try:
            # 获取最近5天数据
            stock_data = self._get_stock_data(symbol, date, window=5)
            if stock_data is None or len(stock_data) < 2:
                return False
            
            # 今日数据
            today_close = stock_data['close'].iloc[-1]
            today_volume = stock_data['volume'].iloc[-1]
            yesterday_close = stock_data['close'].iloc[-2]
            
            # 涨幅
            pct_change = ((today_close - yesterday_close) / yesterday_close) * 100
            
            # 成交量比（今日vs前4天平均）
            avg_volume = stock_data['volume'].iloc[:-1].mean()
            volume_ratio = today_volume / avg_volume if avg_volume > 0 else 1.0
            
            # 判断：爆量分歧（量增价不增或下跌）
            is_volume_spike = (volume_ratio > 1.5)
            is_price_weak = (pct_change < 3.0)  # 涨幅<3%视为弱势
            
            if is_volume_spike and is_price_weak:
                logger.debug(f"  {symbol} 爆量分歧: 量比={volume_ratio:.2f}x, 涨幅={pct_change:.2f}%")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查龙头见顶信号异常: {e}")
            return False
    
    def _check_leader_peak(self, symbol: str, date: str) -> bool:
        """
        检查龙头是否确认见顶
        
        确认见顶标准：
        1. 出现爆量分歧后
        2. 连续下跌3天 或 跌破5日均线
        
        Args:
            symbol: 龙头股票代码
            date: 当前日期
        
        Returns:
            True: 确认见顶
            False: 尚未见顶
        """
        try:
            # 获取最近5天数据
            stock_data = self._get_stock_data(symbol, date, window=5)
            if stock_data is None or len(stock_data) < 5:
                return False
            
            # 检查连续下跌
            closes = stock_data['close']
            consecutive_down = 0
            for i in range(len(closes) - 1, 0, -1):
                if closes.iloc[i] < closes.iloc[i-1]:
                    consecutive_down += 1
                else:
                    break
            
            # 连续下跌3天 → 确认见顶
            if consecutive_down >= 3:
                logger.debug(f"  {symbol} 连续下跌{consecutive_down}天 → 确认见顶")
                return True
            
            # 检查是否跌破5日均线
            ma5 = closes.rolling(5).mean().iloc[-1]
            current_price = closes.iloc[-1]
            
            if current_price < ma5:
                logger.debug(f"  {symbol} 跌破MA5 (价格={current_price:.2f}, MA5={ma5:.2f}) → 确认见顶")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查龙头确认见顶异常: {e}")
            return False
    
    def _timing_signal(self, date: str) -> bool:
        """
        判断择时信号（3种方式，按优先级）
        
        优先级（根据市场状态）：
        1. 强势市场：指数爆发日（第一优先级）
        2. 震荡市场：前龙见顶日（第一优先级） > 情绪冰点日（第二优先级）
        3. 弱势市场：不参与
        
        Returns:
            True表示开始新的统计区间
        """
        # 优先级1：前龙见顶日（震荡市场第一优先级）
        if self.leader_tracker.leader_peak_date == date:
            logger.info(f"📍 择时信号: 前龙见顶日")
            return True
        
        # 优先级2：指数择时（强势市场专用：指数突破+成交量爆发）
        # 只有在5-9月那种大行情才触发（成交量3万亿级别）
        index_data = self._get_index_data(date, window=10)
        if index_data is not None and len(index_data) >= 10:
            # 今日涨幅
            today_close = index_data['close'].iloc[-1]
            yesterday_close = index_data['close'].iloc[-2]
            pct_change = ((today_close - yesterday_close) / yesterday_close) * 100
            
            # 成交量放大：今日 vs 过去10日均量
            if 'volume' in index_data.columns:
                today_volume = index_data['volume'].iloc[-1]
                avg_volume = index_data['volume'].iloc[-11:-1].mean()  # 过去10日均量
                volume_ratio = today_volume / avg_volume if avg_volume > 0 else 0
                
                # 条件：单日涨幅>3% 且 成交量放大2倍以上（大行情启动信号）
                if pct_change > 3.0 and volume_ratio > 2.0:
                    logger.info(f"📍 择时信号: 指数爆发 (涨幅={pct_change:.2f}%, 量比={volume_ratio:.2f}x)")
                    return True
        
        # 优先级3：情绪择时（冰点）- 震荡市场第二优先级
        if self.emotion_manager.is_ice_point(date, percentile_threshold=self.ice_point_percentile, lookback_days=self.emotion_lookback_days):
            logger.info(f"📍 择时信号: 情绪冰点")
            return True
        
        # 兜底：周期重置（避免统计区间过长）
        if self.tracking_start_date:
            try:
                start = pd.to_datetime(self.tracking_start_date)
                current = pd.to_datetime(date)
                days_diff = (current - start).days
                if days_diff >= 30:  # 30天强制重置
                    logger.info(f"📍 择时信号: 周期重置（已{days_diff}天）")
                    return True
            except:
                pass
        
        return False
    
    def get_pred_score(self) -> pd.Series:
        """
        计算龙头分数（真实龙头特征）
        
        龙头股特征（按重要性排序）：
        1. 涨停板数量和高度（最重要！连板优先）
        2. 成交量放大（量比 > 2，有资金关注）
        3. 近期强势（5-10天涨幅居前）
        4. 成交额（大资金才能做龙头）
        
        Returns:
            龙头分数，分数越高越可能是龙头
        """
        try:
            if not self.tracking_start_date:
                return pd.Series()
            
            # 获取近20天数据（足够判断龙头特征）
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (pd.Timestamp(end_date) - pd.Timedelta(days=20)).strftime('%Y-%m-%d')
            
            # 获取OHLCV数据
            fields = ['$close', '$high', '$low', '$volume', '$amount', '$open']
            df = D.features(
                D.instruments('all'),
                fields,
                start_time=start_date,
                end_time=end_date,
                freq='day'
            )
            
            if df.empty:
                return pd.Series()
            
            # 计算每只股票的龙头分数
            scores = {}
            for symbol in df.index.get_level_values('instrument').unique():
                # 过滤指数
                if symbol.startswith('000') or symbol.startswith('399'):
                    continue
                
                try:
                    stock_data = df.loc[symbol]
                    if len(stock_data) < 5:
                        continue
                    
                    score = 0
                    
                    # 1. 涨停板得分（权重最高！）
                    pct_changes = ((stock_data['$close'] - stock_data['$close'].shift(1)) / 
                                  stock_data['$close'].shift(1) * 100)
                    limit_up_days = (pct_changes >= 9.5).sum()  # >=9.5%算涨停
                    score += limit_up_days * 40  # 每个涨停板40分
                    
                    # 连板超级加成
                    if limit_up_days >= 2:
                        score += 30 * (limit_up_days - 1)  # 连板额外30分/板
                    
                    # 2. 量能爆发得分
                    recent_vol = stock_data['$volume'].iloc[-5:].mean()
                    earlier_vol = stock_data['$volume'].iloc[:5].mean()
                    if earlier_vol > 0:
                        vol_ratio = recent_vol / earlier_vol
                        if vol_ratio > 2:  # 近期量能是之前的2倍
                            score += min(25, (vol_ratio - 1) * 12)  # 最多25分
                    
                    # 3. 近期强势得分（5天涨幅）
                    if len(stock_data) >= 5:
                        recent_return = ((stock_data['$close'].iloc[-1] / 
                                        stock_data['$close'].iloc[-5] - 1) * 100)
                        if recent_return > 15:  # 5天涨15%+
                            score += min(20, recent_return)  # 最多20分
                    
                    # 4. 成交额得分（大资金才能做龙头）
                    avg_amount = stock_data['$amount'].iloc[-5:].mean()
                    if avg_amount > 1_000_000_000:  # 10亿+
                        score += 15
                    elif avg_amount > 500_000_000:  # 5亿+
                        score += 10
                    elif avg_amount > 200_000_000:  # 2亿+
                        score += 5
                    
                    # 只记录有分数的股票
                    if score > 0:
                        scores[symbol] = score
                        
                except Exception as e:
                    continue
            
            result = pd.Series(scores).sort_values(ascending=False)
            
            # 打印top 5用于调试
            if len(result) > 0:
                logger.debug(f"龙头分数Top5: {result.head().to_dict()}")
            
            return result
            
        except Exception as e:
            logger.error(f"计算龙头分数失败: {e}")
            return pd.Series()
    
    
    
    def _identify_hot_sectors(self, date: str) -> Dict:
        """
        v18: 识别热点板块（基于静态行业分类）
        
        核心逻辑：
        1. 获取统计区间内涨幅靠前的股票（top 50-100）
        2. 根据行业映射统计各行业的平均涨幅、股票数、涨停数
        3. 筛选热点行业：平均涨幅>15%，成员>=3只，强势股>=2只
        
        Returns:
            热点板块字典：{行业名: {'stocks': [], 'avg_return': float, 'strength': float}}
        """
        if not self.tracking_start_date:
            logger.debug("v18: 板块识别 - tracking_start_date未设置")
            return {}
        
        if not self.stock_industry_mapping:
            logger.warning("v18: 板块识别 - 行业映射为空，无法识别热点")
            return {}
        
        try:
            start_date = self.tracking_start_date
            end_date = date
            
            logger.debug(f"v18: 板块识别时间范围 {start_date} → {end_date}")
            
            # 获取候选股票数据
            df = D.features(
                D.instruments('all'),
                ['$close', '$volume'],
                start_time=start_date,
                end_time=end_date,
                freq='day'
            )
            
            if df.empty:
                logger.debug("v18: 板块识别 - 无数据返回")
                return {}
            
            # 计算每只股票的累计涨幅
            stock_returns = {}
            stock_volumes = {}
            
            for symbol in df.index.get_level_values('instrument').unique():
                # 跳过指数
                if symbol.startswith('000') or symbol.startswith('399'):
                    continue
                
                # 只处理有行业信息的股票
                if symbol not in self.stock_industry_mapping:
                    continue
                
                try:
                    stock_data = df.loc[symbol]
                    if len(stock_data) < 3:
                        continue
                    
                    # 累计涨幅
                    total_return = ((stock_data['$close'].iloc[-1] / 
                                   stock_data['$close'].iloc[0]) - 1) * 100
                    
                    # 平均成交量
                    avg_volume = stock_data['$volume'].mean()
                    
                    stock_returns[symbol] = total_return
                    stock_volumes[symbol] = avg_volume
                    
                except Exception as e:
                    continue
            
            if len(stock_returns) < 10:
                logger.debug(f"v18: 板块识别 - 有效股票不足10只（当前{len(stock_returns)}）")
                return {}
            
            logger.debug(f"v18: 板块识别 - 有效股票{len(stock_returns)}只")
            
            # 筛选涨幅靠前的股票作为候选（top 100或涨幅>5%）
            sorted_stocks = sorted(stock_returns.items(), key=lambda x: x[1], reverse=True)
            candidates = []
            for symbol, ret in sorted_stocks[:100]:
                if ret > 5:  # 涨幅>5%才算热门
                    candidates.append(symbol)
            
            if len(candidates) < 3:
                logger.debug(f"v18: 板块识别 - 热门候选不足3只（当前{len(candidates)}）")
                return {}
            
            logger.debug(f"v18: 板块识别 - 热门候选{len(candidates)}只")
            
            # 按行业统计
            industry_stats = {}
            
            for symbol in candidates:
                # v18: 使用_get_stock_industry获取行业名称
                industry = self._get_stock_industry(symbol)
                if not industry:
                    continue
                
                if industry not in industry_stats:
                    industry_stats[industry] = {
                        'stocks': [],
                        'returns': [],
                        'volumes': [],
                        'strong_count': 0  # 强势股数量（涨幅>15%）
                    }
                
                ret = stock_returns[symbol]
                vol = stock_volumes[symbol]
                
                industry_stats[industry]['stocks'].append(symbol)
                industry_stats[industry]['returns'].append(ret)
                industry_stats[industry]['volumes'].append(vol)
                
                if ret > 15:
                    industry_stats[industry]['strong_count'] += 1
            
            # 筛选热点行业
            hot_sectors = {}
            
            for industry, stats in industry_stats.items():
                stock_count = len(stats['stocks'])
                avg_return = np.mean(stats['returns'])
                strong_count = stats['strong_count']
                
                # 筛选条件（根据统计区间长度动态调整）
                min_return = 15  # 平均涨幅>15%
                min_stocks = 3   # 至少3只
                min_strong = 2   # 至少2只强势股
                
                # 根据统计区间长度动态调整
                days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
                if days <= 5:
                    min_return = 10
                    min_strong = 1
                elif days <= 10:
                    min_return = 12
                    min_strong = 1
                
                if (avg_return >= min_return and 
                    stock_count >= min_stocks and 
                    strong_count >= min_strong):
                    
                    hot_sectors[industry] = {
                        'stocks': stats['stocks'],
                        'avg_return': avg_return,
                        'strength': stock_count * avg_return / 100,  # 板块强度
                        'stock_count': stock_count,
                        'strong_count': strong_count
                    }
            
            logger.info(f"🔥 v18: 识别热点板块 {len(hot_sectors)} 个")
            for industry, info in sorted(hot_sectors.items(), 
                                        key=lambda x: x[1]['strength'], 
                                        reverse=True)[:5]:
                logger.info(f"   {industry}: {info['stock_count']}只 "
                          f"(强势{info['strong_count']}只), "
                          f"平均涨幅{info['avg_return']:.1f}%")
            
            return hot_sectors
            
        except Exception as e:
            logger.error(f"v18: 识别热点板块失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}
    
    def _calculate_leader_score(self, symbol: str, date: str, sector_stocks: List[str]) -> float:
        """
        计算个股龙头分数（文档3维度）- v16优化
        
        1. 累计涨幅：统计区间累计涨幅最高（60分）
        2. 量能：相对历史平均的堆量（30分）
        3. 提前启动：前1/3区间涨幅（10分）
        
        Returns:
            龙头得分（0-100）
        """
        try:
            start_date = self.tracking_start_date
            end_date = date
            
            # 获取统计区间数据
            df = D.features(
                [symbol],
                ['$close', '$volume'],
                start_time=start_date,
                end_time=end_date,
                freq='day'
            )
            
            if df.empty or len(df) < 5:
                return 0
            
            score = 0
            
            # 🔍 诊断：真龙头去哪了？
            is_leader = symbol in ['601869.SH', '300502.SZ', '300308.SZ']  # 长飞光纤, 新易盛, 中际旭创
            
            # 1. 累计涨幅（权重60分 - 最重要）
            total_return = ((df['$close'].iloc[-1] / df['$close'].iloc[0]) - 1) * 100
            cumulative_score = 0
            if total_return > 50:
                cumulative_score = 60
            elif total_return > 30:
                cumulative_score = 50
            elif total_return > 20:
                cumulative_score = 40
            elif total_return > 10:
                cumulative_score = 25
            elif total_return > 5:
                cumulative_score = 10
            score += cumulative_score
            
            # 2. 量能堆量（权重30分 - 资金集中度）
            # 改进：与历史30天平均量能对比，而不是前半vs后半
            vol_score = 0
            vol_ratio = 0
            try:
                # 获取历史30天数据作为基准
                hist_start = (pd.Timestamp(start_date) - pd.Timedelta(days=40)).strftime('%Y-%m-%d')
                hist_df = D.features(
                    [symbol],
                    ['$volume'],
                    start_time=hist_start,
                    end_time=start_date,
                    freq='day'
                )
                
                if not hist_df.empty and len(hist_df) >= 10:
                    # 历史平均量能（基准）
                    hist_avg_vol = hist_df['$volume'].mean()
                    # 当前区间平均量能
                    current_avg_vol = df['$volume'].mean()
                    
                    if hist_avg_vol > 0:
                        vol_ratio = current_avg_vol / hist_avg_vol
                        if vol_ratio > 3:  # 3倍以上堆量
                            vol_score = 30
                        elif vol_ratio > 2:  # 2倍堆量
                            vol_score = 20
                        elif vol_ratio > 1.5:  # 1.5倍堆量
                            vol_score = 10
            except Exception as e:
                logger.debug(f"量能计算失败{symbol}: {e}")
                vol_score = 0
            
            score += vol_score
            
            # 3. 提前启动（权重10分 - 参考指标）
            # 区间前1/3的涨幅
            third_point = len(df) // 3
            early_score = 0
            early_return = 0
            if third_point > 0:
                early_return = ((df['$close'].iloc[third_point] / df['$close'].iloc[0]) - 1) * 100
                if early_return > 15:
                    early_score = 10
                elif early_return > 10:
                    early_score = 7
                elif early_return > 5:
                    early_score = 3
            score += early_score
            
            # 🔍 真龙头日志
            if is_leader:
                logger.warning(
                    f"🎯 [真龙头诊断-v16] {symbol} | "
                    f"日期:{date} | 总分:{score} | "
                    f"累计涨幅:{total_return:.1f}%({cumulative_score}分/60) | "
                    f"量能堆量:{vol_ratio:.2f}x({vol_score}分/30) | "
                    f"提前启动:{early_return:.1f}%({early_score}分/10) | "
                    f"统计天数:{len(df)}天"
                )
            
            return score
            
        except Exception as e:
            logger.debug(f"计算{symbol}得分失败: {e}")
            return 0
    
    def _update_leader_candidates(self, date: str):
        """
        更新龙头候选池（基于板块的完整逻辑）
        
        流程（完全按文档）：
        1. 识别热点板块
        2. 在每个板块内选涨幅Top股票
        3. 跨板块选出Top10
        4. 如果同板块多只 → 每天去弱留强
        5. 如果分散板块 → 3维度筛选（提前启动、量能、板块联动）
        """
        if not self.tracking_start_date:
            return
        
        # 第1步：识别热点板块
        self.hot_sectors = self._identify_hot_sectors(date)
        
        if not self.hot_sectors:
            logger.warning("未识别到热点板块，回退到全市场选股")
            # 回退：全市场区间涨幅Top10
            pred_score = self.get_pred_score()
            if pred_score is not None and not pred_score.empty:
                self.leader_candidates = pred_score.nlargest(self.topk).index.tolist()
            return
        
        # 第2步：在每个热点板块内计算个股得分
        all_scores = {}
        # v18: 临时存储股票→板块映射（热点板块内的股票）
        stock_to_hot_sector = {}
        
        for sector_id, sector_info in self.hot_sectors.items():
            sector_stocks = sector_info['stocks']
            
            for symbol in sector_stocks:
                score = self._calculate_leader_score(symbol, date, sector_stocks)
                if score > 0:
                    all_scores[symbol] = score
                    stock_to_hot_sector[symbol] = sector_id
        
        if not all_scores:
            logger.warning("板块内无合格候选股")
            return
        
        # 第3步：跨板块选Top10
        sorted_scores = pd.Series(all_scores).sort_values(ascending=False)
        top_candidates = sorted_scores.head(self.topk)
        
        # 第4步：检查是否集中在同一板块
        candidate_sectors = [stock_to_hot_sector.get(s, 'unknown') for s in top_candidates.index]
        sector_counts = pd.Series(candidate_sectors).value_counts()
        
        if len(sector_counts) > 0 and sector_counts.iloc[0] >= 5:
            # 同板块集中 → 每天去弱留强（选板块内最强的）
            dominant_sector = sector_counts.index[0]
            logger.info(f"📊 候选集中在板块: {dominant_sector}")
            
            # 在这个板块内重新排序，取最强的topk只
            sector_candidates = {k: v for k, v in all_scores.items() 
                                if stock_to_hot_sector.get(k) == dominant_sector}
            self.leader_candidates = pd.Series(sector_candidates).nlargest(self.topk).index.tolist()
        else:
            # 板块分散 → 已经通过3维度打分筛选
            self.leader_candidates = top_candidates.index.tolist()
        
        logger.info(f"🎯 龙头候选池: {len(self.leader_candidates)}只")
        logger.info(f"   候选股票: {self.leader_candidates}")
        if len(top_candidates) > 0:
            logger.info(f"   Top3分数: {top_candidates.head(3).to_dict()}")
        
        # 记录龙头历史（用于板块连续性判断）
        if len(self.leader_candidates) > 0:
            top_leader = self.leader_candidates[0]
            leader_sector = stock_to_hot_sector.get(top_leader, None)
            leader_score = top_candidates.iloc[0] if len(top_candidates) > 0 else 0
            
            self.leader_history[date] = {
                'leader': top_leader,
                'sector': leader_sector,
                'score': leader_score
            }
            logger.debug(f"  记录龙头历史: {date} → {top_leader} (板块={leader_sector}, 分数={leader_score:.1f})")
    
    def _generate_buy_orders(
        self, 
        date: str, 
        market_regime: str,
        current_positions: dict,
        current_cash: float,
        total_value: float
    ) -> List[Order]:
        """
        生成买入订单（并行检测版本）
        
        改进：不再串行遍历候选股，而是：
        1. 并行检测所有候选股的所有买点
        2. 收集所有触发的买入信号及其优先级评分
        3. 按评分从高到低排序
        4. 依次买入直到满仓或资金不足
        """
        orders = []
        
        # 🎯 v18: 根据市场环境动态调整仓位策略（3种状态）
        if market_regime == MarketRegime.STRONG:
            # 强势市场：只买1只，全仓梭哈最强龙头
            max_positions = 1
            position_size = 1.0  # 100%全仓
            logger.info(f"🐂 v18-强势市场: 最多{max_positions}只, 仓位{position_size*100:.0f}%")
        
        elif market_regime == MarketRegime.OSCILLATE:
            # 震荡市场：2只，各40%（有热点就参与）
            max_positions = 2
            position_size = 0.4  # 40%
            logger.info(f"📈 v18-震荡市场: 最多{max_positions}只, 仓位{position_size*100:.0f}%")
        
        elif market_regime == MarketRegime.WEAK:
            # 弱势市场：空仓观望，不参与
            logger.info(f"🐻 v18-弱势市场: 空仓观望，不参与交易")
            return orders  # 直接返回空订单
        
        else:
            # 未知状态，默认保守策略
            max_positions = 2
            position_size = 0.4
            logger.warning(f"⚠️ 未知市场状态: {market_regime}, 使用保守策略")
        
        # 风控1：检查持仓数量
        active_positions = len([v for v in current_positions.values() if v > 0])
        if active_positions >= max_positions:
            logger.info(f"🛑 已达最大持仓数 {max_positions}，不再买入")
            return orders
        
        # 风控2：检查可用资金
        required_cash_per_buy = total_value * position_size
        if current_cash < required_cash_per_buy * 0.5:
            logger.warning(f"🛑 可用资金不足: 需要{required_cash_per_buy:,.0f}, 剩余{current_cash:,.0f}")
            return orders
        
        # 第1步：并行检测所有候选股，收集买入信号
        buy_signals = []  # [(symbol, signal_type, priority_score, dragon_score)]
        
        for symbol in self.leader_candidates:
            # 已持仓则跳过
            if symbol in current_positions and current_positions[symbol] > 0:
                continue
            
            # 检查买入信号（返回所有满足的信号，不是只返回第一个）
            signals = self._check_all_buy_signals(symbol, date, market_regime)
            
            if signals:
                # 获取龙头评分（用于相同买点优先级时的排序）
                dragon_score = 0
                if symbol in self.leader_candidates:
                    idx = self.leader_candidates.index(symbol)
                    dragon_score = 100 - idx * 5  # Top1=100分，Top2=95分，依此类推
                
                # 选择优先级最高的信号
                best_signal = signals[0]  # signals已按优先级排序
                signal_type, priority_score = best_signal
                
                buy_signals.append((symbol, signal_type, priority_score, dragon_score))
                logger.debug(f"[信号收集] {symbol}: {signal_type} (优先级={priority_score}, 龙头分={dragon_score})")
        
        if not buy_signals:
            logger.info("🔍 无符合买入条件的股票")
            return orders
        
        # 第2步：按优先级排序（优先级分数>龙头分数）
        buy_signals.sort(key=lambda x: (x[2], x[3]), reverse=True)
        
        logger.info(f"📊 收集到{len(buy_signals)}个买入信号，按优先级排序")
        for i, (symbol, signal_type, pri, dragon) in enumerate(buy_signals[:5]):
            logger.info(f"   #{i+1} {symbol}: {signal_type} (优先级={pri}, 龙头分={dragon})")
        
        # 第3步：按顺序买入
        max_buys_per_day = 3  # 每日最大买入次数
        buy_count = 0
        
        for symbol, signal_type, _, _ in buy_signals:
            # 风控：再次确认资金充足
            if current_cash < required_cash_per_buy * 0.5:
                logger.warning(f"🛑 资金不足，停止买入（剩余{current_cash:,.0f}）")
                break
            
            # 获取当前价格
            stock_data = self._get_stock_data(symbol, date, window=1)
            if stock_data is None or len(stock_data) == 0:
                logger.warning(f"⚠️ {symbol} 无法获取价格数据，跳过")
                continue
            
            current_price = stock_data['close'].iloc[-1]
            if pd.isna(current_price) or current_price <= 0:
                logger.warning(f"⚠️ {symbol} 价格无效 ({current_price})，跳过")
                continue
            
            # 计算股数
            target_value = total_value * position_size
            buy_shares = target_value / current_price
            buy_shares = int(buy_shares / 100) * 100
            
            if buy_shares < 100:
                logger.warning(f"⚠️ {symbol} 可买股数不足100股，跳过")
                continue
            
            # 创建买入订单
            order = Order(
                stock_id=symbol,
                amount=buy_shares,
                direction=Order.BUY,
                factor=1.0,
                start_time=pd.Timestamp(date),
                end_time=pd.Timestamp(date) + pd.Timedelta(days=1)
            )
            orders.append(order)
            
            # 更新模拟资金
            actual_cost = buy_shares * current_price
            current_cash -= actual_cost
            buy_count += 1
            
            logger.info(f"✅ 买入信号: {symbol}, 信号类型: {signal_type}, "
                       f"价格: ¥{current_price:.2f}, 股数: {buy_shares}, "
                       f"预计金额: {actual_cost:,.0f}, 剩余: {current_cash:,.0f}")
            
            # 风控：达到限制
            if active_positions + len(orders) >= max_positions:
                logger.info(f"🛑 已达最大持仓数 {max_positions}")
                break
            
            if buy_count >= max_buys_per_day:
                logger.info(f"🛑 已达单日最大买入数 {max_buys_per_day}")
                break
        
        return orders
    
    def _check_all_buy_signals(
        self, 
        symbol: str, 
        date: str, 
        market_regime: str
    ) -> List[Tuple[str, int]]:
        """
        v18: 检查所有买入信号（针对3种市场状态）
        
        不同市场状态有不同的买点优先级：
        - 强势市场（STRONG）：追涨 > 板块起爆 > 突破
        - 震荡市场（OSCILLATE）：冰点低吸 > 回踩 > 板块起爆
        - 弱势市场（WEAK）：不参与
        
        Returns:
            [(signal_type, priority_score), ...] 买入信号列表，按优先级排序
        """
        signals = []
        
        # 弱势市场：不参与
        if market_regime == MarketRegime.WEAK:
            return signals
        
        # 获取股票数据
        stock_data = self._get_stock_data(symbol, date, window=20)
        if stock_data is None or len(stock_data) < 5:
            return signals
        
        close = stock_data['close']
        volume = stock_data['volume']
        pct_change = stock_data['pct_change'].iloc[-1] if 'pct_change' in stock_data else 0
        
        # ========== 强势市场：追涨为主 ==========
        if market_regime == MarketRegime.STRONG:
            # 1. 追涨龙头（优先级100）- 当日大涨且是龙头候选
            if pct_change > 5 and len(close) >= 5:
                ma5 = close.rolling(5).mean().iloc[-1]
                if close.iloc[-1] > ma5:
                    signals.append(('strong_chase', 100))
                    logger.debug(f"{symbol}: v18-强势追涨信号（涨幅={pct_change:.2f}%）")
            
            # 2. 板块起爆分歧（优先级90）- 板块首次放量突破
            if self._check_sector_breakout(symbol, date, stock_data):
                signals.append(('strong_sector_breakout', 90))
                logger.debug(f"{symbol}: v18-强势板块起爆")
            
            # 3. 强势突破（优先级80）- 突破前高
            if len(close) >= 10:
                recent_high = close.iloc[-10:-1].max()
                if close.iloc[-1] > recent_high * 1.02:
                    signals.append(('strong_breakthrough', 80))
                    logger.debug(f"{symbol}: v18-强势突破")
        
        # ========== 震荡市场：低吸为主 ==========
        elif market_regime == MarketRegime.OSCILLATE:
            # 1. 情绪冰点低吸（优先级100）- 市场最低迷时
            ice_point = self._check_ice_point_signal(date)
            if ice_point and pct_change < 0:  # 冰点且个股下跌
                signals.append(('oscillate_ice_point', 100))
                logger.debug(f"{symbol}: v18-震荡冰点低吸")
            
            # 2. 龙头回踩（优先级90）- 回调到MA5附近
            if self._check_pullback_signal(symbol, stock_data):
                signals.append(('oscillate_pullback', 90))
                logger.debug(f"{symbol}: v18-震荡回踩买入")
            
            # 3. 板块起爆分歧（优先级80）
            if self._check_sector_breakout(symbol, date, stock_data):
                signals.append(('oscillate_sector_breakout', 80))
                logger.debug(f"{symbol}: v18-震荡板块起爆")
            
            # 4. 缩量回调（优先级70）
            if self._check_volume_pullback(symbol, date, stock_data):
                signals.append(('oscillate_volume_pullback', 70))
                logger.debug(f"{symbol}: v18-震荡缩量回调")
        
        # 按优先级降序排序
        signals.sort(key=lambda x: x[1], reverse=True)
        
        return signals
    
    def _check_ice_point_signal(self, date: str) -> bool:
        """
        检查是否为情绪冰点
        
        Args:
            date: 当前日期
            
        Returns:
            是否为冰点
        """
        try:
            # 获取当前情绪数据
            emotion = self.emotion_manager.get_emotion_data(date)
            if not emotion:
                return False
            
            limit_up_count = emotion.get('limit_up_count', 0)
            
            # 获取近期情绪数据进行对比
            recent_emotions = self.emotion_manager.get_recent_emotions(
                date, 
                days=self.emotion_lookback_days
            )
            
            if not recent_emotions:
                return False
            
            # 计算百分位
            recent_limit_ups = [e.get('limit_up_count', 0) for e in recent_emotions]
            percentile = np.percentile(recent_limit_ups, self.ice_point_percentile * 100)
            
            # 当前涨停数低于百分位阈值视为冰点
            return limit_up_count <= percentile
            
        except Exception as e:
            logger.debug(f"检查冰点信号失败: {e}")
            return False
    
    def _check_sector_breakout(self, symbol: str, date: str, stock_data: pd.DataFrame) -> bool:
        """
        检查板块起爆分歧
        
        标准：
        - 当日涨幅>5%
        - 成交量>5日均量的1.5倍
        - 股价在MA5上方
        """
        try:
            if len(stock_data) < 5:
                return False
            
            close = stock_data['close']
            volume = stock_data['volume']
            pct_change = stock_data['pct_change'].iloc[-1] if 'pct_change' in stock_data else 0
            
            # 当日涨幅>5%
            if pct_change <= 5:
                return False
            
            # 成交量放大
            ma5_volume = volume.rolling(5).mean().iloc[-2]  # 前5日均量
            current_volume = volume.iloc[-1]
            
            if current_volume < ma5_volume * 1.5:
                return False
            
            # 股价在MA5上方
            ma5_price = close.rolling(5).mean().iloc[-1]
            if close.iloc[-1] <= ma5_price:
                return False
            
            return True
            
        except Exception as e:
            return False
    
    def _check_pullback_signal(self, symbol: str, stock_data: pd.DataFrame) -> bool:
        """
        检查回踩买入信号
        
        标准：
        - 股价回调到MA5附近（0.95-1.02倍）
        - 当日涨幅在[-2%, +3%]
        - 前期有过上涨（5日内最高价>当前价5%）
        """
        try:
            if len(stock_data) < 5:
                return False
            
            close = stock_data['close']
            pct_change = stock_data['pct_change'].iloc[-1] if 'pct_change' in stock_data else 0
            
            # 当日涨跌幅合理
            if not (-2 <= pct_change <= 3):
                return False
            
            # 股价在MA5附近
            ma5 = close.rolling(5).mean().iloc[-1]
            price_to_ma5 = close.iloc[-1] / ma5
            
            if not (0.95 <= price_to_ma5 <= 1.02):
                return False
            
            # 前期有过上涨
            recent_high = close.iloc[-5:].max()
            if recent_high <= close.iloc[-1] * 1.05:
                return False
            
            return True
            
        except Exception as e:
            return False


    def _is_previous_leader(self, symbol: str) -> bool:
        """
        判断是否是前龙头
        
        Args:
            symbol: 股票代码
        
        Returns:
            True: 是前龙头
            False: 不是前龙头
        """
        # 检查是否是最近见顶的龙头
        if self.leader_tracker.current_leader == symbol:
            # 当前龙头但已见顶
            if self.leader_tracker.leader_status == "dead":
                return True
        
        # 检查历史记录中最近5天的龙头
        recent_leaders = set()
        dates = sorted(self.leader_history.keys(), reverse=True)[:5]
        for date in dates:
            leader_info = self.leader_history.get(date)
            if leader_info:
                recent_leaders.add(leader_info.get('leader'))
        
        return symbol in recent_leaders
    
    def _check_volume_pullback(self, symbol: str, date: str, stock_data: pd.DataFrame) -> bool:
        """
        检查缩量回踩（震荡轮动时的买点）
        
        标准：
        - 价格在MA5附近（0.95-1.05）
        - 成交量缩小（<0.9倍均量）
        """
        try:
            if len(stock_data) < self.ma_period:
                return False
            
            close = stock_data['close']
            volume = stock_data['volume']
            
            ma5 = close.rolling(self.ma_period).mean().iloc[-1]
            current_close = close.iloc[-1]
            
            # 价格在MA5附近
            if not (0.95 <= current_close / ma5 <= 1.05):
                return False
            
            # 成交量缩小
            if len(volume) >= 6:
                avg_volume = volume.rolling(5).mean().iloc[-2]
                current_volume = volume.iloc[-1]
                
                if avg_volume > 0:
                    volume_ratio = current_volume / avg_volume
                    if volume_ratio < 0.9:
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查缩量回踩异常: {e}")
            return False
    
    def _check_technical_pullback(self, symbol: str, date: str, stock_data: pd.DataFrame) -> bool:
        """
        检查技术面回踩（通用买点）
        
        标准：
        - 价格在MA5附近（0.95-1.05）
        - 成交量缩小（<0.9倍均量）
        """
        return self._check_volume_pullback(symbol, date, stock_data)
    
    def _check_buy_signal(
        self, 
        symbol: str, 
        date: str, 
        market_regime: str
    ) -> Tuple[bool, str]:
        """
        检查买入信号（兼容旧版本，调用新的并行检测）
        
        保留此方法是为了兼容性，实际使用_check_all_buy_signals
        """
        signals = self._check_all_buy_signals(symbol, date, market_regime)
        if signals:
            return True, signals[0][0]  # 返回优先级最高的信号
        return False, ''
    
    def _check_sector_outbreak_divergence(self, symbol: str, date: str) -> bool:
        """
        检测板块起爆分歧买点
        
        逻辑：
        1. 股票在某个热点板块中
        2. 前一日板块内涨停股>=3只（板块起爆）
        3. 今日龙头小幅回调2-5%（分歧）
        4. 但不破5日线（强势回调）
        
        这是板块启动后的首次低吸机会
        """
        # v18: 检查股票是否在热点板块中
        stock_industry = self._get_stock_industry(symbol)
        if not stock_industry or stock_industry not in self.hot_sectors:
            return False
        
        sector_stocks = self.hot_sectors[stock_industry]['stocks']
        
        # 获取前一日数据（检测是否有涨停潮）
        yesterday = (pd.Timestamp(date) - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        
        # 统计前一日板块内涨停股票数
        limit_up_count = 0
        for stock in sector_stocks:
            stock_data = self._get_stock_data(stock, yesterday, window=1)
            if stock_data is not None and len(stock_data) > 0:
                pct = stock_data['pct_change'].iloc[-1] if 'pct_change' in stock_data else 0
                # A股涨停约9.9-10.1%（考虑四舍五入）
                if pct >= 9.5:
                    limit_up_count += 1
        
        # 判断：前一日至少3只涨停（板块起爆）
        if limit_up_count < 3:
            return False
        
        # 获取目标股票今日数据
        stock_data = self._get_stock_data(symbol, date, window=self.ma_period)
        if stock_data is None or len(stock_data) < self.ma_period:
            return False
        
        pct_change = stock_data['pct_change'].iloc[-1] if 'pct_change' in stock_data else 0
        close = stock_data['close']
        
        # 判断：今日小幅回调2-5%（分歧）
        if not (-5 <= pct_change <= -2):
            return False
        
        # 判断：不破5日线（强势回调）
        ma5 = close.rolling(self.ma_period).mean().iloc[-1]
        current_close = close.iloc[-1]
        
        # 收盘价在5日线上方或最多低3%
        if current_close < ma5 * 0.97:
            return False
        
        logger.debug(f"   板块起爆: {sector_id}板块昨日{limit_up_count}只涨停, "
                    f"{symbol}今日回调{pct_change:.2f}%, 在5日线{(current_close/ma5-1)*100:.1f}%附近")
        
        return True
    
    def _generate_sell_orders(
        self, 
        date: str, 
        market_regime: str,
        current_positions: dict
    ) -> List[Order]:
        """生成卖出订单"""
        orders = []
        
        for symbol, amount in current_positions.items():
            if amount <= 0:
                continue
                
            # 检查卖出信号
            sell_signal, signal_type = self._check_sell_signal(symbol, date, market_regime)
            
            if sell_signal:
                # 创建卖出订单（全部卖出）
                order = Order(
                    stock_id=symbol,
                    amount=amount,
                    direction=Order.SELL,
                    factor=0.0,  # 清仓
                    start_time=pd.Timestamp(date),
                    end_time=pd.Timestamp(date) + pd.Timedelta(days=1)
                )
                orders.append(order)
                
                logger.info(f"卖出信号: {symbol}, 信号类型: {signal_type}, 数量: {amount}")
        
        return orders
    
    def _check_sell_signal(
        self, 
        symbol: str, 
        date: str, 
        market_regime: str
    ) -> Tuple[bool, str]:
        """
        检查卖出信号（Phase 5：根据市场状态分支）
        
        不同市场状态有不同的卖出逻辑：
        - 强势市场（STRONG）：板块高潮+跌破五日线
        - 震荡-板块效应（OSCILLATE_SECTOR）：见好就收，持仓≥2天或盈利>5%
        - 震荡-板块轮动（OSCILLATE_ROTATION）：次日兑现，不黏股
        - 弱势市场（WEAK）：不应持仓，立即清仓
        
        Returns:
            (是否卖出, 信号类型)
        """
        stock_data = self._get_stock_data(symbol, date, window=20)
        if stock_data is None or len(stock_data) < 5:
            return False, ''
        
        close = stock_data['close']
        volume = stock_data['volume']
        pct_change = stock_data['pct_change'].iloc[-1] if 'pct_change' in stock_data else 0
        
        # ========== v18: 市场状态分支（3种状态） ==========
        
        # 🐻 弱势市场：不应持仓，立即清仓
        if market_regime == MarketRegime.WEAK:
            logger.info(f"[卖出检测] {symbol} - v18-弱势市场空仓")
            return True, 'weak_market_exit'
        
        # 📈 震荡市场：见好就收，不贪
        elif market_regime == MarketRegime.OSCILLATE:
            # 1. 小盈利即卖（>5%）
            if len(close) >= 10:
                buy_price_approx = close.iloc[-10]
                current_price = close.iloc[-1]
                profit_rate = (current_price - buy_price_approx) / buy_price_approx
                
                if profit_rate >= 0.05:
                    logger.info(f"[卖出检测] {symbol} - v18-震荡止盈（收益≈{profit_rate*100:.1f}%）")
                    return True, 'oscillate_profit_5'
            
            # 2. 跌破MA5卖
            if len(close) >= self.ma_period:
                ma5 = close.rolling(self.ma_period).mean().iloc[-1]
                if close.iloc[-1] < ma5 * 0.98:
                    logger.info(f"[卖出检测] {symbol} - v18-震荡跌破MA5")
                    return True, 'oscillate_break_ma5'
            
            # 3. 止损（-8%）
            if pct_change < -8:
                logger.info(f"[卖出检测] {symbol} - v18-震荡止损（跌幅={pct_change:.2f}%）")
                return True, 'oscillate_stop_loss'
            
            # 4. 板块高潮卖出
            sector_climax = self._check_sector_climax(symbol, date)
            if sector_climax:
                logger.info(f"[卖出检测] {symbol} - v18-震荡板块高潮")
                return True, 'oscillate_sector_climax'
            
            return False, ''
        
        # 🐂 强势市场：持股待涨，但要设止盈止损
        elif market_regime == MarketRegime.STRONG:
            # 1. 大止盈（>30%）
            if len(close) >= 20:
                buy_price_approx = close.iloc[-20]
                current_price = close.iloc[-1]
                profit_rate = (current_price - buy_price_approx) / buy_price_approx
                
                if profit_rate >= 0.30:
                    logger.info(f"[卖出检测] {symbol} - v18-强势大止盈（收益≈{profit_rate*100:.1f}%）")
                    return True, 'strong_profit_30'
            
            # 2. 跌破MA5（趋势破坏）
            if len(close) >= self.ma_period:
                ma5 = close.rolling(self.ma_period).mean().iloc[-1]
                if close.iloc[-1] < ma5:
                    logger.info(f"[卖出检测] {symbol} - v18-强势跌破MA5")
                    return True, 'strong_break_ma5'
            
            # 3. 板块高潮
            sector_climax = self._check_sector_climax(symbol, date)
            if sector_climax:
                logger.info(f"[卖出检测] {symbol} - v18-强势板块高潮")
                return True, 'strong_sector_climax'
            
            # 4. 止损（-10%）
            if len(close) >= 10:
                recent_high = close.iloc[-10:].max()
                current_price = close.iloc[-1]
                drawdown = (current_price - recent_high) / recent_high
                
                if drawdown <= -0.10:
                    logger.info(f"[卖出检测] {symbol} - v18-强势止损（回撤={drawdown*100:.1f}%）")
                    return True, 'strong_stop_loss'
            
            return False, ''
        
        # 默认：不卖
        return False, ''

    def _check_sector_climax(self, symbol: str, date: str) -> bool:
        """
        检查板块是否达到高潮（过热）
        
        判断标准：
        1. 股票所属的热点板块内
        2. 板块内涨停股数 >= 板块股票总数的30%
        3. 且连续2天保持高热度
        
        Args:
            symbol: 股票代码
            date: 当前日期
            
        Returns:
            是否板块高潮
        """
        try:
            # 1. 获取股票所属行业
            stock_industry = self._get_stock_industry(symbol)
            if not stock_industry or stock_industry not in self.hot_sectors:
                return False
            
            sector_stocks = self.hot_sectors[stock_industry]['stocks']
            if len(sector_stocks) < 3:
                return False
            
            # 2. 检查当前和前一天的涨停情况
            date_pd = pd.Timestamp(date)
            yesterday = (date_pd - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            
            # 统计今天的涨停数
            today_limit_up = 0
            for stock in sector_stocks:
                stock_data = self._get_stock_data(stock, date, window=1)
                if stock_data is not None and len(stock_data) > 0:
                    pct = stock_data['pct_change'].iloc[-1] if 'pct_change' in stock_data else 0
                    if pct >= 9.5:  # 涨停
                        today_limit_up += 1
            
            # 统计昨天的涨停数
            yesterday_limit_up = 0
            for stock in sector_stocks:
                stock_data = self._get_stock_data(stock, yesterday, window=1)
                if stock_data is not None and len(stock_data) > 0:
                    pct = stock_data['pct_change'].iloc[-1] if 'pct_change' in stock_data else 0
                    if pct >= 9.5:
                        yesterday_limit_up += 1
            
            # 3. 判断是否达到高潮
            total_stocks = len(sector_stocks)
            today_ratio = today_limit_up / total_stocks
            yesterday_ratio = yesterday_limit_up / total_stocks
            
            # 连续2天涨停股占比超过30%
            is_climax = today_ratio >= 0.3 and yesterday_ratio >= 0.3
            
            if is_climax:
                logger.debug(f"板块高潮检测: {stock_industry} - "
                           f"今日涨停{today_limit_up}/{total_stocks}({today_ratio*100:.1f}%), "
                           f"昨日涨停{yesterday_limit_up}/{total_stocks}({yesterday_ratio*100:.1f}%)")
            
            return is_climax
            
        except Exception as e:
            logger.debug(f"板块高潮检测失败: {e}")
            return False

    def _get_index_data(
        self, 
        date: str, 
        window: int = 20, 
        index_code: str = "000001.SH"  # 上证指数
    ) -> Optional[pd.DataFrame]:
        """获取指数数据"""
        try:
            # 从 Qlib 获取指数数据
            end_date = pd.to_datetime(date)
            start_date = end_date - pd.Timedelta(days=window*2)  # 多留余量
            
            df = D.features(
                [index_code],
                ['$close', '$open', '$high', '$low', '$volume'],
                start_time=start_date.strftime('%Y-%m-%d'),
                end_time=end_date.strftime('%Y-%m-%d'),
                freq='day'
            )
            
            if df.empty:
                return None
            
            # 提取单只指数的数据
            if isinstance(df.index, pd.MultiIndex):
                df = df.xs(index_code, level='instrument')
            
            # 重命名列
            df = df.rename(columns={
                '$close': 'close',
                '$open': 'open', 
                '$high': 'high',
                '$low': 'low',
                '$volume': 'volume'
            })
            
            # 只取最近 window 条
            return df.tail(window)
            
        except Exception as e:
            logger.debug(f"获取指数数据失败: {e}")
            return None
    
    def _get_stock_data(
        self, 
        symbol: str, 
        date: str, 
        window: int = 10
    ) -> Optional[pd.DataFrame]:
        """获取个股数据"""
        try:
            # 从 Qlib 数据源获取
            end_date = pd.to_datetime(date)
            start_date = end_date - pd.Timedelta(days=window*3)  # 留余量
            
            df = D.features(
                [symbol],
                ['$close', '$open', '$high', '$low', '$volume'],
                start_time=start_date.strftime('%Y-%m-%d'),
                end_time=end_date.strftime('%Y-%m-%d'),
                freq='day'
            )
            
            if df.empty:
                return None
            
            # 提取单只股票的数据
            if isinstance(df.index, pd.MultiIndex):
                df = df.xs(symbol, level='instrument')
            
            # 重命名列
            df = df.rename(columns={
                '$close': 'close',
                '$open': 'open',
                '$high': 'high',
                '$low': 'low',
                '$volume': 'volume'
            })
            
            # 计算涨跌幅
            df['pct_change'] = df['close'].pct_change() * 100
            
            # 只取最近 window+1 条（需要前一天数据计算涨跌幅）
            return df.tail(window+1)
            
        except Exception as e:
            logger.debug(f"获取 {symbol} 数据失败: {e}")
            return None


if __name__ == "__main__":
    # 测试代码
    strategy = LeaderLowAbsorptionStrategy(
        topk=10,
        max_positions=3,
        position_size=0.3
    )
    
    print("策略初始化成功")
