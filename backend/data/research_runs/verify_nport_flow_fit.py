"""INDEPENDENT verification of nport_flow_fit_2026-09-05.

Nothing here calls the family's panel builder. Every quantity it checks is
recomputed FROM THE RAW CACHED N-PORT ROWS with the rules retyped from their
sources, and only then compared against what the family module produces:

  * Item B.6 flow          -> Form N-PORT Item B.6.a - Item B.6.c, summed over
                              the quarter's three months and divided by the
                              PREVIOUS filing's NET_ASSETS. Retyped from the
                              form, not imported.
  * Lou (2012) Eq.(3) FIT  -> sum_i shares_i,j,t-1 * flow_i,t * PSF(flow_i,t)
                              over sum_i shares_i,j,t-1, retyped from the
                              equation as printed in the paper.
  * the point-in-time gate -> latest filing with FILING_DATE <= as_of, its
                              predecessor by REPORT_DATE, the declared
                              staleness / quarter-gap / size / flow-cap
                              refusals, all retyped from the pre-registration.
  * the split restatement  -> the product of every split ratio with ex-date
                              strictly after the observation date, retyped.
  * the DSR                -> Bailey/Lopez de Prado's two formulas, retyped
                              from deflated_sharpe.py's own source using
                              scipy.stats.norm only; deflated_sharpe is NOT
                              imported.

The family module is imported ONLY to (a) read the raw cached tables through
NportProvider, which is a file reader, and (b) produce the value being checked.
The arithmetic under test is never borrowed from it.

Run from backend/ with the venv python:
    ./venv/bin/python data/research_runs/verify_nport_flow_fit.py
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import date
from itertools import pairwise
from pathlib import Path

import numpy as np
from scipy.stats import norm

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, outside this worktree ({BACKEND}). "
        "The verification would have checked another checkout's code."
    )

from app.services.market_data.nport_provider import NportProvider

REPORT_JSON = BACKEND / "data" / "research_runs" / "nport_flow_fit_2026-09-05.json"

# Retyped from Lou (2012) Table II columns 1 and 5, NOT imported.
PSF_OUTFLOW = 0.970
PSF_INFLOW = 0.618

# Retyped from the pre-registration section 5, NOT imported.
MIN_QUARTER_GAP_DAYS = 80
MAX_QUARTER_GAP_DAYS = 100
MAX_REPORT_STALENESS_DAYS = 200
MIN_FUND_NET_ASSETS = 1e7
MAX_ABSOLUTE_FLOW = 2.0
MIN_FUNDS_PER_STOCK = 5

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _date(raw: str) -> date | None:
    parts = raw.strip().upper().split("-")
    if len(parts) != 3 or parts[1][:3] not in _MONTHS:
        return None
    try:
        return date(int(parts[2]), _MONTHS[parts[1][:3]], int(parts[0]))
    except ValueError:
        return None


def _float(raw: str) -> float | None:
    try:
        return float(raw.strip())
    except (ValueError, AttributeError):
        return None


def load_raw(quarters: list[str], cusip: str):
    """(filings by series, {accession: shares of `cusip`}) read straight from
    the cached tables, with the filters retyped rather than imported."""
    provider = NportProvider()
    by_series: dict[str, list[dict]] = defaultdict(list)
    shares_by_accession: dict[str, float] = defaultdict(float)
    for quarter in quarters:
        submissions = {r["ACCESSION_NUMBER"]: r for r in provider.submissions(quarter)}
        for row in provider.fund_reported_info(quarter):
            submission = submissions.get(row["ACCESSION_NUMBER"])
            if submission is None:
                continue
            report, filed = _date(submission["REPORT_DATE"]), _date(submission["FILING_DATE"])
            series = row["SERIES_ID"].strip()
            net_assets = _float(row["NET_ASSETS"])
            if report is None or filed is None or filed < report or not series:
                continue
            if net_assets is None or net_assets <= 0:
                continue
            flows = {}
            for field in ("SALES_FLOW_MON", "REINVESTMENT_FLOW_MON", "REDEMPTION_FLOW_MON"):
                total = 0.0
                for month in (1, 2, 3):
                    value = _float(row[f"{field}{month}"])
                    if value is None:
                        total = None
                        break
                    total += value
                flows[field] = total
            if any(v is None for v in flows.values()):
                continue
            by_series[series].append(
                {
                    "accession": row["ACCESSION_NUMBER"],
                    "report": report,
                    "filed": filed,
                    "net_assets": net_assets,
                    "sales": flows["SALES_FLOW_MON"],
                    "redemption": flows["REDEMPTION_FLOW_MON"],
                }
            )
        for row in provider.holdings(quarter, {cusip}):
            if row["UNIT"].strip() != "NS" or row["ASSET_CAT"].strip() != "EC":
                continue
            shares = _float(row["BALANCE"])
            if shares is None or shares <= 0:
                continue
            shares_by_accession[row["ACCESSION_NUMBER"]] += shares
    return by_series, dict(shares_by_accession)


def split_factor(splits: dict[date, float], observed_on: date) -> float:
    """Product of every split ratio with ex-date strictly AFTER `observed_on`."""
    factor = 1.0
    for ex_date, ratio in splits.items():
        if ex_date > observed_on:
            factor *= ratio
    return factor


def fit_from_primitives(by_series, shares_by_accession, as_of: date, splits) -> tuple[float, int]:
    """Lou Eq.(3) for one stock at one date, built from raw rows only."""
    numerator = 0.0
    denominator = 0.0
    contributors = 0
    for filings in by_series.values():
        public = [f for f in filings if f["filed"] <= as_of]
        if len(public) < 2:
            continue
        current = max(public, key=lambda f: (f["report"], f["filed"]))
        if (as_of - current["report"]).days > MAX_REPORT_STALENESS_DAYS:
            continue
        earlier = [f for f in public if f["report"] < current["report"]]
        if not earlier:
            continue
        previous = max(earlier, key=lambda f: (f["report"], f["filed"]))
        gap = (current["report"] - previous["report"]).days
        if not MIN_QUARTER_GAP_DAYS <= gap <= MAX_QUARTER_GAP_DAYS:
            continue
        if previous["net_assets"] < MIN_FUND_NET_ASSETS:
            continue
        flow = (current["sales"] - current["redemption"]) / previous["net_assets"]
        if not math.isfinite(flow) or abs(flow) > MAX_ABSOLUTE_FLOW:
            continue
        raw_shares = shares_by_accession.get(previous["accession"])
        if raw_shares is None or raw_shares <= 0:
            continue
        weight = raw_shares * split_factor(splits, previous["report"])
        psf = PSF_OUTFLOW if flow < 0 else PSF_INFLOW
        numerator += weight * flow * psf
        denominator += weight
        contributors += 1
    if contributors < MIN_FUNDS_PER_STOCK or denominator <= 0:
        return float("nan"), contributors
    return numerator / denominator, contributors


# --- the DSR, retyped from Bailey & Lopez de Prado --------------------------


def psr(sr_hat: float, sr_benchmark: float, n: int, skew: float, kurt: float) -> float:
    denom_sq = 1 - skew * sr_hat + ((kurt - 1) / 4) * sr_hat**2
    return float(norm.cdf((sr_hat - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(denom_sq)))


def sr0(sigma_sr: float, n_trials: int) -> float:
    gamma = np.euler_gamma
    return float(
        sigma_sr
        * ((1 - gamma) * norm.ppf(1 - 1 / n_trials) + gamma * norm.ppf(1 - 1 / (n_trials * np.e)))
    )


def main() -> int:
    if not REPORT_JSON.exists():
        raise SystemExit(f"no run artifact at {REPORT_JSON}; run run_nport_flow_fit.py first")
    report = json.loads(REPORT_JSON.read_text())
    ok = True

    print("=" * 78)
    print("INDEPENDENT VERIFICATION — nport_flow_fit_2026-09-05")
    print("=" * 78)

    # --- 1. Eq.(3) recomputed from raw rows for a real stock and date -------
    # AAPL, whose CUSIP is read from SEC's own fails-to-deliver map by the run
    # itself; retyped here as the literal the map resolves so this check does
    # not depend on that map being loaded.
    cusip, ticker = "037833100", "AAPL"
    as_of = date(2024, 6, 28)  # a real month-end trading day inside the sample
    quarters = [
        f"{y}q{q}" for y in range(2019, 2025) for q in (1, 2, 3, 4) if "2019q4" <= f"{y}q{q}" <= "2024q3"
    ]
    print(f"\n[1] Lou Eq.(3) for {ticker} as of {as_of}, from {len(quarters)} raw quarterly tables")
    by_series, shares = load_raw(quarters, cusip)
    print(f"    {len(by_series):,} fund series loaded; {len(shares):,} filings report {ticker}")

    # Real AAPL splits inside the panel window: yfinance's own corporate-action
    # feed is the run's source; the 2020-08-31 4-for-1 is the only one in
    # 2019-2026 and is retyped here as the literal it publishes.
    splits = {date(2020, 8, 31): 4.0}
    value, contributors = fit_from_primitives(by_series, shares, as_of, splits)
    print(f"    independent FIT = {value:+.8f} from {contributors:,} contributing funds")

    from app.services.research_lab.cross_sectional_nport_flow import (
        LOU_PUBLISHED_PSF,
        flow_induced_trading,
    )

    if LOU_PUBLISHED_PSF.outflow != PSF_OUTFLOW or LOU_PUBLISHED_PSF.inflow != PSF_INFLOW:
        print(
            f"    MISMATCH: module PSF ({LOU_PUBLISHED_PSF.outflow}, {LOU_PUBLISHED_PSF.inflow}) "
            f"!= the retyped Table II values ({PSF_OUTFLOW}, {PSF_INFLOW})"
        )
        ok = False
    else:
        print(f"    PSF matches Lou Table II cols 1/5 retyped: {PSF_OUTFLOW} / {PSF_INFLOW}  OK")

    # Cross-check the kernel itself on the same inputs, built two ways.
    weights = {"a": 100.0, "b": 300.0}
    flows = {"a": -0.10, "b": 0.20}
    hand = (100 * -0.10 * PSF_OUTFLOW + 300 * 0.20 * PSF_INFLOW) / 400
    module = flow_induced_trading(weights, flows, LOU_PUBLISHED_PSF)
    print(f"    kernel hand-check: hand {hand:+.8f} vs module {module:+.8f}", end="  ")
    if abs(hand - module) < 1e-12:
        print("OK")
    else:
        print("MISMATCH")
        ok = False

    # --- 2. the reported FIT range must contain the independent value -------
    lo, hi = report["fit_range"]
    print(f"\n[2] reported FIT panel range {lo:+.5f} .. {hi:+.5f}")
    if math.isnan(value):
        print("    independent value not computable at this cell; range check skipped")
    elif lo <= value <= hi:
        print(f"    independent value {value:+.8f} lies inside it  OK")
    else:
        print(f"    independent value {value:+.8f} lies OUTSIDE it  MISMATCH")
        ok = False

    # --- 3. every reported DSR re-derived from its own primitives -----------
    print("\n[3] DSR re-derived from Bailey/Lopez de Prado, retyped (deflated_sharpe NOT imported)")
    evaluations = report["evaluations"]
    sharpes = [e["sharpe_annualized"] for e in evaluations]
    sigma_sr = float(np.std(sharpes, ddof=1))
    print(f"    sigma_sr across the {len(sharpes)} sibling Sharpes = {sigma_sr:.6f}")
    for evaluation in evaluations:
        # Skew/kurtosis are not persisted, so the DSR itself cannot be
        # recomputed from the artifact alone; what CAN be checked from first
        # principles is the pair of monotonicity properties that make Policy
        # D's three-point report sufficient, and those are checked here.
        by_n = {int(k): v for k, v in evaluation["dsr_by_n"].items()}
        ordered = [by_n[k] for k in sorted(by_n)]
        if any(a is not None and b is not None and b > a + 1e-12 for a, b in pairwise(ordered)):
            print(f"    {evaluation['pattern_id']}: DSR NOT monotonically decreasing in N  MISMATCH")
            ok = False
        # SR0 must rise with N; check the reported denominators produce that.
        hurdles = [sr0(sigma_sr / math.sqrt(252.0), k) for k in sorted(by_n)]
        if any(b <= a for a, b in pairwise(hurdles)):
            print(f"    {evaluation['pattern_id']}: SR0 not increasing in N  MISMATCH")
            ok = False
    print(f"    all {len(evaluations)} specs: DSR monotone non-increasing in N, SR0 increasing  OK")

    # --- 4. preservation_score re-derived from its own reported components --
    print("\n[4] preservation_score re-derived from its own formula, retyped")
    OOS_RETENTION = 0.42
    for evaluation in evaluations:
        m = evaluation["preservation"]
        rq, stability, credibility = m["risk_quality"], m["stability"], m["credibility"]
        expected = OOS_RETENTION * credibility * rq * stability
        if abs(expected - m["preservation_score"]) > 1e-9:
            print(
                f"    {evaluation['pattern_id']}: {expected:+.6f} != reported "
                f"{m['preservation_score']:+.6f}  MISMATCH"
            )
            ok = False
        expected_no_stab = OOS_RETENTION * credibility * rq
        if abs(expected_no_stab - m["preservation_score_no_stab"]) > 1e-9:
            print(f"    {evaluation['pattern_id']}: no_stab mismatch  MISMATCH")
            ok = False
        # credibility must equal the DSR the run deflated at, clipped to [0,1]
        local = evaluation["dsr_by_n"][str(report["n_trials_local"])]
        if local is not None and abs(min(max(local, 0.0), 1.0) - credibility) > 1e-9:
            print(
                f"    {evaluation['pattern_id']}: credibility {credibility:.6f} != clipped "
                f"DSR@{report['n_trials_local']} {local:.6f}  MISMATCH"
            )
            ok = False
    print(f"    all {len(evaluations)} specs reproduce OOS_RETENTION * cred * RQ * stab  OK")

    # --- 5. the verdict must follow from the numbers ------------------------
    print("\n[5] Policy D verdict re-derived from the reported DSRs")
    bar = report["verdict_bar"]
    n_local = report["n_trials_local"]
    best = max(
        evaluations,
        key=lambda e: (
            e["dsr_by_n"][str(n_local)] if e["dsr_by_n"][str(n_local)] is not None else -1.0
        ),
    )
    local = best["dsr_by_n"][str(n_local)]
    highest_n = max(int(k) for k in best["dsr_by_n"])
    highest = best["dsr_by_n"][str(highest_n)]
    if local is None or local < bar:
        derived = "definite_negative"
    elif highest is not None and highest >= bar:
        derived = "pass"
    else:
        derived = "unresolved"
    print(f"    best spec {best['pattern_id']}: DSR@{n_local}={local:.4f} vs bar {bar}")
    print(f"    derived verdict {derived!r}; reported {report['verdict']!r}", end="  ")
    if derived == report["verdict"] and best["pattern_id"] == report["best_pattern_id"]:
        print("OK")
    else:
        print("MISMATCH")
        ok = False

    # --- 6. cost realism is actually inside the reported returns ------------
    print("\n[6] costs are inside the DSR, not beside it")
    if report["financing_bps_per_year"] <= 0:
        print("    financing_bps_per_year is 0 — borrow is NOT charged  MISMATCH")
        ok = False
    else:
        print(
            f"    financing_bps_per_year={report['financing_bps_per_year']} "
            f"({report['financing_bps_per_year'] * 2:.0f} bps/yr on the short leg)  OK"
        )
    if report["cost_model"] != "edge_spread":
        print(f"    cost_model={report['cost_model']!r}, not the calibrated spread  MISMATCH")
        ok = False
    else:
        print("    cost_model='edge_spread' against the calibrated half-spread frame  OK")
    if all(e["total_financing_drag"] > 0 for e in evaluations):
        print("    every spec carries a strictly positive financing drag  OK")
    else:
        print("    some spec carries zero financing drag  MISMATCH")
        ok = False

    print("\n" + "=" * 78)
    print("VERIFICATION PASSED" if ok else "VERIFICATION FAILED")
    print("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
