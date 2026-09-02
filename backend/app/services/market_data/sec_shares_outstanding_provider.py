"""POINT-IN-TIME SHARES OUTSTANDING from SEC's XBRL *frames* API — the
denominator the Boehmer/Huszar/Jordan short-interest ratio needs, fetched in
~37 requests instead of ~600.

WHY A SECOND SHARE-COUNT SOURCE EXISTS AT ALL, given this project already
has two. Both existing ones are per-ticker and neither fits here:

 * YFinanceProvider.get_shares_outstanding loops ONE network call per
   ticker (its own docstring: "Not cheap for a wide universe"), and its
   coverage before 2018 is documented in cross_sectional_buyback.py as "a
   drought (median 4 observations per ticker for the whole year)". A
   full-universe fetch over ~690 names was also measured FLAKY during this
   build (2026-09-02): a batch price fetch returned nothing at all for BK,
   CMA, MMC, K and HOLX, all live large caps, and they stayed empty on
   individual retries after a 90-second cooldown.
 * EdgarXbrlProvider.get_company_facts is one multi-megabyte companyfacts
   document per CIK — the right tool when a family needs many line items
   for a sampled 200 names, the wrong one when it needs a single scalar for
   the whole index.

The FRAMES endpoint inverts the axis: one request returns ONE concept for
ONE period across EVERY filer that reported it.

    https://data.sec.gov/api/xbrl/frames/dei/
        EntityCommonStockSharesOutstanding/shares/CY<YYYY>Q<Q>I.json

Verified live 2026-09-02: CY2020Q1I is 630,911 bytes and carries 4,774
companies. Thirty-seven such frames (2017Q3..2026Q3) cover this project's
entire point-in-time S&P 500 union universe at ~470-520 names per quarter.

=======================================================================
THE POINT-IN-TIME PROBLEM, AND ITS MEASURED — NOT ASSUMED — ANSWER
=======================================================================

A frames record carries `end` (the date the share count is AS OF) and
`accn`, but NOT `filed`. Verified by reading a real response:

    {"accn": "0001104659-20-037857", "cik": 1750,
     "entityName": "AAR CORP.", "loc": "US-IL",
     "end": "2020-02-29", "val": 35100696}

So the date a value became PUBLIC is not in the payload, and using `end` as
if it were would be a look-ahead of exactly the kind this project's
point-in-time discipline exists to rule out.

RATHER THAN GUESS A LAG, THIS BUILD MEASURED THE REAL ONE. The `filed`
field IS present in the per-company companyfacts documents, and this
project already has 163 of them cached from the sibling quality families.
Extracting every dei:EntityCommonStockSharesOutstanding fact from the 115
of those that carry the tag gives 7,539 real (end, filed) pairs:

    end -> filed gap, calendar days
        min   -6      (a cover count dated slightly AFTER the filing)
        p50    8
        p95   35
        p99   73
        max  744      (a late or amended filing)
    2.07% of observations exceed 45 days
   10.82% of observations exceed 30 days

VISIBILITY_LAG_DAYS = 90 is set from that measured distribution: it
dominates the 99th percentile (73 days) with margin, and it dominates every
statutory deadline that could apply to an S&P 500 constituent (a large
accelerated filer's 10-K is due 60 days after fiscal year end, its 10-Q 40
days after quarter end).

WHAT IT DOES NOT DO, STATED PLAINLY: it does not achieve 100%. Roughly 0.5%
of real filings — late filings and amendments — took longer than 90 days
from their `end` date to reach EDGAR, and for those this panel would admit
a count some days before the public had it. Three things bound the damage,
and they are the reason this is disclosed rather than treated as
disqualifying:

 (1) The affected quantity is a slowly-moving DENOMINATOR. A share count
     changes by well under 1% in a typical quarter, so seeing next
     quarter's count early instead of this quarter's perturbs the ranking
     variable by a fraction of a percent, not by a sign.
 (2) The NUMERATOR — FINRA short interest — carries all the fast variation
     and is exactly point-in-time by construction (see
     finra_short_interest_provider.py section 3).
 (3) A late filer is late for reasons uncorrelated with the short-interest
     cross-section, so the residual is noise, not a directional bias
     toward the leg being tested.

THE LAG IS APPLIED TO `end`, AND STALENESS IS BOUNDED SEPARATELY. A count
is forward-filled as a STEP series from `end` + VISIBILITY_LAG_DAYS and is
refused (NaN) once carried further than MAX_STALENESS_DAYS — never
interpolated, never back-filled, never extrapolated. This is the same
contract cross_sectional_buyback.build_point_in_time_share_counts keeps for
its own source, and MAX_STALENESS_DAYS is imported from that module rather
than re-derived, so the two sources cannot silently drift apart.

=======================================================================
COVERAGE, MEASURED
=======================================================================

Against this project's 691-name point-in-time S&P 500 union universe over
2017-12-29..2026-09-02, using SEC's current-day company_tickers.json map:

    583 of 691 tickers resolve a CIK at all (108 are departed members whose
        symbols died — the SAME known limit EdgarXbrlProvider's docstring
        records, not a new defect introduced here)
    532 of those 583 have at least one share-count observation
    median 34 quarterly observations per covered ticker

The Q4 frames are systematically thinner (~330-415 of our names against
~470-520 in Q1-Q3) for a benign reason: most 10-K cover pages are dated in
the FOLLOWING calendar quarter, so a December fiscal-year-end company's
annual count lands in the Q1 frame. Forward-filling across the gap is the
correct treatment and is what this module does.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

SEC_FRAMES_URL = (
    "https://data.sec.gov/api/xbrl/frames/dei/"
    "EntityCommonStockSharesOutstanding/shares/CY{year}Q{quarter}I.json"
)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "sec_shares_outstanding"

# See the module docstring's measured (end -> filed) distribution. Dominates
# its 99th percentile (73 days) and every statutory deadline an S&P 500
# constituent files under.
VISIBILITY_LAG_DAYS = 90

# --- the two share-count plausibility guards --------------------------------
#
# BOTH ARE NECESSARY; NEITHER IS SUFFICIENT. Found by inspecting the real
# distribution over this project's 691-name universe (16,645 records) after a
# first production run emitted a short-interest RATIO of 32,050,932 — a
# quantity that is mathematically confined to roughly [0, 1].
#
# TWO INDEPENDENT CORRUPTION MODES EXIST IN dei:EntityCommonStockSharesOutstanding:
#
#  (1) SHELL / PRE-DISTRIBUTION REGISTRATIONS. A newly-registered entity files
#      a cover page before its real share distribution, reporting a token
#      count. Real cases in this universe, every one an S&P 500 constituent:
#      FOXA 2019-03-18 = 1 share, CTVA 2019-03-31 = 100, SW 2024-06-06 = 100,
#      VTRS 2020-05-06 = 100, PSKY = 1,000, AMCR = 13,001, LIN = 25,000,
#      CMG 2022-04-25 = 27,962, RMD = 145,681, BALL 2022-02-14 = 0.
#      These make the RATIO explode, driving the name to the short leg.
#
#  (2) SCALE / UNITS ERRORS. AJG 2020-06-30 reports 191,469,000,000,000 shares
#      against its own median of 210,588,000 — off by a factor of ~10^6.
#      GRMN 2018 reports 198,077,418,000 against a median of 192,369,290.
#      Also CCL (932bn) and PKG (89.9bn). These make the ratio ~0, driving the
#      name to the LONG leg — which is precisely the leg this family tests,
#      and is therefore the more dangerous of the two modes.
#
# WHY A FLOOR AND A SCALE BREAK RATHER THAN EITHER ALONE:
#  * The scale break is measured against the TICKER'S OWN MEDIAN, so it cannot
#    see a ticker whose ENTIRE history is one corrupt record. FOXA has exactly
#    one observation, the value 1, so its median is 1 and nothing looks
#    anomalous. Only the absolute floor catches it.
#  * The floor cannot catch AJG: 191 trillion is above any floor.
#
# CALIBRATION, and the reason SHARES_SCALE_BREAK_RATIO is not a tuned
# parameter. Sweeping the threshold over the real data, 50x, 100x and 500x
# refuse the IDENTICAL 19 records — a wide plateau, because the corruptions are
# 10^3 to 10^6 off while every legitimate move is under 20x. At 20x the guard
# starts firing on AMZN, whose 2022 20-for-1 split is a real 20x change, so the
# plateau's lower edge is set by real splits and 100x sits in its middle.
# Verified to KEEP the two hardest legitimate cases: NVR (~2.7-3.7M shares, the
# lowest real share count in the S&P 500) and NVDA (~24.5bn after its 10-for-1
# split). Together the guards refuse 22 of 16,645 records — 0.13%.
#
# This is the direct analogue of cross_sectional_quality's
# ASSETS_SCALE_BREAK_RATIO, which exists for the same reason on a different
# line item: a shell-to-operating-company transition makes two filings
# incomparable.
SHARES_MIN_PLAUSIBLE = 1_000_000.0
SHARES_SCALE_BREAK_RATIO = 100.0

# The earliest frame worth requesting for a panel that starts at FINRA's own
# first available cycle (2017-12-29): one quarter of warm-up before it, so
# the first formation already has a filled step value rather than a NaN.
EARLIEST_FRAME = (2017, 3)

SEC_RETRY_ATTEMPTS = 3
SEC_RETRY_BASE_DELAY_SECONDS = 1.0

# SEC's fair-access policy asks for a declared User-Agent and no more than
# 10 requests/second. This module makes ~37 requests total, so the pause
# below is courtesy rather than a binding constraint.
DEFAULT_USER_AGENT = "aladdin2-research/1.0 (autoa0792@gmail.com)"
INTER_REQUEST_SLEEP_SECONDS = 0.15


class SecSharesFetchError(RuntimeError):
    """A frame could not be retrieved after every retry."""


@dataclass
class ShareCountDiagnostics:
    """Measured coverage, never assumed. Read alongside any run that uses
    the panel this module builds."""

    n_frames_requested: int = 0
    n_frames_resolved: int = 0
    n_observations: int = 0
    tickers_without_cik: list[str] = field(default_factory=list)
    tickers_without_share_count: list[str] = field(default_factory=list)
    n_refused: dict[str, int] = field(default_factory=dict)
    # Every record the plausibility guards threw away, named: (ticker, as_of,
    # value). Deliberately the full list rather than a count — there are ~20 of
    # them across the whole universe, each is a real corporate event worth
    # eyeballing, and a guard whose firings cannot be inspected is a guard
    # nobody can audit.
    refused_records: list[tuple[str, date, float]] = field(default_factory=list)

    def refuse(self, reason: str) -> None:
        self.n_refused[reason] = self.n_refused.get(reason, 0) + 1


@dataclass(frozen=True)
class ShareCountObservation:
    """One filer's common-share count as of one date, plus the date a
    backtest may first read it."""

    as_of: date
    available: date
    shares: float


def quarterly_frames(start: date, end: date) -> list[tuple[int, int]]:
    """The (year, quarter) instantaneous frames spanning [start, end], never
    earlier than EARLIEST_FRAME."""
    frames: list[tuple[int, int]] = []
    year, quarter = max((start.year, (start.month - 1) // 3 + 1), EARLIEST_FRAME)
    last = (end.year, (end.month - 1) // 3 + 1)
    while (year, quarter) <= last:
        frames.append((year, quarter))
        year, quarter = (year + 1, 1) if quarter == 4 else (year, quarter + 1)
    return frames


class SecSharesOutstandingProvider:
    """Fetches, caches and reshapes SEC's dei:EntityCommonStockSharesOutstanding
    frames into per-ticker point-in-time observations.

    A completed calendar quarter's frame is effectively immutable (a later
    amendment can add a filer, but the endpoint is not rewritten in place),
    so the cache needs no age bound for a backward-looking research run. A
    LIVE consumer wanting the current quarter must delete that quarter's
    cache file — the same explicit contract EdgarXbrlProvider states for its
    own growing documents.
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

    def _cache_path(self, year: int, quarter: int) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"CY{year}Q{quarter}I.json"

    @staticmethod
    def _write_cache_atomically(cache_path: Path, payload: str) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=cache_path.parent, suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(payload)
            os.replace(tmp_path, cache_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def fetch_frame(self, year: int, quarter: int) -> dict:
        """One quarter's frame, cached. Raises SecSharesFetchError after
        every retry — a frame that silently came back empty would look
        exactly like "no company filed that quarter"."""
        cache_path = self._cache_path(year, quarter)
        if cache_path is not None and cache_path.exists():
            return json.loads(cache_path.read_text())

        url = SEC_FRAMES_URL.format(year=year, quarter=quarter)
        last_error: Exception | None = None
        for attempt in range(1, SEC_RETRY_ATTEMPTS + 1):
            try:
                response = self._session.get(url, timeout=90)
                response.raise_for_status()
                payload = response.json()
                if "data" not in payload:
                    raise SecSharesFetchError(f"{url} returned no 'data' key")
                if cache_path is not None:
                    self._write_cache_atomically(cache_path, json.dumps(payload))
                self._sleep(INTER_REQUEST_SLEEP_SECONDS)
                return payload
            except Exception as error:  # noqa: BLE001 — retried, then re-raised
                last_error = error
                if attempt < SEC_RETRY_ATTEMPTS:
                    self._sleep(SEC_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        raise SecSharesFetchError(
            f"failed after {SEC_RETRY_ATTEMPTS} attempts: {url}"
        ) from last_error

    def fetch_share_counts(
        self,
        ticker_to_cik: dict[str, int],
        start: date,
        end: date,
        *,
        missing_from_map: Iterable[str] = (),
    ) -> tuple[dict[str, list[ShareCountObservation]], ShareCountDiagnostics]:
        """(ticker -> chronological share-count observations, diagnostics).

        REFUSALS, all counted:
         * `non_positive_shares` — a zero, negative or non-finite count. This
           is the DENOMINATOR of a short-interest ratio; a zero there would
           produce an infinity that ranks first in the cross-section.
         * `unparseable_record` — a malformed `end` or `val`.

        Where one CIK reports the same `end` twice across frames (a share
        class split across records, or an amendment), the LAST value read
        wins, matching YFinanceProvider.get_shares_outstanding's documented
        keep-last de-duplication for the same situation."""
        diagnostics = ShareCountDiagnostics()
        diagnostics.tickers_without_cik = sorted(missing_from_map)
        cik_to_ticker = {cik: ticker for ticker, cik in ticker_to_cik.items()}
        by_ticker: dict[str, dict[date, float]] = {}

        frames = quarterly_frames(start, end)
        diagnostics.n_frames_requested = len(frames)
        for year, quarter in frames:
            payload = self.fetch_frame(year, quarter)
            diagnostics.n_frames_resolved += 1
            for record in payload.get("data", []):
                ticker = cik_to_ticker.get(record.get("cik"))
                if ticker is None:
                    continue
                try:
                    as_of = date.fromisoformat(record["end"])
                    shares = float(record["val"])
                except (KeyError, TypeError, ValueError):
                    diagnostics.refuse("unparseable_record")
                    continue
                if not np.isfinite(shares) or shares <= 0.0:
                    diagnostics.refuse("non_positive_shares")
                    continue
                by_ticker.setdefault(ticker, {})[as_of] = shares

        out: dict[str, list[ShareCountObservation]] = {}
        for ticker in ticker_to_cik:
            values = by_ticker.get(ticker, {})
            if not values:
                diagnostics.tickers_without_share_count.append(ticker)
                out[ticker] = []
                continue

            # THE TWO PLAUSIBILITY GUARDS (see their constants above). Applied
            # HERE, after a ticker's whole history is assembled, because the
            # scale-break guard is defined against the ticker's own median and
            # cannot be evaluated one record at a time.
            plausible = [shares for shares in values.values() if shares >= SHARES_MIN_PLAUSIBLE]
            median = float(np.median(plausible)) if plausible else float("nan")

            kept: list[ShareCountObservation] = []
            for as_of, shares in sorted(values.items()):
                if shares < SHARES_MIN_PLAUSIBLE:
                    diagnostics.refuse("below_plausible_share_floor")
                    diagnostics.refused_records.append((ticker, as_of, shares))
                    continue
                if np.isfinite(median) and median > 0.0 and (
                    shares > median * SHARES_SCALE_BREAK_RATIO
                    or shares * SHARES_SCALE_BREAK_RATIO < median
                ):
                    diagnostics.refuse("share_count_scale_break")
                    diagnostics.refused_records.append((ticker, as_of, shares))
                    continue
                kept.append(
                    ShareCountObservation(
                        as_of=as_of,
                        available=as_of + timedelta(days=VISIBILITY_LAG_DAYS),
                        shares=shares,
                    )
                )

            out[ticker] = kept
            if not kept:
                diagnostics.tickers_without_share_count.append(ticker)
            diagnostics.n_observations += len(kept)
        diagnostics.tickers_without_share_count.sort()
        return out, diagnostics


def build_point_in_time_share_count_frame(
    close: pd.DataFrame,
    observations: dict[str, list[ShareCountObservation]],
    *,
    max_staleness_days: int,
) -> tuple[pd.DataFrame, list[str]]:
    """The forward-filled STEP panel of share counts, aligned to `close`'s
    exact trading-day index and column order.

    Returns (frame, tickers_with_no_usable_count).

    THE STEP FUNCTION IS THE DATA, not an artifact to be smoothed — the same
    rule CrossSectionalData.shares_outstanding states. Each value appears
    from its own `available` date (as_of + VISIBILITY_LAG_DAYS) and is
    carried forward unchanged until the next one supersedes it, then refused
    (NaN) once carried further than `max_staleness_days`. No interpolation,
    no back-fill: a date before a ticker's first visible count is NaN, and a
    date long after its last is NaN too, which is the correct answer for a
    company whose share count this project cannot observe there.

    The fill runs over the union of the availability dates and `close`'s
    index so a count becoming visible on a non-trading day still propagates
    from its own date, and is then read back on `close`'s dates alone."""
    empty = pd.Series(np.nan, index=close.index, dtype=float)
    columns: dict[str, pd.Series] = {}
    unusable: list[str] = []

    for ticker in close.columns:
        records = observations.get(ticker) or []
        points = {
            pd.Timestamp(record.available): record.shares
            for record in sorted(records, key=lambda r: r.available)
        }
        if not points:
            unusable.append(ticker)
            columns[ticker] = empty.copy()
            continue

        sparse = pd.Series(points).sort_index()
        union = sparse.index.union(close.index)
        filled = sparse.reindex(union).ffill()
        ages = pd.Series(union, index=union).sub(
            pd.Series(sparse.index, index=sparse.index).reindex(union).ffill()
        )
        fresh = filled.where(ages <= pd.Timedelta(days=max_staleness_days))
        columns[ticker] = fresh.reindex(close.index).astype(float)

    frame = pd.DataFrame(columns, index=close.index).reindex(columns=close.columns)
    return frame, unusable


__all__ = [
    "DEFAULT_CACHE_DIR",
    "EARLIEST_FRAME",
    "SEC_FRAMES_URL",
    "SecSharesFetchError",
    "SecSharesOutstandingProvider",
    "ShareCountDiagnostics",
    "ShareCountObservation",
    "VISIBILITY_LAG_DAYS",
    "build_point_in_time_share_count_frame",
    "quarterly_frames",
]
