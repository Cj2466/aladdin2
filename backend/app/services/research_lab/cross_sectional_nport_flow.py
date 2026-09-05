"""FLOW-INDUCED TRADING (FIT): one pre-declared cross-sectional US equity
family testing Lou (2012)'s mutual-fund flow-induced-trading measure, built
from real SEC Form N-PORT bulk data, in BOTH of the two forms the paper
defines — realized FIT (his Eq.(3)) and EXPECTED FIT (his Eq.(5)) — under one
12-spec grid and one DSR denominator.

=======================================================================
1. THE SOURCE, AND WHAT IT ACTUALLY CLAIMS
=======================================================================

PRIMARY. Lou, Dong, "A Flow-Based Explanation for Return Predictability",
Review of Financial Studies 25(12), 2012, pp. 3457-3489. Every equation and
every coefficient below was read off the author's own working paper, fetched
live from https://personal.lse.ac.uk/loud/flows.pdf on 2026-09-05 and
converted to text (2,230 lines) — never reconstructed from memory, per
CLAUDE.md's standing rule.

    Section 3.2, Eq.(3), quoted verbatim:

        FIT_j,t = [ sum_i shares_i,j,t-1 * flow_i,t * PSF_i,t-1 ]
                  / [ sum_i shares_i,j,t-1 ]

      "where flow_i,t is the dollar flow to fund i in quarter t scaled by the
       fund's lagged total net assets, and shares_i,j,t-1 is the number of
       shares held by mutual fund i at the end of the previous quarter.
       PSF_i,t-1 is the partial scaling factor, computed based on the
       regression specifications shown in columns 1 and 7 of Table II."

    Section 3.3.2, Eq.(5), quoted verbatim:

        E_t[FIT_j] = [ sum_i shares_i,j,t * E_t[flow_i] * PSF_i,t ]
                     / [ sum_i shares_i,j,t ]

      "where E_t[flow_i] is the expected capital flow to mutual fund i
       conditional on fund performance measured at the end of period t. For
       most part of the paper, expected flows are constructed from lagged
       four-factor fund alpha."

THE CLAIM THIS FAMILY WAS BRIEFED WITH DID NOT SURVIVE READING THE PAPER, and
that correction is recorded here rather than quietly absorbed. This family's
build brief stated that "Lou then shows FIT positively forecasts the following
year's returns for the stocks with the highest FIT". THE PAPER SHOWS THE
OPPOSITE FOR *FIT*. From Table III Panel B (equal-weighted, 10 minus 1 decile,
monthly returns), read off the fetched paper:

    Qtr 0 (the FORMATION quarter)  +1.73%/mo  (t =  7.77)
    Qtrs 1-4 (the FOLLOWING YEAR)  -0.03%/mo  (t = -0.17)
    Qtrs 5-8                       -0.40%/mo  (t = -2.46)
    Qtrs 5-12                      -0.30%/mo  (t = -2.70)

and Lou's own prose, verbatim: "the difference in equal-weighted returns
between the top and bottom deciles ranked by FIT is 5.19% (t = 7.77) in the
ranking quarter. While the return spread is indistinguishable from zero in the
following year, it is -7.20% (t = -2.70) in years two and three combined."

So realized FIT's large positive spread is CONTEMPORANEOUS with the quarter
whose flows define it, and is therefore not tradeable at all — you would have
to know the quarter's fund flows before the quarter happened. The paper's
actual FORWARD-LOOKING claim is E[FIT] (Table V Panel A): "+2.52% (t = 3.96)
in the quarter following portfolio formation and 5.28% (t = 2.63) in the
following year", reversing to "-5.67% (t = -2.17) in quarters six to twelve".

This family therefore tests BOTH measures, pre-declared together in ONE grid
(section 5). Testing only FIT would be running a test the source itself
predicts must come back flat; testing only E[FIT] would drop the measure the
brief asked for. Both, one denominator, decided before any number was
computed.

MECHANISM. Vayanos & Woolley ("An Institutional Theory of Momentum and
Reversal", RFS 26(5), 2013, pp. 1087-1145) model the same fund-flow trading
pressure as the common cause of short-run momentum and long-run reversal.
Neither paper's mechanism is tested here — this family tests only whether the
measure sorts returns on this project's universe and window.

=======================================================================
2. THE DATA, AND THE 60-DAY WALL THAT SHAPES EVERYTHING
=======================================================================

Lou used CDA/Spectrum quarterly mutual-fund holdings 1980-2006. That database
is not available here. SEC Form N-PORT is, free, and carries both of Eq.(3)'s
raw ingredients — per-fund per-security prior-quarter share counts and
per-fund period flow. Two prior scoping runs established this in detail and
are NOT re-derived here:

  * data/research_runs/nport_flow_feasibility_2026-09-05.txt — N-PORT is real,
    free, bulk-downloadable, covers Oct 2019 to present, and covers open-end
    funds + closed-end funds + UIT ETFs (~83% of the $39.2tn registered-fund
    industry by AUM), i.e. Lou's own scope, not a narrower one.
  * data/research_runs/nport_flow_definition_resolution_2026-09-05.txt — on
    49,705 real fund-quarters, the flow definition to use is Item B.6.a minus
    Item B.6.c (EXTERNAL net flow, excluding reinvested distributions), which
    is ALGEBRAICALLY Lou's own Eq.(1) estimand under his own stated
    reinvestment assumption.

THE 60-DAY PUBLICATION WALL. SEC Release 33-10231 (2016), verbatim: N-PORT
information "will not be made public until 60 days after the end of the third
month of the fund's fiscal quarter." Consequences this family is built around
rather than around which it argues:

  (a) FIT_j,t is not merely non-tradeable because Lou's own return spread is
      contemporaneous — it is not even OBSERVABLE until ~60 days into quarter
      t+1. Both facts point the same way and neither is assumed: every panel
      value here is gated on the real FILING_DATE of every filing that
      contributed to it (section 3).
  (b) The measure must be recomputed as filings arrive, not on a calendar
      quarter grid, because funds have STAGGERED FISCAL quarters (a January
      fiscal-quarter fund and a December one publish two months apart). This
      family therefore snapshots the measure at each MONTH END and lets the
      harness's step frame carry it forward — see build_flow_panels.

HISTORY DEPTH, stated as the binding constraint it is: usable public N-PORT
runs Oct 2019 to now, so this family's formations span roughly 2020-2026 —
about six years, against Lou's twenty-seven. That is the single biggest reason
to expect low power here, and it cannot be fixed with more work.

=======================================================================
3. POINT-IN-TIME CONSTRUCTION
=======================================================================

At each month-end snapshot date D, for each fund SERIES:

  CURRENT filing = the filing with the latest REPORT_DATE among those with
      FILING_DATE <= D; among filings sharing that report date (an NPORT-P/A
      amendment supersedes its original) the one with the latest FILING_DATE
      <= D. An amendment therefore takes effect from ITS OWN filing date and
      never rewrites history before it.
  PREVIOUS filing = the same series' filing with the largest REPORT_DATE
      strictly less than the current one's, again FILING_DATE <= D.
  Both are REFUSED unless the two report dates are one fiscal quarter apart
  (80..100 calendar days) and the current report date is no more than
  MAX_REPORT_STALENESS_DAYS old at D.

  flow_i = (Item B.6.a - Item B.6.c, summed over the current filing's three
            months) / (PREVIOUS filing's NET_ASSETS)

  which is Lou's "dollar flow to fund i in quarter t scaled by the fund's
  lagged total net assets", with the resolved definition substituted for his
  TNA-inferred proxy.

WHY LOOK-AHEAD IS STRUCTURALLY IMPOSSIBLE HERE, twice over: the panel cell for
snapshot D is built only from filings whose real FILING_DATE is <= D, and the
resulting step frame rides CrossSectionalData.fundamental_signal, which the
harness slices to rows <= the formation date before any signal function sees
it.

SPLIT ADJUSTMENT, and why it is load-bearing rather than housekeeping. Eq.(3)
sums SHARE COUNTS across funds. Under calendar-aligned quarterly holdings a
stock split would cancel between numerator and denominator, because every
fund's count would be measured on the same date. N-PORT fiscal quarters are
NOT aligned: fund A's t-1 may be 31 December and fund B's 31 January, so a
2-for-1 split on 15 January doubles B's count relative to A's for the same
economic position, and the weighted average silently over-weights B. Every
share count is therefore restated onto a common (latest) split basis using the
real per-ticker split history YFinanceProvider.get_market_cap_basis returns.

=======================================================================
4. THE PARTIAL SCALING FACTOR — THE ONE REAL MECHANISM-FIDELITY DECISION
=======================================================================

Lou's Eq.(2) panel regression is

    trade_i,j,t = b0 + b1*flow_i,t + g2*X + g3*flow_i,t*X + e

with trade_i,j,t = shares_i,j,t / shares_i,j,t-1 - 1 (split adjusted), and the
PSF is the implied marginal propensity to scale holdings per unit of flow,
b1 + g3*X. He specifies "columns 1 and 7 of Table II". Read off the fetched
paper's Table II:

    column 1 (OUTFLOW sample, univariate):   intercept -0.059, flow 0.970 (t 16.82)
    column 5 (INFLOW  sample, univariate):   intercept  0.020, flow 0.618 (t 15.78)
    column 7 (INFLOW, portfolio-average X):  flow 0.858 (t 10.57),
        flow x avg ownership share  -21.337 (t -3.20),
        flow x avg effective spread -51.076 (t -3.01)

CORRECTION TO THIS FAMILY'S OWN BRIEF, recorded rather than smoothed over: the
brief (and the earlier feasibility report) quoted the inflow PSF as "0.62",
citing Lou's own sentence "managers invest only 62 (t = 15.78) cents out of
each dollar of inflow in their existing holdings". That sentence describes
column 5. Lou's Eq.(3) says PSF comes from column 7, whose flow coefficient is
0.858, not 0.618. The two are different numbers from different specifications
and the paper is unambiguous about which one Eq.(3) uses.

THE DECISION MADE HERE, and its justification:

  ADOPTED: Lou's own PUBLISHED UNIVARIATE coefficients — column 1 for
  outflows (PSF = 0.970) and column 5 for inflows (PSF = 0.618) — as the
  headline PSF, i.e. a two-valued constant depending only on the SIGN of the
  fund's flow.

  (a) WHY NOT COLUMN 7 AS LOU SPECIFIES. Column 7's PSF is
      0.858 - 21.337*avgOwnershipShare_i - 51.076*avgEffectiveSpread_i, and
      NEITHER regressor is reconstructible here. avgOwnershipShare needs
      shares outstanding for every position in the fund's WHOLE portfolio
      (foreign equities, bonds, derivatives included); avgEffectiveSpread is,
      per Lou's own Table II note, "the effective half bid-ask spread
      estimated from the Basic Market-Adjusted model as described in
      Hasbrouck (2006, 2009)", a Gibbs-sampler estimator this project does not
      implement — and the estimator it DOES have (Ardia-Guidotti-Kroencke
      EDGE) is documented in spread_estimator.py as unreliable as a LEVEL for
      exactly the large-cap regime here, which is precisely what a -51 level
      loading would need. Substituting one spread estimator for another inside
      a coefficient calibrated on the first would be a formula-from-memory
      error wearing a citation.
      Lou himself sanctions the fallback, footnote 9, verbatim: "The main
      results of the paper are not sensitive to the particular choice of PSF.
      Using specifications in other columns of Table II yields similar return
      patterns."

  (b) WHY NOT RE-ESTIMATE EQ.(2) ON THIS PROJECT'S OWN N-PORT PANEL, which
      would otherwise match this project's measure-don't-assume preference
      (borrow_cost.py, spread_estimator.py). Because the PSF is applied to
      form portfolios ACROSS the same sample it would be fitted on: a
      full-sample re-estimate is in-sample look-ahead inside a predictive
      signal, and the expanding-window alternative is dominated by estimation
      noise over the ~24 usable quarters this sample has. Lou reports
      (footnote 9) that a rolling-window PSF gives "virtually identical
      results", so the measured upside is small and the look-ahead risk is
      not. The published coefficients are EXOGENOUS to this sample, which is
      the property that matters most here.

  (c) WHAT IS DONE INSTEAD, so the choice is checked rather than merely
      argued: Lou's univariate Eq.(2) IS re-estimated on this project's own
      N-PORT panel and REPORTED (estimate_partial_scaling_factor below), at
      the cost of zero additional trials, so a reader can see whether
      2019-2026 managers behave like Lou's 1980-2006 ones. And PSF source is
      a pre-declared COST-STYLE SENSITIVITY ARM (section 6): the whole grid is
      re-scored under the re-estimated PSF and under the perfect-scaling
      benchmark PSF == 1, Sharpe only, NOT new trials.

      AND THAT RE-ESTIMATION IS WHERE THIS FAMILY'S FIRST RUN WAS WRONG, which
      is recorded here rather than quietly repaired. Eq.(2)'s dependent
      variable is structurally censored at -1 below and unbounded above, and
      the untreated OLS on this project's real panel returned outflow -744.2
      and inflow -136.2 with R-squared 0.0000 — decided entirely by a handful
      of positions INITIATED from a residual stake (the realised maximum is
      +776,631, a fund that went from about one share to about 776,000). That
      was published in the first run's report as a "measured" number before
      being caught. See MAX_ABS_TRADE_FOR_PSF for the bound now applied, the
      three treatments reported side by side, and the honest note that the
      bound was chosen after seeing the failure.

      THE PRE-REGISTRATION IS WHAT CONTAINED THAT MISTAKE, and that is the
      argument for (b) restated as evidence rather than as reasoning: because
      the headline PSF was fixed to Lou's published constants BEFORE any of
      this was computed, a defect in the re-estimation could only ever damage a
      disclosure and a sensitivity arm. Had the re-estimate been the headline,
      the family's entire result would have been built on a sign-flipped
      scaling factor.

  DISCLOSED CONSEQUENCE OF THE UNIVARIATE FORM. With PSF constant within each
  flow sign, the PSF's entire effect on Eq.(3) is to weight outflow dollars
  0.970/0.618 = 1.57x more heavily than inflow dollars. That is a real and
  intended asymmetry (Lou's own finding: managers must sell pro-rata to fund
  redemptions but reinvest only part of an inflow), not a free parameter.

THE MERGER TERM CANNOT BE REPRODUCED, and this is a permanent, irreducible
fidelity gap for any N-PORT build. Lou's Eq.(1) carries an MGN_i,t term, "the
increase in TNA due to fund mergers in quarter t", which he SUBTRACTS. Form
N-PORT's Item B.6 instruction does the opposite, verbatim: "For mergers and
other acquisitions, include in the value of shares sold any transaction in
which the Fund acquired the assets of another investment company". There is no
field separating merger-driven issuance from ordinary subscriptions under ANY
N-PORT flow definition. So a fund that absorbs another fund reads as a large
external inflow that was not an investor decision. This is NOISE IN THE FLOW
MEASURE that cannot be removed here; it is logged, not fixed, and it biases
toward finding LESS signal, not more.

=======================================================================
5. THE PRE-DECLARED GRID
=======================================================================

    measure {fit, expected_fit}                 2
  x holding period {63, 126, 252} days          3
  x rank fraction {decile, quintile}            2
  = 12 definitions, long_short throughout.

n_trials = 12, this family's own denominator, raised to the project-wide
pooled figure by global_effective_n.dsr_n_trials() inside the harness, and
reported at every N Policy D requires (section 7).

HOLDING PERIODS. 63 trading days is one quarter — the cadence at which the
underlying data itself refreshes, and the horizon of Lou's own Table V
"quarter following portfolio formation" result. 252 is his "following year".
126 sits between them. A 21-day hold is deliberately EXCLUDED: the ranking
variable is refreshed monthly at best and quarterly in substance, so a monthly
hold re-pays turnover on an almost unchanged ranking — the same exclusion, for
the same reason, as cross_sectional_quality.py section 4.

BOTH MEASURES IN ONE GRID, following cross_sectional_asset_growth.py's
departure from the NOA pair: the alternative is to run FIT, see it come back
flat exactly as Lou's Table III says it must, and only then pre-declare
E[FIT] — a sequential search whose second stage would have to carry the
first's trials anyway. Declaring both up front costs the same denominator and
buys an honest one.

LEG WEIGHTING is the harness default "magnitude". VALUE weighting is NOT in
the grid even though Lou reports value-weighted results alongside
equal-weighted ones (his Table III Panel C), because adding it would be a
fourth searched axis for a robustness point, and the paper's own value-weighted
numbers are not qualitatively different from its equal-weighted ones.

=======================================================================
6. COSTS — FED INTO THE DSR, NOT DISCLOSED BESIDE IT
=======================================================================

TURNOVER: cost_model="edge_spread" against the CALIBRATED per-ticker half-
spread frame (spread_estimator.build_calibrated_half_spread_frame), the same
basis cross_sectional_lazy_prices.py adopted on 2026-09-05 — EDGE used as a
relative-cost RANKER scaling an externally published S&P 500 median level,
with a per-ticker $0.01-tick floor. The raw uncalibrated EDGE frame is ~19x
too expensive on this project's own panel and is not used.

BORROW: financing_bps_per_year = 17.0, i.e. borrow_cost.
financing_bps_for_long_short_book(34.0) — the D'Avolio (2002) /
Beneish-Lee-Nichols (2015) GENERAL COLLATERAL rate of 34 bps/yr charged on the
short leg alone. Justified for THIS universe by D'Avolio p.273 verbatim: "S&P
500 constituents, provided in excess supply by indexing lenders, are almost
always general collateral." This is NOT the 0.0 every other single-stock
equity family in this project charges; a new family with no live registration
to park has no reason to inherit that disclosed optimism.

PRE-DECLARED SENSITIVITY LADDER, Sharpe AND DSR recomputed, no new trials:
short-leg borrow at {0, 34, 430} bps/yr, the last being D'Avolio Table 3's
value-weighted mean fee for "specials" — an explicit worst case in which every
short-leg name is hard to borrow. A family whose verdict flips across that
ladder is reported as flipping.

=======================================================================
7. PASS/FAIL, FIXED BEFORE RESULTS
=======================================================================

Policy D's two-tier rule (registration_scorecard.policy_d_verdict) against the
0.95 VALIDATED-EDGE bar this project's pre-registrations use:

  DEFINITE NEGATIVE  best spec's DSR < 0.95 at n_local = 12.
  UNRESOLVED         clears 0.95 at n_local but not at the pooled N.
  PASS               clears 0.95 at every N measured (12, 481, 857).

Cost realism is inside that DSR, not beside it: the headline DSR is computed
on returns already net of the calibrated spread cost and the GC borrow charge.

THE HONEST PRIOR, written before any result: LOW. Six years of history, a
measure whose realized form the source paper itself shows is flat over the
following year, a 60-day publication wall between the data and the trade, and
a large-cap universe. An honest negative is the expected outcome and is a
useful one.
"""

from __future__ import annotations

import logging
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial
from itertools import pairwise

import numpy as np
import pandas as pd

from app.services.market_data.fama_french_provider import load_carhart_four_factors
from app.services.market_data.form13f_provider import (
    Form13FProvider,
    build_cusip_ticker_map,
    parse_ftd_archive,
)
from app.services.market_data.nport_provider import (
    FundQuarterFiling,
    NportLoadDiagnostics,
    NportProvider,
    build_fund_quarter_filings,
    build_holding_rows,
    parse_float,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    screen_cross_sectional_universe,
)
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.preservation_score import compute_preservation_metrics
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)
from app.services.research_lab.spread_estimator import (
    build_calibrated_half_spread_frame,
)

logger = logging.getLogger(__name__)

NPORT_FLOW_FAMILY_KEY = "nport_flow_fit"
NPORT_FLOW_FAMILY = "nport_flow_fit"

NPORT_FLOW_CITATION = (
    "Lou, 'A Flow-Based Explanation for Return Predictability' (Review of Financial Studies "
    "25(12), 2012, pp. 3457-3489), Eq.(3) flow-induced trading and Eq.(5) expected "
    "flow-induced trading, with the partial scaling factor from Table II columns 1 and 5 and "
    "fund flow taken as SEC Form N-PORT Item B.6.a - Item B.6.c (the resolved equivalent of "
    "Lou's own Eq.(1) estimand); mechanism per Vayanos & Woolley, 'An Institutional Theory of "
    "Momentum and Reversal' (RFS 26(5), 2013, pp. 1087-1145)"
)


# --- the partial scaling factor ----------------------------------------------


@dataclass(frozen=True)
class PartialScalingFactor:
    """Lou (2012) Eq.(2)'s implied marginal propensity to scale existing
    holdings per unit of fund flow, in the UNIVARIATE form (no X vector), so
    the factor depends only on the SIGN of the flow.

    See module docstring section 4 for why the univariate form and not Lou's
    stated column 7, and why his published coefficients rather than a
    re-estimate."""

    outflow: float
    inflow: float
    source: str

    def __post_init__(self) -> None:
        if not np.isfinite(self.outflow) or not np.isfinite(self.inflow):
            raise ValueError("partial scaling factors must be finite")

    def for_flow(self, flow: float) -> float:
        """The scaling factor a fund with this flow gets.

        A flow of EXACTLY zero takes the inflow branch. It contributes exactly
        zero to Eq.(3)'s numerator either way (the term is flow * PSF), so the
        choice cannot affect any result; it is fixed here only so the function
        is total rather than undefined at a point."""
        return self.outflow if flow < 0.0 else self.inflow


# Lou (2012) Table II, read off the fetched working paper:
#   column 1, OUTFLOW sample, univariate: coefficient on flow 0.970 (t = 16.82)
#   column 5, INFLOW  sample, univariate: coefficient on flow 0.618 (t = 15.78)
# His own prose for the second: "managers invest only 62 (t = 15.78) cents out
# of each dollar of inflow in their existing holdings"; for the first: "the
# coefficient on flow in a univariate regression is 0.97 (t = 16.82), which is
# not statistically different from one."
LOU_PUBLISHED_PSF = PartialScalingFactor(
    outflow=0.970,
    inflow=0.618,
    source="Lou (2012) Table II, columns 1 (outflow) and 5 (inflow), univariate specification",
)

# The perfect-scaling benchmark Lou's section 3.1 sets up and rejects: a
# manager who expands or liquidates every position exactly proportionally,
# i.e. "we expect b1 to be equal to one and g3 to be a zero vector". Used ONLY
# as a pre-declared sensitivity arm, never as the headline.
PERFECT_SCALING_PSF = PartialScalingFactor(
    outflow=1.0, inflow=1.0, source="perfect-scaling benchmark (Lou 2012 section 3.1), PSF == 1"
)


# --- Eq.(3) / Eq.(5), the kernel ---------------------------------------------


def flow_induced_trading(
    shares_by_fund: Mapping[str, float],
    flow_by_fund: Mapping[str, float],
    psf: PartialScalingFactor,
) -> float | None:
    """Lou (2012) Eq.(3) / Eq.(5) for ONE stock at ONE date.

        FIT = sum_i shares_i * flow_i * PSF(flow_i) / sum_i shares_i

    `shares_by_fund` are the share counts the measure weights by — Eq.(3)'s
    t-1 counts or Eq.(5)'s t counts; the arithmetic is identical and the
    caller decides which. Funds present in `shares_by_fund` but absent from
    `flow_by_fund` are dropped from BOTH sums, never treated as zero-flow: a
    fund whose flow is unobservable contributes no information to the
    numerator and must not dilute the denominator either.

    Returns None when no fund contributes a positive share count, which is the
    honest answer for "no mutual fund is observed holding this stock here" and
    excludes the stock from ranking.

    HAND-CHECKABLE KNOWN ANSWER, which is also pinned in the tests: two funds
    holding 100 and 300 shares with flows -0.10 and +0.20 under
    LOU_PUBLISHED_PSF give
        numerator   = 100*(-0.10)*0.970 + 300*(0.20)*0.618 = -9.70 + 37.08 = 27.38
        denominator = 400
        FIT         = 0.06845
    """
    numerator = 0.0
    denominator = 0.0
    for fund, shares in shares_by_fund.items():
        if not np.isfinite(shares) or shares <= 0.0:
            continue
        flow = flow_by_fund.get(fund)
        if flow is None or not np.isfinite(flow):
            continue
        numerator += shares * flow * psf.for_flow(flow)
        denominator += shares
    if denominator <= 0.0:
        return None
    return numerator / denominator


def flow_induced_trading_multi(
    shares_by_fund: Mapping[str, float],
    contribution_by_fund: Mapping[str, Sequence[float]],
    n_factors: int,
) -> list[float] | None:
    """Eq.(3)/(5) evaluated for SEVERAL partial scaling factors in one pass over
    the funds.

    `contribution_by_fund` gives, per fund, the pre-multiplied
    `flow_i * PSF(flow_i)` for each factor in a fixed order — the only part of
    the numerator that depends on the factor. Sharing the single pass over the
    fund list (and the single denominator) across factors is what makes the
    pre-declared PSF sensitivity arm affordable: the alternative recomputes the
    same weighted sum once per factor.

    Identical semantics to flow_induced_trading, which stays the reference
    implementation and is what the hand-derived tests check; this function is
    pinned against it on random inputs rather than trusted on inspection."""
    numerators = [0.0] * n_factors
    denominator = 0.0
    for fund, shares in shares_by_fund.items():
        if not np.isfinite(shares) or shares <= 0.0:
            continue
        contributions = contribution_by_fund.get(fund)
        if contributions is None:
            continue
        denominator += shares
        for position in range(n_factors):
            numerators[position] += shares * contributions[position]
    if denominator <= 0.0:
        return None
    return [numerator / denominator for numerator in numerators]


# THE BOUND ON EQ.(2)'s DEPENDENT VARIABLE, and why it is not an arbitrary
# winsorisation.
#
# trade_i,j,t = shares_i,j,t / shares_i,j,t-1 - 1 is STRUCTURALLY BOUNDED BELOW
# AT -1: a fund cannot sell more shares than it holds, so a complete
# liquidation is -1.00 and nothing is worse. It is UNBOUNDED ABOVE, and on this
# project's own real N-PORT panel that asymmetry is not theoretical — measured
# over 2024q1..2024q4, the realised range is
#
#     p0     p1      p25     p50     p75     p99     p99.9    max
#   -1.000 -0.706  -0.050  +0.000  +0.045  +3.334  +43.44   +776,631
#
# The median is 0.0000 and the interquartile range is [-0.05, +0.04] — the
# quantity is perfectly well behaved in the body — but the top tail is
# positions INITIATED from a residual stake (a fund holding ~1 share of an
# issuer and then holding ~776,000). Those are not "percentage trading of an
# existing position", which is what Eq.(2) regresses; and under OLS they alone
# decide the answer. UNTREATED, the fit is destroyed: slope +1.564 for outflows
# and -2.957 for INFLOWS, with R-squared 0.00000 on both sides — a manager who
# supposedly SELLS harder the more money he takes in. That is not a finding, it
# is an artifact, and it was reported as if it were a measurement in this
# family's first run before being caught.
#
# The bound applied is the SYMMETRIC counterpart of the structural lower bound:
# |trade| <= 1, i.e. the position was at most fully liquidated or at most
# doubled. It is the only bound that makes the regression's two tails
# comparable rather than one of them censored by construction and the other
# open. It retains 97.5% (outflow) / 96.3% (inflow) of observations.
#
# HONEST NOTE ON HOW THIS BOUND WAS ARRIVED AT: it was chosen AFTER seeing that
# the untreated fit was degenerate, so it is a post-hoc treatment. Two things
# make that acceptable rather than a silent free parameter. (1) Every treatment
# is reported side by side in the returned stats — untreated, winsorised at
# 1/99, and this bound — so a reader sees the sensitivity instead of one
# selected number. (2) It cannot contaminate the family's headline result,
# because the headline PSF was PRE-REGISTERED as Lou's own published constants
# before any of this was computed; this estimate is a disclosure and a
# sensitivity arm only. That separation is exactly what the pre-registration
# was for.
MAX_ABS_TRADE_FOR_PSF = 1.0


def _ols_with_r_squared(y: np.ndarray, x: np.ndarray) -> tuple[float, float, float]:
    """(intercept, slope, R-squared) for a univariate OLS, or NaNs when the
    design is degenerate."""
    if len(x) < 2:
        return float("nan"), float("nan"), float("nan")
    design = np.column_stack([np.ones_like(x), x])
    beta, _residuals, rank, _sv = np.linalg.lstsq(design, y, rcond=None)
    if rank < design.shape[1]:
        return float("nan"), float("nan"), float("nan")
    residual = y - design @ beta
    total = float(np.sum((y - y.mean()) ** 2))
    r_squared = 1.0 - float(np.sum(residual**2)) / total if total > 0 else float("nan")
    return float(beta[0]), float(beta[1]), r_squared


def estimate_partial_scaling_factor(
    trades_and_flows: Sequence[tuple[float, float]],
    *,
    max_abs_trade: float = MAX_ABS_TRADE_FOR_PSF,
) -> tuple[PartialScalingFactor | None, dict[str, float]]:
    """Re-estimate Lou (2012) Eq.(2) in its UNIVARIATE form on this project's
    own data, separately for the inflow and outflow subsamples:

        trade_i,j,t = b0 + b1 * flow_i,t + e

    `trades_and_flows` is a sequence of (trade, flow) pairs, where trade is
    the split-adjusted percentage change in a fund's share count in one stock
    over one quarter and flow is that fund's own quarter flow as a fraction of
    lagged net assets — exactly Lou's own two variables.

    Returned for DISCLOSURE and as a sensitivity arm, never as the headline
    PSF: see module docstring section 4(b) on why fitting this parameter on the
    same sample it is then applied to would be look-ahead. The returned stats
    carry, for BOTH flow signs, the estimate under three treatments of the
    dependent variable — untreated, winsorised at the 1st/99th percentiles, and
    the |trade| <= max_abs_trade bound this function returns — so the reader
    sees the sensitivity rather than a single selected number. See
    MAX_ABS_TRADE_FOR_PSF above for why the bound exists at all and how it was
    chosen.

    Lou conducts "separate regressions for the inflow and outflow subsamples"
    (his section 3.1) for the stated economic reason that "Managers with
    outflow ... would have to sell their holdings dollar-for-dollar to pay for
    redemptions", so the split is his, not a choice made here. The treatments
    are likewise applied WITHIN each subsample, never pooled across them.
    """
    stats: dict[str, float] = {"max_abs_trade": float(max_abs_trade)}
    coefficients: dict[str, float] = {}
    for name, keep in (("outflow", lambda f: f < 0.0), ("inflow", lambda f: f > 0.0)):
        selected = [(t, f) for t, f in trades_and_flows if keep(f) and np.isfinite(t) and np.isfinite(f)]
        trades = np.array([t for t, _f in selected], dtype=float)
        flows = np.array([f for _t, f in selected], dtype=float)
        stats[f"{name}_n_all"] = float(len(trades))
        if len(trades) < 2:
            coefficients[name] = float("nan")
            for suffix in ("intercept", "slope", "r_squared"):
                for treatment in ("raw", "winsorized", "bounded"):
                    stats[f"{name}_{treatment}_{suffix}"] = float("nan")
            stats[f"{name}_n"] = 0.0
            continue

        # (1) untreated — reported to show what the tail does, never used
        intercept, slope, r_squared = _ols_with_r_squared(trades, flows)
        stats[f"{name}_raw_intercept"] = intercept
        stats[f"{name}_raw_slope"] = slope
        stats[f"{name}_raw_r_squared"] = r_squared

        # (2) winsorised at 1/99 — the conventional treatment, reported
        low, high = np.quantile(trades, 0.01), np.quantile(trades, 0.99)
        intercept, slope, r_squared = _ols_with_r_squared(np.clip(trades, low, high), flows)
        stats[f"{name}_winsorized_intercept"] = intercept
        stats[f"{name}_winsorized_slope"] = slope
        stats[f"{name}_winsorized_r_squared"] = r_squared
        stats[f"{name}_winsor_low"] = float(low)
        stats[f"{name}_winsor_high"] = float(high)

        # (3) |trade| <= max_abs_trade — THE returned estimate
        kept = np.abs(trades) <= max_abs_trade
        intercept, slope, r_squared = _ols_with_r_squared(trades[kept], flows[kept])
        stats[f"{name}_bounded_intercept"] = intercept
        stats[f"{name}_bounded_slope"] = slope
        stats[f"{name}_bounded_r_squared"] = r_squared
        stats[f"{name}_n"] = float(int(kept.sum()))
        stats[f"{name}_retained_fraction"] = float(kept.mean())
        coefficients[name] = slope

    if not np.isfinite(coefficients.get("outflow", float("nan"))) or not np.isfinite(
        coefficients.get("inflow", float("nan"))
    ):
        # A side with no usable observations has no partial scaling factor. It
        # is returned as None rather than as a NaN-carrying PartialScalingFactor
        # so a degenerate estimate cannot be handed to Eq.(3) and quietly turn
        # every FIT value into NaN.
        return None, stats
    return (
        PartialScalingFactor(
            outflow=coefficients["outflow"],
            inflow=coefficients["inflow"],
            source=(
                "re-estimated on this project's own N-PORT panel (Lou Eq.(2), univariate, "
                f"dependent variable bounded to |trade| <= {max_abs_trade:g})"
            ),
        ),
        stats,
    )


# --- point-in-time fund state -------------------------------------------------

# A fund's current and previous public filings must be one fiscal quarter
# apart. A quarter is 90-92 days; the window allows the month-end drift a
# 52/53-week fiscal calendar produces without admitting a two-quarter gap
# (which would make `flow` a six-month figure divided by a six-month-old
# asset base).
MIN_QUARTER_GAP_DAYS = 80
MAX_QUARTER_GAP_DAYS = 100

# How stale a fund's latest PUBLIC report may be at a snapshot date before that
# fund stops contributing. A quarter (92) plus the statutory 60-day publication
# wall is 152 days; 200 leaves room for a late filer without letting a fund
# that stopped filing altogether keep voting with a year-old book.
MAX_REPORT_STALENESS_DAYS = 200

# Minimum lagged net assets for a fund to contribute. The flow-definition
# resolution run's own closing instruction, verbatim: "Apply a size floor.
# Micro-funds produce flow ratios up to 911x TNA." $10mm is the floor that run
# used for its own regressions and it retained 92% of its panel.
MIN_FUND_NET_ASSETS = 1e7

# A fund-quarter whose external flow exceeds this fraction of lagged net
# assets is refused outright. 2.0 = the fund tripled or was more than wiped out
# in one quarter; at that point the ratio is measuring a merger, a seed
# redemption or a reporting error, not investor flow, and the merger term is
# exactly the one Lou removes and N-PORT cannot (module docstring section 4).
MAX_ABSOLUTE_FLOW = 2.0

# A stock needs at least this many contributing funds at a snapshot for its
# measure to be ranked. Eq.(3) is an average over "the entire mutual fund
# industry as one giant fund" (Lou's own reading); an average over two funds is
# not that, it is two funds.
MIN_FUNDS_PER_STOCK = 5

# Months of fund returns required before a four-factor alpha is computed.
# Lou: "the monthly Carhart four-factor alpha computed from the fund's returns
# in the previous year" (Table IV note) — twelve months, not a shorter window.
ALPHA_WINDOW_MONTHS = 12

# Minimum (alpha, next-quarter flow) training pairs before the expected-flow
# regression is fitted at a snapshot. Below this the first stage is noise and
# every fund's expected flow would be an artifact of a handful of funds.
MIN_EXPECTED_FLOW_TRAINING_PAIRS = 200


@dataclass(frozen=True)
class FundSnapshot:
    """One fund series' point-in-time state at a snapshot date: the flow it
    reported for its most recent PUBLIC quarter, and the two filings that
    supply Eq.(3)'s t-1 and Eq.(5)'s t share counts."""

    series_id: str
    current_accession: str
    previous_accession: str
    report_date: date
    previous_report_date: date
    flow: float
    net_assets: float
    previous_net_assets: float


@dataclass
class FlowPanelDiagnostics:
    """Every refusal counted, never silent."""

    n_snapshot_dates: int = 0
    n_series_seen: int = 0
    n_refused: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    n_fund_snapshots: int = 0
    n_fit_cells: int = 0
    n_expected_fit_cells: int = 0
    n_alpha_estimates: int = 0
    expected_flow_fits: list[dict[str, float]] = field(default_factory=list)

    def refuse(self, reason: str, count: int = 1) -> None:
        self.n_refused[reason] += count


def _series_index(filings: Sequence[FundQuarterFiling]) -> dict[str, list[FundQuarterFiling]]:
    by_series: dict[str, list[FundQuarterFiling]] = defaultdict(list)
    for filing in filings:
        by_series[filing.series_id].append(filing)
    for rows in by_series.values():
        rows.sort(key=lambda f: (f.filing_date, f.report_date))
    return by_series


def fund_snapshots_as_of(
    by_series: Mapping[str, list[FundQuarterFiling]],
    as_of: date,
    diagnostics: FlowPanelDiagnostics,
) -> dict[str, FundSnapshot]:
    """Each fund series' Eq.(3) inputs computed from filings PUBLIC at `as_of`.

    Filings are pre-sorted by FILING_DATE, so the public subset is a prefix and
    is found by bisection rather than by rescanning every fund's whole history
    at every snapshot."""
    out: dict[str, FundSnapshot] = {}
    for series_id, rows in by_series.items():
        cut = bisect_right([f.filing_date for f in rows], as_of)
        public = rows[:cut]
        if len(public) < 2:
            diagnostics.refuse("fewer_than_two_public_filings")
            continue
        # Latest report date among public filings; among ties (an amendment
        # superseding its original) the latest-filed wins.
        current = max(public, key=lambda f: (f.report_date, f.filing_date))
        if (as_of - current.report_date).days > MAX_REPORT_STALENESS_DAYS:
            diagnostics.refuse("latest_public_report_too_stale")
            continue
        earlier = [f for f in public if f.report_date < current.report_date]
        if not earlier:
            diagnostics.refuse("no_prior_public_report")
            continue
        previous = max(earlier, key=lambda f: (f.report_date, f.filing_date))
        gap = (current.report_date - previous.report_date).days
        if not MIN_QUARTER_GAP_DAYS <= gap <= MAX_QUARTER_GAP_DAYS:
            diagnostics.refuse("report_dates_not_one_quarter_apart")
            continue
        if previous.net_assets < MIN_FUND_NET_ASSETS:
            diagnostics.refuse("fund_below_size_floor")
            continue
        flow = current.external_flow_dollars / previous.net_assets
        if not np.isfinite(flow):
            diagnostics.refuse("non_finite_flow")
            continue
        if abs(flow) > MAX_ABSOLUTE_FLOW:
            diagnostics.refuse("flow_exceeds_absolute_cap")
            continue
        out[series_id] = FundSnapshot(
            series_id=series_id,
            current_accession=current.accession,
            previous_accession=previous.accession,
            report_date=current.report_date,
            previous_report_date=previous.report_date,
            flow=flow,
            net_assets=current.net_assets,
            previous_net_assets=previous.net_assets,
        )
    diagnostics.n_fund_snapshots += len(out)
    return out


# --- split adjustment ---------------------------------------------------------


def build_split_adjustment(
    splits_by_ticker: Mapping[str, pd.Series], index: pd.DatetimeIndex
) -> dict[str, pd.Series]:
    """Per-ticker CUMULATIVE FORWARD split factor: the number by which a share
    count observed on date d must be MULTIPLIED to state it on the panel's
    final (latest) basis.

    A 2-for-1 split on date s means one pre-split share becomes two, so a count
    observed BEFORE s must be doubled to be comparable with counts observed
    after it. The factor is therefore the product of every split ratio with
    ex-date strictly AFTER d, and is exactly 1.0 from the last split onward.

    Only relative comparability matters — Eq.(3) is a ratio of two sums of the
    same restated counts — so any common basis works and the latest one is
    chosen because it makes the factor 1.0 for the most recent, most numerous
    observations.

    Hand check: a single 4-for-1 split on 2020-08-31 gives factor 4.0 on
    2020-06-30 and 1.0 on 2020-12-31."""
    adjustments: dict[str, pd.Series] = {}
    for ticker, events in splits_by_ticker.items():
        ratios = events[events > 0].sort_index()
        if ratios.empty:
            continue
        # For a date d the factor is the product of every split ratio with
        # ex-date strictly AFTER d, i.e. the reverse cumulative product.
        reversed_cumulative = ratios[::-1].cumprod()[::-1]
        factor = pd.Series(1.0, index=index, dtype=float)
        # DESCENDING ex-date order is load-bearing, not stylistic. Each
        # assignment paints every row before its ex-date, so an ascending pass
        # would let a LATER split overwrite an EARLIER one's larger factor and
        # silently under-restate every count before the earlier split. Caught
        # by the two-split test, which an ascending pass fails.
        for ex_date, cumulative in sorted(reversed_cumulative.items(), reverse=True):
            factor.loc[factor.index < pd.Timestamp(ex_date)] = float(cumulative)
        adjustments[ticker] = factor
    return adjustments


def split_factor_on(
    adjustments: Mapping[str, pd.Series], ticker: str, when: date
) -> float:
    """The multiplier for a share count observed on `when`. 1.0 for a ticker
    with no recorded splits, or for a date at/after the panel's last split."""
    series = adjustments.get(ticker)
    if series is None or series.empty:
        return 1.0
    stamp = pd.Timestamp(when)
    position = series.index.searchsorted(stamp, side="right") - 1
    if position < 0:
        return float(series.iloc[0])
    return float(series.iloc[position])


# --- four-factor alpha and expected flow --------------------------------------


def fund_monthly_returns(
    filings: Sequence[FundQuarterFiling],
    returns_by_accession: Mapping[str, list[tuple[float, float, float]]],
) -> dict[str, dict[pd.Timestamp, float]]:
    """{series_id: {month_end: fund return}} in DECIMAL units.

    Form N-PORT Item B.5.a reports "Monthly total returns of the Fund for each
    of the preceding three months", per share CLASS, as PERCENTAGES. The three
    map to the report month and the two before it — the same ordering the
    flow-definition resolution run compounded into a quarterly return.

    A multi-class fund is collapsed to the MEAN across its classes, and that is
    a DISCLOSED APPROXIMATION rather than a choice: Form N-PORT reports returns
    per class but reports NO class-level assets, so a true NAV-weighted blend
    is not computable from N-PORT alone (measured and stated in
    nport_flow_definition_resolution_2026-09-05.txt Q4(a), which also refutes
    class blending as a driver of any material disagreement).
    """
    out: dict[str, dict[pd.Timestamp, float]] = defaultdict(dict)
    for filing in filings:
        rows = returns_by_accession.get(filing.accession)
        if not rows:
            continue
        report_month = pd.Timestamp(filing.report_date) + pd.offsets.MonthEnd(0)
        months = [report_month - pd.offsets.MonthEnd(2), report_month - pd.offsets.MonthEnd(1), report_month]
        for position, month in enumerate(months):
            values = [row[position] for row in rows if np.isfinite(row[position])]
            if not values:
                continue
            out[filing.series_id][month] = float(np.mean(values)) / 100.0
    return {series: dict(sorted(months.items())) for series, months in out.items()}


def four_factor_alpha(
    monthly_returns: Mapping[pd.Timestamp, float],
    factors: pd.DataFrame,
    through: pd.Timestamp,
    *,
    window_months: int = ALPHA_WINDOW_MONTHS,
) -> float | None:
    """Monthly Carhart (1997) four-factor alpha over the `window_months` months
    ending at `through`.

        r_i - rf = alpha + b1*MKTRF + b2*SMB + b3*HML + b4*MOM + e

    `factors` must carry mkt_rf, smb, hml, mom, rf in DECIMAL units, month-end
    indexed. Returns None unless the full window is available with matching
    factor rows — a short window would silently make alpha an artifact of
    however many months the fund happened to report.

    Lou, Table IV note, verbatim on the variable being reproduced here: "the
    monthly Carhart four-factor alpha computed from the fund's returns in the
    previous year"."""
    months = [m for m in monthly_returns if m <= through]
    if len(months) < window_months:
        return None
    window = sorted(months)[-window_months:]
    if (through - window[0]).days > 400:
        # A 12-observation window spanning more than ~13 months means the fund
        # has reporting gaps; the "previous year" it would describe is not one.
        return None
    rows = factors.reindex(pd.DatetimeIndex(window))
    if rows.isna().to_numpy().any():
        return None
    excess = np.array([monthly_returns[m] for m in window], dtype=float) - rows["rf"].to_numpy()
    design = np.column_stack(
        [
            np.ones(len(window)),
            rows["mkt_rf"].to_numpy(),
            rows["smb"].to_numpy(),
            rows["hml"].to_numpy(),
            rows["mom"].to_numpy(),
        ]
    )
    if not np.isfinite(excess).all() or not np.isfinite(design).all():
        return None
    beta, _residuals, rank, _sv = np.linalg.lstsq(design, excess, rcond=None)
    if rank < design.shape[1]:
        return None
    return float(beta[0])


def fit_expected_flow_model(
    pairs: Sequence[tuple[float, float]],
) -> tuple[float, float, dict[str, float]] | None:
    """Lou (2012) Eq.(4) in the univariate form his Eq.(5) uses:

        flow_i,t+1 = b0 + b1 * alpha_i,t + e

    `pairs` are (alpha, realized next-quarter flow) observations, and the
    caller must supply only pairs whose OUTCOME filing was already public at
    the snapshot date — this function has no way to check that and does not
    try to.

    Lou's footnote 10 states verbatim why lagged FLOWS are excluded from this
    particular specification even though his Table IV columns 2-6 include them:
    "I exclude lagged fund flows to forecast future flows in Equation (5),
    because lagged flow-induced trading has no predictive power for stock
    returns in the subsequent year." Reproduced, not simplified away.

    HIS PUBLISHED COEFFICIENTS ARE DELIBERATELY NOT USED. Table IV column 1
    (Fama-MacBeth, univariate) gives intercept 0.028 and slope 4.827 (t 9.67).
    The SLOPE is a behavioural flow-performance sensitivity; the INTERCEPT is
    an average quarterly flow, and +2.8% per quarter is a 1980-2006
    fund-industry-growth number. Carrying it into a 2019-2026 sample in which
    active mutual funds are in persistent net redemption would put almost every
    fund on the inflow side of the PSF branch, which is factually wrong about
    this sample. Unlike the PSF (module docstring section 4), this quantity IS
    a forecast by construction, so estimating it from data available at the
    snapshot is what Lou does, not a departure from it.

    Returns None when the sample is too small or degenerate to fit."""
    if len(pairs) < MIN_EXPECTED_FLOW_TRAINING_PAIRS:
        return None
    alphas = np.array([a for a, _f in pairs], dtype=float)
    flows = np.array([f for _a, f in pairs], dtype=float)
    finite = np.isfinite(alphas) & np.isfinite(flows)
    alphas, flows = alphas[finite], flows[finite]
    if len(alphas) < MIN_EXPECTED_FLOW_TRAINING_PAIRS:
        return None
    design = np.column_stack([np.ones_like(alphas), alphas])
    beta, _residuals, rank, _sv = np.linalg.lstsq(design, flows, rcond=None)
    if rank < design.shape[1]:
        # A constant regressor. np.std() is NOT a sufficient guard here: a
        # column of identical floats can return a tiny non-zero std while
        # lstsq still falls back to its minimum-norm solution and reports a
        # meaningless slope (measured: slope 3.09e-4, R^2 1.1e-16).
        return None
    fitted = design @ beta
    total_ss = float(np.sum((flows - flows.mean()) ** 2))
    residual_ss = float(np.sum((flows - fitted) ** 2))
    return (
        float(beta[0]),
        float(beta[1]),
        {
            "n": float(len(alphas)),
            "intercept": float(beta[0]),
            "slope": float(beta[1]),
            "r_squared": 1.0 - residual_ss / total_ss if total_ss > 0 else float("nan"),
        },
    )


# --- the pre-declared grid ----------------------------------------------------

NPORT_FLOW_MEASURES: tuple[str, ...] = ("fit", "expected_fit")
NPORT_FLOW_HOLDING_DAYS: tuple[int, ...] = (63, 126, 252)
NPORT_FLOW_RANK_FRACTIONS: tuple[tuple[str, float], ...] = (
    ("", 0.1),  # deciles — Lou's own sort
    ("_quintile", 0.2),  # quintile robustness variant
)
NPORT_FLOW_N_TRIALS = (
    len(NPORT_FLOW_MEASURES) * len(NPORT_FLOW_HOLDING_DAYS) * len(NPORT_FLOW_RANK_FRACTIONS)
)

# Trading rows of history the signal needs before its first formation. The
# signal reads only the LAST row of the step frame, so one row would do; 2 is
# kept so the harness's own history-length guard has something to bite on and
# a degenerate one-row view can never be handed to a signal.
NPORT_FLOW_SIGNAL_LOOKBACK_ROWS = 2

# Calendar days of price history fetched before the first formation, purely to
# warm up the 63-day calibrated-spread window. No formation may occur inside
# it (config.formation_start enforces that).
NPORT_FLOW_PRICE_HISTORY_PADDING_CALENDAR_DAYS = 200

# borrow_cost.financing_bps_for_long_short_book(34.0). See module docstring
# section 6: the D'Avolio general-collateral rate on the short leg alone,
# converted to the config's gross-notional base.
NPORT_FLOW_FINANCING_BPS_PER_YEAR = 17.0

# The pre-declared borrow ladder, in SHORT-LEG bps/yr, re-scored Sharpe and DSR
# with no new trials. 0 is this project's standing (known-wrong) optimism, 34
# the general-collateral rate used as the headline, 430 D'Avolio Table 3's
# value-weighted mean fee for specials as an explicit worst case.
NPORT_FLOW_BORROW_LADDER_BPS: tuple[float, ...] = (0.0, 34.0, 430.0)


def _signal_from_frame(history) -> pd.Series:
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "the N-PORT flow signals require CrossSectionalData.fundamental_signal; the spec "
            "must set requires_fundamental_signal=True and the caller must supply the frame."
        )
    row = frame.iloc[-1].astype(float)
    return row.where(np.isfinite(row))


def signal_flow_induced_trading(history) -> pd.Series:
    """Realized FIT (Lou Eq.(3)) at the formation date, read off the
    point-in-time step frame.

    Direction is +1: Lou sorts "stocks into deciles based on FIT in ascending
    order", so the TOP decile is the flow-induced-PURCHASE side, which the
    harness's top-is-long convention puts on the long leg — matching the
    paper's own hedge portfolio, which "goes long in the top decile and short
    in the bottom decile".

    All the real work — the formula, the 60-day publication gate, the split
    restatement, the staleness refusals — is already done in the panel this
    reads. This function only takes the last row of a history view the harness
    has already truncated to rows <= the formation date, which is the
    structural look-ahead guarantee."""
    return _signal_from_frame(history)


def signal_expected_flow_induced_trading(
    history, *, expected_fit_frame: pd.DataFrame
) -> pd.Series:
    """Expected FIT (Lou Eq.(5)) at the formation date. Same direction as
    signal_flow_induced_trading.

    WHY THIS ONE READS A BOUND FRAME RATHER THAN CrossSectionalData.
    fundamental_signal. Both measures are per-ticker step panels and the
    harness carries exactly ONE such field, so a family holding two must bind
    the second into its signal closure. That is not a new pattern here: it is
    exactly how cross_sectional_asset_growth.py's industry-neutral half reads
    its point-in-time SIC bucket panel, and how the FX family reads its
    inverse-vol basis.

    THE LOOK-AHEAD GUARANTEE IS DIFFERENT IN KIND AND IS STATED, NOT ASSUMED.
    For the fundamental_signal frame, the harness truncates the frame before
    the signal ever sees it, so look-ahead is structurally impossible. A bound
    frame gets no such truncation, so this function reads exactly ONE row —
    the view's own last (formation) timestamp — and the frame's cells are
    point-in-time by the panel builder's own contract (build_flow_panels: the
    value at snapshot D is computed only from filings with FILING_DATE <= D).
    That contract is what the tests pin; the pinning is the substitute for the
    structural guarantee, and the two are not the same strength."""
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "signal_expected_flow_induced_trading needs CrossSectionalData.fundamental_signal "
            "for the formation timestamp and the eligible column set; the spec must set "
            "requires_fundamental_signal=True."
        )
    formation_ts = frame.index[-1]
    row = expected_fit_frame.loc[formation_ts].reindex(frame.columns).astype(float)
    return row.where(np.isfinite(row))


def build_nport_flow_family(measure_frames: Mapping[str, pd.DataFrame]) -> list[CrossSectionalSpec]:
    """The 12 pre-declared specs, bound to the two concrete measure panels.

    `measure_frames` maps each measure key to its own point-in-time step frame.
    The frames are runtime DATA — the grid itself (measures x holds x rank
    fractions, and the count of 12) is fixed in the module constants above and
    is never a searched axis. All 12 specs are screened in ONE pass so that
    sigma_sr (the sibling-Sharpe dispersion the DSR benchmark is built from) is
    taken across the whole declared family, not within each half of it."""
    missing = [m for m in NPORT_FLOW_MEASURES if m not in measure_frames]
    if missing:
        raise ValueError(f"no panel supplied for measure(s) {missing}")
    specs: list[CrossSectionalSpec] = []
    for measure in NPORT_FLOW_MEASURES:
        signal_fn = (
            signal_flow_induced_trading
            if measure == "fit"
            else partial(
                signal_expected_flow_induced_trading,
                expected_fit_frame=measure_frames["expected_fit"],
            )
        )
        prefix = "fit" if measure == "fit" else "efit"
        for holding in NPORT_FLOW_HOLDING_DAYS:
            for suffix, rank_fraction in NPORT_FLOW_RANK_FRACTIONS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=f"{prefix}_ls_h{holding}{suffix}",
                        family=NPORT_FLOW_FAMILY,
                        citation=NPORT_FLOW_CITATION,
                        signal_fn=signal_fn,
                        lookback_days=NPORT_FLOW_SIGNAL_LOOKBACK_ROWS,
                        holding_days=holding,
                        portfolio="long_short",
                        rank_fraction=rank_fraction,
                        requires_fundamental_signal=True,
                    )
                )
    assert len(specs) == NPORT_FLOW_N_TRIALS == 12, (
        f"nport flow built {len(specs)} definitions; the declared grid implies "
        f"{NPORT_FLOW_N_TRIALS} and the pre-registration declared exactly 12. All three must "
        "agree — a drift silently changes this family's DSR denominator."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.leg_weighting == "magnitude" for s in specs)
    assert all(s.requires_fundamental_signal for s in specs)
    assert 21 not in NPORT_FLOW_HOLDING_DAYS, (
        "monthly holds are excluded up front: N-PORT holdings refresh QUARTERLY and are "
        "published 60 days late, so a 21-day hold re-pays turnover on an unchanged ranking."
    )
    return specs


def default_nport_flow_config() -> CrossSectionalConfig:
    """A fresh config per call — the harness writes formation_start onto
    whatever it is given, so a shared singleton would leak between runs.

    cost_model="edge_spread" against the CALIBRATED half-spread frame, and a
    non-zero borrow charge. See module docstring section 6 for both, and for
    why this family does not inherit the 0.0 financing every other single-stock
    equity family here carries."""
    return CrossSectionalConfig(
        cost_model="edge_spread",
        financing_bps_per_year=NPORT_FLOW_FINANCING_BPS_PER_YEAR,
    )


# --- the panel builder --------------------------------------------------------


@dataclass
class FlowPanels:
    """The point-in-time measure panels plus everything measured while building
    them. A panel read without these numbers is not interpretable.

    `fit` and `expected_fit` are keyed by PSF NAME, because the pre-declared
    PSF-source sensitivity arm (module docstring section 4(c)) needs the same
    measure under more than one partial scaling factor. Building them together
    in ONE pass is not merely an optimisation: the expensive part of
    build_flow_panels — resolving each fund's point-in-time filing pair and
    restating every share count onto a common split basis — is entirely
    PSF-independent, so computing the arms separately would repeat it and give
    three chances for the arms to drift apart."""

    fit: dict[str, pd.DataFrame]
    expected_fit: dict[str, pd.DataFrame]
    diagnostics: FlowPanelDiagnostics
    snapshot_dates: list[pd.Timestamp]
    headline_psf: str = ""
    # Per-snapshot expected-flow first-stage fits (Lou Eq.(4), univariate).
    expected_flow_fits: list[dict[str, float]] = field(default_factory=list)
    # Realized value ranges — the cheapest sanity check a reader has.
    fit_min: float = float("nan")
    fit_max: float = float("nan")
    expected_fit_min: float = float("nan")
    expected_fit_max: float = float("nan")
    tickers_never_ranked: list[str] = field(default_factory=list)


def month_end_snapshots(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """The last trading row of each calendar month in the price index.

    Monthly, not quarterly, because funds' FISCAL quarters are staggered: a new
    tranche of filings becomes public every month, and a quarterly snapshot
    grid would let a filing sit unused for up to two months after it was
    already public. Monthly is also the finest grid that is not simply
    re-reading the same filings — Item B.6 flow is monthly but HOLDINGS, which
    Eq.(3) weights by, are quarterly (see module docstring section 2)."""
    if len(index) == 0:
        return []
    frame = pd.Series(index, index=index)
    return list(frame.groupby([index.year, index.month]).last())


def build_flow_panels(
    close: pd.DataFrame,
    filings: Sequence[FundQuarterFiling],
    holdings_by_accession: Mapping[str, dict[str, float]],
    cusip_to_ticker: Mapping[str, str],
    returns_by_accession: Mapping[str, list[tuple[float, float, float]]],
    factors: pd.DataFrame,
    split_adjustments: Mapping[str, pd.Series],
    *,
    psfs: Mapping[str, PartialScalingFactor] | None = None,
    headline_psf: str = "lou_published",
    formation_start: date | None = None,
) -> FlowPanels:
    """Build the FIT and E[FIT] point-in-time step panels aligned to `close`.

    `holdings_by_accession` maps an accession to {cusip: split-UNadjusted
    shares}; this function does the split restatement itself so the adjustment
    is applied once, at the one place that knows both the ticker and the
    observation date (module docstring section 3).

    THE POINT-IN-TIME CONTRACT, restated because it is the whole basis of the
    result: the value written at snapshot row D is computed ONLY from filings
    with FILING_DATE <= D, and rows between snapshots carry the previous
    snapshot's value forward. The frame is a STEP series, never interpolated —
    a measure of quarterly holdings published 60 days late does not vary
    smoothly and pretending it does would manufacture values nobody could have
    known."""
    psfs = dict(psfs) if psfs else {headline_psf: LOU_PUBLISHED_PSF}
    if headline_psf not in psfs:
        raise ValueError(f"headline_psf {headline_psf!r} is not among the supplied PSFs {list(psfs)}")
    diagnostics = FlowPanelDiagnostics()
    by_series = _series_index(filings)
    diagnostics.n_series_seen = len(by_series)
    monthly_returns = fund_monthly_returns(filings, returns_by_accession)

    snapshots = month_end_snapshots(close.index)
    if formation_start is not None:
        # Warmup rows exist only to fill the spread window; no measure is
        # needed there and computing one would just burn time.
        snapshots = [s for s in snapshots if s.date() >= formation_start - timedelta(days=45)]
    diagnostics.n_snapshot_dates = len(snapshots)

    tickers = list(close.columns)
    ticker_position = {t: i for i, t in enumerate(tickers)}
    fit_values = {
        name: np.full((len(snapshots), len(tickers)), np.nan) for name in psfs
    }
    efit_values = {
        name: np.full((len(snapshots), len(tickers)), np.nan) for name in psfs
    }

    # (alpha, realized next-quarter flow) training pairs for Lou Eq.(4), keyed
    # by the fund and the FILING that revealed the outcome and stamped with
    # that filing's own FILING_DATE, so a snapshot can take only the pairs that
    # were public at it.
    #
    # A DICT, NOT A LIST, AND THAT IS LOAD-BEARING. The same fund-quarter stays
    # the fund's latest public filing for one to three monthly snapshots, so
    # appending once per snapshot would enter it two or three times — and NOT
    # uniformly, since a fund with a longer publication gap would be entered
    # more often. That is a weighting of the first-stage regression by
    # publication cadence, which is not a thing anyone chose.
    training: dict[tuple[str, str], tuple[date, float, float]] = {}
    alpha_cache: dict[tuple[str, date], float | None] = {}

    def _alpha(series: str, report_date: date) -> float | None:
        key = (series, report_date)
        if key not in alpha_cache:
            alpha_cache[key] = four_factor_alpha(
                monthly_returns.get(series, {}),
                factors,
                pd.Timestamp(report_date) + pd.offsets.MonthEnd(0),
            )
        return alpha_cache[key]

    factor_names = list(psfs)
    split_cache: dict[tuple[str, date], float] = {}

    def _factor(ticker: str, observed_on: date) -> float:
        key = (ticker, observed_on)
        cached = split_cache.get(key)
        if cached is None:
            cached = split_factor_on(split_adjustments, ticker, observed_on)
            split_cache[key] = cached
        return cached

    for row_position, snapshot in enumerate(snapshots):
        as_of = snapshot.date()
        fund_state = fund_snapshots_as_of(by_series, as_of, diagnostics)
        if not fund_state:
            continue

        flow_by_fund = {series: state.flow for series, state in fund_state.items()}

        # --- Eq.(3): weights are the PREVIOUS filing's share counts ---------
        lagged_shares: dict[str, dict[str, float]] = defaultdict(dict)
        current_shares: dict[str, dict[str, float]] = defaultdict(dict)
        for series, state in fund_state.items():
            for accession, target, observed_on in (
                (state.previous_accession, lagged_shares, state.previous_report_date),
                (state.current_accession, current_shares, state.report_date),
            ):
                book = holdings_by_accession.get(accession)
                if not book:
                    continue
                for cusip, shares in book.items():
                    ticker = cusip_to_ticker.get(cusip)
                    if ticker is None or ticker not in ticker_position:
                        continue
                    target[ticker][series] = (
                        target[ticker].get(series, 0.0) + shares * _factor(ticker, observed_on)
                    )

        realized_contribution = {
            series: [flow * psfs[name].for_flow(flow) for name in factor_names]
            for series, flow in flow_by_fund.items()
        }
        for ticker, shares_by_fund in lagged_shares.items():
            if len(shares_by_fund) < MIN_FUNDS_PER_STOCK:
                diagnostics.refuse("fit_too_few_funds")
                continue
            values = flow_induced_trading_multi(
                shares_by_fund, realized_contribution, len(factor_names)
            )
            if values is None:
                diagnostics.refuse("fit_not_computable")
                continue
            for position, name in enumerate(factor_names):
                if not np.isfinite(values[position]):
                    diagnostics.refuse("fit_not_computable")
                    continue
                fit_values[name][row_position, ticker_position[ticker]] = values[position]
                if name == headline_psf:
                    diagnostics.n_fit_cells += 1

        # --- Eq.(5): expected flow from the lagged four-factor alpha --------
        alphas: dict[str, float] = {}
        for series, state in fund_state.items():
            alpha = _alpha(series, state.report_date)
            if alpha is None:
                diagnostics.refuse("no_four_factor_alpha")
                continue
            alphas[series] = alpha
        diagnostics.n_alpha_estimates += len(alphas)

        usable_pairs = [(a, f) for filed, a, f in training.values() if filed <= as_of]
        model = fit_expected_flow_model(usable_pairs)
        if model is None:
            diagnostics.refuse("expected_flow_model_unfitted")
        else:
            intercept, slope, stats = model
            stats["snapshot"] = float(pd.Timestamp(snapshot).value)
            diagnostics.expected_flow_fits.append(stats)
            expected_contribution = {}
            for series, alpha in alphas.items():
                expected = intercept + slope * alpha
                expected_contribution[series] = [
                    expected * psfs[name].for_flow(expected) for name in factor_names
                ]
            for ticker, shares_by_fund in current_shares.items():
                usable = {s: v for s, v in shares_by_fund.items() if s in expected_contribution}
                if len(usable) < MIN_FUNDS_PER_STOCK:
                    diagnostics.refuse("efit_too_few_funds")
                    continue
                values = flow_induced_trading_multi(
                    usable, expected_contribution, len(factor_names)
                )
                if values is None:
                    diagnostics.refuse("efit_not_computable")
                    continue
                for position, name in enumerate(factor_names):
                    if not np.isfinite(values[position]):
                        diagnostics.refuse("efit_not_computable")
                        continue
                    efit_values[name][row_position, ticker_position[ticker]] = values[position]
                    if name == headline_psf:
                        diagnostics.n_expected_fit_cells += 1

        # --- grow the training set with THIS snapshot's realized outcomes ---
        # Lou Eq.(4) regresses flow_{i,t+1} on alpha_{i,t}, so the pair is the
        # PREVIOUS report's alpha against the CURRENT report's realized flow.
        for series, state in fund_state.items():
            key = (series, state.current_accession)
            if key in training:
                continue
            previous_alpha = _alpha(series, state.previous_report_date)
            if previous_alpha is None:
                continue
            # The outcome (this quarter's realized flow) became public on the
            # current filing's own filing date; find it rather than assume it.
            current = next(
                (f for f in by_series[series] if f.accession == state.current_accession), None
            )
            if current is None:
                continue
            training[key] = (current.filing_date, previous_alpha, state.flow)

    def _to_step_frame(values: np.ndarray) -> pd.DataFrame:
        sparse = pd.DataFrame(values, index=pd.DatetimeIndex(snapshots), columns=tickers)
        return sparse.reindex(close.index).ffill()

    fit_frames = {name: _to_step_frame(values) for name, values in fit_values.items()}
    efit_frames = {name: _to_step_frame(values) for name, values in efit_values.items()}

    def _range(frame: pd.DataFrame) -> tuple[float, float]:
        flat = frame.to_numpy(dtype=float)
        flat = flat[np.isfinite(flat)]
        if flat.size == 0:
            return float("nan"), float("nan")
        return float(flat.min()), float(flat.max())

    headline_fit = fit_frames[headline_psf]
    fit_lo, fit_hi = _range(headline_fit)
    efit_lo, efit_hi = _range(efit_frames[headline_psf])
    never_ranked = sorted(
        t for t in tickers if not np.isfinite(headline_fit[t].to_numpy(dtype=float)).any()
    )

    # The Lou Eq.(2) re-estimation sample is DELIBERATELY NOT collected here.
    # The caller needs it BEFORE this function runs (a re-estimated PSF is one
    # of the variants this pass builds), and collecting it here as well walked
    # all 8.78 million fund-stock-quarter pairs a second time for a result
    # nothing read — measured on the real panel, where it was the slowest thing
    # in the run. _collect_psf_observations is called once, by the caller.
    return FlowPanels(
        fit=fit_frames,
        expected_fit=efit_frames,
        diagnostics=diagnostics,
        snapshot_dates=snapshots,
        headline_psf=headline_psf,
        expected_flow_fits=diagnostics.expected_flow_fits,
        fit_min=fit_lo,
        fit_max=fit_hi,
        expected_fit_min=efit_lo,
        expected_fit_max=efit_hi,
        tickers_never_ranked=never_ranked,
    )


def _collect_psf_observations(
    by_series: Mapping[str, list[FundQuarterFiling]],
    holdings_by_accession: Mapping[str, dict[str, float]],
    cusip_to_ticker: Mapping[str, str],
    split_adjustments: Mapping[str, pd.Series],
    ticker_position: Mapping[str, int],
) -> list[tuple[float, float]]:
    """(trade, flow) pairs for the Lou Eq.(2) re-estimation, one per
    fund-stock-quarter.

    Uses each series' own consecutive REPORT dates directly rather than the
    snapshot loop's as-of view, so a fund-stock-quarter appears exactly once no
    matter how many months its filing happened to be the latest public one.
    This sample is a DISCLOSURE and a sensitivity input only — it is never used
    to build the headline panels (module docstring section 4(b)) — so it is
    deliberately NOT gated on a formation date."""
    out: list[tuple[float, float]] = []
    for rows in by_series.values():
        # One filing per report date: the latest-filed (an amendment wins).
        latest: dict[date, FundQuarterFiling] = {}
        for filing in rows:
            existing = latest.get(filing.report_date)
            if existing is None or filing.filing_date > existing.filing_date:
                latest[filing.report_date] = filing
        ordered = [latest[d] for d in sorted(latest)]
        for previous, current in pairwise(ordered):
            gap = (current.report_date - previous.report_date).days
            if not MIN_QUARTER_GAP_DAYS <= gap <= MAX_QUARTER_GAP_DAYS:
                continue
            if previous.net_assets < MIN_FUND_NET_ASSETS:
                continue
            flow = current.external_flow_dollars / previous.net_assets
            if not np.isfinite(flow) or abs(flow) > MAX_ABSOLUTE_FLOW:
                continue
            before = holdings_by_accession.get(previous.accession)
            after = holdings_by_accession.get(current.accession)
            if not before or not after:
                continue
            for cusip, shares_before in before.items():
                ticker = cusip_to_ticker.get(cusip)
                if ticker is None or ticker not in ticker_position or shares_before <= 0.0:
                    continue
                shares_after = after.get(cusip)
                if shares_after is None:
                    continue
                adjusted_before = shares_before * split_factor_on(
                    split_adjustments, ticker, previous.report_date
                )
                adjusted_after = shares_after * split_factor_on(
                    split_adjustments, ticker, current.report_date
                )
                if adjusted_before <= 0.0:
                    continue
                trade = adjusted_after / adjusted_before - 1.0
                if np.isfinite(trade):
                    out.append((trade, flow))
    return out


# --- production entry point ---------------------------------------------------

# The earliest formation. N-PORT's first public quarter is the one ending
# 2019-09-30 (filed from ~2019-11-18), and Eq.(3) needs a fund's PREVIOUS
# quarter too, so the first snapshot at which a meaningful number of funds have
# two consecutive PUBLIC filings is around 2020-03. 2020-04-01 is the first
# formation date this family allows, declared here rather than discovered.
NPORT_FLOW_FORMATION_START = date(2020, 4, 1)


# Policy D's denominators, read from the committed artifact rather than
# retyped so they cannot drift from the run that measured them:
#   n_local  = 12, this family's own pre-declared grid
#   481      = n_specs_clustered, the pooled population carrying realized returns
#   857      = raw_pooled_distinct_trials, every trial this project has persisted
def policy_d_denominators(n_local: int = NPORT_FLOW_N_TRIALS) -> list[int]:
    """The N values a Policy D report must cover, ascending and deduplicated.

    THE LOWEST TIER IS dsr_n_trials(n_local), NOT n_local ITSELF, and that
    distinction is load-bearing rather than pedantic. dsr_n_trials returns
    max(family grid size, pooled effective N), which is the denominator
    screen_cross_sectional_universe actually deflates this family at; reporting
    the raw grid size beside it would show a DSR the run never computed. The two
    coincide today only because the pooled ONC estimate sits at its own
    structural floor of 2 (see global_effective_n.json), and they would silently
    diverge the moment that estimate exceeds a family's grid size — which is
    exactly the drift this project wired dsr_n_trials to prevent.

    DSR is strictly decreasing in N (SR0 is strictly increasing in N and PSR is
    strictly decreasing in its benchmark), so these three points BRACKET every N
    between them — which is what makes a three-point report sufficient rather
    than a sample of a curve."""
    # Imported locally, NOT at module level, purely so the module-level import
    # of dsr_n_trials above stays on the single line the governance scan in
    # tests/test_global_effective_n.py matches on; isort wraps a combined import
    # of both names and the scan then stops seeing it.
    from app.services.research_lab.global_effective_n import load_global_effective_n

    artifact = load_global_effective_n()
    return sorted(
        {
            dsr_n_trials(int(n_local)),
            artifact.n_specs_clustered,
            artifact.raw_pooled_distinct_trials,
        }
    )


def dsr_across_denominators(
    sharpe_annualized: float,
    returns: pd.Series,
    sigma_sr_annualized: float | None,
    denominators: Sequence[int],
    *,
    periods_per_year: float,
) -> dict[int, float | None]:
    """DSR at each N. A None means the machinery could not produce one there
    (below deflated_sharpe.MIN_TRIALS_FOR_DSR, or a degenerate return series) —
    treated downstream as NOT clearing the bar, because an unmeasurable
    deflation is not a passing one."""
    from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe

    out: dict[int, float | None] = {}
    for n in denominators:
        result = compute_deflated_sharpe(
            sharpe_annualized,
            returns,
            int(n),
            sigma_sr_annualized,
            periods_per_year=periods_per_year,
        )
        out[int(n)] = result.dsr
    return out


@dataclass
class SpecEvaluation:
    """One spec's full Policy D record: DSR at every denominator, the
    preservation score, and the realized return series they were computed from.

    preservation_score is here rather than in a separate optional pass on
    purpose. It was shipped 2026-09-03 and then SKIPPED for the next two real
    registration decisions until someone asked whether it had been run; a metric
    applied when someone remembers is a decoration, not a check."""

    pattern_id: str
    sharpe_annualized: float
    dsr_by_n: dict[int, float | None]
    preservation: dict[str, float | int | bool | None]
    n_trading_days: int
    total_cost_drag: float
    total_financing_drag: float
    total_turnover: float
    edge_flat_fallback_notional: float
    avg_names_per_leg: float
    n_formations: int


@dataclass
class SensitivityArm:
    """One pre-declared sensitivity arm: the whole grid re-scored under one
    changed assumption. NOT new trials — the DSR denominator is unchanged, only
    the returns the DSR is computed on."""

    key: str
    description: str
    sharpe_by_pattern: dict[str, float]
    dsr_by_pattern: dict[str, dict[int, float | None]]


@dataclass
class NportFlowScreeningSummary:
    """run_nport_flow_screening's full result: the screening output plus every
    measured coverage number a reader needs to interpret it. Typed fields, not
    docstring paragraphs — the discipline the sibling family summaries state."""

    results: list[CrossSectionalScreeningResult]
    n_trials: int
    universe_size: int
    cusips_resolved: int
    tickers_without_cusip: list[str]
    missing_price_data: list[str]
    tickers_never_ranked: list[str]
    quarters_loaded: list[str]
    n_filings: int
    n_holding_rows: int
    panel_start: date | None
    panel_end: date | None
    formation_start: date
    psf: PartialScalingFactor
    psf_reestimated: PartialScalingFactor | None = None
    psf_reestimation_stats: dict[str, float] = field(default_factory=dict)
    expected_flow_fits: list[dict[str, float]] = field(default_factory=list)
    panel_diagnostics: FlowPanelDiagnostics = field(default_factory=FlowPanelDiagnostics)
    fit_min: float = float("nan")
    fit_max: float = float("nan")
    expected_fit_min: float = float("nan")
    expected_fit_max: float = float("nan")
    n_fit_cells: int = 0
    n_expected_fit_cells: int = 0
    half_spread_calibration: str = ""
    cost_model: str = ""
    cost_bps: float = float("nan")
    financing_bps_per_year: float = float("nan")
    ff3_vintage: str = ""
    momentum_vintage: str = ""
    # The built panels themselves, so a runner can persist the DERIVED measure
    # alongside its report and a reviewer can re-derive every number offline
    # without the ~7GB N-PORT bulk cache.
    panels: FlowPanels | None = None
    denominators: list[int] = field(default_factory=list)
    evaluations: list[SpecEvaluation] = field(default_factory=list)
    borrow_arms: list[SensitivityArm] = field(default_factory=list)
    psf_arms: list[SensitivityArm] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def verdict(self, threshold: float = 0.95) -> tuple[str, str]:
        """(verdict, best pattern_id) under Policy D's two-tier rule, computed
        by registration_scorecard.policy_d_verdict rather than reimplemented
        here so the run report and the scorecard cannot disagree."""
        from app.services.research_lab.registration_scorecard import policy_d_verdict

        if not self.evaluations:
            return ("definite_negative", "")
        best = max(
            self.evaluations,
            key=lambda e: (
                e.dsr_by_n.get(self.n_trials) if e.dsr_by_n.get(self.n_trials) is not None else -1.0
            ),
        )
        return (
            policy_d_verdict(
                dsr_by_n=best.dsr_by_n, threshold=threshold, n_local=self.n_trials
            ),
            best.pattern_id,
        )


def load_cusip_ticker_map(universe: Sequence[str], form13f: Form13FProvider | None = None):
    """CUSIP -> ticker for `universe`, from SEC's own fails-to-deliver files.

    Reuses form13f_provider's dated map wholesale rather than building a second
    one: it is already the mapping cross_sectional_best_ideas.py uses, already
    tested, and already resolves the FTD dot/dash share-class convention. The
    map is DATED (nearest published observation in time), so a CUSIP whose
    symbol was reassigned does not silently apply today's symbol to a 2020
    holding."""
    provider = form13f or Form13FProvider()
    stamps = provider.available_ftd_stamps()
    if not stamps:
        # LOUD, not empty. An empty map silently makes every N-PORT holding
        # unresolvable, which downstream looks exactly like "no mutual fund
        # holds any of these stocks" — a plausible-looking all-NaN panel rather
        # than an error. Observed on the first real run of this family, whose
        # worktree had no fails-to-deliver cache.
        raise RuntimeError(
            f"no SEC fails-to-deliver archives are cached in {provider.cache_dir}. Without them "
            "no CUSIP resolves to a ticker and every N-PORT holding is silently dropped. Fetch "
            "them first (Form13FProvider.get_ftd_archive) rather than screening an empty panel."
        )
    triples: list[tuple[date, str, str]] = []
    empty_archives: list[str] = []
    for stamp in stamps:
        parsed = parse_ftd_archive(provider.get_ftd_archive(stamp))
        if not parsed:
            empty_archives.append(stamp)
        triples.extend(parsed)
    return build_cusip_ticker_map(triples, restrict_to=set(universe)), empty_archives


def load_nport_quarters(
    provider: NportProvider,
    quarters: Sequence[str],
    cusips: set[str],
):
    """(filings, holdings_by_accession, monthly returns by accession, diagnostics)
    across `quarters`.

    Holdings are collapsed to {accession: {cusip: shares}} here rather than
    kept as rows because Eq.(3) needs exactly one share count per fund per
    stock; a fund reporting the same issuer's common stock on two lines (two
    lots, two custodians) is summed, which is what "the number of shares held
    by mutual fund i" means."""
    diagnostics = NportLoadDiagnostics()
    filings = []
    holdings_by_accession: dict[str, dict[str, float]] = defaultdict(dict)
    returns_by_accession: dict[str, list[tuple[float, float, float]]] = defaultdict(list)

    for quarter in quarters:
        quarter_filings, diagnostics = build_fund_quarter_filings(
            provider.submissions(quarter), provider.fund_reported_info(quarter), diagnostics
        )
        filings.extend(quarter_filings)
        rows, diagnostics = build_holding_rows(provider.holdings(quarter, cusips), diagnostics)
        for row in rows:
            book = holdings_by_accession[row.accession]
            book[row.cusip] = book.get(row.cusip, 0.0) + row.shares
        for record in provider.monthly_total_returns(quarter):
            values = tuple(
                parse_float(record.get(f"MONTHLY_TOTAL_RETURN{n}", "")) for n in (1, 2, 3)
            )
            if any(v is None for v in values):
                continue
            returns_by_accession[record["ACCESSION_NUMBER"]].append(values)  # type: ignore[arg-type]

    # One filing per accession: the same accession appears in exactly one
    # quarterly ZIP, but a defensive dedup costs nothing and a duplicated
    # filing would double-count that fund's weight in every stock it holds.
    seen: set[str] = set()
    unique = []
    for filing in filings:
        if filing.accession in seen:
            continue
        seen.add(filing.accession)
        unique.append(filing)
    return unique, dict(holdings_by_accession), dict(returns_by_accession), diagnostics


def run_nport_flow_screening(
    start: date = NPORT_FLOW_FORMATION_START,
    end: date | None = None,
    *,
    provider: YFinanceProvider | None = None,
    nport: NportProvider | None = None,
    form13f: Form13FProvider | None = None,
    config: CrossSectionalConfig | None = None,
    quarters: Sequence[str] | None = None,
) -> NportFlowScreeningSummary:
    """THE production entry point: one N-PORT load, one price fetch, one
    12-spec pre-declared family screened under one DSR denominator.

    Deliberately the sibling equity families' pipeline (point-in-time universe,
    point-in-time step panel, price panel, membership gate, calibrated
    edge_spread cost) with one factor swapped in, so any difference in result
    is a difference in the MEASURE, not in the machinery around it."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"formation start {start.isoformat()} predates point-in-time membership coverage "
            f"({MEMBERSHIP_DATA_START.isoformat()})."
        )
    end = end if end is not None else date.today()  # noqa: DTZ011 — price-fetch end bound only
    provider = provider if provider is not None else YFinanceProvider()
    nport = nport if nport is not None else NportProvider()
    config = config if config is not None else default_nport_flow_config()
    config.formation_start = start

    warnings: list[str] = []
    universe = get_universe_over(MEMBERSHIP_DATA_START, end)
    # Restrict to names that were members at some point during the N-PORT era;
    # a company that left the index in 2016 can never be ranked here and would
    # only inflate the "never ranked" count.
    universe = get_universe_over(max(MEMBERSHIP_DATA_START, start - timedelta(days=400)), end)

    cusip_map, empty_archives = load_cusip_ticker_map(universe, form13f)
    if empty_archives:
        warnings.append(
            f"{len(empty_archives)} cached fails-to-deliver archives contributed ZERO rows to the "
            f"CUSIP map ({empty_archives[:5]}) — the dated map is thinner than its file count."
        )
    resolved_tickers = cusip_map.tickers()
    without_cusip = sorted(set(universe) - resolved_tickers)
    if without_cusip:
        warnings.append(
            f"{len(without_cusip)} of {len(universe)} universe tickers resolve NO CUSIP in SEC's "
            f"fails-to-deliver files ({without_cusip}) and can never be ranked."
        )

    # A DATED map resolved at a single date would be wrong for a reassigned
    # symbol; resolving at each holding's own report date is not possible here
    # because the map is keyed by CUSIP and the holdings are loaded in bulk, so
    # each CUSIP is resolved at the MIDPOINT of the sample and the count of
    # CUSIPs whose answer would differ at the two ends is reported.
    midpoint = start + (end - start) / 2
    cusip_to_ticker: dict[str, str] = {}
    ambiguous = 0
    for cusip in cusip_map.observations:
        at_mid = cusip_map.resolve(cusip, midpoint)
        if at_mid is None:
            continue
        cusip_to_ticker[cusip] = at_mid
        if cusip_map.resolve(cusip, start) != at_mid or cusip_map.resolve(cusip, end) != at_mid:
            ambiguous += 1
    if ambiguous:
        warnings.append(
            f"{ambiguous} of {len(cusip_to_ticker)} CUSIPs resolve to a DIFFERENT ticker at the "
            "start or end of the sample than at its midpoint (symbol reassignment); the midpoint "
            "answer is used for all of them."
        )

    quarters = list(quarters) if quarters is not None else nport.cached_quarters()
    if not quarters:
        raise RuntimeError(
            "no N-PORT bulk quarters are cached. Run data/research_runs/"
            "fetch_nport_bulk.py first — this entry point deliberately does not download "
            "~7GB of SEC bulk data as a side effect of being called."
        )
    filings, holdings_by_accession, returns_by_accession, load_diagnostics = load_nport_quarters(
        nport, quarters, set(cusip_to_ticker)
    )

    padded_start = start - timedelta(days=NPORT_FLOW_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    frames, missing_price = provider.get_daily_ohlcv(universe, padded_start, end)
    close = frames["close"]
    if close.empty:
        raise RuntimeError("no price data resolved for any universe ticker")
    if missing_price:
        warnings.append(
            f"{len(missing_price)} of {len(universe)} universe tickers resolved no price data "
            "(the standing departed-member yfinance gap — see cross_sectional.py)."
        )

    _cap_close, splits_by_ticker, _cap_missing = provider.get_market_cap_basis(
        list(close.columns), padded_start, end
    )
    split_adjustments = build_split_adjustment(splits_by_ticker, close.index)

    factors, ff3_vintage, momentum_vintage = load_carhart_four_factors()
    logger.info(
        "loaded %d filings, %d accessions with holdings, %d CUSIPs, %d price columns",
        len(filings), len(holdings_by_accession), len(cusip_to_ticker), len(close.columns),
    )

    # PSF pass 1: the Eq.(2) re-estimation sample, needed BEFORE the panels are
    # built so the re-estimated PSF can be one of the arms computed in the same
    # (expensive) snapshot pass. It reads only holdings and flows, never prices
    # or returns, so it cannot leak a return into the headline panel.
    psf_pairs = _collect_psf_observations(
        _series_index(filings),
        holdings_by_accession,
        cusip_to_ticker,
        split_adjustments,
        {t: i for i, t in enumerate(close.columns)},
    )
    reestimated, reestimation_stats = (
        estimate_partial_scaling_factor(psf_pairs) if psf_pairs else (None, {})
    )
    logger.info(
        "Lou Eq.(2) re-estimation sample: %d (trade, flow) pairs; bounded estimate %s",
        len(psf_pairs),
        f"outflow {reestimated.outflow:.4f} / inflow {reestimated.inflow:.4f}"
        if reestimated
        else "not estimable",
    )

    psfs: dict[str, PartialScalingFactor] = {
        "lou_published": LOU_PUBLISHED_PSF,
        "perfect_scaling": PERFECT_SCALING_PSF,
    }
    if reestimated is not None:
        psfs["reestimated"] = reestimated

    logger.info("building point-in-time measure panels for %d PSF variant(s)", len(psfs))
    panels = build_flow_panels(
        close,
        filings,
        holdings_by_accession,
        cusip_to_ticker,
        returns_by_accession,
        factors,
        split_adjustments,
        psfs=psfs,
        headline_psf="lou_published",
        formation_start=start,
    )

    half_spread = None
    calibration_summary = ""
    if config.cost_model == "edge_spread":
        half_spread, report = build_calibrated_half_spread_frame(
            frames["open"],
            frames["high"],
            frames["low"],
            close,
            calibration_start=pd.Timestamp(start),
        )
        calibration_summary = report.summary()
        logger.info("nport_flow half-spread basis: %s", calibration_summary)

    def _screen(psf_name: str, screening_config: CrossSectionalConfig):
        data = CrossSectionalData(
            close=close,
            open=frames["open"],
            volume=frames["volume"],
            fundamental_signal=panels.fit[psf_name],
            half_spread=half_spread,
        )
        specs = build_nport_flow_family(
            {"fit": panels.fit[psf_name], "expected_fit": panels.expected_fit[psf_name]}
        )
        return data, specs, screen_cross_sectional_universe(data, specs, screening_config)

    logger.info(
        "panels built: %d FIT cells, %d E[FIT] cells over %d snapshots; screening %d specs",
        panels.diagnostics.n_fit_cells,
        panels.diagnostics.n_expected_fit_cells,
        panels.diagnostics.n_snapshot_dates,
        NPORT_FLOW_N_TRIALS,
    )
    data, specs, results = _screen("lou_published", config)

    # --- Policy D evaluation: DSR at every N, preservation for every spec ----
    denominators = policy_d_denominators(NPORT_FLOW_N_TRIALS)
    sigma_sr = (
        float(np.std([r.sharpe_annualized for r in results], ddof=1)) if len(results) >= 2 else None
    )
    evaluations: list[SpecEvaluation] = []
    replays = _replay_all(data, specs, config)
    for result in results:
        replay = replays.get(result.pattern_id)
        if replay is None:
            continue
        evaluations.append(
            SpecEvaluation(
                pattern_id=result.pattern_id,
                sharpe_annualized=result.sharpe_annualized,
                dsr_by_n=dsr_across_denominators(
                    result.sharpe_annualized,
                    replay.daily_returns,
                    sigma_sr,
                    denominators,
                    periods_per_year=config.periods_per_year,
                ),
                preservation=compute_preservation_metrics(
                    replay.daily_returns,
                    dsr=result.deflated_sharpe.dsr,
                    periods_per_year=config.periods_per_year,
                ).as_dict(),
                n_trading_days=result.n_trading_days,
                total_cost_drag=result.total_cost_drag,
                total_financing_drag=result.total_financing_drag,
                total_turnover=result.total_turnover,
                edge_flat_fallback_notional=result.edge_flat_fallback_notional,
                avg_names_per_leg=result.avg_names_per_leg,
                n_formations=result.n_formations,
            )
        )

    # --- pre-declared sensitivity arms: no new trials, only new returns -----
    logger.info("headline screen done; running %d borrow arms", len(NPORT_FLOW_BORROW_LADDER_BPS))
    borrow_arms = [
        _sensitivity_arm(
            key=f"borrow_{int(short_leg_bps)}bp",
            description=(
                f"short-leg borrow {short_leg_bps:.0f} bps/yr "
                f"(config financing_bps_per_year={short_leg_bps / 2.0:.1f})"
            ),
            data=data,
            specs=specs,
            config=_config_with(config, financing_bps_per_year=short_leg_bps / 2.0),
            denominators=denominators,
        )
        for short_leg_bps in NPORT_FLOW_BORROW_LADDER_BPS
    ]
    psf_arms = []
    for psf_name, factor in psfs.items():
        if psf_name == "lou_published":
            continue
        arm_data = CrossSectionalData(
            close=close,
            open=frames["open"],
            volume=frames["volume"],
            fundamental_signal=panels.fit[psf_name],
            half_spread=half_spread,
        )
        arm_specs = build_nport_flow_family(
            {"fit": panels.fit[psf_name], "expected_fit": panels.expected_fit[psf_name]}
        )
        logger.info("psf arm %s: replaying %d specs", psf_name, len(arm_specs))
        psf_arms.append(
            _sensitivity_arm(
                key=f"psf_{psf_name}",
                description=(
                    f"PSF {psf_name}: outflow {factor.outflow:.3f}, inflow {factor.inflow:.3f} "
                    f"({factor.source})"
                ),
                data=arm_data,
                specs=arm_specs,
                config=config,
                denominators=denominators,
            )
        )

    return NportFlowScreeningSummary(
        results=results,
        n_trials=NPORT_FLOW_N_TRIALS,
        universe_size=len(universe),
        cusips_resolved=len(cusip_to_ticker),
        tickers_without_cusip=without_cusip,
        missing_price_data=missing_price,
        tickers_never_ranked=panels.tickers_never_ranked,
        quarters_loaded=list(quarters),
        n_filings=len(filings),
        n_holding_rows=sum(len(book) for book in holdings_by_accession.values()),
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        formation_start=start,
        psf=LOU_PUBLISHED_PSF,
        psf_reestimated=reestimated,
        psf_reestimation_stats=reestimation_stats,
        expected_flow_fits=panels.expected_flow_fits,
        panel_diagnostics=panels.diagnostics,
        fit_min=panels.fit_min,
        fit_max=panels.fit_max,
        expected_fit_min=panels.expected_fit_min,
        expected_fit_max=panels.expected_fit_max,
        n_fit_cells=panels.diagnostics.n_fit_cells,
        n_expected_fit_cells=panels.diagnostics.n_expected_fit_cells,
        half_spread_calibration=calibration_summary,
        cost_model=config.cost_model,
        cost_bps=config.cost_bps,
        financing_bps_per_year=config.financing_bps_per_year,
        ff3_vintage=ff3_vintage,
        momentum_vintage=momentum_vintage,
        panels=panels,
        denominators=denominators,
        evaluations=evaluations,
        borrow_arms=borrow_arms,
        psf_arms=psf_arms,
        warnings=[*warnings, *(f"nport load: {k}={v}" for k, v in load_diagnostics.n_refused.items())],
    )


def _config_with(base: CrossSectionalConfig, **overrides) -> CrossSectionalConfig:
    """A copy of `base` with fields replaced. A fresh object per arm, never a
    mutation: the harness writes formation_start onto whatever config it is
    given, so reusing one object across arms would silently couple them."""
    from dataclasses import replace

    return replace(base, **overrides)


def _replay_all(data, specs, config):
    """{pattern_id: backtest result} for every spec that produced a usable
    replay.

    Re-runs the harness rather than reusing screen_cross_sectional_universe's
    internals because CrossSectionalScreeningResult deliberately does not carry
    the realized daily return series, and preservation_score and the
    multi-N DSR both need it."""
    from app.services.research_lab.cross_sectional import (
        MIN_REPLAY_TRADING_DAYS,
        run_cross_sectional_backtest,
    )

    out = {}
    for spec in specs:
        replay = run_cross_sectional_backtest(data, spec, config)
        if replay.status != "ok" or len(replay.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            continue
        out[spec.pattern_id] = replay
    return out


def _sensitivity_arm(
    *, key: str, description: str, data, specs, config, denominators: Sequence[int]
) -> SensitivityArm:
    """Re-score the WHOLE grid under one changed cost assumption.

    The DSR denominator is unchanged — a sensitivity arm is not a new search
    dimension, it is the same twelve hypotheses priced differently. sigma_sr is
    recomputed within the arm because it is a property of the arm's own sibling
    Sharpes, exactly as it is for the headline."""
    from app.services.research_lab.metrics import sharpe_ratio

    replays = _replay_all(data, specs, config)
    sharpes = {
        pid: sharpe_ratio(replay.daily_returns, periods_per_year=config.periods_per_year)
        for pid, replay in replays.items()
    }
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None
    return SensitivityArm(
        key=key,
        description=description,
        sharpe_by_pattern=sharpes,
        dsr_by_pattern={
            pid: dsr_across_denominators(
                sharpes[pid],
                replays[pid].daily_returns,
                sigma_sr,
                denominators,
                periods_per_year=config.periods_per_year,
            )
            for pid in sharpes
        },
    )


__all__ = [
    "LOU_PUBLISHED_PSF",
    "MAX_ABSOLUTE_FLOW",
    "MAX_REPORT_STALENESS_DAYS",
    "MIN_FUNDS_PER_STOCK",
    "MIN_FUND_NET_ASSETS",
    "NPORT_FLOW_BORROW_LADDER_BPS",
    "NPORT_FLOW_CITATION",
    "NPORT_FLOW_FAMILY",
    "NPORT_FLOW_FAMILY_KEY",
    "NPORT_FLOW_FORMATION_START",
    "NPORT_FLOW_HOLDING_DAYS",
    "NPORT_FLOW_MEASURES",
    "NPORT_FLOW_N_TRIALS",
    "NPORT_FLOW_RANK_FRACTIONS",
    "PERFECT_SCALING_PSF",
    "FlowPanelDiagnostics",
    "FlowPanels",
    "FundSnapshot",
    "NportFlowScreeningSummary",
    "PartialScalingFactor",
    "SensitivityArm",
    "SpecEvaluation",
    "build_flow_panels",
    "build_nport_flow_family",
    "build_split_adjustment",
    "default_nport_flow_config",
    "dsr_across_denominators",
    "estimate_partial_scaling_factor",
    "fit_expected_flow_model",
    "flow_induced_trading",
    "flow_induced_trading_multi",
    "four_factor_alpha",
    "fund_monthly_returns",
    "fund_snapshots_as_of",
    "load_cusip_ticker_map",
    "load_nport_quarters",
    "month_end_snapshots",
    "policy_d_denominators",
    "run_nport_flow_screening",
    "signal_expected_flow_induced_trading",
    "signal_flow_induced_trading",
    "split_factor_on",
]
