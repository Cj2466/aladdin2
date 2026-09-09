"""Repair the coverage ledger the five-day tolerance froze on seven-day
symbols, then let the missing crypto bars actually arrive.

    set -a; . ./.env; set +a
    ./venv/bin/python data/research_runs/crypto_coverage_2026-09-10/repair_crypto_coverage.py

WHY. Found 2026-09-10 while checking live-panel reproducibility: 68 of the 73
crypto tickers in the shared store held no row after 2026-09-07 while the
ledger recorded them covered through 2026-09-09. `bounded_coverage_end` gave
them the five-day weekend slack (ROLLING_WINDOW_TOLERANCE_DAYS = 4), which runs
past the requested end and therefore shrank nothing, so `is_covered` returned
True and the real, final 09-08 bar was never re-asked. cross_sectional_crypto —
a live forward registration — built its 2026-09-09 panel a whole day stale.

The code fix is in this branch (CONTINUOUS_CALENDAR_TOLERANCE_DAYS = 1, applied
per ticker through coverage_tolerance_days). This script repairs the ledger that
was already written under the old rule and refetches, which the fix alone does
not do.

WHAT IT TOUCHES. The shared price store under the MAIN checkout, and the vendor.
It writes NOTHING to the database: no registration is read for its state and no
trial or forward-validation row is created or changed (CLAUDE.md rule 6). The
store is append-only and first-write-wins, so the refetch can only ADD the bars
that are missing; it cannot rewrite a stored one.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from app.services.market_data.price_store import (
    PriceStore,
    trades_every_calendar_day,
    utc_today,
)
from app.services.market_data.yfinance_provider import YFinanceProvider
from app.services.research_lab.cross_sectional_crypto import (
    CRYPTO_PRICE_HISTORY_START,
    CRYPTO_UNIVERSE,
)

HERE = Path(__file__).resolve().parent


def newest_rows(store: PriceStore, tickers: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for ticker in tickers:
        frame = store.read_ticker(ticker)
        out[ticker] = None if frame is None or frame.empty else str(frame.index.max().date())
    return out


def main() -> int:
    today = utc_today()
    now = datetime.now(UTC)
    store = PriceStore()
    print(f"store: {store.store_dir}\nas of {today} (UTC)\n")

    universe = sorted(CRYPTO_UNIVERSE)
    assert all(trades_every_calendar_day(t) for t in universe)

    before = newest_rows(store, universe)
    ledger_before = store.read_coverage()

    changed = store.rebound_coverage(as_of=today)
    crypto_changed = {t: v for t, v in changed.items() if trades_every_calendar_day(t)}
    print(f"ledger windows shrunk: {len(changed)} total, {len(crypto_changed)} of them crypto")
    for ticker, (old, new) in sorted(crypto_changed.items())[:5]:
        print(f"   {ticker:10s} {old} -> {new}")
    if len(crypto_changed) > 5:
        print(f"   ... and {len(crypto_changed) - 5} more")

    # Ask for the same window the family itself uses: everything from the
    # earliest listing to today. The store refuses any row dated on or after
    # today (section 4c), so this can only bring in final bars.
    provider = YFinanceProvider()
    # CRYPTO_PRICE_HISTORY_START, not an earlier date: asking from 2013 makes
    # the append-only store ALSO take in whatever earlier history the vendor
    # happens to hold (BTC-USD and LTC-USD go back to 2014-09-17 on Yahoo),
    # which is real data and harms nothing stored, but it widens a live
    # family's inputs as a side effect of a repair. Measured when this script
    # was first run that way: the panel was unchanged, because
    # CRYPTO_PRICE_HISTORY_START is a fixed module constant and clamps it.
    # Pinning the request to the same constant makes that a guarantee instead
    # of a fact about today's module.
    start = CRYPTO_PRICE_HISTORY_START
    print(f"\nfetching {len(universe)} crypto tickers [{start} .. {today})")
    panel, missing = provider.get_price_history(universe, start, today)
    # get_price_history returns a (dates x tickers) FRAME, so this is a row
    # count, not a count of tickers.
    print(f"returned {len(panel)} rows x {panel.shape[1]} tickers, {len(missing)} missing")

    after = newest_rows(store, universe)
    advanced = {t: (before[t], after[t]) for t in universe if before[t] != after[t]}
    print(f"\ntickers whose newest stored row advanced: {len(advanced)}")
    for ticker, (old, new) in sorted(advanced.items())[:5]:
        print(f"   {ticker:10s} {old} -> {new}")
    if len(advanced) > 5:
        print(f"   ... and {len(advanced) - 5} more")

    expected = (today - timedelta(days=1)).isoformat()
    at_expected = sorted(t for t in universe if after[t] == expected)
    print(f"\ncrypto tickers now current to {expected}: {len(at_expected)} of {len(universe)}")
    stale = sorted(t for t in universe if after[t] is not None and after[t] < expected)
    print(f"still older than that (dead or delisted feeds): {len(stale)}")
    for ticker in stale:
        print(f"   {ticker:10s} newest {after[ticker]}")

    payload = {
        "run_at": now.isoformat(timespec="minutes"),
        "as_of": today.isoformat(),
        "store_dir": str(store.store_dir),
        "ledger_windows_shrunk_total": len(changed),
        "ledger_windows_shrunk_crypto": {t: list(v) for t, v in sorted(crypto_changed.items())},
        "ledger_entries_before": len(ledger_before),
        "newest_row_before": before,
        "newest_row_after": after,
        "advanced": {t: list(v) for t, v in sorted(advanced.items())},
        "current_to_expected": at_expected,
        "expected_newest": expected,
        "still_stale": {t: after[t] for t in stale},
        "vendor_missing": sorted(missing),
        "note": (
            "Store writes only; no DB row of any kind was read for its state or written. "
            "The store is append-only and first-write-wins, so nothing already stored changed."
        ),
    }
    out = HERE / f"crypto_coverage_repair_{now.strftime('%Y-%m-%dT%H%MZ')}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"\nwritten {out.relative_to(_BACKEND)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
