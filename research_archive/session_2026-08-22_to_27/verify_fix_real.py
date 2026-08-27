"""Verify the FIXED market cap against real data: continuity across every
real split in the D1 window, and correct absolute level vs known market caps."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_ivol import (
    build_point_in_time_market_cap,
    split_adjust_share_counts,
)

TICKERS = ["AAPL", "TSLA", "NVDA", "AMZN", "GOOGL", "MSFT"]
START = date(2015, 1, 7)
END = date(2026, 8, 26)

prov = YFinanceProvider()
print("fetching signal close (auto_adjust=True) ...", flush=True)
close, missing = prov.get_price_history(TICKERS, START, END)
print("fetching market-cap basis close + splits (auto_adjust=False, actions=True) ...", flush=True)
mcap_close, splits, missing2 = prov.get_market_cap_basis(TICKERS, START, END)
mcap_close = mcap_close.reindex(index=close.index, columns=close.columns)
print("fetching shares ...", flush=True)
shares, missing3 = prov.get_shares_outstanding(TICKERS, START, END)
print("missing:", missing, missing2, missing3)

print("\n=== splits recovered from the batched call ===")
for t, s in splits.items():
    print(f"  {t}: " + ", ".join(f"{d.date()}->{v:g}" for d, v in s.items()))

old_cap, _ = build_point_in_time_market_cap(mcap_close, shares, {})   # no split adjustment = old behaviour
new_cap, _ = build_point_in_time_market_cap(mcap_close, shares, splits)
legacy_cap, _ = build_point_in_time_market_cap(close, shares, {})     # exactly the shipped code path

print("\n=== CONTINUITY across each real split: max 1-day |log change| in market cap ===")
print("(a pure stock split must not move market cap at all)")
for t, s in splits.items():
    for exd, ratio in s.items():
        for label, cap in (("shipped(buggy)", legacy_cap), ("split-fixed", new_cap)):
            col = cap[t].dropna()
            win = col[(col.index >= exd - pd.Timedelta(days=120)) & (col.index <= exd + pd.Timedelta(days=120))]
            if len(win) < 3:
                continue
            step = (win / win.shift()).dropna()
            worst = step.iloc[np.argmax(np.abs(np.log(step.values)))]
            worst_day = step.index[int(np.argmax(np.abs(np.log(step.values))))]
            print(f"  {t} {exd.date()} {ratio:g}-for-1  {label:>15}: worst 1-day cap ratio "
                  f"{worst:8.3f} on {worst_day.date()}")

print("\n=== ABSOLUTE LEVEL: AAPL market cap on known dates ===")
for d, truth in (("2020-08-28", "~$2.13T (real: 4.2756e9 sh x $499.23)"),
                 ("2020-10-22", "~$1.92T"),
                 ("2024-06-28", "~$3.19T")):
    ts = pd.Timestamp(d)
    print(f"  {d}: shipped(buggy) ${legacy_cap.loc[ts,'AAPL']/1e12:6.3f}T   "
          f"fixed ${new_cap.loc[ts,'AAPL']/1e12:6.3f}T   truth {truth}")

print("\n=== AAPL split-adjusted share counts around the 2020 split ===")
adj = split_adjust_share_counts(shares["AAPL"], splits["AAPL"])
sub = pd.DataFrame({"raw": shares["AAPL"], "adjusted": adj})
sub = sub.loc["2020-07-15":"2020-11-15"]
print(sub[sub["raw"].ne(sub["raw"].shift())].to_string())

print("\n=== dividend-basis effect (shipped close vs market-cap-basis close), AAPL 2015-01-07 ===")
ts = pd.Timestamp("2015-01-07")
print(f"  signal close (div-adjusted)   : {close.loc[ts,'AAPL']:.4f}")
print(f"  market-cap basis close        : {mcap_close.loc[ts,'AAPL']:.4f}")
print(f"  ratio                          : {close.loc[ts,'AAPL']/mcap_close.loc[ts,'AAPL']:.4f}")
