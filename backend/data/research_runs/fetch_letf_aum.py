"""Fetch and audit ProShares' daily historical NAV / shares-outstanding / AUM CSV.

WHAT THIS IS
============
`A_{i,t-1}` in the rebalancing formula (L^2 - L)*A*r -- Ivanov & Lenkey, FEDS
2014-106, Eq. (6), and the same expression as Shum, Hejazi, Haryanto & Rodier,
Review of Finance 20(6) 2016, Eq. (1) -- is a leveraged ETF's net assets at the
previous close. ProShares publishes it daily for every one of its funds, free,
at https://accounts.profunds.com/etfdata/historical_nav.csv (linked from
proshares.com/resources/data-downloads). This script downloads that file, stores
it under the MAIN checkout with the UTC fetch date in the filename, and writes a
committed manifest recording the SHA-256, the byte count, and the per-ticker row
counts and date ranges of the twelve funds the pre-registration names.

WHY A DATED FILENAME AND A COMMITTED MANIFEST
=============================================
The CSV is the issuer's CURRENT historical record. Restatements are undetectable
from a single snapshot -- PREREGISTRATION section 2 discloses this. Pinning the
SHA-256 of the snapshot a run actually used is the only thing that makes the run
re-checkable at all: a later fetch that differs is then visibly a different file
rather than a silent change of inputs.

TWO TRAPS, BOTH ALREADY PAID FOR
================================
1. TRUNCATED DOWNLOAD. The file is ~52.5 MB and the server is slow. A curl that
   times out mid-stream yields a VALID-LOOKING CSV with a smaller ticker set --
   the tickers are ordered, so a truncation silently drops the tail of the
   alphabet. This script therefore requires >= MIN_BYTES and re-checks the
   ticker set explicitly.
2. LEXICAL DATE SORT. The Date column is MM/DD/YYYY. Sorting it as a STRING puts
   every January 2nd first, which is exactly the artefact that made the
   feasibility memo report first dates of 2008-01-02/2013-01-02 and call the
   missing early years "a real, disclosed gap"; the orchestrator's review section 2
   corrected it -- coverage actually reaches each fund's inception. Dates are
   parsed with an explicit format=%m/%d/%Y here and nowhere sorted as text.

SANITY CHECK (PREREGISTRATION section 2)
========================================
AUM ~= NAV * Shares Outstanding (000) * 1000, within 0.1%, on >= 99% of rows.
The result is reported for the twelve target tickers and written to the manifest
whether it passes or fails; discrepancy rows are listed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import _main_checkout_backend_dir

URL = "https://accounts.profunds.com/etfdata/historical_nav.csv"
MAIN_BACKEND = _main_checkout_backend_dir(BACKEND)
AUM_DIR = MAIN_BACKEND / "data" / "letf_aum"
MANIFEST = BACKEND / "data" / "research_runs" / "letf_rebalancing_2026-09-11" / (
    "aum_snapshot_manifest.json"
)

# Verified 52,552,331 bytes on 2026-09-11 by the orchestrator's re-fetch
# (ORCHESTRATOR_REVIEW_2026-09-11.md section 1). The floor is deliberately below
# that so the file may legitimately grow, but far above any plausible truncation.
MIN_BYTES = 50_000_000
CURL_MAX_TIME = 300

DATE_FORMAT = "%m/%d/%Y"
TICKER_COL = "Ticker"
DATE_COL = "Date"
NAV_COL = "NAV"
SHARES_COL = "Shares Outstanding (000)"
AUM_COL = "Assets Under Management"

# PREREGISTRATION section 2. Leverage from letf_universe.csv (the feasibility
# directory), which the orchestrator re-verified column by column.
TARGET_TICKERS: dict[str, tuple[str, float]] = {
    "SSO": ("SPY", 2.0),
    "SDS": ("SPY", -2.0),
    "UPRO": ("SPY", 3.0),
    "SPXU": ("SPY", -3.0),
    "QLD": ("QQQ", 2.0),
    "QID": ("QQQ", -2.0),
    "TQQQ": ("QQQ", 3.0),
    "SQQQ": ("QQQ", -3.0),
    "UWM": ("IWM", 2.0),
    "TWM": ("IWM", -2.0),
    "URTY": ("IWM", 3.0),
    "SRTY": ("IWM", -3.0),
}

SANITY_TOLERANCE = 0.001  # 0.1%
SANITY_MIN_PASS_FRACTION = 0.99
# The family reads A_{i,t-1}, so the earliest AUM row it can consume is the
# session before the first minute bar (2016-01-04). The identity check is
# reported over the WHOLE file AND over this range separately, because a
# failure confined to years the family never reads is a different fact from one
# inside its sample. Neither is a gate -- PREREGISTRATION section 2 says
# "reported ... else the discrepancy rows are listed", not "or the run stops".
SAMPLE_RANGE_START = "2015-12-01"


def snapshot_path(fetch_date: str) -> Path:
    return AUM_DIR / f"historical_nav_{fetch_date}.csv"


def download(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".csv.partial")
    print(f"downloading {URL} -> {target} (max-time {CURL_MAX_TIME}s)", flush=True)
    result = subprocess.run(
        ["curl", "-sS", "-L", "--max-time", str(CURL_MAX_TIME), "-o", str(tmp), URL],
        check=False,
    )
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"curl failed with exit code {result.returncode}; NOT substituting a source")
    size = tmp.stat().st_size
    if size < MIN_BYTES:
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            f"downloaded only {size:,} bytes, below the {MIN_BYTES:,} floor -- this is a "
            "TRUNCATED download and would silently change the ticker set. Refusing it."
        )
    tmp.replace(target)
    print(f"  {size:,} bytes", flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target_frame(path: Path) -> pd.DataFrame:
    """Rows for the twelve target funds only, with Date parsed as MM/DD/YYYY."""
    frame = pd.read_csv(path, low_memory=False)
    missing_cols = {DATE_COL, TICKER_COL, NAV_COL, SHARES_COL, AUM_COL} - set(frame.columns)
    if missing_cols:
        raise SystemExit(f"CSV missing expected columns {sorted(missing_cols)}")
    frame = frame[frame[TICKER_COL].isin(TARGET_TICKERS)].copy()
    absent = set(TARGET_TICKERS) - set(frame[TICKER_COL].unique())
    if absent:
        raise SystemExit(f"target tickers absent from the CSV: {sorted(absent)} -- truncated file?")
    frame[DATE_COL] = pd.to_datetime(frame[DATE_COL], format=DATE_FORMAT)
    for col in (NAV_COL, SHARES_COL, AUM_COL):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.sort_values([TICKER_COL, DATE_COL]).reset_index(drop=True)


def sanity_check(frame: pd.DataFrame) -> dict:
    """AUM ~= NAV * Shares(000) * 1000 within SANITY_TOLERANCE."""
    usable = frame[frame[NAV_COL].notna() & frame[SHARES_COL].notna() & frame[AUM_COL].notna()]
    implied = usable[NAV_COL] * usable[SHARES_COL] * 1000.0
    denom = usable[AUM_COL].abs()
    relative = (implied - usable[AUM_COL]).abs() / denom.where(denom > 0)
    ok = relative <= SANITY_TOLERANCE
    n = len(usable)
    n_ok = int(ok.sum())
    fraction = (n_ok / n) if n else 0.0
    failures = usable.loc[~ok.fillna(False)]
    worst = failures.assign(rel=relative.loc[failures.index]).nlargest(
        min(25, len(failures)), "rel"
    )
    return {
        "n_rows_checked": n,
        "n_rows_within_0.1pct": n_ok,
        "fraction_within_0.1pct": fraction,
        "passes_99pct_rule": fraction >= SANITY_MIN_PASS_FRACTION,
        "median_relative_error": float(relative.median()) if n else None,
        "max_relative_error": float(relative.max()) if n else None,
        "n_rows_unusable_nan": int(len(frame) - n),
        "worst_rows": [
            {
                "ticker": row[TICKER_COL],
                "date": row[DATE_COL].strftime("%Y-%m-%d"),
                "nav": float(row[NAV_COL]),
                "shares_000": float(row[SHARES_COL]),
                "aum": float(row[AUM_COL]),
                "implied_aum": float(row[NAV_COL] * row[SHARES_COL] * 1000.0),
                "relative_error": float(row["rel"]),
            }
            for _, row in worst.iterrows()
        ],
    }


def per_ticker(frame: pd.DataFrame) -> dict:
    out: dict[str, dict] = {}
    for ticker, group in frame.groupby(TICKER_COL):
        underlying, leverage = TARGET_TICKERS[ticker]
        out[ticker] = {
            "underlying": underlying,
            "leverage": leverage,
            "leverage_sq_minus_l": leverage**2 - leverage,
            "n_rows": len(group),
            "first_date": group[DATE_COL].min().strftime("%Y-%m-%d"),
            "last_date": group[DATE_COL].max().strftime("%Y-%m-%d"),
            "n_duplicate_dates": int(group[DATE_COL].duplicated().sum()),
            "aum_on_first_date": float(group.iloc[0][AUM_COL]),
            "aum_on_last_date": float(group.iloc[-1][AUM_COL]),
        }
    return out


def main() -> None:
    fetch_date = datetime.now(UTC).strftime("%Y-%m-%d")
    target = snapshot_path(fetch_date)
    if target.exists() and "--force" not in sys.argv:
        print(f"{target} exists; skipping download (pass --force to refetch)")
    else:
        download(target)

    frame = load_target_frame(target)
    manifest = {
        "written_utc": datetime.now(UTC).isoformat(),
        "url": URL,
        "snapshot_path": str(target),
        "snapshot_filename": target.name,
        "bytes": target.stat().st_size,
        "sha256": sha256(target),
        "date_format_parsed": DATE_FORMAT,
        "n_rows_target_tickers": len(frame),
        "per_ticker": per_ticker(frame),
        "aum_identity_check": sanity_check(frame),
        "aum_identity_check_sample_range": {
            "range_start": SAMPLE_RANGE_START,
            "why": (
                "the family reads A_{i,t-1}, so only rows from just before the first "
                "minute bar (2016-01-04) onward can enter any result"
            ),
            **sanity_check(frame[frame[DATE_COL] >= pd.Timestamp(SAMPLE_RANGE_START)]),
        },
        "note": (
            "Rows are the issuer's CURRENT historical record; restatements are "
            "undetectable from one snapshot (PREREGISTRATION section 2). The sha256 "
            "pins which snapshot a run used."
        ),
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k: v for k, v in manifest.items() if k != "per_ticker"}, indent=2)[:2000])
    print(f"wrote {MANIFEST}")


if __name__ == "__main__":
    main()
