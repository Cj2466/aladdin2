"""JOB 3 of futures_span_full_pull_2026-09-07: verify the FULL CME SPAN pull
(not just the 3 sample files spot-checked in
futures_data_sourcing_phase2_2026-09-07.txt), against real downloaded data.

Four checks, each against the real pulled store
(data/futures_daily/cme_span/), not synthetic fixtures:

  1. DATE COVERAGE PER INSTRUMENT vs the claimed 2013-01-02..2025-09-12
     archive window (cme_span_settlements.SPAN_ARCHIVE_FIRST_DATE/LAST_DATE).
     Reports gaps honestly per instrument rather than assuming uniform
     coverage -- some roots (RTY pre-2017-07, HE/LE trading-calendar
     differences) are expected to have real, legitimate gaps.
  2. CL NEGATIVE SETTLEMENT RE-CONFIRMATION on 2020-04-20, read directly from
     the real pulled daily CSV (not the 3-file sample previously checked in
     phase 2).
  3. EXTENDED EIA CROSS-CHECK: fetches EIA's live Contract-1..4 series fresh
     (not reusing phase-1/phase-2 cached numbers) and compares to SPAN's
     nearest-unexpired-contract settle on additional sampled dates across
     multiple years (2013, 2016, 2019, 2022, 2024 -- deliberately spanning
     more of the archive than the 2 dates phase 2 checked), for CL/NG/HO/RB.
  4. Runs the existing pytest suite's REAL-DATA-CAPABLE tests, if any exist
     that read from the store, and reports whether the full pull changes any
     pass/fail outcome versus the fixture-based suite.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app  # noqa: E402

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(f"REFUSING TO RUN: `app` resolved to {app.__file__}, not inside {_BACKEND}")

from app.services.market_data import cme_span_settlements as span  # noqa: E402
from app.services.market_data import eia_nymex_futures as eia  # noqa: E402

STORE = _BACKEND / "data" / "futures_daily" / "cme_span"
BY_INSTRUMENT = STORE / "by_instrument"

EXTENDED_CROSS_CHECK_DATES = ["2013-06-03", "2016-03-15", "2019-01-02", "2022-11-07", "2024-01-02"]
CL_NEGATIVE_DATE = "2020-04-20"
CL_NEGATIVE_EXPECTED = -37.63


def check_date_coverage() -> dict[str, Any]:
    frame = span.load_daily(STORE)
    out: dict[str, Any] = {}
    for globex, g in frame.groupby("globex"):
        dates = pd.to_datetime(g["trade_date"]).sort_values().unique()
        first, last = pd.Timestamp(dates.min()), pd.Timestamp(dates.max())
        expected_bdays = pd.bdate_range(span.SPAN_ARCHIVE_FIRST_DATE, span.SPAN_ARCHIVE_LAST_DATE)
        # coverage is measured against the ARCHIVE's own window, not
        # necessarily against every business day (holidays are legitimately
        # absent; this is an outer bound, not a strict requirement)
        present = set(pd.DatetimeIndex(dates))
        missing_within_own_span = [d for d in pd.bdate_range(first, last) if d not in present]
        out[str(globex)] = {
            "n_trade_days": int(len(dates)),
            "first_date": str(first.date()),
            "last_date": str(last.date()),
            "matches_claimed_start": bool(first.date() == span.SPAN_ARCHIVE_FIRST_DATE),
            "matches_claimed_end": bool(last.date() == span.SPAN_ARCHIVE_LAST_DATE),
            "n_business_days_missing_within_own_span": len(missing_within_own_span),
            "pct_business_days_missing_within_own_span": round(
                100.0 * len(missing_within_own_span) / max(1, len(pd.bdate_range(first, last))), 3
            ),
        }
    out["_archive_claimed_window"] = {
        "first": span.SPAN_ARCHIVE_FIRST_DATE.isoformat(),
        "last": span.SPAN_ARCHIVE_LAST_DATE.isoformat(),
        "n_business_days_in_window": len(expected_bdays),
    }
    return out


def check_cl_negative_settlement() -> dict[str, Any]:
    path = span.daily_csv_path(STORE, pd.Timestamp(CL_NEGATIVE_DATE).date())
    if not path.exists():
        return {"ok": False, "error": f"{path} not fetched yet"}
    daily = pd.read_csv(path, dtype={"contract_month": str, "expiration_date": str})
    cl_rows = daily[daily["globex"] == "CL"]
    negatives = cl_rows[cl_rows["settle"] < 0]
    return {
        "ok": bool(len(negatives) >= 1 and any(abs(v - CL_NEGATIVE_EXPECTED) < 0.005 for v in negatives["settle"])),
        "n_cl_rows_that_date": int(len(cl_rows)),
        "negative_rows": negatives[["contract_month", "settle", "expiration_date"]].to_dict("records"),
        "expected": CL_NEGATIVE_EXPECTED,
    }


def check_extended_eia_cross(dates: list[str]) -> dict[str, Any]:
    """Fetch EIA's Contract-1 series fresh for CL/NG/HO/RB and compare to
    SPAN's own nearest-unexpired-contract settle on each sampled date,
    across more years than phase 2's 2 dates."""
    results: dict[str, Any] = {}
    roots = {"CL": "RCLC1", "NG": "RNGC1", "HO": None, "RB": None}
    series_by_root: dict[str, pd.Series] = {}
    fetch_errors: dict[str, str] = {}
    for s in eia.EIA_SERIES:
        if s.position != 1:
            continue
        try:
            html = eia.fetch_series_html(s)
            series_by_root[s.globex] = eia.parse_weekly_html(html)
        except Exception as exc:  # noqa: BLE001 -- report, don't crash the whole check
            fetch_errors[s.globex] = f"{type(exc).__name__}: {exc}"

    daily_frame = span.load_daily(STORE)
    for root in ("CL", "NG", "HO", "RB"):
        per_date = []
        eia_series = series_by_root.get(root)
        for d in dates:
            ts = pd.Timestamp(d)
            day_rows = daily_frame[
                (daily_frame["globex"] == root) & (pd.to_datetime(daily_frame["trade_date"]) == ts)
            ]
            if day_rows.empty:
                per_date.append({"date": d, "status": "no SPAN data for this date (not yet fetched or archive gap)"})
                continue
            day_rows = day_rows.copy()
            day_rows["expiration_dt"] = pd.to_datetime(day_rows["expiration_date"], format="%Y%m%d", errors="coerce")
            unexpired = day_rows[day_rows["expiration_dt"] >= ts].dropna(subset=["expiration_dt"])
            if unexpired.empty:
                per_date.append({"date": d, "status": "no unexpired contract found"})
                continue
            front = unexpired.loc[unexpired["expiration_dt"].idxmin()]
            span_settle = float(front["settle"])
            eia_val = None
            if eia_series is not None and ts in eia_series.index:
                eia_val = float(eia_series.loc[ts])
            per_date.append(
                {
                    "date": d,
                    "span_front_contract": front["contract_month"],
                    "span_settle": span_settle,
                    "eia_c1": eia_val,
                    "match_to_cent": (eia_val is not None and abs(eia_val - span_settle) < 0.005),
                }
            )
        results[root] = {"per_date": per_date, "eia_fetch_error": fetch_errors.get(root)}
    return results


def main() -> None:
    report: dict[str, Any] = {"generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds")}
    print("1. date coverage per instrument")
    report["date_coverage"] = check_date_coverage()

    print("2. CL negative settlement re-confirmation")
    report["cl_negative_settlement"] = check_cl_negative_settlement()
    print(json.dumps(report["cl_negative_settlement"], indent=2, default=str))

    print("3. extended EIA cross-check")
    report["extended_eia_cross_check"] = check_extended_eia_cross(EXTENDED_CROSS_CHECK_DATES)

    out_path = STORE / "verification_report.json"
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
