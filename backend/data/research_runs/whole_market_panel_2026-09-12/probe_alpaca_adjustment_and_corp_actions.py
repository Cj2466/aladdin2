"""Step A1.2 — PROBE BEFORE BULK, committed.

Two questions, answered with real HTTP calls against this account's Alpaca
keys, before any bulk ingest is written:

  1. Does GET /v2/stocks/bars adjustment="raw" already return AS-TRADED
     prices (the price_store.py convention -- raw, unadjusted, split factors
     applied at read time), or does it need the same un-split-adjustment
     price_store.to_as_traded applies to yfinance's auto_adjust=False rows?
     Checked against the one independently-known fact already pinned in this
     codebase's own test suite: AAPL closed at 499.23 on 2020-08-28, three
     trading days before its 2020-08-31 4-for-1 split
     (tests/test_price_store.py::test_apple_2020_split_reconstructs_the_real_traded_price).

  2. Does Alpaca expose a free corporate-actions endpoint
     (data.alpaca.markets/v1/corporate-actions)? What HTTP status, and what
     action types does it return?

20 symbols: 10 large caps, 5 small/mid caps, 5 KNOWN-DELISTED names drawn
from universe.csv's own inactive rows (AABA=Yahoo/Altaba, ACC=American
Campus Communities/acquired by Blackstone 2022, ACIA=Acacia Communications/
acquired by Cisco 2021, ABDC=Alcentra Capital/acquired, ACBI=Atlantic
Capital Bancshares/acquired by SouthState 2023).

Usage:
    ./venv/bin/python data/research_runs/whole_market_panel_2026-09-12/probe_alpaca_adjustment_and_corp_actions.py

Writes probe_results.json next to this script.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import httpx

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.config import settings  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
RESULTS_JSON = OUT_DIR / "probe_results.json"

LARGE_CAPS = ["AAPL", "MSFT", "AMZN", "GOOGL", "NVDA", "META", "TSLA", "JPM", "XOM", "WMT"]
SMALL_MID_CAPS = ["EBON", "DGII", "STLD", "BLKB", "EVRG"]
KNOWN_DELISTED = ["AABA", "ACC", "ACIA", "ABDC", "ACBI"]
PROBE_SYMBOLS = LARGE_CAPS + SMALL_MID_CAPS + KNOWN_DELISTED

DATA_BASE_URL = "https://data.alpaca.markets"

AAPL_SPLIT_WINDOW = (date(2020, 8, 20), date(2020, 9, 4))
AAPL_KNOWN_AS_TRADED_CLOSE_2020_08_28 = 499.23


def auth_headers() -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
    }


def fetch_bars(client: httpx.Client, symbols: list[str], start: date, end: date, adjustment: str) -> dict:
    resp = client.get(
        "/v2/stocks/bars",
        params={
            "symbols": ",".join(symbols),
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "adjustment": adjustment,
            "feed": "sip",
            "limit": 10000,
        },
        headers=auth_headers(),
        timeout=30.0,
    )
    return {"status_code": resp.status_code, "body": resp.json() if resp.status_code == 200 else resp.text}


def fetch_corporate_actions(client: httpx.Client, symbols: list[str], start: date, end: date) -> dict:
    resp = client.get(
        "/v1/corporate-actions",
        params={"symbols": ",".join(symbols), "start": start.isoformat(), "end": end.isoformat()},
        headers=auth_headers(),
        timeout=30.0,
    )
    body: object
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    return {"status_code": resp.status_code, "body": body}


def main() -> None:
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        raise SystemExit("ALPACA_API_KEY / ALPACA_API_SECRET not set in the environment")

    results: dict = {"symbols_probed": PROBE_SYMBOLS}

    with httpx.Client(base_url=DATA_BASE_URL) as client:
        # --- Question 1: raw vs all adjustment, same window, same symbols ---
        raw = fetch_bars(client, PROBE_SYMBOLS, *AAPL_SPLIT_WINDOW, adjustment="raw")
        allj = fetch_bars(client, PROBE_SYMBOLS, *AAPL_SPLIT_WINDOW, adjustment="all")
        results["bars_raw"] = raw
        results["bars_all"] = allj

        aapl_raw_close_2020_08_28 = None
        if raw["status_code"] == 200:
            for bar in raw["body"].get("bars", {}).get("AAPL", []):
                if bar["t"].startswith("2020-08-28"):
                    aapl_raw_close_2020_08_28 = bar["c"]
        results["aapl_raw_close_2020_08_28"] = aapl_raw_close_2020_08_28
        results["aapl_known_as_traded_close_2020_08_28"] = AAPL_KNOWN_AS_TRADED_CLOSE_2020_08_28
        results["raw_matches_known_as_traded_fact"] = (
            aapl_raw_close_2020_08_28 is not None
            and abs(aapl_raw_close_2020_08_28 - AAPL_KNOWN_AS_TRADED_CLOSE_2020_08_28) < 0.01
        )

        # --- Question 2: corporate-actions endpoint ---
        ca = fetch_corporate_actions(client, PROBE_SYMBOLS, date(2016, 1, 1), date(2026, 9, 11))
        results["corporate_actions"] = ca
        if ca["status_code"] == 200 and isinstance(ca["body"], dict):
            action_types = sorted((ca["body"].get("corporate_actions") or {}).keys())
            results["corporate_actions_types_returned"] = action_types

        # --- corporate-actions BULK (no symbols filter) probe: does it cover
        # the whole market in one paginated walk, or only named symbols? ---
        bulk = client.get(
            "/v1/corporate-actions",
            params={"start": "2020-01-01", "end": "2020-01-31"},
            headers=auth_headers(),
            timeout=30.0,
        )
        bulk_body = bulk.json() if bulk.status_code == 200 else bulk.text
        results["corporate_actions_bulk_no_symbol_filter"] = {
            "status_code": bulk.status_code,
            "types_and_counts": (
                {k: len(v) for k, v in bulk_body.get("corporate_actions", {}).items()}
                if bulk.status_code == 200
                else bulk_body
            ),
            "has_next_page_token": bool(bulk_body.get("next_page_token")) if bulk.status_code == 200 else None,
        }

    RESULTS_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(json.dumps({k: v for k, v in results.items() if k not in ("bars_raw", "bars_all")}, indent=2, default=str))


if __name__ == "__main__":
    main()
