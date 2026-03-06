"""
测试最小化策略
"""

import qlib
from qlib.config import REG_CN
from qlib.backtest import backtest, executor
from pathlib import Path
from loguru import logger
import sys

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from strategies.minimal_test_strategy import MinimalTestStrategy

def test_minimal():
    """测试最小策略"""
    
    # 初始化Qlib
    data_path = project_root / "qlib_data" / "cn_data"
    qlib.init(provider_uri=str(data_path), region=REG_CN)
    
    logger.info("="*60)
    logger.info("测试最小化策略")
    logger.info("="*60)
    
    # 创建策略
    strategy = MinimalTestStrategy()
    
    # 运行回测
    try:
        portfolio_metric_dict, indicator_dict = backtest(
            start_time="2025-03-01",
            end_time="2025-03-10",  # 只测试10天
            strategy=strategy,
            executor=executor.SimulatorExecutor(
                time_per_step="day",
                generate_portfolio_metrics=True
            ),
            benchmark="000300.SH",  # 沪深300指数
            account=100000
        )
        
        logger.info("\n✅ 回测完成！")
        logger.info(f"\n组合指标:")
        for key, value in (portfolio_metric_dict or {}).items():
            logger.info(f"  {key}: {value}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_minimal()
