"""
F6 / Path A — monthly backtest with SW-1 industry features.

Adds to the v2 backtest:
  - Industry ID as a LightGBM categorical feature
  - Three industry-relative factors: `factor - industry_mean(factor)`
    (computed daily, cross-sectionally within the same industry on each day)

Goal: beat csi300 buy-and-hold (+26.99% Sharpe 2.00) and equal-weight
universe (+24.64% Sharpe 1.93) on the same 2025-07-01 to 2026-05-13 test
segment.

If this version still under-performs the benchmarks, the conclusion is that
SW-1 industry information alone doesn't fix the alpha problem in a strong
bull rally — we'd then need fundamentals (Path C) or industry rotation (B).

Output: qlib_data/monthly_v3_results.json + console comparison.
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
STOCK_SW1 = "D:/PM/jr/qlib_data/stock_sw1.csv"
TRAIN_START, TRAIN_END = "2018-01-01", "2024-06-30"
VALID_START, VALID_END = "2024-07-01", "2025-06-30"
TEST_START,  TEST_END  = "2025-07-01", "2026-05-13"
TOP_K = 50

COST_BUY_LEG  = 0.0003 + 0.0010
COST_SELL_LEG = 0.0003 + 0.0005 + 0.0010

FACTORS = {
    "limit_up_reversal_20d":   "0 - Mean(Greater($close/Ref($close,1)-1, 0.095), 20)",
    "price_volume_divergence": "($volume - Mean($volume, 20)) / (Std($volume, 20) + 1e-8) * ($close/Ref($close,1) - 1)",
    "amihud_illiquidity_20d":  "Mean(Abs($close/Ref($close,1) - 1) / ($amount + 1e-8), 20)",
}
LABEL_EXPR = "Ref($close, -22)/Ref($close, -1) - 1"
DAILY_RET_EXPR = "$close/Ref($close, 1) - 1"

LGB_PARAMS = dict(objective="regression", metric="rmse",
                  learning_rate=0.03, num_leaves=31, max_depth=6,
                  min_data_in_leaf=200, feature_fraction=0.9, bagging_fraction=0.8,
                  bagging_freq=5, lambda_l1=1.0, lambda_l2=10.0, verbose=-1)


def qlib_symbol_to_short(sym: str) -> str:
    """Convert SH600000 -> 600000."""
    return sym[2:] if sym.startswith(("SH", "SZ")) else sym


def load_industry_map() -> dict[str, str]:
    """symbol(6-digit) -> SW-1 code (6-digit, e.g. '801010').

    If a stock appears in multiple industries (rare history), keep the most
    recent join_date.
    """
    df = pd.read_csv(STOCK_SW1, dtype={"symbol": str, "sw1_code": str})
    df["join_date"] = pd.to_datetime(df["join_date"], errors="coerce")
    df = df.sort_values("join_date").drop_duplicates("symbol", keep="last")
    return dict(zip(df["symbol"], df["sw1_code"]))


def load_panel(start: str, end: str, with_label: bool = True,
               industry_map: dict[str, str] | None = None) -> pd.DataFrame:
    exprs = list(FACTORS.values())
    cols = list(FACTORS.keys())
    if with_label:
        exprs.append(LABEL_EXPR); cols.append("label")
    df = D.features(D.instruments("csi300"), exprs, start_time=start, end_time=end, freq="day")
    df.columns = cols
    df = df.replace([np.inf, -np.inf], np.nan)
    # Attach industry code
    if industry_map is not None:
        sym = df.index.get_level_values("instrument").map(
            lambda s: industry_map.get(qlib_symbol_to_short(s), "999999")
        )
        df["sw1"] = sym
        # Industry-relative factors: factor - daily industry mean
        for f in FACTORS:
            grp = df.groupby([df.index.get_level_values("datetime"), df["sw1"]])[f]
            df[f"{f}_rel"] = df[f] - grp.transform("mean")
    return df


def month_end_dates(dates: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = pd.Series(dates, index=dates)
    return s.groupby([s.dt.year, s.dt.month]).max().sort_values().tolist()


def run_strategy(name, score_fn, rebal_dates, daily, all_test_dates):
    held: set[str] = set()
    daily_pnl: dict[pd.Timestamp, float] = {}
    monthly_log = []
    for i, rebal in enumerate(rebal_dates):
        next_rebal = rebal_dates[i+1] if i+1 < len(rebal_dates) else all_test_dates[-1]
        cross = score_fn(rebal)
        new_h = set(cross.nlargest(TOP_K).index.tolist()) if cross is not None and not cross.empty else held
        sells, buys = held - new_h, new_h - held
        cost = (len(sells) * COST_SELL_LEG + len(buys) * COST_BUY_LEG) / TOP_K
        held = new_h
        period = all_test_dates[(all_test_dates > rebal) & (all_test_dates <= next_rebal)]
        rs = []
        for d in period:
            try:
                day = daily.xs(d, level="datetime")
            except KeyError:
                continue
            avail = held & set(day.index)
            r = float(day.loc[list(avail), "ret"].mean()) if avail else 0.0
            daily_pnl[d] = r
            rs.append(r)
        if rebal in daily.index.get_level_values("datetime"):
            daily_pnl[rebal] = daily_pnl.get(rebal, 0.0) - cost
        elif period.size:
            daily_pnl[period[0]] -= cost
        gross = float(np.prod([1+x for x in rs]) - 1) if rs else 0.0
        monthly_log.append({"rebal_date": rebal.strftime("%Y-%m-%d"),
                            "buys": len(buys), "sells": len(sells),
                            "turnover": len(buys)/TOP_K, "cost": cost,
                            "gross": gross, "net": gross-cost})
    s = pd.Series(daily_pnl).sort_index()
    return summarize(name, s, monthly_log)


def summarize(name, pnl, log=None):
    if len(pnl) == 0 or pnl.std() == 0:
        return {"name": name, "cum_net": 0.0, "sharpe": None, "max_dd": 0.0,
                "n_days": int(len(pnl)), "log": log or []}
    cum = float((1 + pnl).prod() - 1)
    sh = float(pnl.mean() / pnl.std() * np.sqrt(252))
    eq = (1 + pnl).cumprod()
    dd = float((eq / eq.cummax() - 1).min())
    cost = sum(r["cost"] for r in (log or []))
    tn = float(np.mean([r["turnover"] for r in log])) if log else 0.0
    return {"name": name, "cum_net": cum, "sharpe": sh, "max_dd": dd,
            "n_days": int(len(pnl)), "total_cost": cost, "avg_turnover": tn,
            "log": log or []}


def main():
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)
    print("Loading industry map ...", flush=True)
    ind_map = load_industry_map()
    print(f"  {len(ind_map)} symbol -> SW-1 mappings", flush=True)

    print("Loading train/valid panels with industry features ...", flush=True)
    train = load_panel(TRAIN_START, TRAIN_END, industry_map=ind_map).dropna(subset=list(FACTORS.keys()) + ["label"])
    valid = load_panel(VALID_START, VALID_END, industry_map=ind_map).dropna(subset=list(FACTORS.keys()) + ["label"])
    print(f"  train {len(train):,}  valid {len(valid):,}", flush=True)

    # Build feature matrix: 3 raw factors + 3 industry-relative + industry as categorical
    base_cols = list(FACTORS.keys())
    rel_cols = [f"{f}_rel" for f in base_cols]
    feat_cols = base_cols + rel_cols + ["sw1_cat"]

    # Industry code as integer categorical
    all_industries = sorted(set(train["sw1"]) | set(valid["sw1"]))
    ind2int = {c: i for i, c in enumerate(all_industries)}
    for df in (train, valid):
        df["sw1_cat"] = df["sw1"].map(ind2int).astype("int32")

    # Drop any rows missing relative features (industry of size 1 -> std=0 -> NaN won't happen actually, but inf can)
    for df in (train, valid):
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
    train = train.dropna(subset=feat_cols + ["label"])
    valid = valid.dropna(subset=feat_cols + ["label"])
    print(f"  after clean: train {len(train):,}  valid {len(valid):,}", flush=True)

    cat_idx = [feat_cols.index("sw1_cat")]
    ds_tr = lgb.Dataset(train[feat_cols].values, label=train["label"].values, categorical_feature=cat_idx)
    ds_va = lgb.Dataset(valid[feat_cols].values, label=valid["label"].values, reference=ds_tr,
                         categorical_feature=cat_idx)
    print("Training LightGBM (with industry features) ...", flush=True)
    model = lgb.train(LGB_PARAMS, ds_tr, num_boost_round=2000, valid_sets=[ds_va],
                      callbacks=[lgb.early_stopping(50), lgb.log_evaluation(period=200)])
    print(f"  best_iter = {model.best_iteration}", flush=True)
    imp = dict(zip(feat_cols, model.feature_importance().tolist()))
    print(f"  feature_importance = {imp}", flush=True)

    # Score test
    print("\nLoading test features (with industry) ...", flush=True)
    test_feat = load_panel(TEST_START, TEST_END, with_label=False, industry_map=ind_map)
    test_feat["sw1_cat"] = test_feat["sw1"].map(ind2int).fillna(-1).astype("int32")
    test_feat = test_feat.replace([np.inf, -np.inf], np.nan).dropna(subset=feat_cols)
    pred = pd.Series(model.predict(test_feat[feat_cols].values), index=test_feat.index, name="pred")

    daily = D.features(D.instruments("csi300"), [DAILY_RET_EXPR], TEST_START, TEST_END, freq="day")
    daily.columns = ["ret"]; daily = daily.dropna()
    all_test = pd.DatetimeIndex(sorted(set(daily.index.get_level_values("datetime"))))
    rebal = month_end_dates(all_test)
    if rebal[0] != all_test[0]:
        rebal = [all_test[0]] + rebal

    print(f"\nBacktest: {len(rebal)} rebalances over {len(all_test)} trading days", flush=True)
    def score(d):
        try: return pred.xs(d, level="datetime")
        except KeyError: return pd.Series(dtype=float)
    res_main = run_strategy("v3_industry_lgb", score, rebal, daily, all_test)

    # Benchmarks (same logic as v2)
    bench = D.features(["SH000300"], [DAILY_RET_EXPR], TEST_START, TEST_END, freq="day")
    bench.columns = ["ret"]
    res_bench = summarize("csi300_bench", bench["ret"].dropna().droplevel("instrument"))
    eq = daily.groupby(level="datetime")["ret"].mean()
    res_eq = summarize("eq_weight_universe", eq)

    print("\n" + "=" * 78)
    print(f"  {'Strategy':<24s} {'CumNet':>8s} {'Sharpe':>7s} {'MaxDD':>7s} {'Turn/m':>7s}")
    print("-" * 78)
    for r in [res_main, res_bench, res_eq]:
        sh = f"{r['sharpe']:+.2f}" if r.get('sharpe') is not None else "  n/a"
        tn = f"{r.get('avg_turnover', 0):.1%}" if r.get('avg_turnover') else "  --"
        print(f"  {r['name']:<24s} {r['cum_net']:+.2%}  {sh:>7s}  {r['max_dd']:.2%}  {tn:>7s}")
    print("=" * 78)

    out = Path("D:/PM/jr/qlib_data/monthly_v3_results.json")
    out.write_text(json.dumps({
        "best_iter": int(model.best_iteration),
        "feature_importance": imp,
        "strategies": {r["name"]: {k:v for k,v in r.items() if k != "log"}
                        for r in [res_main, res_bench, res_eq]},
        "monthly_log": res_main["log"],
    }, indent=2, default=str))
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
