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
  * Keyless. Standard 12-element kline arrays (element count re-counted
    live 2026-08-29: 12); element [0] is openTime ms, [4] close, [7]
    quote-asset volume (USDT — genuine dollar turnover, unlike base
    volume in [5]), [6] closeTime, [8] trade count, [9] taker-buy BASE
    volume, [10] taker-buy QUOTE volume. limit max 1500 for this
    endpoint per the live doc; this provider requests 1500.
  * SIGNED VOLUME is therefore available from this one endpoint, with no
    tick data and no vendor: [10] is the buyer-initiated quote volume and
    [7] - [10] is the seller-initiated remainder. Both halves were
    reconciled EXACTLY against the raw /fapi/v1/aggTrades tape in this
    session — the arithmetic is shown in get_daily_klines' docstring
    rather than asserted here. Available back to each contract's
    inception, the same as [4] and [7].
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

THE EVER-LISTED ROSTER — TWO SOURCES, BOTH VERIFIED LIVE 2026-08-29,
because neither alone is survivorship-free:
GET https://fapi.binance.com/fapi/v1/exchangeInfo
  * Keyless, returns a DICT (not a list) with `symbols[]`; 882 entries
    today. Each carries `symbol`, `contractType`, `quoteAsset`, `status`
    and `onboardDate` (int ms). Counted live: 654 USDT-quoted
    contractType=PERPETUAL (524 TRADING, 129 SETTLING, 1 PENDING_TRADING)
    and 180 contractType=TRADIFI_PERPETUAL (underlyingType EQUITY /
    CN_EQUITY / KR_EQUITY / HK_EQUITY / COMMODITY / PREMARKET —
    tokenized-stock and metals perps, all onboarded 2025-12-11 or later).
  * SURVIVORSHIP HOLE, measured: SRMUSDT and LUNAUSDT are ABSENT — a
    delisted perp leaves exchangeInfo entirely even though its funding
    and kline history is still served. So this endpoint alone is a
    survivor-only roster and must never be used as "every symbol that
    ever existed".
GET https://s3-ap-northeast-1.amazonaws.com/data.binance.vision
    ?delimiter=/&prefix=data/futures/um/monthly/fundingRate/
  * Keyless S3 ListBucket XML (the HTML page at data.binance.vision is a
    JS shell over this same API). One <CommonPrefixes> entry per symbol
    that has ever had a UM (USDT-margined) funding-rate archive; paginate
    with `marker` while IsTruncated is true.
  * Counted live: 920 symbol directories, 833 of them USDT-quoted —
    including SRMUSDT, LUNAUSDT, FTTUSDT, COCOSUSDT and BUSD-era pairs.
    Only perpetuals have funding, so a fundingRate directory IS the marker
    of an ever-listed perp.
  * The survivorship gap, stated exactly (recounted live 2026-08-29 by the
    independent verification pass, which found the earlier wording of this
    paragraph overstated it): 180 archived USDT names are NOT in
    exchangeInfo's USDT PERPETUAL set — but 149 of those ARE in
    exchangeInfo, under contractType=TRADIFI_PERPETUAL (the tokenized
    equities, which this roster excludes anyway). Only 31 are absent from
    exchangeInfo ENTIRELY, and those 31 are the contracts the archive
    exists to recover. 31 is small; it is also exactly the set a
    survivor-only roster would delete, so the size is not the point.
  * The archive lags the live roster slightly (1 currently-live USDT perp,
    DOSUSDT, had no archive directory yet), which is why the roster below
    is the UNION of the two sources rather than either one.

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
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

FAPI_BASE_URL = "https://fapi.binance.com"

# The S3 ListBucket API behind data.binance.vision, and the prefix whose
# per-symbol directories enumerate every UM perp that ever had a funding
# archive — including delisted ones exchangeInfo has dropped. Both
# verified live 2026-08-29; see the module docstring.
BINANCE_VISION_LIST_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
BINANCE_VISION_UM_FUNDING_PREFIX = "data/futures/um/monthly/fundingRate/"
VISION_LIST_PAGE_LIMIT = 1000
VISION_MIN_SECONDS_BETWEEN_REQUESTS = 0.2

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

# The columns get_daily_klines returns, in order. Also the schema a cached
# klines CSV must satisfy to be reusable — see _read_cache's self-healing
# note: the last two were added 2026-08-29 and an older cache file lacks
# them, so it is refetched rather than read half-empty.
KLINE_COLUMNS: tuple[str, ...] = (
    "close",
    "quote_volume",
    "taker_buy_quote_volume",
    "trade_count",
)

# A cached file is fresh if its recorded fetch coverage reaches the
# requested end minus this many days.
CACHE_FRESH_DAYS = 3

DEFAULT_CACHE_DIR = Path("data") / "binance_futures"


class BinanceFuturesError(RuntimeError):
    """A fetch that failed after retries — never raised for an empty
    result, which is a real answer (unknown/never-listed symbol)."""


def _ms(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)


@dataclass(frozen=True)
class PerpRoster:
    """Every USDT-margined CRYPTO perpetual Binance has EVER listed, as far
    as its two public rosters can say — see get_usdt_perp_roster.

    `usdt_perp_symbols` is the union candidate list. The three other tuples
    exist so a caller can report the composition honestly instead of
    quoting one number: `live_symbols` are in exchangeInfo today,
    `archive_only_symbols` are the delisted ones only the data archive
    remembers, and `excluded_tradifi` are the tokenized-equity/commodity
    perps deliberately dropped. `onboard_dates` is exchangeInfo's declared
    onboardDate for live symbols ONLY — it is metadata for cross-checking,
    NOT the inception date a point-in-time universe should be built from
    (delisted symbols have none, so using it would reintroduce exactly the
    survivorship hole the archive closes)."""

    usdt_perp_symbols: tuple[str, ...]
    live_symbols: tuple[str, ...]
    archive_only_symbols: tuple[str, ...]
    excluded_tradifi: tuple[str, ...]
    onboard_dates: dict[str, date] = field(default_factory=dict)


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
        payload = self._get_payload(path, params, bucket, min_interval)
        if not isinstance(payload, list):
            # /fapi error bodies are {"code": ..., "msg": ...} — surface
            # them as failures, not as empty data.
            raise BinanceFuturesError(f"unexpected non-list response for {path}: {payload!r}")
        return payload

    def _get_payload(self, path: str, params: dict, bucket: str, min_interval: float) -> object:
        """The retrying/throttling GET, WITHOUT the list-shape assertion.
        Split out 2026-08-29 for /fapi/v1/exchangeInfo, which legitimately
        answers a dict; the two data endpoints keep their list contract via
        _get_json, which is the only caller that may relax to a bare
        payload."""
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
                #
                # -1122 "Invalid symbol status" is the SECOND permanent
                # no-data answer, found 2026-08-29 while sweeping the full
                # ever-listed roster: GAIBUSDT serves funding history
                # normally (first settlement 2026-04-13) but its klines
                # answer HTTP 400 / -1122 on every attempt, with or
                # without a time range — measured directly against the
                # production endpoint, not inferred. Exactly 1 of the 685
                # roster contracts answers -1122. Retrying it three times
                # and then raising would abort a whole roster sweep over
                # one contract's server-side state, so it is normalized to
                # "no data" like -1121.
                #
                # WHAT THE CONSUMER ACTUALLY SEES, recounted live by the
                # independent verification pass 2026-08-29 because the
                # first version of this comment got it wrong: a klines-only
                # 400 does NOT put the symbol in symbols_missing.
                # build_funding_carry_panels lists a symbol as missing only
                # when klines AND funding are both empty, so a contract
                # whose funding archive survives while its klines 400
                # becomes an ALL-NaN COLUMN instead. Five of the 685 are in
                # that state (GAIBUSDT on -1122; AERGOUSDT, BDXNUSDT,
                # BTCSTUSDT, SXPUSDT on -1121, each with 2.4k-6.2k real
                # funding settlements), and the point-in-time family
                # discloses them explicitly — see
                # cross_sectional_funding_carry_pit's residual limitations.
                if resp.status_code == 400:
                    try:
                        body = resp.json()
                    except ValueError:
                        body = {}
                    if isinstance(body, dict) and body.get("code") in (-1121, -1122):
                        return []
                resp.raise_for_status()
                return resp.json()
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

    def _read_cache(
        self,
        kind: str,
        symbol: str,
        end: date,
        required_columns: tuple[str, ...] = (),
    ) -> pd.DataFrame | None:
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
        # SCHEMA SELF-HEALING, added 2026-08-29 with the taker-buy columns:
        # a cache file written by an EARLIER version of this provider is
        # date-fresh but column-poor. Treating that as a miss refetches and
        # overwrites the same path, so an existing cache upgrades itself in
        # place rather than raising KeyError on a column that simply did not
        # exist when the file was written.
        if required_columns and not set(required_columns).issubset(frame.columns):
            return None
        return frame

    def _write_cache(self, kind: str, symbol: str, frame: pd.DataFrame, end: date) -> None:
        paths = self._cache_paths(kind, symbol)
        if paths is None:
            return
        csv_path, meta_path = paths
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(csv_path)
        meta_path.write_text(json.dumps({"fetched_through": end.isoformat()}))

    # -- the ever-listed roster ----------------------------------------------

    def list_vision_um_symbols(self) -> list[str]:
        """Every UM (USDT-margined) futures symbol that has a funding-rate
        directory in Binance's own public data archive — INCLUDING symbols
        delisted years ago, which is the whole point (see the module
        docstring's survivorship-hole note on exchangeInfo). Sorted,
        de-duplicated. Paginated with the S3 `marker` parameter."""
        symbols: list[str] = []
        marker = ""
        pattern = re.compile(
            r"<Prefix>" + re.escape(BINANCE_VISION_UM_FUNDING_PREFIX) + r"([^<]+)/</Prefix>"
        )
        while True:
            self._throttle("vision", VISION_MIN_SECONDS_BETWEEN_REQUESTS)
            resp = self._client.get(
                BINANCE_VISION_LIST_URL,
                params={
                    "delimiter": "/",
                    "prefix": BINANCE_VISION_UM_FUNDING_PREFIX,
                    "max-keys": VISION_LIST_PAGE_LIMIT,
                    "marker": marker,
                },
            )
            resp.raise_for_status()
            body = resp.text
            page = pattern.findall(body)
            symbols.extend(page)
            if "<IsTruncated>true</IsTruncated>" not in body:
                break
            next_marker = re.search(r"<NextMarker>([^<]*)</NextMarker>", body)
            if next_marker is not None and next_marker.group(1):
                marker = next_marker.group(1)
            elif page:
                marker = BINANCE_VISION_UM_FUNDING_PREFIX + page[-1] + "/"
            else:  # truncated with nothing parsed — refuse to spin
                break
        return sorted(set(symbols))

    def get_exchange_info_symbols(self) -> list[dict]:
        """/fapi/v1/exchangeInfo's `symbols` list, raw. SURVIVOR-ONLY —
        delisted contracts are absent (verified: SRMUSDT, LUNAUSDT). Used
        here for contract-type metadata and onboard dates, never as the
        historical roster."""
        payload = self._get_payload(
            "/fapi/v1/exchangeInfo", {}, bucket="klines", min_interval=KLINES_MIN_SECONDS_BETWEEN_REQUESTS
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            raise BinanceFuturesError(f"unexpected exchangeInfo payload: {type(payload).__name__}")
        return list(payload["symbols"])

    def get_usdt_perp_roster(self, end: date | None = None) -> PerpRoster:
        """THE ever-listed USDT-margined CRYPTO perpetual roster: the union
        of the archive's USDT-quoted symbols (which keeps the dead ones)
        and exchangeInfo's live USDT PERPETUAL symbols (which keeps names
        listed too recently to have an archive directory yet), MINUS
        contractType=TRADIFI_PERPETUAL — Binance's tokenized-equity and
        metals perps (XAUUSDT, TSLAUSDT, NVDAUSDT, ...), a different asset
        class that a crypto family must not silently absorb.

        This is a roster of contracts, not a point-in-time universe: WHEN
        each of these was tradeable is a separate question, answered from
        each symbol's own earliest/latest data rather than from any list.

        Cached to disk on the same freshness rule as the data endpoints —
        an hour-old roster is not worth a 2-request refetch, but a
        week-old one would miss new listings."""
        end = end if end is not None else date.today()  # noqa: DTZ011 — cache-freshness bound only
        cached = self._read_roster_cache(end)
        if cached is not None:
            return cached

        archive = [s for s in self.list_vision_um_symbols() if s.endswith("USDT")]
        info = self.get_exchange_info_symbols()
        tradifi = {
            s["symbol"] for s in info if s.get("contractType") == "TRADIFI_PERPETUAL"
        }
        live = {
            s["symbol"]
            for s in info
            if s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT"
        }
        onboard = {
            s["symbol"]: datetime.fromtimestamp(int(s["onboardDate"]) / 1000, tz=UTC).date()
            for s in info
            if s.get("onboardDate") and s["symbol"] in live
        }
        candidates = sorted((set(archive) | live) - tradifi)
        roster = PerpRoster(
            usdt_perp_symbols=tuple(candidates),
            live_symbols=tuple(sorted(live - tradifi)),
            archive_only_symbols=tuple(sorted(set(archive) - live - tradifi)),
            excluded_tradifi=tuple(sorted(tradifi)),
            onboard_dates=onboard,
        )
        self._write_roster_cache(roster, end)
        return roster

    def _roster_cache_path(self) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / "usdt_perp_roster.json"

    def _read_roster_cache(self, end: date) -> PerpRoster | None:
        path = self._roster_cache_path()
        if path is None or not path.exists():
            return None
        try:
            blob = json.loads(path.read_text())
            covered_through = date.fromisoformat(blob["fetched_through"])
            if (end - covered_through).days > CACHE_FRESH_DAYS:
                return None
            return PerpRoster(
                usdt_perp_symbols=tuple(blob["usdt_perp_symbols"]),
                live_symbols=tuple(blob["live_symbols"]),
                archive_only_symbols=tuple(blob["archive_only_symbols"]),
                excluded_tradifi=tuple(blob["excluded_tradifi"]),
                onboard_dates={k: date.fromisoformat(v) for k, v in blob["onboard_dates"].items()},
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _write_roster_cache(self, roster: PerpRoster, end: date) -> None:
        path = self._roster_cache_path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "fetched_through": end.isoformat(),
                    "usdt_perp_symbols": list(roster.usdt_perp_symbols),
                    "live_symbols": list(roster.live_symbols),
                    "archive_only_symbols": list(roster.archive_only_symbols),
                    "excluded_tradifi": list(roster.excluded_tradifi),
                    "onboard_dates": {k: v.isoformat() for k, v in roster.onboard_dates.items()},
                }
            )
        )

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
            # EMPTY STILL MEANS DATETIME-INDEXED. Found by the independent
            # verification pass 2026-08-29: a bare pd.Series(dtype=float)
            # carries a RangeIndex, so a no-funding symbol used to come
            # back int64-indexed on the FRESH path while the cached path
            # (_read_cache's pd.to_datetime) came back DatetimeIndex. The
            # two disagreed, which made the bug invisible behind a warm
            # cache; on a cold one, build_funding_carry_panels' funding-gap
            # tripwire (index.to_series().diff().dt) raised AttributeError:
            # "Can only use .dt accessor with datetimelike values", and any
            # concat of these series produced an object-dtype panel index.
            frame = pd.DataFrame(
                {"funding_rate": pd.Series(dtype=float)}, index=pd.DatetimeIndex([])
            )
        self._write_cache("funding", symbol, frame, end)
        return frame

    # -- daily klines --------------------------------------------------------

    def get_daily_klines(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Daily perp klines for `symbol`: a DataFrame indexed by the UTC
        calendar day (from openTime) with float columns `close`,
        `quote_volume`, `taker_buy_quote_volume` and `trade_count`.

        `quote_volume` is USDT turnover — element [7], the genuine dollar
        number; base volume [5] is deliberately not exposed so no caller
        can multiply it by price out of equity habit.

        `taker_buy_quote_volume` (element [10]) and `trade_count` (element
        [8]) were added 2026-08-29 for the cross-sectional ORDER-FLOW
        IMBALANCE family (cross_sectional_ofi.py), which documents the
        strategy-side reasoning. ADDITIVE: the two pre-existing columns
        keep their names, dtypes and semantics, so the funding-carry
        family (the only other caller) is untouched.

        THE SIGNED-VOLUME IDENTITY, VERIFIED LIVE 2026-08-29 IN THIS
        SESSION against the raw aggregate-trade tape (/fapi/v1/aggTrades),
        not assumed and not taken from documentation. For ADAUSDT's
        1-minute bar at 2026-08-28 22:56 UTC, reconstructing signed volume
        from every aggTrade in the window (a trade's "m" flag is
        isBuyerMaker, so m=False means the TAKER was the buyer —
        buyer-initiated — and m=True means the taker was the seller):
            element [10] takerBuyQuoteVolume == tape buyer-initiated quote
                volume  ->  33972.7421 == 33972.7421   EXACT
            element  [7] quoteVolume        == tape buy + sell quote
                volume  ->  42948.692  == 42948.692    EXACT
            element  [9] takerBuyBaseVolume == tape buyer-initiated base
                volume  ->  168173.0   == 168173.0     EXACT
            element  [5] volume             == tape total base volume
                        ->  212630.0   == 212630.0     EXACT
        The consequence every consumer depends on, and the reason this
        docstring shows the arithmetic rather than asserting it:
            SELLER-INITIATED quote volume = quote_volume - taker_buy_quote_volume
        which reproduced the tape's sell side exactly (8975.9499).
        A one-minute bar was used because /fapi/v1/aggTrades refuses any
        window older than two days ("Search window is restricted to recent
        2 days only", code -4166, measured) and a daily BTCUSDT bar is
        millions of trades; the identity is a per-bar accounting identity,
        so a bar small enough to reconcile tick-for-tick proves it.

        CAVEAT, measured in the same check and NOT a defect: element [8]
        (`trade_count`, 126 for that bar) is the RAW trade count, while the
        aggTrades tape returned 25 rows — aggTrades merges same-price,
        same-side, same-taker fills. The two are different quantities;
        `trade_count` is the raw one.

        Empty frame with those columns when the symbol never traded. Raw
        data: zero-volume zombie bars are returned as Binance serves them;
        market-or-not is the consumer's judgement (see module docstring).
        A zero-turnover bar makes the seller-initiated residual zero too,
        so consumers computing a log ratio must gate on turnover — the OFI
        family does."""
        cached = self._read_cache("klines_1d", symbol, end, required_columns=KLINE_COLUMNS)
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
                    "taker_buy_quote_volume": [float(r[10]) for r in rows],
                    "trade_count": [float(r[8]) for r in rows],
                },
                index=pd.to_datetime([int(r[0]) for r in rows], unit="ms").normalize(),
            ).sort_index()
            frame = frame[~frame.index.duplicated(keep="first")]
        else:
            # Same fix, and the one that actually mattered: five roster
            # contracts serve funding but 400 on klines (see the -1121/-1122
            # note above), so on a cold cache their RangeIndex-ed empty
            # close series poisoned pd.concat's index union and the whole
            # panel came back object-indexed — after which measure_breadth's
            # `index.year` raised AttributeError and the point-in-time run
            # could not complete at all. It only ever worked because the
            # cache was already warm from an earlier fetch pass.
            frame = pd.DataFrame(
                {c: pd.Series(dtype=float) for c in KLINE_COLUMNS}, index=pd.DatetimeIndex([])
            )
        self._write_cache("klines_1d", symbol, frame, end)
        return frame


__all__ = [
    "BINANCE_VISION_LIST_URL",
    "BINANCE_VISION_UM_FUNDING_PREFIX",
    "CACHE_FRESH_DAYS",
    "EARLIEST_FUNDING_START_MS",
    "FAPI_BASE_URL",
    "FUNDING_MIN_SECONDS_BETWEEN_REQUESTS",
    "KLINES_MIN_SECONDS_BETWEEN_REQUESTS",
    "KLINE_COLUMNS",
    "VISION_LIST_PAGE_LIMIT",
    "VISION_MIN_SECONDS_BETWEEN_REQUESTS",
    "BinanceFuturesError",
    "BinanceFuturesProvider",
    "PerpRoster",
]
