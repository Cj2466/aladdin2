import numpy as np
import pandas as pd

from app.services.research_lab.engine import DayResult, Trade

# The EQUITY/BOND/FX/COMMODITY calendar: ~252 exchange sessions a year.
# Deliberately left as a module-level constant AND as sharpe_ratio's default
# rather than being generalized away, because it is imported directly by
# deflated_sharpe.py and sharpe_robustness.py; changing this value would
# silently move every number those modules produce.
TRADING_DAYS_PER_YEAR = 252

# 24/7/365 markets — crypto. Verified live 2026-08-27 against yfinance:
# BTC-USD returns 365/365/366/365/365/365/366/365 rows for 2018..2025 with
# ZERO missing calendar days, against SPY's 251/252/253/252/251/250/252/250.
# Annualizing a 365-row-per-year return series with sqrt(252) understates
# its Sharpe by sqrt(252/365) = 0.831 (a ~17% understatement) and its
# annualized mean return by 252/365 (a ~31% understatement).
CALENDAR_DAYS_PER_YEAR = 365


def sharpe_ratio(returns: pd.Series, *, periods_per_year: float = TRADING_DAYS_PER_YEAR) -> float:
    """No risk-free-rate subtraction — this is a self-financing,
    dollar-neutral position (long one leg, short the other), unlike
    optimizer.py's long-only portfolio Sharpe which does subtract it.

    periods_per_year is the number of return observations a YEAR of this
    instrument's data contains, and it must match the series actually being
    passed: a daily equity series has ~252 of them, a daily CRYPTO series has
    365-366 (crypto has no market holidays and no weekends — see
    CALENDAR_DAYS_PER_YEAR for the live verification). Keyword-only and
    defaulted to TRADING_DAYS_PER_YEAR so every existing caller — equity,
    bond, FX and commodity families alike — is byte-for-byte unaffected; a
    365-day-a-year family passes it explicitly."""
    std = returns.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(returns.mean() / std * np.sqrt(periods_per_year))


def max_drawdown(equity_curve: pd.Series) -> float:
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1.0
    return float(drawdown.min()) if len(drawdown) else 0.0


def hit_rate(trades: list[Trade]) -> float | None:
    closed = [t for t in trades if not t.still_open]
    if not closed:
        return None
    wins = sum(1 for t in closed if t.trade_return > 0)
    return wins / len(closed)


def exposure_pct(day_results: list[DayResult]) -> float:
    if not day_results:
        return 0.0
    active = sum(1 for d in day_results if d.position != 0)
    return active / len(day_results)


def total_cost_drag(day_results: list[DayResult]) -> float:
    return float(sum(d.cost for d in day_results))
