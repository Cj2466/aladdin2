"""Production runner for the asset growth / investment effect screen.

Calls the module's OWN entrypoint (run_asset_growth_screening) — not a
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
from app.services.research_lab.cross_sectional_asset_growth import (
    ASSET_GROWTH_CITATION,
    ASSET_GROWTH_FAMILY_KEY,
    ASSET_GROWTH_N_TRIALS,
    run_asset_growth_screening,
)
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

RUN_TAG = "asset_growth_build_2026-09-01"
REPORT_PATH = "data/research_runs/asset_growth_2026-09-01.txt"
RUN_END = date(2026, 9, 1)

# THE SHARED EDGAR COMPANYFACTS CACHE, stated explicitly rather than left to a
# default. This worktree's own data/edgar_companyfacts/ is empty, while the main
# checkout holds the ~165 CIKs the sibling quality families already fetched from
# SEC. That directory is a GITIGNORED, REFETCHABLE VENDOR CACHE (see backend/
# .gitignore: "Raw SEC EDGAR companyfacts JSON cache ... not results"), not code
# and not results, and it is the same real SEC data either way — pointing at it
# avoids ~165 redundant multi-MB fetches against SEC's fair-access limits. Any
# CIK not already cached is fetched LIVE from SEC on this run and written here.
SHARED_EDGAR_CACHE = Path("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/edgar_companyfacts")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("asset_growth_runner")


def _fmt(value: float | None, spec: str = "+.3f") -> str:
    return "n/a" if value is None else format(value, spec)


def build_report(summary, elapsed: float) -> str:
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add("ASSET GROWTH / INVESTMENT EFFECT — RESULTS")
    add("=" * 78)
    add(
        f"Cooper/Gulen/Schill (2008) total asset growth, screened as exactly "
        f"{ASSET_GROWTH_N_TRIALS} PRE-DECLARED specs under its own {ASSET_GROWTH_N_TRIALS}-trial "
        "DSR denominator."
    )
    add(f"family_key={ASSET_GROWTH_FAMILY_KEY}  run_tag={RUN_TAG}  wall clock {elapsed / 60:.1f} min")
    add("")
    add("SOURCE: " + ASSET_GROWTH_CITATION)
    add("")
    add(
        "PRE-REGISTRATION: data/research_runs/asset_growth_PREREGISTRATION.txt, committed in "
        "16841c5 BEFORE this run existed. The grid below is that document's grid, unchanged, and "
        "the pass/fail rule applied at the end is that document's rule, unchanged."
    )
    add("")
    add("DATA PROVENANCE — REAL, NOT SIMULATED.")
    add(
        "  Fundamentals: real SEC EDGAR XBRL companyfacts JSON (data.sec.gov), via the shared "
        "gitignored vendor cache the sibling quality families populated, refetched live from SEC "
        "for anything absent. Industry classifications: real archived 10-K SGML headers."
    )
    add("  Prices: real yfinance daily history. No synthetic or simulated input anywhere.")
    add("")

    add("=" * 78)
    add("UNIVERSE ACCOUNTING (all measured this run, none assumed)")
    add("=" * 78)
    add(
        f"Point-in-time S&P 500 union pool over [{MEMBERSHIP_DATA_START.isoformat()}, "
        f"{RUN_END.isoformat()}]: {summary.universe_size} tickers. Seeded sample actually "
        f"screened: {summary.sample_size} (seed {summary.sample_seed}) — the IDENTICAL sample as "
        "the sibling quality families, deliberately, so this result is about the same "
        "cross-section whose sector composition is already measured."
    )
    add(
        f"  {len(summary.missing_cik)} sampled tickers resolve NO CIK in SEC's current-day ticker "
        "map (departed members whose symbols died with them) and can never be ranked."
    )
    add(f"  {len(summary.failed_edgar_fetch)} EDGAR companyfacts fetches failed outright.")
    add(
        f"  {len(summary.missing_price_data)} sampled tickers resolved no yfinance price history "
        "(the standing departed-member gap)."
    )
    add(
        f"  {len(summary.tickers_without_asset_growth)} PRICED tickers produced no usable "
        "asset-growth observation and are never ranked."
    )
    add(f"Price panel: {summary.panel_start} .. {summary.panel_end}")
    add("")
    add(
        "RESIDUAL SURVIVORSHIP, stated not hidden: point-in-time membership makes the ROSTER "
        "honest, not the PRICES. The unresolvable names are overwhelmingly index leavers, i.e. "
        "disproportionately the short leg's natural candidates, so the surviving cross-section is "
        "better than the real one was. THIS FLATTERS THE RESULTS BELOW."
    )
    add("")

    add("=" * 78)
    add("THE FACTOR PANEL — COVERAGE AND THE ENTITY GUARD")
    add("=" * 78)
    diag = summary.diagnostics
    add(f"Asset-growth firm-year observations: {diag.n_observations:,}")
    add(
        f"Realized `Assets` tag coverage (the one line item this factor needs): "
        f"{summary.assets_tier_usage}"
    )
    add(f"Median panel-cell age on formation-eligible dates: {summary.median_value_age_days:.0f} days")
    add(
        f"Realized factor range: {summary.min_asset_growth:+.3f} .. {summary.max_asset_growth:+.3f} "
        "(i.e. annual asset growth, as a fraction)"
    )
    add("REFUSALS (each counted, never silent):")
    if diag.n_refused:
        for reason, count in sorted(diag.n_refused.items(), key=lambda kv: -kv[1]):
            add(f"  {reason}: {count}")
    else:
        add("  none")
    add(
        "  `assets_entity_scale_break` is THE load-bearing guard for this factor: a growth rate is "
        "a ratio of exactly the two numbers a shell-to-operating-company transition makes "
        "incomparable. Unguarded, TechnipFMC's real $74,100 -> $28.3B pair is a growth rate of "
        "~+38,000,000% that would pin the name to the short leg's extreme for a year."
    )
    add("")

    add("=" * 78)
    add("INDUSTRY BUCKETS (the neutral half of the grid) — POINT-IN-TIME SIC")
    add("=" * 78)
    add(
        f"  {len(summary.tickers_without_bucket)} tickers have no bucket at all; "
        f"{len(summary.current_sic_fallback_tickers)} bucketed from CURRENT SIC only "
        f"{summary.current_sic_fallback_tickers} (a disclosed point-in-time approximation)."
    )
    add(
        f"  {summary.n_growth_without_bucket_slots} ranked ticker-formation slots had a growth "
        f"value but no bucket; {summary.n_min_bucket_refusals} refused by MIN_BUCKET_SIZE=3."
    )
    total_slots = sum(summary.bucket_slot_counts.values()) or 1
    add(f"  Realized composition over {total_slots:,} ranked slots (h126 cadence):")
    for bucket, count in sorted(summary.bucket_slot_counts.items(), key=lambda kv: -kv[1]):
        add(f"    {bucket:<16} {count:6,}  {count / total_slots * 100:5.1f}%")
    add("")

    add("=" * 78)
    add("COST MODEL")
    add("=" * 78)
    add(
        f"{summary.cost_bps:.1f}bp one-way flat on turnover — identical to every S&P 500 equity "
        "family here, so Sharpes stay comparable across families."
    )
    add(
        f"Financing {summary.financing_bps_per_year:.0f}bp/yr: this project's standing DISCLOSED "
        "optimism about short borrow, NOT an estimate. A real securities-borrow feed remains a "
        "known open paid-data item. This FLATTERS the short leg."
    )
    add("")

    add("=" * 78)
    add(f"RESULTS — ALL {ASSET_GROWTH_N_TRIALS} SPECS, ranked by Sharpe")
    add("=" * 78)
    ordered = sorted(summary.results, key=lambda r: -r.sharpe_annualized)
    header = (
        f"{'pattern_id':<30} {'Sharpe':>8} {'DSR':>7} {'PSR>0':>7} {'days':>6} "
        f"{'forms':>6} {'skip':>5} {'names/leg':>10} {'costdrag':>9}"
    )
    add(header)
    add("-" * len(header))
    for r in ordered:
        add(
            f"{r.pattern_id:<30} {r.sharpe_annualized:>+8.3f} "
            f"{_fmt(r.deflated_sharpe.dsr, '.3f'):>7} "
            f"{_fmt(r.deflated_sharpe.psr_vs_zero, '.3f'):>7} "
            f"{r.n_trading_days:>6,} {r.n_formations:>6} {r.n_skipped_formations:>5} "
            f"{r.avg_names_per_leg:>10.1f} {r.total_cost_drag:>9.4f}"
        )
    add("")
    first = ordered[0]
    add(
        f"DSR denominator n_trials={first.deflated_sharpe.n_trials} for every row — this family's "
        "own pre-declared grid size, no carried trials (see pre-registration section 5)."
    )
    add("")
    return "\n".join(lines)


def main() -> int:
    started = time.time()
    logger.info("asset growth screen starting; run_tag=%s", RUN_TAG)
    if not SHARED_EDGAR_CACHE.exists():
        logger.warning("shared EDGAR cache %s absent — every CIK will be fetched live", SHARED_EDGAR_CACHE)
    edgar = EdgarXbrlProvider(cache_dir=SHARED_EDGAR_CACHE)

    summary = run_asset_growth_screening(end=RUN_END, edgar=edgar)
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
            db, ASSET_GROWTH_FAMILY_KEY, summary.results, run_tag=RUN_TAG
        )
        logger.info("persisted %d rows to cross_sectional_trial_results", n)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
