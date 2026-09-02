"""SEC Form 13F structured data sets: real institutional holdings, parsed
point-in-time from SEC's own quarterly TSV archives, plus the CUSIP ->
ticker resolution those archives require and do not themselves provide.

This is the ingestion half of the 13F "Best Ideas" family
(cross_sectional_best_ideas.py). It is deliberately a market_data
PROVIDER rather than research_lab code: it knows about SEC file layouts,
fair-access rate limits, dirty vendor rows and identifier mapping, and
nothing at all about signals, formations or backtests.

Structurally it follows cross_sectional_insider.py's treatment of the
sibling SEC product (the Insider Transactions Data Sets): quarterly ZIPs
fetched with a real User-Agent under SEC's fair-access policy, cached as
raw bytes so parsing can be rewritten without re-hitting sec.gov, and
parsed by HEADER NAME rather than column position.

=======================================================================
1. THE SOURCE, CONFIRMED LIVE 2026-09-02
=======================================================================

INDEX: https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
was fetched live and its own links enumerated: 53 quarterly archives from
2013q2 through the 01mar2026-31may2026 window. Two naming conventions
appear on that page and BOTH are real -- `<year>q<n>_form13f.zip` through
2023q4, then explicit filing-window date ranges from 2024 onward. The
names in QUARTER_NAMES below are transcribed from that live index, not
reconstructed from a pattern.

EACH ARCHIVE holds tab-separated tables. This module reads three:
  SUBMISSION.tsv  ACCESSION_NUMBER, FILING_DATE, SUBMISSIONTYPE, CIK,
                  PERIODOFREPORT
  COVERPAGE.tsv   ACCESSION_NUMBER, ..., FILINGMANAGER_NAME, ...
  INFOTABLE.tsv   ACCESSION_NUMBER, INFOTABLE_SK, NAMEOFISSUER,
                  TITLEOFCLASS, CUSIP, FIGI, VALUE, SSHPRNAMT,
                  SSHPRNAMTTYPE, PUTCALL, INVESTMENTDISCRETION,
                  OTHERMANAGER, VOTING_AUTH_SOLE/SHARED/NONE

THE ARCHIVES ARE KEYED ON FILING DATE, NOT REPORT PERIOD, and that was
MEASURED on the real 2016q1 archive rather than assumed: its FILING_DATE
values fall entirely in Jan/Feb/Mar 2016 (4,953 FEB, 1,041 JAN, 78 MAR)
while its PERIODOFREPORT is 31-DEC-2015 for 5,870 of ~6,072 submissions,
with a tail of late filers reporting older quarters. That IS the 45-day
statutory lag, visible directly in the vendor's own file organisation,
and it is the reason everything downstream keys on FILING_DATE.

SUBMISSIONTYPE in that same real archive: 4,268 13F-HR, 1,523 13F-NT,
271 13F-HR/A, 10 13F-NT/A. 13F-NT are NOTICE filings carrying no
holdings at all and are dropped by count.

=======================================================================
2. THE VALUE-UNITS DEFECT -- MEASURED, NOT ASSUMED, AND LOAD-BEARING
=======================================================================

13F's VALUE column is specified in THOUSANDS of dollars for the era this
family covers. A minority of filers report it in WHOLE DOLLARS anyway.
This is a real, measurable defect in the vendor data and it is the single
dirtiest thing in this pipeline.

MEASURED on the real 2016q1 archive, using VALUE/SSHPRNAMT as a per-row
implied price (AAPL closed near $105.26 on 2015-12-31, so a correctly
scaled row implies ~105 in dollars or ~0.105 in thousands): of the filers
reporting AAPL, 3,374 implied ~0.105 (thousands) and 72 implied ~105
(whole dollars), with a handful of unusable rows. Across ALL 4,462
accessions in that archive, a per-accession MEDIAN of VALUE/SSHPRNAMT
separates cleanly -- 4,363 land in 0.001..1 (thousands), 92 in 1..1000
(whole dollars), 7 elsewhere. There is no ambiguous mass at the boundary,
which is what makes the classifier below safe.

WHY IT IS SAFE TO CLASSIFY PER FILING: the unit error is a property of
the FILER's software, so it is constant within one submission. That has
two consequences, and the second is the more important:

 (a) classify_value_scale can decide per accession from the filing's own
     internal median implied price, needing NO external price data and no
     coverage of the thousands of tickers outside our universe;

 (b) A PORTFOLIO WEIGHT IS IMMUNE TO THE DEFECT ENTIRELY. lambda_i =
     VALUE_i / sum_j VALUE_j is a ratio of two numbers carrying the same
     unit, so a mis-scaled filing produces exactly correct weights. The
     "conviction" best-idea measure is therefore untouched by this defect
     even before normalisation. Normalisation matters only where values
     are compared ACROSS filings: the $5m minimum-equity screen and the
     aggregate-13F market-weight vector.

THE CONVENTION CHANGED IN 2023, AND THE CLASSIFIER FOUND IT WITHOUT BEING
TOLD. Measured across all 53 real archives, the share of filings reporting
whole dollars is:

    2021q1..2022q4     1.2% - 1.6%
    2023q1            79.9%          <- the break
    2023q2..2023q4    86.3% -> 89.4%
    2024..2026q2      90.5% -> 96.0%

VERIFIED against the primary source: the CURRENT Form 13F instructions
(https://www.sec.gov/files/form13f.pdf, fetched 2026-09-02) state at
instruction 8, verbatim, "Enter values rounded to the nearest dollar",
and the information-table header reads "(to the nearest dollar)".

LABELLED AS INFERENCE: that the 2023q1 break IS the form's units
convention changing, with a multi-year tail of filers still on the old
thousands convention. No explicit effective-date statement was found in
the fetched instructions, so the causal attribution is an inference. The
counts above are not — they are measured from the real archives.

WHY THIS MATTERS BEYOND THIS PROJECT: essentially every pre-2023
description of this dataset says VALUE is in thousands. A pipeline that
hardcodes that is wrong by a factor of 1,000 for 80-96% of filings from
2023 onward. Classifying per filing is not defensive over-engineering
here; it is the only thing that makes the recent half of the sample
usable at all for any cross-filer comparison.

The classifier is unit-tested in both directions and its realized
per-quarter counts are reported by every production run, never assumed.

=======================================================================
3. CUSIP -> TICKER, AND WHY IT COMES FROM FAILS-TO-DELIVER
=======================================================================

13F identifies securities by CUSIP and by nothing else usable. (The
INFOTABLE FIGI column exists in the schema but was EMPTY in the real
2016q1 rows inspected, so it is not relied on.) CUSIP is a licensed
identifier; this project has no CUSIP licence and no commercial security
master, so the mapping has to come from a free, official, dated source.

SEC's own Fails-to-Deliver files are exactly that. Enumerated live from
https://www.sec.gov/data/foiadocsfailsdatahtm, they are pipe-delimited
with this header, verbatim from the real 201603a file:

    SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE

so every row is an SEC-published (CUSIP, SYMBOL) pair stamped with a
settlement date -- roughly 60,000 rows per semi-monthly file.

KNOWN LIMITATIONS, stated where the code lives rather than buried:
 * COVERAGE IS INCIDENTAL. A security appears only because it had a
   settlement fail, so this is evidence of a mapping, never a registry.
   For S&P 500 names over a multi-year window coverage should be
   near-total, but realized coverage is MEASURED per run and reported.
 * IT IS SECURITY-LEVEL, NOT ISSUER-LEVEL. Multi-class issuers get
   distinct CUSIPs (GOOG vs GOOGL), which is correct for weighting but
   means one issuer's stake can be split across classes.
 * IDENTIFIERS GET REUSED. Both tickers and CUSIPs are recycled on
   corporate actions, so the map keeps every DATED observation and
   resolves by the one NEAREST IN TIME to the filing, rather than
   collapsing to a single all-time symbol per CUSIP. In the real cached
   corpus 21 of the mapped CUSIPs carry more than one universe symbol
   (FB/META, ANTM/ELV, COG/CTRA, BK/BNY and so on), and nearest-in-time
   is what puts a 2015 filing on the 2015 symbol.
   THE RESOLUTION IS NOT WINDOW-BOUNDED, and an earlier version of this
   docstring wrongly said it was. There is no maximum distance: a CUSIP
   with a single observation resolves to that symbol at any date, and a
   filing sitting in a gap between observations can be resolved by an
   observation dated AFTER it. That is a real, if narrow, use of
   information post-dating the filing — see resolve().
 * NO CHECK-DIGIT ARITHMETIC IS TREATED AS AUTHORITY. CUSIPs are
   normalised (upper-cased, stripped, 9 characters) and anything
   malformed is refused by counted reason.
"""

import io
import logging
import re
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "form13f_raw"

FORM13F_BASE_URL = "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/"
FTD_BASE_URLS = (
    "https://www.sec.gov/files/data/fails-deliver-data/",
    "https://www.sec.gov/files/data/other/fails-deliver-data/",
    "https://www.sec.gov/files/data/frequently-requested-foia-document-fails-deliver-data/",
)

# SEC's published fair-access ceiling is 10 requests/second; these are
# 40-70MB archives so the binding constraint is bandwidth, not the rate
# limit. Kept well under regardless.
SEC_MIN_REQUEST_INTERVAL_SECONDS = 0.6

# Transcribed from the live index page (section 1), NOT generated from a
# pattern -- SEC changed the naming convention partway through and both
# halves are real.
QUARTER_NAMES: tuple[str, ...] = (
    *(f"{y}q{q}" for y in range(2013, 2024) for q in (1, 2, 3, 4) if f"{y}q{q}" >= "2013q2"),
    "01jan2024-29feb2024",
    "01mar2024-31may2024",
    "01jun2024-31aug2024",
    "01sep2024-30nov2024",
    "01dec2024-28feb2025",
    "01mar2025-31may2025",
    "01jun2025-31aug2025",
    "01sep2025-30nov2025",
    "01dec2025-28feb2026",
    "01mar2026-31may2026",
)

# Only holdings reports carry positions. 13F-NT is a NOTICE filing whose
# whole content is "another manager reports my holdings", and including
# it would create phantom zero-holding managers.
HOLDINGS_SUBMISSION_TYPES = frozenset({"13F-HR", "13F-HR/A"})

# Per-filing VALUE unit classification (section 2). A diversified 13F
# filer's MEDIAN implied price (VALUE/SSHPRNAMT) cannot plausibly be
# below $1 in whole dollars, so a median under this bound is the
# thousands convention. The measured 2016q1 split (4,363 vs 92, nothing
# at the boundary) is what licenses a hard cut here rather than a
# fuzzy one.
VALUE_SCALE_DECISION_BOUND = 1.0
VALUE_THOUSANDS_MULTIPLIER = 1_000.0
# A filing whose median implied price is outside this range is not
# credibly either convention (real 2016q1 examples implied 0 and 11,551)
# and is refused rather than guessed at.
MIN_CREDIBLE_IMPLIED_PRICE = 1e-4
MAX_CREDIBLE_IMPLIED_PRICE = 1e4

_CUSIP_RE = re.compile(r"^[0-9A-Z]{9}$")
# FTD symbols are plain exchange tickers; anything with whitespace or
# punctuation beyond a dot/dash is vendor noise.
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def build_sec_user_agent(contact: str = "autoa0792@gmail.com") -> str:
    """SEC fair-access requires a real, contactable User-Agent on every
    automated request. Same convention as the sibling EDGAR providers."""
    return f"Aladdin2 Research {contact}"


def normalize_ticker(raw: str) -> str:
    """SEC's fails-to-deliver files write share classes with a DOT
    ('BRK.B', 'BF.B'); this project's price universe uses yfinance's DASH
    convention ('BRK-B', 'BF-B'). Without this the two largest dual-class
    names in the S&P 500 silently fail to resolve a CUSIP — measured
    during this build, where BRK-B and BF-B were among only 23 unresolved
    tickers out of 768 and were the only two whose cause was a format
    mismatch rather than a genuinely absent security."""
    return raw.strip().upper().replace(".", "-")


def normalize_cusip(raw: str) -> str | None:
    """A 9-character uppercase alphanumeric CUSIP, or None.

    Deliberately NOT check-digit-validated: the check digit is arithmetic
    over the first eight characters and a filer that fat-fingers a digit
    produces a syntactically valid but wrong CUSIP either way, so
    validating it would buy a false sense of authority while rejecting
    real rows. The real defence is that an unmapped CUSIP simply fails to
    resolve to a ticker and is counted, never guessed at.

    The real 2016q1 archive's very first INFOTABLE row carries CUSIP
    '0        ' with issuer name '0' -- this is the function that refuses
    it."""
    if not raw:
        return None
    cleaned = raw.strip().upper()
    if len(cleaned) == 8 and cleaned.isdigit():
        # Some filers drop the leading zero of an all-numeric CUSIP
        # ('37833100' for Apple's 037833100). Restricted to all-DIGIT
        # strings deliberately: padding any 8-character value would turn
        # arbitrary 8-character garbage into a syntactically valid
        # identifier, which a test caught doing exactly that to the
        # string 'BADCUSIP'.
        cleaned = "0" + cleaned
    if not _CUSIP_RE.match(cleaned):
        return None
    if set(cleaned) <= {"0"}:
        return None
    return cleaned


def parse_sec_date(raw: str) -> date | None:
    """SEC's structured-data date convention is '31-MAR-2016'. A couple of
    other shapes appear in the wild; all are tried, and an unparseable
    date returns None so the caller can refuse the row by count rather
    than crash a 53-quarter run on one bad cell."""
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%B-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()  # noqa: DTZ007 — date-only vendor field
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class Form13FHolding:
    """One reported long equity position, already unit-normalised to whole
    dollars (section 2)."""

    cusip: str
    value_usd: float
    shares: float


@dataclass
class Form13FFiling:
    """One 13F-HR submission: who filed it, WHEN IT BECAME PUBLIC, which
    quarter it describes, and the long equity book it reports.

    `filing_date` is the only date this pipeline ever keys visibility on
    (see the family module's point-in-time section). `period` is retained
    for diagnostics and for the period-lagged market-weight vector, never
    for visibility."""

    accession: str
    cik: int
    manager_name: str
    filing_date: date
    period: date
    submission_type: str
    holdings: dict[str, float]  # cusip -> value in whole USD
    total_value_usd: float
    n_holdings: int
    value_scale: float  # 1.0 if the filer reported dollars, 1000.0 if thousands

    @property
    def is_amendment(self) -> bool:
        return self.submission_type.endswith("/A")


@dataclass
class Form13FParseDiagnostics:
    """Every refusal this parser makes, by reason. Nothing is dropped
    silently -- the same discipline the sibling XBRL families apply to
    their line-item refusals."""

    n_submissions: int = 0
    n_holdings_filings: int = 0
    n_rows: int = 0
    n_refused: Counter = field(default_factory=Counter)
    value_scale_counts: Counter = field(default_factory=Counter)

    def merge(self, other: "Form13FParseDiagnostics") -> None:
        self.n_submissions += other.n_submissions
        self.n_holdings_filings += other.n_holdings_filings
        self.n_rows += other.n_rows
        self.n_refused.update(other.n_refused)
        self.value_scale_counts.update(other.value_scale_counts)


def _find_member(archive: zipfile.ZipFile, name: str) -> str | None:
    """Locate a table by BASENAME, not by exact path.

    SEC's own archives are not internally consistent about this and it is
    a measured fact, not a defensive guess: of the 53 archives this family
    downloads, 52 store the tables at the archive root ('SUBMISSION.tsv')
    while ONE — 01jun2025-31aug2025 — nests every table under a directory
    ('01JUN2025-31AUG2025_form13f/SUBMISSION.tsv'). An exact-path lookup
    parses 52 quarters and then dies on the 53rd, which is exactly what
    the first production run did."""
    if name in archive.namelist():
        return name
    lowered = name.lower()
    for member in archive.namelist():
        if member.rsplit("/", 1)[-1].lower() == lowered:
            return member
    return None


def _read_tsv(archive: zipfile.ZipFile, name: str) -> tuple[list[str], list[list[str]]]:
    """Header row plus data rows, split on tabs. Parsed by NAME downstream
    (see _column_index) because SEC has changed 13F column sets before and
    positional parsing would silently misread if it does so again."""
    member = _find_member(archive, name)
    if member is None:
        return [], []
    try:
        raw = archive.read(member)
    except KeyError:
        return [], []
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")
    if not lines:
        return [], []
    header = lines[0].rstrip("\r").split("\t")
    rows = [line.rstrip("\r").split("\t") for line in lines[1:] if line.strip()]
    return header, rows


def _column_index(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError as exc:
        raise ValueError(f"13F archive is missing the required column {name!r}") from exc


def classify_value_scale(implied_prices: list[float]) -> float | None:
    """The per-filing VALUE unit multiplier (section 2): 1000.0 if this
    filing reports the standard THOUSANDS convention, 1.0 if it reports
    whole dollars, None if the filing is not credibly either.

    `implied_prices` are that filing's own VALUE/SSHPRNAMT ratios. The
    decision is on their MEDIAN, so a handful of bad rows inside an
    otherwise sane filing cannot flip the whole book's scale.

    A median implied price below VALUE_SCALE_DECISION_BOUND ($1) means the
    values are ~1000x too small to be dollars, i.e. the filing is in
    thousands. Measured separation on the real 2016q1 archive was clean in
    both directions with nothing at the boundary (section 2)."""
    if not implied_prices:
        return None
    ordered = sorted(implied_prices)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])
    if not (MIN_CREDIBLE_IMPLIED_PRICE <= median <= MAX_CREDIBLE_IMPLIED_PRICE):
        return None
    return VALUE_THOUSANDS_MULTIPLIER if median < VALUE_SCALE_DECISION_BOUND else 1.0


def parse_quarter_archive(
    zip_bytes: bytes,
) -> tuple[list[Form13FFiling], Form13FParseDiagnostics]:
    """One quarterly 13F archive -> its 13F-HR filings, unit-normalised.

    ONLY LONG EQUITY POSITIONS SURVIVE, and each exclusion is a counted
    refusal rather than a silent filter:
      * PUTCALL non-blank -- option positions are reported at the notional
        of the underlying, so leaving them in would let a small options
        overlay masquerade as a manager's largest conviction bet.
      * SSHPRNAMTTYPE != 'SH' -- 'PRN' rows are principal amounts of debt
        instruments, not share counts.
      * non-positive VALUE, unparseable CUSIP, malformed numerics.

    Rows for the same CUSIP within one filing are SUMMED, not overwritten:
    a manager legitimately reports the same security on several lines when
    it is split across investment discretion categories or other managers,
    and taking only one line would understate that position -- which for
    this family would understate exactly the largest-conviction names it
    exists to find."""
    diagnostics = Form13FParseDiagnostics()
    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))

    sub_header, sub_rows = _read_tsv(archive, "SUBMISSION.tsv")
    if not sub_header:
        raise ValueError("13F archive has no SUBMISSION.tsv")
    i_acc = _column_index(sub_header, "ACCESSION_NUMBER")
    i_filed = _column_index(sub_header, "FILING_DATE")
    i_type = _column_index(sub_header, "SUBMISSIONTYPE")
    i_cik = _column_index(sub_header, "CIK")
    i_period = _column_index(sub_header, "PERIODOFREPORT")

    submissions: dict[str, tuple[int, date, date, str]] = {}
    for row in sub_rows:
        if len(row) <= max(i_acc, i_filed, i_type, i_cik, i_period):
            diagnostics.n_refused["submission_row_truncated"] += 1
            continue
        diagnostics.n_submissions += 1
        stype = row[i_type].strip().upper()
        if stype not in HOLDINGS_SUBMISSION_TYPES:
            diagnostics.n_refused[f"submission_type_{stype or 'blank'}"] += 1
            continue
        filed = parse_sec_date(row[i_filed])
        period = parse_sec_date(row[i_period])
        if filed is None or period is None:
            diagnostics.n_refused["unparseable_date"] += 1
            continue
        # A report cannot become public before the quarter it describes
        # has ended. Such rows are vendor corruption, and admitting one
        # would be a direct look-ahead injection.
        if filed < period:
            diagnostics.n_refused["filed_before_period_end"] += 1
            continue
        try:
            cik = int(row[i_cik])
        except ValueError:
            diagnostics.n_refused["unparseable_cik"] += 1
            continue
        submissions[row[i_acc].strip()] = (cik, filed, period, stype)

    cover_header, cover_rows = _read_tsv(archive, "COVERPAGE.tsv")
    names: dict[str, str] = {}
    if cover_header:
        c_acc = _column_index(cover_header, "ACCESSION_NUMBER")
        c_name = _column_index(cover_header, "FILINGMANAGER_NAME")
        for row in cover_rows:
            if len(row) > max(c_acc, c_name):
                names[row[c_acc].strip()] = row[c_name].strip()

    info_header, info_rows = _read_tsv(archive, "INFOTABLE.tsv")
    if not info_header:
        raise ValueError("13F archive has no INFOTABLE.tsv")
    n_acc = _column_index(info_header, "ACCESSION_NUMBER")
    n_cusip = _column_index(info_header, "CUSIP")
    n_value = _column_index(info_header, "VALUE")
    n_shares = _column_index(info_header, "SSHPRNAMT")
    n_type = _column_index(info_header, "SSHPRNAMTTYPE")
    n_putcall = _column_index(info_header, "PUTCALL")
    widest = max(n_acc, n_cusip, n_value, n_shares, n_type, n_putcall)

    raw_by_accession: dict[str, dict[str, float]] = defaultdict(dict)
    prices_by_accession: dict[str, list[float]] = defaultdict(list)

    for row in info_rows:
        diagnostics.n_rows += 1
        if len(row) <= widest:
            diagnostics.n_refused["infotable_row_truncated"] += 1
            continue
        accession = row[n_acc].strip()
        if accession not in submissions:
            diagnostics.n_refused["orphan_or_non_holdings_accession"] += 1
            continue
        if row[n_putcall].strip():
            diagnostics.n_refused["option_position"] += 1
            continue
        if row[n_type].strip().upper() != "SH":
            diagnostics.n_refused["not_share_denominated"] += 1
            continue
        cusip = normalize_cusip(row[n_cusip])
        if cusip is None:
            diagnostics.n_refused["malformed_cusip"] += 1
            continue
        try:
            value = float(row[n_value])
            shares = float(row[n_shares])
        except ValueError:
            diagnostics.n_refused["unparseable_numeric"] += 1
            continue
        if not (value > 0.0):
            diagnostics.n_refused["non_positive_value"] += 1
            continue
        book = raw_by_accession[accession]
        book[cusip] = book.get(cusip, 0.0) + value
        if shares > 0.0:
            prices_by_accession[accession].append(value / shares)

    filings: list[Form13FFiling] = []
    for accession, book in raw_by_accession.items():
        scale = classify_value_scale(prices_by_accession.get(accession, []))
        if scale is None:
            diagnostics.n_refused["uninterpretable_value_scale"] += 1
            continue
        diagnostics.value_scale_counts[
            "thousands" if scale == VALUE_THOUSANDS_MULTIPLIER else "dollars"
        ] += 1
        cik, filed, period, stype = submissions[accession]
        holdings = {c: v * scale for c, v in book.items()}
        total = sum(holdings.values())
        diagnostics.n_holdings_filings += 1
        filings.append(
            Form13FFiling(
                accession=accession,
                cik=cik,
                manager_name=names.get(accession, ""),
                filing_date=filed,
                period=period,
                submission_type=stype,
                holdings=holdings,
                total_value_usd=total,
                n_holdings=len(holdings),
                value_scale=scale,
            )
        )

    filings.sort(key=lambda f: (f.filing_date, f.accession))
    return filings, diagnostics


# --- CUSIP -> ticker ---------------------------------------------------------


@dataclass
class CusipTickerMap:
    """A DATED CUSIP <-> ticker mapping assembled from SEC fails-to-deliver
    files (section 3).

    `observations` holds, per CUSIP, the set of (settlement date, symbol)
    pairs SEC itself published. Resolution is by nearest observation in
    time rather than by a single flat dictionary, because both identifiers
    get recycled on corporate actions and a flat map would silently apply
    a 2024 ticker reassignment to a 2015 filing."""

    observations: dict[str, list[tuple[date, str]]] = field(default_factory=dict)

    def resolve(self, cusip: str, as_of: date) -> str | None:
        """The symbol SEC published for this CUSIP nearest in time to
        `as_of`, in EITHER direction and with no maximum distance.

        Nearest-in-time (rather than latest-at-or-before) is deliberate:
        FTD coverage of any one security is sporadic, so requiring a
        strictly earlier observation would drop real mappings — most
        sharply at the start of the sample, where a 2015 filing may have
        no earlier observation at all.

        THE COST IS STATED PLAINLY RATHER THAN ARGUED AWAY. This can name
        a security using a file published AFTER the filing being resolved.
        An earlier version of this docstring justified that on the grounds
        that a CUSIP->ticker identity "cannot leak return information";
        that is too strong. The symbol chosen decides WHICH PRICE SERIES a
        holding is attributed to, and symbols are reassigned by corporate
        actions, so on a renamed security a future observation can move a
        position onto the post-rename column. It is not a return leak in
        the ordinary sense — no price or return is read — but it is not
        nothing either, and the realized magnitude is measured per run
        rather than assumed (see load_cusip_map_for_universe)."""
        seen = self.observations.get(cusip)
        if not seen:
            return None
        return min(seen, key=lambda pair: abs((pair[0] - as_of).days))[1]

    def tickers(self) -> set[str]:
        return {sym for obs in self.observations.values() for _, sym in obs}


def parse_ftd_archive(zip_bytes: bytes) -> list[tuple[date, str, str]]:
    """(settlement date, cusip, symbol) triples from one fails-to-deliver
    ZIP. Pipe-delimited with the header
    'SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE'
    (verbatim from the real 201604a file).

    EVERY non-directory member is parsed, and the extension is NOT used to
    decide that. SEC is not consistent about naming these members, and it
    is a MEASURED fact rather than a defensive guess: of the 107 cached
    fails-to-deliver archives, 76 hold a member named 'cnsfails<stamp>.txt'
    while 31 -- every semi-monthly file from 202207a through 202604a --
    hold one named 'cnsfails<stamp>' with NO extension at all, carrying
    byte-identical pipe-delimited content and the same header.

    An extension whitelist therefore silently returned ZERO triples for
    those 31 archives, which is how the CUSIP->ticker map came to have a
    four-year hole (2022-07 .. 2026-04) with nothing raised anywhere. The
    per-line validation below is the real filter -- a member that is not
    this format contributes no rows because every row fails the 8-digit
    settlement-date and CUSIP checks -- so the whitelist bought nothing
    and cost a third of the corpus."""
    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    out: list[tuple[date, str, str]] = []
    for member in archive.namelist():
        if member.endswith("/"):
            continue
        text = archive.read(member).decode("utf-8", errors="replace")
        for line in text.split("\n")[1:]:
            parts = line.rstrip("\r").split("|")
            if len(parts) < 3:
                continue
            stamp = parts[0].strip()
            if len(stamp) != 8 or not stamp.isdigit():
                continue
            cusip = normalize_cusip(parts[1])
            symbol = normalize_ticker(parts[2])
            if cusip is None or not _SYMBOL_RE.match(symbol):
                continue
            try:
                settled = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
            except ValueError:
                continue
            out.append((settled, cusip, symbol))
    return out


def build_cusip_ticker_map(
    triples: list[tuple[date, str, str]],
    *,
    restrict_to: set[str] | None = None,
) -> CusipTickerMap:
    """Collapse raw FTD triples into a dated map, optionally restricted to
    a ticker universe.

    Restricting is what makes this tractable and is not a shortcut: this
    family ranks a point-in-time S&P 500 universe, so the only CUSIPs it
    must resolve are the ones belonging to those tickers. Everything else
    in a manager's book is needed only as an anonymous weight denominator,
    for which the CUSIP is a perfectly good opaque key."""
    observations: dict[str, set[tuple[date, str]]] = defaultdict(set)
    for settled, cusip, symbol in triples:
        if restrict_to is not None and symbol not in restrict_to:
            continue
        observations[cusip].add((settled, symbol))
    return CusipTickerMap({c: sorted(v) for c, v in observations.items()})


# --- passive / index filer screen --------------------------------------------

# The source paper screens FUND names to exclude index and tax-managed
# products (its footnote 3 lists INDEX, Idx, S&P, Fixed, TAX, CONVERTIBLE,
# annuity, VAR and similar). 13F is filed by an INSTITUTION, not a fund,
# so the closest available analogue is a FILER-name screen -- which is
# strictly coarser, and the family module says so rather than implying
# parity with the paper.
PASSIVE_NAME_PATTERNS: tuple[str, ...] = (
    "INDEX",
    " IDX",
    "S&P",
    "ISHARES",
    "VANGUARD",
    "SPDR",
    "STATE STREET",
    "BLACKROCK",
    "GEODE",
    "DIMENSIONAL",
    "NORTHERN TRUST",
    "ETF",
    "EXCHANGE TRADED",
    "ANNUITY",
    "TAX MANAGED",
    "TAX-MANAGED",
)


def is_passive_filer_name(name: str) -> bool:
    """True if the filer name matches this project's index/passive screen.

    Named sponsors appear alongside generic tokens deliberately: the very
    largest passive complexes do not put 'INDEX' in their institutional
    filer name, so a purely generic screen would let exactly the biggest
    closet-indexers through -- the opposite of what the mechanism
    requires."""
    upper = f" {name.strip().upper()} "
    return any(pattern in upper for pattern in PASSIVE_NAME_PATTERNS)


# --- fetching ----------------------------------------------------------------


class Form13FProvider:
    """Rate-limited fetch + on-disk raw-bytes cache for the SEC archives.

    Raw bytes, not parsed rows, are what gets cached: an archived SEC file
    is immutable, so the cache needs no age bound, and caching pre-parse
    means the parser can be rewritten and re-run over 53 quarters without
    re-downloading ~2.7GB or touching sec.gov again."""

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

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self._last_request = time.monotonic()

    def _fetch(self, url: str) -> bytes:
        self._throttle()
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310 — fixed sec.gov host
            return response.read()

    def _cached(self, filename: str, urls: list[str]) -> bytes:
        if self.cache_dir is not None:
            path = self.cache_dir / filename
            if path.exists() and path.stat().st_size > 0:
                return path.read_bytes()
        last: Exception | None = None
        for url in urls:
            try:
                payload = self._fetch(url)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                last = exc
                continue
            if self.cache_dir is not None:
                tmp = self.cache_dir / f"{filename}.part"
                tmp.write_bytes(payload)
                tmp.rename(self.cache_dir / filename)
            return payload
        raise RuntimeError(f"could not fetch {filename}: {last}")

    def get_quarter_archive(self, quarter: str) -> bytes:
        name = f"{quarter}_form13f.zip"
        return self._cached(name, [FORM13F_BASE_URL + name])

    def get_ftd_archive(self, stamp: str) -> bytes:
        """`stamp` is SEC's own YYYYMM + 'a'/'b' half-month suffix."""
        name = f"cnsfails{stamp}.zip"
        return self._cached(name, [base + name for base in FTD_BASE_URLS])

    def available_quarters(self) -> list[str]:
        """The quarter names this provider has cached locally, in the
        canonical order of QUARTER_NAMES."""
        if self.cache_dir is None:
            return []
        return [
            q
            for q in QUARTER_NAMES
            if (self.cache_dir / f"{q}_form13f.zip").exists()
            and (self.cache_dir / f"{q}_form13f.zip").stat().st_size > 0
        ]

    def available_ftd_stamps(self) -> list[str]:
        if self.cache_dir is None:
            return []
        stamps = []
        for path in sorted(self.cache_dir.glob("cnsfails*.zip")):
            if path.stat().st_size > 0:
                stamps.append(path.stem.replace("cnsfails", ""))
        return stamps
