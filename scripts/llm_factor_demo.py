"""
Minimal "LLM-driven factor generator" — RD-Agent-lite for the impatient.

Loop:
  1. Prompt Ollama (Qwen2.5-Coder:14B) to propose a Qlib expression-language
     factor (e.g. `(Mean($close, 20) - $close) / Mean($close, 20)`).
  2. Validate it's a parseable Qlib expression.
  3. Compute the factor on our CSI300 dataset, get IC vs next-day return.
  4. Feed the IC back to the LLM and ask for a refinement.

This proves the LLM-factor-generation pipeline end-to-end, without
RD-Agent's Windows-incompatible code-execution sandbox.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

for v in ("HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(v, None)

import httpx
import numpy as np
import pandas as pd
import qlib
from qlib.constant import REG_CN
from qlib.data import D

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5-coder:14b"

SYSTEM_PROMPT = """You are a quantitative finance researcher generating factors for Microsoft Qlib.

Qlib expression syntax cheatsheet:
  - $open, $close, $high, $low, $volume, $amount, $vwap   — raw fields (prefix with $)
  - Mean(x, N)        — N-day rolling mean
  - Std(x, N)         — N-day rolling std
  - Ref(x, N)         — N-day lag (N > 0 means N days ago)
  - Rank(x, N)        — N-day rolling cross-sectional rank
  - Greater(x, y), Less(x, y), Abs(x), Log(x)
  - +, -, *, / arithmetic; parentheses

Reply with EXACTLY one JSON object, no prose, no markdown fence:
  {"name": "snake_case_name", "expr": "<a Qlib expression>", "rationale": "<one sentence>"}
"""

USER_INIT = """Propose a new alpha factor for predicting next-day stock return on Chinese CSI300.
Focus on price/volume relationships, momentum, or volatility. Do not propose anything that requires data outside the listed fields.
"""


FIELDS = ["open", "close", "high", "low", "volume", "amount", "vwap"]


def normalize_expr(expr: str) -> str:
    """Add $ prefix in front of bare field names (the LLM frequently forgets)."""
    for f in FIELDS:
        # Replace bare field (capitalized or lower), word boundary, not already $-prefixed
        for variant in (f.capitalize(), f.upper(), f):
            expr = re.sub(rf"(?<![\$\w]){re.escape(variant)}\b", f"${f}", expr)
    return expr


def ask_llm(messages: list[dict]) -> dict:
    r = httpx.post(
        OLLAMA_URL,
        json={"model": MODEL, "messages": messages, "stream": False, "options": {"temperature": 0.4}},
        timeout=180.0,
    )
    r.raise_for_status()
    content = r.json()["message"]["content"]
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON in LLM reply:\n{content}")
    parsed = json.loads(m.group(0))
    if "expr" in parsed:
        parsed["expr"] = normalize_expr(parsed["expr"])
    return parsed


def evaluate_factor(expr: str, name: str) -> dict:
    label_expr = "Ref($close, -2)/Ref($close, -1) - 1"  # next-day fwd return
    df = D.features(
        D.instruments("csi300"),
        [expr, label_expr],
        start_time="2025-07-01",
        end_time="2026-05-13",
        freq="day",
    )
    df.columns = ["factor", "label"]
    df = df.dropna()
    if df.empty:
        return {"name": name, "expr": expr, "ic": None, "rank_ic": None, "n_obs": 0}
    by_date = df.groupby(level="datetime")
    ic = by_date.apply(lambda g: g["factor"].corr(g["label"]) if len(g) > 5 else np.nan).dropna()
    rank_ic = by_date.apply(
        lambda g: g["factor"].rank().corr(g["label"].rank()) if len(g) > 5 else np.nan
    ).dropna()
    return {
        "name": name,
        "expr": expr,
        "ic": float(ic.mean()),
        "ic_ir": float(ic.mean() / ic.std()) if ic.std() > 0 else None,
        "rank_ic": float(rank_ic.mean()),
        "n_obs": int(len(df)),
        "n_days": int(len(ic)),
    }


def main() -> None:
    qlib.init(provider_uri="D:/PM/jr/qlib_data/cn_data", region=REG_CN)
    print(f"Asking {MODEL} for factor proposals via Ollama @ {OLLAMA_URL}...\n")

    history: list[dict] = []
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    user_msg = USER_INIT

    for i in range(5):
        messages.append({"role": "user", "content": user_msg})
        print(f"--- Round {i+1} ---")
        try:
            proposal = ask_llm(messages)
        except Exception as e:
            print(f"  LLM call failed: {e}")
            break
        name = proposal.get("name", f"factor_{i}")
        expr = proposal.get("expr", "")
        print(f"  proposed: {name}  ::  {expr}")
        print(f"  rationale: {proposal.get('rationale', '')}")
        try:
            metrics = evaluate_factor(expr, name)
        except Exception as e:
            print(f"  evaluation failed: {e}")
            metrics = {"name": name, "expr": expr, "ic": None, "error": str(e)}
        print(f"  metrics: IC={metrics.get('ic')}  Rank IC={metrics.get('rank_ic')}  n_days={metrics.get('n_days')}")
        history.append(metrics)
        messages.append({"role": "assistant", "content": json.dumps(proposal)})
        # feedback prompt for next round
        err = metrics.get("error")
        if err:
            fb = f"Previous factor `{name}` failed to evaluate: {err[:200]}. Fix the syntax issue and try again."
        else:
            fb = (
                f"Previous factor `{name}` got IC={metrics.get('ic')}, Rank IC={metrics.get('rank_ic')}. "
                "Propose a different factor that explores a complementary signal."
            )
        user_msg = fb + " Use the EXACT same JSON output format and remember $-prefix on every field."

    print("\n=== SUMMARY ===")
    for h in history:
        print(f"  {h.get('name'):30s}  IC={h.get('ic')}  Rank IC={h.get('rank_ic')}")
    Path("D:/PM/jr/qlib_data/llm_factors.json").write_text(json.dumps(history, indent=2))
    print(f"\nSaved {len(history)} factor proposals → D:/PM/jr/qlib_data/llm_factors.json")


if __name__ == "__main__":
    main()
