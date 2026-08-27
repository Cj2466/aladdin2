"""Part 2: where the discontinuity actually lands, how wrong the level is,
and whether a batched actions=True download can supply split ratios."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

import pandas as pd
import yfinance as yf

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_ivol import build_point_in_time_market_cap

prov = YFinanceProvider()

print("=== A. AAPL buggy market cap across the SHARE-FILING date 2020-10-22 ===")
close, _ = prov.get_price_history(["AAPL"], date(2020, 6, 1), date(2021, 1, 1))
shares, _ = prov.get_shares_outstanding(["AAPL"], date(2020, 6, 1), date(2021, 1, 1))
cap, _ = build_point_in_time_market_cap(close, shares)
w = cap.loc["2020-10-16":"2020-10-28", "AAPL"] / 1e9
px = close.loc["2020-10-16":"2020-10-28", "AAPL"]
print(pd.DataFrame({"adj_close": px.round(2), "buggy_cap_$B": w.round(1)}).to_string())
print("\nTRUE AAPL market cap late Aug 2020 was ~$2.0-2.1T.")
print("Buggy cap on 2020-08-28 was $517B  ->  understated ~4x (the 4-for-1 split).")

print("\n=== B. Does a BATCHED yf.download(actions=True, auto_adjust=True) carry Stock Splits? ===")
raw = yf.download(["AAPL", "NVDA", "TSLA", "GOOGL", "AMZN", "MSFT"],
                  start=date(2015, 1, 1), end=date(2026, 8, 26),
                  auto_adjust=True, actions=True, progress=False)
print("top-level fields:", sorted(set(raw.columns.get_level_values(0))))
if "Stock Splits" in raw.columns.get_level_values(0):
    sp = raw["Stock Splits"]
    nz = sp[(sp != 0).any(axis=1)]
    print("\nAll non-zero split rows, 2015-01-01..today (batched, one call):")
    print(nz.to_string())

print("\n=== C. Dividend-adjustment residual: AdjClose/Close spread at 2015-01-07 ===")
raw2 = yf.download(["AAPL", "MSFT", "XOM", "JNJ", "T", "KO", "NVDA", "AMZN", "GOOGL", "BRK-B"],
                   start=date(2015, 1, 1), end=date(2015, 1, 15),
                   auto_adjust=False, actions=False, progress=False)
d = (raw2["Adj Close"] / raw2["Close"]).loc["2015-01-07"]
print(d.round(4).to_string())
print(f"\nspread of the dividend factor across these names: {d.min():.3f} .. {d.max():.3f}")
