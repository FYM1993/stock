"""
adata 数据提供器 — 为 Qlib 提供 A股数据

基于 https://github.com/1nchaos/adata
比 akshare 更稳定，多数据源融合，动态代理
"""

import adata
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
from loguru import logger
import time


class ADataProvider:
    """adata 数据提供器"""

    def __init__(self, qlib_data_path: str = "./qlib_data/cn_data"):
        self.qlib_data_path = Path(qlib_data_path)
        self.qlib_data_path.mkdir(parents=True, exist_ok=True)

    def get_stock_list(self) -> pd.DataFrame:
        """
        获取全部A股列表

        Returns:
            DataFrame[stock_code, short_name, exchange, list_date]
        """
        df = adata.stock.info.all_code()
        logger.info(f"获取到 {len(df)} 只股票")
        return df

    def save_stock_info(self, stock_df: pd.DataFrame = None):
        """
        保存股票信息列表（含名称、上市日期等），用于 ST/科创板/次新股过滤。
        保存为 CSV: qlib_data/cn_data/stock_info.csv
        """
        if stock_df is None:
            stock_df = self.get_stock_list()

        info = stock_df.copy()
        info["symbol"] = info.apply(
            lambda r: f"{r['stock_code']}.{r['exchange']}", axis=1
        )

        # 标记 ST
        info["is_st"] = info["short_name"].str.contains(
            r"ST|退市", case=False, na=False
        )
        # 标记科创板 (688xxx)
        info["is_kcb"] = info["stock_code"].str.startswith("688")
        # 标记北交所 (exchange=BJ)
        info["is_bj"] = info["exchange"] == "BJ"

        out_path = self.qlib_data_path / "stock_info.csv"
        info.to_csv(out_path, index=False, encoding="utf-8-sig")

        n_st = info["is_st"].sum()
        n_kcb = info["is_kcb"].sum()
        n_bj = info["is_bj"].sum()
        logger.info(
            f"✓ 保存股票信息: {len(info)} 只 → {out_path} "
            f"(ST={n_st}, 科创板={n_kcb}, 北交所={n_bj})"
        )
        return info

    def get_stock_daily(
        self,
        stock_code: str,
        start_date: str = "2020-01-01",
        end_date: Optional[str] = None,
        adjust_type: int = 1,
    ) -> Optional[pd.DataFrame]:
        """
        获取个股日线行情（前复权）

        Args:
            stock_code: 6位纯数字代码，如 '000001'
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期，None表示至今
            adjust_type: 1=前复权 2=后复权 0=不复权

        Returns:
            DataFrame[date, open, close, high, low, volume, amount, vwap]
        """
        try:
            df = adata.stock.market.get_market(
                stock_code=stock_code,
                start_date=start_date,
                end_date=end_date,
                k_type=1,
                adjust_type=adjust_type,
            )
            if df is None or df.empty:
                return None

            volume = df["volume"].astype(float)
            amount = df["amount"].astype(float) if "amount" in df.columns else (volume * df["close"].astype(float))
            vwap = np.where(volume > 0, amount / volume, df["close"].astype(float))

            result = pd.DataFrame({
                "date": pd.to_datetime(df["trade_date"]),
                "open": df["open"].astype(float),
                "close": df["close"].astype(float),
                "high": df["high"].astype(float),
                "low": df["low"].astype(float),
                "volume": volume,
                "amount": amount,
                "vwap": vwap,
            })
            result = result.set_index("date").sort_index()
            return result

        except Exception as e:
            logger.debug(f"{stock_code}: {e}")
            return None

    def get_index_daily(
        self,
        index_code: str = "000300",
        start_date: str = "2020-01-01",
    ) -> Optional[pd.DataFrame]:
        """
        获取指数日线行情

        Args:
            index_code: 指数代码，如 '000300'(沪深300), '000001'(上证指数)
            start_date: 开始日期

        Returns:
            DataFrame[date, open, close, high, low, volume, amount, vwap]
        """
        try:
            df = adata.stock.market.get_market_index(
                index_code=index_code,
                start_date=start_date,
            )
            if df is None or df.empty:
                return None

            volume = df["volume"].astype(float)
            amount = df["amount"].astype(float) if "amount" in df.columns else (volume * df["close"].astype(float))
            vwap = np.where(volume > 0, amount / volume, df["close"].astype(float))

            result = pd.DataFrame({
                "date": pd.to_datetime(df["trade_date"]),
                "open": df["open"].astype(float),
                "close": df["close"].astype(float),
                "high": df["high"].astype(float),
                "low": df["low"].astype(float),
                "volume": volume,
                "amount": amount,
                "vwap": vwap,
            })
            result = result.set_index("date").sort_index()
            return result

        except Exception as e:
            logger.error(f"指数 {index_code}: {e}")
            return None

    def download_all(
        self,
        start_date: str = "2020-01-01",
        end_date: Optional[str] = None,
        delay: float = 0.3,
        max_stocks: Optional[int] = None,
    ):
        """
        下载全部A股日线数据，保存为Qlib格式CSV

        Args:
            start_date: 开始日期
            end_date: 结束日期
            delay: 请求间隔(秒)
            max_stocks: 最大下载数(None=全部)
        """
        stock_df = self.get_stock_list()

        codes = stock_df["stock_code"].tolist()
        exchanges = dict(zip(stock_df["stock_code"], stock_df["exchange"]))

        if max_stocks:
            codes = codes[:max_stocks]

        total = len(codes)
        success = 0
        failed = 0

        logger.info(f"开始下载 {total} 只股票, {start_date} ~ {end_date or '至今'}")

        csv_dir = self.qlib_data_path / "instruments"
        csv_dir.mkdir(parents=True, exist_ok=True)

        for idx, code in enumerate(codes, 1):
            try:
                df = self.get_stock_daily(code, start_date, end_date)
                if df is not None and len(df) > 0:
                    ex = exchanges.get(code, "SZ")
                    symbol = f"{code}.{ex}"
                    csv_path = csv_dir / f"{symbol}.csv"
                    df.to_csv(csv_path)
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.debug(f"{code}: {e}")

            if idx % 100 == 0:
                logger.info(f"  进度 {idx}/{total} | 成功 {success} | 失败 {failed}")

            time.sleep(delay)

        logger.info(f"下载完成: 成功 {success}/{total}, 失败 {failed}")

    def download_index(
        self,
        index_code: str = "000300",
        start_date: str = "2020-01-01",
    ):
        """下载指数数据并保存"""
        logger.info(f"下载指数 {index_code}...")
        df = self.get_index_daily(index_code, start_date)
        if df is not None:
            symbol = f"{index_code}.SH"
            csv_dir = self.qlib_data_path / "instruments"
            csv_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(csv_dir / f"{symbol}.csv")
            logger.info(f"  {symbol}: {len(df)} 条记录")
        else:
            logger.error(f"  {index_code}: 下载失败")


if __name__ == "__main__":
    p = ADataProvider()

    print("=== 股票列表 ===")
    stocks = p.get_stock_list()
    print(f"  数量: {len(stocks)}")
    print(stocks.head(3))

    print("\n=== 000001 日线 ===")
    df = p.get_stock_daily("000001", "2025-05-01", "2025-05-10")
    print(df)

    print("\n=== 沪深300指数 ===")
    idx = p.get_index_daily("000300", "2025-05-01")
    print(idx.head())
