"""The Correlation-Risk-Premium (CRP) family: CBOE implied correlation minus
realized correlation, traded as an outright SPY market-timing signal, screened
as exactly 15 PRE-DECLARED specs with its own n_trials denominator.

THE HYPOTHESIS
============================================================================
Driessen, Maenhout & Vilkov, "The Price of Correlation Risk: Evidence from
Equity Options", Journal of Finance 64(3), 2009: index options are expensive
relative to a portfolio of individual-stock options, and the wedge is a priced
CORRELATION risk premium — compensation for the fact that diversification
fails exactly when it is most needed. The premium is a read on aggregate risk
aversion, so a high premium should be followed by HIGHER subsequent equity
returns, in the same way Bollerslev, Tauchen & Zhou (RFS 22(11), 2009) find
for the variance risk premium.

    CRP_t = implied_correlation_t - realized_correlation_t

============================================================================
THE OVERLAP PROBLEM — WHY THIS MODULE MUST PROVE IT IS NOT vol_regime_timing
============================================================================
This project ALREADY screened and rejected `vol_regime_timing.py`, a 48-spec
cross-asset IMPLIED-VOLATILITY-dislocation family whose control spec was
`vix_level` = z(log ^VIX). Implied correlation is mechanically related to the
VIX family: index variance is approximately average constituent variance times
average pairwise correlation, so an implied-correlation index is, definitionally,
index implied vol deflated by constituent implied vol. A positive result here
could very easily be the already-rejected signal wearing a new name.

That is not left to a reviewer to notice. compute_overlap_diagnostics() is run
on EVERY spec, always, and reports three things against the rejected family's
own `vix_level` state variable:

  1. signal overlap in LEVELS  — corr(z(CRP), z(log VIX)). This is the decisive
     one, because the LEVEL of the z-score is what sets the position, so two
     signals with a high level correlation hold the same book.
  2. signal overlap in DAILY CHANGES — the same pair, differenced. Reported
     because a low level correlation with a high change correlation means the
     two signals share short-run dynamics while differing in regime, which is
     worth seeing even though it is not what sets the position.
  3. RETURN overlap — corr(this spec's daily returns, the SAME-horizon
     vix_level spec's daily returns). The end of the argument: if two
     strategies' realized P&L streams are highly correlated, it does not
     matter what their signals are called.

CRP_VIX_OVERLAP_THRESHOLD = 0.5, declared in advance. Above it on the LEVELS
or on the RETURNS, any apparent edge here is reported as SUSPECT — a probable
relabelling of a family this project already rejected — regardless of how good
the Sharpe looks. A number does not get to overrule this check.

Measured live 2026-08-27 over the full overlapping sample, before any backtest
was run: corr(raw COR1M, raw ^VIX) = 0.641 — the mechanical relationship is
real and large. Subtracting realized correlation removes most of it:
corr(raw CRP_1m, raw ^VIX) = 0.169. That is the argument that CRP is a
different object from VIX, and it is an argument about the RAW series only;
the z-scored, position-setting comparison is computed per-run and reported.

============================================================================
THE DATA, VERIFIED LIVE 2026-08-27
============================================================================
CBOE publishes its implied-correlation indices as free, unauthenticated CSV:

    https://cdn.cboe.com/api/global/us_indices/daily_prices/COR1M_History.csv
    https://cdn.cboe.com/api/global/us_indices/daily_prices/COR3M_History.csv

Both pulled successfully this session (HTTP 200, ~264KB each):

    COR1M   n=5194   2006-01-03..2026-08-26   min 2.93  med 35.54  max 96.59
    COR3M   n=5179   2006-01-03..2026-08-26   min 7.19  med 41.00  max 90.79
    corr(COR1M, COR3M) in levels = 0.946

These are index-level implied correlation in PERCENT (a 35.54 print means
35.54%), derived by CBOE from SPX option prices against the option prices of
the index's largest components.

REALIZED CORRELATION comes from this project's OWN risk machinery, not a
reimplementation: risk.correlation.correlation_matrix followed by
risk.diversification.average_pairwise_correlation (the mean off-diagonal
entry), computed on a trailing window and rescaled to percent so it is on
COR1M's scale.

THE UNIVERSE IT IS COMPUTED OVER — a real limitation, disclosed not hidden.
The nine SPDR sector ETFs, a FIXED pre-declared set with continuous history
from 1998. Two consequences, both measured:

 a) LEVEL BIAS. Sector ETFs are already-diversified baskets, so their average
    pairwise correlation is structurally HIGHER than that of the individual
    large-cap stocks CBOE prices. Measured: realized_corr_21d has median 57.5%
    against COR1M's 35.5%, so CRP_1m is negative on 92% of days (mean -18.96).
    THE LEVEL OF CRP AS COMPUTED HERE IS THEREFORE NOT THE DRIESSEN-MAENHOUT-
    VILKOV PREMIUM AND MUST NOT BE READ AS ONE. Only its time variation is
    used: every spec trades a trailing z-score, which removes any constant
    offset. What the z-score does NOT remove is drift in the offset — if the
    sector-basket-vs-single-stock correlation gap itself trends, that trend
    enters the signal. This is the single largest known weakness of the
    construction and is why the point-in-time cross-check below exists.

 b) WHY NOT POINT-IN-TIME S&P 500 CONSTITUENTS, which would match CBOE's
    methodology directly. This project does have that data
    (sp500_membership_history.get_universe_as_of), and it IS used here — as a
    cross-check, not as the production signal. Two reasons it is not the
    production signal, both pre-declared: its coverage starts 2015-01-07
    (MEMBERSHIP_DATA_START), which would discard 2006-2015 and with it the
    2008 crisis — the single most informative correlation regime available —
    and constituent price history for delisted names is this project's known
    OPEN data gap, so a point-in-time constituent correlation computed on
    yfinance quietly reintroduces survivorship bias through the back door.
    A fixed set of nine ETFs that never delisted has neither problem.
    compute_pit_realized_correlation_crosscheck() computes the point-in-time
    version over 2015+ and reports how closely it tracks the sector proxy, so
    the proxy's validity is a measured number rather than an assertion.

    MEASURED, live 2026-08-27, over 573 sampled dates 2015-02-06..2026-06-24
    against the ACTUAL point-in-time S&P 500 membership (mean 439 constituents
    with usable price history per cross-section, min 361, max 497):

        corr(sector-ETF proxy, true constituent correlation)  LEVELS  = 0.930
                                                              CHANGES = 0.870
        mean level: 48.5% (sector proxy) vs 28.6% (constituents)

    So the proxy TRACKS the quantity it stands in for closely, while sitting
    ~20 percentage points above it — exactly the constant-offset-plus-good-
    tracking picture that a trailing z-score handles correctly. That 0.930 is
    the evidence for (a)'s claim that only the LEVEL is unusable. It is not a
    licence to read CRP levels as the DMV premium; it is the reason the
    z-scored SIGNAL can still be taken seriously.

    The 153 tickers that failed to download in that cross-check (WFM, COL,
    HOT, TWC, CELG, MON, RTN, ...) are precisely this project's known OPEN
    delisted-coverage gap, and their absence is why the point-in-time version
    is a diagnostic here rather than the traded signal.

============================================================================
THE 15 SPECS, AND WHY THE SIGN IS NOT A FREE PARAMETER
============================================================================
5 state variables x 3 holding periods x 1 target = 15, asserted three ways in
_build_crp_family() against the pre-declared CRP_N_TRIALS, for the same reason
vol_regime_timing.py asserts its 48: a silent drift in family size silently
changes the DSR denominator.

  crp_1m        z(COR1M - realized_corr_21d)   THE HYPOTHESIS, 1-month tenor
  crp_3m        z(COR3M - realized_corr_63d)   THE HYPOTHESIS, 3-month tenor
  implied_1m    z(COR1M)                       CONTROL
  realized_21d  z(realized_corr_21d)           CONTROL
  vix_level     z(log ^VIX)                    CONTROL — the rejected family's

The three controls are not filler; they spend 9 of the 15 trials and each
kills a specific way this family could be fooling itself:

  implied_1m   — if implied correlation ALONE does as well as CRP, then the
                 "premium" framing (the subtraction of realized) is decoration
                 and the family's entire thesis is unsupported by its own
                 contents.
  realized_21d — if realized correlation alone does as well, the CBOE data is
                 contributing nothing and this is a realized-vol-style signal.
  vix_level    — the direct like-for-like against the ALREADY-REJECTED family,
                 on the same target, over the same sample, at the same
                 horizons. If vix_level matches or beats the CRP specs, this
                 family is that family.

WINDOW CHOICE: realized correlation is measured over a window TENOR-MATCHED to
the implied index it is subtracted from — 21 trading days against COR1M
(1 month), 63 against COR3M (3 months). This is the only defensible pairing:
a risk premium is the wedge between what is priced for a horizon and what is
realized over THAT SAME horizon, and pairing a 1-month implied with a 3-month
realized would measure a term-structure effect instead. The pairing is fixed
a priori and the off-diagonal combinations are deliberately NOT searched —
doing so would double the family to 30 while the extra specs measured
something the hypothesis does not claim.

DIRECTION is +1 for all 15 specs (CRP_DIRECTION). Letting each spec choose its
own sign would double the real search to 30 while still reporting n_trials=15
— the exact uncounted-degree-of-freedom failure the DSR exists to prevent.
Specs whose true sign is the opposite will print negative Sharpes here and
will NOT be flipped.

HOLDING PERIODS: 5, 21, 63 trading days. The 5-day spec is included here
although vol_regime_timing.py deliberately floored its own family at 21,
because that floor was a COST judgement about a two-legged ETF spread and this
family trades SPY outright, whose quoted half-spread is ~0.08bp on a ~$6xx
price. It is still the spec most exposed to the cost assumption, and
build_crp_disclosure() reports its breakeven cost multiple separately.

============================================================================
COSTS, AND THE ONE PLACE THIS FAMILY IS NOT SELF-FINANCING
============================================================================
CRP_COST_BPS = 2.0 one-way per unit of gross notional traded. SPY's actual
one-cent bid/ask at a ~$6xx price is ~0.08bp of half-spread, so 2.0bp is
~25x the quoted half-spread — deliberately far above it, to cover commission
and any slippage.

CRP_FINANCING_BPS_PER_YEAR = 100.0, charged on |position| for BOTH SIGNS,
accrued on CALENDAR days / 365. This differs from vol_regime_timing.py's 50bp
and the difference is load-bearing, not a tweak: that family traded a
dollar-neutral two-legged spread, which is genuinely self-financing (short
proceeds fund the long) and whose only residual cost is the short rebate
shortfall. THIS family trades SPY OUTRIGHT, so a long position must be FUNDED
and a short position pays borrow. metrics.sharpe_ratio subtracts no risk-free
rate — its docstring is explicit that this is licensed by dollar-neutrality —
so charging financing on both signs is what keeps the resulting series
interpretable as an excess return rather than silently crediting the strategy
with the cash rate on every long day. 100bp/yr is a DISCLOSED BLENDED
ASSUMPTION, not a sourced funding or borrow quote, and it is on the low side
for 2006-2026 (average fed funds over that period is materially above 1%),
which is the honest direction to flag: this assumption FLATTERS long-biased
specs. build_crp_disclosure() reports the breakeven cost multiple so a reader
can see how much it would have to be wrong by to matter.

============================================================================
WHAT COULD MAKE A POSITIVE RESULT HERE FAKE — CHECKED IN-MODULE
============================================================================
Two of this project's best-looking results were killed on adversarial recheck
(a commodities family that was a disguised long-precious-metals bet, residual
Sharpe ~0.000 after regressing on a metals factor; a buyback family whose DSR
sat below the median best-of-7 under pure noise). The equivalents here are
computed automatically for EVERY spec by compute_confound_diagnostics():

 1. STATIC LONG-SPY TILT — the killer, and it is worse for this family than
    for any spread family. A trailing z-score is only approximately mean-zero;
    if CRP drifts, the z sits persistently on one side and the "timing" signal
    is really a constant long-SPY position. Over 2007-2026 a constant long SPY
    is an enormous winner for reasons having nothing to do with correlation.
    So every spec reports mean_position and, decisively, spy_beta and
    residual_sharpe from an OLS of its own daily returns on buy-and-hold SPY
    (reusing risk.beta.compute_beta). This is precisely the regression that
    reduced the commodities family to zero. A spec whose residual_sharpe
    collapses toward 0 while its raw Sharpe looks good IS a static tilt.
 2. VIX-FAMILY OVERLAP — see the overlap section above. Computed always.
 3. ONE-CRISIS DEPENDENCE — the sample opens in January 2007 so it contains
    the 2008 crisis, which is a strength for regime coverage and a hazard for
    inference: a risk-aversion signal can earn its whole lifetime Sharpe in
    one autumn. Every spec reports subperiod_sharpes in equal thirds.
 4. WITHIN-HOLD DEPENDENCE — formations are non-overlapping, so the HOLDS are
    independent, but Sharpe/PSR/DSR are computed on the DAILY series (matching
    every other family here, so the numbers stay comparable). The ~5-63 daily
    returns inside one hold share a constant position, so the daily n
    overstates independent information. Every spec therefore also gets
    vol_regime_timing.block_bootstrap_sharpe_pvalue with block length =
    holding_days — REUSED, not reimplemented, so the two families' p-values
    mean the same thing. Where the two disagree, believe the bootstrap.
 5. THE SEARCH THAT LED HERE IS NOT IN n_trials. 15 is the size of THIS
    family, declared before any return was computed. It does not cover the
    literature-scan that nominated the correlation risk premium, nor the ~10
    other asset-class families screened in this project this session. The true
    multiple-comparisons burden is strictly larger than 15, so every DSR
    reported here is an UPPER BOUND on the honest one. That correction is what
    sank the buyback family and it applies to every number this module prints.

RESIDUAL BIASES NOT FIXED, only disclosed: the nine sector ETFs and SPY were
selected today from instruments that still exist and are still liquid.
Positions are treated as re-set daily inside a hold at zero cost, matching
cross_sectional.py's convention and mildly optimistic. Formation is assumed
executable at the exact closing print. CBOE's own index methodology has
changed over the 2006-2026 history (the COR1M/COR3M series as published are
CBOE's current-methodology backfill), which this module consumes as given.
"""

import io
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import httpx
import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.deflated_sharpe import (
    MIN_TRIALS_FOR_DSR,
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    PointInTimeUniverseError,
    get_universe_as_of,
    get_universe_over,
)
from app.services.research_lab.vol_regime_timing import (
    FINANCING_DAYS_PER_YEAR,
    MIN_REPLAY_TRADING_DAYS,
    block_bootstrap_sharpe_pvalue,
    trailing_zscore,
)
from app.services.risk.beta import compute_beta
from app.services.risk.correlation import correlation_matrix
from app.services.risk.diversification import average_pairwise_correlation

logger = logging.getLogger(__name__)

# --- CBOE implied-correlation data ----------------------------------------

CBOE_DAILY_PRICES_BASE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/"

COR1M = "COR1M"
COR3M = "COR3M"

IMPLIED_CORRELATION_INDICES: tuple[str, ...] = (COR1M, COR3M)

# Verified live 2026-08-27: both endpoints returned HTTP 200 with real history
# back to 2006-01-03. Used by run_crp_screening's data-sanity log as a
# WARNING trigger, never as a hard gate — a vendor extending or truncating
# history should surface, not crash a research run.
CBOE_VERIFIED_START: dict[str, date] = {
    COR1M: date(2006, 1, 3),
    COR3M: date(2006, 1, 3),
}
CBOE_VERIFIED_ROWS: dict[str, int] = {COR1M: 5194, COR3M: 5179}

CBOE_HTTP_TIMEOUT_SECONDS = 30.0
CBOE_USER_AGENT = "aladdin2-research/1.0"

# CBOE prints on the SPX calendar; the traded calendar is SPY's. A missing
# print is carried forward at most this many days — carrying an OLDER value
# forward can only stale the signal, never leak future information, and the
# limit stops a genuinely dead feed from being silently carried for months.
# Same value and same reasoning as vol_regime_timing.VOL_INDEX_FFILL_LIMIT_DAYS.
CBOE_FFILL_LIMIT_DAYS = 5


class CboeDataError(RuntimeError):
    """Raised when the CBOE endpoint is reachable but its payload is not the
    expected daily-price CSV. Distinct from httpx's transport errors so a
    caller can tell 'the network failed' from 'the feed changed shape'."""


def parse_cboe_history_csv(payload: str, symbol: str) -> pd.Series:
    """CBOE daily-price CSV -> a date-indexed CLOSE series.

    Column names are upper-cased and stripped before lookup because the feed
    has historically shipped both 'DATE' and ' Date '. Dates are parsed with
    an EXPLICIT %m/%d/%Y format rather than letting pandas infer: the feed is
    US-formatted, and an inferred parse would silently read 03/04/2006 as
    4 March in one run and 3 April in another depending on how many
    unambiguous rows happened to lead the file.

    Non-positive closes are dropped rather than kept — an implied correlation
    of zero or below is not a real print, and leaving one in would produce a
    garbage z-score downstream."""
    frame = pd.read_csv(io.StringIO(payload))
    frame.columns = [str(c).strip().upper() for c in frame.columns]
    for required in ("DATE", "CLOSE"):
        if required not in frame.columns:
            raise CboeDataError(
                f"{symbol}: CBOE payload has columns {list(frame.columns)}, expected a "
                f"'{required}' column — the feed's shape has changed."
            )
    parsed = pd.to_datetime(frame["DATE"], format="%m/%d/%Y", errors="coerce")
    series = (
        pd.Series(pd.to_numeric(frame["CLOSE"], errors="coerce").to_numpy(), index=parsed)
        .dropna()
        .sort_index()
    )
    series = series[series.index.notna()]
    series = series[series > 0]
    if series.empty:
        raise CboeDataError(f"{symbol}: CBOE payload parsed to zero usable rows.")
    return series.astype(float).rename(symbol)


def fetch_cboe_implied_correlation(
    symbols: tuple[str, ...] = IMPLIED_CORRELATION_INDICES,
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """Pull CBOE's free implied-correlation history. No auth, no key.

    `client` is injectable so tests can exercise the parse/align path against
    a stub without touching the network, following sp500_membership_refresh.py's
    convention of passing an httpx.Client rather than patching a module global."""
    owned = client is None
    active = client or httpx.Client(
        timeout=CBOE_HTTP_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": CBOE_USER_AGENT},
    )
    try:
        columns: list[pd.Series] = []
        for symbol in symbols:
            response = active.get(f"{CBOE_DAILY_PRICES_BASE}{symbol}_History.csv")
            response.raise_for_status()
            columns.append(parse_cboe_history_csv(response.text, symbol))
    finally:
        if owned:
            active.close()
    return pd.concat(columns, axis=1, sort=True).sort_index()


# --- realized correlation --------------------------------------------------

# Fixed, pre-declared, NOT a searched axis. The nine SPDR sector ETFs: complete
# coverage of the S&P 500 by GICS sector, continuous history from 1998, and
# none has ever delisted. (The four sectors carved out later — XLRE 2015,
# XLC 2018, and the XLK/XLC reshuffle — are deliberately excluded: adding them
# would change the composition of the correlation measure partway through the
# sample, which is exactly the kind of silent regime break that makes a
# trailing z-score misbehave.)
SECTOR_ETF_UNIVERSE: tuple[str, ...] = (
    "XLB",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
)

TRADED_TICKER = "SPY"

VIX = "^VIX"

# Tenor-matched to the implied index each is subtracted from. See the module
# docstring's WINDOW CHOICE note for why the off-diagonal pairings are not
# searched.
REALIZED_WINDOW_1M = 21
REALIZED_WINDOW_3M = 63

# Below this many names a mean off-diagonal correlation is not a meaningful
# summary of a cross-section. 3 is the floor at which "average pairwise" has
# at least three distinct pairs behind it.
MIN_NAMES_FOR_REALIZED_CORRELATION = 3


def rolling_average_pairwise_correlation(
    returns: pd.DataFrame, window: int, *, as_percent: bool = True
) -> pd.Series:
    """Trailing average pairwise correlation, one value per date.

    REUSES risk.correlation.correlation_matrix and
    risk.diversification.average_pairwise_correlation unmodified rather than
    recomputing a mean off-diagonal by hand — those two are this project's
    definition of the quantity, and a second implementation would be free to
    drift from it.

    The value at date t uses the window ENDING at t inclusive, so it is
    knowable at t's close and carries no look-ahead. Rescaled to PERCENT by
    default so it lands on CBOE's scale (a COR1M print of 35.54 means 35.54%)
    and the subtraction that forms CRP is between like units."""
    if window < 2:
        raise ValueError(f"realized-correlation window must be >= 2, got {window}")
    if returns.shape[1] < MIN_NAMES_FOR_REALIZED_CORRELATION:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], name=returns.index.name))

    scale = 100.0 if as_percent else 1.0
    values: dict[pd.Timestamp, float] = {}
    for end in range(window, len(returns) + 1):
        chunk = returns.iloc[end - window : end]
        values[returns.index[end - 1]] = (
            average_pairwise_correlation(correlation_matrix(chunk)) * scale
        )
    return pd.Series(values, dtype=float).sort_index()


def correlation_risk_premium(
    implied: pd.Series, realized: pd.Series
) -> pd.Series:
    """CRP = implied - realized, on the intersection of their dates.

    Deliberately NOT forward-filled here: alignment onto the traded calendar
    (and the bounded ffill that goes with it) is align_crp_data's job, and
    doing it twice would let a stale print survive two ffill budgets."""
    joined = pd.concat(
        [implied.rename("implied"), realized.rename("realized")], axis=1, sort=True
    ).dropna()
    return (joined["implied"] - joined["realized"]).rename("crp")


# --- pre-declared family parameters ---------------------------------------

# One fixed value, never searched — searching it would multiply the family and
# the DSR denominator. 252 = one year, the conventional "relative to the recent
# regime" window, and identical to vol_regime_timing.VOL_REGIME_Z_WINDOW so the
# vix_level control spec here is the SAME object that family screened.
CRP_Z_WINDOW = 252

# |z| at which the position reaches full size. Pre-declared, not tuned; being a
# pure scalar on an otherwise unchanged position path it moves the return
# series' SCALE far more than its Sharpe (which is scale-invariant except
# through the clip).
CRP_POSITION_Z_SCALE = 1.0

CRP_HOLDING_DAYS: tuple[int, ...] = (5, 21, 63)

# Uniform, pre-declared from the cited literature, never fitted per spec.
CRP_DIRECTION = 1.0

CRP_N_TRIALS = 15

CRP_COST_BPS = 2.0

# On |position|, BOTH SIGNS — this family trades SPY outright and is not
# self-financing. See the module docstring's COSTS section.
CRP_FINANCING_BPS_PER_YEAR = 100.0

# Declared in advance. Above this on the z-score LEVELS or on the realized
# strategy RETURNS, a spec is a probable relabelling of the already-rejected
# vol-regime family and is reported as SUSPECT whatever its Sharpe.
CRP_VIX_OVERLAP_THRESHOLD = 0.5

# First formation. COR1M starts 2006-01-03; a 252-day z-window on CRP is warm
# ~2007-01-05. Set just past that so the sample opens BEFORE the 2008 crisis
# — the most informative correlation regime available, and the one a
# risk-aversion signal most needs to be tested against.
CRP_FORMATION_START = date(2007, 1, 16)

# Calendar padding fetched before CRP_FORMATION_START, sized to warm both the
# 63-day realized window and the 252-day z-window on top of it (~315 trading
# days ~= 460 calendar days) with generous room for holiday clustering.
CRP_HISTORY_PADDING_CALENDAR_DAYS = 1100

# A spec needs at least this many independent holds for its bootstrap p-value
# to mean anything. Same register as vol_regime_timing's own floor.
MIN_FORMATIONS_FOR_BOOTSTRAP = 8

# When a beta-hedged return stream's standard deviation falls to this fraction
# of the original's, the hedge has explained everything and what remains is
# floating-point dust, not a residual. See compute_confound_diagnostics for
# why an unguarded Sharpe of that dust is actively misleading. 1e-8 sits many
# orders of magnitude above double-precision noise (~1e-16 relative) and many
# below any real residual, so nothing genuine can be swallowed by it.
RESIDUAL_DEGENERACY_RATIO = 1e-8

# --- citations -------------------------------------------------------------

CORRELATION_RISK_CITATION = (
    "Driessen, Maenhout & Vilkov, 'The Price of Correlation Risk: Evidence from Equity Options', "
    "Journal of Finance 64(3), 2009 — index options are expensive relative to a basket of "
    "individual-stock options, and the wedge is a priced correlation risk premium compensating "
    "for diversification failing in a crash. Paired with Bollerslev, Tauchen & Zhou, "
    "'Expected Stock Returns and Variance Risk Premia', Review of Financial Studies 22(11), 2009, "
    "which finds the analogous implied-minus-realized variance premium predicts HIGHER subsequent "
    "equity returns — the source of this family's pre-declared +1 direction."
)

IMPLIED_CORRELATION_CITATION = (
    "CBOE, 'Cboe Implied Correlation Indices' methodology — COR1M/COR3M measure the average "
    "implied correlation among S&P 500 components priced into index versus single-stock options. "
    "Traded here as a LEVEL control on " + CORRELATION_RISK_CITATION
)

REALIZED_CORRELATION_CITATION = (
    "Pollet & Wilson, 'Average Correlation and Stock Market Returns', Journal of Financial "
    "Economics 96(3), 2010 — average REALIZED pairwise correlation among large stocks forecasts "
    "market returns on its own. The control that asks whether the CBOE implied data contributes "
    "anything beyond it."
)

VIX_CONTROL_CITATION = (
    "Whaley, 'Understanding the VIX', Journal of Portfolio Management 35(3), 2009. This spec is "
    "the `vix_level` state variable of this project's ALREADY-REJECTED vol_regime_timing family, "
    "reproduced here on this family's own target so the overlap check is like-for-like in return "
    "space rather than only in signal space."
)


# --- state variables -------------------------------------------------------


@dataclass(frozen=True)
class CrpData:
    """Implied correlation, realized correlation, the VIX control and the
    traded close, all on ONE shared trading calendar.

    `traded_close` defines the calendar because it is the only series that is
    actually tradeable — an implied-correlation print on a day SPY did not
    trade is unusable, and a SPY day with no fresh CBOE print is handled by
    carrying the last one forward (older information, never future
    information; see CBOE_FFILL_LIMIT_DAYS)."""

    implied: pd.DataFrame
    realized: pd.DataFrame
    vix: pd.Series
    traded_close: pd.Series

    def __post_init__(self) -> None:
        for name, frame in (
            ("realized", self.realized),
            ("implied", self.implied),
        ):
            if not frame.index.equals(self.traded_close.index):
                raise ValueError(
                    f"{name} and traded_close must share an identical index — align them with "
                    "align_crp_data() rather than passing raw frames"
                )
        if not self.vix.index.equals(self.traded_close.index):
            raise ValueError(
                "vix and traded_close must share an identical index — align them with "
                "align_crp_data() rather than passing raw frames"
            )


def align_crp_data(
    implied: pd.DataFrame,
    sector_close: pd.DataFrame,
    vix: pd.Series,
    traded_close: pd.Series,
) -> CrpData:
    """Puts every input onto the TRADED calendar and computes the realized
    correlation columns.

    Order matters and is deliberate. The traded series is reduced first to
    days SPY actually printed; realized correlation is computed on the sector
    returns' OWN full calendar and only then reindexed, so that a SPY holiday
    does not silently shorten a 21-day correlation window; and the CBOE frame
    is reindexed last and forward-filled within CBOE_FFILL_LIMIT_DAYS. Doing
    it the other way round would let a vendor's calendar decide which days are
    tradeable."""
    traded = traded_close.dropna()
    sectors = sector_close.dropna(axis=1, how="all").dropna(axis=0, how="any")
    sector_returns = sectors.pct_change().dropna(how="any")

    realized = pd.DataFrame(
        {
            f"realized_{window}": rolling_average_pairwise_correlation(sector_returns, window)
            for window in (REALIZED_WINDOW_1M, REALIZED_WINDOW_3M)
        }
    )

    return CrpData(
        implied=implied.reindex(traded.index).ffill(limit=CBOE_FFILL_LIMIT_DAYS),
        realized=realized.reindex(traded.index).ffill(limit=CBOE_FFILL_LIMIT_DAYS),
        vix=vix.reindex(traded.index).ffill(limit=CBOE_FFILL_LIMIT_DAYS).rename(VIX),
        traded_close=traded,
    )


StateFn = Callable[[CrpData, int], pd.Series]


def state_crp(data: CrpData, z_window: int, *, implied_key: str, realized_window: int) -> pd.Series:
    """z-score of implied minus realized, tenor-matched."""
    realized_key = f"realized_{realized_window}"
    if implied_key not in data.implied.columns or realized_key not in data.realized.columns:
        return pd.Series(np.nan, index=data.traded_close.index, dtype=float)
    raw = correlation_risk_premium(data.implied[implied_key], data.realized[realized_key])
    return trailing_zscore(raw.reindex(data.traded_close.index), z_window)


def state_implied_level(data: CrpData, z_window: int, *, implied_key: str) -> pd.Series:
    if implied_key not in data.implied.columns:
        return pd.Series(np.nan, index=data.traded_close.index, dtype=float)
    return trailing_zscore(data.implied[implied_key], z_window)


def state_realized_level(data: CrpData, z_window: int, *, realized_window: int) -> pd.Series:
    key = f"realized_{realized_window}"
    if key not in data.realized.columns:
        return pd.Series(np.nan, index=data.traded_close.index, dtype=float)
    return trailing_zscore(data.realized[key], z_window)


def state_vix_level(data: CrpData, z_window: int) -> pd.Series:
    """THE control: byte-for-byte the same construction as the already-rejected
    vol_regime_timing family's `vix_level` state variable — z of log(^VIX) over
    the same 252-day window, via the same imported trailing_zscore."""
    series = data.vix.where(data.vix > 0)
    return trailing_zscore(np.log(series), z_window)


VIX_CONTROL_KEY = "vix_level"

# (key, state fn, citation, hypothesis, is the CRP hypothesis itself)
_STATE_VARIABLES: tuple[tuple[str, StateFn, str, str, bool], ...] = (
    (
        "crp_1m",
        lambda d, w: state_crp(d, w, implied_key=COR1M, realized_window=REALIZED_WINDOW_1M),
        CORRELATION_RISK_CITATION,
        (
            "1-month implied correlation rich vs 21d realized -> correlation risk being paid "
            "for -> elevated risk aversion -> higher subsequent equity returns"
        ),
        True,
    ),
    (
        "crp_3m",
        lambda d, w: state_crp(d, w, implied_key=COR3M, realized_window=REALIZED_WINDOW_3M),
        CORRELATION_RISK_CITATION,
        "3-month implied correlation rich vs 63d realized -> the same premium at a longer tenor",
        True,
    ),
    (
        "implied_1m",
        lambda d, w: state_implied_level(d, w, implied_key=COR1M),
        IMPLIED_CORRELATION_CITATION,
        (
            "CONTROL: implied correlation LEVEL alone — if this matches crp_1m, subtracting "
            "realized correlation adds nothing and the 'premium' framing is decoration"
        ),
        False,
    ),
    (
        "realized_21d",
        lambda d, w: state_realized_level(d, w, realized_window=REALIZED_WINDOW_1M),
        REALIZED_CORRELATION_CITATION,
        (
            "CONTROL: realized correlation alone — if this matches crp_1m, the CBOE implied "
            "data is contributing nothing"
        ),
        False,
    ),
    (
        VIX_CONTROL_KEY,
        state_vix_level,
        VIX_CONTROL_CITATION,
        (
            "CONTROL: the ALREADY-REJECTED vol_regime_timing family's own vix_level state "
            "variable, on this family's target — if this matches the CRP specs, this family "
            "IS that family"
        ),
        False,
    ),
)


# --- specs -----------------------------------------------------------------


@dataclass(frozen=True)
class CrpSpec:
    spec_id: str
    state_key: str
    citation: str
    hypothesis: str
    state_fn: StateFn
    holding_days: int
    is_crp_hypothesis: bool = False
    direction: float = CRP_DIRECTION
    z_window: int = CRP_Z_WINDOW
    position_z_scale: float = CRP_POSITION_Z_SCALE


@dataclass
class CrpConfig:
    cost_bps: float = CRP_COST_BPS
    financing_bps_per_year: float = CRP_FINANCING_BPS_PER_YEAR
    formation_start: date = CRP_FORMATION_START


def default_crp_config() -> CrpConfig:
    """This family's cost configuration, as a FUNCTION rather than a module
    singleton so callers cannot mutate shared state — the same reason
    vol_regime_timing.default_vol_regime_config() is one."""
    return CrpConfig()


def _build_crp_family() -> list[CrpSpec]:
    """The exact product _STATE_VARIABLES x CRP_HOLDING_DAYS. The literal
    length of this list is the n_trials denominator screen_crp_timing uses —
    every definition counts, whether or not it survives the data floors,
    because shrinking the denominator to "specs that worked" would be
    gameable by declaring specs expected to fail."""
    specs = [
        CrpSpec(
            spec_id=f"crp_{key}_h{holding}",
            state_key=key,
            citation=citation,
            hypothesis=hypothesis,
            state_fn=state_fn,
            holding_days=holding,
            is_crp_hypothesis=is_hypothesis,
        )
        for key, state_fn, citation, hypothesis, is_hypothesis in _STATE_VARIABLES
        for holding in CRP_HOLDING_DAYS
    ]

    expected = len(_STATE_VARIABLES) * len(CRP_HOLDING_DAYS)
    assert len(specs) == expected == CRP_N_TRIALS, (
        f"CRP family built {len(specs)} definitions; the grid ({len(_STATE_VARIABLES)} state "
        f"variables x {len(CRP_HOLDING_DAYS)} holding periods) implies {expected}; the "
        f"pre-declared CRP_N_TRIALS is {CRP_N_TRIALS}. All three must agree — a drift here "
        "silently changes the DSR's multiple-comparisons denominator for every future run."
    )
    assert len({s.spec_id for s in specs}) == len(specs), "spec_ids must be unique"
    assert all(s.direction == CRP_DIRECTION for s in specs), (
        "every spec trades the single pre-declared direction — a per-spec sign would double the "
        "real search to 30 while still reporting n_trials=15"
    )
    assert all(s.z_window == CRP_Z_WINDOW for s in specs), (
        "the z-window is fixed at one pre-declared value; searching it would multiply the family "
        "size and the DSR denominator"
    )
    assert sum(1 for s in specs if s.state_key == VIX_CONTROL_KEY) == len(CRP_HOLDING_DAYS), (
        "the vix_level control must exist at EVERY holding period — it is the like-for-like "
        "comparison against the already-rejected vol-regime family and a missing horizon would "
        "leave a CRP spec with no counterpart to be checked against"
    )
    return specs


CRP_FAMILY: list[CrpSpec] = _build_crp_family()


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
class CrpBacktestResult:
    spec_id: str
    status: str
    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    positions: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    state: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    benchmark_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    formations: list[FormationRecord] = field(default_factory=list)
    total_cost: float = 0.0
    total_financing_cost: float = 0.0
    n_skipped_formations: int = 0
    n_interior_skips: int = 0


def run_crp_backtest(data: CrpData, spec: CrpSpec, config: CrpConfig) -> CrpBacktestResult:
    """One spec's non-overlapping walk-forward replay.

    THE NON-OVERLAP CONTRACT: formations sit at trading-day positions p0,
    p0+H, p0+2H, ... for H = spec.holding_days. The position set at formation p
    is held over days p+1..p+H inclusive, and the next formation is at exactly
    p+H. Every realized day therefore belongs to exactly one hold, and
    n_formations is a true count of independent bets.

    Formation is at the CLOSE: the state z uses data up to and including day p,
    and the position is assumed established at day p's close, so the first
    return it earns is day p+1's. There is no path by which a return from day
    p+1 onward can influence the position that earned it.

    A formation whose state is NaN is SKIPPED: the book goes flat and that hold
    contributes NO daily returns, rather than a run of forced zeros. Zeros
    would not be neutral — they would shrink both the mean and the std of the
    return series and quietly report the Sharpe of "hold cash, then trade" as
    if it were the Sharpe of the signal. Leading skips are the ordinary
    warmup case; an INTERIOR skip means a feed died mid-sample, so those are
    counted separately and logged."""
    state = spec.state_fn(data, spec.z_window)
    benchmark = data.traded_close.pct_change().rename(TRADED_TICKER)

    index = data.traded_close.index
    start_positions = np.flatnonzero(index.date >= config.formation_start)
    if len(start_positions) == 0:
        return CrpBacktestResult(spec_id=spec.spec_id, status="no_history_after_start")
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

    financing_daily_rate = config.financing_bps_per_year / 1e4 / FINANCING_DAYS_PER_YEAR

    p = first
    while p < n - 1:
        formation_date = index[p]
        raw_state = state.iloc[p] if p < len(state) else np.nan
        z = float(raw_state) if pd.notna(raw_state) else None

        if z is None:
            # Closing an existing position IS a real trade and is charged;
            # going flat-to-flat is not.
            turnover = abs(0.0 - previous_position)
            cost = config.cost_bps / 1e4 * turnover
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
        position = float(np.clip(spec.direction * z / spec.position_z_scale, -1.0, 1.0))
        # One unit of gross notional per unit of position — SPY outright,
        # unlike vol_regime_timing's two-legged spread where a unit position
        # trades 2.0 gross.
        turnover = abs(position - previous_position)
        cost = config.cost_bps / 1e4 * turnover
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
            gross = position * float(benchmark.iloc[j])
            if not np.isfinite(gross):
                gross = 0.0
            elapsed_days = (index[j] - index[j - 1]).days
            financing = financing_daily_rate * abs(position) * max(elapsed_days, 0)
            total_financing += financing
            # The reformation charge lands on the hold's FIRST realized day
            # rather than the formation day, whose return already belongs to
            # the previous hold. This shifts WHEN the cost appears by one day,
            # not WHETHER it is paid.
            day_cost = cost if j == p + 1 else 0.0
            returns[index[j]] = gross - day_cost - financing
            positions[index[j]] = position

        previous_position = position
        p += holding

    if interior_skips:
        logger.warning(
            "CRP spec %s: %d INTERIOR skipped formation(s) — a data feed went unavailable "
            "mid-sample rather than merely warming up. Its return series has gaps.",
            spec.spec_id,
            interior_skips,
        )

    if not returns:
        return CrpBacktestResult(
            spec_id=spec.spec_id,
            status="no_realized_returns",
            formations=formations,
            n_skipped_formations=sum(1 for f in formations if f.skipped_reason is not None),
            n_interior_skips=interior_skips,
        )

    daily = pd.Series(returns).sort_index()
    return CrpBacktestResult(
        spec_id=spec.spec_id,
        status="ok",
        daily_returns=daily,
        positions=pd.Series(positions).sort_index(),
        state=state.reindex(daily.index),
        benchmark_returns=benchmark.reindex(daily.index),
        formations=formations,
        total_cost=total_cost,
        total_financing_cost=total_financing,
        n_skipped_formations=sum(1 for f in formations if f.skipped_reason is not None),
        n_interior_skips=interior_skips,
    )


# --- confound + overlap diagnostics ----------------------------------------


@dataclass(frozen=True)
class ConfoundDiagnostic:
    """Everything needed to decide whether a positive Sharpe here is real or a
    disguised static long-SPY position. Computed for EVERY spec, always."""

    spec_id: str
    mean_position: float
    mean_abs_position: float
    fraction_long: float
    # The decisive one — see the module docstring's confound section.
    spy_beta: float
    spy_alpha_annualized: float
    # Sharpe of the BETA-HEDGED stream (y - beta*x), NOT of the OLS residual
    # (y - alpha - beta*x). The distinction is not pedantic and this project
    # has already been bitten by it: an OLS residual that includes an intercept
    # has mean exactly zero by construction, so its Sharpe is ~0 for every
    # strategy ever measured, and computing it that way would report every
    # single spec as a disguised static tilt with total confidence.
    residual_sharpe: float
    buy_and_hold_sharpe: float
    subperiod_sharpes: tuple[float, ...]
    bootstrap_p_value: float | None
    n_formations: int


@dataclass(frozen=True)
class OverlapDiagnostic:
    """THE check this module exists to survive: is this spec a relabelling of
    the already-rejected vol_regime_timing family?

    All three correlations are against that family's own `vix_level` state
    variable. `is_suspect` is True when EITHER the position-setting signal
    levels OR the realized return streams exceed CRP_VIX_OVERLAP_THRESHOLD."""

    spec_id: str
    signal_level_corr_vs_vix: float | None
    signal_change_corr_vs_vix: float | None
    return_corr_vs_vix_spec: float | None
    threshold: float
    is_suspect: bool
    reason: str


def _corr(a: pd.Series, b: pd.Series) -> float | None:
    joined = pd.concat([a.rename("a"), b.rename("b")], axis=1, sort=True).dropna()
    if len(joined) < MIN_REPLAY_TRADING_DAYS:
        return None
    if joined["a"].std(ddof=1) == 0 or joined["b"].std(ddof=1) == 0:
        return None
    value = float(joined["a"].corr(joined["b"]))
    return value if np.isfinite(value) else None


def compute_overlap_diagnostics(
    spec: CrpSpec,
    replay: CrpBacktestResult,
    vix_state: pd.Series,
    vix_spec_returns: pd.Series | None,
) -> OverlapDiagnostic:
    """Signal-level, signal-change and RETURN correlation against the rejected
    family's vix_level signal at the same horizon.

    The vix_level specs are of course perfectly correlated with themselves;
    they are still measured rather than special-cased, because a 1.000 printed
    next to a CRP spec's number is the clearest possible statement of what the
    comparison is."""
    level = _corr(replay.state, vix_state)
    change = _corr(replay.state.diff(), vix_state.diff())
    ret = (
        _corr(replay.daily_returns, vix_spec_returns)
        if vix_spec_returns is not None and len(vix_spec_returns)
        else None
    )

    breached = [
        label
        for label, value in (("signal levels", level), ("strategy returns", ret))
        if value is not None and abs(value) > CRP_VIX_OVERLAP_THRESHOLD
    ]
    if breached:
        reason = (
            f"OVERLAP SUSPECT: |corr| exceeds {CRP_VIX_OVERLAP_THRESHOLD} on "
            f"{' and '.join(breached)} against the already-rejected vol_regime_timing "
            "vix_level signal — any apparent edge may be that rejected family relabelled."
        )
    else:
        reason = (
            f"No overlap breach: |corr| stays at or below {CRP_VIX_OVERLAP_THRESHOLD} on both "
            "the position-setting signal levels and the realized return stream."
        )
    return OverlapDiagnostic(
        spec_id=spec.spec_id,
        signal_level_corr_vs_vix=level,
        signal_change_corr_vs_vix=change,
        return_corr_vs_vix_spec=ret,
        threshold=CRP_VIX_OVERLAP_THRESHOLD,
        is_suspect=bool(breached),
        reason=reason,
    )


def _subperiod_sharpes(returns: pd.Series, n_periods: int = 3) -> tuple[float, ...]:
    """Sharpe in each of n_periods equal, contiguous slices of the spec's own
    realized sample. A risk-aversion signal can earn its entire lifetime Sharpe
    in one crisis autumn; this is the cheapest way to see that."""
    clean = returns.dropna()
    if len(clean) < n_periods * 2:
        return ()
    bounds = np.linspace(0, len(clean), n_periods + 1).astype(int)
    out = []
    for i in range(n_periods):
        chunk = clean.iloc[bounds[i] : bounds[i + 1]]
        out.append(sharpe_ratio(chunk) if len(chunk) >= 2 else 0.0)
    return tuple(out)


def compute_confound_diagnostics(spec: CrpSpec, replay: CrpBacktestResult) -> ConfoundDiagnostic:
    """The in-module adversarial pass.

    residual_sharpe is the number that decides whether a spec is real. It is
    the Sharpe of the strategy's returns AFTER removing its OLS exposure to
    buy-and-hold SPY — i.e. after taking away everything a constant, signal-free
    long position in the same instrument would have earned. This is the
    identical test that reduced this project's commodities momentum family
    (raw DSR 0.767) to a residual Sharpe of ~0.000 once regressed on a
    precious-metals factor.

    compute_beta is REUSED from risk.beta rather than re-derived here."""
    daily = replay.daily_returns
    benchmark = replay.benchmark_returns

    aligned = pd.concat([daily.rename("y"), benchmark.rename("x")], axis=1, sort=True).dropna()
    if len(aligned) >= 3:
        beta = compute_beta(aligned["y"], aligned["x"])
        if not np.isfinite(beta):
            beta = 0.0
        hedged = aligned["y"] - beta * aligned["x"]
        # NUMERICAL GUARD, and it is load-bearing rather than defensive.
        # A Sharpe ratio is SCALE-INVARIANT, so a hedged stream that is
        # mathematically zero but numerically 1e-18 still reports whatever
        # Sharpe its floating-point dust happens to have. The worst case is
        # exactly the case this diagnostic exists to catch: a spec that is a
        # PERFECT replica of buy-and-hold SPY (position pinned at 1.0) makes
        # y and x bit-identical, yet compute_beta returns 1.0000000000000002
        # rather than 1.0, leaving hedged = -2e-16 * x — a scaled copy of the
        # BENCHMARK whose Sharpe is a large NEGATIVE number. Verified on this
        # module's own synthetic fixture: max|y-x| = 0.0 exactly, and the
        # unguarded residual Sharpe still printed -0.836. The most blatant
        # possible static tilt would therefore have been reported with a
        # confident-looking negative alpha instead of "nothing is left".
        # When the hedge explains essentially all of the variance, the honest
        # answer is 0.0 — there is no residual stream to have a Sharpe.
        y_std = float(aligned["y"].std(ddof=1))
        hedged_std = float(hedged.std(ddof=1))
        fully_explained = y_std > 0 and hedged_std <= RESIDUAL_DEGENERACY_RATIO * y_std
        residual_sharpe = 0.0 if fully_explained else sharpe_ratio(hedged)
        # The hedged stream's mean IS the regression alpha, so this and
        # residual_sharpe describe the same series.
        alpha_annualized = 0.0 if fully_explained else float(hedged.mean()) * TRADING_DAYS_PER_YEAR
        bh_sharpe = sharpe_ratio(aligned["x"])
    else:
        beta = 0.0
        residual_sharpe = 0.0
        alpha_annualized = 0.0
        bh_sharpe = 0.0

    pos = replay.positions
    active = [f for f in replay.formations if f.skipped_reason is None]

    return ConfoundDiagnostic(
        spec_id=spec.spec_id,
        mean_position=float(pos.mean()) if len(pos) else 0.0,
        mean_abs_position=float(pos.abs().mean()) if len(pos) else 0.0,
        fraction_long=float((pos > 0).mean()) if len(pos) else 0.0,
        spy_beta=float(beta),
        spy_alpha_annualized=alpha_annualized,
        residual_sharpe=residual_sharpe,
        buy_and_hold_sharpe=bh_sharpe,
        subperiod_sharpes=_subperiod_sharpes(daily),
        bootstrap_p_value=block_bootstrap_sharpe_pvalue(daily, spec.holding_days),
        n_formations=len(active),
    )


# --- point-in-time cross-check ---------------------------------------------


@dataclass
class PitCrosscheckResult:
    """Does the fixed sector-ETF proxy actually track the point-in-time S&P 500
    constituent correlation it stands in for? See the module docstring's (b)."""

    status: str
    n_dates: int = 0
    start: date | None = None
    end: date | None = None
    level_correlation: float | None = None
    change_correlation: float | None = None
    mean_sector_correlation: float | None = None
    mean_pit_correlation: float | None = None
    mean_names: float | None = None
    notes: list[str] = field(default_factory=list)


def compute_pit_realized_correlation_crosscheck(
    sector_returns: pd.DataFrame,
    constituent_close: pd.DataFrame,
    window: int = REALIZED_WINDOW_1M,
    sample_every: int = 5,
) -> PitCrosscheckResult:
    """Realized average pairwise correlation over the POINT-IN-TIME S&P 500,
    compared against the sector-ETF proxy this family actually trades.

    Reuses sp500_membership_history.get_universe_as_of so each date's
    cross-section is the index's ACTUAL membership on that date, not today's —
    the same survivorship discipline every cross-sectional family here uses.

    `sample_every` subsamples the date axis (a 500x500 correlation matrix per
    day over 2,800 days is far more computation than a validity check needs).
    This is a DIAGNOSTIC, never a traded signal, so subsampling costs nothing
    that matters.

    Names whose price history is missing on a given date simply do not enter
    that date's cross-section, and mean_names reports how many did — which is
    itself the disclosure of this project's known delisted-coverage gap, since
    a constituent that delisted is exactly a name yfinance will not return."""
    notes: list[str] = []
    if constituent_close.empty or sector_returns.empty:
        return PitCrosscheckResult(status="no_data", notes=["no constituent or sector data"])

    constituent_returns = constituent_close.pct_change()
    sector_proxy = rolling_average_pairwise_correlation(sector_returns, window)

    dates = constituent_returns.index
    usable = [d for d in dates if d.date() >= MEMBERSHIP_DATA_START]
    if len(usable) <= window:
        return PitCrosscheckResult(
            status="insufficient_history",
            notes=[f"only {len(usable)} dates at or after {MEMBERSHIP_DATA_START.isoformat()}"],
        )

    pit_values: dict[pd.Timestamp, float] = {}
    name_counts: list[int] = []
    positions = {d: i for i, d in enumerate(dates)}
    for target in usable[window::sample_every]:
        try:
            members = get_universe_as_of(target.date())
        except PointInTimeUniverseError:
            continue
        present = [m for m in members if m in constituent_returns.columns]
        if len(present) < MIN_NAMES_FOR_REALIZED_CORRELATION:
            continue
        end = positions[target]
        chunk = constituent_returns.iloc[end - window + 1 : end + 1][present]
        chunk = chunk.dropna(axis=1, how="any")
        if chunk.shape[1] < MIN_NAMES_FOR_REALIZED_CORRELATION:
            continue
        name_counts.append(chunk.shape[1])
        pit_values[target] = average_pairwise_correlation(correlation_matrix(chunk)) * 100.0

    if len(pit_values) < 2:
        return PitCrosscheckResult(
            status="insufficient_constituents",
            notes=["fewer than 2 dates produced a usable point-in-time cross-section"],
        )

    pit = pd.Series(pit_values).sort_index()
    joined = pd.concat(
        [pit.rename("pit"), sector_proxy.rename("sector")], axis=1, sort=True
    ).dropna()
    if len(joined) < 2:
        return PitCrosscheckResult(status="no_overlap", notes=["no overlapping dates"])

    if name_counts:
        notes.append(
            f"point-in-time cross-sections averaged {np.mean(name_counts):.0f} names with usable "
            f"price history (min {min(name_counts)}, max {max(name_counts)}); names absent from "
            "the price source — delisted constituents above all — are silently excluded, which is "
            "this project's known open delisted-coverage gap showing up here."
        )

    return PitCrosscheckResult(
        status="ok",
        n_dates=len(joined),
        start=joined.index[0].date(),
        end=joined.index[-1].date(),
        level_correlation=float(joined["pit"].corr(joined["sector"])),
        change_correlation=float(joined["pit"].diff().corr(joined["sector"].diff())),
        mean_sector_correlation=float(joined["sector"].mean()),
        mean_pit_correlation=float(joined["pit"].mean()),
        mean_names=float(np.mean(name_counts)) if name_counts else None,
        notes=notes,
    )


# --- screening -------------------------------------------------------------


@dataclass
class CrpScreeningResult:
    spec_id: str
    state_key: str
    holding_days: int
    citation: str
    hypothesis: str
    is_crp_hypothesis: bool
    n_formations: int
    n_skipped_formations: int
    n_trading_days: int
    first_formation: date | None
    last_formation: date | None
    sharpe_annualized: float
    # Sum of the NET daily returns (costs and financing already subtracted). A
    # simple sum rather than a compounded product, so that adding back
    # total_cost_drag and total_financing_drag — themselves sums of
    # per-formation charges in the same units — reconstructs the pre-cost
    # return exactly, which is what makes the breakeven-cost multiple in
    # build_crp_disclosure arithmetic rather than an approximation.
    net_cumulative_return: float
    total_cost_drag: float
    total_financing_drag: float
    deflated_sharpe: DeflatedSharpeResult
    confound: ConfoundDiagnostic
    overlap: OverlapDiagnostic


def screen_crp_timing(
    data: CrpData, specs: list[CrpSpec], config: CrpConfig
) -> list[CrpScreeningResult]:
    """One Sharpe per spec, DSR-corrected for the family's pre-declared size.

    Trial counting follows vol_regime_timing.screen_vol_regime_timing and
    cross_sectional.screen_cross_sectional_universe exactly, for the same
    documented reason: each spec IS already a single portfolio, so no
    uncorrected "which ticker" search dimension exists, leaving "which
    definition" as the one search dimension. n_trials is therefore fixed at
    len(specs) — the family's literal pre-declared size — and never shrunk to
    however many specs survived the data floors, which would be gameable.

    sigma_sr is the ddof=1 standard deviation of every sibling spec's Sharpe
    from this same pass, the sibling convention both modules above use.

    The caveat no caller may drop: 15 counts THIS family only. The literature
    scan that nominated the correlation risk premium, and the other families
    screened alongside it, are NOT in the denominator, so every DSR here is an
    upper bound on the honest one."""
    n_trials = len(specs)

    replays: dict[str, CrpBacktestResult] = {}
    for spec in specs:
        replay = run_crp_backtest(data, spec, config)
        if replay.status != "ok":
            logger.info("CRP spec %s not replayed: %s", spec.spec_id, replay.status)
            continue
        if len(replay.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            logger.info(
                "CRP spec %s dropped: only %d realized days (floor %d)",
                spec.spec_id,
                len(replay.daily_returns),
                MIN_REPLAY_TRADING_DAYS,
            )
            continue
        replays[spec.spec_id] = replay

    sharpes = {sid: sharpe_ratio(r.daily_returns) for sid, r in replays.items()}
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    # The rejected family's signal, and its per-horizon return streams, for the
    # overlap check. Built once here rather than per spec.
    vix_state = state_vix_level(data, CRP_Z_WINDOW)
    vix_returns_by_horizon: dict[int, pd.Series] = {
        spec.holding_days: replays[spec.spec_id].daily_returns
        for spec in specs
        if spec.state_key == VIX_CONTROL_KEY and spec.spec_id in replays
    }

    spec_by_id = {s.spec_id: s for s in specs}
    results: list[CrpScreeningResult] = []
    for spec_id, replay in replays.items():
        spec = spec_by_id[spec_id]
        active = [f for f in replay.formations if f.skipped_reason is None]
        results.append(
            CrpScreeningResult(
                spec_id=spec_id,
                state_key=spec.state_key,
                holding_days=spec.holding_days,
                citation=spec.citation,
                hypothesis=spec.hypothesis,
                is_crp_hypothesis=spec.is_crp_hypothesis,
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
                confound=compute_confound_diagnostics(spec, replay),
                overlap=compute_overlap_diagnostics(
                    spec, replay, vix_state, vix_returns_by_horizon.get(spec.holding_days)
                ),
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results


# --- disclosure ------------------------------------------------------------


@dataclass
class CrpScreeningSummary:
    results: list[CrpScreeningResult] = field(default_factory=list)
    missing_instruments: list[str] = field(default_factory=list)
    cboe_starts: dict[str, date] = field(default_factory=dict)
    cboe_rows: dict[str, int] = field(default_factory=dict)
    pit_crosscheck: PitCrosscheckResult | None = None
    formation_calendar_start: date | None = None
    formation_calendar_end: date | None = None
    disclosure: list[str] = field(default_factory=list)


def build_crp_disclosure(
    results: list[CrpScreeningResult],
    config: CrpConfig,
    pit: PitCrosscheckResult | None = None,
) -> list[str]:
    """Plain-language caveats that must travel with any number from this
    family, including the breakeven-cost arithmetic that says how wrong the
    cost assumption would have to be to matter."""
    lines = [
        (
            f"n_trials = {CRP_N_TRIALS} ({len(_STATE_VARIABLES)} state variables x "
            f"{len(CRP_HOLDING_DAYS)} holding periods x 1 target), fixed before any return was "
            "computed and never shrunk to the specs that survived the data floors."
        ),
        (
            "n_trials covers THIS family only. The literature scan that nominated the correlation "
            "risk premium, and the other asset-class families screened alongside it, are NOT in "
            "the denominator, so every DSR below is an UPPER BOUND on the honest one."
        ),
        (
            f"Direction was pre-declared uniformly at {CRP_DIRECTION:+.0f} ('a high correlation "
            "risk premium = high risk aversion = higher subsequent equity returns') and never "
            "fitted per spec; negative Sharpes are reported as they came out, not flipped."
        ),
        (
            "Realized correlation is computed over a FIXED set of nine SPDR sector ETFs, which "
            "are already-diversified baskets and therefore structurally MORE correlated than the "
            "individual stocks CBOE prices. The LEVEL of CRP here is consequently not the "
            "Driessen-Maenhout-Vilkov premium and must not be read as one; only its time "
            "variation, via a trailing z-score, is used."
        ),
        (
            "Formations are non-overlapping: cadence equals holding_days, so n_formations is a "
            "true count of independent bets. Sharpe/PSR/DSR still use the DAILY series (matching "
            "every other family here), so a circular block bootstrap with block length = "
            "holding_days is reported alongside; where they disagree, believe the bootstrap."
        ),
        (
            f"Costs: {config.cost_bps:.1f}bp one-way per unit of gross notional traded (~25x SPY's "
            f"quoted half-spread), plus {config.financing_bps_per_year:.0f}bp/yr charged on "
            "|position| for BOTH signs and accrued on calendar days, because an outright SPY "
            "position is not self-financing. That financing rate is a disclosed blended "
            "assumption, not a sourced quote, and it is on the LOW side for 2006-2026 — it "
            "FLATTERS long-biased specs."
        ),
        (
            "Positions are re-set daily inside a hold at zero cost, and formation is assumed "
            "executable at the exact closing print — both mildly optimistic, both disclosed."
        ),
        (
            "SPY and the nine sector ETFs were selected today from instruments that still exist "
            "and are still liquid; that hindsight-selection channel is small for instruments this "
            "large but is not zero."
        ),
    ]

    if pit is not None:
        if pit.status == "ok" and pit.level_correlation is not None:
            lines.append(
                f"Point-in-time cross-check ({pit.start} to {pit.end}, {pit.n_dates} sampled "
                f"dates): the sector-ETF realized correlation tracks the true point-in-time S&P "
                f"500 constituent correlation at {pit.level_correlation:+.3f} in levels and "
                f"{pit.change_correlation:+.3f} in changes, with mean levels "
                f"{pit.mean_sector_correlation:.1f}% (sector) vs {pit.mean_pit_correlation:.1f}% "
                "(constituents) — the structural level gap the disclosure above describes."
            )
        else:
            lines.append(
                f"Point-in-time cross-check did not run ({pit.status}); the sector-ETF proxy's "
                "validity is therefore ASSERTED here, not measured."
            )
        lines.extend(f"  {note}" for note in pit.notes)

    if not results:
        lines.append("No spec produced a replayable return series — nothing to interpret.")
        return lines

    best = results[0]
    lines.append(
        f"Best raw Sharpe: {best.spec_id} at {best.sharpe_annualized:+.3f} over "
        f"{best.n_trading_days} days / {best.n_formations} independent formations."
    )

    # The decision rule from PREDECLARATION.txt, encoded here rather than
    # left only in prose: best-raw-Sharpe and best-DSR need not be the same
    # spec (a smaller, cleaner sample can beat a noisier bigger one once
    # deflated), so this is a genuinely separate figure, not a restatement.
    dsr_results = [r for r in results if r.deflated_sharpe.dsr is not None]
    if dsr_results:
        best_dsr_result = max(dsr_results, key=lambda r: r.deflated_sharpe.dsr)
        dsr = best_dsr_result.deflated_sharpe.dsr
        if dsr >= 0.90:
            verdict = "clears this project's ~0.90-0.95 significance standard"
        elif dsr >= 0.50:
            verdict = "possibly interesting, but well short of this project's ~0.90-0.95 standard"
        else:
            verdict = "an HONEST NEGATIVE by this project's own decision rule"
        lines.append(
            f"Best DSR: {best_dsr_result.spec_id} at {dsr:.3f} (n_trials={CRP_N_TRIALS}) — {verdict}."
        )
    else:
        lines.append(f"No spec had enough sibling trials for a DSR (need >= {MIN_TRIALS_FOR_DSR}).")

    charges = best.total_cost_drag + best.total_financing_drag
    lines.append(
        f"Cost sensitivity for {best.spec_id}: turnover drag {best.total_cost_drag:.4f} plus "
        f"financing drag {best.total_financing_drag:.4f} in cumulative return units, both already "
        f"subtracted from its reported net cumulative return of {best.net_cumulative_return:+.4f}."
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
                f"{config.financing_bps_per_year:.0f}bp-per-year to erase its net return."
            )

    # SIGNED, deliberately not abs(). The question a static-tilt check asks is
    # "did the positive Sharpe SURVIVE hedging out the static exposure", and
    # only an upside comparison answers it. Using abs() would let the
    # degenerate case through: when the position is near-constant the hedge is
    # near-perfect, all that is left is the near-deterministic cost drag, and
    # its Sharpe is a large NEGATIVE number whose absolute value sails past any
    # threshold — the most blatant possible static tilt would be the one the
    # filter cleared.
    tilts = [
        r
        for r in results
        if r.sharpe_annualized > 0 and r.confound.residual_sharpe < 0.5 * r.sharpe_annualized
    ]
    if tilts:
        lines.append(
            f"{len(tilts)} spec(s) with a positive raw Sharpe lose more than half of it once "
            "their static exposure to buy-and-hold SPY is regressed out — those are disguised "
            "long-market tilts, not timing signals."
        )

    suspects = [r for r in results if r.overlap.is_suspect]
    if suspects:
        lines.append(
            f"OVERLAP WARNING: {len(suspects)} of {len(results)} spec(s) exceed the pre-declared "
            f"|corr| > {CRP_VIX_OVERLAP_THRESHOLD} overlap threshold against the ALREADY-REJECTED "
            "vol_regime_timing family's vix_level signal. Any apparent edge in those specs must "
            "be treated as a probable relabelling of a family this project already rejected."
        )
    else:
        lines.append(
            f"Overlap check: no spec exceeds |corr| > {CRP_VIX_OVERLAP_THRESHOLD} against the "
            "already-rejected vol_regime_timing vix_level signal, on either the position-setting "
            "signal levels or the realized return streams."
        )
    # Signal-CHANGE correlation was deliberately left out of is_suspect
    # (PREDECLARATION.txt scopes the threshold to levels-or-returns only) --
    # but an adversarial review of this family found that omitting it from
    # this disclosure, even though the code computes and stores it on every
    # result, reads as a cleaner "not overlapping" claim than the numbers
    # support. Disclosing it here does not change is_suspect or any DSR
    # above; it exists so a reader never has to take "no overlap breach" as
    # the complete picture.
    changes = [
        (r.spec_id, r.overlap.signal_change_corr_vs_vix)
        for r in results
        if r.is_crp_hypothesis and r.overlap.signal_change_corr_vs_vix is not None
    ]
    if changes:
        worst_id, worst_change = max(changes, key=lambda pair: abs(pair[1]))
        lines.append(
            f"Signal-CHANGE correlation vs the rejected family's vix_level (not part of the "
            f"pre-declared suspect criterion, disclosed for completeness): up to "
            f"{worst_change:+.3f} ({worst_id}) among the CRP-hypothesis specs. The hypothesis "
            "specs share a non-trivial fraction of their day-to-day dynamics with the "
            "already-rejected family even though their levels and returns clear the threshold."
        )
    return lines


# --- production entry point ------------------------------------------------


def run_crp_screening(
    start: date = CRP_FORMATION_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    config: CrpConfig | None = None,
    specs: list[CrpSpec] | None = None,
    client: httpx.Client | None = None,
    include_pit_crosscheck: bool = True,
) -> CrpScreeningSummary:
    """THE research entry point for the CRP family, scoped to exactly
    CRP_FAMILY's 15 definitions and their own n_trials.

    Deliberately NOT wired into any live runner or forward-validation registry:
    this is a research screen, and promoting anything from it to production
    tracking is a separate explicit decision.

    `start` is the first FORMATION date; price history is padded before it by
    CRP_HISTORY_PADDING_CALENDAR_DAYS so both the 63-day realized-correlation
    window and the 252-day z-window on top of it are warm. Formations never
    occur in the padding."""
    # date.today() is the LOCAL date. Immaterial here — it is only the
    # exclusive end bound of a price fetch.
    end = end if end is not None else date.today()  # noqa: DTZ011
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else default_crp_config()
    config.formation_start = start
    specs = specs if specs is not None else CRP_FAMILY

    padded_start = start - timedelta(days=CRP_HISTORY_PADDING_CALENDAR_DAYS)

    implied = fetch_cboe_implied_correlation(client=client)
    cboe_starts = {
        str(col): implied[col].dropna().index[0].date()
        for col in implied.columns
        if not implied[col].dropna().empty
    }
    cboe_rows = {str(col): int(implied[col].notna().sum()) for col in implied.columns}
    for symbol, observed in cboe_starts.items():
        expected = CBOE_VERIFIED_START.get(symbol)
        if expected is not None and observed > expected + timedelta(days=7):
            logger.warning(
                "CRP screening: %s history starts %s, later than the verified inception %s — "
                "CBOE may have truncated this index.",
                symbol,
                observed,
                expected,
            )

    wanted = [*SECTOR_ETF_UNIVERSE, TRADED_TICKER, VIX]
    closes, missing = provider.get_price_history(wanted, padded_start, end)
    if closes.empty or TRADED_TICKER not in closes.columns:
        return CrpScreeningSummary(missing_instruments=missing or wanted, cboe_starts=cboe_starts)
    if missing:
        logger.error(
            "CRP screening: %d of %d instruments resolved NO price data (%s).",
            len(missing),
            len(wanted),
            ", ".join(missing),
        )

    sector_columns = [t for t in SECTOR_ETF_UNIVERSE if t in closes.columns]
    if len(sector_columns) < MIN_NAMES_FOR_REALIZED_CORRELATION:
        return CrpScreeningSummary(missing_instruments=missing, cboe_starts=cboe_starts)

    vix_series = (
        closes[VIX]
        if VIX in closes.columns
        else pd.Series(np.nan, index=closes.index, dtype=float)
    )
    data = align_crp_data(implied, closes[sector_columns], vix_series, closes[TRADED_TICKER])
    results = screen_crp_timing(data, specs, config)

    pit: PitCrosscheckResult | None = None
    if include_pit_crosscheck:
        pit = _run_pit_crosscheck(provider, closes[sector_columns], padded_start, end)

    firsts = [r.first_formation for r in results if r.first_formation is not None]
    lasts = [r.last_formation for r in results if r.last_formation is not None]

    return CrpScreeningSummary(
        results=results,
        missing_instruments=missing,
        cboe_starts=cboe_starts,
        cboe_rows=cboe_rows,
        pit_crosscheck=pit,
        formation_calendar_start=min(firsts) if firsts else None,
        formation_calendar_end=max(lasts) if lasts else None,
        disclosure=build_crp_disclosure(results, config, pit),
    )


def _run_pit_crosscheck(
    provider: YFinanceProvider,
    sector_close: pd.DataFrame,
    padded_start: date,
    end: date,
) -> PitCrosscheckResult:
    """Fetches the survivorship-free S&P 500 candidate pool and runs the
    proxy-validity cross-check. Isolated in its own function (and wrapped) so a
    failure in a DIAGNOSTIC can never take down the screen it is diagnosing."""
    pit_start = max(padded_start, MEMBERSHIP_DATA_START)
    try:
        universe = get_universe_over(pit_start, end)
    except PointInTimeUniverseError as exc:
        return PitCrosscheckResult(status="no_membership_coverage", notes=[str(exc)])
    if not universe:
        return PitCrosscheckResult(status="empty_universe")

    try:
        constituents, _ = provider.get_price_history(universe, pit_start, end)
    except Exception as exc:  # noqa: BLE001 - a diagnostic must never break the screen
        logger.warning("CRP point-in-time cross-check could not fetch constituents: %s", exc)
        return PitCrosscheckResult(status="constituent_fetch_failed", notes=[str(exc)])

    sector_returns = sector_close.dropna(axis=0, how="any").pct_change().dropna(how="any")
    return compute_pit_realized_correlation_crosscheck(sector_returns, constituents)


__all__ = [
    "CBOE_DAILY_PRICES_BASE",
    "CBOE_FFILL_LIMIT_DAYS",
    "CBOE_VERIFIED_ROWS",
    "CBOE_VERIFIED_START",
    "COR1M",
    "COR3M",
    "CRP_COST_BPS",
    "CRP_DIRECTION",
    "CRP_FAMILY",
    "CRP_FINANCING_BPS_PER_YEAR",
    "CRP_FORMATION_START",
    "CRP_HOLDING_DAYS",
    "CRP_N_TRIALS",
    "CRP_POSITION_Z_SCALE",
    "CRP_VIX_OVERLAP_THRESHOLD",
    "CRP_Z_WINDOW",
    "IMPLIED_CORRELATION_INDICES",
    "MIN_NAMES_FOR_REALIZED_CORRELATION",
    "REALIZED_WINDOW_1M",
    "REALIZED_WINDOW_3M",
    "RESIDUAL_DEGENERACY_RATIO",
    "SECTOR_ETF_UNIVERSE",
    "TRADED_TICKER",
    "VIX_CONTROL_KEY",
    "CboeDataError",
    "ConfoundDiagnostic",
    "CrpBacktestResult",
    "CrpConfig",
    "CrpData",
    "CrpScreeningResult",
    "CrpScreeningSummary",
    "CrpSpec",
    "FormationRecord",
    "OverlapDiagnostic",
    "PitCrosscheckResult",
    "align_crp_data",
    "build_crp_disclosure",
    "compute_confound_diagnostics",
    "compute_overlap_diagnostics",
    "compute_pit_realized_correlation_crosscheck",
    "correlation_risk_premium",
    "default_crp_config",
    "fetch_cboe_implied_correlation",
    "parse_cboe_history_csv",
    "rolling_average_pairwise_correlation",
    "run_crp_backtest",
    "run_crp_screening",
    "screen_crp_timing",
    "state_crp",
    "state_implied_level",
    "state_realized_level",
    "state_vix_level",
]
