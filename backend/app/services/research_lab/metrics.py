import numpy as np
import pandas as pd

from app.services.research_lab.engine import DayResult, Trade

TRADING_DAYS_PER_YEAR = 252


def sharpe_ratio(returns: pd.Series) -> float:
    """No risk-free-rate subtraction — this is a self-financing,
    dollar-neutral position (long one leg, short the other), unlike
    optimizer.py's long-only portfolio Sharpe which does subtract it."""
    std = returns.std(ddof=1)
    if std == 0 or not np.isfinite(std):
        return 0.0
    return float(returns.mean() / std * np.sqrt(TRADING_DAYS_PER_YEAR))


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
