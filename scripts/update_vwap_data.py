"""
增量更新脚本: 为已有股票数据补充 amount/vwap 字段 + 保存股票名称列表

用法:
  python scripts/update_vwap_data.py                  # 全量更新
  python scripts/update_vwap_data.py --max 50         # 测试前50只
  python scripts/update_vwap_data.py --info-only      # 只更新股票信息
"""

import sys
import argparse
import time
import numpy as np
import pandas as pd
from pathlib import Path
from loguru import logger

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from data.adata_provider import ADataProvider
from data.data_converter import QlibDataConverter


def update_vwap_for_stock(provider, converter, symbol, start_date, end_date):
    """为单只股票下载 amount 并计算 vwap，写入 Qlib 二进制"""
    code = symbol.split(".")[0]
    target_dir = converter.bin_dir / symbol

    if not target_dir.exists():
        return False

    try:
        df = provider.get_stock_daily(code, start_date, end_date)
        if df is None or df.empty:
            return False

        if converter.calendar is not None:
            aligned = pd.DataFrame(index=converter.calendar)
            for col in ["amount", "vwap"]:
                aligned[col] = df[col] if col in df.columns else np.nan
            df = aligned

        for field in ["amount", "vwap"]:
            if field not in df.columns:
                continue
            data = df[field].values.astype(np.float32)
            bin_file = target_dir / f"{field}.day.bin"
            with open(bin_file, "wb") as f:
                f.write(data.tobytes())

        return True
    except Exception as e:
        logger.debug(f"{symbol}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="补充 amount/vwap 数据")
    parser.add_argument("--start", default="2020-01-01", help="开始日期")
    parser.add_argument("--end", default=None, help="结束日期")
    parser.add_argument("--max", type=int, default=None, help="最大更新数")
    parser.add_argument("--delay", type=float, default=0.3, help="请求间隔(秒)")
    parser.add_argument("--info-only", action="store_true", help="只更新股票信息")
    args = parser.parse_args()

    provider = ADataProvider()

    logger.info("=" * 60)
    logger.info("更新股票数据: amount/vwap + 股票信息")
    logger.info("=" * 60)

    # 1. 保存股票信息
    logger.info("[1] 保存股票信息列表 (含 ST/科创板/北交所 标记)...")
    stock_info = provider.save_stock_info()

    if args.info_only:
        logger.info("完成(仅股票信息)")
        return

    # 2. 获取已有数据的股票列表
    converter = QlibDataConverter()
    features_dir = converter.bin_dir
    existing_symbols = sorted([d.name for d in features_dir.iterdir() if d.is_dir()])

    if args.max:
        existing_symbols = existing_symbols[: args.max]

    total = len(existing_symbols)
    logger.info(f"[2] 更新 {total} 只股票的 amount/vwap 数据...")

    success = 0
    failed = 0
    skipped = 0

    for idx, symbol in enumerate(existing_symbols, 1):
        vwap_file = features_dir / symbol / "vwap.day.bin"
        if vwap_file.exists():
            skipped += 1
            if idx % 500 == 0:
                logger.info(f"  进度 {idx}/{total} | 成功 {success} | 跳过 {skipped} | 失败 {failed}")
            continue

        ok = update_vwap_for_stock(provider, converter, symbol, args.start, args.end)
        if ok:
            success += 1
        else:
            failed += 1

        if idx % 100 == 0:
            logger.info(f"  进度 {idx}/{total} | 成功 {success} | 跳过 {skipped} | 失败 {failed}")

        time.sleep(args.delay)

    logger.info(f"完成! 成功 {success}, 跳过 {skipped}, 失败 {failed}")


if __name__ == "__main__":
    main()
