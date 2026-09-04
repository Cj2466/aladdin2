"""THE 2026-09-05 COST-BASIS SWITCH, MEASURED ON THE FAMILY IT WAS APPLIED TO.

Three scenarios over ONE shared data build (same frozen price snapshot, same
frozen filing index, same six similarity panels, same 36 pre-declared specs),
so every difference between them is the cost assumption and nothing else:

  BEFORE   the raw EDGE half-spread frame, financing 0.0 — byte-for-byte what
           lazy_prices_jaccard_full traded on from 2026-09-03 until this
           commit. This is the "before" line of the switch record.
  AFTER    the calibrated frame, financing 0.0 — what default_lazy_prices_
           config() + build_lazy_prices_half_spread_frame now produce, and
           what the live tick computes from this commit forward. ADOPTED.
  +BORROW  the calibrated frame PLUS the borrow rate this family's own short
           leg was MEASURED to owe under borrow_cost's schedule — 96.33 bp/yr
           on the short leg, i.e. financing_bps_per_year 48.16 on gross (see
           lazy_prices_borrow_composition_2026-09-05.txt). NOT ADOPTED, and
           not because it is wrong: financing_bps_per_year is in
           config_identity(), so adopting it re-hashes config_fingerprint and
           the runner parks the live row as "spec_drift" permanently. That is
           an operational-status change and the repo owner's call. Measured
           here so the decision is made against a number.

BEFORE/AFTER duplicates two of the four scenarios in run_edge_cost_correction_
lazy_prices.py deliberately, rather than importing them: that script is the
committed reproducibility artifact of the 39f7cb5 measurement and is left
untouched, and this run re-derives its figures independently on a later day as
a check on them.

    ./venv/bin/python data/research_runs/run_lazy_prices_cost_basis_switch.py
"""

import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np

# WORKTREE BINDING GUARD — load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv, whose site-packages
# resolves `app` to the MAIN worktree's backend/app. Without the two lines
# below, this runner silently measures main's code instead of this branch's —
# and for a module that exists in both, with NO error at all. This run exists
# precisely to measure a change to app/, so binding to the wrong checkout would
# report the "after" number of code that was never edited.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The comparison would have measured another checkout's code."
    )

from app.db import SessionLocal, engine
from app.services.market_data.edgar_filing_text_provider import (
    EdgarFilingTextProvider,
    load_filing_index,
)
from app.services.market_data.yfinance_provider import load_ohlcv_snapshot
from app.services.research_lab.cross_sectional import CrossSectionalConfig
from app.services.research_lab.cross_sectional_lazy_prices import (
    BASIS_WEIGHTED_MODES,
    DEFAULT_FILING_INDEX_PATH,
    DEFAULT_PRICE_SNAPSHOT_DIR,
    LAZY_PRICES_FAMILY,
    LAZY_PRICES_FILING_WARMUP_DAYS,
    LAZY_PRICES_N_TRIALS,
    build_inverse_vol_basis,
    build_lazy_prices_half_spread_frame,
    build_similarity_observations,
    build_similarity_panel,
    screen_lazy_prices_family,
)
from app.services.research_lab.cross_sectional_persistence import (
    persist_cross_sectional_trial_results,
)
from app.services.research_lab.deflated_sharpe import (
    MIN_TRIALS_FOR_DSR,
    expected_max_sharpe_under_noise,
    probabilistic_sharpe_ratio,
)
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START
from app.services.research_lab.spread_estimator import build_edge_half_spread_frame

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("cost_basis_switch")

RUN_DATE = "2026-09-05"
FAMILY_KEY = "lazy_prices"
START = MEMBERSHIP_DATA_START
END = date(2026, 8, 31)
POLICY_D_N = (LAZY_PRICES_N_TRIALS, 481, 857)
OUT_JSON = "data/research_runs/lazy_prices_cost_basis_switch_2026-09-05.json"

# borrow_cost's schedule averaged over this family's REAL short leg across the
# 17 formations that carry FINRA short-interest coverage. Not a scenario knob:
# the output of run_lazy_prices_borrow_composition.py, quoted so this run does
# not have to rebuild the short-interest panel.
MEASURED_SHORT_LEG_BORROW_BPS = 96.3287
MEASURED_FINANCING_BPS = MEASURED_SHORT_LEG_BORROW_BPS / 2.0


def recompute_dsr_at(dsr_result, n_trials: int) -> float | None:
    """DSR for an already-computed screening result at a DIFFERENT n_trials.
    n_trials enters compute_deflated_sharpe only via
    expected_max_sharpe_under_noise; every other input is a property of the
    return series. Same arithmetic, one term substituted, using this
    project's own functions."""
    if dsr_result.sigma_sr_annualized is None or dsr_result.dsr is None:
        return None
    if n_trials < MIN_TRIALS_FOR_DSR:
        return None
    root = np.sqrt(TRADING_DAYS_PER_YEAR)
    sr0 = expected_max_sharpe_under_noise(dsr_result.sigma_sr_annualized / root, n_trials)
    if sr0 is None:
        return None
    return probabilistic_sharpe_ratio(
        dsr_result.sharpe_net_annualized / root,
        sr0,
        dsr_result.n_observations,
        dsr_result.skewness,
        dsr_result.kurtosis,
    )


def main() -> None:
    import app.models  # noqa: F401 — registers every table on Base.metadata
    from app.db import Base

    Base.metadata.create_all(engine)

    if not DEFAULT_PRICE_SNAPSHOT_DIR.exists():
        sys.exit(f"frozen price snapshot missing at {DEFAULT_PRICE_SNAPSHOT_DIR}")
    frames = load_ohlcv_snapshot(DEFAULT_PRICE_SNAPSHOT_DIR)
    if frames is None:
        sys.exit(f"no readable snapshot manifest under {DEFAULT_PRICE_SNAPSHOT_DIR}")
    close = frames["close"]

    loaded = load_filing_index(DEFAULT_FILING_INDEX_PATH)
    if loaded is None:
        sys.exit(f"frozen filing index missing at {DEFAULT_FILING_INDEX_PATH}")
    filing_index, _report = loaded
    warmup_floor = START.toordinal() - LAZY_PRICES_FILING_WARMUP_DAYS
    trimmed = {
        t: [f for f in fl if f.filing_date.toordinal() >= warmup_floor]
        for t, fl in filing_index.items()
        if t in close.columns
    }

    text_provider = EdgarFilingTextProvider()
    observations, _sim = build_similarity_observations(text_provider, trimmed)
    panels = {}
    for (metric, scope), by_ticker in observations.items():
        panel, _ages, _unusable = build_similarity_panel(close, by_ticker)
        panels[(metric, scope)] = panel
    log.info("panels built: %d", len(panels))

    leg_weight_basis = (
        build_inverse_vol_basis(close)
        if any(s.spec.leg_weighting in BASIS_WEIGHTED_MODES for s in LAZY_PRICES_FAMILY)
        else None
    )

    # BEFORE: the raw estimator, called directly — the family's own builder no
    # longer produces this frame, which is the point of the switch.
    before_frame = build_edge_half_spread_frame(
        frames["open"], frames["high"], frames["low"], close
    )
    # AFTER: the family's own builder, i.e. exactly what the live tick calls.
    after_frame = build_lazy_prices_half_spread_frame(
        frames["open"], frames["high"], frames["low"], close, calibration_start=START
    )

    scenarios = [
        ("BEFORE-raw-edge", before_frame, 0.0, f"cost_basis_switch_{RUN_DATE}_before_raw_edge"),
        ("AFTER-calibrated", after_frame, 0.0, f"cost_basis_switch_{RUN_DATE}_after_calibrated"),
        (
            "AFTER+measured-borrow",
            after_frame,
            MEASURED_FINANCING_BPS,
            f"cost_basis_switch_{RUN_DATE}_after_calibrated_measured_borrow",
        ),
    ]

    payload = {
        "run_date": RUN_DATE,
        "family_key": FAMILY_KEY,
        "window": [START.isoformat(), END.isoformat()],
        "policy_d_n": list(POLICY_D_N),
        "measured_short_leg_borrow_bps_per_year": MEASURED_SHORT_LEG_BORROW_BPS,
        "measured_financing_bps_per_year": MEASURED_FINANCING_BPS,
        "frame_median_half_spread_bps": {
            "before": float(np.nanmedian(before_frame.to_numpy())) * 10_000,
            "after": float(np.nanmedian(after_frame.to_numpy())) * 10_000,
        },
        "scenarios": {},
    }

    persist = os.environ.get("PERSIST_TRIALS", "1") != "0"
    db = SessionLocal() if persist else None
    try:
        for name, half_spread, financing, run_tag in scenarios:
            config = CrossSectionalConfig(
                cost_model="edge_spread", financing_bps_per_year=financing
            )
            config.formation_start = START
            results = screen_lazy_prices_family(
                close, panels, config, half_spread=half_spread, leg_weight_basis=leg_weight_basis
            )
            per_spec = {}
            for r in results:
                d = r.deflated_sharpe
                dsr_by_n = {str(n): recompute_dsr_at(d, n) for n in POLICY_D_N}
                if not (
                    d.dsr is not None
                    and dsr_by_n[str(LAZY_PRICES_N_TRIALS)] is not None
                    and abs(dsr_by_n[str(LAZY_PRICES_N_TRIALS)] - d.dsr) < 1e-12
                ):
                    sys.exit(
                        f"{name}/{r.pattern_id}: analytic DSR recomputation disagreed with the "
                        "screening's own figure — refusing to report numbers that do not reconcile."
                    )
                per_spec[r.pattern_id] = {
                    "sharpe": r.sharpe_annualized,
                    "n_observations": d.n_observations,
                    "dsr_by_n": dsr_by_n,
                    "psr_vs_zero": d.psr_vs_zero,
                    "sigma_sr_annualized": d.sigma_sr_annualized,
                    "skewness": d.skewness,
                    "kurtosis": d.kurtosis,
                    "total_cost_drag": r.total_cost_drag,
                    "total_financing_drag": r.total_financing_drag,
                }
            best_pid = max(per_spec, key=lambda pid: per_spec[pid]["sharpe"])
            best = per_spec[best_pid]
            payload["scenarios"][name] = {
                "run_tag": run_tag,
                "financing_bps_per_year": financing,
                "n_specs": len(per_spec),
                "n_specs_positive": sum(1 for v in per_spec.values() if v["sharpe"] > 0),
                "best_spec": best_pid,
                "best": best,
                "all_specs": per_spec,
            }
            log.info(
                "%s: best %s sharpe=%+.4f dsr@36=%.4f @481=%.4f @857=%.4f cost=%.4f fin=%.4f pos=%d/36",
                name,
                best_pid,
                best["sharpe"],
                best["dsr_by_n"]["36"],
                best["dsr_by_n"]["481"],
                best["dsr_by_n"]["857"],
                best["total_cost_drag"],
                best["total_financing_drag"],
                payload["scenarios"][name]["n_specs_positive"],
            )
            if db is not None:
                n = persist_cross_sectional_trial_results(db, FAMILY_KEY, results, run_tag)
                log.info("persisted %d rows under run_tag=%s", n, run_tag)
    finally:
        if db is not None:
            db.close()

    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    log.info("wrote %s", OUT_JSON)


if __name__ == "__main__":
    main()
