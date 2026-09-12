"""Step A1.1 — WHOLE-MARKET US-equity universe from Alpaca's trading API,
cross-referenced against SEC's own company_tickers.json.

Usage:
    ./venv/bin/python data/research_runs/whole_market_panel_2026-09-12/fetch_universe.py

Writes universe.csv next to this script and prints the counts the plan asked
to be verified rather than assumed:
  - active-listed / inactive-listed us_equity assets, before any filter
  - the same after keeping only exchange in {NYSE, NASDAQ, AMEX, ARCA, BATS}
    and symbol matching ^[A-Z]{1,5}$
  - how many of the kept symbols also appear in SEC's company_tickers.json
    (operating companies that file with the SEC; ETFs/trusts mostly do not)

Endpoint: GET /v2/assets on Alpaca's TRADING API (not the market-data API).
Verified live 2026-09-12: api.alpaca.markets returned HTTP 401 "request is
not authorized" for this account's keys; paper-api.alpaca.markets returned
HTTP 200. This account's keys are paper-trading keys (ALPACA_PAPER_TRADING=
true in .env) -- the /v2/assets reference data is identical on both trading
hosts (it is not a paper-money concept, just gated by which host the key is
valid on), so paper-api.alpaca.markets/v2/assets is the correct, and only
working, source for this account. Recorded here rather than silently
switched to, per the project's never-fabricate rule.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import sys
import time
from pathlib import Path

import httpx

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.config import settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fetch_universe")

OUT_DIR = Path(__file__).resolve().parent
UNIVERSE_CSV = OUT_DIR / "universe.csv"
COUNTS_JSON = OUT_DIR / "universe_counts.json"

TRADING_BASE_URL = "https://paper-api.alpaca.markets"
ALLOWED_EXCHANGES = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}
SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_USER_AGENT = "aladdin2 research autoa0792@gmail.com"


def fetch_assets(client: httpx.Client, status: str) -> list[dict]:
    resp = client.get(
        "/v2/assets",
        params={"status": status, "asset_class": "us_equity"},
        headers={
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_sec_company_tickers() -> set[str]:
    """Returns the set of tickers SEC's company_tickers.json knows about
    (operating companies that file with the SEC -- this is what separates
    them from ETFs/trusts for later cross-sectional sorts)."""
    with httpx.Client(headers={"User-Agent": SEC_USER_AGENT}, timeout=60.0) as client:
        resp = client.get(SEC_COMPANY_TICKERS_URL)
        resp.raise_for_status()
        payload = resp.json()
    tickers = {row["ticker"].upper() for row in payload.values()}
    logger.info("SEC company_tickers.json: %d tickers", len(tickers))
    return tickers


def main() -> None:
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        raise SystemExit("ALPACA_API_KEY / ALPACA_API_SECRET not set in the environment")

    with httpx.Client(base_url=TRADING_BASE_URL) as client:
        t0 = time.time()
        active = fetch_assets(client, "active")
        inactive = fetch_assets(client, "inactive")
        logger.info("fetched %d active + %d inactive us_equity assets in %.1fs", len(active), len(inactive), time.time() - t0)

    all_assets = [(a, "active") for a in active] + [(a, "inactive") for a in inactive]

    kept = []
    for asset, status_bucket in all_assets:
        symbol = asset.get("symbol", "")
        exchange = asset.get("exchange", "")
        if exchange not in ALLOWED_EXCHANGES:
            continue
        if not SYMBOL_RE.match(symbol):
            continue
        kept.append(asset)

    sec_tickers = fetch_sec_company_tickers()

    with UNIVERSE_CSV.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["symbol", "name", "exchange", "status", "tradable", "in_sec_company_tickers"])
        for asset in sorted(kept, key=lambda a: a["symbol"]):
            writer.writerow(
                [
                    asset["symbol"],
                    asset.get("name", ""),
                    asset.get("exchange", ""),
                    asset.get("status", ""),
                    asset.get("tradable", ""),
                    asset["symbol"].upper() in sec_tickers,
                ]
            )

    n_inactive_kept = sum(1 for a in kept if a["status"] == "inactive")
    n_active_kept = sum(1 for a in kept if a["status"] == "active")
    n_sec = sum(1 for a in kept if a["symbol"].upper() in sec_tickers)

    counts = {
        "raw_active_us_equity": len(active),
        "raw_inactive_us_equity": len(inactive),
        "kept_after_exchange_and_symbol_filter": len(kept),
        "kept_active": n_active_kept,
        "kept_inactive": n_inactive_kept,
        "kept_in_sec_company_tickers": n_sec,
        "kept_not_in_sec_company_tickers": len(kept) - n_sec,
        "sec_company_tickers_total": len(sec_tickers),
        "allowed_exchanges": sorted(ALLOWED_EXCHANGES),
        "symbol_regex": SYMBOL_RE.pattern,
    }
    COUNTS_JSON.write_text(json.dumps(counts, indent=2))

    logger.info("counts: %s", json.dumps(counts, indent=2))
    logger.info("wrote %s (%d rows)", UNIVERSE_CSV, len(kept))


if __name__ == "__main__":
    main()
