#!/usr/bin/env python
"""Per persisted family: the minimum TRUE annualized Sharpe the family's own
gate (0.95 and 0.50 bars, at n_local) could detect with 80% power, and the
power a true 0.5 had — from the live DB through dsr_power, so the table can
be regenerated. Claim-free (no per-family claimed Sharpe is pre-registered
for the closed families), so this is a sensitivity table, not a relabel.

Run from backend/:  python data/research_runs/criteria_fix_2026-09-09/family_min_detectable.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))

from app.db import SessionLocal
from app.models.cross_sectional_trial_result import CrossSectionalTrialResult as T
from app.services.research_lab.deflated_sharpe import MIN_TRIALS_FOR_DSR
from app.services.research_lab.dsr_power import (
    DsrPowerError,
    min_detectable_sharpe,
    power_to_pass,
)

OUT = Path(__file__).resolve().parent / "family_min_detectable.csv"


def main() -> None:
    db = SessionLocal()
    rows = db.query(T).all()
    by_fam = defaultdict(list)
    for r in rows:
        by_fam[r.family_key].append(r)
    out = []
    for fam, rs in sorted(by_fam.items()):
        latest = max(r.run_tag for r in rs)
        rr = [r for r in rs if r.run_tag == latest]
        sh = np.array([r.sharpe_annualized for r in rr], dtype=float)
        sigma = float(np.std(sh, ddof=1)) if len(sh) >= 2 else float("nan")
        n_obs = int(np.median([r.n_observations for r in rr]))
        n_tr = int(max(r.n_trials for r in rr))
        ppy = 365.0 if "crypto" in fam else 252.0
        rec = {
            "family": fam, "n_specs": len(rr), "n_trials": n_tr, "n_obs": n_obs,
            "sigma_sr": sigma, "best_sharpe": float(sh.max()),
        }
        for bar in (0.95, 0.50):
            tag = f"{bar:.2f}".replace(".", "")
            if n_tr < MIN_TRIALS_FOR_DSR or not np.isfinite(sigma):
                rec[f"mds80_{tag}"] = None
                rec[f"power_S05_{tag}"] = None
                continue
            try:
                rec[f"mds80_{tag}"] = min_detectable_sharpe(
                    threshold=bar, n_observations=n_obs, n_trials=n_tr, sigma_sr_annualized=sigma, periods_per_year=ppy
                )
                rec[f"power_S05_{tag}"] = power_to_pass(
                    true_sharpe_annualized=0.5, threshold=bar, n_observations=n_obs, n_trials=n_tr,
                    sigma_sr_annualized=sigma, periods_per_year=ppy,
                )
            except DsrPowerError as exc:
                rec[f"mds80_{tag}"] = None
                rec[f"power_S05_{tag}"] = None
                rec["note"] = str(exc)[:80]
        out.append(rec)
    df = pd.DataFrame(out)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    print(df.round(3).to_string(index=False))
    df.to_csv(OUT, index=False)
    ok = df.dropna(subset=["mds80_095"])
    print()
    print(f"families scored at 0.95: {len(ok)}; median min-detectable Sharpe (80% power) = {ok['mds80_095'].median():.2f}; "
          f"median power at a true 0.5 = {ok['power_S05_095'].median():.2f}; "
          f"families where a true 0.5 had >= 80% power at 0.95: {(ok['power_S05_095'] >= 0.8).sum()}")
    ok5 = df.dropna(subset=["mds80_050"])
    print(f"at the 0.50 floor: median min-detectable = {ok5['mds80_050'].median():.2f}; median power at true 0.5 = {ok5['power_S05_050'].median():.2f}")


if __name__ == "__main__":
    main()
