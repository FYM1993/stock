"""
下载股票行业分类数据

使用AKShareProvider下载所有股票的行业分类
保存到 qlib_data_path/stock_industry_mapping.json
"""

import sys
from pathlib import Path
from loguru import logger

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))

from data.akshare_provider import AKShareProvider

def main():
    """下载行业映射数据"""
    
    # 配置日志
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    # 创建提供器（使用项目内路径）
    provider = AKShareProvider(qlib_data_path="qlib_data/cn_data")
    
    # 下载到项目data目录
    save_path = Path(__file__).parent.parent / "data" / "stock_industry_mapping.json"
    
    # 下载行业映射
    try:
        mapping = provider.download_stock_industry_mapping(save_path=str(save_path))
        logger.info(f"\n✅ 成功下载 {len(mapping)} 只股票的行业信息")
    except Exception as e:
        logger.error(f"❌ 下载失败: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
