"""Re-derive the REAL S&P 600 production fetch used by
run_small_cap_ivol_screening(start=2020-01-01, end=today) and save every
intermediate to disk so the cross-endpoint audit can replay offline.
"""
import pickle
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_small_mid_cap import (
    IVOL_PRICE_HISTORY_PADDING_CALENDAR_DAYS,
    mask_recycled_ticker_prices,
)
from app.services.research_lab.small_cap_membership_history import get_universe_over

OUT = Path(__file__).parent / "sc600_fetch.pkl"

START = date(2020, 1, 1)
END = date(2026, 8, 27)

provider = YFinanceProvider()
universe = get_universe_over(START, END)
print(f"universe: {len(universe)} tickers", flush=True)

padded_start = START - timedelta(days=IVOL_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
print(f"padded_start={padded_start} end={END}", flush=True)

close, missing_price = provider.get_price_history(universe, padded_start, END)
print(f"price: {close.shape} missing={len(missing_price)}", flush=True)

cleaned, recycled, truncated = mask_recycled_ticker_prices({"close": close})
close_clean = cleaned["close"]
print(f"after recycled mask: {close_clean.shape} dropped={len(recycled)} truncated={len(truncated)}", flush=True)
print(f"recycled: {recycled}", flush=True)

priced = list(close_clean.columns)
mcap_close, splits, mcap_missing = provider.get_market_cap_basis(priced, padded_start, END)
print(f"mcap basis: {mcap_close.shape} splits={len(splits)} missing={len(mcap_missing)}", flush=True)

shares, missing_shares = provider.get_shares_outstanding(priced, padded_start, END)
print(f"shares: {len(shares)} resolved, {len(missing_shares)} missing", flush=True)

with OUT.open("wb") as fh:
    pickle.dump(
        {
            "start": START,
            "end": END,
            "padded_start": padded_start,
            "universe": universe,
            "close_raw": close,
            "close": close_clean,
            "missing_price": missing_price,
            "recycled": recycled,
            "truncated": truncated,
            "mcap_close": mcap_close,
            "splits": splits,
            "mcap_missing": mcap_missing,
            "shares": shares,
            "missing_shares": missing_shares,
        },
        fh,
    )
print(f"saved -> {OUT}", flush=True)
