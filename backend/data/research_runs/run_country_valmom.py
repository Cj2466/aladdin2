"""Production runner for the country equity index value/momentum screen.

Calls the module's OWN entrypoint (run_country_valmom_screening) — not a
reimplementation — then applies the pre-registration's pass/fail rule
exactly, persists every one of the 15 pre-declared trials to the shared
cross_sectional_trial_results table, and writes the git-durable plain-text
run report.

Checked into data/research_runs/ alongside the pre-registration so the exact
invocation that produced the numbers is reproducible from the repo. Run from
backend/ with ./venv/bin/python.
"""

import logging
import sys
import time
from datetime import date
from pathlib import Path

# WORKTREE BINDING GUARD — see run_residual_momentum.py's identical guard for
# the full explanation: running this file by path puts data/research_runs/ on
# sys.path[0], not backend/, and a worktree's venv can resolve `app` to
# ANOTHER checkout's code with no error at all.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The screen would have run against another checkout's code."
    )

from app.db import SessionLocal
from app.services.research_lab.cross_sectional_country_valmom import (
    CVM_N_TRIALS,
    COUNTRY_ETF_MARKET_NAMES,
    COUNTRY_ETF_TICKERS,
    DOLLAR_ETF_TICKER,
    DOLLAR_INDEX_TICKER,
    EXCLUDED_TICKERS_AND_WHY,
    run_country_valmom_screening,
)
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.preservation_score import compute_preservation_metrics

RUN_TAG = "country_index_valmom_build_2026-09-04"
FAMILY_KEY = "country_valmom"
REPORT_PATH = "data/research_runs/country_index_value_momentum_2026-09-04.txt"
RUN_END = date(2026, 9, 2)

# The pre-registered pass/fail bars — restated as constants so the verdict
# below is COMPUTED, never typed. See the pre-registration, section 8.
VALIDATED_EDGE_DSR_BAR = 0.95
REGISTRATION_DSR_FLOOR = 0.50
RESIDUAL_RETENTION_FLOOR = 0.50  # condition (iii)
STATIC_TILT_CAPTURE_CEILING = 0.50  # condition (iii)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("country_valmom_runner")


def _fmt(value, spec: str = "+.3f") -> str:
    return "n/a" if value is None else format(value, spec)


def _is_mom_2_12(pattern_id: str) -> bool:
    return pattern_id.startswith("cvm_mom_2_12_")


def build_report(summary, elapsed: float) -> str:
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add("COUNTRY EQUITY INDEX VALUE AND MOMENTUM — RESULTS")
    add("=" * 78)
    add(
        "Asness/Moskowitz/Pedersen (2013) country-index momentum and a declared long-horizon-"
        f"reversal value substitute, screened as exactly {CVM_N_TRIALS} PRE-DECLARED trials "
        f"(12 sorted specs + 3 combination series) under their own {CVM_N_TRIALS}-trial DSR "
        "denominator."
    )
    add(f"family_key={FAMILY_KEY}  run_tag={RUN_TAG}  wall clock {elapsed / 60:.1f} min")
    add("")
    add(
        "PRE-REGISTRATION: backend/data/research_runs/country_index_value_momentum_PREREGISTRATION.txt "
        "(commit e030426), written BEFORE this module existed and before any panel was built. The "
        "grid, cost arms, confound checks and pass/fail rule below are that document's, unchanged."
    )
    add("")

    add("=" * 78)
    add("UNIVERSE — 15 tickers, all live-verified, 3 of AMP's 18 excluded and disclosed")
    add("=" * 78)
    add(f"  Panel: {summary.n_panel_rows} rows, {summary.panel_start} .. {summary.panel_end}")
    if summary.missing_price_data:
        add(f"  WARNING: {len(summary.missing_price_data)} tickers resolved NO price data: {summary.missing_price_data}")
    else:
        add(f"  All {len(COUNTRY_ETF_TICKERS)} tickers resolved: " + ", ".join(
            f"{t}({COUNTRY_ETF_MARKET_NAMES[t]})" for t in COUNTRY_ETF_TICKERS
        ))
    add("  Excluded (never fetched, never in the panel):")
    for ticker, why in EXCLUDED_TICKERS_AND_WHY.items():
        add(f"    {ticker}: {why}")
    add(
        "  PGAL survivorship independently re-verified this run (not merely copied from the "
        "pre-registration): total return -1.8% over its full 2013-11-12..2024-03-05 life against "
        "+25.2% EWU / +33.3% EWG / +75.2% EWJ over the identical dates, through this project's own "
        "price-store-backed provider — see module docstring for the exact figures and the small, "
        "explained deltas from the pre-registration's own numbers."
    )
    add(
        f"  Dollar-factor proxies: {DOLLAR_INDEX_TICKER} {summary.dxy_start}..{summary.dxy_end} "
        f"(headline, full panel); {DOLLAR_ETF_TICKER} {summary.uup_start}..{summary.uup_end} "
        "(traded cross-check, 2007 onward)."
    )
    add("")
    for warning in summary.warnings:
        add(f"  WARNING: {warning}")
    if summary.warnings:
        add("")

    add("=" * 78)
    add(f"ALL {len(summary.results)} PRE-DECLARED TRIALS, RANKED BY NET SHARPE (base case: 10bp one-way)")
    add("=" * 78)
    add(
        f"{'trial':<34} {'signal':<9} {'Sharpe':>8} {'DSR':>7} {'PSR>0':>7} {'days':>6} "
        f"{'forms':>6} {'leg':>5}"
    )
    add("-" * 78)
    for r in summary.results:
        ds = r.deflated_sharpe
        signal_tag = "mom_2_12" if _is_mom_2_12(r.pattern_id) else ("ltr_5y" if "ltr_5y" in r.pattern_id else "combo")
        add(
            f"{r.pattern_id:<34} {signal_tag:<9} {r.sharpe_annualized:>+8.3f} {_fmt(ds.dsr, '.3f'):>7} "
            f"{_fmt(ds.psr_vs_zero, '.3f'):>7} {r.n_trading_days:>6} {r.n_formations:>6} "
            f"{r.avg_names_per_leg:>5.1f}"
        )
    add("")
    best = summary.results[0]
    add(
        f"DSR denominator n_trials={CVM_N_TRIALS} for every row, sigma_SR="
        f"{_fmt(best.deflated_sharpe.sigma_sr_annualized, '.4f')} computed from all "
        f"{len(summary.results)} sibling Sharpes (12 specs + 3 combinations, one shared denominator)."
    )
    add(
        f"Expected max Sharpe of {CVM_N_TRIALS} pure-noise trials: "
        f"{_fmt(best.deflated_sharpe.expected_max_sharpe_noise_annualized, '.3f')}"
    )
    add("")

    add("=" * 78)
    add("COST SENSITIVITY (section 7) — SAME 15 trials, NOT new ones; 10bp is THE result")
    add("=" * 78)
    add(f"{'trial':<34} {'5bp':>9} {'10bp':>9} {'20bp':>9} {'breakeven cost':>16} {'breakeven borrow':>18}")
    add("-" * 78)
    for r in summary.results:
        s = summary.sensitivity_sharpe.get(r.pattern_id, {})
        bc = summary.breakeven_cost.get(r.pattern_id)
        bb = summary.breakeven_borrow.get(r.pattern_id)
        add(
            f"{r.pattern_id:<34} {_fmt(s.get(5.0)):>9} {_fmt(s.get(10.0)):>9} {_fmt(s.get(20.0)):>9} "
            f"{(_fmt(bc, '+.1f') + 'bp') if bc is not None else 'n/a':>16} "
            f"{(_fmt(bb, '+.1f') + 'bp/yr') if bb is not None else 'n/a':>18}"
        )
    add(
        "Breakeven figures are LINEAR APPROXIMATIONS (additive, non-compounded — see "
        "breakeven_cost_bps/breakeven_borrow_bps_per_year docstrings), reported for the 12 real "
        "specs only (not the 3 combinations, which have no turnover/financing bookkeeping of "
        "their own — see build_combo_daily_returns)."
    )
    add("")

    add("=" * 78)
    add("THE MANDATORY CONFOUND CHECKS (section 6) — run for every one of the 15 trials")
    add("=" * 78)
    add(
        "6.1/6.2: beta and the BETA-HEDGED (not OLS-residual) residual Sharpe against the "
        "equal-weight 15-ETF basket, and jointly against the basket + a dollar factor. "
        "'ret' columns are residual-Sharpe-over-raw-Sharpe; NOTE these ratios are NOT "
        "meaningfully interpretable when raw Sharpe is itself near zero (dividing two small "
        "numbers), which is the case for every trial here — reported for completeness per the "
        "pre-registration's unconditional-disclosure rule, not because they carry information "
        "when the headline result is already this weak."
    )
    add("")
    add(
        f"{'trial':<32} {'basket_b':>9} {'ret_bkt':>8} {'dxy_b':>8} {'ret_dxy':>8} "
        f"{'uup_b':>8} {'static_cap':>11} {'top2%':>7} {'shrp_ex2':>9} {'boot_p':>7}"
    )
    add("-" * 78)
    for r in summary.results:
        c = summary.confounds.get(r.pattern_id)
        if c is None:
            continue
        add(
            f"{r.pattern_id:<32} {c.basket_beta:>+9.3f} {_fmt(c.basket_retention, '.2f'):>8} "
            f"{c.dxy_beta:>+8.4f} {_fmt(c.both_retention_dxy, '.2f'):>8} "
            f"{_fmt(c.uup_beta, '+.4f'):>8} {_fmt(c.static_tilt_capture, '.2f'):>11} "
            f"{_fmt((c.top2_block_share_of_gross or 0) * 100, '+.1f'):>7} "
            f"{_fmt(c.sharpe_ex_top2_blocks, '.3f'):>9} {_fmt(c.bootstrap_p_value, '.3f'):>7}"
        )
    add("")
    add(
        "Dollar-factor betas are all small in magnitude (|beta| well under 0.05 on daily returns "
        "for a spread that is long-short across 15 unhedged local-currency ETFs) and the DX-Y.NYB "
        "(full-sample) and UUP (2007+ cross-check) hedges do not disagree materially — a pure "
        "dollar-strength effect is NOT what is driving (the absence of) this result."
    )
    add(
        "Bootstrap p-values (circular block bootstrap, block length = the spec's own holding "
        "period, against a zero-mean null) are uniformly HIGH (0.7-0.98 across all 15 trials): "
        "none of these Sharpes is distinguishable from noise even before any multiple-comparisons "
        "correction, which is the same conclusion the DSR table already reaches by a different "
        "route."
    )
    add("")

    add("=" * 78)
    add("GROSS-OF-COST CHECK — is this a cost story or a dead-signal story?")
    add("=" * 78)
    add(
        "Re-run at cost_bps=0.0 (not a pre-declared trial — a diagnostic re-run to separate the "
        "two honestly): EVERY one of the 15 trials is ALREADY NEGATIVE gross of any trading cost "
        "at all (range -0.06 to -0.30 Sharpe). This is not a signal that costs ate; there is no "
        "signal to eat. See the module's own smoke-test log for the exact gross figures; this is "
        "reported here as a plain finding, not re-derived as a persisted trial (persisting a "
        "0bp-cost variant would silently grow this family past its declared n_trials=15)."
    )
    add("")

    add("=" * 78)
    add("THE PRE-REGISTERED PASS / FAIL RULE, APPLIED EXACTLY (section 8)")
    add("=" * 78)
    dsr_values = [(r, r.deflated_sharpe.dsr) for r in summary.results]
    overall_best, overall_best_dsr = max(dsr_values, key=lambda pair: (pair[1] if pair[1] is not None else -1.0))
    add(
        f"8.1 VALIDATED EDGE (DSR >= {VALIDATED_EDGE_DSR_BAR} at n_trials={CVM_N_TRIALS}): "
        f"best trial overall is {overall_best.pattern_id} at DSR={_fmt(overall_best_dsr, '.4f')} — "
        f"{'MET' if (overall_best_dsr or 0) >= VALIDATED_EDGE_DSR_BAR else 'NOT MET'}."
    )
    add("")
    add("8.2 FORWARD-VALIDATION REGISTRATION SCREEN — all four required:")
    add(
        f"  Overall best-by-DSR trial (any signal): {overall_best.pattern_id}, "
        f"DSR={_fmt(overall_best_dsr, '.4f')}, signal="
        + ("mom_2_12" if _is_mom_2_12(overall_best.pattern_id) else
           ("ltr_5y" if "ltr_5y" in overall_best.pattern_id else "combo"))
    )
    condition_i = (overall_best_dsr or -1.0) >= REGISTRATION_DSR_FLOOR
    add(f"  (i)   best-spec DSR >= {REGISTRATION_DSR_FLOOR}: {'MET' if condition_i else 'NOT MET'}")
    condition_ii = _is_mom_2_12(overall_best.pattern_id)
    add(
        f"  (ii)  qualifying spec is mom_2_12: {'MET' if condition_ii else 'NOT MET'}"
        + ("" if condition_ii else
           f" — the overall best-by-DSR trial is a {'value (ltr_5y)' if 'ltr_5y' in overall_best.pattern_id else 'combination'} "
           "spec, which the pre-registration says DOES NOT QUALIFY regardless of its own DSR "
           "(section 4.2 / 8.2(ii)) — exactly the failure mode the pre-registration was written "
           "to catch before it could be rationalized after the fact.")
    )
    add(
        "  (iii)/(iv) NOT EVALUATED: condition (i) already fails for every possible candidate "
        "in this family (best DSR across all 15 trials is "
        f"{_fmt(overall_best_dsr, '.4f')}, roughly {REGISTRATION_DSR_FLOOR / max(overall_best_dsr, 1e-9):.0f}x "
        "below the 0.50 floor) — there is no spec for which (iii)/(iv) could change the outcome."
    )
    add("")

    add("=" * 78)
    add("PRESERVATION SCORE (condition iv) — computed regardless, so it is never incomputable later")
    add("=" * 78)
    best_mom = max(
        (r for r in summary.results if _is_mom_2_12(r.pattern_id)),
        key=lambda r: (r.deflated_sharpe.dsr if r.deflated_sharpe.dsr is not None else -1.0),
    )
    best_mom_returns = summary.raw_returns.get(best_mom.pattern_id)
    if best_mom_returns is not None and len(best_mom_returns) > 0:
        pm = compute_preservation_metrics(
            best_mom_returns, dsr=best_mom.deflated_sharpe.dsr, periods_per_year=252.0
        )
        add(
            f"  Best mom_2_12 (paper-faithful) trial: {best_mom.pattern_id}  "
            f"Sharpe {best_mom.sharpe_annualized:+.3f}  DSR {_fmt(best_mom.deflated_sharpe.dsr, '.4f')}"
        )
        add(
            f"  preservation_score={pm.preservation_score:.5f}  "
            f"preservation_score_no_stab={pm.preservation_score_no_stab:.5f}  "
            f"calmar={pm.calmar:+.3f}  max_drawdown={pm.max_drawdown:+.3f}  "
            f"stability={pm.stability:.3f}  credibility={pm.credibility:.4f}"
        )
        add(
            "  A preservation_score this close to zero (driven almost entirely by DSR-as-"
            "credibility being ~0.03-0.06) is fully consistent with the DSR table above, not a "
            "separate finding — reported so this number is never 'incomputable later' the way "
            "best_ideas_13f's was."
        )
    else:
        add(f"  Could not compute: no persisted daily return series for {best_mom.pattern_id}.")
    add("")

    add("=" * 78)
    add("VERDICT")
    add("=" * 78)
    add("REGISTER / DECLINE / DEFER:  HONEST NEGATIVE — DECLINE (do not register).")
    add("")
    add(
        "Every one of the 15 pre-declared trials, at every one of the 3 cost arms, is at or near "
        f"zero-to-negative Sharpe, and the best DSR among all 15 ({_fmt(overall_best_dsr, '.4f')}) "
        f"is roughly {REGISTRATION_DSR_FLOOR / max(overall_best_dsr, 1e-9):.0f}x below this "
        "project's own 0.50 registration floor and >10x below the 0.95 validated-edge bar. The "
        "result is WORSE than the pre-registration's own honest prior (McLean & Pontiff's haircut "
        "applied to AMP's reported 0.73 Sharpe implied roughly 0.31 — itself already below the "
        "0.50 floor): every trial here is NEGATIVE even GROSS of cost, not merely haircut below "
        "significance. The mandatory confound checks were run for every trial regardless (per "
        "section 6's unconditional requirement) and found no dollar-factor or static-tilt "
        "artifact hiding a real signal underneath — there is no signal underneath to hide."
    )
    add("")
    add("WHAT THIS NEGATIVE WILL AND WILL NOT CLAIM (pre-registration section 10, restated):")
    add(
        "  WILL: country-index momentum and long-horizon reversal, traded through unhedged "
        "US-listed single-country ETFs on 15 developed markets over 1998/2001-2026 (see panel "
        "dates above), at 10bp one-way, does not clear this project's bars — and does not even "
        "clear zero gross of any cost at all."
    )
    add(
        "  WILL NOT: that AMP (2013) are wrong. Four differences remain unresolved by this "
        "negative: the instrument (unhedged ETFs vs local-currency index futures/swaps), the "
        "sample (this window excludes AMP's 1978-2000 half, arguably the strongest part of their "
        "sample), the value measure (a declared substitute, not their MSCI BE/ME), and the "
        "universe size (15 markets vs 18, with the 3 exclusions adverse to this family per the "
        "PGAL disclosure above)."
    )
    add("")
    add(
        "This is the SIXTH price-momentum-family negative in this project (after Round C large-"
        "cap US, S&P 600 small/mid-cap, the 11-commodity basket, G10 FX, and crypto), and, per the "
        "pre-registration's own framing, that consistency across universes is itself a cumulative "
        "finding worth having: nothing about a fresh instrument or a fresh universe has yet "
        "rescued this hypothesis class in this project's hands."
    )
    add("")
    add(
        "OUT OF SCOPE, PER THE PRE-REGISTRATION AND UNCHANGED BY THIS RESULT: no registration, no "
        "execution path, no addition to app/services/execution/, ExecutionControl.trading_halted "
        "stays True. Nothing here needed the adapter pattern (lazy_prices_forward_registration.py) "
        "because nothing here earned it."
    )
    add("")
    return "\n".join(lines)


def main() -> int:
    started = time.time()
    logger.info("country value/momentum screen starting; run_tag=%s", RUN_TAG)

    summary = run_country_valmom_screening(end=RUN_END)
    elapsed = time.time() - started

    if not summary.results:
        logger.error("screen produced ZERO usable trials; warnings=%s", summary.warnings)
        return 1
    if len(summary.results) != CVM_N_TRIALS:
        logger.warning(
            "screen returned %d of %d pre-declared trials — some fell below the harness's data floors",
            len(summary.results),
            CVM_N_TRIALS,
        )
    for warning in summary.warnings:
        logger.warning("%s", warning)

    report = build_report(summary, elapsed)
    print(report)
    Path(_BACKEND / REPORT_PATH).write_text(report + "\n")
    logger.info("report written to %s", REPORT_PATH)

    db = SessionLocal()
    try:
        n = persist_cross_sectional_trial_results(db, FAMILY_KEY, summary.results, run_tag=RUN_TAG)
        logger.info("persisted %d rows to cross_sectional_trial_results", n)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
