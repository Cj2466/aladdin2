"""The Vol-Regime family: a cross-asset IMPLIED-volatility-dislocation
timing signal over a small fixed set of liquid ETFs, screened as exactly 48
PRE-DECLARED specs with its own n_trials denominator.

WHY THIS IS A NEW MODULE AND NOT A cross_sectional.py FAMILY
============================================================================
cross_sectional.screen_cross_sectional_universe ranks a UNIVERSE of names on
a per-ticker signal at each formation and buys the top rank_fraction against
the bottom. Its whole return-generating step is `select_leg_tickers(signal,
rank_fraction)` — a cross-sectional sort. This family has no cross-section
to sort: the state variable (log(MOVE/VIX), say) is a single scalar per DAY
that belongs to no ticker at all, and the traded object is a single fixed
spread (long SPY / short IEF) whose SIZE AND SIGN that scalar sets. Forcing
it into the ranking harness would mean fabricating a fake two-name "universe"
whose per-ticker signals are +z and -z so the sort trivially reproduces the
spread — which would work numerically and would be a lie about what the code
does, would silently inherit rank_fraction/min_names_per_leg semantics that
mean nothing here, and could never express the one thing this design
genuinely needs that ranking cannot: a CONTINUOUS position size, including
near-flat, driven by the magnitude of an external scalar.

So the backtest loop below is this module's own. What is reused, unmodified,
is everything downstream that already operates on a daily return series —
metrics.sharpe_ratio and deflated_sharpe.compute_deflated_sharpe — exactly as
intraday_patterns.py and cross_sectional.py each reuse them. The conventions
that ARE portable (formation at the close, non-overlapping holds, turnover
priced on |position change|, financing accrued on calendar days, a fixed
pre-declared n_trials, sigma_sr as the sibling-Sharpe dispersion) are
deliberately copied from cross_sectional.py so this family's numbers stay
comparable with the ones screened before it.

============================================================================
THE DATA, RE-VERIFIED LIVE 2026-08-27 (the scout's list did NOT survive)
============================================================================
This family was proposed by a feasibility scout that reported a nine-index
volatility complex on yfinance. Re-pulling every one of those tickers
directly (both `yf.download(start=1990-01-01)` and
`yf.Ticker(t).history(period="max")`, two independent code paths, retried)
found that FIVE of them return exactly ONE row — today's quote — and have no
usable history at all through this data source:

    ^VIX3M   scout claimed 2006    ACTUAL: 1 row (2026-08-26 only)
    ^VIX6M   scout claimed 2008    ACTUAL: 1 row
    ^VXD     scout claimed 2005    ACTUAL: 1 row
    ^VIX9D   scout claimed 2011    ACTUAL: 1 row
    ^VIX1D   scout claimed 2022    ACTUAL: 1 row

^VIX9D/^VIX1D were already excluded by the review's amendment 1; ^VIX3M,
^VIX6M and ^VXD were NOT, and they are excluded here on measurement, not on
instruction. Alternate symbologies were tried and also fail: ^VXV, ^VXMT,
^RVX, ^VXEEM, ^TYVIX, ^VXTLT, ^DJX do not resolve at all, and ^VXEFA/^EVZ
return a single row. Any term-structure mechanism (VIX3M/VIX, VIX6M/VIX3M)
is therefore NOT BUILDABLE on free data today, and no spec here pretends
otherwise.

What DOES have deep, real history (verified same session, same two paths):

    ^VIX    1990-01-02   9231 rows   SPX 30-day implied vol
    ^SKEW   1990-01-02   9156 rows   SPX tail/OTM-put skew
    ^VXN    2001-01-23   6436 rows   NDX 30-day implied vol   <- scout missed this
    ^MOVE   2002-11-12   5882 rows   Treasury swaption implied vol
    ^VVIX   2007-01-03   4934 rows   implied vol OF VIX options
    ^OVX    2007-05-10   4855 rows   crude-oil (USO) implied vol
    ^GVZ    2008-06-03   4587 rows   gold (GLD) implied vol

^VXN is a genuine ADDITION found by this re-verification, not carried from
the scout. Seven usable indices, and the family below is built from these
seven and nothing else.

THESE ARE OPTION-DERIVED, NOT REALIZED VOL RELABELLED. Re-verified rather
than taken on trust, because it is the single assumption the whole family
rests on: over ^MOVE's full 5,882-row history,

    corr(log(MOVE/VIX), trailing 21d realized SPY vol) = -0.388
    corr(VIX level,     trailing 21d realized SPY vol) = +0.866

The ratio moves OPPOSITE to realized equity vol while its own denominator
moves almost one-for-one with it — a realized-vol series in disguise could
not do that. (-0.388 also independently reproduces the scout's -0.40.)

AND THE CROSS-ASSET INDICES CARRY INDEPENDENT INFORMATION — but only three
of them do, which is a correction to the scout's framing. Correlations of
DAILY LOG CHANGES against ^VIX, over the common 2008-06-04..2026-08-26
window (n=4,291):

    ^MOVE  0.322     ^OVX  0.409     ^GVZ  0.408     <- genuinely cross-ASSET
    ^SKEW -0.085                                     <- genuinely orthogonal
    ^VVIX  0.822     ^VXN  0.919                     <- NOT independent

^VXN at 0.919 and ^VVIX at 0.822 are, in daily-change terms, largely the
same object as ^VIX (both are US equity-complex implied vol). They are kept
in the family — a signal being correlated with VIX is a hypothesis about it,
not a disqualification — but the module reports that correlation as a
first-class diagnostic (VOL_INDEX_VIX_CORRELATIONS) so no reader can mistake
a `vxn_vix` result for evidence about cross-ASSET dislocation. Only MOVE,
OVX and GVZ earn that description, and only those three enter the composite.

============================================================================
THE 48 SPECS, AND WHY THE SIGN IS NOT A FREE PARAMETER
============================================================================
8 state variables x 3 holding periods x 2 targets = 48. That product is
asserted three ways in _build_vol_regime_family() against the pre-declared
VOL_REGIME_N_TRIALS, for the same reason cross_sectional_bonds.py asserts
its 18: a silent drift in family size silently changes the DSR denominator.

Every one of the eight is traded in the SAME direction: VOL_REGIME_DIRECTION
= -1, "richer implied volatility -> risk-off -> short the risk-on leg". That
uniformity is the point. Letting each signal pick its own sign would double
the real search to 96 while still reporting n_trials=48 — the exact
uncounted-degree-of-freedom failure the DSR exists to prevent. The sign is
fixed by the cited literature BEFORE any return is computed, and specs whose
true sign is the opposite will simply print negative Sharpes here. They will
not be flipped. If a reader wants the flipped family, that is a second
48-trial search and must be counted as one.

The honest competing view is recorded rather than hidden: Bollerslev,
Tauchen & Zhou, "Expected Stock Returns and Variance Risk Premia" (Review of
Financial Studies 22(11), 2009) find the variance RISK PREMIUM (implied minus
realized variance) predicts HIGHER subsequent equity returns, which points
+1 for a level signal. The -1 pre-declaration follows Connolly, Stivers &
Sun, "Stock Market Uncertainty and the Stock-Bond Return Relation" (Journal
of Financial and Quantitative Analysis 40(1), 2005), which is the directly
on-point result for THIS trade — days of high implied volatility are
followed by relatively better BOND than stock returns (flight-to-quality) at
exactly the horizons traded here. Two real, opposed literatures; one sign
picked in advance and left alone.

THE STATE VARIABLES
  move_vix    log(^MOVE/^VIX)   rates-vs-equity IV dislocation
  ovx_vix     log(^OVX/^VIX)    oil-vs-equity IV dislocation
  gvz_vix     log(^GVZ/^VIX)    gold-vs-equity IV dislocation
  vxn_vix     log(^VXN/^VIX)    tech-vs-broad equity IV (NOT cross-asset)
  vvix_vix    log(^VVIX/^VIX)   vol-of-vol vs vol, i.e. convexity demand
  skew        log(^SKEW)        OTM-put/tail-risk pricing
  vix_level   log(^VIX)         THE CONTROL — see below
  cross_asset mean z of move_vix, ovx_vix, gvz_vix

vix_level is a deliberate CONTROL SPEC, not filler. The entire claim of this
family is that CROSS-ASSET implied vol says something the equity market's own
implied vol does not. If `vix_level` matches or beats the dislocation specs,
that claim is refuted by the family's own contents, and the comparison is
built in rather than left to a later reviewer. It spends 6 of the 48 trials
and is worth every one.

`cross_asset` is the law-of-large-numbers construction: the equal-weighted
mean of the three genuinely-independent dislocation z-scores (pairwise daily-
change correlations 0.181/0.268/0.271, verified above), requiring at least
2 of 3 to be computable so it can run from the family's common start rather
than waiting on ^GVZ's 2008-06-03 inception.

HOLDING PERIODS: 21, 42, 63 trading days, no sub-weekly variant. This is the
standing lesson from every family screened in this project — reformation cost
scales with rebalance frequency, and 270 sub-weekly pattern definitions came
back cost-dominated. 21 trading days is the floor, per the build instruction.

============================================================================
NON-OVERLAPPING FORMATIONS (the methodological requirement, amendment 2)
============================================================================
The scout's indicative R^2 check (0.019 -> 0.036) used OVERLAPPING windows
and was explicitly flagged untrustworthy. Nothing here inherits that.

Formation cadence is EXACTLY holding_days: a formation at trading-day
position p sets a position held over days p+1..p+H, and the next formation
is at position p+H. Holds are adjacent and disjoint — every realized day
belongs to exactly one hold, and the number of independent bets is
n_formations, reported per spec as first-class output
(VolRegimeScreeningResult.n_formations) rather than buried. There is no
cohort staggering, no overlapping cadence option, and _build_vol_regime_
family() asserts cadence == holding_days for all 48 specs so none can be
added by accident.

Sharpe/PSR/DSR are still computed on the DAILY return series, matching every
other family in this project (deviating would make the numbers
incomparable). Daily returns inside one hold are of course not independent
of each other — the position is constant across them — so the daily n
overstates independent information. That is why, on top of the
non-overlapping design, every spec also gets a CIRCULAR BLOCK BOOTSTRAP
(block_bootstrap_sharpe_pvalue) with block length = holding_days: it
resamples whole holds under a zero-mean null, so the resulting p-value
respects exactly the dependence the daily count ignores. Both numbers are
reported; where they disagree, the bootstrap is the one to believe.

============================================================================
COSTS
============================================================================
VOL_REGIME_COST_BPS = 2.0 bps ONE-WAY per unit of gross notional traded.
Grounded in these instruments' actual quoted spreads rather than assumed: at
2026-08-26 closes, a one-cent bid/ask on SPY (~$6xx) is ~0.08bp, on IEF
(~$95) ~1.05bp, on HYG (~$80) ~1.25bp. The binding leg is therefore ~1.25bp
of half-spread, and 2.0bp one-way is deliberately set ABOVE it to cover
commission and slippage. A full swing from flat to a unit spread trades
gross notional 2.0 (one unit long, one short), so establishing the book
costs ~4bp of equity and a full reversal ~8bp — a materially more
conservative assumption than the ~1-2bp round trip the build instruction
offered as a starting point, chosen in that direction on purpose.

VOL_REGIME_SHORT_BORROW_BPS_PER_YEAR = 50.0, charged on the SHORT notional
only (|position| units) and accrued on CALENDAR days / 365, copying
cross_sectional.py's FINANCING_DAYS_PER_YEAR reasoning exactly — a weekend
costs three days of borrow, and charging per TRADING day would undercharge a
continuously-held book by ~31%. The long leg is not separately financed
because the position is dollar-neutral and self-financing (short proceeds
fund the long), which is the same assumption metrics.sharpe_ratio documents
as its reason for not subtracting a risk-free rate; the residual real cost
is the short rebate shortfall, which is what this rate is. 50bp/yr is a
general-collateral figure for large liquid ETFs and is NOT a sourced
borrow-rate quote — it is a disclosed assumption, and
build_vol_regime_disclosure() reports the breakeven cost multiple so a reader
can see how much it would have to be wrong by to matter.

Both are reported separately and never summed, per cross_sectional.py's
two-cost convention: turnover cost scales with trading MORE OFTEN, financing
with holding LONGER, and they push in opposite directions across the very
holding_days axis this family searches over.

============================================================================
WHAT COULD MAKE A POSITIVE RESULT HERE FAKE — CHECKED IN-MODULE
============================================================================
Two of this project's best-looking results were killed on adversarial
recheck (a commodities momentum family that was a disguised long-precious-
metals bet, residual Sharpe ~0.000 after regressing on a metals factor; a
buyback family whose DSR sat below the median best-of-7 under pure noise).
The equivalent confound here is obvious and is computed automatically by
compute_confound_diagnostics() for EVERY spec, not on request:

 1. STATIC TILT — the killer. A trailing z-score is only approximately
    mean-zero; if a ratio trends, its z sits persistently on one side and the
    "timing" signal is really a constant long-SPY-short-IEF position. Over
    2008-2026 that constant position is a large winner for reasons having
    nothing to do with implied volatility. So every spec reports
    mean_position AND, decisively, spread_beta / residual_sharpe from an OLS
    of its own daily returns on the buy-and-hold target spread. This is
    precisely the regression that reduced the commodities family to zero. A
    spec whose residual_sharpe collapses toward 0 while its raw Sharpe looks
    good IS a static tilt, and is reported as one.
 2. EQUITY BETA / RATES BETA — regressions on SPY and on IEF daily returns,
    for the same reason at the single-asset level.
 3. ONE-CRISIS DEPENDENCE — the sample opens in May 2008 precisely so it
    contains the 2008 crisis, which is a strength for regime coverage and a
    hazard for inference: a flight-to-quality signal can earn its whole
    lifetime Sharpe in one autumn. Every spec therefore reports its Sharpe in
    equal thirds of its own sample (subperiod_sharpes).
 4. THE CONTROL SPEC — see vix_level above.
 5. THE SEARCH THAT LED HERE IS NOT IN n_trials. This must be stated
    wherever these results are: 48 is the size of THIS family, declared
    before any return was computed. It does not cover the scout's own prior
    exploration across the volatility complex (which had already looked at
    MOVE/VIX and reported an indicative positive before this module existed),
    nor the other families screened alongside it. The true multiple-
    comparisons burden is strictly larger than 48, so the DSR reported here
    is an UPPER bound on the real one. That is the same correction that sank
    the buyback family, and it applies to every number this module prints.

RESIDUAL BIASES NOT FIXED, only disclosed: the three ETFs were chosen today,
with hindsight, from instruments that still exist and are still liquid (the
same hindsight-selection channel cross_sectional.fixed_universe_membership
documents — small here, since SPY/IEF/HYG are among the largest ETFs in
existence and none was ever at risk of closure, but not zero). Position
weights are treated as re-set daily inside a hold at zero cost, matching
cross_sectional.py's leg-weight convention and mildly optimistic. Formation
is assumed executable at the exact closing print.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio

logger = logging.getLogger(__name__)

# --- the volatility complex ------------------------------------------------

# The seven indices with real history, verified live 2026-08-27 via two
# independent yfinance code paths (see the module docstring for the five the
# scout listed that return exactly one row and are therefore absent).
VIX = "^VIX"
VXN = "^VXN"
SKEW = "^SKEW"
MOVE = "^MOVE"
VVIX = "^VVIX"
OVX = "^OVX"
GVZ = "^GVZ"

VOL_INDEX_UNIVERSE: tuple[str, ...] = (VIX, VXN, SKEW, MOVE, VVIX, OVX, GVZ)

# Verified first print per index (yfinance, 2026-08-27). Used by
# run_vol_regime_screening's data-sanity log, not as a hard gate — a vendor
# extending or truncating history should surface as a WARNING, not a crash.
VOL_INDEX_VERIFIED_START: dict[str, date] = {
    VIX: date(1990, 1, 2),
    SKEW: date(1990, 1, 2),
    VXN: date(2001, 1, 23),
    MOVE: date(2002, 11, 12),
    VVIX: date(2007, 1, 3),
    OVX: date(2007, 5, 10),
    GVZ: date(2008, 6, 3),
}

# Correlation of each index's DAILY LOG CHANGE with ^VIX's, measured over the
# common 2008-06-04..2026-08-26 window (n=4,291), verified 2026-08-27. Kept
# as data rather than prose because it is the number that decides which
# specs may honestly be called "cross-asset": ^VXN and ^VVIX are largely the
# equity complex restated, and only MOVE/OVX/GVZ are independent enough to
# enter CROSS_ASSET_COMPONENTS.
VOL_INDEX_VIX_CORRELATIONS: dict[str, float] = {
    VXN: 0.919,
    VVIX: 0.822,
    OVX: 0.409,
    GVZ: 0.408,
    MOVE: 0.322,
    SKEW: -0.085,
}

# Above this daily-change correlation with ^VIX, an index is treated as part
# of the equity volatility complex rather than an independent asset class,
# and is barred from the composite. 0.5 sits in the wide empty gap between
# the independent group (max 0.409) and the equity-complex group (min 0.822)
# — it is a classification threshold placed in a genuine bimodal gap, not a
# tuned parameter, and no result depends on its exact value.
CROSS_ASSET_MAX_VIX_CORRELATION = 0.5

# When a beta-hedged return stream's standard deviation falls to this fraction
# of the unhedged stream's, treat the hedge as having explained essentially
# all of it and report residual_sharpe as exactly 0.0 rather than computing a
# Sharpe on floating-point dust. A Sharpe ratio is SCALE-INVARIANT, so a
# hedged stream that is mathematically zero but numerically ~1e-18 still
# reports whatever Sharpe its noise happens to have -- and the direction of
# that noise is a coin flip, not a diagnosis. Confirmed directly on this
# exact code path: replaying a spec whose position was pinned so that y and x
# are bit-identical (max|y-x| == 0.0) leaves compute_beta returning
# 1.0000000000000002 rather than 1.0, and the unguarded residual_sharpe came
# out +0.5497 on one such replay -- a confident-looking POSITIVE number for a
# spec with literally nothing left after hedging. That is the dangerous
# direction: the static-tilt filter below is `residual_sharpe < 0.5 *
# sharpe_annualized`, so a spurious positive doesn't just mislabel a static
# tilt, it CLEARS one. Same guard as
# cross_sectional_correlation_risk_premium.py's compute_confound_diagnostics,
# which found this failure mode first.
RESIDUAL_DEGENERACY_RATIO = 1e-8

# --- the traded instruments ------------------------------------------------

RISK_ON_EQUITY = "SPY"
RISK_ON_CREDIT = "HYG"
RISK_OFF_DURATION = "IEF"

TRADED_UNIVERSE: tuple[str, ...] = (RISK_ON_EQUITY, RISK_ON_CREDIT, RISK_OFF_DURATION)


@dataclass(frozen=True)
class TimingTarget:
    """One fixed dollar-neutral spread. `risk_on` is the leg that a
    risk-seeking view buys and `risk_off` the leg it sells, so a position of
    +1 always means "risk-on" and -1 always means "risk-off" across every
    target — without that convention the pre-declared VOL_REGIME_DIRECTION
    would mean different trades in different specs."""

    key: str
    risk_on: str
    risk_off: str
    description: str


TARGET_EQUITY_VS_DURATION = TimingTarget(
    key="spy_ief",
    risk_on=RISK_ON_EQUITY,
    risk_off=RISK_OFF_DURATION,
    description="US large-cap equity vs 7-10y Treasury duration",
)

TARGET_CREDIT_VS_DURATION = TimingTarget(
    key="hyg_ief",
    risk_on=RISK_ON_CREDIT,
    risk_off=RISK_OFF_DURATION,
    description="US high-yield credit vs 7-10y Treasury duration",
)

# Two targets, deliberately sharing the risk_off leg. The pair is a control
# on itself: hyg_ief carries the same credit/risk-appetite exposure as
# spy_ief with a far smaller equity-DIRECTION component, so a signal that
# works on spy_ief but not on hyg_ief is likely timing the equity market
# rather than reading a risk-appetite regime, and vice versa.
VOL_REGIME_TARGETS: tuple[TimingTarget, ...] = (
    TARGET_EQUITY_VS_DURATION,
    TARGET_CREDIT_VS_DURATION,
)

# --- pre-declared family parameters ---------------------------------------

# Trailing window for every z-score, in trading days. FIXED AT ONE VALUE ON
# PURPOSE: making it a searched axis would multiply the family (and the DSR
# denominator) by however many values were tried, and this family's whole
# claim to a 48-trial budget is that nothing else was tried. 252 = one year,
# the conventional "relative to the recent regime" window, chosen a priori.
VOL_REGIME_Z_WINDOW = 252

# |z| at which the position reaches full size. Position is
# clip(direction * z / scale, -1, +1), so 1.0 means "one standard deviation
# from the trailing mean is a full-size bet". Pre-declared, not tuned;
# because it is a pure scalar on an otherwise unchanged position path, it
# affects the return series' SCALE far more than its Sharpe (a Sharpe is
# scale-invariant except through the clip), which is exactly why it is a
# safe thing to fix rather than search.
VOL_REGIME_POSITION_Z_SCALE = 1.0

VOL_REGIME_HOLDING_DAYS: tuple[int, ...] = (21, 42, 63)
VOL_REGIME_MIN_HOLDING_DAYS = 21

# Uniform, pre-declared, never fitted. See the module docstring's "why the
# sign is not a free parameter".
VOL_REGIME_DIRECTION = -1.0

VOL_REGIME_N_TRIALS = 48

# One-way, per unit of gross notional traded. See the module docstring's
# COSTS section for the quoted-spread arithmetic behind 2.0.
VOL_REGIME_COST_BPS = 2.0

# Per year, on the SHORT notional only. A disclosed general-collateral
# assumption, not a sourced quote.
VOL_REGIME_SHORT_BORROW_BPS_PER_YEAR = 50.0

# 365, not 252 — financing accrues on calendar days. Same reasoning as
# cross_sectional.FINANCING_DAYS_PER_YEAR.
FINANCING_DAYS_PER_YEAR = 365.0

# Same floor as cross_sectional.MIN_REPLAY_TRADING_DAYS (itself mirroring
# momentum.py / ou_pairs.py): below this many realized daily returns a Sharpe
# is too thin to report, and the spec is dropped from screening output rather
# than surfaced with misleading precision.
MIN_REPLAY_TRADING_DAYS = 60

# A spec needs at least this many INDEPENDENT holds before its bootstrap
# p-value means anything — with fewer, the circular block bootstrap has too
# few distinct blocks to resample. 8 is the same "small enough to be
# dominated by 2-3 draws" register as deflated_sharpe.MIN_TRIALS_FOR_DSR.
MIN_FORMATIONS_FOR_BOOTSTRAP = 8

# Vol-index prints are not on the NYSE calendar for every index: measured
# 2026-08-27 against the SPY/IEF/HYG trading calendar, ^MOVE is absent on
# 1.80% of trading days (longest run 5) and ^SKEW on 1.29% (longest run 3);
# ^VIX/^VXN/^OVX/^GVZ are absent on none. Carrying the last print forward
# across such a gap uses OLDER information only and therefore cannot leak
# look-ahead — the worst it can do is stale the signal. The limit stops a
# genuinely dead index from being silently carried for months.
VOL_INDEX_FFILL_LIMIT_DAYS = 5

# Formations begin here: the first trading day on which the six non-^GVZ
# indices all have a full VOL_REGIME_Z_WINDOW of history (^OVX's 2007-05-10
# inception is the binding constraint, + 252 trading days). Pre-declared so
# the window is a stated choice rather than whatever the data happened to
# allow, and chosen at the ex-^GVZ constraint SPECIFICALLY so the sample
# contains the autumn 2008 crisis: waiting for ^GVZ's own warmup would push
# the first formation to 2009-06-04 and lose the single most informative
# risk-off regime available. ^GVZ-dependent specs instead stay uncomputable
# (and simply do not trade) until their own warmup completes — see
# run_timing_backtest's skipped-formation handling.
VOL_REGIME_FORMATION_START = date(2008, 5, 13)

# Calendar padding fetched before VOL_REGIME_FORMATION_START purely to warm
# the 252-trading-day z-window (~365 calendar days) with room for holiday
# clustering. Formations never occur in the padding.
VOL_REGIME_HISTORY_PADDING_CALENDAR_DAYS = 500

# --- citations -------------------------------------------------------------

FLIGHT_TO_QUALITY_CITATION = (
    "Connolly, Stivers & Sun, 'Stock Market Uncertainty and the Stock-Bond Return Relation', "
    "Journal of Financial and Quantitative Analysis 40(1), 2005 — days of elevated implied "
    "volatility are followed by relatively better bond than stock returns (flight-to-quality), "
    "the directly on-point result for a stock-vs-bond timing spread. Opposed view recorded in "
    "the module docstring: Bollerslev, Tauchen & Zhou, RFS 22(11), 2009."
)

SPILLOVER_CITATION = (
    "Diebold & Yilmaz, 'Better to Give than to Receive: Predictive Directional Measurement of "
    "Volatility Spillovers', International Journal of Forecasting 28(1), 2012 — volatility "
    "shocks transmit ACROSS asset classes with measurable direction, so one market's implied "
    "vol carries information about another's forthcoming returns."
)

OIL_SHOCK_CITATION = (
    "Kilian, 'Not All Oil Price Shocks Are Alike: Disentangling Demand and Supply Shocks in the "
    "Crude Oil Market', American Economic Review 99(3), 2009 — oil-market uncertainty maps to "
    "real-economy shocks whose equity consequences differ by shock type. Paired with "
    + SPILLOVER_CITATION
)

SAFE_HAVEN_CITATION = (
    "Baur & Lucey, 'Is Gold a Hedge or a Safe Haven? An Analysis of Stocks, Bonds and Gold', "
    "Financial Review 45(2), 2010 — gold behaves as a safe haven in equity stress, so the price "
    "of gold OPTIONALITY is a read on demand for crisis protection. Paired with "
    + SPILLOVER_CITATION
)

TAIL_RISK_CITATION = (
    "Bollerslev & Todorov, 'Tails, Fears, and Risk Premia', Journal of Finance 66(6), 2011 — a "
    "large share of the equity risk premium is compensation for rare disaster risk, priced in "
    "deep-OTM options, which is what the CBOE SKEW index is computed from."
)

VOL_OF_VOL_CITATION = (
    "Huang, Schlag, Shaliastovich & Thimme, 'Volatility-of-Volatility Risk', Journal of "
    "Financial and Quantitative Analysis 54(6), 2019 — vol-of-vol is a separately priced risk "
    "factor, not a restatement of the volatility level; ^VVIX is its traded analogue."
)

VARIANCE_RISK_PREMIUM_CITATION = (
    "Whaley, 'Understanding the VIX', Journal of Portfolio Management 35(3), 2009 (^VIX as a "
    "model-free implied volatility computed from SPX option prices), traded here in the "
    "direction of " + FLIGHT_TO_QUALITY_CITATION
)


# --- state variables -------------------------------------------------------


def trailing_zscore(series: pd.Series, window: int) -> pd.Series:
    """Rolling z-score using ONLY data up to and including each date.

    `min_periods=window` is load-bearing, not a default: a partial-window
    z-score computed off 3 observations is not a smaller-sample version of
    the same statistic, it is noise with a plausible scale, and allowing it
    would silently start every spec's trading a year early on garbage. A
    zero or non-finite trailing std yields NaN (the formation is then
    skipped) rather than an infinity."""
    if window < 2:
        raise ValueError(f"z-score window must be >= 2, got {window}")
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std(ddof=1)
    std = std.where(np.isfinite(std) & (std > 0))
    return (series - mean) / std


def _log_ratio(vol: pd.DataFrame, numerator: str, denominator: str) -> pd.Series:
    """log of one vol index over another. Logs (rather than the raw ratio)
    so that "twice as rich" and "half as rich" are symmetric distances from
    zero — a z-score of a raw ratio would treat the two asymmetrically and
    give the rich side systematically larger positions. Non-positive prints
    (never observed in these indices, but a vendor zero would otherwise
    become -inf and then a garbage z) are masked to NaN."""
    for column in (numerator, denominator):
        if column not in vol.columns:
            return pd.Series(np.nan, index=vol.index, dtype=float)
    num = vol[numerator].where(vol[numerator] > 0)
    den = vol[denominator].where(vol[denominator] > 0)
    return np.log(num / den)


def _log_level(vol: pd.DataFrame, ticker: str) -> pd.Series:
    if ticker not in vol.columns:
        return pd.Series(np.nan, index=vol.index, dtype=float)
    return np.log(vol[ticker].where(vol[ticker] > 0))


def state_ratio(vol: pd.DataFrame, z_window: int, *, numerator: str, denominator: str) -> pd.Series:
    return trailing_zscore(_log_ratio(vol, numerator, denominator), z_window)


def state_level(vol: pd.DataFrame, z_window: int, *, ticker: str) -> pd.Series:
    return trailing_zscore(_log_level(vol, ticker), z_window)


# The three indices independent enough of ^VIX to be called cross-ASSET (see
# VOL_INDEX_VIX_CORRELATIONS). Asserted against the correlation table below
# so the list and the evidence for it cannot drift apart.
CROSS_ASSET_COMPONENTS: tuple[str, ...] = (MOVE, OVX, GVZ)

assert all(
    VOL_INDEX_VIX_CORRELATIONS[t] < CROSS_ASSET_MAX_VIX_CORRELATION for t in CROSS_ASSET_COMPONENTS
), "a CROSS_ASSET_COMPONENTS member exceeds the equity-complex correlation threshold"

# Minimum components that must be computable for the composite to trade. 2 of
# 3 lets the composite run from VOL_REGIME_FORMATION_START on ^MOVE + ^OVX
# and pick up ^GVZ when its own z-window warms, instead of idling for the
# ~13 months to 2009-06 — the same "capture 2008" reasoning as
# VOL_REGIME_FORMATION_START itself.
CROSS_ASSET_MIN_COMPONENTS = 2


def state_cross_asset_composite(vol: pd.DataFrame, z_window: int) -> pd.Series:
    """Equal-weighted mean of the three cross-asset dislocation z-scores.

    Averaging the Z-SCORES, not the underlying log ratios, is what makes the
    weights equal in RISK terms: the three ratios have quite different
    dispersions, so averaging them raw would silently let whichever is
    noisiest dominate the composite. Components are averaged skipna with a
    minimum count, so the composite is defined as soon as
    CROSS_ASSET_MIN_COMPONENTS of them are — and is NaN (not a partial
    guess) below that."""
    components = pd.concat(
        [state_ratio(vol, z_window, numerator=t, denominator=VIX) for t in CROSS_ASSET_COMPONENTS],
        axis=1,
    )
    available = components.notna().sum(axis=1)
    composite = components.mean(axis=1, skipna=True)
    return composite.where(available >= CROSS_ASSET_MIN_COMPONENTS)


StateFn = Callable[[pd.DataFrame, int], pd.Series]

# (key, state fn, citation, human-readable hypothesis, is a genuine
#  cross-ASSET dislocation)
_STATE_VARIABLES: tuple[tuple[str, StateFn, str, str, bool], ...] = (
    (
        "move_vix",
        partial(state_ratio, numerator=MOVE, denominator=VIX),
        SPILLOVER_CITATION,
        "Treasury swaption vol rich vs equity vol -> rates market pricing stress equities have not",
        True,
    ),
    (
        "ovx_vix",
        partial(state_ratio, numerator=OVX, denominator=VIX),
        OIL_SHOCK_CITATION,
        "Crude-oil vol rich vs equity vol -> energy/supply shock ahead of equity repricing",
        True,
    ),
    (
        "gvz_vix",
        partial(state_ratio, numerator=GVZ, denominator=VIX),
        SAFE_HAVEN_CITATION,
        "Gold vol rich vs equity vol -> demand for crisis protection ahead of equity repricing",
        True,
    ),
    (
        "vxn_vix",
        partial(state_ratio, numerator=VXN, denominator=VIX),
        SPILLOVER_CITATION,
        "Nasdaq vol rich vs broad equity vol -> stress concentrated in long-duration equity",
        False,
    ),
    (
        "vvix_vix",
        partial(state_ratio, numerator=VVIX, denominator=VIX),
        VOL_OF_VOL_CITATION,
        "Vol-of-vol rich vs vol -> demand for convexity/crash protection is bid",
        False,
    ),
    (
        "skew",
        partial(state_level, ticker=SKEW),
        TAIL_RISK_CITATION,
        "Deep-OTM put pricing elevated -> tail risk being actively bid",
        False,
    ),
    (
        "vix_level",
        partial(state_level, ticker=VIX),
        VARIANCE_RISK_PREMIUM_CITATION,
        "CONTROL: equity implied vol alone, the benchmark every dislocation spec must beat",
        False,
    ),
    (
        "cross_asset",
        state_cross_asset_composite,
        SPILLOVER_CITATION,
        "Equal-risk-weighted mean of the three independent cross-asset dislocations",
        True,
    ),
)


# --- specs -----------------------------------------------------------------


@dataclass(frozen=True)
class TimingSpec:
    spec_id: str
    state_key: str
    citation: str
    hypothesis: str
    state_fn: StateFn
    holding_days: int
    target: TimingTarget
    direction: float = VOL_REGIME_DIRECTION
    is_cross_asset: bool = False
    z_window: int = VOL_REGIME_Z_WINDOW
    position_z_scale: float = VOL_REGIME_POSITION_Z_SCALE


@dataclass
class VolRegimeConfig:
    cost_bps: float = VOL_REGIME_COST_BPS
    short_borrow_bps_per_year: float = VOL_REGIME_SHORT_BORROW_BPS_PER_YEAR
    formation_start: date = VOL_REGIME_FORMATION_START


def default_vol_regime_config() -> VolRegimeConfig:
    """This family's cost configuration, as a FUNCTION rather than a module
    singleton so callers cannot mutate shared state — the same reason
    cross_sectional_bonds.default_bonds_config() is one."""
    return VolRegimeConfig()


def _build_vol_regime_family() -> list[TimingSpec]:
    """The exact product _STATE_VARIABLES x VOL_REGIME_HOLDING_DAYS x
    VOL_REGIME_TARGETS. The literal length of this list is the n_trials
    denominator screen_vol_regime_timing uses — every definition counts,
    whether or not it survives the data floors, because shrinking the
    denominator to "specs that worked" would be gameable by declaring specs
    expected to fail."""
    specs: list[TimingSpec] = []
    for key, state_fn, citation, hypothesis, is_cross_asset in _STATE_VARIABLES:
        for holding in VOL_REGIME_HOLDING_DAYS:
            for target in VOL_REGIME_TARGETS:
                specs.append(
                    TimingSpec(
                        spec_id=f"vol_{key}_h{holding}_{target.key}",
                        state_key=key,
                        citation=citation,
                        hypothesis=hypothesis,
                        state_fn=state_fn,
                        holding_days=holding,
                        target=target,
                        is_cross_asset=is_cross_asset,
                    )
                )

    expected = len(_STATE_VARIABLES) * len(VOL_REGIME_HOLDING_DAYS) * len(VOL_REGIME_TARGETS)
    assert len(specs) == expected == VOL_REGIME_N_TRIALS, (
        f"Vol-regime family built {len(specs)} definitions; the grid "
        f"({len(_STATE_VARIABLES)} state variables x {len(VOL_REGIME_HOLDING_DAYS)} holding "
        f"periods x {len(VOL_REGIME_TARGETS)} targets) implies {expected}; the pre-declared "
        f"VOL_REGIME_N_TRIALS is {VOL_REGIME_N_TRIALS}. All three must agree — a drift here "
        "silently changes the DSR's multiple-comparisons denominator for every future run."
    )
    assert len({s.spec_id for s in specs}) == len(specs), "spec_ids must be unique"
    assert all(s.direction == VOL_REGIME_DIRECTION for s in specs), (
        "every spec trades the single pre-declared direction — a per-spec sign would double the "
        "real search to 96 while still reporting n_trials=48"
    )
    assert all(s.holding_days >= VOL_REGIME_MIN_HOLDING_DAYS for s in specs), (
        "sub-21-day holding periods are deliberately excluded — see the module docstring's "
        "HOLDING PERIODS note"
    )
    assert all(s.z_window == VOL_REGIME_Z_WINDOW for s in specs), (
        "the z-window is fixed at one pre-declared value; searching it would multiply the family "
        "size and the DSR denominator"
    )
    return specs


VOL_REGIME_FAMILY: list[TimingSpec] = _build_vol_regime_family()


# --- data ------------------------------------------------------------------


@dataclass(frozen=True)
class VolRegimeData:
    """Vol-index closes and traded-ETF closes on ONE shared trading calendar.

    `traded_close` defines the calendar, because it is the only one that is
    actually tradeable — a vol index printing on a day the ETFs do not is
    unusable, and an ETF day with no fresh vol print is handled by carrying
    the last one forward (older information, never future information; see
    VOL_INDEX_FFILL_LIMIT_DAYS)."""

    vol_close: pd.DataFrame
    traded_close: pd.DataFrame

    def __post_init__(self) -> None:
        if not self.vol_close.index.equals(self.traded_close.index):
            raise ValueError(
                "vol_close and traded_close must share an identical index — align them with "
                "align_vol_regime_data() rather than passing raw frames"
            )


def align_vol_regime_data(vol_close: pd.DataFrame, traded_close: pd.DataFrame) -> VolRegimeData:
    """Puts the vol complex onto the traded calendar.

    Order matters and is deliberate: the traded frame is first reduced to
    days on which EVERY traded instrument printed (a spread cannot be held
    on a day one of its legs did not trade), and only then is the vol frame
    reindexed onto that calendar and forward-filled within
    VOL_INDEX_FFILL_LIMIT_DAYS. Doing it the other way round would let a
    vol-index calendar quietly decide which days are tradeable."""
    traded = traded_close.dropna(axis=1, how="all").dropna(axis=0, how="any")
    vol = vol_close.reindex(traded.index).ffill(limit=VOL_INDEX_FFILL_LIMIT_DAYS)
    return VolRegimeData(vol_close=vol, traded_close=traded)


# --- backtest --------------------------------------------------------------


@dataclass(frozen=True)
class FormationRecord:
    formation_date: date
    state_z: float | None
    position: float
    turnover: float
    cost: float
    skipped_reason: str | None = None


@dataclass
class TimingBacktestResult:
    spec_id: str
    status: str
    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    positions: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    spread_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    formations: list[FormationRecord] = field(default_factory=list)
    total_cost: float = 0.0
    total_financing_cost: float = 0.0
    n_skipped_formations: int = 0
    n_interior_skips: int = 0


def _spread_daily_returns(traded_close: pd.DataFrame, target: TimingTarget) -> pd.Series:
    """The buy-and-hold unit spread: +1 unit risk_on, -1 unit risk_off,
    dollar-neutral and self-financing (which is what lets metrics.sharpe_ratio
    be reused unmodified — see its own docstring). Costs are NOT in here;
    this series is both the strategy's raw return driver and the benchmark
    the static-tilt confound check regresses against, and the benchmark must
    be the untraded, uncosted spread for that regression to mean anything."""
    on = traded_close[target.risk_on].pct_change()
    off = traded_close[target.risk_off].pct_change()
    return (on - off).rename(f"{target.risk_on}_minus_{target.risk_off}")


def run_timing_backtest(
    data: VolRegimeData, spec: TimingSpec, config: VolRegimeConfig
) -> TimingBacktestResult:
    """One spec's non-overlapping walk-forward replay.

    THE NON-OVERLAP CONTRACT (amendment 2): formations sit at trading-day
    positions p0, p0+H, p0+2H, ... for H = spec.holding_days. The position set
    at formation p is held over days p+1..p+H inclusive, and the next
    formation is at exactly p+H. Every realized day therefore belongs to
    exactly one hold, and n_formations is a true count of independent bets.

    Formation is at the CLOSE: the state z uses vol data up to and including
    day p, and the position is assumed established at day p's close, so the
    first return it earns is day p+1's. There is no path by which a return
    from day p+1 onward can influence the position that earned it.

    A formation whose state is NaN — a vol index that has not yet reached its
    z-window warmup, or a stale gap beyond VOL_INDEX_FFILL_LIMIT_DAYS — is
    SKIPPED: the book goes flat and that hold contributes NO daily returns at
    all, rather than a run of forced zeros. Zeros would not be neutral; they
    would shrink both the mean and the std of the return series and quietly
    report the Sharpe of "hold cash for a year, then trade" as if it were the
    Sharpe of the signal. Leading skips are the ordinary case (a spec waiting
    on ^GVZ); an INTERIOR skip would mean a vol index died mid-sample, so
    those are counted separately (n_interior_skips) and logged, never merged
    into the leading-warmup count."""
    traded = data.traded_close
    for ticker in (spec.target.risk_on, spec.target.risk_off):
        if ticker not in traded.columns:
            return TimingBacktestResult(spec_id=spec.spec_id, status="missing_traded_instrument")

    state = spec.state_fn(data.vol_close, spec.z_window)
    spread = _spread_daily_returns(traded, spec.target)

    index = traded.index
    start_positions = np.flatnonzero(index.date >= config.formation_start)
    if len(start_positions) == 0:
        return TimingBacktestResult(spec_id=spec.spec_id, status="no_history_after_start")
    first = int(start_positions[0])

    holding = spec.holding_days
    n = len(index)

    returns: dict[pd.Timestamp, float] = {}
    positions: dict[pd.Timestamp, float] = {}
    formations: list[FormationRecord] = []
    total_cost = 0.0
    total_financing = 0.0
    previous_position = 0.0
    seen_active = False
    interior_skips = 0

    borrow_daily_rate = config.short_borrow_bps_per_year / 1e4 / FINANCING_DAYS_PER_YEAR

    p = first
    while p < n - 1:
        formation_date = index[p]
        raw_state = state.iloc[p] if p < len(state) else np.nan
        z = float(raw_state) if pd.notna(raw_state) else None

        if z is None:
            # Book goes flat. Closing an existing position IS a real trade and
            # is charged; opening from flat to flat is not.
            turnover = abs(0.0 - previous_position)
            cost = config.cost_bps / 1e4 * 2.0 * turnover
            total_cost += cost
            if seen_active:
                interior_skips += 1
            formations.append(
                FormationRecord(
                    formation_date=formation_date.date(),
                    state_z=None,
                    position=0.0,
                    turnover=turnover,
                    cost=cost,
                    skipped_reason="state_unavailable",
                )
            )
            previous_position = 0.0
            p += holding
            continue

        seen_active = True
        position = float(
            np.clip(spec.direction * z / spec.position_z_scale, -1.0, 1.0)
        )
        turnover = abs(position - previous_position)
        cost = config.cost_bps / 1e4 * 2.0 * turnover
        total_cost += cost

        formations.append(
            FormationRecord(
                formation_date=formation_date.date(),
                state_z=z,
                position=position,
                turnover=turnover,
                cost=cost,
            )
        )

        last = min(p + holding, n - 1)
        for j in range(p + 1, last + 1):
            gross = position * float(spread.iloc[j])
            if not np.isfinite(gross):
                gross = 0.0
            elapsed_days = (index[j] - index[j - 1]).days
            financing = borrow_daily_rate * abs(position) * max(elapsed_days, 0)
            total_financing += financing
            # The reformation charge lands on the hold's FIRST realized day
            # rather than on the formation day itself, because the formation
            # day's return already belongs to the previous hold. This shifts
            # WHEN the cost appears by one day and not WHETHER it is paid —
            # the same total is subtracted from the same return stream.
            day_cost = cost if j == p + 1 else 0.0
            returns[index[j]] = gross - day_cost - financing
            positions[index[j]] = position

        previous_position = position
        p += holding

    if interior_skips:
        logger.warning(
            "vol-regime spec %s: %d INTERIOR skipped formation(s) — a vol index went "
            "unavailable mid-sample rather than merely warming up. Its realized return series "
            "has gaps.",
            spec.spec_id,
            interior_skips,
        )

    if not returns:
        return TimingBacktestResult(
            spec_id=spec.spec_id,
            status="no_realized_returns",
            formations=formations,
            n_skipped_formations=sum(1 for f in formations if f.skipped_reason is not None),
            n_interior_skips=interior_skips,
        )

    daily = pd.Series(returns).sort_index()
    pos = pd.Series(positions).sort_index()
    return TimingBacktestResult(
        spec_id=spec.spec_id,
        status="ok",
        daily_returns=daily,
        positions=pos,
        spread_returns=spread.reindex(daily.index),
        formations=formations,
        total_cost=total_cost,
        total_financing_cost=total_financing,
        n_skipped_formations=sum(1 for f in formations if f.skipped_reason is not None),
        n_interior_skips=interior_skips,
    )


# --- confound diagnostics --------------------------------------------------


def _ols_beta_alpha(y: pd.Series, x: pd.Series) -> tuple[float, float]:
    """Slope and intercept of y on x, computed directly rather than through
    statsmodels because only the two coefficients are wanted and the inputs
    are already aligned and finite-checked. Returns (0.0, mean(y)) when x has
    no variance — the honest degenerate answer (nothing to explain y with),
    not a NaN that would silently poison the residual Sharpe."""
    joined = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(joined) < 3:
        return 0.0, 0.0
    xv = joined["x"].to_numpy()
    yv = joined["y"].to_numpy()
    var = float(np.var(xv, ddof=1))
    if var <= 0 or not np.isfinite(var):
        return 0.0, float(np.mean(yv))
    beta = float(np.cov(yv, xv, ddof=1)[0, 1] / var)
    alpha = float(np.mean(yv) - beta * np.mean(xv))
    return beta, alpha


@dataclass(frozen=True)
class ConfoundDiagnostic:
    """Everything needed to decide whether a positive Sharpe here is real or
    is a disguised static exposure. Computed for EVERY spec, always."""

    spec_id: str
    mean_position: float
    mean_abs_position: float
    fraction_long: float
    # The decisive one — see the module docstring's confound section.
    spread_beta: float
    spread_alpha_annualized: float
    # Sharpe of the BETA-HEDGED stream (y - beta*x), NOT of the OLS residual
    # (y - alpha - beta*x). The distinction is not pedantic: an OLS residual
    # series that includes an intercept has mean exactly zero by construction,
    # so its Sharpe is ~0 for every strategy ever measured. Computing it that
    # way — which this module did until it was caught by the "a genuine timing
    # signal must keep its residual Sharpe" test — would have reported every
    # single spec as a disguised static tilt with total confidence.
    residual_sharpe: float
    buy_and_hold_spread_sharpe: float
    equity_beta: float
    rates_beta: float
    subperiod_sharpes: tuple[float, ...]
    bootstrap_p_value: float | None
    n_formations: int


def block_bootstrap_sharpe_pvalue(
    returns: pd.Series,
    block_length: int,
    n_resamples: int = 2000,
    seed: int = 20260827,
) -> float | None:
    """Circular block bootstrap p-value for the observed Sharpe under a
    zero-mean null.

    WHY IT EXISTS even though this family's formations are already
    non-overlapping: non-overlap makes the HOLDS independent, but Sharpe and
    PSR are computed on DAILY returns, and the ~21-63 daily returns inside
    one hold share a single constant position. The daily n therefore
    overstates independent information even under a perfectly non-overlapping
    design. Resampling whole blocks of `block_length` (= holding_days) keeps
    that within-hold dependence intact in every replicate, so the null
    distribution is built from series with the same serial structure as the
    real one.

    Circular (wrapping past the end) rather than plain blocks so every
    observation is equally likely to appear in a replicate — plain blocks
    systematically under-sample the head and tail of the series.

    The null is imposed by DEMEANING, not by shuffling signs: the question is
    "could a series with this volatility and this serial dependence but NO
    edge produce a Sharpe this high", and demeaning is what removes exactly
    the edge while leaving both of the others alone."""
    clean = returns.dropna()
    n = len(clean)
    if n < MIN_REPLAY_TRADING_DAYS or block_length < 1 or n_resamples < 1:
        return None
    if n // block_length < MIN_FORMATIONS_FOR_BOOTSTRAP:
        return None

    observed = sharpe_ratio(clean)
    values = clean.to_numpy()
    centred = values - values.mean()

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block_length))
    starts = rng.integers(0, n, size=(n_resamples, n_blocks))
    offsets = np.arange(block_length)
    # (n_resamples, n_blocks, block_length) -> wrap -> flatten -> trim to n
    idx = (starts[:, :, None] + offsets[None, None, :]) % n
    samples = centred[idx].reshape(n_resamples, -1)[:, :n]

    means = samples.mean(axis=1)
    stds = samples.std(axis=1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        sharpes = np.where(stds > 0, means / stds * np.sqrt(TRADING_DAYS_PER_YEAR), 0.0)

    # One-sided: this family pre-declared its direction, so only an
    # unusually HIGH Sharpe is evidence. The +1/+1 correction is the standard
    # finite-resample adjustment that keeps the p-value from ever being
    # exactly 0 (which would claim more resolution than n_resamples has).
    exceed = int(np.sum(sharpes >= observed))
    return float((exceed + 1) / (n_resamples + 1))


def _subperiod_sharpes(returns: pd.Series, n_periods: int = 3) -> tuple[float, ...]:
    """Sharpe in each of n_periods equal, contiguous slices of the spec's own
    realized sample. A flight-to-quality signal can earn its entire lifetime
    Sharpe in one crisis autumn; this is the cheapest way to see that."""
    clean = returns.dropna()
    if len(clean) < n_periods * 2:
        return ()
    bounds = np.linspace(0, len(clean), n_periods + 1).astype(int)
    out = []
    for i in range(n_periods):
        chunk = clean.iloc[bounds[i] : bounds[i + 1]]
        out.append(sharpe_ratio(chunk) if len(chunk) >= 2 else 0.0)
    return tuple(out)


def compute_confound_diagnostics(
    spec: TimingSpec,
    replay: TimingBacktestResult,
    traded_close: pd.DataFrame,
) -> ConfoundDiagnostic:
    """The in-module adversarial pass.

    residual_sharpe is the number that decides whether a spec is real. It is
    the Sharpe of the strategy's returns AFTER removing its OLS exposure to
    the buy-and-hold target spread — i.e. after taking away everything a
    constant, signal-free position in the same two instruments would have
    earned. This is the identical test that reduced this project's
    commodities momentum family (raw DSR 0.767) to a residual Sharpe of
    ~0.000 once regressed on a precious-metals factor. A spec whose raw
    Sharpe is high and whose residual_sharpe is near zero has no timing
    content whatsoever; it is a static tilt that the z-score's drift
    happened to hold in a profitable direction."""
    daily = replay.daily_returns
    spread = replay.spread_returns

    spread_beta, spread_alpha = _ols_beta_alpha(daily, spread)
    aligned = pd.concat([daily.rename("y"), spread.rename("x")], axis=1).dropna()
    if len(aligned) >= 3:
        # BETA-HEDGED, NOT THE OLS RESIDUAL. Subtracting the fitted intercept
        # as well would set the mean to exactly zero by construction — an OLS
        # residual series with an intercept ALWAYS has mean 0, so its Sharpe
        # is always ~0 regardless of the strategy, which would make this whole
        # diagnostic vacuous while looking like a devastating verdict on every
        # spec. What is wanted is the return stream that remains after selling
        # off the static spread exposure and KEEPING whatever average return
        # survives: y - beta*x. Its mean is exactly the regression alpha, so
        # spread_alpha_annualized below and this Sharpe describe the same
        # stream.
        hedged = aligned["y"] - spread_beta * aligned["x"]
        # NUMERICAL GUARD, load-bearing not defensive -- see
        # RESIDUAL_DEGENERACY_RATIO's module-level comment for the exact
        # failure mode this closes (a bit-identical y/x replay produced a
        # confident +0.5497 residual_sharpe unguarded).
        y_std = float(aligned["y"].std(ddof=1))
        hedged_std = float(hedged.std(ddof=1))
        fully_explained = y_std > 0 and hedged_std <= RESIDUAL_DEGENERACY_RATIO * y_std
        residual_sharpe = 0.0 if fully_explained else sharpe_ratio(hedged)
        bh_sharpe = sharpe_ratio(aligned["x"])
    else:
        residual_sharpe = 0.0
        bh_sharpe = 0.0

    equity = traded_close[RISK_ON_EQUITY].pct_change().reindex(daily.index)
    rates = traded_close[RISK_OFF_DURATION].pct_change().reindex(daily.index)
    equity_beta, _ = _ols_beta_alpha(daily, equity)
    rates_beta, _ = _ols_beta_alpha(daily, rates)

    pos = replay.positions
    active = [f for f in replay.formations if f.skipped_reason is None]

    return ConfoundDiagnostic(
        spec_id=spec.spec_id,
        mean_position=float(pos.mean()) if len(pos) else 0.0,
        mean_abs_position=float(pos.abs().mean()) if len(pos) else 0.0,
        fraction_long=float((pos > 0).mean()) if len(pos) else 0.0,
        spread_beta=spread_beta,
        spread_alpha_annualized=spread_alpha * TRADING_DAYS_PER_YEAR,
        residual_sharpe=residual_sharpe,
        buy_and_hold_spread_sharpe=bh_sharpe,
        equity_beta=equity_beta,
        rates_beta=rates_beta,
        subperiod_sharpes=_subperiod_sharpes(daily),
        bootstrap_p_value=block_bootstrap_sharpe_pvalue(daily, spec.holding_days),
        n_formations=len(active),
    )


# --- screening -------------------------------------------------------------


@dataclass
class VolRegimeScreeningResult:
    spec_id: str
    state_key: str
    target_key: str
    holding_days: int
    citation: str
    hypothesis: str
    is_cross_asset: bool
    n_formations: int
    n_skipped_formations: int
    n_trading_days: int
    first_formation: date | None
    last_formation: date | None
    sharpe_annualized: float
    # Sum of the NET daily returns (costs and financing already subtracted).
    # A simple sum rather than a compounded product, so that adding back
    # total_cost_drag and total_financing_drag — themselves sums of
    # per-formation charges in the same units — reconstructs the pre-cost
    # return exactly. That additivity is what makes the breakeven-cost
    # multiple in build_vol_regime_disclosure arithmetic rather than an
    # approximation.
    net_cumulative_return: float
    total_cost_drag: float
    total_financing_drag: float
    deflated_sharpe: DeflatedSharpeResult
    confound: ConfoundDiagnostic


def screen_vol_regime_timing(
    data: VolRegimeData,
    specs: list[TimingSpec],
    config: VolRegimeConfig,
) -> list[VolRegimeScreeningResult]:
    """One Sharpe per spec, DSR-corrected for the family's pre-declared size.

    Trial counting follows cross_sectional.screen_cross_sectional_universe
    and intraday_patterns.screen_pattern_universe exactly, for the same
    documented reason: each spec IS already a single portfolio (there is no
    per-ticker result to cherry-pick, so no uncorrected "which ticker" search
    dimension exists), leaving "which definition" as the one search
    dimension. n_trials is therefore fixed at len(specs) — the family's
    literal pre-declared size — and never shrunk to however many specs
    survived the data floors, which would be gameable.

    sigma_sr is the ddof=1 standard deviation of every sibling spec's own
    Sharpe from this same pass, the direct analogue of the sibling convention
    used by both modules above.

    THE n_trials CAVEAT THIS USED TO CARRY IS NOW CLOSED (2026-09-04). It
    read: "48 counts THIS family only. The exploration that selected this
    hypothesis happened before this module existed and is not in the
    denominator, so every DSR here is an upper bound on the honest one."
    dsr_n_trials now raises 48 to the project-wide effectively-independent
    trial count whenever that is larger. See global_effective_n.py."""
    # POOLED DENOMINATOR (2026-09-04). len(specs) is this FAMILY's search;
    # it was never the whole search. dsr_n_trials raises it to the
    # project-wide effectively-independent trial count (ONC E[K] over every
    # persisted trial's realized returns) whenever that is larger, and only
    # ever larger -- see global_effective_n.py's "THE ONE GUARD".
    # `if specs else 0` because dsr_n_trials REFUSES a grid size of 0 (a
    # caller with no pre-declared family at all), and an empty spec list is
    # a legitimate no-op every one of these screens already returns [] for.
    n_trials = dsr_n_trials(len(specs)) if specs else 0

    replays: dict[str, TimingBacktestResult] = {}
    for spec in specs:
        replay = run_timing_backtest(data, spec, config)
        if replay.status != "ok":
            logger.info("vol-regime spec %s not replayed: %s", spec.spec_id, replay.status)
            continue
        if len(replay.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            logger.info(
                "vol-regime spec %s dropped: only %d realized days (floor %d)",
                spec.spec_id,
                len(replay.daily_returns),
                MIN_REPLAY_TRADING_DAYS,
            )
            continue
        replays[spec.spec_id] = replay

    sharpes = {sid: sharpe_ratio(r.daily_returns) for sid, r in replays.items()}
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {s.spec_id: s for s in specs}
    results: list[VolRegimeScreeningResult] = []
    for spec_id, replay in replays.items():
        spec = spec_by_id[spec_id]
        active = [f for f in replay.formations if f.skipped_reason is None]
        results.append(
            VolRegimeScreeningResult(
                spec_id=spec_id,
                state_key=spec.state_key,
                target_key=spec.target.key,
                holding_days=spec.holding_days,
                citation=spec.citation,
                hypothesis=spec.hypothesis,
                is_cross_asset=spec.is_cross_asset,
                n_formations=len(active),
                n_skipped_formations=replay.n_skipped_formations,
                n_trading_days=len(replay.daily_returns),
                first_formation=active[0].formation_date if active else None,
                last_formation=active[-1].formation_date if active else None,
                sharpe_annualized=sharpes[spec_id],
                net_cumulative_return=float(replay.daily_returns.sum()),
                total_cost_drag=replay.total_cost,
                total_financing_drag=replay.total_financing_cost,
                deflated_sharpe=compute_deflated_sharpe(
                    sharpes[spec_id], replay.daily_returns, n_trials, sigma_sr
                ),
                confound=compute_confound_diagnostics(spec, replay, data.traded_close),
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results


# --- disclosure ------------------------------------------------------------


@dataclass
class VolRegimeScreeningSummary:
    results: list[VolRegimeScreeningResult] = field(default_factory=list)
    missing_vol_indices: list[str] = field(default_factory=list)
    missing_traded_instruments: list[str] = field(default_factory=list)
    vol_index_starts: dict[str, date] = field(default_factory=dict)
    formation_calendar_start: date | None = None
    formation_calendar_end: date | None = None
    disclosure: list[str] = field(default_factory=list)


def build_vol_regime_disclosure(
    results: list[VolRegimeScreeningResult], config: VolRegimeConfig
) -> list[str]:
    """Plain-language caveats that must travel with any number from this
    family, including the breakeven-cost arithmetic that says how wrong the
    cost assumption would have to be to matter."""
    lines = [
        (
            f"n_trials = {VOL_REGIME_N_TRIALS} ({len(_STATE_VARIABLES)} state variables x "
            f"{len(VOL_REGIME_HOLDING_DAYS)} holding periods x "
            f"{len(VOL_REGIME_TARGETS)} targets), fixed before any return was computed."
        ),
        (
            "n_trials is POOLED across the project (2026-09-04): this family's own 48 specs are "
            "raised to the project-wide effectively-independent trial count -- ONC E[K] over every "
            "persisted trial's realized returns -- whenever that is larger, so the prior "
            "exploration that selected the cross-asset-implied-vol hypothesis is now counted in "
            "the denominator alongside it."
        ),
        (
            f"Direction was pre-declared uniformly at {VOL_REGIME_DIRECTION:+.0f} "
            "('richer implied vol -> risk-off') and never fitted per spec; negative Sharpes "
            "are reported as they came out, not flipped."
        ),
        (
            "Formations are non-overlapping: cadence equals holding_days, so n_formations is a "
            "true count of independent bets. Sharpe/PSR/DSR still use the DAILY series "
            "(matching every other family here), so a circular block bootstrap with block "
            "length = holding_days is reported alongside; where they disagree, believe the "
            "bootstrap."
        ),
        (
            f"Costs: {config.cost_bps:.1f}bp one-way per unit gross notional traded (a "
            f"flat-to-unit spread trades 2.0 gross, so ~{2 * config.cost_bps:.0f}bp to "
            f"establish), plus {config.short_borrow_bps_per_year:.0f}bp/yr borrow on the short "
            "notional, accrued on calendar days. Borrow is a disclosed general-collateral "
            "assumption, not a sourced quote."
        ),
        (
            "Position weights are re-set daily inside a hold at zero cost, and formation is "
            "assumed executable at the exact closing print — both mildly optimistic, both "
            "disclosed."
        ),
        (
            "The three ETFs were selected today from instruments that still exist and are "
            "still liquid; that hindsight-selection channel is small for SPY/IEF/HYG but not "
            "zero."
        ),
    ]

    if not results:
        lines.append("No spec produced a replayable return series — nothing to interpret.")
        return lines

    best = results[0]
    lines.append(
        f"Best raw Sharpe: {best.spec_id} at {best.sharpe_annualized:+.3f} over "
        f"{best.n_trading_days} days / {best.n_formations} independent formations."
    )

    # Cost sensitivity, stated as the multiple of the assumed cost that would
    # erase the strategy's own net return. The replayed series is already NET
    # of both charges, so the pre-cost cumulative return is
    # net + turnover_drag + financing_drag, and the breakeven multiple is
    # (pre-cost return) / (charges actually levied). Below 1.0 means the
    # strategy was under water before it paid a single basis point, and no
    # cost assumption can rescue it.
    charges = best.total_cost_drag + best.total_financing_drag
    lines.append(
        f"Cost sensitivity for {best.spec_id}: turnover drag {best.total_cost_drag:.4f} plus "
        f"financing drag {best.total_financing_drag:.4f} in cumulative return units, both "
        f"already subtracted from its reported net cumulative return of "
        f"{best.net_cumulative_return:+.4f}."
    )
    if charges > 0:
        multiple = (best.net_cumulative_return + charges) / charges
        if multiple <= 1.0:
            lines.append(
                f"  Breakeven cost multiple {multiple:.2f}x — at or below 1.0, meaning "
                f"{best.spec_id} was already unprofitable BEFORE costs. No cost assumption "
                "rescues it."
            )
        else:
            lines.append(
                f"  Breakeven cost multiple {multiple:.2f}x — costs would have to be "
                f"{multiple:.2f} times the assumed {config.cost_bps:.1f}bp/"
                f"{config.short_borrow_bps_per_year:.0f}bp-per-year to erase its net return."
            )

    # SIGNED, deliberately not abs(). The question a static-tilt check asks is
    # "did the positive Sharpe SURVIVE hedging out the static exposure", and
    # only an upside comparison answers it. Using abs() would let the
    # degenerate case through: when the position is near-constant the hedge is
    # near-perfect, the only thing left is the near-deterministic cost drag,
    # and its Sharpe is a large NEGATIVE number whose absolute value sails
    # past any threshold — the most blatant possible static tilt would be the
    # one the filter cleared.
    strong_tilt = [
        r
        for r in results
        if r.sharpe_annualized > 0
        and r.confound.residual_sharpe < 0.5 * r.sharpe_annualized
    ]
    if strong_tilt:
        lines.append(
            f"{len(strong_tilt)} spec(s) with a positive raw Sharpe lose more than half of it "
            "once their static exposure to the buy-and-hold target spread is regressed out — "
            "those are disguised static tilts, not timing signals."
        )
    return lines


# --- production entry point ------------------------------------------------


def run_vol_regime_screening(
    start: date = VOL_REGIME_FORMATION_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    config: VolRegimeConfig | None = None,
    specs: list[TimingSpec] | None = None,
) -> VolRegimeScreeningSummary:
    """THE production entry point for the Vol-Regime family, scoped to
    exactly VOL_REGIME_FAMILY's 48 definitions and their own n_trials.

    Fetches the seven-index volatility complex and the three traded ETFs,
    aligns them onto the tradeable calendar, and screens the family.
    `start` is the first FORMATION date; price history is padded before it by
    VOL_REGIME_HISTORY_PADDING_CALENDAR_DAYS so the 252-day z-window is warm,
    and formations never occur in the padding."""
    # date.today() is the LOCAL date. Immaterial here — it is only the
    # exclusive end bound of a price fetch, where being a day either side
    # just includes or omits the most recent bar.
    end = end if end is not None else date.today()  # noqa: DTZ011
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else default_vol_regime_config()
    config.formation_start = start
    specs = specs if specs is not None else VOL_REGIME_FAMILY

    padded_start = start - timedelta(days=VOL_REGIME_HISTORY_PADDING_CALENDAR_DAYS)

    vol_close, missing_vol = provider.get_price_history(
        list(VOL_INDEX_UNIVERSE), padded_start, end
    )
    traded_close, missing_traded = provider.get_price_history(
        list(TRADED_UNIVERSE), padded_start, end
    )

    if vol_close.empty or traded_close.empty:
        return VolRegimeScreeningSummary(
            missing_vol_indices=missing_vol,
            missing_traded_instruments=missing_traded,
        )

    if missing_vol:
        logger.error(
            "Vol-regime screening: %d of %d volatility indices resolved NO price data (%s). "
            "Every spec depending on them will skip every formation.",
            len(missing_vol),
            len(VOL_INDEX_UNIVERSE),
            ", ".join(missing_vol),
        )
    if missing_traded:
        logger.error(
            "Vol-regime screening: traded instrument(s) missing (%s) — the affected target's "
            "specs cannot be replayed at all.",
            ", ".join(missing_traded),
        )

    starts: dict[str, date] = {}
    for ticker in vol_close.columns:
        series = vol_close[ticker].dropna()
        if series.empty:
            continue
        observed = series.index[0].date()
        starts[str(ticker)] = observed
        expected = VOL_INDEX_VERIFIED_START.get(str(ticker))
        # The fetch is padded, so an index whose real inception predates the
        # padding legitimately appears to "start" at the padding boundary.
        # Only a start LATER than both the verified inception and the padding
        # boundary indicates the vendor actually truncated history.
        if expected is not None and observed > max(expected, padded_start) + timedelta(days=7):
            logger.warning(
                "Vol-regime screening: %s history starts %s, later than the verified inception "
                "%s — the vendor may have truncated this index.",
                ticker,
                observed,
                expected,
            )

    data = align_vol_regime_data(vol_close, traded_close)
    results = screen_vol_regime_timing(data, specs, config)

    formation_dates = [
        r.first_formation for r in results if r.first_formation is not None
    ]
    last_dates = [r.last_formation for r in results if r.last_formation is not None]

    return VolRegimeScreeningSummary(
        results=results,
        missing_vol_indices=missing_vol,
        missing_traded_instruments=missing_traded,
        vol_index_starts=starts,
        formation_calendar_start=min(formation_dates) if formation_dates else None,
        formation_calendar_end=max(last_dates) if last_dates else None,
        disclosure=build_vol_regime_disclosure(results, config),
    )


__all__ = [
    "CROSS_ASSET_COMPONENTS",
    "CROSS_ASSET_MIN_COMPONENTS",
    "MIN_REPLAY_TRADING_DAYS",
    "TARGET_CREDIT_VS_DURATION",
    "TARGET_EQUITY_VS_DURATION",
    "TRADED_UNIVERSE",
    "VOL_INDEX_FFILL_LIMIT_DAYS",
    "VOL_INDEX_UNIVERSE",
    "VOL_INDEX_VERIFIED_START",
    "VOL_INDEX_VIX_CORRELATIONS",
    "VOL_REGIME_COST_BPS",
    "VOL_REGIME_DIRECTION",
    "VOL_REGIME_FAMILY",
    "VOL_REGIME_FORMATION_START",
    "VOL_REGIME_HOLDING_DAYS",
    "VOL_REGIME_MIN_HOLDING_DAYS",
    "VOL_REGIME_N_TRIALS",
    "VOL_REGIME_POSITION_Z_SCALE",
    "VOL_REGIME_SHORT_BORROW_BPS_PER_YEAR",
    "VOL_REGIME_TARGETS",
    "VOL_REGIME_Z_WINDOW",
    "ConfoundDiagnostic",
    "FormationRecord",
    "TimingBacktestResult",
    "TimingSpec",
    "TimingTarget",
    "VolRegimeConfig",
    "VolRegimeData",
    "VolRegimeScreeningResult",
    "VolRegimeScreeningSummary",
    "align_vol_regime_data",
    "block_bootstrap_sharpe_pvalue",
    "build_vol_regime_disclosure",
    "compute_confound_diagnostics",
    "default_vol_regime_config",
    "run_timing_backtest",
    "run_vol_regime_screening",
    "screen_vol_regime_timing",
    "state_cross_asset_composite",
    "state_level",
    "state_ratio",
    "trailing_zscore",
]
