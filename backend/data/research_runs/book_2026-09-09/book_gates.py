#!/usr/bin/env python
"""Pre-registered book — gates GB1-GB4 exactly as declared in
BOOK_PREREGISTRATION.md (read that first). Uses the Dormant pool's committed
LOW boundary and look schedule unchanged; nothing is recalibrated unless a
gate fails.

Run from backend/:  python data/research_runs/book_2026-09-09/book_gates.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import kurtosis, norm, skew

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))

from app.services.research_lab.dormant_pool import BUCKET_LOW, C_K, K_MAX

PPY = 252
ALPHA = 0.05
C_LOW = C_K[BUCKET_LOW]
SEED = 20260910
REPS = 3000


def psr_path(x: np.ndarray) -> np.ndarray:
    out = np.empty((x.shape[0], K_MAX))
    for k in range(1, K_MAX + 1):
        seg = x[:, : k * PPY]
        n = seg.shape[1]
        sr = seg.mean(axis=1) / seg.std(axis=1, ddof=1)
        sk = skew(seg, axis=1, bias=True)
        ku = kurtosis(seg, axis=1, fisher=False, bias=True)
        denom = 1 - sk * sr + ((ku - 1) / 4) * sr**2
        z = sr * np.sqrt(n - 1) / np.sqrt(np.where(denom > 0, denom, np.nan))
        out[:, k - 1] = norm.cdf(z)
    return out


def promoted_within(p: np.ndarray, c: float) -> np.ndarray:
    hit = p >= c
    first = np.argmax(hit, axis=1) + 1
    return np.where(hit.any(axis=1), first, 0)


def members(rng, reps: int, m: int, n: int, s_annual: np.ndarray, rho: float) -> np.ndarray:
    """(reps, m, n) daily member returns, unit variance, one common factor
    giving pairwise correlation rho, per-member true annualized Sharpe s."""
    s = s_annual / np.sqrt(PPY)
    f = rng.standard_normal((reps, 1, n)) * np.sqrt(rho)
    e = rng.standard_normal((reps, m, n)) * np.sqrt(1 - rho)
    return f + e + s[None, :, None]


def book(x: np.ndarray) -> np.ndarray:
    return x.mean(axis=1)


def rate(looks: np.ndarray) -> tuple[float, float]:
    r = float((looks > 0).mean())
    return r, float(np.sqrt(r * (1 - r) / len(looks)))


def main() -> int:
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    n = K_MAX * PPY
    print(f"book gates: LOW boundary C_K={C_LOW:.5f} (dormant_pool.C_K), K_MAX={K_MAX}, reps={REPS}, seed={SEED}")
    ok_all = True

    print("\n== GB1: null members, correlated — per-book false promotion over 10 looks")
    for m in (10, 30, 50):
        for rho in (0.0, 0.05, 0.2, 0.5):
            x = members(rng, REPS, m, n, np.zeros(m), rho)
            r, se = rate(promoted_within(psr_path(book(x)), C_LOW))
            ok = r <= ALPHA + 2 * se
            ok_all &= ok
            print(f"   M={m:>2} rho={rho:.2f}: {r:.4f} (se {se:.4f}) -> {'PASS' if ok else 'FAIL'}")

    print("\n== GB2: in-sample-selected null members (the option-D trap), scored only after inception")
    pool, admit, pre_years = 200, 30, 5
    reps2 = 1500
    hits = 0
    for _ in range(reps2):
        x = members(rng, 1, pool, (pre_years + K_MAX) * PPY, np.zeros(pool), 0.05)[0]
        pre = x[:, : pre_years * PPY]
        insample_sr = pre.mean(axis=1) / pre.std(axis=1, ddof=1)
        chosen = np.argsort(insample_sr)[-admit:]
        post = x[chosen, pre_years * PPY :].mean(axis=0)[None, :]
        hits += int(promoted_within(psr_path(post), C_LOW)[0] > 0)
    r2 = hits / reps2
    se2 = float(np.sqrt(r2 * (1 - r2) / reps2))
    ok2 = r2 <= ALPHA + 2 * se2
    ok_all &= ok2
    # and the trap itself, for contrast: score the SAME selected book on its in-sample window
    print(f"   post-inception false promotion = {r2:.4f} (se {se2:.4f}) -> {'PASS' if ok2 else 'FAIL'}")
    x = members(rng, 300, pool, pre_years * PPY, np.zeros(pool), 0.05)
    sr_in = x.mean(axis=2) / x.std(axis=2, ddof=1)
    trap = []
    for i in range(300):
        chosen = np.argsort(sr_in[i])[-admit:]
        b = x[i, chosen].mean(axis=0)
        trap.append(b.mean() / b.std(ddof=1) * np.sqrt(PPY))
    print(f"   (contrast: the same selected-in-sample book's IN-SAMPLE annualized Sharpe averages {np.mean(trap):.2f} "
          f"with zero true edge — that is what option D would have scored)")

    print("\n== GB3: power — P(book promoted within 10y) [median year among promoted]")
    for s in (0.2, 0.3, 0.5):
        row = []
        for m in (10, 30, 50):
            for rho in (0.0, 0.05, 0.2):
                x = members(rng, 1500, m, n, np.full(m, s), rho)
                looks = promoted_within(psr_path(book(x)), C_LOW)
                p = float((looks > 0).mean())
                med = int(np.median(looks[looks > 0])) if (looks > 0).any() else 0
                row.append(f"M={m},rho={rho:.2f}: {p:.2f}[{med}y]")
        print(f"   s={s:.1f}: " + "  ".join(row))

    print("\n== GB4: dilution — M=30, rho=0.05, true members at s=0.3, the rest null")
    for null_frac in (0.0, 0.5, 0.8):
        m = 30
        s_vec = np.where(np.arange(m) < int(round(m * (1 - null_frac))), 0.3, 0.0)
        x = members(rng, 1500, m, n, s_vec, 0.05)
        looks = promoted_within(psr_path(book(x)), C_LOW)
        p = float((looks > 0).mean())
        med = int(np.median(looks[looks > 0])) if (looks > 0).any() else 0
        print(f"   null fraction {null_frac:.0%}: promoted within 10y = {p:.2f} [median {med}y]")

    print(f"\nelapsed {time.time() - t0:.0f}s")
    print("OVERALL:", "ALL GATES PASS" if ok_all else "A GATE FAILED — see above; do not build")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
