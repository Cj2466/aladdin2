"""Step A1.3 — WHOLE-MARKET US daily price panel ingest, from Alpaca into a
NEW, separate point-in-time store: backend/data/price_store_alpaca/.

SAFETY: this NEVER writes to backend/data/price_store/ (the existing
yfinance-sourced store LIVE forward-validation registrations read). It
constructs PriceStore(store_dir=ALPACA_STORE_DIR) explicitly, a fresh
directory this script owns end to end. Mixing two vendors into one
first-write-wins store would silently decide which vendor's prices a live
registration sees on any given (ticker, date) -- see price_store.py section 4
and the CLAUDE.md instruction this script was built under.

ADJUSTMENT CONVENTION: adjustment="raw". Verified in
probe_alpaca_adjustment_and_corp_actions.py (probe_results.json,
raw_matches_known_as_traded_fact=true): Alpaca's raw bars are ALREADY
as-traded (AAPL's raw close on 2020-08-28 is 499.23, exactly the price
that traded three days before the 2020-08-31 4-for-1 split -- the same fact
tests/test_price_store.py pins for the existing yfinance-sourced store).
This is UNLIKE yfinance's auto_adjust=False, which is split-adjusted
forward and needs price_store.to_as_traded's un-adjustment step. So this
script does NOT call to_as_traded -- it writes Alpaca's raw OHLCV straight
into the store's as-traded columns.

DIVIDEND / SPLIT COLUMNS: populated from data.alpaca.markets/v1/
corporate-actions, fetched in ONE bulk paginated walk over the whole
ingest window with no `symbols` filter (probed and confirmed to cover the
whole market per page, not one symbol -- see probe_results.json's
corporate_actions_bulk_no_symbol_filter). Only cash_dividends and
{forward,reverse}_splits are mapped onto the store's `dividend`/`split`
columns (the store has no column for mergers/spin-offs, matching the
existing yfinance-sourced store's own scope). A (ticker, date) with no
matching corporate-action record gets 0.0 in both columns -- this is not a
guess, it reflects "the bulk corporate-actions endpoint was actually asked
about this whole window and returned nothing for this symbol on this date."
Split ratio is stored as new_rate/old_rate (yfinance's own actions
encoding: >1.0 for a forward split, <1.0 for a reverse split, matching
price_store.py's `split` column convention and its
cumulative_split_factor()).

Resumable: reads/writes the store's own coverage ledger
(PriceStore.read_coverage / is_covered / record_coverage) exactly as the
existing store does, so a re-run skips any ticker already covered for
[START_DATE, END_DATE] and a Ctrl-C mid-run loses at most the batch in
flight (every completed batch is already flushed to disk by merge_ticker's
atomic writes before record_coverage is called for it).

Usage:
    ./venv/bin/python data/research_runs/whole_market_panel_2026-09-12/ingest_alpaca_whole_market.py
    ./venv/bin/python data/research_runs/whole_market_panel_2026-09-12/ingest_alpaca_whole_market.py --limit 500   # smoke test
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.market_data.alpaca_provider import (
    SYMBOLS_PER_REQUEST,
    AlpacaProvider,
)
from app.services.market_data.price_store import (
    STORE_COLUMNS,
    PriceStore,
    PriceStoreReport,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ingest_alpaca_whole_market")

OUT_DIR = Path(__file__).resolve().parent
UNIVERSE_CSV = OUT_DIR / "universe.csv"
INGEST_LOG_JSON = OUT_DIR / "ingest_run_log.json"
CORP_ACTIONS_CACHE = OUT_DIR / "corporate_actions_cache.json"

# NEW store, sibling to the existing data/price_store/ -- never the same
# directory. Routed the same way the existing store is (MAIN_CHECKOUT_
# BACKEND_DIR), so every worktree reads/writes the one shared copy.
from app.config import MAIN_CHECKOUT_BACKEND_DIR

ALPACA_STORE_DIR = MAIN_CHECKOUT_BACKEND_DIR / "data" / "price_store_alpaca" / "v1"

START_DATE = date(2016, 1, 4)


def last_complete_utc_day() -> date:
    """Alpaca 403s on any window touching the current UTC day (observed
    directly while building this script). The trading day is not final
    until it is over, so the safe end is yesterday UTC regardless of what
    time it is right now."""
    return datetime.now(UTC).date() - timedelta(days=1)


DATA_BASE_URL = "https://data.alpaca.markets"
CORP_ACTIONS_PAGE_LIMIT = 1000


def fetch_corporate_actions_bulk(api_key: str, api_secret: str, start: date, end: date) -> dict:
    """One paginated walk over [start, end] with NO symbols filter --
    probed to cover the whole market per page (probe_results.json). Returns
    {"cash_dividends": {(symbol, date_iso): rate}, "split": {(symbol,
    date_iso): ratio}}. Cached to CORP_ACTIONS_CACHE so a re-run does not
    re-ask; delete the cache file to force a refetch."""
    if CORP_ACTIONS_CACHE.exists():
        logger.info("loading cached corporate actions from %s", CORP_ACTIONS_CACHE)
        cached = json.loads(CORP_ACTIONS_CACHE.read_text())
        return {
            "dividends": {tuple(k.split("|")): v for k, v in cached["dividends"].items()},
            "splits": {tuple(k.split("|")): v for k, v in cached["splits"].items()},
        }

    dividends: dict[tuple[str, str], float] = {}
    splits: dict[tuple[str, str], float] = {}
    page_token: str | None = None
    pages = 0
    with httpx.Client(base_url=DATA_BASE_URL, timeout=60.0) as client:
        while True:
            params: dict[str, str | int] = {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": CORP_ACTIONS_PAGE_LIMIT,
            }
            if page_token is not None:
                params["page_token"] = page_token
            resp = client.get(
                "/v1/corporate-actions",
                params=params,
                headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret},
            )
            resp.raise_for_status()
            payload = resp.json()
            pages += 1
            ca = payload.get("corporate_actions", {})
            for row in ca.get("cash_dividends", []):
                symbol = row.get("symbol")
                ex_date = row.get("ex_date")
                rate = row.get("rate")
                if symbol and ex_date and rate is not None:
                    dividends[(symbol, ex_date)] = float(rate)
            for kind in ("forward_splits", "reverse_splits"):
                for row in ca.get(kind, []):
                    symbol = row.get("symbol")
                    ex_date = row.get("ex_date")
                    old_rate = row.get("old_rate")
                    new_rate = row.get("new_rate")
                    if symbol and ex_date and old_rate and new_rate:
                        splits[(symbol, ex_date)] = float(new_rate) / float(old_rate)
            page_token = payload.get("next_page_token")
            if pages % 10 == 0:
                logger.info(
                    "corporate-actions bulk fetch: %d pages, %d dividends, %d splits so far",
                    pages, len(dividends), len(splits),
                )
            if not page_token:
                break

    logger.info(
        "corporate-actions bulk fetch complete: %d pages, %d dividend records, %d split records",
        pages, len(dividends), len(splits),
    )
    CORP_ACTIONS_CACHE.write_text(
        json.dumps(
            {
                "dividends": {f"{k[0]}|{k[1]}": v for k, v in dividends.items()},
                "splits": {f"{k[0]}|{k[1]}": v for k, v in splits.items()},
            }
        )
    )
    return {"dividends": dividends, "splits": splits}


def build_store_frame(ticker: str, bars: pd.DataFrame, corp_actions: dict) -> pd.DataFrame:
    """bars: tz-aware America/New_York DatetimeIndex, columns
    open/high/low/close/volume (AlpacaProvider.get_stock_bars' shape,
    adjustment=raw i.e. already as-traded -- see module docstring).
    Returns a frame shaped like STORE_COLUMNS, tz-naive date index."""
    index = pd.DatetimeIndex(bars.index).tz_localize(None).normalize()
    out = pd.DataFrame(index=index)
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = bars[col].to_numpy()
    dividends = corp_actions["dividends"]
    splits = corp_actions["splits"]
    out["dividend"] = [dividends.get((ticker, d.strftime("%Y-%m-%d")), 0.0) for d in index]
    out["split"] = [splits.get((ticker, d.strftime("%Y-%m-%d")), 0.0) for d in index]
    out["capital_gains"] = 0.0
    out.index.name = "date"
    return out[list(STORE_COLUMNS)]


def load_universe_symbols(limit: int | None) -> list[str]:
    with UNIVERSE_CSV.open() as fh:
        symbols = [row["symbol"] for row in csv.DictReader(fh)]
    if limit is not None:
        symbols = symbols[:limit]
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only ingest the first N universe symbols (smoke test)")
    args = parser.parse_args()

    from app.config import settings

    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        raise SystemExit("ALPACA_API_KEY / ALPACA_API_SECRET not set in the environment")

    end_date = last_complete_utc_day()
    logger.info("ingest window: %s .. %s", START_DATE, end_date)
    logger.info("store dir: %s", ALPACA_STORE_DIR)

    symbols = load_universe_symbols(args.limit)
    logger.info("universe: %d symbols", len(symbols))

    corp_actions = fetch_corporate_actions_bulk(
        settings.alpaca_api_key, settings.alpaca_api_secret, START_DATE, end_date
    )

    store = PriceStore(store_dir=ALPACA_STORE_DIR)
    provider = AlpacaProvider(settings.alpaca_api_key, settings.alpaca_api_secret)

    coverage = store.read_coverage()
    to_fetch = [s for s in symbols if not PriceStore.is_covered(coverage, s, START_DATE, end_date)]
    already_covered = len(symbols) - len(to_fetch)
    logger.info("%d/%d symbols already covered by the ledger, %d to fetch", already_covered, len(symbols), len(to_fetch))

    report = PriceStoreReport()
    report.tickers_requested = len(symbols)
    zero_bar_symbols: list[str] = []
    error_symbols: list[str] = []
    processed = 0
    t_start = time.time()

    for chunk_start in range(0, len(to_fetch), SYMBOLS_PER_REQUEST):
        chunk = to_fetch[chunk_start : chunk_start + SYMBOLS_PER_REQUEST]
        try:
            bars_by_ticker, _missing = provider.get_stock_bars(
                chunk, "1Day", START_DATE, end_date, feed="sip", adjustment="raw"
            )
        except Exception:
            logger.exception("chunk starting at %s failed outright; will retry on next run", chunk[0])
            error_symbols.extend(chunk)
            processed += len(chunk)
            continue

        for ticker in chunk:
            bars = bars_by_ticker.get(ticker)
            if bars is None or bars.empty:
                zero_bar_symbols.append(ticker)
                continue
            frame = build_store_frame(ticker, bars, corp_actions)
            frame = PriceStore.drop_implausible(frame, report)
            if frame.empty:
                zero_bar_symbols.append(ticker)
                continue
            report.tickers_fetched += 1
            store.merge_ticker(ticker, frame, report)

        # Record coverage for the WHOLE requested chunk (including symbols
        # Alpaca returned nothing for): we genuinely asked about
        # [START_DATE, end_date] for each of these, so re-asking again
        # later without new information would be wasted work, not honesty.
        store.record_coverage(chunk, START_DATE, end_date)

        processed += len(chunk)
        if processed % 500 < SYMBOLS_PER_REQUEST:
            elapsed = time.time() - t_start
            logger.info(
                "progress: %d/%d fetched (%d already covered skipped), %s, elapsed %.0fs",
                processed, len(to_fetch), already_covered, report.describe(), elapsed,
            )

    logger.info("DONE. %s", report.describe())
    logger.info("zero-bar symbols: %d, hard-error symbols (retry next run): %d", len(zero_bar_symbols), len(error_symbols))

    INGEST_LOG_JSON.write_text(
        json.dumps(
            {
                "run_started_utc": datetime.now(UTC).isoformat(),
                "start_date": START_DATE.isoformat(),
                "end_date": end_date.isoformat(),
                "universe_symbols": len(symbols),
                "already_covered_before_run": already_covered,
                "attempted_this_run": len(to_fetch),
                "tickers_fetched": report.tickers_fetched,
                "rows_written": report.rows_written,
                "rows_already_present": report.rows_already_present,
                "rejected_rows": report.rejected_rows,
                "revisions": len(report.revisions),
                "basis_mismatches": len(report.basis_mismatches),
                "zero_bar_symbols_count": len(zero_bar_symbols),
                "zero_bar_symbols_sample": zero_bar_symbols[:50],
                "error_symbols": error_symbols,
                "elapsed_seconds": time.time() - t_start,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
