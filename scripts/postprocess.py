"""
Post-process collected CSVs for Qlib Alpha158 compatibility:
1. Add `vwap` column (= amount / volume) to every per-symbol CSV.
2. Download CSI300 index daily kline (SH000300) and add it as an instrument
   so Qlib backtest can compute excess return vs benchmark.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(v, None)

import pandas as pd

CSV_DIR = Path("D:/PM/jr/qlib_data/csv")


def add_vwap_inplace() -> None:
    files = sorted(CSV_DIR.glob("*.csv"))
    print(f"Adding vwap to {len(files)} CSVs...")
    for i, f in enumerate(files, 1):
        df = pd.read_csv(f)
        if "vwap" in df.columns:
            continue
        # vwap = amount / volume; guard against div-by-zero
        df["vwap"] = (df["amount"] / df["volume"]).where(df["volume"] > 0, df["close"])
        df.to_csv(f, index=False)
        if i % 50 == 0:
            print(f"  [{i}/{len(files)}]")
    print("Done.")


def download_csi300_index() -> None:
    import akshare as ak
    print("Downloading CSI300 index (SH000300) from sina...")
    df = ak.stock_zh_index_daily(symbol="sh000300")
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] >= pd.Timestamp("2018-01-01")].copy()
    df["symbol"] = "sh000300"
    # index doesn't have amount/turnover; fill sentinel
    df["amount"] = df["close"] * df["volume"]
    df["turnover"] = 0.0
    df["factor"] = 1.0
    df["vwap"] = df["close"]
    df = df[["date", "symbol", "open", "close", "high", "low", "volume", "amount", "turnover", "factor", "vwap"]]
    out = CSV_DIR / "sh000300.csv"
    df.to_csv(out, index=False)
    print(f"  wrote {out}: {len(df)} rows, last date {df['date'].iloc[-1]}")


if __name__ == "__main__":
    add_vwap_inplace()
    download_csi300_index()
