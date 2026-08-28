"""Keyless, throttled, retrying, disk-caching fetcher for Binance
USDT-margined perpetual-futures PUBLIC market data: funding-rate history
and daily klines. Built 2026-08-29 for the funding-rate carry family
(cross_sectional_funding_carry.py), which documents the strategy-side
reasoning; this module documents only the data facts.

EVERY CLAIM BELOW WAS VERIFIED LIVE 2026-08-29 IN THIS SESSION by direct
request against the production endpoint, not recalled from memory and not
taken from the earlier scoping pass's notes:

GET https://fapi.binance.com/fapi/v1/fundingRate
  * Keyless. Params: symbol, startTime (ms, inclusive), endTime (ms,
    inclusive), limit (default 100, max 1000) — parameter semantics
    cross-checked against the published endpoint doc, fetched live
    (developers.binance.com, "Get Funding Rate History").
  * Response rows: {"symbol", "fundingTime" (int ms — sometimes with a
    few ms of jitter, e.g. ...0013), "fundingRate" (str),
    "markPrice" (str, EMPTY STRING for old rows — 2019 BTCUSDT rows have
    ""), "rateType" ("Regular" observed; docs also list "Special")}.
  * BTCUSDT's earliest row is fundingTime=1568102400000 = 2019-09-10
    08:00 UTC. History is served in full for the whole life of a symbol.
  * QUIRK, measured: startTime=0 is treated as ABSENT (the endpoint
    returns the MOST RECENT rows), while an explicit early epoch
    (2015-01-01) correctly returns the true earliest rows. This provider
    therefore never passes 0; see EARLIEST_FUNDING_START_MS.
  * DELISTED symbols still serve their full funding history even though
    they no longer appear in /fapi/v1/exchangeInfo at all (verified:
    SRMUSDT and LUNAUSDT both answer; LUNAUSDT's May-2022 rows show
    funding pinned at -0.75%/-1.0% per 8h through the Terra collapse).
    An unknown symbol returns [] with HTTP 200, not an error — so "no
    data" is a real answer this provider passes through, never a retry.
  * RATE LIMIT, quoted verbatim from the endpoint doc fetched live:
    "share 500/5min/IP rate limit with GET /fapi/v1/fundingInfo".
    FUNDING_MIN_SECONDS_BETWEEN_REQUESTS spaces funding requests so a
    sustained fetch stays under that budget with margin (300s / 0.65s
    ~= 461 requests per 5 minutes worst case).

GET https://fapi.binance.com/fapi/v1/klines  (interval=1d)
  * Keyless. Standard 12-element kline arrays; element [0] is openTime
    ms, [4] close, [7] quote-asset volume (USDT — genuine dollar
    turnover, unlike base volume in [5]), [6] closeTime. limit max 1500
    for this endpoint per the live doc; this provider requests 1500.
  * BTCUSDT perp daily klines begin 1567900800000 = 2019-09-08. Unlike
    fundingRate, startTime=0 here DOES return the earliest rows —
    verified — but this provider passes an explicit epoch anyway so both
    endpoints share one convention.
  * Delisted symbols serve klines too (LUNAUSDT: 2021-01-28 through the
    2022-05-12 collapse bar, plus a final zero-volume bar). Zero-volume
    bars are returned as data; the CONSUMER decides whether a
    zero-turnover print is a market (the carry family treats it as not).
  * Whole-endpoint IP weight budget: exchangeInfo.rateLimits (fetched
    live) says REQUEST_WEIGHT 2400/min; the doc's per-request weight for
    limit>1000 is 10. KLINES_MIN_SECONDS_BETWEEN_REQUESTS keeps a bulk
    fetch far under that.

FUNDING INTERVALS ARE NOT UNIFORMLY 8 HOURS. /fapi/v1/fundingInfo
(fetched live 2026-08-29) lists 441 symbols on a 4h interval, 324 on 8h,
2 on 1h, with adjustedFundingRateCap/Floor of +/-2% per period on the
sampled entries. Consumers must therefore SUM the funding events that
actually settled in a window, never multiply an average rate by an
assumed 3-events-per-day. This provider returns raw per-event rows and
leaves aggregation to the consumer for exactly that reason.

Retry/throttle conventions mirror edgar_xbrl_provider.EdgarXbrlProvider
(this project's httpx precedent): a minimum interval between requests
enforced from a monotonic clock, exponential jittered backoff on
transient failures, and injectable sleep/clock so tests never really
wait. Disk cache: one CSV per (symbol, kind) plus a sidecar meta JSON
recording the end date the fetch covered — a cached file is reused only
when its recorded coverage reaches the requested end minus
CACHE_FRESH_DAYS, so a stale cache refreshes itself and a dead symbol's
cache (whose data can never reach a recent end date) is simply refetched
in full, which is cheap because its history is bounded."""

from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

FAPI_BASE_URL = "https://fapi.binance.com"

# See module docstring: fundingRate shares a 500-requests-per-5-minutes
# budget with fundingInfo (quoted from the live doc). 0.65s spacing is
# ~461 requests per 5 minutes flat out — under the ceiling rather than at
# it, the same deliberate-margin register as EDGAR's 0.13s vs 10/s.
FUNDING_MIN_SECONDS_BETWEEN_REQUESTS = 0.65

# Klines are charged against the 2400-weight/min IP budget at weight 10
# per limit=1500 request; 0.2s spacing is at most 300 weight/min from
# this provider — an order of magnitude under the ceiling.
KLINES_MIN_SECONDS_BETWEEN_REQUESTS = 0.2

# Same shape and register as yfinance_provider._call_with_retry and the
# EDGAR provider: small attempt count, exponential backoff with jitter.
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0

# 2019-01-01 00:00 UTC — safely before Binance futures existed (BTCUSDT,
# the first USDT perp, starts 2019-09). Used instead of 0 because the
# fundingRate endpoint treats startTime=0 as absent (measured — see the
# module docstring), which silently returns the WRONG (most recent) page.
EARLIEST_FUNDING_START_MS = 1546300800000

FUNDING_PAGE_LIMIT = 1000  # documented max for /fapi/v1/fundingRate
KLINES_PAGE_LIMIT = 1500  # documented max for /fapi/v1/klines

# A cached file is fresh if its recorded fetch coverage reaches the
# requested end minus this many days.
CACHE_FRESH_DAYS = 3

DEFAULT_CACHE_DIR = Path("data") / "binance_futures"


class BinanceFuturesError(RuntimeError):
    """A fetch that failed after retries — never raised for an empty
    result, which is a real answer (unknown/never-listed symbol)."""


def _ms(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)


class BinanceFuturesProvider:
    """Throttled, retrying, disk-caching client for the two endpoints in
    the module docstring. `sleep` and `clock` are injectable so tests can
    drive the throttle without real waiting — the same reason the EDGAR
    provider resolves them at construction time."""

    def __init__(
        self,
        cache_dir: Path | str | None = DEFAULT_CACHE_DIR,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        client: httpx.Client | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: dict[str, float] = {}
        self._client = (
            client
            if client is not None
            else httpx.Client(base_url=FAPI_BASE_URL, timeout=30.0)
        )

    # -- plumbing ------------------------------------------------------------

    def _throttle(self, bucket: str, min_interval: float) -> None:
        """Per-BUCKET spacing, not global: fundingRate's 500/5min budget
        (shared with fundingInfo) is separate from the weight budget
        klines draw on, so interleaving the two kinds of request must not
        let one bucket's spacing satisfy the other's."""
        last = self._last_request_at.get(bucket)
        if last is not None:
            remaining = min_interval - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at[bucket] = self._clock()

    def _get_json(self, path: str, params: dict, bucket: str, min_interval: float) -> list:
        last_error: Exception | None = None
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            self._throttle(bucket, min_interval)
            try:
                resp = self._client.get(path, params=params)
                # A symbol Binance never listed: fundingRate answers []
                # with HTTP 200, but klines answers HTTP 400 with body
                # {"code": -1121, "msg": "Invalid symbol."} — verified
                # live 2026-08-29 on AMPUSDT (no Binance USDT perp ever
                # existed) and on a nonsense symbol. Same real answer,
                # different wire shape; normalize both to "no data", and
                # never retry it (retrying cannot invent a listing).
                if resp.status_code == 400:
                    try:
                        body = resp.json()
                    except ValueError:
                        body = {}
                    if isinstance(body, dict) and body.get("code") == -1121:
                        return []
                resp.raise_for_status()
                payload = resp.json()
                if not isinstance(payload, list):
                    # /fapi error bodies are {"code": ..., "msg": ...} —
                    # surface them as failures, not as empty data.
                    raise BinanceFuturesError(f"unexpected non-list response for {path}: {payload!r}")
                return payload
            except BinanceFuturesError:
                raise
            except Exception as exc:  # noqa: BLE001 — transient network/429/5xx; last attempt re-raises below
                last_error = exc
                if attempt < RETRY_ATTEMPTS:
                    self._sleep(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 1))
        raise BinanceFuturesError(
            f"failed after {RETRY_ATTEMPTS} attempts: {path} params={params}"
        ) from last_error

    def _cache_paths(self, kind: str, symbol: str) -> tuple[Path, Path] | None:
        if self.cache_dir is None:
            return None
        base = self.cache_dir / f"{kind}_{symbol}"
        return base.with_suffix(".csv"), base.with_suffix(".meta.json")

    def _read_cache(self, kind: str, symbol: str, end: date) -> pd.DataFrame | None:
        paths = self._cache_paths(kind, symbol)
        if paths is None:
            return None
        csv_path, meta_path = paths
        if not (csv_path.exists() and meta_path.exists()):
            return None
        try:
            meta = json.loads(meta_path.read_text())
            covered_through = date.fromisoformat(meta["fetched_through"])
        except (KeyError, ValueError, json.JSONDecodeError):
            return None
        if (end - covered_through).days > CACHE_FRESH_DAYS:
            return None
        frame = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        return frame

    def _write_cache(self, kind: str, symbol: str, frame: pd.DataFrame, end: date) -> None:
        paths = self._cache_paths(kind, symbol)
        if paths is None:
            return
        csv_path, meta_path = paths
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(csv_path)
        meta_path.write_text(json.dumps({"fetched_through": end.isoformat()}))

    # -- funding -------------------------------------------------------------

    def get_funding_history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Every funding settlement for `symbol` with start <= settlement
        date <= end: a DataFrame indexed by the settlement's UTC timestamp
        (tz-naive, UTC by construction) with one float column
        `funding_rate` (decimal per period, e.g. 0.0001 = 1bp per
        interval). Empty frame (with that column) when the symbol has no
        funding history at all in the range — a real answer, see the
        module docstring. Paginated by advancing startTime past the last
        row until a short page arrives."""
        cached = self._read_cache("funding", symbol, end)
        if cached is not None:
            cached.index = pd.to_datetime(cached.index)
            return cached

        start_ms = max(_ms(start), EARLIEST_FUNDING_START_MS)
        end_ms = _ms(end) + 86_400_000 - 1  # inclusive through end-of-day
        rows: list[dict] = []
        cursor = start_ms
        while cursor <= end_ms:
            page = self._get_json(
                "/fapi/v1/fundingRate",
                {"symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": FUNDING_PAGE_LIMIT},
                bucket="funding",
                min_interval=FUNDING_MIN_SECONDS_BETWEEN_REQUESTS,
            )
            if not page:
                break
            rows.extend(page)
            if len(page) < FUNDING_PAGE_LIMIT:
                break
            cursor = int(page[-1]["fundingTime"]) + 1

        if rows:
            frame = pd.DataFrame(
                {
                    "funding_rate": [float(r["fundingRate"]) for r in rows],
                },
                index=pd.to_datetime([int(r["fundingTime"]) for r in rows], unit="ms"),
            ).sort_index()
            # Defensive de-dup: pagination advances past the last row, so
            # duplicates should be impossible; keep-first makes that an
            # invariant rather than an assumption.
            frame = frame[~frame.index.duplicated(keep="first")]
        else:
            frame = pd.DataFrame({"funding_rate": pd.Series(dtype=float)})
        self._write_cache("funding", symbol, frame, end)
        return frame

    # -- daily klines --------------------------------------------------------

    def get_daily_klines(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Daily perp klines for `symbol`: a DataFrame indexed by the UTC
        calendar day (from openTime) with float columns `close` and
        `quote_volume` (USDT turnover — element [7], the genuine dollar
        number; base volume [5] is deliberately not exposed so no caller
        can multiply it by price out of equity habit). Empty frame with
        those columns when the symbol never traded. Raw data: zero-volume
        zombie bars are returned as Binance serves them; market-or-not is
        the consumer's judgement (see module docstring)."""
        cached = self._read_cache("klines_1d", symbol, end)
        if cached is not None:
            cached.index = pd.to_datetime(cached.index)
            return cached

        start_ms = max(_ms(start), EARLIEST_FUNDING_START_MS)
        end_ms = _ms(end) + 86_400_000 - 1
        rows: list[list] = []
        cursor = start_ms
        while cursor <= end_ms:
            page = self._get_json(
                "/fapi/v1/klines",
                {
                    "symbol": symbol,
                    "interval": "1d",
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": KLINES_PAGE_LIMIT,
                },
                bucket="klines",
                min_interval=KLINES_MIN_SECONDS_BETWEEN_REQUESTS,
            )
            if not page:
                break
            rows.extend(page)
            if len(page) < KLINES_PAGE_LIMIT:
                break
            cursor = int(page[-1][0]) + 1

        if rows:
            frame = pd.DataFrame(
                {
                    "close": [float(r[4]) for r in rows],
                    "quote_volume": [float(r[7]) for r in rows],
                },
                index=pd.to_datetime([int(r[0]) for r in rows], unit="ms").normalize(),
            ).sort_index()
            frame = frame[~frame.index.duplicated(keep="first")]
        else:
            frame = pd.DataFrame(
                {"close": pd.Series(dtype=float), "quote_volume": pd.Series(dtype=float)}
            )
        self._write_cache("klines_1d", symbol, frame, end)
        return frame


__all__ = [
    "CACHE_FRESH_DAYS",
    "EARLIEST_FUNDING_START_MS",
    "FAPI_BASE_URL",
    "FUNDING_MIN_SECONDS_BETWEEN_REQUESTS",
    "KLINES_MIN_SECONDS_BETWEEN_REQUESTS",
    "BinanceFuturesError",
    "BinanceFuturesProvider",
]
