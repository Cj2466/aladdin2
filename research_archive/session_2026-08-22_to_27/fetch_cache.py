"""Fetch and cache the real yfinance data the buyback family needs, ONCE.

The per-ticker get_shares_full loop over ~716 tickers is the expensive part
(one network call each). Caching lets constant-calibration measurements and
the production screening run share a single fetch.
"""
import pickle
import sys
import time
import warnings
from datetime import date

warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/wf_d605a76f-0be-2/backend")

from app.services.market_data.yfinance_provider import YFinanceProvider  # noqa: E402
from app.services.research_lab.sp500_membership_history import get_universe_over  # noqa: E402

OUT = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"

END = date(2026, 8, 27)
FETCH_START = date(2015, 1, 1)

provider = YFinanceProvider()
universe = get_universe_over(date(2017, 1, 1), END)
print(f"universe: {len(universe)} tickers", flush=True)

t0 = time.time()
close, missing_price = provider.get_price_history(universe, FETCH_START, END)
print(f"prices: {close.shape} missing={len(missing_price)} in {time.time()-t0:.0f}s", flush=True)
with open(f"{OUT}/close.pkl", "wb") as f:
    pickle.dump({"close": close, "missing_price": missing_price, "universe": universe}, f)

priced = list(close.columns)
t0 = time.time()
mcap_close, splits, missing_basis = provider.get_market_cap_basis(priced, FETCH_START, END)
print(f"basis: {mcap_close.shape} splits_tickers={len(splits)} missing={len(missing_basis)} in {time.time()-t0:.0f}s", flush=True)
with open(f"{OUT}/splits.pkl", "wb") as f:
    pickle.dump({"splits": splits, "mcap_close": mcap_close, "missing_basis": missing_basis}, f)

t0 = time.time()
shares, missing_shares = provider.get_shares_outstanding(priced, FETCH_START, END)
print(f"shares: {len(shares)} resolved, {len(missing_shares)} missing in {time.time()-t0:.0f}s", flush=True)
with open(f"{OUT}/shares.pkl", "wb") as f:
    pickle.dump({"shares": shares, "missing_shares": missing_shares}, f)

print("DONE", flush=True)
