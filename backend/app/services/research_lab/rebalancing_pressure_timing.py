"""The Rebalancing-Pressure family: a two-instrument EQUITY-vs-TREASURY timing
overlay built from Harvey, Mazzoleni & Melone's simulated 60/40 rebalancing
signals, screened as exactly 24 PRE-DECLARED specs with its own n_trials
denominator.

PRE-REGISTRATION: data/research_runs/rebalancing_pressure_PREREGISTRATION.txt,
committed as 3b59dc1 BEFORE this module or any backtest existed. Every
construction constant below is fixed there; this module implements that
document and does not extend it.

============================================================================
THE SOURCE, READ DIRECTLY
============================================================================
[HMM26] Harvey, Campbell R., Mazzoleni, Michele G. & Melone, Alessandro, "The
Unintended Consequences of Rebalancing", NBER Working Paper No. 33554, March
2025, REVISED JANUARY 2026. The PDF was fetched 2026-09-06 from
https://www.nber.org/system/files/working_papers/w33554/w33554.pdf (HTTP 200,
667,944 bytes) and text-extracted with `pdftotext -layout`; every equation
below is transcribed from that text, not from memory and not from a summary.

IT IS A WORKING PAPER, NOT A PEER-REVIEWED ARTICLE, and its own cover page
says so: "NBER working papers are circulated for discussion and comment
purposes. They have not been peer-reviewed..." That status is disclosed
wherever this family's results are, not glossed.

MECHANISM. Large institutions (pensions, sovereign wealth funds, target-date
funds) hold target-weight equity/bond portfolios and trade back toward target
when prices push the actual weight away from it. That produces MARKET-WIDE,
non-informational selling pressure on equities after equities have
outperformed bonds, and buying pressure after they have underperformed.
[HMM26]'s abstract: "When stocks are overweight, funds sell stocks and buy
bonds, leading to a decrease in equity returns of 17 basis points over the
next day."

The economically stated magnitude, from the BODY rather than the abstract
(p.18, verbatim, and this is the number the fidelity checks compare against):
"a one-standard-deviation decrease in the Threshold (Calendar) signal is
associated with an increase in XA returns of about 20 bps (19.2 bps) over the
next trading day, and vice versa."

============================================================================
WHY THIS IS A NEW MODULE AND NOT A cross_sectional.py FAMILY
============================================================================
The same reason vol_regime_timing.py is not one, and this module deliberately
copies that module's shape rather than inventing a third:
cross_sectional.screen_cross_sectional_universe ranks a UNIVERSE of names on a
per-ticker signal. This family has no cross-section to rank. The state
variable is a single scalar per DAY -- a simulated 60/40 portfolio's deviation
from its 60% equity target -- belonging to no ticker at all, and the traded
object is one fixed spread (SPY vs IEF) whose size and sign that scalar sets.
Forcing it into the ranking harness would mean fabricating a two-name
"universe" whose per-ticker signals are +z and -z so the sort trivially
reproduces the spread: numerically fine, and a lie about what the code does.

What IS reused unmodified: metrics.sharpe_ratio, deflated_sharpe.
compute_deflated_sharpe, preservation_score.compute_preservation_metrics,
global_effective_n.dsr_n_trials, registration_scorecard.policy_d_verdict, and
vol_regime_timing's own block_bootstrap_sharpe_pvalue and _ols_beta_alpha --
imported, not re-implemented. The portable conventions (formation at the
close, turnover priced on |position change|, financing accrued on CALENDAR
days, a fixed pre-declared n_trials, sigma_sr as the sibling-Sharpe
dispersion) are copied from vol_regime_timing.py so this family's numbers stay
comparable with the ones screened before it.

============================================================================
THE CONSTRUCTION, EQUATION BY EQUATION
============================================================================
THE WEIGHT RECURSION ([HMM26] p.10, repeated in Appendix B p.52):

    w_{t+1}(w_t; R^SP, R^10Y) =            w_t (1 + R^SP)
                                ----------------------------------------
                                w_t (1 + R^SP) + (1 - w_t)(1 + R^10Y)

implemented as `rebalanced_weight`. VALIDATED AGAINST A KNOWN ANSWER FROM THE
PAPER ITSELF before it is trusted on real data, per CLAUDE.md's rule against
formulas from memory. [HMM26] footnote 8, verbatim: "If the equity market
increases by 10% and the bond market remains unchanged, the portfolio value
becomes 66 + 40 = $106. The equity allocation is now 66/106 = 62.26%." The
unit test pins rebalanced_weight(0.60, 0.10, 0.0) == 66/106 to machine
precision and to the paper's own printed 0.6226.

THE THRESHOLD RULE AND SIGNAL (Appendix B and Eq. B.1):

    w^T_{t+1} = 60%                     if the trigger fired on w^T_t
              = w_{t+1}(w^T_t; ...)     otherwise
    Threshold signal^delta_{t+1} = w_{t+1}(w^T_t; ...) - 60%              (B.1)

NOTE THE STRUCTURE, because it is the easy thing to get wrong: the SIGNAL is
ALWAYS the drifted deviation, computed by applying the transition function to
the previous state, whether or not a rebalance was triggered. Only the STATE
is reset. The trigger is evaluated on the PREVIOUS day's state, so a breach
seen at t produces a reset at t+1 -- one day of implementation lag, which is
also the economically sensible "observe at the close, trade tomorrow".

THE TRIGGER IS TWO-SIDED, AND THE PAPER CONTRADICTS ITSELF ABOUT THIS.
Appendix B's DISPLAYED equation writes it one-sided, "w^T_{t+1} = 60% if
w^T_t - 60% >= delta". Four other places in the same paper say two-sided:
  * p.9  "rebalances ... when the weights DEVIATE BEYOND A SET DISTANCE from
         their targets"
  * p.11 Figure 2 caption: "portfolio rebalancing occurs when THE DISTANCE of
         a portfolio weight from its target exceeds delta"
  * p.12 the non-linearity test uses "days with |Threshold Signal^delta_t| >=
         delta, corresponding to predicted rebalancing days"
  * p.14 "The AVERAGE values of the Threshold and Calendar signals are
         POSITIVE" -- IMPOSSIBLE under a one-sided rule, which resets only on
         positive breaches and lets negative deviations drift without bound.
A structural argument the paper does not make: under the literal one-sided
rule the state never resets on the downside, so the signal depends on the
entire price path since an arbitrary t=0 and the initial condition never
washes out.

RESOLVED IN THE PRE-REGISTRATION (section 3.2), not here and not after seeing
a result: two-sided is PRIMARY, and the literal one-sided form is carried as
an explicitly counted grid arm (`threshold_1sided`) so that resolving the
ambiguity costs trials instead of being free.

THE ADOPTED THRESHOLD SIGNAL ([HMM26] Eq. 2, p.12, verbatim: "the average of
Threshold signals computed using delta values that span the range 0%-2.5%
with increments of 0.1%"):

    Threshold Signal_t = (1/26) * SUM over delta in {0.0%, 0.1%, ..., 2.5%}

The grid is INHERITED from the published paper, not searched here. At
delta = 0 the trigger |w - 60%| >= 0 is always true, so the portfolio resets
every day -- which is exactly what [HMM26] p.11 says it should ("When delta =
0, the 60/40 portfolio rebalances 252 times per year").

THE CALENDAR RULE AND SIGNAL (Appendix B and Eq. B.2): identical, with the
trigger "t is the last business day of the month" in place of the band.

    Calendar signal_{t+1} = w_{t+1}(w^C_t; ...) - 60%                     (B.2)

ONE-DAY AMBIGUITY, DISCLOSED RATHER THAN SILENTLY RESOLVED. The displayed
equation resets the state at t+1 when t is the month-end day, i.e. the reset
lands the day AFTER month end. The economically natural reading is that the
fund trades at the close of the month-end day itself, so the post-trade state
at t is already 60%. The two differ by exactly one day of drift, on exactly
one day per month -- the first trading day of the new month, which the week4
gate excludes anyway and which Section 4 overrides with its own reversal term.
This module implements the paper's LITERAL displayed form and reports the
correlation between it and the alternative as a diagnostic
(`calendar_variant_correlation`), so the immateriality is a measured number
rather than a claim.

THE WEEK4 GATE ([HMM26] Eq. 3 and p.13-14, verbatim): "Calendar predictability
peaks in the last four days of the month... Moreover, Figure 3 suggests that
funds attempt to minimize market impact by avoiding trades on the very last
day while spreading trades over several days. Therefore, our focus for the
rest of the paper is the interaction between the Calendar signal and the last
week of the month, labeled as week4_t, which corresponds to Dummy^{5 Days}_t."

THE PAPER'S OWN TRADEABLE STRATEGY ([HMM26] Section 4, p.37, verbatim):

    R^Strategy_{t+1} = (R^SP500_{t+1} - R^10y_{t+1}) * w^Strategy_t

"where the portfolio weight w^Strategy_t is defined as the average of modified
versions of the Threshold and Calendar signals... We modify Threshold signal
by rescaling to -Threshold Signal_t / 1.5%... The signal is multiplied by -1
because a positive Threshold value indicates that the S&P 500 is overweight...
the Calendar signal is modified to sign(-Calendar Signal_t) if t falls within
the last week of a month... Furthermore, on the first business day of a new
month, the modified Calendar signal is set to sign(Calendar Signal_{-4}) to
capture potential reversal effects... On any other day, the modified version
of the signal is set to zero."

The MISSING minus sign on the first-business-day term is the paper's own and
is the REVERSAL leg, corroborated by its footnote 27 (p.29, verbatim): "we
also find statistically significant predictability in weeks 1 and 3. In these
weeks, however, the predictive coefficient is positive, consistent with a
reversal of rebalancing pressures."

============================================================================
THE DATA DEVIATION -- ETFs, NOT FUTURES. THE BIG ONE.
============================================================================
[HMM26] uses S&P 500 futures and 10-YEAR TREASURY NOTE FUTURES. This project
has no free roll-adjusted futures series: the identical gap was scoped and
logged THIS SESSION as paid-data gap P4 (Norgate, ~$270/yr) after free Yahoo
futures tickers were proven to carry undetectable fabricated roll returns
(data/research_runs/tsmom_futures_feasibility_2026-09-05.txt). Nothing here
re-litigates that.

SUBSTITUTE: SPY and IEF, through YFinanceProvider.get_price_history off the
point-in-time price store -- the same pair and the same call
vol_regime_timing.TARGET_EQUITY_VS_DURATION already uses, and IEF is the same
instrument cross_sectional_bonds.py has used since 2026-08-26. Coverage
RE-VERIFIED LIVE 2026-09-06: SPY 1993-01-29..2026-09-04 (8,458 rows), IEF
2002-07-30..2026-09-04 (6,065 rows), common window 2002-07-30..2026-09-04
(6,065 rows), zero missing tickers.

WHICH DIRECTION IT BIASES THE RESULT (pre-registration 3.1, restated because
it must travel with the numbers):
 * THE FINANCING LEG LARGELY CANCELS. A futures return is approximately a spot
   total return minus financing; an adjusted-close ETF return is the spot total
   return. Both the paper's dependent variable and this family's traded object
   are DIFFERENCES of an equity and a bond leg, so financing enters with
   opposite signs and cancels to first order.
 * EXPENSE RATIOS are a small one-directional drag on each leg that partly
   cancels in the spread, and what survives is a CONSTANT. A constant drift in
   the dependent variable cannot manufacture predictability from a
   mean-reverting deviation signal; it shifts the intercept, which Eq. (1)
   estimates freely.
 * THE SIGNAL'S OWN INPUT IS ARGUABLY MORE FAITHFUL WITH ETFs. The recursion
   wants "the returns earned by the S&P500 and the 10-year Treasury note" --
   what a real 60/40 fund's holdings earned, a CASH total return, not a futures
   excess return.
 * DURATION MISMATCH IS REAL AND UNQUANTIFIED. IEF tracks 7-10y Treasuries; the
   10-year note future's cheapest-to-deliver sits in a similar but not
   identical band. This changes the bond leg's volatility and hence the SCALE
   of the deviations, not their sign or timing. No adjustment is made.
 * TRACKING ERROR and the ETFs' own creation/redemption flow are unmeasured
   here. Direction unknown, disclosed rather than assumed benign.

WINDOW. Paper: 1997-09-10..2023-03-17. Here: 2002-07-30..2026-09-04, with
formations from 2003-08-01 after a 252-trading-day burn-in for the path-
dependent recursions. Lost: 1997-2002 -- which [HMM26] Section 3 says are the
WEAK years ("the signals' predictive power became significant in the early
2000s"), so the truncation is if anything favourable to the hypothesis.
Gained: 2023-03-18..2026-09-04, ~3.5 years GENUINELY out of sample for the
paper and postdating its March 2025 circulation. That slice is the most
informative thing in this build and is reported separately (F7).

NO MULTIVARIATE CONTROLS. [HMM26]'s headline Table 1 is a multivariate
regression with momentum, trailing return, VIX, MOVE, EPU, ADS and a news
sentiment index. This project has VIX and MOVE but not EPU, ADS or the
Shapiro-Sudhof-Wilson index, and a partial control set is not the paper's
specification. The regressions reported here are the paper's own UNIVARIATE
Eq. (1) and Eq. (3) and are labelled as such; NO Table 1 coefficient is
claimed to be replicated. A traded portfolio has no controls at all, which is
why the CONTROL SPEC below exists instead.

============================================================================
THE 24 SPECS, AND THE ONE THAT MATTERS MOST
============================================================================
6 signals x 2 sizings x 2 holds = 24, asserted three ways in
_build_rebalancing_family() against the pre-declared REBALANCING_N_TRIALS, for
the same reason cross_sectional_bonds.py asserts its 18 and
vol_regime_timing.py its 48: a silent drift in family size silently changes
the DSR denominator for every future run.

SIGNALS
  threshold          Eq. (2), two-sided trigger. The paper's adopted signal.
  threshold_1sided   Same, with Appendix B's literal one-sided trigger.
  calendar           Eq. (B.2) traded UNCONDITIONALLY. PRE-DECLARED TO FAIL:
                     [HMM26]'s own Table 1 Column (1) gives it +0.0553
                     (0.0709), t = +0.78, and Table 2 Panel A Column (1) gives
                     -0.0778 (0.0582) away from month-end. It is the matched
                     negative control for calendar_week4, not a candidate.
  calendar_week4     Eq. (B.2) gated to the last 5 trading days plus Section
                     4's first-business-day reversal leg. The paper's actual
                     calendar claim.
  paper_combined     [HMM26] Section 4's w^Strategy verbatim. Its published
                     counterpart reports Sharpe 1.11 (Table 6 Panel A) with
                     CAPM alpha 9.61%/yr (s.e. 1.77). This is the spec the
                     family exists to test.
  trailing21_ctrl    THE CONTROL, and the most important spec here. The SAME
                     deviation formula on a rolling 21-TRADING-DAY window of
                     cumulative SPY and IEF returns, with NO trigger and NO
                     calendar. Same units, same scale, same sign convention.
                     It carries the trailing-return content of the rebalancing
                     signals and none of their structure.
                     PRE-DECLARED READING (pre-registration section 5): if it
                     matches or beats the rebalancing signals, this family
                     measured 21-day cross-asset REVERSAL wearing a
                     rebalancing costume, and the report says so regardless of
                     the DSR. Motivated by the paper's own admission (p.16)
                     that "Momentum and rebalancing signals have a correlation
                     higher than 67%".

SIZINGS, both cited to [HMM26] Section 4
  scaled   position = -signal / 1.5%   (the paper's own rescaling). NOT
           clipped, because the paper does not clip; realized max |position|
           is reported so the implied leverage is visible. For
           paper_combined this means w^Strategy verbatim -- the rescaling is
           already inside it and is not applied twice.
  sign     position = -sign(signal)    (the paper's own Calendar treatment).
           For paper_combined, sign(w^Strategy).

HOLDS: 1 and 5 trading days. h=1 IS Eq. (1) traded. h=5 is an h-SLEEVE
OVERLAPPING BOOK -- the held position is the equal-weighted mean of the last h
daily targets, i.e. h equal sleeves each formed on a different day and held h
days. That is a genuinely different book, not a rescaling: it smooths a
one-day-ahead prediction across five days, so if the effect really is one-day
it should DEGRADE there, while turnover falls by roughly 1/h. No h >= 21: a
21-day hold of a next-day prediction is a different claim, not a slower
version of this one.

DIRECTION IS NOT A FREE PARAMETER. Every spec trades REBALANCING_DIRECTION =
-1, fixed by [HMM26] p.10 ("both Threshold and Calendar signals should
negatively predict equity market returns and positively predict Treasury
market returns") before any return was computed. Specs whose realized sign is
the opposite print negative Sharpes and are NOT flipped; a flipped family is a
second 24-trial search and must be counted as one.

============================================================================
COSTS -- AND THIS IS THE FAMILY WHERE THEY BITE
============================================================================
REBALANCING_COST_BPS = 2.0 one-way per unit of gross notional traded. Same
instruments and same grounding as vol_regime_timing.py, whose docstring
measures it: a one-cent bid/ask on SPY (~$6xx) is ~0.08bp and on IEF (~$95)
~1.05bp, so the binding leg is IEF at ~1.05bp of half-spread and 2.0bp one-way
sits deliberately above it to cover commission and slippage. A unit position
change trades 2.0 units of gross notional, so a flat-to-unit swing costs ~4bp
and a full +1 -> -1 reversal ~8bp.

PRE-ACKNOWLEDGED: at h=1 with `sign` sizing this book can reverse in a day.
The paper trades FUTURES, whose all-in costs are far below an ETF pair's, and
its own cost treatment is a single sentence (p.38: "Following the conservative
assumptions of Harvey et al. (2018), we estimate that the Sharpe ratio net of
transaction costs remains close to 1") with no turnover figure tabulated. This
build does not inherit that reassurance and prices its own turnover.

REBALANCING_SHORT_BORROW_BPS_PER_YEAR = borrow_cost.
GENERAL_COLLATERAL_BPS_PER_YEAR = 34.0, on the SHORT notional only, accrued on
CALENDAR days / 365 (a weekend costs three days -- charging per trading day
would undercharge a continuously-held book by ~31%). SOURCED, not assumed:
Beneish, Lee & Nichols, "In Short Supply", JAE 60(1), 2015, p.15 (DCBS=1 fees
average <34bp/yr), the conservative envelope over D'Avolio (2002) Table 3's
17bp value-weighted GC mean. Deliberately the project's SOURCED rate rather
than vol_regime_timing.py's unsourced 50bp. The long leg is not separately
financed: the book is dollar-neutral and self-financing, the assumption
metrics.sharpe_ratio already documents.

The two are reported separately and never summed -- turnover cost scales with
trading more often, financing with holding longer, and they push in opposite
directions across the very holding axis this family searches.

============================================================================
WHAT COULD MAKE A POSITIVE RESULT HERE FAKE -- CHECKED IN-MODULE
============================================================================
 1. STATIC TILT, and this family is STRUCTURALLY exposed to it. [HMM26] p.14
    says the average value of both signals is POSITIVE, which under DIRECTION
    = -1 means the book is short equity / long bonds more often than not --
    and over 2003-2026 that is a large persistent loser. So the tilt here
    threatens to hide a real signal rather than to fake one, which is the
    opposite of the usual direction and is why BOTH the raw and the
    beta-hedged Sharpe are reported for every spec. The hedged stream is
    y - beta*x, NOT the OLS residual: an OLS residual with an intercept has
    mean exactly zero by construction, so its Sharpe is ~0 for every strategy
    ever measured, and computing it that way would report every spec as a
    disguised tilt with total confidence. vol_regime_timing.py found that trap
    first and its _ols_beta_alpha is imported here rather than re-derived.
 2. THE SIGNAL IS MECHANICALLY A TRAILING-RETURN FUNCTION. Every signal here
    is a smooth function of past SPY-minus-IEF returns; the paper concedes
    correlation with momentum above 67% and handles it with multivariate
    controls, which a traded portfolio cannot have. `trailing21_ctrl` is the
    whole defence.
 3. TWO CRISES. 2008-09 and March 2020 are exactly the windows [HMM26] p.38
    excludes when it reports its own Sharpe falling 1.11 -> 0.90. Every spec
    reports its Sharpe in equal thirds AND excluding those two windows.
 4. PUBLICATION AND CROWDING. Circulated March 2025, revised January 2026,
    presented at the AFA 2026 Annual Meeting, and about the single most
    predictable flow in markets. Every spec's Sharpe is reported separately
    inside and after the paper's own estimation window.
 5. THE SEARCH THAT LED HERE IS NOT ALL IN n_trials. 24 is the size of THIS
    family, declared before any return was computed. dsr_n_trials raises it to
    the project-wide effectively-independent count when that is larger, and
    the report also carries the 481 and 857 pooled denominators -- but no
    denominator captures the choice to read this particular paper.

RESIDUAL BIASES NOT FIXED, only disclosed: SPY and IEF were chosen today from
instruments that still exist and are still liquid (the hindsight-selection
channel cross_sectional.fixed_universe_membership documents -- small for these
two, not zero). Formation is assumed executable at the exact closing print.
Position weights inside an h-sleeve book are re-set daily, which is what the
turnover charge prices.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.borrow_cost import GENERAL_COLLATERAL_BPS_PER_YEAR
from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe

# dsr_n_trials is imported ALONE and on one line, deliberately:
# tests/test_global_effective_n.py's "every DSR call site routes through the
# pooled denominator" guard scans module source for the literal string
# "global_effective_n import dsr_n_trials", and a wrapped multi-name import
# would make this module look unpooled to it when it is not.
# load_global_effective_n is imported inside policy_d_denominators instead,
# exactly as cross_sectional_tax_loss_selling.py does it.
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio
from app.services.research_lab.preservation_score import compute_preservation_metrics
from app.services.research_lab.registration_scorecard import policy_d_verdict
from app.services.research_lab.vol_regime_timing import (
    MIN_REPLAY_TRADING_DAYS,
    _ols_beta_alpha,
    block_bootstrap_sharpe_pvalue,
)

logger = logging.getLogger(__name__)

# --- the traded instruments ------------------------------------------------

EQUITY_TICKER = "SPY"
BOND_TICKER = "IEF"
TRADED_UNIVERSE: tuple[str, ...] = (EQUITY_TICKER, BOND_TICKER)

# VERIFIED LIVE 2026-09-06 through this project's own point-in-time price
# store, not taken on trust: SPY 1993-01-29, IEF 2002-07-30. IEF binds.
VERIFIED_TICKER_START: dict[str, date] = {
    EQUITY_TICKER: date(1993, 1, 29),
    BOND_TICKER: date(2002, 7, 30),
}
COMMON_HISTORY_START = date(2002, 7, 30)

# --- the paper's own constants, inherited and never searched ---------------

# [HMM26] Appendix B: "Target weights follow a common 60/40 allocation."
TARGET_EQUITY_WEIGHT = 0.60

# [HMM26] Eq. (2), verbatim: "delta values that span the range 0%-2.5% with
# increments of 0.1%". 26 values including both endpoints. INHERITED from the
# published paper; not tuned, not searched, and not chosen with any knowledge
# of how it performs on SPY/IEF.
DELTA_GRID: tuple[float, ...] = tuple(round(i / 1000.0, 4) for i in range(26))
assert len(DELTA_GRID) == 26 and DELTA_GRID[0] == 0.0 and DELTA_GRID[-1] == 0.025

# [HMM26] Section 4, verbatim: "We modify Threshold signal by rescaling to
# -Threshold Signal_t / 1.5% so that the two rebalancing signals have the same
# risk contribution to the strategy". A published constant, inherited.
SIGNAL_RESCALE = 0.015

# [HMM26] p.14, verbatim: week4 "corresponds to Dummy^{5 Days}_t". The paper's
# own adopted choice after its Figure 3 sweep; not searched here.
WEEK4_TRADING_DAYS = 5

# [HMM26] Section 4: "on the first business day of a new month, the modified
# Calendar signal is set to sign(Calendar Signal_{-4})". Read as lag 4 -- on
# the first trading day of a month, t-4 is the fourth-to-last trading day of
# the previous month under either reading, so the interpretation is not
# load-bearing (pre-registration 3.6).
MONTH_START_REVERSAL_LAG = 4

# The CONTROL spec's window, fixed a priori rather than tuned: [HMM26] p.14
# reports the Threshold approach's median rebalancing frequency as "about 16
# times per year" (~16 trading days between resets) and the Calendar
# approach's as 12 (~21 trading days, one month). 21 trading days sits at the
# calendar arm's own cadence and just above the threshold arm's.
CONTROL_WINDOW_DAYS = 21

# --- pre-declared family parameters ----------------------------------------

# Uniform, pre-declared, never fitted. [HMM26] p.10: "both Threshold and
# Calendar signals should negatively predict equity market returns and
# positively predict Treasury market returns."
REBALANCING_DIRECTION = -1.0

REBALANCING_HOLDING_DAYS: tuple[int, ...] = (1, 5)

REBALANCING_N_TRIALS = 24

# One-way, per unit of gross notional traded. See the module docstring's COSTS
# section for the quoted-spread arithmetic behind 2.0.
REBALANCING_COST_BPS = 2.0

# Per year, on the SHORT notional only. SOURCED -- see COSTS.
REBALANCING_SHORT_BORROW_BPS_PER_YEAR = GENERAL_COLLATERAL_BPS_PER_YEAR

# 365, not 252 -- financing accrues on calendar days. Same reasoning as
# cross_sectional.FINANCING_DAYS_PER_YEAR and vol_regime_timing.py.
FINANCING_DAYS_PER_YEAR = 365.0

# Formations begin here: the first trading day on or after this date, which
# sits 254 trading rows into the common SPY/IEF history (verified 2026-09-06:
# row 253 is 2003-07-31), i.e. more than a full 252-day burn-in for the
# path-dependent threshold and calendar recursions. Pre-declared so the window
# is a stated choice rather than whatever the data happened to allow.
REBALANCING_FORMATION_START = date(2003, 8, 1)
REBALANCING_BURN_IN_TRADING_DAYS = 252

# Calendar padding fetched before the formation start, purely to warm the
# recursions. Formations never occur in the padding.
REBALANCING_HISTORY_PADDING_CALENDAR_DAYS = 500

# [HMM26]'s own estimation window ends here. Everything after it is genuinely
# out of sample for the paper and postdates its March 2025 first circulation.
PAPER_SAMPLE_START = date(1997, 9, 10)
PAPER_SAMPLE_END = date(2023, 3, 17)

# The two windows [HMM26] p.38 excludes when it reports its own strategy's
# Sharpe falling from 1.11 to 0.90, verbatim: "even after excluding the
# September 2008 to March 2009 and March 2020 periods".
CRISIS_WINDOWS: tuple[tuple[date, date], ...] = (
    (date(2008, 9, 1), date(2009, 3, 31)),
    (date(2020, 3, 1), date(2020, 3, 31)),
)

# Policy D bars, identical to every other family here.
VALIDATED_EDGE_BAR = 0.95
SCREENING_FLOOR = 0.50

REBALANCING_CITATION = (
    "Harvey, Mazzoleni & Melone, 'The Unintended Consequences of Rebalancing', NBER Working "
    "Paper No. 33554, March 2025, revised January 2026 -- simulated 60/40 rebalancing weight "
    "deviations (Eqs. B.1-B.2) negatively predict next-day S&P 500 returns in excess of the "
    "10-year Treasury note (Eq. 1), with predictability concentrated in the last five trading "
    "days of the month (Eq. 3). NOT PEER REVIEWED: an NBER working paper, whose own cover page "
    "states it has not been refereed."
)

CONTROL_CITATION = (
    "CONTROL SPEC, not a candidate: the same weight-deviation formula on a plain rolling "
    "21-trading-day window, carrying the trailing-return content of Harvey/Mazzoleni/Melone's "
    "signals and none of their trigger or calendar structure. Motivated by the paper's own "
    "p.16 statement that 'Momentum and rebalancing signals have a correlation higher than 67%'."
)


# --- the recursion ---------------------------------------------------------


def rebalanced_weight(w: float, equity_return: float, bond_return: float) -> float:
    """[HMM26] p.10 / Appendix B, the 60/40 weight transition:

        w_{t+1} = w(1+R^SP) / [ w(1+R^SP) + (1-w)(1+R^10Y) ]

    KNOWN-ANSWER VALIDATED before it is trusted on real data, per CLAUDE.md's
    rule against implementing a published formula from memory. [HMM26]
    footnote 8, verbatim: "If the equity market increases by 10% and the bond
    market remains unchanged, the portfolio value becomes 66 + 40 = $106. The
    equity allocation is now 66/106 = 62.26%." tests/ pins
    rebalanced_weight(0.60, 0.10, 0.0) against 66/106 exactly and against the
    paper's own printed 0.6226.

    Returns NaN for a non-finite input or a non-positive portfolio value (a
    total wipeout of both legs), which propagates to a NaN signal -- the
    honest "cannot evaluate this day" answer rather than a fabricated number.
    """
    if not (np.isfinite(w) and np.isfinite(equity_return) and np.isfinite(bond_return)):
        return float("nan")
    equity_value = w * (1.0 + equity_return)
    total = equity_value + (1.0 - w) * (1.0 + bond_return)
    if not np.isfinite(total) or total <= 0.0:
        return float("nan")
    return float(equity_value / total)


def _daily_returns(close: pd.DataFrame) -> pd.DataFrame:
    """Close-to-close simple returns. fill_method=None for the same reason
    cross_sectional.py and cross_sectional_bonds.py use it: a mid-series NaN
    must yield a NaN return, never pandas' legacy forward-fill, which would
    fabricate a 0% return for a day the instrument did not trade."""
    return close.pct_change(fill_method=None)


def threshold_signal_series(
    equity_returns: pd.Series,
    bond_returns: pd.Series,
    delta: float,
    *,
    two_sided: bool = True,
) -> pd.Series:
    """[HMM26] Eq. (B.1): the simulated 60/40 portfolio's deviation from its
    60% equity target, for a rebalancing band of `delta`.

    The recursion, exactly as the module docstring transcribes it:

        signal_t = w(w_state_{t-1}; R^SP_t; R^10Y_t) - 60%
        w_state_t = 60%    if the trigger fired on w_state_{t-1}
                  = the drifted weight above    otherwise

    The SIGNAL is always the drifted deviation whether or not a rebalance
    fired; only the STATE resets. The trigger is evaluated on the PREVIOUS
    state, which is the paper's own one-day implementation lag.

    `two_sided` selects |w - 60%| >= delta (the main-text reading, PRIMARY --
    see the module docstring's four citations for it) against Appendix B's
    literal displayed w - 60% >= delta. Both are screened as separate,
    counted specs; neither is chosen after seeing a result.

    At delta = 0 the two-sided trigger is always true, so the portfolio resets
    every day -- which is exactly what [HMM26] p.11 says ("When delta = 0, the
    60/40 portfolio rebalances 252 times per year").

    A NaN return leaves the state untouched and yields a NaN signal for that
    day: a day on which one leg did not trade is unobservable, not a day on
    which nothing happened.
    """
    if delta < 0.0:
        raise ValueError(f"delta must be non-negative, got {delta}")

    index = equity_returns.index
    out = np.full(len(index), np.nan, dtype=float)
    state = TARGET_EQUITY_WEIGHT
    equity = equity_returns.to_numpy(dtype=float)
    bond = bond_returns.to_numpy(dtype=float)

    for i in range(len(index)):
        r_e = equity[i]
        r_b = bond[i]
        if not (np.isfinite(r_e) and np.isfinite(r_b)):
            continue
        drifted = rebalanced_weight(state, r_e, r_b)
        if not np.isfinite(drifted):
            continue
        out[i] = drifted - TARGET_EQUITY_WEIGHT
        deviation = state - TARGET_EQUITY_WEIGHT
        triggered = (abs(deviation) >= delta) if two_sided else (deviation >= delta)
        state = TARGET_EQUITY_WEIGHT if triggered else drifted

    return pd.Series(out, index=index, name=f"threshold_{delta}")


def threshold_reset_count(
    equity_returns: pd.Series,
    bond_returns: pd.Series,
    delta: float,
    *,
    two_sided: bool = True,
) -> int:
    """How many times the threshold recursion actually rebalanced. Measured
    rather than assumed, because [HMM26] p.11 and p.14 both make quantitative
    claims about it ("When delta = 0, the 60/40 portfolio rebalances 252 times
    per year"; "the median rebalancing frequency of the Threshold signal is
    about 16 times per year") and fidelity check F4 compares against them."""
    state = TARGET_EQUITY_WEIGHT
    resets = 0
    equity = equity_returns.to_numpy(dtype=float)
    bond = bond_returns.to_numpy(dtype=float)
    for i in range(len(equity)):
        r_e = equity[i]
        r_b = bond[i]
        if not (np.isfinite(r_e) and np.isfinite(r_b)):
            continue
        drifted = rebalanced_weight(state, r_e, r_b)
        if not np.isfinite(drifted):
            continue
        deviation = state - TARGET_EQUITY_WEIGHT
        triggered = (abs(deviation) >= delta) if two_sided else (deviation >= delta)
        if triggered:
            resets += 1
            state = TARGET_EQUITY_WEIGHT
        else:
            state = drifted
    return resets


def averaged_threshold_signal(
    equity_returns: pd.Series,
    bond_returns: pd.Series,
    *,
    two_sided: bool = True,
    deltas: tuple[float, ...] = DELTA_GRID,
) -> pd.Series:
    """[HMM26] Eq. (2): the simple average of Threshold Signal^delta over the
    published delta grid (0%-2.5% in 0.1% steps, 26 values).

    Averaging "approximates what a heterogeneous group of investors might
    implement while also reducing the set of potential predictors" ([HMM26]
    p.12). The grid is inherited from the paper; this module does not choose
    it and does not search it."""
    frame = pd.concat(
        [
            threshold_signal_series(equity_returns, bond_returns, d, two_sided=two_sided)
            for d in deltas
        ],
        axis=1,
    )
    return frame.mean(axis=1, skipna=False).rename("threshold")


def month_end_flags(index: pd.DatetimeIndex) -> np.ndarray:
    """True on the LAST trading day of each calendar month present in the
    index. Derived from the traded calendar itself rather than from a holiday
    library, so "last business day" means the last day this book could
    actually have traded."""
    periods = index.to_period("M")
    if len(periods) == 0:
        return np.zeros(0, dtype=bool)
    out = np.zeros(len(periods), dtype=bool)
    values = periods.to_numpy()
    out[:-1] = values[:-1] != values[1:]
    # The final row of the panel is the last trading day of ITS month so far,
    # so it is flagged. That is the honest answer for a partial trailing
    # month, and it can only affect the very last formation.
    out[-1] = True
    return out


def last_n_trading_days_mask(index: pd.DatetimeIndex, n: int) -> np.ndarray:
    """[HMM26] Eq. (3)'s Dummy^{N Days}: True on the last n TRADING days of
    each calendar month. Trading days rather than calendar days is the only
    reading consistent with the paper's daily futures observations and its
    "Days to end-of-month" axis; declared in the pre-registration (3.5)
    rather than discovered.

    DISCLOSED EDGE CASE: the panel's final, incomplete calendar month has its
    own last n trading days flagged even though that month has not ended. On a
    ~5,800-day formation window that is at most 5 days (0.09%), it affects only
    the very end of the sample, and it is left visible rather than papered over
    with a look-ahead-flavoured "is this month complete" test."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    periods = index.to_period("M")
    out = np.zeros(len(index), dtype=bool)
    # Position from the END of each month's own block of trading days.
    counts: dict[pd.Period, int] = {}
    for period in periods:
        counts[period] = counts.get(period, 0) + 1
    seen: dict[pd.Period, int] = {}
    for i, period in enumerate(periods):
        seen[period] = seen.get(period, 0) + 1
        if counts[period] - seen[period] < n:
            out[i] = True
    return out


def calendar_signal_series(
    equity_returns: pd.Series,
    bond_returns: pd.Series,
    *,
    reset_on_month_end_day: bool = False,
) -> pd.Series:
    """[HMM26] Eq. (B.2): the same deviation, with a month-end reset instead
    of a band.

    `reset_on_month_end_day=False` (the DEFAULT and the traded form) is the
    paper's LITERAL displayed rule -- the state resets on the day AFTER the
    month-end day, because the trigger is evaluated on the previous day's
    date, exactly as the threshold trigger is evaluated on the previous day's
    state. `True` is the economically natural alternative (the fund trades at
    the close of the month-end day itself). The two differ on exactly one day
    per month -- the first trading day of the new month, which the week4 gate
    excludes and which Section 4 overrides with its own reversal term. The
    correlation between them is reported as a diagnostic rather than argued
    about; see the module docstring's ONE-DAY AMBIGUITY note."""
    index = equity_returns.index
    is_month_end = month_end_flags(index)
    out = np.full(len(index), np.nan, dtype=float)
    state = TARGET_EQUITY_WEIGHT
    equity = equity_returns.to_numpy(dtype=float)
    bond = bond_returns.to_numpy(dtype=float)

    for i in range(len(index)):
        r_e = equity[i]
        r_b = bond[i]
        if not (np.isfinite(r_e) and np.isfinite(r_b)):
            continue
        drifted = rebalanced_weight(state, r_e, r_b)
        if not np.isfinite(drifted):
            continue
        out[i] = drifted - TARGET_EQUITY_WEIGHT
        if reset_on_month_end_day:
            triggered = bool(is_month_end[i])
        else:
            triggered = bool(is_month_end[i - 1]) if i >= 1 else False
        state = TARGET_EQUITY_WEIGHT if triggered else drifted

    return pd.Series(out, index=index, name="calendar")


def trailing_window_signal(
    equity_returns: pd.Series, bond_returns: pd.Series, window: int = CONTROL_WINDOW_DAYS
) -> pd.Series:
    """THE CONTROL SIGNAL. The same 60/40 deviation formula evaluated on a
    plain rolling `window`-trading-day block of cumulative returns, with NO
    threshold trigger and NO calendar structure:

        deviation_t = w(60%; cum_window R^SP; cum_window R^10Y) - 60%

    Identical units, identical scale and identical sign convention to the two
    rebalancing signals, so its Sharpe is directly comparable to theirs. What
    it does NOT contain is any rebalancing mechanism. If this matches or beats
    them, the family measured 21-day cross-asset reversal wearing a
    rebalancing costume -- the pre-declared reading fixed in the
    pre-registration, section 5.

    Deliberately equivalent to "a portfolio that resets to target exactly
    `window` trading days ago", i.e. the same object with a mechanical rather
    than a triggered or calendrical reset."""
    log_e = np.log1p(equity_returns.astype(float))
    log_b = np.log1p(bond_returns.astype(float))
    cum_e = np.expm1(log_e.rolling(window, min_periods=window).sum())
    cum_b = np.expm1(log_b.rolling(window, min_periods=window).sum())

    values = [
        rebalanced_weight(TARGET_EQUITY_WEIGHT, e, b) - TARGET_EQUITY_WEIGHT
        for e, b in zip(cum_e.to_numpy(), cum_b.to_numpy(), strict=True)
    ]
    return pd.Series(values, index=equity_returns.index, name=f"trailing{window}")


# --- signal -> position ----------------------------------------------------


def week4_modified_calendar_position(
    calendar_signal: pd.Series, *, use_sign: bool
) -> pd.Series:
    """[HMM26] Section 4's "modified" Calendar signal, verbatim:

      * sign(-Calendar Signal_t)          if t is in the last week of a month
      * sign(Calendar Signal_{t-4})       on the first trading day of a month
                                          -- NOTE the missing minus, the
                                          paper's own REVERSAL leg
      * 0                                 on any other day

    `use_sign=False` replaces the two sign() calls with the Section 4
    Threshold rescaling (-signal / 1.5%, and +signal_{t-4} / 1.5% on the
    reversal leg) so that the family's two sizing arms are the same two
    transforms everywhere. That is a declared grid axis, not a construction
    choice made after a result."""
    index = calendar_signal.index
    week4 = last_n_trading_days_mask(index, WEEK4_TRADING_DAYS)
    is_month_end = month_end_flags(index)
    # First trading day of a month == the day after a month-end day.
    first_of_month = np.zeros(len(index), dtype=bool)
    first_of_month[1:] = is_month_end[:-1]

    signal = calendar_signal.to_numpy(dtype=float)
    lagged = np.full(len(index), np.nan, dtype=float)
    if len(index) > MONTH_START_REVERSAL_LAG:
        lagged[MONTH_START_REVERSAL_LAG:] = signal[:-MONTH_START_REVERSAL_LAG]

    out = np.zeros(len(index), dtype=float)
    for i in range(len(index)):
        if first_of_month[i]:
            # NO minus sign: the paper's reversal leg, and it reads the LAGGED
            # signal, so today's own signal being unobservable does not block
            # it.
            source = lagged[i]
            out[i] = (
                np.nan
                if not np.isfinite(source)
                else (np.sign(source) if use_sign else source / SIGNAL_RESCALE)
            )
        elif week4[i]:
            source = signal[i]
            out[i] = (
                np.nan
                if not np.isfinite(source)
                else (-np.sign(source) if use_sign else -source / SIGNAL_RESCALE)
            )
        elif not np.isfinite(signal[i]):
            # The recursion could not be evaluated at all on this day (one leg
            # did not trade). Unobservable, not flat.
            out[i] = np.nan
        else:
            # Genuinely flat by design, not missing. Zeros here are part of
            # the strategy and belong in its return series: a book that is in
            # cash ~76% of sessions really does earn the lower annualized
            # Sharpe that including them produces, and dropping them would
            # report the Sharpe of a strategy nobody could have run.
            out[i] = 0.0
    return pd.Series(out, index=index, name="calendar_week4_position")


def _plain_position(signal: pd.Series, *, use_sign: bool) -> pd.Series:
    """The two sizing transforms from [HMM26] Section 4, applied to a raw
    deviation signal. Both carry REBALANCING_DIRECTION = -1 explicitly rather
    than as a hard-coded minus, so the pre-declared sign is visible at the one
    place it is applied."""
    values = signal.astype(float)
    if use_sign:
        return (REBALANCING_DIRECTION * np.sign(values)).rename("position")
    # Not clipped: [HMM26] Section 4 does not clip, and the realized maximum
    # |position| is reported instead so the implied leverage is visible.
    return (REBALANCING_DIRECTION * values / SIGNAL_RESCALE).rename("position")


# --- the family ------------------------------------------------------------

SignalBuilder = Callable[[pd.Series, pd.Series], pd.Series]


@dataclass(frozen=True)
class RebalancingSpec:
    spec_id: str
    signal_key: str
    sizing: str  # "scaled" | "sign"
    holding_days: int
    citation: str
    hypothesis: str
    is_control: bool = False


@dataclass(frozen=True)
class SignalDefinition:
    key: str
    hypothesis: str
    citation: str
    is_control: bool
    # Produces the RAW deviation signal. None for paper_combined, which
    # produces an already-sized position instead.
    raw_builder: SignalBuilder | None
    # Produces a POSITION directly (calendar_week4 and paper_combined, whose
    # sizing rules are part of [HMM26] Section 4's own construction).
    position_builder: Callable[[pd.Series, pd.Series, bool], pd.Series] | None


def _calendar_week4_position(
    equity_returns: pd.Series, bond_returns: pd.Series, use_sign: bool
) -> pd.Series:
    return week4_modified_calendar_position(
        calendar_signal_series(equity_returns, bond_returns), use_sign=use_sign
    )


def _paper_combined_position(
    equity_returns: pd.Series, bond_returns: pd.Series, use_sign: bool
) -> pd.Series:
    """[HMM26] Section 4's w^Strategy: "the average of modified versions of the
    Threshold and Calendar signals". The Threshold leg is -Threshold/1.5% and
    the Calendar leg is the week4-modified sign series, both verbatim.

    `use_sign=True` takes sign(w^Strategy) -- a declared second sizing arm,
    NOT a second application of the rescaling (which is already inside the
    Threshold leg and is not applied twice)."""
    threshold_leg = _plain_position(
        averaged_threshold_signal(equity_returns, bond_returns, two_sided=True),
        use_sign=False,
    )
    calendar_leg = week4_modified_calendar_position(
        calendar_signal_series(equity_returns, bond_returns), use_sign=True
    )
    combined = (threshold_leg + calendar_leg) / 2.0
    if use_sign:
        return np.sign(combined).rename("position")
    return combined.rename("position")


_SIGNAL_DEFINITIONS: tuple[SignalDefinition, ...] = (
    SignalDefinition(
        key="threshold",
        hypothesis=(
            "Simulated 60/40 equity weight above target -> institutions sell equities and buy "
            "bonds -> next-day equity-minus-Treasury return is lower. [HMM26] Eq. (2), "
            "two-sided rebalancing band."
        ),
        citation=REBALANCING_CITATION,
        is_control=False,
        raw_builder=lambda e, b: averaged_threshold_signal(e, b, two_sided=True),
        position_builder=None,
    ),
    SignalDefinition(
        key="threshold_1sided",
        hypothesis=(
            "Identical, using Appendix B's LITERAL one-sided trigger (w - 60% >= delta). A "
            "robustness arm that costs trials on purpose, because the paper contradicts "
            "itself about the trigger and resolving that must not be a free choice."
        ),
        citation=REBALANCING_CITATION,
        is_control=False,
        raw_builder=lambda e, b: averaged_threshold_signal(e, b, two_sided=False),
        position_builder=None,
    ),
    SignalDefinition(
        key="calendar",
        hypothesis=(
            "MATCHED NEGATIVE CONTROL, PRE-DECLARED TO FAIL: [HMM26] Eq. (B.2) traded on every "
            "day of the month. The paper's own Table 1 Column (1) gives this signal +0.0553 "
            "(0.0709), t = +0.78, i.e. no predictive power away from month-end."
        ),
        citation=REBALANCING_CITATION,
        is_control=False,
        raw_builder=lambda e, b: calendar_signal_series(e, b),
        position_builder=None,
    ),
    SignalDefinition(
        key="calendar_week4",
        hypothesis=(
            "[HMM26]'s actual calendar claim: Eq. (B.2) traded only in the last 5 trading days "
            "of the month (Eq. 3's week4, Table 1's Calendar*week4 = -0.3029, t = -3.75), plus "
            "Section 4's first-trading-day reversal leg."
        ),
        citation=REBALANCING_CITATION,
        is_control=False,
        raw_builder=None,
        position_builder=_calendar_week4_position,
    ),
    SignalDefinition(
        key="paper_combined",
        hypothesis=(
            "[HMM26] Section 4's own front-running strategy w^Strategy verbatim, whose "
            "published counterpart reports Sharpe 1.11 with CAPM alpha 9.61%/yr (Table 6). "
            "The spec this family exists to test."
        ),
        citation=REBALANCING_CITATION,
        is_control=False,
        raw_builder=None,
        position_builder=_paper_combined_position,
    ),
    SignalDefinition(
        key="trailing21_ctrl",
        hypothesis=(
            "CONTROL: the same deviation formula on a plain rolling 21-trading-day window, "
            "with no trigger and no calendar. If it matches or beats the rebalancing signals, "
            "this family measured 21-day cross-asset reversal, not rebalancing pressure."
        ),
        citation=CONTROL_CITATION,
        is_control=True,
        raw_builder=lambda e, b: trailing_window_signal(e, b, CONTROL_WINDOW_DAYS),
        position_builder=None,
    ),
)

REBALANCING_SIZINGS: tuple[str, ...] = ("scaled", "sign")


def _build_rebalancing_family() -> list[RebalancingSpec]:
    """The exact product _SIGNAL_DEFINITIONS x REBALANCING_SIZINGS x
    REBALANCING_HOLDING_DAYS. The literal length of this list is the n_trials
    denominator screen_rebalancing_pressure uses -- every definition counts,
    whether or not it survives the data floors, because shrinking the
    denominator to "specs that worked" would be gameable by declaring specs
    expected to fail (and this family declares two that are)."""
    specs: list[RebalancingSpec] = []
    for definition in _SIGNAL_DEFINITIONS:
        for sizing in REBALANCING_SIZINGS:
            for holding in REBALANCING_HOLDING_DAYS:
                specs.append(
                    RebalancingSpec(
                        spec_id=f"rebal_{definition.key}_{sizing}_h{holding}",
                        signal_key=definition.key,
                        sizing=sizing,
                        holding_days=holding,
                        citation=definition.citation,
                        hypothesis=definition.hypothesis,
                        is_control=definition.is_control,
                    )
                )

    expected = (
        len(_SIGNAL_DEFINITIONS) * len(REBALANCING_SIZINGS) * len(REBALANCING_HOLDING_DAYS)
    )
    assert len(specs) == expected == REBALANCING_N_TRIALS, (
        f"Rebalancing-pressure family built {len(specs)} definitions; the grid "
        f"({len(_SIGNAL_DEFINITIONS)} signals x {len(REBALANCING_SIZINGS)} sizings x "
        f"{len(REBALANCING_HOLDING_DAYS)} holding periods) implies {expected}; the "
        f"pre-declared REBALANCING_N_TRIALS is {REBALANCING_N_TRIALS}. All three must agree "
        "-- a drift here silently changes the DSR's multiple-comparisons denominator for "
        "every future run."
    )
    assert len({s.spec_id for s in specs}) == len(specs), "spec_ids must be unique"
    assert all(s.holding_days in REBALANCING_HOLDING_DAYS for s in specs)
    assert sum(1 for s in specs if s.is_control) == len(REBALANCING_SIZINGS) * len(
        REBALANCING_HOLDING_DAYS
    ), "exactly one signal definition is the control, and it must appear in every cell"
    return specs


REBALANCING_FAMILY: list[RebalancingSpec] = _build_rebalancing_family()

_DEFINITION_BY_KEY = {d.key: d for d in _SIGNAL_DEFINITIONS}


# --- config ----------------------------------------------------------------


@dataclass
class RebalancingConfig:
    cost_bps: float = REBALANCING_COST_BPS
    short_borrow_bps_per_year: float = REBALANCING_SHORT_BORROW_BPS_PER_YEAR
    formation_start: date = REBALANCING_FORMATION_START


def default_rebalancing_config() -> RebalancingConfig:
    """This family's cost configuration, as a FUNCTION rather than a module
    singleton so callers cannot mutate shared state -- the same reason
    cross_sectional_bonds.default_bonds_config() and
    vol_regime_timing.default_vol_regime_config() are functions."""
    return RebalancingConfig()


# The pre-declared cost sensitivity ladder (pre-registration section 7). Same
# 24 specs, same DSR denominators, only the returns change -- these are NOT
# new trials.
@dataclass(frozen=True)
class CostArm:
    key: str
    description: str
    cost_bps: float
    short_borrow_bps_per_year: float


COST_ARMS: tuple[CostArm, ...] = (
    CostArm(
        key="cost_free",
        description="cost_bps=0, borrow=0 -- the GROSS signal, for attribution only, never a verdict input",
        cost_bps=0.0,
        short_borrow_bps_per_year=0.0,
    ),
    CostArm(
        key="baseline",
        description=(
            "cost_bps=2.0 one-way (above IEF's ~1.05bp quoted half-spread), borrow=34bp/yr "
            "general collateral (Beneish/Lee/Nichols 2015 p.15) -- THE VERDICT ARM"
        ),
        cost_bps=REBALANCING_COST_BPS,
        short_borrow_bps_per_year=REBALANCING_SHORT_BORROW_BPS_PER_YEAR,
    ),
    CostArm(
        key="stress",
        description=(
            "cost_bps=10.0 one-way (~10x IEF's quoted half-spread), borrow=34bp/yr -- a "
            "deliberate UNSOURCED stress standing in for market impact and adverse selection "
            "on a daily-turnover book"
        ),
        cost_bps=10.0,
        short_borrow_bps_per_year=REBALANCING_SHORT_BORROW_BPS_PER_YEAR,
    ),
)
BASELINE_COST_ARM = "baseline"


# --- data ------------------------------------------------------------------


@dataclass(frozen=True)
class RebalancingData:
    """SPY and IEF closes on one shared trading calendar, plus the derived
    daily returns and the buy-and-hold spread every diagnostic regresses
    against."""

    close: pd.DataFrame
    equity_returns: pd.Series
    bond_returns: pd.Series
    spread_returns: pd.Series


def align_rebalancing_data(close: pd.DataFrame) -> RebalancingData:
    """Reduces to days on which BOTH instruments printed -- a spread cannot be
    held on a day one leg did not trade -- and derives the return series once
    so every signal builder sees the same inputs."""
    frame = close.dropna(axis=1, how="all").dropna(axis=0, how="any")
    for ticker in TRADED_UNIVERSE:
        if ticker not in frame.columns:
            raise ValueError(
                f"{ticker} is absent from the price panel; this family cannot be replayed "
                "without both legs."
            )
    returns = _daily_returns(frame)
    equity = returns[EQUITY_TICKER].rename("equity")
    bond = returns[BOND_TICKER].rename("bond")
    spread = (equity - bond).rename(f"{EQUITY_TICKER}_minus_{BOND_TICKER}")
    return RebalancingData(
        close=frame, equity_returns=equity, bond_returns=bond, spread_returns=spread
    )


def build_target_positions(data: RebalancingData, spec: RebalancingSpec) -> pd.Series:
    """The DAILY target position for one spec, before the h-sleeve smoothing.

    Positive means long SPY / short IEF; negative the reverse. The position
    formed at the close of day t earns day t+1's spread return, which is
    exactly [HMM26] Eq. (1)'s Ret_{t+1} = f(Signal_t) timing and is what makes
    a look-ahead impossible here: the signal at t uses returns through t only.
    """
    definition = _DEFINITION_BY_KEY[spec.signal_key]
    use_sign = spec.sizing == "sign"
    if definition.position_builder is not None:
        return definition.position_builder(data.equity_returns, data.bond_returns, use_sign)
    assert definition.raw_builder is not None
    raw = definition.raw_builder(data.equity_returns, data.bond_returns)
    return _plain_position(raw, use_sign=use_sign)


def sleeve_smoothed_positions(targets: pd.Series, holding_days: int) -> pd.Series:
    """The h-SLEEVE OVERLAPPING BOOK: the held position is the equal-weighted
    mean of the last `holding_days` daily targets, i.e. h equal sleeves each
    formed on a different day and held h days.

    `min_periods=holding_days` is load-bearing: a partial average over 2 of 5
    sleeves is a different, larger book than the one declared, and allowing it
    would silently over-lever the first few days of the sample. At h=1 this
    reduces to the daily target exactly."""
    if holding_days < 1:
        raise ValueError(f"holding_days must be >= 1, got {holding_days}")
    if holding_days == 1:
        return targets
    return targets.rolling(holding_days, min_periods=holding_days).mean()


# --- backtest --------------------------------------------------------------


@dataclass
class RebalancingBacktestResult:
    spec_id: str
    status: str
    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    positions: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    spread_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    total_cost: float = 0.0
    total_financing_cost: float = 0.0
    total_turnover: float = 0.0
    n_position_changes: int = 0
    n_sign_flips: int = 0
    max_abs_position: float = 0.0
    first_trading_day: date | None = None
    last_trading_day: date | None = None


def run_rebalancing_backtest(
    data: RebalancingData, spec: RebalancingSpec, config: RebalancingConfig
) -> RebalancingBacktestResult:
    """One spec's walk-forward replay.

    THE TIMING CONTRACT: the position held over day t+1 is the one formed at
    the close of day t from a signal that uses returns through day t only.
    There is no path by which day t+1's return can influence the position that
    earned it. This is [HMM26] Eq. (1) traded rather than regressed.

    A day whose position is NaN -- the recursions' burn-in, or a day one leg
    did not trade -- contributes NO return at all rather than a forced zero.
    Zeros would not be neutral: they would shrink both the mean and the
    standard deviation of the return series and quietly report the Sharpe of
    "hold cash for a year, then trade" as if it were the Sharpe of the signal.
    That is vol_regime_timing.py's reasoning, adopted unchanged. It does NOT
    apply to the calendar_week4 specs' deliberate zeros, which are a real flat
    position and stay in the series.
    """
    targets = build_target_positions(data, spec)
    positions = sleeve_smoothed_positions(targets, spec.holding_days)

    index = data.close.index
    spread = data.spread_returns
    start_positions = np.flatnonzero(index.date >= config.formation_start)
    if len(start_positions) == 0:
        return RebalancingBacktestResult(spec_id=spec.spec_id, status="no_history_after_start")
    first = int(start_positions[0])

    pos = positions.to_numpy(dtype=float)
    spr = spread.to_numpy(dtype=float)
    borrow_daily_rate = config.short_borrow_bps_per_year / 1e4 / FINANCING_DAYS_PER_YEAR
    cost_rate = config.cost_bps / 1e4

    returns: dict[pd.Timestamp, float] = {}
    held: dict[pd.Timestamp, float] = {}
    previous = 0.0
    total_cost = 0.0
    total_financing = 0.0
    total_turnover = 0.0
    n_changes = 0
    n_flips = 0
    max_abs = 0.0

    for t in range(first, len(index) - 1):
        position = pos[t]
        if not np.isfinite(position):
            continue
        gross = position * spr[t + 1]
        if not np.isfinite(gross):
            continue

        turnover = abs(position - previous)
        # A unit position change trades 2.0 units of GROSS notional -- one
        # long leg and one short leg -- which is why the 2.0 is here and not
        # folded into cost_bps.
        cost = cost_rate * 2.0 * turnover
        elapsed_days = max((index[t + 1] - index[t]).days, 0)
        financing = borrow_daily_rate * abs(position) * elapsed_days

        returns[index[t + 1]] = gross - cost - financing
        held[index[t + 1]] = position
        total_cost += cost
        total_financing += financing
        total_turnover += turnover
        if turnover > 0.0:
            n_changes += 1
        if previous * position < 0.0:
            n_flips += 1
        max_abs = max(max_abs, abs(position))
        previous = position

    if not returns:
        return RebalancingBacktestResult(spec_id=spec.spec_id, status="no_realized_returns")

    daily = pd.Series(returns).sort_index()
    held_series = pd.Series(held).sort_index()
    return RebalancingBacktestResult(
        spec_id=spec.spec_id,
        status="ok",
        daily_returns=daily,
        positions=held_series,
        spread_returns=spread.reindex(daily.index),
        total_cost=total_cost,
        total_financing_cost=total_financing,
        total_turnover=total_turnover,
        n_position_changes=n_changes,
        n_sign_flips=n_flips,
        max_abs_position=max_abs,
        first_trading_day=daily.index[0].date(),
        last_trading_day=daily.index[-1].date(),
    )


# --- confound diagnostics --------------------------------------------------


def _sharpe_over(returns: pd.Series, start: date, end: date) -> float | None:
    mask = (returns.index.date >= start) & (returns.index.date <= end)
    window = returns[mask]
    if len(window) < MIN_REPLAY_TRADING_DAYS:
        return None
    return sharpe_ratio(window)


def _sharpe_excluding(returns: pd.Series, windows: tuple[tuple[date, date], ...]) -> float | None:
    keep = np.ones(len(returns), dtype=bool)
    dates = returns.index.date
    for start, end in windows:
        keep &= ~((dates >= start) & (dates <= end))
    window = returns[keep]
    if len(window) < MIN_REPLAY_TRADING_DAYS:
        return None
    return sharpe_ratio(window)


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


# When the beta-hedged stream's standard deviation falls to this fraction of
# the raw stream's, the hedge explained essentially all of it and
# residual_sharpe is reported as exactly 0.0 rather than as the Sharpe of
# floating-point dust. Same constant and same failure mode as
# vol_regime_timing.RESIDUAL_DEGENERACY_RATIO, which documents a replay where
# an unguarded hedged stream reported a confident +0.5497 with literally
# nothing left in it.
RESIDUAL_DEGENERACY_RATIO = 1e-8


@dataclass(frozen=True)
class RebalancingConfound:
    """Everything needed to decide whether a Sharpe here is real or is a
    disguised static exposure. Computed for EVERY spec, always."""

    spec_id: str
    mean_position: float
    mean_abs_position: float
    max_abs_position: float
    fraction_long: float
    fraction_flat: float
    spread_beta: float
    spread_alpha_annualized: float
    residual_sharpe: float
    buy_and_hold_spread_sharpe: float
    equity_beta: float
    bond_beta: float
    subperiod_sharpes: tuple[float, ...]
    sharpe_in_paper_window: float | None
    sharpe_after_paper_window: float | None
    sharpe_excluding_crises: float | None
    bootstrap_p_value: float | None
    annual_turnover: float


def compute_confound_diagnostics(
    spec: RebalancingSpec, replay: RebalancingBacktestResult, data: RebalancingData
) -> RebalancingConfound:
    """The in-module adversarial pass.

    residual_sharpe is the number that decides whether a spec is real: the
    Sharpe of the strategy's returns after removing its OLS exposure to the
    BUY-AND-HOLD SPY-minus-IEF spread, i.e. after taking away everything a
    constant, signal-free position in the same two instruments would have
    earned. It is the beta-hedged stream y - beta*x, NOT the OLS residual --
    see the module docstring's confound section for why that distinction is
    load-bearing rather than pedantic."""
    daily = replay.daily_returns
    spread = replay.spread_returns

    spread_beta, spread_alpha = _ols_beta_alpha(daily, spread)
    aligned = pd.concat([daily.rename("y"), spread.rename("x")], axis=1).dropna()
    if len(aligned) >= 3:
        hedged = aligned["y"] - spread_beta * aligned["x"]
        y_std = float(aligned["y"].std(ddof=1))
        hedged_std = float(hedged.std(ddof=1))
        fully_explained = y_std > 0 and hedged_std <= RESIDUAL_DEGENERACY_RATIO * y_std
        residual_sharpe = 0.0 if fully_explained else sharpe_ratio(hedged)
        bh_sharpe = sharpe_ratio(aligned["x"])
    else:
        residual_sharpe = 0.0
        bh_sharpe = 0.0

    equity_beta, _ = _ols_beta_alpha(daily, data.equity_returns.reindex(daily.index))
    bond_beta, _ = _ols_beta_alpha(daily, data.bond_returns.reindex(daily.index))

    pos = replay.positions
    n_years = max(len(daily) / TRADING_DAYS_PER_YEAR, 1e-9)

    return RebalancingConfound(
        spec_id=spec.spec_id,
        mean_position=float(pos.mean()) if len(pos) else 0.0,
        mean_abs_position=float(pos.abs().mean()) if len(pos) else 0.0,
        max_abs_position=replay.max_abs_position,
        fraction_long=float((pos > 0).mean()) if len(pos) else 0.0,
        fraction_flat=float((pos == 0).mean()) if len(pos) else 0.0,
        spread_beta=spread_beta,
        spread_alpha_annualized=spread_alpha * TRADING_DAYS_PER_YEAR,
        residual_sharpe=residual_sharpe,
        buy_and_hold_spread_sharpe=bh_sharpe,
        equity_beta=equity_beta,
        bond_beta=bond_beta,
        subperiod_sharpes=_subperiod_sharpes(daily),
        sharpe_in_paper_window=_sharpe_over(daily, PAPER_SAMPLE_START, PAPER_SAMPLE_END),
        sharpe_after_paper_window=_sharpe_over(
            daily, PAPER_SAMPLE_END + timedelta(days=1), date(2100, 1, 1)
        ),
        sharpe_excluding_crises=_sharpe_excluding(daily, CRISIS_WINDOWS),
        # Block length max(h, 5): at h=1 the position still changes only when
        # a slow-moving deviation signal does, so a one-day block would treat
        # a persistent book as 5,800 independent draws. 5 is one trading week
        # and matches the week4 gate's own unit.
        bootstrap_p_value=block_bootstrap_sharpe_pvalue(daily, max(spec.holding_days, 5)),
        annual_turnover=replay.total_turnover / n_years,
    )


# --- the paper's own predictive regressions (fidelity checks) --------------


def _hc0_regression(y: pd.Series, X: pd.DataFrame) -> tuple[dict[str, float], dict[str, float], float, int]:
    """OLS with White (1980) heteroskedasticity-consistent (HC0) standard
    errors, which is [HMM26]'s own convention throughout ("t-statistics are
    based on heteroskedasticity-consistent standard errors", Figure 2 and
    Table 1 captions).

    Uses statsmodels rather than a hand-rolled sandwich estimator, on
    CLAUDE.md's rule against implementing a published formula from memory: the
    HC0 covariance is White's, and a library implementation that is itself
    tested is strictly preferable to re-deriving it here."""
    import statsmodels.api as sm

    frame = pd.concat([y.rename("__y"), X], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 30:
        return {}, {}, float("nan"), len(frame)
    endog = frame["__y"]
    exog = sm.add_constant(frame.drop(columns="__y"), has_constant="add")
    fit = sm.OLS(endog, exog).fit(cov_type="HC0")
    return (
        {str(k): float(v) for k, v in fit.params.items()},
        {str(k): float(v) for k, v in fit.tvalues.items()},
        float(fit.rsquared),
        int(fit.nobs),
    )


@dataclass(frozen=True)
class DeltaSensitivityPoint:
    delta: float
    gamma1: float
    t_stat: float
    n_obs: int
    resets_per_year: float


def threshold_delta_sensitivity(
    data: RebalancingData,
    *,
    formation_start: date,
    deltas: tuple[float, ...] | None = None,
) -> list[DeltaSensitivityPoint]:
    """FIDELITY CHECK F1 -- reproduce [HMM26] Figure 2 on THIS project's own
    SPY/IEF data.

    Estimates Eq. (1), Ret_{t+1} = gamma0 + gamma1 * ThresholdSignal^delta_t +
    eps, with HC0 standard errors, for delta from 0% to 4% in 0.1% steps (the
    paper's own Figure 2 x-axis range).

    PAPER'S SHAPE, p.11-12 verbatim: "the Threshold signal is negatively
    related to subsequent daily S&P 500 returns in excess of the 10-year
    Treasury note... the signal's predictive power peaks around 2 percentage
    points and declines for values of delta above 2.5%."

    A DIAGNOSTIC, never a trial: nothing here may be used to pick a delta. The
    traded grid uses Eq. (2)'s inherited 0-2.5% average whatever this shows,
    which is the pre-registration's fixed reading (F1)."""
    grid = deltas if deltas is not None else tuple(round(i / 1000.0, 4) for i in range(41))
    mask = data.close.index.date >= formation_start
    target = data.spread_returns.shift(-1)
    n_years = max(int(mask.sum()) / TRADING_DAYS_PER_YEAR, 1e-9)

    points: list[DeltaSensitivityPoint] = []
    for delta in grid:
        signal = threshold_signal_series(
            data.equity_returns, data.bond_returns, delta, two_sided=True
        )
        params, tvalues, _, n_obs = _hc0_regression(
            target[mask], signal[mask].to_frame("threshold")
        )
        resets = threshold_reset_count(
            data.equity_returns[mask], data.bond_returns[mask], delta, two_sided=True
        )
        points.append(
            DeltaSensitivityPoint(
                delta=delta,
                gamma1=params.get("threshold", float("nan")),
                t_stat=tvalues.get("threshold", float("nan")),
                n_obs=n_obs,
                resets_per_year=resets / n_years,
            )
        )
    return points


@dataclass(frozen=True)
class MonthEndPoint:
    n_days: int
    beta1: float
    beta2: float
    t_stat_beta2: float
    n_obs: int


def calendar_month_end_sensitivity(
    data: RebalancingData, *, formation_start: date, max_days: int = 10
) -> list[MonthEndPoint]:
    """FIDELITY CHECK F2 -- reproduce [HMM26] Figure 3.

    Estimates Eq. (3),
        Ret_{t+1} = beta0 + beta1*Calendar_t + beta2*Calendar_t*Dummy^N_t
                    + beta3*Dummy^N_t + eps,
    with HC0 standard errors, for N = 1..max_days, and reports beta2's
    t-statistic at each N.

    PAPER'S SHAPE, p.13-14 verbatim: "Calendar predictability peaks in the
    last four days of the month... funds attempt to minimize market impact by
    avoiding trades on the very last day while spreading trades over several
    days." The curve is therefore expected to be NON-MONOTONIC, with N=1
    weaker than N=4. Reported as it comes out, not smoothed."""
    mask = data.close.index.date >= formation_start
    calendar = calendar_signal_series(data.equity_returns, data.bond_returns)
    target = data.spread_returns.shift(-1)

    points: list[MonthEndPoint] = []
    for n in range(1, max_days + 1):
        dummy = pd.Series(
            last_n_trading_days_mask(data.close.index, n).astype(float), index=data.close.index
        )
        design = pd.DataFrame(
            {
                "calendar": calendar,
                "calendar_x_dummy": calendar * dummy,
                "dummy": dummy,
            }
        )
        params, tvalues, _, n_obs = _hc0_regression(target[mask], design[mask])
        points.append(
            MonthEndPoint(
                n_days=n,
                beta1=params.get("calendar", float("nan")),
                beta2=params.get("calendar_x_dummy", float("nan")),
                t_stat_beta2=tvalues.get("calendar_x_dummy", float("nan")),
                n_obs=n_obs,
            )
        )
    return points


@dataclass(frozen=True)
class SignalDiagnostics:
    """FIDELITY CHECKS F3, F4, F5 -- the paper's own reported signal
    properties, measured on this project's own data."""

    threshold_mean: float
    threshold_std: float
    threshold_ar1: float
    threshold_skew: float
    calendar_mean: float
    calendar_std: float
    calendar_ar1: float
    calendar_skew: float
    threshold_calendar_correlation: float
    calendar_variant_correlation: float
    threshold_resets_per_year_median_delta: float
    threshold_resets_per_year_by_delta: dict[float, float]
    calendar_resets_per_year: float
    # Eq. (1) with the Eq. (2) averaged threshold signal.
    eq1_gamma1: float
    eq1_t_stat: float
    eq1_r_squared: float
    eq1_n_obs: int
    eq1_bps_per_one_sd: float
    # Eq. (3) at the paper's adopted week4 = 5 days.
    eq3_beta1: float
    eq3_beta2: float
    eq3_t_stat_beta2: float
    eq3_n_obs: int
    eq3_bps_per_one_sd_week4: float


def compute_signal_diagnostics(
    data: RebalancingData, *, formation_start: date
) -> SignalDiagnostics:
    """Everything [HMM26] states about its own signals, re-measured here so
    the fidelity comparison is a table of numbers rather than an assertion."""
    mask = data.close.index.date >= formation_start
    threshold = averaged_threshold_signal(data.equity_returns, data.bond_returns, two_sided=True)
    calendar = calendar_signal_series(data.equity_returns, data.bond_returns)
    calendar_alt = calendar_signal_series(
        data.equity_returns, data.bond_returns, reset_on_month_end_day=True
    )
    target = data.spread_returns.shift(-1)

    thr = threshold[mask].dropna()
    cal = calendar[mask].dropna()
    n_years = max(int(mask.sum()) / TRADING_DAYS_PER_YEAR, 1e-9)

    resets_by_delta = {
        d: threshold_reset_count(
            data.equity_returns[mask], data.bond_returns[mask], d, two_sided=True
        )
        / n_years
        for d in DELTA_GRID
    }
    median_delta = DELTA_GRID[len(DELTA_GRID) // 2]

    calendar_resets = int(month_end_flags(data.close.index)[mask].sum()) / n_years

    params1, t1, r2_1, n1 = _hc0_regression(target[mask], threshold[mask].to_frame("threshold"))
    gamma1 = params1.get("threshold", float("nan"))

    dummy = pd.Series(
        last_n_trading_days_mask(data.close.index, WEEK4_TRADING_DAYS).astype(float),
        index=data.close.index,
    )
    design3 = pd.DataFrame(
        {"calendar": calendar, "calendar_x_week4": calendar * dummy, "week4": dummy}
    )
    params3, t3, _, n3 = _hc0_regression(target[mask], design3[mask])
    beta1 = params3.get("calendar", float("nan"))
    beta2 = params3.get("calendar_x_week4", float("nan"))

    thr_sd = float(thr.std(ddof=1)) if len(thr) > 1 else float("nan")
    cal_sd = float(cal.std(ddof=1)) if len(cal) > 1 else float("nan")

    return SignalDiagnostics(
        threshold_mean=float(thr.mean()) if len(thr) else float("nan"),
        threshold_std=thr_sd,
        threshold_ar1=float(thr.autocorr(1)) if len(thr) > 2 else float("nan"),
        threshold_skew=float(thr.skew()) if len(thr) > 3 else float("nan"),
        calendar_mean=float(cal.mean()) if len(cal) else float("nan"),
        calendar_std=cal_sd,
        calendar_ar1=float(cal.autocorr(1)) if len(cal) > 2 else float("nan"),
        calendar_skew=float(cal.skew()) if len(cal) > 3 else float("nan"),
        threshold_calendar_correlation=float(threshold[mask].corr(calendar[mask])),
        calendar_variant_correlation=float(calendar[mask].corr(calendar_alt[mask])),
        threshold_resets_per_year_median_delta=resets_by_delta[median_delta],
        threshold_resets_per_year_by_delta=resets_by_delta,
        calendar_resets_per_year=calendar_resets,
        eq1_gamma1=gamma1,
        eq1_t_stat=t1.get("threshold", float("nan")),
        eq1_r_squared=r2_1,
        eq1_n_obs=n1,
        # The paper's own normalization (p.18): the effect on next-day return
        # of a ONE-STANDARD-DEVIATION move in the signal, in basis points.
        eq1_bps_per_one_sd=gamma1 * thr_sd * 1e4,
        eq3_beta1=beta1,
        eq3_beta2=beta2,
        eq3_t_stat_beta2=t3.get("calendar_x_week4", float("nan")),
        eq3_n_obs=n3,
        eq3_bps_per_one_sd_week4=(beta1 + beta2) * cal_sd * 1e4,
    )


@dataclass(frozen=True)
class ReversalDecomposition:
    """POST-HOC, EXPLICITLY NOT PRE-REGISTERED, AND PURELY ADVERSARIAL.

    Added after the F1 sweep came back with the WRONG SHAPE: on this project's
    SPY/IEF data the Eq. (1) t-statistic is most negative at delta = 0 and
    decays as delta rises, rather than peaking near 2% as [HMM26] Figure 2
    reports. At delta = 0 the band |w - 60%| >= 0 fires every day, so
    Threshold Signal^0_t is (to the recursion's second order) just
    0.24 * yesterday's SPY-minus-IEF return -- i.e. ONE-DAY CROSS-ASSET
    REVERSAL, with no rebalancing content whatever.

    This runs the one regression that separates the two readings: Ret_{t+1} on
    the Eq. (2) AVERAGED Threshold signal and on Threshold Signal^0 jointly.
    If the averaged signal's coefficient survives, the multi-band rebalancing
    structure carries information beyond one-day reversal. If it collapses,
    the family measured one-day reversal wearing a rebalancing costume.

    IT IS DECLARED POST-HOC BECAUSE IT IS. It adds no spec, changes no
    verdict input, and can only make this family look WORSE -- the standing
    exception this project allows for adversarial checks. It is the obvious
    content of a FUTURE pre-declared round, not a revision of this one; the
    traded grid stays exactly as pre-registered whatever this shows.
    """

    n_obs: int
    # Univariate, for reference.
    averaged_alone_coef: float
    averaged_alone_t: float
    delta0_alone_coef: float
    delta0_alone_t: float
    # Joint. THE decisive pair.
    averaged_joint_coef: float
    averaged_joint_t: float
    delta0_joint_coef: float
    delta0_joint_t: float
    joint_r_squared: float
    correlation_averaged_delta0: float


def post_hoc_reversal_decomposition(
    data: RebalancingData, *, formation_start: date
) -> ReversalDecomposition:
    """See ReversalDecomposition. Post-hoc, adversarial, verdict-neutral."""
    mask = data.close.index.date >= formation_start
    averaged = averaged_threshold_signal(data.equity_returns, data.bond_returns, two_sided=True)
    delta0 = threshold_signal_series(
        data.equity_returns, data.bond_returns, 0.0, two_sided=True
    )
    target = data.spread_returns.shift(-1)

    p_a, t_a, _, _ = _hc0_regression(target[mask], averaged[mask].to_frame("averaged"))
    p_0, t_0, _, _ = _hc0_regression(target[mask], delta0[mask].to_frame("delta0"))
    joint = pd.DataFrame({"averaged": averaged, "delta0": delta0})
    p_j, t_j, r2_j, n_j = _hc0_regression(target[mask], joint[mask])

    return ReversalDecomposition(
        n_obs=n_j,
        averaged_alone_coef=p_a.get("averaged", float("nan")),
        averaged_alone_t=t_a.get("averaged", float("nan")),
        delta0_alone_coef=p_0.get("delta0", float("nan")),
        delta0_alone_t=t_0.get("delta0", float("nan")),
        averaged_joint_coef=p_j.get("averaged", float("nan")),
        averaged_joint_t=t_j.get("averaged", float("nan")),
        delta0_joint_coef=p_j.get("delta0", float("nan")),
        delta0_joint_t=t_j.get("delta0", float("nan")),
        joint_r_squared=r2_j,
        correlation_averaged_delta0=float(averaged[mask].corr(delta0[mask])),
    )


# --- screening -------------------------------------------------------------


def policy_d_denominators(n_local: int = REBALANCING_N_TRIALS) -> list[int]:
    """The N values a Policy D report must cover, ascending and deduplicated:
    dsr_n_trials(n_local) plus the pooled rungs from dsr_policy_n.json
    (n_mechanisms, n_effective, n_raw).

    Same derivation and same artifact as
    cross_sectional_tax_loss_selling.policy_d_denominators. The lowest tier is
    dsr_n_trials(n_local), NOT n_local itself, because that is the denominator
    the screen actually deflates at."""
    # The pooled rungs come from dsr_policy_n.json, the project's explicit
    # DENOMINATOR LADDER, not from global_effective_n.json's provenance fields.
    # Until 2026-09-06 this returned {n_local, 481, 857}, where 481 was
    # `n_specs_clustered` ("how many specs happened to carry a usable return
    # series") and 857 was that run's raw population count -- two bookkeeping
    # numbers on a MEASUREMENT artifact that were never chosen as denominators.
    # See dsr_policy_n.py for the four rungs and what each one is measured from.
    #
    # dsr_n_trials() is still applied to n_local first, so the family's own grid
    # remains the floor and this ladder can only ever GROW the denominator.
    from app.services.research_lab.dsr_policy_n import dsr_policy_denominators

    return dsr_policy_denominators(dsr_n_trials(int(n_local)))


def dsr_across_denominators(
    sharpe_annualized: float,
    returns: pd.Series,
    sigma_sr_annualized: float | None,
    denominators: list[int],
) -> dict[int, float | None]:
    """DSR at each N. None means the machinery could not produce one there
    (below deflated_sharpe.MIN_TRIALS_FOR_DSR, or a degenerate series) and is
    treated downstream as NOT clearing the bar -- an unmeasurable deflation is
    not a passing one."""
    return {
        int(n): compute_deflated_sharpe(
            sharpe_annualized,
            returns,
            int(n),
            sigma_sr_annualized,
            periods_per_year=TRADING_DAYS_PER_YEAR,
        ).dsr
        for n in denominators
    }


@dataclass
class RebalancingScreeningResult:
    """One spec's full Policy D record. preservation_score lives HERE rather
    than in an optional later pass on purpose -- this project has twice
    shipped a check and then skipped it for the next real decision, and a
    metric applied when someone remembers is a decoration, not a check."""

    spec_id: str
    signal_key: str
    sizing: str
    holding_days: int
    citation: str
    hypothesis: str
    is_control: bool
    cost_arm: str
    n_trading_days: int
    first_trading_day: date | None
    last_trading_day: date | None
    sharpe_annualized: float
    dsr_by_n: dict[int, float | None]
    preservation: dict[str, float | int | bool | None]
    net_cumulative_return: float
    total_cost_drag: float
    total_financing_drag: float
    total_turnover: float
    annual_turnover: float
    n_position_changes: int
    n_sign_flips: int
    deflated_sharpe: object  # DeflatedSharpeResult at n_local -- for persistence
    confound: RebalancingConfound


def screen_rebalancing_pressure(
    data: RebalancingData,
    specs: list[RebalancingSpec],
    config: RebalancingConfig,
    *,
    denominators: list[int] | None = None,
    cost_arm: str = BASELINE_COST_ARM,
) -> list[RebalancingScreeningResult]:
    """One Sharpe per spec, DSR-corrected at every pre-declared denominator.

    Trial counting follows cross_sectional.screen_cross_sectional_universe,
    intraday_patterns.screen_pattern_universe and
    vol_regime_timing.screen_vol_regime_timing exactly and for the same
    documented reason: each spec IS already a single portfolio, so no
    uncorrected "which ticker" search dimension exists and "which definition"
    is the one search dimension. n_trials is fixed at len(specs) -- the
    family's literal pre-declared size -- raised to the project-wide
    effectively-independent count by dsr_n_trials whenever that is larger, and
    NEVER shrunk to however many specs survived the data floors.

    sigma_sr is the ddof=1 standard deviation of every sibling spec's Sharpe
    from this same pass."""
    denominators = denominators if denominators is not None else policy_d_denominators(len(specs))
    n_local = dsr_n_trials(len(specs)) if specs else 0

    replays: dict[str, RebalancingBacktestResult] = {}
    for spec in specs:
        replay = run_rebalancing_backtest(data, spec, config)
        if replay.status != "ok":
            logger.info("rebalancing spec %s not replayed: %s", spec.spec_id, replay.status)
            continue
        if len(replay.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            logger.info(
                "rebalancing spec %s dropped: only %d realized days (floor %d)",
                spec.spec_id,
                len(replay.daily_returns),
                MIN_REPLAY_TRADING_DAYS,
            )
            continue
        replays[spec.spec_id] = replay

    sharpes = {sid: sharpe_ratio(r.daily_returns) for sid, r in replays.items()}
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {s.spec_id: s for s in specs}
    results: list[RebalancingScreeningResult] = []
    for spec_id, replay in replays.items():
        spec = spec_by_id[spec_id]
        daily = replay.daily_returns
        sharpe = sharpes[spec_id]
        dsr_by_n = dsr_across_denominators(sharpe, daily, sigma_sr, denominators)
        deflated_local = compute_deflated_sharpe(
            sharpe, daily, n_local, sigma_sr, periods_per_year=TRADING_DAYS_PER_YEAR
        )
        preservation = compute_preservation_metrics(daily, dsr=dsr_by_n.get(n_local)).as_dict()
        confound = compute_confound_diagnostics(spec, replay, data)
        results.append(
            RebalancingScreeningResult(
                spec_id=spec_id,
                signal_key=spec.signal_key,
                sizing=spec.sizing,
                holding_days=spec.holding_days,
                citation=spec.citation,
                hypothesis=spec.hypothesis,
                is_control=spec.is_control,
                cost_arm=cost_arm,
                n_trading_days=len(daily),
                first_trading_day=replay.first_trading_day,
                last_trading_day=replay.last_trading_day,
                sharpe_annualized=sharpe,
                dsr_by_n=dsr_by_n,
                preservation=preservation,
                net_cumulative_return=float(daily.sum()),
                total_cost_drag=replay.total_cost,
                total_financing_drag=replay.total_financing_cost,
                total_turnover=replay.total_turnover,
                annual_turnover=confound.annual_turnover,
                n_position_changes=replay.n_position_changes,
                n_sign_flips=replay.n_sign_flips,
                deflated_sharpe=deflated_local,
                confound=confound,
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results


# --- summary ---------------------------------------------------------------


@dataclass
class RebalancingScreeningSummary:
    n_trials: int = REBALANCING_N_TRIALS
    denominators: list[int] = field(default_factory=list)
    results_by_cost_arm: dict[str, list[RebalancingScreeningResult]] = field(default_factory=dict)
    signal_diagnostics: SignalDiagnostics | None = None
    delta_sensitivity: list[DeltaSensitivityPoint] = field(default_factory=list)
    month_end_sensitivity: list[MonthEndPoint] = field(default_factory=list)
    reversal_decomposition: ReversalDecomposition | None = None
    sigma_sr_by_cost_arm: dict[str, float | None] = field(default_factory=dict)
    missing_tickers: list[str] = field(default_factory=list)
    ticker_starts: dict[str, date] = field(default_factory=dict)
    formation_start: date | None = None
    window_end: date | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def baseline_results(self) -> list[RebalancingScreeningResult]:
        return self.results_by_cost_arm.get(BASELINE_COST_ARM, [])

    def verdict(self, threshold: float = VALIDATED_EDGE_BAR) -> tuple[str, str | None]:
        """Policy D's two-tier verdict, read off the BASELINE cost arm's best
        spec by DSR at n_local -- exactly the rule the pre-registration fixed
        (section 9) before any number existed."""
        results = self.baseline_results
        if not results:
            return "definite_negative", None
        # The denominator the screen actually deflated at -- max(family grid
        # size, project-wide effective N) -- which is also the LOWEST rung of
        # the Policy D ladder, hence the most lenient tier.
        n_local = dsr_n_trials(self.n_trials)
        best = max(
            results,
            key=lambda r: (r.dsr_by_n.get(n_local) if r.dsr_by_n.get(n_local) is not None else -1.0),
        )
        return (
            policy_d_verdict(dsr_by_n=best.dsr_by_n, threshold=threshold, n_local=n_local),
            best.spec_id,
        )


def build_rebalancing_disclosure(
    summary: RebalancingScreeningSummary, config: RebalancingConfig
) -> list[str]:
    """Plain-language caveats that must travel with any number from this
    family, including the breakeven-cost arithmetic that says how wrong the
    cost assumption would have to be to matter."""
    lines = [
        (
            f"SOURCE IS A WORKING PAPER, NOT A PEER-REVIEWED ARTICLE: {REBALANCING_CITATION}"
        ),
        (
            f"n_trials = {REBALANCING_N_TRIALS} ({len(_SIGNAL_DEFINITIONS)} signals x "
            f"{len(REBALANCING_SIZINGS)} sizings x {len(REBALANCING_HOLDING_DAYS)} holding "
            "periods), fixed in the pre-registration before any return was computed, and "
            "raised to the project-wide effectively-independent count by dsr_n_trials whenever "
            "that is larger. It does NOT cover the choice to read this particular paper."
        ),
        (
            f"Direction was pre-declared uniformly at {REBALANCING_DIRECTION:+.0f} "
            "('equity overweight -> sell equity, buy bonds', [HMM26] p.10) and never fitted "
            "per spec; negative Sharpes are reported as they came out, not flipped."
        ),
        (
            "INSTRUMENT DEVIATION: [HMM26] uses S&P 500 and 10-YEAR TREASURY NOTE FUTURES. "
            "This build uses SPY and IEF because no free roll-adjusted futures series exists "
            "here (paid-data gap P4). The financing leg largely cancels in a spread and the "
            "expense-ratio difference is a constant the intercept absorbs, but the duration "
            "mismatch and tracking error are real and unquantified."
        ),
        (
            "WINDOW DEVIATION: 2003-08-01..2026-09-04 against the paper's "
            "1997-09-10..2023-03-17. The lost years are the ones the paper itself calls weak; "
            "the gained ~3.5 years are genuinely out of sample for it and are reported "
            "separately."
        ),
        (
            "NO MULTIVARIATE CONTROLS. The regressions reported here are the paper's UNIVARIATE "
            "Eq. (1) and Eq. (3); no Table 1 coefficient is claimed to be replicated."
        ),
        (
            f"Costs: {config.cost_bps:.1f}bp one-way per unit gross notional traded (a unit "
            f"position change trades 2.0 gross, so ~{2 * config.cost_bps:.0f}bp per unit swing), "
            f"plus {config.short_borrow_bps_per_year:.0f}bp/yr general-collateral borrow on the "
            "short notional, accrued on calendar days. The borrow rate is SOURCED "
            "(Beneish/Lee/Nichols 2015 p.15); the turnover rate is a disclosed assumption."
        ),
        (
            "Formation is assumed executable at the exact closing print, and the two ETFs were "
            "chosen today from instruments that still exist and are still liquid. Both are "
            "small hindsight channels here, and neither is zero."
        ),
    ]

    results = summary.baseline_results
    if not results:
        lines.append("No spec produced a replayable return series -- nothing to interpret.")
        return lines

    best = results[0]
    lines.append(
        f"Best raw Sharpe (baseline costs): {best.spec_id} at {best.sharpe_annualized:+.4f} over "
        f"{best.n_trading_days} trading days."
    )
    charges = best.total_cost_drag + best.total_financing_drag
    if charges > 0:
        multiple = (best.net_cumulative_return + charges) / charges
        if multiple <= 1.0:
            lines.append(
                f"  Breakeven cost multiple {multiple:.2f}x -- at or below 1.0, meaning "
                f"{best.spec_id} was already unprofitable BEFORE costs. No cost assumption "
                "rescues it."
            )
        else:
            lines.append(
                f"  Breakeven cost multiple {multiple:.2f}x -- costs would have to be "
                f"{multiple:.2f} times the assumed {config.cost_bps:.1f}bp / "
                f"{config.short_borrow_bps_per_year:.0f}bp-per-year to erase its net return."
            )

    # SIGNED, deliberately not abs(): the question is whether a POSITIVE
    # Sharpe survived hedging out the static exposure. abs() would let the
    # degenerate case through, where a near-constant position leaves only the
    # near-deterministic cost drag whose Sharpe is a large negative number.
    tilts = [
        r
        for r in results
        if r.sharpe_annualized > 0 and r.confound.residual_sharpe < 0.5 * r.sharpe_annualized
    ]
    if tilts:
        lines.append(
            f"{len(tilts)} spec(s) with a positive raw Sharpe lose more than half of it once "
            "their static exposure to the buy-and-hold SPY-minus-IEF spread is regressed out "
            "-- those are disguised static tilts, not timing signals."
        )

    control = [r for r in results if r.is_control]
    non_control = [r for r in results if not r.is_control]
    if control and non_control:
        best_control = max(control, key=lambda r: r.sharpe_annualized)
        best_real = max(non_control, key=lambda r: r.sharpe_annualized)
        lines.append(
            f"CONTROL COMPARISON (pre-declared reading): best control spec "
            f"{best_control.spec_id} Sharpe {best_control.sharpe_annualized:+.4f} vs best "
            f"rebalancing spec {best_real.spec_id} Sharpe {best_real.sharpe_annualized:+.4f}. "
            + (
                "The control MATCHES OR BEATS the rebalancing signals: this family measured "
                "21-day cross-asset reversal, not rebalancing pressure."
                if best_control.sharpe_annualized >= best_real.sharpe_annualized
                else "The rebalancing signals beat the plain trailing-window control."
            )
        )
    return lines


# --- production entry point ------------------------------------------------


def run_rebalancing_screening(
    start: date = REBALANCING_FORMATION_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    config: RebalancingConfig | None = None,
    specs: list[RebalancingSpec] | None = None,
) -> RebalancingScreeningSummary:
    """THE production entry point, scoped to exactly REBALANCING_FAMILY's 24
    definitions and their own n_trials.

    `start` is the first FORMATION date; price history is padded before it by
    REBALANCING_HISTORY_PADDING_CALENDAR_DAYS so the path-dependent recursions
    are warm, and formations never occur in the padding."""
    end = end if end is not None else date.today()  # noqa: DTZ011
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else default_rebalancing_config()
    config.formation_start = start
    specs = specs if specs is not None else REBALANCING_FAMILY

    padded_start = start - timedelta(days=REBALANCING_HISTORY_PADDING_CALENDAR_DAYS)
    close, missing = provider.get_price_history(list(TRADED_UNIVERSE), padded_start, end)

    summary = RebalancingScreeningSummary(
        n_trials=len(specs), missing_tickers=missing, formation_start=start
    )
    if close.empty or missing:
        summary.warnings.append(
            f"price panel unusable: empty={close.empty}, missing={missing}. Nothing replayed."
        )
        return summary

    starts: dict[str, date] = {}
    for ticker in close.columns:
        series = close[ticker].dropna()
        if series.empty:
            continue
        observed = series.index[0].date()
        starts[str(ticker)] = observed
        expected = VERIFIED_TICKER_START.get(str(ticker))
        if expected is not None and observed > max(expected, padded_start) + timedelta(days=7):
            summary.warnings.append(
                f"{ticker} history starts {observed}, later than the verified inception "
                f"{expected} -- the vendor may have truncated this series."
            )
    summary.ticker_starts = starts

    data = align_rebalancing_data(close)
    summary.window_end = data.close.index[-1].date()

    n_burn_in = int((data.close.index.date < start).sum())
    if n_burn_in < REBALANCING_BURN_IN_TRADING_DAYS:
        summary.warnings.append(
            f"only {n_burn_in} trading days of burn-in before {start} (declared floor "
            f"{REBALANCING_BURN_IN_TRADING_DAYS}); the path-dependent recursions may still "
            "carry their initial condition."
        )

    denominators = policy_d_denominators(len(specs))
    summary.denominators = denominators

    for arm in COST_ARMS:
        arm_config = RebalancingConfig(
            cost_bps=arm.cost_bps,
            short_borrow_bps_per_year=arm.short_borrow_bps_per_year,
            formation_start=start,
        )
        arm_results = screen_rebalancing_pressure(
            data, specs, arm_config, denominators=denominators, cost_arm=arm.key
        )
        summary.results_by_cost_arm[arm.key] = arm_results
        sharpes = [r.sharpe_annualized for r in arm_results]
        summary.sigma_sr_by_cost_arm[arm.key] = (
            float(np.std(sharpes, ddof=1)) if len(sharpes) >= 2 else None
        )

    summary.signal_diagnostics = compute_signal_diagnostics(data, formation_start=start)
    summary.delta_sensitivity = threshold_delta_sensitivity(data, formation_start=start)
    summary.month_end_sensitivity = calendar_month_end_sensitivity(data, formation_start=start)
    summary.reversal_decomposition = post_hoc_reversal_decomposition(data, formation_start=start)
    return summary


__all__ = [
    "BASELINE_COST_ARM",
    "CONTROL_WINDOW_DAYS",
    "COST_ARMS",
    "CRISIS_WINDOWS",
    "DELTA_GRID",
    "MONTH_START_REVERSAL_LAG",
    "PAPER_SAMPLE_END",
    "PAPER_SAMPLE_START",
    "REBALANCING_CITATION",
    "REBALANCING_COST_BPS",
    "REBALANCING_DIRECTION",
    "REBALANCING_FAMILY",
    "REBALANCING_FORMATION_START",
    "REBALANCING_HOLDING_DAYS",
    "REBALANCING_N_TRIALS",
    "REBALANCING_SHORT_BORROW_BPS_PER_YEAR",
    "REBALANCING_SIZINGS",
    "SCREENING_FLOOR",
    "SIGNAL_RESCALE",
    "TARGET_EQUITY_WEIGHT",
    "TRADED_UNIVERSE",
    "VALIDATED_EDGE_BAR",
    "WEEK4_TRADING_DAYS",
    "CostArm",
    "DeltaSensitivityPoint",
    "MonthEndPoint",
    "RebalancingBacktestResult",
    "RebalancingConfig",
    "RebalancingConfound",
    "RebalancingData",
    "RebalancingScreeningResult",
    "RebalancingScreeningSummary",
    "RebalancingSpec",
    "ReversalDecomposition",
    "SignalDiagnostics",
    "align_rebalancing_data",
    "averaged_threshold_signal",
    "build_rebalancing_disclosure",
    "build_target_positions",
    "calendar_month_end_sensitivity",
    "calendar_signal_series",
    "compute_confound_diagnostics",
    "compute_signal_diagnostics",
    "default_rebalancing_config",
    "dsr_across_denominators",
    "last_n_trading_days_mask",
    "month_end_flags",
    "policy_d_denominators",
    "post_hoc_reversal_decomposition",
    "rebalanced_weight",
    "run_rebalancing_backtest",
    "run_rebalancing_screening",
    "screen_rebalancing_pressure",
    "sleeve_smoothed_positions",
    "threshold_delta_sensitivity",
    "threshold_reset_count",
    "threshold_signal_series",
    "trailing_window_signal",
    "week4_modified_calendar_position",
]
