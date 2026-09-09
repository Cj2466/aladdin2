"""Rebuild the SPY 1-minute Alpaca SIP bar cache for the intraday_momentum_spy family.

WHY A COMMITTED SCRIPT AND A DURABLE PATH
=========================================
Same reason as data/research_runs/fetch_intraday_bars_15min.py, whose docstring
records the incident this convention exists to prevent: the 2026-08-26
low_frequency_patterns run cached its bars in an EPHEMERAL session scratchpad,
that directory is gone, and the run's exact inputs are unrecoverable. So this
script is committed and writes to a durable, explicitly-gitignored path under
the MAIN checkout's backend/data/ (resolved through the shared .git directory by
app.config._main_checkout_backend_dir), which survives `git worktree remove`.

WINDOW
======
2016-01-04 .. 2026-09-08, pre-registered in
data/research_runs/intraday_momentum_spy_2026-09-09/PREREGISTRATION.md section 2.
2016-01-04 is the first trading day of 2016; ADDENDUM_ALPACA_PROBE.md verified
390 one-minute rows for 2016-01-05 on this account.

FEED
====
AlpacaProvider's DEFAULT_FEED is "sip" and this script does not override it, so
an entitlement change fails loudly rather than silently degrading to IEX (the
reason alpaca_provider.py passes feed explicitly in the first place). The
pre-registration section 2c declares a volume cross-check against the same
endpoint's 1Day bars; run_intraday_momentum_spy.py performs it and reports the
answer either way.

REQUEST SHAPE
=============
One symbol, serial, 6-month windows. Inherited from fetch_intraday_bars_15min.py's
measured finding that the server segments per symbol-month and that
single-symbol requests sized to about one full page sustain the best throughput;
a 6-month 1-minute window is ~49k bars = ~5 pages of the 10k page limit.
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

from app.config import _main_checkout_backend_dir  # noqa: E402
from app.services.market_data.alpaca_provider import AlpacaProvider  # noqa: E402

MAIN_BACKEND = _main_checkout_backend_dir(BACKEND)
CACHE_DIR = MAIN_BACKEND / "data" / "spy_1min_bars"
MINUTE_PICKLE = CACHE_DIR / "SPY_1Min.pkl"
DAILY_PICKLE = CACHE_DIR / "SPY_1Day.pkl"

TICKER = "SPY"
START = date(2016, 1, 4)
END = date(2026, 9, 8)
WINDOW_MONTHS = 6


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


def fetch(timeframe: str, target: Path, provider: AlpacaProvider) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    windows = _windows(START, END, WINDOW_MONTHS) if timeframe == "1Min" else [(START, END)]
    for i, (w_start, w_end) in enumerate(windows, 1):
        bars, missing = provider.get_stock_bars(
            [TICKER], timeframe=timeframe, start=w_start, end=w_end, regular_session_only=True
        )
        if missing:
            print(f"  window {i}/{len(windows)} {w_start}..{w_end}: MISSING {missing}", flush=True)
            continue
        frame = bars[TICKER]
        frames.append(frame)
        print(
            f"  window {i}/{len(windows)} {w_start}..{w_end}: {len(frame):,} bars", flush=True
        )
    if not frames:
        raise SystemExit(f"no {timeframe} bars returned for {TICKER}")
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
    for timeframe, target in (("1Min", MINUTE_PICKLE), ("1Day", DAILY_PICKLE)):
        if target.exists() and not force:
            print(f"{target} exists; skipping (pass --force to refetch)")
            continue
        print(f"fetching {TICKER} {timeframe} {START}..{END}")
        fetch(timeframe, target, provider)


if __name__ == "__main__":
    main()
