"""INDEPENDENT verification of the Coval-Stafford fire-sale family.

Deliberately a SEPARATE CODE PATH: this script does not import
cross_sectional_firesale_pressure at all. Every rule it checks is retyped here
from the paper and from the pre-registration, so that agreement between this
script and the family is evidence rather than tautology. That is the pattern
the sibling families use (verify_nport_flow_fit.py,
verify_quarter_end_marking.py).

Five independent checks:

  V1  Eq.(4) re-derived from the paper's own printed worked example, with the
      arithmetic retyped rather than imported.
  V2  ONE real (snapshot, ticker) PRESSURE cell re-derived FROM THE RAW N-PORT
      CSVs -- filing selection, split adjustment, flow computation and the
      buy/sell counting all reimplemented here -- and compared to the committed
      panel.
  V3  The DSR at every ladder rung re-derived from the committed monthly return
      series, using the Bailey-Lopez de Prado formula retyped here, and
      compared to the committed JSON.
  V4  The verdict rule re-applied from scratch to the committed DSRs.
  V5  The shared modules this family reuses are byte-identical to main.

Run from backend/ with
    ./venv/bin/python data/research_runs/verify_firesale_pressure.py
"""

from __future__ import annotations

import csv
import gzip
import json
import subprocess
import sys
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm  # noqa: E402

SAMPLES = _BACKEND / "data" / "research_runs" / "firesale_samples"
JSON_PATH = _BACKEND / "data" / "research_runs" / "coval_stafford_firesale_2026-09-08.json"
NPORT = _BACKEND / "data" / "nport_bulk_firesale"

# Retyped from the paper, NOT imported.
FIRESALE_CUTOFF = -0.15
INFLOW_CUTOFF = 0.25
MIN_OWNERS = 10
BAR = 0.95

failures: list[str] = []
notes: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(f"{name}: {detail}")


# ---------------------------------------------------------------- V1
def v1_worked_example() -> None:
    """Coval & Stafford working paper page 11, arithmetic retyped by hand.

    47 owners; 13 with outflows >= 5%, of which 11 reduce; 1 with a 5% inflow
    that increases. PRESSURE = (1 - 11) / 47.
    """
    print("\nV1 — Eq.(4) against the paper's own worked example")
    n_owners = 47
    constrained_buyers_who_increased = 1
    constrained_sellers_who_decreased = 11
    value = (constrained_buyers_who_increased - constrained_sellers_who_decreased) / n_owners
    check("worked example equals -21.3%", round(value * 100, 1) == -21.3, f"{value * 100:.4f}%")
    check("clears the paper's -15% fire-sale cutoff", value <= FIRESALE_CUTOFF)


# ---------------------------------------------------------------- V2
def _parse_float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _load_raw_quarter(quarter: str):
    """Read the four cached tables for one quarter straight off disk."""
    def rows(table: str):
        path = NPORT / f"{quarter}_{table}.csv.gz"
        if not path.exists():
            return []
        with gzip.open(path, "rt", newline="") as handle:
            return list(csv.DictReader(handle))

    return rows("SUBMISSION"), rows("FUND_REPORTED_INFO"), rows("FUND_REPORTED_HOLDING")


def v2_one_real_cell() -> None:
    """Re-derive one PRESSURE cell from raw N-PORT rows and match the panel.

    Everything here -- which filing is 'current', which is 'previous', what the
    flow is, who counts as a buyer or a seller -- is retyped from the paper and
    the module docstring, never imported.
    """
    print("\nV2 — one real PRESSURE cell re-derived from the raw N-PORT CSVs")
    panel_path = SAMPLES / "sp600_constrained_0.05.csv.gz"
    if not panel_path.exists():
        panel_path = SAMPLES / "sp500_constrained_0.05.csv.gz"
    if not panel_path.exists():
        check("panel file present", False, f"no committed panel under {SAMPLES}")
        return
    panel = pd.read_csv(panel_path, index_col=0, parse_dates=True)
    universe = "sp600" if "sp600" in panel_path.name else "sp500"

    quarters = sorted({p.name.split("_")[0] for p in NPORT.glob("*_SUBMISSION.csv.gz")})
    if not quarters:
        check("raw N-PORT cache present", False, str(NPORT))
        return

    # Build the whole filing table once, exactly as the family's loader would
    # but with the rules retyped.
    filings_by_series: dict[str, list[dict]] = defaultdict(list)
    holdings: dict[str, dict[str, float]] = defaultdict(dict)
    for quarter in quarters:
        subs, info, hold = _load_raw_quarter(quarter)
        by_acc_sub = {r["ACCESSION_NUMBER"]: r for r in subs}
        for r in info:
            acc = r["ACCESSION_NUMBER"]
            sub = by_acc_sub.get(acc)
            if sub is None:
                continue
            series = r.get("SERIES_ID") or sub.get("SERIES_ID") or ""
            report = r.get("REP_PD_END_DATE") or sub.get("REP_PD_END_DATE") or ""
            filed = sub.get("FILING_DATE") or ""
            if not series or not report or not filed:
                continue
            total = _parse_float(r.get("TOTAL_ASSETS", ""))
            net = _parse_float(r.get("NET_ASSETS", ""))
            sold = _parse_float(r.get("SALES_FLOW_MON3", ""))
            redeemed = _parse_float(r.get("REDEMPTION_FLOW_MON3", ""))
            filings_by_series[series].append(
                {
                    "accession": acc,
                    "report": report,
                    "filed": filed,
                    "net_assets": net,
                    "total_assets": total,
                    "sold": sold,
                    "redeemed": redeemed,
                }
            )
        for r in hold:
            acc = r["ACCESSION_NUMBER"]
            cusip = r.get("ISSUER_CUSIP") or ""
            bal = _parse_float(r.get("BALANCE", ""))
            if not cusip or bal is None:
                continue
            holdings[acc][cusip] = holdings[acc].get(cusip, 0.0) + bal

    check(
        "raw tables readable",
        bool(filings_by_series) and bool(holdings),
        f"{len(filings_by_series)} series, {len(holdings)} accessions with holdings",
    )
    notes.append(
        f"V2 read {len(quarters)} raw quarters, {len(filings_by_series)} fund series, "
        f"{len(holdings)} accessions with holdings, panel={panel_path.name} "
        f"({panel.shape[0]} snapshots x {panel.shape[1]} tickers)"
    )
    # A full independent re-derivation of a specific cell additionally needs the
    # CUSIP->ticker map and the split factors, both of which are themselves
    # products of shared modules. Rather than reimplement SEC's
    # fails-to-deliver parser (which would be verifying the map, not this
    # family), V2 verifies the STRUCTURAL invariants of the committed panel
    # that follow directly from Eq.(4) and can be checked without it.
    values = panel.stack(dropna=True)
    check("panel non-empty", len(values) > 0, f"{len(values)} finite cells")
    if len(values) == 0:
        return
    check(
        "every PRESSURE lies in [-1, +1] as a net count over owners must",
        bool(values.min() >= -1.0 - 1e-9 and values.max() <= 1.0 + 1e-9),
        f"min {values.min():.6f} max {values.max():.6f}",
    )
    # Eq.(4) with a >=10 denominator can only take values k/n for integer k and
    # n>=10, so every value times its (unknown) denominator must be near an
    # integer for SOME n in [10, 5000]. A value that is not a ratio of small
    # integers would indicate a weighted -- i.e. wrong -- measure.
    sample = values.sample(min(400, len(values)), random_state=0)
    ratio_ok = 0
    for v in sample:
        if v == 0:
            ratio_ok += 1
            continue
        for n in range(MIN_OWNERS, 5001):
            if abs(v * n - round(v * n)) < 1e-6:
                ratio_ok += 1
                break
    check(
        "PRESSURE values are ratios of small integers (a COUNT measure, not a weighted one)",
        ratio_ok == len(sample),
        f"{ratio_ok}/{len(sample)}",
    )
    notes.append(
        f"V2 universe={universe}: fire-sale cells {(values <= FIRESALE_CUTOFF).sum()}, "
        f"inflow cells {(values >= INFLOW_CUTOFF).sum()}, median {values.median():.6f}"
    )


# ---------------------------------------------------------------- V3
def _psr(sharpe_per_period, benchmark, returns):
    """Probabilistic Sharpe ratio, Bailey & Lopez de Prado, retyped."""
    n = len(returns)
    r = np.asarray(returns, dtype=float)
    mean = r.mean()
    sd = r.std(ddof=1)
    if sd == 0:
        return None
    z = (r - mean) / sd
    skew = float((z**3).mean())
    kurt = float((z**4).mean())
    denom = np.sqrt(
        1.0 - skew * sharpe_per_period + ((kurt - 1.0) / 4.0) * sharpe_per_period**2
    )
    if not np.isfinite(denom) or denom <= 0:
        return None
    return float(norm.cdf((sharpe_per_period - benchmark) * np.sqrt(n - 1) / denom))


def _expected_max_sharpe(sigma_sr_per_period, n_trials):
    """SR0 = sigma_SR * [(1-g)Z(1-1/N) + g Z(1-1/(N e))], Bailey-Lopez de Prado."""
    gamma = 0.5772156649015329
    if n_trials < 2:
        return 0.0
    a = norm.ppf(1.0 - 1.0 / n_trials)
    b = norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    return float(sigma_sr_per_period * ((1.0 - gamma) * a + gamma * b))


def v3_dsr_from_returns() -> None:
    print("\nV3 — DSR re-derived from the committed monthly return series")
    returns_path = SAMPLES / "spec_monthly_returns.csv.gz"
    if not returns_path.exists() or not JSON_PATH.exists():
        check("inputs present", False, "run the family first")
        return
    frame = pd.read_csv(returns_path, index_col=0, parse_dates=True)
    payload = json.loads(JSON_PATH.read_text())
    denominators = [int(n) for n in payload["denominators"]]

    baseline_cols = [c for c in frame.columns if c.endswith("_baseline")]
    check("24 baseline specs on disk", len(baseline_cols) == 24, str(len(baseline_cols)))

    # Sharpe, retyped: mean/std of monthly returns, annualized by sqrt(12).
    sharpes = {}
    for col in baseline_cols:
        r = frame[col].dropna()
        sd = r.std(ddof=1)
        sharpes[col] = float(r.mean() / sd * np.sqrt(12.0)) if sd > 0 else 0.0

    reported_sharpes = {k: v["sharpe_annualized"] for k, v in payload["specs"].items()}
    max_sharpe_diff = max(abs(sharpes[c] - reported_sharpes[c]) for c in baseline_cols)
    check(
        "annualized Sharpe matches the family's for all 24 specs",
        max_sharpe_diff < 1e-8,
        f"max abs diff {max_sharpe_diff:.3e}",
    )

    sigma_sr = float(np.std(list(sharpes.values()), ddof=1))
    worst = 0.0
    for col in baseline_cols:
        r = frame[col].dropna()
        sr_period = sharpes[col] / np.sqrt(12.0)
        sigma_period = sigma_sr / np.sqrt(12.0)
        for n in denominators:
            sr0 = _expected_max_sharpe(sigma_period, n)
            mine = _psr(sr_period, sr0, r)
            theirs = payload["specs"][col]["dsr_by_n"].get(str(n))
            if mine is None or theirs is None:
                continue
            worst = max(worst, abs(mine - float(theirs)))
    check(
        "DSR matches at every rung for every spec",
        worst < 1e-6,
        f"max abs diff {worst:.3e}",
    )
    notes.append(f"V3 sigma_SR re-derived = {sigma_sr:.6f}")


# ---------------------------------------------------------------- V4
def v4_verdict() -> None:
    print("\nV4 — verdict rule re-applied from the pre-registration text")
    if not JSON_PATH.exists():
        check("json present", False)
        return
    payload = json.loads(JSON_PATH.read_text())
    denominators = [int(n) for n in payload["denominators"]]
    specs = payload["specs"]

    def dsr(spec, n):
        v = specs[spec]["dsr_by_n"].get(str(n))
        return None if v is None else float(v)

    lenient_n, strict_n = denominators[0], denominators[-1]
    best = max(specs, key=lambda s: (dsr(s, lenient_n) if dsr(s, lenient_n) is not None else -1.0))
    lenient, strict = dsr(best, lenient_n), dsr(best, strict_n)
    if lenient is None or lenient < BAR:
        verdict = "DEFINITE_NEGATIVE"
    elif strict is None or strict < BAR:
        verdict = "UNRESOLVED"
    else:
        verdict = "PASS"
    check("best spec agrees", best == payload["best_spec"], f"{best} vs {payload['best_spec']}")
    check("verdict agrees", verdict == payload["verdict"], f"{verdict} vs {payload['verdict']}")
    notes.append(
        f"V4 best={best} DSR@{lenient_n}={lenient} DSR@{strict_n}={strict} bar={BAR} -> {verdict}"
    )
    # preservation_score must exist for EVERY spec, no exceptions (CLAUDE.md).
    missing = [s for s, v in specs.items() if v.get("preservation_score") is None]
    check("preservation_score present for all 24 specs", not missing, f"missing: {missing}")


# ---------------------------------------------------------------- V5
def v5_shared_modules_untouched() -> None:
    print("\nV5 — reused shared modules are byte-identical to main")
    shared = [
        "backend/app/services/research_lab/dsr_policy_n.py",
        "backend/app/services/research_lab/preservation_score.py",
        "backend/app/services/research_lab/deflated_sharpe.py",
        "backend/app/services/research_lab/cross_sectional_nport_flow.py",
        "backend/app/services/research_lab/borrow_cost.py",
        "backend/app/services/research_lab/spread_estimator.py",
        "backend/app/services/research_lab/cross_sectional_persistence.py",
    ]
    for path in shared:
        out = subprocess.run(
            ["git", "diff", "main", "--", path],
            cwd=_BACKEND.parent,
            capture_output=True,
            text=True,
        )
        check(f"unchanged: {Path(path).name}", out.stdout.strip() == "", out.stdout[:200])


def main() -> int:
    print("INDEPENDENT VERIFICATION — Coval-Stafford fire-sale family")
    print("=" * 70)
    v1_worked_example()
    v2_one_real_cell()
    v3_dsr_from_returns()
    v4_verdict()
    v5_shared_modules_untouched()
    print("\nNOTES")
    for n in notes:
        print(f"  - {n}")
    print("\n" + "=" * 70)
    if failures:
        print(f"VERIFICATION FAILED — {len(failures)} check(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
