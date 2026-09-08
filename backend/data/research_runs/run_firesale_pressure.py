"""Production runner for the Coval-Stafford (2007) mutual-fund fire-sale family.

Builds the Eq.(4) PRESSURE panels from the cached N-PORT bulk data, replays the
24 pre-registered calendar-time specs across both universes, computes DSR
across the policy ladder and preservation_score for every spec, applies the
pre-registered verdict rule and the four binding interpretive checks, persists
every spec to cross_sectional_trial_results, and writes the git-durable text
and JSON reports.

Run from backend/ with
    ./venv/bin/python data/research_runs/run_firesale_pressure.py

REQUIRES the UNION N-PORT cache at data/nport_bulk_firesale, built by
data/research_runs/fetch_nport_bulk_firesale.py. It deliberately does NOT read
data/nport_bulk: that cache was filtered to S&P 500 CUSIPs only at fetch time
(599 distinct ISSUER_CUSIPs, verified), so reading it would return an empty
S&P 600 arm rather than an error. This runner does not download anything as a
side effect.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

# WORKTREE BINDING GUARD — load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv, whose site-packages
# can resolve `app` to the MAIN worktree's backend/app. Without this the run
# would silently screen main's code instead of this branch's. (The FIT family
# hit exactly this and had a script rewrite main's inventory file.)
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app  # noqa: E402

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND})."
    )

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.services.market_data.nport_provider import NportProvider  # noqa: E402
from app.services.market_data.yfinance_provider import YFinanceProvider  # noqa: E402
from app.services.research_lab.borrow_cost import (  # noqa: E402
    GENERAL_COLLATERAL_BPS_PER_YEAR,
)
from app.services.research_lab.cross_sectional_firesale_pressure import (  # noqa: E402
    FIRESALE_CITATION,
    FIRESALE_CUTOFF,
    FIRESALE_FAMILY_KEY,
    FIRESALE_FORMATION_START,
    FIRESALE_N_TRIALS,
    FIRESALE_SMALL_CAP_FAMILY_KEY,
    FLOW_THRESHOLDS,
    INFLOW_CUTOFF,
    LEGS,
    WEIGHTINGS,
    FiresaleSpecResult,
    build_pressure_panels,
    calendar_time_returns,
    evaluate_specs,
    spec_id_for,
    verdict_for,
)
from app.services.research_lab.cross_sectional_nport_flow import (  # noqa: E402
    build_split_adjustment,
    load_cusip_ticker_map,
    load_nport_quarters,
)
from app.services.research_lab.cross_sectional_persistence import (  # noqa: E402
    persist_cross_sectional_trial_results,
    verify_persisted_trial_results,
)
from app.services.research_lab.spread_estimator import (  # noqa: E402
    build_calibrated_half_spread_frame,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("firesale")

RUN_TAG = "firesale_pressure_build_2026-09-08"
REPORT_PATH = "data/research_runs/coval_stafford_firesale_2026-09-08.txt"
JSON_PATH = "data/research_runs/coval_stafford_firesale_2026-09-08.json"
PANEL_DIR = "data/research_runs/firesale_samples"
RUN_END = date(2026, 9, 8)
# NOT data/nport_bulk — see the module docstring.
NPORT_CACHE_DIR = _BACKEND / "data" / "nport_bulk_firesale"
BAR = 0.95

FAMILY_KEY_BY_UNIVERSE = {
    "sp500": FIRESALE_FAMILY_KEY,
    "sp600": FIRESALE_SMALL_CAP_FAMILY_KEY,
}


def _universe_api(universe: str):
    if universe == "sp500":
        from app.services.research_lab import sp500_membership_history as mod
    else:
        from app.services.research_lab import small_cap_membership_history as mod
    return mod


def _coverage_end(mod, fallback: date) -> date:
    """The last date this universe has point-in-time membership for.

    Necessary, not defensive: S&P 500 membership coverage ends 2026-06-30 while
    N-PORT and prices run to today, and get_universe_as_of RAISES past the end
    rather than quietly returning a stale roster. Formations must stop at the
    membership wall, not at the price wall, or the last two months would be
    formed against an assumed-unchanged index.
    """
    fn = getattr(mod, "membership_coverage_end", None)
    if fn is not None:
        return min(fallback, fn())
    probe = fallback
    floor = fallback - timedelta(days=800)
    while probe > floor:
        try:
            mod.get_universe_as_of(probe)
            return probe
        except Exception:  # noqa: BLE001 — the module raises its own typed error
            probe -= timedelta(days=1)
    raise SystemExit(f"no point-in-time membership found within 800 days of {fallback}")


def _build_market_cap(provider, close, splits, tickers):
    """Point-in-time market cap, reusing cross_sectional_ivol's builder.

    Best-effort by design: yfinance's shares-outstanding endpoint is sparse and
    slow, and a ticker without a usable count simply does not receive a value
    weight. Coverage is REPORTED rather than assumed, because a value-weighted
    arm silently running on a third of its universe would be a different
    strategy than the one pre-registered.
    """
    from app.services.research_lab.cross_sectional_ivol import build_point_in_time_market_cap

    shares, missing = provider.get_shares_outstanding(
        list(tickers), close.index[0].date(), close.index[-1].date()
    )
    frame, dropped = build_point_in_time_market_cap(close, shares, splits)
    return frame, missing, dropped


def main() -> int:
    started = time.time()
    warnings: list[str] = []
    provider = YFinanceProvider()
    nport = NportProvider(cache_dir=NPORT_CACHE_DIR)

    quarters = nport.cached_quarters()
    if not quarters:
        raise SystemExit(
            f"no N-PORT quarters cached in {NPORT_CACHE_DIR} — run "
            "data/research_runs/fetch_nport_bulk_firesale.py first"
        )
    logger.info("N-PORT quarters cached: %d (%s .. %s)", len(quarters), quarters[0], quarters[-1])

    universe_results = []
    all_returns: dict[str, pd.Series] = {}
    per_universe_payload = {}

    for universe in ("sp500", "sp600"):
        mod = _universe_api(universe)
        start = FIRESALE_FORMATION_START
        # A year of lookback plus a quarter of skip before the first formation.
        history_start = start - timedelta(days=500)
        end = _coverage_end(mod, RUN_END)
        if end < RUN_END:
            warnings.append(
                f"[{universe}] formations stop at {end} (point-in-time membership coverage end), "
                f"not {RUN_END}; prices and N-PORT run later but the index roster does not"
            )
        names = mod.get_universe_over(max(mod.MEMBERSHIP_DATA_START, history_start), end)
        logger.info("[%s] universe over window: %d tickers", universe, len(names))

        cusip_map, empty_archives = load_cusip_ticker_map(names)
        if empty_archives:
            warnings.append(
                f"[{universe}] {len(empty_archives)} cached fails-to-deliver archives "
                f"contributed zero CUSIP rows"
            )
        midpoint = history_start + (end - history_start) / 2
        cusip_to_ticker: dict[str, str] = {}
        ambiguous = 0
        for cusip in cusip_map.observations:
            at_mid = cusip_map.resolve(cusip, midpoint)
            if at_mid is None:
                continue
            cusip_to_ticker[cusip] = at_mid
            if (
                cusip_map.resolve(cusip, history_start) != at_mid
                or cusip_map.resolve(cusip, end) != at_mid
            ):
                ambiguous += 1
        if ambiguous:
            warnings.append(
                f"[{universe}] {ambiguous} of {len(cusip_to_ticker)} CUSIPs resolve to a "
                "different ticker at a sample endpoint than at the midpoint; the midpoint "
                "answer is used"
            )
        logger.info("[%s] resolved %d CUSIPs", universe, len(cusip_to_ticker))

        filings, holdings, _returns_by_acc, load_diag = load_nport_quarters(
            nport, quarters, set(cusip_to_ticker)
        )
        logger.info(
            "[%s] %d filings, %d accessions with holdings", universe, len(filings), len(holdings)
        )

        frames, missing_price = provider.get_daily_ohlcv(names, history_start, end)
        frames = {k: v.loc[v.index <= pd.Timestamp(end)] for k, v in frames.items()}
        close = frames["close"]
        if close.empty:
            raise SystemExit(f"[{universe}] no price data resolved")
        if missing_price:
            warnings.append(
                f"[{universe}] {len(missing_price)} of {len(names)} tickers resolved no price "
                "data (the standing departed-member yfinance gap)"
            )

        cap_close, splits_by_ticker, _cap_missing = provider.get_market_cap_basis(
            list(close.columns), history_start, end
        )
        split_adjustments = build_split_adjustment(splits_by_ticker, close.index)

        panels, pdiag = build_pressure_panels(
            close,
            filings,
            holdings,
            cusip_to_ticker,
            split_adjustments,
            formation_start=start,
            flow_thresholds=FLOW_THRESHOLDS,
            include_unconstrained=True,
        )
        logger.info(
            "[%s] pressure measured on %d stock-snapshots (%d refused for <10 owners)",
            universe,
            pdiag.n_measured,
            pdiag.n_below_min_owners,
        )

        # Persist the derived panels so every number below is re-derivable with
        # no network call and without the ~7GB N-PORT cache.
        panel_dir = _BACKEND / PANEL_DIR
        panel_dir.mkdir(parents=True, exist_ok=True)
        for name, frame in panels.items():
            if frame.empty:
                continue
            frame.to_csv(panel_dir / f"{universe}_{name}.csv.gz", compression="gzip")

        market_cap, mc_missing, mc_dropped = _build_market_cap(
            provider, cap_close, splits_by_ticker, list(close.columns)
        )
        # get_market_cap_basis returns its OWN close (split-adjusted,
        # dividend-unadjusted) on its own index; the portfolio indexes by dates
        # taken from the PRICE frame, so the two must be aligned explicitly.
        # Forward-fill only — each date takes the most recent known cap.
        market_cap = market_cap.reindex(index=close.index, columns=close.columns).ffill()
        if mc_missing or mc_dropped:
            warnings.append(
                f"[{universe}] value-weight arm: {len(mc_missing)} tickers had no "
                f"shares-outstanding series and {len(mc_dropped)} were dropped by the "
                "market-cap builder; those names fall out of the value-weighted portfolios"
            )

        half_spread, calibration = build_calibrated_half_spread_frame(
            frames["open"],
            frames["high"],
            frames["low"],
            close,
            calibration_start=pd.Timestamp(start),
        )
        logger.info("[%s] half-spread: %s", universe, calibration.summary())

        results: list[FiresaleSpecResult] = []
        leg_diag_by_key: dict[str, dict] = {}
        returns_here: dict[str, pd.Series] = {}

        for threshold in FLOW_THRESHOLDS:
            panel = panels[f"constrained_{threshold:g}"]
            for weighting in WEIGHTINGS:
                for cost_arm, hs, borrow in (
                    ("baseline", half_spread, GENERAL_COLLATERAL_BPS_PER_YEAR),
                    ("zero_cost", None, 0.0),
                ):
                    long_r, short_r, ls_r, ldiag = calendar_time_returns(
                        panel,
                        close,
                        members_on=mod.get_universe_as_of,
                        market_cap=market_cap if weighting == "value" else None,
                        half_spread=hs,
                        formation_start=start,
                        borrow_bps_per_year=borrow,
                        weighting=weighting,
                    )
                    by_leg = {"long": long_r, "short": short_r, "long_short": ls_r}
                    for leg in LEGS:
                        sid = spec_id_for(universe, threshold, leg, weighting, cost_arm)
                        returns_here[sid] = by_leg[leg]
                        leg_diag_by_key[sid] = {
                            "n_months": ldiag.n_months,
                            "n_long_formable": ldiag.n_long_formable,
                            "n_short_formable": ldiag.n_short_formable,
                            "formable_fraction": ldiag.formable_fraction(leg),
                            "mean_long_size": (
                                float(np.mean(ldiag.long_sizes)) if ldiag.long_sizes else 0.0
                            ),
                            "mean_short_size": (
                                float(np.mean(ldiag.short_sizes)) if ldiag.short_sizes else 0.0
                            ),
                        }

        # THE PAPER'S OWN CONTROL (C1). Same construction, flow condition
        # removed. Reported separately and NEVER folded into the DSR grid.
        unconstrained_returns: dict[str, pd.Series] = {}
        if not panels["unconstrained"].empty:
            for weighting in WEIGHTINGS:
                long_r, short_r, ls_r, _ld = calendar_time_returns(
                    panels["unconstrained"],
                    close,
                    members_on=mod.get_universe_as_of,
                    market_cap=market_cap if weighting == "value" else None,
                    half_spread=None,
                    formation_start=start,
                    borrow_bps_per_year=0.0,
                    weighting=weighting,
                )
                unconstrained_returns[f"{universe}/unconstrained_long_{weighting}"] = long_r
                unconstrained_returns[f"{universe}/unconstrained_long_short_{weighting}"] = ls_r

        per_universe_payload[universe] = {
            "n_tickers": len(names),
            "n_cusips": len(cusip_to_ticker),
            "n_filings": len(filings),
            "pressure_diagnostics": {
                "n_snapshots": pdiag.n_snapshots,
                "n_stock_snapshots_attempted": pdiag.n_stock_snapshots_attempted,
                "n_below_min_owners": pdiag.n_below_min_owners,
                "n_measured": pdiag.n_measured,
                "n_firesale_flags": {str(k): v for k, v in pdiag.n_firesale_flags.items()},
                "n_inflow_flags": {str(k): v for k, v in pdiag.n_inflow_flags.items()},
                "owner_counts": pdiag.owner_count_summary(),
            },
            "leg_diagnostics": leg_diag_by_key,
            "half_spread_calibration": calibration.summary(),
            "unconstrained_control": {
                k: {
                    "mean_monthly": float(v.mean()) if len(v) else None,
                    "cumulative": float((1 + v).prod() - 1) if len(v) else None,
                    "n_months": int(len(v)),
                }
                for k, v in unconstrained_returns.items()
            },
        }
        all_returns.update(returns_here)
        universe_results.append((universe, returns_here, leg_diag_by_key))

    # ---- one evaluation over the whole pre-registered grid ------------------
    # The 24-spec grid is the BASELINE cost arm; the zero-cost arm is a
    # robustness report, not extra specs, so it is evaluated separately and
    # cannot inflate the denominator.
    baseline = {k: v for k, v in all_returns.items() if k.endswith("_baseline")}
    zero_cost = {k: v for k, v in all_returns.items() if k.endswith("_zero_cost")}
    assert len(baseline) == FIRESALE_N_TRIALS, f"expected 24 baseline specs, got {len(baseline)}"

    # Persist the realized monthly return series for every spec, so the DSR,
    # the preservation score and the verdict can all be re-derived by a
    # verification script that never imports this family's code.
    panel_dir = _BACKEND / PANEL_DIR
    panel_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_returns).sort_index().to_csv(
        panel_dir / "spec_monthly_returns.csv.gz", compression="gzip"
    )

    dsr_base, sharpe_base, pres_base, denominators = evaluate_specs(baseline)
    dsr_zero, sharpe_zero, pres_zero, _ = evaluate_specs(zero_cost)

    def _rank(dsr_map, sharpes):
        ordered = sorted(
            dsr_map.items(),
            key=lambda kv: (
                kv[1].get(denominators[0]) if kv[1].get(denominators[0]) is not None else -1.0
            ),
            reverse=True,
        )
        return ordered

    ranked = _rank(dsr_base, sharpe_base)
    best_spec, best_dsr_map = ranked[0]
    verdict, rationale = verdict_for(best_dsr_map, denominators, bar=BAR)

    ranked_zero = _rank(dsr_zero, sharpe_zero)
    best_zero_spec, best_zero_map = ranked_zero[0]
    verdict_zero, _ = verdict_for(best_zero_map, denominators, bar=BAR)

    # ---- persist ------------------------------------------------------------
    results_by_universe: dict[str, list[FiresaleSpecResult]] = {"sp500": [], "sp600": []}
    from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe

    sigma = float(np.std(list(sharpe_base.values()), ddof=1))
    for sid, series in baseline.items():
        # spec_id shape: "<universe>/cs_flow<threshold>_<leg>_<weighting>_<arm>"
        # Parsed with an explicit regex rather than positional splitting: the
        # leg "long_short" itself contains an underscore, which is exactly what
        # broke the first attempt at this.
        match = re.fullmatch(
            r"(?P<universe>[^/]+)/cs_flow(?P<threshold>[0-9.]+)_"
            r"(?P<leg>long_short|long|short)_(?P<weighting>equal|value)_(?P<arm>\w+)",
            sid,
        )
        if match is None:
            raise ValueError(f"unparseable spec_id {sid!r}")
        universe = match["universe"]
        clean = series.dropna()
        deflated = compute_deflated_sharpe(
            sharpe_base[sid], clean, denominators[0], sigma, periods_per_year=12.0
        )
        results_by_universe[universe].append(
            FiresaleSpecResult(
                spec_id=sid,
                universe=universe,
                flow_threshold=float(match["threshold"]),
                leg=match["leg"],
                weighting=match["weighting"],
                cost_arm="baseline",
                sharpe_annualized=sharpe_base[sid],
                n_trading_days=int(len(clean)),
                mean_monthly_return=float(clean.mean()) if len(clean) else 0.0,
                dsr_by_n={int(k): v for k, v in dsr_base[sid].items()},
                preservation_score=pres_base[sid],
                formable_fraction=float(
                    next(
                        (d[sid]["formable_fraction"] for _u2, _r, d in universe_results if sid in d),
                        0.0,
                    )
                ),
                deflated_sharpe=deflated,
            )
        )

    db = SessionLocal()
    try:
        written = 0
        for universe, rows in results_by_universe.items():
            if rows:
                written += persist_cross_sectional_trial_results(
                    db, FAMILY_KEY_BY_UNIVERSE[universe], rows, run_tag=RUN_TAG
                )
        verify_persisted_trial_results(db, RUN_TAG, written)
        logger.info("persisted %d rows", written)
    finally:
        db.close()

    # ---- reports ------------------------------------------------------------
    payload = {
        "family": "coval_stafford_firesale_pressure",
        "citation": FIRESALE_CITATION,
        "run_tag": RUN_TAG,
        "run_end": RUN_END.isoformat(),
        "formation_start": FIRESALE_FORMATION_START.isoformat(),
        "n_local": FIRESALE_N_TRIALS,
        "denominators": denominators,
        "bar": BAR,
        "cutoffs": {"firesale": FIRESALE_CUTOFF, "inflow": INFLOW_CUTOFF},
        "flow_thresholds": list(FLOW_THRESHOLDS),
        "verdict": verdict,
        "verdict_rationale": rationale,
        "best_spec": best_spec,
        "best_dsr_by_n": {str(k): v for k, v in best_dsr_map.items()},
        "best_preservation_score": pres_base[best_spec],
        "zero_cost_verdict": verdict_zero,
        "zero_cost_best_spec": best_zero_spec,
        "zero_cost_best_dsr_by_n": {str(k): v for k, v in best_zero_map.items()},
        "specs": {
            sid: {
                "sharpe_annualized": sharpe_base[sid],
                "dsr_by_n": {str(k): v for k, v in dsr_base[sid].items()},
                "preservation_score": pres_base[sid],
                "n_months": int(len(baseline[sid].dropna())),
                "mean_monthly_return": float(baseline[sid].dropna().mean())
                if len(baseline[sid].dropna())
                else None,
            }
            for sid in sorted(baseline)
        },
        "zero_cost_specs": {
            sid: {
                "sharpe_annualized": sharpe_zero[sid],
                "dsr_by_n": {str(k): v for k, v in dsr_zero[sid].items()},
                "preservation_score": pres_zero[sid],
            }
            for sid in sorted(zero_cost)
        },
        "universes": per_universe_payload,
        "warnings": warnings,
        "elapsed_seconds": time.time() - started,
    }
    (_BACKEND / JSON_PATH).write_text(json.dumps(payload, indent=2, default=str) + "\n")

    lines = []
    lines.append("COVAL & STAFFORD (2007) MUTUAL-FUND FIRE SALES — RUN REPORT")
    lines.append("=" * 74)
    lines.append(f"run_tag           {RUN_TAG}")
    lines.append(f"citation          {FIRESALE_CITATION}")
    lines.append(f"pre-registration  coval_stafford_firesale_PREREGISTRATION.txt (commit 3a81d63)")
    lines.append(f"formations        {FIRESALE_FORMATION_START} .. {RUN_END}")
    lines.append(f"grid              {FIRESALE_N_TRIALS} baseline specs; ladder {denominators}; bar {BAR}")
    lines.append("")
    lines.append(f"VERDICT           {verdict}")
    lines.append(f"                  {rationale}")
    lines.append(f"best spec         {best_spec}")
    lines.append(f"  sharpe          {sharpe_base[best_spec]:.4f}")
    lines.append(f"  DSR by N        {best_dsr_map}")
    lines.append(f"  preservation    {pres_base[best_spec]}")
    lines.append("")
    lines.append(f"ZERO-COST ARM     {verdict_zero} (best {best_zero_spec}, DSR {best_zero_map})")
    lines.append("")
    lines.append("ALL 24 BASELINE SPECS, ranked by DSR at the most lenient rung")
    lines.append("-" * 74)
    for sid, dmap in ranked:
        lines.append(
            f"  {sid:<52} SR {sharpe_base[sid]:+.4f}  "
            f"DSR@{denominators[0]} {dmap[denominators[0]]}  pres {pres_base[sid]}"
        )
    lines.append("")
    for universe, data in per_universe_payload.items():
        lines.append(f"[{universe}] DIAGNOSTICS")
        lines.append("-" * 74)
        pd_ = data["pressure_diagnostics"]
        lines.append(f"  tickers {data['n_tickers']}  cusips {data['n_cusips']}  filings {data['n_filings']}")
        lines.append(
            f"  stock-snapshots measured {pd_['n_measured']} "
            f"(refused <10 owners: {pd_['n_below_min_owners']})"
        )
        lines.append(f"  owner counts {pd_['owner_counts']}")
        lines.append(f"  fire-sale flags {dict(pd_['n_firesale_flags'])}")
        lines.append(f"  inflow flags    {dict(pd_['n_inflow_flags'])}")
        lines.append(f"  C1 unconstrained control: {data['unconstrained_control']}")
        lines.append("")
    if warnings:
        lines.append("WARNINGS")
        lines.append("-" * 74)
        for w in warnings:
            lines.append(f"  - {w}")
    report = "\n".join(lines) + "\n"
    (_BACKEND / REPORT_PATH).write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
