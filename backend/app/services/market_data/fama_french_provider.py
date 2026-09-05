"""Kenneth R. French's Data Library — the "Fama/French 3 Factors" monthly
series (Mkt-RF, SMB, HML, RF).

WHY THIS EXISTS. cross_sectional_residual_momentum.py orthogonalizes each
stock's monthly excess return against a Fama-French three-factor model, which
is what Blitz, Huij & Martens ("Residual momentum", Journal of Empirical
Finance 18(3), 2011, pp. 506-521, doi:10.1016/j.jempfin.2011.01.003) do. That
requires the actual FF3 series. Nothing else in this codebase had ever needed
it: every other family that wants a "market" builds one from the eligible
cross-section's equal-weighted mean (cross_sectional_ivol), from PCA
eigenportfolios (cross_sectional_eigenportfolio), or uses SPY as a
benchmark/hedge leg rather than as a regression factor. None of those is the
FF3 model, so none of them can test BHM's construction.

THE FILE IS CACHED IN THE REPOSITORY, and that is deliberate rather than
incidental:

  * REPRODUCIBILITY. A research run whose factor inputs are re-downloaded at
    run time is not reproducible — French rebuilds the whole history when CRSP
    is refreshed, so last month's download and today's are different files with
    the same URL. The vintage actually used by a run is therefore committed to
    git alongside the run's results.
  * OFFLINE. The production run must not depend on a third-party website being
    up.
  * PROVENANCE. The cached file is French's ORIGINAL bytes, preamble and all,
    not a cleaned derivative. The first line records which CRSP database built
    it. That line is the vintage stamp, and this module surfaces it rather than
    stripping it.

Downloading is therefore OPT-IN (`allow_download=True`), never the default. A
missing cache raises rather than silently reaching for the network mid-backtest.

UNITS. French publishes PERCENT. Everything this module returns is DECIMAL
(divided by 100), because every return series elsewhere in this codebase is
decimal and a silent percent/decimal mix in a regression would rescale betas by
100x while leaving R^2 — the thing a reader would check — completely unchanged.

MISSING-DATA SENTINELS. French encodes missing observations as -99.99 (and
-999 in some files). Those are NOT valid returns and are converted to NaN, with
a count returned, so an unaware caller cannot regress against a -99.99 that
looks like a plausible float. The vintage cached here has ZERO sentinel cells in
its monthly section — verified at cache time — but the guard is not conditional
on that, because the next vintage is not this one.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# The canonical publisher URL for the monthly 3-factor file.
FAMA_FRENCH_MONTHLY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_CSV.zip"
)

# The committed cache: backend/data/fama_french_factors_monthly.csv.
# Path is resolved from this file so it is independent of the working
# directory a run or a test happens to start in.
FAMA_FRENCH_MONTHLY_CACHE = (
    Path(__file__).resolve().parents[3] / "data" / "fama_french_factors_monthly.csv"
)

FACTOR_COLUMNS: tuple[str, ...] = ("mkt_rf", "smb", "hml", "rf")

# French's own missing-value encodings. Anything at or below this in PERCENT
# units is a sentinel, not a return: the worst real monthly market return in
# the series is roughly -29%, so -90 is comfortably below anything genuine
# while still catching both -99.99 and -999.
_SENTINEL_PERCENT_FLOOR = -90.0

# A monthly factor return outside +/-100% would mean the file is not in the
# units this module thinks it is (or is not this file at all). Checked, not
# assumed — a silent percent/decimal confusion is the exact failure this
# module's docstring warns about, so it is enforced rather than described.
_MAX_PLAUSIBLE_MONTHLY_DECIMAL = 1.0

# Monthly rows are keyed by a 6-digit YYYYMM. The SAME file also contains an
# "Annual Factors: January-December" section keyed by a 4-digit year, with an
# identical column header. Matching on exactly 6 digits is what separates them;
# matching on "a row that starts with digits" would silently splice annual
# returns into a monthly series, which would look entirely plausible.
_MONTHLY_ROW = re.compile(r"^\s*(\d{6})\s*,(.*)$")


@dataclass(frozen=True)
class FamaFrenchMonthly:
    """The parsed monthly FF3 panel plus everything a caller needs to judge
    whether it is fit for their purpose.

    `frame` is indexed by MONTH-END timestamps and carries FACTOR_COLUMNS in
    DECIMAL units. `vintage_line` is French's own first line (e.g. "This file
    was created using the 202606 CRSP database.") — the provenance stamp.
    `n_sentinel_cells` is how many -99.99/-999 cells were converted to NaN.
    """

    frame: pd.DataFrame
    vintage_line: str
    n_sentinel_cells: int
    source_path: Path | None

    @property
    def first_month_end(self) -> pd.Timestamp:
        return self.frame.index[0]

    @property
    def last_month_end(self) -> pd.Timestamp:
        return self.frame.index[-1]


def parse_fama_french_monthly(text: str, *, source_path: Path | None = None) -> FamaFrenchMonthly:
    """Parse French's raw monthly 3-factor CSV — preamble, annual section and
    all — into a decimal, month-end-indexed panel.

    Deliberately parses the ORIGINAL file rather than requiring a pre-cleaned
    one, so that the bytes under version control are the publisher's own and
    the cleaning is code that can be tested.
    """
    lines = text.splitlines()
    if not lines:
        raise ValueError("Fama-French factor file is empty.")

    vintage_line = lines[0].strip()

    records: list[tuple[int, list[str]]] = []
    for line in lines:
        match = _MONTHLY_ROW.match(line)
        if match is None:
            continue  # preamble, blank lines, headers, and the ANNUAL section
        yyyymm = int(match.group(1))
        fields = [f.strip() for f in match.group(2).split(",")]
        records.append((yyyymm, fields))

    if not records:
        raise ValueError(
            "No monthly (YYYYMM) rows found in the Fama-French file. Either the file is a "
            "different series than F-F_Research_Data_Factors, or its layout changed."
        )

    index: list[pd.Timestamp] = []
    values: list[list[float]] = []
    n_sentinel = 0
    for yyyymm, fields in records:
        if len(fields) < len(FACTOR_COLUMNS):
            raise ValueError(
                f"Fama-French monthly row {yyyymm} has {len(fields)} value columns; "
                f"{len(FACTOR_COLUMNS)} ({', '.join(FACTOR_COLUMNS)}) are required."
            )
        year, month = divmod(yyyymm, 100)
        if not 1 <= month <= 12:
            raise ValueError(f"Fama-French row key {yyyymm} is not a valid YYYYMM.")
        row: list[float] = []
        for raw in fields[: len(FACTOR_COLUMNS)]:
            percent = float(raw)
            if percent <= _SENTINEL_PERCENT_FLOOR:
                n_sentinel += 1
                row.append(np.nan)
            else:
                row.append(percent / 100.0)
        index.append(pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0))
        values.append(row)

    frame = pd.DataFrame(values, index=pd.DatetimeIndex(index), columns=list(FACTOR_COLUMNS))
    frame = frame.sort_index()

    if not frame.index.is_unique:
        duplicates = frame.index[frame.index.duplicated()].unique()
        raise ValueError(f"Fama-French monthly file has duplicate months: {list(duplicates)[:5]}")

    finite = frame.to_numpy(dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size and np.abs(finite).max() > _MAX_PLAUSIBLE_MONTHLY_DECIMAL:
        raise ValueError(
            f"Fama-French monthly values reach {np.abs(finite).max():.2f} in DECIMAL units, "
            "which is implausible for a monthly factor return. The file is probably not in "
            "percent units as this parser assumes."
        )

    return FamaFrenchMonthly(
        frame=frame,
        vintage_line=vintage_line,
        n_sentinel_cells=n_sentinel,
        source_path=source_path,
    )


def download_fama_french_monthly(url: str = FAMA_FRENCH_MONTHLY_URL, *, timeout: float = 60.0) -> str:
    """Fetch and unzip the publisher's monthly 3-factor CSV, returning its raw
    text. Never called by the production run — see module docstring on why
    downloading is opt-in — but kept here so refreshing the cache is a
    reviewable code path rather than a shell command in someone's history."""
    import httpx  # local import: the production path never needs the network

    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(
                f"Expected exactly one CSV inside {url}, found {len(names)}: {names}"
            )
        return archive.read(names[0]).decode("utf-8", errors="replace")


def load_fama_french_monthly(
    path: Path | None = None, *, allow_download: bool = False
) -> FamaFrenchMonthly:
    """Load the committed FF3 monthly cache (the default), or optionally
    download and write it.

    `allow_download` defaults to FALSE on purpose: a research run must use the
    committed vintage, not whatever the publisher happens to be serving at run
    time (see module docstring). A missing cache is an error, not a cue to
    reach for the network mid-backtest.
    """
    target = path if path is not None else FAMA_FRENCH_MONTHLY_CACHE
    if target.exists():
        return parse_fama_french_monthly(target.read_text(encoding="utf-8"), source_path=target)

    if not allow_download:
        raise FileNotFoundError(
            f"No cached Fama-French factor file at {target}. The production run deliberately "
            "does NOT download at run time (the vintage a run used must be in git). To refresh "
            "the cache, call load_fama_french_monthly(allow_download=True) explicitly and "
            "commit the result."
        )

    text = download_fama_french_monthly()
    parsed = parse_fama_french_monthly(text, source_path=target)  # validate BEFORE writing
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return parsed


def month_end(day: date) -> pd.Timestamp:
    """The month-end timestamp `day` falls in — the key this module's frame is
    indexed by."""
    return pd.Timestamp(year=day.year, month=day.month, day=1) + pd.offsets.MonthEnd(0)


# --- the momentum factor (the fourth Carhart leg) ----------------------------
#
# WHY THIS IS HERE AND NOT ASSUMED AWAY. Lou (2012), "A Flow-Based Explanation
# for Return Predictability", RFS 25(12), builds his expected-flow-induced-
# trading measure E[FIT] (his Eq.(5)) from each fund's monthly CARHART
# FOUR-FACTOR alpha, and his footnote 11 gives the reason explicitly: he
# excludes raw fund returns from the construction "because the flow-based
# mechanism is also an important driver of the price momentum effect", so a
# raw-return-based measure "would bias the result against finding any return
# predictive power". Substituting a THREE-factor alpha would leave exactly the
# momentum component he is removing inside the signal, which is the confound
# his construction exists to avoid. So the fourth leg is fetched, not skipped.
#
# Same publisher, same units (PERCENT, converted to decimal here), same
# sentinel encoding, and the same committed-vintage discipline as the 3-factor
# file above — for the identical reproducibility reason.

FAMA_FRENCH_MOMENTUM_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Momentum_Factor_CSV.zip"
)

FAMA_FRENCH_MOMENTUM_CACHE = (
    Path(__file__).resolve().parents[3] / "data" / "fama_french_momentum_monthly.csv"
)

MOMENTUM_COLUMN = "mom"


def parse_fama_french_momentum_monthly(
    text: str, *, source_path: Path | None = None
) -> FamaFrenchMonthly:
    """Parse French's raw monthly momentum CSV into a decimal, month-end-indexed
    single-column panel.

    Reuses _MONTHLY_ROW deliberately: this file has the SAME layout as the
    3-factor one — a text preamble, a monthly section keyed by YYYYMM, and an
    "Annual Factors" section keyed by a 4-digit year with an identical column
    header — so the exactly-six-digits match is what keeps annual rows out of a
    monthly series here too.

    Returns the same FamaFrenchMonthly container as the 3-factor loader so the
    vintage line and sentinel count travel with the data identically; its
    `frame` carries one column, MOMENTUM_COLUMN.
    """
    lines = text.splitlines()
    if not lines:
        raise ValueError("Fama-French momentum file is empty.")
    vintage_line = lines[0].strip()

    index: list[pd.Timestamp] = []
    values: list[float] = []
    n_sentinel = 0
    for line in lines:
        match = _MONTHLY_ROW.match(line)
        if match is None:
            continue
        yyyymm = int(match.group(1))
        fields = [f.strip() for f in match.group(2).split(",") if f.strip() != ""]
        if not fields:
            raise ValueError(f"Fama-French momentum row {yyyymm} has no value column.")
        year, month = divmod(yyyymm, 100)
        if not 1 <= month <= 12:
            raise ValueError(f"Fama-French momentum row key {yyyymm} is not a valid YYYYMM.")
        percent = float(fields[0])
        if percent <= _SENTINEL_PERCENT_FLOOR:
            n_sentinel += 1
            values.append(np.nan)
        else:
            values.append(percent / 100.0)
        index.append(pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0))

    if not index:
        raise ValueError(
            "No monthly (YYYYMM) rows found in the Fama-French momentum file. Either the file "
            "is a different series than F-F_Momentum_Factor, or its layout changed."
        )

    frame = pd.DataFrame({MOMENTUM_COLUMN: values}, index=pd.DatetimeIndex(index)).sort_index()
    if not frame.index.is_unique:
        duplicates = frame.index[frame.index.duplicated()].unique()
        raise ValueError(f"Fama-French momentum file has duplicate months: {list(duplicates)[:5]}")

    finite = frame.to_numpy(dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size and np.abs(finite).max() > _MAX_PLAUSIBLE_MONTHLY_DECIMAL:
        raise ValueError(
            f"Fama-French momentum values reach {np.abs(finite).max():.2f} in DECIMAL units, "
            "which is implausible for a monthly factor return."
        )

    return FamaFrenchMonthly(
        frame=frame,
        vintage_line=vintage_line,
        n_sentinel_cells=n_sentinel,
        source_path=source_path,
    )


def load_fama_french_momentum_monthly(
    path: Path | None = None, *, allow_download: bool = False
) -> FamaFrenchMonthly:
    """Load the committed momentum monthly cache, or optionally download it.

    `allow_download` defaults to False for the reason load_fama_french_monthly
    states: a research run must use the vintage that is in git, not whatever
    the publisher is serving at run time."""
    target = path if path is not None else FAMA_FRENCH_MOMENTUM_CACHE
    if target.exists():
        return parse_fama_french_momentum_monthly(
            target.read_text(encoding="utf-8"), source_path=target
        )
    if not allow_download:
        raise FileNotFoundError(
            f"No cached Fama-French momentum file at {target}. The production run deliberately "
            "does NOT download at run time (the vintage a run used must be in git). To refresh "
            "the cache, call load_fama_french_momentum_monthly(allow_download=True) explicitly "
            "and commit the result."
        )
    text = download_fama_french_monthly(FAMA_FRENCH_MOMENTUM_URL)
    parsed = parse_fama_french_momentum_monthly(text, source_path=target)  # validate BEFORE writing
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return parsed


def load_carhart_four_factors(
    *, allow_download: bool = False
) -> tuple[pd.DataFrame, str, str]:
    """(frame, ff3 vintage line, momentum vintage line).

    `frame` is month-end indexed with columns mkt_rf, smb, hml, mom, rf — all
    DECIMAL — restricted to the months BOTH files cover. Carhart, Mark M., "On
    Persistence in Mutual Fund Performance", Journal of Finance 52(1), 1997,
    pp. 57-82: the three Fama-French factors plus a one-year momentum factor.

    The intersection is taken rather than an outer join with NaNs: a
    four-factor regression run on months where the fourth factor is missing is
    a three-factor regression wearing the wrong name."""
    ff3 = load_fama_french_monthly(allow_download=allow_download)
    mom = load_fama_french_momentum_monthly(allow_download=allow_download)
    joined = ff3.frame.join(mom.frame, how="inner")
    return (
        joined[["mkt_rf", "smb", "hml", MOMENTUM_COLUMN, "rf"]],
        ff3.vintage_line,
        mom.vintage_line,
    )
