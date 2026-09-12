#!/usr/bin/env python
"""Probe 2: do the free Yahoo .BK feeds carry the Thai market's SEPARATE BOARDS?

Thailand quotes the same company on up to three lines: the main (local) board, the
foreign board (-F, used when the foreign-ownership limit is full) and the NVDR line
(-R).  A foreign-limit premium can only be measured if the -F line has free data.
This script measures what is actually retrievable, nothing else.
"""
import time

import pandas as pd
import yfinance as yf
from yfinance import EquityQuery, screen

BIG = ["ADVANC", "BBL", "KBANK", "PTT", "SCB", "CPALL", "AOT", "SCC", "BDMS", "TU"]
NAMED = ["SSI", "MAX", "POLAR", "EARTH", "PACE", "NMG", "STARK", "MORE", "IFEC", "JAS", "TRUE", "DTAC"]

def bars(sym):
    try:
        h = yf.Ticker(sym).history(period="max", auto_adjust=False)
        if len(h) == 0:
            return None
        return h
    except Exception as e:  # noqa: BLE001 - probe records the failure and continues
        print(f"   {sym}: ERROR {e!r}")
        return None

print("=== A. foreign-board (-F) lines on Yahoo ===")
for b in BIG:
    h = bars(f"{b}-F.BK")
    print(f"  {b}-F.BK  {'0 bars' if h is None else f'bars={len(h)} first={h.index[0].date()} last={h.index[-1].date()}'}")
    time.sleep(0.2)

print("\n=== B. NVDR (-R) line vs main line: are they the same price series? ===")
for b in BIG[:5]:
    a, r = bars(f"{b}.BK"), bars(f"{b}-R.BK")
    if a is None or r is None:
        print(f"  {b}: missing one leg (main={'None' if a is None else len(a)}, R={'None' if r is None else len(r)})")
        continue
    j = pd.DataFrame({"m": a["Close"], "r": r["Close"]}).dropna()
    j.index = j.index.tz_localize(None)
    d = (j["r"] / j["m"] - 1.0)
    print(f"  {b}: overlap={len(j)} days {j.index[0].date()}..{j.index[-1].date()} "
          f"| R/main-1: mean={d.mean():+.5%} sd={d.std():.5%} max|d|={d.abs().max():.5%} "
          f"| days differing >0.1%: {(d.abs()>0.001).sum()}")
    vm = pd.DataFrame({"m": a["Volume"], "r": r["Volume"]}).dropna()
    print(f"      volume: median main={vm['m'].median():,.0f} median R={vm['r'].median():,.0f}")
    time.sleep(0.2)

print("\n=== C. are the 12 named suspended/delisted symbols in the live screener universe? ===")
rows, start = [], 0
while True:
    rr = screen(EquityQuery("eq", ["region", "th"]), size=250, offset=start)
    qs = rr.get("quotes", [])
    if not qs: break
    rows += qs; start += len(qs)
    if start >= rr.get("total", 0): break
    time.sleep(0.3)
live = {q["symbol"] for q in rows}
for n in NAMED:
    print(f"  {n:7s} in live screener universe: {f'{n}.BK' in live}")
print(f"  (live universe size {len(live)})")
