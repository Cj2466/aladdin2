"""Rebuild the 15-minute Alpaca SIP bar cache for PHASE_B_UNIVERSE_15MIN.

WHY THIS SCRIPT IS COMMITTED AND ITS 2026-08-26 ANCESTOR WAS NOT
================================================================
The original Phase C (low_frequency_patterns) screening run on 2026-08-26
fetched these same bars with an uncommitted scratch script
(research_archive/session_2026-08-22_to_27/fetch_bars.py) into an EPHEMERAL
session scratchpad:

    /private/tmp/claude-501/<session-uuid>/scratchpad/bars_cache   (line 33)

That path no longer exists, and no *_15Min.pkl survives anywhere on this
machine. The consequence is concrete and is disclosed in the recovered
family's results file: the original run's exact inputs are GONE, so its
headline numbers can be RE-MEASURED against a fresh fetch but never
bit-reproduced. This script is committed, and writes to a durable
gitignored path, so that failure mode is not repeated.

REQUEST SHAPE
=============
Inherited unchanged from the 2026-08-26 fetcher, which chose it by direct
measurement rather than guesswork (its docstring, lines 4-13): multi-symbol
requests and over-wide single-symbol windows both return small partial pages
(~830 bars/s) because the server segments per symbol-month; single-symbol
requests over a window sized to about one full page sustain 5-15k bars/s. So:
one symbol at a time, 12-month windows for 15Min (~6.6k bars/page), serial,
with a hard watchdog because a response can occasionally hang or trickle for
minutes without tripping httpx's per-read timeout.

FEED
====
AlpacaProvider's DEFAULT_FEED is "sip" and this script does not override it.
That matters for comparability: alpaca_provider.py's own docstring records
the measurement that feed=iex returned AAPL 28,658 shares for one real minute
in Jan 2021 where feed=sip returned 3,806,856. A cache built on the thin feed
would not be comparable to the 2026-08-26 run at all.

WINDOW
======
2021-01-04..2026-08-24, identical to the original run, so the reproduction
attempt differs from the original in as few dimensions as possible. The end
date is deliberately NOT advanced to today: extending the sample would change
the measured quantity and make any difference from the original numbers
uninterpretable.

Resumable: an existing per-ticker pickle is left untouched, so an interrupted
run is restarted by re-invoking with no arguments.
"""

from __future__ import annotations

import os
import pickle
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import _main_checkout_backend_dir
from app.services.market_data.alpaca_provider import AlpacaProvider
from app.services.research_lab.intraday_patterns import (
    PHASE_B_UNIVERSE_15MIN,
)

# The MAIN checkout's backend/, resolved through the shared .git directory —
# the same routing app/config.py uses for aladdin2.db, and for the same
# reason (its docstring: a worktree-local path "reported success -- and then
# `git worktree remove` deleted the whole directory, taking the rows with
# it"). A ~1GB refetchable bar cache should no more die with this worktree
# than the trial rows should, and .env lives here too.
MAIN_BACKEND = _main_checkout_backend_dir(BACKEND)
CACHE = MAIN_BACKEND / "data" / "intraday_bars_15min"


def _credential(key: str) -> str:
    """Alpaca credentials live in the MAIN checkout's gitignored backend/.env.
    A linked worktree has no copy, and Settings' env_file=".env" is resolved
    against the PROCESS WORKING DIRECTORY (app/config.py:508), so importing
    settings from a worktree silently yields empty strings. Hence reading the
    main checkout's file directly and passing the values to AlpacaProvider's
    explicit api_key/api_secret arguments (alpaca_provider.py:119-121) rather
    than relying on the settings singleton.

    A real environment variable always wins. Never prints a value.

    Loud on failure rather than letting the fetch discover it 284 tickers in:
    AlpacaProvider raises "credentials are not configured" per REQUEST, so the
    retry loop would patiently repeat that four times for every window of
    every ticker without ever failing the run."""
    from_env = os.environ.get(key)
    if from_env:
        return from_env
    env_path = MAIN_BACKEND / ".env"
    if not env_path.is_file():
        raise SystemExit(f"{key} is unset and no .env exists at {env_path}")
    for line in env_path.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() == key:
            resolved = value.strip().strip('"').strip("'")
            if resolved:
                return resolved
    raise SystemExit(f"{key} is unset and {env_path} does not define a non-empty value for it")

# Identical to the 2026-08-26 run's M15_START / M15_END.
M15_START, M15_END = date(2021, 1, 4), date(2026, 8, 24)
WINDOW_MONTHS = 12
HARD_TIMEOUT_S = 90

# Tickers fetched concurrently. Concurrency is across TICKERS only; each
# ticker's own windows stay serial, preserving the original fetcher's measured
# one-symbol-per-request shape.
#
# THIS NUMBER WAS SET BY MEASUREMENT, AND THE FIRST GUESS WAS WRONG. Fully
# serial (the 2026-08-26 fetcher's shape) measured ~4.5 min/ticker here, i.e.
# ~21h for 284 tickers. Reasoning from Alpaca's DOCUMENTED 200-requests/minute
# window (alpaca_provider.py:38, :100) and ~9 requests per ticker suggested 12
# workers would sit at ~28 req/min with a 7x margin. In practice 12 workers
# drew sustained 429s within minutes, so the binding constraint is NOT the
# documented request count -- most likely a payload/bars-per-minute limit on
# this account's data tier, which request-count arithmetic cannot see. Backed
# off rather than re-deriving from a model already shown not to predict this
# endpoint's behaviour. 429s are retried with backoff by _call_with_retry, so a
# too-high setting is wasteful rather than fatal -- but pointing a sustained
# retry storm at a vendor API is the wrong default.
#
# Settled at 8 by bisection: 5 workers sustained ~1.1 tickers/min with ZERO
# 429s over a 3-minute observation, 12 drew them immediately. 8 keeps a margin
# under the level that actually broke rather than creeping up to it.
N_WORKERS = 8

provider = AlpacaProvider(
    api_key=_credential("ALPACA_API_KEY"), api_secret=_credential("ALPACA_API_SECRET")
)


def month_windows(start: date, end: date, months: int) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        nxt_month = cur.month + months
        nxt = date(cur.year + (nxt_month - 1) // 12, (nxt_month - 1) % 12 + 1, 1)
        windows.append((cur, min(nxt - timedelta(days=1), end)))
        cur = nxt
    return windows


def fetch_window_watchdog(sym: str, timeframe: str, w_start: date, w_end: date):
    """A hung response is retried, never silently treated as an empty window —
    an empty window would look exactly like a ticker that legitimately had no
    bars and would quietly shorten that ticker's history."""
    last_exc: Exception | None = None
    for attempt in range(4):
        pool = ThreadPoolExecutor(max_workers=1)
        fut = pool.submit(provider.get_stock_bars, [sym], timeframe, w_start, w_end)
        try:
            result = fut.result(timeout=HARD_TIMEOUT_S)
            pool.shutdown(wait=False)
            return result
        except FutureTimeout:
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"  watchdog: {sym} {w_start}..{w_end} hung >{HARD_TIMEOUT_S}s, retrying", flush=True)
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised below
            last_exc = exc
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"  {sym} {w_start}..{w_end} failed: {str(exc)[:80]}, retrying", flush=True)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"{sym} {w_start}..{w_end} failed after 4 attempts: {last_exc}")


def fetch_ticker(ticker: str) -> tuple[str, int]:
    path = CACHE / f"{ticker}_15Min.pkl"
    if path.exists():
        return "cached", 0
    sym = ticker.replace("-", ".")
    frames = []
    for w_start, w_end in month_windows(M15_START, M15_END, WINDOW_MONTHS):
        bars, _missing = fetch_window_watchdog(sym, "15Min", w_start, w_end)
        if sym in bars:
            frames.append(bars[sym])
    if not frames:
        return "MISSING", 0
    frame = pd.concat(frames).sort_index()
    frame = frame[~frame.index.duplicated(keep="first")]
    # Write-then-rename: a killed process can never leave a half-written
    # pickle that the resume path would mistake for a complete ticker.
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(frame))
    tmp.rename(path)
    return "ok", len(frame)


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    tickers = list(PHASE_B_UNIVERSE_15MIN)
    print(f"{len(tickers)} tickers, window {M15_START}..{M15_END}, cache {CACHE}", flush=True)

    def run_one(ticker: str) -> tuple[str, str, int]:
        try:
            status, n = fetch_ticker(ticker)
        except Exception as exc:  # noqa: BLE001 - recorded, run continues
            return ticker, f"FAILED:{str(exc)[:60]}", 0
        return ticker, status, n

    t0 = time.time()
    total_bars = 0
    n_ok = 0
    n_cached = 0
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=N_WORKERS) as pool:
        for j, (ticker, status, n) in enumerate(pool.map(run_one, tickers), 1):
            total_bars += n
            if status == "ok":
                n_ok += 1
            elif status == "cached":
                n_cached += 1
            else:
                failures.append(f"{ticker}:{status}")
            if j % 10 == 0 or status not in ("ok", "cached"):
                elapsed = time.time() - t0
                print(
                    f"[{j}/{len(tickers)}] {ticker}: {status} bars={n} total={total_bars} "
                    f"elapsed={elapsed / 60:.1f}m ETA={(len(tickers) - j) * elapsed / j / 60:.0f}m",
                    flush=True,
                )

    print(
        f"DONE: {n_ok} fetched, {n_cached} already cached, {len(failures)} failed, "
        f"{total_bars} new bars in {time.time() - t0:.0f}s",
        flush=True,
    )
    if failures:
        print(f"FAILURES: {failures}", flush=True)


if __name__ == "__main__":
    main()
