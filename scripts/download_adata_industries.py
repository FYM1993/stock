#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用AData库下载股票行业分类数据
"""

import os
import sys
import json
import time
from pathlib import Path
from loguru import logger

# 检查是否安装了adata
try:
    import adata
except ImportError:
    logger.error("未安装adata库，正在安装...")
    os.system("pip install adata -i http://mirrors.aliyun.com/pypi/simple/")
    import adata

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("logs/download_adata_industries.log", rotation="10 MB", level="DEBUG")


class AdataIndustryDownloader:
    """使用AData下载行业数据"""
    
    def __init__(self, stock_list_file: str, output_file: str):
        self.stock_list_file = stock_list_file
        self.output_file = output_file
        self.request_delay = 0.5  # 请求间隔
        self.stock_industry_mapping = {}
        
        # 加载股票列表
        self._load_stock_list()
    
    def _load_stock_list(self):
        """加载股票列表"""
        if not os.path.exists(self.stock_list_file):
            logger.error(f"股票列表文件不存在: {self.stock_list_file}")
            sys.exit(1)
        
        with open(self.stock_list_file, 'r', encoding='utf-8') as f:
            self.stock_list = [line.strip() for line in f if line.strip()]
        
        logger.info(f"已加载 {len(self.stock_list)} 只股票")
    
    def _normalize_stock_code(self, qlib_code: str) -> str:
        """
        转换Qlib格式到AData格式
        Qlib: 000001.SZ
        AData: 000001
        """
        return qlib_code.split('.')[0]
    
    def download_industry_data(self):
        """
        下载所有股票的行业数据
        优先使用申万行业，失败则使用东方财富板块
        """
        logger.info("=" * 60)
        logger.info("开始使用AData下载行业分类数据")
        logger.info("=" * 60)
        
        success_count = 0
        fail_count = 0
        
        for i, qlib_code in enumerate(self.stock_list, 1):
            adata_code = self._normalize_stock_code(qlib_code)
            
            try:
                # 方法1：尝试获取申万行业
                industry_info = self._get_sw_industry(adata_code)
                
                # 方法2：如果申万行业失败，尝试东方财富板块
                if not industry_info:
                    industry_info = self._get_east_plate(adata_code)
                
                if industry_info:
                    self.stock_industry_mapping[qlib_code] = industry_info
                    success_count += 1
                    logger.debug(f"✓ {qlib_code}: {industry_info.get('ind_name', '未知')}")
                else:
                    fail_count += 1
                    logger.debug(f"✗ {qlib_code}: 无行业数据")
                
                # 每50只打印进度并保存
                if i % 50 == 0:
                    self._save_mapping()
                    logger.info(f"进度: {i}/{len(self.stock_list)} ({i/len(self.stock_list)*100:.1f}%), "
                              f"成功: {success_count}, 失败: {fail_count}")
                
                # 请求延迟
                time.sleep(self.request_delay)
                
            except Exception as e:
                fail_count += 1
                logger.error(f"获取 {qlib_code} 行业信息失败: {e}")
                continue
        
        # 最终保存
        self._save_mapping()
        
        # 统计信息
        logger.info("=" * 60)
        logger.info("下载完成统计:")
        logger.info(f"  总股票数: {len(self.stock_list)}")
        logger.info(f"  成功获取: {success_count}")
        logger.info(f"  获取失败: {fail_count}")
        logger.info(f"  成功率: {success_count / len(self.stock_list) * 100:.2f}%")
        logger.info(f"  保存路径: {self.output_file}")
        logger.info("=" * 60)
        
        # 统计行业分布
        self._print_industry_stats()
    
    def _get_sw_industry(self, stock_code: str) -> dict:
        """
        获取申万行业
        
        Args:
            stock_code: 股票代码，如 '000001'
            
        Returns:
            行业信息字典或None
        """
        try:
            df = adata.stock.info.get_industry_sw(stock_code=stock_code)
            
            if df is not None and not df.empty:
                # 提取一级行业或二级行业
                industries = df['industry'].tolist()
                if industries:
                    return {
                        'ind_code': 'SW',  # 申万标识
                        'ind_name': industries[0],  # 使用第一个行业
                        'ind_name_full': '|'.join(industries),  # 完整行业链
                        'source': '申万'
                    }
            
            return None
            
        except Exception as e:
            logger.debug(f"获取申万行业失败({stock_code}): {e}")
            return None
    
    def _get_east_plate(self, stock_code: str) -> dict:
        """
        获取东方财富板块信息（包含行业、地域、概念）
        
        Args:
            stock_code: 股票代码，如 '000001'
            
        Returns:
            行业信息字典或None
        """
        try:
            df = adata.stock.info.get_plate_east(stock_code=stock_code)
            
            if df is not None and not df.empty:
                # 优先选择行业板块
                industry_rows = df[df['plate_type'] == '行业板块']
                
                if not industry_rows.empty:
                    plate_name = industry_rows.iloc[0]['plate_name']
                    return {
                        'ind_code': 'EAST',
                        'ind_name': plate_name,
                        'source': '东方财富'
                    }
                
                # 如果没有行业板块，使用第一个板块
                if not df.empty:
                    first_plate = df.iloc[0]
                    return {
                        'ind_code': 'EAST',
                        'ind_name': first_plate['plate_name'],
                        'plate_type': first_plate['plate_type'],
                        'source': '东方财富'
                    }
            
            return None
            
        except Exception as e:
            logger.debug(f"获取东方财富板块失败({stock_code}): {e}")
            return None
    
    def _save_mapping(self):
        """保存行业映射数据"""
        try:
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(self.stock_industry_mapping, f, ensure_ascii=False, indent=2)
            logger.debug(f"已保存 {len(self.stock_industry_mapping)} 条行业映射数据")
        except Exception as e:
            logger.error(f"保存行业映射数据失败: {e}")
    
    def _print_industry_stats(self):
        """打印行业分布统计"""
        industry_stats = {}
        for stock_info in self.stock_industry_mapping.values():
            ind_name = stock_info.get('ind_name', '未知')
            industry_stats[ind_name] = industry_stats.get(ind_name, 0) + 1
        
        logger.info("\n行业分布（前20）:")
        sorted_industries = sorted(industry_stats.items(), key=lambda x: x[1], reverse=True)
        for industry, count in sorted_industries[:20]:
            logger.info(f"  {industry}: {count}只")


def main():
    """主函数"""
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    
    # 配置路径
    stock_list_file = project_root / "data" / "qlib_stocks_list.txt"
    output_file = project_root / "data" / "stock_industry_mapping.json"
    
    # 创建下载器并执行
    downloader = AdataIndustryDownloader(
        stock_list_file=str(stock_list_file),
        output_file=str(output_file)
    )
    
    downloader.download_industry_data()


if __name__ == "__main__":
    main()
