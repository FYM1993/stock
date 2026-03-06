#!/usr/bin/env python3
"""
批量转换所有股票和指数数据为Qlib格式（对齐日历）
"""

from pathlib import Path
import pandas as pd
import numpy as np
from loguru import logger
from tqdm import tqdm

# 读取日历
calendar_file = Path('./qlib_data/cn_data/calendars/day.txt')
calendar_dates = calendar_file.read_text().strip().split('\n')
calendar = pd.DatetimeIndex(pd.to_datetime(calendar_dates))

logger.info(f'日历: {len(calendar)} 个交易日 ({calendar[0].date()} ~ {calendar[-1].date()})')

# 获取所有CSV
csv_dir = Path('qlib_data/cn_data/instruments')
csv_files = sorted(csv_dir.glob('[0-9]*.csv'))

logger.info(f'找到 {len(csv_files)} 个CSV文件')
logger.info('开始批量转换...')
logger.info('')

success = 0
fail = 0

for csv_file in tqdm(csv_files, desc="转换进度"):
    symbol = csv_file.stem
    
    try:
        # 读取CSV
        df = pd.read_csv(csv_file)
        date_col = '日期' if '日期' in df.columns else 'date'
        df['date'] = pd.to_datetime(df[date_col])
        df = df.set_index('date').sort_index()
        
        # 对齐到日历
        aligned = pd.DataFrame(index=calendar)
        for col in ['open', 'close', 'high', 'low', 'volume']:
            if col in df.columns:
                aligned[col] = df[col]
        
        # 找到有效数据范围
        first_valid = aligned['close'].first_valid_index()
        last_valid = aligned['close'].last_valid_index()
        
        if first_valid is None:
            fail += 1
            continue
        
        start_index = calendar.get_loc(first_valid)
        end_index = calendar.get_loc(last_valid)
        
        # 创建目标目录
        feature_dir = Path(f'qlib_data/cn_data/features/{symbol}')
        feature_dir.mkdir(parents=True, exist_ok=True)
        
        # 转换各字段
        for field in ['open', 'close', 'high', 'low', 'volume']:
            if field not in aligned.columns:
                continue
            
            bin_file = feature_dir / f'{field}.day.bin'
            
            # 只保存有效数据范围
            valid_data = aligned[field].iloc[start_index:end_index+1].values.astype(np.float32)
            
            # 写入：start_index + 数据
            with open(bin_file, 'wb') as f:
                f.write(np.array([start_index], dtype=np.float32).tobytes())
                f.write(valid_data.tobytes())
        
        success += 1
        
    except Exception as e:
        logger.debug(f'{symbol} 失败: {e}')
        fail += 1

logger.info('')
logger.info(f'✅ 转换完成: 成功 {success}, 失败 {fail}')
