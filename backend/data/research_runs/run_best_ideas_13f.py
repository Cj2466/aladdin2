"""Production runner for the 13F institutional "Best Ideas" screen.

Calls the module's OWN entrypoint (run_best_ideas_screening) — not a
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
from app.services.research_lab.cross_sectional_best_ideas import (
    ACTIVENESS_QUANTILE,
    BEST_IDEA_MEASURES,
    BEST_IDEAS_CITATION,
    BEST_IDEAS_FAMILY_KEY,
    BEST_IDEAS_N_TRIALS,
    MANAGER_VIEW_MAX_STALENESS_DAYS,
    MAX_REPORTING_LAG_DAYS,
    MIN_HOLDINGS_PER_FILING,
    MIN_PORTFOLIO_VALUE_USD,
    run_best_ideas_screening,
)
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

RUN_TAG = "best_ideas_13f_build_2026-09-02"
REPORT_PATH = "data/research_runs/best_ideas_13f_2026-09-02.txt"
RUN_END = date(2026, 8, 31)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("best_ideas_runner")


def _fmt(value: float | None, spec: str = "+.3f") -> str:
    return "n/a" if value is None else format(value, spec)


def build_report(summary, elapsed: float) -> str:
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add('13F INSTITUTIONAL "BEST IDEAS" — RESULTS')
    add("=" * 78)
    add(
        f"Anton/Cohen/Polk best ideas, screened as exactly {BEST_IDEAS_N_TRIALS} PRE-DECLARED "
        f"specs under its own {BEST_IDEAS_N_TRIALS}-trial DSR denominator."
    )
    add(
        f"family_key={BEST_IDEAS_FAMILY_KEY}  run_tag={RUN_TAG}  wall clock {elapsed / 60:.1f} min"
    )
    add("")
    add("SOURCE: " + BEST_IDEAS_CITATION)
    add("")
    add(
        "PRE-REGISTRATION: data/research_runs/best_ideas_13f_PREREGISTRATION.txt, committed in "
        "ac9bc8b BEFORE this run existed. The grid below is that document's grid, unchanged, and "
        "the pass/fail rule applied at the end is that document's rule, unchanged."
    )
    add("")
    add("DATA PROVENANCE — REAL, NOT SIMULATED.")
    add(
        "  Holdings: real SEC Form 13F structured data sets (quarterly TSV archives downloaded "
        f"from sec.gov). {len(summary.quarters_parsed)} archives parsed: "
        f"{summary.quarters_parsed[0]} .. {summary.quarters_parsed[-1]}."
    )
    add(
        "  CUSIP->ticker: real SEC fails-to-deliver files (the official free, dated "
        "(CUSIP, SYMBOL) source; this project holds no CUSIP licence)."
    )
    add("  Prices: real yfinance daily history. No synthetic or simulated input anywhere.")
    add("")

    add("=" * 78)
    add("POINT-IN-TIME — THE HEADLINE CORRECTNESS NUMBERS")
    add("=" * 78)
    add(
        "Every filing becomes visible on its own FILING_DATE and never one day earlier. The "
        "SEC archives are themselves organised by filing window, and SUBMISSION.tsv carries the "
        "exact filing date per accession."
    )
    add(
        f"  Realized report-period -> filing-date lag across all eligible filings: "
        f"min {summary.min_filing_lag_days} days, median "
        f"{summary.median_filing_lag_days:.0f} days."
    )
    add(
        "  MIN LAG IS NEVER NEGATIVE BY CONSTRUCTION: the parser refuses any submission whose "
        "FILING_DATE precedes its own PERIODOFREPORT (counted as filed_before_period_end)."
    )
    add(
        f"  A filing whose report period was already older than {MAX_REPORTING_LAG_DAYS} days when "
        "filed is refused outright — delinquent filers reporting multi-year-old books are public "
        "when filed (so not look-ahead) but do not represent current conviction."
    )
    add(
        f"  A manager's view expires {MANAGER_VIEW_MAX_STALENESS_DAYS} calendar days after it was "
        "filed, so a filer who stops filing does not haunt the panel."
    )
    add(
        "  Both cross-manager statistics (the aggregate market-weight vector and the activeness "
        "cutoff) are computed from the PREVIOUS period's filings, restricted to those filed "
        "strictly before the current period ended — so no filing is ever judged against a "
        "contemporaneous or later one."
    )
    add(
        "  Tests (a)-(d) named in advance in the pre-registration are implemented in "
        "tests/test_cross_sectional_best_ideas.py, two of them against REAL cached SEC archives."
    )
    add("")

    add("=" * 78)
    add("UNIVERSE AND IDENTIFIER COVERAGE (all measured this run, none assumed)")
    add("=" * 78)
    add(
        f"Point-in-time S&P 500 union pool over [{MEMBERSHIP_DATA_START.isoformat()}, "
        f"{RUN_END.isoformat()}]: {summary.universe_size} tickers — the FULL pool, not a seeded "
        "sample, because 13F archives are whole-market files parsed once regardless of universe "
        "size (unlike the EDGAR families, which pay one fetch per ticker)."
    )
    add(
        f"  CUSIP->ticker map: {summary.cusip_map_size:,} CUSIPs, resolving "
        f"{summary.universe_tickers_with_cusip} of {summary.universe_size} universe tickers "
        f"({summary.universe_tickers_with_cusip / max(summary.universe_size, 1) * 100:.1f}%)."
    )
    if summary.universe_tickers_without_cusip:
        add(
            f"  {len(summary.universe_tickers_without_cusip)} tickers NEVER resolved a CUSIP and "
            f"can never be ranked: {summary.universe_tickers_without_cusip}"
        )
    add(
        f"  {len(summary.missing_price_data)} universe tickers resolved no yfinance price history "
        "(the standing departed-member gap)."
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
    add("MANAGER UNIVERSE")
    add("=" * 78)
    diag = summary.diagnostics
    add(
        f"Eligible manager-filing views: {summary.n_manager_views:,} from "
        f"{summary.n_distinct_managers:,} distinct filers across {diag.n_periods} report periods."
    )
    add(
        f"Screens applied (the paper's own where the data permits): >= {MIN_HOLDINGS_PER_FILING} "
        f"holdings, > ${MIN_PORTFOLIO_VALUE_USD:,.0f} equity, index/passive filer-name screen, "
        f"top {(1 - ACTIVENESS_QUANTILE) * 100:.0f}% activeness cut per measure."
    )
    add("FILING-LEVEL REFUSALS (each counted, never silent):")
    for reason, count in sorted(diag.n_refused.items(), key=lambda kv: -kv[1]):
        add(f"  {reason}: {count:,}")
    add("")
    add("Best ideas landing INSIDE the ranked universe, by measure:")
    for measure in BEST_IDEA_MEASURES:
        n = diag.n_best_idea_in_universe.get(measure, 0)
        add(
            f"  {measure:<16} {n:>8,} of {summary.n_manager_views:,} views "
            f"({n / max(summary.n_manager_views, 1) * 100:5.1f}%)"
        )
    add(
        "  The rest name a security outside the S&P 500 — the CORRECT answer, and consistent with "
        "the paper's own finding that best ideas are spread thinly across the whole market."
    )
    add("")
    add("Fraction of ranked (day, ticker) cells with a NON-ZERO best-idea count:")
    for measure, rate in summary.panel_nonzero_rate.items():
        add(f"  {measure:<16} {rate * 100:5.1f}%")
    add("")

    add("=" * 78)
    add("SEC ARCHIVE PARSE DIAGNOSTICS")
    add("=" * 78)
    parse = diag.parse
    add(
        f"  {parse.n_submissions:,} submissions, {parse.n_holdings_filings:,} holdings filings, "
        f"{parse.n_rows:,} INFOTABLE rows."
    )
    add(f"  VALUE unit scale per filing: {dict(parse.value_scale_counts)}")
    add(
        "  (13F specifies VALUE in THOUSANDS; a minority of filers report whole dollars anyway. "
        "The scale is classified per filing from its own median implied price. Portfolio WEIGHTS "
        "are immune to the defect either way — they are ratios of same-unit numbers.)"
    )
    add("  ROW REFUSALS:")
    for reason, count in sorted(parse.n_refused.items(), key=lambda kv: -kv[1])[:12]:
        add(f"    {reason}: {count:,}")
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
    add(f"RESULTS — ALL {BEST_IDEAS_N_TRIALS} SPECS, ranked by Sharpe")
    add("=" * 78)
    ordered = sorted(summary.results, key=lambda r: -r.sharpe_annualized)
    header = (
        f"{'pattern_id':<38} {'Sharpe':>8} {'DSR':>7} {'PSR>0':>7} {'days':>6} "
        f"{'forms':>6} {'skip':>5} {'names/leg':>10} {'costdrag':>9}"
    )
    add(header)
    add("-" * len(header))
    for r in ordered:
        add(
            f"{r.pattern_id:<38} {r.sharpe_annualized:>+8.3f} "
            f"{_fmt(r.deflated_sharpe.dsr, '.3f'):>7} "
            f"{_fmt(r.deflated_sharpe.psr_vs_zero, '.3f'):>7} "
            f"{r.n_trading_days:>6,} {r.n_formations:>6} {r.n_skipped_formations:>5} "
            f"{r.avg_names_per_leg:>10.1f} {r.total_cost_drag:>9.4f}"
        )
    add("")
    first = ordered[0]
    add(
        f"DSR denominator n_trials={first.deflated_sharpe.n_trials} for every row — this family's "
        "own pre-declared grid size, no carried trials (see pre-registration section 6)."
    )
    add("")
    add("WARNINGS RAISED THIS RUN:")
    for warning in summary.warnings:
        add(f"  * {warning}")
    if not summary.warnings:
        add("  none")
    add("")
    return "\n".join(lines)


def main() -> int:
    started = time.time()
    logger.info("13F best-ideas screen starting; run_tag=%s", RUN_TAG)

    summary = run_best_ideas_screening(end=RUN_END)
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
            db, BEST_IDEAS_FAMILY_KEY, summary.results, run_tag=RUN_TAG
        )
        logger.info("persisted %d rows to cross_sectional_trial_results", n)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
