#!/usr/bin/env python
"""Probe 3: is the Thai FOREIGN-BOARD (-F) premium measurable on free Yahoo data?

When a stock's foreign-ownership limit (FOL) is full, foreigners who want voting shares
must buy on the separate foreign board, which trades at a premium to the main board.
This measures, for a set of large SET names, whether the -F line's closes actually differ
from the main line's and by how much, plus how often the -F line trades at all.
Measured only; no strategy, no backtest.
"""
import time

import pandas as pd
import yfinance as yf

BIG = ["ADVANC","BBL","KBANK","PTT","SCB","CPALL","AOT","SCC","TU","KTB","BAY","TISCO","SCCC","EGCO","BANPU"]

def h(sym):
    try:
        d = yf.Ticker(sym).history(period="max", auto_adjust=False)
        return None if len(d)==0 else d
    except Exception as e:  # noqa: BLE001 - probe records the failure and continues
        print(f"  {sym} ERROR {e!r}"); return None

print("symbol | overlap days | first | last | F/main-1 mean | sd | p95 | max | days>1% | median F volume | days F volume=0")
for b in BIG:
    m, f = h(f"{b}.BK"), h(f"{b}-F.BK")
    if m is None or f is None:
        print(f"{b}: missing leg main={'None' if m is None else len(m)} F={'None' if f is None else len(f)}")
        continue
    m.index = m.index.tz_localize(None); f.index = f.index.tz_localize(None)
    j = pd.DataFrame({"m": m["Close"], "f": f["Close"], "vf": f["Volume"], "vm": m["Volume"]}).dropna()
    j = j[(j.m > 0) & (j.f > 0)]
    d = j["f"]/j["m"] - 1.0
    print(f"{b:7s} | {len(j):5d} | {j.index[0].date()} | {j.index[-1].date()} | {d.mean():+.3%} | {d.std():.3%} | "
          f"{d.quantile(0.95):+.3%} | {d.max():+.3%} | {(d.abs()>0.01).sum():5d} | {j['vf'].median():,.0f} | {(j['vf']==0).sum():5d}")
    time.sleep(0.2)

print("\n=== Why the -R (NVDR) series looked wrong: raw vs split-adjusted for PTT ===")
for s in ["PTT.BK","PTT-R.BK"]:
    d = yf.Ticker(s).history(period="max", auto_adjust=False)
    a = yf.Ticker(s).history(period="max", auto_adjust=True)
    print(f"  {s}: raw close 2026-09-11 area={d['Close'].iloc[-1]:.2f} adj={a['Close'].iloc[-1]:.2f} "
          f"bars={len(d)} splits={int((yf.Ticker(s).splits!=0).sum())} median_vol={d['Volume'].median():,.0f} "
          f"zero-vol days={(d['Volume']==0).sum()}")
