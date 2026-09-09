#!/usr/bin/env python
"""Dormant pool RE-SCORER — runs a parked family on data extended to `end`,
captures the frozen spec's realized net daily returns, scores the
out-of-sample extension with dormant_pool.evaluate_look, and PERSISTS the
look as a committed JSON record.

HOW IT REACHES 36 FAMILY KEYS WITHOUT 36 ADAPTERS. run_global_effective_n.py
already solved "get every family's per-spec net daily return series": it
patches the shared replay harness (and the seven bespoke engines) so each
replay's `.daily_returns` is recorded under its pattern_id. This script
reuses those hooks unchanged and re-declares the same invocation table with
ONE difference: the window end is a parameter instead of a pinned date, so a
run today naturally includes everything after the family's original window.
Each invocation is copied from that table (itself copied from committed call
sites) — nothing is re-invented. The families built after that run
(quarter-end marking, tax-loss, rebalancing, dividend pressure, margin
credit, IPO lockup) are added the same way, with cost-arm gating for the
three engines that replay every spec once per cost arm (see _EXTRA_BESPOKE)
AND for the two SHARED-HARNESS families that replay their whole grid once per
sensitivity arm (quarter-end marking's cost ladder x0/x1/x2, tax-loss's
short-leg borrow ladder 0/34/430bp; see _HUB_ARM_GATES). The second gate was
missing until 2026-09-09 and was the ENTIRE cause of the two "reproducibility
gaps" recorded that morning — see KNOWN_REPRODUCIBILITY_GAPS below.
Every persisted family key is either in the table or in NOT_RESCORABLE with
a reason; a test pins that.

VERIFIED BY RE-RUN, not assumed: with the cut at each family's original
window end, the re-run's pre-entry Sharpe equals the persisted one to 1e-15
for quality_cbop (0.4531 vs 0.4565 at a 2-month-earlier cut), rebalancing
(0.2298 = 0.2298), margin_credit (−0.2487 = −0.2487) and ipo_lockup
(−0.9629 = −0.9629) — committed demo records in looks/. dividend_pressure
needs its gitignored payment calendar rebuilt first
(data/research_runs/fetch_dividend_payment_calendar.py); without it the
family replays nothing and says so.

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

# Families whose series is not on the exchange calendar. A real manifest
# entry carries periods_per_year itself; this is only for --demo.
DEMO_PERIODS_PER_YEAR = {"crypto": 365.0, "margin_credit": 12.0}


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
    from app.services.research_lab.cross_sectional_quarter_end_marking import (
        run_qem_screening,
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
    from app.services.research_lab.cross_sectional_tax_loss_selling import (
        run_tax_loss_screening,
    )
    from app.services.research_lab.dividend_payment_pressure_timing import (
        run_dividend_pressure_screening,
    )
    from app.services.research_lab.ipo_lockup_expiration import (
        PREREGISTERED_IDENTITY,
        run_ipo_lockup_screening,
    )
    from app.services.research_lab.margin_credit_timing import (
        run_margin_credit_screening,
    )
    from app.services.research_lab.rebalancing_pressure_timing import (
        run_rebalancing_screening,
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

        # ---- families built after the 2026-09-05 effective-N run ---------
        # Invocations copied from their committed run scripts (named), with
        # the pinned RUN_END replaced by `end`. Engines: quarter-end marking
        # and tax-loss route through the shared harness (hook route 2);
        # rebalancing, dividend-pressure and IPO-lockup have bespoke replays
        # wrapped in install_extra_hooks(); margin credit is MONTHLY and its
        # replay exposes `strategy_returns`, captured by a dedicated hook —
        # a Dormant entry for it must carry periods_per_year = 12.
        # ONE universe per family key. The production runners pass both universes
        # in one call and both share the same 18/16 pattern_ids, so a two-universe
        # replay under a capture keyed by pattern_id keeps whichever universe ran
        # LAST (sp600): the first demo showed n=1678 (= the sp600 row's 1677) and a
        # +0.27 / -2.11 "drift" for the sp500 families. A single-universe call is
        # documented as legitimate by both engines (the DSR denominator is unchanged).
        "quarter_end_marking": lambda: run_qem_screening(_two_universe_windows(end, only="sp500")),  # run_quarter_end_marking.py
        "small_cap_quarter_end_marking": lambda: run_qem_screening(_two_universe_windows(end, only="sp600")),
        "tax_loss_selling_turn_of_year": lambda: run_tax_loss_screening(_two_universe_windows(end, only="sp500")),  # run_tax_loss_selling.py
        "small_cap_tax_loss_selling_turn_of_year": lambda: run_tax_loss_screening(_two_universe_windows(end, only="sp600")),
        "rebalancing_pressure": lambda: run_rebalancing_screening(end=end),  # run_rebalancing_pressure.py
        "dividend_payment_pressure": lambda: run_dividend_pressure_screening(end=end),  # run_dividend_payment_pressure.py
        "margin_credit": lambda: run_margin_credit_screening(),  # run_margin_credit.py; panel rebuilt from current inputs
        "ipo_lockup_expiration": lambda: run_ipo_lockup_screening(policy=PREREGISTERED_IDENTITY),  # run_ipo_lockup_expiration.py
    }


def _two_universe_windows(end: date, only: str | None = None) -> dict:
    """The WINDOWS mapping run_quarter_end_marking.py / run_tax_loss_selling.py
    both declare: sp500 from sp500_membership_history.MEMBERSHIP_DATA_START,
    sp600 from small_cap_membership_history.MEMBERSHIP_DATA_START. `only`
    restricts it to one universe (see the registry note on the capture collision)."""
    from app.services.research_lab.small_cap_membership_history import (
        MEMBERSHIP_DATA_START as SMALL_CAP_START,
    )
    from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

    windows = {"sp500": (MEMBERSHIP_DATA_START, end), "sp600": (SMALL_CAP_START, end)}
    if only is not None:
        if only not in windows:
            raise KeyError(f"unknown universe {only!r}; expected one of {sorted(windows)}")
        windows = {only: windows[only]}
    return windows


# Bespoke replay engines the effective-N hooks do not know about. Each takes
# a spec object carrying `spec_id` and returns a result with `.status` and
# `.daily_returns`; the IPO-lockup result's spec_id carries the cost arm
# ("...|raw|all"), which is the persisted trial_id, so the result's own id
# is preferred over the argument's.
# THE COST-ARM TRAP, found by the first demo runs: rebalancing, dividend-
# pressure and margin-credit replay every spec once PER COST ARM
# (cost_free, baseline, ...), and the persisted trial row is the BASELINE
# arm's. A last-write-wins capture keeps whichever arm ran last, which is
# why rebalancing's demo showed a −0.175 "drift" with identical n. So the
# screen_* function that receives `cost_arm=` is wrapped to open a recording
# window only while it is the baseline arm; the replay wrapper records only
# inside that window. margin_credit's persisted Sharpe is on
# `overlay_returns` (screen_margin_credit: sharpe_ratio(r.overlay_returns,
# MONTHS_PER_YEAR)), not `strategy_returns`, so that is what is recorded.
# IPO-lockup's arm is part of its spec_id ("...|raw|all"), no gating needed.
_EXTRA_BESPOKE = (
    # (module, replay fn, series attr, screen fn that carries cost_arm=, baseline constant)
    ("rebalancing_pressure_timing", "run_rebalancing_backtest", "daily_returns", "screen_rebalancing_pressure", "BASELINE_COST_ARM"),
    ("dividend_payment_pressure_timing", "run_dividend_pressure_backtest", "daily_returns", "screen_dividend_pressure", "BASELINE_COST_ARM"),
    ("margin_credit_timing", "run_margin_credit_backtest", "overlay_returns", "screen_margin_credit", "BASELINE_COST_ARM"),
    ("ipo_lockup_expiration", "run_ipo_lockup_backtest", "daily_returns", None, None),
)
_EXTRA_HOOKS_INSTALLED = False
_RECORDING_OPEN: dict[str, bool] = {}  # module name -> inside the baseline arm?


def _wrap_bespoke(module, name: str, series_attr: str, gate_key: str | None) -> None:
    original = getattr(module, name, None)
    if original is None or not callable(original):
        return

    def wrapper(*args, **kwargs):
        result = original(*args, **kwargs)
        if gate_key is not None and not _RECORDING_OPEN.get(gate_key, False):
            return result
        sid = gen._spec_id_of(result) or gen._find_spec_id(args, kwargs)
        if sid is not None and getattr(result, "status", "ok") == "ok":
            gen._record(sid, getattr(result, series_attr, None))
        return result

    setattr(module, name, wrapper)
    gen._PATCHED.append((module, name, original))


def _wrap_arm_gate(module, screen_name: str, baseline_attr: str, gate_key: str) -> None:
    original = getattr(module, screen_name, None)
    baseline = getattr(module, baseline_attr, None)
    if original is None or baseline is None:
        raise RuntimeError(f"{module.__name__}: cannot gate on {screen_name}/{baseline_attr}")

    def wrapper(*args, **kwargs):
        _RECORDING_OPEN[gate_key] = kwargs.get("cost_arm", baseline) == baseline
        try:
            return original(*args, **kwargs)
        finally:
            _RECORDING_OPEN[gate_key] = False

    setattr(module, screen_name, wrapper)
    gen._PATCHED.append((module, screen_name, original))


# THE SHARED-HARNESS ARM TRAP (the same defect one level up, found 2026-09-09
# evening). quarter_end_marking and tax_loss_selling replay through the SHARED
# harness (run_cross_sectional_backtest), whose hub hook has no arm gate. Both
# replay every spec a second, third and fourth time inside a sensitivity
# function — qem._cost_arm(multiplier=0/1/2), tls._sensitivity_arm(borrow
# 0/34/430bp) — and the hub's last-write-wins capture kept the LAST arm's
# series: for qem the x2-cost arm, for tls the 430bp-borrow arm. The persisted
# row is the main replay's. Measured on the original window (sp500, end
# 2026-09-05): the committed run's cost_x2 Sharpe for
# qem_month_placebo_day0_perf_h126 is -0.5104 and its borrow_430bp Sharpe for
# tls_dec_full_year_lossonly_h21 is +0.0349 — the very numbers the "drifted"
# re-runs produced (-0.508 / +0.034; the last 1-2e-3 is the EDGE half-spread
# calibration re-pooled over the 4-day-longer demo panel, see
# REPRODUCIBILITY_GAP_ROOT_CAUSE_2026-09-09.md). The gate below swaps the
# family module's harness binding back to the UNHOOKED original for the
# duration of the sensitivity function, so only the main replay is recorded.
_HUB_ARM_GATES = (
    # (module, sensitivity fn whose replays must NOT be recorded)
    ("cross_sectional_quarter_end_marking", "_cost_arm"),
    ("cross_sectional_tax_loss_selling", "_sensitivity_arm"),
)


def _unhooked_hub() -> Callable:
    """The shared harness as it was before gen.install_capture_hooks wrapped it."""
    from app.services.research_lab import cross_sectional as xs

    for module, name, original in gen._PATCHED:
        if module is xs and name == "run_cross_sectional_backtest":
            return original
    raise RuntimeError("install_capture_hooks() has not wrapped run_cross_sectional_backtest")


def _wrap_hub_arm_gate(module, fn_name: str, unhooked: Callable) -> None:
    original = getattr(module, fn_name, None)
    if original is None or not callable(original):
        raise RuntimeError(f"{module.__name__}: cannot gate on {fn_name}")

    def wrapper(*args, **kwargs):
        hooked = module.run_cross_sectional_backtest
        module.run_cross_sectional_backtest = unhooked
        try:
            return original(*args, **kwargs)
        finally:
            module.run_cross_sectional_backtest = hooked

    setattr(module, fn_name, wrapper)
    gen._PATCHED.append((module, fn_name, original))


def install_extra_hooks() -> None:
    global _EXTRA_HOOKS_INSTALLED
    if _EXTRA_HOOKS_INSTALLED:
        return
    import importlib

    for mod_name, replay_fn, series_attr, screen_fn, baseline_attr in _EXTRA_BESPOKE:
        module = importlib.import_module(f"app.services.research_lab.{mod_name}")
        gate_key = mod_name if screen_fn else None
        if screen_fn:
            _wrap_arm_gate(module, screen_fn, baseline_attr, gate_key)
        _wrap_bespoke(module, replay_fn, series_attr, gate_key)
    unhooked = _unhooked_hub()
    for mod_name, fn_name in _HUB_ARM_GATES:
        module = importlib.import_module(f"app.services.research_lab.{mod_name}")
        _wrap_hub_arm_gate(module, fn_name, unhooked)
    _EXTRA_HOOKS_INSTALLED = True


# Persisted family keys that CANNOT be re-scored by this script, each with the
# reason. Every persisted key must be in the table above or here — pinned by
# tests/test_dormant_rescore.py against the criteria_fix family list.
NOT_RESCORABLE = {
    **gen.EXCLUDED_FAMILIES,
    "funding_carry": gen.EXCLUDED_FAMILIES["funding_carry / funding_carry_pit / ofi_crypto"],
    "funding_carry_pit": gen.EXCLUDED_FAMILIES["funding_carry / funding_carry_pit / ofi_crypto"],
    "ofi_crypto": gen.EXCLUDED_FAMILIES["funding_carry / funding_carry_pit / ofi_crypto"],
    "low_frequency_patterns": (
        "replays vendor 15-minute bars from a gitignored cache (data/intraday_bars_15min); the "
        "inputs are not in the repository, so a re-run is not reproducible from a checkout. Closed "
        "family (scorecard definite_negative) in any case."
    ),
    "firesale_pressure": "script-driven evaluation (evaluate_specs), no per-spec replay to hook; closed STRUCTURAL (long leg unformable from N-PORT breadth).",
    "small_cap_firesale_pressure": "as firesale_pressure.",
    "dumb_money": "script-driven evaluation (quintile_portfolio_returns), no per-spec replay to hook; closed on a well-powered reversed sign — verify the power number before any Dormant entry.",
    "small_cap_dumb_money": "as dumb_money.",
    "inelastic_markets": "script-driven GIV panel, no per-spec replay; closed by MECHANISM (the source itself predicts no forecastability).",
    "nport_flow_fit": "no trials found under this key in cross_sectional_trial_results at the time of writing; the family's run_nport_flow_screening(start, end) IS hookable (shared harness) — add to the table once its persisted key is confirmed.",
    "lazy_prices_ptit_fix_verification": "diagnostic re-run of lazy_prices, not a separate candidate.",
    "lazy_prices_vocab_ceiling_confound": "diagnostic re-run of lazy_prices, not a separate candidate.",
    "lazy_prices_xom_hypothesis_test_fast": "diagnostic re-run of lazy_prices, not a separate candidate.",
}


# Rescorable families whose re-run does NOT reproduce the persisted Sharpe on
# the IDENTICAL window and universe, for a reason not yet found. EMPTY since
# 2026-09-09 evening: the two entries recorded that morning (quarter_end_marking
# rerun -0.508 vs persisted -0.215; tax_loss_selling_turn_of_year +0.034 vs
# +0.091) were NOT data revisions — they were this script capturing the last
# sensitivity arm instead of the main replay (see _HUB_ARM_GATES). With the
# gate in place both families reproduce their persisted Sharpe exactly on the
# original window; the record is REPRODUCIBILITY_GAP_ROOT_CAUSE_2026-09-09.md
# beside this file. The mechanism stays: a key listed here can never receive
# pit_ok = True in a Dormant entry, whatever its statistical tier.
KNOWN_REPRODUCIBILITY_GAPS: dict[str, str] = {}


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
        install_extra_hooks()
        _HOOKS_INSTALLED = True
    gen.CAPTURED.clear()
    gen._REPLAY_OWNER.clear()
    results = registry[family_key]()
    if not isinstance(results, (list, tuple)):
        results = []  # a summary object: the hooks did the capturing
    for r in results:  # capture route (1): result objects that carry the series
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
        ppy = float(DEMO_PERIODS_PER_YEAR.get(family_key, metrics.TRADING_DAYS_PER_YEAR))
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
