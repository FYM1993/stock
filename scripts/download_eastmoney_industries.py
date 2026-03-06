#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用AKShare东方财富接口获取股票行业分类数据
通过行业板块成份股构建股票→行业映射
"""

import os
import sys
import json
import time
import akshare as ak
import pandas as pd
from loguru import logger
from pathlib import Path

# 禁用代理，因为东方财富不允许代理访问
for proxy_env in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    if proxy_env in os.environ:
        del os.environ[proxy_env]

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("logs/download_eastmoney_industries.log", rotation="10 MB", level="DEBUG")


class EastmoneyIndustryDownloader:
    """东方财富行业数据下载器"""
    
    def __init__(self, stock_list_file: str, output_file: str):
        self.stock_list_file = stock_list_file
        self.output_file = output_file
        self.request_delay = 1.0  # 请求间隔1秒
        self.stock_industry_mapping = {}
        
        # 加载股票列表
        self._load_stock_list()
        
    def _load_stock_list(self):
        """加载股票列表"""
        if not os.path.exists(self.stock_list_file):
            logger.error(f"股票列表文件不存在: {self.stock_list_file}")
            sys.exit(1)
        
        with open(self.stock_list_file, 'r', encoding='utf-8') as f:
            self.stock_list = set(line.strip() for line in f if line.strip())
        
        logger.info(f"已加载 {len(self.stock_list)} 只股票")
    
    def _normalize_stock_code(self, code: str) -> str:
        """
        标准化股票代码为Qlib格式
        输入: 600000 (SH) 或 000001 (SZ)
        输出: 600000.SH 或 000001.SZ
        """
        if not code or len(code) != 6:
            return None
        
        # 根据代码前缀判断市场
        if code.startswith('6') or code.startswith('9'):
            return f"{code}.SH"
        elif code.startswith(('0', '3', '2')):
            return f"{code}.SZ"
        elif code.startswith('4') or code.startswith('8'):
            return f"{code}.BJ"
        else:
            return None
    
    def fetch_all_industries(self) -> list:
        """
        获取所有行业板块信息
        
        Returns:
            行业板块列表
        """
        try:
            logger.info("正在获取所有行业板块列表...")
            df = ak.stock_board_industry_name_em()
            
            if df is None or df.empty:
                logger.error("未能获取行业板块数据")
                return []
            
            # 提取板块名称列表
            industries = df['板块名称'].tolist()
            logger.success(f"成功获取 {len(industries)} 个行业板块")
            
            return industries
            
        except Exception as e:
            logger.error(f"获取行业板块列表失败: {e}")
            return []
    
    def fetch_industry_constituents(self, industry_name: str) -> list:
        """
        获取指定行业板块的成份股
        
        Args:
            industry_name: 行业板块名称
            
        Returns:
            成份股代码列表 (Qlib格式)
        """
        try:
            logger.info(f"正在获取行业板块 '{industry_name}' 的成份股...")
            
            df = ak.stock_board_industry_cons_em(symbol=industry_name)
            
            if df is None or df.empty:
                logger.warning(f"行业板块 '{industry_name}' 无成份股数据")
                return []
            
            # 提取股票代码并标准化
            codes = []
            for code in df['代码'].tolist():
                qlib_code = self._normalize_stock_code(code)
                if qlib_code:
                    codes.append(qlib_code)
            
            logger.success(f"行业板块 '{industry_name}' 有 {len(codes)} 只成份股")
            return codes
            
        except Exception as e:
            logger.error(f"获取行业板块 '{industry_name}' 成份股失败: {e}")
            return []
    
    def build_stock_industry_mapping(self):
        """
        构建股票→行业映射
        遍历所有行业板块，记录每只股票所属的行业
        """
        # 获取所有行业板块
        industries = self.fetch_all_industries()
        
        if not industries:
            logger.error("无法获取行业板块列表，退出")
            return
        
        # 遍历每个行业板块
        for i, industry_name in enumerate(industries, 1):
            logger.info(f"[{i}/{len(industries)}] 处理行业板块: {industry_name}")
            
            # 获取该行业的成份股
            constituents = self.fetch_industry_constituents(industry_name)
            
            # 更新映射
            for stock_code in constituents:
                # 只处理在Qlib股票列表中的股票
                if stock_code in self.stock_list:
                    # 如果股票已经有行业，可以选择保留第一个或者记录多个
                    # 这里选择保留第一个遇到的行业
                    if stock_code not in self.stock_industry_mapping:
                        self.stock_industry_mapping[stock_code] = {
                            'ind_code': '',  # 东方财富板块代码（如果需要可以提取）
                            'ind_name': industry_name
                        }
            
            # 每处理10个行业保存一次
            if i % 10 == 0:
                self._save_mapping()
                logger.info(f"进度: {i}/{len(industries)}, 已映射 {len(self.stock_industry_mapping)} 只股票")
            
            # 请求间隔
            if i < len(industries):
                time.sleep(self.request_delay)
        
        # 最后再保存一次
        self._save_mapping()
        
        # 统计信息
        mapped_count = len(self.stock_industry_mapping)
        total_count = len(self.stock_list)
        unmapped_count = total_count - mapped_count
        
        logger.info("=" * 60)
        logger.info("构建完成统计:")
        logger.info(f"  总股票数: {total_count}")
        logger.info(f"  已映射: {mapped_count}")
        logger.info(f"  未映射: {unmapped_count}")
        logger.info(f"  覆盖率: {mapped_count / total_count * 100:.2f}%")
        logger.info("=" * 60)
        
        # 输出部分未映射的股票作为参考
        if unmapped_count > 0:
            unmapped_stocks = self.stock_list - set(self.stock_industry_mapping.keys())
            logger.info(f"部分未映射股票示例: {list(unmapped_stocks)[:10]}")
    
    def _save_mapping(self):
        """保存行业映射数据"""
        try:
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(self.stock_industry_mapping, f, ensure_ascii=False, indent=2)
            logger.debug(f"已保存 {len(self.stock_industry_mapping)} 条行业映射数据")
        except Exception as e:
            logger.error(f"保存行业映射数据失败: {e}")


def main():
    """主函数"""
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    
    # 配置路径
    stock_list_file = project_root / "data" / "qlib_stocks_list.txt"
    output_file = project_root / "data" / "stock_industry_mapping.json"
    
    # 创建下载器并执行
    downloader = EastmoneyIndustryDownloader(
        stock_list_file=str(stock_list_file),
        output_file=str(output_file)
    )
    
    downloader.build_stock_industry_mapping()


if __name__ == "__main__":
    main()
