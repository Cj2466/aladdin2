import random
import time
from collections.abc import Callable
from datetime import date
from typing import TypeVar

import pandas as pd
import yfinance as yf

from app.services.market_data.base import MarketDataError, MarketDataProvider, TickerMetadataResult

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

# The three daily fields the Round C cross-sectional families need beyond
# get_price_history's Close-only extraction: Open for the Lou/Polk/Skouras
# overnight-vs-intraday return decomposition (close->open vs open->close
# needs a genuine daily Open, not just Close), Volume for the Grinblatt/Han
# capital-gains-overhang turnover proxy. High/Low are deliberately NOT
# fetched — no Round C signal reads them, and leaving them out keeps the
# wide multi-hundred-ticker response ~40% smaller.
DAILY_OHLCV_FIELDS = ("Open", "Close", "Volume")


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
    unofficial yfinance library. No caching in this class itself — the
    read-through caches in price_cache.py / metadata_cache.py sit in front
    of this same interface."""

    def get_price_history(
        self, tickers: list[str], start: date, end: date
    ) -> tuple[pd.DataFrame, list[str]]:
        try:
            raw = _call_with_retry(
                lambda: yf.download(
                    tickers,
                    start=start,
                    end=end,
                    auto_adjust=True,
                    progress=False,
                )
            )
        except Exception as exc:
            raise MarketDataError(f"Failed to fetch price data: {exc}") from exc

        if raw is None or raw.empty:
            # A genuine connectivity/upstream failure already raised above,
            # inside the try block — reaching here with an empty frame means
            # yfinance responded successfully but none of the requested
            # tickers resolved (typo, delisted, never listed). That's the
            # same "missing ticker" case the partial-invalid path below
            # already handles via the `missing` list, not a MarketDataError
            # — unify them rather than treating "0 of N tickers resolved"
            # as categorically different from "N-1 of N", which previously
            # surfaced as an inconsistent 502 instead of a 422.
            return pd.DataFrame(), list(tickers)

        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" not in raw.columns.get_level_values(0):
                raise MarketDataError(f"Unexpected data shape for {tickers}")
            close = raw["Close"]
        else:
            # Some yfinance versions collapse to flat columns for a single ticker.
            if "Close" not in raw.columns:
                raise MarketDataError(f"Unexpected data shape for {tickers}")
            close = raw[["Close"]]
            close.columns = tickers

        # Drop any ticker column that came back entirely empty (bad/delisted
        # ticker, or a request yfinance silently failed on).
        close = close.dropna(axis=1, how="all")
        close = close.dropna(axis=0, how="all")

        if close.empty:
            # Same reasoning as above — every column was entirely NaN after
            # cleaning, i.e. every ticker is missing, not an upstream failure.
            return pd.DataFrame(), list(tickers)

        missing = [t for t in tickers if t not in close.columns]
        return close, missing

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
        """Daily Open/Close/Volume as three wide (dates x tickers) frames,
        keyed "open"/"close"/"volume" — the Round C cross-sectional
        families' data shape. Added ALONGSIDE get_price_history rather than
        replacing it, exactly the way get_intraday_bars was added alongside
        the Close-only path: every existing daily-bar caller keeps its
        Close-only contract untouched, and this method serves the one new
        consumer (cross_sectional.py) that genuinely needs Open (for the
        Lou/Polk/Skouras overnight-vs-intraday decomposition) and Volume
        (for the Grinblatt/Han turnover proxy).

        Not a new abstract method on MarketDataProvider, for the same
        reason get_intraday_bars isn't (see that method's docstring): one
        caller today, and no alternate provider needs to implement it yet.

        auto_adjust=True applies to Open and Close alike, so an
        open_t/close_{t-1} overnight return is split/dividend-consistent
        (both prices on the same adjusted basis — a raw Open against an
        adjusted Close would inject a fake gap at every ex-dividend/split
        date). Dividends therefore land in the OVERNIGHT component, which
        matches the ex-date mechanics (the price adjustment happens at the
        open) and Lou/Polk/Skouras's own convention. Volume is returned as
        yfinance ships it; the only consumer normalizes it by its own
        trailing mean (see cross_sectional_patterns.py's turnover proxy),
        which is insensitive to level convention except transiently at
        split dates.

        A ticker is "missing" if its Close came back entirely empty —
        Close availability defines the ticker set, and open/volume are
        reindexed to close's exact index/columns so the three frames are
        always aligned (a ticker with Close but a sparse Open just carries
        NaN Opens, which the signal fns' own min-observation gates handle,
        rather than being dropped wholesale)."""
        try:
            raw = _call_with_retry(
                lambda: yf.download(
                    tickers,
                    start=start,
                    end=end,
                    auto_adjust=True,
                    progress=False,
                )
            )
        except Exception as exc:
            raise MarketDataError(f"Failed to fetch daily OHLCV data: {exc}") from exc

        if raw is None or raw.empty:
            # Same reasoning as get_price_history: a genuine connectivity
            # failure already raised above — an empty-but-successful
            # response means none of the requested tickers resolved.
            return {}, list(tickers)

        if isinstance(raw.columns, pd.MultiIndex):
            available_fields = set(raw.columns.get_level_values(0))
            if not set(DAILY_OHLCV_FIELDS).issubset(available_fields):
                raise MarketDataError(f"Unexpected daily OHLCV data shape for {tickers}")
            close = raw["Close"]
            open_ = raw["Open"]
            volume = raw["Volume"]
        else:
            # Some yfinance versions collapse to flat columns for a single
            # ticker — same defensive fallback get_price_history carries.
            if not set(DAILY_OHLCV_FIELDS).issubset(set(raw.columns)):
                raise MarketDataError(f"Unexpected daily OHLCV data shape for {tickers}")
            close = raw[["Close"]]
            close.columns = tickers
            open_ = raw[["Open"]]
            open_.columns = tickers
            volume = raw[["Volume"]]
            volume.columns = tickers

        # Close availability defines the result, mirroring
        # get_price_history's own cleaning exactly.
        close = close.dropna(axis=1, how="all")
        close = close.dropna(axis=0, how="all")
        if close.empty:
            return {}, list(tickers)

        aligned = {
            "open": open_.reindex(index=close.index, columns=close.columns),
            "close": close,
            "volume": volume.reindex(index=close.index, columns=close.columns),
        }
        missing = [t for t in tickers if t not in close.columns]
        return aligned, missing

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
