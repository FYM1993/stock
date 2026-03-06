"""
数据格式转换模块

负责将 AKShare 下载的 CSV 数据转换为 Qlib 二进制格式
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, List
from loguru import logger


class QlibDataConverter:
    """Qlib 数据格式转换器"""
    
    def __init__(self, qlib_data_path: str = "./qlib_data/cn_data"):
        """
        初始化转换器
        
        Args:
            qlib_data_path: Qlib 数据目录路径
        """
        self.qlib_data_path = Path(qlib_data_path)
        self.csv_dir = self.qlib_data_path / "instruments"
        self.bin_dir = self.qlib_data_path / "features"
        
        # 确保目录存在
        self.csv_dir.mkdir(parents=True, exist_ok=True)
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载交易日历
        self._load_calendar()
    
    def _load_calendar(self):
        """加载交易日历"""
        calendar_file = self.qlib_data_path / "calendars" / "day.txt"
        
        if calendar_file.exists():
            calendar_dates = calendar_file.read_text().strip().split('\n')
            self.calendar = pd.DatetimeIndex(pd.to_datetime(calendar_dates))
            logger.info(f"加载交易日历: {len(self.calendar)} 个交易日 ({self.calendar[0].date()} ~ {self.calendar[-1].date()})")
        else:
            self.calendar = None
            logger.warning("交易日历不存在，将使用股票自身的日期")
    
    def convert_single_stock(self, symbol: str, append: bool = True):
        """
        转换单只股票/指数的数据（对齐日历）
        
        Args:
            symbol: 股票代码，如 '000001.SZ' 或 'sh000300'
            append: 是否追加到已有数据（True）还是覆盖（False）
        """
        csv_file = self.csv_dir / f"{symbol}.csv"
        
        if not csv_file.exists():
            logger.warning(f"CSV文件不存在: {csv_file}")
            return False
        
        try:
            # 读取CSV
            df = pd.read_csv(csv_file)
            
            if df.empty:
                logger.warning(f"{symbol}: CSV数据为空")
                return False
            
            # 处理日期列（支持中文和英文列名）
            date_col = None
            if 'date' in df.columns:
                date_col = 'date'
            elif '日期' in df.columns:
                date_col = '日期'
            
            if date_col:
                df['date'] = pd.to_datetime(df[date_col])
                df = df.set_index('date').sort_index()
            else:
                logger.warning(f"{symbol}: 找不到日期列")
                return False
            
            # 如果有交易日历，对齐到日历
            if self.calendar is not None:
                # 创建一个与日历对齐的空 DataFrame
                aligned_df = pd.DataFrame(index=self.calendar)
                
                # 将股票数据合并到对齐的 DataFrame
                for col in df.columns:
                    aligned_df[col] = df[col]
                
                df = aligned_df
            
            # 创建目标目录
            target_dir = self.bin_dir / symbol
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # 转换并保存各字段
            fields = ['open', 'high', 'low', 'close', 'volume', 'change', 'factor']
            
            for field in fields:
                if field not in df.columns:
                    continue
                
                bin_file = target_dir / f"{field}.day.bin"
                
                # 获取数据（保留 NaN）
                data = df[field].values.astype(np.float32)
                
                if append and bin_file.exists():
                    # 追加模式
                    with open(bin_file, 'ab') as f:
                        f.write(data.tobytes())
                else:
                    # 覆盖模式
                    with open(bin_file, 'wb') as f:
                        f.write(data.tobytes())
            
            # 统计有效数据数量
            valid_count = df['close'].notna().sum() if 'close' in df.columns else len(df)
            logger.info(f"✓ {symbol}: 转换完成 ({valid_count} 条有效记录 / {len(df)} 总长度)")
            return True
            
        except Exception as e:
            logger.error(f"转换 {symbol} 失败: {e}")
            return False
    
    def convert_batch(self, symbols: Optional[List[str]] = None, append: bool = True):
        """
        批量转换多只股票
        
        Args:
            symbols: 股票代码列表，None表示转换所有CSV文件
            append: 是否追加模式
        """
        if symbols is None:
            # 获取所有CSV文件
            csv_files = list(self.csv_dir.glob("*.csv"))
            symbols = [f.stem for f in csv_files]
        
        if not symbols:
            logger.warning("没有找到需要转换的数据")
            return
        
        logger.info(f"开始批量转换 {len(symbols)} 个文件...")
        
        success = 0
        failed = 0
        
        for idx, symbol in enumerate(symbols, 1):
            if self.convert_single_stock(symbol, append=append):
                success += 1
            else:
                failed += 1
            
            if idx % 100 == 0:
                logger.info(f"  进度: {idx}/{len(symbols)}, 成功: {success}, 失败: {failed}")
        
        logger.info(f"批量转换完成: 成功 {success}, 失败 {failed}")
    
    def clean_csv_files(self):
        """清理已转换的CSV文件（节省空间）"""
        csv_files = list(self.csv_dir.glob("*.csv"))
        
        if not csv_files:
            logger.info("没有CSV文件需要清理")
            return
        
        logger.info(f"清理 {len(csv_files)} 个CSV文件...")
        
        for csv_file in csv_files:
            csv_file.unlink()
        
        logger.info("✓ CSV文件清理完成")
    
    def verify_data(self, symbol: str) -> bool:
        """
        验证数据是否可用
        
        Args:
            symbol: 股票代码
            
        Returns:
            数据是否完整
        """
        target_dir = self.bin_dir / symbol
        
        if not target_dir.exists():
            return False
        
        # 检查必需字段
        required_fields = ['open', 'high', 'low', 'close', 'volume']
        
        for field in required_fields:
            bin_file = target_dir / f"{field}.day.bin"
            if not bin_file.exists():
                return False
        
        return True
    
    def update_calendar(self, calendar_dates: List[str]):
        """
        更新交易日历
        
        Args:
            calendar_dates: 日期列表，格式如 ['2024-01-02', '2024-01-03', ...]
        """
        calendar_file = self.qlib_data_path / "calendars" / "day.txt"
        calendar_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # 读取现有日历
            if calendar_file.exists():
                existing_dates = set(calendar_file.read_text().strip().split('\n'))
            else:
                existing_dates = set()
            
            # 合并新日期
            all_dates = existing_dates.union(set(calendar_dates))
            all_dates = sorted([d for d in all_dates if d])  # 去重+排序
            
            # 写入
            calendar_file.write_text('\n'.join(all_dates) + '\n')
            
            logger.info(f"✓ 交易日历已更新: {len(all_dates)} 个交易日")
            
        except Exception as e:
            logger.error(f"更新交易日历失败: {e}")


if __name__ == "__main__":
    # 测试转换
    converter = QlibDataConverter()
    
    # 转换所有CSV
    converter.convert_batch(append=False)
    
    # 验证
    if converter.verify_data('sh000300'):
        print("✓ 数据验证通过")
    else:
        print("✗ 数据验证失败")
