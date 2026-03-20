#!/usr/bin/env python3
"""
增量更新 qlib 数据：从 adata 拉最新行情，直接 append 到 qlib bin
前提：已有历史数据（从 investment_data release 下载的 tar 包解压）
每天: python update_daily_data.py
"""

import time
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# ============ 配置 ============
DEFAULT_QLIB_DIR = Path.home() / "GolandProjects/stock/qlib_data/cn_data"

INDEX_MAP = {
    "csi300":  ("csi300.txt",  "000300"),
    "csi500":  ("csi500.txt",  "000905"),
    "csi800":  ("csi800.txt",  "000906"),
    "csi1000": ("csi1000.txt", "000852"),
    "csiall":  ("csiall.txt",  "000985"),
}

FEATURE_MAP = [
    ("open",   "price.open",   np.float32),
    ("close",  "price.close",  np.float32),
    ("high",   "price.high",   np.float32),
    ("low",    "price.low",    np.float32),
    ("volume", "volume",       np.float32),
]


# ================================================================
#  工具函数
# ================================================================
def load_calendar(qlib_dir):
    cal_file = Path(qlib_dir) / "calendars" / "day.txt"
    if not cal_file.exists():
        raise FileNotFoundError(f"找不到 calendar: {cal_file}，请先解压历史数据")
    dates = [line.strip() for line in cal_file.read_text().strip().split("\n") if line.strip()]
    return dates, {d: i for i, d in enumerate(dates)}


def save_calendar(qlib_dir, dates):
    cal_file = Path(qlib_dir) / "calendars" / "day.txt"
    with open(cal_file, "w") as f:
        for d in dates:
            f.write(d + "\n")


def load_bin(qlib_dir, symbol, bin_name, dtype=np.float32):
    bin_path = Path(qlib_dir) / "features" / symbol / f"{bin_name}.bin"
    if not bin_path.exists():
        return None
    return np.fromfile(bin_path, dtype=dtype)


def save_bin(qlib_dir, symbol, bin_name, arr):
    bin_path = Path(qlib_dir) / "features" / symbol / f"{bin_name}.bin"
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    arr.tofile(bin_path)


def get_symbol_stocks(index_code="000852"):
    import adata
    df = adata.stock.info.index_constituent(index_code=index_code)
    stocks = []
    for _, row in df.iterrows():
        code = str(row.iloc[0])
        if len(code) == 6:
            prefix = "SH" if code.startswith("6") else "SZ"
            stocks.append(f"{prefix}{code}")
    return stocks


def get_date_range(qlib_dir, symbol):
    dates, _ = load_calendar(qlib_dir)
    if not dates:
        return None, None
    bin_path = Path(qlib_dir) / "features" / symbol / "price.close.bin"
    if not bin_path.exists():
        return None, None
    arr = np.fromfile(bin_path, dtype=np.float32)
    if len(arr) == 0:
        return None, None
    valid = ~np.isnan(arr)
    if not valid.any():
        return None, None
    start_idx = np.argmax(valid)
    end_idx = len(valid) - 1 - np.argmax(valid[::-1])
    return dates[start_idx], dates[end_idx]


# ================================================================
#  增量更新
# ================================================================
def incremental_update(qlib_dir, stock_list):
    import adata

    qlib_dir = Path(qlib_dir)

    # 1. 读现有 calendar，确定要拉的起始日期
    calendar, _ = load_calendar(qlib_dir)
    last_date = calendar[-1]
    next_date = (pd.Timestamp(last_date) + timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    if pd.Timestamp(next_date) > pd.Timestamp(today):
        print(f"  数据已是最新 (最后交易日: {last_date})")
        return last_date

    print(f"  最后交易日: {last_date}，拉取 {next_date} ~ {today}")

    # 2. 逐股票拉增量
    new_data = {}  # date -> {symbol: {col: value}}
    total = len(stock_list)
    errors = []

    for i, symbol in enumerate(stock_list):
        code = symbol[2:]
        try:
            df = adata.stock.market.get_market(
                stock_code=code, k_type=1, start_date=next_date
            )
            if df is None or len(df) == 0:
                continue

            if "trade_time" in df.columns and "trade_date" not in df.columns:
                df = df.rename(columns={"trade_time": "trade_date"})
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")

            for _, row in df.iterrows():
                date = row["trade_date"]
                if date not in new_data:
                    new_data[date] = {}
                new_data[date][symbol] = {
                    "open":   float(row.get("open", np.nan)),
                    "close":  float(row.get("close", np.nan)),
                    "high":   float(row.get("high", np.nan)),
                    "low":    float(row.get("low", np.nan)),
                    "volume": float(row.get("volume", np.nan)),
                }
        except Exception as e:
            errors.append((symbol, str(e)))

        if (i + 1) % 200 == 0:
            print(f"    进度: {i+1}/{total} | 新增 {len(new_data)} 个交易日")
            time.sleep(2)

    if errors:
        print(f"  ⚠ {len(errors)} 只拉取失败")
        for sym, err in errors[:5]:
            print(f"    {sym}: {err}")

    if not new_data:
        print("  没有新数据")
        return last_date

    # 3. 追加到 bin
    new_dates = sorted(new_data.keys())
    print(f"  新增交易日: {new_dates}")

    calendar.extend(new_dates)
    save_calendar(qlib_dir, calendar)

    for symbol in stock_list:
        for col_name, bin_name, dtype in FEATURE_MAP:
            old_arr = load_bin(qlib_dir, symbol, bin_name, dtype)
            if old_arr is None:
                old_arr = np.full(len(calendar) - len(new_dates), np.nan, dtype=dtype)

            new_arr = np.full(len(new_dates), np.nan, dtype=dtype)
            for j, date in enumerate(new_dates):
                if date in new_data and symbol in new_data[date]:
                    new_arr[j] = dtype(new_data[date][symbol].get(col_name, np.nan))

            full_arr = np.concatenate([old_arr, new_arr])
            save_bin(qlib_dir, symbol, bin_name, full_arr)

    latest = new_dates[-1]
    print(f"  ✅ 更新完成，最新交易日: {latest}")
    return latest


# ================================================================
#  更新 instruments
# ================================================================
def update_instruments(qlib_dir, stock_list):
    qlib_dir = Path(qlib_dir)
    instruments_dir = qlib_dir / "instruments"
    instruments_dir.mkdir(parents=True, exist_ok=True)

    # all.txt
    all_lines = []
    for symbol in stock_list:
        start, end = get_date_range(qlib_dir, symbol)
        if start and end:
            all_lines.append(f"{symbol}\t{start}\t{end}")

    with open(instruments_dir / "all.txt", "w") as f:
        f.write("\n".join(all_lines) + "\n")
    print(f"  all.txt: {len(all_lines)} 只")

    # 各指数
    import adata
    for name, (filename, index_code) in INDEX_MAP.items():
        try:
            df = adata.stock.info.index_constituent(index_code=index_code)
        except Exception as e:
            print(f"  ⚠ {name}({index_code}): {e}")
            continue

        lines = []
        for _, row in df.iterrows():
            code = str(row.iloc[0])
            if len(code) != 6:
                continue
            prefix = "SH" if code.startswith("6") else "SZ"
            symbol = f"{prefix}{code}"
            start, end = get_date_range(qlib_dir, symbol)
            if not start:
                start = "2000-01-01"
                end = datetime.now().strftime("%Y-%m-%d")
            lines.append(f"{symbol}\t{start}\t{end}")

        with open(instruments_dir / filename, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"  {filename}: {len(lines)} 只")


# ================================================================
#  入口
# ================================================================
def update_daily(qlib_dir=None):
    qlib_dir = Path(qlib_dir) if qlib_dir else DEFAULT_QLIB_DIR
    print(f"📁 qlib: {qlib_dir}")

    print("\n[1/3] 获取成分股...")
    stock_list = get_symbol_stocks("000852")
    print(f"  共 {len(stock_list)} 只")

    print("\n[2/3] 增量拉取行情 → 写入 bin...")
    latest_date = incremental_update(qlib_dir, stock_list)

    print("\n[3/3] 更新 instruments...")
    update_instruments(qlib_dir, stock_list)

    print(f"\n✅ 最新交易日: {latest_date}")
    return latest_date


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qlib-dir", default=str(DEFAULT_QLIB_DIR))
    args = parser.parse_args()

    latest = update_daily(qlib_dir=args.qlib_dir)
    if latest:
        print(f"💡 config.yaml end_time 应为: {latest}")


if __name__ == "__main__":
    main()
