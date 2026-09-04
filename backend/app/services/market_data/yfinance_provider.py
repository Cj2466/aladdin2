import json
import logging
import random
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TypeVar

import pandas as pd
import yfinance as yf

from app.services.market_data.base import MarketDataError, MarketDataProvider, TickerMetadataResult
from app.services.market_data.price_store import (
    AdjustmentConvention,
    PriceStore,
    PriceStoreReport,
    adjusted_frames,
    distribution_series,
    split_adjusted_prices,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0


def _call_with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = RETRY_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY_SECONDS,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Same exponential-backoff-with-jitter shape as
    FinnhubWebSocketClient.run's reconnect delay — the one existing
    retry precedent in this codebase. yfinance is an unofficial,
    scraping-based API with no retry logic of its own; a transient
    failure previously failed the whole caller immediately.

    `sleep` defaults to None (resolved to time.sleep on each call, not
    bound as a parameter default) so tests can monkeypatch this module's
    `time.sleep` and have it take effect — a bound default would capture
    the original function at import time, before any patch applies."""
    sleep_fn = sleep if sleep is not None else time.sleep
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception:
            if attempt == attempts:
                raise
            sleep_fn(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1))
    raise AssertionError("unreachable")  # loop always returns or raises

# Individual/CUSIP-level bonds have no practical yfinance coverage, and
# options need a greeks/IV risk model this variance-based engine doesn't
# implement — both are deliberately left unmapped (fall through to "Other").
_QUOTE_TYPE_TO_ASSET_CLASS = {
    "EQUITY": "Equity",
    "ETF": "ETF",
    "MUTUALFUND": "Mutual Fund",
    "CRYPTOCURRENCY": "Crypto",
}

_BOND_KEYWORDS = ("bond", "fixed income", "fixed-income", "treasury")


# Empirically verified 2026-08-25 (Phase A, pattern-mining pilot): yfinance's
# intraday intervals have wildly different free-history ceilings, confirmed
# via live yf.download calls, not assumed from docs. 1m: hard API error past
# ~8 days. 5m/15m/30m: hard API error past ~60 days, AND that 60-day window
# is genuinely ROLLING — re-fetching tomorrow returns a different trailing
# 60 days, it never accumulates into more history. 60m (alias "1h"): no such
# wall with period="max" — confirmed 3471 hourly bars for AAPL spanning
# 2024-08-26 to 2026-08-24 (~2 years), at a clean 7 bars/day (09:30-15:30 ET)
# on 493 of ~500 real trading days; the remaining ~7 are early closes with
# 2-3 bars (half-day holidays). This is the only intraday granularity with
# enough real history to walk-forward backtest a pattern against — finer
# granularity is explicitly Phase B's job, against Alpaca's historical API
# instead of yfinance, not this provider's.
INTRADAY_ALLOWED_INTERVALS = {"60m", "1h"}
INTRADAY_OHLCV_FIELDS = ("Open", "High", "Low", "Close", "Volume")

# The daily fields the cross-sectional families need beyond
# get_price_history's Close-only extraction: Open for the Lou/Polk/Skouras
# overnight-vs-intraday return decomposition (close->open vs open->close
# needs a genuine daily Open, not just Close), Volume for the Grinblatt/Han
# capital-gains-overhang turnover proxy. High/Low were originally left out
# ("no Round C signal reads them") and added 2026-08-28 for the EDGE
# spread-based cost model (spread_estimator.build_edge_half_spread_frame
# consumes full OHLC): yf.download returns every field regardless — the
# earlier version merely declined to extract High/Low from a response that
# already carried them — so extracting them costs nothing on the wire and
# spares the one consumer that needs OHLC a second, redundant download.
DAILY_OHLCV_FIELDS = ("Open", "High", "Low", "Close", "Volume")


def _lowercase_ohlcv_columns(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns={c: str(c).lower() for c in frame.columns})


def _is_bond_etf(info: dict) -> bool:
    # yfinance's `category` field is inconsistently populated across ETF
    # issuers, so fall back to the fund name as a second signal.
    haystack = " ".join(
        str(info.get(field) or "").lower() for field in ("category", "longName", "shortName")
    )
    return any(keyword in haystack for keyword in _BOND_KEYWORDS)


class YFinanceProvider(MarketDataProvider):
    """Fetches price history and ticker metadata from Yahoo Finance via the
    unofficial yfinance library.

    DAILY PRICE READS GO THROUGH THE POINT-IN-TIME PRICE STORE BY DEFAULT
    (price_store.py). get_price_history, get_daily_ohlcv and
    get_total_and_price_return_closes no longer ask Yahoo for an
    already-adjusted series on every call: they record RAW (as-traded) OHLCV
    plus corporate actions once, never overwrite a recorded row, and compute
    every adjusted series deterministically from that stored copy. See
    price_store.py's module docstring for the measured bug (identical fetches
    of an identical historical window returning different prices depending on
    when they ran), the CRSP primary source for the architecture, and the
    immutability policy.

    THIS IS THE DEFAULT, NOT AN OPT-IN. `price_store=PriceStore(None)`
    disables persistence and restores straight pass-through fetching; it
    exists for unit tests and is not a supported production mode, because a
    run with persistence off has exactly the reproducibility properties the
    store was written to remove.

    The metadata read-through cache in metadata_cache.py still sits in front
    of this interface; price_cache.py's PriceBar table now sits in front of a
    provider that is itself already reproducible."""

    def __init__(
        self,
        price_store: PriceStore | None = None,
        adjustment: AdjustmentConvention = AdjustmentConvention.YAHOO,
    ) -> None:
        self.price_store = price_store if price_store is not None else PriceStore()
        self.adjustment = adjustment
        # The report from the most recent store interaction, so a caller or a
        # runner can inspect what was fetched versus replayed — and, crucially,
        # whether any upstream REVISION to an already-stored row was held back
        # (price_store section 4). Revisions are ALSO logged at WARNING as they
        # happen — inspectable was not enough, since nothing in a live tick
        # reads this attribute.
        self.last_store_report: PriceStoreReport | None = None

    # --- store-backed daily price path ------------------------------------

    def _download_raw_with_actions(self, tickers: list[str], start: date, end: date):
        """The one and only network call the daily price path makes.

        auto_adjust=False + actions=True is what yields the store's inputs
        together in a single request: Yahoo's split-adjusted-but-not-
        dividend-adjusted OHLCV alongside the `Dividends` and `Stock Splits`
        series needed to put it on the as-traded basis and to adjust it
        again later. Asking for the adjusted series instead would be asking
        for the derived opinion whose instability is the entire problem."""
        try:
            return _call_with_retry(
                lambda: yf.download(
                    tickers,
                    start=start,
                    end=end,
                    auto_adjust=False,
                    actions=True,
                    progress=False,
                )
            )
        except Exception as exc:
            raise MarketDataError(f"Failed to fetch price data: {exc}") from exc

    @staticmethod
    def _per_ticker_fields(raw: pd.DataFrame, tickers: list[str]) -> dict[str, dict[str, pd.Series]]:
        """Split one yf.download response into per-ticker column bundles,
        handling both the MultiIndex(field, ticker) shape and the flat
        single-ticker shape every other method in this class defends
        against."""
        wanted = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Dividends": "dividend",
            "Stock Splits": "split",
            "Capital Gains": "capital_gains",
        }
        bundles: dict[str, dict[str, pd.Series]] = {}
        if isinstance(raw.columns, pd.MultiIndex):
            fields = set(raw.columns.get_level_values(0))
            if "Close" not in fields:
                raise MarketDataError(f"Unexpected data shape for {tickers}")
            resolved = set(raw.columns.get_level_values(1))
            for ticker in tickers:
                if ticker not in resolved:
                    continue
                bundle = {
                    key: pd.to_numeric(raw[(field, ticker)], errors="coerce")
                    for field, key in wanted.items()
                    if field in fields
                }
                bundles[ticker] = bundle
        else:
            if "Close" not in raw.columns:
                raise MarketDataError(f"Unexpected data shape for {tickers}")
            if not tickers:
                return bundles
            bundles[tickers[0]] = {
                key: pd.to_numeric(raw[field], errors="coerce")
                for field, key in wanted.items()
                if field in raw.columns
            }
        return bundles

    def _stored_rows(
        self, tickers: list[str], start: date, end: date
    ) -> tuple[dict[str, pd.DataFrame], PriceStoreReport]:
        """Every requested ticker's stored as-traded rows covering
        [start, end), fetching from Yahoo only the tickers the store cannot
        already serve.

        A FULLY-COVERED FIXED HISTORICAL WINDOW MAKES NO NETWORK CALL AT ALL.
        That is the reproducibility guarantee in operational form: a rerun of
        a finished backtest cannot pick up a revised price because it never
        asks for one.

        COVERAGE IS READ FROM THE LEDGER, NOT INFERRED FROM THE ROWS. "Have I
        already asked the vendor about this window?" and "do the rows reach
        the window's end?" are different questions, and for a delisted name or
        a window ending on a weekend the honest answer to the first is yes
        while the second is no. See price_store.COVERAGE_NAME.

        A ROLLING WINDOW (end >= today) IS REFETCHED ONCE PER CALENDAR DAY,
        AND THAT PRECISION IS LOAD-BEARING FOR LIVE FORWARD VALIDATION.
        Recorded coverage is capped at the day it was recorded and a rolling
        request demands coverage through today, so the first call on any given
        day misses and picks up every new bar, while every later call that day
        replays it. An earlier draft of this method allowed the
        ROLLING_WINDOW_TOLERANCE_DAYS slack that price_cache uses, which was
        WRONG HERE: price_cache infers coverage from data (and so must tolerate
        a window ending on a weekend), but this ledger records the question
        asked — and with that slack a live tick could be served four-day-stale
        prices and evaluate a registered strategy against them. Every live
        panel builder in cross_sectional_forward_registry reaches the vendor
        through this method, so that would have silently degraded the live
        track record of all four live registrations."""
        report = PriceStoreReport(tickers_requested=len(tickers))
        store = self.price_store
        unique = list(dict.fromkeys(tickers))

        today = date.today()  # noqa: DTZ011 — coverage bound only
        # A request reaching into the future can only ever be answered up to
        # today; requiring more would mean no rolling window is ever covered
        # and every call refetches.
        required_end = min(end, today)
        required_start = start

        coverage = store.read_coverage()
        stored: dict[str, pd.DataFrame] = {}
        need_fetch: list[str] = []
        for ticker in unique:
            if not store.is_covered(coverage, ticker, required_start, required_end):
                need_fetch.append(ticker)
                continue
            report.tickers_served_from_store += 1
            frame = store.read_ticker(ticker)
            if frame is None or frame.empty:
                continue  # covered, and the honest answer is "no rows".
            window = frame.loc[
                (frame.index >= pd.Timestamp(start)) & (frame.index < pd.Timestamp(end))
            ]
            if not window.empty:
                stored[ticker] = window

        if need_fetch:
            report.tickers_fetched = len(need_fetch)
            raw = self._download_raw_with_actions(need_fetch, start, end)
            bundles: dict[str, dict[str, pd.Series]] = {}
            if raw is not None and not raw.empty:
                bundles = self._per_ticker_fields(raw, need_fetch)
            for ticker in need_fetch:
                bundle = bundles.get(ticker)
                if bundle is None or "close" not in bundle:
                    continue
                as_traded = PriceStore.to_as_traded(bundle, bundle.get("split", pd.Series(dtype=float)))
                as_traded = PriceStore.drop_implausible(as_traded, report)
                if as_traded.empty:
                    continue
                merged = store.merge_ticker(ticker, as_traded, report)
                window = merged.loc[
                    (merged.index >= pd.Timestamp(start)) & (merged.index < pd.Timestamp(end))
                ]
                if not window.empty:
                    stored[ticker] = window
            # Coverage is recorded for EVERY fetched ticker, including the
            # ones that resolved nothing: "asked, and there is none" is an
            # answer, and the whole point of the ledger is that it is stored
            # as one instead of being re-asked forever.
            store.record_coverage(need_fetch, start, min(end, today))

        if report.revisions:
            # Holding a vendor revision back is only defensible if it is
            # VISIBLE. Inspectable-on-the-report was not enough: nothing in a
            # live forward-validation tick reads the report, so a silently
            # withheld correction would look exactly like no correction.
            sample = ", ".join(
                f"{ticker} {when.isoformat()} {stored:.6g}->{fetched:.6g}"
                for ticker, when, stored, fetched in report.revisions[:5]
            )
            logger.warning(
                "price store held back %d upstream revision(s) to already-recorded rows "
                "(first-write-wins, price_store section 4); resync_ticker adopts one on "
                "purpose. Sample: %s",
                len(report.revisions),
                sample,
            )

        report.missing = [t for t in tickers if t not in stored]
        self.last_store_report = report
        return stored, report

    def _adjusted_wide(
        self, tickers: list[str], start: date, end: date, fields: tuple[str, ...]
    ) -> tuple[dict[str, pd.DataFrame], list[str]]:
        """The requested adjusted fields as wide (dates x tickers) frames,
        computed per ticker from stored rows and then aligned.

        Alignment mirrors get_daily_ohlcv's long-standing contract exactly:
        `close` availability defines the result, every other field is
        reindexed onto close's index and columns, and a ticker with a close
        but a sparse open just carries NaN rather than being dropped."""
        stored, _report = self._stored_rows(tickers, start, end)
        if not stored:
            return {}, list(tickers)

        per_field: dict[str, dict[str, pd.Series]] = {name: {} for name in fields}
        for ticker, frame in stored.items():
            adjusted = adjusted_frames(frame, convention=self.adjustment)
            for name in fields:
                per_field[name][ticker] = adjusted[name]

        close = pd.DataFrame(per_field["close"])
        close = close.dropna(axis=1, how="all").dropna(axis=0, how="all")
        if close.empty:
            return {}, list(tickers)
        close = close.sort_index()
        # Column order follows the caller's request order, not dict insertion
        # order, so a wide frame is reproducible independent of how the store
        # happened to be traversed.
        ordered = [t for t in dict.fromkeys(tickers) if t in close.columns]
        close = close[ordered]

        aligned: dict[str, pd.DataFrame] = {}
        for name in fields:
            if name == "close":
                aligned[name] = close
                continue
            aligned[name] = pd.DataFrame(per_field[name]).reindex(
                index=close.index, columns=close.columns
            )
        missing = [t for t in tickers if t not in close.columns]
        return aligned, missing

    def get_price_history(
        self, tickers: list[str], start: date, end: date
    ) -> tuple[pd.DataFrame, list[str]]:
        """The dividend-and-split-adjusted Close panel, served from the
        point-in-time price store.

        SEMANTICS ARE UNCHANGED from the previous `auto_adjust=True`
        implementation — the returned series is still a total-return-adjusted
        close whose pct_change() is a total return — but it is now computed by
        this project from stored as-traded rows rather than requested fresh
        from Yahoo, so an identical (tickers, start, end) request returns an
        identical frame however long after the first one it runs. Verified
        equivalent to the old path to a max relative difference of 1.4e-06
        across 1.70 million universe cells; see price_store.py section 5.

        The empty-frame contract is unchanged too: reaching a result with no
        resolved ticker means yfinance answered successfully but nothing
        resolved (typo, delisted, never listed), which is the same "missing
        ticker" case the partial-invalid path handles via `missing`, not a
        MarketDataError. A genuine connectivity failure still raises from
        _download_raw_with_actions."""
        frames, missing = self._adjusted_wide(tickers, start, end, ("close",))
        if not frames:
            return pd.DataFrame(), list(tickers)
        return frames["close"], missing

    def get_intraday_bars(
        self, tickers: list[str], interval: str = "60m"
    ) -> tuple[dict[str, pd.DataFrame], list[str]]:
        """Full OHLCV hourly bars for the Phase A pattern-mining pilot —
        genuinely distinct from get_price_history, which extracts Close
        only (fine for daily-bar strategies, not for candlestick-shape
        patterns that need the full bar). Returns a dict keyed by ticker
        (each value a DataFrame with lowercase open/high/low/close/volume
        columns and a tz-aware intraday DatetimeIndex) rather than one
        wide multi-index frame, since every downstream consumer
        (intraday_patterns.py) processes one ticker's own bars at a time
        — this does that split once here instead of at every call site.

        Not a NEW abstract method on MarketDataProvider: the daily-bar
        interface (get_price_history/get_ticker_metadata) exists so a
        fallback/alternate provider can be swapped in without touching
        risk math or route code. This method has a genuinely different
        shape (dict-of-DataFrames, no start/end window, OHLCV not
        Close-only) and exactly one caller today (Phase A screening) — no
        alternate provider needs to implement it yet. Revisit if/when
        Phase B's Alpaca provider needs a matching intraday method (its
        own shape may differ, e.g. real start/end support at finer
        granularity), rather than forcing this exact signature onto it.

        No caching layer, deliberately, unlike get_price_history_cached's
        PriceBar table: that cache is justified by many features (
        screening, sweeps, forward-validation, risk analysis) hitting the
        SAME 503-ticker universe repeatedly, many times a day. This
        method has exactly one caller today (the Phase A screening pass,
        not wired into any daily/autonomous runner) — no recurring-fetch
        cost to amortize yet. A persistent cache would also have to solve
        a problem daily bars never face: this ~2-year window is itself a
        ROLLING window (yfinance's own ceiling, see
        INTRADAY_ALLOWED_INTERVALS's comment), so cached rows age OUT of
        the fetchable range over time and would need active pruning, not
        the daily cache's simple append-only growth. Building that now,
        for a workload that doesn't exist yet, would be exactly the kind
        of speculative infrastructure this phase was told not to add —
        revisit once/if this is wired into a recurring job.

        Always fetches period="max" (yfinance's own ceiling for this
        interval) — no start/end window, unlike get_price_history."""
        if interval not in INTRADAY_ALLOWED_INTERVALS:
            raise ValueError(
                f"Unsupported intraday interval {interval!r}; only "
                f"{sorted(INTRADAY_ALLOWED_INTERVALS)} have enough free yfinance history to "
                "walk-forward backtest against (see INTRADAY_ALLOWED_INTERVALS's module comment) "
                "— finer granularity is Phase B's job, against Alpaca instead of yfinance."
            )

        try:
            raw = _call_with_retry(
                lambda: yf.download(
                    tickers,
                    period="max",
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                )
            )
        except Exception as exc:
            raise MarketDataError(f"Failed to fetch intraday price data: {exc}") from exc

        if raw is None or raw.empty:
            # Same reasoning as get_price_history: a genuine connectivity
            # failure already raised above — an empty-but-successful
            # response means none of the requested tickers resolved.
            return {}, list(tickers)

        bars_by_ticker: dict[str, pd.DataFrame] = {}
        if isinstance(raw.columns, pd.MultiIndex):
            available_fields = set(raw.columns.get_level_values(0))
            if not set(INTRADAY_OHLCV_FIELDS).issubset(available_fields):
                raise MarketDataError(f"Unexpected intraday data shape for {tickers}")
            resolved_tickers = set(raw.columns.get_level_values(1))
            for ticker in tickers:
                if ticker not in resolved_tickers:
                    continue
                frame = raw.xs(ticker, axis=1, level=1)[list(INTRADAY_OHLCV_FIELDS)]
                frame = frame.dropna(how="all")
                if not frame.empty:
                    bars_by_ticker[ticker] = _lowercase_ohlcv_columns(frame)
        else:
            # Defensive fallback mirroring get_price_history's own
            # comment — some yfinance versions/inputs collapse to flat
            # columns for a single ticker; empirically NOT observed for
            # this method even with a length-1 list (verified 2026-08-25,
            # still returns MultiIndex), but kept for the same reason
            # get_price_history keeps it.
            if not set(INTRADAY_OHLCV_FIELDS).issubset(set(raw.columns)):
                raise MarketDataError(f"Unexpected intraday data shape for {tickers}")
            frame = raw[list(INTRADAY_OHLCV_FIELDS)].dropna(how="all")
            if not frame.empty and tickers:
                bars_by_ticker[tickers[0]] = _lowercase_ohlcv_columns(frame)

        missing = [t for t in tickers if t not in bars_by_ticker]
        return bars_by_ticker, missing

    def get_daily_ohlcv(
        self, tickers: list[str], start: date, end: date
    ) -> tuple[dict[str, pd.DataFrame], list[str]]:
        """Daily Open/High/Low/Close/Volume as five wide (dates x tickers)
        frames, keyed "open"/"high"/"low"/"close"/"volume" — the
        cross-sectional families' data shape (originally Open/Close/Volume
        only; High/Low added 2026-08-28 for the EDGE spread cost model, see
        DAILY_OHLCV_FIELDS). Added ALONGSIDE get_price_history rather than
        replacing it, exactly the way get_intraday_bars was added alongside
        the Close-only path: every existing daily-bar caller keeps its
        Close-only contract untouched, and this method serves the one new
        consumer (cross_sectional.py) that genuinely needs Open (for the
        Lou/Polk/Skouras overnight-vs-intraday decomposition) and Volume
        (for the Grinblatt/Han turnover proxy).

        Not a new abstract method on MarketDataProvider, for the same
        reason get_intraday_bars isn't (see that method's docstring): one
        caller today, and no alternate provider needs to implement it yet.

        SERVED FROM THE POINT-IN-TIME PRICE STORE (price_store.py), like
        get_price_history — the returned frames are computed from stored
        as-traded rows, not requested fresh from Yahoo, so a fixed historical
        window reproduces exactly however long after the first run it is
        re-requested.

        The adjustment basis is unchanged in kind. Open/High/Low/Close all
        carry the same per-date total-return factor, so an open_t/close_{t-1}
        overnight return is still split/dividend-consistent (a raw Open
        against an adjusted Close would inject a fake gap at every
        ex-dividend/split date). Dividends therefore still land in the
        OVERNIGHT component, matching the ex-date mechanics (the price
        adjustment happens at the open) and Lou/Polk/Skouras's own
        convention.

        VOLUME IS NOW SPLIT-ADJUSTED ONTO THE WINDOW'S OWN BASE DATE rather
        than shipped as Yahoo happened to express it. This is a deliberate
        correction, not a side effect: CRSP adjusts share and volume data by
        MULTIPLYING by the cumulative factor where prices are DIVIDED by it
        (Data Description Guide ch.5 p.117), and this project's dollar-volume
        liquidity gates multiply close by volume — so leaving the two on
        inconsistent bases would put a discontinuity into every such gate at
        every split date. The one consumer that normalizes volume by its own
        trailing mean (cross_sectional_patterns.py's turnover proxy) is
        insensitive to the level convention either way.

        A ticker is "missing" if its Close came back entirely empty —
        Close availability defines the ticker set, and open/volume are
        reindexed to close's exact index/columns so the three frames are
        always aligned (a ticker with Close but a sparse Open just carries
        NaN Opens, which the signal fns' own min-observation gates handle,
        rather than being dropped wholesale)."""
        frames, missing = self._adjusted_wide(
            tickers, start, end, ("open", "high", "low", "close", "volume")
        )
        if not frames:
            return {}, list(tickers)
        return frames, missing

    def get_shares_outstanding(
        self, tickers: list[str], start: date, end: date
    ) -> tuple[dict[str, pd.Series], list[str]]:
        """Sparse, point-in-time shares-outstanding EVENTS per ticker, via
        yfinance's yf.Ticker(ticker).get_shares_full(start, end) — added for
        Build D1's value-weighted idiosyncratic-volatility family
        (cross_sectional_ivol.py), the first consumer in this codebase that
        needs real historical share counts rather than today's snapshot.
        This is the ONLY free point-in-time market-cap input available:
        yfinance carries no historical shares-outstanding series any other
        way, and a single current `.info["sharesOutstanding"]` value would
        silently apply TODAY's share count to every historical formation
        date — exactly the look-ahead bug "point-in-time" is meant to rule
        out everywhere else in this project (was_member, the membership
        history module).

        Confirmed live (2026-08-26, AAPL/MSFT/BRK-B) that get_shares_full
        has NO multi-ticker batch form the way yf.download does — it is a
        Ticker-level method only — so this loops one call per ticker, each
        wrapped in the same _call_with_retry backoff every other call in
        this class uses. Not cheap for a wide universe; deliberately not
        used anywhere that runs routinely yet (see cross_sectional_ivol.py's
        run_round_d1_screening docstring).

        Each returned Series is SPARSE and EVENT-DATED — one row per SEC
        filing that changed the share count, not one row per trading day
        (confirmed live: AAPL over 2024-01-01..2024-02-01 returns 11 rows
        for a ~21-trading-day window). Callers MUST forward-fill onto their
        own trading-day index themselves (see cross_sectional_ivol.py's
        build_point_in_time_market_cap) — a date with no row here means "no
        filing that day", never "zero shares".

        DO NOT MULTIPLY THESE BY get_price_history's CLOSE. That is not a
        market cap, and shipping it as one was a real bug in Build D1's
        first production run. These counts are as-filed at the time; that
        close is back-adjusted for every later split AND every dividend
        since, so the product is wrong by the cumulative split factor
        (AAPL's computed cap jumped 3.96x across its 2020 4-for-1's filing
        boundary on a -0.95% price day) and by the ticker's own dividend
        history (0.448x for T vs 1.000x for AMZN as of 2015-01-07). Use
        get_market_cap_basis below for the right price and the split ratios,
        and cross_sectional_ivol.split_adjust_share_counts to put these
        counts on that same basis first.

        Two yfinance quirks are normalized away here rather than left for
        every caller to rediscover:
          (1) The raw index is tz-aware (America/New_York); get_daily_ohlcv's
              close index is tz-naive. Stripped via tz_localize(None) (not
              tz_convert — these timestamps are already midnight-local
              filing dates, there is no wall-clock conversion to make) so a
              caller can align the two without a tz-mismatch error.
          (2) The raw index can carry EXACT DUPLICATE dates with two
              different share counts (confirmed live: AAPL 2024-01-05 and
              2024-02-01 both appeared twice, ~1.3% apart — almost
              certainly a preliminary vs. corrected filing for the same
              date). De-duplicated by keeping the LAST value for a given
              date, after sorting — the corrected filing, not an
              arbitrary one.

        A ticker that fails to resolve (bad ticker, no SEC-filed share
        count anywhere in the window, or a transient error surviving every
        retry) is simply absent from the returned dict and present in
        `missing` — this method never raises for a single bad ticker, the
        same "don't fail a whole universe fetch over one name" contract
        get_price_history/get_daily_ohlcv already keep via their own
        `missing` lists."""
        shares: dict[str, pd.Series] = {}
        missing: list[str] = []
        for ticker in tickers:
            try:
                raw = _call_with_retry(lambda t=ticker: yf.Ticker(t).get_shares_full(start=start, end=end))
            except Exception:
                raw = None
            if raw is None or raw.empty:
                missing.append(ticker)
                continue
            series = raw.astype(float)
            series.index = pd.DatetimeIndex(series.index).tz_localize(None)
            series = series[~series.index.duplicated(keep="last")].sort_index()
            shares[ticker] = series
        return shares, missing

    def get_market_cap_basis(
        self, tickers: list[str], start: date, end: date
    ) -> tuple[pd.DataFrame, dict[str, pd.Series], list[str]]:
        """The two extra inputs a POINT-IN-TIME MARKET CAP needs that
        get_price_history alone cannot supply, both from ONE batched
        yf.download(auto_adjust=False, actions=True) call:

          (1) `close` — Yahoo's own Close column, which is adjusted for
              SPLITS but NOT for dividends. This, not get_price_history's
              auto_adjust=True close, is the correct price to multiply a
              share count by: auto_adjust=True additionally back-adjusts
              every historical price DOWNWARD by the dividends paid since
              (confirmed live 2026-08-26: on 2015-01-07 the ratio
              AdjClose/Close was 1.000 for AMZN/BRK-B, which paid nothing,
              but 0.448 for T and 0.611 for XOM). Multiplying a share count
              by an ex-dividend-adjusted price understates market cap by
              that factor — and by DIFFERENT factors for different tickers,
              which is precisely the distortion a cross-sectional VALUE
              weighting must not have. Yahoo's Close carries no such
              dividend adjustment, so shares * Close is the real market
              cap. Total-return SIGNALS must still use get_price_history's
              dividend-adjusted close — these are two different prices for
              two different jobs, deliberately fetched separately.

          (2) `splits` — per-ticker dated split ratios (ex-date -> ratio,
              e.g. AAPL 2020-08-31 -> 4.0). Needed because Yahoo's Close
              above is back-adjusted for splits (every historical price is
              expressed in TODAY's share units) while
              get_shares_outstanding's counts are the raw counts filed at
              the time. See cross_sectional_ivol.split_adjust_share_counts,
              which uses these to put the two on one basis.

        Both come from the same single batched download — a split ratio is
        also available per-ticker via yf.Ticker(t).splits, but that is one
        network call PER TICKER (the same cost problem
        get_shares_outstanding already documents), whereas actions=True
        rides along on a call this method has to make anyway. Confirmed
        live 2026-08-26 that a batched multi-ticker download does carry a
        'Stock Splits' field per ticker.

        Only splits INSIDE [start, end] are returned, and that is exactly
        right rather than a limitation: a split before `start` is already
        reflected in both series (the prices in the window are post-it, and
        so are the share counts filed in the window), so it needs no
        adjustment; a split after `end` cannot exist for a window ending
        today.

        Returns (close, splits_by_ticker, missing) with the same
        "never fail a whole universe over one bad name" contract
        get_price_history keeps. A ticker with no splits in the window is
        simply absent from `splits_by_ticker` — meaning "no splits", never
        "unknown".

        SERVED FROM THE POINT-IN-TIME PRICE STORE, from the same stored rows
        the price methods read. This method fetched its own
        auto_adjust=False + actions=True download before the store landed —
        exactly the request the store now makes — so routing it here removes
        a duplicate network call AND removes a second, independent copy of
        the same instability: Yahoo's `Close` is split-adjusted onto TODAY's
        share basis, so this method's own output was silently re-expressed
        every time a name split again. The `close` returned here is now the
        split-adjusted price on the WINDOW's base date, which is the same
        quantity on a basis that a later corporate action cannot move."""
        stored, _report = self._stored_rows(tickers, start, end)
        if not stored:
            return pd.DataFrame(), {}, list(tickers)

        closes = {t: split_adjusted_prices(f, ["close"])["close"] for t, f in stored.items()}
        close = pd.DataFrame(closes).dropna(axis=1, how="all").dropna(axis=0, how="all").sort_index()
        if close.empty:
            return pd.DataFrame(), {}, list(tickers)
        close = close[[t for t in dict.fromkeys(tickers) if t in close.columns]]

        splits_by_ticker: dict[str, pd.Series] = {}
        for ticker in close.columns:
            col = pd.to_numeric(stored[ticker]["split"], errors="coerce")
            # A "no split today" row is 0.0 (not NaN, not 1.0) in yfinance's
            # actions output, which is what the store records verbatim; 1.0
            # would be a no-op ratio and is dropped for the same reason.
            events = col[(col > 0.0) & (col != 1.0)].dropna()
            if events.empty:
                continue
            # Normalized to midnight so a split ex-date compares cleanly
            # against get_shares_outstanding's own midnight-dated index.
            events.index = pd.DatetimeIndex(events.index).normalize()
            splits_by_ticker[ticker] = events.sort_index()

        missing = [t for t in tickers if t not in close.columns]
        return close, splits_by_ticker, missing

    def get_dividend_history(
        self, tickers: list[str], start: date, end: date
    ) -> tuple[dict[str, pd.Series], pd.DataFrame, list[str]]:
        """Per-ticker CASH DIVIDEND history plus the split-adjusted Close it
        must be read against, from ONE batched
        yf.download(auto_adjust=False, actions=True) call — the same call
        shape get_market_cap_basis makes, for the same reason: the
        per-ticker alternative (yf.Ticker(t).dividends) is one network round
        trip PER NAME, which is the cost problem get_shares_outstanding
        already documents.

        Returns (dividends_by_ticker, close, missing).

        THE INDEX IS THE EX-DIVIDEND DATE, NOT THE PAYMENT DATE. This is a
        FACT ABOUT THE SOURCE and it is stated here rather than in a
        consumer, because it is the single most consequential thing to know
        about this data. Yahoo's actions feed carries one date per
        distribution and it is the ex-date (verified live 2026-09-02 against
        the known AAPL 2014-08-07 ex-date / 2014-08-14 pay-date pair, and
        against KO's March/June/September/December ex-date cadence). A
        caller that needs PAYMENT dates does not have them here and must say
        so; nothing in this method can recover one.

        AMOUNTS ARE SPLIT-ADJUSTED, expressed in today's share units — the
        same basis as the `Close` returned alongside them (Yahoo's Close is
        split-adjusted but NOT dividend-adjusted, per get_market_cap_basis).
        That pairing is deliberate and load-bearing: dividend / Close is
        therefore a scale-consistent yield at every historical date, whereas
        dividing by get_price_history's dividend-back-adjusted close would
        overstate old yields by the same factor that method documents (0.448
        for T on 2015-01-07). NVDA's 2014 dividends coming back as $0.002125
        rather than the $0.085 actually paid is this adjustment working, not
        a data error.

        A zero row is "no distribution that day", never "unknown" — yfinance
        fills the action columns with 0.0 on ordinary days — so only strictly
        positive values are kept. A ticker with no dividend inside the
        window is simply ABSENT from the returned dict, meaning "paid
        nothing", never "unknown"; a ticker that resolved no price at all is
        in `missing` instead, which is the difference that matters to a
        family predicting payers from non-payers.

        Missing-ticker contract mirrors get_market_cap_basis exactly: the
        Close frame defines the result.

        SERVED FROM THE POINT-IN-TIME PRICE STORE, for the same reasons
        get_market_cap_basis is (see that method): this made the identical
        auto_adjust=False + actions=True request the store now makes, and its
        `Close` carried the same silently-moving split basis. The
        dividend-over-close yield this method exists to make scale-consistent
        is therefore now consistent by construction rather than by both
        halves happening to come from one download."""
        stored, _report = self._stored_rows(tickers, start, end)
        if not stored:
            return {}, pd.DataFrame(), list(tickers)

        closes = {t: split_adjusted_prices(f, ["close"])["close"] for t, f in stored.items()}
        close = pd.DataFrame(closes).dropna(axis=1, how="all").dropna(axis=0, how="all").sort_index()
        if close.empty:
            return {}, pd.DataFrame(), list(tickers)
        close = close[[t for t in dict.fromkeys(tickers) if t in close.columns]]

        dividends_by_ticker: dict[str, pd.Series] = {}
        for ticker in close.columns:
            frame = stored[ticker]
            # On the SAME split-adjusted basis as `close` above, which is what
            # makes dividend/close a scale-consistent yield at every historical
            # date — the property this method's docstring turns on.
            amounts = distribution_series(frame, drop_same_day_split_distributions=False)
            events = amounts[amounts > 0.0].dropna()
            if events.empty:
                continue
            # Normalized to midnight so an ex-date compares cleanly against a
            # daily price index, exactly as get_market_cap_basis normalizes
            # split ex-dates.
            events.index = pd.DatetimeIndex(events.index).normalize()
            dividends_by_ticker[ticker] = events.sort_index()

        missing = [t for t in tickers if t not in close.columns]
        return dividends_by_ticker, close, missing

    def get_total_and_price_return_closes(
        self, tickers: list[str], start: date, end: date
    ) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
        """BOTH close-price bases as two aligned wide (dates x tickers)
        frames, from ONE batched download:

          (1) `total_return_close` — Yahoo's `Adj Close`: adjusted for
              splits AND dividends, so a return computed off it is the real
              total return of holding the instrument.
          (2) `price_only_close` — Yahoo's `Close`: adjusted for splits
              only, so a return computed off it is PRICE CHANGE ALONE, with
              every distribution excluded.

        Why both, and why together. For an income-dominated instrument the
        two are not a rounding apart — they can differ in SIGN over a
        multi-year window (a long-duration Treasury ETF that lost money on
        price while making money on total return is the ordinary case, not a
        corner one). Any family whose signal is about CARRY therefore needs
        to see the two separately: over any window,
        (TR_t/TR_{t-L}) / (PX_t/PX_{t-L}) - 1 is the distribution actually
        paid — an OBSERVED yield, not an assumed or vendor-supplied one.
        cross_sectional_bonds.py's curve carry/roll-down mechanism is the
        first consumer; see CrossSectionalData.price_only_close.

        BOTH ARE NOW COMPUTED FROM THE POINT-IN-TIME PRICE STORE, from the
        same stored rows get_daily_ohlcv and get_price_history read: the
        total-return close is the chained total return, and the price-only
        close is the split-adjusted-only price. That is a strictly stronger
        version of what this method previously relied on.

        It previously relied on the claim that auto_adjust=False's
        `Adj Close` is BYTE-IDENTICAL to auto_adjust=True's `Close`, verified
        live 2026-08-27. THAT CLAIM IS CORRECTED HERE: re-measured
        2026-09-04 across 1,701,367 (date, ticker) cells of this project's own
        768-name universe, the two agree only to a maximum RELATIVE difference
        of 1.4e-06, with 954,019 cells differing by more than 1e-09. The
        difference is immaterial to every consumer (it is Yahoo's own
        float rounding between two representations of the same series) but it
        was not what the previous sentence asserted, and this project does not
        leave a measured overstatement standing. The equivalence that actually
        matters is now structural rather than incidental: `close` here and
        `close` from get_daily_ohlcv/get_price_history are the SAME FUNCTION
        of the SAME STORED ROWS, so they are identical by construction and
        cannot drift apart.

        Missing-ticker contract mirrors get_daily_ohlcv's exactly: the
        PRIMARY frame defines the result — a ticker is "missing" only if its
        Adj Close came back entirely empty — and the secondary frame is
        reindexed to the primary's exact index/columns, so the pair is
        always aligned and CrossSectionalData's own alignment check cannot
        fail on data from here. The total-return basis is the primary one
        because it is what CrossSectionalData.close must carry and what
        every realized return is computed from; a ticker priced on total
        return but sparse on price-only just carries NaNs (which the
        consuming signal's own coverage gate handles) rather than being
        dropped from the universe wholesale."""
        frames, missing = self._adjusted_wide(tickers, start, end, ("close", "price_only_close"))
        if not frames:
            return pd.DataFrame(), pd.DataFrame(), list(tickers)
        return frames["close"], frames["price_only_close"], missing

    def get_ticker_metadata(self, ticker: str) -> TickerMetadataResult | None:
        try:
            info = _call_with_retry(lambda: yf.Ticker(ticker).info)
        except Exception:
            return None

        if not info or info.get("quoteType") is None:
            return None

        quote_type = info.get("quoteType")
        asset_class = _QUOTE_TYPE_TO_ASSET_CLASS.get(quote_type, "Other")
        if quote_type == "ETF" and _is_bond_etf(info):
            asset_class = "Bond"

        return TickerMetadataResult(
            sector=info.get("sector"),
            industry=info.get("industry"),
            asset_class=asset_class,
            currency=info.get("currency"),
        )


# --- OHLCV reproducibility snapshot -----------------------------------------
#
# WHY THIS EXISTS, proven rather than assumed (2026-09-04, the lazy_prices
# reproduction-drift investigation): get_daily_ohlcv (and get_price_history)
# call yf.download(..., auto_adjust=True) with NO caching layer, by design
# (see get_daily_ohlcv's own docstring). auto_adjust=True does not return a
# fixed historical record — it back-adjusts the ENTIRE returned series for
# every split and cash dividend Yahoo currently knows about, and that
# knowledge keeps changing: a newly-processed dividend shifts the adjustment
# factor for every date ON OR BEFORE its ex-date, retroactively, on the very
# next live fetch.
#
# MEASURED, not hypothesized: fetching the SAME 625 tickers over the SAME
# 2015-01-07..2026-08-31 window twice, ~5.5 hours apart, with zero code
# changes, changed 2.9% of all (date, ticker) Close cells by more than 1bp,
# with entire multi-year Close series for names like AIZ/ALL/CBOE/DOV/PH
# uniformly rescaled and — critically — a handful of names (DOW, PCL, Q,
# FCPT) rescaled only from a specific date onward, which manufactures or
# erases a single day's pct_change() return at that boundary purely as an
# artifact of when the fetch happened to run. Isolating this from every
# other input (identical similarity panels, identical code, only the price
# fetch re-run) moved cross_sectional_lazy_prices's registered spec's Sharpe
# by +0.0205 and other specs in the same family by up to 0.0433 — the same
# order of magnitude as the previously unexplained +0.6035/+0.5741/+0.5946
# non-monotonic drift across that family's real historical reruns. See
# cross_sectional_lazy_prices.py's module docstring and
# lazy_prices_forward_registration.py's 2026-09-04 correction for the full
# investigation.
#
# THE FIX IS NOT "make Yahoo's data point-in-time" — a free vendor's
# continuously-revised adjusted-close series cannot be made retroactively
# immutable by anything this project controls. The fix is the same shape as
# edgar_filing_text_provider.save_filing_index/load_filing_index: freeze the
# external answer ONCE, to disk, and let a caller that wants a REPRODUCIBLE
# rebuild of a fixed historical window opt into replaying the frozen copy
# instead of re-asking Yahoo a question whose answer has since changed. A
# caller that genuinely wants today's best-available data (e.g. a live
# forward-validation tick evaluating real new trading days) must keep
# calling get_daily_ohlcv/get_price_history directly — nothing about this
# pair loads automatically, exactly like the filing-index pair, so a live
# path can never be silently pinned to stale data by importing this module.
OHLCV_SNAPSHOT_MANIFEST_NAME = "manifest.json"


def save_ohlcv_snapshot(frames: dict[str, pd.DataFrame], directory: Path) -> None:
    """Persist the frames get_daily_ohlcv returned (keys "open"/"high"/"low"/
    "close"/"volume", or any subset) as one gzipped CSV per field plus a small
    JSON manifest, so a FIXED historical window's price data can be replayed
    bit-for-bit on every later rerun instead of depending on Yahoo's live,
    continuously back-adjusted series (see this section's header).

    Deliberately plain CSV+gzip rather than a binary format: this project has
    no parquet/pyarrow dependency, and pandas round-trips a float64 frame
    through to_csv/read_csv losslessly (the default repr carries full
    precision) — the same lightweight-format choice save_filing_index makes
    for the sibling EDGAR snapshot."""
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "saved_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "fields": sorted(frames),
    }
    (directory / OHLCV_SNAPSHOT_MANIFEST_NAME).write_text(json.dumps(manifest))
    for field, frame in frames.items():
        frame.to_csv(directory / f"{field}.csv.gz", compression="gzip")


def load_ohlcv_snapshot(directory: Path) -> dict[str, pd.DataFrame] | None:
    """The inverse of save_ohlcv_snapshot. None (not an exception) when no
    snapshot has been saved at this path yet — the same "absent means build
    one" contract load_filing_index keeps, so a caller can write
    `frames = load_ohlcv_snapshot(path) or fetch-and-save` without a
    try/except."""
    manifest_path = directory / OHLCV_SNAPSHOT_MANIFEST_NAME
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    frames: dict[str, pd.DataFrame] = {}
    for field in manifest["fields"]:
        frames[field] = pd.read_csv(
            directory / f"{field}.csv.gz",
            index_col=0,
            parse_dates=True,
            compression="gzip",
        )
    return frames
