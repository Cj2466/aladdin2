"""The TSMOM signal formula, transcribed from MOP 2012 and validated against
synthetic data with known answers BEFORE it ever meets real futures prices.

SCOPE -- read this before adding anything here
====================================================================
This module contains the FORMULA ONLY: pure functions of a return series.
No data access, no universe construction, no contract chaining, no
backtest, no DSR, no registration. Those come later and elsewhere.

That split is deliberate. CLAUDE.md's rule is "never implement a published
formula from memory -- put the source paper/section in context, cite the
equation number in code, and validate against synthetic data with a known
true answer before trusting it on real data." Keeping the formula in its own
module with no I/O is what makes that validation possible: every function
here can be checked against arithmetic on a hand-built series, with no
market data anywhere near it. See tests/test_tsmom_signal_formula.py, which
is the harness that does exactly that.

The real futures data is NOT wired in, on purpose -- the universe's
effective-breadth gate has not been measured yet (see
futures_effective_breadth.py), and the CME SPAN pull is still incomplete.

SOURCE
====================================================================
Moskowitz, T. J., Ooi, Y. H. & Pedersen, L. H., "Time series momentum",
Journal of Financial Economics 104(2), 2012, pp. 228-250. Quoted verbatim
below from the authors' own hosted copy, extracted and read on 2026-09-07.

--- Section 2.4 "Ex ante volatility estimate", p.233 -------------------

    "We estimate each instrument's ex ante volatility sigma_t at each point
    in time using an extremely simple model: the exponentially weighted
    lagged squared daily returns (i.e., similar to a simple univariate
    GARCH model). Specifically, the ex ante annualized variance sigma_t^2
    for each instrument is calculated as follows:

        sigma_t^2 = 261 * sum_{i=0}^{inf} (1-delta) delta^i (r_{t-1-i} - rbar_t)^2   (1)

    where the scalar 261 scales the variance to be annual, the weights
    (1-delta) delta^i add up to one, and rbar_t is the exponentially
    weighted average return computed similarly. The parameter delta is
    chosen so that the center of mass of the weights is
    sum_{i=0}^{inf} (1-delta) delta^i i = delta/(1-delta) = 60 days. The
    volatility model is the same for all assets at all times. While all of
    the results in the paper are robust to more sophisticated volatility
    models, we chose this model due to its simplicity and lack of look-ahead
    bias in the volatility[.]"

Three things this quote settles that would otherwise be guesses:
  * 261, not 252, is the annualization constant. Transcribed, not assumed.
  * The sum runs over r_{t-1-i}, i.e. STRICTLY LAGGED returns. sigma_t is
    knowable at t. This is the paper's own stated "lack of look-ahead bias"
    and it is enforced and tested here.
  * The deviation is taken from rbar_t, an exponentially weighted MEAN over
    the same weights -- not from zero. Many secondary write-ups of this
    formula silently drop the mean; this one does not.

  delta/(1-delta) = 60  =>  delta = 60/61 = 0.9836065573770492

--- Section 4.1, p.236 -- position sizing and the strategy return -------

    "We size each position (long or short) so that it has an ex ante
    annualized volatility of 40%. That is, the position size is chosen to be
    40%/sigma_{t-1}, where sigma_{t-1} is the estimate of the ex ante
    volatility of the contract as described above. The choice of 40% is
    inconsequential, but it makes it easier to intuitively compare our
    portfolios to others in the literature. The 40% annual volatility is
    chosen because it is similar to the risk of an average individual stock,
    and when we average the return across all securities (equal-weighted) to
    form the portfolio of securities which represent our TSMOM factor, it
    has an annualized volatility of 12% per year over the sample period
    1985-2009[.] The TSMOM return for any instrument s at time t is
    therefore:

        r^{TSMOM,s}_{t,t+1} = sign(r^s_{t-12,t}) * (40% / sigma^s_t) * r^s_{t,t+1}   (5)"

    And the diversified portfolio, same page:

        r^{TSMOM}_{t,t+1} = (1/S_t) * sum_{s=1}^{S_t}
                            sign(r^s_{t-12,t}) * (40%/sigma^s_t) * r^s_{t,t+1}

NOTE ON EQUATION NUMBERING -- a correction to this task's own brief:
the position-sizing equation is **Eq. (5) on p.236**, NOT Eq. (2)/(3). Eq.
(3), p.233, is a different thing entirely -- the sign-based PREDICTIVE
REGRESSION r^s_t/sigma^s_{t-1} = alpha + beta_h sign(r^s_{t-h}) + e^s_t,
used to document predictability, not to size a position. Recorded because
citing Eq. (3) for position sizing would be a real mechanism-fidelity error.

A NOTATIONAL INCONSISTENCY IN THE SOURCE, FLAGGED NOT PAPERED OVER:
the prose says the position size is "40%/sigma_{t-1}" while Eq. (5) writes
"40%/sigma^s_t". These denote the same quantity -- the ex ante estimate that
is known when the position is put on -- because Eq. (1) already defines
sigma_t from returns up to t-1. The subscript differs; the information set
does not. This module follows Eq. (1)'s definition, so sigma_t uses returns
through t-1 and the position for the t -> t+1 holding period is set using
sigma_t. Stated explicitly so a later reviewer does not "fix" it in the
wrong direction.

--- Section 4, p.236 -- the headline parameterization -------------------

    "we focus on the properties of the 12-month time series momentum
    strategy with a 1-month holding period (e.g., k=12 and h=1), which we
    refer to simply as TSMOM."

So: sign of the trailing 12-month return, held one month, with the
volatility estimated from DAILY returns via Eq. (1).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CONSTANTS -- every one transcribed from the quotes above, none chosen here.
# ---------------------------------------------------------------------------

#: MOP Eq. (1): "the scalar 261 scales the variance to be annual". 261, not
#: 252. Transcribed from the paper.
MOP_ANNUALIZATION_DAYS = 261

#: MOP Eq. (1): delta is chosen so the center of mass delta/(1-delta) is 60
#: days.
MOP_VOLATILITY_CENTER_OF_MASS_DAYS = 60

#: MOP p.236: "an ex ante annualized volatility of 40%".
MOP_VOLATILITY_TARGET = 0.40

#: MOP p.236: "k=12 and h=1".
MOP_LOOKBACK_MONTHS = 12
MOP_HOLDING_MONTHS = 1


def mop_delta_from_center_of_mass(
    center_of_mass_days: float = MOP_VOLATILITY_CENTER_OF_MASS_DAYS,
) -> float:
    """Invert MOP Eq. (1)'s stated condition delta/(1-delta) = c.

        delta / (1 - delta) = c   =>   delta = c / (1 + c)

    For c = 60 this gives delta = 60/61 = 0.9836065573770492.

    Derived rather than hard-coded so the relationship the paper actually
    states is the thing in the code, and so a different center of mass can
    be justified explicitly rather than by editing a magic number.
    """
    if center_of_mass_days <= 0:
        raise ValueError("center of mass must be positive")
    return float(center_of_mass_days / (1.0 + center_of_mass_days))


#: delta = 60/61.
MOP_DELTA = mop_delta_from_center_of_mass()


def ex_ante_volatility(
    daily_returns: pd.Series,
    delta: float = MOP_DELTA,
    annualization_days: int = MOP_ANNUALIZATION_DAYS,
    min_periods: int = 2,
) -> pd.Series:
    """MOP 2012 Eq. (1), p.233 -- ex ante ANNUALIZED volatility (sigma_t,
    the square root of the variance Eq. (1) defines).

        sigma_t^2 = 261 * sum_i (1-delta) delta^i (r_{t-1-i} - rbar_t)^2

    IMPLEMENTATION NOTE -- why this is an exact transcription, not an
    approximation. With weights w_i = (1-delta) delta^i summing to one and
    rbar_t = sum_i w_i r_{t-1-i},

        sum_i w_i (r_{t-1-i} - rbar_t)^2
            = sum_i w_i r_{t-1-i}^2 - 2 rbar_t sum_i w_i r_{t-1-i} + rbar_t^2
            = E_w[r^2] - 2 rbar_t^2 + rbar_t^2
            = E_w[r^2] - rbar_t^2

    so the weighted variance is exactly (EWMA of r^2) minus (EWMA of r)^2.
    That identity is what is computed below, which is why no truncation of
    the infinite sum is involved.

    LAGGING: the sum is over r_{t-1-i}, so the series is shifted by one
    before any weighting. sigma_t therefore depends only on returns strictly
    before t and is knowable at t -- the paper's own "lack of look-ahead
    bias". This is enforced here and tested.

    `min_periods` is the number of lagged observations required before a
    value is emitted; below it the result is NaN rather than a volatility
    estimated from one point.

    Returns annualized volatility (0.20 == 20% per year), NOT variance.
    """
    if not isinstance(daily_returns, pd.Series):
        raise TypeError("daily_returns must be a pd.Series")
    if not 0.0 < delta < 1.0:
        raise ValueError("delta must lie strictly between 0 and 1")

    lagged = daily_returns.shift(1)
    alpha = 1.0 - delta  # pandas weights go as (1-alpha)^i = delta^i

    weighted_mean = lagged.ewm(alpha=alpha, adjust=True, min_periods=min_periods).mean()
    weighted_mean_of_squares = (
        (lagged**2).ewm(alpha=alpha, adjust=True, min_periods=min_periods).mean()
    )

    variance = weighted_mean_of_squares - weighted_mean**2
    # Floating-point cancellation can push a mathematically-zero variance a
    # hair below zero; clip rather than emit NaN from the square root.
    variance = variance.clip(lower=0.0)
    return np.sqrt(annualization_days * variance)


def trailing_return(returns: pd.Series, periods: int) -> pd.Series:
    """Cumulative compounded return over the trailing `periods` observations,
    inclusive of the current one -- MOP's r^s_{t-12,t} when `returns` is a
    monthly series and periods=12.

    Compounded, not summed: MOP construct a "cumulative return index from
    which we can compute returns at any horizon" (Section 2.1).
    """
    if periods < 1:
        raise ValueError("periods must be >= 1")
    log_growth = np.log1p(returns)
    return np.expm1(log_growth.rolling(periods).sum())


def tsmom_sign(returns: pd.Series, lookback_periods: int = MOP_LOOKBACK_MONTHS) -> pd.Series:
    """sign(r_{t-12,t}) from MOP Eq. (5).

    +1 / -1. A trailing return of EXACTLY zero yields 0 (no position), which
    is what numpy's sign gives and is the honest reading: MOP's own
    formulation offers no tie-break, and inventing one (defaulting flat ties
    to long, say) would be an undocumented deviation that quietly adds a
    long bias.
    """
    return np.sign(trailing_return(returns, lookback_periods))


def position_size(
    ex_ante_vol: pd.Series | float,
    volatility_target: float = MOP_VOLATILITY_TARGET,
) -> pd.Series | float:
    """MOP p.236: "the position size is chosen to be 40%/sigma_{t-1}".

    Returns target/sigma. An instrument with 20% ex ante vol gets 2.0x; one
    with 80% gets 0.5x. Zero or non-finite volatility yields NaN rather than
    an infinite position.
    """
    if isinstance(ex_ante_vol, pd.Series):
        safe = ex_ante_vol.where(ex_ante_vol > 0.0)
        return volatility_target / safe
    if not np.isfinite(ex_ante_vol) or ex_ante_vol <= 0.0:
        return float("nan")
    return volatility_target / float(ex_ante_vol)


def tsmom_strategy_return(
    signal_returns: pd.Series,
    realized_returns: pd.Series,
    ex_ante_vol: pd.Series,
    lookback_periods: int = MOP_LOOKBACK_MONTHS,
    volatility_target: float = MOP_VOLATILITY_TARGET,
) -> pd.Series:
    """MOP 2012 Eq. (5), p.236, for a single instrument:

        r^{TSMOM,s}_{t,t+1} = sign(r^s_{t-12,t}) * (40% / sigma^s_t) * r^s_{t,t+1}

    Parameters
    ----------
    signal_returns
        The return series the 12-period lookback sign is computed from
        (monthly, for MOP's headline k=12/h=1 specification).
    realized_returns
        The NEXT period's realized return r_{t,t+1}, already aligned to t --
        i.e. `signal_returns.shift(-1)` for a simple one-period hold. Passed
        separately rather than shifted internally so the caller's alignment
        is explicit and auditable, which is the single easiest place to
        introduce lookahead by accident.
    ex_ante_vol
        sigma_t, annualized, from `ex_ante_volatility` -- resampled to the
        signal frequency by the caller if the vol was estimated on daily
        data (which is what MOP do).

    Every input must be indexed at the signal frequency and aligned to t.
    """
    sign = tsmom_sign(signal_returns, lookback_periods)
    size = position_size(ex_ante_vol, volatility_target)
    return sign * size * realized_returns


def diversified_tsmom_return(per_instrument: pd.DataFrame) -> pd.Series:
    """MOP p.236's diversified factor: the equal-weighted average across the
    S_t instruments available at t.

        r^{TSMOM}_{t,t+1} = (1/S_t) sum_s r^{TSMOM,s}_{t,t+1}

    S_t is the count of instruments actually available at t, so the mean
    skips NaN rather than treating an absent instrument as a zero return --
    "the St securities that are available at time t" is MOP's own wording.
    """
    return per_instrument.mean(axis=1, skipna=True)
