"""JOB 5 of futures_span_full_pull_2026-09-07: measure the REAL 31-instrument
CME-SPAN futures universe's effective breadth against the pre-declared floor
of 15.

This is the gate the whole TSMOM thread has been building toward
(project_tsmom_prep_sequencing_2026-09-05): two earlier ETF/cash universes
measured 7.10 and 8.11 and FAILED the floor, which is why the project moved
to real futures at all. This script does not decide anything by itself -- it
runs the already-built, already-unit-tested
app/services/research_lab/futures_effective_breadth.py against the real
chained continuous series produced by chain_cme_span_continuous.py.

It builds NO TSMOM signal: no lookback return, no volatility estimate, no
position sizing, no DSR, no registration.

RETURN PANEL
------------
One column per instrument, taken from the `chained_daily_return` column of
data/futures_daily/cme_span/continuous/<ROOT>.csv -- i.e. the MOP (2012)
Section 2.1 chained same-contract return, which by construction never lets a
roll gap leak into a return. NaN before an instrument's inception (RTY starts
2017-07-07), which is exactly the staggered-inception case the module's
pairwise / conservative routes exist to handle.

THE CL 2020-04-20 NEGATIVE-PRICE CONTAMINATION (a real, disclosed problem)
--------------------------------------------------------------------------
CL settled at -37.63 on 2020-04-20 -- a genuine market event, re-confirmed
directly from the pulled daily CSVs, and the ONLY negative settlement in the
entire 31-instrument universe. Ratio/percentage returns are not well defined
through a negative price: the chained series reports -305.97% on 2020-04-20
and then -126.60% on 2020-04-21 even though the price ROSE that day (-37.63
-> +10.01). Those two numbers are artifacts of the ratio convention, not
economic returns, and a correlation matrix is a second-moment estimate, so
two ~300%/-127% outliers in one column can move CL's correlations
materially.

Rather than silently pick one convention, this script reports BOTH:
  - HEADLINE: the panel exactly as chained, nothing removed.
  - SENSITIVITY: the same panel with CL's 2020-04-20 and 2020-04-21 returns
    masked to NaN (the two dates the ratio convention corrupts).
If the two land on the same side of the floor, the gate verdict is robust to
this judgment call. If they do not, that is itself the finding and the gate
result must be treated as unresolved rather than forced.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app  # noqa: E402

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, not inside {_BACKEND}"
    )

from app.services.research_lab.futures_effective_breadth import (  # noqa: E402
    EFFECTIVE_BREADTH_FLOOR,
    PUBLISHED_STEP1_BREADTH,
    PUBLISHED_STEP1B_BREADTH,
    effective_breadth_from_correlation,
    measure_futures_effective_breadth,
)

CONTINUOUS = _BACKEND / "data" / "futures_daily" / "cme_span" / "continuous"
OUT_JSON = _BACKEND / "data" / "research_runs" / "futures_effective_breadth_2026-09-07.json"

#: The two dates on which the ratio convention corrupts CL's return.
CL_CORRUPTED_DATES = ["2020-04-20", "2020-04-21"]


def load_return_panel() -> pd.DataFrame:
    """One column of chained daily returns per instrument."""
    series: dict[str, pd.Series] = {}
    for path in sorted(CONTINUOUS.glob("*.csv")):
        root = path.stem
        frame = pd.read_csv(path)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        series[root] = pd.Series(
            frame["chained_daily_return"].to_numpy(dtype=float),
            index=pd.DatetimeIndex(frame["trade_date"]),
            name=root,
        )
    panel = pd.DataFrame(series).sort_index()
    # The first row of every chained series is NaN by construction (no prior
    # close). Drop rows that are entirely NaN so they do not masquerade as
    # missing history.
    return panel.dropna(how="all")


def mask_cl_negative_price_dates(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    if "CL" not in out.columns:
        return out
    for d in CL_CORRUPTED_DATES:
        ts = pd.Timestamp(d)
        if ts in out.index:
            out.loc[ts, "CL"] = np.nan
    return out


def summarize(result: Any) -> dict[str, Any]:
    def one(m: Any) -> dict[str, Any]:
        return {
            "label": m.label,
            "breadth_eigenvalue": float(m.breadth_eigenvalue),
            "breadth_frobenius": float(m.breadth_frobenius),
            "cross_check_delta": float(m.cross_check_delta),
            "n_instruments": int(m.n_instruments),
            "n_observations": int(m.n_observations),
            "min_eigenvalue": float(m.min_eigenvalue),
            "n_missing_pairs": int(m.n_missing_pairs),
            "is_positive_semidefinite": bool(m.is_positive_semidefinite),
            "is_safely_interpretable": bool(m.is_safely_interpretable),
        }

    return {
        "common_window": one(result.common_window),
        "pairwise": one(result.pairwise),
        "conservative_max_rule": one(result.conservative),
        "common_window_start": str(result.common_window_start),
        "common_window_end": str(result.common_window_end),
        "floor": float(result.floor),
        "passes_floor": bool(result.passes_floor),
        # NOTE: `verdict` is a METHOD on FuturesBreadthResult, while its
        # siblings `passes_floor` / `estimates_disagree_materially` are
        # @property. Calling it without parens silently serializes a
        # bound-method repr into this report -- which is exactly what
        # happened on the first run of this script. Pinned by
        # tests/test_futures_effective_breadth.py::
        # test_verdict_returns_a_real_string_not_a_bound_method.
        "verdict": result.verdict(),
        "estimates_disagree_materially": bool(result.estimates_disagree_materially),
        "notes": list(result.notes),
    }


def main() -> None:
    panel = load_return_panel()
    print(f"panel: {panel.shape[0]} dates x {panel.shape[1]} instruments")
    print(f"        {panel.index.min().date()} .. {panel.index.max().date()}")

    headline = measure_futures_effective_breadth(panel)
    sens_panel = mask_cl_negative_price_dates(panel)
    sensitivity = measure_futures_effective_breadth(sens_panel)

    # Independent re-derivation of the headline number from primitives, NOT
    # by calling the same helper: build the common-window correlation matrix
    # with pandas, take eigenvalues with numpy, apply sum(l)^2/sum(l^2) by
    # hand. Must match the module's own figure.
    common_panel = panel.dropna(how="any")
    corr = common_panel.corr()
    eigs = np.linalg.eigvalsh(corr.to_numpy())
    by_hand = float((eigs.sum() ** 2) / (eigs**2).sum())
    module_value = headline.common_window.breadth_eigenvalue
    delta = abs(by_hand - module_value)

    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "universe": sorted(panel.columns),
        "n_instruments": int(panel.shape[1]),
        "panel_first_date": str(panel.index.min().date()),
        "panel_last_date": str(panel.index.max().date()),
        "floor": float(EFFECTIVE_BREADTH_FLOOR),
        "prior_failed_baselines": {
            "step1_etf_cash_43_tickers": PUBLISHED_STEP1_BREADTH,
            "step1b_expanded_68_tickers": PUBLISHED_STEP1B_BREADTH,
        },
        "headline_as_chained": summarize(headline),
        "sensitivity_cl_negative_dates_masked": summarize(sensitivity),
        "independent_rederivation": {
            "method": "pandas .corr() + numpy.linalg.eigvalsh + sum(l)^2/sum(l^2) by hand",
            "by_hand": by_hand,
            "module_value": module_value,
            "delta": delta,
            "agrees": bool(delta < 1e-9),
        },
        "cl_negative_price_dates_masked_in_sensitivity": CL_CORRUPTED_DATES,
    }
    report["gate"] = {
        "headline_breadth": headline.common_window.breadth_eigenvalue,
        "sensitivity_breadth": sensitivity.common_window.breadth_eigenvalue,
        "floor": float(EFFECTIVE_BREADTH_FLOOR),
        "headline_passes": bool(headline.passes_floor),
        "sensitivity_passes": bool(sensitivity.passes_floor),
        "robust_to_cl_judgment_call": bool(
            headline.passes_floor == sensitivity.passes_floor
        ),
    }

    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")

    print()
    print("=== EFFECTIVE BREADTH, real 31-instrument CME futures universe ===")
    for name, res in (("HEADLINE (as chained)", headline), ("SENSITIVITY (CL masked)", sensitivity)):
        cw = res.common_window
        print(
            f"{name:26} common-window {cw.breadth_eigenvalue:.4f} / {cw.n_instruments} "
            f"(frobenius {cw.breadth_frobenius:.4f}, delta {cw.cross_check_delta:.2e}, "
            f"n_obs {cw.n_observations})  -> {res.verdict()}"
        )
        print(
            f"{'':26} pairwise {res.pairwise.breadth_eigenvalue:.4f}   "
            f"conservative(max-rule) {res.conservative.breadth_eigenvalue:.4f}"
        )
    print()
    print(f"floor = {EFFECTIVE_BREADTH_FLOOR}")
    print(f"independent by-hand re-derivation: {by_hand:.12f} vs module {module_value:.12f} (delta {delta:.2e})")
    print()
    for n in headline.notes:
        print(" note:", n)
    print()
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
