"""Build the SPY / QQQ / IWM 1-minute (and 1-day) Alpaca SIP bar cache for
the letf_rebalancing_eod family.

WHY A COMMITTED SCRIPT AND A DURABLE PATH
=========================================
Identical reasoning to data/research_runs/fetch_spy_1min_bars.py and
fetch_intraday_bars_15min.py, whose docstrings record the incident the
convention exists to prevent: the 2026-08-26 low_frequency_patterns run cached
its bars in an EPHEMERAL session scratchpad, that directory is gone, and the
run's exact inputs are unrecoverable. This script is committed and writes to a
durable, explicitly-gitignored path under the MAIN checkout's backend/data/,
resolved through the shared .git directory by
app.config._main_checkout_backend_dir, so a `git worktree remove` cannot take it
and every worktree reads the same bars.

WINDOW
======
2016-01-04 .. the last COMPLETE UTC session before the run, per PREREGISTRATION
section 2. "Complete" is judged in UTC, never the local date: the US regular
session closes at 20:00/21:00 UTC, so in Bangkok (UTC+7) the local date has
already rolled over while New York is still trading, and a local-date end would
request a forming session. END is therefore pinned explicitly below rather than
computed from date.today().

WHY ALL THREE TICKERS ARE FETCHED FRESH INTO A NEW DIRECTORY
============================================================
data/spy_1min_bars/SPY_1Min.pkl already holds 1,046,038 SIP minute bars for
2016-01-04..2026-09-08 -- verified, and one session short of this family's
window. PREREGISTRATION section 2 permits reusing it if the range is extended
and never spliced from two feeds. It is NOT reused here, for a reason that costs
only fetch time: this family's panel is BALANCED (a session enters only if all
three underlyings pass U1-U3), so the three series must come from one request
shape, one feed and one run. Fetching SPY alongside QQQ and IWM makes that true
by construction instead of by argument, and leaves the intraday_momentum_spy
family's own cache untouched and still exactly what that run used.

FEED
====
AlpacaProvider's DEFAULT_FEED is "sip" and this script does not override it, so
an entitlement change fails loudly rather than silently degrading to IEX. The
1Day bars are fetched for the volume cross-check the pre-registration inherits
from intraday_momentum_spy section 2c; run_letf_rebalancing_eod.py performs it
and reports the answer either way.

REQUEST SHAPE
=============
One symbol, serial, 6-month windows -- inherited from fetch_intraday_bars_15min.py's
measured finding that the server segments per symbol-month and that single-symbol
requests sized to about one full page sustain the best throughput. A 6-month
1-minute window is ~49k bars, about five pages of the 10k page limit;
AlpacaProvider walks next_page_token itself.

Resumable: an existing pickle is left untouched unless --force is passed.
"""

from __future__ import annotations

import os
import pickle
import sys
from datetime import date
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import _main_checkout_backend_dir
from app.services.market_data.alpaca_provider import AlpacaProvider

MAIN_BACKEND = _main_checkout_backend_dir(BACKEND)
CACHE_DIR = MAIN_BACKEND / "data" / "letf_1min_bars"

TICKERS = ("SPY", "QQQ", "IWM")
START = date(2016, 1, 4)
# Last COMPLETE UTC session before the run. 2026-09-10 17:55 UTC is inside the
# 2026-09-10 US session, so 2026-09-09 is the last complete one. It also equals
# the last Date in the ProShares AUM snapshot this run pins.
END = date(2026, 9, 9)
WINDOW_MONTHS = 6


def minute_pickle(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker}_1Min.pkl"


def daily_pickle(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker}_1Day.pkl"


def _credential(key: str) -> str:
    """Alpaca credentials live in the MAIN checkout's gitignored backend/.env.
    A linked worktree has no copy, and Settings' env_file=".env" resolves against
    the PROCESS working directory, so importing `settings` from a worktree
    silently yields empty strings. Read the main checkout's file directly and
    pass the values to AlpacaProvider's explicit api_key/api_secret arguments.
    A real environment variable always wins. Never prints a value, and the
    secret is never copied into the worktree or committed."""
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


def _windows(start: date, end: date, months: int) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        year, month = cursor.year, cursor.month + months
        year += (month - 1) // 12
        month = (month - 1) % 12 + 1
        nxt = date(year, month, 1)
        out.append((cursor, min(end, nxt - pd.Timedelta(days=1).to_pytimedelta())))
        cursor = nxt
    return out


def fetch(ticker: str, timeframe: str, target: Path, provider: AlpacaProvider) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    windows = _windows(START, END, WINDOW_MONTHS) if timeframe == "1Min" else [(START, END)]
    for i, (w_start, w_end) in enumerate(windows, 1):
        bars, missing = provider.get_stock_bars(
            [ticker], timeframe=timeframe, start=w_start, end=w_end, regular_session_only=True
        )
        if missing:
            print(f"  {ticker} window {i}/{len(windows)} {w_start}..{w_end}: MISSING {missing}", flush=True)
            continue
        frame = bars[ticker]
        frames.append(frame)
        print(f"  {ticker} window {i}/{len(windows)} {w_start}..{w_end}: {len(frame):,} bars", flush=True)
    if not frames:
        raise SystemExit(f"no {timeframe} bars returned for {ticker} -- recording the failure, NOT substituting a source")
    combined = pd.concat(frames).sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as fh:
        pickle.dump(combined, fh)
    print(f"wrote {len(combined):,} {timeframe} bars -> {target}", flush=True)
    return combined


def main() -> None:
    force = "--force" in sys.argv
    provider = AlpacaProvider(
        api_key=_credential("ALPACA_API_KEY"), api_secret=_credential("ALPACA_API_SECRET")
    )
    for ticker in TICKERS:
        for timeframe, target in (("1Min", minute_pickle(ticker)), ("1Day", daily_pickle(ticker))):
            if target.exists() and not force:
                print(f"{target} exists; skipping (pass --force to refetch)")
                continue
            print(f"fetching {ticker} {timeframe} {START}..{END}", flush=True)
            fetch(ticker, timeframe, target, provider)


if __name__ == "__main__":
    main()
