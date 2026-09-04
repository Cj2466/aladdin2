"""Production runner for the Daniel-Moskowitz crash-mitigation overlay on
residual momentum.

Rebuilds the residual-momentum family's own data with that module's OWN public
helpers (not a reimplementation), re-screens its 18 specs so this run's base
Sharpes can be checked against the persisted ones, captures the three base
specs' realized daily return series, applies the four pre-registered overlays to
each, and computes Sharpe / PSR / DSR at n_trials = 30 with sigma_SR pooled over
all 30 — using this project's own deflated_sharpe functions, the identical
estimators screen_cross_sectional_universe calls.

Checked into data/research_runs/ alongside the pre-registration and the report
so the exact invocation that produced the numbers is reproducible from the repo.
Run from backend/ with ./venv/bin/python.
"""

import itertools
import json
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# WORKTREE BINDING GUARD — load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv, whose site-packages
# resolves `app` to the MAIN worktree's backend/app. Without the two lines
# below, this runner silently screens main's code instead of this branch's.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND}). The screen would have run against another checkout's code."
    )

import numpy as np
import pandas as pd

from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
from app.services.market_data.fama_french_provider import load_fama_french_monthly
from app.services.market_data.yfinance_provider import (
    YFinanceProvider,
    load_ohlcv_snapshot,
    save_ohlcv_snapshot,
)
from app.services.research_lab.cross_sectional import (
    CrossSectionalData,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
)
from app.services.research_lab.cross_sectional_quality import (
    build_point_in_time_factor_frame,
    build_quality_sample,
    default_quality_config,
)
from app.services.research_lab.cross_sectional_quality_neutral import (
    build_point_in_time_bucket_frame,
)
from app.services.research_lab.cross_sectional_residual_momentum import (
    RESIDUAL_MOM_ARMS,
    RESIDUAL_MOM_MAX_STALENESS_DAYS,
    RESIDUAL_MOM_N_TRIALS,
    RESIDUAL_MOM_PRICE_PADDING_CALENDAR_DAYS,
    build_residual_momentum_family,
    build_residual_momentum_observations,
    compute_residual_momentum_scores,
    monthly_returns_from_daily_close,
    repool_deflated_sharpe,
    specs_for_arm,
)
from app.services.research_lab.cross_sectional_residual_momentum_dm_overlay import (
    DM_BASE_SPECS,
    DM_OVERLAY_N_TRIALS,
    DM_REGISTRABLE_SPEC_IDS,
    base_specs_for_overlay,
    bear_market_indicator,
    build_dm_overlay_grid,
    build_overlay,
)
from app.services.research_lab.deflated_sharpe import (
    compute_deflated_sharpe,
)
from app.services.research_lab.global_effective_n import dsr_n_trials
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR, sharpe_ratio
from app.services.research_lab.preservation_score import compute_preservation_metrics
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

RUN_TAG = "residual_momentum_dm_overlay_2026-09-04"
RUN_END = date(2026, 9, 4)
MARKET_PROXY = "SPY"

# The shared EDGAR cache — a gitignored, refetchable vendor cache, not code and
# not results. Same rationale as run_residual_momentum.py's own constant.
SHARED_EDGAR_CACHE = Path(
    "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/edgar_companyfacts"
)

# Where the price snapshot for the deterministic re-run check is written. NOT
# committed: this family already documents that it is reproducible to reported
# precision but not bit-reproducible (yfinance restates adjusted closes between
# fetches). The snapshot exists so THIS module's determinism can be verified
# separately from the vendor's.
SNAPSHOT_DIR = Path(
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
    "142109e4-1c17-421d-b8eb-cdbe7ecaf779/scratchpad/dm_overlay_price_snapshot"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("dm_overlay")


def build_panel(provider, edgar, start, end, *, use_snapshot: bool):
    """The residual-momentum family's own data build, assembled from that
    module's public helpers. Deliberately not a call to
    run_residual_momentum_screening: this run needs the intermediate price frame
    and the per-arm score panels, which that entry point does not return."""
    sample, universe_size = build_quality_sample(start, end)
    padded_start = start - timedelta(days=RESIDUAL_MOM_PRICE_PADDING_CALENDAR_DAYS)

    frames = load_ohlcv_snapshot(SNAPSHOT_DIR) if use_snapshot else None
    if frames is not None:
        close = frames["close"]
        market_close = frames["market"]
        missing_price = sorted(set(sample) - set(close.columns))
        logger.info("replayed FROZEN price snapshot from %s", SNAPSHOT_DIR)
    else:
        close, missing_price = provider.get_price_history(sample, padded_start, end)
        market_close, market_missing = provider.get_price_history(
            [MARKET_PROXY], padded_start, end
        )
        if market_missing:
            raise SystemExit(f"market proxy {MARKET_PROXY} did not resolve: {market_missing}")
        # The MARKET proxy travels in the SAME snapshot as the universe panel:
        # freezing one and re-fetching the other would leave the overlay's
        # state variable drifting between runs while the base it modifies did
        # not, which is the one asymmetry that would make a re-run's delta
        # uninterpretable.
        save_ohlcv_snapshot({"close": close, "market": market_close}, SNAPSHOT_DIR)
        logger.info("froze price snapshot to %s", SNAPSHOT_DIR)

    logger.info(
        "panel %s..%s, %d tickers priced, %d sampled, %d missing",
        close.index[0].date(),
        close.index[-1].date(),
        close.shape[1],
        len(sample),
        len(missing_price),
    )

    factors = load_fama_french_monthly()
    monthly = monthly_returns_from_daily_close(close)
    score_frames, diagnostics = compute_residual_momentum_scores(monthly, factors.frame)

    sic_histories, _, sic_failed = edgar.fetch_sic_history_for_tickers(list(close.columns))
    bucket_frame, no_bucket, sic_fallback = build_point_in_time_bucket_frame(close, sic_histories)
    logger.info(
        "buckets built: %d without bucket, %d current-SIC fallback, %d SIC fetch failures",
        len(no_bucket),
        len(sic_fallback),
        len(sic_failed),
    )
    return (
        close,
        market_close,
        score_frames,
        bucket_frame,
        factors,
        universe_size,
        sample,
        missing_price,
        diagnostics,
    )


def main() -> int:
    t0 = time.time()
    start = MEMBERSHIP_DATA_START
    use_snapshot = "--replay-snapshot" in sys.argv

    provider = YFinanceProvider()
    edgar = EdgarXbrlProvider(cache_dir=SHARED_EDGAR_CACHE)
    config = default_quality_config()
    config.formation_start = start

    (
        close,
        market_close,
        score_frames,
        bucket_frame,
        factors,
        universe_size,
        sample,
        missing_price,
        score_diagnostics,
    ) = build_panel(provider, edgar, start, RUN_END, use_snapshot=use_snapshot)

    all_specs = build_residual_momentum_family(bucket_frame)

    # --- STEP 1: re-screen the family's own 18, as a reproduction check -------
    panels: dict[str, pd.DataFrame] = {}
    base_results = []
    for arm, _columns in RESIDUAL_MOM_ARMS:
        observations = build_residual_momentum_observations(score_frames[arm])
        panel, _ages, _unusable = build_point_in_time_factor_frame(
            close, observations, max_staleness_days=RESIDUAL_MOM_MAX_STALENESS_DAYS
        )
        panels[arm] = panel
        base_results.extend(
            screen_cross_sectional_universe(
                CrossSectionalData(close=close, fundamental_signal=panel),
                specs_for_arm(all_specs, arm),
                config,
                n_trials_override=RESIDUAL_MOM_N_TRIALS,
            )
        )
    base_results = repool_deflated_sharpe(base_results)
    logger.info("re-screened %d residual-momentum base specs in %.0fs", len(base_results), time.time() - t0)

    base_sharpes_18 = {r.pattern_id: r.sharpe_annualized for r in base_results}

    # --- STEP 2: capture the three base specs' daily return series -----------
    resolved_bases = base_specs_for_overlay(all_specs)
    arm_for_base = {
        "ctrl": "total_return_control",
        "ff3": "ff3_residual",
        "ff3n": "ff3_residual",
    }
    base_returns: dict[str, pd.Series] = {}
    for base_key, spec in resolved_bases.items():
        replay = run_cross_sectional_backtest(
            CrossSectionalData(close=close, fundamental_signal=panels[arm_for_base[base_key]]),
            spec,
            config,
        )
        if replay.status != "ok":
            raise SystemExit(f"base {spec.pattern_id} replayed with status {replay.status}")
        base_returns[base_key] = replay.daily_returns
        logger.info(
            "base %-6s %-32s %d days  Sharpe %+.4f  (screen said %+.4f)",
            base_key,
            spec.pattern_id,
            len(replay.daily_returns),
            sharpe_ratio(replay.daily_returns),
            base_sharpes_18[spec.pattern_id],
        )

    # --- STEP 3: the market state series -------------------------------------
    market_daily = market_close[MARKET_PROXY].pct_change(fill_method=None)
    market_monthly = factors.frame["mkt_rf"] + factors.frame["rf"]

    bear = bear_market_indicator(market_monthly)
    window = bear[(bear.index >= pd.Timestamp("2015-01-01")) & (bear.index <= pd.Timestamp("2026-08-31"))]
    bear_months = [d.date() for d in window[window == 1.0].index]
    logger.info(
        "bear state: %d of %d months in window (%.2f%%): %s",
        len(bear_months),
        int(window.notna().sum()),
        100.0 * float(window.mean()),
        ", ".join(d.strftime("%Y-%m") for d in bear_months),
    )

    # --- STEP 4: the 12 overlays ---------------------------------------------
    overlays = []
    for base_key, base_pattern_id, arm in build_dm_overlay_grid():
        overlays.append(
            build_overlay(
                base_key,
                base_pattern_id,
                arm,
                base_returns[base_key],
                market_monthly_returns=market_monthly,
                market_daily_returns=market_daily,
                cost_bps=config.cost_bps,
            )
        )

    # --- STEP 5: Sharpe / PSR / DSR, sigma_SR over all 30 ---
    # DM_OVERLAY_N_TRIALS = 30 already pools ACROSS a family boundary (18
    # carried residual-momentum trials + this family's 12), which is the same
    # argument global_effective_n makes for the whole project -- made here by
    # hand, for one family, before the pooled measurement existed. It is now
    # the FLOOR rather than the answer: dsr_n_trials raises it to the
    # project-wide effectively-independent trial count whenever that is larger.
    overlay_sharpes = {o.pattern_id: sharpe_ratio(o.returns) for o in overlays}
    pooled = list(base_sharpes_18.values()) + list(overlay_sharpes.values())
    assert len(pooled) == DM_OVERLAY_N_TRIALS == 30, f"pooled {len(pooled)} Sharpes, expected 30"
    n_trials_pooled = dsr_n_trials(DM_OVERLAY_N_TRIALS)
    sigma_sr = float(np.std(pooled, ddof=1))
    logger.info("sigma_SR pooled over all %d Sharpes: %.5f", len(pooled), sigma_sr)

    rows = []
    for overlay in overlays:
        dsr = compute_deflated_sharpe(
            overlay_sharpes[overlay.pattern_id],
            overlay.returns,
            n_trials_pooled,
            sigma_sr,
        )
        preservation = compute_preservation_metrics(overlay.returns, dsr=dsr.dsr)
        base_preservation = compute_preservation_metrics(
            base_returns[overlay.base_key], dsr=dsr.dsr
        )
        d = overlay.diagnostics
        rows.append(
            {
                "pattern_id": overlay.pattern_id,
                "base_key": overlay.base_key,
                "base_pattern_id": overlay.base_pattern_id,
                "arm": overlay.arm,
                "registrable": overlay.pattern_id in DM_REGISTRABLE_SPEC_IDS,
                "sharpe": overlay_sharpes[overlay.pattern_id],
                "sharpe_base": sharpe_ratio(base_returns[overlay.base_key]),
                "sharpe_pre_overlay_cost": sharpe_ratio(overlay.returns_pre_overlay_cost),
                "dsr": dsr.dsr,
                "psr_vs_zero": dsr.psr_vs_zero,
                "sr0_annualized": dsr.expected_max_sharpe_noise_annualized,
                "n_observations": dsr.n_observations,
                "skewness": dsr.skewness,
                "kurtosis": dsr.kurtosis,
                "max_drawdown": preservation.max_drawdown,
                "max_drawdown_base": base_preservation.max_drawdown,
                "max_drawdown_delta": preservation.max_drawdown - base_preservation.max_drawdown,
                "calmar": preservation.calmar,
                "annualized_return": preservation.annualized_return,
                "sharpe_first_half": preservation.sharpe_first_half,
                "sharpe_second_half": preservation.sharpe_second_half,
                "stability": preservation.stability,
                "preservation_score": preservation.preservation_score,
                "preservation_score_no_stab": preservation.preservation_score_no_stab,
                "preservation_score_base": base_preservation.preservation_score,
                "overlay_cost_total": overlay.overlay_cost_total,
                "normalization_k": overlay.normalization_k,
                "weight_min": d.weight_min,
                "weight_max": d.weight_max,
                "weight_mean_abs": d.weight_mean_abs,
                "n_negative_weight_months": d.n_negative_weight_months,
                "n_months": d.n_months,
                "n_warmup_months": d.n_warmup_months,
                "n_unidentified_months": d.n_unidentified_months,
                "n_bear_months": d.n_bear_months,
                "n_months_weight_moved": d.n_months_weight_moved,
            }
        )

    # --- STEP 6: the three pre-declared structural diagnostics ---------------
    by_id = {o.pattern_id: o for o in overlays}
    diagnostics_extra = {}
    for base_key, _pid in DM_BASE_SPECS:
        dyn = by_id[f"dm_{base_key}_dyn_h21"].weights
        vscale = by_id[f"dm_{base_key}_vscale_h21"].weights
        diagnostics_extra[f"corr_dyn_vscale_{base_key}"] = float(
            np.corrcoef(dyn.to_numpy(), vscale.to_numpy())[0, 1]
        )

    # DOWNSIDE METRICS. Max drawdown is one number about one episode. D&M's
    # claim is about the whole left tail, so the left tail is measured: worst
    # month, worst day, downside deviation (semi-deviation below zero), the 5%
    # daily VaR, and the count of months below -5%. Reported for every arm AND
    # its own base so the comparison is like-for-like.
    def downside(series):
        idx = series.index
        monthly = (1.0 + series).groupby([idx.year, idx.month]).prod() - 1.0
        negative = series[series < 0.0]
        return {
            "worst_month": float(monthly.min()),
            "worst_day": float(series.min()),
            "downside_deviation_ann": float(
                np.sqrt((negative**2).mean()) * np.sqrt(TRADING_DAYS_PER_YEAR)
            )
            if len(negative)
            else 0.0,
            "var95_daily": float(np.percentile(series.to_numpy(), 5.0)),
            "n_months_below_minus5pct": int((monthly < -0.05).sum()),
            "n_months": len(monthly),
        }

    downside_rows = []
    for overlay in overlays:
        row = {"pattern_id": overlay.pattern_id}
        row.update({f"overlay_{k}": v for k, v in downside(overlay.returns).items()})
        row.update({f"base_{k}": v for k, v in downside(base_returns[overlay.base_key]).items()})
        downside_rows.append(row)

    # THE `dyn` COEFFICIENT PATH. If D&M's dynamic weight misbehaves here, the
    # reason has to be shown rather than asserted. These are the actual
    # expanding-window (g0, g_int) estimates the weight was built from.
    from app.services.research_lab.cross_sectional_residual_momentum_dm_overlay import (
        DM_VARIANCE_WINDOW_DAYS,
        month_end_positions,
        trailing_annualized_variance,
    )

    coefficient_path = {}
    for base_key in ("ctrl", "ff3", "ff3n"):
        base = base_returns[base_key]
        idx = base.index
        ends = month_end_positions(idx)
        me = idx[ends]
        monthly = (1.0 + base).groupby([idx.year, idx.month]).prod() - 1.0
        monthly.index = me
        mv = trailing_annualized_variance(
            market_daily.reindex(idx), window_days=DM_VARIANCE_WINDOW_DAYS
        ).iloc[ends]
        bb = bear_market_indicator(market_monthly)
        bb.index = bb.index.to_period("M")
        b = pd.Series([bb.get(t.to_period("M"), np.nan) for t in me], index=me, dtype=float)
        x = (b * mv).to_numpy(dtype=float)
        x_lag = np.concatenate([[np.nan], x[:-1]])
        y = monthly.to_numpy(dtype=float)
        path = []
        for m in range(len(y)):
            usable = np.isfinite(y[: m + 1]) & np.isfinite(x_lag[: m + 1])
            if usable.sum() < 36 or np.ptp(x_lag[: m + 1][usable]) <= 0.0:
                continue
            design = np.column_stack(
                [np.ones(int(usable.sum())), x_lag[: m + 1][usable]]
            )
            coefficients, *_ = np.linalg.lstsq(design, y[: m + 1][usable], rcond=None)
            path.append(
                {
                    "month": me[m].date().isoformat(),
                    "g0": float(coefficients[0]),
                    "g_int": float(coefficients[1]),
                    "mu_hat": float(coefficients[0] + coefficients[1] * x[m])
                    if np.isfinite(x[m])
                    else None,
                }
            )
        g0s = [p["g0"] for p in path]
        coefficient_path[base_key] = {
            "n_estimated_months": len(path),
            "first_month": path[0]["month"] if path else None,
            "g0_min": min(g0s) if g0s else None,
            "g0_max": max(g0s) if g0s else None,
            "g0_sign_changes": sum(
                1 for a, b_ in itertools.pairwise(g0s) if (a > 0) != (b_ > 0)
            ),
            "n_months_g0_negative": sum(1 for g in g0s if g < 0),
            "path": path,
        }

    # THE LOOK-AHEAD PROBE. Delaying every weight by one further whole month
    # can only destroy information, never add any, so an effect that survives
    # it is reading something genuinely persistent and one that collapses was
    # reading something that had to be acted on instantly.
    extra_lag = []
    for base_key, base_pattern_id, arm in build_dm_overlay_grid():
        probe = build_overlay(
            base_key,
            base_pattern_id,
            arm,
            base_returns[base_key],
            market_monthly_returns=market_monthly,
            market_daily_returns=market_daily,
            cost_bps=config.cost_bps,
            extra_lag_months=1,
        )
        extra_lag.append(
            {
                "pattern_id": probe.pattern_id,
                "sharpe_extra_lag_1m": sharpe_ratio(probe.returns),
                "sharpe_headline": overlay_sharpes[probe.pattern_id],
                "max_drawdown_extra_lag_1m": compute_preservation_metrics(
                    probe.returns, dsr=1.0
                ).max_drawdown,
            }
        )

    # EPISODE CONCENTRATION. The DSR deflates for trial count, sample length,
    # skew and kurtosis. It does NOT deflate for how few effectively
    # independent bets produced the result — the exact gap dd288f9 identified
    # in the industry-neutral finding. Measured here directly: of the total
    # monthly excess return the overlay adds over its own base, what share
    # comes from the single best month, and from the best three?
    concentration = []
    for overlay in overlays:
        base = base_returns[overlay.base_key]
        idx = base.index
        excess_monthly = (
            (1.0 + overlay.returns).groupby([idx.year, idx.month]).prod()
            - (1.0 + base).groupby([idx.year, idx.month]).prod()
        )
        total = float(excess_monthly.sum())
        ordered = excess_monthly.sort_values(ascending=False)
        concentration.append(
            {
                "pattern_id": overlay.pattern_id,
                "total_monthly_excess": total,
                "n_months": len(excess_monthly),
                "top1_share": float(ordered.iloc[0] / total) if total else float("nan"),
                "top3_share": float(ordered.iloc[:3].sum() / total) if total else float("nan"),
                "top1_month": str(ordered.index[0]),
                "top3_months": [str(i) for i in ordered.index[:3]],
                "n_positive_months": int((excess_monthly > 0).sum()),
            }
        )

    # k sensitivity: k/2 and 2k, cost and drawdown only (Sharpe cannot move).
    sensitivity = []
    for scale in (0.5, 2.0):
        for base_key, base_pattern_id, arm in build_dm_overlay_grid():
            if base_key != "ff3":
                continue
            alt = build_overlay(
                base_key,
                base_pattern_id,
                arm,
                base_returns[base_key],
                market_monthly_returns=market_monthly,
                market_daily_returns=market_daily,
                cost_bps=config.cost_bps,
                normalization_scale=scale,
            )
            sensitivity.append(
                {
                    "pattern_id": alt.pattern_id,
                    "k_scale": scale,
                    "sharpe": sharpe_ratio(alt.returns),
                    "overlay_cost_total": alt.overlay_cost_total,
                    "max_drawdown": compute_preservation_metrics(
                        alt.returns, dsr=1.0
                    ).max_drawdown,
                }
            )

    payload = {
        "run_tag": RUN_TAG,
        "run_end": RUN_END.isoformat(),
        "formation_start": start.isoformat(),
        "n_trials": DM_OVERLAY_N_TRIALS,
        "sigma_sr_pooled_30": sigma_sr,
        "universe_size": universe_size,
        "sample_size": len(sample),
        "n_missing_price": len(missing_price),
        "panel_start": close.index[0].date().isoformat(),
        "panel_end": close.index[-1].date().isoformat(),
        "cost_bps": config.cost_bps,
        "factor_vintage": factors.vintage_line.strip(),
        "factor_last_month": factors.last_month_end.date().isoformat(),
        "bear_months": [d.isoformat() for d in bear_months],
        "n_market_months_in_window": int(window.notna().sum()),
        "base_sharpes_18": base_sharpes_18,
        "base_dsr_18": {r.pattern_id: r.deflated_sharpe.dsr for r in base_results},
        "rows": rows,
        "diagnostics": diagnostics_extra,
        "k_sensitivity": sensitivity,
        "extra_lag_probe": extra_lag,
        "episode_concentration": concentration,
        "downside": downside_rows,
        "dyn_coefficient_path": coefficient_path,
        "score_diagnostics": {
            "n_scored": score_diagnostics.n_scored,
            "n_refused": dict(score_diagnostics.n_refused),
            "n_month_windows": score_diagnostics.n_month_windows,
            "n_months_without_factor_coverage": score_diagnostics.n_months_without_factor_coverage,
        },
        "elapsed_seconds": time.time() - t0,
    }
    out = Path(_BACKEND) / "data" / "research_runs" / f"{RUN_TAG}.json"
    out.write_text(json.dumps(payload, indent=2, default=str))
    logger.info("wrote %s in %.0fs", out, time.time() - t0)

    # --- console summary ------------------------------------------------------
    print("\n" + "=" * 100)
    print(f"{'spec':<26} {'reg':>4} {'Sharpe':>8} {'base':>8} {'DSR':>7} {'PSR':>7} "
          f"{'maxDD':>8} {'baseDD':>8} {'dDD':>8} {'presv':>7}")
    print("=" * 100)
    for r in sorted(rows, key=lambda r: -r["sharpe"]):
        print(
            f"{r['pattern_id']:<26} {'Y' if r['registrable'] else '-':>4} "
            f"{r['sharpe']:>+8.4f} {r['sharpe_base']:>+8.4f} "
            f"{(r['dsr'] if r['dsr'] is not None else float('nan')):>7.4f} "
            f"{(r['psr_vs_zero'] if r['psr_vs_zero'] is not None else float('nan')):>7.4f} "
            f"{r['max_drawdown']:>+8.4f} {r['max_drawdown_base']:>+8.4f} "
            f"{r['max_drawdown_delta']:>+8.4f} {r['preservation_score']:>7.5f}"
        )
    print("=" * 100)
    for k, v in diagnostics_extra.items():
        print(f"{k}: {v:+.6f}")
    print("\nlook-ahead probe (weight delayed one further month):")
    for e in extra_lag:
        print(f"  {e['pattern_id']:<24} headline {e['sharpe_headline']:+.4f} -> "
              f"+1m lag {e['sharpe_extra_lag_1m']:+.4f}  (dd {e['max_drawdown_extra_lag_1m']:+.4f})")
    print("\ndownside metrics (overlay vs its own base):")
    for r in downside_rows:
        print(f"  {r['pattern_id']:<24} worstM {r['overlay_worst_month']:+.4f}/{r['base_worst_month']:+.4f} "
              f"worstD {r['overlay_worst_day']:+.4f}/{r['base_worst_day']:+.4f} "
              f"dsdev {r['overlay_downside_deviation_ann']:.4f}/{r['base_downside_deviation_ann']:.4f} "
              f"var95 {r['overlay_var95_daily']:+.5f}/{r['base_var95_daily']:+.5f} "
              f"M<-5% {r['overlay_n_months_below_minus5pct']}/{r['base_n_months_below_minus5pct']}")
    print("\ndyn expanding-window intercept path:")
    for k, v in coefficient_path.items():
        print(f"  {k}: {v['n_estimated_months']} months from {v['first_month']}, "
              f"g0 in [{v['g0_min']:+.5f}, {v['g0_max']:+.5f}], "
              f"{v['n_months_g0_negative']} months g0<0, {v['g0_sign_changes']} sign changes")
    print("\nepisode concentration of the overlay's monthly excess return:")
    for c in concentration:
        print(f"  {c['pattern_id']:<24} total {c['total_monthly_excess']:+.4f} "
              f"top1 {c['top1_share']:+.3f} top3 {c['top3_share']:+.3f} "
              f"pos {c['n_positive_months']}/{c['n_months']}  best {c['top1_month']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
