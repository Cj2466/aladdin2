"""Design + validate the reversal-aware bad-print scrub, and check the
leg-size floating point trap."""
import numpy as np
import pandas as pd
import yfinance as yf

print("=== rank_fraction leg-size arithmetic with n=9 ===")
for rf in (1/3, 0.33, 0.34, 0.35, 0.2, 0.25):
    n_leg = max(1, int(9 * rf))
    print(f"  rank_fraction={rf!r:22} -> int(9*rf)={9*rf!r:22} -> n_leg={n_leg}  legs disjoint={2*n_leg <= 9}")

PAIRS = {"EUR": "EURUSD=X", "GBP": "GBPUSD=X", "JPY": "USDJPY=X", "AUD": "AUDUSD=X",
         "CHF": "USDCHF=X", "CAD": "USDCAD=X", "NZD": "NZDUSD=X", "SEK": "USDSEK=X",
         "NOK": "USDNOK=X"}
INVERTED = {"JPY", "CHF", "CAD", "SEK", "NOK"}
raw = yf.download(list(PAIRS.values()), start="2003-01-01", end="2026-08-28",
                  auto_adjust=False, progress=False, group_by="column")
close = raw["Close"][list(PAIRS.values())].dropna(how="any")
px = pd.DataFrame(index=close.index)
for c, t in PAIRS.items():
    px[c] = 1.0 / close[t] if c in INVERTED else close[t]

SPIKE = 0.04
REV = 0.5

def scrub_flags(prices):
    r = prices.pct_change()
    nxt = r.shift(-1)
    two_day = (1.0 + r) * (1.0 + nxt) - 1.0
    return (r.abs() >= SPIKE) & (two_day.abs() <= REV * r.abs())

flags = scrub_flags(px)
print(f"\n=== SCRUB (|r|>={SPIKE:.0%} AND 2-day round-trip <= {REV:.0%} of the spike) ===")
print(f"total flagged cells: {int(flags.sum().sum())} of {flags.size} = {100*flags.sum().sum()/flags.size:.4f}%")
print(flags.sum())

print("\nflagged events (date, ccy, spike, next-day, 2-day):")
r = px.pct_change(); nxt = r.shift(-1); two = (1+r)*(1+nxt)-1
for dt, ccy in flags.stack()[flags.stack()].index:
    print(f"  {dt.date()} {ccy}: r={r.loc[dt,ccy]:+7.2%}  next={nxt.loc[dt,ccy]:+7.2%}  2day={two.loc[dt,ccy]:+7.2%}")

print("\n=== GENUINE events that must SURVIVE the scrub ===")
checks = [("CHF", "2015-01-16", "SNB de-peg"), ("GBP", "2016-06-24", "Brexit"),
          ("GBP", "2022-09-26", "LDI/mini-budget")]
for ccy, d, label in checks:
    ts = pd.Timestamp(d)
    if ts in px.index:
        print(f"  {ccy} {d} ({label}): r={r.loc[ts,ccy]:+.2%}  next={nxt.loc[ts,ccy]:+.2%}  "
              f"2day={two.loc[ts,ccy]:+.2%}  FLAGGED={bool(flags.loc[ts,ccy])}")
    else:
        print(f"  {ccy} {d} ({label}): not a panel row")

print("\n=== Post-scrub return stats (NaN out flagged closes) ===")
clean = px.mask(flags)
rc = clean.pct_change()
print(rc.describe().T[["std", "min", "max"]].round(4))
print(f"\nremaining |ret|>10%: {int((rc.abs()>0.10).sum().sum())} cells")
print(f"remaining |ret|>7.5%: {int((rc.abs()>0.075).sum().sum())} cells")
print("\nlargest 6 surviving moves:")
print(rc.abs().stack().sort_values(ascending=False).head(6))

print("\n=== NaN cost of the scrub ===")
print(f"panel rows: {len(px)}, cells NaN'd: {int(flags.sum().sum())}")
print("rows where ALL 9 are usable after scrub:", int(clean.notna().all(axis=1).sum()))
