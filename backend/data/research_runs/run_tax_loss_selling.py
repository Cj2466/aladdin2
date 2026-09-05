"""Production runner for the tax-loss-selling / turn-of-the-year family.

Calls the module's OWN entry point (run_tax_loss_screening) — not a
reimplementation, not a shortcut — then persists every per-spec result to the
shared cross_sectional_trial_results table and writes the git-durable
plain-text and JSON run reports.

Checked into data/research_runs/ alongside the pre-registration and the report
so the exact invocation that produced the numbers is reproducible from the
repo rather than living only in a scratchpad. Run from backend/ with
./venv/bin/python data/research_runs/run_tax_loss_selling.py

Needs only the point-in-time price store; no filings, no vendor feed.
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
)
from app.services.research_lab.cross_sectional_tax_loss_selling import (
    SCREENING_FLOOR,
    TAX_LOSS_CITATION,
    TAX_LOSS_FAMILY,
    VALIDATED_EDGE_BAR,
    run_tax_loss_screening,
)

RUN_TAG = "tax_loss_selling_build_2026-09-06"
REPORT_PATH = "data/research_runs/tax_loss_selling_2026-09-06.txt"
JSON_PATH = "data/research_runs/tax_loss_selling_2026-09-06.json"

# One family_key per universe, following the convention already in the table
# for the only other two-universe family here (small_cap_disposition /
# small_cap_ivol beside their S&P 500 originals). The pattern_ids are
# identical across universes by design — they are the SAME 16 definitions —
# so a shared family_key would collide.
FAMILY_KEY_BY_UNIVERSE = {
    "sp500": TAX_LOSS_FAMILY,
    "sp600": f"small_cap_{TAX_LOSS_FAMILY}",
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
logger = logging.getLogger("tax_loss_selling_runner")


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
    n_local = summary.n_trials
    denominators = summary.denominators

    add("=" * 100)
    add("TAX-LOSS SELLING / TURN-OF-THE-YEAR (Poterba & Weisbenner 2001) — RESULTS")
    add("=" * 100)
    add(f"run_tag={RUN_TAG}   wall clock {elapsed / 60:.1f} min")
    add("")
    add("SOURCE: " + TAX_LOSS_CITATION)
    add("")
    add(
        "PRE-REGISTRATION: data/research_runs/tax_loss_selling_PREREGISTRATION.txt, committed as "
        "4ec0672 BEFORE this run existed."
    )
    add(
        "The grid below is that document's grid, unchanged, and the pass/fail rule applied at the "
        "end is that document's rule, unchanged."
    )
    add("")
    add(f"VERDICT (Policy D two-tier, bar = {VALIDATED_EDGE_BAR:.2f}): {verdict.upper()}")
    add(f"  best spec at n_local={n_local}: {best or 'none'}")
    add(f"  DSR denominators reported: {denominators}")
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
        add(f"  financing_bps_per_year={universe.financing_bps_per_year} (gross-notional basis)")
        if universe.half_spread_calibration:
            add(f"  half-spread basis: {universe.half_spread_calibration}")
        add(f"  sigma_sr (sibling Sharpe dispersion, ddof=1): {_fmt(universe.sigma_sr)}")
        add(f"  anchor formation dates in the panel: {', '.join(universe.anchors)}")
        if universe.skipped_years:
            add(f"  anchor years skipped (truncated month / no prior history): {universe.skipped_years}")
        add("")
        add("  SIGNAL COVERAGE BY ANCHOR (n_with_accrued_loss counts the whole priced frame, not")
        add("  just the point-in-time-eligible slice, so it is an upper bound on the loser pool):")
        for anchor_date, cov in universe.coverage_by_anchor.items():
            add(
                f"    {anchor_date}  finite signal {cov['n_finite_signal']:>4}   "
                f"with accrued loss {cov['n_with_accrued_loss']:>4}"
            )
        add("")
        add("  PRICE-BASIS DIAGNOSTIC (pre-registration 3.3): Spearman rank correlation between the")
        add("  dividend-UNADJUSTED signal actually used and the total-return-basis alternative:")
        vals = list(universe.price_vs_total_return_spearman.values())
        if vals:
            add(
                f"    min {_fmt(min(vals))}  median {_fmt(sorted(vals)[len(vals) // 2])}  "
                f"max {_fmt(max(vals))}  over {len(vals)} anchors"
            )
        add("")

        add("  RESULTS — all 16 specs, sorted by DSR at n_local:")
        add("")
        header = "  ".join(f"DSR@{n:<4d}" for n in denominators)
        add(
            f"    spec                                  Sharpe     {header}  "
            "presv   ann.mean   ann.t   hit   n"
        )
        add("    " + "-" * 116)
        for e in sorted(
            universe.evaluations,
            key=lambda x: (x.dsr_by_n.get(n_local) if x.dsr_by_n.get(n_local) is not None else -1.0),
            reverse=True,
        ):
            ladder = "  ".join(_fmt(e.dsr_by_n.get(n)).rjust(8) for n in denominators)
            add(
                f"    {e.pattern_id:<36} {e.sharpe_annualized:+8.4f}  {ladder}  "
                f"{_fmt(e.preservation.get('preservation_score')):>6}  {e.annual.mean:+8.4f}  "
                f"{_fmt(e.annual.naive_t, '.2f'):>6}  {e.annual.hit_rate:4.2f}  "
                f"{e.annual.n_events:2d}"
            )
        add("")
        add(
            "    ann.mean / ann.t / hit / n are the PER-EVENT statistics: each turn-of-year hold "
            "compounded into one"
        )
        add(
            "    number, then mean / (mean/std)*sqrt(n) / fraction positive / count. n IS the "
            "effective independent"
        )
        add(
            "    sample. The Sharpe and DSR columns rest on ~2,700 daily observations of which all "
            "but ~n*h are exact"
        )
        add("    zeros (the book is flat ~246 sessions a year). See pre-registration section 8.")
        add("")

        add("  PER-EVENT RETURNS (real, un-blended book — see pre-registration 3.7):")
        for e in sorted(universe.evaluations, key=lambda x: x.pattern_id):
            add(
                f"    {e.pattern_id:<36} "
                + " ".join(f"{r:+.4f}" for r in e.annual.event_returns)
            )
        add("")

        add("  COST AND TURNOVER, de-scaled to the real once-a-year book (x sleeve_scale):")
        add("")
        add(
            "    spec                                 sleeves   turnover   cost drag   financing   "
            "flat-fallback"
        )
        add("    " + "-" * 104)
        for e in sorted(universe.evaluations, key=lambda x: x.pattern_id):
            add(
                f"    {e.pattern_id:<36} {e.sleeve_scale:5d}  {e.total_turnover:9.3f}  "
                f"{e.total_cost_drag * e.sleeve_scale:10.5f}  "
                f"{e.total_financing_drag * e.sleeve_scale:10.6f}  "
                f"{e.edge_flat_fallback_notional:12.3f}"
            )
        add("")

        if universe.dose_response is not None and universe.dose_response.n_anchors:
            d = universe.dose_response
            add("  FIDELITY CHECK F3 — DOSE RESPONSE ACROSS LOSS BUCKETS")
            add(f"    {d.note}")
            add("    bucket:  " + "  ".join(f"{i:>7d}" for i in range(len(d.bucket_mean_excess))))
            add(
                "    excess:  "
                + "  ".join(f"{v * 100:+7.3f}" for v in d.bucket_mean_excess)
                + "   (%)"
            )
            add(f"    Spearman(bucket rank, mean excess) = {_fmt(d.spearman_rank_vs_excess)}")
            add(
                "    [PW01] eq.(2) is LINEAR in LOSS, so the tax story predicts a MONOTONE increase "
                "across buckets."
            )
            add("")

        add("  PRE-DECLARED BORROW SENSITIVITY LADDER (no new trials — same grid, new returns):")
        for arm in universe.borrow_arms:
            add(f"    {arm.key}: {arm.description}")
            for pid in sorted(arm.sharpe_by_pattern):
                dsr = arm.dsr_by_pattern.get(pid, {})
                add(
                    f"      {pid:<36} Sharpe {arm.sharpe_by_pattern[pid]:+8.4f}   "
                    f"DSR@{n_local} {_fmt(dsr.get(n_local))}"
                )
        add("")
        for warning in universe.warnings:
            add(f"  WARNING: {warning}")
        add("")

    return "\n".join(lines)


def main() -> int:
    started = time.time()
    logger.info("screening tax-loss-selling on %s", list(WINDOWS))
    summary = run_tax_loss_screening(WINDOWS)
    elapsed = time.time() - started

    report = build_report(summary, elapsed)
    (_BACKEND / REPORT_PATH).write_text(report + "\n")
    logger.info("report written to %s", REPORT_PATH)

    payload = {
        "run_tag": RUN_TAG,
        "n_trials": summary.n_trials,
        "denominators": summary.denominators,
        "validated_edge_bar": VALIDATED_EDGE_BAR,
        "screening_floor": SCREENING_FLOOR,
        "verdict": summary.verdict(VALIDATED_EDGE_BAR)[0],
        "best_spec": summary.verdict(VALIDATED_EDGE_BAR)[1],
        "citation": TAX_LOSS_CITATION,
        "preregistration": "data/research_runs/tax_loss_selling_PREREGISTRATION.txt",
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
                "anchors": universe.anchors,
                "skipped_years": universe.skipped_years,
                "coverage_by_anchor": universe.coverage_by_anchor,
                "price_vs_total_return_spearman": universe.price_vs_total_return_spearman,
                "dose_response": (
                    asdict(universe.dose_response) if universe.dose_response is not None else None
                ),
                "warnings": universe.warnings,
                "evaluations": [
                    {
                        **{k: v for k, v in asdict(e).items() if k != "annual"},
                        "annual": asdict(e.annual),
                    }
                    for e in universe.evaluations
                ],
                "borrow_arms": [asdict(a) for a in universe.borrow_arms],
            }
        )
    (_BACKEND / JSON_PATH).write_text(json.dumps(payload, indent=2, default=str) + "\n")
    logger.info("json written to %s", JSON_PATH)

    # PERSISTENCE, AND WHY IT IS CHECKED RATHER THAN ASSUMED.
    #
    # The first run of this family (2026-09-06) wrote both report files and
    # then FAILED to persist a single row: app/config.py defaults
    # database_url to "sqlite:///./aladdin2.db", which resolves against the
    # PROCESS WORKING DIRECTORY, so a runner invoked from a git worktree
    # creates a brand-new, EMPTY aladdin2.db there and every INSERT dies on
    # "no such table". The same thing happened silently to the N-PORT family
    # the day before — its family_key is absent from the project database
    # even though its report is committed and its verdict was acted on.
    #
    # Two consequences, both deliberate:
    #  * The resolved database is LOGGED, so a reader of the run output can
    #    see which file received the rows rather than inferring it.
    #  * The row count is verified by reading back, and a zero raises. A
    #    research run that believes it persisted and did not is exactly the
    #    failure mode this project's "persist every computed result" rule
    #    exists to prevent, and a log line nobody reads is not a check.
    # Point the runner at the project database explicitly when running from a
    # worktree, e.g.
    #   DATABASE_URL=sqlite:////abs/path/to/backend/aladdin2.db ./venv/bin/python ...
    from sqlalchemy import func, select

    from app.config import settings
    from app.models.cross_sectional_trial_result import CrossSectionalTrialResult

    logger.info("persisting to database_url=%s", settings.database_url)
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
        read_back = db.execute(
            select(func.count())
            .select_from(CrossSectionalTrialResult)
            .where(CrossSectionalTrialResult.run_tag == RUN_TAG)
        ).scalar_one()
        if read_back != written:
            raise SystemExit(
                f"PERSISTENCE CHECK FAILED: wrote {written} rows for run_tag={RUN_TAG!r} but read "
                f"back {read_back} from {settings.database_url}. The reports on disk are real; the "
                "database record is not. Do not treat this run as persisted."
            )
        logger.info(
            "persisted and read back %d rows to cross_sectional_trial_results (%s)",
            read_back,
            settings.database_url,
        )
    finally:
        db.close()

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
