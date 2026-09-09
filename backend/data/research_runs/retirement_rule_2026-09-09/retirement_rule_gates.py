#!/usr/bin/env python
"""Forward-retirement rule — boundary calibration and gates R1-R5, exactly as
pre-registered in RETIREMENT_RULE_PREREGISTRATION.md (read that first; the
pass criteria live there, not here).

Three statistics on daily standardized net returns z_t = r_t / sigma_hat_t
(expanding-sample sd), monitored DAILY from MIN_DAYS on, over a horizon H:
  S-A  whole-record PSR vs 0 (the project's own PSR arithmetic)  -> trigger PSR <= L
  S-B  SPRT   Lambda_t = sum l_i                                   -> trigger >= B
  S-C  CUSUM  C_t = max(0, C_{t-1} + l_t)                          -> trigger >= h
with l_t = d (z_t - m), d = (s1 - s0)/sqrt(252), m = (s1 + s0)/(2 sqrt(252)).
Every boundary is the simulated alpha-quantile of the path extreme under the
PROTECT truth s0 (not Wald's approximation).

Run from backend/:  python data/research_runs/retirement_rule_2026-09-09/retirement_rule_gates.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import kurtosis, norm, skew

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))

from app.services.research_lab.deflated_sharpe import probabilistic_sharpe_ratio  # noqa: E402

PPY = 252
H_YEARS = 5
H = H_YEARS * PPY
H10 = 10 * PPY
MIN_DAYS = 60  # UNDERPERFORMANCE_LOOKBACK_TRADING_DAYS, unchanged
ALPHA = 0.05
S1 = -1.0  # harm level the statistic is designed against
CAL_PATHS = 20_000
CAL_SEED = 20260909
GATE_SEED = 777
GATE_PATHS = 20_000
CHUNK = 4_000
OLD_RULE_LOOKBACK = 60
OLD_RULE_THRESHOLD = -0.5
STATS = ("S-A PSR floor", "S-B SPRT", "S-C CUSUM")


# --- return generators (same three models as the Dormant pool) --------------


def gen(rng, model: str, true_sharpe_annual: float, paths: int, n: int) -> np.ndarray:
    s = true_sharpe_annual / np.sqrt(PPY)
    if model == "normal":
        x = rng.standard_normal((paths, n))
    elif model == "t4":
        x = rng.standard_t(4, (paths, n)) / np.sqrt(2.0)
    elif model.startswith("ar1"):
        phi = float(model.split(":")[1])
        e = rng.standard_normal((paths, n)) * np.sqrt(1 - phi**2)
        x = np.empty((paths, n))
        x[:, 0] = rng.standard_normal(paths)
        for t in range(1, n):
            x[:, t] = phi * x[:, t - 1] + e[:, t]
    else:
        raise ValueError(model)
    return x + s


def gen_decay(rng, paths: int, n: int, change: int, s_before: float, s_after: float) -> np.ndarray:
    x = rng.standard_normal((paths, n))
    x[:, :change] += s_before / np.sqrt(PPY)
    x[:, change:] += s_after / np.sqrt(PPY)
    return x


# --- statistics along the path (vectorised over paths) ----------------------


def running_moments(r: np.ndarray):
    """Expanding-sample mean, sd (ddof=1), biased skew and non-Fisher kurtosis
    at every t, from cumulative power sums. Returns arrays shaped like r."""
    t = np.arange(1, r.shape[1] + 1, dtype=float)
    m1 = np.cumsum(r, axis=1) / t
    m2 = np.cumsum(r**2, axis=1) / t
    m3 = np.cumsum(r**3, axis=1) / t
    m4 = np.cumsum(r**4, axis=1) / t
    var = m2 - m1**2
    mu3 = m3 - 3 * m1 * m2 + 2 * m1**3
    mu4 = m4 - 4 * m1 * m3 + 6 * m1**2 * m2 - 3 * m1**4
    with np.errstate(divide="ignore", invalid="ignore"):
        sd1 = np.sqrt(var * t / (t - 1))
        sk = mu3 / var**1.5
        ku = mu4 / var**2
    return m1, sd1, sk, ku, t


def psr_along(r: np.ndarray) -> np.ndarray:
    m1, sd1, sk, ku, t = running_moments(r)
    with np.errstate(divide="ignore", invalid="ignore"):
        sr = m1 / sd1
        denom = 1 - sk * sr + ((ku - 1) / 4) * sr**2
        z = sr * np.sqrt(t - 1) / np.sqrt(np.where(denom > 0, denom, np.nan))
    p = norm.cdf(z)
    p[:, : MIN_DAYS - 1] = np.nan
    return p


def llr_along(r: np.ndarray, s0: float, s1: float) -> np.ndarray:
    m1, sd1, _, _, _ = running_moments(r)
    d = (s1 - s0) / np.sqrt(PPY)
    m = (s1 + s0) / (2 * np.sqrt(PPY))
    with np.errstate(divide="ignore", invalid="ignore"):
        z = r / sd1
    z[:, 0] = 0.0  # sd undefined at t=1; contributes nothing
    return d * (z - m)


def sprt_along(l: np.ndarray) -> np.ndarray:
    return np.cumsum(l, axis=1)


def cusum_along(l: np.ndarray) -> np.ndarray:
    c = np.zeros_like(l)
    prev = np.zeros(l.shape[0])
    for t in range(l.shape[1]):
        prev = np.maximum(0.0, prev + l[:, t])
        c[:, t] = prev
    return c


def old_rule_along(r: np.ndarray) -> np.ndarray:
    """Trailing OLD_RULE_LOOKBACK-day annualized Sharpe <= threshold, as
    forward_validation_service.check_underperformance did."""
    n = r.shape[1]
    out = np.zeros_like(r, dtype=bool)
    cs = np.cumsum(r, axis=1)
    cs2 = np.cumsum(r**2, axis=1)
    L = OLD_RULE_LOOKBACK
    for t in range(L - 1, n):
        lo = t - L
        s = cs[:, t] - (cs[:, lo] if lo >= 0 else 0.0)
        s2 = cs2[:, t] - (cs2[:, lo] if lo >= 0 else 0.0)
        mean = s / L
        var = (s2 - L * mean**2) / (L - 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sharpe = mean / np.sqrt(var) * np.sqrt(PPY)
        out[:, t] = sharpe <= OLD_RULE_THRESHOLD
    return out


def stats_along(r: np.ndarray, s0: float) -> dict[str, np.ndarray]:
    l = llr_along(r, s0, S1)
    return {"S-A PSR floor": psr_along(r), "S-B SPRT": sprt_along(l), "S-C CUSUM": cusum_along(l)}


def first_trigger(stat: np.ndarray, boundary: float, name: str, horizon: int) -> np.ndarray:
    """First day index (1-based) within `horizon` at which the trigger fires
    (from MIN_DAYS on), or 0 if never."""
    seg = stat[:, :horizon]
    hit = (seg <= boundary) if name.startswith("S-A") else (seg >= boundary)
    hit[:, : MIN_DAYS - 1] = False
    hit = np.nan_to_num(hit, nan=False)
    first = np.argmax(hit, axis=1) + 1
    return np.where(hit.any(axis=1), first, 0)


def extremes(stat: np.ndarray, name: str, horizon: int) -> np.ndarray:
    seg = stat[:, MIN_DAYS - 1 : horizon]
    return np.nanmin(seg, axis=1) if name.startswith("S-A") else np.nanmax(seg, axis=1)


# --- self checks ------------------------------------------------------------


def spot_checks(rng):
    x = rng.standard_normal((1, 400))
    p = psr_along(x)[0, 299]
    seg = x[0, :300]
    scalar = probabilistic_sharpe_ratio(
        float(seg.mean() / seg.std(ddof=1)), 0.0, 300, float(skew(seg, bias=True)), float(kurtosis(seg, fisher=False, bias=True))
    )
    assert abs(p - scalar) < 1e-9, (p, scalar)
    # CUSUM known answer: constant increments +a from a reset accumulate linearly,
    # constant -a stay at zero
    l = np.full((1, 10), 0.3)
    assert np.allclose(cusum_along(l)[0], 0.3 * np.arange(1, 11))
    assert np.all(cusum_along(-l) == 0.0)
    # SPRT known answer: cumulative sum
    assert np.allclose(sprt_along(l)[0], 0.3 * np.arange(1, 11))
    # old rule: a 60-day block of -1 daily (sd 0 -> inf) never divides by zero
    r = np.concatenate([np.ones((1, 60)) * -0.01 + np.linspace(0, 1e-4, 60)[None, :], np.zeros((1, 5))], axis=1)
    old_rule_along(r)


# --- calibration and gates ---------------------------------------------------


def calibrate(rng, s0: float, models: tuple[str, ...]) -> dict[str, dict[str, float]]:
    """(per model) alpha-quantile of min PSR / (1-alpha) quantile of max SPRT
    and CUSUM over the first H days under truth s0."""
    out: dict[str, dict[str, float]] = {}
    for model in models:
        ext = {s: [] for s in STATS}
        for _ in range(CAL_PATHS // CHUNK):
            r = gen(rng, model, s0, CHUNK, H)
            st = stats_along(r, s0)
            for s in STATS:
                ext[s].append(extremes(st[s], s, H))
        out[model] = {}
        for s in STATS:
            e = np.concatenate(ext[s])
            out[model][s] = float(np.quantile(e, ALPHA) if s.startswith("S-A") else np.quantile(e, 1 - ALPHA))
    return out


def bucket_boundaries(cal: dict[str, dict[str, float]], models: tuple[str, ...]) -> dict[str, float]:
    """Worst case across the bucket's models: LOWEST L for S-A, HIGHEST B / h."""
    b = {}
    for s in STATS:
        vals = [cal[m][s] for m in models]
        b[s] = min(vals) if s.startswith("S-A") else max(vals)
    return b


def trigger_rate(rng, model: str, s_true: float, s0: float, bounds: dict[str, float], horizon: int, paths: int,
                 decay: tuple[int, float, float] | None = None):
    """P(trigger within horizon) per statistic, plus the trigger days."""
    days = {s: [] for s in STATS}
    dd_at = {s: [] for s in STATS}
    for _ in range(max(1, paths // CHUNK)):
        n = min(paths, CHUNK)
        if decay is None:
            r = gen(rng, model, s_true, n, horizon)
        else:
            r = gen_decay(rng, n, horizon, *decay)
        st = stats_along(r, s0)
        eq = np.cumsum(r, axis=1)
        peak = np.maximum.accumulate(eq, axis=1)
        dd = (peak - eq) / np.sqrt(PPY)  # in annual-vol units
        for s in STATS:
            f = first_trigger(st[s], bounds[s], s, horizon)
            days[s].append(f)
            dd_at[s].append(np.where(f > 0, dd[np.arange(n), np.maximum(f - 1, 0)], np.nan))
    return {s: np.concatenate(days[s]) for s in STATS}, {s: np.concatenate(dd_at[s]) for s in STATS}


def main() -> int:
    t0 = time.time()
    rng = np.random.default_rng(CAL_SEED)
    spot_checks(rng)
    grng = np.random.default_rng(GATE_SEED)
    results: dict[str, bool] = {}
    selection: dict[str, float] = {}

    low_models = ("normal", "t4", "ar1:0.1")
    high_models = ("ar1:0.3",)

    for s0 in (0.5, 1.0):
        primary = s0 == 0.5
        print(f"\n{'=' * 78}\nPROTECT s0 = {s0}  {'(PRIMARY, gating)' if primary else '(alternative for the owner, informational)'}"
              f"   harm s1 = {S1}, alpha = {ALPHA}, H = {H_YEARS}y, daily monitoring from day {MIN_DAYS}")
        cal = calibrate(rng, s0, low_models + high_models)
        for m in low_models + high_models:
            print(f"  calibration under {m:<8}: " + ", ".join(f"{s}: {cal[m][s]:.4f}" for s in STATS))
        buckets = {"LOW (phi_hat <= 0.10)": bucket_boundaries(cal, low_models),
                   "HIGH (phi_hat > 0.10)": bucket_boundaries(cal, high_models)}
        for b, bounds in buckets.items():
            print(f"  boundaries {b}: " + ", ".join(f"{s}: {bounds[s]:.4f}" for s in STATS))

        for bucket, bounds in buckets.items():
            print(f"\n-- bucket {bucket}")
            contract = low_models if bucket.startswith("LOW") else high_models
            # R1
            for m in contract:
                days, _ = trigger_rate(grng, m, s0, s0, bounds, H, GATE_PATHS)
                for s in STATS:
                    rate = float((days[s] > 0).mean())
                    se = float(np.sqrt(rate * (1 - rate) / len(days[s])))
                    crit = ALPHA + 2 * se if m == "normal" or bucket.startswith("HIGH") else 0.07
                    ok = rate <= crit
                    if primary:
                        results[f"{bucket}/R1 {m}/{s}"] = ok
                    print(f"  R1 protect s={s0} under {m:<8} {s:<14}: P(trigger within {H_YEARS}y) = {rate:.4f} (se {se:.4f}) "
                          f"vs {crit:.4f} -> {'PASS' if ok else 'FAIL'}")
            # R2
            days, dd = trigger_rate(grng, "normal", S1, s0, bounds, H, GATE_PATHS)
            for s in STATS:
                rate = float((days[s] > 0).mean())
                ok = rate >= 0.80
                if primary:
                    results[f"{bucket}/R2/{s}"] = ok
                med = np.median(days[s][days[s] > 0]) / PPY if (days[s] > 0).any() else float("nan")
                print(f"  R2 catch s={S1} {s:<14}: P(trigger within {H_YEARS}y) = {rate:.4f}; median trigger {med:.2f}y; "
                      f"median drawdown at trigger {np.nanmedian(dd[s]):.2f} annual-vol units -> {'PASS' if ok else 'FAIL'}")
            if not bucket.startswith("LOW"):
                continue
            # R3 decay (LOW bucket, normal): 1.0 for 2y then -1.0
            change = 2 * PPY
            days, _ = trigger_rate(grng, "normal", 0.0, s0, bounds, H, GATE_PATHS, decay=(change, 1.0, S1))
            for s in STATS:
                d = days[s]
                pre = float(((d > 0) & (d <= change)).mean())
                post = d[d > change] - change
                caught = float((d > change).mean())
                med = np.median(post) / PPY if len(post) else float("nan")
                p80 = np.quantile(post, 0.8) / PPY if len(post) else float("nan")
                if primary:
                    selection[s] = med if (results.get(f"{bucket}/R2/{s}", False) and all(
                        v for k, v in results.items() if k.startswith(f"{bucket}/R1") and k.endswith(s))) else float("inf")
                print(f"  R3 decay (1.0 for 2y, then {S1}) {s:<14}: P(false trigger before change) = {pre:.4f}; "
                      f"P(caught within {H_YEARS}y) = {caught:.4f}; delay after change median {med:.2f}y, 80th pct {p80:.2f}y")
            # R4 operating characteristic
            print(f"  R4 operating characteristic (normal), P(trigger by year) and, for negatives, median drawdown at trigger")
            for s_true in (1.0, 0.5, 0.3, 0.0, -0.3, -0.5, -1.0):
                days, dd = trigger_rate(grng, "normal", s_true, s0, bounds, H10, 4000)
                for s in STATS:
                    d = days[s]
                    by = ", ".join(f"{y}y:{float(((d > 0) & (d <= y * PPY)).mean()):.2f}" for y in (1, 2, 3, 5, 10))
                    ddtxt = f"; DD@trigger median {np.nanmedian(dd[s]):.2f} vol-units" if s_true < 0 else ""
                    print(f"    s={s_true:+.1f} {s:<14}: {by}{ddtxt}")
            print(f"  with N live registrations the expected number of wrong retirement recommendations over {H_YEARS}y is N x {ALPHA}")

    # R5 the retired rule, reproduced in this harness
    print(f"\n{'=' * 78}\nR5 the retired trailing-{OLD_RULE_LOOKBACK}d Sharpe <= {OLD_RULE_THRESHOLD} rule (normal)")
    for s_true in (1.0, 0.5, 0.0):
        r = gen(grng, "normal", s_true, 12_000, 3 * PPY)
        hit = old_rule_along(r)
        by = {y: float(hit[:, : y * PPY].any(axis=1).mean()) for y in (1, 2, 3)}
        print(f"  true Sharpe {s_true:+.1f}: P(parked by 1y) {by[1]:.3f}, 2y {by[2]:.3f}, 3y {by[3]:.3f}")
    r5_ok = None
    r = gen(grng, "normal", 1.0, 12_000, 3 * PPY)
    k3 = float(old_rule_along(r).any(axis=1).mean())
    r5_ok = 0.55 <= k3 <= 0.80
    results["R5 harness reproduces the criteria-audit measurement (kills true 1.0 ~2 in 3 within 3y)"] = r5_ok
    print(f"  harness check: kills true 1.0 within 3y = {k3:.3f} -> {'consistent' if r5_ok else 'NOT consistent — harness suspect'}")

    # selection
    print(f"\n{'=' * 78}\nSELECTION (pre-declared: shortest median R3 delay among statistics passing R1 and R2 in the LOW bucket at s0=0.5)")
    for s in STATS:
        print(f"  {s:<14}: {'ineligible (failed R1 or R2)' if selection.get(s, float('inf')) == float('inf') else f'median decay delay {selection[s]:.2f}y'}")
    eligible = {s: v for s, v in selection.items() if v != float("inf")}
    if eligible:
        best = min(eligible.values())
        tied = [s for s in ("S-A PSR floor", "S-C CUSUM", "S-B SPRT") if s in eligible and eligible[s] <= best + 0.05]
        print(f"  ADOPT: {tied[0]} (ties within 0.05y resolved in the order S-A, S-C, S-B: {tied})")
    else:
        print("  ADOPT: nothing — no statistic passes R1 and R2 at s0 = 0.5; see the pre-registration, section 4 R2")

    print(f"\nelapsed {time.time() - t0:.0f}s")
    failed = [k for k, v in results.items() if not v]
    print("GATES:", "ALL PASS" if not failed else f"FAILED: {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
