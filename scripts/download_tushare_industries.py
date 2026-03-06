"""
使用Tushare下载股票行业信息

从Qlib股票列表读取，使用Tushare的stock_basic接口获取行业信息
保存到 data/stock_industry_mapping.json
"""

import sys
from pathlib import Path
from loguru import logger
import json
import time
import random

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

def convert_to_tushare_code(qlib_code: str) -> str:
    """
    将Qlib格式转换为Tushare格式
    例如：000001.SZ -> 000001.SZ (Tushare格式相同)
    """
    return qlib_code

def convert_to_qlib_code(tushare_code: str) -> str:
    """
    将Tushare格式转换为Qlib格式
    例如：000001.SZ -> 000001.SZ (格式相同)
    """
    return tushare_code

def download_with_tushare(stocks: list, save_path: Path) -> dict:
    """使用Tushare批量下载行业信息"""
    
    try:
        import tushare as ts
    except ImportError:
        logger.error("❌ 未安装 tushare，请运行: pip install tushare")
        return {}
    
    logger.info("=" * 60)
    logger.info("使用 Tushare 下载股票行业信息")
    logger.info("=" * 60)
    
    # 检查是否有token（从环境变量或配置）
    logger.warning("⚠️ Tushare需要token，如果没有会使用免费接口")
    
    # 尝试初始化pro接口（可选，没token会用免费接口）
    try:
        # 用户需要设置环境变量 TUSHARE_TOKEN 或在这里填写
        token = None  # 可以设置为 ts.get_token() 或直接填写token
        if token:
            pro = ts.pro_api(token)
            logger.info("✓ 使用 Tushare Pro 接口")
        else:
            pro = None
            logger.info("✓ 使用 Tushare 免费接口")
    except:
        pro = None
        logger.info("✓ 使用 Tushare 免费接口")
    
    # 加载已有数据
    existing = {}
    if save_path.exists():
        with open(save_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        logger.info(f"已有 {len(existing)} 只股票的数据")
    
    # 如果有Pro接口，可以批量获取
    if pro:
        try:
            logger.info("尝试使用 stock_basic 接口批量获取...")
            df = pro.stock_basic(
                fields='ts_code,name,industry'
            )
            
            logger.info(f"✓ 获取到 {len(df)} 只股票的信息")
            
            # 转换为映射表
            mapping = existing.copy()
            for _, row in df.iterrows():
                qlib_code = convert_to_qlib_code(row['ts_code'])
                if qlib_code in stocks:
                    mapping[qlib_code] = {
                        'industry': row['industry'] if pd.notna(row['industry']) else '未知',
                        'name': row['name'] if pd.notna(row['name']) else '',
                        'source': 'tushare_pro'
                    }
            
            # 保存
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 保存成功: {len(mapping)} 只股票")
            return mapping
            
        except Exception as e:
            logger.warning(f"Pro接口失败: {e}，尝试免费接口...")
    
    # 使用免费接口（逐个获取或使用stock_basic）
    logger.info("使用免费接口获取股票列表...")
    
    try:
        # Tushare免费版也有stock_basic，但可能有限制
        import tushare as ts
        
        # 尝试获取全部股票基本信息
        logger.info("获取股票基本信息...")
        df = ts.get_stock_basics()  # 免费接口
        
        if df is not None and len(df) > 0:
            logger.info(f"✓ 获取到 {len(df)} 只股票的信息")
            
            # get_stock_basics返回的index是股票代码（6位），需要添加市场后缀
            mapping = existing.copy()
            
            for code in df.index:
                # 判断市场
                if code.startswith('6'):
                    qlib_code = f"{code}.SH"
                else:
                    qlib_code = f"{code}.SZ"
                
                if qlib_code in stocks:
                    industry = df.loc[code, 'industry'] if 'industry' in df.columns else '未知'
                    name = df.loc[code, 'name'] if 'name' in df.columns else ''
                    
                    mapping[qlib_code] = {
                        'industry': industry if pd.notna(industry) else '未知',
                        'name': name if pd.notna(name) else '',
                        'source': 'tushare_free'
                    }
            
            # 保存
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 保存成功: {len(mapping)} 只股票")
            logger.info(f"覆盖率: {len(mapping)}/{len(stocks)} = {len(mapping)/len(stocks)*100:.1f}%")
            
            return mapping
        else:
            logger.error("❌ 免费接口也无法获取数据")
            return existing
            
    except Exception as e:
        logger.error(f"❌ 下载失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return existing

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
    logger.info("下载Qlib股票行业信息（使用Tushare）")
    logger.info("=" * 60)
    
    # 加载股票列表
    stocks = load_stock_list()
    if not stocks:
        logger.error("未加载到股票列表")
        return 1
    
    logger.info(f"待下载行业信息: {len(stocks)} 只股票")
    
    # 保存路径
    save_path = Path(__file__).parent.parent / "data" / "stock_industry_mapping.json"
    
    try:
        mapping = download_with_tushare(stocks, save_path)
        
        if mapping:
            logger.info(f"\n✅ 完成!")
            logger.info(f"成功: {len(mapping)} 只")
            logger.info(f"覆盖率: {len(mapping)}/{len(stocks)} = {len(mapping)/len(stocks)*100:.1f}%")
        else:
            logger.error("\n❌ 下载失败")
            return 1
        
    except KeyboardInterrupt:
        logger.warning("\n⚠️ 用户中断下载")
        return 0
    except Exception as e:
        logger.error(f"\n❌ 下载失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
