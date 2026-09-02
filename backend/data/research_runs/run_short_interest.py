"""Production runner for the short-interest long-side screen.

Calls the module's OWN entrypoint (run_short_interest_screening) — not a
reimplementation, not a shortcut — then persists every per-spec result to the
shared cross_sectional_trial_results table and writes the git-durable plain-text
run report.

Checked into data/research_runs/ alongside the pre-registration and the report so
the exact invocation that produced the numbers is reproducible from the repo,
rather than living only in a scratchpad. Run from backend/ with ./venv/bin/python.
"""

import logging
import sys
import time
from datetime import date
from pathlib import Path

# WORKTREE BINDING GUARD — load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv, whose site-packages
# resolves `app` to the MAIN worktree's backend/app. Without the two lines
# below, this runner silently screens main's code instead of this branch's —
# and for a module that exists in both, with NO error at all.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The screen would have run against another checkout's code."
    )

from app.db import SessionLocal
from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.market_data.finra_short_interest_provider import (
    EARLIEST_SETTLEMENT_DATE,
    PUBLICATION_LAG_CALENDAR_DAYS,
)
from app.services.market_data.sec_shares_outstanding_provider import VISIBILITY_LAG_DAYS
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.cross_sectional_short_interest import (
    SHORT_INTEREST_CITATION,
    SHORT_INTEREST_FAMILY_KEY,
    SHORT_INTEREST_FORMATION_START,
    SHORT_INTEREST_N_TRIALS,
    SHORT_INTEREST_RANK_FRACTION,
    run_short_interest_screening,
)

# Pre-registration section 5, condition (i). Fixed in commit f091c7c BEFORE the
# first result existed; reproduced here as a constant so the report renders the
# rule it actually applied rather than a prose restatement of it.
PASS_BAR_DSR = 0.95

RUN_TAG = "short_interest_build_2026-09-02"
REPORT_PATH = "data/research_runs/short_interest_2026-09-02.txt"
RUN_END = date(2026, 9, 2)

# THE SHARED EDGAR COMPANYFACTS CACHE, stated explicitly rather than left to a
# default. Only the ticker -> CIK map (company_tickers.json) is read from it by
# this family; that file is a GITIGNORED, REFETCHABLE VENDOR CACHE, not results.
SHARED_EDGAR_CACHE = Path("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/edgar_companyfacts")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("short_interest_runner")


def _fmt(value, spec: str = "+.3f") -> str:
    return "n/a" if value is None else format(value, spec)


def build_report(summary, elapsed: float) -> str:
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add("SHORT INTEREST, THE LONG-SIDE READING — RESULTS")
    add("=" * 78)
    add(
        f"Boehmer/Huszar/Jordan (2010) low short interest, screened as exactly "
        f"{SHORT_INTEREST_N_TRIALS} PRE-DECLARED specs under its own "
        f"{SHORT_INTEREST_N_TRIALS}-trial DSR denominator."
    )
    add(f"family_key={SHORT_INTEREST_FAMILY_KEY}  run_tag={RUN_TAG}  wall clock {elapsed / 60:.1f} min")
    add("")
    add("SOURCE: " + SHORT_INTEREST_CITATION)
    add("")
    add(
        "PRE-REGISTRATION: data/research_runs/short_interest_PREREGISTRATION.txt, committed "
        "BEFORE this run existed. The grid below is that document's grid, unchanged, and the "
        "pass/fail rule applied at the end is that document's rule, unchanged."
    )
    add("")
    add("DATA PROVENANCE — REAL, NOT SIMULATED.")
    add(
        "  Short interest: real FINRA bi-monthly files (cdn.finra.org/equity/otcmarket/biweekly). "
        "Share counts: real SEC XBRL frames (dei:EntityCommonStockSharesOutstanding). "
        "Prices: real yfinance daily history. No synthetic input anywhere."
    )
    add("")

    add("=" * 78)
    add("SAMPLE LENGTH — READ THIS BEFORE ANY NUMBER BELOW")
    add("=" * 78)
    add(
        f"FINRA's usable free history on this endpoint begins {EARLIEST_SETTLEMENT_DATE.isoformat()}. "
        f"Formations run from {summary.formation_start.isoformat()}; the price panel is "
        f"{summary.panel_start} .. {summary.panel_end}."
    )
    add(
        "THAT IS ~8.7 YEARS. Most families in this project backtest 10+ years. Every Sharpe and "
        "DSR below carries correspondingly LESS confidence than a same-numbered result from a "
        "longer-sample family, and must not be compared to one as if it were equivalent."
    )
    add(
        "The build brief scoped this candidate at ~5.2 years (FINRA's catalog note says "
        "exchange-listed coverage starts June 2021). That premise was CHECKED and is wrong for "
        "this endpoint as served today — see pre-registration section 3, which also records the "
        "unresolved question of whether pre-2021 files were retroactively backfilled."
    )
    add("")

    add("=" * 78)
    add("UNIVERSE AND PANEL ACCOUNTING (all measured this run, none assumed)")
    add("=" * 78)
    add(
        f"Point-in-time S&P 500 union pool: {summary.universe_size} tickers (FULL universe, not a "
        f"seeded sample — this family's data cost is per-CYCLE, not per-ticker)."
    )
    add(f"  {len(summary.missing_price_data)} resolved no yfinance price history.")
    add(
        f"FINRA cycles: {summary.finra.n_cycles_resolved} resolved of "
        f"{summary.finra.n_cycles_requested} anchors; unresolved: "
        f"{[d.isoformat() for d in summary.finra.unresolved_anchors]}"
    )
    add(f"  rows parsed: {summary.finra.n_rows_parsed:,}   refusals: {summary.finra.n_rows_refused}")
    add(f"  separator-stripped symbol matches: {summary.finra.separator_stripped_matches}")
    add(
        f"SEC share counts: {summary.shares.n_frames_resolved} frames, "
        f"{summary.shares.n_observations:,} observations; "
        f"{len(summary.shares.tickers_without_cik)} tickers resolve no CIK; "
        f"{len(summary.shares.tickers_without_share_count)} resolve a CIK but no count."
    )
    add(f"  refusals: {summary.shares.n_refused}")
    add(
        "  THE TWO SHARE-COUNT PLAUSIBILITY GUARDS — every record they threw away, named. These "
        "exist because THIS FAMILY'S FIRST RUN emitted a realized short-interest ratio range of "
        "0 .. 32,050,932, a quantity confined to ~[0,1]. Root-caused to shell/pre-distribution "
        "registrations (a token share count) and to scale/units errors, both real and both in "
        "SEC's own data:"
    )
    for ticker, as_of, value in sorted(summary.shares.refused_records):
        add(f"    {ticker:<8} {as_of.isoformat()}  {value:>25,.0f}")
    add(
        f"    ({len(summary.shares.refused_records)} records refused of "
        f"{summary.shares.n_observations + len(summary.shares.refused_records):,} seen)"
    )
    add("")
    add("PANEL:")
    add(f"  short-interest observations used (ratio): {summary.panel.n_observations_used:,}")
    add(f"  refusals: {summary.panel.n_refused}")
    add(
        f"  THE COMMON-CROSS-SECTION MASK: {summary.panel.n_cells_common:,} cells finite in BOTH "
        f"panels; {summary.panel.n_cells_ratio_only:,} were ratio-only and "
        f"{summary.panel.n_cells_dtc_only:,} days-to-cover-only — all of those are masked out so "
        "the two normalizer halves rank the identical cross-section."
    )
    add(f"  {len(summary.panel.tickers_never_ranked)} priced tickers are never ranked at all.")
    add(f"  realized short-interest ratio range: {summary.ratio_range[0]:.5f} .. {summary.ratio_range[1]:.5f}")
    add(f"  realized days-to-cover range:        {summary.dtc_range[0]:.3f} .. {summary.dtc_range[1]:.3f}")
    add("  mean names ranked per formation:")
    for key, value in sorted(summary.n_eligible_by_formation.items()):
        add(f"    {key:<22} {value:7.1f}")
    add("")
    add(
        "RESIDUAL SURVIVORSHIP, stated not hidden: the mask reimports SEC's current-day "
        "ticker-map bias into the whole family. The names it drops are overwhelmingly index "
        "leavers — disproportionately the short/hedge leg's natural candidates — so the "
        "surviving cross-section is better than the real one was. THIS FLATTERS THE RESULTS."
    )
    add("")

    add("=" * 78)
    add("POINT-IN-TIME BOUNDS ACTUALLY APPLIED")
    add("=" * 78)
    add(
        f"  short interest readable at settlement + {PUBLICATION_LAG_CALENDAR_DAYS} calendar days "
        "(FINRA's own published 2026 schedule has a worst real gap of 12 days; this bound is "
        "unit-tested against all 24 of its rows)."
    )
    add(
        f"  share counts readable at cover-page `end` + {VISIBILITY_LAG_DAYS} calendar days (set "
        "from 7,539 MEASURED real (end, filed) pairs: p50 8, p95 35, p99 73; ~0.5% residual "
        "disclosed in the provider docstring)."
    )
    add("")

    add("=" * 78)
    add("COST MODEL")
    add("=" * 78)
    add(f"{summary.cost_bps:.1f}bp one-way flat on turnover — same as every S&P 500 equity family here.")
    add(
        f"Financing {summary.financing_bps_per_year:.0f}bp/yr: this project's standing DISCLOSED "
        "optimism about short borrow, NOT an estimate — and it bites HARDER here than anywhere "
        "else, because this family's entire subject is short selling. The long_short specs short "
        "the MOST heavily shorted names in the index, exactly where real borrow is expensive. "
        "THIS FLATTERS THE SHORT LEG, and is a reason the pass rule leans on the long side."
    )
    add("")

    add("=" * 78)
    add(f"RESULTS — ALL {SHORT_INTEREST_N_TRIALS} SPECS, ranked by Sharpe")
    add("=" * 78)
    add(
        f"rank_fraction fixed at {SHORT_INTEREST_RANK_FRACTION} (the paper's 5th-percentile "
        "cutoff), NOT searched over — see pre-registration section 4."
    )
    add("")
    ordered = sorted(summary.results, key=lambda r: -r.sharpe_annualized)
    header = (
        f"{'pattern_id':<24} {'Sharpe':>8} {'DSR':>7} {'PSR>0':>7} {'days':>6} "
        f"{'forms':>6} {'skip':>5} {'names/leg':>10} {'costdrag':>9}"
    )
    add(header)
    add("-" * len(header))
    for r in ordered:
        add(
            f"{r.pattern_id:<24} {r.sharpe_annualized:>+8.3f} "
            f"{_fmt(r.deflated_sharpe.dsr, '.3f'):>7} "
            f"{_fmt(r.deflated_sharpe.psr_vs_zero, '.3f'):>7} "
            f"{r.n_trading_days:>6,} {r.n_formations:>6} {r.n_skipped_formations:>5} "
            f"{r.avg_names_per_leg:>10.1f} {r.total_cost_drag:>9.4f}"
        )
    add("")
    if ordered:
        first = ordered[0]
        add(
            f"DSR denominator n_trials={first.deflated_sharpe.n_trials} on every row — the "
            "family's full pre-declared grid size, passed explicitly to both normalizer passes so "
            "neither is scored against a halved denominator."
        )
        add(
            "sigma_SR is estimated WITHIN each 6-spec pass (the harness sees one panel at a "
            "time) — a disclosed limitation of the estimate's stability, stated in "
            "pre-registration section 4 before this run."
        )
    add("")

    add("=" * 78)
    add("PRE-DECLARED DIAGNOSTIC: THE JANUARY SPLIT")
    add("=" * 78)
    add(
        "Pre-registered in section 6 because one source claims BHJ's long side is mainly a "
        "January effect. Mean DAILY return, January vs the rest. Reported whatever it shows; "
        "never used to select a spec."
    )
    add("")
    add(f"{'pattern_id':<24} {'Jan mean':>12} {'non-Jan mean':>14} {'ratio':>9}")
    add("-" * 62)
    for pattern_id, (jan, other) in sorted(summary.january_split.items()):
        ratio = (jan / other) if other not in (0.0,) and other == other else float("nan")
        add(f"{pattern_id:<24} {jan:>+12.6f} {other:>+14.6f} {ratio:>9.2f}")
    add("")

    add("=" * 78)
    add("VERDICT — THE PRE-REGISTERED RULE, APPLIED UNCHANGED")
    add("=" * 78)
    best = ordered[0] if ordered else None
    if best is None:
        add("No replayable spec — no verdict.")
        return "\n".join(lines)
    best_dsr = best.deflated_sharpe.dsr
    add(
        f"Pre-registration section 5, condition (i): the best spec's DSR must clear {PASS_BAR_DSR}."
    )
    add(f"  best spec = {best.pattern_id}, Sharpe {best.sharpe_annualized:+.3f}, DSR {best_dsr:.3f}")
    passed = best_dsr is not None and best_dsr > PASS_BAR_DSR
    if passed:
        add("  CONDITION (i) MET — proceed to condition (ii).")
    else:
        add(
            f"  CONDITION (i) NOT MET ({best_dsr:.3f} <= {PASS_BAR_DSR}). Condition (ii) is never "
            "reached. THE VERDICT IS AN HONEST NEGATIVE."
        )
        add("")
        add(
            f"  The rule is applied exactly as written. {best_dsr:.3f} is not {PASS_BAR_DSR}, and "
            "'close to a threshold' is not a pass — the bar was fixed in commit f091c7c before "
            "any of these numbers existed, and moving it now for any reason would convert this "
            "whole exercise into the thing it was built to prevent."
        )
    add("")
    n_dtc_in_top5 = sum(1 for r in ordered[:5] if r.pattern_id.startswith("si_dtc"))
    add(
        "READ THE FULL VERDICT, INCLUDING THE VOLUME CONFOUND, in "
        "cross_sectional_short_interest.py section 5. The structural fact this run measured: "
        f"{n_dtc_in_top5} of the top 5 specs are DAYS-TO-COVER, which is NOT the paper's own "
        "measure; the paper's measure (short interest / shares outstanding) fills the bottom "
        "half of the grid."
    )
    add(
        "  A POST-HOC diagnostic (run separately on 2026-09-02, AFTER this verdict was already a "
        "fail, and incapable of changing it — these figures are NOT produced by this run and "
        "will not update if it is re-run) found: the ratio and days-to-cover long legs overlap "
        "only 19.7% over 34 quarterly formations; the days-to-cover long leg sits at the 72.7th "
        "percentile of trading VOLUME but only the 33.2nd percentile of the short-interest ratio "
        "itself. Sorting on low days-to-cover is substantially sorting on high volume."
    )
    add("")
    add(
        "FORWARD VALIDATION: nothing from this family is registered, and no registration is "
        "wired into app startup. The reasoning, and the specific recommendation for a human who "
        "wants it accumulating (si_dtc_hedged_h63), is in that module's section 6."
    )
    add("")
    return "\n".join(lines)


def main() -> int:
    started = time.time()
    logger.info("short interest screen starting; run_tag=%s", RUN_TAG)
    edgar = EdgarXbrlProvider(cache_dir=SHARED_EDGAR_CACHE)

    summary = run_short_interest_screening(
        start=SHORT_INTEREST_FORMATION_START, end=RUN_END, edgar=edgar
    )
    elapsed = time.time() - started

    if not summary.results:
        logger.error("screen produced ZERO replayable specs; warnings=%s", summary.warnings)
        return 1

    for warning in summary.warnings:
        logger.warning("%s", warning)

    report = build_report(summary, elapsed)
    print(report)
    Path(_BACKEND / REPORT_PATH).write_text(report + "\n")
    logger.info("report written to %s", REPORT_PATH)

    db = SessionLocal()
    try:
        n = persist_cross_sectional_trial_results(
            db, SHORT_INTEREST_FAMILY_KEY, summary.results, run_tag=RUN_TAG
        )
        logger.info("persisted %d rows to cross_sectional_trial_results", n)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
