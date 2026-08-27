"""Confirm the market-cap split-adjustment bug against REAL AAPL data."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

import pandas as pd
import yfinance as yf

pd.set_option("display.width", 200)

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_ivol import build_point_in_time_market_cap

T = "AAPL"
START = date(2020, 6, 1)
END = date(2020, 11, 1)

print("=== 1. yf.Ticker(AAPL).splits (real, dated split ratios) ===")
splits = yf.Ticker(T).splits
print(splits.tail(6))

print("\n=== 2. auto_adjust=True close (what get_price_history returns) ===")
prov = YFinanceProvider()
close, missing = prov.get_price_history([T], START, END)
print("missing:", missing)
sub = close.loc["2020-08-24":"2020-09-04"]
print(sub)

print("\n=== 2b. auto_adjust=False raw download, same window ===")
raw = yf.download([T], start=START, end=END, auto_adjust=False, progress=False, actions=True)
print(raw.loc["2020-08-24":"2020-09-04"].to_string())

print("\n=== 3. get_shares_full (raw historical share counts) ===")
shares, miss_sh = prov.get_shares_outstanding([T], START, END)
s = shares[T]
print("missing:", miss_sh)
print(s.loc["2020-06-01":"2020-11-01"].to_string())

print("\n=== 4. CURRENT (buggy) build_point_in_time_market_cap around the split ===")
cap, no_shares = build_point_in_time_market_cap(close, shares)
window = cap.loc["2020-08-24":"2020-09-04", T]
print((window / 1e9).round(1).to_string())
pre = cap.loc["2020-08-28", T]
post = cap.loc["2020-08-31", T]
print(f"\npre-split  2020-08-28 cap = ${pre/1e9:,.1f}B")
print(f"post-split 2020-08-31 cap = ${post/1e9:,.1f}B")
print(f"ratio post/pre = {post/pre:.4f}   <-- should be ~1.0 for a pure split")
