"""EXPLORATORY diagnostic — explicitly EXCLUDED from the DSR grid.

Pre-registration check C3 forbids re-tuning Coval-Stafford's -15%/+25% cutoffs
to manufacture a sample, and requires that any re-run at different cutoffs be
labelled EXPLORATORY and kept out of the family's 24-spec denominator. This
script is that re-run. Nothing it produces is a candidate result, nothing it
produces is persisted to cross_sectional_trial_results, and no verdict here
supersedes the pre-registered one.

WHY IT EXISTS. The pre-registered run came back DEFINITE_NEGATIVE, but the
binding C2 check fired on every single spec: the long leg was formable in 0 of
65 months (S&P 500) and 2 of 67 months (S&P 600), and the short leg never. A
DSR computed on a strategy that essentially never trades is not evidence about
the mechanism in either direction, so reporting "DEFINITE_NEGATIVE" without
this diagnostic would overstate what was learned.

THE QUESTION THIS ANSWERS: is the emptiness a property of the MECHANISM (no
widespread forced selling happens any more) or of the CUTOFF TRANSFERRING
BADLY (the paper's fixed thresholds were percentiles of ITS ownership
distribution, and N-PORT's is far denser)? Those have different implications
for any future round, and the answer is measurable rather than arguable.

Coval & Stafford's footnote 7, verbatim: "The cutoffs of -15% and 25%
approximately correspond to the 5th and 95th percentiles of the PRESSURE
variable, respectively." So the paper's OWN definition of its cutoffs is
distributional. This script reports what the 5th/95th percentiles actually are
on this project's panels, and what the strategy does if the paper's
distributional definition (rather than its numeric values) is carried over.

Run from backend/ with
    ./venv/bin/python data/research_runs/explore_firesale_cutoffs.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app  # noqa: E402

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(f"REFUSING TO RUN: `app` resolved to {app.__file__}, outside {_BACKEND}")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.market_data.yfinance_provider import YFinanceProvider  # noqa: E402
from app.services.research_lab.cross_sectional_firesale_pressure import (  # noqa: E402
    FIRESALE_CUTOFF,
    FIRESALE_FORMATION_START,
    INFLOW_CUTOFF,
    MIN_FIRMS_PER_LEG,
    calendar_time_returns,
    month_end_snapshots,
)

SAMPLES = _BACKEND / "data" / "research_runs" / "firesale_samples"
OUT_TXT = _BACKEND / "data" / "research_runs" / "coval_stafford_firesale_EXPLORATORY_2026-09-08.txt"
OUT_JSON = _BACKEND / "data" / "research_runs" / "coval_stafford_firesale_EXPLORATORY_2026-09-08.json"

# The paper's own worked example (page 11) has 47 owners. Quoted so the
# ownership-density comparison below is anchored to a real number from the
# source rather than an impression of one.
PAPER_WORKED_EXAMPLE_OWNERS = 47


def _universe_api(universe: str):
    if universe == "sp500":
        from app.services.research_lab import sp500_membership_history as mod
    else:
        from app.services.research_lab import small_cap_membership_history as mod
    return mod


def main() -> int:
    lines: list[str] = []
    payload: dict = {"label": "EXPLORATORY — excluded from the DSR grid per pre-registration C3"}

    lines.append("COVAL-STAFFORD FIRE SALES — EXPLORATORY CUTOFF DIAGNOSTIC")
    lines.append("=" * 74)
    lines.append("EXPLORATORY ONLY. Excluded from the 24-spec DSR grid and from the")
    lines.append("family's verdict, per pre-registration check C3. No DB rows are written.")
    lines.append("")
    lines.append("The pre-registered result stands unchanged: DEFINITE_NEGATIVE by the")
    lines.append("letter of the DSR rule, but POWER-LIMITED on every spec by check C2,")
    lines.append("which is the honest reading. This file explains WHY the sample was empty.")
    lines.append("")

    provider = YFinanceProvider()
    results = {}

    for universe in ("sp500", "sp600"):
        panel = pd.read_csv(SAMPLES / f"{universe}_constrained_0.05.csv.gz", index_col=0, parse_dates=True)
        panel10 = pd.read_csv(SAMPLES / f"{universe}_constrained_0.1.csv.gz", index_col=0, parse_dates=True)
        # dropna() is load-bearing: np.percentile propagates NaN where pandas'
        # mean/std silently skip it, which produced an all-NaN first draft of
        # this table.
        values = panel.stack().dropna()
        values10 = panel10.stack().dropna()

        p05 = float(values.quantile(0.05))
        p95 = float(values.quantile(0.95))
        p01 = float(values.quantile(0.01))
        p99 = float(values.quantile(0.99))

        lines.append(f"[{universe}] PRESSURE DISTRIBUTION, |flow| > 5% arm")
        lines.append("-" * 74)
        lines.append(f"  cells                {len(values)}")
        lines.append(f"  mean / std           {values.mean():+.6f} / {values.std():.6f}")
        lines.append(f"  1st  percentile      {p01:+.6f}")
        lines.append(f"  5th  percentile      {p05:+.6f}   <- paper's own definition of its -15% cutoff")
        lines.append(f"  50th percentile      {values.median():+.6f}")
        lines.append(f"  95th percentile      {p95:+.6f}   <- paper's own definition of its +25% cutoff")
        lines.append(f"  99th percentile      {p99:+.6f}")
        lines.append(f"  min / max            {values.min():+.6f} / {values.max():+.6f}")
        lines.append(f"  cells <= -15%        {int((values <= FIRESALE_CUTOFF).sum())}")
        lines.append(f"  cells >= +25%        {int((values >= INFLOW_CUTOFF).sum())}")
        lines.append(f"  (|flow|>10% arm) cells <= -15%  {int((values10 <= FIRESALE_CUTOFF).sum())}")
        lines.append("")
        lines.append(
            f"  THE TRANSFER FAILURE, stated numerically: the paper calls -15% its 5th"
        )
        lines.append(
            f"  percentile; here the 5th percentile is {p05:+.4f}. To reach -15% on this"
        )
        lines.append(
            f"  panel a stock needs a net {abs(FIRESALE_CUTOFF):.0%} of its owners to be forced"
        )
        lines.append(
            f"  sellers at once, which on a panel this densely owned is a different"
        )
        lines.append("  event than the one the paper measured.")
        lines.append("")

        results[universe] = {
            "n_cells": int(len(values)),
            "mean": float(values.mean()),
            "std": float(values.std()),
            "p01": p01,
            "p05": p05,
            "median": float(values.median()),
            "p95": p95,
            "p99": p99,
            "min": float(values.min()),
            "max": float(values.max()),
            "cells_at_paper_firesale_cutoff": int((values <= FIRESALE_CUTOFF).sum()),
            "cells_at_paper_inflow_cutoff": int((values >= INFLOW_CUTOFF).sum()),
        }

        # --- the percentile-matched EXPLORATORY strategy ----------------------
        mod = _universe_api(universe)
        end = panel.index.max().date()
        history_start = FIRESALE_FORMATION_START - timedelta(days=500)
        names = mod.get_universe_over(max(mod.MEMBERSHIP_DATA_START, history_start), end)
        frames, _missing = provider.get_daily_ohlcv(names, history_start, end)
        close = frames["close"]
        close = close.loc[close.index <= pd.Timestamp(end)]

        arm = {}
        for label, lo, hi in (
            ("paper_fixed", FIRESALE_CUTOFF, INFLOW_CUTOFF),
            ("percentile_5_95", p05, p95),
            ("percentile_1_99", p01, p99),
        ):
            # A cutoff at a percentile of the pooled distribution is applied as a
            # FIXED number, exactly as the paper applies its own: the percentile
            # is used to CHOOSE the number, not recomputed per formation. That is
            # itself a look-ahead (the percentile is measured on the full sample)
            # and is one more reason this arm is exploratory only.
            patched = panel.copy()
            long_r, short_r, ls_r, diag = calendar_time_returns(
                patched,
                close,
                members_on=mod.get_universe_as_of,
                market_cap=None,
                half_spread=None,
                formation_start=FIRESALE_FORMATION_START,
                borrow_bps_per_year=0.0,
                weighting="equal",
                cutoffs=(lo, hi),
            )
            n = len(long_r)
            arm[label] = {
                "firesale_cutoff": lo,
                "inflow_cutoff": hi,
                "months": int(diag.n_months),
                "long_formable_months": int(diag.n_long_formable),
                "short_formable_months": int(diag.n_short_formable),
                "mean_long_size": float(np.mean(diag.long_sizes)) if diag.long_sizes else 0.0,
                "long_mean_monthly": float(long_r.mean()) if n else None,
                "long_cumulative": float((1 + long_r).prod() - 1) if n else None,
                "long_short_mean_monthly": float(ls_r.mean()) if n else None,
                "long_short_cumulative": float((1 + ls_r).prod() - 1) if n else None,
            }
            lines.append(
                f"  [{label:16s}] cutoffs ({lo:+.4f},{hi:+.4f})  "
                f"long formable {diag.n_long_formable}/{diag.n_months} months "
                f"(mean {arm[label]['mean_long_size']:.1f} names), "
                f"long net-of-market mean {arm[label]['long_mean_monthly']!s:.10s}/mo, "
                f"L/S mean {arm[label]['long_short_mean_monthly']!s:.10s}/mo"
            )
        lines.append("")
        results[universe]["arms"] = arm

    payload["universes"] = results
    payload["paper_worked_example_owners"] = PAPER_WORKED_EXAMPLE_OWNERS

    lines.append("READING THIS HONESTLY")
    lines.append("-" * 74)
    lines.append("Even at percentile-matched cutoffs this is NOT a test that could have")
    lines.append("produced a registrable edge: the percentiles are chosen on the full")
    lines.append("sample (look-ahead), the arm is un-costed, and it sits outside the")
    lines.append("pre-registered grid. It answers one question only — whether the empty")
    lines.append("sample was a property of the cutoff or of the mechanism — and that")
    lines.append("answer belongs in the 'what a future round would need' section of the")
    lines.append("results file, not in any verdict.")

    OUT_TXT.write_text("\n".join(lines) + "\n")
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
