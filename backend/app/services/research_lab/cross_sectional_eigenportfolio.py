"""PCA / eigenportfolio statistical arbitrage — Avellaneda & Lee (2010),
screened as exactly 12 PRE-DECLARED specs with its own n_trials denominator.

============================================================================
THE SOURCE, AND WHY IT WAS READ RATHER THAN RECALLED
============================================================================
Marco Avellaneda & Jeong-Hyun Lee, "Statistical arbitrage in the US equities
market", Quantitative Finance 10(7), August-September 2010, pp. 761-782,
DOI 10.1080/14697680903124632.

Full text retrieved 2026-08-30 as a PDF from
    https://traders.studentorg.berkeley.edu/papers/
        Statistical%20arbitrage%20in%20the%20US%20equities%20market.pdf
(23 pages, 3.0 MB) and text-extracted locally with pypdf. Every formula and
every constant in this module was read off that extracted text. None of it
was recalled from memory and none of it came from a secondary summary.

That distinction is load-bearing here, not ceremonial. A reputable secondary
source was consulted FIRST — the Hudson & Thames `arbitragelab` PCA-approach
documentation — and it garbles the paper's close-position rules:

    arbitragelab PROSE DOCS ->  "Close a long position if s < +s_bc"  (0.75)
    THE ACTUAL PAPER        ->  "close long position s > -s_sc"       (-0.50)

The docs invert the paper's subscript mapping: the paper attaches s_bc = 0.75
to CLOSE SHORT ("buy to close") and s_sc = 0.50 to CLOSE LONG ("sell to
close"); the docs attach them the other way round. Read literally the docs'
close-long rule fires the instant a long is opened, since a long is opened at
s < -1.25, which is already below +0.75.

CORRECTED 2026-08-30 BY INDEPENDENT VERIFICATION, and the correction is
recorded rather than quietly applied. An earlier draft of this note claimed
the readthedocs page and its GitHub .rst source stated the rule wrongly in
two DIFFERENT ways. Re-retrieving both that day showed they do not: the
rendered page and the .rst are one document and state the same single wrong
rule above. Two further qualifications the earlier note also lacked —
arbitragelab's IMPLEMENTATION (other_approaches/pca_approach.py) is correct
and matches the paper, so the defect is confined to its prose; and the claim
that the docs never state how m is chosen is not relied on here either way.
The substantive point survives all three corrections and is the only one that
motivated reading the primary source: implementing the exit rule from that
prose would have been wrong, with nothing in the output to reveal it. The
paper is therefore the only authority cited below, by its own equation
numbers and section headings.

============================================================================
THE ALGORITHM, AS THE PAPER STATES IT
============================================================================
1. RETURNS PANEL (p.5)
       R_ik = (S_i(t0-(k-1)dt) - S_i(t0-k dt)) / S_i(t0-k dt),  dt = 1/252

2. STANDARDIZED RETURNS (p.5)
       Y_ik = (R_ik - Rbar_i) / sigmabar_i
       sigmabar_i^2 = (1/(M-1)) sum_k (R_ik - Rbar_i)^2

3. CORRELATION MATRIX (paper eq. 8), unit diagonal so trace = N
       rho_ij = (1/(M-1)) sum_k Y_ik Y_jk
   Window, quoted: "In this paper, we always use an estimation window for the
   correlation matrix of one-year (252 trading days) prior to the trading
   date."

4. EIGENPORTFOLIOS (p.5, paper eq. 9) — the volatility weighting is the
   paper's, not an embellishment:
       Q_i^(j) = v_i^(j) / sigmabar_i
       F_jk    = sum_i ( v_i^(j) / sigmabar_i ) R_ik ,   j = 1..m

5. HOW m IS CHOSEN — the paper gives TWO rules and this family uses both:
     (a) section 5.3 "PCA with 15 eigenportfolios" — a FIXED 15. The paper's
         headline PCA specification.
     (b) section 5.4 — a VARIABLE count: retain the top eigenvalues until
         their sum reaches a set percentage of the trace. The paper's worked
         level is 55%.
   The paper's own verdict, quoted: "Back-testing the strategy with 55%
   explained variance shows that the strategy is comparable but slightly
   inferior to taking 15 eigenvectors."

6. FACTOR REGRESSION (Appendix A) over 60 BUSINESS DAYS, T1 = 60/252:
       R^S_n = beta_0 + beta . R^I_n + eps_n ,  n = 1..60
   The cumulative residual
       X_k = sum_{j<=k} eps_j
   satisfies X_60 = 0 exactly — the paper calls this "an artifact of the
   regression, due to the fact that the betas and the residuals are estimated
   using the same sample." This module does NOT hardcode that zero; it uses
   the computed X_60, and a unit test pins that the computed value really is
   ~0. Hardcoding it would hide a genuine regression bug.

7. OU FIT — the discretized AR(1), Appendix A eq. (A1):
       X_{n+1} = a + b X_n + zeta_{n+1} ,  n = 1..59
       kappa    = -log(b) * 252
       m        = a / (1 - b)
       sigma    = sqrt( Var(zeta) * 2 kappa / (1 - b^2) )
       sigma_eq = sqrt( Var(zeta) / (1 - b^2) )

8. S-SCORE (paper eq. 15)
       s = ( X(t) - m ) / sigma_eq
   with the paper's own final refinement, quoted from Appendix A: "The last
   caveat is that we found that centred means work better, so we set
       m = a/(1-b) - < a/(1-b) >,
   where angle brackets denote averaging over different stocks."

9. MEAN-REVERSION SPEED FILTER (section 4), quoted: "We selected stocks with
   mean-reversion times less than 1/2 period (kappa > 252/30 = 8.4)."
   Appendix A adds: "In this case, 0 < b < 0.9672 and the above formulae make
   sense. If b is too close to 1, the mean-reversion time is too long and the
   model is rejected for the stock under consideration."

   A UNITS WARNING, because this is the single easiest thing to misquote about
   this paper: 252/30 is a threshold on the mean-reversion TIME tau = 1/kappa,
   NOT on the half-life.
       kappa > 8.4/yr  <=>  tau < 30 trading days
                       <=>  half-life = ln(2)/kappa < 20.8 trading days
   This module reports the implied half-life as its own separate number and
   never calls 30 days a half-life.

   Section 5 also specifies what happens when the filter fails mid-position:
   "When kappa_i crosses this threshold, we reject the model and (i) do not
   open trades or (ii) close open trades." Both branches are implemented.

10. TRADING RULE (paper eq. 16) — the exact signs, as printed:
        buy to open           if s_i < -s_bo
        sell to open          if s_i > +s_so
        close short position  if s_i < +s_bc
        close long position   if s_i > -s_sc
    with s_bo = s_so = 1.25, s_bc = 0.75, s_sc = 0.50, calibrated by the
    authors on 2000-2004. The paper's prose confirming the asymmetry: "We
    close long trades when the s-score reaches -0.50. Closing short trades
    sooner, at s = 0.75, gives slightly better results than 0.50 in the
    training period of 2000-2002, so we use this slightly asymmetric rule in
    back-testing."
    So a LONG opened at s < -1.25 closes once s recovers above -0.50, and a
    SHORT opened at s > +1.25 closes once s falls below +0.75. This is a
    persistent STATE MACHINE, not a daily cross-sectional re-sort, and it is
    implemented as one.

11. COSTS, as the paper charges them (section 5 PNL equation): "a round-trip
    transaction cost per trade of 10 basis points", entering as
    - sum_i |Q_i(t+dt) - Q_it| * eps with eps = 0.0005, i.e. 5bp ONE-WAY.

WHAT IS DELIBERATELY NOT IMPLEMENTED: the drift-adjusted "modified s-score"
of paper eq. 17. The paper defines it and then declines to back-test it —
"In back-testing simulations, the effect of incorporating a drift in these
time-scales of a few days is minor. Thus, for the sake of brevity, we do not
present back-testing results with the modified s-scores." Implementing an
extension the source itself never tested would be an unsourced addition and
an extra uncounted degree of freedom. Out of scope by pre-declaration.

============================================================================
SURVIVORSHIP — WHAT THE POINT-IN-TIME UNIVERSE FIXES, AND WHAT IT DOES NOT
============================================================================
The traded cross-section on formation date t is exactly
sp500_membership_history.get_universe_as_of(t) — the index's ACTUAL members
that day — intersected with names having usable trailing history. The
candidate pool is get_universe_over(start, end).

ticker_universe.SCREENING_UNIVERSE (a snapshot of TODAY) is NOT used and must
not be. This project has independently rediscovered and fixed that exact
survivorship bug twice already in this session; this family is written not to
be the third.

BUT POINT-IN-TIME MEMBERSHIP ONLY FIXES THE ROSTER, NOT THE PRICES, and that
distinction is the largest single caveat on every number this module prints.
sp500_membership_history's own KNOWN LIMITS record that of the 105 tickers
that were members at some point in the trailing 5 years but are not members
today, yfinance returns NO price history for 50 (48%) — and those 50 are
precisely the acquired/failed names (ATVI, TWTR, SIVB, SBNY, FRC, XLNX,
CERN, ...) whose absence inflates a backtest most. So this module measures
and reports, on EVERY formation date, how many point-in-time members it
actually had usable history for. The residual bias FLATTERS the strategy,
because the missing names are the failures. Closing it needs a delisted-
securities price vendor (Norgate, CRSP, Sharadar) which this project does not
have; that is a known OPEN item on its pending-paid-decisions list and is not
resolved here.

============================================================================
THE 12 SPECS, AND WHY m1 IS IN THE GRID RATHER THAN BESIDE IT
============================================================================
3 factor rules x 2 correlation windows x 2 threshold sets = 12, asserted three
ways in _build_eigen_family() against the pre-declared EIGEN_N_TRIALS, for the
same reason cross_sectional_correlation_risk_premium.py asserts its 15: a
silent drift in family size silently changes the DSR denominator.

  FACTOR RULES
    pca15  m = 15 fixed                       paper section 5.3
    var55  m = smallest k reaching 55% of tr  paper section 5.4
    m1     m = 1                              THE CONTROL

  m1 projects out only the FIRST eigenportfolio — the market mode — so it is
  plain market-neutral residual reversion with none of the multi-factor
  structure the paper's PCA approach is actually about. If m1 matches or beats
  pca15 and var55, then the entire eigenportfolio apparatus contributes
  nothing over a simple market hedge and this family's thesis is unsupported
  by its own results. It sits IN the grid and IN n_trials, costing a trial
  exactly like a hypothesis spec, rather than being reported alongside as a
  free extra — the same discipline the correlation-risk-premium family applies
  to its `vix_level` control.

  CORRELATION WINDOWS: 252 (the paper's own, and its only one) and 126 (a
  pre-declared robustness halving, not a searched value).

  THRESHOLD SETS: `paper` = (1.25, 1.25, 0.75, 0.50), exactly eq. 16; `wide` =
  (1.50, 1.50, 0.75, 0.50), which opens later and exits identically.

  HELD FIXED, NEVER SEARCHED: the 60-day regression window, the 8.4 kappa
  floor, the centered cross-sectional mean, and DIRECTION. Direction is
  contrarian (+1) uniformly across all 12 specs. Letting each spec pick its
  own sign would double the real search to 24 while still reporting
  n_trials = 12 — the exact uncounted-degree-of-freedom failure the DSR
  exists to prevent. Specs whose true sign is the opposite print negative
  Sharpes here and are NOT flipped.

============================================================================
PORTFOLIO CONSTRUCTION, AND WHY THE HEADLINE COST IS HARSHER THAN THE PAPER'S
============================================================================
A position earns its own return minus its fitted factor exposure,
R_i(t+1) - sum_j beta_ij F_j(t+1) — exactly the paper's "buying one dollar of
the corresponding stock and selling beta_i1 dollars of ETF #1, ... beta_im
dollars of ETF #m", with eigenportfolios in place of ETFs. Because
eigenportfolio #1 IS the market mode, the market hedge is already inside this
construction, so the paper's additional daily SPY overlay is not applied;
realized SPY beta is MEASURED per spec instead, where it doubles as the
static-tilt check.

THE FULL BOOK. The stock legs are not the whole portfolio. Each position
carries a hedge of -sum_j beta_ij Q^(j), and each eigenportfolio Q^(j) is
itself a vector of weights in the SAME stocks — so the hedge legs are real
positions that must be rebalanced as betas and eigenvectors move, every single
day. The paper charges turnover only on its stock leg, |Q_i(t+dt) - Q_it|.
This module maps the hedge back into stock space,

        book = w - Qmat @ (beta^T w)

normalizes so the FULL book's gross notional sum|book| = 1.0 each date, and
charges turnover on THAT. The paper-convention stock-legs-only turnover is
also computed and reported per spec, so the gap between the two is visible
rather than assumed away. Returns are therefore per dollar of gross capital
actually deployed, matching this codebase's existing normalization convention
(ou_pairs.realize_pairs_return divides by 1 + |hedge_ratio| for exactly this
reason). This choice can only make the reported result WORSE than the paper's
convention; it is made deliberately, in advance, in the conservative
direction.

Note that beta and Qmat are individually scale-dependent (v is unit-L2 and is
divided by sigma, so Qmat's gross notional is arbitrary) but their PRODUCT is
not: F_j is a dollar P&L of the holding Qmat[:,j], so beta_ij * Qmat[:,j] is
invariant to how Qmat is scaled. The book above is therefore well-defined.

COSTS. EIGEN_COST_BPS = 5.0 one-way — the paper's own eps = 0.0005, adopted
unchanged so the headline is directly comparable to the source. This is a
DAILY-rebalanced book, so cost is the most load-bearing assumption in the
whole exercise; hence a pre-declared sensitivity at 5/10/20bp on the identical
position path, and a breakeven multiple per spec.

THE EDGE CROSS-CHECK ON THAT 5bp, which the pre-registration required and an
earlier version of this module only DESCRIBED. This project's own per-ticker
cost model (spread_estimator.build_edge_half_spread_frame — Ardia, Guidotti &
Kroencke, JFE 2024, via the `bidask` package) is imported and CALLED, not
merely cited: summarize_edge_half_spreads() runs it over the point-in-time
traded cross-section and reports the realized distribution of one-way
half-spreads beside the flat assumption. It is a DIAGNOSTIC and never the
headline — the flat 5bp is the paper's own number and keeping it is what makes
the comparison to the source exact — but it is the number that says which
column of the sensitivity table a reader should actually believe. If the OHLC
fetch fails, the summary carries a status string saying so and the report
prints it: a stated limitation, never a silent skip.

READ ITS OUTPUT WITH THE ESTIMATOR'S OWN KNOWN BIAS IN HAND. spread_estimator
documents, from this project's synthetic-recovery test, that EDGE is biased
UPWARD in precisely the tightest large-cap regime this universe lives in (a
true 10bp spread recovering as ~21bp at a 21-day window; the 63-day window
used here reduces but does not eliminate it). So the EDGE figure is an UPPER
bound on the true cost, not a point estimate, and the honest reading is
directional: it says the flat 5bp sits at the OPTIMISTIC end of the plausible
range, which is why the pre-declared 10bp and 20bp columns exist.

FINANCING. EIGEN_FINANCING_BPS_PER_YEAR = 50.0 on the SHORT side of the full
book only, accrued on calendar days / 365 — this project's existing
dollar-neutral convention (vol_regime_timing's 50bp for a self-financing
two-legged book, as against the correlation-risk-premium family's 100bp for an
outright position that must be funded). It is a DISCLOSED BLENDED ASSUMPTION,
not a sourced borrow quote; a real securities-borrow feed is a known open
paid-data item here. It is plausible general collateral for large caps and is
NOT plausible for hard-to-borrow names, so it FLATTERS the short book.

============================================================================
WHAT COULD MAKE A POSITIVE RESULT HERE FAKE — CHECKED IN-MODULE
============================================================================
 1. A DISGUISED STATIC MARKET TILT. Every spec reports spy_beta and the
    Sharpe of the BETA-HEDGED stream y - beta*x. Deliberately not the OLS
    residual y - alpha - beta*x, whose mean is zero by construction and would
    report every strategy ever measured as a pure tilt; and guarded against
    the degenerate case where the hedge explains everything, which this
    project has already been bitten by once (an unguarded version printed a
    confident -0.836 on a stream mathematically identical to its benchmark).
 2. BEING SHORT-TERM REVERSAL IN A LAB COAT. The single most likely way this
    family is fooling itself: a contrarian book on residuals is close kin to
    plain cross-sectional reversal, which is a long-known and largely
    cost-arbitraged effect. compute_reversal_overlap() measures corr(spec
    daily returns, a plain 5-day cross-sectional reversal book on the SAME
    universe with the SAME costs) and reports SUSPECT above a pre-declared
    |corr| > 0.7, whatever the Sharpe says. The reversal book is a diagnostic
    and is NOT in n_trials, because it is not a variant of this family's
    signal — it is the thing this family must be shown not to be.
 3. ONE-DISLOCATION DEPENDENCE. subperiod_sharpes in three equal thirds.
 4. DAILY-n OVERSTATING INDEPENDENT INFORMATION. Positions persist for many
    days under the state machine, so the daily count overstates independent
    bets. vol_regime_timing.block_bootstrap_sharpe_pvalue is IMPORTED (not
    reimplemented, so it means the same thing it means in sibling families)
    with block length 21. Where it disagrees with the DSR, believe it.
 5. THE SEARCH THAT LED HERE IS NOT IN n_trials. 12 is the size of THIS
    family, fixed before any return was computed. It does not cover the
    literature scan that nominated Avellaneda-Lee, nor the ~12 other families
    this project has screened. The true multiple-comparisons burden is
    strictly larger than 12, so every DSR here is an UPPER BOUND on the
    honest one.

RESIDUAL BIASES NOT FIXED, ONLY DISCLOSED: delisted-name price coverage
(above, the big one); formation assumed executable at the exact closing print;
no market-impact model, cost linear in traded notional at a flat rate, which
is optimistic for a book rebalancing hundreds of names daily; no
borrow-availability constraint; the sample starts 2015-01-07 so it contains no
2008-style crisis, while the paper's strongest PCA years (2000-2002, 2004) all
predate it; yfinance's split/dividend adjustment taken as given.

The full pre-registration, written before this module existed, is checked in at
backend/data/research_runs/eigenportfolio_statarb_PREREGISTRATION.txt.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.deflated_sharpe import (
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
from app.services.research_lab.spread_estimator import (
    COST_MODEL_WINDOW_DAYS,
    build_edge_half_spread_frame,
)
from app.services.research_lab.vol_regime_timing import (
    FINANCING_DAYS_PER_YEAR,
    MIN_REPLAY_TRADING_DAYS,
    block_bootstrap_sharpe_pvalue,
)
from app.services.risk.beta import compute_beta

logger = logging.getLogger(__name__)


# --- citation --------------------------------------------------------------

AVELLANEDA_LEE_CITATION = (
    "Avellaneda & Lee, 'Statistical arbitrage in the US equities market', Quantitative Finance "
    "10(7), 2010, pp. 761-782, DOI 10.1080/14697680903124632. Full text read 2026-08-30 from "
    "traders.studentorg.berkeley.edu/papers/Statistical%20arbitrage%20in%20the%20US%20equities"
    "%20market.pdf and text-extracted with pypdf; every formula and constant below is quoted "
    "from that text, not from a secondary summary (two secondary sources were checked first and "
    "BOTH stated the paper's close-position rules incorrectly, in different ways)."
)

REVERSAL_CONTROL_CITATION = (
    "Lehmann, 'Fads, Martingales, and Market Efficiency', Quarterly Journal of Economics 105(1), "
    "1990, and Lo & MacKinlay, 'When Are Contrarian Profits Due to Stock Market Overreaction?', "
    "Review of Financial Studies 3(2), 1990 — short-horizon cross-sectional return reversal. The "
    "diagnostic this family must be shown NOT to be: a contrarian book on residuals is close kin "
    "to plain reversal, which is long-known and largely cost-arbitraged."
)


# --- paper constants -------------------------------------------------------

# Paper p.5: "we always use an estimation window for the correlation matrix of
# one-year (252 trading days) prior to the trading date." 126 is this family's
# single pre-declared robustness halving, not a searched value.
EIGEN_CORRELATION_WINDOWS: tuple[int, ...] = (252, 126)

# Paper section 4: "We considered an estimation window of 60 business days,
# i.e. T1 = 60/252." Fixed, never searched.
EIGEN_REGRESSION_WINDOW = 60

# Paper section 4: "We selected stocks with mean-reversion times less than 1/2
# period (kappa > 252/30 = 8.4)." A threshold on the mean-reversion TIME
# 1/kappa, NOT on the half-life — see the module docstring's units warning.
EIGEN_KAPPA_FLOOR = 252.0 / 30.0

# Appendix A's own restatement of the same filter in AR(1) space: "In this
# case, 0 < b < 0.9672". Derived here rather than hardcoded so the two can
# never drift apart, and pinned against the paper's printed 0.9672 by a test.
EIGEN_B_CEILING = float(np.exp(-EIGEN_KAPPA_FLOOR / TRADING_DAYS_PER_YEAR))

# Paper section 5.3 ("PCA with 15 eigenportfolios") and section 5.4 (variable
# count reaching a set percentage of the trace; the paper's worked level).
EIGEN_PCA_FIXED_COUNT = 15
EIGEN_VARIANCE_THRESHOLD = 0.55

# Paper eq. 16, calibrated by the authors on 2000-2004.
PAPER_S_BO = 1.25
PAPER_S_SO = 1.25
PAPER_S_BC = 0.75
PAPER_S_SC = 0.50

# Paper section 5 PNL equation: eps = 0.0005, described as "a round-trip
# transaction cost per trade of 10 basis points" — i.e. 5bp one-way.
EIGEN_COST_BPS = 5.0


# --- this family's own pre-declared parameters -----------------------------

# See PREREGISTRATION.txt AMENDMENT 1, written before the module existed: a
# fixed 60-observation regression fitting m factors plus an intercept leaves
# 60 - m - 1 residual degrees of freedom, and the var55 rule chooses m from
# data. Below this floor the regression saturates and the OU fit returns
# confident-looking garbage instead of failing. A violating (date, spec)
# produces NO tradeable s-scores — open positions close, none open — and is
# COUNTED, rather than m being silently capped, which would quietly turn
# var55 into pca15 and misreport the family's real size.
EIGEN_MIN_RESIDUAL_DOF = 20

# A PCA cross-section thinner than this cannot support 15 eigenportfolios
# meaningfully.
EIGEN_MIN_NAMES = 50

# On the SHORT side of the full book only, calendar-day accrued. This project's
# dollar-neutral convention. A DISCLOSED BLENDED ASSUMPTION, not a borrow quote.
EIGEN_FINANCING_BPS_PER_YEAR = 50.0

# Identical position path, three cost levels. Pre-declared so the reader sees
# the whole cost picture rather than the one number that flatters most.
EIGEN_COST_SENSITIVITY_BPS: tuple[float, ...] = (5.0, 10.0, 20.0)

# The diagnostic this family must be shown not to be. Pre-declared threshold.
EIGEN_REVERSAL_LOOKBACK = 5
EIGEN_REVERSAL_OVERLAP_THRESHOLD = 0.7

# Positions persist across many days under the state machine, so the daily n
# overstates independent bets. Same register as the sibling families' choices.
EIGEN_BOOTSTRAP_BLOCK_DAYS = 21

# Point-in-time membership coverage begins here; formations cannot precede it.
EIGEN_FORMATION_START = MEMBERSHIP_DATA_START

# ~345 trading days, comfortably warming the 252-day correlation window.
# Formations never occur inside the padding.
EIGEN_HISTORY_PADDING_CALENDAR_DAYS = 500

EIGEN_N_TRIALS = 12

EIGEN_DIRECTION = 1.0

# When a beta-hedged stream's sd falls to this fraction of the original's, the
# hedge has explained everything and what is left is floating-point dust, not a
# residual. Same constant and same reasoning as the correlation-risk-premium
# family's RESIDUAL_DEGENERACY_RATIO.
RESIDUAL_DEGENERACY_RATIO = 1e-8


# --- numerical core: standardization, PCA, OU ------------------------------


def standardize_returns(window: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Paper p.5: Y_ik = (R_ik - Rbar_i)/sigmabar_i with sigmabar_i the ddof=1
    sample sd. `window` is (M observations, N names); returns (Y, sigmabar).

    ddof=1 is the paper's own definition (its sigmabar^2 carries 1/(M-1)), and
    it is the same ddof the correlation formula in eq. 8 assumes — using the
    population sd here would make rho's diagonal differ from 1."""
    sigma = window.std(axis=0, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        standardized = (window - window.mean(axis=0)) / sigma
    return standardized, sigma


def correlation_from_standardized(standardized: np.ndarray) -> np.ndarray:
    """Paper eq. 8: rho_ij = (1/(M-1)) sum_k Y_ik Y_jk. Written as the paper
    writes it rather than calling np.corrcoef, so the unit diagonal is a
    property of the arithmetic on THESE standardized returns rather than of a
    library re-standardizing them behind our back."""
    n_obs = standardized.shape[0]
    return standardized.T @ standardized / (n_obs - 1)


def select_n_factors(
    eigenvalues: np.ndarray, rule: str, *, variance_threshold: float = EIGEN_VARIANCE_THRESHOLD
) -> int:
    """How many eigenportfolios to retain, by the paper's OWN two rules.

    `eigenvalues` must be sorted DESCENDING.

    "pca15" — paper section 5.3, a fixed 15 (clipped to the cross-section size).
    "var55" — paper section 5.4: "we retain a certain number of eigenportfolios
              (factors) such that the sum of the corresponding eigenvectors is
              equal to a set percentage of the trace of the correlation
              matrix." The trace of a correlation matrix is N, and equals the
              eigenvalue sum; the sum is used so a numerically imperfect
              diagonal cannot shift the answer.
    "m1"    — THE CONTROL: the market mode only.
    """
    n_names = len(eigenvalues)
    if rule == "m1":
        return 1
    if rule == "pca15":
        return min(EIGEN_PCA_FIXED_COUNT, n_names)
    if rule == "var55":
        total = float(eigenvalues.sum())
        if total <= 0:
            return 1
        cumulative = np.cumsum(eigenvalues) / total
        # +1 converts a 0-based index into a COUNT of retained factors.
        return int(np.searchsorted(cumulative, variance_threshold) + 1)
    raise ValueError(f"unknown factor rule {rule!r}; expected one of pca15, var55, m1")


@dataclass(frozen=True)
class OuFit:
    """One cross-section's vectorized AR(1)/OU fit. Every array is per-name and
    shares one order; `valid` is the mask of names the paper's own rules allow
    to be traded (finite fit, 0 < b < 0.9672 i.e. kappa > 8.4)."""

    a: np.ndarray
    b: np.ndarray
    kappa: np.ndarray
    m_raw: np.ndarray
    m_centered: np.ndarray
    sigma_eq: np.ndarray
    s_score: np.ndarray
    valid: np.ndarray


def fit_ou_ar1(cumulative_residuals: np.ndarray) -> OuFit:
    """Appendix A eq. (A1), fitted per column and vectorized across the whole
    cross-section at once.

        X_{n+1} = a + b X_n + zeta_{n+1}
        kappa = -log(b)*252,  m = a/(1-b),  sigma_eq = sqrt(Var(zeta)/(1-b^2))
        s = (X(t) - m)/sigma_eq        [paper eq. 15]

    `cumulative_residuals` is (60 rows, N names) — the X_k of Appendix A.

    NUMERICAL CONVENTIONS, matched to this project's existing OU code
    (ou_pairs.fit_ou_pairs_window) rather than reinvented:
      * Var(zeta) uses ddof=2 because a and b are both estimated from the same
        sample — ou_pairs uses exactly this for exactly this reason.
      * The validity mask requires 0 < b < 1 before taking log(b), the same
        degenerate-fit guard ou_pairs applies. ou_pairs stops there because a
        pair only needs stationarity; this module additionally imposes the
        paper's OWN kappa > 8.4 speed filter, which is strictly tighter
        (b < 0.9672).
      * A zero-variance column (a name whose cumulative residual never moves)
        has Sxx = 0 and is excluded rather than producing a divide-by-zero.

    THE CENTERED MEAN is the paper's own final choice, Appendix A: "we found
    that centred means work better, so we set m = a/(1-b) - <a/(1-b)>, where
    angle brackets denote averaging over different stocks." The average is
    taken over the VALID names only — those are the names the paper would
    actually be trading and scoring on that date, and letting a rejected,
    near-unit-root fit (whose a/(1-b) can be enormous) into the cross-sectional
    mean would drag every other name's s-score with it.
    """
    x_lag = cumulative_residuals[:-1]
    x_next = cumulative_residuals[1:]
    n_obs = x_lag.shape[0]

    x_mean = x_lag.mean(axis=0)
    y_mean = x_next.mean(axis=0)
    x_centered = x_lag - x_mean
    sxx = (x_centered * x_centered).sum(axis=0)
    sxy = (x_centered * (x_next - y_mean)).sum(axis=0)

    with np.errstate(invalid="ignore", divide="ignore"):
        b = np.where(sxx > 0, sxy / np.where(sxx > 0, sxx, 1.0), np.nan)
        a = y_mean - b * x_mean
        residual = x_next - (a + b * x_lag)
        # ddof=2: a and b are both estimated from this same sample.
        var_zeta = (residual * residual).sum(axis=0) / max(n_obs - 2, 1)

        finite_fit = np.isfinite(b) & np.isfinite(a) & (sxx > 0)
        # 0 < b < 1 is the stationarity/degeneracy guard; b < EIGEN_B_CEILING
        # is the paper's own kappa > 252/30 speed filter, and is tighter.
        speed_ok = finite_fit & (b > 0.0) & (b < EIGEN_B_CEILING)

        safe_b = np.where(speed_ok, b, 0.5)
        kappa = np.where(speed_ok, -np.log(safe_b) * TRADING_DAYS_PER_YEAR, np.nan)
        m_raw = np.where(speed_ok, a / (1.0 - safe_b), np.nan)
        sigma_eq = np.where(
            speed_ok, np.sqrt(np.maximum(var_zeta, 0.0) / (1.0 - safe_b**2)), np.nan
        )

    valid = speed_ok & np.isfinite(sigma_eq) & (sigma_eq > 0) & np.isfinite(m_raw)

    m_centered = np.full_like(m_raw, np.nan)
    s_score = np.full_like(m_raw, np.nan)
    if valid.any():
        centre = float(np.mean(m_raw[valid]))
        m_centered[valid] = m_raw[valid] - centre
        # X(t) is the LAST cumulative residual. The paper notes it is exactly
        # zero by construction and simplifies s to -m/sigma_eq; the computed
        # value is used here instead, so that a genuine regression bug would
        # show up as a non-zero X_60 rather than being hidden by a hardcoded 0.
        x_last = cumulative_residuals[-1]
        s_score[valid] = (x_last[valid] - m_centered[valid]) / sigma_eq[valid]

    return OuFit(
        a=a,
        b=b,
        kappa=kappa,
        m_raw=m_raw,
        m_centered=m_centered,
        sigma_eq=sigma_eq,
        s_score=s_score,
        valid=valid,
    )


def implied_half_life_days(kappa: np.ndarray | float) -> np.ndarray | float:
    """ln(2)/kappa expressed in TRADING days. Exists so that the paper's
    mean-reversion TIME threshold (1/kappa < 30 days) is never accidentally
    reported as a half-life — see the module docstring's units warning."""
    return np.log(2.0) / np.asarray(kappa, dtype=float) * TRADING_DAYS_PER_YEAR


# --- one formation date's signal -------------------------------------------


@dataclass(frozen=True)
class CrossSectionSignal:
    """Everything one formation date produces for ONE factor rule."""

    tickers: tuple[str, ...]
    n_factors: int
    s_score: np.ndarray
    kappa: np.ndarray
    tradeable: np.ndarray
    # (N, m) factor loadings and eigenportfolio weights — the two objects the
    # book construction needs. Their individual scales are arbitrary; their
    # product is not (see the module docstring).
    betas: np.ndarray
    eigen_weights: np.ndarray
    residual_return_next: np.ndarray
    variance_explained: float
    dof_ok: bool


def build_cross_section_signal(
    window: np.ndarray,
    next_returns: np.ndarray,
    tickers: tuple[str, ...],
    rule: str,
    *,
    regression_window: int = EIGEN_REGRESSION_WINDOW,
    min_residual_dof: int = EIGEN_MIN_RESIDUAL_DOF,
    precomputed: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
) -> CrossSectionSignal:
    """The whole per-date pipeline for one factor rule: standardize -> PCA ->
    eigenportfolios -> 60-day factor regression -> cumulative residual -> OU
    fit -> s-score, plus the next-day residual return each open position earns.

    `window` is (M, N) trailing returns ENDING at the formation date inclusive,
    so everything here is knowable at that date's close. `next_returns` is the
    (N,) vector of the FOLLOWING day's returns, used only to value positions
    and never to form them.

    `precomputed` carries (standardized, sigma, eigendecomposition) so the
    three factor rules sharing one correlation window pay for the eigen-
    decomposition once instead of three times. It is an optimization only: the
    default path recomputes it and a test pins that both paths agree.
    """
    if precomputed is None:
        standardized, sigma = standardize_returns(window)
        rho = correlation_from_standardized(standardized)
        eigenvalues, eigenvectors = np.linalg.eigh(rho)
        eigenvalues = eigenvalues[::-1]
        eigenvectors = eigenvectors[:, ::-1]
    else:
        sigma, eigenvalues, eigenvectors = precomputed

    n_factors = select_n_factors(eigenvalues, rule)
    total_variance = float(eigenvalues.sum())
    variance_explained = (
        float(eigenvalues[:n_factors].sum() / total_variance) if total_variance > 0 else 0.0
    )

    # Paper eq. 9: Q_i^(j) = v_i^(j)/sigmabar_i, and F_jk = sum_i Q_i^(j) R_ik.
    eigen_weights = eigenvectors[:, :n_factors] / sigma[:, None]

    regression_returns = window[-regression_window:]
    factor_returns = regression_returns @ eigen_weights  # (60, m)

    n_names = window.shape[1]
    dof = regression_window - n_factors - 1
    if dof < min_residual_dof:
        # Not enough residual degrees of freedom for the OU fit to mean
        # anything — see PREREGISTRATION AMENDMENT 1. Nothing is tradeable on
        # this date for this rule, and the caller counts it.
        empty = np.full(n_names, np.nan)
        return CrossSectionSignal(
            tickers=tickers,
            n_factors=n_factors,
            s_score=empty,
            kappa=empty,
            tradeable=np.zeros(n_names, dtype=bool),
            betas=np.zeros((n_names, n_factors)),
            eigen_weights=eigen_weights,
            residual_return_next=np.zeros(n_names),
            variance_explained=variance_explained,
            dof_ok=False,
        )

    # Appendix A: R^S_n = beta_0 + beta . R^I_n + eps_n, n = 1..60, solved for
    # every stock at once. lstsq on a (60, m+1) design shared by all columns.
    design = np.column_stack([np.ones(regression_window), factor_returns])
    coefficients, *_ = np.linalg.lstsq(design, regression_returns, rcond=None)
    residuals = regression_returns - design @ coefficients
    betas = coefficients[1:].T  # (N, m)

    # Appendix A: X_k = sum_{j<=k} eps_j.
    cumulative_residuals = np.cumsum(residuals, axis=0)
    fit = fit_ou_ar1(cumulative_residuals)

    # Paper: "long $1 in the stock and short beta_ij dollars in the jth
    # factor" — so a unit long earns the stock's return net of its fitted
    # factor exposure, valued with the NEXT day's factor returns.
    next_factor_returns = next_returns @ eigen_weights
    residual_return_next = next_returns - betas @ next_factor_returns

    return CrossSectionSignal(
        tickers=tickers,
        n_factors=n_factors,
        s_score=fit.s_score,
        kappa=fit.kappa,
        tradeable=fit.valid,
        betas=betas,
        eigen_weights=eigen_weights,
        residual_return_next=residual_return_next,
        variance_explained=variance_explained,
        dof_ok=True,
    )


# --- the trading rule ------------------------------------------------------


@dataclass(frozen=True)
class ThresholdSet:
    """Paper eq. 16's four cutoffs. `key` names the pre-declared set."""

    key: str
    s_bo: float
    s_so: float
    s_bc: float
    s_sc: float


PAPER_THRESHOLDS = ThresholdSet("paper", PAPER_S_BO, PAPER_S_SO, PAPER_S_BC, PAPER_S_SC)
WIDE_THRESHOLDS = ThresholdSet("wide", 1.50, 1.50, PAPER_S_BC, PAPER_S_SC)

EIGEN_THRESHOLD_SETS: tuple[ThresholdSet, ...] = (PAPER_THRESHOLDS, WIDE_THRESHOLDS)


def next_position(current: int, s_score: float, thresholds: ThresholdSet) -> int:
    """Paper eq. 16, as a state transition. The exact signs, as printed:

        buy to open           if s < -s_bo        ->  +1
        sell to open          if s > +s_so        ->  -1
        close short position  if s < +s_bc        ->   0
        close long position   if s > -s_sc        ->   0

    A position is HELD whenever no rule fires — that persistence is the whole
    point of the rule and is why this is a state machine rather than a daily
    re-sort. Confirmed against the paper's own prose: "We close long trades
    when the s-score reaches -0.50. Closing short trades sooner, at s = 0.75."
    """
    if not np.isfinite(s_score):
        return 0
    if current > 0:
        return 0 if s_score > -thresholds.s_sc else 1
    if current < 0:
        return 0 if s_score < thresholds.s_bc else -1
    if s_score < -thresholds.s_bo:
        return 1
    if s_score > thresholds.s_so:
        return -1
    return 0


# --- specs -----------------------------------------------------------------

_FACTOR_RULES: tuple[tuple[str, str, bool], ...] = (
    (
        "pca15",
        "Paper section 5.3, the headline PCA specification: a FIXED 15 eigenportfolios.",
        True,
    ),
    (
        "var55",
        (
            "Paper section 5.4: a VARIABLE count, the top eigenvalues summing to 55% of the "
            "trace. The paper's own verdict is that this is 'comparable but slightly inferior' "
            "to taking 15."
        ),
        True,
    ),
    (
        "m1",
        (
            "CONTROL: the market mode ONLY. Plain market-neutral residual reversion with none "
            "of the multi-factor structure. If this matches pca15/var55, the eigenportfolio "
            "apparatus adds nothing over a market hedge and this family's thesis is unsupported "
            "by its own results."
        ),
        False,
    ),
)


@dataclass(frozen=True)
class EigenSpec:
    spec_id: str
    factor_rule: str
    correlation_window: int
    thresholds: ThresholdSet
    hypothesis: str
    is_eigen_hypothesis: bool
    citation: str = AVELLANEDA_LEE_CITATION
    regression_window: int = EIGEN_REGRESSION_WINDOW
    direction: float = EIGEN_DIRECTION


@dataclass
class EigenConfig:
    cost_bps: float = EIGEN_COST_BPS
    financing_bps_per_year: float = EIGEN_FINANCING_BPS_PER_YEAR
    formation_start: date = EIGEN_FORMATION_START
    min_names: int = EIGEN_MIN_NAMES


def default_eigen_config() -> EigenConfig:
    """This family's cost configuration, as a FUNCTION rather than a module
    singleton so callers cannot mutate shared state — the same reason
    default_crp_config() is one."""
    return EigenConfig()


def _build_eigen_family() -> list[EigenSpec]:
    """The exact product _FACTOR_RULES x EIGEN_CORRELATION_WINDOWS x
    EIGEN_THRESHOLD_SETS. The literal length of this list is the n_trials
    denominator — every definition counts, whether or not it survives the data
    floors, because shrinking the denominator to "specs that worked" would be
    gameable by declaring specs expected to fail."""
    specs = [
        EigenSpec(
            spec_id=f"eig_{rule}_c{window}_{thresholds.key}",
            factor_rule=rule,
            correlation_window=window,
            thresholds=thresholds,
            hypothesis=hypothesis,
            is_eigen_hypothesis=is_hypothesis,
        )
        for rule, hypothesis, is_hypothesis in _FACTOR_RULES
        for window in EIGEN_CORRELATION_WINDOWS
        for thresholds in EIGEN_THRESHOLD_SETS
    ]

    expected = len(_FACTOR_RULES) * len(EIGEN_CORRELATION_WINDOWS) * len(EIGEN_THRESHOLD_SETS)
    assert len(specs) == expected == EIGEN_N_TRIALS, (
        f"eigenportfolio family built {len(specs)} definitions; the grid "
        f"({len(_FACTOR_RULES)} factor rules x {len(EIGEN_CORRELATION_WINDOWS)} correlation "
        f"windows x {len(EIGEN_THRESHOLD_SETS)} threshold sets) implies {expected}; the "
        f"pre-declared EIGEN_N_TRIALS is {EIGEN_N_TRIALS}. All three must agree — a drift here "
        "silently changes the DSR's multiple-comparisons denominator for every future run."
    )
    assert len({s.spec_id for s in specs}) == len(specs), "spec_ids must be unique"
    assert all(s.direction == EIGEN_DIRECTION for s in specs), (
        "every spec trades the single pre-declared contrarian direction — a per-spec sign would "
        "double the real search to 24 while still reporting n_trials=12"
    )
    assert all(s.regression_window == EIGEN_REGRESSION_WINDOW for s in specs), (
        "the 60-day regression window is the paper's and is fixed; searching it would multiply "
        "the family size and the DSR denominator"
    )
    assert sum(1 for s in specs if s.factor_rule == "m1") == (
        len(EIGEN_CORRELATION_WINDOWS) * len(EIGEN_THRESHOLD_SETS)
    ), (
        "the m1 control must exist at EVERY window/threshold combination — it is the "
        "like-for-like comparison that decides whether the multi-factor structure earns its "
        "keep, and a missing cell would leave a hypothesis spec with no counterpart"
    )
    return specs


EIGEN_FAMILY: list[EigenSpec] = _build_eigen_family()


# --- panel -----------------------------------------------------------------


@dataclass(frozen=True)
class EigenPanel:
    """Daily returns for the survivorship-free candidate pool, plus each date's
    POINT-IN-TIME membership mask.

    `member_mask` is (dates x tickers) booleans: True where that ticker was an
    actual S&P 500 constituent on that date, per
    sp500_membership_history.get_universe_as_of. It is the whole reason this
    family is not survivorship-biased in its roster — and, as the module
    docstring says at length, it does nothing about missing PRICES for names
    that delisted."""

    returns: pd.DataFrame
    member_mask: pd.DataFrame
    n_members_by_date: pd.Series

    def __post_init__(self) -> None:
        if not self.returns.index.equals(self.member_mask.index):
            raise ValueError("returns and member_mask must share an identical index")
        if not self.returns.columns.equals(self.member_mask.columns):
            raise ValueError("returns and member_mask must share identical columns")


def build_eigen_panel(closes: pd.DataFrame) -> EigenPanel:
    """Closes -> daily simple returns plus the point-in-time membership mask.

    A date the membership module cannot answer for (before its coverage, or
    after it) gets an ALL-FALSE mask rather than a guessed one: the resulting
    cross-section falls below EIGEN_MIN_NAMES and the date is skipped and
    counted, which is the honest handling. Silently substituting today's
    membership there is exactly the survivorship bug this module exists not to
    reintroduce."""
    returns = closes.sort_index().pct_change()
    mask = pd.DataFrame(False, index=returns.index, columns=returns.columns)
    n_members: dict[pd.Timestamp, int] = {}
    columns = list(returns.columns)
    position = {ticker: i for i, ticker in enumerate(columns)}
    values = np.zeros((len(returns.index), len(columns)), dtype=bool)

    for row, stamp in enumerate(returns.index):
        try:
            members = get_universe_as_of(stamp.date())
        except PointInTimeUniverseError:
            n_members[stamp] = 0
            continue
        n_members[stamp] = len(members)
        for ticker in members:
            index = position.get(ticker)
            if index is not None:
                values[row, index] = True

    mask.loc[:, :] = values
    return EigenPanel(
        returns=returns,
        member_mask=mask,
        n_members_by_date=pd.Series(n_members).sort_index(),
    )


# --- replay ----------------------------------------------------------------


@dataclass(frozen=True)
class FormationRecord:
    formation_date: date
    n_members: int
    n_usable: int
    n_factors: int
    variance_explained: float
    n_tradeable: int
    n_long: int
    n_short: int
    gross_before_normalization: float
    full_book_turnover: float
    stock_leg_turnover: float
    cost: float
    skipped_reason: str | None = None


@dataclass
class EigenBacktestResult:
    spec_id: str
    status: str
    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    gross_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    net_exposure: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    formations: list[FormationRecord] = field(default_factory=list)
    total_cost: float = 0.0
    total_financing_cost: float = 0.0
    total_full_book_turnover: float = 0.0
    total_stock_leg_turnover: float = 0.0
    n_dof_skipped: int = 0
    n_thin_skipped: int = 0
    n_missing_next_return: int = 0
    median_kappa: float | None = None
    median_n_factors: float | None = None


class _BookState:
    """One spec's persistent position state machine plus its last full book.

    Kept as a small class rather than a tuple of dicts because the replay loop
    carries six of these at once (three factor rules x two threshold sets per
    correlation window) and the bookkeeping is easy to get subtly wrong when it
    is spread across parallel dictionaries."""

    def __init__(self) -> None:
        self.positions: dict[str, int] = {}
        self.book: dict[str, float] = {}
        self.stock_legs: dict[str, float] = {}

    def close_all(self) -> tuple[float, float]:
        """Flatten. Returns (full-book turnover, stock-leg turnover) — closing a
        real position IS a real trade and is charged; flat-to-flat is free."""
        full = sum(abs(v) for v in self.book.values())
        legs = sum(abs(v) for v in self.stock_legs.values())
        self.positions = {}
        self.book = {}
        self.stock_legs = {}
        return full, legs


def _turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    """L1 distance between two sparse weight vectors, aligned on their union —
    a name in exactly one of them contributes its full weight, which is the
    correct charge for opening or closing it."""
    total = 0.0
    for ticker, weight in current.items():
        total += abs(weight - previous.get(ticker, 0.0))
    for ticker, weight in previous.items():
        if ticker not in current:
            total += abs(weight)
    return total


def run_eigen_replay(
    panel: EigenPanel,
    specs: list[EigenSpec],
    config: EigenConfig,
) -> dict[str, EigenBacktestResult]:
    """Walk forward once per CORRELATION WINDOW, driving every spec that shares
    it, and return one result per spec.

    THE SHARING IS THE WHOLE DESIGN. The expensive step is the eigen-
    decomposition of a ~500x500 correlation matrix on every one of ~2,900
    formation dates, and it depends ONLY on the correlation window — not on the
    factor rule, not on the thresholds. So it is computed once per (date,
    window) and reused across the three factor rules, whose s-scores in turn
    drive the two threshold sets' state machines. Twelve specs therefore cost
    two passes over the panel rather than twelve.

    NO LOOK-AHEAD. The cross-section on formation date p is chosen from
    point-in-time membership and trailing returns ENDING at p inclusive; the
    position is established at p's close; the first return it earns is p+1's.
    Names whose NEXT-day return is missing are deliberately NOT excluded when
    the cross-section is formed — excluding them would be a real (if small)
    look-ahead, because "this name stops trading tomorrow" is not knowable at
    p. They keep their book weight and contribute a zero return, and every
    occurrence is COUNTED in n_missing_next_return.
    """
    index = panel.returns.index
    tickers = np.array(panel.returns.columns)
    values = panel.returns.to_numpy(dtype=float)
    mask_values = panel.member_mask.to_numpy(dtype=bool)
    n_dates = len(index)

    financing_daily = config.financing_bps_per_year / 1e4 / FINANCING_DAYS_PER_YEAR
    cost_rate = config.cost_bps / 1e4

    results: dict[str, EigenBacktestResult] = {
        spec.spec_id: EigenBacktestResult(spec_id=spec.spec_id, status="ok") for spec in specs
    }
    returns_by_spec: dict[str, dict[pd.Timestamp, float]] = {s.spec_id: {} for s in specs}
    gross_by_spec: dict[str, dict[pd.Timestamp, float]] = {s.spec_id: {} for s in specs}
    exposure_by_spec: dict[str, dict[pd.Timestamp, float]] = {s.spec_id: {} for s in specs}
    kappas_by_spec: dict[str, list[float]] = {s.spec_id: [] for s in specs}
    factors_by_spec: dict[str, list[int]] = {s.spec_id: [] for s in specs}

    start_positions = np.flatnonzero(index.date >= config.formation_start)
    if len(start_positions) == 0:
        for result in results.values():
            result.status = "no_history_after_start"
        return results

    for window_length in sorted({spec.correlation_window for spec in specs}):
        window_specs = [s for s in specs if s.correlation_window == window_length]
        states = {spec.spec_id: _BookState() for spec in window_specs}
        rules = sorted({spec.factor_rule for spec in window_specs})

        first = max(int(start_positions[0]), window_length)
        for p in range(first, n_dates - 1):
            stamp = index[p]
            next_stamp = index[p + 1]
            elapsed_days = max((next_stamp - stamp).days, 0)

            block = values[p - window_length + 1 : p + 1]
            usable = mask_values[p] & np.isfinite(block).all(axis=0)
            column_index = np.flatnonzero(usable)
            n_members = int(mask_values[p].sum())

            if len(column_index) >= config.min_names:
                # A name whose trailing window never moves has sigmabar_i = 0
                # and cannot be standardized (the paper's p.5 divides by it);
                # dropped here rather than producing NaNs downstream.
                trailing_sigma = block[:, column_index].std(axis=0, ddof=1)
                column_index = column_index[trailing_sigma > 0]

            if len(column_index) < config.min_names:
                for spec in window_specs:
                    state = states[spec.spec_id]
                    full, legs = state.close_all()
                    cost = cost_rate * full
                    result = results[spec.spec_id]
                    result.total_cost += cost
                    result.total_full_book_turnover += full
                    result.total_stock_leg_turnover += legs
                    result.n_thin_skipped += 1
                    result.formations.append(
                        FormationRecord(
                            formation_date=stamp.date(),
                            n_members=n_members,
                            n_usable=len(column_index),
                            n_factors=0,
                            variance_explained=0.0,
                            n_tradeable=0,
                            n_long=0,
                            n_short=0,
                            gross_before_normalization=0.0,
                            full_book_turnover=full,
                            stock_leg_turnover=legs,
                            cost=cost,
                            skipped_reason="cross_section_too_thin",
                        )
                    )
                continue

            window = block[:, column_index]
            sigma = window.std(axis=0, ddof=1)
            window_tickers = tuple(tickers[column_index])
            raw_next = values[p + 1, column_index]
            missing_next = ~np.isfinite(raw_next)
            next_returns = np.where(missing_next, 0.0, raw_next)

            standardized = (window - window.mean(axis=0)) / sigma
            rho = standardized.T @ standardized / (window.shape[0] - 1)
            eigenvalues, eigenvectors = np.linalg.eigh(rho)
            eigenvalues = eigenvalues[::-1]
            eigenvectors = eigenvectors[:, ::-1]
            precomputed = (sigma, eigenvalues, eigenvectors)

            signals = {
                rule: build_cross_section_signal(
                    window,
                    next_returns,
                    window_tickers,
                    rule,
                    precomputed=precomputed,
                )
                for rule in rules
            }

            for spec in window_specs:
                signal = signals[spec.factor_rule]
                state = states[spec.spec_id]
                result = results[spec.spec_id]
                result.n_missing_next_return += int(missing_next.sum())

                if not signal.dof_ok:
                    full, legs = state.close_all()
                    cost = cost_rate * full
                    result.total_cost += cost
                    result.total_full_book_turnover += full
                    result.total_stock_leg_turnover += legs
                    result.n_dof_skipped += 1
                    result.formations.append(
                        FormationRecord(
                            formation_date=stamp.date(),
                            n_members=n_members,
                            n_usable=len(column_index),
                            n_factors=signal.n_factors,
                            variance_explained=signal.variance_explained,
                            n_tradeable=0,
                            n_long=0,
                            n_short=0,
                            gross_before_normalization=0.0,
                            full_book_turnover=full,
                            stock_leg_turnover=legs,
                            cost=cost,
                            skipped_reason="insufficient_residual_dof",
                        )
                    )
                    continue

                # --- the state machine, paper eq. 16 ---------------------
                new_positions: dict[str, int] = {}
                weights = np.zeros(len(window_tickers))
                for i, ticker in enumerate(window_tickers):
                    current = state.positions.get(ticker, 0)
                    if not signal.tradeable[i]:
                        # Paper section 5: when kappa crosses below the
                        # threshold "we reject the model and (i) do not open
                        # trades or (ii) close open trades."
                        continue
                    updated = next_position(current, float(signal.s_score[i]), spec.thresholds)
                    if updated != 0:
                        new_positions[ticker] = updated
                        weights[i] = float(updated) * spec.direction

                # Names that were open but are no longer in the cross-section
                # at all (left the index, lost price history) are dropped, i.e.
                # closed — their weight simply does not appear below.
                n_long = sum(1 for v in new_positions.values() if v > 0)
                n_short = sum(1 for v in new_positions.values() if v < 0)

                # --- the full book, mapped back into stock space ---------
                # book = w - Qmat @ (beta^T w). See the module docstring.
                factor_exposure = signal.betas.T @ weights
                hedge = signal.eigen_weights @ factor_exposure
                book_vector = weights - hedge
                gross = float(np.abs(book_vector).sum())

                if gross <= 0:
                    full, legs = state.close_all()
                    cost = cost_rate * full
                    result.total_cost += cost
                    result.total_full_book_turnover += full
                    result.total_stock_leg_turnover += legs
                    result.formations.append(
                        FormationRecord(
                            formation_date=stamp.date(),
                            n_members=n_members,
                            n_usable=len(column_index),
                            n_factors=signal.n_factors,
                            variance_explained=signal.variance_explained,
                            n_tradeable=int(signal.tradeable.sum()),
                            n_long=0,
                            n_short=0,
                            gross_before_normalization=0.0,
                            full_book_turnover=full,
                            stock_leg_turnover=legs,
                            cost=cost,
                            skipped_reason="no_open_positions",
                        )
                    )
                    continue

                scale = 1.0 / gross
                scaled_weights = weights * scale
                scaled_book = book_vector * scale

                new_book = {
                    ticker: float(scaled_book[i])
                    for i, ticker in enumerate(window_tickers)
                    if scaled_book[i] != 0.0
                }
                new_legs = {
                    ticker: float(scaled_weights[i])
                    for i, ticker in enumerate(window_tickers)
                    if scaled_weights[i] != 0.0
                }

                full_turnover = _turnover(state.book, new_book)
                leg_turnover = _turnover(state.stock_legs, new_legs)
                cost = cost_rate * full_turnover

                # Financing on the SHORT side of the full book only.
                short_notional = float(np.maximum(-scaled_book, 0.0).sum())
                financing = financing_daily * short_notional * elapsed_days

                gross_return = float(scaled_weights @ signal.residual_return_next)
                net_return = gross_return - cost - financing

                result.total_cost += cost
                result.total_financing_cost += financing
                result.total_full_book_turnover += full_turnover
                result.total_stock_leg_turnover += leg_turnover
                returns_by_spec[spec.spec_id][next_stamp] = net_return
                gross_by_spec[spec.spec_id][next_stamp] = gross_return
                exposure_by_spec[spec.spec_id][next_stamp] = float(scaled_book.sum())

                tradeable_kappa = signal.kappa[signal.tradeable]
                if tradeable_kappa.size:
                    kappas_by_spec[spec.spec_id].append(float(np.median(tradeable_kappa)))
                factors_by_spec[spec.spec_id].append(signal.n_factors)

                result.formations.append(
                    FormationRecord(
                        formation_date=stamp.date(),
                        n_members=n_members,
                        n_usable=len(column_index),
                        n_factors=signal.n_factors,
                        variance_explained=signal.variance_explained,
                        n_tradeable=int(signal.tradeable.sum()),
                        n_long=n_long,
                        n_short=n_short,
                        gross_before_normalization=gross,
                        full_book_turnover=full_turnover,
                        stock_leg_turnover=leg_turnover,
                        cost=cost,
                    )
                )

                state.positions = new_positions
                state.book = new_book
                state.stock_legs = new_legs

    for spec in specs:
        result = results[spec.spec_id]
        daily = pd.Series(returns_by_spec[spec.spec_id]).sort_index()
        if daily.empty:
            result.status = "no_realized_returns"
            continue
        result.daily_returns = daily
        result.gross_returns = pd.Series(gross_by_spec[spec.spec_id]).sort_index()
        result.net_exposure = pd.Series(exposure_by_spec[spec.spec_id]).sort_index()
        kappas = kappas_by_spec[spec.spec_id]
        result.median_kappa = float(np.median(kappas)) if kappas else None
        counts = factors_by_spec[spec.spec_id]
        result.median_n_factors = float(np.median(counts)) if counts else None

    return results


# --- the naive-reversal diagnostic -----------------------------------------


@dataclass
class ReversalBook:
    """A plain 5-day cross-sectional reversal book on the SAME point-in-time
    universe with the SAME cost model — the thing this family must be shown not
    to be. A DIAGNOSTIC, never a spec: it is not in EIGEN_N_TRIALS because it is
    not a variant of this family's signal."""

    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    sharpe_annualized: float = 0.0
    n_trading_days: int = 0
    total_cost: float = 0.0
    status: str = "ok"


def build_reversal_book(
    panel: EigenPanel,
    config: EigenConfig,
    lookback: int = EIGEN_REVERSAL_LOOKBACK,
) -> ReversalBook:
    """Weights proportional to MINUS the cross-sectionally demeaned trailing
    `lookback`-day return, normalized to gross notional 1.0, rebalanced daily,
    charged the same one-way cost on turnover. Deliberately as simple as the
    effect it stands for."""
    index = panel.returns.index
    tickers = np.array(panel.returns.columns)
    values = panel.returns.to_numpy(dtype=float)
    mask_values = panel.member_mask.to_numpy(dtype=bool)
    cost_rate = config.cost_bps / 1e4

    start_positions = np.flatnonzero(index.date >= config.formation_start)
    if len(start_positions) == 0:
        return ReversalBook(status="no_history_after_start")

    previous: dict[str, float] = {}
    returns: dict[pd.Timestamp, float] = {}
    total_cost = 0.0

    for p in range(max(int(start_positions[0]), lookback), len(index) - 1):
        block = values[p - lookback + 1 : p + 1]
        usable = mask_values[p] & np.isfinite(block).all(axis=0)
        column_index = np.flatnonzero(usable)
        if len(column_index) < config.min_names:
            continue

        trailing = block[:, column_index].sum(axis=0)
        signal = -(trailing - trailing.mean())
        gross = float(np.abs(signal).sum())
        if gross <= 0:
            continue
        weights = signal / gross

        current = {
            ticker: float(weights[i])
            for i, ticker in enumerate(tickers[column_index])
            if weights[i] != 0.0
        }
        cost = cost_rate * _turnover(previous, current)
        total_cost += cost

        raw_next = values[p + 1, column_index]
        next_returns = np.where(np.isfinite(raw_next), raw_next, 0.0)
        returns[index[p + 1]] = float(weights @ next_returns) - cost
        previous = current

    if not returns:
        return ReversalBook(status="no_realized_returns")
    series = pd.Series(returns).sort_index()
    return ReversalBook(
        daily_returns=series,
        sharpe_annualized=sharpe_ratio(series),
        n_trading_days=len(series),
        total_cost=total_cost,
    )


# --- diagnostics -----------------------------------------------------------


@dataclass(frozen=True)
class ConfoundDiagnostic:
    """Everything needed to decide whether a positive Sharpe here is real, a
    disguised static market tilt, or short-term reversal relabelled."""

    spec_id: str
    mean_net_exposure: float
    spy_beta: float
    spy_alpha_annualized: float
    # Sharpe of the BETA-HEDGED stream y - beta*x, NOT the OLS residual
    # y - alpha - beta*x, whose mean is zero by construction and would report
    # every strategy ever measured as a pure tilt.
    residual_sharpe: float
    benchmark_sharpe: float
    subperiod_sharpes: tuple[float, ...]
    bootstrap_p_value: float | None
    reversal_return_corr: float | None
    reversal_overlap_suspect: bool
    median_kappa: float | None
    median_half_life_days: float | None
    median_n_factors: float | None


def _subperiod_sharpes(returns: pd.Series, n_periods: int = 3) -> tuple[float, ...]:
    clean = returns.dropna()
    if len(clean) < n_periods * 2:
        return ()
    bounds = np.linspace(0, len(clean), n_periods + 1).astype(int)
    return tuple(
        sharpe_ratio(clean.iloc[bounds[i] : bounds[i + 1]])
        if bounds[i + 1] - bounds[i] >= 2
        else 0.0
        for i in range(n_periods)
    )


def _corr(a: pd.Series, b: pd.Series) -> float | None:
    joined = pd.concat([a.rename("a"), b.rename("b")], axis=1, sort=True).dropna()
    if len(joined) < MIN_REPLAY_TRADING_DAYS:
        return None
    if joined["a"].std(ddof=1) == 0 or joined["b"].std(ddof=1) == 0:
        return None
    value = float(joined["a"].corr(joined["b"]))
    return value if np.isfinite(value) else None


def compute_confound_diagnostics(
    replay: EigenBacktestResult,
    benchmark_returns: pd.Series,
    reversal: ReversalBook | None,
) -> ConfoundDiagnostic:
    """The in-module adversarial pass, run on EVERY spec, always.

    residual_sharpe is the number that decides whether a spec is real: the
    Sharpe left after removing the strategy's OLS exposure to buy-and-hold SPY.
    compute_beta is REUSED from risk.beta rather than re-derived.

    The degeneracy guard is not defensive decoration. A Sharpe is
    SCALE-INVARIANT, so a hedged stream that is mathematically zero but
    numerically 1e-18 still reports whatever Sharpe its floating-point dust
    happens to have — and this project has already seen an unguarded version
    print a confident -0.836 on a stream bit-identical to its benchmark. When
    the hedge explains essentially all the variance the honest answer is 0.0.
    """
    daily = replay.daily_returns
    aligned = pd.concat(
        [daily.rename("y"), benchmark_returns.rename("x")], axis=1, sort=True
    ).dropna()

    if len(aligned) >= 3:
        beta = compute_beta(aligned["y"], aligned["x"])
        if not np.isfinite(beta):
            beta = 0.0
        hedged = aligned["y"] - beta * aligned["x"]
        y_std = float(aligned["y"].std(ddof=1))
        hedged_std = float(hedged.std(ddof=1))
        fully_explained = y_std > 0 and hedged_std <= RESIDUAL_DEGENERACY_RATIO * y_std
        residual_sharpe = 0.0 if fully_explained else sharpe_ratio(hedged)
        alpha_annualized = (
            0.0 if fully_explained else float(hedged.mean()) * TRADING_DAYS_PER_YEAR
        )
        benchmark_sharpe = sharpe_ratio(aligned["x"])
    else:
        beta = 0.0
        residual_sharpe = 0.0
        alpha_annualized = 0.0
        benchmark_sharpe = 0.0

    reversal_corr = (
        _corr(daily, reversal.daily_returns)
        if reversal is not None and len(reversal.daily_returns)
        else None
    )

    median_kappa = replay.median_kappa
    return ConfoundDiagnostic(
        spec_id=replay.spec_id,
        mean_net_exposure=float(replay.net_exposure.mean()) if len(replay.net_exposure) else 0.0,
        spy_beta=float(beta),
        spy_alpha_annualized=alpha_annualized,
        residual_sharpe=residual_sharpe,
        benchmark_sharpe=benchmark_sharpe,
        subperiod_sharpes=_subperiod_sharpes(daily),
        bootstrap_p_value=block_bootstrap_sharpe_pvalue(daily, EIGEN_BOOTSTRAP_BLOCK_DAYS),
        reversal_return_corr=reversal_corr,
        reversal_overlap_suspect=(
            reversal_corr is not None and abs(reversal_corr) > EIGEN_REVERSAL_OVERLAP_THRESHOLD
        ),
        median_kappa=median_kappa,
        median_half_life_days=(
            float(implied_half_life_days(median_kappa)) if median_kappa else None
        ),
        median_n_factors=replay.median_n_factors,
    )


@dataclass(frozen=True)
class EdgeCostDiagnostic:
    """What the project's own per-ticker cost model says about the flat 5bp.

    A DIAGNOSTIC, pre-declared in PREREGISTRATION section 5, never the headline
    and never in n_trials. `status` is "ok", or a plain-language reason the
    estimate could not be produced — which the run report prints verbatim,
    because the pre-registration's requirement was that an unobtainable
    estimate be STATED, not silently skipped.

    Every figure is a ONE-WAY HALF-SPREAD in basis points, directly comparable
    to EIGEN_COST_BPS. Read them as an UPPER bound: spread_estimator's own
    synthetic-recovery test records that EDGE is biased upward in the tightest
    large-cap regime, which is exactly this universe."""

    status: str
    window_days: int = COST_MODEL_WINDOW_DAYS
    n_tickers: int = 0
    n_estimates: int = 0
    median_bps: float | None = None
    mean_bps: float | None = None
    p75_bps: float | None = None
    p90_bps: float | None = None
    by_year_median_bps: dict[int, float] = field(default_factory=dict)


def summarize_edge_half_spreads(
    open_: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    close: pd.DataFrame,
    member_mask: pd.DataFrame,
    formation_start: date,
) -> EdgeCostDiagnostic:
    """Run the EDGE estimator over the POINT-IN-TIME traded cross-section.

    The membership mask is applied for the same reason it is applied
    everywhere else in this module: the question is what the names this family
    ACTUALLY traded cost to trade, not what the union candidate pool cost. A
    cell outside the mask, before the first formation date, or with no usable
    EDGE estimate is excluded rather than imputed.

    Reuses spread_estimator.build_edge_half_spread_frame rather than
    reimplementing the estimator, so the number means the same thing it means
    everywhere else in this codebase."""
    if close.empty:
        return EdgeCostDiagnostic(status="no OHLC data resolved for the traded universe")

    frame = build_edge_half_spread_frame(open_, high, low, close)
    aligned = member_mask.reindex(index=frame.index, columns=frame.columns, fill_value=False)
    eligible = frame.where(aligned.to_numpy(dtype=bool))
    eligible = eligible.loc[eligible.index >= pd.Timestamp(formation_start)]

    values = eligible.to_numpy(dtype=float).ravel()
    values = values[np.isfinite(values)] * 1e4
    if values.size == 0:
        return EdgeCostDiagnostic(
            status="OHLC resolved but no usable EDGE estimate on any traded name/date",
            n_tickers=len(frame.columns),
        )

    by_year: dict[int, float] = {}
    for year, group in eligible.groupby(eligible.index.year):
        row = group.to_numpy(dtype=float).ravel()
        row = row[np.isfinite(row)] * 1e4
        if row.size:
            by_year[int(year)] = float(np.median(row))

    return EdgeCostDiagnostic(
        status="ok",
        n_tickers=len(frame.columns),
        n_estimates=int(values.size),
        median_bps=float(np.median(values)),
        mean_bps=float(values.mean()),
        p75_bps=float(np.percentile(values, 75)),
        p90_bps=float(np.percentile(values, 90)),
        by_year_median_bps=by_year,
    )


def cost_sensitivity(
    replay: EigenBacktestResult,
    config: EigenConfig,
    levels: tuple[float, ...] = EIGEN_COST_SENSITIVITY_BPS,
) -> dict[float, float]:
    """Sharpe at each pre-declared cost level, on the IDENTICAL position path —
    no re-optimization, no re-formation. Only the per-day turnover charge
    changes, which is exactly the question "how much does the cost assumption
    carry this result".

    Reconstructed by adding back the charge actually levied and subtracting the
    alternative, using each formation's own recorded full-book turnover, so it
    is arithmetic rather than an approximation."""
    if replay.daily_returns.empty:
        return {}
    charged = pd.Series(
        {
            pd.Timestamp(f.formation_date): f.full_book_turnover
            for f in replay.formations
            if f.skipped_reason is None
        }
    ).sort_index()
    # Turnover recorded at formation p is charged against the return dated p+1.
    turnover = pd.Series(
        charged.to_numpy(), index=replay.daily_returns.index[: len(charged)]
    ).reindex(replay.daily_returns.index, fill_value=0.0)

    out: dict[float, float] = {}
    for level in levels:
        delta = (level - config.cost_bps) / 1e4
        out[level] = sharpe_ratio(replay.daily_returns - turnover * delta)
    return out


# --- screening -------------------------------------------------------------


@dataclass
class EigenScreeningResult:
    spec_id: str
    factor_rule: str
    correlation_window: int
    threshold_key: str
    citation: str
    hypothesis: str
    is_eigen_hypothesis: bool
    n_formations: int
    n_skipped_formations: int
    n_dof_skipped: int
    n_trading_days: int
    first_formation: date | None
    last_formation: date | None
    sharpe_annualized: float
    gross_sharpe_annualized: float
    net_cumulative_return: float
    total_cost_drag: float
    total_financing_drag: float
    mean_full_book_turnover: float
    mean_stock_leg_turnover: float
    mean_n_long: float
    mean_n_short: float
    mean_n_usable: float
    # PREREGISTRATION section 6, diagnostic 6: "fraction of names passing the
    # kappa > 8.4 filter". Reported per spec so a reader can see how much of
    # the cross-section the paper's own speed filter actually removes — which
    # is what says whether the median fitted kappa is a property of the data
    # or an artifact of a hard truncation.
    mean_tradeable_fraction: float
    deflated_sharpe: DeflatedSharpeResult
    confound: ConfoundDiagnostic
    cost_sensitivity_sharpe: dict[float, float]


def screen_eigenportfolio(
    panel: EigenPanel,
    specs: list[EigenSpec],
    config: EigenConfig,
    benchmark_returns: pd.Series,
    reversal: ReversalBook | None = None,
) -> list[EigenScreeningResult]:
    """One Sharpe per spec, DSR-corrected for the family's pre-declared size.

    n_trials is fixed at len(specs) — the family's literal pre-declared size —
    and never shrunk to however many specs survived the data floors, which
    would be gameable by declaring specs expected to fail. sigma_sr is the
    ddof=1 sd of every sibling spec's Sharpe from this same pass, the sibling
    convention throughout this codebase.

    The caveat no caller may drop: 12 counts THIS family only. The literature
    scan that nominated Avellaneda-Lee, and the other families screened
    alongside it, are NOT in the denominator, so every DSR here is an upper
    bound on the honest one."""
    n_trials = len(specs)
    replays = run_eigen_replay(panel, specs, config)

    usable: dict[str, EigenBacktestResult] = {}
    for spec in specs:
        replay = replays[spec.spec_id]
        if replay.status != "ok":
            logger.info("eigenportfolio spec %s not replayed: %s", spec.spec_id, replay.status)
            continue
        if len(replay.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            logger.info(
                "eigenportfolio spec %s dropped: only %d realized days (floor %d)",
                spec.spec_id,
                len(replay.daily_returns),
                MIN_REPLAY_TRADING_DAYS,
            )
            continue
        usable[spec.spec_id] = replay

    sharpes = {sid: sharpe_ratio(r.daily_returns) for sid, r in usable.items()}
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {s.spec_id: s for s in specs}
    results: list[EigenScreeningResult] = []
    for spec_id, replay in usable.items():
        spec = spec_by_id[spec_id]
        active = [f for f in replay.formations if f.skipped_reason is None]
        skipped = [f for f in replay.formations if f.skipped_reason is not None]
        results.append(
            EigenScreeningResult(
                spec_id=spec_id,
                factor_rule=spec.factor_rule,
                correlation_window=spec.correlation_window,
                threshold_key=spec.thresholds.key,
                citation=spec.citation,
                hypothesis=spec.hypothesis,
                is_eigen_hypothesis=spec.is_eigen_hypothesis,
                n_formations=len(active),
                n_skipped_formations=len(skipped),
                n_dof_skipped=replay.n_dof_skipped,
                n_trading_days=len(replay.daily_returns),
                first_formation=active[0].formation_date if active else None,
                last_formation=active[-1].formation_date if active else None,
                sharpe_annualized=sharpes[spec_id],
                gross_sharpe_annualized=sharpe_ratio(replay.gross_returns),
                net_cumulative_return=float(replay.daily_returns.sum()),
                total_cost_drag=replay.total_cost,
                total_financing_drag=replay.total_financing_cost,
                mean_full_book_turnover=(
                    float(np.mean([f.full_book_turnover for f in active])) if active else 0.0
                ),
                mean_stock_leg_turnover=(
                    float(np.mean([f.stock_leg_turnover for f in active])) if active else 0.0
                ),
                mean_n_long=float(np.mean([f.n_long for f in active])) if active else 0.0,
                mean_n_short=float(np.mean([f.n_short for f in active])) if active else 0.0,
                mean_n_usable=float(np.mean([f.n_usable for f in active])) if active else 0.0,
                mean_tradeable_fraction=(
                    float(np.mean([f.n_tradeable / f.n_usable for f in active if f.n_usable]))
                    if any(f.n_usable for f in active)
                    else 0.0
                ),
                deflated_sharpe=compute_deflated_sharpe(
                    sharpes[spec_id], replay.daily_returns, n_trials, sigma_sr
                ),
                confound=compute_confound_diagnostics(replay, benchmark_returns, reversal),
                cost_sensitivity_sharpe=cost_sensitivity(replay, config),
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results


# --- disclosure ------------------------------------------------------------


@dataclass
class EigenScreeningSummary:
    results: list[EigenScreeningResult] = field(default_factory=list)
    reversal: ReversalBook | None = None
    universe_size: int = 0
    n_resolved: int = 0
    missing_tickers: list[str] = field(default_factory=list)
    panel_start: date | None = None
    panel_end: date | None = None
    coverage_by_year: dict[int, tuple[float, float]] = field(default_factory=dict)
    edge_cost: EdgeCostDiagnostic | None = None
    disclosure: list[str] = field(default_factory=list)


def build_eigen_disclosure(
    results: list[EigenScreeningResult],
    config: EigenConfig,
    summary: "EigenScreeningSummary | None" = None,
) -> list[str]:
    """Plain-language caveats that must travel with any number from this
    family, including the breakeven-cost arithmetic that says how wrong the
    cost assumption would have to be to matter."""
    lines = [
        (
            f"n_trials = {EIGEN_N_TRIALS} ({len(_FACTOR_RULES)} factor rules x "
            f"{len(EIGEN_CORRELATION_WINDOWS)} correlation windows x "
            f"{len(EIGEN_THRESHOLD_SETS)} threshold sets), fixed before any return was computed "
            "and never shrunk to the specs that survived the data floors."
        ),
        (
            "n_trials covers THIS family only. The literature scan that nominated Avellaneda-Lee, "
            "and the other asset-class families screened alongside it, are NOT in the denominator, "
            "so every DSR below is an UPPER BOUND on the honest one."
        ),
        (
            f"Direction was pre-declared uniformly contrarian ({EIGEN_DIRECTION:+.0f}, the paper's "
            "own mean-reversion rule) and never fitted per spec; negative Sharpes are reported as "
            "they came out, not flipped."
        ),
        (
            "UNIVERSE: point-in-time S&P 500 membership via get_universe_as_of on every formation "
            "date. A static present-day ticker list was NOT used. What that does NOT fix is "
            "missing PRICES for names that delisted — this project's own measurement is that "
            "yfinance returns no history for ~48% of recent former members, and those are the "
            "acquired/failed names. The residual survivorship bias FLATTERS these results."
        ),
        (
            f"Costs: {config.cost_bps:.1f}bp one-way on FULL-BOOK turnover (the paper's own "
            "eps=0.0005), where the full book includes the eigenportfolio hedge legs mapped back "
            "into stock space — a harsher and more honest charge than the paper's stock-legs-only "
            f"convention, which is reported alongside. Plus {config.financing_bps_per_year:.0f}"
            "bp/yr on the SHORT side only, a disclosed blended assumption rather than a sourced "
            "borrow quote."
        ),
        (
            "This is a DAILY-rebalanced book, so the cost assumption is the single most "
            "load-bearing input. The per-spec cost-sensitivity table at 5/10/20bp is computed on "
            "the identical position path and is the number to read before any Sharpe here."
        ),
        (
            "Positions persist across days under the paper's state machine, so the daily n "
            "overstates independent bets; a circular block bootstrap (block 21) is reported "
            "alongside every DSR, and where they disagree, believe the bootstrap."
        ),
        (
            f"Sample starts {EIGEN_FORMATION_START.isoformat()} (the limit of point-in-time "
            "membership coverage), so it contains no 2008-style crisis. The paper's strongest PCA "
            "years — 2000-2002 and 2004 — all predate this sample entirely, so this is NOT a "
            "replication of the paper's reported performance and must not be read as one."
        ),
        (
            "Formation is assumed executable at the exact closing print, cost is linear in traded "
            "notional with no market-impact model, and every name is assumed shortable. For a "
            "book rebalancing hundreds of names daily all three are optimistic."
        ),
    ]

    if summary is not None and summary.edge_cost is not None:
        edge = summary.edge_cost
        if edge.status == "ok" and edge.median_bps is not None:
            lines.append(
                f"EDGE CROSS-CHECK ON THE COST ASSUMPTION (pre-declared diagnostic, not the "
                f"headline): the project's own per-ticker model (Ardia, Guidotti & Kroencke, JFE "
                f"2024) puts the MEDIAN one-way half-spread of the point-in-time traded "
                f"cross-section at {edge.median_bps:.1f}bp (mean {edge.mean_bps:.1f}, p75 "
                f"{edge.p75_bps:.1f}, p90 {edge.p90_bps:.1f}), against the {config.cost_bps:.1f}bp "
                "flat rate charged above. EDGE is biased UPWARD in exactly this tightest "
                "large-cap regime (spread_estimator's own synthetic-recovery test), so treat it "
                "as an UPPER bound; the honest reading is directional, that the flat rate sits at "
                "the OPTIMISTIC end and the 10bp/20bp sensitivity columns are the ones to believe."
            )
        else:
            lines.append(
                "EDGE cross-check on the cost assumption is UNAVAILABLE for this run — stated "
                f"rather than skipped, as pre-declared. Reason: {edge.status}."
            )

    if summary is not None and summary.universe_size:
        lines.append(
            f"Candidate pool: {summary.universe_size} tickers that were S&P 500 members on any day "
            f"in the sample; {summary.n_resolved} resolved usable price history "
            f"({len(summary.missing_tickers)} did not, and those absences are the delisted-coverage "
            "gap above showing up concretely)."
        )

    if not results:
        lines.append("No spec produced a replayable return series — nothing to interpret.")
        return lines

    best = results[0]
    lines.append(
        f"Best raw Sharpe: {best.spec_id} at {best.sharpe_annualized:+.3f} over "
        f"{best.n_trading_days} days / {best.n_formations} formations."
    )

    dsr_results = [r for r in results if r.deflated_sharpe.dsr is not None]
    if dsr_results:
        best_dsr = max(dsr_results, key=lambda r: r.deflated_sharpe.dsr)
        dsr = best_dsr.deflated_sharpe.dsr
        if dsr >= 0.90:
            verdict = "clears this project's ~0.90-0.95 significance standard"
        elif dsr >= 0.50:
            verdict = "possibly interesting, but well short of this project's ~0.90-0.95 standard"
        else:
            verdict = "an HONEST NEGATIVE by this project's own pre-declared decision rule"
        lines.append(
            f"Best DSR: {best_dsr.spec_id} at {dsr:.3f} (n_trials={EIGEN_N_TRIALS}) — {verdict}."
        )

    charges = best.total_cost_drag + best.total_financing_drag
    if charges > 0:
        multiple = (best.net_cumulative_return + charges) / charges
        if multiple <= 1.0:
            lines.append(
                f"Breakeven cost multiple for {best.spec_id}: {multiple:.2f}x — at or below 1.0, "
                "meaning it was already unprofitable BEFORE costs. No cost assumption rescues it."
            )
        else:
            lines.append(
                f"Breakeven cost multiple for {best.spec_id}: {multiple:.2f}x — costs would have "
                f"to be {multiple:.2f} times the assumed {config.cost_bps:.1f}bp to erase its net "
                "return."
            )

    # SIGNED, deliberately not abs(): the question is whether a POSITIVE Sharpe
    # survived hedging out the static exposure. abs() would let the degenerate
    # case through, where a near-constant book leaves only cost drag whose
    # Sharpe is a large negative number sailing past any threshold.
    tilts = [
        r
        for r in results
        if r.sharpe_annualized > 0 and r.confound.residual_sharpe < 0.5 * r.sharpe_annualized
    ]
    if tilts:
        lines.append(
            f"{len(tilts)} spec(s) with a positive raw Sharpe lose more than half of it once "
            "their static exposure to buy-and-hold SPY is regressed out — those are disguised "
            "market tilts, not stat-arb."
        )

    suspects = [r for r in results if r.confound.reversal_overlap_suspect]
    if suspects:
        lines.append(
            f"REVERSAL-OVERLAP WARNING: {len(suspects)} of {len(results)} spec(s) exceed the "
            f"pre-declared |corr| > {EIGEN_REVERSAL_OVERLAP_THRESHOLD} against a plain 5-day "
            "cross-sectional reversal book on the same universe. Any apparent edge in those specs "
            "must be treated as probable short-term reversal relabelled."
        )
    else:
        lines.append(
            f"Reversal-overlap check: no spec exceeds |corr| > "
            f"{EIGEN_REVERSAL_OVERLAP_THRESHOLD} against a plain 5-day cross-sectional reversal "
            "book on the same universe with the same costs."
        )

    controls = [r for r in results if not r.is_eigen_hypothesis]
    hypotheses = [r for r in results if r.is_eigen_hypothesis]
    if controls and hypotheses:
        best_control = max(controls, key=lambda r: r.sharpe_annualized)
        best_hypothesis = max(hypotheses, key=lambda r: r.sharpe_annualized)
        if best_control.sharpe_annualized >= best_hypothesis.sharpe_annualized:
            lines.append(
                f"CONTROL BEATS HYPOTHESIS: the m1 control ({best_control.spec_id}, Sharpe "
                f"{best_control.sharpe_annualized:+.3f}) matches or beats the best multi-factor "
                f"spec ({best_hypothesis.spec_id}, {best_hypothesis.sharpe_annualized:+.3f}). On "
                "this sample the eigenportfolio structure earns nothing over a plain market hedge, "
                "which is a direct negative for the paper's PCA thesis as tested here."
            )
        else:
            lines.append(
                f"The best multi-factor spec ({best_hypothesis.spec_id}, "
                f"{best_hypothesis.sharpe_annualized:+.3f}) beats the best m1 control "
                f"({best_control.spec_id}, {best_control.sharpe_annualized:+.3f}) — the "
                "eigenportfolio structure is contributing something beyond a market hedge."
            )

    return lines


# --- production entry point ------------------------------------------------


def run_eigenportfolio_screening(
    start: date = EIGEN_FORMATION_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    config: EigenConfig | None = None,
    specs: list[EigenSpec] | None = None,
    benchmark_ticker: str = "SPY",
    include_reversal_diagnostic: bool = True,
    include_edge_cost_diagnostic: bool = True,
) -> EigenScreeningSummary:
    """THE research entry point for the eigenportfolio family, scoped to
    exactly EIGEN_FAMILY's 12 definitions and their own n_trials.

    Deliberately NOT wired into any live runner or forward-validation registry:
    this is a research screen, and promoting anything from it to production
    tracking is a separate explicit decision.

    `start` is the first FORMATION date; price history is padded before it by
    EIGEN_HISTORY_PADDING_CALENDAR_DAYS so the 252-day correlation window is
    warm. Formations never occur in the padding."""
    end = end if end is not None else date.today()  # noqa: DTZ011
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else default_eigen_config()
    config.formation_start = start
    specs = specs if specs is not None else EIGEN_FAMILY

    if start < MEMBERSHIP_DATA_START:
        raise PointInTimeUniverseError(
            f"eigenportfolio formations cannot start {start.isoformat()}: point-in-time S&P 500 "
            f"membership coverage begins {MEMBERSHIP_DATA_START.isoformat()}, and using a static "
            "present-day universe before it would reintroduce exactly the survivorship bias this "
            "family exists to avoid."
        )

    padded_start = start - timedelta(days=EIGEN_HISTORY_PADDING_CALENDAR_DAYS)
    universe = get_universe_over(start, end)
    if not universe:
        return EigenScreeningSummary(disclosure=["empty point-in-time universe"])

    wanted = [*universe, benchmark_ticker]
    closes, missing = provider.get_price_history(wanted, padded_start, end)
    if closes.empty:
        return EigenScreeningSummary(
            universe_size=len(universe),
            missing_tickers=missing or wanted,
            disclosure=["no price history resolved for the point-in-time universe"],
        )
    if missing:
        logger.warning(
            "eigenportfolio screening: %d of %d requested tickers resolved NO price data — this "
            "is the known delisted-coverage gap and it FLATTERS the result.",
            len(missing),
            len(wanted),
        )

    benchmark = (
        closes[benchmark_ticker].pct_change()
        if benchmark_ticker in closes.columns
        else pd.Series(dtype=float)
    )
    constituent_columns = [c for c in closes.columns if c != benchmark_ticker]
    panel = build_eigen_panel(closes[constituent_columns])

    reversal = build_reversal_book(panel, config) if include_reversal_diagnostic else None
    results = screen_eigenportfolio(panel, specs, config, benchmark, reversal)

    usable_counts = panel.returns.notna() & panel.member_mask
    per_date_usable = usable_counts.sum(axis=1)
    coverage: dict[int, tuple[float, float]] = {}
    for year, group in per_date_usable.groupby(per_date_usable.index.year):
        members = panel.n_members_by_date.reindex(group.index)
        coverage[int(year)] = (float(members.mean()), float(group.mean()))

    # PREREGISTRATION section 5's pre-declared EDGE cross-check on the flat
    # 5bp. Wrapped because it is a DIAGNOSTIC: a failed OHLC fetch must
    # degrade to a stated limitation in the report, never take down a screen
    # whose headline cost model does not depend on it.
    edge_cost: EdgeCostDiagnostic | None = None
    if include_edge_cost_diagnostic:
        try:
            frames, _edge_missing = provider.get_daily_ohlcv(universe, padded_start, end)
            edge_cost = summarize_edge_half_spreads(
                frames["open"],
                frames["high"],
                frames["low"],
                frames["close"],
                panel.member_mask,
                start,
            )
        except Exception as exc:  # noqa: BLE001 — a diagnostic must not fail the screen
            logger.warning("eigenportfolio EDGE cost diagnostic unavailable: %s", exc)
            edge_cost = EdgeCostDiagnostic(status=f"OHLC fetch failed: {exc}")

    summary = EigenScreeningSummary(
        results=results,
        reversal=reversal,
        edge_cost=edge_cost,
        universe_size=len(universe),
        n_resolved=len(constituent_columns),
        missing_tickers=missing,
        panel_start=panel.returns.index[0].date() if len(panel.returns.index) else None,
        panel_end=panel.returns.index[-1].date() if len(panel.returns.index) else None,
        coverage_by_year=coverage,
    )
    summary.disclosure = build_eigen_disclosure(results, config, summary)
    return summary


__all__ = [
    "AVELLANEDA_LEE_CITATION",
    "EIGEN_BOOTSTRAP_BLOCK_DAYS",
    "EIGEN_B_CEILING",
    "EIGEN_CORRELATION_WINDOWS",
    "EIGEN_COST_BPS",
    "EIGEN_COST_SENSITIVITY_BPS",
    "EIGEN_DIRECTION",
    "EIGEN_FAMILY",
    "EIGEN_FINANCING_BPS_PER_YEAR",
    "EIGEN_FORMATION_START",
    "EIGEN_HISTORY_PADDING_CALENDAR_DAYS",
    "EIGEN_KAPPA_FLOOR",
    "EIGEN_MIN_NAMES",
    "EIGEN_MIN_RESIDUAL_DOF",
    "EIGEN_N_TRIALS",
    "EIGEN_PCA_FIXED_COUNT",
    "EIGEN_REGRESSION_WINDOW",
    "EIGEN_REVERSAL_LOOKBACK",
    "EIGEN_REVERSAL_OVERLAP_THRESHOLD",
    "EIGEN_THRESHOLD_SETS",
    "EIGEN_VARIANCE_THRESHOLD",
    "PAPER_S_BC",
    "PAPER_S_BO",
    "PAPER_S_SC",
    "PAPER_S_SO",
    "PAPER_THRESHOLDS",
    "REVERSAL_CONTROL_CITATION",
    "WIDE_THRESHOLDS",
    "ConfoundDiagnostic",
    "CrossSectionSignal",
    "EdgeCostDiagnostic",
    "EigenBacktestResult",
    "EigenConfig",
    "EigenPanel",
    "EigenScreeningResult",
    "EigenScreeningSummary",
    "EigenSpec",
    "FormationRecord",
    "OuFit",
    "ReversalBook",
    "ThresholdSet",
    "build_cross_section_signal",
    "build_eigen_disclosure",
    "build_eigen_panel",
    "build_reversal_book",
    "compute_confound_diagnostics",
    "correlation_from_standardized",
    "cost_sensitivity",
    "default_eigen_config",
    "fit_ou_ar1",
    "implied_half_life_days",
    "next_position",
    "run_eigen_replay",
    "run_eigenportfolio_screening",
    "screen_eigenportfolio",
    "select_n_factors",
    "standardize_returns",
    "summarize_edge_half_spreads",
]
