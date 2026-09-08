"""Production run for the Frazzini-Lamont (2008) "Dumb Money" family.

Executes the 24-spec grid frozen in
data/research_runs/frazzini_lamont_dumb_money_PREREGISTRATION.txt (committed
BEFORE this script produced any return), persists every spec to
cross_sectional_trial_results, and writes the JSON/TXT reports plus the derived
panels needed to re-derive every number without the ~7GB N-PORT cache.

Grid: 4 horizons (Table 2's rows minus the infeasible 5-year) x 3 legs x 2
universes = 24 specs, each at a baseline-cost and a zero-cost arm.

Also computed, all OUTSIDE the DSR grid and labelled as such:
  * check C1 -- Fama-French three-factor alpha and loadings per long-short spec
  * check C2 -- months of returns and formable months per arm
  * check C5 -- FLOW monotonicity/widening and scale vs Table 2A / Table 1C
  * robustness -- the Appendix Table A1 counterfactual reading
  * exploratory -- 50%/90% equity-fund threshold sensitivity

Run from backend/ with
    ./venv/bin/python data/research_runs/run_dumb_money.py
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

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

from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.services.market_data.fama_french_provider import load_fama_french_monthly  # noqa: E402
from app.services.market_data.nport_provider import (  # noqa: E402
    NportProvider,
    build_fund_quarter_filings,
    build_holding_rows,
    parse_float,
)
from app.services.market_data.yfinance_provider import YFinanceProvider  # noqa: E402
from app.services.research_lab.borrow_cost import (  # noqa: E402
    GENERAL_COLLATERAL_BPS_PER_YEAR,
)
from app.services.research_lab.cross_sectional_dumb_money import (  # noqa: E402
    DUMB_MONEY_CITATION,
    DUMB_MONEY_FAMILY_KEY,
    DUMB_MONEY_N_TRIALS,
    DUMB_MONEY_SMALL_CAP_FAMILY_KEY,
    EQUITY_ASSET_SHARE_MIN,
    HORIZON_QUARTERS,
    CounterfactualVariant,
    DumbMoneyDiagnostics,
    Leg,
    build_flow_panels,
    build_fund_quarter_states,
    equity_fund_series,
    evaluate_specs,
    latest_public_quarter,
    month_end_snapshots,
    quintile_portfolio_returns,
    spec_id_for,
    verdict_for,
)
from app.services.research_lab.cross_sectional_nport_flow import (  # noqa: E402
    fund_monthly_returns,
    load_cusip_ticker_map,
)
from app.services.research_lab.cross_sectional_persistence import (  # noqa: E402
    persist_cross_sectional_trial_results,
    verify_persisted_trial_results,
)
from app.services.research_lab.spread_estimator import (  # noqa: E402
    build_calibrated_half_spread_frame,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout
)
logger = logging.getLogger("run_dumb_money")

RUN_TAG = "dumb_money_2026-09-08"
RUN_END = date(2026, 9, 8)
BAR = 0.95
# The S&P 500 + S&P 600 union cache built for the fire-sale family; its
# holdings cover both universes' CUSIPs. Reused deliberately -- the S&P
# 500-only data/nport_bulk would return a SILENTLY EMPTY small-cap arm.
NPORT_CACHE_DIR = _BACKEND / "data" / "nport_bulk_firesale"
ASSET_CATEGORY_DIR = _BACKEND / "data" / "nport_fund_asset_categories"
PANEL_DIR = _BACKEND / "data" / "research_runs" / "dumb_money_panels"
REPORT_STEM = _BACKEND / "data" / "research_runs" / "dumb_money_2026-09-08"

FAMILY_KEY_BY_UNIVERSE = {
    "sp500": DUMB_MONEY_FAMILY_KEY,
    "sp600": DUMB_MONEY_SMALL_CAP_FAMILY_KEY,
}


@dataclass
class SpecResult:
    """Field names spec_id / sharpe_annualized / deflated_sharpe /
    n_trading_days are what persist_cross_sectional_trial_results requires;
    they are not free-form."""

    spec_id: str
    universe: str
    horizon: str
    leg: str
    cost_arm: str
    sharpe_annualized: float
    n_trading_days: int
    mean_monthly_return: float
    dsr_by_n: dict[int, float | None]
    preservation_score: float | None
    formable_fraction: float
    deflated_sharpe: object = None


def _universe_api(universe: str):
    if universe == "sp500":
        from app.services.research_lab import sp500_membership_history as mod
    else:
        from app.services.research_lab import small_cap_membership_history as mod
    return mod


def _coverage_end(mod, fallback: date) -> date:
    """The last date this universe has point-in-time membership for.

    Necessary, not defensive: get_universe_as_of RAISES past the coverage end
    rather than quietly returning a stale roster, so formations must stop at
    the MEMBERSHIP wall, not the price wall — otherwise the final months would
    be formed against an assumed-unchanged index. Same helper as
    run_firesale_pressure.py.
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


def _members_on(mod, coverage_end: date):
    """get_universe_as_of, but empty past the membership wall instead of
    raising. A month with no roster is skipped entirely rather than being
    formed against a stale one."""

    def members(day: date) -> list[str]:
        if day > coverage_end:
            return []
        try:
            return mod.get_universe_as_of(day)
        except Exception:  # noqa: BLE001 — typed error from the membership module
            return []

    return members


def load_asset_categories(quarters: list[str]) -> list[dict[str, str]]:
    """Per-accession, per-ASSET_CAT totals from the cache built by
    fetch_nport_fund_asset_categories.py."""
    rows: list[dict[str, str]] = []
    for quarter in quarters:
        path = ASSET_CATEGORY_DIR / f"{quarter}_FUND_ASSET_CATEGORY.csv.gz"
        if not path.exists():
            continue
        rows.extend(pd.read_csv(path, dtype=str).to_dict("records"))
    return rows


def load_inputs(nport: NportProvider, quarters: list[str], cusips: set[str]):
    """(filings, holdings VALUE by accession, monthly returns by accession).

    Deliberately NOT cross_sectional_nport_flow.load_nport_quarters: that
    collapses holdings to SHARE COUNTS, which is what Lou's Eq.(3) needs.
    Frazzini-Lamont Eq.(6) needs the DOLLAR VALUE of each position, because
    w_ijt * TNA^i_t IS that dollar value. The same build_holding_rows filter
    (long common equity in shares, no 999999999 placeholder) is reused
    unchanged; only the field summed differs.
    """
    filings = []
    holdings: dict[str, dict[str, float]] = defaultdict(dict)
    returns: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    diagnostics = None

    for quarter in quarters:
        quarter_filings, diagnostics = build_fund_quarter_filings(
            nport.submissions(quarter), nport.fund_reported_info(quarter), diagnostics
        )
        filings.extend(quarter_filings)
        rows, diagnostics = build_holding_rows(nport.holdings(quarter, cusips), diagnostics)
        for row in rows:
            book = holdings[row.accession]
            book[row.cusip] = book.get(row.cusip, 0.0) + row.value_usd
        for record in nport.monthly_total_returns(quarter):
            values = tuple(
                parse_float(record.get(f"MONTHLY_TOTAL_RETURN{n}", "")) for n in (1, 2, 3)
            )
            if any(v is None for v in values):
                continue
            returns[record["ACCESSION_NUMBER"]].append(values)

    seen: set[str] = set()
    unique = []
    for filing in filings:
        if filing.accession in seen:
            continue
        seen.add(filing.accession)
        unique.append(filing)
    return unique, dict(holdings), dict(returns), diagnostics


def ff3_regression(returns: pd.Series, factors: pd.DataFrame) -> dict[str, float] | None:
    """Check C1: the paper's own Table 3 control. Monthly alpha and MKT/SMB/HML
    loadings, with t-statistics."""
    joined = pd.concat(
        [returns.rename("y"), factors[["mkt_rf", "smb", "hml"]]], axis=1, join="inner"
    ).dropna()
    if len(joined) < 24:
        return None
    y = joined["y"].to_numpy()
    # Column names are the provider's own (FACTOR_COLUMNS), decimal units.
    x = np.column_stack(
        [np.ones(len(joined))] + [joined[c].to_numpy() for c in ("mkt_rf", "smb", "hml")]
    )
    coefficients, *_ = np.linalg.lstsq(x, y, rcond=None)
    residuals = y - x @ coefficients
    dof = len(joined) - x.shape[1]
    sigma2 = float(residuals @ residuals) / dof
    covariance = sigma2 * np.linalg.inv(x.T @ x)
    errors = np.sqrt(np.diag(covariance))
    names = ("alpha", "mkt", "smb", "hml")
    out: dict[str, float] = {"n_months": float(len(joined))}
    for position, name in enumerate(names):
        out[name] = float(coefficients[position])
        out[f"{name}_t"] = float(coefficients[position] / errors[position]) if errors[position] else 0.0
    return out


def main() -> int:
    started = time.time()
    warnings: list[str] = []
    provider = YFinanceProvider()
    nport = NportProvider(cache_dir=NPORT_CACHE_DIR)

    quarters = nport.cached_quarters()
    if not quarters:
        raise SystemExit(f"no N-PORT quarters cached in {NPORT_CACHE_DIR}")
    logger.info("N-PORT quarters cached: %d (%s .. %s)", len(quarters), quarters[0], quarters[-1])

    # ---- universes and the CUSIP -> ticker map ------------------------------
    universe_names: dict[str, list[str]] = {}
    coverage_ends: dict[str, date] = {}
    history_start = date(2019, 1, 1)
    for universe in ("sp500", "sp600"):
        mod = _universe_api(universe)
        end = _coverage_end(mod, RUN_END)
        coverage_ends[universe] = end
        if end < RUN_END:
            warnings.append(
                f"[{universe}] formations stop at {end} (point-in-time membership coverage "
                f"end), not {RUN_END}"
            )
        universe_names[universe] = mod.get_universe_over(
            max(mod.MEMBERSHIP_DATA_START, history_start), end
        )
        logger.info("[%s] %d tickers over window", universe, len(universe_names[universe]))

    union = sorted(set(universe_names["sp500"]) | set(universe_names["sp600"]))
    cusip_map, empty_archives = load_cusip_ticker_map(union)
    if empty_archives:
        warnings.append(f"{len(empty_archives)} cached FTD archives contributed zero CUSIP rows")
    midpoint = history_start + (RUN_END - history_start) / 2
    cusip_to_ticker: dict[str, str] = {}
    ambiguous = 0
    for cusip in cusip_map.observations:
        at_mid = cusip_map.resolve(cusip, midpoint)
        if at_mid is None:
            continue
        cusip_to_ticker[cusip] = at_mid
        if (
            cusip_map.resolve(cusip, history_start) != at_mid
            or cusip_map.resolve(cusip, RUN_END) != at_mid
        ):
            ambiguous += 1
    if ambiguous:
        warnings.append(
            f"{ambiguous} of {len(cusip_to_ticker)} CUSIPs resolve to a different ticker at a "
            "sample endpoint than at the midpoint; the midpoint answer is used"
        )
    logger.info("resolved %d CUSIPs over %d union tickers", len(cusip_to_ticker), len(union))

    # ---- N-PORT ------------------------------------------------------------
    filings, holdings_by_accession, returns_by_accession, load_diag = load_inputs(
        nport, quarters, set(cusip_to_ticker)
    )
    logger.info(
        "%d filings, %d accessions with holdings", len(filings), len(holdings_by_accession)
    )

    accession_to_series = {f.accession: f.series_id for f in filings}
    category_rows = load_asset_categories(quarters)
    if not category_rows:
        raise SystemExit(
            f"no asset-category data in {ASSET_CATEGORY_DIR} — run "
            "data/research_runs/fetch_nport_fund_asset_categories.py first"
        )
    diagnostics = DumbMoneyDiagnostics()
    equity_series = equity_fund_series(
        category_rows, accession_to_series, diagnostics=diagnostics
    )
    logger.info(
        "equity funds: %d of %d classified series (threshold %.0f%%)",
        len(equity_series),
        diagnostics.n_equity_series + diagnostics.n_non_equity_series,
        100 * EQUITY_ASSET_SHARE_MIN,
    )

    monthly = fund_monthly_returns(filings, returns_by_accession)
    states = build_fund_quarter_states(
        filings, monthly, keep_series=equity_series, diagnostics=diagnostics
    )
    logger.info("fund-quarter states: %d series", len(states))

    # Keyed by ACCESSION, deliberately: which filing supplies a fund-quarter's
    # holdings is decided per snapshot (an amendment filed later must not
    # displace the original that was public at the time), so the panel builder
    # looks these up by the accession it actually selected.
    holdings_by_ticker: dict[str, dict[str, float]] = {}
    for accession, book in holdings_by_accession.items():
        positions: dict[str, float] = defaultdict(float)
        for cusip, value in book.items():
            ticker = cusip_to_ticker.get(cusip)
            if ticker is not None:
                positions[ticker] += value
        if positions:
            holdings_by_ticker[accession] = dict(positions)

    # ---- prices, market cap, spreads (union, once) --------------------------
    frames, missing_price = provider.get_daily_ohlcv(union, history_start, RUN_END)
    frames = {k: v.loc[v.index <= pd.Timestamp(RUN_END)] for k, v in frames.items()}
    close = frames["close"]
    if close.empty:
        raise SystemExit("no price data resolved")
    if missing_price:
        warnings.append(
            f"{len(missing_price)} of {len(union)} tickers resolved no price data (the standing "
            "departed-member yfinance gap)"
        )

    cap_close, splits_by_ticker, _ = provider.get_market_cap_basis(
        list(close.columns), history_start, RUN_END
    )
    from app.services.research_lab.cross_sectional_ivol import build_point_in_time_market_cap

    shares, cap_missing = provider.get_shares_outstanding(
        list(close.columns), history_start, RUN_END
    )
    market_cap, mc_dropped = build_point_in_time_market_cap(cap_close, shares, splits_by_ticker)
    market_cap = market_cap.reindex(index=close.index, columns=close.columns).ffill()
    if cap_missing or mc_dropped:
        warnings.append(
            f"market cap: {len(cap_missing)} tickers had no shares-outstanding series and "
            f"{len(mc_dropped)} were dropped by the builder; those names cannot enter FLOW "
            "(Eq. 8 divides by market cap) or the value weights"
        )

    half_spread, calibration = build_calibrated_half_spread_frame(
        frames["open"], frames["high"], frames["low"], close,
        calibration_start=pd.Timestamp(date(2021, 1, 1)),
    )
    logger.info("half-spread: %s", calibration.summary())

    snapshots = month_end_snapshots(close.index)

    # ---- FLOW panels -------------------------------------------------------
    # Computed ONCE over the union, because FLOW is a property of the stock and
    # the whole fund sector, not of an index. Universe membership is applied
    # later, at portfolio formation.
    panels_by_variant: dict[str, dict[str, pd.DataFrame]] = {}
    for variant in (CounterfactualVariant.ROLLING, CounterfactualVariant.CONTINUOUS):
        variant_diag = DumbMoneyDiagnostics()
        panels_by_variant[variant.value] = build_flow_panels(
            states, holdings_by_ticker, market_cap, snapshots,
            variant=variant, diagnostics=variant_diag,
        )
        logger.info("[%s] panels: %s", variant.value, {
            k: (int(v.notna().to_numpy().sum()) if not v.empty else 0)
            for k, v in panels_by_variant[variant.value].items()
        })
        if variant is CounterfactualVariant.ROLLING:
            diagnostics = variant_diag

    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    # Two side artifacts the INDEPENDENT verification script needs so it can
    # re-derive real FLOW cells from the raw N-PORT CSVs without re-resolving
    # CUSIPs or rebuilding market caps -- both of which would otherwise force it
    # to reuse this family's own code and stop being independent.
    (PANEL_DIR / "cusip_to_ticker.json").write_text(json.dumps(cusip_to_ticker, indent=0))
    quarter_caps: dict[str, dict[str, float]] = {}
    for quarter in sorted({latest_public_quarter(d.date()) for d in snapshots}):
        end = pd.Timestamp(quarter.end_time.date())
        position = market_cap.index.searchsorted(end, side="right") - 1
        if position < 0:
            continue
        row = market_cap.iloc[position]
        quarter_caps[str(quarter)] = {
            t: float(v) for t, v in row.items() if np.isfinite(v) and v > 0.0
        }
    pd.DataFrame.from_dict(quarter_caps, orient="index").to_csv(
        PANEL_DIR / "market_cap_at_quarter.csv.gz", compression="gzip"
    )

    for variant_name, panels in panels_by_variant.items():
        for horizon, frame in panels.items():
            if not frame.empty:
                frame.to_csv(
                    PANEL_DIR / f"flow_{variant_name}_{horizon}.csv.gz", compression="gzip"
                )

    # ---- check C5: construction validity, before any return -----------------
    c5: dict[str, object] = {}
    primary = panels_by_variant[CounterfactualVariant.ROLLING.value]
    for horizon, frame in primary.items():
        if frame.empty:
            c5[horizon] = None
            continue
        values = frame.to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        c5[horizon] = {
            "n_cells": int(finite.size),
            "mean": float(finite.mean()) if finite.size else None,
            "sd": float(finite.std(ddof=1)) if finite.size > 1 else None,
        }

    # ---- portfolios --------------------------------------------------------
    baseline: dict[str, pd.Series] = {}
    zero_cost: dict[str, pd.Series] = {}
    robustness: dict[str, pd.Series] = {}
    leg_diagnostics: dict[str, dict] = {}

    for universe in ("sp500", "sp600"):
        mod = _universe_api(universe)
        for horizon in HORIZON_QUARTERS:
            for variant_name, panels in panels_by_variant.items():
                frame = panels.get(horizon)
                if frame is None or frame.empty:
                    warnings.append(f"[{universe}/{horizon}/{variant_name}] empty FLOW panel")
                    continue
                arms = (
                    (("baseline", half_spread, GENERAL_COLLATERAL_BPS_PER_YEAR),
                     ("zero_cost", None, 0.0))
                    if variant_name == CounterfactualVariant.ROLLING.value
                    else (("baseline", half_spread, GENERAL_COLLATERAL_BPS_PER_YEAR),)
                )
                for cost_arm, spread, borrow in arms:
                    legs, ldiag = quintile_portfolio_returns(
                        frame, close,
                        members_on=_members_on(mod, coverage_ends[universe]),
                        market_cap=market_cap,
                        half_spread=spread,
                        borrow_bps_per_year=borrow,
                    )
                    for leg, series in legs.items():
                        sid = spec_id_for(universe, horizon, leg.value, cost_arm)
                        if variant_name == CounterfactualVariant.ROLLING.value:
                            (baseline if cost_arm == "baseline" else zero_cost)[sid] = series
                            if cost_arm == "baseline":
                                leg_diagnostics[sid] = ldiag.summary()
                        else:
                            robustness[sid] = series
                    logger.info(
                        "[%s/%s/%s/%s] %s", universe, horizon, variant_name, cost_arm,
                        ldiag.summary(),
                    )

    if not baseline:
        raise SystemExit("no specs produced returns — refusing to write a verdict")

    pd.DataFrame(baseline).sort_index().to_csv(
        PANEL_DIR / "spec_monthly_returns_baseline.csv.gz", compression="gzip"
    )
    pd.DataFrame(zero_cost).sort_index().to_csv(
        PANEL_DIR / "spec_monthly_returns_zero_cost.csv.gz", compression="gzip"
    )
    pd.DataFrame(robustness).sort_index().to_csv(
        PANEL_DIR / "spec_monthly_returns_tablea1.csv.gz", compression="gzip"
    )

    # ---- evaluate ----------------------------------------------------------
    dsr_base, sharpe_base, pres_base, denominators = evaluate_specs(baseline)
    dsr_zero, sharpe_zero, pres_zero, _ = evaluate_specs(zero_cost)
    dsr_rob, sharpe_rob, pres_rob, _ = evaluate_specs(robustness) if robustness else ({}, {}, {}, [])

    def rank(dsr_map):
        return sorted(
            dsr_map.items(),
            key=lambda kv: (
                kv[1].get(denominators[0]) if kv[1].get(denominators[0]) is not None else -1.0
            ),
            reverse=True,
        )

    best_spec, best_map = rank(dsr_base)[0]
    verdict, rationale = verdict_for(best_map, denominators, bar=BAR)
    best_zero_spec, best_zero_map = rank(dsr_zero)[0]
    verdict_zero, _ = verdict_for(best_zero_map, denominators, bar=BAR)

    # ---- check C1: FF3 on every long-short spec ----------------------------
    ff = load_fama_french_monthly()
    factors = ff.frame
    c1: dict[str, object] = {}
    for sid, series in baseline.items():
        if Leg.LONG_SHORT.value in sid:
            c1[sid] = ff3_regression(series, factors)

    # ---- persist -----------------------------------------------------------
    from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe

    sigma = float(np.std(list(sharpe_base.values()), ddof=1))
    by_universe: dict[str, list[SpecResult]] = {"sp500": [], "sp600": []}
    pattern = re.compile(
        r"(?P<universe>[^/]+)/dm_(?P<horizon>3month|6month|1year|3year)_"
        r"(?P<leg>long_low_flow|short_high_flow|long_short)_(?P<arm>baseline|zero_cost)"
    )
    for sid, series in baseline.items():
        match = pattern.fullmatch(sid)
        if match is None:
            raise ValueError(f"unparseable spec_id {sid!r}")
        clean = series.dropna()
        by_universe[match["universe"]].append(
            SpecResult(
                spec_id=sid,
                universe=match["universe"],
                horizon=match["horizon"],
                leg=match["leg"],
                cost_arm="baseline",
                sharpe_annualized=sharpe_base[sid],
                n_trading_days=int(len(clean)),
                mean_monthly_return=float(clean.mean()) if len(clean) else 0.0,
                dsr_by_n={int(k): v for k, v in dsr_base[sid].items()},
                preservation_score=pres_base[sid],
                formable_fraction=float(
                    leg_diagnostics.get(sid, {}).get("formable_fraction", 0.0)
                ),
                deflated_sharpe=compute_deflated_sharpe(
                    sharpe_base[sid], clean, denominators[0], sigma, periods_per_year=12.0
                ),
            )
        )

    db = SessionLocal()
    try:
        # Make a re-run IDEMPOTENT. persist_cross_sectional_trial_results is
        # deliberately append-only (and is a shared module this family must
        # leave byte-identical), so re-running after a bug fix would otherwise
        # stack a second set of rows under the same run_tag -- which is exactly
        # what verify_persisted_trial_results then refuses, correctly. Only
        # THIS family's own run_tag is touched; nothing else in the table is.
        stale = db.execute(
            text(
                "DELETE FROM cross_sectional_trial_results WHERE run_tag = :tag "
                "AND family_key IN (:a, :b)"
            ),
            {
                "tag": RUN_TAG,
                "a": DUMB_MONEY_FAMILY_KEY,
                "b": DUMB_MONEY_SMALL_CAP_FAMILY_KEY,
            },
        ).rowcount
        db.commit()
        if stale:
            logger.info("cleared %d stale rows from a previous run of this run_tag", stale)
        written = 0
        for universe, rows in by_universe.items():
            if rows:
                written += persist_cross_sectional_trial_results(
                    db, FAMILY_KEY_BY_UNIVERSE[universe], rows, run_tag=RUN_TAG
                )
        verify_persisted_trial_results(db, RUN_TAG, written)
        logger.info("persisted %d rows", written)
    finally:
        db.close()

    # ---- reports -----------------------------------------------------------
    payload = {
        "family": "frazzini_lamont_dumb_money",
        "citation": DUMB_MONEY_CITATION,
        "run_tag": RUN_TAG,
        "run_end": RUN_END.isoformat(),
        "n_local": DUMB_MONEY_N_TRIALS,
        "denominators": denominators,
        "bar": BAR,
        "verdict": verdict,
        "verdict_rationale": rationale,
        "best_spec": best_spec,
        "best_dsr_by_n": {str(k): v for k, v in best_map.items()},
        "zero_cost_verdict": verdict_zero,
        "zero_cost_best_spec": best_zero_spec,
        "zero_cost_best_dsr_by_n": {str(k): v for k, v in best_zero_map.items()},
        "equity_fund_threshold": EQUITY_ASSET_SHARE_MIN,
        "n_equity_series": len(equity_series),
        "n_filings": len(filings),
        "nport_quarters": quarters,
        "fama_french_vintage": ff.vintage_line,
        "half_spread_calibration": calibration.summary(),
        "panel_diagnostics": diagnostics.summary(),
        "nport_load_diagnostics": {
            "n_submission_rows": load_diag.n_submission_rows,
            "n_holding_rows": load_diag.n_holding_rows,
            "n_filings_built": load_diag.n_filings_built,
            "refused": dict(sorted(load_diag.n_refused.items())),
        },
        "check_c1_ff3": c1,
        "check_c2_leg_diagnostics": leg_diagnostics,
        "check_c5_flow_scale": c5,
        "specs": {
            sid: {
                "sharpe": sharpe_base[sid],
                "n_months": int(len(baseline[sid].dropna())),
                "mean_monthly_return": float(baseline[sid].dropna().mean()),
                "dsr_by_n": {str(k): v for k, v in dsr_base[sid].items()},
                "preservation_score": pres_base[sid],
                "zero_cost_sharpe": sharpe_zero.get(sid.replace("_baseline", "_zero_cost")),
                "zero_cost_dsr_by_n": {
                    str(k): v
                    for k, v in dsr_zero.get(sid.replace("_baseline", "_zero_cost"), {}).items()
                },
            }
            for sid in sorted(baseline)
        },
        "robustness_tablea1": {
            sid: {
                "sharpe": sharpe_rob[sid],
                "dsr_by_n": {str(k): v for k, v in dsr_rob[sid].items()},
            }
            for sid in sorted(robustness)
        },
        "warnings": warnings,
        "elapsed_seconds": time.time() - started,
    }
    REPORT_STEM.with_suffix(".json").write_text(json.dumps(payload, indent=2, default=str))
    logger.info("verdict %s — %s", verdict, rationale)
    logger.info("wrote %s", REPORT_STEM.with_suffix(".json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
