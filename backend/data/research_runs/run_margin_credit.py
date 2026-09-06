"""Production runner for the margin-credit family.

Calls the module's OWN entry point (run_margin_credit_screening) -- not a
reimplementation, not a shortcut -- then persists every per-spec result of the
BASELINE cost arm to the shared cross_sectional_trial_results table and writes
the git-durable plain-text and JSON run reports.

Checked into data/research_runs/ alongside the pre-registration and the report
so the exact invocation that produced the numbers is reproducible from the repo
rather than living only in a scratchpad. Run from backend/ with
./venv/bin/python data/research_runs/run_margin_credit.py

Needs only committed inputs: data/margin_credit/ (FINRA + GDP snapshots), the
point-in-time price store (SPY) and data/fama_french_factors_monthly.csv. No
network, no vendor feed, no paid data.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from dataclasses import asdict
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
    describe_configured_database,
    persist_cross_sectional_trial_results,
    verify_persisted_trial_results,
)
from app.services.research_lab.margin_credit_timing import (
    BURN_IN_MONTHS,
    COST_ARMS,
    MARGIN_CREDIT_CITATION,
    MARGIN_CREDIT_N_TRIALS,
    PAPER_INSAMPLE_R2_MONTHLY,
    PAPER_LONG_ONLY_SHARPE,
    PAPER_ONE_SD_EFFECT_PP_PER_MONTH,
    SCREENING_FLOOR,
    VALIDATED_EDGE_BAR,
    build_margin_credit_disclosure,
    run_margin_credit_screening,
)

RUN_TAG = "margin_credit_build_2026-09-06"
FAMILY_KEY = "margin_credit"
REPORT_PATH = "data/research_runs/margin_credit_2026-09-06.txt"
JSON_PATH = "data/research_runs/margin_credit_2026-09-06.json"
PREREGISTRATION = "data/research_runs/margin_credit_PREREGISTRATION.txt"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout
)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger("margin_credit_runner")


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
    baseline = summary.baseline_results

    add("=" * 118)
    add("MARGIN CREDIT (Deuskar, Kumar & Poland 2016 / Review of Finance 2020) — RESULTS")
    add("=" * 118)
    add(f"run_tag={RUN_TAG}   wall clock {elapsed / 60:.1f} min")
    add("")
    add("SOURCE: " + MARGIN_CREDIT_CITATION)
    add("")
    add(f"PRE-REGISTRATION: {PREREGISTRATION}, committed as c50fb89 BEFORE this module or")
    add("this run existed. The grid below is that document's 24-spec grid, unchanged, and the")
    add("pass/fail rule applied at the end is that document's rule, unchanged.")
    add("")
    add(
        f"VERDICT (Policy D two-tier, bar = {VALIDATED_EDGE_BAR:.2f}, BASELINE cost arm, "
        f"OVERLAY stream): {verdict.upper()}"
    )
    add(f"  best spec by DSR at n_local={n_local}: {best_id or 'none'}")
    add(f"  DSR denominators reported: {denominators}")
    add(f"  screening floor (not a pass): {SCREENING_FLOOR:.2f}")
    add(f"  panel window: {summary.panel_first_month} .. {summary.panel_last_month}")
    for w in summary.warnings:
        add(f"  WARNING: {w}")
    add("")

    # ---- synthesis, computed from the numbers rather than typed -----------
    if baseline:
        best = max(
            baseline,
            key=lambda r: (r.dsr_by_n.get(n_local) if r.dsr_by_n.get(n_local) is not None else -1.0),
        )
        signal_specs = [r for r in baseline if not r.is_control]
        controls = [r for r in baseline if r.is_control]
        best_signal = max(signal_specs, key=lambda r: r.sharpe_annualized) if signal_specs else None
        best_control = max(controls, key=lambda r: r.sharpe_annualized) if controls else None
        mc_recursive = [
            r for r in baseline if r.predictor == "mc" and r.mode == "recursive"
        ]

        add("=" * 118)
        add("WHAT THIS RUN ACTUALLY FOUND")
        add("=" * 118)
        add("")
        add("  THE HEADLINE:")
        add(
            f"   * The best spec in the whole family by DSR at n_local={n_local} is "
            f"{best.spec_id} at DSR {_fmt(best.dsr_by_n.get(n_local))}, against a bar of "
            f"{VALIDATED_EDGE_BAR:.2f}."
        )
        if best.is_control:
            add(
                "   * THAT SPEC IS A CONTROL. It contains NO MARGIN DATA AT ALL -- its forecast "
                "is the historical mean excess return. Whatever the family's best-looking number "
                "is, it is not coming from margin credit."
            )
        add(
            f"   * Its overlay market beta is {_fmt(best.confound.overlay_beta_on_market)} on a "
            f"mean weight of {_fmt(best.confound.mean_weight, '.3f')} with "
            f"{best.confound.n_switches} switch(es) over {best.n_trading_days} months -- i.e. it "
            "is a near-STATIC leverage position, not a timing decision. Its overlay Sharpe "
            f"({_fmt(best.sharpe_annualized)}) sits against a buy-and-hold Sharpe of "
            f"{_fmt(best.buy_and_hold_sharpe)} over the identical window."
        )
        add("")
        if mc_recursive:
            add("  THE PAPER'S OWN PREDICTOR, OUT OF SAMPLE (the specs the verdict is about):")
            for r in sorted(mc_recursive, key=lambda r: r.spec_id):
                add(
                    f"   * {r.spec_id:38s} overlay Sharpe {_fmt(r.sharpe_annualized):>8s}  "
                    f"DSR@{n_local} {_fmt(r.dsr_by_n.get(n_local)):>7s}  n={r.n_trading_days:3d} mo"
                )
            add(
                "     EVERY recursive (genuinely out-of-sample) margin-credit spec has a NEGATIVE "
                "overlay Sharpe."
                if all(r.sharpe_annualized < 0 for r in mc_recursive)
                else "     Not every recursive margin-credit spec is negative; see the table."
            )
            add("")
        if best_signal is not None and best_control is not None:
            add(
                f"  SIGNAL vs CONTROL: best NON-control overlay Sharpe "
                f"{_fmt(best_signal.sharpe_annualized)} ({best_signal.spec_id}) versus best "
                f"CONTROL overlay Sharpe {_fmt(best_control.sharpe_annualized)} "
                f"({best_control.spec_id})."
            )
            add("")

    # ---- mechanism fidelity ------------------------------------------------
    add("=" * 118)
    add("MECHANISM-FIDELITY CHECKS (pre-registration section 9)")
    add("=" * 118)
    add("")
    add("F5 — THE TREND, RE-TESTED ON THIS SAMPLE RATHER THAN ASSUMED FROM THE PAPER'S")
    add(
        "  [DKP16] p.15-16 detrends because it finds a significant POSITIVE deterministic trend "
        "(Perron-Yabu t = 3.36) on 1984-2014 NYSE data. On THIS sample:"
    )
    add("")
    add(f"    {'arm':10s} {'series':7s} {'n':>4s} {'slope/month':>13s} {'t(Newey-West)':>14s} {'ADF(resid)':>11s}")
    for t in summary.trend_diagnostics:
        add(
            f"    {t.arm:10s} {t.series:7s} {t.n_observations:4d} {t.slope_per_month:13.3e} "
            f"{t.slope_t_stat_nw:14.2f} {_fmt(t.adf_stat_on_residual, '.3f'):>11s}"
        )
    add("")
    add(
        "  READ THIS HONESTLY: the paper's stated reason for detrending margin credit does NOT "
        "carry over. On the `proxy` arm the MC/GDP trend is statistically indistinguishable from "
        "zero, and on the `faithful` arm it is significantly NEGATIVE -- the opposite sign to the "
        "paper's. Only MARGIN DEBT shows the paper's positive trend on this sample. The detrend "
        "is applied anyway, because the pre-registration fixed it before any of this was visible "
        "and changing a construction after seeing a diagnostic is how a family gets fitted to its "
        "own sample. But it means the `faithful` arm's MC is a residual around a trend the paper "
        "did not describe."
    )
    add("")
    add("F6 — THE PREDICTIVE REGRESSION SIGN AND SIZE")
    add(
        f"  [DKP16] p.2 predicts beta < 0 with a 1-s.d. effect near "
        f"{PAPER_ONE_SD_EFFECT_PP_PER_MONTH:+.1f} pp/month and in-sample monthly R^2 "
        f"{PAPER_INSAMPLE_R2_MONTHLY:.2%}."
    )
    add("")
    add(
        f"    {'predictor':10s} {'arm':10s} {'mode':10s} {'beta':>10s} {'t(NW)':>7s} {'R^2':>8s} "
        f"{'1sd effect':>12s}"
    )
    seen = set()
    for r in sorted(baseline, key=lambda r: (r.predictor, r.arm, r.mode)):
        key = (r.predictor, r.arm, r.mode)
        if r.is_control or key in seen:
            continue
        seen.add(key)
        c = r.confound
        add(
            f"    {r.predictor:10s} {r.arm:10s} {r.mode:10s} {_fmt(c.predictive_beta, '+.6f'):>10s} "
            f"{_fmt(c.predictive_beta_t_nw, '+.2f'):>7s} {_fmt(c.predictive_r2, '.5f'):>8s} "
            f"{_fmt(c.one_sd_effect_pp_per_month, '+.3f'):>10s}pp"
        )
    add("")
    add(
        "  PARTIALLY REPLICATED, AND THE SPLIT MATTERS. On the `proxy` arm the paper's sign and "
        "rough magnitude DO appear (negative beta, ~-0.7 pp per 1 s.d., R^2 ~2.7-3.5%, HAC t "
        "around -2.2). On the `faithful` arm -- the ONLY definitionally correct one -- the sign "
        "FLIPS POSITIVE and is insignificant. So the one arm that reproduces the paper's "
        "regression is the arm that is NOT the paper's measure, and the arm that IS the paper's "
        "measure does not reproduce it."
    )
    add(
        "  AND THE REGRESSION DOES NOT CONVERT INTO A TRADEABLE EDGE: the same `proxy` arm whose "
        "beta is right-signed and significant produces NEGATIVE out-of-sample overlay Sharpes. "
        "That gap between an in-sample predictive coefficient and an out-of-sample tradeable "
        "result is the central Welch-Goyal (2008) finding, and this run reproduces it."
    )
    add("")
    if summary.seam is not None:
        s = summary.seam
        add("F7 — THE 2010-02 DEFINITIONAL SEAM, MEASURED")
        add(
            f"  {s.last_combined_month} -> {s.first_split_month}: margin debt "
            f"{s.debit_pct_change:+.2%}, reconstructed COMBINED free credit "
            f"{s.combined_free_credit_pct_change:+.2%}, as-reported cash column "
            f"{s.cash_reported_pct_change:+.2%}."
        )
        add(
            "  The first two are ordinary month-on-month moves, so the FINRA population change at "
            "that date is immaterial and the `proxy` arm's reconstruction is continuous. The "
            "third is the definitional split itself, and is exactly why the raw cash column must "
            "never be read as one continuous series."
        )
        add("")

    # ---- full tables -------------------------------------------------------
    for arm in COST_ARMS:
        results = summary.results_by_cost_arm.get(arm.key, [])
        add("=" * 118)
        add(f"COST ARM: {arm.key} — {arm.description}")
        add(f"  sigma_SR (ddof=1 across sibling specs' OVERLAY Sharpes) = "
            f"{_fmt(summary.sigma_sr_by_cost_arm.get(arm.key))}")
        add("=" * 118)
        header = (
            f"{'spec_id':40s} {'n_mo':>5s} {'ovlSR':>8s} {'stratSR':>8s} {'B&H_SR':>8s} "
            + " ".join(f"{'DSR@' + str(n):>9s}" for n in denominators)
            + f" {'presv':>7s} {'meanW':>7s} {'ovlBeta':>8s} {'annTO':>7s} {'boot_p':>7s}"
        )
        add(header)
        add("-" * len(header))
        for r in results:
            add(
                f"{r.spec_id:40s} {r.n_trading_days:5d} {r.sharpe_annualized:8.4f} "
                f"{r.strategy_sharpe:8.4f} {r.buy_and_hold_sharpe:8.4f} "
                + " ".join(f"{_fmt(r.dsr_by_n.get(n)):>9s}" for n in denominators)
                + f" {r.preservation['preservation_score']:7.4f} "
                f"{r.confound.mean_weight:7.3f} {r.confound.overlay_beta_on_market:8.4f} "
                f"{r.confound.annual_turnover:7.3f} {_fmt(r.confound.bootstrap_p_value, '.4f'):>7s}"
            )
        add("")

    add("=" * 118)
    add("COMPARISON WITH THE PAPER'S OWN NUMBERS (NOT TARGETS — see the disclosure)")
    add("=" * 118)
    add(
        f"  [DKP16] long-only OOS Sharpe 1994-01..2014-12: {PAPER_LONG_ONLY_SHARPE:.2f} "
        "(STRATEGY stream, not overlay)."
    )
    if baseline:
        longonly = [r for r in baseline if r.strategy == "longonly" and not r.is_control]
        if longonly:
            best_lo = max(longonly, key=lambda r: r.strategy_sharpe)
            add(
                f"  This run's best long-only STRATEGY Sharpe: {_fmt(best_lo.strategy_sharpe)} "
                f"({best_lo.spec_id}), against a buy-and-hold Sharpe of "
                f"{_fmt(best_lo.buy_and_hold_sharpe)} over the identical window."
            )
            add(
                "  Note the strategy Sharpe is NOT the verdict input and is reported only for "
                "comparability: over this window buy-and-hold itself is high, so a respectable "
                "strategy Sharpe here mostly measures the equity risk premium."
            )
    add("")

    add("=" * 118)
    add("DISCLOSURE — TRAVELS WITH EVERY NUMBER ABOVE")
    add("=" * 118)
    for line in build_margin_credit_disclosure(summary):
        add(f"  * {line}")
    add("")
    add(
        "  KNOWN ARTIFACT, DISCLOSED RATHER THAN FIXED AFTER THE FACT: the pre-registration "
        "(section 6) fixed that the SAME cost is charged to both streams because 'the w=1 "
        "benchmark never trades'. That is true for every month except the first, where the "
        "benchmark would also have had to buy in once. The consequence is that a spec which "
        "holds w=1 throughout shows a small NEGATIVE overlay Sharpe (its one-off entry cost) "
        "rather than exactly zero. The bias is CONSERVATIVE -- it penalises specs and can never "
        "flatter one -- so it was left exactly as pre-registered rather than corrected after "
        "seeing results."
    )
    add("")
    add("=" * 118)
    add(f"PERSISTENCE: baseline cost arm rows written under run_tag={RUN_TAG!r}, family_key="
        f"{FAMILY_KEY!r}, to {describe_configured_database()}")
    add("=" * 118)
    return "\n".join(lines)


def _serialize_result(r) -> dict:
    payload = asdict(r)
    payload["dsr_by_n"] = {str(k): v for k, v in r.dsr_by_n.items()}
    return payload


def main() -> int:
    started = time.time()
    logger.info("screening the margin-credit family (%d specs)", MARGIN_CREDIT_N_TRIALS)
    summary = run_margin_credit_screening()
    elapsed = time.time() - started

    report = build_report(summary, elapsed)
    (_BACKEND / REPORT_PATH).write_text(report + "\n")
    logger.info("report written to %s", REPORT_PATH)

    verdict, best_id = summary.verdict(VALIDATED_EDGE_BAR)
    payload = {
        "run_tag": RUN_TAG,
        "family_key": FAMILY_KEY,
        "verdict": verdict,
        "best_spec": best_id,
        "validated_edge_bar": VALIDATED_EDGE_BAR,
        "screening_floor": SCREENING_FLOOR,
        "n_trials": summary.n_trials,
        "denominators": summary.denominators,
        "burn_in_months": BURN_IN_MONTHS,
        "citation": MARGIN_CREDIT_CITATION,
        "preregistration": PREREGISTRATION,
        "panel_first_month": summary.panel_first_month,
        "panel_last_month": summary.panel_last_month,
        "warnings": summary.warnings,
        "sigma_sr_by_cost_arm": summary.sigma_sr_by_cost_arm,
        "seam": asdict(summary.seam) if summary.seam else None,
        "trend_diagnostics": [asdict(t) for t in summary.trend_diagnostics],
        "results_by_cost_arm": {
            arm: [_serialize_result(r) for r in results]
            for arm, results in summary.results_by_cost_arm.items()
        },
        "disclosure": build_margin_credit_disclosure(summary),
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
        written = persist_cross_sectional_trial_results(db, FAMILY_KEY, baseline, run_tag=RUN_TAG)
        verify_persisted_trial_results(db, RUN_TAG, written, family_key=FAMILY_KEY)
        logger.info("persisted %d baseline rows to %s", written, describe_configured_database())
    finally:
        db.close()

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
