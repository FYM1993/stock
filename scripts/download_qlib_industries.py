"""
下载Qlib股票的行业信息

从 data/qlib_stocks_list.txt 读取股票列表
调用AKShareProvider下载行业信息
保存到 data/stock_industry_mapping.json
"""

import sys
from pathlib import Path
from loguru import logger
import json

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))

from data.akshare_provider import AKShareProvider

def load_stock_list():
    """从文件加载股票列表"""
    stock_file = Path(__file__).parent.parent / "data" / "qlib_stocks_list.txt"
    
    if not stock_file.exists():
        logger.error(f"股票列表文件不存在: {stock_file}")
        return []
    
    with open(stock_file, 'r') as f:
        stocks = [line.strip() for line in f if line.strip()]
    
    logger.info(f"从文件加载 {len(stocks)} 只股票")
    return stocks

def main():
    """主函数"""
    # 配置日志
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    logger.info("=" * 60)
    logger.info("下载Qlib股票行业信息")
    logger.info("=" * 60)
    
    # 加载股票列表
    stocks = load_stock_list()
    if not stocks:
        logger.error("未加载到股票列表")
        return 1
    
    logger.info(f"待下载行业信息: {len(stocks)} 只股票")
    logger.info(f"预计耗时: {len(stocks) * 1.5 / 60:.0f} 分钟（含随机延迟）")
    logger.warning("⚠️ 这将需要较长时间，建议后台运行")
    logger.warning("⚠️ 每50只保存一次，可随时中断")
    
    # 保存路径
    save_path = Path(__file__).parent.parent / "data" / "stock_industry_mapping.json"
    
    # 加载已有数据（如果存在）
    existing_count = 0
    if save_path.exists():
        with open(save_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)
            existing_count = len(existing)
        logger.info(f"已有 {existing_count} 只股票的数据，将继续下载")
    
    # 创建提供器（使用模拟路径，实际不会用到）
    provider = AKShareProvider(qlib_data_path="qlib_data/cn_data")
    
    # 重写get_stock_list方法，返回我们的列表
    provider.get_stock_list = lambda **kwargs: stocks
    
    try:
        logger.info("\n开始下载...")
        
        mapping = provider.download_stock_industry_mapping(
            save_path=str(save_path),
            delay=1.0  # 1秒基础延迟 + 0-0.5秒随机
        )
        
        logger.info(f"\n✅ 下载完成!")
        logger.info(f"成功: {len(mapping)} 只")
        logger.info(f"增量: {len(mapping) - existing_count} 只")
        
    except KeyboardInterrupt:
        logger.warning("\n⚠️ 用户中断下载")
        logger.info("已下载的数据已保存")
        return 0
    except Exception as e:
        logger.error(f"\n❌ 下载失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
