#!/usr/bin/env python3
"""
数据完整性检查工具

检查现有数据时间范围，识别缺失数据
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, List, Set
import pandas as pd
from loguru import logger

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class DataChecker:
    """数据完整性检查器"""
    
    def __init__(self, qlib_data_path: str = "./qlib_data/cn_data"):
        self.qlib_data_path = Path(qlib_data_path)
        self.csv_dir = self.qlib_data_path / "instruments"
        self.calendar_file = self.qlib_data_path / "calendars" / "day.txt"
    
    def get_available_date_range(self) -> Tuple[str, str, int]:
        """
        获取现有数据的时间范围
        
        Returns:
            (开始日期, 结束日期, 总天数) 如 ('2020-01-02', '2024-12-31', 1234)
            如果没有数据返回 ('', '', 0)
        """
        if not self.calendar_file.exists():
            return ('', '', 0)
        
        try:
            dates = self.calendar_file.read_text().strip().split('\n')
            dates = [d for d in dates if d and d.strip()]
            
            if not dates:
                return ('', '', 0)
            
            return (dates[0], dates[-1], len(dates))
            
        except Exception as e:
            logger.error(f"读取日历失败: {e}")
            return ('', '', 0)
    
    def check_date_coverage(self, start_date: str, end_date: str) -> dict:
        """
        检查指定日期范围的数据覆盖情况
        
        Args:
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
        
        Returns:
            {
                'has_data': bool,  # 是否有数据
                'full_coverage': bool,  # 是否完全覆盖
                'existing_start': str,  # 现有数据开始
                'existing_end': str,  # 现有数据结束
                'missing_ranges': [(start, end), ...],  # 缺失的时间段
                'need_download': bool  # 是否需要下载
            }
        """
        existing_start, existing_end, count = self.get_available_date_range()
        
        # 没有任何数据
        if not existing_start:
            return {
                'has_data': False,
                'full_coverage': False,
                'existing_start': '',
                'existing_end': '',
                'missing_ranges': [(start_date, end_date)],
                'need_download': True
            }
        
        # 有数据，检查覆盖情况
        req_start = datetime.strptime(start_date, '%Y-%m-%d')
        req_end = datetime.strptime(end_date, '%Y-%m-%d')
        data_start = datetime.strptime(existing_start, '%Y-%m-%d')
        data_end = datetime.strptime(existing_end, '%Y-%m-%d')
        
        # 完全覆盖
        if data_start <= req_start and data_end >= req_end:
            return {
                'has_data': True,
                'full_coverage': True,
                'existing_start': existing_start,
                'existing_end': existing_end,
                'missing_ranges': [],
                'need_download': False
            }
        
        # 部分覆盖或不覆盖，计算缺失范围
        missing_ranges = []
        
        # 前面缺失
        if req_start < data_start:
            missing_end = min(data_start - timedelta(days=1), req_end)
            missing_ranges.append((
                req_start.strftime('%Y-%m-%d'),
                missing_end.strftime('%Y-%m-%d')
            ))
        
        # 后面缺失
        if req_end > data_end:
            missing_start = max(data_end + timedelta(days=1), req_start)
            missing_ranges.append((
                missing_start.strftime('%Y-%m-%d'),
                req_end.strftime('%Y-%m-%d')
            ))
        
        return {
            'has_data': True,
            'full_coverage': False,
            'existing_start': existing_start,
            'existing_end': existing_end,
            'missing_ranges': missing_ranges,
            'need_download': True
        }
    
    def get_stock_count(self) -> int:
        """获取已下载的股票数量"""
        if not self.csv_dir.exists():
            return 0
        
        csv_files = list(self.csv_dir.glob("[0-9]*.csv"))
        return len(csv_files)
    
    def check_emotion_data(self, start_date: str, end_date: str) -> dict:
        """
        检查情绪数据完整性
        
        Returns:
            {
                'has_data': bool,
                'total_days': int,
                'existing_days': int,
                'missing_days': int,
                'coverage_rate': float  # 0.0-1.0
            }
        """
        emotion_file = self.qlib_data_path.parent / "emotion_data.csv"
        
        if not emotion_file.exists():
            return {
                'has_data': False,
                'total_days': 0,
                'existing_days': 0,
                'missing_days': 0,
                'coverage_rate': 0.0
            }
        
        try:
            df = pd.read_csv(emotion_file)
            
            # 计算请求的日期范围内有多少天
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            total_days = (end - start).days + 1
            
            # 统计该范围内有多少条记录
            df['date'] = pd.to_datetime(df['date'])
            mask = (df['date'] >= start) & (df['date'] <= end)
            existing_days = mask.sum()
            
            return {
                'has_data': True,
                'total_days': total_days,
                'existing_days': existing_days,
                'missing_days': total_days - existing_days,
                'coverage_rate': existing_days / total_days if total_days > 0 else 0.0
            }
            
        except Exception as e:
            logger.error(f"检查情绪数据失败: {e}")
            return {
                'has_data': False,
                'total_days': 0,
                'existing_days': 0,
                'missing_days': 0,
                'coverage_rate': 0.0
            }


def main():
    """命令行接口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='检查数据完整性')
    parser.add_argument('--start', type=str, required=True, help='开始日期 YYYY-MM-DD')
    parser.add_argument('--end', type=str, required=True, help='结束日期 YYYY-MM-DD')
    parser.add_argument('--json', action='store_true', help='输出JSON格式')
    args = parser.parse_args()
    
    checker = DataChecker()
    
    # 检查价格数据
    price_result = checker.check_date_coverage(args.start, args.end)
    
    # 检查情绪数据
    emotion_result = checker.check_emotion_data(args.start, args.end)
    
    if args.json:
        import json
        print(json.dumps({
            'price_data': price_result,
            'emotion_data': emotion_result,
            'stock_count': checker.get_stock_count()
        }, ensure_ascii=False, indent=2))
    else:
        print("\n" + "="*70)
        print("  数据完整性检查")
        print("="*70)
        print(f"\n请求时间范围: {args.start} ~ {args.end}")
        print(f"\n【价格数据】")
        if price_result['has_data']:
            print(f"  现有数据: {price_result['existing_start']} ~ {price_result['existing_end']}")
            print(f"  股票数量: {checker.get_stock_count()} 只")
            if price_result['full_coverage']:
                print(f"  状态: ✓ 完全覆盖")
            else:
                print(f"  状态: ✗ 需要补充")
                for start, end in price_result['missing_ranges']:
                    print(f"    缺失: {start} ~ {end}")
        else:
            print(f"  状态: ✗ 无数据")
        
        print(f"\n【情绪数据】")
        if emotion_result['has_data']:
            print(f"  已有天数: {emotion_result['existing_days']} / {emotion_result['total_days']}")
            print(f"  覆盖率: {emotion_result['coverage_rate']*100:.1f}%")
            if emotion_result['missing_days'] > 0:
                print(f"  状态: ✗ 缺少 {emotion_result['missing_days']} 天")
            else:
                print(f"  状态: ✓ 完全覆盖")
        else:
            print(f"  状态: ✗ 无数据")
        
        print("")


if __name__ == "__main__":
    main()
