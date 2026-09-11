#!/usr/bin/env python
"""Step 0 rule R5 helper: does adding one member raise the BOOK's power to
clear the 0.95 bar in `years` years?

Pooled Sharpe uses the BOOK pre-registration's own identity (book.py header):
    S_pool(M) = s * sqrt(M / (1 + (M - 1) * rho))
with s = assumed TRUE member Sharpe (default 0.30, the book's assumption) and
rho = mean pairwise correlation. Power comes from the existing
sourcing_power_check (no new formula). The book is ONE pre-registered object
(N = 1 in its own looks), but the DSR gate refuses n_trials < 5
(deflated_sharpe.MIN_TRIALS_FOR_DSR), so n_local = 5 is used here: a slightly
HARSHER bar than the book's real N = 1 -- disclosed, conservative direction.

Usage: book_power_gain.py --members 2 --rho 0.02 [--s 0.30] [--years 10]
Prints power for M and M+1 and the gain. NO strategy, NO return, NO DB row.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.research_lab.sourcing_power_check import sourcing_power_check

N_LOCAL_STAND_IN = 5  # book is N=1; DSR gate minimum is 5 (see docstring)


def pooled_sharpe(s: float, m: int, rho: float) -> float:
    if m <= 0:
        return 0.0
    return s * math.sqrt(m / (1.0 + (m - 1) * rho))


def power_for(m: int, s: float, rho: float, years: float, periods: float) -> float:
    sp = pooled_sharpe(s, m, rho)
    if sp <= 0:
        return 0.0
    rep = sourcing_power_check(sp, periods, years, N_LOCAL_STAND_IN, offset_fractions=(1.0,))
    return rep.power_at_smallest_fraction_at_n_local


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", type=int, required=True, help="members already counted (M)")
    ap.add_argument("--rho", type=float, required=True, help="mean pairwise correlation incl. the candidate")
    ap.add_argument("--s", type=float, default=0.30, help="assumed true member Sharpe")
    ap.add_argument("--years", type=float, default=10.0)
    ap.add_argument("--periods", type=float, default=252.0)
    a = ap.parse_args()
    rho = max(a.rho, 0.0)
    before = power_for(a.members, a.s, rho, a.years, a.periods)
    after = power_for(a.members + 1, a.s, rho, a.years, a.periods)
    out = {
        "M": a.members, "rho": rho, "s": a.s, "years": a.years,
        "pooled_sharpe_M": pooled_sharpe(a.s, a.members, rho), "pooled_sharpe_M_plus_1": pooled_sharpe(a.s, a.members + 1, rho),
        "power_M": before, "power_M_plus_1": after, "gain": after - before, "R5": after > before,
    }
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
