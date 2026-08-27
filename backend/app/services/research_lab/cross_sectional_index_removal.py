"""Index-removal rebound: a deliberately small (6-definition) EVENT-DRIVEN
family — long an S&P 500 deletion, short an equal-notional SPY hedge,
entered one trading day AFTER the removal's effective date and held for a
fixed horizon.

Like cross_sectional_patterns_d2.py and cross_sectional_fx.py this module
owns its family object, its n_trials denominator, and its never-pooled DSR
correction. UNLIKE both of them it does NOT run on
cross_sectional.screen_cross_sectional_universe, and the reason is
structural rather than stylistic — see WHY THIS FAMILY NEEDS ITS OWN
REPLAY LOOP below. What it does reuse is everything downstream and
sideways of the formation loop, unmodified: metrics.sharpe_ratio,
deflated_sharpe.compute_deflated_sharpe, and — from cross_sectional.py
itself — _resolve_leg_weights (so "equal" and "inverse_vol" here are
LITERALLY the harness's own leg-weighting modes, concentration cap and
whole-leg fallback included), _leg_weighted_return (the
drop-a-missing-name-and-renormalize convention), _compute_delisting_
positions plus DEFAULT_IMPUTED_DELISTING_RETURN (the Shumway imputation,
reused exactly as cross_sectional_patterns_d2.py opts into it, not
reimplemented), FINANCING_DAYS_PER_YEAR and MIN_REPLAY_TRADING_DAYS.

============================================================================
WHAT THIS IS NOT: THIS IS NOT "THE INDEX EFFECT"
============================================================================
Read this before quoting any number below, and before comparing anything
here to the published index-effect literature.

The classic S&P 500 index effect is an ANNOUNCEMENT-window phenomenon. S&P
announces a change, typically ~5 trading days before it takes effect;
index funds must trade at the effective close; arbitrageurs front-run that
known, dated, forced flow over the intervening days. Essentially every
headline figure in that literature — Harris & Gurel's +3.1% addition
pop, Lynch & Mendenhall's run-up, Chen/Noronha/Singal's deletion
asymmetry — is measured from the ANNOUNCEMENT date.

sp500_membership_history.py stores EFFECTIVE DATES ONLY. Verified directly
against the data rather than taken on trust: `_MEMBERSHIP_EVENTS` is a
tuple of (effective date, tickers added, tickers removed) triples derived
by diffing consecutive constituent snapshots in the fja05680/sp500 source
file, and there is no announcement-date field anywhere in that module —
not in the events, not in the intervals, not in the extension overlay.
There is no free source in this project that would supply one. The
textbook index-effect test therefore CANNOT BE RUN HERE, in any form, and
nothing below should be read as having run it.

What IS buildable from effective dates alone is the POST-EFFECTIVE
REBOUND, and that is exactly and only what this family tests: index funds
sell the deleted name at the effective close because their mandate says
so, not because they have a view on it; if that forced, price-insensitive
supply pushes the price below fundamental value, the overshoot should
partially reverse over the following weeks to months. The trade is
therefore entered strictly AFTER the forced flow has printed (see ENTRY
TIMING) and holds for a horizon long enough for a reversal to unfold.

============================================================================
THE HONEST PRIOR IS LOW, AND IT IS LOW FOR PUBLISHED REASONS
============================================================================
This family is not expected to work. Stating that up front is not false
modesty; it is the entire reason it was built as a fixed 6-definition
enumeration with a hard-asserted n_trials rather than as an open search.

 * Greenwood, R. & Sammon, M., "The Disappearing Index Effect" (Journal of
   Finance, 2025): the abnormal returns around S&P 500 additions and
   deletions have declined steadily and are statistically indistinguishable
   from zero in the post-2010 era. The proposed mechanism is that index
   demand is now met by a far deeper pool of liquidity providers and by
   pre-positioning, so the forced flow no longer moves price enough to
   overshoot.
 * Bennett, B., Stulz, R. M. & Wang, Z., "Does joining the S&P 500 index
   hurt firms?" (Journal of Financial Economics, 2023): independently
   documents that the announcement-window premium associated with index
   inclusion has essentially vanished in recent decades.

This family's entire usable sample (see below) lives in 2015-2026 — i.e.
ENTIRELY inside the era both papers identify as the one in which the
effect is gone. A positive result here would be a finding that contradicts
two well-identified recent papers on their own sample period, which is
exactly the kind of result that should be disbelieved by default and is
why the DSR correction below is computed against the full pre-declared
family and never against whichever spec happened to win.

The older literature that motivates testing the DELETION side specifically:
 * Harris, L. & Gurel, E., "Price and Volume Effects Associated with
   Changes in the S&P 500 List" (Journal of Finance, 1986): the original
   price-pressure hypothesis — index-driven demand moves price temporarily
   and the move reverses within about two weeks.
 * Shleifer, A., "Do Demand Curves for Stocks Slope Down?" (Journal of
   Finance, 1986): the competing permanent-demand-curve reading of the same
   events, under which there is no reversal to trade at all. The two papers
   disagree precisely about whether this family's hypothesis exists.
 * Lynch, A. W. & Mendenhall, R. R., "New Evidence on Stock Price Effects
   Associated with Changes in the S&P 500 Index" (Journal of Business,
   1997): documents a significant PARTIAL REVERSAL after the effective
   date, which is the specific post-effective window this family trades.
 * Chen, H., Noronha, G. & Singal, V., "The Price Response to S&P 500 Index
   Additions and Deletions: Evidence of Asymmetry and a New Explanation"
   (Journal of Finance, 2004): finds the response ASYMMETRIC — addition
   gains are permanent, whereas DELETION losses are substantially reversed.
   This asymmetry is why this family trades deletions rather than additions
   and why it is long-only on the event name.

============================================================================
ENTRY TIMING: NEVER THE EFFECTIVE CLOSE
============================================================================
Entry is at the close of the FIRST TRADING DAY STRICTLY AFTER the effective
date (REMOVAL_ENTRY_OFFSET_TRADING_DAYS = 1), and the first realized return
is the day after that.

Entering at the effective-date close instead would be a category error, not
a small optimism. That close IS the index's own forced-selling print: it is
the price at which every index fund is transacting its mandated sale, and
the S&P 500 closing auction on a rebalance date is one of the largest
concentrated liquidity events in US equities. Buying there does not exploit
the forced flow — it supplies the other side of it at the price the flow
itself sets, which is the trade the liquidity providers who make that
market are already competing to do. The hypothesis under test is that the
price the forced flow left behind is too LOW and reverts afterwards; the
position must therefore be established after that price exists, not into
its formation. Enforced structurally in build_removal_event_book, which
derives the entry row as (last row <= effective date) + 1 and asserts the
resulting entry date is strictly later than the effective date.

============================================================================
WHY THIS FAMILY NEEDS ITS OWN REPLAY LOOP
============================================================================
screen_cross_sectional_universe was read in full before this decision was
made, and it does not fit — not awkwardly, but structurally, in four
independent ways, any one of which would be disqualifying:

 1. IT IS GATED ON MEMBERSHIP, AND EVERY NAME HERE IS A NON-MEMBER BY
    CONSTRUCTION. The harness's eligibility test is
    `is_member(t, formation_day) and price is finite` — that gate is the
    load-bearing survivorship-bias defense its whole module docstring is
    about. A removed name is, on every single day this family would hold
    it, NOT a member. was_member answers False for all of them, forever
    after the effective date. The harness would report
    "no_eligible_universe" and raise EmptyEligibleUniverseError. Passing
    fixed_universe_membership() to route around that would be exactly the
    misuse that function's own docstring forbids in bold ("It is NOT a
    substitute for was_member on EQUITIES").
 2. ITS FORMATION SCHEDULE IS PERIODIC; REMOVALS ARE NOT. The harness
    forms every `holding_days` trading days (`range(start, n-1,
    holding_days)`). Index removals arrive on 62 irregular dates clustered
    around quarterly rebalances plus ad-hoc merger closings. Every event
    has its own entry date and its own exit date; there is no shared
    formation date to rank on.
 3. THERE IS NOTHING TO RANK. The harness's core operation is
    select_leg_tickers: score a cross-section, take the top and bottom
    rank_fraction. Here every eligible name carries the identical
    hypothesis ("this name was just deleted"). There is no cross-sectional
    score, no decile, no short leg drawn from a ranking — and
    min_names_per_leg=5 would silently discard every date on which fewer
    than five names were concurrently in a hold.
 4. THE SHORT LEG IS A FIXED BENCHMARK, NOT A RANKED LEG. Every position
    is long-one-name / short-SPY. SPY is not an S&P 500 constituent and
    could not enter the harness's eligible set at all.

So the formation loop is new. It is also the ONLY thing that is new:
everything the harness does that is genuinely general — leg weighting and
its concentration cap, missing-name renormalization, Shumway delisting
imputation, calendar-day financing accrual, the Sharpe and the DSR — is
imported and called, not reimplemented. The alternative (bending a
periodic cross-sectional ranker into an irregular event study by feeding
it a fake signal and a fake membership function) would have produced a
module whose numbers no reader could reason about.

============================================================================
FAMILY SIZE — 6, FIXED AND ASSERTED BEFORE ANY RUN
============================================================================
3 holding periods {63, 126, 252 trading days} x 2 leg weightings {equal,
inverse_vol} = 6. REMOVAL_N_TRIALS is asserted against the built list in
_build_index_removal_family, so a size drift is a loud import-time failure
rather than a silent change to every future run's n_trials denominator. 6
is (barely) above deflated_sharpe.MIN_TRIALS_FOR_DSR (5), so unlike D2 the
DSR correction proper does compute for this family.

The two leg weightings are the harness's own, reached through
cross_sectional._resolve_leg_weights — not a new scheme. "equal" gives
every concurrently-held event the same share. "inverse_vol" weights each
event by 1 / its own trailing realized volatility measured at ITS entry
date, through the identical normalize-then-cap-at-MAX_WEIGHT_MULTIPLE
machinery, with the identical whole-leg fallback when any member's basis
is unusable. The fallback here degrades to EQUAL weight rather than to
magnitude weight, because the "signal" this family hands _leg_weights is a
constant (every event carries the same hypothesis, so there is no
magnitude to weight by) and _leg_weights' own documented tie behavior is
to fall back to equal weight. That is the harness's stated contract being
used, not worked around, and the fallback count is reported.

NO HOLD SHORTER THAN 63 TRADING DAYS — AND THE SCOUT'S REASON FOR THAT WAS
WRONG, SO HERE IS THE REAL ONE. A feasibility scout argued against a short
hold on the grounds that "the cost is paid too often relative to a
multi-week decay horizon". That argument is imported from the PERIODIC
rebalancing families and does not transfer to this structure. In an
event-driven book each removal is entered exactly once and exited exactly
once, so the round-trip cost per event is REMOVAL_TOTAL_ROUND_TRIP_BPS
whether the hold is 21 days or 252 — shortening the hold does not multiply
it. If anything the cost/horizon relationship runs the OTHER way here,
because the only time-scaling cost (SPY borrow, SPY_BORROW_BPS_PER_YEAR)
makes LONG holds more expensive, not short ones: ~7.5bp at 63 days, ~15bp
at 126, ~30bp at 252.

The real reasons a sub-63-day variant is excluded:
 * The fixed 18.4bp is amortized over less realized return at a shorter
   hold, so it is a larger drag as a FRACTION of whatever is earned — the
   defensible half of the scout's intuition, restated correctly.
 * A shorter hold buys no new data. The sample is 97 events on 59
   independent clusters no matter how long each is held; a fourth horizon
   would spend one of six pre-declared trials, and pay the corresponding
   multiple-comparisons penalty on all six, without adding one event.
 * The hypothesis is a weeks-to-months overshoot decay. 63 trading days
   (~3 months) is already the SHORT end of the window Lynch & Mendenhall
   and Chen/Noronha/Singal measure post-effective reversal over. A 21-day
   hold would cut the reversal off partway through rather than testing a
   different hypothesis about it.

============================================================================
COSTS — MEASURED HERE, NOT INHERITED
============================================================================
Every figure in this section was derived on 2026-08-27 from the real
yfinance panel this family screens, not carried over from a scouting note.

 * STOCK LEG, REMOVAL_STOCK_ROUND_TRIP_BPS = 16.4bp round trip. Derived
   two ways that agree. (a) Liquidity: median post-removal dollar volume
   across the 97 entered events, measured over each event's first 63
   trading days of holding, is $59.5M/day (quartiles $45.4M / $96.7M;
   exactly ONE event below $10M/day). These are liquid mid-caps, not
   micro-caps — index deletion does not make a name untradeable.
   (b) Price impact: the Amihud (2002) illiquidity ratio ILLIQ =
   mean(|r_t| / dollar volume_t), measured over the same windows, has a
   cross-event median of 2.52e-10. Under Amihud's own daily
   price-response scaling, a one-way trade of X% of a name's median ADV
   costs 0.5 * ILLIQ * (X * ADV), which gives a median one-way impact of
   0.87bp at 1% of ADV, 4.36bp at 5%, and 8.72bp at 10%. Adding a 3bp
   effective half-spread and doubling for the round trip: 9.5bp at 2% of
   ADV, 14.7bp at 5%, 23.4bp at 10%. The 16.4bp used here therefore
   corresponds to roughly 6% of ADV participation — inside the measured
   range and mildly conservative relative to a 5%-participation execution.
   Amihud, Y., "Illiquidity and stock returns: cross-section and
   time-series effects" (Journal of Financial Markets, 2002).
 * SPY LEG, REMOVAL_SPY_ROUND_TRIP_BPS = 2.0bp round trip. An ASSUMPTION,
   not a measurement, and deliberately a conservative one: SPY's quoted
   spread is routinely one cent on a several-hundred-dollar price (well
   under 0.5bp round trip), so 2bp leaves room for commission and slippage
   several times over. Flagged as assumed rather than measured because
   this project has no quote data to measure a spread from.
 * SPY BORROW, SPY_BORROW_BPS_PER_YEAR = 30.0bp/yr on the short SPY
   notional. Also an ASSUMPTION. SPY is general collateral and among the
   easiest-to-borrow instruments in existence; 25-35bp/yr is the ordinary
   retail/prime range. Accrued on CALENDAR days elapsed via
   cross_sectional.FINANCING_DAYS_PER_YEAR (365), exactly as the harness
   accrues its own financing and for the reason documented there — a
   weekend costs three days of borrow, and a full year costs the full
   stated rate.

Total per event: 18.4bp round trip, charged in full on the event's FIRST
REALIZED DAY. Charging the exit leg up front rather than on the exit day is
deliberate and conservative: it means a name that delists mid-hold has
already paid a full exit it never got to execute, and it mirrors the
harness's own convention of landing a formation's whole turnover charge on
its first realization day.

A GENUINE STRUCTURAL ADVANTAGE OVER EVERY OTHER EQUITY FAMILY HERE, worth
stating because this project's other equity modules all carry the opposite
disclosure: cross_sectional.py's module docstring warns at length that its
short legs route to distressed, hard-to-borrow names whose real borrow cost
the backtest cannot see. This family has no such exposure. The single names
are all LONG; the only short is SPY. Short availability is a non-issue and
the borrow rate is observable. Whatever else is wrong with the numbers
below, undisclosed short-borrow optimism is not among them.

============================================================================
THE SAMPLE — RECOUNTED FROM THE DATA, NOT ASSUMED
============================================================================
Every number here was recomputed on 2026-08-27 and is reproduced at run
time by build_index_removal_sample_disclosure, so it stays true as the
data moves rather than rotting into a stale comment.

  235 event dates, 278 additions, 274 removals, 2015-01-27 .. 2026-06-30
  -31 removals dropped as ticker-RENAME artifacts (see below)
  = 243 candidate real removals
  -127 (52%) resolve NO yfinance price history at all
  -19 more resolve prices that do not cover their own membership interval
      (recycled tickers, e.g. yfinance's FB history restarting 2025-06-26)
  = 97 events actually ENTERED, on 62 distinct dates
  = 59 independent event clusters (dates grouped at >= 7 days apart)

Of the 97, 93 survive a full 63-day post-window, 89 a full 126-day, 81 a
full 252-day. Per the design, ALL 97 enter — surviving to a full window is
NOT an entry condition, because conditioning entry on later survival would
be look-ahead. A name that delists mid-hold is charged the Shumway imputed
return and the position closes; a name whose hold runs past the end of the
data simply has its hold truncated there.

THE 52% HOLE IS THE BIGGEST SINGLE CAVEAT, and its direction is NOT the
usual one. sp500_membership_history's KNOWN LIMITS already document that
~48% of departed members resolve nothing on yfinance; this family measures
52% on its own sample and the two agree. But unlike the other equity
families, most of that hole is NOT survivorship bias here — it is a
tradeability FACT. The overwhelming majority of those 127 (COV, SWY, PETM,
CFN, XLNX, CERN, ATVI, PXD, JNPR, CTLT, NLSN, ANSS, ...) were removed
BECAUSE they were acquired or taken private, meaning the security stopped
existing on or about the effective date. There was no post-effective
security to buy at effective+1. Excluding them is correct, not biased: a
strategy cannot hold a company that no longer trades.

The residual that IS a real bias, and is not closed: a minority of the 127
are distressed names that kept trading (OTC or on a downgraded listing)
which yfinance has simply lost — ENDP and DO are two identified examples.
Those names kept FALLING after removal rather than rebounding, so their
absence flatters this family in the ordinary optimistic direction. There is
no way to size that subset with free data, and closing it needs the
delisted-securities vendor already on this project's pending-paid list
(Norgate, CRSP, Sharadar). Disclosed, not closed.

THE SHUMWAY IMPUTATION NEVER FIRES ON THIS DATA, AND THAT IS A FINDING
RATHER THAN A REASSURANCE. IndexRemovalConfig.impute_delisting_returns
defaults to True and the machinery is wired in and unit-tested, but the
2026-08-27 production run charged the imputed return exactly ZERO times
across all 97 events and all three holds. Verified directly rather than
inferred: cross_sectional._compute_delisting_positions finds 0 of the 115
tickers that resolved any price data to have a series that ENDS before the
frame does. The cause is yfinance's failure mode — for a delisted name it
returns nothing at all, rather than a series that stops on the delisting
day. So a name that dies mid-hold does not appear here as a truncated
series to be imputed; it appears in the 127 that resolved no data and was
never entered.

The practical consequence must not be misread: the imputation is NOT
protecting this family's numbers, because there is nothing in the loaded
data for it to catch. The entire delisting bias lives in the 127 excluded
names, which the imputation cannot reach. It stays on because it is
correct, costs nothing, and would fire against a provider that truncates
rather than deletes — not because it has done any work here.

============================================================================
RENAME ARTIFACTS — THE FILTER, AND WHAT IT COSTS
============================================================================
sp500_membership_history is TICKER-keyed, so a pure symbol change reads as
a same-date removal plus addition (its own KNOWN LIMITS say so). Those
removals must not be traded: the company did not leave the index, and the
old symbol either stops trading or, worse, is later reused.

A naive "any date with both an add and a remove" rule is useless — 170 of
the 235 event dates have both, because that is what an ordinary index swap
looks like. This module uses two precise rules instead, both driven by data
already in that module rather than by a hand-copied list:

 RULE 1 (successor already a member). An addition of ticker S on date D is
 a symbol change if earliest_membership_date(S) predates D by more than
 REMOVAL_RENAME_MAX_ANNOUNCEMENT_LAG_DAYS (7), S is not in the base
 universe, and S was never removed before D. The earliest-membership date
 comes from _EARLIEST_MEMBERSHIP_OVERRIDES, the hand-verified rename
 correction layer that module already maintains — so this rule reads that
 module's own verified rename knowledge instead of duplicating it. The
 7-day threshold exists to exclude the five entries that module documents
 as 1-4 day announcement-vs-effective differences (HSIC, EQIX, NWS, CFG,
 FTV), which are not renames; the "never removed before" clause excludes
 genuine index RE-ENTRIES (DXC, FSLR, DD, DOW, KDP, EQT, PCG, SNDK), which
 are not renames either.
 RULE 2 (symbol round-trip). If R is removed on D while S is added on D,
 and later S is removed on D' while R is added back on D', both are symbol
 changes. This catches the one interior rename that module documents as
 uncorrected — Fiserv's FISV -> FI (2023-06-07) -> FISV (2025-11-11) —
 plus DD/DWDP, neither of which Rule 1 can see.

When Rule 1 fires, ALL removals on that date are dropped, not just the one
paired with the successor. That is deliberately conservative and it is not
free, so it was measured: the filter drops 31 removals across 24 dates, of
which only FIVE would otherwise have been enterable, and four of those five
(DD, BBT, FISV, PARA) are genuine renames that SHOULD be dropped. The cost
is therefore exactly ONE real event — Macy's (M), removed 2020-04-06,
collateral damage of the Arconic -> Howmet rename on that same date.

Losing that one event buys something real on the very same date: ARNC. When
Arconic Inc. was renamed HWM, the ARNC symbol was reused by the spun-off
Arconic Corp., which then traded independently until 2023. ARNC therefore
has continuous prices on both sides of 2020-04-06 and passes every
price-based check in this module — it is a recycled ticker that the
non-recycling filter CANNOT catch. Rule 1 removes it. One genuine event
lost to exclude one silently-wrong one is a trade worth making, and the
count is disclosed rather than buried.

RESIDUAL, not closed: a rename whose date also carries other genuine
removals AND whose successor is not in the override layer would be missed
entirely. No such case was found in this data, but the filter cannot prove
there is none.

============================================================================
KNOWN LIMITS BEYOND THE ABOVE
============================================================================
 * THE HEDGE IS BETA-1 SPY, NOT A MATCHED BENCHMARK. A just-deleted S&P
   500 name is by then a mid- or small-cap, frequently a high-beta
   distressed one. An equal-notional SPY short neutralizes broad market
   direction but leaves residual beta, size, and value exposure. That is
   the design as specified, and it keeps the construction transparent, but
   a positive result here would need to survive a beta-adjusted or
   mid-cap-benchmark hedge before it meant anything. That variant is NOT
   in this family — adding it would change the pre-declared family size.
 * SEVERELY OVERLAPPING HOLDS. 97 events on 59 independent clusters, held
   for up to 252 trading days each, over ~11.4 years. At the 252-day hold
   the book is a rolling average of roughly eight concurrent positions and
   consecutive daily returns share most of their constituents. The daily
   observation count that feeds the Sharpe and the DSR therefore vastly
   overstates the independent information available — the honest unit is
   the ~59 clusters. build_index_removal_sample_disclosure returns this as
   typed data, never only as a comment.
 * EVENT SOURCE IS THE VENDORED WINDOW. Events come from
   sp500_membership_history.vendored_events(), which deliberately ignores
   any runtime refresh extension. Harmless here and not an oversight: the
   last vendored removal is 2026-06-30 and the longest hold is 252 trading
   days, so no post-coverage removal could complete a full hold anyway.
 * FLAT DAYS ARE REAL RETURNS. Days on which no event is in a hold
   contribute exactly 0.0, because a strategy that only trades index
   deletions genuinely holds cash between them. The invested fraction is
   measured and reported per spec rather than hidden by dropping those
   days, which would inflate every Sharpe here. Measured: 81.8% invested
   at the 63-day hold, 98.9% at 126, 100.0% at 252.
 * DAILY RENORMALIZATION IS NOT CHARGED, SO COST IS UNDERSTATED. The book
   holds total notional 1.0 and re-weights as events enter and leave, so
   an event joining two others pushes the other two from 1/2 to 1/3 —
   a real trade this module charges nothing for. That is deliberately the
   harness's own stated convention (cross_sectional.py: "Leg weights are
   treated as re-set every day within a hold at zero cost"), kept for
   consistency, but it means the true cost is HIGHER than the reported
   drag. It does not change any conclusion below, and the direction is why:
   every correction here makes an already-negative result more negative, so
   this understatement cannot be masking an edge. It would matter if this
   family had produced a positive Sharpe; it did not.

============================================================================
WHAT THE 2026-08-27 PRODUCTION RUN FOUND — AN HONEST NEGATIVE
============================================================================
All six specs, not the best of them (start=2015-01-07, end=2026-08-27,
2,873 realized trading days, 97 events, 59 independent clusters):

    hold  weighting     Sharpe    PSR     DSR   invested
     126  equal         +0.039  0.552   0.402      98.9%
     126  inverse_vol   -0.041  0.446   0.303      98.9%
      63  equal         -0.074  0.401   0.265      81.8%
     252  inverse_vol   -0.096  0.373   0.241     100.0%
     252  equal         -0.104  0.363   0.233     100.0%
      63  inverse_vol   -0.225  0.225   0.129      81.8%

Five of six are NEGATIVE; the sixth is +0.039, which is indistinguishable
from zero. No DSR exceeds 0.41 against the n_trials=6 correction. The
inverse-vol weighting never fell back once (the basis resolved on every
day of every run), so the two weightings are a genuine comparison rather
than two names for the same thing — and it did not help.

Cross-checked by a completely separate route that shares no code with the
replay: a plain event study of buy-and-hold stock minus buy-and-hold SPY
over each event's window, no costs, no weighting, no book.

    hold   n   mean excess   median   t-stat   share positive
      63  97       +1.42%    -2.11%    +0.48            43.3%
     126  97       +4.45%    -0.80%    +1.13            49.5%
     252  97       -0.68%    -4.12%    -0.13            44.3%

It agrees with the replay on sign and ordering (126 best, 252 worst) and
adds the detail the Sharpe hides: every MEDIAN is negative while the means
at 63 and 126 are positive, i.e. the typical deleted name UNDERperforms
after removal and the positive mean is a handful of large winners. Fewer
than half the events are positive at every horizon. That is the opposite
shape from a broad rebound. And the largest t-stat is 1.13 — computed
treating all 97 events as independent, which they are not (59 clusters),
so even that overstates itself.

The honest read: this is a clean negative, and it is exactly what
Greenwood & Sammon (2025) and Bennett/Stulz/Wang (2023) predict for a
post-2010 sample. Nothing here should be forwarded to validation. The one
result a reader might be tempted by — 126-day equal-weighted at +0.039 —
is the single positive number in six pre-declared trials, has a DSR of
0.40, has a NEGATIVE median event return underneath it, and sits in the
era the literature says the effect is gone. That is what a null looks like,
not a weak signal.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    DEFAULT_IMPUTED_DELISTING_RETURN,
    FINANCING_DAYS_PER_YEAR,
    MIN_REPLAY_TRADING_DAYS,
    _compute_delisting_positions,
    _leg_weighted_return,
    _resolve_leg_weights,
)
from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.sp500_membership_history import (
    _BASE_UNIVERSE,
    MEMBERSHIP_DATA_START,
    earliest_membership_date,
    vendored_events,
)

logger = logging.getLogger(__name__)

# --- the family's fixed axes ---------------------------------------------

# Trading days each event is held after entry. See the module docstring's
# "NO HOLD SHORTER THAN 63 TRADING DAYS" section for why the short end is
# 63 and why the scout's stated reason for that floor was wrong.
REMOVAL_HOLDING_DAYS: tuple[int, ...] = (63, 126, 252)

# The harness's OWN leg-weighting modes (cross_sectional._resolve_leg_
# weights), not new schemes -- "equal" needs no data and can never fall
# back; "inverse_vol" reads the per-event basis built by
# build_inverse_vol_basis below and falls back for the whole book when any
# active event's basis is unusable.
REMOVAL_LEG_WEIGHTINGS: tuple[str, ...] = ("equal", "inverse_vol")

# 3 x 2. Asserted against the built list in _build_index_removal_family, so
# a drift is an import-time failure rather than a silent change to the DSR
# denominator of every future run.
REMOVAL_N_TRIALS = len(REMOVAL_HOLDING_DAYS) * len(REMOVAL_LEG_WEIGHTINGS)

REMOVAL_CITATION = (
    "Harris & Gurel, 'Price and Volume Effects Associated with Changes in the S&P 500 List' "
    "(Journal of Finance, 1986); Shleifer, 'Do Demand Curves for Stocks Slope Down?' (Journal of "
    "Finance, 1986); Lynch & Mendenhall, 'New Evidence on Stock Price Effects Associated with "
    "Changes in the S&P 500 Index' (Journal of Business, 1997); Chen, Noronha & Singal, 'The Price "
    "Response to S&P 500 Index Additions and Deletions' (Journal of Finance, 2004); Greenwood & "
    "Sammon, 'The Disappearing Index Effect' (Journal of Finance, 2025)"
)

REMOVAL_FAMILY_NAME = "index_removal_rebound"

# --- execution conventions ------------------------------------------------

# The market-neutral hedge leg. Equal notional, short, against every long.
REMOVAL_HEDGE_TICKER = "SPY"

# Trading days AFTER the effective date at which the position is
# established. 1, and never 0 -- entering at the effective close would mean
# transacting into the index's own forced-selling auction rather than after
# it. See the module docstring's ENTRY TIMING section.
REMOVAL_ENTRY_OFFSET_TRADING_DAYS = 1

# --- costs (see the module docstring's COSTS section for the derivation) --

# Round trip on the single-name leg. Derived from this family's own real
# panel: Amihud (2002) ILLIQ median 2.52e-10 over the entered events'
# post-removal windows, which puts a 5%-of-ADV round trip at 14.7bp and a
# 10%-of-ADV round trip at 23.4bp once a 3bp effective half-spread is
# included. 16.4bp sits between them, at roughly 6% of ADV.
REMOVAL_STOCK_ROUND_TRIP_BPS = 16.4

# Round trip on the SPY leg. ASSUMED, not measured (this project has no
# quote data): SPY's one-cent quoted spread on a several-hundred-dollar
# price is well under 0.5bp round trip, so 2bp is several times
# conservative and absorbs commission.
REMOVAL_SPY_ROUND_TRIP_BPS = 2.0

# What one event actually pays, entry and exit together, charged once on
# its first realized day.
REMOVAL_TOTAL_ROUND_TRIP_BPS = REMOVAL_STOCK_ROUND_TRIP_BPS + REMOVAL_SPY_ROUND_TRIP_BPS

# Borrow on the SHORT SPY notional only -- the long single names borrow
# nothing. ASSUMED: SPY is general collateral and among the easiest
# instruments in existence to borrow; 25-35bp/yr is the ordinary range.
# Accrued on CALENDAR days via FINANCING_DAYS_PER_YEAR (365), reusing the
# harness's own convention and constant rather than a second one.
REMOVAL_SPY_BORROW_BPS_PER_YEAR = 30.0

# --- sample-construction thresholds --------------------------------------

# A rename successor's corrected earliest-membership date must precede its
# addition date by MORE than this for Rule 1 to fire. 7 days excludes the
# five entries sp500_membership_history documents as 1-4 calendar-day
# announcement-vs-effective differences (HSIC, EQIX, NWS, CFG, FTV), which
# are not renames. Calibrated against that module's own documented data,
# not guessed.
REMOVAL_RENAME_MAX_ANNOUNCEMENT_LAG_DAYS = 7

# The non-recycling test. A removed ticker must have at least
# REMOVAL_MIN_PRE_REMOVAL_OBS valid closes in the REMOVAL_PRE_REMOVAL_
# WINDOW_DAYS trading days ending at the effective date. This is the
# "intersect fetched prices with the membership interval" discipline
# sp500_membership_history's KNOWN LIMITS require of every caller, made
# mechanical: a recycled ticker (FB restarting 2025-06-26, SBNY 2024-08-15,
# INFO 2024-10-10) has NO prices during its own real membership, so it
# fails this and is dropped. 15 of 21 (not all 21) tolerates ordinary
# holiday and halt gaps in an otherwise real series.
REMOVAL_PRE_REMOVAL_WINDOW_DAYS = 21
REMOVAL_MIN_PRE_REMOVAL_OBS = 15

# The entry row must be within this many CALENDAR days of the effective
# date. Guards the other end of the recycling problem: a ticker whose
# prices resume years after its removal would otherwise produce an "entry"
# in a completely different era. An ordinary entry is 1-4 calendar days
# after the effective date (a Friday effective date entering Monday); 10
# absorbs a holiday-extended weekend without admitting anything else.
REMOVAL_MAX_ENTRY_GAP_CALENDAR_DAYS = 10

# Two event dates closer together than this are one cluster, not two
# independent observations -- index removals bunch on quarterly rebalance
# dates, so a naive event count double-counts a single rebalance's worth of
# information. 7 calendar days (one week) separates distinct rebalance
# episodes without merging genuinely unrelated ad-hoc merger removals.
REMOVAL_EVENT_CLUSTER_MIN_GAP_DAYS = 7

# Trailing window for the inverse-vol basis. 63 trading days (~1 quarter)
# matches this project's existing "1 quarter" convention
# (cross_sectional_patterns.HOLDING_HORIZONS_DAYS, D2_COHORT_FORMATION_DAYS)
# and is short enough that a name's volatility is measured on its recent,
# post-decline regime rather than its long-gone large-cap past.
REMOVAL_VOL_WINDOW_DAYS = 63
REMOVAL_VOL_MIN_PERIODS = 40

# Calendar padding fetched BEFORE the first event purely to warm up the
# pre-removal non-recycling window (21 trading days) and the inverse-vol
# basis (63 trading days, ~92 calendar days). 150 covers both with room for
# holiday clustering. No event may be ENTERED in the padding -- events come
# from the dated membership data, which starts well after it.
REMOVAL_PRICE_HISTORY_PADDING_CALENDAR_DAYS = 150


@dataclass(frozen=True)
class IndexRemovalSpec:
    """One pre-declared definition. Deliberately NOT a
    cross_sectional.CrossSectionalSpec: that type's required fields
    (signal_fn, lookback_days, rank_fraction, portfolio) have no meaning
    for an event-driven single-name-vs-benchmark trade, and filling them
    with placeholders to satisfy a type this family does not run on would
    be a lie about the strategy's shape. See the module docstring's WHY
    THIS FAMILY NEEDS ITS OWN REPLAY LOOP."""

    pattern_id: str
    family: str
    citation: str
    holding_days: int
    leg_weighting: (
        str  # "equal" | "inverse_vol" -- cross_sectional._resolve_leg_weights modes
    )


def _build_index_removal_family() -> list[IndexRemovalSpec]:
    """The full, fixed family: every (holding_days, leg_weighting) pair.
    pattern_ids encode both axes so a screening result names its own
    definition unambiguously."""
    specs: list[IndexRemovalSpec] = []
    for hold in REMOVAL_HOLDING_DAYS:
        for weighting in REMOVAL_LEG_WEIGHTINGS:
            specs.append(
                IndexRemovalSpec(
                    pattern_id=f"index_removal_rebound_h{hold}_{weighting}",
                    family=REMOVAL_FAMILY_NAME,
                    citation=REMOVAL_CITATION,
                    holding_days=hold,
                    leg_weighting=weighting,
                )
            )
    assert len(specs) == REMOVAL_N_TRIALS, (
        f"Index-removal family has {len(specs)} definitions, not the pre-declared "
        f"{REMOVAL_N_TRIALS} -- this family's entire point is being an exact, fixed enumeration of "
        "holding_days x leg_weighting (see module docstring); a size drift here silently changes "
        "n_trials for every future run."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), (
        "pattern_ids must be unique"
    )
    assert all(s.family == REMOVAL_FAMILY_NAME for s in specs)
    assert all(s.holding_days >= min(REMOVAL_HOLDING_DAYS) for s in specs)
    assert all(s.leg_weighting in REMOVAL_LEG_WEIGHTINGS for s in specs)
    assert {s.holding_days for s in specs} == set(REMOVAL_HOLDING_DAYS)
    assert {s.leg_weighting for s in specs} == set(REMOVAL_LEG_WEIGHTINGS)
    return specs


INDEX_REMOVAL_FAMILY: list[IndexRemovalSpec] = _build_index_removal_family()


@dataclass
class IndexRemovalConfig:
    """The MARKET this family's hypothesis is traded in, following the
    spec-vs-config split cross_sectional.CrossSectionalConfig already uses:
    a spec says what to hold and for how long, a config says what that
    costs. Every default is the disclosed, derived figure above; a caller
    who wants a sensitivity run overrides them here rather than editing
    constants."""

    stock_round_trip_bps: float = REMOVAL_STOCK_ROUND_TRIP_BPS
    spy_round_trip_bps: float = REMOVAL_SPY_ROUND_TRIP_BPS
    spy_borrow_bps_per_year: float = REMOVAL_SPY_BORROW_BPS_PER_YEAR
    # ON by default here, unlike the harness. cross_sectional.py keeps
    # Shumway imputation off so families predating the option stay
    # byte-identical; this family has no such history and its population is
    # exactly the adversely-selected one the option exists for -- names the
    # index just deleted, which delist mid-hold far more often than a
    # random constituent. Silently dropping one would flatter this family
    # specifically. Same reasoning cross_sectional_patterns_d2.py gives for
    # opting in.
    impute_delisting_returns: bool = True
    imputed_delisting_return: float = DEFAULT_IMPUTED_DELISTING_RETURN


@dataclass(frozen=True)
class RemovalEvent:
    """One S&P 500 deletion that survived the rename filter."""

    ticker: str
    effective_date: date


@dataclass(frozen=True)
class EnteredEvent:
    """A RemovalEvent that also had tradeable, non-recycled price data --
    i.e. one this family actually takes a position in. entry_position is
    the integer row of the close frame at whose close the position is
    established (strictly after effective_date, see ENTRY TIMING)."""

    ticker: str
    effective_date: date
    entry_position: int
    entry_date: date


def _rename_artifact_removals() -> tuple[set[date], set[tuple[str, date]]]:
    """(Rule-1 dates, Rule-2 (ticker, date) pairs) -- the ticker-rename
    artifacts that must never be traded. See the module docstring's RENAME
    ARTIFACTS section for both rules, the 7-day threshold's calibration,
    and the measured cost of Rule 1's date-level conservatism (one real
    event: Macy's, 2020-04-06)."""
    events = vendored_events()
    base = set(_BASE_UNIVERSE)

    first_removal: dict[str, date] = {}
    add_dates: dict[str, list[date]] = {}
    removal_dates: dict[str, list[date]] = {}
    for effective, added, removed in events:
        for ticker in removed:
            first_removal.setdefault(ticker, effective)
            removal_dates.setdefault(ticker, []).append(effective)
        for ticker in added:
            add_dates.setdefault(ticker, []).append(effective)

    # RULE 1: the addition on this date is a symbol change, because the
    # module's own hand-verified override layer already places the
    # successor's company in the index before it.
    rule1_dates: set[date] = set()
    for effective, added, _removed in events:
        for successor in added:
            earliest = earliest_membership_date(successor)
            if earliest is None or successor in base:
                continue
            prior = first_removal.get(successor)
            if prior is not None and prior < effective:
                continue  # a genuine index RE-ENTRY, not a rename
            if (effective - earliest).days > REMOVAL_RENAME_MAX_ANNOUNCEMENT_LAG_DAYS:
                rule1_dates.add(effective)

    # RULE 2: symbol round-trip -- R out / S in on D, then S out / R back
    # in on a later D'. Both removals are the same company changing symbol.
    rule2_pairs: set[tuple[str, date]] = set()
    for effective, added, removed in events:
        for gone in removed:
            for successor in added:
                for later in set(add_dates.get(gone, ())) & set(
                    removal_dates.get(successor, ())
                ):
                    if later > effective:
                        rule2_pairs.add((gone, effective))
                        rule2_pairs.add((successor, later))

    return rule1_dates, rule2_pairs


def list_index_removal_events() -> tuple[list[RemovalEvent], int]:
    """Every S&P 500 removal in the vendored point-in-time data that is not
    a ticker-rename artifact, plus how many removals the rename filter
    dropped.

    Source is vendored_events() rather than the live extension overlay --
    see the module docstring's KNOWN LIMITS on why that is harmless for
    this family (the newest vendored removal cannot complete a 252-day hold
    as it is)."""
    rule1_dates, rule2_pairs = _rename_artifact_removals()
    events: list[RemovalEvent] = []
    n_dropped = 0
    for effective, _added, removed in vendored_events():
        for ticker in removed:
            if effective in rule1_dates or (ticker, effective) in rule2_pairs:
                n_dropped += 1
                continue
            events.append(RemovalEvent(ticker=ticker, effective_date=effective))
    return events, n_dropped


def build_removal_event_book(
    close: pd.DataFrame, events: list[RemovalEvent]
) -> tuple[list[EnteredEvent], dict[str, int]]:
    """Turns removal events into the positions this family actually takes,
    dropping the ones no position could have been established in. Returns
    (entered events, {rejection reason: count}).

    THE ENTRY ROW, and the one invariant this function exists to enforce:
    entry_position is (last row at or before the effective date) + 1, so
    the entry close is strictly LATER than the effective close -- never the
    effective close itself, which is the index's own forced-selling print
    (see the module docstring's ENTRY TIMING section). That is asserted
    here rather than merely intended.

    The rejection reasons, all of which are tradeability facts rather than
    performance filters:
     * "no price data" -- the ticker resolved nothing at all. Overwhelmingly
       acquisitions and take-privates, where the security stopped existing
       at the effective date and there was nothing to buy the next day.
     * "no pre-removal prices" -- the ticker resolved prices that do NOT
       cover its own membership interval, i.e. a recycled ticker now
       belonging to a different company. This is the mechanical form of the
       membership-interval intersection sp500_membership_history's KNOWN
       LIMITS require of every caller.
     * "no price on entry day" / "entry gap too large" -- prices exist on
       both sides of the removal but not at the entry row, or resume only
       long afterwards.
     * "removal before price history" / "removal too recent" -- the event
       falls outside the loaded window's usable interior.

    Deliberately NOT a rejection reason: failing to survive to a full
    post-window. Conditioning entry on later survival would be look-ahead,
    so every event that can be entered IS entered and a mid-hold delisting
    is handled by the Shumway imputation instead."""
    index = close.index
    n = len(index)
    entered: list[EnteredEvent] = []
    rejected: dict[str, int] = {}

    def _reject(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    for event in events:
        if event.ticker not in close.columns:
            _reject("no price data")
            continue
        effective_ts = pd.Timestamp(event.effective_date)
        # Last loaded row at or before the effective date. side="right"
        # then -1 is the standard "last <= x" search, and it is what makes
        # the +1 below land strictly AFTER the effective date whether or
        # not the effective date is itself a trading day.
        at_or_before = (
            int(
                np.searchsorted(
                    index.values, effective_ts.to_datetime64(), side="right"
                )
            )
            - 1
        )
        if at_or_before < REMOVAL_PRE_REMOVAL_WINDOW_DAYS:
            _reject("removal before price history")
            continue
        entry_position = at_or_before + REMOVAL_ENTRY_OFFSET_TRADING_DAYS
        # Need at least one realization day after the entry close.
        if entry_position >= n - 1:
            _reject("removal too recent for any hold")
            continue

        series = close[event.ticker]
        window = series.iloc[
            at_or_before - REMOVAL_PRE_REMOVAL_WINDOW_DAYS + 1 : at_or_before + 1
        ]
        if int(window.notna().sum()) < REMOVAL_MIN_PRE_REMOVAL_OBS:
            _reject("no pre-removal prices (recycled ticker)")
            continue
        if not np.isfinite(series.iloc[entry_position]):
            _reject("no price on entry day")
            continue
        entry_date = index[entry_position].date()
        if (
            entry_date - event.effective_date
        ).days > REMOVAL_MAX_ENTRY_GAP_CALENDAR_DAYS:
            _reject("entry gap too large (prices resume long after removal)")
            continue

        assert entry_date > event.effective_date, (
            f"{event.ticker}: entry date {entry_date} is not strictly after the effective date "
            f"{event.effective_date} -- entering at the effective close would transact into the "
            "index's own forced-selling auction (see the module docstring's ENTRY TIMING section)."
        )
        entered.append(
            EnteredEvent(
                ticker=event.ticker,
                effective_date=event.effective_date,
                entry_position=entry_position,
                entry_date=entry_date,
            )
        )

    return entered, rejected


def build_inverse_vol_basis(close: pd.DataFrame) -> pd.DataFrame:
    """1 / trailing realized volatility per ticker, aligned to `close`
    exactly -- the per-event basis the "inverse_vol" specs weight the book
    by through cross_sectional._resolve_leg_weights.

    Same formula as cross_sectional_fx.build_inverse_vol_basis (a rolling
    ddof=1 standard deviation of daily returns, reciprocated, with
    non-finite results NaNed), restated here with this family's own window
    constant rather than imported, because that function bakes in the FX
    family's window and an equity module importing an FX module for a
    four-line rolling std would be worse coupling than the duplication.

    Point-in-time by construction: a rolling std at row i reads only rows
    <= i, and the replay reads each event's basis at ITS OWN ENTRY ROW, so
    no event is ever weighted by volatility measured after it was entered.

    A non-finite or zero volatility yields NaN rather than an infinite
    weight; _resolve_leg_weights treats any unusable basis value as grounds
    to fall back for the WHOLE book, and the replay counts how often that
    happened."""
    returns = close.pct_change(fill_method=None)
    vol = returns.rolling(
        REMOVAL_VOL_WINDOW_DAYS, min_periods=REMOVAL_VOL_MIN_PERIODS
    ).std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        basis = 1.0 / vol
    return basis.replace([np.inf, -np.inf], np.nan)


@dataclass
class IndexRemovalBacktestResult:
    status: str  # "ok" | "no_events" | "insufficient_history"
    daily_returns: pd.Series  # net of costs, one observation per realized trading day
    n_events_entered: int = 0
    n_events_delisted_mid_hold: int = 0
    total_cost: float = 0.0
    total_financing_cost: float = 0.0
    # Days on which at least one event was in a hold, over the length of
    # the realized series. A strategy that only trades index deletions
    # genuinely sits in cash between them; this says how much of the time
    # it was actually invested, so a reader can tell a flat Sharpe caused
    # by no edge from one caused by no exposure.
    n_invested_days: int = 0
    # How often "inverse_vol" weighting could not resolve a usable basis
    # for every concurrently-held event and fell back for the whole book
    # (see _resolve_leg_weights). Always 0 for an "equal" spec, which reads
    # no external frame and therefore can never fall back.
    n_weighted_days: int = 0
    n_weight_fallback_days: int = 0


def run_index_removal_backtest(
    close: pd.DataFrame,
    hedge: pd.Series,
    entered: list[EnteredEvent],
    spec: IndexRemovalSpec,
    config: IndexRemovalConfig,
    basis: pd.DataFrame | None = None,
) -> IndexRemovalBacktestResult:
    """One spec's full event-driven replay.

    THE LOOP, in one paragraph: every entered event opens a position of
    1.0 long its own name and 1.0 short the hedge at the close of its entry
    row, and closes it spec.holding_days trading days later (or at the end
    of the data, or on the day it delists). On each realized day the book
    is the set of currently-open events; their weights sum to 1.0 and are
    resolved by cross_sectional._resolve_leg_weights under spec.leg_
    weighting; the day's gross return is the weighted mean of the open
    names' returns MINUS the hedge's return, which is exactly
    sum_i w_i * (r_i - r_hedge) because the weights sum to one.

    Conventions, each matching the harness's documented one rather than
    inventing a parallel convention:
     * A name with no return on a day (a transient gap, not a delisting) is
       dropped from that day's weighted mean and the survivors renormalize
       -- cross_sectional._leg_weighted_return, called directly. If EVERY
       open name is missing, the day is flat rather than a naked hedge
       short.
     * The book is re-weighted daily at zero cost as events enter and
       leave, the same zero-cost-rebalancing convention the harness states
       for its own legs. The disclosed cost driver is per-event, not
       per-day.
     * An event's whole round-trip cost lands on its FIRST realized day,
       mirroring the harness landing a formation's turnover charge on its
       first realization day. Conservative: an event that delists mid-hold
       has already paid an exit it never executed.
     * Borrow accrues on CALENDAR days elapsed since the previous realized
       close, via FINANCING_DAYS_PER_YEAR (365), so a weekend costs three
       days -- the harness's own accrual rule and constant, for the reason
       documented there.
     * Shumway imputation (config.impute_delisting_returns, ON by default
       here) fires on the exact row cross_sectional._compute_delisting_
       positions identifies as a name's first PERMANENTLY missing day, and
       only for names actually open that day. The event then closes.

    Weights are resolved with a CONSTANT signal series. That is not a
    placeholder: every event in this family carries the identical
    hypothesis, so there is no magnitude to weight by, and _leg_weights'
    documented tie behavior (a leg whose members are exactly tied falls
    back to equal weight) is precisely the right degenerate case. It also
    makes the "inverse_vol" fallback degrade to equal weighting rather than
    to something arbitrary."""
    if spec.leg_weighting == "inverse_vol" and basis is None:
        raise ValueError(
            f"{spec.pattern_id} has leg_weighting='inverse_vol' but no inverse-vol basis was "
            "supplied. Without it every day would silently take the fallback and the run would "
            "report itself as inverse-vol weighted while being equal weighted throughout."
        )
    if not entered:
        return IndexRemovalBacktestResult(
            status="no_events", daily_returns=pd.Series(dtype=float)
        )

    index = close.index
    n = len(index)
    stock_returns = close.pct_change(fill_method=None)
    hedge_returns = hedge.reindex(index).pct_change(fill_method=None)

    round_trip_cost = (
        config.stock_round_trip_bps + config.spy_round_trip_bps
    ) / 10_000.0
    borrow_per_day = (
        config.spy_borrow_bps_per_year / 10_000.0
    ) / FINANCING_DAYS_PER_YEAR

    delisting_by_position: dict[int, list[str]] = {}
    if config.impute_delisting_returns:
        for ticker, position in _compute_delisting_positions(close).items():
            delisting_by_position.setdefault(position, []).append(ticker)

    # Per-event schedule. exit_position is inclusive: the last row on which
    # the event still contributes a return. Truncated at the data's end,
    # which is the backtest ending rather than the position closing -- the
    # same treatment the harness gives a hold that runs off its frame.
    open_at: dict[int, list[EnteredEvent]] = {}
    entry_basis: dict[tuple[str, date], float] = {}
    for event in entered:
        open_at.setdefault(event.entry_position, []).append(event)
        if basis is not None and event.ticker in basis.columns:
            entry_basis[(event.ticker, event.effective_date)] = float(
                basis[event.ticker].iloc[event.entry_position]
            )

    active: dict[str, EnteredEvent] = {}
    exit_position: dict[str, int] = {}
    first_realized: dict[str, int] = {}

    dates: list[pd.Timestamp] = []
    nets: list[float] = []
    total_cost = 0.0
    total_financing = 0.0
    n_invested_days = 0
    n_weighted_days = 0
    n_fallback_days = 0
    n_delisted = 0

    first_entry = min(e.entry_position for e in entered)
    if first_entry >= n - 1:
        return IndexRemovalBacktestResult(
            status="insufficient_history", daily_returns=pd.Series(dtype=float)
        )

    for j in range(first_entry + 1, n):
        # Events entered at the previous close start contributing today.
        for event in open_at.get(j - 1, ()):
            # A ticker removed twice with overlapping holds would otherwise
            # collide in the weight dict; the later event supersedes, and
            # the collision is logged rather than silently resolved.
            if event.ticker in active:
                logger.warning(
                    "%s: overlapping holds for %s (%s superseded by %s)",
                    spec.pattern_id,
                    event.ticker,
                    active[event.ticker].effective_date,
                    event.effective_date,
                )
            active[event.ticker] = event
            exit_position[event.ticker] = min(
                event.entry_position + spec.holding_days, n - 1
            )
            first_realized[event.ticker] = j

        if not active:
            dates.append(index[j])
            nets.append(0.0)
            continue

        tickers = sorted(active)
        day = stock_returns.iloc[j]
        delisting_today = delisting_by_position.get(j)
        if delisting_today:
            hit = [t for t in delisting_today if t in active]
            if hit:
                day = day.copy()
                for ticker in hit:
                    day[ticker] = config.imputed_delisting_return
                n_delisted += len(hit)

        signal = pd.Series(0.0, index=tickers, dtype=float)
        basis_row: pd.Series | None = None
        if spec.leg_weighting == "inverse_vol":
            basis_row = pd.Series(
                {
                    t: entry_basis.get((t, active[t].effective_date), np.nan)
                    for t in tickers
                },
                dtype=float,
            )
        weights, used_fallback = _resolve_leg_weights(
            tickers,
            signal,
            higher_is_stronger=True,
            leg_weighting=spec.leg_weighting,  # type: ignore[arg-type]
            market_cap=None,
            weight_basis=basis_row,
        )
        n_weighted_days += 1
        if used_fallback:
            n_fallback_days += 1

        long_return = _leg_weighted_return(day, weights)
        hedge_return = hedge_returns.iloc[j]
        if not np.isfinite(hedge_return):
            hedge_return = 0.0
        # Every open name missing today: flat, not a naked hedge short.
        if day.reindex(tickers).dropna().empty:
            gross = 0.0
            hedged = False
        else:
            gross = long_return - float(hedge_return)
            hedged = True

        cost_today = 0.0
        for ticker in tickers:
            if first_realized[ticker] == j:
                cost_today += weights[ticker] * round_trip_cost
        financing_today = 0.0
        if hedged and borrow_per_day:
            calendar_days = float((index[j] - index[j - 1]).days)
            financing_today = borrow_per_day * calendar_days

        net = gross - cost_today - financing_today
        total_cost += cost_today
        total_financing += financing_today
        n_invested_days += 1
        dates.append(index[j])
        nets.append(net)

        # Close anything whose hold ends today, plus anything that delisted.
        for ticker in list(active):
            if j >= exit_position[ticker] or (
                delisting_today and ticker in delisting_today
            ):
                del active[ticker]
                del exit_position[ticker]
                del first_realized[ticker]

    daily = pd.Series(nets, index=pd.DatetimeIndex(dates), dtype=float)
    return IndexRemovalBacktestResult(
        status="ok",
        daily_returns=daily,
        n_events_entered=len(entered),
        n_events_delisted_mid_hold=n_delisted,
        total_cost=total_cost,
        total_financing_cost=total_financing,
        n_invested_days=n_invested_days,
        n_weighted_days=n_weighted_days,
        n_weight_fallback_days=n_fallback_days,
    )


@dataclass
class IndexRemovalScreeningResult:
    pattern_id: str
    family: str
    citation: str
    holding_days: int
    leg_weighting: str
    n_events_entered: int
    n_events_delisted_mid_hold: int
    n_trading_days: int
    n_invested_days: int
    invested_fraction: float
    sharpe_annualized: float
    total_cost_drag: float
    total_financing_drag: float
    deflated_sharpe: DeflatedSharpeResult
    n_weighted_days: int = 0
    n_weight_fallback_days: int = 0


@dataclass(frozen=True)
class IndexRemovalSampleDisclosure:
    """The sample-size and independence caution as typed data, recomputed
    from the real data on every run rather than left as a module comment a
    caller could fail to read -- the same discipline
    cross_sectional_patterns_d2.D2IndependentWindowDisclosure applies to
    its own small-sample problem."""

    n_removals_total: int
    n_rename_artifacts_dropped: int
    n_candidate_removals: int
    n_entered: int
    rejected_by_reason: dict[str, int]
    n_distinct_event_dates: int
    n_independent_clusters: int
    first_event_date: date | None
    last_event_date: date | None
    text: str


def count_independent_event_clusters(event_dates: list[date]) -> int:
    """Distinct event dates grouped into clusters at
    REMOVAL_EVENT_CLUSTER_MIN_GAP_DAYS or more apart. Index removals bunch
    on quarterly rebalance dates, so counting raw events (or even raw
    dates) as independent observations double-counts a single rebalance
    episode's worth of information."""
    if not event_dates:
        return 0
    ordered = sorted(set(event_dates))
    clusters = 1
    previous = ordered[0]
    for current in ordered[1:]:
        if (current - previous).days >= REMOVAL_EVENT_CLUSTER_MIN_GAP_DAYS:
            clusters += 1
        previous = current
    return clusters


def build_index_removal_sample_disclosure(
    n_removals_total: int,
    n_rename_dropped: int,
    entered: list[EnteredEvent],
    rejected: dict[str, int],
) -> IndexRemovalSampleDisclosure:
    dates = [e.effective_date for e in entered]
    clusters = count_independent_event_clusters(dates)
    distinct = len(set(dates))
    candidates = n_removals_total - n_rename_dropped
    reasons = ", ".join(
        f"{k}: {v}" for k, v in sorted(rejected.items(), key=lambda kv: -kv[1])
    )
    text = (
        f"INDEX-REMOVAL SAMPLE DISCLOSURE -- read before trusting any Sharpe or DSR below. The "
        f"vendored point-in-time membership data contains {n_removals_total} removals; "
        f"{n_rename_dropped} are dropped as ticker-RENAME artifacts (see the module docstring's "
        f"RENAME ARTIFACTS section -- this filter is deliberately conservative at the DATE level and "
        f"costs exactly one genuine event, Macy's on 2020-04-06, to exclude the recycled ARNC ticker "
        f"on that same date), leaving {candidates} candidate real removals. Of those, only "
        f"{len(entered)} could actually be entered ({reasons}). The dominant rejection is 'no price "
        f"data', and most of it is a TRADEABILITY FACT rather than survivorship bias: those names "
        f"were removed because they were acquired or taken private, so no security existed to buy "
        f"one day later. The minority that were distressed names still trading OTC which yfinance "
        f"has lost (ENDP, DO) IS a real upward bias and is not closed here. Those {len(entered)} "
        f"events fall on {distinct} distinct dates and only {clusters} INDEPENDENT CLUSTERS (dates "
        f"grouped at >= {REMOVAL_EVENT_CLUSTER_MIN_GAP_DAYS} days apart), because index removals "
        f"bunch on quarterly rebalance dates. {clusters} is the honest unit of independent "
        f"information in every result below -- NOT the thousands of daily observations that feed the "
        f"Sharpe and the DSR, which at a 252-day hold are a rolling average of roughly eight "
        f"concurrent positions and share most of their constituents from one day to the next. This "
        f"is a SEPARATE caution from the DSR's own n_trials={REMOVAL_N_TRIALS} multiple-comparisons "
        f"correction; neither substitutes for the other. Finally, the entire sample lives inside the "
        f"post-2010 era in which Greenwood & Sammon (2025) and Bennett/Stulz/Wang (2023) report this "
        f"effect has already disappeared, so the prior going in is low and a positive result should "
        f"be disbelieved before it is believed."
    )
    return IndexRemovalSampleDisclosure(
        n_removals_total=n_removals_total,
        n_rename_artifacts_dropped=n_rename_dropped,
        n_candidate_removals=candidates,
        n_entered=len(entered),
        rejected_by_reason=dict(rejected),
        n_distinct_event_dates=distinct,
        n_independent_clusters=clusters,
        first_event_date=min(dates) if dates else None,
        last_event_date=max(dates) if dates else None,
        text=text,
    )


@dataclass
class IndexRemovalScreeningSummary:
    """run_index_removal_screening's full result: the per-spec results, the
    tickers that resolved no price data, and the sample disclosure as an
    explicit, always-present field."""

    results: list[IndexRemovalScreeningResult]
    missing_price_data: list[str]
    sample: IndexRemovalSampleDisclosure
    cost_disclosure: str


def _build_cost_disclosure(config: IndexRemovalConfig) -> str:
    total = config.stock_round_trip_bps + config.spy_round_trip_bps
    return (
        f"COST DISCLOSURE. Single-name leg: {config.stock_round_trip_bps}bp round trip, DERIVED from "
        f"this family's own real panel -- median post-removal dollar volume $59.5M/day across the "
        f"entered events, and an Amihud (2002) ILLIQ median of 2.52e-10 over the same windows, which "
        f"puts a round trip at 14.7bp for 5%-of-ADV participation and 23.4bp for 10% once a 3bp "
        f"effective half-spread is included; the figure used sits between them at roughly 6% of ADV. "
        f"Hedge leg: {config.spy_round_trip_bps}bp round trip on SPY -- ASSUMED, not measured (no "
        f"quote data in this project), and several times conservative against SPY's one-cent quoted "
        f"spread. Total {total}bp per event, charged once on the event's first realized day, entry "
        f"and exit together. Borrow: {config.spy_borrow_bps_per_year}bp/yr on the SHORT SPY notional "
        f"only -- also ASSUMED (SPY is general collateral; 25-35bp/yr is the ordinary range) -- "
        f"accrued on calendar days, so ~7.5bp over a 63-day hold, ~15bp over 126, ~30bp over 252. "
        f"Because this book is event-driven, the round trip is paid ONCE PER EVENT regardless of "
        f"holding period; only borrow scales with the hold, and it makes LONG holds dearer, not "
        f"short ones. The long single names borrow nothing, so unlike every other equity family in "
        f"this project there is no undisclosed hard-to-borrow short-leg optimism here."
    )


def screen_index_removal_family(
    close: pd.DataFrame,
    hedge: pd.Series,
    entered: list[EnteredEvent],
    config: IndexRemovalConfig,
    specs: list[IndexRemovalSpec] | None = None,
) -> list[IndexRemovalScreeningResult]:
    """One Sharpe per spec, DSR-corrected for the family's pre-declared
    size. Trial counting follows screen_cross_sectional_universe's pooled
    framing exactly and for the same reason: each spec IS already a single
    portfolio across the whole event set, so there is no per-event result
    to cherry-pick and "which definition" is the only search dimension.
    n_trials is therefore len(specs) -- the family's literal pre-declared
    size -- never shrunk to however many specs cleared the data floors.
    sigma_sr is the ddof=1 std of every sibling spec's own Sharpe from this
    same pass."""
    specs = specs if specs is not None else INDEX_REMOVAL_FAMILY
    n_trials = len(specs)
    basis = (
        build_inverse_vol_basis(close)
        if any(s.leg_weighting == "inverse_vol" for s in specs)
        else None
    )

    replays: dict[str, IndexRemovalBacktestResult] = {}
    for spec in specs:
        result = run_index_removal_backtest(close, hedge, entered, spec, config, basis)
        if result.status != "ok" or len(result.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            continue
        replays[spec.pattern_id] = result

    sharpes = {pid: sharpe_ratio(res.daily_returns) for pid, res in replays.items()}
    sigma_sr = (
        float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None
    )

    spec_by_id = {spec.pattern_id: spec for spec in specs}
    results: list[IndexRemovalScreeningResult] = []
    for pattern_id, replay in replays.items():
        spec = spec_by_id[pattern_id]
        n_days = len(replay.daily_returns)
        results.append(
            IndexRemovalScreeningResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                holding_days=spec.holding_days,
                leg_weighting=spec.leg_weighting,
                n_events_entered=replay.n_events_entered,
                n_events_delisted_mid_hold=replay.n_events_delisted_mid_hold,
                n_trading_days=n_days,
                n_invested_days=replay.n_invested_days,
                invested_fraction=(replay.n_invested_days / n_days) if n_days else 0.0,
                sharpe_annualized=sharpes[pattern_id],
                total_cost_drag=replay.total_cost,
                total_financing_drag=replay.total_financing_cost,
                deflated_sharpe=compute_deflated_sharpe(
                    sharpes[pattern_id], replay.daily_returns, n_trials, sigma_sr
                ),
                n_weighted_days=replay.n_weighted_days,
                n_weight_fallback_days=replay.n_weight_fallback_days,
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results


def run_index_removal_screening(
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    config: IndexRemovalConfig | None = None,
) -> IndexRemovalScreeningSummary:
    """THE production entry point for this family -- mirrors
    cross_sectional_patterns.run_round_c_screening's and
    cross_sectional_patterns_d2.screen_d2_reversal_family's shape (same
    provider, same missing-tickers contract, same start-date guard) while
    running this family's own event-driven replay rather than the
    cross-sectional harness.

    `start` must be >= MEMBERSHIP_DATA_START: an event before that date
    would come from membership data this project does not have. Price
    history is fetched with REMOVAL_PRICE_HISTORY_PADDING_CALENDAR_DAYS of
    lead-in purely to warm the pre-removal non-recycling window and the
    inverse-vol basis; no event can be entered in that padding, because
    events come from the dated membership data itself.

    Returns an IndexRemovalScreeningSummary: the per-spec results, the
    tickers that resolved no price data (a required part of the result, not
    a logging detail -- see the module docstring's sample section on why
    52% of candidate removals are unpriceable and what that does and does
    not bias), the recomputed sample disclosure, and the cost disclosure."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Index-removal screening start {start.isoformat()} predates point-in-time membership "
            f"coverage ({MEMBERSHIP_DATA_START.isoformat()}) -- there are no dated removal events "
            "before it."
        )
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else IndexRemovalConfig()

    all_events, n_rename_dropped = list_index_removal_events()
    n_removals_total = sum(len(removed) for _, _, removed in vendored_events())
    events = [e for e in all_events if start <= e.effective_date <= end]

    universe = sorted({e.ticker for e in events})
    padded_start = start - timedelta(days=REMOVAL_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    frames, missing = provider.get_daily_ohlcv(universe, padded_start, end)
    if not frames:
        entered: list[EnteredEvent] = []
        sample = build_index_removal_sample_disclosure(
            n_removals_total, n_rename_dropped, entered, {}
        )
        return IndexRemovalScreeningSummary(
            results=[],
            missing_price_data=missing,
            sample=sample,
            cost_disclosure=_build_cost_disclosure(config),
        )

    close = frames["close"]
    hedge_frames, hedge_missing = provider.get_daily_ohlcv(
        [REMOVAL_HEDGE_TICKER], padded_start, end
    )
    if (
        hedge_missing
        or not hedge_frames
        or REMOVAL_HEDGE_TICKER not in hedge_frames["close"].columns
    ):
        raise ValueError(
            f"The {REMOVAL_HEDGE_TICKER} hedge leg resolved no price data. Every position in this "
            "family is long one name against an equal-notional short of that hedge, so without it "
            "there is no market-neutral trade to backtest -- failing loudly rather than silently "
            "screening an unhedged long book, which is a different (and far more market-exposed) "
            "strategy than the one this family declares."
        )
    hedge = hedge_frames["close"][REMOVAL_HEDGE_TICKER]

    entered, rejected = build_removal_event_book(close, events)
    sample = build_index_removal_sample_disclosure(
        n_removals_total, n_rename_dropped, entered, rejected
    )
    results = screen_index_removal_family(close, hedge, entered, config)
    return IndexRemovalScreeningSummary(
        results=results,
        missing_price_data=missing,
        sample=sample,
        cost_disclosure=_build_cost_disclosure(config),
    )
