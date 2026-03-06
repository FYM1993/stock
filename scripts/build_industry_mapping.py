"""
构建股票-行业映射数据

使用AKShare的 stock_individual_info_em 接口获取每只股票的行业分类
保存到 data/stock_industry_mapping.json 供策略使用
"""

import akshare as ak
import json
import time
import os
from pathlib import Path
from loguru import logger

def get_all_stock_codes():
    """获取所有A股代码（从Qlib）"""
    logger.info("从Qlib获取股票列表...")
    
    try:
        import qlib
        from qlib.data import D
        
        # 初始化Qlib
        qlib.init(provider_uri="~/.qlib/qlib_data/cn_data")
        
        # 获取所有股票
        instruments = D.instruments('all')
        
        # 过滤掉指数
        all_codes = [code for code in instruments if not (code.startswith('000') or code.startswith('399'))]
        
        logger.info(f"共获取 {len(all_codes)} 只股票")
        
        return all_codes
    except Exception as e:
        logger.error(f"获取股票列表失败: {e}")
        return []

def get_stock_industry(symbol):
    """
    获取单只股票的行业信息
    
    Args:
        symbol: 股票代码，如 "300502.SZ"
    
    Returns:
        行业名称，如 "通信设备"，失败返回 None
    """
    try:
        # 去掉后缀
        code = symbol.split('.')[0]
        
        # 调用AKShare接口
        info = ak.stock_individual_info_em(symbol=code)
        
        # 查找行业字段
        industry_row = info[info['item'] == '行业']
        if not industry_row.empty:
            industry = industry_row.iloc[0]['value']
            return industry
        else:
            logger.warning(f"{symbol}: 无行业信息")
            return None
            
    except Exception as e:
        logger.debug(f"{symbol}: 获取失败 - {e}")
        return None

def build_industry_mapping(output_path="data/stock_industry_mapping.json", batch_size=50):
    """
    构建股票-行业映射
    
    Args:
        output_path: 输出文件路径
        batch_size: 每批次处理股票数（每批次后暂停，避免被限流）
    """
    logger.info("=" * 60)
    logger.info("开始构建股票-行业映射")
    logger.info("=" * 60)
    
    # 确保输出目录存在
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 加载已有映射（如果存在）
    existing_mapping = {}
    if output_file.exists():
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_mapping = json.load(f)
        logger.info(f"加载已有映射: {len(existing_mapping)} 只股票")
    
    # 获取所有股票代码
    all_codes = get_all_stock_codes()
    if not all_codes:
        logger.error("未获取到股票列表，退出")
        return
    
    # 筛选需要更新的股票（不在已有映射中的）
    codes_to_update = [code for code in all_codes if code not in existing_mapping]
    logger.info(f"需要更新: {len(codes_to_update)} 只股票")
    
    if not codes_to_update:
        logger.info("所有股票已有行业信息，无需更新")
        return
    
    # 开始批量获取
    mapping = existing_mapping.copy()
    success_count = 0
    fail_count = 0
    
    for i, symbol in enumerate(codes_to_update):
        industry = get_stock_industry(symbol)
        
        if industry:
            mapping[symbol] = industry
            success_count += 1
            logger.info(f"[{i+1}/{len(codes_to_update)}] {symbol}: {industry}")
        else:
            fail_count += 1
            logger.warning(f"[{i+1}/{len(codes_to_update)}] {symbol}: 失败")
        
        # 每批次后暂停
        if (i + 1) % batch_size == 0:
            logger.info(f"已处理 {i+1} 只，暂停3秒...")
            
            # 保存中间结果
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
            logger.info(f"中间结果已保存: {len(mapping)} 只股票")
            
            time.sleep(3)
    
    # 保存最终结果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    
    logger.info("=" * 60)
    logger.info(f"✅ 构建完成!")
    logger.info(f"总计: {len(mapping)} 只股票")
    logger.info(f"本次成功: {success_count}, 失败: {fail_count}")
    logger.info(f"保存路径: {output_file.absolute()}")
    logger.info("=" * 60)
    
    # 统计行业分布
    industry_stats = {}
    for industry in mapping.values():
        industry_stats[industry] = industry_stats.get(industry, 0) + 1
    
    logger.info("\n行业分布（前20）:")
    sorted_industries = sorted(industry_stats.items(), key=lambda x: x[1], reverse=True)
    for industry, count in sorted_industries[:20]:
        logger.info(f"  {industry}: {count}只")

def update_mapping(output_path="data/stock_industry_mapping.json"):
    """增量更新映射（只更新新股和失败的）"""
    logger.info("增量更新模式...")
    build_industry_mapping(output_path=output_path)

if __name__ == "__main__":
    import sys
    
    # 配置日志
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    # 运行
    build_industry_mapping()
