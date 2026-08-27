"""Diagnostic: WHY did magnitude-weighting help lps_intraday_l252_h63 but
hurt cgo_ls_decile_l252_h126? For every formation of both patterns, record
each leg member's (weight_within_leg, its own forward cumulative return
over that hold) and correlate them. If magnitude-weighting is picking up
genuine information, weight should positively correlate with the long
leg's forward return and negatively with the short leg's (i.e. the more
extreme members should also be the better/worse performers) -- not just
asserted, actually measured against the real data."""
import sys
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    _leg_weights,
    select_leg_tickers,
)
from app.services.research_lab.cross_sectional_patterns import (
    PRICE_HISTORY_PADDING_CALENDAR_DAYS,
    ROUND_C_FAMILY,
)
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
    was_member,
)
from datetime import timedelta

START = MEMBERSHIP_DATA_START
END = date.today()
TARGET_IDS = ["lps_intraday_l252_h63", "cgo_ls_decile_l252_h126"]

print("Fetching universe + price data (same window as the two production runs)...", flush=True)
universe = get_universe_over(START, END)
provider = YFinanceProvider()
padded_start = START - timedelta(days=PRICE_HISTORY_PADDING_CALENDAR_DAYS)
frames, missing = provider.get_daily_ohlcv(universe, padded_start, END)
print(f"Resolved {len(frames['close'].columns)} tickers, {len(missing)} missing", flush=True)

data = CrossSectionalData(close=frames["close"], open=frames["open"], volume=frames["volume"])
index = data.close.index
n = len(index)
daily_returns_all = data.close.pct_change(fill_method=None)

specs_by_id = {s.pattern_id: s for s in ROUND_C_FAMILY}

for pattern_id in TARGET_IDS:
    spec = specs_by_id[pattern_id]
    print(f"\n=== {pattern_id} ===", flush=True)

    first_formation = spec.lookback_days
    eligible_positions = np.flatnonzero(index.date >= START)
    first_formation = max(first_formation, int(eligible_positions[0]))

    long_pairs: list[tuple[float, float]] = []  # (weight_within_leg, forward_cum_return)
    short_pairs: list[tuple[float, float]] = []
    n_formations_used = 0

    for i in range(first_formation, n - 1, spec.holding_days):
        formation_ts = index[i]
        formation_day = formation_ts.date()
        formation_close = data.close.iloc[i]
        eligible = [
            t for t in data.close.columns if was_member(t, formation_day) and np.isfinite(formation_close[t])
        ]
        if not eligible:
            continue
        row_start = max(0, i + 1 - spec.lookback_days)
        view = CrossSectionalData(
            close=data.close.iloc[row_start : i + 1].loc[:, eligible],
            open=data.open.iloc[row_start : i + 1].loc[:, eligible] if spec.requires_open else None,
            volume=data.volume.iloc[row_start : i + 1].loc[:, eligible] if spec.requires_volume else None,
        )
        signal = spec.signal_fn(view)
        top, bottom = select_leg_tickers(signal, spec.rank_fraction)
        n_ranked = int(signal.dropna().shape[0])
        n_leg = len(top)
        if n_leg < 5 or 2 * n_leg > n_ranked:
            continue

        long_w = _leg_weights(top, signal, higher_is_stronger=True)
        short_w = _leg_weights(bottom, signal, higher_is_stronger=False)

        hold_end = min(i + spec.holding_days, n - 1)
        # Forward cumulative return per ticker over the hold (close[hold_end]/close[i] - 1),
        # skipping tickers with no valid end price (delisted mid-hold).
        start_px = data.close.iloc[i]
        end_px = data.close.iloc[hold_end]
        fwd_ret = (end_px / start_px) - 1.0

        for t, w in long_w.items():
            r = fwd_ret.get(t)
            if r is not None and np.isfinite(r):
                long_pairs.append((w, float(r)))
        for t, w in short_w.items():
            r = fwd_ret.get(t)
            if r is not None and np.isfinite(r):
                short_pairs.append((w, float(r)))
        n_formations_used += 1

    print(f"formations used: {n_formations_used}, long obs: {len(long_pairs)}, short obs: {len(short_pairs)}")

    for leg_name, pairs in (("LONG", long_pairs), ("SHORT", short_pairs)):
        if len(pairs) < 10:
            print(f"  {leg_name}: too few observations")
            continue
        w = np.array([p[0] for p in pairs])
        r = np.array([p[1] for p in pairs])
        corr = float(np.corrcoef(w, r)[0, 1])
        # Split into "extreme" (top quartile of weight) vs "marginal" (bottom quartile)
        # within this leg, compare mean forward return.
        q75 = np.quantile(w, 0.75)
        q25 = np.quantile(w, 0.25)
        extreme_mean = r[w >= q75].mean()
        marginal_mean = r[w <= q25].mean()
        print(
            f"  {leg_name}: corr(weight, fwd_return)={corr:+.4f}  "
            f"extreme-quartile mean fwd ret={extreme_mean:+.4%}  "
            f"marginal-quartile mean fwd ret={marginal_mean:+.4%}  "
            f"(n={len(pairs)})"
        )

print("\nDone.", flush=True)
