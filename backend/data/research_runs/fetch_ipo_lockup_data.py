"""Build data/ipo_lockup/ — every external input the ipo_lockup_expiration
family needs, frozen to disk so the screen itself makes NO network call.

Run from backend/ with the venv:

    ./venv/bin/python data/research_runs/fetch_ipo_lockup_data.py

Four artifacts, in this order:

  1. data/ipo_lockup/IPO-age.xlsx
     Jay R. Ritter (Warrington College of Business, University of Florida),
     https://site.warrington.ufl.edu/ritter/files/IPO-age.xlsx — the IPO
     universe. Committed, so the run reproduces without the network.

  2. data/ipo_lockup/sec_company_tickers.json
     https://www.sec.gov/files/company_tickers.json — the free ticker->CIK
     master file, used for identity gate G1. Committed. NOTE, and this is the
     point of the pre-registration's section 5.4: this file is CURRENT-ONLY and
     is NOT sufficient for identity resolution on its own. It maps CNOB to CIK
     712771 titled "ConnectOne Bancorp, Inc.", which name-matches Ritter's 2013
     ConnectOne IPO row and is wrong — 712771 is Center Bancorp's registrant,
     which survived the 2014 merger and took the symbol. G1 is informational;
     G2 (the first-trade anchor, in the family module) is what actually
     excludes.

  3. data/ipo_lockup/price_store/
     A FAMILY-LOCAL PriceStore (app/services/market_data/price_store.py) of
     as-traded OHLCV + corporate actions for every filtered universe ticker
     plus SPY. Family-local rather than the shared store at data/price_store/
     because this universe is ~1,200 small-cap names that no other family
     trades, and because a fixed historical window in a committed store makes
     the screen bit-reproducible (a fully-covered window makes no network call
     at all — see PriceStore._stored_rows).

  4. data/ipo_lockup/ticker_info.json
     yfinance's own `.info` longName / shortName / quoteType for every ticker
     that returned any price rows — identity gate G3. Fetched here rather than
     in the screen because it is one slow HTTP call per ticker.
     YFinanceProvider.get_ticker_metadata deliberately does not expose
     longName/quoteType (it returns sector/industry/asset_class/currency), so
     this script reads yf.Ticker(...).info directly rather than widening a
     provider contract four other families depend on.

Idempotent: re-running skips downloads whose file already exists (pass
--refresh to force) and the price fetch replays from the store for any window
already covered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv, whose site-packages
# resolves `app` to the MAIN worktree's backend/app. Without the lines below
# this script silently populates another checkout's data directory.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The fetch would have written into another checkout."
    )

import yfinance as yf

from app.services.market_data.price_store import PriceStore
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.ipo_lockup_expiration import (
    BENCHMARK_TICKER,
    IPO_LOCKUP_DIR,
    PRICE_STORE_DIR,
    RITTER_IPO_AGE_PATH,
    SEC_COMPANY_TICKERS_PATH,
    TICKER_INFO_PATH,
    UNIVERSE_END_YEAR,
    UNIVERSE_START_YEAR,
    filter_universe,
    load_ritter_universe,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout
)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger("ipo_lockup_fetch")

RITTER_IPO_AGE_URL = "https://site.warrington.ufl.edu/ritter/files/IPO-age.xlsx"
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# SEC asks automated clients to identify themselves; Ritter's server rejects a
# bare urllib default UA.
UA_RITTER = {"User-Agent": "Mozilla/5.0 (aladdin2 research; academic replication)"}
UA_SEC = {"User-Agent": "aladdin2 research autoa0792@gmail.com"}

# The price window fetched per IPO COHORT YEAR, as offsets in whole years/months
# around that year. It must cover, for every offer date in the cohort:
#   * six months BEFORE the earliest offer date  -> identity gate G2 needs to
#     see any earlier holder of the symbol;
#   * offer date + 240 calendar days + 1 trading day -> the placebo arm's own
#     event window is the furthest-out thing measured.
# Batching by cohort year turns ~1,200 single-ticker requests into 8, which
# matters because each request is a network round trip.
COHORT_FETCH_START = (-1, 7, 1)  # (year offset, month, day) -> July 1 of Y-1
COHORT_FETCH_END = (2, 1, 1)  # January 1 of Y+2


def _download(url: str, dest: Path, headers: dict[str, str], refresh: bool) -> None:
    if dest.exists() and not refresh:
        logger.info("%s already present (%d bytes) — skipping download", dest.name, dest.stat().st_size)
        return
    logger.info("downloading %s -> %s", url, dest)
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    logger.info(
        "wrote %s (%d bytes, sha256 %s)", dest.name, len(payload), hashlib.sha256(payload).hexdigest()
    )


def fetch_prices(refresh: bool) -> dict[str, int]:
    rows = load_ritter_universe()
    universe, counts = filter_universe(rows)
    logger.info("universe filter: %s", counts.as_dict())

    store = PriceStore(store_dir=PRICE_STORE_DIR)
    provider = YFinanceProvider(price_store=store)

    by_year: dict[int, list[str]] = {}
    for row in universe:
        by_year.setdefault(row.offer_date.year, []).append(row.ticker)

    stats = {"cohorts": 0, "tickers_requested": 0, "tickers_with_rows": 0}
    for year in sorted(by_year):
        tickers = sorted(set(by_year[year]))
        start = date(year + COHORT_FETCH_START[0], COHORT_FETCH_START[1], COHORT_FETCH_START[2])
        end = date(year + COHORT_FETCH_END[0], COHORT_FETCH_END[1], COHORT_FETCH_END[2])
        logger.info("cohort %d: %d tickers, window %s..%s", year, len(tickers), start, end)
        began = time.time()
        _frame, missing = provider.get_price_history(tickers, start, end)
        stats["cohorts"] += 1
        stats["tickers_requested"] += len(tickers)
        stats["tickers_with_rows"] += len(tickers) - len(missing)
        logger.info(
            "cohort %d done in %.1fs: %d/%d tickers returned rows",
            year,
            time.time() - began,
            len(tickers) - len(missing),
            len(tickers),
        )

    # The benchmark, over the union of every cohort's window.
    bench_start = date(UNIVERSE_START_YEAR + COHORT_FETCH_START[0], *COHORT_FETCH_START[1:])
    bench_end = date(UNIVERSE_END_YEAR + COHORT_FETCH_END[0], *COHORT_FETCH_END[1:])
    logger.info("benchmark %s: %s..%s", BENCHMARK_TICKER, bench_start, bench_end)
    provider.get_price_history([BENCHMARK_TICKER], bench_start, bench_end)
    return stats


def fetch_ticker_info(refresh: bool) -> dict[str, int]:
    """Identity gate G3's input: longName / shortName / quoteType per ticker.

    Only tickers that actually returned price rows are queried — a ticker with
    no rows is already excluded by G2 and its `.info` would tell us nothing
    about the row we dropped."""
    existing: dict[str, dict] = {}
    if TICKER_INFO_PATH.exists() and not refresh:
        existing = json.loads(TICKER_INFO_PATH.read_text())
        logger.info("ticker_info.json already has %d entries", len(existing))

    rows = load_ritter_universe()
    universe, _counts = filter_universe(rows)
    store = PriceStore(store_dir=PRICE_STORE_DIR)

    wanted = []
    for row in universe:
        if row.ticker in existing:
            continue
        stored = store.read_ticker(row.ticker)
        if stored is None or stored.empty:
            continue
        wanted.append(row.ticker)
    wanted = sorted(set(wanted))
    logger.info("fetching .info for %d tickers", len(wanted))

    for index, ticker in enumerate(wanted, start=1):
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as exc:  # noqa: BLE001 — a failed lookup is data, not a crash
            logger.warning("info fetch failed for %s: %s", ticker, exc)
            existing[ticker] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        existing[ticker] = {
            "longName": info.get("longName"),
            "shortName": info.get("shortName"),
            "quoteType": info.get("quoteType"),
        }
        if index % 50 == 0:
            logger.info("  %d/%d", index, len(wanted))
            TICKER_INFO_PATH.write_text(json.dumps(existing, indent=1, sort_keys=True))

    TICKER_INFO_PATH.write_text(json.dumps(existing, indent=1, sort_keys=True))
    logger.info("wrote %s (%d entries)", TICKER_INFO_PATH, len(existing))
    return {"info_entries": len(existing), "info_fetched_this_run": len(wanted)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="re-download files that already exist")
    parser.add_argument("--skip-info", action="store_true", help="skip the slow per-ticker .info pass")
    args = parser.parse_args()

    IPO_LOCKUP_DIR.mkdir(parents=True, exist_ok=True)
    PRICE_STORE_DIR.mkdir(parents=True, exist_ok=True)

    _download(RITTER_IPO_AGE_URL, RITTER_IPO_AGE_PATH, UA_RITTER, args.refresh)
    _download(SEC_COMPANY_TICKERS_URL, SEC_COMPANY_TICKERS_PATH, UA_SEC, args.refresh)

    price_stats = fetch_prices(args.refresh)
    logger.info("price fetch: %s", price_stats)

    if not args.skip_info:
        info_stats = fetch_ticker_info(args.refresh)
        logger.info("info fetch: %s", info_stats)


if __name__ == "__main__":
    main()
