"""Aggregate recent A-share-relevant news into paper_trades/news_cache.json.

Sources (akshare):
  - stock_news_main_cx     : 财新 financial news (~100 items, no explicit date — extract from URL)
  - news_cctv              : CCTV evening news (policy signal)
  - news_economic_baidu    : macro/economic event calendar

The cache JSON is consumed by:
  - /api/news/recent       : FastAPI endpoint
  - llm_industry_picker.py : injects top N items into LLM prompt

Idempotent: overwrites the cache file each run.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

for v in ("HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(v, None)

sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import akshare as ak

OUT = Path(os.environ.get("JR_PROJ_ROOT", "D:/PM/jr")) / "paper_trades" / "news_cache.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

DAYS_BACK = int(os.environ.get("JR_NEWS_DAYS", "14"))


def _date_from_url(url: str) -> str | None:
    m = re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})", str(url))
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def fetch_caixin() -> list[dict]:
    items: list[dict] = []
    try:
        df = ak.stock_news_main_cx()
    except Exception as e:
        print(f"  [caixin] FAIL: {e}", flush=True)
        return items
    for _, r in df.iterrows():
        date = _date_from_url(r.get("url", ""))
        items.append({
            "source": "财新",
            "date": date or "",
            "title": str(r.get("tag", "")).strip(),
            "summary": str(r.get("summary", "")).strip()[:300],
            "url": str(r.get("url", "")),
        })
    return items


def fetch_cctv(days_back: int) -> list[dict]:
    items: list[dict] = []
    try:
        df = ak.news_cctv()
    except Exception as e:
        print(f"  [cctv] FAIL: {e}", flush=True)
        return items
    df["dt"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days_back * 3)  # wider for CCTV
    df = df[df["dt"] >= cutoff].sort_values("dt", ascending=False)
    for _, r in df.iterrows():
        items.append({
            "source": "CCTV",
            "date": r["dt"].strftime("%Y-%m-%d") if pd.notna(r["dt"]) else "",
            "title": str(r.get("title", "")).strip(),
            "summary": str(r.get("content", ""))[:400].strip(),
            "url": "",
        })
    return items


def fetch_economic_baidu(days_back: int) -> list[dict]:
    items: list[dict] = []
    try:
        df = ak.news_economic_baidu()
    except Exception as e:
        print(f"  [baidu_econ] FAIL: {e}", flush=True)
        return items
    df["dt"] = pd.to_datetime(df["日期"], errors="coerce")
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days_back)
    df = df[df["dt"] >= cutoff]
    # Importance 2-3 are "highly impactful"; filter to those for signal-to-noise
    if "重要性" in df.columns:
        df = df[df["重要性"].astype(int) >= 2]
    for _, r in df.iterrows():
        region = r.get("地区", "")
        event = r.get("事件", "")
        actual = r.get("公布", "")
        prior = r.get("前值", "")
        items.append({
            "source": "Baidu Econ",
            "date": r["dt"].strftime("%Y-%m-%d") if pd.notna(r["dt"]) else "",
            "title": f"[{region}] {event}".strip(),
            "summary": f"公布: {actual} · 前值: {prior}",
            "url": "",
        })
    return items


def main() -> None:
    print(f"=== refresh_news (last {DAYS_BACK} days) → {OUT} ===", flush=True)
    all_items: list[dict] = []
    print("Fetching 财新 financial news...", flush=True)
    all_items.extend(fetch_caixin())
    print("Fetching CCTV evening news...", flush=True)
    all_items.extend(fetch_cctv(DAYS_BACK))
    print("Fetching Baidu economic calendar...", flush=True)
    all_items.extend(fetch_economic_baidu(DAYS_BACK))

    # Sort by date desc when available
    all_items.sort(key=lambda x: x.get("date", ""), reverse=True)

    cache = {
        "refreshed_at": datetime.now().isoformat(timespec="seconds"),
        "days_back": DAYS_BACK,
        "n_items": len(all_items),
        "by_source": {
            s: sum(1 for it in all_items if it["source"] == s)
            for s in {it["source"] for it in all_items}
        },
        "items": all_items,
    }
    OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nTotal {len(all_items)} items written to {OUT}", flush=True)
    for src, n in cache["by_source"].items():
        print(f"  {src}: {n}", flush=True)


if __name__ == "__main__":
    main()
