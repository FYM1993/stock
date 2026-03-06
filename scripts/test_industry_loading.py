#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试行业数据加载
"""

import json
import sys
from pathlib import Path
from loguru import logger

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_industry_mapping():
    """测试行业映射数据"""
    
    # 加载数据
    mapping_file = Path(__file__).parent.parent / "data" / "stock_industry_mapping.json"
    
    logger.info(f"加载行业映射文件: {mapping_file}")
    
    if not mapping_file.exists():
        logger.error(f"文件不存在: {mapping_file}")
        return False
    
    with open(mapping_file, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
    
    logger.info(f"✓ 成功加载 {len(mapping)} 只股票的行业数据")
    
    # 统计行业分布
    industry_counts = {}
    valid_count = 0
    
    for stock, info in mapping.items():
        if isinstance(info, dict) and 'ind_name' in info:
            ind_name = info['ind_name']
            if ind_name and ind_name != '未知':
                industry_counts[ind_name] = industry_counts.get(ind_name, 0) + 1
                valid_count += 1
    
    logger.info(f"✓ 有效行业数据: {valid_count} 只股票")
    logger.info(f"✓ 行业种类数: {len(industry_counts)} 个")
    
    # 显示前10大行业
    logger.info("\n行业分布（前10）:")
    sorted_industries = sorted(industry_counts.items(), key=lambda x: x[1], reverse=True)
    for i, (industry, count) in enumerate(sorted_industries[:10], 1):
        logger.info(f"  {i}. {industry}: {count}只")
    
    # 测试几个示例股票
    logger.info("\n示例股票:")
    test_stocks = ['000001.SZ', '600000.SH', '300750.SZ', '600519.SH']
    for stock in test_stocks:
        info = mapping.get(stock, {})
        ind_name = info.get('ind_name', '未知') if isinstance(info, dict) else '未知'
        source = info.get('source', '-') if isinstance(info, dict) else '-'
        logger.info(f"  {stock}: {ind_name} ({source})")
    
    return True


def test_strategy_loading():
    """测试策略中的行业数据加载"""
    try:
        from strategies.leader_low_absorption import LeaderLowAbsorptionStrategy
        
        logger.info("\n测试策略加载...")
        
        # 创建策略实例
        strategy = LeaderLowAbsorptionStrategy(
            topk=10,
            max_positions=3
        )
        
        logger.info(f"✓ 策略成功加载行业映射: {len(strategy.stock_industry_mapping)} 只股票")
        
        # 测试获取行业
        test_stocks = ['000001.SZ', '600000.SH', '300750.SZ']
        logger.info("\n测试_get_stock_industry方法:")
        for stock in test_stocks:
            industry = strategy._get_stock_industry(stock)
            logger.info(f"  {stock}: {industry}")
        
        return True
        
    except Exception as e:
        logger.error(f"策略加载失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("测试行业数据加载")
    logger.info("=" * 60)
    
    # 测试1：直接加载JSON
    success1 = test_industry_mapping()
    
    # 测试2：策略中加载
    logger.info("\n" + "=" * 60)
    success2 = test_strategy_loading()
    
    logger.info("\n" + "=" * 60)
    if success1 and success2:
        logger.info("✅ 所有测试通过！")
    else:
        logger.error("❌ 部分测试失败")
    logger.info("=" * 60)
