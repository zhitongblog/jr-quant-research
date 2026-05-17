"""
Build a survivorship-bias-free CSI300 instrument list.

For each month between 2018-01 and 2026-05, query baostock for the index
constituents on the month's first trading day. Aggregate into:
  - union.csv:        every symbol that was ever in CSI300 in the window
  - csi300.txt:       Qlib instrument file with per-symbol start/end intervals
                      reflecting when each symbol was actually a member.

Run before the main collector so the universe is complete.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

for v in ("HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(v, None)

import pandas as pd
import baostock as bs


OUT_DIR = Path("D:/PM/jr/qlib_data")
START = "2018-01-01"
END = "2026-05-15"


def first_trading_days() -> list[str]:
    """List the first trading day of each month in [START, END]."""
    bs.login()
    rs = bs.query_trade_dates(start_date=START, end_date=END)
    trade_days = []
    while rs.error_code == "0" and rs.next():
        row = rs.get_row_data()
        if row[1] == "1":  # is_trading_day
            trade_days.append(row[0])
    df = pd.DataFrame({"date": pd.to_datetime(trade_days)})
    df["ym"] = df["date"].dt.to_period("M")
    firsts = df.groupby("ym")["date"].min().dt.strftime("%Y-%m-%d").tolist()
    return firsts


def main() -> None:
    print(f"Collecting CSI300 constituents 月初快照 {START} → {END} ...")
    snapshot_dates = first_trading_days()
    print(f"  {len(snapshot_dates)} monthly snapshots planned")

    # per-symbol intervals of membership
    intervals: dict[str, list[tuple[str, str]]] = defaultdict(list)
    # carrying state: which symbols were members at the previous snapshot?
    prev_members: set[str] = set()
    prev_date: str | None = None

    for d in snapshot_dates:
        rs = bs.query_hs300_stocks(date=d)
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            continue
        # bs symbols are 'sh.600000' — strip dot
        members = {r[1].replace(".", "") for r in rows}
        # opens: new this snapshot
        for sym in members - prev_members:
            intervals[sym].append([d, None])  # to be closed
        # closes: dropped this snapshot
        for sym in prev_members - members:
            # close at prev_date (last day before drop)
            intervals[sym][-1][1] = prev_date
        prev_members = members
        prev_date = d
        if len(intervals) % 50 == 0:
            print(f"  through {d}: total ever-members = {len(intervals)}")

    # close still-open intervals at END
    for sym, ivs in intervals.items():
        for iv in ivs:
            if iv[1] is None:
                iv[1] = END

    bs.logout()

    union = sorted(intervals.keys())
    print(f"\nTotal symbols that were ever in CSI300 in window: {len(union)}")

    # Qlib instrument file format: <SYMBOL>\t<start>\t<end>, one line per interval
    csi300_path = OUT_DIR / "csi300_history.txt"
    with csi300_path.open("w") as f:
        for sym in union:
            for start, end in intervals[sym]:
                # Qlib uses uppercase symbol convention in instrument files
                f.write(f"{sym.upper()}\t{start}\t{end}\n")
    n_lines = sum(len(v) for v in intervals.values())
    print(f"  wrote {csi300_path}: {n_lines} interval rows")

    # plain union list for the collector
    union_path = OUT_DIR / "union_codes.txt"
    with union_path.open("w") as f:
        for sym in union:
            # collector wants 6-digit code (e.g. '600000')
            code = sym.replace("sh", "").replace("sz", "").replace("bj", "")
            f.write(code + "\n")
    print(f"  wrote {union_path}: {len(union)} codes")


if __name__ == "__main__":
    main()
