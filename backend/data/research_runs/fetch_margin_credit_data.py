"""One-shot fetcher for the margin-credit family's two external inputs.

Writes THREE git-durable snapshots under backend/data/margin_credit/ so that
every later run of this family replays byte-identical inputs and never depends
on FINRA or FRED being reachable (or on either of them not silently revising
history under us):

  finra_margin_statistics.csv        the FINRA Rule 4521(d) monthly aggregate
                                     margin statistics, parsed from FINRA's own
                                     .xlsx, plus the raw .xlsx alongside it.
  gdp_nominal_latest_vintage.csv     nominal GDP (FRED `GDP`, Billions of
                                     Dollars, SAAR), most recent vintage --
                                     the IN-SAMPLE scaler.
  gdp_nominal_realtime.csv           for every month-end signal date, the GDP
                                     quarter and value that were ACTUALLY
                                     PUBLISHED as of that date, resolved from
                                     ALFRED real-time vintages -- the
                                     OUT-OF-SAMPLE scaler.

WHY A SEPARATE FETCH STEP. The screening module must be deterministic and
offline; a family whose numbers change because a vendor re-cut a series is not
reproducible. Same reason data/price_store/ exists.

ALFRED VINTAGES ARE FREE AND SUFFICIENT, verified live 2026-09-06: the FRED
`GDP` series exposes 414 vintage dates from 1991-12-04 onward, which fully
covers the FINRA sample (1997-01 onward). Deuskar/Kumar/Poland used the
Philadelphia Fed's real-time dataset; ALFRED is the same idea from a different
custodian, and it removes the paper's own real-2009-dollars -> nominal
conversion step because FRED's `GDP` is already nominal.

Run from backend/ with:  ./venv/bin/python data/research_runs/fetch_margin_credit_data.py
"""

from __future__ import annotations

import calendar
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, outside this worktree ({_BACKEND})."
    )

from app.config import settings

OUT_DIR = _BACKEND / "data" / "margin_credit"

# Found live on FINRA's own page 2026-09-06 by scraping the href rather than
# guessing the path; the page is https://www.finra.org/rules-guidance/
# key-topics/margin-accounts/margin-statistics and it links this file.
FINRA_XLSX_URL = "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"

# Pinned so a silently-reshaped upstream file fails loudly instead of quietly
# changing this family's numbers. Update deliberately, never to make a run pass.
FINRA_EXPECTED_HEADER = (
    "Year-Month",
    "Debit Balances in Customers' Securities Margin Accounts",
    "Free Credit Balances in Customers' Cash Accounts",
    "Free Credit Balances in Customers' Securities Margin Accounts",
)

FRED_BASE = "https://api.stlouisfed.org/fred/"
GDP_SERIES = "GDP"

# The first month for which a GDP vintage is resolved. One year before the
# FINRA series starts, so nothing at the boundary is missing.
REALTIME_FIRST_MONTH = (1996, 1)


def _fred(path: str, **params: str) -> dict:
    if not settings.fred_api_key:
        raise SystemExit("FRED_API_KEY is not configured; cannot fetch GDP vintages.")
    params["api_key"] = settings.fred_api_key
    params["file_type"] = "json"
    url = FRED_BASE + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def fetch_finra() -> list[dict[str, str]]:
    """Downloads FINRA's .xlsx and parses it WITHOUT openpyxl.

    The file is a single-sheet, inline-string workbook with no sharedStrings
    part, so a 20-line zip+regex read is both sufficient and one fewer
    dependency to pin. The header assertion below is what makes that safe."""
    req = urllib.request.Request(
        FINRA_XLSX_URL, headers={"User-Agent": "aladdin2-research/1.0 (margin-credit family)"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "margin-statistics.xlsx").write_bytes(raw)
    print(f"FINRA xlsx: {len(raw)} bytes -> data/margin_credit/margin-statistics.xlsx")

    z = zipfile.ZipFile(OUT_DIR / "margin-statistics.xlsx")
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    parsed: list[dict[str, str]] = []
    for row_xml in re.findall(r"<row[^>]*>.*?</row>", sheet, re.DOTALL):
        cells: dict[str, str] = {}
        for col, _rn, body in re.findall(r'<c r="([A-Z]+)(\d+)"[^>]*>(.*?)</c>', row_xml, re.DOTALL):
            inline = re.search(r"<is><t[^>]*>(.*?)</t></is>", body, re.DOTALL)
            if inline is not None:
                cells[col] = inline.group(1)
                continue
            numeric = re.search(r"<v>(.*?)</v>", body, re.DOTALL)
            if numeric is not None:
                cells[col] = numeric.group(1)
        parsed.append(cells)

    header = tuple(parsed[0].get(c, "") for c in ("A", "B", "C", "D"))
    if header != FINRA_EXPECTED_HEADER:
        raise SystemExit(
            "FINRA workbook header changed. Expected\n  "
            + "\n  ".join(FINRA_EXPECTED_HEADER)
            + "\ngot\n  "
            + "\n  ".join(header)
            + "\nRefusing to parse a file whose columns may no longer mean what this "
            "family thinks they mean."
        )

    rows = []
    for cells in parsed[1:]:
        ym = cells.get("A", "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}", ym):
            continue
        rows.append(
            {
                "year_month": ym,
                "debit_margin_musd": cells.get("B", "").strip(),
                "free_credit_cash_musd": cells.get("C", "").strip(),
                "free_credit_margin_musd": cells.get("D", "").strip(),
            }
        )
    rows.sort(key=lambda r: r["year_month"])

    path = OUT_DIR / "finra_margin_statistics.csv"
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "year_month",
                "debit_margin_musd",
                "free_credit_cash_musd",
                "free_credit_margin_musd",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(
        f"FINRA parsed: {len(rows)} months {rows[0]['year_month']}..{rows[-1]['year_month']} "
        f"-> {path.name}"
    )
    return rows


def fetch_gdp_latest() -> None:
    obs = _fred("series/observations", series_id=GDP_SERIES, observation_start="1990-01-01")[
        "observations"
    ]
    rows = [
        {"quarter_start": o["date"], "gdp_nominal_bnusd": o["value"]}
        for o in obs
        if o["value"] != "."
    ]
    path = OUT_DIR / "gdp_nominal_latest_vintage.csv"
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["quarter_start", "gdp_nominal_bnusd"])
        w.writeheader()
        w.writerows(rows)
    print(
        f"GDP latest vintage: {len(rows)} quarters "
        f"{rows[0]['quarter_start']}..{rows[-1]['quarter_start']} -> {path.name}"
    )


def _month_ends(first: tuple[int, int], last_inclusive: date) -> list[date]:
    out = []
    y, m = first
    while True:
        d = date(y, m, calendar.monthrange(y, m)[1])
        if d > last_inclusive:
            break
        out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def fetch_gdp_realtime(last_month_end: date) -> None:
    """For every month-end, what an investor could actually see that day.

    THE RULE, and it is the whole anti-look-ahead point of this file:
    query ALFRED with realtime_start = realtime_end = the month-end date, which
    returns the series EXACTLY as it stood on that date, then take the
    SECOND-most-recent quarter present.

    The second-most-recent, not the most recent, implements Deuskar/Kumar/
    Poland's own extra lag (p.12): "The GDP numbers used are further lagged...
    because there seems to be the largest change in value from the first to
    second revision in GDP announcements." Their worked example -- a prediction
    in August 1997 uses the Q1 1997 GDP value -- is reproduced exactly by this
    rule, and is asserted in the test suite."""
    rows = []
    for d in _month_ends(REALTIME_FIRST_MONTH, last_month_end):
        payload = _fred(
            "series/observations",
            series_id=GDP_SERIES,
            realtime_start=d.isoformat(),
            realtime_end=d.isoformat(),
        )
        obs = [o for o in payload["observations"] if o["value"] != "."]
        if len(obs) < 2:
            raise SystemExit(f"ALFRED returned fewer than 2 GDP observations as of {d}")
        chosen = obs[-2]  # second-most-recent published quarter
        rows.append(
            {
                "signal_month_end": d.isoformat(),
                "gdp_quarter_start": chosen["date"],
                "gdp_nominal_bnusd": chosen["value"],
                "latest_quarter_available": obs[-1]["date"],
            }
        )
        time.sleep(0.15)  # stay well inside FRED's 120 req/min
    path = OUT_DIR / "gdp_nominal_realtime.csv"
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "signal_month_end",
                "gdp_quarter_start",
                "gdp_nominal_bnusd",
                "latest_quarter_available",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(
        f"GDP real-time: {len(rows)} month-ends "
        f"{rows[0]['signal_month_end']}..{rows[-1]['signal_month_end']} -> {path.name}"
    )
    aug97 = [r for r in rows if r["signal_month_end"].startswith("1997-08")]
    if aug97:
        print(
            "  paper's own worked example (p.12), reproduced: prediction in August 1997 uses "
            f"GDP quarter {aug97[0]['gdp_quarter_start']} "
            f"(latest then available: {aug97[0]['latest_quarter_available']})"
        )


def main() -> int:
    finra = fetch_finra()
    fetch_gdp_latest()
    last_ym = finra[-1]["year_month"]
    y, m = int(last_ym[:4]), int(last_ym[5:7])
    # Two extra months so every FINRA month has a signal date under the
    # 2-month reporting lag -- but never past today, because ALFRED rejects a
    # realtime_start in the future and a "vintage" that does not exist yet is
    # not a thing this family is allowed to invent.
    y2, m2 = (y + 1, m - 10) if m > 10 else (y, m + 2)
    wanted = date(y2, m2, calendar.monthrange(y2, m2)[1])
    today = date.today()
    last_complete_month_end = date(today.year, today.month, 1) - timedelta(days=1)
    fetch_gdp_realtime(min(wanted, last_complete_month_end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
