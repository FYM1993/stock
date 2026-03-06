"""
测试Qlib官方策略是否能正常交易

用TopkDropoutStrategy验证Qlib系统本身
"""

import qlib
from qlib.config import REG_CN
from qlib.backtest import backtest, executor
from qlib.contrib.strategy import TopkDropoutStrategy
from pathlib import Path
from loguru import logger

project_root = Path(__file__).parent.parent

def test_official_strategy():
    """测试Qlib官方策略"""
    
    # 初始化Qlib
    data_path = project_root / "qlib_data" / "cn_data"
    qlib.init(provider_uri=str(data_path), region=REG_CN)
    
    logger.info("="*60)
    logger.info("测试Qlib官方TopkDropoutStrategy")
    logger.info("="*60)
    
    # 创建官方策略
    strategy = TopkDropoutStrategy(
        model=None,  # 不使用模型，用随机选股
        dataset=None,
        topk=5,
        n_drop=1
    )
    
    # 运行回测
    try:
        portfolio_metric_dict, indicator_dict = backtest(
            start_time="2025-03-01",
            end_time="2025-03-31",
            strategy=strategy,
            executor=executor.SimulatorExecutor(
                time_per_step="day",
                generate_portfolio_metrics=True
            ),
            benchmark="SH000300",
            account=100000
        )
        
        logger.info("\n✅ 回测完成！")
        logger.info(f"组合指标: {portfolio_metric_dict}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_official_strategy()
    
    if success:
        print("\n" + "="*60)
        print("✅ Qlib系统正常，问题出在我们的策略实现")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("❌ Qlib系统异常或数据问题")
        print("="*60)
