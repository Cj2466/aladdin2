#!/usr/bin/env python
"""Dormant pool — boundary calibration and gates G1-G4, exactly as
pre-registered in DORMANT_POOL_PREREGISTRATION.md (read that first; the
pass criteria live there, not here).

Look structure: looks at k*252 cumulative extension observations, k=1..K_MAX.
Statistic at each look: PSR_ext = probabilistic_sharpe_ratio(SR, 0, n, skew,
kurt) on the CUMULATIVE extension (the project's own function, as-is).
Promotion at the first look with PSR_ext >= C_K. C_K is the empirical
(1-ALPHA) quantile of max_k PSR_ext,k under i.i.d. normal null, calibration
seed 20260909; every gate then uses a DIFFERENT seed.

Run from backend/:  python data/research_runs/dormant_pool_2026-09-09/dormant_pool_gates.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import kurtosis, skew

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))

from app.services.research_lab.deflated_sharpe import (
    probabilistic_sharpe_ratio,
)

PPY = 252
K_MAX = 10
ALPHA = 0.05
CAL_PATHS = 20_000
CAL_SEED = 20260909
GATE_SEED = 777
N_FAMILIES = 50
GATE_REPS_PER_FAMILY = 400  # 50 families x 400 = 20 000 null paths per gate


def psr_path(x: np.ndarray) -> np.ndarray:
    """PSR_ext at each look k on the cumulative first k*PPY observations.
    Vectorised over paths: x is (paths, K_MAX*PPY)."""
    out = np.empty((x.shape[0], K_MAX))
    for k in range(1, K_MAX + 1):
        seg = x[:, : k * PPY]
        n = seg.shape[1]
        mean = seg.mean(axis=1)
        sd = seg.std(axis=1, ddof=1)
        sr = mean / sd
        sk = skew(seg, axis=1, bias=True)
        ku = kurtosis(seg, axis=1, fisher=False, bias=True)
        # same guard/arithmetic as probabilistic_sharpe_ratio, vectorised for
        # speed; spot-checked against the scalar function below
        denom = 1 - sk * sr + ((ku - 1) / 4) * sr**2
        z = (sr - 0.0) * np.sqrt(n - 1) / np.sqrt(np.where(denom > 0, denom, np.nan))
        from scipy.stats import norm

        out[:, k - 1] = norm.cdf(z)
    return out


def spot_check(rng):
    x = rng.standard_normal(3 * PPY)
    vec = psr_path(x[None, :])[0, 2]
    scalar = probabilistic_sharpe_ratio(
        float(x.mean() / x.std(ddof=1)), 0.0, len(x), float(skew(x, bias=True)), float(kurtosis(x, fisher=False, bias=True))
    )
    assert abs(vec - scalar) < 1e-12, (vec, scalar)


def gen(rng, model: str, true_sharpe_annual: float, paths: int) -> np.ndarray:
    """model: 'normal', 't4', or 'ar1:<phi>' (e.g. 'ar1:0.1')."""
    n = K_MAX * PPY
    s = true_sharpe_annual / np.sqrt(PPY)
    if model == "normal":
        x = rng.standard_normal((paths, n))
    elif model == "t4":
        x = rng.standard_t(4, (paths, n)) / np.sqrt(2.0)  # unit variance
    elif model.startswith("ar1"):
        phi = float(model.split(":")[1]) if ":" in model else 0.3
        e = rng.standard_normal((paths, n)) * np.sqrt(1 - phi**2)
        x = np.empty((paths, n))
        x[:, 0] = rng.standard_normal(paths)
        for t in range(1, n):
            x[:, t] = phi * x[:, t - 1] + e[:, t]
    else:
        raise ValueError(model)
    return x + s


def promotion_look(p: np.ndarray, c: float) -> np.ndarray:
    """First look index (1-based) at which PSR >= c, or 0 if never."""
    hit = p >= c
    first = np.argmax(hit, axis=1) + 1
    return np.where(hit.any(axis=1), first, 0)


def main() -> int:
    t0 = time.time()
    rng = np.random.default_rng(CAL_SEED)
    spot_check(rng)

    # --- calibration ---------------------------------------------------------
    # FIRST RUN (recorded in dormant_pool_gates_output.txt, run 1): the
    # boundary calibrated under i.i.d. normal (0.98865) passed G1 and G2a but
    # FAILED G2b — AR(1) phi=0.3 daily returns gave a 0.1661 false-promotion
    # rate, because PSR's variance term assumes independence and positive
    # autocorrelation shrinks the effective sample. Per the pre-registration
    # (section 5, G2): "the boundary is recalibrated under the worse model and
    # G1 re-run, and that is recorded." So C_K is now the MAX of the three
    # models' (1-ALPHA) quantiles — i.e. calibrated under the model that
    # inflates it most — and every gate below runs against that one value.
    # RUN 3 (DORMANT_POOL_AMENDMENT_1.md): two pre-declared buckets chosen at
    # entry from the family's ORIGINAL-window lag-1 autocorrelation. Measured
    # on the 481 persisted spec series: 95th percentile 0.070, max 0.247,
    # none >= 0.3. LOW (phi_hat <= 0.10) is calibrated as the max over normal
    # / t4 / AR(1) 0.10; HIGH (phi_hat > 0.10) keeps run 2's AR(1) 0.30 value.
    print(f"calibration ({CAL_PATHS} null paths per model, seed {CAL_SEED}): K_MAX={K_MAX}, ALPHA={ALPHA}")
    c_by_model = {}
    for model in ("normal", "t4", "ar1:0.1", "ar1:0.3"):
        p = psr_path(gen(rng, model, 0.0, CAL_PATHS))
        c_by_model[model] = float(np.quantile(p.max(axis=1), 1 - ALPHA))
        if model == "normal":
            per_look_naive = float((p[:, -1] >= 0.95).mean())
            any_look_naive = float((p >= 0.95).any(axis=1).mean())
        print(f"  (1-ALPHA) quantile of max_k PSR under {model:<8} = {c_by_model[model]:.5f}")
    buckets = {
        "LOW (phi_hat <= 0.10)": max(c_by_model[m] for m in ("normal", "t4", "ar1:0.1")),
        "HIGH (phi_hat > 0.10)": c_by_model["ar1:0.3"],
    }
    for b, c in buckets.items():
        print(f"  boundary C_K[{b}] = {c:.5f}")
    print(f"  for contrast, a naive fixed 0.95 bar looked at every year (normal): FWER = {any_look_naive:.4f} "
          f"(single final look {per_look_naive:.4f})")

    # --- gates per bucket ------------------------------------------------------
    grng = np.random.default_rng(GATE_SEED)
    results = {}
    gate_plan = {
        "LOW (phi_hat <= 0.10)": (
            ("G1 normal", "normal", ALPHA, True),
            ("G2a t4", "t4", 0.07, True),
            ("G2b ar1 phi=0.1 (bucket contract)", "ar1:0.1", 0.07, True),
            ("stress ar1 phi=0.3 (outside bucket, disclosed)", "ar1:0.3", None, False),
        ),
        "HIGH (phi_hat > 0.10)": (
            ("G2b ar1 phi=0.3", "ar1:0.3", 0.07, True),
        ),
    }
    for bucket, c_k in buckets.items():
        print(f"\n== bucket {bucket}, C_K = {c_k:.5f}")
        for label, model, crit, gating in gate_plan[bucket]:
            x = gen(grng, model, 0.0, N_FAMILIES * GATE_REPS_PER_FAMILY)
            looks = promotion_look(psr_path(x), c_k)
            rate = float((looks > 0).mean())
            se = float(np.sqrt(rate * (1 - rate) / len(looks)))
            if gating:
                tol = crit + (2 * se if label.startswith("G1") else 0.0)
                ok = rate <= tol
                results[f"{bucket}/{label}"] = ok
                print(f"  {label}: per-family false promotion over {K_MAX} looks = {rate:.4f} (se {se:.4f}) "
                      f"vs criterion {tol:.4f} -> {'PASS' if ok else 'FAIL'}")
            else:
                print(f"  {label}: {rate:.4f} (se {se:.4f}) — not a gate for this bucket; a family here belongs in HIGH")
        null_rate = float((promotion_look(psr_path(gen(grng, "normal", 0.0, 4000)), c_k) > 0).mean())
        print(f"  G4: with {N_FAMILIES} null Dormant families in this bucket, expected false promotions over "
              f"{K_MAX} years = {N_FAMILIES * null_rate:.1f} (forward-tracking slots, not capital)")
        print("  G3 (power, informational): years of NEW data until promotion")
        for s in (0.5, 0.8, 1.0):
            looks = promotion_look(psr_path(gen(grng, "normal", s, 4000)), c_k)
            promoted = looks[looks > 0]
            frac = len(promoted) / len(looks)
            med = np.median(promoted) if len(promoted) else float("nan")
            by = {k: float((looks[(looks > 0)] <= k).sum() / len(looks)) for k in (1, 2, 3, 5, 10)}
            print(f"    true annual Sharpe {s:.1f}: promoted within {K_MAX}y = {frac:.3f}; median look among promoted = {med:.0f}; "
                  f"P(promoted by year) " + ", ".join(f"{k}y:{v:.2f}" for k, v in by.items()))

    print(f"\nelapsed {time.time() - t0:.0f}s")
    all_ok = all(results.values())
    print("OVERALL:", "ALL GATES PASS" if all_ok else "A GATE FAILED — see above; do not build")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
