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
