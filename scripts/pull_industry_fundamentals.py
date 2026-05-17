"""
One-time data pull for paths A/B/C:

  - SW Level-1 industry list (31 rows)              -> qlib_data/sw1_list.csv
  - SW Level-1 daily index OHLCV (31 files)         -> qlib_data/sw1_idx/801xxx.csv
  - Per-stock SW-1 industry membership              -> qlib_data/stock_sw1.csv
  - Per-stock quarterly financial indicators        -> qlib_data/fundamentals/<symbol>.csv

Slow part is fundamentals (553 stocks * ~16 quarters = 8k+ rows, plus per-stock
API call). Uses a thread pool but akshare backends differ in tolerance so we
keep workers low.

Idempotent: skips files that already exist with non-zero size, so it's safe to
re-run if interrupted.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

for v in ("HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(v, None)

sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
import akshare as ak

OUT_DIR = Path("D:/PM/jr/qlib_data")
SW1_IDX_DIR = OUT_DIR / "sw1_idx"
FUND_DIR = OUT_DIR / "fundamentals"
SW1_IDX_DIR.mkdir(parents=True, exist_ok=True)
FUND_DIR.mkdir(parents=True, exist_ok=True)


# --- 1. SW Level-1 industry list ---------------------------------------------

def pull_sw1_list() -> pd.DataFrame:
    out = OUT_DIR / "sw1_list.csv"
    if out.exists() and out.stat().st_size > 0:
        print(f"[skip] {out}")
        return pd.read_csv(out, dtype={"行业代码": str})
    df = ak.sw_index_first_info()
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[ok]   {out}  ({len(df)} rows)")
    return df


# --- 2. SW-1 industry index daily OHLCV --------------------------------------

def pull_sw1_idx(code: str) -> tuple[str, str]:
    sym = code.replace(".SI", "")
    out = SW1_IDX_DIR / f"{sym}.csv"
    if out.exists() and out.stat().st_size > 200:
        return sym, "skip"
    try:
        df = ak.index_hist_sw(symbol=sym, period="day")
        df.to_csv(out, index=False, encoding="utf-8-sig")
        return sym, f"ok ({len(df)})"
    except Exception as e:
        return sym, f"fail: {e}"


# --- 3. Per-stock SW-1 membership --------------------------------------------

def pull_stock_sw1_map(sw1_codes: list[str]) -> pd.DataFrame:
    out = OUT_DIR / "stock_sw1.csv"
    if out.exists() and out.stat().st_size > 0:
        print(f"[skip] {out}")
        return pd.read_csv(out, dtype={"symbol": str, "sw1_code": str})
    rows = []
    for code in sw1_codes:
        sym = code.replace(".SI", "")
        try:
            comps = ak.index_component_sw(symbol=sym)
            for _, r in comps.iterrows():
                rows.append({"symbol": r["证券代码"], "name": r["证券名称"],
                             "sw1_code": sym, "join_date": r["计入日期"]})
        except Exception as e:
            print(f"  [fail] {sym}: {e}")
            continue
        time.sleep(0.4)
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[ok]   {out}  ({len(df)} stock-industry rows, {df['symbol'].nunique()} unique stocks)")
    return df


# --- 4. Per-stock fundamentals -----------------------------------------------

def stocks_in_our_universe() -> list[str]:
    """Return 6-digit codes from qlib_data/csv/SH600xxx.csv style filenames."""
    csv_dir = OUT_DIR / "csv"
    syms = []
    for p in csv_dir.glob("*.csv"):
        name = p.stem.upper()
        # SH600000 -> 600000 ; SZ000001 -> 000001 ; SH000300 (index) skip
        if name.startswith(("SH", "SZ")) and len(name) == 8:
            code = name[2:]
            # exclude indices (SH000xxx)
            if name.startswith("SH00") and code.startswith("0"):
                continue
            syms.append(code)
    return sorted(set(syms))


def pull_one_fundamental(sym: str) -> tuple[str, str]:
    out = FUND_DIR / f"{sym}.csv"
    if out.exists() and out.stat().st_size > 200:
        return sym, "skip"
    try:
        df = ak.stock_financial_analysis_indicator(symbol=sym, start_year="2017")
        if df is None or len(df) == 0:
            return sym, "empty"
        # Keep only the metrics we'll use to limit file size
        keep = ["日期"]
        for col in df.columns[1:]:
            if any(k in col for k in [
                "净资产收益率", "总资产报酬率", "营业利润率", "毛利率",
                "每股净资产", "营业收入增长率", "净利润增长率",
                "每股收益", "每股经营性现金流", "资产负债率", "流动比率",
                "市净率", "市盈率",
            ]):
                keep.append(col)
        df = df[keep] if len(keep) > 1 else df
        df.to_csv(out, index=False, encoding="utf-8-sig")
        return sym, f"ok ({len(df)}r/{len(keep)}c)"
    except Exception as e:
        return sym, f"fail: {str(e)[:80]}"


# --- main --------------------------------------------------------------------

def main() -> None:
    t0 = time.time()
    print("== 1/4 SW Level-1 industry list ==")
    sw1 = pull_sw1_list()
    codes = sw1["行业代码"].tolist()
    print(f"  {len(codes)} SW-1 industries")

    print("\n== 2/4 SW-1 daily index OHLCV (31 files) ==")
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(pull_sw1_idx, c): c for c in codes}
        for f in as_completed(futs):
            sym, status = f.result()
            print(f"  [{sym}] {status}")

    print("\n== 3/4 Per-stock SW-1 membership ==")
    stock_map = pull_stock_sw1_map(codes)

    print("\n== 4/4 Per-stock fundamentals ==")
    universe = stocks_in_our_universe()
    print(f"  {len(universe)} stocks in universe")
    done, fail = 0, 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(pull_one_fundamental, s): s for s in universe}
        for i, f in enumerate(as_completed(futs), 1):
            sym, status = f.result()
            if status.startswith("ok") or status == "skip":
                done += 1
            else:
                fail += 1
            if i % 25 == 0 or i == len(universe):
                print(f"  [{i}/{len(universe)}] {sym}: {status}  (done={done} fail={fail})", flush=True)

    print(f"\nElapsed {time.time()-t0:.1f}s")
    print(f"  sw1_list      -> {OUT_DIR}/sw1_list.csv")
    print(f"  sw1_idx/      -> {SW1_IDX_DIR}  ({len(list(SW1_IDX_DIR.glob('*.csv')))} files)")
    print(f"  stock_sw1     -> {OUT_DIR}/stock_sw1.csv")
    print(f"  fundamentals/ -> {FUND_DIR}  ({len(list(FUND_DIR.glob('*.csv')))} files)")


if __name__ == "__main__":
    main()
