"""
F7 / Path B — industry-rotation overlay.

Two-stage selection:
  Stage 1: rank the 31 SW-1 industry indices by their own factor signal
           (built from index OHLCV), pick top-N industries each month.
  Stage 2: within those top-N industries, pick top-K stocks by the v3
           (stock-level + industry-relative) signal.

Industries are scored using the same three concepts but adapted:
  - 20d momentum reversal: take negative-sign of 20-day return
  - 20d realized vol z-score
  - 20d turnover z-score (proxy for "hot" rotation)

We sweep N (number of industries) in {3, 5, 8, 12, 15, 31=no-filter} to
see whether tightening the industry filter helps or hurts.

Output: D:/PM/jr/qlib_data/monthly_v4_results.json
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

QLIB_DIR = "D:/PM/jr/qlib_data/cn_data"
SW1_LIST  = "D:/PM/jr/qlib_data/sw1_list.csv"
SW1_DIR   = Path("D:/PM/jr/qlib_data/sw1_idx")
STOCK_SW1 = "D:/PM/jr/qlib_data/stock_sw1.csv"
TEST_START, TEST_END = "2025-07-01", "2026-05-13"
TOP_K = 50

COST_BUY_LEG  = 0.0003 + 0.0010
COST_SELL_LEG = 0.0003 + 0.0005 + 0.0010

DAILY_RET_EXPR = "$close/Ref($close, 1) - 1"

# Stock-level factors (reuse limit_up_reversal which has PBO=0.42)
STOCK_FACTOR = "0 - Mean(Greater($close/Ref($close,1)-1, 0.095), 30)"


def load_industry_map() -> dict[str, str]:
    df = pd.read_csv(STOCK_SW1, dtype={"symbol": str, "sw1_code": str})
    df["join_date"] = pd.to_datetime(df["join_date"], errors="coerce")
    df = df.sort_values("join_date").drop_duplicates("symbol", keep="last")
    return dict(zip(df["symbol"], df["sw1_code"]))


def load_sw1_panel() -> pd.DataFrame:
    """Stack all 31 SW-1 indices into one DataFrame indexed by (date, sw1_code)."""
    frames = []
    for p in SW1_DIR.glob("*.csv"):
        sw1 = p.stem
        df = pd.read_csv(p, encoding="utf-8-sig")
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.rename(columns={"日期": "date", "收盘": "close", "成交额": "amount",
                                  "成交量": "volume"})[["date", "close", "amount", "volume"]]
        df["sw1"] = sw1
        frames.append(df)
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.set_index(["date", "sw1"]).sort_index()
    return panel


def industry_rank_score(panel: pd.DataFrame) -> pd.Series:
    """Daily cross-sectional rank score across 31 industries.

    Composite: -momentum_20d + (-vol_20d zscore) + (-turnover_20d zscore)
    All three: tilt toward 'cool, low-vol, low-volume' industries (reversal-style).
    """
    panel = panel.copy()
    panel["ret"] = panel.groupby(level="sw1")["close"].pct_change()
    # 20d return
    panel["mom20"] = panel.groupby(level="sw1")["close"].pct_change(20)
    # 20d vol
    panel["vol20"] = panel.groupby(level="sw1")["ret"].transform(lambda s: s.rolling(20).std())
    # 20d turnover (use 成交额 sum as proxy)
    panel["turn20"] = panel.groupby(level="sw1")["amount"].transform(lambda s: s.rolling(20).sum())

    # Cross-sectionally z-score each day across the 31 industries
    by_date = panel.groupby(level="date")
    def zs(col):
        return (panel[col] - by_date[col].transform("mean")) / by_date[col].transform("std").replace(0, np.nan)

    # Reversal/cool/quiet: negate each
    score = -zs("mom20") - zs("vol20") - zs("turn20")
    return score


def month_end_dates(dates: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = pd.Series(dates, index=dates)
    return s.groupby([s.dt.year, s.dt.month]).max().sort_values().tolist()


def summarize(name, pnl, log=None):
    if len(pnl) == 0 or pnl.std() == 0:
        return {"name": name, "cum_net": 0.0, "sharpe": None, "max_dd": 0.0,
                "n_days": int(len(pnl)), "log": log or []}
    cum = float((1 + pnl).prod() - 1)
    sh = float(pnl.mean() / pnl.std() * np.sqrt(252))
    eq = (1 + pnl).cumprod()
    dd = float((eq / eq.cummax() - 1).min())
    tn = float(np.mean([r["turnover"] for r in log])) if log else 0.0
    return {"name": name, "cum_net": cum, "sharpe": sh, "max_dd": dd,
            "n_days": int(len(pnl)), "avg_turnover": tn, "log": log or []}


def main():
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)
    print("Loading industry index panel ...", flush=True)
    panel = load_sw1_panel()
    print(f"  industries: {panel.index.get_level_values('sw1').nunique()}, dates: {panel.index.get_level_values('date').nunique()}")

    print("Computing industry rotation scores ...", flush=True)
    ind_score = industry_rank_score(panel).dropna()
    # Restrict to test window
    ind_score = ind_score[ind_score.index.get_level_values("date") >= pd.Timestamp(TEST_START)]
    ind_score = ind_score[ind_score.index.get_level_values("date") <= pd.Timestamp(TEST_END)]
    print(f"  industry-score obs: {len(ind_score)}")

    ind_map = load_industry_map()

    # Stock factor
    print("Loading stock factor ...", flush=True)
    stock_panel = D.features(D.instruments("csi300"), [STOCK_FACTOR, DAILY_RET_EXPR],
                              start_time=TEST_START, end_time=TEST_END, freq="day")
    stock_panel.columns = ["factor", "ret"]
    stock_panel = stock_panel.replace([np.inf, -np.inf], np.nan)
    # Attach SW-1
    def short_sym(s): return s[2:] if s.startswith(("SH","SZ")) else s
    stock_panel["sw1"] = stock_panel.index.get_level_values("instrument").map(
        lambda s: ind_map.get(short_sym(s), "999999"))

    daily = stock_panel[["ret"]].dropna()
    all_test = pd.DatetimeIndex(sorted(set(daily.index.get_level_values("datetime"))))
    rebal = month_end_dates(all_test)
    if rebal[0] != all_test[0]:
        rebal = [all_test[0]] + rebal

    # Run for each N
    Ns = [3, 5, 8, 12, 15, 31]
    all_results = {}
    for N in Ns:
        held: set[str] = set()
        daily_pnl: dict[pd.Timestamp, float] = {}
        monthly_log = []
        for i, d in enumerate(rebal):
            next_d = rebal[i+1] if i+1 < len(rebal) else all_test[-1]
            # Industry top-N
            try:
                ind_cross = ind_score.xs(d, level="date")
                top_inds = set(ind_cross.nlargest(N).index)
            except KeyError:
                top_inds = set()
            # Stock cross — only in top_inds (or all if N==31)
            try:
                stock_cross = stock_panel.xs(d, level="datetime").dropna(subset=["factor"])
            except KeyError:
                stock_cross = pd.DataFrame()
            if N < 31 and len(top_inds) > 0:
                stock_cross = stock_cross[stock_cross["sw1"].isin(top_inds)]
            if not stock_cross.empty:
                new_h = set(stock_cross.nlargest(TOP_K, "factor").index)
            else:
                new_h = held
            sells, buys = held - new_h, new_h - held
            cost = (len(sells)*COST_SELL_LEG + len(buys)*COST_BUY_LEG) / TOP_K
            held = new_h
            period = all_test[(all_test > d) & (all_test <= next_d)]
            rs = []
            for dt in period:
                try:
                    day = daily.xs(dt, level="datetime")
                except KeyError:
                    continue
                avail = held & set(day.index)
                r = float(day.loc[list(avail), "ret"].mean()) if avail else 0.0
                daily_pnl[dt] = r
                rs.append(r)
            if d in daily.index.get_level_values("datetime"):
                daily_pnl[d] = daily_pnl.get(d, 0.0) - cost
            elif period.size:
                daily_pnl[period[0]] -= cost
            monthly_log.append({"rebal_date": d.strftime("%Y-%m-%d"),
                                "n_inds_picked": len(top_inds), "n_held": len(held),
                                "buys": len(buys), "sells": len(sells),
                                "turnover": len(buys)/TOP_K, "cost": cost,
                                "gross": float(np.prod([1+x for x in rs])-1) if rs else 0.0})
        s = pd.Series(daily_pnl).sort_index()
        res = summarize(f"top{N}_industries", s, monthly_log)
        all_results[N] = res
        sh = f"{res['sharpe']:+.2f}" if res['sharpe'] is not None else "n/a"
        print(f"  N={N:2d}: cum_net={res['cum_net']:+.2%}  Sharpe={sh}  DD={res['max_dd']:.2%}  turn={res['avg_turnover']:.1%}")

    # Benchmarks
    bench = D.features(["SH000300"], [DAILY_RET_EXPR], TEST_START, TEST_END, freq="day")
    bench.columns = ["ret"]
    res_bench = summarize("csi300_bench", bench["ret"].dropna().droplevel("instrument"))
    eq = daily.groupby(level="datetime")["ret"].mean()
    res_eq = summarize("eq_weight_universe", eq)

    print("\n" + "=" * 78)
    print(f"  {'Strategy':<24s} {'CumNet':>8s} {'Sharpe':>7s} {'MaxDD':>7s} {'Turn/m':>7s}")
    print("-" * 78)
    for r in [*all_results.values(), res_bench, res_eq]:
        sh = f"{r['sharpe']:+.2f}" if r.get('sharpe') is not None else "  n/a"
        tn = f"{r.get('avg_turnover', 0):.1%}" if r.get('avg_turnover') else "  --"
        print(f"  {r['name']:<24s} {r['cum_net']:+.2%}  {sh:>7s}  {r['max_dd']:.2%}  {tn:>7s}")
    print("=" * 78)

    out = Path("D:/PM/jr/qlib_data/monthly_v4_results.json")
    out.write_text(json.dumps({
        "by_top_N": {N: {k:v for k,v in r.items() if k != "log"} for N, r in all_results.items()},
        "benchmarks": {r["name"]: {k:v for k,v in r.items() if k != "log"} for r in [res_bench, res_eq]},
    }, indent=2, default=str))
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
