#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专业量化回测报告 - 重点突出版

核心内容：
1. 账户收益曲线（最重要！）
2. 个股K线+买卖点标注
3. 简洁的统计摘要
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
import re
import json
from datetime import datetime
import numpy as np

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'STHeiti']
plt.rcParams['axes.unicode_minus'] = False

class ProfessionalBacktestReport:
    """专业回测报告生成器"""
    
    def __init__(self, log_file: str):
        self.log_file = Path(log_file)
        self.output_dir = Path('results/reports')
        self.charts_dir = Path('results/charts')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.charts_dir.mkdir(parents=True, exist_ok=True)
        
        # 解析交易数据
        self.trades = self._parse_trades()
        self.account_history = self._parse_account_history()
        
    def _parse_trades(self):
        """解析交易记录"""
        trades = []
        current_date = None
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                date_match = re.search(r'日期: (\d{4}-\d{2}-\d{2})', line)
                if date_match:
                    current_date = date_match.group(1)
                
                # 买入
                buy_match = re.search(r'✅ 买入信号: ([^,]+).*?预计金额: ([\d,]+)', line)
                if buy_match and current_date:
                    trades.append({
                        'date': current_date,
                        'symbol': buy_match.group(1),
                        'action': 'BUY',
                        'amount': float(buy_match.group(2).replace(',', ''))
                    })
                
                # 卖出
                sell_match = re.search(r'\[卖出检测\] ([^\s]+) - (.+?)（', line)
                if sell_match and current_date:
                    trades.append({
                        'date': current_date,
                        'symbol': sell_match.group(1),
                        'action': 'SELL',
                        'reason': sell_match.group(2)
                    })
        
        return pd.DataFrame(trades) if trades else pd.DataFrame()
    
    def _parse_account_history(self):
        """解析账户历史（从资金状态日志）"""
        account_data = []
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            current_date = None
            for line in f:
                # 提取日期
                date_match = re.search(r'日期: (\d{4}-\d{2}-\d{2})', line)
                if date_match:
                    current_date = date_match.group(1)
                
                # 提取资金状态： 💰 资金状态: 可用=100,000, 总值=100,000, 仓位=0.0%, 持股=0只
                money_match = re.search(
                    r'💰 资金状态: 可用=([\d,]+), 总值=([\d,]+), 仓位=([\d.]+)%, 持股=(\d+)只',
                    line
                )
                if money_match and current_date:
                    cash = float(money_match.group(1).replace(',', ''))
                    total_value = float(money_match.group(2).replace(',', ''))
                    position_rate = float(money_match.group(3))
                    positions = int(money_match.group(4))
                    
                    account_data.append({
                        'date': pd.to_datetime(current_date),
                        'cash': cash,
                        'total_value': total_value,
                        'position_rate': position_rate,
                        'positions': positions
                    })
        
        return pd.DataFrame(account_data) if account_data else pd.DataFrame()
    
    def create_account_curve(self):
        """1. 账户收益曲线（最重要的图）"""
        if self.account_history.empty:
            print("⚠️  无账户数据，无法生成收益曲线")
            return
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), 
                                       gridspec_kw={'height_ratios': [3, 1]})
        
        # 上图：账户净值曲线
        dates = self.account_history['date']
        values = self.account_history['total_value']
        initial_value = values.iloc[0]
        
        # 计算收益率
        returns = (values / initial_value - 1) * 100
        
        # 绘制净值曲线
        ax1.plot(dates, values, linewidth=2.5, color='#2E86C1', label='账户净值')
        ax1.fill_between(dates, initial_value, values, 
                         where=(values >= initial_value),
                         color='green', alpha=0.2, label='盈利区')
        ax1.fill_between(dates, initial_value, values,
                         where=(values < initial_value),
                         color='red', alpha=0.2, label='亏损区')
        
        # 基准线
        ax1.axhline(y=initial_value, color='gray', linestyle='--', 
                   linewidth=1, label=f'初始资金 ¥{initial_value:,.0f}')
        
        # 标注最终净值
        final_value = values.iloc[-1]
        final_return = returns.iloc[-1]
        color = 'green' if final_return > 0 else 'red'
        
        ax1.text(dates.iloc[-1], final_value, 
                f'¥{final_value:,.0f}\n({final_return:+.1f}%)',
                fontsize=12, fontweight='bold', color=color,
                bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))
        
        ax1.set_title('账户净值曲线', fontsize=16, fontweight='bold', pad=20)
        ax1.set_ylabel('账户净值 (¥)', fontsize=12)
        ax1.legend(loc='upper left', fontsize=10)
        ax1.grid(True, alpha=0.3)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'¥{x/1000:.0f}K'))
        
        # 下图：持仓数量
        ax2.fill_between(dates, 0, self.account_history['positions'],
                        color='steelblue', alpha=0.5)
        ax2.plot(dates, self.account_history['positions'],
                color='darkblue', linewidth=2)
        ax2.set_title('持仓数量变化', fontsize=12, fontweight='bold')
        ax2.set_xlabel('日期', fontsize=12)
        ax2.set_ylabel('持仓只数', fontsize=10)
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(bottom=0)
        
        plt.tight_layout()
        output_file = self.output_dir / '1_账户收益曲线.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"✅ 账户收益曲线: {output_file}")
        plt.close()
    
    def create_stock_kline(self, symbol: str, stock_data_file: str = None):
        """2. 个股K线+买卖点（核心图）"""
        if self.trades.empty:
            return
        
        # 获取该股票的交易记录
        stock_trades = self.trades[self.trades['symbol'] == symbol].copy()
        if stock_trades.empty:
            return
        
        # 确保date是datetime类型
        stock_trades['date'] = pd.to_datetime(stock_trades['date'])
        
        # 从qlib_data读取股票价格数据
        symbol_file = f"{symbol.split('.')[0]}.{symbol.split('.')[1]}"
        csv_file = Path(f'qlib_data/cn_data/instruments/{symbol_file}.csv')
        
        if not csv_file.exists():
            print(f"⏭️  跳过 {symbol} K线图（找不到数据文件: {csv_file}）")
            return
        
        # 读取价格数据
        try:
            df = pd.read_csv(csv_file)
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.set_index('日期')
            # CSV列名已经是 open,close,high,low,volume,amount
            df = df[['open', 'high', 'low', 'close', 'volume']]
            
            # 只取交易日期范围
            if not stock_trades.empty:
                start_date = stock_trades['date'].min() - pd.Timedelta(days=10)
                end_date = stock_trades['date'].max() + pd.Timedelta(days=5)
                df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            if df.empty:
                print(f"⏭️  跳过 {symbol} K线图（日期范围内无数据）")
                return
            
            # 创建图表
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10),
                                           gridspec_kw={'height_ratios': [3, 1]})
            
            # 上图：K线
            # 涨跌颜色
            colors = ['red' if df['close'].iloc[i] >= df['open'].iloc[i] else 'green'
                     for i in range(len(df))]
            
            # 绘制K线（简化版）
            for i in range(len(df)):
                date = df.index[i]
                open_price = df['open'].iloc[i]
                high = df['high'].iloc[i]
                low = df['low'].iloc[i]
                close = df['close'].iloc[i]
                color = colors[i]
                
                # 影线
                ax1.plot([i, i], [low, high], color=color, linewidth=1)
                # 实体
                body_height = abs(close - open_price)
                body_bottom = min(open_price, close)
                rect = plt.Rectangle((i-0.3, body_bottom), 0.6, body_height,
                                    facecolor=color, edgecolor=color, alpha=0.8)
                ax1.add_patch(rect)
            
            # 标注买卖点
            for _, trade in stock_trades.iterrows():
                trade_date = trade['date']
                if trade_date not in df.index:
                    continue
                idx = df.index.get_loc(trade_date)
                price = df.loc[trade_date, 'close']
                
                if trade['action'] == 'BUY':
                    ax1.scatter(idx, price, color='red', s=200, marker='^',
                              zorder=5, label='买入' if idx == 0 else "")
                    ax1.annotate('买', xy=(idx, price), xytext=(idx, price*0.95),
                               fontsize=12, color='red', fontweight='bold',
                               ha='center', bbox=dict(boxstyle='round', 
                                                     facecolor='yellow', alpha=0.7))
                elif trade['action'] == 'SELL':
                    ax1.scatter(idx, price, color='green', s=200, marker='v',
                              zorder=5, label='卖出' if idx == 0 else "")
                    ax1.annotate('卖', xy=(idx, price), xytext=(idx, price*1.05),
                               fontsize=12, color='green', fontweight='bold',
                               ha='center', bbox=dict(boxstyle='round',
                                                     facecolor='lightblue', alpha=0.7))
            
            ax1.set_title(f'{symbol} K线图 + 买卖点', fontsize=16, fontweight='bold')
            ax1.set_ylabel('价格 (¥)', fontsize=12)
            ax1.grid(True, alpha=0.3)
            ax1.set_xticks(range(0, len(df), max(1, len(df)//10)))
            ax1.set_xticklabels([df.index[i].strftime('%m-%d') 
                                for i in range(0, len(df), max(1, len(df)//10))],
                               rotation=45)
            
            # 下图：成交量
            ax2.bar(range(len(df)), df['volume'], color=colors, alpha=0.5)
            ax2.set_ylabel('成交量', fontsize=10)
            ax2.set_xlabel('日期', fontsize=12)
            ax2.grid(True, alpha=0.3)
            ax2.set_xticks(range(0, len(df), max(1, len(df)//10)))
            ax2.set_xticklabels([df.index[i].strftime('%m-%d')
                                for i in range(0, len(df), max(1, len(df)//10))],
                               rotation=45)
            
            plt.tight_layout()
            output_file = self.charts_dir / f'{symbol}_kline.png'
            plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
            print(f"✅ K线图: {output_file}")
            plt.close()
            
        except Exception as e:
            print(f"❌ {symbol} K线图生成失败: {e}")
    
    def create_summary_dashboard(self):
        """3. 一页纸摘要仪表板"""
        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
        
        # 大标题
        fig.suptitle('回测报告总览', fontsize=20, fontweight='bold', y=0.98)
        
        # 左上：关键指标
        ax1 = fig.add_subplot(gs[0, :2])
        ax1.axis('off')
        
        if not self.account_history.empty:
            initial = self.account_history['total_value'].iloc[0]
            final = self.account_history['total_value'].iloc[-1]
            total_return = (final / initial - 1) * 100
            
            # 计算最大回撤
            cummax = self.account_history['total_value'].cummax()
            drawdown = (self.account_history['total_value'] - cummax) / cummax * 100
            max_drawdown = drawdown.min()
            
            buy_count = len(self.trades[self.trades['action'] == 'BUY'])
            sell_count = len(self.trades[self.trades['action'] == 'SELL'])
            
            metrics_text = f"""
┌─────────────────────────────────────────────────┐
│  【核心指标】
│  
│  初始资金:  ¥{initial:,.0f}
│  最终净值:  ¥{final:,.0f}
│  总收益率:  {total_return:+.2f}%
│  最大回撤:  {max_drawdown:.2f}%
│  
│  交易次数:  买入{buy_count}次 / 卖出{sell_count}次
│  胜率:      {(sell_count/buy_count*100 if buy_count>0 else 0):.1f}%
└─────────────────────────────────────────────────┘
            """
        else:
            metrics_text = "无账户数据"
        
        ax1.text(0.05, 0.5, metrics_text, fontsize=14, family='monospace',
                verticalalignment='center',
                bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.3))
        
        # 右上：月度收益
        ax2 = fig.add_subplot(gs[0, 2])
        ax2.set_title('月度收益分布', fontsize=11, fontweight='bold')
        ax2.text(0.5, 0.5, '待实现', ha='center', va='center')
        ax2.axis('off')
        
        # 中间：简化的净值曲线
        ax3 = fig.add_subplot(gs[1, :])
        if not self.account_history.empty:
            ax3.plot(self.account_history['date'], 
                    self.account_history['total_value'],
                    linewidth=2, color='#2E86C1')
            ax3.fill_between(self.account_history['date'],
                           self.account_history['total_value'].iloc[0],
                           self.account_history['total_value'],
                           alpha=0.2, color='green')
            ax3.set_title('账户净值走势', fontsize=12, fontweight='bold')
            ax3.set_ylabel('净值 (¥)', fontsize=10)
            ax3.grid(True, alpha=0.3)
        
        # 下方：交易统计
        ax4 = fig.add_subplot(gs[2, 0])
        ax4.set_title('买入统计', fontsize=10, fontweight='bold')
        if not self.trades.empty:
            buy_trades = self.trades[self.trades['action'] == 'BUY']
            top_stocks = buy_trades['symbol'].value_counts().head(5)
            ax4.barh(range(len(top_stocks)), top_stocks.values, color='green')
            ax4.set_yticks(range(len(top_stocks)))
            ax4.set_yticklabels(top_stocks.index, fontsize=8)
            ax4.invert_yaxis()
        
        ax5 = fig.add_subplot(gs[2, 1])
        ax5.set_title('卖出统计', fontsize=10, fontweight='bold')
        if not self.trades.empty:
            sell_trades = self.trades[self.trades['action'] == 'SELL']
            if not sell_trades.empty:
                reasons = sell_trades['reason'].value_counts().head(5)
                ax5.barh(range(len(reasons)), reasons.values, color='red')
                ax5.set_yticks(range(len(reasons)))
                ax5.set_yticklabels(reasons.index, fontsize=8)
                ax5.invert_yaxis()
            else:
                ax5.text(0.5, 0.5, '无卖出', ha='center', va='center')
                ax5.axis('off')
        
        ax6 = fig.add_subplot(gs[2, 2])
        ax6.set_title('持仓时长', fontsize=10, fontweight='bold')
        ax6.text(0.5, 0.5, '待实现', ha='center', va='center')
        ax6.axis('off')
        
        plt.savefig(self.output_dir / '0_总览仪表板.png',
                   dpi=300, bbox_inches='tight', facecolor='white')
        print(f"✅ 总览仪表板: {self.output_dir / '0_总览仪表板.png'}")
        plt.close()
    
    def save_simple_summary(self):
        """保存简洁的文字摘要"""
        if self.account_history.empty:
            return
        
        initial = self.account_history['total_value'].iloc[0]
        final = self.account_history['total_value'].iloc[-1]
        total_return = (final / initial - 1) * 100
        
        buy_count = len(self.trades[self.trades['action'] == 'BUY'])
        sell_count = len(self.trades[self.trades['action'] == 'SELL'])
        
        summary = f"""
# 回测报告摘要

## 💰 收益情况

- **初始资金**: ¥{initial:,.0f}
- **最终净值**: ¥{final:,.0f}
- **总收益**: ¥{final-initial:,.0f}
- **收益率**: {total_return:+.2f}%

## 📊 交易统计

- **买入次数**: {buy_count}
- **卖出次数**: {sell_count}
- **胜率**: {(sell_count/buy_count*100 if buy_count>0 else 0):.1f}%

## 📁 报告文件

1. `0_总览仪表板.png` - 一页纸总览
2. `1_账户收益曲线.png` - 详细净值曲线

---

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        with open(self.output_dir / 'README.md', 'w', encoding='utf-8') as f:
            f.write(summary)
        
        print(f"✅ 摘要文档: {self.output_dir / 'README.md'}")
    
    def generate_all(self):
        """生成所有报告"""
        print("\n" + "="*60)
        print("📊 生成专业回测报告（重点突出版）")
        print("="*60 + "\n")
        
        print("📈 1. 生成账户收益曲线（最重要）...")
        self.create_account_curve()
        
        print("\n📋 2. 生成总览仪表板...")
        self.create_summary_dashboard()
        
        print("\n📊 3. 生成个股K线+买卖点...")
        if not self.trades.empty:
            traded_symbols = self.trades['symbol'].unique()
            print(f"   共 {len(traded_symbols)} 只股票")
            for symbol in traded_symbols:
                self.create_stock_kline(symbol)
        else:
            print("   ⏭️  无交易记录，跳过")
        
        print("\n💾 4. 保存摘要文档...")
        self.save_simple_summary()
        
        print("\n" + "="*60)
        print(f"✅ 报告生成完成！")
        print(f"📁 查看报告: {self.output_dir}")
        print(f"📁 查看K线图: {self.charts_dir}")
        print("="*60 + "\n")
        print("🔑 重点文件:")
        print("  1. 1_账户收益曲线.png  - 先看这个！")
        print("  2. 0_总览仪表板.png   - 完整总览")
        print("  3. charts/股票代码_kline.png - 个股K线+买卖点")
        print("  4. README.md          - 文字摘要")

def main():
    import sys
    
    log_file = 'logs/backtest_v7_final.log'
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    
    generator = ProfessionalBacktestReport(log_file)
    generator.generate_all()

if __name__ == "__main__":
    main()
