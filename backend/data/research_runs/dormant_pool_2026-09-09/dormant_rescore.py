#!/usr/bin/env python
"""Dormant pool RE-SCORER — runs a parked family on data extended to `end`,
captures the frozen spec's realized net daily returns, scores the
out-of-sample extension with dormant_pool.evaluate_look, and PERSISTS the
look as a committed JSON record.

HOW IT REACHES 28 FAMILIES WITHOUT 28 ADAPTERS. run_global_effective_n.py
already solved "get every family's per-spec net daily return series": it
patches the shared replay harness (and the seven bespoke engines) so each
replay's `.daily_returns` is recorded under its pattern_id. This script
reuses those hooks unchanged and re-declares the same invocation table with
ONE difference: the window end is a parameter instead of a pinned date, so a
run today naturally includes everything after the family's original window.
Each invocation is copied from that table (itself copied from committed call
sites) — nothing is re-invented.

WHAT A LOOK IS (dormant_pool.py, pre-registered): PSR of the frozen spec's
net returns strictly AFTER window_end_at_entry, N=1, promotion only at a
scheduled look and only above the bucket's calibrated boundary. Never a pass
to capital.

THE PRE-ENTRY DRIFT CHECK. A re-run recomputes the ORIGINAL window too. Its
Sharpe on [.., window_end_at_entry] is compared with the Sharpe the family
persisted when the verdict was made (cross_sectional_trial_results). A large
drift means the data path is not point-in-time (revisions, survivorship,
the known lazy_prices ticker->CIK issue) — the record carries it, and a
drift above DRIFT_FLAG_ABS is stated loudly. Promotion is still governed by
the entry's pit_ok flag, which a human sets; this check is the evidence for
setting it.

Usage (from backend/):
  python data/research_runs/dormant_pool_2026-09-09/dormant_rescore.py            # every manifest entry
  ... --family quality_cbop                                                        # one family
  ... --demo quality_cbop:cbop_ls_h63:2026-06-30                                   # a synthetic entry, manifest untouched
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "data" / "research_runs"))

import run_global_effective_n as gen

from app.services.research_lab import metrics
from app.services.research_lab.dormant_pool import (
    K_MAX,
    DormantEntry,
    assign_bucket,
    evaluate_look,
    lag1_autocorrelation,
    load_manifest,
)

LOOKS_DIR = HERE / "looks"
LOG_PATH = HERE / "looks_log.jsonl"

# |Sharpe_rerun_pre_entry - Sharpe_persisted| above this is flagged as a
# point-in-time concern. 0.10 annualized is well above what a few revised
# prints move a 2 900-day Sharpe by, and well below a genuinely different
# universe or cost path.
DRIFT_FLAG_ABS = 0.10

_HOOKS_INSTALLED = False


# ---------------------------------------------------------------------------
# invocation table, `end` parameterised
# ---------------------------------------------------------------------------


def rescore_registry(end: date) -> dict[str, Callable[[], list]]:
    """family_key -> zero-arg callable returning that family's per-spec
    result objects, on data through `end`. Mirrors
    run_global_effective_n.build_registry() invocation for invocation; the
    only change is `end`. Keys are the cross_sectional_trial_results
    namespace (the Dormant manifest's namespace), not the forward
    registration one."""
    from app.services.research_lab.cross_sectional_asset_growth import (
        run_asset_growth_screening,
    )
    from app.services.research_lab.cross_sectional_best_ideas import (
        run_best_ideas_screening,
    )
    from app.services.research_lab.cross_sectional_bonds import run_bonds_screening
    from app.services.research_lab.cross_sectional_buyback import run_buyback_screening
    from app.services.research_lab.cross_sectional_commodities import (
        run_commodities_screening,
    )
    from app.services.research_lab.cross_sectional_correlation_risk_premium import (
        run_crp_screening,
    )
    from app.services.research_lab.cross_sectional_country_valmom import (
        run_country_valmom_screening,
    )
    from app.services.research_lab.cross_sectional_crypto import run_crypto_screening
    from app.services.research_lab.cross_sectional_dividend_month import (
        run_dmp_screening,
    )
    from app.services.research_lab.cross_sectional_earnings_premium import (
        run_eap_screening,
    )
    from app.services.research_lab.cross_sectional_eigenportfolio import (
        run_eigenportfolio_screening,
    )
    from app.services.research_lab.cross_sectional_fx import screen_fx_family
    from app.services.research_lab.cross_sectional_illiq import run_illiq_screening
    from app.services.research_lab.cross_sectional_index_removal import (
        run_index_removal_screening,
    )
    from app.services.research_lab.cross_sectional_insider import run_insider_screening
    from app.services.research_lab.cross_sectional_ivol import run_round_d1_screening
    from app.services.research_lab.cross_sectional_jump_drift import (
        run_jump_drift_screening,
    )
    from app.services.research_lab.cross_sectional_lazy_prices import (
        run_lazy_prices_screening,
    )
    from app.services.research_lab.cross_sectional_patterns import run_round_c_screening
    from app.services.research_lab.cross_sectional_patterns_d2 import (
        screen_d2_reversal_family,
    )
    from app.services.research_lab.cross_sectional_pead import run_pead_screening
    from app.services.research_lab.cross_sectional_quality import run_quality_screening
    from app.services.research_lab.cross_sectional_quality_neutral import (
        run_noa_neutral_screening,
    )
    from app.services.research_lab.cross_sectional_residual_momentum import (
        run_residual_momentum_screening,
    )
    from app.services.research_lab.cross_sectional_seasonality import (
        run_seasonality_screening,
    )
    from app.services.research_lab.cross_sectional_short_interest import (
        SHORT_INTEREST_FORMATION_START,
        run_short_interest_screening,
    )
    from app.services.research_lab.cross_sectional_small_mid_cap import (
        run_small_cap_disposition_screening,
        run_small_cap_ivol_screening,
    )
    from app.services.research_lab.small_cap_membership_history import (
        MEMBERSHIP_DATA_START as SMALL_CAP_START,
    )
    from app.services.research_lab.sp500_membership_history import (
        MEMBERSHIP_DATA_START,
        get_universe_over,
    )
    from app.services.research_lab.vol_regime_timing import run_vol_regime_screening

    def quality_all() -> list:
        s = run_quality_screening(end=end, edgar=gen._edgar())
        return list(s.cbop_results) + list(s.noa_results)

    return {
        "quality_cbop": quality_all,
        "quality_noa": quality_all,
        "quality_noa_industry_neutral": lambda: run_noa_neutral_screening(end=end, edgar=gen._edgar()).results,
        "short_interest": lambda: run_short_interest_screening(
            start=SHORT_INTEREST_FORMATION_START, end=end, edgar=gen._edgar()).results,
        "lazy_prices": lambda: run_lazy_prices_screening(
            MEMBERSHIP_DATA_START, end, tickers=get_universe_over(MEMBERSHIP_DATA_START, end)).results,
        "residual_momentum": lambda: run_residual_momentum_screening(end=end, edgar=gen._edgar()).results,
        "asset_growth": lambda: run_asset_growth_screening(end=end, edgar=gen._edgar()).results,
        "liquidity_shock_delta_illiq": lambda: run_illiq_screening(MEMBERSHIP_DATA_START, end)[0],
        "same_calendar_month_seasonality": lambda: run_seasonality_screening(MEMBERSHIP_DATA_START, end)[0],
        "round_c": lambda: run_round_c_screening(MEMBERSHIP_DATA_START, end)[0],
        "jump_drift": lambda: run_jump_drift_screening(MEMBERSHIP_DATA_START, end, run_event_study=False).results,
        "best_ideas_13f": lambda: run_best_ideas_screening(end=end).results,
        "correlation_risk_premium": lambda: run_crp_screening(end=end, include_pit_crosscheck=False).results,
        "country_valmom": lambda: run_country_valmom_screening(end=end).results,
        "eigenportfolio_statarb": lambda: run_eigenportfolio_screening(
            end=end, include_reversal_diagnostic=False, include_edge_cost_diagnostic=False).results,
        "dividend_month_premium": lambda: run_dmp_screening(MEMBERSHIP_DATA_START, end).results,
        "earnings_announcement_premium": lambda: run_eap_screening(MEMBERSHIP_DATA_START, end).results,
        "insider_opportunistic": lambda: run_insider_screening(MEMBERSHIP_DATA_START, end).results,
        "pead_ear": lambda: run_pead_screening(MEMBERSHIP_DATA_START, end).results,
        "fx": lambda: screen_fx_family(end=end).results,
        "crypto": lambda: run_crypto_screening(end=end).results,
        "small_cap_disposition": lambda: run_small_cap_disposition_screening(SMALL_CAP_START, end)[0],
        "small_cap_ivol": lambda: run_small_cap_ivol_screening(SMALL_CAP_START, end)[0],
        "commodities": lambda: run_commodities_screening(end=end).results,
        "ivol": lambda: run_round_d1_screening(MEMBERSHIP_DATA_START, end)[0],
        "bonds": lambda: run_bonds_screening(end=end).results,
        "buyback": lambda: run_buyback_screening(end=end).results,
        "index_removal": lambda: run_index_removal_screening(MEMBERSHIP_DATA_START, end).results,
        "patterns_d2": lambda: screen_d2_reversal_family(MEMBERSHIP_DATA_START, end).results,
        "vol_regime": lambda: run_vol_regime_screening(end=end).results,
    }


NOT_RESCORABLE = dict(gen.EXCLUDED_FAMILIES)


def run_family_and_capture(family_key: str, end: date) -> dict[str, pd.Series]:
    """Every captured per-spec net daily series for one family, keyed by
    pattern_id. Hooks are installed AFTER the registry's imports so every
    module's own binding of the harness is patched (see
    run_global_effective_n.install_capture_hooks)."""
    global _HOOKS_INSTALLED
    registry = rescore_registry(end)
    if family_key not in registry:
        raise KeyError(f"{family_key!r} has no rescore invocation; not rescorable: "
                       f"{NOT_RESCORABLE.get(family_key, 'not in the table')}")
    if not _HOOKS_INSTALLED:
        gen.install_capture_hooks()
        _HOOKS_INSTALLED = True
    gen.CAPTURED.clear()
    gen._REPLAY_OWNER.clear()
    results = registry[family_key]()
    for r in results or []:  # capture route (1): result objects that carry the series
        sid = gen._spec_id_of(r)
        series = getattr(r, "daily_returns", None)
        if sid and sid not in gen.CAPTURED and isinstance(series, pd.Series):
            gen._record(sid, series)
    return dict(gen.CAPTURED)


# ---------------------------------------------------------------------------
# scoring (pure; unit-tested)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LookRecord:
    schema: str
    family_key: str
    pattern_id: str
    demo: bool
    run_at: str
    data_end: str
    window_end_at_entry: str
    bucket: str
    boundary: float
    periods_per_year: float
    n_pre_entry: int
    sharpe_pre_entry_rerun: float | None
    sharpe_persisted_original: float | None
    pre_entry_drift: float | None
    pre_entry_drift_flagged: bool
    phi_hat_pre_entry_rerun: float | None
    n_extension: int
    look_index: int
    k_max: int
    psr_ext: float | None
    sharpe_ext_annualized: float | None
    promoted: bool
    note: str


def score_series(
    series: pd.Series,
    entry: DormantEntry,
    *,
    persisted_sharpe: float | None,
    data_end: date,
    demo: bool = False,
    now: datetime | None = None,
) -> LookRecord:
    """Split the re-run series at window_end_at_entry, run the drift check on
    the pre-entry part, and evaluate the look on the extension."""
    s = pd.Series(series, dtype=float).dropna().sort_index()
    idx = pd.DatetimeIndex(s.index)
    cut = pd.Timestamp(entry.window_end_at_entry)
    pre = s[idx <= cut]
    ext = s[idx > cut]

    sharpe_pre = metrics.sharpe_ratio(pre, periods_per_year=entry.periods_per_year) if len(pre) >= 20 else None
    drift = None if (sharpe_pre is None or persisted_sharpe is None) else float(sharpe_pre - persisted_sharpe)
    phi_pre = None
    if len(pre) >= 3 and float(pre.std(ddof=1)) > 0:
        phi_pre = lag1_autocorrelation(pre)

    look = evaluate_look(ext, entry)
    note = look.note
    flagged = drift is not None and abs(drift) > DRIFT_FLAG_ABS
    if flagged:
        note += (f" | PRE-ENTRY DRIFT {drift:+.3f} (rerun {sharpe_pre:.3f} vs persisted {persisted_sharpe:.3f}) "
                 f"exceeds {DRIFT_FLAG_ABS}: data path may not be point-in-time — review pit_ok")
    return LookRecord(
        schema="dormant_pool_look/v1",
        family_key=entry.family_key,
        pattern_id=entry.pattern_id,
        demo=demo,
        run_at=(now or datetime.now(UTC)).isoformat(timespec="seconds"),
        data_end=data_end.isoformat(),
        window_end_at_entry=entry.window_end_at_entry.isoformat(),
        bucket=entry.bucket,
        boundary=entry.boundary,
        periods_per_year=entry.periods_per_year,
        n_pre_entry=len(pre),
        sharpe_pre_entry_rerun=sharpe_pre,
        sharpe_persisted_original=persisted_sharpe,
        pre_entry_drift=drift,
        pre_entry_drift_flagged=flagged,
        phi_hat_pre_entry_rerun=phi_pre,
        n_extension=look.n_extension,
        look_index=look.look_index,
        k_max=K_MAX,
        psr_ext=look.psr_ext,
        sharpe_ext_annualized=look.sharpe_ext_annualized,
        promoted=look.promoted,
        note=note,
    )


def persist(record: LookRecord, looks_dir: Path = LOOKS_DIR, log_path: Path = LOG_PATH) -> Path:
    looks_dir.mkdir(parents=True, exist_ok=True)
    stamp = record.run_at[:10]
    path = looks_dir / f"{record.family_key}__{record.pattern_id}__{stamp}{'__demo' if record.demo else ''}.json"
    payload = asdict(record)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    with log_path.open("a") as fh:
        fh.write(json.dumps(payload) + "\n")
    return path


def persisted_sharpe_for(family_key: str, pattern_id: str) -> float | None:
    from app.db import SessionLocal
    from app.models.cross_sectional_trial_result import CrossSectionalTrialResult as T

    db = SessionLocal()
    try:
        rows = db.query(T).filter(T.family_key == family_key, T.trial_id == pattern_id).all()
        if not rows:
            return None
        latest = max(rows, key=lambda r: r.run_tag)
        return float(latest.sharpe_annualized)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _demo_entry(spec: str, series_for_phi: pd.Series | None, ppy: float) -> DormantEntry:
    family_key, pattern_id, window_end = spec.split(":")[:3]
    cut = date.fromisoformat(window_end)
    phi = 0.0
    if series_for_phi is not None:
        pre = series_for_phi[pd.DatetimeIndex(series_for_phi.index) <= pd.Timestamp(cut)]
        if len(pre) >= 3 and float(pre.std(ddof=1)) > 0:
            phi = lag1_autocorrelation(pre)
    return DormantEntry(
        family_key=family_key, pattern_id=pattern_id,
        spec_fingerprint="demo", config_fingerprint="demo",
        window_end_at_entry=cut, entered_at=date.today(),  # noqa: DTZ011
        periods_per_year=ppy, phi_hat_entry=phi, bucket=assign_bucket(phi),
        pit_ok=True, rescorable=True,
        mechanism_review="DEMO entry: not a pool decision; exercises the runner end to end",
        entry_rationale="DEMO entry created by dormant_rescore.py --demo; manifest untouched",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default=None, help="data end (YYYY-MM-DD); default today")
    ap.add_argument("--family", default=None, help="only this family_key")
    ap.add_argument("--demo", default=None, help="family:pattern_id:window_end — synthetic entry, manifest untouched")
    args = ap.parse_args()
    end = date.fromisoformat(args.end) if args.end else date.today()  # noqa: DTZ011

    if args.demo:
        family_key = args.demo.split(":")[0]
        t0 = time.time()
        captured = run_family_and_capture(family_key, end)
        pattern_id = args.demo.split(":")[1]
        if pattern_id not in captured:
            print(f"pattern {pattern_id!r} not captured for {family_key}; captured: {sorted(captured)[:20]}")
            return 1
        series = captured[pattern_id]
        ppy = float(metrics.CALENDAR_DAYS_PER_YEAR) if family_key == "crypto" else float(metrics.TRADING_DAYS_PER_YEAR)
        entry = _demo_entry(args.demo, series, ppy)
        rec = score_series(series, entry, persisted_sharpe=persisted_sharpe_for(family_key, pattern_id), data_end=end, demo=True)
        path = persist(rec)
        print(f"{family_key}/{pattern_id}: {len(captured)} specs captured in {time.time()-t0:.0f}s; wrote {path.name}")
        print(json.dumps(asdict(rec), indent=2))
        return 0

    entries = load_manifest()
    if args.family:
        entries = [e for e in entries if e.family_key == args.family]
    if not entries:
        print("no Dormant entries to score (manifest empty or filter matched nothing)")
        return 0
    by_family: dict[str, list[DormantEntry]] = {}
    for e in entries:
        by_family.setdefault(e.family_key, []).append(e)
    n_written = 0
    for family_key, fam_entries in sorted(by_family.items()):
        rescorable = [e for e in fam_entries if e.rescorable]
        skipped = [e for e in fam_entries if not e.rescorable]
        for e in skipped:
            print(f"SKIP {family_key}/{e.pattern_id}: rescorable=false (recorded, not scored)")
        if not rescorable:
            continue
        t0 = time.time()
        try:
            captured = run_family_and_capture(family_key, end)
        except Exception as exc:  # noqa: BLE001 — one family's failure must not stop the others
            print(f"FAILED {family_key}: {type(exc).__name__}: {exc}")
            continue
        for e in rescorable:
            if e.pattern_id not in captured:
                print(f"MISSING {family_key}/{e.pattern_id}: not captured (specs seen: {len(captured)})")
                continue
            rec = score_series(captured[e.pattern_id], e, persisted_sharpe=persisted_sharpe_for(family_key, e.pattern_id), data_end=end)
            path = persist(rec)
            n_written += 1
            print(f"{family_key}/{e.pattern_id}: look {rec.look_index}/{K_MAX} PSR_ext={rec.psr_ext} promoted={rec.promoted} -> {path.name}")
        print(f"  ({family_key}: {time.time()-t0:.0f}s)")
    print(f"wrote {n_written} look record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
