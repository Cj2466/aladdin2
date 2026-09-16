#!/usr/bin/env python
"""Test B, step 0: FEASIBILITY ONLY. Does the free Alpaca plan return historical
NBBO quotes for the ILLIQUID names where our cost problem actually lives?

This measures data AVAILABILITY, not any trading outcome. No spread number
produced here is used as a result; the run that produces results is governed by
a protocol committed before it (Test A's lesson).

Why this script exists: on 2026-09-16 I told the owner, and wrote into
RESULT_2026-09-16.md, that answering the spread question "needs paid quote
data". I never probed the endpoint. GET /v2/stocks/{sym}/quotes returns HTTP 200
on this account with feed=sip, back to at least 2016. This script establishes
how far that reaches across the liquidity distribution.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
COST_CSV = HERE.parent / "a2_cost_2026-09-15" / "a2_per_ticker_cost.csv"
BASE = "https://data.alpaca.markets"
# A normal, complete, non-holiday session comfortably in the past. Free SIP
# refuses any window touching the current UTC day (known, recorded 2026-09-09).
DAY = "2026-06-10"
WINDOW = (f"{DAY}T14:30:00Z", f"{DAY}T21:00:00Z")
PER_BUCKET = 8


def headers() -> dict[str, str]:
    key, sec = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_API_SECRET")
    if not key or not sec:
        raise SystemExit("ALPACA_API_KEY / ALPACA_API_SECRET not in environment")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}


def sample() -> dict[str, list[dict]]:
    rows = list(csv.DictReader(COST_CSV.open()))
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        buckets.setdefault(r["liquidity_bucket"], []).append(r)
    for b in buckets:
        buckets[b].sort(key=lambda r: r["symbol"])
        step = max(1, len(buckets[b]) // PER_BUCKET)
        buckets[b] = buckets[b][::step][:PER_BUCKET]
    return buckets


def probe(client: httpx.Client, sym: str, path: str) -> dict:
    """One page only. We are asking IF data exists, not collecting it."""
    r = client.get(
        f"/v2/stocks/{sym}/{path}",
        params={"start": WINDOW[0], "end": WINDOW[1], "limit": 10000, "feed": "sip"},
        headers=headers(),
        timeout=60.0,
    )
    if r.status_code != 200:
        return {"http": r.status_code, "body": r.text[:200]}
    d = r.json()
    items = d.get(path) or []
    return {"http": 200, "n_first_page": len(items),
            "more_pages": bool(d.get("next_page_token")),
            "first": items[0] if items else None,
            "last": items[-1] if items else None}


def main() -> int:
    out = {"day": DAY, "window_utc": WINDOW, "feed": "sip",
           "purpose": "feasibility only - data availability, not a result",
           "per_bucket": PER_BUCKET, "buckets": {}}
    with httpx.Client(base_url=BASE) as client:
        for bucket, rows in sorted(sample().items()):
            recs = []
            for r in rows:
                rec = {"symbol": r["symbol"],
                       "median_dollar_volume": float(r["median_dollar_volume"]),
                       "median_close": float(r["median_close"])}
                for path in ("quotes", "trades"):
                    rec[path] = probe(client, r["symbol"], path)
                    time.sleep(0.35)
                recs.append(rec)
                print(bucket, r["symbol"],
                      "q:", rec["quotes"].get("n_first_page", rec["quotes"]["http"]),
                      "t:", rec["trades"].get("n_first_page", rec["trades"]["http"]),
                      flush=True)
            out["buckets"][bucket] = recs
    (HERE / "probe_quote_availability.json").write_text(json.dumps(out, indent=1))
    print("\n=== availability by bucket ===")
    for bucket, recs in sorted(out["buckets"].items()):
        ok = sum(1 for r in recs if r["quotes"].get("n_first_page", 0) > 0)
        tr = sum(1 for r in recs if r["trades"].get("n_first_page", 0) > 0)
        print(f"{bucket:20s} quotes {ok}/{len(recs)}  trades {tr}/{len(recs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
