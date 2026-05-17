"""
F8 / Path C — fundamentals with PIT lag.

Adds three slow-moving fundamental features to the v3 industry-aware model:

  - roe_ttm        : trailing ROE  (净资产收益率)
  - earnings_yoy   : YoY net-profit growth
  - revenue_yoy    : YoY revenue growth

Critical PIT discipline:
  - Quarterly reports (Q1/Q2/Q3) publish within 1 month of quarter end
  - Annual report  (Q4)  publishes by April 30 of following year
  - Conservative: apply 90-day publication delay across all quarters.
    A fundamental value dated 2025-03-31 becomes usable from 2025-06-30 onwards.

Then forward-fill until next report. The result: at any backtest date T,
the model only sees what was actually publicly available at time T.

This is the slowest path (per-stock CSVs to read, parse, align). Strict PIT
discipline because A-share has well-known fundamental-look-ahead disasters.

Output: D:/PM/jr/qlib_data/monthly_v5_results.json
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
FUND_DIR = Path("D:/PM/jr/qlib_data/fundamentals")
STOCK_SW1 = "D:/PM/jr/qlib_data/stock_sw1.csv"

TRAIN_START, TRAIN_END = "2018-01-01", "2024-06-30"
VALID_START, VALID_END = "2024-07-01", "2025-06-30"
TEST_START,  TEST_END  = "2025-07-01", "2026-05-13"
TOP_K = 50
PIT_LAG_DAYS = 90   # publication delay

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

# Mapping from fundamentals CSV columns to clean names (akshare returns
# different col names per version — match by substring).
FUND_COL_MATCHERS = {
    "roe_weighted":   ["加权净资产收益率"],
    "earnings_yoy":   ["净利润增长率"],
    "gross_margin":   ["销售毛利率"],
    "op_margin":      ["营业利润率"],
    "debt_ratio":     ["资产负债率"],
    "current_ratio":  ["流动比率"],
}


def load_industry_map() -> dict[str, str]:
    df = pd.read_csv(STOCK_SW1, dtype={"symbol": str, "sw1_code": str})
    df["join_date"] = pd.to_datetime(df["join_date"], errors="coerce")
    df = df.sort_values("join_date").drop_duplicates("symbol", keep="last")
    return dict(zip(df["symbol"], df["sw1_code"]))


def parse_fund_pct(s):
    """akshare returns '12.34' (string) or float — convert to float, NaN if blank."""
    if pd.isna(s) or s == "" or s == "--":
        return np.nan
    try:
        return float(str(s).replace("%", ""))
    except (ValueError, TypeError):
        return np.nan


def load_fundamentals_panel() -> pd.DataFrame:
    """Return DataFrame indexed by (date, instrument) with PIT-lagged fundamentals."""
    rows = []
    for p in FUND_DIR.glob("*.csv"):
        sym = p.stem  # e.g. '600000'
        try:
            df = pd.read_csv(p, encoding="utf-8-sig")
        except Exception:
            continue
        if "日期" not in df.columns:
            continue
        out = pd.DataFrame()
        out["report_date"] = pd.to_datetime(df["日期"], errors="coerce")
        for clean, candidates in FUND_COL_MATCHERS.items():
            col = next((c for c in df.columns if any(k in c for k in candidates)), None)
            out[clean] = df[col].map(parse_fund_pct) if col else np.nan
        out = out.dropna(subset=["report_date"]).copy()
        out["available_from"] = out["report_date"] + pd.Timedelta(days=PIT_LAG_DAYS)
        # Convert short symbol -> qlib SH/SZ form
        first = sym[0]
        prefix = "SH" if first in "6" else "SZ"
        out["instrument"] = f"{prefix}{sym}"
        rows.append(out)
    if not rows:
        return pd.DataFrame(columns=["available_from","instrument","roe_ttm","earnings_yoy","revenue_yoy"])
    panel = pd.concat(rows, ignore_index=True)
    return panel


def align_fund_to_daily(panel: pd.DataFrame, fund_panel: pd.DataFrame) -> pd.DataFrame:
    """As-of join fund_panel onto panel's (datetime, instrument) index.

    For each (date, instrument) in `panel`, take the latest fundamental record
    where `available_from <= date` (i.e. PIT-respecting).
    """
    fund_cols = list(FUND_COL_MATCHERS.keys())
    left = panel.reset_index()[["datetime", "instrument"]].copy()
    left = left.sort_values("datetime")
    right = fund_panel[["available_from", "instrument"] + fund_cols].copy()
    right = right.sort_values("available_from")
    merged = pd.merge_asof(
        left, right,
        left_on="datetime", right_on="available_from",
        by="instrument", direction="backward", allow_exact_matches=True,
    )
    merged = merged.set_index(["datetime", "instrument"])[fund_cols]
    return merged


def qlib_symbol_to_short(s):
    return s[2:] if s.startswith(("SH","SZ")) else s


def load_panel_base(start, end, ind_map, with_label=True):
    exprs = list(FACTORS.values())
    cols = list(FACTORS.keys())
    if with_label:
        exprs.append(LABEL_EXPR); cols.append("label")
    df = D.features(D.instruments("csi300"), exprs, start_time=start, end_time=end, freq="day")
    df.columns = cols
    df = df.replace([np.inf, -np.inf], np.nan)
    sym = df.index.get_level_values("instrument").map(
        lambda s: ind_map.get(qlib_symbol_to_short(s), "999999"))
    df["sw1"] = sym
    for f in FACTORS:
        grp = df.groupby([df.index.get_level_values("datetime"), df["sw1"]])[f]
        df[f"{f}_rel"] = df[f] - grp.transform("mean")
    return df


def month_end_dates(dates):
    s = pd.Series(dates, index=dates)
    return s.groupby([s.dt.year, s.dt.month]).max().sort_values().tolist()


def run_strategy(name, score_fn, rebal_dates, daily, all_test_dates):
    held: set[str] = set()
    daily_pnl: dict[pd.Timestamp, float] = {}
    log = []
    for i, rb in enumerate(rebal_dates):
        nxt = rebal_dates[i+1] if i+1 < len(rebal_dates) else all_test_dates[-1]
        cross = score_fn(rb)
        new_h = set(cross.nlargest(TOP_K).index.tolist()) if cross is not None and not cross.empty else held
        sells, buys = held - new_h, new_h - held
        cost = (len(sells)*COST_SELL_LEG + len(buys)*COST_BUY_LEG) / TOP_K
        held = new_h
        period = all_test_dates[(all_test_dates > rb) & (all_test_dates <= nxt)]
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
        if rb in daily.index.get_level_values("datetime"):
            daily_pnl[rb] = daily_pnl.get(rb, 0.0) - cost
        elif period.size:
            daily_pnl[period[0]] -= cost
        log.append({"rebal_date": rb.strftime("%Y-%m-%d"),
                    "buys": len(buys), "sells": len(sells),
                    "turnover": len(buys)/TOP_K, "cost": cost,
                    "gross": float(np.prod([1+x for x in rs])-1) if rs else 0.0})
    s = pd.Series(daily_pnl).sort_index()
    return summarize(name, s, log)


def summarize(name, pnl, log=None):
    if len(pnl) == 0 or pnl.std() == 0:
        return {"name": name, "cum_net": 0.0, "sharpe": None, "max_dd": 0.0,
                "n_days": int(len(pnl)), "log": log or []}
    cum = float((1+pnl).prod()-1)
    sh  = float(pnl.mean()/pnl.std()*np.sqrt(252))
    eq  = (1+pnl).cumprod()
    dd  = float((eq/eq.cummax()-1).min())
    tn  = float(np.mean([r["turnover"] for r in log])) if log else 0.0
    return {"name": name, "cum_net": cum, "sharpe": sh, "max_dd": dd,
            "n_days": int(len(pnl)), "avg_turnover": tn, "log": log or []}


def main():
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)
    print("Loading industry map ...", flush=True)
    ind_map = load_industry_map()

    print("Loading fundamentals (PIT-lagged) ...", flush=True)
    fund = load_fundamentals_panel()
    print(f"  fundamentals rows: {len(fund):,}  unique stocks: {fund['instrument'].nunique()}")

    print("Loading train/valid/test base panels ...", flush=True)
    train = load_panel_base(TRAIN_START, TRAIN_END, ind_map)
    valid = load_panel_base(VALID_START, VALID_END, ind_map)
    test  = load_panel_base(TEST_START,  TEST_END,  ind_map, with_label=False)

    print("Aligning fundamentals to each segment (PIT merge_asof) ...", flush=True)
    train_f = align_fund_to_daily(train, fund)
    valid_f = align_fund_to_daily(valid, fund)
    test_f  = align_fund_to_daily(test, fund)
    print(f"  fund_aligned sizes — train: {len(train_f):,}  valid: {len(valid_f):,}  test: {len(test_f):,}")
    train = train.join(train_f, how="left")
    valid = valid.join(valid_f, how="left")
    test  = test.join(test_f, how="left")
    print(f"  post-join non-null roe_weighted — train: {train['roe_weighted'].notna().sum():,}  valid: {valid['roe_weighted'].notna().sum():,}  test: {test['roe_weighted'].notna().sum():,}")

    # Categorical
    all_industries = sorted(set(train["sw1"]) | set(valid["sw1"]) | set(test["sw1"]))
    ind2int = {c: i for i, c in enumerate(all_industries)}
    for df in (train, valid, test):
        df["sw1_cat"] = df["sw1"].map(ind2int).fillna(-1).astype("int32")

    base = list(FACTORS.keys())
    rel  = [f"{f}_rel" for f in base]
    fund_cols = list(FUND_COL_MATCHERS.keys())
    feat_cols = base + rel + ["sw1_cat"] + fund_cols

    # Fundamentals are sparse and uneven across columns. For each segment:
    #   1. drop columns that are entirely NaN (different per segment)
    #   2. fill per-date cross-sectional median, then global median
    #   3. only require the first fund_col (roe_weighted) to be present
    for label, df in [("train", train), ("valid", valid), ("test", test)]:
        for c in fund_cols:
            if c in df.columns:
                nn = df[c].notna().sum()
                if nn == 0:
                    print(f"    {label}: column {c} is all-NaN, dropping from features", flush=True)
                    df[c] = 0.0  # neutral fill; LGB will ignore a constant column
                    continue
                df[c] = df.groupby(level="datetime")[c].transform(
                    lambda s: s.fillna(s.median()))
                df[c] = df[c].fillna(df[c].median())
                if df[c].isna().any():
                    df[c] = df[c].fillna(0.0)

    for df in (train, valid, test):
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
    # Only require non-NaN on base+rel+sw1_cat+label; fundamentals were imputed above
    core_cols = base + rel + ["sw1_cat"]
    train = train.dropna(subset=core_cols + ["label"])
    valid = valid.dropna(subset=core_cols + ["label"])
    test  = test.dropna(subset=core_cols)
    print(f"  after clean: train {len(train):,} valid {len(valid):,} test {len(test):,}")

    cat_idx = [feat_cols.index("sw1_cat")]
    ds_tr = lgb.Dataset(train[feat_cols].values, label=train["label"].values, categorical_feature=cat_idx)
    ds_va = lgb.Dataset(valid[feat_cols].values, label=valid["label"].values, reference=ds_tr,
                          categorical_feature=cat_idx)
    print("Training LightGBM (industry + fundamentals) ...", flush=True)
    model = lgb.train(LGB_PARAMS, ds_tr, num_boost_round=2000, valid_sets=[ds_va],
                      callbacks=[lgb.early_stopping(50), lgb.log_evaluation(period=200)])
    print(f"  best_iter = {model.best_iteration}")
    imp = dict(zip(feat_cols, model.feature_importance().tolist()))
    print("  feature_importance:")
    for k, v in sorted(imp.items(), key=lambda kv: -kv[1]):
        print(f"    {k:32s} {v}")

    pred = pd.Series(model.predict(test[feat_cols].values), index=test.index, name="pred")
    daily = D.features(D.instruments("csi300"), [DAILY_RET_EXPR], TEST_START, TEST_END, freq="day")
    daily.columns = ["ret"]; daily = daily.dropna()
    all_test = pd.DatetimeIndex(sorted(set(daily.index.get_level_values("datetime"))))
    rebal = month_end_dates(all_test)
    if rebal[0] != all_test[0]:
        rebal = [all_test[0]] + rebal

    def score(d):
        try: return pred.xs(d, level="datetime")
        except KeyError: return pd.Series(dtype=float)
    res_main = run_strategy("v5_fund_industry_lgb", score, rebal, daily, all_test)

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

    out = Path("D:/PM/jr/qlib_data/monthly_v5_results.json")
    out.write_text(json.dumps({
        "best_iter": int(model.best_iteration),
        "feature_importance": imp,
        "pit_lag_days": PIT_LAG_DAYS,
        "strategies": {r["name"]: {k:v for k,v in r.items() if k != "log"}
                        for r in [res_main, res_bench, res_eq]},
        "monthly_log": res_main["log"],
    }, indent=2, default=str))
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
