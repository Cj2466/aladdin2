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
   KNOWN LIMIT 1, measured not assumed: this file maps CURRENT tickers
   only. A departed index member whose ticker no longer maps (delisted,
   acquired) resolves no CIK here even though its EDGAR filings still
   exist; the caller receives it in the missing-CIK list and must disclose
   the count. (Resolving those needs a historical ticker-CIK mapping this
   project does not have.)
   KNOWN LIMIT 2, measured live 2026-09-02 and the reason the
   SUCCESSOR-SHELL RESOLUTION block below exists: this file maps a ticker
   to whichever registrant currently CARRIES it, which after a holding-
   company reorganization is the newly-registered successor and NOT the
   entity holding the operating history. XOM resolved to CIK 2115436
   ("ExxonMobil Holdings Corp", 29 filings, all from 2026-07-01, zero
   10-Ks) rather than CIK 34088 ("EXXON MOBIL CORP", 3,554 filings back to
   1994, 10-Ks through 2026-02-18).
   WHAT THE FIX DOES NOT CLOSE, stated as a dated expectation rather than
   left as a surprise: it recovers the predecessor only while the
   successor has NO annual facts of its own. Once ExxonMobil Holdings
   files its first 10-K (expected around February 2027) the trigger stops
   firing and XOM's history truncates to that single year. Closing that
   needs a MERGE of predecessor and successor facts, whose trigger cannot
   be "zero annual facts" — and the measured population gives no basis
   for the threshold such a rule would need, so it is recorded here
   rather than guessed at now.

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
import re
import tempfile
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

# --- SIC (industry classification) endpoints, added 2026-08-28 for the
# industry-neutral NOA family (cross_sectional_quality_neutral.py). Both
# verified LIVE that day, not recalled from memory:
#  * https://data.sec.gov/submissions/CIK##########.json carries the
#    company's CURRENT SEC-assigned SIC code ("sic": "6798",
#    "sicDescription": "Real Estate Investment Trusts") — current-day ONLY,
#    with no history (verified on CIK0001020569/Iron Mountain, which reads
#    6798 today).
#  * Every archived filing's full-submission text file
#    (https://www.sec.gov/Archives/edgar/data/{cik}/{accession-no-dashes}/
#    {accession}.txt) begins with a static SGML header recording the SIC
#    EDGAR had on file AT DISSEMINATION TIME:
#    "STANDARD INDUSTRIAL CLASSIFICATION:\tPUBLIC WAREHOUSING & STORAGE
#    [4220]". These are point-in-time archives, NOT regenerated: Iron
#    Mountain's 10-Ks filed 2013/2014/2015 all read 4220 (warehousing)
#    while its 2016 10-K reads 6798 (REIT) — the real classification
#    change around its REIT conversion, preserved in place (all four
#    fetched live 2026-08-28). This is what makes free point-in-time SIC
#    possible at all: the submissions API alone would project today's
#    classification onto the whole past.
#    The server honors HTTP Range requests (verified live: bytes=0-2500
#    returned only the header region), so reading a filing's SIC never
#    downloads the filing itself — a 10-K's full text runs to tens of MB;
#    its header fits in the first few KB. _get_text_prefix below also
#    hard-caps how much of the body it will read, so a server that ignored
#    Range would still cost only SIC_HEADER_PREFIX_BYTES per filing.
EDGAR_SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_FILING_TEXT_URL_TEMPLATE = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{accession}.txt"
)

# How much of a filing's full-submission text to read when extracting the
# SGML header's SIC. The header (accession, form type, FILER blocks with
# COMPANY DATA) precedes the first document; 16KB covers every observed
# header with a wide margin (the IRM headers above fit in <2.5KB) while
# still being ~0.01% of a typical 10-K's full text.
SIC_HEADER_PREFIX_BYTES = 16_384

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


# --- point-in-time SIC extraction (see the SIC endpoints block above) -------

# "STANDARD INDUSTRIAL CLASSIFICATION:  <description> [4220]" — the code is
# always the bracketed 4-digit group at the end of the line.
_SIC_HEADER_LINE_RE = re.compile(
    r"STANDARD INDUSTRIAL CLASSIFICATION:[^\[\r\n]*\[(\d{4})\]"
)
_CIK_HEADER_LINE_RE = re.compile(r"CENTRAL INDEX KEY:\s*(\d+)")


def parse_filing_header_sic(header_text: str, cik: int) -> int | None:
    """The SIC code the SGML header of one archived filing records for the
    given CIK, or None when the fetched header region carries none.

    A filing can name several entities (co-registrant FILER blocks, and —
    structurally identical in the header grammar — SUBJECT COMPANY /
    FILED BY blocks on other form types), each with its own COMPANY DATA
    including its own SIC. Scanning line-by-line and keeping the SIC that
    follows the requested CIK's own CENTRAL INDEX KEY line attributes the
    classification to the right entity; when no SIC is attributable to the
    requested CIK (some very old headers order fields differently), the
    first SIC in the header is the fallback — for a single-filer 10-K,
    which is every filing this project reads headers from, the two are the
    same thing."""
    current_cik: int | None = None
    matched: int | None = None
    first: int | None = None
    for line in header_text.splitlines():
        cik_match = _CIK_HEADER_LINE_RE.search(line)
        if cik_match:
            current_cik = int(cik_match.group(1))
            continue
        sic_match = _SIC_HEADER_LINE_RE.search(line)
        if sic_match:
            code = int(sic_match.group(1))
            if first is None:
                first = code
            if current_cik == cik and matched is None:
                matched = code
    return matched if matched is not None else first


@dataclass
class SicHistory:
    """One company's point-in-time industry-classification record: the SIC
    code EDGAR had on file at each annual (10-K/10-K/A) filing date, plus
    today's classification from the submissions API.

    `events` is [(filed date, header SIC or None)] sorted by filed date —
    one entry per annual accession whose header was successfully fetched,
    None when the fetched header carried no parseable SIC line. The
    CONSUMER decides what to do about Nones and about disagreement between
    header history and `current_sic`; this record just reports both
    honestly (the point-in-time-correctness reasoning lives with the
    consuming family, cross_sectional_quality_neutral.py)."""

    cik: int
    events: list[tuple[date, int | None]] = field(default_factory=list)
    current_sic: int | None = None
    # Annual accessions whose header fetch failed outright after retries
    # (network/5xx) — NOT headers that fetched fine but had no SIC line
    # (those are (filed, None) events above).
    n_header_fetch_failures: int = 0


# ---------------------------------------------------------------------------
# SUCCESSOR-SHELL CIK RESOLUTION (bug found 2026-09-01 by an independent
# verifier re-deriving coverage counts during the asset_growth build; root
# cause confirmed live against SEC's own endpoints 2026-09-02).
#
# THE REAL CASE. Exxon completed a holding-company reorganization on
# 2026-07-01 (its successor-issuer 8-K12B is dated that day). SEC's
# company_tickers.json then moved ticker XOM onto the SUCCESSOR, CIK
# 2115436 "ExxonMobil Holdings Corp" — 29 filings, all from 2026-07-01, one
# 10-Q and ZERO 10-Ks — while the whole operating history stayed on CIK
# 34088 "EXXON MOBIL CORP" (3,554 filings from 1994, 10-Ks through
# 2026-02-18). Because this module reads ANNUAL_FORMS only, the resolved CIK
# yielded nothing for every line item in every year, and a top-10 S&P 500
# constituent vanished from every cross-sectional formation. It did not even
# reach the missing-CIK list: the ticker resolved, the fetch returned 200,
# and extract_line_items simply returned empty dicts. NOTHING recorded it.
#
# WHY THE TRIGGER IS "ZERO ANNUAL FACTS" AND NOT A HISTORY-DEPTH THRESHOLD.
# Measured over all 162 companyfacts documents of the 2026-08-28 production
# run: exactly TWO carry zero 10-K/10-K/A facts — Sea Limited (a foreign
# private issuer that files 20-F, so it genuinely has no annual facts here)
# and the Exxon shell. The next-shallowest documents hold 4, 5, 5, 7, 7, 8,
# 9 and 10 distinct annual fiscal years (Paramount Skydance, GE Vernova,
# QNITY, GE HealthCare, Bunge Global, Robinhood, DoorDash, Otis — every one
# a genuine recent spin-off or IPO that SHOULD rank on the history it has),
# against a median of 20. Zero therefore sits in a real measured gap in this
# population, exactly the way ASSETS_SCALE_BREAK_RATIO's 100x sits in the
# gap between 11x and 10,135x. A "must have multi-decade history" rule would
# instead refuse eight legitimate names to catch one, and its threshold
# would be invented rather than measured. Zero is also the only condition
# under which the redirect is RISK-FREE: the resolved CIK contributes
# literally no annual observation, so replacing it cannot displace data.
#
# HOW THE PREDECESSOR IS FOUND, without inventing a mapping. A companyfacts
# document records the accession number of every fact, and an accession
# number's first block is the CIK it was filed under. 269 of the Exxon
# shell's 274 facts carry accession prefix 0000034088 — the real Exxon
# filed them. That candidate costs ZERO extra requests to discover, because
# the document is already downloaded.
#
# WHY THAT SIGNAL IS GATED RATHER THAN TRUSTED. Measured on the same 162
# documents: 150 of them contain facts filed under some other CIK, because
# filing AGENTS (RR Donnelley 1193125, Toppan 1144204/1140361, Workiva
# 1628280) issue accession numbers. A foreign prefix is therefore evidence
# of nothing on its own. A candidate is accepted only if it passes BOTH
# gates below, and refused otherwise:
#   (1) its own companyfacts carries at least one annual fact — filing
#       agents fail this outright (1193125, 1144204 and 1140361 all return
#       HTTP 404 from the companyfacts endpoint, verified live 2026-09-02);
#   (2) its entityName equals the resolved document's entityName after
#       case/punctuation normalization. Exxon passes because BOTH documents
#       read "Exxon Mobil Corporation" — the shell's name comes from facts
#       the predecessor filed, which is the same fact that makes the
#       accession prefix meaningful.
# Refusal is the safe direction and is what Sea Limited gets: a wrongly
# refused ticker is reported and excluded (the pre-existing behaviour),
# while a wrongly accepted one would silently corrupt a panel.
#
# WHAT IS DELIBERATELY NOT DONE HERE, and why:
#  * No hand-maintained {"XOM": 34088} override table. It would fix exactly
#    one ticker, would not have caught this case before a human noticed it,
#    and would need a new entry for every future reorganization — whereas
#    the condition that actually matters ("this CIK yields no annual data")
#    is directly measurable from data already on disk.
#  * No SEC file-number linkage. It looks authoritative and is wrong here:
#    the successor's filings carry file number 001-43384, not Exxon's
#    001-02256 (verified live 2026-09-02).
#  * No MERGE of predecessor and successor facts. Today the successor has
#    no annual facts at all, so a redirect and a merge are the same thing
#    for this pipeline. Once the successor files its OWN first 10-K the
#    trigger stops firing and XOM's history truncates to that one year —
#    a REAL, DATED future hole, recorded in KNOWN LIMITS rather than
#    papered over with a threshold this population gives no basis for.
# ---------------------------------------------------------------------------

# How many distinct filer CIKs from a fundamentals-empty document may be
# probed before giving up. Ordered by fact count, so the entity that filed
# the bulk of the document is always tried first. The cap bounds the cost
# of a document like Sea Limited's, whose three foreign prefixes are all
# filing agents and all 404: three wasted requests, once, then never again
# for that CIK within the run.
MAX_PREDECESSOR_CANDIDATES = 3

# An accession number is "0000034088-26-000093": the filer CIK, the year,
# then a sequence number.
_ACCESSION_RE = re.compile(r"^(\d{10})-\d{2}-\d{6}$")

_ENTITY_NAME_NOISE_RE = re.compile(r"[^a-z0-9]+")


def normalize_entity_name(name: object) -> str:
    """An entityName reduced to lowercase alphanumerics, so
    "Exxon Mobil Corporation" and "EXXON MOBIL CORP." compare equal.

    Corporate SUFFIXES are deliberately NOT stripped. Dropping
    Corp/Inc/Holdings/Group would make "Acme Holdings" and "Acme Group"
    compare equal, and this comparison is the only gate standing between a
    coincidental accession prefix and a silently wrong filing history. The
    real case needs no stripping anyway: both Exxon documents literally
    read "Exxon Mobil Corporation"."""
    if not isinstance(name, str):
        return ""
    return _ENTITY_NAME_NOISE_RE.sub("", name.lower())


def count_annual_facts(company_facts: dict) -> int:
    """How many 10-K/10-K/A observations a companyfacts document carries,
    across every taxonomy and unit. Zero means this CIK can contribute
    nothing to an annual pipeline — see the block above."""
    total = 0
    for tags in company_facts.get("facts", {}).values():
        if not isinstance(tags, dict):
            continue
        for node in tags.values():
            for entries in node.get("units", {}).values():
                total += sum(1 for e in entries if e.get("form") in ANNUAL_FORMS)
    return total


def annual_accessions_from_facts(company_facts: dict) -> dict[str, date]:
    """{accession number -> earliest 'filed' date} for every 10-K/10-K/A in
    one companyfacts document. Split out of
    EdgarXbrlProvider.get_annual_accessions so the successor-shell redirect
    can hand it the PREDECESSOR's already-fetched document instead of
    re-resolving, and so it is unit-testable with no provider at all."""
    accessions: dict[str, date] = {}
    for node in company_facts.get("facts", {}).get("us-gaap", {}).values():
        for entries in node.get("units", {}).values():
            for e in entries:
                if e.get("form") not in ANNUAL_FORMS:
                    continue
                accn = e.get("accn")
                filed_s = e.get("filed")
                if not accn or not filed_s:
                    continue
                filed = _parse_iso(filed_s)
                prev = accessions.get(accn)
                if prev is None or filed < prev:
                    accessions[accn] = filed
    return accessions


def filer_cik_counts(company_facts: dict) -> Counter:
    """CIK -> how many of this document's facts were filed under an
    accession number issued to it. Malformed accessions are ignored rather
    than guessed at."""
    counts: Counter = Counter()
    for tags in company_facts.get("facts", {}).values():
        if not isinstance(tags, dict):
            continue
        for node in tags.values():
            for entries in node.get("units", {}).values():
                for e in entries:
                    match = _ACCESSION_RE.match(str(e.get("accn", "")))
                    if match:
                        counts[int(match.group(1))] += 1
    return counts


@dataclass(frozen=True)
class CikRedirect:
    """One ticker's CIK redirected from a fundamentals-empty successor shell
    to the validated predecessor that holds the annual filing history."""

    resolved_cik: int
    filing_cik: int
    entity_name: str
    n_annual_facts: int


@dataclass
class CikResolutionReport:
    """Every successor-shell decision this provider made, kept as RESULT
    data rather than log lines — the same contract fetch_line_items_for_
    tickers keeps for its missing-CIK and failed-fetch lists, and for the
    same reason: the silence is what made the XOM bug survive four days of
    live formations and a full production run. A consuming family reads
    this and discloses it.

    `redirects` is keyed by the CIK SEC's ticker map resolved;
    `without_annual_history` holds the CIKs that carried no annual facts
    and for which no candidate passed both gates (their entityName is kept
    so the report names a company, not just a number)."""

    redirects: dict[int, CikRedirect] = field(default_factory=dict)
    without_annual_history: dict[int, str] = field(default_factory=dict)

    def describe(self) -> str:
        """One human-readable line per decision, for a family's `warnings`
        list. Empty string when nothing happened, so a caller can test it
        directly."""
        lines = [
            f"CIK {r.resolved_cik} ({r.entity_name}) carries no 10-K history; "
            f"redirected to CIK {r.filing_cik}, which filed most of its facts and "
            f"carries {r.n_annual_facts} annual observations under the same entity name"
            for r in sorted(self.redirects.values(), key=lambda r: r.resolved_cik)
        ]
        lines += [
            f"CIK {cik} ({name or 'unnamed'}) carries no 10-K history and no candidate "
            "predecessor CIK passed validation; it contributes no fundamentals"
            for cik, name in sorted(self.without_annual_history.items())
        ]
        return "; ".join(lines)


class EdgarFetchError(RuntimeError):
    pass


class EdgarXbrlProvider:
    """Rate-limited, retrying, disk-caching fetcher for the two live-verified
    EDGAR endpoints in the module docstring.

    `sleep` and `clock` are injectable so tests can drive the throttle
    without real waiting — the same reason yfinance_provider._call_with_retry
    resolves time.sleep at call time rather than binding it.

    `max_cache_age_days` bounds how long the two MUTABLE disk caches
    (companyfacts and the ticker->CIK map) may be served without refetching.
    It defaults to None — no bound, the behavior that existed before this
    parameter — so every backtest, screening run and test that ever ran
    against this provider keeps reading exactly the bytes it read before,
    which is the reproducibility contract those runs' persisted numbers
    depend on.

    IT EXISTS FOR THE LIVE FORWARD-VALIDATION PATH, which has the opposite
    requirement: cross_sectional_forward_registry's quality adapters rebuild
    their panel every real day, and an unbounded companyfacts cache would
    freeze each firm's fundamentals at whatever was on disk when the
    registration started. A firm's next 10-K would then never enter the
    panel, and once its cached value aged past
    cross_sectional_quality.FUNDAMENTAL_MAX_STALENESS_DAYS the name would
    silently drop out of the ranked cross-section altogether — a live track
    record degrading for a caching reason rather than a market one, which is
    exactly the corruption a forward clock must not tolerate.

    ONLY THOSE TWO CACHES ARE BOUNDED, deliberately. filing_sic/ is keyed on
    an ACCESSION NUMBER — an immutable archived document whose SGML header
    can never change — so refetching it could only ever return the same
    bytes; submissions_sic/ holds a current-day classification used solely
    as the whole-history fallback for companies whose headers never carried
    a SIC (see cross_sectional_quality_neutral section 3), where a day-old
    answer cannot change a bucket that a filing header would have decided."""

    def __init__(
        self,
        cache_dir: Path | str | None = DEFAULT_CACHE_DIR,
        user_agent: str | None = None,
        min_request_interval: float = EDGAR_MIN_SECONDS_BETWEEN_REQUESTS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        client: httpx.Client | None = None,
        max_cache_age_days: int | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.min_request_interval = min_request_interval
        self.max_cache_age_days = max_cache_age_days
        # Accumulated across every resolve_company_facts call on this
        # provider, so one fetch pass's decisions are all readable at the
        # end of it (see CikResolutionReport).
        self.cik_resolution = CikResolutionReport()
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

    def _cache_is_usable(self, cache_path: Path) -> bool:
        """Whether a MUTABLE cache file may be served without refetching.

        True whenever it exists and no age bound is configured (the default
        — see __init__), which is what keeps this provider byte-identical
        for every existing caller. With a bound set, a file whose mtime is
        older than it is treated as absent, so the next read refetches and
        rewrites it. An unreadable mtime is treated as EXPIRED rather than
        fresh: refetching costs one request, while wrongly serving a frozen
        document costs a forward registration its data."""
        if not cache_path.exists():
            return False
        if self.max_cache_age_days is None:
            return True
        try:
            age_seconds = time.time() - cache_path.stat().st_mtime
        except OSError:
            return False
        return age_seconds <= self.max_cache_age_days * 86_400

    @staticmethod
    def _write_cache_atomically(cache_path: Path, payload: str) -> None:
        """Publish a cache file so a concurrent reader can only ever see the
        WHOLE old file or the WHOLE new one — never a half-written middle.

        WHY THIS IS NOT PARANOIA HERE. Before max_cache_age_days existed,
        every one of these files was written exactly once and then only ever
        read (`if cache_path.exists()`), so no two callers could ever be at
        the same path at the same time. A bound changes that: the two quality
        families' live panels BOTH rebuild on the first tick of each UTC day,
        and CrossSectionalForwardValidationRunner._tick runs families
        CONCURRENTLY (asyncio.gather over asyncio.to_thread), walking the same
        ~165 CIKs at the same pace. Path.write_text truncates and then streams
        a ~4 MB document through an 8 KB buffer, so the other family's read of
        that same path lands mid-write and json.loads raises — measured, not
        theorised: a torn read reproduced on the first attempt at realistic
        document size. A JSONDecodeError is not an EdgarFetchError, so nothing
        downstream absorbs it and that family loses the tick.

        os.replace is atomic on POSIX and Windows when both paths are on one
        filesystem, which is why the temp file is created in the destination's
        OWN directory rather than in /tmp."""
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=cache_path.parent, suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(payload)
            os.replace(tmp_path, cache_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    def get_ticker_cik_map(self) -> dict[str, int]:
        """Ticker -> CIK from SEC's company_tickers.json (dash symbology,
        current tickers only — see the module docstring's measured KNOWN
        LIMIT about departed members). Disk-cached alongside the
        companyfacts JSONs; delete the cache file to force a refresh, or
        construct the provider with max_cache_age_days to bound it."""
        cache_path = self.cache_dir / "company_tickers.json" if self.cache_dir else None
        if cache_path is not None and self._cache_is_usable(cache_path):
            raw = json.loads(cache_path.read_text())
        else:
            raw = self._get_json(EDGAR_COMPANY_TICKERS_URL)
            if cache_path is not None:
                self._write_cache_atomically(cache_path, json.dumps(raw))
        return {row["ticker"]: int(row["cik_str"]) for row in raw.values()}

    def get_company_facts(self, cik: int) -> dict:
        """One company's full companyfacts JSON, disk-cached by CIK. The
        document GROWS with every new filing, so a caller that needs it to
        stay current (the live forward-validation path) must construct the
        provider with max_cache_age_days — see the class docstring."""
        cache_path = self.cache_dir / f"CIK{cik:010d}.json" if self.cache_dir else None
        if cache_path is not None and self._cache_is_usable(cache_path):
            return json.loads(cache_path.read_text())
        data = self._get_json(EDGAR_COMPANYFACTS_URL_TEMPLATE.format(cik=cik))
        if cache_path is not None:
            self._write_cache_atomically(cache_path, json.dumps(data))
        return data

    def resolve_company_facts(self, cik: int) -> tuple[int, dict]:
        """(the CIK whose ANNUAL filing history this company's fundamentals
        actually live under, that CIK's companyfacts document).

        Normally the identity: the resolved CIK has annual facts and is
        returned as-is, at no extra cost. When it has NONE — the
        successor-shell case measured in the block above the provider — the
        predecessor that filed the bulk of its facts is probed and accepted
        only if it passes both gates there. Every outcome, redirect or
        refusal, is recorded on self.cik_resolution.

        A candidate whose fetch FAILS is simply a candidate that did not
        pass gate (1) — it never fails the ticker. EdgarFetchError still
        propagates for the resolved CIK's own fetch, and for an
        already-accepted predecessor's (whose document the caller is by
        then depending on), so both reach the callers' failed-fetch lists
        exactly as an ordinary fetch failure always has."""
        facts = self.get_company_facts(cik)
        if count_annual_facts(facts) > 0:
            return cik, facts

        # BOTH outcomes are remembered, so the candidate probe runs at most
        # once per CIK per provider. That matters on the refusal side too:
        # every fetch entry point resolves the same CIK independently (the
        # NOA-neutral path calls both of them), and a name like Sea Limited
        # — whose three candidates are filing agents that 404 — would
        # otherwise re-spend three requests against SEC's shared public
        # service, and re-log the same warning, on every pass.
        known = self.cik_resolution.redirects.get(cik)
        if known is not None:
            return known.filing_cik, self.get_company_facts(known.filing_cik)
        if cik in self.cik_resolution.without_annual_history:
            return cik, facts

        entity_name = facts.get("entityName")
        normalized = normalize_entity_name(entity_name)
        candidates = [
            candidate
            for candidate, _ in filer_cik_counts(facts).most_common()
            if candidate != cik
        ][:MAX_PREDECESSOR_CANDIDATES]
        for candidate in candidates:
            try:
                candidate_facts = self.get_company_facts(candidate)
            except EdgarFetchError:
                continue  # gate (1): filing agents have no companyfacts at all
            n_annual = count_annual_facts(candidate_facts)
            if n_annual == 0:
                continue  # gate (1): no annual history to inherit
            if not normalized or normalize_entity_name(
                candidate_facts.get("entityName")
            ) != normalized:
                continue  # gate (2): a different company, whoever filed it
            redirect = CikRedirect(
                resolved_cik=cik,
                filing_cik=candidate,
                entity_name=str(entity_name or ""),
                n_annual_facts=n_annual,
            )
            self.cik_resolution.redirects[cik] = redirect
            logger.warning(
                "EDGAR CIK %d (%s) carries no 10-K history; using CIK %d, which filed "
                "most of its facts and carries %d annual observations under the same "
                "entity name",
                cik,
                entity_name,
                candidate,
                n_annual,
            )
            return candidate, candidate_facts

        self.cik_resolution.without_annual_history[cik] = str(entity_name or "")
        logger.warning(
            "EDGAR CIK %d (%s) carries no 10-K history and no candidate predecessor "
            "CIK passed validation; it will contribute no fundamentals",
            cik,
            entity_name,
        )
        return cik, facts

    def _get_text_prefix(self, url: str, max_bytes: int) -> str:
        """The first max_bytes of a text resource, throttled and retried
        exactly like _get_json. Sends an HTTP Range header (honored by
        www.sec.gov, verified live 2026-08-28) AND stops reading the
        response stream at max_bytes regardless — so a server that ignored
        Range would still cost only max_bytes of transfer, never a whole
        multi-MB filing."""
        last_error: Exception | None = None
        for attempt in range(1, EDGAR_RETRY_ATTEMPTS + 1):
            self._throttle()
            try:
                with self._client.stream(
                    "GET", url, headers={"Range": f"bytes=0-{max_bytes - 1}"}
                ) as resp:
                    if resp.status_code == 404:
                        raise EdgarFetchError(f"404 for {url}")
                    resp.raise_for_status()
                    chunks: list[bytes] = []
                    received = 0
                    for chunk in resp.iter_bytes():
                        chunks.append(chunk)
                        received += len(chunk)
                        if received >= max_bytes:
                            break
                return b"".join(chunks)[:max_bytes].decode("utf-8", errors="replace")
            except EdgarFetchError:
                raise
            except Exception as exc:  # noqa: BLE001 — transient network/5xx/403; last attempt re-raises below
                last_error = exc
                if attempt < EDGAR_RETRY_ATTEMPTS:
                    self._sleep(EDGAR_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        raise EdgarFetchError(f"failed after {EDGAR_RETRY_ATTEMPTS} attempts: {url}") from last_error

    def get_annual_accessions(self, cik: int) -> dict[str, date]:
        """{accession number -> earliest 'filed' date} for every 10-K/10-K/A
        observed anywhere in the company's (disk-cached) companyfacts JSON.
        The accession list is read from companyfacts rather than the
        submissions API deliberately: it is exactly the set of filings the
        NOA panel's own values came from, so the SIC step series built on
        it is keyed to the same filing events as the factor it buckets —
        and the companyfacts document is already on disk from the factor
        fetch, costing zero additional requests.

        Goes through resolve_company_facts, so a successor shell yields its
        PREDECESSOR's accessions — the same document the line items come
        from, which is what keeps the SIC series keyed to the same filing
        events as the factor."""
        _filing_cik, facts = self.resolve_company_facts(cik)
        return annual_accessions_from_facts(facts)

    def get_filing_header_sic(self, cik: int, accession: str) -> int | None:
        """The SIC code the archived SGML header of one filing records for
        this CIK (see the SIC endpoints block in the module docstring for
        why headers are the point-in-time source). Disk-cached per company
        (filing_sic/CIK##########.json: {accession: sic-or-null}); a
        successfully-fetched header with no SIC line caches null so it is
        never refetched, while a FAILED fetch caches nothing and raises."""
        cache_path = (
            self.cache_dir / "filing_sic" / f"CIK{cik:010d}.json" if self.cache_dir else None
        )
        cached: dict[str, int | None] = {}
        if cache_path is not None and cache_path.exists():
            cached = json.loads(cache_path.read_text())
            if accession in cached:
                return cached[accession]
        url = EDGAR_FILING_TEXT_URL_TEMPLATE.format(
            cik=cik, accession_nodash=accession.replace("-", ""), accession=accession
        )
        text = self._get_text_prefix(url, SIC_HEADER_PREFIX_BYTES)
        sic = parse_filing_header_sic(text, cik)
        if cache_path is not None:
            cached[accession] = sic
            self._write_cache_atomically(cache_path, json.dumps(cached))
        return sic

    def get_current_sic(self, cik: int) -> int | None:
        """The company's CURRENT SEC-assigned SIC from the submissions API
        — today's classification only, no history (see the SIC endpoints
        block). Only the parsed code is disk-cached (submissions_sic/), not
        the ~1MB submissions document it came from."""
        cache_path = (
            self.cache_dir / "submissions_sic" / f"CIK{cik:010d}.json" if self.cache_dir else None
        )
        if cache_path is not None and cache_path.exists():
            value = json.loads(cache_path.read_text()).get("sic")
            return int(value) if value is not None else None
        data = self._get_json(EDGAR_SUBMISSIONS_URL_TEMPLATE.format(cik=cik))
        raw = str(data.get("sic") or "").strip()
        sic = int(raw) if raw.isdigit() else None
        if cache_path is not None:
            self._write_cache_atomically(cache_path, json.dumps({"sic": sic}))
        return sic

    def fetch_sic_history_for_tickers(
        self, tickers: list[str]
    ) -> tuple[dict[str, SicHistory], list[str], list[str]]:
        """Point-in-time SIC history for each ticker: (histories by ticker,
        tickers with no CIK in SEC's current map, tickers whose companyfacts
        fetch failed so no accession list exists). Per-accession header
        failures do NOT fail the ticker — they are counted on its own
        SicHistory (n_header_fetch_failures) and that filing date simply
        contributes no classification event; a failed current-SIC fetch
        likewise leaves current_sic None rather than failing the ticker.
        Same result-not-log-line contract as fetch_line_items_for_tickers."""
        cik_map = self.get_ticker_cik_map()
        histories: dict[str, SicHistory] = {}
        missing_cik: list[str] = []
        failed: list[str] = []
        for ticker in tickers:
            cik = cik_map.get(ticker)
            if cik is None:
                missing_cik.append(ticker)
                continue
            try:
                # The successor-shell redirect has to happen HERE, not just
                # on the accession list: an archived filing lives under the
                # CIK that filed it, so a shell's CIK in the Archives URL
                # would 404 on its predecessor's every 10-K.
                filing_cik, facts = self.resolve_company_facts(cik)
            except EdgarFetchError as exc:
                logger.warning("EDGAR companyfacts fetch failed for %s: %s", ticker, exc)
                failed.append(ticker)
                continue
            accessions = annual_accessions_from_facts(facts)
            history = SicHistory(cik=filing_cik)
            for accession, filed in sorted(accessions.items(), key=lambda kv: (kv[1], kv[0])):
                try:
                    sic = self.get_filing_header_sic(filing_cik, accession)
                except EdgarFetchError as exc:
                    logger.warning(
                        "EDGAR filing header fetch failed for %s %s: %s", ticker, accession, exc
                    )
                    history.n_header_fetch_failures += 1
                    continue
                history.events.append((filed, sic))
            try:
                history.current_sic = self.get_current_sic(filing_cik)
            except EdgarFetchError as exc:
                logger.warning("EDGAR submissions fetch failed for %s: %s", ticker, exc)
            histories[ticker] = history
        return histories, sorted(missing_cik), sorted(failed)

    def fetch_line_items_for_tickers(
        self, tickers: list[str]
    ) -> tuple[dict[str, LineItemExtraction], list[str], list[str]]:
        """The pipeline entry point: (extractions by ticker, tickers with no
        CIK in SEC's current map, tickers whose fetch failed). Both failure
        lists are part of the RESULT, not log lines — the consuming family
        reports them, per this project's universe-accounting discipline.
        A THIRD accounting surface, self.cik_resolution, records every
        successor-shell redirect and every CIK left with no annual history
        (see CikResolutionReport); it is on the provider rather than in this
        tuple so the return contract every existing caller unpacks stays
        exactly three elements."""
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
                _filing_cik, facts = self.resolve_company_facts(cik)
            except EdgarFetchError as exc:
                logger.warning("EDGAR companyfacts fetch failed for %s: %s", ticker, exc)
                failed.append(ticker)
                continue
            extractions[ticker] = extract_line_items(facts)
        return extractions, sorted(missing_cik), sorted(failed)
