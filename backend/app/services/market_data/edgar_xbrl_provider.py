"""SEC EDGAR XBRL company-facts provider: point-in-time ANNUAL financial
statement line items, with explicit per-line-item tag-normalization fallbacks.

Built 2026-08-28 for the quality/profitability cross-sectional families
(cross_sectional_quality.py): cash-based operating profitability (Ball,
Gerakos, Linnainmaa & Nikolaev 2016) and net operating assets (Hirshleifer,
Hou, Teoh & Zhang 2004). Nothing like it existed in this codebase before —
every prior fundamental-ish input (share counts, market caps) came from
yfinance endpoints; this is the project's first primary-source fundamentals
pipeline.

ENDPOINTS — every one verified LIVE 2026-08-28 against the real services,
not recalled from memory:
 * https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json (10-digit
   zero-padded CIK). Fetched live for CIK0000320193 (Apple): the JSON nests
   as {"cik", "entityName", "facts": {taxonomy ("us-gaap"/"dei"): {tag:
   {"label", "description", "units": {unit ("USD"): [{"start"?, "end",
   "val", "accn", "fy", "fp", "form", "filed", "frame"?}, ...]}}}}}.
   Duration facts (income statement) carry "start"+"end"; instant facts
   (balance sheet) carry "end" only. "filed" is the filing's submission
   date — the point-in-time public-availability date this module keys on.
   The endpoint shape is also confirmed by SEC's own API documentation at
   https://www.sec.gov/edgar/sec-api-documentation (fetched live same day),
   which additionally documents companyconcept/, frames/, and a nightly
   bulk ZIP this module deliberately does not use (per-CIK fetches keep the
   download proportional to the sampled universe).
 * https://www.sec.gov/files/company_tickers.json — ticker -> CIK map,
   fetched live 2026-08-28: {"0": {"cik_str": 1045810, "ticker": "NVDA",
   "title": "NVIDIA CORP"}, ...}, 10,388 rows that day. Share classes use
   DASH symbology ("BRK-B", "BF-B") — the same symbology this project's
   membership data uses, verified by lookup of both.
   KNOWN LIMIT, measured not assumed: this file maps CURRENT tickers only.
   A departed index member whose ticker no longer maps (delisted,
   acquired) resolves no CIK here even though its EDGAR filings still
   exist; the caller receives it in the missing-CIK list and must disclose
   the count. (Resolving those needs a historical ticker-CIK mapping this
   project does not have.)

FAIR ACCESS — from SEC's own policy page (https://www.sec.gov/
search-filings/edgar-search-assistance/accessing-edgar-data, fetched live
2026-08-28): "Current max request rate: 10 requests/second", and "Please
declare your user agent in request headers" with the sample format
"Sample Company Name AdminContact@<sample company domain>.com". This module
throttles to EDGAR_MIN_SECONDS_BETWEEN_REQUESTS (~7.7 req/s, deliberately
under the published 10/s) and sends EDGAR_USER_AGENT on every request. The
contact address is env-overridable (SEC_EDGAR_CONTACT) and defaults to a
placeholder; set a real monitored contact before any recurring production
use — SEC's policy expects one.

WHY ANNUAL (10-K) ONLY. Both consuming factors are defined in their source
papers on ANNUAL Compustat data with year-over-year changes; quarterly
mixing would be a different (undeclared) definition. Restricting to forms
10-K/10-K/A also makes the point-in-time story simple and conservative: a
fiscal year's figures become visible at the 10-K's own "filed" date, never
earlier (an earnings 8-K may precede it in reality, so this errs toward
LATE visibility — the safe direction for a backtest).

TAG NORMALIZATION — the real, known problem this module exists to handle.
Different companies/eras tag economically-equivalent line items under
different us-gaap concepts, and one company can switch tags mid-history
(Apple's revenue: SalesRevenueNet through FY2017, Revenues FY2016-18,
RevenueFromContractWithCustomerExcludingAssessedTax from FY2018 — all three
observed in its real companyfacts). The fallback lists below were designed
from a MEASURED probe (2026-08-28) of 14 real companyfacts documents
spanning sectors and eras (AAPL, XOM, JPM, JNJ, WMT, CAT, T, NEE, KO,
NVDA, BA, PG, GE, AMZN), not guessed; each tag's comment records what the
probe observed. Resolution is PER (ticker, fiscal-year): each year takes
the highest-priority tag that actually has a value for that year, so a
mid-history tag switch resolves naturally. Realized tier usage over the
production sample is tallied per line item (LineItemExtraction.tier_usage)
so the consuming family can report real coverage instead of assuming it.

MEASURED COVERAGE on the first production run (2026-08-28, 162 real
companyfacts documents from the point-in-time S&P 500 sample — the full
per-tier breakdown lives in cross_sectional_quality.py's section 5):
every fallback tier below fired on real data. Headlines: the primary tag
carried 100% of assets, 98% of inventory, 87% of accounts payable, 84%
of receivables and 69% of SG&A observations — but only 46% of revenue
(the Revenues/ASC-606/SalesRevenueNet era split is real and large), 52%
of COGS, 31% of short-term debt (69% needed component composites), and
just 3.8% of cash+short-term-investments (96% had to be assembled from
cash plus an STI/marketable-securities tag). A single-canonical-tag
implementation would silently lose roughly half the revenue/COGS panel
and nearly all of the cash panel.
"""

import json
import logging
import os
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

EDGAR_COMPANYFACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
EDGAR_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# SEC's published ceiling is 10 requests/second (see module docstring for the
# live-fetched source). 0.13s between requests is ~7.7/s — deliberately under
# the ceiling rather than at it, because this is a shared public service and
# the difference costs a 200-ticker fetch only a few seconds.
EDGAR_MIN_SECONDS_BETWEEN_REQUESTS = 0.13

# Same shape and register as yfinance_provider._call_with_retry (this
# project's one retry precedent): exponential backoff, jittered, small
# attempt count. EDGAR is an official API but still rate-limits (403s a
# too-fast or undeclared client) and has transient 5xx.
EDGAR_RETRY_ATTEMPTS = 3
EDGAR_RETRY_BASE_DELAY_SECONDS = 1.0

# The declared-bot User-Agent format SEC's policy page shows:
# "Sample Company Name AdminContact@<sample company domain>.com".
# The contact defaults to a PLACEHOLDER and must be overridden (env
# SEC_EDGAR_CONTACT) with a real monitored address before recurring
# production use. Deliberately NOT defaulted to any personal address —
# embedding one in committed code would ship it to every future runner.
EDGAR_CONTACT_ENV_VAR = "SEC_EDGAR_CONTACT"
DEFAULT_EDGAR_CONTACT = "research-placeholder@example.com"

# Annual duration facts: a fiscal year spans 340-380 days (52/53-week fiscal
# calendars produce 357-371-day years — Apple's FY2016 Revenues entry spans
# 2015-09-27..2016-09-24, 364 days, observed live). Transition-period
# stub "years" (fiscal-year-end changes) fall outside and are excluded —
# a 7-month "annual" figure is not a fiscal year.
ANNUAL_FLOW_MIN_DAYS = 340
ANNUAL_FLOW_MAX_DAYS = 380

ANNUAL_FORMS = ("10-K", "10-K/A")

# CROSS-FILING SCALE-CONFLICT GUARD (bug found & fixed 2026-08-28,
# independent verification pass). "Earliest filed wins" assumes every 10-K
# that reports a figure for one period describes the same economic entity.
# A newly-formed holding company breaks that: TechnipFMC's first 10-K
# (filed 2017-01-13, the pre-merger SHELL) reports 2016-12-31 total assets
# = cash = equity = $74,100, while its FY2017 10-K's comparatives for the
# SAME period end report $18.7B / $6.3B / $5.1B — and short/long-term debt
# for 2016 exist ONLY in the later filing, so per-item earliest-filed
# resolution assembled a balance sheet mixing two entities (operating
# assets $100 against operating liabilities of -$2.55B, scaled NOA
# +34,294). When two annual filings disagree about the same (tag, period)
# by more than this ratio, no resolution can be trusted — the period's
# value for that tag is entity-ambiguous and is REFUSED outright (counted
# in LineItemExtraction.n_cross_filing_scale_conflicts), never resolved.
# 100x deliberately matches the quality module's ASSETS_SCALE_BREAK_RATIO
# reasoning: genuine restatements move figures by percents (the largest
# same-period disagreements observed outside entity breaks are low single-
# digit multiples), entity mixes by 3-6 orders of magnitude. A reported
# zero against a large restated value is also a conflict (the ratio is
# unbounded), and refusing it errs toward the papers' own missing->0
# convention for zeroable items rather than toward trusting either figure.
CROSS_FILING_SCALE_CONFLICT_RATIO = 100.0

# Default on-disk cache for raw companyfacts JSON, next to the project's
# other collected data (backend/data/). Git-ignored (see backend/.gitignore):
# raw vendor JSON is refetchable input, not a computed result — computed
# results go to the cross_sectional_trial_results table per this project's
# persistence rule.
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "edgar_companyfacts"


def build_edgar_user_agent() -> str:
    contact = os.environ.get(EDGAR_CONTACT_ENV_VAR, "").strip() or DEFAULT_EDGAR_CONTACT
    return f"Aladdin2 Research {contact}"


@dataclass(frozen=True)
class ResolvedItem:
    """One line item's value for one fiscal-year end, after tag fallback.

    `filed` is when this value first became PUBLIC: the earliest 10-K
    submission date carrying it — for a composite (summed) resolution, the
    LATEST of the parts' own earliest filed dates, since the composite is
    only knowable once every part is. `tag` names the us-gaap tag(s) that
    resolved it ("+"-joined for composites); `tier` is the 0-based fallback
    rule index that fired, so realized coverage per tier is countable."""

    value: float
    filed: date
    tag: str
    tier: int


@dataclass
class LineItemExtraction:
    """extract_line_items' full result for one company: per-item annual
    series, plus the realized tag-coverage tallies the consuming family
    reports (measured coverage, not assumed — this project's standing
    discipline)."""

    items: dict[str, dict[date, ResolvedItem]]
    # item -> Counter keyed "t{tier}:{tag}" — one count per resolved
    # (fiscal-year, item) observation.
    tier_usage: dict[str, Counter] = field(default_factory=dict)
    # Fiscal years where accounts_payable resolved from the COMBINED
    # AccountsPayableAndAccruedLiabilitiesCurrent tag while a separate
    # AccruedLiabilitiesCurrent value also existed: the accrued value is
    # dropped for that year (it is already inside the combined figure) and
    # counted here. A silent double-count would overstate +ΔAccrued in
    # cash-based operating profitability.
    n_ap_accrued_double_count_guard: int = 0
    # (tag, period) values refused because two annual filings disagreed
    # about them by more than CROSS_FILING_SCALE_CONFLICT_RATIO — the
    # entity-ambiguity guard (see that constant). One count per refused
    # (tag, start-or-None, end) triple.
    n_cross_filing_scale_conflicts: int = 0


def _parse_iso(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()  # noqa: DTZ007 — dates only, no tz concept


def extract_annual_tag_series(
    gaap: dict, tag: str, *, kind: str, unit: str = "USD"
) -> dict[date, tuple[float, date]]:
    """{fiscal-year end -> (value, earliest filed date)} for one us-gaap tag,
    from 10-K/10-K/A entries in the given unit.

    kind="flow" (income statement): requires start+end spanning
    ANNUAL_FLOW_MIN/MAX_DAYS — that is what makes an entry a FISCAL YEAR
    figure rather than a quarter or a transition stub.
    kind="instant" (balance sheet): entries without "start". A 10-K carries
    the prior year-end balance sheet as comparatives, so one filing yields
    two year-end observations per instant tag — both kept, each dated by
    its own period end.

    EARLIEST filed wins per period: the first 10-K that published a figure
    is when it became public, and it is the ORIGINALLY-FILED value — a
    later filing's restated comparative for the same period is deliberately
    not preferred, because using restated history would leak information
    into the past."""
    node = gaap.get(tag)
    if not node:
        return {}
    entries = node.get("units", {}).get(unit, [])
    out: dict[date, tuple[float, date]] = {}
    for e in entries:
        if e.get("form") not in ANNUAL_FORMS:
            continue
        val = e.get("val")
        end_s = e.get("end")
        filed_s = e.get("filed")
        if val is None or not end_s or not filed_s or not isinstance(val, (int, float)):
            continue
        if kind == "flow":
            start_s = e.get("start")
            if not start_s:
                continue
            span = (_parse_iso(end_s) - _parse_iso(start_s)).days
            if not (ANNUAL_FLOW_MIN_DAYS <= span <= ANNUAL_FLOW_MAX_DAYS):
                continue
        else:
            if e.get("start"):
                continue  # a duration entry under an instant item is not a balance
        end = _parse_iso(end_s)
        filed = _parse_iso(filed_s)
        prev = out.get(end)
        if prev is None or filed < prev[1]:
            out[end] = (float(val), filed)
    return out


def _resolve_priority(
    gaap: dict, tags: tuple[str, ...], *, kind: str
) -> dict[date, ResolvedItem]:
    """Per fiscal-year end, the highest-priority tag holding a value for
    that year. Resolution is per-YEAR, not per-ticker: a company that
    switched tags mid-history (Apple's revenue did, twice — see module
    docstring) resolves each era under its own tag."""
    series = [extract_annual_tag_series(gaap, t, kind=kind) for t in tags]
    ends: set[date] = set()
    for s in series:
        ends.update(s.keys())
    out: dict[date, ResolvedItem] = {}
    for end in ends:
        for tier, (tag, s) in enumerate(zip(tags, series)):
            if end in s:
                value, filed = s[end]
                out[end] = ResolvedItem(value=value, filed=filed, tag=tag, tier=tier)
                break
    return out


def _sum_parts(
    parts: list[tuple[float, date, str]], tier: int
) -> ResolvedItem:
    """A composite value from >=1 parts: values summed, filed = latest of
    the parts' earliest filed dates (see ResolvedItem.filed)."""
    return ResolvedItem(
        value=float(sum(p[0] for p in parts)),
        filed=max(p[1] for p in parts),
        tag="+".join(p[2] for p in parts),
        tier=tier,
    )


# ---------------------------------------------------------------------------
# Per-line-item fallback resolvers. EVERY tag below earned its place in the
# measured 14-ticker probe of real companyfacts (2026-08-28) described in the
# module docstring; the comment on each records what the probe observed.
# ---------------------------------------------------------------------------

# Revenue (Compustat REVT analogue).
REVENUE_TAGS: tuple[str, ...] = (
    # The ASC 606 standard tag, dominant from FY2018 (8/14 probe tickers,
    # incl. AAPL/AMZN/JNJ from 2017-18 on).
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    # The umbrella tag; 12/14 probe tickers carry it for at least part of
    # their history (BA/CAT/GE/JPM/T span 2007-2025 on it alone).
    "Revenues",
    # The pre-2018 umbrella variant (AAPL/AMZN/CAT/GE/PG/WMT, 2007-2018).
    "SalesRevenueNet",
    # Rare including-assessed-taxes variant (NEE 2018-2025 in the probe) —
    # slightly overstates net revenue by pass-through taxes; last-resort
    # before goods-only.
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    # Goods-only revenue: JNJ 2007-2017 reports revenue ONLY under this tag,
    # so for a goods company it IS total revenue; for a mixed firm it would
    # understate, but every mixed-revenue probe ticker also carries one of
    # the umbrella tags above, which win by priority.
    "SalesRevenueGoodsNet",
)

# COGS (Compustat COGS analogue).
COGS_TAGS_SIMPLE: tuple[str, ...] = (
    # Combined goods+services cost, the modern standard (8/14 probe).
    "CostOfGoodsAndServicesSold",
    # Umbrella "cost of revenue" (BA/CAT/NVDA/T/WMT eras).
    "CostOfRevenue",
)
# BA and GE (probe) report goods and services costs as two SEPARATE tags
# pre-2018; using CostOfGoodsSold alone would understate COGS and overstate
# profitability, so when both exist for a year they are SUMMED (tier 2)
# before falling back to CostOfGoodsSold alone (tier 3).
COGS_GOODS_TAG = "CostOfGoodsSold"
COGS_SERVICES_TAG = "CostOfServices"
COGS_LAST_RESORT_TAG = "CostOfGoodsSoldExcludingDepreciationDepletionAndAmortization"  # T 2013-18

# SG&A. NOTE ON THE PAPER'S (XSGA - XRD): Compustat's XSGA is S&P's OWN
# construction that ADDS R&D into the company's reported SG&A; Ball et al.
# subtract XRD back out precisely "to undo the adjustment that Standard &
# Poor's makes", i.e. to recover REPORTED SG&A (their own words — see
# cross_sectional_quality.py's citation block). us-gaap
# SellingGeneralAndAdministrativeExpense IS the company's reported SG&A —
# R&D is a separate income-statement line under its own tag — so the XBRL
# equivalent of (XSGA - XRD) is this tag used DIRECTLY, with no R&D
# subtraction (subtracting R&D here would remove it twice).
SGA_TAG = "SellingGeneralAndAdministrativeExpense"  # 10/14 probe tickers
# AMZN and BA never tag the combined concept; both tag G&A separately
# (AMZN 2007-2025, BA 2007-2025) and AMZN tags marketing under
# MarketingExpense (2007-2025, observed directly in its companyfacts).
# Composite: G&A + first-available marketing/selling tag, summing the parts
# that exist that year.
SGA_COMPONENT_GA_TAG = "GeneralAndAdministrativeExpense"
SGA_COMPONENT_SELLING_TAGS: tuple[str, ...] = ("SellingAndMarketingExpense", "MarketingExpense")

# Balance-sheet items for the CbOP accrual adjustments and NOA.
RECEIVABLES_TAGS: tuple[str, ...] = (
    "AccountsReceivableNetCurrent",  # 12/14 probe
    "ReceivablesNetCurrent",  # WMT's only receivables tag; GE/XOM eras
)
INVENTORY_TAGS: tuple[str, ...] = (
    "InventoryNet",  # 12/14 probe
    # XOM tags inventory ONLY under this industry concept from 2011 —
    # InventoryNet exists for it in 2010-2011 alone (observed live).
    "InventoryCrudeOilProductsAndMerchandise",
    "InventoryFinishedGoodsNetOfReserves",  # partial-era fallback (CAT/JNJ/KO)
)
PREPAID_TAGS: tuple[str, ...] = (
    "PrepaidExpenseCurrent",  # the clean concept (T, early WMT)
    # 8/14 probe tickers only ever tag prepaid BUNDLED with other current
    # assets. Using it overstates the prepaid LEVEL, but CbOP consumes only
    # the year-over-year CHANGE, where the bundling error largely nets out;
    # still a disclosed approximation, not an exact XPP.
    "PrepaidExpenseAndOtherAssetsCurrent",
)
DEFERRED_REVENUE_CURRENT_TAGS: tuple[str, ...] = (
    "ContractWithCustomerLiabilityCurrent",  # ASC 606 era (8/14 probe)
    "DeferredRevenueCurrent",  # pre-606 era (AAPL/AMZN/NVDA)
)
DEFERRED_REVENUE_NONCURRENT_TAGS: tuple[str, ...] = (
    "ContractWithCustomerLiabilityNoncurrent",
    "DeferredRevenueNoncurrent",
)
ACCOUNTS_PAYABLE_TAGS: tuple[str, ...] = (
    "AccountsPayableCurrent",  # 10/14 probe
    "AccountsPayableTradeCurrent",  # KO/XOM/late GE
    # KO/T/XOM (probe) tag AP only COMBINED with accrued liabilities. When
    # this tier fires, the accrued item is suppressed for that year — see
    # LineItemExtraction.n_ap_accrued_double_count_guard.
    "AccountsPayableAndAccruedLiabilitiesCurrent",
)
ACCRUED_TAGS: tuple[str, ...] = ("AccruedLiabilitiesCurrent",)  # 9/14 probe
ASSETS_TAGS: tuple[str, ...] = ("Assets",)  # 14/14 probe — the one universal tag
# Cash and short-term investments (Compustat CHE analogue) for NOA's
# operating assets.
CASH_STI_COMBINED_TAG = "CashCashEquivalentsAndShortTermInvestments"  # exact CHE analogue
CASH_ONLY_TAG = "CashAndCashEquivalentsAtCarryingValue"  # 14/14 probe
STI_TAGS: tuple[str, ...] = ("ShortTermInvestments", "MarketableSecuritiesCurrent")
# Short-term debt (Compustat DLC analogue) for NOA's operating liabilities.
ST_DEBT_UMBRELLA_TAG = "DebtCurrent"  # the umbrella; 8/14 probe
# When the umbrella is absent: one short-term-borrowings concept plus one
# current-portion-of-LT-debt concept, each the first available of its own
# list. ShortTermBorrowings conventionally CONTAINS commercial paper, so CP
# is a fallback within the same slot, never an addend beside it.
ST_BORROWINGS_TAGS: tuple[str, ...] = (
    "ShortTermBorrowings",
    "CommercialPaper",
    "OtherShortTermBorrowings",
    "NotesPayableCurrent",
)
LTD_CURRENT_TAGS: tuple[str, ...] = (
    "LongTermDebtCurrent",
    "LongTermDebtAndCapitalLeaseObligationsCurrent",
)
# Long-term debt (Compustat DLTT analogue).
LT_DEBT_NONCURRENT_TAGS: tuple[str, ...] = (
    "LongTermDebtNoncurrent",  # 11/14 probe
    "LongTermDebtAndCapitalLeaseObligations",  # BA/GE/XOM/T convention
)
LT_DEBT_TOTAL_TAG = "LongTermDebt"  # includes the current portion — see resolver
MINORITY_TAGS: tuple[str, ...] = ("MinorityInterest",)  # 10/14 probe; missing -> 0 per HHT
PREFERRED_TAGS: tuple[str, ...] = ("PreferredStockValue",)  # sparse; missing -> 0 per HHT
# Common equity (Compustat CEQ analogue): parent stockholders' equity minus
# preferred at carrying value. CAT/JNJ/PG (probe) never tag plain
# StockholdersEquity — only the including-noncontrolling-interests variant,
# from which parent equity is recovered by subtracting minority interest.
SE_PARENT_TAG = "StockholdersEquity"
SE_INCLUDING_NCI_TAG = "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"


def _resolve_cogs(gaap: dict) -> dict[date, ResolvedItem]:
    simple = _resolve_priority(gaap, COGS_TAGS_SIMPLE, kind="flow")
    goods = extract_annual_tag_series(gaap, COGS_GOODS_TAG, kind="flow")
    services = extract_annual_tag_series(gaap, COGS_SERVICES_TAG, kind="flow")
    last = extract_annual_tag_series(gaap, COGS_LAST_RESORT_TAG, kind="flow")
    ends = set(simple) | set(goods) | set(services) | set(last)
    out: dict[date, ResolvedItem] = {}
    for end in ends:
        if end in simple:
            out[end] = simple[end]
        elif end in goods and end in services:
            out[end] = _sum_parts(
                [(*goods[end], COGS_GOODS_TAG), (*services[end], COGS_SERVICES_TAG)], tier=2
            )
        elif end in goods:
            out[end] = ResolvedItem(*goods[end], tag=COGS_GOODS_TAG, tier=3)
        elif end in last:
            out[end] = ResolvedItem(*last[end], tag=COGS_LAST_RESORT_TAG, tier=4)
    return out


def _resolve_sga(gaap: dict) -> dict[date, ResolvedItem]:
    combined = extract_annual_tag_series(gaap, SGA_TAG, kind="flow")
    ga = extract_annual_tag_series(gaap, SGA_COMPONENT_GA_TAG, kind="flow")
    selling = [
        (t, extract_annual_tag_series(gaap, t, kind="flow")) for t in SGA_COMPONENT_SELLING_TAGS
    ]
    ends = set(combined) | set(ga)
    for _, s in selling:
        ends |= set(s)
    out: dict[date, ResolvedItem] = {}
    for end in ends:
        if end in combined:
            out[end] = ResolvedItem(*combined[end], tag=SGA_TAG, tier=0)
            continue
        parts: list[tuple[float, date, str]] = []
        if end in ga:
            parts.append((*ga[end], SGA_COMPONENT_GA_TAG))
        for tag, s in selling:
            if end in s:
                parts.append((*s[end], tag))
                break  # one selling/marketing concept only — they overlap
        if parts:
            out[end] = _sum_parts(parts, tier=1)
    return out


def _resolve_deferred_revenue(gaap: dict) -> dict[date, ResolvedItem]:
    """Current + noncurrent deferred revenue (DRC + DRLT in the paper's
    Compustat terms), each side resolved by its own era priority
    (ContractWithCustomerLiability* post-ASC-606, DeferredRevenue* before),
    missing side treated as 0 — but at least one side must exist, else the
    item is absent for that year (which the factor treats as a no-change
    account per the paper's missing->0 convention)."""
    cur = _resolve_priority(gaap, DEFERRED_REVENUE_CURRENT_TAGS, kind="instant")
    non = _resolve_priority(gaap, DEFERRED_REVENUE_NONCURRENT_TAGS, kind="instant")
    out: dict[date, ResolvedItem] = {}
    for end in set(cur) | set(non):
        parts = [
            (r.value, r.filed, r.tag) for r in (cur.get(end), non.get(end)) if r is not None
        ]
        tier = max(r.tier for r in (cur.get(end), non.get(end)) if r is not None)
        out[end] = _sum_parts(parts, tier=tier)
    return out


def _resolve_cash_sti(gaap: dict) -> dict[date, ResolvedItem]:
    combined = extract_annual_tag_series(gaap, CASH_STI_COMBINED_TAG, kind="instant")
    cash = extract_annual_tag_series(gaap, CASH_ONLY_TAG, kind="instant")
    sti = [(t, extract_annual_tag_series(gaap, t, kind="instant")) for t in STI_TAGS]
    ends = set(combined) | set(cash)
    out: dict[date, ResolvedItem] = {}
    for end in ends:
        if end in combined:
            out[end] = ResolvedItem(*combined[end], tag=CASH_STI_COMBINED_TAG, tier=0)
            continue
        if end not in cash:
            continue
        parts = [(*cash[end], CASH_ONLY_TAG)]
        for tag, s in sti:
            if end in s:
                parts.append((*s[end], tag))
                break  # ShortTermInvestments and MarketableSecuritiesCurrent overlap
        out[end] = _sum_parts(parts, tier=1)
    return out


def _resolve_st_debt(gaap: dict) -> dict[date, ResolvedItem]:
    umbrella = extract_annual_tag_series(gaap, ST_DEBT_UMBRELLA_TAG, kind="instant")
    borrow = _resolve_priority(gaap, ST_BORROWINGS_TAGS, kind="instant")
    ltd_cur = _resolve_priority(gaap, LTD_CURRENT_TAGS, kind="instant")
    ends = set(umbrella) | set(borrow) | set(ltd_cur)
    out: dict[date, ResolvedItem] = {}
    for end in ends:
        if end in umbrella:
            out[end] = ResolvedItem(*umbrella[end], tag=ST_DEBT_UMBRELLA_TAG, tier=0)
            continue
        parts: list[tuple[float, date, str]] = []
        for r in (borrow.get(end), ltd_cur.get(end)):
            if r is not None:
                parts.append((r.value, r.filed, r.tag))
        if parts:
            out[end] = _sum_parts(parts, tier=1)
    return out


def _resolve_lt_debt(gaap: dict) -> dict[date, ResolvedItem]:
    noncur = _resolve_priority(gaap, LT_DEBT_NONCURRENT_TAGS, kind="instant")
    total = extract_annual_tag_series(gaap, LT_DEBT_TOTAL_TAG, kind="instant")
    ltd_cur = _resolve_priority(gaap, LTD_CURRENT_TAGS, kind="instant")
    ends = set(noncur) | set(total)
    out: dict[date, ResolvedItem] = {}
    for end in ends:
        if end in noncur:
            out[end] = noncur[end]
            continue
        # LongTermDebt includes the current portion; subtract it back out
        # when it is separately known so the current portion is not counted
        # in BOTH st_debt and lt_debt. When it is not separately known the
        # total is used as-is (tier 3) — that overstates lt_debt by the
        # current portion, which UNDERSTATES NOA's operating liabilities;
        # disclosed via the tier tally rather than silently accepted.
        value, filed = total[end]
        cur = ltd_cur.get(end)
        if cur is not None:
            out[end] = ResolvedItem(
                value=value - cur.value,
                filed=max(filed, cur.filed),
                tag=f"{LT_DEBT_TOTAL_TAG}-{cur.tag}",
                tier=2,
            )
        else:
            out[end] = ResolvedItem(value=value, filed=filed, tag=LT_DEBT_TOTAL_TAG, tier=3)
    return out


def _resolve_common_equity(gaap: dict) -> dict[date, ResolvedItem]:
    """Compustat CEQ analogue: parent stockholders' equity minus preferred
    stock at carrying value (0 when untagged). When only the
    including-noncontrolling-interests total is tagged (CAT/JNJ/PG in the
    probe), parent equity is recovered by subtracting minority interest (0
    when untagged — for these filers NCI is then genuinely inside the
    figure and NOA's OL is understated by it; the tier tally discloses how
    often)."""
    parent = extract_annual_tag_series(gaap, SE_PARENT_TAG, kind="instant")
    incl = extract_annual_tag_series(gaap, SE_INCLUDING_NCI_TAG, kind="instant")
    pref = _resolve_priority(gaap, PREFERRED_TAGS, kind="instant")
    minority = _resolve_priority(gaap, MINORITY_TAGS, kind="instant")
    out: dict[date, ResolvedItem] = {}
    for end in set(parent) | set(incl):
        p = pref.get(end)
        pref_value = p.value if p is not None else 0.0
        if end in parent:
            value, filed = parent[end]
            filed = max(filed, p.filed) if p is not None else filed
            out[end] = ResolvedItem(
                value=value - pref_value,
                filed=filed,
                tag=SE_PARENT_TAG if p is None else f"{SE_PARENT_TAG}-{p.tag}",
                tier=0,
            )
        else:
            value, filed = incl[end]
            m = minority.get(end)
            minority_value = m.value if m is not None else 0.0
            for r in (p, m):
                if r is not None:
                    filed = max(filed, r.filed)
            out[end] = ResolvedItem(
                value=value - minority_value - pref_value,
                filed=filed,
                tag=SE_INCLUDING_NCI_TAG,
                tier=1,
            )
    return out


# The line items extract_line_items produces, with how each resolves.
# Callable resolvers own the composite arithmetic; tuple entries are plain
# priority lists.
_ITEM_RESOLVERS: dict[str, Callable[[dict], dict[date, ResolvedItem]]] = {
    "revenue": lambda g: _resolve_priority(g, REVENUE_TAGS, kind="flow"),
    "cogs": _resolve_cogs,
    "sga": _resolve_sga,
    "receivables": lambda g: _resolve_priority(g, RECEIVABLES_TAGS, kind="instant"),
    "inventory": lambda g: _resolve_priority(g, INVENTORY_TAGS, kind="instant"),
    "prepaid": lambda g: _resolve_priority(g, PREPAID_TAGS, kind="instant"),
    "deferred_revenue": _resolve_deferred_revenue,
    "accounts_payable": lambda g: _resolve_priority(g, ACCOUNTS_PAYABLE_TAGS, kind="instant"),
    "accrued_expenses": lambda g: _resolve_priority(g, ACCRUED_TAGS, kind="instant"),
    "assets": lambda g: _resolve_priority(g, ASSETS_TAGS, kind="instant"),
    "cash_and_short_term_investments": _resolve_cash_sti,
    "short_term_debt": _resolve_st_debt,
    "long_term_debt": _resolve_lt_debt,
    "minority_interest": lambda g: _resolve_priority(g, MINORITY_TAGS, kind="instant"),
    "preferred_stock": lambda g: _resolve_priority(g, PREFERRED_TAGS, kind="instant"),
    "common_equity": _resolve_common_equity,
}

LINE_ITEMS: tuple[str, ...] = tuple(_ITEM_RESOLVERS)

AP_COMBINED_TAG = "AccountsPayableAndAccruedLiabilitiesCurrent"


def _find_cross_filing_scale_conflicts(gaap: dict) -> set[tuple[str, str | None, str]]:
    """Every (tag, start-or-None, end) whose annual-form USD values across
    ALL filings disagree by more than CROSS_FILING_SCALE_CONFLICT_RATIO —
    the entity-ambiguity pre-scan (see that constant's comment for the real
    TechnipFMC case). Flows are grouped per (start, end) and instants per
    (None, end), so a fiscal year reported by consecutive 10-Ks (original +
    next year's comparative, values differing by restatement percents)
    never trips it."""
    conflicts: set[tuple[str, str | None, str]] = set()
    for tag, node in gaap.items():
        by_period: dict[tuple[str | None, str], list[float]] = {}
        for e in node.get("units", {}).get("USD", []):
            if e.get("form") not in ANNUAL_FORMS:
                continue
            val = e.get("val")
            end = e.get("end")
            if val is None or not end or not isinstance(val, (int, float)):
                continue
            by_period.setdefault((e.get("start"), end), []).append(abs(float(val)))
        for (start, end), magnitudes in by_period.items():
            hi, lo = max(magnitudes), min(magnitudes)
            if hi > 0.0 and (lo == 0.0 or hi / lo > CROSS_FILING_SCALE_CONFLICT_RATIO):
                conflicts.add((tag, start, end))
    return conflicts


def _drop_conflicted_periods(
    gaap: dict, conflicts: set[tuple[str, str | None, str]]
) -> dict:
    """gaap with every conflicted (tag, period)'s entries removed, leaving
    everything else untouched (the original dict is never mutated)."""
    if not conflicts:
        return gaap
    conflicted_tags = {t for t, _, _ in conflicts}
    out = dict(gaap)
    for tag in conflicted_tags:
        node = gaap.get(tag)
        if not node:
            continue
        periods = {(s, e) for t, s, e in conflicts if t == tag}
        units = {
            unit: [e for e in entries if (e.get("start"), e.get("end")) not in periods]
            for unit, entries in node.get("units", {}).items()
        }
        out[tag] = {**node, "units": units}
    return out


def extract_line_items(company_facts: dict) -> LineItemExtraction:
    """All of LINE_ITEMS for one company from its raw companyfacts JSON,
    resolved through the measured fallback lists above, with realized tier
    usage tallied per item.

    Takes the raw JSON dict (not a provider instance) so it is directly
    unit-testable against hand-built companyfacts-shaped fixtures with no
    network — the same contract build_point_in_time_share_counts keeps for
    the same reason."""
    gaap = company_facts.get("facts", {}).get("us-gaap", {})
    conflicts = _find_cross_filing_scale_conflicts(gaap)
    gaap = _drop_conflicted_periods(gaap, conflicts)
    items: dict[str, dict[date, ResolvedItem]] = {}
    tier_usage: dict[str, Counter] = {}
    for item, resolver in _ITEM_RESOLVERS.items():
        resolved = resolver(gaap)
        items[item] = resolved
        counter: Counter = Counter()
        for r in resolved.values():
            counter[f"t{r.tier}:{r.tag}"] += 1
        tier_usage[item] = counter

    # The AP/accrued double-count guard (see LineItemExtraction).
    n_guard = 0
    ap = items["accounts_payable"]
    accrued = items["accrued_expenses"]
    for end, r in ap.items():
        if r.tag == AP_COMBINED_TAG and end in accrued:
            del accrued[end]
            n_guard += 1

    return LineItemExtraction(
        items=items,
        tier_usage=tier_usage,
        n_ap_accrued_double_count_guard=n_guard,
        n_cross_filing_scale_conflicts=len(conflicts),
    )


class EdgarFetchError(RuntimeError):
    pass


class EdgarXbrlProvider:
    """Rate-limited, retrying, disk-caching fetcher for the two live-verified
    EDGAR endpoints in the module docstring.

    `sleep` and `clock` are injectable so tests can drive the throttle
    without real waiting — the same reason yfinance_provider._call_with_retry
    resolves time.sleep at call time rather than binding it."""

    def __init__(
        self,
        cache_dir: Path | str | None = DEFAULT_CACHE_DIR,
        user_agent: str | None = None,
        min_request_interval: float = EDGAR_MIN_SECONDS_BETWEEN_REQUESTS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        client: httpx.Client | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.min_request_interval = min_request_interval
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        headers = {
            "User-Agent": user_agent if user_agent is not None else build_edgar_user_agent(),
            "Accept-Encoding": "gzip, deflate",
        }
        self._client = client if client is not None else httpx.Client(
            headers=headers, timeout=60.0, follow_redirects=True
        )

    def _throttle(self) -> None:
        if self._last_request_at is not None:
            elapsed = self._clock() - self._last_request_at
            remaining = self.min_request_interval - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def _get_json(self, url: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, EDGAR_RETRY_ATTEMPTS + 1):
            self._throttle()
            try:
                resp = self._client.get(url)
                if resp.status_code == 404:
                    # A real answer (no XBRL facts for this CIK), not a
                    # transient failure — retrying cannot change it.
                    raise EdgarFetchError(f"404 for {url}")
                resp.raise_for_status()
                return resp.json()
            except EdgarFetchError:
                raise
            except Exception as exc:  # noqa: BLE001 — transient network/5xx/403; last attempt re-raises below
                last_error = exc
                if attempt < EDGAR_RETRY_ATTEMPTS:
                    self._sleep(EDGAR_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        raise EdgarFetchError(f"failed after {EDGAR_RETRY_ATTEMPTS} attempts: {url}") from last_error

    def get_ticker_cik_map(self) -> dict[str, int]:
        """Ticker -> CIK from SEC's company_tickers.json (dash symbology,
        current tickers only — see the module docstring's measured KNOWN
        LIMIT about departed members). Disk-cached alongside the
        companyfacts JSONs; delete the cache file to force a refresh."""
        cache_path = self.cache_dir / "company_tickers.json" if self.cache_dir else None
        if cache_path is not None and cache_path.exists():
            raw = json.loads(cache_path.read_text())
        else:
            raw = self._get_json(EDGAR_COMPANY_TICKERS_URL)
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(raw))
        return {row["ticker"]: int(row["cik_str"]) for row in raw.values()}

    def get_company_facts(self, cik: int) -> dict:
        """One company's full companyfacts JSON, disk-cached by CIK."""
        cache_path = self.cache_dir / f"CIK{cik:010d}.json" if self.cache_dir else None
        if cache_path is not None and cache_path.exists():
            return json.loads(cache_path.read_text())
        data = self._get_json(EDGAR_COMPANYFACTS_URL_TEMPLATE.format(cik=cik))
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data))
        return data

    def fetch_line_items_for_tickers(
        self, tickers: list[str]
    ) -> tuple[dict[str, LineItemExtraction], list[str], list[str]]:
        """The pipeline entry point: (extractions by ticker, tickers with no
        CIK in SEC's current map, tickers whose fetch failed). Both failure
        lists are part of the RESULT, not log lines — the consuming family
        reports them, per this project's universe-accounting discipline."""
        cik_map = self.get_ticker_cik_map()
        extractions: dict[str, LineItemExtraction] = {}
        missing_cik: list[str] = []
        failed: list[str] = []
        for ticker in tickers:
            cik = cik_map.get(ticker)
            if cik is None:
                missing_cik.append(ticker)
                continue
            try:
                facts = self.get_company_facts(cik)
            except EdgarFetchError as exc:
                logger.warning("EDGAR companyfacts fetch failed for %s: %s", ticker, exc)
                failed.append(ticker)
                continue
            extractions[ticker] = extract_line_items(facts)
        return extractions, sorted(missing_cik), sorted(failed)
