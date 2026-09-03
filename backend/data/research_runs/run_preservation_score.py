"""Rebuilds the realized daily net-return series for every cheaply-reproducible
cross-sectional family, scores every spec with preservation_score.py, and runs
the turnover-vs-decay test that the score deliberately does NOT assume.

WHY A REBUILD IS NEEDED AT ALL. cross_sectional_trial_results persists only
SUMMARY statistics (Sharpe, DSR, PSR, n_observations and the family's own
diagnostics inside full_result_json). It does NOT persist the daily return
series, and neither does any research_runs report. Max drawdown, half-sample
Sharpes and every path statistic therefore cannot be read out of the database
at all -- they have to be recomputed from a replay. That is this file's job.

HOW THE SERIES IS OBTAINED WITHOUT REIMPLEMENTING ANY BACKTEST. Every family
listed below routes through cross_sectional.screen_cross_sectional_universe,
which calls cross_sectional.run_cross_sectional_backtest once per spec and
then DISCARDS the CrossSectionalBacktestResult.daily_returns it returns. This
runner wraps that one function on the module object, records the series it
already produced, and returns the result object untouched. Nothing about any
family's replay, cost model, universe or spec grid is altered or duplicated:
the numbers come from the families' own production entry points.

REPRODUCIBILITY IS CHECKED, NOT ASSUMED. For every spec, the rebuilt Sharpe is
compared against the Sharpe already persisted for that family's canonical
run_tag, and the agreement is reported per family. A family that fails to
reproduce is REPORTED as failing to reproduce; it is not quietly dropped and
its numbers are not quietly used as if they matched.

FAMILIES DELIBERATELY EXCLUDED, and why (stated so the sample is honest):
  * best_ideas_13f      -- its own report records 207.4 minutes of wall clock
                           (form 13F parsing). Too expensive for this analysis.
  * eigenportfolio_statarb, dividend_month_premium -- bespoke replay engines
                           that do NOT go through screen_cross_sectional_universe,
                           so the single capture hook here does not see them.
  * phase_a_intraday_expanded -- intraday patterns, a different harness
                           (intraday_patterns.screen_pattern_universe) and a
                           holding period that is not measured in days.
  * multi_signal_combination  -- derived portfolios OF the other families'
                           signals, not independent candidates; scoring them
                           alongside their own inputs would double-count.

ATTEMPTED AND CAPTURED NOTHING, kept in the list on purpose so the ledger
records the attempt rather than hiding it: insider_opportunistic and pead_ear.
Both are EVENT-DRIVEN families whose own module docstrings state outright that
they cannot run on screen_cross_sectional_universe -- their spec types
(InsiderSpec, PeadSpec) are not CrossSectionalSpec and their replays never
call run_cross_sectional_backtest. The hook below therefore sees nothing for
them, correctly. That is a property of this hook, NOT a data failure, and NOT
evidence about either family.

Run from backend/ with ./venv/bin/python.
"""

from __future__ import annotations

import json
import logging
import statistics
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# WORKTREE BINDING GUARD — load-bearing, not boilerplate. Running this file by
# path puts data/research_runs/ on sys.path[0], NOT backend/, and this
# worktree's venv is a SYMLINK to the main worktree's venv, whose site-packages
# resolves `app` to the MAIN worktree's backend/app.
_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, which is not inside this worktree "
        f"({_BACKEND})."
    )

import pandas as pd

from app.services.research_lab import cross_sectional as xs
from app.services.research_lab.metrics import TRADING_DAYS_PER_YEAR
from app.services.research_lab.preservation_score import (
    LOW_TURNOVER_MIN_HOLDING_DAYS,
    MCLEAN_PONTIFF_CITATION,
    OOS_RETENTION,
    compute_preservation_metrics,
    turnover_bucket,
)

RUN_TAG = "preservation_score_2026-09-03"
REPORT_PATH = "data/research_runs/preservation_score_2026-09-03.txt"
JSON_PATH = "data/research_runs/preservation_score_2026-09-03.json"

# The gitignored vendor caches and the local sqlite database live in the MAIN
# checkout, not in a worktree (both are gitignored, so a fresh worktree has
# neither). Pointed at explicitly rather than relative to _BACKEND so running
# this from a worktree reads the same real EDGAR JSON and the same persisted
# trial rows the original runs wrote, instead of silently finding nothing.
_MAIN_BACKEND = Path("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend")
SHARED_EDGAR_CACHE = _MAIN_BACKEND / "data" / "edgar_companyfacts"
DB_PATH = _MAIN_BACKEND / "aladdin2.db"

# Reproduction tolerance on the rebuilt annualized Sharpe vs the persisted one.
# Not zero: yfinance adjusted closes are restated over time (splits, dividend
# back-adjustment) and the universes are rebuilt live, so a rerun days or weeks
# later is not expected to be bit-identical. Anything inside this band is
# reported as reproduced; anything outside is reported as NOT reproduced.
SHARPE_REPRODUCTION_TOLERANCE = 0.05

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("preservation_score_runner")


# ---------------------------------------------------------------------------
# The capture hook
# ---------------------------------------------------------------------------

CAPTURED: dict[str, dict[str, Any]] = {}
_ORIGINAL_BACKTEST = xs.run_cross_sectional_backtest


def _capturing_backtest(data, spec, config, membership_fn=None):
    result = _ORIGINAL_BACKTEST(data, spec, config, membership_fn)
    if result.status == "ok" and len(result.daily_returns) > 0:
        CAPTURED[spec.pattern_id] = {
            "returns": result.daily_returns,
            "holding_days": spec.holding_days,
            "rank_fraction": spec.rank_fraction,
            "leg_weighting": spec.leg_weighting,
            "portfolio": spec.portfolio,
            "family": spec.family,
            "cohort_formation_days": spec.cohort_formation_days,
        }
    return result


xs.run_cross_sectional_backtest = _capturing_backtest


# ---------------------------------------------------------------------------
# Family invocations
# ---------------------------------------------------------------------------


@dataclass
class FamilyRun:
    """One family's production entry point plus the persisted run_tag its
    numbers must be checked against."""

    label: str
    family_keys: tuple[str, ...]
    persisted_run_tag: str
    invoke: Callable[[], list]
    periods_per_year: float = TRADING_DAYS_PER_YEAR
    note: str = ""


def _edgar():
    from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider

    return EdgarXbrlProvider(cache_dir=SHARED_EDGAR_CACHE)


def _quality_results(summary) -> list:
    """QualityScreeningSummary is the one summary with two result lists."""
    return list(summary.cbop_results) + list(summary.noa_results)


def _build_family_runs() -> list[FamilyRun]:
    from app.services.research_lab.cross_sectional_asset_growth import (
        run_asset_growth_screening,
    )
    from app.services.research_lab.cross_sectional_illiq import run_illiq_screening
    from app.services.research_lab.cross_sectional_insider import run_insider_screening
    from app.services.research_lab.cross_sectional_jump_drift import (
        run_jump_drift_screening,
    )
    from app.services.research_lab.cross_sectional_lazy_prices import (
        run_lazy_prices_screening,
    )
    from app.services.research_lab.cross_sectional_patterns import run_round_c_screening
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
    from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

    return [
        FamilyRun(
            label="residual_momentum",
            family_keys=("residual_momentum",),
            persisted_run_tag="residual_momentum_build_2026-09-02",
            invoke=lambda: run_residual_momentum_screening(
                end=date(2026, 9, 2), edgar=_edgar()
            ).results,
        ),
        FamilyRun(
            label="asset_growth",
            family_keys=("asset_growth",),
            persisted_run_tag="asset_growth_build_2026-09-01",
            invoke=lambda: run_asset_growth_screening(
                end=date(2026, 9, 1), edgar=_edgar()
            ).results,
        ),
        FamilyRun(
            label="quality_cbop + quality_noa",
            family_keys=("quality_cbop", "quality_noa"),
            persisted_run_tag="quality_build_2026-08-28",
            # The one summary that carries TWO result lists rather than a
            # `results` field: cross_sectional_quality.py screens the CBOP and
            # NOA families in a single pass and returns them separately.
            invoke=lambda: _quality_results(
                run_quality_screening(end=date(2026, 8, 28), edgar=_edgar())
            ),
        ),
        FamilyRun(
            label="quality_noa_industry_neutral",
            family_keys=("quality_noa_industry_neutral",),
            persisted_run_tag="noa_neutral_build_2026-08-28",
            invoke=lambda: run_noa_neutral_screening(
                end=date(2026, 8, 28), edgar=_edgar()
            ).results,
        ),
        FamilyRun(
            label="short_interest",
            family_keys=("short_interest",),
            persisted_run_tag="short_interest_build_2026-09-02",
            invoke=lambda: run_short_interest_screening(
                start=SHORT_INTEREST_FORMATION_START, end=date(2026, 9, 2), edgar=_edgar()
            ).results,
        ),
        FamilyRun(
            label="jump_drift",
            family_keys=("jump_drift",),
            persisted_run_tag="jump_drift_2026-08-30",
            invoke=lambda: run_jump_drift_screening(
                MEMBERSHIP_DATA_START, date(2026, 8, 30), run_event_study=False
            ).results,
        ),
        FamilyRun(
            label="round_c",
            family_keys=("round_c",),
            persisted_run_tag="edge_cost_reaudit_corrected_2026-08-30_flat_control",
            invoke=lambda: run_round_c_screening(MEMBERSHIP_DATA_START, date(2026, 8, 30))[0],
            note=(
                "checked against the re-audit's FLAT 5bp control arm, which is the same "
                "cost model as this default-config rerun"
            ),
        ),
        FamilyRun(
            label="liquidity_shock_delta_illiq",
            family_keys=("liquidity_shock_delta_illiq",),
            persisted_run_tag="illiq_build_2026-08-28",
            invoke=lambda: run_illiq_screening(MEMBERSHIP_DATA_START, date(2026, 8, 28))[0],
        ),
        FamilyRun(
            label="same_calendar_month_seasonality",
            family_keys=("same_calendar_month_seasonality",),
            persisted_run_tag="seasonality_build_2026-08-28",
            invoke=lambda: run_seasonality_screening(MEMBERSHIP_DATA_START, date(2026, 8, 28))[0],
        ),
        FamilyRun(
            label="lazy_prices",
            family_keys=("lazy_prices",),
            persisted_run_tag="lazy_prices_2026-09-01",
            invoke=lambda: run_lazy_prices_screening(
                MEMBERSHIP_DATA_START, date(2026, 9, 1)
            ).results,
            note="reads the ~900MB gitignored EDGAR filing-text vendor cache; no fresh text pulls",
        ),
        FamilyRun(
            label="insider_opportunistic",
            family_keys=("insider_opportunistic",),
            persisted_run_tag="insider_form4_verified_2026-08-28",
            invoke=lambda: run_insider_screening(
                MEMBERSHIP_DATA_START, date(2026, 8, 28)
            ).results,
        ),
        FamilyRun(
            label="pead_ear",
            family_keys=("pead_ear",),
            persisted_run_tag="pead_build_2026-08-28",
            invoke=lambda: run_pead_screening(MEMBERSHIP_DATA_START, date(2026, 8, 28)).results,
        ),
    ]


# ---------------------------------------------------------------------------
# Persisted-row lookup
# ---------------------------------------------------------------------------


def load_persisted() -> dict[tuple[str, str], dict[str, Any]]:
    """Every persisted trial row keyed by (run_tag, trial_id)."""
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT family_key, trial_id, run_tag, sharpe_annualized, dsr, psr_vs_zero, "
        "n_observations, n_trials FROM cross_sectional_trial_results"
    ).fetchall()
    conn.close()
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for fam, tid, tag, sharpe, dsr, psr, nobs, ntrials in rows:
        out[(tag, tid)] = {
            "family_key": fam,
            "trial_id": tid,
            "run_tag": tag,
            "persisted_sharpe": sharpe,
            "persisted_dsr": dsr,
            "persisted_psr": psr,
            "persisted_n_observations": nobs,
            "n_trials": ntrials,
        }
    return out


# ---------------------------------------------------------------------------
# Statistics used by the turnover-vs-decay test
# ---------------------------------------------------------------------------


def welch_t(a: list[float], b: list[float]) -> tuple[float | None, float | None]:
    """Welch's two-sample t statistic and its Welch-Satterthwaite df.

    No p-value is printed anywhere in the report: with these sample sizes and
    with specs inside a family sharing a return series, a p-value would imply
    an independence this data does not have. The statistic and df are reported
    so a reader can see the magnitude relative to the noise."""
    if len(a) < 2 or len(b) < 2:
        return None, None
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    na, nb = len(a), len(b)
    denom = va / na + vb / nb
    if denom <= 0:
        return None, None
    t = (ma - mb) / (denom**0.5)
    df_num = denom**2
    df_den = (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    return t, (df_num / df_den if df_den > 0 else None)


def spearman(xs_: list[float], ys_: list[float]) -> float | None:
    if len(xs_) < 3:
        return None
    rx = pd.Series(xs_).rank()
    ry = pd.Series(ys_).rank()
    if rx.std(ddof=1) == 0 or ry.std(ddof=1) == 0:
        return None
    return float(rx.corr(ry, method="pearson"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


@dataclass
class SpecRecord:
    family_key: str
    pattern_id: str
    holding_days: int
    bucket: str
    metrics: dict[str, Any]
    persisted: dict[str, Any] = field(default_factory=dict)
    reproduced: bool = False


def main() -> int:
    started = time.time()
    persisted = load_persisted()
    runs = _build_family_runs()

    records: list[SpecRecord] = []
    family_status: list[dict[str, Any]] = []

    for fr in runs:
        CAPTURED.clear()
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] running {fr.label} ...", file=sys.stderr, flush=True)
        try:
            results = fr.invoke()
        except Exception as exc:  # noqa: BLE001 — a family that fails is REPORTED, never hidden
            traceback.print_exc()
            family_status.append(
                {
                    "label": fr.label,
                    "status": "FAILED",
                    "error": f"{type(exc).__name__}: {exc}",
                    "elapsed_s": time.time() - t0,
                    "n_specs": 0,
                    "n_reproduced": 0,
                }
            )
            continue

        elapsed = time.time() - t0
        n_reproduced = 0
        deltas: list[float] = []
        fam_records: list[SpecRecord] = []

        for res in results:
            cap = CAPTURED.get(res.pattern_id)
            if cap is None:
                continue
            m = compute_preservation_metrics(
                cap["returns"],
                dsr=res.deflated_sharpe.dsr,
                periods_per_year=fr.periods_per_year,
            )
            prow = persisted.get((fr.persisted_run_tag, res.pattern_id), {})
            reproduced = False
            if prow.get("persisted_sharpe") is not None:
                delta = abs(m.sharpe_full - prow["persisted_sharpe"])
                deltas.append(delta)
                reproduced = delta <= SHARPE_REPRODUCTION_TOLERANCE
                n_reproduced += int(reproduced)
            d = m.as_dict()
            d["rerun_dsr"] = res.deflated_sharpe.dsr
            d["rerun_n_trials"] = res.deflated_sharpe.n_trials
            d["rank_fraction"] = cap["rank_fraction"]
            d["leg_weighting"] = cap["leg_weighting"]
            d["portfolio"] = cap["portfolio"]
            fam_records.append(
                SpecRecord(
                    family_key=prow.get("family_key") or res.family,
                    pattern_id=res.pattern_id,
                    holding_days=cap["holding_days"],
                    bucket=turnover_bucket(cap["holding_days"]) or "unknown",
                    metrics=d,
                    persisted=prow,
                    reproduced=reproduced,
                )
            )

        records.extend(fam_records)
        family_status.append(
            {
                "label": fr.label,
                "status": "ok",
                "elapsed_s": elapsed,
                "n_specs": len(fam_records),
                "n_reproduced": n_reproduced,
                "n_with_persisted_row": len(deltas),
                "median_abs_sharpe_delta": (statistics.median(deltas) if deltas else None),
                "max_abs_sharpe_delta": (max(deltas) if deltas else None),
                "persisted_run_tag": fr.persisted_run_tag,
                "note": fr.note,
            }
        )
        print(
            f"    -> {len(fam_records)} specs, {n_reproduced}/{len(deltas)} reproduced, "
            f"{elapsed:.0f}s",
            file=sys.stderr,
            flush=True,
        )

        # Written after EVERY family, not only at the end: these families take
        # tens of minutes in aggregate and a crash in a later one must not
        # discard the earlier ones' measured series.
        _write_payload(records, family_status, started)

    _write_payload(records, family_status, started)
    print(f"wrote {JSON_PATH}: {len(records)} specs", file=sys.stderr)
    return 0


def _write_payload(
    records: list[SpecRecord], family_status: list[dict[str, Any]], started: float
) -> None:
    payload = {
        "run_tag": RUN_TAG,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "oos_retention": OOS_RETENTION,
        "citation": MCLEAN_PONTIFF_CITATION,
        "low_turnover_min_holding_days": LOW_TURNOVER_MIN_HOLDING_DAYS,
        "sharpe_reproduction_tolerance": SHARPE_REPRODUCTION_TOLERANCE,
        "families": family_status,
        "specs": [
            {
                "family_key": r.family_key,
                "pattern_id": r.pattern_id,
                "holding_days": r.holding_days,
                "bucket": r.bucket,
                "reproduced": r.reproduced,
                **r.metrics,
                **{k: v for k, v in r.persisted.items() if k not in {"family_key", "trial_id"}},
            }
            for r in records
        ],
        "elapsed_s": time.time() - started,
    }
    out = _BACKEND / JSON_PATH
    out.write_text(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
