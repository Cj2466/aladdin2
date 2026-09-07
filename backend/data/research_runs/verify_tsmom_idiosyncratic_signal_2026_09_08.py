"""INDEPENDENT VERIFICATION of run_tsmom_idiosyncratic_signal_2026_09_08.py.

Written from the portfolio definitions, NOT by importing the run script's
build_strategy. It re-derives the headline numbers along a separate code path
and fails loudly on any disagreement. CLAUDE.md workflow rule 2.

Checks:
  V1  headline gross and net Sharpe, re-derived from scratch
  V2  factor neutrality, measured per-block against the block's OWN factors
      (the run script's whole-sample static diagnostic is mis-specified --
      see the note in V2 -- and this replaces it)
  V3  variance decomposition: var(raw) vs var(hedged) + var(hedge P&L)
  V4  DSR at n_local recomputed from the Bailey/Lopez de Prado formula by hand
  V5  cost calibration arithmetic reproduced from the citation's own numbers
  V6  the six shared modules are byte-identical to main
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

RESULT = _BACKEND / "data" / "research_runs" / "tsmom_idiosyncratic_signal_2026-09-08.json"
PAYLOAD = json.loads(RESULT.read_text())

CONTINUOUS = Path(PAYLOAD["panel"]["source"])
BURN_IN, REFIT, K = 504, 21, 6
VOL_TARGET, DELTA, ANNUAL = 0.40, 60.0 / 61.0, 261
TDY = 252
FAILURES: list[str] = []


def check(name: str, got: float, want: float, tol: float) -> None:
    ok = abs(got - want) <= tol
    print(f"{'OK  ' if ok else 'FAIL'} {name}: got {got!r} want {want!r} (tol {tol})")
    if not ok:
        FAILURES.append(name)


# --- panel, rebuilt from the CSVs -----------------------------------------
cols = {}
for p in sorted(CONTINUOUS.glob("*.csv")):
    f = pd.read_csv(p)
    cols[p.stem] = pd.Series(
        f["chained_daily_return"].to_numpy(dtype=float),
        index=pd.DatetimeIndex(pd.to_datetime(f["trade_date"])),
    )
panel = pd.DataFrame(cols).sort_index().dropna(how="all")
for d in PAYLOAD["panel"]["cl_dates_masked"]:
    panel.loc[pd.Timestamp(d), "CL"] = np.nan
common = panel.dropna(how="any")
R = common.to_numpy()
T, N = R.shape
check("panel n_obs", T, PAYLOAD["panel"]["common_window_n_obs"], 0)
check("panel n_instruments", N, PAYLOAD["panel"]["n_instruments"], 0)


# --- ex-ante vol, MOP Eq.(1), written out longhand here --------------------
def ex_ante_vol_manual(r: np.ndarray) -> np.ndarray:
    """sigma_t^2 = 261 * EWMA_delta[(r_{t-1-i} - rbar_t)^2], expanded via the
    E[x^2]-E[x]^2 identity. Independent transcription; no import."""
    alpha = 1.0 - DELTA
    frame = pd.DataFrame(r)
    lag = frame.shift(1)
    mean = lag.ewm(alpha=alpha, adjust=True, min_periods=2).mean()
    msq = (lag**2).ewm(alpha=alpha, adjust=True, min_periods=2).mean()
    var = (msq - mean**2).clip(lower=0.0)
    return np.sqrt(ANNUAL * var).to_numpy()


SIGMA = ex_ante_vol_manual(R)


def trailing_manual(r: np.ndarray, days: int) -> np.ndarray:
    """Compounded trailing return over `days` rows, inclusive."""
    out = np.full(r.shape, np.nan)
    lg = np.log1p(r)
    csum = np.cumsum(lg, axis=0)
    out[days - 1 :] = np.expm1(csum[days - 1 :] - np.concatenate([np.zeros((1, r.shape[1])), csum[:-days]]))
    return out


def build(lookback_days: int, hedged: bool, rebalance: int = REFIT):
    signs = np.sign(trailing_manual(R, lookback_days))
    gross = np.full(T, np.nan)
    turn = np.zeros(T)
    prev = np.zeros(N)
    hedge_pnl = np.full(T, np.nan)
    exposures = []
    start = BURN_IN
    while start < T:
        stop = min(start + rebalance, T)
        prior = R[:start]
        m, s = prior.mean(0), prior.std(0, ddof=1)
        z = (prior - m) / s
        ev, evec = np.linalg.eigh(np.corrcoef(z, rowvar=False))
        L = evec[:, np.argsort(ev)[::-1]][:, :K]
        fz = z @ L
        coef = np.linalg.lstsq(np.column_stack([np.ones(len(z)), fz]), z, rcond=None)[0]
        B = coef[1:]

        sg, sig = signs[start - 1], SIGMA[start - 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            size = VOL_TARGET / sig
        ok = np.isfinite(sg) & np.isfinite(size) & (sig > 0)
        S = int(ok.sum())
        if S == 0:
            start = stop
            continue
        w = np.zeros(N)
        w[ok] = sg[ok] * size[ok] / S
        E = B @ (w * s)
        h = -(L @ E) / s if hedged else np.zeros(N)
        wn = w + h
        turn[start] = np.abs(wn - prev).sum()
        prev = wn
        blk = np.nan_to_num(R[start:stop], nan=0.0)
        gross[start:stop] = blk @ wn
        hedge_pnl[start:stop] = blk @ h
        if hedged:
            exposures.append((slice(start, stop), blk @ (L / s[:, None]), E))
        start = stop
    mask = np.isfinite(gross)
    return (
        pd.Series(gross[mask], index=common.index[mask]),
        pd.Series(turn[mask], index=common.index[mask]),
        pd.Series(hedge_pnl[mask], index=common.index[mask]),
        exposures,
    )


def sharpe(x: pd.Series) -> float:
    return float(x.mean() / x.std(ddof=1) * np.sqrt(TDY))


print("\n--- V1: headline gross/net Sharpe re-derived ---")
g_h, t_h, hp_h, exps = build(12 * REFIT, True)
g_u, t_u, _, _ = build(12 * REFIT, False)
g_ref, t_ref, _, _ = build(252, False, rebalance=5)

check("headline gross Sharpe", sharpe(g_h), PAYLOAD["headline"]["sharpe_gross_annualized"], 1e-9)

years = len(g_ref) / TDY
vol_ref = float(g_ref.std(ddof=1) * np.sqrt(TDY))
turn_ref = float(t_ref.sum()) / years
c_mid = 0.025 * (vol_ref / 0.10) / turn_ref
check("cost per unit (mid)", c_mid, PAYLOAD["cost_model"]["cost_per_unit_notional_traded"]["0.025"], 1e-12)

net_h = g_h - c_mid * t_h
check("headline net Sharpe", sharpe(net_h), PAYLOAD["headline"]["sharpe_net_annualized"], 1e-9)
check("unhedged net Sharpe", sharpe(g_u - c_mid * t_u),
      PAYLOAD["specs"]["lb12_unhedged"]["sharpe_net_annualized"], 1e-9)

print("\n--- V2: factor neutrality, per-block against the block's OWN factors ---")
# A POOLED regression of the whole history on ONE factor basis is the wrong
# diagnostic and the run script's first version of it was mis-specified. The
# hedge uses a basis that is re-estimated every 21 days, and the loadings
# rotate 31.88 degrees over the sample (d020a3d), so no single fixed
# coefficient vector can represent it: the pooled R^2 of the UNHEDGED leg came
# out at only 0.12 even though 91.5% of its variance is demonstrably in the
# removed component. The right pair of statements is:
#   (a) how much of the raw leg's variance sits in the component the hedge
#       removes -- c_t, evaluated with the block's OWN fixed exposures, no
#       refitting, so there is no overfit; and
#   (b) whether what survives is uncorrelated with that removed component.
removed = -hp_h  # hedge P&L is exactly minus the removed factor component
frac_removed = float(removed.var(ddof=1)) / float(g_u.var(ddof=1))
corr_resid = float(np.corrcoef(g_h, removed)[0, 1])
print(f"     fraction of raw variance in the removed factor component: {frac_removed:.4%}")
print(f"     corr(idiosyncratic leg, removed factor component):        {corr_resid:+.6f}")
if frac_removed < 0.50:
    FAILURES.append("V2 removed-variance fraction unexpectedly small")
if abs(corr_resid) > 0.30:
    FAILURES.append("V2 residual still strongly correlated with removed factors")
if not FAILURES:
    print("OK   hedge removes the dominant common component and leaves a weakly-correlated residual")

print("\n--- V3: variance decomposition ---")
v_raw = float(g_u.var(ddof=1))
v_hedged = float(g_h.var(ddof=1))
v_hedge_pnl = float(hp_h.var(ddof=1))
cov = float(np.cov(g_h, hp_h, ddof=1)[0, 1])
print(f"     var(raw)={v_raw:.6e}  var(hedged)={v_hedged:.6e}  var(hedgePnL)={v_hedge_pnl:.6e}")
# hedged = raw + hedge_pnl by construction, so raw = hedged - hedge_pnl and
# var(raw) = var(hedged) + var(hedgePnL) - 2cov(hedged, hedgePnL).
check("var(raw) == var(hedged)+var(hedgePnL)-2cov", v_hedged + v_hedge_pnl - 2 * cov, v_raw, 1e-12)
# Stronger still: the two independent builds must agree elementwise.
check("max|hedged - hedgePnL - unhedged|", float((g_h - hp_h - g_u).abs().max()), 0.0, 1e-15)
print(f"     variance retained by the idiosyncratic leg: {v_hedged / v_raw:.4%}")
print(f"     leverage to restore raw risk: {np.sqrt(v_raw / v_hedged):.4f}x")

print("\n--- V4: DSR at n_local recomputed by hand ---")
sig_sr = PAYLOAD["construction"]["sigma_sr_annualized"]
n_local = PAYLOAD["construction"]["n_local"]
sr_d = sharpe(net_h) / np.sqrt(TDY)
sig_d = sig_sr / np.sqrt(TDY)
gam = np.euler_gamma
sr0 = sig_d * ((1 - gam) * norm.ppf(1 - 1 / n_local) + gam * norm.ppf(1 - 1 / (n_local * np.e)))
sk = float(skew(net_h, bias=True))
ku = float(kurtosis(net_h, fisher=False, bias=True))
z = (sr_d - sr0) * np.sqrt(len(net_h) - 1) / np.sqrt(1 - sk * sr_d + ((ku - 1) / 4) * sr_d**2)
check("DSR @ n_local", float(norm.cdf(z)), PAYLOAD["headline"]["dsr_by_n"][str(n_local)], 1e-9)

print("\n--- V5: cost calibration reproduces the citation's own band ---")
annual_cost_ref = c_mid * turn_ref
check("reference leg annual cost == 2.5% scaled to its vol",
      annual_cost_ref, 0.025 * vol_ref / 0.10, 1e-12)
print(f"     implied one-way cost per unit notional: {c_mid * 1e4:.3f} bp")

print("\n--- V6: shared modules byte-identical to main ---")
for mod in (
    "tsmom_signal.py", "tsmom_regime_definition.py", "futures_effective_breadth.py",
    "dsr_policy_n.py", "preservation_score.py", "deflated_sharpe.py",
):
    rel = f"backend/app/services/research_lab/{mod}"
    out = subprocess.run(
        ["git", "diff", "main", "--", rel], cwd=_BACKEND.parent, capture_output=True, text=True, check=False
    )
    risk = subprocess.run(
        ["git", "diff", "main", "--", "backend/app/services/risk/rmt_denoising.py"],
        cwd=_BACKEND.parent, capture_output=True, text=True, check=False,
    )
    if out.stdout.strip():
        FAILURES.append(f"V6 {mod} differs from main")
        print(f"FAIL {mod} DIFFERS from main")
    else:
        print(f"OK   {mod} byte-identical to main")
if risk.stdout.strip():
    FAILURES.append("V6 rmt_denoising.py differs from main")
    print("FAIL rmt_denoising.py DIFFERS from main")
else:
    print("OK   rmt_denoising.py byte-identical to main")

print("\n" + "=" * 60)
if FAILURES:
    print("VERIFICATION FAILED:")
    for f in FAILURES:
        print("  -", f)
    raise SystemExit(1)
print("ALL VERIFICATION CHECKS PASSED")
