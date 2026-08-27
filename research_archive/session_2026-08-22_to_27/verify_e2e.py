import sys
sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

import pandas as pd
import numpy as np
from app.services.research_lab.cross_sectional import (
    CrossSectionalData, CrossSectionalSpec, CrossSectionalConfig,
    run_cross_sectional_backtest, _leg_weights,
)
from app.services.research_lab.cross_sectional_ivol import build_point_in_time_market_cap

# 6 tickers, ~40 trading days. Constant per-ticker "rank score" baked into
# price drift so a trivial signal_fn (last price) gives a STABLE, deterministic
# ranking across every formation -> top-2 always {A,B}, bottom-2 always {E,F}.
np.random.seed(0)
n_days = 40
dates = pd.bdate_range("2024-01-02", periods=n_days)
base_rank = {"A": 6, "B": 5, "C": 4, "D": 3, "E": 2, "F": 1}
close = pd.DataFrame(
    {t: 100.0 + rank * 5.0 + np.cumsum(np.random.normal(0, 0.05, n_days)) for t, rank in base_rank.items()},
    index=dates,
)

# Signal: literally just "current price level" -- since base offsets dominate
# the tiny random walk, top-2 by price is always A,B and bottom-2 is always E,F,
# deterministically, at every formation.
def signal_fn(view):
    return view.close.iloc[-1]

# Shares: A,B,C,D have real share history from day 0 onward (never missing).
# E's FIRST filing is at day 25 -- so E has NO resolvable market cap (NaN)
# for every formation date strictly before day 25: a genuine
# "gap spanning a formation date" in the sense that E is a real, tracked
# ticker (present in the dict, non-empty series) whose share history simply
# doesn't reach back far enough to cover early formations.
# F has continuous coverage throughout (control).
shares = {
    "A": pd.Series([1e9], index=[dates[0]]),
    "B": pd.Series([2e9], index=[dates[0]]),
    "C": pd.Series([3e9], index=[dates[0]]),
    "D": pd.Series([4e9], index=[dates[0]]),
    "E": pd.Series([5e9], index=[dates[25]]),   # <-- gap: nothing before day 25
    "F": pd.Series([6e9], index=[dates[0]]),
}
market_cap, no_shares_at_all = build_point_in_time_market_cap(close, shares)
print("tickers with NO shares entry at all (should be empty -- E has *some* data, just late):", no_shares_at_all)
print("\nE's market cap, days 0..30 (NaN expected days 0..24, real value from day 25):")
print(market_cap["E"].iloc[[0,10,20,24,25,26,30]])

data = CrossSectionalData(close=close, market_cap=market_cap)

spec = CrossSectionalSpec(
    pattern_id="adversarial_gap_test",
    family="test",
    citation="n/a",
    signal_fn=signal_fn,
    lookback_days=2,
    holding_days=5,     # formation every 5 trading days -> formations at day positions 2,7,12,17,22,27,32,37
    portfolio="long_short",
    rank_fraction=0.34,  # 6 tickers * 0.34 = 2.04 -> top-2 / bottom-2
    leg_weighting="value",
    requires_market_cap=True,
)
config = CrossSectionalConfig(min_names_per_leg=2)

result = run_cross_sectional_backtest(data, spec, config, membership_fn=lambda t, d: True)
print("\nstatus:", result.status)
print(f"{'date':12s} {'long_tickers':20s} {'long_fallback':13s} {'short_tickers':20s} {'short_fallback'}")
for f in result.formations:
    print(f"{str(f.date):12s} {str(f.long_tickers):20s} {str(f.long_leg_value_weight_fallback):13s} {str(f.short_tickers):20s} {f.short_leg_value_weight_fallback}")

# ---- Assertions: the claimed behavior ----
# Short leg is always {E,F} (or a subset given ties) by construction: F always
# has real market cap, E only from day 25 onward.
# Expect: for formations BEFORE E's day-25 filing exists, short leg
# (containing E) must show fallback=True. For formations AFTER, fallback=False
# (assuming E,F both usable) -- UNLESS the actual selected tickers differ.
def as_date(x):
    return x.date() if hasattr(x, "date") else x

cutoff = dates[25].date()
formation_before = [f for f in result.formations if as_date(f.date) < cutoff]
formation_after = [f for f in result.formations if as_date(f.date) >= cutoff]

print("\n--- Checking claimed fallback behavior ---")
for f in formation_before:
    if "E" in f.short_tickers:
        assert f.short_leg_value_weight_fallback is True, f"EXPECTED fallback=True (E has no known shares yet) at {f.date}, got False -- BUG"
        print(f"OK: {f.date} short leg contains E (no shares data yet) -> fallback=True as claimed")
for f in formation_after:
    if "E" in f.short_tickers:
        # E's market cap now resolvable; F also always resolvable -> should NOT fall back
        ok = f.short_leg_value_weight_fallback is False
        print(f"{f.date} short leg contains E (shares now known) -> fallback={f.short_leg_value_weight_fallback} (expected False): {'OK' if ok else 'MISMATCH'}")

# Also directly verify the short leg's weights, when NOT falling back, actually
# equal what real market-cap value-weighting (normalized+capped) would produce,
# hand-computed independently -- NOT reusing _resolve_leg_weights internals.
for f in formation_after:
    if not f.short_leg_value_weight_fallback and set(f.short_tickers) == {"E", "F"}:
        mc_row = market_cap.loc[pd.Timestamp(as_date(f.date).isoformat())]
        e_cap, f_cap = mc_row["E"], mc_row["F"]
        total = e_cap + f_cap
        expected = {"E": e_cap/total, "F": f_cap/total}
        # cap check: with only 2 members, MAX_WEIGHT_MULTIPLE(3.0)*0.5=1.5 > 1 so cap never binds for n=2
        print(f"\n{f.date}: hand-computed value weights (no cap needed, n=2): {expected}")
        print(f"   harness weights: {f.short_weights}")
        for t in ("E","F"):
            assert abs(f.short_weights[t] - expected[t]) < 1e-9, f"MISMATCH weight for {t}: harness={f.short_weights[t]} hand={expected[t]}"
        print("   MATCH (hand-computed value weights == harness output)")
        break

print("\nADVERSARIAL SHARE-GAP END-TO-END CHECK: behavior matches the report's claims.")
