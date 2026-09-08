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
  V2  Real (snapshot, ticker) PRESSURE cells re-derived FROM THE RAW N-PORT
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
from datetime import date, datetime, timedelta
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
def _as_date(text: str) -> date:
    """N-PORT dates are DD-MMM-YYYY in the DERA extracts; fall back to ISO."""
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unparseable N-PORT date {text!r}")


def _sum_three(row: dict, prefix: str) -> float | None:
    """Sum a per-month N-PORT flow field over the quarter's three months."""
    total = 0.0
    for n in (1, 2, 3):
        value = _parse_float(row.get(f"{prefix}{n}", ""))
        if value is None:
            return None
        total += value
    return total


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
    """Re-derive real PRESSURE cells from raw N-PORT rows and match the panel.

    The CUSIP->ticker map and the split factors are treated as INPUTS (they are
    shared modules, proven byte-identical to main by V5). Everything that is
    this family's own logic -- which filing is 'current', which is 'previous',
    what the flow is, who counts as a buyer or seller, and Eq.(4) itself -- is
    retyped here from the paper and the pre-registration, never imported.
    """
    print("\nV2 — real PRESSURE cells re-derived from the raw N-PORT CSVs")
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

    # --- inputs (shared, unchanged from main; see V5) ------------------------
    from app.services.research_lab.cross_sectional_nport_flow import (
        build_split_adjustment,
        load_cusip_ticker_map,
    )
    from app.services.market_data.yfinance_provider import YFinanceProvider

    if universe == "sp600":
        from app.services.research_lab import small_cap_membership_history as mod
    else:
        from app.services.research_lab import sp500_membership_history as mod

    # The CUSIP->ticker map is date-resolved, so it must be built over the SAME
    # window the runner used or a handful of symbols resolve differently and the
    # OWNER SET (not Eq.(4)) diverges. The runner itself warns that 18 of 1190
    # CUSIPs resolve differently at a sample endpoint than at the midpoint.
    # Aligning the window here is what makes V2 a test of Eq.(4) rather than a
    # test of the map's date handling.
    hist_start = date(2021, 1, 1) - timedelta(days=500)
    end_date = date(2026, 9, 8)
    probe = end_date
    while probe > end_date - timedelta(days=800):
        try:
            mod.get_universe_as_of(probe)
            break
        except Exception:  # noqa: BLE001
            probe -= timedelta(days=1)
    end_date = probe
    names = mod.get_universe_over(max(mod.MEMBERSHIP_DATA_START, hist_start), end_date)
    cusip_map, _ = load_cusip_ticker_map(names)
    midpoint = hist_start + (end_date - hist_start) / 2
    cusip_to_ticker = {}
    for cusip in cusip_map.observations:
        t = cusip_map.resolve(cusip, midpoint)
        if t is not None:
            cusip_to_ticker[cusip] = t

    provider = YFinanceProvider()
    frames, _missing = provider.get_daily_ohlcv(list(panel.columns), hist_start, end_date)
    close = frames["close"]
    _cc, splits, _m = provider.get_market_cap_basis(list(close.columns), hist_start, end_date)
    split_adj = build_split_adjustment(splits, close.index)

    def split_factor(ticker, when):
        series = split_adj.get(ticker)
        if series is None or len(series) == 0:
            return 1.0
        pos = series.index.searchsorted(pd.Timestamp(when), side="right") - 1
        return float(series.iloc[0]) if pos < 0 else float(series.iloc[pos])

    # --- raw tables ----------------------------------------------------------
    filings_by_series = defaultdict(list)
    holdings = defaultdict(dict)
    # One filing per (accession, series). The family dedups accessions globally
    # for exactly this reason: an accession appearing in two quarterly extracts
    # would otherwise give a fund two copies of one filing, which satisfies the
    # "at least two public filings" test for funds that really have only one.
    # Omitting this was this script's fourth first-pass bug -- it inflated
    # RITM's owner count from 200 to 212.
    seen_rows: set[tuple[str, str]] = set()
    for quarter in quarters:
        subs, info, hold = _load_raw_quarter(quarter)
        sub_by_acc = {r["ACCESSION_NUMBER"]: r for r in subs}
        for r in info:
            acc = r["ACCESSION_NUMBER"]
            sub = sub_by_acc.get(acc)
            if sub is None:
                continue
            series = r.get("SERIES_ID") or ""
            report = sub.get("REPORT_DATE") or ""
            filed = sub.get("FILING_DATE") or ""
            net = _parse_float(r.get("NET_ASSETS", ""))
            # Item B.6.a and B.6.c are reported PER MONTH; the quarter's flow
            # is the sum of all three. Using MON3 alone was this script's own
            # first-pass bug -- it produced correct owner COUNTS (denominators
            # matched exactly) but misclassified which funds were constrained.
            sold = _sum_three(r, "SALES_FLOW_MON")
            redeemed = _sum_three(r, "REDEMPTION_FLOW_MON")
            # The family also requires REINVESTMENT to parse: it builds one
            # record with all three legs and drops the row if any is missing.
            # Eq.(4) never uses reinvestment, but it still GATES the row, so a
            # re-derivation that ignores it sees filings the family refused.
            reinvested = _sum_three(r, "REINVESTMENT_FLOW_MON")
            if not (series and report and filed) or net is None:
                continue
            if sold is None or redeemed is None or reinvested is None:
                continue
            # Net assets must be strictly positive, and a filing cannot predate
            # the period it reports on -- such a row would make a value visible
            # before it existed. Both refusals are the family's; omitting them
            # was this script's third first-pass bug and inflated owner counts.
            if not net > 0.0:
                continue
            if _as_date(filed) < _as_date(report):
                continue
            if (acc, series) in seen_rows:
                continue
            seen_rows.add((acc, series))
            filings_by_series[series].append(
                {
                    "accession": acc,
                    "report": _as_date(report),
                    "filed": _as_date(filed),
                    "net_assets": net,
                    "sold": sold,
                    "redeemed": redeemed,
                }
            )
        for r in hold:
            # Only LONG COMMON-EQUITY positions measured in SHARES count as
            # owning the stock: Item C.4 unit "NS", Item C.7 asset category
            # "EC", a real CUSIP (not N-PORT's 999999999 placeholder) and a
            # strictly positive balance. A fund's bond or preferred position in
            # the same issuer is a different security and a short position is
            # not ownership. Omitting these four refusals was this script's
            # fifth first-pass bug -- it inflated RITM's owner count from 200
            # to 212 by counting non-equity positions in the same issuer.
            if (r.get("UNIT") or "").strip() != "NS":
                continue
            if (r.get("ASSET_CAT") or "").strip() != "EC":
                continue
            cusip = (r.get("ISSUER_CUSIP") or "").strip()
            if not cusip or cusip == "999999999":
                continue
            bal = _parse_float(r.get("BALANCE", ""))
            if bal is None or not bal > 0.0:
                continue
            acc = r["ACCESSION_NUMBER"]
            holdings[acc][cusip] = holdings[acc].get(cusip, 0.0) + bal

    for rows in filings_by_series.values():
        rows.sort(key=lambda f: (f["filed"], f["report"]))

    check(
        "raw tables readable",
        bool(filings_by_series) and bool(holdings),
        f"{len(filings_by_series)} series, {len(holdings)} accessions with holdings",
    )

    # --- retyped constants (module docstring / flow-definition resolution) ---
    MAX_STALE = 200
    MIN_GAP, MAX_GAP = 80, 100
    MIN_NET_ASSETS = 1e7
    MAX_ABS_FLOW = 2.0

    def snapshots_as_of(as_of):
        out = {}
        for series, rows in filings_by_series.items():
            cut = bisect_right([f["filed"] for f in rows], as_of)
            public = rows[:cut]
            if len(public) < 2:
                continue
            current = max(public, key=lambda f: (f["report"], f["filed"]))
            if (as_of - current["report"]).days > MAX_STALE:
                continue
            earlier = [f for f in public if f["report"] < current["report"]]
            if not earlier:
                continue
            previous = max(earlier, key=lambda f: (f["report"], f["filed"]))
            gap = (current["report"] - previous["report"]).days
            if not MIN_GAP <= gap <= MAX_GAP:
                continue
            if previous["net_assets"] < MIN_NET_ASSETS:
                continue
            sold, redeemed = current["sold"], current["redeemed"]
            if sold is None or redeemed is None:
                continue
            flow = (sold - redeemed) / previous["net_assets"]   # Item B.6.a - B.6.c
            if not np.isfinite(flow) or abs(flow) > MAX_ABS_FLOW:
                continue
            out[series] = (current, previous, flow)
        return out

    # Re-derive a handful of cells spread across the panel.
    rng = np.random.default_rng(0)
    stacked = panel.stack()
    if len(stacked) == 0:
        check("panel non-empty", False)
        return
    picks = rng.choice(len(stacked), size=min(5, len(stacked)), replace=False)
    matched = 0
    attempted = 0
    for idx in picks:
        (snap, ticker) = stacked.index[int(idx)]
        expected = float(stacked.iloc[int(idx)])
        as_of = pd.Timestamp(snap).date()
        snaps = snapshots_as_of(as_of)
        if not snaps:
            continue
        buys = sells = owners = 0
        for series, (current, previous, flow) in snaps.items():
            before_book = holdings.get(previous["accession"], {})
            after_book = holdings.get(current["accession"], {})
            before = after = 0.0
            for cusip, shares in before_book.items():
                if cusip_to_ticker.get(cusip) == ticker:
                    before += shares * split_factor(ticker, previous["report"])
            for cusip, shares in after_book.items():
                if cusip_to_ticker.get(cusip) == ticker:
                    after += shares * split_factor(ticker, current["report"])
            if before <= 0:
                continue
            owners += 1
            if after > before and flow > 0.05:
                buys += 1
            elif after < before and flow < -0.05:
                sells += 1
        attempted += 1
        if owners < MIN_OWNERS:
            continue
        mine = (buys - sells) / owners
        ok = abs(mine - expected) < 1e-9
        matched += int(ok)
        print(
            f"    {ticker} @ {as_of}: re-derived {mine:.9f} vs panel {expected:.9f} "
            f"(owners={owners}, buys={buys}, sells={sells}) {'OK' if ok else 'MISMATCH'}"
        )
    check(
        "re-derived PRESSURE cells match the committed panel exactly",
        attempted > 0 and matched == attempted,
        f"{matched}/{attempted} matched",
    )

    values = panel.stack()
    check(
        "every PRESSURE lies in [-1, +1] as a net count over owners must",
        bool(values.min() >= -1.0 - 1e-9 and values.max() <= 1.0 + 1e-9),
        f"min {values.min():.6f} max {values.max():.6f}",
    )
    notes.append(
        f"V2 universe={universe}: {len(values)} finite cells, "
        f"fire-sale {(values <= FIRESALE_CUTOFF).sum()}, inflow {(values >= INFLOW_CUTOFF).sum()}, "
        f"median {values.median():.6f}"
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
    # scipy's skew/kurtosis with bias=True standardize by the POPULATION
    # second moment (ddof=0), not the ddof=1 sample std used for the Sharpe.
    # Using sd here was this script's own second first-pass bug: it shifted
    # every DSR by ~7e-4.
    d = r - mean
    m2 = float((d**2).mean())
    if m2 <= 0:
        return None
    skew = float((d**3).mean()) / m2**1.5
    kurt = float((d**4).mean()) / m2**2
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
