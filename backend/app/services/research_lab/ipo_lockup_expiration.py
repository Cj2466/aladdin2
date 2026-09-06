"""IPO SHARE-LOCKUP EXPIRATION — a pre-scheduled, publicly-disclosed supply
shock with a documented but incompletely understood price effect.

PRE-REGISTRATION: data/research_runs/ipo_lockup_expiration_PREREGISTRATION.txt,
committed BEFORE any abnormal return, CAR, Sharpe or DSR of this family was
computed. Everything below implements that document; where this module makes a
call the pre-registration did not specify, it says so at the point of the call.

SOURCE, READ IN FULL (all 30 pages) BEFORE ANY CODE WAS WRITTEN
===============================================================
Field, Laura Casares; Hanka, Gordon. "The Expiration of IPO Share Lockups."
The Journal of Finance, Vol. LVI, No. 2, April 2001, pp. 471-500.

Equation (1), p.477, VERBATIM in form — the three-day abnormal return:

                    +1
    CAR_i  =  [  PROD    (1 + R_i,t) / (1 + R_m,t)  ]  -  1                (1)
                   t=-1

"where R_i,t is the simple return on firm i on day t relative to the unlock
day, and R_m,t is the simple return on the CRSP value weighted market index."
It is a COMPOUNDED ratio of gross returns. Implementing it as SUM(R_i - R_m)
would be a different statistic; compound_abnormal_return below implements the
product form and tests/test_ipo_lockup_expiration.py pins it against a
hand-computed value AND asserts it differs from the additive approximation.

Equation (2), p.478 — abnormal volume:

                                    V_i,T
    Abnormal Volume_i,T  =  --------------------------  -  1              (2)
                             (1/45) * SUM_{t=-50}^{-6} V_i,t

(-50..-6 inclusive is exactly 45 trading days, which is the 1/45.)

WHAT KIND OF CANDIDATE THIS IS, HONESTLY
========================================
NOT a forced/mechanical flow (insiders are ALLOWED to sell, not required to —
p.471: "insiders are suddenly allowed to sell up to the volume limits of Rule
144"), and NOT a clean informed-positioning signal either. The authors state
in their own abstract (p.471): "We find limited support for several hypotheses
that may explain the abnormal return, but no complete explanation." They reject
temporary price pressure (Sec III.B p.487), the trades-at-the-bid explanation
(Sec III.A p.486) and a trading-cost explanation (Sec III.C p.488-489); they
find partial but incomplete support for downward-sloping demand curves and for
worse-than-expected insider sales (Sec VI p.495-496).

AND THE PART THAT SETS THE PRIOR. [FH01] p.472, verbatim: "The abnormal returns
around the unlock day are not large enough to provide short-term profits for
traders who must transact at the bid and ask." Sec III.B p.487-488: "the bid and
ask prices do not fall far enough to reward the strategy of selling short at the
bid price before the unlock day and then covering at the ask price after the
unlock day. This conclusion also holds in the subsample of firms that are
venture financed." The source paper checked, on its own sample, and found no
trade. That is why the cost model here (COST_ARMS) is bounded on both sides and
is the centre of the build rather than a footnote.

THE TWO RISKS THIS FAMILY CARRIES THAT NO OTHER FAMILY IN THIS PROJECT DOES
===========================================================================
1. TICKER RECYCLING IS SILENT MISATTRIBUTION, NOT MISSINGNESS, AND CIK
   RESOLUTION DOES NOT STOP IT. Established live 2026-09-06 on a row from this
   family's OWN universe, before any signal code existed:

     Ritter row: "ConnectOne Bancorp Inc", ticker CNOB, offer date 2013-02-11.
     SEC company_tickers.json maps CNOB -> CIK 712771, title "ConnectOne
     Bancorp, Inc." That NAME-MATCHES the Ritter row. It is WRONG. CIK 712771
     is CENTER Bancorp's registrant (filing since the 1980s); the 2013 IPO
     entity was CIK 1462694. Center Bancorp survived the 2014-07-01 merger,
     renamed itself ConnectOne Bancorp and kept the CNOB symbol. This project's
     own provider returns CNOB rows from 2012-07-02 — seven months before the
     IPO the row describes.

   A CIK-plus-name join ACCEPTS that row and attributes an older, larger bank's
   price series to a 2013 lockup expiration. So the load-bearing gate here is
   not the CIK map. It is FIRST_TRADE_ANCHOR: prices are requested from six
   months before the offer date, and a row is accepted only if its first
   observation lands in [offer_date, offer_date + 7 calendar days]. Measured on
   the 2013 cohort, that offset is 0 for 38 rows and +1 for 25 rows with
   exactly two outliers (-224 CNOB, -507 NVGS) — which independently reproduces
   Ritter's own documentation that the offer date is "sometimes the first day of
   trading, and sometimes the day before the first day of trading".

2. SURVIVORSHIP BIAS OF UNKNOWN DIRECTION. Roughly two thirds of the filtered
   universe returns no free price data at all. The direction this pulls the
   average abnormal return is NOT established and is NOT guessed: see
   ipo_lockup_feasibility_2026-09-06.txt Q3 and the pre-registration section 6.
   Any PASS or UNRESOLVED verdict must carry the measured availability rate and
   the unknown-direction statement in the verdict paragraph itself.

A DELIBERATE DIFFERENCE FROM EVERY OTHER FAMILY HERE: TWO RETURN STREAMS
========================================================================
~600 one-shot per-company events pooled over eight years is not a repeated
monthly cross-section and not a repeated aggregate timing decision, and the
number of OBSERVATIONS feeding PSR's sqrt(n-1) is genuinely ambiguous for it.
So both readings are computed for every spec and the verdict takes the WORSE
(lower) DSR of the two — a min, not a choice, fixed in the pre-registration
before any number existed:

  stream `daily`  a calendar-time portfolio: on each trading day, the summed
                  hedged return of every event currently inside its window,
                  0.0 on days with none. ~2,000 observations, 252/year.
  stream `event`  one observation per DISTINCT UNLOCK DATE: the summed
                  Equation-(1) trade return of the events unlocking that day.
                  ~500 observations, periods_per_year measured from the data.

The MULTIPLE-COMPARISONS denominator is a separate question and is unaffected
by the event structure: it is the count of pre-declared SPECS (24) run through
the project-wide Policy D ladder, exactly as every other family does.

The two streams differ in one respect worth stating rather than hiding: the
`event` stream uses Equation (1)'s COMPOUNDED form, because that is the paper's
statistic, while the `daily` stream sums simple daily differences, because that
is what a constant-notional position actually earns each day. Over a 3-7 day
window at ordinary return magnitudes the two agree to second order (O(r^2),
~1e-4 on a 1-2% daily move). Neither is an approximation of the other's intent.
"""

from __future__ import annotations

import difflib
import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.research_lab.borrow_cost import (
    GENERAL_COLLATERAL_BPS_PER_YEAR,
    HARD_TO_BORROW_BPS_PER_YEAR,
)
from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio
from app.services.research_lab.preservation_score import compute_preservation_metrics
from app.services.research_lab.spread_estimator import (
    COST_MODEL_WINDOW_DAYS,
    build_edge_half_spread_frame,
)

logger = logging.getLogger(__name__)

IPO_LOCKUP_CITATION = (
    "Field, Laura Casares; Hanka, Gordon, 'The Expiration of IPO Share Lockups', "
    "The Journal of Finance 56(2), April 2001, pp. 471-500. Eq. (1) p.477 (three-day "
    "CAR, compounded, vs the CRSP value-weighted index); Eq. (2) p.478 (abnormal "
    "volume, normalised on days -50..-6); Table I p.476 (80% of lockups exactly 180 "
    "days); Table II p.479 (day -1..+1 CAR -1.5%, day -5..+1 CAR -1.9%); Table III "
    "p.481 (VC-backed -2.3% vs non-VC -0.8%); Sec II.D.1 p.484 (no-lockup placebo, "
    "days 175-181, insignificant -0.4%); Sec III.C p.488 (unlock days tend to fall on "
    "Monday); Sec VI p.495-496 ('no complete explanation')."
)

RITTER_CITATION = (
    "Jay R. Ritter, 'IPO-age.xlsx', sheet 1975-2025, Warrington College of Business, "
    "University of Florida, https://site.warrington.ufl.edu/ritter/files/IPO-age.xlsx, "
    "downloaded 2026-09-06. VC column coding (1=VC-backed, 2=growth-capital-backed) "
    "established empirically against Ritter's own 'IPO-age' documentation and his "
    "published Table 4c ('VC-backed, Growth Capital-backed, and Buyout-backed IPOs, "
    "1980-2025', updated 2025-12-29) rather than assumed -- see the pre-registration "
    "section 5.1 for the year-by-year cross-tabulation."
)

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
IPO_LOCKUP_DIR = _DATA_DIR / "ipo_lockup"
RITTER_IPO_AGE_PATH = IPO_LOCKUP_DIR / "IPO-age.xlsx"
RITTER_SHEET_NAME = "1975-2025"
SEC_COMPANY_TICKERS_PATH = IPO_LOCKUP_DIR / "sec_company_tickers.json"
TICKER_INFO_PATH = IPO_LOCKUP_DIR / "ticker_info.json"
PRICE_STORE_DIR = IPO_LOCKUP_DIR / "price_store"

# ---------------------------------------------------------------------------
# universe constants (pre-registration section 5)
# ---------------------------------------------------------------------------

UNIVERSE_START_YEAR = 2012
UNIVERSE_END_YEAR = 2019

# Ritter's ADR column is NOT a 0/1 flag. Its 2012-2019 values are 1 (ordinary
# US common, n=1,488), 2 (ADRs, n=130, exactly as the column header says) and
# 3-7 (n=86), which on inspection are BDCs/credit funds, MLP and energy funds,
# municipal-bond funds and royalty funds. Keeping ONLY 1 is a first-party
# implementation of [FH01] Sec I.A's exclusion of "non-common stock offers
# (unit offers, REITs, and ADRs)".
ORDINARY_COMMON_ADR_FLAG = 1

# Nasdaq's fifth-character symbol convention: "U" denotes units. Length is
# required to be exactly 5 so ordinary four-letter tickers ending in U (MANU)
# survive. Implements [FH01] Sec I.A's "unit offers" exclusion.
UNIT_TICKER_LENGTH = 5
UNIT_TICKER_SUFFIX = "U"

SPAC_NAME_PATTERN = re.compile(r"ACQUISITION|ACQUISITIONS|\bACQ\b|BLANK CHECK|\bSPAC\b", re.IGNORECASE)

# Ritter records an unknown founding year as -99. A founding year equal to (or
# after) the IPO year means a vehicle formed for the offering, which by
# construction has no pre-IPO shareholders to lock up. On this universe the
# rule removes REITs, MLPs, royalty trusts, BDCs and mutual-to-stock bank
# conversions -- the same categories [FH01] Sec I.A excludes by hand.
MIN_PLAUSIBLE_FOUNDING_YEAR = 1800

VC_FLAG_VENTURE = 1
VC_FLAG_NONE = 0
VC_FLAG_GROWTH_CAPITAL = 2  # verified against Ritter Table 4c; in `all` only

# ---------------------------------------------------------------------------
# event constants (pre-registration sections 5.3, 8)
# ---------------------------------------------------------------------------

LOCKUP_CALENDAR_DAYS = 180
# 240 is not one of the lockup lengths [FH01] p.475 says actually occur ("90,
# 270, or 365 days"), and the widest window around day 240 cannot overlap the
# one around day 180. The free-data analogue of [FH01] Sec II.D.1's own
# no-lockup control (p.484).
PLACEBO_CALENDAR_DAYS = 240
EVENT_TYPE_DAYS = {"lockup": LOCKUP_CALENDAR_DAYS, "placebo": PLACEBO_CALENDAR_DAYS}

# (first day, last day) relative to the unlock day. Both are [FH01] Table II
# p.479's own windows, printed in bold there.
EVENT_WINDOWS: dict[str, tuple[int, int]] = {"w_m1_p1": (-1, 1), "w_m5_p1": (-5, 1)}

BENCHMARK_TICKER = "SPY"

# Equation (2)'s normalisation window, p.478.
VOLUME_NORM_FIRST_DAY = -50
VOLUME_NORM_LAST_DAY = -6

# The last day before the widest event window opens. Used for the penny-stock
# filter and as the as-of date for the EDGE half-spread, so both are identical
# across the two window arms and neither can see the event.
COST_AS_OF_DAY = -6

# [FH01] Sec I.A excludes "300 'penny stocks' with a price below five dollars",
# measured at the offer. Ritter's file carries no offer price, so this is
# applied to the AS-TRADED close on day -6 (deviation D5). As-traded, not
# adjusted: Yahoo retroactively split-adjusts Close for all history, so an
# adjusted level is not a price.
MIN_PRICE_DOLLARS = 5.0

# Identity gate G2. Six months of lead so any earlier holder of the symbol is
# visible; a 7-day upper bound for holidays (the measured data uses 0 and +1
# only).
IDENTITY_LOOKBACK_DAYS = 183
FIRST_TRADE_ANCHOR_MAX_LAG_DAYS = 7

# Identity gate G3's name-similarity threshold. Ritter truncates company names
# to ~30 characters ("Greenway Medical Tech Inc"), so an exact match is not
# available; difflib on normalised names with a 0.6 floor is the rule, declared
# here rather than tuned.
NAME_SIMILARITY_FLOOR = 0.60
EQUITY_QUOTE_TYPE = "EQUITY"

_CORPORATE_SUFFIXES = {
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED",
    "PLC", "LLC", "LP", "NV", "SA", "AG", "HOLDING", "HOLDINGS", "GROUP", "THE",
    "CLASS", "A", "COM", "COMMON", "STOCK", "SHARES",
}

# ---------------------------------------------------------------------------
# screening constants (pre-registration sections 8-12)
# ---------------------------------------------------------------------------

IPO_LOCKUP_N_TRIALS = 24  # 2 event types x 2 windows x 2 benchmarks x 3 cross-sections
VALIDATED_EDGE_BAR = 0.95
SCREENING_FLOOR = 0.50

MIN_EVENTS_PER_SPEC = 30
MIN_DAILY_OBSERVATIONS = 252
MIN_EVENT_OBSERVATIONS = 60

# preservation_score.MIN_HALF_OBSERVATIONS is documented as "half a trading
# year" and is 126 for a daily series. The event stream carries roughly 60
# observations a year, so half a year there is 30. The MEANING of the constant
# is preserved, not its numeral. Declared in pre-registration section 10.
EVENT_STREAM_MIN_HALF_OBSERVATIONS = 30

MONTHS_PER_YEAR = 12.0

# A stream whose standard deviation is at or below this is treated as
# degenerate and reports Sharpe 0.0 rather than a ratio of floating-point dust
# (vol_regime_timing.RESIDUAL_DEGENERACY_RATIO's precedent).
STREAM_DEGENERACY_STD = 1e-12

# ---------------------------------------------------------------------------
# [FH01]'s own numbers -- checks for implausible divergence, NOT targets
# ---------------------------------------------------------------------------

PAPER_CAR_M1_P1_ALL = -0.015  # Table II p.479 / Table III p.481, t = -8.7
PAPER_CAR_M5_P1_ALL = -0.019  # Table II p.479, t = -8.7
PAPER_CAR_M1_P1_VC = -0.023  # Table III p.481, t = -9.2, n = 944
PAPER_CAR_M1_P1_NONVC = -0.008  # Table III p.481, t = -4.2, n = 1,004
PAPER_FRACTION_NEGATIVE = 0.63  # Table II p.479
PAPER_ABNORMAL_VOLUME_ALL = 0.44  # Table III p.481, t = 9.0
PAPER_ABNORMAL_VOLUME_VC = 0.75  # Table III p.481, t = 9.0
PAPER_ABNORMAL_VOLUME_NONVC = 0.15  # Table III p.481, t = 2.8
PAPER_PLACEBO_CAR = -0.004  # Sec II.D.1 p.484, insignificant
PAPER_SAMPLE_SIZE = 1948
PAPER_QUOTED_RELATIVE_SPREAD = 0.0335  # Sec III.C p.488, 1988-1997 Nasdaq


# ===========================================================================
# 1. the two equations
# ===========================================================================


def compound_abnormal_return(
    stock_returns: np.ndarray | pd.Series, market_returns: np.ndarray | pd.Series | None
) -> float | None:
    """[FH01] Equation (1), p.477 — the COMPOUNDED cumulative abnormal return.

        CAR_i = [ PROD_{t} (1 + R_i,t) / (1 + R_m,t) ] - 1

    `market_returns` may be None, which is the paper's own raw-return
    robustness arm ("We also examined raw returns... Our results are
    insensitive to these choices", p.477) and sets R_m,t = 0 throughout.

    Returns None on an empty input or a non-finite value, rather than a
    silently wrong number. A gross return of exactly zero on either leg
    (1 + R = 0, a -100% day) is also None: the ratio is undefined and a
    delisting-to-zero is not an abnormal return this statistic can express."""
    stock = np.asarray(stock_returns, dtype=float)
    if stock.size == 0 or not np.all(np.isfinite(stock)):
        return None
    gross_stock = 1.0 + stock
    if np.any(gross_stock == 0.0):
        return None

    if market_returns is None:
        ratio = gross_stock
    else:
        market = np.asarray(market_returns, dtype=float)
        if market.shape != stock.shape or not np.all(np.isfinite(market)):
            return None
        gross_market = 1.0 + market
        if np.any(gross_market == 0.0):
            return None
        ratio = gross_stock / gross_market

    value = float(np.prod(ratio) - 1.0)
    return value if np.isfinite(value) else None


def abnormal_volume(
    volume_window: np.ndarray | pd.Series, normalisation_window: np.ndarray | pd.Series
) -> float | None:
    """[FH01] Equation (2), p.478 — volume relative to the firm's own
    pre-unlock mean daily volume over days -50 to -6 (45 trading days).

        Abnormal Volume_i,T = V_i,T / mean(V_i, t=-50..-6) - 1

    `volume_window` is averaged first when it has more than one element, which
    is the paper's "three-day average abnormal volume, computed as the average
    of equation (2) over days -1 to +1" (p.478). Averaging the ratios and
    dividing the average volume by the same constant denominator are
    algebraically identical, so no choice is being smuggled in here.

    None when the normalisation mean is zero or non-positive (a name with no
    volume in its pre-window has no meaningful abnormal volume)."""
    observed = np.asarray(volume_window, dtype=float)
    baseline = np.asarray(normalisation_window, dtype=float)
    if observed.size == 0 or baseline.size == 0:
        return None
    if not np.all(np.isfinite(observed)) or not np.all(np.isfinite(baseline)):
        return None
    denominator = float(np.mean(baseline))
    if denominator <= 0.0:
        return None
    value = float(np.mean(observed) / denominator - 1.0)
    return value if np.isfinite(value) else None


# ===========================================================================
# 2. the universe
# ===========================================================================


@dataclass(frozen=True)
class IpoRow:
    """One row of Ritter's IPO-age.xlsx, parsed."""

    offer_date: date
    name: str
    ticker: str
    cusip: str | None
    adr_flag: int | None
    vc_flag: int | None
    dual_flag: int | None
    internet_flag: int | None
    crsp_permno: int | None
    founding_year: int | None

    @property
    def is_venture_backed(self) -> bool:
        return self.vc_flag == VC_FLAG_VENTURE

    @property
    def is_not_venture_backed(self) -> bool:
        return self.vc_flag == VC_FLAG_NONE


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_offer_date(value: object) -> date | None:
    raw = _as_int(value)
    if raw is None:
        return None
    text = str(raw)
    if len(text) != 8:
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def load_ritter_universe(path: Path | None = None) -> list[IpoRow]:
    """Every parsable row of Ritter's file, unfiltered.

    openpyxl in read-only mode rather than pandas.read_excel so the sheet name
    is asserted explicitly — a silently-renamed sheet in a future vintage
    should raise, not be picked up positionally."""
    import openpyxl

    source = path or RITTER_IPO_AGE_PATH
    workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
    if RITTER_SHEET_NAME not in workbook.sheetnames:
        raise ValueError(
            f"{source} has sheets {workbook.sheetnames!r}; expected {RITTER_SHEET_NAME!r}. "
            "A new vintage of Ritter's file has renamed the sheet — check the columns too "
            "before changing this constant."
        )
    sheet = workbook[RITTER_SHEET_NAME]

    rows: list[IpoRow] = []
    header_seen = False
    for values in sheet.iter_rows(values_only=True):
        if not header_seen:
            header_seen = True
            continue
        if not values or values[0] is None:
            continue
        offer_date = _parse_offer_date(values[0])
        if offer_date is None:
            continue
        ticker = values[2]
        rows.append(
            IpoRow(
                offer_date=offer_date,
                name=str(values[1]).strip() if values[1] else "",
                ticker=str(ticker).strip().upper() if ticker not in (None, ".", "") else "",
                cusip=str(values[3]).strip() if values[3] else None,
                adr_flag=_as_int(values[4]),
                vc_flag=_as_int(values[5]),
                dual_flag=_as_int(values[6]),
                internet_flag=_as_int(values[8]),
                crsp_permno=_as_int(values[9]),
                founding_year=_as_int(values[10]),
            )
        )
    workbook.close()
    return rows


@dataclass
class UniverseFilterCounts:
    """Row count after each filter step, in order. Reported (F8) rather than
    described, so a build that silently dropped rows would be visible."""

    total_rows: int = 0
    in_window: int = 0
    ticker_present: int = 0
    ordinary_common: int = 0
    not_unit_offer: int = 0
    not_spac_name: int = 0
    operating_history: int = 0
    vc_backed: int = 0
    not_vc_backed: int = 0
    growth_capital: int = 0
    vc_unknown: int = 0
    per_year: dict[int, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "total_rows": self.total_rows,
            "1_in_window": self.in_window,
            "2_ticker_present": self.ticker_present,
            "3_ordinary_common_adr_flag_1": self.ordinary_common,
            "4_not_unit_offer": self.not_unit_offer,
            "5_not_spac_name": self.not_spac_name,
            "6_operating_history_founding_before_ipo": self.operating_history,
            "vc_backed": self.vc_backed,
            "not_vc_backed": self.not_vc_backed,
            "growth_capital": self.growth_capital,
            "vc_unknown": self.vc_unknown,
            "per_year": dict(sorted(self.per_year.items())),
        }


def filter_universe(
    rows: list[IpoRow], *, start_year: int = UNIVERSE_START_YEAR, end_year: int = UNIVERSE_END_YEAR
) -> tuple[list[IpoRow], UniverseFilterCounts]:
    """Pre-registration section 5.2, in order, counting at every step."""
    counts = UniverseFilterCounts(total_rows=len(rows))

    current = [r for r in rows if start_year <= r.offer_date.year <= end_year]
    counts.in_window = len(current)

    current = [r for r in current if r.ticker]
    counts.ticker_present = len(current)

    current = [r for r in current if r.adr_flag == ORDINARY_COMMON_ADR_FLAG]
    counts.ordinary_common = len(current)

    current = [
        r
        for r in current
        if not (len(r.ticker) == UNIT_TICKER_LENGTH and r.ticker.endswith(UNIT_TICKER_SUFFIX))
    ]
    counts.not_unit_offer = len(current)

    current = [r for r in current if not SPAC_NAME_PATTERN.search(r.name)]
    counts.not_spac_name = len(current)

    current = [
        r
        for r in current
        if r.founding_year is not None
        and MIN_PLAUSIBLE_FOUNDING_YEAR < r.founding_year < r.offer_date.year
    ]
    counts.operating_history = len(current)

    counts.vc_backed = sum(1 for r in current if r.vc_flag == VC_FLAG_VENTURE)
    counts.not_vc_backed = sum(1 for r in current if r.vc_flag == VC_FLAG_NONE)
    counts.growth_capital = sum(1 for r in current if r.vc_flag == VC_FLAG_GROWTH_CAPITAL)
    counts.vc_unknown = len(current) - counts.vc_backed - counts.not_vc_backed - counts.growth_capital
    counts.per_year = dict(Counter(r.offer_date.year for r in current))
    return current, counts


# ===========================================================================
# 3. identity resolution (pre-registration section 5.4)
# ===========================================================================

CIK_NAME_MATCH = "cik_name_match"
CIK_NAME_MISMATCH = "cik_name_mismatch"
CIK_ABSENT = "cik_absent"


def normalise_company_name(name: str) -> str:
    """Uppercase, strip punctuation, drop generic corporate suffixes.

    Deliberately crude and deterministic: this feeds a similarity SCORE, not a
    decision by itself, and a cleverer normaliser would be one more thing to
    get subtly wrong."""
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", (name or "").upper())
    tokens = [t for t in text.split() if t and t not in _CORPORATE_SUFFIXES]
    return " ".join(tokens)


def name_similarity(left: str, right: str) -> float:
    a, b = normalise_company_name(left), normalise_company_name(right)
    if not a or not b:
        return 0.0
    # Ritter truncates names to ~30 characters, so a prefix containment is a
    # legitimate match even when the full-string ratio is low.
    if a.startswith(b) or b.startswith(a):
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def load_sec_ticker_map(path: Path | None = None) -> dict[str, tuple[int, str]]:
    """{TICKER: (cik, title)} from SEC's company_tickers.json snapshot.

    CURRENT-ONLY, AND NOT SUFFICIENT FOR IDENTITY ON ITS OWN — see the module
    docstring's CNOB case, where this file's own entry name-matches a Ritter row
    it does not describe."""
    source = path or SEC_COMPANY_TICKERS_PATH
    payload = json.loads(source.read_text())
    mapping: dict[str, tuple[int, str]] = {}
    for entry in payload.values():
        ticker = str(entry.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        mapping[ticker] = (int(entry.get("cik_str", 0)), str(entry.get("title", "")))
    return mapping


def classify_cik_status(row: IpoRow, sec_map: dict[str, tuple[int, str]]) -> tuple[str, int | None, str | None]:
    """Identity gate G1. INFORMATIONAL — excludes nothing by itself."""
    hit = sec_map.get(row.ticker)
    if hit is None:
        return CIK_ABSENT, None, None
    cik, title = hit
    status = CIK_NAME_MATCH if name_similarity(row.name, title) >= NAME_SIMILARITY_FLOOR else CIK_NAME_MISMATCH
    return status, cik, title


def first_trade_anchor_ok(first_observation: date, offer_date: date) -> bool:
    """Identity gate G2 — THE LOAD-BEARING ONE.

    Accept only if the ticker's first available price observation, in a window
    that starts six months before the offer date, lands in
    [offer_date, offer_date + FIRST_TRADE_ANCHOR_MAX_LAG_DAYS].

    ANY observation before the offer date rejects the row: the symbol was
    already trading for somebody else (CNOB), or the company itself was already
    quoted before this "IPO" (NVGS). The second case is a real event lost, and
    the gate is conservative about it on purpose — an IPO-date-anchored event
    study cannot use a name whose price series predates its own IPO."""
    if first_observation < offer_date:
        return False
    return (first_observation - offer_date).days <= FIRST_TRADE_ANCHOR_MAX_LAG_DAYS


G3_OK = "ok"
G3_REJECT_QUOTE_TYPE = "reject_quote_type"
G3_REJECT_NAME = "reject_name"
G3_INFO_UNAVAILABLE = "info_unavailable"


def classify_ticker_info(row: IpoRow, info: dict | None) -> str:
    """Identity gate G3 — security type and name, from yfinance's own `.info`.

    A CASE THE PRE-REGISTRATION DID NOT SPECIFY, RESOLVED HERE AND SAID SO: an
    absent or errored `.info` returns G3_INFO_UNAVAILABLE and the row is KEPT,
    counted separately. Rejecting on the absence of a metadata call would
    delete exactly the delisted names whose retention is what LIMITS this
    family's survivorship bias — it would make the headline risk worse in order
    to look stricter."""
    if not info or info.get("error") or not info.get("quoteType"):
        return G3_INFO_UNAVAILABLE
    if str(info.get("quoteType")).upper() != EQUITY_QUOTE_TYPE:
        return G3_REJECT_QUOTE_TYPE
    resolved = info.get("longName") or info.get("shortName") or ""
    if name_similarity(row.name, str(resolved)) < NAME_SIMILARITY_FLOOR:
        return G3_REJECT_NAME
    return G3_OK


# ===========================================================================
# 4. the event panel
# ===========================================================================


@dataclass(frozen=True)
class IdentityPolicy:
    """How the three identity gates behave. THE DEFAULT REPRODUCES THE
    PRE-REGISTRATION EXACTLY and is what the headline verdict is computed on.

    The non-default settings exist because running the pre-registered gates on
    the full universe exposed two defects in them that the 2013-cohort
    measurement behind the pre-registration could not have shown. Both are
    reported as a disclosed SENSITIVITY beside the pre-registered result, never
    in place of it:

    anchor_requires_nonzero_volume
        G2 as pre-registered accepts "the first available price observation".
        On the full universe that turned out to reject 22 unambiguously-correct
        rows (GoDaddy, Shopify, Teladoc, Natera, Bandwidth, SiTime and 16 more)
        at exactly -1 day. VERIFIED CAUSE, not inferred: Yahoo carries a
        SYNTHETIC row on the pricing date at the IPO OFFER PRICE with
        volume = 0 — SHOP 2015-05-20 open=close=1.70 volume=0 before its real
        first trade on 2015-05-21; GDDY 2015-03-31 close=20.00 volume=0 (its
        $20 offer price); TDOC 2015-06-30 close=19.00 volume=0 (its $19 offer
        price). A zero-volume offer-price row is not a trade, so the gate's own
        name ("first-trade anchor") argues for skipping it. That is an
        implementation defect against the pre-registration's stated INTENT, not
        a parameter worth tuning, and it is corrected here only in the
        sensitivity arm so the pre-registered number stays exactly reproducible.

    enforce_g3
        G3 as pre-registered REJECTS on quoteType and on name similarity. On
        the full universe it rejected 44 rows, and inspection shows the large
        majority are correct identifications: all 33 rows tagged
        quoteType="MUTUALFUND" are cik_absent (Nationstar Mortgage, CafePress,
        Tesaro, Pinnacle Foods, Envision Healthcare, Foundation Medicine —
        whose yfinance longName is literally "Foundation Medicine, Inc. Common
        Stock" — Barracuda Networks, RSP Permian and more), i.e. Yahoo tags
        DELISTED equities as MUTUALFUND, and 9 of the 12 name rejections are
        ordinary corporate RENAMES (Restoration Hardware -> RH, ING US -> Voya,
        Hannon Armstrong -> HA Sustainable Infrastructure, ShotSpotter ->
        SoundThinking, Kala Pharmaceuticals -> KALA BIO, Sundial Growers ->
        SNDL, MCBC -> MasterCraft, Orion Engineered Carbons -> Orion S.A.,
        Wheeler REIT -> Wheeler Real Estate Investment Trust).

        THE CONSEQUENCE IS THE OPPOSITE OF WHAT THE GATE WAS FOR: measured on
        this universe, quoteType rejection removes ONLY delisted names (33 of
        33 are cik_absent; zero current filers are affected), so it AMPLIFIES
        the survivorship bias that section 6 of the pre-registration names as
        this family's largest threat. G2, which vouches for the first-trade
        anchor, had already cleared every one of those rows.
    """

    anchor_requires_nonzero_volume: bool = False
    enforce_g3: bool = True

    @property
    def key(self) -> str:
        return "preregistered" if not self.anchor_requires_nonzero_volume and self.enforce_g3 else "corrected"


PREREGISTERED_IDENTITY = IdentityPolicy()
CORRECTED_IDENTITY = IdentityPolicy(anchor_requires_nonzero_volume=True, enforce_g3=False)


@dataclass(frozen=True)
class IpoLockupEvent:
    """One accepted (row, event_type) pair, with everything the replay needs
    already extracted so the backtest touches no price frame."""

    ticker: str
    name: str
    offer_date: date
    event_type: str
    vc_flag: int | None
    unlock_date: date
    # window key -> (dates, stock simple returns, market simple returns)
    window_dates: dict[str, list[pd.Timestamp]]
    window_stock_returns: dict[str, np.ndarray]
    window_market_returns: dict[str, np.ndarray]
    half_spread: float  # one-way, fraction of price, as of day -6
    half_spread_is_fallback: bool
    as_traded_close_day_m6: float
    abnormal_volume_3day: float | None
    abnormal_volume_day_p1: float | None
    unlock_weekday: int  # Monday = 0
    cik_status: str
    g3_status: str


@dataclass
class IdentityCounts:
    """Every gate's outcome, counted. Reported per F8/F9."""

    universe_rows: int = 0
    no_price_rows: int = 0
    g2_rejected_recycled: int = 0
    g3_rejected_quote_type: int = 0
    g3_rejected_name: int = 0
    g3_info_unavailable: int = 0
    penny_rejected: int = 0
    insufficient_window: int = 0
    accepted_universe_rows: int = 0
    cik_status_counts: dict[str, int] = field(default_factory=dict)
    availability_by_cik_status: dict[str, dict[str, int]] = field(default_factory=dict)
    first_obs_offset_counts: dict[int, int] = field(default_factory=dict)
    offer_weekday_counts: dict[int, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "universe_rows": self.universe_rows,
            "no_price_rows": self.no_price_rows,
            "g2_rejected_first_trade_anchor": self.g2_rejected_recycled,
            "g3_rejected_quote_type": self.g3_rejected_quote_type,
            "g3_rejected_name": self.g3_rejected_name,
            "g3_info_unavailable_kept": self.g3_info_unavailable,
            "penny_rejected_below_5_dollars_day_m6": self.penny_rejected,
            "insufficient_event_window": self.insufficient_window,
            "accepted_universe_rows": self.accepted_universe_rows,
            "cik_status_counts": dict(sorted(self.cik_status_counts.items())),
            "availability_by_cik_status": {
                k: dict(v) for k, v in sorted(self.availability_by_cik_status.items())
            },
            "first_obs_minus_offer_date_days": dict(sorted(self.first_obs_offset_counts.items())),
            "offer_weekday_counts": dict(sorted(self.offer_weekday_counts.items())),
        }


@dataclass
class IpoLockupPanel:
    events: list[IpoLockupEvent]
    identity: IdentityCounts
    universe_counts: UniverseFilterCounts
    trading_calendar: pd.DatetimeIndex
    benchmark_returns: pd.Series
    policy: IdentityPolicy = PREREGISTERED_IDENTITY

    def for_event_type(self, event_type: str) -> list[IpoLockupEvent]:
        return [e for e in self.events if e.event_type == event_type]


def predicted_unlock_weekday(offer_weekday: int, calendar_days: int) -> int:
    """The unlock weekday implied by the calendar arithmetic ALONE, ignoring
    market holidays: add `calendar_days` mod 7 to the offer weekday, then
    forward a Saturday or Sunday landing to the following Monday.

    F2's real content. [FH01] Sec III.C p.488 observes that "because of the
    weekend, unlock days tend to fall on Monday", and the pre-registration
    turned that into a prediction that Monday would be the MODAL unlock
    weekday here. That prediction has an unstated premise — a roughly uniform
    distribution of offer weekdays — which is false for 2012-2019 US IPOs, so
    the modal-Monday form of the check is not the one to run. This function is
    the stricter version: it predicts the whole distribution from the observed
    offer weekdays, and the realised unlock weekdays must match it up to market
    holidays. See the run report's F2 section for the measured comparison."""
    landed = (offer_weekday + calendar_days) % 7
    return 0 if landed in (5, 6) else landed


def _slice_positions(index_length: int, day0: int, first_day: int, last_day: int) -> tuple[int, int] | None:
    """Positions [day0+first_day, day0+last_day] inclusive, plus the position
    before the first (needed to compute the first day's return). None when any
    of them falls outside the series."""
    start = day0 + first_day - 1
    end = day0 + last_day
    if start < 0 or end >= index_length:
        return None
    return start, end


def build_event_panel(
    universe: list[IpoRow],
    *,
    adjusted_by_ticker: dict[str, dict[str, pd.Series]],
    as_traded_close_by_ticker: dict[str, pd.Series],
    half_spread_by_ticker: dict[str, pd.Series],
    benchmark_close: pd.Series,
    sec_map: dict[str, tuple[int, str]],
    ticker_info: dict[str, dict],
    universe_counts: UniverseFilterCounts,
    fallback_half_spread: float,
    policy: IdentityPolicy = PREREGISTERED_IDENTITY,
) -> IpoLockupPanel:
    """Turn the filtered universe plus price data into accepted events.

    THE TIMING CONTRACT: every date used by an event is derived from the OFFER
    DATE alone (offer + 180 or 240 calendar days, then the first trading day on
    or after), and every cost input is read as of day -6. There is no path by
    which a return inside the event window can influence the position or the
    charge."""
    identity = IdentityCounts(universe_rows=len(universe))
    benchmark_returns = benchmark_close.pct_change().dropna()

    events: list[IpoLockupEvent] = []
    for row in universe:
        # F2's diagnostic input. The unlock weekday is a DETERMINISTIC function
        # of the offer weekday (180 = 25*7 + 5, so +5 weekdays, then any
        # weekend landing forwards to the next session), so the realised unlock
        # weekday distribution is only interpretable next to this one.
        identity.offer_weekday_counts[row.offer_date.weekday()] = (
            identity.offer_weekday_counts.get(row.offer_date.weekday(), 0) + 1
        )
        cik_status, _cik, _title = classify_cik_status(row, sec_map)
        identity.cik_status_counts[cik_status] = identity.cik_status_counts.get(cik_status, 0) + 1
        bucket = identity.availability_by_cik_status.setdefault(
            cik_status, {"with_price_rows": 0, "without_price_rows": 0, "accepted": 0}
        )

        fields = adjusted_by_ticker.get(row.ticker)
        close = None if fields is None else fields["close"].dropna()
        if close is None or close.empty:
            identity.no_price_rows += 1
            bucket["without_price_rows"] += 1
            continue
        bucket["with_price_rows"] += 1

        volume = fields["volume"].reindex(close.index)
        anchor_index = close.index
        if policy.anchor_requires_nonzero_volume:
            traded = volume.fillna(0.0) > 0.0
            anchor_index = close.index[traded.to_numpy()]
            if len(anchor_index) == 0:
                identity.no_price_rows += 1
                bucket["with_price_rows"] -= 1
                bucket["without_price_rows"] += 1
                continue
        first_observation = anchor_index[0].date()
        offset = (first_observation - row.offer_date).days
        identity.first_obs_offset_counts[offset] = identity.first_obs_offset_counts.get(offset, 0) + 1
        if not first_trade_anchor_ok(first_observation, row.offer_date):
            identity.g2_rejected_recycled += 1
            continue

        g3_status = classify_ticker_info(row, ticker_info.get(row.ticker))
        if g3_status == G3_REJECT_QUOTE_TYPE:
            identity.g3_rejected_quote_type += 1
            if policy.enforce_g3:
                continue
        elif g3_status == G3_REJECT_NAME:
            identity.g3_rejected_name += 1
            if policy.enforce_g3:
                continue
        elif g3_status == G3_INFO_UNAVAILABLE:
            identity.g3_info_unavailable += 1

        stock_returns = close.pct_change()
        as_traded = as_traded_close_by_ticker.get(row.ticker)
        half_spreads = half_spread_by_ticker.get(row.ticker)

        accepted_any = False
        for event_type, calendar_days in EVENT_TYPE_DAYS.items():
            target = row.offer_date + timedelta(days=calendar_days)
            after = close.index[close.index >= pd.Timestamp(target)]
            if len(after) == 0:
                identity.insufficient_window += 1
                continue
            unlock_timestamp = after[0]
            day0 = int(close.index.get_loc(unlock_timestamp))

            # Every window must fit, and Equation (2)'s -50..-6 normalisation
            # window must fit, or the event is not usable at all.
            if day0 + VOLUME_NORM_FIRST_DAY < 0:
                identity.insufficient_window += 1
                continue
            spans = {
                key: _slice_positions(len(close), day0, first_day, last_day)
                for key, (first_day, last_day) in EVENT_WINDOWS.items()
            }
            if any(span is None for span in spans.values()):
                identity.insufficient_window += 1
                continue

            cost_position = day0 + COST_AS_OF_DAY
            cost_as_of = close.index[cost_position]
            price_day_m6 = (
                float(as_traded.get(cost_as_of, np.nan)) if as_traded is not None else float("nan")
            )
            if not np.isfinite(price_day_m6) or price_day_m6 < MIN_PRICE_DOLLARS:
                identity.penny_rejected += 1
                continue

            half_spread = float("nan")
            if half_spreads is not None:
                half_spread = float(half_spreads.get(cost_as_of, np.nan))
            is_fallback = not (np.isfinite(half_spread) and half_spread > 0.0)
            if is_fallback:
                half_spread = fallback_half_spread

            window_dates: dict[str, list[pd.Timestamp]] = {}
            window_stock: dict[str, np.ndarray] = {}
            window_market: dict[str, np.ndarray] = {}
            usable = True
            for key, (first_day, last_day) in EVENT_WINDOWS.items():
                dates = list(close.index[day0 + first_day : day0 + last_day + 1])
                stock_leg = stock_returns.reindex(dates).to_numpy(dtype=float)
                market_leg = benchmark_returns.reindex(dates).to_numpy(dtype=float)
                if not np.all(np.isfinite(stock_leg)) or not np.all(np.isfinite(market_leg)):
                    usable = False
                    break
                window_dates[key] = dates
                window_stock[key] = stock_leg
                window_market[key] = market_leg
            if not usable:
                identity.insufficient_window += 1
                continue

            norm_slice = volume.iloc[day0 + VOLUME_NORM_FIRST_DAY : day0 + VOLUME_NORM_LAST_DAY + 1]
            three_day = volume.iloc[day0 - 1 : day0 + 2]
            day_p1 = volume.iloc[day0 + 1 : day0 + 2]

            events.append(
                IpoLockupEvent(
                    ticker=row.ticker,
                    name=row.name,
                    offer_date=row.offer_date,
                    event_type=event_type,
                    vc_flag=row.vc_flag,
                    unlock_date=unlock_timestamp.date(),
                    window_dates=window_dates,
                    window_stock_returns=window_stock,
                    window_market_returns=window_market,
                    half_spread=half_spread,
                    half_spread_is_fallback=is_fallback,
                    as_traded_close_day_m6=price_day_m6,
                    abnormal_volume_3day=abnormal_volume(three_day, norm_slice),
                    abnormal_volume_day_p1=abnormal_volume(day_p1, norm_slice),
                    unlock_weekday=int(unlock_timestamp.weekday()),
                    cik_status=cik_status,
                    g3_status=g3_status,
                )
            )
            accepted_any = True

        if accepted_any:
            identity.accepted_universe_rows += 1
            bucket["accepted"] += 1

    calendar = pd.DatetimeIndex(sorted(benchmark_returns.index))
    return IpoLockupPanel(
        events=events,
        identity=identity,
        universe_counts=universe_counts,
        trading_calendar=calendar,
        benchmark_returns=benchmark_returns,
        policy=policy,
    )


# ===========================================================================
# 5. specs and cost arms
# ===========================================================================


@dataclass(frozen=True)
class IpoLockupSpec:
    spec_id: str
    event_type: str
    window: str
    benchmark: str
    cross_section: str
    citation: str
    hypothesis: str
    is_control: bool


CROSS_SECTIONS = ("all", "vc", "nonvc")
BENCHMARKS = ("spy", "raw")


def _hypothesis_for(event_type: str, window: str, benchmark: str, cross_section: str) -> str:
    if event_type == "placebo":
        return (
            f"CONTROL. Day 0 is offer + {PLACEBO_CALENDAR_DAYS} calendar days, which is not a "
            "lockup expiration for any standard contract ([FH01] p.475 names 90/180/270/365). "
            "The free-data analogue of [FH01] Sec II.D.1 p.484, which found an insignificant "
            "-0.4% for no-lockup firms at days 175-181. A placebo effect comparable to the "
            "lockup arm's REFUTES the mechanism attribution."
        )
    first_day, last_day = EVENT_WINDOWS[window]
    target = {
        "all": f"[FH01] Table II p.479: day {first_day}..{last_day} CAR "
        f"{PAPER_CAR_M1_P1_ALL if window == 'w_m1_p1' else PAPER_CAR_M5_P1_ALL:+.1%}",
        "vc": f"[FH01] Table III p.481: venture-backed CAR {PAPER_CAR_M1_P1_VC:+.1%} (t=-9.2)",
        "nonvc": f"[FH01] Table III p.481: non-venture-backed CAR {PAPER_CAR_M1_P1_NONVC:+.1%} (t=-4.2)",
    }[cross_section]
    hedge = "market-hedged with SPY" if benchmark == "spy" else "unhedged (the paper's own raw-return arm, p.477)"
    return (
        f"Short the stock over days {first_day}..{last_day} around the scheduled unlock day, "
        f"{hedge}. Expected sign POSITIVE for the strategy, because the documented CAR is "
        f"negative. {target}."
    )


def build_family() -> list[IpoLockupSpec]:
    """The 24 pre-declared specs. Fully crossed, fixed in the pre-registration
    section 8, not extended after any result."""
    specs: list[IpoLockupSpec] = []
    for event_type in EVENT_TYPE_DAYS:
        for window in EVENT_WINDOWS:
            for benchmark in BENCHMARKS:
                for cross_section in CROSS_SECTIONS:
                    specs.append(
                        IpoLockupSpec(
                            spec_id=f"{event_type}|{window}|{benchmark}|{cross_section}",
                            event_type=event_type,
                            window=window,
                            benchmark=benchmark,
                            cross_section=cross_section,
                            citation=IPO_LOCKUP_CITATION,
                            hypothesis=_hypothesis_for(event_type, window, benchmark, cross_section),
                            is_control=(event_type == "placebo"),
                        )
                    )
    if len(specs) != IPO_LOCKUP_N_TRIALS:
        raise AssertionError(
            f"grid built {len(specs)} specs but the pre-registration declares "
            f"{IPO_LOCKUP_N_TRIALS}. The grid is BINDING — fix the code, not the constant."
        )
    return specs


@dataclass(frozen=True)
class CostArm:
    key: str
    description: str
    stock_half_spread_bps: float | None  # None -> use the per-name EDGE estimate
    benchmark_half_spread_bps: float
    borrow_bps_per_year: float


# 2.0 bp one-way on SPY, identical to rebalancing_pressure_timing.py and
# margin_credit_timing.py so the three families' hedge-leg costs stay
# comparable. It is well above SPY's own quoted half-spread.
SPY_HALF_SPREAD_BPS = 2.0

# The one-tick physical floor, stated as arithmetic rather than estimated: the
# US minimum tick is $0.01, so on a $20 stock one tick is a 5 bp FULL spread
# and 2.5 bp one-way. Nothing real is cheaper. Also the EDGE fallback rate.
CHEAP_HALF_SPREAD_BPS = 2.5

COST_ARMS: tuple[CostArm, ...] = (
    CostArm(
        key="cost_free",
        description="0 bp, 0 borrow -- the GROSS signal, attribution only, NEVER a verdict input",
        stock_half_spread_bps=0.0,
        benchmark_half_spread_bps=0.0,
        borrow_bps_per_year=0.0,
    ),
    CostArm(
        key="cheap",
        description=(
            f"{CHEAP_HALF_SPREAD_BPS} bp flat one-way on the stock leg (the one-tick floor on a "
            f"$20 stock: $0.01 tick = 5 bp full spread = 2.5 bp one-way), {SPY_HALF_SPREAD_BPS} bp "
            f"on SPY, {GENERAL_COLLATERAL_BPS_PER_YEAR} bp/yr general-collateral borrow "
            "(Beneish/Lee/Nichols 2015 p.15). A DELIBERATELY OPTIMISTIC LOWER BOUND, not an "
            "estimate: a spec that fails HERE cannot be rescued by any dispute about the spread "
            "estimator"
        ),
        stock_half_spread_bps=CHEAP_HALF_SPREAD_BPS,
        benchmark_half_spread_bps=SPY_HALF_SPREAD_BPS,
        borrow_bps_per_year=GENERAL_COLLATERAL_BPS_PER_YEAR,
    ),
    CostArm(
        key="baseline",
        description=(
            "per-name, per-day EDGE effective half-spread (Ardia/Guidotti/Kroencke, JFE 2024, "
            f"{COST_MODEL_WINDOW_DAYS}-day rolling window ending at day -6), falling back to "
            f"{CHEAP_HALF_SPREAD_BPS} bp where EDGE has no usable estimate; "
            f"{SPY_HALF_SPREAD_BPS} bp on SPY; {HARD_TO_BORROW_BPS_PER_YEAR} bp/yr HARD-TO-BORROW "
            "(D'Avolio 2002 Table 3 p.286, value-weighted specials mean) because pre-unlock float "
            "is about a third of shares outstanding ([FH01] p.471). THE VERDICT ARM"
        ),
        stock_half_spread_bps=None,
        benchmark_half_spread_bps=SPY_HALF_SPREAD_BPS,
        borrow_bps_per_year=HARD_TO_BORROW_BPS_PER_YEAR,
    ),
)
BASELINE_COST_ARM = "baseline"
COST_ARMS_BY_KEY = {arm.key: arm for arm in COST_ARMS}


def event_matches(event: IpoLockupEvent, spec: IpoLockupSpec) -> bool:
    if event.event_type != spec.event_type:
        return False
    if spec.cross_section == "all":
        return True
    if spec.cross_section == "vc":
        return event.vc_flag == VC_FLAG_VENTURE
    return event.vc_flag == VC_FLAG_NONE


# ===========================================================================
# 6. the replay
# ===========================================================================


@dataclass
class EventTrade:
    ticker: str
    unlock_date: date
    car: float
    gross_return: float
    cost: float
    net_return: float
    half_spread_bps: float
    days_held: int


@dataclass
class IpoLockupBacktestResult:
    spec_id: str
    status: str
    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    event_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    trades: list[EventTrade] = field(default_factory=list)
    n_events: int = 0
    total_cost: float = 0.0
    mean_half_spread_bps: float = 0.0
    fallback_fraction: float = 0.0
    active_day_fraction: float = 0.0
    first_date: str | None = None
    last_date: str | None = None


def _event_cost(event: IpoLockupEvent, spec: IpoLockupSpec, arm: CostArm, days_held: int) -> tuple[float, float, float]:
    """(entry cost, exit cost, borrow cost) as fractions of unit notional."""
    if arm.stock_half_spread_bps is None:
        stock_half = event.half_spread
    else:
        stock_half = arm.stock_half_spread_bps / 1e4
    hedge_half = (arm.benchmark_half_spread_bps / 1e4) if spec.benchmark == "spy" else 0.0
    entry = stock_half + hedge_half
    exit_ = stock_half + hedge_half
    borrow = (arm.borrow_bps_per_year / 1e4) * (days_held / TRADING_DAYS_PER_YEAR)
    return entry, exit_, borrow


def run_ipo_lockup_backtest(
    panel: IpoLockupPanel, spec: IpoLockupSpec, arm: CostArm
) -> IpoLockupBacktestResult:
    """One spec's replay, producing BOTH streams from ONE set of trades so they
    cannot drift apart.

      daily : per trading day, SUM over active events of -(R_stock - R_market),
              minus the costs charged that day. 0.0 on days with no event.
      event : per DISTINCT UNLOCK DATE, SUM over that day's events of
              -CAR (Equation 1) minus that event's whole cost.

    Unit notional per event, deliberately: scaling every event by a common
    capital base divides mean and standard deviation alike and leaves the
    Sharpe -- and therefore the verdict -- unchanged, so no such parameter
    exists to be tuned."""
    selected = [e for e in panel.events if event_matches(e, spec)]
    if len(selected) < MIN_EVENTS_PER_SPEC:
        return IpoLockupBacktestResult(
            spec_id=spec.spec_id, status=f"too_few_events_{len(selected)}", n_events=len(selected)
        )

    daily: dict[pd.Timestamp, float] = {}
    by_unlock: dict[date, float] = {}
    trades: list[EventTrade] = []
    total_cost = 0.0
    half_spreads_bps: list[float] = []
    fallbacks = 0
    active_days: set[pd.Timestamp] = set()

    for event in selected:
        dates = event.window_dates[spec.window]
        stock = event.window_stock_returns[spec.window]
        market = event.window_market_returns[spec.window] if spec.benchmark == "spy" else None
        days_held = len(dates)
        car = compound_abnormal_return(stock, market)
        if car is None:
            continue

        entry, exit_, borrow = _event_cost(event, spec, arm, days_held)
        cost = entry + exit_ + borrow
        total_cost += cost
        half_spreads_bps.append(
            (event.half_spread if arm.stock_half_spread_bps is None else arm.stock_half_spread_bps / 1e4) * 1e4
        )
        if arm.stock_half_spread_bps is None and event.half_spread_is_fallback:
            fallbacks += 1

        gross = -car
        trades.append(
            EventTrade(
                ticker=event.ticker,
                unlock_date=event.unlock_date,
                car=car,
                gross_return=gross,
                cost=cost,
                net_return=gross - cost,
                half_spread_bps=half_spreads_bps[-1],
                days_held=days_held,
            )
        )
        by_unlock[event.unlock_date] = by_unlock.get(event.unlock_date, 0.0) + gross - cost

        daily_borrow = borrow / days_held if days_held else 0.0
        for position, day in enumerate(dates):
            leg = -(stock[position] - (market[position] if market is not None else 0.0))
            charge = daily_borrow
            if position == 0:
                charge += entry
            if position == days_held - 1:
                charge += exit_
            daily[day] = daily.get(day, 0.0) + leg - charge
            active_days.add(day)

    if not trades:
        return IpoLockupBacktestResult(spec_id=spec.spec_id, status="no_replayable_events")

    first_day, last_day = min(daily), max(daily)
    calendar = panel.trading_calendar
    # The benchmark's calendar defines the flat days; the union with the events'
    # own dates keeps any P&L that landed on a session the benchmark missed
    # rather than silently dropping it.
    replay_index = calendar[(calendar >= first_day) & (calendar <= last_day)]
    full_index = replay_index.union(pd.DatetimeIndex(sorted(daily))).sort_values()
    daily_series = pd.Series(0.0, index=full_index)
    daily_series.loc[list(daily)] = list(daily.values())

    event_series = pd.Series(by_unlock).sort_index()
    event_series.index = pd.DatetimeIndex(event_series.index)

    return IpoLockupBacktestResult(
        spec_id=spec.spec_id,
        status="ok",
        daily_returns=daily_series,
        event_returns=event_series,
        trades=trades,
        n_events=len(trades),
        total_cost=total_cost,
        mean_half_spread_bps=float(np.mean(half_spreads_bps)) if half_spreads_bps else 0.0,
        fallback_fraction=fallbacks / len(trades),
        active_day_fraction=len(active_days) / max(len(daily_series), 1),
        first_date=str(daily_series.index[0].date()),
        last_date=str(daily_series.index[-1].date()),
    )


# ===========================================================================
# 7. diagnostics
# ===========================================================================


@dataclass(frozen=True)
class IpoLockupDiagnostics:
    """The replication and mechanism-fidelity numbers (F6, F7, F10), computed
    for every spec and reported beside [FH01]'s own."""

    spec_id: str
    n_events: int
    mean_car: float
    median_car: float
    fraction_negative: float
    car_t_stat: float
    mean_abnormal_volume_3day: float | None
    mean_abnormal_volume_day_p1: float | None
    unlock_weekday_counts: dict[int, int]
    modal_unlock_weekday: int | None
    mean_half_spread_bps: float
    breakeven_half_spread_bps: float | None
    gross_mean_trade_return: float
    net_mean_trade_return: float


def compute_diagnostics(
    panel: IpoLockupPanel, spec: IpoLockupSpec, replay: IpoLockupBacktestResult
) -> IpoLockupDiagnostics:
    cars = np.array([t.car for t in replay.trades], dtype=float)
    gross = np.array([t.gross_return for t in replay.trades], dtype=float)
    net = np.array([t.net_return for t in replay.trades], dtype=float)
    n = len(cars)
    std = float(np.std(cars, ddof=1)) if n >= 2 else 0.0
    t_stat = float(np.mean(cars) / (std / math.sqrt(n))) if std > 0 and n >= 2 else float("nan")

    selected = [e for e in panel.events if event_matches(e, spec)]
    vol_3day = [e.abnormal_volume_3day for e in selected if e.abnormal_volume_3day is not None]
    vol_p1 = [e.abnormal_volume_day_p1 for e in selected if e.abnormal_volume_day_p1 is not None]
    weekdays = Counter(e.unlock_weekday for e in selected)

    # The one-way stock-leg half-spread at which the mean trade return would
    # reach zero: gross - 2*h - hedge - borrow = 0. Everything but h is already
    # in `cost`, so solve on the realised averages.
    mean_gross = float(np.mean(gross)) if n else 0.0
    mean_non_spread = float(np.mean([t.cost - 2.0 * t.half_spread_bps / 1e4 for t in replay.trades])) if n else 0.0
    breakeven = ((mean_gross - mean_non_spread) / 2.0) * 1e4 if n else None

    return IpoLockupDiagnostics(
        spec_id=spec.spec_id,
        n_events=n,
        mean_car=float(np.mean(cars)) if n else float("nan"),
        median_car=float(np.median(cars)) if n else float("nan"),
        fraction_negative=float(np.mean(cars < 0.0)) if n else float("nan"),
        car_t_stat=t_stat,
        mean_abnormal_volume_3day=float(np.mean(vol_3day)) if vol_3day else None,
        mean_abnormal_volume_day_p1=float(np.mean(vol_p1)) if vol_p1 else None,
        unlock_weekday_counts=dict(sorted(weekdays.items())),
        modal_unlock_weekday=(max(weekdays, key=lambda k: weekdays[k]) if weekdays else None),
        mean_half_spread_bps=replay.mean_half_spread_bps,
        breakeven_half_spread_bps=breakeven,
        gross_mean_trade_return=mean_gross,
        net_mean_trade_return=float(np.mean(net)) if n else float("nan"),
    )


# ===========================================================================
# 8. screening
# ===========================================================================


def policy_d_denominators(n_local: int = IPO_LOCKUP_N_TRIALS) -> list[int]:
    """The N values a Policy D report must cover, ascending and deduplicated:
    dsr_n_trials(n_local), n_specs_clustered, raw_pooled_distinct_trials.

    Same derivation and same committed artifact as
    margin_credit_timing.policy_d_denominators. The lowest tier is
    dsr_n_trials(n_local), NOT n_local itself, because that is the denominator
    the screen actually deflates at.

    THE EVENT STRUCTURE DOES NOT ENTER HERE, deliberately: this ladder counts
    SPECIFICATIONS SEARCHED, and a family made of one-shot events searches
    specifications exactly the way a monthly cross-section does. What the event
    structure changes is the OBSERVATION count, which is handled by running two
    streams and taking the worse DSR (pre-registration section 7.4)."""
    from app.services.research_lab.global_effective_n import load_global_effective_n

    artifact = load_global_effective_n()
    return sorted(
        {dsr_n_trials(int(n_local)), artifact.n_specs_clustered, artifact.raw_pooled_distinct_trials}
    )


def _rank_dsr(value: float | None) -> float:
    """Sort key for a DSR that may be None.

    NOT `value or -1.0`: a genuine DSR of exactly 0.0 is falsy in Python and
    would be silently rewritten to -1.0 by that idiom, which would rank a spec
    with a real, computed zero BELOW a spec whose DSR could not be computed at
    all. -1.0 is reserved for the None case, which is what "the machinery could
    not produce a number here" means, and which never clears the bar."""
    return -1.0 if value is None else float(value)


def _annualised_sharpe(returns: pd.Series, periods_per_year: float) -> float:
    if len(returns) < 2 or float(returns.std(ddof=1)) <= STREAM_DEGENERACY_STD:
        return 0.0
    return sharpe_ratio(returns, periods_per_year=periods_per_year)


def event_stream_periods_per_year(returns: pd.Series) -> float:
    """Observations per year, MEASURED from the realised index rather than
    assumed. One observation is one distinct unlock date."""
    if len(returns) < 2:
        return float(len(returns))
    span_days = (returns.index[-1] - returns.index[0]).days
    years = max(span_days / 365.25, 1e-9)
    return float(len(returns) / years)


def dsr_across_denominators(
    sharpe_annualized: float,
    returns: pd.Series,
    sigma_sr_annualized: float | None,
    denominators: list[int],
    periods_per_year: float,
) -> dict[int, float | None]:
    """DSR at each N. None means the machinery could not produce one there
    (below deflated_sharpe.MIN_TRIALS_FOR_DSR, or a degenerate series) and is
    treated downstream as NOT clearing the bar."""
    return {
        int(n): compute_deflated_sharpe(
            sharpe_annualized, returns, int(n), sigma_sr_annualized, periods_per_year=periods_per_year
        ).dsr
        for n in denominators
    }


@dataclass
class StreamResult:
    stream: str
    n_observations: int
    periods_per_year: float
    sharpe_annualized: float
    dsr_by_n: dict[int, float | None]
    preservation: dict[str, float | int | bool | None]
    deflated_sharpe: object


@dataclass
class IpoLockupScreeningResult:
    """One spec's full Policy D record.

    THE VERDICT FIELDS ARE THE WORSE OF THE TWO STREAMS. `sharpe_annualized`
    reports the DAILY stream (the one whose units are comparable to every other
    family here); `dsr_by_n` is the ELEMENTWISE MINIMUM of the two streams' DSR
    at each N, per pre-registration section 7.4. Both streams' own numbers are
    carried in `streams` and neither is ever discarded."""

    spec_id: str
    event_type: str
    window: str
    benchmark: str
    cross_section: str
    citation: str
    hypothesis: str
    is_control: bool
    cost_arm: str
    n_trading_days: int  # DAILY-stream observations — cross_sectional_persistence's contract
    n_events: int
    first_date: str | None
    last_date: str | None
    sharpe_annualized: float
    dsr_by_n: dict[int, float | None]
    preservation: dict[str, float | int | bool | None]
    streams: dict[str, StreamResult]
    active_day_fraction: float
    fallback_fraction: float
    total_cost_drag: float
    bootstrap_p_value: float | None
    deflated_sharpe: object
    diagnostics: IpoLockupDiagnostics


def screen_ipo_lockup(
    panel: IpoLockupPanel,
    specs: list[IpoLockupSpec],
    *,
    cost_arm: str = BASELINE_COST_ARM,
    denominators: list[int] | None = None,
) -> list[IpoLockupScreeningResult]:
    """One record per replayable spec.

    n_trials is fixed at len(specs) — the family's literal pre-declared size —
    raised to the project-wide effectively-independent count by dsr_n_trials
    whenever that is larger, and NEVER shrunk to however many specs survived
    the data floors. Same rule as every other family here.

    sigma_sr is computed PER STREAM as the ddof=1 standard deviation of every
    sibling spec's Sharpe in that stream from this same pass — mixing the two
    streams' Sharpes into one sigma would compare a 252-a-year series against a
    ~60-a-year one."""
    from app.services.research_lab.vol_regime_timing import (
        block_bootstrap_sharpe_pvalue,
    )

    arm = COST_ARMS_BY_KEY[cost_arm]
    denominators = denominators if denominators is not None else policy_d_denominators(len(specs))
    n_local = dsr_n_trials(len(specs)) if specs else 0

    replays: dict[str, IpoLockupBacktestResult] = {}
    for spec in specs:
        replay = run_ipo_lockup_backtest(panel, spec, arm)
        if replay.status != "ok":
            logger.info("ipo_lockup spec %s not replayed: %s", spec.spec_id, replay.status)
            continue
        if len(replay.daily_returns) < MIN_DAILY_OBSERVATIONS:
            logger.info(
                "ipo_lockup spec %s dropped: %d daily observations (floor %d)",
                spec.spec_id,
                len(replay.daily_returns),
                MIN_DAILY_OBSERVATIONS,
            )
            continue
        if len(replay.event_returns) < MIN_EVENT_OBSERVATIONS:
            logger.info(
                "ipo_lockup spec %s dropped: %d event observations (floor %d)",
                spec.spec_id,
                len(replay.event_returns),
                MIN_EVENT_OBSERVATIONS,
            )
            continue
        replays[spec.spec_id] = replay

    daily_sharpes = {
        sid: _annualised_sharpe(r.daily_returns, TRADING_DAYS_PER_YEAR) for sid, r in replays.items()
    }
    event_sharpes = {
        sid: _annualised_sharpe(r.event_returns, event_stream_periods_per_year(r.event_returns))
        for sid, r in replays.items()
    }
    sigma_daily = float(np.std(list(daily_sharpes.values()), ddof=1)) if len(daily_sharpes) >= 2 else None
    sigma_event = float(np.std(list(event_sharpes.values()), ddof=1)) if len(event_sharpes) >= 2 else None

    spec_by_id = {s.spec_id: s for s in specs}
    results: list[IpoLockupScreeningResult] = []
    for spec_id, replay in replays.items():
        spec = spec_by_id[spec_id]

        daily_ppy = TRADING_DAYS_PER_YEAR
        event_ppy = event_stream_periods_per_year(replay.event_returns)
        streams: dict[str, StreamResult] = {}
        for name, series, sharpe, sigma, ppy, min_half in (
            ("daily", replay.daily_returns, daily_sharpes[spec_id], sigma_daily, daily_ppy, None),
            (
                "event",
                replay.event_returns,
                event_sharpes[spec_id],
                sigma_event,
                event_ppy,
                EVENT_STREAM_MIN_HALF_OBSERVATIONS,
            ),
        ):
            dsr_by_n = dsr_across_denominators(sharpe, series, sigma, denominators, ppy)
            deflated = compute_deflated_sharpe(sharpe, series, n_local, sigma, periods_per_year=ppy)
            preservation_kwargs = {} if min_half is None else {"min_half_observations": min_half}
            preservation = compute_preservation_metrics(
                series, dsr=dsr_by_n.get(n_local), periods_per_year=ppy, **preservation_kwargs
            ).as_dict()
            streams[name] = StreamResult(
                stream=name,
                n_observations=len(series),
                periods_per_year=ppy,
                sharpe_annualized=sharpe,
                dsr_by_n=dsr_by_n,
                preservation=preservation,
                deflated_sharpe=deflated,
            )

        # THE VERDICT RULE, pre-registration 7.4: elementwise MINIMUM of the two
        # streams' DSR. A None on either side (the machinery could not produce a
        # number there) propagates as None, which downstream is NOT clearing the
        # bar — never as "the other stream's value".
        merged: dict[int, float | None] = {}
        for n in denominators:
            values = [streams[s].dsr_by_n.get(int(n)) for s in ("daily", "event")]
            merged[int(n)] = None if any(v is None for v in values) else float(min(values))  # type: ignore[arg-type]

        worse_stream = min(streams.values(), key=lambda s: _rank_dsr(s.dsr_by_n.get(n_local)))
        first_day, last_day = EVENT_WINDOWS[spec.window]
        results.append(
            IpoLockupScreeningResult(
                spec_id=spec_id,
                event_type=spec.event_type,
                window=spec.window,
                benchmark=spec.benchmark,
                cross_section=spec.cross_section,
                citation=spec.citation,
                hypothesis=spec.hypothesis,
                is_control=spec.is_control,
                cost_arm=cost_arm,
                n_trading_days=len(replay.daily_returns),
                n_events=replay.n_events,
                first_date=replay.first_date,
                last_date=replay.last_date,
                sharpe_annualized=daily_sharpes[spec_id],
                dsr_by_n=merged,
                preservation=worse_stream.preservation,
                streams=streams,
                active_day_fraction=replay.active_day_fraction,
                fallback_fraction=replay.fallback_fraction,
                total_cost_drag=replay.total_cost,
                bootstrap_p_value=block_bootstrap_sharpe_pvalue(
                    replay.daily_returns, block_length=max(last_day - first_day + 1, 1)
                ),
                deflated_sharpe=streams["daily"].deflated_sharpe,
                diagnostics=compute_diagnostics(panel, spec, replay),
            )
        )
    return results


# ===========================================================================
# 9. summary and verdict
# ===========================================================================


@dataclass
class IpoLockupSummary:
    panel: IpoLockupPanel
    specs: list[IpoLockupSpec]
    denominators: list[int]
    n_local: int
    results_by_cost_arm: dict[str, list[IpoLockupScreeningResult]]
    policy: IdentityPolicy = PREREGISTERED_IDENTITY

    def baseline_results(self) -> list[IpoLockupScreeningResult]:
        return self.results_by_cost_arm.get(BASELINE_COST_ARM, [])

    def best_spec(self, cost_arm: str = BASELINE_COST_ARM, *, controls: bool = False) -> IpoLockupScreeningResult | None:
        candidates = [
            r for r in self.results_by_cost_arm.get(cost_arm, []) if r.is_control == controls
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: _rank_dsr(r.dsr_by_n.get(self.n_local)))

    def verdict(self, bar: float = VALIDATED_EDGE_BAR) -> tuple[str, str | None, str]:
        """(verdict, best spec id, reason). Pre-registration section 12,
        including BOTH binding overrides."""
        best = self.best_spec()
        if best is None:
            return "NO_REPLAYABLE_SPECS", None, "no non-control spec survived the data floors"

        local = best.dsr_by_n.get(self.n_local)
        conservative_n = max(self.denominators)
        conservative = best.dsr_by_n.get(conservative_n)

        placebo = self.best_spec(controls=True)
        if placebo is not None and local is not None and local >= bar:
            placebo_local = placebo.dsr_by_n.get(self.n_local)
            if placebo_local is not None and placebo_local >= bar:
                return (
                    "DEFINITE_NEGATIVE",
                    best.spec_id,
                    (
                        "PLACEBO OVERRIDE (pre-registration 12(i)): the day-240 control arm clears "
                        f"the same bar (placebo DSR {placebo_local:.4f} at N={self.n_local}), so "
                        "the effect is not attributable to lockup expiration"
                    ),
                )

        if local is None or local < bar:
            return (
                "DEFINITE_NEGATIVE",
                best.spec_id,
                (
                    f"best non-control spec's worse-stream DSR at the most lenient "
                    f"N={self.n_local} is {'None' if local is None else f'{local:.4f}'}, "
                    f"below the {bar} bar"
                ),
            )
        if conservative is None or conservative < bar:
            return (
                "UNRESOLVED",
                best.spec_id,
                (
                    f"worse-stream DSR {local:.4f} clears {bar} at N={self.n_local} but is "
                    f"{'None' if conservative is None else f'{conservative:.4f}'} "
                    f"at N={conservative_n}"
                ),
            )
        return (
            "PASS",
            best.spec_id,
            (
                f"worse-stream DSR {conservative:.4f} clears {bar} even at the most conservative "
                f"N={conservative_n}"
            ),
        )


def build_ipo_lockup_disclosure(panel: IpoLockupPanel) -> dict[str, object]:
    """The honesty block that must travel with any verdict on this family
    (pre-registration section 12(ii))."""
    identity = panel.identity
    with_rows = identity.universe_rows - identity.no_price_rows
    return {
        "survivorship": {
            "universe_rows": identity.universe_rows,
            "rows_with_any_price_data": with_rows,
            "price_availability_rate": (with_rows / identity.universe_rows) if identity.universe_rows else 0.0,
            "direction_of_bias": "UNKNOWN — NOT assumed conservative, NOT assumed flattering",
            "why_unknown": (
                "[FH01] Table III p.481 shows firms whose price had RISEN since the IPO carry a "
                "LARGER negative CAR (-1.7%) than firms whose price had FALLEN (-1.2%), which "
                "establishes that trajectory and CAR magnitude are related but says nothing about "
                "which trajectory characterises the firms this free-data path loses. Establishing "
                "that needs exactly the delisted history the gap makes unavailable "
                "(PENDING_PAID_DATA_DECISIONS.md gap P2)."
            ),
            "consequence": (
                "A PASS or UNRESOLVED verdict on this family is a reason for MORE scrutiny, not "
                "less, and must carry this block in the verdict paragraph itself."
            ),
        },
        "identity": identity.as_dict(),
        "universe": panel.universe_counts.as_dict(),
        "citation": IPO_LOCKUP_CITATION,
        "universe_citation": RITTER_CITATION,
    }


# ===========================================================================
# 10. the entry point
# ===========================================================================

# The per-cohort fetch window, kept identical to fetch_ipo_lockup_data.py's so
# the store's coverage ledger answers every request from disk and the screen
# makes no network call. Six months of lead before the earliest offer date in a
# cohort is what identity gate G2 needs to see an earlier holder of the symbol;
# the far end covers offer + PLACEBO_CALENDAR_DAYS + one trading day.
COHORT_FETCH_START = (-1, 7, 1)
COHORT_FETCH_END = (2, 1, 1)


def load_ipo_lockup_inputs(
    universe: list[IpoRow],
    *,
    provider: object | None = None,
    store: object | None = None,
) -> tuple[dict[str, dict[str, pd.Series]], dict[str, pd.Series], dict[str, pd.Series], pd.Series]:
    """Assemble every price input from the FAMILY-LOCAL price store.

    Returns (adjusted fields per ticker, as-traded close per ticker, EDGE
    half-spread per ticker, benchmark adjusted close).

    Batched by IPO cohort year, with exactly the windows fetch_ipo_lockup_data.py
    recorded, so PriceStore serves everything from disk. A window the store has
    not covered WOULD hit the network — which is why the runner logs the store
    report and why fetch_ipo_lockup_data.py exists as a separate step."""
    from app.services.market_data.price_store import PriceStore
    from app.services.market_data.yfinance_provider import YFinanceProvider

    price_store = store if store is not None else PriceStore(store_dir=PRICE_STORE_DIR)
    data_provider = provider if provider is not None else YFinanceProvider(price_store=price_store)

    by_year: dict[int, list[str]] = {}
    for row in universe:
        by_year.setdefault(row.offer_date.year, []).append(row.ticker)

    adjusted: dict[str, dict[str, pd.Series]] = {}
    half_spread: dict[str, pd.Series] = {}
    for year in sorted(by_year):
        tickers = sorted(set(by_year[year]))
        start = date(year + COHORT_FETCH_START[0], *COHORT_FETCH_START[1:])
        end = date(year + COHORT_FETCH_END[0], *COHORT_FETCH_END[1:])
        frames, missing = data_provider.get_daily_ohlcv(tickers, start, end)
        if not frames:
            logger.info("cohort %d: no price data for any of %d tickers", year, len(tickers))
            continue
        spreads = build_edge_half_spread_frame(
            frames["open"], frames["high"], frames["low"], frames["close"]
        )
        for ticker in frames["close"].columns:
            adjusted[ticker] = {name: frames[name][ticker] for name in ("open", "high", "low", "close", "volume")}
            half_spread[ticker] = spreads[ticker]
        logger.info(
            "cohort %d: %d/%d tickers with price rows", year, len(tickers) - len(missing), len(tickers)
        )

    as_traded: dict[str, pd.Series] = {}
    for ticker in adjusted:
        stored = price_store.read_ticker(ticker)
        if stored is not None and not stored.empty:
            as_traded[ticker] = stored["close"].dropna()

    bench_start = date(UNIVERSE_START_YEAR + COHORT_FETCH_START[0], *COHORT_FETCH_START[1:])
    bench_end = date(UNIVERSE_END_YEAR + COHORT_FETCH_END[0], *COHORT_FETCH_END[1:])
    bench_frame, bench_missing = data_provider.get_price_history(
        [BENCHMARK_TICKER], bench_start, bench_end
    )
    if bench_missing or bench_frame.empty:
        raise ValueError(
            f"benchmark {BENCHMARK_TICKER} returned no rows for {bench_start}..{bench_end}. "
            "Run data/research_runs/fetch_ipo_lockup_data.py first."
        )
    return adjusted, as_traded, half_spread, bench_frame[BENCHMARK_TICKER].dropna()


def run_ipo_lockup_screening(
    *,
    ritter_path: Path | None = None,
    sec_map_path: Path | None = None,
    ticker_info_path: Path | None = None,
    provider: object | None = None,
    store: object | None = None,
    policy: IdentityPolicy = PREREGISTERED_IDENTITY,
) -> IpoLockupSummary:
    """Load, build the panel, screen every cost arm. The one entry point a
    runner calls."""
    rows = load_ritter_universe(ritter_path)
    universe, universe_counts = filter_universe(rows)
    logger.info("universe: %s", universe_counts.as_dict())

    sec_map = load_sec_ticker_map(sec_map_path)
    info_source = ticker_info_path or TICKER_INFO_PATH
    ticker_info = json.loads(info_source.read_text()) if info_source.exists() else {}
    if not ticker_info:
        logger.warning(
            "no ticker_info.json at %s — identity gate G3 will report info_unavailable for every "
            "row. Run data/research_runs/fetch_ipo_lockup_data.py to populate it.",
            info_source,
        )

    adjusted, as_traded, half_spread, benchmark_close = load_ipo_lockup_inputs(
        universe, provider=provider, store=store
    )
    panel = build_event_panel(
        universe,
        adjusted_by_ticker=adjusted,
        as_traded_close_by_ticker=as_traded,
        half_spread_by_ticker=half_spread,
        benchmark_close=benchmark_close,
        sec_map=sec_map,
        ticker_info=ticker_info,
        universe_counts=universe_counts,
        fallback_half_spread=CHEAP_HALF_SPREAD_BPS / 1e4,
        policy=policy,
    )
    logger.info("panel: %d events, identity %s", len(panel.events), panel.identity.as_dict())

    specs = build_family()
    denominators = policy_d_denominators(len(specs))
    results_by_cost_arm = {
        arm.key: screen_ipo_lockup(panel, specs, cost_arm=arm.key, denominators=denominators)
        for arm in COST_ARMS
    }
    return IpoLockupSummary(
        panel=panel,
        specs=specs,
        denominators=denominators,
        n_local=dsr_n_trials(len(specs)),
        results_by_cost_arm=results_by_cost_arm,
        policy=policy,
    )
