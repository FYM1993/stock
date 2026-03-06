"""
从日志分析v18回测结果
"""

import re
from collections import defaultdict
from pathlib import Path

def analyze_log(log_file):
    """分析回测日志"""
    
    print("="*60)
    print("v18 回测结果分析")
    print("="*60)
    
    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取买入记录
    buy_pattern = r'✅ 买入信号: ([^,]+), 信号类型: ([^,]+), 价格: ¥([\d.]+), 股数: (\d+), 预计金额: ([\d,]+)'
    buy_matches = re.findall(buy_pattern, content)
    
    # 提取卖出记录
    sell_pattern = r'卖出信号: ([^,]+), 信号类型: ([^,]+), 数量: ([\d.]+)'
    sell_matches = re.findall(sell_pattern, content)
    
    # 提取龙头切换记录
    leader_pattern = r'🔄 龙头切换: ([^\s]+) → ([^\s]+) \(板块: ([^)]+)\)'
    leader_matches = re.findall(leader_pattern, content)
    
    # 提取资金状态（取最后一个）
    money_pattern = r'💰 资金状态: 可用=([\d,]+), 总值=([\d,]+), 仓位=([\d.]+)%, 持股=(\d+)只'
    money_matches = re.findall(money_pattern, content)
    
    # 统计
    print(f"\n交易统计:")
    print(f"  买入次数: {len(buy_matches)}")
    print(f"  卖出次数: {len(sell_matches)}")
    print(f"  龙头切换: {len(leader_matches)}次")
    
    # 买入信号类型分布
    buy_signal_types = defaultdict(int)
    for _, signal_type, _, _, _ in buy_matches:
        buy_signal_types[signal_type] += 1
    
    print(f"\n买入信号类型分布:")
    for signal_type, count in sorted(buy_signal_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {signal_type}: {count}次")
    
    # 卖出信号类型分布
    sell_signal_types = defaultdict(int)
    for _, signal_type, _ in sell_matches:
        sell_signal_types[signal_type] += 1
    
    print(f"\n卖出信号类型分布:")
    for signal_type, count in sorted(sell_signal_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {signal_type}: {count}次")
    
    # 最后的资金状态
    if money_matches:
        last_money = money_matches[-1]
        available = int(last_money[0].replace(',', ''))
        total = int(last_money[1].replace(',', ''))
        position_pct = float(last_money[2])
        holdings = int(last_money[3])
        
        print(f"\n最终账户状态:")
        print(f"  可用资金: ¥{available:,}")
        print(f"  总资产: ¥{total:,}")
        print(f"  仓位: {position_pct}%")
        print(f"  持股数: {holdings}只")
        
        # 计算收益率
        initial = 100000
        returns = (total - initial) / initial * 100
        print(f"\n收益分析:")
        print(f"  期初资金: ¥{initial:,}")
        print(f"  期末资金: ¥{total:,}")
        print(f"  总收益: ¥{total - initial:,}")
        print(f"  收益率: {returns:.2f}%")
    
    # 买入的股票列表
    print(f"\n买入股票列表:")
    stocks_bought = defaultdict(int)
    for stock, _, _, _, _ in buy_matches:
        stocks_bought[stock] += 1
    
    for stock, count in sorted(stocks_bought.items(), key=lambda x: x[1], reverse=True):
        print(f"  {stock}: {count}次")
    
    # 龙头切换记录（前10个）
    if leader_matches:
        print(f"\n龙头切换记录（前10个）:")
        for i, (from_leader, to_leader, sector) in enumerate(leader_matches[:10], 1):
            print(f"  {i}. {from_leader} → {to_leader} (板块: {sector})")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    log_file = Path(__file__).parent.parent / "logs" / "backtest_v18.log"
    if not log_file.exists():
        print(f"日志文件不存在: {log_file}")
    else:
        analyze_log(log_file)
