"""
AKShare 数据提供器 - 为 Qlib 提供 A股数据

这个模块负责：
1. 从 AKShare 获取股票数据
2. 转换为 Qlib 标准格式
3. 存储到本地文件系统
"""

import akshare as ak
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
from loguru import logger
import time


class AKShareProvider:
    """AKShare 数据提供器"""
    
    def __init__(self, qlib_data_path: str = "~/.qlib/qlib_data/cn_data"):
        """
        初始化数据提供器
        
        Args:
            qlib_data_path: Qlib数据存储路径
        """
        self.qlib_data_path = Path(qlib_data_path).expanduser()
        self.qlib_data_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"数据存储路径: {self.qlib_data_path}")
    
    def get_stock_list(self, filter_inactive: bool = False, active_threshold: float = 0.7) -> List[str]:
        """
        获取所有A股代码列表
        
        过滤规则：
        - 排除北交所（8/4开头）
        - 排除科创板（688开头）
        - 只保留主板、中小板、创业板
        - 可选：排除不活跃股票（成交额后30%）
        
        Args:
            filter_inactive: 是否过滤不活跃股票
            active_threshold: 活跃度阈值（0-1），保留成交额前X%的股票，默认0.7（前70%）
        
        Returns:
            股票代码列表，格式如 ['000001.SZ', '600000.SH']
        """
        try:
            df = ak.stock_zh_a_spot_em()
            stock_list = []
            stock_codes = []
            
            for code in df['代码'].tolist():
                # 转换为标准格式
                if code.startswith('6'):
                    # 上海主板
                    # 排除科创板（688开头）
                    if code.startswith('688'):
                        continue
                    stock_list.append(f"{code}.SH")
                    stock_codes.append(code)
                elif code.startswith('0') or code.startswith('3'):
                    # 深圳主板（000/001）、中小板（002）、创业板（300）
                    stock_list.append(f"{code}.SZ")
                    stock_codes.append(code)
                elif code.startswith('8') or code.startswith('4'):
                    # 北交所股票，跳过
                    continue
                else:
                    # 其他未知代码，跳过
                    continue
            
            total_stocks = len(stock_list)
            logger.info(f"获取到 {total_stocks} 只股票（已排除北交所和科创板）")
            
            # 如果需要过滤不活跃股票
            if filter_inactive:
                logger.info(f"开始过滤冷门股（保留当前成交额前 {active_threshold*100:.0f}% 的股票）...")
                
                try:
                    # 简化方案：使用当前市场成交额排名
                    # 逻辑：当前成交额靠后的股票，大概率长期冷门
                    df_filtered = df[df['代码'].isin(stock_codes)].copy()
                    df_filtered['成交额'] = pd.to_numeric(df_filtered['成交额'], errors='coerce')
                    
                    # 按成交额降序排序
                    df_sorted = df_filtered.sort_values('成交额', ascending=False)
                    
                    # 计算保留数量
                    keep_count = int(len(df_sorted) * active_threshold)
                    top_codes = set(df_sorted.head(keep_count)['代码'].tolist())
                    
                    # 过滤（stock_list是字符串列表，如"000001.SZ"）
                    filtered_list = []
                    for stock in stock_list:
                        code = stock.split('.')[0]  # 提取股票代码
                        if code in top_codes:
                            filtered_list.append(stock)
                    
                    excluded_count = len(stock_list) - len(filtered_list)
                    
                    logger.info(f"✓ 过滤完成：")
                    logger.info(f"  保留: {len(filtered_list)} 只（当前成交额前 {active_threshold*100:.0f}%）")
                    logger.info(f"  排除: {excluded_count} 只（成交额靠后，长期冷门）")
                    return filtered_list
                    
                except Exception as e:
                    logger.error(f"过滤失败: {e}，返回全部股票")
                    import traceback
                    logger.error(traceback.format_exc())
                    return stock_list
            
            return stock_list
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return []
    
    def get_stock_daily(
        self, 
        symbol: str, 
        start_date: str, 
        end_date: str,
        adjust: str = "qfq"
    ) -> Optional[pd.DataFrame]:
        """
        获取个股日线数据
        
        Args:
            symbol: 股票代码，如 '000001.SZ'
            start_date: 开始日期，格式 '20200101'
            end_date: 结束日期，格式 '20241231'
            adjust: 复权类型，'qfq'前复权, 'hfq'后复权, ''不复权
            
        Returns:
            DataFrame with columns: [open, close, high, low, volume, amount]
        """
        try:
            # 转换为 AKShare 格式
            code = symbol.split('.')[0]
            
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=adjust
            )
            
            if df.empty:
                return None
            
            # 转换为 Qlib 标准格式
            df_qlib = pd.DataFrame({
                'open': df['开盘'].values,
                'close': df['收盘'].values,
                'high': df['最高'].values,
                'low': df['最低'].values,
                'volume': df['成交量'].values,
                'amount': df['成交额'].values,
            }, index=pd.to_datetime(df['日期']))
            
            return df_qlib
            
        except Exception as e:
            logger.error(f"获取 {symbol} 数据失败: {e}")
            return None
    
    def download_all_stocks(
        self,
        start_date: str = "20200101",
        end_date: Optional[str] = None,
        delay: float = 1.0,
        max_stocks: Optional[int] = None,
        random_delay: bool = True,
        filter_inactive: bool = False,
        active_threshold: float = 0.7
    ):
        """
        下载所有股票的历史数据
        
        ⚠️ 警告：批量下载可能被视为爬虫，建议：
        - 增加延迟时间（delay >= 1秒）
        - 分批下载（设置 max_stocks）
        - 错峰下载（非交易时段）
        - 优先下载活跃股票（设置 filter_inactive=True）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期，默认为今天
            delay: 基础请求延迟（秒），默认1秒，建议1-3秒
            max_stocks: 最大下载数量，None表示全部（用于分批下载）
            random_delay: 是否使用随机延迟（更安全）
            filter_inactive: 是否过滤不活跃股票（推荐：True）
            active_threshold: 活跃度阈值，保留成交额前X%的股票，默认0.7（前70%）
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')
        
        stock_list = self.get_stock_list(
            filter_inactive=filter_inactive,
            active_threshold=active_threshold
        )
        
        # 限制下载数量（用于分批）
        if max_stocks:
            stock_list = stock_list[:max_stocks]
            logger.warning(f"⚠️ 限制下载数量: {max_stocks} 只股票")
        
        total = len(stock_list)
        success = 0
        failed = 0
        
        logger.info(f"开始下载 {total} 只股票数据，时间范围: {start_date} - {end_date}")
        logger.info(f"延迟设置: {delay}秒{'(随机)' if random_delay else ''}")
        if filter_inactive:
            logger.info(f"✅ 已启用活跃度过滤（保留成交额前 {active_threshold*100:.0f}%）")
        logger.warning("⚠️ 批量下载可能被视为爬虫，建议:")
        logger.warning("  1. 增加延迟时间（1-3秒）")
        logger.warning("  2. 分批下载（分多天完成）")
        logger.warning("  3. 错峰下载（非交易时段）")
        logger.warning("  4. 使用 download_stock_pool() 只下载关注股票")
        logger.warning("  4. 使用 download_stock_pool() 只下载关注股票")
        
        for idx, symbol in enumerate(stock_list, 1):
            try:
                df = self.get_stock_daily(symbol, start_date, end_date)
                
                if df is not None and not df.empty:
                    # 保存到本地
                    self._save_stock_data(symbol, df)
                    success += 1
                    
                    if idx % 50 == 0:
                        logger.info(f"进度: {idx}/{total} ({idx/total*100:.1f}%), "
                                  f"成功: {success}, 失败: {failed}")
                else:
                    failed += 1
                
                # 随机延迟，更安全
                if random_delay:
                    actual_delay = delay + np.random.uniform(0, delay * 0.5)
                else:
                    actual_delay = delay
                
                time.sleep(actual_delay)
                
            except Exception as e:
                logger.error(f"下载 {symbol} 失败: {e}")
                failed += 1
                
                # 如果连续失败，可能被限流，增加延迟
                if failed > success * 0.1 and failed > 10:
                    logger.warning(f"⚠️ 失败率过高({failed}/{idx})，可能被限流，增加延迟到 {delay * 2}秒")
                    time.sleep(delay * 2)
                
                continue
        
        logger.info(f"下载完成! 总计: {total}, 成功: {success}, 失败: {failed}")
    
    def download_index(
        self,
        index_code: str,
        start_date: str = "20200101",
        end_date: Optional[str] = None
    ):
        """
        下载指数数据（如沪深300）
        
        Args:
            index_code: 指数代码，如 'sh000300'
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期，None表示今天
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')
        
        logger.info(f"下载指数数据: {index_code}, 时间范围: {start_date} - {end_date}")
        
        try:
            # 获取指数日线数据（直接使用完整代码）
            df = ak.stock_zh_index_daily(symbol=index_code)
            
            if df is None or df.empty:
                logger.error(f"指数 {index_code} 数据为空")
                return
            
            # 过滤日期范围
            df['date'] = pd.to_datetime(df['date'])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
            
            if df.empty:
                logger.warning(f"指定日期范围内无数据: {start_date} - {end_date}")
                return
            
            # 计算涨跌幅
            df['change'] = df['close'].pct_change()
            df['factor'] = 1.0  # 指数不需要复权因子
            
            # 保存
            self._save_stock_data(index_code, df)
            logger.info(f"✓ 指数 {index_code} 下载完成: {len(df)} 条记录")
            
        except Exception as e:
            logger.error(f"下载指数 {index_code} 失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def download_stock_pool(
        self,
        stock_pool: List[str],
        start_date: str = "20200101",
        end_date: Optional[str] = None,
        delay: float = 0.5
    ):
        """
        下载指定股票池的数据（推荐使用）
        
        相比 download_all_stocks，这个方法更安全：
        - 只下载需要的股票，数量可控
        - 请求量小，不容易被限流
        - 更快完成下载
        
        Args:
            stock_pool: 股票代码列表，如 ['000001.SZ', '600000.SH']
            start_date: 开始日期
            end_date: 结束日期
            delay: 请求延迟（秒）
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')
        
        total = len(stock_pool)
        success = 0
        failed = 0
        
        logger.info(f"开始下载股票池数据: {total} 只股票")
        logger.info(f"时间范围: {start_date} - {end_date}")
        
        for idx, symbol in enumerate(stock_pool, 1):
            try:
                logger.info(f"[{idx}/{total}] 下载 {symbol}...")
                df = self.get_stock_daily(symbol, start_date, end_date)
                
                if df is not None and not df.empty:
                    self._save_stock_data(symbol, df)
                    success += 1
                else:
                    failed += 1
                
                time.sleep(delay)
                
            except Exception as e:
                logger.error(f"下载 {symbol} 失败: {e}")
                failed += 1
                continue
        
        logger.info(f"下载完成! 成功: {success}, 失败: {failed}")
    
    def _save_stock_data(self, symbol: str, df: pd.DataFrame):
        """保存股票数据到本地"""
        # 创建股票目录
        stock_dir = self.qlib_data_path / "instruments"
        stock_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存为 CSV 格式（Qlib 会自动转换）
        file_path = stock_dir / f"{symbol}.csv"
        df.to_csv(file_path)
    
    def get_market_emotion_data(self, date: Optional[str] = None) -> dict:
        """
        获取市场情绪数据
        
        Args:
            date: 日期，格式 '2024-01-01'，None表示今天
            
        Returns:
            市场情绪指标字典
        """
        try:
            df = ak.stock_zh_a_spot_em()
            
            emotion = {
                'date': date or datetime.now().strftime('%Y-%m-%d'),
                'total_count': len(df),
                'up_count': len(df[df['涨跌幅'] > 0]),
                'down_count': len(df[df['涨跌幅'] < 0]),
                'flat_count': len(df[df['涨跌幅'] == 0]),
                'limit_up_count': len(df[df['涨跌幅'] >= 9.9]),
                'limit_down_count': len(df[df['涨跌幅'] <= -9.9]),
                'avg_pct_change': df['涨跌幅'].mean(),
                'median_pct_change': df['涨跌幅'].median(),
                'total_amount': df['成交额'].sum(),
            }
            
            return emotion
            
        except Exception as e:
            logger.error(f"获取市场情绪数据失败: {e}")
            return {}
    
    def get_sector_data(self) -> pd.DataFrame:
        """
        获取板块数据
        
        Returns:
            DataFrame with columns: [板块名称, 涨跌幅, 换手率, 成交额, ...]
        """
        try:
            # 概念板块
            concept = ak.stock_board_concept_name_em()
            concept['板块类型'] = '概念'
            
            # 行业板块
            industry = ak.stock_board_industry_name_em()
            industry['板块类型'] = '行业'
            
            # 合并
            df = pd.concat([concept, industry], ignore_index=True)
            
            return df
            
        except Exception as e:
            logger.error(f"获取板块数据失败: {e}")
            return pd.DataFrame()
    
    def get_sector_constituents(self, sector_name: str) -> List[str]:
        """
        获取板块成分股
        
        Args:
            sector_name: 板块名称
            
        Returns:
            成分股代码列表
        """
        try:
            df = ak.stock_board_concept_cons_em(symbol=sector_name)
            
            stock_list = []
            for code in df['代码'].tolist():
                if code.startswith('6'):
                    stock_list.append(f"{code}.SH")
                else:
                    stock_list.append(f"{code}.SZ")
            
            return stock_list
            
        except Exception as e:
            logger.error(f"获取板块 {sector_name} 成分股失败: {e}")
            return []
    
    def download_stock_industry_mapping(self, save_path: Optional[str] = None, delay: float = 1.0) -> dict:
        """
        下载所有股票的行业分类映射
        
        Args:
            save_path: 保存路径，默认为 qlib_data_path/stock_industry_mapping.json
            delay: 请求延迟（秒），默认1秒，建议1-2秒
            
        Returns:
            股票-行业映射字典 {股票代码: 行业名称}
        """
        import json
        
        if save_path is None:
            save_path = self.qlib_data_path / "stock_industry_mapping.json"
        else:
            save_path = Path(save_path)
        
        logger.info("=" * 60)
        logger.info("开始下载股票行业分类数据")
        logger.info("=" * 60)
        
        # 获取所有股票列表
        stock_list = self.get_stock_list(filter_inactive=False)
        logger.info(f"待获取行业信息的股票数: {len(stock_list)}")
        logger.info(f"请求延迟: {delay}秒（随机）")
        logger.warning("⚠️ 批量下载可能被限流，建议:")
        logger.warning("  1. 使用1-2秒延迟")
        logger.warning("  2. 分批下载（中断后可续传）")
        logger.warning("  3. 错峰下载（非交易时段）")
        
        mapping = {}
        success_count = 0
        fail_count = 0
        
        for i, stock_code in enumerate(stock_list):
            try:
                # 提取股票代码（去掉.SH/.SZ后缀）
                code = stock_code.split('.')[0]
                
                # 获取股票信息
                info = ak.stock_individual_info_em(symbol=code)
                
                # 查找行业字段
                industry_row = info[info['item'] == '行业']
                if not industry_row.empty:
                    industry = industry_row.iloc[0]['value']
                    mapping[stock_code] = industry
                    success_count += 1
                else:
                    fail_count += 1
                    logger.debug(f"{stock_code}: 无行业信息")
                
                # 每50只打印进度并保存
                if (i + 1) % 50 == 0:
                    logger.info(f"进度: {i+1}/{len(stock_list)} ({(i+1)/len(stock_list)*100:.1f}%), "
                              f"成功: {success_count}, 失败: {fail_count}")
                    
                    # 保存中间结果
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, 'w', encoding='utf-8') as f:
                        json.dump(mapping, f, ensure_ascii=False, indent=2)
                    logger.debug(f"中间结果已保存")
                
                # 随机延迟，避免被限流
                actual_delay = delay + np.random.uniform(0, delay * 0.5)
                time.sleep(actual_delay)
                    
            except Exception as e:
                fail_count += 1
                logger.debug(f"{stock_code}: 获取失败 - {e}")
                
                # 如果连续失败率过高，可能被限流
                if fail_count > success_count * 0.2 and fail_count > 20:
                    logger.warning(f"⚠️ 失败率过高({fail_count}/{i+1})，可能被限流，增加延迟到 {delay * 3}秒")
                    time.sleep(delay * 3)
                
                continue
        
        # 保存最终结果
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        
        logger.info("=" * 60)
        logger.info(f"✅ 下载完成!")
        logger.info(f"成功: {success_count}, 失败: {fail_count}")
        logger.info(f"保存路径: {save_path.absolute()}")
        logger.info("=" * 60)
        
        # 统计行业分布
        industry_stats = {}
        for industry in mapping.values():
            industry_stats[industry] = industry_stats.get(industry, 0) + 1
        
        logger.info("\n行业分布（前20）:")
        sorted_industries = sorted(industry_stats.items(), key=lambda x: x[1], reverse=True)
        for industry, count in sorted_industries[:20]:
            logger.info(f"  {industry}: {count}只")
        
        return mapping


if __name__ == "__main__":
    # 测试代码
    provider = AKShareProvider()
    
    # 测试获取股票列表
    stocks = provider.get_stock_list()
    print(f"股票数量: {len(stocks)}")
    print(f"前10只: {stocks[:10]}")
    
    # 测试获取个股数据
    df = provider.get_stock_daily('000001.SZ', '20240101', '20241231')
    print(f"\n000001.SZ 数据:\n{df.head()}")
    
    # 测试获取市场情绪
    emotion = provider.get_market_emotion_data()
    print(f"\n市场情绪: {emotion}")
    
    # 测试获取板块数据
    sectors = provider.get_sector_data()
    print(f"\n板块数量: {len(sectors)}")
    print(f"热门板块:\n{sectors.head()}")
