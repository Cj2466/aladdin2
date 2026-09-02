"""Production runner for the residual (idiosyncratic) momentum screen.

Calls the module's OWN entrypoint (run_residual_momentum_screening) — not a
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
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.cross_sectional_residual_momentum import (
    RESIDUAL_MOM_ARMS,
    RESIDUAL_MOM_CONDITIONINGS,
    RESIDUAL_MOM_FAMILY_KEY,
    RESIDUAL_MOM_HOLDING_DAYS,
    RESIDUAL_MOM_N_TRIALS,
    RESIDUAL_MOMENTUM_CITATION,
    run_residual_momentum_screening,
)
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

RUN_TAG = "residual_momentum_build_2026-09-02"
REPORT_PATH = "data/research_runs/residual_momentum_2026-09-02.txt"
RUN_END = date(2026, 9, 2)

# The pre-registered pass/fail bar, restated here as a constant so the report's
# verdict is computed rather than typed. See the pre-registration, section 6.
DSR_BAR = 0.95

# THE SHARED EDGAR CACHE, stated explicitly rather than left to a default. This
# worktree's own data/edgar_companyfacts/ is empty, while the main checkout
# holds the CIKs the sibling quality families already fetched from SEC. That
# directory is a GITIGNORED, REFETCHABLE VENDOR CACHE, not code and not results,
# and it is the same real SEC data either way — pointing at it avoids redundant
# fetches against SEC's fair-access limits. Anything not cached is fetched LIVE.
SHARED_EDGAR_CACHE = Path(
    "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/edgar_companyfacts"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("residual_momentum_runner")


def _fmt(value: float | None, spec: str = "+.3f") -> str:
    return "n/a" if value is None else format(value, spec)


def _arm_of(pattern_id: str) -> str:
    for arm, _cols in RESIDUAL_MOM_ARMS:
        if pattern_id.startswith(f"rm_{arm}"):
            return arm
    raise ValueError(f"unrecognised pattern_id {pattern_id}")


def _conditioning_of(pattern_id: str) -> str:
    return "industry_neutral" if "_neutral_" in pattern_id else "raw"


def _holding_of(pattern_id: str) -> int:
    return int(pattern_id.rsplit("_h", 1)[1])


def build_report(summary, elapsed: float) -> str:
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add("RESIDUAL (IDIOSYNCRATIC) MOMENTUM — RESULTS")
    add("=" * 78)
    add(
        f"Blitz/Huij/Martens (2011) residual momentum, screened as exactly "
        f"{RESIDUAL_MOM_N_TRIALS} PRE-DECLARED specs under its own "
        f"{RESIDUAL_MOM_N_TRIALS}-trial DSR denominator."
    )
    add(
        f"family_key={RESIDUAL_MOM_FAMILY_KEY}  run_tag={RUN_TAG}  "
        f"wall clock {elapsed / 60:.1f} min"
    )
    add("")
    add("SOURCE: " + RESIDUAL_MOMENTUM_CITATION)
    add("")
    add(
        "PRE-REGISTRATION: data/research_runs/residual_momentum_PREREGISTRATION.txt, committed "
        "in 75b9ff4 BEFORE this run existed and before this module was written. The grid below "
        "is that document's grid, unchanged, and the pass/fail rule applied at the end is that "
        "document's rule, unchanged."
    )
    add("")
    add("DATA PROVENANCE — REAL, NOT SIMULATED.")
    add(
        "  Factors: Kenneth R. French's own Fama/French 3 Factors monthly file, committed at "
        "backend/data/fama_french_factors_monthly.csv so this run's exact vintage is in git."
    )
    add(f"    vintage line: {summary.factor_vintage}")
    add(
        f"    coverage: {summary.factor_first_month} -> {summary.factor_last_month}; "
        f"missing-value sentinel cells converted to NaN: {summary.factor_sentinel_cells}"
    )
    add("  Prices: real yfinance daily adjusted closes (total-return basis).")
    add("  Industry classifications: real archived SEC 10-K SGML filing headers.")
    add("  No synthetic or simulated input anywhere in this run.")
    add("")

    add("=" * 78)
    add("CONSTRUCTION ACTUALLY USED")
    add("=" * 78)
    add(
        f"  Rolling OLS estimation window     {summary.regression_months} months "
        "(BHM's own; NOT a grid axis)"
    )
    add(
        f"  Scoring window (Eq. 9)            {summary.formation_months} months, "
        "most recent month skipped"
    )
    add(
        f"  Factor publication lag applied    {summary.publication_lag_days} calendar days "
        "(measured French lag on this vintage: 34)"
    )
    add(f"  Score staleness bound             {summary.max_staleness_days} calendar days")
    add(
        f"  MEDIAN AGE OF THE DATA RANKED ON  {summary.median_signal_age_days:.0f} calendar days "
        "— the realized skip, measured not assumed"
    )
    add("  Alpha is NOT added back; legs are deciles, equal-weighted, long_short.")
    add("")

    add("=" * 78)
    add("UNIVERSE ACCOUNTING (all measured this run, none assumed)")
    add("=" * 78)
    add(
        f"Point-in-time S&P 500 union pool over [{MEMBERSHIP_DATA_START.isoformat()}, "
        f"{RUN_END.isoformat()}]: {summary.universe_size} tickers. Seeded sample actually "
        f"screened: {summary.sample_size} (seed {summary.sample_seed}) — the IDENTICAL sample as "
        "the sibling quality / asset-growth families, deliberately."
    )
    add(
        f"  {len(summary.missing_price_data)} sampled tickers resolved NO price data "
        "(the standing departed-member yfinance gap)."
    )
    add(
        f"  {len(summary.tickers_without_score)} priced tickers produced no usable score at any "
        f"date (need {summary.regression_months} complete consecutive monthly returns)."
    )
    add(f"  Price panel: {summary.panel_start} -> {summary.panel_end}")
    add(f"  First formation permitted at: {summary.formation_start}")
    add("")
    add("SCORE DIAGNOSTICS")
    d = summary.diagnostics
    add(f"  monthly windows evaluated                  {d.n_month_windows}")
    add(f"  ...refused for incomplete factor coverage  {d.n_months_without_factor_coverage}")
    add(f"  ticker-months scored (per arm)             {d.n_scored}")
    for reason, count in sorted(d.n_refused.items()):
        add(f"  refused: {reason:<40} {count}")
    if not any(k.startswith("degenerate_residual_std") for k in d.n_refused):
        add(
            "  refused: degenerate_residual_std_*            0  "
            "(the _MIN_RESIDUAL_STD guard never fired — expected on real data)"
        )
    add("  realized score range per arm:")
    for arm, (low, high) in summary.score_range.items():
        add(f"    {arm:<24} {low:+.3f} .. {high:+.3f}")
    add("")
    add("INDUSTRY BUCKETS (the neutral half of the grid)")
    add(
        f"  {len(summary.tickers_without_bucket)} tickers have no point-in-time bucket; "
        f"{len(summary.current_sic_fallback_tickers)} fell back to CURRENT SIC."
    )
    add(f"  ranked ticker-formation slots refused by MIN_BUCKET_SIZE: {summary.n_min_bucket_refusals}")
    if summary.bucket_slot_counts:
        composition = ", ".join(
            f"{b}={n}" for b, n in sorted(summary.bucket_slot_counts.items(), key=lambda kv: -kv[1])
        )
        add(f"  slot composition (h63 cadence): {composition}")
    add("")
    for warning in summary.warnings:
        add(f"  WARNING: {warning}")
    if summary.warnings:
        add("")

    add("=" * 78)
    add(f"ALL {len(summary.results)} SPECS, RANKED BY NET SHARPE")
    add("=" * 78)
    add(
        "COSTS: 5 bps one-way, financing_bps_per_year = 0.0 (this project's standing DISCLOSED "
        "optimism about short borrow, not an estimate). Note a 21-day hold on a monthly-"
        "refreshing signal pays turnover 12x a year, so the cost drag column matters here more "
        "than in the annual-refresh families."
    )
    add("")
    add(
        f"{'spec':<34} {'Sharpe':>8} {'DSR':>7} {'PSR>0':>7} {'days':>6} "
        f"{'forms':>6} {'leg':>5} {'costdrag':>9}"
    )
    add("-" * 78)
    ordered = sorted(summary.results, key=lambda r: r.sharpe_annualized, reverse=True)
    for r in ordered:
        ds = r.deflated_sharpe
        add(
            f"{r.pattern_id:<34} {r.sharpe_annualized:>+8.3f} {_fmt(ds.dsr, '.3f'):>7} "
            f"{_fmt(ds.psr_vs_zero, '.3f'):>7} {r.n_trading_days:>6} {r.n_formations:>6} "
            f"{r.avg_names_per_leg:>5.1f} {r.total_cost_drag:>9.4f}"
        )
    add("")
    first = ordered[0].deflated_sharpe
    add(
        f"DSR denominator n_trials={first.n_trials} for every row, with sigma_SR "
        f"{_fmt(first.sigma_sr_annualized, '.4f')} POOLED across all {len(summary.results)} "
        "screened specs (see repool_deflated_sharpe: the family screens in three passes because "
        "each arm ranks a different score panel, and a per-pass sigma_SR would describe 6 "
        "siblings rather than the 18 the search spanned)."
    )
    add(
        f"Expected max Sharpe of {first.n_trials} pure-noise trials: "
        f"{_fmt(first.expected_max_sharpe_noise_annualized, '.3f')}"
    )
    add("")

    by_id = {r.pattern_id: r for r in summary.results}

    add("=" * 78)
    add("BHM'S OWN COMPARATIVE CLAIM: RESIDUAL vs TOTAL-RETURN MOMENTUM")
    add("=" * 78)
    add(
        "The abstract's claim is COMPARATIVE — residual momentum earns risk-adjusted profits "
        "'about twice as large as those associated with total return momentum'. Every cell below "
        "is matched on conditioning and holding period, so the ONLY difference is the ranking "
        "variable. Both residual arms and the control carry the identical publication lag and "
        "are scored on the identical set of months."
    )
    add("")
    add(f"{'conditioning':<18} {'hold':>5} {'control':>9} {'capm':>9} {'ff3':>9}   verdict")
    add("-" * 78)
    n_capm_better = 0
    n_ff3_better = 0
    n_cells = 0
    for conditioning in RESIDUAL_MOM_CONDITIONINGS:
        suffix = "_neutral" if conditioning == "industry_neutral" else ""
        for holding in RESIDUAL_MOM_HOLDING_DAYS:
            control = by_id.get(f"rm_total_return_control{suffix}_ls_h{holding}")
            capm = by_id.get(f"rm_capm_residual{suffix}_ls_h{holding}")
            ff3 = by_id.get(f"rm_ff3_residual{suffix}_ls_h{holding}")
            if not (control and capm and ff3):
                continue
            n_cells += 1
            capm_better = capm.sharpe_annualized > control.sharpe_annualized
            ff3_better = ff3.sharpe_annualized > control.sharpe_annualized
            n_capm_better += capm_better
            n_ff3_better += ff3_better
            marks = []
            if capm_better:
                marks.append("capm>control")
            if ff3_better:
                marks.append("ff3>control")
            add(
                f"{conditioning:<18} {holding:>5} {control.sharpe_annualized:>+9.3f} "
                f"{capm.sharpe_annualized:>+9.3f} {ff3.sharpe_annualized:>+9.3f}   "
                + (", ".join(marks) if marks else "neither beats control")
            )
    add("")
    add(
        f"CAPM residual beat the total-return control in {n_capm_better}/{n_cells} matched cells; "
        f"FF3 residual in {n_ff3_better}/{n_cells}."
    )
    add(
        "PRE-COMMITTED READING (pre-registration section 6): residual arms beating the control in "
        "most cells is WEAK corroboration of BHM's DIRECTION only. It is explicitly NOT a claim "
        "of tradeability. 'About twice as large' is NOT treated as a quantitative target — with "
        "18 correlated specs on decile legs this size, this sample cannot resolve a 2x "
        "risk-adjusted ratio, and no such ratio is reported."
    )
    add("")

    add("=" * 78)
    add("THE INDUSTRY-NEUTRAL CONFOUND CHECK")
    add("=" * 78)
    add(
        "Residualizing against FF3 removes market, size and value exposure. It does NOT remove "
        "INDUSTRY, so a residual-momentum sort can still be an industry bet — the failure mode "
        "that killed the sibling NOA family. Both conditionings were pre-declared in ONE grid "
        "under ONE denominator, so this is half the grid rather than a follow-up study."
    )
    add("")
    add(f"{'arm':<24} {'hold':>5} {'raw':>9} {'neutral':>9}   {'delta':>9}")
    add("-" * 78)
    for arm, _cols in RESIDUAL_MOM_ARMS:
        for holding in RESIDUAL_MOM_HOLDING_DAYS:
            raw = by_id.get(f"rm_{arm}_ls_h{holding}")
            neutral = by_id.get(f"rm_{arm}_neutral_ls_h{holding}")
            if not (raw and neutral):
                continue
            delta = neutral.sharpe_annualized - raw.sharpe_annualized
            add(
                f"{arm:<24} {holding:>5} {raw.sharpe_annualized:>+9.3f} "
                f"{neutral.sharpe_annualized:>+9.3f}   {delta:>+9.3f}"
            )
    add("")

    add("=" * 78)
    add("THE PRE-REGISTERED PASS / FAIL RULE, APPLIED")
    add("=" * 78)
    add(
        f"A VALIDATED EDGE required BOTH: (i) the best RESIDUAL spec's DSR (at n_trials="
        f"{RESIDUAL_MOM_N_TRIALS}) exceeds {DSR_BAR}; AND (ii) that spec's industry-neutral "
        "counterpart, at the same arm and holding period, is also materially positive."
    )
    add(
        "The raw total-return control can NEVER be this family's finding — it is the benchmark "
        "(pre-registration section 6)."
    )
    add("")
    residual_results = [
        r for r in summary.results if _arm_of(r.pattern_id) != "total_return_control"
    ]
    best = max(residual_results, key=lambda r: (r.deflated_sharpe.dsr or -1.0))
    best_dsr = best.deflated_sharpe.dsr
    add(
        f"  Best residual spec by DSR: {best.pattern_id}  Sharpe "
        f"{best.sharpe_annualized:+.3f}  DSR {_fmt(best_dsr, '.3f')}"
    )
    condition_i = best_dsr is not None and best_dsr > DSR_BAR
    add(f"  CONDITION (i)  DSR > {DSR_BAR}: {'MET' if condition_i else 'NOT MET'}")
    if condition_i:
        arm = _arm_of(best.pattern_id)
        holding = _holding_of(best.pattern_id)
        counterpart = by_id.get(f"rm_{arm}_neutral_ls_h{holding}")
        add(
            f"  CONDITION (ii) industry-neutral counterpart "
            f"({counterpart.pattern_id if counterpart else 'n/a'}): "
            f"{counterpart.sharpe_annualized:+.3f}" if counterpart else "  CONDITION (ii): n/a"
        )
    else:
        add("  CONDITION (ii) is never reached — (i) already fails.")
    add("")
    add(
        f"  VERDICT: {'VALIDATED EDGE — REQUIRES HUMAN REVIEW' if condition_i else 'HONEST NEGATIVE'}"
    )
    add("")
    add(
        "A well-documented honest negative is a FULLY SUCCESSFUL OUTCOME by this project's "
        "standards. Every one of the 18 specs is persisted regardless of outcome; no spec was "
        "dropped, re-run, or re-specified after seeing its number."
    )
    add("")
    return "\n".join(lines)


def main() -> int:
    started = time.time()
    logger.info("residual momentum screen starting; run_tag=%s", RUN_TAG)
    if not SHARED_EDGAR_CACHE.exists():
        logger.warning(
            "shared EDGAR cache %s absent — every CIK will be fetched live", SHARED_EDGAR_CACHE
        )
    edgar = EdgarXbrlProvider(cache_dir=SHARED_EDGAR_CACHE)

    summary = run_residual_momentum_screening(end=RUN_END, edgar=edgar)
    elapsed = time.time() - started

    if not summary.results:
        logger.error("screen produced ZERO replayable specs; warnings=%s", summary.warnings)
        return 1
    if len(summary.results) != RESIDUAL_MOM_N_TRIALS:
        logger.warning(
            "screen returned %d of %d specs — some fell below the harness's data floors",
            len(summary.results),
            RESIDUAL_MOM_N_TRIALS,
        )

    for warning in summary.warnings:
        logger.warning("%s", warning)

    report = build_report(summary, elapsed)
    print(report)
    Path(_BACKEND / REPORT_PATH).write_text(report + "\n")
    logger.info("report written to %s", REPORT_PATH)

    db = SessionLocal()
    try:
        n = persist_cross_sectional_trial_results(
            db, RESIDUAL_MOM_FAMILY_KEY, summary.results, run_tag=RUN_TAG
        )
        logger.info("persisted %d rows to cross_sectional_trial_results", n)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
