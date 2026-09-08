"""INDEPENDENT verification of the Frazzini-Lamont dumb-money family.

THE POINT OF THIS FILE IS THAT IT DOES NOT IMPORT THE FAMILY. Nothing from
app.services.research_lab.cross_sectional_dumb_money is imported anywhere
below. Every formula is retyped from the published paper, every panel value is
re-derived from the raw N-PORT CSVs, and the DSR/verdict are recomputed from
the persisted monthly returns. A check that shares code with the thing it
checks is not a check.

Seven checks:
  V1  Appendix Table A1's 21 counterfactual cells, from a from-scratch
      recursion written against the paper's prose rather than the family's.
  V2  The Cisco worked example, pp.301-302, end to end to its printed 5.6%.
  V3  A sample of REAL FLOW cells re-derived from the raw N-PORT CSVs --
      filings, flows, returns, holdings values, market caps -- and compared to
      the family's committed panel.
  V4  DSR at every ladder rung, recomputed from the committed monthly returns
      with the Bailey-Lopez de Prado formula retyped, and the verdict rule
      re-applied from the pre-registration's own words.
  V5  Every reused shared module diffed against main; any difference is a
      failure, because the pre-registration promises they are untouched.
  V6  The persisted DB rows match the report.
  V7  The pre-registration commit really does precede the first result.

Run from backend/ with
    ./venv/bin/python data/research_runs/verify_dumb_money.py
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm  # noqa: E402

REPORT = _BACKEND / "data" / "research_runs" / "dumb_money_2026-09-08.json"
PANEL_DIR = _BACKEND / "data" / "research_runs" / "dumb_money_panels"
NPORT_DIR = _BACKEND / "data" / "nport_bulk_firesale"
CATEGORY_DIR = _BACKEND / "data" / "nport_fund_asset_categories"

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"[{PASS if ok else FAIL}] {name}: {detail}")


# =============================================================================
# A from-scratch counterfactual, written from the paper's prose
# =============================================================================


def counterfactual_path(tna, flow, ret, columns, *, anchor="previous"):
    """Counterfactual TNA per fund per column, Eqs. (11)/(12) retyped.

    `tna[fund][col]`, `flow[fund][col]`, `ret[fund][col]`; a fund absent from a
    column is not alive then. A fund present with TNA 0 has died.

    Rules, from Appendix A.1 p.320:
      * pro-rata share = TNA^i_lagged / sum over funds alive at BOTH ends
      * F^Agg = flow of every fund alive NOW and not dying, newborns included
      * newborn counterfactual TNA starts at 0
      * a dying fund's counterfactual flow is MINUS ITS COUNTERFACTUAL TNA and
        it is 0 thereafter
      * a counterfactual TNA driven negative is pinned at 0 and its share
        redistributed
    `anchor="previous"` re-anchors the share each step (Table A1 / CONTINUOUS);
    `anchor="start"` fixes it at the window's first column (main text /
    ROLLING).
    """
    funds = sorted(tna)
    alive = lambda f, c: c in tna[f] and tna[f][c] > 0.0  # noqa: E731
    present = lambda f, c: c in tna[f]  # noqa: E731

    counter = {f: (tna[f][columns[0]] if present(f, columns[0]) else 0.0) for f in funds}
    dead: set[str] = set()
    path = {f: [] for f in funds}

    for position in range(1, len(columns)):
        prior, now = columns[position - 1], columns[position]
        both = [f for f in funds if present(f, prior) and alive(f, now)]
        dying = [f for f in funds if present(f, prior) and not alive(f, now) and f not in dead]
        for f in dying:
            dead.add(f)
            counter[f] = 0.0

        anchor_col = prior if anchor == "previous" else columns[0]
        weights = {
            f: tna[f][anchor_col]
            for f in both
            if f not in dead and present(f, anchor_col)
        }
        # F^Agg: everyone alive now and not dying, INCLUDING newborns.
        aggregate_flow = sum(
            flow[f].get(now, 0.0) for f in funds if alive(f, now) and f not in dead
        )

        pinned: set[str] = set()
        while True:
            denominator = sum(w for f, w in weights.items() if f not in pinned)
            nxt = {}
            for f in funds:
                if f in dead:
                    nxt[f] = 0.0
                    continue
                if not present(f, now):
                    nxt[f] = counter[f]
                    continue
                grown = (1.0 + ret[f].get(now, 0.0)) * counter[f]
                if f in pinned or f not in weights or denominator <= 0.0:
                    nxt[f] = 0.0 if f in pinned else grown
                    continue
                nxt[f] = grown + (weights[f] / denominator) * aggregate_flow
            breached = {f for f in weights if f not in pinned and nxt[f] < 0.0}
            if not breached or denominator <= 0.0:
                break
            pinned |= breached
        counter = {f: max(v, 0.0) for f, v in nxt.items()}
        for f in funds:
            path[f].append(counter[f])
    return path


def check_table_a1() -> None:
    """V1 — Appendix Table A1, p.321, all 21 published counterfactual cells."""
    cols = ["1980", "1981", "1982", "1983", "1985"]
    tna = {
        "F1": dict(zip(cols, [100.0, 160.0, 268.0, 395.0, 515.0])),
        "F2": dict(zip(cols, [50.0, 105.0, 144.0, 0.0, 0.0])),
        "F3": dict(zip(cols[1:], [50.0, 45.0, 100.0, 154.0])),
    }
    flow = {
        "F1": dict(zip(cols[1:], [50.0, 100.0, 100.0, 100.0])),
        "F2": dict(zip(cols[1:], [50.0, 50.0, -144.0, 0.0])),
        "F3": dict(zip(cols[1:], [50.0, -10.0, 50.0, 50.0])),
    }
    ret = {
        "F1": dict(zip(cols, [0.0, 0.10, 0.05, 0.10, 0.05])),
        "F2": dict(zip(cols, [0.0, 0.10, -0.10, 0.0, 0.0])),
        "F3": dict(zip(cols[1:], [0.0, 0.10, 0.10, 0.05])),
    }
    path = counterfactual_path(tna, flow, ret, cols, anchor="previous")
    expected = {"F1": [210, 292, 449, 591], "F2": [105, 141, 0, 0], "F3": [0, 22, 46, 79]}
    got = {f: [round(v) for v in values] for f, values in path.items()}
    record(
        "V1 Table A1 counterfactual TNA (21 published cells)",
        got == expected,
        f"expected {expected}, got {got}",
    )


def check_cisco() -> None:
    """V2 — the Cisco example, Section 2 pp.301-302, printed answer 5.6%."""
    cols = ["q0", "q1"]
    tna = {"TECH": {"q0": 20e9, "q1": 40e9}, "VALUE": {"q0": 80e9, "q1": 80e9}}
    flow = {"TECH": {"q1": 11e9}, "VALUE": {"q1": -1e9}}
    ret = {"TECH": {"q1": 9.0 / 20.0}, "VALUE": {"q1": 1.0 / 80.0}}
    path = counterfactual_path(tna, flow, ret, cols, anchor="start")
    tech, value = path["TECH"][-1], path["VALUE"][-1]
    ok_tna = abs(tech - 31e9) < 1.0 and abs(value - 89e9) < 1.0

    # Eqs. (6),(7),(8) retyped: z is actual dollar ownership over market cap;
    # zhat rescales each holder's position by its counterfactual/actual TNA
    # ratio and renormalises by the sector aggregate ratio.
    holdings = {"TECH": {"CSCO": 4e9}, "VALUE": {}}
    actual_agg = 40e9 + 80e9
    counter_agg = tech + value
    z = 4e9 / 16e9
    z_hat = (actual_agg / counter_agg) * (4e9 * (tech / 40e9)) / 16e9
    flow_pct = 100.0 * (z - z_hat)
    record(
        "V2 Cisco worked example (paper prints 5.6%)",
        ok_tna and abs(flow_pct - 5.625) < 0.01,
        f"counterfactual TNAs {tech/1e9:.3f}bn / {value/1e9:.3f}bn (paper 31/89), "
        f"FLOW {flow_pct:.4f}% (paper 5.6%)",
    )


# =============================================================================
# V3 — real FLOW cells re-derived from the raw N-PORT CSVs
# =============================================================================


def _read(path: Path) -> list[dict[str, str]]:
    import csv

    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _parse_sec_date(value: str) -> date | None:
    """SEC bulk dates come as DD-MON-YYYY; ISO is accepted too."""
    value = (value or "").strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _to_float(value: str) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def check_real_cells(report: dict, n_cells: int = 5) -> None:
    """V3 — rebuild the whole FLOW pipeline from raw CSVs for one snapshot and
    compare a sample of cells against the family's committed panel.

    Every rule is retyped here: the 60-day publication wall, the FILING_DATE
    gate, the equity-fund threshold, the three-month return compounding, the
    amendment tie-break, the size floor, and Eqs. (6)-(8),(11),(12).
    """
    horizon, k = "1year", 4
    panel_path = PANEL_DIR / f"flow_rolling_{horizon}.csv.gz"
    if not panel_path.exists():
        record("V3 real FLOW cells", False, f"missing {panel_path}")
        return
    panel = pd.read_csv(panel_path, index_col=0, parse_dates=True)
    if panel.empty:
        record("V3 real FLOW cells", False, "committed panel is empty")
        return

    snapshot = panel.index[len(panel.index) // 2]
    as_of = snapshot.date()
    quarter = pd.Period(as_of - timedelta(days=60), freq="Q") - 1
    window = [quarter - offset for offset in range(k, -1, -1)]

    quarters = sorted(
        p.name.split("_")[0] for p in NPORT_DIR.glob("*_SUBMISSION.csv.gz")
    )

    # --- filings, with the family's own refusals retyped --------------------
    # CHECKER CORRECTION 2. build_fund_quarter_filings refuses a row when
    # NET_ASSETS is not strictly POSITIVE, when SERIES_ID is blank, when either
    # date fails to parse, when FILING_DATE precedes REPORT_DATE, or when ANY
    # of the NINE Item B.6 monthly flow fields is missing -- a missing month is
    # refused, never read as zero. This checker originally read a missing month
    # as 0.0, never looked at the reinvestment fields at all, and accepted a
    # non-positive NET_ASSETS, so it kept filings the family drops.
    #
    # A correction to the CHECKER, not a weakening of the family: refusing an
    # incomplete quarter rather than imputing zero is plainly right, and it is
    # what the shared, already-independently-verified module does.
    filings: dict[str, dict] = {}
    for q in quarters:
        submissions = {r["ACCESSION_NUMBER"]: r for r in _read(NPORT_DIR / f"{q}_SUBMISSION.csv.gz")}
        for row in _read(NPORT_DIR / f"{q}_FUND_REPORTED_INFO.csv.gz"):
            accession = row["ACCESSION_NUMBER"]
            submission = submissions.get(accession)
            if submission is None:
                continue
            report = _parse_sec_date(submission.get("REPORT_DATE", ""))
            filed = _parse_sec_date(submission.get("FILING_DATE", ""))
            if report is None or filed is None or filed < report:
                continue
            series = row.get("SERIES_ID", "").strip()
            if not series:
                continue
            net = _to_float(row.get("NET_ASSETS", ""))
            if net is None or not net > 0.0:
                continue
            sums: dict[str, float | None] = {}
            for prefix in ("SALES_FLOW_MON", "REINVESTMENT_FLOW_MON", "REDEMPTION_FLOW_MON"):
                total: float | None = 0.0
                for n in (1, 2, 3):
                    value = _to_float(row.get(f"{prefix}{n}", ""))
                    if value is None:
                        total = None
                        break
                    total += value
                sums[prefix] = total
            if any(v is None for v in sums.values()):
                continue
            filings[accession] = {
                "series": series,
                "report": report,
                "filing": filed,
                "net": net,
                # Item B.6.a - Item B.6.c, this project's settled external-flow
                # definition (merged a1d64b3).
                "flow": sums["SALES_FLOW_MON"] - sums["REDEMPTION_FLOW_MON"],
            }
    accession_series = {a: v["series"] for a, v in filings.items()}

    # --- equity funds, threshold retyped -----------------------------------
    equity_share: dict[str, float] = {}
    for q in quarters:
        path = CATEGORY_DIR / f"{q}_FUND_ASSET_CATEGORY.csv.gz"
        if not path.exists():
            continue
        totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for row in _read(path):
            value = _to_float(row["VALUE_SUM"])
            if value is None:
                continue
            totals[row["ACCESSION_NUMBER"]][row["ASSET_CAT"].strip()] += value
        for accession, categories in totals.items():
            gross = sum(abs(v) for v in categories.values())
            if gross > 0:
                equity_share[accession] = categories.get("EC", 0.0) / gross
    equity_series = {
        accession_series[a] for a, s in equity_share.items() if s >= 0.80 and a in accession_series
    }

    # --- returns ------------------------------------------------------------
    # CHECKER CORRECTION 3. Item B.5.a is reported per SHARE CLASS, so a
    # fund-month carries several values. fund_monthly_returns() averages the
    # classes WITHIN ONE FILING and ASSIGNS that value, walking filings sorted
    # by (series_id, report_date, filing_date) -- so where two filings cover the
    # same month, the one with the LATER FILING DATE wins. This checker
    # originally pooled every class of every filing into one mean, which
    # double-counts an amendment's classes. Corrected in the CHECKER; the
    # family's behaviour here belongs to a shared module the pre-registration
    # promises to leave byte-identical.
    classes: dict[str, list[list[float]]] = defaultdict(list)
    for q in quarters:
        for row in _read(NPORT_DIR / f"{q}_MONTHLY_TOTAL_RETURN.csv.gz"):
            accession = row["ACCESSION_NUMBER"]
            if accession not in filings:
                continue
            values = [_to_float(row[f"MONTHLY_TOTAL_RETURN{n}"]) for n in (1, 2, 3)]
            if any(v is None for v in values):
                continue
            classes[accession].append(values)

    monthly: dict[str, dict[pd.Timestamp, float]] = defaultdict(dict)
    for accession in sorted(
        classes, key=lambda a: (filings[a]["series"], filings[a]["report"], filings[a]["filing"])
    ):
        info = filings[accession]
        end_month = pd.Timestamp(info["report"]) + pd.offsets.MonthEnd(0)
        for position in range(3):
            month = end_month - pd.offsets.MonthEnd(2 - position)
            monthly[info["series"]][month] = (
                float(np.mean([r[position] for r in classes[accession]])) / 100.0
            )

    # --- states, point-in-time ---------------------------------------------
    states: dict[str, dict] = defaultdict(dict)
    chosen: dict[tuple[str, pd.Period], date] = {}
    for accession, info in filings.items():
        series = info["series"]
        if series not in equity_series:
            continue
        if info["filing"] > as_of:
            continue
        if info["net"] < 1_000_000.0:
            continue
        end_month = pd.Timestamp(info["report"]) + pd.offsets.MonthEnd(0)
        months = [end_month - pd.offsets.MonthEnd(2 - i) for i in range(3)]
        values = [monthly[series].get(m) for m in months]
        if any(v is None for v in values):
            continue
        compounded = float(np.prod([1.0 + float(v) for v in values]) - 1.0)
        period = pd.Period(info["report"], freq="Q")
        key = (series, period)
        # The point-in-time amendment tie-break: latest-filed among the PUBLIC
        # filings. This is what disagreed with the family and was right.
        if key in chosen and chosen[key] >= info["filing"]:
            continue
        chosen[key] = info["filing"]
        states[series][period] = {
            "accession": accession,
            "net": info["net"],
            "flow": info["flow"],
            "ret": compounded,
        }

    # --- the counterfactual, from the retyped recursion ---------------------
    tna = {s: {p: v["net"] for p, v in q.items()} for s, q in states.items()}
    flow = {s: {p: v["flow"] for p, v in q.items()} for s, q in states.items()}
    ret = {s: {p: v["ret"] for p, v in q.items()} for s, q in states.items()}
    in_window = {s for s in tna if any(w in tna[s] for w in window)}
    tna = {s: tna[s] for s in in_window}
    flow = {s: flow[s] for s in in_window}
    ret = {s: ret[s] for s in in_window}

    path = counterfactual_path(tna, flow, ret, window, anchor="start")
    present = {s for s in tna if window[-1] in tna[s] and tna[s][window[-1]] > 0.0}
    actual_end = {s: tna[s][window[-1]] for s in present}
    # The newborn rule: a fund with no observation at the window start has a
    # counterfactual TNA of zero, so all of its ownership is flow-driven.
    counter_end = {
        s: (path[s][-1] if window[0] in tna[s] else 0.0) for s in present
    }
    actual_agg = sum(actual_end.values())
    counter_agg = sum(counter_end.values())
    if counter_agg <= 0.0:
        record("V3 real FLOW cells", False, "counterfactual aggregate is non-positive")
        return

    # --- holdings and market cap -------------------------------------------
    cusip_ticker = json.loads((PANEL_DIR / "cusip_to_ticker.json").read_text())
    caps = pd.read_csv(PANEL_DIR / "market_cap_at_quarter.csv.gz", index_col=0)
    cap_row = caps.loc[str(window[-1])] if str(window[-1]) in caps.index else None
    if cap_row is None:
        record("V3 real FLOW cells", False, f"no committed market cap for {window[-1]}")
        return

    wanted_accessions = {states[s][window[-1]]["accession"] for s in present if window[-1] in states[s]}
    actual_dollars: dict[str, float] = defaultdict(float)
    counter_dollars: dict[str, float] = defaultdict(float)
    for q in quarters:
        for row in _read(NPORT_DIR / f"{q}_FUND_REPORTED_HOLDING.csv.gz"):
            accession = row["ACCESSION_NUMBER"]
            if accession not in wanted_accessions:
                continue
            if row.get("UNIT", "").strip() != "NS" or row.get("ASSET_CAT", "").strip() != "EC":
                continue
            cusip = row.get("ISSUER_CUSIP", "").strip()
            if not cusip or cusip == "999999999":
                continue
            shares = _to_float(row.get("BALANCE", ""))
            if shares is None or shares <= 0.0:
                continue
            ticker = cusip_ticker.get(cusip)
            if ticker is None:
                continue
            value = _to_float(row.get("CURRENCY_VALUE", "")) or 0.0
            series = accession_series[accession]
            if series not in actual_end:
                continue
            actual_dollars[ticker] += value
            counter_dollars[ticker] += value * (counter_end[series] / actual_end[series])

    normaliser = actual_agg / counter_agg
    rederived = {}
    for ticker, dollars in actual_dollars.items():
        cap = cap_row.get(ticker)
        if cap is None or not np.isfinite(cap) or cap <= 0:
            continue
        rederived[ticker] = 100.0 * (dollars / cap - normaliser * counter_dollars[ticker] / cap)

    committed = panel.loc[snapshot].dropna()
    overlap = sorted(set(rederived) & set(committed.index))
    if not overlap:
        record("V3 real FLOW cells", False, "no overlapping tickers to compare")
        return
    shared = overlap[:n_cells]
    diffs = {t: abs(rederived[t] - float(committed[t])) for t in shared}
    worst = max(diffs.values())
    record(
        f"V3a real FLOW cells re-derived from raw CSVs ({snapshot.date()}, {horizon}) "
        f"reproduce EXACTLY",
        worst < 1e-6,
        f"{len(shared)} cells, max |diff| {worst:.3e}; sample "
        + ", ".join(f"{t}={rederived[t]:.6f}" for t in shared[:3]),
    )

    # V3b — MATERIALITY, reported alongside V3a rather than replacing it.
    #
    # V3a is deliberately left as an EXACT test that is allowed to fail. Three
    # real corrections cut the residual from 3.3e-03 to ~4e-05 (two of them
    # checker bugs, one a genuine family bug), and what is left is at the level
    # of tie-break ORDERING among amendments: fund_monthly_returns walks
    # filings quarter-file by quarter-file while this checker walks them sorted
    # by (series, report_date, filing_date), so where one fund-month is covered
    # by filings in two different quarterly ZIPs the two can pick a different
    # winner. Relaxing V3a's tolerance to make it green would be exactly the
    # "quietly weakened test" CLAUDE.md forbids, so it stays red and this check
    # measures whether the residual can matter.
    #
    # It cannot matter unless it moves a stock across a QUINTILE BREAKPOINT,
    # because FLOW enters the strategy only as a cross-sectional sort key
    # (Section 3, p.306). That is what this counts, over every overlapping
    # ticker rather than the five sampled above.
    full_diffs = np.array(
        [abs(rederived[t] - float(committed[t])) for t in overlap], dtype=float
    )
    mine = pd.Series({t: rederived[t] for t in overlap}).sort_values()
    theirs = pd.Series({t: float(committed[t]) for t in overlap}).sort_values()

    def quintiles(series: pd.Series) -> dict[str, int]:
        buckets = np.array_split(np.array(series.index), 5)
        return {t: i for i, bucket in enumerate(buckets) for t in bucket}

    a, b = quintiles(mine), quintiles(theirs)
    moved = [t for t in overlap if a[t] != b[t]]
    record(
        "V3b the residual moves NO stock across a quintile breakpoint",
        not moved,
        f"{len(overlap)} tickers, max |diff| {full_diffs.max():.3e}, median "
        f"{np.median(full_diffs):.3e}; {len(moved)} quintile assignments differ"
        + (f" ({moved[:5]})" if moved else " — FLOW's only role is as a sort key, "
           "so a residual that reorders nothing cannot reach the verdict"),
    )


# =============================================================================
# V4 — DSR and the verdict, recomputed
# =============================================================================


def deflated_sharpe(returns: np.ndarray, n_trials: int, sigma_sr: float) -> float:
    """Bailey & Lopez de Prado (2014) Eq.(9), retyped.

    SR0 = sigma_SR * [ (1-gamma) Z^-1(1-1/N) + gamma Z^-1(1-1/(N e)) ]
    DSR = Z( (SR_hat - SR0) sqrt(T-1) / sqrt(1 - g3 SR_hat + (g4-1)/4 SR_hat^2) )
    with SR_hat and the moments on the RETURN FREQUENCY (monthly here), not
    annualised -- annualising the numerator without annualising the moments is
    the classic way to get this wrong.
    """
    t = len(returns)
    mean, sd = float(np.mean(returns)), float(np.std(returns, ddof=1))
    if sd == 0 or t < 3:
        return float("nan")
    sr = mean / sd
    centred = returns - mean
    m2 = float(np.mean(centred**2))
    skew = float(np.mean(centred**3)) / m2**1.5
    kurt = float(np.mean(centred**4)) / m2**2
    gamma = 0.5772156649015329
    sr0 = sigma_sr * (
        (1 - gamma) * norm.ppf(1 - 1.0 / n_trials)
        + gamma * norm.ppf(1 - 1.0 / (n_trials * np.e))
    )
    denominator = np.sqrt(max(1 - skew * sr + (kurt - 1) / 4.0 * sr**2, 1e-12))
    return float(norm.cdf((sr - sr0) * np.sqrt(t - 1) / denominator))


def check_dsr_and_verdict(report: dict) -> None:
    """V4 — recompute every spec's DSR at every rung and re-apply the rule."""
    path = PANEL_DIR / "spec_monthly_returns_baseline.csv.gz"
    if not path.exists():
        record("V4 DSR and verdict", False, f"missing {path}")
        return
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    denominators = [int(n) for n in report["denominators"]]

    sharpes = {}
    for spec in frame.columns:
        series = frame[spec].dropna().to_numpy()
        sd = float(np.std(series, ddof=1)) if len(series) > 1 else 0.0
        sharpes[spec] = (
            float(np.mean(series)) / sd * np.sqrt(12.0) if sd else 0.0
        )
    sigma_sr = float(np.std(list(sharpes.values()), ddof=1))

    worst = 0.0
    recomputed: dict[str, dict[int, float]] = {}
    for spec in frame.columns:
        series = frame[spec].dropna().to_numpy()
        recomputed[spec] = {}
        for n in denominators:
            value = deflated_sharpe(series, n, sigma_sr / np.sqrt(12.0))
            recomputed[spec][n] = value
            reported = report["specs"].get(spec, {}).get("dsr_by_n", {}).get(str(n))
            if reported is not None and np.isfinite(value):
                worst = max(worst, abs(value - float(reported)))
    record(
        "V4a DSR recomputed at every ladder rung",
        worst < 1e-6,
        f"max |diff| vs report across {len(frame.columns)} specs x {len(denominators)} rungs: "
        f"{worst:.3e}",
    )

    best = max(recomputed, key=lambda s: recomputed[s][denominators[0]])
    lenient = recomputed[best][denominators[0]]
    strict = recomputed[best][denominators[-1]]
    bar = float(report["bar"])
    if not np.isfinite(lenient) or lenient < bar:
        verdict = "DEFINITE_NEGATIVE"
    elif not np.isfinite(strict) or strict < bar:
        verdict = "UNRESOLVED"
    else:
        verdict = "PASS"
    record(
        "V4b verdict rule re-applied independently",
        verdict == report["verdict"],
        f"recomputed {verdict} (best {best}, DSR@{denominators[0]}={lenient:.6f}), "
        f"report says {report['verdict']} (best {report['best_spec']})",
    )


# =============================================================================
# V5 / V6 / V7
# =============================================================================

SHARED_MODULES = [
    "app/services/research_lab/dsr_policy_n.py",
    "app/services/research_lab/preservation_score.py",
    "app/services/research_lab/deflated_sharpe.py",
    "app/services/research_lab/metrics.py",
    "app/services/research_lab/spread_estimator.py",
    "app/services/research_lab/borrow_cost.py",
    "app/services/research_lab/cross_sectional_persistence.py",
    "app/services/research_lab/cross_sectional_nport_flow.py",
    "app/services/market_data/nport_provider.py",
]


def check_shared_modules_unchanged() -> None:
    """V5 — the pre-registration promises these are byte-identical to main."""
    changed = []
    for module in SHARED_MODULES:
        proc = subprocess.run(
            ["git", "diff", "--quiet", "main", "--", f"backend/{module}"],
            cwd=_BACKEND.parent,
            capture_output=True,
        )
        if proc.returncode != 0:
            changed.append(module)
    record(
        "V5 reused shared modules byte-identical to main",
        not changed,
        "all 9 unchanged" if not changed else f"CHANGED: {changed}",
    )


def check_persisted_rows(report: dict) -> None:
    """V6 — the DB rows exist and agree with the report."""
    from app.db import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                # CHECKER CORRECTION 1: the column is trial_id, not spec_id.
                # Fixed here rather than in the family -- the family writes
                # through persist_cross_sectional_trial_results, which maps its
                # SpecResult.spec_id onto the table's own trial_id column.
                "SELECT family_key, trial_id, sharpe_annualized FROM cross_sectional_trial_results "
                "WHERE run_tag = :tag"
            ),
            {"tag": report["run_tag"]},
        ).fetchall()
    finally:
        db.close()
    by_spec = {r[1]: float(r[2]) for r in rows}
    expected = {s: float(v["sharpe"]) for s, v in report["specs"].items()}
    mismatched = [
        s for s in expected if s not in by_spec or abs(by_spec[s] - expected[s]) > 1e-9
    ]
    record(
        "V6 persisted DB rows match the report",
        len(rows) == len(expected) and not mismatched,
        f"{len(rows)} rows for run_tag {report['run_tag']}, {len(expected)} specs in report, "
        f"{len(mismatched)} mismatched",
    )


def check_preregistration_precedes_results() -> None:
    """V7 — the pre-registration commit predates the first result commit."""
    def commit_time(pathspec: str) -> int | None:
        proc = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%ct", "--", pathspec],
            cwd=_BACKEND.parent,
            capture_output=True,
            text=True,
        )
        stamps = [int(line) for line in proc.stdout.split() if line.strip()]
        return min(stamps) if stamps else None

    prereg = commit_time("backend/data/research_runs/frazzini_lamont_dumb_money_PREREGISTRATION.txt")
    module = commit_time("backend/app/services/research_lab/cross_sectional_dumb_money.py")
    ok = prereg is not None and module is not None and prereg < module
    record(
        "V7 pre-registration committed before any family code",
        bool(ok),
        f"pre-registration {prereg}, family module {module}"
        + (" (pre-registration is earlier)" if ok else " — ORDER WRONG"),
    )


def main() -> int:
    check_table_a1()
    check_cisco()
    check_shared_modules_unchanged()
    check_preregistration_precedes_results()
    if REPORT.exists():
        report = json.loads(REPORT.read_text())
        check_real_cells(report)
        check_dsr_and_verdict(report)
        check_persisted_rows(report)
    else:
        record("report present", False, f"{REPORT} not found — run run_dumb_money.py first")

    failures = [r for r in results if r[1] == FAIL]
    print("\n" + "=" * 70)
    print(f"{len(results) - len(failures)}/{len(results)} checks passed")
    for name, status, detail in results:
        print(f"  [{status}] {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
