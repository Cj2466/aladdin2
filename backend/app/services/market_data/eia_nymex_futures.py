"""Daily NYMEX energy futures settlement prices by CONTRACT POSITION
("Contract 1".."Contract 4") from the U.S. Energy Information Administration
(eia.gov) -- an official U.S. government publication, keyless, free.
Built 2026-09-07 for the futures-data-sourcing task.

EVERY CLAIM BELOW WAS VERIFIED LIVE 2026-09-07 IN THIS SESSION.

WHAT EIA PUBLISHES (all read live, row counts from the downloaded files)
  series    instrument                      first row    last row
  RCLC1..4  Cushing OK WTI crude, $/bbl     1983-04-04   2024-04-05  (C1: 10,297 rows)
  RNGC1..4  Henry Hub natural gas, $/MMBtu  1994-01-13   2024-04-05  (C1: 7,592)
  EER_EPD2F_PE1..4_Y35NY_DPG  NY Harbor No.2 heating oil, $/gal  1980-01-02 .. 2024-04-05 (C1: 11,099)
  EER_EPMRR_PE1..4_Y35NY_DPG  NY Harbor RBOB gasoline, $/gal      2005-10-03 .. 2024-04-05 (C1: 4,645)
  EER_EPLLPA_PE1..2_Y44MB_DPG Mont Belvieu propane (ends 2009-09-18; not used)

THE SERIES STOP ON 2024-04-05. EIA's own page title now reads "NYMEX Futures
Prices (Futures prices after April 5, 2024, are not available)"
(https://www.eia.gov/dnav/pet/PET_PRI_FUT_S1_M.htm, read live 2026-09-07).
This coincides with CME ending free end-of-day licences for its exchanges
(WatersTechnology, "CME rankles market data users with licensing changes").
So this source is a 1983/1994/2005-to-2024-04 HISTORY, not a live feed.

WHAT "CONTRACT 1" MEANS, in EIA's own definition (glossary text on the
series pages): Contract 1 is "the futures contract specifying the earliest
delivery date", Contract 2 the next, and so on -- i.e. a POSITIONAL
front-month series, NOT an individual contract. Each series is therefore
a splice (Contract 1 changes identity at every expiry), exactly the shape
Yahoo's `=F` has, and it is used here in two ways only:
  (1) as an INDEPENDENT CROSS-CHECK of the SPAN per-contract settlements
      (an EIA Contract-1 print on date t must equal SPAN's nearest
      unexpired contract's settle on t -- it does, to the cent, on every
      date measured), and
  (2) as pre-2013 energy history whose roll dates can be recovered from
      the C1/C2 crossings; the run script measures how far that goes.

DOWNLOAD FORMATS (both keyless):
  * https://www.eia.gov/dnav/{pet|ng}/hist_xls/<SERIES>d.xls -- legacy
    .xls, sheet "Data 1", row 0 title, row 1 sourcekey, rows 3+ = date,
    value. Needs the `xlrd` package, which this project does NOT install;
    read_xls() is provided for a caller that has it.
  * https://www.eia.gov/dnav/{pet|ng}/hist/<SERIES>d.htm -- the same data
    as a weekly HTML table ("Week Of" + Mon..Fri columns), parsed here
    with pandas.read_html (lxml is already a dependency). Cross-checked
    against the .xls in this session: identical values and dates.

THE NEGATIVE WTI PRINT IS PRESENT: RCLC1 carries -37.63 on 2020-04-20.
This module never drops it; price_store.drop_implausible would.

Licence: U.S. federal government work; EIA states its data are in the
public domain (https://www.eia.gov/about/copyrights_reuse.php).
"""

from __future__ import annotations

import io
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

EIA_HIST_HTML = "https://www.eia.gov/dnav/{area}/hist/{series}d.htm"
EIA_HIST_XLS = "https://www.eia.gov/dnav/{area}/hist_xls/{series}d.xls"
EIA_COPYRIGHT_URL = "https://www.eia.gov/about/copyrights_reuse.php"
EIA_DISCONTINUATION_URL = "https://www.eia.gov/dnav/pet/PET_PRI_FUT_S1_M.htm"
USER_AGENT = "aladdin2-research/0.1 (contact: autoa0792@gmail.com)"
MIN_SECONDS_BETWEEN_REQUESTS = 1.0


@dataclass(frozen=True)
class EiaSeries:
    globex: str
    position: int  # 1..4 = EIA "Contract N"
    series_id: str
    area: str  # "pet" or "ng"
    unit: str


EIA_SERIES: list[EiaSeries] = [
    *[EiaSeries("CL", n, f"RCLC{n}", "pet", "USD per barrel") for n in (1, 2, 3, 4)],
    *[EiaSeries("NG", n, f"RNGC{n}", "ng", "USD per MMBtu") for n in (1, 2, 3, 4)],
    *[EiaSeries("HO", n, f"EER_EPD2F_PE{n}_Y35NY_DPG", "pet", "USD per gallon") for n in (1, 2, 3, 4)],
    *[EiaSeries("RB", n, f"EER_EPMRR_PE{n}_Y35NY_DPG", "pet", "USD per gallon") for n in (1, 2, 3, 4)],
]

_WEEK_OF = re.compile(r"^(\d{4})\s+([A-Z][a-z]{2})-\s*(\d{1,2})\s+to\s+")
_MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def parse_weekly_html(html: str) -> pd.Series:
    """EIA's weekly layout -> a daily Series indexed by date. The 'Week Of'
    cell gives the Monday; Mon..Fri columns are the five weekdays. Blank
    cells (holidays) are dropped, not filled."""
    tables = pd.read_html(io.StringIO(html))
    table = None
    for t in tables:
        cols = [str(c) for c in t.columns]
        if "Week Of" in cols and "Mon" in cols and "Fri" in cols:
            table = t
            break
    if table is None:
        raise ValueError("no 'Week Of' table found in EIA page")
    values: dict[pd.Timestamp, float] = {}
    for _, row in table.iterrows():
        m = _WEEK_OF.match(str(row["Week Of"]))
        if not m:
            continue
        year, mon, day = int(m.group(1)), _MONTHS[m.group(2)], int(m.group(3))
        monday = pd.Timestamp(year=year, month=mon, day=day)
        for offset, col in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
            v = pd.to_numeric(row.get(col), errors="coerce")
            if pd.notna(v):
                values[monday + pd.Timedelta(days=offset)] = float(v)
    out = pd.Series(values, dtype=float).sort_index()
    out.index.name = "date"
    return out


def read_xls(path: Path) -> pd.Series:
    """Legacy .xls reader (requires xlrd, not a project dependency)."""
    frame = pd.read_excel(path, sheet_name="Data 1", header=None)
    data = frame.iloc[3:, :2].dropna()
    out = pd.Series(data.iloc[:, 1].astype(float).values, index=pd.to_datetime(data.iloc[:, 0]))
    out.index.name = "date"
    return out.sort_index()


def fetch_series_html(series: EiaSeries, *, timeout: int = 120) -> str:
    url = EIA_HIST_HTML.format(area=series.area, series=series.series_id)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("latin-1")


def fetch_all(store_dir: Path, series: list[EiaSeries] = EIA_SERIES) -> dict[str, dict]:
    """Download every series as HTML, parse, write <store>/eia/<SERIES>.csv,
    return per-series coverage for the manifest."""
    out_dir = store_dir / "eia"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, dict] = {}
    for s in series:
        html = fetch_series_html(s)
        values = parse_weekly_html(html)
        path = out_dir / f"{s.series_id}.csv"
        values.rename("value").to_csv(path)
        report[s.series_id] = {
            "globex": s.globex,
            "position": s.position,
            "unit": s.unit,
            "rows": len(values),
            "first": str(values.index.min().date()),
            "last": str(values.index.max().date()),
            "url": EIA_HIST_HTML.format(area=s.area, series=s.series_id),
        }
        time.sleep(MIN_SECONDS_BETWEEN_REQUESTS)
    return report


def load_series(store_dir: Path, series_id: str) -> pd.Series:
    frame = pd.read_csv(store_dir / "eia" / f"{series_id}.csv", parse_dates=["date"], index_col="date")
    return frame["value"].astype(float)
