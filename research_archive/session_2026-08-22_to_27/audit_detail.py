"""Per-ticker forensics on every case the time axis flagged, plus the
magnitude-axis distribution needed to derive an S&P 600 plausibility band.
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
import yfinance as yf  # noqa: E402

HERE = Path(__file__).parent
with (HERE / "sc600_fetch.pkl").open("rb") as fh:
    D = pickle.load(fh)
with (HERE / "audit_stage1.pkl").open("rb") as fh:
    S = pickle.load(fh)

close = D["close"]
shares = D["shares"]
mcap_before = S["mcap_before"]
pd.set_option("display.width", 250, "display.max_columns", 40)

FLAGGED = list(S["dropped"].keys())
print("FLAGGED BY THE TIME AXIS:", FLAGGED)
print()

for t in FLAGGED:
    raw = shares[t]
    priced = close[t].dropna()
    first_price = priced.index[0]
    pre = raw[raw.index < first_price - pd.Timedelta(days=10)]
    post = raw[raw.index >= first_price - pd.Timedelta(days=10)]
    print("=" * 78)
    print(f"{t}: {len(raw)} share obs {raw.index[0].date()}..{raw.index[-1].date()}; "
          f"price {first_price.date()}..{priced.index[-1].date()} ({len(priced)} bars)")
    print(f"   PRE-price-window counts : n={len(pre)} "
          f"range {pre.min():,.0f}..{pre.max():,.0f}" if len(pre) else "   PRE: none")
    if len(post):
        print(f"   IN-price-window counts  : n={len(post)} "
              f"range {post.min():,.0f}..{post.max():,.0f}   first={post.iloc[0]:,.0f} on {post.index[0].date()}")
        if len(pre):
            step = post.iloc[0] / pre.iloc[-1]
            print(f"   STEP across the boundary: {pre.iloc[-1]:,.0f} -> {post.iloc[0]:,.0f}  = {step:.4f}x")
    else:
        print("   IN-price-window counts  : NONE — every observation is outside the lifecycle")
    # what the contaminated join actually produced on this ticker's priced days
    mc = mcap_before[t].dropna()
    if len(mc):
        print(f"   implied mcap on priced days (contaminated): "
              f"{mc.min()/1e9:,.4f}bn .. {mc.max()/1e9:,.4f}bn  (n={len(mc)})")
    try:
        info = yf.Ticker(t).info
        print(f"   .info -> name={info.get('longName')!r} shares={info.get('sharesOutstanding')} "
              f"mcap={info.get('marketCap')} exch={info.get('exchange')}")
    except Exception as exc:
        print(f"   .info -> FAILED {exc}")
print()
print("=" * 78)
print("MAGNITUDE AXIS: what an S&P 600 band would flag")
print("=" * 78)
elig = S["elig"]
mc_e = mcap_before.where(elig)
vals = mc_e.to_numpy().ravel()
vals = vals[np.isfinite(vals)]
total = len(vals)
for lo in (5e7, 1e8, 2e8):
    for hi in (1e11, 2e11, 5e11):
        n = int(((vals < lo) | (vals > hi)).sum())
        print(f"  band [{lo/1e9:.2f}bn, {hi/1e9:.0f}bn]: {n:,} of {total:,} eligible cells ({100*n/total:.3f}%)")
with (HERE / "mc_elig.pkl").open("wb") as fh:
    pickle.dump({"mc_e": mc_e}, fh)
