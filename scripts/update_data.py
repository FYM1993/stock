"""
增量更新数据

在已有 Qlib 数据基础上，补充最新交易日的数据

用法:
  python scripts/update_data.py                   # 更新近1年
  python scripts/update_data.py --start 2025-01-01  # 指定起始
  python scripts/update_data.py --max 500           # 只更新前500只
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from data.adata_provider import ADataProvider
from data.data_converter import QlibDataConverter


def main():
    parser = argparse.ArgumentParser(description="增量更新A股数据")
    parser.add_argument("--start", type=str, default=None, help="开始日期(默认近1年)")
    parser.add_argument("--end", type=str, default=None, help="结束日期")
    parser.add_argument("--max", type=int, default=None, help="最大下载数")
    parser.add_argument("--delay", type=float, default=0.3, help="请求间隔(秒)")
    args = parser.parse_args()

    if args.start is None:
        args.start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    logger.info("=" * 60)
    logger.info("增量更新A股数据")
    logger.info(f"  时间范围: {args.start} ~ {args.end or '至今'}")
    logger.info("=" * 60)

    provider = ADataProvider()

    logger.info("[1] 更新指数...")
    for idx_code in ["000300", "000905", "000001"]:
        provider.download_index(idx_code, args.start)

    logger.info("[2] 更新股票...")
    provider.download_all(
        start_date=args.start,
        end_date=args.end,
        delay=args.delay,
        max_stocks=args.max,
    )

    logger.info("[3] 转换为Qlib格式...")
    converter = QlibDataConverter()
    converter.convert_batch(append=False)

    logger.info("完成!")


if __name__ == "__main__":
    main()
