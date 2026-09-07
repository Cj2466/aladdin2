"""Quantify the disclosed optimistic bias in the 16.9550 PIT residual-breadth
figure from tsmom_factor_decomposition_2026-09-07 (merged b8880c8).

WHY THIS EXISTS
====================================================================
The merged decomposition report measured a point-in-time (walk-forward,
504-day burn-in, 21-day refit) effective breadth of 16.9550 on the
idiosyncratic residual panel of the real 31-instrument CME futures universe,
clearing the pre-declared floor of 15. That same report disclosed, in its own
words, that the number is OPTIMISTICALLY BIASED and said so explicitly:

    "PIT is NOT simply the conservative version of IN_SAMPLE. At k = [1, 2, 3]
     the PIT breadth is HIGHER than the in-sample one, which cannot be a
     look-ahead effect. The cause is that PIT betas are estimated with error,
     and that estimation error enters each instrument's residual as noise that
     is largely INDEPENDENT across instruments -- which lowers measured
     residual correlation and therefore INFLATES measured breadth.
     ...
     Quantifying that bias (e.g. by a noise-injection null, or by measuring
     breadth on residuals from factors estimated on a disjoint sample) is
     REQUIRED before this gate result is relied on. It is not done here, and
     this report does not claim the gate is settled."

This script is exactly that quantification, and nothing else. It builds NO
TSMOM signal, runs no DSR, no preservation_score, no mechanism-fidelity
review, no registration, and changes no live registration status.

WHAT IS REUSED VERSUS WHAT IS NEW
====================================================================
REUSED, UNMODIFIED -- this is what keeps every number below directly
comparable to the merged 10.0081 / 16.9550 figures:
  - app/services/research_lab/futures_effective_breadth.py
    (`measure_futures_effective_breadth`). Imported, not edited, not copied.
  - app/services/risk/rmt_denoising.py. Imported, not edited.
  - data/research_runs/run_tsmom_factor_decomposition_2026_09_07.py -- the
    MERGED script itself is imported as a module and its `residualize_pit`,
    `residualize_in_sample`, `measure`, `spectrum`, `_standardize` and
    `_import_gate_script` functions are called directly. The walk-forward
    procedure under test is therefore literally the same code that produced
    16.9550, not a re-implementation that could silently differ.
  - data/research_runs/measure_futures_breadth_2026_09_07.py -- reached
    through the above, so the return panel is built by the same loader that
    produced the published 10.0081.

NEW HERE: the noise-injection null (Method 1), the equicorrelation
calibration algebra, and the disjoint-sample estimator (Method 2).

METHOD 1 -- NOISE-INJECTION NULL (calibrated, not just a single null)
====================================================================
The naive null ("simulate 6 factors + i.i.d. idiosyncratic noise, true
residual breadth is 31, see what the procedure reports") answers only one
question: what does the procedure report when the truth is 31? That is the
wrong operating point. 16.9550 was measured, not 31, so what is needed is the
behaviour of the estimator NEAR 17.

So this script builds a CALIBRATION CURVE instead. Synthetic panels are
generated with a KNOWN true residual breadth B_true spanning a ladder from 31
down to 11, the identical walk-forward procedure is run on each, and the
mapping B_true -> E[B_measured] is estimated. The real 16.9550 is then
INVERTED through that mapping to recover the B_true that would produce it.
The pure-i.i.d. case (B_true = 31) is included in the ladder, so the naive
null the task asked for is a strict subset of what is computed.

Synthetic panel construction, using REAL magnitudes, not invented ones:
  Let Z be the real 31-column common-window panel, z-scored (correlation-PCA
  convention, matching J3 of the merged report). Its full-sample correlation
  matrix has eigenvalues lambda_1..lambda_31 and orthonormal eigenvectors V.
  For the top k = 6 (the merged report's RMT-determined headline k):

      common_i(t) = sum_{j<=k} f_j(t) * V_ij

  where the real factor scores f_j = Z v_j have sample variance lambda_j
  exactly (an identity of correlation PCA with orthonormal v_j, machine-
  checked below). So the simulation draws

      f_j(t) ~ N(0, lambda_j)      lambda_j and V_ij BOTH taken from the real
                                   fitted decomposition -- no loading
                                   magnitude is invented anywhere

  and the per-instrument true idiosyncratic variance is fixed by the same
  identity to

      s_i^2 = 1 - sum_{j<=k} lambda_j * V_ij^2

  i.e. the real, per-instrument residual variance share, not a flat guess.
  The idiosyncratic vector e(t) ~ N(0, D R D) with D = diag(s_i) and R an
  equicorrelation matrix with parameter rho.

THE EQUICORRELATION ALGEBRA -- DERIVED HERE, NOT QUOTED
====================================================================
FLAGGED: the following is exact algebra derived in this file, not taken from
any paper. It needs no citation because it is an identity of the
equicorrelation matrix, and it is machine-checked below against
numpy.linalg.eigvalsh rather than asserted.

For R = (1-rho) I_n + rho 11', the eigenvalues are

    lambda_1 = 1 + (n-1) rho        (eigenvector 1/sqrt(n) * 1)
    lambda_2..n = 1 - rho           (multiplicity n-1)

The project's breadth statistic B = (sum lambda)^2 / sum(lambda^2) with
sum(lambda) = trace = n gives

    B(rho) = n^2 / [ (1 + (n-1) rho)^2 + (n-1)(1 - rho)^2 ]        (E1)

B(0) = n (n independent bets) and B is strictly decreasing in rho on [0, 1),
so (E1) is invertible: a target B_true is hit by solving (E1) for rho with a
bracketed root find. Note D R D has the SAME correlation matrix as R for any
positive diagonal D, so scaling by the real per-instrument residual
volatilities does not disturb the known true breadth.

The measured breadth of a FINITE sample from R is not exactly B(rho) -- it
carries ordinary sampling noise. That is measured too and reported as
`B_true_realized`, so the calibration compares like with like rather than
comparing a measured number against a population constant.

METHOD 2 -- DISJOINT-SAMPLE ESTIMATION
====================================================================
Standardization moments, eigenvectors and betas are estimated on one
non-overlapping sub-sample and applied, with NO refitting whatsoever, to a
different sub-sample on which the breadth is measured. This removes the
walk-forward pathway entirely: the residualization has never seen a single
observation of the test period. Two split designs, both reported:

  HALVES        first half estimates -> second half tested, and the reverse.
                Strictly disjoint in time. Cost: the loadings are stale by up
                to ~4 years on the far end of the test block, which is a
                DOWNWARD pressure on measured breadth (a stale factor is
                removed imperfectly, leaving common variance in the residual).
  BLOCK_ALTERNATING
                the sample is cut into consecutive blocks and the odd blocks
                estimate while the even blocks are tested. Still no test
                observation enters the estimation, but the estimation and test
                periods are interleaved so staleness is small. This is the
                design that isolates the in-test-period-noise pathway without
                also paying the staleness cost.

Both designs are ALSO run on the synthetic panels, so the disjoint estimator
gets its own calibration curve and its own bias-corrected inversion rather
than being read raw.

JUDGMENT CALLS MADE HERE (all flagged, none hidden)
====================================================================
  K1. k = 6 factors removed everywhere, and the synthetic panels are built
      with EXACTLY 6 true factors. This is the merged report's RMT-determined
      headline k, not a hand-pick. But it makes the null FAVOURABLE to the
      procedure: the estimator is asked to find exactly the number of factors
      that really exist. If the real panel has weak 7th/8th factors (Kaiser-
      Guttman said 8), the real-data bias could differ from the null's. Stated
      as a limitation, not corrected for.
  K2. Gaussian i.i.d.-in-time innovations. Real futures returns are fat-tailed
      and volatility-clustered. Heavier tails would add sampling noise to
      every correlation estimate, which if anything makes the real estimation
      error LARGER than the null's -- i.e. this choice biases the measured
      bias DOWNWARD, making the correction conservative in the direction that
      matters. A Student-t sensitivity run is included to check that claim
      rather than assert it.
  K3. Calibration ladder B_true in {31, 25, 20, 17, 15, 13, 11} and N_SEEDS
      Monte Carlo draws per rung. Ordinary choices, not from a source.
  K4. BLOCK_DAYS = 252 for the alternating-block design. An ordinary
      one-year convention; a sensitivity over {63, 126, 252, 504} is run.
  K5. The inversion of the calibration curve uses linear interpolation on the
      (B_true -> mean B_measured) ladder. With 7 rungs over a smooth monotone
      relationship this is adequate; the raw ladder is printed so a reader can
      check the interpolation rather than trust it.
  K6. Everything inherits the merged report's own judgment calls J1-J5
      (burn_in=504, refit_every=21, correlation PCA, k choice). Changing them
      here would break comparability with 16.9550, so they are held fixed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import brentq

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, not inside {_BACKEND}"
    )

from app.services.research_lab.futures_effective_breadth import (
    EFFECTIVE_BREADTH_FLOOR,
)

# --- the merged decomposition script, imported so the procedure under test is
# --- literally the merged code, not a re-implementation -----------------------
_DECOMP_PATH = (
    Path(__file__).resolve().parent / "run_tsmom_factor_decomposition_2026_09_07.py"
)
if not _DECOMP_PATH.exists():
    raise SystemExit(f"merged decomposition script not found at {_DECOMP_PATH}")
_spec = importlib.util.spec_from_file_location("_tsmom_decomp", _DECOMP_PATH)
if _spec is None or _spec.loader is None:
    raise SystemExit("could not load the merged decomposition script")
DECOMP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DECOMP)

#: The figure this whole script exists to audit. From
#: data/research_runs/tsmom_factor_decomposition_2026-09-07.json (b8880c8).
PUBLISHED_PIT_RESIDUAL_BREADTH = 16.9550
#: and the raw universe gate figure, reproduced as a tripwire.
PUBLISHED_FUTURES_BREADTH = DECOMP.PUBLISHED_FUTURES_BREADTH

K_FACTORS = DECOMP.K_SWEEP_MAX  # 6, the merged headline k (K1)
BURN_IN_DAYS = DECOMP.BURN_IN_DAYS  # 504 (K6)
REFIT_EVERY_DAYS = DECOMP.REFIT_EVERY_DAYS  # 21 (K6)

N_SEEDS = 60  # K3
B_TRUE_LADDER = (31.0, 25.0, 20.0, 17.0, 15.0, 13.0, 11.0)  # K3
BLOCK_DAYS = 252  # K4
BLOCK_DAYS_SENSITIVITY = (63, 126, 252, 504)  # K4
STUDENT_T_DF = 4  # K2 sensitivity

OUT_TXT = (
    _BACKEND
    / "data"
    / "research_runs"
    / "tsmom_breadth_bias_quantification_2026-09-08.txt"
)
OUT_JSON = (
    _BACKEND
    / "data"
    / "research_runs"
    / "tsmom_breadth_bias_quantification_2026-09-08.json"
)


# --------------------------------------------------------------------------
# Equicorrelation algebra (E1) -- derived here, machine-checked
# --------------------------------------------------------------------------
def equicorr_breadth(rho: float, n: int) -> float:
    """Effective breadth of an n x n equicorrelation matrix, per (E1)."""
    lam_top = 1.0 + (n - 1) * rho
    lam_rest = 1.0 - rho
    return n**2 / (lam_top**2 + (n - 1) * lam_rest**2)


def rho_for_breadth(target: float, n: int) -> float:
    """Invert (E1). B(0) = n and B is strictly decreasing on [0, 1)."""
    if target >= n - 1e-12:
        return 0.0
    return float(brentq(lambda r: equicorr_breadth(r, n) - target, 0.0, 0.999999))


def verify_equicorr_algebra(n: int) -> list[dict[str, Any]]:
    """Machine-check (E1) against a numerical eigendecomposition. If this
    fails, every synthetic panel below has an unknown true breadth and the
    whole script is void."""
    checks = []
    for rho in (0.0, 0.05, 0.1, 0.25, 0.5):
        mat = (1 - rho) * np.eye(n) + rho * np.ones((n, n))
        lam = np.linalg.eigvalsh(mat)
        numeric = float(lam.sum() ** 2 / (lam**2).sum())
        analytic = equicorr_breadth(rho, n)
        checks.append(
            {
                "rho": rho,
                "analytic_E1": analytic,
                "numeric_eigvalsh": numeric,
                "delta": abs(analytic - numeric),
                "holds": bool(abs(analytic - numeric) < 1e-9),
            }
        )
    return checks


# --------------------------------------------------------------------------
# Synthetic panel generation -- REAL loadings, REAL residual variances
# --------------------------------------------------------------------------
class TrueStructure:
    """The real fitted 6-factor structure, reused verbatim as the synthetic
    panel's TRUE structure so no loading magnitude is invented."""

    def __init__(self, common: pd.DataFrame, k: int):
        self.columns = list(common.columns)
        self.n = common.shape[1]
        self.t = common.shape[0]
        self.k = k
        corr = common.corr()
        eigenvalues, eigenvectors = DECOMP.spectrum(corr)
        self.eigenvalues = eigenvalues
        self.loadings = eigenvectors[:, :k]  # 31 x k, orthonormal columns
        self.factor_var = eigenvalues[:k]  # variance of each real factor score
        # s_i^2 = 1 - sum_j lambda_j V_ij^2, the real per-instrument
        # idiosyncratic variance share under the k-factor model.
        explained = (self.loadings**2) @ self.factor_var
        self.idio_var = np.clip(1.0 - explained, 1e-8, None)
        self.explained_var_share = explained

    def identity_check(self, common: pd.DataFrame) -> dict[str, Any]:
        """f_j = Z v_j must have sample variance lambda_j exactly. If not, the
        factor variances used in the simulation are wrong."""
        z = DECOMP._standardize(common).to_numpy()
        scores = z @ self.loadings
        emp = scores.var(axis=0, ddof=1)
        return {
            "factor_variance_from_eigenvalues": [float(v) for v in self.factor_var],
            "factor_variance_empirical": [float(v) for v in emp],
            "max_delta": float(np.abs(emp - self.factor_var).max()),
            "holds": bool(np.abs(emp - self.factor_var).max() < 1e-6),
            "mean_explained_variance_share": float(self.explained_var_share.mean()),
            "mean_idiosyncratic_variance_share": float(self.idio_var.mean()),
        }

    def simulate(
        self, rho: float, rng: np.random.Generator, heavy_tailed: bool = False
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return (observed_panel, true_idiosyncratic_panel), both T x n."""
        t, n, k = self.t, self.n, self.k
        corr_e = (1 - rho) * np.eye(n) + rho * np.ones((n, n))
        chol = np.linalg.cholesky(corr_e)

        if heavy_tailed:
            # Standardized Student-t: unit variance for df > 2 (K2).
            def draw(rows: int, cols: int) -> np.ndarray:
                raw = rng.standard_t(STUDENT_T_DF, size=(rows, cols))
                return raw / np.sqrt(STUDENT_T_DF / (STUDENT_T_DF - 2.0))
        else:

            def draw(rows: int, cols: int) -> np.ndarray:
                return rng.standard_normal((rows, cols))

        factors = draw(t, k) * np.sqrt(self.factor_var)
        idio = (draw(t, n) @ chol.T) * np.sqrt(self.idio_var)
        observed = factors @ self.loadings.T + idio
        return observed, idio


# --------------------------------------------------------------------------
# Method 2 -- disjoint-sample residualization (NEW)
# --------------------------------------------------------------------------
def residualize_disjoint(
    panel: pd.DataFrame,
    k: int,
    estimate_mask: np.ndarray,
    test_mask: np.ndarray,
) -> pd.DataFrame:
    """Estimate standardization moments, top-k eigenvectors and per-instrument
    alpha/beta on the ESTIMATE rows only; apply them, with no refitting at
    all, to the TEST rows; return the test-row residuals.

    The estimate and test row sets are disjoint by construction (asserted), so
    not one observation whose residual is measured has ever entered the
    estimation of the loadings used to residualize it.
    """
    if np.any(estimate_mask & test_mask):
        raise AssertionError("estimate and test masks overlap -- not disjoint")
    values = panel.to_numpy()
    est = values[estimate_mask]
    test = values[test_mask]

    mean = est.mean(axis=0)
    std = est.std(axis=0, ddof=1)
    if np.any(std <= 0) or not np.all(np.isfinite(std)):
        raise AssertionError("degenerate estimation-window standard deviation")
    z_est = (est - mean) / std
    corr_est = np.corrcoef(z_est, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(corr_est)
    order = np.argsort(eigvals)[::-1]
    loadings = eigvecs[:, order][:, :k]

    factors_est = z_est @ loadings
    design_est = np.column_stack([np.ones(len(z_est)), factors_est])
    coef, *_ = np.linalg.lstsq(design_est, z_est, rcond=None)

    z_test = (test - mean) / std
    factors_test = z_test @ loadings
    design_test = np.column_stack([np.ones(len(z_test)), factors_test])
    residual = z_test - design_test @ coef
    return pd.DataFrame(
        residual, index=panel.index[test_mask], columns=panel.columns
    )


def halves_masks(n_obs: int) -> tuple[np.ndarray, np.ndarray]:
    half = n_obs // 2
    first = np.zeros(n_obs, dtype=bool)
    first[:half] = True
    second = np.zeros(n_obs, dtype=bool)
    second[half:] = True
    return first, second


def alternating_block_masks(
    n_obs: int, block_days: int
) -> tuple[np.ndarray, np.ndarray]:
    """Odd-numbered blocks estimate, even-numbered blocks are tested."""
    block_id = np.arange(n_obs) // block_days
    even = (block_id % 2) == 0
    odd = ~even
    return odd, even


# --------------------------------------------------------------------------
def _breadth(panel: pd.DataFrame) -> float:
    return float(DECOMP.measure(panel)["breadth_eigenvalue"])


def _as_frame(values: np.ndarray, index: pd.Index, columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(values, index=index, columns=columns)


def _interp_invert(
    ladder: list[tuple[float, float]], measured: float
) -> dict[str, Any]:
    """Invert a monotone (B_true -> mean B_measured) ladder at `measured` by
    linear interpolation (K5). `ladder` is sorted ascending by B_true."""
    xs = [b_true for b_true, _ in ladder]
    ys = [b_meas for _, b_meas in ladder]
    monotone = all(ys[i] < ys[i + 1] for i in range(len(ys) - 1))
    if measured <= ys[0]:
        return {
            "b_true_implied": None,
            "note": (
                f"measured {measured:.4f} is at or below the lowest calibration "
                f"rung's mean measured value {ys[0]:.4f}; outside the ladder, "
                "would require extrapolation"
            ),
            "calibration_is_monotone": monotone,
        }
    if measured >= ys[-1]:
        return {
            "b_true_implied": None,
            "note": (
                f"measured {measured:.4f} is at or above the highest calibration "
                f"rung's mean measured value {ys[-1]:.4f}; outside the ladder"
            ),
            "calibration_is_monotone": monotone,
        }
    implied = float(np.interp(measured, ys, xs))
    return {
        "b_true_implied": implied,
        "note": "linear interpolation on the calibration ladder (K5)",
        "calibration_is_monotone": monotone,
    }


# --------------------------------------------------------------------------
def main() -> None:
    gate = DECOMP._import_gate_script()
    print(f"continuous CSVs: {gate.CONTINUOUS}")

    panel = gate.load_return_panel()
    common = panel.dropna(how="any")
    n = common.shape[1]
    t_obs = common.shape[0]
    columns = list(common.columns)
    index = common.index
    print(f"common window {t_obs} x {n}: "
          f"{index.min().date()} .. {index.max().date()}")

    # ---- TRIPWIRE 1: reproduce the published raw gate number --------------
    raw_breadth = _breadth(panel)
    if abs(raw_breadth - PUBLISHED_FUTURES_BREADTH) > 1e-9:
        raise SystemExit(
            f"REFUSING TO CONTINUE: raw breadth {raw_breadth} != published "
            f"{PUBLISHED_FUTURES_BREADTH}. Data or module has moved."
        )
    print(f"tripwire 1 OK: raw breadth reproduced {raw_breadth:.12f}")

    # ---- TRIPWIRE 2: reproduce the published PIT residual number ----------
    real_pit = DECOMP.residualize_pit(common, K_FACTORS)
    real_pit_breadth = _breadth(real_pit)
    real_in_sample = DECOMP.residualize_in_sample(common, K_FACTORS)
    real_in_sample_breadth = _breadth(real_in_sample)
    if abs(real_pit_breadth - PUBLISHED_PIT_RESIDUAL_BREADTH) > 5e-4:
        raise SystemExit(
            f"REFUSING TO CONTINUE: PIT residual breadth {real_pit_breadth} does "
            f"not reproduce the published {PUBLISHED_PIT_RESIDUAL_BREADTH}."
        )
    print(f"tripwire 2 OK: PIT residual breadth reproduced {real_pit_breadth:.4f}")

    # ---- structure + algebra self-checks ---------------------------------
    truth = TrueStructure(common, K_FACTORS)
    identity = truth.identity_check(common)
    if not identity["holds"]:
        raise SystemExit(f"factor-variance identity failed: {identity}")
    algebra = verify_equicorr_algebra(n)
    if not all(c["holds"] for c in algebra):
        raise SystemExit(f"equicorrelation algebra (E1) failed self-check: {algebra}")
    print("self-checks OK: factor-variance identity + equicorrelation algebra (E1)")

    # ======================================================================
    # METHOD 2 on the REAL data -- disjoint-sample breadth
    # ======================================================================
    first, second = halves_masks(t_obs)
    disjoint_real: dict[str, Any] = {}
    disjoint_real["halves_first_estimates_second_tested"] = {
        "n_estimate": int(first.sum()),
        "n_test": int(second.sum()),
        "estimate_window": [str(index[first][0].date()), str(index[first][-1].date())],
        "test_window": [str(index[second][0].date()), str(index[second][-1].date())],
        "breadth": _breadth(residualize_disjoint(common, K_FACTORS, first, second)),
    }
    disjoint_real["halves_second_estimates_first_tested"] = {
        "n_estimate": int(second.sum()),
        "n_test": int(first.sum()),
        "estimate_window": [str(index[second][0].date()), str(index[second][-1].date())],
        "test_window": [str(index[first][0].date()), str(index[first][-1].date())],
        "breadth": _breadth(residualize_disjoint(common, K_FACTORS, second, first)),
    }
    odd, even = alternating_block_masks(t_obs, BLOCK_DAYS)
    disjoint_real["block_alternating_252d"] = {
        "block_days": BLOCK_DAYS,
        "n_estimate": int(odd.sum()),
        "n_test": int(even.sum()),
        "breadth": _breadth(residualize_disjoint(common, K_FACTORS, odd, even)),
    }
    block_sensitivity = []
    for bd in BLOCK_DAYS_SENSITIVITY:
        o, e = alternating_block_masks(t_obs, bd)
        block_sensitivity.append(
            {
                "block_days": bd,
                "n_estimate": int(o.sum()),
                "n_test": int(e.sum()),
                "breadth_odd_estimates_even_tested": _breadth(
                    residualize_disjoint(common, K_FACTORS, o, e)
                ),
                "breadth_even_estimates_odd_tested": _breadth(
                    residualize_disjoint(common, K_FACTORS, e, o)
                ),
            }
        )
    disjoint_real["block_days_sensitivity"] = block_sensitivity
    print("METHOD 2 (real data) done: "
          f"halves {disjoint_real['halves_first_estimates_second_tested']['breadth']:.4f}"
          f" / {disjoint_real['halves_second_estimates_first_tested']['breadth']:.4f}, "
          f"blocks {disjoint_real['block_alternating_252d']['breadth']:.4f}")

    # ======================================================================
    # METHOD 1 -- noise-injection null, as a calibration ladder
    # ======================================================================
    rungs: list[dict[str, Any]] = []
    for b_true in B_TRUE_LADDER:
        rho = rho_for_breadth(b_true, n)
        pit_vals: list[float] = []
        true_vals: list[float] = []
        in_sample_vals: list[float] = []
        halves_vals: list[float] = []
        blocks_vals: list[float] = []
        for seed in range(N_SEEDS):
            rng = np.random.default_rng(20260908 + 1000 * int(b_true * 10) + seed)
            observed, idio = truth.simulate(rho, rng)
            obs_df = _as_frame(observed, index, columns)
            idio_df = _as_frame(idio, index, columns)
            # The TRUE residual breadth actually realized in this finite draw.
            true_vals.append(_breadth(idio_df))
            pit_vals.append(_breadth(DECOMP.residualize_pit(obs_df, K_FACTORS)))
            in_sample_vals.append(
                _breadth(DECOMP.residualize_in_sample(obs_df, K_FACTORS))
            )
            halves_vals.append(
                _breadth(residualize_disjoint(obs_df, K_FACTORS, first, second))
            )
            blocks_vals.append(
                _breadth(residualize_disjoint(obs_df, K_FACTORS, odd, even))
            )

        def summarize(vals: list[float]) -> dict[str, float]:
            arr = np.array(vals)
            return {
                "mean": float(arr.mean()),
                "sd": float(arr.std(ddof=1)),
                "p05": float(np.percentile(arr, 5)),
                "p95": float(np.percentile(arr, 95)),
            }

        rung = {
            "b_true_population": b_true,
            "rho": rho,
            "b_true_realized": summarize(true_vals),
            "pit_measured": summarize(pit_vals),
            "in_sample_measured": summarize(in_sample_vals),
            "disjoint_halves_measured": summarize(halves_vals),
            "disjoint_blocks_measured": summarize(blocks_vals),
        }
        rung["pit_bias_vs_realized_truth"] = (
            rung["pit_measured"]["mean"] - rung["b_true_realized"]["mean"]
        )
        rung["disjoint_halves_bias"] = (
            rung["disjoint_halves_measured"]["mean"] - rung["b_true_realized"]["mean"]
        )
        rung["disjoint_blocks_bias"] = (
            rung["disjoint_blocks_measured"]["mean"] - rung["b_true_realized"]["mean"]
        )
        rungs.append(rung)
        print(
            f"  ladder B_true={b_true:5.1f} (rho={rho:.5f}) realized="
            f"{rung['b_true_realized']['mean']:7.4f}  PIT="
            f"{rung['pit_measured']['mean']:7.4f} (bias "
            f"{rung['pit_bias_vs_realized_truth']:+.4f})  halves="
            f"{rung['disjoint_halves_measured']['mean']:7.4f}  blocks="
            f"{rung['disjoint_blocks_measured']['mean']:7.4f}"
        )

    # The naive null the task asked for, as a subset of the ladder.
    iid_rung = next(r for r in rungs if r["b_true_population"] == 31.0)

    # ---- Student-t sensitivity at the operating point (K2) ----------------
    b_true_t = 17.0
    rho_t = rho_for_breadth(b_true_t, n)
    t_pit, t_true, t_halves, t_blocks = [], [], [], []
    for seed in range(N_SEEDS):
        rng = np.random.default_rng(77770908 + seed)
        observed, idio = truth.simulate(rho_t, rng, heavy_tailed=True)
        obs_df = _as_frame(observed, index, columns)
        t_true.append(_breadth(_as_frame(idio, index, columns)))
        t_pit.append(_breadth(DECOMP.residualize_pit(obs_df, K_FACTORS)))
        t_halves.append(
            _breadth(residualize_disjoint(obs_df, K_FACTORS, first, second))
        )
        t_blocks.append(_breadth(residualize_disjoint(obs_df, K_FACTORS, odd, even)))
    student_t = {
        "df": STUDENT_T_DF,
        "b_true_population": b_true_t,
        "b_true_realized_mean": float(np.mean(t_true)),
        "pit_measured_mean": float(np.mean(t_pit)),
        "pit_bias": float(np.mean(t_pit) - np.mean(t_true)),
        "disjoint_halves_measured_mean": float(np.mean(t_halves)),
        "disjoint_blocks_measured_mean": float(np.mean(t_blocks)),
        "gaussian_pit_bias_at_17": next(
            r["pit_bias_vs_realized_truth"]
            for r in rungs
            if r["b_true_population"] == 17.0
        ),
    }
    print(f"Student-t(4) sensitivity at B_true=17: PIT bias "
          f"{student_t['pit_bias']:+.4f} vs Gaussian "
          f"{student_t['gaussian_pit_bias_at_17']:+.4f}")

    # ======================================================================
    # INVERSION -- what true breadth would produce the observed numbers
    # ======================================================================
    ladder_sorted = sorted(rungs, key=lambda r: r["b_true_realized"]["mean"])
    pit_ladder = [
        (r["b_true_realized"]["mean"], r["pit_measured"]["mean"]) for r in ladder_sorted
    ]
    halves_ladder = [
        (r["b_true_realized"]["mean"], r["disjoint_halves_measured"]["mean"])
        for r in ladder_sorted
    ]
    blocks_ladder = [
        (r["b_true_realized"]["mean"], r["disjoint_blocks_measured"]["mean"])
        for r in ladder_sorted
    ]

    inversion = {
        "pit_from_real_16_9550": _interp_invert(pit_ladder, real_pit_breadth),
        "disjoint_halves_from_real": _interp_invert(
            halves_ladder,
            disjoint_real["halves_first_estimates_second_tested"]["breadth"],
        ),
        "disjoint_halves_reverse_from_real": _interp_invert(
            halves_ladder,
            disjoint_real["halves_second_estimates_first_tested"]["breadth"],
        ),
        "disjoint_blocks_from_real": _interp_invert(
            blocks_ladder, disjoint_real["block_alternating_252d"]["breadth"]
        ),
    }

    # Monte-Carlo uncertainty of the ladder means, carried into the inversion
    # as a crude +/- band: shift the observed number by the rung's own seed
    # standard error and re-invert.
    def rung_se(ladder_key: str, measured: float) -> float:
        nearest = min(
            rungs, key=lambda r: abs(r[ladder_key]["mean"] - measured)
        )
        return nearest[ladder_key]["sd"] / np.sqrt(N_SEEDS)

    pit_se = rung_se("pit_measured", real_pit_breadth)
    inversion["pit_from_real_16_9550_mc_band"] = {
        "monte_carlo_se_of_ladder_mean": float(pit_se),
        "b_true_implied_minus_1se": _interp_invert(
            pit_ladder, real_pit_breadth - pit_se
        ).get("b_true_implied"),
        "b_true_implied_plus_1se": _interp_invert(
            pit_ladder, real_pit_breadth + pit_se
        ).get("b_true_implied"),
        "note": (
            "band from Monte-Carlo error in the calibration ladder ONLY. It does "
            "NOT include sampling error in the real 16.9550 itself, nor model "
            "error from K1/K2. It is a lower bound on total uncertainty."
        ),
    }

    # ======================================================================
    # VERDICT
    # ======================================================================
    pit_implied = inversion["pit_from_real_16_9550"].get("b_true_implied")
    blocks_implied = inversion["disjoint_blocks_from_real"].get("b_true_implied")
    halves_implied = inversion["disjoint_halves_from_real"].get("b_true_implied")

    estimates = {
        "method_1_pit_bias_corrected": pit_implied,
        "method_2_blocks_bias_corrected": blocks_implied,
        "method_2_halves_bias_corrected": halves_implied,
        "method_2_blocks_raw_uncorrected": disjoint_real["block_alternating_252d"][
            "breadth"
        ],
        "method_2_halves_raw_uncorrected": disjoint_real[
            "halves_first_estimates_second_tested"
        ]["breadth"],
    }
    live = [v for v in estimates.values() if v is not None]
    all_clear = all(v >= EFFECTIVE_BREADTH_FLOOR for v in live)
    all_fail = all(v < EFFECTIVE_BREADTH_FLOOR for v in live)
    if all_clear:
        verdict = "PASSES"
    elif all_fail:
        verdict = "FAILS"
    else:
        verdict = "UNRESOLVED"

    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "what_this_is": (
            "Quantification of the optimistic bias that "
            "tsmom_factor_decomposition_2026-09-07 (merged b8880c8) disclosed in "
            "its own 16.9550 PIT residual-breadth figure. Two methods: a "
            "calibrated noise-injection null and a disjoint-sample estimator. "
            "Measurement only -- no TSMOM signal, no DSR, no preservation_score, "
            "no registration, no live-status change, nothing pushed."
        ),
        "universe": columns,
        "n_instruments": n,
        "common_window_n_observations": t_obs,
        "common_window": [str(index.min().date()), str(index.max().date())],
        "floor": float(EFFECTIVE_BREADTH_FLOOR),
        "k_factors_removed": K_FACTORS,
        "burn_in_days": BURN_IN_DAYS,
        "refit_every_days": REFIT_EVERY_DAYS,
        "n_monte_carlo_seeds_per_rung": N_SEEDS,
        "tripwires": {
            "raw_universe_breadth_published": PUBLISHED_FUTURES_BREADTH,
            "raw_universe_breadth_reproduced": raw_breadth,
            "pit_residual_breadth_published": PUBLISHED_PIT_RESIDUAL_BREADTH,
            "pit_residual_breadth_reproduced": real_pit_breadth,
            "in_sample_residual_breadth_reproduced": real_in_sample_breadth,
        },
        "self_checks": {
            "factor_variance_identity": identity,
            "equicorrelation_algebra_E1": algebra,
        },
        "method_1_noise_injection_null": {
            "design": (
                "synthetic panels: 31 instruments, same T, exactly 6 true factors "
                "with the REAL fitted eigenvector loadings and REAL eigenvalue "
                "factor variances, plus idiosyncratic noise whose per-instrument "
                "variances are the REAL residual variance shares and whose "
                "correlation is equicorrelated with a rho chosen so the TRUE "
                "residual breadth is a known target. The identical merged "
                "walk-forward procedure is then run on them."
            ),
            "naive_iid_null_b_true_31": iid_rung,
            "calibration_ladder": rungs,
            "student_t_sensitivity": student_t,
        },
        "method_2_disjoint_sample": {
            "design": (
                "standardization moments, top-6 eigenvectors and per-instrument "
                "betas estimated on one sub-sample and applied with NO refitting "
                "to a strictly disjoint sub-sample, on which breadth is measured"
            ),
            "real_data": disjoint_real,
        },
        "inversion": inversion,
        "bias_corrected_estimates": estimates,
        "verdict": verdict,
        "judgment_calls": {
            "K1_k_equals_6_in_null": (
                "k=6 removed everywhere and the synthetic truth has exactly 6 "
                "factors -- the merged report's RMT-determined headline k, not "
                "hand-picked, but it makes the null FAVOURABLE to the procedure "
                "(the estimator is asked to find exactly the factors that exist). "
                "Kaiser-Guttman said 8 on the real data. Limitation, not corrected."
            ),
            "K2_gaussian_iid_innovations": (
                "Gaussian, i.i.d. in time. Real returns are fat-tailed and "
                "vol-clustered, which would add estimation noise and therefore "
                "MORE bias -- so this choice understates the bias. A Student-t(4) "
                "run at the operating point checks that claim rather than "
                "asserting it."
            ),
            "K3_ladder_and_seeds": (
                f"B_true ladder {list(B_TRUE_LADDER)}, {N_SEEDS} Monte-Carlo draws "
                "per rung. Ordinary choices, not from any source."
            ),
            "K4_block_size": (
                f"alternating-block design uses {BLOCK_DAYS}-day blocks; "
                f"sensitivity over {list(BLOCK_DAYS_SENSITIVITY)} reported."
            ),
            "K5_linear_interpolation_inversion": (
                "the calibration curve is inverted by linear interpolation over "
                "7 rungs; the raw ladder is printed so the interpolation can be "
                "checked rather than trusted."
            ),
            "K6_inherited": (
                "burn_in=504, refit_every=21, correlation PCA and k=6 are held "
                "fixed at the merged report's J1/J3/J4 values, because changing "
                "them would break comparability with the 16.9550 under audit."
            ),
            "K7_equicorrelation_shape": (
                "the synthetic idiosyncratic correlation is EQUICORRELATED. Real "
                "residual correlation is not equicorrelated -- it has structure. "
                "Equicorrelation is used because it is the shape whose effective "
                "breadth is analytically known and invertible (E1), which is what "
                "makes 'known true breadth' meaningful at all. Whether the "
                "estimator's bias depends on the SHAPE of residual correlation and "
                "not just its breadth is NOT tested here and is an open limitation."
            ),
        },
        "explicitly_not_done": [
            "no TSMOM signal built",
            "no DSR, no preservation_score, no mechanism-fidelity review",
            "no registration, no live-registration status change",
            "futures_effective_breadth.py and rmt_denoising.py NOT modified",
            "run_tsmom_factor_decomposition_2026_09_07.py NOT modified (imported)",
            "nothing pushed to origin",
        ],
    }
    OUT_JSON.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    # ---------------- human-readable report -------------------------------
    L: list[str] = []
    a = L.append
    a("=" * 78)
    a("TSMOM RESIDUAL-BREADTH BIAS QUANTIFICATION")
    a(f"generated {report['generated_at_utc']}")
    a("=" * 78)
    a("")
    a("MEASUREMENT ONLY. No TSMOM signal, no DSR, no preservation_score, no")
    a("mechanism-fidelity review, no registration, nothing pushed.")
    a("")
    a("WHAT IS BEING AUDITED")
    a("-" * 78)
    a("  tsmom_factor_decomposition_2026-09-07 (merged b8880c8) measured a")
    a("  point-in-time residual effective breadth of 16.9550 against a floor of")
    a("  15.0, and disclosed in its own text that the figure is OPTIMISTICALLY")
    a("  BIASED by an unquantified amount, because walk-forward estimation error")
    a("  in the factor betas leaks into the residuals as near-independent noise.")
    a("  It stated that quantifying that bias is REQUIRED before the gate result")
    a("  is relied on. This report is that quantification.")
    a("")
    a("TRIPWIRES (nothing below means anything if these fail)")
    a("-" * 78)
    a(f"  raw universe breadth  published {PUBLISHED_FUTURES_BREADTH:.12f}")
    a(f"                        reproduced {raw_breadth:.12f}")
    a(f"  PIT residual breadth  published {PUBLISHED_PIT_RESIDUAL_BREADTH:.4f}")
    a(f"                        reproduced {real_pit_breadth:.4f}")
    a(f"  in-sample residual breadth reproduced {real_in_sample_breadth:.4f}")
    a("")
    a("SELF-CHECKS")
    a("-" * 78)
    a(f"  factor-variance identity (f_j = Z v_j has var lambda_j): "
      f"max delta {identity['max_delta']:.3e}  OK")
    a(f"  equicorrelation algebra (E1) vs numpy eigvalsh: max delta "
      f"{max(c['delta'] for c in algebra):.3e}  OK")
    a(f"  mean real explained variance share (k=6): "
      f"{identity['mean_explained_variance_share']:.4f}")
    a(f"  mean real idiosyncratic variance share  : "
      f"{identity['mean_idiosyncratic_variance_share']:.4f}")
    a("")
    a("METHOD 1 -- NOISE-INJECTION NULL")
    a("=" * 78)
    a("")
    a("  Synthetic panels use the REAL fitted 6-factor loadings and the REAL")
    a("  eigenvalue factor variances and the REAL per-instrument residual")
    a("  variance shares. No loading magnitude is invented. The idiosyncratic")
    a("  correlation is equicorrelated with rho set so the TRUE residual breadth")
    a("  is a known target (identity E1, machine-checked above). The identical")
    a("  merged walk-forward code is then run on them.")
    a("")
    a("  THE NAIVE i.i.d. NULL (true residual breadth = 31, rho = 0)")
    a("  " + "-" * 74)
    a(f"    true breadth realized in finite samples : "
      f"{iid_rung['b_true_realized']['mean']:.4f}")
    a(f"    walk-forward PIT procedure reports      : "
      f"{iid_rung['pit_measured']['mean']:.4f}"
      f"  (sd {iid_rung['pit_measured']['sd']:.4f})")
    a(f"    BIAS                                    : "
      f"{iid_rung['pit_bias_vs_realized_truth']:+.4f}")
    a("")
    a("  CALIBRATION LADDER (this is the number that actually matters --")
    a("  the bias is not constant, so it must be evaluated NEAR 17, not at 31)")
    a("  " + "-" * 74)
    a("   B_true    rho      realized     PIT    PIT bias   halves   blocks")
    for r in rungs:
        a(f"   {r['b_true_population']:5.1f}  {r['rho']:.5f}  "
          f"{r['b_true_realized']['mean']:9.4f} {r['pit_measured']['mean']:8.4f}  "
          f"{r['pit_bias_vs_realized_truth']:+8.4f} "
          f"{r['disjoint_halves_measured']['mean']:8.4f} "
          f"{r['disjoint_blocks_measured']['mean']:8.4f}")
    a("")
    a(f"  Student-t({STUDENT_T_DF}) sensitivity at B_true=17 (K2):")
    a(f"    Gaussian PIT bias {student_t['gaussian_pit_bias_at_17']:+.4f}   "
      f"Student-t PIT bias {student_t['pit_bias']:+.4f}")
    a("")
    a("METHOD 2 -- DISJOINT-SAMPLE ESTIMATION (real data)")
    a("=" * 78)
    a("")
    h1 = disjoint_real["halves_first_estimates_second_tested"]
    h2 = disjoint_real["halves_second_estimates_first_tested"]
    bl = disjoint_real["block_alternating_252d"]
    a(f"  halves: estimate {h1['estimate_window'][0]}..{h1['estimate_window'][1]}"
      f" ({h1['n_estimate']} obs)")
    a(f"          test     {h1['test_window'][0]}..{h1['test_window'][1]}"
      f" ({h1['n_test']} obs)")
    a(f"          breadth  {h1['breadth']:.4f}")
    a(f"  halves REVERSED (second estimates, first tested)")
    a(f"          breadth  {h2['breadth']:.4f}")
    a(f"  alternating {BLOCK_DAYS}-day blocks (odd estimate, even tested)")
    a(f"          breadth  {bl['breadth']:.4f}")
    a("")
    a("  Block-size sensitivity (K4):")
    a("    block_days   odd->even    even->odd")
    for row in block_sensitivity:
        a(f"    {row['block_days']:>9}  {row['breadth_odd_estimates_even_tested']:10.4f}"
          f"  {row['breadth_even_estimates_odd_tested']:11.4f}")
    a("")
    a("  NOTE ON DIRECTION: the disjoint estimators are NOT clean either. They")
    a("  carry the SAME estimation-noise inflation as PIT (they estimate betas")
    a("  from a finite sample too), plus, for the halves design, a STALENESS")
    a("  deflation. That is exactly why they are run through the same synthetic")
    a("  calibration above rather than read as raw truth.")
    a("")
    a("INVERSION -- WHAT TRUE BREADTH WOULD PRODUCE THE OBSERVED NUMBERS")
    a("=" * 78)
    a("")
    for key, label in (
        ("pit_from_real_16_9550", "PIT walk-forward (the 16.9550 under audit)"),
        ("disjoint_blocks_from_real", "disjoint alternating blocks"),
        ("disjoint_halves_from_real", "disjoint halves (first->second)"),
        ("disjoint_halves_reverse_from_real", "disjoint halves (second->first)"),
    ):
        entry = inversion[key]
        val = entry.get("b_true_implied")
        shown = f"{val:.4f}" if val is not None else "OUT OF LADDER"
        a(f"  {label:<45} -> B_true {shown}")
        if val is None:
            a(f"      {entry['note']}")
    band = inversion["pit_from_real_16_9550_mc_band"]
    lo, hi = band["b_true_implied_minus_1se"], band["b_true_implied_plus_1se"]
    if lo is not None and hi is not None:
        a(f"  PIT inversion Monte-Carlo band (+/-1 SE of the ladder mean): "
          f"{lo:.4f} .. {hi:.4f}")
    a("      " + band["note"])
    a("")
    a("VERDICT")
    a("=" * 78)
    a("")
    a(f"  FLOOR = {EFFECTIVE_BREADTH_FLOOR}")
    for label, val in estimates.items():
        if val is None:
            a(f"  {label:<42} OUT OF LADDER")
        else:
            mark = ">= floor" if val >= EFFECTIVE_BREADTH_FLOOR else "<  floor"
            a(f"  {label:<42} {val:8.4f}  {mark}")
    a("")
    a(f"  VERDICT: {verdict}")
    a("")
    a("JUDGMENT CALLS")
    a("=" * 78)
    for key, text in report["judgment_calls"].items():
        a(f"  {key}:")
        line = "    "
        for word in text.split():
            if len(line) + len(word) + 1 > 76:
                a(line)
                line = "    "
            line += word + " "
        a(line.rstrip())
    a("")
    a("EXPLICITLY NOT DONE")
    a("=" * 78)
    for item in report["explicitly_not_done"]:
        a(f"  - {item}")
    a("")
    OUT_TXT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT_TXT}")
    print(f"wrote {OUT_JSON}")
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
