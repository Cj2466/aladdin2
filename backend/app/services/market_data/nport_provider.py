"""SEC FORM N-PORT BULK DATA — fund flows and per-security fund holdings.

WHAT THIS IS
============
Form N-PORT is the monthly portfolio report every registered management
investment company (and every ETF organised as a unit investment trust) files
with the SEC, other than money market funds and small business investment
companies. Only the THIRD month of each fund's fiscal quarter is made public,
and only 60 days after that month ends:

    SEC Release 33-10231 / IC-32314, "Investment Company Reporting
    Modernization", adopted 2016-10-13, 81 FR 81870, verbatim:
      "Only information reported for the third month of each fund's fiscal
       quarter on Form N-PORT will be made publicly available, and such
       information will not be made public until 60 days after the end of the
       third month of the fund's fiscal quarter."

That regime has been continuously in force since 2016 and is still in force:
the 2024 amendments that would have made disclosure monthly were delayed
(IC-35538, 2025-04-16) before ever taking effect and the SEC then PROPOSED
(2026-02-18, IC-35962, File No. S7-2026-05) to abandon them and keep quarterly
publication. Two consequences this module's callers must design around:

  * HOLDINGS ARE QUARTERLY, not monthly, and there is no near-term prospect of
    that changing.
  * EVERY value is public only ~60 days after its own report date. Any
    point-in-time construction must gate on FILING_DATE, which this module
    carries on every row for exactly that reason.

Both facts, the rule text above, and the bulk-dataset mechanics below were
established and verified live against sec.gov on 2026-09-05 by
data/research_runs/run_nport_flow_feasibility.py; its report
(data/research_runs/nport_flow_feasibility_2026-09-05.txt) is the primary
record and is not re-derived here.

THE BULK DATASET, AND WHY NOTHING HERE SCRAPES INDIVIDUAL FILINGS
================================================================
SEC DERA publishes one tab-delimited, UTF-8 ZIP per calendar quarter at
https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets
("The N-PORT data sets consists of XML data submitted from October 2019
through current period"). One ZIP holds up to 32 flat tables; this module
reads four of them:

    SUBMISSION.tsv              accession -> FILING_DATE, SUB_TYPE, REPORT_DATE
    FUND_REPORTED_INFO.tsv      accession -> series id/name, NET_ASSETS, and the
                                nine Item B.6 monthly flow fields
    MONTHLY_TOTAL_RETURN.tsv    accession/share class -> three monthly returns
    FUND_REPORTED_HOLDING.tsv   accession -> one row per portfolio position,
                                with ISSUER_CUSIP, BALANCE, UNIT, ASSET_CAT

THE SIZE PROBLEM, AND THE RANGE-REQUEST ANSWER
==============================================
A quarterly ZIP is 240-724MB and FUND_REPORTED_HOLDING.tsv alone is
157-425MB compressed (503MB-1.59GB uncompressed) — measured across all 27
published quarters on 2026-09-05, not estimated. Downloading 27 of them whole
would move ~11GB to read a few hundred thousand rows.

So this module does what run_nport_flow_feasibility.py's PROOF_3 proved
works: two small HTTP range requests read the ZIP's end-of-central-directory
and central directory, a third reads the wanted member's local header, and the
member's compressed bytes are then pulled in 8MB ranges and inflated
incrementally with a raw-DEFLATE decompressor. The holdings stream is filtered
line-by-line against a caller-supplied CUSIP set, so the full table is never
held in memory or written to disk. Only the filtered result is cached.

ZIP64 is handled explicitly rather than assumed absent: several quarters
exceed the 4GB/65535-entry fields' range in principle and the parser reads the
ZIP64 extra field wherever a 0xFFFFFFFF sentinel appears.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
=========================================
It computes no flow definition and no signal. Which of Lou (2012) Eq.(1),
Item B.6 NET (a+b-c) or Item B.6 EXTERNAL (a-c) is the right flow measure was
resolved separately, on 49,705 real fund-quarters, in
data/research_runs/nport_flow_definition_resolution_2026-09-05.txt (answer:
B.6 EXTERNAL, a - c). This module hands back the raw a, b and c fields and
lets the consumer apply that decision, so a future change of definition needs
no re-fetch.
"""

from __future__ import annotations

import csv
import gzip
import struct
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "nport_bulk"

BULK_URL_TEMPLATE = "https://www.sec.gov/files/dera/data/form-n-port-data-sets/{quarter}_nport.zip"

# The first published quarter. SEC's own bulk-dataset page: "The N-PORT data
# sets consists of XML data submitted from October 2019 through current
# period" — and the earliest ZIP that resolves is 2019q4 (verified live
# 2026-09-05: 2019q1..2019q3 all return HTTP 404).
FIRST_BULK_QUARTER = "2019q4"

# SEC's published fair-access ceiling is 10 requests/second. Same interval the
# sibling SEC providers in this package use.
SEC_MIN_REQUEST_INTERVAL_SECONDS = 0.6

# Bytes of compressed member pulled per range request while streaming. 8MB
# keeps the request count for a 425MB member at ~53 rather than thousands,
# while never holding more than one chunk's inflation in memory.
STREAM_CHUNK_BYTES = 8 << 20

# Form N-PORT Item C.4 "Balance. Indicate whether amount is expressed in number
# of shares, principal amount, or other units" — 'NS' is the number-of-shares
# unit, which is the only one a share-count-weighted construction can use. A
# bond position ('PA', principal amount) is not a share count.
UNIT_NUMBER_OF_SHARES = "NS"

# Item C.7 asset category 'EC' = equity-common. Verified against a real filing
# in run_nport_flow_feasibility.py PROOF_2 (Hilton Worldwide Holdings Inc,
# balance 872023, UNIT 'NS', assetCat 'EC').
ASSET_CAT_EQUITY_COMMON = "EC"

# N-PORT's own placeholder when a filer reports no CUSIP. Real, and common:
# see the derivative/loan rows in any quarter's holdings table.
CUSIP_NOT_AVAILABLE = "999999999"

TABLE_SUBMISSION = "SUBMISSION.tsv"
TABLE_FUND_REPORTED_INFO = "FUND_REPORTED_INFO.tsv"
TABLE_MONTHLY_TOTAL_RETURN = "MONTHLY_TOTAL_RETURN.tsv"
TABLE_FUND_REPORTED_HOLDING = "FUND_REPORTED_HOLDING.tsv"

SUBMISSION_COLUMNS = (
    "ACCESSION_NUMBER",
    "FILING_DATE",
    "SUB_TYPE",
    "REPORT_DATE",
    "IS_LAST_FILING",
)
FUND_INFO_COLUMNS = (
    "ACCESSION_NUMBER",
    "SERIES_ID",
    "SERIES_NAME",
    "TOTAL_ASSETS",
    "NET_ASSETS",
    "SALES_FLOW_MON1",
    "REINVESTMENT_FLOW_MON1",
    "REDEMPTION_FLOW_MON1",
    "SALES_FLOW_MON2",
    "REINVESTMENT_FLOW_MON2",
    "REDEMPTION_FLOW_MON2",
    "SALES_FLOW_MON3",
    "REINVESTMENT_FLOW_MON3",
    "REDEMPTION_FLOW_MON3",
)
MONTHLY_RETURN_COLUMNS = (
    "ACCESSION_NUMBER",
    "CLASS_ID",
    "MONTHLY_TOTAL_RETURN1",
    "MONTHLY_TOTAL_RETURN2",
    "MONTHLY_TOTAL_RETURN3",
)
HOLDING_COLUMNS = (
    "ACCESSION_NUMBER",
    "ISSUER_CUSIP",
    "BALANCE",
    "UNIT",
    "CURRENCY_VALUE",
    "PERCENTAGE",
    "ASSET_CAT",
    "CURRENCY_CODE",
)

_MONTH_ABBREVIATIONS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def build_sec_user_agent(contact: str = "autoa0792@gmail.com") -> str:
    """SEC fair-access requires a real, contactable User-Agent on every
    automated request. Same convention as the sibling SEC providers."""
    return f"Aladdin2 Research {contact}"


def published_quarters(through: date) -> list[str]:
    """Every DERA bulk quarter name from FIRST_BULK_QUARTER through the
    calendar quarter containing `through`, in order.

    Names the CALENDAR QUARTER THE FILINGS WERE RECEIVED IN, not the period
    they report on — a fund's 2026-06-30 report is filed ~60 days later and so
    lands in the 2026q3 ZIP, not 2026q2. Verified rather than assumed: the
    2026q2 ZIP's own REPORT_DATE column is dominated by report dates two to
    three months before the ZIP's own quarter."""
    out: list[str] = []
    year, quarter = int(FIRST_BULK_QUARTER[:4]), int(FIRST_BULK_QUARTER[-1])
    last_year, last_quarter = through.year, (through.month - 1) // 3 + 1
    while (year, quarter) <= (last_year, last_quarter):
        out.append(f"{year}q{quarter}")
        quarter += 1
        if quarter > 4:
            year, quarter = year + 1, 1
    return out


def parse_sec_date(raw: str) -> date | None:
    """SEC DERA writes dates as DD-MON-YYYY ('24-APR-2026'). Returns None for
    an empty or unparseable cell rather than raising: the tables are published
    'as-filed' and SEC's own README warns they "may contain redundancies,
    inconsistencies, and discrepancies", so a single bad cell must not abort a
    27-quarter sweep."""
    text = raw.strip().upper()
    if not text:
        return None
    parts = text.split("-")
    if len(parts) != 3:
        return None
    day, month, year = parts
    month_number = _MONTH_ABBREVIATIONS.get(month[:3])
    if month_number is None:
        return None
    try:
        return date(int(year), month_number, int(day))
    except ValueError:
        return None


def parse_float(raw: str) -> float | None:
    """A DERA numeric cell, or None when it is blank/unparseable. N-PORT
    writes bare leading decimals ('.0040692036') and negative values, both of
    which float() handles; it also writes empty strings for absent optional
    items, which it does not."""
    text = raw.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value


# --- remote ZIP member access ------------------------------------------------


@dataclass(frozen=True)
class ZipMember:
    """One entry of a remote ZIP's central directory."""

    name: str
    compressed_size: int
    uncompressed_size: int
    local_header_offset: int


class NportBulkError(RuntimeError):
    """A bulk ZIP could not be read as a ZIP.

    Deliberately loud. A partially-parsed archive would silently produce a
    holdings panel missing whole funds, which is indistinguishable downstream
    from a quarter in which those funds genuinely held nothing.
    """


class NportProvider:
    """Rate-limited range-request reader for the DERA N-PORT bulk ZIPs, with an
    on-disk cache of the EXTRACTED, FILTERED tables.

    What gets cached is the filtered extraction, not the raw ZIP — the opposite
    of Form13FProvider's choice, and for a stated reason: a Form 13F quarter
    ZIP is ~50MB and caching it raw lets the parser be rewritten without
    re-downloading, while an N-PORT quarter ZIP is 240-724MB and 27 of them
    will not fit anywhere sensible. The cost is real and is stated rather than
    hidden: changing the wanted-CUSIP set or the retained columns means
    re-downloading, because the discarded rows are gone.
    """

    def __init__(
        self,
        cache_dir: Path | str | None = DEFAULT_CACHE_DIR,
        user_agent: str | None = None,
        min_request_interval: float = SEC_MIN_REQUEST_INTERVAL_SECONDS,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent or build_sec_user_agent()
        self.min_request_interval = min_request_interval
        self._last_request = 0.0
        self._directories: dict[str, dict[str, ZipMember]] = {}

    # -- HTTP ---------------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self._last_request = time.monotonic()

    def _open(self, url: str, start: int | None, end: int | None, head: bool):
        request = urllib.request.Request(url, method="HEAD" if head else "GET")
        request.add_header("User-Agent", self.user_agent)
        if start is not None:
            request.add_header("Range", f"bytes={start}-{'' if end is None else end}")
        return urllib.request.urlopen(request, timeout=300)

    def _range(self, url: str, start: int, end: int, *, attempts: int = 4) -> bytes:
        last: Exception | None = None
        for attempt in range(attempts):
            self._throttle()
            try:
                with self._open(url, start, end, head=False) as response:
                    return response.read()
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
                time.sleep(2.0 * (attempt + 1))
        raise NportBulkError(f"range {start}-{end} of {url} failed after {attempts} attempts: {last}")

    def content_length(self, url: str) -> int:
        self._throttle()
        with self._open(url, None, None, head=True) as response:
            return int(response.headers["content-length"])

    # -- ZIP ----------------------------------------------------------------

    def central_directory(self, quarter: str) -> dict[str, ZipMember]:
        """Member table for one quarter's ZIP, from two range requests."""
        if quarter in self._directories:
            return self._directories[quarter]
        url = BULK_URL_TEMPLATE.format(quarter=quarter)
        size = self.content_length(url)
        tail = self._range(url, max(0, size - (1 << 16)), size - 1)
        eocd_at = tail.rfind(b"PK\x05\x06")
        if eocd_at < 0:
            raise NportBulkError(f"{quarter}: no end-of-central-directory record")
        n_entries, cd_size, cd_offset = struct.unpack("<HII", tail[eocd_at + 10 : eocd_at + 20])
        if cd_offset == 0xFFFFFFFF or n_entries == 0xFFFF:
            locator = tail.rfind(b"PK\x06\x07")
            if locator < 0:
                raise NportBulkError(f"{quarter}: ZIP64 sentinel with no ZIP64 locator")
            zip64_at = struct.unpack("<Q", tail[locator + 8 : locator + 16])[0]
            zip64 = self._range(url, zip64_at, zip64_at + 55)
            n_entries, cd_size, cd_offset = struct.unpack("<QQQ", zip64[32:56])
        directory = self._parse_central_directory(
            self._range(url, cd_offset, cd_offset + cd_size - 1), n_entries, quarter
        )
        self._directories[quarter] = directory
        return directory

    @staticmethod
    def _parse_central_directory(raw: bytes, n_entries: int, quarter: str) -> dict[str, ZipMember]:
        members: dict[str, ZipMember] = {}
        position = 0
        for _ in range(n_entries):
            if raw[position : position + 4] != b"PK\x01\x02":
                break
            (
                method, _time, _date, _crc, csize, usize,
                name_len, extra_len, comment_len, _disk, _internal, _external, header_offset,
            ) = struct.unpack("<HHHIIIHHHHHII", raw[position + 10 : position + 46])
            name = raw[position + 46 : position + 46 + name_len].decode("utf-8", "replace")
            extra = raw[position + 46 + name_len : position + 46 + name_len + extra_len]
            if 0xFFFFFFFF in (csize, usize, header_offset):
                csize, usize, header_offset = _read_zip64_extra(extra, csize, usize, header_offset)
            if method != 8 and csize:
                raise NportBulkError(
                    f"{quarter}/{name}: compression method {method}; this reader inflates raw "
                    "DEFLATE only (every DERA N-PORT member observed is method 8)."
                )
            members[name] = ZipMember(name, csize, usize, header_offset)
            position += 46 + name_len + extra_len + comment_len
        return members

    def _member_data_offset(self, url: str, member: ZipMember) -> int:
        header = self._range(url, member.local_header_offset, member.local_header_offset + 29)
        if header[:4] != b"PK\x03\x04":
            raise NportBulkError(f"{member.name}: bad local file header signature")
        name_len, extra_len = struct.unpack("<HH", header[26:30])
        return member.local_header_offset + 30 + name_len + extra_len

    def stream_member_lines(self, quarter: str, table: str) -> Iterator[str]:
        """Decoded text lines of one member, inflated incrementally."""
        url = BULK_URL_TEMPLATE.format(quarter=quarter)
        member = self.central_directory(quarter)[table]
        offset = self._member_data_offset(url, member)
        remaining = member.compressed_size
        decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
        carry = ""
        while remaining > 0:
            chunk = self._range(url, offset, offset + min(STREAM_CHUNK_BYTES, remaining) - 1)
            if not chunk:
                raise NportBulkError(f"{quarter}/{table}: empty range response")
            offset += len(chunk)
            remaining -= len(chunk)
            text = carry + decompressor.decompress(chunk).decode("utf-8", "replace")
            lines = text.split("\n")
            carry = lines.pop()
            yield from lines
        for line in (carry + decompressor.flush().decode("utf-8", "replace")).split("\n"):
            if line:
                yield line

    # -- extraction ---------------------------------------------------------

    def _cache_path(self, quarter: str, table: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{quarter}_{table.replace('.tsv', '')}.csv.gz"

    def extract_table(
        self,
        quarter: str,
        table: str,
        columns: Sequence[str],
        *,
        row_filter=None,
    ) -> list[dict[str, str]]:
        """`columns` of `table`, cached per quarter as gzipped CSV.

        `row_filter` is called with the raw split row and the column index map
        and must return True to keep the row; it exists so the 157-425MB
        holdings member can be reduced to the caller's own CUSIP set WHILE
        streaming, never after."""
        path = self._cache_path(quarter, table)
        if path is not None and path.exists() and path.stat().st_size > 0:
            with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
                return list(csv.DictReader(handle))

        rows: list[dict[str, str]] = []
        stream = self.stream_member_lines(quarter, table)
        header = next(stream).rstrip("\r").split("\t")
        index = {name: position for position, name in enumerate(header)}
        missing = [name for name in columns if name not in index]
        if missing:
            raise NportBulkError(
                f"{quarter}/{table}: columns {missing} absent. SEC changed the layout; refusing "
                f"to guess. Published header: {header}"
            )
        for line in stream:
            if not line.strip():
                continue
            parts = line.rstrip("\r").split("\t")
            if len(parts) != len(header):
                # As-filed data: a row whose field count disagrees with the
                # header cannot be positionally decoded. Skipped, never
                # guessed at.
                continue
            if row_filter is not None and not row_filter(parts, index):
                continue
            rows.append({name: parts[index[name]] for name in columns})

        if path is not None:
            temporary = path.with_suffix(".part")
            with gzip.open(temporary, "wt", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(columns))
                writer.writeheader()
                writer.writerows(rows)
            temporary.rename(path)
        return rows

    def submissions(self, quarter: str) -> list[dict[str, str]]:
        return self.extract_table(quarter, TABLE_SUBMISSION, SUBMISSION_COLUMNS)

    def fund_reported_info(self, quarter: str) -> list[dict[str, str]]:
        return self.extract_table(quarter, TABLE_FUND_REPORTED_INFO, FUND_INFO_COLUMNS)

    def monthly_total_returns(self, quarter: str) -> list[dict[str, str]]:
        return self.extract_table(quarter, TABLE_MONTHLY_TOTAL_RETURN, MONTHLY_RETURN_COLUMNS)

    def holdings(self, quarter: str, cusips: set[str]) -> list[dict[str, str]]:
        """Holdings rows whose ISSUER_CUSIP is in `cusips`.

        The filter runs inside the stream, so the 157-425MB member is read once
        and never materialised."""
        cusip_column = "ISSUER_CUSIP"

        def keep(parts: list[str], index: dict[str, int]) -> bool:
            return parts[index[cusip_column]] in cusips

        return self.extract_table(
            quarter, TABLE_FUND_REPORTED_HOLDING, HOLDING_COLUMNS, row_filter=keep
        )

    def cached_quarters(self) -> list[str]:
        """Quarters whose four tables are all present in the cache."""
        if self.cache_dir is None:
            return []
        tables = (
            TABLE_SUBMISSION,
            TABLE_FUND_REPORTED_INFO,
            TABLE_MONTHLY_TOTAL_RETURN,
            TABLE_FUND_REPORTED_HOLDING,
        )
        found: list[str] = []
        for path in sorted(self.cache_dir.glob(f"*_{TABLE_SUBMISSION.replace('.tsv', '')}.csv.gz")):
            quarter = path.name.split("_")[0]
            if all(
                (p := self._cache_path(quarter, table)) is not None
                and p.exists()
                and p.stat().st_size > 0
                for table in tables
            ):
                found.append(quarter)
        return sorted(found)


def _read_zip64_extra(
    extra: bytes, csize: int, usize: int, header_offset: int
) -> tuple[int, int, int]:
    """Replace 0xFFFFFFFF sentinels from the ZIP64 extended information extra
    field (header id 0x0001), in the field order the format mandates:
    uncompressed size, compressed size, local header offset — each present
    only if its 32-bit counterpart was the sentinel."""
    position = 0
    while position + 4 <= len(extra):
        header_id, block_size = struct.unpack("<HH", extra[position : position + 4])
        if header_id == 0x0001:
            body, cursor = extra[position + 4 : position + 4 + block_size], 0
            if usize == 0xFFFFFFFF:
                usize = struct.unpack("<Q", body[cursor : cursor + 8])[0]
                cursor += 8
            if csize == 0xFFFFFFFF:
                csize = struct.unpack("<Q", body[cursor : cursor + 8])[0]
                cursor += 8
            if header_offset == 0xFFFFFFFF:
                header_offset = struct.unpack("<Q", body[cursor : cursor + 8])[0]
            break
        position += 4 + block_size
    return csize, usize, header_offset


# --- typed views over the extracted rows -------------------------------------


@dataclass(frozen=True)
class FundQuarterFiling:
    """One public N-PORT filing for one fund series: what it reported, and the
    date the public could first see it.

    `filing_date` is load-bearing, not metadata. Every value on this record was
    secret until that date (the 60-day rule quoted in the module docstring), so
    any point-in-time construction must gate on it rather than on
    `report_date`.
    """

    accession: str
    series_id: str
    series_name: str
    report_date: date
    filing_date: date
    submission_type: str
    is_last_filing: bool
    net_assets: float
    # Item B.6.a / B.6.b / B.6.c, summed over the quarter's three months.
    sales: float
    reinvestment: float
    redemption: float

    @property
    def external_flow_dollars(self) -> float:
        """Item B.6.a - Item B.6.c: EXTERNAL net flow, excluding reinvested
        distributions.

        THE flow definition for this project, resolved on 49,705 real
        fund-quarters in data/research_runs/
        nport_flow_definition_resolution_2026-09-05.txt. Lou (2012) Section 2.2
        states verbatim that he assumes "investors reinvest their dividends and
        capital appreciation distributions in the same fund"; under that
        assumption his Eq.(1) is algebraically identical to B.6.a - B.6.c, so
        reading the directly-reported figure measures his own estimand rather
        than proxying it."""
        return self.sales - self.redemption

    @property
    def net_flow_dollars(self) -> float:
        """Item B.6.a + B.6.b - B.6.c. Reported for completeness; NOT the
        project's definition — it adds reinvested distributions back in, which
        Lou's construction excludes by assumption."""
        return self.sales + self.reinvestment - self.redemption


@dataclass(frozen=True)
class HoldingRow:
    """One equity position: fund series, stock, split-unadjusted share count."""

    accession: str
    cusip: str
    shares: float
    value_usd: float
    percent_of_net_assets: float


@dataclass
class NportLoadDiagnostics:
    """Every row this loader declined, counted. Refusals are never silent."""

    n_submission_rows: int = 0
    n_fund_rows: int = 0
    n_holding_rows: int = 0
    n_filings_built: int = 0
    n_refused: dict[str, int] = field(default_factory=dict)

    def refuse(self, reason: str) -> None:
        self.n_refused[reason] = self.n_refused.get(reason, 0) + 1


def _sum_three_months(row: dict[str, str], prefix: str, diagnostics: NportLoadDiagnostics) -> float | None:
    total = 0.0
    for month in (1, 2, 3):
        value = parse_float(row.get(f"{prefix}{month}", ""))
        if value is None:
            diagnostics.refuse(f"missing_{prefix.lower()}{month}")
            return None
        total += value
    return total


def build_fund_quarter_filings(
    submission_rows: Sequence[dict[str, str]],
    fund_rows: Sequence[dict[str, str]],
    diagnostics: NportLoadDiagnostics | None = None,
) -> tuple[list[FundQuarterFiling], NportLoadDiagnostics]:
    """Join SUBMISSION.tsv onto FUND_REPORTED_INFO.tsv by accession.

    Amendments are NOT deduplicated here. That is deliberate: an NPORT-P/A
    supersedes its original only from ITS OWN filing date onward, and a
    point-in-time consumer must be able to see the original for dates before
    that. Deduplication is the consumer's decision, made against a formation
    date it knows and this function does not.
    """
    diagnostics = diagnostics or NportLoadDiagnostics()
    diagnostics.n_submission_rows += len(submission_rows)
    diagnostics.n_fund_rows += len(fund_rows)

    by_accession: dict[str, dict[str, str]] = {}
    for row in submission_rows:
        by_accession[row["ACCESSION_NUMBER"]] = row

    out: list[FundQuarterFiling] = []
    for row in fund_rows:
        accession = row["ACCESSION_NUMBER"]
        submission = by_accession.get(accession)
        if submission is None:
            diagnostics.refuse("no_submission_row")
            continue
        report_date = parse_sec_date(submission.get("REPORT_DATE", ""))
        filing_date = parse_sec_date(submission.get("FILING_DATE", ""))
        if report_date is None or filing_date is None:
            diagnostics.refuse("unparseable_dates")
            continue
        if filing_date < report_date:
            # As-filed data quality: a filing cannot predate the period it
            # reports on. Refused rather than trusted, because such a row would
            # make a value visible before it existed.
            diagnostics.refuse("filing_date_before_report_date")
            continue
        series_id = row.get("SERIES_ID", "").strip()
        if not series_id:
            diagnostics.refuse("missing_series_id")
            continue
        net_assets = parse_float(row.get("NET_ASSETS", ""))
        if net_assets is None or not net_assets > 0.0:
            diagnostics.refuse("non_positive_net_assets")
            continue
        sales = _sum_three_months(row, "SALES_FLOW_MON", diagnostics)
        reinvestment = _sum_three_months(row, "REINVESTMENT_FLOW_MON", diagnostics)
        redemption = _sum_three_months(row, "REDEMPTION_FLOW_MON", diagnostics)
        if sales is None or reinvestment is None or redemption is None:
            continue
        out.append(
            FundQuarterFiling(
                accession=accession,
                series_id=series_id,
                series_name=row.get("SERIES_NAME", "").strip(),
                report_date=report_date,
                filing_date=filing_date,
                submission_type=submission.get("SUB_TYPE", "").strip(),
                is_last_filing=submission.get("IS_LAST_FILING", "").strip().upper() == "Y",
                net_assets=net_assets,
                sales=sales,
                reinvestment=reinvestment,
                redemption=redemption,
            )
        )
    diagnostics.n_filings_built += len(out)
    out.sort(key=lambda f: (f.series_id, f.report_date, f.filing_date))
    return out, diagnostics


def build_holding_rows(
    holding_rows: Sequence[dict[str, str]],
    diagnostics: NportLoadDiagnostics | None = None,
) -> tuple[list[HoldingRow], NportLoadDiagnostics]:
    """Keep only long common-equity positions measured in shares.

    Four refusals, each counted:
      * `not_number_of_shares` — Item C.4 unit is not 'NS'. A principal amount
        or a contract count is not a share count and cannot be summed with one.
      * `not_equity_common` — Item C.7 asset category is not 'EC'. A fund's
        preferred stock or convertible position in the same issuer is a
        different security.
      * `cusip_not_available` — the filer wrote N-PORT's 999999999 placeholder.
      * `non_positive_shares` — a zero or SHORT position. Lou's Eq.(3) weight
        `shares_i,j,t-1` is a long share count used as a liquidity-provision
        scaler (his footnote 8); a negative weight would invert the sign of
        that fund's flow contribution, which is not what the measure means.
    """
    diagnostics = diagnostics or NportLoadDiagnostics()
    diagnostics.n_holding_rows += len(holding_rows)
    out: list[HoldingRow] = []
    for row in holding_rows:
        if row.get("UNIT", "").strip() != UNIT_NUMBER_OF_SHARES:
            diagnostics.refuse("not_number_of_shares")
            continue
        if row.get("ASSET_CAT", "").strip() != ASSET_CAT_EQUITY_COMMON:
            diagnostics.refuse("not_equity_common")
            continue
        cusip = row.get("ISSUER_CUSIP", "").strip()
        if not cusip or cusip == CUSIP_NOT_AVAILABLE:
            diagnostics.refuse("cusip_not_available")
            continue
        shares = parse_float(row.get("BALANCE", ""))
        if shares is None or not shares > 0.0:
            diagnostics.refuse("non_positive_shares")
            continue
        value = parse_float(row.get("CURRENCY_VALUE", "")) or 0.0
        percent = parse_float(row.get("PERCENTAGE", "")) or 0.0
        out.append(
            HoldingRow(
                accession=row["ACCESSION_NUMBER"],
                cusip=cusip,
                shares=shares,
                value_usd=value,
                percent_of_net_assets=percent,
            )
        )
    return out, diagnostics
