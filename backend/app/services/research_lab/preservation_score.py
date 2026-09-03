"""PRESERVATION SCORE — a selection score for already-screened cross-sectional
specs that discounts backtested Sharpe for out-of-sample decay, weights it by
this project's own multiple-testing credibility number, and penalizes
drawdown and within-sample Sharpe instability.

WHY THIS EXISTS. Every family in cross_sectional_trial_results is ranked by
raw Sharpe in its own run report, and admitted to forward validation on an
ad-hoc reading of DSR. Neither number says anything about (a) how much of the
backtested edge survives contact with the future, (b) what the path to that
Sharpe looked like, or (c) whether the edge was present throughout the sample
or only in one half of it. This module puts those three into one reproducible
number so candidates can be compared on the same footing.

WHAT IT DELIBERATELY DOES *NOT* CONTAIN: a turnover or holding-period term.
The score is defined without any prior that low-turnover candidates decay
less, precisely so that the question "do low-turnover specs decay less on OUR
data?" can be tested against it rather than assumed into it. See
data/research_runs/run_preservation_score.py, which runs that test. If the
test had come back positive and strong, a holding-period term would have been
justified; it must not be added on prior belief alone.

==============================================================================
THE FORMULA, stated exactly
==============================================================================
Given a spec's realized daily net return series `r` (one observation per
realized trading day, net of the family's own cost model), its persisted
deflation number `dsr`, and `periods_per_year` (252 for equities, 365 for
crypto -- see metrics.CALENDAR_DAYS_PER_YEAR):

    S   = sharpe_ratio(r)                       annualized net Sharpe
    AR  = mean(r) * periods_per_year            annualized ARITHMETIC net return,
                                                built on the same mean as S so
                                                the two are consistent
    MDD = max_drawdown(cumprod(1 + r))          the compounded equity curve's
                                                worst peak-to-trough, <= 0
    C   = AR / max(|MDD|, MDD_FLOOR)            Calmar ratio, floored (below)
    RQ  = sign(S) * sqrt(|S| * |C|)             risk quality: the signed
                                                GEOMETRIC MEAN of Sharpe and
                                                Calmar
    S1  = sharpe_ratio(first  half of r)
    S2  = sharpe_ratio(second half of r)
    stab= clip( min(S1, S2) / |S| , 0, 1 )      stability, 0 if either half
                                                lost money
    cred= clip(dsr, 0, 1)                       credibility

    preservation_score          = OOS_RETENTION * cred * RQ * stab
    preservation_score_no_stab  = OOS_RETENTION * cred * RQ

Every one of those is computed from the spec's own realized return series --
nothing is assumed, estimated by eye, or carried over from another family.

------------------------------------------------------------------------------
(a) OOS_RETENTION = 0.42, and why that number rather than a round 0.5
------------------------------------------------------------------------------
McLean & Pontiff, "Does Academic Research Destroy Stock Return
Predictability?" (Journal of Finance 71(1), 2016, pp. 5-32,
doi:10.1111/jofi.12365) replicate 97 published cross-sectional predictors and
measure two DISTINCT decays against the original in-sample estimate:

  * 26% lower out-of-sample but still PRE-publication -- i.e. pure
    statistical-bias / overfitting decay, before anyone could have traded on
    the paper; and
  * 58% lower POST-publication -- the additional erosion once the result is
    public and being arbitraged.

Which of the two applies to a spec in THIS database is not a free choice. Our
specs are re-implementations of ALREADY-PUBLISHED anomalies (every family
carries a `citation`), run on a cross-section that is public, liquid, and
heavily traded by everyone else who has read the same papers. That places them
at or past McLean & Pontiff's post-publication point, not before it. So the
retention factor is 1 - 0.58 = 0.42, not 1 - 0.26 = 0.74, and not an
unjustified 0.5.

STATED PLAINLY: 0.42 is a CONSTANT multiplier. It therefore changes no
ranking whatsoever -- it exists so the score reads as an expected FORWARD
Sharpe-like quantity rather than as a backtest number, which matters when the
number is compared against a live threshold. All re-ranking in this module
comes from `cred`, `RQ` and `stab`.

WHAT 0.42 IS NOT: it is not a claim that this project's specs will retain
exactly 42%. It is a literature-anchored central estimate applied uniformly,
in place of the implicit 1.00 that ranking on raw Sharpe assumes.

------------------------------------------------------------------------------
(b) The drawdown penalty: why a geometric mean of Sharpe and Calmar
------------------------------------------------------------------------------
Sharpe divides by volatility, which is symmetric and path-blind: two specs
with identical Sharpe can have very different worst losing runs. Calmar
(AR / |MDD|) is exactly the path-aware complement -- but on its own it is a
single-realization statistic driven by one episode, and it is far noisier than
Sharpe. Taking the GEOMETRIC MEAN of the two keeps both concerns and halves
the exponent on each, so a single bad drawdown episode moves the score by the
square root of what it would move a pure Calmar ranking. The signed form keeps
losing specs ordered rather than folding them all onto zero.

MDD_FLOOR = 0.01 (1%) stops a spec whose sample happens to contain no
meaningful drawdown from producing an unbounded Calmar. Any spec that hits the
floor is flagged, never silently rescaled.

------------------------------------------------------------------------------
(c) The stability factor: min-half Sharpe over full Sharpe
------------------------------------------------------------------------------
`stab` asks one blunt question: did the WORSE half of the sample still deliver
the edge? A spec whose weaker half matches the full-sample Sharpe scores 1.0
and is untouched. A spec that made all its money in one half and lost in the
other scores 0.0 and is zeroed out. Everything between scales linearly. The
clip at 1.0 refuses to REWARD a spec whose second half beat the first --
improvement inside a backtest is at least as likely to be luck as to be a
strengthening edge, and paying for it would just be a second selection
dimension.

The halves are the first and second halves of the realized return series by
POSITION, not by calendar: a spec's series already has one observation per
realized trading day, so an equal split is an equal split of the exposure the
spec actually had.

==============================================================================
CAVEATS THAT TRAVEL WITH EVERY NUMBER THIS MODULE PRODUCES
==============================================================================
1. `dsr` is used as a [0, 1] credibility WEIGHT. For several families this
   project's own persisted `dsr` column is explicitly documented as a
   deflation-style SENSITIVITY rather than a Bailey/Lopez de Prado DSR (see
   the `dsr_caveat` key in cross_sectional_trial_results.full_result_json for
   multi_signal_combination). Where that caveat applies to the input, it
   applies to the output.
2. MDD is sample-length dependent. Comparing MDD across families with
   materially different sample lengths compares different amounts of
   opportunity to draw down. Sample length is reported alongside every score
   for exactly this reason.
3. Splitting a sample in half doubles the standard error of each half's
   Sharpe relative to the full sample. `stab` is a coarse screen, not a test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.research_lab.metrics import (
    TRADING_DAYS_PER_YEAR,
    max_drawdown,
    sharpe_ratio,
)

# 1 - 0.58, McLean & Pontiff (2016) post-publication decay. See the module
# docstring for why the post-publication figure and not the 26% pre-publication
# one is the applicable anchor for this project's specs.
OOS_RETENTION = 0.42
MCLEAN_PONTIFF_CITATION = (
    "McLean & Pontiff, 'Does Academic Research Destroy Stock Return Predictability?', "
    "Journal of Finance 71(1), 2016, pp. 5-32, doi:10.1111/jofi.12365 "
    "(26% out-of-sample decay pre-publication; 58% post-publication)"
)

# Floor on |max drawdown| in the Calmar denominator, as a FRACTION (0.01 = 1%).
MDD_FLOOR = 0.01

# A half-sample below this many observations is not scored for stability: the
# half-sample Sharpe would be noise. 126 = half a trading year.
MIN_HALF_OBSERVATIONS = 126


@dataclass(frozen=True)
class PreservationMetrics:
    """Everything the score is built from, kept alongside the score itself so
    a reader can re-derive it without re-running the backtest."""

    n_observations: int
    periods_per_year: float
    sharpe_full: float
    annualized_return: float
    max_drawdown: float  # <= 0
    calmar: float
    mdd_floor_hit: bool
    risk_quality: float
    sharpe_first_half: float | None
    sharpe_second_half: float | None
    sharpe_decay: float | None  # second half MINUS first half
    stability: float
    credibility: float
    preservation_score: float
    preservation_score_no_stab: float

    def as_dict(self) -> dict[str, float | int | bool | None]:
        return {
            "n_observations": self.n_observations,
            "periods_per_year": self.periods_per_year,
            "sharpe_full": self.sharpe_full,
            "annualized_return": self.annualized_return,
            "max_drawdown": self.max_drawdown,
            "calmar": self.calmar,
            "mdd_floor_hit": self.mdd_floor_hit,
            "risk_quality": self.risk_quality,
            "sharpe_first_half": self.sharpe_first_half,
            "sharpe_second_half": self.sharpe_second_half,
            "sharpe_decay": self.sharpe_decay,
            "stability": self.stability,
            "credibility": self.credibility,
            "preservation_score": self.preservation_score,
            "preservation_score_no_stab": self.preservation_score_no_stab,
        }


def equity_curve(returns: pd.Series) -> pd.Series:
    """Compounded equity curve from a daily net-return series, starting at 1.0.

    Compounded rather than cumulative-sum because max drawdown is a
    path/wealth statistic: a summed curve would understate the depth of a
    drawdown that follows a run-up and overstate one that follows a loss."""
    return (1.0 + returns).cumprod()


def split_half_sharpes(
    returns: pd.Series,
    *,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    min_half_observations: int = MIN_HALF_OBSERVATIONS,
) -> tuple[float | None, float | None]:
    """First-half and second-half annualized Sharpe, split by POSITION.

    Returns (None, None) when either half would fall below
    min_half_observations -- a half-sample Sharpe on a handful of days is
    noise, and reporting it as a decay measurement would be fabrication.
    An odd-length series gives the extra observation to the SECOND half."""
    n = len(returns)
    cut = n // 2
    if cut < min_half_observations or (n - cut) < min_half_observations:
        return None, None
    first = returns.iloc[:cut]
    second = returns.iloc[cut:]
    return (
        sharpe_ratio(first, periods_per_year=periods_per_year),
        sharpe_ratio(second, periods_per_year=periods_per_year),
    )


def compute_preservation_metrics(
    returns: pd.Series,
    *,
    dsr: float | None,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    mdd_floor: float = MDD_FLOOR,
    min_half_observations: int = MIN_HALF_OBSERVATIONS,
) -> PreservationMetrics:
    """The whole formula in one call. See the module docstring for the exact
    definition of every term and the justification for every constant.

    `dsr` may be None (no persisted deflation number), in which case
    credibility is 0.0 and the score collapses to 0.0 -- an UNSCORED spec,
    never a silently-full-credit one."""
    if len(returns) == 0:
        raise ValueError("preservation metrics need at least one return observation")

    clean = returns.dropna()
    n = len(clean)
    if n == 0:
        raise ValueError("return series is entirely NaN")

    sharpe_full = sharpe_ratio(clean, periods_per_year=periods_per_year)
    annualized_return = float(clean.mean() * periods_per_year)

    mdd = max_drawdown(equity_curve(clean))
    mdd_abs = abs(mdd)
    mdd_floor_hit = mdd_abs < mdd_floor
    calmar = annualized_return / max(mdd_abs, mdd_floor)

    # Signed geometric mean of Sharpe and Calmar. A sign disagreement between
    # the two (possible only in pathological samples where the arithmetic mean
    # and the compounded path disagree in sign) falls back to the Sharpe's
    # sign, which is the statistic the rest of the project ranks on.
    risk_quality = math.copysign(
        math.sqrt(abs(sharpe_full) * abs(calmar)), sharpe_full if sharpe_full != 0 else 1.0
    )
    if sharpe_full == 0.0:
        risk_quality = 0.0

    s1, s2 = split_half_sharpes(
        clean,
        periods_per_year=periods_per_year,
        min_half_observations=min_half_observations,
    )
    decay = None if (s1 is None or s2 is None) else float(s2 - s1)

    if s1 is None or s2 is None or sharpe_full == 0.0:
        # Unmeasurable stability is NOT free credit: an unscoreable spec keeps
        # the full-formula score at 0 and remains visible in the no-stability
        # variant.
        stability = 0.0
    else:
        stability = float(np.clip(min(s1, s2) / abs(sharpe_full), 0.0, 1.0))

    credibility = 0.0 if dsr is None or not np.isfinite(dsr) else float(np.clip(dsr, 0.0, 1.0))

    base = OOS_RETENTION * credibility * risk_quality
    return PreservationMetrics(
        n_observations=n,
        periods_per_year=periods_per_year,
        sharpe_full=sharpe_full,
        annualized_return=annualized_return,
        max_drawdown=mdd,
        calmar=calmar,
        mdd_floor_hit=mdd_floor_hit,
        risk_quality=risk_quality,
        sharpe_first_half=s1,
        sharpe_second_half=s2,
        sharpe_decay=decay,
        stability=stability,
        credibility=credibility,
        preservation_score=base * stability,
        preservation_score_no_stab=base,
    )


# Holding-period bucket boundary used by the turnover-vs-decay test. 63
# trading days is one quarter -- the natural break in this project's own spec
# grids, which cluster at {5, 7, 10, 20, 21, 30} on one side and {63, 126,
# 252} on the other.
LOW_TURNOVER_MIN_HOLDING_DAYS = 63


def turnover_bucket(holding_days: int | None) -> str | None:
    """"low_turnover" for holding_days >= 63, "high_turnover" below it, None
    when the spec's holding period is unknown (never guessed)."""
    if holding_days is None:
        return None
    return "low_turnover" if holding_days >= LOW_TURNOVER_MIN_HOLDING_DAYS else "high_turnover"
