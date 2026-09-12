"""
Fetch corporate-actions data from Alpaca for every dead ticker in dead_names.csv,
batched by ~100 symbols per request, over the whole window 2016-01-01..2026-09-11.
Caches raw JSON responses to a gzipped file for reproducibility.

Types requested: cash_merger, stock_merger, stock_and_cash_merger (the outcomes we
care about for delisting), plus name_change, redemption, worthless_removal,
reverse_split, forward_split for context on "other_action" classification.
"""
import csv
import gzip
import json
import os
import sys
import time
import urllib.request
import urllib.parse

API_KEY = os.environ["ALPACA_API_KEY"]
API_SECRET = os.environ["ALPACA_API_SECRET"]
BASE_URL = "https://data.alpaca.markets/v1/corporate-actions"

DEAD_NAMES_CSV = "data/research_runs/delisting_outcomes_2026-09-12/dead_names.csv"
OUT_CACHE = "data/research_runs/delisting_outcomes_2026-09-12/corporate_actions_raw.json.gz"

START = "2016-01-01"
END = "2026-09-11"
BATCH_SIZE = 100
TYPES = "cash_merger,stock_merger,stock_and_cash_merger,name_change,redemption,worthless_removal,reverse_split,forward_split"


def load_tickers():
    tickers = []
    with open(DEAD_NAMES_CSV) as f:
        for row in csv.DictReader(f):
            tickers.append(row["ticker"])
    return tickers


def fetch_batch(symbols_batch, session):
    all_actions = {}
    page_token = None
    n_pages = 0
    while True:
        params = {
            "types": TYPES,
            "symbols": ",".join(symbols_batch),
            "start": START,
            "end": END,
            "limit": 1000,
        }
        if page_token:
            params["page_token"] = page_token
        url = BASE_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "APCA-API-KEY-ID": API_KEY,
                "APCA-API-SECRET-KEY": API_SECRET,
            },
        )
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = json.loads(resp.read())
                break
            except urllib.error.HTTPError as e:
                err_body = e.read().decode(errors="replace")
                print(f"HTTPError {e.code} for batch starting {symbols_batch[0]}: {err_body}", file=sys.stderr)
                if e.code == 429:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except Exception as e:
                print(f"retry {attempt} error: {e}", file=sys.stderr)
                time.sleep(1 + attempt)
        else:
            raise RuntimeError("exhausted retries")

        cas = body.get("corporate_actions", {})
        for k, v in cas.items():
            all_actions.setdefault(k, []).extend(v)
        page_token = body.get("next_page_token")
        n_pages += 1
        if not page_token:
            break
    return all_actions, n_pages


def main():
    tickers = load_tickers()
    print(f"loaded {len(tickers)} dead tickers")

    combined = {}
    batches = [tickers[i : i + BATCH_SIZE] for i in range(0, len(tickers), BATCH_SIZE)]
    print(f"{len(batches)} batches of up to {BATCH_SIZE}")

    for i, batch in enumerate(batches):
        try:
            actions, n_pages = fetch_batch(batch, None)
        except Exception as e:
            print(f"BATCH {i} FAILED: {e}", file=sys.stderr)
            raise
        for k, v in actions.items():
            combined.setdefault(k, []).extend(v)
        total_so_far = sum(len(v) for v in combined.values())
        print(f"batch {i+1}/{len(batches)} ({batch[0]}..{batch[-1]}): {n_pages} page(s), running total actions={total_so_far}")
        time.sleep(0.2)  # be polite to the free endpoint

    with gzip.open(OUT_CACHE, "wt") as f:
        json.dump({"types_requested": TYPES, "start": START, "end": END, "corporate_actions": combined}, f)

    print(f"wrote {OUT_CACHE}")
    for k, v in combined.items():
        print(f"  {k}: {len(v)}")


if __name__ == "__main__":
    main()
