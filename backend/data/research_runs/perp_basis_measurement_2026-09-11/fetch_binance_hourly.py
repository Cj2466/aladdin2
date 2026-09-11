"""Fetch hourly Binance SPOT and USDT-margined PERP klines for the perp-basis
descriptive measurement (see MEASUREMENT_2026-09-11.md). Keyless public
endpoints, no strategy logic here -- this script only fetches and caches raw
bars plus a per-file SHA-256 meta record.

Endpoints (both keyless, verified live 2026-09-11 by this script's own first
run -- HTTP 200 with the documented row shape):
  spot: GET https://api.binance.com/api/v3/klines
  perp: GET https://fapi.binance.com/fapi/v1/klines
Both take symbol, interval, startTime (ms, inclusive), endTime (ms,
inclusive), limit. Spot's documented max `limit` for /api/v3/klines is 1000;
perp's /fapi/v1/klines documented max is 1500 (see
app/services/market_data/binance_futures_provider.py's module docstring,
verified live 2026-08-29 in this repo) -- this script requests 1000 for both
so one paging loop serves both markets identically.

Throttle/retry conventions mirror BinanceFuturesProvider
(app/services/market_data/binance_futures_provider.py): a minimum interval
between requests enforced from a monotonic clock, per-endpoint-bucket so spot
and perp budgets don't cross-throttle each other, exponential jittered
backoff on 429/418/5xx, and a symbol that the venue never listed (400,
code -1121 "Invalid symbol") is treated as a real "no data" answer, not
retried.

Kline element layout (12-element array), both endpoints, re-checked live this
run: [0] openTime ms, [1] open, [2] high, [3] low, [4] close, [5] volume,
[6] closeTime, [7] quoteAssetVolume, [8] numberOfTrades, [9] takerBuyBaseVol,
[10] takerBuyQuoteVol, [11] ignore. This script keeps only close ([4]) --
descriptive measurement of the basis needs closes only, ln F and ln S at the
same hour, per the paper's Eq. (8) (perpetual_futures_fundamentals.txt,
line ~935).

Output: one CSV per (market, symbol) under --out-dir (default the MAIN
checkout's backend/data/binance_hourly/, gitignored -- see backend/.gitignore),
plus a sidecar <name>.meta.json with rows, first, last timestamp, fetch time
(UTC), and the CSV's own SHA-256 so a later run can prove whether the file
changed underneath it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd

# Make `import app.config` work whether this script is run with backend/ as
# the cwd (as the README-style instructions here assume) or from elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # .../backend
from app.config import MAIN_CHECKOUT_BACKEND_DIR

SPOT_BASE_URL = "https://api.binance.com"
PERP_BASE_URL = "https://fapi.binance.com"

SPOT_PATH = "/api/v3/klines"
PERP_PATH = "/fapi/v1/klines"

PAGE_LIMIT = 1000  # <= spot's documented max (1000); well under perp's (1500)

# Deliberate margin under the documented per-IP budgets, same register as
# BinanceFuturesProvider's KLINES_MIN_SECONDS_BETWEEN_REQUESTS (0.2s there
# for perp weight-10 requests against a 2400/min budget). Spot's
# /api/v3/klines is weight 2 against a 6000/min (1200/min per some docs)
# request-weight budget depending on tier; 0.25s spacing is a conservative
# floor for a keyless IP-limited caller on either market.
MIN_SECONDS_BETWEEN_REQUESTS = 0.25
RETRY_ATTEMPTS = 5
RETRY_BASE_DELAY_SECONDS = 1.0

PAPER_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT"]

# The 20 largest OTHER Binance USDT perps by trailing-30-day (2026-07-30 ..
# 2026-08-28 inclusive, 30 calendar days) median daily quote_volume
# (dollar turnover), computed from this repo's existing daily-kline cache
# (backend/data/binance_futures/klines_1d_*.csv, fetched through 2026-08-29
# by BinanceFuturesProvider) -- see MEASUREMENT_2026-09-11.md section 2 for
# the ranked table of all 59 candidates and the exact medians.
ALT_SYMBOLS = [
    "SOLUSDT", "XRPUSDT", "ZECUSDT", "LINKUSDT", "UNIUSDT",
    "NEARUSDT", "AVAXUSDT", "AAVEUSDT", "FILUSDT", "BCHUSDT",
    "TRXUSDT", "LTCUSDT", "XMRUSDT", "XLMUSDT", "DOTUSDT",
    "CRVUSDT", "HBARUSDT", "ICPUSDT", "ETCUSDT", "ATOMUSDT",
]

ALL_SYMBOLS = PAPER_SYMBOLS + ALT_SYMBOLS

DEFAULT_OUT_DIR = MAIN_CHECKOUT_BACKEND_DIR / "data" / "binance_hourly"


class FetchError(RuntimeError):
    pass


@dataclass
class _Throttle:
    last_at: dict[str, float]

    def wait(self, bucket: str, min_interval: float) -> None:
        last = self.last_at.get(bucket)
        now = time.monotonic()
        if last is not None:
            remaining = min_interval - (now - last)
            if remaining > 0:
                time.sleep(remaining)
        self.last_at[bucket] = time.monotonic()


def _get_klines_page(
    client: httpx.Client,
    base_url: str,
    path: str,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    throttle: _Throttle,
    bucket: str,
) -> list[list] | None:
    """Returns the page (possibly empty list) or None for a permanent
    "never listed" answer (HTTP 400, code -1121/-1122)."""
    last_error: Exception | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        throttle.wait(bucket, MIN_SECONDS_BETWEEN_REQUESTS)
        try:
            resp = client.get(
                base_url + path,
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": start_ms,
                    "endTime": end_ms,
                    "limit": PAGE_LIMIT,
                },
            )
            if resp.status_code == 400:
                try:
                    body = resp.json()
                except ValueError:
                    body = {}
                if isinstance(body, dict) and body.get("code") in (-1121, -1122):
                    return None
            if resp.status_code in (429, 418):
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                print(f"  [{symbol}] HTTP {resp.status_code}, sleeping {delay:.1f}s", file=sys.stderr)
                time.sleep(delay + random.uniform(0, 1))
                continue
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, list):
                raise FetchError(f"unexpected non-list response for {symbol}: {payload!r}")
            return payload
        except FetchError:
            raise
        except Exception as exc:  # noqa: BLE001 - transient network/5xx; last attempt re-raises
            last_error = exc
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 1))
    raise FetchError(f"failed after {RETRY_ATTEMPTS} attempts: {symbol} {path}") from last_error


def fetch_symbol_hourly(
    client: httpx.Client,
    base_url: str,
    path: str,
    symbol: str,
    start_ms: int,
    end_ms: int,
    throttle: _Throttle,
    bucket: str,
) -> pd.DataFrame:
    """Hourly klines for `symbol` from start_ms to end_ms inclusive.
    Returns a DataFrame indexed by UTC hour-open timestamp with a single
    `close` column (float). Empty (but correctly typed) frame if the venue
    never listed this symbol on this market."""
    rows: list[list] = []
    cursor = start_ms
    page_count = 0
    while cursor <= end_ms:
        page = _get_klines_page(
            client, base_url, path, symbol, "1h", cursor, end_ms, throttle, bucket
        )
        page_count += 1
        if page_count % 10 == 0:
            print(f"    [{bucket}/{symbol}] page {page_count}, {len(rows)} rows so far", file=sys.stderr, flush=True)
        if page is None:
            return pd.DataFrame({"close": pd.Series(dtype=float)}, index=pd.DatetimeIndex([], name="open_time"))
        if not page:
            break
        rows.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        cursor = int(page[-1][0]) + 1

    if not rows:
        return pd.DataFrame({"close": pd.Series(dtype=float)}, index=pd.DatetimeIndex([], name="open_time"))

    frame = pd.DataFrame(
        {"close": [float(r[4]) for r in rows]},
        index=pd.to_datetime([int(r[0]) for r in rows], unit="ms", utc=True).tz_localize(None),
    )
    frame.index.name = "open_time"
    frame = frame[~frame.index.duplicated(keep="first")].sort_index()
    return frame


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_symbol(out_dir: Path, market: str, symbol: str, frame: pd.DataFrame) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{market}_{symbol}.csv"
    meta_path = out_dir / f"{market}_{symbol}.meta.json"
    frame.to_csv(csv_path)
    sha = _sha256_of(csv_path)
    meta = {
        "symbol": symbol,
        "market": market,
        "rows": len(frame),
        "first": frame.index.min().isoformat() if len(frame) else None,
        "last": frame.index.max().isoformat() if len(frame) else None,
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "sha256": sha,
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--symbols", nargs="*", default=ALL_SYMBOLS,
        help="Symbols to fetch (default: the 5 paper coins + 20 largest alts)",
    )
    parser.add_argument(
        "--start", default="2019-01-01T00:00:00",
        help="Earliest hour to request (ISO, UTC). Each symbol's actual first "
        "bar depends on when Binance listed it; requesting before listing "
        "just returns fewer rows, not an error.",
    )
    parser.add_argument(
        "--end", default=None,
        help="Latest hour to request (ISO, UTC). Default: the last fully "
        "closed UTC hour as of run time.",
    )
    args = parser.parse_args()

    start_dt = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    if args.end is not None:
        end_dt = datetime.fromisoformat(args.end).replace(tzinfo=UTC)
    else:
        now = datetime.now(UTC)
        end_dt = now.replace(minute=0, second=0, microsecond=0) - pd.Timedelta(hours=1)

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000) + 3_600_000 - 1  # inclusive through end-of-hour

    print(f"Fetching hourly klines {start_dt.isoformat()} .. {end_dt.isoformat()} "
          f"for {len(args.symbols)} symbols x 2 markets -> {args.out_dir}")

    throttle = _Throttle(last_at={})
    summary = []
    with httpx.Client(timeout=30.0) as client:
        for symbol in args.symbols:
            for market, base_url, path, bucket in (
                ("spot", SPOT_BASE_URL, SPOT_PATH, "spot"),
                ("perp", PERP_BASE_URL, PERP_PATH, "perp"),
            ):
                frame = fetch_symbol_hourly(
                    client, base_url, path, symbol, start_ms, end_ms, throttle, bucket
                )
                meta = _write_symbol(args.out_dir, market, symbol, frame)
                summary.append(meta)
                print(f"  {market:4s} {symbol:10s} rows={meta['rows']:>6d} "
                      f"first={meta['first']} last={meta['last']}", flush=True)

    (args.out_dir / "_fetch_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"Done. Summary written to {args.out_dir / '_fetch_summary.json'}")


if __name__ == "__main__":
    main()
