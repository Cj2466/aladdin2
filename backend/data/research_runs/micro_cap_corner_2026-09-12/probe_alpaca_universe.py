#!/usr/bin/env python
"""Step 0 Day 2 measurement: what universe does free Alpaca data give for the
micro-cap corner, INCLUDING names that no longer trade?

Reads /v2/assets (status active and inactive, us_equity), then for a
deterministic sample of inactive listed-exchange symbols fetches SIP daily bars
2016-01-04 -> last complete UTC day and records first/last bar dates and
median dollar volume. NO strategy, NO return, NO DB row. Output: JSON next to
this script. The Alpaca free tier refuses windows touching the current UTC day.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))
from app.services.market_data.alpaca_provider import AlpacaProvider

LISTED = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}
SAMPLE = 300
SEED = 20260912


def main() -> int:
    h = {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET"]}
    base = os.environ.get("ALPACA_TRADING_BASE_URL", "https://paper-api.alpaca.markets")
    assets = {}
    for st in ("active", "inactive"):
        r = requests.get(f"{base}/v2/assets", params={"status": st, "asset_class": "us_equity"}, headers=h, timeout=120)
        r.raise_for_status()
        assets[st] = r.json()
    out = {"fetched_at": datetime.now(UTC).isoformat(), "counts": {}, "sample": []}
    for st, a in assets.items():
        out["counts"][st] = {"total": len(a), "by_exchange": dict(Counter(x["exchange"] for x in a)),
                             "listed_exchanges": sum(1 for x in a if x["exchange"] in LISTED)}
    inactive_listed = sorted(x["symbol"] for x in assets["inactive"] if x["exchange"] in LISTED)
    rng = random.Random(SEED)
    sample = rng.sample(inactive_listed, min(SAMPLE, len(inactive_listed)))
    end = (datetime.now(UTC) - timedelta(days=1)).date()
    prov = AlpacaProvider()
    t0 = time.time()
    start = date(2016, 1, 4)
    for i in range(0, len(sample), 50):
        chunk = sample[i : i + 50]
        try:
            frames, _missing = prov.get_stock_bars(chunk, "1Day", start, end, feed="sip")
        except Exception as exc:  # noqa: BLE001
            for sym in chunk:
                out["sample"].append({"symbol": sym, "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
            continue
        for sym in chunk:
            rec = {"symbol": sym}
            df = frames.get(sym)
            if df is None or len(df) == 0:
                rec["bars"] = 0
            else:
                rec["bars"] = len(df)
                rec["first"] = str(df.index.min())[:10]
                rec["last"] = str(df.index.max())[:10]
                rec["median_dollar_volume"] = float((df["close"] * df["volume"]).median())
            out["sample"].append(rec)
        print(f"{i+len(chunk)}/{len(sample)} {time.time()-t0:.0f}s", flush=True)
    with_bars = [r for r in out["sample"] if r.get("bars")]
    lasts = sorted(r["last"] for r in with_bars)
    out["summary"] = {
        "sampled": len(sample), "with_bars": len(with_bars), "zero_bars": sum(1 for r in out["sample"] if r.get("bars") == 0),
        "errors": sum(1 for r in out["sample"] if "error" in r),
        "last_bar_min": lasts[0] if lasts else None, "last_bar_p10": lasts[len(lasts)//10] if lasts else None,
        "last_bar_median": lasts[len(lasts)//2] if lasts else None, "last_bar_max": lasts[-1] if lasts else None,
        "still_ending_at_window_end": sum(1 for r in with_bars if r["last"] >= (end - timedelta(days=7)).isoformat()),
        "seconds": round(time.time() - t0, 1),
    }
    (HERE / "alpaca_universe_probe.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["counts"], indent=1)); print(json.dumps(out["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
