"""Measure what the 2026-09-05 cost-model correction does to lazy_prices —
the one live-registered family that trades on cost_model="edge_spread".

WHAT IS BEING MEASURED. Four scenarios over ONE shared data build (same
frozen price snapshot, same frozen filing index, same similarity panels, same
36 specs), so every difference between them is the cost assumption and
nothing else:

  S0-control      raw EDGE half-spread frame, financing 0.0.
                  Byte-for-byte the production configuration
                  (default_lazy_prices_config + build_edge_half_spread_frame)
                  that produced run_tag lazy_prices_2026-09-01 and the live
                  forward registration. Re-run here so the comparison is
                  against a number computed on THIS data build rather than
                  against a persisted row from a different calendar day.
  S1-calibrated   calibrated EDGE frame (sign=True + truncation, one pooled
                  scalar to Hagstromer/Nasdaq's ~2bp one-way S&P 500 level,
                  per-cell tick floor), financing 0.0. Isolates the
                  SPREAD fix.
  S2-borrow-gc    calibrated frame + general-collateral borrow on the short
                  leg (34bp/yr, Beneish/Lee/Nichols DCBS=1) => financing
                  17bp/yr on gross. D'Avolio p.273 is the justification for
                  GC being the right band for an S&P 500 cross-section.
  S3-borrow-htb   calibrated frame + the hard-to-borrow rate applied to the
                  WHOLE short leg (430bp/yr, D'Avolio Table 3 specials) =>
                  financing 215bp/yr on gross. Not an estimate: a worst-case
                  bracket, since this family's short leg is not built from
                  heavily-shorted names and its true rate is near GC.

DSR is reported at all three Policy D denominators (36 / 481 / 857) for every
scenario. The extra denominators are computed ANALYTICALLY from the same
screening pass rather than by re-screening: n_trials enters
compute_deflated_sharpe only through expected_max_sharpe_under_noise(sigma_sr,
n_trials), and every other input (the Sharpe, n, skew, kurtosis, sigma_sr) is
identical across denominators. So DSR(N) = probabilistic_sharpe_ratio(
sr_daily, SR0_daily(N), n, skew, kurt) reuses the persisted numbers exactly.
recompute_dsr_at() below does that with this project's own functions — nothing
is reimplemented — and dsr_at_local_matches_screening in the output is the
check that it reproduces the screening's own figure to floating point.

NOTHING HERE TOUCHES A REGISTRATION. This script reads the forward-validation
tables not at all and writes only cross_sectional_trial_results rows under new
run tags. The live lazy_prices registration keeps trading the S0 frame until
the repo owner decides otherwise — swapping the frame changes an accumulating
track record without changing any fingerprint, which is exactly the silent
drift live_registration_dependencies.json exists to surface.

    ./venv/bin/python run_edge_cost_correction_lazy_prices.py
"""

import json
import logging
import os
import sys
from datetime import date

import numpy as np

from app.db import SessionLocal, engine
from app.services.market_data.edgar_filing_text_provider import (
    EdgarFilingTextProvider,
    load_filing_index,
)
from app.services.market_data.yfinance_provider import load_ohlcv_snapshot
from app.services.research_lab.borrow_cost import (
    GENERAL_COLLATERAL_BPS_PER_YEAR,
    HARD_TO_BORROW_BPS_PER_YEAR,
    financing_bps_for_long_short_book,
)
from app.services.research_lab.cross_sectional import CrossSectionalConfig
from app.services.research_lab.cross_sectional_lazy_prices import (
    BASIS_WEIGHTED_MODES,
    DEFAULT_FILING_INDEX_PATH,
    DEFAULT_PRICE_SNAPSHOT_DIR,
    LAZY_PRICES_FAMILY,
    LAZY_PRICES_FILING_WARMUP_DAYS,
    LAZY_PRICES_N_TRIALS,
    build_inverse_vol_basis,
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
from app.services.research_lab.spread_estimator import (
    build_calibrated_half_spread_frame,
    build_edge_half_spread_frame,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("edge_cost_correction")

RUN_DATE = "2026-09-05"
FAMILY_KEY = "lazy_prices"
OUT_JSON = "/tmp/edge_cost_correction_lazy_prices.json"

START = MEMBERSHIP_DATA_START
END = date(2026, 8, 31)

# Policy D's three denominators. 36 is this family's own pre-declared grid
# (LAZY_PRICES_N_TRIALS); 481 and 857 come from global_effective_n.json.
POLICY_D_N = (LAZY_PRICES_N_TRIALS, 481, 857)


def recompute_dsr_at(dsr_result, n_trials: int) -> float | None:
    """DSR for an already-computed screening result at a DIFFERENT n_trials.

    n_trials enters compute_deflated_sharpe only via
    expected_max_sharpe_under_noise; every other input is a property of the
    return series and is unchanged. So this is the same arithmetic the
    screening did, with one term substituted — using deflated_sharpe's own
    functions, not a reimplementation of them. The de-annualization mirrors
    compute_deflated_sharpe's exactly (both sr_hat and sigma_SR divided by
    sqrt(periods_per_year); see that function's docstring on why missing the
    second one is the classic bug)."""
    if dsr_result.sigma_sr_annualized is None or dsr_result.dsr is None:
        return None
    if n_trials < MIN_TRIALS_FOR_DSR:
        return None
    root = np.sqrt(TRADING_DAYS_PER_YEAR)
    sr_daily = dsr_result.sharpe_net_annualized / root
    sigma_daily = dsr_result.sigma_sr_annualized / root
    sr0_daily = expected_max_sharpe_under_noise(sigma_daily, n_trials)
    if sr0_daily is None:
        return None
    return probabilistic_sharpe_ratio(
        sr_daily,
        sr0_daily,
        dsr_result.n_observations,
        dsr_result.skewness,
        dsr_result.kurtosis,
    )


def scenario_configs():
    """(name, config_factory, uses_calibrated_frame, run_tag)."""
    gc_financing = financing_bps_for_long_short_book(GENERAL_COLLATERAL_BPS_PER_YEAR)
    htb_financing = financing_bps_for_long_short_book(HARD_TO_BORROW_BPS_PER_YEAR)
    return [
        (
            "S0-control",
            lambda: CrossSectionalConfig(cost_model="edge_spread"),
            False,
            f"edge_cost_correction_{RUN_DATE}_control_raw_edge",
        ),
        (
            "S1-calibrated",
            lambda: CrossSectionalConfig(cost_model="edge_spread"),
            True,
            f"edge_cost_correction_{RUN_DATE}_calibrated_spread",
        ),
        (
            "S2-borrow-gc",
            lambda: CrossSectionalConfig(
                cost_model="edge_spread", financing_bps_per_year=gc_financing
            ),
            True,
            f"edge_cost_correction_{RUN_DATE}_calibrated_plus_gc_borrow",
        ),
        (
            "S3-borrow-htb",
            lambda: CrossSectionalConfig(
                cost_model="edge_spread", financing_bps_per_year=htb_financing
            ),
            True,
            f"edge_cost_correction_{RUN_DATE}_calibrated_plus_htb_borrow",
        ),
    ]


def main() -> None:
    import app.models  # noqa: F401 — registers every table on Base.metadata
    from app.db import Base

    Base.metadata.create_all(engine)

    if not DEFAULT_PRICE_SNAPSHOT_DIR.exists():
        sys.exit(
            f"frozen price snapshot missing at {DEFAULT_PRICE_SNAPSHOT_DIR} — this comparison "
            "must not fall back to a live fetch, or the 'before' number would not be the "
            "registered one."
        )
    frames = load_ohlcv_snapshot(DEFAULT_PRICE_SNAPSHOT_DIR)
    if frames is None:
        sys.exit(f"no readable snapshot manifest under {DEFAULT_PRICE_SNAPSHOT_DIR}")
    close = frames["close"]
    log.info(
        "frozen price snapshot: %d tickers, %s..%s",
        len(close.columns),
        close.index[0].date(),
        close.index[-1].date(),
    )

    loaded = load_filing_index(DEFAULT_FILING_INDEX_PATH)
    if loaded is None:
        sys.exit(
            f"frozen filing index missing at {DEFAULT_FILING_INDEX_PATH} — this comparison must "
            "not rebuild it from a live EDGAR walk, or the 'before' number would not be the "
            "registered one."
        )
    filing_index, filing_report = loaded
    warmup_floor = START.toordinal() - LAZY_PRICES_FILING_WARMUP_DAYS
    trimmed = {
        ticker: [f for f in filings if f.filing_date.toordinal() >= warmup_floor]
        for ticker, filings in filing_index.items()
        if ticker in close.columns
    }
    log.info("filing index: %d tickers after trim", len(trimmed))

    text_provider = EdgarFilingTextProvider()
    observations, similarity_report = build_similarity_observations(text_provider, trimmed)
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

    raw_frame = build_edge_half_spread_frame(
        frames["open"], frames["high"], frames["low"], close
    )
    calibrated_frame, calibration = build_calibrated_half_spread_frame(
        frames["open"], frames["high"], frames["low"], close, calibration_start=START
    )
    log.info("calibration: %s", calibration.summary())

    raw_cells = raw_frame.to_numpy().ravel()
    cal_cells = calibrated_frame.to_numpy().ravel()
    frame_stats = {
        "raw_median_half_spread_bps": float(np.nanmedian(raw_cells) * 10_000),
        "raw_mean_half_spread_bps": float(np.nanmean(raw_cells) * 10_000),
        "calibrated_median_half_spread_bps": float(np.nanmedian(cal_cells) * 10_000),
        "calibrated_mean_half_spread_bps": float(np.nanmean(cal_cells) * 10_000),
        "calibration": {
            "window_days": calibration.window_days,
            "target_median_half_spread_bps": calibration.target_median_half_spread * 10_000,
            "observed_median_half_spread_bps": calibration.observed_median_half_spread * 10_000,
            "scale": calibration.scale,
            "n_cells_total": calibration.n_cells_total,
            "n_cells_estimated": calibration.n_cells_estimated,
            "n_cells_truncated_to_zero": calibration.n_cells_truncated_to_zero,
            "n_cells_no_estimate": calibration.n_cells_no_estimate,
            "n_cells_raised_to_tick_floor": calibration.n_cells_raised_to_tick_floor,
            "realized_median_half_spread_bps": calibration.realized_median_half_spread * 10_000,
        },
    }
    log.info(
        "half-spread frames: raw median %.2fbp, calibrated median %.2fbp",
        frame_stats["raw_median_half_spread_bps"],
        frame_stats["calibrated_median_half_spread_bps"],
    )

    payload = {
        "run_date": RUN_DATE,
        "family_key": FAMILY_KEY,
        "window": [START.isoformat(), END.isoformat()],
        "n_priced_tickers": len(close.columns),
        "policy_d_n": list(POLICY_D_N),
        "frame_stats": frame_stats,
        "similarity_report": {
            "n_tickers": similarity_report.n_tickers,
        },
        "filing_report_tickers_requested": filing_report.n_tickers_requested,
        "scenarios": {},
    }

    persist = os.environ.get("PERSIST_TRIALS", "1") != "0"
    db = SessionLocal() if persist else None
    try:
        for name, make_config, use_calibrated, run_tag in scenario_configs():
            half_spread = calibrated_frame if use_calibrated else raw_frame
            config = make_config()
            config.formation_start = START
            results = screen_lazy_prices_family(
                close,
                panels,
                config,
                half_spread=half_spread,
                leg_weight_basis=leg_weight_basis,
            )

            per_spec = {}
            for r in results:
                d = r.deflated_sharpe
                dsr_by_n = {str(n): recompute_dsr_at(d, n) for n in POLICY_D_N}
                per_spec[r.pattern_id] = {
                    "sharpe": r.sharpe_annualized,
                    "n_observations": d.n_observations,
                    "n_trials_screened": d.n_trials,
                    "dsr_screening": d.dsr,
                    "dsr_by_n": dsr_by_n,
                    "psr_vs_zero": d.psr_vs_zero,
                    "sigma_sr_annualized": d.sigma_sr_annualized,
                    "total_cost_drag": r.total_cost_drag,
                    "total_financing_drag": r.total_financing_drag,
                    # The check that the analytic recomputation is the same
                    # arithmetic the screening did, not an approximation.
                    "dsr_at_local_matches_screening": (
                        d.dsr is not None
                        and dsr_by_n[str(LAZY_PRICES_N_TRIALS)] is not None
                        and abs(dsr_by_n[str(LAZY_PRICES_N_TRIALS)] - d.dsr) < 1e-12
                    ),
                }

            mismatches = [pid for pid, v in per_spec.items() if not v["dsr_at_local_matches_screening"]]
            if mismatches:
                sys.exit(
                    f"{name}: analytic DSR recomputation disagreed with the screening's own "
                    f"figure for {mismatches} — refusing to report numbers that do not reconcile."
                )

            best_pid = max(per_spec, key=lambda pid: per_spec[pid]["sharpe"])
            best = per_spec[best_pid]
            payload["scenarios"][name] = {
                "run_tag": run_tag,
                "uses_calibrated_frame": use_calibrated,
                "financing_bps_per_year": config.financing_bps_per_year,
                "n_specs": len(per_spec),
                "best_spec": best_pid,
                "best": best,
                "all_specs": per_spec,
            }
            log.info(
                "%s: best %s sharpe=%.4f dsr@36=%s dsr@481=%s dsr@857=%s cost_drag=%.4f fin_drag=%.4f",
                name,
                best_pid,
                best["sharpe"],
                best["dsr_by_n"]["36"],
                best["dsr_by_n"]["481"],
                best["dsr_by_n"]["857"],
                best["total_cost_drag"],
                best["total_financing_drag"],
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
