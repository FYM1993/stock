"""
数据采集脚本

使用 adata 下载A股行情数据，转换为 Qlib 格式

用法:
  python scripts/collect_data.py                        # 下载全部(默认2020年起)
  python scripts/collect_data.py --start 2023-01-01     # 指定起始日期
  python scripts/collect_data.py --max 100              # 只下载前100只(测试)
  python scripts/collect_data.py --index-only           # 只下载指数
"""

import sys
import argparse
from pathlib import Path
from loguru import logger

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from data.adata_provider import ADataProvider
from data.data_converter import QlibDataConverter


def main():
    parser = argparse.ArgumentParser(description="A股数据采集(adata)")
    parser.add_argument("--start", type=str, default="2020-01-01", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="结束日期")
    parser.add_argument("--max", type=int, default=None, help="最大下载数(测试用)")
    parser.add_argument("--delay", type=float, default=0.3, help="请求间隔(秒)")
    parser.add_argument("--index-only", action="store_true", help="只下载指数")
    parser.add_argument("--no-convert", action="store_true", help="只下载不转换")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("A股数据采集 (adata)")
    logger.info("=" * 60)

    provider = ADataProvider()

    # 下载指数
    logger.info("[1] 下载指数数据...")
    for idx_code in ["000300", "000905", "000001"]:
        provider.download_index(idx_code, args.start)

    if args.index_only:
        logger.info("完成(仅指数)")
        return

    # 下载股票
    logger.info(f"[2] 下载股票数据 ({args.start} ~ {args.end or '至今'})...")
    provider.download_all(
        start_date=args.start,
        end_date=args.end,
        delay=args.delay,
        max_stocks=args.max,
    )

    # 转换为Qlib二进制格式
    if not args.no_convert:
        logger.info("[3] 转换为Qlib格式...")
        converter = QlibDataConverter()
        converter.convert_batch(append=False)

    logger.info("完成!")


if __name__ == "__main__":
    main()
