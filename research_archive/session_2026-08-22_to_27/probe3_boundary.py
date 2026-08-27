"""Part 3: which side of the split ex-date does get_shares_full's own count
sit on? Decides whether the cumulative factor includes splits with
ex-date >= obs date or strictly >."""
import sys
from datetime import date, timedelta

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

import pandas as pd
import yfinance as yf

from app.services.market_data.yfinance_provider import YFinanceProvider

prov = YFinanceProvider()

CASES = [
    ("AAPL", date(2020, 8, 31), 4.0),
    ("TSLA", date(2020, 8, 31), 5.0),
    ("NVDA", date(2021, 7, 20), 4.0),
    ("AMZN", date(2022, 6, 6), 20.0),
    ("GOOGL", date(2022, 7, 18), 20.0),
    ("TSLA", date(2022, 8, 25), 3.0),
    ("NVDA", date(2024, 6, 10), 10.0),
]

for ticker, exdate, ratio in CASES:
    lo = exdate - timedelta(days=75)
    hi = exdate + timedelta(days=120)
    shares, missing = prov.get_shares_outstanding([ticker], lo, hi)
    print(f"\n=== {ticker}  {ratio}-for-1 ex-date {exdate} ===")
    if ticker not in shares:
        print("  no shares data:", missing)
        continue
    s = shares[ticker]
    # collapse to distinct values with their first date, so the transition is visible
    changed = s[s.ne(s.shift())]
    for d, v in changed.items():
        side = "PRE " if d.date() < exdate else ("ON  " if d.date() == exdate else "POST")
        print(f"  {side} {d.date()}  shares={v:,.0f}")
    on_or_before = s[s.index.date <= exdate]
    after = s[s.index.date > exdate]
    if len(on_or_before) and len(after):
        last_pre = float(on_or_before.iloc[-1])
        first_post_distinct = None
        for d, v in after.items():
            if abs(v - last_pre) / last_pre > 0.5:
                first_post_distinct = (d.date(), float(v))
                break
        print(f"  last count on/before ex-date : {last_pre:,.0f}")
        if first_post_distinct:
            print(f"  first materially different  : {first_post_distinct[0]}  {first_post_distinct[1]:,.0f}")
            print(f"  implied ratio               : {first_post_distinct[1]/last_pre:.3f}  (split ratio {ratio})")
