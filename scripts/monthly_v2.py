"""
F5-v2: Monthly backtest with three sanity checks bolted on:

  1. CSI300 buy-and-hold benchmark (is our Sharpe alpha or beta?)
  2. Walk-forward LightGBM (retrain at every month-end on expanding window)
  3. Equal-weight cross-sectional z-score linear combo (does LGB even help?)

All strategies share:
  - Same universe (survivorship-corrected csi300)
  - Same top-K = 50, equal weight, monthly rebalance
  - Same realistic A-share costs (buy 0.13% / sell 0.18% per leg)
  - Same test segment 2025-07-01 to 2026-05-13

Output: D:/PM/jr/qlib_data/monthly_v2_results.json + console table.
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
TRAIN_START = "2018-01-01"   # expands for walk-forward
FIXED_TRAIN_END = "2024-06-30"
VALID_START, VALID_END = "2024-07-01", "2025-06-30"
TEST_START, TEST_END = "2025-07-01", "2026-05-13"
TOP_K = 50

COST_BUY_LEG  = 0.0003 + 0.0010                  # 0.13%
COST_SELL_LEG = 0.0003 + 0.0005 + 0.0010         # 0.18%

FACTORS = {
    "limit_up_reversal_20d":   "0 - Mean(Greater($close/Ref($close,1)-1, 0.095), 20)",
    "price_volume_divergence": "($volume - Mean($volume, 20)) / (Std($volume, 20) + 1e-8) * ($close/Ref($close,1) - 1)",
    "amihud_illiquidity_20d":  "Mean(Abs($close/Ref($close,1) - 1) / ($amount + 1e-8), 20)",
}
LABEL_EXPR = "Ref($close, -22)/Ref($close, -1) - 1"
DAILY_RET_EXPR = "$close/Ref($close, 1) - 1"

LGB_PARAMS = dict(objective="regression", metric="rmse",
                  learning_rate=0.03, num_leaves=15, max_depth=4,
                  min_data_in_leaf=200, feature_fraction=1.0, bagging_fraction=0.8,
                  bagging_freq=5, lambda_l1=1.0, lambda_l2=10.0, verbose=-1)


# ---------- Data loading ----------

def load_panel(start: str, end: str, with_label: bool = True) -> pd.DataFrame:
    exprs = list(FACTORS.values())
    cols = list(FACTORS.keys())
    if with_label:
        exprs.append(LABEL_EXPR); cols.append("label")
    df = D.features(D.instruments("csi300"), exprs, start_time=start, end_time=end, freq="day")
    df.columns = cols
    return df.replace([np.inf, -np.inf], np.nan)


def month_end_dates(dates: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = pd.Series(dates, index=dates)
    return s.groupby([s.dt.year, s.dt.month]).max().sort_values().tolist()


# ---------- Strategy harness ----------

def run_strategy(
    name: str,
    score_fn,                      # callable(rebal_date) -> pd.Series of cross-sectional scores
    rebal_dates: list[pd.Timestamp],
    daily: pd.DataFrame,
    all_test_dates: pd.DatetimeIndex,
) -> dict:
    held: set[str] = set()
    daily_pnl: dict[pd.Timestamp, float] = {}
    monthly_log = []
    for i, rebal in enumerate(rebal_dates):
        next_rebal = rebal_dates[i + 1] if i + 1 < len(rebal_dates) else all_test_dates[-1]
        cross = score_fn(rebal)
        new_holdings = set(cross.nlargest(TOP_K).index.tolist()) if cross is not None and not cross.empty else held
        sells = held - new_holdings
        buys  = new_holdings - held
        cost_today = (len(sells) * COST_SELL_LEG + len(buys) * COST_BUY_LEG) / TOP_K
        held = new_holdings
        period_dates = all_test_dates[(all_test_dates > rebal) & (all_test_dates <= next_rebal)]
        period_rets = []
        for d in period_dates:
            try:
                day = daily.xs(d, level="datetime")
            except KeyError:
                continue
            avail = held & set(day.index)
            r = float(day.loc[list(avail), "ret"].mean()) if avail else 0.0
            daily_pnl[d] = r
            period_rets.append(r)
        if rebal in daily.index.get_level_values("datetime"):
            daily_pnl[rebal] = daily_pnl.get(rebal, 0.0) - cost_today
        elif period_dates.size:
            daily_pnl[period_dates[0]] -= cost_today
        gross = float(np.prod([1 + x for x in period_rets]) - 1) if period_rets else 0.0
        monthly_log.append({
            "rebal_date": rebal.strftime("%Y-%m-%d"),
            "n_buys": len(buys), "n_sells": len(sells),
            "turnover": len(buys) / TOP_K, "cost": cost_today,
            "gross": gross, "net": gross - cost_today,
        })

    s = pd.Series(daily_pnl).sort_index()
    return summarize(name, s, monthly_log)


def summarize(name: str, pnl: pd.Series, monthly_log: list[dict] | None = None) -> dict:
    if pnl.std() == 0 or len(pnl) == 0:
        return {"name": name, "cum_net": 0.0, "sharpe_net_ann": None, "max_dd": 0.0,
                "n_days": int(len(pnl)), "monthly_log": monthly_log or []}
    cum = float((1 + pnl).prod() - 1)
    sharpe = float(pnl.mean() / pnl.std() * np.sqrt(252))
    eq = (1 + pnl).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    total_cost = sum(r["cost"] for r in monthly_log) if monthly_log else 0.0
    avg_turn = float(np.mean([r["turnover"] for r in monthly_log])) if monthly_log else 0.0
    return {"name": name, "cum_net": cum, "sharpe_net_ann": sharpe, "max_dd": float(dd),
            "n_days": int(len(pnl)), "total_cost": total_cost,
            "avg_one_way_turnover": avg_turn, "monthly_log": monthly_log or []}


# ---------- Strategy 1: fixed-train LightGBM (matches F5) ----------

def build_fixed_train_lgb() -> "lgb.Booster":
    train = load_panel(TRAIN_START, FIXED_TRAIN_END).dropna()
    valid = load_panel(VALID_START, VALID_END).dropna()
    feat_cols = list(FACTORS.keys())
    ds_train = lgb.Dataset(train[feat_cols].values, label=train["label"].values)
    ds_valid = lgb.Dataset(valid[feat_cols].values, label=valid["label"].values, reference=ds_train)
    model = lgb.train(LGB_PARAMS, ds_train, num_boost_round=2000, valid_sets=[ds_valid],
                      callbacks=[lgb.early_stopping(50), lgb.log_evaluation(period=0)])
    print(f"  fixed LGB best_iter = {model.best_iteration}", flush=True)
    return model


# ---------- Strategy 2: walk-forward LightGBM ----------

def build_walk_forward_lgb(rebal_date: pd.Timestamp) -> "lgb.Booster":
    """Retrain on all data with observable label_end <= rebal_date.

    Forward-21d label means feature day t has observable label if t + 22 <= rebal_date,
    i.e. feature_date <= rebal_date - 22 trading days. Use calendar-22d cutoff
    (~30 calendar days) — close enough for monthly horizon.
    """
    label_cutoff = rebal_date - pd.Timedelta(days=30)
    panel = load_panel(TRAIN_START, label_cutoff.strftime("%Y-%m-%d")).dropna()
    # carve last 6 months as validation
    cut_valid = label_cutoff - pd.Timedelta(days=180)
    train = panel[panel.index.get_level_values("datetime") <= cut_valid]
    valid = panel[panel.index.get_level_values("datetime") >  cut_valid]
    if len(valid) < 1000 or len(train) < 5000:
        # not enough data — fall back to fixed model
        return None
    feat_cols = list(FACTORS.keys())
    ds_train = lgb.Dataset(train[feat_cols].values, label=train["label"].values)
    ds_valid = lgb.Dataset(valid[feat_cols].values, label=valid["label"].values, reference=ds_train)
    model = lgb.train(LGB_PARAMS, ds_train, num_boost_round=2000, valid_sets=[ds_valid],
                      callbacks=[lgb.early_stopping(50), lgb.log_evaluation(period=0)])
    return model


# ---------- Strategy 3: equal-weight z-score linear combo ----------

def build_linear_signs() -> dict[str, int]:
    """Learn per-factor sign on TRAIN segment using mean cross-sectional Rank IC."""
    train = load_panel(TRAIN_START, FIXED_TRAIN_END).dropna()
    by_date = train.groupby(level="datetime")
    signs = {}
    for f in FACTORS:
        ric = by_date.apply(lambda g: g[f].rank().corr(g["label"].rank()) if len(g) > 20 else np.nan).dropna()
        signs[f] = 1 if ric.mean() > 0 else -1
        print(f"  linear sign for {f}: {signs[f]} (train mean RankIC = {ric.mean():+.4f})", flush=True)
    return signs


# ---------- Main ----------

def main() -> None:
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)
    feat_cols = list(FACTORS.keys())

    print("Loading test features and daily returns ...", flush=True)
    test_feat = load_panel(TEST_START, TEST_END, with_label=False).dropna(subset=feat_cols)
    daily = D.features(D.instruments("csi300"), [DAILY_RET_EXPR],
                       start_time=TEST_START, end_time=TEST_END, freq="day")
    daily.columns = ["ret"]
    daily = daily.dropna()
    all_test_dates = pd.DatetimeIndex(sorted(set(daily.index.get_level_values("datetime"))))
    rebal_dates = month_end_dates(all_test_dates)
    if rebal_dates[0] != all_test_dates[0]:
        rebal_dates = [all_test_dates[0]] + rebal_dates
    print(f"  {len(all_test_dates)} trading days, {len(rebal_dates)} rebalances", flush=True)

    # -- Strategy 1: fixed-train LGB --
    print("\n[1/3] Training fixed-window LightGBM ...", flush=True)
    fixed = build_fixed_train_lgb()
    pred_fixed = pd.Series(fixed.predict(test_feat[feat_cols].values), index=test_feat.index, name="pred")

    def score_fixed(d):
        try: return pred_fixed.xs(d, level="datetime")
        except KeyError: return pd.Series(dtype=float)
    print("Running fixed-window strategy backtest ...", flush=True)
    res_fixed = run_strategy("fixed_lgb", score_fixed, rebal_dates, daily, all_test_dates)

    # -- Strategy 2: walk-forward LGB --
    print("\n[2/3] Running walk-forward LightGBM (retrain at every rebalance) ...", flush=True)
    pred_wf: dict[pd.Timestamp, pd.Series] = {}
    for d in rebal_dates:
        model = build_walk_forward_lgb(d)
        if model is None:
            print(f"  [{d.date()}] fallback to fixed model", flush=True)
            mdl = fixed
        else:
            print(f"  [{d.date()}] retrained, best_iter={model.best_iteration}", flush=True)
            mdl = model
        try:
            day_feat = test_feat.xs(d, level="datetime")
            pred_wf[d] = pd.Series(mdl.predict(day_feat[feat_cols].values), index=day_feat.index)
        except KeyError:
            pred_wf[d] = pd.Series(dtype=float)

    def score_wf(d):
        return pred_wf.get(d, pd.Series(dtype=float))
    res_wf = run_strategy("walk_forward_lgb", score_wf, rebal_dates, daily, all_test_dates)

    # -- Strategy 3: equal-weight z-score linear combo --
    print("\n[3/3] Building equal-weight z-score linear combo ...", flush=True)
    signs = build_linear_signs()

    # Cross-sectional z-score per (date, factor), then sum sign-flipped
    def zs_cross(df, col):
        g = df.groupby(level="datetime")[col]
        return (df[col] - g.transform("mean")) / g.transform("std").replace(0, np.nan)

    lin_scores = pd.Series(0.0, index=test_feat.index)
    for f in feat_cols:
        lin_scores = lin_scores + signs[f] * zs_cross(test_feat, f)
    lin_scores = lin_scores.dropna()

    def score_linear(d):
        try: return lin_scores.xs(d, level="datetime")
        except KeyError: return pd.Series(dtype=float)
    res_linear = run_strategy("equal_weight_linear", score_linear, rebal_dates, daily, all_test_dates)

    # -- Benchmark: CSI300 buy-and-hold over same test window --
    print("\nLoading CSI300 benchmark (SH000300) ...", flush=True)
    bench = D.features(["SH000300"], [DAILY_RET_EXPR],
                       start_time=TEST_START, end_time=TEST_END, freq="day")
    bench.columns = ["ret"]
    bench_pnl = bench["ret"].dropna().droplevel("instrument")
    res_bench = summarize("csi300_bench", bench_pnl)

    # -- Equal-weight 300 daily (no signal) baseline --
    eq_pnl = daily.groupby(level="datetime")["ret"].mean()
    res_eq = summarize("eq_weight_universe", eq_pnl)

    # -- Print comparison --
    print("\n" + "=" * 78, flush=True)
    print(f"  {'Strategy':<22s} {'CumNet':>8s} {'Sharpe':>7s} {'MaxDD':>7s} {'Turn/m':>7s} {'CostTot':>8s}", flush=True)
    print("-" * 78, flush=True)
    for r in [res_fixed, res_wf, res_linear, res_bench, res_eq]:
        cum = f"{r['cum_net']:+.2%}"
        sh  = f"{r['sharpe_net_ann']:+.2f}" if r.get('sharpe_net_ann') is not None else "  n/a"
        dd  = f"{r['max_dd']:.2%}"
        tn  = f"{r.get('avg_one_way_turnover', 0):.1%}" if r.get('avg_one_way_turnover') else "  --"
        ct  = f"{r.get('total_cost', 0):.2%}" if r.get('total_cost') else "   --"
        print(f"  {r['name']:<22s} {cum:>8s} {sh:>7s} {dd:>7s} {tn:>7s} {ct:>8s}", flush=True)
    print("=" * 78, flush=True)

    out = Path("D:/PM/jr/qlib_data/monthly_v2_results.json")
    payload = {
        "linear_signs": signs,
        "strategies": {r["name"]: {k: v for k, v in r.items() if k != "monthly_log"}
                        for r in [res_fixed, res_wf, res_linear, res_bench, res_eq]},
        "monthly_logs": {
            "fixed_lgb": res_fixed["monthly_log"],
            "walk_forward_lgb": res_wf["monthly_log"],
            "equal_weight_linear": res_linear["monthly_log"],
        },
    }
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nSaved -> {out}", flush=True)


if __name__ == "__main__":
    main()
