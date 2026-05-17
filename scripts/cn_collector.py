"""
A-share daily kline collector with 2-source fallback (akshare-sina → baostock).
Output: one CSV per symbol in OUT_DIR, ready for Qlib dump_bin.

Notes:
- We bypass the system proxy (Clash-style scientific VPN at 127.0.0.1:7897)
  because it breaks TLS to push2his.eastmoney.com.
- We use the sina backend (akshare.stock_zh_a_daily) instead of the eastmoney
  backend (akshare.stock_zh_a_hist / efinance) — eastmoney does TLS fingerprinting
  and silently drops connections that don't look like a real Chrome browser.
- baostock is NOT thread-safe, so all baostock calls are serialized through a lock.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

for _var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_var, None)
os.environ["NO_PROXY"] = "*"

import pandas as pd

_BS_LOCK = threading.Lock()
_BS_LOGGED_IN = [False]


def to_qlib_symbol(code: str) -> str:
    code = code.strip().replace(".", "").upper()
    if code.startswith(("SH", "SZ", "BJ")):
        return code.lower()
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("0", "3")):
        return f"sz{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return code.lower()


def fetch_sina(code: str, start: str, end: str) -> pd.DataFrame | None:
    """Via akshare's sina backend. start/end as YYYYMMDD."""
    import akshare as ak
    sym = to_qlib_symbol(code)
    s = f"{start[:4]}-{start[4:6]}-{start[6:]}"
    e = f"{end[:4]}-{end[4:6]}-{end[6:]}"
    try:
        df = ak.stock_zh_a_daily(symbol=sym, start_date=s, end_date=e, adjust="qfq")
        if df is None or df.empty:
            return None
        df = df.rename(columns={"date": "date", "outstanding_share": "shares"})
        df["date"] = pd.to_datetime(df["date"])
        # sina volume is in shares already; convert to lots for unit consistency with baostock note
        # We keep shares as-is — Qlib doesn't care about unit, just consistency.
        return df[["date", "open", "close", "high", "low", "volume", "amount", "turnover"]]
    except Exception as e:
        print(f"  sina {code} failed: {e}", file=sys.stderr, flush=True)
        return None


def fetch_baostock(code: str, start: str, end: str) -> pd.DataFrame | None:
    import baostock as bs
    bs_code = f"sh.{code}" if code.startswith("6") else f"sz.{code}"
    with _BS_LOCK:
        if not _BS_LOGGED_IN[0]:
            bs.login()
            _BS_LOGGED_IN[0] = True
        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount,turn",
                start_date=f"{start[:4]}-{start[4:6]}-{start[6:]}",
                end_date=f"{end[:4]}-{end[4:6]}-{end[6:]}",
                frequency="d",
                adjustflag="2",
            )
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
            if not rows:
                return None
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount", "turnover"])
            for c in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df["date"] = pd.to_datetime(df["date"])
            return df[["date", "open", "close", "high", "low", "volume", "amount", "turnover"]]
        except Exception as e:
            print(f"  baostock {code} failed: {e}", file=sys.stderr, flush=True)
            return None


SOURCES = [("sina", fetch_sina), ("baostock", fetch_baostock)]


def fetch_one(code: str, start: str, end: str, out_dir: Path) -> tuple[str, pd.DataFrame | None, str]:
    sym = to_qlib_symbol(code)
    if (out_dir / f"{sym}.csv").exists():
        return code, None, "skip"
    for name, fn in SOURCES:
        df = fn(code, start, end)
        if df is not None and not df.empty:
            return code, df, name
    return code, None, "none"


def get_csi300_codes() -> list[str]:
    import akshare as ak
    df = ak.index_stock_cons(symbol="000300")
    return df["品种代码"].tolist()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="D:/PM/jr/qlib_data/csv")
    ap.add_argument("--start", default="20200101")
    ap.add_argument("--end", default="20260516")
    ap.add_argument("--limit", type=int, default=10, help="Limit number of symbols")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching CSI300 constituents via akshare...", flush=True)
    codes = get_csi300_codes()
    if args.limit > 0:
        codes = codes[: args.limit]
    print(f"Will fetch {len(codes)} symbols, {args.start} → {args.end}, workers={args.workers}", flush=True)

    t0 = time.time()
    src_count: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, c, args.start, args.end, out_dir): c for c in codes}
        for i, fut in enumerate(as_completed(futs), 1):
            code, df, src = fut.result()
            if src == "skip":
                src_count["skip"] = src_count.get("skip", 0) + 1
                print(f"[{i}/{len(codes)}] {to_qlib_symbol(code)} skip (cached)", flush=True)
                continue
            if df is None:
                print(f"[{i}/{len(codes)}] {code} FAILED", flush=True)
                src_count["none"] = src_count.get("none", 0) + 1
                continue
            sym = to_qlib_symbol(code)
            df["symbol"] = sym
            df = df[["date", "symbol", "open", "close", "high", "low", "volume", "amount", "turnover"]]
            df["factor"] = 1.0
            df.to_csv(out_dir / f"{sym}.csv", index=False)
            src_count[src] = src_count.get(src, 0) + 1
            print(f"[{i}/{len(codes)}] {sym} OK via {src} ({len(df)} rows)", flush=True)

    print(f"\nDone in {time.time() - t0:.1f}s. Sources used: {src_count}", flush=True)
    print(f"Output: {out_dir}", flush=True)


if __name__ == "__main__":
    main()
