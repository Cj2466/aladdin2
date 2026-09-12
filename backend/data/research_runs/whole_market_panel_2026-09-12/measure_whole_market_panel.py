"""Step A1.4 — MEASURE what ingest_alpaca_whole_market.py actually built.

Reads directly from backend/data/price_store_alpaca/v1/ (read-only) and
writes whole_market_panel_report.json next to this script. No fabricated
numbers: every figure below is computed from the stored files themselves or
from universe.csv / ingest_run_log.json, both already committed as evidence
of what was asked for and what came back.

Usage:
    ./venv/bin/python data/research_runs/whole_market_panel_2026-09-12/measure_whole_market_panel.py
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.config import MAIN_CHECKOUT_BACKEND_DIR

OUT_DIR = Path(__file__).resolve().parent
UNIVERSE_CSV = OUT_DIR / "universe.csv"
INGEST_LOG_JSON = OUT_DIR / "ingest_run_log.json"
REPORT_JSON = OUT_DIR / "whole_market_panel_report.json"
REPORT_MD = OUT_DIR / "WHOLE_MARKET_PANEL_2026-09-12.md"

ALPACA_STORE_DIR = MAIN_CHECKOUT_BACKEND_DIR / "data" / "price_store_alpaca" / "v1"
EDGAR_FACTS_STORE_DIR = MAIN_CHECKOUT_BACKEND_DIR / "data" / "edgar_facts_store" / "v1"

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_USER_AGENT = "aladdin2 research autoa0792@gmail.com"


def load_universe() -> list[dict]:
    with UNIVERSE_CSV.open() as fh:
        return list(csv.DictReader(fh))


def load_ticker_frame(ticker: str) -> pd.DataFrame | None:
    path = ALPACA_STORE_DIR / f"{ticker}.csv.gz"
    if not path.exists():
        return None
    frame = pd.read_csv(path, index_col=0, parse_dates=True, compression="gzip")
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
    return frame


def sec_cik_to_ticker() -> dict[str, str]:
    with httpx.Client(headers={"User-Agent": SEC_USER_AGENT}, timeout=60.0) as client:
        resp = client.get(SEC_COMPANY_TICKERS_URL)
        resp.raise_for_status()
        payload = resp.json()
    return {f"{row['cik_str']:010d}": row["ticker"].upper() for row in payload.values()}


def main() -> None:
    universe = load_universe()
    universe_symbols = [row["symbol"] for row in universe]
    ingest_log = json.loads(INGEST_LOG_JSON.read_text()) if INGEST_LOG_JSON.exists() else None

    stored_files = sorted(ALPACA_STORE_DIR.glob("*.csv.gz")) if ALPACA_STORE_DIR.exists() else []
    stored_tickers = {p.name[: -len(".csv.gz")] for p in stored_files}

    attempted = set(universe_symbols)
    with_bars = 0
    zero_bars = 0
    total_rows = 0
    total_disk_bytes = sum(p.stat().st_size for p in stored_files)

    per_year_ge200: dict[int, int] = {}
    last_bar_dates: dict[str, pd.Timestamp] = {}
    dollar_volume_by_sec_flag: dict[bool, list[float]] = {True: [], False: []}
    sec_flag_by_symbol = {row["symbol"]: row["in_sec_company_tickers"] == "True" for row in universe}

    window_end = None
    if ingest_log is not None:
        window_end = pd.Timestamp(ingest_log["end_date"])

    for ticker in sorted(attempted):
        frame = load_ticker_frame(ticker)
        if frame is None or frame.empty:
            zero_bars += 1
            continue
        with_bars += 1
        total_rows += len(frame)
        last_bar_dates[ticker] = frame.index.max()

        years = frame.index.year
        for year, count in zip(*np.unique(years, return_counts=True)):
            if count >= 200:
                per_year_ge200[int(year)] = per_year_ge200.get(int(year), 0) + 1

        close = pd.to_numeric(frame["close"], errors="coerce")
        volume = pd.to_numeric(frame["volume"], errors="coerce")
        dollar_vol = (close * volume).replace([np.inf, -np.inf], np.nan).dropna()
        if not dollar_vol.empty:
            flag = sec_flag_by_symbol.get(ticker, False)
            dollar_volume_by_sec_flag[flag].append(float(dollar_vol.median()))

    dead_names: list[dict] = []
    if window_end is not None:
        for ticker, last_date in last_bar_dates.items():
            gap_days = (window_end - last_date).days
            if gap_days > 30:
                dead_names.append({"ticker": ticker, "last_bar_date": last_date.date().isoformat(), "gap_days": int(gap_days)})
    dead_names.sort(key=lambda d: -d["gap_days"])

    def quartiles(values: list[float]) -> dict:
        if not values:
            return {"n": 0, "median": None, "q1": None, "q3": None}
        arr = np.array(values)
        return {
            "n": len(arr),
            "median": float(np.median(arr)),
            "q1": float(np.percentile(arr, 25)),
            "q3": float(np.percentile(arr, 75)),
        }

    # EDGAR facts store coverage: how many of its CIKs map (via SEC's own
    # cik->ticker table) to a ticker actually stored in this panel.
    edgar_ciks = []
    if EDGAR_FACTS_STORE_DIR.exists():
        for p in EDGAR_FACTS_STORE_DIR.glob("CIK*.facts.json.gz"):
            edgar_ciks.append(p.name[len("CIK") : len("CIK") + 10])
    cik_to_ticker = sec_cik_to_ticker()
    edgar_tickers = {cik_to_ticker[cik] for cik in edgar_ciks if cik in cik_to_ticker}
    edgar_covered = edgar_tickers & stored_tickers

    report = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "store_dir": str(ALPACA_STORE_DIR),
        "ingest_window": {
            "start_date": ingest_log["start_date"] if ingest_log else None,
            "end_date": ingest_log["end_date"] if ingest_log else None,
        },
        "symbols_attempted": len(attempted),
        "symbols_with_bars": with_bars,
        "symbols_zero_bars": zero_bars,
        "rows_total": total_rows,
        "on_disk_bytes": total_disk_bytes,
        "on_disk_mb": round(total_disk_bytes / 1e6, 2),
        "breadth_by_year_ge200_bars": dict(sorted(per_year_ge200.items())),
        "dead_names_retained_count": len(dead_names),
        "dead_names_examples": dead_names[:10],
        "dollar_volume_by_sec_flag": {
            "in_sec_company_tickers": quartiles(dollar_volume_by_sec_flag[True]),
            "not_in_sec_company_tickers": quartiles(dollar_volume_by_sec_flag[False]),
        },
        "edgar_facts_store_ciks": len(edgar_ciks),
        "edgar_facts_store_ciks_resolved_to_ticker": len(edgar_tickers),
        "edgar_facts_store_ciks_covered_by_this_panel": len(edgar_covered),
        "edgar_covered_tickers_sample": sorted(edgar_covered)[:20],
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

    md_lines = [
        "# Whole-market Alpaca price panel — 2026-09-12",
        "",
        f"Store: `{ALPACA_STORE_DIR}`",
        f"Window: {report['ingest_window']['start_date']} .. {report['ingest_window']['end_date']}",
        "",
        f"- symbols attempted: {report['symbols_attempted']}",
        f"- symbols with >=1 bar: {report['symbols_with_bars']}",
        f"- symbols with zero bars: {report['symbols_zero_bars']}",
        f"- total rows: {report['rows_total']:,}",
        f"- on-disk size: {report['on_disk_mb']} MB",
        f"- dead names retained (last bar >30 days before window end): {report['dead_names_retained_count']}",
        "",
        "## Breadth by year (symbols with >=200 bars that year)",
        "",
        "| year | symbols with >=200 bars |",
        "|---|---|",
    ]
    for year, count in report["breadth_by_year_ge200_bars"].items():
        md_lines.append(f"| {year} | {count} |")
    md_lines += [
        "",
        "## Dead names retained — examples",
        "",
        "| ticker | last bar date | gap (days) |",
        "|---|---|---|",
    ]
    for row in report["dead_names_examples"]:
        md_lines.append(f"| {row['ticker']} | {row['last_bar_date']} | {row['gap_days']} |")
    md_lines += [
        "",
        "## Median daily dollar volume, by SEC company_tickers membership",
        "",
        f"- in SEC company_tickers.json: {json.dumps(report['dollar_volume_by_sec_flag']['in_sec_company_tickers'])}",
        f"- NOT in SEC company_tickers.json: {json.dumps(report['dollar_volume_by_sec_flag']['not_in_sec_company_tickers'])}",
        "",
        "## EDGAR facts store coverage",
        "",
        f"- CIKs in edgar_facts_store: {report['edgar_facts_store_ciks']}",
        f"- of those, resolved to a ticker via SEC company_tickers.json: {report['edgar_facts_store_ciks_resolved_to_ticker']}",
        f"- of those, covered by this panel: {report['edgar_facts_store_ciks_covered_by_this_panel']}",
    ]
    REPORT_MD.write_text("\n".join(md_lines) + "\n")


if __name__ == "__main__":
    main()
