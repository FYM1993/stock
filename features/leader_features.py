"""
龙头识别特征

基于以下维度识别龙头股:
1. 区间涨幅（相对强度）
2. 量能特征（堆量、放量）
3. 板块联动（板块热度、板块内排名）
4. 提前启动（相对大盘和板块的领先性）
5. 成交额排名
"""

import pandas as pd
import numpy as np
from typing import Dict, List
from loguru import logger


class LeaderFeatures:
    """龙头识别特征计算"""
    
    @staticmethod
    def calculate_interval_return(
        df: pd.DataFrame,
        start_date: str,
        end_date: str
    ) -> float:
        """
        计算区间涨幅
        
        Args:
            df: 股票数据
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            区间涨幅（百分比）
        """
        try:
            start_price = df.loc[start_date, 'close']
            end_price = df.loc[end_date, 'close']
            
            return (end_price / start_price - 1) * 100
        except:
            return 0.0
    
    @staticmethod
    def calculate_relative_strength(
        stock_df: pd.DataFrame,
        benchmark_df: pd.DataFrame,
        window: int = 20
    ) -> float:
        """
        计算相对强度（RS）
        
        相对强度 = 个股涨幅 / 大盘涨幅
        
        Args:
            stock_df: 个股数据
            benchmark_df: 基准数据（如沪深300）
            window: 回溯窗口
            
        Returns:
            相对强度值
        """
        if len(stock_df) < window or len(benchmark_df) < window:
            return 1.0
        
        # 计算个股收益
        stock_return = (stock_df['close'].iloc[-1] / stock_df['close'].iloc[-window] - 1) * 100
        
        # 计算基准收益
        benchmark_return = (benchmark_df['close'].iloc[-1] / benchmark_df['close'].iloc[-window] - 1) * 100
        
        # 避免除零
        if benchmark_return == 0:
            return 1.0
        
        rs = stock_return / benchmark_return
        
        return rs
    
    @staticmethod
    def calculate_volume_surge(
        df: pd.DataFrame,
        window: int = 20
    ) -> float:
        """
        计算量能激增度
        
        Args:
            df: 股票数据
            window: 回溯窗口
            
        Returns:
            当前量能 / 平均量能
        """
        if len(df) < window:
            return 1.0
        
        current_volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].iloc[-window:-1].mean()
        
        if avg_volume == 0:
            return 1.0
        
        return current_volume / avg_volume
    
    @staticmethod
    def calculate_volume_accumulation(
        df: pd.DataFrame,
        window: int = 5
    ) -> float:
        """
        计算量能堆积
        
        检查最近N天的量能是否持续放大
        
        Args:
            df: 股票数据
            window: 窗口大小
            
        Returns:
            堆量得分 (0-1)
        """
        if len(df) < window * 2:
            return 0.0
        
        # 最近N天的量能
        recent_volume = df['volume'].iloc[-window:].mean()
        
        # 之前N天的量能
        previous_volume = df['volume'].iloc[-window*2:-window].mean()
        
        if previous_volume == 0:
            return 0.0
        
        # 量能比率
        ratio = recent_volume / previous_volume
        
        # 归一化到 0-1
        score = min(ratio / 2.0, 1.0)
        
        return score
    
    @staticmethod
    def calculate_turnover_rank(
        stock_symbol: str,
        all_stocks_df: pd.DataFrame,
        date: str
    ) -> float:
        """
        计算成交额排名
        
        Args:
            stock_symbol: 股票代码
            all_stocks_df: 全市场股票数据
            date: 日期
            
        Returns:
            排名百分比 (0-1, 越接近1排名越靠前)
        """
        try:
            # 获取当日所有股票的成交额
            amounts = all_stocks_df.loc[date, 'amount']
            
            # 排序
            ranked = amounts.rank(ascending=False, pct=True)
            
            # 获取目标股票的排名
            rank_pct = ranked[stock_symbol]
            
            return rank_pct
            
        except:
            return 0.5
    
    @staticmethod
    def calculate_early_start_signal(
        stock_df: pd.DataFrame,
        sector_df: pd.DataFrame,
        start_date: str,
        window: int = 5
    ) -> bool:
        """
        判断是否提前启动
        
        股票在板块启动前就开始上涨
        
        Args:
            stock_df: 个股数据
            sector_df: 板块数据
            start_date: 统计起点
            window: 提前窗口
            
        Returns:
            是否提前启动
        """
        try:
            start_idx = stock_df.index.get_loc(start_date)
            
            if start_idx < window:
                return False
            
            # 股票在起点前的涨幅
            stock_pre_return = (
                stock_df['close'].iloc[start_idx] / 
                stock_df['close'].iloc[start_idx - window] - 1
            ) * 100
            
            # 板块在起点前的涨幅
            sector_pre_return = (
                sector_df['close'].iloc[start_idx] / 
                sector_df['close'].iloc[start_idx - window] - 1
            ) * 100
            
            # 个股涨幅明显大于板块
            return stock_pre_return > sector_pre_return + 5
            
        except:
            return False
    
    @staticmethod
    def calculate_leader_score(
        symbol: str,
        stock_df: pd.DataFrame,
        benchmark_df: pd.DataFrame,
        start_date: str,
        end_date: str,
        all_stocks_df: pd.DataFrame = None
    ) -> Dict[str, float]:
        """
        综合计算龙头得分
        
        Args:
            symbol: 股票代码
            stock_df: 个股数据
            benchmark_df: 基准数据
            start_date: 统计起点
            end_date: 统计终点
            all_stocks_df: 全市场数据（可选）
            
        Returns:
            特征字典
        """
        features = {}
        
        # 1. 区间涨幅
        features['interval_return'] = LeaderFeatures.calculate_interval_return(
            stock_df, start_date, end_date
        )
        
        # 2. 相对强度
        features['relative_strength'] = LeaderFeatures.calculate_relative_strength(
            stock_df, benchmark_df, window=20
        )
        
        # 3. 量能激增
        features['volume_surge'] = LeaderFeatures.calculate_volume_surge(
            stock_df, window=20
        )
        
        # 4. 量能堆积
        features['volume_accumulation'] = LeaderFeatures.calculate_volume_accumulation(
            stock_df, window=5
        )
        
        # 5. 成交额排名
        if all_stocks_df is not None:
            features['turnover_rank'] = LeaderFeatures.calculate_turnover_rank(
                symbol, all_stocks_df, end_date
            )
        else:
            features['turnover_rank'] = 0.5
        
        # 6. 综合得分（加权平均）
        weights = {
            'interval_return': 0.3,
            'relative_strength': 0.25,
            'volume_surge': 0.15,
            'volume_accumulation': 0.15,
            'turnover_rank': 0.15
        }
        
        # 归一化区间涨幅（假设最大100%）
        normalized_return = min(features['interval_return'] / 100, 1.0)
        
        # 归一化相对强度（假设最大3倍）
        normalized_rs = min(features['relative_strength'] / 3, 1.0)
        
        # 归一化量能激增（假设最大5倍）
        normalized_vs = min(features['volume_surge'] / 5, 1.0)
        
        # 计算综合得分
        total_score = (
            normalized_return * weights['interval_return'] +
            normalized_rs * weights['relative_strength'] +
            normalized_vs * weights['volume_surge'] +
            features['volume_accumulation'] * weights['volume_accumulation'] +
            features['turnover_rank'] * weights['turnover_rank']
        )
        
        features['leader_score'] = total_score
        
        return features


if __name__ == "__main__":
    # 测试代码
    # 构造测试数据
    dates = pd.date_range('2024-01-01', '2024-12-31', freq='D')
    
    stock_data = pd.DataFrame({
        'close': np.random.randn(len(dates)).cumsum() + 100,
        'volume': np.random.randint(1000000, 10000000, len(dates)),
        'amount': np.random.randint(10000000, 100000000, len(dates))
    }, index=dates)
    
    benchmark_data = pd.DataFrame({
        'close': np.random.randn(len(dates)).cumsum() + 3000,
    }, index=dates)
    
    # 计算特征
    features = LeaderFeatures.calculate_leader_score(
        symbol='000001.SZ',
        stock_df=stock_data,
        benchmark_df=benchmark_data,
        start_date='2024-06-01',
        end_date='2024-12-31'
    )
    
    print("龙头特征:")
    for key, value in features.items():
        print(f"  {key}: {value:.4f}")
