"""Re-run of the multi-signal combination thesis after round_c's
re-admission — executes the pipeline of multi_signal_combination.py
exactly as its docstring sections 1-5 froze it, on the selection framework
as amended by section 8 (round_c's hard-exclusion removed on commit
dd34094's independently verified corrected-cost re-audit; both
CANONICAL_RUN_TAGS entries moved off the discredited edge_spread tag).

Nothing methodological lives here: selection, regeneration, alignment,
the four weighting schemes, the null control, Kelly and the verdict all
come from the module. This script only wires the frozen pieces together,
asserts the run is reproducing the persisted record it claims to, and
persists the results — the job the (uncommitted, since lost) 2026-08-29
runner did for section 6, done durably this time.

Run from inside this worktree's backend/ so `app` and ./aladdin2.db
resolve to THIS worktree. The three cache paths point at the main repo's
data caches (gitignored data, the same caches every prior regeneration
used); with the module's pinned end dates every provider call should be a
cache read or an idempotent refetch, never a main-repo mutation.
"""

import json
import time
from dataclasses import asdict
from pathlib import Path
from unittest import mock

from app.db import SessionLocal
from app.services.research_lab import multi_signal_combination as msc
from app.services.research_lab.metrics import (
    CALENDAR_DAYS_PER_YEAR,
    TRADING_DAYS_PER_YEAR,
    sharpe_ratio,
)

MAIN_DATA = Path("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data")
SCRATCH = Path(
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
    "be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
)

RUN_TAG_PRIMARY = "multi_signal_recombination_2026-08-30"
RUN_TAG_SENSITIVITY = "multi_signal_recomb_sensitivity_add_noa_neutral_2026-08-30"

# The selection section 8 derived from the corrected table before this
# script ran. If the mechanical rule returns anything else, the premise of
# the run is wrong and it must stop, not improvise.
EXPECTED_SELECTED = {
    "correlation_risk_premium": "crp_realized_21d_h63",
    "insider_opportunistic": "insider_opp_buy_h21_c2_equal",
    "ofi_crypto": "ofi_raw_h7",
    "quality_cbop": "cbop_ls_h63",
    "round_c": "lps_intraday_l252_h63",
}
NOA_SPEC_ID = "noa_neutral_ls_h126_median"
NOA_EXPECTED_OBSERVATIONS = 2926  # the noa_neutral_build_2026-08-28 row


def log(msg: str) -> None:
    print(f"[{time.strftime('%X')}] {msg}", flush=True)


def regenerate_noa_neutral_series(edgar_cache_dir: Path):
    """The add-back sensitivity's sleeve, regenerated from its own family's
    code (cross_sectional_quality_neutral.py's exact pipeline, one spec of
    it) — the same standard every primary candidate is held to."""
    from datetime import timedelta

    from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider
    from app.services.market_data.yfinance_provider import YFinanceProvider
    from app.services.research_lab.cross_sectional import (
        CrossSectionalData,
        run_cross_sectional_backtest,
    )
    from app.services.research_lab.cross_sectional_quality import (
        QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS,
        build_point_in_time_factor_frame,
        build_quality_sample,
        compute_noa_observations,
        default_quality_config,
    )
    from app.services.research_lab.cross_sectional_quality_neutral import (
        build_noa_neutral_family,
        build_point_in_time_bucket_frame,
    )
    from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

    start = MEMBERSHIP_DATA_START
    end = msc.QUALITY_REPRO_END  # same price panel as the persisted build
    config = default_quality_config()
    config.formation_start = start

    sample, _ = build_quality_sample(start, end)
    edgar = EdgarXbrlProvider(cache_dir=edgar_cache_dir)
    extractions, missing_cik, _ = edgar.fetch_line_items_for_tickers(sample)
    sic_histories, _, _ = edgar.fetch_sic_history_for_tickers(
        [t for t in sample if t not in missing_cik]
    )
    padded = start - timedelta(days=QUALITY_PRICE_HISTORY_PADDING_CALENDAR_DAYS)
    close, _ = YFinanceProvider().get_price_history(sample, padded, end)

    noa_obs = {t: compute_noa_observations(e)[0] for t, e in extractions.items()}
    noa_frame, _, _ = build_point_in_time_factor_frame(close, noa_obs)
    bucket_frame, _, _ = build_point_in_time_bucket_frame(close, sic_histories)
    spec = next(
        s for s in build_noa_neutral_family(bucket_frame) if s.pattern_id == NOA_SPEC_ID
    )
    series = run_cross_sectional_backtest(
        CrossSectionalData(close=close, fundamental_signal=noa_frame), spec, config, None
    ).daily_returns
    if len(series) != NOA_EXPECTED_OBSERVATIONS:
        raise ValueError(
            f"{NOA_SPEC_ID}: regenerated {len(series)} observations but the persisted "
            f"row says {NOA_EXPECTED_OBSERVATIONS} — the sensitivity must not run on a "
            "series that does not reproduce the record."
        )
    import pandas as pd

    idx = pd.DatetimeIndex(series.index)
    if idx.tz is not None:
        series = pd.Series(series.to_numpy(dtype=float), index=idx.tz_localize(None))
    return series


def family_counts_for(series_labels, selection, scanned):
    """k_f per sleeve for the null control: the number of persisted specs the
    sleeve's family had under its canonical tag, keyed by sleeve label in
    returns-matrix column order (the null's own contract)."""
    fam_by_trial = {s.trial_id: s.family_key for s in selection.selected}
    fam_sizes: dict[str, int] = {}
    for s in scanned:
        fam_sizes[s.family_key] = fam_sizes.get(s.family_key, 0) + 1
    return {label: fam_sizes[fam_by_trial[label]] for label in series_labels}


def run_and_persist(db, tag, selection, series, scanned) -> None:
    counts = family_counts_for(list(series), selection, scanned)
    log(f"{tag}: family_spec_counts={counts}")
    summary = msc.run_combination(
        selection,
        series,
        daily_calendar_specs=msc.NON_EQUITY_CALENDAR_SPECS,
        family_spec_counts=counts,
        run_null=True,
    )
    print("\n".join(msc.summary_lines(summary)), flush=True)
    with open(SCRATCH / f"{tag}_summary.json", "w") as f:
        json.dump(
            {
                "run_tag": tag,
                "window": [summary.window_start, summary.window_end],
                "n_trading_days": summary.n_trading_days,
                "results": [asdict(r) for r in summary.results],
                "kelly": summary.kelly,
                "null_control": asdict(summary.null_control),
                "verdict": summary.verdict,
                "notes": list(summary.notes),
                "single_candidate_sharpes": summary.single_candidate_sharpes,
                "correlation_matrix": summary.correlation_matrix,
            },
            f,
            indent=2,
            default=str,
        )
    n = msc.persist_combination(db, summary, run_tag=tag)
    log(f"{tag}: persisted {n} rows")


def main() -> None:
    db = SessionLocal()

    # ---- Step 1 on the corrected table ------------------------------------
    scanned = msc.load_scanned_specs(db)
    selection = msc.select_candidates(scanned)
    stages: dict[str, int] = {}
    for d in selection.decisions:
        stages[d.stage] = stages.get(d.stage, 0) + 1
    log(f"scanned {selection.n_scanned} specs; stages {stages}")
    log(f"sigma_SR scanned {selection.sigma_sr_annualized:.4f}; "
        f"diagnostic ({selection.n_trials_diagnostic} specs) "
        f"{selection.sigma_sr_diagnostic:.4f}")
    got = {s.family_key: s.trial_id for s in selection.selected}
    if got != EXPECTED_SELECTED:
        raise SystemExit(f"selection mismatch: expected {EXPECTED_SELECTED}, got {got}")
    (SCRATCH / "recombination_selection.json").write_text(msc.selection_report(selection))

    # ---- Regenerate the five sleeves from their families' own code --------
    log("regenerating the 5 selected series (SEC/Yahoo/Binance, pinned ends)...")
    t0 = time.time()
    series = msc.regenerate_candidate_series(
        edgar_cache_dir=MAIN_DATA / "edgar_companyfacts",
        insider_trades_cache=MAIN_DATA / "insider_form4_trades.csv.gz",
        binance_cache_dir=MAIN_DATA / "binance_futures",
    )
    log(f"regenerated in {time.time() - t0:.0f}s")
    fam_by_trial = {s.trial_id: s for s in selection.selected}
    for label, s in series.items():
        # Each family's persisted Sharpe is annualized on ITS OWN calendar —
        # the crypto sleeve trades 24/7/365, everything else on the 252-day
        # session calendar — so the reproduction check must use the same
        # basis or it manufactures a phantom drift of sqrt(252/365) on the
        # OFI sleeve (the 2026-08-30 run's log shows exactly that artifact;
        # the series itself reproduced the persisted row to 4e-16).
        periods = (
            CALENDAR_DAYS_PER_YEAR
            if label in msc.NON_EQUITY_CALENDAR_SPECS
            else TRADING_DAYS_PER_YEAR
        )
        regen = sharpe_ratio(s, periods_per_year=periods)
        row = fam_by_trial[label]
        log(
            f"  {label}: n={len(s)} regenerated Sharpe {regen:+.4f} vs persisted "
            f"{row.sharpe_annualized:+.4f} (drift {regen - row.sharpe_annualized:+.5f})"
        )

    # ---- Primary run ------------------------------------------------------
    run_and_persist(db, RUN_TAG_PRIMARY, selection, series, scanned)

    # ---- Pre-declared section 1 sensitivity: add noa_neutral back ---------
    log("sensitivity: regenerating the noa_neutral sleeve...")
    noa_series = regenerate_noa_neutral_series(MAIN_DATA / "edgar_companyfacts")
    noa_sharpe = sharpe_ratio(noa_series, periods_per_year=TRADING_DAYS_PER_YEAR)
    log(f"  {NOA_SPEC_ID}: n={len(noa_series)} regenerated Sharpe {noa_sharpe:+.4f}")
    without_noa = tuple(
        r for r in msc.HARD_EXCLUSIONS if r.family_key != msc.SENSITIVITY_ADD_BACK
    )
    with mock.patch.object(msc, "HARD_EXCLUSIONS", without_noa):
        selection_s = msc.select_candidates(scanned)
    got_s = {s.family_key: s.trial_id for s in selection_s.selected}
    expected_s = dict(EXPECTED_SELECTED, quality_noa_industry_neutral=NOA_SPEC_ID)
    if got_s != expected_s:
        raise SystemExit(f"sensitivity selection mismatch: {got_s}")
    series_s = dict(series)
    series_s[NOA_SPEC_ID] = noa_series
    run_and_persist(db, RUN_TAG_SENSITIVITY, selection_s, series_s, scanned)

    db.close()
    log("DONE")


if __name__ == "__main__":
    main()
