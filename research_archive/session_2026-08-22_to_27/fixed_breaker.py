"""Per-strategy circuit breaker — the second, independent layer of live-risk
control, sitting under the account-wide daily-loss breaker.

Why a second layer at all. The account-wide breaker reads Alpaca's own
equity/last_equity and halts EVERYTHING when the account's own P&L breaches a
threshold. That is necessary but not sufficient: with several strategies
running simultaneously, one broken strategy — bad fill logic, a stale signal, a
data glitch specific to one ticker or pair — can do real damage while the
account's aggregate P&L stays comfortably inside its limit, because the other
strategies mask it. A per-strategy layer bounds how long a single broken
strategy can bleed before a human looks at it.

This is the live-execution analogue of the already-shipped
forward_validation_service.check_underperformance / "underperforming" status:
same trailing-window Sharpe shape, same "not enough data to judge, so don't"
floor, same deliberately-not-auto-reversible posture. What differs is the input
(real broker P&L on real fills, not backtest day-results) and the window (see
below), and what tripping it does: it stops NEW orders for that one strategy
and leaves its existing positions completely alone — the same "don't
force-liquidate during the triggering event" philosophy as the account-wide
breaker.
"""

import json
import logging
import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.services.research_lab import metrics

logger = logging.getLogger(__name__)

# Reuses this codebase's own MIN_FORWARD_DAYS_FOR_SHARPE = 20 — the smallest
# sample it has already committed to as the floor at which it is willing to
# quote a Sharpe at all ("a Sharpe computed off a handful of daily returns
# misrepresents precision the data can't support"). Not independently
# calibrated here; it is that existing convention applied at the
# live-execution layer.
#
# Deliberately NOT forward validation's 60 days. That number exists because 60
# is MIN_OUT_OF_SAMPLE_TRADING_DAYS, the floor below which a *research* result
# is meaningless — and waiting three months before pulling a strategy that is
# actively losing real money defeats the entire point of a circuit breaker.
BREAKER_LOOKBACK_TRADING_DAYS = 20

# Same "not enough data to judge, so don't" convention as
# check_underperformance's own floor: below this many recorded days the breaker
# never fires, regardless of how bad the few days look.
BREAKER_MIN_DAYS_TO_JUDGE = 20

# A risk-tolerance judgment call, stated honestly as such — and, unlike
# check_underperformance's -0.5, it is NOT even approximately a significance
# test, which matters enough to spell out:
#
#   The standard error of an annualized Sharpe is roughly
#   sqrt((1 + S^2/2)/n) * sqrt(252). At n = 20 and S ~ 0 that is
#   sqrt(1/20) * 15.87 ~= 3.55. So an annualized Sharpe of -1.0 over 20 days
#   sits about 0.28 SE below zero: statistically indistinguishable from noise.
#
# That is deliberate, not an oversight. This threshold is not trying to prove a
# strategy is bad — it is bounding how long one strategy can bleed before a
# human is forced to look, exactly as the account-wide 3% daily-loss limit is a
# damage bound rather than a hypothesis test. The asymmetry makes a false
# positive cheap and a false negative expensive: tripping this only stops new
# orders, holds every existing position untouched, and a human can lift it in
# one click — while not tripping it costs real money.
#
# It is set stricter (more negative) than forward validation's -0.5 for the
# same reason: at 20 days -0.5 would fire on noise constantly, and each firing
# is a real action on real exposure rather than a research-slot bookkeeping
# change.
BREAKER_SHARPE_THRESHOLD = -1.0

# The floor below which a trailing window's return variance is treated as
# numerically zero for breach purposes (see the degenerate-case handling in
# evaluate() below). This deliberately is NOT "std == 0.0" exactly:
# metrics.sharpe_ratio()'s own exact-zero test is fine for ITS purpose (a
# clean, defined "no ratio" answer), but float64 variance of a run of
# bit-identical daily returns does not reliably land on exactly 0.0 -- e.g.
# twenty identical -0.004 returns compute to a std of ~8.9e-19 here, not
# 0.0, purely from summation order, while twenty-five of the same value
# compute to exactly 0.0. Testing for exact equality would make breach
# detection depend on that kind of incidental floating-point rounding rather
# than on the strategy's actual P&L. This tolerance sits many orders of
# magnitude above float64 noise at daily-return scale and many orders of
# magnitude below any daily-return volatility that represents real trading
# risk, so it cannot mistake a genuinely (even if only mildly) noisy return
# stream for a riskless one.
NEAR_ZERO_VARIANCE_STD = 1e-9

# Bounds day_pnl_json's growth permanently. Enough to keep several breaker
# windows of context visible for a post-mortem without the row growing without
# limit.
DAY_PNL_HISTORY_LIMIT = 120

METHODOLOGY_NOTE = (
    "Per-strategy daily P&L is the broker's own per-position session P&L "
    "(Alpaca unrealized_intraday_pl), attributed to each strategy in proportion "
    "to its signed share of that ticker's netted target notional — exact when a "
    "ticker is driven by one strategy, pro-rata by target when several share it. "
    "Two limitations are disclosed rather than hidden: a position closed in full "
    "intraday leaves /positions, so that day's realized P&L on it is not "
    f"captured; and the {BREAKER_LOOKBACK_TRADING_DAYS}-day Sharpe this breaker "
    "tests is a damage bound, not a significance test (its standard error at "
    "n=20 is ~3.5, so the -1.0 threshold is well inside one SE of zero)."
)


@dataclass(frozen=True)
class BreakerVerdict:
    breached: bool
    trailing_sharpe: float | None
    trailing_days: int
    trailing_return: float | None


def load_day_pnl(day_pnl_json: str | None) -> list[dict]:
    if not day_pnl_json:
        return []
    try:
        rows = json.loads(day_pnl_json)
    except (TypeError, ValueError):
        return []
    return rows if isinstance(rows, list) else []


def append_or_update_day(
    day_pnl: list[dict], *, trade_date: date, pnl: float, allocated_capital: float
) -> list[dict]:
    """Record one trading day's attributed P&L, replacing the day's existing
    entry in place if it is already there.

    The runner ticks roughly every 60 seconds all session, so the same trading
    day is written many times; the last write before the close is the day's
    final number. Updating in place (rather than appending) is what keeps the
    rolling window a window of DAYS rather than of ticks — getting this wrong
    would let 20 ticks of one bad minute trip a "20-day" breaker.
    """
    day_return = pnl / allocated_capital if allocated_capital > 0 else 0.0
    entry = {
        "date": trade_date.isoformat(),
        "pnl": float(pnl),
        "return": float(day_return),
        "allocated_capital": float(allocated_capital),
    }
    updated = [row for row in day_pnl if row.get("date") != entry["date"]]
    updated.append(entry)
    updated.sort(key=lambda row: row.get("date", ""))
    return updated[-DAY_PNL_HISTORY_LIMIT:]


def evaluate(day_pnl: list[dict]) -> BreakerVerdict:
    """True iff the trailing BREAKER_LOOKBACK_TRADING_DAYS days of attributed
    returns have an annualized Sharpe at or below BREAKER_SHARPE_THRESHOLD, OR
    are a (numerically) zero-variance run of net-negative P&L — a degenerate
    input no Sharpe threshold can judge (see the inline comment below).

    Trailing, not all-time cumulative — for the same reason
    check_underperformance is trailing: a recent bad stretch must not be masked
    by an older good one."""
    if len(day_pnl) < BREAKER_MIN_DAYS_TO_JUDGE:
        return BreakerVerdict(
            breached=False, trailing_sharpe=None, trailing_days=len(day_pnl), trailing_return=None
        )
    trailing = day_pnl[-BREAKER_LOOKBACK_TRADING_DAYS:]
    returns = pd.Series([float(row.get("return", 0.0)) for row in trailing])
    cumulative = float((1.0 + returns).prod() - 1.0)

    # Degenerate case metrics.sharpe_ratio() is not equipped to answer
    # correctly for THIS caller. mean/std is undefined in the limit as
    # std -> 0: it diverges to -infinity for a negative mean and +infinity
    # for a positive one. metrics.sharpe_ratio() answers a flat 0.0 for
    # (numerically) zero-variance input by convention -- the right, neutral
    # answer for a caller with no stake in the sign -- but that is exactly
    # wrong here. A strategy that has posted the same negative P&L every
    # single day for the whole trailing window is not "Sharpe-neutral"; it
    # is a certain, unvarying loss, which is strictly worse than the noisy
    # losses BREAKER_SHARPE_THRESHOLD is calibrated to catch (a noisy
    # stretch that bad is already borderline-indistinguishable from luck; a
    # riskless one that bad has no such excuse). So it is treated as an
    # automatic breach here, decided directly off the trailing returns'
    # variance and mean rather than by routing a manufactured extreme number
    # through the shared Sharpe formula. A flat *non-negative* P&L (zero, or
    # a steady gain) is the mirror case and correctly does NOT breach.
    std = float(returns.std(ddof=1))
    mean = float(returns.mean())
    if mean < 0 and (not math.isfinite(std) or std <= NEAR_ZERO_VARIANCE_STD):
        return BreakerVerdict(
            breached=True,
            trailing_sharpe=float("-inf"),
            trailing_days=len(trailing),
            trailing_return=cumulative,
        )

    sharpe = metrics.sharpe_ratio(returns)
    return BreakerVerdict(
        breached=sharpe <= BREAKER_SHARPE_THRESHOLD,
        trailing_sharpe=sharpe,
        trailing_days=len(trailing),
        trailing_return=cumulative,
    )
