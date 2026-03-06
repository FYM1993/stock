#!/usr/bin/env python3
"""
下载市场情绪数据

使用场景：
- 下载市场每日情绪数据（涨跌家数、涨停跌停等）
- 配合股票价格数据用于情绪策略回测

特点：
- 支持指定日期范围
- 自动跳过周末和节假日
- 断点续传
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
import argparse

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.emotion_data import EmotionDataManager


def download_emotion_data(start_date: str, end_date: str):
    """
    下载情绪数据
    
    Args:
        start_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
    """
    logger.info("="*70)
    logger.info("  下载市场情绪数据")
    logger.info("="*70)
    logger.info("")
    logger.info(f"日期范围: {start_date} 至 {end_date}")
    logger.info("")
    
    emotion_manager = EmotionDataManager()
    
    # 解析日期
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    current_date = start_dt
    success_count = 0
    fail_count = 0
    skip_count = 0
    
    logger.info("开始下载...")
    logger.info("")
    
    while current_date <= end_dt:
        date_str = current_date.strftime('%Y-%m-%d')
        
        try:
            # 检查是否已存在
            existing = emotion_manager.get_emotion_on_date(date_str)
            if existing:
                skip_count += 1
                logger.debug(f"跳过 {date_str}（已存在）")
            else:
                emotion_manager.update_emotion_data(date_str)
                success_count += 1
                
                # 每10条显示进度
                if (success_count + skip_count) % 10 == 0:
                    logger.info(f"  进度: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}")
        
        except Exception as e:
            fail_count += 1
            logger.debug(f"获取 {date_str} 失败: {e}")
        
        current_date += timedelta(days=1)
    
    logger.info("")
    logger.info("="*70)
    logger.info("  下载完成")
    logger.info("="*70)
    logger.info("")
    logger.info(f"成功: {success_count} 条")
    logger.info(f"跳过: {skip_count} 条（已存在）")
    logger.info(f"失败: {fail_count} 条")
    logger.info("")


def main():
    parser = argparse.ArgumentParser(description='下载市场情绪数据')
    parser.add_argument('--start', type=str, help='开始日期 YYYY-MM-DD')
    parser.add_argument('--end', type=str, help='结束日期 YYYY-MM-DD')
    parser.add_argument('--recent', action='store_true', help='下载近1年数据')
    
    args = parser.parse_args()
    
    # 确定日期范围
    if args.recent:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    elif args.start and args.end:
        start_date = args.start
        end_date = args.end
    else:
        # 默认：近1年
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    logger.info(f"下载情绪数据: {start_date} 至 {end_date}")
    download_emotion_data(start_date, end_date)


if __name__ == "__main__":
    main()
