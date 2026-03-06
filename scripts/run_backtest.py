"""
运行回测

使用 Qlib 回测引擎测试龙头低吸策略
"""

import qlib
from qlib.config import REG_CN
from qlib.backtest import backtest, executor
from qlib.contrib.strategy import TopkDropoutStrategy
from qlib.contrib.evaluate import risk_analysis
from qlib.contrib.report import analysis_position, analysis_model
from qlib.data import D

import sys
from pathlib import Path
from datetime import datetime
from loguru import logger
import yaml

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from strategies.leader_low_absorption import LeaderLowAbsorptionStrategy
from data.emotion_data import EmotionDataManager


def load_config(config_path: str = None) -> dict:
    """加载配置文件"""
    if config_path is None:
        config_path = project_root / "configs" / "strategy_config.yaml"
    
    if not Path(config_path).exists():
        logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
        return get_default_config()
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config


def get_default_config() -> dict:
    """获取默认配置"""
    return {
        'market': 'csi300',
        'benchmark': 'SH000300',
        'start_time': '2020-01-01',
        'end_time': '2024-12-31',
        'account': 1000000,  # 初始资金100万
        'strategy': {
            'topk': 10,
            'max_positions': 3,
            'position_size': 0.3,
            'ice_point_threshold': 1000,
            'climax_threshold': 3500,
            'ma_period': 5
        },
        'executor': {
            'trade_type': 'day',
            'generate_report': True
        }
    }


def run_backtest(config: dict):
    """
    运行回测
    
    Args:
        config: 配置字典
    """
    logger.info("="*60)
    logger.info("开始回测")
    logger.info("="*60)
    
    # 初始化 Qlib (使用项目本地数据路径)
    data_path = project_root / "qlib_data" / "cn_data"
    qlib.init(
        provider_uri=str(data_path),
        region=REG_CN
    )
    
    # 获取配置
    market = config.get('market', 'csi300')
    benchmark = config.get('benchmark', 'SH000300')
    start_time = config.get('start_time', '2020-01-01')
    end_time = config.get('end_time', '2024-12-31')
    account = config.get('account', 1000000)
    
    logger.info(f"市场: {market}")
    logger.info(f"基准: {benchmark}")
    logger.info(f"时间范围: {start_time} ~ {end_time}")
    logger.info(f"初始资金: {account:,.0f}")
    
    # 创建策略
    strategy_config = config.get('strategy', {})
    strategy = LeaderLowAbsorptionStrategy(
        **strategy_config
    )
    
    logger.info(f"策略参数: {strategy_config}")
    
    # 创建执行器
    executor_config = config.get('executor', {})
    
    # 运行回测
    logger.info("\n开始回测...")
    
    try:
        # Qlib 回测接口
        portfolio_metric_dict, indicator_dict = backtest(
            start_time=start_time,
            end_time=end_time,
            strategy=strategy,
            executor=executor.SimulatorExecutor(
                time_per_step="day",
                generate_portfolio_metrics=True
            ),
            benchmark=benchmark,
            account=account,
        )
        
        logger.info("\n回测完成!")
        
        # 分析结果
        analyze_results(portfolio_metric_dict, indicator_dict, config)
        
    except Exception as e:
        logger.error(f"回测失败: {e}")
        import traceback
        traceback.print_exc()


def analyze_results(portfolio_metric_dict, indicator_dict, config):
    """
    分析回测结果
    
    Args:
        portfolio_metric_dict: 组合指标
        indicator_dict: 其他指标
        config: 配置
    """
    logger.info("\n" + "="*60)
    logger.info("回测结果分析")
    logger.info("="*60)
    
    # 提取关键指标
    if portfolio_metric_dict:
        logger.info("\n组合指标:")
        for key, value in portfolio_metric_dict.items():
            if isinstance(value, (int, float)):
                logger.info(f"  {key}: {value:.4f}")
    
    # 风险分析
    logger.info("\n进行风险分析...")
    
    # 保存结果
    save_results(portfolio_metric_dict, indicator_dict, config)


def save_results(portfolio_metric_dict, indicator_dict, config):
    """
    保存回测结果
    
    Args:
        portfolio_metric_dict: 组合指标
        indicator_dict: 其他指标
        config: 配置
    """
    results_dir = project_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    result_file = results_dir / f"backtest_{timestamp}.yaml"
    
    results = {
        'config': config,
        'portfolio_metrics': portfolio_metric_dict,
        'indicators': indicator_dict,
        'timestamp': timestamp
    }
    
    with open(result_file, 'w', encoding='utf-8') as f:
        yaml.dump(results, f, allow_unicode=True)
    
    logger.info(f"\n结果已保存到: {result_file}")


def main():
    """主函数"""
    # 加载配置
    config = load_config()
    
    # 运行回测
    run_backtest(config)
    
    logger.info("\n完成!")


if __name__ == "__main__":
    main()
