"""
数据采集脚本

定期采集市场数据，包括：
1. 个股日线数据
2. 市场情绪数据
3. 板块数据
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
import argparse

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from data.akshare_provider import AKShareProvider
from data.emotion_data import EmotionDataManager


def collect_daily_data(date: str = None):
    """
    采集当日数据
    
    Args:
        date: 日期，格式 '20240101'，None表示今天
    """
    if date is None:
        date = datetime.now().strftime('%Y%m%d')
    
    logger.info(f"采集日期: {date}")
    
    provider = AKShareProvider()
    
    # 1. 更新市场情绪数据
    logger.info("1. 更新市场情绪数据...")
    emotion_manager = EmotionDataManager()
    emotion_manager.update_emotion_data(date)
    
    # 2. 更新个股数据（增量更新）
    logger.info("2. 更新个股数据...")
    # 这里可以选择只更新关注的股票，而不是全市场
    # provider.download_all_stocks(start_date=date, end_date=date, delay=0.05)
    
    logger.info("数据采集完成")


def collect_historical_data(
    start_date: str,
    end_date: str = None
):
    """
    采集历史数据
    
    Args:
        start_date: 开始日期，格式 '20200101'
        end_date: 结束日期，None表示今天
    """
    if end_date is None:
        end_date = datetime.now().strftime('%Y%m%d')
    
    logger.info(f"采集历史数据: {start_date} - {end_date}")
    
    provider = AKShareProvider()
    
    # 1. 下载所有股票数据
    logger.info("1. 下载股票数据...")
    provider.download_all_stocks(
        start_date=start_date,
        end_date=end_date,
        delay=0.1
    )
    
    # 2. 采集市场情绪数据
    logger.info("2. 采集市场情绪数据...")
    emotion_manager = EmotionDataManager()
    emotion_manager.collect_historical_data(start_date, end_date)
    
    logger.info("历史数据采集完成")


def update_watchlist(symbols: list):
    """
    更新自选股数据
    
    Args:
        symbols: 股票代码列表，如 ['000001.SZ', '600000.SH']
    """
    logger.info(f"更新自选股: {len(symbols)} 只")
    
    provider = AKShareProvider()
    
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
    
    for symbol in symbols:
        logger.info(f"更新 {symbol}...")
        df = provider.get_stock_daily(symbol, start_date, end_date)
        
        if df is not None:
            provider._save_stock_data(symbol, df)
    
    logger.info("自选股更新完成")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='数据采集工具')
    
    parser.add_argument(
        '--mode',
        type=str,
        choices=['daily', 'historical', 'watchlist'],
        default='daily',
        help='采集模式'
    )
    
    parser.add_argument(
        '--start-date',
        type=str,
        default='20200101',
        help='开始日期（历史模式）'
    )
    
    parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='结束日期（历史模式）'
    )
    
    parser.add_argument(
        '--date',
        type=str,
        default=None,
        help='指定日期（日常模式）'
    )
    
    parser.add_argument(
        '--symbols',
        type=str,
        nargs='+',
        default=[],
        help='股票代码列表（自选股模式）'
    )
    
    args = parser.parse_args()
    
    logger.info("="*60)
    logger.info("数据采集工具")
    logger.info("="*60)
    
    if args.mode == 'daily':
        collect_daily_data(args.date)
    elif args.mode == 'historical':
        collect_historical_data(args.start_date, args.end_date)
    elif args.mode == 'watchlist':
        if not args.symbols:
            logger.error("请指定股票代码列表")
            return
        update_watchlist(args.symbols)
    
    logger.info("\n完成!")


if __name__ == "__main__":
    main()
