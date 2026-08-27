"""Re-running this project's EXISTING cross-sectional equity families on a
NEW universe: the S&P 600 small-cap index instead of the S&P 500.

WHAT THIS MODULE IS, AND WHAT IT DELIBERATELY IS NOT. Every signal definition
re-run here already existed and was already tested on the S&P 500. Nothing is
redesigned, retuned, or newly hypothesised: the signal FUNCTIONS are imported
from the two modules that own them (cross_sectional_ivol.signal_
idiosyncratic_volatility; cross_sectional_patterns.signal_52_week_high_
nearness and signal_capital_gains_overhang) and called through the same
partial-application scheme, with the same lookbacks, the same rank fractions,
the same portfolio constructions and the same citations. Exactly three things
differ, and each is stated as a decision below with its own reasoning: the
UNIVERSE, the TRANSACTION-COST assumption, and the HOLDING-PERIOD axis.

Re-implementing the signals here rather than importing them would have made
this a family that merely resembles the originals — and then a "the small-cap
result differs from the large-cap result" finding could be an artifact of the
re-implementation rather than of the universe. Importing them is what makes
the comparison mean anything.

=======================================================================
1. WHICH FAMILIES ARE REUSED, AND THEIR EXACT SIZES
=======================================================================

 (a) BUILD D1 — idiosyncratic volatility (cross_sectional_ivol.py).
     Original family: 21 definitions = 3 lookbacks {21, 63, 252} x 2
     portfolios {long_short, long_universe_hedged} x 3 holds {21, 63, 126}
     (= 18 residual-IVOL) + 3 raw-volatility robustness definitions at
     w=63, long_short only, across the same 3 holds. Asserted at import as
     REUSED_IVOL_FAMILY_SIZE == len(ROUND_D1_FAMILY) == 21, so this
     module's arithmetic cannot silently drift if that family is ever
     edited.
     Citations: Ang/Hodrick/Xing/Zhang (2006), Bali/Cakici (2008),
     Blitz/van Vliet (2007).

 (b) ROUND C's DISPOSITION CORE (cross_sectional_patterns.py).
     Round C's full family is 30 definitions in three groups. The two
     REUSED here are the disposition-effect groups, 18 definitions
     together:
       * George & Hwang 52-week-high nearness — 9 definitions (long-short
         decile, long-short quintile, and universe-hedged long-only decile,
         each across 3 holds).
       * Grinblatt & Han capital-gains overhang — 9 definitions (deciles at
         two reference-price windows {252, 504} across 3 holds, plus a
         quintile sensitivity variant at the 252 window across 3 holds).
     Asserted at import against the real ROUND_C_FAMILY by counting its
     members' `family` fields, never as a hand-typed literal.

     THE THIRD GROUP IS EXCLUDED, and the reason is a pre-registration, not
     a result: Lou/Polk/Skouras component persistence (12 definitions) is
     specified in its own module at holds {21, 63} ONLY, and both of those
     holds are ruled out here by the cost argument in section 3. Extending
     LPS to a 126- or 252-day hold would contradict that family's own
     documented rationale (its module states plainly that component
     persistence decays faster than the disposition anomalies, which is why
     the 6-month hold was spent elsewhere) — and, more importantly, it
     would be INVENTING A NEW DEFINITION rather than re-running an existing
     one, which is the one thing this module exists not to do. So LPS is
     not re-run at all, rather than re-run at a hold its authors did not
     specify.

=======================================================================
2. n_trials FOR THIS RUN: DOUBLED, AND WHY THAT IS ARITHMETIC
=======================================================================

screen_cross_sectional_universe's default denominator is len(specs), and
its docstring gives the reason: each spec is already ONE portfolio over the
whole universe, so there is no per-ticker result to cherry-pick and "which
definition" is the only search dimension.

THAT REASONING IS INCOMPLETE FOR THIS RUN, and the gap is the whole point.
Testing an already-designed, already-tested family on a NEW universe makes
the universe a second searched dimension. Concretely: D1's 21 definitions
were already screened on the S&P 500 and those 21 results were computed and
seen. Running the same definitions on the S&P 600 means the set of results
from which a maximum could now be reported is

    {21 definitions} x {S&P 500, S&P 600} = 42 configurations,

not 21. Reporting the best S&P 600 number against a denominator of 21 would
correct for only half the comparisons actually made — it would treat the
choice of universe as free, when it is exactly the kind of choice that gets
made, silently, until something looks good. The honest denominator is

    n_trials = UNIVERSE_MULTIPLIER x (the reused family's own size)

with UNIVERSE_MULTIPLIER = 2, giving 42 for D1 and 36 for the 18-definition
disposition core. Both are asserted in code (see IVOL_N_TRIALS /
DISPOSITION_N_TRIALS and their assertions) and passed explicitly to the
screening call via n_trials_override, so the number the DSR actually uses is
the number stated here — not a claim made in prose over a call that quietly
uses len(specs).

DELIBERATELY *NOT* SHRUNK TO THE NUMBER OF SPECS ACTUALLY RUN. Section 3's
holding-period restriction means only 14 of D1's shape and 12 of the
disposition core's shape are replayed here. It would be arithmetically
tidier to double THOSE (28 and 24). It would also be wrong, in the specific
way this project has already caught itself once: cross_sectional_patterns_
round_d.py's module docstring works through why narrowing a family after the
fact and then deflating against the narrowed count is "trial-count
laundering" — a corrected-LOOKING Sharpe that is not corrected for the
search that produced the hypothesis. The 21 and the 18 are the sizes of the
searches that produced these definitions; the hold restriction removes specs
from THIS replay, it does not un-search them. So the larger, uncomfortable
denominator is the correct one, and screen_cross_sectional_universe now
refuses an override smaller than len(specs) outright.

=======================================================================
3. HOLDING PERIODS: {126, 252} ONLY, PRE-REGISTERED BEFORE ANY RESULT
=======================================================================

Fixed before the first backtest was run, by cost arithmetic alone, and
recorded here so it cannot be mistaken for a post-hoc filter.

A fully-formed long_short book carries gross notional 2.0 (1.0 long + 1.0
short), so ONE complete reformation at c bps one-way costs 2c bps of equity.
At SMALL_CAP_COST_BPS = 15.0 that is 30 bps per reformation, and a year
contains 252/H reformations:

    H=21   ->  12.0 reformations/yr  ->  360 bps/yr
    H=63   ->   4.0 reformations/yr  ->  120 bps/yr
    H=126  ->   2.0 reformations/yr  ->   60 bps/yr
    H=252  ->   1.0 reformation /yr  ->   30 bps/yr

Expressed as Sharpe drag — the only unit in which these are comparable to
anything this project reports — divided by a dollar-neutral small-cap decile
book's annualized volatility, ~10%:

    H=21 -> 0.36    H=63 -> 0.12    H=126 -> 0.06    H=252 -> 0.03

So H=21 spends roughly a third of a Sharpe point on costs before any signal
is even consulted, and H=63 an eighth. Round C's own S&P 500 screening
already came back cost-dominated at those horizons at a THIRD of this cost
assumption; re-running them here at 3x the cost would spend real compute
re-deriving a conclusion already established, with a larger n_trials
denominator as the only result. H=126 and H=252 pay 0.06 and 0.03 — small
enough that a real signal could survive them.

(These figures assume 100% turnover at each reformation, the worst case. The
feasibility scout that proposed this build derived the same ORDERING from a
partial-turnover assumption and got smaller absolute drags — ~0.21 at H=21,
~0.02/0.01 at H=126/252. The numbers above are the more conservative of the
two derivations and were re-derived here independently; the decision they
support is identical either way.)

H=252 is NOT in either original family's hold axis (D1 tops out at 126,
Round C's disposition groups at 126). It is included because the cost
argument above points there and because both cited literatures report holds
out to 12 months — George & Hwang's and Grinblatt & Han's tables span 1-12
months, and the original module says in as many words that 12-month holds
were dropped "to keep the family inside the ceiling", not because they were
uninteresting. Adding it is therefore a restoration of a hold the source
literature reports, not an invention. It is also counted: it is part of why
n_trials is doubled rather than left alone.

=======================================================================
4. TRANSACTION COSTS: 15 bps ONE-WAY, NOT THE 5 bps EQUITY DEFAULT
=======================================================================

The harness default DEFAULT_XS_COST_BPS = 5.0 was calibrated for S&P 500
large caps and is WRONG for this universe. Measured live 2026-08-27 on real
yfinance daily bars, 120 randomly sampled tickers per index over
2024-01-01..2026-08-26, using the Corwin & Schultz (2012) high-low spread
estimator:

    median estimated spread   S&P 600  33.6 bps   vs   S&P 500  22.6 bps
    median daily dollar volume S&P 600  $22.2M    vs   S&P 500  $276.1M

READ THOSE ABSOLUTE NUMBERS WITH CARE — this is the honest part. A 22.6 bps
effective spread for the median S&P 500 name is far too high; the real
figure is low single digits. Corwin-Schultz is well known to be badly
upward-biased when applied to daily bars of liquid names, so the LEVELS here
are not usable and are not used. What IS usable is the RATIO, where the bias
substantially cancels: small caps trade at ~1.49x the large-cap spread and
in books ~12.5x thinner. (The feasibility scout measured this independently
with a different estimator and got 1.4x and 13x — the levels it reported,
132/94 bps, are likewise not credible as effective spreads, but its ratios
replicate mine almost exactly, which is the part both measurements agree on.)

The 15 bps is built from the ratios, not the levels:
  * Spread half: 5.0 x 1.49  ~=  7.5 bps.
  * Impact half: the square-root law says impact scales as sqrt(Q/ADV), so
    the same dollar order into a 12.5x thinner book costs sqrt(12.5) = 3.54x
    more impact. Splitting the 5.0 bps large-cap figure evenly between
    spread and impact, this universe pays 2.5 x 1.49 + 2.5 x 3.54 = 12.5 bps.
  * Rounded UP to 15.0, the direction a cost assumption should be rounded.

The scout's own independent estimate, reached by a different route, was also
15 bps. Two derivations agreeing is why this number is used rather than a
wider bracket — but it remains an ESTIMATE from free data, not a measured
fill cost, and every result this module produces should be read with the
breakeven arithmetic in section 3 in hand.

Financing (config.financing_bps_per_year) is left at 0.0, exactly as every
prior equity family leaves it. That is not a claim that small-cap short
borrow is free — it is emphatically NOT, and small caps are harder and
dearer to borrow than large caps, so the undisclosed short-borrow optimism
cross_sectional.py documents is WORSE here than on the S&P 500. It is left
at 0.0 because this project has no sourced borrow-rate data for these names
and inventing one would be a fabricated number dressed as a correction.

=======================================================================
5. SURVIVORSHIP: DISCLOSED, NOT CLOSED
=======================================================================

Measured live 2026-08-27 against the real point-in-time universe (see
small_cap_membership_history.py for the membership data's own quality
audit):

  * The point-in-time union universe over 2020-01-01..today is 1,088
    tickers — 603 of them still members at coverage end, 485 departed. That
    churn is itself the headline: 45% of the names this strategy could have
    held left the index during the window.
  * Price coverage splits sharply along exactly the survivorship-relevant
    line. Still-members: 601/603 resolve (99.7%). DEPARTED: 272/485 resolve
    (56.1%) — 213 names, 43.9% of the departed population, have NO yfinance
    price history at all. That is the same rate the S&P 500 harness
    discloses for its own departed members (48%), but over a population
    4.6x larger.
  * Of the 272 departed names that DO resolve, 25 are RECYCLED TICKERS
    whose entire yfinance history postdates their index exit — a different
    company trading under the reused symbol. See mask_recycled_ticker_
    prices below, which removes them structurally rather than relying on
    the containment argument cross_sectional.py makes for the S&P 500 case.
    That argument (recycling gaps are years, holds are months) does NOT
    hold at this universe's scale: 7 of the 25 resume within a year of exit
    and 2 within 40 days (PRA at +3 days, FDP at +38), well inside a
    252-day hold.

None of this is closed by this module, and the direction of the residual
bias is the same open question cross_sectional.py reasons through at length
for the S&P 500 — plausibly understating a long-short strategy's edge by
denying the short leg its best names, but not confidently signed. Closing it
needs a delisted-securities price vendor this project does not have.

Alpaca was NOT used, despite resolving a higher fraction of delisted names
in this project's earlier testing, and despite credentials being available:
it was independently found to have real gaps of its own (a pre-2016 coverage
floor, silent ticker recycling, zero-volume ghost bars). Swapping one
partially-broken source for another partially-broken source would change the
disclosure without closing the gap, and would make this run's prices
inconsistent with every other equity family in the project.

=======================================================================
6. THE IVOL FAMILY IS BARELY VALUE-WEIGHTED ON THIS UNIVERSE
=======================================================================

Found by the production run, and load-bearing for how family (a)'s results
may be read. Build D1's defining property is VALUE-weighted legs — its whole
citation chain (Bali & Cakici especially) is about the low-IVOL premium being
weaker and less reliably signed under equal-weighting, so the weighting is
the hypothesis, not a detail.

On the S&P 600 that property largely does not survive contact with the data.
Measured on the real run: 201 of 231 formed legs — 87% — fell back to
magnitude weighting. The harness falls a WHOLE leg back whenever ANY member's
point-in-time market cap is unusable (see _resolve_leg_weights, and the
no-partial-state discipline behind it), and with quintile legs of ~100 names
drawn from small caps, the chance that all 100 have a filed share count
already known at that formation date is low. Note the cause is NOT missing
tickers: every priced ticker resolved SOME share history (the run reports 0
tickers with no share data). It is that yfinance's filing-dated share counts
begin later than the price history for many small caps, and
build_point_in_time_market_cap correctly refuses to back-fill a count before
its first real observation.

So family (a)'s numbers below should be read as a MOSTLY MAGNITUDE-WEIGHTED
replay of the IVOL definitions, not as the value-weighted construction the
literature reports. The fallback rate is reported as a first-class field on
every result (n_value_weighted_legs / n_value_weight_fallbacks), which is how
this was found rather than assumed — but no result here is a clean test of
the value-weighted anomaly, and none should be described as one.

=======================================================================
7. CROSS-ENDPOINT CONTAMINATION AUDIT (2026-08-27) — REAL, PRESENT, AND
   IT MOVED NOTHING
=======================================================================

Family (a) reaches yfinance's share counts through Build D1's own plumbing
(get_shares_outstanding -> build_point_in_time_market_cap), so it inherits
the defect that module's CROSS-ENDPOINT CONSISTENCY block describes: the
price and the share count come from two DIFFERENT yfinance endpoints joined
by ticker symbol alone, symbols get reassigned, and the two endpoints do not
agree about when. cross_sectional_ivol.py's own commit flagged this module as
un-audited on the reasoning that small caps are where symbol reuse is most
common. This section is that audit, run against THIS family's real
production fetch (2020-01-01..2026-08-27, the 1,088-ticker point-in-time
union, 849 priced tickers after mask_recycled_ticker_prices, 435,882 raw
share-count observations). The two checks are IMPORTED from
cross_sectional_ivol.py, not reimplemented, so a "small caps are worse"
finding cannot be an artifact of a second implementation — the same
discipline this whole module applies to the signal functions.

THE TIME AXIS FOUND REAL CONTAMINATION: 3,383 share-count observations
across 16 of the 849 priced tickers (1.88%) are dated outside their own
ticker's price history. Confirmed case by case against yfinance's own
current metadata, not inferred:
  * AMR — this universe's STI. 113 observations from 2018-11-28 carrying
    176M-527M shares (Alta Mesa Resources, the Nasdaq E&P that went
    bankrupt in 2019) sit in front of a price series that begins
    2021-02-08 and belongs to Alpha Metallurgical Resources, whose real
    count is 12.7M-21.7M. The join steps 384,351,008 -> 18,308,800 across
    the boundary, a 0.0476x break with no split anywhere near it.
  * INT — 254 observations from 2018-11-28 carrying World Fuel Services'
    59.8M-68.7M shares, against a price series of exactly 34 bars
    (2026-07-10..2026-08-26) that yfinance's own .info names
    'Corgi Intc 2x Daily ETF'. One column, a defunct symbol's fundamentals
    and a leveraged ETF's prices. INT was a point-in-time member until
    2026-08-04, so those bars were live and eligible.
  * SOLS — 265 observations up to 2.50e9 shares (Honeywell's own scale;
    the last pre-boundary value is 532,560,000) in front of Solstice
    Advanced Materials' post-spin prices from 2025-10-20, whose real count
    is 158.7M. The contaminated join reads $26.5bn against a real ~$7.9bn.
  * FG — 142 observations of 213M-265M shares (Fidelity National
    Financial's scale) in front of F&G Annuities & Life's post-spin prices
    from 2022-11-22; the boundary step is 221,972,992 -> 18,836,000.
  * The predecessor-entity cases, same class, different cause — a
    bankruptcy reorganisation or a spin-off cancelled and reissued the
    equity while the symbol carried on: HTZ (151 obs, 3.08x step), CRC
    (138), GPOR (144), NE (143), DBD (214), SPWR (194), XPER (180),
    DAVE (94, 39.88x step).
  * CPRX, AVNS, STEL — yfinance serves exactly ONE price bar for each over
    the whole 7.7-year window (verified with a per-ticker .history() call,
    so this is the feed's own state, not a batch-download flake) against
    525/459/364 share observations. Every observation is outside a
    one-day lifecycle, so all three end up with no usable share history at
    all, which is the honest answer for a ticker with no price series.
  * SEZL — 3 observations at a 23-day lead. The grace-window edge case,
    and the only one of the 16 where the exact grace value matters.

WHAT IT CHANGED FOR THIS FAMILY: NOTHING, and that is measured rather than
hoped. Replayed against the SAME saved production fetch (a controlled
comparison, not two different runs — the replay reproduces the published
run's leg accounting EXACTLY, 231 formed legs and 201 fallbacks, and its
Sharpe range -0.4164..-0.7564 against the published -0.42..-0.76), all 14
specs come back BIT-IDENTICAL to four decimal places, every DSR identical,
every fallback tally identical.

The reason is specific and worth stating, because "no change" can also mean
"not wired". Only 20 of 825,668 eligible (ticker, day) market-cap cells
change at all — INT 17, AVNS/CPRX/STEL 1 each. For the other 12 tickers the
contaminated observations never reach a priced day: a real in-window filing
already exists at or before the first price bar (AMR's first in-window
observation is 2021-02-05, three days BEFORE its first price bar), so the
forward-fill never carries a pre-lifecycle count into the price window. And
the 20 cells that do change belong to tickers whose legs were already
falling back to magnitude weighting, which section 6 explains is 87% of
them. The checks demonstrably fire, and that is checkable rather than
asserted: run_small_cap_ivol_screening now returns both refusal counts as
its last two values (3,383 and 488 on this run), precisely so a correction
that silently stops firing cannot look like a correction that had nothing
to do — the same reason BuybackScreeningSummary carries its own two.

THE FIX IS WIRED ANYWAY, for the reason cross_sectional_ivol.py wired it
into D1 on an equally immaterial result: it is a correctness guarantee about
whose company's shares are in the weight, not a numbers change, and the one
ticker where the contamination DOES reach eligible cells (INT) shows the
margin is thin. Nothing here got MORE positive — every number is unchanged
— so the extra-scrutiny rule this project applies to a flattering fix has
nothing to bite on.

THE MAGNITUDE BAND HAD TO BE RE-DERIVED, and the S&P 500's is unusable
here. cross_sectional_ivol.SP500_MIN/MAX_PLAUSIBLE_MARKET_CAP_USD is
[$1bn, $6T]; applied to this universe that floor alone refuses 199,765 of
825,668 real eligible cells — 24.19%, since the 25th percentile of a real
S&P 600 market cap here is $1.02bn and the median only $1.73bn. See
SMALL_CAP_MIN/MAX_PLAUSIBLE_MARKET_CAP_USD below for the band
this universe's own measured distribution supports, and note the honest
consequence: it refuses 488 cells, ALL of them on days the ticker was not a
point-in-time member and therefore unreadable by any formation, and ZERO
eligible cells. On the S&P 500 the magnitude axis was the check that caught
BNY and COL; here it catches nothing that matters, because a small cap's
real range and its contaminated range OVERLAP instead of sitting orders of
magnitude apart. The time axis does all the work on this universe.

TWO CONFIRMED CONTAMINATIONS NEITHER CHECK CAN SEE — disclosed, not fixed,
in the same register split_adjust_share_counts discloses TSLA/TTD/PARA:
  * BBT, 1,440 eligible cells, the largest single contamination in this
    universe. Berkshire Hills Bancorp's real prices (mcap-basis close
    $32.74 on 2020-01-02) are joined to a share count of 1,341,340,032 —
    Truist's, inherited when BB&T's symbol was freed in December 2019 — for
    the entire 2020-01-02..2025-09-02 membership interval, giving implied
    market caps of $2.63bn-$43.9bn for a company really worth ~$1.6bn. The
    series steps 766,302,976 -> 1,341,340,032 on 2019-12-11 (the BB&T /
    SunTrust merger) and 1,341,340,032 -> 84,272,200 on 2025-09-03 (the
    handover to Beacon Financial Corporation, which .info now names as the
    symbol's holder), with no split at either date. The time axis cannot
    see it — price and share series overlap perfectly, all 1,946 rows —
    and the magnitude axis cannot either, because $2.6bn-$43.9bn is inside
    the real S&P 600 range (a real member, SanDisk, reached $41.5bn while
    a member on 2025-11-12).
  * BNED, 568 eligible cells at 100x. Its 1-for-100 reverse split
    (2024-06-12, ratio 0.01) back-adjusts every pre-2024 price by 100
    while split_adjust_share_counts correctly declines to adjust the share
    count, because the series shows no 0.01x jump — a 243.9M-share
    issuance on 2024-06-06 immediately before the split means the observed
    step is 0.145x, nowhere near the ratio. Result: $61.9bn implied on
    2021-10-12 against a real ~$0.62bn. This is the AIV case from D1's own
    band comment, at 100x instead of 9.3x. $61.9bn sits below BOTH the
    S&P 500's $6T ceiling and this module's own tighter $1T one -- neither
    catches it; only a materially tighter, S&P-600-calibrated ceiling
    would, and tightening the ceiling that far would itself start refusing
    real large members of this universe.
  Both would need a THIRD check (a share-count step with no matching
  split), which is a new detector with its own tuning risk, not a reuse of
  these two — deliberately not built as part of this audit.

ARE SMALL CAPS WORSE? MEASURED, and the naive answer is wrong. Running the
identical check over Build D1's own S&P 500 production fetch on the same
day gives 32 of 617 priced tickers (5.19%), against 16 of 849 (1.88%) here
— small caps look 2.8x BETTER. That comparison is confounded twice, and
both confounds run the same way:
  * This module already applies mask_recycled_ticker_prices, which D1 has
    no equivalent of. Run against the UNMASKED 874-ticker price frame the
    rate is 41/874 = 4.69%, essentially the S&P 500's 5.19%. All 25 of the
    tickers that mask drops independently trip the lifecycle check too —
    100% agreement between two detectors that share no input (one keyed on
    membership intervals and price gaps, the other on price dates versus
    share-count dates), which is a mutual confirmation, and the opposite
    of the ZERO overlap D1's audit found against the Alpaca recycling
    detector.
  * The windows differ: 6.6 years here against D1's 11.6. Per year of
    window the unmasked rates are 0.71%/yr small-cap against 0.45%/yr
    large-cap — 1.6x MORE for small caps, which is the direction the
    a-priori argument predicted, at a much smaller magnitude than "small
    caps are where symbol reuse is most common" implies.
So: real, comparable to the large-cap rate per ticker, ~1.6x worse per unit
of time, and already half pre-empted by this module's own recycled-ticker
mask.
"""

from collections.abc import Callable
from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_ivol import (
    IVOL_CITATION,
    IVOL_LOOKBACK_DAYS,
    IVOL_RANK_FRACTION,
    IVOL_ROBUSTNESS_LOOKBACK_DAYS,
    ROUND_D1_FAMILY,
    build_point_in_time_market_cap,
    implausible_market_cap_mask,
    restrict_share_counts_to_price_lifecycle,
    signal_idiosyncratic_volatility,
)
from app.services.research_lab.cross_sectional_patterns import (
    CGO_CITATION,
    CGO_LOOKBACK_DAYS,
    GH52_CITATION,
    ROUND_C_FAMILY,
    TURNOVER_NORMALIZATION_WINDOW,
    signal_52_week_high_nearness,
    signal_capital_gains_overhang,
)
from app.services.research_lab.small_cap_membership_history import (
    MEMBERSHIP_DATA_START,
    get_membership_intervals,
    get_universe_over,
    was_member,
)

# --- section 3: the pre-registered holding-period axis ----------------------

# Fixed by the cost arithmetic in the module docstring's section 3, BEFORE any
# backtest was run. 21 and 63 are excluded by that argument, not by any
# result; 252 is included because both cited literatures report holds out to
# 12 months and the cost arithmetic points there.
SMALL_CAP_HOLDING_DAYS: tuple[int, ...] = (126, 252)

# --- section 4: the cost assumption -----------------------------------------

# One-way, per unit of gross notional traded. NOT the harness's
# DEFAULT_XS_COST_BPS = 5.0, which is a large-cap number — see the module
# docstring's section 4 for the measurement, the two ratios it rests on, and
# the explicit warning that the measured LEVELS are not credible and are not
# used. Same register as cross_sectional_bonds.BONDS_COST_BPS, which likewise
# overrides the harness default for its own asset class.
SMALL_CAP_COST_BPS = 15.0

# --- section 2: the doubled n_trials ----------------------------------------

# The universe is a searched dimension. Re-running an N-definition family on
# a second universe makes the reportable configuration set N x 2. See the
# module docstring's section 2 for the full derivation and for why this is
# NOT applied to the (smaller) number of specs actually replayed here.
UNIVERSE_MULTIPLIER = 2

# The two reused families' OWN sizes, read from the real family objects
# rather than typed as literals, so an edit to either upstream family can
# never leave this module's n_trials arithmetic quietly stale.
REUSED_IVOL_FAMILY_SIZE = len(ROUND_D1_FAMILY)
DISPOSITION_FAMILIES: tuple[str, ...] = (
    "disposition_52wk_high",
    "disposition_capital_gains_overhang",
)
REUSED_DISPOSITION_FAMILY_SIZE = sum(
    1 for spec in ROUND_C_FAMILY if spec.family in DISPOSITION_FAMILIES
)

IVOL_N_TRIALS = UNIVERSE_MULTIPLIER * REUSED_IVOL_FAMILY_SIZE
DISPOSITION_N_TRIALS = UNIVERSE_MULTIPLIER * REUSED_DISPOSITION_FAMILY_SIZE

# Asserted, not merely documented — the build's own explicit requirement, and
# the same discipline every family module in this project applies to its own
# family size. These are the numbers the DSR denominators must be, and they
# are passed to screen_cross_sectional_universe explicitly below.
assert REUSED_IVOL_FAMILY_SIZE == 21, (
    f"Build D1's family is {REUSED_IVOL_FAMILY_SIZE} definitions, not the 21 this module's n_trials "
    "arithmetic was derived for — re-derive section 2 of the module docstring before proceeding."
)
assert REUSED_DISPOSITION_FAMILY_SIZE == 18, (
    f"Round C's disposition core is {REUSED_DISPOSITION_FAMILY_SIZE} definitions, not the 18 this "
    "module's n_trials arithmetic was derived for — re-derive section 2 before proceeding."
)
assert IVOL_N_TRIALS == 42
assert DISPOSITION_N_TRIALS == 36

# --- price-history padding --------------------------------------------------

# Calendar days fetched BEFORE the requested screening start, purely to warm
# the longest signal lookback each family uses. Formations themselves never
# occur in the padding (CrossSectionalConfig.formation_start pins them to the
# requested start), so no formation can predate the point-in-time membership
# data either.
#
# IVOL: max lookback 252 + 1 = 253 trading rows ~= 367 calendar days, rounded
# up for holiday clustering — the same 400 cross_sectional_ivol.py uses.
IVOL_PRICE_HISTORY_PADDING_CALENDAR_DAYS = 400
# Disposition: max 504 + 63 = 567 trading rows ~= 822 calendar days — the same
# 850 cross_sectional_patterns.py uses.
DISPOSITION_PRICE_HISTORY_PADDING_CALENDAR_DAYS = 850

# --- section 5: structural recycled-ticker containment ----------------------

# A gap this long in a departed member's price series, on the far side of its
# index exit, is a different listing rather than a data outage: real trading
# halts in this universe run days, not months, and every recycled symbol
# measured here reappeared after a gap far longer than this. Used only to
# decide where a departed ticker's OWN history stops — never to delete data
# inside a membership interval.
RECYCLED_TICKER_GAP_DAYS = 30

# --- section 7: this universe's own cross-endpoint plausibility band --------
#
# The dollar band outside which a computed market cap is taken as proof that
# the price endpoint and the share-count endpoint are not describing the same
# company. Passed EXPLICITLY to cross_sectional_ivol.implausible_market_cap_
# mask, which is parameterised for exactly this reason — its own defaults
# (SP500_MIN/MAX_PLAUSIBLE_MARKET_CAP_USD = $1bn / $6T) are an S&P 500 fact
# and are WRONG here by more than an order of magnitude in both directions.
# Reusing them would refuse a quarter of this universe's real data: measured
# over the 825,668 (ticker, day) cells that were actually ELIGIBLE (a
# point-in-time S&P 600 member with a finite close and a resolvable share
# count) in this family's real production run, the computed market cap runs
# p0.1 $0.118bn, p1 $0.267bn, p25 $1.02bn, MEDIAN $1.73bn, p99 $7.89bn,
# p99.9 $34.97bn. The S&P 500 floor alone refuses 199,765 of those cells —
# 24.19% of the real data, none of it defective.
#
# BOTH ENDS ARE SET AT 2.89x MARGIN FROM THE MEASURED REAL EXTREMES, so
# neither can decide a real case — the same "not load-bearing" property
# CROSS_ENDPOINT_PRICE_GRACE_DAYS claims for itself, here made symmetric:
#  * FLOOR $10M, against a smallest real eligible reading of $28.9M (TETRA
#    Technologies at the 2020-03/04 COVID trough — genuinely a $29M company
#    for a few weeks while still an index member; LSB Industries $31.1M and
#    Ring Energy $36.0M sit just above it). A floor anywhere near the S&P
#    500's would delete those real readings; this one cannot reach them.
#  * CEILING $1T, against a largest reading anywhere in the priced frame of
#    $345.8bn (SanDisk in 2026, real, on days it was no longer a member) and
#    a largest ELIGIBLE reading of $61.9bn. No company that was ever an S&P
#    600 small-cap member is worth a trillion dollars; a PARA-class splice
#    (which read $6,639bn-$75,330bn on the S&P 500) still lands outside.
#
# WHAT IT ACTUALLY CAUGHT on the real run — 488 cells over 6 tickers, ZERO of
# them eligible, i.e. zero readable by any formation. All 488 are floor hits
# and all are genuine defects rather than small companies: EGRX (247 cells),
# MARA (147), CLSK (43), LESL (37) and RGS (6) are reverse-split
# back-adjustments the share series shows no matching jump for, and CRC (8)
# is a single corrupt 51,037-share filing on 2020-10-30 against a real ~49M.
# The ceiling caught nothing real and nothing false. This is the honest
# result: on this universe the magnitude axis is insurance, and the time axis
# is the check that does the work — the reverse of the S&P 500 case, where
# the magnitude axis was the only thing that could see BNY and COL.
SMALL_CAP_MIN_PLAUSIBLE_MARKET_CAP_USD = 1.0e7
SMALL_CAP_MAX_PLAUSIBLE_MARKET_CAP_USD = 1.0e12


def mask_recycled_ticker_prices(
    frames: dict[str, pd.DataFrame],
    membership_intervals_fn: Callable[[str], list[tuple[date, date | None]]] = get_membership_intervals,
) -> tuple[dict[str, pd.DataFrame], list[str], list[str]]:
    """Removes price data that provably belongs to a DIFFERENT COMPANY than
    the index member whose ticker it is served under, and returns
    (cleaned frames, wholly-recycled tickers dropped, tickers truncated).

    THE HAZARD, measured rather than assumed (2026-08-27, real yfinance data
    over this module's own universe): of the 272 departed S&P 600 members
    that resolve any price history at all, 25 have histories that begin
    ENTIRELY AFTER the ticker left the index — the symbol was reassigned and
    yfinance serves the new company's bars under it. Examples: BBBY (exited
    2023-03-20, history starts 2026-07-17), PRA (exited 2026-06-29, history
    starts 2026-07-02), FDP (exited 2026-06-09, starts 2026-07-17).

    WHY THIS IS NOT ALREADY HANDLED. cross_sectional.py contains a
    containment ARGUMENT for exactly this failure mode: a ticker's prices can
    only reach a portfolio via a formation on which it was a member, or a
    hold begun at one; membership gates the first, and the second extends at
    most holding_days past a formation, "and every observed ticker recycling
    gap is years, not months". That argument is sound for the S&P 500 and it
    does NOT survive contact with this universe. Measured here: 7 of the 25
    recycled symbols reappear within a YEAR of exit and two within 40 days
    (PRA +3, FDP +38) — comfortably inside this module's 252-day hold. The
    argument's premise is empirically false at small-cap churn rates, so the
    guarantee is made structural instead of inferred.

    TWO RULES, both keyed on the ticker's own membership intervals:
     1. A departed ticker whose first valid price postdates its last
        membership interval's end has NO real history in the frame at all —
        every row is the successor company. The whole column is dropped.
     2. Otherwise, a departed ticker's history is truncated at the first gap
        longer than RECYCLED_TICKER_GAP_DAYS occurring AFTER its exit. This
        preserves the legitimate post-removal return window (index removal
        is not a forced sale — cross_sectional.py's convention, deliberately
        kept) while cutting the reused-symbol tail. Measured 0 occurrences
        on the current data; implemented anyway, because the rule is what
        makes rule 1's completeness checkable rather than a coincidence of
        today's feed.

    A ticker still a member at coverage end is never touched: there is no
    exit for a symbol to have been recycled after. Frames are cleaned
    together and stay index/column aligned, which
    validate_cross_sectional_data requires.

    membership_intervals_fn is injectable so this is unit-testable against
    hand-built intervals with no dependency on the vendored data."""
    close = frames["close"]
    dropped: list[str] = []
    truncated: list[str] = []
    cut_at: dict[str, pd.Timestamp] = {}

    for ticker in close.columns:
        spans = membership_intervals_fn(ticker)
        if not spans or spans[-1][1] is None:
            continue  # never a member, or still one — no exit to recycle after
        exit_date = spans[-1][1]
        series = close[ticker].dropna()
        if series.empty:
            continue
        if series.index[0].date() > exit_date:
            dropped.append(ticker)
            continue
        after = series[series.index.date > exit_date]  # type: ignore[attr-defined]
        if after.empty:
            continue
        # The gap that matters most is the one straddling the exit itself —
        # a name that stops trading at removal and whose symbol is reissued
        # months later. Measuring diffs WITHIN `after` alone would miss it
        # entirely, because that gap sits before `after`'s own first row. So
        # the last observation on or before the exit is used as the anchor
        # for the first diff. (This is a real bug the tests below caught: an
        # earlier version measured only intra-`after` gaps and silently
        # truncated nothing in exactly the case the rule exists for.)
        before = series[series.index.date <= exit_date]  # type: ignore[attr-defined]
        gaps = after.index.to_series().diff().dt.days
        gaps.iloc[0] = (after.index[0] - before.index[-1]).days
        big = gaps[gaps > RECYCLED_TICKER_GAP_DAYS]
        if len(big):
            cut_at[ticker] = big.index[0]
            truncated.append(ticker)

    if not dropped and not cut_at:
        return frames, [], []

    keep = [t for t in close.columns if t not in set(dropped)]
    cleaned: dict[str, pd.DataFrame] = {}
    for name, frame in frames.items():
        f = frame.loc[:, keep].copy()
        for ticker, cut in cut_at.items():
            f.loc[f.index >= cut, ticker] = np.nan
        cleaned[name] = f
    return cleaned, sorted(dropped), sorted(truncated)


# --- the two re-run families ------------------------------------------------


def _build_small_cap_ivol_family() -> list[CrossSectionalSpec]:
    """Build D1's definitions, unchanged except for the holding-period axis,
    re-expressed against the S&P 600.

    Every field is the ORIGINAL family's: the same imported signal function,
    the same IVOL_LOOKBACK_DAYS, the same IVOL_RANK_FRACTION quintiles, the
    same two portfolio constructions, the same value leg-weighting and
    market-cap requirement, the same +1 lookback row for pct_change, the same
    citation string. Only holding_days changes, to SMALL_CAP_HOLDING_DAYS.

    14 definitions (12 residual-IVOL + 2 raw-vol robustness), against the
    original's 21 — the difference being exactly the {21, 63} holds excluded
    in section 3 and the {252} hold added there. The DSR denominator is NOT
    14 and not 28: see IVOL_N_TRIALS."""
    specs: list[CrossSectionalSpec] = []

    for lookback in IVOL_LOOKBACK_DAYS:
        for portfolio in ("long_short", "long_universe_hedged"):
            portfolio_tag = "ls" if portfolio == "long_short" else "hedged"
            for horizon in SMALL_CAP_HOLDING_DAYS:
                specs.append(
                    CrossSectionalSpec(
                        pattern_id=f"sc600_ivol_resid_w{lookback}_{portfolio_tag}_h{horizon}",
                        family="small_cap_idiosyncratic_volatility",
                        citation=IVOL_CITATION,
                        signal_fn=partial(
                            signal_idiosyncratic_volatility, lookback_days=lookback, raw_vol=False
                        ),
                        lookback_days=lookback + 1,
                        holding_days=horizon,
                        portfolio=portfolio,
                        rank_fraction=IVOL_RANK_FRACTION,
                        leg_weighting="value",
                        requires_market_cap=True,
                    )
                )

    for horizon in SMALL_CAP_HOLDING_DAYS:
        specs.append(
            CrossSectionalSpec(
                pattern_id=f"sc600_ivol_rawvol_w{IVOL_ROBUSTNESS_LOOKBACK_DAYS}_ls_h{horizon}",
                family="small_cap_idiosyncratic_volatility",
                citation=IVOL_CITATION,
                signal_fn=partial(
                    signal_idiosyncratic_volatility,
                    lookback_days=IVOL_ROBUSTNESS_LOOKBACK_DAYS,
                    raw_vol=True,
                ),
                lookback_days=IVOL_ROBUSTNESS_LOOKBACK_DAYS + 1,
                holding_days=horizon,
                portfolio="long_short",
                rank_fraction=IVOL_RANK_FRACTION,
                leg_weighting="value",
                requires_market_cap=True,
            )
        )

    assert len(specs) == 14, f"small-cap IVOL family has {len(specs)} definitions, expected 14."
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.holding_days in SMALL_CAP_HOLDING_DAYS for s in specs), (
        "every spec must hold for one of the pre-registered SMALL_CAP_HOLDING_DAYS — the 21/63-day "
        "holds are excluded by the cost argument in section 3, before any result was seen."
    )
    return specs


def _build_small_cap_disposition_family() -> list[CrossSectionalSpec]:
    """Round C's two disposition groups, unchanged except for the
    holding-period axis, re-expressed against the S&P 600.

    Same imported signal functions, same CGO_LOOKBACK_DAYS, same decile /
    quintile rank fractions, same three George-Hwang portfolio variants, same
    turnover-normalization budget in lookback_days, same citations. Only
    holding_days changes.

    12 definitions (6 George-Hwang + 6 Grinblatt-Han), against the reused
    core's 18. Lou/Polk/Skouras is absent by pre-registration — see section 1.
    The DSR denominator is DISPOSITION_N_TRIALS, not 12 and not 24."""
    specs: list[CrossSectionalSpec] = []

    # George & Hwang: long-short decile, long-short quintile, and
    # universe-hedged long-only decile — the original's three variants.
    gh52_variants = (
        ("ls_decile", "long_short", 0.1),
        ("ls_quintile", "long_short", 0.2),
        ("long_hedged_decile", "long_universe_hedged", 0.1),
    )
    for tag, portfolio, rank_fraction in gh52_variants:
        for horizon in SMALL_CAP_HOLDING_DAYS:
            specs.append(
                CrossSectionalSpec(
                    pattern_id=f"sc600_gh52_{tag}_h{horizon}",
                    family="small_cap_disposition_52wk_high",
                    citation=GH52_CITATION,
                    signal_fn=partial(signal_52_week_high_nearness, lookback_days=252),
                    lookback_days=252,
                    holding_days=horizon,
                    portfolio=portfolio,
                    rank_fraction=rank_fraction,
                )
            )

    # Grinblatt & Han: deciles at both reference-price windows, plus the
    # quintile sensitivity variant at the shorter window.
    cgo_variants = [(f"ls_decile_l{lb}", lb, 0.1) for lb in CGO_LOOKBACK_DAYS]
    cgo_variants.append(("ls_quintile_l252", 252, 0.2))
    for tag, lookback, rank_fraction in cgo_variants:
        for horizon in SMALL_CAP_HOLDING_DAYS:
            specs.append(
                CrossSectionalSpec(
                    pattern_id=f"sc600_cgo_{tag}_h{horizon}",
                    family="small_cap_disposition_capital_gains_overhang",
                    citation=CGO_CITATION,
                    signal_fn=partial(signal_capital_gains_overhang, lookback_days=lookback),
                    lookback_days=lookback + TURNOVER_NORMALIZATION_WINDOW,
                    holding_days=horizon,
                    portfolio="long_short",
                    rank_fraction=rank_fraction,
                    requires_volume=True,
                )
            )

    assert len(specs) == 12, f"small-cap disposition family has {len(specs)} definitions, expected 12."
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.holding_days in SMALL_CAP_HOLDING_DAYS for s in specs), (
        "every spec must hold for one of the pre-registered SMALL_CAP_HOLDING_DAYS."
    )
    return specs


SMALL_CAP_IVOL_FAMILY: list[CrossSectionalSpec] = _build_small_cap_ivol_family()
SMALL_CAP_DISPOSITION_FAMILY: list[CrossSectionalSpec] = _build_small_cap_disposition_family()


def default_small_cap_config(start: date | None = None) -> CrossSectionalConfig:
    """A CrossSectionalConfig carrying this universe's own cost assumption.
    Every entry point below uses this unless the caller supplies its own
    config, which is then used exactly as given and never silently patched
    except for formation_start — the same contract run_commodities_screening
    and screen_fx_family keep."""
    return CrossSectionalConfig(cost_bps=SMALL_CAP_COST_BPS, formation_start=start)


def _check_start(start: date) -> None:
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"S&P 600 screening start {start.isoformat()} predates point-in-time small-cap "
            f"membership coverage ({MEMBERSHIP_DATA_START.isoformat()}) — a formation before that "
            "date would silently see an empty universe."
        )


def run_small_cap_disposition_screening(
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> tuple[list[CrossSectionalScreeningResult], list[str], list[str], list[str]]:
    """Production entry point for the re-run George-Hwang / Grinblatt-Han
    disposition core on the S&P 600.

    Returns (results, tickers that resolved no price data, tickers dropped as
    wholly recycled, tickers truncated at a post-exit gap). All three
    diagnostic lists are a required part of the result rather than a logging
    detail — the same discipline run_round_c_screening states for its one
    missing list, extended to the two this universe's measured recycling
    hazard needs (see mask_recycled_ticker_prices).

    membership_fn is passed EXPLICITLY as the small-cap gate. Leaving it None
    would default to the S&P 500's was_member, which answers False for every
    small cap — the entire universe would be ineligible on every formation
    date, which the harness now raises EmptyEligibleUniverseError for rather
    than silently returning zeros.

    STRUCTURALLY IMMUNE to section 7's cross-endpoint defect, and that is a
    property of the code path rather than a measurement: this entry point
    never calls get_shares_outstanding, never builds a market cap, and every
    one of its 12 specs leaves leg_weighting at the "magnitude" default with
    requires_market_cap unset. There is no share-count endpoint in this
    family for a price endpoint to disagree with. Pinned by test rather than
    asserted, so the 12 disposition specs' published numbers need no
    before/after — they cannot have one."""
    _check_start(start)
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else default_small_cap_config()
    config.formation_start = start

    universe = get_universe_over(start, end)
    padded_start = start - timedelta(days=DISPOSITION_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    frames, missing = provider.get_daily_ohlcv(universe, padded_start, end)
    if not frames:
        return [], missing, [], []

    frames, recycled, truncated = mask_recycled_ticker_prices(frames)
    data = CrossSectionalData(close=frames["close"], open=frames["open"], volume=frames["volume"])
    results = screen_cross_sectional_universe(
        data,
        SMALL_CAP_DISPOSITION_FAMILY,
        config,
        membership_fn=was_member,
        n_trials_override=DISPOSITION_N_TRIALS,
    )
    return results, missing, recycled, truncated


def run_small_cap_ivol_screening(
    start: date,
    end: date,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> tuple[
    list[CrossSectionalScreeningResult], list[str], list[str], list[str], list[str], int, int
]:
    """Production entry point for the re-run Build D1 idiosyncratic-volatility
    family on the S&P 600.

    Returns (results, no-price tickers, wholly-recycled tickers dropped,
    truncated tickers, tickers with no usable point-in-time share-count
    history among the priced ones, share-count observations refused as
    outside their ticker's price lifecycle, market-cap cells refused as
    implausible).

    The last two are COUNTS rather than lists, and they are returned rather
    than logged for the reason section 7 gives: a correction that silently
    stops firing looks exactly like a correction that had nothing to do, and
    on this run the two are genuinely different (the time axis refused 3,383
    observations, the magnitude band 488 cells, and the family's numbers did
    not move by 0.0001 either way). Same discipline as the three lists above
    and as BuybackScreeningSummary's own two counts, which these mirror.

    The three-step data fetch is Build D1's own, unchanged and for its own
    reasons (see run_round_d1_screening's docstring): Close-only prices for
    the signal; the split-adjusted, dividend-UNadjusted market-cap basis plus
    split ratios; and real point-in-time share counts, fetched only for
    tickers that actually resolved a price. The market cap those three
    combine into is what makes the legs value-weighted rather than
    magnitude-weighted, which is this family's defining property and is kept
    exactly as the original has it."""
    _check_start(start)
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else default_small_cap_config()
    config.formation_start = start

    universe = get_universe_over(start, end)
    padded_start = start - timedelta(days=IVOL_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    close, missing_price = provider.get_price_history(universe, padded_start, end)
    if close.empty:
        return [], missing_price, [], [], [], 0, 0

    cleaned, recycled, truncated = mask_recycled_ticker_prices({"close": close})
    close = cleaned["close"]

    priced = list(close.columns)
    mcap_close, splits, _ = provider.get_market_cap_basis(priced, padded_start, end)
    mcap_close = (
        pd.DataFrame(np.nan, index=close.index, columns=close.columns)
        if mcap_close.empty
        else mcap_close.reindex(index=close.index, columns=close.columns)
    )
    shares, missing_shares_fetch = provider.get_shares_outstanding(priced, padded_start, end)
    # CROSS-ENDPOINT CONSISTENCY, both axes — the same two checks
    # run_round_d1_screening applies, imported from the module that owns them
    # and applied in the same order and the same place. `close` (the frame
    # that DEFINED `priced`, already cleaned by mask_recycled_ticker_prices
    # above) is the authority on each ticker's price lifecycle, not the
    # market-cap basis, which can carry its own gaps. A ticker left with
    # nothing usable flows into never_resolved_shares below through the
    # builder's existing empty-series path, so it is reported in
    # tickers_without_shares exactly like a ticker whose fetch failed
    # outright — which is what happened to CPRX, AVNS and STEL on the real
    # run (see section 7).
    shares, out_of_lifecycle = restrict_share_counts_to_price_lifecycle(shares, close)
    n_out_of_lifecycle = sum(out_of_lifecycle.values())
    market_cap, never_resolved_shares = build_point_in_time_market_cap(mcap_close, shares, splits)
    # The magnitude axis, applied to the JOINED product — the only place a
    # BBT-style contamination could be visible at all — against THIS
    # universe's own band, never the S&P 500's (see
    # SMALL_CAP_MIN/MAX_PLAUSIBLE_MARKET_CAP_USD for why reusing that one
    # would delete a quarter of the real data). A masked cell is a missing
    # market cap, which the harness already handles by falling that WHOLE leg
    # back to magnitude weighting and counting it in n_value_weight_fallbacks
    # — no new failure mode, no new diagnostic.
    implausible = implausible_market_cap_mask(
        market_cap,
        minimum_usd=SMALL_CAP_MIN_PLAUSIBLE_MARKET_CAP_USD,
        maximum_usd=SMALL_CAP_MAX_PLAUSIBLE_MARKET_CAP_USD,
    )
    n_implausible = int(implausible.to_numpy().sum())
    market_cap = market_cap.mask(implausible)
    tickers_without_shares = sorted(set(missing_shares_fetch) | set(never_resolved_shares))

    data = CrossSectionalData(close=close, market_cap=market_cap)
    results = screen_cross_sectional_universe(
        data,
        SMALL_CAP_IVOL_FAMILY,
        config,
        membership_fn=was_member,
        n_trials_override=IVOL_N_TRIALS,
    )
    return (
        results,
        missing_price,
        recycled,
        truncated,
        tickers_without_shares,
        n_out_of_lifecycle,
        n_implausible,
    )
