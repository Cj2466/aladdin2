"""FINRA BI-MONTHLY EQUITY SHORT INTEREST — the real, free, public file, and
the point-in-time contract that makes it usable in a backtest.

Every factual claim in this docstring was verified LIVE against FINRA on
2026-09-02 during this module's build; nothing here is recalled from memory
or inferred from plausibility. Where a claim came into the build as a
premise and did NOT survive verification, the correction is recorded rather
than quietly applied — see section 2, which contains one such correction
that materially changes what this data can be used for.

=======================================================================
1. WHAT THE FILE IS
=======================================================================

FINRA Rule 4560 requires member firms to report their short positions
twice a month. FINRA aggregates them per security and publishes one
pipe-delimited file per reporting cycle at

    https://cdn.finra.org/equity/otcmarket/biweekly/shrt<YYYYMMDD>.csv

where <YYYYMMDD> is the cycle's SETTLEMENT date. Fetched live 2026-09-02;
the 2026-08-14 file is 2,195,139 bytes and 22,482 rows.

THE FOURTEEN COLUMNS, verified by reading the real header rather than a
schema document:

    accountingYearMonthNumber | symbolCode | issueName
    issuerServicesGroupExchangeCode | marketClassCode
    currentShortPositionQuantity | previousShortPositionQuantity
    stockSplitFlag | averageDailyVolumeQuantity | daysToCoverQuantity
    revisionFlag | changePercent | changePreviousNumber | settlementDate

THE THREE THIS MODULE READS, with FINRA's own glossary definitions
(https://www.finra.org/finra-data/browse-catalog/equity-short-interest/
glossary, fetched 2026-09-02), quoted verbatim:

 * currentShortPositionQuantity — "The total number of shares in the issue
   that are reflected on the books and records of the reporting firms as
   short as defined by Rule 200 of Regulation SHO as of the current cycle's
   designated settlement date."

 * averageDailyVolumeQuantity — "Total Volume or Adjusted Volume in case of
   splits / Total trade days between (previous settlement date + 1) to
   (current settlement date)."

   READ THAT DEFINITION CAREFULLY, because it is the single most useful
   property of this file for a point-in-time backtest: the volume figure is
   computed over a window that ENDS at the settlement date. It is strictly
   TRAILING. It is also split-adjusted by FINRA itself. So this one file
   carries both a short-interest LEVEL and a contemporaneous
   TRADING-ACTIVITY measure, on the same security, over the same cycle,
   released at the same instant — which means a signal that needs both
   needs no second data source, no share-count vendor, and no split
   reconciliation between two providers. See cross_sectional_short_
   interest.py section 3 for why that mattered to the family's design.

 * settlementDate — the cycle's designated settlement date, ISO format in
   the file. Constant within a file (verified: all 22,482 rows of the
   2026-08-14 file carry 2026-08-14).

daysToCoverQuantity is NOT read: it is exactly the ratio of the two fields
above ("The number of days of average share volume it would require to buy
all of the shares that were sold short during the reporting cycle"), and
recomputing it from its own inputs lets this module apply its own
non-positive-denominator guard rather than trusting a vendor's rounding —
the published field is given to 2 decimal places, which is a coarse
quantization for a cross-sectional RANKING variable (thousands of ties).

=======================================================================
2. COVERAGE — WHERE THIS MODULE'S BUILD BRIEF WAS WRONG, AND THE
   CORRECTION, WHICH IS THE MOST IMPORTANT PARAGRAPH IN THIS FILE
=======================================================================

FINRA's own catalog page carries the note: "Prior to June 2021, the data
contains short interest positions in over-the-counter securities only and
does not reflect short interest data in exchange-listed securities"
(https://www.finra.org/finra-data/browse-catalog/equity-short-interest/
files, fetched 2026-09-02). This family's build brief took that note at
face value and scoped the whole candidate around it, as an available free
history of roughly 5.2 years.

THAT NOTE DOES NOT DESCRIBE WHAT THIS ENDPOINT SERVES TODAY. Verified by
downloading and parsing the real files:

    shrt20171229.csv  15,495 rows  marketClassCode: NYSE 3,102 / NNM 2,355
                      / ARCA 1,433 / SC 854 / AMEX 347 / BZX 235
                      / OTC 7,152 / OTCBB 17
                      AAPL present: 45,746,430 shares short, ADV 23,901,107

    shrt20180131.csv  15,627 rows, AAPL present
    shrt20190115.csv  15,812 rows, AAPL present
    shrt20200115.csv  16,246 rows, AAPL present
    shrt20210430.csv  19,913 rows, AAPL present

Exchange-listed securities are present in every one of those files, years
before the stated June-2021 boundary. A full anchor-walk-back probe of
every candidate settlement date from 2014 to today found 208 files, the
earliest 2017-12-29 and the latest 2026-08-14, with a complete 24 cycles
in every one of 2018-2025 and no interior gaps.

WHAT THIS MEANS, AND THE HONEST LIMIT OF IT. The usable free history is
2017-12-29..2026-08-14 — about 8.7 years, not 5.2. That is a materially
better sample than the candidate was scoped against, and it is REAL data,
verified by parsing it. But the near-certain explanation for the
discrepancy is that FINRA RETROACTIVELY BACKFILLED consolidated
(exchange-listed + OTC) files onto this endpoint when it took over
consolidated publication in 2021, replacing the OTC-only files that
originally sat at these URLs.

The pre-June-2021 exchange-listed rows are therefore data that WAS public
at the time — the listing exchanges (NYSE, Nasdaq) disseminated their own
semi-monthly short interest on the same statutory cycle — but NOT
necessarily data that was public AT THIS URL IN THIS FORM at the time.
That distinction is a real one and it is disclosed rather than papered
over. An attempt to verify contemporaneous availability through the
Internet Archive found NO snapshot of any pre-2021 file at this path
(archive.org's CDX index returns snapshots only from 2023 onward), so the
question COULD NOT BE SETTLED either way and is left open here rather than
resolved by assertion.

Nothing in this module depends on which answer is right. The consequence
is a disclosure the consuming family must carry, not a code path.

=======================================================================
3. THE POINT-IN-TIME CONTRACT — PUBLICATION_LAG_CALENDAR_DAYS
=======================================================================

A settlement date is NOT an availability date, and the gap is large enough
that ignoring it would be a straightforward look-ahead bug rather than a
rounding error.

FINRA's rule, from its own reporting page (https://www.finra.org/filing-
reporting/regulatory-filing-systems/short-interest, fetched 2026-09-02):
firms must report "by 6 p.m. Eastern Time on the second business day after
the reporting settlement date", and FINRA then "disseminates aggregate
short interest information seven business days after the reporting
settlement date".

Seven BUSINESS days is an awkward quantity to reimplement correctly (it
needs a market-holiday calendar that agrees with FINRA's, over nine years),
and getting it wrong in the optimistic direction is precisely a look-ahead.
So this module does not reimplement it. It uses a CALENDAR-day bound chosen
to DOMINATE the real schedule under every holiday configuration FINRA
itself publishes.

The full published 2026 schedule (24 rows, fetched 2026-09-02) has a
settlement-to-publication gap ranging from 9 to 12 calendar days:

    Jan 15 -> Jan 27 (12)    Jul 15 -> Jul 24  (9)
    Jan 30 -> Feb 10 (11)    Jul 31 -> Aug 11 (11)
    Feb 13 -> Feb 25 (12)    Aug 14 -> Aug 25 (11)
    Feb 27 -> Mar 10 (11)    Aug 31 -> Sep 10 (10)
    Mar 13 -> Mar 24 (11)    Sep 15 -> Sep 24  (9)
    Mar 31 -> Apr 10 (10)    Sep 30 -> Oct  9  (9)
    Apr 15 -> Apr 24  (9)    Oct 15 -> Oct 26 (11)
    Apr 30 -> May 11 (11)    Oct 30 -> Nov 10 (11)
    May 15 -> May 27 (12)    Nov 13 -> Nov 24 (11)
    May 29 -> Jun  9 (11)    Nov 30 -> Dec  9  (9)
    Jun 15 -> Jun 25 (10)    Dec 15 -> Dec 24  (9)
    Jun 30 -> Jul 10 (10)    Dec 31 -> Jan 12 (12)

PUBLICATION_LAG_CALENDAR_DAYS = 14 therefore exceeds the worst published
gap by two full days, in a year containing every US market holiday. It is
deliberately CONSERVATIVE: it can only ever make the signal STALER than it
really was, never fresher. The cost is bounded and small — at most ~5 days
of extra staleness on a variable that only refreshes every ~15 days — and
it buys a guarantee that no formation in any run can read a short-interest
figure before the public could.

This bound is unit-tested directly against the 24 published 2026 rows
above (test_finra_short_interest_provider.py), so a future change to it
cannot silently drop below the real schedule.

INDEPENDENT LIVE CORROBORATION that the lag is real and material, observed
2026-09-02: the 2026-08-14 settlement file was downloadable (published Aug
25), while the 2026-08-31 settlement file returned HTTP 403 — it is
scheduled to publish 2026-09-10 and did not exist yet. The lag is not a
formality; two full weeks of the most recent short interest is genuinely
unavailable at any moment.

=======================================================================
4. SETTLEMENT-DATE RESOLUTION AND SYMBOLOGY
=======================================================================

SETTLEMENT DATES are "the 15th of each month" and the last day of the
month, each walked BACK to the preceding business day when it lands on a
weekend or holiday (verified against the published 2026 schedule: the
"August 14 (Friday)" row is the 15th walked back over a Saturday; "May 29
(Friday)" is the 31st walked back over a Sunday; "March 31 (Tuesday)" is
untouched). Rather than hard-coding a holiday calendar, this module walks
each anchor back up to WALK_BACK_MAX_DAYS business days and takes the FIRST
date for which a file actually exists — resolution by observation, not by
assumption. A cycle with no file at any offset is reported, never
interpolated.

SYMBOLOGY. FINRA symbols carry NO separator for share classes: this
project's BRK-B is FINRA's BRKB and BF-B is BFB (verified against the real
issueName fields, "BERKSHIRE HATHAWAY Class B" and "Brown-Forman
Corporation Class"). No symbol in any parsed file contains "." or "-" at
all. `finra_symbol` therefore strips both separators, and the consuming
family MEASURES its realized per-cycle match rate rather than assuming one.

THE SEPARATOR-STRIP IS ONLY EVER A FALLBACK, never a first choice: a
direct symbol match wins, and the stripped form is consulted only when the
direct form is absent from that cycle. Stripping can in principle collide
(a hypothetical "AB-C" stripping onto an unrelated real "ABC"), so the
resolution order matters and is tested.

A PROPERTY WORTH STATING BECAUSE THE SIBLING EDGAR FAMILIES LACK IT: these
files are PER-DATE SNAPSHOTS keyed on the ticker as it existed on that
settlement date. A company that was renamed, acquired or delisted in 2020
still appears, under its real 2020 ticker, in the 2020 files. There is no
"current-day ticker map" to resolve through, so the failure mode that lost
XOM from the EDGAR-based quality families (a CIK re-registration breaking a
present-day lookup) has no analogue here. Departed index members are
covered for exactly the cycles in which they really traded.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

FINRA_SHORT_INTEREST_URL = "https://cdn.finra.org/equity/otcmarket/biweekly/shrt{stamp}.csv"

# Default on-disk cache for the raw pipe-delimited files, next to the
# project's other refetchable vendor caches (see backend/.gitignore, which
# excludes this directory for the same reason it excludes
# data/edgar_companyfacts/: ~366MB of vendor input, not results).
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "finra_short_interest"

# See module docstring section 3. Chosen to DOMINATE FINRA's published
# schedule (worst observed gap 12 calendar days), never to approximate it.
PUBLICATION_LAG_CALENDAR_DAYS = 14

# The first settlement date this endpoint serves, established by probing
# every candidate anchor from 2014 forward (module docstring section 2).
EARLIEST_SETTLEMENT_DATE = date(2017, 12, 29)

# How far back an anchor (the 15th, or the month's last day) may be walked
# to find the real settlement date. The longest US market-holiday run
# adjacent to a weekend is 3 calendar days (e.g. a Friday holiday before a
# weekend), so 6 is comfortable slack, and a miss is reported rather than
# guessed at.
WALK_BACK_MAX_DAYS = 6

FINRA_RETRY_ATTEMPTS = 3
FINRA_RETRY_BASE_DELAY_SECONDS = 1.0

# A declared-bot User-Agent, the same courtesy EdgarXbrlProvider extends to
# SEC. FINRA's CDN does not publish a fair-access policy the way SEC does,
# so this is politeness rather than compliance with a stated rule.
DEFAULT_USER_AGENT = "aladdin2-research/1.0 (autoa0792@gmail.com)"

# A real file is ~1.5-2.2MB. Anything dramatically smaller is a truncated
# download or an error document that happened to return HTTP 200, and must
# not be cached as if it were data.
MIN_PLAUSIBLE_FILE_BYTES = 100_000


class FinraShortInterestFetchError(RuntimeError):
    """A settlement-date file could not be retrieved after every retry."""


@dataclass(frozen=True)
class ShortInterestObservation:
    """One security's short interest for one reporting cycle, plus the two
    dates that make it usable point-in-time.

    `available` is the date from which a backtest may READ this value — the
    settlement date plus PUBLICATION_LAG_CALENDAR_DAYS (module docstring
    section 3) — and is precomputed here rather than left to each consumer,
    because a consumer that forgets it produces a silent look-ahead rather
    than an error."""

    symbol: str
    settlement_date: date
    available: date
    short_shares: float
    average_daily_volume: float
    market_class: str
    # FINRA's own stockSplitFlag for this cycle ("S" -> True). Carried
    # through rather than acted on here, because whether a split matters
    # depends on the consumer: a days-to-cover ratio is internally
    # consistent (both its inputs are this cycle's, both split-adjusted by
    # FINRA per the glossary), while a ratio against an EXTERNAL share count
    # from an earlier date is corrupted by the split factor. The consuming
    # family decides; this provider only reports.
    # Measured population: 348 flagged rows across 11 sampled cycles of
    # ~20,000 securities each.
    split_flagged: bool = False

    @property
    def days_to_cover(self) -> float:
        """Short interest expressed in days of the cycle's own average
        volume. Recomputed from the two raw fields rather than read from the
        vendor's 2-decimal `daysToCoverQuantity` — see module docstring
        section 1. The parser guarantees average_daily_volume > 0, so this
        cannot divide by zero."""
        return self.short_shares / self.average_daily_volume


@dataclass
class ShortInterestFetchDiagnostics:
    """Everything a reader needs to judge how complete a fetch really was.
    Counted, never assumed — the same discipline the quality families'
    summaries keep."""

    n_cycles_requested: int = 0
    n_cycles_resolved: int = 0
    unresolved_anchors: list[date] = field(default_factory=list)
    n_rows_parsed: int = 0
    n_rows_refused: dict[str, int] = field(default_factory=dict)
    # ticker -> number of cycles in which it was matched by stripping a
    # share-class separator rather than directly. Reported so a silent
    # symbology collision is visible.
    separator_stripped_matches: dict[str, int] = field(default_factory=dict)

    def refuse(self, reason: str) -> None:
        self.n_rows_refused[reason] = self.n_rows_refused.get(reason, 0) + 1


def finra_symbol(ticker: str) -> str:
    """This project's symbology -> FINRA's. BRK-B -> BRKB, BF-B -> BFB.

    Verified against real files (module docstring section 4): no symbol in
    any parsed FINRA file contains "." or "-". Callers must treat the result
    as a FALLBACK only, after a direct match fails."""
    return ticker.replace("-", "").replace(".", "")


def settlement_anchors(start: date, end: date) -> list[date]:
    """The nominal semi-monthly reporting anchors in [start, end]: the 15th
    and the final calendar day of each month. These are NOT settlement dates
    — a weekend or holiday anchor is walked back by the resolver — but they
    are the fixed, assumption-free grid the resolver walks from."""
    anchors: list[date] = []
    year, month = start.year, start.month
    while date(year, month, 1) <= end:
        last_day = (date(year + (month // 12), (month % 12) + 1, 1) - timedelta(days=1)).day
        for day in (15, last_day):
            anchor = date(year, month, day)
            if start <= anchor <= end:
                anchors.append(anchor)
        year, month = year + (month // 12), (month % 12) + 1
    return sorted(anchors)


def publication_date(settlement: date) -> date:
    """The date from which a settlement cycle's figures may be read. See
    module docstring section 3 — deliberately a conservative calendar bound
    over FINRA's seven-business-day rule, never an approximation of it."""
    return settlement + timedelta(days=PUBLICATION_LAG_CALENDAR_DAYS)


class FinraShortInterestProvider:
    """Fetches, caches and parses FINRA's bi-monthly short interest files.

    The cache is a plain directory of the raw vendor files under their own
    settlement-stamped names. An archived reporting cycle is IMMUTABLE
    except for the rare same-cycle revision FINRA flags in `revisionFlag`
    (5 of 22,482 rows in the 2026-08-14 file), so unlike the EDGAR
    companyfacts cache this one needs no age bound — a cached file is the
    file. Delete a file to force a refetch.
    """

    def __init__(
        self,
        cache_dir: Path | str | None = DEFAULT_CACHE_DIR,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._session = session if session is not None else requests.Session()
        self._session.headers.update({"User-Agent": user_agent})
        self._sleep = sleep

    # --- raw file access -----------------------------------------------

    def _cache_path(self, settlement: date) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"shrt{settlement:%Y%m%d}.csv"

    @staticmethod
    def _write_cache_atomically(cache_path: Path, payload: bytes) -> None:
        """Publish through a temp file + os.replace so a concurrent reader
        can only ever see a complete file — the same discipline
        EdgarXbrlProvider._write_cache_atomically keeps, and it matters more
        here because five agents share one checkout's data directory."""
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=cache_path.parent, suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            os.replace(tmp_path, cache_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def file_exists(self, settlement: date) -> bool:
        """Whether a file exists for this settlement date, cache first then
        a real HEAD. This is how the resolver decides an anchor's true
        settlement date — by observation (module docstring section 4)."""
        cache_path = self._cache_path(settlement)
        if cache_path is not None and cache_path.exists():
            return cache_path.stat().st_size >= MIN_PLAUSIBLE_FILE_BYTES
        url = FINRA_SHORT_INTEREST_URL.format(stamp=f"{settlement:%Y%m%d}")
        try:
            response = self._session.head(url, timeout=45)
        except requests.RequestException:
            return False
        return response.status_code == 200

    def fetch_raw(self, settlement: date) -> str:
        """The raw pipe-delimited text for one settlement date, cached.

        Raises FinraShortInterestFetchError rather than returning a partial
        or empty document — a caller that silently accepted an error page
        would produce a cycle in which every security looks unranked, which
        is indistinguishable from a real market event at read time."""
        cache_path = self._cache_path(settlement)
        if cache_path is not None and cache_path.exists():
            if cache_path.stat().st_size >= MIN_PLAUSIBLE_FILE_BYTES:
                return cache_path.read_text(encoding="utf-8", errors="replace")
            logger.warning("discarding implausibly small cached FINRA file %s", cache_path)

        url = FINRA_SHORT_INTEREST_URL.format(stamp=f"{settlement:%Y%m%d}")
        last_error: Exception | None = None
        for attempt in range(1, FINRA_RETRY_ATTEMPTS + 1):
            try:
                response = self._session.get(url, timeout=120)
                response.raise_for_status()
                payload = response.content
                if len(payload) < MIN_PLAUSIBLE_FILE_BYTES:
                    raise FinraShortInterestFetchError(
                        f"{url} returned only {len(payload)} bytes; a real cycle file is >1MB"
                    )
                if cache_path is not None:
                    self._write_cache_atomically(cache_path, payload)
                return payload.decode("utf-8", errors="replace")
            except Exception as error:  # noqa: BLE001 — retried, then re-raised below
                last_error = error
                if attempt < FINRA_RETRY_ATTEMPTS:
                    self._sleep(FINRA_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        raise FinraShortInterestFetchError(
            f"failed after {FINRA_RETRY_ATTEMPTS} attempts: {url}"
        ) from last_error

    # --- resolution ----------------------------------------------------

    def resolve_settlement_dates(self, start: date, end: date) -> tuple[list[date], list[date]]:
        """(resolved settlement dates, anchors that resolved to nothing).

        Walks each anchor back up to WALK_BACK_MAX_DAYS days and takes the
        first date whose file really exists. Anchors before
        EARLIEST_SETTLEMENT_DATE are skipped without probing — the endpoint
        genuinely serves nothing there and probing them would be ~150
        pointless requests against FINRA's CDN."""
        resolved: list[date] = []
        unresolved: list[date] = []
        for anchor in settlement_anchors(start, end):
            if anchor + timedelta(days=WALK_BACK_MAX_DAYS) < EARLIEST_SETTLEMENT_DATE:
                continue
            for back in range(WALK_BACK_MAX_DAYS + 1):
                candidate = anchor - timedelta(days=back)
                if candidate < start or candidate.weekday() >= 5:
                    continue
                if self.file_exists(candidate):
                    resolved.append(candidate)
                    break
            else:
                unresolved.append(anchor)
        # A walk-back can in principle land two anchors on one date; dedupe
        # so a cycle is never counted or parsed twice.
        return sorted(set(resolved)), unresolved

    # --- parsing -------------------------------------------------------

    def parse_cycle(
        self,
        raw: str,
        symbols: set[str] | None = None,
        diagnostics: ShortInterestFetchDiagnostics | None = None,
    ) -> dict[str, ShortInterestObservation]:
        """One cycle's rows, keyed by FINRA symbol, restricted to `symbols`
        when given.

        REFUSALS, all counted and never silent:
         * `non_positive_volume` — averageDailyVolumeQuantity <= 0 or blank.
           2,759 of 19,471 rows in the 2024-05-15 file are like this, almost
           entirely dormant OTC issues. (The date was corrected from
           "2026-05-15" by independent verification 2026-09-02: both counts
           reproduce exactly against shrt20240515.csv and against no other
           cached cycle. The 2026-05-15 file really has 21,896 rows and 2,783
           such rows.) There is no meaningful days-to-cover
           for a security that did not trade, and dividing by it would rank
           an untraded name at the extreme of the cross-section.
         * `non_positive_short_interest` — a zero or blank short position.
           Zero is a legitimate reading in principle, but it is
           indistinguishable in this file from "not reported", and a zero
           numerator pins a name to the long leg's extreme on what may be an
           absence of data. Refused rather than trusted.
         * `unparseable_number` / `missing_settlement_date` — malformed rows.

        The settlement date is read from the ROW, not from the filename the
        caller asked for: the file is authoritative about its own cycle.

        QUOTE_NONE IS LOAD-BEARING, NOT A STYLE CHOICE, and it was found the
        hard way during this build. FINRA's files are pipe-delimited with NO
        quoting, and `issueName` contains LITERAL double-quote characters —
        e.g. `ELEMENTS "Dogs of the Dow" Tot`, present in 68 of the 208
        cached cycle files. Python's csv module defaults to QUOTE_MINIMAL,
        which reads that first `"` as opening a quoted field and then
        swallows every delimiter and newline until the next one. On the real
        data that surfaced as `_csv.Error: field larger than field limit`,
        which is the LUCKY outcome; the unlucky one is a file whose quotes
        happen to balance, where the reader silently merges rows and emits
        plausible-looking values for the wrong security. QUOTE_NONE is the
        correct reading of the format and is pinned by a regression test
        carrying that real issue name."""
        diagnostics = diagnostics if diagnostics is not None else ShortInterestFetchDiagnostics()
        out: dict[str, ShortInterestObservation] = {}
        for row in csv.DictReader(io.StringIO(raw), delimiter="|", quoting=csv.QUOTE_NONE):
            symbol = (row.get("symbolCode") or "").strip()
            if not symbol or (symbols is not None and symbol not in symbols):
                continue
            stamp = (row.get("settlementDate") or "").strip()
            if not stamp:
                diagnostics.refuse("missing_settlement_date")
                continue
            try:
                settlement = date.fromisoformat(stamp)
                short_shares = float(row.get("currentShortPositionQuantity") or "nan")
                volume = float(row.get("averageDailyVolumeQuantity") or "nan")
            except ValueError:
                diagnostics.refuse("unparseable_number")
                continue
            if not volume > 0.0:
                diagnostics.refuse("non_positive_volume")
                continue
            if not short_shares > 0.0:
                diagnostics.refuse("non_positive_short_interest")
                continue
            diagnostics.n_rows_parsed += 1
            out[symbol] = ShortInterestObservation(
                symbol=symbol,
                settlement_date=settlement,
                available=publication_date(settlement),
                short_shares=short_shares,
                average_daily_volume=volume,
                market_class=(row.get("marketClassCode") or "").strip(),
                split_flagged=(row.get("stockSplitFlag") or "").strip().upper() == "S",
            )
        return out

    # --- the production entry point ------------------------------------

    def fetch_observations_for_tickers(
        self, tickers: Iterable[str], start: date, end: date
    ) -> tuple[dict[str, list[ShortInterestObservation]], ShortInterestFetchDiagnostics]:
        """(ticker -> its chronological observations, diagnostics), keyed by
        THIS PROJECT's ticker symbology rather than FINRA's.

        One pass per settlement cycle over the whole requested ticker set —
        the cost of this data is per-CYCLE, not per-ticker, which is why the
        consuming family can afford the FULL point-in-time universe where
        the EDGAR-based families had to draw a 200-name sample.

        Symbol resolution per cycle is direct-match-first, separator-stripped
        fallback second (module docstring section 4), with every fallback hit
        counted in diagnostics so a collision cannot pass unnoticed."""
        tickers = list(tickers)
        direct = {ticker: ticker for ticker in tickers}
        stripped = {ticker: finra_symbol(ticker) for ticker in tickers}
        wanted = set(direct.values()) | set(stripped.values())

        diagnostics = ShortInterestFetchDiagnostics()
        settlements, unresolved = self.resolve_settlement_dates(start, end)
        diagnostics.n_cycles_requested = len(settlements) + len(unresolved)
        diagnostics.n_cycles_resolved = len(settlements)
        diagnostics.unresolved_anchors = unresolved

        out: dict[str, list[ShortInterestObservation]] = {ticker: [] for ticker in tickers}
        for settlement in settlements:
            by_symbol = self.parse_cycle(self.fetch_raw(settlement), wanted, diagnostics)
            for ticker in tickers:
                observation = by_symbol.get(direct[ticker])
                if observation is None:
                    observation = by_symbol.get(stripped[ticker])
                    if observation is not None and stripped[ticker] != direct[ticker]:
                        diagnostics.separator_stripped_matches[ticker] = (
                            diagnostics.separator_stripped_matches.get(ticker, 0) + 1
                        )
                if observation is not None:
                    out[ticker].append(observation)
        return out, diagnostics


__all__ = [
    "EARLIEST_SETTLEMENT_DATE",
    "FINRA_SHORT_INTEREST_URL",
    "FinraShortInterestFetchError",
    "FinraShortInterestProvider",
    "PUBLICATION_LAG_CALENDAR_DAYS",
    "ShortInterestFetchDiagnostics",
    "ShortInterestObservation",
    "finra_symbol",
    "publication_date",
    "settlement_anchors",
]
