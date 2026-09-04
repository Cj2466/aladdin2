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
from dataclasses import dataclass
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

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND})."
    )

import numpy as np
import pandas as pd

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

    def wrapper(*args, **kwargs):
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


def _wrap_batch_replay(module: Any, name: str) -> None:
    """For an engine that replays the WHOLE spec list in one call and returns
    {spec_id: result} -- cross_sectional_eigenportfolio.run_eigen_replay is the
    only one. _wrap_replay cannot see it: it scans the arguments for an object
    carrying a spec id, and a LIST of specs carries none, so the first pass of
    this run captured 12 eigenportfolio results and 0 series. Found by reading
    the per-family series count in the run log against the result count, which
    is why that pair is reported per family rather than summed."""
    original = getattr(module, name, None)
    if original is None or not callable(original):
        return

    def wrapper(*args, **kwargs):
        results = original(*args, **kwargs)
        if isinstance(results, dict):
            for spec_id, result in results.items():
                if isinstance(spec_id, str) and getattr(result, "status", "ok") == "ok":
                    _record(spec_id, getattr(result, "daily_returns", None))
        return results

    setattr(module, name, wrapper)
    _PATCHED.append((module, name, original))


def _wrap_net_returns(module: Any) -> None:
    original = getattr(module, "net_daily_returns", None)
    if original is None or not callable(original):
        return

    def wrapper(*args, **kwargs):
        series = original(*args, **kwargs)
        replay = kwargs.get("replay") if "replay" in kwargs else (args[0] if args else None)
        spec_id = _REPLAY_OWNER.get(id(replay)) if replay is not None else None
        if spec_id is not None:
            _record(spec_id, series)
        return series

    module.net_daily_returns = wrapper
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
            mod.run_cross_sectional_backtest = hub_wrapper
            n_rebound += 1
    census["modules_rebound_to_hub_wrapper"] = n_rebound

    # (3) the bespoke engines, one hook each.
    bespoke = [
        ("cross_sectional_index_removal", "run_index_removal_backtest"),
        ("cross_sectional_insider", "run_insider_backtest"),
        ("cross_sectional_pead", "run_pead_backtest"),
        ("cross_sectional_correlation_risk_premium", "run_crp_backtest"),
        ("vol_regime_timing", "run_timing_backtest"),
        ("cross_sectional_dividend_month", "run_dmp_backtest"),
        ("cross_sectional_earnings_premium", "run_eap_backtest"),
    ]
    for mod_name, fn_name in bespoke:
        module = importlib.import_module(f"app.services.research_lab.{mod_name}")
        before = len(_PATCHED)
        _wrap_replay(module, fn_name)
        census[f"{mod_name}.{fn_name}"] = int(len(_PATCHED) > before)

    # the one batch engine (see _wrap_batch_replay)
    eigen = importlib.import_module("app.services.research_lab.cross_sectional_eigenportfolio")
    _wrap_batch_replay(eigen, "run_eigen_replay")
    census["cross_sectional_eigenportfolio.run_eigen_replay (batch)"] = 1

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


def _edgar():
    from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider

    return EdgarXbrlProvider()


def build_registry() -> list[Family]:
    from app.services.market_data.yfinance_provider import (
        YFinanceProvider,  # noqa: F401
    )
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
    from app.services.research_lab.cross_sectional_fx import (
        FX_N_TRIALS,
        screen_fx_family,
    )
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
    from app.services.research_lab.cross_sectional_jump_drift import (
        run_jump_drift_screening,
    )
    from app.services.research_lab.cross_sectional_lazy_prices import (
        LAZY_PRICES_N_TRIALS,
        run_lazy_prices_screening,
    )
    from app.services.research_lab.cross_sectional_patterns import run_round_c_screening
    from app.services.research_lab.cross_sectional_patterns_d2 import (
        D2_N_TRIALS,
        screen_d2_reversal_family,
    )
    from app.services.research_lab.cross_sectional_pead import (
        PEAD_N_TRIALS,
        run_pead_screening,
    )
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
    from app.services.research_lab.cross_sectional_seasonality import (
        run_seasonality_screening,
    )
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

    # A PARTIAL RE-RUN MERGES, IT DOES NOT REPLACE. Learned the hard way in
    # this run's own build: `--only eigenportfolio_statarb` (to pick up a
    # capture-hook fix for one family) rewrote the 469-column matrix with that
    # family's 12 columns, because the writer serialized whatever this
    # invocation happened to collect. The pooled matrix is the expensive
    # artifact -- ~55 minutes of screening -- and a one-family fix must not
    # destroy it. Any family present in THIS run replaces its own rows;
    # everything else is carried forward untouched, and the carried-forward
    # families are marked so the report cannot silently present a spliced
    # matrix as a single pass.
    series_by_spec: dict[str, pd.Series] = {}
    spec_meta: dict[str, dict[str, Any]] = {}
    family_status: list[dict[str, Any]] = []
    carried_forward: list[str] = []
    if only and MATRIX_PATH.exists() and META_PATH.exists():
        with gzip.open(MATRIX_PATH, "rt") as fh:
            previous = pd.read_csv(fh, index_col=0, parse_dates=True)
        prev_meta = json.loads(META_PATH.read_text())
        rerun_keys = {f.key for f in registry}
        for col, sm in prev_meta.get("specs", {}).items():
            if sm.get("family_key") in rerun_keys or col not in previous.columns:
                continue
            series_by_spec[col] = previous[col].dropna()
            spec_meta[col] = sm
        for fs in prev_meta.get("families", []):
            if fs.get("family_key") not in rerun_keys:
                family_status.append({**fs, "carried_forward_from_earlier_run": True})
                carried_forward.append(str(fs.get("family_key")))
        _log(f"merging into an existing matrix: carried forward {len(series_by_spec)} series "
             f"from {len(carried_forward)} family(ies) not in this --only run")
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
                "n_observations": len(series),
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
        "families_carried_forward_from_an_earlier_run": sorted(
            f["family_key"] for f in family_status
            if f.get("carried_forward_from_earlier_run")
        ),
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
    def kv(label: str, value: str) -> None:
        a(f"  {label:<44s}: {value}")

    kv(f"GLOBAL EFFECTIVE N (mode across {p['n_seeds']} seeds)",
       str(p["global_effective_n_mode"]))
    kv("range across seeds",
       f"{p['global_effective_n_min']}..{p['global_effective_n_max']}")
    kv(f"headline seed {p['headline_seed']}", str(p["global_effective_n_headline"]))
    kv("full distribution",
       ", ".join(f"K={k}x{v}" for k, v in p["cluster_count_distribution"].items()))
    sr = p["mean_silhouette_range"]
    kv("mean silhouette", f"{p['mean_silhouette_headline']:.4f}"
       + (f" (range {sr[0]:.4f}..{sr[1]:.4f})" if sr else ""))
    kv("clustered population",
       f"{p['matrix_shape'][1]} specs x {p['matrix_shape'][0]} dates, "
       f"{len(p['families_in_matrix'])} families")
    kv("variance-based N_eff (companion, not E[K])", f"{p['variance_effective_n']:.3f}")
    a("")
    a("RAW POOLED TRIAL COUNT (the number E[K] deflates)")
    a("-" * 78)
    raw = p["raw_pooled_trial_count"]
    kv("rows in cross_sectional_trial_results", str(raw["total_rows"]))
    kv("DISTINCT (family_key, trial_id) trials", str(raw["distinct_trials"]))
    kv("families with at least one persisted trial", str(raw["n_families"]))
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


def _derive_periods_per_year(sharpe_annualized: float, sharpe_daily: float) -> float:
    """compute_deflated_sharpe stores BOTH the annualized and the per-period
    Sharpe, and the only thing between them is sqrt(periods_per_year). So the
    row carries its own annualization factor and it does not have to be
    guessed -- which matters, because getting it wrong here would compound the
    exact unit-mixing error deflated_sharpe.py's docstring documents (crypto
    annualizes at 365, every equity family at 252, and nothing in the table
    records which)."""
    if not sharpe_daily:
        return 252.0
    return float((sharpe_annualized / sharpe_daily) ** 2)


def _canonical_rows() -> list[dict[str, Any]]:
    """One row per family: its best spec, from its MOST RECENT screening.

    Read straight out of cross_sectional_trial_results rather than recomputed
    from return series, for two reasons. It covers every family that ever
    persisted a trial -- including the six whose replay engines this run cannot
    hook, which a return-series approach would silently drop from the
    before/after table. And the persisted deflated_sharpe blob carries every
    input the DSR needs (daily Sharpe, n, skew, kurtosis, sigma_SR), so the old
    figure can be INDEPENDENTLY RE-DERIVED from the same row and checked
    against what the family stored -- a reproduction check the return-series
    route could not perform at all.

    "Best" is by the family's own persisted DSR, falling back to PSR-vs-zero
    where the DSR is None (a family whose own trial count sat below
    MIN_TRIALS_FOR_DSR never had one).
    """
    import sqlite3

    from app.db import engine

    db_path = engine.url.database
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # The most recent run_tag per family, by that tag's max computed_at.
    latest = conn.execute(
        "SELECT family_key, run_tag FROM ("
        "  SELECT family_key, run_tag, MAX(computed_at) AS t,"
        "         ROW_NUMBER() OVER (PARTITION BY family_key ORDER BY MAX(computed_at) DESC,"
        "                            run_tag DESC) AS rn"
        "  FROM cross_sectional_trial_results GROUP BY family_key, run_tag"
        ") WHERE rn = 1"
    ).fetchall()

    out: list[dict[str, Any]] = []
    for fam_row in latest:
        family_key, run_tag = fam_row["family_key"], fam_row["run_tag"]
        rows = conn.execute(
            "SELECT trial_id, sharpe_annualized, n_observations, n_trials, dsr, psr_vs_zero,"
            "       full_result_json, computed_at FROM cross_sectional_trial_results"
            " WHERE family_key = ? AND run_tag = ?",
            (family_key, run_tag),
        ).fetchall()
        if not rows:
            continue
        best = max(
            rows,
            key=lambda r: (
                r["dsr"] if r["dsr"] is not None else -1.0,
                r["psr_vs_zero"] if r["psr_vs_zero"] is not None else -1.0,
            ),
        )
        try:
            blob = json.loads(best["full_result_json"]).get("deflated_sharpe") or {}
        except (TypeError, ValueError):
            blob = {}
        out.append({
            "family_key": family_key,
            "run_tag": run_tag,
            "computed_at": best["computed_at"],
            "trial_id": best["trial_id"],
            "n_specs_in_run": len(rows),
            "sharpe_annualized": float(best["sharpe_annualized"]),
            "n_observations": int(best["n_observations"]),
            "old_n_trials": int(best["n_trials"]),
            "old_dsr_persisted": best["dsr"],
            "psr_vs_zero_persisted": best["psr_vs_zero"],
            "sharpe_net_daily": blob.get("sharpe_net_daily"),
            "skewness": blob.get("skewness"),
            "kurtosis": blob.get("kurtosis"),
            "sigma_sr_annualized": blob.get("sigma_sr_annualized"),
            "old_sr0_persisted": blob.get("expected_max_sharpe_noise_annualized"),
        })
    conn.close()
    return sorted(out, key=lambda r: r["family_key"])


# ---------------------------------------------------------------------------
# THE FOUR LIVE FORWARD REGISTRATIONS
# ---------------------------------------------------------------------------
#
# The family table above reports each family's BEST spec. For three of the
# four live registrations that is a DIFFERENT spec from the one actually
# registered -- quality_cbop's best is a noa spec, short_interest's best is a
# days-to-cover spec that registration deliberately declined -- so reading the
# live book off that table would report numbers for strategies nobody
# registered. These four rows are pinned by (family_key, pattern_id) taken
# from the registration modules themselves, so the report tracks the code that
# creates the registrations rather than a transcription of it.
#
# `documented_dsr` is the figure each registration's own rationale text states.
# It is carried here only so the report can show whether the persisted row
# still reproduces it; nothing computes from it.
LIVE_REGISTRATIONS = [
    {
        "label": "quality_cbop / cbop_ls_h63",
        "family_key": "quality_cbop",
        "trial_id": "cbop_ls_h63",
        "registration_module": "quality_forward_registration.py",
        "registration_family_key": "quality_cbop",
        "documented_dsr": 0.8173935191490574,
    },
    {
        "label": "short_interest_ratio / si_ratio_hedged_h21",
        "family_key": "short_interest",
        "trial_id": "si_ratio_hedged_h21",
        "registration_module": "short_interest_forward_registration.py",
        "registration_family_key": "short_interest_ratio",
        "documented_dsr": 0.7962107673459036,
    },
    {
        "label": "lazy_prices_jaccard_full / lazy_jaccard_full_h126_ivol",
        "family_key": "lazy_prices",
        "trial_id": "lazy_jaccard_full_h126_ivol",
        "registration_module": "lazy_prices_forward_registration.py",
        "registration_family_key": "lazy_prices_jaccard_full",
        "documented_dsr": 0.7539980897081575,
    },
    {
        "label": "crypto / xc_btcbeta_l180_h180",
        "family_key": "crypto",
        "trial_id": "xc_btcbeta_l180_h180",
        "registration_module": "bab_forward_registration.py",
        "registration_family_key": "crypto",
        "documented_dsr": 0.3552701584241104,
    },
]


def sensitivity_denominators(local: int) -> list[tuple[str, int]]:
    """The candidate denominators the sensitivity table walks, given a family's
    own grid size.

    EVERY VALUE IS READ FROM THE CLUSTER RUN'S OWN OUTPUT, never typed in here.
    An earlier draft of this function hardcoded the numbers from one run; they
    were silently wrong the moment the matrix grew from 232 specs to 481, which
    is precisely the staleness failure global_effective_n.py exists to prevent.
    Reading them back means a re-cluster updates this table for free, and a
    missing cluster artifact produces no sensitivity table at all rather than a
    plausible-looking stale one.

    The four candidates, and why each is defensible:
      * variance_effective_n over the same matrix -- a COMPANION diagnostic,
        NOT E[K]: effective_n_clustering.py's docstring is explicit that it
        answers a diversification question rather than ONC's partition question
        and "must not be substituted for E[K]". Shown because it is the other
        number the same matrix produced, and it is far from the ONC answer.
      * the TOP of the seed sweep -- what the same estimator would have handed
        back on its most conservative draw.
      * every spec in the clustered matrix -- no deflation for correlation at
        all, across the families whose returns could be captured.
      * every distinct persisted trial in the project -- the raw pooled count.
        The most conservative number available, and the one
        effective_n_clustering.py's own interpretation string calls "the only
        honest multiplicity number" for a population whose silhouette sits
        below the no-structure threshold, as this one's does."""
    out = [("family's own grid (status quo = corrected)", int(local))]
    if not CLUSTER_JSON_PATH.exists():
        return out
    c = json.loads(CLUSTER_JSON_PATH.read_text())
    for label, n in (
        ("variance N_eff over the pooled matrix", round(float(c["variance_effective_n"]))),
        (f"top of the {c['n_seeds']}-seed E[K] sweep", int(c["global_effective_n_max"])),
        ("every spec in the clustered matrix", int(c["matrix_shape"][1])),
        ("every distinct persisted trial", int(c["raw_pooled_trial_count"]["distinct_trials"])),
    ):
        if n > local and n not in {v for _, v in out}:
            out.append((label, n))
    return out


def _live_registration_rows() -> list[dict[str, Any]]:
    """Every persisted row for each registered spec, newest last.

    ALL of them, not just the newest, and deliberately so. Three of these four
    specs have been screened more than once, and the re-runs do not always
    reproduce the registration-time figure -- short_interest's does not, for
    the mid-split price-freeze reason commit fa614ac diagnosed. Collapsing to
    one row would silently pick a side in that discrepancy. Showing every row
    lets the pooled-N correction (which changes ONLY n_trials) be read
    separately from the reproducibility drift (which changes the Sharpe), so
    neither is mistaken for the other."""
    import sqlite3

    from app.db import engine

    conn = sqlite3.connect(str(engine.url.database))
    conn.row_factory = sqlite3.Row
    out: list[dict[str, Any]] = []
    for reg in LIVE_REGISTRATIONS:
        rows = conn.execute(
            "SELECT run_tag, computed_at, sharpe_annualized, n_observations, n_trials, dsr,"
            "       psr_vs_zero, full_result_json FROM cross_sectional_trial_results"
            " WHERE family_key = ? AND trial_id = ? ORDER BY computed_at",
            (reg["family_key"], reg["trial_id"]),
        ).fetchall()
        observations = []
        for row in rows:
            try:
                blob = json.loads(row["full_result_json"]).get("deflated_sharpe") or {}
            except (TypeError, ValueError):
                blob = {}
            observations.append({
                "run_tag": row["run_tag"],
                "computed_at": row["computed_at"],
                "sharpe_annualized": float(row["sharpe_annualized"]),
                "n_observations": int(row["n_observations"]),
                "old_n_trials": int(row["n_trials"]),
                "old_dsr_persisted": row["dsr"],
                "psr_vs_zero_persisted": row["psr_vs_zero"],
                "sharpe_net_daily": blob.get("sharpe_net_daily"),
                "skewness": blob.get("skewness"),
                "kurtosis": blob.get("kurtosis"),
                "sigma_sr_annualized": blob.get("sigma_sr_annualized"),
            })
        out.append({**reg, "observations": observations, "n_persisted_rows": len(rows)})
    conn.close()
    return out


def _dsr_at(
    n_trials: int,
    sr_daily: float | None,
    sigma_sr_annualized: float | None,
    skewness: float | None,
    kurtosis: float | None,
    n_observations: int,
    periods_per_year: float,
) -> tuple[float | None, float | None]:
    """DSR and the annualized SR0 at a given denominator, RE-DERIVED from a
    persisted row's own stored inputs via deflated_sharpe's two primitives --
    expected_max_sharpe_under_noise and probabilistic_sharpe_ratio -- rather
    than by re-running any backtest.

    Deliberately a module-level function rather than a closure over the loop
    that calls it: a closure would capture the loop variables by reference,
    which is correct only for as long as every call stays inside the iteration
    that created it, and is exactly the kind of quiet coupling that turns into
    a wrong number the first time someone collects these for later evaluation.

    Returns (None, None) below MIN_TRIALS_FOR_DSR, matching
    compute_deflated_sharpe's own contract: that is a real "not computable at
    this trial count", not a zero."""
    from app.services.research_lab.deflated_sharpe import (
        MIN_TRIALS_FOR_DSR,
        expected_max_sharpe_under_noise,
        probabilistic_sharpe_ratio,
    )

    if sigma_sr_annualized is None or sr_daily is None or skewness is None or kurtosis is None:
        return None, None
    if n_trials < MIN_TRIALS_FOR_DSR:
        return None, None
    root = float(np.sqrt(periods_per_year))
    sr0_daily = expected_max_sharpe_under_noise(sigma_sr_annualized / root, n_trials)
    if sr0_daily is None:
        return None, None
    return (
        probabilistic_sharpe_ratio(sr_daily, sr0_daily, n_observations, skewness, kurtosis),
        float(sr0_daily * root),
    )


def stage_dsr() -> None:
    """Every family's best spec under the OLD local denominator and the NEW
    pooled one, side by side.

    NOTHING IS OVERWRITTEN. The old figure is the one the family itself
    persisted, read back unchanged; the new figure is an additional column.
    The persisted rows keep their original n_trials and dsr exactly as they
    were written -- the same convention lazy_prices' price fix and dividend
    fix used, where the original number stayed visible beside the corrected
    one."""
    from app.services.research_lab.global_effective_n import load_global_effective_n

    cfg = load_global_effective_n()
    rows_out: list[dict[str, Any]] = []

    for r in _canonical_rows():
        sr_daily = r["sharpe_net_daily"]
        sigma = r["sigma_sr_annualized"]
        skew, kurt, n_obs = r["skewness"], r["kurtosis"], r["n_observations"]
        new_n = cfg.dsr_n_trials(r["old_n_trials"])
        ppy = _derive_periods_per_year(r["sharpe_annualized"], sr_daily) if sr_daily else 252.0

        old_dsr, old_sr0 = _dsr_at(r["old_n_trials"], sr_daily, sigma, skew, kurt, n_obs, ppy)
        new_dsr, new_sr0 = _dsr_at(new_n, sr_daily, sigma, skew, kurt, n_obs, ppy)
        persisted = r["old_dsr_persisted"]
        rows_out.append({
            **r,
            "periods_per_year_derived": ppy,
            "old_dsr_rederived": old_dsr,
            "old_rederivation_delta": (
                None if (old_dsr is None or persisted is None) else float(old_dsr - persisted)
            ),
            "old_sr0_rederived": old_sr0,
            "new_n_trials": new_n,
            "new_dsr": new_dsr,
            "new_sr0_annualized": new_sr0,
            "dsr_change": (
                None if (old_dsr is None or new_dsr is None) else float(new_dsr - old_dsr)
            ),
            "newly_computable": old_dsr is None and new_dsr is not None,
        })

    # The four live forward registrations, computed the SAME way from the same
    # primitives -- separately, because these are the specs actually carrying
    # the project's forward-validation book and three of the four are not
    # their own family's best spec.
    live_out: list[dict[str, Any]] = []
    for reg in _live_registration_rows():
        obs_out = []
        for o in reg["observations"]:
            sr_daily, sigma = o["sharpe_net_daily"], o["sigma_sr_annualized"]
            skew, kurt, n_obs = o["skewness"], o["kurtosis"], o["n_observations"]
            new_n = cfg.dsr_n_trials(o["old_n_trials"])
            ppy = _derive_periods_per_year(o["sharpe_annualized"], sr_daily) if sr_daily else 252.0
            old_dsr, old_sr0 = _dsr_at(o["old_n_trials"], sr_daily, sigma, skew, kurt, n_obs, ppy)
            new_dsr, new_sr0 = _dsr_at(new_n, sr_daily, sigma, skew, kurt, n_obs, ppy)
            persisted = o["old_dsr_persisted"]
            obs_out.append({
                **o,
                "periods_per_year_derived": ppy,
                "old_dsr_rederived": old_dsr,
                "old_rederivation_delta": (
                    None if (old_dsr is None or persisted is None) else float(old_dsr - persisted)
                ),
                "old_sr0_rederived": old_sr0,
                "new_n_trials": new_n,
                "new_dsr": new_dsr,
                "new_sr0_annualized": new_sr0,
                "dsr_change": (
                    None if (old_dsr is None or new_dsr is None) else float(new_dsr - old_dsr)
                ),
            })
        # DENOMINATOR SENSITIVITY. Computed for the registration-time
        # observation only (the row whose DSR each rationale text quotes).
        #
        # WHY THIS EXISTS. E[K] came back at the estimator's structural floor
        # of 2, so max(local, E[K]) is the identity for every family and the
        # whole correction moves nothing. A table of zeroes is a true result
        # but an uninterpretable one: it looks identical to a correction that
        # was never wired up. This shows what the SAME machinery produces at
        # other candidate denominators, so a reader can see the wiring is live
        # and see how much the choice of denominator is actually worth.
        #
        # NONE OF THESE IS THE CORRECTED NUMBER. The corrected number is the
        # newDSR column above. These are what-ifs, and which (if any) should
        # replace E[K] is a methodology decision for the repo owner.
        sens = []
        if obs_out:
            base = obs_out[0]
            sr_daily, sigma = base["sharpe_net_daily"], base["sigma_sr_annualized"]
            skew, kurt = base["skewness"], base["kurtosis"]
            n_obs, ppy = base["n_observations"], base["periods_per_year_derived"]
            for label, N in sensitivity_denominators(base["old_n_trials"]):
                d, _ = _dsr_at(N, sr_daily, sigma, skew, kurt, n_obs, ppy)
                sens.append({"label": label, "n_trials": N, "dsr": d})
        live_out.append({**reg, "observations": obs_out, "sensitivity": sens})

    payload = {
        "run_tag": RUN_TAG,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "global_effective_n": cfg.n_effective,
        "global_effective_n_seed_range": list(cfg.n_effective_seed_range),
        "global_effective_n_computed_at": cfg.computed_at,
        # Carried so the prose below can DESCRIBE the measurement instead of
        # restating it from memory. An earlier draft hardcoded "ranged 2..21,
        # 13 of 25 seeds" into the narrative; that was true of a partial
        # 232-spec matrix and became a false sentence in the report the moment
        # the full 481-spec matrix was clustered. Nothing here is retyped.
        "n_seeds": cfg.n_seeds,
        "cluster_count_distribution": cfg.cluster_count_distribution,
        "mean_silhouette": cfg.mean_silhouette,
        "n_specs_clustered": cfg.n_specs_clustered,
        "n_families_clustered": cfg.n_families_clustered,
        "raw_pooled_distinct_trials": cfg.raw_pooled_distinct_trials,
        "wiring": "n_trials = max(this family's own pre-declared grid size, global effective N)",
        "source": "cross_sectional_trial_results, latest run_tag per family_key, best spec by DSR",
        "live_registrations": live_out,
        "rows": rows_out,
    }
    DSR_JSON_PATH.write_text(json.dumps(payload, indent=2, default=str))
    DSR_REPORT_PATH.write_text(_render_dsr_report(payload))
    _log(f"wrote {DSR_REPORT_PATH.name} ({len(rows_out)} families)")


def _render_dsr_report(p: dict[str, Any]) -> str:
    L: list[str] = []
    a = L.append
    a("DSR BEFORE / AFTER THE POOLED-N CORRECTION -- 2026-09-04")
    a("=" * 118)
    a(f"run_tag={p['run_tag']}  generated={p['generated_at']}")
    a(f"global effective N = {p['global_effective_n']} "
      f"(seed range {p['global_effective_n_seed_range'][0]}.."
      f"{p['global_effective_n_seed_range'][1]}, measured {p['global_effective_n_computed_at']})")
    a(f"wiring : {p['wiring']}")
    a(f"source : {p['source']}")
    a("")
    a("NOTHING BELOW OVERWRITES A HISTORICAL FIGURE. 'oldDSR' is the number the family itself")
    a("persisted; 'newDSR' is an additional column derived from the SAME stored inputs (daily")
    a("Sharpe, n, skew, kurtosis, sigma_SR) with only n_trials changed. The persisted rows keep")
    a("their original n_trials and dsr exactly as written.")
    a("")
    def fmt(v: float | None) -> str:
        return "     n/a" if v is None else f"{v:8.4f}"

    # ---- the live book, first, because it is the operative result ----------
    a("*" * 118)
    a("THE FOUR LIVE FORWARD REGISTRATIONS UNDER THE CORRECTED DENOMINATOR")
    a("*" * 118)
    a("These are the specs actually registered for forward validation, pinned by (family_key,")
    a("pattern_id) from the registration modules. THREE OF THE FOUR ARE NOT THEIR OWN FAMILY'S")
    a("BEST SPEC, so their numbers are NOT the ones in the family table below and must not be")
    a("read off it. Every persisted screening of each spec is shown, oldest first.")
    a("")
    a("NO REGISTRATION'S STATUS IS CHANGED BY THIS RUN. This report computes a denominator and")
    a("a probability; whether either should move a live registration is a decision for the repo")
    a("owner, made on these numbers, and is deliberately not a side effect of running this file.")
    a("")
    if p["global_effective_n"] <= 2:
        a("READ THE ZEROES IN THE 'delta' COLUMN CORRECTLY -- THEY ARE A MEASUREMENT, NOT A BUG.")
        a(f"ONC returned E[K] = {p['global_effective_n']}, the estimator's own structural floor")
        a("(effective_n_clustering.py searches k = 2..N-1, so 2 is the smallest value it can ever")
        a("return). Every family's own grid is larger than 2, so max(local grid, E[K]) is the")
        a("identity for all of them and the correction moves no number anywhere. The wiring is")
        a("live and exercised -- tests/test_global_effective_n.py pins that it is a max(), and the")
        a("sensitivity lines under each registration below show the same code path producing")
        a("different DSRs at different denominators -- it is the measured E[K] that is inert.")
        a("")
        lo, hi = p["global_effective_n_seed_range"]
        dist = p.get("cluster_count_distribution") or {}
        at_floor = int(dist.get(str(p["global_effective_n"]), 0))
        a("WHY E[K] CAME BACK AT THE FLOOR, in the estimator's own words: mean silhouette was")
        a(f"{p['mean_silhouette']:.3f}, at or below the 0.25 that Kaufman & Rousseeuw call \"no")
        a("substantial structure found\". ONC found no trustworthy cluster structure in the pooled")
        a(f"matrix ({p['n_specs_clustered']} specs across {p['n_families_clustered']} families) and "
          "fell back to carving it into two")
        a(f"blobs. The {p['n_seeds']}-seed sweep ranged {lo}..{hi}, with {at_floor} of "
          f"{p['n_seeds']} seeds landing on {p['global_effective_n']}"
          + (" -- i.e. every seed agreed, so this is a" if lo == hi else " -- so this is an"))
        a("CONVERGED result and not an unlucky draw." if lo == hi else
          "dispersed result that should be read as the range, not the mode.")
        a("The estimator's own interpretation string for this run declines to read a bet count")
        a(f"from it at all, and says the raw pooled count of {p['raw_pooled_distinct_trials']} "
          "distinct trials is the only honest")
        a("multiplicity number for a population with this little structure.")
        a("")
        a("SO THE HONEST BOTTOM LINE IS NOT 'the DSRs were already correct'. It is: this")
        a("methodology did not succeed in measuring the pooled denominator, and the pre-existing")
        a("per-family DSRs therefore still stand UNCORRECTED and still too generous by an amount")
        a("this run did not manage to quantify. The sensitivity lines under each registration")
        a("show the size of what is at stake if a defensible denominator is adopted instead.")
        a("")
    for reg in p.get("live_registrations", []):
        a(f"{reg['label']}   [{reg['registration_module']}]")
        if not reg["observations"]:
            a("    NO PERSISTED TRIAL ROW FOUND for this spec -- DSR cannot be recomputed.")
            a("")
            continue
        a(f"    documented in the registration rationale: DSR {reg['documented_dsr']:.4f}")
        a(f"    {'run_tag':46s} {'Sharpe':>8s} {'oldN':>5s} {'oldDSR':>8s} "
          f"{'newN':>5s} {'newDSR':>8s} {'delta':>8s}")
        for o in reg["observations"]:
            a(f"    {o['run_tag'][:46]:46s} {o['sharpe_annualized']:8.4f} "
              f"{o['old_n_trials']:5d} {fmt(o['old_dsr_rederived'])} {o['new_n_trials']:5d} "
              f"{fmt(o['new_dsr'])} {fmt(o['dsr_change'])}")
        newest = reg["observations"][-1]
        drift = (
            None if (newest["old_dsr_persisted"] is None)
            else float(newest["old_dsr_persisted"] - reg["documented_dsr"])
        )
        if drift is not None and abs(drift) > 1e-6:
            a(f"    NOTE: the newest screening's persisted DSR ({newest['old_dsr_persisted']:.4f}) "
              f"differs from the documented {reg['documented_dsr']:.4f} by {drift:+.4f}.")
            a("          That is REPRODUCIBILITY DRIFT (the Sharpe itself moved between runs), a")
            a("          separate matter from this run's correction, which changes only n_trials.")
        if reg.get("sensitivity"):
            a("    denominator sensitivity (NOT the corrected number -- see the header below):")
            for s in reg["sensitivity"]:
                a(f"      N={s['n_trials']:<5d} DSR {fmt(s['dsr'])}   {s['label']}")
        a("")
    a("*" * 118)
    a("")
    a("EVERY FAMILY'S BEST SPEC (the registered spec is a different row for three of the four above)")
    a("-" * 118)
    a(f"{'family_key':36s} {'best spec':32s} {'Sharpe':>8s} {'oldN':>5s} {'oldDSR':>8s} "
      f"{'newN':>5s} {'newDSR':>8s} {'delta':>8s}")
    a("-" * 118)

    for r in sorted(p["rows"], key=lambda r: -(r["old_dsr_rederived"] or -1)):
        flag = "  <- DSR computable for the first time" if r["newly_computable"] else ""
        a(f"{r['family_key']:36s} {r['trial_id'][:32]:32s} {r['sharpe_annualized']:8.4f} "
          f"{r['old_n_trials']:5d} {fmt(r['old_dsr_rederived'])} {r['new_n_trials']:5d} "
          f"{fmt(r['new_dsr'])} {fmt(r['dsr_change'])}{flag}")
    a("")
    a("REPRODUCTION CHECK -- this run's re-derived old DSR against what the family persisted")
    a("-" * 118)
    a("Re-derived from the row's own stored inputs via deflated_sharpe's expected_max_sharpe_")
    a("under_noise + probabilistic_sharpe_ratio, with periods_per_year recovered from the row")
    a("itself (sharpe_annualized / sharpe_net_daily)^2. A non-zero delta means the stored DSR")
    a("cannot be reproduced from the stored inputs and is reported, not smoothed.")
    a("")
    a(f"{'family_key':36s} {'rederived':>11s} {'persisted':>11s} {'delta':>13s}")
    worst = 0.0
    for r in sorted(p["rows"], key=lambda r: -abs(r["old_rederivation_delta"] or 0.0)):
        d = r["old_rederivation_delta"]
        if d is not None:
            worst = max(worst, abs(d))
        a(f"{r['family_key']:36s} "
          f"{(r['old_dsr_rederived'] if r['old_dsr_rederived'] is not None else float('nan')):11.6f} "
          f"{(r['old_dsr_persisted'] if r['old_dsr_persisted'] is not None else float('nan')):11.6f} "
          f"{(d if d is not None else float('nan')):13.2e}")
    a("")
    a(f"  worst absolute reproduction delta: {worst:.3e}")
    a("")
    a("PROVENANCE OF EACH ROW")
    a("-" * 118)
    a(f"{'family_key':36s} {'run_tag':52s} {'specs':>6s} {'ppy':>6s} {'n_obs':>7s}")
    for r in sorted(p["rows"], key=lambda r: r["family_key"]):
        a(f"{r['family_key']:36s} {r['run_tag'][:52]:52s} {r['n_specs_in_run']:6d} "
          f"{r['periods_per_year_derived']:6.0f} {r['n_observations']:7d}")
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
