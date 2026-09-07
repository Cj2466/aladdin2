"""INDEPENDENT verification of the decisive claim in
tsmom_breadth_bias_quantification_2026-09-08.

The headline finding is a SIGN FLIP: under a diffuse weak-factor
idiosyncratic shape the walk-forward procedure understates true residual
breadth, but under an asset-class-block shape it overstates it. That finding
is what turns the verdict into UNRESOLVED, so it must not rest on the same
code that produced it.

This file therefore re-derives the sign flip from scratch:
  - its OWN walk-forward residualization, written independently (not
    DECOMP.residualize_pit);
  - its OWN breadth statistic sum(l)^2/sum(l^2) via numpy.linalg.eigvalsh
    (not measure_futures_effective_breadth);
  - its OWN panel simulation.
The only thing shared with the audited script is the real price data itself.

If this file's numbers disagree in SIGN with the report's, the report is
wrong and must not be merged.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

_DECOMP_PATH = (
    Path(__file__).resolve().parent / "run_tsmom_factor_decomposition_2026_09_07.py"
)
_spec = importlib.util.spec_from_file_location("_d", _DECOMP_PATH)
DECOMP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DECOMP)

K = 6
BURN_IN = 504
REFIT = 21
N_SEEDS = 25  # fewer than the report's 60; enough to establish a SIGN


def breadth(panel: np.ndarray) -> float:
    """sum(lambda)^2 / sum(lambda^2) of the correlation matrix. Written here
    from the definition, not imported."""
    corr = np.corrcoef(panel, rowvar=False)
    lam = np.linalg.eigvalsh(corr)
    return float(lam.sum() ** 2 / (lam**2).sum())


def my_pit_residuals(values: np.ndarray, k: int) -> np.ndarray:
    """My own expanding-window residualization, written from the description:
    at each refit boundary use ONLY strictly-prior rows to fit moments,
    eigenvectors and betas; apply forward to the next block."""
    n_obs, n_inst = values.shape
    out = np.full((n_obs, n_inst), np.nan)
    start = BURN_IN
    while start < n_obs:
        stop = min(start + REFIT, n_obs)
        prior = values[:start]
        mu = prior.mean(axis=0)
        sd = prior.std(axis=0, ddof=1)
        zp = (prior - mu) / sd
        w, v = np.linalg.eigh(np.corrcoef(zp, rowvar=False))
        load = v[:, np.argsort(w)[::-1][:k]]
        fp = zp @ load
        X = np.hstack([np.ones((len(zp), 1)), fp])
        beta = np.linalg.pinv(X) @ zp
        blk = (values[start:stop] - mu) / sd
        Xb = np.hstack([np.ones((len(blk), 1)), blk @ load])
        out[start:stop] = blk - Xb @ beta
        start = stop
    return out[BURN_IN:]


def main() -> None:
    gate = DECOMP._import_gate_script()
    common = gate.load_return_panel().dropna(how="any")
    obs = common.to_numpy()
    n = obs.shape[1]
    t = obs.shape[0]
    cols = list(common.columns)

    # Independent tripwire: the audited PIT figure, my own code.
    mine = breadth(my_pit_residuals(obs, K))
    print(f"independent PIT residual breadth : {mine:.4f}  (report: 16.9550)")

    # Real fitted structure, re-derived here.
    z = (common - common.mean()) / common.std(ddof=1)
    w, v = np.linalg.eigh(np.corrcoef(z.to_numpy(), rowvar=False))
    order = np.argsort(w)[::-1]
    lam, vec = w[order], v[:, order]
    load = vec[:, :K]
    fvar = lam[:K]
    idio_var = np.clip(1.0 - (load**2) @ fvar, 1e-8, None)
    print(f"mean idiosyncratic variance share: {idio_var.mean():.4f}")

    # --- shape A: diffuse weak factors (10 modes) -------------------------
    rng0 = np.random.default_rng(20260908)
    W = rng0.standard_normal((n, 10))

    def shape_a(c: float) -> np.ndarray:
        cov = c * (W @ W.T) + np.eye(n)
        d = np.sqrt(np.diag(cov))
        return cov / np.outer(d, d)

    # --- shape B: asset-class blocks --------------------------------------
    classes = [DECOMP.ASSET_CLASS.get(c, "unmapped") for c in cols]
    groups = [
        [i for i, c in enumerate(classes) if c == g] for g in sorted(set(classes))
    ]

    def shape_b(r: float) -> np.ndarray:
        m = np.eye(n)
        for grp in groups:
            for i in grp:
                for j in grp:
                    if i != j:
                        m[i, j] = r
        return m

    def pop_breadth(mat: np.ndarray) -> float:
        lm = np.linalg.eigvalsh(mat)
        return float(lm.sum() ** 2 / (lm**2).sum())

    def tune(fn, target: float) -> float:
        lo, hi = 0.0, 0.99
        for _ in range(200):
            mid = (lo + hi) / 2
            if pop_breadth(fn(mid)) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    for label, fn in (("weak-factor", shape_a), ("asset-class-block", shape_b)):
        par = tune(fn, 17.0)
        corr_e = fn(par)
        chol = np.linalg.cholesky(corr_e)
        meas, tru = [], []
        for s in range(N_SEEDS):
            rng = np.random.default_rng(999_000 + s)
            f = rng.standard_normal((t, K)) * np.sqrt(fvar)
            e = (rng.standard_normal((t, n)) @ chol.T) * np.sqrt(idio_var)
            panel = f @ load.T + e
            tru.append(breadth(e))
            meas.append(breadth(my_pit_residuals(panel, K)))
        bias = float(np.mean(meas) - np.mean(tru))
        print(
            f"{label:>18}: param={par:.5f}  true={np.mean(tru):7.4f}  "
            f"measured={np.mean(meas):7.4f}  BIAS={bias:+.4f}"
        )


if __name__ == "__main__":
    main()
