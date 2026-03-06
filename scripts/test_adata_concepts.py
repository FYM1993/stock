"""
测试adata支持的板块分类
"""
import adata
from loguru import logger

# 初始化
stock_info = adata.stock.info

logger.info("="*60)
logger.info("测试adata支持的板块分类")
logger.info("="*60)

# 1. 测试同花顺概念
logger.info("\n【1】同花顺概念板块 (get_concept_ths)")
try:
    ths_concepts = stock_info.get_concept_ths('300059')  # 东方财富
    logger.info(f"东方财富(300059)的同花顺概念:")
    logger.info(ths_concepts)
except Exception as e:
    logger.error(f"获取同花顺概念失败: {e}")

# 2. 测试东方财富概念
logger.info("\n【2】东方财富概念板块 (get_concept_east)")
try:
    east_concepts = stock_info.get_concept_east('300059')
    logger.info(f"东方财富(300059)的东财概念:")
    logger.info(east_concepts)
except Exception as e:
    logger.error(f"获取东财概念失败: {e}")

# 3. 测试申万行业
logger.info("\n【3】申万行业 (get_industry_sw)")
try:
    sw_industry = stock_info.get_industry_sw('300059')
    logger.info(f"东方财富(300059)的申万行业:")
    logger.info(sw_industry)
except Exception as e:
    logger.error(f"获取申万行业失败: {e}")

# 4. 获取所有同花顺概念列表
logger.info("\n【4】所有同花顺概念列表 (前20个)")
try:
    all_ths_concepts = stock_info.all_concept_code_ths()
    logger.info(f"同花顺概念总数: {len(all_ths_concepts)}")
    logger.info(f"前20个概念:")
    for i, concept in enumerate(all_ths_concepts[:20], 1):
        logger.info(f"  {i}. {concept}")
except Exception as e:
    logger.error(f"获取概念列表失败: {e}")

# 5. 获取所有东财概念列表
logger.info("\n【5】所有东方财富概念列表 (前20个)")
try:
    all_east_concepts = stock_info.all_concept_code_east()
    logger.info(f"东财概念总数: {len(all_east_concepts)}")
    logger.info(f"前20个概念:")
    for i, concept in enumerate(all_east_concepts[:20], 1):
        logger.info(f"  {i}. {concept}")
except Exception as e:
    logger.error(f"获取概念列表失败: {e}")

logger.info("\n" + "="*60)
