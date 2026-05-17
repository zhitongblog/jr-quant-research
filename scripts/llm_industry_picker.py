"""
F9 / Path D — monthly LLM industry analysis for forward paper-trading.

How it works (forward only — no historical backtest possible without
point-in-time news archive):

  1. Each run, fetch a snapshot of current month's industry context:
     - SW-1 industry list with PE/PB/dividend (already on disk)
     - Recent 30d performance for each industry
     - Top news headlines per industry (akshare news API; best-effort)
  2. Build a prompt asking the LLM to identify the 3 industries most
     likely to outperform over the next month and rationale.
  3. Persist prediction + portfolio (top-K stocks within those industries
     by limit_up_reversal_20d_rel) to paper_trades/<YYYY-MM-DD>.json.
  4. Each subsequent run also evaluates the previous month's prediction
     and appends to paper_trades/evaluation.csv.

Designed to be scheduled monthly (e.g. via /schedule or Windows Task Scheduler).
Idempotent within a calendar month — re-running on the same day overwrites
that day's prediction.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

for v in ("HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(v, None)

sys.path.insert(0, "D:/PM/jr/src")
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import qlib
from qlib.constant import REG_CN
from qlib.data import D
import httpx

QLIB_DIR = "D:/PM/jr/qlib_data/cn_data"
PAPER_DIR = Path("D:/PM/jr/paper_trades")
PAPER_DIR.mkdir(parents=True, exist_ok=True)
EVAL_CSV = PAPER_DIR / "evaluation.csv"

SW1_LIST_CSV = "D:/PM/jr/qlib_data/sw1_list.csv"
SW1_IDX_DIR  = Path("D:/PM/jr/qlib_data/sw1_idx")
STOCK_SW1_CSV = "D:/PM/jr/qlib_data/stock_sw1.csv"

TOP_INDUSTRIES = 3
STOCKS_PER_INDUSTRY = 17   # 3 industries * ~17 stocks = ~50 total
DAILY_RET_EXPR = "$close/Ref($close, 1) - 1"
STOCK_FACTOR = "0 - Mean(Greater($close/Ref($close,1)-1, 0.095), 20)"

# LLM config — prefer DeepSeek API; fall back to Ollama Qwen
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5-coder:14b"


SYSTEM_PROMPT = """You are an A-share macro & industry analyst.
You will be given:
  - The full list of 31 申万 Level-1 industries with current valuation snapshots
  - 30-day price performance of each industry index

Your job: pick the 3 industries most likely to OUTPERFORM the CSI300 over the
NEXT MONTH (approximately 20 trading days). Use macro / sector rotation logic.

Reply with EXACTLY a JSON object, no prose, no markdown fences:
{
  "picks": [
    {"sw1_code": "801xxx", "sw1_name": "<chinese name>", "rationale": "<1-2 sentence reason>"},
    ...3 entries...
  ],
  "macro_view": "<2-3 sentences on the broader market regime>"
}
"""


def load_industry_snapshot() -> pd.DataFrame:
    """Industry-level table: code, name, PE_TTM, PB, dividend, recent return."""
    sw1 = pd.read_csv(SW1_LIST_CSV, dtype={"行业代码": str})
    # Normalize code
    sw1["sw1"] = sw1["行业代码"].str.replace(".SI", "", regex=False)
    sw1["name"] = sw1["行业名称"]
    sw1["pe_ttm"] = sw1["TTM(滚动)市盈率"]
    sw1["pb"] = sw1["市净率"]
    sw1["dividend"] = sw1["静态股息率"]

    # Recent 30d return per industry
    today = datetime.now()
    rets = []
    for sym in sw1["sw1"]:
        p = SW1_IDX_DIR / f"{sym}.csv"
        if not p.exists():
            rets.append(np.nan); continue
        df = pd.read_csv(p, encoding="utf-8-sig")
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.sort_values("日期").tail(31)
        if len(df) < 2:
            rets.append(np.nan); continue
        rets.append(float(df["收盘"].iloc[-1] / df["收盘"].iloc[0] - 1))
    sw1["ret_30d"] = rets
    return sw1[["sw1", "name", "pe_ttm", "pb", "dividend", "ret_30d"]]


def load_news_section(max_items: int = 25, max_user_chars: int = 2000) -> str:
    """Build the news/macro context section of the LLM prompt.

    Sources, in order of precedence:
      1. User-supplied free-text (paper_trades/news_context.txt) — always included
      2. Cached aggregated news (paper_trades/news_cache.json from refresh_news.py)
    """
    parts: list[str] = []

    user_ctx_file = PAPER_DIR / "news_context.txt"
    if user_ctx_file.exists():
        ctx = user_ctx_file.read_text(encoding="utf-8").strip()
        if ctx:
            parts.append("用户提供的近期消息摘要（最重要、优先参考）:")
            parts.append(ctx[:max_user_chars])
            parts.append("")

    cache_file = PAPER_DIR / "news_cache.json"
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
            items = cache.get("items", [])
            if items:
                refreshed = cache.get("refreshed_at", "")
                parts.append(f"自动聚合新闻摘要（最近 {cache.get('days_back', '?')} 天 · 截止 {refreshed[:10]}）:")
                for it in items[:max_items]:
                    src = it.get("source", "")
                    date = it.get("date", "") or "?"
                    title = (it.get("title", "") or "").strip()
                    summary = (it.get("summary", "") or "").strip()
                    if not title and not summary:
                        continue
                    line = f"  [{date} {src}] {title}"
                    if summary:
                        line += f" — {summary[:120]}"
                    parts.append(line)
                parts.append("")
        except Exception:
            pass

    return "\n".join(parts) if parts else ""


def build_prompt(snap: pd.DataFrame) -> str:
    rows = []
    for _, r in snap.iterrows():
        rt = f"{r['ret_30d']*100:+.1f}%" if pd.notna(r['ret_30d']) else "n/a"
        rows.append(f"  {r['sw1']}  {r['name']:<8s}  PE={r['pe_ttm']:>6}  PB={r['pb']:>5}  div={r['dividend']:>5}  ret30d={rt}")
    table = "\n".join(rows)
    today = datetime.now().strftime("%Y-%m-%d")
    news_section = load_news_section()
    news_block = f"\n{news_section}\n" if news_section else "\n"
    return f"""Today is {today}.
{news_block}
申万一级行业当前状况：
代码      行业        PE_TTM     PB     股息率   近30日涨幅
{table}

基于上面的当前估值、近期表现，以及（如有）新闻/政策上下文，
挑出未来一个月最有可能跑赢沪深300的 3 个行业。
Reply with valid JSON ONLY (no prose, no fences). Field structure as specified."""


def call_llm(user_msg: str) -> dict:
    """Try DeepSeek API first; fall back to Ollama Qwen if key absent or call fails."""
    if DEEPSEEK_KEY:
        try:
            r = httpx.post(
                f"{DEEPSEEK_BASE}/v1/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
                json={"model": DEEPSEEK_MODEL,
                      "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                    {"role": "user", "content": user_msg}],
                      "max_tokens": 4000, "temperature": 0.3},
                timeout=300.0,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return {"backend": "deepseek", "model": DEEPSEEK_MODEL, "raw": content}
        except Exception as e:
            print(f"  DeepSeek failed ({e}); falling back to Ollama", flush=True)
    r = httpx.post(OLLAMA_URL,
                    json={"model": OLLAMA_MODEL,
                          "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                        {"role": "user", "content": user_msg}],
                          "stream": False, "options": {"temperature": 0.3}},
                    timeout=300.0)
    r.raise_for_status()
    return {"backend": "ollama", "model": OLLAMA_MODEL, "raw": r.json()["message"]["content"]}


def parse_reply(raw: str) -> dict:
    import re
    # Strip <think> blocks (R1 style)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    # Strip markdown fences
    raw = re.sub(r"```(?:json)?", "", raw).replace("```", "")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON in LLM reply: {raw[:200]}")
    return json.loads(m.group(0))


def pick_stocks(picks: list[dict]) -> list[str]:
    """For each picked SW-1 industry, return top stocks by recent
    limit_up_reversal_20d signal. Returns list of qlib symbols (SH/SZxxxxxx)."""
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)
    stock_sw1 = pd.read_csv(STOCK_SW1_CSV, dtype={"symbol": str, "sw1_code": str})
    stock_sw1 = stock_sw1.sort_values("join_date").drop_duplicates("symbol", keep="last")

    today = datetime.now().strftime("%Y-%m-%d")
    # Pull factor for the universe over last 60 days
    csi = D.instruments("csi300")
    end = today
    start = (datetime.now() - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    try:
        df = D.features(csi, [STOCK_FACTOR], start_time=start, end_time=end, freq="day")
    except Exception as e:
        print(f"  qlib feature fetch failed: {e}", flush=True)
        return []
    df.columns = ["factor"]
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    if df.empty:
        return []
    latest_date = df.index.get_level_values("datetime").max()
    cross = df.xs(latest_date, level="datetime")["factor"]

    def short(s): return s[2:] if s.startswith(("SH","SZ")) else s
    inst_to_sw1 = dict(zip(stock_sw1["symbol"], stock_sw1["sw1_code"]))

    selected = []
    for p in picks:
        sw1 = p.get("sw1_code", "")
        in_industry = [inst for inst in cross.index if inst_to_sw1.get(short(inst)) == sw1]
        if not in_industry:
            continue
        sub = cross.loc[in_industry].dropna()
        if sub.empty:
            continue
        chosen = sub.nlargest(STOCKS_PER_INDUSTRY).index.tolist()
        selected.extend(chosen)
        print(f"  {sw1}: picked {len(chosen)} stocks", flush=True)
    return selected


def evaluate_previous(today_str: str) -> dict | None:
    """If there's a prediction from approximately one month ago, evaluate it."""
    today = pd.to_datetime(today_str)
    candidates = sorted(PAPER_DIR.glob("prediction_*.json"))
    prev = None
    for p in candidates:
        try:
            d = pd.to_datetime(p.stem.replace("prediction_", ""))
        except Exception:
            continue
        if d < today and (today - d).days >= 25 and (today - d).days <= 45:
            prev = (p, d)
    if prev is None:
        return None
    pred_path, pred_date = prev
    data = json.loads(pred_path.read_text(encoding="utf-8"))
    holdings = data.get("holdings", [])
    if not holdings:
        return None
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)
    try:
        rets = D.features(holdings, [DAILY_RET_EXPR],
                          start_time=pred_date.strftime("%Y-%m-%d"),
                          end_time=today_str, freq="day")
    except Exception as e:
        return {"prediction_date": str(pred_date.date()), "error": str(e)}
    rets.columns = ["ret"]
    daily = rets.groupby(level="datetime")["ret"].mean()
    cum = float((1 + daily).prod() - 1)
    # Benchmark
    bench = D.features(["SH000300"], [DAILY_RET_EXPR],
                       start_time=pred_date.strftime("%Y-%m-%d"),
                       end_time=today_str, freq="day")
    bench.columns = ["ret"]
    bench_daily = bench["ret"].dropna().droplevel("instrument")
    bench_cum = float((1 + bench_daily).prod() - 1)
    return {
        "prediction_date": str(pred_date.date()),
        "eval_date": today_str,
        "n_days": int(len(daily)),
        "portfolio_cum_ret": cum,
        "csi300_cum_ret": bench_cum,
        "excess_ret": cum - bench_cum,
    }


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"=== LLM Industry Picker — {today} ===", flush=True)

    snap = load_industry_snapshot()
    prompt = build_prompt(snap)
    print(f"Prompt size: {len(prompt)} chars", flush=True)

    print("\nCalling LLM ...", flush=True)
    t0 = time.time()
    res = call_llm(prompt)
    elapsed = time.time() - t0
    print(f"  backend={res['backend']} model={res['model']} elapsed={elapsed:.1f}s", flush=True)

    try:
        parsed = parse_reply(res["raw"])
    except Exception as e:
        print(f"  LLM reply parse failed: {e}", flush=True)
        out = PAPER_DIR / f"prediction_{today}.json"
        out.write_text(json.dumps({"date": today, "error": str(e),
                                    "raw": res["raw"]}, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return

    picks = parsed.get("picks", [])
    macro = parsed.get("macro_view", "")
    print(f"\n  picks ({len(picks)}):", flush=True)
    for p in picks:
        print(f"    {p.get('sw1_code')} {p.get('sw1_name')}: {p.get('rationale')}", flush=True)
    print(f"  macro_view: {macro}", flush=True)

    print("\nSelecting stocks within picked industries ...", flush=True)
    holdings = pick_stocks(picks)
    print(f"  total holdings: {len(holdings)}", flush=True)

    pred_obj = {"date": today, "backend": res["backend"], "model": res["model"],
                "elapsed_s": round(elapsed, 1), "picks": picks, "macro_view": macro,
                "holdings": holdings, "raw_llm_reply": res["raw"]}
    out = PAPER_DIR / f"prediction_{today}.json"
    out.write_text(json.dumps(pred_obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved -> {out}", flush=True)

    # Evaluate previous month if exists
    print("\nChecking previous-month evaluation ...", flush=True)
    ev = evaluate_previous(today)
    if ev is None:
        print("  no prior prediction in evaluation window (25-45 days ago)", flush=True)
    else:
        print(f"  vs prediction on {ev.get('prediction_date')}:", flush=True)
        if "error" in ev:
            print(f"    error: {ev['error']}", flush=True)
        else:
            print(f"    portfolio: {ev['portfolio_cum_ret']:+.2%}  CSI300: {ev['csi300_cum_ret']:+.2%}  excess: {ev['excess_ret']:+.2%}", flush=True)
            # Append to evaluation log
            new_row = pd.DataFrame([ev])
            if EVAL_CSV.exists():
                old = pd.read_csv(EVAL_CSV)
                new_row = pd.concat([old, new_row], ignore_index=True)
            new_row.to_csv(EVAL_CSV, index=False)
            print(f"  appended to {EVAL_CSV}", flush=True)


if __name__ == "__main__":
    # Load .env so DEEPSEEK_API_KEY etc. are available
    env = Path("D:/PM/jr/.env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")
    main()
