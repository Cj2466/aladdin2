import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

import pandas as pd
import numpy as np

from app.services.research_lab.cross_sectional_ivol import (
    build_point_in_time_market_cap,
    signal_idiosyncratic_volatility,
    ROUND_D1_FAMILY,
)
from app.services.research_lab.cross_sectional import (
    _apply_weight_cap,
    _resolve_leg_weights,
    CrossSectionalData,
    MAX_WEIGHT_MULTIPLE,
)

print("=== TEST 1: family size ===")
print("len(ROUND_D1_FAMILY) =", len(ROUND_D1_FAMILY))
assert len(ROUND_D1_FAMILY) == 21

print("\n=== TEST 2: look-ahead safety in build_point_in_time_market_cap ===")
# Build a close frame with 10 consecutive trading days.
dates = pd.bdate_range("2024-01-02", periods=10)
close = pd.DataFrame({"AAA": np.linspace(100, 109, 10), "BBB": np.linspace(50, 59, 10)}, index=dates)

# AAA: share count known at day0 (=1000) and then a NEW filing at day7 (=2000).
# The gap between day0 and day7 (days 1..6) must ffill from day0's 1000, NEVER from day7's 2000.
shares_AAA = pd.Series([1000.0, 2000.0], index=[dates[0], dates[7]])
# BBB: no share data at all -> should end up in tickers_with_no_shares_data, all-NaN column.
shares = {"AAA": shares_AAA}

market_cap, no_shares = build_point_in_time_market_cap(close, shares)
print(market_cap)
print("no_shares:", no_shares)

# Check: days 1..6 (index 1..6) for AAA must equal 1000 * close, NOT 2000 * close.
for i in range(1, 7):
    expected = 1000.0 * close["AAA"].iloc[i]
    actual = market_cap["AAA"].iloc[i]
    assert actual == expected, f"LOOKAHEAD BUG at day {i}: expected {expected} (past shares), got {actual}"
    print(f"day {i} ({dates[i].date()}): market_cap={actual}, expected(past-only)={expected}  OK")

# Day 7 onward must switch to 2000
for i in range(7, 10):
    expected = 2000.0 * close["AAA"].iloc[i]
    actual = market_cap["AAA"].iloc[i]
    assert actual == expected, f"BUG at day {i}: expected {expected}, got {actual}"
    print(f"day {i} ({dates[i].date()}): market_cap={actual}, expected={expected}  OK (post-filing)")

# BBB should be all NaN
assert market_cap["BBB"].isna().all()
assert no_shares == ["BBB"]
print("BBB correctly all-NaN, in no_shares list.")

print("\n=== TEST 2b: adversarial -- share data STARTS in the future relative to formation date ===")
# CCC: only share data starting AFTER the whole close window (i.e. no known share count
# as of ANY of these formation dates. Must be all-NaN across the whole close index, not
# some garbage extrapolated backward value.
close3 = close.copy()
close3["CCC"] = np.linspace(20, 29, 10)
shares_future_only = pd.Series([5000.0], index=[dates[-1] + pd.Timedelta(days=5)])
mc2, no_shares2 = build_point_in_time_market_cap(close3, {"CCC": shares_future_only, "AAA": shares_AAA})
print(mc2["CCC"])
assert mc2["CCC"].isna().all(), "LOOKAHEAD BUG: future-only share date leaked backward into market cap"
print("CCC (share filing strictly after the whole window) correctly all-NaN across whole close index. OK")
# CCC has a raw series that's non-empty, so per docstring it should NOT be in tickers_with_no_shares_data
# (that list is only for None/empty). Check that claim:
print("no_shares2:", no_shares2)
assert "CCC" not in no_shares2, "CCC has real (if useless) share data -- should not appear in tickers_with_no_shares_data per docstring"
print("Confirms docstring claim: a non-empty-but-fully-future series is NOT flagged, silently produces all-NaN market cap -- POTENTIAL ISSUE (see summary).")

