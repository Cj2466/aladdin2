"""Fetch all Phase B bars from Alpaca into a resumable per-ticker pickle
cache.

Request shape chosen from direct measurement, not guesswork:
- multi-symbol requests return tiny (~700-1000 bar) pages regardless of
  the 10k limit (server segments per symbol-month) -> ~830 bars/s;
- wide-window single-symbol requests also return partial pages;
- single-symbol requests over a window sized to ~one full page sustain
  5-15k bars/s.
So: one symbol at a time, 12-month windows for 15Min (~6.6k bars/page),
1-month windows for 1Min (~8.5k bars/page), serial, with a hard watchdog
because a response can occasionally hang/trickle for minutes without
tripping httpx's per-read timeout."""

import pickle
import sys
import time
from concurrent.futures import ThreadPoolExecutor as TPE
from concurrent.futures import TimeoutError as FutTimeout
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")

from app.services.market_data.alpaca_provider import AlpacaProvider
from app.services.research_lab.intraday_patterns import (
    PHASE_B_UNIVERSE_15MIN,
    PHASE_B_UNIVERSE_1MIN,
)

CACHE = Path("/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/bars_cache")
CACHE.mkdir(exist_ok=True)

M15_START, M15_END = date(2021, 1, 4), date(2026, 8, 24)
M1_START, M1_END = date(2023, 1, 3), date(2026, 8, 24)

provider = AlpacaProvider()


def month_windows(start: date, end: date, months: int):
    windows = []
    cur = start
    while cur <= end:
        nxt_month = cur.month + months
        nxt = date(cur.year + (nxt_month - 1) // 12, (nxt_month - 1) % 12 + 1, 1)
        windows.append((cur, min(nxt - timedelta(days=1), end)))
        cur = nxt
    return windows


def fetch_window_watchdog(sym, timeframe, w_start, w_end, hard_timeout=90):
    for attempt in range(4):
        pool = TPE(max_workers=1)
        fut = pool.submit(provider.get_stock_bars, [sym], timeframe, w_start, w_end)
        try:
            result = fut.result(timeout=hard_timeout)
            pool.shutdown(wait=False)
            return result
        except FutTimeout:
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"  watchdog: {sym} {w_start}..{w_end} hung >{hard_timeout}s, retrying", flush=True)
        except Exception as exc:
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"  {sym} {w_start}..{w_end} failed: {str(exc)[:80]}, retrying", flush=True)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"{sym} {w_start}..{w_end} failed after retries")


def fetch_ticker(ticker, timeframe, start, end, window_months):
    path = CACHE / f"{ticker}_{timeframe}.pkl"
    if path.exists():
        return "cached", 0
    sym = ticker.replace("-", ".")
    frames = []
    for w_start, w_end in month_windows(start, end, window_months):
        bars, _missing = fetch_window_watchdog(sym, timeframe, w_start, w_end)
        if sym in bars:
            frames.append(bars[sym])
    if not frames:
        return "MISSING", 0
    frame = pd.concat(frames).sort_index()
    frame = frame[~frame.index.duplicated(keep="first")]
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(frame))
    tmp.rename(path)
    return "ok", len(frame)


jobs = [(t, "15Min", M15_START, M15_END, 12) for t in PHASE_B_UNIVERSE_15MIN]
jobs += [(t, "1Min", M1_START, M1_END, 1) for t in PHASE_B_UNIVERSE_1MIN]

t0 = time.time()
total_bars = 0
n_ok = 0
for j, (ticker, timeframe, start, end, months) in enumerate(jobs, 1):
    try:
        status, n = fetch_ticker(ticker, timeframe, start, end, months)
    except Exception as exc:
        status, n = f"FAILED:{str(exc)[:60]}", 0
    total_bars += n
    if status == "ok":
        n_ok += 1
    if status != "cached" and (j % 10 == 0 or status != "ok"):
        print(
            f"[{j}/{len(jobs)}] {ticker} {timeframe}: {status} bars={n} "
            f"total={total_bars} elapsed={time.time()-t0:.0f}s",
            flush=True,
        )

print(f"ALL DONE: {n_ok} fetched, {total_bars} bars in {time.time()-t0:.0f}s", flush=True)
