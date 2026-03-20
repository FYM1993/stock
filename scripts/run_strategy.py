#!/usr/bin/env python3
"""
A股量化策略
===========

基于 Qlib 的量化策略，使用 config.yaml 配置所有参数。

使用示例：
    # 使用默认配置
    python scripts/run_strategy.py
    
    # 使用自定义配置文件
    python scripts/run_strategy.py custom_config.yaml
"""

import sys
import yaml
from pathlib import Path

import qlib
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord
from qlib.utils import init_instance_by_config

# 添加 scripts 目录到 Python 路径，以便导入自定义策略
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "scripts"))

 
def load_config(config_path: str = "config.yaml") -> dict:
    """加载配置文件"""
    config_file = Path(config_path)
    
    if not config_file.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config


def print_config_summary(config: dict):
    """打印配置摘要"""
    print("=" * 60)
    print("🚀 A股量化策略")
    print("=" * 60)
    print(f"股票池:   {config['market']}")
    print(f"基准:     {config['benchmark']}")
    print(f"持仓数:   {config['port_analysis_config']['strategy']['kwargs']['topk']} 只")
    print()
    
    segments = config['dataset']['kwargs']['segments']
    print("📅 时间配置:")
    print(f"  训练集: {segments['train'][0]} ~ {segments['train'][1]}")
    print(f"  验证集: {segments['valid'][0]} ~ {segments['valid'][1]}")
    print(f"  测试集: {segments['test'][0]} ~ {segments['test'][1]}")
    print()
    
    backtest = config['port_analysis_config']['backtest']
    print("💰 回测配置:")
    print(f"  初始资金: {backtest['account']:,.0f} 元")
    print(f"  开仓费率: {backtest['exchange_kwargs']['open_cost']:.4f}")
    print(f"  平仓费率: {backtest['exchange_kwargs']['close_cost']:.4f}")
    print("=" * 60)
    print()


def run_strategy(config: dict):
    """运行策略"""
    # 初始化Qlib
    qlib.init(**config["qlib_init"])
    
    # 打印配置
    print_config_summary(config)
    
    # 生成实验名称（基于时间和市场）
    from datetime import datetime
    exp_name = f"{config['market']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 开始实验
    with R.start(experiment_name=exp_name):
        print("📊 1/4 初始化模型和数据集...")
        model = init_instance_by_config(config["model"])
        dataset = init_instance_by_config(config["dataset"])
        
        print("🎯 2/4 训练模型...")
        model.fit(dataset)
        
        print("📈 3/4 生成预测信号...")
        rec = R.get_recorder()
        
        # 保存模型（方便后续加载）
        rec.save_objects(trained_model=model)
        
        sr = SignalRecord(model, dataset, rec)
        sr.generate()
        
        print("💹 4/4 执行回测...")
        par = PortAnaRecord(rec, config=config["port_analysis_config"])
        par.generate()
        
        print()
        print("=" * 60)
        print("✅ 策略运行完成！")
        print("=" * 60)
        print(f"📁 结果保存在实验: {exp_name}")
        print()
        
        # 打印关键指标
        try:
            report = par.load()
            if report is not None and '1day' in report:
                metrics = report['1day']
                print("📊 回测结果:")
                print(f"  年化收益:   {metrics.get('annual_return', 0):.2%}")
                print(f"  夏普比率:   {metrics.get('information_ratio', 0):.4f}")
                print(f"  最大回撤:   {metrics.get('max_drawdown', 0):.2%}")
                print(f"  胜率:       {metrics.get('win_rate', 0):.2%}")
                print()
        except Exception as e:
            print(f"⚠️  无法显示指标详情: {e}")


def main():
    """主函数"""
    # 获取配置文件路径（默认使用 config.yaml）
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    
    print(f"📄 加载配置: {config_path}\n")
    
    # 加载配置
    config = load_config(config_path)
    
    # 运行策略
    run_strategy(config)


if __name__ == "__main__":
    main()

