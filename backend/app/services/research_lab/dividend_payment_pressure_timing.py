"""AGGREGATE DIVIDEND-PAYMENT PRICE PRESSURE: a single-instrument SPY market-
timing overlay driven by the market-wide dollar dividend paid on a day and the
day before, screened as exactly 34 PRE-DECLARED specs with its own n_trials
denominator.

PRE-REGISTRATION: data/research_runs/dividend_payment_pressure_PREREGISTRATION.txt,
committed as 92a6f5b BEFORE this module or any backtest existed. Every
construction constant below is fixed there; this module implements that
document and does not extend it.

============================================================================
THE SOURCE, READ DIRECTLY, AND ITS TWO TIERS
============================================================================
[HS25] Hartzmark, Samuel M. & Solomon, David H., "Market-Wide Predictable Price
Pressure", AMERICAN ECONOMIC REVIEW 115(9), September 2025, pp. 3171-3213,
doi:10.1257/aer.20231725. RECORD VERIFIED INDEPENDENTLY AT CROSSREF 2026-09-06.

**THIS IS A PEER-REVIEWED ARTICLE IN A TOP-FIVE ECONOMICS JOURNAL** -- the only
source among this session's six flow candidates that cleared refereeing, and
unlike the NBER working papers behind the others it carries no "has not been
peer-reviewed" disclaimer. THE PUBLISHED BODY WAS NOT RETRIEVED:
doi.org/10.1257/aer.20231725 returns HTTP 403 and OpenAlex reports is_oa =
False with no OA location. Only the published ABSTRACT was obtained.

[HS22] Hartzmark & Solomon, "Predictable Price Pressure", NBER Working Paper
30688, November 2022 -- the circulated precursor. OBTAINED AND READ IN FULL:
fetched 2026-09-06 from nber.org (HTTP 200, 800,140 bytes, SHA-256
96844d617d0827be52d8105dfc2cb6935df11fd3835960138fb671ffb4cf63b7) and
text-extracted with `pdftotext -layout`. EVERY equation, coefficient and
threshold quoted below is read off THAT text, not from memory and not from a
summary.

WHICH TIER A NUMBER COMES FROM MATTERS AND IS ALWAYS STATED. Every coefficient
and basis-point magnitude in this module is [HS22]'s working-paper figure. The
published [HS25] went through refereeing and its estimates may have moved; this
build cannot see them. The identical two-tier situation exists for the SAME two
authors' 2013 JFE paper in cross_sectional_dividend_month.py, and is handled
the same way.

WHAT CHANGED BETWEEN THE TWO, measured by comparing the two abstracts (the only
comparison the retrievable material supports): the price multiplier went from a
"1.5 to 2.3" range to a point estimate of 1.9, and -- THE ONE THAT DEFINES THIS
FAMILY'S SCOPE -- [HS22]'s blackout-period / stock-compensation selling result
is ABSENT from [HS25]'s abstract, and the title narrowed from "Predictable
Price Pressure" to "MARKET-WIDE Predictable Price Pressure". Building only the
dividend-payment side is therefore the whole of the published paper's headline
claim, not half of it. The blackout result is a different mechanism entirely
and nothing here touches it.

MECHANISM ([HS25] abstract, verbatim, and the only [HS25] text this build could
read): "We demonstrate that predictable uninformed cash flows forecast
aggregate market stock returns. Buying pressure from dividend payments
(announced weeks prior) predicts higher value-weighted market returns, with
returns for the top quintile of payment days four times higher than the
lowest."

WHY THE IDENTIFICATION IS CLEAN ([HS22] Section III.A, verbatim): "the payment
date, which on average occurs 22 days after the ex-date, and so is on average
43 days after the initial announcement. The payment date is the date when cash
is disbursed, and lacks economically meaningful news or tax implications." And:
"Once the dividend is declared, companies have a legal obligation to pay it."

============================================================================
WHY THIS IS A NEW MODULE AND NOT A cross_sectional.py FAMILY
============================================================================
The same reason vol_regime_timing.py and rebalancing_pressure_timing.py are
not, and this module deliberately copies the latter's shape rather than
inventing a third: cross_sectional.screen_cross_sectional_universe ranks a
UNIVERSE of names on a per-ticker signal. This family has no cross-section. The
state variable is a single scalar per DAY -- the market-wide dollar dividend
paid that day and the day before -- belonging to no ticker at all, and the
traded object is ONE instrument (SPY) whose sign and size that scalar sets.
[HS22]'s own dependent variable is the value-weighted MARKET portfolio, not
individual stock returns.

What IS reused unmodified: metrics.sharpe_ratio, deflated_sharpe.
compute_deflated_sharpe, preservation_score.compute_preservation_metrics,
global_effective_n.dsr_n_trials, registration_scorecard.policy_d_verdict,
vol_regime_timing's block_bootstrap_sharpe_pvalue and _ols_beta_alpha, and
rebalancing_pressure_timing's _hc0_regression -- imported, not re-implemented.

============================================================================
THE CONSTRUCTION, QUOTED
============================================================================
THE STATE VARIABLE ([HS22] Table II Panel B, verbatim): "we examine whether or
not a given day's dividend payment is high relative to the payments made in the
previous 252 days. Specifically, we regress market returns on dummy variables
equal to one if the cumulative dividend payment on day t and t-1 is in the top
2 weeks (10 days), quarter (63 days), third (84 days) or half (126 days) of
days in the past year, and equal to zero otherwise."

    S_t    = D_t + D_{t-1}                     the two-day cumulative dollars
    x_t    = scale(S_t)                        one of three published scalings
    high_t = 1 if x_t is in the top N of {x_{t-251} .. x_t}, else 0

THE PAPER CHOSE THIS RULE FOR EXACTLY THIS PURPOSE, verbatim: "to use a simple
rule that is easy to interpret and EX-ANTE TRADABLE". It is not a portfolio
this build invented around a regression coefficient.

THE THREE SCALINGS, all published:
  raw       x_t = S_t. Table II Panel B literally: no scaling at all. PRIMARY.
  mktcap    x_t = S_t / MktCap_{t-1}. Table I's payment yield, whose
            denominator is verbatim "the previous day's total market
            capitalization".
  abnormal  x_t = S_t / mean(D over trading days t-20 .. t-272). Table II
            Panel A verbatim ("dividends on days t and t-1 divided by the
            average daily dividend paid over the prior year") with footnote
            12's exact window verbatim ("We calculate this average using the
            trading days from t-20 to t-272. The average year contains 252
            trading days and we skip about a month (20 trading days) to ensure
            the denominator excludes any recent market information").
            PRICE-INDEPENDENT: the paper's own answer to any circularity
            concern about the market-cap denominator.

AND THE PLACEBO, TRADED:
  future_ph x_t = D_{t+1} + D_{t+2}. [HS22] Table I columns 5-6. **PRE-DECLARED
            TO FAIL**, and NOT point-in-time tradeable -- it deliberately reads
            dividends dated after the formation. The paper's own result is that
            these coefficients "are economically small and insignificant",
            because cash that has not yet arrived cannot be reinvested. It is
            the matched negative control for the three real scalings.

THE POSITION -- DEMEANED, AND THERE IS EXACTLY ONE SIZING:

    position_t = high_t - N/252

A long-only "hold SPY on high-dividend days" book is long the market a
predictable fraction of the time, so its Sharpe would be dominated by the
EQUITY PREMIUM rather than by anything [HS25] claims. Subtracting the
PRE-DECLARED unconditional frequency N/252 makes the book market-neutral by
construction and makes it the exact traded analogue of the Table II Panel B
dummy COEFFICIENT, which is the number the paper actually reports. N/252 is
DEFINITIONAL -- the frequency of a top-N-of-252 rank -- not estimated from the
sample, so no in-sample quantity enters the position. The long-only Sharpe is
still reported as a diagnostic so the equity-premium share of any positive is
visible as a number rather than as an argument.

THE TIMING CONTRACT, and it is the paper's central claim rather than a
modelling liberty: the position held over day t is formed at the close of day
t-1 from x_t, which depends on D_t and D_{t-1}. Using day t's OWN dividend is
NOT look-ahead -- the amount and date were declared on average 43 days earlier
and are a legal obligation. assert_no_lookahead() checks this on the real
calendar rather than asserting it in prose: for the `payment` dating every
dividend contributing to D_t must carry an ex-date STRICTLY BEFORE t, and the
count of violations is zero or the run refuses to proceed.

============================================================================
THE DATA DEVIATION -- PAYMENT DATE vs EX-DATE. THE BIG ONE.
============================================================================
[HS22] Section II, verbatim: "Unless otherwise noted, when we refer to the
timing of a dividend, we mean the payment date." The choice is deliberate and
defended: the payment date "lacks economically meaningful news or tax
implications", where the ex-date is precisely "when any implications of
receiving a dividend payment, such as tax consequences, are resolved."

THIS PROJECT'S EXISTING DIVIDEND INFRASTRUCTURE HAS EX-DATES ONLY.
cross_sectional_dividend_month.py, DividendEvent, build_ex_date_calendar and
data/dividend_month_ex_date_calendar.json are all ex-date objects, and that is
a property of the FEED rather than an oversight:
YFinanceProvider.get_dividend_history's own docstring says so -- "THE INDEX IS
THE EX-DIVIDEND DATE, NOT THE PAYMENT DATE ... A caller that needs PAYMENT
dates does not have them here and must say so; nothing in this method can
recover one." RE-VERIFIED LIVE 2026-09-06 against the endpoints themselves
rather than taken on the docstring's word: .dividends and .actions carry a
single date index and columns ['Dividends','Stock Splits'], with no
payment-date field of any kind.

TWO FREE PAYMENT-DATE SOURCES WERE FOUND, TESTED LIVE, AND MEASURED BEFORE THE
GRID WAS FROZEN:

 (i) yfinance's PER-TICKER `.calendar` endpoint carries BOTH 'Ex-Dividend Date'
     and 'Dividend Date' (the PAYMENT date) -- ONE observation per ticker, not
     a history. Coverage measured on this project's own point-in-time pool: 486
     of 496 dividend payers (98.0%) return a usable pair. On a 50-name random
     pre-check the implied lag ran min 7 / median 21 / mean 21.2 / max 34
     calendar days, WHICH MATCHES [HS22]'s OWN STATED "on average 22 days after
     the ex-date" almost exactly, on a universe and a window the paper never
     saw. That agreement is why this imputation is evidence-backed rather than
     a guess.
 (ii) NASDAQ'S dividend-history API returns REAL HISTORICAL (ex, record,
     DECLARATION, payment) tuples. IT CANNOT BE PRIMARY, for a structural
     rather than transient reason: it answers, verbatim and repeatably,
     "Dividend History for Non-Nasdaq symbols is not available" for NYSE names.
     Measured on a random 60-name sample of this project's own universe: 9
     covered (15.0%), 38 refused as non-Nasdaq, 4 no-dividend, 9 other-empty, 0
     HTTP errors. A market-wide aggregate on a source that structurally
     excludes the NYSE would be missing most of the dividend dollars in the
     market. It is used ONLY as INDEPENDENT GROUND TRUTH (fidelity check F7).

THE ADOPTED IMPUTATION:

    payment_date(i,k) = next trading day on or after [ ex_date(i,k) + L_i ]

with L_i the ticker's own calendar-day lag from (i), falling back to the
universe median. Rolled FORWARD only -- a payment landing on a weekend cannot
be a trading day, and rolling backward would move cash earlier than it could
have arrived.

WHICH DIRECTION THE RESIDUAL ERROR BIASES THE RESULT (pre-registration 3.1,
restated because it must travel with the numbers):
 * ATTENUATION IS FIRST-ORDER AND RUNS AGAINST THIS FAMILY. Per-event timing
   error moves dollars out of the correct (t, t-1) bucket into a wrong one.
   That is classical measurement error in the regressor: it biases the
   coefficient TOWARD ZERO. A NULL HERE IS THEREFORE WEAK EVIDENCE AGAINST THE
   PAPER, and the report says so rather than reporting a null as a refutation.
 * A CONSTANT PER-FIRM SHIFT IS THE BENIGN CASE, and F7 measures the residual
   jitter against Nasdaq's real pay dates instead of assuming it.
 * THE CHANNEL THAT COULD MANUFACTURE A FALSE POSITIVE IS THE EX-DATE ARM'S,
   NOT THE PAYMENT ARM'S. The ex-date carries large, long-documented price
   effects the payment date does not -- the ex-day drop, and the run-up and
   reversal the SAME TWO AUTHORS document in JFE 2013 and that THIS PROJECT has
   already measured on its own data (+12.84bp run-up, -18.08bp reversal;
   cross_sectional_dividend_month.py section 5). So an ex-date-anchored signal
   can pick up a REAL effect that is NOT this mechanism. That is why `ex_date`
   is a counted arm rather than the primary, and why a positive appearing ONLY
   there is pre-declared to be read as evidence for the WRONG mechanism.

THE EX-DATE ARM IS KEPT because it is what this project's infrastructure
natively gives (a successor needs to know what that buys), and because carrying
it means resolving the ambiguity COSTS TRIALS instead of being a free choice
made after seeing which one worked -- the same device
rebalancing_pressure_timing.py used for its trigger-sidedness ambiguity.

============================================================================
THE OTHER DEVIATIONS
============================================================================
UNIVERSE. [HS22] uses ALL CRSP ordinary common shares (codes 10/11) on
NYSE/NASDAQ/AMEX, 1926-2018. This build uses the point-in-time S&P 500,
per-date masked by cross_sectional_earnings_premium.build_membership_frame.
NOTE THE ASYMMETRY WITH THIS PROJECT'S OTHER HARTZMARK-SOLOMON FAMILY:
cross_sectional_dividend_month.py had to disclose that large-cap-only is where
a CROSS-SECTIONAL price-pressure effect should be SMALLEST. That argument does
NOT transfer here, because this family's object is an AGGREGATE market-wide
dollar flow and the S&P 500 is the large majority of US market cap and of US
dividend dollars. It is still a proxy: excluded small- and mid-caps pay on
their own calendars, and their absence adds timing noise to the aggregate.

DEPENDENT VARIABLE. [HS22] uses the CRSP value-weighted market portfolio; this
uses SPY total return off the point-in-time price store, consistent with the
universe. SPY is net of a ~9bp/yr expense ratio, a constant drift the
regression intercept absorbs freely and which cannot manufacture predictability
from a mean-reverting dividend-timing signal.

WINDOW, AND IT IS THIS BUILD'S SEVEREST LIMITATION. [HS22]: 1926-2018, ~24,000
daily observations. Here: formations from 2018-01-02, roughly 2,100 trading
days -- about ONE ELEVENTH. What binds the start is NOT the obvious thing:
point-in-time membership begins 2015-01-07, but the SEC share counts needed to
turn per-share dividends into DOLLARS begin at frame CY2017Q3 with a 90-day
visibility lag, so no dollar aggregate exists before ~2017-12-29. THE WHOLE
GRID USES THAT ONE WINDOW, including specs needing no share counts, so sigma_SR
measures spec differences rather than universe differences.

NO YEAR-BY-MONTH FIXED EFFECTS IN THE TRADED BOOK. [HS22]'s stronger columns
all add them, and a TRADED PORTFOLIO CANNOT: they are estimated using the whole
sample including the future. The fidelity regressions report both the no-FE and
FE specifications because both are the paper's; the traded specs use no
controls at all. That is why the CALENDAR CONTROL SPECS exist -- the paper's
own stated purpose for its fixed effects is that they control "for specific
calendar effects", and a portfolio has to defend against those structurally.

SHARE COUNTS ARE SEC-FILED, NOT CRSP, and the SPLIT-BASIS HAZARD is named
because getting it wrong would silently scale the numerator: yfinance dividend
amounts are split-adjusted into TODAY's share units while SEC counts are the
RAW counts filed at the time, so multiplying them directly understates a
pre-split firm's dollars by its cumulative split factor. Both are put on ONE
basis with cross_sectional_ivol.split_adjust_share_counts -- the same function
cross_sectional_buyback.py uses for the identical hazard -- before any product
is formed, and F8 checks the result against the implied aggregate dividend
yield rather than trusting it.

"ORDINARY CASH DIVIDENDS" IS NOT SEPARATELY IDENTIFIABLE. [HS22] restricts to
ordinary cash dividends by CRSP distribution code; Yahoo's actions feed has no
distribution code, so SPECIALS ARE INCLUDED. They are large and rare, so they
push the aggregate's extreme right tail -- precisely the top-10-day bucket this
family trades. Direction: a special IS cash that gets reinvested, so including
it is arguably faithful to the MECHANISM even where it is unfaithful to the
paper's SAMPLE. Not adjusted; disclosed.

============================================================================
WHAT COULD MAKE A POSITIVE RESULT HERE FAKE -- CHECKED IN-MODULE
============================================================================
 1. THE TURN-OF-THE-MONTH EFFECT, and this is the big one. Firms pay on the
    1st, 10th, 15th and month-end, so a "high aggregate dividend day" indicator
    is MECHANICALLY substantially a CALENDAR indicator. The turn-of-the-month
    effect (Ariel 1987; Lakonishok & Smidt 1988) is a large, independently
    documented equity return regularity that would produce exactly the pattern
    this family looks for, with no dividend mechanism at all. [HS22] defends
    against it with year-by-month fixed effects; a portfolio cannot. The two
    `tom_ctrl_*` specs are the whole defence, they contain NO dividend data,
    and their pre-declared reading is fixed in the pre-registration section 5:
    if either matches or beats the dividend specs, this family measured
    turn-of-the-month wearing a dividend costume, and the report says so
    REGARDLESS OF THE DSR.
 2. REVERSE CAUSALITY / SPURIOUS CALENDAR CORRELATION -- answered by the
    paper's own future-dividend placebo, run here as both a traded spec
    (`future_ph`) and a regression (F2), with a pre-declared VETO.
 3. THE EQUITY PREMIUM IN DISGUISE -- answered structurally by the demeaned
    sizing, and measured by F9's beta and beta-hedged Sharpe plus the long-only
    Sharpe reported beside every spec.
 4. PUBLICATION AND CROWDING. Circulated November 2022, published in the AER
    September 2025, about a flow that is public and known 43 days ahead. Every
    spec's Sharpe is reported before and after the November 2022 circulation.
 5. THE SEARCH THAT LED HERE IS NOT ALL IN n_trials. 34 is the size of THIS
    family, declared before any return was computed. It does not cover the
    choice to read this particular paper, nor that this is this project's
    SECOND Hartzmark-Solomon family after cross_sectional_dividend_month.py.
    Both DSRs are upper bounds.

AND THE ARITHMETIC THAT SAYS THE VERDICT IS NEARLY FOREORDAINED, done in
advance in pre-registration 10.2 from the paper's OWN Table III magnitudes: a
demeaned long/short book at N=126 has an expected gross Sharpe of ~0.26 and at
N=10 of ~0.30, and on a sample 1/11 the paper's length the expected F1
t-statistic is ~0.98. **A PERFECT, UNDECAYED, ZERO-COST REPLICATION OF THE
PAPER'S OWN REPORTED MAGNITUDE WOULD STILL FAIL THIS PROJECT'S 0.95 BAR AND ITS
0.50 FLOOR.** That is not a criticism of the paper, which reports a real
economic effect and never claims a tradeable Sharpe; it is a statement about
what this family can possibly conclude, and it is why a null here is reported
as "could not detect", never as "refuted".

RESIDUAL BIASES NOT FIXED, only disclosed: SPY was chosen today from
instruments that still exist and are still liquid; formation is assumed
executable at the exact closing print; and the dividend calendar is a vendor
scrape whose historical revisions this build cannot see.

============================================================================
ERRATA -- DEFECTS FOUND AFTER THE FIRST RUN
============================================================================
An independent re-derivation of the headline numbers, written WITHOUT
importing this module's backtest, indicator or position code, reproduced
divpay_raw_payment_top10 exactly (2,180 days, Sharpe +0.4030) and FAILED to
reproduce the control (+0.1906 against a reported +0.4426). Chasing that gap
found E1. E2 and E3 came out of the same pass. They are listed here rather
than silently repaired, because a family whose whole claim is "we did not
overstate" has to show its corrections.

 E1 THE TWO CONTROL SPECS SHARED ONE INDICATOR, AND IT FLIPPED A VETO.
    build_indicator called turn_of_month_indicator() with its module DEFAULTS
    for both controls, so tom_ctrl_1d and tom_ctrl_4d were the same 4-day
    series (measured: identical n_high = 419, identical long-only Sharpe
    +0.5399) differing only in the demeaning constant. Demeaning a 4-day
    indicator by 1/21 instead of 4/21 leaves a PERMANENT +0.1446 net-long
    position, so tom_ctrl_1d's Sharpe was substantially the EQUITY PREMIUM --
    exactly what the demeaned sizing exists to remove -- and it read +0.4426
    where the correctly-specified one-day control reads +0.1906.
    CONSEQUENCE, AND IT RUNS IN THE DIRECTION THAT FLATTERS THIS FAMILY:
    pre-declared VETO (ii) tripped on the mis-specified control (+0.4426
    against the best dividend spec's +0.4030) and does NOT trip once the
    control is built as the pre-registration specifies. The fix is therefore
    reported loudly rather than quietly, because "we fixed a bug and a veto
    against us went away" is the single most suspicious-looking correction a
    build can make. What makes it defensible is that the pre-registration
    fixes the one-day window in writing, committed before any number existed:
    the code did not implement the frozen document, and now it does.
    The window is now carried on the SPEC and its demeaning constant is
    DERIVED from that window, so the two can never drift apart again; a test
    pins both.
 E2 THE PAYMENT-DATE ROLL-FORWARD GUARDED ONLY THE END OF THE PANEL.
    np.searchsorted returns 0 for a target before the panel, so 6,843 of
    24,712 pre-panel events (ex-dates 2012-01-03..2016-05-05) were being
    assigned to the panel's first trading day -- the exact pile-up
    build_payment_events' own docstring forbids at the other end. It moved no
    published number (all of them predate the share-count visibility start and
    were already dropped for having no share count; `counted` stayed at
    11,499) but it inflated the skip tally and would have detonated for the
    first successor to extend the share-count history. Fixed, with a
    regression test.
 E3 THE ABNORMAL ARM'S BURN-IN ARTIFACT -- see
    AbnormalBurnInDiagnostic, which is a full post-hoc treatment rather than a
    one-line erratum because it nearly produced a FABRICATED FINDING against
    the paper. NOT fixed, deliberately: fixing it means moving a frozen
    formation window after seeing results. Its eight specs' numbers should be
    treated as unreliable and it is the first thing a successor should repair.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.borrow_cost import GENERAL_COLLATERAL_BPS_PER_YEAR
from app.services.research_lab.cross_sectional_ivol import split_adjust_share_counts
from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe

# dsr_n_trials is imported ALONE and on one line, deliberately:
# tests/test_global_effective_n.py's "every DSR call site routes through the
# pooled denominator" guard scans module source for the literal string
# "global_effective_n import dsr_n_trials", and a wrapped multi-name import
# would make this module look unpooled to it when it is not.
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio
from app.services.research_lab.preservation_score import compute_preservation_metrics
from app.services.research_lab.rebalancing_pressure_timing import _hc0_regression
from app.services.research_lab.registration_scorecard import policy_d_verdict
from app.services.research_lab.vol_regime_timing import (
    MIN_REPLAY_TRADING_DAYS,
    _ols_beta_alpha,
    block_bootstrap_sharpe_pvalue,
)

logger = logging.getLogger(__name__)

DIVIDEND_PAYMENT_FAMILY_NAME = "dividend_payment_pressure"

# The traded instrument. ONE instrument -- see the module docstring on why this
# is not a cross_sectional.py family. Same ticker and same call
# vol_regime_timing.py and rebalancing_pressure_timing.py already use.
MARKET_TICKER = "SPY"
TRADED_UNIVERSE: tuple[str, ...] = (MARKET_TICKER,)

# On-disk cache of the fetched dividend/payment/share-count inputs, following
# the data/ convention the DMP ex-date calendar and the EAP announcement
# calendar use. Gitignored as a refetchable VENDOR INPUT, not a result -- the
# results live in cross_sectional_trial_results and data/research_runs/.
# Rebuilt from scratch by data/research_runs/fetch_dividend_payment_calendar.py.
PAYMENT_CACHE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "dividend_payment_calendar.json"
)

# --- the paper's own constants, inherited and never searched ---------------

# [HS22] Table II Panel B, verbatim: "the top 2 weeks (10 days), quarter (63
# days), third (84 days) or half (126 days) of days in the past year". All four
# the paper names are used; none is dropped, because dropping one would be a
# free choice this family does not get to make.
TOP_N_THRESHOLDS: tuple[int, ...] = (10, 63, 84, 126)

# [HS22] Table II Panel B: "the previous 252 days".
RANK_WINDOW_DAYS = 252

# [HS22] Table I columns 3-4: "the cumulative dividend payment yield on the
# payment date and the day before".
CUMULATION_DAYS = 2

# [HS22] footnote 12, verbatim: "We calculate this average using the trading
# days from t-20 to t-272." Inclusive at both ends, hence 253 trading days.
ABNORMAL_SKIP_DAYS = 20
ABNORMAL_LOOKBACK_DAYS = 272

# [HS22] Table I columns 5-6: the placebo reads "future dividends (on day t+1
# and t+2)".
PLACEBO_FUTURE_LAGS: tuple[int, ...] = (1, 2)

# Lakonishok & Smidt (1988) / Ariel (1987) turn-of-the-month window: the last
# trading day of a month plus the first three of the next. The CONTROL's
# window, fixed a priori from that literature rather than tuned here.
TOM_WINDOW_LAST_DAYS = 1
TOM_WINDOW_FIRST_DAYS = 3

# --- pre-declared family parameters ----------------------------------------

# Uniform, pre-declared, never fitted. [HS25] abstract: dividend buying pressure
# "predicts HIGHER value-weighted market returns".
DIVIDEND_PRESSURE_DIRECTION = 1.0

DIVIDEND_PAYMENT_N_TRIALS = 34

# One-way, per unit of gross notional traded. A SINGLE-INSTRUMENT book trades
# 1.0 unit of gross notional per unit of position change, NOT the 2.0 a
# two-legged spread trades -- the difference from
# rebalancing_pressure_timing.REBALANCING_COST_BPS is deliberate and is stated
# here so it cannot look like a copied constant. Grounding:
# vol_regime_timing.py measures a one-cent bid/ask on SPY (~$6xx) at ~0.08bp of
# half-spread, so 1.0bp one-way carries ~12x the quoted half-spread.
DIVIDEND_PRESSURE_COST_BPS = 1.0
GROSS_NOTIONAL_PER_UNIT_POSITION = 1.0

# Per year, on the SHORT notional only. SOURCED, not assumed: Beneish, Lee &
# Nichols, "In Short Supply", JAE 60(1), 2015, p.15 (DCBS=1 fees average
# <34bp/yr), the conservative envelope over D'Avolio (2002) Table 3's 17bp
# value-weighted GC mean. This book is SHORT SPY most of the time by
# construction (the demeaned N=10 position is -10/252 on 96% of days), so the
# borrow charge matters here more than the turnover charge does.
DIVIDEND_PRESSURE_SHORT_BORROW_BPS_PER_YEAR = GENERAL_COLLATERAL_BPS_PER_YEAR

# 365, not 252 -- financing accrues on calendar days. Same reasoning as
# cross_sectional.FINANCING_DAYS_PER_YEAR and rebalancing_pressure_timing.py.
FINANCING_DAYS_PER_YEAR = 365.0

# Formations begin here. What binds it is NOT membership coverage (2015-01-07)
# but the SEC share counts the dollar aggregate needs: EARLIEST_FRAME CY2017Q3
# plus VISIBILITY_LAG_DAYS = 90 puts the first visible count at ~2017-12-29.
# The WHOLE grid uses this one window, including specs needing no share counts,
# so sigma_SR measures spec differences rather than universe differences.
DIVIDEND_PRESSURE_FORMATION_START = date(2018, 1, 2)

# Calendar padding fetched before the formation start, purely to warm the
# trailing 252-day rank window and the t-20..t-272 abnormal denominator.
# 272 trading days is ~385 calendar days; 600 is a comfortable margin and
# formations never occur in the padding.
HISTORY_PADDING_CALENDAR_DAYS = 600

# [HS22]'s own sample ends here; [HS22] was circulated 2022-11-01 and [HS25]
# published 2025-09-01. The circulation date is the closest available
# post-publication split, and it is weak: only ~2 of ~8.5 years sit after it.
PAPER_SAMPLE_END = date(2018, 12, 31)
PAPER_CIRCULATION_DATE = date(2022, 11, 1)

# Policy D bars, identical to every other family here.
VALIDATED_EDGE_BAR = 0.95
SCREENING_FLOOR = 0.50

DIVIDEND_PRESSURE_CITATION = (
    "Hartzmark & Solomon, 'Market-Wide Predictable Price Pressure', American Economic Review "
    "115(9), September 2025, pp. 3171-3213, doi:10.1257/aer.20231725 -- PEER REVIEWED, record "
    "verified at Crossref; the published body is paywalled (HTTP 403, not open access) and was "
    "NOT retrieved, so every quoted equation, coefficient and threshold comes from the NBER "
    "working-paper precursor w30688 (November 2022), which WAS fetched and read in full. "
    "Aggregate dollar dividends paid on days t and t-1 positively predict the value-weighted "
    "market return on day t; the top quintile of payment days earns about four times the bottom."
)

TOM_CONTROL_CITATION = (
    "CONTROL SPEC, not a candidate, and it contains NO dividend data: the turn-of-the-month "
    "calendar window of Ariel (1987) and Lakonishok & Smidt (1988). Dividends are paid on the "
    "1st, 10th, 15th and month-end, so a 'high aggregate dividend day' indicator is mechanically "
    "substantially a calendar indicator. Hartzmark & Solomon defend against this with "
    "year-by-month fixed effects, which a traded portfolio cannot have."
)


# ===========================================================================
# THE PAYMENT CALENDAR
# ===========================================================================


@dataclass(frozen=True)
class DividendPaymentEvent:
    """One cash distribution, carrying BOTH the date this project's feed
    actually supplies (the ex-date) and the payment date imputed from it.

    `amount_per_share` is SPLIT-ADJUSTED into today's share units, the basis
    YFinanceProvider.get_dividend_history returns. It is only ever multiplied
    by a share count that split_adjust_share_counts has put onto that SAME
    basis -- see the module docstring's SPLIT-BASIS HAZARD note, which is the
    one place this construction could silently scale the whole numerator."""

    ticker: str
    ex_date: date
    payment_date: date
    amount_per_share: float
    lag_days: int
    lag_source: str  # "ticker" | "universe_median"


@dataclass
class PaymentCalendarReport:
    """What the acquisition pass actually covered. Every field is a
    sample-construction fact that belongs in the run report."""

    n_tickers_requested: int = 0
    n_tickers_priced: int = 0
    n_tickers_with_dividends: int = 0
    n_ex_dates: int = 0
    n_tickers_with_ticker_lag: int = 0
    n_events_on_universe_median_lag: int = 0
    universe_median_lag_days: float = float("nan")
    lag_percentiles: dict[str, float] = field(default_factory=dict)
    n_tickers_with_share_counts: int = 0
    n_priced_without_cik: int = 0
    nasdaq_tally: dict[str, int] = field(default_factory=dict)
    fetch_start: date | None = None
    fetch_end: date | None = None
    missing_price_data: list[str] = field(default_factory=list)


@dataclass
class RawPaymentCache:
    """The parsed on-disk acquisition cache, before any trading calendar is
    applied. Kept as its own object so the fidelity checks that measure the
    DATA (F7, F8) can read it without going through the signal builders."""

    dividends: dict[str, list[tuple[date, float]]]
    yf_payment_lag: dict[str, dict]
    nasdaq_history: dict[str, list[dict]]
    share_counts: dict[str, list[tuple[date, date, float]]]
    report: PaymentCalendarReport


def load_payment_cache(path: Path = PAYMENT_CACHE_PATH) -> RawPaymentCache | None:
    """The cached dividend/payment/share-count inputs, or None if never built.

    Deliberately a plain load with no fallback to a live fetch, for exactly the
    reason cross_sectional_dividend_month.load_dividend_cache gives: a
    screening run must replay a FIXED input, and silently re-fetching from an
    unofficial scraping API mid-run would mean two runs of the same script
    could disagree with no record of why."""
    if not path.exists():
        return None
    payload = json.loads(path.read_text())

    dividends = {
        ticker: [(date.fromisoformat(iso), float(amount)) for iso, amount in rows]
        for ticker, rows in payload["dividends"].items()
    }
    share_counts = {
        ticker: [
            (date.fromisoformat(r["as_of"]), date.fromisoformat(r["available"]), float(r["shares"]))
            for r in rows
        ]
        for ticker, rows in payload.get("share_counts", {}).items()
    }
    report = PaymentCalendarReport(
        n_tickers_requested=int(payload.get("n_tickers_requested", 0)),
        n_tickers_priced=int(payload.get("n_tickers_priced", 0)),
        n_tickers_with_dividends=int(payload.get("n_tickers_with_dividends", 0)),
        n_ex_dates=sum(len(v) for v in dividends.values()),
        n_tickers_with_share_counts=len(share_counts),
        n_priced_without_cik=int(
            (payload.get("share_count_diagnostics") or {}).get("n_priced_without_cik", 0)
        ),
        nasdaq_tally=dict(payload.get("nasdaq_tally") or {}),
        fetch_start=date.fromisoformat(payload["fetch_start"]),
        fetch_end=date.fromisoformat(payload["fetch_end"]),
        missing_price_data=list(payload.get("missing_price_data") or []),
    )
    return RawPaymentCache(
        dividends=dividends,
        yf_payment_lag=dict(payload.get("yf_payment_lag") or {}),
        nasdaq_history=dict(payload.get("nasdaq_history") or {}),
        share_counts=share_counts,
        report=report,
    )


def resolve_payment_lags(yf_payment_lag: dict[str, dict]) -> tuple[dict[str, int], float]:
    """({ticker: calendar-day ex->pay lag}, universe median lag).

    A NON-POSITIVE OR ABSURD LAG IS REFUSED RATHER THAN USED. Yahoo's
    `.calendar` can return a STALE pair -- a payment date belonging to the
    previous distribution alongside an already-updated ex-date -- which
    presents as a negative lag. A payment cannot precede its own ex-date, so
    such a row is dropped and the ticker falls back to the universe median.
    The upper bound is equally structural: [HS22] reports the gap averaging 22
    days and this project's own 50-name pre-check measured a maximum of 34, so
    a lag beyond a quarter is not a dividend schedule, it is a parse error."""
    lags: dict[str, int] = {}
    for ticker, row in yf_payment_lag.items():
        value = row.get("lag_days")
        if value is None:
            continue
        lag = int(value)
        if lag < MIN_PLAUSIBLE_LAG_DAYS or lag > MAX_PLAUSIBLE_LAG_DAYS:
            continue
        lags[ticker] = lag
    median = float(np.median(list(lags.values()))) if lags else float("nan")
    return lags, median


# A payment cannot precede its own ex-date, so 0 is the hard floor (same-day
# payment is theoretically possible and is not refused). The ceiling is 92
# calendar days -- one quarter -- because a lag beyond a full dividend cycle
# would mean the imputed payment lands after the NEXT ex-date, which no real
# schedule does. [HS22]: the gap averages 22 days; this project's own live
# pre-check measured a maximum of 34.
MIN_PLAUSIBLE_LAG_DAYS = 0
MAX_PLAUSIBLE_LAG_DAYS = 92


def build_payment_events(
    cache: RawPaymentCache, trading_days: pd.DatetimeIndex
) -> tuple[list[DividendPaymentEvent], PaymentCalendarReport]:
    """Every distribution, with its payment date imputed and rolled FORWARD to
    the next trading day.

    Rolled forward only: a payment landing on a weekend or holiday cannot be a
    trading day in a daily return panel, and rolling BACKWARD would move cash
    earlier than it could possibly have arrived.

    AN EVENT WHOSE IMPUTED PAYMENT DATE FALLS OUTSIDE THE PANEL AT EITHER END
    IS DROPPED, never clamped to the nearest edge. Clamping would pile a mass
    of unrelated payments onto one date and MANUFACTURE the largest dividend
    day in the sample -- which, on a top-N-of-252 rank, is precisely the day
    this family trades.

    THE START-OF-PANEL HALF OF THAT GUARD WAS MISSING IN THE FIRST BUILD AND
    IS RECORDED HERE RATHER THAN QUIETLY ADDED. np.searchsorted returns 0 for
    a target before the panel, so every pre-panel payment was being assigned to
    the panel's FIRST trading day: measured on the real calendar, 6,843 of
    24,712 events (27.7%), with ex-dates running 2012-01-03 to 2016-05-05, all
    landing on 2016-05-12. It changed no published number in this build,
    because every one of those events predates the SEC share-count visibility
    start and was therefore already dropped downstream for having no share
    count -- but it inflated the `no_share_count` skip tally, it contradicted
    this docstring's own stated contract, and it would have detonated for the
    first successor who extended the share-count history, which is exactly what
    fixing the abnormal-arm burn-in requires."""
    lags, median_lag = resolve_payment_lags(cache.yf_payment_lag)
    calendar_days = trading_days.normalize()
    day_values = calendar_days.to_numpy()

    events: list[DividendPaymentEvent] = []
    n_median_fallback = 0
    for ticker, rows in cache.dividends.items():
        ticker_lag = lags.get(ticker)
        for ex_date, amount in rows:
            if amount <= 0.0 or not np.isfinite(amount):
                continue
            if ticker_lag is not None:
                lag, source = ticker_lag, "ticker"
            elif np.isfinite(median_lag):
                lag, source = int(round(median_lag)), "universe_median"
                n_median_fallback += 1
            else:
                continue
            target = np.datetime64(ex_date + timedelta(days=lag), "ns")
            # BOTH edges, deliberately. searchsorted returns 0 for a target
            # before the panel and len() for one after it; only the second was
            # guarded in the first build. See the docstring.
            if len(day_values) == 0 or target < day_values[0]:
                continue
            position = int(np.searchsorted(day_values, target, side="left"))
            if position >= len(day_values):
                continue
            events.append(
                DividendPaymentEvent(
                    ticker=ticker,
                    ex_date=ex_date,
                    payment_date=pd.Timestamp(day_values[position]).date(),
                    amount_per_share=float(amount),
                    lag_days=lag,
                    lag_source=source,
                )
            )

    events.sort(key=lambda e: (e.payment_date, e.ticker))
    report = cache.report
    report.n_tickers_with_ticker_lag = len(lags)
    report.n_events_on_universe_median_lag = n_median_fallback
    report.universe_median_lag_days = median_lag
    values = sorted(lags.values())
    if values:
        report.lag_percentiles = {
            "min": float(values[0]),
            "p10": float(values[int(0.1 * (len(values) - 1))]),
            "median": float(np.median(values)),
            "p90": float(values[int(0.9 * (len(values) - 1))]),
            "max": float(values[-1]),
            "mean": float(np.mean(values)),
        }
    return events, report


# ===========================================================================
# THE DOLLAR AGGREGATE AND ITS DENOMINATOR
# ===========================================================================


def build_share_count_frame(
    cache: RawPaymentCache,
    close: pd.DataFrame,
    splits_by_ticker: dict[str, pd.Series],
) -> tuple[pd.DataFrame, list[str]]:
    """SEC point-in-time share counts, SPLIT-ADJUSTED onto the same basis as
    `close`, forward-filled as a STEP function from each count's own
    VISIBILITY date.

    THE SPLIT ADJUSTMENT IS THE LOAD-BEARING STEP and is the module docstring's
    named hazard: SEC files the RAW count outstanding at the time, while both
    Yahoo's `Close` and Yahoo's dividend amounts are expressed in TODAY's share
    units. cross_sectional_ivol.split_adjust_share_counts is the function this
    project already uses for exactly this join (see
    cross_sectional_buyback.py), and it is imported rather than re-derived.

    Each count appears from its `available` date -- as_of + the provider's
    90-day visibility lag -- and is carried forward unchanged until superseded.
    No interpolation and no back-fill: a date before a ticker's first VISIBLE
    count is NaN, which is the correct answer for a count this project could
    not have observed there."""
    frames: dict[str, pd.Series] = {}
    no_counts: list[str] = []
    for ticker in close.columns:
        rows = cache.share_counts.get(str(ticker))
        if not rows:
            no_counts.append(str(ticker))
            continue
        raw = pd.Series(
            {pd.Timestamp(as_of): shares for as_of, _available, shares in rows}
        ).sort_index()
        adjusted = split_adjust_share_counts(raw, splits_by_ticker.get(str(ticker)))
        # Re-index the ADJUSTED counts onto their own AVAILABILITY dates, so a
        # count is readable only from the day this project could have seen it.
        availability = {
            pd.Timestamp(as_of): pd.Timestamp(available) for as_of, available, _ in rows
        }
        visible = pd.Series(
            {availability[ts]: value for ts, value in adjusted.items() if ts in availability}
        ).sort_index()
        visible = visible[~visible.index.duplicated(keep="last")]
        if visible.empty:
            no_counts.append(str(ticker))
            continue
        union = visible.index.union(close.index).sort_values()
        frames[str(ticker)] = visible.reindex(union).ffill().reindex(close.index)
    frame = pd.DataFrame(frames, index=close.index) if frames else pd.DataFrame(index=close.index)
    return frame, no_counts


def build_daily_dividend_dollars(
    events: list[DividendPaymentEvent],
    share_frame: pd.DataFrame,
    membership: pd.DataFrame,
    trading_days: pd.DatetimeIndex,
    *,
    use_ex_date: bool,
) -> tuple[pd.Series, dict[str, int]]:
    """D_t -- the market-wide DOLLAR dividend attributed to each trading day.

        D_t = SUM over point-in-time index members i paying on day t of
              amount_per_share(i) * split_adjusted_shares(i, t)

    `use_ex_date` selects the DATING AXIS of the pre-registration's deviation
    D1: False dates each payment by its imputed PAYMENT date (the paper's own
    explicit choice), True by the raw EX-DATE (what this project's existing
    infrastructure natively provides). Both are counted grid arms so that
    resolving the ambiguity costs trials.

    A distribution whose ticker has no VISIBLE share count on that day
    contributes NOTHING and is counted in `skipped`. That is the honest
    treatment -- a per-share amount without a share count is not a dollar
    figure -- but it is also a real downward bias on the aggregate's LEVEL, so
    the count is reported rather than absorbed. Because the signal is a RANK
    within a trailing window, a level bias that is roughly stationary in
    composition affects the signal far less than it affects the aggregate, but
    that is a mitigation, not an absence.

    An ex-date-dated event landing on a non-trading day is dropped rather than
    rolled: unlike an imputed payment date, an ex-date IS a market date by
    definition, so one that is not in the panel is a data defect, not a
    calendar artifact, and is counted as such."""
    # FOUR DISTINCT REASONS AN EVENT CONTRIBUTES NOTHING, counted separately
    # because they mean different things and a single bucket would hide which
    # one is doing the work. `absent_from_price_panel` in particular is a
    # COVERAGE failure (the ticker never resolved a price at all), where
    # `not_a_member` is the point-in-time universe doing its job.
    skipped = {
        "counted": 0,
        "absent_from_price_panel": 0,
        "not_a_member": 0,
        "no_share_count": 0,
        "date_off_panel": 0,
    }
    positions = {ts: i for i, ts in enumerate(trading_days)}
    member_columns = {t: i for i, t in enumerate(membership.columns)}
    share_columns = {t: i for i, t in enumerate(share_frame.columns)}
    member_values = membership.to_numpy(dtype=bool)
    share_values = share_frame.to_numpy(dtype=float)
    values = np.zeros(len(trading_days), dtype=float)

    for event in events:
        anchor = event.ex_date if use_ex_date else event.payment_date
        index = positions.get(pd.Timestamp(anchor))
        if index is None:
            skipped["date_off_panel"] += 1
            continue
        ticker = event.ticker
        member_column = member_columns.get(ticker)
        if member_column is None:
            skipped["absent_from_price_panel"] += 1
            continue
        if not bool(member_values[index, member_column]):
            skipped["not_a_member"] += 1
            continue
        share_column = share_columns.get(ticker)
        if share_column is None:
            skipped["no_share_count"] += 1
            continue
        shares = share_values[index, share_column]
        if not np.isfinite(shares) or shares <= 0.0:
            skipped["no_share_count"] += 1
            continue
        values[index] += event.amount_per_share * float(shares)
        skipped["counted"] += 1

    dollars = pd.Series(values, index=trading_days, name="dividend_dollars")
    return dollars, skipped


def build_aggregate_market_cap(
    close: pd.DataFrame, share_frame: pd.DataFrame, membership: pd.DataFrame
) -> pd.Series:
    """[HS22] Table I's denominator: "the previous day's total market
    capitalization", built as SUM over point-in-time members of
    split-adjusted-close * split-adjusted-shares.

    `close` MUST be Yahoo's split-adjusted-but-NOT-dividend-adjusted Close,
    which is what YFinanceProvider.get_market_cap_basis returns and which that
    method's docstring explains at length: auto_adjust=True back-adjusts every
    historical price DOWNWARD by the dividends paid since, by a DIFFERENT
    factor per ticker, so multiplying a share count by it understates market
    cap by that factor. This function does not fetch, so it cannot choose
    wrongly on its own -- the caller's choice is pinned by a test."""
    aligned_shares = share_frame.reindex(index=close.index, columns=close.columns)
    aligned_members = membership.reindex(index=close.index, columns=close.columns).fillna(False)
    caps = close.where(aligned_members) * aligned_shares.where(aligned_members)
    return caps.sum(axis=1, min_count=1).rename("aggregate_market_cap")


# ===========================================================================
# THE SIGNALS
# ===========================================================================


def two_day_cumulative(dollars: pd.Series) -> pd.Series:
    """S_t = D_t + D_{t-1}. [HS22] Table I columns 3-4, verbatim: "the
    cumulative dividend payment yield on the payment date and the day before".

    min_periods equals the window, so the very first day of the panel yields
    NaN rather than a one-day sum masquerading as a two-day one."""
    return (
        dollars.rolling(CUMULATION_DAYS, min_periods=CUMULATION_DAYS)
        .sum()
        .rename("two_day_dollars")
    )


def abnormal_denominator(dollars: pd.Series) -> pd.Series:
    """[HS22] Table II Panel A footnote 12, verbatim: "We calculate this
    average using the trading days from t-20 to t-272. The average year
    contains 252 trading days and we skip about a month (20 trading days) to
    ensure the denominator excludes any recent market information."

    Implemented EXACTLY as stated: the mean of D over the 253 trading days
    t-272 .. t-20 inclusive, which is a 253-day rolling mean shifted forward by
    20 days. The skip is the whole point of the construction -- it is what
    makes the denominator independent of anything recent -- so it is
    implemented as a shift rather than approximated, and a unit test pins the
    exact window boundaries on a synthetic panel with a known answer."""
    window = ABNORMAL_LOOKBACK_DAYS - ABNORMAL_SKIP_DAYS + 1
    return (
        dollars.rolling(window, min_periods=window)
        .mean()
        .shift(ABNORMAL_SKIP_DAYS)
        .rename("abnormal_denominator")
    )


def future_cumulative(dollars: pd.Series) -> pd.Series:
    """[HS22] Table I columns 5-6's PLACEBO regressor: dividends paid on days
    t+1 and t+2.

    IT READS THE FUTURE ON PURPOSE and is NOT point-in-time tradeable. It is
    the paper's own falsification device -- cash that has not yet arrived
    cannot be reinvested, so this must NOT predict day t's return -- and every
    place its number appears says so."""
    shifted = [dollars.shift(-lag) for lag in PLACEBO_FUTURE_LAGS]
    return sum(shifted[1:], shifted[0]).rename("future_dollars")


def top_n_indicator(x: pd.Series, n: int, window: int = RANK_WINDOW_DAYS) -> pd.Series:
    """[HS22] Table II Panel B: 1 if x_t is in the top `n` of the trailing
    `window` days INCLUDING today, else 0.

    TIE HANDLING IS DECLARED RATHER THAN INHERITED FROM A SORT. A day counts as
    high when STRICTLY FEWER THAN n values in its own window exceed it. On a
    dollar aggregate exact ties are essentially impossible except at zero, but
    zero-dividend days do tie, and the alternative (an arbitrary
    first-seen tiebreak) would make the signal depend on row order. The
    consequence is that the REALIZED frequency of high days can exceed n/window
    where ties cluster; the realized frequency is reported beside the
    pre-declared n/252 so any inflation is visible as a number.

    The window includes today because the paper's question is whether TODAY's
    payment "is high relative to the payments made in the previous 252 days".
    That reads no future information: x_t is known at the formation, which is
    the paper's central claim (dividends are declared ~43 days ahead).

    Returns float with NaN wherever a full window is unavailable -- a partial
    window would rank today against a shorter history and silently change what
    "top 10 of a year" means."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if n > window:
        raise ValueError(f"n={n} cannot exceed the window {window}")

    values = x.to_numpy(dtype=float)
    out = np.full(len(values), np.nan, dtype=float)
    for i in range(window - 1, len(values)):
        current = values[i]
        if not np.isfinite(current):
            continue
        block = values[i - window + 1 : i + 1]
        if not np.isfinite(block).all():
            continue
        n_greater = int(np.count_nonzero(block > current))
        out[i] = 1.0 if n_greater < n else 0.0
    return pd.Series(out, index=x.index, name=f"top{n}")


def turn_of_month_indicator(
    index: pd.DatetimeIndex,
    *,
    first_days: int = TOM_WINDOW_FIRST_DAYS,
    last_days: int = TOM_WINDOW_LAST_DAYS,
) -> pd.Series:
    """THE CONTROL SIGNAL, and it touches no dividend data at all: 1 on the
    last `last_days` trading days of a month and the first `first_days` of the
    next.

    THE WINDOW IS A PARAMETER because the family declares TWO control specs at
    two different widths, and the first build wrongly served both from these
    defaults -- see build_indicator's CORRECTION note. `last_days = 0` is
    meaningful and is what tom_ctrl_1d uses: the first trading day of the month
    alone, with no month-end leg.

    Ariel (1987) and Lakonishok & Smidt (1988)'s turn-of-the-month window,
    fixed a priori from that literature. Derived from the TRADED calendar
    itself rather than from a holiday library, so "last trading day of the
    month" means the last day this book could actually have traded."""
    periods = index.to_period("M")
    counts: dict = {}
    for period in periods:
        counts[period] = counts.get(period, 0) + 1
    seen: dict = {}
    out = np.zeros(len(index), dtype=float)
    for i, period in enumerate(periods):
        seen[period] = seen.get(period, 0) + 1
        position_from_start = seen[period]
        position_from_end = counts[period] - seen[period]
        # Each leg is guarded by its own > 0 test so that a ZERO-width leg is
        # genuinely absent rather than accidentally always-true. last_days = 0
        # is not a degenerate case here, it is tom_ctrl_1d's actual
        # specification: the first trading day of the month alone.
        in_first_leg = first_days > 0 and position_from_start <= first_days
        in_last_leg = last_days > 0 and position_from_end < last_days
        if in_first_leg or in_last_leg:
            out[i] = 1.0
    return pd.Series(out, index=index, name=f"turn_of_month_{first_days}f{last_days}l")


def demeaned_position(indicator: pd.Series, frequency: float) -> pd.Series:
    """position_t = indicator_t - frequency.

    `frequency` is the PRE-DECLARED unconditional frequency of the high state
    (n/252 for a top-n rank, the structural share of turn-of-month days for the
    control), NOT the realized in-sample frequency. Using the realized one
    would put an in-sample statistic into the position and make the book
    unimplementable in real time; using the definitional one keeps it
    market-neutral in expectation and makes the book the exact traded analogue
    of [HS22] Table II Panel B's dummy COEFFICIENT.

    See the module docstring on why a long-only book is not screened here: its
    Sharpe would be dominated by the equity premium rather than by anything the
    paper claims. The long-only Sharpe is still reported as a diagnostic."""
    return (DIVIDEND_PRESSURE_DIRECTION * (indicator - frequency)).rename("position")


# ===========================================================================
# THE FAMILY
# ===========================================================================


@dataclass(frozen=True)
class DividendPressureSpec:
    spec_id: str
    signal_key: str
    dating: str  # "payment" | "ex_date" | "none" (controls)
    threshold_n: int | None
    frequency: float
    citation: str
    hypothesis: str
    is_control: bool = False
    is_placebo: bool = False
    # Control specs only: the turn-of-the-month window this spec's indicator
    # uses. Carried on the SPEC rather than read from module constants so the
    # two controls cannot silently share one indicator, which is exactly what
    # the first build did.
    tom_first_days: int = TOM_WINDOW_FIRST_DAYS
    tom_last_days: int = TOM_WINDOW_LAST_DAYS


@dataclass(frozen=True)
class SignalDefinition:
    key: str
    hypothesis: str
    citation: str
    is_control: bool
    is_placebo: bool
    dated: bool  # False for the calendar controls, which use no dividend data


_DIVIDEND_SIGNALS: tuple[SignalDefinition, ...] = (
    SignalDefinition(
        key="raw",
        hypothesis=(
            "[HS22] Table II Panel B LITERALLY: the two-day cumulative DOLLAR dividend, unscaled, "
            "ranked against the previous 252 days. High aggregate payment -> uninformed "
            "reinvestment -> higher same-day value-weighted market return. The paper's own most "
            "literal ex-ante rule and this family's PRIMARY definition."
        ),
        citation=DIVIDEND_PRESSURE_CITATION,
        is_control=False,
        is_placebo=False,
        dated=True,
    ),
    SignalDefinition(
        key="mktcap",
        hypothesis=(
            "[HS22] Table I's payment yield: the same two-day dollar total divided by 'the "
            "previous day's total market capitalization'. Paper's headline: coefficient 59.50, "
            "t = 3.32 (67.07, t = 3.47 with year-by-month fixed effects)."
        ),
        citation=DIVIDEND_PRESSURE_CITATION,
        is_control=False,
        is_placebo=False,
        dated=True,
    ),
    SignalDefinition(
        key="abnormal",
        hypothesis=(
            "[HS22] Table II Panel A's PRICE-INDEPENDENT abnormal dividend yield: the same "
            "two-day total divided by the mean daily dividend over trading days t-20..t-272. The "
            "paper's own answer to any circularity concern about the market-cap denominator, and "
            "it reports the two give similar magnitudes (2.7bp against 3.2bp per one SD)."
        ),
        citation=DIVIDEND_PRESSURE_CITATION,
        is_control=False,
        is_placebo=False,
        dated=True,
    ),
    SignalDefinition(
        key="future_ph",
        hypothesis=(
            "MATCHED NEGATIVE CONTROL, PRE-DECLARED TO FAIL, AND NOT POINT-IN-TIME TRADEABLE: "
            "[HS22] Table I columns 5-6's placebo, traded. Dividends paid on days t+1 and t+2, "
            "ranked the same way. Cash that has not yet arrived cannot be reinvested; the paper's "
            "own coefficients here are 'economically small and insignificant'."
        ),
        citation=DIVIDEND_PRESSURE_CITATION,
        is_control=False,
        is_placebo=True,
        dated=True,
    ),
)

DATINGS: tuple[str, ...] = ("payment", "ex_date")


def _build_dividend_pressure_family() -> list[DividendPressureSpec]:
    """The exact product _DIVIDEND_SIGNALS x DATINGS x TOP_N_THRESHOLDS, plus
    the two dating-independent calendar controls.

    The literal length of this list is the n_trials denominator the screen
    uses. Every definition counts, whether or not it survives the data floors,
    because shrinking the denominator to "specs that worked" would be gameable
    by declaring specs expected to fail -- and this family declares EIGHT that
    are (the four future_ph placebo cells at each of two datings)."""
    specs: list[DividendPressureSpec] = []
    for definition in _DIVIDEND_SIGNALS:
        for dating in DATINGS:
            for n in TOP_N_THRESHOLDS:
                specs.append(
                    DividendPressureSpec(
                        spec_id=f"divpay_{definition.key}_{dating}_top{n}",
                        signal_key=definition.key,
                        dating=dating,
                        threshold_n=n,
                        frequency=n / RANK_WINDOW_DAYS,
                        citation=definition.citation,
                        hypothesis=definition.hypothesis,
                        is_control=definition.is_control,
                        is_placebo=definition.is_placebo,
                    )
                )

    # The controls carry NO dividend data, so they are NOT duplicated across
    # the dating axis -- the two datings would produce byte-identical position
    # series and counting them twice would inflate the denominator with a
    # distinction that does not exist.
    # (spec_id, first_days, last_days, label). The frequency each is demeaned
    # by is DERIVED from its own window rather than typed, so the two can never
    # again drift apart from their indicators.
    for key, first_days, last_days, label in (
        ("tom_ctrl_4d", TOM_WINDOW_FIRST_DAYS, TOM_WINDOW_LAST_DAYS, "4d"),
        ("tom_ctrl_1d", 1, 0, "1d"),
    ):
        frequency = (first_days + last_days) / 21.0
        specs.append(
            DividendPressureSpec(
                spec_id=key,
                signal_key=key,
                dating="none",
                threshold_n=None,
                frequency=frequency,
                citation=TOM_CONTROL_CITATION,
                hypothesis=(
                    f"CONTROL, no dividend data at all: the {label} turn-of-the-month window "
                    "(Ariel 1987; Lakonishok & Smidt 1988). If it matches or beats the dividend "
                    "specs, this family measured the turn-of-the-month effect wearing a dividend "
                    "costume, and the report says so regardless of the DSR."
                ),
                is_control=True,
                is_placebo=False,
                tom_first_days=first_days,
                tom_last_days=last_days,
            )
        )

    expected = len(_DIVIDEND_SIGNALS) * len(DATINGS) * len(TOP_N_THRESHOLDS) + 2
    assert len(specs) == expected == DIVIDEND_PAYMENT_N_TRIALS, (
        f"Dividend-payment-pressure family built {len(specs)} definitions; the grid "
        f"({len(_DIVIDEND_SIGNALS)} signals x {len(DATINGS)} datings x "
        f"{len(TOP_N_THRESHOLDS)} thresholds, plus 2 calendar controls) implies {expected}; the "
        f"pre-declared DIVIDEND_PAYMENT_N_TRIALS is {DIVIDEND_PAYMENT_N_TRIALS}. All three must "
        "agree -- a drift here silently changes the DSR's multiple-comparisons denominator for "
        "every future run."
    )
    assert len({s.spec_id for s in specs}) == len(specs), "spec_ids must be unique"
    assert sum(1 for s in specs if s.is_control) == 2, "exactly two calendar controls"
    assert sum(1 for s in specs if s.is_placebo) == len(DATINGS) * len(TOP_N_THRESHOLDS), (
        "the future-dividend placebo must appear in every dating x threshold cell"
    )
    return specs


DIVIDEND_PRESSURE_FAMILY: list[DividendPressureSpec] = _build_dividend_pressure_family()

_DEFINITION_BY_KEY = {d.key: d for d in _DIVIDEND_SIGNALS}


# --- config ----------------------------------------------------------------


@dataclass
class DividendPressureConfig:
    cost_bps: float = DIVIDEND_PRESSURE_COST_BPS
    short_borrow_bps_per_year: float = DIVIDEND_PRESSURE_SHORT_BORROW_BPS_PER_YEAR
    formation_start: date = DIVIDEND_PRESSURE_FORMATION_START


def default_dividend_pressure_config() -> DividendPressureConfig:
    """This family's cost configuration, as a FUNCTION rather than a module
    singleton so callers cannot mutate shared state -- the same reason
    rebalancing_pressure_timing.default_rebalancing_config() is one."""
    return DividendPressureConfig()


@dataclass(frozen=True)
class CostArm:
    key: str
    description: str
    cost_bps: float
    short_borrow_bps_per_year: float


COST_ARMS: tuple[CostArm, ...] = (
    CostArm(
        key="cost_free",
        description=(
            "cost_bps=0, borrow=0 -- the GROSS signal, for attribution only, never a verdict input"
        ),
        cost_bps=0.0,
        short_borrow_bps_per_year=0.0,
    ),
    CostArm(
        key="baseline",
        description=(
            "cost_bps=1.0 one-way (~12x SPY's ~0.08bp quoted half-spread), borrow=34bp/yr general "
            "collateral (Beneish/Lee/Nichols 2015 p.15) -- THE VERDICT ARM"
        ),
        cost_bps=DIVIDEND_PRESSURE_COST_BPS,
        short_borrow_bps_per_year=DIVIDEND_PRESSURE_SHORT_BORROW_BPS_PER_YEAR,
    ),
    CostArm(
        key="stress",
        description=(
            "cost_bps=5.0 one-way (~60x SPY's quoted half-spread), borrow=34bp/yr -- a deliberate "
            "UNSOURCED stress standing in for market impact and adverse selection"
        ),
        cost_bps=5.0,
        short_borrow_bps_per_year=DIVIDEND_PRESSURE_SHORT_BORROW_BPS_PER_YEAR,
    ),
)
BASELINE_COST_ARM = "baseline"


# ===========================================================================
# THE PANEL
# ===========================================================================


@dataclass
class DividendPressureData:
    """Everything the signals and the diagnostics read, built once so every
    spec sees the identical inputs."""

    market_close: pd.Series
    market_returns: pd.Series
    dollars_by_dating: dict[str, pd.Series]
    aggregate_market_cap: pd.Series
    signals: dict[tuple[str, str], pd.Series]  # (signal_key, dating) -> x_t
    events: list[DividendPaymentEvent]
    report: PaymentCalendarReport
    skip_counts: dict[str, dict[str, int]]
    no_share_count_tickers: list[str] = field(default_factory=list)


def build_signal_series(
    dollars: pd.Series, market_cap: pd.Series, signal_key: str
) -> pd.Series:
    """x_t for one scaling. Every branch is a published construction; see the
    module docstring's THE THREE SCALINGS."""
    two_day = two_day_cumulative(dollars)
    if signal_key == "raw":
        return two_day.rename("raw")
    if signal_key == "mktcap":
        # "divided by the PREVIOUS DAY'S total market capitalization" -- the
        # shift(1) is the paper's own timing and is not a lag added for safety.
        return (two_day / market_cap.shift(1)).rename("mktcap")
    if signal_key == "abnormal":
        return (two_day / abnormal_denominator(dollars)).rename("abnormal")
    if signal_key == "future_ph":
        return future_cumulative(dollars).rename("future_ph")
    raise ValueError(f"unknown signal_key {signal_key!r}")


def assert_no_lookahead(
    events: list[DividendPaymentEvent], *, use_ex_date: bool
) -> int:
    """Checks the timing contract on the REAL calendar rather than asserting it
    in prose, and returns the number of events whose ex-date is NOT strictly
    before their attribution date.

    For the `payment` dating this count MUST be zero: the position for day t is
    formed at the close of t-1, and every dividend contributing to D_t must
    therefore already have gone ex. It is checked rather than trusted because
    the imputed lag is data-driven and a bad `.calendar` row could in principle
    produce a zero-day lag.

    For the `ex_date` dating the count is BY CONSTRUCTION every event -- the
    attribution date IS the ex-date -- and that is precisely the point-in-time
    weakness the pre-registration discloses for that arm. It rests on [HS22]'s
    own stated ~21-day declaration-to-ex gap, which is real but which THIS
    build's own data cannot verify for the NYSE majority of the universe. F7
    measures it on the Nasdaq subset, which does carry declaration dates."""
    if use_ex_date:
        return len(events)
    return sum(1 for e in events if e.ex_date >= e.payment_date)


# ===========================================================================
# BACKTEST
# ===========================================================================


@dataclass
class DividendPressureBacktestResult:
    spec_id: str
    status: str
    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    positions: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    long_only_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    market_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    total_cost: float = 0.0
    total_financing_cost: float = 0.0
    total_turnover: float = 0.0
    n_position_changes: int = 0
    n_high_days: int = 0
    realized_high_frequency: float = float("nan")
    first_trading_day: date | None = None
    last_trading_day: date | None = None


def build_indicator(data: DividendPressureData, spec: DividendPressureSpec) -> pd.Series:
    """The 0/1 high-state series for one spec, before demeaning.

    THE CONTROL BRANCH READS THE SPEC'S OWN WINDOW, and that is a CORRECTION.
    The first build called turn_of_month_indicator() with its module defaults
    for BOTH controls, so tom_ctrl_1d and tom_ctrl_4d shared one indicator
    (measured: identical n_high = 419 and identical long-only Sharpe) and
    differed only in the demeaning constant. That did not implement the
    pre-registration, which specifies a genuine ONE-DAY window for tom_ctrl_1d
    ("the first trading day of the month alone"), and it mattered: demeaning a
    4-day indicator by 1/21 leaves a permanent +0.14 net-long tilt, so
    tom_ctrl_1d's Sharpe was substantially the EQUITY PREMIUM -- exactly what
    the demeaned sizing exists to remove. See the module docstring's CONTROL
    SPECIFICATION ERRATUM."""
    if spec.is_control:
        return turn_of_month_indicator(
            data.market_close.index,
            first_days=spec.tom_first_days,
            last_days=spec.tom_last_days,
        )
    x = data.signals[(spec.signal_key, spec.dating)]
    assert spec.threshold_n is not None
    return top_n_indicator(x, spec.threshold_n)


def run_dividend_pressure_backtest(
    data: DividendPressureData,
    spec: DividendPressureSpec,
    config: DividendPressureConfig,
) -> DividendPressureBacktestResult:
    """One spec's walk-forward replay.

    THE TIMING CONTRACT: the position held over day t is formed at the close of
    day t-1 from x_t, which depends on D_t and D_{t-1} -- both declared on
    average 43 days earlier and legally owed. Using day t's own dividend is
    [HS22]'s central identifying claim, not a modelling liberty, and
    assert_no_lookahead checks it on the real calendar. The ONE exception is
    the `future_ph` placebo, which reads days t+1 and t+2 ON PURPOSE and is
    labelled as not point-in-time tradeable everywhere its number appears.

    A day whose indicator is NaN -- the trailing-window burn-in, or a day the
    abnormal denominator was unavailable -- contributes NO return at all rather
    than a forced zero. Zeros would not be neutral: they would shrink both the
    mean and the standard deviation of the return series and quietly report the
    Sharpe of "hold cash for a year, then trade" as the Sharpe of the signal.
    That is vol_regime_timing.py's reasoning, adopted unchanged. It does NOT
    apply to a demeaned position of exactly -n/252, which is a real held short
    and stays in the series."""
    indicator = build_indicator(data, spec)
    positions = demeaned_position(indicator, spec.frequency)

    index = data.market_close.index
    market = data.market_returns
    start_positions = np.flatnonzero(index.date >= config.formation_start)
    if len(start_positions) == 0:
        return DividendPressureBacktestResult(
            spec_id=spec.spec_id, status="no_history_after_start"
        )
    first = int(start_positions[0])

    pos = positions.to_numpy(dtype=float)
    ind = indicator.to_numpy(dtype=float)
    ret = market.to_numpy(dtype=float)
    borrow_daily_rate = config.short_borrow_bps_per_year / 1e4 / FINANCING_DAYS_PER_YEAR
    cost_rate = config.cost_bps / 1e4

    returns: dict[pd.Timestamp, float] = {}
    long_only: dict[pd.Timestamp, float] = {}
    held: dict[pd.Timestamp, float] = {}
    previous = 0.0
    total_cost = 0.0
    total_financing = 0.0
    total_turnover = 0.0
    n_changes = 0
    n_high = 0

    # The formation at index t-1 earns day t's return, so the loop walks the
    # FORMATION index from `first` to the second-to-last row.
    for t in range(first, len(index) - 1):
        position = pos[t]
        if not np.isfinite(position):
            continue
        gross = position * ret[t + 1]
        if not np.isfinite(gross):
            continue

        turnover = abs(position - previous)
        cost = cost_rate * GROSS_NOTIONAL_PER_UNIT_POSITION * turnover
        elapsed_days = max((index[t + 1] - index[t]).days, 0)
        # Borrow accrues on the SHORT notional only -- max(-position, 0).
        financing = borrow_daily_rate * max(-position, 0.0) * elapsed_days

        returns[index[t + 1]] = gross - cost - financing
        long_only[index[t + 1]] = ind[t] * ret[t + 1]
        held[index[t + 1]] = position
        total_cost += cost
        total_financing += financing
        total_turnover += turnover
        if turnover > 0.0:
            n_changes += 1
        if ind[t] > 0.5:
            n_high += 1
        previous = position

    if not returns:
        return DividendPressureBacktestResult(spec_id=spec.spec_id, status="no_realized_returns")

    daily = pd.Series(returns).sort_index()
    return DividendPressureBacktestResult(
        spec_id=spec.spec_id,
        status="ok",
        daily_returns=daily,
        positions=pd.Series(held).sort_index(),
        long_only_returns=pd.Series(long_only).sort_index(),
        market_returns=market.reindex(daily.index),
        total_cost=total_cost,
        total_financing_cost=total_financing,
        total_turnover=total_turnover,
        n_position_changes=n_changes,
        n_high_days=n_high,
        realized_high_frequency=n_high / len(daily),
        first_trading_day=daily.index[0].date(),
        last_trading_day=daily.index[-1].date(),
    )


# ===========================================================================
# CONFOUND DIAGNOSTICS
# ===========================================================================


def _sharpe_over(returns: pd.Series, start: date, end: date) -> float | None:
    mask = (returns.index.date >= start) & (returns.index.date <= end)
    window = returns[mask]
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
# vol_regime_timing.RESIDUAL_DEGENERACY_RATIO.
RESIDUAL_DEGENERACY_RATIO = 1e-8


@dataclass(frozen=True)
class DividendPressureConfound:
    """Everything needed to decide whether a Sharpe here is real or is a
    disguised market exposure or calendar effect. Computed for EVERY spec."""

    spec_id: str
    mean_position: float
    mean_abs_position: float
    fraction_long: float
    market_beta: float
    market_alpha_annualized: float
    residual_sharpe: float
    long_only_sharpe: float
    buy_and_hold_sharpe: float
    turn_of_month_overlap: float
    turn_of_month_position_correlation: float
    subperiod_sharpes: tuple[float, ...]
    sharpe_in_paper_window: float | None
    sharpe_after_paper_window: float | None
    sharpe_before_circulation: float | None
    sharpe_after_circulation: float | None
    bootstrap_p_value: float | None
    annual_turnover: float


def compute_confound_diagnostics(
    spec: DividendPressureSpec,
    replay: DividendPressureBacktestResult,
    data: DividendPressureData,
) -> DividendPressureConfound:
    """The in-module adversarial pass.

    residual_sharpe is the Sharpe of the strategy's returns after removing its
    OLS exposure to buy-and-hold SPY, i.e. after taking away everything a
    constant, signal-free position in the same instrument would have earned. It
    is the BETA-HEDGED stream y - beta*x, NOT the OLS residual -- an OLS
    residual with an intercept has mean exactly zero by construction, so its
    Sharpe is ~0 for every strategy ever measured and computing it that way
    would report every spec as a disguised tilt with total confidence.
    vol_regime_timing.py found that trap first and its _ols_beta_alpha is
    imported here rather than re-derived.

    turn_of_month_overlap is the fraction of this spec's HIGH days that fall
    inside the control's turn-of-the-month window. It is the quantitative basis
    for the pre-declared control reading, and it is computed for the controls
    themselves too, where it is 1.0 by construction and serves as a check that
    the measurement is doing what it claims."""
    daily = replay.daily_returns
    market = replay.market_returns

    beta, alpha = _ols_beta_alpha(daily, market)
    aligned = pd.concat([daily.rename("y"), market.rename("x")], axis=1).dropna()
    if len(aligned) >= 3:
        hedged = aligned["y"] - beta * aligned["x"]
        y_std = float(aligned["y"].std(ddof=1))
        hedged_std = float(hedged.std(ddof=1))
        fully_explained = y_std > 0 and hedged_std <= RESIDUAL_DEGENERACY_RATIO * y_std
        residual_sharpe = 0.0 if fully_explained else sharpe_ratio(hedged)
        bh_sharpe = sharpe_ratio(aligned["x"])
    else:
        residual_sharpe = 0.0
        bh_sharpe = 0.0

    indicator = build_indicator(data, spec).reindex(replay.positions.index)
    # The REFERENCE window for the overlap statistic is the 4-day one, named
    # explicitly rather than taken from a default, so this diagnostic means the
    # same thing for every spec including the 1-day control.
    tom = turn_of_month_indicator(
        data.market_close.index,
        first_days=TOM_WINDOW_FIRST_DAYS,
        last_days=TOM_WINDOW_LAST_DAYS,
    ).reindex(replay.positions.index)
    high = indicator > 0.5
    overlap = float((tom[high] > 0.5).mean()) if int(high.sum()) > 0 else float("nan")
    tom_position = demeaned_position(tom, (TOM_WINDOW_FIRST_DAYS + TOM_WINDOW_LAST_DAYS) / 21.0)
    correlation = float(replay.positions.corr(tom_position))

    pos = replay.positions
    n_years = max(len(daily) / TRADING_DAYS_PER_YEAR, 1e-9)

    return DividendPressureConfound(
        spec_id=spec.spec_id,
        mean_position=float(pos.mean()) if len(pos) else 0.0,
        mean_abs_position=float(pos.abs().mean()) if len(pos) else 0.0,
        fraction_long=float((pos > 0).mean()) if len(pos) else 0.0,
        market_beta=beta,
        market_alpha_annualized=alpha * TRADING_DAYS_PER_YEAR,
        residual_sharpe=residual_sharpe,
        long_only_sharpe=sharpe_ratio(replay.long_only_returns)
        if len(replay.long_only_returns) >= 2
        else 0.0,
        buy_and_hold_sharpe=bh_sharpe,
        turn_of_month_overlap=overlap,
        turn_of_month_position_correlation=correlation,
        subperiod_sharpes=_subperiod_sharpes(daily),
        sharpe_in_paper_window=_sharpe_over(daily, date(1900, 1, 1), PAPER_SAMPLE_END),
        sharpe_after_paper_window=_sharpe_over(
            daily, PAPER_SAMPLE_END + timedelta(days=1), date(2100, 1, 1)
        ),
        sharpe_before_circulation=_sharpe_over(
            daily, date(1900, 1, 1), PAPER_CIRCULATION_DATE - timedelta(days=1)
        ),
        sharpe_after_circulation=_sharpe_over(daily, PAPER_CIRCULATION_DATE, date(2100, 1, 1)),
        # Block length 5 -- one trading week. The high state persists for
        # several days around a payment cluster, so a one-day block would treat
        # a persistent book as ~2,100 independent draws.
        bootstrap_p_value=block_bootstrap_sharpe_pvalue(daily, 5),
        annual_turnover=replay.total_turnover / n_years,
    )


# ===========================================================================
# MECHANISM-FIDELITY CHECKS (F1-F12) -- DIAGNOSTICS, NEVER SPECS
# ===========================================================================


def _year_month_dummies(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Year-by-month fixed effects as explicit dummies, one column dropped to
    avoid collinearity with the intercept.

    [HS22]'s stronger columns all use these. THEY ARE A DIAGNOSTIC ONLY AND
    NEVER ENTER A TRADED SPEC: a fixed effect is estimated from the whole
    sample, including the future, so a portfolio cannot have one (see the
    module docstring's NO YEAR-BY-MONTH FIXED EFFECTS note)."""
    labels = index.to_period("M").astype(str)
    dummies = pd.get_dummies(pd.Series(labels, index=index), prefix="ym", dtype=float)
    return dummies.iloc[:, 1:]


@dataclass(frozen=True)
class PrimaryRegression:
    """F1 -- [HS22] Table I columns 3-4 reproduced on this project's own data.

    PAPER'S NUMBERS (working paper, verbatim): coefficient 59.50, t = 3.32
    without fixed effects; 67.07, t = 3.47 with year-by-month fixed effects; a
    one-standard-deviation move in payout yield (.0004711) predicts 3.2 b.p.

    READ THESE AGAINST PRE-REGISTRATION 10.2(b), NOT AGAINST THE PAPER
    DIRECTLY: this build has ~2,100 observations against the paper's ~24,000,
    so an exactly-true effect of exactly the paper's size implies an expected
    t here of 3.32 * sqrt(2100/24000) = 0.98. A t near 1 with the right sign
    is the SUCCESS case for this check, not a failure."""

    label: str
    n_obs: int
    coefficient: float
    t_stat: float
    r_squared: float
    signal_sd: float
    bps_per_one_sd: float


def _regression_point(
    label: str, y: pd.Series, x: pd.Series, *, fixed_effects: bool
) -> PrimaryRegression:
    design = x.to_frame("signal")
    if fixed_effects:
        design = pd.concat([design, _year_month_dummies(x.index)], axis=1)
    params, tvalues, r2, n_obs = _hc0_regression(y, design)
    coefficient = params.get("signal", float("nan"))
    aligned = pd.concat([y.rename("__y"), x.rename("signal")], axis=1).dropna()
    sd = float(aligned["signal"].std(ddof=1)) if len(aligned) > 1 else float("nan")
    return PrimaryRegression(
        label=label,
        n_obs=n_obs,
        coefficient=coefficient,
        t_stat=tvalues.get("signal", float("nan")),
        r_squared=r2,
        signal_sd=sd,
        # [HS22]'s own normalization: the effect on the day's return of a
        # ONE-STANDARD-DEVIATION move in the signal, in basis points.
        bps_per_one_sd=coefficient * sd * 1e4,
    )


@dataclass(frozen=True)
class LagPoint:
    lag: int
    coefficient: float
    t_stat: float
    n_obs: int


@dataclass(frozen=True)
class QuintilePoint:
    quintile: int
    mean_return_bps: float
    n_days: int


@dataclass(frozen=True)
class ThresholdPoint:
    n_days: int
    coefficient_bps: float
    t_stat: float
    coefficient_bps_fe: float
    t_stat_fe: float
    n_obs: int
    realized_frequency: float


@dataclass(frozen=True)
class ImputationValidation:
    """F7 -- the payment-date imputation measured against Nasdaq's REAL
    historical pay dates.

    A DATA-QUALITY MEASUREMENT CONTAINING NO RETURN OF ANY KIND, which is why
    running it before the grid was frozen is not a p-hacking route (the same
    reasoning cross_sectional_dividend_month.py records for its
    forecast-accuracy table). Reported whatever it shows: a poor result here is
    a headline finding of this build, not a reason to change the construction
    after the fact."""

    n_tickers_covered: int
    n_events_compared: int
    n_exact: int
    n_within_1_day: int
    n_within_2_days: int
    n_within_5_days: int
    mean_signed_error_days: float
    median_signed_error_days: float
    mean_absolute_error_days: float
    p90_absolute_error_days: float
    # The EX-DATE arm's point-in-time assumption, measurable only here because
    # Nasdaq is the one free source carrying declaration dates.
    n_declaration_pairs: int
    median_declaration_to_ex_days: float
    fraction_declared_before_ex: float
    # Within-firm stability of the lag, which is what the single-observation
    # imputation actually assumes.
    median_within_firm_lag_sd_days: float


def validate_payment_imputation(cache: RawPaymentCache) -> ImputationValidation:
    """F7. Compares imputed payment dates against Nasdaq's real ones, and
    measures the declaration-to-ex gap that the ex-date arm rests on."""
    lags, median_lag = resolve_payment_lags(cache.yf_payment_lag)
    errors: list[int] = []
    declaration_gaps: list[int] = []
    within_firm_sds: list[float] = []
    n_covered = 0

    for ticker, rows in cache.nasdaq_history.items():
        true_pairs: list[tuple[date, date]] = []
        for row in rows:
            if not row.get("ex") or not row.get("pay"):
                continue
            ex = date.fromisoformat(row["ex"])
            pay = date.fromisoformat(row["pay"])
            true_pairs.append((ex, pay))
            if row.get("declaration"):
                declaration_gaps.append((ex - date.fromisoformat(row["declaration"])).days)
        if not true_pairs:
            continue
        n_covered += 1
        realized = [(pay - ex).days for ex, pay in true_pairs]
        if len(realized) >= 2:
            within_firm_sds.append(float(np.std(realized, ddof=1)))
        imputed_lag = lags.get(ticker)
        if imputed_lag is None:
            if not np.isfinite(median_lag):
                continue
            imputed_lag = int(round(median_lag))
        # Signed error in CALENDAR days of the imputed pay date against the
        # real one. Positive means the imputation is LATE.
        errors.extend(imputed_lag - actual for actual in realized)

    absolute = [abs(e) for e in errors]
    return ImputationValidation(
        n_tickers_covered=n_covered,
        n_events_compared=len(errors),
        n_exact=sum(1 for e in errors if e == 0),
        n_within_1_day=sum(1 for e in absolute if e <= 1),
        n_within_2_days=sum(1 for e in absolute if e <= 2),
        n_within_5_days=sum(1 for e in absolute if e <= 5),
        mean_signed_error_days=float(np.mean(errors)) if errors else float("nan"),
        median_signed_error_days=float(np.median(errors)) if errors else float("nan"),
        mean_absolute_error_days=float(np.mean(absolute)) if absolute else float("nan"),
        p90_absolute_error_days=float(np.percentile(absolute, 90)) if absolute else float("nan"),
        n_declaration_pairs=len(declaration_gaps),
        median_declaration_to_ex_days=float(np.median(declaration_gaps))
        if declaration_gaps
        else float("nan"),
        fraction_declared_before_ex=float(np.mean([g > 0 for g in declaration_gaps]))
        if declaration_gaps
        else float("nan"),
        median_within_firm_lag_sd_days=float(np.median(within_firm_sds))
        if within_firm_sds
        else float("nan"),
    )


@dataclass(frozen=True)
class DataSanity:
    """F8 -- the dollar aggregate checked against economically meaningful known
    quantities rather than against nothing.

    implied_annual_dividend_yield is the one that would catch the module
    docstring's named SPLIT-BASIS HAZARD: if SEC's raw share counts were
    multiplied by Yahoo's split-adjusted per-share amounts without
    split_adjust_share_counts putting them on one basis, this number would be
    wrong by the universe's aggregate split factor. A large-cap US index yield
    lives in the low single digits of percent; anything an order of magnitude
    away means the join is broken."""

    fraction_days_with_payment: float
    implied_annual_dividend_yield: float
    mean_aggregate_market_cap: float
    total_dividend_dollars: float
    n_years: float
    dollars_by_day_of_month: dict[int, float]
    dollars_by_weekday: dict[int, float]
    top_day_share_of_total: float


def compute_data_sanity(dollars: pd.Series, market_cap: pd.Series) -> DataSanity:
    """F8. [HS22] Section III.A, verbatim, is the comparison for the first
    field: "while there is some seasonality in dividend payments, over 90% of
    trading days involve a dividend payment"."""
    clean = dollars.dropna()
    n_years = max(len(clean) / TRADING_DAYS_PER_YEAR, 1e-9)
    total = float(clean.sum())
    mean_cap = float(market_cap.dropna().mean()) if market_cap.notna().any() else float("nan")
    by_dom: dict[int, float] = {}
    by_dow: dict[int, float] = {}
    for ts, value in clean.items():
        by_dom[ts.day] = by_dom.get(ts.day, 0.0) + float(value)
        by_dow[ts.weekday()] = by_dow.get(ts.weekday(), 0.0) + float(value)
    return DataSanity(
        fraction_days_with_payment=float((clean > 0).mean()),
        implied_annual_dividend_yield=(total / n_years / mean_cap)
        if np.isfinite(mean_cap) and mean_cap > 0
        else float("nan"),
        mean_aggregate_market_cap=mean_cap,
        total_dividend_dollars=total,
        n_years=n_years,
        dollars_by_day_of_month=by_dom,
        dollars_by_weekday=by_dow,
        top_day_share_of_total=(float(clean.max()) / total) if total > 0 else float("nan"),
    )


@dataclass(frozen=True)
class ScalingAgreement:
    """F6 -- [HS22]'s OWN robustness claim, reproduced. The paper reports the
    price-independent abnormal-yield estimate as "similar to the 3.2 b.p. found
    from the same specification normalizing by market capitalization" (2.7 vs
    3.2 b.p.).

    PRE-DECLARED READING (pre-registration F6): if the two scalings DIVERGE
    SHARPLY on this project's own free-data build, that is an important finding
    in its own right and is reported as one -- it would be evidence about THIS
    BUILD'S DATA rather than about the paper."""

    correlation_mktcap_abnormal: float
    correlation_raw_mktcap: float
    correlation_raw_abnormal: float
    jaccard_by_threshold: dict[int, float]
    bps_per_one_sd_mktcap: float
    bps_per_one_sd_abnormal: float


@dataclass(frozen=True)
class FidelityChecks:
    """Every F-check, computed once on the PAYMENT dating (the primary) unless
    a field says otherwise."""

    dating: str
    # F1
    primary_no_fe: PrimaryRegression
    primary_with_fe: PrimaryRegression
    abnormal_no_fe: PrimaryRegression
    abnormal_with_fe: PrimaryRegression
    # F2 -- THE PLACEBO, and a pre-declared VETO
    placebo_no_fe: PrimaryRegression
    placebo_with_fe: PrimaryRegression
    # F3
    lag_structure: list[LagPoint]
    # F4
    abnormal_quintiles: list[QuintilePoint]
    # F5
    threshold_dummies: list[ThresholdPoint]
    # F6
    scaling_agreement: ScalingAgreement
    # F8
    data_sanity: DataSanity


def compute_fidelity_checks(
    data: DividendPressureData, *, dating: str, formation_start: date
) -> FidelityChecks:
    """F1-F6 and F8 on one dating axis. Every regression uses HC0 standard
    errors, which is the convention rebalancing_pressure_timing._hc0_regression
    already implements via statsmodels rather than a hand-rolled sandwich."""
    index = data.market_close.index
    mask = index.date >= formation_start
    y = data.market_returns[mask]

    dollars = data.dollars_by_dating[dating]
    market_cap = data.aggregate_market_cap
    x_mktcap = data.signals[("mktcap", dating)][mask]
    x_abnormal = data.signals[("abnormal", dating)][mask]
    x_raw = data.signals[("raw", dating)][mask]
    x_future = data.signals[("future_ph", dating)][mask]

    # F3 -- the lag structure, [HS22] Table I column 1. Each lag's payment
    # yield SEPARATELY, on the same market-cap denominator the paper uses.
    lag_points: list[LagPoint] = []
    single_day_yield = (dollars / market_cap.shift(1)).rename("yield")
    for lag in range(5):
        params, tvalues, _, n_obs = _hc0_regression(
            y, single_day_yield.shift(lag)[mask].to_frame("signal")
        )
        lag_points.append(
            LagPoint(
                lag=lag,
                coefficient=params.get("signal", float("nan")),
                t_stat=tvalues.get("signal", float("nan")),
                n_obs=n_obs,
            )
        )

    # F4 -- [HS22] Figure 1's quintiles of the ABNORMAL (price-independent)
    # yield. Paper's shape: monotonically increasing, roughly 2, 2, 4, 4, 8bp.
    quintiles: list[QuintilePoint] = []
    frame = pd.concat([y.rename("ret"), x_abnormal.rename("x")], axis=1).dropna()
    if len(frame) >= 25:
        try:
            buckets = pd.qcut(frame["x"], 5, labels=False, duplicates="drop")
            for q in sorted(set(buckets.dropna())):
                rows = frame["ret"][buckets == q]
                quintiles.append(
                    QuintilePoint(
                        quintile=int(q) + 1,
                        mean_return_bps=float(rows.mean()) * 1e4,
                        n_days=len(rows),
                    )
                )
        except ValueError:
            pass

    # F5 -- [HS22] Table II Panel B's dummy regressions at each threshold, on
    # the RAW dollar signal (the paper's own literal formulation).
    threshold_points: list[ThresholdPoint] = []
    for n in TOP_N_THRESHOLDS:
        indicator = top_n_indicator(data.signals[("raw", dating)], n)[mask]
        params, tvalues, _, n_obs = _hc0_regression(y, indicator.to_frame("signal"))
        design_fe = pd.concat(
            [indicator.rename("signal"), _year_month_dummies(indicator.index)], axis=1
        )
        params_fe, tvalues_fe, _, _ = _hc0_regression(y, design_fe)
        clean = indicator.dropna()
        threshold_points.append(
            ThresholdPoint(
                n_days=n,
                coefficient_bps=params.get("signal", float("nan")) * 1e4,
                t_stat=tvalues.get("signal", float("nan")),
                coefficient_bps_fe=params_fe.get("signal", float("nan")) * 1e4,
                t_stat_fe=tvalues_fe.get("signal", float("nan")),
                n_obs=n_obs,
                realized_frequency=float(clean.mean()) if len(clean) else float("nan"),
            )
        )

    # F6 -- the market-cap versus prior-year-average agreement.
    jaccard: dict[int, float] = {}
    for n in TOP_N_THRESHOLDS:
        a = top_n_indicator(data.signals[("mktcap", dating)], n)[mask]
        b = top_n_indicator(data.signals[("abnormal", dating)], n)[mask]
        pair = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
        if pair.empty:
            jaccard[n] = float("nan")
            continue
        union = float(((pair["a"] > 0.5) | (pair["b"] > 0.5)).sum())
        intersection = float(((pair["a"] > 0.5) & (pair["b"] > 0.5)).sum())
        jaccard[n] = intersection / union if union > 0 else float("nan")

    primary_no_fe = _regression_point("mktcap_no_fe", y, x_mktcap, fixed_effects=False)
    abnormal_no_fe = _regression_point("abnormal_no_fe", y, x_abnormal, fixed_effects=False)

    return FidelityChecks(
        dating=dating,
        primary_no_fe=primary_no_fe,
        primary_with_fe=_regression_point("mktcap_fe", y, x_mktcap, fixed_effects=True),
        abnormal_no_fe=abnormal_no_fe,
        abnormal_with_fe=_regression_point("abnormal_fe", y, x_abnormal, fixed_effects=True),
        placebo_no_fe=_regression_point("placebo_no_fe", y, x_future, fixed_effects=False),
        placebo_with_fe=_regression_point("placebo_fe", y, x_future, fixed_effects=True),
        lag_structure=lag_points,
        abnormal_quintiles=quintiles,
        threshold_dummies=threshold_points,
        scaling_agreement=ScalingAgreement(
            correlation_mktcap_abnormal=float(x_mktcap.corr(x_abnormal)),
            correlation_raw_mktcap=float(x_raw.corr(x_mktcap)),
            correlation_raw_abnormal=float(x_raw.corr(x_abnormal)),
            jaccard_by_threshold=jaccard,
            bps_per_one_sd_mktcap=primary_no_fe.bps_per_one_sd,
            bps_per_one_sd_abnormal=abnormal_no_fe.bps_per_one_sd,
        ),
        data_sanity=compute_data_sanity(dollars[mask], market_cap[mask]),
    )


@dataclass(frozen=True)
class AbnormalBurnInDiagnostic:
    """POST-HOC, EXPLICITLY NOT PRE-REGISTERED, AND PURELY CORRECTIVE.

    Added AFTER F6 came back reporting corr(raw, abnormal) = -0.03 and
    corr(mktcap, abnormal) = +0.08 -- i.e. that [HS22]'s own market-cap-versus-
    prior-year-average agreement claim FAILED here. The pre-registration (F6)
    pre-declared that a sharp divergence would be "an important finding in its
    own right". IT WOULD HAVE BEEN A FABRICATED ONE, and this diagnostic is
    what establishes that, so it is run and reported rather than left as a
    plausible-sounding headline.

    THE DEFECT, measured rather than argued. The abnormal denominator is the
    mean daily dividend over trading days t-20..t-272, so a formation on
    2018-01-02 reads a window running back to roughly 2016-11 -- entirely
    inside the PADDING. But the padding has almost no dividend DOLLARS, because
    the SEC share counts that turn per-share amounts into dollars only become
    visible at frame CY2017Q3 plus a 90-day lag (~2017-12-29). Measured on the
    real panel: the 413 padding trading days carry 9 non-zero dividend days and
    $2.4e9 in total, against 2,011 non-zero days and $4.28e12 in the formation
    window -- three orders of magnitude of structural, artificial zero.

    The consequence is a denominator up to four orders of magnitude too small
    for the first 272 formation days (12.5% of the sample), which sends the
    abnormal signal's 99th percentile to 113 and its maximum to 4,038 against a
    median of 1.7, and it is that fat artificial tail -- not any property of the
    data or of the paper -- that destroys the F6 correlation.

    THIS CHANGES NO SPEC, NO POSITION AND NO VERDICT INPUT. The traded grid
    stays exactly as pre-registered, the frozen formation window is NOT moved
    (changing a frozen window after seeing a result is precisely the move the
    pre-registration exists to prevent), and the verdict does not turn on it:
    the best candidate spec is a `raw` one, which has no such denominator. What
    this corrects is the READING of F6, and it corrects it AGAINST this build --
    the honest conclusion is "this build's abnormal arm has a burn-in artifact",
    not "the paper's scalings disagree".

    IT IS THE FIRST THING A SUCCESSOR SHOULD FIX: pad the dividend panel with
    enough share-count history to warm a 272-day denominator, or start the
    abnormal arm's formations 272 trading days later than the others.
    """

    n_formation_days: int
    n_clean_days: int
    n_contaminated_days: int
    padding_trading_days: int
    padding_nonzero_dividend_days: int
    padding_total_dollars: float
    formation_nonzero_dividend_days: int
    formation_total_dollars: float
    # As run, over the whole formation window (what F6 reports).
    corr_raw_abnormal_as_run: float
    corr_mktcap_abnormal_as_run: float
    abnormal_p99_as_run: float
    abnormal_max_as_run: float
    # On the subset whose t-20..t-272 window lies entirely inside the formation
    # window, i.e. touches no padding.
    corr_raw_abnormal_clean: float
    corr_mktcap_abnormal_clean: float
    abnormal_p99_clean: float
    abnormal_max_clean: float


def post_hoc_abnormal_burn_in_diagnostic(
    data: DividendPressureData, *, dating: str, formation_start: date
) -> AbnormalBurnInDiagnostic:
    """See AbnormalBurnInDiagnostic. Post-hoc, corrective, verdict-neutral."""
    index = data.market_close.index
    dates = index.date
    formation = dates >= formation_start

    # "Clean" = the whole t-272..t-20 lookback lies inside the formation window,
    # so the denominator saw no structurally-empty padding day.
    clean = np.zeros(len(index), dtype=bool)
    for i in range(len(index)):
        if not formation[i]:
            continue
        low = i - ABNORMAL_LOOKBACK_DAYS
        high = i - ABNORMAL_SKIP_DAYS
        if low >= 0 and not (dates[low : high + 1] < formation_start).any():
            clean[i] = True

    dollars = data.dollars_by_dating[dating]
    raw = data.signals[("raw", dating)]
    mktcap = data.signals[("mktcap", dating)]
    abnormal = data.signals[("abnormal", dating)].replace([np.inf, -np.inf], np.nan)

    padding = ~formation

    def _stats(mask: np.ndarray) -> tuple[float, float, float, float]:
        values = abnormal[mask].dropna()
        return (
            float(raw[mask].corr(abnormal[mask])),
            float(mktcap[mask].corr(abnormal[mask])),
            float(values.quantile(0.99)) if len(values) else float("nan"),
            float(values.max()) if len(values) else float("nan"),
        )

    as_run = _stats(formation)
    clean_stats = _stats(clean)

    return AbnormalBurnInDiagnostic(
        n_formation_days=int(formation.sum()),
        n_clean_days=int(clean.sum()),
        n_contaminated_days=int(formation.sum() - clean.sum()),
        padding_trading_days=int(padding.sum()),
        padding_nonzero_dividend_days=int((dollars[padding] > 0).sum()),
        padding_total_dollars=float(dollars[padding].sum()),
        formation_nonzero_dividend_days=int((dollars[formation] > 0).sum()),
        formation_total_dollars=float(dollars[formation].sum()),
        corr_raw_abnormal_as_run=as_run[0],
        corr_mktcap_abnormal_as_run=as_run[1],
        abnormal_p99_as_run=as_run[2],
        abnormal_max_as_run=as_run[3],
        corr_raw_abnormal_clean=clean_stats[0],
        corr_mktcap_abnormal_clean=clean_stats[1],
        abnormal_p99_clean=clean_stats[2],
        abnormal_max_clean=clean_stats[3],
    )


# ===========================================================================
# SCREENING
# ===========================================================================


def policy_d_denominators(n_local: int = DIVIDEND_PAYMENT_N_TRIALS) -> list[int]:
    """The N values a Policy D report must cover, ascending and deduplicated:
    dsr_n_trials(n_local), n_specs_clustered, raw_pooled_distinct_trials.

    Same derivation and same artifact as
    rebalancing_pressure_timing.policy_d_denominators. The lowest tier is
    dsr_n_trials(n_local), NOT n_local itself, because that is the denominator
    the screen actually deflates at."""
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
class DividendPressureScreeningResult:
    """One spec's full Policy D record. preservation_score lives HERE rather
    than in an optional later pass on purpose -- this project has twice shipped
    a check and then skipped it for the next real decision, and a metric
    applied when someone remembers is a decoration, not a check."""

    spec_id: str
    signal_key: str
    dating: str
    threshold_n: int | None
    frequency: float
    citation: str
    hypothesis: str
    is_control: bool
    is_placebo: bool
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
    n_high_days: int
    realized_high_frequency: float
    deflated_sharpe: object  # DeflatedSharpeResult at n_local -- for persistence
    confound: DividendPressureConfound


def screen_dividend_pressure(
    data: DividendPressureData,
    specs: list[DividendPressureSpec],
    config: DividendPressureConfig,
    *,
    denominators: list[int] | None = None,
    cost_arm: str = BASELINE_COST_ARM,
) -> list[DividendPressureScreeningResult]:
    """One Sharpe per spec, DSR-corrected at every pre-declared denominator.

    Trial counting follows cross_sectional.screen_cross_sectional_universe,
    vol_regime_timing.screen_vol_regime_timing and
    rebalancing_pressure_timing.screen_rebalancing_pressure exactly and for the
    same documented reason: each spec IS already a single portfolio, so no
    uncorrected "which ticker" search dimension exists and "which definition"
    is the one search dimension. n_trials is fixed at len(specs) -- the
    family's literal pre-declared size -- raised to the project-wide
    effectively-independent count by dsr_n_trials whenever that is larger, and
    NEVER shrunk to however many specs survived the data floors.

    sigma_sr is the ddof=1 standard deviation of every sibling spec's Sharpe
    from this same pass."""
    denominators = denominators if denominators is not None else policy_d_denominators(len(specs))
    n_local = dsr_n_trials(len(specs)) if specs else 0

    replays: dict[str, DividendPressureBacktestResult] = {}
    for spec in specs:
        replay = run_dividend_pressure_backtest(data, spec, config)
        if replay.status != "ok":
            logger.info("dividend-pressure spec %s not replayed: %s", spec.spec_id, replay.status)
            continue
        if len(replay.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            logger.info(
                "dividend-pressure spec %s dropped: only %d realized days (floor %d)",
                spec.spec_id,
                len(replay.daily_returns),
                MIN_REPLAY_TRADING_DAYS,
            )
            continue
        replays[spec.spec_id] = replay

    sharpes = {sid: sharpe_ratio(r.daily_returns) for sid, r in replays.items()}
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {s.spec_id: s for s in specs}
    results: list[DividendPressureScreeningResult] = []
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
            DividendPressureScreeningResult(
                spec_id=spec_id,
                signal_key=spec.signal_key,
                dating=spec.dating,
                threshold_n=spec.threshold_n,
                frequency=spec.frequency,
                citation=spec.citation,
                hypothesis=spec.hypothesis,
                is_control=spec.is_control,
                is_placebo=spec.is_placebo,
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
                n_high_days=replay.n_high_days,
                realized_high_frequency=replay.realized_high_frequency,
                deflated_sharpe=deflated_local,
                confound=confound,
            )
        )

    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results


# ===========================================================================
# SUMMARY AND VERDICT
# ===========================================================================


@dataclass
class DividendPressureScreeningSummary:
    n_trials: int = DIVIDEND_PAYMENT_N_TRIALS
    denominators: list[int] = field(default_factory=list)
    results_by_cost_arm: dict[str, list[DividendPressureScreeningResult]] = field(
        default_factory=dict
    )
    fidelity_by_dating: dict[str, FidelityChecks] = field(default_factory=dict)
    imputation: ImputationValidation | None = None
    abnormal_burn_in: AbnormalBurnInDiagnostic | None = None
    calendar_report: PaymentCalendarReport | None = None
    skip_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    lookahead_violations: dict[str, int] = field(default_factory=dict)
    sigma_sr_by_cost_arm: dict[str, float | None] = field(default_factory=dict)
    formation_start: date | None = None
    window_end: date | None = None
    n_universe_tickers: int = 0
    n_no_share_count: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def baseline_results(self) -> list[DividendPressureScreeningResult]:
        return self.results_by_cost_arm.get(BASELINE_COST_ARM, [])

    @property
    def candidate_results(self) -> list[DividendPressureScreeningResult]:
        """The specs the verdict may be read off: neither a calendar control
        nor the future-dividend placebo. Both of those are in the grid to
        FAIL, and reading a verdict off one would be reading it off a spec
        designed as a negative control."""
        return [r for r in self.baseline_results if not r.is_control and not r.is_placebo]

    def verdict(self, threshold: float = VALIDATED_EDGE_BAR) -> tuple[str, str | None]:
        """Policy D's two-tier verdict, read off the BASELINE cost arm's best
        NON-CONTROL, NON-PLACEBO spec by DSR at n_local -- exactly the rule the
        pre-registration fixed (section 9) before any number existed.

        The three pre-declared VETOES of pre-registration section 9 are NOT
        applied here: they change how a result is READ, not what the DSR is,
        and folding them into this function would hide them inside a number.
        They are evaluated explicitly in build_dividend_pressure_disclosure and
        reported in prose, which is where a veto belongs."""
        results = self.candidate_results
        if not results:
            return "definite_negative", None
        n_local = dsr_n_trials(self.n_trials)
        best = max(
            results,
            key=lambda r: (
                r.dsr_by_n.get(n_local) if r.dsr_by_n.get(n_local) is not None else -1.0
            ),
        )
        return (
            policy_d_verdict(dsr_by_n=best.dsr_by_n, threshold=threshold, n_local=n_local),
            best.spec_id,
        )


def build_dividend_pressure_disclosure(
    summary: DividendPressureScreeningSummary, config: DividendPressureConfig
) -> list[str]:
    """Plain-language caveats that must travel with any number from this
    family, INCLUDING the three pre-declared vetoes of pre-registration section
    9, each evaluated against what the run actually produced rather than
    asserted."""
    lines = [
        f"SOURCE IS PEER-REVIEWED: {DIVIDEND_PRESSURE_CITATION}",
        (
            f"n_trials = {DIVIDEND_PAYMENT_N_TRIALS} ({len(_DIVIDEND_SIGNALS)} signals x "
            f"{len(DATINGS)} datings x {len(TOP_N_THRESHOLDS)} thresholds, plus 2 calendar "
            "controls), fixed in the pre-registration before any return was computed, and raised "
            "to the project-wide effectively-independent count by dsr_n_trials whenever that is "
            "larger. It does NOT cover the choice to read this particular paper, nor that this is "
            "this project's SECOND Hartzmark-Solomon family after cross_sectional_dividend_month."
        ),
        (
            f"Direction was pre-declared uniformly at {DIVIDEND_PRESSURE_DIRECTION:+.0f} "
            "('high dividend payments -> buying pressure -> higher market returns', [HS25] "
            "abstract) and never fitted per spec; negative Sharpes are reported as they came out, "
            "not flipped."
        ),
        (
            "PAYMENT-DATE DEVIATION: the paper is explicit that the PAYMENT date is the correct "
            "timing, and this project's dividend feed carries EX-DATES only. Payment dates are "
            "IMPUTED from a per-ticker ex-to-pay lag (yfinance .calendar, 486/496 payers) and "
            "VALIDATED against Nasdaq's real historical pay dates (F7). Residual timing error "
            "ATTENUATES toward zero, so a null here is weak evidence against the paper."
        ),
        (
            "WINDOW DEVIATION: ~2,100 formation days against the paper's ~24,000, because the SEC "
            "share counts the dollar aggregate needs begin at frame CY2017Q3 plus a 90-day "
            "visibility lag. An exactly-true effect of exactly the paper's size implies an "
            "expected regression t-statistic of ~0.98 here (pre-registration 10.2b)."
        ),
        (
            "NO YEAR-BY-MONTH FIXED EFFECTS IN ANY TRADED SPEC. The paper's stronger columns all "
            "use them; a portfolio cannot, because they are estimated using the future. The "
            "fidelity regressions report both specifications and label them."
        ),
        (
            f"Costs: {config.cost_bps:.1f}bp one-way per unit of gross notional traded "
            f"(a SINGLE-instrument book trades {GROSS_NOTIONAL_PER_UNIT_POSITION:.1f} gross per "
            f"unit of position change, not the 2.0 a spread trades), plus "
            f"{config.short_borrow_bps_per_year:.0f}bp/yr general-collateral borrow on the SHORT "
            "notional, accrued on calendar days. This book is short SPY most of the time by "
            "construction. The borrow rate is SOURCED (Beneish/Lee/Nichols 2015 p.15); the "
            "turnover rate is a disclosed assumption."
        ),
        (
            "SPECIALS ARE INCLUDED: Yahoo's feed carries no CRSP distribution code, so a special "
            "dividend is indistinguishable from an ordinary one. Specials are large and rare, so "
            "they land in exactly the top-10-day bucket this family trades."
        ),
        (
            "Formation is assumed executable at the exact closing print, and SPY was chosen today "
            "from instruments that still exist and are still liquid. Both are small hindsight "
            "channels here, and neither is zero."
        ),
    ]

    results = summary.baseline_results
    candidates = summary.candidate_results
    if not results:
        lines.append("No spec produced a replayable return series -- nothing to interpret.")
        return lines

    best = max(candidates, key=lambda r: r.sharpe_annualized) if candidates else None
    if best is not None:
        lines.append(
            f"Best candidate raw Sharpe (baseline costs): {best.spec_id} at "
            f"{best.sharpe_annualized:+.4f} over {best.n_trading_days} trading days, against the "
            "~0.26-0.30 that pre-registration 10.2(a) derived IN ADVANCE from the paper's own "
            "Table III magnitudes."
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

    # --- VETO (i): the future-dividend placebo ---------------------------
    fidelity = summary.fidelity_by_dating.get("payment")
    if fidelity is not None:
        real_t = abs(fidelity.primary_no_fe.t_stat)
        placebo_t = abs(fidelity.placebo_no_fe.t_stat)
        tripped = np.isfinite(placebo_t) and np.isfinite(real_t) and placebo_t >= real_t
        lines.append(
            f"PRE-DECLARED VETO (i) -- THE FUTURE-DIVIDEND PLACEBO: contemporaneous |t| "
            f"{real_t:.3f} vs future-dividend placebo |t| {placebo_t:.3f}. "
            + (
                "VETO TRIPPED: the placebo predicts as strongly as the real signal, so whatever "
                "this build measured is NOT payment-date price pressure. This overrides any DSR."
                if tripped
                else "Not tripped: the placebo is weaker than the contemporaneous signal, which "
                "is the paper's own reported pattern."
            )
        )

    # --- VETO (ii): the turn-of-month control ----------------------------
    controls = [r for r in results if r.is_control]
    if controls and candidates:
        best_control = max(controls, key=lambda r: r.sharpe_annualized)
        best_candidate = max(candidates, key=lambda r: r.sharpe_annualized)
        tripped = best_control.sharpe_annualized >= best_candidate.sharpe_annualized
        lines.append(
            f"PRE-DECLARED VETO (ii) -- THE TURN-OF-MONTH CONTROL: best control "
            f"{best_control.spec_id} Sharpe {best_control.sharpe_annualized:+.4f} vs best "
            f"dividend spec {best_candidate.spec_id} Sharpe "
            f"{best_candidate.sharpe_annualized:+.4f}. "
            + (
                "VETO TRIPPED: a calendar window carrying NO dividend data matches or beats the "
                "dividend signals, so this family measured the turn-of-the-month effect wearing a "
                "dividend costume. This overrides any DSR."
                if tripped
                else "Not tripped: the dividend signals beat the pure turn-of-the-month calendar."
            )
        )

    # --- VETO (iii): the dating asymmetry --------------------------------
    payment_specs = [r for r in candidates if r.dating == "payment"]
    ex_date_specs = [r for r in candidates if r.dating == "ex_date"]
    if payment_specs and ex_date_specs:
        best_payment = max(payment_specs, key=lambda r: r.sharpe_annualized)
        best_ex = max(ex_date_specs, key=lambda r: r.sharpe_annualized)
        tripped = best_ex.sharpe_annualized > 0 and best_payment.sharpe_annualized <= 0
        lines.append(
            f"PRE-DECLARED VETO (iii) -- THE DATING ASYMMETRY: best PAYMENT-dated "
            f"{best_payment.spec_id} Sharpe {best_payment.sharpe_annualized:+.4f} vs best "
            f"EX-DATE-dated {best_ex.spec_id} Sharpe {best_ex.sharpe_annualized:+.4f}. "
            + (
                "VETO TRIPPED: a positive appears ONLY under ex-date dating, which is evidence "
                "for the ex-day run-up/reversal this project has already measured -- a DIFFERENT, "
                "already-known mechanism -- and NOT for the payment-date reinvestment channel."
                if tripped
                else "Not tripped: the result does not live exclusively in the ex-date arm."
            )
        )

    # --- WHAT VETO (iii) WAS DESIGNED TO CATCH BUT IS NOT WIRED TO SEE ------
    # Veto (iii) is operationalized on SHARPES, because that is how the
    # pre-registration wrote it. The dating asymmetry it exists to detect can
    # also show up in the REGRESSIONS, and on this run it does -- in the
    # opposite direction to the mechanism. This line reports that comparison
    # explicitly rather than leaving it for a reader to assemble from two
    # different tables, and it can only make this family look worse.
    payment_checks = summary.fidelity_by_dating.get("payment")
    ex_date_checks = summary.fidelity_by_dating.get("ex_date")
    if payment_checks is not None and ex_date_checks is not None:
        pay_t = payment_checks.primary_no_fe.t_stat
        ex_t = ex_date_checks.primary_no_fe.t_stat
        pay_bps = payment_checks.primary_no_fe.bps_per_one_sd
        ex_bps = ex_date_checks.primary_no_fe.bps_per_one_sd
        backwards = np.isfinite(pay_t) and np.isfinite(ex_t) and ex_t > abs(pay_t)
        lines.append(
            "THE DATING ASYMMETRY IN THE REGRESSIONS, WHICH VETO (iii)'s SHARPE TEST DOES NOT "
            f"SEE: [HS22]'s Table I specification gives t {pay_t:+.3f} ({pay_bps:+.2f} bp per one "
            f"SD) under the PAYMENT dating the paper itself insists on, against t {ex_t:+.3f} "
            f"({ex_bps:+.2f} bp) under the EX-DATE dating. "
            + (
                "THE EX-DATE ARM LOOKS MORE LIKE THE PAPER THAN THE PAYMENT ARM DOES, which is "
                "BACKWARDS under the stated mechanism -- the payment date is supposed to be the "
                "one carrying the reinvestment flow, and the ex-date the one carrying tax and "
                "news effects. Read together with veto (i), the honest reading is that this "
                "build's apparent signal sits on the ex-date, where this project has ALREADY "
                "measured a run-up and reversal (cross_sectional_dividend_month.py), and not on "
                "the payment-date reinvestment channel this family exists to test. Veto (iii) "
                "did not trip only because it was written as a Sharpe comparison; a successor "
                "should operationalize it on the regressions too."
                if backwards
                else "The payment arm is not weaker than the ex-date arm, so this particular "
                "asymmetry does not arise."
            )
        )

    # --- The protection that runs the other way (pre-registration 9(iv)) --
    lines.append(
        "PRE-DECLARED PROTECTION FOR THE PAPER: a null here is NOT a refutation of [HS25]. "
        "Pre-registration 10.2 computed IN ADVANCE that this build has ~1/3 of the paper's "
        "t-statistic power and that a faithful replication of the paper's own magnitude implies a "
        "Sharpe of ~0.26-0.30 -- which fails this project's 0.95 bar AND its 0.50 floor. The "
        "honest reading of a null is 'this build could not detect an effect of the size the paper "
        "reports, and would not have been able to even if the effect were exactly as described'."
    )

    tilts = [
        r
        for r in results
        if r.sharpe_annualized > 0 and r.confound.residual_sharpe < 0.5 * r.sharpe_annualized
    ]
    if tilts:
        lines.append(
            f"{len(tilts)} spec(s) with a positive raw Sharpe lose more than half of it once "
            "their exposure to buy-and-hold SPY is regressed out -- those are disguised market "
            "exposure, not timing signals."
        )
    return lines


# ===========================================================================
# PRODUCTION ENTRY POINT
# ===========================================================================


def run_dividend_pressure_screening(
    start: date = DIVIDEND_PRESSURE_FORMATION_START,
    end: date | None = None,
    provider: YFinanceProvider | None = None,
    config: DividendPressureConfig | None = None,
    specs: list[DividendPressureSpec] | None = None,
    cache_path: Path = PAYMENT_CACHE_PATH,
) -> DividendPressureScreeningSummary:
    """THE production entry point, scoped to exactly DIVIDEND_PRESSURE_FAMILY's
    34 definitions and their own n_trials.

    `start` is the first FORMATION date; the dividend and price panels are
    padded before it by HISTORY_PADDING_CALENDAR_DAYS so the trailing 252-day
    rank window and the t-20..t-272 abnormal denominator are warm, and
    formations never occur in the padding."""
    from app.services.research_lab.cross_sectional_earnings_premium import (
        build_membership_frame,
    )
    from app.services.research_lab.sp500_membership_history import (
        get_universe_over,
        membership_coverage_end,
    )

    end = end if end is not None else date.today()  # noqa: DTZ011
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else default_dividend_pressure_config()
    config.formation_start = start
    specs = specs if specs is not None else DIVIDEND_PRESSURE_FAMILY

    summary = DividendPressureScreeningSummary(n_trials=len(specs), formation_start=start)

    cache = load_payment_cache(cache_path)
    if cache is None:
        summary.warnings.append(
            f"no payment calendar at {cache_path}; run "
            "data/research_runs/fetch_dividend_payment_calendar.py first. Nothing replayed."
        )
        return summary

    padded_start = start - timedelta(days=HISTORY_PADDING_CALENDAR_DAYS)

    # The traded instrument's TOTAL-RETURN close defines the trading calendar
    # and the dependent variable.
    market_close, missing = provider.get_price_history([MARKET_TICKER], padded_start, end)
    if market_close.empty or MARKET_TICKER not in market_close.columns:
        summary.warnings.append(
            f"price panel unusable for {MARKET_TICKER}: empty={market_close.empty}, "
            f"missing={missing}. Nothing replayed."
        )
        return summary
    market = market_close[MARKET_TICKER].dropna()
    trading_days = pd.DatetimeIndex(market.index)
    summary.window_end = trading_days[-1].date()

    # The universe's SPLIT-ADJUSTED-BUT-NOT-DIVIDEND-ADJUSTED closes and split
    # ratios -- the correct price basis for a market cap, and NOT
    # get_price_history's dividend-back-adjusted close. See
    # build_aggregate_market_cap's docstring and
    # YFinanceProvider.get_market_cap_basis's.
    universe = get_universe_over(
        max(padded_start, date(2015, 1, 7)), min(end, membership_coverage_end())
    )
    summary.n_universe_tickers = len(universe)
    cap_close, splits_by_ticker, _cap_missing = provider.get_market_cap_basis(
        universe, padded_start, end
    )
    if cap_close.empty:
        summary.warnings.append("market-cap price basis is empty. Nothing replayed.")
        return summary
    cap_close = cap_close.reindex(trading_days).ffill()

    share_frame, no_shares = build_share_count_frame(cache, cap_close, splits_by_ticker)
    summary.n_no_share_count = len(no_shares)
    membership = build_membership_frame(trading_days, list(cap_close.columns))

    events, report = build_payment_events(cache, trading_days)
    summary.calendar_report = report

    dollars_by_dating: dict[str, pd.Series] = {}
    for dating in DATINGS:
        use_ex_date = dating == "ex_date"
        dollars, skipped = build_daily_dividend_dollars(
            events, share_frame, membership, trading_days, use_ex_date=use_ex_date
        )
        dollars_by_dating[dating] = dollars
        summary.skip_counts[dating] = skipped
        summary.lookahead_violations[dating] = assert_no_lookahead(
            events, use_ex_date=use_ex_date
        )

    if summary.lookahead_violations.get("payment", 0) != 0:
        raise ValueError(
            f"REFUSING TO SCREEN: {summary.lookahead_violations['payment']} imputed payment dates "
            "are on or before their own ex-date, which would put an undeclared dividend into the "
            "formation. resolve_payment_lags' plausibility bounds should make this impossible; a "
            "non-zero count means the calendar is corrupt."
        )

    aggregate_market_cap = build_aggregate_market_cap(cap_close, share_frame, membership)

    signals: dict[tuple[str, str], pd.Series] = {}
    for definition in _DIVIDEND_SIGNALS:
        for dating in DATINGS:
            signals[(definition.key, dating)] = build_signal_series(
                dollars_by_dating[dating], aggregate_market_cap, definition.key
            )

    data = DividendPressureData(
        market_close=market,
        market_returns=market.pct_change(fill_method=None).rename("market"),
        dollars_by_dating=dollars_by_dating,
        aggregate_market_cap=aggregate_market_cap,
        signals=signals,
        events=events,
        report=report,
        skip_counts=summary.skip_counts,
        no_share_count_tickers=no_shares,
    )

    denominators = policy_d_denominators(len(specs))
    summary.denominators = denominators

    for arm in COST_ARMS:
        arm_config = DividendPressureConfig(
            cost_bps=arm.cost_bps,
            short_borrow_bps_per_year=arm.short_borrow_bps_per_year,
            formation_start=start,
        )
        arm_results = screen_dividend_pressure(
            data, specs, arm_config, denominators=denominators, cost_arm=arm.key
        )
        summary.results_by_cost_arm[arm.key] = arm_results
        arm_sharpes = [r.sharpe_annualized for r in arm_results]
        summary.sigma_sr_by_cost_arm[arm.key] = (
            float(np.std(arm_sharpes, ddof=1)) if len(arm_sharpes) >= 2 else None
        )

    for dating in DATINGS:
        summary.fidelity_by_dating[dating] = compute_fidelity_checks(
            data, dating=dating, formation_start=start
        )
    summary.imputation = validate_payment_imputation(cache)
    # POST-HOC AND CORRECTIVE -- see AbnormalBurnInDiagnostic. Adds no spec and
    # changes no verdict input; it exists to establish that F6's apparent
    # scaling DISAGREEMENT is this build's own burn-in artifact rather than a
    # finding about the paper.
    summary.abnormal_burn_in = post_hoc_abnormal_burn_in_diagnostic(
        data, dating="payment", formation_start=start
    )
    return summary


__all__ = [
    "ABNORMAL_LOOKBACK_DAYS",
    "ABNORMAL_SKIP_DAYS",
    "BASELINE_COST_ARM",
    "COST_ARMS",
    "CUMULATION_DAYS",
    "DATINGS",
    "DIVIDEND_PAYMENT_FAMILY_NAME",
    "DIVIDEND_PAYMENT_N_TRIALS",
    "DIVIDEND_PRESSURE_CITATION",
    "DIVIDEND_PRESSURE_COST_BPS",
    "DIVIDEND_PRESSURE_DIRECTION",
    "DIVIDEND_PRESSURE_FAMILY",
    "DIVIDEND_PRESSURE_FORMATION_START",
    "DIVIDEND_PRESSURE_SHORT_BORROW_BPS_PER_YEAR",
    "MARKET_TICKER",
    "MAX_PLAUSIBLE_LAG_DAYS",
    "MIN_PLAUSIBLE_LAG_DAYS",
    "PAPER_CIRCULATION_DATE",
    "PAPER_SAMPLE_END",
    "PAYMENT_CACHE_PATH",
    "PLACEBO_FUTURE_LAGS",
    "RANK_WINDOW_DAYS",
    "SCREENING_FLOOR",
    "TOM_CONTROL_CITATION",
    "TOM_WINDOW_FIRST_DAYS",
    "TOM_WINDOW_LAST_DAYS",
    "TOP_N_THRESHOLDS",
    "TRADED_UNIVERSE",
    "VALIDATED_EDGE_BAR",
    "AbnormalBurnInDiagnostic",
    "CostArm",
    "DataSanity",
    "DividendPaymentEvent",
    "DividendPressureBacktestResult",
    "DividendPressureConfig",
    "DividendPressureConfound",
    "DividendPressureData",
    "DividendPressureScreeningResult",
    "DividendPressureScreeningSummary",
    "DividendPressureSpec",
    "FidelityChecks",
    "ImputationValidation",
    "LagPoint",
    "PaymentCalendarReport",
    "PrimaryRegression",
    "QuintilePoint",
    "RawPaymentCache",
    "ScalingAgreement",
    "ThresholdPoint",
    "abnormal_denominator",
    "assert_no_lookahead",
    "build_aggregate_market_cap",
    "build_daily_dividend_dollars",
    "build_dividend_pressure_disclosure",
    "build_indicator",
    "build_payment_events",
    "build_share_count_frame",
    "build_signal_series",
    "compute_confound_diagnostics",
    "compute_data_sanity",
    "compute_fidelity_checks",
    "default_dividend_pressure_config",
    "demeaned_position",
    "dsr_across_denominators",
    "future_cumulative",
    "load_payment_cache",
    "policy_d_denominators",
    "post_hoc_abnormal_burn_in_diagnostic",
    "resolve_payment_lags",
    "run_dividend_pressure_backtest",
    "run_dividend_pressure_screening",
    "screen_dividend_pressure",
    "top_n_indicator",
    "turn_of_month_indicator",
    "two_day_cumulative",
    "validate_payment_imputation",
]
