"""POOLED, PROJECT-WIDE TRIAL COUNT for the Deflated Sharpe Ratio.

WHAT THIS FIXES, stated as the bug it is
========================================
deflated_sharpe.compute_deflated_sharpe() takes `n_trials` as an input and
corrects the Sharpe for having searched that many configurations. Until this
run, EVERY family passed its OWN grid size:

    cross_sectional.screen_cross_sectional_family:1899   n_trials = len(specs)
    cross_sectional_country_valmom.py:438                CVM_N_TRIALS = 15
    cross_sectional_bonds.py:640                         BONDS_N_TRIALS = 18
    cross_sectional_crypto.py:789                        CRYPTO_N_TRIALS = 28
    ... and ~25 more

That denominator answers "how many variants did THIS family try", which is
not the question the False Strategy theorem asks. The selection that produced
any registered spec was made across the WHOLE project: 30-odd families were
built, screened, and kept or abandoned over months, and the choice of which
family's best spec to register was itself a comparison across all of them. A
per-family n_trials silently prices none of that in.

The one prior exception, and the precedent this run generalizes:
cross_sectional_residual_momentum_dm_overlay.py:245 already pools ACROSS a
family boundary --

    DM_OVERLAY_PRIOR_TRIALS = 18
    DM_OVERLAY_N_TRIALS = DM_OVERLAY_PRIOR_TRIALS + DM_OVERLAY_N_NEW_SPECS  # 30

-- on exactly this reasoning ("those 18 Sharpes were computed, persisted and
READ before these 12 specs were designed"). It was done by hand, for one
family. This run measures the pooled number for all of them.

WHY "EFFECTIVE" AND NOT THE RAW POOLED COUNT
============================================
The raw pooled count is not right either, in the opposite direction. Trials
inside a family are near-duplicates of one another: si_ratio_hedged_h21,
si_ratio_hedged_h63 and si_ratio_hedged_h126 are one bet observed at three
holding periods, not three independent draws from the noise distribution.
Counting them as three inflates SR0 and over-deflates.

effective_n_clustering.py (ONC; Lopez de Prado & Lewis 2019) answers exactly
this: cluster the trials on their realized return correlations and count the
clusters. This script's whole job is to run that estimator on the POOLED
population rather than on one family, or on the post-selection subset that
data/research_runs/run_effective_n_clustering.py used.

THE SELECTION BIAS IN THE PRIOR RUN, and what changed
=====================================================
run_effective_n_clustering.py's POP-B was "every spec whose persisted DSR
clears the 0.50 floor" -- 42 specs. That population is conditioned on the
outcome, so its E[K]=8..10 cannot be used as a search-breadth denominator:
the trials that were searched and FAILED are exactly the ones a multiplicity
correction exists to count. This run uses the unconditioned population: every
spec every family screened, pass or fail.

Two further gaps that run also had, closed here:
  * 11 families never persisted a single trial row (verified by direct query
    against cross_sectional_trial_results before this run). Their specs were
    invisible to any pooled count. This script persists them.
  * Its Stage 1 covered 11 families / 203 specs. This one covers every family
    whose replay engine can be hooked; the families it still cannot reach are
    listed in the report with the direction of the bias they cause.

STAGES
======
  --stage rebuild   run every family, persist its trials to
                    cross_sectional_trial_results, and record every spec's
                    realized daily return series into one pooled matrix
  --stage cluster   ONC over the pooled matrix across a seed sweep -> the
                    committed global_effective_n.json artifact
  --stage dsr       recompute every family's best spec under both the old
                    local N and the new pooled effective N, side by side

Run from backend/ with ./venv/bin/python data/research_runs/run_global_effective_n.py
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate (identical in intent
# to run_effective_n_clustering.py's and run_country_valmom.py's). Running this
# file by path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv, whose site-packages
# would resolve `app` to the MAIN worktree's backend/app.
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

RUN_TAG = "global_effective_n_2026-09-04"
OUT_DIR = _BACKEND / "data" / "research_runs"
MATRIX_PATH = OUT_DIR / "global_effective_n_return_matrix_2026-09-04.csv.gz"
META_PATH = OUT_DIR / "global_effective_n_return_matrix_2026-09-04.meta.json"

# THE COMMITTED ARTIFACT the production code reads. Deliberately a tracked
# file and not a code constant: a constant baked into a module goes stale
# silently as trials accumulate, and nothing in a diff would show it. See
# app/services/research_lab/global_effective_n.py for the reader.
CONFIG_PATH = _BACKEND / "app" / "services" / "research_lab" / "global_effective_n.json"

CLUSTER_REPORT_PATH = OUT_DIR / "global_effective_n_2026-09-04.txt"
CLUSTER_JSON_PATH = OUT_DIR / "global_effective_n_2026-09-04.json"
DSR_REPORT_PATH = OUT_DIR / "global_effective_n_dsr_before_after_2026-09-04.txt"
DSR_JSON_PATH = OUT_DIR / "global_effective_n_dsr_before_after_2026-09-04.json"

# Seed for the headline estimate, and the sweep every reported E[K] is
# additionally measured across. ONC is a stochastic k-means search; a single
# seed's cluster count is one draw, and quoting it alone would present more
# precision than a k-means restart delivers. Same discipline, same sweep width
# as run_effective_n_clustering.py.
RANDOM_STATE = 20260904
SEED_SWEEP = list(range(20260904, 20260904 + 25))

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    stream=sys.stderr)


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# RETURN-SERIES CAPTURE
# ---------------------------------------------------------------------------
#
# Every family computes a realized daily return series per spec and then keeps
# only summary statistics. The series is what ONC needs. Three capture routes,
# tried in this order per family, because no single one reaches every engine:
#
#  (1) THE RESULT OBJECT ITSELF. A few families (country_valmom) already carry
#      `.daily_returns` on their per-spec result dataclass. Read it directly --
#      no patching, nothing to go wrong.
#  (2) THE SHARED HARNESS. Most equity/bond/FX/commodity/crypto families route
#      every replay through cross_sectional.run_cross_sectional_backtest. One
#      wrapper on that function sees all of them. NOTE: several modules do
#      `from ... import run_cross_sectional_backtest`, binding their OWN
#      reference, so patching only the defining module would miss them --
#      every imported module's binding is patched, checked by name.
#  (3) A BESPOKE ENGINE. Event-driven families (index_removal, insider, pead)
#      and the timing/CRP/eigen families have their own replay functions with
#      the same shape: take a spec, return an object with `.daily_returns`.
#      Each is wrapped the same way.
#
# The dividend-month and earnings-premium engines are the one shape that needs
# two hooks: their replay result carries GROSS returns and a turnover path, and
# the net series is produced later by a module-level net_daily_returns(replay,
# ...). The replay hook records id(replay) -> spec_id and the net hook uses it,
# so the captured series is the net one the family's own Sharpe is computed on
# -- never the gross one, which would silently overstate every correlation
# input by the cost path they all share.

CAPTURED: dict[str, pd.Series] = {}
_REPLAY_OWNER: dict[int, str] = {}  # id(replay result) -> spec id
_PATCHED: list[tuple[Any, str, Any]] = []


def _spec_id_of(obj: Any) -> str | None:
    for attr in ("pattern_id", "spec_id"):
        value = getattr(obj, attr, None)
        if isinstance(value, str) and value:
            return value
    return None


def _find_spec_id(args: tuple, kwargs: dict) -> str | None:
    for value in (*args, *kwargs.values()):
        found = _spec_id_of(value)
        if found is not None:
            return found
    return None


def _record(spec_id: str, series: Any) -> None:
    if not isinstance(series, pd.Series) or series.empty:
        return
    clean = series.dropna()
    if clean.empty:
        return
    # Last write wins DELIBERATELY: a family that replays the same spec twice
    # (a cost-sensitivity arm, a diagnostic pass) ends on its headline arm.
    CAPTURED[spec_id] = clean


def _wrap_replay(module: Any, name: str) -> None:
    original = getattr(module, name, None)
    if original is None or not callable(original):
        return

    def wrapper(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        result = original(*args, **kwargs)
        spec_id = _find_spec_id(args, kwargs)
        if spec_id is not None:
            if getattr(result, "status", "ok") == "ok":
                _record(spec_id, getattr(result, "daily_returns", None))
            # gross-only engines: remember who owns this replay for the
            # net_daily_returns hook below.
            if getattr(result, "gross_daily_returns", None) is not None:
                _REPLAY_OWNER[id(result)] = spec_id
        return result

    setattr(module, name, wrapper)
    _PATCHED.append((module, name, original))


def _wrap_net_returns(module: Any) -> None:
    original = getattr(module, "net_daily_returns", None)
    if original is None or not callable(original):
        return

    def wrapper(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        series = original(*args, **kwargs)
        replay = kwargs.get("replay") if "replay" in kwargs else (args[0] if args else None)
        spec_id = _REPLAY_OWNER.get(id(replay)) if replay is not None else None
        if spec_id is not None:
            _record(spec_id, series)
        return series

    setattr(module, "net_daily_returns", wrapper)
    _PATCHED.append((module, "net_daily_returns", original))


def install_capture_hooks() -> dict[str, int]:
    """Patch every replay entry point that is already imported. Returns a
    census of what was hooked, so the report can state which engines this run
    could actually see rather than implying it saw everything."""
    import importlib

    census: dict[str, int] = {}

    # (2) the shared harness, in its defining module AND in every module that
    # imported the name into its own namespace.
    from app.services.research_lab import cross_sectional as xs

    _wrap_replay(xs, "run_cross_sectional_backtest")
    census["cross_sectional.run_cross_sectional_backtest"] = 1
    hub_wrapper = xs.run_cross_sectional_backtest
    n_rebound = 0
    for mod_name, mod in list(sys.modules.items()):
        if not mod_name.startswith("app.services.research_lab.") or mod is None:
            continue
        if getattr(mod, "run_cross_sectional_backtest", None) not in (None, hub_wrapper):
            setattr(mod, "run_cross_sectional_backtest", hub_wrapper)
            n_rebound += 1
    census["modules_rebound_to_hub_wrapper"] = n_rebound

    # (3) the bespoke engines, one hook each.
    bespoke = [
        ("cross_sectional_index_removal", "run_index_removal_backtest"),
        ("cross_sectional_insider", "run_insider_backtest"),
        ("cross_sectional_pead", "run_pead_backtest"),
        ("cross_sectional_correlation_risk_premium", "run_crp_backtest"),
        ("cross_sectional_eigenportfolio", "run_eigen_replay"),
        ("vol_regime_timing", "run_timing_backtest"),
        ("cross_sectional_dividend_month", "run_dmp_backtest"),
        ("cross_sectional_earnings_premium", "run_eap_backtest"),
    ]
    for mod_name, fn_name in bespoke:
        module = importlib.import_module(f"app.services.research_lab.{mod_name}")
        before = len(_PATCHED)
        _wrap_replay(module, fn_name)
        census[f"{mod_name}.{fn_name}"] = int(len(_PATCHED) > before)

    for mod_name in ("cross_sectional_dividend_month", "cross_sectional_earnings_premium"):
        module = importlib.import_module(f"app.services.research_lab.{mod_name}")
        _wrap_net_returns(module)
        census[f"{mod_name}.net_daily_returns"] = 1

    return census


# ---------------------------------------------------------------------------
# FAMILY REGISTRY
# ---------------------------------------------------------------------------
#
# Every invocation below is COPIED from an existing, committed call site rather
# than invented here, so each family runs against the same window it ran
# against when its own reported numbers were produced. The source of each is
# named in `invocation_source`. Where two committed call sites disagree, the
# most recent one wins and the older is noted.


@dataclass
class Family:
    key: str  # family_key written to cross_sectional_trial_results
    label: str
    invoke: Callable[[], list]
    n_trials_constant: str  # the local constant this run replaces, for the report
    local_n_trials: int
    invocation_source: str
    periods_per_year: float = 252.0
    already_persisted: bool = True  # False = one of the 11 persistence gaps
    note: str = ""


def _edgar():  # noqa: ANN202
    from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider

    return EdgarXbrlProvider()


def build_registry() -> list[Family]:
    from app.services.market_data.yfinance_provider import YFinanceProvider  # noqa: F401
    from app.services.research_lab.cross_sectional_asset_growth import (
        ASSET_GROWTH_N_TRIALS,
        run_asset_growth_screening,
    )
    from app.services.research_lab.cross_sectional_best_ideas import (
        BEST_IDEAS_N_TRIALS,
        run_best_ideas_screening,
    )
    from app.services.research_lab.cross_sectional_bonds import (
        BONDS_N_TRIALS,
        run_bonds_screening,
    )
    from app.services.research_lab.cross_sectional_buyback import (
        BUYBACK_N_TRIALS,
        run_buyback_screening,
    )
    from app.services.research_lab.cross_sectional_commodities import (
        COMMODITIES_N_TRIALS,
        run_commodities_screening,
    )
    from app.services.research_lab.cross_sectional_correlation_risk_premium import (
        CRP_N_TRIALS,
        run_crp_screening,
    )
    from app.services.research_lab.cross_sectional_country_valmom import (
        CVM_N_TRIALS,
        run_country_valmom_screening,
    )
    from app.services.research_lab.cross_sectional_crypto import (
        CRYPTO_N_TRIALS,
        run_crypto_screening,
    )
    from app.services.research_lab.cross_sectional_dividend_month import (
        DMP_N_TRIALS,
        run_dmp_screening,
    )
    from app.services.research_lab.cross_sectional_earnings_premium import (
        EAP_N_TRIALS,
        run_eap_screening,
    )
    from app.services.research_lab.cross_sectional_eigenportfolio import (
        EIGEN_N_TRIALS,
        run_eigenportfolio_screening,
    )
    from app.services.research_lab.cross_sectional_fx import FX_N_TRIALS, screen_fx_family
    from app.services.research_lab.cross_sectional_illiq import run_illiq_screening
    from app.services.research_lab.cross_sectional_index_removal import (
        REMOVAL_N_TRIALS,
        run_index_removal_screening,
    )
    from app.services.research_lab.cross_sectional_insider import (
        INSIDER_N_TRIALS,
        run_insider_screening,
    )
    from app.services.research_lab.cross_sectional_ivol import run_round_d1_screening
    from app.services.research_lab.cross_sectional_jump_drift import run_jump_drift_screening
    from app.services.research_lab.cross_sectional_lazy_prices import (
        LAZY_PRICES_N_TRIALS,
        run_lazy_prices_screening,
    )
    from app.services.research_lab.cross_sectional_patterns import run_round_c_screening
    from app.services.research_lab.cross_sectional_patterns_d2 import (
        D2_N_TRIALS,
        screen_d2_reversal_family,
    )
    from app.services.research_lab.cross_sectional_pead import PEAD_N_TRIALS, run_pead_screening
    from app.services.research_lab.cross_sectional_quality import (
        CBOP_N_TRIALS,
        NOA_N_TRIALS,
        run_quality_screening,
    )
    from app.services.research_lab.cross_sectional_quality_neutral import (
        NOA_NEUTRAL_DSR_N_TRIALS,
        run_noa_neutral_screening,
    )
    from app.services.research_lab.cross_sectional_residual_momentum import (
        RESIDUAL_MOM_N_TRIALS,
        run_residual_momentum_screening,
    )
    from app.services.research_lab.cross_sectional_seasonality import run_seasonality_screening
    from app.services.research_lab.cross_sectional_short_interest import (
        SHORT_INTEREST_FORMATION_START,
        SHORT_INTEREST_N_TRIALS,
        run_short_interest_screening,
    )
    from app.services.research_lab.cross_sectional_small_mid_cap import (
        DISPOSITION_N_TRIALS,
        IVOL_N_TRIALS,
        run_small_cap_disposition_screening,
        run_small_cap_ivol_screening,
    )
    from app.services.research_lab.metrics import CALENDAR_DAYS_PER_YEAR
    from app.services.research_lab.small_cap_membership_history import (
        MEMBERSHIP_DATA_START as SMALL_CAP_START,
    )
    from app.services.research_lab.sp500_membership_history import (
        MEMBERSHIP_DATA_START,
        get_universe_over,
    )
    from app.services.research_lab.vol_regime_timing import (
        VOL_REGIME_N_TRIALS,
        run_vol_regime_screening,
    )

    DC = "data/research_runs/run_dividend_convention.py::_families"

    def quality_all() -> list:
        s = run_quality_screening(end=date(2026, 8, 28), edgar=_edgar())
        return list(s.cbop_results) + list(s.noa_results)

    return [
        # ---- families that ALREADY persisted trials -----------------------
        Family("quality_cbop", "quality (cbop + noa)", quality_all,
               "CBOP_N_TRIALS / NOA_N_TRIALS", max(CBOP_N_TRIALS, NOA_N_TRIALS), DC),
        Family("quality_noa_industry_neutral", "noa industry-neutral",
               lambda: run_noa_neutral_screening(end=date(2026, 8, 28), edgar=_edgar()).results,
               "NOA_NEUTRAL_DSR_N_TRIALS", NOA_NEUTRAL_DSR_N_TRIALS, DC),
        Family("short_interest", "short interest",
               lambda: run_short_interest_screening(
                   start=SHORT_INTEREST_FORMATION_START, end=date(2026, 9, 2),
                   edgar=_edgar()).results,
               "SHORT_INTEREST_N_TRIALS", SHORT_INTEREST_N_TRIALS, DC),
        Family("lazy_prices", "lazy prices",
               lambda: run_lazy_prices_screening(
                   MEMBERSHIP_DATA_START, date(2026, 8, 31),
                   tickers=get_universe_over(MEMBERSHIP_DATA_START, date(2026, 8, 31))).results,
               "LAZY_PRICES_N_TRIALS", LAZY_PRICES_N_TRIALS, DC),
        Family("residual_momentum", "residual momentum",
               lambda: run_residual_momentum_screening(end=date(2026, 9, 2), edgar=_edgar()).results,
               "RESIDUAL_MOM_N_TRIALS", RESIDUAL_MOM_N_TRIALS, DC),
        Family("asset_growth", "asset growth",
               lambda: run_asset_growth_screening(end=date(2026, 9, 1), edgar=_edgar()).results,
               "ASSET_GROWTH_N_TRIALS", ASSET_GROWTH_N_TRIALS, DC),
        Family("liquidity_shock_delta_illiq", "illiquidity shock",
               lambda: run_illiq_screening(MEMBERSHIP_DATA_START, date(2026, 8, 28))[0],
               "len(specs) via the shared harness", 8, DC),
        Family("same_calendar_month_seasonality", "same-calendar-month seasonality",
               lambda: run_seasonality_screening(MEMBERSHIP_DATA_START, date(2026, 8, 28))[0],
               "len(specs) via the shared harness", 8, DC),
        Family("round_c", "patterns round C",
               lambda: run_round_c_screening(MEMBERSHIP_DATA_START, date(2026, 8, 30))[0],
               "len(specs) via the shared harness", 30, DC),
        Family("jump_drift", "jump drift",
               lambda: run_jump_drift_screening(
                   MEMBERSHIP_DATA_START, date(2026, 8, 30), run_event_study=False).results,
               "len(specs) via the shared harness", 24, DC),
        Family("best_ideas_13f", "best ideas 13F",
               lambda: run_best_ideas_screening(end=date(2026, 8, 31)).results,
               "BEST_IDEAS_N_TRIALS", BEST_IDEAS_N_TRIALS, DC),
        Family("correlation_risk_premium", "correlation risk premium",
               lambda: run_crp_screening(end=date(2026, 8, 31),
                                         include_pit_crosscheck=False).results,
               "CRP_N_TRIALS", CRP_N_TRIALS, DC),
        Family("country_valmom", "country index value/momentum",
               lambda: run_country_valmom_screening(end=date(2026, 8, 31)).results,
               "CVM_N_TRIALS", CVM_N_TRIALS, DC),
        Family("eigenportfolio_statarb", "eigenportfolio stat-arb",
               lambda: run_eigenportfolio_screening(
                   end=date(2026, 8, 31), include_reversal_diagnostic=False,
                   include_edge_cost_diagnostic=False).results,
               "EIGEN_N_TRIALS", EIGEN_N_TRIALS, DC),
        Family("dividend_month_premium", "dividend month premium",
               lambda: run_dmp_screening(MEMBERSHIP_DATA_START, date(2026, 8, 31)).results,
               "DMP_N_TRIALS", DMP_N_TRIALS,
               "data/research_runs/run_dividend_month_premium.py"),
        Family("earnings_announcement_premium", "earnings announcement premium",
               lambda: run_eap_screening(MEMBERSHIP_DATA_START, date(2026, 8, 31)).results,
               "EAP_N_TRIALS", EAP_N_TRIALS, DC),
        Family("insider_opportunistic", "insider opportunistic buying",
               lambda: run_insider_screening(MEMBERSHIP_DATA_START, date(2026, 8, 31)).results,
               "INSIDER_N_TRIALS", INSIDER_N_TRIALS, DC),
        Family("pead_ear", "PEAD / earnings announcement return",
               lambda: run_pead_screening(MEMBERSHIP_DATA_START, date(2026, 8, 31)).results,
               "PEAD_N_TRIALS", PEAD_N_TRIALS, DC),

        # ---- THE 11 PERSISTENCE GAPS --------------------------------------
        # Confirmed absent from cross_sectional_trial_results by direct query
        # before this run. Each gets a family_key here for the first time.
        Family("fx", "FX carry / momentum / value",
               lambda: screen_fx_family(end=date(2026, 8, 31)).results,
               "FX_N_TRIALS", FX_N_TRIALS,
               "research_archive/session_2026-08-22_to_27/rerun.py.bak (screen_fx_family)",
               already_persisted=False,
               note="rate differentials fetched from FRED, as the family's own default does"),
        Family("crypto", "crypto cross-section (xc_btcbeta's family)",
               lambda: run_crypto_screening(end=date(2026, 8, 31)).results,
               "CRYPTO_N_TRIALS", CRYPTO_N_TRIALS, DC,
               periods_per_year=float(CALENDAR_DAYS_PER_YEAR), already_persisted=False,
               note="365-day year: this family trades every calendar day"),
        Family("small_cap_disposition", "small/mid cap disposition",
               lambda: run_small_cap_disposition_screening(SMALL_CAP_START, date(2026, 8, 31))[0],
               "DISPOSITION_N_TRIALS", DISPOSITION_N_TRIALS, DC, already_persisted=False),
        Family("small_cap_ivol", "small/mid cap idiosyncratic vol",
               lambda: run_small_cap_ivol_screening(SMALL_CAP_START, date(2026, 8, 31))[0],
               "IVOL_N_TRIALS", IVOL_N_TRIALS, DC, already_persisted=False),
        Family("commodities", "commodities",
               lambda: run_commodities_screening(end=date(2026, 8, 31)).results,
               "COMMODITIES_N_TRIALS", COMMODITIES_N_TRIALS, DC, already_persisted=False),
        Family("ivol", "round D1 idiosyncratic vol",
               lambda: run_round_d1_screening(MEMBERSHIP_DATA_START, date(2026, 8, 28))[0],
               "len(specs) via the shared harness", 21, DC, already_persisted=False),
        Family("bonds", "bonds",
               lambda: run_bonds_screening(end=date(2026, 8, 31)).results,
               "BONDS_N_TRIALS", BONDS_N_TRIALS, DC, already_persisted=False),
        Family("buyback", "buyback / net share issuance",
               lambda: run_buyback_screening(end=date(2026, 8, 31)).results,
               "BUYBACK_N_TRIALS", BUYBACK_N_TRIALS, DC, already_persisted=False),
        Family("index_removal", "index removal",
               lambda: run_index_removal_screening(MEMBERSHIP_DATA_START, date(2026, 8, 31)).results,
               "REMOVAL_N_TRIALS", REMOVAL_N_TRIALS, DC, already_persisted=False),
        Family("patterns_d2", "patterns round D2 reversal",
               lambda: screen_d2_reversal_family(MEMBERSHIP_DATA_START, date(2026, 8, 30)).results,
               "D2_N_TRIALS", D2_N_TRIALS, DC, already_persisted=False),
        Family("vol_regime", "vol-regime timing",
               lambda: run_vol_regime_screening(end=date(2026, 8, 31)).results,
               "VOL_REGIME_N_TRIALS", VOL_REGIME_N_TRIALS, DC, already_persisted=False),
    ]


# Families this run deliberately does NOT rebuild, each with the reason. Stated
# as data so the report cannot quietly omit one.
EXCLUDED_FAMILIES = {
    "phase_a_intraday_expanded": (
        "212 specs on the intraday engine (intraday_patterns.py), which replays minute bars "
        "rather than the daily harness. Its 212 trials ARE already persisted, so they are "
        "counted in the raw pooled trial count; only their return series are missing from the "
        "correlation matrix. EXCLUDING them from the clustering biases E[K] DOWN (fewer "
        "distinct bets in the pool), i.e. toward a SMALLER, more lenient denominator."
    ),
    "multi_signal_combination": (
        "its 4 trials are weighted COMBINATIONS of specs already in the pool, not independent "
        "searches. Counting them would double-count their constituents."
    ),
    "funding_carry / funding_carry_pit / ofi_crypto": (
        "Binance perpetual-futures families whose replay does not route through either the "
        "shared harness or a hookable per-spec engine. 28 persisted trials; counted raw, "
        "absent from the matrix. Same downward bias on E[K] as phase_a."
    ),
    "residual_momentum_dm_overlay": (
        "produces a MONTHLY return series. Correlating it against daily series needs a "
        "resampling choice that would be this script's invention rather than the family's. "
        "Its 12 trials are persisted by this run's sibling change and counted raw."
    ),
}


# ---------------------------------------------------------------------------
# STAGE: rebuild
# ---------------------------------------------------------------------------


def stage_rebuild(only: str | None) -> None:
    from app.db import SessionLocal
    from app.models.cross_sectional_trial_result import CrossSectionalTrialResult
    from app.services.research_lab.cross_sectional_persistence import (
        persist_cross_sectional_trial_results,
    )

    registry = build_registry()
    if only:
        wanted = {k.strip() for k in only.split(",")}
        registry = [f for f in registry if f.key in wanted]

    census = install_capture_hooks()
    _log(f"capture hooks installed: {census}")

    series_by_spec: dict[str, pd.Series] = {}
    spec_meta: dict[str, dict[str, Any]] = {}
    family_status: list[dict[str, Any]] = []
    started = time.time()

    for fam in registry:
        CAPTURED.clear()
        _REPLAY_OWNER.clear()
        t0 = time.time()
        _log(f"running {fam.key} ({fam.label}) ...")
        try:
            results = fam.invoke()
        except Exception as exc:  # noqa: BLE001 -- a failure is REPORTED, never hidden
            traceback.print_exc()
            family_status.append({
                "family_key": fam.key, "label": fam.label, "status": "FAILED",
                "error": f"{type(exc).__name__}: {exc}", "elapsed_s": round(time.time() - t0, 1),
                "n_results": 0, "n_series_captured": 0,
                "local_n_trials": fam.local_n_trials,
                "n_trials_constant": fam.n_trials_constant,
                "already_persisted_before_this_run": fam.already_persisted,
                "invocation_source": fam.invocation_source, "note": fam.note,
            })
            continue

        # ---- persist (the 11 gaps get their first-ever rows here) ----------
        # IDEMPOTENT per (family_key, run_tag): this run takes ~1 hour and will
        # be restarted, and persist_cross_sectional_trial_results appends
        # unconditionally. Without the delete, a restart would silently double
        # every family it had already finished, and the pooled trial count --
        # the whole point of the exercise -- would be inflated by exactly the
        # number of restarts. Scoped to THIS run_tag only: no other run's rows
        # are touched, so every historical figure stays exactly where it is.
        persisted_rows = 0
        persist_error = None
        if results:
            db = SessionLocal()
            try:
                deleted = db.query(CrossSectionalTrialResult).filter(
                    CrossSectionalTrialResult.family_key == fam.key,
                    CrossSectionalTrialResult.run_tag == RUN_TAG,
                ).delete(synchronize_session=False)
                db.commit()
                if deleted:
                    _log(f"  (replacing {deleted} row(s) from an earlier attempt of this run_tag)")
                persisted_rows = persist_cross_sectional_trial_results(
                    db, fam.key, results, run_tag=RUN_TAG
                )
            except Exception as exc:  # noqa: BLE001
                persist_error = f"{type(exc).__name__}: {exc}"
                traceback.print_exc()
            finally:
                db.close()

        # ---- collect return series ----------------------------------------
        n_from_result_object = 0
        for res in results:
            spec_id = _spec_id_of(res)
            if spec_id is None:
                continue
            own = getattr(res, "daily_returns", None)
            if isinstance(own, pd.Series) and not own.dropna().empty:
                CAPTURED[spec_id] = own.dropna()
                n_from_result_object += 1

        captured_here = 0
        for res in results:
            spec_id = _spec_id_of(res)
            if spec_id is None or spec_id not in CAPTURED:
                continue
            series = CAPTURED[spec_id]
            # A spec id collision across families would silently overwrite one
            # family's series with another's. Namespaced only if it actually
            # collides, so ids stay readable and comparable to persisted rows.
            key = spec_id if spec_id not in series_by_spec else f"{fam.key}::{spec_id}"
            series_by_spec[key] = series
            deflated = getattr(res, "deflated_sharpe", None)
            spec_meta[key] = {
                "family_key": fam.key,
                "family_label": fam.label,
                "spec_id": spec_id,
                "periods_per_year": fam.periods_per_year,
                "n_observations": int(len(series)),
                "sharpe_annualized": float(getattr(res, "sharpe_annualized", float("nan"))),
                "local_n_trials": int(getattr(deflated, "n_trials", fam.local_n_trials))
                if deflated is not None else fam.local_n_trials,
                "local_dsr": (None if deflated is None else deflated.dsr),
                "psr_vs_zero": (None if deflated is None else deflated.psr_vs_zero),
                "sigma_sr_annualized": (
                    None if deflated is None else deflated.sigma_sr_annualized
                ),
                "skewness": (None if deflated is None else deflated.skewness),
                "kurtosis": (None if deflated is None else deflated.kurtosis),
                "holding_days": getattr(res, "holding_days", None),
            }
            captured_here += 1

        family_status.append({
            "family_key": fam.key, "label": fam.label, "status": "ok",
            "elapsed_s": round(time.time() - t0, 1),
            "n_results": len(results),
            "n_series_captured": captured_here,
            "n_series_from_result_object": n_from_result_object,
            "n_rows_persisted": persisted_rows,
            "persist_error": persist_error,
            "local_n_trials": fam.local_n_trials,
            "n_trials_constant": fam.n_trials_constant,
            "already_persisted_before_this_run": fam.already_persisted,
            "periods_per_year": fam.periods_per_year,
            "invocation_source": fam.invocation_source,
            "note": fam.note,
        })
        _log(f"  -> {len(results)} results, {captured_here} series, "
             f"{persisted_rows} rows persisted, {time.time() - t0:.0f}s")

        # Checkpoint after EVERY family: a run this long must not lose what it
        # already finished if it is interrupted.
        _write_matrix(series_by_spec, spec_meta, family_status, census, started)

    _write_matrix(series_by_spec, spec_meta, family_status, census, started)
    _log(f"rebuild done: {len(series_by_spec)} series across "
         f"{len({m['family_key'] for m in spec_meta.values()})} families")


def _write_matrix(series_by_spec: dict[str, pd.Series], spec_meta: dict[str, dict[str, Any]],
                  family_status: list[dict[str, Any]], census: dict[str, int],
                  started: float) -> None:
    if not series_by_spec:
        return
    matrix = pd.DataFrame(series_by_spec).sort_index()
    matrix.index.name = "date"
    with gzip.open(MATRIX_PATH, "wt") as fh:
        matrix.to_csv(fh)
    META_PATH.write_text(json.dumps({
        "run_tag": RUN_TAG,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_s": round(time.time() - started, 1),
        "matrix_shape": list(matrix.shape),
        "capture_hook_census": census,
        "excluded_families": EXCLUDED_FAMILIES,
        "families": family_status,
        "specs": spec_meta,
    }, indent=2, default=str))


# ---------------------------------------------------------------------------
# STAGE: cluster
# ---------------------------------------------------------------------------


def _pooled_raw_trial_count() -> dict[str, Any]:
    """The RAW pooled count, straight from the table, deduplicated by
    (family_key, trial_id). Deduplication is not optional: round_c has 7
    run_tags over the SAME 30 specs (cost-model re-audits) and
    phase_a_intraday_expanded has 6 over the same 212, so the row count
    (1,971 before this run) triple-counts re-runs of one search."""
    from sqlalchemy import text

    from app.db import engine

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT family_key, COUNT(DISTINCT trial_id) FROM cross_sectional_trial_results "
            "GROUP BY family_key ORDER BY family_key"
        )).fetchall()
        total_rows = conn.execute(
            text("SELECT COUNT(*) FROM cross_sectional_trial_results")
        ).scalar_one()
    per_family = {str(f): int(n) for f, n in rows}
    return {
        "total_rows": int(total_rows),
        "distinct_trials": int(sum(per_family.values())),
        "n_families": len(per_family),
        "per_family_distinct_trials": per_family,
    }


def stage_cluster() -> None:
    from app.services.research_lab.effective_n_clustering import (
        MIN_TRIALS_FOR_CLUSTERING,
        estimate_effective_n_from_returns,
        pooled_effective_n,
        variance_effective_n,
    )

    with gzip.open(MATRIX_PATH, "rt") as fh:
        matrix = pd.read_csv(fh, index_col=0, parse_dates=True)
    meta = json.loads(META_PATH.read_text())

    _log(f"clustering pooled matrix: {matrix.shape[0]} dates x {matrix.shape[1]} specs")
    sweep = pooled_effective_n(matrix, seeds=SEED_SWEEP, headline_seed=RANDOM_STATE)
    headline = sweep.headline

    corr = matrix.corr(min_periods=60)
    var_eff = variance_effective_n(corr)
    from_returns = estimate_effective_n_from_returns(matrix, random_state=RANDOM_STATE)

    raw = _pooled_raw_trial_count()

    # Per-family cluster composition: which families ended up sharing a
    # cluster is the substantive finding, not just the count.
    fam_of = {c: (meta["specs"].get(c, {}) or {}).get("family_key", "?") for c in matrix.columns}
    cluster_families = [
        {
            "cluster_id": c.cluster_id,
            "n_members": len(c.members),
            "families": sorted({fam_of.get(m, "?") for m in c.members}),
            "quality_tstat": c.quality_tstat,
            "members": c.members,
        }
        for c in headline.clusters
    ]

    payload = {
        "run_tag": RUN_TAG,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "matrix_shape": list(matrix.shape),
        "headline_seed": RANDOM_STATE,
        "seed_sweep": [SEED_SWEEP[0], SEED_SWEEP[-1]],
        "n_seeds": len(SEED_SWEEP),
        "min_trials_for_clustering": MIN_TRIALS_FOR_CLUSTERING,
        "global_effective_n_headline": headline.n_effective,
        "global_effective_n_mode": sweep.mode,
        "global_effective_n_min": sweep.minimum,
        "global_effective_n_max": sweep.maximum,
        "cluster_count_distribution": {str(k): v for k, v in sorted(sweep.counts.items())},
        "mean_silhouette_headline": headline.mean_silhouette,
        "mean_silhouette_range": sweep.silhouette_range,
        "floor_met": headline.floor_met,
        "dropped_trials": from_returns.dropped_trials,
        "variance_effective_n": var_eff,
        "clusters": cluster_families,
        "interpretation": headline.interpretation,
        "raw_pooled_trial_count": raw,
        "families_in_matrix": sorted({v for v in fam_of.values()}),
        "excluded_families": EXCLUDED_FAMILIES,
        "stage1_meta_families": meta["families"],
    }
    CLUSTER_JSON_PATH.write_text(json.dumps(payload, indent=2, default=str))
    CLUSTER_REPORT_PATH.write_text(_render_cluster_report(payload))

    # ---- the committed artifact production code reads ---------------------
    CONFIG_PATH.write_text(json.dumps({
        "schema": "global_effective_n/v1",
        "n_effective": sweep.mode,
        "computed_at": time.strftime("%Y-%m-%d"),
        "run_tag": RUN_TAG,
        "headline_seed": RANDOM_STATE,
        "seed_sweep_first": SEED_SWEEP[0],
        "seed_sweep_last": SEED_SWEEP[-1],
        "n_seeds": len(SEED_SWEEP),
        "n_effective_headline_seed": headline.n_effective,
        "n_effective_seed_range": [sweep.minimum, sweep.maximum],
        "cluster_count_distribution": {str(k): v for k, v in sorted(sweep.counts.items())},
        "mean_silhouette": headline.mean_silhouette,
        "n_specs_clustered": int(matrix.shape[1]),
        "n_families_clustered": len({v for v in fam_of.values()}),
        "raw_pooled_distinct_trials": raw["distinct_trials"],
        "raw_pooled_rows": raw["total_rows"],
        "raw_pooled_families": raw["n_families"],
        "estimator": (
            "ONC (Lopez de Prado & Lewis 2019, Quantitative Finance 19(9) 1555-1565, "
            "SSRN 3167017) via app/services/research_lab/effective_n_clustering.py"
        ),
        "provenance": "data/research_runs/run_global_effective_n.py --stage cluster",
        "report": "data/research_runs/global_effective_n_2026-09-04.txt",
    }, indent=2) + "\n")
    _log(f"wrote {CONFIG_PATH} with n_effective={sweep.mode} "
         f"(seed range {sweep.minimum}..{sweep.maximum})")


def _render_cluster_report(p: dict[str, Any]) -> str:
    L: list[str] = []
    a = L.append
    a("GLOBAL EFFECTIVE NUMBER OF TRIALS -- THE POOLED DSR DENOMINATOR -- 2026-09-04")
    a("=" * 78)
    a(f"run_tag={p['run_tag']}  generated={p['generated_at']}")
    a("Estimator: app/services/research_lab/effective_n_clustering.py (ONC; Lopez de Prado &")
    a("Lewis 2019, Quantitative Finance 19(9) 1555-1565, SSRN 3167017).")
    a("")
    a("HEADLINE")
    a("-" * 78)
    a(f"  GLOBAL EFFECTIVE N (mode across {p['n_seeds']} seeds) : {p['global_effective_n_mode']}")
    a(f"  range across seeds                        : "
      f"{p['global_effective_n_min']}..{p['global_effective_n_max']}")
    a(f"  headline seed {p['headline_seed']}                    : "
      f"{p['global_effective_n_headline']}")
    dist = ", ".join(f"K={k}x{v}" for k, v in p["cluster_count_distribution"].items())
    a(f"  full distribution                         : {dist}")
    sr = p["mean_silhouette_range"]
    a(f"  mean silhouette                           : {p['mean_silhouette_headline']:.4f}"
      + (f" (range {sr[0]:.4f}..{sr[1]:.4f})" if sr else ""))
    a(f"  clustered population                      : {p['matrix_shape'][1]} specs x "
      f"{p['matrix_shape'][0]} dates, {len(p['families_in_matrix'])} families")
    a(f"  variance-based N_eff (companion, not E[K]) : {p['variance_effective_n']:.3f}")
    a("")
    a("RAW POOLED TRIAL COUNT (the number E[K] deflates)")
    a("-" * 78)
    raw = p["raw_pooled_trial_count"]
    a(f"  rows in cross_sectional_trial_results     : {raw['total_rows']}")
    a(f"  DISTINCT (family_key, trial_id) trials    : {raw['distinct_trials']}")
    a(f"  families with at least one persisted trial: {raw['n_families']}")
    a("  (the row count exceeds the distinct-trial count because round_c and")
    a("   phase_a_intraday_expanded were each re-screened under several cost")
    a("   models; those are re-runs of one search, not new searches.)")
    a("")
    for fam, n in sorted(raw["per_family_distinct_trials"].items()):
        a(f"    {fam:42s} {n:5d}")
    a("")
    a("FAMILIES IN THE CLUSTERED MATRIX")
    a("-" * 78)
    for f in p["stage1_meta_families"]:
        if f["status"] != "ok":
            a(f"  {f['family_key']:36s} FAILED: {f['error']}")
            continue
        a(f"  {f['family_key']:36s} {f['n_results']:4d} results  "
          f"{f['n_series_captured']:4d} series  {f['n_rows_persisted']:4d} rows persisted  "
          f"local N={f['local_n_trials']:3d}  {f['elapsed_s']:.0f}s"
          + ("  [FIRST-EVER PERSISTENCE]" if not f["already_persisted_before_this_run"] else ""))
        if f.get("persist_error"):
            a(f"      PERSIST ERROR: {f['persist_error']}")
        if f.get("note"):
            a(f"      note: {f['note']}")
    a("")
    a("FAMILIES EXCLUDED FROM THE MATRIX (counted raw, absent from the clustering)")
    a("-" * 78)
    for key, why in p["excluded_families"].items():
        a(f"  {key}:")
        for line in _wrap(why, 72):
            a(f"      {line}")
    a("")
    a("CLUSTERS (headline seed)")
    a("-" * 78)
    for c in p["clusters"]:
        a(f"  cluster {c['cluster_id']:2d}  n={c['n_members']:3d}  q={c['quality_tstat']:8.3f}  "
          f"families: {', '.join(c['families'])}")
    a("")
    a("ONC's own interpretation string:")
    for line in _wrap(p["interpretation"], 74):
        a(f"  {line}")
    a("")
    a("HOW THIS NUMBER IS USED, and the one guard on it")
    a("-" * 78)
    for line in _wrap(
        "effective_n_clustering.py's own docstring states that E[K] is bounded to [2, N-1] by "
        "construction and that k-means UNDER-counts genuinely independent trials, which LOWERS "
        "the expected-max-Sharpe hurdle -- anti-conservative. That is why the module shipped "
        "unwired. The wiring in global_effective_n.dsr_n_trials therefore takes "
        "max(local grid size, global effective N), never the global number alone: the "
        "denominator can only ever GROW relative to the status quo, so no family's DSR can be "
        "made more lenient by this change, and the [2, N-1] under-counting bound can only cost "
        "conservatism this project did not already have.", 74):
        a(f"  {line}")
    return "\n".join(L) + "\n"


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------------------
# STAGE: dsr
# ---------------------------------------------------------------------------


def stage_dsr() -> None:
    """Recompute every family's best spec under the OLD local n_trials and the
    NEW pooled effective N, from the SAME stored return series and the same
    sigma_SR, so the only thing that moves between the two columns is N.

    Nothing here overwrites a historical figure. The old value is recomputed
    and printed alongside the new one, and the recomputation is checked
    against the value the family itself persisted -- a disagreement is
    REPORTED, not smoothed over."""
    from app.services.research_lab.deflated_sharpe import compute_deflated_sharpe
    from app.services.research_lab.global_effective_n import load_global_effective_n

    cfg = load_global_effective_n()
    with gzip.open(MATRIX_PATH, "rt") as fh:
        matrix = pd.read_csv(fh, index_col=0, parse_dates=True)
    meta = json.loads(META_PATH.read_text())
    specs = meta["specs"]

    by_family: dict[str, list[str]] = {}
    for key, m in specs.items():
        if key in matrix.columns:
            by_family.setdefault(m["family_key"], []).append(key)

    rows: list[dict[str, Any]] = []
    for family_key, keys in sorted(by_family.items()):
        # "best spec" = highest DSR under the OLD denominator, which is the
        # spec each family's own report and registration decision named.
        ranked = sorted(keys, key=lambda k: (specs[k]["local_dsr"] or -1.0), reverse=True)
        for key in ranked[:1]:
            m = specs[key]
            series = matrix[key].dropna()
            sigma = m.get("sigma_sr_annualized")
            local_n = int(m["local_n_trials"])
            new_n = cfg.dsr_n_trials(local_n)
            ppy = float(m["periods_per_year"])
            old = compute_deflated_sharpe(m["sharpe_annualized"], series, local_n, sigma,
                                          periods_per_year=ppy)
            new = compute_deflated_sharpe(m["sharpe_annualized"], series, new_n, sigma,
                                          periods_per_year=ppy)
            rows.append({
                "family_key": family_key,
                "spec_id": m["spec_id"],
                "sharpe_annualized": m["sharpe_annualized"],
                "n_observations": int(len(series)),
                "skewness": old.skewness,
                "kurtosis": old.kurtosis,
                "sigma_sr_annualized": sigma,
                "psr_vs_zero": old.psr_vs_zero,
                "old_n_trials": local_n,
                "old_dsr_recomputed": old.dsr,
                "old_dsr_as_persisted_by_family": m["local_dsr"],
                "old_recompute_delta": (
                    None if (old.dsr is None or m["local_dsr"] is None)
                    else float(old.dsr - m["local_dsr"])
                ),
                "new_n_trials": new_n,
                "new_dsr": new.dsr,
                "dsr_change": (
                    None if (old.dsr is None or new.dsr is None) else float(new.dsr - old.dsr)
                ),
                "old_sr0_annualized": old.expected_max_sharpe_noise_annualized,
                "new_sr0_annualized": new.expected_max_sharpe_noise_annualized,
            })

    payload = {
        "run_tag": RUN_TAG,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "global_effective_n": cfg.n_effective,
        "global_effective_n_seed_range": cfg.n_effective_seed_range,
        "global_effective_n_computed_at": cfg.computed_at,
        "wiring": "n_trials = max(local grid size, global effective N)",
        "rows": rows,
    }
    DSR_JSON_PATH.write_text(json.dumps(payload, indent=2, default=str))
    DSR_REPORT_PATH.write_text(_render_dsr_report(payload))
    _log(f"wrote {DSR_REPORT_PATH.name} ({len(rows)} families)")


def _render_dsr_report(p: dict[str, Any]) -> str:
    L: list[str] = []
    a = L.append
    a("DSR BEFORE / AFTER THE POOLED-N CORRECTION -- 2026-09-04")
    a("=" * 112)
    a(f"run_tag={p['run_tag']}  generated={p['generated_at']}")
    a(f"global effective N = {p['global_effective_n']} "
      f"(seed range {p['global_effective_n_seed_range']}, computed "
      f"{p['global_effective_n_computed_at']})")
    a(f"wiring: {p['wiring']}")
    a("")
    a("Each family's BEST spec by its own old-denominator DSR -- the spec its own report and,")
    a("where one exists, its registration decision named. Every column is recomputed from the")
    a("SAME stored return series and the SAME sigma_SR; only n_trials differs between them.")
    a("")
    a(f"{'family_key':36s} {'spec_id':34s} {'Sharpe':>8s} {'oldN':>5s} {'oldDSR':>8s} "
      f"{'newN':>5s} {'newDSR':>8s} {'delta':>8s}")
    a("-" * 112)
    for r in sorted(p["rows"], key=lambda r: -(r["old_dsr_recomputed"] or -1)):
        def fmt(v: float | None) -> str:
            return "  n/a" if v is None else f"{v:8.4f}"
        a(f"{r['family_key']:36s} {r['spec_id'][:34]:34s} {r['sharpe_annualized']:8.4f} "
          f"{r['old_n_trials']:5d} {fmt(r['old_dsr_recomputed'])} {r['new_n_trials']:5d} "
          f"{fmt(r['new_dsr'])} {fmt(r['dsr_change'])}")
    a("")
    a("RECOMPUTE CHECK -- this run's old-N DSR against the value the family itself persisted")
    a("-" * 112)
    a("A non-zero delta means the family's own run and this one disagree on the same spec's")
    a("DSR at the same N. Reported, never smoothed: the causes are real (a different price")
    a("vintage in the store, a different end date) and belong in the open-questions list.")
    a(f"{'family_key':36s} {'spec_id':34s} {'thisrun':>9s} {'persisted':>10s} {'delta':>9s}")
    for r in sorted(p["rows"], key=lambda r: -abs(r["old_recompute_delta"] or 0.0)):
        d = r["old_recompute_delta"]
        a(f"{r['family_key']:36s} {r['spec_id'][:34]:34s} "
          f"{(r['old_dsr_recomputed'] if r['old_dsr_recomputed'] is not None else float('nan')):9.4f} "
          f"{(r['old_dsr_as_persisted_by_family'] if r['old_dsr_as_persisted_by_family'] is not None else float('nan')):10.4f} "
          f"{(d if d is not None else float('nan')):9.4f}")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["rebuild", "cluster", "dsr"])
    ap.add_argument("--only", default=None, help="comma-separated family_keys (rebuild only)")
    args = ap.parse_args()
    if args.stage == "rebuild":
        stage_rebuild(args.only)
    elif args.stage == "cluster":
        stage_cluster()
    else:
        stage_dsr()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
