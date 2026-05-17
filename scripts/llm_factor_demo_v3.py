"""
LLM-driven Qlib factor generator — v3 (reasoning-first, multi-backend, history-aware).

Key upgrades over v2:
  1. Multi-backend: Ollama (local) or DeepSeek API. `--backend` flag picks.
  2. Reasoning-first prompt: LLM must produce a ``thought:`` block analysing
     why the proposed factor should work, BEFORE the expression. This pushes
     simple template-recombiners (Qwen-Coder) toward something more deliberate.
  3. History feedback: every round, the LLM sees the full table of prior
     attempts (name + expr + IC + Rank IC), and is told what *direction* to
     try next based on what's been weak.
  4. Persistence: results JSON is timestamped and tagged with backend/model.
  5. Auto $ normalization for bare field names is kept from v2.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# bypass system Clash proxy for domestic data feeds + DeepSeek API
for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(v, None)
os.environ.setdefault("NO_PROXY", "*")

# load .env if present (lightweight, no python-dotenv dep)
ENV_FILE = Path("D:/PM/jr/.env")
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import httpx
import numpy as np
import pandas as pd
import qlib
from qlib.constant import REG_CN
from qlib.data import D

FIELDS = ["open", "close", "high", "low", "volume", "amount", "vwap"]


SYSTEM_PROMPT = """You are a senior quant researcher developing alpha factors for Chinese A-share equities on a monthly horizon.

You work with Microsoft Qlib's expression language. Cheatsheet:
  Fields: $open $close $high $low $volume $amount $vwap   (ALWAYS prefix with $)
  Ops:
    Mean(x, N)    rolling mean over N days
    Std(x, N)     rolling std
    Sum(x, N)     rolling sum
    Max(x, N), Min(x, N), Med(x, N)
    Ref(x, N)     x lagged by N days   (N > 0 = past)
    Rank(x, N)    rolling cross-sectional rank
    Corr(x, y, N) rolling correlation
    Cov(x, y, N)  rolling covariance
    Log(x), Abs(x), Sign(x)
    Greater(x, y), Less(x, y)
    +, -, *, /, ()

CRITICAL RULES:
  - Every field must have $ prefix.
  - Output MUST be a single JSON object, no markdown fence, no prose around it.
  - Schema: {"thought": "<2-4 sentence reasoning>", "name": "snake_case_name", "expr": "<qlib_expr>"}
  - In `thought`, explain the *economic intuition* (why this should predict next-day return).
  - Do NOT propose factors that are trivial restatements of past attempts.

You will receive a feedback table of previous attempts. A useful Rank IC is > 0.02 in absolute terms. IC near zero means no signal.
"""


def normalize_expr(expr: str) -> str:
    """Inject $ in front of bare field names. Be word-boundary safe."""
    for f in FIELDS:
        for variant in (f, f.capitalize(), f.upper()):
            expr = re.sub(rf"(?<![\$\w]){re.escape(variant)}\b", f"${f}", expr)
    return expr


# ---------- Backend abstraction ----------


class OllamaBackend:
    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self.model = model
        self.url = f"{base_url}/api/chat"

    def chat(self, messages: list[dict]) -> str:
        r = httpx.post(
            self.url,
            json={"model": self.model, "messages": messages, "stream": False,
                  "options": {"temperature": 0.6, "num_predict": 800}},
            timeout=300.0,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]


class DeepSeekBackend:
    def __init__(self, model: str, api_key: str, base_url: str = "https://api.deepseek.com") -> None:
        self.model = model
        self.url = f"{base_url}/v1/chat/completions"
        self.api_key = api_key

    def chat(self, messages: list[dict]) -> str:
        r = httpx.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "messages": messages, "temperature": 0.6, "max_tokens": 8000},
            timeout=300.0,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def get_backend(name: str) -> tuple[Any, str]:
    if name == "ollama-coder":
        m = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
        return OllamaBackend(m, os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")), m
    if name == "ollama-r1":
        m = os.environ.get("OLLAMA_REASONING_MODEL", "deepseek-r1:14b")
        return OllamaBackend(m, os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")), m
    if name == "deepseek":
        key = os.environ["DEEPSEEK_API_KEY"]
        m = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
        return DeepSeekBackend(m, key, os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")), m
    raise ValueError(f"Unknown backend: {name}")


# ---------- Factor evaluation ----------


def evaluate_factor(expr: str, name: str, start: str = "2025-07-01", end: str = "2026-05-13") -> dict:
    label_expr = "Ref($close, -2)/Ref($close, -1) - 1"  # next-day fwd return
    try:
        df = D.features(
            D.instruments("csi300"),
            [expr, label_expr],
            start_time=start, end_time=end, freq="day",
        )
    except Exception as e:
        return {"name": name, "expr": expr, "error": f"qlib parse: {e}", "ic": None, "rank_ic": None}
    df.columns = ["factor", "label"]
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    if df.empty:
        return {"name": name, "expr": expr, "error": "empty after dropna", "ic": None, "rank_ic": None}
    by_date = df.groupby(level="datetime")
    ic = by_date.apply(lambda g: g["factor"].corr(g["label"]) if len(g) > 5 else np.nan).dropna()
    rank_ic = by_date.apply(
        lambda g: g["factor"].rank().corr(g["label"].rank()) if len(g) > 5 else np.nan
    ).dropna()
    if ic.empty:
        return {"name": name, "expr": expr, "error": "no valid IC days", "ic": None, "rank_ic": None}
    return {
        "name": name, "expr": expr,
        "ic": float(ic.mean()),
        "ic_ir": float(ic.mean() / ic.std()) if ic.std() > 0 else None,
        "rank_ic": float(rank_ic.mean()),
        "rank_ic_ir": float(rank_ic.mean() / rank_ic.std()) if rank_ic.std() > 0 else None,
        "n_obs": int(len(df)), "n_days": int(len(ic)),
    }


# ---------- Prompt assembly ----------


def parse_llm_reply(raw: str) -> dict:
    # Strip <think>...</think> blocks (R1-style models)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    # Strip markdown JSON fences (```json ... ```)
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        raw = fence.group(1)
    # First {...} block; use greedy match in case the expression contains nested braces
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON in reply:\n{raw[:500]}")
    obj = json.loads(m.group(0))
    if "expr" in obj:
        obj["expr"] = normalize_expr(obj["expr"])
        # Qlib expression engine doesn't support unary minus in front of operators like -Sum(...).
        # Rewrite leading "-Func(" to "(0 - Func(" with matching close.
        # Qlib doesn't support unary minus in front of function calls; rewrite only at expression
        # boundaries (start of string, after `(`, or after `,`) where binary minus is impossible.
        obj["expr"] = re.sub(r"(^|[\(\,])\s*-\s*(?=[A-Z][a-zA-Z]*\()", r"\1 0 - ", obj["expr"]).strip()
    return obj


def history_table(history: list[dict]) -> str:
    if not history:
        return "(no prior attempts yet — propose your strongest first idea)"
    lines = ["| name | expr | IC | Rank IC | note |", "|---|---|---|---|---|"]
    for h in history:
        ic = f"{h['ic']:.4f}" if h.get("ic") is not None else "—"
        ric = f"{h['rank_ic']:.4f}" if h.get("rank_ic") is not None else "—"
        note = h.get("error", "") or ("OK" if h.get("ic") is not None else "")
        lines.append(f"| {h['name']} | `{h['expr']}` | {ic} | {ric} | {note} |")
    return "\n".join(lines)


def initial_user_prompt() -> str:
    return (
        "Propose your FIRST factor for predicting next-day return on CSI300 A-shares.\n\n"
        "Available history of prior attempts:\n"
        "(none — this is round 1)\n\n"
        "Required JSON schema: {\"thought\": \"...\", \"name\": \"...\", \"expr\": \"...\"}"
    )


def next_user_prompt(history: list[dict]) -> str:
    weakness = []
    if all(abs(h.get("rank_ic", 0) or 0) < 0.02 for h in history):
        weakness.append("All previous factors have |Rank IC| < 0.02 — they are essentially noise.")
    used_ideas = ", ".join(h["name"] for h in history)
    return (
        "Below is the full history of factors you have proposed so far on this CSI300 A-share monthly task.\n\n"
        f"{history_table(history)}\n\n"
        f"Observations: {' '.join(weakness) if weakness else 'mixed results.'}\n"
        f"Already-tried names: {used_ideas}.\n\n"
        "Now propose a DIFFERENT factor. Required:\n"
        "  - Move to a category not yet explored. Categories: momentum, reversal, volatility, "
        "    liquidity, price-volume-divergence, intraday-pattern, cross-sectional-rank, mean-reversion.\n"
        "  - In `thought`, name the category and explain WHY this factor exploits a specific A-share market structure "
        "(e.g. T+1 trading, daily price limits, retail concentration, dividend-cut effects, sector rotation).\n"
        "  - Same JSON schema as before."
    )


# ---------- Main loop ----------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="ollama-coder", choices=["ollama-coder", "ollama-r1", "deepseek"])
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    backend, model_name = get_backend(args.backend)
    qlib.init(provider_uri=os.environ.get("QLIB_PROVIDER_URI", "D:/PM/jr/qlib_data/cn_data"),
              region=REG_CN)
    print(f"Backend: {args.backend} ({model_name})", flush=True)

    history: list[dict] = []
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for i in range(args.rounds):
        user_msg = initial_user_prompt() if i == 0 else next_user_prompt(history)
        # Rebuild messages per round to keep context small for big histories
        msgs = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg}]
        print(f"\n--- Round {i+1}/{args.rounds} ---", flush=True)
        t0 = time.time()
        try:
            raw = backend.chat(msgs)
            proposal = parse_llm_reply(raw)
        except Exception as e:
            print(f"  LLM error: {e}", flush=True)
            history.append({"name": f"round_{i}_error", "expr": "", "error": str(e)})
            continue
        name = proposal.get("name", f"factor_{i}")
        expr = proposal.get("expr", "")
        thought = proposal.get("thought", "")
        print(f"  thought: {thought}", flush=True)
        print(f"  expr:    {expr}", flush=True)
        metrics = evaluate_factor(expr, name)
        metrics["thought"] = thought
        metrics["round"] = i + 1
        metrics["elapsed_s"] = round(time.time() - t0, 1)
        history.append(metrics)
        ic = metrics.get("ic")
        ric = metrics.get("rank_ic")
        print(f"  IC={ic if ic is None else f'{ic:.4f}'}  RankIC={ric if ric is None else f'{ric:.4f}'}  ({metrics['elapsed_s']}s)", flush=True)

    print("\n=== SUMMARY ===", flush=True)
    print(history_table(history), flush=True)
    out = args.out or f"D:/PM/jr/qlib_data/llm_factors_{args.backend}_{int(time.time())}.json"
    Path(out).write_text(json.dumps({"backend": args.backend, "model": model_name, "history": history}, indent=2))
    print(f"\nSaved → {out}", flush=True)


if __name__ == "__main__":
    main()
