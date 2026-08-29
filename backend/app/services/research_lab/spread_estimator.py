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
#
# WIRED (2026-08-28) into the cross-sectional harness as an OPT-IN
# alternative cost model, never a silent replacement: CrossSectionalConfig.
# cost_model="edge_spread" charges each formation's per-ticker traded
# notional at that ticker's own trailing EDGE half-spread (via
# build_edge_half_spread_frame below, carried on CrossSectionalData.
# half_spread), falling back to the flat config.cost_bps for any
# ticker/date with no usable estimate. The default cost_model="flat_bps"
# is byte-for-byte the old behavior — exactly the additive-alternative
# discipline the dual price basis followed (see cross_sectional.py).

DEFAULT_WINDOW_DAYS = 21  # ~1 trading month

# KNOWN LIMITATION -- SEVERITY UPDATED 2026-08-30 after a dedicated
# investigation into a large-cap cost-inflation report from two same-night
# strategy builds (eigenportfolio-statarb, jump-drift). The 2026-08-28 note
# below (~2x bias at 10bps, synthetic-only) badly understated this in the
# real-data regime this project actually screens (mega/large-cap S&P names,
# true half-spreads on the order of ~0.3-1.5bps). Independently reproduced
# at production settings (window=63): PG/JNJ/KO/VZ median HALF-spread
# 11.8/14.1/13.5/15.8bps against tick-floor true half-spreads of roughly
# 0.3-1.5bps -- a ~10-40x overstatement, not ~2x. SPY itself (true full
# spread ~0.26bps, live-verified) gets a rolling-63 median FULL-spread
# estimate of ~24bps. This is NOT an implementation bug -- verified
# line-by-line against the paper's own reference `bidask` package and its
# Eq. (11)-(13); units, the half-spread division by 2, and auto_adjust
# handling are all correct. It is the source paper's OWN disclosed
# limitation for this exact regime (Ardia/Guidotti/Kroencke, pp. 24-26 of
# the working paper, SSRN 3892335): "the spreads for mid and large caps
# have become too small to be reliably estimated from a monthly sample of
# daily data" (post-2005), with intraday price data named as the paper's
# own recommended remedy over more daily-bar history or a wider window --
# widening the window here trades away liquidity-regime responsiveness
# without closing this gap, since the dominant failure mode is a real-data
# violation of the estimator's model (documented positive-skewed overnight
# gap dynamics reading as a spurious positive transitory component), not
# just short-sample GMM noise. A secondary, smaller amplifier: this module
# calls `edge_rolling` with the package default `sign=False`, which FOLDS
# negative squared-spread estimates to positive via abs() rather than the
# paper's own canonical truncation-to-zero (Eq. 14); recomputing with
# truncation reduces but does not close the gap (e.g. JNJ 14.1 -> 5.3bps).
#
# PRACTICAL CONSEQUENCE: do not read this module's output as an accurate
# cost LEVEL for a single liquid large-cap ticker, at any window length.
# It remains far more trustworthy (a) for ranking tickers by relative
# cost, and (b) as a level estimate for wider-spread/less-liquid names
# above roughly 30-50bps true spread, where the earlier 2026-08-28 note's
# few-percent recovery numbers do hold. Any existing run persisted under
# cost_model="edge_spread" that concluded a strategy was uneconomic on a
# mega/large-cap-heavy universe should be read as a PESSIMISTIC bound, not
# a realistic cost estimate -- since cost only ever pushes net Sharpe
# down, no prior "positive edge" conclusion is invalidated by this, but a
# prior "uneconomic under edge_spread costs" conclusion on such a universe
# is not sound as stated and may be worth re-examining under a more
# realistic cost assumption (e.g. a lower calibrated flat rate, or EDGE
# used as a ranker scaling a calibrated base rate, or an intraday-based
# estimate) before being treated as a closed negative.


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


# The rolling window used when the estimate feeds a COST MODEL (the
# cross-sectional harness's cost_model="edge_spread", and the intraday
# re-audit's per-ticker cost derivation) rather than a point-in-time
# liquidity *ranking*. One quarter, not DEFAULT_WINDOW_DAYS=21, because of
# the KNOWN LIMITATION documented above: at 21 days a true 10bps spread
# recovers as ~21bps — a ~2x UPWARD bias exactly in the tight-spread
# large-cap regime this project's S&P universe lives in — and that bias is
# short-sample GMM noise, which widening the window directly reduces. A
# cost model biased 2x high at the tight end would rebuild, in miniature,
# the very flat-cost pessimism this option exists to correct. 63 trading
# days mirrors the "one quarter" judgment call this codebase already uses
# for a smoothing horizon (cross_sectional_patterns.TURNOVER_
# NORMALIZATION_WINDOW), trading some responsiveness to genuine liquidity
# regime shifts for materially less small-sample bias; disclosed judgment
# call, not an independently calibrated constant. Pinned by the synthetic
# recovery test in tests/test_edge_cost_model.py at THIS window, not just
# the module default.
COST_MODEL_WINDOW_DAYS = 63


def build_edge_half_spread_frame(
    open_: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    close: pd.DataFrame,
    window_days: int = COST_MODEL_WINDOW_DAYS,
) -> pd.DataFrame:
    """Wide (dates x tickers) frame of one-way HALF-spreads as a fraction
    of price (0.0005 = 5bps per unit of notional traded, one-way) — the
    per-ticker, per-day cost basis CrossSectionalData.half_spread carries
    for cost_model="edge_spread". Each column is that ticker's rolling
    EDGE full-spread estimate divided by 2: crossing from mid to bid or
    ask costs half the effective spread, which makes each cell directly
    comparable to the flat one-way config.cost_bps / 10_000 it replaces.

    All four input frames must share one index and one column set (the
    exact alignment YFinanceProvider.get_daily_ohlcv guarantees). The
    output is aligned to close likewise, so validate_cross_sectional_data
    accepts it unchanged.

    TRAILING BY CONSTRUCTION — the property that lets the harness read row
    i at formation i without look-ahead: edge_rolling is a pandas-style
    rolling window ENDING at each row, so the estimate on a formation date
    uses only that date's own and earlier OHLC rows (pinned by the
    truncation-invariance test in tests/test_edge_cost_model.py). The
    adjustment basis does not matter here: auto_adjust scales O/H/L/C by
    the same per-day factor, and the estimator reads only intraday log
    RATIOS, which that scaling leaves untouched.

    A cell is NaN wherever no usable estimate exists — not enough valid
    rows in the window yet, missing OHLC, or a degenerate/non-positive
    estimate (edge_rolling's unsigned output can be exactly 0.0 when its
    squared-spread estimate lands at zero; a zero trading cost is not a
    plausible real-world number, so it is treated as "no estimate" rather
    than "free"). NaN is deliberate: the consuming cost model falls back
    to the flat config.cost_bps for exactly those ticker/dates and COUNTS
    the fallback (FormationRecord.edge_flat_fallback_notional), instead of
    crashing or silently charging zero."""
    for name, frame in (("high", high), ("low", low), ("close", close)):
        if not frame.index.equals(open_.index) or not frame.columns.equals(open_.columns):
            raise ValueError(
                f"build_edge_half_spread_frame: {name} is not aligned with open "
                "(index/columns must match exactly — see get_daily_ohlcv, which guarantees this)."
            )
    half_by_ticker: dict[str, pd.Series] = {}
    for ticker in close.columns:
        ohlc = pd.DataFrame(
            {"open": open_[ticker], "high": high[ticker], "low": low[ticker], "close": close[ticker]}
        )
        half_by_ticker[ticker] = edge_rolling(ohlc, window=window_days) / 2.0
    result = pd.DataFrame(half_by_ticker, index=close.index).loc[:, close.columns]
    return result.where(result > 0.0)
