"""TAX-LOSS SELLING / TURN-OF-THE-YEAR — a cross-sectional equity family
expressed against cross_sectional.py's harness.

The grid, the denominator, the cost model, the fidelity checks and the
pass/fail rule are fixed by
data/research_runs/tax_loss_selling_PREREGISTRATION.txt, committed BEFORE
this module screened anything. Nothing here may quietly differ from it; a
difference is a diff, not a decision.

Needs ONLY daily price history — no filings, no fundamentals, no vendor
feed. That is why this family is cheap enough to run at all; it is not a
claim that it is more likely to work than the ones that were not.


====================================================================
1. SOURCES, AND EXACTLY WHAT WAS OBTAINED OF EACH
====================================================================
[PW01] Poterba, James M. & Weisbenner, Scott J., "Capital Gains Tax Rules,
       Tax-loss Trading, and Turn-of-the-year Returns", THE JOURNAL OF
       FINANCE, Vol. LVI, No. 1, February 2001, pp. 353-368.
       OBTAINED IN FULL AND READ IN FULL (2026-09-06). The published
       article PDF was fetched from the second author's own university
       posting, scottweisbenner.web.illinois.edu/RESEARCH/PAPERS/
       JF_JanuaryEffect_Feb2001_353-368.pdf, and text-extracted with
       `pdftotext -layout` (800 lines, Tables I-V intact). Every equation,
       window, coefficient and definition quoted below is read off that
       text, never reconstructed from memory. NBER WP 6616 was tried first
       and is a SCANNED IMAGE PDF with no text layer; it was discarded
       rather than guessed at.
       THIS IS THE MECHANISM-FIDELITY PAPER for this family.

[RK76] Rozeff, Michael S. & Kinney, William R., "Capital market
       seasonality: The case of stock returns", JOURNAL OF FINANCIAL
       ECONOMICS 3(4), 1976, pp. 379-402.
       ABSTRACT-LEVEL ONLY — FULL TEXT NOT OBTAINED (ScienceDirect and
       Semantic Scholar both 403 to automated fetch; RePEc confirms the
       volume/issue/pages/year and says "No abstract is available for this
       item"). NO NUMBER OR METHOD FROM [RK76] IS USED IN ANY CONSTRUCTION
       HERE. Its only role is to establish that the January anomaly is a
       fifty-year-old, thoroughly public finding, which lowers the prior.
       The widely-repeated "3.48% January vs 0.42%" figure is NOT treated
       as verified and appears nowhere in this module.

[SK14] Sikes, Stephanie A., "The turn-of-the-year effect and
       tax-loss-selling by institutional investors", JOURNAL OF ACCOUNTING
       AND ECONOMICS 57(1), 2014, pp. 22-42.
       ABSTRACT-LEVEL ONLY — FULL TEXT NOT OBTAINED (ScienceDirect 403,
       SSRN 403). NO METHODOLOGY FROM [SK14] IS IMPLEMENTED. Cited for two
       qualitative claims that are inside its abstract: the effect is a
       SMALL-CAPITALIZATION, EARLY-JANUARY phenomenon, and taxable
       INSTITUTIONS (not only individuals) do the selling. The "47bp per
       percentage point of Q4 realized losses" figure that circulates in
       secondary summaries is NOT quoted, used or relied on anywhere.


====================================================================
2. THE MECHANISM, AND THE CONSTRUCTION IT DICTATES
====================================================================
A taxable holder of a stock with an accrued capital LOSS can accelerate the
tax benefit by realizing before 31 December rather than after. That is
non-informational selling pressure late in the calendar year, concentrated
in the largest accrued losses, and a price recovery once it abates.

2.1 THE ANCHOR. [PW01] p.358, verbatim: "We define turn-of-the-year returns
following Roll (1983), Sims (1995), and others as the dividend-inclusive
return on the last trading day in December and the first five days in
January."

Writing d(-1) for the LAST trading day of December and d(-2) for the one
before it: the harness forms at a date's CLOSE and realizes from the next
day, so capturing the return ON d(-1) requires forming at the close of
d(-2). Independently corroborated by [PW01]'s own control variable, p.359
verbatim: "PRICE is the stock's closing price on the second to last trading
day in December" — the paper measures its cross-section on exactly that
date. Hence TAX_LOSS_FORMATION_OFFSET = 2 (see that constant) and a 6-day
hold covering d(-1) plus the first five January sessions.

2.2 THE RANKING VARIABLE. [PW01] p.357-358, verbatim: "Our primary
explanatory variable is LOSS, which measures the tax-loss potential of a
stock. It is defined as the percentage difference between a stock's price at
the beginning of a time period (say July 1) and its price at the end of the
period." Equations (1a)/(1b), verbatim:

        LOSS_July-Dec = (P_Dec24 / P_July1 - 1)                       (1a)
        LOSS_Jan-June = (P_June30 / P_Jan1 - 1)                       (1b)

and immediately after: "LOSS_July-Dec excludes returns on the last five
trading days of December, on the grounds that these returns may already
reflect some of the turn-of-the-year returns. We set LOSS equal to zero if
the firm experienced a capital gain."

So any window running into December ENDS at d(-6) — the last December
session that is not one of "the last five trading days of December" — which
puts a FOUR-TRADING-DAY GAP between the last price the signal reads and the
formation close. That gap is [PW01]'s own exclusion and is strictly
conservative about look-ahead (see TAX_LOSS_SIGNAL_END_OFFSET).

2.3 THE PRICE BASIS — DIVIDEND-UNADJUSTED, ON PURPOSE. [PW01]'s LOSS is
defined on PRICE, and a capital loss for US tax purposes IS a price-basis
quantity: dividends are taxed as income in the year received and are not
part of the accrued gain or loss. The signal is therefore built from
CrossSectionalData.price_only_close (split-adjusted, dividend-UNadjusted).
Realized returns still come off the harness's total-return `close`, exactly
as in every other family here — which also matches [PW01], whose
turn-of-the-year RETURN is explicitly "dividend-inclusive" while its LOSS is
not. The rank correlation between the two bases is REPORTED as a diagnostic
(price_vs_total_return_spearman) so a reader can see whether the choice
moved anything; it is not a second searched arm.

2.4 THE TWO SIGNAL FORMS, AND WHY THE ASYMMETRY IS THE POINT.
[PW01] Table III, all six columns (three tax regimes x with/without firm
effects), read off the extracted text:

    LOSS_Jan-June   -0.084 -0.102 -0.053 -0.057 -0.068 -0.069
    LOSS_July-Dec   -0.143 -0.167 -0.151 -0.178 -0.086 -0.118
    GAIN_Jan-June   -0.016 -0.006 -0.001 +0.003 +0.003 +0.008
    GAIN_July-Dec   -0.017 -0.013 -0.002 -0.011 -0.017 -0.015

and p.360 verbatim: "Losses in the previous year predict higher
turn-of-the-year returns in each of the three regimes... The absolute effect
of GAIN is much smaller than the effect of LOSS, and we often fail to reject
the null hypothesis that the coefficients on the GAIN variables are zero."

The estimated effect is ASYMMETRIC AT ZERO. So:

  "lossonly"  s = max(-R, 0)  — [PW01]'s truncated LOSS verbatim ("We set
              LOSS equal to zero if the firm experienced a capital gain"),
              traded LONG the top decile against the equal-weighted eligible
              universe ("long_universe_hedged"). There is deliberately NO
              short-the-winners leg, because [PW01] estimates no winner
              effect to short.
  "signed"    s = -R — the plain reversal ranking, traded long_short
              (biggest losers vs biggest winners). This is what a generic
              "losers bounce" story predicts and what the tax mechanism does
              NOT predict.

PRE-DECLARED READING (pre-registration section 3.4): if "signed" beats
"lossonly" materially and consistently, this family measured cross-sectional
reversal wearing a calendar, and the report says so regardless of the DSR.


====================================================================
3. THE MATCHED CALENDAR PLACEBO
====================================================================
tls_jun_placebo_* uses the SAME RANKING VARIABLE as tls_dec_jan_jun_* — the
accrued price change from the last close of year Y-1 to the sixth-to-last
trading day of a month — and differs in ONE thing only: the month it is
traded at. Late June has no tax deadline; late December does.

That is a matched pair, not a loose control. Anything that works in December
and not in June is about the calendar boundary. Anything that works in both
is generic mean reversion and is not this mechanism. This is the same
discipline cross_sectional_seasonality.py's other-month placebo applies, and
in that family the placebo BEAT every real spec — which is exactly the
outcome a family without a placebo would have mistaken for a finding.


====================================================================
4. HOW THIS DIFFERS FROM cross_sectional_seasonality.py
====================================================================
That family (Keloharju, Linnainmaa & Nyberg 2016, screened 2026-08-28,
honest negative) ranks on a stock's OWN average return in the SAME CALENDAR
MONTH over the prior 5/10/20 years, reforming twelve times a year. This one
ranks on the ACCRUED CAPITAL LOSS IN THE CURRENT YEAR and forms ONCE, on one
pre-specified December date, sitting flat the other ~246 sessions. Different
ranking variable, different calendar structure, different mechanism — KLN's
own abstract disclaims a distinct mechanism, while this one has a named
institutional fact (the US tax year ends 31 December) behind it.

Overlap that DOES exist, disclosed rather than denied: both are calendar
stories on the same universe and price data, and a December-anchored loser
portfolio is mechanically correlated with the long-horizon reversal this
project also already tested (cross_sectional_patterns_d2.py). The pooled DSR
denominator is what prices that; no independence from prior families is
claimed.


====================================================================
5. THE ONE REAL HARNESS DEVIATION, DECLARED IN THE PRE-REGISTRATION
====================================================================
cross_sectional.py forms every `holding_days` TRADING days. This family must
form on ONE specific CALENDAR date a year. It therefore sets
cohort_formation_days=1, which makes the harness run `holding_days`
independent staggered sleeves, so every trading day is a formation date in
exactly one sleeve and the December anchor is always hit. The signal panel is
NaN on every non-anchor date, so the other sleeves form nothing and stay flat.

CONSEQUENCE, declared in advance (pre-registration section 3.7) rather than
discovered afterwards: the harness blends concurrently active sleeves by
equal-weighted average, so the reported daily return series is EXACTLY
1/holding_days times the economically real once-a-year book's series on every
day inside a formed hold. Sharpe, Calmar, risk_quality, stability and
preservation_score are invariant to that constant scale; ANNUALIZED RETURN,
total_cost_drag and total_financing_drag are NOT, and are 1/holding_days of
the real figures. sleeve_scale() gives the multiplier, the runner reports both
the raw and the de-scaled number, and tests/test_cross_sectional_tax_loss_
selling.py pins the exact-scaling property instead of assuming it.

WHY THE SHARPE IS NEVERTHELESS THE HONEST ONE: a strategy that is flat for
~246 sessions a year SHOULD be annualized including those sessions. The zeros
are not padding, they are real flat days on which no capital was at risk and
no return was earned.


====================================================================
6. THE SIZE CONFOUND — HANDLED AGAINST THE PAPERS, NOT AGAINST THE DSR
====================================================================
[PW01] p.362-363, verbatim: "Keim (1983) and many others suggest that large
turn-of-the-year returns are concentrated among small-capitalization
stocks... The effect of lagged losses on turn-of-the-year returns is
strongest for small- and medium-size firms, which might be expected given
their higher individual as opposed to institutional ownership... The two
estimated coefficients are statistically indistinguishable for the largest
and smallest size classes."

[PW01] Table V, LARGEST size decile, b3 - b4 by regime:
    Regime I  +0.050 (0.025)   Regime II  -0.006 (0.022)   Regime III  +0.023 (0.018)
Not one is significantly negative, and the Regime II cell — the regime with
the strongest tax incentive in the entire paper — is essentially zero.
[SK14]'s abstract independently calls the whole thing a
small-capitalization phenomenon.

This project's primary universe is the S&P 500, i.e. the top of that largest
decile and above it: PRECISELY WHERE BOTH PAPERS REPORT THE SIGNATURE TO BE
WEAKEST OR ABSENT. So the identical 16-spec grid runs on TWO universes —
point-in-time S&P 500 (from 2015-01-07) and point-in-time S&P 600 small-cap
(from 2020-01-01) — and the denominator doubles to 32 for the arithmetic
cross_sectional_small_mid_cap.py section 2 already established.

SIZE-NEUTRALIZING INSIDE THE S&P 500 WAS REJECTED: its internal size
dispersion is a slice of [PW01]'s top decile, so demeaning within it would
manufacture a "size-neutral" number about a range over which the paper
reports no effect. This project has already declined a candidate
(residual_momentum) for exactly that shape, where neutralization supplied
82.7% of the Sharpe.

NEITHER UNIVERSE REACHES THE MICRO-CAPS where the effect is reported
largest, and small_cap_membership_history.py documents that its own price
coverage gap is WORSE than the S&P 500's. This family does not claim to test
the effect where it is strongest.


====================================================================
7. WHAT THIS FAMILY CANNOT TEST
====================================================================
[PW01]'s identification is the 1969 Tax Reform Act (long-term loss
deductibility 100% -> 50%) and the 1976 Tax Reform Act (long-term holding
period 6 -> 9 -> 12 months). Both are decades before any daily price history
this project can reach, and neither is attempted.

There is NO in-window substitute. JGTRRA 2003 and ATRA 2013 predate
MEMBERSHIP_DATA_START. Within 2015-2026 none of the three parameters
[PW01]'s identification uses changed: the Tax Cuts and Jobs Act of 2017 left
the holding period, the long-term loss deduction fraction and the loss limit
alone (its proposed mandatory-FIFO securities provision was dropped from the
final bill), and IRS Topic no. 409 — fetched live 2026-09-06, page last
reviewed 25-Feb-2026 — still states verbatim "Generally, if you hold the
asset for more than one year before you dispose of it, your capital gain or
loss is long-term" and "The amount of the excess loss that you can claim to
lower your income is the lesser of $3,000 ($1,500 if married filing
separately) or your total net loss".

That is [PW01]'s Table I row for 1988-1996 — its REGIME III — unchanged.
Which gives the one regime-specific prediction that IS testable here, [PW01]
p.360 verbatim: "when the long-term holding period is 12 months in Regime
III, we would expect b3 = b4 < 0. This is the regime with the weakest
pressure for investors to realize early year losses before year-end."
So `jul_dec` and `jan_jun` are predicted to behave SIMILARLY today, and a
large divergence is evidence against the tax reading under current law.

CONSEQUENCE, accepted and stated: a positive result here would be CONSISTENT
with the tax-loss story but would not IDENTIFY it against plain seasonality
or reversal. The placebo (section 3) is the strongest falsification this
window supports; it is not as strong as [PW01]'s.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial
from typing import Literal

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab import borrow_cost
from app.services.research_lab.cross_sectional import (
    DEFAULT_XS_COST_BPS,
    CrossSectionalBacktestResult,
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    MembershipFn,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
)
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.preservation_score import compute_preservation_metrics
from app.services.research_lab.spread_estimator import (
    build_calibrated_half_spread_frame,
)

logger = logging.getLogger(__name__)

TAX_LOSS_FAMILY = "tax_loss_selling_turn_of_year"

TAX_LOSS_CITATION = (
    "Poterba & Weisbenner, 'Capital Gains Tax Rules, Tax-loss Trading, and Turn-of-the-year "
    "Returns', Journal of Finance 56(1), Feb 2001, pp. 353-368 — read in full 2026-09-06 from the "
    "authors' own posting. Turn-of-the-year return = 'the dividend-inclusive return on the last "
    "trading day in December and the first five days in January' (p.358); LOSS = the price change "
    "over a window ending before 'the last five trading days of December', set to zero for a gain "
    "(Eqs. 1a/1b); Table III LOSS coefficients -0.053..-0.178 all significant while GAIN "
    "coefficients -0.017..+0.008 are 'much smaller' and mostly insignificant; Table V's LARGEST "
    "size decile shows no significant effect in any regime. Context: Rozeff & Kinney, JFE 3(4) "
    "1976, 379-402, and Sikes, JAE 57(1) 2014, 22-42 — both ABSTRACT-LEVEL ONLY, no number or "
    "method from either used in this construction."
)

# --- section 2.1: the calendar anchor ---------------------------------------

# The formation date is the k-th-from-last trading day of the anchor month,
# with k = 2 -- i.e. d(-2), the SECOND-TO-LAST trading day. See section 2.1:
# the harness realizes from the day AFTER formation, so this is what makes
# d(-1)'s return the first realized day, and it is also the exact date
# [PW01] p.359 measures its own PRICE control on.
TAX_LOSS_FORMATION_OFFSET = 2

# The signal's window ends at the k-th-from-last trading day of December,
# with k = 6 -- i.e. d(-6), the last session that is NOT one of "the last
# five trading days of December" that [PW01] Eq.(1a) excludes. Four trading
# days before the formation date, never after it.
TAX_LOSS_SIGNAL_END_OFFSET = 6

# A calendar month with fewer real sessions than this in the loaded index is
# TRUNCATED BY THE DATA WINDOW, not a short month -- a real December has ~21
# and a real June ~21. Taking d(-1) from a truncated month would anchor the
# trade on a date that is not the last trading day of the month at all, which
# is a silently-wrong answer rather than a missing one. Such a year is skipped
# and COUNTED (TaxLossPanel.skipped_years), never guessed at.
MIN_ANCHOR_MONTH_TRADING_DAYS = 15

# --- section 2.4 / 3: the grid ----------------------------------------------

TaxLossWindow = Literal["full_year", "jul_dec", "jan_jun", "placebo_jan_jun"]
TaxLossForm = Literal["lossonly", "signed"]

# December-anchored windows, all three straight out of [PW01]:
#   full_year  [PW01] p.361, "losses and gains over the previous 12 months"
#   jul_dec    Eq.(1a)
#   jan_jun    Eq.(1b)
DECEMBER_WINDOWS: tuple[TaxLossWindow, ...] = ("full_year", "jul_dec", "jan_jun")

# The matched placebo (section 3): the SAME ranking variable as jan_jun,
# anchored in June instead of December.
PLACEBO_WINDOW: TaxLossWindow = "placebo_jan_jun"

TAX_LOSS_FORMS: tuple[TaxLossForm, ...] = ("lossonly", "signed")

# h=6  [PW01]'s exact turn-of-the-year window: d(-1) plus the first five
#      January sessions.
# h=21 approximately all of January -- the unit [RK76]'s month-of-year result
#      is stated in and the window inside which [SK14]'s "early January" sits.
# No third value: a longer hold would be holding a prediction about a window
# that has already closed.
TAX_LOSS_HOLDING_DAYS: tuple[int, ...] = (6, 21)

# Deciles on every spec. [PW01] runs a panel regression and sorts nothing, so
# neither deciles nor quintiles is "the paper's"; deciles are this project's
# standing convention and are DECLARED, not searched.
TAX_LOSS_RANK_FRACTION = 0.1

# The signal function reads exactly ONE row (the formation row) of a
# precomputed panel, so it needs no lookback window at all. Keeping this at 1
# is also what makes the per-formation history view a 1 x universe slice
# instead of a 252 x universe copy -- this family attempts one formation per
# trading day per sleeve (section 5) and a full-lookback view would make that
# quadratically expensive for no benefit.
TAX_LOSS_SIGNAL_LOOKBACK_ROWS = 1

# The overlapping-cohort stagger (see section 5 and CrossSectionalSpec.
# cohort_formation_days). 1 is the only value that makes EVERY trading day a
# formation date in exactly one sleeve, which is what guarantees the December
# anchor is hit in every year regardless of how many sessions that year had.
TAX_LOSS_COHORT_FORMATION_DAYS = 1

TAX_LOSS_SPEC_CEILING = 16

# --- section 6: two universes, one doubled denominator ----------------------

TaxLossUniverse = Literal["sp500", "sp600"]
TAX_LOSS_UNIVERSES: tuple[TaxLossUniverse, ...] = ("sp500", "sp600")

# The universe is a SEARCHED DIMENSION. Running one pre-declared 16-definition
# grid on two universes makes the set of results from which a maximum could be
# reported 16 x 2 = 32. This is cross_sectional_small_mid_cap.py section 2's
# own derivation, applied here; it is arithmetic, not conservatism, and it is
# passed to screen_cross_sectional_universe explicitly for BOTH universes so
# the number the DSR uses is the number the pre-registration states.
UNIVERSE_MULTIPLIER = 2
TAX_LOSS_N_TRIALS = UNIVERSE_MULTIPLIER * TAX_LOSS_SPEC_CEILING

assert TAX_LOSS_N_TRIALS == 32, (
    "the pre-registration declares n_local = 32 (16 specs x 2 universes); this module computes "
    f"{TAX_LOSS_N_TRIALS}. The two must agree — a drift silently changes the DSR denominator."
)

# --- section 6 of the pre-registration: costs -------------------------------

# S&P 600 one-way flat cost, per unit of gross notional traded. NOT invented
# here: it is the figure cross_sectional_small_mid_cap.SMALL_CAP_COST_BPS
# already pre-declared and used for this exact universe (its own docstring
# section 4 carries the derivation). Restated by value rather than imported so
# this module does not drag that family's whole import graph and its
# import-time family-size assertions in; tests/test_cross_sectional_tax_loss_
# selling.py asserts the two are equal, so they cannot drift silently.
SMALL_CAP_COST_BPS = 15.0

# D'Avolio (2002) / Beneish-Lee-Nichols (2015) general-collateral rate on the
# SHORT LEG alone, converted to the config's gross-notional basis by
# borrow_cost.financing_bps_for_long_short_book. 17.0 is simultaneously right
# for the long_universe_hedged specs, whose short side IS the whole index and
# is general collateral by construction (D'Avolio p.273: "S&P 500
# constituents, provided in excess supply by indexing lenders, are almost
# always general collateral").
TAX_LOSS_GC_SHORT_LEG_BPS_PER_YEAR = 34.0

# Pre-declared borrow sensitivity ladder (short-leg bps/yr). 430 is D'Avolio
# Table 3's value-weighted mean fee for "specials" — an explicit worst case in
# which every short-leg name is hard to borrow. NOT new trials: the same grid,
# re-scored on different returns.
TAX_LOSS_BORROW_LADDER_BPS: tuple[float, ...] = (0.0, 34.0, 430.0)

# Calendar days of price history fetched BEFORE the requested screening start.
# The longest window a formation reads is "last close of year Y-1 -> late
# December of year Y", so a December-Y formation needs roughly 400 calendar
# days of history; 500 is that plus slack for the price store's own holiday
# clustering. Formations never occur in the padding (config.formation_start
# pins them), so no formation can predate point-in-time membership coverage.
TAX_LOSS_PRICE_PADDING_CALENDAR_DAYS = 500

VALIDATED_EDGE_BAR = 0.95
SCREENING_FLOOR = 0.50


# ============================================================================
# the anchor schedule
# ============================================================================


@dataclass(frozen=True)
class AnchorDates:
    """One year's trading dates for one anchor month. Every field is a real
    row of the loaded price index, never a constructed calendar date."""

    year: int
    anchor_month: int
    formation: pd.Timestamp  # d(-2) of the anchor month
    signal_end: pd.Timestamp  # d(-6) of the anchor month
    last_session: pd.Timestamp  # d(-1), the first realized day of the hold


def anchor_schedule(index: pd.DatetimeIndex, *, anchor_month: int) -> list[AnchorDates]:
    """One AnchorDates per year in which `anchor_month` has a full set of
    sessions in `index`.

    A month with fewer than MIN_ANCHOR_MONTH_TRADING_DAYS rows is skipped
    outright, not clamped: it means the data window cut the month short, so
    its "last trading day" is an artifact of where the fetch ended rather
    than a real month end, and anchoring a once-a-year trade on an artifact
    is a silently-wrong answer. Callers surface the skipped years."""
    if len(index) == 0:
        return []
    years = sorted({int(y) for y in index.year})
    schedule: list[AnchorDates] = []
    for year in years:
        month_days = index[(index.year == year) & (index.month == anchor_month)]
        if len(month_days) < MIN_ANCHOR_MONTH_TRADING_DAYS:
            continue
        schedule.append(
            AnchorDates(
                year=year,
                anchor_month=anchor_month,
                formation=month_days[-TAX_LOSS_FORMATION_OFFSET],
                signal_end=month_days[-TAX_LOSS_SIGNAL_END_OFFSET],
                last_session=month_days[-1],
            )
        )
    return schedule


def _last_session_before(index: pd.DatetimeIndex, boundary: pd.Timestamp) -> pd.Timestamp | None:
    """The last row of `index` STRICTLY BEFORE `boundary`, or None.

    "Strictly before" is the right reading of [PW01]'s P_Jan1 and P_July1: 1
    January and 1 July are not trading days, and the price an investor's
    position carries into a period is the last close BEFORE the period opens.
    It also makes jan_jun and jul_dec partition full_year exactly — jan_jun's
    END and jul_dec's START are then the same session, with no gap and no
    double count."""
    position = int(index.searchsorted(boundary, side="left")) - 1
    if position < 0:
        return None
    return index[position]


def window_bounds(
    index: pd.DatetimeIndex, anchor: AnchorDates, window: TaxLossWindow
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """(start session, end session) for one anchor-year and one window, or
    None if the loaded index does not reach far enough back.

    full_year        last close of Y-1  ->  d(-6) of December Y   [PW01] p.361
    jul_dec          last close of June Y -> d(-6) of December Y  [PW01] (1a)
    jan_jun          last close of Y-1  ->  last close of June Y  [PW01] (1b)
    placebo_jan_jun  last close of Y-1  ->  d(-6) of June Y       section 3
    """
    year_open = _last_session_before(index, pd.Timestamp(year=anchor.year, month=1, day=1))
    mid_year = _last_session_before(index, pd.Timestamp(year=anchor.year, month=7, day=1))
    if window == "full_year":
        start, end = year_open, anchor.signal_end
    elif window == "jul_dec":
        start, end = mid_year, anchor.signal_end
    elif window == "jan_jun":
        start, end = year_open, mid_year
    elif window == "placebo_jan_jun":
        start, end = year_open, anchor.signal_end
    else:
        raise ValueError(f"unknown tax-loss window {window!r}")
    if start is None or end is None or start >= end:
        return None
    return start, end


def anchor_month_for(window: TaxLossWindow) -> int:
    """December for every [PW01] window, June for the placebo. The placebo's
    whole design is that only this differs (section 3)."""
    return 6 if window == PLACEBO_WINDOW else 12


# ============================================================================
# the signal panel
# ============================================================================


@dataclass
class TaxLossPanel:
    """One (window, form) pair's point-in-time signal panel, plus everything
    needed to audit it without re-running the build.

    `frame` is NaN everywhere except the formation rows, one per anchor year.
    That is the whole content of this family's calendar structure, and it is
    why a signal function here reads a single row rather than a lookback."""

    window: TaxLossWindow
    form: TaxLossForm
    frame: pd.DataFrame
    anchors: list[AnchorDates]
    skipped_years: list[int]
    n_finite_by_anchor: dict[pd.Timestamp, int]
    n_losers_by_anchor: dict[pd.Timestamp, int]
    price_vs_total_return_spearman: dict[pd.Timestamp, float]

    @property
    def key(self) -> str:
        return f"{self.window}_{self.form}"


def _window_return(
    price: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> pd.Series:
    """Simple price return over [start, end] per ticker, NaN where either
    endpoint is missing or the base price is non-positive.

    This is [PW01]'s "percentage difference between a stock's price at the
    beginning of a time period and its price at the end of the period",
    computed on the DIVIDEND-UNADJUSTED basis (section 2.3)."""
    base = price.loc[start]
    final = price.loc[end]
    base = base.where(np.isfinite(base) & (base > 0.0))
    final = final.where(np.isfinite(final))
    return (final / base) - 1.0


def _apply_form(window_return: pd.Series, form: TaxLossForm) -> pd.Series:
    """[PW01]'s LOSS truncation, or the plain reversal ranking (section 2.4).

    "lossonly" is Eq.(1a)/(1b) plus the sentence that follows them verbatim:
    "We set LOSS equal to zero if the firm experienced a capital gain." The
    harness ranks HIGH-is-long, and [PW01]'s LOSS is non-positive with more
    negative meaning more accrued loss, so the signal is its magnitude:
    max(-R, 0). NaN stays NaN -- a ticker with no window return has no signal,
    which is the SignalFn contract's "no valid signal today", not a zero."""
    if form == "lossonly":
        return (-window_return).clip(lower=0.0)
    if form == "signed":
        return -window_return
    raise ValueError(f"unknown tax-loss signal form {form!r}")


def build_tax_loss_panel(
    price_only_close: pd.DataFrame,
    total_return_close: pd.DataFrame,
    *,
    window: TaxLossWindow,
    form: TaxLossForm,
) -> TaxLossPanel:
    """One (window, form) panel, aligned to `total_return_close` exactly.

    POINT-IN-TIME CORRECTNESS, structurally and twice over:
      * The only row this panel ever carries a value on is the formation date
        d(-2), and that value is computed from prices at `start` and `end`,
        both of which are at or before d(-6) < d(-2) by construction of
        window_bounds and TAX_LOSS_SIGNAL_END_OFFSET. No formation row can
        read a price from its own day, let alone a later one.
      * The consuming signal function reads exactly ONE row, at the formation
        timestamp the harness hands it, and the harness has already truncated
        its view to rows <= that timestamp.
    Both are pinned by tests rather than asserted here.

    `total_return_close` is used for TWO things and neither is the signal: it
    fixes the panel's index/columns (validate_cross_sectional_data requires
    exact alignment with `close`), and it supplies the second basis for the
    price_vs_total_return_spearman diagnostic in section 2.3."""
    index = total_return_close.index
    frame = pd.DataFrame(
        np.nan, index=index, columns=total_return_close.columns, dtype=float
    )
    price = price_only_close.reindex(index=index, columns=total_return_close.columns)

    anchors = anchor_schedule(index, anchor_month=anchor_month_for(window))
    used: list[AnchorDates] = []
    skipped: list[int] = []
    n_finite: dict[pd.Timestamp, int] = {}
    n_losers: dict[pd.Timestamp, int] = {}
    spearman: dict[pd.Timestamp, float] = {}

    for anchor in anchors:
        bounds = window_bounds(index, anchor, window)
        if bounds is None:
            skipped.append(anchor.year)
            continue
        start, end = bounds
        raw = _window_return(price, start, end)
        signal = _apply_form(raw, form)
        frame.loc[anchor.formation] = signal.to_numpy()
        used.append(anchor)
        n_finite[anchor.formation] = int(np.isfinite(signal.to_numpy()).sum())
        n_losers[anchor.formation] = int((raw.to_numpy() < 0.0).sum())

        # Section 2.3's diagnostic: would the total-return basis have ranked
        # the cross-section differently? Reported, never acted on.
        total_raw = _window_return(total_return_close, start, end)
        both = pd.DataFrame({"px": raw, "tr": total_raw}).dropna()
        spearman[anchor.formation] = (
            float(both["px"].corr(both["tr"], method="spearman")) if len(both) >= 3 else float("nan")
        )

    return TaxLossPanel(
        window=window,
        form=form,
        frame=frame,
        anchors=used,
        skipped_years=skipped,
        n_finite_by_anchor=n_finite,
        n_losers_by_anchor=n_losers,
        price_vs_total_return_spearman=spearman,
    )


def build_all_tax_loss_panels(
    price_only_close: pd.DataFrame, total_return_close: pd.DataFrame
) -> dict[str, TaxLossPanel]:
    """All eight (window, form) panels the 16-spec grid is built from."""
    panels: dict[str, TaxLossPanel] = {}
    for window in (*DECEMBER_WINDOWS, PLACEBO_WINDOW):
        for form in TAX_LOSS_FORMS:
            panel = build_tax_loss_panel(
                price_only_close, total_return_close, window=window, form=form
            )
            panels[panel.key] = panel
    return panels


def signal_tax_loss(history: CrossSectionalData, *, panel: pd.DataFrame) -> pd.Series:
    """The formation date's row of a bound panel, restricted to the eligible
    columns the harness put in the view.

    WHY THE PANEL IS BOUND INTO THE CLOSURE rather than read off
    CrossSectionalData.fundamental_signal: this family carries EIGHT panels
    and the harness carries exactly one such field. Binding is the established
    pattern for that (cross_sectional_nport_flow.signal_expected_flow_induced_
    trading, cross_sectional_asset_growth's SIC bucket panel, the FX family's
    inverse-vol basis), and its look-ahead argument is stated rather than
    inherited: this function reads ONE row, at the view's own last (formation)
    timestamp, and the panel builder's contract is that the value on that row
    was computed only from prices at or before d(-6). Both halves are pinned
    by tests; that pinning is the substitute for the structural truncation
    guarantee, and the two are not the same strength.

    fundamental_signal is still required on every spec because it is what
    supplies the formation timestamp and the eligible column set here."""
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "signal_tax_loss needs CrossSectionalData.fundamental_signal for the formation "
            "timestamp and the eligible column set; the spec must set "
            "requires_fundamental_signal=True."
        )
    formation_ts = frame.index[-1]
    if formation_ts not in panel.index:
        return pd.Series(np.nan, index=frame.columns, dtype=float)
    row = panel.loc[formation_ts].reindex(frame.columns).astype(float)
    return row.where(np.isfinite(row))


# ============================================================================
# the grid
# ============================================================================


def _portfolio_for(form: TaxLossForm) -> Literal["long_short", "long_universe_hedged"]:
    """Section 2.4. "lossonly" is universe-hedged because [PW01]'s GAIN
    coefficients are "much smaller" and mostly insignificant, so there is no
    winner effect in the source to short. "signed" is long_short because that
    IS the generic reversal alternative the placebo and the asymmetry test
    exist to distinguish the mechanism from."""
    return "long_universe_hedged" if form == "lossonly" else "long_short"


def spec_id(window: TaxLossWindow, form: TaxLossForm, holding_days: int) -> str:
    prefix = "tls_jun_placebo" if window == PLACEBO_WINDOW else f"tls_dec_{window}"
    return f"{prefix}_{form}_h{holding_days}"


def build_tax_loss_family(panels: Mapping[str, TaxLossPanel]) -> list[CrossSectionalSpec]:
    """The 16 pre-declared specs, bound to their concrete panels.

    The panels are runtime DATA. The GRID — three December windows plus one
    placebo window, two signal forms, two holds, and the count of 16 — is
    fixed in the module constants above and in the pre-registration, and is
    never a searched axis. All 16 are screened in ONE pass per universe so
    sigma_sr (the sibling-Sharpe dispersion the DSR benchmark is built from)
    is taken across the whole declared family rather than within a slice."""
    specs: list[CrossSectionalSpec] = []
    for window in (*DECEMBER_WINDOWS, PLACEBO_WINDOW):
        for form in TAX_LOSS_FORMS:
            key = f"{window}_{form}"
            if key not in panels:
                raise ValueError(f"no panel supplied for {key}")
            for holding_days in TAX_LOSS_HOLDING_DAYS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=spec_id(window, form, holding_days),
                        family=TAX_LOSS_FAMILY,
                        citation=TAX_LOSS_CITATION,
                        signal_fn=partial(signal_tax_loss, panel=panels[key].frame),
                        lookback_days=TAX_LOSS_SIGNAL_LOOKBACK_ROWS,
                        holding_days=holding_days,
                        portfolio=_portfolio_for(form),
                        rank_fraction=TAX_LOSS_RANK_FRACTION,
                        requires_fundamental_signal=True,
                        # Section 5: one sleeve per trading-day phase, so the
                        # December anchor is a formation date in exactly one
                        # of them every year.
                        cohort_formation_days=TAX_LOSS_COHORT_FORMATION_DAYS,
                    )
                )
    assert len(specs) == TAX_LOSS_SPEC_CEILING == 16, (
        f"tax-loss family built {len(specs)} definitions; the declared ceiling is "
        f"{TAX_LOSS_SPEC_CEILING} and the pre-registration declared exactly 16. All three must "
        "agree — a drift silently changes this family's DSR denominator."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.leg_weighting == "magnitude" for s in specs)
    assert all(s.rank_fraction == TAX_LOSS_RANK_FRACTION for s in specs)
    assert all(s.cohort_formation_days == TAX_LOSS_COHORT_FORMATION_DAYS for s in specs)
    assert all(s.requires_fundamental_signal for s in specs)
    return specs


def sleeve_scale(holding_days: int) -> int:
    """How many staggered sleeves the harness runs for this family, which is
    exactly the factor the reported daily returns are DIVIDED by (section 5).

    Multiply a reported annualized return, total_cost_drag or
    total_financing_drag by this to recover the economically real once-a-year
    book's figure. Sharpe, Calmar, risk_quality, stability and
    preservation_score need no such correction — they are invariant under a
    constant positive scaling of the whole return series.

    This mirrors run_cross_sectional_backtest's own n_sleeves arithmetic
    (holding_days // cadence, floored at 1) rather than restating a magic
    number; a test pins the two against each other."""
    return max(1, holding_days // TAX_LOSS_COHORT_FORMATION_DAYS)


def memoized_membership(base: MembershipFn) -> MembershipFn:
    """A PURE-FUNCTION CACHE over a point-in-time membership gate.

    Not a semantic change and not a substitute for the real gate: it calls
    `base` and returns exactly what `base` returns, memoized on (ticker,
    date). It exists because this family attempts one formation per trading
    day per sleeve — ~2,700 dates x up to 21 sleeves x 16 specs — and every
    one of those re-asks the same (ticker, date) questions the previous spec
    already asked. Without it the eligibility loop, not the signal, dominates
    the run."""
    cache: dict[tuple[str, date], bool] = {}

    def _is_member(ticker: str, on: date) -> bool:
        key = (ticker, on)
        cached = cache.get(key)
        if cached is None:
            cached = bool(base(ticker, on))
            cache[key] = cached
        return cached

    return _is_member


# ============================================================================
# Policy D plumbing
# ============================================================================

# These two mirror cross_sectional_nport_flow's exported versions of the same
# name, deliberately re-stated here rather than imported: that module's import
# graph pulls in the SEC N-PORT and Form 13F provider stack, and an
# equity-price-only family should not depend on it to compute a DSR ladder.
# The arithmetic is identical and tests/test_cross_sectional_tax_loss_selling.py
# pins it against the same committed artifact.


def policy_d_denominators(n_local: int = TAX_LOSS_N_TRIALS) -> list[int]:
    """The N values a Policy D report must cover, ascending and deduplicated:
    dsr_n_trials(n_local), n_specs_clustered, raw_pooled_distinct_trials.

    The lowest tier is dsr_n_trials(n_local), NOT n_local itself:
    dsr_n_trials returns max(family grid size, pooled effective N), which is
    the denominator screen_cross_sectional_universe actually deflates at.
    Reporting the raw grid size beside it would show a DSR the run never
    computed. DSR is strictly decreasing in N, so three points BRACKET every N
    between them."""
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
    """DSR at each N. None means the machinery could not produce one there
    (below deflated_sharpe.MIN_TRIALS_FOR_DSR, or a degenerate series) and is
    treated downstream as NOT clearing the bar — an unmeasurable deflation is
    not a passing one."""
    from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe

    out: dict[int, float | None] = {}
    for n in denominators:
        out[int(n)] = compute_deflated_sharpe(
            sharpe_annualized,
            returns,
            int(n),
            sigma_sr_annualized,
            periods_per_year=periods_per_year,
        ).dsr
    return out


@dataclass
class AnnualEventStats:
    """The statistic a reader of this family should weigh most heavily.

    The Sharpe machinery reports ~2,700 daily observations per spec; the
    EFFECTIVE independent sample is the number of turn-of-year events —
    eleven on the S&P 500, six on the S&P 600. Compounding each hold into one
    number and taking a t-statistic on THOSE is the honest small-sample view,
    and it is declared in the pre-registration section 8 precisely so a
    large-looking DSR on a zero-inflated daily series cannot be reported as if
    it rested on 2,700 draws."""

    n_events: int
    event_returns: list[float]
    event_dates: list[str]
    mean: float
    std: float
    naive_t: float
    hit_rate: float


def annual_event_returns(
    replay: CrossSectionalBacktestResult, holding_days: int
) -> AnnualEventStats:
    """Per-formation compounded NET return of the real (un-blended) book.

    The harness blends `holding_days` staggered sleeves by equal-weighted
    average, and on every day inside a formed hold exactly one sleeve carries
    a book while the rest are flat, so the reported daily figure is the real
    one divided by sleeve_scale(holding_days) (section 5). Multiplying back by
    that factor and compounding over each formed formation's own hold window
    recovers the economically real event return."""
    scale = float(sleeve_scale(holding_days))
    daily = replay.daily_returns
    formed = [f for f in replay.formations if f.skipped_reason is None]
    returns: list[float] = []
    dates: list[str] = []
    for record in formed:
        after = daily.index[daily.index > record.date]
        hold = after[:holding_days]
        if len(hold) == 0:
            continue
        compounded = float(np.prod(1.0 + daily.loc[hold].to_numpy() * scale) - 1.0)
        returns.append(compounded)
        dates.append(record.date.date().isoformat())
    n = len(returns)
    if n == 0:
        return AnnualEventStats(0, [], [], float("nan"), float("nan"), float("nan"), float("nan"))
    array = np.asarray(returns, dtype=float)
    mean = float(array.mean())
    std = float(array.std(ddof=1)) if n >= 2 else float("nan")
    naive_t = float(mean / std * np.sqrt(n)) if n >= 2 and std > 0.0 else float("nan")
    return AnnualEventStats(
        n_events=n,
        event_returns=returns,
        event_dates=dates,
        mean=mean,
        std=std,
        naive_t=naive_t,
        hit_rate=float((array > 0.0).mean()),
    )


@dataclass
class SpecEvaluation:
    """One spec's full Policy D record: DSR at every denominator, the
    preservation score, and the annual-event view.

    preservation_score lives here rather than in an optional later pass on
    purpose — this project has twice shipped a check and then skipped it for
    the next real decision. A metric applied when someone remembers is a
    decoration, not a check."""

    pattern_id: str
    universe: str
    window: str
    form: str
    holding_days: int
    portfolio: str
    sharpe_annualized: float
    dsr_by_n: dict[int, float | None]
    preservation: dict[str, float | int | bool | None]
    annual: AnnualEventStats
    n_trading_days: int
    n_formations: int
    avg_names_per_leg: float
    total_cost_drag: float
    total_financing_drag: float
    total_turnover: float
    edge_flat_fallback_notional: float
    sleeve_scale: int


@dataclass
class SensitivityArm:
    """One pre-declared sensitivity arm: the whole grid re-scored under one
    changed assumption. NOT new trials — the DSR denominator is unchanged,
    only the returns the DSR is computed on."""

    key: str
    description: str
    sharpe_by_pattern: dict[str, float]
    dsr_by_pattern: dict[str, dict[int, float | None]]


@dataclass
class DoseResponse:
    """Fidelity check F3 (pre-registration section 7): [PW01]'s equation (2)
    is LINEAR in LOSS, so the tax story predicts a MONOTONE relationship
    between loss magnitude and turn-of-the-year return, not merely a
    top-decile jump.

    A DIAGNOSTIC computed from the same price data and the same panel — no
    new specs, no new trials."""

    bucket_mean_excess: list[float]
    bucket_counts: list[int]
    spearman_rank_vs_excess: float
    n_anchors: int
    holding_days: int
    note: str


@dataclass
class TaxLossUniverseResult:
    """Everything one universe's screening pass produced."""

    universe: TaxLossUniverse
    results: list[CrossSectionalScreeningResult]
    evaluations: list[SpecEvaluation]
    borrow_arms: list[SensitivityArm]
    dose_response: DoseResponse | None
    universe_size: int
    missing_price_data: list[str]
    formation_start: date
    window_end: date
    anchors: list[str]
    skipped_years: list[int]
    coverage_by_anchor: dict[str, dict[str, int]]
    price_vs_total_return_spearman: dict[str, float]
    sigma_sr: float | None
    cost_model: str
    cost_bps: float
    financing_bps_per_year: float
    half_spread_calibration: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class TaxLossScreeningSummary:
    """The whole build: both universes, one shared denominator."""

    universes: list[TaxLossUniverseResult]
    n_trials: int
    denominators: list[int]

    def all_evaluations(self) -> list[SpecEvaluation]:
        return [e for u in self.universes for e in u.evaluations]

    def verdict(self, threshold: float = VALIDATED_EDGE_BAR) -> tuple[str, str]:
        """(verdict, best pattern_id) under Policy D's two-tier rule across
        BOTH universes, computed by registration_scorecard.policy_d_verdict
        rather than reimplemented here so the run report and the scorecard
        cannot disagree."""
        from app.services.research_lab.registration_scorecard import policy_d_verdict

        evaluations = self.all_evaluations()
        if not evaluations:
            return ("definite_negative", "")
        best = max(
            evaluations,
            key=lambda e: (
                e.dsr_by_n.get(self.n_trials) if e.dsr_by_n.get(self.n_trials) is not None else -1.0
            ),
        )
        return (
            policy_d_verdict(
                dsr_by_n=best.dsr_by_n, threshold=threshold, n_local=self.n_trials
            ),
            f"{best.universe}/{best.pattern_id}",
        )


# ============================================================================
# F3: the dose-response diagnostic
# ============================================================================


def loss_decile_dose_response(
    total_return_close: pd.DataFrame,
    panel: TaxLossPanel,
    is_member: MembershipFn,
    *,
    holding_days: int,
    n_buckets: int = 10,
) -> DoseResponse:
    """Mean excess turn-of-the-year return by loss bucket, averaged over
    anchors — fidelity check F3.

    At each anchor the eligible cross-section (point-in-time member, finite
    formation close, finite signal) is split into `n_buckets` equal-count
    buckets by the panel's own signal. Each bucket's EQUAL-WEIGHTED
    compounded return over the same `holding_days` the specs hold is measured
    and the equal-weighted return of the whole eligible cross-section is
    subtracted, so the numbers are excess returns that sum to ~0 by
    construction. Bucket 0 is the LOWEST signal (smallest accrued loss, or a
    gain); bucket n-1 is the LARGEST accrued loss.

    [PW01]'s prediction is a MONOTONE INCREASE across buckets, because its
    equation (2) is linear in LOSS. A top-bucket jump with a flat or
    non-monotone middle is a different, weaker fact than the paper's."""
    index = total_return_close.index
    daily = total_return_close.pct_change(fill_method=None)
    sums = np.zeros(n_buckets, dtype=float)
    counts = np.zeros(n_buckets, dtype=int)
    n_anchors = 0

    for anchor in panel.anchors:
        formation = anchor.formation
        if formation not in panel.frame.index:
            continue
        after = index[index > formation][:holding_days]
        if len(after) < holding_days:
            continue
        formation_day = formation.date()
        signal = panel.frame.loc[formation]
        close_row = total_return_close.loc[formation]
        eligible = [
            t
            for t in total_return_close.columns
            if np.isfinite(signal.get(t, np.nan))
            and np.isfinite(close_row.get(t, np.nan))
            and is_member(t, formation_day)
        ]
        if len(eligible) < n_buckets * 2:
            continue
        hold = daily.loc[after, eligible]
        forward = (1.0 + hold.fillna(0.0)).prod(axis=0) - 1.0
        universe_mean = float(forward.mean())
        ordered = signal.reindex(eligible).sort_values(kind="mergesort")
        edges = np.array_split(np.arange(len(ordered)), n_buckets)
        for bucket, positions in enumerate(edges):
            if len(positions) == 0:
                continue
            names = list(ordered.index[positions])
            sums[bucket] += float(forward.reindex(names).mean()) - universe_mean
            counts[bucket] += len(names)
        n_anchors += 1

    if n_anchors == 0:
        return DoseResponse([], [], float("nan"), 0, holding_days, "no anchor had a usable cross-section")
    means = (sums / n_anchors).tolist()
    ranks = np.arange(n_buckets, dtype=float)
    finite = np.isfinite(np.asarray(means))
    spearman = (
        float(pd.Series(np.asarray(means)[finite]).corr(pd.Series(ranks[finite]), method="spearman"))
        if finite.sum() >= 3
        else float("nan")
    )
    return DoseResponse(
        bucket_mean_excess=means,
        bucket_counts=counts.tolist(),
        spearman_rank_vs_excess=spearman,
        n_anchors=n_anchors,
        holding_days=holding_days,
        note=(
            "bucket 0 = smallest accrued loss / largest gain, bucket "
            f"{n_buckets - 1} = largest accrued loss; equal-weighted compounded "
            f"{holding_days}-day return minus the equal-weighted eligible universe, averaged over "
            f"{n_anchors} anchors; a ticker missing a session inside the hold contributes 0.0 for "
            "that session rather than dropping out, which is a diagnostic-grade simplification the "
            "harness itself does not make"
        ),
    )


# ============================================================================
# the production entry point
# ============================================================================


def default_tax_loss_config(universe: TaxLossUniverse, start: date) -> CrossSectionalConfig:
    """A fresh config per call — the harness writes formation_start onto
    whatever it is given, so a shared singleton would leak between runs.

    Costs are pre-registration section 6, and the two universes deliberately
    do NOT share a turnover model. The calibrated EDGE half-spread frame's
    LEVEL is pinned to a published S&P 500 median, and spread_estimator's own
    docstring says so in as many words ("THIS NUMBER IS A UNIVERSE PROPERTY,
    NOT A CONSTANT OF NATURE... Pass an explicit target_median_half_spread for
    anything else"). This project has no sourced small-cap median half-spread,
    so the S&P 600 run uses the flat SMALL_CAP_COST_BPS = 15.0 that
    cross_sectional_small_mid_cap.py already pre-declared for exactly this
    universe, rather than a fabricated calibration target chosen to keep the
    two universes cosmetically symmetric."""
    if universe == "sp500":
        return CrossSectionalConfig(
            cost_bps=DEFAULT_XS_COST_BPS,
            cost_model="edge_spread",
            formation_start=start,
            financing_bps_per_year=borrow_cost.financing_bps_for_long_short_book(
                TAX_LOSS_GC_SHORT_LEG_BPS_PER_YEAR
            ),
        )
    return CrossSectionalConfig(
        cost_bps=SMALL_CAP_COST_BPS,
        cost_model="flat_bps",
        formation_start=start,
        financing_bps_per_year=borrow_cost.financing_bps_for_long_short_book(
            TAX_LOSS_GC_SHORT_LEG_BPS_PER_YEAR
        ),
    )


def _universe_gate(universe: TaxLossUniverse) -> tuple[Callable[[date, date], list[str]], MembershipFn, date]:
    if universe == "sp500":
        from app.services.research_lab.sp500_membership_history import (
            MEMBERSHIP_DATA_START,
            get_universe_over,
            was_member,
        )

        return get_universe_over, was_member, MEMBERSHIP_DATA_START
    from app.services.research_lab.small_cap_membership_history import (
        MEMBERSHIP_DATA_START,
        get_universe_over,
        was_member,
    )

    return get_universe_over, was_member, MEMBERSHIP_DATA_START


def _replay_all(
    data: CrossSectionalData,
    specs: Sequence[CrossSectionalSpec],
    config: CrossSectionalConfig,
    membership_fn: MembershipFn,
) -> dict[str, CrossSectionalBacktestResult]:
    replays: dict[str, CrossSectionalBacktestResult] = {}
    for spec in specs:
        replay = run_cross_sectional_backtest(data, spec, config, membership_fn)
        if replay.status == "ok":
            replays[spec.pattern_id] = replay
    return replays


def _config_with(base: CrossSectionalConfig, **overrides) -> CrossSectionalConfig:
    from dataclasses import replace

    return replace(base, **overrides)


def _sensitivity_arm(
    *,
    key: str,
    description: str,
    data: CrossSectionalData,
    specs: Sequence[CrossSectionalSpec],
    config: CrossSectionalConfig,
    membership_fn: MembershipFn,
    denominators: Sequence[int],
) -> SensitivityArm:
    from app.services.research_lab.metrics import sharpe_ratio

    replays = _replay_all(data, specs, config, membership_fn)
    sharpes = {
        pid: sharpe_ratio(r.daily_returns, periods_per_year=config.periods_per_year)
        for pid, r in replays.items()
    }
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None
    dsr_by_pattern = {
        pid: dsr_across_denominators(
            sharpes[pid],
            replays[pid].daily_returns,
            sigma_sr,
            denominators,
            periods_per_year=config.periods_per_year,
        )
        for pid in replays
    }
    return SensitivityArm(
        key=key, description=description, sharpe_by_pattern=sharpes, dsr_by_pattern=dsr_by_pattern
    )


def run_tax_loss_universe(
    universe: TaxLossUniverse,
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    *,
    denominators: Sequence[int] | None = None,
    borrow_ladder: Sequence[float] = TAX_LOSS_BORROW_LADDER_BPS,
) -> TaxLossUniverseResult:
    """Screen the full 16-spec grid on ONE universe.

    `start` must be at or after that universe's own MEMBERSHIP_DATA_START; a
    formation before it would silently see an empty cross-section because the
    membership gate answers False for everyone, which this project has already
    been bitten by once on a bond-ETF family."""
    get_universe_over, was_member, membership_start = _universe_gate(universe)
    if start < membership_start:
        raise ValueError(
            f"tax-loss screening start {start.isoformat()} predates point-in-time membership "
            f"coverage for {universe} ({membership_start.isoformat()}) — a formation before that "
            "date would silently see an empty universe."
        )
    provider = provider if provider is not None else YFinanceProvider()
    config = default_tax_loss_config(universe, start)
    denominators = list(denominators) if denominators is not None else policy_d_denominators()

    tickers = get_universe_over(start, end)
    padded_start = start - timedelta(days=TAX_LOSS_PRICE_PADDING_CALENDAR_DAYS)
    frames, missing_price = provider.get_daily_ohlcv(tickers, padded_start, end)
    if not frames:
        raise ValueError(f"no price data resolved for the {universe} universe over the window")
    close = frames["close"]

    _, price_only_close, _ = provider.get_total_and_price_return_closes(
        tickers, padded_start, end
    )
    price_only_close = price_only_close.reindex(index=close.index, columns=close.columns)

    warnings: list[str] = []
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

    panels = build_all_tax_loss_panels(price_only_close, close)
    specs = build_tax_loss_family(panels)
    membership_fn = memoized_membership(was_member)

    data = CrossSectionalData(
        close=close,
        open=frames["open"],
        volume=frames["volume"],
        price_only_close=price_only_close,
        # Carrier for the formation timestamp and the eligible column set only
        # — every spec's real signal is bound into its closure (see
        # signal_tax_loss). Any of the eight panels would serve identically;
        # the first December window's lossonly panel is chosen so the frame
        # that IS structurally truncated by the harness is a real one from the
        # declared grid rather than a synthetic placeholder.
        fundamental_signal=panels[f"{DECEMBER_WINDOWS[0]}_lossonly"].frame,
        half_spread=half_spread,
    )

    results = screen_cross_sectional_universe(
        data, specs, config, membership_fn=membership_fn, n_trials_override=TAX_LOSS_N_TRIALS
    )
    replays = _replay_all(data, specs, config, membership_fn)
    sigma_sr = (
        float(np.std([r.sharpe_annualized for r in results], ddof=1)) if len(results) >= 2 else None
    )

    spec_by_id = {s.pattern_id: s for s in specs}
    evaluations: list[SpecEvaluation] = []
    for result in results:
        replay = replays.get(result.pattern_id)
        if replay is None:
            continue
        spec = spec_by_id[result.pattern_id]
        window, form = _decode_pattern_id(result.pattern_id)
        evaluations.append(
            SpecEvaluation(
                pattern_id=result.pattern_id,
                universe=universe,
                window=window,
                form=form,
                holding_days=spec.holding_days,
                portfolio=spec.portfolio,
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
                annual=annual_event_returns(replay, spec.holding_days),
                n_trading_days=result.n_trading_days,
                n_formations=result.n_formations,
                avg_names_per_leg=result.avg_names_per_leg,
                total_cost_drag=result.total_cost_drag,
                total_financing_drag=result.total_financing_drag,
                total_turnover=result.total_turnover,
                edge_flat_fallback_notional=result.edge_flat_fallback_notional,
                sleeve_scale=sleeve_scale(spec.holding_days),
            )
        )

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
            membership_fn=membership_fn,
            denominators=denominators,
        )
        for short_leg_bps in borrow_ladder
    ]

    dose_panel = panels[f"{DECEMBER_WINDOWS[0]}_lossonly"]
    dose = loss_decile_dose_response(
        close, dose_panel, membership_fn, holding_days=TAX_LOSS_HOLDING_DAYS[0]
    )

    headline_panel = dose_panel
    if headline_panel.skipped_years:
        warnings.append(
            f"{universe}: anchor years skipped for want of a full anchor month or enough prior "
            f"history: {headline_panel.skipped_years}"
        )

    coverage = {
        ts.date().isoformat(): {
            "n_finite_signal": headline_panel.n_finite_by_anchor.get(ts, 0),
            "n_with_accrued_loss": headline_panel.n_losers_by_anchor.get(ts, 0),
        }
        for ts in sorted(headline_panel.n_finite_by_anchor)
    }

    return TaxLossUniverseResult(
        universe=universe,
        results=results,
        evaluations=evaluations,
        borrow_arms=borrow_arms,
        dose_response=dose,
        universe_size=len(tickers),
        missing_price_data=missing_price,
        formation_start=start,
        window_end=end,
        anchors=[a.formation.date().isoformat() for a in headline_panel.anchors],
        skipped_years=headline_panel.skipped_years,
        coverage_by_anchor=coverage,
        price_vs_total_return_spearman={
            ts.date().isoformat(): v
            for ts, v in sorted(headline_panel.price_vs_total_return_spearman.items())
        },
        sigma_sr=sigma_sr,
        cost_model=config.cost_model,
        cost_bps=config.cost_bps,
        financing_bps_per_year=config.financing_bps_per_year,
        half_spread_calibration=calibration_summary,
        warnings=warnings,
    )


def _decode_pattern_id(pattern_id: str) -> tuple[str, str]:
    """(window, form) back out of a pattern_id built by spec_id()."""
    for window in (*DECEMBER_WINDOWS, PLACEBO_WINDOW):
        for form in TAX_LOSS_FORMS:
            for holding_days in TAX_LOSS_HOLDING_DAYS:
                if spec_id(window, form, holding_days) == pattern_id:
                    return window, form
    raise ValueError(f"unrecognised tax-loss pattern_id {pattern_id!r}")


def run_tax_loss_screening(
    windows: Mapping[TaxLossUniverse, tuple[date, date]],
    provider: YFinanceProvider | None = None,
) -> TaxLossScreeningSummary:
    """THE production entry point: the same 16-spec grid on every universe in
    `windows`, sharing ONE denominator (TAX_LOSS_N_TRIALS = 32).

    `windows` maps a universe key to its (start, end). Both universes are
    expected in a production run; a single-universe call is legitimate for
    tests and diagnostics but its DSR still carries the two-universe
    denominator, because the pre-registration declared both."""
    denominators = policy_d_denominators()
    universes = [
        run_tax_loss_universe(universe, start, end, provider, denominators=denominators)
        for universe, (start, end) in windows.items()
    ]
    return TaxLossScreeningSummary(
        universes=universes, n_trials=TAX_LOSS_N_TRIALS, denominators=denominators
    )


__all__ = [
    "TAX_LOSS_CITATION",
    "TAX_LOSS_FAMILY",
    "TAX_LOSS_HOLDING_DAYS",
    "TAX_LOSS_N_TRIALS",
    "TAX_LOSS_SPEC_CEILING",
    "TAX_LOSS_UNIVERSES",
    "AnchorDates",
    "AnnualEventStats",
    "DoseResponse",
    "SensitivityArm",
    "SpecEvaluation",
    "TaxLossPanel",
    "TaxLossScreeningSummary",
    "TaxLossUniverseResult",
    "anchor_schedule",
    "annual_event_returns",
    "build_all_tax_loss_panels",
    "build_tax_loss_family",
    "build_tax_loss_panel",
    "default_tax_loss_config",
    "dsr_across_denominators",
    "loss_decile_dose_response",
    "memoized_membership",
    "policy_d_denominators",
    "run_tax_loss_screening",
    "run_tax_loss_universe",
    "signal_tax_loss",
    "sleeve_scale",
    "spec_id",
    "window_bounds",
]
