#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用AKShare雪球接口获取股票行业分类数据
严格控制请求频率为1秒/次
"""

import os
import sys
import json
import time
import akshare as ak
from loguru import logger
from pathlib import Path

# 禁用代理，因为雪球不允许代理访问
for proxy_env in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    if proxy_env in os.environ:
        del os.environ[proxy_env]

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("logs/download_akshare_xueqiu_industries.log", rotation="10 MB", level="DEBUG")


class XueqiuIndustryDownloader:
    """雪球行业数据下载器"""
    
    def __init__(self, stock_list_file: str, output_file: str):
        self.stock_list_file = stock_list_file
        self.output_file = output_file
        self.request_delay = 1.0  # 严格控制为1秒/次
        self.industry_mapping = {}
        
        # 加载已有的映射数据
        self._load_existing_mapping()
    
    def _load_existing_mapping(self):
        """加载已有的行业映射数据"""
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    self.industry_mapping = json.load(f)
                logger.info(f"已加载 {len(self.industry_mapping)} 条已有行业映射数据")
            except Exception as e:
                logger.error(f"加载已有数据失败: {e}")
                self.industry_mapping = {}
    
    def _convert_symbol_format(self, qlib_symbol: str) -> str:
        """
        转换Qlib股票代码格式到雪球格式
        Qlib: 000001.SZ, 600000.SH
        雪球: SZ000001, SH600000
        """
        if not qlib_symbol or '.' not in qlib_symbol:
            return None
        
        code, market = qlib_symbol.split('.')
        return f"{market}{code}"
    
    def _extract_industry_info(self, df) -> dict:
        """
        从雪球API返回的DataFrame中提取行业信息
        """
        try:
            # 查找affiliate_industry这一行
            for idx, row in df.iterrows():
                if row['item'] == 'affiliate_industry':
                    industry_data = row['value']
                    
                    # 检查是否是字典类型
                    if isinstance(industry_data, dict):
                        return {
                            'ind_code': industry_data.get('ind_code', ''),
                            'ind_name': industry_data.get('ind_name', '')
                        }
                    else:
                        logger.warning(f"affiliate_industry数据格式不是字典: {type(industry_data)}")
                        return None
            
            logger.warning("未找到affiliate_industry字段")
            return None
            
        except Exception as e:
            logger.error(f"提取行业信息失败: {e}")
            return None
    
    def fetch_stock_industry(self, qlib_symbol: str) -> dict:
        """
        获取单个股票的行业信息
        
        Args:
            qlib_symbol: Qlib格式的股票代码，如 000001.SZ
            
        Returns:
            包含行业信息的字典，或None
        """
        xueqiu_symbol = self._convert_symbol_format(qlib_symbol)
        if not xueqiu_symbol:
            logger.error(f"无法转换股票代码: {qlib_symbol}")
            return None
        
        try:
            logger.info(f"正在获取 {qlib_symbol} ({xueqiu_symbol}) 的行业信息...")
            
            # 调用雪球接口
            df = ak.stock_individual_basic_info_xq(symbol=xueqiu_symbol)
            
            if df is None or df.empty:
                logger.warning(f"股票 {qlib_symbol} 未返回数据")
                return None
            
            # 提取行业信息
            industry_info = self._extract_industry_info(df)
            
            if industry_info and industry_info.get('ind_name'):
                logger.success(f"成功获取 {qlib_symbol} 的行业: {industry_info['ind_name']}")
                return industry_info
            else:
                logger.warning(f"股票 {qlib_symbol} 无行业信息")
                return None
                
        except Exception as e:
            logger.error(f"获取股票 {qlib_symbol} 行业信息失败: {e}")
            return None
    
    def _save_mapping(self):
        """保存行业映射数据"""
        try:
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(self.industry_mapping, f, ensure_ascii=False, indent=2)
            logger.success(f"已保存 {len(self.industry_mapping)} 条行业映射数据到 {self.output_file}")
        except Exception as e:
            logger.error(f"保存行业映射数据失败: {e}")
    
    def download_all(self):
        """
        下载所有股票的行业信息
        严格控制请求频率为1秒/次
        """
        # 读取股票列表
        if not os.path.exists(self.stock_list_file):
            logger.error(f"股票列表文件不存在: {self.stock_list_file}")
            return
        
        with open(self.stock_list_file, 'r', encoding='utf-8') as f:
            stock_list = [line.strip() for line in f if line.strip()]
        
        logger.info(f"共需要处理 {len(stock_list)} 只股票")
        
        # 统计信息
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        # 遍历所有股票
        for i, stock_code in enumerate(stock_list, 1):
            # 跳过已经有数据的股票
            if stock_code in self.industry_mapping:
                existing_industry = self.industry_mapping[stock_code]
                if isinstance(existing_industry, dict) and existing_industry.get('ind_name'):
                    logger.info(f"[{i}/{len(stock_list)}] {stock_code} 已有行业数据，跳过")
                    skip_count += 1
                    continue
            
            # 获取行业信息
            industry_info = self.fetch_stock_industry(stock_code)
            
            if industry_info:
                self.industry_mapping[stock_code] = industry_info
                success_count += 1
            else:
                # 标记为失败，但不删除已有数据
                if stock_code not in self.industry_mapping:
                    self.industry_mapping[stock_code] = {"ind_code": "", "ind_name": "未知"}
                fail_count += 1
            
            # 每处理10只股票保存一次
            if i % 10 == 0:
                self._save_mapping()
                logger.info(f"进度: {i}/{len(stock_list)}, 成功: {success_count}, 失败: {fail_count}, 跳过: {skip_count}")
            
            # 严格控制请求频率：每次请求后等待1秒
            if i < len(stock_list):  # 最后一只不需要等待
                logger.debug(f"等待 {self.request_delay} 秒后继续...")
                time.sleep(self.request_delay)
        
        # 最后保存一次
        self._save_mapping()
        
        # 输出统计信息
        logger.info("=" * 60)
        logger.info("下载完成统计:")
        logger.info(f"  总股票数: {len(stock_list)}")
        logger.info(f"  成功获取: {success_count}")
        logger.info(f"  获取失败: {fail_count}")
        logger.info(f"  跳过处理: {skip_count}")
        logger.info(f"  成功率: {success_count / (len(stock_list) - skip_count) * 100:.2f}%")
        logger.info("=" * 60)


def main():
    """主函数"""
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    
    # 配置路径
    stock_list_file = project_root / "data" / "qlib_stocks_list.txt"
    output_file = project_root / "data" / "stock_industry_mapping.json"
    
    # 创建下载器并执行
    downloader = XueqiuIndustryDownloader(
        stock_list_file=str(stock_list_file),
        output_file=str(output_file)
    )
    
    downloader.download_all()


if __name__ == "__main__":
    main()
