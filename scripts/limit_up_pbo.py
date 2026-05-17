"""
limit_up_reversal grid search + CSCV PBO.

Tests whether the best-performing factor variant in the test segment
is genuinely picking up the A-share limit-up-reversal effect, or whether
it's an artefact of overfitting a single hyperparameter pair.

Variant:    `0 - Mean(Greater($close/Ref($close,1)-1, T), W)`
Sweep:      windows W in [5, 10, 20, 30, 60, 90, 120]
            thresholds T in [0.07, 0.08, 0.09, 0.095, 0.099]
Total:      35 variants.

For each variant:
  - Compute factor on csi300 test segment (2025-07-01 to 2026-05-13).
  - Daily IC and Rank IC vs next-day return.
  - Build long-top-50 daily P&L (equal-weight) — this is the strategy
    matrix fed to CSCV PBO.

Output: ranked grid table + PBO probability of overfitting.
"""
from __future__ import annotations

import json
import os
import sys
from itertools import product
from pathlib import Path

for v in ("HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(v, None)

sys.path.insert(0, "D:/PM/jr/src")

import numpy as np
import pandas as pd
import qlib
from qlib.constant import REG_CN
from qlib.data import D

from jr_validation import cscv_pbo


QLIB_DIR = "D:/PM/jr/qlib_data/cn_data"
TEST_START = "2025-07-01"
TEST_END = "2026-05-13"
TOP_K = 50

WINDOWS = [5, 10, 20, 30, 60, 90, 120]
THRESHOLDS = [0.07, 0.08, 0.09, 0.095, 0.099]


def factor_expr(window: int, threshold: float) -> str:
    return f"0 - Mean(Greater($close/Ref($close,1)-1, {threshold}), {window})"


def evaluate(window: int, threshold: float, label: pd.Series) -> dict:
    expr = factor_expr(window, threshold)
    try:
        df = D.features(
            D.instruments("csi300"),
            [expr],
            start_time=TEST_START, end_time=TEST_END, freq="day",
        )
    except Exception as e:
        return {"window": window, "threshold": threshold, "error": f"parse: {e}"}
    df.columns = ["factor"]
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    # join with label
    merged = df.join(label.rename("label"), how="inner").dropna()
    if merged.empty:
        return {"window": window, "threshold": threshold, "error": "empty after join"}

    by_date = merged.groupby(level="datetime")
    ic = by_date.apply(lambda g: g["factor"].corr(g["label"]) if len(g) > 5 else np.nan).dropna()
    rank_ic = by_date.apply(
        lambda g: g["factor"].rank().corr(g["label"].rank()) if len(g) > 5 else np.nan
    ).dropna()
    if ic.empty:
        return {"window": window, "threshold": threshold, "error": "no IC days"}

    # Build daily long-top-K P&L
    def daily_pnl(g):
        if len(g) < TOP_K:
            return np.nan
        top = g.nlargest(TOP_K, "factor")
        return top["label"].mean()

    pnl = by_date.apply(daily_pnl).dropna()

    return {
        "window": window, "threshold": threshold,
        "ic_mean": float(ic.mean()), "rank_ic_mean": float(rank_ic.mean()),
        "rank_ic_ir": float(rank_ic.mean() / rank_ic.std()) if rank_ic.std() > 0 else None,
        "pnl_mean_daily": float(pnl.mean()),
        "pnl_sharpe_ann": float(pnl.mean() / pnl.std() * np.sqrt(252)) if pnl.std() > 0 else None,
        "n_days": int(len(ic)),
        "pnl_series": pnl,
    }


def main() -> None:
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)

    # Realised next-day return as label (Alpha158-style)
    label_expr = "Ref($close, -2)/Ref($close, -1) - 1"
    label_df = D.features(
        D.instruments("csi300"),
        [label_expr],
        start_time=TEST_START, end_time=TEST_END, freq="day",
    )
    label_df.columns = ["label"]
    label = label_df["label"]
    print(f"Loaded label series: {len(label)} obs across {label.index.get_level_values('datetime').nunique()} days")

    grid = list(product(WINDOWS, THRESHOLDS))
    print(f"Sweeping {len(grid)} variants...")

    rows: list[dict] = []
    pnls: dict[str, pd.Series] = {}
    for i, (w, t) in enumerate(grid, 1):
        r = evaluate(w, t, label)
        name = f"W{w}_T{int(t*1000):03d}"
        if "error" in r:
            print(f"  [{i}/{len(grid)}] {name}: {r['error']}", flush=True)
            continue
        pnls[name] = r.pop("pnl_series")
        r["name"] = name
        rows.append(r)
        print(f"  [{i}/{len(grid)}] {name}: RankIC={r['rank_ic_mean']:+.4f} sharpe_ann={r['pnl_sharpe_ann']:+.2f}", flush=True)

    df = pd.DataFrame(rows).sort_values("rank_ic_mean", ascending=False)
    print("\n=== Grid sorted by RankIC ===")
    print(df[["name", "window", "threshold", "rank_ic_mean", "rank_ic_ir", "pnl_sharpe_ann"]].to_string(index=False))

    # PBO via CSCV
    pnl_df = pd.DataFrame(pnls).dropna(how="any")
    print(f"\nP&L matrix shape: {pnl_df.shape}  (T days × N strategies)")
    if pnl_df.shape[0] < 40:
        print("⚠️  Too few rows for CSCV n_splits=10; using 6.")
        n_splits = 6
    else:
        n_splits = 10
    result = cscv_pbo(pnl_df.values, n_splits=n_splits)
    print(f"\n=== PBO RESULT ===")
    print(f"PBO: {result['pbo']:.3f}")
    print(f"  > 0.5 = overfit. < 0.5 = robust signal.")
    print(f"n_combinations: {result['n_combinations']}")
    print(f"n_strategies:   {pnl_df.shape[1]}")

    out_path = Path("D:/PM/jr/qlib_data/limit_up_pbo_results.json")
    out_path.write_text(json.dumps({
        "grid": rows,
        "pbo": result["pbo"],
        "n_combinations": result["n_combinations"],
        "n_strategies": pnl_df.shape[1],
        "n_test_days": int(pnl_df.shape[0]),
        "best_by_rank_ic": df.iloc[0].to_dict() if not df.empty else None,
    }, indent=2, default=str))
    print(f"\nSaved → {out_path}")


if __name__ == "__main__":
    main()
