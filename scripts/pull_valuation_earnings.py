"""Pull historical valuation (PE/PB/market cap) and recent earnings forecasts.

Outputs:
  - qlib_data/valuation/<symbol>.csv  : per-stock daily PE/PB/PEG/PS history (~2028 rows)
  - qlib_data/yjyg/<YYYYMMDD>.csv     : market-wide earnings forecast snapshots by quarter

The valuation pull is slow (~553 stocks × 5-15s each). Uses ThreadPoolExecutor.
Idempotent: skips files that exist with non-trivial size.
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

QLIB = Path(os.environ.get("JR_PROJ_ROOT", "D:/PM/jr")) / "qlib_data"
VAL_DIR = QLIB / "valuation"
YJYG_DIR = QLIB / "yjyg"
VAL_DIR.mkdir(parents=True, exist_ok=True)
YJYG_DIR.mkdir(parents=True, exist_ok=True)


def csi300_symbols() -> list[str]:
    """Read existing CSV files to get the symbol universe."""
    csv_dir = QLIB / "csv"
    syms: list[str] = []
    for p in csv_dir.glob("*.csv"):
        name = p.stem.upper()
        if not name.startswith(("SH", "SZ")) or len(name) != 8:
            continue
        code = name[2:]
        # exclude indices (SH000xxx)
        if name.startswith("SH00") and code.startswith("0"):
            continue
        syms.append(code)
    return sorted(set(syms))


# ---------- 1. Valuation history ----------

def pull_one_valuation(sym: str) -> tuple[str, str]:
    out = VAL_DIR / f"{sym}.csv"
    if out.exists() and out.stat().st_size > 1000:
        return sym, "skip"
    try:
        df = ak.stock_value_em(symbol=sym)
        if df is None or len(df) == 0:
            return sym, "empty"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        return sym, f"ok ({len(df)})"
    except Exception as e:
        return sym, f"fail: {str(e)[:80]}"


def pull_valuations(syms: list[str], workers: int = 4) -> None:
    print(f"== Valuation history ({len(syms)} stocks, {workers} workers) ==", flush=True)
    done = 0; fail = 0; skip = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(pull_one_valuation, s): s for s in syms}
        for i, f in enumerate(as_completed(futs), 1):
            sym, status = f.result()
            if status == "skip": skip += 1
            elif status.startswith("ok"): done += 1
            else: fail += 1
            if i % 25 == 0 or i == len(syms):
                rate = i / max(time.time() - t0, 0.1)
                eta = (len(syms) - i) / max(rate, 0.01)
                print(f"  [{i}/{len(syms)}] {sym}: {status}  | done={done} fail={fail} skip={skip}  rate={rate:.1f}/s ETA={eta/60:.1f}min", flush=True)
    print(f"\n  Total {len(list(VAL_DIR.glob('*.csv')))} valuation files in {VAL_DIR}\n", flush=True)


# ---------- 2. Earnings forecasts (last 8 quarters) ----------

def quarter_dates(n: int = 8) -> list[str]:
    """Return last N quarter-end dates as YYYYMMDD strings."""
    now = pd.Timestamp.now()
    qts = []
    for i in range(n):
        end = (now - pd.DateOffset(months=3 * i)).to_period("Q").end_time.normalize()
        qts.append(end.strftime("%Y%m%d"))
    return list(dict.fromkeys(qts))   # dedupe, preserve order


def pull_one_yjyg(qdate: str) -> tuple[str, str]:
    out = YJYG_DIR / f"{qdate}.csv"
    if out.exists() and out.stat().st_size > 200:
        return qdate, "skip"
    try:
        df = ak.stock_yjyg_em(date=qdate)
        if df is None or len(df) == 0:
            return qdate, "empty"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        return qdate, f"ok ({len(df)})"
    except Exception as e:
        return qdate, f"fail: {str(e)[:80]}"


def pull_yjyg(quarters: list[str]) -> None:
    print(f"== Earnings forecasts ({len(quarters)} quarters) ==", flush=True)
    for q in quarters:
        sym, status = pull_one_yjyg(q)
        print(f"  [{q}]: {status}", flush=True)


# ---------- main ----------

def main() -> None:
    t0 = time.time()
    syms = csi300_symbols()
    print(f"Found {len(syms)} stocks in csv/ to pull for", flush=True)

    pull_yjyg(quarter_dates(8))
    print()
    pull_valuations(syms, workers=4)
    print(f"Total elapsed: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
