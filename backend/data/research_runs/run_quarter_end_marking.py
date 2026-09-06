"""Production runner for the period-end marking-the-close family.

Calls the module's OWN entry point (run_qem_screening) — not a
reimplementation, not a shortcut — then persists every per-spec result to the
shared cross_sectional_trial_results table and writes the git-durable
plain-text and JSON run reports.

Checked into data/research_runs/ alongside the pre-registration and the report
so the exact invocation that produced the numbers is reproducible from the repo
rather than living only in a scratchpad. Run from backend/ with
./venv/bin/python data/research_runs/run_quarter_end_marking.py

Needs only the point-in-time price store and the two membership modules; no
filings, no vendor feed.
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

# WORKTREE BINDING GUARD — load-bearing, not boilerplate. Running this file by
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
from app.services.research_lab.cross_sectional_quarter_end_marking import (
    QEM_CITATION,
    QEM_FAMILY,
    SCREENING_FLOOR,
    VALIDATED_EDGE_BAR,
    run_qem_screening,
)

RUN_TAG = "quarter_end_marking_build_2026-09-06"
REPORT_PATH = "data/research_runs/quarter_end_marking_2026-09-06.txt"
JSON_PATH = "data/research_runs/quarter_end_marking_2026-09-06.json"

# One family_key per universe, following the convention already in the table
# for the other two-universe families here (small_cap_disposition /
# small_cap_ivol / small_cap_tax_loss_selling_turn_of_year beside their S&P 500
# originals). The pattern_ids are identical across universes by design — they
# are the SAME 18 definitions — so a shared family_key would collide.
FAMILY_KEY_BY_UNIVERSE = {
    "sp500": QEM_FAMILY,
    "sp600": f"small_cap_{QEM_FAMILY}",
}

RUN_END = date(2026, 9, 5)
WINDOWS = {
    # sp500: sp500_membership_history.MEMBERSHIP_DATA_START
    "sp500": (date(2015, 1, 7), RUN_END),
    # sp600: small_cap_membership_history.MEMBERSHIP_DATA_START
    "sp600": (date(2020, 1, 1), RUN_END),
}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout
)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger("quarter_end_marking_runner")

DUMMY_ORDER = ("const", "YEND", "YBEG", "QEND", "QBEG", "MEND", "MBEG")


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
    verdict, best = summary.verdict(VALIDATED_EDGE_BAR)
    placebo_triggered, placebo_detail = summary.placebo_override_triggered()
    n_local = summary.n_trials
    denominators = summary.denominators

    add("=" * 100)
    add("PERIOD-END 'MARKING THE CLOSE' (Carhart, Kaniel, Musto & Reed 1999) — RESULTS")
    add("=" * 100)
    add(f"run_tag={RUN_TAG}   wall clock {elapsed / 60:.1f} min")
    add("")
    add("SOURCE: " + QEM_CITATION)
    add("")
    add(
        "PRE-REGISTRATION: data/research_runs/quarter_end_marking_PREREGISTRATION.txt, committed "
        "as bca1314 BEFORE this run existed."
    )
    add(
        "The grid below is that document's grid, unchanged, and the pass/fail rule applied at the "
        "end is that document's rule, unchanged."
    )
    add("")
    add(f"VERDICT (Policy D two-tier, bar = {VALIDATED_EDGE_BAR:.2f}, BASELINE cost arm): {verdict.upper()}")
    add(f"  best spec at n_local={n_local}: {best or 'none'}")
    add(f"  DSR denominators reported: {denominators}")
    add("")
    add("  BINDING OVERRIDE (i), the placebo override (pre-registration section 6):")
    add(f"    TRIGGERED: {placebo_triggered}")
    add(f"    {placebo_detail}")
    add(
        "    If TRIGGERED, the family is a NEGATIVE ON MECHANISM GROUNDS whatever the real arms' "
        "DSR — the"
    )
    add(
        "    month-end placebo is [CKMR99]'s own control (p.9: 'There is no evidence of the price "
        "shifts for"
    )
    add("    month-ends that aren't quarter-ends') and it has ~8x the events of the year-end arm.")
    add("")
    add("  BINDING OVERRIDE (ii), the pre-weighted quarter-end asymmetry (section 6):")
    add(
        "    [CKMR99] Table I gives QEND p=1.82% but QBEG p=12.69%, and p.9 says the QBEG p-values"
    )
    add(
        "    'generally exceed the usual rejection levels'. Any strong quarter_end/day1 result is"
    )
    add("    SURPRISING RELATIVE TO THE SOURCE and is reported as such, not as confirmation.")
    add("")

    for universe in summary.universes:
        add("=" * 100)
        add(f"UNIVERSE: {universe.universe.upper()}")
        add("=" * 100)
        add(
            f"  point-in-time candidate pool {universe.universe_size} tickers; "
            f"{len(universe.missing_price_data)} resolved no price data at all"
        )
        add(
            f"  formations {universe.formation_start.isoformat()} .. "
            f"{universe.window_end.isoformat()}"
        )
        add(f"  cost_model={universe.cost_model}  cost_bps={universe.cost_bps}")
        add(
            f"  financing_bps_per_year={universe.financing_bps_per_year} (gross-notional basis; "
            "under 0.01bp on a one-day hold — charged, not load-bearing)"
        )
        if universe.half_spread_calibration:
            add(f"  half-spread basis: {universe.half_spread_calibration}")
        add(f"  sigma_sr (sibling Sharpe dispersion, ddof=1): {_fmt(universe.sigma_sr)}")
        add("")
        add(
            "  EVENT CALENDAR (the panel's, over the PADDED price window — events before "
            "formation_start above are"
        )
        add(
            "  in the calendar but were never traded, which is why a spec's per-event n can be "
            "smaller than this count):"
        )
        for period, dates in universe.events_by_period.items():
            add(f"  {period:<14} {len(dates):>3} events   {', '.join(dates)}")
            if universe.skipped_months.get(period):
                add(f"                 skipped months: {universe.skipped_months[period]}")
        add("")

        add("  RESULTS — all 18 specs, sorted by DSR at n_local (BASELINE cost arm):")
        add("")
        header = "  ".join(f"DSR@{n:<4d}" for n in denominators)
        add(
            f"    spec                                  Sharpe     {header}  "
            "presv    evt.mean   evt.t   hit    n"
        )
        add("    " + "-" * 118)
        for e in sorted(
            universe.evaluations,
            key=lambda x: (x.dsr_by_n.get(n_local) if x.dsr_by_n.get(n_local) is not None else -1.0),
            reverse=True,
        ):
            ladder = "  ".join(_fmt(e.dsr_by_n.get(n)).rjust(8) for n in denominators)
            add(
                f"    {e.pattern_id:<36} {e.sharpe_annualized:+8.4f}  {ladder}  "
                f"{_fmt(e.preservation.get('preservation_score')):>6}  {e.events.mean:+9.5f}  "
                f"{_fmt(e.events.naive_t, '.2f'):>6}  {e.events.hit_rate:4.2f}  "
                f"{e.events.n_events:3d}"
            )
        add("")
        add(
            "    evt.mean / evt.t / hit / n are the PER-EVENT statistics: each event's own "
            "ENTRY-TO-EXIT window"
        )
        add(
            "    compounded into one number, then mean / (mean/std)*sqrt(n) / fraction positive / "
            "count. The window is"
        )
        add(
            "    day0 -> [d(0), d(1)];  day1 -> [d(1), d(2)];  oval -> [d(0), d(1), d(2)] — one "
            "session longer than the"
        )
        add(
            "    exposure in every case, because the harness charges a formation's turnover on its "
            "FIRST REALIZATION"
        )
        add(
            "    DAY, so the LIQUIDATION charge lands the session after the book goes flat. On that "
            "session the book is"
        )
        add(
            "    flat, so its daily return is exactly minus that charge. n IS the effective "
            "independent sample; the"
        )
        add(
            "    Sharpe and DSR columns rest on ~2,900 daily observations of which all but ~n*2..3 "
            "are exact zeros."
        )
        add("    See pre-registration sections 7 and 9.")
        add("")

        add("  PER-EVENT RETURNS (the real book — sleeve_scale is 1, nothing is rescaled):")
        for e in sorted(universe.evaluations, key=lambda x: x.pattern_id):
            add(
                f"    {e.pattern_id:<36} "
                + " ".join(f"{r:+.4f}" for r in e.events.event_returns)
            )
        add("")

        add("  COST AND TURNOVER (baseline arm):")
        add("")
        add(
            "    spec                                 sleeves   turnover   cost drag   financing   "
            "flat-fallback   names/leg"
        )
        add("    " + "-" * 116)
        for e in sorted(universe.evaluations, key=lambda x: x.pattern_id):
            add(
                f"    {e.pattern_id:<36} {e.sleeve_scale:5d}  {e.total_turnover:9.3f}  "
                f"{e.total_cost_drag:10.5f}  {e.total_financing_drag:10.6f}  "
                f"{e.edge_flat_fallback_notional:12.3f}  {e.avg_names_per_leg:10.1f}"
            )
        add("")

        add("  FIDELITY CHECK F1 — QUINTILE DOSE-RESPONSE (analogue of [CKMR99] Figures 2A-2C)")
        add(
            "    [CKMR99] pp.15-16, full cross-section, 1993/4-1997/8: WINNER quintile day0 +81bp, "
            "day1 -79bp, OVAL"
        )
        add(
            "    +160bp; LOSER quintile +250bp on BOTH days, OVAL ~0; VW index +25bp/day. "
            "Largest-cap quintile: winners"
        )
        add(
            "    +37bp then -144bp, OVAL +181bp. Smallest-cap: +109bp then +6bp, OVAL +103bp. "
            "'The in-between quintiles"
        )
        add("    are in between, in exact order' (p.15) — i.e. a MONOTONE profile is predicted.")
        for profile in universe.quintile_profiles:
            add("")
            add(f"    {profile.period} / {profile.perf}   ({profile.n_events} events)")
            if profile.n_events == 0:
                add(f"      {profile.note}")
                continue
            add(f"      {profile.note}")
            add(
                "      quintile:    "
                + "  ".join(f"{i:>8d}" for i in range(len(profile.oval_by_quintile)))
                + "      universe"
            )
            add(
                "      day0 (bp):   "
                + "  ".join(f"{v * 10000:+8.2f}" for v in profile.day0_by_quintile)
                + f"      {profile.universe_day0 * 10000:+8.2f}"
            )
            add(
                "      day1 (bp):   "
                + "  ".join(f"{v * 10000:+8.2f}" for v in profile.day1_by_quintile)
                + f"      {profile.universe_day1 * 10000:+8.2f}"
            )
            add(
                "      OVAL (bp):   "
                + "  ".join(f"{v * 10000:+8.2f}" for v in profile.oval_by_quintile)
                + f"      {(profile.universe_day0 - profile.universe_day1) * 10000:+8.2f}"
            )
            add(
                f"      Spearman(quintile rank, OVAL) = "
                f"{_fmt(profile.spearman_quintile_vs_oval)}   (bucket 0 = LOSERS, "
                f"{len(profile.oval_by_quintile) - 1} = WINNERS)"
            )
        add("")

        add("  FIDELITY CHECKS F2 / F3 — [CKMR99] TABLE I AND TABLE II ANALOGUES")
        for regression in universe.dummy_regressions:
            add("")
            add(f"    {regression.label}: {regression.dependent}")
            add(f"      {regression.note}")
            add(f"      n = {regression.n_observations}, coefficients in {regression.units}")
            if not regression.coefficients:
                add("      NOT ESTIMABLE on this window (too few usable observations)")
                continue
            names = [k for k in DUMMY_ORDER if k in regression.coefficients]
            names += [k for k in regression.coefficients if k not in DUMMY_ORDER]
            add("      term:   " + "  ".join(f"{k:>10s}" for k in names))
            add(
                "      coef:   "
                + "  ".join(f"{regression.coefficients[k]:+10.4f}" for k in names)
            )
            add(
                "      p (%):  "
                + "  ".join(f"{regression.p_values_pct[k]:10.2f}" for k in names)
            )
        add("")

        add("  PRE-DECLARED COST LADDER (no new trials — same grid, same denominator, new returns):")
        for arm in universe.cost_arms:
            add("")
            add(f"    {arm.key}: {arm.description}")
            add(
                f"      {'spec':<36} {'Sharpe':>9}   DSR@{n_local:<5} {'evt.mean':>10}"
            )
            for pid in sorted(arm.sharpe_by_pattern):
                dsr = arm.dsr_by_pattern.get(pid, {})
                add(
                    f"      {pid:<36} {arm.sharpe_by_pattern[pid]:+9.4f}   "
                    f"{_fmt(dsr.get(n_local)):>9}  "
                    f"{_fmt(arm.event_mean_by_pattern.get(pid), '+.5f'):>10}"
                )
        add("")
        for warning in universe.warnings:
            add(f"  WARNING: {warning}")
        add("")

    return "\n".join(lines)


def main() -> int:
    started = time.time()
    logger.info("screening quarter-end marking on %s", list(WINDOWS))
    summary = run_qem_screening(WINDOWS)
    elapsed = time.time() - started

    report = build_report(summary, elapsed)
    (_BACKEND / REPORT_PATH).write_text(report + "\n")
    logger.info("report written to %s", REPORT_PATH)

    verdict, best = summary.verdict(VALIDATED_EDGE_BAR)
    placebo_triggered, placebo_detail = summary.placebo_override_triggered()
    payload = {
        "run_tag": RUN_TAG,
        "n_trials": summary.n_trials,
        "denominators": summary.denominators,
        "validated_edge_bar": VALIDATED_EDGE_BAR,
        "screening_floor": SCREENING_FLOOR,
        "verdict": verdict,
        "best_spec": best,
        "placebo_override_triggered": placebo_triggered,
        "placebo_override_detail": placebo_detail,
        "citation": QEM_CITATION,
        "preregistration": "data/research_runs/quarter_end_marking_PREREGISTRATION.txt",
        "universes": [],
    }
    for universe in summary.universes:
        payload["universes"].append(
            {
                "universe": universe.universe,
                "family_key": FAMILY_KEY_BY_UNIVERSE[universe.universe],
                "universe_size": universe.universe_size,
                "n_missing_price_data": len(universe.missing_price_data),
                "missing_price_data": universe.missing_price_data,
                "formation_start": universe.formation_start.isoformat(),
                "window_end": universe.window_end.isoformat(),
                "cost_model": universe.cost_model,
                "cost_bps": universe.cost_bps,
                "financing_bps_per_year": universe.financing_bps_per_year,
                "half_spread_calibration": universe.half_spread_calibration,
                "sigma_sr": universe.sigma_sr,
                "events_by_period": universe.events_by_period,
                "skipped_months": universe.skipped_months,
                "coverage_by_event": universe.coverage_by_event,
                "quintile_profiles": [asdict(p) for p in universe.quintile_profiles],
                "dummy_regressions": [asdict(d) for d in universe.dummy_regressions],
                "warnings": universe.warnings,
                "evaluations": [
                    {
                        **{k: v for k, v in asdict(e).items() if k != "events"},
                        "events": asdict(e.events),
                    }
                    for e in universe.evaluations
                ],
                "cost_arms": [asdict(a) for a in universe.cost_arms],
            }
        )
    (_BACKEND / JSON_PATH).write_text(json.dumps(payload, indent=2, default=str) + "\n")
    logger.info("json written to %s", JSON_PATH)

    # PERSISTENCE, AND WHY IT IS CHECKED RATHER THAN ASSUMED. The N-PORT family
    # and the first tax-loss-selling run both left committed reports on disk
    # describing results no database row backed (a cwd-relative sqlite default,
    # since fixed, plus the worktree-local-database hazard). Both root causes
    # are fixed at the source, but a check that only holds because two other
    # things are working is not a check — so the read-back, the resolved-file
    # log line and the worktree-local warning all run here via the shared
    # helper.
    db = SessionLocal()
    try:
        written = 0
        for universe in summary.universes:
            written += persist_cross_sectional_trial_results(
                db,
                FAMILY_KEY_BY_UNIVERSE[universe.universe],
                universe.results,
                run_tag=RUN_TAG,
            )
        verify_persisted_trial_results(db, RUN_TAG, written)
    finally:
        db.close()

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
