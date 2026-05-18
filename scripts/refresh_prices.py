"""Incrementally refresh price CSVs (latest N days only).

For each existing CSV in qlib_data/csv/, read its last date and pull from
(last_date + 1) to today via akshare-sina, then append + dedupe.

Much faster than full cn_collector.py (~30 sec vs ~30 min) — appropriate
for monthly updates or whenever the dashboard shows stale data.

Falls back to baostock if sina fails on a particular symbol.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

for _v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_v, None)
os.environ["NO_PROXY"] = "*"

import pandas as pd

CSV_DIR = Path(os.environ.get("JR_PROJ_ROOT", "D:/PM/jr")) / "qlib_data" / "csv"
WORKERS = 6
_BS_LOCK = threading.Lock()
_BS_LOGGED_IN = [False]


def to_qlib_sym(stem: str) -> str:
    return stem.lower()


def fetch_sina_tail(qlib_sym: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame | None:
    """Pull (start..end] from sina via akshare. qlib_sym like 'sh600000'."""
    import akshare as ak
    try:
        df = ak.stock_zh_a_daily(symbol=qlib_sym, start_date=start.strftime("%Y%m%d"),
                                 end_date=end.strftime("%Y%m%d"), adjust="")
        if df is None or len(df) == 0:
            return None
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        return df
    except Exception:
        return None


def fetch_baostock_tail(qlib_sym: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame | None:
    """Fallback: baostock. Format conversion required."""
    import baostock as bs
    with _BS_LOCK:
        if not _BS_LOGGED_IN[0]:
            bs.login()
            _BS_LOGGED_IN[0] = True
        bs_code = f"sh.{qlib_sym[2:]}" if qlib_sym.startswith("sh") else f"sz.{qlib_sym[2:]}"
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,close,high,low,volume,amount,turn",
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            frequency="d", adjustflag="3",
        )
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume", "amount", "turnover"])
    df["date"] = pd.to_datetime(df["date"])
    for c in ("open", "close", "high", "low", "volume", "amount", "turnover"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["date", "close"]).reset_index(drop=True)


def update_one(csv_path: Path, today: pd.Timestamp) -> tuple[str, str]:
    sym = csv_path.stem
    try:
        existing = pd.read_csv(csv_path, parse_dates=["date"])
    except Exception as e:
        return sym, f"read fail: {e}"
    if existing.empty:
        return sym, "empty existing"

    last_date = existing["date"].max()
    if last_date >= today:
        return sym, "already current"

    start = last_date + pd.Timedelta(days=1)
    new = fetch_sina_tail(sym, start, today)
    src = "sina"
    if new is None or new.empty:
        new = fetch_baostock_tail(sym, start, today)
        src = "baostock"
    if new is None or new.empty:
        return sym, "no new data"

    # Align column schema with existing CSV
    new["symbol"] = sym
    # vwap column (existing has it)
    if "amount" in new.columns and "volume" in new.columns:
        with pd.option_context("mode.use_inf_as_na", True):
            new["vwap"] = (new["amount"] / new["volume"].replace(0, pd.NA)).fillna(0)
    new["factor"] = 1.0
    keep_cols = [c for c in existing.columns if c in new.columns]
    new = new[keep_cols]

    combined = pd.concat([existing, new], ignore_index=True)
    combined = combined.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    combined.to_csv(csv_path, index=False)
    return sym, f"+{len(new)} rows via {src}"


def main() -> None:
    if not CSV_DIR.exists():
        print(f"FAIL: {CSV_DIR} not found", flush=True)
        sys.exit(1)

    today = pd.Timestamp.today().normalize()
    files = list(CSV_DIR.glob("*.csv"))
    print(f"Refreshing {len(files)} symbols, target date {today.strftime('%Y-%m-%d')}", flush=True)

    t0 = time.time()
    done = 0
    skipped = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(update_one, p, today): p.stem for p in files}
        for i, f in enumerate(as_completed(futs), 1):
            sym, status = f.result()
            if "+" in status:
                done += 1
            elif "current" in status:
                skipped += 1
            else:
                failed += 1
            if i % 25 == 0 or i == len(files) or "+" in status:
                print(f"  [{i}/{len(files)}] {sym}: {status}", flush=True)

    # Logout baostock if used
    try:
        if _BS_LOGGED_IN[0]:
            import baostock as bs
            bs.logout()
    except Exception:
        pass

    print(f"\nDone in {time.time() - t0:.1f}s. updated={done}, already_current={skipped}, failed={failed}", flush=True)


if __name__ == "__main__":
    main()
