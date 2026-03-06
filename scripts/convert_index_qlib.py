#!/usr/bin/env python3
"""
使用 Qlib 官方 API 转换指数数据
"""

from pathlib import Path
import pandas as pd
import numpy as np
from qlib.data.storage import CalendarStorage, InstrumentStorage, FeatureStorage
from qlib.config import C
import qlib

# 初始化 Qlib
qlib.init(provider_uri='./qlib_data/cn_data', region='cn')

# 读取日历
calendar_file = Path('./qlib_data/cn_data/calendars/day.txt')
calendar_dates = calendar_file.read_text().strip().split('\n')
calendar = pd.DatetimeIndex(pd.to_datetime(calendar_dates))

print(f'日历: {len(calendar)} 个交易日 ({calendar[0].date()} ~ {calendar[-1].date()})')

# 指数列表
indices = {
    '000001.SH': '上证指数',
    '000300.SH': '沪深300',
    '000905.SH': '中证500',
    '399001.SZ': '深证成指',
    '399006.SZ': '创业板指'
}

# 转换每个指数
for code, name in indices.items():
    print(f'\n处理 {name} ({code})...')
    
    # 读取CSV
    csv_file = Path(f'qlib_data/cn_data/instruments/{code}.csv')
    if not csv_file.exists():
        print(f'  ✗ CSV不存在')
        continue
    
    df = pd.read_csv(csv_file)
    df['date'] = pd.to_datetime(df['日期'])
    df = df.set_index('date').sort_index()
    
    print(f'  CSV数据: {len(df)} 行 ({df.index[0].date()} ~ {df.index[-1].date()})')
    
    # 对齐到日历
    aligned = pd.DataFrame(index=calendar)
    for col in ['open', 'close', 'high', 'low', 'volume']:
        if col in df.columns:
            aligned[col] = df[col]
    
    # 找到第一个和最后一个有效数据的位置
    first_valid_idx = aligned['close'].first_valid_index()
    last_valid_idx = aligned['close'].last_valid_index()
    
    if first_valid_idx is None:
        print(f'  ✗ 没有有效数据')
        continue
    
    start_index = calendar.get_loc(first_valid_idx)
    end_index = calendar.get_loc(last_valid_idx)
    
    valid_count = aligned['close'].notna().sum()
    print(f'  有效数据: {valid_count} 行')
    print(f'  索引范围: {start_index} ~ {end_index}')
    
    # 使用 Qlib 的 FeatureStorage API 写入
    feature_dir = Path(f'qlib_data/cn_data/features/{code}')
    feature_dir.mkdir(parents=True, exist_ok=True)
    
    for field in ['open', 'close', 'high', 'low', 'volume']:
        if field not in aligned.columns:
            continue
        
        bin_file = feature_dir / f'{field}.day.bin'
        
        # 只保存有效数据范围（从start_index到end_index）
        valid_data = aligned[field].iloc[start_index:end_index+1].values.astype(np.float32)
        
        # 写入：前4字节是start_index，然后是有效数据
        with open(bin_file, 'wb') as f:
            # 写入 start_index（作为 float32）
            f.write(np.array([start_index], dtype=np.float32).tobytes())
            # 写入数据
            f.write(valid_data.tobytes())
        
        print(f'    ✓ {field}.day.bin: start={start_index}, count={len(valid_data)}')
    
    print(f'  ✅ {name} 转换完成')

print('\n完成！')
