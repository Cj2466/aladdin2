"""Are the big FX daily moves genuine jumps or bad prints that revert?"""
import numpy as np
import pandas as pd
import yfinance as yf

PAIRS = {"EUR": "EURUSD=X", "GBP": "GBPUSD=X", "JPY": "USDJPY=X", "AUD": "AUDUSD=X",
         "CHF": "USDCHF=X", "CAD": "USDCAD=X", "NZD": "NZDUSD=X", "SEK": "USDSEK=X",
         "NOK": "USDNOK=X"}
INVERTED = {"JPY", "CHF", "CAD", "SEK", "NOK"}

raw = yf.download(list(PAIRS.values()), start="2003-01-01", end="2026-08-27",
                  auto_adjust=False, progress=False, group_by="column")
close = raw["Close"][list(PAIRS.values())].dropna(how="any")
px = pd.DataFrame(index=close.index)
for c, t in PAIRS.items():
    px[c] = 1.0 / close[t] if c in INVERTED else close[t]

r = px.pct_change()

print("=== Context around the worst moves: is the move REVERSED next day? ===")
worst = r.abs().stack().sort_values(ascending=False).head(12)
for (dt, ccy) in worst.index:
    i = px.index.get_loc(dt)
    lo, hi = max(0, i - 2), min(len(px), i + 3)
    seg = px[ccy].iloc[lo:hi]
    rr = r[ccy].iloc[lo:hi]
    print(f"\n--- {ccy} {dt.date()}  move={r[ccy].loc[dt]:+.2%} ---")
    for d, p, x in zip(seg.index, seg.values, rr.values):
        flag = "  <<<" if d == dt else ""
        print(f"   {d.date()} {d.day_name()[:3]}  px={p:.6f}  ret={x:+.3%}{flag}")

print("\n\n=== Weekday composition of the panel (are holidays/weekends present?) ===")
print(pd.Series(px.index.day_name()).value_counts())

print("\n=== Rows on well-known holidays ===")
for d in ["2021-01-01", "2020-12-25", "2020-01-01", "2019-12-25"]:
    ts = pd.Timestamp(d)
    print(f"  {d}: in panel = {ts in px.index}")

print("\n=== How many days would a 5-MAD robust scrub flag, per currency? ===")
def mad_flags(s, k=8.0, win=63):
    med = s.rolling(win, min_periods=20).median()
    mad = (s - med).abs().rolling(win, min_periods=20).median()
    thr = k * 1.4826 * mad
    return (s - med).abs() > thr.replace(0, np.nan)

for c in px.columns:
    f = mad_flags(r[c])
    print(f"  {c}: {int(f.sum()):4d} / {len(r):5d} = {100*f.mean():.2f}%")

print("\n=== Simple absolute cap: how many days exceed 5%/7.5%/10% ===")
for thr in (0.05, 0.075, 0.10):
    print(f"  |ret| > {thr:.1%}: {int((r.abs() > thr).sum().sum())} cell(s) across all 9")
