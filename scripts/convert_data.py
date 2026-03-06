#!/usr/bin/env python3
"""
数据转换脚本

将 CSV 格式的数据转换为 Qlib 二进制格式
"""

import sys
from pathlib import Path
from loguru import logger
import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.data_converter import QlibDataConverter


def main():
    """主函数"""
    logger.info("="*70)
    logger.info("  数据格式转换")
    logger.info("="*70)
    logger.info("")
    
    qlib_data_path = "./qlib_data/cn_data"
    
    # 1. 转换 CSV → 二进制
    logger.info("步骤 1/2: 转换 CSV → 二进制格式...")
    converter = QlibDataConverter(qlib_data_path=qlib_data_path)
    converter.convert_batch(append=False)  # 覆盖模式
    
    # 2. 更新交易日历
    logger.info("")
    logger.info("步骤 2/2: 更新交易日历...")
    csv_dir = Path(qlib_data_path) / "instruments"
    csv_files = list(csv_dir.glob("[0-9]*.csv"))
    
    if not csv_files:
        logger.warning("没有找到 CSV 文件")
        return
    
    all_dates = set()
    sample_size = min(100, len(csv_files))
    
    for csv in csv_files[:sample_size]:
        try:
            df = pd.read_csv(csv)
            # 支持中文和英文列名
            date_col = '日期' if '日期' in df.columns else 'date'
            if date_col in df.columns:
                dates = pd.to_datetime(df[date_col]).dt.strftime('%Y-%m-%d').tolist()
                all_dates.update(dates)
        except Exception as e:
            logger.debug(f"跳过 {csv.name}: {e}")
    
    # 读取旧日历并合并
    calendar_file = Path(qlib_data_path) / "calendars" / "day.txt"
    if calendar_file.exists():
        old_dates = set(calendar_file.read_text().strip().split('\n'))
        all_dates = old_dates.union(all_dates)
    
    all_dates = sorted([d for d in all_dates if d and d.strip()])
    
    # 写入日历
    calendar_file.parent.mkdir(parents=True, exist_ok=True)
    calendar_file.write_text('\n'.join(all_dates) + '\n')
    
    logger.info(f"✓ 交易日历已更新: {len(all_dates)} 个交易日")
    logger.info(f"  最早: {all_dates[0]}")
    logger.info(f"  最新: {all_dates[-1]}")
    
    # 3. 更新 instruments 文件
    logger.info("")
    logger.info("步骤 3/3: 更新 instruments 文件...")
    all_txt = Path(qlib_data_path) / "instruments" / "all.txt"
    if all_txt.exists():
        lines = all_txt.read_text().split('\n')
        new_lines = []
        
        for line in lines:
            if line.strip():
                parts = line.split('\t')
                if len(parts) == 3:
                    # 更新结束日期
                    parts[2] = all_dates[-1]
                    line = '\t'.join(parts)
            new_lines.append(line)
        
        all_txt.write_text('\n'.join(new_lines))
        logger.info("✓ instruments/all.txt 已更新")
    
    logger.info("")
    logger.info("="*70)
    logger.info("  ✅ 数据转换完成！")
    logger.info("="*70)
    logger.info("")


if __name__ == "__main__":
    main()
