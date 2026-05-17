"""
jr-dashboard FastAPI backend.

Serves data from D:/PM/jr/{qlib_data,paper_trades} to the Tauri frontend.

Endpoints:
  GET  /api/health
  GET  /api/portfolio/latest                  current paper-trade snapshot, with names
  GET  /api/portfolio/history                 list available portfolio dates
  GET  /api/portfolio/{date}                  specific portfolio + LLM details
  GET  /api/llm/latest                        latest LLM picks + macro view
  GET  /api/backtest/comparison               consolidated v2/v3/v4/v5 table
  GET  /api/performance/timeseries            ensemble_evaluation.csv parsed
  POST /api/run/monthly_update                trigger paper_trade_monthly.py (returns task_id)
  GET  /api/run/status/{task_id}              poll job status + tail of stdout
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import io
import numpy as np
import pandas as pd

PROJ = Path(os.environ.get("JR_PROJ_ROOT", "D:/PM/jr"))
QLIB = PROJ / "qlib_data"
CSV_DIR = QLIB / "csv"
PAPER = PROJ / "paper_trades"
SCRIPTS = PROJ / "scripts"
VENV_PY = PROJ / ".venv" / "Scripts" / "python.exe"

app = FastAPI(title="jr-dashboard API", version="0.1.0")
# Allow all localhost-ish origins. This API only binds to 127.0.0.1, so
# external machines can't reach it anyway — the wildcard is safe locally.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1|tauri\.localhost)(:\d+)?|tauri://localhost)$",
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


# --- helpers ---------------------------------------------------------------

def short(qlib_sym: str) -> str:
    return qlib_sym[2:] if qlib_sym.startswith(("SH", "SZ")) else qlib_sym


_stock_lookup_cache: dict[str, dict] | None = None
_sw1_lookup_cache: dict[str, str] | None = None


def stock_lookup() -> dict[str, dict]:
    """qlib instrument (SH600000) -> {name, sw1_code, sw1_name}."""
    global _stock_lookup_cache
    if _stock_lookup_cache is not None:
        return _stock_lookup_cache
    sw1_list_path = QLIB / "sw1_list.csv"
    stock_sw1_path = QLIB / "stock_sw1.csv"
    sw1_to_name: dict[str, str] = {}
    if sw1_list_path.exists():
        df = pd.read_csv(sw1_list_path, dtype={"行业代码": str})
        for _, r in df.iterrows():
            sw1_code = str(r["行业代码"]).replace(".SI", "")
            sw1_to_name[sw1_code] = r["行业名称"]
    lookup: dict[str, dict] = {}
    if stock_sw1_path.exists():
        df = pd.read_csv(stock_sw1_path, dtype={"symbol": str, "sw1_code": str})
        df["join_date"] = pd.to_datetime(df["join_date"], errors="coerce")
        df = df.sort_values("join_date").drop_duplicates("symbol", keep="last")
        for _, r in df.iterrows():
            sym = str(r["symbol"])
            sw1 = str(r["sw1_code"])
            prefix = "SH" if sym.startswith(("6", "9")) else "SZ"
            qlib_sym = f"{prefix}{sym}"
            lookup[qlib_sym] = {
                "symbol": sym, "name": str(r.get("name", "")),
                "sw1_code": sw1, "sw1_name": sw1_to_name.get(sw1, ""),
            }
    _stock_lookup_cache = lookup
    return lookup


def sw1_lookup() -> dict[str, str]:
    global _sw1_lookup_cache
    if _sw1_lookup_cache is not None:
        return _sw1_lookup_cache
    sw1_list_path = QLIB / "sw1_list.csv"
    out: dict[str, str] = {}
    if sw1_list_path.exists():
        df = pd.read_csv(sw1_list_path, dtype={"行业代码": str})
        for _, r in df.iterrows():
            code = str(r["行业代码"]).replace(".SI", "")
            out[code] = r["行业名称"]
    _sw1_lookup_cache = out
    return out


def enrich_holdings(holdings: list[str]) -> list[dict]:
    lookup = stock_lookup()
    out = []
    for h in holdings or []:
        info = lookup.get(h, {})
        out.append({
            "qlib_symbol": h,
            "symbol": info.get("symbol", short(h)),
            "name": info.get("name", ""),
            "sw1_code": info.get("sw1_code", ""),
            "sw1_name": info.get("sw1_name", ""),
        })
    return out


def list_portfolio_dates() -> list[str]:
    if not PAPER.exists():
        return []
    files = sorted(PAPER.glob("portfolio_*.json"))
    dates = []
    for p in files:
        m = re.match(r"portfolio_(\d{4}-\d{2}-\d{2})\.json", p.name)
        if m:
            dates.append(m.group(1))
    return dates


def list_prediction_dates() -> list[str]:
    if not PAPER.exists():
        return []
    files = sorted(PAPER.glob("prediction_*.json"))
    return [m.group(1) for f in files for m in [re.match(r"prediction_(\d{4}-\d{2}-\d{2})\.json", f.name)] if m]


# --- endpoints -------------------------------------------------------------

def _data_last_date() -> str | None:
    """Return latest date across a sample of CSV files (uses SH600000 as canary)."""
    sample = CSV_DIR / "sh600000.csv"
    if not sample.exists():
        return None
    try:
        df = pd.read_csv(sample, usecols=["date"], parse_dates=["date"])
        return df["date"].max().strftime("%Y-%m-%d")
    except Exception:
        return None


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "proj_root": str(PROJ),
        "qlib_data_exists": QLIB.exists(),
        "paper_trades_exists": PAPER.exists(),
        "n_portfolios": len(list_portfolio_dates()),
        "n_predictions": len(list_prediction_dates()),
        "data_last_date": _data_last_date(),
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/api/portfolio/latest")
def portfolio_latest():
    dates = list_portfolio_dates()
    if not dates:
        raise HTTPException(404, "no portfolio snapshots found")
    return portfolio_by_date(dates[-1])


@app.get("/api/portfolio/history")
def portfolio_history():
    dates = list_portfolio_dates()
    return {"dates": dates}


@app.get("/api/portfolio/{date}")
def portfolio_by_date(date: str):
    p = PAPER / f"portfolio_{date}.json"
    if not p.exists():
        raise HTTPException(404, f"portfolio_{date}.json not found")
    raw = json.loads(p.read_text(encoding="utf-8"))
    out = {
        "date": raw.get("date", date),
        "path_a": {
            "name": raw.get("path_a", {}).get("name", ""),
            "holdings": enrich_holdings(raw.get("path_a", {}).get("holdings", [])),
        },
        "path_d": {
            "name": raw.get("path_d", {}).get("name", ""),
            "holdings": enrich_holdings(raw.get("path_d", {}).get("holdings", [])),
            "llm_picks": raw.get("path_d", {}).get("llm_picks") or [],
            "llm_macro": raw.get("path_d", {}).get("llm_macro") or "",
        },
        "ensemble": {
            "name": raw.get("ensemble", {}).get("name", ""),
            "intersection_size": raw.get("ensemble", {}).get("intersection_size", 0),
            "holdings": enrich_holdings(raw.get("ensemble", {}).get("holdings", [])),
        },
    }
    # Resolve LLM industry codes to names
    sw1 = sw1_lookup()
    for pick in out["path_d"]["llm_picks"]:
        code = str(pick.get("sw1_code", ""))
        pick.setdefault("sw1_name", sw1.get(code, pick.get("sw1_name", "")))
    return out


@app.get("/api/llm/latest")
def llm_latest():
    files = sorted(PAPER.glob("prediction_*.json"))
    if not files:
        raise HTTPException(404, "no LLM predictions found")
    raw = json.loads(files[-1].read_text(encoding="utf-8"))
    return {
        "date": raw.get("date", ""),
        "backend": raw.get("backend", ""),
        "model": raw.get("model", ""),
        "elapsed_s": raw.get("elapsed_s", 0),
        "picks": raw.get("picks", []),
        "macro_view": raw.get("macro_view", ""),
        "n_holdings": len(raw.get("holdings", [])),
    }


@app.get("/api/backtest/comparison")
def backtest_comparison():
    rows = []
    # v2 (no industry, baseline)
    p = QLIB / "monthly_v2_results.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        for name, s in d.get("strategies", {}).items():
            rows.append({"version": "v2", "name": name,
                         "cum_net": s.get("cum_net"), "sharpe": s.get("sharpe_net_ann"),
                         "max_dd": s.get("max_dd")})
    # v3 (industry features)
    p = QLIB / "monthly_v3_results.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        for name, s in d.get("strategies", {}).items():
            rows.append({"version": "v3", "name": name,
                         "cum_net": s.get("cum_net"), "sharpe": s.get("sharpe"),
                         "max_dd": s.get("max_dd")})
    # v4 (industry rotation)
    p = QLIB / "monthly_v4_results.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        for n, s in d.get("by_top_N", {}).items():
            rows.append({"version": "v4", "name": s.get("name", f"top{n}"),
                         "cum_net": s.get("cum_net"), "sharpe": s.get("sharpe"),
                         "max_dd": s.get("max_dd")})
        for s in d.get("benchmarks", {}).values():
            rows.append({"version": "v4", "name": s.get("name", "bench"),
                         "cum_net": s.get("cum_net"), "sharpe": s.get("sharpe"),
                         "max_dd": s.get("max_dd")})
    # v5 (fundamentals)
    p = QLIB / "monthly_v5_results.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        for name, s in d.get("strategies", {}).items():
            rows.append({"version": "v5", "name": name,
                         "cum_net": s.get("cum_net"), "sharpe": s.get("sharpe"),
                         "max_dd": s.get("max_dd")})
    return {"rows": rows}


@app.get("/api/performance/timeseries")
def performance_timeseries():
    csv = PAPER / "ensemble_evaluation.csv"
    if not csv.exists():
        return {"rows": [], "message": "no monthly evaluation data yet — paper-trading starts now"}
    df = pd.read_csv(csv)
    return {"rows": df.to_dict(orient="records")}


# --- per-stock detail ------------------------------------------------------

def csv_path_for(qlib_symbol: str) -> Path:
    """SH600000 -> qlib_data/csv/sh600000.csv (lowercase)."""
    return CSV_DIR / f"{qlib_symbol.lower()}.csv"


def load_daily(qlib_symbol: str, days: int | None = None) -> pd.DataFrame | None:
    p = csv_path_for(qlib_symbol)
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p, parse_dates=["date"])
    except Exception:
        return None
    df = df.sort_values("date").reset_index(drop=True)
    if days is not None and days > 0:
        df = df.tail(days).reset_index(drop=True)
    return df


def compute_factor_latest(df: pd.DataFrame) -> dict | None:
    """Compute the three alpha factors for the LATEST available row in df."""
    if df is None or len(df) < 25:
        return None
    d = df.copy()
    d["ret1"] = d["close"] / d["close"].shift(1) - 1
    # limit_up_reversal_20d: 0 - Mean(Greater(ret1, 0.095), 20)
    lu_clipped = d["ret1"].clip(lower=0.095)
    d["limit_up_reversal_20d"] = -lu_clipped.rolling(20).mean()
    # price_volume_divergence
    vol_mean = d["volume"].rolling(20).mean()
    vol_std = d["volume"].rolling(20).std()
    d["price_volume_divergence"] = (d["volume"] - vol_mean) / (vol_std + 1e-8) * d["ret1"]
    # amihud_illiquidity_20d
    amihud_raw = d["ret1"].abs() / (d["amount"].abs() + 1e-8)
    d["amihud_illiquidity_20d"] = amihud_raw.rolling(20).mean()
    last = d.iloc[-1]
    return {
        "as_of": str(last["date"].date()),
        "close": float(last["close"]),
        "volume": float(last["volume"]),
        "amount": float(last["amount"]),
        "ret_1d": float(last["ret1"]) if pd.notna(last["ret1"]) else None,
        "limit_up_reversal_20d": float(last["limit_up_reversal_20d"]) if pd.notna(last["limit_up_reversal_20d"]) else None,
        "price_volume_divergence": float(last["price_volume_divergence"]) if pd.notna(last["price_volume_divergence"]) else None,
        "amihud_illiquidity_20d": float(last["amihud_illiquidity_20d"]) if pd.notna(last["amihud_illiquidity_20d"]) else None,
    }


def compute_industry_factor_table(sw1_code: str) -> pd.DataFrame:
    """Compute latest factor values for every stock in a SW-1 industry that has a CSV."""
    lookup = stock_lookup()
    syms = [s for s, info in lookup.items() if info.get("sw1_code") == sw1_code]
    rows = []
    for s in syms:
        df = load_daily(s, days=60)
        f = compute_factor_latest(df)
        if f is None:
            continue
        rows.append({
            "qlib_symbol": s,
            "symbol": lookup[s]["symbol"],
            "name": lookup[s]["name"],
            "close": f["close"],
            "ret_1d": f["ret_1d"],
            "limit_up_reversal_20d": f["limit_up_reversal_20d"],
            "price_volume_divergence": f["price_volume_divergence"],
            "amihud_illiquidity_20d": f["amihud_illiquidity_20d"],
        })
    return pd.DataFrame(rows)


@app.get("/api/stock/{symbol}")
def stock_detail(symbol: str, peers: int = 8):
    info = stock_lookup().get(symbol)
    if not info:
        raise HTTPException(404, f"unknown symbol {symbol}")
    df = load_daily(symbol, days=60)
    if df is None:
        raise HTTPException(404, f"no CSV for {symbol}")
    self_factors = compute_factor_latest(df)

    # Industry peers
    sw1 = info.get("sw1_code") or ""
    ind_df = compute_industry_factor_table(sw1) if sw1 else pd.DataFrame()

    # Industry-relative factors + ranks
    rel: dict = {}
    rank: dict = {}
    for fcol in ("limit_up_reversal_20d", "price_volume_divergence", "amihud_illiquidity_20d"):
        if ind_df.empty or fcol not in ind_df.columns:
            continue
        vals = ind_df[fcol].dropna()
        if vals.empty or self_factors is None or self_factors.get(fcol) is None:
            continue
        mean = float(vals.mean())
        rel[fcol] = self_factors[fcol] - mean
        # Rank: 1 = highest factor value
        sorted_syms = ind_df.dropna(subset=[fcol]).sort_values(fcol, ascending=False)["qlib_symbol"].tolist()
        rank[fcol] = {
            "rank": sorted_syms.index(symbol) + 1 if symbol in sorted_syms else None,
            "total": len(sorted_syms),
            "industry_mean": mean,
        }

    # Top peers: by combined ranking on limit_up_reversal_rel + (-amihud) + price_volume_divergence
    peer_table = []
    if not ind_df.empty:
        ind_df_calc = ind_df.copy()
        for fcol in ("limit_up_reversal_20d", "price_volume_divergence", "amihud_illiquidity_20d"):
            ind_df_calc[f"{fcol}_z"] = (ind_df_calc[fcol] - ind_df_calc[fcol].mean()) / (ind_df_calc[fcol].std() + 1e-8)
        ind_df_calc["combo"] = (
            ind_df_calc["limit_up_reversal_20d_z"]
            + ind_df_calc["price_volume_divergence_z"]
            - ind_df_calc["amihud_illiquidity_20d_z"]
        )
        ind_df_calc = ind_df_calc.sort_values("combo", ascending=False)
        peer_table = ind_df_calc.head(peers).to_dict(orient="records")

    return {
        "info": info,
        "factors_latest": self_factors,
        "industry_relative": rel,
        "industry_rank": rank,
        "industry_size": 0 if ind_df.empty else len(ind_df),
        "peers": peer_table,
    }


@app.get("/api/prices/latest")
def prices_latest(symbols: str):
    """Batch latest price + name for a comma-separated list of qlib symbols.

    Returns rows in the same order as requested; missing symbols get a null
    `close` so the caller can still display the row.
    """
    lookup = stock_lookup()
    out = []
    for s in [x.strip() for x in symbols.split(",") if x.strip()]:
        info = lookup.get(s, {"symbol": short(s), "name": "", "sw1_code": "", "sw1_name": ""})
        df = load_daily(s, days=2)
        close = float(df["close"].iloc[-1]) if df is not None and len(df) else None
        out.append({
            "qlib_symbol": s,
            "symbol": info["symbol"],
            "name": info["name"],
            "sw1_name": info["sw1_name"],
            "close": close,
        })
    return {"rows": out}


@app.get("/api/etf/comparison")
def etf_comparison(days: int = 252):
    """Compare a hypothetical investment in CSI300 ETF (SH510300) and the
    CSI300 buy-and-hold index over the last `days` trading days.

    Returns daily cumulative returns for the period so the frontend can
    render an apples-to-apples chart against the paper portfolio.
    """
    targets = {
        "csi300_index": "SH000300",  # we already have this CSV (data source)
        # 510300 ETF would be ideal but we don't have its CSV — index is the
        # closest proxy (the ETF tracks 000300 within ~0.5% annual drag).
    }
    out: dict = {"rows": [], "etf_drag_assumption_annual": 0.005}
    for label, sym in targets.items():
        df = load_daily(sym, days=days + 1)
        if df is None or len(df) < 2:
            continue
        df = df.sort_values("date").reset_index(drop=True)
        df["ret"] = df["close"] / df["close"].iloc[0] - 1
        rows = []
        for _, r in df.iterrows():
            rows.append({"date": str(r["date"].date()), "cum_ret": float(r["ret"])})
        out[label] = rows
    return out


@app.get("/api/stock/{symbol}/prices")
def stock_prices(symbol: str, days: int = 120):
    info = stock_lookup().get(symbol)
    if not info:
        raise HTTPException(404, f"unknown symbol {symbol}")
    df = load_daily(symbol, days=days)
    if df is None:
        raise HTTPException(404, f"no CSV for {symbol}")
    df["ret1"] = df["close"] / df["close"].shift(1) - 1
    df["limit_up"] = (df["ret1"] >= 0.095).astype(int)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "date": str(r["date"].date()),
            "open": float(r["open"]),
            "close": float(r["close"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "volume": float(r["volume"]),
            "amount": float(r["amount"]),
            "ret1": float(r["ret1"]) if pd.notna(r["ret1"]) else None,
            "limit_up": bool(r["limit_up"]),
        })
    return {"info": info, "rows": rows}


# --- my-trades CRUD --------------------------------------------------------

TRADES_FILE = PAPER / "my_trades.jsonl"


class TradeIn(BaseModel):
    trade_date: str          # YYYY-MM-DD
    qlib_symbol: str         # e.g. SH600000
    side: str                # "buy" | "sell"
    shares: int
    price: float
    fee: float = 0.0
    note: str = ""


def trades_load() -> list[dict]:
    if not TRADES_FILE.exists():
        return []
    out = []
    for line in TRADES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def trades_save(rows: list[dict]) -> None:
    PAPER.mkdir(parents=True, exist_ok=True)
    TRADES_FILE.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
        encoding="utf-8",
    )


def _enrich_trade(t: TradeIn, trade_id: str | None = None) -> dict:
    info = stock_lookup().get(t.qlib_symbol, {})
    return {
        "id": trade_id or uuid.uuid4().hex[:12],
        "trade_date": t.trade_date,
        "qlib_symbol": t.qlib_symbol,
        "symbol": info.get("symbol", short(t.qlib_symbol)),
        "name": info.get("name", ""),
        "sw1_code": info.get("sw1_code", ""),
        "sw1_name": info.get("sw1_name", ""),
        "side": t.side.lower(),
        "shares": int(t.shares),
        "price": float(t.price),
        "fee": float(t.fee),
        "note": t.note,
        "amount": int(t.shares) * float(t.price),
    }


@app.get("/api/trades")
def trades_list():
    rows = trades_load()
    rows.sort(key=lambda r: (r.get("trade_date", ""), r.get("id", "")), reverse=True)
    return {"rows": rows, "count": len(rows)}


@app.post("/api/trades")
def trades_add(trade: TradeIn):
    if trade.side.lower() not in ("buy", "sell"):
        raise HTTPException(400, "side must be buy or sell")
    if trade.shares <= 0:
        raise HTTPException(400, "shares must be > 0")
    rows = trades_load()
    row = _enrich_trade(trade)
    rows.append(row)
    trades_save(rows)
    return row


@app.put("/api/trades/{trade_id}")
def trades_update(trade_id: str, trade: TradeIn):
    rows = trades_load()
    for i, r in enumerate(rows):
        if r.get("id") == trade_id:
            rows[i] = _enrich_trade(trade, trade_id=trade_id)
            trades_save(rows)
            return rows[i]
    raise HTTPException(404, "trade not found")


@app.delete("/api/trades/{trade_id}")
def trades_delete(trade_id: str):
    rows = trades_load()
    new_rows = [r for r in rows if r.get("id") != trade_id]
    if len(new_rows) == len(rows):
        raise HTTPException(404, "trade not found")
    trades_save(new_rows)
    return {"deleted": trade_id}


# --- positions + P&L from trade log ---------------------------------------

@app.get("/api/trades/positions")
def trades_positions():
    rows = trades_load()
    # Aggregate by qlib_symbol (FIFO simplification: use weighted avg cost)
    by_sym: dict[str, dict] = {}
    sorted_rows = sorted(rows, key=lambda r: r.get("trade_date", ""))
    realized_total = 0.0
    for r in sorted_rows:
        sym = r["qlib_symbol"]
        if sym not in by_sym:
            by_sym[sym] = {
                "qlib_symbol": sym, "symbol": r["symbol"], "name": r["name"],
                "sw1_name": r["sw1_name"],
                "shares": 0, "cost_basis": 0.0, "realized_pnl": 0.0,
            }
        pos = by_sym[sym]
        if r["side"] == "buy":
            pos["cost_basis"] += r["shares"] * r["price"] + r.get("fee", 0)
            pos["shares"] += r["shares"]
        else:  # sell
            if pos["shares"] <= 0:
                continue
            avg_cost = pos["cost_basis"] / max(pos["shares"], 1)
            sold = min(r["shares"], pos["shares"])
            realized = sold * (r["price"] - avg_cost) - r.get("fee", 0)
            pos["realized_pnl"] += realized
            realized_total += realized
            pos["cost_basis"] -= sold * avg_cost
            pos["shares"] -= sold

    # Current prices
    syms_active = [s for s, p in by_sym.items() if p["shares"] > 0]
    prices: dict[str, float | None] = {}
    for s in syms_active:
        df = load_daily(s, days=2)
        prices[s] = float(df["close"].iloc[-1]) if df is not None and len(df) else None

    out_active = []
    total_market = 0.0
    total_cost = 0.0
    unrealized_total = 0.0
    for s, p in by_sym.items():
        if p["shares"] <= 0:
            continue
        px = prices.get(s)
        market = (px * p["shares"]) if px else None
        avg_cost = p["cost_basis"] / max(p["shares"], 1)
        unrealized = (market - p["cost_basis"]) if market is not None else None
        out_active.append({
            **p,
            "avg_cost": avg_cost,
            "current_price": px,
            "market_value": market,
            "unrealized_pnl": unrealized,
            "pnl_pct": (unrealized / p["cost_basis"]) if (unrealized is not None and p["cost_basis"] > 0) else None,
        })
        total_cost += p["cost_basis"]
        if market is not None:
            total_market += market
            unrealized_total += unrealized or 0.0

    out_active.sort(key=lambda p: -(p.get("market_value") or 0))
    return {
        "positions": out_active,
        "summary": {
            "n_positions": len(out_active),
            "total_cost_basis": total_cost,
            "total_market_value": total_market,
            "unrealized_pnl": unrealized_total,
            "realized_pnl": realized_total,
            "total_pnl": unrealized_total + realized_total,
            "pnl_pct": (unrealized_total + realized_total) / total_cost if total_cost > 0 else None,
        },
    }


# --- CSV import -----------------------------------------------------------

HEADER_ALIASES = {
    "trade_date": ["成交日期", "委托日期", "日期", "时间"],
    "symbol":     ["证券代码", "股票代码", "代码"],
    "name":       ["证券名称", "股票名称", "名称"],
    "side":       ["买卖标志", "买卖方向", "操作", "委托类型", "买卖"],
    "price":      ["成交价格", "成交价", "委托价格", "价格"],
    "shares":     ["成交数量", "委托数量", "数量", "股数"],
    "amount":     ["成交金额", "金额"],
    "fee":        ["手续费", "佣金", "费用"],
}


def _detect_encoding(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "utf-8"


def _find_col(headers: list[str], aliases: list[str]) -> str | None:
    for h in headers:
        for alias in aliases:
            if alias in str(h):
                return h
    return None


def _parse_side(value) -> str | None:
    s = str(value).lower()
    if any(t in s for t in ("买", "buy", " b ", "申购")): return "buy"
    if any(t in s for t in ("卖", "sell", " s ", "赎回")): return "sell"
    return None


def _short_to_qlib(symbol: str) -> str:
    s = str(symbol).strip().zfill(6)
    # SH: 6xxxxx, 9xxxxx; SZ: 0xxxxx, 3xxxxx
    if s.startswith(("6", "9")): return f"SH{s}"
    return f"SZ{s}"


@app.post("/api/trades/import")
async def trades_import(file: UploadFile = File(...), commit: bool = False):
    """Parse CSV broker export. Returns preview unless commit=true.

    Auto-detects encoding (UTF-8 / GBK) and column layout via fuzzy header match.
    """
    raw = await file.read()
    enc = _detect_encoding(raw)
    try:
        df = pd.read_csv(io.BytesIO(raw), encoding=enc)
    except Exception:
        # Some brokers export tab-separated as .csv
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=enc, sep="\t")
        except Exception as e:
            raise HTTPException(400, f"无法解析 CSV: {e}")

    headers = list(df.columns)
    col_map = {k: _find_col(headers, v) for k, v in HEADER_ALIASES.items()}
    required = ["trade_date", "symbol", "side", "price", "shares"]
    missing = [k for k in required if col_map[k] is None]
    if missing:
        return {
            "ok": False,
            "encoding": enc,
            "headers": headers,
            "column_mapping": col_map,
            "error": f"缺失关键列: {missing}（识别到的列名见 headers）",
        }

    parsed: list[dict] = []
    errors: list[dict] = []
    for idx, row in df.iterrows():
        try:
            side = _parse_side(row[col_map["side"]])
            if side is None:
                errors.append({"row": int(idx), "reason": f"无法识别买卖方向: {row[col_map['side']]}"})
                continue
            sym_raw = str(row[col_map["symbol"]]).strip().split(".")[0]
            digits = "".join(c for c in sym_raw if c.isdigit())
            if not digits:
                errors.append({"row": int(idx), "reason": "代码无数字"})
                continue
            date_str = pd.to_datetime(row[col_map["trade_date"]]).strftime("%Y-%m-%d")
            shares = int(float(row[col_map["shares"]]))
            price = float(row[col_map["price"]])
            fee = float(row[col_map["fee"]]) if col_map["fee"] else 0.0
            if shares <= 0 or price <= 0:
                errors.append({"row": int(idx), "reason": "数量或价格非正"})
                continue
            parsed.append(TradeIn(
                trade_date=date_str,
                qlib_symbol=_short_to_qlib(digits),
                side=side,
                shares=shares,
                price=price,
                fee=fee,
                note=f"imported from {file.filename}",
            ).model_dump())
        except Exception as e:
            errors.append({"row": int(idx), "reason": str(e)[:100]})

    preview = [
        {**_enrich_trade(TradeIn(**p)), "id": f"preview-{i}"}
        for i, p in enumerate(parsed)
    ]

    if commit and parsed:
        existing = trades_load()
        for p in parsed:
            existing.append(_enrich_trade(TradeIn(**p)))
        trades_save(existing)

    return {
        "ok": True,
        "encoding": enc,
        "filename": file.filename,
        "column_mapping": col_map,
        "n_parsed": len(parsed),
        "n_errors": len(errors),
        "errors": errors[:50],
        "preview": preview[:50],
        "committed": commit,
    }


# --- stock search for autocomplete ----------------------------------------

@app.get("/api/stocks/search")
def stocks_search(q: str, limit: int = 20):
    """Match by 6-digit symbol prefix OR substring of name (Chinese)."""
    q = (q or "").strip()
    if not q:
        return {"rows": []}
    lookup = stock_lookup()
    rows = []
    q_lower = q.lower()
    for qlib_sym, info in lookup.items():
        sym = info.get("symbol", "")
        name = info.get("name", "")
        if (q in sym) or (q_lower in qlib_sym.lower()) or (q in name):
            rows.append({
                "qlib_symbol": qlib_sym,
                "symbol": sym,
                "name": name,
                "sw1_name": info.get("sw1_name", ""),
            })
            if len(rows) >= limit:
                break
    return {"rows": rows}


# --- news cache + context -------------------------------------------------

NEWS_CACHE_FILE = PAPER / "news_cache.json"
NEWS_CONTEXT_FILE = PAPER / "news_context.txt"


@app.get("/api/news/recent")
def news_recent(limit: int = 30):
    """Return cached news items. Use POST /api/news/refresh to update."""
    if not NEWS_CACHE_FILE.exists():
        return {
            "refreshed_at": None,
            "n_items": 0,
            "items": [],
            "message": "尚未拉过新闻。点击刷新按钮（首次需 30-60 秒）。",
        }
    try:
        cache = json.loads(NEWS_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"读取 news_cache.json 失败: {e}")
    items = cache.get("items", [])
    return {
        "refreshed_at": cache.get("refreshed_at"),
        "days_back": cache.get("days_back"),
        "by_source": cache.get("by_source", {}),
        "n_items": len(items),
        "items": items[:limit],
    }


class NewsContextIn(BaseModel):
    text: str


@app.get("/api/news/context")
def news_context_get():
    if not NEWS_CONTEXT_FILE.exists():
        return {"text": ""}
    return {"text": NEWS_CONTEXT_FILE.read_text(encoding="utf-8")}


@app.post("/api/news/context")
def news_context_set(body: NewsContextIn):
    PAPER.mkdir(parents=True, exist_ok=True)
    NEWS_CONTEXT_FILE.write_text(body.text or "", encoding="utf-8")
    return {"ok": True, "n_chars": len(body.text or "")}


@app.post("/api/news/refresh")
async def news_refresh():
    """Spawn scripts/refresh_news.py and return a task_id to poll."""
    task_id = uuid.uuid4().hex[:12]
    JOBS[task_id] = {"status": "pending", "log": [], "command": "refresh_news.py"}
    cmd = [str(VENV_PY), str(SCRIPTS / "refresh_news.py")]
    asyncio.get_event_loop().run_in_executor(None, _run_subprocess, task_id, cmd)
    return {"task_id": task_id, "status": "pending"}


# --- secrets (DeepSeek API key etc.) --------------------------------------

SECRETS_FILE = PAPER / "secrets.json"


def _load_secrets() -> dict:
    if not SECRETS_FILE.exists():
        return {}
    try:
        return json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_secrets(d: dict) -> None:
    PAPER.mkdir(parents=True, exist_ok=True)
    SECRETS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _secrets_to_env() -> dict:
    """Translate secrets file into the env-var names the scripts expect."""
    s = _load_secrets()
    env: dict[str, str] = {}
    if s.get("deepseek_api_key"):
        env["DEEPSEEK_API_KEY"] = s["deepseek_api_key"]
    if s.get("deepseek_model"):
        env["DEEPSEEK_MODEL"] = s["deepseek_model"]
    if s.get("deepseek_api_base"):
        env["DEEPSEEK_API_BASE"] = s["deepseek_api_base"]
    return env


class DeepseekSecretIn(BaseModel):
    api_key: str
    model: str = "deepseek-v4-pro"
    api_base: str = "https://api.deepseek.com"


@app.get("/api/secrets/status")
def secrets_status():
    s = _load_secrets()
    key = s.get("deepseek_api_key", "")
    return {
        "deepseek_set": bool(key),
        "deepseek_key_preview": (key[:6] + "..." + key[-4:]) if len(key) > 12 else "",
        "deepseek_model": s.get("deepseek_model", ""),
        "deepseek_api_base": s.get("deepseek_api_base", ""),
    }


@app.post("/api/secrets/deepseek")
def secrets_deepseek_set(body: DeepseekSecretIn):
    if not body.api_key.startswith("sk-"):
        raise HTTPException(400, "DeepSeek API key should start with sk-")
    s = _load_secrets()
    s["deepseek_api_key"] = body.api_key
    s["deepseek_model"] = body.model
    s["deepseek_api_base"] = body.api_base
    _save_secrets(s)
    return {"ok": True}


@app.delete("/api/secrets/deepseek")
def secrets_deepseek_clear():
    s = _load_secrets()
    for k in ("deepseek_api_key", "deepseek_model", "deepseek_api_base"):
        s.pop(k, None)
    _save_secrets(s)
    return {"ok": True}


# --- run-job orchestration -------------------------------------------------

# In-process job registry. Resets when API restarts (acceptable — jobs are
# minutes long, persistence not required).
JOBS: dict[str, dict] = {}


def _run_subprocess(task_id: str, cmd: list[str]) -> None:
    job = JOBS[task_id]
    job["status"] = "running"
    job["started_at"] = time.time()
    env = os.environ.copy()
    env.update(_secrets_to_env())  # inject DEEPSEEK_API_KEY etc. from secrets.json
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                bufsize=1, text=True, encoding="utf-8", errors="replace",
                                env=env)
        for line in proc.stdout:
            job["log"].append(line.rstrip())
            # keep log bounded to last 500 lines
            if len(job["log"]) > 500:
                job["log"] = job["log"][-500:]
        rc = proc.wait()
        job["status"] = "completed" if rc == 0 else "failed"
        job["return_code"] = rc
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        job["ended_at"] = time.time()


@app.post("/api/run/monthly_update")
async def run_monthly_update():
    task_id = uuid.uuid4().hex[:12]
    JOBS[task_id] = {"status": "pending", "log": [], "command": "paper_trade_monthly.py"}
    cmd = [str(VENV_PY), str(SCRIPTS / "paper_trade_monthly.py")]
    asyncio.get_event_loop().run_in_executor(None, _run_subprocess, task_id, cmd)
    return {"task_id": task_id, "status": "pending"}


@app.get("/api/run/status/{task_id}")
def run_status(task_id: str):
    job = JOBS.get(task_id)
    if not job:
        raise HTTPException(404, "no such job")
    return {
        "task_id": task_id,
        "status": job["status"],
        "command": job.get("command"),
        "tail": job["log"][-50:],
        "n_lines": len(job["log"]),
        "started_at": job.get("started_at"),
        "ended_at": job.get("ended_at"),
        "return_code": job.get("return_code"),
        "error": job.get("error"),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("JR_API_PORT", "8765"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
