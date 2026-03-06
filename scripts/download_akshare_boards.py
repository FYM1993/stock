"""
使用AKShare的板块接口获取股票行业分类

策略：
1. 获取所有行业板块列表
2. 逐个获取每个板块的成份股
3. 反向构建 股票->行业 的映射
"""

import akshare as ak
import json
from pathlib import Path
from loguru import logger
import time
import random

def main():
    logger.info("=" * 60)
    logger.info("使用AKShare板块接口获取行业分类")
    logger.info("=" * 60)
    
    try:
        # 1. 获取所有行业板块列表
        logger.info("步骤1: 获取行业板块列表...")
        industry_list = ak.stock_board_industry_name_em()
        logger.info(f"✓ 获取到 {len(industry_list)} 个行业板块")
        logger.info(f"板块列表前5个:\n{industry_list.head()}")
        
        # 2. 构建股票->行业映射
        logger.info("\n步骤2: 获取每个板块的成份股...")
        stock_industry_map = {}
        
        for idx, row in industry_list.iterrows():
            board_name = row['板块名称']
            board_code = row['板块代码']
            
            try:
                # 获取该板块的成份股
                constituents = ak.stock_board_industry_cons_em(symbol=board_name)
                
                logger.info(f"  [{idx+1}/{len(industry_list)}] {board_name}: {len(constituents)} 只股票")
                
                # 将成份股添加到映射表
                for _, stock in constituents.iterrows():
                    stock_code = stock['代码']
                    stock_name = stock['名称']
                    
                    # 添加市场后缀
                    if stock_code.startswith('6'):
                        full_code = f"{stock_code}.SH"
                    else:
                        full_code = f"{stock_code}.SZ"
                    
                    # 如果股票已存在，保留第一个板块（通常是主板块）
                    if full_code not in stock_industry_map:
                        stock_industry_map[full_code] = {
                            'industry': board_name,
                            'name': stock_name,
                            'source': 'akshare_board_em'
                        }
                
                # 随机延迟，避免被限流
                time.sleep(random.uniform(0.5, 1.5))
                
            except Exception as e:
                logger.warning(f"  ⚠️ 获取 {board_name} 失败: {e}")
                continue
        
        # 3. 保存结果
        save_path = Path(__file__).parent.parent / "data" / "stock_industry_mapping.json"
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(stock_industry_map, f, ensure_ascii=False, indent=2)
        
        logger.info(f"\n✅ 完成!")
        logger.info(f"成功获取 {len(stock_industry_map)} 只股票的行业分类")
        logger.info(f"覆盖 {len(industry_list)} 个行业板块")
        logger.info(f"保存至: {save_path}")
        
        # 显示示例
        logger.info(f"\n示例数据:")
        for i, (code, info) in enumerate(list(stock_industry_map.items())[:5]):
            logger.info(f"  {code}: {info['name']} -> {info['industry']}")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ 执行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    exit(main())
