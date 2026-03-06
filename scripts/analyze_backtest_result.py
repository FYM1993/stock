"""
分析回测结果

从YAML文件中提取关键指标并生成报告
"""

import yaml
import pandas as pd
from pathlib import Path
from loguru import logger

def analyze_result(result_file: str):
    """分析回测结果"""
    
    logger.info("="*60)
    logger.info("回测结果分析")
    logger.info("="*60)
    
    # 加载结果
    with open(result_file, 'r', encoding='utf-8') as f:
        results = yaml.safe_load(f)
    
    config = results.get('config', {})
    portfolio_metrics = results.get('portfolio_metrics', {})
    indicators = results.get('indicators', {})
    
    # 打印配置
    logger.info("\n配置信息:")
    logger.info(f"  回测时间: {config.get('start_time')} ~ {config.get('end_time')}")
    logger.info(f"  初始资金: {config.get('account'):,}")
    logger.info(f"  策略参数: topk={config['strategy']['topk']}, "
               f"max_positions={config['strategy']['max_positions']}, "
               f"position_size={config['strategy']['position_size']}")
    
    # 打印组合指标
    logger.info("\n组合指标:")
    if portfolio_metrics:
        for key, value in portfolio_metrics.items():
            if isinstance(value, (int, float)):
                logger.info(f"  {key}: {value:.4f}")
            else:
                logger.info(f"  {key}: {value}")
    else:
        logger.warning("  ⚠️  无组合指标数据")
    
    # 分析交易数据
    logger.info("\n交易分析:")
    if '1day' in indicators and indicators['1day']:
        try:
            positions_df = indicators['1day'][0]
            logger.info(f"  总交易日数: {len(positions_df)}")
            
            # 统计持仓情况
            trades = []
            for date, row in positions_df.iterrows():
                position_count = row.count() - row.isna().sum()
                if position_count > 0:
                    trades.append({'date': date, 'count': position_count})
            
            if trades:
                logger.info(f"  实际交易天数: {len(trades)}")
                avg_positions = sum(t['count'] for t in trades) / len(trades)
                logger.info(f"  平均持仓数: {avg_positions:.2f}只")
            else:
                logger.warning("  ⚠️  整个回测期间未产生任何持仓")
        except Exception as e:
            logger.error(f"  交易分析失败: {e}")
    else:
        logger.warning("  ⚠️  无交易数据")
    
    # 分析账户收益
    logger.info("\n账户分析:")
    initial_account = config.get('account', 100000)
    
    # 尝试从indicators中提取账户价值变化
    if '1day' in indicators and len(indicators['1day']) > 0:
        try:
            # 通常第二个DataFrame是账户价值
            if len(indicators['1day']) > 1:
                account_df = indicators['1day'][1]
                if not account_df.empty:
                    final_value = account_df.iloc[-1].sum()
                    total_return = (final_value - initial_account) / initial_account * 100
                    logger.info(f"  期初资金: {initial_account:,.0f}")
                    logger.info(f"  期末资金: {final_value:,.0f}")
                    logger.info(f"  总收益率: {total_return:.2f}%")
                else:
                    logger.warning("  ⚠️  账户数据为空")
        except Exception as e:
            logger.error(f"  账户分析失败: {e}")
    
    logger.info("\n" + "="*60)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        result_file = sys.argv[1]
    else:
        # 使用最新的结果文件
        results_dir = Path(__file__).parent.parent / "results"
        result_files = sorted(results_dir.glob("backtest_*.yaml"), key=lambda x: x.stat().st_mtime)
        if result_files:
            result_file = result_files[-1]
        else:
            logger.error("未找到回测结果文件")
            sys.exit(1)
    
    logger.info(f"分析文件: {result_file}")
    analyze_result(result_file)
