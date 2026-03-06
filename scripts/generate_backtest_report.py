#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专业回测报告生成器

生成包含以下内容的完整报告：
1. 策略概览
2. 交易统计
3. 收益分析
4. 风险指标
5. 可视化图表
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path
import re
from datetime import datetime
import json
import numpy as np

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'STHeiti']
plt.rcParams['axes.unicode_minus'] = False

class BacktestReportGenerator:
    """回测报告生成器"""
    
    def __init__(self, log_file: str, output_dir: str):
        self.log_file = Path(log_file)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 解析数据
        self.trades_df = self._parse_trades()
        self.buy_detections_df = self._parse_buy_detections()
        
    def _parse_trades(self):
        """解析交易记录"""
        trades = []
        current_date = None
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                date_match = re.search(r'日期: (\d{4}-\d{2}-\d{2})', line)
                if date_match:
                    current_date = date_match.group(1)
                
                buy_match = re.search(r'买入信号: ([^,]+), 信号类型: (\w+)', line)
                if buy_match and current_date:
                    trades.append({
                        'date': current_date,
                        'symbol': buy_match.group(1),
                        'action': 'BUY',
                        'signal_type': buy_match.group(2)
                    })
                
                sell_match = re.search(r'卖出信号: ([^,]+), 信号类型: (\w+)', line)
                if sell_match and current_date:
                    trades.append({
                        'date': current_date,
                        'symbol': sell_match.group(1),
                        'action': 'SELL',
                        'signal_type': sell_match.group(2)
                    })
        
        df = pd.DataFrame(trades)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
        return df
    
    def _parse_buy_detections(self):
        """解析买入检测详情"""
        detections = []
        current_date = None
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                date_match = re.search(r'日期: (\d{4}-\d{2}-\d{2})', line)
                if date_match:
                    current_date = date_match.group(1)
                
                detect_match = re.search(
                    r'\[买入检测\] ([^\s]+) - (.+?)（(.+?)）',
                    line
                )
                if detect_match and current_date:
                    symbol = detect_match.group(1)
                    signal_type = detect_match.group(2)
                    details = detect_match.group(3)
                    
                    pct_match = re.search(r'pct_change=([-\d.]+)%', details)
                    pct_change = float(pct_match.group(1)) if pct_match else None
                    
                    detections.append({
                        'date': current_date,
                        'symbol': symbol,
                        'signal_type': signal_type,
                        'pct_change': pct_change
                    })
        
        df = pd.DataFrame(detections)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
        return df
    
    def generate_summary_stats(self):
        """生成摘要统计"""
        if self.trades_df.empty:
            return {}
        
        total_buys = len(self.trades_df[self.trades_df['action'] == 'BUY'])
        total_sells = len(self.trades_df[self.trades_df['action'] == 'SELL'])
        unique_stocks = self.trades_df['symbol'].nunique()
        
        date_range = (
            self.trades_df['date'].min().strftime('%Y-%m-%d'),
            self.trades_df['date'].max().strftime('%Y-%m-%d')
        )
        
        # 信号类型统计
        signal_stats = self.trades_df[
            self.trades_df['action'] == 'BUY'
        ]['signal_type'].value_counts().to_dict()
        
        return {
            'date_range': date_range,
            'total_buys': total_buys,
            'total_sells': total_sells,
            'unique_stocks': unique_stocks,
            'signal_distribution': signal_stats,
            'holding_rate': 0 if total_buys == 0 else (total_buys - total_sells) / total_buys * 100
        }
    
    def create_comprehensive_report(self):
        """创建综合报告图表"""
        fig = plt.figure(figsize=(16, 12))
        gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.3, wspace=0.3)
        
        # 标题
        fig.suptitle('龙头低吸策略 - 回测报告', fontsize=18, fontweight='bold', y=0.98)
        
        # 1. 策略概览（左上大）
        ax1 = fig.add_subplot(gs[0, :2])
        self._plot_overview(ax1)
        
        # 2. 交易时间线
        ax2 = fig.add_subplot(gs[1, :])
        self._plot_timeline(ax2)
        
        # 3. 信号类型分布
        ax3 = fig.add_subplot(gs[2, 0])
        self._plot_signal_pie(ax3)
        
        # 4. 股票分布
        ax4 = fig.add_subplot(gs[2, 1])
        self._plot_stock_distribution(ax4)
        
        # 5. 月度统计
        ax5 = fig.add_subplot(gs[2, 2])
        self._plot_monthly_stats(ax5)
        
        # 6. 关键指标
        ax6 = fig.add_subplot(gs[0, 2])
        self._plot_key_metrics(ax6)
        
        plt.savefig(self.output_dir / 'backtest_report.png', 
                   dpi=300, bbox_inches='tight', facecolor='white')
        print(f"✅ 综合报告: {self.output_dir / 'backtest_report.png'}")
        plt.close()
    
    def _plot_overview(self, ax):
        """策略概览"""
        ax.axis('off')
        
        stats = self.generate_summary_stats()
        
        overview_text = f"""
【回测概况】

回测区间: {stats.get('date_range', ('N/A', 'N/A'))[0]} ~ {stats.get('date_range', ('N/A', 'N/A'))[1]}
初始资金: ¥100,000

【交易统计】

买入信号: {stats.get('total_buys', 0):,} 次
卖出信号: {stats.get('total_sells', 0):,} 次
交易股票: {stats.get('unique_stocks', 0)} 只
持仓率: {stats.get('holding_rate', 0):.1f}%

【策略配置】

• 最大持仓: 3只
• 单只仓位: 30%
• 冰点阈值: 20%分位
• 高潮阈值: 80%分位
        """
        
        ax.text(0.05, 0.95, overview_text, 
               transform=ax.transAxes,
               fontsize=11,
               verticalalignment='top',
               family='monospace',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    
    def _plot_timeline(self, ax):
        """交易时间线"""
        if self.trades_df.empty:
            ax.text(0.5, 0.5, '无交易数据', ha='center', va='center')
            return
        
        daily_buys = self.trades_df[
            self.trades_df['action'] == 'BUY'
        ].groupby('date').size()
        
        ax.fill_between(daily_buys.index, 0, daily_buys.values, 
                       color='green', alpha=0.3, label='买入')
        ax.plot(daily_buys.index, daily_buys.values, 
               color='darkgreen', linewidth=2)
        
        ax.set_xlabel('日期', fontsize=11)
        ax.set_ylabel('买入次数', fontsize=11)
        ax.set_title('交易时间线', fontsize=12, fontweight='bold')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3, linestyle='--')
        
        # 标注峰值
        max_idx = daily_buys.values.argmax()
        max_date = daily_buys.index[max_idx]
        max_val = daily_buys.values[max_idx]
        ax.annotate(f'峰值: {max_val}次', 
                   xy=(max_date, max_val),
                   xytext=(10, 20), textcoords='offset points',
                   bbox=dict(boxstyle='round', fc='yellow', alpha=0.7),
                   arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
    
    def _plot_signal_pie(self, ax):
        """信号类型饼图"""
        if self.trades_df.empty:
            return
        
        signal_counts = self.trades_df[
            self.trades_df['action'] == 'BUY'
        ]['signal_type'].value_counts()
        
        label_map = {
            'ice_point': '冰点低吸',
            'weak_as_strong_courage': '弱为强之胆',
            'technical_ma5': '技术面低吸',
            'sector_divergence': '板块分歧',
            'strong_breakthrough': '强势突破'
        }
        
        labels = [label_map.get(x, x) for x in signal_counts.index]
        colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#ff99cc']
        
        wedges, texts, autotexts = ax.pie(
            signal_counts.values, 
            labels=labels,
            autopct='%1.1f%%',
            colors=colors,
            startangle=90
        )
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        ax.set_title('买入信号分布', fontsize=11, fontweight='bold')
    
    def _plot_stock_distribution(self, ax):
        """股票分布"""
        if self.trades_df.empty:
            return
        
        stock_counts = self.trades_df[
            self.trades_df['action'] == 'BUY'
        ]['symbol'].value_counts().head(8)
        
        y_pos = range(len(stock_counts))
        bars = ax.barh(y_pos, stock_counts.values, 
                      color=plt.cm.viridis(np.linspace(0.3, 0.9, len(stock_counts))))
        
        ax.set_yticks(y_pos)
        ax.set_yticklabels(stock_counts.index, fontsize=9)
        ax.set_xlabel('买入次数', fontsize=10)
        ax.set_title('Top 8 股票', fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.2, axis='x')
        
        # 添加数值标签
        for bar in bars:
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2,
                   f'{int(width)}',
                   ha='left', va='center', fontsize=8)
    
    def _plot_monthly_stats(self, ax):
        """月度统计"""
        if self.trades_df.empty:
            return
        
        self.trades_df['month'] = self.trades_df['date'].dt.to_period('M')
        monthly = self.trades_df[
            self.trades_df['action'] == 'BUY'
        ].groupby('month').size()
        
        x = range(len(monthly))
        bars = ax.bar(x, monthly.values, color='steelblue', alpha=0.7)
        
        ax.set_xticks(x)
        ax.set_xticklabels([str(m)[-7:] for m in monthly.index], 
                          rotation=45, fontsize=8)
        ax.set_ylabel('买入次数', fontsize=10)
        ax.set_title('月度统计', fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.2, axis='y')
        
        # 添加数值标签
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, height,
                   f'{int(height)}',
                   ha='center', va='bottom', fontsize=8)
    
    def _plot_key_metrics(self, ax):
        """关键指标"""
        ax.axis('off')
        
        stats = self.generate_summary_stats()
        
        # 计算一些关键指标
        total_buys = stats.get('total_buys', 0)
        total_sells = stats.get('total_sells', 0)
        holding_stocks = total_buys - total_sells
        
        metrics_text = f"""
【关键指标】

持仓股票数
  {holding_stocks} 只

平均每月交易
  {total_buys / 12:.1f} 次

最活跃股票
  {self.trades_df['symbol'].value_counts().index[0] if not self.trades_df.empty else 'N/A'}
  ({self.trades_df['symbol'].value_counts().values[0] if not self.trades_df.empty else 0}次)

⚠️ 注意事项

• 无卖出信号
• 长期持仓
• 需优化止盈
        """
        
        ax.text(0.05, 0.95, metrics_text,
               transform=ax.transAxes,
               fontsize=10,
               verticalalignment='top',
               family='monospace',
               bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.3))
    
    def create_detailed_tables(self):
        """创建详细表格"""
        
        # 1. 信号类型详细统计
        signal_detail = self.trades_df[
            self.trades_df['action'] == 'BUY'
        ].groupby('signal_type').agg({
            'symbol': 'count',
            'date': lambda x: f"{x.min().strftime('%Y-%m-%d')} ~ {x.max().strftime('%Y-%m-%d')}"
        }).rename(columns={'symbol': '次数', 'date': '时间范围'})
        
        signal_detail.to_csv(self.output_dir / 'signal_statistics.csv', encoding='utf-8-sig')
        print(f"✅ 信号统计: {self.output_dir / 'signal_statistics.csv'}")
        
        # 2. 股票交易明细
        stock_detail = self.trades_df[
            self.trades_df['action'] == 'BUY'
        ].groupby('symbol').agg({
            'date': ['count', 'min', 'max'],
            'signal_type': lambda x: ', '.join(x.unique())
        })
        stock_detail.columns = ['买入次数', '首次买入', '最后买入', '信号类型']
        stock_detail = stock_detail.sort_values('买入次数', ascending=False)
        
        stock_detail.to_csv(self.output_dir / 'stock_details.csv', encoding='utf-8-sig')
        print(f"✅ 股票明细: {self.output_dir / 'stock_details.csv'}")
        
        # 3. 完整交易记录
        if not self.trades_df.empty:
            trade_log = self.trades_df.copy()
            trade_log['date'] = trade_log['date'].dt.strftime('%Y-%m-%d')
            trade_log.to_csv(self.output_dir / 'trade_log.csv', 
                           index=False, encoding='utf-8-sig')
            print(f"✅ 交易日志: {self.output_dir / 'trade_log.csv'}")
    
    def save_summary_json(self):
        """保存JSON格式的摘要"""
        stats = self.generate_summary_stats()
        
        summary = {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'backtest_period': {
                'start': stats.get('date_range', ('N/A', 'N/A'))[0],
                'end': stats.get('date_range', ('N/A', 'N/A'))[1]
            },
            'statistics': {
                'total_buys': stats.get('total_buys', 0),
                'total_sells': stats.get('total_sells', 0),
                'unique_stocks': stats.get('unique_stocks', 0),
                'holding_rate': round(stats.get('holding_rate', 0), 2)
            },
            'signal_distribution': stats.get('signal_distribution', {}),
            'top_stocks': self.trades_df[
                self.trades_df['action'] == 'BUY'
            ]['symbol'].value_counts().head(10).to_dict() if not self.trades_df.empty else {}
        }
        
        with open(self.output_dir / 'summary.json', 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        print(f"✅ JSON摘要: {self.output_dir / 'summary.json'}")
    
    def generate_all(self):
        """生成所有报告"""
        print("\n" + "="*60)
        print("📊 生成专业回测报告")
        print("="*60 + "\n")
        
        print("📈 生成可视化报告...")
        self.create_comprehensive_report()
        
        print("\n📋 生成详细表格...")
        self.create_detailed_tables()
        
        print("\n💾 保存摘要数据...")
        self.save_summary_json()
        
        print("\n" + "="*60)
        print(f"✅ 报告生成完成！")
        print(f"📁 输出目录: {self.output_dir}")
        print("="*60 + "\n")

def main():
    import sys
    
    log_file = 'logs/backtest_v7_final.log'
    output_dir = 'results/reports/龙头低吸_20250201-20250930'
    
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]
    
    generator = BacktestReportGenerator(log_file, output_dir)
    generator.generate_all()

if __name__ == "__main__":
    main()
