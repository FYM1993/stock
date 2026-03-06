#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用已有的AKShareProvider下载行业映射
使用 stock_individual_info_em 接口（个股信息）
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'data'))

from akshare_provider import AKShareProvider
from loguru import logger

def main():
    """使用AKShareProvider下载行业映射"""
    
    # 创建数据提供器
    provider = AKShareProvider(qlib_data_path=str(project_root / "qlib_data" / "cn_data"))
    
    # 下载行业映射
    # 保存到项目data目录
    save_path = project_root / "data" / "stock_industry_mapping.json"
    
    logger.info("使用 stock_individual_info_em 接口下载行业映射...")
    logger.info(f"保存路径: {save_path}")
    
    mapping = provider.download_stock_industry_mapping(
        save_path=str(save_path),
        delay=1.0  # 1秒延迟
    )
    
    logger.info(f"下载完成，共获取 {len(mapping)} 只股票的行业信息")


if __name__ == "__main__":
    main()
