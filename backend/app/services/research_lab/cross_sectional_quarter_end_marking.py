"""PERIOD-END "MARKING THE CLOSE" / MARKING-UP — a calendar-anchored
cross-sectional equity family expressed against cross_sectional.py's harness.

The grid, the denominator, the cost model, the fidelity checks, the placebo and
the pass/fail rule are fixed by
data/research_runs/quarter_end_marking_PREREGISTRATION.txt, committed BEFORE
this module screened anything. Nothing here may quietly differ from it; a
difference is a diff, not a decision.

Needs ONLY daily price history and point-in-time index membership — no filings,
no fundamentals, no vendor feed.


====================================================================
1. THE SOURCE, AND EXACTLY WHAT WAS OBTAINED OF IT
====================================================================
[CKMR99] Carhart, Mark M.; Kaniel, Ron; Musto, David K.; Reed, Adam. "Mutual
         Fund Returns and Market Microstructure." Rodney L. White Center for
         Financial Research, Wharton School, University of Pennsylvania,
         Working Paper 011-99, this revision 2 June 1999.
         OBTAINED IN FULL AND READ IN FULL (2026-09-06). 32-page PDF: two
         cover pages, the paper's own pp.1-22, Tables I-V (pp.23-27), Figures
         1A-2C (pp.28-30). Read both as `pdftotext -layout` text (1,430 lines)
         and, for the first 16 pages, as rendered images. Every page number,
         table number, coefficient and quotation below was read off those
         pages. THIS IS THE MECHANISM-FIDELITY PAPER.

[CKMR02] THE PUBLISHED VERSION, NOT OBTAINED. Carhart, Kaniel, Musto & Reed,
         "Leaning for the Tape: Evidence of Gaming Behavior in Equity Mutual
         Funds", THE JOURNAL OF FINANCE 57(2), April 2002, pp. 661-693,
         doi:10.1111/1540-6261.00438. Bibliographic details VERIFIED against
         Wiley, RePEc (bla/jfinan/v57y2002i2p661-693) and SSRN (309177);
         FULL TEXT BEHIND A PAYWALL (Wiley 403; the UPenn institutional
         repository also 403s an automated fetch). NO NUMBER, PAGE OR
         QUOTATION HERE COMES FROM IT. Three years and a referee process
         separate the two versions; the published article may use a longer
         sample or a refined methodology, and DISAGREEMENT WITH IT IS
         POSSIBLE AND NOT RULED OUT.

[ZW97]   Zweig, "Watch out for the year-end fund flimflam", Money Magazine,
         November 1997, 130-133. NOT OBTAINED, NOT READ. Quoted only as
         [CKMR99] p.5 quotes it, and used in no construction.

[SEC95]  SEC release #36556, 6 December 1995. NOT OBTAINED, NOT READ. Its
         definition of "marking the close" appears only as [CKMR99] p.5 quotes
         it, and no construction depends on it.


====================================================================
2. THE MECHANISM, AND THE CONSTRUCTION IT DICTATES
====================================================================
[CKMR99] p.3, verbatim: "The share price of an open-end mutual fund is not
negotiated in a market. It is inferred from the negotiated prices of the fund's
holdings, typically their closing prices on their primary exchanges... The
location within the spread of a stock's closing trade has little or no
intrinsic significance, but it passes straight through to the prices of the
funds positioning it."

p.5, verbatim: "In SEC terminology, 'marking the close' is 'the practice of
attempting to influence the closing price of a stock by executing purchase or
sale orders at or near the close of the market,' (SEC release #36556, December
6, 1995). One explanation offered by Zweig (1997), which we call the marking-up
model, is that fund managers mark the close of their holdings with buy orders."

p.6, verbatim: "the obvious target for this strategy is the calendar-year
return... The convexity of the new investment/annual return relation (Ippolito
(1992), Sirri and Tufano (1998)), combined with the weakness of performance
persistence... suggests an especially strong incentive for the year-to-date's
best performers to increase their year-end portfolio value at the expense of
the next year's return."

2.1 THE EVENT CALENDAR IS THE PAPER'S OWN DUMMY DEFINITION, Table I caption
p.23, verbatim: "YENDd is 1 if d is the last trading day of December, YBEGd is
1 if YENDd-1 is 1, QENDd is 1 if d is the last trading day of March, June or
September, and QBEGd is 1 if QENDd-1 is 1, MENDd is 1 if d is the last day of
January, February, April, May, July, August, October or November, and MBEGd is
1 if MENDd-1 is 1."

NOTE THE WORKING PAPER'S OWN INTERNAL CONTRADICTION, recorded rather than
silently resolved. Its ABSTRACT (p.2) says "The same applies on a smaller scale
at quarter-ends that aren't month-ends", which cannot be right — every
quarter-end IS a month-end. The Section III definitions (p.8), the Table I
caption above and the Conclusion (p.20, "This applies on a smaller scale to
quarter-ends, but not month-ends that aren't quarter-ends") all agree with each
other and disagree with the abstract. THIS MODULE FOLLOWS THE BODY. Whether
[CKMR02] fixed the abstract is unknown here.

2.2 THE RANKING VARIABLE. [CKMR99]'s stock-level sort, p.14 verbatim: "For a
given year-end y, our universe is all equities in TAQ with a total return from
CRSP from the end of June to day -1, so we can sort by recent performance. For
stock s we call this PERFy,s." Table V's caption restates it: "Performance
quintiles for stocks are based on the previous six-months' return not including
last day of the year."

Two windows are pre-declared (pre-registration 4.3), both TOTAL-RETURN and both
measured with data up to and including the close of d(-1):
  perf_h126  the trailing 126-trading-day return ending at d(-1) — the paper's
             own six-month window, expressed as a fixed session count so that
             one definition serves year-, quarter- and month-ends alike.
  perf_ptd   the PERIOD-TO-DATE return, from the last close before the period
             opened to the close of d(-1) — the MOTIVE variable of p.6 and
             p.12 ("If we sort funds by their year-to-date return going into
             the last day, we should find by this argument that the best
             performers evidence above-average inflation of year-end
             valuations"), adapted to whichever period is ending.

2.3 THE THREE ARMS. Writing d(0) for the event session, d(-1) for the one
before and d(1) for the one after, and remembering that the harness forms at a
date's CLOSE and realizes from the NEXT day:

  day0  form at d(-1) with signal = +PERF, hold 1 day -> realizes d(0)'s
        close-to-close return, LONG winners / SHORT losers. The markup leg.
  day1  form at d(0) with signal = -PERF, hold 1 day -> realizes d(1)'s return,
        LONG losers / SHORT winners. The reversal leg. PERF is still measured
        through d(-1) (see 2.4).
  oval  BOTH, as one continuously managed book: +PERF at d(-1), flipped to
        -PERF at d(0), flat after d(1). Its realized return is exactly the
        winner-minus-loser spread's d(0) return MINUS its d(1) return, which is
        [CKMR99] p.18's own measure, verbatim: "Our measure of a stock's
        overvaluation is the day 0 return minus the day 1 return, which for
        stock s in year y we call OVALs,y."

`oval` IS THE PRIMARY ARM, and section 4 is why.

2.4 WHY day1 RANKS ON A WINDOW ENDING d(-1) AND NOT d(0). [CKMR99]'s fund-level
Tables II and IV rank on a window ending d-1 for a dependent variable on d,
which for d = d(1) would end at d(0). This module refuses that at the STOCK
level: a cross-sectional sort that includes d(0)'s own return would be sorting
partly on "which stocks printed high at the close", which at daily frequency is
indistinguishable from bid-ask bounce and one-day reversal and would manufacture
a next-day reversal out of microstructure alone. Excluding d(0) can only weaken
a measured reversal, never create one, and it is what makes day0/day1/oval a
matched trio on ONE ranking.


====================================================================
3. WHAT THIS FAMILY CANNOT TEST — THE LARGEST DEVIATION IN THE BUILD
====================================================================
[CKMR99] uses four data sources. This project has an analogue of ONE, and not
the important one.

  S&P MICROPAL daily fund returns (2,207 funds)  NOT AVAILABLE. Tables I-IV are
    all fund-return regressions. THE PAPER'S HEADLINE FACT — p.9, "80% of funds
    beat the S&P on the last day of the year... compared with only 30% the next
    day", 89% and 26% for Aggressive Growth — IS FUND-LEVEL AND IS NOT TESTED
    HERE AT ALL.
  NYSE TAQ intraday transactions  NOT AVAILABLE. Section IV's six timestamped
    prices per stock-year (p.14-15) are unbuildable. The paper puts the effect
    precisely inside the interval this family cannot see: p.15, "46 of those bp
    came in the last hour of the year and 44 of them were gone 30 minutes into
    day 1"; p.16, "most of the action is in a small window around the close".
  CDA quarterly fund holdings  NOT AVAILABLE. Section V / Table V need the
    disclosed holdings of the top 10% of funds by year-to-date return.
  CRSP daily returns  THE ONE WITH AN ANALOGUE: this repository's point-in-time
    price store, gated by point-in-time index membership.

So this family tests the STOCK-LEVEL cross-sectional prediction [CKMR99] itself
derives and tests in Sections IV and V, at the daily close only. It is not a
stand-in for the fund-level result and does not claim to be one.


====================================================================
4. THE NUMBER THAT GOVERNS THE DESIGN
====================================================================
[CKMR99] pp.15-16 describes its own stock-level quintile results in prose
(Figures 2A-2C are charts; these are the authors' readings of them), verbatim:

  FULL CROSS-SECTION: "The loser portfolio gains 2 1/2% on both day 0 and day 1,
  compared with only 1/4% per day for the VW index... The winner portfolio, on
  the other hand, goes nowhere. The top-quintile stocks gain only 2bp over the
  two trading-days. But at the year's close in the middle, they are up 81bp,
  where 46 of those bp came in the last hour of the year and 44 of them were
  gone 30 minutes into day 1."
  SMALLEST-CAP QUINTILE: "Winners are up 109bp by the end of the year... This
  does not reverse on the next day, though they do lag the market, making 6bp
  rather than 21." Losers "making 6.3% in total".
  LARGEST-CAP QUINTILE: "winners make 37bp on day 0, 22 in the last hour, and
  then lose 94bp in the first 30 minutes of day 1 and 50 more over the rest of
  the day."

Reading r0 and r1 off those sentences for the WINNER quintile: full
cross-section r0 = +81bp and r0+r1 = +2bp so r1 = -79bp; smallest-cap +109bp
then +6bp; largest-cap +37bp then -144bp. For the full cross-section LOSER
quintile r0 = r1 = +250bp.

THEREFORE, AT THE DAILY CLOSE, IN THE PAPER'S OWN DATA, the day-0
winner-minus-loser spread is 81 - 250 = -169bp and the day-1 spread is
-79 - 250 = -329bp. Both negative; both swamped by the turn-of-the-year
small-cap loser effect the paper names in the same paragraph (p.15, "This is
exactly the turn-of-the-year effect already documented in earlier years - big
returns for small stocks, especially recent losers"). The quantity that
ISOLATES the marking signature is r0 - r1: +160bp for full-cross-section
winners, +103bp smallest-cap, +181bp largest-cap, and ~0bp for
full-cross-section losers.

That is why `oval` is the primary arm and why `day0` and `day1` are
PRE-DECLARED AS EXPECTED TO FAIL (pre-registration 11(2)). A large positive
`day1` result is most likely a rediscovery of the turn-of-the-year loser effect
this project has already closed as an honest negative
(cross_sectional_tax_loss_selling, DEFINITE_NEGATIVE at DSR 0.5553), not
evidence of marking.


====================================================================
5. THE PLACEBO — THE SOURCE'S OWN CONTROL
====================================================================
[CKMR99] p.9, verbatim: "There is no evidence of the price shifts for
month-ends that aren't quarter-ends", and "Other month-ends show nothing
(despite many more observations), ruling out month-end explanations for the
effect, such as the monthly transfer from paychecks to pensions or other
savings plans." Table I bears it out: MEND -1.00 with p = 82.53%.

`month_placebo` runs the IDENTICAL grid — same ranking, same arms, same
universe, same costs — on the eight months that are neither quarter- nor
year-ends, and it has roughly eight times the events of the year-end arm, so it
is the BETTER-POWERED arm. Pre-registration section 6 makes it a binding
one-sided override: if the best placebo spec matches the best real spec in sign
and magnitude, the family is a negative on mechanism grounds whatever the DSR.


====================================================================
6. HARNESS FIT — ONE DEVIATION, AND IT IS SMALLER THAN TAX-LOSS-SELLING'S
====================================================================
holding_days = 1 makes cross_sectional.py's formation cadence one trading day,
so EVERY session is a formation date in the single sleeve
(holding_days // cadence == 1). There is NO sleeve blending and therefore NO
1/holding_days rescaling of returns, costs or annualized figures — unlike
cross_sectional_tax_loss_selling.py, whose 21-day holds forced 21 staggered
sleeves. Every number the harness reports for this family is the real book's
number, and a unit test pins that rather than assuming it.

The signal panel is NaN on every session that is not a formation date for its
own (period, arm), so those formations skip, the book goes flat, and the
round-trip turnover is charged exactly where it occurs: entry at d(-1), and
either liquidation at d(0) (day0 arm) or a full sign flip at d(0) then
liquidation at d(1) (oval arm).

ONE CONSEQUENCE THAT IS EASY TO GET WRONG AND IS HANDLED EXPLICITLY: the
harness charges a formation's turnover on that formation's FIRST REALIZATION
DAY, so the LIQUIDATION charge lands one session AFTER the last day the book
was exposed. An event's realized profit and loss therefore spans one session
more than its exposure — see arm_pnl_window. Compounding only the exposed
sessions would report an entry-cost-only number and would flatter every arm,
including the month-end placebo whose comparison decides the section 5
override.
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

QEM_FAMILY = "quarter_end_marking"

QEM_CITATION = (
    "Carhart, Kaniel, Musto & Reed, 'Mutual Fund Returns and Market Microstructure', Wharton "
    "Rodney L. White Center WP 011-99, revision 2 June 1999 — read in full 2026-09-06 (32-page "
    "PDF, prose pp.1-22 plus Tables I-V and Figures 1A-2C). Marking the close = 'the practice of "
    "attempting to influence the closing price of a stock by executing purchase or sale orders at "
    "or near the close of the market' (SEC release #36556, quoted p.5). Event days are the "
    "paper's own Table I dummies (p.23): YEND = last trading day of December, QEND = last trading "
    "day of March/June/September, MEND = last trading day of the other eight months. Stock-level "
    "sort is the 'previous six-months' return not including last day of the year' into QUINTILES, "
    "equal-weighted within quintile (p.14-15, Table V caption). The traded measure is OVAL, 'the "
    "day 0 return minus the day 1 return' (p.18). Table I ALL-funds coefficients (bp): YEND "
    "+48.03 (p=0.02%), YBEG -32.93 (0.72%), QEND +17.36 (1.82%), QBEG -11.21 (12.69%), MEND "
    "-1.00 (82.53%). PUBLISHED VERSION NOT OBTAINED: Carhart/Kaniel/Musto/Reed, 'Leaning for the "
    "Tape', Journal of Finance 57(2), April 2002, 661-693, doi:10.1111/1540-6261.00438 — "
    "bibliographic details verified against Wiley/RePEc/SSRN, full text paywalled, and "
    "disagreement between this build and that article is possible and not ruled out."
)

# --- section 2.1: the event calendar ---------------------------------------

QemPeriod = Literal["year_end", "quarter_end", "month_placebo"]

# [CKMR99] Table I caption, p.23. December is deliberately absent from
# QUARTER_END_MONTHS ("quarter-end (other than a year-end)", Section III p.8)
# and every quarter-end month is absent from PLACEBO_MONTHS ("month-end (other
# than a quarter-end)"). The three sets partition the twelve months exactly,
# which a test pins.
YEAR_END_MONTHS: tuple[int, ...] = (12,)
QUARTER_END_MONTHS: tuple[int, ...] = (3, 6, 9)
PLACEBO_MONTHS: tuple[int, ...] = (1, 2, 4, 5, 7, 8, 10, 11)

QEM_PERIODS: tuple[QemPeriod, ...] = ("year_end", "quarter_end", "month_placebo")

PERIOD_MONTHS: dict[QemPeriod, tuple[int, ...]] = {
    "year_end": YEAR_END_MONTHS,
    "quarter_end": QUARTER_END_MONTHS,
    "month_placebo": PLACEBO_MONTHS,
}

# A calendar month with fewer real sessions than this in the loaded index is
# TRUNCATED BY THE DATA WINDOW, not a short month — a real month has ~19-23.
# Taking its last row as "the last trading day of the month" would anchor the
# trade on an artifact of where the fetch ended, which is a silently-wrong
# answer rather than a missing one. Such a month is skipped and COUNTED
# (QemPanel.skipped_months), never clamped. Same rule and same threshold
# cross_sectional_tax_loss_selling.MIN_ANCHOR_MONTH_TRADING_DAYS uses.
MIN_EVENT_MONTH_TRADING_DAYS = 15

# --- section 2.2 / 2.3: the grid --------------------------------------------

QemPerf = Literal["perf_h126", "perf_ptd"]
QEM_PERFS: tuple[QemPerf, ...] = ("perf_h126", "perf_ptd")

# [CKMR99] p.14 sorts on "a total return from CRSP from the end of June to day
# -1"; Table V's caption calls it "the previous six-months' return". 126
# sessions is half of the 252 the paper itself uses for its fund-level Table IV
# sort ("252 trading days (i.e. one year, give or take a day)", p.13), and 126
# sessions back from 31 December lands in the first days of July. DEVIATION,
# declared: the paper anchors on a CALENDAR date and this on a fixed session
# count, so that one definition serves every period type.
QEM_H126_SESSIONS = 126

QemArm = Literal["day0", "day1", "oval"]
QEM_ARMS: tuple[QemArm, ...] = ("day0", "day1", "oval")

# [CKMR99] p.15 sorts stocks "into performance-quintile portfolios"; Table V's
# sorts are quintiles too. This is the SOURCE's cut, not this project's usual
# deciles, and it is declared rather than searched.
QEM_RANK_FRACTION = 0.2

# [CKMR99] p.15, verbatim: "calculate the equal-weighted average of r_s,y,d,t
# for all d and t within each portfolio."
QEM_LEG_WEIGHTING = "equal"

# The event is ONE session. There is no holding axis; a longer hold would be
# holding a prediction about a window that has already closed.
QEM_HOLDING_DAYS = 1

# The signal function reads exactly ONE row (the formation row) of a
# precomputed panel, so it needs no lookback window at all.
QEM_SIGNAL_LOOKBACK_ROWS = 1

QEM_SPEC_CEILING = 18

# --- the denominator --------------------------------------------------------

# Running one pre-declared 18-definition grid on TWO universes makes the set of
# results from which a maximum could be reported 18 x 2 = 36. This is
# cross_sectional_small_mid_cap.py section 2's own derivation, applied here; it
# is arithmetic, not conservatism, and it is passed to
# screen_cross_sectional_universe explicitly for BOTH universes so the number
# the DSR uses is the number the pre-registration states.
UNIVERSE_MULTIPLIER = 2
QEM_N_TRIALS = UNIVERSE_MULTIPLIER * QEM_SPEC_CEILING

assert QEM_N_TRIALS == 36, (
    "the pre-registration declares n_local = 36 (18 specs x 2 universes); this module computes "
    f"{QEM_N_TRIALS}. The two must agree — a drift silently changes the DSR denominator."
)

# --- section 7 of the pre-registration: costs -------------------------------

# S&P 600 one-way flat cost per unit of gross notional traded. NOT invented
# here: it is cross_sectional_small_mid_cap.SMALL_CAP_COST_BPS, already
# pre-declared and used for this exact universe. Restated by value rather than
# imported so this module does not drag that family's import-time assertions
# in; the test file asserts the two are equal so they cannot drift silently.
SMALL_CAP_COST_BPS = 15.0

# D'Avolio (2002) general-collateral rate on the SHORT LEG alone, converted to
# the config's gross-notional basis by
# borrow_cost.financing_bps_for_long_short_book. Charged for consistency with
# every other long/short family here, and DECLARED IRRELEVANT rather than
# dressed up as diligence: at a one-day hold 34 bps/yr is under 0.01bp. That is
# also why there is no borrow ladder in this family — a ladder on a quantity
# that cannot move the answer is decoration. The cost ladder below is the one
# that matters.
QEM_GC_SHORT_LEG_BPS_PER_YEAR = 34.0

# Pre-declared turnover-cost ladder (pre-registration section 7). NOT new
# trials: the same grid and the same denominator, re-scored on different
# returns. 0.0 exists to separate "the mechanism is absent" from "the mechanism
# is untradeable" and IS NOT A RESULT THIS FAMILY MAY BE JUDGED ON.
QEM_COST_MULTIPLIERS: tuple[float, ...] = (0.0, 1.0, 2.0)

# Calendar days of price history fetched BEFORE the requested screening start.
# The longest window a formation reads is 126 SESSIONS, which is ~183 calendar
# days; 400 is that plus generous slack. Formations never occur in the padding
# (config.formation_start pins them), so no formation can predate point-in-time
# membership coverage.
QEM_PRICE_PADDING_CALENDAR_DAYS = 400

VALIDATED_EDGE_BAR = 0.95
SCREENING_FLOOR = 0.50


# ============================================================================
# the event schedule
# ============================================================================


@dataclass(frozen=True)
class EventDates:
    """One period-end event, as up to four real rows of the loaded price index.

    Never a constructed calendar date: `d0` is whatever session the index
    actually ends that month on, `d_minus_1` the row before it, `d1` the row
    after and `d2` the one after that. `d1`/`d2` are None only for an event at
    the very end of the loaded window.

    `d2` is not a trading day for any arm — it exists because the harness
    charges a formation's turnover on that formation's FIRST REALIZATION DAY,
    so the LIQUIDATION charge for a book that goes flat at the close of d(1)
    lands on d(2). An event's realized profit and loss is not complete without
    it (see arm_pnl_window)."""

    period: QemPeriod
    year: int
    month: int
    d_minus_1: pd.Timestamp
    d0: pd.Timestamp
    d1: pd.Timestamp | None
    d2: pd.Timestamp | None


def event_schedule(index: pd.DatetimeIndex, period: QemPeriod) -> tuple[list[EventDates], list[str]]:
    """(events, skipped) for one period type over the loaded index.

    `skipped` carries "YYYY-MM" for every calendar month of the right kind that
    was NOT usable — either truncated by the data window (fewer than
    MIN_EVENT_MONTH_TRADING_DAYS rows) or with no session before its own last
    one inside the index. Callers surface it; nothing is silently clamped."""
    months = PERIOD_MONTHS[period]
    events: list[EventDates] = []
    skipped: list[str] = []
    if len(index) == 0:
        return events, skipped
    positions = pd.Series(np.arange(len(index)), index=index)
    for year in sorted({int(y) for y in index.year}):
        for month in months:
            rows = index[(index.year == year) & (index.month == month)]
            if len(rows) < MIN_EVENT_MONTH_TRADING_DAYS:
                if len(rows) > 0:
                    skipped.append(f"{year}-{month:02d}")
                continue
            d0 = rows[-1]
            i0 = int(positions.loc[d0])
            if i0 == 0:
                skipped.append(f"{year}-{month:02d}")
                continue
            events.append(
                EventDates(
                    period=period,
                    year=year,
                    month=month,
                    d_minus_1=index[i0 - 1],
                    d0=d0,
                    d1=index[i0 + 1] if i0 + 1 < len(index) else None,
                    d2=index[i0 + 2] if i0 + 2 < len(index) else None,
                )
            )
    return events, skipped


def _last_session_before(index: pd.DatetimeIndex, boundary: pd.Timestamp) -> pd.Timestamp | None:
    """The last row of `index` STRICTLY BEFORE `boundary`, or None.

    "Strictly before" is the right reading of "the price a position carries
    into a period": 1 January, 1 April and so on are rarely trading days, and
    the base of a period-to-date return is the last close before the period
    opened."""
    position = int(index.searchsorted(boundary, side="left")) - 1
    if position < 0:
        return None
    return index[position]


def period_open_boundary(event: EventDates) -> pd.Timestamp:
    """The calendar instant at which the ending period OPENED — the boundary
    `perf_ptd`'s base close is taken strictly before.

    year_end       1 January of the event year   (calendar-year-to-date)
    quarter_end    1 January / 1 April / 1 July  (quarter-to-date)
    month_placebo  the 1st of the event month    (month-to-date)
    """
    if event.period == "year_end":
        return pd.Timestamp(year=event.year, month=1, day=1)
    if event.period == "quarter_end":
        quarter_first_month = 3 * ((event.month - 1) // 3) + 1
        return pd.Timestamp(year=event.year, month=quarter_first_month, day=1)
    if event.period == "month_placebo":
        return pd.Timestamp(year=event.year, month=event.month, day=1)
    raise ValueError(f"unknown period {event.period!r}")


# ============================================================================
# the signal panels
# ============================================================================


@dataclass
class QemPanel:
    """One (period, arm, perf) triple's point-in-time signal panel, plus
    everything needed to audit it without re-running the build.

    `frame` is NaN everywhere except the formation rows this arm actually
    trades: d(-1) for `day0`, d(0) for `day1`, and BOTH for `oval` (with the
    sign flipped on the second). That is the entire content of this family's
    calendar structure."""

    period: QemPeriod
    arm: QemArm
    perf: QemPerf
    frame: pd.DataFrame
    events: list[EventDates]
    skipped_months: list[str]
    n_finite_by_event: dict[pd.Timestamp, int]

    @property
    def key(self) -> str:
        return f"{self.period}_{self.arm}_{self.perf}"


def perf_series(
    close: pd.DataFrame, event: EventDates, perf: QemPerf
) -> pd.Series | None:
    """PERF for one event, or None if the loaded index does not reach back far
    enough.

    Both windows END at the close of d(-1) and never later, which is what makes
    the panel value on d(-1) readable at that formation and the value on d(0)
    free of d(0)'s own return (section 2.4).

    perf_h126  close[d(-1)] / close[126 sessions earlier] - 1
    perf_ptd   close[d(-1)] / close[last session before the period opened] - 1
    """
    index = close.index
    end_position = int(index.searchsorted(event.d_minus_1, side="left"))
    if end_position >= len(index) or index[end_position] != event.d_minus_1:
        return None
    if perf == "perf_h126":
        start_position = end_position - QEM_H126_SESSIONS
        if start_position < 0:
            return None
        start = index[start_position]
    elif perf == "perf_ptd":
        found = _last_session_before(index, period_open_boundary(event))
        if found is None or found >= event.d_minus_1:
            return None
        start = found
    else:
        raise ValueError(f"unknown perf window {perf!r}")

    base = close.loc[start]
    final = close.loc[event.d_minus_1]
    base = base.where(np.isfinite(base) & (base > 0.0))
    final = final.where(np.isfinite(final))
    return (final / base) - 1.0


def build_qem_panel(
    close: pd.DataFrame, *, period: QemPeriod, arm: QemArm, perf: QemPerf
) -> QemPanel:
    """One (period, arm, perf) panel, aligned to `close` exactly.

    POINT-IN-TIME CORRECTNESS, structurally: every value written into the frame
    comes from perf_series, whose window ends at the close of d(-1). A value on
    the d(-1) row therefore reads only its own day and earlier, and a value on
    the d(0) row reads only strictly earlier days. The consuming signal function
    reads exactly ONE row, at the formation timestamp the harness hands it, and
    the harness has already truncated its view to rows <= that timestamp. Both
    halves are pinned by tests."""
    index = close.index
    frame = pd.DataFrame(np.nan, index=index, columns=close.columns, dtype=float)
    events, skipped = event_schedule(index, period)

    used: list[EventDates] = []
    n_finite: dict[pd.Timestamp, int] = {}
    for event in events:
        signal = perf_series(close, event, perf)
        if signal is None:
            skipped.append(f"{event.year}-{event.month:02d}")
            continue
        values = signal.to_numpy()
        if arm in ("day0", "oval"):
            frame.loc[event.d_minus_1] = values
        if arm in ("day1", "oval"):
            frame.loc[event.d0] = -values
        used.append(event)
        n_finite[event.d0] = int(np.isfinite(values).sum())

    return QemPanel(
        period=period,
        arm=arm,
        perf=perf,
        frame=frame,
        events=used,
        skipped_months=sorted(set(skipped)),
        n_finite_by_event=n_finite,
    )


def build_all_qem_panels(close: pd.DataFrame) -> dict[str, QemPanel]:
    """All 18 (period, arm, perf) panels the grid is built from."""
    panels: dict[str, QemPanel] = {}
    for period in QEM_PERIODS:
        for arm in QEM_ARMS:
            for perf in QEM_PERFS:
                panel = build_qem_panel(close, period=period, arm=arm, perf=perf)
                panels[panel.key] = panel
    return panels


def signal_qem(history: CrossSectionalData, *, panel: pd.DataFrame) -> pd.Series:
    """The formation date's row of a bound panel, restricted to the eligible
    columns the harness put in the view.

    WHY THE PANEL IS BOUND INTO THE CLOSURE rather than read off
    CrossSectionalData.fundamental_signal: this family carries EIGHTEEN panels
    and the harness carries exactly one such field. Binding is the established
    pattern for that (cross_sectional_tax_loss_selling.signal_tax_loss,
    cross_sectional_nport_flow, cross_sectional_asset_growth's SIC panel), and
    its look-ahead argument is stated rather than inherited: this function reads
    ONE row, at the view's own last (formation) timestamp, and the panel
    builder's contract is that the value on that row was computed only from
    closes at or before d(-1).

    fundamental_signal is still required on every spec because it is what
    supplies the formation timestamp and the eligible column set here."""
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "signal_qem needs CrossSectionalData.fundamental_signal for the formation timestamp "
            "and the eligible column set; the spec must set requires_fundamental_signal=True."
        )
    formation_ts = frame.index[-1]
    if formation_ts not in panel.index:
        return pd.Series(np.nan, index=frame.columns, dtype=float)
    row = panel.loc[formation_ts].reindex(frame.columns).astype(float)
    return row.where(np.isfinite(row))


# ============================================================================
# the grid
# ============================================================================


def spec_id(period: QemPeriod, arm: QemArm, perf: QemPerf) -> str:
    return f"qem_{period}_{arm}_{perf}"


def build_qem_family(panels: Mapping[str, QemPanel]) -> list[CrossSectionalSpec]:
    """The 18 pre-declared specs, bound to their concrete panels.

    The panels are runtime DATA. The GRID — three period types, three arms, two
    ranking windows, and the count of 18 — is fixed in the module constants
    above and in the pre-registration, and is never a searched axis. All 18 are
    screened in ONE pass per universe so sigma_sr (the sibling-Sharpe dispersion
    the DSR benchmark is built from) is taken across the whole declared family
    rather than within a slice."""
    specs: list[CrossSectionalSpec] = []
    for period in QEM_PERIODS:
        for arm in QEM_ARMS:
            for perf in QEM_PERFS:
                key = f"{period}_{arm}_{perf}"
                if key not in panels:
                    raise ValueError(f"no panel supplied for {key}")
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=spec_id(period, arm, perf),
                        family=QEM_FAMILY,
                        citation=QEM_CITATION,
                        signal_fn=partial(signal_qem, panel=panels[key].frame),
                        lookback_days=QEM_SIGNAL_LOOKBACK_ROWS,
                        holding_days=QEM_HOLDING_DAYS,
                        portfolio="long_short",
                        rank_fraction=QEM_RANK_FRACTION,
                        requires_fundamental_signal=True,
                        leg_weighting=QEM_LEG_WEIGHTING,
                    )
                )
    assert len(specs) == QEM_SPEC_CEILING == 18, (
        f"quarter-end-marking built {len(specs)} definitions; the declared ceiling is "
        f"{QEM_SPEC_CEILING} and the pre-registration declared exactly 18. All three must agree — "
        "a drift silently changes this family's DSR denominator."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.leg_weighting == QEM_LEG_WEIGHTING for s in specs)
    assert all(s.rank_fraction == QEM_RANK_FRACTION for s in specs)
    assert all(s.holding_days == QEM_HOLDING_DAYS for s in specs)
    assert all(s.cohort_formation_days is None for s in specs)
    assert all(s.requires_fundamental_signal for s in specs)
    return specs


def sleeve_scale(holding_days: int = QEM_HOLDING_DAYS) -> int:
    """How many staggered sleeves the harness runs for this family — ALWAYS 1.

    Mirrors run_cross_sectional_backtest's own n_sleeves arithmetic
    (holding_days // cadence, floored at 1) with cadence == holding_days
    because cohort_formation_days is None. It is 1, so unlike
    cross_sectional_tax_loss_selling.py NOTHING reported by the harness needs
    de-scaling: the daily returns, the cost drags and the annualized figures are
    all the real book's. A test pins this against the harness rather than
    assuming it."""
    return max(1, holding_days // holding_days)


def memoized_membership(base: MembershipFn) -> MembershipFn:
    """A PURE-FUNCTION CACHE over a point-in-time membership gate.

    Not a semantic change and not a substitute for the real gate: it calls
    `base` and returns exactly what `base` returns, memoized on (ticker, date).
    It exists because holding_days=1 makes EVERY trading day a formation date —
    ~2,900 dates x 18 specs x up to ~800 tickers — and every one of those
    re-asks the same (ticker, date) questions the previous spec already asked."""
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

# These two mirror cross_sectional_tax_loss_selling's exported versions of the
# same name, deliberately re-stated rather than imported: that module's import
# graph pulls in its own family-size assertions and an unrelated grid, and a
# DSR ladder should not depend on another family being importable. The
# arithmetic is identical and the test file pins it against the same committed
# artifact.


def policy_d_denominators(n_local: int = QEM_N_TRIALS) -> list[int]:
    """The N values a Policy D report must cover, ascending and deduplicated:
    dsr_n_trials(n_local), n_specs_clustered, raw_pooled_distinct_trials.

    The lowest tier is dsr_n_trials(n_local), NOT n_local itself: dsr_n_trials
    returns max(family grid size, pooled effective N), which is the denominator
    screen_cross_sectional_universe actually deflates at. DSR is strictly
    decreasing in N, so three points BRACKET every N between them."""
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
class EventStats:
    """The statistic a reader of this family should weigh most heavily
    (pre-registration section 9).

    The Sharpe machinery reports ~2,900 daily observations per spec, of which
    all but a handful are exact zeros — the book is flat on every session that
    is not adjacent to a period end. The EFFECTIVE independent sample is the
    number of EVENTS: ~11 year-ends and ~33 quarter-ends on the S&P 500, ~6 and
    ~18 on the S&P 600, against ~88 and ~48 placebo month-ends. Compounding
    each event's own realized window into ONE number and taking a t-statistic on
    THOSE is the honest small-sample view.

    The window is ENTRY TO EXIT, including the settlement session that carries
    the liquidation charge (arm_pnl_window), so these numbers are net of the
    whole round trip the pre-registration's section 7 arithmetic counts — not
    of the entry alone."""

    n_events: int
    event_returns: list[float]
    event_dates: list[str]
    mean: float
    std: float
    naive_t: float
    hit_rate: float


def arm_exposed_dates(event: EventDates, arm: QemArm) -> list[pd.Timestamp]:
    """The sessions an arm's book is actually EXPOSED on, for ONE event.

    day0  d(0) alone      — formed at the close of d(-1), held one day.
    day1  d(1) alone      — formed at the close of d(0), held one day.
    oval  d(0) and d(1)   — formed at d(-1), flipped at d(0), flat after d(1).
    """
    if arm == "day0":
        return [event.d0]
    if arm == "day1":
        return [] if event.d1 is None else [event.d1]
    if arm == "oval":
        return [] if event.d1 is None else [event.d0, event.d1]
    raise ValueError(f"unknown arm {arm!r}")


def arm_pnl_window(event: EventDates, arm: QemArm) -> list[pd.Timestamp]:
    """Every session whose realized daily return belongs to ONE event's profit
    and loss — the exposed sessions PLUS the settlement session that carries
    the liquidation charge.

    WHY THE EXTRA SESSION IS NOT PADDING. cross_sectional.py charges a
    formation's turnover on that formation's FIRST REALIZATION DAY. The
    formation that takes this family's book back to flat happens at the close
    of the arm's LAST EXPOSED SESSION, so its charge — the exit half of the
    round trip the pre-registration's section 7 arithmetic counts — lands on
    the NEXT session, on which the book is flat and the daily return is
    therefore exactly minus that charge (gross 0, financing 0 on a flat book).
    Compounding only the exposed sessions would report an entry-cost-only
    number and would systematically flatter every arm, including the placebo
    the section 6 override is decided on.

    day0  [d(0), d(1)]
    day1  [d(1), d(2)]
    oval  [d(0), d(1), d(2)]
    An event missing any of its own sessions (the loaded window ends first)
    contributes no window at all rather than a truncated one."""
    exposed = arm_exposed_dates(event, arm)
    if not exposed:
        return []
    settlement = event.d1 if arm == "day0" else event.d2
    if settlement is None:
        return []
    return [*exposed, settlement]


def event_returns(
    replay: CrossSectionalBacktestResult, panel: QemPanel
) -> EventStats:
    """Per-event compounded NET return, read straight off the replay's realized
    daily series over each event's own entry-to-exit window.

    Computed from the KNOWN event calendar rather than from the formation
    records so that the arm's economic window (which for `oval` spans two
    formations, and for every arm spans one settlement session past the last
    exposed day — see arm_pnl_window) is what gets compounded. sleeve_scale()
    is 1 for this family (section 6), so no de-scaling factor appears anywhere
    here — and a test pins that it really is 1.

    Because these windows cover every session on which this family's book is
    either exposed or being charged, and the book is flat and free on every
    other session, the per-event returns account for the WHOLE daily series.
    A test pins that against the compounded series rather than asserting it."""
    daily = replay.daily_returns
    returns: list[float] = []
    dates: list[str] = []
    for event in panel.events:
        wanted = arm_pnl_window(event, panel.arm)
        window = [ts for ts in wanted if ts in daily.index]
        if not wanted or len(window) != len(wanted):
            continue
        compounded = float(np.prod(1.0 + daily.loc[window].to_numpy()) - 1.0)
        returns.append(compounded)
        dates.append(event.d0.date().isoformat())
    n = len(returns)
    if n == 0:
        return EventStats(0, [], [], float("nan"), float("nan"), float("nan"), float("nan"))
    array = np.asarray(returns, dtype=float)
    mean = float(array.mean())
    std = float(array.std(ddof=1)) if n >= 2 else float("nan")
    naive_t = float(mean / std * np.sqrt(n)) if n >= 2 and std > 0.0 else float("nan")
    return EventStats(
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
    preservation score, and the per-event view.

    preservation_score lives here rather than in an optional later pass on
    purpose — this project has twice shipped a check and then skipped it for the
    next real decision. A metric applied when someone remembers is a decoration,
    not a check."""

    pattern_id: str
    universe: str
    period: str
    arm: str
    perf: str
    sharpe_annualized: float
    dsr_by_n: dict[int, float | None]
    preservation: dict[str, float | int | bool | None]
    events: EventStats
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
    """One pre-declared cost arm: the whole grid re-scored under one changed
    turnover charge. NOT new trials — the DSR denominator is unchanged, only
    the returns the DSR is computed on."""

    key: str
    description: str
    multiplier: float
    sharpe_by_pattern: dict[str, float]
    dsr_by_pattern: dict[str, dict[int, float | None]]
    event_mean_by_pattern: dict[str, float]


@dataclass
class QuintileProfile:
    """Fidelity check F1 (pre-registration section 8): the direct analogue of
    [CKMR99] Figures 2A-2C.

    At every event the eligible cross-section is sorted into five PERF
    quintiles and each quintile's mean d(0) return, mean d(1) return and mean
    OVAL (d(0) minus d(1)) is averaged over events. Bucket 0 is the LOSER
    quintile, bucket 4 the WINNER quintile. A DIAGNOSTIC computed from the same
    price data and the same panels — no new specs, no new trials."""

    period: str
    perf: str
    n_events: int
    day0_by_quintile: list[float]
    day1_by_quintile: list[float]
    oval_by_quintile: list[float]
    universe_day0: float
    universe_day1: float
    spearman_quintile_vs_oval: float
    note: str


@dataclass
class DummyRegression:
    """A [CKMR99]-shaped dummy regression: one dependent series on a named set
    of period dummies plus an intercept. Coefficients in BASIS POINTS (or in
    raw units where the dependent variable is a slope), two-sided p-values in
    PERCENT, exactly as the paper's own tables report them."""

    label: str
    dependent: str
    n_observations: int
    coefficients: dict[str, float]
    p_values_pct: dict[str, float]
    units: str
    note: str


@dataclass
class QemUniverseResult:
    """Everything one universe's screening pass produced."""

    universe: str
    results: list[CrossSectionalScreeningResult]
    evaluations: list[SpecEvaluation]
    cost_arms: list[SensitivityArm]
    quintile_profiles: list[QuintileProfile]
    dummy_regressions: list[DummyRegression]
    universe_size: int
    missing_price_data: list[str]
    formation_start: date
    window_end: date
    events_by_period: dict[str, list[str]]
    skipped_months: dict[str, list[str]]
    coverage_by_event: dict[str, int]
    sigma_sr: float | None
    cost_model: str
    cost_bps: float
    financing_bps_per_year: float
    half_spread_calibration: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class QemScreeningSummary:
    """The whole build: both universes, one shared denominator."""

    universes: list[QemUniverseResult]
    n_trials: int
    denominators: list[int]

    def all_evaluations(self) -> list[SpecEvaluation]:
        return [e for u in self.universes for e in u.evaluations]

    def verdict(self, threshold: float = VALIDATED_EDGE_BAR) -> tuple[str, str]:
        """(verdict, best pattern_id) under Policy D's two-tier rule across BOTH
        universes, on the BASELINE cost arm, computed by
        registration_scorecard.policy_d_verdict rather than reimplemented here
        so the run report and the scorecard cannot disagree.

        The section 6 overrides (placebo, quarter-end asymmetry) are applied by
        the runner's report on top of this, and can only make it worse."""
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
            policy_d_verdict(dsr_by_n=best.dsr_by_n, threshold=threshold, n_local=self.n_trials),
            f"{best.universe}/{best.pattern_id}",
        )

    def placebo_override_triggered(self, tolerance: float = 0.5) -> tuple[bool, str]:
        """Pre-registration section 6, override (i), computed rather than
        eyeballed.

        True when the best `month_placebo` spec's per-event mean return has the
        SAME SIGN as the best real (year_end / quarter_end) spec's and is at
        least `tolerance` times its magnitude — "comparable magnitude" made
        explicit at the only threshold this project has to declare. One-sided:
        it can only make the verdict worse."""
        real = [e for e in self.all_evaluations() if e.period != "month_placebo"]
        placebo = [e for e in self.all_evaluations() if e.period == "month_placebo"]
        if not real or not placebo:
            return (False, "no comparable real/placebo pair")
        best_real = max(real, key=lambda e: e.sharpe_annualized)
        best_placebo = max(placebo, key=lambda e: e.sharpe_annualized)
        r = best_real.events.mean
        p = best_placebo.events.mean
        if not (np.isfinite(r) and np.isfinite(p)):
            return (False, "per-event mean unavailable on one side")
        same_sign = (r > 0 and p > 0) or (r < 0 and p < 0)
        comparable = abs(p) >= tolerance * abs(r)
        detail = (
            f"best real {best_real.universe}/{best_real.pattern_id} per-event mean {r:+.5f} "
            f"(Sharpe {best_real.sharpe_annualized:+.4f}); best placebo "
            f"{best_placebo.universe}/{best_placebo.pattern_id} per-event mean {p:+.5f} "
            f"(Sharpe {best_placebo.sharpe_annualized:+.4f}); same sign={same_sign}, "
            f"|placebo| >= {tolerance:g}x|real|={comparable}"
        )
        return (bool(same_sign and comparable), detail)


# ============================================================================
# F1: the quintile dose-response
# ============================================================================


def quintile_profile(
    close: pd.DataFrame,
    panel: QemPanel,
    is_member: MembershipFn,
    *,
    n_buckets: int = 5,
) -> QuintileProfile:
    """Mean d(0) return, d(1) return and OVAL by PERF quintile, averaged over
    events — fidelity check F1.

    At each event the eligible cross-section (point-in-time member on d(-1),
    finite close on d(-1), finite PERF) is split into `n_buckets` equal-count
    buckets by PERF. Bucket 0 is the LOSER quintile, bucket n-1 the WINNER
    quintile. Returns are simple close-to-close, EQUAL-WEIGHTED within bucket,
    matching [CKMR99] p.15 ("the equal-weighted average of r_s,y,d,t ... within
    each portfolio"). The equal-weighted eligible universe's own d(0) and d(1)
    means are reported beside them.

    [CKMR99] p.15's prediction: "The in-between quintiles are in between, in
    exact order" — a MONOTONE profile, with the winner quintile's OVAL highest.
    """
    index = close.index
    daily = close.pct_change(fill_method=None)
    day0_sums = np.zeros(n_buckets, dtype=float)
    day1_sums = np.zeros(n_buckets, dtype=float)
    universe_day0 = 0.0
    universe_day1 = 0.0
    n_events = 0

    for event in panel.events:
        if event.d1 is None or event.d0 not in index or event.d1 not in index:
            continue
        perf = perf_series(close, event, panel.perf)
        if perf is None:
            continue
        close_row = close.loc[event.d_minus_1]
        d_minus_1_day = event.d_minus_1.date()
        eligible = [
            t
            for t in close.columns
            if np.isfinite(perf.get(t, np.nan))
            and np.isfinite(close_row.get(t, np.nan))
            and is_member(t, d_minus_1_day)
        ]
        if len(eligible) < n_buckets * 2:
            continue
        r0 = daily.loc[event.d0, eligible]
        r1 = daily.loc[event.d1, eligible]
        universe_day0 += float(r0.mean(skipna=True))
        universe_day1 += float(r1.mean(skipna=True))
        ordered = perf.reindex(eligible).sort_values(kind="mergesort")
        for bucket, positions in enumerate(np.array_split(np.arange(len(ordered)), n_buckets)):
            if len(positions) == 0:
                continue
            names = list(ordered.index[positions])
            day0_sums[bucket] += float(r0.reindex(names).mean(skipna=True))
            day1_sums[bucket] += float(r1.reindex(names).mean(skipna=True))
        n_events += 1

    if n_events == 0:
        return QuintileProfile(
            period=panel.period,
            perf=panel.perf,
            n_events=0,
            day0_by_quintile=[],
            day1_by_quintile=[],
            oval_by_quintile=[],
            universe_day0=float("nan"),
            universe_day1=float("nan"),
            spearman_quintile_vs_oval=float("nan"),
            note="no event had a usable cross-section",
        )

    day0 = (day0_sums / n_events).tolist()
    day1 = (day1_sums / n_events).tolist()
    oval = [a - b for a, b in zip(day0, day1, strict=True)]
    ranks = np.arange(n_buckets, dtype=float)
    finite = np.isfinite(np.asarray(oval))
    spearman = (
        float(
            pd.Series(np.asarray(oval)[finite]).corr(pd.Series(ranks[finite]), method="spearman")
        )
        if finite.sum() >= 3
        else float("nan")
    )
    return QuintileProfile(
        period=panel.period,
        perf=panel.perf,
        n_events=n_events,
        day0_by_quintile=day0,
        day1_by_quintile=day1,
        oval_by_quintile=oval,
        universe_day0=universe_day0 / n_events,
        universe_day1=universe_day1 / n_events,
        spearman_quintile_vs_oval=spearman,
        note=(
            f"bucket 0 = LOSER quintile, bucket {n_buckets - 1} = WINNER quintile, ranked on "
            f"{panel.perf}; equal-weighted simple close-to-close returns averaged over "
            f"{n_events} {panel.period} events; a ticker missing a session is skipped for that "
            "session (mean over the survivors), a diagnostic-grade simplification the harness "
            "itself does not make"
        ),
    )


# ============================================================================
# F2 / F3: the aggregate dummy regressions
# ============================================================================


def period_dummies(index: pd.DatetimeIndex) -> pd.DataFrame:
    """[CKMR99] Table I's six dummies, on the loaded session index.

    Caption p.23, verbatim: "YENDd is 1 if d is the last trading day of
    December, YBEGd is 1 if YENDd-1 is 1, QENDd is 1 if d is the last trading
    day of March, June or September, and QBEGd is 1 if QENDd-1 is 1, MENDd is 1
    if d is the last day of January, February, April, May, July, August,
    October or November, and MBEGd is 1 if MENDd-1 is 1."

    Truncated months are excluded exactly as event_schedule excludes them, so
    the dummies and the tradeable specs see the same event set."""
    frame = pd.DataFrame(0.0, index=index, columns=["YEND", "YBEG", "QEND", "QBEG", "MEND", "MBEG"], dtype=float)
    for period, end_col, beg_col in (
        ("year_end", "YEND", "YBEG"),
        ("quarter_end", "QEND", "QBEG"),
        ("month_placebo", "MEND", "MBEG"),
    ):
        events, _ = event_schedule(index, period)  # type: ignore[arg-type]
        for event in events:
            frame.loc[event.d0, end_col] = 1.0
            if event.d1 is not None:
                frame.loc[event.d1, beg_col] = 1.0
    return frame


def _ols_with_pvalues(y: pd.Series, x: pd.DataFrame) -> tuple[dict[str, float], dict[str, float], int]:
    """OLS of y on [intercept, x], returning (coefficients, two-sided p-values
    in PERCENT, n). Uses statsmodels — already a project dependency and already
    the estimator every other regression-carrying family here uses — rather than
    a hand-rolled normal equation, so the standard errors are not reinvented."""
    import statsmodels.api as sm

    frame = pd.concat([y.rename("__y__"), x], axis=1).dropna()
    if len(frame) < len(x.columns) + 2:
        return ({}, {}, len(frame))
    design = sm.add_constant(frame[list(x.columns)], has_constant="add")
    fitted = sm.OLS(frame["__y__"], design).fit()
    coefficients = {str(k): float(v) for k, v in fitted.params.items()}
    p_values = {str(k): float(v) * 100.0 for k, v in fitted.pvalues.items()}
    return (coefficients, p_values, int(fitted.nobs))


def table_i_analogue(
    close: pd.DataFrame,
    market_close: pd.Series,
    eligible_by_date: Mapping[pd.Timestamp, list[str]],
) -> list[DummyRegression]:
    """F2: two regressions on [CKMR99] Table I's six dummies.

    (a) SPY's OWN daily return. NOT the paper's dependent variable and NOT a
        replication of anything — it answers whether there is a MARKET-WIDE
        period-end pattern a long/short book would sit inside. [CKMR99] p.5
        flags exactly this confound in [ZW97]'s numbers ("This is an odd fit
        with the price shifts of small-cap indices, which generally beat the
        market on both days in those years").
    (b) the EQUAL-WEIGHTED point-in-time universe's return MINUS SPY's. This is
        the closest available analogue of Table I's dependent variable (an
        equal-weighted fund index in excess of the S&P 500) and it is labelled
        an ANALOGUE, not a replication: an equal-weighted portfolio of index
        constituents is not a mutual fund, and no fund data exists here.
    """
    index = close.index
    dummies = period_dummies(index)
    market_ret = market_close.reindex(index).pct_change(fill_method=None)
    daily = close.pct_change(fill_method=None)

    equal_weighted = pd.Series(np.nan, index=index, dtype=float)
    for ts in index:
        names = eligible_by_date.get(ts)
        if not names:
            continue
        row = daily.loc[ts, [n for n in names if n in daily.columns]]
        if row.notna().any():
            equal_weighted.loc[ts] = float(row.mean(skipna=True))

    out: list[DummyRegression] = []
    for label, dependent, series, note in (
        (
            "F2a_market",
            "SPY daily total return",
            market_ret,
            (
                "NOT [CKMR99]'s dependent variable. A confound check: is there a market-wide "
                "period-end/period-start pattern at all?"
            ),
        ),
        (
            "F2b_equal_weighted_excess",
            "equal-weighted point-in-time universe return minus SPY return",
            equal_weighted - market_ret,
            (
                "ANALOGUE of Table I's dependent variable (equal-weighted fund index in excess of "
                "the S&P 500), NOT a replication — an equal-weighted basket of index constituents "
                "is not a mutual fund and no fund NAV data exists in this project."
            ),
        ),
    ):
        coefficients, p_values, n = _ols_with_pvalues(series, dummies)
        out.append(
            DummyRegression(
                label=label,
                dependent=dependent,
                n_observations=n,
                coefficients={k: v * 10_000.0 for k, v in coefficients.items()},
                p_values_pct=p_values,
                units="basis points",
                note=note,
            )
        )
    return out


def table_ii_analogue(
    close: pd.DataFrame, eligible_by_date: Mapping[pd.Timestamp, list[str]]
) -> DummyRegression:
    """F3: [CKMR99] Table II's design, at the stock level.

    Table II's caption p.24: "For each d we run a cross-sectional regression of
    funds' day d returns on their day d-1 return, saving the fitted slope
    coefficient bd. We then regress the bd on three dummy variables: YBEGd...
    QBEGd... MBEGd". Same here, with stocks in place of funds.

    DECLARED IN ADVANCE (pre-registration F3), because it will otherwise look
    like a failure: at the STOCK level the intercept is expected NEGATIVE, not
    positive, because daily stock returns reverse cross-sectionally (bid-ask
    bounce and short-term reversal) while daily FUND returns do not
    ([CKMR99]'s own ALL intercept is +0.0355). The testable part is whether the
    YBEG/QBEG dummies push the slope MORE negative than the baseline."""
    index = close.index
    daily = close.pct_change(fill_method=None)
    slopes = pd.Series(np.nan, index=index, dtype=float)
    previous: pd.Timestamp | None = None
    for ts in index:
        if previous is not None:
            names = eligible_by_date.get(ts)
            if names:
                cols = [n for n in names if n in daily.columns]
                pair = pd.DataFrame(
                    {"y": daily.loc[ts, cols], "x": daily.loc[previous, cols]}
                ).dropna()
                if len(pair) >= 30:
                    variance = float(pair["x"].var(ddof=1))
                    if variance > 0.0:
                        slopes.loc[ts] = float(pair["x"].cov(pair["y"]) / variance)
        previous = ts

    dummies = period_dummies(index)[["YBEG", "QBEG", "MBEG"]]
    coefficients, p_values, n = _ols_with_pvalues(slopes, dummies)
    return DummyRegression(
        label="F3_cross_sectional_lag_slope",
        dependent="daily cross-sectional OLS slope of stock day-d return on its own day-(d-1) return",
        n_observations=n,
        coefficients=coefficients,
        p_values_pct=p_values,
        units="raw slope (dimensionless)",
        note=(
            "[CKMR99] Table II, ALL funds: intercept +0.0355 (p 0.01%), YBEG -0.2418 (1.37%), "
            "QBEG -0.1407 (1.18%), MBEG -0.0239 (48.81%). The intercept here is EXPECTED to be "
            "negative because daily STOCK returns reverse cross-sectionally while daily FUND "
            "returns do not; the testable part is whether YBEG/QBEG push the slope further "
            "negative. Days with fewer than 30 paired observations are dropped."
        ),
    )


# ============================================================================
# the production entry point
# ============================================================================

QemUniverse = Literal["sp500", "sp600"]
QEM_UNIVERSES: tuple[QemUniverse, ...] = ("sp500", "sp600")

MARKET_TICKER = "SPY"


def default_qem_config(universe: QemUniverse, start: date) -> CrossSectionalConfig:
    """A fresh config per call — the harness writes formation_start onto
    whatever it is given, so a shared singleton would leak between runs.

    Costs are pre-registration section 7, and the two universes deliberately do
    NOT share a turnover model. The calibrated EDGE half-spread frame's LEVEL is
    pinned to a published S&P 500 median and spread_estimator's own docstring
    says so ("THIS NUMBER IS A UNIVERSE PROPERTY, NOT A CONSTANT OF NATURE"), so
    the S&P 600 run uses the flat SMALL_CAP_COST_BPS that
    cross_sectional_small_mid_cap.py already pre-declared for exactly that
    universe rather than a fabricated calibration target."""
    financing = borrow_cost.financing_bps_for_long_short_book(QEM_GC_SHORT_LEG_BPS_PER_YEAR)
    if universe == "sp500":
        return CrossSectionalConfig(
            cost_bps=DEFAULT_XS_COST_BPS,
            cost_model="edge_spread",
            formation_start=start,
            financing_bps_per_year=financing,
        )
    return CrossSectionalConfig(
        cost_bps=SMALL_CAP_COST_BPS,
        cost_model="flat_bps",
        formation_start=start,
        financing_bps_per_year=financing,
    )


def _universe_gate(
    universe: QemUniverse,
) -> tuple[Callable[[date, date], list[str]], MembershipFn, date]:
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


def _scaled_cost(
    data: CrossSectionalData, config: CrossSectionalConfig, multiplier: float
) -> tuple[CrossSectionalData, CrossSectionalConfig]:
    """The same data and config with the TURNOVER charge scaled.

    For "edge_spread" the per-ticker half-spread frame IS the charge, so it is
    scaled along with the flat fallback; scaling only cost_bps there would have
    moved the fallback and left the real cost untouched. For "flat_bps"
    cost_bps is the whole charge. financing_bps_per_year is deliberately NOT
    scaled — this ladder is about turnover, and the borrow charge is under
    0.01bp on a one-day hold either way."""
    from dataclasses import replace

    scaled_config = replace(config, cost_bps=config.cost_bps * multiplier)
    if config.cost_model != "edge_spread" or data.half_spread is None:
        return data, scaled_config
    return replace(data, half_spread=data.half_spread * multiplier), scaled_config


def _cost_arm(
    *,
    multiplier: float,
    data: CrossSectionalData,
    specs: Sequence[CrossSectionalSpec],
    config: CrossSectionalConfig,
    membership_fn: MembershipFn,
    panels: Mapping[str, QemPanel],
    denominators: Sequence[int],
) -> SensitivityArm:
    from app.services.research_lab.metrics import sharpe_ratio

    arm_data, arm_config = _scaled_cost(data, config, multiplier)
    replays = _replay_all(arm_data, specs, arm_config, membership_fn)
    sharpes = {
        pid: sharpe_ratio(r.daily_returns, periods_per_year=arm_config.periods_per_year)
        for pid, r in replays.items()
    }
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None
    dsr_by_pattern = {
        pid: dsr_across_denominators(
            sharpes[pid],
            replays[pid].daily_returns,
            sigma_sr,
            denominators,
            periods_per_year=arm_config.periods_per_year,
        )
        for pid in replays
    }
    event_means: dict[str, float] = {}
    for spec in specs:
        replay = replays.get(spec.pattern_id)
        if replay is None:
            continue
        period, arm, perf = _decode_pattern_id(spec.pattern_id)
        event_means[spec.pattern_id] = event_returns(
            replay, panels[f"{period}_{arm}_{perf}"]
        ).mean
    return SensitivityArm(
        key=f"cost_x{multiplier:g}",
        description=(
            f"turnover charge x{multiplier:g} "
            + (
                f"(calibrated half-spread frame x{multiplier:g}, flat fallback "
                f"{arm_config.cost_bps:.1f}bp)"
                if config.cost_model == "edge_spread"
                else f"(flat {arm_config.cost_bps:.1f}bp one-way)"
            )
            + ("  — BASELINE, the only arm the verdict is computed on" if multiplier == 1.0 else "")
            + (
                "  — DIAGNOSTIC ONLY, cannot pass anything (pre-registration section 7)"
                if multiplier == 0.0
                else ""
            )
        ),
        multiplier=multiplier,
        sharpe_by_pattern=sharpes,
        dsr_by_pattern=dsr_by_pattern,
        event_mean_by_pattern=event_means,
    )


def _decode_pattern_id(pattern_id: str) -> tuple[QemPeriod, QemArm, QemPerf]:
    """(period, arm, perf) back out of a pattern_id built by spec_id()."""
    for period in QEM_PERIODS:
        for arm in QEM_ARMS:
            for perf in QEM_PERFS:
                if spec_id(period, arm, perf) == pattern_id:
                    return period, arm, perf
    raise ValueError(f"unrecognised quarter-end-marking pattern_id {pattern_id!r}")


def run_qem_universe(
    universe: QemUniverse,
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    *,
    denominators: Sequence[int] | None = None,
    cost_multipliers: Sequence[float] = QEM_COST_MULTIPLIERS,
) -> QemUniverseResult:
    """Screen the full 18-spec grid on ONE universe.

    `start` must be at or after that universe's own MEMBERSHIP_DATA_START; a
    formation before it would silently see an empty cross-section because the
    membership gate answers False for everyone, which this project has already
    been bitten by once on a bond-ETF family."""
    get_universe_over, was_member, membership_start = _universe_gate(universe)
    if start < membership_start:
        raise ValueError(
            f"quarter-end-marking screening start {start.isoformat()} predates point-in-time "
            f"membership coverage for {universe} ({membership_start.isoformat()}) — a formation "
            "before that date would silently see an empty universe."
        )
    provider = provider if provider is not None else YFinanceProvider()
    config = default_qem_config(universe, start)
    denominators = list(denominators) if denominators is not None else policy_d_denominators()

    tickers = get_universe_over(start, end)
    padded_start = start - timedelta(days=QEM_PRICE_PADDING_CALENDAR_DAYS)
    frames, missing_price = provider.get_daily_ohlcv(tickers, padded_start, end)
    if not frames:
        raise ValueError(f"no price data resolved for the {universe} universe over the window")
    close = frames["close"]

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

    panels = build_all_qem_panels(close)
    specs = build_qem_family(panels)
    membership_fn = memoized_membership(was_member)

    data = CrossSectionalData(
        close=close,
        open=frames["open"],
        volume=frames["volume"],
        # Carrier for the formation timestamp and the eligible column set only
        # — every spec's real signal is bound into its closure (see signal_qem).
        # Any of the eighteen panels would serve identically; the year-end oval
        # h126 panel is chosen so the frame that IS structurally truncated by
        # the harness is a real one from the declared grid rather than a
        # synthetic placeholder.
        fundamental_signal=panels["year_end_oval_perf_h126"].frame,
        half_spread=half_spread,
    )

    results = screen_cross_sectional_universe(
        data, specs, config, membership_fn=membership_fn, n_trials_override=QEM_N_TRIALS
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
        period, arm, perf = _decode_pattern_id(result.pattern_id)
        evaluations.append(
            SpecEvaluation(
                pattern_id=result.pattern_id,
                universe=universe,
                period=period,
                arm=arm,
                perf=perf,
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
                events=event_returns(replay, panels[f"{period}_{arm}_{perf}"]),
                n_trading_days=result.n_trading_days,
                n_formations=result.n_formations,
                avg_names_per_leg=result.avg_names_per_leg,
                total_cost_drag=result.total_cost_drag,
                total_financing_drag=result.total_financing_drag,
                total_turnover=result.total_turnover,
                edge_flat_fallback_notional=result.edge_flat_fallback_notional,
                sleeve_scale=sleeve_scale(spec_by_id[result.pattern_id].holding_days),
            )
        )

    cost_arms = [
        _cost_arm(
            multiplier=float(multiplier),
            data=data,
            specs=specs,
            config=config,
            membership_fn=membership_fn,
            panels=panels,
            denominators=denominators,
        )
        for multiplier in cost_multipliers
    ]

    # F1, one profile per (period, perf): six in all, all diagnostics.
    quintile_profiles = [
        quintile_profile(close, panels[f"{period}_oval_{perf}"], membership_fn)
        for period in QEM_PERIODS
        for perf in QEM_PERFS
    ]

    # F2 / F3 need the point-in-time eligible set per session. Built once here
    # from the SAME memoized gate the specs use, so the diagnostics and the
    # tradeable specs cannot disagree about who was in the universe.
    eligible_by_date: dict[pd.Timestamp, list[str]] = {}
    for ts in close.index:
        day = ts.date()
        row = close.loc[ts]
        eligible_by_date[ts] = [
            t for t in close.columns if membership_fn(t, day) and np.isfinite(row[t])
        ]

    market_frames, market_missing = provider.get_daily_ohlcv(
        [MARKET_TICKER], padded_start, end
    )
    dummy_regressions: list[DummyRegression] = []
    if market_missing or not market_frames:
        warnings.append(
            f"{universe}: {MARKET_TICKER} price history did not resolve; the F2 Table I analogue "
            "was NOT computed rather than being computed against a substitute benchmark."
        )
    else:
        market_close = market_frames["close"][MARKET_TICKER].reindex(close.index)
        dummy_regressions.extend(table_i_analogue(close, market_close, eligible_by_date))
    dummy_regressions.append(table_ii_analogue(close, eligible_by_date))

    events_by_period: dict[str, list[str]] = {}
    skipped_months: dict[str, list[str]] = {}
    coverage: dict[str, int] = {}
    for period in QEM_PERIODS:
        panel = panels[f"{period}_oval_perf_h126"]
        events_by_period[period] = [e.d0.date().isoformat() for e in panel.events]
        skipped_months[period] = panel.skipped_months
        for ts, n in panel.n_finite_by_event.items():
            coverage[ts.date().isoformat()] = n
        if panel.skipped_months:
            warnings.append(
                f"{universe}: {period} months skipped for a truncated month or too little prior "
                f"history: {panel.skipped_months}"
            )

    return QemUniverseResult(
        universe=universe,
        results=results,
        evaluations=evaluations,
        cost_arms=cost_arms,
        quintile_profiles=quintile_profiles,
        dummy_regressions=dummy_regressions,
        universe_size=len(tickers),
        missing_price_data=missing_price,
        formation_start=start,
        window_end=end,
        events_by_period=events_by_period,
        skipped_months=skipped_months,
        coverage_by_event=dict(sorted(coverage.items())),
        sigma_sr=sigma_sr,
        cost_model=config.cost_model,
        cost_bps=config.cost_bps,
        financing_bps_per_year=config.financing_bps_per_year,
        half_spread_calibration=calibration_summary,
        warnings=warnings,
    )


def run_qem_screening(
    windows: Mapping[QemUniverse, tuple[date, date]],
    provider: YFinanceProvider | None = None,
) -> QemScreeningSummary:
    """THE production entry point: the same 18-spec grid on every universe in
    `windows`, sharing ONE denominator (QEM_N_TRIALS = 36).

    `windows` maps a universe key to its (start, end). Both universes are
    expected in a production run; a single-universe call is legitimate for tests
    and diagnostics but its DSR still carries the two-universe denominator,
    because the pre-registration declared both."""
    denominators = policy_d_denominators()
    universes = [
        run_qem_universe(universe, start, end, provider, denominators=denominators)
        for universe, (start, end) in windows.items()
    ]
    return QemScreeningSummary(
        universes=universes, n_trials=QEM_N_TRIALS, denominators=denominators
    )


__all__ = [
    "MARKET_TICKER",
    "MIN_EVENT_MONTH_TRADING_DAYS",
    "PERIOD_MONTHS",
    "PLACEBO_MONTHS",
    "QEM_ARMS",
    "QEM_CITATION",
    "QEM_COST_MULTIPLIERS",
    "QEM_FAMILY",
    "QEM_H126_SESSIONS",
    "QEM_HOLDING_DAYS",
    "QEM_LEG_WEIGHTING",
    "QEM_N_TRIALS",
    "QEM_PERFS",
    "QEM_PERIODS",
    "QEM_PRICE_PADDING_CALENDAR_DAYS",
    "QEM_RANK_FRACTION",
    "QEM_SPEC_CEILING",
    "QEM_UNIVERSES",
    "QUARTER_END_MONTHS",
    "SCREENING_FLOOR",
    "SMALL_CAP_COST_BPS",
    "UNIVERSE_MULTIPLIER",
    "VALIDATED_EDGE_BAR",
    "YEAR_END_MONTHS",
    "DummyRegression",
    "EventDates",
    "EventStats",
    "QemPanel",
    "QemScreeningSummary",
    "QemUniverseResult",
    "QuintileProfile",
    "SensitivityArm",
    "SpecEvaluation",
    "arm_exposed_dates",
    "arm_pnl_window",
    "build_all_qem_panels",
    "build_qem_family",
    "build_qem_panel",
    "default_qem_config",
    "dsr_across_denominators",
    "event_returns",
    "event_schedule",
    "memoized_membership",
    "perf_series",
    "period_dummies",
    "period_open_boundary",
    "policy_d_denominators",
    "quintile_profile",
    "run_qem_screening",
    "run_qem_universe",
    "signal_qem",
    "sleeve_scale",
    "spec_id",
    "table_i_analogue",
    "table_ii_analogue",
]
