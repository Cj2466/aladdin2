"""Production runner for the aggregate-dividend-payment price-pressure family.

Calls the module's OWN entry point (run_dividend_pressure_screening) -- not a
reimplementation, not a shortcut -- then persists every per-spec result of the
BASELINE cost arm to the shared cross_sectional_trial_results table and writes
the git-durable plain-text and JSON run reports.

Checked into data/research_runs/ alongside the pre-registration and the report
so the exact invocation that produced the numbers is reproducible from the repo
rather than living only in a scratchpad. Run from backend/ with
./venv/bin/python data/research_runs/run_dividend_payment_pressure.py

Needs the point-in-time price store (SPY plus the universe's market-cap price
basis) and the dividend/payment/share-count cache built by
data/research_runs/fetch_dividend_payment_calendar.py. No paid data.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv, whose site-packages
# resolves `app` to the MAIN worktree's backend/app. Without the lines below
# this runner silently screens main's code instead of this branch's.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The screen would have run against another checkout's code."
    )

from app.db import SessionLocal
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
    verify_persisted_trial_results,
)
from app.services.research_lab.dividend_payment_pressure_timing import (
    BASELINE_COST_ARM,
    COST_ARMS,
    DIVIDEND_PAYMENT_N_TRIALS,
    DIVIDEND_PRESSURE_CITATION,
    PAPER_CIRCULATION_DATE,
    SCREENING_FLOOR,
    TOP_N_THRESHOLDS,
    VALIDATED_EDGE_BAR,
    build_dividend_pressure_disclosure,
    default_dividend_pressure_config,
    run_dividend_pressure_screening,
)

RUN_TAG = "dividend_payment_pressure_build_2026-09-06"
FAMILY_KEY = "dividend_payment_pressure"
REPORT_PATH = "data/research_runs/dividend_payment_pressure_2026-09-06.txt"
JSON_PATH = "data/research_runs/dividend_payment_pressure_2026-09-06.json"

RUN_END = date(2026, 9, 6)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout
)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger("dividend_payment_pressure_runner")


def _fmt(value, spec: str = ".4f") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and math.isnan(value):
        return "n/a"
    if not isinstance(value, (int, float)):
        return str(value)
    return format(value, spec)


def build_report(summary, elapsed: float) -> str:
    lines: list[str] = []
    add = lines.append
    verdict, best_id = summary.verdict(VALIDATED_EDGE_BAR)
    denominators = summary.denominators
    n_local = denominators[0] if denominators else summary.n_trials

    add("=" * 112)
    add("AGGREGATE DIVIDEND-PAYMENT PRICE PRESSURE (Hartzmark & Solomon, AER 2025) — RESULTS")
    add("=" * 112)
    add(f"run_tag={RUN_TAG}   wall clock {elapsed / 60:.1f} min")
    add("")
    add("SOURCE: " + DIVIDEND_PRESSURE_CITATION)
    add("")
    add(
        "PRE-REGISTRATION: data/research_runs/dividend_payment_pressure_PREREGISTRATION.txt, "
        "committed as 92a6f5b BEFORE this module or this run existed."
    )
    add(
        "The grid below is that document's 34-spec grid, unchanged, and the pass/fail rule and the "
        "three vetoes applied at the end are that document's, unchanged."
    )
    add("")
    add(
        f"VERDICT (Policy D two-tier, bar = {VALIDATED_EDGE_BAR:.2f}, BASELINE cost arm, best "
        f"NON-CONTROL NON-PLACEBO spec): {verdict.upper()}"
    )
    add(f"  best candidate spec by DSR at n_local={n_local}: {best_id or 'none'}")
    add(f"  DSR denominators reported: {denominators}")
    add(f"  screening floor (not a pass): {SCREENING_FLOOR:.2f}")
    add("")
    add(f"  formation window: {summary.formation_start} .. {summary.window_end}")
    add(f"  point-in-time universe: {summary.n_universe_tickers} tickers")
    for w in summary.warnings:
        add(f"  WARNING: {w}")
    add("")

    # ---- the number the whole build must be read against ----
    add("=" * 112)
    add("READ EVERYTHING BELOW AGAINST THIS, WHICH WAS COMPUTED BEFORE THE RUN")
    add("=" * 112)
    add("Pre-registration 10.2, from the paper's OWN Table III magnitudes:")
    add("  * a demeaned long/short book at N=126 implies an expected Sharpe of ~0.26,")
    add("    and at N=10 of ~0.30 — BOTH BELOW this project's 0.50 screening floor and far")
    add("    below its 0.95 DSR bar. A PERFECT, UNDECAYED, ZERO-COST REPLICATION OF THE")
    add("    PAPER'S OWN REPORTED MAGNITUDE WOULD STILL NOT PASS.")
    add("  * this build has ~1/11 of the paper's observations, so its expected regression")
    add("    t-statistic is 3.32 * sqrt(2100/24000) = 0.98. A |t| near 1 with the RIGHT SIGN")
    add("    is the SUCCESS case for the fidelity regressions, not a failure.")
    add("So the DSR verdict is nearly foreordained and is the LEAST informative output here.")
    add("The informative questions are the F-checks: does the effect appear at all, at the")
    add("right sign and rough magnitude, on 2018-2026 data the published paper never saw?")
    add("")

    # ---- the data build ----
    report = summary.calendar_report
    if report is not None:
        add("=" * 112)
        add("THE DATA BUILD — WHAT THE AGGREGATE IS ACTUALLY MADE OF")
        add("=" * 112)
        add(f"  tickers requested (point-in-time pool):   {report.n_tickers_requested}")
        add(f"  tickers with a resolved price:            {report.n_tickers_priced}")
        add(f"  tickers with any dividend history:        {report.n_tickers_with_dividends}")
        add(f"  ex-dates in the raw calendar:             {report.n_ex_dates}")
        add(f"  tickers with their OWN ex->pay lag:       {report.n_tickers_with_ticker_lag}")
        add(f"  events falling back to the median lag:    {report.n_events_on_universe_median_lag}")
        add(f"  universe median ex->pay lag (cal. days):  {_fmt(report.universe_median_lag_days, '.1f')}")
        if report.lag_percentiles:
            p = report.lag_percentiles
            add(
                f"  lag distribution: min {p['min']:.0f}  p10 {p['p10']:.0f}  median "
                f"{p['median']:.0f}  p90 {p['p90']:.0f}  max {p['max']:.0f}  mean {p['mean']:.1f}"
            )
            add(
                "    [HS22] Section III.A states the gap as 'on average 22 days after the "
                "ex-date' — compare the mean above."
            )
        add(f"  tickers with SEC share counts:            {report.n_tickers_with_share_counts}")
        add(f"  priced tickers resolving no CIK:          {report.n_priced_without_cik}")
        add(f"  tickers with no usable share count:       {summary.n_no_share_count}")
        add(f"  Nasdaq ground-truth coverage tally:       {report.nasdaq_tally}")
        add("")
        add("  DIVIDEND-EVENT ACCOUNTING PER DATING (an event with no visible share count is")
        add("  NOT a dollar figure and is dropped, and counted here rather than absorbed):")
        for dating, counts in summary.skip_counts.items():
            add(f"    {dating:<9} {counts}")
        add("")
        add("  POINT-IN-TIME CONTRACT (assert_no_lookahead, checked on the real calendar):")
        for dating, violations in summary.lookahead_violations.items():
            note = (
                "MUST be 0 — every dividend in D_t must already have gone ex"
                if dating == "payment"
                else "equals every event BY CONSTRUCTION — the disclosed weakness of this arm, "
                "which rests on the paper's own ~21-day declaration-to-ex gap"
            )
            add(f"    {dating:<9} {violations:>7}   ({note})")
        add("")

    # ---- F7 ----
    imp = summary.imputation
    if imp is not None:
        add("=" * 112)
        add("FIDELITY CHECK F7 — THE PAYMENT-DATE IMPUTATION, MEASURED AGAINST REAL PAY DATES")
        add("=" * 112)
        add("Ground truth is Nasdaq's own dividend-history API, which carries real historical")
        add("(ex, record, DECLARATION, payment) tuples. It covers only Nasdaq-listed names —")
        add("it answers 'Dividend History for Non-Nasdaq symbols is not available' for NYSE —")
        add("so it cannot be a primary source, but it is real independent ground truth.")
        add("A DATA-QUALITY MEASUREMENT CONTAINING NO RETURN OF ANY KIND.")
        add("")
        add(f"  tickers with ground truth:            {imp.n_tickers_covered}")
        add(f"  (ex, pay) pairs compared:             {imp.n_events_compared}")
        if imp.n_events_compared:
            n = imp.n_events_compared
            add(
                f"  imputed date EXACT:                   {imp.n_exact} ({imp.n_exact / n:.1%})"
            )
            add(
                f"  within 1 calendar day:                {imp.n_within_1_day} "
                f"({imp.n_within_1_day / n:.1%})"
            )
            add(
                f"  within 2 calendar days:               {imp.n_within_2_days} "
                f"({imp.n_within_2_days / n:.1%})"
            )
            add(
                f"  within 5 calendar days:               {imp.n_within_5_days} "
                f"({imp.n_within_5_days / n:.1%})"
            )
        add(f"  mean SIGNED error (days, +ve = late):  {_fmt(imp.mean_signed_error_days, '.2f')}")
        add(f"  median signed error:                  {_fmt(imp.median_signed_error_days, '.2f')}")
        add(f"  mean ABSOLUTE error:                  {_fmt(imp.mean_absolute_error_days, '.2f')}")
        add(f"  p90 absolute error:                   {_fmt(imp.p90_absolute_error_days, '.2f')}")
        add(
            f"  median WITHIN-FIRM sd of the lag:     "
            f"{_fmt(imp.median_within_firm_lag_sd_days, '.2f')}"
        )
        add("    (the single-observation imputation assumes a firm's lag is stable over time;")
        add("     this is the measured size of the drift it is assuming away)")
        add("")
        add("  THE EX-DATE ARM'S POINT-IN-TIME ASSUMPTION, measurable only here because Nasdaq")
        add("  is the one free source carrying DECLARATION dates:")
        add(f"    declaration/ex pairs:               {imp.n_declaration_pairs}")
        add(
            f"    median declaration-to-ex gap:       "
            f"{_fmt(imp.median_declaration_to_ex_days, '.1f')} days   "
            f"([HS22]: 'on average 21 days')"
        )
        add(
            f"    fraction declared BEFORE the ex-day: "
            f"{_fmt(imp.fraction_declared_before_ex, '.4f')}"
        )
        add("")

    # ---- F1..F6, F8 per dating ----
    for dating, f in summary.fidelity_by_dating.items():
        primary = dating == "payment"
        add("=" * 112)
        add(
            f"FIDELITY CHECKS F1-F6, F8 — DATING = {dating.upper()}"
            + ("   <-- THE PRIMARY DATING (the paper's own choice)" if primary else
               "   (the arm this project's existing infrastructure natively provides)")
        )
        add("=" * 112)
        add("All regressions use HC0 (White 1980) standard errors. NO year-by-month fixed")
        add("effects enter any TRADED spec — a portfolio cannot have a fixed effect estimated")
        add("from the future — but both specifications are reported because both are the")
        add("paper's own.")
        add("")
        add("  F1 — [HS22] TABLE I: MktRet_t on the cumulative PAYMENT YIELD over days t, t-1")
        add("       paper: coef 59.50 t=3.32 (no FE); 67.07 t=3.47 (FE); one SD = +3.2 bp")
        for label, r in (("no FE", f.primary_no_fe), ("with FE", f.primary_with_fe)):
            add(
                f"       {label:<8} coef {r.coefficient:+12.4f}  t(HC0) {r.t_stat:+7.3f}  "
                f"R^2 {r.r_squared:.5f}  n {r.n_obs}  one-SD {r.bps_per_one_sd:+7.2f} bp"
            )
        add("")
        add("  F1b — [HS22] TABLE II PANEL A: the same on the PRICE-INDEPENDENT abnormal yield")
        add("        paper: positive, significant at 1%; one SD = +2.7 bp")
        for label, r in (("no FE", f.abnormal_no_fe), ("with FE", f.abnormal_with_fe)):
            add(
                f"       {label:<8} coef {r.coefficient:+12.6f}  t(HC0) {r.t_stat:+7.3f}  "
                f"R^2 {r.r_squared:.5f}  n {r.n_obs}  one-SD {r.bps_per_one_sd:+7.2f} bp"
            )
        add("")
        add("  F2 — **THE FUTURE-DIVIDEND PLACEBO** ([HS22] Table I cols 5-6). Dividends paid")
        add("       on days t+1 and t+2 regressed on day t's return. Cash that has not arrived")
        add("       cannot be reinvested. paper: 'economically small and insignificant'.")
        for label, r in (("no FE", f.placebo_no_fe), ("with FE", f.placebo_with_fe)):
            add(
                f"       {label:<8} coef {r.coefficient:+14.6e}  t(HC0) {r.t_stat:+7.3f}  "
                f"n {r.n_obs}  one-SD {r.bps_per_one_sd:+7.2f} bp"
            )
        add("       READING: this is a PRE-DECLARED VETO. If |t| here is as large as F1's, what")
        add("       this build measured is NOT payment-date price pressure.")
        add("")
        add("  F3 — [HS22] TABLE I COLUMN 1: the LAG STRUCTURE, one payment yield per lag")
        add("       paper: lag0 55.76 (t=1.74), lag1 60.04 (t=2.73), lags 2-3 small/insig,")
        add("       lag4 marginal (t=1.89) — which the paper's own footnote 9 attributes to")
        add("       pre-1960 settlement delays, a period this build does not have.")
        add("       lag    coefficient      t(HC0)      n")
        add("       " + "-" * 46)
        for p in f.lag_structure:
            add(f"       {p.lag:3d}   {p.coefficient:+13.4f}  {p.t_stat:+9.3f}   {p.n_obs}")
        add("")
        add("  F4 — **[HS22] FIGURE 1: QUINTILE MONOTONICITY** of the ABNORMAL yield")
        add("       paper: monotonically increasing, roughly 2, 2, 4, 4, 8 bp (top ~4x bottom)")
        add("       quintile   mean SPY return (bp)    n days")
        add("       " + "-" * 48)
        for q in f.abnormal_quintiles:
            add(f"       {q.quintile:5d}      {q.mean_return_bps:+14.2f}      {q.n_days:6d}")
        if len(f.abnormal_quintiles) >= 2:
            values = [q.mean_return_bps for q in f.abnormal_quintiles]
            monotone = all(b >= a for a, b in zip(values, values[1:], strict=False))
            ratio = (values[-1] / values[0]) if values[0] not in (0.0,) else float("nan")
            add("")
            add(
                f"       MONOTONIC INCREASING: {'YES' if monotone else 'NO'}   "
                f"top/bottom ratio {_fmt(ratio, '.2f')} (paper: ~4x)"
            )
        add("")
        add("  F5 — [HS22] TABLE II PANEL B: the top-N-day DUMMY regressions (raw dollars)")
        add("       paper: N=10 +9.8bp t=2.39 (no FE), +11.6bp (FE); N=63 +7.1bp t=4.27 (FE);")
        add("              N=84 +5.7bp t=3.71 (FE); N=126 +4.7bp t=3.15 (FE)")
        add("        N     coef(bp)   t(HC0)   coef FE(bp)  t FE     realized freq   n")
        add("       " + "-" * 72)
        for p in f.threshold_dummies:
            add(
                f"       {p.n_days:4d}  {p.coefficient_bps:+9.2f} {p.t_stat:+8.3f}  "
                f"{p.coefficient_bps_fe:+10.2f} {p.t_stat_fe:+7.3f}  "
                f"{p.realized_frequency:13.4f}   {p.n_obs}"
            )
        add(
            "       realized freq is checked against the PRE-DECLARED N/252 "
            f"({', '.join(f'{n}->{n / 252:.4f}' for n in TOP_N_THRESHOLDS)}); a gap is the"
        )
        add("       declared tie rule admitting extra days, and is visible rather than hidden.")
        add("")
        s = f.scaling_agreement
        add("  F6 — **MARKET-CAP vs PRIOR-YEAR-AVERAGE SCALING AGREEMENT** ([HS22]'s own")
        add("       robustness claim: the abnormal-yield estimate is 'similar to the 3.2 b.p.")
        add("       found from the same specification normalizing by market capitalization')")
        add(f"       corr(mktcap, abnormal) = {s.correlation_mktcap_abnormal:+.4f}")
        add(f"       corr(raw,    mktcap)   = {s.correlation_raw_mktcap:+.4f}")
        add(f"       corr(raw,    abnormal) = {s.correlation_raw_abnormal:+.4f}")
        add(
            f"       one-SD effect: mktcap {s.bps_per_one_sd_mktcap:+.2f} bp vs abnormal "
            f"{s.bps_per_one_sd_abnormal:+.2f} bp   (paper: 3.2 vs 2.7 bp)"
        )
        add("       Jaccard overlap of the two scalings' top-N day sets:")
        for n, j in s.jaccard_by_threshold.items():
            add(f"         N={n:4d}   {_fmt(j, '.4f')}")
        add("")
        d = f.data_sanity
        add("  F8 — DATA SANITY against economically meaningful known quantities")
        add(
            f"       fraction of trading days with a payment: {d.fraction_days_with_payment:.4f}"
            "    ([HS22]: 'over 90% of trading days involve a dividend payment')"
        )
        add(
            f"       implied AGGREGATE ANNUAL DIVIDEND YIELD:  "
            f"{d.implied_annual_dividend_yield:.4%}"
        )
        add("         ^ THE CHECK THAT WOULD CATCH A BROKEN SPLIT-BASIS JOIN. A large-cap US")
        add("           index yield lives in the low single digits of percent; an order of")
        add("           magnitude away means SEC raw share counts were multiplied by Yahoo's")
        add("           split-adjusted per-share amounts without being put on one basis.")
        add(f"       mean aggregate market cap:               ${d.mean_aggregate_market_cap:,.0f}")
        add(f"       total dividend dollars over {d.n_years:.1f} years:  ${d.total_dividend_dollars:,.0f}")
        add(f"       largest single day's share of the total: {d.top_day_share_of_total:.4%}")
        top_dom = sorted(d.dollars_by_day_of_month.items(), key=lambda kv: -kv[1])[:6]
        add(
            "       heaviest days of the MONTH by dollars:   "
            + ", ".join(f"{day}({value / d.total_dividend_dollars:.1%})" for day, value in top_dom)
        )
        add("         ^ the structural basis for the turn-of-month control: if the dollars pile")
        add("           onto the 1st and the month-end, a high-dividend-day indicator IS")
        add("           substantially a calendar indicator.")
        add("")

    # ---- the post-hoc, corrective burn-in diagnostic ----
    b = summary.abnormal_burn_in
    if b is not None:
        add("=" * 112)
        add("POST-HOC CORRECTIVE DIAGNOSTIC — NOT PRE-REGISTERED, DECLARED AS SUCH")
        add("=" * 112)
        add("Added AFTER F6 came back reporting that [HS22]'s OWN market-cap-versus-prior-year-")
        add("average agreement claim FAILED here. The pre-registration pre-declared that a sharp")
        add("divergence would be 'an important finding in its own right'. IT WOULD HAVE BEEN A")
        add("FABRICATED ONE, and this is what establishes that.")
        add("")
        add("THE DEFECT: the abnormal denominator averages dividends over trading days t-20..t-272,")
        add("so early formations read a window lying inside the PADDING — and the padding has almost")
        add("no dividend DOLLARS, because the SEC share counts that turn per-share amounts into")
        add("dollars only become visible at frame CY2017Q3 + 90 days (~2017-12-29).")
        add("")
        add(f"  padding trading days:                     {b.padding_trading_days}")
        add(
            f"  ...of which carry a non-zero dividend:    {b.padding_nonzero_dividend_days}"
            f"   (total ${b.padding_total_dollars:,.0f})"
        )
        add(
            f"  formation days carrying a dividend:       {b.formation_nonzero_dividend_days}"
            f"   (total ${b.formation_total_dollars:,.0f})"
        )
        add(
            f"  formation days with a CONTAMINATED window: {b.n_contaminated_days} of "
            f"{b.n_formation_days} ({b.n_contaminated_days / max(b.n_formation_days, 1):.1%})"
        )
        add("")
        add("                                  AS RUN (what F6 reports)      CLEAN SUBSET ONLY")
        add("    " + "-" * 76)
        add(
            f"    corr(raw, abnormal)              {b.corr_raw_abnormal_as_run:+21.4f}"
            f"{b.corr_raw_abnormal_clean:+24.4f}"
        )
        add(
            f"    corr(mktcap, abnormal)           {b.corr_mktcap_abnormal_as_run:+21.4f}"
            f"{b.corr_mktcap_abnormal_clean:+24.4f}"
        )
        add(
            f"    abnormal signal p99              {b.abnormal_p99_as_run:21.2f}"
            f"{b.abnormal_p99_clean:24.2f}"
        )
        add(
            f"    abnormal signal max              {b.abnormal_max_as_run:21.2f}"
            f"{b.abnormal_max_clean:24.2f}"
        )
        add("")
        add("READING, AND IT CORRECTS THIS BUILD RATHER THAN THE PAPER: once the burn-in artifact")
        add("is removed, [HS22]'s market-cap-versus-prior-year-average agreement REPLICATES, and")
        add("strongly. The as-run F6 divergence is an artifact of this build's own padding, not a")
        add("property of the data and not a finding about the paper. Reporting it as a finding")
        add("would have been a fabricated one.")
        add("")
        add("THE FROZEN WINDOW WAS NOT MOVED AND NO SPEC WAS RE-RUN. Changing a frozen formation")
        add("window after seeing a result is precisely the move the pre-registration exists to")
        add("prevent, and the verdict does not turn on this: the best candidate spec is a `raw`")
        add("one, which has no such denominator. A successor should pad the dividend panel with")
        add("enough share-count history to warm a 272-day denominator before re-testing the")
        add("abnormal arm; its eight specs' numbers here should be treated as unreliable.")
        add("")

    # ---- the specs ----
    for arm in COST_ARMS:
        results = summary.results_by_cost_arm.get(arm.key, [])
        if not results:
            continue
        is_baseline = arm.key == BASELINE_COST_ARM
        add("=" * 112)
        add(f"COST ARM: {arm.key.upper()}" + ("   <-- THE VERDICT ARM" if is_baseline else ""))
        add("=" * 112)
        add(f"  {arm.description}")
        add(
            f"  sigma_sr (sibling Sharpe dispersion, ddof=1): "
            f"{_fmt(summary.sigma_sr_by_cost_arm.get(arm.key))}"
        )
        add("")
        header = "  ".join(f"DSR@{n:<4d}" for n in summary.denominators)
        add(
            f"    spec                                   Sharpe    {header}   presv    hedgedSR  "
            " longSR   boot p   turn/yr"
        )
        add("    " + "-" * 130)
        for r in sorted(
            results,
            key=lambda x: (
                x.dsr_by_n.get(n_local) if x.dsr_by_n.get(n_local) is not None else -1.0
            ),
            reverse=True,
        ):
            ladder = "  ".join(_fmt(r.dsr_by_n.get(n)).rjust(8) for n in summary.denominators)
            marker = " [CTRL]" if r.is_control else (" [PLCB]" if r.is_placebo else "")
            add(
                f"    {r.spec_id + marker:<37} {r.sharpe_annualized:+8.4f}  {ladder}  "
                f"{_fmt(r.preservation.get('preservation_score')):>7}  "
                f"{r.confound.residual_sharpe:+8.4f}  "
                f"{r.confound.long_only_sharpe:+8.4f}  "
                f"{_fmt(r.confound.bootstrap_p_value, '.4f'):>7}  {r.annual_turnover:7.1f}"
            )
        add("")
        if is_baseline:
            add("    [CTRL] = turn-of-the-month calendar control, NO dividend data, in the grid")
            add("            to be beaten. [PLCB] = the paper's own future-dividend placebo,")
            add("            PRE-DECLARED TO FAIL and NOT point-in-time tradeable. Neither is")
            add("            eligible for the verdict.")
            add("    hedgedSR is the Sharpe of the BETA-HEDGED stream (y - beta*x) against")
            add("            buy-and-hold SPY — NOT the OLS residual, whose mean is zero by")
            add("            construction. longSR is the LONG-ONLY book's Sharpe, which shows")
            add("            how much of a positive would simply be the equity premium.")
            add("")
            add("  CONFOUND AND EXPOSURE DETAIL (baseline arm):")
            add("")
            add(
                "    spec                                   mean pos  mean|pos|  frac>0  mkt beta"
                "   ann alpha   TOM overlap  TOM corr   high days"
            )
            add("    " + "-" * 134)
            for r in sorted(results, key=lambda x: x.spec_id):
                c = r.confound
                add(
                    f"    {r.spec_id:<37} {c.mean_position:+9.4f} {c.mean_abs_position:10.4f} "
                    f"{c.fraction_long:7.3f} {c.market_beta:+9.4f} "
                    f"{c.market_alpha_annualized:+10.4f}  "
                    f"{_fmt(c.turn_of_month_overlap, '.4f'):>11}  "
                    f"{_fmt(c.turn_of_month_position_correlation, '.4f'):>8}   {r.n_high_days:6d}"
                )
            add("")
            add("    TOM overlap = the fraction of this spec's HIGH days that fall inside the")
            add("    turn-of-the-month window. That is F10, and it is the quantitative basis for")
            add("    reading the control: a dividend signal that fires almost entirely on")
            add("    turn-of-month days is a calendar signal whatever it is called.")
            add("")
            add("  WINDOW SPLITS (baseline arm):")
            add("")
            add(
                "    spec                                   full SR   thru2018  post2018  "
                "pre-circ  post-circ   thirds"
            )
            add("    " + "-" * 124)
            for r in sorted(results, key=lambda x: x.spec_id):
                c = r.confound
                thirds = " ".join(f"{s:+.2f}" for s in c.subperiod_sharpes)
                add(
                    f"    {r.spec_id:<37} {r.sharpe_annualized:+8.4f}  "
                    f"{_fmt(c.sharpe_in_paper_window):>8}  "
                    f"{_fmt(c.sharpe_after_paper_window):>8}  "
                    f"{_fmt(c.sharpe_before_circulation):>8}  "
                    f"{_fmt(c.sharpe_after_circulation):>9}   {thirds}"
                )
            add("")
            add(
                f"    pre-/post-circ splits at {PAPER_CIRCULATION_DATE} ([HS22]'s NBER "
                "circulation). This is a WEAK post-publication proxy:"
            )
            add(
                "    the formation window begins 2018-01-02, so almost none of it predates the"
                " paper's own sample end and only"
            )
            add("    part of it postdates circulation. It is reported for completeness, not as a")
            add("    decay measurement.")
            add("")
            add("  COST AND TURNOVER (baseline arm, cumulative return units):")
            add("")
            add(
                "    spec                                   net cum    cost drag  fin. drag   "
                "turnover   changes  realized freq"
            )
            add("    " + "-" * 128)
            for r in sorted(results, key=lambda x: x.spec_id):
                add(
                    f"    {r.spec_id:<37} {r.net_cumulative_return:+10.4f} "
                    f"{r.total_cost_drag:10.4f} {r.total_financing_drag:10.4f} "
                    f"{r.total_turnover:10.1f} {r.n_position_changes:9d} "
                    f"{r.realized_high_frequency:14.4f}"
                )
            add("")

    add("=" * 112)
    add("DISCLOSURE AND THE THREE PRE-DECLARED VETOES — TRAVELS WITH EVERY NUMBER ABOVE")
    add("=" * 112)
    for line in build_dividend_pressure_disclosure(summary, default_dividend_pressure_config()):
        add(f"  * {line}")
    add("")
    add(
        "  NO FORWARD-VALIDATION REGISTRATION was created by this run under any outcome. "
        "Registration is a separate, later, human decision (CLAUDE.md 6.6)."
    )
    return "\n".join(lines)


def _serialize_result(r) -> dict:
    payload = asdict(r)
    payload["dsr_by_n"] = {str(k): v for k, v in r.dsr_by_n.items()}
    return payload


def main() -> int:
    started = time.time()
    logger.info("screening the aggregate dividend-payment-pressure family")
    summary = run_dividend_pressure_screening(end=RUN_END)
    elapsed = time.time() - started

    report = build_report(summary, elapsed)
    (_BACKEND / REPORT_PATH).write_text(report + "\n")
    logger.info("report written to %s", REPORT_PATH)

    verdict, best_id = summary.verdict(VALIDATED_EDGE_BAR)
    payload = {
        "run_tag": RUN_TAG,
        "family_key": FAMILY_KEY,
        "n_trials": summary.n_trials,
        "declared_n_trials": DIVIDEND_PAYMENT_N_TRIALS,
        "denominators": summary.denominators,
        "validated_edge_bar": VALIDATED_EDGE_BAR,
        "screening_floor": SCREENING_FLOOR,
        "verdict": verdict,
        "best_spec": best_id,
        "citation": DIVIDEND_PRESSURE_CITATION,
        "preregistration": "data/research_runs/dividend_payment_pressure_PREREGISTRATION.txt",
        "formation_start": str(summary.formation_start),
        "window_end": str(summary.window_end),
        "n_universe_tickers": summary.n_universe_tickers,
        "n_no_share_count": summary.n_no_share_count,
        "skip_counts": summary.skip_counts,
        "lookahead_violations": summary.lookahead_violations,
        "warnings": summary.warnings,
        "sigma_sr_by_cost_arm": summary.sigma_sr_by_cost_arm,
        "calendar_report": asdict(summary.calendar_report) if summary.calendar_report else None,
        "imputation_validation": asdict(summary.imputation) if summary.imputation else None,
        "abnormal_burn_in_diagnostic": (
            asdict(summary.abnormal_burn_in) if summary.abnormal_burn_in else None
        ),
        "fidelity_by_dating": {
            dating: asdict(checks) for dating, checks in summary.fidelity_by_dating.items()
        },
        "results_by_cost_arm": {
            arm: [_serialize_result(r) for r in results]
            for arm, results in summary.results_by_cost_arm.items()
        },
        "disclosure": build_dividend_pressure_disclosure(
            summary, default_dividend_pressure_config()
        ),
    }
    (_BACKEND / JSON_PATH).write_text(json.dumps(payload, indent=2, default=str) + "\n")
    logger.info("json written to %s", JSON_PATH)

    # PERSISTENCE, AND WHY IT IS CHECKED RATHER THAN ASSUMED. See
    # cross_sectional_persistence.verify_persisted_trial_results' docstring: two
    # families this session left committed reports that no database row backs.
    # Only the BASELINE cost arm's rows are persisted -- the other two arms are
    # the same 34 trials re-scored under a changed assumption, not new trials,
    # and writing them would triple-count this family in every future pooled
    # effective-N computation that reads this table.
    db = SessionLocal()
    try:
        baseline = summary.baseline_results
        if not baseline:
            raise SystemExit(
                "REFUSING TO FINISH: the baseline cost arm produced no replayable spec, so there "
                "is nothing to persist and the report above describes nothing."
            )
        written = persist_cross_sectional_trial_results(
            db, FAMILY_KEY, baseline, run_tag=RUN_TAG
        )
        verify_persisted_trial_results(db, RUN_TAG, written, family_key=FAMILY_KEY)
        logger.info("persisted and verified %d baseline rows under run_tag=%s", written, RUN_TAG)
    finally:
        db.close()

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
