import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

from app.services.research_lab.cross_sectional_patterns_d2 import (
    screen_d2_reversal_family,
    D2_HOLDING_DAYS,
    D2_COHORT_FORMATION_DAYS,
)
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START


_STALWART_MEMBERS = [
    "AAPL", "MSFT", "JPM", "JNJ", "KO", "PG", "XOM", "WMT", "MCD", "HD", "CAT", "MMM",
]


class _FakeProvider:
    def __init__(self, tickers_expected_member, seed=17):
        self.tickers = tickers_expected_member
        self.seed = seed
        self.requested = None

    def get_daily_ohlcv(self, tickers, start, end):
        self.requested = list(tickers)
        rng = np.random.default_rng(self.seed)
        index = pd.bdate_range(start, end)
        served = [t for t in tickers if t in self.tickers]
        close = pd.DataFrame(
            {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.015, len(index))) for t in served},
            index=index,
        )
        open_ = close * (1.0 + rng.normal(0.0, 0.004, close.shape))
        volume = pd.DataFrame(
            rng.integers(1_000_000, 5_000_000, close.shape).astype(float),
            index=index,
            columns=close.columns,
        )
        missing = [t for t in tickers if t not in served]
        return {"open": open_, "close": close, "volume": volume}, missing


provider = _FakeProvider(_STALWART_MEMBERS)
today = date(2026, 8, 26)
summary = screen_d2_reversal_family(MEMBERSHIP_DATA_START, today, provider=provider)

print("n_trading_days_replayed:", summary.independent_window_disclosure.n_trading_days_replayed)
print("holding_days:", summary.independent_window_disclosure.holding_days)
print("n_full_independent_windows:", summary.independent_window_disclosure.n_full_independent_windows)
print("partial_window_fraction:", summary.independent_window_disclosure.partial_window_fraction)
print()
print(summary.independent_window_disclosure.text)
print()
print("n results:", len(summary.results))
for r in summary.results:
    print(r.pattern_id, "sharpe=", round(r.sharpe_annualized, 3), "dsr=", r.deflated_sharpe.dsr,
          "dsr_floor_met=", r.deflated_sharpe.dsr_floor_met, "n_trials=", r.deflated_sharpe.n_trials,
          "psr_vs_zero=", r.deflated_sharpe.psr_vs_zero)
