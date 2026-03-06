#!/usr/bin/env python3
"""
下载股票指数数据

下载主要指数的历史数据，用于策略的市场环境判断
"""

import sys
from pathlib import Path
from loguru import logger
import pandas as pd
import akshare as ak
from datetime import datetime
import argparse

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def download_index_data(start_date: str = '2020-01-01', end_date: str = None):
    """
    下载主要指数数据
    
    Args:
        start_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD (None表示今天)
    """
    logger.info("="*70)
    logger.info("  下载指数数据")
    logger.info("="*70)
    logger.info("")
    
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    logger.info(f"日期范围: {start_date} 至 {end_date}")
    logger.info("")
    
    # 主要指数列表
    indices = {
        'sh000001': '上证指数',
        'sz399001': '深证成指',
        'sz399006': '创业板指',
        'sh000300': '沪深300',
        'sh000905': '中证500'
    }
    
    output_dir = Path("qlib_data/cn_data/instruments")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    fail_count = 0
    
    for code, name in indices.items():
        try:
            logger.info(f"下载 {name} ({code})...")
            
            # 下载数据
            df = ak.stock_zh_index_daily(symbol=code)
            
            # 筛选日期范围
            df['date'] = pd.to_datetime(df['date'])
            mask = (df['date'] >= start_date) & (df['date'] <= end_date)
            df = df[mask]
            
            if df.empty:
                logger.warning(f"  {name}: 无数据")
                fail_count += 1
                continue
            
            # 重命名列，保持与股票数据一致
            df = df.rename(columns={
                'date': '日期'
            })
            
            # 转换代码格式：sh000001 -> 000001.SH
            if code.startswith('sh'):
                qlib_code = code[2:].upper() + '.SH'
            elif code.startswith('sz'):
                qlib_code = code[2:].upper() + '.SZ'
            else:
                qlib_code = code.upper()
            
            # 保存CSV
            csv_file = output_dir / f"{qlib_code}.csv"
            df[['日期', 'open', 'close', 'high', 'low', 'volume']].to_csv(
                csv_file, 
                index=False
            )
            
            logger.info(f"  ✓ {name}: {len(df)} 条记录 -> {csv_file.name}")
            success_count += 1
            
        except Exception as e:
            logger.error(f"  ✗ {name}: {e}")
            fail_count += 1
    
    logger.info("")
    logger.info("="*70)
    logger.info("  下载完成")
    logger.info("="*70)
    logger.info(f"成功: {success_count} 个指数")
    logger.info(f"失败: {fail_count} 个指数")
    logger.info("")


def main():
    parser = argparse.ArgumentParser(description='下载指数数据')
    parser.add_argument('--start', type=str, default='2020-01-01', help='开始日期 YYYY-MM-DD')
    parser.add_argument('--end', type=str, help='结束日期 YYYY-MM-DD')
    
    args = parser.parse_args()
    
    download_index_data(start_date=args.start, end_date=args.end)


if __name__ == "__main__":
    main()
