"""
数据采集脚本

使用 adata 下载A股行情数据，转换为 Qlib 格式
含 amount/vwap 字段，保存股票名称信息用于 ST/科创板过滤

用法:
  python scripts/collect_data.py                        # 下载全部(默认2020年起)
  python scripts/collect_data.py --start 2023-01-01     # 指定起始日期
  python scripts/collect_data.py --max 100              # 只下载前100只(测试)
  python scripts/collect_data.py --index-only           # 只下载指数
  python scripts/collect_data.py --skip-excluded        # 跳过科创板/北交所
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
    parser.add_argument("--delay", type=float, default=0.2, help="请求间隔(秒)")
    parser.add_argument("--index-only", action="store_true", help="只下载指数")
    parser.add_argument("--no-convert", action="store_true", help="只下载不转换")
    parser.add_argument("--skip-excluded", action="store_true", default=True,
                        help="跳过科创板/北交所(默认跳过)")
    parser.add_argument("--with-vwap", action="store_true", default=True,
                        help="包含 amount/vwap 字段(默认启用，用于预测VWAP回测与实盘建议价)")
    parser.add_argument("--no-vwap", action="store_true",
                        help="不包含 amount/vwap，节省存储；后续可用 update_vwap_data.py 补充")
    args = parser.parse_args()
    args.with_vwap = args.with_vwap and not args.no_vwap

    logger.info("=" * 60)
    logger.info("A股数据采集 (adata)" + (" — 含 amount/vwap" if args.with_vwap else " — 不含 amount/vwap"))
    logger.info("=" * 60)

    provider = ADataProvider()

    # [0] 保存股票信息 (名称、ST标记、科创板标记等)
    logger.info("[0] 获取股票列表并保存信息...")
    stock_df = provider.get_stock_list()
    stock_info = provider.save_stock_info(stock_df)

    # [1] 下载指数
    logger.info("[1] 下载指数数据...")
    for idx_code in ["000300", "000905", "000001"]:
        provider.download_index(idx_code, args.start)

    if args.index_only:
        logger.info("完成(仅指数)")
        return

    # [2] 下载股票 (含 amount/vwap)
    if args.skip_excluded:
        excluded_codes = set()
        for _, row in stock_info.iterrows():
            if row.get("is_kcb", False) or row.get("is_bj", False):
                excluded_codes.add(row["stock_code"])
        n_before = len(stock_df)
        stock_df = stock_df[~stock_df["stock_code"].isin(excluded_codes)]
        logger.info(f"  跳过科创板/北交所: {n_before} -> {len(stock_df)} 只")

    codes = stock_df["stock_code"].tolist()
    exchanges = dict(zip(stock_df["stock_code"], stock_df["exchange"]))

    if args.max:
        codes = codes[:args.max]

    total = len(codes)
    success = 0
    failed = 0

    logger.info(f"[2] 下载 {total} 只股票 ({args.start} ~ {args.end or '至今'})...")

    csv_dir = provider.qlib_data_path / "instruments"
    csv_dir.mkdir(parents=True, exist_ok=True)

    import time
    for idx, code in enumerate(codes, 1):
        try:
            df = provider.get_stock_daily(code, args.start, args.end)
            if df is not None and len(df) > 0:
                if not args.with_vwap:
                    df = df.drop(columns=["amount", "vwap"], errors="ignore")
                ex = exchanges.get(code, "SZ")
                symbol = f"{code}.{ex}"
                csv_path = csv_dir / f"{symbol}.csv"
                df.to_csv(csv_path)
                success += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.debug(f"{code}: {e}")

        if idx % 100 == 0:
            logger.info(f"  进度 {idx}/{total} | 成功 {success} | 失败 {failed}")

        time.sleep(args.delay)

    logger.info(f"下载完成: 成功 {success}/{total}, 失败 {failed}")

    # [3] 转换为Qlib二进制格式
    if not args.no_convert:
        logger.info("[3] 转换为Qlib格式...")
        converter = QlibDataConverter()
        converter.convert_batch(append=False)

    logger.info("全部完成!")


if __name__ == "__main__":
    main()
