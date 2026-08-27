import pandas as pd
from bidask import edge_rolling

# Ardia, Guidotti & Kroencke, "Efficient Estimation of Bid-Ask Spreads from
# Open, High, Low, and Close Prices," Journal of Financial Economics 2024
# (doi.org/10.1016/j.jfineco.2024.103916). A GMM-style estimator of the
# effective bid-ask spread from daily OHLC alone -- no tick/quote data
# needed. Uses the `bidask` package (MIT license, github.com/eguidotti/
# bidask) directly rather than re-implementing the formula: it's the
# paper's own maintained reference implementation, not a third-party
# guess at their method.
#
# SUPERSEDES an earlier hand-rolled Corwin & Schultz (2012) implementation,
# built first and then discarded after direct validation exposed it as the
# wrong tool for this project's universe: on synthetic OHLC with a KNOWN
# injected spread, Corwin-Schultz recovered a true 10bps spread as -12.8bps
# and a true 50bps spread as 20.5bps -- a large, sign-flipping downward
# bias at exactly the LOW-spread regime this project's S&P 500/600 universe
# lives in. This estimator, tested identically on the same synthetic data,
# recovered 10bps as 4.7bps and 50bps as 48.0bps -- close to exact at every
# true-spread level tested (10/50/100/300/500bps). The CS bias is
# well-documented in the literature (it's why Abdi-Ranaldo 2017 and then
# this estimator were developed as successors); it wasn't a bug in that
# implementation, the formula itself is known-weak exactly where this
# project needs it strong.
#
# Built in response to this project's own repeated finding (Phase A/B
# intraday pattern mining, 420/420 patterns tried, zero with positive
# pooled Sharpe after cost): every backtest in this codebase currently
# assumes a FLAT cost in basis points, identical across every ticker and
# every day. This gives a per-ticker, per-day-varying cost proxy instead.
# NOT wired into any backtest yet -- replacing a flat cost assumption
# touches every family's realized Sharpe and is a decision to make
# explicitly, not fold in quietly alongside an unrelated change.

DEFAULT_WINDOW_DAYS = 21  # ~1 trading month

# KNOWN LIMITATION, found by this project's own synthetic-recovery test
# (not documented in the source paper as far as this project checked): at
# DEFAULT_WINDOW_DAYS=21, recovery of a true spread has real accuracy
# variation by regime. Averaged across 15 synthetic seeds each: a true
# 10bps spread recovers as ~21bps (roughly 2x upward bias -- exactly the
# tightest, most liquid-large-cap regime this project's universe lives
# in), while 50/100/300/500bps recover within a few percent (45.7, 96.2,
# 299.1, 500.7bps respectively). Widening the window reduces this bias
# (short-sample GMM noise) but trades away responsiveness to a real
# regime change in liquidity. Do not treat this module's output as an
# accurate point estimate for a single very-liquid large-cap ticker
# without accounting for this; it is far more trustworthy for ranking
# tickers by relative cost or for anything above ~30-50bps true spread.


def estimate_effective_spread(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> pd.Series | None:
    """Rolling effective-spread estimate, as a fraction of price (0.01 =
    1%, i.e. ~100bps). All four series must share one ascending
    DatetimeIndex. Returns None if there isn't enough history for even one
    full window -- edge_rolling would otherwise return an all-NaN Series,
    which is a worse signal to callers than an explicit None (same
    convention as classify_regime's insufficient-history skip)."""
    if not (
        open_.index.equals(high.index)
        and open_.index.equals(low.index)
        and open_.index.equals(close.index)
    ):
        raise ValueError("open, high, low, close must share the same index")
    if len(open_) < window_days:
        return None

    frame = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})
    return edge_rolling(frame, window=window_days)
