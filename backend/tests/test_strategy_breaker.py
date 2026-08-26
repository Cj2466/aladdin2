"""Per-strategy circuit breaker: the rolling P&L ledger and its verdict."""

import math
from datetime import date, timedelta

import pandas as pd
import pytest

from app.services.execution import strategy_breaker


def _days(returns: list[float], *, capital: float = 1000.0) -> list[dict]:
    start = date(2026, 1, 5)
    return [
        {
            "date": (start + timedelta(days=i)).isoformat(),
            "pnl": r * capital,
            "return": r,
            "allocated_capital": capital,
        }
        for i, r in enumerate(returns)
    ]


# --- the ledger ---------------------------------------------------------------


def test_same_trading_day_is_updated_in_place_not_appended():
    """The runner ticks ~390 times a session. Appending would let 20 ticks of
    one bad minute trip a "20-day" breaker."""
    day_pnl: list[dict] = []
    for pnl in (-5.0, -8.0, -11.0):
        day_pnl = strategy_breaker.append_or_update_day(
            day_pnl, trade_date=date(2026, 3, 2), pnl=pnl, allocated_capital=1000.0
        )
    assert len(day_pnl) == 1
    assert day_pnl[0]["pnl"] == pytest.approx(-11.0)


def test_a_new_trading_day_appends():
    day_pnl = strategy_breaker.append_or_update_day(
        [], trade_date=date(2026, 3, 2), pnl=1.0, allocated_capital=1000.0
    )
    day_pnl = strategy_breaker.append_or_update_day(
        day_pnl, trade_date=date(2026, 3, 3), pnl=2.0, allocated_capital=1000.0
    )
    assert [d["date"] for d in day_pnl] == ["2026-03-02", "2026-03-03"]


def test_return_is_pnl_over_allocated_capital():
    day_pnl = strategy_breaker.append_or_update_day(
        [], trade_date=date(2026, 3, 2), pnl=-25.0, allocated_capital=1000.0
    )
    assert day_pnl[0]["return"] == pytest.approx(-0.025)


def test_zero_allocated_capital_does_not_divide_by_zero():
    day_pnl = strategy_breaker.append_or_update_day(
        [], trade_date=date(2026, 3, 2), pnl=-25.0, allocated_capital=0.0
    )
    assert day_pnl[0]["return"] == 0.0


def test_history_is_trimmed_to_a_bounded_length():
    day_pnl: list[dict] = []
    start = date(2026, 1, 1)
    for i in range(strategy_breaker.DAY_PNL_HISTORY_LIMIT + 40):
        day_pnl = strategy_breaker.append_or_update_day(
            day_pnl, trade_date=start + timedelta(days=i), pnl=1.0, allocated_capital=1000.0
        )
    assert len(day_pnl) == strategy_breaker.DAY_PNL_HISTORY_LIMIT


def test_corrupt_json_reads_as_an_empty_ledger_rather_than_raising():
    assert strategy_breaker.load_day_pnl("not json") == []
    assert strategy_breaker.load_day_pnl(None) == []
    assert strategy_breaker.load_day_pnl('{"not": "a list"}') == []


# --- the verdict --------------------------------------------------------------


def test_never_fires_below_the_minimum_sample():
    """"Not enough data to judge, so don't" — the same convention
    check_underperformance already applies."""
    catastrophic = _days([-0.05] * (strategy_breaker.BREAKER_MIN_DAYS_TO_JUDGE - 1))
    verdict = strategy_breaker.evaluate(catastrophic)
    assert verdict.breached is False
    assert verdict.trailing_sharpe is None


def test_a_persistently_losing_strategy_breaches():
    verdict = strategy_breaker.evaluate(_days([-0.004] * 25))
    assert verdict.breached is True
    assert verdict.trailing_sharpe is not None
    assert verdict.trailing_sharpe <= strategy_breaker.BREAKER_SHARPE_THRESHOLD
    assert verdict.trailing_return is not None and verdict.trailing_return < 0


def test_a_profitable_strategy_does_not_breach():
    verdict = strategy_breaker.evaluate(_days([0.003] * 25))
    assert verdict.breached is False


def test_the_window_is_trailing_so_an_old_good_run_cannot_mask_a_recent_bad_one():
    """Deliberately trailing, not all-time cumulative — the same reasoning
    check_underperformance documents."""
    history = _days([0.02] * 60 + [-0.004] * 25)
    all_time_positive = sum(d["return"] for d in history) > 0
    assert all_time_positive
    assert strategy_breaker.evaluate(history).breached is True


def test_only_the_lookback_window_is_measured():
    history = _days([-0.05] * 40 + [0.003] * 25)
    verdict = strategy_breaker.evaluate(history)
    assert verdict.trailing_days == strategy_breaker.BREAKER_LOOKBACK_TRADING_DAYS
    assert verdict.breached is False


def test_flat_zero_pnl_does_not_breach():
    """A strategy that is simply flat (no position, no P&L) must not be pulled
    — a zero-variance series has no meaningful Sharpe to judge."""
    verdict = strategy_breaker.evaluate(_days([0.0] * 25))
    assert verdict.breached is False


# --- the zero/near-zero-variance degenerate case -------------------------------
#
# metrics.sharpe_ratio() returns exactly 0.0 (not negative) whenever the
# trailing window's variance is (numerically) zero, by its own documented
# convention. Fed straight into `sharpe <= BREAKER_SHARPE_THRESHOLD`
# (-1.0), 0.0 never crosses a negative threshold — so, without the explicit
# degenerate-case handling in evaluate(), a strategy losing the exact same
# amount every single day, with no variance at all, would NEVER trip this
# breaker no matter how long the bleed continued. A steady loss like that is
# not "Sharpe-neutral": it is a certain, unvarying loss, which is a worse
# signal than the noisy losses the -1.0 threshold is calibrated to catch.
#
# -0.0078125 (= -1/128) is used rather than an arbitrary decimal like
# -0.004 because it is exactly representable in binary floating point, so
# twenty (or any number of) identical copies of it sum and average back to
# themselves exactly — the trailing window's pandas-computed std(ddof=1) is
# guaranteed to land on precisely 0.0, not on some incidental tiny nonzero
# float noise. That makes this a deterministic reproduction of the audit
# gap, independent of which floating-point rounding a given repeated
# decimal happens to produce (see test_a_persistently_losing_strategy_breaches
# above, whose repeated -0.004 already had a nonzero-but-tiny std purely by
# floating-point accident — passing today, but not for a robust reason).


def test_a_steady_exactly_zero_variance_flat_loss_trips_the_breaker():
    """The core regression: a constant, riskless, every-single-day loss
    (guaranteed exactly-zero variance by construction) must be an automatic
    breach — this is the exact scenario the audit found silently slipping
    through a Sharpe-of-0.0 comparison against a negative threshold."""
    flat_bleed = _days([-0.0078125] * 25)
    trailing = pd.Series([row["return"] for row in flat_bleed[-strategy_breaker.BREAKER_LOOKBACK_TRADING_DAYS:]])
    assert trailing.std(ddof=1) == 0.0  # sanity-check the fixture is truly degenerate, not just tiny

    verdict = strategy_breaker.evaluate(flat_bleed)

    assert verdict.breached is True
    assert verdict.trailing_sharpe == float("-inf")
    assert verdict.trailing_return is not None and verdict.trailing_return < 0


def test_a_steady_exactly_zero_variance_flat_gain_does_not_breach():
    """The mirror case: a constant, riskless, every-single-day GAIN (same
    exactly-zero variance) must NOT be treated as a breach — the fix must be
    keyed off the sign of the flat P&L, not off variance being near zero on
    its own."""
    flat_gain = _days([0.0078125] * 25)
    trailing = pd.Series([row["return"] for row in flat_gain[-strategy_breaker.BREAKER_LOOKBACK_TRADING_DAYS:]])
    assert trailing.std(ddof=1) == 0.0

    verdict = strategy_breaker.evaluate(flat_gain)

    assert verdict.breached is False


def test_near_zero_but_not_exactly_zero_variance_flat_loss_still_breaches():
    """Guards against a narrower fix that only special-cases literal
    `std == 0.0`: real floating-point noise on a repeated-decimal loss (as
    seen with -0.004, whose 20-day std computes to ~8.9e-19, not exactly
    0.0) must still count as the degenerate case, not silently fall through
    to a coincidentally-huge-but-fragile Sharpe value."""
    verdict = strategy_breaker.evaluate(_days([-0.004] * 25))
    assert verdict.breached is True
    assert verdict.trailing_sharpe == float("-inf")


# --- normal, real-variance P&L is unaffected ------------------------------------
#
# The degenerate-case branch must only fire when variance is genuinely
# (numerically) negligible. These fixtures have real day-to-day variance —
# far above NEAR_ZERO_VARIANCE_STD — so they must be decided exactly as
# before: by comparing metrics.sharpe_ratio() against BREAKER_SHARPE_THRESHOLD.


def _noisy_returns(shift: float) -> list[float]:
    base = [0.02, -0.02, 0.015, -0.015, 0.01, -0.01, 0.025, -0.025, 0.005, -0.005] * 2
    return [v - shift for v in base]


def test_real_variance_persistently_losing_strategy_still_breaches():
    returns = _noisy_returns(shift=0.012)  # mean -1.2%/day, real ~1.7% daily std
    day_pnl = _days(returns)
    trailing = pd.Series(returns[-strategy_breaker.BREAKER_LOOKBACK_TRADING_DAYS:])
    assert trailing.std(ddof=1) > strategy_breaker.NEAR_ZERO_VARIANCE_STD * 1000  # genuinely noisy, not degenerate

    verdict = strategy_breaker.evaluate(day_pnl)

    assert verdict.breached is True
    assert verdict.trailing_sharpe is not None and math.isfinite(verdict.trailing_sharpe)
    assert verdict.trailing_sharpe <= strategy_breaker.BREAKER_SHARPE_THRESHOLD


def test_real_variance_mildly_losing_strategy_still_does_not_breach():
    """A noisy strategy that is losing a little, but not badly enough to
    cross the Sharpe threshold, must still be left alone — the new
    degenerate-case check must not make the breaker more trigger-happy for
    ordinary noisy P&L."""
    returns = _noisy_returns(shift=0.001)  # mean -0.1%/day, same real ~1.7% daily std
    day_pnl = _days(returns)
    trailing = pd.Series(returns[-strategy_breaker.BREAKER_LOOKBACK_TRADING_DAYS:])
    assert trailing.std(ddof=1) > strategy_breaker.NEAR_ZERO_VARIANCE_STD * 1000

    verdict = strategy_breaker.evaluate(day_pnl)

    assert verdict.breached is False
    assert verdict.trailing_sharpe is not None and math.isfinite(verdict.trailing_sharpe)
    assert verdict.trailing_sharpe > strategy_breaker.BREAKER_SHARPE_THRESHOLD
