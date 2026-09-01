"""Scheduled earnings-announcement premium: a deliberately small
(8-definition) CALENDAR-driven family -- long every firm PREDICTED to
announce earnings inside a short upcoming window, ex ante, before the news
exists and regardless of what it turns out to be, hedged against every
other point-in-time S&P 500 member.

WHAT MAKES THIS NOT cross_sectional_pead.py, which is the nearest sibling
and the structural template for this file: PEAD conditions on the REALIZED
announcement return and trades the drift AFTERWARDS. This family conditions
on the SCHEDULED EVENT ITSELF and is fully determined BEFORE the
announcement. Nothing here reads an announcement outcome: the long leg is
selected from a firm's own past filing CALENDAR, the position's entry and
exit rows are both fixed the moment the window opens, and no gate anywhere
consults what the announcement said or how the stock reacted. The one place
a past outcome is read at all is the "ann_vol" weighting axis, and it reads
the SIZE of previous announcement moves (a risk measure), never a direction.

Like the PEAD family this module owns its family object, its n_trials
denominator, and its never-pooled DSR correction, and it does NOT run on
cross_sectional.screen_cross_sectional_universe -- that harness ranks a
synchronized universe snapshot on a signal, and this family ranks nothing
at all; it selects on a calendar. What it reuses UNMODIFIED, from
cross_sectional.py itself: _resolve_leg_weights (so "equal" here is
LITERALLY the harness's own equal mode, and the "ann_vol" basis rides its
generic weight_basis path), _leg_weighted_return (the drop-a-missing-name-
and-renormalize convention), _compute_delisting_positions plus
DEFAULT_IMPUTED_DELISTING_RETURN (the Shumway imputation),
DEFAULT_XS_COST_BPS, FINANCING_DAYS_PER_YEAR and MIN_REPLAY_TRADING_DAYS;
and from cross_sectional_pead.py, the SEC access layer (see below).

============================================================================
THE ACADEMIC BASIS -- INDEPENDENTLY VERIFIED 2026-09-01, AND TWO OF THE
BUILD BRIEF'S OWN CLAIMS DID NOT SURVIVE THAT VERIFICATION
============================================================================
An adversarial pass re-fetched every source rather than trusting the build
brief's summary. Tiers are labelled per entry and must not be blurred:
  PRIMARY   = the paper's own retrievable text was read and quoted.
  ABSTRACT  = the publisher-deposited abstract was retrieved and quoted,
              but the paywalled body was NOT.
  RECORD    = bibliographic record confirmed only.
  SECONDARY = the figure comes from a summary of the paper, not the paper.

 * Savor, P. & Wilson, M., "Earnings Announcements and Systematic Risk"
   (Journal of Finance, 71(1), 2016, pp. 83-138, doi:10.1111/jofi.12361).
   ABSTRACT: record and abstract both retrieved from Crossref's
   publisher-deposited metadata (RePEc corroborates the record but lists a
   WRONG, issue-level DOI -- Crossref is authoritative). The abstract opens,
   verbatim: "Firms scheduled to report earnings earn an annualized abnormal
   return of 9.9%. We propose a risk-based explanation for this phenomenon,
   whereby investors use announcements to revise their expectations for
   nonannouncing firms, but can only do so imperfectly. Consequently, the
   covariance between firm-specific and market cash flow news spikes around
   announcements, making announcers especially risky."
   *** CORRECTION TO THE BUILD BRIEF, #1. *** The brief pointed at a
   December 2011 Wharton working-paper draft as interchangeable with the
   published paper ("the mechanism is stable across versions"). The
   MECHANISM is; THE HEADLINE NUMBER IS NOT. The draft (retrieved and read
   at faculty.wharton.upenn.edu/wp-content/uploads/2012/04/
   Draft20111215p_edited.pdf, "This version: December 2011", sample
   1974-2009) states: "A portfolio strategy that buys all announcing firms
   in a given week and sells short all the non-announcing firms earns an
   annualized abnormal return of 20%." That 20% is the EQUAL-WEIGHTED book
   in the draft; the published abstract's figure is 9.9%. WHY the headline
   moved was NOT established -- the published body is behind Wiley (403) and
   was not retrieved -- so no reconciliation is asserted here. THE CITABLE
   PUBLISHED NUMBER IS 9.9%; 20% is a superseded draft figure and must not
   be quoted as the paper's result.
   Two mechanism nuances read directly from the draft, both load-bearing
   for this family's prior: (a) the premium requires IMPERFECT signal
   extraction and dies at BOTH corners -- if investors learn nothing about
   non-announcers the news is idiosyncratic and unpriced, if they learn as
   much as about announcers the differential is zero; (b) the claim is
   explicitly that the excess return is LARGER than the higher market beta
   explains (the draft puts the announcement portfolio's market beta at
   0.12), so this is not a "beta rises during announcements" story.
 * Barber, B. M., De George, E. T., Lehavy, R. & Trueman, B., "The earnings
   announcement premium around the globe" (Journal of Financial Economics,
   108(1), 2013, pp. 118-138, doi:10.1016/j.jfineco.2012.10.006 -- the DOI
   the brief did not supply). ABSTRACT: record confirmed at Crossref and
   OpenAlex, abstract retrieved verbatim: "...We document that this earnings
   announcement premium exists across the globe... Of the 20 countries with
   enough data to conduct a within-country analysis, nine exhibit a
   significantly positive premium. A cross-country analysis finds that the
   premium is strongest in countries with the greatest increase in
   idiosyncratic volatility around the time of their firms' earnings
   announcements."
   HONEST FLAG: THE PUBLISHED ABSTRACT CONTAINS NO MAGNITUDE AT ALL. Any
   percentage attributed to it would be fabricated. The 2011 working paper
   (retrieved at Tel Aviv University) says "by over 11 percent annually";
   a CFA Institute digest of the PUBLISHED version reports 59.7bp/month
   (7.16% annualized) -- SECONDARY, not read in the paper itself, and it
   disagrees with the working paper's own 66.8bp raw / 95.4bp adjusted.
   Treat the international magnitude as UNSETTLED at this project's level
   of access.
 * Lamont, O. & Frazzini, A., "The Earnings Announcement Premium and
   Trading Volume" (NBER Working Paper 13090, May 2007,
   doi:10.3386/w13090). PRIMARY: the NBER PDF was retrieved and read.
   THE DIRECT PRECEDENT for this family, because it is the EX-ANTE
   TRADEABLE version -- it conditions on PREDICTED announcement timing, as
   this module must. From p.1, verbatim: "we find monthly strategies
   earning excess returns of between 7% and 18% per year, with Sharpe
   ratios larger than other popular anomalies. The premium is strong in
   large capitalization stocks, is not only confined to the three-day
   window around the announcement, and appears consistently since 1927."
   (Author order: NBER's own title page reads Lamont, Frazzini; Savor &
   Wilson cite it Frazzini-first. NBER's order is used here.)
   Their proposed mechanism is LIMITED ATTENTION and small-investor buying
   pressure -- explicitly NOT risk.
 * Beaver, W. H., "The Information Content of Annual Earnings
   Announcements" (Journal of Accounting Research, 6, 1968, pp. 67-92).
   RECORD (RePEc). The ancestor: volume and volatility spike at
   announcements. Not itself a tradeable-premium paper.
 * Ball, R. & Kothari, S. P., "Security Returns Around Earnings
   Announcements" (The Accounting Review, 66, 1991, pp. 718-738). RECORD,
   verified from Kothari's own MIT CV. Cited here for the OPPOSITE reason
   to the rest: per Barber et al.'s own text, "Ball and Kothari (1991) find
   that the short-window announcement premium is not explained by
   systematic risk."
 * Cohen, D., Dey, A., Lys, T. & Sunder, S., "Earnings Announcement Premia
   and the Limits to Arbitrage" (Journal of Accounting and Economics,
   43(2-3), 2007, pp. 153-180, doi:10.1016/j.jacceco.2007.01.008). RECORD
   (Crossref). Explanation: LIMITS TO ARBITRAGE, not risk.

*** CORRECTION TO THE BUILD BRIEF, #2, AND IT IS THE IMPORTANT ONE. ***
The brief states the premium "is a risk premium, not an inefficiency, so --
unlike most anomalies -- there's no strong a priori reason it should decay
once known." THE LITERATURE DOES NOT SUPPORT THAT AS SETTLED. The
risk-based reading is Savor & Wilson's PROPOSAL, and it is one of at least
three live explanations: Ball & Kothari (1991) find the short-window
premium is NOT explained by systematic risk; Cohen, Dey, Lys & Sunder
(2007) attribute it to limits to arbitrage; Lamont & Frazzini (2007)
attribute it to retail attention. Two of those three ARE inefficiency
stories, and inefficiency stories decay. The "should not decay" claim is
therefore recorded here as CONTESTED, not as a premise this family is
entitled to lean on.

============================================================================
THE HONEST PRIOR, STATED BEFORE ANY RESULT
============================================================================
Unusually for this project, one leg of the prior is FAVORABLE and it should
be said plainly rather than buried: Lamont & Frazzini's verified sentence
"The premium is strong in large capitalization stocks" means this family's
S&P 500 universe is NOT the handicap it was for PEAD (whose own source
table showed the effect "considerably reduced" in large caps). This is the
first family in this project whose literature actively points AT its
universe rather than away from it.

Against that, four compounding reasons for a modest prior:
 1. DECAY, AND A SPECIFIC ALLEGATION THAT IT ALREADY HAPPENED. There is NO
    peer-reviewed published study establishing whether this premium
    survived post-2013 out-of-sample. The one directly on-point study,
    Heitz, Narayanamoorthy & Zekhnini, "Filings of Material Information and
    the Disappearing Earnings Announcement Premium" (SSRN 3296537, DOI
    10.2139/ssrn.3296537), is an UNPUBLISHED working paper whose text could
    NOT be retrieved (SSRN 403, the Rotman mirror 500, no abstract at
    Crossref or OpenAlex). Its existence, authorship and title are verified;
    its numbers are not, and none are quoted here or anywhere in this
    family. Its CLAIM, consistently reported across independent summaries
    and stated here as the paper's claim rather than as fact, is that the US
    premium disappeared after 2004 because the 2004 Form 8-K disclosure
    regime pre-empted the information. THIS FAMILY'S ENTIRE SAMPLE IS
    POST-2004. If that claim is right, the expected result here is zero.
    Separately, McLean & Pontiff, "Does Academic Research Destroy Stock
    Return Predictability?" (Journal of Finance, 71(1), 2016, pp. 5-32,
    doi:10.1111/jofi.12365 -- abstract retrieved verbatim from Crossref)
    measure returns "58% lower post-publication" across 97 predictors. That
    is a GENERAL result, not an EAP-specific one, and is used here only as
    a prior, never as evidence about this premium in particular.
 2. THE CALENDAR IS PREDICTED, NOT KNOWN. Every published implementation
    above had a real earnings-date source. This project has none, so the
    announcement date is inferred from the firm's own past filing calendar,
    and a window that misses the real announcement earns nothing by
    construction. The measured accuracy of that predictor is reported in
    the run report whatever it shows, and the per-spec
    caught_actual_fraction says how much of each spec's book was pointed at
    a real announcement at all.
 3. TURNOVER. The long leg is rebuilt every few days as firms rotate
    through their windows. This is a far more cost-sensitive book than a
    monthly-rebalanced one, which is why the pre-declared cost ladder is
    reported for every spec and the HEADLINE uses the conservative 5bp end.
 4. PROXY NOISE. Item 2.02 is overwhelmingly quarterly earnings but also
    covers preliminary-results and guidance 8-Ks; no press-release text is
    parsed to tell them apart.
An honest negative is the expected outcome and is a complete result.

============================================================================
SEC EDGAR
============================================================================
The access layer -- ticker->CIK mapping, submissions URL, declared
User-Agent, and the 0.15s (~6.7 req/s) interval under SEC's published
10 req/s fair-access cap -- is IMPORTED from cross_sectional_pead.py rather
than restated, because those are facts about SEC's API and this project's
identity, not choices belonging to either family. What this module adds is
filings.files PAGINATION, for the reason documented at the constant block
below: a firm's own past filing calendar IS this family's signal source, so
the ~1,000-row filings.recent cap that merely costs PEAD some events would
here delete the mega-cap banks from the early sample entirely.

============================================================================
SIGNAL, TIMING AND THE POINT-IN-TIME GUARANTEE
============================================================================
DAY 0 of an ACTUAL announcement is derived by
cross_sectional_pead.announcement_day0, reused unchanged (acceptance before
16:00 ET -> that session; at/after 16:00 ET, on a non-trading day, or with
no timestamp -> the next session, the never-early direction).

THE PREDICTOR: each actual announcement generates exactly ONE prediction,
EAP_PREDICTOR_LAG_DAYS = 364 calendar days later (52 weeks, which preserves
day of week). That single rule is what makes the whole predicted calendar
point-in-time by construction -- a prediction is generated by an
announcement roughly a year before the position it justifies, so it can
never read a filing that had not yet been made. build_traded_windows
asserts this rather than trusting it.

A position opens at the CLOSE of (predicted row - days_before - 1) and
closes at the CLOSE of (predicted row + days_after). Both rows are fixed
when the window opens. The first realized return is the following session.
Exit is also forced by delisting (Shumway imputation, ON by default).

============================================================================
KNOWN LIMITS
============================================================================
 * The predicted calendar is a proxy for a real earnings-date feed, and its
   error rate directly dilutes every result. Measured, not assumed.
 * Point-in-time membership fixes the ROSTER, not the PRICES: yfinance sells
   no delisted history, so the acquired and failed names are missing and
   their absence FLATTERS these numbers.
 * Earnings cluster into four reporting seasons, so daily returns are
   heavily overlapping and the observation count feeding the Sharpe and DSR
   overstates the independent information.
 * A day on which either leg is empty is 0.0 by design, counted, never
   traded as a naked single leg.
 * Market impact, commissions and borrow are not modelled; true costs are
   higher than the reported drag at every level of the cost ladder.
"""

import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.research_lab.cross_sectional import (
    DEFAULT_IMPUTED_DELISTING_RETURN,
    DEFAULT_XS_COST_BPS,
    FINANCING_DAYS_PER_YEAR,
    MIN_REPLAY_TRADING_DAYS,
    _compute_delisting_positions,
    _leg_weighted_return,
    _resolve_leg_weights,
)
from app.services.research_lab.cross_sectional_pead import (
    PEAD_SEC_MIN_REQUEST_INTERVAL_SECONDS,
    PEAD_SEC_USER_AGENT,
    SEC_SUBMISSIONS_URL_TEMPLATE,
    EarningsEvent,
    announcement_day0,
    load_cik_map,
)
from app.services.research_lab.deflated_sharpe import (
    DeflatedSharpeResult,
    compute_deflated_sharpe,
)
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_START,
    get_universe_as_of,
    get_universe_over,
    membership_coverage_end,
)

logger = logging.getLogger(__name__)

EAP_FAMILY_NAME = "earnings_announcement_premium"

# --- SEC EDGAR access ------------------------------------------------------
#
# REUSED, NOT REINVENTED, from cross_sectional_pead.py: the ticker->CIK
# mapping file loader, the submissions URL template, the project's declared
# User-Agent, the 0.15s (~6.7 req/s) interval under SEC's published 10 req/s
# fair-access cap, and the EarningsEvent record itself. Those are facts about
# SEC's API and about this project's identity, not choices belonging to
# either family, so there is one source of truth for them.
#
# WHAT THIS MODULE ADDS, AND WHY IT IS NOT A DRIVE-BY CHANGE TO PEAD:
# filings.recent is capped (~1,000 rows, or one year for a very heavy filer),
# and older history lives in the paginated filings.files chunks that
# cross_sectional_pead.py deliberately does NOT fetch. For PEAD that
# truncation costs some events. For THIS family it is far more damaging:
# a firm's own past filing calendar IS the signal source -- a ticker whose
# EDGAR coverage starts in 2025 cannot have a "same fiscal quarter last
# year" prediction made for 2016 at all -- and the heavy filers hit by the
# cap are systematically the mega-cap banks (verified live 2026-09-01:
# JPM's filings.recent is 26,083 rows covering only 2025-08-29 onward,
# against 69 older chunks). Dropping them would thin financials out of the
# early sample in a way that is not random. So this module paginates, and
# PEAD is left byte-for-byte untouched.
#
# VERIFIED LIVE 2026-09-01, not assumed: submissions.filings.files is a list
# of {"name", "filingCount", "filingFrom", "filingTo"}; each named chunk at
# https://data.sec.gov/submissions/<name> is a dict of the SAME parallel
# arrays as filings.recent (accessionNumber / filingDate / acceptanceDateTime
# / form / items / ...). The filingFrom/filingTo range lets a chunk be
# skipped without fetching it, which is why this costs ~1-4 extra requests
# for a typical S&P 500 name and only the heavy filers pay ~30-60.

SEC_SUBMISSIONS_CHUNK_URL_TEMPLATE = "https://data.sec.gov/submissions/{name}"

# "Results of Operations and Financial Condition" -- the 8-K item number a
# quarterly earnings release is filed under.
EAP_EARNINGS_ITEM = "2.02"

# Default on-disk cache for the fetched filing calendar, following the
# data/ convention futures_curve_collector.py and the insider/funding
# caches use. Gitignored as a refetchable VENDOR INPUT, not a result --
# the results live in cross_sectional_trial_results and in
# data/research_runs/. Rebuilt from scratch by fetch_announcement_calendar.
EAP_EVENT_CACHE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "eap_edgar_announcement_calendar.json"
)


@dataclass
class CalendarFetchReport:
    """What the EDGAR pass actually covered. Every field here is a
    sample-construction fact that belongs in the run report, not a log
    detail -- a ticker with no pre-sample filing history silently produces
    no predictions, and silence is exactly what has to be counted."""

    n_tickers_requested: int = 0
    n_tickers_cik_resolved: int = 0
    n_tickers_fetched: int = 0
    n_tickers_fetch_failed: int = 0
    # Older filings.files chunks actually downloaded (those whose own
    # filingFrom/filingTo range overlapped the requested window).
    n_chunks_fetched: int = 0
    n_chunks_failed: int = 0
    # Tickers whose EARLIEST observed filing of ANY form still lands after
    # the requested fetch_start even after pagination -- i.e. EDGAR itself
    # has no earlier coverage for them, so their early-sample predictions
    # cannot exist. Distinct from a fetch failure.
    n_tickers_coverage_starts_late: int = 0
    unresolved_tickers: list[str] = field(default_factory=list)
    failed_tickers: list[str] = field(default_factory=list)
    late_coverage_tickers: list[str] = field(default_factory=list)


def _sec_get_json(url: str, user_agent: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_filing_rows(
    ticker: str,
    cik: int,
    rows: dict,
    fetch_start: date,
    end: date,
) -> tuple[list[EarningsEvent], date | None]:
    """(item-2.02 8-K events in [fetch_start, end], earliest filingDate of
    ANY form seen in `rows`) from one parallel-array block -- either
    filings.recent or one older filings.files chunk, which share a shape.

    Only form == '8-K', never '8-K/A': an amendment is not the
    announcement, and counting it would put a phantom extra date on the
    firm's calendar. Item matching is against the comma-split list, so
    '2.02' never matches '12.02'.

    The second return value is what detects genuine EDGAR coverage limits
    (as opposed to "this firm filed no 8-Ks that year"), and it reads
    EVERY form deliberately -- a 10-K is proof of coverage just as much as
    an 8-K is."""
    forms = rows.get("form", [])
    items = rows.get("items", [])
    filing_dates = rows.get("filingDate", [])
    acceptances = rows.get("acceptanceDateTime", [])
    accessions = rows.get("accessionNumber", [])

    events: list[EarningsEvent] = []
    earliest: date | None = None
    for i, form in enumerate(forms):
        if i >= len(filing_dates):
            break
        try:
            filed = date.fromisoformat(filing_dates[i])
        except (TypeError, ValueError):
            continue
        if earliest is None or filed < earliest:
            earliest = filed
        if form != "8-K":
            continue
        item_field = items[i] if i < len(items) else ""
        if EAP_EARNINGS_ITEM not in (item_field or "").split(","):
            continue
        if not (fetch_start <= filed <= end):
            continue
        events.append(
            EarningsEvent(
                ticker=ticker,
                cik=cik,
                accession=accessions[i] if i < len(accessions) else "",
                filing_date=filed,
                acceptance_utc=(acceptances[i] or "") if i < len(acceptances) else "",
            )
        )
    return events, earliest


def _chunk_overlaps(chunk: dict, fetch_start: date, end: date) -> bool:
    """Whether an older filings.files chunk's own declared date range
    intersects [fetch_start, end]. A chunk with an unparseable or missing
    range is FETCHED rather than skipped -- the conservative direction,
    since skipping it would silently drop real filings, while fetching an
    unnecessary chunk only costs one request."""
    try:
        chunk_from = date.fromisoformat(chunk["filingFrom"])
        chunk_to = date.fromisoformat(chunk["filingTo"])
    except (KeyError, TypeError, ValueError):
        return True
    return chunk_from <= end and chunk_to >= fetch_start


def fetch_announcement_calendar(
    tickers: list[str],
    fetch_start: date,
    end: date,
    user_agent: str = PEAD_SEC_USER_AGENT,
    min_request_interval: float = PEAD_SEC_MIN_REQUEST_INTERVAL_SECONDS,
    progress_every: int = 25,
) -> tuple[list[EarningsEvent], CalendarFetchReport]:
    """Every 8-K Item 2.02 filing by `tickers` in [fetch_start, end], from
    filings.recent AND from every older filings.files chunk whose declared
    range overlaps the window. Rate-limited under SEC's published 10 req/s
    fair-access cap. A ticker or chunk that fails is recorded and skipped,
    never retried in a tight loop.

    Deduplicated by (ticker, accessionNumber): the recent block and the
    newest chunk can genuinely overlap, and a duplicated filing would put
    a duplicate date on a firm's calendar, which is precisely the input
    this family's predictor is most sensitive to."""
    report = CalendarFetchReport(n_tickers_requested=len(tickers))
    cik_map = load_cik_map(user_agent)
    events: list[EarningsEvent] = []
    last_request = 0.0

    def _throttled_get(url: str) -> dict:
        nonlocal last_request
        elapsed = time.monotonic() - last_request
        if elapsed < min_request_interval:
            time.sleep(min_request_interval - elapsed)
        last_request = time.monotonic()
        return _sec_get_json(url, user_agent)

    for n_done, ticker in enumerate(tickers, start=1):
        if progress_every and n_done % progress_every == 0:
            logger.info(
                "EDGAR calendar: %d/%d tickers, %d chunks, %d events so far",
                n_done,
                len(tickers),
                report.n_chunks_fetched,
                len(events),
            )
        cik = cik_map.get(ticker)
        if cik is None:
            report.unresolved_tickers.append(ticker)
            continue
        report.n_tickers_cik_resolved += 1
        try:
            submissions = _throttled_get(SEC_SUBMISSIONS_URL_TEMPLATE.format(cik=cik))
        except Exception as exc:  # noqa: BLE001 -- record and continue
            logger.warning("EDGAR submissions fetch failed for %s: %s", ticker, exc)
            report.n_tickers_fetch_failed += 1
            report.failed_tickers.append(ticker)
            continue
        report.n_tickers_fetched += 1

        # Every parallel-array block for this ticker -- filings.recent first,
        # then each older chunk whose declared range overlaps the window.
        # Collected as a LIST and folded below rather than absorbed by a
        # closure over the loop variables, which would be a late-binding
        # hazard even where (as here) every call happens in the same
        # iteration.
        filings = submissions.get("filings", {})
        blocks: list[dict] = [filings.get("recent", {})]
        for chunk in filings.get("files", []) or []:
            if not _chunk_overlaps(chunk, fetch_start, end):
                continue
            name = chunk.get("name")
            if not name:
                continue
            try:
                blocks.append(
                    _throttled_get(SEC_SUBMISSIONS_CHUNK_URL_TEMPLATE.format(name=name))
                )
            except Exception as exc:  # noqa: BLE001 -- record and continue
                logger.warning("EDGAR chunk fetch failed for %s/%s: %s", ticker, name, exc)
                report.n_chunks_failed += 1
                continue
            report.n_chunks_fetched += 1

        seen: set[str] = set()
        ticker_events: list[EarningsEvent] = []
        earliest_seen: date | None = None
        for rows in blocks:
            parsed, earliest = _parse_filing_rows(ticker, cik, rows, fetch_start, end)
            if earliest is not None and (earliest_seen is None or earliest < earliest_seen):
                earliest_seen = earliest
            for event in parsed:
                # The recent block and the newest chunk genuinely overlap, and
                # a duplicated filing would put a duplicate date on this
                # firm's calendar -- the input this family is most sensitive to.
                key = event.accession or f"{event.filing_date.isoformat()}:{len(seen)}"
                if key in seen:
                    continue
                seen.add(key)
                ticker_events.append(event)

        if earliest_seen is None or earliest_seen > fetch_start:
            report.n_tickers_coverage_starts_late += 1
            report.late_coverage_tickers.append(ticker)
        events.extend(ticker_events)

    return events, report


def save_calendar_cache(
    events: list[EarningsEvent],
    report: CalendarFetchReport,
    fetch_start: date,
    end: date,
    path: Path = EAP_EVENT_CACHE_PATH,
) -> None:
    payload = {
        "fetched_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "fetch_start": fetch_start.isoformat(),
        "end": end.isoformat(),
        "report": {
            "n_tickers_requested": report.n_tickers_requested,
            "n_tickers_cik_resolved": report.n_tickers_cik_resolved,
            "n_tickers_fetched": report.n_tickers_fetched,
            "n_tickers_fetch_failed": report.n_tickers_fetch_failed,
            "n_chunks_fetched": report.n_chunks_fetched,
            "n_chunks_failed": report.n_chunks_failed,
            "n_tickers_coverage_starts_late": report.n_tickers_coverage_starts_late,
            "unresolved_tickers": report.unresolved_tickers,
            "failed_tickers": report.failed_tickers,
            "late_coverage_tickers": report.late_coverage_tickers,
        },
        "events": [
            {
                "ticker": e.ticker,
                "cik": e.cik,
                "accession": e.accession,
                "filing_date": e.filing_date.isoformat(),
                "acceptance_utc": e.acceptance_utc,
            }
            for e in events
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def load_calendar_cache(
    path: Path = EAP_EVENT_CACHE_PATH,
) -> tuple[list[EarningsEvent], CalendarFetchReport, date, date] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    events = [
        EarningsEvent(
            ticker=row["ticker"],
            cik=int(row["cik"]),
            accession=row["accession"],
            filing_date=date.fromisoformat(row["filing_date"]),
            acceptance_utc=row["acceptance_utc"],
        )
        for row in payload["events"]
    ]
    r = payload["report"]
    report = CalendarFetchReport(
        n_tickers_requested=r["n_tickers_requested"],
        n_tickers_cik_resolved=r["n_tickers_cik_resolved"],
        n_tickers_fetched=r["n_tickers_fetched"],
        n_tickers_fetch_failed=r["n_tickers_fetch_failed"],
        n_chunks_fetched=r.get("n_chunks_fetched", 0),
        n_chunks_failed=r.get("n_chunks_failed", 0),
        n_tickers_coverage_starts_late=r.get("n_tickers_coverage_starts_late", 0),
        unresolved_tickers=list(r["unresolved_tickers"]),
        failed_tickers=list(r["failed_tickers"]),
        late_coverage_tickers=list(r.get("late_coverage_tickers", [])),
    )
    return (
        events,
        report,
        date.fromisoformat(payload["fetch_start"]),
        date.fromisoformat(payload["end"]),
    )


# ===========================================================================
# THE ANNOUNCEMENT CALENDAR AND THE EX-ANTE PREDICTOR
# ===========================================================================
#
# This family's whole difficulty is that it must know a firm's NEXT
# announcement date BEFORE that announcement happens, using only information
# that existed at the time. This project has no analyst-estimate or
# earnings-calendar vendor feed, so the only available source is the firm's
# OWN past filing calendar from EDGAR.
#
# THE HEURISTIC: a firm's next announcement lands 364 CALENDAR DAYS after the
# announcement of the same fiscal quarter one year earlier. 364 = 52 weeks
# exactly, which PRESERVES DAY OF WEEK -- earnings releases are scheduled on
# weekdays (overwhelmingly Tue/Wed/Thu), so a 365-day shift walks the
# prediction one weekday per year and a 364-day shift does not. That choice
# is not asserted from intuition: it is MEASURED against the real filing
# history, alongside the 365-day and last-announcement-plus-median-gap
# variants, and the measured accuracy is reported in the run report whatever
# it shows (see EAP_PREDICTOR_LAG_CANDIDATES and
# measure_predictor_accuracy below).
#
# Every announcement therefore generates exactly ONE prediction, one year
# ahead, which is known from the moment that announcement occurs. That makes
# the whole predicted calendar point-in-time by construction: no prediction
# can ever read a filing that had not yet been made.

# Two Item 2.02 filings by one ticker within this many trading rows are one
# announcement (re-files, same-quarter follow-ups). Same constant and same
# reasoning as cross_sectional_pead.PEAD_DUPLICATE_FILING_GAP_TRADING_DAYS,
# restated rather than imported because a change to PEAD's event de-dup
# should not silently move this family's CALENDAR, which is a different
# object serving a different purpose.
EAP_DUPLICATE_FILING_GAP_TRADING_DAYS = 5

# Calendar-day lag from an announcement to the same fiscal quarter's
# announcement one year later. 364 = 52 weeks (day-of-week preserving).
EAP_PREDICTOR_LAG_DAYS = 364

# Measured against, never searched over for returns: the calibration in
# measure_predictor_accuracy reports all three, the run report prints all
# three, and EAP_PREDICTOR_LAG_DAYS above is fixed before any return exists.
EAP_PREDICTOR_LAG_CANDIDATES: tuple[int, ...] = (364, 365, 371)

# A predicted announcement whose "slot" the firm has ALREADY filled -- i.e.
# an actual announcement observed within this many calendar days of the
# predicted date and on or before the decision date -- is suppressed. Without
# this, a firm that reports a few days EARLY than last year would be predicted
# to announce again days after it just did. 30 days is comfortably under the
# ~91-day quarterly spacing, so it can never suppress a genuinely different
# quarter's announcement.
EAP_SLOT_FILLED_WINDOW_DAYS = 30


@dataclass(frozen=True)
class AnnouncementDay:
    """One ACTUAL announcement, mapped to the first trading session that
    could have reacted to it (cross_sectional_pead.announcement_day0,
    reused unchanged: acceptance before 16:00 ET -> that session, at/after
    16:00 ET or missing -> the next one, the never-early direction)."""

    ticker: str
    day0_position: int
    day0_date: date


@dataclass(frozen=True)
class PredictedAnnouncement:
    """One EX-ANTE prediction: the firm is expected to announce at
    `predicted_position`, on the strength of `source_date` (its own
    announcement `lag_days` earlier). `known_from_position` is the day 0 of
    that source announcement -- the first session on which this prediction
    could have been made at all. Nothing here reads a filing later than
    known_from_position."""

    ticker: str
    predicted_position: int
    predicted_date: date
    source_position: int
    source_date: date
    known_from_position: int


def build_announcement_calendar(
    index: pd.DatetimeIndex,
    events: list[EarningsEvent],
    min_gap_trading_days: int = EAP_DUPLICATE_FILING_GAP_TRADING_DAYS,
) -> tuple[dict[str, list[AnnouncementDay]], dict[str, int]]:
    """{ticker: ascending actual announcement days}, plus {reason: count}
    for what was dropped. Two filings within min_gap_trading_days rows are
    one announcement and the FIRST wins -- an amended or follow-up 2.02 is
    not a second event, and letting it through would put a phantom extra
    date on the firm's calendar and, one year later, a phantom extra
    PREDICTION."""
    rejected: dict[str, int] = {}

    def _reject(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    by_ticker: dict[str, list[AnnouncementDay]] = {}
    for event in sorted(events, key=lambda e: (e.ticker, e.filing_date, e.accession)):
        day0 = announcement_day0(event, index)
        if day0 is None:
            _reject("announcement beyond loaded price history")
            continue
        existing = by_ticker.setdefault(event.ticker, [])
        if existing and day0 - existing[-1].day0_position <= min_gap_trading_days:
            _reject("duplicate filing within gap")
            continue
        existing.append(
            AnnouncementDay(
                ticker=event.ticker, day0_position=day0, day0_date=index[day0].date()
            )
        )
    for days in by_ticker.values():
        days.sort(key=lambda d: d.day0_position)
    return by_ticker, rejected


def _first_row_at_or_after(index: pd.DatetimeIndex, target: date) -> int | None:
    position = int(
        np.searchsorted(index.values, pd.Timestamp(target).to_datetime64(), side="left")
    )
    return None if position >= len(index) else position


def predict_announcements(
    calendar: dict[str, list[AnnouncementDay]],
    index: pd.DatetimeIndex,
    lag_days: int = EAP_PREDICTOR_LAG_DAYS,
    slot_filled_window_days: int = EAP_SLOT_FILLED_WINDOW_DAYS,
    min_gap_trading_days: int = EAP_DUPLICATE_FILING_GAP_TRADING_DAYS,
) -> dict[str, list[PredictedAnnouncement]]:
    """{ticker: ascending ex-ante predicted announcements}. Each ACTUAL
    announcement generates exactly one prediction `lag_days` later, known
    from that announcement's own day 0.

    Two predictions landing within min_gap_trading_days rows of each other
    are one predicted announcement (the earlier source wins), mirroring the
    de-dup applied to the actual calendar.

    NOTE ON THE SUPPRESSION RULE: it is applied at REPLAY time, not here,
    because "has this firm already announced for this quarter?" depends on
    the decision date and this function returns a decision-date-independent
    object. See suppressed_by_actual_announcement."""
    predicted: dict[str, list[PredictedAnnouncement]] = {}
    for ticker, days in calendar.items():
        rows: list[PredictedAnnouncement] = []
        for source in days:
            target = source.day0_date + timedelta(days=lag_days)
            position = _first_row_at_or_after(index, target)
            if position is None:
                continue
            if rows and position - rows[-1].predicted_position <= min_gap_trading_days:
                continue
            rows.append(
                PredictedAnnouncement(
                    ticker=ticker,
                    predicted_position=position,
                    predicted_date=index[position].date(),
                    source_position=source.day0_position,
                    source_date=source.day0_date,
                    known_from_position=source.day0_position,
                )
            )
        if rows:
            predicted[ticker] = rows
    return predicted


def suppressed_by_actual_announcement(
    prediction: PredictedAnnouncement,
    actual_days: list[AnnouncementDay],
    decision_position: int,
    slot_filled_window_days: int = EAP_SLOT_FILLED_WINDOW_DAYS,
) -> bool:
    """True when, as of `decision_position`, this firm has ALREADY made an
    actual announcement for the quarter this prediction was aiming at --
    i.e. an announcement whose day 0 is at or before the decision date and
    within slot_filled_window_days calendar days of the predicted date.

    Strictly point-in-time: only announcements with day0_position <=
    decision_position are consulted. The prediction's OWN source
    announcement sits ~`lag_days` earlier and so can never trigger this."""
    for day in actual_days:
        if day.day0_position > decision_position:
            break
        if abs((day.day0_date - prediction.predicted_date).days) <= slot_filled_window_days:
            return True
    return False


@dataclass
class PredictorAccuracy:
    """How well the ex-ante predictor actually locates real announcements.
    A DATA-QUALITY measurement, containing no return of any kind -- see the
    pre-registration for why running it before the grid was frozen is not a
    p-hacking route."""

    lag_days: int
    n_predictions: int
    n_matched: int
    # Signed (actual - predicted) error in TRADING days, over matched pairs.
    mean_error_days: float
    median_error_days: float
    mean_abs_error_days: float
    median_abs_error_days: float
    # Fraction of matched pairs whose actual announcement fell within +/- k
    # trading days of the prediction, k = 0,1,2,3,5,7,10.
    hit_rate_within: dict[int, float]
    # Fraction of ALL predictions with no actual announcement anywhere
    # within EAP_PREDICTOR_MATCH_WINDOW_TRADING_DAYS -- a prediction for an
    # announcement that never came (de-listing, calendar change, a 2.02
    # that was not really quarterly earnings).
    unmatched_fraction: float


# Widest distance at which a prediction is still considered to be ABOUT a
# given actual announcement rather than a different quarter's. 45 trading
# days is ~9 weeks, comfortably inside the ~63-trading-day quarterly spacing.
EAP_PREDICTOR_MATCH_WINDOW_TRADING_DAYS = 45


def measure_predictor_accuracy(
    calendar: dict[str, list[AnnouncementDay]],
    index: pd.DatetimeIndex,
    lag_days: int,
    first_position: int = 0,
    last_position: int | None = None,
) -> PredictorAccuracy:
    """Matches every prediction to the NEAREST actual announcement by the
    same ticker and reports the signed trading-day error distribution.

    Reported honestly whatever it shows: this number is the single largest
    determinant of whether this family can work at all, since a position
    opened around a badly-predicted date holds a name through an ordinary
    week rather than through its announcement."""
    predicted = predict_announcements(calendar, index, lag_days=lag_days)
    horizon = len(index) - 1 if last_position is None else last_position
    errors: list[int] = []
    n_predictions = 0
    n_unmatched = 0
    for ticker, rows in predicted.items():
        actual_positions = [d.day0_position for d in calendar.get(ticker, [])]
        if not actual_positions:
            continue
        actual_array = np.asarray(actual_positions)
        for row in rows:
            if not (first_position <= row.predicted_position <= horizon):
                continue
            n_predictions += 1
            deltas = actual_array - row.predicted_position
            nearest = int(np.argmin(np.abs(deltas)))
            error = int(deltas[nearest])
            if abs(error) > EAP_PREDICTOR_MATCH_WINDOW_TRADING_DAYS:
                n_unmatched += 1
                continue
            errors.append(error)

    if not errors:
        return PredictorAccuracy(
            lag_days=lag_days,
            n_predictions=n_predictions,
            n_matched=0,
            mean_error_days=float("nan"),
            median_error_days=float("nan"),
            mean_abs_error_days=float("nan"),
            median_abs_error_days=float("nan"),
            hit_rate_within={},
            unmatched_fraction=1.0 if n_predictions else 0.0,
        )
    array = np.asarray(errors, dtype=float)
    return PredictorAccuracy(
        lag_days=lag_days,
        n_predictions=n_predictions,
        n_matched=len(errors),
        mean_error_days=float(array.mean()),
        median_error_days=float(np.median(array)),
        mean_abs_error_days=float(np.abs(array).mean()),
        median_abs_error_days=float(np.median(np.abs(array))),
        hit_rate_within={
            k: float((np.abs(array) <= k).mean()) for k in (0, 1, 2, 3, 5, 7, 10)
        },
        unmatched_fraction=n_unmatched / n_predictions if n_predictions else 0.0,
    )


# ===========================================================================
# THE TRADED BOOK
# ===========================================================================

# A firm needs at least this many of its OWN past announcements before any
# prediction about it is traded. Two jobs, one gate: (a) a predictor built
# from one or two observed announcements is not a calendar, and (b) the
# announcement-volatility weighting needs a real sample to estimate from.
# Applied UNIFORMLY to every spec in the grid -- including the equal-weighted
# ones, which do not need (b) -- so that all eight specs trade the IDENTICAL
# population and differ only in window and weights. Without that uniformity
# the eight Sharpes would not be comparable and the sigma_SR feeding the DSR
# would be measuring universe differences rather than spec differences.
EAP_MIN_PRIOR_ANNOUNCEMENTS = 4

# Past announcements entering the announcement-volatility basis (the most
# recent this many, i.e. ~2 years of quarterly reports).
EAP_VOL_BASIS_ANNOUNCEMENTS = 8

# The announcement-window whose realized move the basis measures:
# close(day0 - 1) -> close(day0 + 1), the standard three-day announcement
# window, in EXCESS of the benchmark over the same window (the excess is
# what makes it firm-specific news rather than a market move).
EAP_VOL_BASIS_WINDOW: tuple[int, int] = (-1, 1)


@dataclass(frozen=True)
class EapSpec:
    """One pre-declared definition. Deliberately NOT a
    cross_sectional.CrossSectionalSpec, for the same reason
    cross_sectional_pead.PeadSpec is not: that type's required fields
    (signal_fn, lookback_days, rank_fraction) describe a periodic
    universe-scan ranked on a signal, and this family ranks nothing -- it
    selects on a CALENDAR."""

    pattern_id: str
    family: str
    citation: str
    days_before: int
    days_after: int
    leg_weighting: str  # "equal" | "ann_vol"


@dataclass
class EapConfig:
    """Market conventions, split from the specs exactly as
    CrossSectionalConfig / PeadConfig split them."""

    # One-way cost in bps charged on L1 turnover of the NET book. 5.0 =
    # cross_sectional.DEFAULT_XS_COST_BPS, this project's conservative
    # equity control rate; the pre-registered sensitivity ladder
    # (EAP_COST_SENSITIVITY_BPS) carries the sourced realistic levels.
    cost_bps: float = DEFAULT_XS_COST_BPS
    # 0.0 = the equity families' shared, DISCLOSED optimism (no observable
    # borrow feed; a known OPEN paid-data item for this project).
    financing_bps_per_year: float = 0.0
    impute_delisting_returns: bool = True
    imputed_delisting_return: float = DEFAULT_IMPUTED_DELISTING_RETURN


@dataclass(frozen=True)
class TradedWindow:
    """One predicted announcement turned into a position: on at the close of
    entry_position, off at the close of exit_position. Both are fixed the
    moment the window is opened and NEITHER depends on the announcement
    actually arriving, or on anything it says -- that is the whole point of
    this family."""

    ticker: str
    predicted_position: int
    predicted_date: date
    entry_position: int
    exit_position: int
    vol_basis: float


@dataclass
class WindowCounts:
    n_predictions: int = 0
    n_before_formation: int = 0
    n_off_index: int = 0
    n_thin_history: int = 0
    n_slot_already_filled: int = 0
    n_not_member: int = 0
    n_no_price: int = 0
    n_no_vol_basis: int = 0
    n_traded: int = 0
    # DIAGNOSTIC, never a filter: how many traded windows actually contained
    # the firm's real announcement. Computed with hindsight and used for
    # REPORTING ONLY -- it is not consulted anywhere in position formation.
    n_caught_actual: int = 0


def build_announcement_vol_basis(
    close: pd.DataFrame,
    benchmark: pd.Series,
    calendar: dict[str, list[AnnouncementDay]],
    window: tuple[int, int] = EAP_VOL_BASIS_WINDOW,
    n_announcements: int = EAP_VOL_BASIS_ANNOUNCEMENTS,
) -> dict[str, list[tuple[int, float]]]:
    """{ticker: [(day0_position, mean |excess announcement-window return|
    over the most recent `n_announcements` announcements COMPLETED at or
    before that day0)]} -- the risk basis the "ann_vol" specs weight by.

    Savor & Wilson's mechanism is a COMPENSATION FOR RISK BORNE, so the
    theory-implied weighting is PROPORTIONAL to a firm's announcement-window
    risk, not inverse to it (which is what a generic inverse-vol weighting
    would do). Mean ABSOLUTE excess return rather than a standard deviation:
    with only 8 observations the mean absolute deviation is the more stable
    of the two, and the quantity wanted is the typical SIZE of the
    announcement move, not its dispersion about a mean nobody believes.

    Point-in-time by construction: the value stamped at a given day0 reads
    only announcement windows that had already CLOSED by then, and the
    replay looks up each event's basis as of its own entry."""
    index_len = len(close.index)
    start_offset, end_offset = window
    basis: dict[str, list[tuple[int, float]]] = {}
    for ticker, days in calendar.items():
        if ticker not in close.columns:
            continue
        prices = close[ticker].to_numpy()
        bench = benchmark.to_numpy()
        magnitudes: list[float] = []
        rows: list[tuple[int, float]] = []
        for day in days:
            window_start = day.day0_position + start_offset - 1
            window_end = day.day0_position + end_offset
            if window_start < 0 or window_end >= index_len:
                continue
            p0, p1 = prices[window_start], prices[window_end]
            b0, b1 = bench[window_start], bench[window_end]
            if not (np.isfinite(p0) and np.isfinite(p1) and np.isfinite(b0) and np.isfinite(b1)):
                continue
            if p0 <= 0.0 or b0 <= 0.0:
                continue
            magnitudes.append(abs(float(p1 / p0 - b1 / b0)))
            recent = magnitudes[-n_announcements:]
            # Stamped at the window's CLOSE, not at day 0: the observation
            # is not complete until then.
            rows.append((window_end, float(np.mean(recent))))
        if rows:
            basis[ticker] = rows
    return basis


def _basis_as_of(rows: list[tuple[int, float]], position: int, min_obs: int) -> float:
    """The most recent basis value stamped strictly at or before `position`,
    or NaN when fewer than `min_obs` announcement windows had closed by
    then. Linear scan from the right; the per-ticker lists are short (tens
    of entries) and this keeps the point-in-time rule obvious."""
    count = 0
    value = float("nan")
    for stamp, magnitude in rows:
        if stamp > position:
            break
        count += 1
        value = magnitude
    return value if count >= min_obs else float("nan")


def build_traded_windows(
    close: pd.DataFrame,
    calendar: dict[str, list[AnnouncementDay]],
    predicted: dict[str, list[PredictedAnnouncement]],
    vol_basis: dict[str, list[tuple[int, float]]],
    formation_start: date,
    formation_end: date,
    days_before: int,
    days_after: int,
    membership: pd.DataFrame,
) -> tuple[list[TradedWindow], WindowCounts]:
    """Every prediction that clears the ex-ante gates, as a dated position.

    THE GATES, in order, each counted and none of them a performance filter:
      * the entry close must sit inside the formation window and the price
        index;
      * the prediction's SOURCE announcement must already have happened
        (point-in-time -- by construction it did, asserted anyway);
      * the firm must have EAP_MIN_PRIOR_ANNOUNCEMENTS observed
        announcements by the entry close;
      * the firm must not have ALREADY announced for this quarter (see
        suppressed_by_actual_announcement);
      * the firm must be a point-in-time index member at the entry close;
      * it must have a usable price at entry and a usable announcement-vol
        basis (applied to every spec, see EAP_MIN_PRIOR_ANNOUNCEMENTS).
    """
    counts = WindowCounts()
    index = close.index
    n = len(index)
    windows: list[TradedWindow] = []
    for ticker, rows in predicted.items():
        actual = calendar.get(ticker, [])
        actual_positions = np.asarray([d.day0_position for d in actual]) if actual else None
        basis_rows = vol_basis.get(ticker, [])
        has_price = ticker in close.columns
        prices = close[ticker].to_numpy() if has_price else None
        for prediction in rows:
            counts.n_predictions += 1
            entry = prediction.predicted_position - days_before - 1
            exit_position = prediction.predicted_position + days_after
            if entry < 0 or exit_position > n - 1:
                counts.n_off_index += 1
                continue
            entry_date = index[entry].date()
            if entry_date < formation_start or entry_date > formation_end:
                counts.n_before_formation += 1
                continue
            assert prediction.known_from_position <= entry, (
                f"{ticker}: prediction known_from {prediction.known_from_position} is AFTER its "
                f"own entry row {entry} -- this family's point-in-time guarantee is that a "
                "prediction is generated by an announcement a year earlier, so this is impossible "
                "unless the predictor was changed."
            )
            n_prior = 0
            if actual_positions is not None:
                n_prior = int((actual_positions <= entry).sum())
            if n_prior < EAP_MIN_PRIOR_ANNOUNCEMENTS:
                counts.n_thin_history += 1
                continue
            if suppressed_by_actual_announcement(prediction, actual, entry):
                counts.n_slot_already_filled += 1
                continue
            if ticker not in membership.columns or not bool(membership[ticker].iloc[entry]):
                counts.n_not_member += 1
                continue
            if not has_price or prices is None or not np.isfinite(prices[entry]):
                counts.n_no_price += 1
                continue
            basis_value = _basis_as_of(basis_rows, entry, EAP_MIN_PRIOR_ANNOUNCEMENTS)
            if not np.isfinite(basis_value) or basis_value <= 0.0:
                counts.n_no_vol_basis += 1
                continue
            counts.n_traded += 1
            if actual_positions is not None and (
                ((actual_positions > entry) & (actual_positions <= exit_position)).any()
            ):
                counts.n_caught_actual += 1
            windows.append(
                TradedWindow(
                    ticker=ticker,
                    predicted_position=prediction.predicted_position,
                    predicted_date=prediction.predicted_date,
                    entry_position=entry,
                    exit_position=exit_position,
                    vol_basis=basis_value,
                )
            )
    windows.sort(key=lambda w: (w.entry_position, w.ticker))
    return windows, counts


@dataclass
class EapBacktestResult:
    """One spec's replay. GROSS returns and TURNOVER are stored separately
    from any net series so that the whole pre-declared cost ladder
    (EAP_COST_SENSITIVITY_BPS) is derived from ONE position path rather
    than from re-running the book at each cost level -- the positions are
    identical by construction, and re-running them would invite a silent
    divergence between the sensitivity table and the headline."""

    status: str  # "ok" | "no_windows" | "insufficient_history"
    gross_daily_returns: pd.Series
    daily_turnover: pd.Series
    daily_gross_notional: pd.Series
    n_windows_entered: int = 0
    n_windows_delisted_mid_hold: int = 0
    n_invested_days: int = 0
    n_one_sided_days: int = 0
    n_weight_fallback_days: int = 0
    mean_long_leg_size: float = 0.0
    mean_short_leg_size: float = 0.0
    max_long_leg_size: int = 0
    min_long_leg_size: int = 0
    # Mean daily L1 turnover split four ways, so a reader can see whether
    # the cost that decides this family's verdict is REAL trading or an
    # artifact of how the book is normalized. Buckets:
    #   long_inout   a name entering or leaving the long leg -- unavoidable,
    #                it is the strategy.
    #   long_drift   weight change among names STAYING long, because the leg
    #                is 1.0 of notional over a membership that swings with
    #                the reporting season. Design-dependent: a fixed
    #                per-name notional would avoid most of it.
    #   short_inout  a name crossing between the universe short and the long
    #                leg -- also unavoidable, it is the same trade seen from
    #                the other side.
    #   short_drift  pure renormalization of the ~400-name universe short as
    #                its membership count ticks. The one bucket that is
    #                mostly an accounting artifact.
    #   flat_unwind  unwinding the whole book on a day the long leg empties
    #                out (flat by design). Charged, so it is explained here
    #                rather than left as an unexplained residual.
    # Buckets are means over EVERY day of the return series and sum exactly
    # to daily_turnover.mean() -- asserted by a test.
    turnover_decomposition: dict[str, float] = field(default_factory=dict)


def net_daily_returns(
    replay: EapBacktestResult, cost_bps: float, financing_bps_per_year: float
) -> pd.Series:
    """gross - turnover*cost - financing, on the stored position path. The
    single place cost is applied, so the headline and every sensitivity
    column are guaranteed to describe the same book."""
    gross = replay.gross_daily_returns
    if gross.empty:
        return gross
    cost = replay.daily_turnover * (cost_bps / 10_000.0)
    financing = pd.Series(0.0, index=gross.index)
    if financing_bps_per_year:
        per_day = (financing_bps_per_year / 10_000.0) / FINANCING_DAYS_PER_YEAR
        calendar_days = pd.Series(
            gross.index.to_series().diff().dt.days.fillna(1.0).to_numpy(),
            index=gross.index,
        )
        financing = replay.daily_gross_notional * per_day * calendar_days
    return gross - cost - financing


def run_eap_backtest(
    close: pd.DataFrame,
    windows: list[TradedWindow],
    membership: pd.DataFrame,
    spec: EapSpec,
    config: EapConfig,
) -> EapBacktestResult:
    """The daily replay. Each traded window is 1 unit of LONG-leg notional
    from the close of its entry_position through the close of its
    exit_position; the SHORT leg is every OTHER point-in-time index member
    with a usable return that day, equal-weighted.

    WHY THE SHORT LEG IS ALWAYS EQUAL-WEIGHTED, whatever the long leg does:
    it is "the rest of the universe", over which no ranking exists. This is
    cross_sectional._target_weights' own stated rule for its
    long_universe_hedged portfolio -- "no rank cutoff exists for 'the whole
    universe', so that side is never magnitude-weighted" -- reused rather
    than re-decided.

    A day on which either leg is empty is 0.0 BY DESIGN and counted
    (n_one_sided_days), never traded as a naked single leg -- the same
    convention cross_sectional_pead.run_pead_backtest states. Both legs
    carry a constant signal (every name in a leg embodies the same
    hypothesis), so _resolve_leg_weights' documented tie behavior makes the
    basis-weighting fallback degrade to equal weight."""
    if not windows:
        empty = pd.Series(dtype=float)
        return EapBacktestResult(
            status="no_windows",
            gross_daily_returns=empty,
            daily_turnover=empty,
            daily_gross_notional=empty,
        )

    index = close.index
    n = len(index)
    first_entry = min(w.entry_position for w in windows)
    if first_entry >= n - 1:
        empty = pd.Series(dtype=float)
        return EapBacktestResult(
            status="insufficient_history",
            gross_daily_returns=empty,
            daily_turnover=empty,
            daily_gross_notional=empty,
        )

    returns = close.pct_change(fill_method=None)
    columns = list(close.columns)
    returns_array = returns.to_numpy(dtype=float)
    membership_array = (
        membership.reindex(columns=columns).fillna(False).to_numpy(dtype=bool)
    )

    delisting_by_position: dict[int, list[str]] = {}
    if config.impute_delisting_returns:
        for ticker, position in _compute_delisting_positions(close).items():
            delisting_by_position.setdefault(position, []).append(ticker)

    open_at: dict[int, list[TradedWindow]] = {}
    for window in windows:
        open_at.setdefault(window.entry_position, []).append(window)

    active: dict[str, TradedWindow] = {}
    previous_weights: dict[str, float] = {}

    dates: list[pd.Timestamp] = []
    gross_values: list[float] = []
    turnovers: list[float] = []
    notionals: list[float] = []
    n_invested = 0
    n_one_sided = 0
    n_fallback = 0
    n_delisted = 0
    decomposition: dict[str, float] = {
        "long_inout": 0.0,
        "long_drift": 0.0,
        "short_inout": 0.0,
        "short_drift": 0.0,
        "flat_unwind": 0.0,
    }
    long_sizes: list[int] = []
    short_sizes: list[int] = []

    for j in range(first_entry + 1, n):
        for window in open_at.get(j - 1, ()):
            active[window.ticker] = window

        day_returns = returns_array[j].copy()
        delisting_today = delisting_by_position.get(j)
        if delisting_today:
            for ticker in delisting_today:
                position = columns.index(ticker)
                day_returns[position] = config.imputed_delisting_return
                if ticker in active:
                    n_delisted += 1

        finite = np.isfinite(day_returns)
        eligible_mask = membership_array[j] & finite
        long_tickers = sorted(t for t in active if finite[columns.index(t)])
        long_set = set(long_tickers)
        short_tickers = [
            columns[i] for i in np.flatnonzero(eligible_mask) if columns[i] not in long_set
        ]

        day_series = pd.Series(day_returns, index=columns)

        if not long_tickers or not short_tickers:
            n_one_sided += 1
            dates.append(index[j])
            gross_values.append(0.0)
            # A flat book trades nothing, so it also pays nothing; the
            # turnover of unwinding into flat is charged on the day the
            # book comes back on, via the weight diff below.
            unwind = _turnover_l1(previous_weights, {})
            turnovers.append(unwind)
            decomposition["flat_unwind"] += unwind
            notionals.append(0.0)
            previous_weights = {}
        else:
            long_signal = pd.Series(0.0, index=long_tickers, dtype=float)
            long_basis = None
            if spec.leg_weighting == "ann_vol":
                long_basis = pd.Series(
                    {t: active[t].vol_basis for t in long_tickers}, dtype=float
                )
            long_weights, long_fallback = _resolve_leg_weights(
                long_tickers,
                long_signal,
                higher_is_stronger=True,
                leg_weighting=(
                    "equal" if spec.leg_weighting == "equal" else "inverse_vol"
                ),
                market_cap=None,
                weight_basis=long_basis,
            )
            short_weights, _ = _resolve_leg_weights(
                short_tickers,
                pd.Series(0.0, index=short_tickers, dtype=float),
                higher_is_stronger=True,
                leg_weighting="equal",
                market_cap=None,
                weight_basis=None,
            )
            if long_fallback:
                n_fallback += 1

            gross = _leg_weighted_return(day_series, long_weights) - _leg_weighted_return(
                day_series, short_weights
            )
            net_weights: dict[str, float] = dict(long_weights)
            for ticker, weight in short_weights.items():
                net_weights[ticker] = net_weights.get(ticker, 0.0) - weight

            n_invested += 1
            long_sizes.append(len(long_tickers))
            short_sizes.append(len(short_tickers))
            dates.append(index[j])
            gross_values.append(gross)
            turnovers.append(_turnover_l1(previous_weights, net_weights))
            _accumulate_turnover_decomposition(
                decomposition, previous_weights, net_weights, long_weights, short_weights
            )
            notionals.append(2.0)
            previous_weights = net_weights

        for ticker in list(active):
            if j >= active[ticker].exit_position or (
                delisting_today and ticker in delisting_today
            ):
                del active[ticker]

    date_index = pd.DatetimeIndex(dates)
    return EapBacktestResult(
        status="ok",
        gross_daily_returns=pd.Series(gross_values, index=date_index, dtype=float),
        daily_turnover=pd.Series(turnovers, index=date_index, dtype=float),
        daily_gross_notional=pd.Series(notionals, index=date_index, dtype=float),
        n_windows_entered=len(windows),
        n_windows_delisted_mid_hold=n_delisted,
        n_invested_days=n_invested,
        n_one_sided_days=n_one_sided,
        n_weight_fallback_days=n_fallback,
        mean_long_leg_size=float(np.mean(long_sizes)) if long_sizes else 0.0,
        mean_short_leg_size=float(np.mean(short_sizes)) if short_sizes else 0.0,
        max_long_leg_size=int(np.max(long_sizes)) if long_sizes else 0,
        min_long_leg_size=int(np.min(long_sizes)) if long_sizes else 0,
        turnover_decomposition={
            bucket: (value / len(dates) if dates else 0.0)
            for bucket, value in decomposition.items()
        },
    )


def _accumulate_turnover_decomposition(
    into: dict[str, float],
    old: dict[str, float],
    new: dict[str, float],
    long_weights: dict[str, float],
    short_weights: dict[str, float],
) -> None:
    """Splits one day's L1 turnover across the four buckets documented on
    EapBacktestResult.turnover_decomposition. Every ticker's |delta| lands in
    exactly one bucket, so the buckets sum to that day's total turnover --
    asserted by a test, because a decomposition that does not reconcile to
    the number it explains is worse than none."""
    for ticker in set(old) | set(new):
        delta = abs(new.get(ticker, 0.0) - old.get(ticker, 0.0))
        if not delta:
            continue
        previous = old.get(ticker, 0.0)
        if ticker in long_weights:
            into["long_drift" if previous > 0.0 else "long_inout"] += delta
        elif ticker in short_weights:
            into["short_drift" if previous < 0.0 else "short_inout"] += delta
        else:
            # Dropped from the book entirely this day; it left whichever leg
            # it was in.
            into["long_inout" if previous > 0.0 else "short_inout"] += delta


def _turnover_l1(old: dict[str, float], new: dict[str, float]) -> float:
    """L1 distance between two net-weight books -- cross_sectional._turnover's
    own definition, restated here because that function is keyed to the
    harness's formation loop rather than to a daily one."""
    tickers = set(old) | set(new)
    return float(sum(abs(new.get(t, 0.0) - old.get(t, 0.0)) for t in tickers))


# ===========================================================================
# THE PRE-DECLARED FAMILY
# ===========================================================================
#
# Levels are fixed in data/research_runs/earnings_announcement_premium_
# PREREGISTRATION.txt and asserted against the built list below, so a size
# drift is a loud import-time failure rather than a silent change to every
# future run's DSR denominator.

# Trading days BEFORE the predicted announcement at which the position is
# opened. 1 = the minimal ex-ante entry (on at the close of the session
# before the predicted announcement session); 5 = a full week of
# accumulation, which is what a real book with a noisy calendar would need.
EAP_DAYS_BEFORE: tuple[int, ...] = (1, 5)

# Trading days AFTER the predicted announcement at which the position is
# closed. The window must SPAN the announcement for the premium to be
# earned at all, and the predictor is not exact, so this axis is what buys
# tolerance for calendar error.
EAP_DAYS_AFTER: tuple[int, ...] = (1, 5)

# "equal" = the harness's own equal mode. "ann_vol" = weight PROPORTIONAL to
# the firm's own trailing announcement-window risk, which is the weighting
# Savor & Wilson's risk mechanism implies (compensation scales with risk
# borne). Note this is the OPPOSITE of a generic inverse-vol weighting; it
# rides the harness's generic weight_basis path, whose mode is named
# "inverse_vol" for historical reasons but performs no inversion of its own.
EAP_LEG_WEIGHTINGS: tuple[str, ...] = ("equal", "ann_vol")

EAP_N_TRIALS = len(EAP_DAYS_BEFORE) * len(EAP_DAYS_AFTER) * len(EAP_LEG_WEIGHTINGS)

# The project's OWN sourced cost ladder for an equal-weighted S&P 500 book,
# adopted verbatim from data/research_runs/edge_cost_reaudit_corrected_
# PREREGISTRATION.txt section 2 rather than re-derived here: 1.0bp
# (2015-regime tight bound), 2.0bp (that document's best estimate for this
# exact universe), 3.5bp (conservative bound covering vol spikes and the
# departed-member illiquidity skew), 5.0bp (= DEFAULT_XS_COST_BPS, the
# project's existing control rate and THIS FAMILY'S HEADLINE).
EAP_COST_SENSITIVITY_BPS: tuple[float, ...] = (0.0, 1.0, 2.0, 3.5, 5.0)

EAP_CITATION = (
    "Savor & Wilson, 'Earnings Announcements and Systematic Risk' (Journal of Finance 71(1), "
    "2016, pp. 83-138, doi:10.1111/jofi.12361); Barber, De George, Lehavy & Trueman, 'The "
    "earnings announcement premium around the globe' (Journal of Financial Economics 108(1), "
    "2013, pp. 118-138, doi:10.1016/j.jfineco.2012.10.006); Lamont & Frazzini, 'The Earnings "
    "Announcement Premium and Trading Volume' (NBER Working Paper 13090, 2007, "
    "doi:10.3386/w13090); Beaver, 'The Information Content of Annual Earnings Announcements' "
    "(Journal of Accounting Research 6, 1968, pp. 67-92)"
)


def _build_eap_family() -> list[EapSpec]:
    specs: list[EapSpec] = []
    for before in EAP_DAYS_BEFORE:
        for after in EAP_DAYS_AFTER:
            for weighting in EAP_LEG_WEIGHTINGS:
                specs.append(
                    EapSpec(
                        pattern_id=f"eap_b{before}_a{after}_{weighting}",
                        family=EAP_FAMILY_NAME,
                        citation=EAP_CITATION,
                        days_before=before,
                        days_after=after,
                        leg_weighting=weighting,
                    )
                )
    assert len(specs) == EAP_N_TRIALS, (
        f"EAP family has {len(specs)} definitions, not the pre-declared {EAP_N_TRIALS} -- this "
        "family's entire point is being an exact, fixed enumeration of days_before x days_after x "
        "leg_weighting (see the pre-registration); a size drift here silently changes n_trials for "
        "every future run."
    )
    assert len({s.pattern_id for s in specs}) == len(specs), "pattern_ids must be unique"
    assert all(s.family == EAP_FAMILY_NAME for s in specs)
    assert {s.days_before for s in specs} == set(EAP_DAYS_BEFORE)
    assert {s.days_after for s in specs} == set(EAP_DAYS_AFTER)
    assert {s.leg_weighting for s in specs} == set(EAP_LEG_WEIGHTINGS)
    return specs


EAP_FAMILY: list[EapSpec] = _build_eap_family()


@dataclass
class EapScreeningResult:
    pattern_id: str
    family: str
    citation: str
    days_before: int
    days_after: int
    leg_weighting: str
    n_windows_traded: int
    n_windows_caught_actual: int
    caught_actual_fraction: float
    n_windows_delisted_mid_hold: int
    n_trading_days: int
    n_invested_days: int
    n_one_sided_days: int
    invested_fraction: float
    mean_long_leg_size: float
    max_long_leg_size: int
    min_long_leg_size: int
    mean_short_leg_size: float
    mean_daily_turnover: float
    sharpe_annualized: float
    gross_sharpe_annualized: float
    total_cost_drag: float
    total_financing_drag: float
    net_cumulative_return: float
    cost_sensitivity_sharpe: dict[float, float]
    subperiod_sharpes: list[float]
    deflated_sharpe: DeflatedSharpeResult
    n_weight_fallback_days: int = 0
    window_counts: dict[str, int] = field(default_factory=dict)
    turnover_decomposition: dict[str, float] = field(default_factory=dict)


def _subperiod_sharpes(returns: pd.Series, n_parts: int = 3) -> list[float]:
    """Sharpe of each of `n_parts` equal contiguous slices -- the same
    stability diagnostic the eigenportfolio family reports. A slice too
    short to annualize honestly returns NaN rather than a number."""
    if len(returns) < n_parts * MIN_REPLAY_TRADING_DAYS:
        return [float("nan")] * n_parts
    edges = np.linspace(0, len(returns), n_parts + 1).astype(int)
    return [
        float(sharpe_ratio(returns.iloc[edges[i] : edges[i + 1]]))
        for i in range(n_parts)
    ]


def build_membership_frame(
    index: pd.DatetimeIndex, tickers: list[str]
) -> pd.DataFrame:
    """Boolean (dates x tickers) point-in-time S&P 500 membership.

    Dates AFTER sp500_membership_history.membership_coverage_end() are
    masked ALL-FALSE rather than filled with today's roster -- substituting
    the present-day membership at the recent end is exactly what would
    silently reintroduce survivorship bias, and this is the convention the
    eigenportfolio family already established for the same boundary.

    Dates BEFORE MEMBERSHIP_DATA_START are masked ALL-FALSE for the mirror
    reason. This band is real and is not a formation region: the price panel
    deliberately starts ~18 months before the first formation so the
    predictor and the announcement-volatility basis can warm up, and
    get_universe_as_of raises PointInTimeUniverseError there rather than
    guessing. All-False is the honest answer -- nothing is tradeable on a
    date whose index membership is unknown."""
    coverage_end = membership_coverage_end()
    frame = pd.DataFrame(False, index=index, columns=tickers)
    for timestamp in index:
        as_of = timestamp.date()
        if as_of > coverage_end or as_of < MEMBERSHIP_DATA_START:
            continue
        members = [t for t in get_universe_as_of(as_of) if t in frame.columns]
        if members:
            frame.loc[timestamp, members] = True
    return frame


# The placebo shifts every predicted announcement by this many CALENDAR days
# -- roughly half a quarter, so a placebo window lands in the quiet middle of
# a reporting cycle where no announcement is scheduled. Pre-declared as a
# FALSIFICATION CONTROL, not a spec: if the placebo book earns what the real
# book earns, whatever is being measured is not about announcements.
EAP_PLACEBO_SHIFT_CALENDAR_DAYS = 45


@dataclass
class EapPlaceboResult:
    status: str
    sharpe_annualized: float
    gross_sharpe_annualized: float
    n_trading_days: int
    n_windows_traded: int
    caught_actual_fraction: float


@dataclass(frozen=True)
class EapSampleDisclosure:
    """Sample-construction and independence facts as typed data, recomputed
    from the real inputs on every run."""

    n_tickers_requested: int
    n_tickers_cik_resolved: int
    n_tickers_fetched: int
    n_tickers_coverage_starts_late: int
    n_raw_events: int
    n_tickers_priced: int
    n_announcements_calendared: int
    calendar_rejections: dict[str, int]
    predictor_accuracy: dict[int, PredictorAccuracy]
    first_announcement: date | None
    last_announcement: date | None
    text: str


@dataclass
class EapScreeningSummary:
    results: list[EapScreeningResult]
    placebo: dict[str, EapPlaceboResult]
    missing_price_data: list[str]
    sample: EapSampleDisclosure
    cost_disclosure: str


def _build_cost_disclosure(config: EapConfig) -> str:
    return (
        f"COST DISCLOSURE. {config.cost_bps:.1f}bp ONE-WAY charged on the L1 turnover of the NET "
        f"book every day (cross_sectional.DEFAULT_XS_COST_BPS, this project's conservative equity "
        f"control rate, used as the HEADLINE). The pre-declared sensitivity ladder "
        f"{EAP_COST_SENSITIVITY_BPS} is adopted verbatim from this project's own sourced "
        f"calibration in data/research_runs/edge_cost_reaudit_corrected_PREREGISTRATION.txt "
        f"section 2 (1.0bp tight bound, 2.0bp BEST ESTIMATE for an equal-weighted S&P 500 book, "
        f"3.5bp conservative bound); it was NOT re-derived here. THIS FAMILY IS TURNOVER-HEAVY BY "
        f"CONSTRUCTION -- the long leg is rebuilt every few days as firms rotate through their "
        f"announcement windows -- so cost is the single most load-bearing assumption in the whole "
        f"result and the sensitivity table must be read before any Sharpe. Financing: "
        f"{config.financing_bps_per_year}bp/yr -- the equity families' shared convention and the "
        f"SAME DISCLOSED OPTIMISM documented in cross_sectional.py: the short leg's real borrow "
        f"cost is unobservable with this project's free data, and a real securities-borrow feed is "
        f"a known OPEN paid-data item. Market impact and commissions are NOT modelled, so true "
        f"costs are HIGHER than the reported drag at every level of the ladder."
    )


def screen_eap_family(
    close: pd.DataFrame,
    benchmark: pd.Series,
    events: list[EarningsEvent],
    membership: pd.DataFrame,
    formation_start: date,
    formation_end: date,
    config: EapConfig,
    specs: list[EapSpec] | None = None,
) -> tuple[
    list[EapScreeningResult],
    dict[str, list[AnnouncementDay]],
    dict[str, int],
    dict[str, EapPlaceboResult],
]:
    """One Sharpe per spec, DSR-corrected for the family's PRE-DECLARED
    size. n_trials is len(specs) -- the family's literal declared size,
    never shrunk to however many specs happened to clear the data floors.
    sigma_sr is the ddof=1 std of every sibling spec's own Sharpe from this
    same pass.

    The calendar, the predictions and the announcement-volatility basis are
    computed ONCE and shared: they do not depend on the spec axes."""
    specs = specs if specs is not None else EAP_FAMILY
    n_trials = len(specs)

    calendar, calendar_rejections = build_announcement_calendar(close.index, events)
    predicted = predict_announcements(calendar, close.index)
    vol_basis = build_announcement_vol_basis(close, benchmark, calendar)

    replays: dict[str, tuple[EapBacktestResult, WindowCounts]] = {}
    for spec in specs:
        windows, counts = build_traded_windows(
            close,
            calendar,
            predicted,
            vol_basis,
            formation_start,
            formation_end,
            spec.days_before,
            spec.days_after,
            membership,
        )
        replay = run_eap_backtest(close, windows, membership, spec, config)
        if replay.status != "ok" or len(replay.gross_daily_returns) < MIN_REPLAY_TRADING_DAYS:
            logger.warning(
                "%s produced no replayable series (status=%s, days=%d)",
                spec.pattern_id,
                replay.status,
                len(replay.gross_daily_returns),
            )
            continue
        replays[spec.pattern_id] = (replay, counts)

    net_by_id = {
        pattern_id: net_daily_returns(
            replay, config.cost_bps, config.financing_bps_per_year
        )
        for pattern_id, (replay, _counts) in replays.items()
    }
    sharpes = {pid: sharpe_ratio(series) for pid, series in net_by_id.items()}
    sigma_sr = (
        float(np.std(list(sharpes.values()), ddof=1)) if len(sharpes) >= 2 else None
    )

    spec_by_id = {spec.pattern_id: spec for spec in specs}
    results: list[EapScreeningResult] = []
    for pattern_id, (replay, counts) in replays.items():
        spec = spec_by_id[pattern_id]
        net = net_by_id[pattern_id]
        n_days = len(net)
        cost_rate = config.cost_bps / 10_000.0
        results.append(
            EapScreeningResult(
                pattern_id=pattern_id,
                family=spec.family,
                citation=spec.citation,
                days_before=spec.days_before,
                days_after=spec.days_after,
                leg_weighting=spec.leg_weighting,
                n_windows_traded=counts.n_traded,
                n_windows_caught_actual=counts.n_caught_actual,
                caught_actual_fraction=(
                    counts.n_caught_actual / counts.n_traded if counts.n_traded else 0.0
                ),
                n_windows_delisted_mid_hold=replay.n_windows_delisted_mid_hold,
                n_trading_days=n_days,
                n_invested_days=replay.n_invested_days,
                n_one_sided_days=replay.n_one_sided_days,
                invested_fraction=(replay.n_invested_days / n_days) if n_days else 0.0,
                mean_long_leg_size=replay.mean_long_leg_size,
                max_long_leg_size=replay.max_long_leg_size,
                min_long_leg_size=replay.min_long_leg_size,
                mean_short_leg_size=replay.mean_short_leg_size,
                mean_daily_turnover=float(replay.daily_turnover.mean()),
                sharpe_annualized=sharpes[pattern_id],
                gross_sharpe_annualized=float(sharpe_ratio(replay.gross_daily_returns)),
                total_cost_drag=float(replay.daily_turnover.sum() * cost_rate),
                total_financing_drag=float(
                    (replay.gross_daily_returns - net).sum()
                    - replay.daily_turnover.sum() * cost_rate
                ),
                net_cumulative_return=float((1.0 + net).prod() - 1.0),
                cost_sensitivity_sharpe={
                    level: float(
                        sharpe_ratio(
                            net_daily_returns(
                                replay, level, config.financing_bps_per_year
                            )
                        )
                    )
                    for level in EAP_COST_SENSITIVITY_BPS
                },
                subperiod_sharpes=_subperiod_sharpes(net),
                deflated_sharpe=compute_deflated_sharpe(
                    sharpes[pattern_id], net, n_trials, sigma_sr
                ),
                n_weight_fallback_days=replay.n_weight_fallback_days,
                turnover_decomposition=replay.turnover_decomposition,
                window_counts={
                    "n_predictions": counts.n_predictions,
                    "n_off_index": counts.n_off_index,
                    "n_outside_formation": counts.n_before_formation,
                    "n_thin_history": counts.n_thin_history,
                    "n_slot_already_filled": counts.n_slot_already_filled,
                    "n_not_member": counts.n_not_member,
                    "n_no_price": counts.n_no_price,
                    "n_no_vol_basis": counts.n_no_vol_basis,
                    "n_traded": counts.n_traded,
                },
            )
        )

    placebo = _run_placebo(
        close, calendar, vol_basis, membership, formation_start, formation_end, config, specs
    )
    results.sort(key=lambda r: r.sharpe_annualized, reverse=True)
    return results, calendar, calendar_rejections, placebo


def _run_placebo(
    close: pd.DataFrame,
    calendar: dict[str, list[AnnouncementDay]],
    vol_basis: dict[str, list[tuple[int, float]]],
    membership: pd.DataFrame,
    formation_start: date,
    formation_end: date,
    config: EapConfig,
    specs: list[EapSpec],
) -> dict[str, EapPlaceboResult]:
    """The pre-declared FALSIFICATION CONTROL: the identical machinery on a
    calendar shifted EAP_PLACEBO_SHIFT_CALENDAR_DAYS forward, so every
    window lands mid-quarter where nothing is scheduled. Not a spec, not in
    n_trials -- it is the thing this family must be shown not to be."""
    shifted = predict_announcements(
        calendar, close.index, lag_days=EAP_PREDICTOR_LAG_DAYS + EAP_PLACEBO_SHIFT_CALENDAR_DAYS
    )
    out: dict[str, EapPlaceboResult] = {}
    for spec in specs:
        windows, counts = build_traded_windows(
            close,
            calendar,
            shifted,
            vol_basis,
            formation_start,
            formation_end,
            spec.days_before,
            spec.days_after,
            membership,
        )
        replay = run_eap_backtest(close, windows, membership, spec, config)
        if replay.status != "ok" or len(replay.gross_daily_returns) < MIN_REPLAY_TRADING_DAYS:
            out[spec.pattern_id] = EapPlaceboResult(
                status=replay.status,
                sharpe_annualized=float("nan"),
                gross_sharpe_annualized=float("nan"),
                n_trading_days=len(replay.gross_daily_returns),
                n_windows_traded=counts.n_traded,
                caught_actual_fraction=0.0,
            )
            continue
        net = net_daily_returns(replay, config.cost_bps, config.financing_bps_per_year)
        out[spec.pattern_id] = EapPlaceboResult(
            status="ok",
            sharpe_annualized=float(sharpe_ratio(net)),
            gross_sharpe_annualized=float(sharpe_ratio(replay.gross_daily_returns)),
            n_trading_days=len(net),
            n_windows_traded=counts.n_traded,
            caught_actual_fraction=(
                counts.n_caught_actual / counts.n_traded if counts.n_traded else 0.0
            ),
        )
    return out


def build_eap_sample_disclosure(
    fetch: CalendarFetchReport,
    n_raw_events: int,
    n_tickers_priced: int,
    calendar: dict[str, list[AnnouncementDay]],
    calendar_rejections: dict[str, int],
    predictor_accuracy: dict[int, PredictorAccuracy],
) -> EapSampleDisclosure:
    all_days = [d for days in calendar.values() for d in days]
    dates = sorted(d.day0_date for d in all_days)
    chosen = predictor_accuracy.get(EAP_PREDICTOR_LAG_DAYS)
    accuracy_line = (
        "PREDICTOR ACCURACY NOT MEASURED THIS RUN."
        if chosen is None
        else (
            f"THE PREDICTOR IS THE WHOLE BALL GAME, so its measured accuracy leads this "
            f"disclosure. Over {chosen.n_predictions:,} ex-ante predictions at the declared "
            f"{EAP_PREDICTOR_LAG_DAYS}-day lag, {chosen.n_matched:,} matched a real announcement "
            f"within {EAP_PREDICTOR_MATCH_WINDOW_TRADING_DAYS} trading days and "
            f"{chosen.unmatched_fraction:.1%} matched nothing at all. Median absolute error "
            f"{chosen.median_abs_error_days:.1f} trading days; mean signed error "
            f"{chosen.mean_error_days:+.2f} days. Share of matched predictions landing within "
            f"+/-1 day: {chosen.hit_rate_within.get(1, float('nan')):.1%}; within +/-3 days: "
            f"{chosen.hit_rate_within.get(3, float('nan')):.1%}; within +/-5 days: "
            f"{chosen.hit_rate_within.get(5, float('nan')):.1%}. A window that MISSES the real "
            f"announcement holds an ordinary week of an ordinary stock and cannot earn an "
            f"announcement premium, so every Sharpe below is diluted by exactly this miss rate -- "
            f"the per-spec caught_actual_fraction column reports the realized dilution."
        )
    )
    text = (
        f"EARNINGS-ANNOUNCEMENT-PREMIUM SAMPLE DISCLOSURE -- read before trusting any Sharpe or "
        f"DSR below. {accuracy_line} "
        f"UNIVERSE: {fetch.n_tickers_requested} tickers that were S&P 500 members on any day of "
        f"the point-in-time membership window (sp500_membership_history.get_universe_over), NOT a "
        f"present-day snapshot; {fetch.n_tickers_cik_resolved} resolved a CIK in SEC's own mapping "
        f"file, {fetch.n_tickers_fetched} returned a submissions JSON, and "
        f"{fetch.n_tickers_coverage_starts_late} have EDGAR coverage beginning after the requested "
        f"fetch start even after filings.files pagination, so their early-sample predictions "
        f"cannot exist. {n_raw_events:,} 8-K Item 2.02 filings were found in-window and "
        f"{len(all_days):,} survived de-duplication into a clean announcement calendar "
        f"({calendar_rejections}); {n_tickers_priced} tickers resolved yfinance prices. "
        f"RESIDUAL SURVIVORSHIP, NOT FIXED BY THE POINT-IN-TIME GATE: membership makes the ROSTER "
        f"honest, not the PRICES -- this project has no delisted-securities price vendor, so the "
        f"names that vanished (the acquired and the failed) are disproportionately unpriceable and "
        f"their absence FLATTERS every number below. INDEPENDENCE: earnings cluster hard into four "
        f"reporting seasons a year, so the long leg is near-empty for weeks and then holds "
        f"hundreds of names at once; consecutive daily returns share most of their constituents "
        f"and the daily observation count feeding the Sharpe and the DSR OVERSTATES the "
        f"independent information by a large and unquantified factor. That is a SEPARATE caution "
        f"from the DSR's own n_trials={EAP_N_TRIALS} multiple-comparisons correction, and neither "
        f"substitutes for the other."
    )
    return EapSampleDisclosure(
        n_tickers_requested=fetch.n_tickers_requested,
        n_tickers_cik_resolved=fetch.n_tickers_cik_resolved,
        n_tickers_fetched=fetch.n_tickers_fetched,
        n_tickers_coverage_starts_late=fetch.n_tickers_coverage_starts_late,
        n_raw_events=n_raw_events,
        n_tickers_priced=n_tickers_priced,
        n_announcements_calendared=len(all_days),
        calendar_rejections=calendar_rejections,
        predictor_accuracy=predictor_accuracy,
        first_announcement=dates[0] if dates else None,
        last_announcement=dates[-1] if dates else None,
        text=text,
    )


EAP_BENCHMARK_TICKER = "SPY"


def run_eap_screening(
    start: date,
    end: date,
    provider=None,
    config: EapConfig | None = None,
    events: list[EarningsEvent] | None = None,
    fetch_report: CalendarFetchReport | None = None,
    tickers: list[str] | None = None,
    fetch_start: date | None = None,
) -> EapScreeningSummary:
    """THE production entry point.

    `start` must be >= MEMBERSHIP_DATA_START: every window is gated by
    point-in-time membership, and was_member answers a silent False before
    coverage begins. Formations are additionally capped at
    membership_coverage_end() -- past it, get_universe_as_of cannot answer
    and this module masks the dates ALL-FALSE rather than substituting
    today's roster.

    Pass `events` (+ `fetch_report`) to reuse a cached EDGAR pass; omitting
    them fetches live, rate-limited under SEC's published fair-access cap."""
    from app.services.market_data.yfinance_provider import YFinanceProvider

    if start < MEMBERSHIP_DATA_START:
        raise ValueError(
            f"EAP screening start {start.isoformat()} predates point-in-time membership coverage "
            f"({MEMBERSHIP_DATA_START.isoformat()}) -- the membership gate would silently answer "
            "False for every window before it."
        )
    provider = provider if provider is not None else YFinanceProvider()
    config = config if config is not None else EapConfig()
    coverage_end = membership_coverage_end()
    formation_end = min(end, coverage_end)
    universe = (
        tickers
        if tickers is not None
        else get_universe_over(MEMBERSHIP_DATA_START, coverage_end)
    )
    # Prices and filings both start well before the first formation: the
    # predictor needs a prior year of the firm's own calendar, and the
    # announcement-volatility basis needs several completed windows.
    price_start = fetch_start if fetch_start is not None else start
    if events is None:
        events, fetch_report = fetch_announcement_calendar(universe, price_start, end)
    if fetch_report is None:
        fetch_report = CalendarFetchReport(n_tickers_requested=len(universe))
    n_raw = len(events)

    event_tickers = sorted({e.ticker for e in events})
    frames, missing = provider.get_daily_ohlcv(event_tickers, price_start, end)
    if not frames:
        sample = build_eap_sample_disclosure(fetch_report, n_raw, 0, {}, {}, {})
        return EapScreeningSummary(
            results=[],
            placebo={},
            missing_price_data=missing,
            sample=sample,
            cost_disclosure=_build_cost_disclosure(config),
        )
    close = frames["close"]

    bench_frames, bench_missing = provider.get_daily_ohlcv(
        [EAP_BENCHMARK_TICKER], price_start, end
    )
    if (
        bench_missing
        or not bench_frames
        or EAP_BENCHMARK_TICKER not in bench_frames["close"].columns
    ):
        raise ValueError(
            f"The {EAP_BENCHMARK_TICKER} benchmark resolved no price data. The announcement-"
            "volatility basis is defined in EXCESS of it, so without it the weighting axis does "
            "not exist -- failing loudly rather than silently weighting on raw announcement "
            "moves, which would be a market-direction-contaminated quantity."
        )
    benchmark = bench_frames["close"][EAP_BENCHMARK_TICKER].reindex(close.index)

    membership = build_membership_frame(close.index, list(close.columns))
    results, calendar, calendar_rejections, placebo = screen_eap_family(
        close, benchmark, events, membership, start, formation_end, config
    )
    accuracy = {
        lag: measure_predictor_accuracy(calendar, close.index, lag)
        for lag in EAP_PREDICTOR_LAG_CANDIDATES
    }
    sample = build_eap_sample_disclosure(
        fetch_report, n_raw, len(close.columns), calendar, calendar_rejections, accuracy
    )
    return EapScreeningSummary(
        results=results,
        placebo=placebo,
        missing_price_data=missing,
        sample=sample,
        cost_disclosure=_build_cost_disclosure(config),
    )
