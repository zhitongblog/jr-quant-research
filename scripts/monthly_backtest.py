"""
F5: Monthly-rebalance backtest of the F3 three-factor LightGBM combo
with realistic A-share trading costs.

Universe:    csi300 (survivorship-corrected — Qlib instruments file is historical)
Signal:      LightGBM regression on three orthogonal alpha factors
             1. limit_up_reversal_20d
             2. price_volume_divergence
             3. amihud_illiquidity_20d
Train:       2018-01-01 -> 2024-06-30
Valid:       2024-07-01 -> 2025-06-30  (early stop)
Test:        2025-07-01 -> 2026-05-13

Strategy:    On the LAST trading day of each month, score the universe,
             pick top-K (default 50) by predicted next-month return, hold
             equal-weight for the whole next month.
Costs (one-way, both legs):
             buy  side: commission 0.03%
             sell side: commission 0.03% + stamp duty 0.05%
             slippage:  0.10% per leg
             => round-trip ~ 0.13% + 0.18% = 0.31% applied to the *traded* notional

Output (qlib_data/monthly_backtest_results.json):
  monthly returns, cumulative net curve, Sharpe (gross/net), max DD,
  monthly turnover series, annual cost drag.
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

# A-share realistic cost model (per leg, fraction)
COMMISSION_BUY  = 0.0003   # 0.03%
COMMISSION_SELL = 0.0003   # 0.03%
STAMP_DUTY_SELL = 0.0005   # 0.05%
SLIPPAGE_LEG    = 0.0010   # 0.10%
COST_BUY_LEG  = COMMISSION_BUY + SLIPPAGE_LEG                     # 0.13%
COST_SELL_LEG = COMMISSION_SELL + STAMP_DUTY_SELL + SLIPPAGE_LEG  # 0.18%

FACTORS = {
    "limit_up_reversal_20d":   "0 - Mean(Greater($close/Ref($close,1)-1, 0.095), 20)",
    "price_volume_divergence": "($volume - Mean($volume, 20)) / (Std($volume, 20) + 1e-8) * ($close/Ref($close,1) - 1)",
    "amihud_illiquidity_20d":  "Mean(Abs($close/Ref($close,1) - 1) / ($amount + 1e-8), 20)",
}

# Use monthly forward return as label (realised total return next ~21 trading days)
# Label: log return from Ref($close,-1) to Ref($close,-22)  ~ holding 21 days
LABEL_EXPR = "Ref($close, -22)/Ref($close, -1) - 1"
DAILY_RET_EXPR = "$close/Ref($close, 1) - 1"


def load_panel(start: str, end: str, with_label: bool = True) -> pd.DataFrame:
    exprs = list(FACTORS.values())
    cols  = list(FACTORS.keys())
    if with_label:
        exprs.append(LABEL_EXPR); cols.append("label")
    df = D.features(D.instruments("csi300"), exprs, start_time=start, end_time=end, freq="day")
    df.columns = cols
    df = df.replace([np.inf, -np.inf], np.nan)
    return df


def month_end_dates(dates: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Last available trading date of each (year, month) in the index."""
    s = pd.Series(dates, index=dates)
    return s.groupby([s.dt.year, s.dt.month]).max().sort_values().tolist()


def main() -> None:
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)
    print("Loading panels ...", flush=True)
    train = load_panel(TRAIN_START, TRAIN_END).dropna()
    valid = load_panel(VALID_START, VALID_END).dropna()
    test_features = load_panel(TEST_START, TEST_END, with_label=False).dropna(subset=list(FACTORS.keys()))
    # Daily returns over the FULL test segment for held-position P&L
    daily = D.features(D.instruments("csi300"), [DAILY_RET_EXPR],
                       start_time=TEST_START, end_time=TEST_END, freq="day")
    daily.columns = ["ret"]
    daily = daily.dropna()

    feat_cols = list(FACTORS.keys())
    print(f"  train {len(train):,} / valid {len(valid):,} / test_feat {len(test_features):,} / daily_ret {len(daily):,}", flush=True)

    # Train LightGBM with monthly forward-return label (low-capacity)
    train_set = lgb.Dataset(train[feat_cols].values, label=train["label"].values)
    valid_set = lgb.Dataset(valid[feat_cols].values, label=valid["label"].values, reference=train_set)
    params = dict(objective="regression", metric="rmse",
                  learning_rate=0.03, num_leaves=15, max_depth=4,
                  min_data_in_leaf=200, feature_fraction=1.0, bagging_fraction=0.8,
                  bagging_freq=5, lambda_l1=1.0, lambda_l2=10.0, verbose=-1)
    print("Training LightGBM on monthly-horizon label ...", flush=True)
    model = lgb.train(params, train_set, num_boost_round=2000, valid_sets=[valid_set],
                      callbacks=[lgb.early_stopping(50), lgb.log_evaluation(period=200)])
    print(f"  best_iter = {model.best_iteration}", flush=True)
    print(f"  feat_imp  = {dict(zip(feat_cols, model.feature_importance().tolist()))}", flush=True)

    # Score the test universe daily
    pred = pd.Series(model.predict(test_features[feat_cols].values),
                     index=test_features.index, name="pred")

    # Identify month-end rebalance dates
    all_test_dates = pd.DatetimeIndex(sorted(set(daily.index.get_level_values("datetime"))))
    rebal_dates = month_end_dates(all_test_dates)
    # Always include the start so first month has positions
    if rebal_dates[0] != all_test_dates[0]:
        rebal_dates = [all_test_dates[0]] + rebal_dates
    print(f"  rebalance dates ({len(rebal_dates)}): {[d.strftime('%Y-%m-%d') for d in rebal_dates]}", flush=True)

    # Walk through rebalance periods
    held: set[str] = set()
    daily_net_pnl: dict[pd.Timestamp, float] = {}
    monthly_log: list[dict] = []

    for i in range(len(rebal_dates)):
        rebal = rebal_dates[i]
        next_rebal = rebal_dates[i + 1] if i + 1 < len(rebal_dates) else all_test_dates[-1]

        # Build new top-K on the rebalance day's predictions
        try:
            cross = pred.xs(rebal, level="datetime")
        except KeyError:
            # signal missing for this date — skip rebalance (keep prior holdings)
            new_holdings = held
        else:
            new_holdings = set(cross.nlargest(TOP_K).index.tolist())

        sells = held - new_holdings
        buys = new_holdings - held
        # Turnover as fraction of portfolio (one-way)
        turnover_one_way = len(buys) / TOP_K if TOP_K else 0.0
        # Round-trip cost charged on the rebalance day:
        # sells: each sold leg ~ 1/K * COST_SELL_LEG ; buys: each ~ 1/K * COST_BUY_LEG
        cost_today = (len(sells) * COST_SELL_LEG + len(buys) * COST_BUY_LEG) / TOP_K

        held = new_holdings

        # Now run P&L through to next_rebal (inclusive of held days)
        period_dates = all_test_dates[(all_test_dates > rebal) & (all_test_dates <= next_rebal)]
        period_returns = []
        for d in period_dates:
            try:
                day = daily.xs(d, level="datetime")
            except KeyError:
                continue
            available = held & set(day.index)
            if not available:
                r = 0.0
            else:
                r = float(day.loc[list(available), "ret"].mean())
            daily_net_pnl[d] = r
            period_returns.append(r)

        # Apply rebalance cost on the rebalance day itself (or first held day if rebal isn't in daily)
        if rebal in daily.index.get_level_values("datetime"):
            daily_net_pnl[rebal] = daily_net_pnl.get(rebal, 0.0) - cost_today
        elif period_dates.size:
            daily_net_pnl[period_dates[0]] -= cost_today

        gross = float(np.prod([1 + x for x in period_returns]) - 1) if period_returns else 0.0
        net   = gross - cost_today
        monthly_log.append({
            "rebal_date": rebal.strftime("%Y-%m-%d"),
            "n_held": len(held), "n_buys": len(buys), "n_sells": len(sells),
            "turnover_one_way": turnover_one_way,
            "cost_drag": cost_today, "period_gross": gross, "period_net": net,
            "period_days": len(period_returns),
        })
        print(f"  [{rebal.strftime('%Y-%m-%d')}] held={len(held)} buys={len(buys)} sells={len(sells)} "
              f"turnover={turnover_one_way:.2%} cost={cost_today:.4%} gross={gross:+.2%} net={net:+.2%}",
              flush=True)

    # ---------- Aggregate stats ----------
    pnl_series = pd.Series(daily_net_pnl).sort_index()
    cum_net = float((1 + pnl_series).prod() - 1)
    sharpe_net = float(pnl_series.mean() / pnl_series.std() * np.sqrt(252)) if pnl_series.std() > 0 else None

    # Gross daily series for comparison (no cost applied)
    pnl_gross_series = pnl_series.copy()
    for row in monthly_log:
        d = pd.Timestamp(row["rebal_date"])
        if d in pnl_gross_series.index:
            pnl_gross_series.loc[d] += row["cost_drag"]
    cum_gross = float((1 + pnl_gross_series).prod() - 1)
    sharpe_gross = float(pnl_gross_series.mean() / pnl_gross_series.std() * np.sqrt(252)) if pnl_gross_series.std() > 0 else None

    # Max drawdown on net curve
    eq = (1 + pnl_series).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1.0
    max_dd = float(dd.min())

    total_cost = sum(r["cost_drag"] for r in monthly_log)
    avg_turnover = float(np.mean([r["turnover_one_way"] for r in monthly_log]))
    n_days = int(len(pnl_series))
    ann_cost_drag = total_cost * (252 / max(n_days, 1))

    print("\n=== MONTHLY-REBALANCE BACKTEST ===", flush=True)
    print(f"  trading days       : {n_days}", flush=True)
    print(f"  rebalances         : {len(monthly_log)}", flush=True)
    print(f"  avg one-way turnover/month : {avg_turnover:.2%}", flush=True)
    print(f"  total cost drag    : {total_cost:.2%}  (~{ann_cost_drag:.2%} annualised)", flush=True)
    print(f"  cumulative gross   : {cum_gross:+.2%}", flush=True)
    print(f"  cumulative net     : {cum_net:+.2%}", flush=True)
    print(f"  Sharpe gross (ann) : {sharpe_gross:+.2f}" if sharpe_gross is not None else "  Sharpe gross: n/a", flush=True)
    print(f"  Sharpe net   (ann) : {sharpe_net:+.2f}"   if sharpe_net   is not None else "  Sharpe net  : n/a", flush=True)
    print(f"  max drawdown (net) : {max_dd:.2%}", flush=True)

    out = Path("D:/PM/jr/qlib_data/monthly_backtest_results.json")
    out.write_text(json.dumps({
        "config": {
            "top_k": TOP_K, "train": [TRAIN_START, TRAIN_END],
            "valid": [VALID_START, VALID_END], "test": [TEST_START, TEST_END],
            "factors": FACTORS, "label_expr": LABEL_EXPR,
            "cost_buy_leg": COST_BUY_LEG, "cost_sell_leg": COST_SELL_LEG,
        },
        "summary": {
            "trading_days": n_days, "rebalances": len(monthly_log),
            "avg_one_way_turnover": avg_turnover,
            "total_cost_drag": total_cost, "annualised_cost_drag": ann_cost_drag,
            "cum_gross": cum_gross, "cum_net": cum_net,
            "sharpe_gross_ann": sharpe_gross, "sharpe_net_ann": sharpe_net,
            "max_dd_net": max_dd,
            "best_iter": int(model.best_iteration),
            "feature_importance": dict(zip(feat_cols, [int(x) for x in model.feature_importance()])),
        },
        "monthly_log": monthly_log,
        "daily_net_returns": {str(k.date()): float(v) for k, v in pnl_series.items()},
    }, indent=2))
    print(f"\nSaved -> {out}", flush=True)


if __name__ == "__main__":
    main()
