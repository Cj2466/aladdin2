"""Dump exact real yfinance values to embed as an offline regression fixture."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider

prov = YFinanceProvider()

for ticker, lo, hi, dates in (
    ("AAPL", date(2020, 7, 1), date(2020, 11, 15),
     ["2020-08-04", "2020-08-28", "2020-08-31", "2020-10-22", "2020-10-23"]),
    ("NVDA", date(2024, 4, 1), date(2024, 8, 1),
     ["2024-05-31", "2024-06-07", "2024-06-10", "2024-06-12", "2024-06-13"]),
):
    close, _, splits, = None, None, None
    mcap_close, splits, _ = prov.get_market_cap_basis([ticker], lo, hi)
    shares, _ = prov.get_shares_outstanding([ticker], lo, hi)
    s = shares[ticker]
    print(f"\n########## {ticker} ##########")
    print("SPLITS:", {str(d.date()): float(v) for d, v in splits[ticker].items()})
    print("SHARE OBSERVATIONS (distinct-value transitions):")
    changed = s[s.ne(s.shift())]
    for d, v in changed.items():
        print(f'    ("{d.date()}", {v!r}),')
    print("MARKET-CAP BASIS CLOSE on key dates:")
    for d in dates:
        ts = pd.Timestamp(d)
        if ts in mcap_close.index:
            print(f'    ("{d}", {float(mcap_close.loc[ts, ticker])!r}),')
        else:
            print(f'    ("{d}", NOT_A_TRADING_DAY),')
