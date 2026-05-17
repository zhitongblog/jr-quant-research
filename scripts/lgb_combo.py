"""
F3: Three-factor LightGBM combo strategy.

Inputs three orthogonal-ish alpha factors discovered in the LLM-factor loop:
  1. limit_up_reversal_20d        (A-share structural: fade frequent limit-ups)
  2. price_volume_divergence      (volume z-score x 1-day return)
  3. amihud_illiquidity_20d       (liquidity premium)

Trains a small LightGBM (depth-capped, low LR) to learn the optimal
non-linear combination on train+valid, then evaluates on the same
2025-07-01 to 2026-05-13 test segment used elsewhere.

Output:
  - Daily long-top-50 P&L, Sharpe, IC, Rank IC
  - Compares to each factor in isolation as a sanity check
  - Persists results to qlib_data/lgb_combo_results.json
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

for v in ("HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(v, None)

sys.path.insert(0, "D:/PM/jr/src")

import numpy as np
import pandas as pd
import qlib
from qlib.constant import REG_CN
from qlib.data import D

import lightgbm as lgb

QLIB_DIR = "D:/PM/jr/qlib_data/cn_data"
TRAIN_START, TRAIN_END = "2018-01-01", "2024-06-30"
VALID_START, VALID_END = "2024-07-01", "2025-06-30"
TEST_START,  TEST_END  = "2025-07-01", "2026-05-13"
TOP_K = 50

FACTORS = {
    "limit_up_reversal_20d":   "0 - Mean(Greater($close/Ref($close,1)-1, 0.095), 20)",
    "price_volume_divergence": "($volume - Mean($volume, 20)) / (Std($volume, 20) + 1e-8) * ($close/Ref($close,1) - 1)",
    "amihud_illiquidity_20d":  "Mean(Abs($close/Ref($close,1) - 1) / ($amount + 1e-8), 20)",
}
LABEL_EXPR = "Ref($close, -2)/Ref($close, -1) - 1"


def load_panel(start: str, end: str) -> pd.DataFrame:
    exprs = list(FACTORS.values()) + [LABEL_EXPR]
    df = D.features(D.instruments("csi300"), exprs, start_time=start, end_time=end, freq="day")
    df.columns = list(FACTORS.keys()) + ["label"]
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    return df


def daily_ic(signal: pd.Series, label: pd.Series) -> tuple[float, float, int]:
    df = pd.DataFrame({"s": signal, "y": label}).dropna()
    g = df.groupby(level="datetime")
    ic = g.apply(lambda x: x["s"].corr(x["y"]) if len(x) > 5 else np.nan).dropna()
    ric = g.apply(lambda x: x["s"].rank().corr(x["y"].rank()) if len(x) > 5 else np.nan).dropna()
    return float(ic.mean()), float(ric.mean()), int(len(ic))


def topk_pnl(signal: pd.Series, label: pd.Series, k: int = TOP_K) -> pd.Series:
    df = pd.DataFrame({"s": signal, "y": label}).dropna()
    df = (
        df.reset_index()
          .sort_values(["datetime", "s"], ascending=[True, False])
          .groupby("datetime")
          .head(k)
    )
    return df.groupby("datetime")["y"].mean()


def main() -> None:
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)
    print("Loading panel: train / valid / test ...", flush=True)
    train = load_panel(TRAIN_START, TRAIN_END)
    valid = load_panel(VALID_START, VALID_END)
    test  = load_panel(TEST_START,  TEST_END)
    feature_cols = list(FACTORS.keys())
    print(f"  train: {len(train):,} rows / valid: {len(valid):,} / test: {len(test):,}", flush=True)

    # Per-factor isolated baseline on test
    print("\n--- Factor-isolated baselines (test) ---", flush=True)
    isolated = {}
    for f in feature_cols:
        ic, ric, n = daily_ic(test[f], test["label"])
        pnl = topk_pnl(test[f], test["label"])
        sharpe = float(pnl.mean() / pnl.std() * np.sqrt(252)) if pnl.std() > 0 else None
        isolated[f] = {"ic": ic, "rank_ic": ric, "n_days": n, "sharpe_ann": sharpe,
                       "pnl_mean_daily": float(pnl.mean())}
        sh_s = f"{sharpe:+.2f}" if sharpe is not None else "n/a"
        print(f"  {f:30s} IC={ic:+.4f}  RankIC={ric:+.4f}  Sharpe={sh_s}  n={n}", flush=True)

    # LightGBM combo
    print("\n--- LightGBM combo ---", flush=True)
    train_set = lgb.Dataset(train[feature_cols].values, label=train["label"].values)
    valid_set = lgb.Dataset(valid[feature_cols].values, label=valid["label"].values, reference=train_set)
    params = dict(
        objective="regression", metric="rmse",
        learning_rate=0.03, num_leaves=15, max_depth=4,
        min_data_in_leaf=200, feature_fraction=1.0, bagging_fraction=0.8,
        bagging_freq=5, lambda_l1=1.0, lambda_l2=10.0, verbose=-1,
    )
    model = lgb.train(
        params, train_set, num_boost_round=2000, valid_sets=[valid_set],
        callbacks=[lgb.early_stopping(stopping_rounds=50), lgb.log_evaluation(period=200)],
    )

    test["pred"] = model.predict(test[feature_cols].values)
    ic, ric, n = daily_ic(test["pred"], test["label"])
    pnl = topk_pnl(test["pred"], test["label"])
    sharpe = float(pnl.mean() / pnl.std() * np.sqrt(252)) if pnl.std() > 0 else None
    cum_ret = float((1 + pnl).prod() - 1)
    print(f"\n=== COMBO RESULT (test) ===", flush=True)
    print(f"  IC      = {ic:+.4f}", flush=True)
    print(f"  RankIC  = {ric:+.4f}", flush=True)
    print(f"  Sharpe  = {sharpe:+.2f}" if sharpe is not None else "  Sharpe  = n/a", flush=True)
    print(f"  daily mean = {pnl.mean():+.4%}", flush=True)
    print(f"  cumulative = {cum_ret:+.2%} over {n} days", flush=True)
    print(f"  best_iter  = {model.best_iteration}", flush=True)
    print(f"  feat_imp   = {dict(zip(feature_cols, model.feature_importance().tolist()))}", flush=True)

    out = Path("D:/PM/jr/qlib_data/lgb_combo_results.json")
    out.write_text(json.dumps({
        "factors": FACTORS,
        "isolated": isolated,
        "combo": {
            "ic": ic, "rank_ic": ric, "sharpe_ann": sharpe,
            "pnl_mean_daily": float(pnl.mean()),
            "cum_return": cum_ret, "n_days": n,
            "best_iter": int(model.best_iteration),
            "feature_importance": dict(zip(feature_cols, [int(x) for x in model.feature_importance()])),
        },
    }, indent=2))
    print(f"\nSaved -> {out}", flush=True)


if __name__ == "__main__":
    main()
