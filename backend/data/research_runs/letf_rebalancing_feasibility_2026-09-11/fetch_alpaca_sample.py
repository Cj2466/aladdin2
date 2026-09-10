"""FEASIBILITY-ONLY data-availability probe for the LETF rebalancing-flow
candidate (Q4 of FEASIBILITY_MEMO_2026-09-11.md).

Fetches SIP 1-minute bars for SPY, QQQ, IWM, SOXX, XBI, GDX over two short
windows (2016-01-04..2016-01-29 and 2025-06-02..2025-06-27) via the existing
AlpacaProvider.get_stock_bars, exactly as intraday_momentum_spy.py and
data/research_runs/fetch_spy_1min_bars.py already do in this repo. This script
computes NO returns and writes NO signal — it only reports, per ticker/window:
first/last date seen, minutes-per-day (regular session, expect ~390), and the
share of daily dollar volume in the last 30 minutes (15:30-16:00 ET) and in
the final minute (15:59-16:00 bar). Output: a small summary JSON. Full bar
data is written to the session scratchpad (gitignored, not committed), per the
orchestrator's instruction, NOT to the repo.

Run from backend/:
  set -a; . /Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/.env; set +a
  python data/research_runs/letf_rebalancing_feasibility_2026-09-11/fetch_alpaca_sample.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.market_data.alpaca_provider import AlpacaProvider

SCRATCHPAD = Path(
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
    "578690ea-ca6c-4d87-9e97-95cd1d64495e/scratchpad/letf_bars"
)
SCRATCHPAD.mkdir(parents=True, exist_ok=True)

TICKERS = ["SPY", "QQQ", "IWM", "SOXX", "XBI", "GDX"]
WINDOWS = [
    ("2016_jan", date(2016, 1, 4), date(2016, 1, 29)),
    ("2025_jun", date(2025, 6, 2), date(2025, 6, 27)),
]


def summarize(ticker: str, window_name: str, df) -> dict:
    if df is None or df.empty:
        return {"available": False}
    df = df.sort_index()
    dollar_vol = df["close"] * df["volume"]
    df = df.assign(dollar_vol=dollar_vol)
    days = df.index.date
    unique_days = sorted(set(days))
    per_day_minutes = []
    last30_shares = []
    last_minute_shares = []
    for d in unique_days:
        day_df = df[df.index.date == d]
        per_day_minutes.append(len(day_df))
        total_dv = day_df["dollar_vol"].sum()
        if total_dv <= 0:
            continue
        last30 = day_df.between_time("15:30", "15:59")["dollar_vol"].sum()
        # final regular-session bar is the one whose bar-start time is 15:59
        # (bar timestamps are bar-START times per AlpacaProvider docstring)
        last_min = day_df.between_time("15:59", "15:59")["dollar_vol"].sum()
        last30_shares.append(float(last30 / total_dv))
        last_minute_shares.append(float(last_min / total_dv))
    return {
        "available": True,
        "first_date": str(unique_days[0]),
        "last_date": str(unique_days[-1]),
        "n_days": len(unique_days),
        "mean_minutes_per_day": (
            sum(per_day_minutes) / len(per_day_minutes) if per_day_minutes else None
        ),
        "min_minutes_per_day": min(per_day_minutes) if per_day_minutes else None,
        "max_minutes_per_day": max(per_day_minutes) if per_day_minutes else None,
        "mean_last30min_dollar_vol_share": (
            sum(last30_shares) / len(last30_shares) if last30_shares else None
        ),
        "mean_last_minute_dollar_vol_share": (
            sum(last_minute_shares) / len(last_minute_shares)
            if last_minute_shares
            else None
        ),
        "n_days_with_volume": len(last30_shares),
    }


def main() -> None:
    provider = AlpacaProvider()
    results: dict[str, dict] = {}
    for window_name, start, end in WINDOWS:
        bars, missing = provider.get_stock_bars(
            TICKERS, "1Min", start, end, regular_session_only=True, feed="sip"
        )
        if missing:
            print(f"[{window_name}] MISSING tickers: {missing}", file=sys.stderr)
        for ticker in TICKERS:
            df = bars.get(ticker)
            key = f"{ticker}_{window_name}"
            results[key] = summarize(ticker, window_name, df)
            if df is not None and not df.empty:
                pkl_path = SCRATCHPAD / f"{ticker}_{window_name}_1Min.pkl"
                df.to_pickle(pkl_path)
                print(f"[{window_name}] {ticker}: {len(df)} bars -> {pkl_path}")
            else:
                print(f"[{window_name}] {ticker}: NO DATA")

    out_path = Path(__file__).resolve().parent / "alpaca_minute_sample.json"
    with open(out_path, "w") as f:
        json.dump(
            {
                "tickers": TICKERS,
                "windows": {name: [str(s), str(e)] for name, s, e in WINDOWS},
                "note": (
                    "Data-availability facts only (Q4). No return statistics. "
                    "Bar timestamps are bar-START times (AlpacaProvider "
                    "docstring); 'last 30 minutes' = between_time(15:30,15:59) "
                    "inclusive of the 15:59 bar-start (which covers 15:59-16:00 "
                    "trading), 'last minute' = the single 15:59 bar-start row."
                ),
                "results": results,
            },
            f,
            indent=2,
        )
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
