#!/usr/bin/env python3
"""
从股票历史数据中计算市场情绪指标

由于 AKShare 无法获取历史情绪数据，我们从已下载的股票历史价格中统计：
- 涨跌家数
- 涨停跌停数量
- 平均涨跌幅
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
import pandas as pd
import numpy as np
import argparse
from tqdm import tqdm

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def calculate_emotion_from_price_data(
    csv_dir: Path,
    start_date: str,
    end_date: str,
    output_file: Path
):
    """
    从股票价格数据计算市场情绪
    
    Args:
        csv_dir: CSV 数据目录
        start_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
        output_file: 输出文件路径
    """
    logger.info("="*70)
    logger.info("  从股票数据计算市场情绪")
    logger.info("="*70)
    logger.info(f"日期范围: {start_date} ~ {end_date}")
    logger.info("")
    
    # 获取所有股票CSV
    csv_files = list(csv_dir.glob("[0-9]*.csv"))
    logger.info(f"找到 {len(csv_files)} 只股票")
    
    if not csv_files:
        logger.error("没有找到股票数据文件")
        return
    
    # 读取所有股票数据
    logger.info("读取股票数据...")
    all_data = []
    
    for csv_file in tqdm(csv_files, desc="读取CSV"):
        try:
            df = pd.read_csv(csv_file)
            
            # 处理列名（支持中文）
            date_col = '日期' if '日期' in df.columns else 'date'
            if date_col not in df.columns:
                continue
            
            # 添加股票代码
            df['symbol'] = csv_file.stem
            
            # 统一列名
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount',
                '涨跌幅': 'change',
                '涨跌额': 'change_amount',
                '换手率': 'turnover'
            })
            
            df['date'] = pd.to_datetime(df['date'])
            
            # 计算涨跌幅（如果没有）
            if 'change' not in df.columns:
                df = df.sort_values('date')
                df['prev_close'] = df['close'].shift(1)
                df['change'] = ((df['close'] - df['prev_close']) / df['prev_close'] * 100).fillna(0)
            
            # 筛选日期范围
            mask = (df['date'] >= start_date) & (df['date'] <= end_date)
            df = df[mask]
            
            if not df.empty:
                all_data.append(df)
        
        except Exception as e:
            logger.debug(f"读取 {csv_file.name} 失败: {e}")
    
    if not all_data:
        logger.error("没有有效的股票数据")
        return
    
    # 合并所有数据
    logger.info("合并数据并计算情绪指标...")
    combined = pd.concat(all_data, ignore_index=True)
    
    # 按日期分组统计
    emotion_list = []
    
    for date, group in tqdm(combined.groupby('date'), desc="计算情绪"):
        date_str = date.strftime('%Y-%m-%d')
        
        # 计算涨停（科创板20%，主板10%）
        limit_up_10 = len(group[group['change'] >= 9.9])  # 主板涨停
        limit_up_20 = len(group[group['change'] >= 19.9])  # 科创板涨停
        limit_up_count = limit_up_10 + limit_up_20
        
        limit_down_10 = len(group[group['change'] <= -9.9])
        limit_down_20 = len(group[group['change'] <= -19.9])
        limit_down_count = limit_down_10 + limit_down_20
        
        emotion = {
            'date': date_str,
            'total_count': len(group),
            'up_count': len(group[group['change'] > 0]),
            'down_count': len(group[group['change'] < 0]),
            'flat_count': len(group[group['change'] == 0]),
            'limit_up_count': limit_up_count,
            'limit_down_count': limit_down_count,
            'avg_pct_change': group['change'].mean(),
            'median_pct_change': group['change'].median(),
            'total_amount': group['amount'].sum() if 'amount' in group.columns else 0
        }
        
        emotion_list.append(emotion)
    
    # 保存结果
    emotion_df = pd.DataFrame(emotion_list)
    emotion_df = emotion_df.sort_values('date')
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    emotion_df.to_csv(output_file, index=False)
    
    logger.info("")
    logger.info("="*70)
    logger.info("  ✅ 计算完成")
    logger.info("="*70)
    logger.info(f"输出文件: {output_file}")
    logger.info(f"记录数: {len(emotion_df)}")
    logger.info("")
    
    # 显示统计
    logger.info("情绪指标统计:")
    logger.info(f"  涨停数量 - 平均: {emotion_df['limit_up_count'].mean():.0f}, "
               f"最大: {emotion_df['limit_up_count'].max()}, "
               f"最小: {emotion_df['limit_up_count'].min()}")
    logger.info(f"  跌停数量 - 平均: {emotion_df['limit_down_count'].mean():.0f}, "
               f"最大: {emotion_df['limit_down_count'].max()}, "
               f"最小: {emotion_df['limit_down_count'].min()}")
    logger.info(f"  平均涨跌幅 - 平均: {emotion_df['avg_pct_change'].mean():.2f}%")


def main():
    parser = argparse.ArgumentParser(description='从股票数据计算市场情绪')
    parser.add_argument('--start', type=str, help='开始日期 YYYY-MM-DD')
    parser.add_argument('--end', type=str, help='结束日期 YYYY-MM-DD')
    parser.add_argument('--recent', action='store_true', help='计算近1年数据')
    
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
    
    # 路径配置
    csv_dir = Path("qlib_data/cn_data/instruments")
    output_file = Path("data/emotion/market_emotion.csv")
    
    if not csv_dir.exists():
        logger.error(f"数据目录不存在: {csv_dir}")
        logger.error("请先下载股票数据")
        return
    
    calculate_emotion_from_price_data(csv_dir, start_date, end_date, output_file)


if __name__ == "__main__":
    main()
