"""Step A1.5 — VERIFY, read-only.

1. Re-reads 10 random stored tickers back through PriceStore.read_ticker
   (the same path every consumer will use) and confirms each frame is
   non-empty and its dates fall inside the ingest window.
2. Prints a fingerprint of backend/data/price_store/ (file count + newest
   mtime) so it can be diffed against a pre-ingest snapshot taken before
   this script's own store ever wrote a byte -- this script does NOT modify
   that fingerprint, it only reports it.

Usage:
    ./venv/bin/python data/research_runs/whole_market_panel_2026-09-12/verify_whole_market_panel.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.config import MAIN_CHECKOUT_BACKEND_DIR
from app.services.market_data.price_store import PriceStore

OUT_DIR = Path(__file__).resolve().parent
INGEST_LOG_JSON = OUT_DIR / "ingest_run_log.json"
VERIFY_JSON = OUT_DIR / "verify_results.json"

ALPACA_STORE_DIR = MAIN_CHECKOUT_BACKEND_DIR / "data" / "price_store_alpaca" / "v1"
EXISTING_YFINANCE_STORE_DIR = MAIN_CHECKOUT_BACKEND_DIR / "data" / "price_store" / "v1"


def main() -> None:
    random.seed(20260912)
    store = PriceStore(store_dir=ALPACA_STORE_DIR)
    all_tickers = sorted(p.name[: -len(".csv.gz")] for p in ALPACA_STORE_DIR.glob("*.csv.gz"))
    sample = random.sample(all_tickers, min(10, len(all_tickers)))

    ingest_log = json.loads(INGEST_LOG_JSON.read_text()) if INGEST_LOG_JSON.exists() else {}
    start = ingest_log.get("start_date")
    end = ingest_log.get("end_date")

    per_ticker = []
    all_ok = True
    for ticker in sample:
        frame = store.read_ticker(ticker)
        ok = frame is not None and not frame.empty
        first_date = last_date = None
        if ok:
            first_date = frame.index.min().date().isoformat()
            last_date = frame.index.max().date().isoformat()
            if start and first_date < start:
                ok = False
            if end and last_date > end:
                ok = False
        all_ok = all_ok and ok
        per_ticker.append(
            {"ticker": ticker, "non_empty": frame is not None and not frame.empty, "rows": 0 if frame is None else len(frame), "first_date": first_date, "last_date": last_date, "within_window": ok}
        )

    existing_store_files = sorted(EXISTING_YFINANCE_STORE_DIR.glob("*.csv.gz")) if EXISTING_YFINANCE_STORE_DIR.exists() else []
    existing_store_fingerprint = {
        "path": str(EXISTING_YFINANCE_STORE_DIR),
        "file_count": len(existing_store_files),
        "newest_mtime": max((p.stat().st_mtime for p in existing_store_files), default=None),
        "total_bytes": sum(p.stat().st_size for p in existing_store_files),
    }

    results = {
        "sampled_tickers": per_ticker,
        "all_sampled_ok": all_ok,
        "existing_yfinance_store_fingerprint_AFTER_alpaca_ingest": existing_store_fingerprint,
    }
    VERIFY_JSON.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
