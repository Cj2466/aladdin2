"""MEASURED EFFECTIVE NUMBER OF INDEPENDENT BETS across this project's real
strategy set -- ONC (Lopez de Prado & Lewis 2019) applied to the actual
registered specs and the actual candidate pool, replacing eyeballed
correlation guesses.

WHY THIS RUN EXISTS. project_1_action_list_2026-09-03 item 3 says: "Before
counting any new candidate as genuinely independent, run it (and the existing
registered set) through effective_n_clustering.py ... to get an actual
measured effective-N rather than eyeballing correlation." The module has
shipped UNWIRED since it was built -- nothing in this codebase imports it
outside its own test file (verified by grep at the start of this run). This
script is the first application of it to real production strategies.

==============================================================================
STAGE 1 -- WHERE THE RETURN SERIES COME FROM
==============================================================================
CHECKED, NOT ASSUMED: cross_sectional_trial_results persists only SUMMARY
statistics (sharpe_annualized, dsr, psr_vs_zero, n_observations) plus a
family-specific full_result_json. A direct scan of every row's
full_result_json found exactly ONE family that persists real return series --
multi_signal_combination, whose rows carry `candidate_daily_returns` (six
specs incl. cbop_ls_h63 and noa_neutral_ls_h126_median) and a
`correlation_matrix`. Those series are on a TRUNCATED common window
(2020-10-05..2026-08-25, 1479 days, cut down to the shortest candidate's
history) and so are used here only as an INDEPENDENT CROSS-CHECK on the
cbop/noa pair, never as the primary input. Everything else has to be
reconstructed.

The reconstruction reuses run_preservation_score.py's proven hook rather than
reimplementing anything: every equity family and the crypto family route
through cross_sectional.run_cross_sectional_backtest, which computes
`daily_returns` and whose caller then discards it. This script wraps that one
function on the module object, records the series it already produced, and
returns the result object untouched. No family's replay, cost model, universe
or spec grid is altered or duplicated.

==============================================================================
THE PRICE-REPRODUCIBILITY PROBLEM AND WHAT THIS SCRIPT DOES ABOUT IT
==============================================================================
Commit 24f0974 proved that YFinanceProvider's uncached auto_adjust=True fetch
is NOT point-in-time: Yahoo retroactively re-adjusts its entire historical
Close series, so the same nominal window fetched on two different days gives
different prices (measured: 2.9% of cells moved >1bp over 5.5h; the
registered lazy_prices spec's Sharpe moved 0.0205). lazy_prices was fixed
with a frozen snapshot. cbop, noa_neutral, residual_momentum, asset_growth
and short_interest ALL still share the vulnerable `get_price_history` path
and are NOT fixed.

That bug is fatal to a CORRELATION study in a way it is not to a single
family's Sharpe: if family A's prices are fetched at 02:00 and family B's at
03:00 and Yahoo re-adjusts in between, the two return series are built on
mutually inconsistent price data and their measured correlation is
contaminated by the inconsistency.

TWO MITIGATIONS, both applied:

 (1) lazy_prices runs off its OWN committed frozen snapshot
     (DEFAULT_PRICE_SNAPSHOT_DIR + DEFAULT_FILING_INDEX_PATH, commit
     24f0974), i.e. the exact byte-identical inputs that reproduced all 36
     specs at delta 0.0.

 (2) Every OTHER family's price fetch goes through a memoizing wrapper
     installed on YFinanceProvider.get_price_history / get_daily_ohlcv here
     in this SCRIPT (not in production code). The first call for a given
     (tickers, start, end) fetches live and freezes the answer to disk; every
     later call in this run and in any rerun replays the frozen answer. The
     effect is that all families in a single run share one consistent price
     vintage, and the whole analysis is exactly rerunnable.

WHAT MITIGATION (2) DOES NOT FIX, stated plainly: the frozen vintage is
whatever Yahoo served at the moment of THIS analysis. It is not the vintage
any family's originally-reported Sharpe was computed on. Rebuilt Sharpes are
therefore compared spec-by-spec against the persisted ones and the agreement
is REPORTED, never assumed.

==============================================================================
STAGE 2 -- WHAT IS ACTUALLY MEASURED
==============================================================================
Three populations, because they answer three different questions and only one
of them is well-posed for ONC:

 POP-A "registered": the live forward-validation registrations. N=5. This is
   the question the action list actually asks (is the eventual portfolio a
   set of diversified bets?) and it is BELOW effective_n_clustering's own
   MIN_TRIALS_FOR_CLUSTERING floor of 10. ONC is still run -- the module
   reports floor_met=False rather than refusing -- but the honest primary
   evidence at this N is the raw pairwise correlation matrix, which is
   reported in full.

 POP-B "admissible pool": every spec whose persisted DSR clears the 0.50
   floor this project has used for registration decisions, across the
   reproducible families. This is the multiplicity question ONC was built
   for, at an N inside the paper's own validated envelope.

 POP-C "one spec per family": the registered spec where a family has one,
   else that family's top-DSR spec. This is the signal-TYPE diversity
   question -- how many genuinely distinct return-generating processes does
   this project have at all -- and it is the population most relevant to
   "should candidate #8+ be a new signal type or another variant".

FAMILIES DELIBERATELY EXCLUDED and why (so the sample is honest):
  * best_ideas_13f -- its own report (best_ideas_13f_2026-09-02.txt line 5)
    records 207.4 minutes of wall clock for one build. Excluded on cost, the
    same reason run_preservation_score.py excluded it; its paper-faithful
    spec's DSR 0.6275 would otherwise qualify for POP-B.
  * residual_momentum_dm_overlay -- DSR 0.387/0.283, below the 0.50 floor, so
    outside POP-B by rule; and its overlay produces a MONTHLY series, which
    cannot be correlated against daily series without a resampling choice
    that would be this script's invention rather than the family's.
  * eigenportfolio_statarb, dividend_month_premium, insider_opportunistic,
    pead_ear, phase_a_intraday -- bespoke replay engines that do not call
    run_cross_sectional_backtest, so the capture hook cannot see them. Same
    limitation run_preservation_score.py documented and measured.

Run from backend/ with ./venv/bin/python data/research_runs/run_effective_n_clustering.py
Stage 1 is skipped automatically if the return matrix is already on disk.
"""

from __future__ import annotations

import gzip
import hashlib
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

# WORKTREE BINDING GUARD -- load-bearing, not boilerplate (copied verbatim in
# intent from run_preservation_score.py). Running this file by path puts
# data/research_runs/ on sys.path[0], NOT backend/, and this worktree's venv
# is a SYMLINK to the main worktree's venv, whose site-packages would resolve
# `app` to the MAIN worktree's backend/app.
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

from app.services.research_lab import cross_sectional as xs  # noqa: E402
from app.services.research_lab.effective_n_clustering import (  # noqa: E402
    MIN_TRIALS_FOR_CLUSTERING,
    EffectiveNResult,
    estimate_effective_n_from_correlation,
    estimate_effective_n_from_returns,
    variance_effective_n,
)
from app.services.research_lab.metrics import (  # noqa: E402
    CALENDAR_DAYS_PER_YEAR,
    TRADING_DAYS_PER_YEAR,
    sharpe_ratio,
)

RUN_TAG = "effective_n_clustering_2026-09-04"
MATRIX_PATH = _BACKEND / "data" / "research_runs" / "effective_n_return_matrix_2026-09-04.csv.gz"
META_PATH = _BACKEND / "data" / "research_runs" / "effective_n_return_matrix_2026-09-04.meta.json"
REPORT_PATH = _BACKEND / "data" / "research_runs" / "effective_n_clustering_2026-09-04.txt"
JSON_PATH = _BACKEND / "data" / "research_runs" / "effective_n_clustering_2026-09-04.json"

# Gitignored vendor caches and the sqlite DB live in the MAIN checkout, not in
# a worktree. Pointed at explicitly, exactly as run_preservation_score.py does,
# so a worktree run reads the same real EDGAR JSON and the same persisted rows.
_MAIN_BACKEND = Path("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
SHARED_EDGAR_CACHE = _MAIN_BACKEND / "data" / "edgar_companyfacts"
DB_PATH = _MAIN_BACKEND / "aladdin2.db"

# The frozen price vintage for THIS analysis. Deliberately outside the repo:
# it is a refetchable vendor input, not a result, and the committed artifact of
# this run is the RETURN MATRIX (small, and the actual input to the
# clustering), not tens of MB of raw closes.
PRICE_FREEZE_DIR = Path(
    "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/"
    "142109e4-1c17-421d-b8eb-cdbe7ecaf779/scratchpad/effective_n_price_freeze"
)

# The DSR floor this project has actually used in registration decisions
# (project_1_action_list_2026-09-03: asset_growth declined because "every h252
# spec in this family fails the 0.5 floor"; noa_neutral's paper-faithful cells
# "all below floor" at max DSR 0.319). POP-B is defined by it.
DSR_FLOOR = 0.50

# Seed for every KMeans restart, so the reported cluster counts are exactly
# reproducible. The module's random_state parameter is its own addition for
# this purpose; the paper leaves sklearn unseeded.
RANDOM_STATE = 20260904

# ONC is a stochastic search. A single seed's answer is one draw. Every
# population is therefore re-estimated across this many seeds and the full
# distribution of cluster counts is reported, not just the headline seed --
# without this, a reported E[K] would be presenting more precision than a
# k-means restart actually delivers.
SEED_SWEEP = list(range(20260904, 20260904 + 25))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("effective_n_runner")


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# The price freeze (mitigation 2 in the module docstring)
# ---------------------------------------------------------------------------


def _freeze_key(prefix: str, tickers: list[str], start: date, end: date) -> str:
    payload = json.dumps(
        {"tickers": sorted(str(t) for t in tickers), "start": str(start), "end": str(end)},
        sort_keys=True,
    )
    return f"{prefix}_{hashlib.sha256(payload.encode()).hexdigest()[:24]}"


def _install_price_freeze() -> dict[str, int]:
    """Memoize YFinanceProvider's two price entry points to disk.

    NOT a production change: this monkey-patches the class inside this script
    only, the same shape as the run_cross_sectional_backtest capture hook
    below. The first call for a given argument tuple fetches live exactly as
    the family itself would; every later call replays the frozen answer, so a
    rerun of this analysis is exactly reproducible and every family in one run
    shares a single price vintage."""
    from app.services.market_data.yfinance_provider import YFinanceProvider

    PRICE_FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    stats = {"hits": 0, "misses": 0}

    original_history = YFinanceProvider.get_price_history
    original_ohlcv = YFinanceProvider.get_daily_ohlcv

    def _read_frame(path: Path) -> pd.DataFrame:
        with gzip.open(path, "rt") as fh:
            return pd.read_csv(fh, index_col=0, parse_dates=True)

    def _write_frame(frame: pd.DataFrame, path: Path) -> None:
        with gzip.open(path, "wt") as fh:
            frame.to_csv(fh)

    def frozen_history(self, tickers, start, end):  # noqa: ANN001, ANN202
        key = _freeze_key("hist", list(tickers), start, end)
        close_path = PRICE_FREEZE_DIR / f"{key}.close.csv.gz"
        meta_path = PRICE_FREEZE_DIR / f"{key}.meta.json"
        if close_path.exists() and meta_path.exists():
            stats["hits"] += 1
            return _read_frame(close_path), json.loads(meta_path.read_text())["missing"]
        stats["misses"] += 1
        _log(f"  price freeze MISS -> live fetch: {len(tickers)} tickers {start}..{end}")
        close, missing = original_history(self, tickers, start, end)
        _write_frame(close, close_path)
        meta_path.write_text(
            json.dumps(
                {
                    "missing": list(missing),
                    "n_tickers_requested": len(tickers),
                    "start": str(start),
                    "end": str(end),
                    "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
        )
        return close, missing

    def frozen_ohlcv(self, tickers, start, end):  # noqa: ANN001, ANN202
        key = _freeze_key("ohlcv", list(tickers), start, end)
        meta_path = PRICE_FREEZE_DIR / f"{key}.meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            stats["hits"] += 1
            frames = {
                field: _read_frame(PRICE_FREEZE_DIR / f"{key}.{field}.csv.gz")
                for field in meta["fields"]
            }
            return frames, meta["missing"]
        stats["misses"] += 1
        _log(f"  ohlcv freeze MISS -> live fetch: {len(tickers)} tickers {start}..{end}")
        frames, missing = original_ohlcv(self, tickers, start, end)
        for field, frame in frames.items():
            _write_frame(frame, PRICE_FREEZE_DIR / f"{key}.{field}.csv.gz")
        meta_path.write_text(
            json.dumps(
                {
                    "fields": sorted(frames),
                    "missing": list(missing),
                    "start": str(start),
                    "end": str(end),
                    "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
        )
        return frames, missing

    YFinanceProvider.get_price_history = frozen_history
    YFinanceProvider.get_daily_ohlcv = frozen_ohlcv
    return stats


# ---------------------------------------------------------------------------
# The capture hook (run_preservation_score.py's, unchanged in intent)
# ---------------------------------------------------------------------------

CAPTURED: dict[str, dict[str, Any]] = {}
_ORIGINAL_BACKTEST = xs.run_cross_sectional_backtest


def _capturing_backtest(data, spec, config, membership_fn=None):  # noqa: ANN001, ANN202
    result = _ORIGINAL_BACKTEST(data, spec, config, membership_fn)
    if result.status == "ok" and len(result.daily_returns) > 0:
        CAPTURED[spec.pattern_id] = {
            "returns": result.daily_returns,
            "holding_days": spec.holding_days,
            "family": spec.family,
        }
    return result


xs.run_cross_sectional_backtest = _capturing_backtest


# ---------------------------------------------------------------------------
# Families
# ---------------------------------------------------------------------------


@dataclass
class FamilyRun:
    label: str
    persisted_run_tag: str | None
    invoke: Callable[[], list]
    periods_per_year: float = TRADING_DAYS_PER_YEAR
    note: str = ""


def _edgar():  # noqa: ANN202
    from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider

    return EdgarXbrlProvider(cache_dir=SHARED_EDGAR_CACHE)


def _quality_results(summary) -> list:  # noqa: ANN001
    return list(summary.cbop_results) + list(summary.noa_results)


def _lazy_prices_frozen() -> list:
    """lazy_prices off its OWN committed frozen snapshots -- the byte-identical
    inputs commit 24f0974 verified reproduce all 36 specs at delta exactly 0.0.
    Neither the price fetch nor the EDGAR listing is live here."""
    from app.services.market_data.edgar_filing_text_provider import load_filing_index
    from app.services.market_data.yfinance_provider import load_ohlcv_snapshot
    from app.services.research_lab.cross_sectional_lazy_prices import (
        DEFAULT_FILING_INDEX_PATH,
        DEFAULT_PRICE_SNAPSHOT_DIR,
        MEMBERSHIP_DATA_START,
        run_lazy_prices_screening,
    )

    # Both artifacts are committed in the MAIN checkout AND in this worktree
    # (they are tracked files), so the worktree's own copies are used.
    prices = load_ohlcv_snapshot(DEFAULT_PRICE_SNAPSHOT_DIR)
    loaded_index = load_filing_index(DEFAULT_FILING_INDEX_PATH)
    if prices is None or loaded_index is None:
        raise RuntimeError(
            "lazy_prices frozen snapshot/filing index missing -- refusing to fall back to a live "
            "fetch, which would silently reintroduce the very reproducibility bug 24f0974 fixed."
        )
    filing_index, filing_report = loaded_index
    return run_lazy_prices_screening(
        MEMBERSHIP_DATA_START,
        date(2026, 8, 31),
        tickers=list(prices["close"].columns),
        filing_index=filing_index,
        filing_report=filing_report,
        price_frames=prices,
    ).results


def _build_family_runs() -> list[FamilyRun]:
    from app.services.research_lab.cross_sectional_asset_growth import run_asset_growth_screening
    from app.services.research_lab.cross_sectional_crypto import run_crypto_screening
    from app.services.research_lab.cross_sectional_illiq import run_illiq_screening
    from app.services.research_lab.cross_sectional_jump_drift import run_jump_drift_screening
    from app.services.research_lab.cross_sectional_patterns import run_round_c_screening
    from app.services.research_lab.cross_sectional_quality import run_quality_screening
    from app.services.research_lab.cross_sectional_quality_neutral import (
        run_noa_neutral_screening,
    )
    from app.services.research_lab.cross_sectional_residual_momentum import (
        run_residual_momentum_screening,
    )
    from app.services.research_lab.cross_sectional_seasonality import run_seasonality_screening
    from app.services.research_lab.cross_sectional_short_interest import (
        SHORT_INTEREST_FORMATION_START,
        run_short_interest_screening,
    )
    from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

    # Every invocation below is byte-for-byte the same call run_preservation_
    # score.py made, so the rebuilt Sharpes are comparable against the SAME
    # canonical persisted run_tags -- the reproduction check stays meaningful.
    return [
        FamilyRun(
            "quality_cbop + quality_noa",
            "quality_build_2026-08-28",
            lambda: _quality_results(run_quality_screening(end=date(2026, 8, 28), edgar=_edgar())),
        ),
        FamilyRun(
            "quality_noa_industry_neutral",
            "noa_neutral_build_2026-08-28",
            lambda: run_noa_neutral_screening(end=date(2026, 8, 28), edgar=_edgar()).results,
        ),
        FamilyRun(
            "residual_momentum",
            "residual_momentum_build_2026-09-02",
            lambda: run_residual_momentum_screening(end=date(2026, 9, 2), edgar=_edgar()).results,
        ),
        FamilyRun(
            "asset_growth",
            "asset_growth_build_2026-09-01",
            lambda: run_asset_growth_screening(end=date(2026, 9, 1), edgar=_edgar()).results,
        ),
        FamilyRun(
            "short_interest",
            "short_interest_build_2026-09-02",
            lambda: run_short_interest_screening(
                start=SHORT_INTEREST_FORMATION_START, end=date(2026, 9, 2), edgar=_edgar()
            ).results,
        ),
        FamilyRun(
            "lazy_prices",
            "lazy_prices_ptit_fix_verification_A_2026-09-04",
            _lazy_prices_frozen,
            note=(
                "runs off the family's OWN committed frozen price snapshot + filing index "
                "(24f0974); checked against the frozen-snapshot verification run_tag, which is "
                "the only persisted vintage this input can reproduce exactly"
            ),
        ),
        FamilyRun(
            "crypto",
            None,
            lambda: run_crypto_screening(end=date(2026, 8, 31)).results,
            periods_per_year=float(CALENDAR_DAYS_PER_YEAR),
            note=(
                "NO persisted local row to check against: the crypto BAB registration predates "
                "the local DB wipe and cross_sectional_trial_results holds no crypto family rows "
                "(verified by direct query). Its rebuilt Sharpe is reported unchecked, and said so."
            ),
        ),
        FamilyRun(
            "jump_drift",
            "jump_drift_2026-08-30",
            lambda: run_jump_drift_screening(
                MEMBERSHIP_DATA_START, date(2026, 8, 30), run_event_study=False
            ).results,
        ),
        FamilyRun(
            "round_c",
            "edge_cost_reaudit_corrected_2026-08-30_flat_control",
            lambda: run_round_c_screening(MEMBERSHIP_DATA_START, date(2026, 8, 30))[0],
            note="checked against the re-audit's FLAT 5bp control arm, per run_preservation_score",
        ),
        FamilyRun(
            "liquidity_shock_delta_illiq",
            "illiq_build_2026-08-28",
            lambda: run_illiq_screening(MEMBERSHIP_DATA_START, date(2026, 8, 28))[0],
        ),
        FamilyRun(
            "same_calendar_month_seasonality",
            "seasonality_build_2026-08-28",
            lambda: run_seasonality_screening(MEMBERSHIP_DATA_START, date(2026, 8, 28))[0],
        ),
    ]


# ---------------------------------------------------------------------------
# Persisted rows
# ---------------------------------------------------------------------------


def load_persisted() -> dict[tuple[str, str], dict[str, Any]]:
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT family_key, trial_id, run_tag, sharpe_annualized, dsr, n_observations "
        "FROM cross_sectional_trial_results"
    ).fetchall()
    conn.close()
    return {
        (tag, tid): {
            "family_key": fam,
            "persisted_sharpe": sharpe,
            "persisted_dsr": dsr,
            "persisted_n_observations": nobs,
        }
        for fam, tid, tag, sharpe, dsr, nobs in rows
    }


# ---------------------------------------------------------------------------
# STAGE 1
# ---------------------------------------------------------------------------


def stage1_rebuild() -> None:
    persisted = load_persisted()
    freeze_stats = _install_price_freeze()

    series_by_spec: dict[str, pd.Series] = {}
    spec_meta: dict[str, dict[str, Any]] = {}
    family_status: list[dict[str, Any]] = []
    started = time.time()

    for fr in _build_family_runs():
        CAPTURED.clear()
        t0 = time.time()
        _log(f"running {fr.label} ...")
        try:
            results = fr.invoke()
        except Exception as exc:  # noqa: BLE001 -- a failure is REPORTED, never hidden
            traceback.print_exc()
            family_status.append(
                {
                    "label": fr.label,
                    "status": "FAILED",
                    "error": f"{type(exc).__name__}: {exc}",
                    "elapsed_s": time.time() - t0,
                    "n_specs": 0,
                }
            )
            continue

        n_repro = 0
        n_checked = 0
        deltas: list[float] = []
        for res in results:
            cap = CAPTURED.get(res.pattern_id)
            if cap is None:
                continue
            r = cap["returns"].dropna()
            if len(r) == 0:
                continue
            rebuilt_sharpe = sharpe_ratio(r, periods_per_year=fr.periods_per_year)
            prow = (
                persisted.get((fr.persisted_run_tag, res.pattern_id), {})
                if fr.persisted_run_tag
                else {}
            )
            delta = None
            if prow.get("persisted_sharpe") is not None:
                delta = float(rebuilt_sharpe - prow["persisted_sharpe"])
                deltas.append(abs(delta))
                n_checked += 1
                n_repro += int(abs(delta) <= 0.05)
            series_by_spec[res.pattern_id] = r
            spec_meta[res.pattern_id] = {
                "family_label": fr.label,
                "family_key": prow.get("family_key") or res.family,
                "holding_days": cap["holding_days"],
                "periods_per_year": fr.periods_per_year,
                "n_observations": len(r),
                "rebuilt_sharpe": float(rebuilt_sharpe),
                "rebuilt_dsr": float(res.deflated_sharpe.dsr),
                "persisted_sharpe": prow.get("persisted_sharpe"),
                "persisted_dsr": prow.get("persisted_dsr"),
                "sharpe_delta_vs_persisted": delta,
                "persisted_run_tag": fr.persisted_run_tag,
            }

        family_status.append(
            {
                "label": fr.label,
                "status": "ok",
                "elapsed_s": time.time() - t0,
                "n_specs": sum(1 for m in spec_meta.values() if m["family_label"] == fr.label),
                "n_checked_against_persisted": n_checked,
                "n_reproduced_within_0.05": n_repro,
                "max_abs_sharpe_delta": max(deltas) if deltas else None,
                "median_abs_sharpe_delta": float(np.median(deltas)) if deltas else None,
                "persisted_run_tag": fr.persisted_run_tag,
                "periods_per_year": fr.periods_per_year,
                "note": fr.note,
            }
        )
        _log(
            f"  -> {family_status[-1]['n_specs']} specs, "
            f"{n_repro}/{n_checked} reproduced, {time.time() - t0:.0f}s"
        )

    matrix = pd.DataFrame(series_by_spec).sort_index()
    matrix.index.name = "date"
    with gzip.open(MATRIX_PATH, "wt") as fh:
        matrix.to_csv(fh)
    META_PATH.write_text(
        json.dumps(
            {
                "run_tag": RUN_TAG,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "elapsed_s": time.time() - started,
                "price_freeze_dir": str(PRICE_FREEZE_DIR),
                "price_freeze_cache_hits": freeze_stats["hits"],
                "price_freeze_live_fetches": freeze_stats["misses"],
                "matrix_shape": list(matrix.shape),
                "families": family_status,
                "specs": spec_meta,
            },
            indent=2,
            default=str,
        )
    )
    _log(f"wrote {MATRIX_PATH.name}: {matrix.shape[0]} dates x {matrix.shape[1]} specs")


# ---------------------------------------------------------------------------
# STAGE 2
# ---------------------------------------------------------------------------

# The live forward-validation registrations, as of 2026-09-04. Sourced from the
# registration modules' own constants, not from memory:
#   quality_forward_registration.CBOP_PATTERN_ID / NOA_NEUTRAL_PATTERN_ID
#   short_interest_forward_registration.SHORT_INTEREST_PATTERN_ID
#   lazy_prices_forward_registration.LAZY_PRICES_PATTERN_ID
#   bab_forward_registration.BAB_PATTERN_ID
REGISTERED_SPECS = [
    "cbop_ls_h63",
    "noa_neutral_ls_h126_median",
    "si_ratio_hedged_h21",
    "lazy_jaccard_full_h126_ivol",
    "xc_btcbeta_l180_h180",
]
# The one recommended for removal (commit 20417f8, pending user sign-off).
NOA_NEUTRAL_SPEC = "noa_neutral_ls_h126_median"


def _seed_sweep(
    corr: pd.DataFrame, label: str
) -> tuple[EffectiveNResult, dict[int, int], list[float]]:
    """Re-estimate across SEED_SWEEP and return the headline result plus the
    full distribution of cluster counts. ONC is a stochastic k-means search;
    quoting one seed's E[K] as if it were a point estimate would be exactly the
    overclaimed precision this project's rules forbid."""
    counts: dict[int, int] = {}
    silhouettes: list[float] = []
    headline: EffectiveNResult | None = None
    for seed in SEED_SWEEP:
        res = estimate_effective_n_from_correlation(corr, random_state=seed)
        counts[res.n_effective] = counts.get(res.n_effective, 0) + 1
        if np.isfinite(res.mean_silhouette):
            silhouettes.append(res.mean_silhouette)
        if seed == RANDOM_STATE:
            headline = res
    if headline is None:
        headline = estimate_effective_n_from_correlation(corr, random_state=RANDOM_STATE)
    _log(f"  {label}: E[K] across {len(SEED_SWEEP)} seeds -> {dict(sorted(counts.items()))}")
    return headline, counts, silhouettes


def _population_block(
    name: str,
    question: str,
    matrix: pd.DataFrame,
    columns: list[str],
    meta: dict[str, Any],
) -> dict[str, Any]:
    sub = matrix[columns]
    from_returns = estimate_effective_n_from_returns(sub, random_state=RANDOM_STATE)
    corr = sub.corr(min_periods=60)
    headline, counts, silhouettes = _seed_sweep(corr, name)

    off = corr.to_numpy()[~np.eye(len(corr), dtype=bool)]
    var_eff = variance_effective_n(corr)

    # Pairwise overlap: how many observations each correlation actually rests
    # on. The binding constraint on confidence, reported rather than assumed.
    notna = sub.notna().astype(float)
    overlap = notna.T.to_numpy() @ notna.to_numpy()
    off_overlap = overlap[~np.eye(len(corr), dtype=bool)]

    # ---- EFFECTIVE independent observations, which is the number that
    # actually governs confidence here and is FAR smaller than the nominal
    # count. Every spec in this project holds a cohort for `holding_days` and
    # rebalances into OVERLAPPING cohorts daily, so consecutive daily returns
    # are strongly dependent by construction: a spec with holding_days=126
    # over 2926 trading days contains roughly 2926/126 ~ 23 non-overlapping
    # holding periods, not 2926 independent draws.
    #
    # STATED AS THE HEURISTIC IT IS, not as an exact result: n/h is the
    # standard non-overlapping-blocks count. It is a coarse, conservative
    # proxy for the true effective sample size, chosen because it needs no
    # assumption about the autocorrelation's shape. The Fisher-z standard
    # error 1/sqrt(n_eff - 3) built on it is likewise indicative, not exact.
    holdings = {c: (meta["specs"].get(c, {}) or {}).get("holding_days") for c in columns}
    pair_independent: list[float] = []
    for i, ca in enumerate(columns):
        for j, cb in enumerate(columns):
            if j <= i:
                continue
            ha, hb = holdings.get(ca), holdings.get(cb)
            if not ha or not hb:
                continue
            # The SLOWER of the two governs: the pair cannot carry more
            # independent joint observations than its stickier leg supplies.
            pair_independent.append(float(overlap[i, j]) / float(max(ha, hb)))
    min_ind = min(pair_independent) if pair_independent else float("nan")
    med_ind = float(np.median(pair_independent)) if pair_independent else float("nan")
    corr_se = 1.0 / np.sqrt(med_ind - 3.0) if med_ind > 3.0 else float("nan")

    # ---- MOVING-BLOCK BOOTSTRAP on the variance-based N_eff.
    # A point estimate of N_eff with no band around it would imply a precision
    # this data does not have -- the whole reason the effective-independent
    # count above is so small. Blocks are resampled with length equal to the
    # population's SLOWEST holding period, which is the crudest defensible way
    # to preserve the overlap-induced autocorrelation that makes daily
    # observations non-independent in the first place. Rows are resampled
    # jointly across specs, so the cross-sectional correlation structure --
    # the thing being measured -- is never broken up.
    block = max((h for h in holdings.values() if h), default=21)
    block = int(min(block, max(len(sub) // 8, 2)))  # need >=8 blocks to resample
    rng = np.random.default_rng(RANDOM_STATE)
    arr = sub.to_numpy()
    n_rows = arr.shape[0]
    n_blocks = max(n_rows // block, 1)
    boot: list[float] = []
    for _ in range(400):
        starts = rng.integers(0, max(n_rows - block, 1), size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])
        idx = idx[idx < n_rows]
        resampled = pd.DataFrame(arr[idx], columns=sub.columns)
        c = resampled.corr(min_periods=60)
        v = variance_effective_n(c)
        if np.isfinite(v):
            boot.append(v)
    boot_lo, boot_hi = (
        (float(np.percentile(boot, 5)), float(np.percentile(boot, 95))) if boot else (float("nan"),) * 2
    )

    return {
        "name": name,
        "question": question,
        "n_specs": len(columns),
        "specs": columns,
        "onc_n_effective_headline": headline.n_effective,
        "onc_cluster_count_distribution": {str(k): v for k, v in sorted(counts.items())},
        "onc_mean_silhouette_headline": headline.mean_silhouette,
        "onc_mean_silhouette_range": [min(silhouettes), max(silhouettes)] if silhouettes else None,
        "onc_floor_met": headline.floor_met,
        "onc_clusters": [
            {"cluster_id": c.cluster_id, "members": c.members, "quality_tstat": c.quality_tstat}
            for c in headline.clusters
        ],
        "onc_interpretation": headline.interpretation,
        "onc_dropped_trials": from_returns.dropped_trials,
        "variance_effective_n": var_eff,
        "variance_effective_n_bootstrap_p05": boot_lo,
        "variance_effective_n_bootstrap_p95": boot_hi,
        "bootstrap_block_length_days": block,
        # nan-aware: a pair with less than min_overlap shared observations comes
        # back NaN from .corr(min_periods=...), and a plain mean would silently
        # turn the whole summary into NaN rather than reporting the gap.
        "n_offdiag_pairs_unmeasurable": int(np.count_nonzero(~np.isfinite(off))),
        "mean_offdiag_correlation": float(np.nanmean(off)),
        "median_offdiag_correlation": float(np.nanmedian(off)),
        "max_abs_offdiag_correlation": float(np.nanmax(np.abs(off))),
        "min_pairwise_overlap": int(off_overlap.min()),
        "median_pairwise_overlap": float(np.median(off_overlap)),
        "min_pairwise_independent_periods": min_ind,
        "median_pairwise_independent_periods": med_ind,
        "implied_correlation_std_error": corr_se,
        "correlation_matrix": {
            a: {b: float(corr.loc[a, b]) for b in corr.columns} for a in corr.index
        },
        "spec_meta": {c: meta["specs"][c] for c in columns if c in meta["specs"]},
    }


def _multi_signal_crosscheck() -> dict[str, Any] | None:
    """The ONE independently-persisted correlation this project already holds:
    multi_signal_combination's stored candidate_daily_returns, on its own
    truncated common window. Used to check this run's cbop/noa correlation
    against a number computed months earlier by different code on a different
    price vintage -- an external check on the reconstruction, not an input."""
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT full_result_json, run_tag FROM cross_sectional_trial_results "
        "WHERE family_key='multi_signal_combination' AND trial_id='rmt_denoised_hrp' "
        "ORDER BY LENGTH(full_result_json) DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row is None:
        return None
    payload = json.loads(row[0])
    cm = payload.get("correlation_matrix") or {}
    if "cbop_ls_h63" not in cm or "noa_neutral_ls_h126_median" not in cm:
        return None
    return {
        "run_tag": row[1],
        "window": [payload.get("window_start"), payload.get("window_end")],
        "n_trading_days": payload.get("n_trading_days"),
        "cbop_vs_noa_neutral": cm["cbop_ls_h63"]["noa_neutral_ls_h126_median"],
        "note": (
            "computed 2026-08-30 by cross_sectional multi-signal code on a TRUNCATED common "
            "window and a different price vintage; an independent sanity check on this run's "
            "reconstruction, not a substitute for it"
        ),
    }


def stage2_cluster() -> None:
    with gzip.open(MATRIX_PATH, "rt") as fh:
        matrix = pd.read_csv(fh, index_col=0, parse_dates=True)
    meta = json.loads(META_PATH.read_text())
    specs = meta["specs"]

    available = set(matrix.columns)

    # --- POP-A: the live registrations -------------------------------------
    pop_a = [s for s in REGISTERED_SPECS if s in available]
    missing_a = [s for s in REGISTERED_SPECS if s not in available]

    # --- POP-B: every spec clearing the project's own 0.50 DSR floor -------
    # Data-driven from the PERSISTED dsr column where one exists (the number
    # the registration decisions were actually made on), falling back to the
    # rebuilt dsr only where no persisted row exists (crypto), which is
    # flagged rather than silently mixed.
    pop_b: list[str] = []
    pop_b_basis: dict[str, str] = {}
    for pid, m in specs.items():
        if pid not in available:
            continue
        dsr = m.get("persisted_dsr")
        basis = "persisted"
        if dsr is None:
            dsr = m.get("rebuilt_dsr")
            basis = "rebuilt (no persisted row)"
        if dsr is not None and dsr >= DSR_FLOOR:
            pop_b.append(pid)
            pop_b_basis[pid] = f"{basis} dsr={dsr:.4f}"
    pop_b.sort()

    # --- POP-C: one spec per family ----------------------------------------
    by_family: dict[str, list[str]] = {}
    for pid, m in specs.items():
        if pid in available:
            by_family.setdefault(m["family_label"], []).append(pid)
    pop_c: list[str] = []
    pop_c_basis: dict[str, str] = {}
    for family, pids in sorted(by_family.items()):
        registered = [p for p in pids if p in REGISTERED_SPECS]
        if registered:
            for p in registered:  # quality runs CBOP and NOA in one pass
                pop_c.append(p)
                pop_c_basis[p] = f"{family}: live registration"
            # The quality pass also contains the un-neutralized NOA family,
            # which has no registration of its own; represent it by its top DSR
            # so the family is not silently dropped from the type census.
            non_reg = [p for p in pids if p not in REGISTERED_SPECS]
            if family.startswith("quality_cbop"):
                best = max(
                    (p for p in non_reg if p.startswith("noa_")),
                    key=lambda p: specs[p].get("persisted_dsr") or -1,
                    default=None,
                )
                if best:
                    pop_c.append(best)
                    pop_c_basis[best] = "quality_noa (un-neutralized): top persisted DSR"
            continue
        best = max(pids, key=lambda p: (specs[p].get("persisted_dsr") or specs[p]["rebuilt_dsr"]))
        pop_c.append(best)
        pop_c_basis[best] = f"{family}: top DSR (no registration in this family)"

    blocks = [
        _population_block(
            "POP-A registered",
            "Are the LIVE forward-validation registrations diversified bets?",
            matrix,
            pop_a,
            meta,
        ),
        _population_block(
            "POP-A' registered minus noa_neutral",
            "The same question if the pending noa_neutral removal is signed off.",
            matrix,
            [s for s in pop_a if s != NOA_NEUTRAL_SPEC],
            meta,
        ),
        _population_block(
            f"POP-B admissible pool (DSR>={DSR_FLOOR:.2f})",
            "How much genuinely distinct search does the qualifying candidate pool represent?",
            matrix,
            pop_b,
            meta,
        ),
        _population_block(
            "POP-C one spec per family",
            "How many distinct return-generating processes does this project have at all?",
            matrix,
            pop_c,
            meta,
        ),
    ]

    payload = {
        "run_tag": RUN_TAG,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "random_state_headline": RANDOM_STATE,
        "seed_sweep": [SEED_SWEEP[0], SEED_SWEEP[-1]],
        "min_trials_for_clustering": MIN_TRIALS_FOR_CLUSTERING,
        "dsr_floor": DSR_FLOOR,
        "matrix_shape": list(matrix.shape),
        "registered_specs_not_rebuilt": missing_a,
        "pop_b_basis": pop_b_basis,
        "pop_c_basis": pop_c_basis,
        "multi_signal_crosscheck": _multi_signal_crosscheck(),
        "stage1_meta": meta,
        "populations": blocks,
    }
    JSON_PATH.write_text(json.dumps(payload, indent=2, default=str))
    REPORT_PATH.write_text(_render_report(payload))
    _log(f"wrote {REPORT_PATH.name} and {JSON_PATH.name}")


def _render_report(p: dict[str, Any]) -> str:
    L: list[str] = []
    a = L.append
    a("EFFECTIVE NUMBER OF INDEPENDENT BETS -- MEASURED, NOT EYEBALLED -- 2026-09-04")
    a("=" * 78)
    a(f"run_tag={p['run_tag']}  generated={p['generated_at']}")
    a(
        "Estimator: app/services/research_lab/effective_n_clustering.py (ONC; Lopez de Prado & "
        "Lewis 2019, Quantitative Finance 19(9) 1555-1565, SSRN 3167017)."
    )
    a(f"Return matrix: {p['matrix_shape'][0]} dates x {p['matrix_shape'][1]} specs.")
    a(
        f"Headline seed {p['random_state_headline']}; every E[K] additionally swept over seeds "
        f"{p['seed_sweep'][0]}..{p['seed_sweep'][1]} and the full distribution reported."
    )
    if p["registered_specs_not_rebuilt"]:
        a(f"!! REGISTERED SPECS WITH NO REBUILT SERIES: {p['registered_specs_not_rebuilt']}")
    a("")

    a("STAGE 1 -- REPRODUCTION OF EACH FAMILY AGAINST ITS PERSISTED run_tag")
    a("-" * 78)
    a(
        f"Price vintage frozen to disk for this analysis: "
        f"{p['stage1_meta']['price_freeze_live_fetches']} live fetch(es), "
        f"{p['stage1_meta']['price_freeze_cache_hits']} replayed from the freeze."
    )
    for f in p["stage1_meta"]["families"]:
        if f["status"] != "ok":
            a(f"  {f['label']:32s} FAILED: {f['error']}")
            continue
        chk = f.get("n_checked_against_persisted") or 0
        mx = f.get("max_abs_sharpe_delta")
        a(
            f"  {f['label']:32s} {f['n_specs']:3d} specs  "
            f"reproduced {f.get('n_reproduced_within_0.05', 0)}/{chk} within 0.05  "
            f"max|dSharpe|={'n/a' if mx is None else f'{mx:.4f}'}  "
            f"{f['elapsed_s']:.0f}s"
        )
        if f["note"]:
            a(f"      note: {f['note']}")
    a("")

    if p["multi_signal_crosscheck"]:
        c = p["multi_signal_crosscheck"]
        a("INDEPENDENT CROSS-CHECK (the one return series this project already persisted)")
        a("-" * 78)
        a(
            f"  multi_signal_combination run_tag={c['run_tag']}, window {c['window'][0]}.."
            f"{c['window'][1]} ({c['n_trading_days']} days)"
        )
        a(f"  its stored corr(cbop_ls_h63, noa_neutral_ls_h126_median) = {c['cbop_vs_noa_neutral']:+.4f}")
        # The same pair as measured by THIS run, side by side, so a reader can
        # judge the corroboration instead of taking the word for it.
        mine = None
        for blk in p["populations"]:
            cmx = blk["correlation_matrix"]
            if "cbop_ls_h63" in cmx and "noa_neutral_ls_h126_median" in cmx["cbop_ls_h63"]:
                mine = cmx["cbop_ls_h63"]["noa_neutral_ls_h126_median"]
                break
        if mine is not None:
            a(
                f"  THIS run's independently-rebuilt same pair            = {mine:+.4f}  "
                f"(difference {mine - c['cbop_vs_noa_neutral']:+.4f})"
            )
        a(f"  {c['note']}")
        a("")

    for b in p["populations"]:
        a("=" * 78)
        a(f"{b['name']}  (N={b['n_specs']})")
        a(f"QUESTION: {b['question']}")
        a("-" * 78)
        dist = ", ".join(f"K={k}x{v}" for k, v in b["onc_cluster_count_distribution"].items())
        a(f"  ONC E[K] (headline seed): {b['onc_n_effective_headline']}")
        a(f"  ONC E[K] across seeds   : {dist}")
        a(
            f"  mean silhouette         : {b['onc_mean_silhouette_headline']:.4f} "
            f"(range over seeds {b['onc_mean_silhouette_range'][0]:.4f}.."
            f"{b['onc_mean_silhouette_range'][1]:.4f})"
            if b["onc_mean_silhouette_range"]
            else f"  mean silhouette         : {b['onc_mean_silhouette_headline']}"
        )
        a(f"  ONC floor met (N>={MIN_TRIALS_FOR_CLUSTERING})   : {b['onc_floor_met']}")
        a(
            f"  variance-based N_eff    : {b['variance_effective_n']:.3f} of {b['n_specs']} "
            f"(equal-weighted; see variance_effective_n's docstring for the two-line derivation)"
        )
        a(
            f"    90% moving-block bootstrap interval: "
            f"[{b['variance_effective_n_bootstrap_p05']:.2f}, "
            f"{b['variance_effective_n_bootstrap_p95']:.2f}] "
            f"(400 resamples, block={b['bootstrap_block_length_days']}d = the population's "
            f"slowest holding period)"
        )
        a(
            f"  off-diagonal corr       : mean {b['mean_offdiag_correlation']:+.4f}, "
            f"median {b['median_offdiag_correlation']:+.4f}, "
            f"max|rho| {b['max_abs_offdiag_correlation']:.4f}"
        )
        a(
            f"  pairwise overlap        : min {b['min_pairwise_overlap']}, "
            f"median {b['median_pairwise_overlap']:.0f} raw daily observations"
        )
        a(
            f"  EFFECTIVE independent   : min {b['min_pairwise_independent_periods']:.1f}, "
            f"median {b['median_pairwise_independent_periods']:.1f} non-overlapping holding "
            f"periods per pair"
        )
        a(
            f"    -> implied std error on a single correlation ~ "
            f"{b['implied_correlation_std_error']:.3f} (Fisher-z, 1/sqrt(n_eff-3), indicative). "
            f"Any |rho| below about {2 * b['implied_correlation_std_error']:.2f} is NOT "
            f"distinguishable from zero at this sample size."
            if np.isfinite(b["implied_correlation_std_error"])
            else "    -> too few independent periods to quote a correlation standard error."
        )
        if b["n_offdiag_pairs_unmeasurable"]:
            a(f"  UNMEASURABLE PAIRS      : {b['n_offdiag_pairs_unmeasurable']} (insufficient overlap)")
        if b["onc_dropped_trials"]:
            a(f"  dropped by data quality : {b['onc_dropped_trials']}")
        a("")
        a("  CLUSTERS (headline seed):")
        for c in b["onc_clusters"]:
            a(f"    cluster {c['cluster_id']} (q={c['quality_tstat']:.3f}): {', '.join(c['members'])}")
        a("")
        if b["n_specs"] <= 8:
            a("  FULL CORRELATION MATRIX:")
            cols = b["specs"]
            width = max(len(c) for c in cols) + 2
            a("    " + " " * width + "".join(f"{c[:12]:>14s}" for c in cols))
            for r in cols:
                a(
                    "    "
                    + f"{r:<{width}s}"
                    + "".join(f"{b['correlation_matrix'][r][c]:>+14.4f}" for c in cols)
                )
            a("")
        a("  ONC's own interpretation string:")
        for line in _wrap(b["onc_interpretation"], 74):
            a(f"    {line}")
        a("")

    return "\n".join(L) + "\n"


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def main() -> int:
    if not MATRIX_PATH.exists() or not META_PATH.exists():
        _log("no return matrix on disk -- running STAGE 1 (rebuild)")
        stage1_rebuild()
    else:
        _log(f"return matrix already on disk ({MATRIX_PATH.name}) -- skipping STAGE 1")
    _log("running STAGE 2 (clustering)")
    stage2_cluster()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
