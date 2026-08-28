"""The crypto perpetual-futures FUNDING-RATE CARRY family: 12 pre-declared
cross-sectional definitions on Binance USDT-margined perpetual futures,
screened as one family with its own never-pooled DSR n_trials denominator.

THE MECHANISM, VERIFIED — NOT ASSUMED — 2026-08-29. A perpetual futures
contract has no expiry, so the exchange levies a periodic funding payment
between the contract's longs and shorts to keep the perp price anchored
near spot: when the funding rate is positive, LONGS PAY SHORTS; negative,
shorts pay longs. This is a structural cash transfer, not a statistical
pattern. Verified this session from two independent sources read directly:
  * Christin, Routledge, Soska & Zetlin-Jones, "The Crypto Carry Trade"
    (working paper, v1.2, Carnegie Mellon; full PDF read this session):
    each settlement "is a transfer of r_t,c * F_t from the long to the
    short side of the contract"; "transfers are made every eight hours";
    on Binance "the funding rate is set at 0.01% per eight-hour period
    plus an adjustment" and the observed median funding rate IS that
    0.01%-per-period default. Their carry trade (short perp + long spot,
    delta-neutral, single-name) earns a full-sample Sharpe of 8.76/yr for
    the Tether-margined BTC contract against 0.46 for buy-and-hold BTC
    and 0.33 for US equities over the same sample (through 2023-06-23) —
    and, their own honest caveat, "the Sharpe ratios are much smaller in
    the later part of the sample" and an FTX-style exchange bankruptcy
    can offset years of harvested funding.
  * Schmeling, Schrimpf & Todorov, "Crypto Carry", BIS Working Papers
    No 1087 (April 2023, revised October 2025; full PDF read this
    session): the sibling phenomenon in FIXED-maturity futures — average
    annualized carry across exchanges ~7% p.a. over April 2019 - July
    2024, occasionally exceeding 40% p.a. — driven by leverage demand
    from smaller trend-chasing investors against limited arbitrage
    capital. Their key risk finding transfers directly to any funding
    harvester: carry predicts LIQUIDATIONS of the short futures leg (a
    10% rise in standardized carry predicts liquidations of 22% of open
    interest within a month), so the "carry" is compensation for a
    crash-and-margin-spiral risk, not free money. They also document the
    spot-ETF introduction compressing carry by ~3pp across exchanges
    (~36% of its mean) — a structural break AGAINST this strategy in the
    recent sample, stated up front rather than discovered in the residual.
    (He, Manela, Ross & von Wachter 2022, "Fundamentals of Perpetual
    Futures", is cited by both papers for the same mechanism; that one is
    cited here VIA the BIS paper — it was not itself read this session.)

WHAT THIS FAMILY ACTUALLY TESTS. The papers above study single-name,
delta-neutral carry (short perp vs long spot). This family tests the
CROSS-SECTIONAL version, in this project's established harness shape:
rank the perp universe by trailing realized funding, go SHORT the
highest-funding names (collecting their funding) and LONG the
lowest-funding names (collecting when their funding is negative, paying
the least when it is not), equal-weighted legs, dollar-neutral in perp
notional. That is a genuinely different (and riskier) construction than
the papers' hedged trade — it is exposed to the funding SPREAD's price
risk rather than hedged to spot — and this docstring says so rather than
borrowing the papers' Sharpe as if it applied.

================================================================================
THE SINGLE MOST IMPORTANT CORRECTNESS DETAIL: THE FUNDING PAYMENT IS P&L
================================================================================
A funding-carry return is NOT price appreciation minus costs. The harvested
payment itself is realized P&L: a LONG perp position's one-day return is
    r_net = r_price - f_day
and a SHORT position's is -(r_price - f_day), where f_day is the SUM of the
funding rates that actually settled that UTC day (positive f_day: the long
paid it, the short collected it). Every daily return this family reports is
built from r_net, so the short leg of a high-funding name EARNS its funding
and the long leg of a negative-funding name EARNS the negated funding. A
dedicated test (tests/test_cross_sectional_funding_carry.py) pins this with
a hand-computed example on constant prices, where the entire return IS the
funding payment.

SUMMED SETTLEMENTS, NEVER rate*3/day: Binance's funding interval is NOT
uniformly 8 hours — /fapi/v1/fundingInfo (fetched live 2026-08-29) lists
441 symbols on a 4h interval, 324 on 8h, 2 on 1h, and intervals have
changed over symbols' lifetimes. f_day sums the settlements that actually
occurred, which is correct under any mixture of intervals.

BOUNDARY CONVENTION, disclosed: a settlement stamped exactly 00:00 UTC of
day D is bucketed into day D. A book formed "at the close" of day t (which
IS 00:00 UTC of t+1) therefore includes the 00:00-of-(t+1) settlement in
its first held day and excludes the 00:00 settlement after its last held
day — symmetric at entry and exit, ambiguous only for a position executed
at the exact settlement microsecond, and worth at most one interval's
median 0.01% per reformation. Disclosed rather than modeled.

================================================================================
DATA — EVERY ENDPOINT FACT VERIFIED LIVE 2026-08-29 (see the provider)
================================================================================
Single source: Binance USDT-margined perpetuals via
app.services.market_data.binance_futures_provider.BinanceFuturesProvider —
funding history (/fapi/v1/fundingRate, keyless, BTCUSDT back to 2019-09-10
08:00 UTC) and daily perp klines (/fapi/v1/klines, BTCUSDT back to
2019-09-08). Returns are computed on the PERP's own close and the PERP's
own funding — internally consistent: the book holds perps, so no
spot-vs-perp basis leaks into the return construction.

SURVIVORSHIP: THE GOOD NEWS, MEASURED. Binance serves full funding and
kline history for DELISTED perps that no longer appear in exchangeInfo at
all — verified live on SRMUSDT and LUNAUSDT, whose final funding rows show
rates pinned at -0.75%/-1.0% per 8h through the May-2022 Terra collapse.
So dead contracts are IN this family's panel on their real dates. The
residual bias is the same one the sibling crypto family discloses: the
candidate list below is that family's hand-assembled 2026 list (reused
deliberately — see UNIVERSE), which omits coins a 2026 author forgot,
though not coins that failed.

SINGLE-VENUE DEPENDENCY, disclosed as a first-class limitation: every
funding rate here is Binance's. Binance is the largest perp venue, but a
one-venue funding panel measures one venue's crowding, caps (+/-2% per
period per fundingInfo), and clamp conventions. cross_venue_funding_check()
runs a deliberately light-touch reasonableness check of daily-summed
funding against Gate.io and KuCoin's keyless public endpoints (both
verified live 2026-08-29) for a couple of majors — a sanity check, not a
cross-venue study, and the summary reports its numbers honestly.

UNIVERSE. Reused from cross_sectional_crypto.CRYPTO_UNIVERSE (the sibling
family already solved candidate-list assembly, including dead coins), each
ticker mapped BTC-USD -> BTCUSDT with two explicit exceptions (LUNA1-USD ->
LUNAUSDT, UNI7083-USD -> UNIUSDT). Coins with no Binance USDT perp resolve
no data and are reported in `symbols_missing`, not silently dropped. The
sibling family's exclusions are kept as-is for universe-identity
consistency even where the reason was a yfinance feed defect that Binance
does not share (SHIB/APE/COMP/GRT) — a coarser rule than re-vetting each
name against the Binance feed, chosen ex ante and disclosed, erring toward
a smaller universe rather than a re-derived one.

ELIGIBILITY is a point-in-time liquidity gate in the sibling family's
register: trailing 30-day median PERP dollar turnover (klines
quote-volume, already USDT) >= $10M, computed strictly from prior rows
(.shift(1)), AND a finite perp close on the formation date. Zero-turnover
zombie bars (delisted perps' trailing prints) are treated as no-market and
NaN'd out of the close panel. Signals additionally refuse any name whose
funding window is under 80% populated.

================================================================================
COSTS AND WHAT IS DELIBERATELY NOT MODELED
================================================================================
FUNDING_CARRY_COST_BPS = 10bp one-way per unit of gross notional traded —
an assumption, not a measured execution cost, sized to liquid USDT perps
(taker fee ~2-5bp tiers plus spread/impact on alt perps), deliberately
BELOW the sibling spot family's 30bp (perp books on Binance are where alt
liquidity actually lives) and double the harness's 5bp equity default.
Every positive spec reports its breakeven one-way cost so a reader sees
exactly how much leans on this number. financing_bps_per_year = 0: a perp
short needs no securities borrow — that is the point of the instrument —
and margin collateral opportunity cost is not charged. NOT MODELED, stated
plainly: exchange-bankruptcy risk (the Christin et al. FTX caveat),
liquidation/margin-spiral risk (the BIS liquidation-prediction channel),
funding-rate caps binding in a crisis, and USDT depeg risk. A live
deployment would carry all four.

HOLDING FLOOR: none — deliberately unlike the sibling family's 90-day
floor. Funding is a fast-mean-reverting payment stream (Christin et al.
document its serial correlation at the 8-hour horizon); a 90-day hold of a
7-day funding rank would test a decayed signal. The price of that choice
is turnover at 10bp charged honestly every 7 or 30 days.

================================================================================
FAMILY SIZE — 12, COMPUTED FROM THE AXES AND FIXED BEFORE ANY RUN
================================================================================
One mechanism (trailing realized funding), three pre-declared axes:
  * funding averaging window W in {7, 14, 30} calendar days       (3)
  * holding/rebalance horizon H in {7, 30} calendar days          (2)
  * rank cutoff in {decile 0.1, quintile 0.2}                     (2)
                                              3 x 2 x 2 = 12 specs
n_trials for the DSR is 12 — the pre-declared enumeration, asserted
against the built list, never shrunk to survivors. Leg weighting is FIXED
at "equal" and is NOT an axis: funding accrues per unit of notional, so
the harvested payment per dollar of a leg is exactly the members' mean
funding rate under equal weighting — the quantity this family ranks on —
whereas inverse-vol weighting would tilt the book toward low-vol majors
whose funding pins at the default and dilute the mechanism being tested.
Both legs are ranked (portfolio long_short); signal = MINUS the trailing
mean daily funding, so the harness convention "higher signal = long leg"
puts the most NEGATIVE funding (shorts pay longs — the long leg collects)
on the long side and the most positive on the short side.

CALENDAR: crypto trades 24/7/365; periods_per_year = 365 throughout
(sharpe_ratio, compute_deflated_sharpe), per the sibling family's verified
365-day-year section. Every "days" figure here is a calendar day.

Attribution is reported per spec (total_funding_pnl vs total_price_pnl):
a carry family whose P&L turns out to be mostly PRICE movement did not
harvest carry, whatever its Sharpe says, and the summary text says which
one happened.

================================================================================
INDEPENDENT VERIFICATION 2026-08-29 — READ THIS BEFORE THE HEADLINE NUMBERS
================================================================================
An adversarial re-derivation of this family's entire result was run the
same day it was built (separate pass, separate code, hand-computed
expectations). What survived, what did not, and the corrected verdict:

WHAT SURVIVED (all re-derived, not trusted):
  * REPRODUCTION: all 12 Sharpe/DSR figures reproduce exactly from the
    cached panel. The cache itself was spot-verified against the live
    Binance API (LUNAUSDT's May-2022 collapse rows match tick-for-tick).
  * NO LOOK-AHEAD: signals recomputed by hand from the raw funding CSVs
    for real formation dates match bit-for-bit, and the first settlement
    after the formation close is confirmed excluded.
  * ATTRIBUTION CORRECTNESS: an independent hand-computed example with
    moving prices, funding, and costs matches every daily return and
    every price/funding/cost component to 1e-12.
  * SURVIVORSHIP DOES NOT MANUFACTURE THE POSITIVE — the dead coins were
    a net DRAG. Per-ticker attribution: the 14 dead names contributed
    -28.85% gross to xf_carry_w30_h7_f10's +236.81% (LUNAUSDT alone
    -41.98%: the book held LUNA LONG through the Terra collapse, because
    collapse funding pins deeply negative, and ate the crash). Excluding
    only the true blowups (LUNA/FTT/SRM) IMPROVES the headline spec to
    +0.872; excluding all 14 dead names leaves 12/12 specs positive
    (best xf_carry_w14_h7_f20 +0.877, DSR 0.828, family median +0.42).
  * COSTS: Binance USDT-M VIP0 fees are 2bp maker / 5bp taker (2026
    schedule, verified), so 10bp one-way = taker + ~5bp spread/impact —
    a plausible mid-estimate for names behind the $10M/day gate. At 20bp
    the family median is +0.31 (10/12 positive), at 30bp +0.20 (9/12);
    it dies around 50bp (median -0.08). Robust to 2-3x costs, not 5x.
  * Both citations verified verbatim against the papers themselves.
  * Cross-venue rows reproduce exactly. Note what they actually say:
    trailing-month mean daily funding on Binance ran 8-61% RICHER than
    Gate.io/KuCoin (corr only 0.42-0.70) — the single-venue dependency
    is real, not a formality. Bybit/OKX re-tested: still DNS-unreachable.

WHAT DID NOT SURVIVE — THE CORRECTED HEADLINE:
  * THE BEST SPEC CANNOT TRADE TODAY. xf_carry_w30_h7_f10 (+0.812, DSR
    0.761) has been 100% in cash since 2025-03: a decile leg of 5 needs
    >=50 eligible names and the eligible count has decayed 66 -> 27
    (yearly means: 2021 59.6, 2022 63.0, 2023 59.0, 2024 53.5, 2025
    44.3, 2026 31.4). Its full-sample Sharpe therefore contains ~18
    months of structural zeros, and ALL four f10 specs are untradeable
    at today's breadth. The decay is baked into the design: the universe
    is a static 2026 hand-assembled list — dead names leave, new
    listings never arrive — so recent breadth (and recent P&L weight)
    shrinks mechanically while the fat 2021-2022 cross-section dominates
    the full-sample number.
  * THE EDGE IS DECAYING, EXACTLY AS BOTH CITED PAPERS WARN. Ex-2021,
    the headline spec is +0.405 (not +0.812) and the family median is
    +0.30. 2026 YTD every spec that could still form a book lost -34%
    to -47% (annualized Sharpe -1.7 to -2.0) — the worst stretch in the
    whole sample, consistent with the BIS finding that the spot-ETF era
    compressed carry by ~36% of its mean and with Christin et al.'s
    "much smaller in the later part of the sample". 2025 was positive
    for all six f20 specs (+4.8% to +63.6%, four above +43%), so the
    recent signal is violent in both directions, not merely dead.
  * SPEC-LEVEL RANKING IS NOISE. Removing the 14 dead names flips the
    best spec from w30_h7_f10 (+0.812 -> +0.146) to w14_h7_f20 (+0.474
    -> +0.877) — the family-level positive is robust, but any claim
    about WHICH definition is best does not survive perturbation.

CORRECTED VERDICT: a real historical cross-sectional funding premium —
genuinely positive in-sample, survivorship-clean, cost-robust at 2-3x,
correctly computed — but NOT a validated deployable edge. The headline
number is dominated by the 2021 leverage era on a universe breadth that
no longer exists; the recent tradeable record is deeply negative; and
even at face value DSR 0.761 never cleared this project's significance
bar (results with better DSRs have been rejected). NO forward-validation
registration was made, deliberately: the backward-best spec cannot form
a book, choosing a different spec now would be fresh post-hoc selection
on exhausted backward data (the exact move bab_forward_registration.py
documents as illegitimate), and a forward tick on a mechanically
shrinking static universe would measure the universe's decay, not the
signal. The legitimate next step, if this mechanism is pursued: rebuild
the universe POINT-IN-TIME from Binance's own listing history (the API
serves every symbol's full life, including delisted ones — verified), so
breadth is real at every formation date, then re-screen as a NEW
pre-declared family. Corrected numbers persisted alongside the originals
under run_tags funding_carry_verified_* (see
cross_sectional_trial_results).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import httpx
import numpy as np
import pandas as pd

from app.services.market_data.binance_futures_provider import BinanceFuturesProvider
from app.services.research_lab.cross_sectional import (
    MIN_REPLAY_TRADING_DAYS,
    _turnover,
    realize_formation_day,
    select_leg_tickers,
)
from app.services.research_lab.cross_sectional_crypto import (
    CRYPTO_UNIVERSE,
    CryptoFactorExposure,
    compute_crypto_factor_exposure,
)
from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.metrics import CALENDAR_DAYS_PER_YEAR, sharpe_ratio

logger = logging.getLogger(__name__)

# --- calendar ----------------------------------------------------------------

FUNDING_CARRY_PERIODS_PER_YEAR = float(CALENDAR_DAYS_PER_YEAR)

# --- universe ----------------------------------------------------------------

# yfinance ticker -> Binance USDT-perp symbol, where the plain
# strip-"-USD"-append-"USDT" rule is wrong.
BINANCE_SYMBOL_EXCEPTIONS: dict[str, str] = {
    "LUNA1-USD": "LUNAUSDT",  # Terra's original LUNA (perp delisted 2022; history verified served)
    "UNI7083-USD": "UNIUSDT",  # Uniswap (the sibling family's yfinance disambiguation suffix)
}


def binance_symbol_for(yf_ticker: str) -> str:
    """Maps the sibling crypto family's yfinance ticker to its Binance
    USDT-margined perpetual symbol."""
    if yf_ticker in BINANCE_SYMBOL_EXCEPTIONS:
        return BINANCE_SYMBOL_EXCEPTIONS[yf_ticker]
    return yf_ticker.replace("-USD", "") + "USDT"


# The candidate universe: the sibling family's hand-assembled list (dead
# coins included), mapped to Binance perp symbols. See the UNIVERSE section
# of the module docstring for what is reused, what is disclosed, and why
# names with no Binance perp are reported rather than silently dropped.
FUNDING_CARRY_UNIVERSE: dict[str, str] = {t: binance_symbol_for(t) for t in CRYPTO_UNIVERSE}

# Fetch start: safely before the first Binance USDT perp (BTCUSDT,
# 2019-09) so "all available history" is what a fetch actually gets.
FUNDING_CARRY_DATA_START = date(2019, 9, 1)

# First formation. By late 2020 Binance's USDT-perp roster covered most of
# the candidate list (the 2020 listing waves); earlier, the cross-section
# is a handful of majors and a decile leg cannot exist. Formations before
# this date would rank a universe too thin to mean anything; the summary
# reports measured eligible counts so the reader can see the real breadth
# rather than trust this paragraph.
FUNDING_CARRY_FORMATION_START = date(2020, 10, 1)

# --- point-in-time eligibility ----------------------------------------------

# Trailing PERP dollar-turnover gate, same register as the sibling
# family's spot gate but on the perp's own quote-volume (already USDT).
FUNDING_LIQUIDITY_WINDOW_DAYS = 30
FUNDING_LIQUIDITY_MIN_PERIODS = 20
FUNDING_MIN_QUOTE_VOLUME = 10_000_000.0

# A funding-averaging window under 80% populated is refused (NaN signal)
# — the sibling families' shared coverage-floor register.
MIN_SIGNAL_OBS_FRACTION = 0.8

# --- the pre-declared axes ---------------------------------------------------

FUNDING_AVG_WINDOWS_DAYS: tuple[int, ...] = (7, 14, 30)
FUNDING_HOLDING_DAYS: tuple[int, ...] = (7, 30)
FUNDING_RANK_FRACTIONS: tuple[float, ...] = (0.1, 0.2)

# 3 windows x 2 holds x 2 cutoffs = 12. Computed from the axes so the two
# can never disagree; build_funding_carry_family asserts the built list
# matches. THE DSR denominator for this family, never pooled elsewhere.
FUNDING_CARRY_N_TRIALS = (
    len(FUNDING_AVG_WINDOWS_DAYS) * len(FUNDING_HOLDING_DAYS) * len(FUNDING_RANK_FRACTIONS)
)

FUNDING_CARRY_COST_BPS = 10.0
FUNDING_CARRY_MIN_NAMES_PER_LEG = 5

FUNDING_CARRY_CITATION = (
    "Christin, Routledge, Soska & Zetlin-Jones, 'The Crypto Carry Trade' (working paper, "
    "Carnegie Mellon, v1.2, read 2026-08-29) — short-perp funding harvesting, BTC carry Sharpe "
    "8.76/yr through 2023-06-23 with the authors' own caveat that later-sample Sharpes are much "
    "smaller; Schmeling, Schrimpf & Todorov, 'Crypto Carry' (BIS Working Papers No 1087, 2023 "
    "rev. 2025, read 2026-08-29) — ~7%/yr average fixed-maturity crypto carry 2019-2024, and "
    "carry as a predictor of short-leg liquidations (the risk this premium pays for)"
)

FUNDING_CARRY_FAMILY_KEY = "funding_carry"


# --- dataclasses -------------------------------------------------------------


@dataclass(frozen=True)
class FundingCarrySpec:
    """One pre-declared definition: rank by trailing avg_window_days mean
    daily funding (signal is the NEGATED mean, so higher = long), reform
    every holding_days calendar days, legs of rank_fraction each side,
    equal-weighted."""

    pattern_id: str
    avg_window_days: int
    holding_days: int
    rank_fraction: float
    family: str = FUNDING_CARRY_FAMILY_KEY
    citation: str = FUNDING_CARRY_CITATION


@dataclass
class FundingCarryConfig:
    cost_bps: float = FUNDING_CARRY_COST_BPS
    min_names_per_leg: int = FUNDING_CARRY_MIN_NAMES_PER_LEG
    periods_per_year: float = FUNDING_CARRY_PERIODS_PER_YEAR
    formation_start: date = FUNDING_CARRY_FORMATION_START


@dataclass
class FundingCoverage:
    """One symbol's real, measured data coverage — the honest-disclosure
    unit the summary aggregates."""

    symbol: str
    first_funding: date | None
    last_funding: date | None
    n_funding_events: int
    n_kline_days: int
    # Largest gap (days) between consecutive funding settlements while the
    # symbol was alive — a data-quality tripwire: >2 days means missed
    # settlements this family would silently have treated as zero funding.
    max_funding_gap_days: float


@dataclass
class FundingCarryPanels:
    """The aligned panels every spec is replayed against.

    funding_daily holds, per (day, symbol), the SUM of funding rates that
    settled that UTC day: 0.0 on a day the perp traded but no settlement
    landed (never happens on a healthy feed), NaN where the perp had no
    market (pre-listing, post-delisting, zero-turnover zombie bars)."""

    close: pd.DataFrame
    quote_volume: pd.DataFrame
    funding_daily: pd.DataFrame
    coverage: dict[str, FundingCoverage]
    symbols_missing: list[str]


@dataclass
class FormationRecordLite:
    formation_date: date
    long_tickers: list[str]
    short_tickers: list[str]
    turnover: float
    skipped_reason: str | None

    @property
    def n_long(self) -> int:
        return len(self.long_tickers)

    @property
    def n_short(self) -> int:
        return len(self.short_tickers)


@dataclass
class FundingCarryBacktest:
    daily_returns: pd.Series  # net of turnover cost
    formations: list[FormationRecordLite]
    total_cost_drag: float
    total_turnover: float
    total_funding_pnl: float  # sum of daily funding components (gross)
    total_price_pnl: float  # sum of daily price components (gross)


@dataclass
class FundingCarrySpecResult:
    """Per-spec screening output. Carries exactly the fields
    persist_cross_sectional_trial_results requires (pattern_id,
    sharpe_annualized, n_trading_days, deflated_sharpe) plus this
    family's own attribution and honesty counters."""

    pattern_id: str
    family: str
    citation: str
    n_formations: int
    n_skipped_formations: int
    avg_names_per_leg: float
    n_trading_days: int
    sharpe_annualized: float
    total_cost_drag: float
    total_turnover: float
    total_funding_pnl: float
    total_price_pnl: float
    deflated_sharpe: DeflatedSharpeResult


@dataclass
class CrossVenueCheckRow:
    """One (venue, symbol) light-touch comparison of DAILY-SUMMED funding
    (interval-agnostic — see cross_venue_funding_check)."""

    venue: str
    binance_symbol: str
    venue_symbol: str
    n_days_compared: int
    daily_sum_correlation: float
    mean_daily_binance: float
    mean_daily_venue: float
    note: str = ""


@dataclass
class FundingCarryScreeningSummary:
    results: list[FundingCarrySpecResult]
    n_trials: int
    periods_per_year: float
    panel_start: date | None
    panel_end: date | None
    n_panel_rows: int
    n_missing_calendar_days: int
    formation_start: date
    candidate_universe_size: int
    symbols_missing: list[str]
    coverage: dict[str, FundingCoverage]
    min_eligible: int
    median_eligible: float
    max_eligible: int
    dead_symbols_ranked: dict[str, tuple[date, date]] = field(default_factory=dict)
    factor_exposures: dict[str, CryptoFactorExposure] = field(default_factory=dict)
    cross_venue: list[CrossVenueCheckRow] = field(default_factory=list)
    text: str = ""
    warnings: list[str] = field(default_factory=list)


# --- panels ------------------------------------------------------------------


def aggregate_funding_daily(events: pd.DataFrame) -> pd.Series:
    """Sum of funding rates per UTC calendar day from a provider funding
    frame (index: settlement timestamps; column funding_rate). A
    settlement stamped exactly 00:00 UTC of day D belongs to day D — the
    boundary convention the module docstring discloses. Timestamp jitter
    of a few ms (observed live: fundingTime ...0013) lands in the same
    day and needs no special-casing."""
    if events.empty:
        return pd.Series(dtype=float)
    return events["funding_rate"].groupby(events.index.normalize()).sum()


def build_funding_carry_panels(
    provider: BinanceFuturesProvider,
    end: date,
    start: date = FUNDING_CARRY_DATA_START,
) -> FundingCarryPanels:
    """Fetches (or reads from the provider's disk cache) klines and
    funding for every candidate symbol and aligns them on one ragged
    calendar-day index. Ragged on purpose, exactly as the sibling
    family's panel builder documents: a symbol is NaN before listing and
    after delisting, and truncating the panel to all-names-priced would
    delete the recent years for everyone (the survivorship fix undone by
    a data-shaping convenience).

    Market-or-not: a close is kept only where the bar's quote turnover is
    strictly positive — a zero-turnover bar (delisted perps keep printing
    one) is a quote, not a market."""
    closes: dict[str, pd.Series] = {}
    volumes: dict[str, pd.Series] = {}
    funding_by_symbol: dict[str, pd.Series] = {}
    coverage: dict[str, FundingCoverage] = {}
    missing: list[str] = []

    for _yf_ticker, symbol in sorted(FUNDING_CARRY_UNIVERSE.items(), key=lambda kv: kv[1]):
        klines = provider.get_daily_klines(symbol, start, end)
        funding = provider.get_funding_history(symbol, start, end)
        if klines.empty and funding.empty:
            missing.append(symbol)
            continue

        close = pd.to_numeric(klines["close"], errors="coerce")
        volume = pd.to_numeric(klines["quote_volume"], errors="coerce")
        close = close.where((close > 0.0) & (volume > 0.0))

        closes[symbol] = close
        volumes[symbol] = volume
        funding_by_symbol[symbol] = aggregate_funding_daily(funding)

        gaps = funding.index.to_series().diff().dt.total_seconds().div(86_400.0)
        coverage[symbol] = FundingCoverage(
            symbol=symbol,
            first_funding=funding.index[0].date() if len(funding) else None,
            last_funding=funding.index[-1].date() if len(funding) else None,
            n_funding_events=len(funding),
            n_kline_days=int(close.notna().sum()),
            max_funding_gap_days=float(gaps.max()) if len(funding) > 1 else float("nan"),
        )

    if not closes:
        empty = pd.DataFrame()
        return FundingCarryPanels(empty, empty, empty, coverage, missing)

    close_frame = pd.concat(closes, axis=1).sort_index()
    close_frame = close_frame.dropna(how="all")
    volume_frame = pd.concat(volumes, axis=1).reindex(close_frame.index)
    funding_frame = pd.concat(funding_by_symbol, axis=1).reindex(close_frame.index)
    # 0.0 where the perp traded but no settlement landed that day; NaN
    # where there was no market — see FundingCarryPanels.
    funding_frame = funding_frame.fillna(0.0).where(close_frame.notna())

    return FundingCarryPanels(
        close=close_frame,
        quote_volume=volume_frame,
        funding_daily=funding_frame,
        coverage=coverage,
        symbols_missing=missing,
    )


def build_funding_eligibility(close: pd.DataFrame, quote_volume: pd.DataFrame) -> pd.DataFrame:
    """Boolean (dates x symbols): a liquid perp market as of this date,
    judged on strictly PRIOR turnover (.shift(1), the sibling families'
    point-in-time discipline) AND priced today (the formation trade must
    be executable at today's close — the same-row read the sibling
    family's gate documents as not-look-ahead)."""
    liquid = (
        quote_volume.rolling(FUNDING_LIQUIDITY_WINDOW_DAYS, min_periods=FUNDING_LIQUIDITY_MIN_PERIODS)
        .median()
        .shift(1)
        >= FUNDING_MIN_QUOTE_VOLUME
    )
    return (liquid & close.notna()).fillna(False).astype(bool)


# --- signal ------------------------------------------------------------------


def funding_carry_signal(
    funding_daily: pd.DataFrame,
    close: pd.DataFrame,
    row: int,
    window_days: int,
) -> pd.Series:
    """The formation-row signal: MINUS the mean daily funding over the
    window ENDING AT row (inclusive), refusing any symbol with under
    MIN_SIGNAL_OBS_FRACTION of the window populated or no price at the
    formation row.

    NO LOOK-AHEAD BY CONSTRUCTION: reads funding_daily rows
    row-window_days+1 .. row only. Every settlement in those rows is
    stamped at or before 16:00 UTC of the formation day for an 8h symbol
    (and earlier for 4h/1h), all strictly before the formation trade at
    the day's close (00:00 UTC of the next day) — settled, known cash,
    not a forecast. A dedicated test mutates future rows and asserts the
    signal is bit-identical."""
    window = funding_daily.iloc[max(0, row - window_days + 1) : row + 1]
    n_obs = window.notna().sum()
    mean_funding = window.mean(skipna=True)
    signal = -mean_funding
    required = math.ceil(window_days * MIN_SIGNAL_OBS_FRACTION)
    signal[n_obs < required] = np.nan
    signal[close.iloc[row].isna()] = np.nan
    signal[~np.isfinite(signal)] = np.nan
    return signal


# --- family ------------------------------------------------------------------


def build_funding_carry_family() -> list[FundingCarrySpec]:
    """The full, fixed 12-definition family. Assertions pin the size to
    the pre-declared axes so a drift silently changing the DSR
    denominator is impossible."""
    specs = [
        FundingCarrySpec(
            pattern_id=f"xf_carry_w{window}_h{holding}_f{int(fraction * 100)}",
            avg_window_days=window,
            holding_days=holding,
            rank_fraction=fraction,
        )
        for window in FUNDING_AVG_WINDOWS_DAYS
        for holding in FUNDING_HOLDING_DAYS
        for fraction in FUNDING_RANK_FRACTIONS
    ]
    assert len(specs) == FUNDING_CARRY_N_TRIALS, (
        f"funding-carry family has {len(specs)} definitions, not the pre-declared "
        f"{FUNDING_CARRY_N_TRIALS} — the axes and the family size may never disagree"
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert FUNDING_CARRY_N_TRIALS == 12
    return specs


def default_funding_carry_config() -> FundingCarryConfig:
    return FundingCarryConfig()


# --- backtest ----------------------------------------------------------------


def run_funding_carry_backtest(
    panels: FundingCarryPanels,
    spec: FundingCarrySpec,
    config: FundingCarryConfig,
    eligibility: pd.DataFrame | None = None,
) -> FundingCarryBacktest:
    """One spec's full replay. Reforms every spec.holding_days calendar
    rows from the first row at/after config.formation_start; each day's
    gross return is realize_formation_day over FUNDING-INCLUSIVE member
    returns (r_net = r_price - f_day — the load-bearing construction, see
    the module docstring), with the long-minus-short and
    survivor-renormalization conventions reused from the harness rather
    than re-derived. Turnover cost lands on the first realized day of
    each formation, exactly as _replay_sleeve charges it.

    Attribution: the price-only component is realized over r_price masked
    to r_net's own NaN pattern, so both components see the identical
    survivor set and weights; the funding component is then EXACTLY
    gross - price (linearity of a fixed-weight mean), an identity a test
    asserts."""
    close = panels.close
    index = close.index
    n = len(index)
    if n == 0:
        return FundingCarryBacktest(pd.Series(dtype=float), [], 0.0, 0.0, 0.0, 0.0)

    if eligibility is None:
        eligibility = build_funding_eligibility(close, panels.quote_volume)

    r_price = close.pct_change(fill_method=None)
    r_net = r_price - panels.funding_daily
    r_price_masked = r_price.where(r_net.notna())

    first = int(index.searchsorted(pd.Timestamp(config.formation_start)))
    prev_weights: dict[str, float] = {}
    formations: list[FormationRecordLite] = []
    daily: dict[pd.Timestamp, float] = {}
    total_cost = 0.0
    total_turnover = 0.0
    total_funding_pnl = 0.0
    total_price_pnl = 0.0

    for i in range(first, n - 1, spec.holding_days):
        signal = funding_carry_signal(panels.funding_daily, close, i, spec.avg_window_days)
        eligible_row = eligibility.iloc[i].reindex(signal.index).fillna(False)
        signal = signal.where(eligible_row)

        n_valid = int(signal.notna().sum())
        n_leg = max(1, int(n_valid * spec.rank_fraction)) if n_valid else 0
        skipped: str | None = None
        if n_valid == 0 or n_leg < config.min_names_per_leg:
            skipped = (
                f"leg of {n_leg} from {n_valid} valid names is below "
                f"min_names_per_leg={config.min_names_per_leg}"
            )
        elif 2 * n_leg > n_valid:
            skipped = f"universe of {n_valid} too small for disjoint legs of {n_leg}"

        if skipped is None:
            long_leg, short_leg = select_leg_tickers(signal, spec.rank_fraction)
            long_weights = {t: 1.0 / len(long_leg) for t in long_leg}
            short_weights = {t: 1.0 / len(short_leg) for t in short_leg}
        else:
            long_leg, short_leg = [], []
            long_weights, short_weights = {}, {}

        net_weights: dict[str, float] = {t: w for t, w in long_weights.items()}
        for t, w in short_weights.items():
            net_weights[t] = net_weights.get(t, 0.0) - w

        turnover = _turnover(prev_weights, net_weights)
        cost = turnover * config.cost_bps / 10_000.0
        prev_weights = net_weights
        total_turnover += turnover

        formations.append(
            FormationRecordLite(
                formation_date=index[i].date(),
                long_tickers=list(long_leg),
                short_tickers=list(short_leg),
                turnover=turnover,
                skipped_reason=skipped,
            )
        )

        hold_end = min(i + spec.holding_days, n - 1)
        for j in range(i + 1, hold_end + 1):
            gross = realize_formation_day(r_net.iloc[j], long_weights, short_weights)
            price_component = realize_formation_day(r_price_masked.iloc[j], long_weights, short_weights)
            funding_component = gross - price_component
            cost_today = cost if j == i + 1 else 0.0
            total_cost += cost_today
            total_funding_pnl += funding_component
            total_price_pnl += price_component
            daily[index[j]] = gross - cost_today

    return FundingCarryBacktest(
        daily_returns=pd.Series(daily).sort_index(),
        formations=formations,
        total_cost_drag=total_cost,
        total_turnover=total_turnover,
        total_funding_pnl=total_funding_pnl,
        total_price_pnl=total_price_pnl,
    )


# --- screening ---------------------------------------------------------------


def screen_funding_carry_family(
    panels: FundingCarryPanels,
    specs: list[FundingCarrySpec],
    config: FundingCarryConfig,
) -> tuple[list[FundingCarrySpecResult], dict[str, pd.Series]]:
    """One Sharpe per spec, DSR-corrected with n_trials =
    FUNDING_CARRY_N_TRIALS (the pre-declared size, NEVER the survivor
    count) and sigma_sr = the ddof=1 spread of the sibling Sharpes from
    this same pass — screen_cross_sectional_universe's exact convention,
    restated here because this family runs its own loop (its returns need
    the funding term the shared harness cannot compute). Returns the
    results and each spec's daily net series for diagnostics."""
    eligibility = build_funding_eligibility(panels.close, panels.quote_volume)
    replays: dict[str, FundingCarryBacktest] = {}
    for spec in specs:
        bt = run_funding_carry_backtest(panels, spec, config, eligibility)
        if len(bt.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            continue
        replays[spec.pattern_id] = bt

    sharpes = {
        pid: sharpe_ratio(bt.daily_returns, periods_per_year=config.periods_per_year)
        for pid, bt in replays.items()
    }
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {s.pattern_id: s for s in specs}
    results: list[FundingCarrySpecResult] = []
    daily_by_pattern: dict[str, pd.Series] = {}
    for pattern_id, bt in replays.items():
        spec = spec_by_id[pattern_id]
        formed = [f for f in bt.formations if f.skipped_reason is None]
        skipped = [f for f in bt.formations if f.skipped_reason is not None]
        avg_leg = float(np.mean([f.n_long for f in formed])) if formed else 0.0
        deflated = compute_deflated_sharpe(
            sharpes[pattern_id],
            bt.daily_returns,
            FUNDING_CARRY_N_TRIALS,
            sigma_sr,
            periods_per_year=config.periods_per_year,
        )
        results.append(
            FundingCarrySpecResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                n_formations=len(formed),
                n_skipped_formations=len(skipped),
                avg_names_per_leg=avg_leg,
                n_trading_days=len(bt.daily_returns),
                sharpe_annualized=float(sharpes[pattern_id]),
                total_cost_drag=float(bt.total_cost_drag),
                total_turnover=float(bt.total_turnover),
                total_funding_pnl=float(bt.total_funding_pnl),
                total_price_pnl=float(bt.total_price_pnl),
                deflated_sharpe=deflated,
            )
        )
        daily_by_pattern[pattern_id] = bt.daily_returns
    return results, daily_by_pattern


# --- cross-venue sanity check ------------------------------------------------

# Both endpoints verified keyless and live 2026-08-29:
#  * Gate.io: GET https://api.gateio.ws/api/v4/futures/usdt/funding_rate
#      ?contract=BTC_USDT&limit=100 -> [{"r": "<rate>", "t": <epoch s>}]
#      (t observed with a couple of seconds' jitter, e.g. ...02).
#  * KuCoin:  GET https://api-futures.kucoin.com/api/v1/contract/funding-rates
#      ?symbol=XBTUSDTM&from=<ms>&to=<ms> ->
#      {"code": "200000", "data": [{"fundingRate": <float>, "timepoint": <ms>}]}
# Bybit and OKX were the first choices and are unreachable from this
# environment (DNS resolution fails for api.bybit.com and www.okx.com —
# measured, not assumed), which is why these two venues stand in.
GATE_FUNDING_URL = "https://api.gateio.ws/api/v4/futures/usdt/funding_rate"
KUCOIN_FUNDING_URL = "https://api-futures.kucoin.com/api/v1/contract/funding-rates"
GATE_SYMBOLS = {"BTCUSDT": "BTC_USDT", "ETHUSDT": "ETH_USDT", "DOGEUSDT": "DOGE_USDT"}
KUCOIN_SYMBOLS = {"BTCUSDT": "XBTUSDTM", "ETHUSDT": "ETHUSDTM", "DOGEUSDT": "DOGEUSDTM"}


def _daily_sum(rates: pd.Series) -> pd.Series:
    return rates.groupby(rates.index.normalize()).sum()


def cross_venue_funding_check(
    provider: BinanceFuturesProvider,
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
    days: int = 30,
    client: httpx.Client | None = None,
) -> list[CrossVenueCheckRow]:
    """The deliberately light-touch single-venue honesty check: for a
    couple of majors, compare Binance's DAILY-SUMMED funding against
    Gate.io and KuCoin over the trailing `days`. Daily sums, not
    per-settlement rates, because venues (and Binance itself across
    symbols) run different funding intervals — a day's total carry is the
    interval-agnostic quantity. A venue failure becomes a note row, never
    an exception: this check must not be able to kill a screening run."""
    owns_client = client is None
    http = client if client is not None else httpx.Client(timeout=20.0)
    end = date.today()  # noqa: DTZ011 — trailing-window bound only
    start = end - timedelta(days=days + 2)
    rows: list[CrossVenueCheckRow] = []
    try:
        for symbol in symbols:
            binance_daily = _daily_sum(
                provider.get_funding_history(symbol, start, end)["funding_rate"]
            )
            # Gate.io
            try:
                payload = http.get(
                    GATE_FUNDING_URL, params={"contract": GATE_SYMBOLS[symbol], "limit": 100}
                ).json()
                gate = pd.Series(
                    [float(r["r"]) for r in payload],
                    index=pd.to_datetime([int(r["t"]) for r in payload], unit="s").round("h"),
                ).sort_index()
                rows.append(_compare_row("gate.io", symbol, GATE_SYMBOLS[symbol], binance_daily, _daily_sum(gate)))
            except Exception as exc:  # noqa: BLE001 — a venue being down is a note, not a run failure
                rows.append(
                    CrossVenueCheckRow(
                        "gate.io", symbol, GATE_SYMBOLS[symbol], 0, float("nan"), float("nan"),
                        float("nan"), note=f"fetch failed: {type(exc).__name__}: {exc}",
                    )
                )
            # KuCoin
            try:
                payload = http.get(
                    KUCOIN_FUNDING_URL,
                    params={
                        "symbol": KUCOIN_SYMBOLS[symbol],
                        "from": int(pd.Timestamp(start).timestamp() * 1000),
                        "to": int((pd.Timestamp(end) + pd.Timedelta(days=1)).timestamp() * 1000),
                    },
                ).json()
                data = payload.get("data") or []
                kucoin = pd.Series(
                    [float(r["fundingRate"]) for r in data],
                    index=pd.to_datetime([int(r["timepoint"]) for r in data], unit="ms").round("h"),
                ).sort_index()
                rows.append(
                    _compare_row("kucoin", symbol, KUCOIN_SYMBOLS[symbol], binance_daily, _daily_sum(kucoin))
                )
            except Exception as exc:  # noqa: BLE001 — same containment as above
                rows.append(
                    CrossVenueCheckRow(
                        "kucoin", symbol, KUCOIN_SYMBOLS[symbol], 0, float("nan"), float("nan"),
                        float("nan"), note=f"fetch failed: {type(exc).__name__}: {exc}",
                    )
                )
    finally:
        if owns_client:
            http.close()
    return rows


def _compare_row(
    venue: str,
    binance_symbol: str,
    venue_symbol: str,
    binance_daily: pd.Series,
    venue_daily: pd.Series,
) -> CrossVenueCheckRow:
    joined = pd.concat([binance_daily.rename("b"), venue_daily.rename("v")], axis=1).dropna()
    # Drop the first/last venue days, which the page limit may have
    # truncated mid-day and would compare a partial sum against a full one.
    if len(joined) > 2:
        joined = joined.iloc[1:-1]
    corr = float(joined["b"].corr(joined["v"])) if len(joined) >= 3 else float("nan")
    return CrossVenueCheckRow(
        venue=venue,
        binance_symbol=binance_symbol,
        venue_symbol=venue_symbol,
        n_days_compared=len(joined),
        daily_sum_correlation=corr,
        mean_daily_binance=float(joined["b"].mean()) if len(joined) else float("nan"),
        mean_daily_venue=float(joined["v"].mean()) if len(joined) else float("nan"),
    )


# --- production entry point --------------------------------------------------


def _build_summary_text(summary: FundingCarryScreeningSummary) -> str:
    dead = ", ".join(
        f"{s} {a}..{b}" for s, (a, b) in sorted(summary.dead_symbols_ranked.items())
    )
    lines = [
        (
            f"FUNDING-RATE CARRY FAMILY — READ BEFORE TRUSTING ANY NUMBER. Pre-declared family "
            f"size {summary.n_trials} (3 funding windows x 2 holds x 2 cutoffs), fixed before the "
            f"run and used as the DSR's n_trials in this family's own never-pooled screening. "
            f"MECHANISM: structural funding transfers on Binance USDT perps — positive funding "
            f"means longs pay shorts; the book shorts the highest trailing funding and longs the "
            f"lowest, EQUAL-weighted legs, and every daily return INCLUDES the settled funding "
            f"(r_net = r_price - f_day, settlements summed per UTC day, never rate*3). "
            f"CALENDAR: periods_per_year={summary.periods_per_year:.0f}; the panel has "
            f"{summary.n_missing_calendar_days} missing calendar days across "
            f"{summary.n_panel_rows} rows ({summary.panel_start} .. {summary.panel_end})."
        ),
        (
            f"SINGLE-VENUE DEPENDENCY: every funding rate is Binance's — the largest perp venue, "
            f"but one venue's crowding and clamp conventions. Light-touch cross-venue check below. "
            f"SURVIVORSHIP: Binance serves delisted perps' full history (verified on SRMUSDT and "
            f"LUNAUSDT live); {len(summary.dead_symbols_ranked)} dead/delisted symbol(s) were "
            f"actually eligible in-window ({dead or 'none'}). Candidate list is the sibling crypto "
            f"family's 2026 hand-assembled universe mapped to perp symbols "
            f"({summary.candidate_universe_size} candidates; {len(summary.symbols_missing)} with "
            f"no Binance USDT perp data at all: {', '.join(summary.symbols_missing) or 'none'})."
        ),
        (
            f"ELIGIBILITY: trailing {FUNDING_LIQUIDITY_WINDOW_DAYS}-day median perp turnover >= "
            f"${FUNDING_MIN_QUOTE_VOLUME:,.0f} (shift(1)) and priced at formation; eligible names "
            f"over the formation window: {summary.min_eligible}..{summary.max_eligible}, median "
            f"{summary.median_eligible:.0f}. COSTS: {FUNDING_CARRY_COST_BPS}bp one-way per unit "
            f"of gross notional traded (an assumption, sized to liquid perps; breakevens below), "
            f"no financing charge (perp shorts need no borrow). NOT MODELED: exchange-bankruptcy "
            f"risk, liquidation/margin spirals (the BIS liquidation channel), funding caps in a "
            f"crisis, USDT depeg."
        ),
    ]

    if summary.results:
        lines.append("PER-SPEC RESULTS (net of turnover cost; attribution gross):")
        for r in sorted(summary.results, key=lambda x: -x.sharpe_annualized):
            dsr = r.deflated_sharpe.dsr
            net = r.total_price_pnl + r.total_funding_pnl - r.total_cost_drag
            breakeven = ""
            if r.sharpe_annualized > 0 and r.total_cost_drag > 0:
                gross = net + r.total_cost_drag
                breakeven_bps = FUNDING_CARRY_COST_BPS * gross / r.total_cost_drag
                breakeven = f", breakeven ~{breakeven_bps:.1f}bp one-way"
            lines.append(
                f"  {r.pattern_id}: Sharpe {r.sharpe_annualized:+.3f}, DSR "
                f"{'n/a' if dsr is None else format(dsr, '.3f')}, {r.n_formations} formations "
                f"({r.n_skipped_formations} skipped), avg leg {r.avg_names_per_leg:.1f} | "
                f"cumulative net {net:+.2%} = price {r.total_price_pnl:+.2%} + funding "
                f"{r.total_funding_pnl:+.2%} - costs {r.total_cost_drag:.2%}{breakeven}"
            )

    if summary.cross_venue:
        lines.append(
            "CROSS-VENUE SANITY CHECK (daily-summed funding vs Binance, trailing window; a "
            "reasonableness check, NOT a cross-venue study):"
        )
        for row in summary.cross_venue:
            if row.note:
                lines.append(f"  {row.venue} {row.venue_symbol}: {row.note}")
            else:
                lines.append(
                    f"  {row.venue} {row.venue_symbol}: corr {row.daily_sum_correlation:.3f} over "
                    f"{row.n_days_compared} days; mean daily funding binance "
                    f"{row.mean_daily_binance:+.5%} vs {row.venue} {row.mean_daily_venue:+.5%}"
                )
    if summary.warnings:
        lines.append("WARNINGS: " + " | ".join(summary.warnings))
    return "\n".join(lines)


def run_funding_carry_screening(
    end: date | None = None,
    provider: BinanceFuturesProvider | None = None,
    config: FundingCarryConfig | None = None,
    with_cross_venue_check: bool = True,
) -> FundingCarryScreeningSummary:
    """THE production entry point: fetch/align real Binance panels, replay
    the 12 pre-declared specs, DSR-correct at n_trials=12, run the
    BTC/basket confound regression for every spec, and (by default) the
    cross-venue sanity check. Persistence stays a separate explicit call
    (persist_cross_sectional_trial_results), per that module's contract."""
    end = end if end is not None else date.today()  # noqa: DTZ011 — fetch end bound only
    provider = provider if provider is not None else BinanceFuturesProvider()
    config = config if config is not None else default_funding_carry_config()

    warnings: list[str] = []
    panels = build_funding_carry_panels(provider, end)
    if panels.close.empty:
        summary = FundingCarryScreeningSummary(
            results=[],
            n_trials=FUNDING_CARRY_N_TRIALS,
            periods_per_year=config.periods_per_year,
            panel_start=None,
            panel_end=None,
            n_panel_rows=0,
            n_missing_calendar_days=0,
            formation_start=config.formation_start,
            candidate_universe_size=len(FUNDING_CARRY_UNIVERSE),
            symbols_missing=panels.symbols_missing,
            coverage=panels.coverage,
            min_eligible=0,
            median_eligible=0.0,
            max_eligible=0,
            warnings=["No Binance perp data resolved — nothing was screened."],
        )
        summary.text = _build_summary_text(summary)
        return summary

    close = panels.close
    expected_days = pd.date_range(close.index[0], close.index[-1], freq="D")
    n_missing_calendar_days = len(expected_days.difference(close.index))
    if n_missing_calendar_days:
        warnings.append(
            f"{n_missing_calendar_days} calendar day(s) missing from a 24/7/365 panel — "
            f"periods_per_year={config.periods_per_year:.0f} assumes none."
        )

    bad_gaps = {
        s: c.max_funding_gap_days
        for s, c in panels.coverage.items()
        if np.isfinite(c.max_funding_gap_days) and c.max_funding_gap_days > 2.0
    }
    if bad_gaps:
        warnings.append(
            f"{len(bad_gaps)} symbol(s) have funding-settlement gaps over 2 days (worst: "
            + ", ".join(f"{s}={g:.1f}d" for s, g in sorted(bad_gaps.items(), key=lambda kv: -kv[1])[:5])
            + ") — those days were treated as zero funding while the perp traded."
        )

    eligibility = build_funding_eligibility(close, panels.quote_volume)
    in_window = eligibility.loc[eligibility.index >= pd.Timestamp(config.formation_start)]
    counts = in_window.sum(axis=1)

    dead_symbols_ranked: dict[str, tuple[date, date]] = {}
    last_row = close.index[-1]
    for symbol in eligibility.columns:
        priced = close[symbol].dropna()
        if priced.empty or priced.index[-1] == last_row:
            continue
        flags = in_window[symbol]
        on = flags[flags]
        if len(on):
            dead_symbols_ranked[symbol] = (on.index[0].date(), on.index[-1].date())

    specs = build_funding_carry_family()
    results, daily_by_pattern = screen_funding_carry_family(panels, specs, config)

    btc_returns = close["BTCUSDT"].pct_change(fill_method=None) if "BTCUSDT" in close else pd.Series(dtype=float)
    basket_returns = close.pct_change(fill_method=None).where(eligibility).mean(axis=1, skipna=True)
    exposures = {
        pattern_id: compute_crypto_factor_exposure(
            pattern_id,
            series,
            btc_returns.reindex(series.index),
            basket_returns.reindex(series.index),
        )
        for pattern_id, series in daily_by_pattern.items()
    }

    cross_venue: list[CrossVenueCheckRow] = []
    if with_cross_venue_check:
        cross_venue = cross_venue_funding_check(provider)

    summary = FundingCarryScreeningSummary(
        results=results,
        n_trials=FUNDING_CARRY_N_TRIALS,
        periods_per_year=config.periods_per_year,
        panel_start=close.index[0].date(),
        panel_end=close.index[-1].date(),
        n_panel_rows=len(close),
        n_missing_calendar_days=n_missing_calendar_days,
        formation_start=config.formation_start,
        candidate_universe_size=len(FUNDING_CARRY_UNIVERSE),
        symbols_missing=panels.symbols_missing,
        coverage=panels.coverage,
        min_eligible=int(counts.min()) if len(counts) else 0,
        median_eligible=float(counts.median()) if len(counts) else 0.0,
        max_eligible=int(counts.max()) if len(counts) else 0,
        dead_symbols_ranked=dead_symbols_ranked,
        factor_exposures=exposures,
        cross_venue=cross_venue,
        warnings=warnings,
    )
    summary.text = _build_summary_text(summary)
    return summary


__all__ = [
    "BINANCE_SYMBOL_EXCEPTIONS",
    "FUNDING_AVG_WINDOWS_DAYS",
    "FUNDING_CARRY_CITATION",
    "FUNDING_CARRY_COST_BPS",
    "FUNDING_CARRY_DATA_START",
    "FUNDING_CARRY_FAMILY_KEY",
    "FUNDING_CARRY_FORMATION_START",
    "FUNDING_CARRY_MIN_NAMES_PER_LEG",
    "FUNDING_CARRY_N_TRIALS",
    "FUNDING_CARRY_PERIODS_PER_YEAR",
    "FUNDING_CARRY_UNIVERSE",
    "FUNDING_HOLDING_DAYS",
    "FUNDING_LIQUIDITY_MIN_PERIODS",
    "FUNDING_LIQUIDITY_WINDOW_DAYS",
    "FUNDING_MIN_QUOTE_VOLUME",
    "FUNDING_RANK_FRACTIONS",
    "MIN_SIGNAL_OBS_FRACTION",
    "CrossVenueCheckRow",
    "FormationRecordLite",
    "FundingCarryBacktest",
    "FundingCarryConfig",
    "FundingCarryPanels",
    "FundingCarryScreeningSummary",
    "FundingCarrySpec",
    "FundingCarrySpecResult",
    "FundingCoverage",
    "aggregate_funding_daily",
    "binance_symbol_for",
    "build_funding_carry_family",
    "build_funding_carry_panels",
    "build_funding_eligibility",
    "cross_venue_funding_check",
    "default_funding_carry_config",
    "funding_carry_signal",
    "run_funding_carry_backtest",
    "run_funding_carry_screening",
    "screen_funding_carry_family",
]
