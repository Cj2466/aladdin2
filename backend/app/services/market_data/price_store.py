"""POINT-IN-TIME PRICE STORE — raw (as-traded) OHLCV plus corporate actions,
recorded once and never re-asked, with every adjusted series computed
deterministically from that stored copy.

=======================================================================
1. THE BUG THIS EXISTS TO FIX, MEASURED RATHER THAN ASSUMED
=======================================================================

YFinanceProvider.get_price_history / get_daily_ohlcv used to call
`yf.download(..., auto_adjust=True)` on every invocation with no persistence.
`auto_adjust=True` does not return a fixed historical record: it back-adjusts
the ENTIRE returned series for every split and cash distribution Yahoo
currently knows about, and that knowledge keeps changing. A newly-processed
dividend shifts the adjustment factor for every date on or before its
ex-date, retroactively, on the very next live fetch.

Measured directly (2026-09-04, this project's own 768-ticker S&P universe
over 2015-01-07..2026-08-31): two identical fetches ~5.5 hours apart, zero
code changes, moved 2.9% of all (date, ticker) Close cells by more than 1bp.
Several names had their rescale boundary fall INSIDE the backtest window,
which manufactures or erases a single day's pct_change() return purely as an
artifact of when the fetch happened to run. Isolating that one input moved
cross_sectional_lazy_prices's registered spec's Sharpe by +0.0205 — the same
order of magnitude as that family's whole unexplained reproduction drift.

This is a documented, vendor-side property, not a local misuse. yfinance's
own Price-repair wiki page states that Yahoo data carries "a variety of price
errors" including "missing dividend adjustments" and "missing split
adjustments", and warns that "If Yahoo eventually does fix the bad data that
required reconstruction, you will see it's slightly different" — i.e. the
upstream series is explicitly expected to change under you over time
(github.com/ranaroussi/yfinance/wiki/Price-repair, fetched 2026-09-04).

=======================================================================
2. THE ARCHITECTURE, AND ITS PRIMARY SOURCE
=======================================================================

The fix is the one point-in-time research databases have used for decades:
STORE RAW, ADJUST YOURSELF. CRSP's own Data Description Guide, Chapter 5
"CRSP Calculations", p.117, states it directly (quoted verbatim):

    "Price, dividend, shares, and volume data are historically adjusted for
     split events to make data directly comparable at different times during
     the history of a security. CRSP provides raw, Unadjusted Data, but data
     utilities stk_print and ts_print can be used to generate Adjusted Data."

    "An adjustment base date is chosen as the anchor date. All data on this
     date are unadjusted, and other data are converted based on the split
     events between the base date and the time of that data. The adjustment
     base date is usually the last available day of trading."

    "Price and dividend data are adjusted with the calculation:
         A(t) = P(t) / C(t)
     where A(t) is the adjusted value at time t, P(t) is the raw value at
     time t, and C(t) is the cumulative adjustment factor at time t."

    "if t=C0, C(t) = 1.0
     if t>C0 and no split events since t-1, C(t) = C(t-1)
     if t>C0 and a split event with factor f since t-1, C(t) = C(t-1) * f"

and, for total return, p.119:

    "Total Return = (adjprc + (divamt / cumfacpr / facpr)) / prev_adjprc - 1"

(Source: CRSP Data Description Guide, Chapter 5, distributed as
crsp_calculations_splits.pdf; retrieved 2026-09-04 from
leiq.bus.umich.edu/docs/crsp_calculations_splits.pdf.)

Two facts make this the right shape here, not merely a prestigious one:

  * A RAW price is a PERMANENT FACT. "AAPL last traded at 499.23 on
    2020-08-28" does not become false when Apple later pays a dividend. An
    ADJUSTED price is a DERIVED OPINION whose value depends on everything
    that has happened since — which is exactly why re-asking the vendor for
    it gives a different answer each time.
  * Adjustment is a SHORT, TOTALLY DETERMINISTIC COMPUTATION over (raw
    prices, splits, distributions). Owning it means it can be unit-tested
    against known historical events, and means the boundary placement that
    fabricated returns above is decided by this module's code rather than by
    a vendor's shifting internal state.

Considered and rejected, for this project's actual constraints (free tier,
yfinance-only, no CRSP/Compustat licence):

  * "Freeze the adjusted series to disk" — the shape of the earlier opt-in
    snapshot fix (commit 24f0974). It works, but it freezes a DERIVED
    OPINION: the frozen file cannot absorb a new trading day without
    splicing a differently-based series onto it, which is the exact
    boundary artifact being fixed. Storing raw is basis-invariant and
    therefore extensible.
  * "Pin a vendor version / use as-of queries" — Yahoo exposes no version
    or as-of parameter. Not available at any price on this feed.
  * "Switch vendors" — every free vendor reachable here (Yahoo, Stooq,
    Alpaca's free tier) serves a continuously-revised adjusted series with
    no as-of facility. Changing vendor changes whose revisions bite, not
    whether they bite.

=======================================================================
3. WHAT "RAW" MEANS HERE, AND THE ONE PLACE YAHOO FORCES A COMPROMISE
=======================================================================

Yahoo does not serve a genuinely unadjusted price. Verified live
2026-09-04: `yf.download(auto_adjust=False)`'s `Close` for AAPL on
2020-08-28 is 124.8075, not the 499.23 that actually traded that day — i.e.
Yahoo's `Close` is ALREADY split-adjusted onto today's share basis (it is
only the DIVIDEND adjustment that `auto_adjust=False` withholds).

That basis is not stable: it is re-expressed every time the security splits
again. Storing it as-fetched would therefore reintroduce the same defect one
level down — a chunk fetched after a new split would splice onto the store at
half scale.

So this module UN-SPLIT-ADJUSTS on the way in, restoring the as-traded price:

    raw(t) = yahoo_close(t) * product(f_i for every split ex-date_i > t)

using the split ratios that ride along in the same download. That value is
basis-invariant: no future corporate action can change what a share actually
cost on a past date, so a row, once written, is never wrong for the reason
this module exists. Verified against the independently-known fact that AAPL
closed at 499.23 on 2020-08-28 before its 4-for-1 split (see
tests/test_price_store.py::test_apple_2020_split_reconstructs_the_real_traded_price).

Dividend amounts are stored on the same as-traded basis, for the same reason
and by the same factor.

=======================================================================
4. IMMUTABILITY POLICY — FIRST WRITE WINS, REVISIONS ARE REPORTED
=======================================================================

A (ticker, date) row, once stored, is NEVER overwritten by a later fetch.
That is what makes a fixed historical window reproduce: the inputs to the
adjustment cannot move under a rerun.

A later fetch that disagrees with a stored row is not silently discarded
either — it is COUNTED and SURFACED on PriceStoreReport.revisions, so a
genuine upstream correction is visible rather than invisible. This is the
deliberate trade CRSP makes with versioned data releases and researchers make
by pinning a version: reproducibility is worth more than always-latest, but
only if the divergence is observable. `resync_ticker` is the explicit,
never-automatic escape hatch for adopting a correction on purpose.

=======================================================================
5. THE ADJUSTMENT CONVENTIONS, AND WHY THE DEFAULT IS THE ONE IT IS
=======================================================================

Two total-return conventions are implemented, both deterministic functions of
the stored rows. They differ only in how a distribution enters the chained
daily return across its ex-date:

  AdjustmentConvention.CRSP   r(t) = (P(t) + D(t)) / P(t-1) - 1   <- DEFAULT
  AdjustmentConvention.YAHOO  r(t) = P(t) / (P(t-1) - D(t)) - 1

CRSP is the definition quoted in section 2 and the one every academic paper
these families replicate uses; for the 99.96% of distribution events that do
not coincide with a split it is simply the arithmetic definition of what a
buy-and-hold holder earned, so it cannot be subtly wrong. YAHOO is what
`auto_adjust=True` actually computes (measured at 1.70 million universe cells
by the rollout that introduced this store, max relative difference 1.4e-06;
independently re-checked 2026-09-04 on five distribution-heavy names over the
full window, max daily-return difference 9.1e-07 with zero cells above 1e-06,
and on four large special distributions to within 2.7e-07) and is kept
selectable so a pre-2026-09-04 number can still be reproduced deliberately.

THE DEFAULT WAS YAHOO UNTIL 2026-09-04 AND IS NOW CRSP. It was originally left
at YAHOO so that introducing this store was provably numerics-neutral; that
job is done (the rollout it enabled found zero verdict changes), and the flip
was then reviewed on its own evidence. See
data/research_runs/dividend_convention_2026-09-04.txt for the full decision
record and its .json companion for every per-family measurement.

WHY YAHOO'S IS WRONG, IN CLOSED FORM. Writing k = D(t)/P(t-1),

    1 + r_YAHOO = (P(t)/P(t-1)) / (1-k)
    1 + r_CRSP  =  P(t)/P(t-1)  + k
  =>  r_YAHOO = r_CRSP / (1 - k)     exactly

Yahoo's convention does not shift the level; it MULTIPLIES the day's true
total return by 1/(1 - D/P). It is a leverage applied on ex-dates only, in
proportion to the distribution's size. Measured on all 144 ordinary
distributions above 5% of price in this project's two point-in-time
universes: the sign of the error equals the sign of the true return on every
one of the 143 that HAS a sign (78 positive returns all overstated, 65
negative returns all made more negative; the 144th had an exactly-zero true
return and is untouched, as the closed form requires); median |error|
0.1498%, p90 0.9513%, max 9.6078%. The worst:

    KDP 2018-07-10, the Keurig/Dr Pepper Snapple merger consideration.
    Close 123.66 -> 22.19 against a $103.75 special cash distribution, with
    the share retained 1:1 (KDP press release 2018-06-26; SEC 8-K,
    CIK 0001418135, accession 0001104659-18-044357).
    True total return    (22.19 + 103.75) / 123.66 - 1 = +1.84%
    Yahoo's convention   22.19 / (123.66 - 103.75) - 1 = +11.45%
    -- the true return amplified 1/(1-0.839) = 6.21x.

Aggregated over 2015-2026 the effect is small: the median name's cumulative
wealth is unchanged to six decimal places, p5 -0.234% and p95 +0.189%. That
is why this was a considered change and not an emergency; it is not why a
known leverage on ex-dates should be kept.

SAME-DAY SPLIT + DISTRIBUTION EVENTS ARE **NOT** SPECIAL-CASED BY DEFAULT,
AND THAT IS A DELIBERATE REVERSAL. `drop_same_day_split_distributions` exists
because Yahoo sometimes encodes ONE spin-off as BOTH a split ratio and a
distribution, so adding the distribution to an already-rescaled price counts
it twice. Until 2026-09-04 the CRSP convention switched that rule ON, on the
stated basis that "only 3 such events exist in this project's universe (DHR /
Fortive, DXC / CSRA, XRX / Conduent) and all three are real spin-offs."

BOTH HALVES OF THAT WERE WRONG. A full scan of both point-in-time universes
(1,423 priced names, 38,153 distributions, 347 splits) finds SIX tickers and
FIFTEEN events -- the three above plus RILY 2016-11-25, SSP 2015-04-01 and
TR every March 2015-2026 -- and the rule is correct for only TWO of the
fifteen:

  * TR (Tootsie Roll) declares a regular quarterly CASH dividend of
    $0.08-0.09 AND, separately, an annual 3% STOCK dividend, on the same
    ex-date, every March. The 1.03 ratio is the stock dividend; the cash is a
    second, real distribution. Dropping it is wrong ten times over -- and the
    KEPT arm is EXACT there: a holder of 1 share at 33.24 on 2015-03-05 had
    1.03 shares at 31.45 plus 1.03*0.078 cash the next day, -2.3049%, which
    is what the shipped default returns (the drop arm returns -2.5466%).
  * DXC's 2015-11-30 event carried BOTH one CSRA share per CSC share AND a
    genuinely separate $10.50/share special cash distribution ($2.25 from
    CSC, $8.25 from CSRA -- SEC 8-K, CIK 0000023082, accession
    0000023082-15-000078). Dropping the cash turns a roughly flat day into
    -20.50%.
  * SSP 2015-04-01: Scripps holders received "a special one-time cash
    dividend of $1.0297 per share AND .25 share in Journal Media Group"
    (Scripps press release). RILY 2016-11-25: "$0.08 per share regular cash
    dividend ... and a one-time special dividend of $0.17 per share" (SEC
    8-K, CIK 0001464790), which is exactly the $0.25 recorded. Both are
    confirmed cash, both would be discarded.
  * Only DHR (drop gives +3.64% against a true +2.33%, computed from FTV's
    own first close of 48.60 at 0.5 per DHR share) and XRX are genuine
    double-encodings, and even XRX is 9.5pp out under the drop rule because
    Yahoo's 1.518 ratio comes from Conduent's when-issued $14.90 rather than
    the $13.72 that traded.

Telling the two cases apart needs to know whether a "split" is a share-count
change or a price factor, and whether the recorded cash is the same value
again or a separate payment. Yahoo's feed carries neither distinction. So no
blind rule is applied: the flag stays available as an explicit opt-in,
defaults to False under BOTH conventions, and the six affected names keep
exactly the treatment every already-recorded number in this project ran on.
Their residual known-bad single-day returns are listed in the decision record
rather than "fixed" in the wrong direction.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Cache layout: data/price_store/v1/<TICKER>.csv.gz, one file per ticker,
# mirroring edgar_filing_text's one-file-per-filing shape for the same
# reasons: an incremental append touches only the tickers it fetched, and a
# partial-universe run never rewrites a whole-universe blob.
#
# The "v1" segment versions THE STORED REPRESENTATION (the as-traded
# normalisation of section 3). Changing what `close` means on disk must bump
# it rather than silently serve rows the current reader would not have
# written.
STORE_SCHEMA_VERSION = "v1"
DEFAULT_STORE_DIR = Path(__file__).resolve().parents[3] / "data" / "price_store" / STORE_SCHEMA_VERSION

# The columns of a stored per-ticker file. `close`/`open`/`high`/`low` and
# `dividend` are AS-TRADED (section 3); `split` is the ratio on its ex-date
# (0.0 on an ordinary day, matching yfinance's own actions encoding);
# `capital_gains` is carried through unused so a later consumer that needs to
# separate it from `dividend` (yfinance issue #2666: Yahoo's Dividends field
# is the sum of ordinary dividends and capital-gain distributions for funds)
# does not need the store rebuilt.
STORE_COLUMNS = ("open", "high", "low", "close", "volume", "dividend", "split", "capital_gains")

# yfinance's actions encoding: an ordinary day carries 0.0 in the split
# column, not NaN and not 1.0. Both 0.0 and 1.0 are no-op ratios and are
# dropped, exactly as YFinanceProvider.get_market_cap_basis already does.
_NON_EVENT_SPLIT_VALUES = (0.0, 1.0)

# A price this small is a feed artifact rather than a market. Rows failing
# this are refused at INGEST rather than stored and filtered later, because
# the whole point of the store is that a stored row is a fact.
MIN_PLAUSIBLE_PRICE = 1e-6

# Two floats are "the same stored value" within this relative tolerance. Set
# at 1e-9 rather than 0.0 because a value round-trips through gzipped CSV on
# the way in and out, and pandas' float repr is exact to ~17 significant
# digits but the un-split-adjustment multiplies by a factor first.
REVISION_RELATIVE_TOLERANCE = 1e-9

# Window-coverage tolerances, defined HERE and imported by price_cache.py so
# the two layers cannot drift apart. Both predate this module (they were
# established by price_cache.get_price_history_cached) and their reasoning is
# unchanged:
#
#  * A rolling window (end >= today) must tolerate today's bar not being
#    published yet, or every such request refetches forever.
#  * ANY window must tolerate a requested `start` that lands on a weekend or
#    holiday — no bar will ever exist exactly on that date, so the earliest
#    real bar is unavoidably a few calendar days later. Without this, the
#    coverage check trips for ~2/7 of all date-derived starts.
ROLLING_WINDOW_TOLERANCE_DAYS = 4
START_DATE_TRADING_CALENDAR_TOLERANCE_DAYS = 4

# Filename of the coverage ledger: per ticker, the merged list of [start, end)
# windows this store has ALREADY ASKED THE VENDOR ABOUT.
#
# COVERAGE IS RECORDED SEPARATELY FROM DATA, and that separation is load-
# bearing rather than bookkeeping. "Do I have every row for this window?"
# cannot be answered from the rows themselves, because the correct answer for
# a huge number of real cases is "yes, and there are none":
#
#   * A delisted name (TWTR after 2022-11, PCP, GAS, SWY, LLTC, ... — ~35 such
#     symbols in this project's own point-in-time universes) has no rows after
#     its death, or none at all. Inferring coverage from the rows would call
#     that "not covered" and refetch it on every single call, forever.
#   * A window whose `end` lands on a weekend, a holiday, or simply after the
#     vendor's last published bar likewise never reaches its own end date.
#
# Both were live defects in the first cut of this module, caught by
# test_get_daily_ohlcv_replays_the_store_without_a_second_network_call.
COVERAGE_NAME = "_coverage.json"


class _Unset:
    """Sentinel distinguishing "caller passed nothing" from "caller passed
    None", which is a meaningful value here (None disables persistence)."""


_UNSET = _Unset()


class AdjustmentConvention(str, Enum):
    """How a distribution enters the chained daily return across its ex-date.

    CRSP is the default since 2026-09-04; YAHOO stays selectable only so a
    number recorded before that date can be reproduced deliberately. See
    section 5 of the module docstring for the closed form that decides it
    (r_YAHOO = r_CRSP / (1 - D/P), i.e. a leverage on ex-dates) and for the
    universe-wide measurement behind the switch."""

    YAHOO = "yahoo"
    CRSP = "crsp"


@dataclass
class PriceStoreReport:
    """What a store interaction actually did — never printed, always
    returnable, so a caller can assert on it and a runner can log it.

    `revisions` is the load-bearing field: it is how a genuine upstream
    correction to an already-stored row becomes visible instead of silently
    discarded by the first-write-wins policy (section 4). Each entry is
    (ticker, date, stored_value, fetched_value) for `close` only — the field
    every downstream number is computed from."""

    tickers_requested: int = 0
    tickers_served_from_store: int = 0
    tickers_fetched: int = 0
    rows_written: int = 0
    rows_already_present: int = 0
    revisions: list[tuple[str, date, float, float]] = field(default_factory=list)
    rejected_rows: int = 0
    missing: list[str] = field(default_factory=list)

    def describe(self) -> str:
        parts = [
            f"{self.tickers_served_from_store}/{self.tickers_requested} tickers served from store",
            f"{self.tickers_fetched} fetched",
            f"{self.rows_written} rows written",
        ]
        if self.revisions:
            parts.append(f"{len(self.revisions)} UPSTREAM REVISIONS held back (see .revisions)")
        if self.rejected_rows:
            parts.append(f"{self.rejected_rows} implausible rows rejected")
        return ", ".join(parts)


def _atomic_write_bytes(path: Path, payload: bytes) -> bool:
    """Publish through a temp file + os.replace so a concurrent reader can
    only ever see a complete file — the same discipline
    FinraShortInterestProvider._write_cache_atomically keeps, and it matters
    here for the same reason: several worktrees share one data directory.

    RETURNS FALSE INSTEAD OF RAISING when the filesystem refuses the write.
    Unlike every other cache in this project, this one now sits in front of
    EVERY daily price read, including a live forward-validation tick — so an
    unwritable or full disk must degrade to "no persistence this run" (which
    is exactly the old pass-through behaviour) rather than fail a request that
    the vendor already answered successfully."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    except OSError:
        logger.warning("price store is not writable at %s; continuing without persistence", path.parent)
        return False
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(tmp_path, path)
        return True
    except OSError:
        logger.warning("price store write failed for %s; continuing without persistence", path)
        return False
    finally:
        tmp_path.unlink(missing_ok=True)


def cumulative_split_factor(splits: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """C(t) of CRSP's section-2 recursion, evaluated over `index` with the
    base date at the LAST row: 1.0 on and after the final date, and
    multiplied by every split ratio whose ex-date is strictly LATER than t.

    `splits` carries yfinance's actions encoding (ratio on the ex-date, 0.0
    on an ordinary day). Both 0.0 and 1.0 are no-op ratios and are ignored.

    Strictly-later is the load-bearing detail. A 4-for-1 split with ex-date D
    means the price ON D is already quoted in the new, quartered units, so D
    itself must NOT be scaled; only D-1 and earlier must. Getting this
    boundary wrong by one row is precisely the single-day fabricated return
    this whole module exists to eliminate, so it is pinned by a test against
    Apple's real 2020-08-31 split."""
    ratios = pd.to_numeric(pd.Series(splits), errors="coerce").reindex(index).fillna(0.0)
    events = ratios[~ratios.isin(_NON_EVENT_SPLIT_VALUES)]
    factor = pd.Series(1.0, index=index, dtype=float)
    if events.empty:
        return factor
    # Reverse-cumulative product of every ratio strictly after each date:
    # shift(-1) drops each date's own ratio out of its own factor, which is
    # what makes the boundary "strictly later" rather than "on or later".
    per_date = ratios.where(~ratios.isin(_NON_EVENT_SPLIT_VALUES), 1.0)
    return per_date.shift(-1).fillna(1.0)[::-1].cumprod()[::-1].astype(float)


class PriceStore:
    """Disk-backed, append-only, immutable-by-(ticker, date) store of
    as-traded OHLCV plus corporate actions.

    `store_dir=None` disables persistence entirely (every call becomes a
    straight pass-through fetch). That is the escape hatch unit tests use so
    they neither touch nor depend on a real data directory — it is NOT a
    supported production mode, because a run with persistence off has exactly
    the reproducibility properties this module was written to remove."""

    def __init__(self, store_dir: Path | str | None | _Unset = _UNSET) -> None:
        # DEFAULT_STORE_DIR is resolved HERE rather than bound as a parameter
        # default, so a test (or a runner pinning an alternate store) can
        # monkeypatch this module's DEFAULT_STORE_DIR and have it take effect
        # — a bound default would capture the import-time value before any
        # patch applies. Same reasoning _call_with_retry's `sleep=None`
        # already uses in yfinance_provider.
        resolved = DEFAULT_STORE_DIR if isinstance(store_dir, _Unset) else store_dir
        self.store_dir = Path(resolved) if resolved is not None else None

    # --- on-disk layer ----------------------------------------------------

    def _path(self, ticker: str) -> Path | None:
        if self.store_dir is None:
            return None
        # Ticker symbols reaching here are vendor symbols (letters, digits,
        # '-', '.', '^', '='); anything else cannot name a file safely.
        safe = "".join(ch if (ch.isalnum() or ch in "-.^=") else "_" for ch in ticker)
        return self.store_dir / f"{safe}.csv.gz"

    def read_ticker(self, ticker: str) -> pd.DataFrame | None:
        """Every stored row for one ticker, or None if it has never been
        stored — the same "absent means build one" contract
        edgar_filing_text_provider.load_filing_index keeps, so a caller can
        branch on None without a try/except."""
        path = self._path(ticker)
        if path is None or not path.exists():
            return None
        frame = pd.read_csv(path, index_col=0, parse_dates=True, compression="gzip")
        frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
        frame.index.name = "date"
        for column in STORE_COLUMNS:
            if column not in frame.columns:
                frame[column] = np.nan
        return frame[list(STORE_COLUMNS)].sort_index()

    def _write_ticker(self, ticker: str, frame: pd.DataFrame) -> pd.DataFrame:
        """Persist `frame` and return WHAT A LATER READ WILL SEE.

        Returning the re-read copy rather than the in-memory one is not
        pedantry — it is what makes the FIRST run of a backtest produce the
        same numbers as every rerun. A float that has been through
        to_csv/read_csv is not always bit-identical to the one that went in
        (the round trip is exact to ~1e-15 relative, not to the last bit), so
        a first run that returned the in-memory frame while every later run
        returned the disk copy would differ from its own reruns in the last
        couple of digits. Measured directly on a live 12-name fetch: runs 2
        and 3 hashed identically and run 1 did not, until this. Now every run
        goes through exactly the same round trip.

        Falls back to the in-memory frame when there is no store directory, or
        when the filesystem refused the write — in both of those cases no
        later read will see anything, so the in-memory copy IS what a caller
        gets."""
        path = self._path(ticker)
        if path is None:
            return frame
        payload = gzip.compress(frame.to_csv().encode("utf-8"))
        if not _atomic_write_bytes(path, payload):
            return frame
        written = self.read_ticker(ticker)
        return frame if written is None else written

    def merge_ticker(self, ticker: str, incoming: pd.DataFrame, report: PriceStoreReport) -> pd.DataFrame:
        """Apply the first-write-wins policy of section 4 and return the
        ticker's complete stored frame afterwards — as a later read will see
        it, see _write_ticker.

        Rows whose date is already stored are DISCARDED, not applied; where
        the discarded row's `close` disagrees with the stored one beyond
        REVISION_RELATIVE_TOLERANCE, the disagreement is appended to
        `report.revisions` so it is observable."""
        incoming = incoming.sort_index()
        existing = self.read_ticker(ticker)
        if existing is None or existing.empty:
            report.rows_written += len(incoming)
            return self._write_ticker(ticker, incoming)

        overlap = incoming.index.intersection(existing.index)
        if len(overlap):
            stored_close = pd.to_numeric(existing.loc[overlap, "close"], errors="coerce")
            fetched_close = pd.to_numeric(incoming.loc[overlap, "close"], errors="coerce")
            denominator = stored_close.abs().where(lambda s: s > 0.0)
            drift = (stored_close - fetched_close).abs() / denominator
            changed = drift[drift > REVISION_RELATIVE_TOLERANCE].dropna()
            for timestamp in changed.index:
                report.revisions.append(
                    (
                        ticker,
                        timestamp.date(),
                        float(stored_close.loc[timestamp]),
                        float(fetched_close.loc[timestamp]),
                    )
                )
            report.rows_already_present += len(overlap)

        fresh = incoming.loc[incoming.index.difference(existing.index)]
        if fresh.empty:
            return existing
        report.rows_written += len(fresh)
        merged = pd.concat([existing, fresh]).sort_index()
        merged = merged[~merged.index.duplicated(keep="first")]
        return self._write_ticker(ticker, merged)

    # --- coverage ledger --------------------------------------------------

    def _coverage_path(self) -> Path | None:
        return None if self.store_dir is None else self.store_dir / COVERAGE_NAME

    def read_coverage(self) -> dict[str, list[list[str]]]:
        """ticker -> merged list of [start_iso, end_iso] windows already asked
        about. Absent file means "nothing covered", never an error, matching
        read_ticker's contract."""
        path = self._coverage_path()
        if path is None or not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            # A corrupt ledger must never fail a research run: the worst
            # outcome of ignoring it is a redundant fetch.
            return {}

    @staticmethod
    def is_covered(coverage: dict[str, list[list[str]]], ticker: str, start: date, end: date) -> bool:
        """Whether ONE recorded window already contains [start, end).

        One window, not the union of several: two adjacent-but-unmerged
        windows would leave an unasked gap between them, and treating their
        union as covered would silently serve a hole as if it were an answer.
        Merging happens on write, so anything genuinely contiguous is already
        a single entry by the time it is read."""
        for low, high in coverage.get(ticker, []):
            if date.fromisoformat(low) <= start and date.fromisoformat(high) >= end:
                return True
        return False

    def record_coverage(self, tickers: Iterable[str], start: date, end: date) -> None:
        """Record that [start, end) has been asked about for each ticker,
        merging into any window it overlaps or touches."""
        path = self._coverage_path()
        if path is None:
            return
        coverage = self.read_coverage()
        for ticker in tickers:
            windows = [
                (date.fromisoformat(low), date.fromisoformat(high))
                for low, high in coverage.get(ticker, [])
            ]
            windows.append((start, end))
            merged: list[list[date]] = []
            for low, high in sorted(windows):
                if merged and low <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], high)
                else:
                    merged.append([low, high])
            coverage[ticker] = [[low.isoformat(), high.isoformat()] for low, high in merged]
        _atomic_write_bytes(path, json.dumps(coverage, sort_keys=True).encode("utf-8"))

    def resync_ticker(self, ticker: str) -> None:
        """Discard everything stored for one ticker so the next read
        re-records it from the vendor.

        THE ONLY WAY A STORED ROW EVER CHANGES, and deliberately manual: it
        exists so a genuine upstream correction surfaced on
        PriceStoreReport.revisions can be adopted ON PURPOSE. Nothing in the
        read path calls it, because an automatic resync is exactly the
        always-latest behaviour that made backtests irreproducible."""
        path = self._path(ticker)
        if path is not None and path.exists():
            path.unlink()
        coverage = self.read_coverage()
        if ticker in coverage:
            del coverage[ticker]
            coverage_path = self._coverage_path()
            if coverage_path is not None:
                _atomic_write_bytes(coverage_path, json.dumps(coverage, sort_keys=True).encode("utf-8"))

    # --- ingest -----------------------------------------------------------

    @staticmethod
    def to_as_traded(
        fields: dict[str, pd.Series],
        splits: pd.Series,
    ) -> pd.DataFrame:
        """One ticker's vendor rows converted to the as-traded basis of
        section 3, ready to store.

        `fields` holds Yahoo's `auto_adjust=False` columns (already
        split-adjusted onto today's basis, NOT dividend-adjusted); `splits`
        its `Stock Splits` column. Prices and the distribution are multiplied
        by C(t); VOLUME IS DIVIDED BY IT, because a split multiplies the
        share count in exactly the inverse proportion to the price — CRSP
        states this asymmetry explicitly ("Share and volume data are adjusted
        with the calculation A(t)=P(t)*C(t)", against A(t)=P(t)/C(t) for
        prices), and getting it backwards would silently corrupt every
        dollar-volume liquidity gate in the project."""
        close = pd.to_numeric(fields["close"], errors="coerce")
        index = pd.DatetimeIndex(close.index)
        factor = cumulative_split_factor(splits, index)

        out = pd.DataFrame(index=index)
        for column in ("open", "high", "low", "close"):
            series = pd.to_numeric(fields.get(column, pd.Series(dtype=float)), errors="coerce")
            out[column] = series.reindex(index).astype(float) * factor
        volume = pd.to_numeric(fields.get("volume", pd.Series(dtype=float)), errors="coerce")
        out["volume"] = volume.reindex(index).astype(float) / factor
        dividend = pd.to_numeric(fields.get("dividend", pd.Series(dtype=float)), errors="coerce")
        out["dividend"] = dividend.reindex(index).fillna(0.0).astype(float) * factor
        gains = pd.to_numeric(fields.get("capital_gains", pd.Series(dtype=float)), errors="coerce")
        out["capital_gains"] = gains.reindex(index).fillna(0.0).astype(float) * factor
        raw_splits = pd.to_numeric(pd.Series(splits), errors="coerce").reindex(index).fillna(0.0)
        out["split"] = raw_splits.astype(float)
        out.index.name = "date"
        return out[list(STORE_COLUMNS)]

    @staticmethod
    def drop_implausible(frame: pd.DataFrame, report: PriceStoreReport) -> pd.DataFrame:
        """Rows with no usable close are refused at ingest rather than
        stored — a stored row is meant to be a fact (section 4), so a NaN or
        non-positive print must never become one."""
        close = pd.to_numeric(frame["close"], errors="coerce")
        keep = close.notna() & (close > MIN_PLAUSIBLE_PRICE)
        report.rejected_rows += int((~keep).sum())
        return frame.loc[keep]


# --- adjustment engine ------------------------------------------------------
#
# Everything below is a pure function of stored rows. No network, no clock, no
# global state — which is the property that makes a fixed historical window
# reproduce bit-for-bit.


def split_adjusted_prices(frame: pd.DataFrame, columns: Iterable[str]) -> dict[str, pd.Series]:
    """A(t) = P(t)/C(t) of CRSP section 2, with the adjustment base date at
    the LAST ROW OF `frame` — i.e. of the requested window, not of "today".

    THAT BASE-DATE CHOICE IS THE REPRODUCIBILITY GUARANTEE, not a detail. It
    makes the returned levels a function of the requested window and the
    immutable stored rows inside it, and of nothing else: a split occurring
    after the window's end cannot reach back and rescale it, which is exactly
    what Yahoo's always-today base does. It also matches CRSP's own stated
    convention ("The adjustment base date is usually the last available day
    of trading"). Daily returns are invariant to the choice either way; price
    LEVELS are not, which is why it is stated here — dollar-volume and
    minimum-price gates read levels."""
    index = pd.DatetimeIndex(frame.index)
    factor = cumulative_split_factor(frame["split"], index)
    out: dict[str, pd.Series] = {}
    for column in columns:
        series = pd.to_numeric(frame[column], errors="coerce")
        out[column] = series / factor if column != "volume" else series * factor
    return out


def distribution_series(frame: pd.DataFrame, *, drop_same_day_split_distributions: bool) -> pd.Series:
    """The per-date distribution, on the split-adjusted basis matching
    `split_adjusted_prices`, ready to enter a chained return.

    `drop_same_day_split_distributions` implements the spin-off rule of
    module section 5: where Yahoo records a split ratio AND a distribution on
    the SAME ex-date, the price series may already have absorbed the value
    through the split factor, in which case counting the distribution again
    double-counts it.

    IT DEFAULTS TO FALSE AND IS NEVER SWITCHED ON BY A CONVENTION. Section 5
    has the evidence: 15 such events exist across 6 tickers in this project's
    two point-in-time universes, and in 13 of them (all ten of Tootsie Roll's
    stock-dividend-plus-cash-dividend pairs, DXC's CSRA separation, SSP's and
    RILY's) the split ratio and the recorded cash describe two DIFFERENT real
    distributions, so dropping the cash discards a payment that was actually
    made. Yahoo's feed cannot distinguish the two cases, so this is an
    explicit caller decision, never a default."""
    index = pd.DatetimeIndex(frame.index)
    factor = cumulative_split_factor(frame["split"], index)
    dividend = pd.to_numeric(frame["dividend"], errors="coerce").fillna(0.0)
    if drop_same_day_split_distributions:
        splits = pd.to_numeric(frame["split"], errors="coerce").fillna(0.0)
        dividend = dividend.where(splits.isin(_NON_EVENT_SPLIT_VALUES), 0.0)
    return dividend / factor


def total_return_close(
    frame: pd.DataFrame,
    *,
    convention: AdjustmentConvention = AdjustmentConvention.CRSP,
    drop_same_day_split_distributions: bool = False,
) -> pd.Series:
    """The dividend-and-split-adjusted close every family's `pct_change()`
    is taken over — built by CHAINING daily total returns rather than by
    back-propagating a multiplicative factor.

    Chaining is what makes this reproducible. A back-propagated factor is
    anchored at whatever the vendor currently believes about the whole
    subsequent history, so learning one new distribution moves every earlier
    value; a chained return at date t reads only dates t-1 and t, so a row
    that is never rewritten produces a return that never changes.

    The series is normalised to equal the split-adjusted close on the base
    date (the last row), so its LEVEL is directly comparable with
    `split_adjusted_prices`'s and with what `auto_adjust=True` returned for a
    window ending today.

    `drop_same_day_split_distributions` is FALSE under both conventions and is
    never implied by one — see distribution_series and module section 5 for
    why (it is right for 2 of the 15 such events in this project's universes
    and wrong for the other 13).

    THE CRSP BRANCH IS CRSP's p.119 FORMULA, not an approximation of it.
    CRSP: Total Return = (adjprc + divamt/cumfacpr/facpr) / prev_adjprc - 1.
    Here adjprc = P(t)/C(t) and prev_adjprc = P(t-1)/C(t-1) = P(t-1)/(f*C(t))
    with f the ratio on date t, so the expression below expands to
    [f*P(t) + f*D(t)] / P(t-1) while CRSP's expands to
    [f*P(t) + divamt] / P(t-1). They coincide because CRSP's divamt is stated
    to be on the PREVIOUS period's basis and one old share becomes f new
    ones, so a payment of D per new share is f*D per old share. For f = 1 —
    38,138 of the 38,153 distribution events in this project's universes —
    this is just (P(t)+D(t))/P(t-1), the arithmetic definition of what a
    holder earned."""
    prices = split_adjusted_prices(frame, ["close"])["close"]
    dividends = distribution_series(
        frame, drop_same_day_split_distributions=drop_same_day_split_distributions
    )
    previous = prices.shift(1)

    if convention is AdjustmentConvention.CRSP:
        growth = (prices + dividends) / previous
    else:
        # Yahoo's own back-adjustment multiplier, (1 - D/P_prev), expressed
        # as the chained return it implies. Reproduces auto_adjust=True to a
        # max relative difference of 1.4e-06 across this project's universe.
        denominator = (previous - dividends).where(lambda s: s > 0.0)
        growth = prices / denominator

    growth = growth.replace([np.inf, -np.inf], np.nan)
    # A gap with no usable previous price contributes no return rather than
    # breaking the chain — the same "missing return is not a zero return"
    # handling CRSP describes for its own compounded returns.
    chained = growth.where(prices.notna()).fillna(1.0).cumprod()
    valid = prices.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=prices.index, dtype=float)
    base = valid.index[-1]
    scaled = chained / chained.loc[base] * float(prices.loc[base])
    return scaled.where(prices.notna())


def adjusted_frames(
    frame: pd.DataFrame,
    *,
    convention: AdjustmentConvention = AdjustmentConvention.CRSP,
) -> dict[str, pd.Series]:
    """One ticker's stored rows rendered as the five adjusted OHLCV series
    the cross-sectional families consume, plus the dividend-unadjusted
    `price_only_close` that market-cap and carry consumers need.

    Open/High/Low are carried on the TOTAL-RETURN basis, scaled by the same
    per-date factor that takes the split-adjusted close to the total-return
    close. That keeps an open(t)/close(t-1) overnight return
    split-and-dividend consistent, which is the property
    YFinanceProvider.get_daily_ohlcv's docstring already relied on
    `auto_adjust=True` for."""
    split_adjusted = split_adjusted_prices(frame, ["open", "high", "low", "close", "volume"])
    total_return = total_return_close(frame, convention=convention)
    close = split_adjusted["close"]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = (total_return / close.where(close > 0.0)).replace([np.inf, -np.inf], np.nan)
    return {
        "open": split_adjusted["open"] * ratio,
        "high": split_adjusted["high"] * ratio,
        "low": split_adjusted["low"] * ratio,
        "close": total_return,
        "volume": split_adjusted["volume"],
        "price_only_close": close,
    }


def store_manifest(store_dir: Path) -> dict:
    """A small, cheap fingerprint of what the store currently holds — ticker
    count, row count and the earliest/latest date — so a research run can
    RECORD which store state produced its numbers alongside the numbers
    themselves, per this project's persist-every-result rule."""
    if not store_dir.exists():
        return {"schema": STORE_SCHEMA_VERSION, "tickers": 0, "generated_at_utc": datetime.now(UTC).isoformat()}
    paths = sorted(store_dir.glob("*.csv.gz"))
    return {
        "schema": STORE_SCHEMA_VERSION,
        "tickers": len(paths),
        "bytes": sum(p.stat().st_size for p in paths),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def write_store_manifest(store_dir: Path) -> Path:
    path = store_dir / "manifest.json"
    _atomic_write_bytes(path, json.dumps(store_manifest(store_dir), indent=2).encode("utf-8"))
    return path
