"""Per-strategy circuit breaker: the rolling P&L ledger and its verdict."""

from datetime import date, timedelta

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
