#!/usr/bin/env python
"""Probe what FREE Yahoo Finance (.BK) data actually exists for the Stock Exchange of Thailand.

Run:  backend/venv/bin/python probe_thai_yfinance.py > thai_probe_output.txt 2>&1

No secrets, no DB writes, no network credentials. Two stages:
  1. Enumerate the whole Yahoo "region = th" equity universe through yfinance's screener
     (the same endpoint Yahoo's own stock screener uses), recording exchange, quote type,
     first-trade date and 3-month average volume for every symbol.
  2. Download daily bars for a seeded random sample of ordinary (non-NVDR, non-DW) symbols
     and measure: bars returned, first/last bar date, median daily turnover in THB.

Everything printed here is measured, not assumed.
"""
import json, random, sys, time
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
from yfinance import EquityQuery, screen

OUT_JSON = "thai_yfinance_probe.json"
SAMPLE_N = 200
SEED = 20260912


def enumerate_universe():
    rows, start = [], 0
    while True:
        r = screen(EquityQuery("eq", ["region", "th"]), size=250, offset=start)
        qs = r.get("quotes", [])
        total = r.get("total")
        if not qs:
            break
        rows.extend(qs)
        start += len(qs)
        if start >= total:
            break
        time.sleep(0.4)
    return rows, total


def classify(sym: str) -> str:
    base = sym.split(".")[0]
    if base.endswith("-R"):
        return "NVDR (-R)"
    if base.endswith("-F"):
        return "foreign board (-F)"
    if base.endswith("-W1") or "-W" in base:
        return "warrant (-W)"
    if base.endswith("-P"):
        return "preferred (-P)"
    # derivative warrants: SYMBOLnnA / SYMBOLnn  (issuer+series digits)
    if any(ch.isdigit() for ch in base[-3:]):
        return "DW / DR (digit suffix)"
    return "ordinary"


def main():
    print("=== STAGE 1: enumerate Yahoo region=th universe ===")
    rows, total = enumerate_universe()
    print(f"screener total={total}  rows_fetched={len(rows)}  fetched_at={datetime.now(timezone.utc).isoformat()}")
    kinds = Counter(classify(q["symbol"]) for q in rows)
    print("\nsymbol classes:")
    for k, v in kinds.most_common():
        print(f"  {k:26s} {v}")
    exch = Counter(q.get("exchange") for q in rows)
    print("\nexchange field:", dict(exch))
    qtype = Counter(q.get("quoteType") for q in rows)
    print("quoteType field:", dict(qtype))

    ordinary = [q for q in rows if classify(q["symbol"]) == "ordinary"]
    print(f"\nordinary symbols: {len(ordinary)}")

    ft = []
    for q in ordinary:
        ms = q.get("firstTradeDateMilliseconds")
        if ms:
            ft.append(datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date())
    ft.sort()
    if ft:
        print(f"first-trade dates (ordinary, n={len(ft)}): min={ft[0]} p10={ft[len(ft)//10]} "
              f"median={ft[len(ft)//2]} p90={ft[9*len(ft)//10]} max={ft[-1]}")
        byyear = Counter(d.year for d in ft)
        print("first-trade year histogram:", dict(sorted(byyear.items())))

    print("\n=== STAGE 2: daily-bar download for a seeded sample of ordinary symbols ===")
    random.seed(SEED)
    sample = sorted(random.sample([q["symbol"] for q in ordinary], min(SAMPLE_N, len(ordinary))))
    print(f"sample n={len(sample)} seed={SEED}")
    stats, errors = [], []
    CH = 25
    for i in range(0, len(sample), CH):
        chunk = sample[i:i + CH]
        try:
            df = yf.download(chunk, period="max", interval="1d", auto_adjust=False,
                             progress=False, threads=True, group_by="ticker")
        except Exception as e:  # pragma: no cover
            errors.append((chunk, repr(e)))
            continue
        for s in chunk:
            try:
                sub = df[s].dropna(subset=["Close"]) if isinstance(df.columns, pd.MultiIndex) else df.dropna(subset=["Close"])
            except Exception:
                errors.append((s, "no column"))
                continue
            if sub is None or len(sub) == 0:
                stats.append({"symbol": s, "bars": 0})
                continue
            turnover = (sub["Close"] * sub["Volume"]).replace(0, pd.NA).dropna()
            stats.append({
                "symbol": s,
                "bars": int(len(sub)),
                "first": str(sub.index[0].date()),
                "last": str(sub.index[-1].date()),
                "median_thb_turnover": float(turnover.median()) if len(turnover) else 0.0,
                "median_volume": float(sub["Volume"].median()),
            })
        time.sleep(0.3)

    ok = [s for s in stats if s["bars"] > 0]
    zero = [s for s in stats if s["bars"] == 0]
    print(f"symbols with >=1 daily bar: {len(ok)}/{len(stats)}   zero bars: {len(zero)}  errors: {len(errors)}")
    if zero:
        print("  zero-bar symbols:", [s['symbol'] for s in zero][:30])
    if errors:
        print("  errors:", errors[:5])
    if ok:
        firsts = sorted(s["first"] for s in ok)
        lasts = sorted(s["last"] for s in ok)
        bars = sorted(s["bars"] for s in ok)
        tos = sorted(s["median_thb_turnover"] for s in ok)
        n = len(ok)
        print(f"  first bar: min={firsts[0]} p25={firsts[n//4]} median={firsts[n//2]} p75={firsts[3*n//4]} max={firsts[-1]}")
        print(f"  last  bar: min={lasts[0]} p25={lasts[n//4]} median={lasts[n//2]} max={lasts[-1]}")
        print(f"  bars:      min={bars[0]} median={bars[n//2]} max={bars[-1]}")
        print(f"  median daily turnover THB: p10={tos[n//10]:,.0f} p25={tos[n//4]:,.0f} median={tos[n//2]:,.0f} p75={tos[3*n//4]:,.0f} p90={tos[9*n//10]:,.0f}")
        stale = [s for s in ok if s["last"] < "2026-08-01"]
        print(f"  symbols whose LAST bar is before 2026-08-01 (candidate delisted/halted): {len(stale)}")
        for s in sorted(stale, key=lambda x: x["last"])[:25]:
            print(f"    {s['symbol']:14s} last={s['last']} bars={s['bars']}")

    print("\n=== STAGE 3: named delisted / suspended SET names (do free bars survive?) ===")
    # Names chosen because they are documented SET delistings/long suspensions.
    named = ["SSI.BK", "MAX.BK", "POLAR.BK", "EARTH.BK", "PACE.BK", "NMG.BK",
             "STARK.BK", "MORE.BK", "IFEC.BK", "JAS.BK", "TRUE.BK", "DTAC.BK"]
    for s in named:
        try:
            h = yf.Ticker(s).history(period="max", auto_adjust=False)
            if len(h) == 0:
                print(f"  {s:10s} 0 bars")
            else:
                print(f"  {s:10s} bars={len(h):5d} first={h.index[0].date()} last={h.index[-1].date()}")
        except Exception as e:
            print(f"  {s:10s} ERROR {e!r}")
        time.sleep(0.2)

    json.dump({"total": total, "classes": kinds, "exchange": exch,
               "n_ordinary": len(ordinary), "sample_stats": stats,
               "fetched_at": datetime.now(timezone.utc).isoformat()},
              open(OUT_JSON, "w"), indent=1, default=str)
    print(f"\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
