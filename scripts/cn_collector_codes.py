"""Run the existing cn_collector but with a hand-supplied symbol list."""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# reuse internals
sys.path.insert(0, str(Path(__file__).parent))
from cn_collector import fetch_one, to_qlib_symbol


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="D:/PM/jr/qlib_data/csv")
    ap.add_argument("--codes-file", required=True, help="One 6-digit code per line")
    ap.add_argument("--start", default="20180101")
    ap.add_argument("--end", default="20260516")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    codes = [c.strip() for c in Path(args.codes_file).read_text().splitlines() if c.strip()]
    print(f"Loaded {len(codes)} symbols from {args.codes_file}")

    t0 = time.time()
    src_count: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, c, args.start, args.end, out_dir): c for c in codes}
        import pandas as pd
        for i, fut in enumerate(as_completed(futs), 1):
            code, df, src = fut.result()
            if src == "skip":
                src_count["skip"] = src_count.get("skip", 0) + 1
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
            if i % 50 == 0:
                print(f"[{i}/{len(codes)}] progress; src={src_count}", flush=True)

    print(f"\nDone in {time.time()-t0:.1f}s. Sources: {src_count}")


if __name__ == "__main__":
    main()
