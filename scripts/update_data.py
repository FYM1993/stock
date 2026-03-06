#!/usr/bin/env python3
"""
补充最新数据脚本

使用场景：
- 已有 Qlib 官方数据（2020-2024.5）
- 想要补充最新数据（2024.5-至今）
- 可以在后台运行，不影响使用官方数据进行回测

特点：
- 支持活跃度过滤（推荐）
- 支持断点续传
- 可随时停止和恢复
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from data.akshare_provider import AKShareProvider


def update_to_latest(
    start_date: str,  # YYYYMMDD
    end_date: str,    # YYYYMMDD
    data_path: str = "./qlib_data/cn_data",
    filter_inactive: bool = True,
    active_threshold: float = 0.2,
    auto_confirm: bool = False
):
    """
    下载指定时间范围的数据
    
    Args:
        start_date: 开始日期 YYYYMMDD
        end_date: 结束日期 YYYYMMDD
        data_path: 数据存储路径
        filter_inactive: 是否过滤不活跃股票
        active_threshold: 活跃度阈值（保留前N%）
        auto_confirm: 是否自动确认
    """
    
    logger.info("="*70)
    logger.info("  下载数据")
    logger.info("="*70)
    logger.info("")
    logger.info("📊 数据范围:")
    logger.info(f"  开始日期: {start_date}")
    logger.info(f"  结束日期: {end_date}")
    logger.info("")
    
    # 计算天数
    start = datetime.strptime(start_date, '%Y%m%d')
    end = datetime.strptime(end_date, '%Y%m%d')
    days = (end - start).days
    
    if filter_inactive:
        stocks = int(4900 * active_threshold)
        logger.info(f"⚡ 活跃度过滤: 启用")
        logger.info(f"  保留: 成交额前 {active_threshold*100:.0f}% (约 {stocks} 只股票)")
        logger.info(f"  排除: 成交额后 {(1-active_threshold)*100:.0f}% (约 {4900-stocks} 只)")
    else:
        stocks = 4900
        logger.info(f"📊 下载全市场: {stocks} 只股票")
    
    # 估算时间
    estimated_hours = days * stocks * 1.5 / 3600
    logger.info("")
    logger.info("⏱️  预计时间:")
    logger.info(f"  约 {estimated_hours:.1f} 小时")
    logger.info("")
    logger.info("💡 提示:")
    logger.info("  - 可以让脚本在后台运行")
    logger.info("  - 可以随时按 Ctrl+C 停止")
    logger.info("  - 已下载的数据会保存，可断点续传")
    logger.info("  - 不影响使用官方数据进行回测")
    logger.info("="*70)
    logger.info("")
    
    # 确认开始
    if not auto_confirm:
        user_input = input("按回车键开始下载（或输入 n 取消）: ").strip().lower()
        if user_input == 'n':
            logger.info("已取消")
            return
    else:
        logger.info("🚀 自动确认模式，立即开始下载...")
    
    # 开始下载
    logger.info("")
    logger.info("开始下载...")
    logger.info("")
    
    provider = AKShareProvider(qlib_data_path=data_path)
    
    try:
        # 1. 下载基准指数数据（沪深300）
        logger.info("步骤 1/3: 下载基准指数数据...")
        provider.download_index('sh000300', start_date=start_date, end_date=end_date)
        provider.download_index('sh000905', start_date=start_date, end_date=end_date)
        logger.info("")
        
        # 2. 下载股票价格数据
        logger.info("步骤 2/3: 下载股票价格数据...")
        provider.download_all_stocks(
            start_date=start_date,
            end_date=end_date,
            delay=1.5,
            random_delay=True,
            filter_inactive=filter_inactive,
            active_threshold=active_threshold
        )
        
        logger.info("")
        logger.info("="*70)
        logger.info("  ✅ 数据下载完成！")
        logger.info("="*70)
        logger.info("")
        logger.info("💡 提示：")
        logger.info("  - 数据已下载为 CSV 格式")
        logger.info("  - 需要运行数据转换才能使用")
        logger.info("")
        
    except KeyboardInterrupt:
        logger.info("")
        logger.info("="*70)
        logger.info("  ⚠️  下载已停止")
        logger.info("="*70)
        logger.info("")
        logger.info("💡 已下载的数据已保存，下次运行时可继续")
        logger.info("   重新运行此脚本即可继续下载")
        
    except Exception as e:
        logger.error(f"下载失败: {e}")
        raise


def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='补充 Qlib 最新数据')
    parser.add_argument('--auto', action='store_true', help='自动确认，无需交互')
    parser.add_argument('--no-filter', action='store_true', help='不启用活跃度过滤')
    parser.add_argument('--recent', action='store_true', help='只下载近1年数据（快速模式）')
    parser.add_argument('--start', type=str, help='开始日期 YYYYMMDD')
    parser.add_argument('--end', type=str, help='结束日期 YYYYMMDD')
    args = parser.parse_args()
    
    logger.info("="*70)
    logger.info("  数据补充工具")
    logger.info("="*70)
    logger.info("")
    
    # 确定时间范围
    if args.start and args.end:
        # 使用指定时间
        start_date = args.start
        end_date = args.end
        logger.info(f"时间范围: {args.start} - {args.end}")
    elif args.recent:
        # 最近1年
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        logger.info("模式: 近1年数据（快速）")
    else:
        # 默认：最近1年
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        logger.info("模式: 默认（近1年）")
    
    logger.info("")
    
    # 检查数据目录（如果不存在则创建）
    data_path = "./qlib_data/cn_data"
    Path(data_path).mkdir(parents=True, exist_ok=True)
    
    # 决定是否启用活跃度过滤
    if args.auto:
        filter_inactive = not args.no_filter  # 自动模式默认启用，除非指定--no-filter
        logger.info("⚡ 活跃度过滤 + 冷门股排除:")
        logger.info("  - 只下载活跃股票（近期曾进入成交额前20%）")
        logger.info("  - 排除从未成为热点的股票")
        logger.info("  - 适合情绪、动量等策略")
        logger.info("  - 节省约 80% 的时间")
        logger.info("")
        if filter_inactive:
            logger.info("✅ 已启用严格过滤（自动模式）")
        else:
            logger.info("⚠️  已关闭活跃度过滤（将下载全市场）")
    else:
        # 交互模式
        logger.info("⚡ 活跃度过滤 + 冷门股排除:")
        logger.info("  - 只下载活跃股票（近期曾进入成交额前20%）")
        logger.info("  - 排除从未成为热点的股票")
        logger.info("  - 适合情绪、动量等策略")
        logger.info("  - 节省约 80% 的时间")
        logger.info("")
        
        filter_input = input("是否启用严格过滤？(y/n，默认 y): ").strip().lower()
        filter_inactive = filter_input != 'n'  # 默认启用
        
        if filter_inactive:
            logger.info("✅ 已启用严格过滤")
        else:
            logger.info("⚠️  已关闭活跃度过滤（将下载全市场）")
    
    logger.info("")
    
    # 开始更新
    update_to_latest(
        start_date=start_date,
        end_date=end_date,
        data_path=data_path,
        filter_inactive=filter_inactive,
        active_threshold=0.2,
        auto_confirm=args.auto
    )


if __name__ == "__main__":
    main()
