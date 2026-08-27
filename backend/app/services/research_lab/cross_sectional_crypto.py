"""The CRYPTO cross-sectional pattern family: 28 pre-declared definitions
across five genuinely distinct ranking mechanisms, screened as one family
with its own never-pooled DSR n_trials denominator.

CITATIONS:
  * Jegadeesh & Titman, "Returns to Buying Winners and Selling Losers"
    (Journal of Finance, 1993) -- cross-sectional momentum, and the
    skip-period convention this family's second mechanism uses.
  * Liu, Tsyvinski & Wu, "Common Risk Factors in Cryptocurrency" (Journal of
    Finance, 2022) -- establishes that a cross-sectional size and momentum
    factor priced in equities also prices the crypto cross-section, on a
    coin universe assembled to include coins that later died.
  * Liu & Tsyvinski, "Risks and Returns of Cryptocurrency" (Review of
    Financial Studies, 2021) -- momentum at horizons of one week to several
    months in crypto specifically.
  * De Bondt & Thaler, "Does the Stock Market Overreact?" (Journal of
    Finance, 1985); Asness, Moskowitz & Pedersen, "Value and Momentum
    Everywhere" (Journal of Finance, 2013) -- long-horizon reversal, and the
    "value = minus the long-run return" definition used here.
  * Ang, Hodrick, Xing & Zhang, "The Cross-Section of Volatility and
    Expected Returns" (Journal of Finance, 2006); Blitz & van Vliet, "The
    Volatility Effect" (Journal of Portfolio Management, 2007) -- the
    low-volatility anomaly, this family's fourth mechanism.
  * Frazzini & Pedersen, "Betting Against Beta" (Journal of Financial
    Economics, 2014) -- long low-beta / short high-beta, this family's fifth
    mechanism, with BTC standing in for the market as it does throughout the
    crypto factor literature.

WHY THIS IS A SEPARATE MODULE AND A SEPARATE SCREENING CALL. Its 28
definitions are screened alone, so the DSR's n_trials is 28 and its sigma_SR
is the spread of these 28 siblings' Sharpes. Pooling crypto into another
family's screening call would corrupt both -- a different asset class's
sibling spread is not this one's noise distribution.

================================================================================
THE 365-DAY YEAR -- THE ONE THING THIS FAMILY MUST NOT GET WRONG
================================================================================
Crypto trades 24 hours a day, 7 days a week, with no exchange holidays. That
is not a footnote; it is the single largest source of silently wrong numbers
in reusing this project's equity machinery on this data.

VERIFIED LIVE 2026-08-27, not assumed: BTC-USD returns 365/365/366/365/365/
365/366/365 rows for calendar years 2018..2025, and the 73-coin panel this
module builds has ZERO missing calendar days between its first and last row.
SPY over the same years returns 251/252/253/252/251/250/252/250.

metrics.sharpe_ratio annualized with a hardcoded sqrt(252) until 2026-08-27,
backtest_result.py annualized mean return with a hardcoded *252, and
deflated_sharpe.compute_deflated_sharpe de-annualized with the same hardcoded
252. Applied to a 365-row-per-year series that understates:
  * every Sharpe by sqrt(252/365) = 0.831, i.e. by ~17%;
  * every annualized return by 252/365 = 0.690, i.e. by ~31%;
  * and, worst of the three because it is not a simple rescaling, the
    DSR -- compute_deflated_sharpe divides the point estimate AND the
    sibling-noise benchmark down to per-period scale, so a Sharpe annualized
    at 365 but de-annualized at 252 is compared against a benchmark built on
    a different year length entirely.
All three now take a periods_per_year parameter defaulted to 252 (so every
equity, bond, FX and commodity family is byte-for-byte unaffected -- pinned
by tests/test_periods_per_year_regression.py, which replays all eight of them
against pre-fix outputs), and this family passes CRYPTO_PERIODS_PER_YEAR=365
through CrossSectionalConfig.periods_per_year.

Note what did NOT need changing: cross_sectional.FINANCING_DAYS_PER_YEAR is
already 365.0, because financing has always accrued on CALENDAR days elapsed
in every asset class. "How many calendar days has this been held" and "how
many return observations does a year of this data contain" are different
questions that happen to share an answer here and only here.

EVERY "days" NUMBER IN THIS MODULE IS A CALENDAR DAY. The harness counts
lookback_days and holding_days in ROWS. A crypto row is one calendar day, so
this family's 90-day hold is ~3 calendar months, where an equity family's
63-day hold is also ~3 calendar months but 63 rows. Windows here are stated
in the calendar units they actually mean; they are deliberately NOT the
equity families' 63/126/252, because copying those numbers across would
silently shorten every window by 252/365.

================================================================================
SURVIVORSHIP: THE ONE PLACE CRYPTO IS *BETTER* THAN THIS PROJECT'S EQUITIES
================================================================================
This project's equity families carry a disclosed, unfixable survivorship hole:
free data sources do not retain delisted US equities, so a dead name's
returns cannot be recovered at any price this project pays (the delisted-
securities vendor is on the pending-paid list). Crypto is the exception.

VERIFIED LIVE 2026-08-27: yfinance genuinely retains dead coins with their
real history intact.
  * LUNA1-USD: 1,172 rows 2019-07-26..2022-10-09, peaking at $116.41 and
    ending at $0.000306 -- the entire May-2022 Terra collapse is IN the data,
    priced all the way down, not truncated at the last healthy print.
  * MATIC-USD: 2,158 rows to 2025-03-24 (Polygon's migration to POL).
  * RNDR-USD: 1,502 rows to 2024-07-21 (Render's migration).
  * FTM-USD: 2,268 rows to 2025-01-13 (Fantom's migration to Sonic).
  * GALA-USD: 2,111 rows to 2026-07-18.
So this family INCLUDES dead coins in its universe, and they are ranked and
held on exactly the dates they were really tradeable -- see the eligibility
section below. Restricting to coins alive in 2026 would delete precisely the
population the short leg most wants to be short of.

WHAT IS STILL BIASED, and must not be claimed away. The CANDIDATE LIST is
hand-assembled in 2026 from coins that mattered at some point in the window.
A coin that was briefly liquid in 2021 and that this list simply forgot is
missing, and no amount of point-in-time gating recovers it. That residual
hole is smaller than the equity one (it omits forgotten names rather than
systematically omitting failed ones -- the five dead coins above are in) but
it is not zero, and it is why the summary reports the candidate-list size and
its construction rule as a first-class field.

DELISTING IMPUTATION IS DELIBERATELY OFF (config.impute_delisting_returns
stays False, the harness default) even though this family's long-horizon
reversal leg is exactly the population most likely to die mid-hold -- the
situation Build D2 turned the option ON for. The reason is that the option
charges a fixed Shumway-style loss on the day a price permanently stops
appearing, and in THIS data that day means something different:
  * A genuine collapse (LUNA1, and UST's depeg) is already priced all the
    way down in the series itself. Imputing an additional -42.5% on top of a
    -99.97% that already happened would double-count the loss.
  * The remaining stops are TOKEN MIGRATIONS -- MATIC->POL, RNDR->RENDER,
    FTM->S. Holders were made whole at a fixed conversion ratio; charging
    them -42.5% would fabricate a loss that no holder took.
Neither case is the equity delisting the imputation was calibrated on, so
this family takes the harness default (drop the name and renormalize the
survivors' weights, i.e. liquidate at the last real price) and says so.

================================================================================
POINT-IN-TIME ELIGIBILITY: A LIQUIDITY GATE, NOT A FIXED BASKET
================================================================================
The bond/FX/commodity families use fixed_universe_membership: every name in a
hand-chosen basket is eligible on every date, which that helper's own
docstring defends on the grounds that those baskets have no membership
boundary to get wrong and every member trades continuously across the window.

Crypto satisfies NEITHER condition, so this family does not use it. Coins are
born mid-sample, die mid-sample, and -- the case a fixed basket handles worst
-- keep printing a quote long after anyone stopped trading them. Measured on
the real panel: EOS-USD's median daily dollar volume over its whole history
is $349M but over the trailing year is $0.1M; MKR-USD's is $35.5M against
$0.2M; CEL-USD (Celsius, bankrupt in 2022) still prints a daily bar in 2026
on $0.1M. A fixed basket would rank those zombie quotes against live markets
as though they were tradeable.

So eligibility here is a real, point-in-time, data-driven gate:
  (1) trailing median daily dollar volume over CRYPTO_LIQUIDITY_WINDOW_DAYS
      >= CRYPTO_MIN_DOLLAR_VOLUME, and
  (2) the trailing stale-print fraction (share of days whose return is
      EXACTLY zero) <= CRYPTO_MAX_STALE_FRACTION.
Both are computed from strictly PRIOR rows (a .shift(1) after the rolling
window, asserted by a dedicated test), so the gate can no more see the future
than a signal can. It composes with the harness's own requirement that an
eligible name have a finite price on the formation date, which is what makes
a dead coin drop out on exactly the right day with no special-casing.

Measured breadth under this gate on the real panel, on/after the 2020-11-01
formation start: 28 to 71 eligible coins, median 50. That is genuinely wider
than the bond (8), FX (10) and commodity (11) baskets, which is why this is
the first non-equity family in this project that does NOT have to lower
config.min_names_per_leg below the harness default of 5 -- quintile legs here
run 5 to 14 names, measured.

DOLLAR VOLUME IS THE VOLUME COLUMN, NOT PRICE x VOLUME. yfinance reports
crypto Volume already denominated in USD, unlike its equity Volume which is
in shares. Verified live 2026-08-27: BTC-USD's January-2025 Volume prints
2.4e10..6.4e10, i.e. $24-64bn/day, which is BTC's real turnover; multiplying
by the ~$95,000 close instead yields ~$2e15/day, roughly 20,000x world GDP.
This module therefore reads volume directly and an assertion-backed test
pins the convention, because the error is invisible in a RANKING (multiplying
every name by its own price still leaves a plausible-looking ordering) and
would quietly re-weight the gate toward high-priced coins.

WHY THE 2020-11-01 FORMATION START. Price history is fetched from
2017-11-01, but formations do not begin until 2020-11-01, and the gap is
deliberate. Two independent reasons:
  * It gives the family's longest lookback (730 days) a full warm-up out of
    data that is BEFORE the test window, so the 730-day reversal specs and
    the 90-day momentum specs form over the identical date range and the
    DSR's sigma_SR measures signal differences rather than sample
    differences. Measured: 2020-11-01 sits at row 1,096 of the panel.
  * Before late 2020 the hand-assembled candidate list stops being a fair
    representation of what was actually liquid -- the 2018-2019 top of the
    market contains many names a 2026 list simply would not think to
    include. The gate would happily admit 13-25 names in 2019; that breadth
    is real but its COMPOSITION is the most hindsight-contaminated part of
    the sample, so it is excluded rather than used.
The resulting window is 2,124 rows, 2020-11-01..2026-08-25, ~5.82 years.

INDEPENDENT OBSERVATIONS, STATED PLAINLY. That window holds ~23 non-
overlapping formations at a 90-day hold and ~11 at a 180-day hold. Eleven is
thin, and no amount of daily-return smoothing changes it; overlapping cohorts
(CrossSectionalSpec.cohort_formation_days) are deliberately NOT used here,
because they would raise the daily observation count without creating a
single additional independent long-horizon bet, and this family already has
to defend its DSR against a 28-way search.

================================================================================
COSTS -- ~30bp ONE-WAY, SIX TIMES THE EQUITY ASSUMPTION
================================================================================
CRYPTO_COST_BPS = 30.0 one-way per unit of gross notional traded, against the
harness's 5.0 equity default and the commodity family's 5.0. This is a
deliberate, large increase, and it is the single assumption most likely to
decide whether anything here survives:
  * Centralized-exchange TAKER fees alone run 5-10bp for a non-VIP account.
  * Quoted spreads on the alt names this family's legs are actually made of
    are tens of bp, not the 1-2bp of BTC/ETH.
  * Market impact on a $10-100M/day book is real at the sizes a quintile leg
    of 5-14 alts implies.
30bp is a blended assumption sized to the ALTS, not to BTC, because a
cross-sectional leg is mostly not BTC. It is an assumption and not a measured
execution cost, which is why every positive spec's BREAKEVEN one-way cost is
reported so a reader can see exactly how much any result leans on it.

FINANCING: CRYPTO_SHORT_BORROW_BPS_PER_YEAR = 800.0, halved to 400.0 on
gross notional held by the harness's documented arithmetic (financing accrues
on gross 2.0, half the book is short, so 800bp on the 1.0 short leg is 400bp
on gross 2.0). 8%/yr is at the LOW end of observed centralized-exchange
margin borrow for alts (commonly 0.02-0.05%/day, i.e. 7-18%/yr) and above
what majors cost.

AND THE CREDIT THIS FAMILY DELIBERATELY DOES NOT TAKE. The same short leg
could be expressed in perpetual futures, where funding is historically
POSITIVE more often than not -- longs pay shorts -- so a short book would
have EARNED carry rather than paid borrow over much of this sample. Modelling
it that way would turn a cost into a subsidy and materially flatter every
number below. This family charges the spot-borrow cost instead and states
the alternative, because a result that only survives by booking a funding
credit is a result about crypto's bull-market funding regime, not about the
signal. Short AVAILABILITY is not modelled at any price.

THE HOLDING FLOOR IS 90 DAYS, and that is a cost decision, not a signal one.
Every family this project has screened has found shorter holds losing to
longer siblings, because the turnover charge scales with rebalance frequency
while the financing charge does not. At 30bp one-way that arithmetic is six
times harsher here than in equities: a 30-day hold would pay the reformation
charge three times as often as a 90-day hold for the same book. No sub-90-day
variant is included, and an assertion in _build_crypto_family enforces it.

================================================================================
FAMILY SIZE -- 28, COMPUTED FROM THE AXES AND FIXED BEFORE ANY RUN
================================================================================
Five mechanisms that are genuinely different questions, not one question at
five parameter settings:
  * momentum          -- trailing return over {90, 180, 365}            (3)
  * momentum skip-7d  -- same windows, last 7 days excluded             (3)
  * long-run reversal -- NEGATED trailing return over {540, 730}        (2)
  * low volatility    -- NEGATED trailing realized vol over {30,90,180} (3)
  * beta vs BTC       -- NEGATED OLS beta on BTC over {90, 180, 365}    (3)
                                                        14 signal definitions
x CRYPTO_HOLDING_DAYS {90, 180}                                 = 28 specs

The reversal windows are 540/730 rather than a third, longer one because 730
already consumes two of the panel's pre-start years; a 1,095-day window would
push the formation start past 2021 and cost more sample than the extra
definition is worth.

LEG WEIGHTING IS FIXED AT inverse_vol AND IS NOT AN AXIS. The FX and
commodity families swept {equal, inverse_vol} and thereby doubled their
n_trials. That is not free, and here the answer is knowable in advance:
crypto's cross-sectional volatility dispersion is extreme (BTC's realized vol
against a small alt's differs by 3-5x, wider than the commodity basket's 3x
that already justified inverse-vol there), so an equally weighted leg is
dominated by whichever alt happens to be the most volatile and measures that
coin rather than the signal. Choosing one weighting on that argument BEFORE
the run halves the multiple-comparisons burden relative to sweeping both.

BOTH LEGS ARE RANKED (portfolio="long_short" throughout). No
long_universe_hedged variant: hedging a 5-14 name leg against the equal-
weighted mean of the same 28-71 name universe it was drawn from is a
construction artifact rather than a distinct hypothesis -- the FX and
commodity families' identical reasoning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    MembershipFn,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
)
from app.services.research_lab.metrics import CALENDAR_DAYS_PER_YEAR, sharpe_ratio

logger = logging.getLogger(__name__)

# --- the calendar -----------------------------------------------------------

# 365, not 252. THE defining property of this asset class for every
# annualized number this family reports -- see the module docstring's
# 365-DAY YEAR section for the live verification and for exactly what each
# of the three affected quantities was understated by.
CRYPTO_PERIODS_PER_YEAR = float(CALENDAR_DAYS_PER_YEAR)

# --- universe ---------------------------------------------------------------

# The hand-assembled CANDIDATE list: coins that were meaningfully liquid at
# some point in 2020-2026, INCLUDING five that subsequently died or migrated
# (LUNA1, MATIC, RNDR, FTM, GALA). Membership in this list does NOT make a
# coin eligible on any date -- the point-in-time liquidity gate below decides
# that. This list only bounds what the gate is allowed to consider.
#
# Its residual hindsight bias is disclosed in the module docstring and
# reported as a typed field on every summary: it omits coins a 2026 author
# forgot, though not (as the equity families must) coins that failed.
CRYPTO_UNIVERSE: tuple[str, ...] = (
    "BTC-USD", "ETH-USD", "XRP-USD", "BNB-USD", "ADA-USD", "SOL-USD", "DOGE-USD",
    "DOT-USD", "AVAX-USD", "LINK-USD", "LTC-USD", "BCH-USD", "XLM-USD", "TRX-USD",
    "ATOM-USD", "ETC-USD", "XMR-USD", "ALGO-USD", "VET-USD", "FIL-USD", "ICP-USD",
    "HBAR-USD", "EOS-USD", "AAVE-USD", "MKR-USD", "CRV-USD", "SNX-USD", "YFI-USD",
    "SUSHI-USD", "ZEC-USD", "DASH-USD", "NEO-USD", "THETA-USD", "EGLD-USD",
    "XTZ-USD", "NEAR-USD", "SAND-USD", "MANA-USD", "AXS-USD", "ENJ-USD", "CHZ-USD",
    "BAT-USD", "ZIL-USD", "QNT-USD", "KSM-USD", "WAVES-USD", "UNI7083-USD",
    "CAKE-USD", "RUNE-USD", "KAVA-USD", "HNT-USD", "AR-USD", "FLOW-USD", "LRC-USD",
    "ZRX-USD", "KNC-USD", "RVN-USD", "DCR-USD", "QTUM-USD", "ONT-USD", "ICX-USD",
    "OMG-USD", "REN-USD", "WAXP-USD", "AMP-USD", "SRM-USD", "CEL-USD",
    # --- coins that DIED or MIGRATED: the survivorship-bias fix ------------
    "LUNA1-USD",   # Terra; collapse of 2022-05 priced in full, ends 2022-10-09
    "MATIC-USD",   # Polygon; feed ends 2025-03-24 on the POL migration
    "RNDR-USD",    # Render; feed ends 2024-07-21 on the RENDER migration
    "FTM-USD",     # Fantom; feed ends 2025-01-13 on the Sonic migration
    "GALA-USD",    # Gala; feed ends 2026-07-18
    "FTT-USD",     # FTX exchange token; the 2022-11 collapse is priced in
)

# The market proxy for the beta mechanism, and itself a rankable member of
# the cross-section (Frazzini-Pedersen rank the market too; its own beta is
# 1.0 by construction). Asserted to be in CRYPTO_UNIVERSE below.
CRYPTO_MARKET_TICKER = "BTC-USD"

# PRE-DECLARED EXCLUSIONS, each with the measurement that justifies it
# (all verified live 2026-08-27 on the real feed). Kept as a typed record
# rather than a comment so the decision is auditable and so a test can assert
# that no excluded ticker ever re-enters the universe.
#
# Two rules, applied ex ante:
#  (1) STABLECOINS. A coin pegged to $1 has no cross-sectional return
#      dispersion to rank on; including one would put a ~0%-return name in
#      whichever leg the ranking happened to sweep it into. Note this rule
#      also removes UST-USD, whose 2022 depeg would have been a PROFITABLE
#      short -- so the rule costs this family a winner rather than hiding a
#      loser, which is the direction an honest ex-ante rule should err.
#  (2) BROKEN OR MIS-MAPPED FEEDS. A ticker whose series is mostly repeated
#      prints, or which yfinance maps to a different token than its name
#      implies. These are data defects, not research findings.
CRYPTO_EXCLUDED: dict[str, str] = {
    "USDT-USD": "stablecoin — pegged, no cross-sectional dispersion to rank",
    "USDC-USD": "stablecoin — pegged, no cross-sectional dispersion to rank",
    "DAI-USD": "stablecoin — pegged, no cross-sectional dispersion to rank",
    "UST-USD": (
        "stablecoin by design (rule 1 applied ex ante); its 2022 depeg would have been a "
        "profitable SHORT, so excluding it makes this family's test harder, not easier"
    ),
    "SHIB-USD": "broken feed — 63.5% of daily returns are EXACTLY zero, and the series touches 0",
    "UNI-USD": (
        "mis-mapped — median daily dollar volume $0.0M and 13.3% stale prints; this is not "
        "Uniswap. Uniswap is UNI7083-USD ($214M/day, 0.0% stale), which IS in the universe"
    ),
    "APE-USD": (
        "mis-mapped — $0.0M/day, 11.4% stale, and its history starts 2020-10-01, ~17 months "
        "BEFORE ApeCoin launched: a different token wearing the ticker"
    ),
    "COMP-USD": "mis-mapped — 46.3% stale, $0.0M/day, feed dies 2022-01-15 while Compound is alive",
    "GRT-USD": "mis-mapped — $0.0M/day, feed dies 2022-04-01 while The Graph is alive",
    "ANC-USD": (
        "unusable — median daily dollar volume ~$1 total, and the series never shows Anchor "
        "Protocol's May-2022 collapse. It downloads real-looking rows but is not a rankable "
        "market (a correction to the feasibility scout's note, which listed it as usable)"
    ),
    "TON11419-USD": (
        "unusable — exactly 1 row of history on this feed (2026-06-15), so no window of any "
        "length can be computed for it"
    ),
    "POL-USD": (
        "not MATIC's successor on this feed — $0.4M/day, dies 2023-10-31, i.e. BEFORE the "
        "2024 MATIC->POL migration it would have to represent"
    ),
}

# Fetch start. Deliberately ~3 years before the first formation so the
# 730-day lookback warms entirely out of pre-test data -- see the module
# docstring's WHY THE 2020-11-01 FORMATION START section.
CRYPTO_PRICE_HISTORY_START = date(2017, 11, 1)

# The first FORMATION date. Not a data-availability limit (the panel starts
# three years earlier); a composition-honesty limit.
CRYPTO_FORMATION_START = date(2020, 11, 1)

# --- point-in-time eligibility ----------------------------------------------

# One quarter of trailing daily dollar volume, refusing an estimate from
# fewer than two months of it -- the same window/floor register as the FX and
# commodity families' inverse-vol basis, kept identical for cross-family
# consistency rather than separately calibrated.
CRYPTO_LIQUIDITY_WINDOW_DAYS = 90
CRYPTO_LIQUIDITY_MIN_PERIODS = 60

# $25M median daily dollar volume. Sized so a quintile leg of 5-14 names is
# plausibly tradeable at institutional-but-not-enormous size, and so the
# zombie quotes the module docstring measures (EOS at $0.1M/day, MKR at
# $0.2M, CEL at $0.1M) fall out on their own dates rather than by name.
CRYPTO_MIN_DOLLAR_VOLUME = 25_000_000.0

# A trailing window more than this fraction exactly-zero returns is a dead
# feed being quoted, not a market. Set well above the ~0-1% a live crypto
# market prints and well below SHIB-USD's measured 63.5%, so it is a guard
# against a feed going stale MID-SAMPLE (which no static exclusion list can
# catch) rather than a filter that routinely fires.
CRYPTO_MAX_STALE_FRACTION = 0.20


def build_dollar_volume(volume: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """Daily dollar volume per coin, aligned to `close`.

    THE VOLUME COLUMN IS ALREADY USD and is returned as-is. This function
    exists precisely so that fact has one documented home instead of being an
    unexplained missing multiplication at the call site. Verified live
    2026-08-27: BTC-USD's Volume prints $24-64bn/day in January 2025, which
    is BTC's real turnover; close * volume would give ~$2e15/day. `close` is
    taken only to align the frame (and to prove the caller had it), never
    multiplied in."""
    return volume.reindex(index=close.index, columns=close.columns)


def build_eligibility(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """A boolean (dates x tickers) frame: was this coin a liquid, non-stale
    market as of this date, judged ONLY on rows strictly before it?

    POINT-IN-TIME BY CONSTRUCTION. Both rolling statistics are .shift(1)ed,
    so the value on row i is computed from rows i-window..i-1 and can never
    include row i itself, let alone anything after it. A dedicated test
    proves that mutating a future row leaves every earlier eligibility flag
    unchanged.

    Note this frame is only half the gate: run_cross_sectional_backtest
    independently requires an eligible name to have a finite price on the
    formation date. The composition is what makes a coin's birth and death
    handle themselves -- a coin with no price yet has no dollar volume
    either, and a dead coin's flag goes False as its trailing volume decays
    while the harness's price check removes it the day the feed stops."""
    dollar_volume = build_dollar_volume(volume, close)
    liquid = (
        dollar_volume.rolling(
            CRYPTO_LIQUIDITY_WINDOW_DAYS, min_periods=CRYPTO_LIQUIDITY_MIN_PERIODS
        )
        .median()
        .shift(1)
        >= CRYPTO_MIN_DOLLAR_VOLUME
    )

    returns = close.pct_change(fill_method=None)
    # A NaN return (no price that day) is not a stale print; only an
    # observed, exactly-zero move is. Counting NaNs as stale would penalize a
    # coin for its own pre-inception rows.
    is_stale = (returns == 0.0).where(returns.notna())
    stale_fraction = (
        is_stale.rolling(
            CRYPTO_LIQUIDITY_WINDOW_DAYS, min_periods=CRYPTO_LIQUIDITY_MIN_PERIODS
        )
        .mean()
        .shift(1)
    )
    # An unmeasurable stale fraction (too few observations in the window) is
    # NOT treated as passing: a coin without enough history to judge is not
    # yet a market this family will rank.
    fresh = stale_fraction <= CRYPTO_MAX_STALE_FRACTION

    # A coin with no price TODAY is not a market today, whatever its trailing
    # volume says. Without this term the flag lingers for up to
    # CRYPTO_LIQUIDITY_WINDOW_DAYS after a coin's feed stops, because the
    # rolling median still has enough prior observations to compute (measured
    # on the real panel: LUNA1-USD's last price is 2022-10-09 but its
    # unguarded flag stayed True to 2022-11-09). The harness's own
    # finite-price check means that never mis-ranked anything, but it did
    # make this frame -- which is also read by the equal-weight basket factor
    # and by the run summary's dead-coin report -- describe a slightly
    # different universe than the one actually traded. Reading close on the
    # SAME row is not look-ahead: it is the formation date's own price, the
    # very thing the harness also requires.
    priced = close.notna()

    return (liquid & fresh & priced).fillna(False).astype(bool)


def liquidity_membership(eligibility: pd.DataFrame) -> MembershipFn:
    """Wraps an eligibility frame as the harness's MembershipFn.

    This is crypto's replacement for fixed_universe_membership, which this
    family deliberately does not use -- see the module docstring's
    POINT-IN-TIME ELIGIBILITY section for why a fixed basket is the wrong
    gate for an asset class with births, deaths and zombie quotes.

    Lookup is by DATE (the harness hands a datetime.date), against a dict
    built once, so a formation date absent from the frame answers False for
    everyone rather than raising -- the same "no" rather than "unknown"
    convention sp500_membership_history.was_member keeps."""
    by_date: dict[date, frozenset[str]] = {
        ts.date(): frozenset(row.index[row.to_numpy()]) for ts, row in eligibility.iterrows()
    }

    def _is_member(ticker: str, on: date) -> bool:
        return ticker in by_date.get(on, frozenset())

    return _is_member


# --- price panel ------------------------------------------------------------


def build_crypto_price_panel(
    provider: YFinanceProvider,
    end: date,
    start: date = CRYPTO_PRICE_HISTORY_START,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """The RAGGED (dates x coins) total-return close panel and its matching
    volume frame, plus the tickers that resolved no data at all.

    RAGGED IS THE WHOLE POINT, and it is the one structural difference from
    build_commodities_price_panel / build_fx_price_panel, both of which
    dropna(how="any") to a common window. Doing that here would be
    catastrophic rather than merely conservative: MATIC-USD's feed ends
    2025-03-24, so an all-names-priced window would truncate the ENTIRE panel
    there and delete the last 17 months for all 72 other coins -- the
    survivorship bias this family exists to avoid, reintroduced through the
    back door by a data-shaping convenience. A coin is simply NaN before it
    is born and after it dies, and the eligibility gate plus the harness's
    own finite-price check handle both ends.

    Rows are restricted to dates on which at least one coin is priced;
    non-positive prices become NaN (a zero or negative crypto print is a feed
    artifact, never a market)."""
    tickers = [t for t in CRYPTO_UNIVERSE if t not in CRYPTO_EXCLUDED]
    frames, _missing = provider.get_daily_ohlcv(tickers, start, end)
    if not frames or "close" not in frames or frames["close"].empty:
        return pd.DataFrame(), pd.DataFrame(), list(tickers)

    raw_close = frames["close"]
    raw_volume = frames.get("volume", pd.DataFrame())
    missing = [t for t in tickers if t not in raw_close.columns]
    present = [t for t in tickers if t in raw_close.columns]

    close = raw_close[present].apply(pd.to_numeric, errors="coerce")
    close = close.where(close > 0.0).sort_index()
    close = close.dropna(how="all")
    if close.empty:
        return pd.DataFrame(), pd.DataFrame(), missing

    if raw_volume.empty:
        volume = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    else:
        volume = (
            raw_volume.reindex(index=close.index, columns=close.columns)
            .apply(pd.to_numeric, errors="coerce")
            .where(lambda v: v >= 0.0)
        )
    return close, volume, missing


# --- inverse-volatility weighting basis -------------------------------------

# Same trailing window and floor as the FX and commodity families', kept
# identical for cross-family consistency rather than recalibrated -- but note
# that 90 rows here is 90 CALENDAR days (~3 months), where their 63 rows is
# ~3 months too. The equal calendar span is the thing being held constant.
CRYPTO_VOL_WINDOW_DAYS = 90
CRYPTO_VOL_MIN_PERIODS = 30


def build_inverse_vol_basis(prices: pd.DataFrame) -> pd.DataFrame:
    """1 / trailing realized volatility per coin, aligned to `prices` -- the
    leg_weight_basis every spec in this family weights its legs by.
    Point-in-time by construction (a rolling std at row i reads rows <= i).

    Non-finite or zero vol yields NaN, which _resolve_leg_weights treats as
    grounds to fall back to magnitude weighting for that whole leg -- counted
    and reported, never silent."""
    returns = prices.pct_change(fill_method=None)
    vol = returns.rolling(CRYPTO_VOL_WINDOW_DAYS, min_periods=CRYPTO_VOL_MIN_PERIODS).std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        basis = 1.0 / vol
    return basis.replace([np.inf, -np.inf], np.nan)


# --- signals ----------------------------------------------------------------

# Same 0.8 register as every other coverage floor in this project: a signal
# window under 80% populated is refused (NaN) rather than computed on
# whatever little data exists. It binds much harder here than on a common-
# window panel, and that is intentional -- it is what stops a coin three
# weeks past its inception from being ranked on a 365-day momentum window it
# does not have.
MIN_SIGNAL_OBS_FRACTION = 0.8

# The skip applied by the second mechanism: one week. Jegadeesh & Titman skip
# the most recent month to avoid contaminating a momentum signal with
# short-horizon reversal; crypto's documented reversal horizon is roughly a
# week rather than a month, which is what this family skips.
CRYPTO_MOMENTUM_SKIP_DAYS = 7


def _trailing_return(window: pd.DataFrame, required_obs: int) -> pd.Series:
    """P_last / P_first - 1 down a window, refusing any column with fewer
    than required_obs observations in it."""
    if window.empty:
        return pd.Series(dtype=float)
    first = window.iloc[0]
    last = window.iloc[-1]
    n_obs = window.notna().sum()
    signal = last / first - 1.0
    signal[n_obs < required_obs] = np.nan
    signal[~np.isfinite(signal)] = np.nan
    return signal


def signal_crypto_momentum(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """Liu/Tsyvinski/Wu cross-sectional crypto momentum: trailing
    lookback_days total return, long past winners and short past losers
    (higher-is-long is both the harness's convention and the literature's
    direction). lookback_days is CALENDAR days -- see the module docstring."""
    window = history.close.iloc[-lookback_days:]
    return _trailing_return(window, int(lookback_days * MIN_SIGNAL_OBS_FRACTION))


def signal_crypto_momentum_skip_week(
    history: CrossSectionalData,
    *,
    lookback_days: int,
    skip_days: int = CRYPTO_MOMENTUM_SKIP_DAYS,
) -> pd.Series:
    """Momentum measured from t-lookback to t-skip, EXCLUDING the most recent
    skip_days -- Jegadeesh & Titman's skip convention at crypto's roughly
    one-week reversal horizon.

    A genuinely different mechanism from plain momentum, not a parameter
    variant of it: the two disagree about whether the last week's move is
    signal or noise, which is exactly the question a skip period asks. If the
    two rank the cross-section nearly identically on real data, that is a
    finding this family reports (see the mechanism-correlation diagnostic),
    not an assumption it makes."""
    if lookback_days <= skip_days:
        raise ValueError(
            f"lookback_days ({lookback_days}) must exceed skip_days ({skip_days}) — otherwise the "
            "skip consumes the entire measurement window and the signal is empty by construction."
        )
    window = history.close.iloc[-lookback_days:]
    measured = window.iloc[: len(window) - skip_days]
    return _trailing_return(measured, int((lookback_days - skip_days) * MIN_SIGNAL_OBS_FRACTION))


def signal_crypto_long_run_reversal(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """De Bondt-Thaler reversal / AMP "value": the NEGATED trailing
    lookback_days return, so multi-year losers score highest and land in the
    long leg. The sign flip lives on the signal because the harness has no
    direction flag and a negation is exactly equivalent -- the same
    construction the FX, commodity and D2 reversals use."""
    return -signal_crypto_momentum(history, lookback_days=lookback_days)


def signal_crypto_low_volatility(history: CrossSectionalData, *, lookback_days: int) -> pd.Series:
    """Ang/Hodrick/Xing/Zhang and Blitz/van Vliet low-volatility: the NEGATED
    trailing realized volatility of daily returns, so the CALMEST coins score
    highest and land in the long leg.

    Distinct from the beta mechanism below, and not merely a rescaling of it:
    this ranks TOTAL risk, that one ranks SYSTEMATIC risk. In a cross-section
    where idiosyncratic variance dominates -- which crypto's does -- the two
    orderings genuinely differ, and the run reports their realized
    correlation rather than assuming it."""
    window = history.close.iloc[-(lookback_days + 1) :]
    returns = window.pct_change(fill_method=None)
    n_obs = returns.notna().sum()
    vol = returns.std(ddof=1)
    signal = -vol
    signal[n_obs < int(lookback_days * MIN_SIGNAL_OBS_FRACTION)] = np.nan
    signal[~np.isfinite(signal)] = np.nan
    # A perfectly flat window has vol 0 -> signal -0.0, which ranks as the
    # calmest possible coin. That is a stale feed, not a calm market; the
    # eligibility gate is what excludes it, and this guard makes the
    # dependence explicit rather than implicit.
    signal[vol <= 0.0] = np.nan
    return signal


def signal_crypto_btc_beta(
    history: CrossSectionalData,
    *,
    lookback_days: int,
    market_ticker: str = CRYPTO_MARKET_TICKER,
) -> pd.Series:
    """Frazzini-Pedersen betting-against-beta: the NEGATED OLS beta of each
    coin's daily returns on BTC's over the trailing window, so LOW-beta coins
    score highest and land in the long leg.

    BTC is the market proxy throughout the crypto factor literature, and it
    is itself a ranked member of the cross-section (its own beta is 1.0 by
    construction, exactly as Frazzini-Pedersen rank the market).

    Returns all-NaN when BTC is not in the view -- a loud, testable contract
    rather than a silent fallback to some other market definition. In
    production BTC clears the eligibility gate on every date in the sample,
    so this never fires; it exists so that a universe misconfiguration
    produces no signal instead of a signal about the wrong market.

    Deliberately regresses on BTC rather than on the view's own equal-
    weighted mean: the equal-weight crypto basket is used as an INDEPENDENT
    confound factor when auditing this family's results (see
    compute_crypto_factor_exposure), and a signal built from the same basket
    it is later checked against would make that check circular."""
    columns = list(history.close.columns)
    if market_ticker not in columns:
        return pd.Series(np.nan, index=columns, dtype=float)

    window = history.close.iloc[-(lookback_days + 1) :]
    returns = window.pct_change(fill_method=None)
    market = returns[market_ticker]
    var_market = market.var(ddof=1)
    if not np.isfinite(var_market) or var_market <= 0.0:
        return pd.Series(np.nan, index=columns, dtype=float)

    required = int(lookback_days * MIN_SIGNAL_OBS_FRACTION)
    # Pairwise-complete covariance: a coin born mid-window is measured on the
    # days it and BTC both traded, then rejected by the coverage floor if
    # that is too few. .cov() is pairwise by default and NaN-skipping.
    covariance = returns.apply(lambda column: column.cov(market))
    n_obs = returns.notna().mul(market.notna(), axis=0).sum()

    beta = covariance / var_market
    signal = -beta
    signal[n_obs < required] = np.nan
    signal[~np.isfinite(signal)] = np.nan
    return signal


# --- the family -------------------------------------------------------------

CRYPTO_MOMENTUM_CITATION = (
    "Jegadeesh & Titman, 'Returns to Buying Winners and Selling Losers' (Journal of Finance, "
    "1993); Liu, Tsyvinski & Wu, 'Common Risk Factors in Cryptocurrency' (Journal of Finance, 2022)"
)
CRYPTO_SKIP_CITATION = (
    "Jegadeesh & Titman, 'Returns to Buying Winners and Selling Losers' (Journal of Finance, "
    "1993), on skipping the most recent period to separate momentum from short-horizon "
    "reversal; Liu & Tsyvinski, 'Risks and Returns of Cryptocurrency' (Review of Financial "
    "Studies, 2021), on crypto's roughly one-week reversal horizon"
)
CRYPTO_REVERSAL_CITATION = (
    "De Bondt & Thaler, 'Does the Stock Market Overreact?' (Journal of Finance, 1985); Asness, "
    "Moskowitz & Pedersen, 'Value and Momentum Everywhere' (Journal of Finance, 2013)"
)
CRYPTO_LOWVOL_CITATION = (
    "Ang, Hodrick, Xing & Zhang, 'The Cross-Section of Volatility and Expected Returns' (Journal "
    "of Finance, 2006); Blitz & van Vliet, 'The Volatility Effect' (Journal of Portfolio "
    "Management, 2007)"
)
CRYPTO_BETA_CITATION = (
    "Frazzini & Pedersen, 'Betting Against Beta' (Journal of Financial Economics, 2014), with "
    "BTC as the market proxy per Liu, Tsyvinski & Wu (Journal of Finance, 2022)"
)

# The pre-declared axes. Their arithmetic IS the family size -- see
# CRYPTO_N_TRIALS, asserted against the built list. ALL IN CALENDAR DAYS.
CRYPTO_MOMENTUM_LOOKBACK_DAYS: tuple[int, ...] = (90, 180, 365)
CRYPTO_SKIP_LOOKBACK_DAYS: tuple[int, ...] = (90, 180, 365)
CRYPTO_REVERSAL_LOOKBACK_DAYS: tuple[int, ...] = (540, 730)
CRYPTO_LOWVOL_LOOKBACK_DAYS: tuple[int, ...] = (30, 90, 180)
CRYPTO_BETA_LOOKBACK_DAYS: tuple[int, ...] = (90, 180, 365)
CRYPTO_HOLDING_DAYS: tuple[int, ...] = (90, 180)

# 3 momentum + 3 skip-momentum + 2 reversal + 3 low-vol + 3 beta.
CRYPTO_N_SIGNAL_DEFINITIONS = (
    len(CRYPTO_MOMENTUM_LOOKBACK_DAYS)
    + len(CRYPTO_SKIP_LOOKBACK_DAYS)
    + len(CRYPTO_REVERSAL_LOOKBACK_DAYS)
    + len(CRYPTO_LOWVOL_LOOKBACK_DAYS)
    + len(CRYPTO_BETA_LOOKBACK_DAYS)
)

# The pre-declared family size and this family's honest, never-pooled DSR
# n_trials denominator: 14 signal definitions x 2 holds = 28. Computed from
# the axes rather than typed as a literal so the two can never disagree;
# _build_crypto_family asserts the built list matches.
CRYPTO_N_TRIALS = CRYPTO_N_SIGNAL_DEFINITIONS * len(CRYPTO_HOLDING_DAYS)

# Quintiles. At the measured 28-71 eligible coins this yields disjoint legs
# of 5-14, so the harness's DEFAULT min_names_per_leg of 5 is never breached
# -- the first non-equity family in this project that does not have to lower
# it (bonds runs 2, FX and commodities 3).
CRYPTO_RANK_FRACTION = 0.2
CRYPTO_MIN_NAMES_PER_LEG = 5

# Every spec shares the family-max lookback so all 28 form over the identical
# date range and the DSR's sigma_SR measures signal differences, not sample
# differences -- cross_sectional_fx.FX_LOOKBACK_DAYS' argument, adopted
# wholesale. Costless here because the shared lookback is warmed entirely out
# of pre-formation-start data.
CRYPTO_LOOKBACK_DAYS = max(CRYPTO_REVERSAL_LOOKBACK_DAYS)

# See the module docstring's COSTS section. 30bp one-way is six times the
# harness's equity default and is sized to the ALTS a quintile leg is
# actually made of, not to BTC.
CRYPTO_COST_BPS = 30.0

# 800bp/yr short-leg borrow, halved to 400bp/yr on gross notional held by the
# harness field's own documented arithmetic. See the module docstring for why
# the perpetual-futures funding CREDIT that would often have applied instead
# is deliberately not taken.
CRYPTO_SHORT_BORROW_BPS_PER_YEAR = 800.0
CRYPTO_FINANCING_BPS_PER_YEAR = CRYPTO_SHORT_BORROW_BPS_PER_YEAR / 2.0

# The single, pre-declared leg weighting -- NOT an axis. See the module
# docstring's FAMILY SIZE section for why fixing it on an ex-ante argument is
# better than sweeping it and doubling n_trials.
CRYPTO_LEG_WEIGHTING = "inverse_vol"


def _build_crypto_family() -> list[CrossSectionalSpec]:
    """Assembles the full, fixed 28-definition Crypto family: 14 signal
    definitions x CRYPTO_HOLDING_DAYS, every one long_short and every one
    inverse-vol weighted."""
    specs: list[CrossSectionalSpec] = []

    def add(pattern_id: str, family: str, citation: str, signal_fn) -> None:
        for holding in CRYPTO_HOLDING_DAYS:
            specs.append(
                CrossSectionalSpec(
                    pattern_id=f"{pattern_id}_h{holding}",
                    family=family,
                    citation=citation,
                    signal_fn=signal_fn,
                    lookback_days=CRYPTO_LOOKBACK_DAYS,
                    holding_days=holding,
                    portfolio="long_short",
                    rank_fraction=CRYPTO_RANK_FRACTION,
                    leg_weighting=CRYPTO_LEG_WEIGHTING,  # type: ignore[arg-type]
                )
            )

    for lookback in CRYPTO_MOMENTUM_LOOKBACK_DAYS:
        add(
            f"xc_momentum_l{lookback}",
            "crypto_momentum",
            CRYPTO_MOMENTUM_CITATION,
            lambda h, lb=lookback: signal_crypto_momentum(h, lookback_days=lb),
        )

    for lookback in CRYPTO_SKIP_LOOKBACK_DAYS:
        add(
            f"xc_momentum_skip{CRYPTO_MOMENTUM_SKIP_DAYS}_l{lookback}",
            "crypto_momentum_skip_week",
            CRYPTO_SKIP_CITATION,
            lambda h, lb=lookback: signal_crypto_momentum_skip_week(h, lookback_days=lb),
        )

    for lookback in CRYPTO_REVERSAL_LOOKBACK_DAYS:
        add(
            f"xc_reversal_l{lookback}",
            "crypto_long_run_reversal",
            CRYPTO_REVERSAL_CITATION,
            lambda h, lb=lookback: signal_crypto_long_run_reversal(h, lookback_days=lb),
        )

    for lookback in CRYPTO_LOWVOL_LOOKBACK_DAYS:
        add(
            f"xc_lowvol_l{lookback}",
            "crypto_low_volatility",
            CRYPTO_LOWVOL_CITATION,
            lambda h, lb=lookback: signal_crypto_low_volatility(h, lookback_days=lb),
        )

    for lookback in CRYPTO_BETA_LOOKBACK_DAYS:
        add(
            f"xc_btcbeta_l{lookback}",
            "crypto_betting_against_beta",
            CRYPTO_BETA_CITATION,
            lambda h, lb=lookback: signal_crypto_btc_beta(h, lookback_days=lb),
        )

    assert len(specs) == CRYPTO_N_TRIALS, (
        f"Crypto family has {len(specs)} definitions, not the pre-declared {CRYPTO_N_TRIALS} "
        f"({CRYPTO_N_SIGNAL_DEFINITIONS} signal definitions x {len(CRYPTO_HOLDING_DAYS)} holds) — "
        "this family's whole point is being an exact, fixed enumeration declared before any run; "
        "a size drift here silently changes the DSR's n_trials denominator."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert CRYPTO_N_SIGNAL_DEFINITIONS == 14
    # Close-only, structurally: no signal here reads open/volume/market cap/
    # the price-only basis/share counts, and none may quietly start to
    # without this family being re-declared. (Volume is read by the
    # ELIGIBILITY gate, which is not a signal and never enters a spec.)
    assert not any(
        s.requires_open
        or s.requires_volume
        or s.requires_market_cap
        or s.requires_price_only_close
        or s.requires_shares_outstanding
        for s in specs
    ), "the crypto family is close-only by design"
    assert all(s.portfolio == "long_short" for s in specs)
    assert all(s.leg_weighting == CRYPTO_LEG_WEIGHTING for s in specs)
    assert all(s.lookback_days == CRYPTO_LOOKBACK_DAYS for s in specs)
    assert all(s.cohort_formation_days is None for s in specs), (
        "overlapping cohorts would raise this family's daily observation count without adding a "
        "single independent long-horizon bet — see the module docstring"
    )
    assert all(s.holding_days in CRYPTO_HOLDING_DAYS for s in specs)
    assert min(CRYPTO_HOLDING_DAYS) >= 90, (
        "a sub-90-calendar-day hold multiplies this family's turnover charge without touching its "
        "time-based financing charge, and at 30bp one-way that arithmetic is six times harsher "
        "than in equities — see the module docstring's HOLDING FLOOR paragraph. Shorter holds "
        "have lost to their longer siblings in every family this project has screened."
    )
    assert CRYPTO_MARKET_TICKER in CRYPTO_UNIVERSE, (
        "the beta mechanism's market proxy must be in the universe"
    )
    # The exclusion rules are part of the family's identity: an excluded
    # ticker must never silently re-enter the universe.
    assert not (set(CRYPTO_EXCLUDED) & set(CRYPTO_UNIVERSE)), (
        "a ticker excluded by the stablecoin/broken-feed rules is in the universe"
    )
    return specs


def build_crypto_family() -> list[CrossSectionalSpec]:
    """Public wrapper over _build_crypto_family — see that function. Built
    per call (not a module-level constant) for symmetry with the FX and
    commodity families' API; nothing in a spec depends on runtime data."""
    return _build_crypto_family()


def default_crypto_config() -> CrossSectionalConfig:
    """This family's own calendar/cost/leg configuration, as a function
    rather than a module-level singleton so callers cannot mutate a shared
    object (the harness writes formation_start onto whatever config it is
    given).

    periods_per_year=365 is the load-bearing field here — see the module
    docstring's 365-DAY YEAR section."""
    return CrossSectionalConfig(
        cost_bps=CRYPTO_COST_BPS,
        min_names_per_leg=CRYPTO_MIN_NAMES_PER_LEG,
        financing_bps_per_year=CRYPTO_FINANCING_BPS_PER_YEAR,
        periods_per_year=CRYPTO_PERIODS_PER_YEAR,
    )


# --- diagnostics and the confound check -------------------------------------


@dataclass
class CryptoFactorExposure:
    """What is left of a return stream after the two obvious crypto-market
    confounds are removed.

    THIS, NOT THE HEADLINE SHARPE, IS WHAT DECIDES whether a positive result
    here means anything. Two of this project's most promising-looking results
    (Commodities DSR 0.767, Buyback DSR 0.598) were both rejected on
    adversarial recheck after turning out to be fully explained by a
    confounding factor. A cross-sectional crypto long-short is dollar-neutral
    by construction but NOT market-neutral in practice: a momentum leg in a
    bull market is systematically long the high-beta names and short the low-
    beta ones, so it carries a real crypto-market beta that a naive Sharpe
    would happily report as skill.

    Two factors, both computed from this family's own panel:
      * btc_beta — exposure to BTC itself, the crypto market proxy.
      * basket_beta — exposure to the equal-weighted return of the eligible
        cross-section, which is a different thing from BTC (it is dominated
        by alts, and diverges sharply from BTC in alt-season and in the
        2022 drawdown).
    Both are regressed TOGETHER, so btc_beta is the exposure to BTC over and
    above the basket rather than a duplicate of it.

    The alpha t-statistic uses the plain iid standard error of the residual
    mean. That OVERSTATES significance for an autocorrelated or overlapping
    stream, so it is a generous bound rather than a strict test: an alpha
    insignificant even by this measure is very safely insignificant, which is
    the direction the honest reading needs."""

    pattern_id: str
    sharpe: float
    btc_beta: float
    basket_beta: float
    alpha_annualized: float
    alpha_t_stat: float
    r_squared: float
    # The Sharpe of the book with both FACTOR EXPOSURES sold off and its
    # alpha retained -- what a real hedged book would have earned. If this
    # collapses toward zero while `sharpe` looks good, the result was the
    # market, not the signal. Deliberately NOT the Sharpe of the regression
    # residual, which an intercept forces to ~0 for every spec regardless of
    # alpha -- see compute_crypto_factor_exposure.
    factor_neutralized_sharpe: float


def equal_weight_basket_return(
    close: pd.DataFrame, eligibility: pd.DataFrame | None = None
) -> pd.Series:
    """The equal-weighted daily return of the eligible cross-section — this
    family's own "crypto market" factor, and deliberately NOT the same thing
    as BTC.

    Restricted to eligible names when an eligibility frame is supplied, so
    the factor is the return of a basket that could actually have been held,
    rather than of every zombie quote in the panel."""
    returns = close.pct_change(fill_method=None)
    if eligibility is not None:
        returns = returns.where(eligibility.reindex_like(returns).fillna(False))
    return returns.mean(axis=1, skipna=True)


def compute_crypto_factor_exposure(
    pattern_id: str,
    daily_returns: pd.Series,
    btc_returns: pd.Series,
    basket_returns: pd.Series,
) -> CryptoFactorExposure:
    """Regresses one spec's realized return stream on BTC and on the
    equal-weighted crypto basket TOGETHER, and reports what survives. See
    CryptoFactorExposure for why this is the number that matters."""
    nan = float("nan")
    joined = pd.concat(
        [
            daily_returns.rename("r"),
            btc_returns.rename("btc"),
            basket_returns.rename("basket"),
        ],
        axis=1,
    ).dropna()
    sharpe = sharpe_ratio(daily_returns, periods_per_year=CRYPTO_PERIODS_PER_YEAR)
    if len(joined) < 10:
        return CryptoFactorExposure(pattern_id, sharpe, nan, nan, nan, nan, nan, nan)

    y = joined["r"].to_numpy()
    x = np.column_stack(
        [np.ones(len(joined)), joined["btc"].to_numpy(), joined["basket"].to_numpy()]
    )
    # lstsq, not a normal-equation inverse: BTC and the equal-weighted basket
    # are highly collinear in crypto (the basket is mostly beta to BTC), and
    # a rank-deficient design must degrade to a least-norm solution rather
    # than raise or return garbage.
    coefficients, _residual_sum, rank, _singular = np.linalg.lstsq(x, y, rcond=None)
    if rank < x.shape[1]:
        logger.warning(
            "%s: BTC and the equal-weight basket are rank-deficient over this window (rank %d of "
            "%d) — the two betas below are a least-norm split of one shared exposure and must not "
            "be read as separable.",
            pattern_id,
            rank,
            x.shape[1],
        )

    alpha_daily, btc_beta, basket_beta = (float(c) for c in coefficients)
    # TWO different "what is left" series, and conflating them is a real bug
    # this module's own test pass caught:
    #  * `residual` (intercept INCLUDED in the fit) has mean exactly zero by
    #    construction. It is the right series for the alpha STANDARD ERROR
    #    and for R^2, and the WRONG one to take a Sharpe of -- a mean-zero
    #    series has a ~0 Sharpe no matter how much alpha the fit found, so
    #    reporting that as "factor-neutralized Sharpe" would make every spec
    #    look confounded, including one with genuine orthogonal alpha.
    #  * `hedged` is the return stream of the book with only its FACTOR
    #    exposures sold off -- alpha retained. That is what a real hedged
    #    book would have earned, and it is what factor_neutralized_sharpe
    #    reports.
    residual = pd.Series(y - x @ coefficients, index=joined.index)
    hedged = pd.Series(
        y - btc_beta * joined["btc"].to_numpy() - basket_beta * joined["basket"].to_numpy(),
        index=joined.index,
    )
    residual_std = float(residual.std(ddof=1))
    stream_std = float(joined["r"].std(ddof=1))

    # A stream that IS a factor combination scaled leaves a residual that is
    # zero only to floating-point dust. Dividing that dust by itself yields a
    # large, meaningless Sharpe -- the exact guard cross_sectional_bonds.
    # compute_rate_exposure documents and for the same reason.
    if stream_std > 0.0 and residual_std <= 1e-9 * stream_std:
        return CryptoFactorExposure(
            pattern_id, sharpe, btc_beta, basket_beta, 0.0, 0.0, 1.0, 0.0
        )

    total_ss = float(((y - y.mean()) ** 2).sum())
    r_squared = 1.0 - float((residual.to_numpy() ** 2).sum()) / total_ss if total_ss > 0 else nan
    standard_error = residual_std / np.sqrt(len(residual))
    t_stat = alpha_daily / standard_error if standard_error > 0 else nan
    return CryptoFactorExposure(
        pattern_id=pattern_id,
        sharpe=sharpe,
        btc_beta=btc_beta,
        basket_beta=basket_beta,
        alpha_annualized=alpha_daily * CRYPTO_PERIODS_PER_YEAR,
        alpha_t_stat=t_stat,
        r_squared=r_squared,
        factor_neutralized_sharpe=sharpe_ratio(
            hedged, periods_per_year=CRYPTO_PERIODS_PER_YEAR
        ),
    )


# The DSR above which a result stops being reportable as a plain number and
# must carry its confound check in the same breath. 0.5 is the threshold the
# two rejected results of 2026-08-26 (Commodities 0.767, Buyback 0.598) both
# cleared before being explained away by a factor.
CRYPTO_CONFOUND_CHECK_DSR = 0.5


def _mechanism_of(pattern_id: str) -> str:
    """'xc_momentum_skip7_l180_h90' -> 'momentum_skip_week'. Order matters:
    the skip variant's id also starts with 'xc_momentum'."""
    for prefix, mechanism in (
        ("xc_momentum_skip", "momentum_skip_week"),
        ("xc_momentum_", "momentum"),
        ("xc_reversal_", "long_run_reversal"),
        ("xc_lowvol_", "low_volatility"),
        ("xc_btcbeta_", "betting_against_beta"),
    ):
        if pattern_id.startswith(prefix):
            return mechanism
    return "unknown"


def effective_breadth(daily_returns: pd.DataFrame) -> float:
    """The eigenvalue-based effective number of independent bets in a return
    panel: (sum lambda)^2 / sum(lambda^2) over the correlation matrix's
    spectrum -- n for n uncorrelated series, 1 for n copies of one series.
    Reported so "50 eligible coins" is never silently read as "50 independent
    things"; crypto is famously a single-factor market most days. NaN when
    fewer than 2 columns have usable returns."""
    usable = daily_returns.dropna(how="any")
    if usable.shape[1] < 2 or len(usable) < 3:
        return float("nan")
    corr = usable.corr().to_numpy()
    if not np.all(np.isfinite(corr)):
        return float("nan")
    lam = np.linalg.eigvalsh(corr)
    denom = float((lam**2).sum())
    if denom <= 0.0:
        return float("nan")
    return float(lam.sum() ** 2 / denom)


# --- production entry point -------------------------------------------------


@dataclass
class CryptoScreeningSummary:
    """run_crypto_screening's full result. Every caution this family carries
    is a TYPED FIELD, not a docstring paragraph a caller could skip."""

    results: list[CrossSectionalScreeningResult]
    n_trials: int
    periods_per_year: float
    panel_start: date | None
    panel_end: date | None
    n_panel_rows: int
    n_missing_calendar_days: int
    formation_start: date
    candidate_universe_size: int
    excluded: dict[str, str]
    missing_price_data: list[str]
    # Point-in-time eligibility, measured over the formation window.
    min_eligible: int
    median_eligible: float
    max_eligible: int
    # The dead coins actually exercised by this run: ticker -> (first, last)
    # date it was eligible. The survivorship fix, as a number rather than a
    # claim.
    dead_coins_ranked: dict[str, tuple[date, date]] = field(default_factory=dict)
    effective_breadth: float = float("nan")
    # Correlations between the five mechanisms' own blended return streams.
    mechanism_correlations: dict[tuple[str, str], float] = field(default_factory=dict)
    # The confound check, run for EVERY spec (not only the ones that looked
    # good) so a reader can see the whole distribution.
    factor_exposures: dict[str, CryptoFactorExposure] = field(default_factory=dict)
    text: str = ""
    warnings: list[str] = field(default_factory=list)


def build_crypto_disclosure(
    results: list[CrossSectionalScreeningResult],
    config: CrossSectionalConfig,
    daily_by_pattern: dict[str, pd.Series] | None = None,
) -> str:
    """The cost/assumption disclosure, computed from the run's own numbers --
    same construction and arithmetic as build_commodities_disclosure /
    build_bonds_disclosure (gross = net + charged; breakeven cost_bps =
    cost_bps * gross / charged), restated with this family's assumptions.
    Financing is never folded into the breakeven: it scales with time held,
    not with turnover, so it does not move when cost_bps does."""
    lines = [
        "CRYPTO FAMILY COST DISCLOSURE.",
        (
            f"  Trading: {config.cost_bps} bps one-way per unit of gross notional traded — six "
            "times the harness's 5bp equity default, sized to the ALT coins a quintile leg is "
            "actually made of (taker fee 5-10bp plus tens of bp of spread/impact), not to "
            "BTC/ETH. An assumption, not a measured execution cost."
        ),
        (
            f"  Financing: {config.financing_bps_per_year} bps/yr on gross notional held, "
            f"representing a {CRYPTO_SHORT_BORROW_BPS_PER_YEAR} bps/yr SHORT-LEG spot borrow "
            "assumption (halved because financing accrues on gross 2.0 and half the book is "
            "short). The perpetual-futures alternative would often have PAID this book funding "
            "instead; that credit is deliberately not taken. Short availability is not modelled "
            "at any price."
        ),
        (
            f"  Calendar: periods_per_year={config.periods_per_year:.0f}. Crypto trades 24/7/365 "
            "with no holidays; annualizing this data at 252 would understate every Sharpe here "
            "by ~17% and every annualized return by ~31%."
        ),
        (
            f"  min_names_per_leg={config.min_names_per_leg} (the harness DEFAULT — unlike the "
            "bond/FX/commodity families, this universe is wide enough not to need it lowered)."
        ),
    ]
    positive = [r for r in results if r.sharpe_annualized > 0]
    if not positive:
        lines.append(
            "  Breakeven cost: not applicable — no spec produced a positive Sharpe, so no "
            "positive result depends on the trading-cost assumption."
        )
        return "\n".join(lines)

    lines.append("  Breakeven one-way trading cost for each spec with a positive Sharpe:")
    for r in sorted(positive, key=lambda x: -x.sharpe_annualized):
        charged = r.total_cost_drag
        series = (daily_by_pattern or {}).get(r.pattern_id)
        if charged <= 0 or series is None or series.empty:
            lines.append(
                f"    {r.pattern_id}: Sharpe {r.sharpe_annualized:+.3f}; breakeven not computable "
                "(no turnover cost charged, or no return series available)."
            )
            continue
        net = float(series.sum())
        gross = net + charged
        breakeven_bps = config.cost_bps * gross / charged
        lines.append(
            f"    {r.pattern_id}: Sharpe {r.sharpe_annualized:+.3f}, cumulative net {net:+.2%} "
            f"after {charged:.2%} of trading cost -> breakeven at ~{breakeven_bps:.1f} bps "
            f"one-way ({breakeven_bps / config.cost_bps:.1f}x the assumption)."
        )
    return "\n".join(lines)


def build_confound_report(
    results: list[CrossSectionalScreeningResult],
    exposures: dict[str, CryptoFactorExposure],
) -> str:
    """The adversarial recheck, reported for every spec over the DSR
    threshold AND summarized for the rest. See CryptoFactorExposure."""
    lines = [
        "CONFOUND CHECK — every spec's realized return stream regressed on BTC AND on the",
        "equal-weighted eligible-crypto basket, jointly. A dollar-neutral cross-sectional book",
        "is not market-neutral: a momentum leg is systematically long high-beta names.",
    ]
    flagged = [
        r
        for r in results
        if r.deflated_sharpe.dsr is not None and r.deflated_sharpe.dsr > CRYPTO_CONFOUND_CHECK_DSR
    ]
    if not flagged:
        best = max((r.deflated_sharpe.dsr or 0.0) for r in results) if results else 0.0
        lines.append(
            f"  No spec exceeded the DSR {CRYPTO_CONFOUND_CHECK_DSR} threshold that requires an "
            f"individual writeup (highest DSR in the family: {best:.3f}). Full per-spec exposures "
            "are still reported below, because a negative result that was never checked is not a "
            "negative result."
        )
    for r in sorted(results, key=lambda x: -x.sharpe_annualized):
        e = exposures.get(r.pattern_id)
        if e is None:
            continue
        dsr = r.deflated_sharpe.dsr
        marker = "  !! " if (dsr is not None and dsr > CRYPTO_CONFOUND_CHECK_DSR) else "     "
        lines.append(
            f"{marker}{r.pattern_id}: Sharpe {e.sharpe:+.3f}, DSR "
            f"{'n/a' if dsr is None else f'{dsr:.3f}'} | BTC beta {e.btc_beta:+.3f}, basket beta "
            f"{e.basket_beta:+.3f}, R2 {e.r_squared:.3f} -> alpha {e.alpha_annualized:+.2%}/yr "
            f"(t={e.alpha_t_stat:+.2f}), factor-neutralized Sharpe {e.factor_neutralized_sharpe:+.3f}"
        )
    return "\n".join(lines)


def _build_summary_text(summary: CryptoScreeningSummary) -> str:
    return (
        f"CRYPTO CROSS-SECTIONAL FAMILY — READ BEFORE TRUSTING ANY NUMBER. Pre-declared family "
        f"size {summary.n_trials} definitions ({CRYPTO_N_SIGNAL_DEFINITIONS} signal definitions x "
        f"{len(CRYPTO_HOLDING_DAYS)} holds), fixed before the run and used as the DSR's n_trials "
        f"denominator in this family's own, never-pooled screening call. FIVE DISTINCT "
        f"MECHANISMS: momentum, momentum skipping the last {CRYPTO_MOMENTUM_SKIP_DAYS} days, "
        f"long-run reversal, low realized volatility, and betting-against-BTC-beta. Leg weighting "
        f"is fixed at {CRYPTO_LEG_WEIGHTING} (NOT swept — crypto's volatility dispersion makes an "
        f"equally weighted leg a bet on its most volatile member, so fixing it ex ante halves the "
        f"multiple-comparisons burden). CALENDAR: periods_per_year="
        f"{summary.periods_per_year:.0f}; crypto trades 24/7/365 and this panel has "
        f"{summary.n_missing_calendar_days} missing calendar days across "
        f"{summary.n_panel_rows} rows ({summary.panel_start} .. {summary.panel_end}). Every "
        f"'days' figure in this family is a CALENDAR day, not a trading day. SURVIVORSHIP: the "
        f"{summary.candidate_universe_size}-coin candidate list deliberately INCLUDES coins that "
        f"died or migrated, and {len(summary.dead_coins_ranked)} of them were actually ranked and "
        f"held on their real trading dates ("
        + ", ".join(
            f"{t} {a}..{b}" for t, (a, b) in sorted(summary.dead_coins_ranked.items())
        )
        + f"). yfinance retains these coins' full history — LUNA1-USD is priced all the way down "
        f"through the 2022 Terra collapse — which is why crypto's survivorship bias is fixable "
        f"here and this project's equity families' is not. RESIDUAL BIAS, NOT CLAIMED AWAY: the "
        f"candidate list is hand-assembled in 2026 and omits coins a 2026 author forgot, though "
        f"not (as equities must) coins that failed. ELIGIBILITY is a point-in-time liquidity gate "
        f"(trailing {CRYPTO_LIQUIDITY_WINDOW_DAYS}-day median dollar volume >= "
        f"${CRYPTO_MIN_DOLLAR_VOLUME:,.0f} and trailing stale-print fraction <= "
        f"{CRYPTO_MAX_STALE_FRACTION:.0%}, both shifted so they read only prior rows), NOT a "
        f"fixed basket — coins are born, die, and keep quoting long after anyone trades them "
        f"(EOS's median dollar volume is $349M lifetime against $0.1M over the trailing year). "
        f"Eligible names over the formation window: {summary.min_eligible}..{summary.max_eligible}, "
        f"median {summary.median_eligible:.0f}, giving disjoint quintile legs that never breach "
        f"the harness's default min_names_per_leg of {CRYPTO_MIN_NAMES_PER_LEG}. HONEST BREADTH: "
        f"the panel's effective number of independent bets is {summary.effective_breadth:.2f} — "
        f"crypto is close to a one-factor market and no Sharpe here should be read as coming from "
        f"a diversified portfolio of that many nominal names. FORMATIONS begin "
        f"{summary.formation_start} (three years after the data does, so the 730-day lookback "
        f"warms entirely out of pre-test data and all {summary.n_trials} specs form over the "
        f"identical range); at a 180-day hold that window holds only ~11 INDEPENDENT "
        f"non-overlapping formations, and overlapping cohorts are deliberately not used to "
        f"disguise that. Costs: {CRYPTO_COST_BPS}bp one-way per unit of gross notional TRADED "
        f"plus {CRYPTO_FINANCING_BPS_PER_YEAR}bps/yr per unit HELD (an "
        f"{CRYPTO_SHORT_BORROW_BPS_PER_YEAR}bps/yr short-leg borrow assumption), and the "
        f"perpetual-futures funding CREDIT a short book would often have earned instead is "
        f"deliberately NOT taken."
    )


def run_crypto_screening(
    end: date | None = None,
    start: date | None = None,
    provider: YFinanceProvider | None = None,
    config: CrossSectionalConfig | None = None,
) -> CryptoScreeningSummary:
    """THE production entry point for the Crypto family, scoped to exactly
    the 28 pre-declared definitions and their own n_trials.

    `start` is the earliest FORMATION date (config.formation_start), not the
    earliest data date: price history is always fetched from
    CRYPTO_PRICE_HISTORY_START so the 730-day lookback is warmed out of
    pre-test data. Left None it defaults to CRYPTO_FORMATION_START
    (2020-11-01) — which, unlike the FX and commodity families' None, is a
    deliberate non-trivial default rather than "as soon as the lookback
    allows", because this family's start date is a composition-honesty
    decision and not a data-availability one (see the module docstring).

    A caller-supplied config is used exactly as given and never silently
    patched, except formation_start — the same contract screen_fx_family and
    run_commodities_screening keep."""
    end = end if end is not None else date.today()  # noqa: DTZ011 — fetch end bound only
    provider = provider if provider is not None else YFinanceProvider()
    if config is None:
        config = default_crypto_config()
    config.formation_start = start if start is not None else CRYPTO_FORMATION_START
    formation_start = config.formation_start

    warnings: list[str] = []
    candidate = [t for t in CRYPTO_UNIVERSE if t not in CRYPTO_EXCLUDED]

    close, volume, missing = build_crypto_price_panel(provider, end)
    if close.empty:
        summary = CryptoScreeningSummary(
            results=[],
            n_trials=CRYPTO_N_TRIALS,
            periods_per_year=config.periods_per_year,
            panel_start=None,
            panel_end=None,
            n_panel_rows=0,
            n_missing_calendar_days=0,
            formation_start=formation_start,
            candidate_universe_size=len(candidate),
            excluded=dict(CRYPTO_EXCLUDED),
            missing_price_data=missing,
            min_eligible=0,
            median_eligible=0.0,
            max_eligible=0,
            warnings=["No crypto price data resolved — nothing was screened."],
        )
        summary.text = _build_summary_text(summary)
        return summary

    if missing:
        warnings.append(
            f"{len(missing)} of {len(candidate)} candidate tickers resolved no price data "
            f"({missing}); the cross-section screened is smaller than the declared candidate list."
        )

    # The 24/7/365 check, measured rather than assumed on every run: a crypto
    # panel that suddenly develops calendar gaps is a data-quality event, and
    # it is also the assumption periods_per_year=365 rests on.
    expected_days = pd.date_range(close.index[0], close.index[-1], freq="D")
    n_missing_calendar_days = len(expected_days.difference(close.index))
    if n_missing_calendar_days:
        warnings.append(
            f"{n_missing_calendar_days} calendar day(s) are missing from a panel that should "
            f"trade 24/7/365 — periods_per_year={config.periods_per_year:.0f} assumes they are "
            "not. Investigate before trusting any annualized number in this run."
        )
        logger.warning(
            "Crypto panel has %d missing calendar days between %s and %s.",
            n_missing_calendar_days,
            close.index[0].date(),
            close.index[-1].date(),
        )

    eligibility = build_eligibility(close, volume)
    membership_fn = liquidity_membership(eligibility)

    in_window = eligibility.loc[eligibility.index >= pd.Timestamp(formation_start)]
    counts = in_window.sum(axis=1)
    dead_coins_ranked: dict[str, tuple[date, date]] = {}
    last_priced_row = close.index[-1]
    for ticker in eligibility.columns:
        priced = close[ticker].dropna()
        if priced.empty or priced.index[-1] == last_priced_row:
            continue  # still alive at the end of the panel
        flags = in_window[ticker]
        on = flags[flags]
        if len(on):
            dead_coins_ranked[ticker] = (on.index[0].date(), on.index[-1].date())

    basis = build_inverse_vol_basis(close)
    data = CrossSectionalData(close=close, leg_weight_basis=basis)

    specs = build_crypto_family()
    results = screen_cross_sectional_universe(data, specs, config, membership_fn)

    # A second, clearly-labelled replay pass purely for diagnostics — the
    # screening call returns aggregates, and the breakeven arithmetic, the
    # mechanism correlations and the confound check all need each spec's own
    # daily series. The exact trade-off run_bonds_screening and
    # run_commodities_screening document.
    daily_by_pattern: dict[str, pd.Series] = {}
    spec_by_id = {s.pattern_id: s for s in specs}
    for r in results:
        replay = run_cross_sectional_backtest(data, spec_by_id[r.pattern_id], config, membership_fn)
        if replay.status == "ok":
            daily_by_pattern[r.pattern_id] = replay.daily_returns

    btc_returns = close[CRYPTO_MARKET_TICKER].pct_change(fill_method=None)
    basket_returns = equal_weight_basket_return(close, eligibility)
    exposures = {
        pattern_id: compute_crypto_factor_exposure(
            pattern_id,
            series,
            btc_returns.reindex(series.index),
            basket_returns.reindex(series.index),
        )
        for pattern_id, series in daily_by_pattern.items()
    }

    by_mechanism: dict[str, list[pd.Series]] = {}
    for pattern_id, series in daily_by_pattern.items():
        by_mechanism.setdefault(_mechanism_of(pattern_id), []).append(series)
    blended = {
        mechanism: pd.concat(streams, axis=1).mean(axis=1)
        for mechanism, streams in sorted(by_mechanism.items())
    }
    mechanism_correlations: dict[tuple[str, str], float] = {}
    names = sorted(blended)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            joined = pd.concat([blended[a], blended[b]], axis=1).dropna()
            if len(joined) >= 2:
                mechanism_correlations[(a, b)] = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))

    summary = CryptoScreeningSummary(
        results=results,
        n_trials=CRYPTO_N_TRIALS,
        periods_per_year=config.periods_per_year,
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        n_panel_rows=len(close),
        n_missing_calendar_days=n_missing_calendar_days,
        formation_start=formation_start,
        candidate_universe_size=len(candidate),
        excluded=dict(CRYPTO_EXCLUDED),
        missing_price_data=missing,
        min_eligible=int(counts.min()) if len(counts) else 0,
        median_eligible=float(counts.median()) if len(counts) else 0.0,
        max_eligible=int(counts.max()) if len(counts) else 0,
        dead_coins_ranked=dead_coins_ranked,
        effective_breadth=effective_breadth(close.pct_change(fill_method=None)),
        mechanism_correlations=mechanism_correlations,
        factor_exposures=exposures,
        warnings=warnings,
    )
    summary.text = (
        _build_summary_text(summary)
        + "\n"
        + build_crypto_disclosure(results, config, daily_by_pattern)
        + "\n"
        + build_confound_report(results, exposures)
    )
    return summary


__all__ = [
    "CRYPTO_BETA_LOOKBACK_DAYS",
    "CRYPTO_CONFOUND_CHECK_DSR",
    "CRYPTO_COST_BPS",
    "CRYPTO_EXCLUDED",
    "CRYPTO_FINANCING_BPS_PER_YEAR",
    "CRYPTO_FORMATION_START",
    "CRYPTO_HOLDING_DAYS",
    "CRYPTO_LEG_WEIGHTING",
    "CRYPTO_LIQUIDITY_WINDOW_DAYS",
    "CRYPTO_LOOKBACK_DAYS",
    "CRYPTO_LOWVOL_LOOKBACK_DAYS",
    "CRYPTO_MARKET_TICKER",
    "CRYPTO_MAX_STALE_FRACTION",
    "CRYPTO_MIN_DOLLAR_VOLUME",
    "CRYPTO_MIN_NAMES_PER_LEG",
    "CRYPTO_MOMENTUM_LOOKBACK_DAYS",
    "CRYPTO_MOMENTUM_SKIP_DAYS",
    "CRYPTO_N_SIGNAL_DEFINITIONS",
    "CRYPTO_N_TRIALS",
    "CRYPTO_PERIODS_PER_YEAR",
    "CRYPTO_PRICE_HISTORY_START",
    "CRYPTO_RANK_FRACTION",
    "CRYPTO_REVERSAL_LOOKBACK_DAYS",
    "CRYPTO_SHORT_BORROW_BPS_PER_YEAR",
    "CRYPTO_SKIP_LOOKBACK_DAYS",
    "CRYPTO_UNIVERSE",
    "CryptoFactorExposure",
    "CryptoScreeningSummary",
    "build_confound_report",
    "build_crypto_disclosure",
    "build_crypto_family",
    "build_crypto_price_panel",
    "build_dollar_volume",
    "build_eligibility",
    "build_inverse_vol_basis",
    "compute_crypto_factor_exposure",
    "default_crypto_config",
    "effective_breadth",
    "equal_weight_basket_return",
    "liquidity_membership",
    "run_crypto_screening",
    "signal_crypto_btc_beta",
    "signal_crypto_long_run_reversal",
    "signal_crypto_low_volatility",
    "signal_crypto_momentum",
    "signal_crypto_momentum_skip_week",
]
