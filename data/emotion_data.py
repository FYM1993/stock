"""
市场情绪数据管理

负责收集、存储和提供市场情绪相关数据，包括：
- 涨跌家数统计
- 涨停跌停家数
- 市场平均涨跌幅
- 成交额统计
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from loguru import logger
import json

from .akshare_provider import AKShareProvider


class EmotionDataManager:
    """市场情绪数据管理器"""
    
    def __init__(self, data_path: str = "./data/emotion"):
        """
        初始化情绪数据管理器
        
        Args:
            data_path: 情绪数据存储路径
        """
        self.data_path = Path(data_path)
        self.data_path.mkdir(parents=True, exist_ok=True)
        
        self.provider = AKShareProvider()
        self.emotion_file = self.data_path / "market_emotion.csv"
        
        # 加载历史数据
        self.emotion_df = self._load_emotion_data()
    
    def _load_emotion_data(self) -> pd.DataFrame:
        """加载历史情绪数据"""
        if self.emotion_file.exists():
            df = pd.read_csv(self.emotion_file, index_col=0, parse_dates=True)
            logger.info(f"加载历史情绪数据: {len(df)} 条记录")
            return df
        else:
            logger.info("创建新的情绪数据文件")
            return pd.DataFrame()
    
    def update_emotion_data(self, date: Optional[str] = None):
        """
        更新市场情绪数据
        
        Args:
            date: 日期，None表示今天
        """
        emotion = self.provider.get_market_emotion_data(date)
        
        if not emotion:
            logger.warning("获取情绪数据失败")
            return
        
        # 转换为DataFrame
        emotion_date = pd.to_datetime(emotion['date'])
        
        # 检查是否已存在
        if emotion_date in self.emotion_df.index:
            logger.info(f"日期 {emotion['date']} 的数据已存在，跳过")
            return
        
        # 添加新数据
        new_row = pd.DataFrame([emotion], index=[emotion_date])
        self.emotion_df = pd.concat([self.emotion_df, new_row])
        self.emotion_df.sort_index(inplace=True)
        
        # 保存
        self._save_emotion_data()
        
        logger.info(f"更新情绪数据: {emotion['date']}, "
                   f"上涨: {emotion['up_count']}, 下跌: {emotion['down_count']}")
    
    def _save_emotion_data(self):
        """保存情绪数据到文件"""
        self.emotion_df.to_csv(self.emotion_file)
        logger.debug(f"保存情绪数据到 {self.emotion_file}")
    
    def get_emotion_on_date(self, date: str) -> Optional[Dict]:
        """
        获取指定日期的情绪数据
        
        Args:
            date: 日期，格式 '2024-01-01'
            
        Returns:
            情绪数据字典
        """
        date_dt = pd.to_datetime(date)
        
        if date_dt not in self.emotion_df.index:
            logger.warning(f"日期 {date} 的情绪数据不存在")
            return None
        
        row = self.emotion_df.loc[date_dt]
        return row.to_dict()
    
    def get_emotion_range(
        self, 
        start_date: str, 
        end_date: str
    ) -> pd.DataFrame:
        """
        获取日期范围内的情绪数据
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            情绪数据DataFrame
        """
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        mask = (self.emotion_df.index >= start_dt) & (self.emotion_df.index <= end_dt)
        return self.emotion_df[mask]
    
    def get_emotion_data(self, date: str, window: int = 5) -> Optional[pd.DataFrame]:
        """
        获取指定日期前N天的情绪数据
        
        Args:
            date: 日期
            window: 窗口大小（交易日）
            
        Returns:
            情绪数据DataFrame
        """
        date_dt = pd.to_datetime(date)
        
        # 获取指定日期及之前的数据
        historical = self.emotion_df[
            self.emotion_df.index <= date_dt
        ].tail(window)
        
        if len(historical) == 0:
            return None
        
        return historical
    
    def get_limit_up_percentile(self, date: str, lookback_days: int = 60) -> float:
        """
        获取当前涨停数在历史中的分位数
        
        Args:
            date: 日期
            lookback_days: 回溯天数
            
        Returns:
            分位数，0-1之间
        """
        emotion = self.get_emotion_on_date(date)
        if emotion is None:
            return 0.5
        
        date_dt = pd.to_datetime(date)
        historical = self.emotion_df[
            self.emotion_df.index <= date_dt
        ].tail(lookback_days)
        
        if len(historical) < 20:
            return 0.5
        
        # 计算涨停数的分位数
        current_limit_up = emotion['limit_up_count']
        percentile = (historical['limit_up_count'] < current_limit_up).sum() / len(historical)
        
        return percentile
    
    def is_ice_point(self, date: str, percentile_threshold: float = 0.2, lookback_days: int = 60) -> bool:
        """
        判断是否为情绪冰点（使用相对百分位数）
        
        Args:
            date: 日期
            percentile_threshold: 百分位阈值，默认0.2（即涨停数处于近期20%分位以下）
            lookback_days: 回溯天数，默认60个交易日（约3个月）
            
        Returns:
            是否为冰点
        """
        emotion = self.get_emotion_on_date(date)
        if emotion is None:
            return False
        
        # 获取历史数据
        date_dt = pd.to_datetime(date)
        historical = self.emotion_df[
            self.emotion_df.index <= date_dt
        ].tail(lookback_days)
        
        if len(historical) < 20:  # 数据不足
            return False
        
        # 计算涨停数的百分位
        current_limit_up = emotion['limit_up_count']
        percentile = (historical['limit_up_count'] < current_limit_up).sum() / len(historical)
        
        return percentile <= percentile_threshold
    
    def is_climax(self, date: str, percentile_threshold: float = 0.8, lookback_days: int = 60) -> bool:
        """
        判断是否为情绪高潮（使用相对百分位数）
        
        Args:
            date: 日期
            percentile_threshold: 百分位阈值，默认0.8（即涨停数处于近期80%分位以上）
            lookback_days: 回溯天数，默认60个交易日（约3个月）
            
        Returns:
            是否为高潮
        """
        emotion = self.get_emotion_on_date(date)
        if emotion is None:
            return False
        
        # 获取历史数据
        date_dt = pd.to_datetime(date)
        historical = self.emotion_df[
            self.emotion_df.index <= date_dt
        ].tail(lookback_days)
        
        if len(historical) < 20:  # 数据不足
            return False
        
        # 计算涨停数的百分位
        current_limit_up = emotion['limit_up_count']
        percentile = (historical['limit_up_count'] < current_limit_up).sum() / len(historical)
        
        return percentile >= percentile_threshold
    
    def get_emotion_trend(self, date: str, window: int = 5) -> str:
        """
        获取情绪趋势
        
        Args:
            date: 日期
            window: 回溯窗口
            
        Returns:
            'improving' 改善, 'worsening' 恶化, 'stable' 稳定
        """
        date_dt = pd.to_datetime(date)
        
        # 获取最近N天的数据
        recent_data = self.emotion_df[
            self.emotion_df.index <= date_dt
        ].tail(window)
        
        if len(recent_data) < 2:
            return 'stable'
        
        # 计算上涨家数的趋势
        up_counts = recent_data['up_count'].values
        
        # 简单线性回归判断趋势
        x = np.arange(len(up_counts))
        slope = np.polyfit(x, up_counts, 1)[0]
        
        if slope > 100:
            return 'improving'
        elif slope < -100:
            return 'worsening'
        else:
            return 'stable'
    
    def get_emotion_percentile(self, date: str, window: int = 60) -> float:
        """
        获取当前情绪在历史中的分位数
        
        Args:
            date: 日期
            window: 回溯窗口（交易日）
            
        Returns:
            分位数，0-1之间
        """
        date_dt = pd.to_datetime(date)
        
        # 获取历史数据
        historical = self.emotion_df[
            self.emotion_df.index <= date_dt
        ].tail(window)
        
        if len(historical) < 10:
            return 0.5  # 数据不足，返回中位数
        
        current_emotion = self.get_emotion_on_date(date)
        if current_emotion is None:
            return 0.5
        
        # 计算上涨家数的分位数
        current_up = current_emotion['up_count']
        percentile = (historical['up_count'] < current_up).sum() / len(historical)
        
        return percentile
    
    def collect_historical_data(
        self,
        start_date: str = "20200101",
        end_date: Optional[str] = None
    ):
        """
        批量采集历史情绪数据
        
        注意：这需要逐日采集，比较慢
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')
        
        start_dt = datetime.strptime(start_date, '%Y%m%d')
        end_dt = datetime.strptime(end_date, '%Y%m%d')
        
        current_dt = start_dt
        
        logger.info(f"开始采集历史情绪数据: {start_date} - {end_date}")
        
        while current_dt <= end_dt:
            date_str = current_dt.strftime('%Y-%m-%d')
            
            # 跳过周末
            if current_dt.weekday() < 5:
                self.update_emotion_data(date_str)
            
            current_dt += timedelta(days=1)
        
        logger.info("历史数据采集完成")


if __name__ == "__main__":
    # 测试代码
    manager = EmotionDataManager()
    
    # 测试更新今日数据
    manager.update_emotion_data()
    
    # 测试查询
    today = datetime.now().strftime('%Y-%m-%d')
    emotion = manager.get_emotion_on_date(today)
    print(f"今日情绪: {emotion}")
    
    # 测试判断冰点
    is_ice = manager.is_ice_point(today)
    print(f"是否冰点: {is_ice}")
    
    # 测试情绪趋势
    trend = manager.get_emotion_trend(today)
    print(f"情绪趋势: {trend}")
