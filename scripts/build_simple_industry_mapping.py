"""
多源下载股票行业信息

优先级：
1. 从已有的mapping文件加载
2. 使用A股代码规则推断行业板块（临时方案）
3. 设置默认行业分类

这个临时方案能让策略先运行起来
"""

import sys
from pathlib import Path
from loguru import logger
import json

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

def infer_industry_by_code(code: str) -> str:
    """
    根据股票代码规则推断可能的行业
    这是一个临时方案，基于常见的板块代码规则
    """
    # 提取6位代码
    stock_num = code.split('.')[0]
    
    # 科创板
    if stock_num.startswith('688'):
        return '科技创新'
    
    # 创业板
    if stock_num.startswith('300'):
        return '成长企业'
    
    # 北交所
    if stock_num.startswith('8') or stock_num.startswith('4'):
        return '专精特新'
    
    # 沪市主板
    if stock_num.startswith('60'):
        # 600-603是传统主板
        if stock_num.startswith('600'):
            return '传统行业'
        elif stock_num.startswith('601'):
            return '金融能源'
        elif stock_num.startswith('603'):
            return '制造业'
        return '沪市主板'
    
    # 深市主板
    if stock_num.startswith('000'):
        return '深市主板'
    
    # 中小板（已并入主板，但历史代码保留）
    if stock_num.startswith('002'):
        return '中小企业'
    
    return '其他'

def build_simple_industry_mapping(stocks: list) -> dict:
    """
    构建简单的行业映射
    使用代码规则推断 + 预定义的常见行业
    """
    
    # 预定义一些常见行业
    common_industries = [
        '银行', '证券', '保险', '房地产', '建筑',
        '钢铁', '煤炭', '石油', '化工', '电力',
        '电子', '通信', '计算机', '医药', '食品饮料',
        '家电', '汽车', '机械', '军工', '交通运输',
        '商业贸易', '轻工制造', '纺织服装', '农林牧渔', '有色金属',
        '环保', '传媒', '非银金融', '综合', '采掘'
    ]
    
    mapping = {}
    
    for stock in stocks:
        # 使用代码推断
        industry = infer_industry_by_code(stock)
        
        mapping[stock] = {
            'industry': industry,
            'name': '',  # 暂时没有名称
            'source': 'code_inference'
        }
    
    return mapping

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
    logger.info("构建简易行业映射（基于代码规则）")
    logger.info("=" * 60)
    logger.warning("⚠️ 这是临时方案，行业分类较粗糙")
    logger.warning("⚠️ 建议后续使用真实的行业数据替换")
    
    # 加载股票列表
    stocks = load_stock_list()
    if not stocks:
        logger.error("未加载到股票列表")
        return 1
    
    logger.info(f"待处理: {len(stocks)} 只股票")
    
    # 保存路径
    save_path = Path(__file__).parent.parent / "data" / "stock_industry_mapping.json"
    
    # 加载已有数据（如果存在）
    existing = {}
    if save_path.exists():
        with open(save_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        logger.info(f"已有 {len(existing)} 只股票的数据")
    
    # 构建映射
    logger.info("开始构建行业映射...")
    mapping = build_simple_industry_mapping(stocks)
    
    # 合并已有数据（优先保留已有的真实数据）
    for stock, info in existing.items():
        if stock in mapping:
            # 如果existing的数据是字符串格式（旧格式）
            if isinstance(info, str):
                mapping[stock] = {
                    'industry': info,
                    'name': '',
                    'source': 'manual'  # 手动添加的数据优先级高
                }
            # 如果是字典格式，且不是代码推断的（即真实数据）
            elif isinstance(info, dict) and info.get('source') != 'code_inference':
                mapping[stock] = info
    
    # 保存
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    
    # 统计行业分布
    industry_count = {}
    for stock, info in mapping.items():
        industry = info['industry']
        industry_count[industry] = industry_count.get(industry, 0) + 1
    
    logger.info(f"\n✅ 完成!")
    logger.info(f"总计: {len(mapping)} 只股票")
    logger.info(f"行业数: {len(industry_count)} 个")
    logger.info("\n行业分布 (Top 10):")
    
    sorted_industries = sorted(industry_count.items(), key=lambda x: x[1], reverse=True)
    for industry, count in sorted_industries[:10]:
        logger.info(f"  {industry}: {count} 只")
    
    logger.info(f"\n保存路径: {save_path}")
    
    return 0

if __name__ == "__main__":
    exit(main())
