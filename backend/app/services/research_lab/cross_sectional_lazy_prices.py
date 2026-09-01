"""Lazy Prices: rank firms by how much their 10-K LANGUAGE changed versus
their own immediately-prior 10-K. Long the non-changers, short the changers.

THE FIRST TEXT/NLP FAMILY IN THIS CODEBASE. Every other family here ranks on
a numeric series — a return, a financial ratio, a funding rate. This one ranks
on the cosine/Jaccard similarity of two English documents. The portfolio
machinery is therefore reused entirely unchanged (cross_sectional.
run_cross_sectional_backtest does every replay), and all the new risk lives in
the text pipeline, which is why that pipeline was built and validated against
real filings BEFORE the spec grid was frozen. See
data/research_runs/lazy_prices_2026-09-01_preregistration.txt section 3 for
what that validation found, including two real defects it caught.

============================================================================
THE SOURCE — VERIFIED, WITH THE HEADLINE FIGURE CORRECTED
============================================================================
 [CMN20] Lauren Cohen, Christopher Malloy & Quoc Nguyen, "Lazy Prices", THE
         JOURNAL OF FINANCE 75(3), 2020, pp. 1371-1415, doi:10.1111/jofi.12885;
         also NBER Working Paper 25084 (Sept 2018, rev. March 2019).

PROVENANCE, and it matters: the NBER working paper PDF was fetched from
nber.org and text-extracted IN FULL on 2026-09-01, and every quote below is
from that extracted document, not from training memory. The published Journal
of Finance text was NOT retrieved (Wiley returns HTTP 403); the bibliographic
record was confirmed independently at RePEc and the AFA issue listing. Treat
every quote as NBER w25084, which is known to differ from the published
abstract.

TWO CORRECTIONS TO THE FIGURE THIS FAMILY WAS BRIEFED WITH, both material:

 1. "188 basis points per month (over 22% per year)" is REAL BUT IS NOT THE
    BASE CASE. It is an "up to", EQUALLY-WEIGHTED, RISK-FACTORS-SECTION-ONLY
    number. The paper's own stated headline, verbatim from its introduction:
    "Our key finding is that a portfolio that goes long 'non-changers' and
    short 'changers' earns a statistically significant 34-58 basis points per
    month — up to 7% per year (t=3.59) - in value-weighted abnormal returns
    over the following year." Quoting 22%/yr as this strategy's expected
    return would misrepresent the source.
 2. MD&A IS WHERE CHANGES CONCENTRATE, NOT WHERE THE RETURNS ARE. Verbatim:
    "We show that firms' reporting changes are concentrated in the management
    discussion (MD&A) section... However, in terms of return-rich content, we
    find that while changes in MD&A section wording do predict large and
    significant abnormal returns, changes in text in the Risk Factors section
    are even more informative for stock returns." MD&A's own effect is
    "ranging between 11-22 basis per month", explicitly smaller than Legal
    Proceedings, Item 7a and "particularly the 'Risk Factors' section".
    So the PRE-REGISTERED ordering across this family's scope axis is
    risk_factors > full > mda.

THE MECHANISM'S OWN EVIDENCE, verbatim: "we find an economically and
statistically zero announcement day return... in the full sample", and "Their
stock prices exhibit little to no reaction at the time of public filing by the
firm, even though there is a robust and systematic relationship... with the
information only being impounded into price in the future." The returns
"continue to accrue out to 18 months, and do not reverse." That no-reaction-
at-filing / reaction-later shape is what distinguishes genuine inattention
(nobody is diffing filings against their predecessors) from a market that
already knows and does not care.

[CMN20] uses FOUR similarity measures — Sim_Cosine, Sim_Jaccard, Sim_MinEdit,
Sim_Simple. This module implements the first two. Sim_MinEdit is minimum edit
distance, which is quadratic in document length and would dominate the run at
~30,000 tokens per document; Sim_Simple is defined in the paper as running
Microsoft Word's Track Changes or Unix diff, which is not a reproducible
library primitive. Both absences are declared deviations, not oversights.

============================================================================
THE HONEST PRIOR IS WEAK, FOR FOUR NAMED REASONS
============================================================================
 1. UNIVERSE MISMATCH, the big one. [CMN20] runs on the COMPLETE universe of
    U.S. filers — thousands of mostly small, thinly-covered firms, exactly
    where an INATTENTION anomaly should live. This family runs on S&P 500
    members: the most intensively analyzed securities in existence, each
    covered by dozens of analysts paid to read these documents.
 2. POST-PUBLICATION ATTENUATION. The paper's sample ends 2014; it circulated
    from 2018 and was published in 2020. This family's sample is 2015-2026,
    almost entirely after the paper was widely read, and filing-diff products
    are now commercially sold.
 3. ANNUAL-ONLY SIGNAL. [CMN20] uses 10-K AND 10-Q, refreshing roughly
    quarterly. This family uses 10-K only, refreshing annually — strictly less
    information (see FORMS below).
 4. WEIGHTING MISMATCH. The paper's 34-58bp headline is VALUE-weighted; this
    family weights equal and inverse-vol, because point-in-time market cap
    would need a share-count pipeline this family does not build.

An honest negative is the expected outcome and is a complete result.

============================================================================
POINT-IN-TIME AVAILABILITY — THE SAFETY-CRITICAL PART
============================================================================
A filing's similarity may be used only from its real EDGAR availability date
(edgar_filing_text_provider.availability_date: acceptanceDateTime converted
UTC -> US/Eastern, with an at/after-16:00-ET shift to the next day). It is
NEVER keyed to reportDate, the fiscal period end.

MEASURED on 481 real 10-Ks from 20 S&P 500 companies (2026-09-01):
availability_date minus report_date has MEDIAN 53 DAYS and MAXIMUM 107 DAYS.
Keying the signal to the period end would let a backtest read, on the fiscal
year-end date, language that did not exist for another ~53 days. Also
measured: 244 of those 481 (51%) are accepted at/after 16:00 ET, so the
after-close shift is material rather than cosmetic.

The panel is a FORWARD-FILLED STEP FRAME on the price index, visible from the
availability date, never interpolated, never backfilled, and bounded by
LAZY_PRICES_MAX_STALENESS_DAYS. Formation-time look-ahead is then structurally
impossible: the harness truncates the history view to rows <= the formation
date before signal_lazy_prices ever sees it.

SAME-TYPE PAIRING is enforced in pair_same_type_filings: a 10-K is compared
only to that firm's previous 10-K. Comparing a 10-K to a 10-Q would produce an
enormous spurious "change" for every firm, correlated with the filing calendar
rather than with news — a real bug class, and one this module has a dedicated
test for on deliberately mixed input.

FORMS: 10-K ONLY in production. The provider and the pairing logic both handle
10-Q (which is what gives the same-type test its teeth), but screening it would
roughly quadruple the EDGAR document footprint and 10-Q risk-factor sections
are typically a one-line "no material changes" cross-reference rather than a
comparable body of text.

============================================================================
TOKENIZATION — TWO CHOICES DECIDED BY MEASUREMENT, NOT ASSUMPTION
============================================================================
 * STOPWORDS ARE REMOVED. Measured over 20 real consecutive 10-K pairs, raw
   term-frequency cosine on whole documents ranged 0.9965-0.9998 — a spread of
   0.0033, dominated by function words identical in every filing. That is the
   boilerplate-dilution failure in the flesh. Removing a standard English
   stopword list widens the spread ~11x, to 0.9676-0.9976. Jaccard, being
   set-based, is unaffected either way (0.775-0.959).
   RESIDUAL, DISCLOSED: whole-document cosine still sits near 1.0, so the
   cross-sectional ordering is carried by small differences. The run report
   must show realized dispersion per scope/metric so a reader can judge
   whether a spec ranks on signal or on parse noise.
 * NUMBERS ARE DROPPED (tokens are runs of >= 2 ASCII letters). Every filing's
   figures change every year mechanically; the hypothesis is about LANGUAGE.

TF-IDF IS DELIBERATELY NOT USED, and this is a point-in-time decision rather
than a stylistic one. An IDF vector fitted over the sample corpus embeds
information from EVERY document in it — including filings from the future of
any given formation date — into that date's score. That is look-ahead by
construction. Pairwise cosine on raw counts needs no corpus and cannot leak.

============================================================================
WHY THIS MODULE RUNS ITS OWN SCREENING LOOP
============================================================================
screen_cross_sectional_universe computes sigma_sr — the multiple-comparisons
dispersion feeding the DSR — from the specs in ONE pass. This family's 36
specs span SIX different signal panels (2 metrics x 3 scopes), and
CrossSectionalData carries exactly one fundamental_signal frame, so it would
take six passes of six specs each.

That would be WRONG IN THE ANTI-CONSERVATIVE DIRECTION. The six specs sharing
a panel differ only in holding period and leg weighting, so their Sharpes are
highly correlated and their dispersion UNDERSTATES the dispersion across the
full 36 (which spans metrics and scopes). A smaller sigma_sr means a smaller
expected-max-under-noise benchmark, which makes every DSR EASIER to pass.

So screen_lazy_prices_family below replays each spec with the harness's own
run_cross_sectional_backtest — every line of real replay logic is the
harness's, unchanged — and only the AGGREGATION is local: all 36 Sharpes are
pooled, sigma_sr is their ddof=1 std, and n_trials is the pre-declared 36.
This is the same relationship cross_sectional_pead.screen_pead_family has to
the harness, for the same kind of structural reason.
"""

import itertools
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.market_data.edgar_filing_text_provider import (
    EdgarFilingTextProvider,
    FilingIndexReport,
    FilingRef,
    availability_date,
    extract_section,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional import (
    BASIS_WEIGHTED_MODES,
    MIN_REPLAY_TRADING_DAYS,
    CrossSectionalBacktestResult,
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalScreeningResult,
    CrossSectionalSpec,
    MembershipFn,
    run_cross_sectional_backtest,
)
from app.services.research_lab.cross_sectional_quality import (
    FactorObservation,
    build_point_in_time_factor_frame,
)
from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_over,
)
from app.services.research_lab.spread_estimator import build_edge_half_spread_frame

logger = logging.getLogger(__name__)

LAZY_PRICES_FAMILY_NAME = "lazy_prices"
LAZY_PRICES_CITATION = (
    "Cohen, Malloy & Nguyen, 'Lazy Prices' (Journal of Finance 75(3), 2020, pp. 1371-1415; "
    "NBER Working Paper 25084)"
)

# --- the family's fixed axes (frozen in the pre-registration) --------------

# [CMN20]'s Sim_Cosine and Sim_Jaccard. Sim_MinEdit and Sim_Simple are
# declared deviations — see the module docstring.
LAZY_PRICES_METRICS: tuple[str, ...] = ("cosine", "jaccard")

# "full" is the paper's own base case (its 34-58bp headline is whole-10-K);
# "risk_factors" is the section it finds most return-informative (the 188bp
# cell); "mda" is where changes concentrate but returns are weakest (11-22bp).
LAZY_PRICES_SCOPES: tuple[str, ...] = ("full", "risk_factors", "mda")

# ~1, 3 and 6 months, inside the horizon over which [CMN20] says the returns
# "continue to accrue out to 18 months".
LAZY_PRICES_HOLDING_DAYS: tuple[int, ...] = (21, 63, 126)

# The two non-signal weighting modes available without a share-count
# pipeline. "magnitude" is deliberately excluded: it weights by signal
# strength, and a similarity bounded just below 1.0 carries essentially no
# magnitude information, so a magnitude-weighted leg would be equal-weighting
# wearing another name.
LAZY_PRICES_LEG_WEIGHTINGS: tuple[str, ...] = ("equal", "inverse_vol")

# 2 x 3 x 3 x 2, asserted against the built list in _build_lazy_prices_family
# so a size drift is a loud import-time failure rather than a silent change to
# every future run's DSR denominator.
LAZY_PRICES_N_TRIALS = (
    len(LAZY_PRICES_METRICS)
    * len(LAZY_PRICES_SCOPES)
    * len(LAZY_PRICES_HOLDING_DAYS)
    * len(LAZY_PRICES_LEG_WEIGHTINGS)
)

# --- fixed design constants (NOT axes) -------------------------------------

# Quintiles — [CMN20]'s own sort.
LAZY_PRICES_RANK_FRACTION = 0.20

# One annual refresh cycle plus the SEC's own 60-90 day 10-K filing window.
# Reuses cross_sectional_quality.FUNDAMENTAL_MAX_STALENESS_DAYS' value and its
# reasoning unchanged: a firm whose next 10-K is later than this has stopped
# filing on schedule, and carrying a year-old similarity as "current" would be
# a dead-series masquerade.
LAZY_PRICES_MAX_STALENESS_DAYS = 455

LAZY_PRICES_FORMS: tuple[str, ...] = ("10-K",)

# The signal reads exactly one row (the formation date's step value), so one
# row of declared lookback is all the price frame owes it — history depth
# lives in the FILING data. Same reasoning as
# cross_sectional_quality.QUALITY_SIGNAL_LOOKBACK_ROWS.
LAZY_PRICES_SIGNAL_LOOKBACK_ROWS = 1

# Trailing window for the inverse-vol basis: the same 63-trading-day /
# 40-observation convention as the sibling families, restated rather than
# imported for the reason cross_sectional_index_removal gives (the sibling's
# function bakes in its own window constants).
LAZY_PRICES_VOL_WINDOW_DAYS = 63
LAZY_PRICES_VOL_MIN_PERIODS = 40

# Calendar days of filing history fetched before the formation start, so the
# first formation already has a similarity (which needs a filing AND its
# predecessor, i.e. roughly two annual cycles).
LAZY_PRICES_FILING_WARMUP_DAYS = 900

DEFAULT_FILING_INDEX_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "lazy_prices_filing_index.json"
)

# --- tokenization ----------------------------------------------------------

# Runs of >= 2 ASCII letters — the frozen definition, exactly as
# pre-registered. No digit is ever part of a token, which is what drops the
# mechanical year-over-year churn of every figure, date and cross-reference
# number in the filing ("$1,234.5 million in 2025" -> ["million"]).
#
# PRECISELY, because a test caught the loose wording: a MIXED token is SPLIT,
# not discarded — "FY2024" yields "fy", and "COVID-19" yields "covid". That is
# harmless and arguably right: the surviving letter run is the same in both
# filings of a pair ("FY2024" vs "FY2025" both give "fy"), so it contributes a
# constant to the comparison rather than spurious change, while the digits that
# genuinely differ are gone.
_TOKEN_RE = re.compile(r"[a-z]{2,}")

# A standard English stopword list. Removed because measurement said so, not
# taste: with these words in, whole-document cosine over 20 real consecutive
# 10-K pairs spanned 0.9965-0.9998; with them out, 0.9676-0.9976 (~11x the
# spread). See the module docstring.
_STOPWORD_SOURCE = """
    about above after again against all also am an and any are aren as at be because been
    before being below between both but by can cannot could couldn did didn do does doesn
    doing don down during each few for from further had hadn has hasn have haven having he
    her here hers herself him himself his how if in into is isn it its itself let may me
    more most must mustn my myself no nor not of off on once only or other ought our ours
    ourselves out over own same shall shan she should shouldn so some such than that the
    their theirs them themselves then there these they this those through to too under
    until up upon very was wasn we were weren what when where which while who whom why
    will with won would wouldn you your yours yourself yourselves
"""
STOPWORDS: frozenset[str] = frozenset(_STOPWORD_SOURCE.split())


def tokenize(text: str) -> list[str]:
    """Lowercased alphabetic tokens with stopwords removed — the frozen
    tokenization of the pre-registration's section 4.

    A pure string function so it is directly unit-testable against hand-built
    fixtures with no network, the same contract every parsing primitive in
    edgar_filing_text_provider keeps."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def term_counts(text: str) -> Counter:
    return Counter(tokenize(text))


def cosine_similarity(a: Counter, b: Counter) -> float:
    """[CMN20]'s Sim_Cosine: the cosine of the angle between the two documents'
    RAW TERM-COUNT vectors.

    Deliberately not TF-IDF weighted — an IDF fitted over the sample corpus
    would embed future documents into a past formation's score (module
    docstring). NaN when either document is empty, which the panel builder
    treats as "no observation" rather than as a similarity of zero: an
    unparseable filing is missing data, and calling it maximally changed would
    put every parse failure straight into the short leg."""
    if not a or not b:
        return float("nan")
    common = set(a) & set(b)
    dot = float(sum(a[t] * b[t] for t in common))
    norm_a = float(np.sqrt(sum(v * v for v in a.values())))
    norm_b = float(np.sqrt(sum(v * v for v in b.values())))
    if norm_a <= 0.0 or norm_b <= 0.0:
        return float("nan")
    return dot / (norm_a * norm_b)


def jaccard_similarity(a: Counter, b: Counter) -> float:
    """[CMN20]'s Sim_Jaccard: |A INTERSECT B| / |A UNION B| over the two
    documents' term SETS (counts ignored — that is what makes it insensitive
    to the function-word frequency mass that flattens cosine)."""
    set_a, set_b = set(a), set(b)
    if not set_a or not set_b:
        return float("nan")
    union = len(set_a | set_b)
    if union == 0:
        return float("nan")
    return len(set_a & set_b) / union


_METRIC_FUNCTIONS = {"cosine": cosine_similarity, "jaccard": jaccard_similarity}


def similarity(a: Counter, b: Counter, metric: str) -> float:
    if metric not in _METRIC_FUNCTIONS:
        raise ValueError(
            f"unknown similarity metric {metric!r}; this family declares {LAZY_PRICES_METRICS}"
        )
    return _METRIC_FUNCTIONS[metric](a, b)


# --- pairing ---------------------------------------------------------------


def pair_same_type_filings(
    filings: list[FilingRef],
) -> list[tuple[FilingRef, FilingRef]]:
    """[(previous, current)] consecutive pairs OF THE SAME FORM TYPE, ordered
    by filing date.

    THIS FUNCTION IS THE SAME-TYPE GUARD, and the guard is the point. A 10-K
    compared to a 10-Q would score a huge spurious "language change" for every
    firm — an annual report and a quarterly report differ enormously in length
    and content for reasons that have nothing to do with news — and that
    spurious change would be correlated with the filing calendar rather than
    with anything about the company. Pairing is therefore done WITHIN each
    form's own chronological sequence and never across sequences.

    A firm's first filing of a given type has no predecessor and yields no
    pair, which is correct: there is nothing to have changed from."""
    by_form: dict[str, list[FilingRef]] = {}
    for filing in sorted(filings, key=lambda f: (f.filing_date, f.accession)):
        by_form.setdefault(filing.form, []).append(filing)
    pairs: list[tuple[FilingRef, FilingRef]] = []
    for sequence in by_form.values():
        pairs.extend(itertools.pairwise(sequence))
    pairs.sort(key=lambda p: (p[1].filing_date, p[1].accession))
    return pairs


# --- similarity observations ------------------------------------------------


@dataclass
class SimilarityBuildReport:
    """What the text pass actually managed, per scope — required output, not a
    log line. Section extraction genuinely fails on some filers (GE's
    integrated report matches neither heading pattern), and that failure is
    NOT random across firms, so a section-scope spec ranks a differently
    composed cross-section than the full-document one. Callers must report
    these numbers rather than assume coverage."""

    n_tickers: int = 0
    n_filings: int = 0
    n_pairs: int = 0
    n_text_fetch_failures: int = 0
    # scope -> count of pairs that yielded a usable similarity
    n_pairs_scored: dict[str, int] = field(default_factory=dict)
    # scope -> count of pairs dropped because a section could not be located
    # in one or both filings
    n_pairs_section_missing: dict[str, int] = field(default_factory=dict)


def scope_text(text: str, scope: str) -> str | None:
    """The portion of a filing a given scope ranks on: the whole document, or
    one extracted section. None when the section could not be located — a
    first-class 'no observation', never an empty string that would silently
    score as maximally changed."""
    if scope == "full":
        return text
    if scope in ("risk_factors", "mda"):
        return extract_section(text, scope)
    raise ValueError(f"unknown scope {scope!r}; this family declares {LAZY_PRICES_SCOPES}")


def _scope_counters(
    provider: EdgarFilingTextProvider,
    ticker: str,
    filing: FilingRef,
    scopes: tuple[str, ...],
    cache: dict[tuple[str, str], Counter | None],
    report: SimilarityBuildReport,
) -> dict[str, Counter | None] | None:
    """Term counters for one filing, one per scope, memoized in `cache` so a
    filing that participates in two consecutive pairs is fetched and tokenized
    once. None (the whole return) means the document could not be fetched at
    all; a None VALUE for one scope means that section could not be located.

    Module-level rather than a closure inside build_similarity_observations
    deliberately: as a nested function it captured the enclosing loop's
    `ticker` and `counters`, which is the late-binding pattern ruff's B023
    flags. It happened to be correct (called only within its own iteration),
    but passing them explicitly makes it independently testable and removes a
    real refactoring hazard."""
    pending = [s for s in scopes if (filing.accession, s) not in cache]
    if pending:
        try:
            text = provider.get_filing_text(filing)
        except Exception as exc:  # noqa: BLE001 — record and skip this filing
            logger.warning("filing text fetch failed for %s %s: %s", ticker, filing.accession, exc)
            report.n_text_fetch_failures += 1
            for scope in scopes:
                cache[(filing.accession, scope)] = None
            return None
        for scope in scopes:
            body = scope_text(text, scope)
            cache[(filing.accession, scope)] = term_counts(body) if body is not None else None
    return {scope: cache[(filing.accession, scope)] for scope in scopes}


def build_similarity_observations(
    provider: EdgarFilingTextProvider,
    filing_index: dict[str, list[FilingRef]],
    metrics: tuple[str, ...] = LAZY_PRICES_METRICS,
    scopes: tuple[str, ...] = LAZY_PRICES_SCOPES,
) -> tuple[dict[tuple[str, str], dict[str, list[FactorObservation]]], SimilarityBuildReport]:
    """{(metric, scope): {ticker: [FactorObservation]}} plus the coverage
    report.

    Each observation's `available` is the CURRENT filing's real EDGAR
    availability date (never its period end — see the module docstring), and
    its `end` is the current filing's period end, used only to order
    observations and to drop a stale one arriving after a fresher one.

    Processes one ticker at a time and holds only that ticker's term counters,
    so peak memory is a dozen documents rather than the whole universe."""
    report = SimilarityBuildReport(n_tickers=len(filing_index))
    report.n_pairs_scored = {s: 0 for s in scopes}
    report.n_pairs_section_missing = {s: 0 for s in scopes}
    observations: dict[tuple[str, str], dict[str, list[FactorObservation]]] = {
        (m, s): {} for m in metrics for s in scopes
    }

    for ticker, filings in sorted(filing_index.items()):
        report.n_filings += len(filings)
        pairs = pair_same_type_filings(filings)
        if not pairs:
            continue
        report.n_pairs += len(pairs)

        # Term counters per (accession, scope), computed once and shared by
        # both metrics and by the two pairs each filing participates in.
        counters: dict[tuple[str, str], Counter | None] = {}

        for previous, current in pairs:
            prev_counters = _scope_counters(
                provider, ticker, previous, scopes, counters, report
            )
            cur_counters = _scope_counters(
                provider, ticker, current, scopes, counters, report
            )
            if prev_counters is None or cur_counters is None:
                continue
            available = availability_date(current)
            period_end = current.report_date or current.filing_date
            for scope in scopes:
                a, b = prev_counters[scope], cur_counters[scope]
                if a is None or b is None:
                    report.n_pairs_section_missing[scope] += 1
                    continue
                scored_any = False
                for metric in metrics:
                    value = similarity(a, b, metric)
                    if not np.isfinite(value):
                        continue
                    observations[(metric, scope)].setdefault(ticker, []).append(
                        FactorObservation(end=period_end, value=float(value), available=available)
                    )
                    scored_any = True
                if scored_any:
                    report.n_pairs_scored[scope] += 1

    return observations, report


def build_similarity_panel(
    close: pd.DataFrame,
    observations: dict[str, list[FactorObservation]],
    *,
    max_staleness_days: int = LAZY_PRICES_MAX_STALENESS_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """The point-in-time step panel this family ranks on: (values, ages in
    calendar days, tickers with no usable observation).

    Delegates to cross_sectional_quality.build_point_in_time_factor_frame
    rather than reimplementing it. That function is a GENERIC
    availability-dated step-frame builder that happens to live in a quality
    family module, and it already handles three subtleties this family needs
    identically: forward-fill from the availability date only (never
    backfill, never interpolate), a hard staleness bound beyond which the
    value goes NaN, and dropping a stale observation that arrives after a
    fresher one. Reimplementing those here would risk exactly the bugs it has
    already been tested against."""
    return build_point_in_time_factor_frame(
        close, observations, max_staleness_days=max_staleness_days
    )


# --- the signal -------------------------------------------------------------


def signal_lazy_prices(history: CrossSectionalData) -> pd.Series:
    """The formation-date row of the similarity step panel, used AS-IS.

    Sign convention: the harness ranks top-of-signal into the LONG leg, and
    HIGH similarity means the firm barely changed its language — [CMN20]'s
    "non-changers", the long side of its own portfolio. So no sign flip is
    needed and none is applied; the direction is not a family axis.

    All the real work (similarity, filing-date visibility, staleness) happened
    in the builders above. This function reads only the last row of the
    history view, which the harness has already truncated to rows <= the
    formation date — the structural look-ahead guarantee. NaN cells refuse the
    ticker from ranking, which is the correct answer for 'this firm's filing
    language is unobservable or stale here'."""
    frame = history.fundamental_signal
    if frame is None:
        raise ValueError(
            "signal_lazy_prices requires CrossSectionalData.fundamental_signal; the spec must "
            "set requires_fundamental_signal=True and the caller must supply the similarity panel."
        )
    row = frame.iloc[-1].astype(float)
    return row.where(np.isfinite(row))


# --- the family --------------------------------------------------------------

_SCOPE_IDS = {"full": "full", "risk_factors": "rf", "mda": "mda"}
_WEIGHTING_IDS = {"equal": "eq", "inverse_vol": "ivol"}


@dataclass(frozen=True)
class LazyPricesSpec:
    """One pre-declared definition, pairing a CrossSectionalSpec with the
    (metric, scope) naming the PANEL it must be replayed against.

    The panel identity cannot live on CrossSectionalSpec itself — that type
    describes how to rank and how long to hold, and carries exactly one
    fundamental_signal requirement flag, not which of six frames to read. It
    lives here instead, and screen_lazy_prices_family groups by it."""

    metric: str
    scope: str
    spec: CrossSectionalSpec


def _build_lazy_prices_family() -> list[LazyPricesSpec]:
    specs: list[LazyPricesSpec] = []
    for metric in LAZY_PRICES_METRICS:
        for scope in LAZY_PRICES_SCOPES:
            for holding in LAZY_PRICES_HOLDING_DAYS:
                for weighting in LAZY_PRICES_LEG_WEIGHTINGS:
                    pattern_id = (
                        f"lazy_{metric}_{_SCOPE_IDS[scope]}_h{holding}_"
                        f"{_WEIGHTING_IDS[weighting]}"
                    )
                    specs.append(
                        LazyPricesSpec(
                            metric=metric,
                            scope=scope,
                            spec=CrossSectionalSpec(
                                pattern_id=pattern_id,
                                family=LAZY_PRICES_FAMILY_NAME,
                                citation=LAZY_PRICES_CITATION,
                                signal_fn=signal_lazy_prices,
                                lookback_days=LAZY_PRICES_SIGNAL_LOOKBACK_ROWS,
                                holding_days=holding,
                                portfolio="long_short",
                                rank_fraction=LAZY_PRICES_RANK_FRACTION,
                                requires_fundamental_signal=True,
                                leg_weighting=weighting,  # type: ignore[arg-type]
                            ),
                        )
                    )

    assert len(specs) == LAZY_PRICES_N_TRIALS == 36, (
        f"Lazy Prices built {len(specs)} definitions; the declared grid implies "
        f"{LAZY_PRICES_N_TRIALS} and the pre-registration froze exactly 36. All three must agree "
        "— a drift silently changes this family's DSR denominator for every future run."
    )
    assert len({s.spec.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert {s.metric for s in specs} == set(LAZY_PRICES_METRICS)
    assert {s.scope for s in specs} == set(LAZY_PRICES_SCOPES)
    assert {s.spec.holding_days for s in specs} == set(LAZY_PRICES_HOLDING_DAYS)
    assert {s.spec.leg_weighting for s in specs} == set(LAZY_PRICES_LEG_WEIGHTINGS)
    assert all(s.spec.rank_fraction == LAZY_PRICES_RANK_FRACTION for s in specs)
    assert all(s.spec.portfolio == "long_short" for s in specs)
    return specs


LAZY_PRICES_FAMILY: list[LazyPricesSpec] = _build_lazy_prices_family()


def build_inverse_vol_basis(close: pd.DataFrame) -> pd.DataFrame:
    """1 / trailing realized volatility per ticker, the basis the
    "inverse_vol" specs weight each leg by (CrossSectionalData.
    leg_weight_basis). Point-in-time by construction: a rolling std at row i
    reads only rows <= i."""
    returns = close.pct_change(fill_method=None)
    vol = returns.rolling(
        LAZY_PRICES_VOL_WINDOW_DAYS, min_periods=LAZY_PRICES_VOL_MIN_PERIODS
    ).std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        basis = 1.0 / vol
    return basis.replace([np.inf, -np.inf], np.nan)


# --- screening ---------------------------------------------------------------


@dataclass
class ScopeDispersion:
    """The realized cross-sectional dispersion of one (metric, scope) panel —
    a REQUIRED run-report number, not a diagnostic nicety.

    Reason 4 of the pre-registration's "what would make a positive result
    fake": whole-document cosine sits near 1.0 even after stopword removal, so
    a spec could in principle be ranking on formatting churn rather than on
    language. Publishing the realized spread lets a reader judge that instead
    of assuming it."""

    metric: str
    scope: str
    n_observations: int
    n_tickers_with_signal: int
    mean: float
    std: float
    p10: float
    p50: float
    p90: float
    median_age_days: float


def compute_scope_dispersion(
    metric: str, scope: str, panel: pd.DataFrame, ages: pd.DataFrame
) -> ScopeDispersion:
    values = panel.to_numpy(dtype=float).ravel()
    values = values[np.isfinite(values)]
    age_values = ages.to_numpy(dtype=float).ravel()
    age_values = age_values[np.isfinite(age_values)]
    if values.size == 0:
        return ScopeDispersion(metric, scope, 0, 0, *(float("nan"),) * 5, float("nan"))
    return ScopeDispersion(
        metric=metric,
        scope=scope,
        n_observations=int(values.size),
        n_tickers_with_signal=int(panel.notna().any(axis=0).sum()),
        mean=float(np.mean(values)),
        std=float(np.std(values, ddof=1)) if values.size > 1 else float("nan"),
        p10=float(np.quantile(values, 0.10)),
        p50=float(np.quantile(values, 0.50)),
        p90=float(np.quantile(values, 0.90)),
        median_age_days=float(np.median(age_values)) if age_values.size else float("nan"),
    )


def screen_lazy_prices_family(
    close: pd.DataFrame,
    panels: dict[tuple[str, str], pd.DataFrame],
    config: CrossSectionalConfig,
    *,
    specs: list[LazyPricesSpec] | None = None,
    half_spread: pd.DataFrame | None = None,
    leg_weight_basis: pd.DataFrame | None = None,
    membership_fn: MembershipFn | None = None,
    n_trials: int | None = None,
) -> list[CrossSectionalScreeningResult]:
    """One Sharpe per spec, DSR-corrected for the family's pre-declared size.

    Every replay is the harness's own run_cross_sectional_backtest — no replay
    logic is reimplemented here. What IS local is the aggregation, and only
    because it has to be: the 36 specs span six panels, so a per-panel call to
    screen_cross_sectional_universe would estimate sigma_sr from six
    near-identical siblings and understate it, making every DSR easier (see
    the module docstring's WHY THIS MODULE RUNS ITS OWN SCREENING LOOP).
    Here all 36 Sharpes are pooled before sigma_sr is taken.

    n_trials defaults to the pre-declared LAZY_PRICES_N_TRIALS, never to
    however many specs cleared the data floors — shrinking it to the survivors
    would be gameable by defining specs expected to fail."""
    specs = specs if specs is not None else LAZY_PRICES_FAMILY
    n_trials = n_trials if n_trials is not None else LAZY_PRICES_N_TRIALS
    if n_trials < len(specs):
        raise ValueError(
            f"n_trials={n_trials} is smaller than the {len(specs)} specs screened — that is "
            "trial-count laundering, reporting a DSR corrected for fewer comparisons than were "
            "really made."
        )

    replays: dict[str, CrossSectionalBacktestResult] = {}
    for lazy_spec in specs:
        panel = panels.get((lazy_spec.metric, lazy_spec.scope))
        if panel is None:
            continue
        data = CrossSectionalData(
            close=close,
            fundamental_signal=panel,
            half_spread=half_spread,
            leg_weight_basis=leg_weight_basis,
        )
        result = run_cross_sectional_backtest(data, lazy_spec.spec, config, membership_fn)
        if result.status != "ok" or len(result.daily_returns) < MIN_REPLAY_TRADING_DAYS:
            continue
        replays[lazy_spec.spec.pattern_id] = result

    sharpes = {
        pid: sharpe_ratio(res.daily_returns, periods_per_year=config.periods_per_year)
        for pid, res in replays.items()
    }
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None

    spec_by_id = {s.spec.pattern_id: s for s in specs}
    results: list[CrossSectionalScreeningResult] = []
    for pattern_id, replay in replays.items():
        spec = spec_by_id[pattern_id].spec
        formed = [f for f in replay.formations if f.skipped_reason is None]
        skipped = [f for f in replay.formations if f.skipped_reason is not None]
        n_basis_legs = 0
        n_basis_fallbacks = 0
        if spec.leg_weighting in BASIS_WEIGHTED_MODES:
            for f in formed:
                n_basis_legs += 1
                if f.long_leg_value_weight_fallback:
                    n_basis_fallbacks += 1
                if spec.portfolio == "long_short":
                    n_basis_legs += 1
                    if f.short_leg_value_weight_fallback:
                        n_basis_fallbacks += 1
        results.append(
            CrossSectionalScreeningResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                n_formations=len(formed),
                n_skipped_formations=len(skipped),
                avg_names_per_leg=(
                    float(np.mean([len(f.long_tickers) for f in formed])) if formed else 0.0
                ),
                n_trading_days=len(replay.daily_returns),
                sharpe_annualized=sharpes[pattern_id],
                total_cost_drag=replay.total_cost,
                total_financing_drag=replay.total_financing_cost,
                deflated_sharpe=compute_deflated_sharpe(
                    sharpes[pattern_id],
                    replay.daily_returns,
                    n_trials,
                    sigma_sr,
                    periods_per_year=config.periods_per_year,
                ),
                n_value_weighted_legs=n_basis_legs,
                n_value_weight_fallbacks=n_basis_fallbacks,
                total_turnover=float(sum(f.turnover for f in replay.formations)),
                edge_flat_fallback_notional=float(
                    sum(f.edge_flat_fallback_notional for f in replay.formations)
                ),
            )
        )
    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results


# --- production entry point ---------------------------------------------------


@dataclass
class LazyPricesSummary:
    results: list[CrossSectionalScreeningResult]
    dispersion: list[ScopeDispersion]
    filing_report: FilingIndexReport
    similarity_report: SimilarityBuildReport
    universe_size: int
    n_priced_tickers: int
    missing_price_tickers: list[str]
    tickers_without_signal: dict[str, int]
    first_date: date | None
    last_date: date | None
    sample_disclosure: str


def _build_sample_disclosure(
    universe_size: int,
    n_priced: int,
    filing_report: FilingIndexReport,
    similarity_report: SimilarityBuildReport,
) -> str:
    scored = similarity_report.n_pairs_scored
    missing = similarity_report.n_pairs_section_missing
    return (
        f"LAZY PRICES SAMPLE DISCLOSURE — read before trusting any Sharpe or DSR below. "
        f"Universe: {universe_size} point-in-time S&P 500 tickers over the window "
        f"(sp500_membership_history.get_universe_over; TODAY's snapshot is NOT used), of which "
        f"{n_priced} resolved yfinance price history. SEC resolved a CIK for "
        f"{filing_report.n_tickers_cik_resolved} of {filing_report.n_tickers_requested} requested "
        f"and indexed {filing_report.n_tickers_indexed}, walking "
        f"{filing_report.n_older_pages_fetched} paginated older-history pages to list "
        f"{filing_report.n_filings_listed} periodic filings. "
        f"{similarity_report.n_pairs} same-type consecutive filing pairs were formed from "
        f"{similarity_report.n_filings} filings ({similarity_report.n_text_fetch_failures} text "
        f"fetches failed). Pairs scored per scope: {scored}; pairs dropped because a section "
        f"could not be located: {missing}. SECTION COVERAGE IS NOT RANDOM ACROSS FILERS — a "
        f"filer whose headings do not match (GE's integrated report is the measured example) "
        f"contributes NO section-scope observation at all, so the risk_factors and mda specs "
        f"rank a differently-composed cross-section than the full specs and the three are not "
        f"directly comparable. SURVIVORSHIP: the point-in-time gate removes the look-ahead half "
        f"of survivorship bias, but it cannot manufacture prices or CIKs that no free source "
        f"sells — yfinance has no history for roughly half the names that left the index, and "
        f"SEC's ticker map resolves CURRENT tickers only. Directionally, a deteriorating firm is "
        f"exactly the kind expected to rewrite its risk-factor and litigation language, i.e. a "
        f"'changer' belonging in the SHORT leg, so their absence works AGAINST the hypothesis "
        f"rather than for it. FINALLY: the whole sample is S&P 500 large caps in 2015-2026, "
        f"while Cohen/Malloy/Nguyen ran the complete U.S. filer universe through 2014 on an "
        f"INATTENTION mechanism — large caps are where inattention is scarcest, and the sample "
        f"post-dates the paper's own publication. The prior going in is weak and a strong "
        f"positive here should be disbelieved before it is believed."
    )


def run_lazy_prices_screening(
    start: date,
    end: date,
    *,
    provider: YFinanceProvider | None = None,
    text_provider: EdgarFilingTextProvider | None = None,
    config: CrossSectionalConfig | None = None,
    tickers: list[str] | None = None,
    filing_index: dict[str, list[FilingRef]] | None = None,
    filing_report: FilingIndexReport | None = None,
) -> LazyPricesSummary:
    """THE production entry point.

    `start` must be >= MEMBERSHIP_DATA_START: every formation is gated by
    point-in-time membership and was_member answers a silent False before
    coverage begins.

    Filings are indexed only for tickers that RESOLVED PRICES, deliberately —
    a ticker with no price history can never be ranked, so fetching its
    filings would spend requests against a public service for documents this
    run cannot use."""
    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"Lazy Prices screening start {start.isoformat()} predates point-in-time membership "
            f"coverage ({MEMBERSHIP_DATA_START.isoformat()}) — the was_member gate would silently "
            "answer False for every formation before it."
        )
    provider = provider if provider is not None else YFinanceProvider()
    text_provider = text_provider if text_provider is not None else EdgarFilingTextProvider()
    config = config if config is not None else CrossSectionalConfig(cost_model="edge_spread")
    if config.formation_start is None:
        config.formation_start = start

    universe = tickers if tickers is not None else get_universe_over(start, end)
    frames, missing = provider.get_daily_ohlcv(sorted(universe), start, end)
    if not frames:
        raise ValueError(
            "no price history resolved for any point-in-time universe ticker — the run cannot "
            "rank anything and this is a data failure, not a finding."
        )
    close = frames["close"]
    priced = list(close.columns)

    if filing_index is None:
        filing_index, filing_report = text_provider.build_filing_index(
            priced, forms=LAZY_PRICES_FORMS
        )
    if filing_report is None:
        filing_report = FilingIndexReport(n_tickers_requested=len(priced))

    # Only filings that could matter: one already needs its predecessor, so
    # history is kept back to the warm-up horizon and no further.
    warmup_floor = start.toordinal() - LAZY_PRICES_FILING_WARMUP_DAYS
    trimmed = {
        ticker: [f for f in filings if f.filing_date.toordinal() >= warmup_floor]
        for ticker, filings in filing_index.items()
        if ticker in close.columns
    }

    observations, similarity_report = build_similarity_observations(text_provider, trimmed)

    panels: dict[tuple[str, str], pd.DataFrame] = {}
    dispersion: list[ScopeDispersion] = []
    tickers_without_signal: dict[str, int] = {}
    for (metric, scope), by_ticker in observations.items():
        panel, ages, unusable = build_similarity_panel(close, by_ticker)
        panels[(metric, scope)] = panel
        dispersion.append(compute_scope_dispersion(metric, scope, panel, ages))
        tickers_without_signal[f"{metric}/{scope}"] = len(unusable)

    half_spread = (
        build_edge_half_spread_frame(frames["open"], frames["high"], frames["low"], close)
        if config.cost_model == "edge_spread"
        else None
    )
    leg_weight_basis = (
        build_inverse_vol_basis(close)
        if any(s.spec.leg_weighting in BASIS_WEIGHTED_MODES for s in LAZY_PRICES_FAMILY)
        else None
    )

    results = screen_lazy_prices_family(
        close,
        panels,
        config,
        half_spread=half_spread,
        leg_weight_basis=leg_weight_basis,
    )
    dispersion.sort(key=lambda d: (d.metric, d.scope))
    return LazyPricesSummary(
        results=results,
        dispersion=dispersion,
        filing_report=filing_report,
        similarity_report=similarity_report,
        universe_size=len(universe),
        n_priced_tickers=len(priced),
        missing_price_tickers=sorted(missing),
        tickers_without_signal=tickers_without_signal,
        first_date=close.index[0].date() if len(close.index) else None,
        last_date=close.index[-1].date() if len(close.index) else None,
        sample_disclosure=_build_sample_disclosure(
            len(universe), len(priced), filing_report, similarity_report
        ),
    )


__all__ = [
    "DEFAULT_FILING_INDEX_PATH",
    "LAZY_PRICES_CITATION",
    "LAZY_PRICES_FAMILY",
    "LAZY_PRICES_FAMILY_NAME",
    "LAZY_PRICES_FORMS",
    "LAZY_PRICES_HOLDING_DAYS",
    "LAZY_PRICES_LEG_WEIGHTINGS",
    "LAZY_PRICES_MAX_STALENESS_DAYS",
    "LAZY_PRICES_METRICS",
    "LAZY_PRICES_N_TRIALS",
    "LAZY_PRICES_RANK_FRACTION",
    "LAZY_PRICES_SCOPES",
    "LazyPricesSpec",
    "LazyPricesSummary",
    "ScopeDispersion",
    "SimilarityBuildReport",
    "build_inverse_vol_basis",
    "build_similarity_observations",
    "build_similarity_panel",
    "cosine_similarity",
    "jaccard_similarity",
    "pair_same_type_filings",
    "run_lazy_prices_screening",
    "scope_text",
    "screen_lazy_prices_family",
    "signal_lazy_prices",
    "similarity",
    "term_counts",
    "tokenize",
]
