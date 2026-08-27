"""Independent re-verification of every 'confirmed real data' claim in the
Bonds build brief. Nothing downstream is trusted until this passes."""
import sys
from datetime import date

import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = ["SHY", "IEI", "IEF", "TLH", "TLT", "TIP", "LQD", "HYG"]
START = date(2000, 1, 1)
END = date(2026, 8, 27)

print("=" * 78)
print("CLAIM 1: 8 liquid bond ETFs, common clean history from 2007-04-11, ~4876+ rows")
print("=" * 78)

adj = yf.download(TICKERS, start=START, end=END, auto_adjust=True, progress=False)
close_adj = adj["Close"].dropna(axis=1, how="all")
print("tickers resolved:", list(close_adj.columns))
for t in close_adj.columns:
    s = close_adj[t].dropna()
    print(f"  {t}: first={s.index[0].date()} last={s.index[-1].date()} rows={len(s)}")

common = close_adj.dropna(axis=0, how="any")
print(f"\nCOMMON (no-NaN across all 8): first={common.index[0].date()} "
      f"last={common.index[-1].date()} rows={len(common)}")

print()
print("=" * 78)
print("CLAIM 2: auto_adjust=True is MANDATORY (raw price return near-zero/negative,")
print("         total return large -- distributions ARE the return)")
print("=" * 78)

raw = yf.download(TICKERS, start=START, end=END, auto_adjust=False, progress=False)
close_raw = raw["Close"]

rows = []
for t in TICKERS:
    a = close_adj[t].dropna()
    r = close_raw[t].dropna()
    a = a.loc[a.index >= common.index[0]]
    r = r.loc[r.index >= common.index[0]]
    years = (a.index[-1] - a.index[0]).days / 365.25
    tr_total = a.iloc[-1] / a.iloc[0] - 1.0
    px_total = r.iloc[-1] / r.iloc[0] - 1.0
    tr_cagr = (1 + tr_total) ** (1 / years) - 1
    px_cagr = (1 + px_total) ** (1 / years) - 1
    rows.append((t, px_total, px_cagr, tr_total, tr_cagr))

print(f"{'ETF':<6}{'PRICE tot':>12}{'PRICE cagr':>13}{'TOTRET tot':>13}{'TOTRET cagr':>13}")
for t, pt, pc, tt, tc in rows:
    print(f"{t:<6}{pt:>11.1%}{pc:>12.2%}{tt:>12.1%}{tc:>12.2%}")

n_px_nonpos = sum(1 for _, _, pc, _, _ in rows if pc <= 0.0)
print(f"\nETFs whose RAW PRICE CAGR is <= 0: {n_px_nonpos} / {len(rows)}")
print(f"ETFs whose TOTAL-RETURN CAGR is > 0: {sum(1 for r_ in rows if r_[4] > 0)} / {len(rows)}")

print()
print("=" * 78)
print("CLAIM 3: HYG-vs-TLT daily correlation ~= -0.13 (independent-axis evidence)")
print("=" * 78)

rets = np.log(common).diff().dropna()
simple = common.pct_change().dropna()
print(f"corr(HYG, TLT) simple daily returns, full common window: "
      f"{simple['HYG'].corr(simple['TLT']):+.4f}")
print(f"corr(HYG, TLT) log daily returns,    full common window: "
      f"{rets['HYG'].corr(rets['TLT']):+.4f}")

print("\nFull daily-return correlation matrix (simple returns, common window):")
print(simple.corr().round(3).to_string())

print()
print("=" * 78)
print("EXTRA: duration ladder sanity -- annualized vol should rise monotonically")
print("       SHY < IEI < IEF < TLH < TLT if these really are a maturity ladder")
print("=" * 78)
vol = simple.std() * np.sqrt(252)
ladder = ["SHY", "IEI", "IEF", "TLH", "TLT"]
for t in ladder:
    print(f"  {t}: ann vol {vol[t]:.2%}")
mono = all(vol[ladder[i]] < vol[ladder[i + 1]] for i in range(len(ladder) - 1))
print(f"  monotonically increasing across the ladder: {mono}")
print(f"\n  credit names: LQD ann vol {vol['LQD']:.2%}, HYG ann vol {vol['HYG']:.2%}, "
      f"TIP ann vol {vol['TIP']:.2%}")

print()
print("=" * 78)
print("EXTRA: book-vol context for the cost/financing drag arithmetic in the brief")
print("=" * 78)
# A crude equal-weighted long-short book across the ladder extremes, to sanity
# check the "3-5% book vol" figure the holding-period reasoning rests on.
for long_t, short_t in [("TLT", "SHY"), ("HYG", "TLT"), ("TLT", "IEF")]:
    spread = simple[long_t] - simple[short_t]
    print(f"  long {long_t} / short {short_t}: ann vol of the spread {spread.std()*np.sqrt(252):.2%}")

print()
print("=" * 78)
print("EXTRA: rank_fraction for an 8-name universe")
print("=" * 78)
for rf in (0.1, 0.2, 0.25, 0.3):
    n_leg = max(1, int(8 * rf))
    print(f"  rank_fraction={rf}: leg size = max(1, int(8*{rf})) = {n_leg}, "
          f"2*leg={2*n_leg} <= 8 disjoint={2*n_leg <= 8}")
