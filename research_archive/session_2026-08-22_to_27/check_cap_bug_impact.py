"""Did the already-reported Round C magnitude-weighted production run
(DSR 0.203 for lps_intraday_l252_h63) actually hit the _apply_weight_cap
convergence bug? Replay the SAME real formations with BOTH the old buggy
inline cap loop (from commit 52a453a, the code that actually ran) and the
new fixed _apply_weight_cap, using the exact same real price data fetched
once, and diff every single formation's resulting weights."""
import sys
from datetime import date, timedelta

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    MAX_WEIGHT_MULTIPLE,
    MIN_RELATIVE_WEIGHT_FRACTION,
    CrossSectionalData,
    _apply_weight_cap,
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


def old_buggy_leg_weights(tickers, signal, *, higher_is_stronger):
    """Verbatim from commit 52a453a -- the code that actually produced the
    already-reported weighted Round C numbers."""
    if not tickers:
        return {}
    if len(tickers) == 1:
        return {tickers[0]: 1.0}
    values = signal.reindex(tickers)
    boundary = values.min() if higher_is_stronger else values.max()
    excess = (values - boundary) if higher_is_stronger else (boundary - values)
    excess = excess.clip(lower=0.0)
    spread = float(excess.max())
    equal_share = 1.0 / len(tickers)
    if spread <= 0.0 or not np.isfinite(spread):
        return {t: equal_share for t in tickers}
    floor = spread * MIN_RELATIVE_WEIGHT_FRACTION
    raw = {t: max(float(excess[t]), floor) for t in tickers}
    total = sum(raw.values())
    weights = {t: w / total for t, w in raw.items()}
    cap = MAX_WEIGHT_MULTIPLE * equal_share
    for _ in range(len(weights)):
        over = {t: w for t, w in weights.items() if w > cap}
        if not over:
            break
        excess_to_redistribute = sum(w - cap for w in over.values())
        under = {t: w for t, w in weights.items() if w <= cap}
        under_total = sum(under.values())
        for t in over:
            weights[t] = cap
        if under_total > 0.0:
            for t in under:
                weights[t] += excess_to_redistribute * (under[t] / under_total)
    return weights


def new_fixed_leg_weights(tickers, signal, *, higher_is_stronger):
    """Current code's raw-weight construction, but calling the NEW fixed
    _apply_weight_cap instead of the old inline loop."""
    if not tickers:
        return {}
    if len(tickers) == 1:
        return {tickers[0]: 1.0}
    values = signal.reindex(tickers)
    boundary = values.min() if higher_is_stronger else values.max()
    excess = (values - boundary) if higher_is_stronger else (boundary - values)
    excess = excess.clip(lower=0.0)
    spread = float(excess.max())
    equal_share = 1.0 / len(tickers)
    if spread <= 0.0 or not np.isfinite(spread):
        return {t: equal_share for t in tickers}
    floor = spread * MIN_RELATIVE_WEIGHT_FRACTION
    raw = {t: max(float(excess[t]), floor) for t in tickers}
    return _apply_weight_cap(raw)


START = MEMBERSHIP_DATA_START
END = date.today()

print("Fetching the SAME real universe/price data used in the actual weighted Round C run...", flush=True)
universe = get_universe_over(START, END)
provider = YFinanceProvider()
padded_start = START - timedelta(days=PRICE_HISTORY_PADDING_CALENDAR_DAYS)
frames, missing = provider.get_daily_ohlcv(universe, padded_start, END)
print(f"Resolved {len(frames['close'].columns)} tickers, {len(missing)} missing", flush=True)

data = CrossSectionalData(close=frames["close"], open=frames["open"], volume=frames["volume"])
index = data.close.index
n = len(index)

total_formations = 0
total_diffs = 0
max_diff_pct = 0.0
diff_examples = []

for spec in ROUND_C_FAMILY:
    first_formation = spec.lookback_days
    eligible_positions = np.flatnonzero(index.date >= START)
    first_formation = max(first_formation, int(eligible_positions[0]))

    for i in range(first_formation, n - 1, spec.holding_days):
        formation_ts = index[i]
        formation_day = formation_ts.date()
        formation_close = data.close.iloc[i]
        eligible = [t for t in data.close.columns if was_member(t, formation_day) and np.isfinite(formation_close[t])]
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

        for tickers, higher in ((top, True), (bottom, False)):
            total_formations += 1
            old_w = old_buggy_leg_weights(tickers, signal, higher_is_stronger=higher)
            new_w = new_fixed_leg_weights(tickers, signal, higher_is_stronger=higher)
            for t in tickers:
                d = abs(old_w.get(t, 0.0) - new_w.get(t, 0.0))
                if d > 1e-9:
                    total_diffs += 1
                    pct = d * 100
                    max_diff_pct = max(max_diff_pct, pct)
                    if len(diff_examples) < 10:
                        diff_examples.append((spec.pattern_id, formation_day, t, old_w.get(t, 0.0), new_w.get(t, 0.0)))

print(f"\nTotal leg-formations checked (across all 30 patterns, both legs): {total_formations}")
print(f"Total individual ticker-weight diffs found: {total_diffs}")
print(f"Max weight difference: {max_diff_pct:.4f} percentage points")
if diff_examples:
    print("\nExample diffs (pattern, formation_day, ticker, old_weight, new_weight):")
    for ex in diff_examples:
        print(" ", ex)
else:
    print("\nNo differences found -- the bug never fired for this actual dataset/family. Already-reported numbers are safe.")
