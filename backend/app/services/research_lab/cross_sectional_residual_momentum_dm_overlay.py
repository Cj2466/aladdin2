"""DANIEL-MOSKOWITZ CRASH-MITIGATION OVERLAY on residual momentum — a
crash-risk overlay screened as its own pre-registered grid, not a new
cross-sectional signal.

PRE-REGISTRATION: data/research_runs/residual_momentum_dm_overlay_
PREREGISTRATION.txt, committed BEFORE this module existed. The hypothesis,
the three bases, the four overlay definitions, n_trials = 30, the
registration-eligibility rules and the pass/fail bar are all fixed there and
are NOT restated here as though they had been decided afterwards.

--------------------------------------------------------------------------------
1. WHAT THIS IS, AND WHY IT IS A SEPARATE MODULE
--------------------------------------------------------------------------------

Every other cross-sectional family in this repo defines a RANKING VARIABLE and
hands it to the harness. This one does not. It takes three ALREADY-SCREENED
residual-momentum specs, reads the daily net return series the harness produced
for them, and applies a time-varying EXPOSURE WEIGHT on top — the thing Daniel
and Moskowitz actually propose. The signal is untouched; only the size of the
book changes.

That is why it is not code inside cross_sectional_residual_momentum.py: it does
not change what that family ranks, it carries a different citation (Daniel &
Moskowitz, not Blitz/Huij/Martens), and it carries its own trial denominator.
Bolting it into the 18-spec grid would have re-deflated eighteen already-
published rows against a denominator chosen after they were computed.

--------------------------------------------------------------------------------
2. THE SOURCE, VERIFIED FROM THE PUBLISHED PAPER
--------------------------------------------------------------------------------

Daniel, Kent & Tobias J. Moskowitz, "Momentum crashes", Journal of Financial
Economics 122(2), November 2016, pp. 221-247,
doi:10.1016/j.jfineco.2015.12.002. Fetched as the published JFE PDF from the
first author's own site (kentdaniel.net/papers/published/jfe_16.pdf) and
text-extracted for this build. NOTHING BELOW IS FROM MEMORY.

THE BEAR-MARKET INDICATOR, verbatim from the Table 4 notes (p. 230), repeated
identically in the section 3.2 variable list (p. 228):

    "IB,t-1 is an ex ante bear market indicator that equals one if the
     cumulative CRSP VW index return in the past 24 months is negative and is
     zero otherwise."

Note what it is NOT: not a drawdown from a peak, not a moving-average cross,
not an excess return. Plain cumulative 24-month TOTAL return on the CRSP
value-weighted index, threshold exactly zero.

THE MARKET VARIANCE, Eq. (4), p. 230: "sigma-hat^2_m,t-1 is the variance of the
daily returns of the market over the 126 days prior to time t."

THE DYNAMIC WEIGHT, Eq. (6), p. 233:

    w*_{t-1} = ( 1 / (2*lambda) ) * mu_{t-1} / sigma^2_{t-1}

"where mu_{t-1} = E_{t-1}[R_WML,t] is the conditional expected return on the
(zero-investment) WML portfolio over the coming month, sigma^2_{t-1} is the
conditional variance of the WML portfolio return over the coming month, and
lambda is a time-invariant scalar that controls the unconditional risk and
return of the dynamic portfolio."

THE MEAN FORECAST, Fig. 7 caption, p. 236:

    mu_{t-1} = gamma-hat_{0,t-1} + gamma-hat_{int,t-1} * IB,t-1 * sigma-hat^2_m,t-1

"only now the gamma-hat_{0,t-1} and gamma-hat_{int,t-1} are the estimated
regression coefficients not over the full sample, but rather from a regression
run from the start of our sample (1927:07) up through month t-1". That is the
IMPLEMENTABLE version and it is the only one built here. The paper's in-sample
variant uses full-sample coefficients, is not implementable, and is absent from
this module entirely rather than present and labelled.

THE TWO SIMPLER SCALINGS, Table 7 notes, p. 236: "cvol is the constant
volatility strategy, in which the WML returns each month are scaled by the
realized volatility of the daily WML returns over the preceding 126 trading
days. For the variance scaled portfolio, the WML returns each month are scaled
by the realized variance of the daily WML returns over the preceding 126
trading days."

WHAT THE PAPER'S OWN TABLE 7 SAYS, read honestly before building on it
(annualized Sharpe, 1934:01-2013:03): WML 0.682, cvol 1.041, variance scaled
1.126, dyn out-of-sample 1.194, dyn in-sample 1.202. Of the +0.512 improvement
from WML to the full dynamic strategy, +0.359 — SEVENTY PERCENT — comes from
the plain volatility scaling that uses no bear indicator at all. D&M's headline
is the dynamic strategy; the bulk of their measured gain is Barroso &
Santa-Clara's volatility scaling, and this module's grid is built so that split
is measurable here too rather than assumed.

AND WHAT THE PAPER CLAIMS THE MECHANISM IS, p. 234: "much of the improved
performance of the constant volatility, and especially dynamic strategy, over
the static WML portfolio is the amelioration of big crashes." THE CLAIM IS
CRASH MITIGATION. A Sharpe improvement without a drawdown improvement has not
reproduced this paper's mechanism, whatever it did to the Sharpe — which is why
`max_drawdown_delta` is a first-class output here and not a footnote.

--------------------------------------------------------------------------------
3. THE INDICATOR IMPLEMENTATION IS VERIFIED AGAINST THE PAPER'S OWN COUNT
--------------------------------------------------------------------------------

`bear_market_indicator` is not merely written to the quoted definition, it is
checked against a number the paper prints. Footnote 6, p. 228: "Of the 1,035
months in the 1927:01-2013:03 period, IB,t-1 = 1 in 183". Running this
module's indicator on Ken French's own monthly market series (mkt_rf + rf IS
the CRSP VW index return — French's library builds it from CRSP) over exactly
that window returns 183 of 1035, 17.7%, to the month. That equality is pinned
by a unit test, because an indicator that silently drifts off the source
definition is the one bug here that would look completely healthy in the
output.

--------------------------------------------------------------------------------
4. THE POWER PROBLEM, MEASURED BEFORE THE GRID WAS DESIGNED
--------------------------------------------------------------------------------

Over this project's 2015-01..2026-08 backtest window the same indicator fires
in 8 of 138 months (5.80%) against D&M's own 17.7% base rate, and those eight
months are TWO episodes: 2020-03, and a 2022-12..2023-11 cluster. That cluster
is small-cap-driven and does not exist at all in a large-cap index — the SPY
version of the identical indicator fires in ONE month of 140.

This is recorded in the pre-registration and it is the reason the two
bear-conditioned arms (`bear`, `dyn`) are declared NON-REGISTRABLE IN ADVANCE
whatever they score. A DSR computed on 2,929 daily observations does not
describe a bet that was taken twice. The DSR machinery deflates for trial
count, sample length, skew and kurtosis; it does not deflate for the effective
independence of the underlying bets, and here that gap is the whole story.

--------------------------------------------------------------------------------
5. THE SCALE-INVARIANCE PROPERTY THAT KEEPS THIS HONEST
--------------------------------------------------------------------------------

A Sharpe ratio is invariant to a constant multiplier. So the leverage LEVEL of
every arm here — the `k` normalization, D&M's own lambda, the choice of
volatility target — cannot move any Sharpe, PSR or DSR in this module by any
amount at all. Everything a Sharpe number here reports comes from the TIME
VARIATION of the weight and from nothing else.

That is a real guarantee rather than a claim: it is asserted in
`apply_overlay`, and a unit test pins it by scaling a weight series by an
arbitrary constant and requiring the resulting Sharpe to be bit-identical.

What the level DOES change is the overlay's own turnover cost and the
percentage depth of a drawdown, so `k` is fixed by D&M's own convention (p.
233: "we scale the weights of both the constant volatility and the dynamic
strategy so as to make the full sample volatility of each return series equal
to that of the baseline WML strategy"), disclosed as a full-sample quantity,
and reported alongside a k/2 and 2k cost sensitivity. Nothing is selected on it.

--------------------------------------------------------------------------------
6. WHAT IS DELIBERATELY NOT DONE
--------------------------------------------------------------------------------

 * NO CAP OR FLOOR ON THE WEIGHT. D&M's own dynamic weight reaches 5.37 and
   goes NEGATIVE in 82 months of their sample (p. 233). Adding a cap would be
   a searched parameter the paper does not have. The realized range is
   reported instead.
 * NO SEARCH OVER THE GATE LEVEL. `bear` stands fully flat (w = 0) in bear
   states — the maximally capital-preserving reading, pre-declared, one value.
 * NO SEARCH OVER THE HOLDING PERIOD. h21 throughout: BHM's own monthly
   rebalance and the cadence D&M's monthly weighting requires.
 * NO GJR-GARCH. It belongs to D&M's in-sample variant only; the
   out-of-sample strategy replicated here uses the 126-day realized variance,
   which is what their Table 7 note specifies.
 * FINANCING IS NOT CHARGED, and that is a DISCLOSED OPTIMISM that is strictly
   worse here than for the un-overlaid base. The family config carries
   financing_bps_per_year = 0.0 (this project's standing short-borrow
   disclosure). An arm whose weight exceeds 1 is LEVERED, and levered gross
   notional is exactly where a 0 bps borrow assumption is least defensible.
   `weight_mean_abs` and `weight_max_abs` are reported for every arm so the
   size of that optimism is visible rather than implied.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.services.research_lab.cross_sectional import CrossSectionalSpec
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR

logger = logging.getLogger(__name__)

DM_OVERLAY_CITATION = (
    "Daniel & Moskowitz, 'Momentum crashes' (Journal of Financial Economics 122(2), 2016, "
    "pp. 221-247, doi:10.1016/j.jfineco.2015.12.002) — a bear-state indicator (one if the "
    "cumulative CRSP VW index return over the past 24 months is negative, Table 4 notes) and a "
    "mean/variance dynamic weight w* = (1/2*lambda) * mu/sigma^2 (Eq. 6), applied here as a "
    "crash-mitigation overlay on Blitz/Huij/Martens residual momentum"
)

DM_OVERLAY_FAMILY = "residual_momentum_dm_overlay"
DM_OVERLAY_FAMILY_KEY = "residual_momentum_dm_overlay"

# --- D&M's own construction constants ---------------------------------------

# "the cumulative CRSP VW index return in the past 24 months" (Table 4 notes).
DM_BEAR_LOOKBACK_MONTHS = 24

# "the variance of the daily returns of the market over the 126 days prior to
# time t" (Eq. 4), and "the realized variance of the daily WML returns over the
# preceding 126 trading days" (Table 7 notes). One window, both uses, theirs.
DM_VARIANCE_WINDOW_DAYS = 126

# The expanding-window mean forecast needs enough months to identify two
# coefficients before it is allowed to move any money. D&M have 1927:07 to work
# from and start their out-of-sample series in 1934:01 — about 78 months of
# warmup. 36 is this build's floor, far shorter because the whole replay is
# only ~138 months; before it, and before at least one bear month exists in the
# window, the `dyn` arm holds w = 1 (the un-overlaid base) rather than trading
# on an unidentified regression.
DM_MIN_FORECAST_MONTHS = 36

# Gross notional per unit of book weight: a fully formed long_short book is
# 1.0 long + 1.0 short (cross_sectional.form_portfolio's gross_notional_held).
# Changing leverage from w_prev to w_new therefore trades |dw| * 2.0 of one-way
# notional, charged at the family's own cost_bps.
GROSS_NOTIONAL_PER_UNIT_WEIGHT = 2.0

# The three already-screened residual-momentum specs this overlay rides on, at
# h21 (BHM's own monthly rebalance, and the cadence D&M's monthly weighting
# requires). Holding period is NOT a search axis here. The key order is the
# pre-registration's own.
DM_BASE_SPECS: tuple[tuple[str, str], ...] = (
    ("ctrl", "rm_total_return_control_ls_h21"),
    ("ff3", "rm_ff3_residual_ls_h21"),
    ("ff3n", "rm_ff3_residual_neutral_ls_h21"),
)

# The four overlay arms. `bear` is an ABLATION, not a D&M construction — see
# `overlay_weights`.
DM_OVERLAY_ARMS: tuple[str, ...] = ("cvol", "vscale", "bear", "dyn")

# 3 bases x 4 overlays, all fixed before anything ran.
DM_OVERLAY_N_NEW_SPECS = len(DM_BASE_SPECS) * len(DM_OVERLAY_ARMS)

# The residual-momentum family's own already-searched grid, carried into this
# grid's DSR denominator because those 18 Sharpes were computed, persisted and
# READ before these 12 specs were designed — the choice of which three to build
# on was made with them in view. dd288f9's own section D.6 instructs any
# follow-up to "carry these 18 trials into the denominator"; this is that.
DM_OVERLAY_PRIOR_TRIALS = 18
DM_OVERLAY_N_TRIALS = DM_OVERLAY_PRIOR_TRIALS + DM_OVERLAY_N_NEW_SPECS  # 30

# Pre-registration section 7: exactly two of the twelve are eligible to be
# PROPOSED for forward validation. Everything else is non-registrable whatever
# it scores — the industry-neutral base was declined in dd288f9, the
# total-return base is BHM's comparison baseline rather than this family's
# hypothesis, and the two bear-conditioned arms are underpowered by section 4.
DM_REGISTRABLE_SPEC_IDS: frozenset[str] = frozenset({"dm_ff3_cvol_h21", "dm_ff3_vscale_h21"})


def overlay_pattern_id(base_key: str, arm: str) -> str:
    return f"dm_{base_key}_{arm}_h21"


# --- D&M's market-state variables --------------------------------------------


def bear_market_indicator(
    market_monthly_returns: pd.Series,
    *,
    lookback_months: int = DM_BEAR_LOOKBACK_MONTHS,
) -> pd.Series:
    """D&M's IB: 1.0 when the cumulative index return over the trailing
    `lookback_months` months is negative, 0.0 when it is not, NaN when the
    window is incomplete.

    Verbatim from the paper's Table 4 notes (p. 230): "an ex ante bear market
    indicator that equals one if the cumulative CRSP VW index return in the
    past 24 months is negative and is zero otherwise."

    `market_monthly_returns` must be TOTAL (not excess) simple monthly returns
    on a value-weighted index, indexed by month end. From Ken French's own file
    that is mkt_rf + rf, which IS the CRSP VW index return.

    NaN RATHER THAN 0.0 for an incomplete window, deliberately: an unformed
    indicator that defaulted to "not a bear market" would be indistinguishable
    in the output from a real calm reading, and the caller — not this function
    — should decide what an unknown state means.

    THE VALUE AT MONTH m IS COMPUTED FROM MONTHS m-23..m INCLUSIVE. It is
    therefore the state known AT THE END of month m, i.e. D&M's IB,t-1 for
    t = m+1. Every caller in this module lags it by one month accordingly, and
    `monthly_overlay_weights` is where that lag is applied, once."""
    if lookback_months < 1:
        raise ValueError(f"lookback_months={lookback_months} must be >= 1")
    cumulative = (1.0 + market_monthly_returns).rolling(lookback_months).apply(
        np.prod, raw=True
    ) - 1.0
    indicator = (cumulative < 0.0).astype(float)
    return indicator.where(cumulative.notna())


def trailing_annualized_variance(
    daily_returns: pd.Series,
    *,
    window_days: int = DM_VARIANCE_WINDOW_DAYS,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> pd.Series:
    """Rolling `window_days`-day realized variance of a daily return series,
    annualized. NaN until the window is full — never a short-window estimate
    dressed up as a full one.

    D&M use this same 126-day window for BOTH the market variance in their
    mean forecast (Eq. 4) and the strategy's own variance in the weight
    (Table 7 notes), so it is one function used twice rather than two."""
    return daily_returns.rolling(window_days).var(ddof=1) * periods_per_year


def month_end_positions(index: pd.DatetimeIndex) -> list[int]:
    """Positions in a daily index of the LAST trading day of each calendar
    month. These are the only dates any weight in this module is set on, which
    is D&M's cadence: the weight for month m is fixed on the last trading day
    of month m-1 and held for every trading day of month m."""
    frame = pd.Series(np.arange(len(index)), index=index)
    return [int(p) for p in frame.groupby([index.year, index.month]).max().to_numpy()]


# --- the four overlay weight rules -------------------------------------------


@dataclass
class OverlayWeightDiagnostics:
    """What the weight construction produced and refused, measured rather than
    assumed — this project's standing rule that a guard which silently stops
    firing must not look like one that was never checked."""

    n_months: int = 0
    n_warmup_months: int = 0  # held at w = 1 for want of 126 days of history
    n_unidentified_months: int = 0  # `dyn` only: regression not yet estimable
    n_bear_months: int = 0
    n_months_weight_moved: int = 0  # |w - 1| > 1% after normalization
    weight_min: float = float("nan")
    weight_max: float = float("nan")
    weight_mean_abs: float = float("nan")
    n_negative_weight_months: int = 0
    normalization_k: float = float("nan")


def _expanding_mean_forecast(
    monthly_strategy_returns: pd.Series,
    regressor: pd.Series,
    *,
    min_months: int = DM_MIN_FORECAST_MONTHS,
) -> tuple[pd.Series, int]:
    """D&M's out-of-sample mu_hat (Fig. 7 caption, p. 236), month by month.

    THE REGRESSION IS PREDICTIVE, NOT CONTEMPORANEOUS, and that distinction is
    the whole content of the paper. D&M's Eq. (4), p. 230, pairs month t's WML
    return with the state at t-1:

        R_WML,t = gamma_0 + ... + gamma_int * IB,t-1 * sigma^2_m,t-1 + eps_t

    So at each month m this fits y[j] against x[j-1] for every j <= m, and then
    forecasts with the state actually in hand:

        mu_hat(m) = g0 + g_int * x[m]        (the forecast for month m+1)

    AN EARLIER DRAFT OF THIS FUNCTION PAIRED y[j] WITH x[j], CONTEMPORANEOUSLY,
    and it is recorded here rather than quietly corrected. That version was not
    a look-ahead in the applied weight — x[m] is known at the end of month m
    either way — but it estimated "how does WML co-move with the panic state it
    is living through" and then used that as though it were "how does WML
    respond to the panic state it inherited", which is a different coefficient
    and not the paper's. Caught by re-reading Eq. (4) against the code.

    The window is EXPANDING and strictly backward-looking, which is the whole
    reason this version of the paper's strategy is implementable and the
    in-sample one is not.

    Returns (mu_hat by month, count of months left unidentified). A month is
    unidentified — and gets NaN, never a fabricated forecast — when fewer than
    `min_months` usable (y[j], x[j-1]) pairs exist, or when the regressor has no
    variation in the window (which here means NO BEAR MONTH HAS EVER HAPPENED
    YET, so g_int is not estimable at all). Refusing rather than falling back to
    an intercept-only fit matters: an intercept-only mu_hat is a constant, and a
    constant mu_hat turns `dyn` silently into `vscale` while still being
    reported as the paper's dynamic strategy."""
    values = np.full(len(monthly_strategy_returns), np.nan)
    y_all = monthly_strategy_returns.to_numpy(dtype=float)
    x_all = regressor.to_numpy(dtype=float)
    # x_lagged[j] is the state at the END of month j-1, i.e. D&M's x_{t-1} for
    # the return y[j]. Position 0 has no predecessor and is never usable.
    x_lagged = np.concatenate([[np.nan], x_all[:-1]])
    n_unidentified = 0

    for m in range(len(monthly_strategy_returns)):
        y = y_all[: m + 1]
        x = x_lagged[: m + 1]
        usable = np.isfinite(y) & np.isfinite(x)
        if usable.sum() < min_months or not np.isfinite(x_all[m]):
            n_unidentified += 1
            continue
        x_fit = x[usable]
        if np.ptp(x_fit) <= 0.0:
            # No bear month in the window yet: g_int is unidentified.
            n_unidentified += 1
            continue
        design = np.column_stack([np.ones(int(usable.sum())), x_fit])
        coefficients, *_ = np.linalg.lstsq(design, y[usable], rcond=None)
        values[m] = float(coefficients[0] + coefficients[1] * x_all[m])

    return pd.Series(values, index=monthly_strategy_returns.index), n_unidentified


def overlay_weights(
    arm: str,
    *,
    own_variance: pd.Series,
    bear: pd.Series,
    market_variance: pd.Series,
    monthly_strategy_returns: pd.Series,
) -> tuple[pd.Series, int]:
    """The RAW (un-normalized) monthly weight for one arm, plus the count of
    months the `dyn` regression could not be identified on.

    Every input is indexed by month end and is ALREADY the state known at the
    end of that month — the one-month lag that turns "state at end of m" into
    "weight applied over m+1" is applied by the caller, once, in
    `monthly_overlay_weights`. Doing it here as well is the single easiest way
    to introduce a silent one-month look-ahead into this module, so it is not
    done here at all.

        cvol    w = 1 / sigma          D&M Table 7 "cvol" (Barroso &
                                       Santa-Clara's constant-volatility
                                       strategy, as the paper implements it)
        vscale  w = 1 / sigma^2        D&M Table 7 "variance scaled"
        bear    w = 0 in bear states   ABLATION — NOT a D&M construction
        dyn     w = mu_hat / sigma^2   D&M Eq. 6 with the Fig. 7 out-of-sample
                                       expanding-window mean forecast

    `bear` IS AN ABLATION AND IS LABELLED ONE EVERYWHERE IT IS REPORTED. D&M
    never propose a binary gate; in their construction IB enters continuously,
    through mu_hat. This arm exists only because it is the one way to separate
    the bear axis from the volatility axis, which this project's
    mechanism-fidelity standard requires — the two are fused in `dyn` and a
    result there could not be attributed to either.

    NO CAP AND NO FLOOR IS APPLIED TO ANY WEIGHT. The paper's own dynamic
    weight reaches 5.37 and is negative in 82 months of its sample (p. 233);
    capping would add a searched parameter the source does not have."""
    if arm not in DM_OVERLAY_ARMS:
        raise ValueError(f"unknown overlay arm {arm!r}; expected one of {DM_OVERLAY_ARMS}")

    if arm == "cvol":
        with np.errstate(divide="ignore", invalid="ignore"):
            return 1.0 / np.sqrt(own_variance), 0
    if arm == "vscale":
        with np.errstate(divide="ignore", invalid="ignore"):
            return 1.0 / own_variance, 0
    if arm == "bear":
        # NaN (unknown state) is NOT treated as calm: it stays NaN and the
        # caller's warmup rule holds the base weight, so an unformed indicator
        # can never be mistaken for a measured all-clear.
        return (1.0 - bear).where(bear.notna()), 0

    regressor = bear * market_variance
    mu_hat, n_unidentified = _expanding_mean_forecast(monthly_strategy_returns, regressor)
    with np.errstate(divide="ignore", invalid="ignore"):
        return mu_hat / own_variance, n_unidentified


def monthly_overlay_weights(
    arm: str,
    daily_base_returns: pd.Series,
    *,
    market_monthly_returns: pd.Series,
    market_daily_returns: pd.Series,
    window_days: int = DM_VARIANCE_WINDOW_DAYS,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    extra_lag_months: int = 0,
) -> tuple[pd.Series, OverlayWeightDiagnostics]:
    """The DAILY weight series for one arm: one weight per trading day of
    `daily_base_returns`, constant within each calendar month, and set from
    information available on the last trading day of the PREVIOUS month.

    THE ONE-MONTH LAG LIVES HERE AND NOWHERE ELSE. Every state input is
    computed as of the end of month m and then shifted forward one month, so
    the weight in force during month m+1 uses nothing from month m+1. That
    single `shift(1)` is the module's whole point-in-time guarantee for the
    overlay, and it is asserted below rather than trusted.

    WARMUP HOLDS w = 1, deliberately. Before 126 trading days of base returns
    exist (and, for `dyn`, before the forecast regression is identified) the
    weight is the base's own 1.0 rather than NaN or a truncated-window
    estimate. That keeps the overlaid series defined on an IDENTICAL day set to
    the base, so the base's Sharpe reproduces exactly and every difference
    between the two series is the overlay and nothing else. A dropped warmup
    would instead have changed the comparison's sample."""
    index = daily_base_returns.index
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("daily_base_returns must be indexed by trading date")

    diagnostics = OverlayWeightDiagnostics()

    # --- state, all measured AT each month end -------------------------------
    ends = month_end_positions(index)
    month_end_index = index[ends]

    own_variance_daily = trailing_annualized_variance(
        daily_base_returns, window_days=window_days, periods_per_year=periods_per_year
    )
    own_variance = own_variance_daily.iloc[ends]

    market_variance_daily = trailing_annualized_variance(
        market_daily_returns.reindex(index), window_days=window_days, periods_per_year=periods_per_year
    )
    market_variance = market_variance_daily.iloc[ends]

    bear_monthly = bear_market_indicator(market_monthly_returns)
    # The monthly market series is indexed by CALENDAR month end; the strategy
    # is indexed by TRADING day. Align on (year, month) rather than on the
    # timestamp, which would miss whenever the last trading day is not the last
    # calendar day (i.e. most months).
    bear_by_period = bear_monthly.copy()
    bear_by_period.index = bear_monthly.index.to_period("M")
    bear = pd.Series(
        [bear_by_period.get(ts.to_period("M"), np.nan) for ts in month_end_index],
        index=month_end_index,
        dtype=float,
    )
    diagnostics.n_bear_months = int((bear == 1.0).sum())

    monthly_strategy_returns = (1.0 + daily_base_returns).groupby(
        [index.year, index.month]
    ).prod() - 1.0
    monthly_strategy_returns.index = month_end_index

    raw, n_unidentified = overlay_weights(
        arm,
        own_variance=own_variance,
        bear=bear,
        market_variance=market_variance,
        monthly_strategy_returns=monthly_strategy_returns,
    )
    diagnostics.n_unidentified_months = n_unidentified

    # --- THE LAG: state at the end of month m governs month m+1 --------------
    # `extra_lag_months` is the LOOK-AHEAD PROBE, not a tunable. Delaying the
    # weight by further whole months can only DESTROY information; it can never
    # add any. So an overlay whose measured benefit survives an extra month of
    # delay is reading something genuinely persistent (volatility clusters for
    # months), while one whose benefit collapses was reading something that had
    # to be acted on immediately -- which, for a weight built from trailing
    # windows, would mean the trailing window was not as trailing as it looks.
    # Nothing in this module's headline uses a non-zero value.
    if extra_lag_months < 0:
        raise ValueError(
            f"extra_lag_months={extra_lag_months} is negative — a NEGATIVE lag would let the "
            "weight for month m read the state at the end of month m, which is look-ahead."
        )
    lagged = raw.shift(1 + extra_lag_months)
    assert lagged.index.equals(raw.index), "the shift must not reindex"

    diagnostics.n_months = len(lagged)
    diagnostics.n_warmup_months = int((~np.isfinite(lagged.to_numpy(dtype=float))).sum())
    # WARMUP MONTHS STAY NaN HERE AND ARE FILLED WITH 1.0 ONLY AFTER THE
    # NORMALIZATION CONSTANT HAS BEEN APPLIED (see build_overlay). Filling them
    # with 1.0 at this point would be wrong in a way that is easy to miss and
    # not small: k multiplies whatever it finds, and for the `vscale` arm k is
    # ~0.029, so a warmup month "held at the base" would in fact have been held
    # at ~3% OF THE BASE — i.e. very nearly flat. An earlier draft of this
    # module did exactly that, and because the warmup lands on the sample's
    # first seven months it silently deleted whatever happened there. Caught by
    # printing the realized monthly weights and finding 0.029 where the
    # docstring promised 1.0.
    weights_by_month = lagged.replace([np.inf, -np.inf], np.nan)

    # --- broadcast the monthly weight onto every trading day -----------------
    daily = pd.Series(np.nan, index=index, dtype=float)
    for position, ts in zip(ends, month_end_index):
        daily.iloc[position] = float(weights_by_month.loc[ts])
    # Each month's weight is stamped on that month's LAST day, then carried
    # BACKWARD to the month's other days: the weight is constant within the
    # month, so back-filling inside the month introduces nothing the last day
    # of the month did not already have. It is bounded to the month by the
    # groupby, never across a month boundary.
    daily = daily.groupby([index.year, index.month]).transform(
        lambda s: s.bfill().ffill()
    )
    return daily, diagnostics


# --- applying an overlay to a return series ----------------------------------


@dataclass
class OverlayResult:
    """One overlaid return series and everything needed to interpret it."""

    pattern_id: str
    base_key: str
    base_pattern_id: str
    arm: str
    returns: pd.Series  # overlaid, net of the overlay's own turnover cost
    returns_pre_overlay_cost: pd.Series
    weights: pd.Series
    overlay_cost_total: float
    normalization_k: float
    diagnostics: OverlayWeightDiagnostics = field(default_factory=OverlayWeightDiagnostics)


def normalization_constant(
    base_returns: pd.Series, weights: pd.Series, *, weight_floor: float = 1e-12
) -> float:
    """The single constant k that makes the overlaid series' full-sample
    volatility equal the base's own — D&M's own convention, p. 233: "we scale
    the weights of both the constant volatility and the dynamic strategy so as
    to make the full sample volatility of each return series equal to that of
    the baseline WML strategy".

    STATED PLAINLY: THIS IS A FULL-SAMPLE QUANTITY. It uses the realized
    volatility of the whole overlaid series to set a level. It is nonetheless
    not a route to a flattering Sharpe, and that is arithmetic rather than
    assurance: a Sharpe ratio is invariant to a constant multiplier, so k
    cannot move any Sharpe, PSR or DSR reported by this module by any amount.
    What it does move is the overlay's turnover cost and the percentage depth
    of a drawdown, which is why the run reports a k/2 and 2k sensitivity on
    both."""
    overlaid = weights * base_returns
    scale = float(overlaid.std(ddof=1))
    if not np.isfinite(scale) or scale < weight_floor:
        return 1.0
    return float(base_returns.std(ddof=1)) / scale


def apply_overlay(
    base_returns: pd.Series,
    weights: pd.Series,
    *,
    cost_bps: float,
    gross_notional_per_unit: float = GROSS_NOTIONAL_PER_UNIT_WEIGHT,
    initial_weight: float = 1.0,
) -> tuple[pd.Series, pd.Series, float]:
    """Apply a daily weight series to a daily base return series and charge the
    overlay's OWN trading cost.

    Returns (net overlaid returns, pre-overlay-cost overlaid returns, total
    overlay cost charged).

    THE COST IS REAL AND IS CHARGED. D&M note (p. 233) that "an actual
    implementation of the dynamic strategy would certainly incur higher
    transaction costs" and leave it there. Moving the book's leverage from
    w_prev to w_new means trading |w_new - w_prev| * gross_notional_per_unit of
    one-way notional — a $1-long/$1-short book carries 2.0 of gross notional
    per unit of weight, so a leverage change trades both legs — and it is
    charged at the family's own cost_bps on the day the weight changes.

    THE BASE'S OWN REBALANCING COST IS ALREADY INSIDE `base_returns` and is
    scaled by the weight along with the returns. That is correct rather than
    convenient: trading cost scales with notional, so a book run at 1.5x pays
    1.5x its own rebalancing cost.

    `initial_weight` = 1.0 because the warmup convention holds the un-overlaid
    base at the start of the series, so the first weight change is measured
    against 1.0 and not against a free zero that would hide the cost of
    establishing the position."""
    if not base_returns.index.equals(weights.index):
        raise ValueError("weights must share the base return series' index exactly")
    rate = cost_bps / 10_000.0
    aligned = weights.to_numpy(dtype=float)
    previous = np.concatenate([[initial_weight], aligned[:-1]])
    traded = np.abs(aligned - previous) * gross_notional_per_unit
    cost = traded * rate

    gross = weights * base_returns
    net = gross - pd.Series(cost, index=base_returns.index)
    return net, gross, float(cost.sum())


def build_overlay(
    base_key: str,
    base_pattern_id: str,
    arm: str,
    daily_base_returns: pd.Series,
    *,
    market_monthly_returns: pd.Series,
    market_daily_returns: pd.Series,
    cost_bps: float,
    normalization_scale: float = 1.0,
    extra_lag_months: int = 0,
) -> OverlayResult:
    """One (base, arm) cell end to end: weights, normalization, cost.

    `normalization_scale` multiplies the D&M-convention k and exists ONLY for
    the pre-registered k/2 and 2k cost sensitivity. `extra_lag_months` exists
    ONLY for the look-ahead probe described in `monthly_overlay_weights`. Both
    default to their no-op values and no reported headline uses anything
    else."""
    weights, diagnostics = monthly_overlay_weights(
        arm,
        daily_base_returns,
        market_monthly_returns=market_monthly_returns,
        market_daily_returns=market_daily_returns,
        extra_lag_months=extra_lag_months,
    )
    # k is estimated on the days the overlay is actually ACTIVE, then applied,
    # and only then do the warmup days take the base's own weight of exactly
    # 1.0. Order matters: normalizing after the fill would scale the warmup
    # too, which is not "hold the base" (see monthly_overlay_weights).
    active = weights.notna()
    if not active.any():
        raise ValueError(f"overlay arm {arm!r} produced no active weights at all")
    k = (
        normalization_constant(daily_base_returns[active], weights[active])
        * normalization_scale
    )
    weights = (weights * k).fillna(1.0)

    diagnostics.normalization_k = k
    finite = weights.to_numpy(dtype=float)
    diagnostics.weight_min = float(np.nanmin(finite))
    diagnostics.weight_max = float(np.nanmax(finite))
    diagnostics.weight_mean_abs = float(np.nanmean(np.abs(finite)))
    ends = month_end_positions(weights.index)
    monthly = weights.iloc[ends]
    diagnostics.n_negative_weight_months = int((monthly < 0.0).sum())
    diagnostics.n_months_weight_moved = int((np.abs(monthly - 1.0) > 0.01).sum())

    net, gross, total_cost = apply_overlay(daily_base_returns, weights, cost_bps=cost_bps)
    return OverlayResult(
        pattern_id=overlay_pattern_id(base_key, arm),
        base_key=base_key,
        base_pattern_id=base_pattern_id,
        arm=arm,
        returns=net,
        returns_pre_overlay_cost=gross,
        weights=weights,
        overlay_cost_total=total_cost,
        normalization_k=k,
        diagnostics=diagnostics,
    )


# --- the pre-declared grid ---------------------------------------------------


def build_dm_overlay_grid() -> list[tuple[str, str, str]]:
    """The 12 pre-declared (base_key, base_pattern_id, arm) cells.

    The grid (3 bases x 4 arms, and the count of 12) is fixed in the module
    constants above and in the pre-registration. The assertion is not
    decoration: a silent drift in this list changes this grid's DSR denominator
    and therefore every number it reports."""
    cells = [
        (base_key, base_pattern_id, arm)
        for base_key, base_pattern_id in DM_BASE_SPECS
        for arm in DM_OVERLAY_ARMS
    ]
    assert len(cells) == DM_OVERLAY_N_NEW_SPECS == 12, (
        f"the D&M overlay grid built {len(cells)} cells; the declared grid implies "
        f"{DM_OVERLAY_N_NEW_SPECS} and the pre-registration froze exactly 12."
    )
    assert DM_OVERLAY_N_TRIALS == 30, (
        "n_trials must be 18 prior residual-momentum trials + 12 new cells = 30; the "
        "pre-registration fixes that denominator and dd288f9 section D.6 requires the 18 "
        "be carried."
    )
    assert DM_REGISTRABLE_SPEC_IDS <= {overlay_pattern_id(b, a) for b, _p, a in cells}
    return cells


def base_specs_for_overlay(all_residual_momentum_specs: list[CrossSectionalSpec]) -> dict[str, CrossSectionalSpec]:
    """The three base specs, looked up by pattern_id out of the residual-
    momentum family's own 18. Raises rather than silently skipping: a missing
    base means the overlay would be built on a spec this project never
    screened."""
    by_id = {spec.pattern_id: spec for spec in all_residual_momentum_specs}
    resolved: dict[str, CrossSectionalSpec] = {}
    for base_key, base_pattern_id in DM_BASE_SPECS:
        if base_pattern_id not in by_id:
            raise ValueError(
                f"base spec {base_pattern_id!r} is not in the residual-momentum family; the "
                "overlay cannot be built on a spec that was never screened."
            )
        resolved[base_key] = by_id[base_pattern_id]
    return resolved


@dataclass
class DmOverlaySummary:
    """Everything a reader needs to interpret one run of this grid."""

    overlays: list[OverlayResult]
    base_returns: dict[str, pd.Series]
    n_trials: int = DM_OVERLAY_N_TRIALS
    n_new_specs: int = DM_OVERLAY_N_NEW_SPECS
    prior_trials: int = DM_OVERLAY_PRIOR_TRIALS
    bear_months: list[date] = field(default_factory=list)
    n_market_months: int = 0
    cost_bps: float = 0.0
    warnings: list[str] = field(default_factory=list)
