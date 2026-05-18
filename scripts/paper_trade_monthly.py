"""
F10 — monthly paper-trade orchestrator.

Each run:
  1. Build current-date portfolios from all strategies that survived
     backtest:
        - PathA_industry_lgb      (trained on full history, predicts today's top-50)
        - PathD_llm_industry      (LLM picks top-3 industries, top-K stocks each)
        - Ensemble                (intersection of A and D + extras from A)
  2. Save snapshots to paper_trades/portfolio_<YYYY-MM-DD>.json
  3. If a previous month's snapshot exists 25-45 days ago, evaluate it
     vs CSI300 and the equal-weight universe, append to evaluation.csv.

Designed to run monthly via /schedule or Windows Task Scheduler.
Repeatedly re-running on the same day overwrites that day's snapshots.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

for v in ("HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(v, None)

sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

PROJ = Path("D:/PM/jr")
PAPER_DIR = PROJ / "paper_trades"
PAPER_DIR.mkdir(parents=True, exist_ok=True)
EVAL_CSV = PAPER_DIR / "ensemble_evaluation.csv"
PYTHON = str(PROJ / ".venv/Scripts/python.exe")
TOP_K = 50

# Lazy import qlib in main since multiple scripts touch it
def build_path_a_holdings(today: str) -> list[str]:
    """Train PathA model on full history, predict for today, return top-K instruments."""
    sys.path.insert(0, str(PROJ / "src"))
    import qlib
    from qlib.constant import REG_CN
    from qlib.data import D
    import lightgbm as lgb

    qlib.init(provider_uri=str(PROJ / "qlib_data" / "cn_data"), region=REG_CN)

    # Reuse the v3 logic in line — copying minimal code rather than importing
    FACTORS = {
        "limit_up_reversal_20d":   "0 - Mean(Greater($close/Ref($close,1)-1, 0.095), 20)",
        "price_volume_divergence": "($volume - Mean($volume, 20)) / (Std($volume, 20) + 1e-8) * ($close/Ref($close,1) - 1)",
        "amihud_illiquidity_20d":  "Mean(Abs($close/Ref($close,1) - 1) / ($amount + 1e-8), 20)",
    }
    LABEL = "Ref($close, -22)/Ref($close, -1) - 1"

    stock_sw1 = pd.read_csv(PROJ / "qlib_data/stock_sw1.csv", dtype={"symbol": str, "sw1_code": str})
    stock_sw1 = stock_sw1.sort_values("join_date").drop_duplicates("symbol", keep="last")
    ind_map = dict(zip(stock_sw1["symbol"], stock_sw1["sw1_code"]))

    def short(s): return s[2:] if s.startswith(("SH","SZ")) else s

    def load(s, e, with_label=True):
        exprs = list(FACTORS.values()); cols = list(FACTORS.keys())
        if with_label: exprs.append(LABEL); cols.append("label")
        df = D.features(D.instruments("csi300"), exprs, start_time=s, end_time=e, freq="day")
        df.columns = cols
        df = df.replace([np.inf, -np.inf], np.nan)
        df["sw1"] = df.index.get_level_values("instrument").map(
            lambda x: ind_map.get(short(x), "999999"))
        for f in FACTORS:
            grp = df.groupby([df.index.get_level_values("datetime"), df["sw1"]])[f]
            df[f"{f}_rel"] = df[f] - grp.transform("mean")
        return df

    # FIXED train/valid window matching v3 (which beat the benchmark with best_iter=140).
    # Sliding the valid forward into a bull rally collapses best_iter to 1 because our
    # reversal factors lose grip in trending regimes. We hold this window until we have
    # a longer history including a regime switch — see memory: project-strategy-architecture.
    today_ts = pd.Timestamp(today)
    train_end = "2024-06-30"
    valid_start = "2024-07-01"
    valid_end = "2025-06-30"

    print(f"  PathA train 2018-01-01 -> {train_end}, valid {valid_start} -> {valid_end} (fixed)", flush=True)
    train = load("2018-01-01", train_end)
    valid = load(valid_start, valid_end)

    base = list(FACTORS.keys()); rel = [f"{f}_rel" for f in base]
    all_inds = sorted(set(train["sw1"]) | set(valid["sw1"]))
    ind2int = {c: i for i, c in enumerate(all_inds)}
    for df in (train, valid):
        df["sw1_cat"] = df["sw1"].map(ind2int).astype("int32")
    feat = base + rel + ["sw1_cat"]
    for df in (train, valid):
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
    train = train.dropna(subset=feat + ["label"])
    valid = valid.dropna(subset=feat + ["label"])
    cat_idx = [feat.index("sw1_cat")]
    ds_tr = lgb.Dataset(train[feat].values, label=train["label"].values, categorical_feature=cat_idx)
    ds_va = lgb.Dataset(valid[feat].values, label=valid["label"].values, reference=ds_tr,
                        categorical_feature=cat_idx)
    print("  PathA training LightGBM ...", flush=True)
    model = lgb.train(
        dict(objective="regression", metric="rmse", learning_rate=0.03,
             num_leaves=31, max_depth=6, min_data_in_leaf=200,
             feature_fraction=0.9, bagging_fraction=0.8, bagging_freq=5,
             lambda_l1=1.0, lambda_l2=10.0, verbose=-1),
        ds_tr, num_boost_round=2000, valid_sets=[ds_va],
        callbacks=[lgb.early_stopping(50), lgb.log_evaluation(period=0)])
    print(f"  PathA best_iter={model.best_iteration}", flush=True)

    # Score the latest day in test_feat (closest trading day to today)
    test_feat = load((today_ts - pd.Timedelta(days=60)).strftime("%Y-%m-%d"), today, with_label=False)
    test_feat["sw1_cat"] = test_feat["sw1"].map(ind2int).fillna(-1).astype("int32")
    test_feat = test_feat.replace([np.inf, -np.inf], np.nan).dropna(subset=feat)
    pred = pd.Series(model.predict(test_feat[feat].values), index=test_feat.index, name="pred")
    latest = pred.index.get_level_values("datetime").max()
    cross = pred.xs(latest, level="datetime")
    holdings = cross.nlargest(TOP_K).index.tolist()
    print(f"  PathA picked {len(holdings)} holdings as of {latest.date()}", flush=True)
    return holdings


def run_llm_picker(today: str) -> dict | None:
    """Invoke llm_industry_picker.py as a subprocess and read its output JSON."""
    print("  PathD launching llm_industry_picker.py ...", flush=True)
    sp_kwargs: dict = {}
    if sys.platform == "win32":
        sp_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    r = subprocess.run(
        [PYTHON, str(PROJ / "scripts/llm_industry_picker.py")],
        capture_output=True, text=True, encoding="utf-8", timeout=600,
        **sp_kwargs,
    )
    print(r.stdout[-2000:] if r.stdout else "")
    if r.returncode != 0:
        print(f"  PathD FAILED: rc={r.returncode}\n{r.stderr[-1000:]}", flush=True)
        return None
    out_path = PAPER_DIR / f"prediction_{today}.json"
    if not out_path.exists():
        print(f"  PathD output file missing: {out_path}", flush=True)
        return None
    return json.loads(out_path.read_text(encoding="utf-8"))


def evaluate_previous_snapshot(today: str) -> dict | None:
    """If a previous month's portfolio snapshot exists 25-45 days ago, evaluate it."""
    sys.path.insert(0, str(PROJ / "src"))
    import qlib
    from qlib.constant import REG_CN
    from qlib.data import D

    today_ts = pd.to_datetime(today)
    candidates = sorted(PAPER_DIR.glob("portfolio_*.json"))
    prev = None
    for p in candidates:
        try:
            d = pd.to_datetime(p.stem.replace("portfolio_", ""))
        except Exception:
            continue
        if d < today_ts and 25 <= (today_ts - d).days <= 45:
            prev = (p, d)
    if prev is None:
        return None
    pf_path, pf_date = prev
    pf = json.loads(pf_path.read_text(encoding="utf-8"))
    qlib.init(provider_uri=str(PROJ / "qlib_data" / "cn_data"), region=REG_CN)
    DAILY = "$close/Ref($close, 1) - 1"
    bench = D.features(["SH000300"], [DAILY],
                       start_time=pf_date.strftime("%Y-%m-%d"), end_time=today, freq="day")
    bench.columns = ["ret"]
    bench_cum = float((1 + bench["ret"].dropna().droplevel("instrument")).prod() - 1)

    out = {"prediction_date": str(pf_date.date()), "eval_date": today,
           "csi300_cum_ret": bench_cum}
    for strat_name in ("path_a", "path_d", "ensemble"):
        holdings = pf.get(strat_name, {}).get("holdings", [])
        if not holdings:
            out[f"{strat_name}_cum_ret"] = None
            continue
        rets = D.features(holdings, [DAILY], start_time=pf_date.strftime("%Y-%m-%d"),
                          end_time=today, freq="day")
        rets.columns = ["ret"]
        daily = rets.groupby(level="datetime")["ret"].mean()
        cum = float((1 + daily).prod() - 1)
        out[f"{strat_name}_cum_ret"] = cum
        out[f"{strat_name}_excess"] = cum - bench_cum
    return out


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n=========== PAPER-TRADE RUN — {today} ===========\n", flush=True)

    print("[1/3] Building PathA holdings (industry LGB) ...", flush=True)
    t0 = time.time()
    a_holdings = build_path_a_holdings(today)
    print(f"  PathA done ({time.time()-t0:.1f}s)\n", flush=True)

    print("[2/3] Running PathD (LLM industry picker) ...", flush=True)
    t0 = time.time()
    d_result = run_llm_picker(today)
    d_holdings = d_result.get("holdings", []) if d_result else []
    print(f"  PathD done ({time.time()-t0:.1f}s): {len(d_holdings)} holdings\n", flush=True)

    # Ensemble = intersection (overlap = strong consensus), pad with PathA extras
    print("[3/3] Building ensemble ...", flush=True)
    inter = list(set(a_holdings) & set(d_holdings))
    extras = [h for h in a_holdings if h not in inter][: TOP_K - len(inter)]
    ensemble = inter + extras
    print(f"  intersection size: {len(inter)}  ensemble size: {len(ensemble)}\n", flush=True)

    portfolio = {
        "date": today,
        "path_a": {"name": "industry_lgb_top50", "holdings": a_holdings},
        "path_d": {"name": "llm_industry_picks", "holdings": d_holdings,
                    "llm_picks": d_result.get("picks") if d_result else None,
                    "llm_macro": d_result.get("macro_view") if d_result else None},
        "ensemble": {"name": "intersect_padded_with_a", "intersection_size": len(inter),
                      "holdings": ensemble},
    }
    out = PAPER_DIR / f"portfolio_{today}.json"
    out.write_text(json.dumps(portfolio, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved -> {out}", flush=True)

    print("\nEvaluating previous month if available ...", flush=True)
    ev = evaluate_previous_snapshot(today)
    if ev is None:
        print("  no prior snapshot in [25, 45] days window", flush=True)
    else:
        print(f"  evaluation of {ev['prediction_date']}:", flush=True)
        for k, v in ev.items():
            if k in ("prediction_date", "eval_date"):
                print(f"    {k}: {v}")
            else:
                if v is None:
                    print(f"    {k}: n/a")
                else:
                    print(f"    {k}: {v:+.2%}")
        row = pd.DataFrame([ev])
        if EVAL_CSV.exists():
            old = pd.read_csv(EVAL_CSV)
            row = pd.concat([old, row], ignore_index=True)
        row.to_csv(EVAL_CSV, index=False)
        print(f"  appended to {EVAL_CSV}", flush=True)


if __name__ == "__main__":
    env = Path("D:/PM/jr/.env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    main()
