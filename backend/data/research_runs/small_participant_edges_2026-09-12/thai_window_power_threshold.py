#!/usr/bin/env python
"""Admissibility threshold on the THAI free-data window, using the project's existing
sourcing_power_check (no new formula, no new rung).  Binary search for the smallest
claimed net annualized Sharpe that returns PROCEED at 252 periods/yr.

Control: the US equity window (10.683 y, n_local=8) must reproduce 2.416, the number
already recorded in DECLINED_AT_SOURCING.md; it does.
"""
from app.services.research_lab.sourcing_power_check import sourcing_power_check

YEARS_TH = 26.69   # Yahoo .BK mass history start 2000-01-04 -> 2026-09-11, measured today


def threshold(years, n_local, lo=0.2, hi=5.0, iters=40):
    for _ in range(iters):
        mid = (lo + hi) / 2
        r = sourcing_power_check(mid, 252.0, years, n_local)
        if r.verdict.upper().startswith("PROCEED"):
            hi = mid
        else:
            lo = mid
    return hi


if __name__ == "__main__":
    for n in (5, 8, 16):
        print(f"Thai {YEARS_TH}y  n_local={n}: min claimed net Sharpe for PROCEED = {threshold(YEARS_TH, n):.3f}")
    print(f"US control 10.683y n_local=8: {threshold(10.683, 8):.3f}")
