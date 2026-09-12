"""
M3a - measure survivorship of the free Yahoo Finance (.BK) feed against SET's
own published delisted-securities list (2000-2026 subset).

Source of the delisted list: SET's official page
    https://www.set.or.th/en/market/information/securities-list/delisted-list
fetched via a headless browser (the JSON API behind it is client-rendered and
was not discoverable from static HTML; the page itself returned all 346 rows
directly in the accessibility tree, no API call needed). Raw scraped rows are
committed at m3_sources/set_delisted_list_scraped_rows.json (SHA-256 in
m3_SOURCES.md) together with the SSR HTML shell as fetched.

For every delisted symbol with a delisting_date in [2000-01-01, 2026-12-31],
this script:
  1. Builds the plain Yahoo ticker "<SYM>.BK" (no attempt at NVDR/foreign-board
     suffixes -- the review's finding was about the ordinary line).
  2. Fetches full history via yfinance (period='max').
  3. Records bar count, first bar date, last bar date.
  4. Flags "retained" = last bar is within 30 days of the SET delisting_date
     (i.e. the feed's history plausibly runs up to the real delisting).
     Flags "zero_bars" = no bars returned at all.
     Anything in between (bars exist but end well before OR after the SET
     delisting date) is reported separately, not folded into either bucket.

This is a MEASUREMENT only -- no strategy, no DB row. Output:
  m3_survivorship_output.json  (full per-symbol detail)
  m3_survivorship_output.txt   (human-readable summary by delisting year)
"""
import csv
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

import yfinance as yf

HERE = Path(__file__).parent
CSV_PATH = HERE / "m3_delisted_list.csv"
OUT_JSON = HERE / "m3_survivorship_output.json"
OUT_TXT = HERE / "m3_survivorship_output.txt"

DATE_FMT = "%d %b %Y"  # e.g. "05 Oct 2020"


def parse_date(s: str):
    s = s.strip()
    if not s or s == "-":
        return None
    return datetime.strptime(s, DATE_FMT).date()  # noqa: DTZ007 - date-only, no tz applicable


def load_universe():
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            delist_dt = parse_date(row["delisting_date"])
            if delist_dt is None:
                continue
            if not (date(2000, 1, 1) <= delist_dt <= date(2026, 12, 31)):
                continue
            rows.append(
                {
                    "symbol": row["symbol"].strip(),
                    "company_name": row["company_name"].strip(),
                    "market": row["market"].strip(),
                    "first_trading_date": row["first_trading_date"].strip(),
                    "delisting_date": row["delisting_date"].strip(),
                    "delisting_dt": delist_dt,
                    "delisting_year": delist_dt.year,
                    "reason": row["reason"].strip(),
                }
            )
    return rows


def probe_symbol(symbol: str):
    yh_ticker = f"{symbol}.BK"
    result = {
        "yahoo_ticker": yh_ticker,
        "bars": 0,
        "first_bar": None,
        "last_bar": None,
        "error": None,
    }
    try:
        tk = yf.Ticker(yh_ticker)
        hist = tk.history(period="max", auto_adjust=False)
        result["bars"] = len(hist)
        if len(hist) > 0:
            result["first_bar"] = hist.index[0].strftime("%Y-%m-%d")
            result["last_bar"] = hist.index[-1].strftime("%Y-%m-%d")
    except Exception as e:  # noqa: BLE001 - record and continue, this is a probe
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def main():
    universe = load_universe()
    print(f"Universe: {len(universe)} delisted symbols with delisting_date in 2000-2026", file=sys.stderr)

    detail = []
    for i, row in enumerate(universe):
        probe = probe_symbol(row["symbol"])
        rec = {**row, **probe}
        rec["delisting_dt"] = row["delisting_dt"].isoformat()

        zero_bars = probe["bars"] == 0
        retained = False
        if probe["last_bar"] is not None:
            last_bar_dt = datetime.strptime(probe["last_bar"], "%Y-%m-%d").date()  # noqa: DTZ007 - date-only
            retained = abs((last_bar_dt - row["delisting_dt"]).days) <= 30
        rec["zero_bars"] = zero_bars
        rec["retained_within_30d"] = retained
        detail.append(rec)

        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(universe)} probed", file=sys.stderr)
        time.sleep(0.05)  # be polite to the free endpoint

    # ---- aggregate ----
    total = len(detail)
    zero = sum(1 for r in detail if r["zero_bars"])
    retained = sum(1 for r in detail if r["retained_within_30d"])
    other = total - zero - retained

    by_year = {}
    for r in detail:
        y = r["delisting_year"]
        by_year.setdefault(y, {"total": 0, "zero_bars": 0, "retained": 0, "other": 0})
        by_year[y]["total"] += 1
        if r["zero_bars"]:
            by_year[y]["zero_bars"] += 1
        elif r["retained_within_30d"]:
            by_year[y]["retained"] += 1
        else:
            by_year[y]["other"] += 1

    summary = {
        "source": "https://www.set.or.th/en/market/information/securities-list/delisted-list",
        "fetched": "2026-09-12",
        "total_symbols_probed": total,
        "zero_bars_count": zero,
        "zero_bars_fraction": zero / total if total else None,
        "retained_within_30d_count": retained,
        "retained_within_30d_fraction": retained / total if total else None,
        "other_count": other,
        "other_fraction": other / total if total else None,
        "by_delisting_year": {str(k): v for k, v in sorted(by_year.items())},
    }

    OUT_JSON.write_text(json.dumps({"summary": summary, "detail": detail}, indent=1))

    lines = []
    lines.append("M3a survivorship measurement -- SET delisted list x Yahoo .BK feed")
    lines.append(f"Source: {summary['source']}  (fetched {summary['fetched']})")
    lines.append(f"Total delisted symbols probed (delisting 2000-2026): {total}")
    lines.append(f"  zero bars returned:            {zero} ({summary['zero_bars_fraction']:.1%})")
    lines.append(f"  retained (last bar <=30d of delisting): {retained} ({summary['retained_within_30d_fraction']:.1%})")
    lines.append(f"  other (bars exist, but not near delisting date): {other} ({summary['other_fraction']:.1%})")
    lines.append("")
    lines.append(f"{'year':>6} {'total':>6} {'zero':>6} {'retained':>9} {'other':>6}")
    for y, d in sorted(by_year.items()):
        lines.append(f"{y:>6} {d['total']:>6} {d['zero_bars']:>6} {d['retained']:>9} {d['other']:>6}")
    OUT_TXT.write_text("\n".join(lines) + "\n")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
