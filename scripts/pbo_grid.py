"""
Generate a grid of LightGBM strategy variants, collect their OOS daily P&L
on the test segment, and run PBO to detect overfitting.

This is the empirical test of whether our "22.7% IR=2.45" baseline survives
combinatorially-symmetric cross-validation, or is just one lucky draw from
the hyperparameter lottery.
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
from qlib.contrib.data.handler import Alpha158
from qlib.contrib.model.gbdt import LGBModel
from qlib.data.dataset import DatasetH

from jr_validation import cscv_pbo

QLIB_DIR = "D:/PM/jr/qlib_data/cn_data"
OUT_PATH = Path("D:/PM/jr/qlib_data/pbo_results.json")


def make_dataset() -> DatasetH:
    handler = Alpha158(
        instruments="csi300",
        start_time="2018-01-01",
        end_time="2026-05-15",
        fit_start_time="2018-01-01",
        fit_end_time="2024-06-30",
    )
    return DatasetH(
        handler=handler,
        segments={
            "train": ("2018-01-01", "2024-06-30"),
            "valid": ("2024-07-01", "2025-06-30"),
            "test": ("2025-07-01", "2026-05-13"),
        },
    )


def long_only_topk_pnl(pred_series: pd.Series, returns: pd.Series, k: int = 50) -> pd.Series:
    """Daily equal-weight long top-k of predicted signal.

    Returns a daily P&L series indexed by date.
    """
    df = pd.DataFrame({"pred": pred_series, "ret": returns}).dropna()
    df = df.reset_index()
    df.columns = ["datetime", "instrument", "pred", "ret"]
    # for each date, take top-k by pred and equal-weight their next-day return
    out = (
        df.sort_values(["datetime", "pred"], ascending=[True, False])
        .groupby("datetime")
        .head(k)
        .groupby("datetime")["ret"]
        .mean()
    )
    return out


def main() -> None:
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)
    print("Loading Alpha158 dataset (this is the slow part, ~1-2 min)...")
    dataset = make_dataset()

    # Hyperparam grid: 24 variants
    grid = {
        "learning_rate": [0.03, 0.05, 0.1],
        "max_depth": [5, 8, 12],
        "num_leaves": [63, 210],
        "subsample": [0.7, 0.9],
    }
    keys = list(grid.keys())
    combos = list(product(*[grid[k] for k in keys]))
    # cap at 24 to keep runtime sane (~24 * 30s training = 12 min)
    combos = combos[:24]
    print(f"Will fit {len(combos)} LightGBM variants")

    # Read realised next-day returns from raw qlib data — Alpha158 label is Ref($close,-2)/Ref($close,-1)-1
    test_segment = dataset.prepare("test", col_set=["label"], data_key="raw")
    actual_ret = test_segment["label"]["LABEL0"]

    pnl_per_strategy = {}
    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        model = LGBModel(
            loss="mse",
            colsample_bytree=0.88,
            lambda_l1=200,
            lambda_l2=580,
            num_threads=8,
            **params,
        )
        print(f"[{i+1}/{len(combos)}] training {params} ...", flush=True)
        model.fit(dataset)
        pred = model.predict(dataset, segment="test")
        if hasattr(pred, "iloc") and pred.ndim == 2:
            pred = pred.iloc[:, 0]
        pnl = long_only_topk_pnl(pred, actual_ret, k=50)
        name = "_".join(f"{k}={v}" for k, v in params.items())
        pnl_per_strategy[name] = pnl
        print(f"   final OOS mean daily ret = {pnl.mean():.4%}, sharpe ann = {pnl.mean()/pnl.std()*np.sqrt(252):.2f}", flush=True)

    # Stack into T x N matrix, aligned on common dates
    pnl_df = pd.DataFrame(pnl_per_strategy)
    pnl_df = pnl_df.dropna(how="any")
    print(f"\nP&L matrix shape: {pnl_df.shape}")

    # PBO
    result = cscv_pbo(pnl_df.values, n_splits=10)
    print(f"\n=== PBO RESULTS ===")
    print(f"PBO: {result['pbo']:.3f}")
    print(f"  Interpretation: probability the IS-best strategy is OOS-bad.")
    print(f"  > 0.5: overfit. < 0.5: real edge.")
    print(f"n_combinations evaluated: {result['n_combinations']}")

    OUT_PATH.write_text(json.dumps({
        "pbo": result["pbo"],
        "n_combinations": result["n_combinations"],
        "n_strategies": pnl_df.shape[1],
        "n_test_days": pnl_df.shape[0],
        "strategy_sharpes": {
            k: float(v.mean() / v.std() * np.sqrt(252)) for k, v in pnl_per_strategy.items()
        },
    }, indent=2))
    print(f"\nResults written to {OUT_PATH}")


if __name__ == "__main__":
    main()
