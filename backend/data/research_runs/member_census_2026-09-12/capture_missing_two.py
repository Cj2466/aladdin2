#!/usr/bin/env python
"""Capture the frozen-spec net daily return series of the two BOOK members that
are absent from global_effective_n_return_matrix_2026-09-05 (both families
were built after that run): rebalancing_pressure/rebal_threshold_scaled_h1 and
dividend_payment_pressure/divpay_raw_payment_top10. Uses the Dormant
re-scorer's own capture path (run_family_and_capture) unchanged, so the
series are the same ones a scheduled look would score. Output: one CSV per
family with every captured spec, written next to this script.

dividend_payment_pressure needs data/dividend_payment_calendar.json (gitignored,
resolved per worktree). On 2026-09-12 the worktree had none and the family
replayed 0 specs; the MAIN checkout's 2026-09-09 file was copied in unchanged
(SHA-256 be87cd4f...) and the run repeated -> 34 specs x 2,180 days.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "data" / "research_runs"))
spec = importlib.util.spec_from_file_location(
    "dormant_rescore", BACKEND / "data/research_runs/dormant_pool_2026-09-09/dormant_rescore.py"
)
dr = importlib.util.module_from_spec(spec)
sys.modules["dormant_rescore"] = dr
assert spec.loader is not None
spec.loader.exec_module(dr)

import pandas as pd

END = date(2026, 9, 5)  # match the matrix run's data end so overlaps are comparable
for family in ("rebalancing_pressure", "dividend_payment_pressure"):
    try:
        captured = dr.run_family_and_capture(family, END)
    except Exception as exc:  # noqa: BLE001 - record the failure, keep going
        print(f"{family}: FAILED {type(exc).__name__}: {exc}")
        continue
    df = pd.DataFrame(captured)
    out = HERE / f"captured_{family}_{END.isoformat()}.csv"
    df.to_csv(out)
    print(f"{family}: {df.shape[1]} specs x {df.shape[0]} days -> {out.name}; columns={sorted(df.columns)[:40]}")
