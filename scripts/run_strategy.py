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
from datetime import datetime

import qlib
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord
from qlib.utils import init_instance_by_config

# 添加 scripts 目录到 Python 路径，以便导入自定义策略
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "scripts"))

# 报告目录
REPORTS_DIR = Path("reports")

 
def load_config(config_path: str = "config.yaml") -> dict:
    """加载配置文件"""
    config_file = Path(config_path)
    
    if not config_file.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config


def generate_backtest_report(exp_name, recorder, config):
    """生成回测报告 Markdown 文件"""
    try:
        # 加载持仓数据
        positions = recorder.load_object("portfolio_analysis/positions_normal_1day.pkl")
        
        # 加载回测指标
        report = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
        
        if positions is None or report is None:
            print("⚠️  未找到回测数据，跳过报告生成")
            return
        
        # 处理持仓数据
        import pandas as pd
        if isinstance(positions, dict) and 'stock' in positions:
            positions = positions['stock']
        
        # 计算每只股票的收益贡献
        stock_contributions = {}
        if isinstance(positions, pd.DataFrame):
            for col in positions.columns:
                if col not in ['cash', 'now_account_value', 'today_account_value']:
                    stock_data = positions[col].dropna()
                    if len(stock_data) > 0:
                        stock_contributions[col] = {
                            'total': stock_data.sum(),
                            'days': len(stock_data),
                            'avg': stock_data.mean()
                        }
        
        # 排序
        sorted_stocks = sorted(stock_contributions.items(), 
                              key=lambda x: x[1]['total'], 
                              reverse=True)
        
        # 提取回测指标
        metrics_with_cost = report.get('excess_return_with_cost', {})
        metrics_without_cost = report.get('excess_return_without_cost', {})
        
        # 生成 Markdown 内容
        md_content = f"""# 回测报告 — {exp_name}

生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

## 📊 回测指标

### ✅ 考虑交易成本
- **年化收益率**: {metrics_with_cost.get('annualized_return', 0):.2%}
- **信息比率**: {metrics_with_cost.get('information_ratio', 0):.4f}
- **最大回撤**: {metrics_with_cost.get('max_drawdown', 0):.2%}

### ℹ️ 不考虑交易成本
- **年化收益率**: {metrics_without_cost.get('annualized_return', 0):.2%}
- **信息比率**: {metrics_without_cost.get('information_ratio', 0):.4f}
- **最大回撤**: {metrics_without_cost.get('max_drawdown', 0):.2%}

---

## 🟢 盈利贡献 Top 10

| 排名 | 股票代码 | 累计贡献 | 持仓天数 | 日均贡献 |
|------|----------|----------|----------|----------|
"""
        
        for i, (stock, data) in enumerate(sorted_stocks[:10], 1):
            md_content += f"| {i} | {stock} | {data['total']:,.2f} | {data['days']} | {data['avg']:,.4f} |\n"
        
        md_content += """
---

## 🔴 亏损贡献 Top 10

| 排名 | 股票代码 | 累计贡献 | 持仓天数 | 日均贡献 |
|------|----------|----------|----------|----------|
"""
        
        for i, (stock, data) in enumerate(sorted_stocks[-10:], 1):
            md_content += f"| {i} | {stock} | {data['total']:,.2f} | {data['days']} | {data['avg']:,.4f} |\n"
        
        # 统计信息
        total_positive = sum(1 for s, d in stock_contributions.items() if d['total'] > 0)
        total_negative = sum(1 for s, d in stock_contributions.items() if d['total'] < 0)
        total_profit = sum(d['total'] for s, d in stock_contributions.items() if d['total'] > 0)
        total_loss = sum(d['total'] for s, d in stock_contributions.items() if d['total'] < 0)
        
        md_content += f"""
---

## 📈 统计信息

- 总交易股票数: {len(stock_contributions)}
- 盈利股票数: {total_positive} ({total_positive/len(stock_contributions)*100:.1f}%)
- 亏损股票数: {total_negative} ({total_negative/len(stock_contributions)*100:.1f}%)
- 总盈利贡献: ¥{total_profit:,.2f}
- 总亏损贡献: ¥{total_loss:,.2f}
- 净收益: ¥{total_profit + total_loss:,.2f}

---

## ⚙️ 配置信息

- 股票池: {config.get('market', 'N/A')}
- 持仓数量: {config.get('port_analysis_config', {}).get('strategy', {}).get('kwargs', {}).get('topk', 'N/A')}
- 回测周期: {config.get('dataset', {}).get('kwargs', {}).get('handler', {}).get('kwargs', {}).get('start_time', 'N/A')} 至 {config.get('dataset', {}).get('kwargs', {}).get('handler', {}).get('kwargs', {}).get('end_time', 'N/A')}
"""
        
        # 保存报告
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / f"{exp_name}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        
        print(f"📄 回测报告已保存: {report_path}")
        
        # 在终端输出盈利 Top 10
        print("\n📊 盈利贡献 Top 10:")
        print(f"{'排名':<6}{'股票代码':<12}{'累计贡献':>15}{'持仓天数':>12}{'日均贡献':>15}")
        print("-" * 70)
        for i, (stock, data) in enumerate(sorted_stocks[:10], 1):
            print(f"{i:<6}{stock:<12}{data['total']:>15,.2f}{data['days']:>12}{data['avg']:>15,.4f}")
        
    except Exception as e:
        print(f"⚠️  生成报告失败: {e}")
        import traceback
        traceback.print_exc()


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
        
        # 生成回测报告
        print("=" * 60)
        print("📝 生成回测报告...")
        print("=" * 60)
        generate_backtest_report(exp_name, rec, config)


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

