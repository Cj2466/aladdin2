"""Production runner for the Inelastic-Markets family (candidate #16).

Runs the pre-registered gates (G1 partition integrity, G2 multiplier
replication, G3 recursive no-look-ahead), then the 24 pre-declared specs across
three cost arms, then persists every baseline-arm result to a real DB row and
writes the committed JSON/TXT reports.

Pre-registration: data/research_runs/gabaix_koijen_inelastic_PREREGISTRATION.txt
(commit a1b1df9, written before any strategy return existed).

Usage:  python3 data/research_runs/run_inelastic_markets.py
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.db import SessionLocal
from app.services.research_lab.cross_sectional_persistence import (
    describe_configured_database,
    persist_cross_sectional_trial_results,
    verify_persisted_trial_results,
)
from app.services.research_lab.deflated_sharpe import (
    compute_deflated_sharpe,
)
from app.services.research_lab.inelastic_markets_timing import (
    AVAILABILITY_LAG_QUARTERS,
    GIV_PANEL_START,
    GK_PAPER_SAMPLE,
    HOLDER_SERIES,
    INELASTIC_COST_BPS,
    INELASTIC_N_TRIALS,
    QUARTERS_PER_YEAR,
    VALIDATED_EDGE_BAR,
    Z1_PUBLICATION_LAG_DAYS,
    SpecResult,
    build_dq_panel,
    check_partition_integrity,
    dsr_across_denominators,
    estimate_multiplier,
    giv_panel_coverage,
    instrument_sectors,
    load_real_gdp_growth,
    load_z1_holdings,
    market_price_return_quarterly,
    policy_d_denominators,
    quarterly_market_excess,
    recursive_giv,
    replay_spec,
    select_giv_sectors,
    spec_grid,
    verdict_from_dsr,
)
from app.services.research_lab.metrics import sharpe_ratio
from app.services.research_lab.preservation_score import (
    compute_preservation_metrics,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("inelastic_markets")

FAMILY_KEY = "inelastic_markets"
RUN_TAG = f"production_{date.today().isoformat()}"
OUT_DIR = Path(__file__).resolve().parent

CITATION = (
    "Gabaix & Koijen, 'In Search of the Origins of Financial Fluctuations: The "
    "Inelastic Markets Hypothesis', NBER WP 28967 (2021), Appendix B.2 eqs. (67)-(69)"
)
HYPOTHESIS = (
    "The granular aggregate equity-flow shock Z_t, lagged two full quarters to real "
    "publication availability, predicts the subsequent quarterly excess return of the "
    "US market. NOTE: [GK21] itself predicts this is FALSE -- its price impact is "
    "permanent, so a null CONFIRMS the paper rather than refuting it."
)

COST_ARMS: tuple[tuple[str, float], ...] = (
    ("gross", 0.0),
    ("baseline", INELASTIC_COST_BPS),
    ("stress", 10.0),
)
BASELINE_ARM = "baseline"


def main() -> None:
    report: dict[str, object] = {
        "family_key": FAMILY_KEY,
        "run_tag": RUN_TAG,
        "citation": CITATION,
        "hypothesis": HYPOTHESIS,
        "preregistration": "data/research_runs/gabaix_koijen_inelastic_PREREGISTRATION.txt",
        "z1_publication_lag_days": Z1_PUBLICATION_LAG_DAYS,
        "availability_lag_quarters": AVAILABILITY_LAG_QUARTERS,
    }

    # ---------------- data ----------------
    wide = load_z1_holdings()
    gdp = load_real_gdp_growth()
    sectors = select_giv_sectors(wide, GIV_PANEL_START)
    dq, shares = build_dq_panel(wide, sectors, GIV_PANEL_START)
    logger.info("Z.1 panel %s, %d admitted sectors", dq.shape, len(sectors))

    # ---------------- GATE G1 ----------------
    g1 = check_partition_integrity(wide)
    report["gate_g1_partition_integrity"] = g1
    logger.info("G1 passed=%s median_abs_rel=%.5f", g1["passed"], g1["median_abs_rel_discrepancy"])
    if not g1["passed"]:
        report["stopped"] = "GATE G1 FAILED -- sector partition is wrong; family stops here."
        (OUT_DIR / f"inelastic_markets_{date.today().isoformat()}.json").write_text(
            json.dumps(report, indent=2, default=str)
        )
        raise SystemExit("G1 failed")

    coverage = giv_panel_coverage(wide, sectors)
    coverage["admitted_sectors"] = [HOLDER_SERIES[c] for c in sectors]
    coverage["excluded_sectors"] = [HOLDER_SERIES[c] for c in HOLDER_SERIES if c not in sectors]
    coverage["instrument_sectors_excl_corporate"] = len(instrument_sectors(sectors))
    report["giv_panel_coverage"] = coverage

    # ---------------- GATE G2 ----------------
    market_price = market_price_return_quarterly()
    g2: dict[str, object] = {
        "sample": list(GK_PAPER_SAMPLE),
        "paper_table2": {"1_pc": 7.08, "2_pc": 5.28},
        "paper_robustness_range": [3.5, 8.0],
        "estimates": {},
    }
    for n_pcs in (1, 2):
        g2["estimates"][f"{n_pcs}_pc"] = estimate_multiplier(
            dq, shares, market_price, gdp, n_pcs
        )
    g2["passed"] = any(
        bool(v.get("in_paper_robustness_range")) for v in g2["estimates"].values()
    )
    report["gate_g2_mechanism_fidelity"] = g2
    logger.info(
        "G2 passed=%s  M(1pc)=%.3f M(2pc)=%.3f (paper 7.08 / 5.28)",
        g2["passed"],
        g2["estimates"]["1_pc"]["multiplier"],
        g2["estimates"]["2_pc"]["multiplier"],
    )

    # sensitivity, run AFTER the registered G2 and labelled as such
    sens = {}
    for start in ("1994Q1", "1995Q1"):
        s_sec = select_giv_sectors(wide, start)
        s_dq, s_sh = build_dq_panel(wide, s_sec, start)
        sens[start] = {
            "n_sectors": len(s_sec),
            "etfs_included": "LM563064100.Q" in s_sec,
            "coverage_median": giv_panel_coverage(wide, s_sec)["coverage_share_median"],
            "multipliers": {
                f"{p}_pc": estimate_multiplier(s_dq, s_sh, market_price, gdp, p)["multiplier"]
                for p in (1, 2)
            },
        }
    report["gate_g2_sensitivity_post_hoc"] = {
        "note": (
            "Run AFTER seeing the registered G2 fail, to check whether the ETF "
            "exclusion forced by the 1993Q1 start explained the gap. It does not."
        ),
        "variants": sens,
    }

    # ---------------- GATE G3 + the tradable signal ----------------
    market_excess = quarterly_market_excess()
    report["market_excess_span"] = [str(market_excess.index[0]), str(market_excess.index[-1])]

    z_by_pcs: dict[int, pd.Series] = {}
    for n_pcs in (1, 2):
        logger.info("building recursive GIV (no-look-ahead) for n_pcs=%d ...", n_pcs)
        z_by_pcs[n_pcs] = recursive_giv(dq, shares, gdp, n_pcs)
    report["gate_g3_recursive"] = {
        "note": (
            "pseudo-equal weights, the eq.(67) panel regression and the PCA are ALL "
            "refit on data through the decision date only"
        ),
        "n_recursive_quarters": {str(k): len(v) for k, v in z_by_pcs.items()},
    }

    # ---------------- the 24 specs x 3 cost arms ----------------
    grid = spec_grid()
    assert len(grid) == INELASTIC_N_TRIALS, f"grid is {len(grid)}, must be {INELASTIC_N_TRIALS}"
    denominators = policy_d_denominators(INELASTIC_N_TRIALS)
    report["dsr_denominators"] = denominators
    logger.info("DSR ladder: %s", denominators)

    bench_sharpe = sharpe_ratio(market_excess, periods_per_year=QUARTERS_PER_YEAR)
    report["buy_and_hold_sharpe"] = bench_sharpe

    all_results: dict[str, list[SpecResult]] = {}
    for arm_name, cost_bps in COST_ARMS:
        replays: dict[str, dict] = {}
        for n_pcs, std, rule, hold in grid:
            spec_id = f"pcs{n_pcs}_{std}_{rule}_{hold}"
            replays[spec_id] = replay_spec(
                z_by_pcs[n_pcs], market_excess, std, rule, hold, cost_bps
            )

        overlay_sharpes = {
            sid: sharpe_ratio(r["overlay"], periods_per_year=QUARTERS_PER_YEAR)
            for sid, r in replays.items()
            if not r["empty"]
        }
        sigma_sr = (
            float(np.std(list(overlay_sharpes.values()), ddof=1))
            if len(overlay_sharpes) >= 2
            else None
        )

        arm_results: list[SpecResult] = []
        for (n_pcs, std, rule, hold) in grid:
            spec_id = f"pcs{n_pcs}_{std}_{rule}_{hold}"
            r = replays[spec_id]
            if r["empty"]:
                logger.warning("spec %s produced no observations", spec_id)
                continue
            overlay = r["overlay"]
            strategy = r["strategy"]
            sharpe = overlay_sharpes[spec_id]
            dsr_by_n = dsr_across_denominators(sharpe, overlay, sigma_sr, denominators)
            deflated = compute_deflated_sharpe(
                sharpe,
                overlay,
                INELASTIC_N_TRIALS,
                sigma_sr,
                periods_per_year=QUARTERS_PER_YEAR,
            )
            pres = compute_preservation_metrics(
                overlay, dsr=deflated.dsr, periods_per_year=QUARTERS_PER_YEAR
            )
            arm_results.append(
                SpecResult(
                    spec_id=spec_id,
                    n_pcs=n_pcs,
                    standardization=std,
                    position_rule=rule,
                    holding=hold,
                    cost_arm=arm_name,
                    citation=CITATION,
                    hypothesis=HYPOTHESIS,
                    n_trading_days=len(overlay),
                    first_quarter=str(overlay.index[0]),
                    last_quarter=str(overlay.index[-1]),
                    sharpe_annualized=sharpe,
                    strategy_sharpe=sharpe_ratio(
                        strategy, periods_per_year=QUARTERS_PER_YEAR
                    ),
                    buy_and_hold_sharpe=bench_sharpe,
                    dsr_by_n=dsr_by_n,
                    preservation=asdict(pres),
                    net_cumulative_overlay_return=float(np.prod(1.0 + overlay.to_numpy()) - 1.0),
                    total_cost_drag=r["cost_drag"],
                    total_turnover=r["turnover"],
                    mean_weight=float(r["weight"].mean()),
                    n_switches=r["n_switches"],
                    verdict=verdict_from_dsr(dsr_by_n),
                    deflated_sharpe=deflated,
                )
            )
        all_results[arm_name] = arm_results
        report[f"sigma_sr_{arm_name}"] = sigma_sr
        logger.info("cost arm %s: %d specs", arm_name, len(arm_results))

    # ---------------- family verdict, read off the BASELINE overlay ----------
    baseline = all_results[BASELINE_ARM]
    verdicts = [r.verdict for r in baseline]
    best = max(baseline, key=lambda r: r.sharpe_annualized)
    family_verdict = (
        "PASS"
        if "PASS" in verdicts
        else ("UNRESOLVED" if "UNRESOLVED" in verdicts else "DEFINITE_NEGATIVE")
    )
    report["family_verdict"] = family_verdict
    report["verdict_counts"] = {v: verdicts.count(v) for v in set(verdicts)}
    report["best_spec_by_overlay_sharpe"] = {
        "spec_id": best.spec_id,
        "overlay_sharpe": best.sharpe_annualized,
        "strategy_sharpe": best.strategy_sharpe,
        "dsr_by_n": best.dsr_by_n,
        "verdict": best.verdict,
    }
    report["results_by_cost_arm"] = {
        arm: [asdict(r) for r in res] for arm, res in all_results.items()
    }

    # ---------------- persist ----------------
    out_json = OUT_DIR / f"inelastic_markets_{date.today().isoformat()}.json"
    out_json.write_text(json.dumps(report, indent=2, default=str))
    logger.info("wrote %s", out_json)

    with SessionLocal() as db:
        written = persist_cross_sectional_trial_results(db, FAMILY_KEY, baseline, run_tag=RUN_TAG)
        verify_persisted_trial_results(db, RUN_TAG, written, family_key=FAMILY_KEY)
        logger.info("persisted %d baseline rows to %s", written, describe_configured_database())

    # ---------------- human-readable ----------------
    lines: list[str] = []
    lines.append("INELASTIC MARKETS (Gabaix & Koijen 2021) -- candidate #16")
    lines.append("=" * 78)
    lines.append(f"run_tag: {RUN_TAG}")
    lines.append(f"FAMILY VERDICT (baseline cost arm, OVERLAY stream): {family_verdict}")
    lines.append("")
    lines.append(f"GATE G1 partition integrity: {'PASS' if g1['passed'] else 'FAIL'} "
                 f"(median |rel| {g1['median_abs_rel_discrepancy']:.5f} vs 0.02 threshold)")
    lines.append(f"GATE G2 mechanism fidelity : {'PASS' if g2['passed'] else 'FAIL'}")
    for k, v in g2["estimates"].items():
        lines.append(f"    M({k}) = {v['multiplier']:.3f}   paper = {v['paper_value']}   "
                     f"n = {v['n_obs']}   R2 = {v.get('r_squared', float('nan')):.3f}")
    lines.append("    paper robustness range [3.5, 8.0]")
    lines.append("")
    lines.append(f"DSR ladder: {denominators}   bar {VALIDATED_EDGE_BAR}")
    lines.append(f"buy-and-hold quarterly-annualized Sharpe: {bench_sharpe:.4f}")
    lines.append("")
    lines.append("BASELINE ARM, all 24 specs (verdict stream = overlay):")
    lines.append(f"  {'spec_id':<34} {'overlay':>8} {'strat':>7} {'DSR@' + str(denominators[0]):>10} "
                 f"{'DSR@' + str(denominators[-1]):>11}  verdict")
    for r in sorted(baseline, key=lambda x: -x.sharpe_annualized):
        d_lo = r.dsr_by_n.get(denominators[0])
        d_hi = r.dsr_by_n.get(denominators[-1])
        lines.append(
            f"  {r.spec_id:<34} {r.sharpe_annualized:8.4f} {r.strategy_sharpe:7.4f} "
            f"{(f'{d_lo:.4f}' if d_lo is not None else 'None'):>10} "
            f"{(f'{d_hi:.4f}' if d_hi is not None else 'None'):>11}  {r.verdict}"
        )
    out_txt = OUT_DIR / f"inelastic_markets_{date.today().isoformat()}.txt"
    out_txt.write_text("\n".join(lines) + "\n")
    logger.info("wrote %s", out_txt)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
