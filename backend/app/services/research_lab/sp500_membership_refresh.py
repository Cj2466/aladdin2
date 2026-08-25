import csv
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date
from io import BytesIO, StringIO

import httpx

from app.services.research_lab.sp500_membership_history import (
    MEMBERSHIP_DATA_AS_OF,
    MEMBERSHIP_DATA_START,
    MembershipExtension,
    apply_membership_extension,
    get_membership_extension,
    get_universe_as_of,
    vendored_events,
)

logger = logging.getLogger(__name__)

# Keeps sp500_membership_history.py's vendored literals from silently going
# stale the way ticker_universe.SCREENING_UNIVERSE does. Three free,
# no-signup sources, each doing the one job it is actually good at:
#
#  (1) github.com/fja05680/sp500 (MIT licensed — verified 2026-08-25 via the
#      GitHub API's license field, so scheduled programmatic re-fetching is
#      explicitly permitted, not merely tolerated). This is the SAME file
#      sp500_membership_history.py was vendored from, and it is the only one
#      of the three that carries DATED historical changes. Cadence measured
#      from its real commit log on 2026-08-25: updates land roughly every
#      one to four months (2026-07-13, 2026-06-08, 2026-01-17, 2025-11-09,
#      2025-07-12, 2025-03-10, 2024-12-10, 2024-11-28, 2024-08-17,
#      2024-04-08, ...), matching its README's own "every couple of months".
#      Good enough to bound staleness; too slow to be the only source.
#      Empirically verified 2026-08-25: re-fetching this file today and
#      replaying it through _derive_events below reproduces the vendored
#      _BASE_UNIVERSE (499/499) and all 235 _MEMBERSHIP_EVENTS EXACTLY,
#      which is what makes an automated re-fetch trustworthy at all — the
#      parser is not "probably equivalent" to what was hand-checked, it is
#      provably identical on the hand-checked window.
#
#  (2) The SPDR S&P 500 ETF Trust (SPY) daily holdings file from State
#      Street. SPY is a unit investment trust that must replicate the index
#      exactly, so its holdings ARE the constituent list — no sampling, no
#      substitutes. Published every business day, free, no signup, no API
#      key, and the file states its own as-of date. Verified 2026-08-25:
#      the 2026-08-24 file's 503 equity lines match
#      ticker_universe.SCREENING_UNIVERSE 503/503 after dot->dash
#      translation, with exactly two non-equity lines to filter (a US
#      DOLLAR cash line and a "CONTRA HOLOGIC INCORPO" merger-contra line,
#      both excluded by _TICKER_RE below).
#
#  (3) datasets/s-and-p-500-companies' constituents.csv — a bot-maintained
#      mirror of Wikipedia's List of S&P 500 companies, committed on a
#      near-daily cadence (measured 2026-08-25: 15 commits in the trailing
#      ~3.5 months). Independent of (2) in every way that matters — a
#      different organisation deriving membership from a different place —
#      and it is the only source of the three that carries a per-company
#      "Date added", which is what lets an addition observed AFTER
#      upstream's coverage still be dated exactly rather than dated
#      "whenever this process happened to look".
#
# WHAT THIS DELIBERATELY DOES NOT DO: synthesize REMOVAL dates. A removal
# is visible live (the ticker vanishes from SPY and from Wikipedia) but
# none of these sources publishes its effective date, and dating it "the
# day this process first noticed" would be wrong by however long the
# process was not running. So removals after coverage_end are disclosed
# WITHOUT a date (see build_membership_warnings) and get their real date
# later, from (1). S&P Dow Jones Indices' own announcements would carry
# exact removal dates, but spglobal.com/spdji answers 403 to a plain
# programmatic GET and press.spglobal.com serves a JavaScript app rather
# than a feed (both re-checked 2026-08-25) — there is no free, stable,
# machine-readable channel for them.
#
# DEAD ENDS, all re-checked 2026-08-25 so nobody re-walks them: iShares IVV
# holdings (returns the fund's terms-of-use HTML page, not the CSV, to an
# un-cookied client); Vanguard VOO (JS single-page app, no plain data
# endpoint); Invesco RSP holdings CSV (HTTP 406 to non-browser clients);
# slickcharts.com/sp500 (HTTP 403, Cloudflare); Financial Modeling Prep's
# sp500_constituent (HTTP 401 — free tier exists but requires signup, and
# its dated historical-constituent endpoint is paid); stockanalysis.com's
# screener API (HTTP 404, endpoint moved). Wikipedia's own "Selected
# changes" table — which would have given dated removals — no longer
# exists: the article is down to four sections (component stocks, See
# also, References, External links), independently reconfirming what
# sp500_membership_history.py already records.

USER_AGENT = "aladdin2-research/1.0 (S&P 500 membership refresh)"

UPSTREAM_RAW_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv"
)
# The upstream file was named with an embedded date ("... (08-17-2025).csv")
# until mid-2026 and only recently settled on "(Updated)" — measured
# 2026-08-25: only two commits ever touch the current path, because the
# earlier history lives under the old names. So a hardcoded raw URL is a
# real single point of failure, and a rename must degrade to "discover the
# file" rather than to "silently stop refreshing forever."
UPSTREAM_CONTENTS_API_URL = "https://api.github.com/repos/fja05680/sp500/contents/"
UPSTREAM_FILE_PREFIX = "S&P 500 Historical Components & Changes"

SPY_HOLDINGS_URL = "https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
WIKIPEDIA_CONSTITUENTS_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
)

# --- Validation bounds. Every one of these is a MEASURED property of the
# vendored data (2026-08-25), not a guess, so a breach really does mean
# "the fetch or the parse is broken", not "the index did something
# unusual". ----------------------------------------------------------------

# Reconstructed universe size across all 236 vendored reconstruction points:
# min 498, max 507. This band is deliberately much wider — it is a
# malformed-fetch tripwire (a truncated file, an HTML error page parsed as
# CSV, a symbology change that orphans half the tickers), not an index
# forecast.
MIN_PLAUSIBLE_UNIVERSE_SIZE = 480
MAX_PLAUSIBLE_UNIVERSE_SIZE = 520

# Largest single-date churn in the vendored window: 9 tickers on 2017-07-26
# (5 added, 4 removed). 25 leaves room for an unusually large rebalance
# while still catching a file whose dates have collapsed together.
MAX_TICKER_CHANGES_PER_EFFECTIVE_DATE = 25

# SPY and the Wikipedia mirror agreed exactly (503/503) on 2026-08-24, but
# requiring exact agreement forever would let one source's one-day timing
# lag block every refresh. A ticker must appear in BOTH to count as a live
# member and be absent from BOTH to count as a live non-member, so a
# disagreement is never resolved in favour of either source — it just
# leaves that ticker undecided. This bounds how much undecidedness is
# tolerable before the whole live tier is treated as broken.
MAX_LIVE_SOURCE_DISAGREEMENT = 10

# Live-vs-reconstruction drift allowance. Measured: the index never moved
# more than 28 ticker-changes in any 90-day window in the vendored data
# (~0.31/day), and annual churn runs 28-58 ticker-changes. 20 + 0.6/day is
# roughly a 2x headroom on the worst observed rate — generous enough never
# to fire on real index activity, tight enough that a garbage live fetch
# (which disagrees on hundreds of tickers) is rejected outright.
LIVE_DRIFT_ALLOWANCE_BASE = 20
LIVE_DRIFT_ALLOWANCE_PER_DAY = 0.6

# How long a previously fetched live constituent set may keep being used
# after the live sources stop responding. The disclosure it feeds always
# quotes its own as-of date, so an older set is misleading rather than
# wrong — but past this point "not in the index as of six months ago" is
# not worth saying.
LIVE_MEMBERSHIP_MAX_AGE_DAYS = 45

# A Wikipedia "Date added" this much earlier than the event date that
# introduced the ticker means the two sources are describing the same
# COMPANY under two different tickers (META/FB, ELV/ANTM, ...), not a
# genuine new addition — the same judgement _EARLIEST_MEMBERSHIP_OVERRIDES
# encodes by hand for the vendored window, applied automatically to
# everything after it. Below this, the gap is an
# announcement-vs-effective difference (the vendored table's own worst
# case is 6 entries at 1-4 days) and taking the earlier date is harmless.
RENAME_LOOKTHROUGH_MIN_GAP_DAYS = 30

# BRK.B / BF.B and nothing else with punctuation; excludes SPY's US DOLLAR
# cash line ("-") and its merger-contra lines (CUSIP-like, digit-bearing).
_TICKER_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")

_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}  # fmt: skip
_SPY_AS_OF_RE = re.compile(r"As of\s+(\d{1,2})-([A-Za-z]{3})-(\d{4})")


class MembershipRefreshError(RuntimeError):
    """A source could not be fetched or could not be parsed into anything
    usable. Always caught by refresh_membership_data — never allowed to
    reach the runner loop, and never allowed to discard the last
    known-good data."""


@dataclass(frozen=True)
class UpstreamHistory:
    """Full point-in-time snapshots parsed out of the upstream CSV, one per
    change date, already dot->dash normalised."""

    snapshots: tuple[tuple[date, frozenset[str]], ...]
    source_url: str


@dataclass(frozen=True)
class LiveConstituents:
    """One live source's answer to "who is in the index right now"."""

    members: frozenset[str]
    as_of: date
    source: str
    # Only the Wikipedia mirror carries these; SPY's holdings file does not.
    added_dates: dict[str, date] | None = None


@dataclass(frozen=True)
class RefreshOutcome:
    """What one refresh attempt concluded. `extension is None` means
    nothing was applied and the previous state — vendored-only, or the
    last good extension — is still in force."""

    extension: MembershipExtension | None
    warnings: tuple[str, ...]
    coverage_end: date
    n_dated_events: int
    n_live_dated_additions: int
    live_as_of: date | None

    @property
    def applied(self) -> bool:
        return self.extension is not None


# --- Symbology / small parsers -------------------------------------------


def _normalize_ticker(raw: str) -> str | None:
    """yfinance's dash convention, or None for anything that isn't a US
    equity ticker — which is how the cash and merger-contra lines in an
    ETF holdings file get dropped without hardcoding their names."""
    ticker = raw.strip().upper()
    if not _TICKER_RE.match(ticker):
        return None
    return ticker.replace(".", "-")


def _parse_iso_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip()[:10])
    except (ValueError, AttributeError):
        return None


def _xlsx_rows(content: bytes) -> list[list[str | None]]:
    """Minimal read-only xlsx reader over the first worksheet. Deliberately
    stdlib-only (zipfile + ElementTree): an xlsx is a zip of XML, this
    needs one sheet's cell text and nothing else, and adding openpyxl as a
    runtime dependency to read one column of one file would be a poor
    trade."""
    try:
        archive = zipfile.ZipFile(BytesIO(content))
        shared = [
            "".join(node.text or "" for node in si.iter(_XLSX_NS + "t"))
            for si in ET.fromstring(archive.read("xl/sharedStrings.xml"))
        ]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise MembershipRefreshError(f"Not a readable xlsx workbook: {exc}") from exc

    rows: list[list[str | None]] = []
    for row in sheet.iter(_XLSX_NS + "row"):
        values: list[str | None] = []
        for cell in row.iter(_XLSX_NS + "c"):
            value = cell.find(_XLSX_NS + "v")
            if value is None:
                values.append(None)
            elif cell.get("t") == "s":
                index = int(value.text or "0")
                values.append(shared[index] if 0 <= index < len(shared) else None)
            else:
                values.append(value.text)
        rows.append(values)
    return rows


# --- Fetchers (network) ---------------------------------------------------


def _get(client: httpx.Client, url: str) -> httpx.Response:
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        raise MembershipRefreshError(f"GET {url} failed: {exc}") from exc
    return response


def _discover_upstream_url(client: httpx.Client) -> str:
    """Ask GitHub which historical-components file the repo currently has,
    for the day the maintainer renames it again."""
    response = _get(client, UPSTREAM_CONTENTS_API_URL)
    if response.status_code != 200:
        raise MembershipRefreshError(
            f"Could not list {UPSTREAM_CONTENTS_API_URL} (HTTP {response.status_code}) to find the "
            f"point-in-time file after {UPSTREAM_RAW_URL} 404'd."
        )
    try:
        entries = response.json()
    except ValueError as exc:
        raise MembershipRefreshError(f"GitHub contents listing was not JSON: {exc}") from exc

    candidates = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and str(entry.get("name", "")).startswith(UPSTREAM_FILE_PREFIX)
        and str(entry.get("name", "")).endswith(".csv")
        and entry.get("download_url")
    ]
    if not candidates:
        raise MembershipRefreshError(
            f"No file named '{UPSTREAM_FILE_PREFIX}*.csv' in fja05680/sp500 any more; the vendored "
            f"snapshot is now the only point-in-time source and needs a human to re-source it."
        )
    # "(Updated)" is the maintained output file; the bare name is the frozen
    # 1996-2019 input it is built from, so never prefer that one.
    updated = [entry for entry in candidates if "Updated" in entry["name"]]
    chosen = max(updated or candidates, key=lambda entry: entry["name"])
    return str(chosen["download_url"])


def fetch_upstream_history(client: httpx.Client) -> UpstreamHistory:
    """The dated point-in-time file, parsed into per-change-date snapshots
    restricted to this module's covered era."""
    url = UPSTREAM_RAW_URL
    response = _get(client, url)
    if response.status_code == 404:
        url = _discover_upstream_url(client)
        response = _get(client, url)
    if response.status_code != 200:
        raise MembershipRefreshError(f"GET {url} returned HTTP {response.status_code}.")

    snapshots: list[tuple[date, frozenset[str]]] = []
    reader = csv.reader(StringIO(response.text))
    header = next(reader, None)
    if header is None or [column.strip().lower() for column in header[:2]] != ["date", "tickers"]:
        raise MembershipRefreshError(f"{url} does not have the expected 'date,tickers' header (got {header}).")
    for row in reader:
        if len(row) < 2:
            continue
        snapshot_date = _parse_iso_date(row[0])
        if snapshot_date is None or snapshot_date < MEMBERSHIP_DATA_START:
            continue
        members = frozenset(
            ticker for ticker in (_normalize_ticker(raw) for raw in row[1].split(",")) if ticker is not None
        )
        snapshots.append((snapshot_date, members))

    if not snapshots:
        raise MembershipRefreshError(f"{url} yielded no snapshots at or after {MEMBERSHIP_DATA_START.isoformat()}.")
    snapshots.sort()
    return UpstreamHistory(snapshots=tuple(snapshots), source_url=url)


def _parse_spy_workbook_rows(rows: list[list[str | None]]) -> LiveConstituents:
    """The SPY holdings sheet's real shape: a few key/value preamble rows
    (one of which carries "As of DD-Mon-YYYY"), a Name/Ticker/... header
    row, the holdings, then free-text disclaimer rows. Split out from the
    fetch so the parsing rules are testable against that shape without a
    network round trip or a binary fixture."""
    as_of: date | None = None
    ticker_column: int | None = None
    members: set[str] = set()
    for row in rows:
        cells = [(cell or "").strip() for cell in row]
        if as_of is None:
            match = _SPY_AS_OF_RE.search(" ".join(cells))
            if match:
                day, month, year = match.groups()
                month_number = _MONTHS.get(month.title())
                if month_number is not None:
                    as_of = date(int(year), month_number, int(day))
        if ticker_column is None:
            if cells and cells[0] == "Name" and "Ticker" in cells:
                ticker_column = cells.index("Ticker")
            continue
        if ticker_column < len(cells):
            ticker = _normalize_ticker(cells[ticker_column])
            if ticker is not None:
                members.add(ticker)

    if ticker_column is None:
        raise MembershipRefreshError(f"{SPY_HOLDINGS_URL} has no 'Name'/'Ticker' header row any more.")
    if as_of is None:
        raise MembershipRefreshError(
            f"{SPY_HOLDINGS_URL} carries no 'As of DD-Mon-YYYY' line; refusing to guess how current it is."
        )
    if not members:
        raise MembershipRefreshError(f"{SPY_HOLDINGS_URL} yielded no equity holdings.")
    return LiveConstituents(members=frozenset(members), as_of=as_of, source="SPY holdings (State Street)")


def fetch_spy_constituents(client: httpx.Client) -> LiveConstituents:
    """SPY's daily holdings, which for a replicating unit investment trust
    are the index's constituents."""
    response = _get(client, SPY_HOLDINGS_URL)
    if response.status_code != 200:
        raise MembershipRefreshError(f"GET {SPY_HOLDINGS_URL} returned HTTP {response.status_code}.")
    return _parse_spy_workbook_rows(_xlsx_rows(response.content))


def fetch_wikipedia_constituents(client: httpx.Client, *, today: date | None = None) -> LiveConstituents:
    """The Wikipedia-derived constituent list, with its per-company
    "Date added" column — the only free source that dates an addition
    before the point-in-time file catches up."""
    response = _get(client, WIKIPEDIA_CONSTITUENTS_URL)
    if response.status_code != 200:
        raise MembershipRefreshError(f"GET {WIKIPEDIA_CONSTITUENTS_URL} returned HTTP {response.status_code}.")

    reader = csv.DictReader(StringIO(response.text))
    if reader.fieldnames is None or "Symbol" not in reader.fieldnames:
        raise MembershipRefreshError(
            f"{WIKIPEDIA_CONSTITUENTS_URL} has no 'Symbol' column (got {reader.fieldnames})."
        )
    members: set[str] = set()
    added_dates: dict[str, date] = {}
    for row in reader:
        ticker = _normalize_ticker(row.get("Symbol") or "")
        if ticker is None:
            continue
        members.add(ticker)
        added = _parse_iso_date(row.get("Date added") or "")
        if added is not None:
            added_dates[ticker] = added

    if not members:
        raise MembershipRefreshError(f"{WIKIPEDIA_CONSTITUENTS_URL} yielded no tickers.")
    # This mirror carries no as-of field of its own; it is regenerated from
    # Wikipedia on a near-daily bot cadence, so the fetch date is the
    # honest upper bound on how current it is.
    return LiveConstituents(
        members=frozenset(members),
        as_of=today or date.today(),
        source="Wikipedia mirror (datasets/s-and-p-500-companies)",
        added_dates=added_dates,
    )


# --- Pure derivation / validation ----------------------------------------


def derive_events(
    snapshots: tuple[tuple[date, frozenset[str]], ...],
) -> tuple[frozenset[str], tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...]]:
    """Consecutive-snapshot diffing: the exact transformation that produced
    sp500_membership_history.py's vendored literals, kept in one place so
    "what the refresh computes" and "what was hand-verified" cannot drift
    apart. Verified 2026-08-25 to reproduce _BASE_UNIVERSE and all 235
    _MEMBERSHIP_EVENTS identically from today's upstream file."""
    if not snapshots:
        return frozenset(), ()
    base = snapshots[0][1]
    events: list[tuple[date, tuple[str, ...], tuple[str, ...]]] = []
    previous = base
    for effective, members in snapshots[1:]:
        added = tuple(sorted(members - previous))
        removed = tuple(sorted(previous - members))
        if added or removed:
            events.append((effective, added, removed))
        previous = members
    return base, tuple(events)


def _replay(base: frozenset[str], events, until: date) -> set[str]:
    universe = set(base)
    for effective, added, removed in events:
        if effective > until:
            break
        universe.difference_update(removed)
        universe.update(added)
    return universe


def _validate_forward_events(
    events: tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...],
    universe_at_handoff: set[str],
    today: date,
) -> list[str]:
    """Everything that must hold for a batch of new events to be worth
    trusting. Returns rejection reasons; empty means accept."""
    reasons: list[str] = []
    dates = [effective for effective, _added, _removed in events]
    if dates != sorted(dates):
        reasons.append("new events are not in chronological order")
    if dates and dates[0] <= MEMBERSHIP_DATA_AS_OF:
        reasons.append(
            f"new events reach back into the verified window (earliest {dates[0].isoformat()} "
            f"<= {MEMBERSHIP_DATA_AS_OF.isoformat()})"
        )
    if dates and dates[-1] > today:
        reasons.append(f"new events are dated in the future (latest {dates[-1].isoformat()} > {today.isoformat()})")

    universe = set(universe_at_handoff)
    for effective, added, removed in events:
        if set(added) & set(removed):
            reasons.append(f"{effective.isoformat()} both adds and removes the same ticker")
        if len(added) + len(removed) > MAX_TICKER_CHANGES_PER_EFFECTIVE_DATE:
            reasons.append(
                f"{effective.isoformat()} changes {len(added) + len(removed)} tickers, over the "
                f"{MAX_TICKER_CHANGES_PER_EFFECTIVE_DATE} plausible-churn limit"
            )
        universe.difference_update(removed)
        universe.update(added)
        if not MIN_PLAUSIBLE_UNIVERSE_SIZE <= len(universe) <= MAX_PLAUSIBLE_UNIVERSE_SIZE:
            reasons.append(
                f"universe size {len(universe)} at {effective.isoformat()} is outside the plausible "
                f"{MIN_PLAUSIBLE_UNIVERSE_SIZE}-{MAX_PLAUSIBLE_UNIVERSE_SIZE} band"
            )
    return reasons


def _reconcile_live_sources(
    spy: LiveConstituents | None,
    wikipedia: LiveConstituents | None,
) -> tuple[frozenset[str] | None, date | None, list[str]]:
    """Two independent sources reduced to one answer, or to nothing. A
    ticker counts as a live member only if BOTH sources list it, so
    neither source can single-handedly assert a membership; the price is
    that a ticker only one source knows about is simply undecided, which
    MAX_LIVE_SOURCE_DISAGREEMENT bounds."""
    warnings: list[str] = []
    if spy is None or wikipedia is None:
        available = [source.source for source in (spy, wikipedia) if source is not None]
        return None, None, [
            (
                f"Live constituent cross-check skipped: {len(available)} of 2 sources available "
                f"({', '.join(available) or 'none'}), and a single unconfirmed source is not enough "
                f"to assert index membership."
            )
        ]

    for source in (spy, wikipedia):
        if not MIN_PLAUSIBLE_UNIVERSE_SIZE <= len(source.members) <= MAX_PLAUSIBLE_UNIVERSE_SIZE:
            warnings.append(
                f"{source.source} returned {len(source.members)} tickers, outside the plausible "
                f"{MIN_PLAUSIBLE_UNIVERSE_SIZE}-{MAX_PLAUSIBLE_UNIVERSE_SIZE} band; live tier rejected."
            )
            return None, None, warnings

    disagreement = spy.members ^ wikipedia.members
    if len(disagreement) > MAX_LIVE_SOURCE_DISAGREEMENT:
        warnings.append(
            f"{spy.source} and {wikipedia.source} disagree on {len(disagreement)} tickers "
            f"(limit {MAX_LIVE_SOURCE_DISAGREEMENT}); live tier rejected rather than picking a winner."
        )
        return None, None, warnings
    if disagreement:
        warnings.append(
            f"{spy.source} and {wikipedia.source} disagree on {len(disagreement)} ticker(s) "
            f"({', '.join(sorted(disagreement))}); those are treated as undecided, not as members."
        )
    return spy.members & wikipedia.members, min(spy.as_of, wikipedia.as_of), warnings


def _carry_forward_live_layer(
    previous: MembershipExtension | None,
    coverage_end: date,
    today: date,
) -> tuple[frozenset[str] | None, date | None, tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...]]:
    """Reuse the last good live layer when the live sources are down this
    round, dropping anything upstream has since superseded or that has
    aged out. Failing safe here means "keep saying what we last verified",
    never "forget it and silently under-disclose"."""
    if previous is None or previous.live_members is None or previous.live_as_of is None:
        return None, None, ()
    if (today - previous.live_as_of).days > LIVE_MEMBERSHIP_MAX_AGE_DAYS:
        return None, None, ()
    carried = tuple(event for event in previous.events if event[0] > coverage_end)
    return previous.live_members, previous.live_as_of, carried


def plan_refresh(
    *,
    upstream: UpstreamHistory | None,
    spy: LiveConstituents | None,
    wikipedia: LiveConstituents | None,
    today: date,
    previous: MembershipExtension | None = None,
    fetch_warnings: tuple[str, ...] = (),
) -> RefreshOutcome:
    """The whole decision, with no network in it — every branch below is
    reachable from a unit test with hand-built inputs."""
    warnings: list[str] = list(fetch_warnings)
    # Start from whatever the last successful refresh established, NOT from
    # the vendored baseline: an upstream outage must cost freshness, never
    # already-earned coverage. Without this a single failed fetch would
    # rebuild the extension around MEMBERSHIP_DATA_AS_OF and silently
    # un-date every event gained since.
    coverage_end = max(previous.coverage_end, MEMBERSHIP_DATA_AS_OF) if previous else MEMBERSHIP_DATA_AS_OF
    forward_events: tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...] = (
        tuple(event for event in previous.events if event[0] <= coverage_end) if previous else ()
    )

    if upstream is not None:
        base, all_events = derive_events(upstream.snapshots)
        vendored_handoff = set(get_universe_as_of(MEMBERSHIP_DATA_AS_OF))
        upstream_handoff = _replay(base, all_events, MEMBERSHIP_DATA_AS_OF)
        if upstream_handoff != vendored_handoff:
            # The one unrecoverable case: splicing new events onto a
            # different membership state would produce intervals that are
            # neither the vendored truth nor upstream's. Refuse the whole
            # upstream tier and say exactly how far apart they are.
            drift = upstream_handoff ^ vendored_handoff
            warnings.append(
                f"Upstream point-in-time file no longer reproduces this module's verified state at "
                f"{MEMBERSHIP_DATA_AS_OF.isoformat()} ({len(drift)} ticker(s) differ: "
                f"{', '.join(sorted(drift)[:10])}). Refusing to extend from it; the vendored snapshot "
                f"stands and needs a human to re-verify and re-vendor."
            )
        else:
            vendored = vendored_events()
            historical = tuple(event for event in all_events if event[0] <= MEMBERSHIP_DATA_AS_OF)
            if historical != vendored:
                # Upstream really does re-date historical events sometimes
                # — it merged a fix moving the Dec-2023 rebalance from
                # 2023-10-18 to 2023-12-18. Adopting that automatically
                # would rewrite hand-verified history behind the operator's
                # back, so it is reported and NOT applied. Extending
                # forward is still safe: the end state at the handoff date
                # was just proven identical, which is the only property
                # the forward splice depends on.
                changed = sorted(
                    {event[0].isoformat() for event in set(historical) ^ set(vendored)}
                )
                warnings.append(
                    f"Upstream has revised the already-verified "
                    f"{MEMBERSHIP_DATA_START.isoformat()}..{MEMBERSHIP_DATA_AS_OF.isoformat()} window "
                    f"on {len(changed)} date(s) ({', '.join(changed[:10])}); it now lists "
                    f"{len(historical)} events there against the vendored {len(vendored)}. The state at "
                    f"{MEMBERSHIP_DATA_AS_OF.isoformat()} still matches exactly, so extending forward is "
                    f"safe, but the vendored literals were NOT rewritten — review and re-vendor by hand."
                )
            candidate = tuple(event for event in all_events if event[0] > MEMBERSHIP_DATA_AS_OF)
            upstream_coverage_end = max(upstream.snapshots[-1][0], MEMBERSHIP_DATA_AS_OF)
            reasons = _validate_forward_events(candidate, vendored_handoff, today)
            if upstream_coverage_end < coverage_end:
                # Coverage must be monotonic. Upstream going BACKWARDS
                # means a partial/rolled-back file, not real news, and
                # accepting it would retract dated events already in use.
                reasons.append(
                    f"upstream coverage {upstream_coverage_end.isoformat()} is earlier than the "
                    f"coverage already in force ({coverage_end.isoformat()})"
                )
            if reasons:
                warnings.append(
                    f"Rejected {len(candidate)} new upstream event(s): {'; '.join(reasons)}. "
                    f"Keeping the last known-good membership data."
                )
            else:
                forward_events = candidate
                coverage_end = upstream_coverage_end

    live_members, live_as_of, live_warnings = _reconcile_live_sources(spy, wikipedia)
    warnings.extend(live_warnings)

    dated_additions: tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...] = ()
    overrides: dict[str, date] = {}
    if live_members is None or live_as_of is None:
        live_members, live_as_of, dated_additions = _carry_forward_live_layer(previous, coverage_end, today)
        if previous is not None and previous.earliest_overrides:
            overrides = {ticker: when for ticker, when in previous.earliest_overrides}
    else:
        reconstructed = _replay(
            frozenset(get_universe_as_of(MEMBERSHIP_DATA_START)),
            vendored_events() + forward_events,
            coverage_end,
        )
        live_union = (spy.members | wikipedia.members) if spy and wikipedia else live_members
        elapsed = max((live_as_of - coverage_end).days, 0)
        allowance = LIVE_DRIFT_ALLOWANCE_BASE + LIVE_DRIFT_ALLOWANCE_PER_DAY * elapsed
        drift = live_union ^ reconstructed
        if len(drift) > allowance:
            warnings.append(
                f"Live constituents differ from the point-in-time reconstruction at "
                f"{coverage_end.isoformat()} on {len(drift)} tickers, over the {allowance:.0f} allowed for "
                f"{elapsed} day(s) of index drift; live tier rejected as implausible."
            )
            live_members, live_as_of, dated_additions = _carry_forward_live_layer(previous, coverage_end, today)
        else:
            dated_additions, override_pairs, addition_warnings = _date_post_coverage_additions(
                live_members=live_members,
                reconstructed=reconstructed,
                added_dates=(wikipedia.added_dates or {}) if wikipedia else {},
                coverage_end=coverage_end,
                today=today,
            )
            overrides.update(override_pairs)
            warnings.extend(addition_warnings)

    # Look through renames for tickers upstream itself introduced after the
    # verified window — the automatic analogue of the hand-built
    # _EARLIEST_MEMBERSHIP_OVERRIDES, without which every future rename
    # would produce a false inclusion-bias warning.
    if wikipedia is not None and wikipedia.added_dates:
        for effective, added, _removed in forward_events:
            for ticker in added:
                wiki_added = wikipedia.added_dates.get(ticker)
                if wiki_added is not None and (effective - wiki_added).days >= RENAME_LOOKTHROUGH_MIN_GAP_DAYS:
                    overrides[ticker] = min(overrides.get(ticker, wiki_added), wiki_added)

    events = tuple(sorted(forward_events + dated_additions))
    if not events and live_members is None:
        return RefreshOutcome(
            extension=None,
            warnings=tuple(warnings),
            coverage_end=coverage_end,
            n_dated_events=0,
            n_live_dated_additions=0,
            live_as_of=None,
        )

    extension = MembershipExtension(
        coverage_end=coverage_end,
        events=events,
        earliest_overrides=tuple(sorted(overrides.items())),
        live_members=live_members,
        live_as_of=live_as_of,
        # Provenance follows the data: when a source was unreachable this
        # round, the extension still contains what that source contributed
        # last time, so it must still be named.
        sources=tuple(
            source
            for source in (
                upstream.source_url if upstream is not None else None,
                spy.source if spy is not None else None,
                wikipedia.source if wikipedia is not None else None,
            )
            if source
        )
        or (previous.sources if previous is not None else ()),
    )
    return RefreshOutcome(
        extension=extension,
        warnings=tuple(warnings),
        coverage_end=coverage_end,
        n_dated_events=len(forward_events),
        n_live_dated_additions=len(dated_additions),
        live_as_of=live_as_of,
    )


def _date_post_coverage_additions(
    *,
    live_members: frozenset[str],
    reconstructed: set[str],
    added_dates: dict[str, date],
    coverage_end: date,
    today: date,
) -> tuple[tuple[tuple[date, tuple[str, ...], tuple[str, ...]], ...], dict[str, date], list[str]]:
    """Tickers that are in the live index but not yet in the dated data.
    Only those the Wikipedia mirror can date EXACTLY, and only forward of
    coverage, become events; a ticker whose "Date added" predates coverage
    is a successor/rename of a company that was already a member, so it
    gets an earliest-membership override (which is silent until upstream
    supplies the real event) rather than an invented addition date."""
    by_date: dict[date, list[str]] = {}
    overrides: dict[str, date] = {}
    warnings: list[str] = []
    undatable: list[str] = []
    for ticker in sorted(live_members - reconstructed):
        added = added_dates.get(ticker)
        if added is None:
            undatable.append(ticker)
        elif added > coverage_end:
            if added > today:
                undatable.append(ticker)
            else:
                by_date.setdefault(added, []).append(ticker)
        else:
            overrides[ticker] = added
    if undatable:
        warnings.append(
            f"{len(undatable)} live S&P 500 member(s) ({', '.join(undatable[:10])}) joined after "
            f"{coverage_end.isoformat()} but carry no usable addition date; left undated rather than "
            f"dated by guesswork, so no membership is claimed for them yet."
        )
    events = tuple((when, tuple(sorted(tickers)), ()) for when, tickers in sorted(by_date.items()))
    return events, overrides, warnings


# --- Orchestration --------------------------------------------------------


def refresh_membership_data(*, timeout: float = 30.0, today: date | None = None) -> RefreshOutcome:
    """One full refresh: fetch what is reachable, decide, and apply. Never
    raises for a data or network problem — a failed or rejected refresh
    leaves the previously applied data (vendored-only, or the last good
    extension) exactly as it was, which is the entire point of returning
    an outcome rather than mutating state on the way through."""
    as_of_today = today or date.today()
    fetch_warnings: list[str] = []
    upstream: UpstreamHistory | None = None
    spy: LiveConstituents | None = None
    wikipedia: LiveConstituents | None = None

    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for label, fetch in (
            ("point-in-time history", lambda: fetch_upstream_history(client)),
            ("SPY holdings", lambda: fetch_spy_constituents(client)),
            ("Wikipedia constituents", lambda: fetch_wikipedia_constituents(client, today=as_of_today)),
        ):
            try:
                result = fetch()
            except MembershipRefreshError as exc:
                fetch_warnings.append(f"{label} unavailable: {exc}")
                continue
            except Exception as exc:  # a parser bug must not take the runner down
                fetch_warnings.append(f"{label} failed unexpectedly: {exc!r}")
                logger.exception("S&P 500 membership refresh: %s failed unexpectedly.", label)
                continue
            if isinstance(result, UpstreamHistory):
                upstream = result
            elif label == "SPY holdings":
                spy = result
            else:
                wikipedia = result

    outcome = plan_refresh(
        upstream=upstream,
        spy=spy,
        wikipedia=wikipedia,
        today=as_of_today,
        previous=get_membership_extension(),
        fetch_warnings=tuple(fetch_warnings),
    )
    for warning in outcome.warnings:
        logger.warning("S&P 500 membership refresh: %s", warning)
    if outcome.extension is not None:
        apply_membership_extension(outcome.extension)
        logger.info(
            "S&P 500 membership refreshed: dated coverage now %s (%d dated event(s) beyond the "
            "vendored window, %d live-dated addition(s), live constituents as of %s).",
            outcome.coverage_end.isoformat(),
            outcome.n_dated_events,
            outcome.n_live_dated_additions,
            outcome.live_as_of.isoformat() if outcome.live_as_of else "n/a",
        )
    else:
        logger.warning(
            "S&P 500 membership refresh applied nothing; still using the last known-good data "
            "(dated coverage through %s).",
            outcome.coverage_end.isoformat(),
        )
    return outcome


__all__ = [
    "LIVE_MEMBERSHIP_MAX_AGE_DAYS",
    "LiveConstituents",
    "MembershipRefreshError",
    "RefreshOutcome",
    "UpstreamHistory",
    "derive_events",
    "fetch_spy_constituents",
    "fetch_upstream_history",
    "fetch_wikipedia_constituents",
    "plan_refresh",
    "refresh_membership_data",
]
