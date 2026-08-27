"""The SAME fetch Build D1's production entry point makes on the S&P 500,
saved so the small-cap contamination RATE can be compared against the
large-cap one under identical code and identical thresholds.
"""
import pickle
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_ivol import (
    PRICE_HISTORY_PADDING_CALENDAR_DAYS,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)

OUT = Path(__file__).parent / "d1_fetch.pkl"

START = MEMBERSHIP_DATA_START  # 2015-01-07, run_round_d1_screening's own floor
END = date(2026, 8, 27)

provider = YFinanceProvider()
universe = get_universe_over(START, END)
print(f"universe: {len(universe)} tickers", flush=True)

padded_start = START - timedelta(days=PRICE_HISTORY_PADDING_CALENDAR_DAYS)
print(f"padded_start={padded_start} end={END}", flush=True)

close, missing_price = provider.get_price_history(universe, padded_start, END)
print(f"price: {close.shape} missing={len(missing_price)}", flush=True)

priced = list(close.columns)
mcap_close, splits, mcap_missing = provider.get_market_cap_basis(priced, padded_start, END)
print(f"mcap basis: {mcap_close.shape} splits={len(splits)}", flush=True)

shares, missing_shares = provider.get_shares_outstanding(priced, padded_start, END)
print(f"shares: {len(shares)} resolved, {len(missing_shares)} missing", flush=True)

with OUT.open("wb") as fh:
    pickle.dump(
        {
            "start": START,
            "end": END,
            "padded_start": padded_start,
            "universe": universe,
            "close": close,
            "missing_price": missing_price,
            "mcap_close": mcap_close,
            "splits": splits,
            "mcap_missing": mcap_missing,
            "shares": shares,
            "missing_shares": missing_shares,
        },
        fh,
    )
print(f"saved -> {OUT}", flush=True)
