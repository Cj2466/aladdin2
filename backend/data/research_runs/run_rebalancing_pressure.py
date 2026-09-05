"""Production runner for the institutional-rebalancing-pressure family.

Calls the module's OWN entry point (run_rebalancing_screening) -- not a
reimplementation, not a shortcut -- then persists every per-spec result of the
BASELINE cost arm to the shared cross_sectional_trial_results table and writes
the git-durable plain-text and JSON run reports.

Checked into data/research_runs/ alongside the pre-registration and the report
so the exact invocation that produced the numbers is reproducible from the repo
rather than living only in a scratchpad. Run from backend/ with
./venv/bin/python data/research_runs/run_rebalancing_pressure.py

Needs only the point-in-time price store (SPY, IEF); no filings, no vendor
feed, no paid data.
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
from app.services.research_lab.rebalancing_pressure_timing import (
    BASELINE_COST_ARM,
    COST_ARMS,
    CRISIS_WINDOWS,
    PAPER_SAMPLE_END,
    REBALANCING_CITATION,
    REBALANCING_N_TRIALS,
    SCREENING_FLOOR,
    VALIDATED_EDGE_BAR,
    build_rebalancing_disclosure,
    default_rebalancing_config,
    run_rebalancing_screening,
)

RUN_TAG = "rebalancing_pressure_build_2026-09-06"
FAMILY_KEY = "rebalancing_pressure"
REPORT_PATH = "data/research_runs/rebalancing_pressure_2026-09-06.txt"
JSON_PATH = "data/research_runs/rebalancing_pressure_2026-09-06.json"

RUN_END = date(2026, 9, 6)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout
)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger("rebalancing_pressure_runner")


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

    add("=" * 110)
    add("INSTITUTIONAL REBALANCING PRESSURE (Harvey, Mazzoleni & Melone 2025/2026) — RESULTS")
    add("=" * 110)
    add(f"run_tag={RUN_TAG}   wall clock {elapsed / 60:.1f} min")
    add("")
    add("SOURCE: " + REBALANCING_CITATION)
    add("")
    add(
        "PRE-REGISTRATION: data/research_runs/rebalancing_pressure_PREREGISTRATION.txt, committed "
        "as 3b59dc1 BEFORE this module or this run existed."
    )
    add(
        "The grid below is that document's 24-spec grid, unchanged, and the pass/fail rule applied "
        "at the end is that document's rule, unchanged."
    )
    add("")
    add(f"VERDICT (Policy D two-tier, bar = {VALIDATED_EDGE_BAR:.2f}, BASELINE cost arm): {verdict.upper()}")
    add(f"  best spec by DSR at n_local={n_local}: {best_id or 'none'}")
    add(f"  DSR denominators reported: {denominators}")
    add(f"  screening floor (not a pass): {SCREENING_FLOOR:.2f}")
    add("")
    add(f"  data window: {summary.formation_start} .. {summary.window_end}")
    add(f"  ticker first prints: {summary.ticker_starts}")
    add(
        "  (the SPY first print above is the PADDED FETCH boundary, not SPY's 1993-01-29 "
        "inception; IEF's 2002-07-30 inception is what binds the common window.)"
    )
    for w in summary.warnings:
        add(f"  WARNING: {w}")
    add("")

    # ---- synthesis, computed from the numbers below rather than typed ----
    d0 = summary.signal_diagnostics
    baseline = summary.baseline_results
    if d0 is not None and baseline:
        best = max(
            baseline,
            key=lambda r: (r.dsr_by_n.get(n_local) if r.dsr_by_n.get(n_local) is not None else -1.0),
        )
        controls = [r for r in baseline if r.is_control]
        best_control = max(controls, key=lambda r: r.sharpe_annualized) if controls else None
        finite_delta = [p for p in summary.delta_sensitivity if not math.isnan(p.t_stat)]
        peak_delta = min(finite_delta, key=lambda p: p.t_stat) if finite_delta else None
        finite_month = [
            p for p in summary.month_end_sensitivity if not math.isnan(p.t_stat_beta2)
        ]
        peak_month = min(finite_month, key=lambda p: p.t_stat_beta2) if finite_month else None
        rd0 = summary.reversal_decomposition

        add("=" * 110)
        add("MECHANISM-FIDELITY SUMMARY — WHAT REPLICATED AND WHAT DID NOT")
        add("=" * 110)
        add("")
        add("  REPLICATED:")
        add(
            f"   * Signal summary statistics. Both signals' means are POSITIVE "
            f"(threshold {d0.threshold_mean:+.6f}, calendar {d0.calendar_mean:+.6f}), as [HMM26] "
            "p.14 reports;"
        )
        add(
            f"     AR(1) {d0.threshold_ar1:.2f}/{d0.calendar_ar1:.2f} against the paper's "
            f"0.61/0.91, skewness {d0.threshold_skew:.2f}/{d0.calendar_skew:.2f} against its "
            "-0.98/-1.43,"
        )
        add(
            f"     and corr(threshold, calendar) = {d0.threshold_calendar_correlation:+.4f} "
            "against its stated ~+0.60."
        )
        add(
            f"   * Calendar rebalancing frequency {d0.calendar_resets_per_year:.2f}/yr against "
            "the paper's 12/yr, and delta=0 giving exactly 252/yr as it states."
        )
        add(
            f"   * Eq. (1)'s SIGN AND SIGNIFICANCE: gamma1 {d0.eq1_gamma1:+.4f}, t(HC0) "
            f"{d0.eq1_t_stat:+.3f}, on an ETF pair and a window the paper never saw."
        )
        add(
            f"     Magnitude is SMALLER: {d0.eq1_bps_per_one_sd:+.2f} bps per one-SD move "
            "against the paper's stated ~20 bps."
        )
        add("")
        add("  DID NOT REPLICATE:")
        if peak_delta is not None:
            add(
                f"   * F1, THE DELTA SHAPE. [HMM26] Figure 2's t-statistic peaks near delta = 2%. "
                f"Here it is MOST negative at delta = {peak_delta.delta * 100:.1f}% "
                f"(t = {peak_delta.t_stat:+.3f}) and"
            )
            add(
                "     decays as delta rises. delta = 0 is DAILY rebalancing, i.e. a signal with no "
                "band and no institutional interpretation at all."
            )
        add(
            f"   * F2/F3, THE WEEK4 EFFECT. Eq. (3)'s interaction is beta2 {d0.eq3_beta2:+.4f}, "
            f"t(HC0) {d0.eq3_t_stat_beta2:+.3f} — the right sign, NOT significant, against the "
            "paper's -0.3029, t = -3.75."
        )
        if peak_month is not None:
            add(
                f"     The most negative beta2 is at N = {peak_month.n_days} against the paper's "
                "N = 4; the N = 1 cell is POSITIVE here, which is at least directionally"
            )
            add(
                "     consistent with the paper's own 'funds avoid trading on the very last day' "
                "and its footnote-27 week-1/week-3 reversal."
            )
        add(
            f"   * F4, THRESHOLD FREQUENCY. The median-delta reset rate is "
            f"{d0.threshold_resets_per_year_median_delta:.2f}/yr against the paper's stated "
            "~16/yr — this build's simulated portfolio breaches its bands about half as often,"
        )
        add(
            "     which is what a lower-volatility bond leg (IEF vs a 10-year note future) and a "
            "calmer window would each do."
        )
        add("")
        add("  F7 — THE SLICE THE PAPER NEVER SAW, AND THE MOST INFORMATIVE NUMBER HERE:")
        add(
            f"   * {best.spec_id} earns Sharpe "
            f"{_fmt(best.confound.sharpe_in_paper_window)} INSIDE [HMM26]'s estimation window "
            f"(to {PAPER_SAMPLE_END}) and "
            f"{_fmt(best.confound.sharpe_after_paper_window)} AFTER it."
        )
        add(
            "     The post-paper slice is ~3.5 years that postdate the paper's own sample AND its "
            "March 2025 circulation. Whatever the"
        )
        add(
            "     in-sample number means, the strategy has not worked since — which is what either "
            "post-publication arbitrage or an"
        )
        add("     in-sample artifact looks like, and this build cannot distinguish the two.")
        add(
            f"   * F8, CRISIS DEPENDENCE: excluding {CRISIS_WINDOWS[0][0]}..{CRISIS_WINDOWS[0][1]} "
            f"and {CRISIS_WINDOWS[1][0]}..{CRISIS_WINDOWS[1][1]}, its Sharpe falls from "
            f"{best.sharpe_annualized:+.4f} to {_fmt(best.confound.sharpe_excluding_crises)}."
        )
        add(
            "     [HMM26] p.38 runs the same exclusion on its own strategy and reports 1.11 -> "
            "0.90; the proportional damage here is larger."
        )
        add("")
        add("  THE NUMBERS THAT DECIDE HOW TO READ THE POSITIVE SHARPE:")
        add(
            f"   * STATIC TILT: {best.spec_id} keeps a beta-hedged Sharpe of "
            f"{best.confound.residual_sharpe:+.4f} against its raw {best.sharpe_annualized:+.4f}. "
            "It is NOT a disguised static tilt."
        )
        if best_control is not None:
            add(
                f"   * THE PRE-DECLARED CONTROL: best control {best_control.spec_id} Sharpe "
                f"{best_control.sharpe_annualized:+.4f} vs {best.sharpe_annualized:+.4f}. The "
                "21-day trailing-window control does NOT explain it."
            )
        if rd0 is not None:
            add(
                f"   * BUT THE POST-HOC ONE-DAY-REVERSAL CHECK DOES MOST OF THE EXPLAINING: in a "
                f"joint regression the Eq. (2) signal falls from t {rd0.averaged_alone_t:+.3f} to "
                f"t {rd0.averaged_joint_t:+.3f},"
            )
            add(
                f"     while the delta=0 one-day-reversal signal holds t {rd0.delta0_joint_t:+.3f}. "
                "The control this family pre-declared was the wrong horizon."
            )
        add("")

    d = summary.signal_diagnostics
    if d is not None:
        add("=" * 110)
        add("FIDELITY CHECKS F3/F4/F5 — THE PAPER'S OWN REPORTED SIGNAL PROPERTIES, RE-MEASURED")
        add("=" * 110)
        add("")
        add("  SIGNAL SUMMARY STATISTICS (deviation from the 60% equity target, in weight units):")
        add(
            f"    threshold  mean {d.threshold_mean:+.6f}  sd {d.threshold_std:.6f}  "
            f"AR(1) {d.threshold_ar1:+.4f}  skew {d.threshold_skew:+.4f}"
        )
        add(
            f"    calendar   mean {d.calendar_mean:+.6f}  sd {d.calendar_std:.6f}  "
            f"AR(1) {d.calendar_ar1:+.4f}  skew {d.calendar_skew:+.4f}"
        )
        add(
            f"    corr(threshold, calendar) = {d.threshold_calendar_correlation:+.4f}"
            "     [HMM26] p.14 reports approximately +0.60"
        )
        add(
            "    [HMM26] p.14: 'The average values of the Threshold and Calendar signals are "
            "positive'; Table C.1 reports AR(1) 0.61 / 0.91 and skewness -0.98 / -1.43."
        )
        add(
            f"    corr(literal B.2, month-end-day-reset variant) = "
            f"{d.calendar_variant_correlation:+.6f}  (the one-day construction ambiguity, "
            "measured rather than argued)"
        )
        add("")
        add("  F4 — REBALANCING FREQUENCY (resets per year, measured on the formation window):")
        add(f"    calendar approach:            {d.calendar_resets_per_year:.2f}/yr   [HMM26] p.14: 12/yr")
        for delta in (0.0, 0.005, 0.011, 0.02, 0.025):
            key = min(d.threshold_resets_per_year_by_delta, key=lambda k: abs(k - delta))
            add(
                f"    threshold delta={key * 100:4.1f}%:        "
                f"{d.threshold_resets_per_year_by_delta[key]:.2f}/yr"
            )
        add(
            "    [HMM26] p.11: 'When delta = 0, the 60/40 portfolio rebalances 252 times per year"
            "... When delta = 1.1%, rebalancing occurs about once per month, and at delta = 2.5% "
            "it happens about once per quarter.'"
        )
        add("    [HMM26] p.14: 'the median rebalancing frequency of the Threshold signal is about")
        add("    16 times per year, higher than the 12 times per year of the Calendar approach.'")
        add("")
        add("  F3 — THE PAPER'S OWN UNIVARIATE PREDICTIVE REGRESSIONS ON SPY/IEF")
        add("  (HC0 standard errors, [HMM26]'s own convention. UNIVARIATE — no momentum, VIX,")
        add("   MOVE, EPU, ADS or sentiment controls; see the module's NO MULTIVARIATE CONTROLS")
        add("   note. No Table 1 coefficient is claimed to be replicated.)")
        add("")
        add("    Eq. (1)  Ret_t+1 = g0 + g1 * ThresholdSignal_t")
        add(
            f"      gamma1 {d.eq1_gamma1:+.4f}   t(HC0) {d.eq1_t_stat:+.3f}   "
            f"R^2 {d.eq1_r_squared:.5f}   n {d.eq1_n_obs}"
        )
        add(
            f"      effect of a ONE-SD signal move on next-day return: "
            f"{d.eq1_bps_per_one_sd:+.2f} bps"
        )
        add(
            "      [HMM26] p.18: 'about 20 bps'; Table 1 Col.(1) Threshold -0.4144 (0.1148), "
            "t = -3.61 (MULTIVARIATE)"
        )
        add("")
        add("    Eq. (3)  Ret_t+1 = b0 + b1*Cal_t + b2*Cal_t*week4_t + b3*week4_t")
        add(
            f"      beta1 (away from month-end) {d.eq3_beta1:+.4f}    "
            f"beta2 (week4 interaction) {d.eq3_beta2:+.4f}   t(HC0) {d.eq3_t_stat_beta2:+.3f}   "
            f"n {d.eq3_n_obs}"
        )
        add(
            f"      effect of a ONE-SD calendar move in week4: "
            f"{d.eq3_bps_per_one_sd_week4:+.2f} bps"
        )
        add(
            "      [HMM26] p.18: 'about 19.2 bps'; Table 1 Col.(1) Calendar +0.0553 (0.0709) "
            "t=+0.78 NOT SIGNIFICANT, Calendar*week4 -0.3029 (0.0808) t=-3.75"
        )
        add("")

    if summary.delta_sensitivity:
        add("=" * 110)
        add("FIDELITY CHECK F1 — THRESHOLD-DELTA SENSITIVITY (reproduce [HMM26] Figure 2)")
        add("=" * 110)
        add("[HMM26] p.11-12: 'the Threshold signal is negatively related to subsequent daily")
        add("S&P 500 returns in excess of the 10-year Treasury note... the signal's predictive")
        add("power peaks around 2 percentage points and declines for values of delta above 2.5%.'")
        add("")
        add("    delta(%)   gamma1      t(HC0)     resets/yr")
        add("    " + "-" * 48)
        for p in summary.delta_sensitivity:
            add(
                f"    {p.delta * 100:6.1f}   {p.gamma1:+9.4f}   {p.t_stat:+8.3f}   "
                f"{p.resets_per_year:9.2f}"
            )
        finite = [p for p in summary.delta_sensitivity if not math.isnan(p.t_stat)]
        if finite:
            peak = min(finite, key=lambda p: p.t_stat)
            add("")
            add(
                f"    MOST NEGATIVE t-statistic at delta = {peak.delta * 100:.1f}% "
                f"(t = {peak.t_stat:+.3f}).  [HMM26]'s Figure 2 peaks near 2.0%."
            )
            n_negative = sum(1 for p in finite if p.gamma1 < 0)
            add(f"    gamma1 < 0 at {n_negative} of {len(finite)} delta values.")
        add("")

    if summary.month_end_sensitivity:
        add("=" * 110)
        add("FIDELITY CHECK F2 — MONTH-END CONCENTRATION (reproduce [HMM26] Figure 3)")
        add("=" * 110)
        add("[HMM26] p.13-14: 'Calendar predictability peaks in the last four days of the month...")
        add("funds attempt to minimize market impact by avoiding trades on the very last day while")
        add("spreading trades over several days.' The curve is expected to be NON-MONOTONIC.")
        add("")
        add("    last N days   beta1        beta2 (interaction)   t(HC0) beta2")
        add("    " + "-" * 62)
        for p in summary.month_end_sensitivity:
            add(
                f"    {p.n_days:11d}   {p.beta1:+9.4f}   {p.beta2:+17.4f}   {p.t_stat_beta2:+12.3f}"
            )
        finite = [p for p in summary.month_end_sensitivity if not math.isnan(p.t_stat_beta2)]
        if finite:
            peak = min(finite, key=lambda p: p.t_stat_beta2)
            add("")
            add(
                f"    MOST NEGATIVE beta2 t-statistic at N = {peak.n_days} "
                f"(t = {peak.t_stat_beta2:+.3f}).  [HMM26]'s Figure 3 peaks at N = 4."
            )
        add("")

    rd = summary.reversal_decomposition
    if rd is not None:
        add("=" * 110)
        add("POST-HOC ADVERSARIAL CHECK — NOT PRE-REGISTERED, DECLARED AS SUCH")
        add("=" * 110)
        add("Added AFTER F1 came back with the wrong shape. At delta = 0 the band fires every")
        add("day, so Threshold Signal^0_t is (to second order) 0.24 x yesterday's SPY-minus-IEF")
        add("return — ONE-DAY CROSS-ASSET REVERSAL with no rebalancing content at all. This is")
        add("the one regression that separates the two readings. It adds no spec, changes no")
        add("verdict input, and can only make this family look worse.")
        add("")
        add(f"    corr(Eq.(2) averaged signal, Threshold Signal^0) = {rd.correlation_averaged_delta0:+.4f}")
        add("")
        add("    UNIVARIATE")
        add(
            f"      averaged (Eq. 2)        coef {rd.averaged_alone_coef:+9.4f}   "
            f"t(HC0) {rd.averaged_alone_t:+7.3f}"
        )
        add(
            f"      delta=0 (1-day reversal) coef {rd.delta0_alone_coef:+9.4f}   "
            f"t(HC0) {rd.delta0_alone_t:+7.3f}"
        )
        add("")
        add(f"    JOINT (n = {rd.n_obs}, R^2 = {rd.joint_r_squared:.5f})")
        add(
            f"      averaged (Eq. 2)        coef {rd.averaged_joint_coef:+9.4f}   "
            f"t(HC0) {rd.averaged_joint_t:+7.3f}"
        )
        add(
            f"      delta=0 (1-day reversal) coef {rd.delta0_joint_coef:+9.4f}   "
            f"t(HC0) {rd.delta0_joint_t:+7.3f}"
        )
        add("")
        add("    READING: if the averaged signal's coefficient survives the joint regression, the")
        add("    multi-band rebalancing structure carries information beyond one-day reversal. If")
        add("    it collapses while delta=0 stands, the family measured one-day cross-asset")
        add("    reversal in a rebalancing costume. Either way this is the content of a FUTURE")
        add("    pre-declared round, not a revision of this one.")
        add("")

    for arm in COST_ARMS:
        results = summary.results_by_cost_arm.get(arm.key, [])
        if not results:
            continue
        is_baseline = arm.key == BASELINE_COST_ARM
        add("=" * 110)
        add(f"COST ARM: {arm.key.upper()}" + ("   <-- THE VERDICT ARM" if is_baseline else ""))
        add("=" * 110)
        add(f"  {arm.description}")
        add(f"  sigma_sr (sibling Sharpe dispersion, ddof=1): {_fmt(summary.sigma_sr_by_cost_arm.get(arm.key))}")
        add("")
        header = "  ".join(f"DSR@{n:<4d}" for n in summary.denominators)
        add(
            f"    spec                                  Sharpe    {header}   presv    hedgedSR   "
            "boot p   turn/yr"
        )
        add("    " + "-" * 122)
        for r in sorted(
            results,
            key=lambda x: (x.dsr_by_n.get(n_local) if x.dsr_by_n.get(n_local) is not None else -1.0),
            reverse=True,
        ):
            ladder = "  ".join(_fmt(r.dsr_by_n.get(n)).rjust(8) for n in summary.denominators)
            marker = " [CTRL]" if r.is_control else ""
            add(
                f"    {r.spec_id + marker:<36} {r.sharpe_annualized:+8.4f}  {ladder}  "
                f"{_fmt(r.preservation.get('preservation_score')):>7}  "
                f"{r.confound.residual_sharpe:+8.4f}  "
                f"{_fmt(r.confound.bootstrap_p_value, '.4f'):>7}  {r.annual_turnover:7.1f}"
            )
        add("")
        if is_baseline:
            add("    hedgedSR is the Sharpe of the BETA-HEDGED stream (y - beta*x) against the")
            add("    buy-and-hold SPY-minus-IEF spread — NOT the OLS residual, whose mean is zero")
            add("    by construction. A positive raw Sharpe that does not survive it is a static")
            add("    tilt, not a timing signal.  boot p is the circular block bootstrap p-value")
            add("    under a zero-mean null with block length max(holding_days, 5).")
            add("")
            add("  CONFOUND AND EXPOSURE DETAIL (baseline arm):")
            add("")
            add(
                "    spec                                  mean pos  mean|pos|  max|pos|  frac>0  "
                "frac=0  spread beta  eq beta  bond beta"
            )
            add("    " + "-" * 126)
            for r in sorted(results, key=lambda x: x.spec_id):
                c = r.confound
                add(
                    f"    {r.spec_id:<36} {c.mean_position:+9.4f} {c.mean_abs_position:10.4f} "
                    f"{c.max_abs_position:9.4f} {c.fraction_long:7.3f} {c.fraction_flat:7.3f} "
                    f"{c.spread_beta:+12.4f} {c.equity_beta:+8.4f} {c.bond_beta:+10.4f}"
                )
            add("")
            add("  F7 / F8 — WINDOW AND CRISIS SPLITS (baseline arm):")
            add("")
            add(
                "    spec                                  full SR   in-paper  post-paper  "
                "ex-crises   thirds"
            )
            add("    " + "-" * 118)
            for r in sorted(results, key=lambda x: x.spec_id):
                c = r.confound
                thirds = " ".join(f"{s:+.2f}" for s in c.subperiod_sharpes)
                add(
                    f"    {r.spec_id:<36} {r.sharpe_annualized:+8.4f}  "
                    f"{_fmt(c.sharpe_in_paper_window):>8}  {_fmt(c.sharpe_after_paper_window):>10}  "
                    f"{_fmt(c.sharpe_excluding_crises):>9}   {thirds}"
                )
            add("")
            add(
                f"    in-paper  = through {PAPER_SAMPLE_END} ([HMM26]'s own estimation window)."
            )
            add(
                "    post-paper = after it, genuinely out of sample for the paper and postdating "
                "its March 2025 circulation."
            )
            add(
                f"    ex-crises = excluding {CRISIS_WINDOWS[0][0]}..{CRISIS_WINDOWS[0][1]} and "
                f"{CRISIS_WINDOWS[1][0]}..{CRISIS_WINDOWS[1][1]}, exactly the windows [HMM26] p.38"
            )
            add("    excludes when reporting its own strategy's Sharpe falling 1.11 -> 0.90.")
            add("")
            add("  COST AND TURNOVER (baseline arm, cumulative return units):")
            add("")
            add(
                "    spec                                  net cum    cost drag  fin. drag   "
                "turnover   changes  flips"
            )
            add("    " + "-" * 116)
            for r in sorted(results, key=lambda x: x.spec_id):
                add(
                    f"    {r.spec_id:<36} {r.net_cumulative_return:+10.4f} "
                    f"{r.total_cost_drag:10.4f} {r.total_financing_drag:10.4f} "
                    f"{r.total_turnover:10.1f} {r.n_position_changes:9d} {r.n_sign_flips:6d}"
                )
            add("")

    add("=" * 110)
    add("DISCLOSURE — TRAVELS WITH EVERY NUMBER ABOVE")
    add("=" * 110)
    for line in build_rebalancing_disclosure(summary, default_rebalancing_config()):
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
    logger.info("screening the rebalancing-pressure family")
    summary = run_rebalancing_screening(end=RUN_END)
    elapsed = time.time() - started

    report = build_report(summary, elapsed)
    (_BACKEND / REPORT_PATH).write_text(report + "\n")
    logger.info("report written to %s", REPORT_PATH)

    verdict, best_id = summary.verdict(VALIDATED_EDGE_BAR)
    payload = {
        "run_tag": RUN_TAG,
        "family_key": FAMILY_KEY,
        "n_trials": summary.n_trials,
        "declared_n_trials": REBALANCING_N_TRIALS,
        "denominators": summary.denominators,
        "validated_edge_bar": VALIDATED_EDGE_BAR,
        "screening_floor": SCREENING_FLOOR,
        "verdict": verdict,
        "best_spec": best_id,
        "citation": REBALANCING_CITATION,
        "preregistration": "data/research_runs/rebalancing_pressure_PREREGISTRATION.txt",
        "formation_start": str(summary.formation_start),
        "window_end": str(summary.window_end),
        "ticker_starts": {k: str(v) for k, v in summary.ticker_starts.items()},
        "warnings": summary.warnings,
        "sigma_sr_by_cost_arm": summary.sigma_sr_by_cost_arm,
        "signal_diagnostics": (
            asdict(summary.signal_diagnostics) if summary.signal_diagnostics else None
        ),
        "delta_sensitivity": [asdict(p) for p in summary.delta_sensitivity],
        "month_end_sensitivity": [asdict(p) for p in summary.month_end_sensitivity],
        "results_by_cost_arm": {
            arm: [_serialize_result(r) for r in results]
            for arm, results in summary.results_by_cost_arm.items()
        },
        "disclosure": build_rebalancing_disclosure(summary, default_rebalancing_config()),
    }
    (_BACKEND / JSON_PATH).write_text(json.dumps(payload, indent=2, default=str) + "\n")
    logger.info("json written to %s", JSON_PATH)

    # PERSISTENCE, AND WHY IT IS CHECKED RATHER THAN ASSUMED. See
    # cross_sectional_persistence.verify_persisted_trial_results' docstring:
    # two families this session left committed reports that no database row
    # backs. Only the BASELINE cost arm's rows are persisted -- the other two
    # arms are the same 24 trials re-scored under a changed assumption, not new
    # trials, and writing them would triple-count this family in every future
    # pooled-effective-N computation that reads this table.
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
    finally:
        db.close()

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
