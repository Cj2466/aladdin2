"""LAST attempt at the residual-breadth bias question, plus a direct
measurement of real factor-loading drift.

WHY THIS EXISTS
====================================================================
tsmom_breadth_bias_quantification_2026-09-08 (merged 4ecd429) tried to
quantify whether the point-in-time residual breadth of 16.9550 is
optimistically biased. It returned UNRESOLVED because two stylized
idiosyncratic-correlation shapes (a diffuse weak-factor shape and an
asset-class-block shape) disagreed on the SIGN of the bias (-2.1453 vs
+4.5177).

Crucially, BOTH of those nulls FAILED a fidelity check. On the real data the
IN-SAMPLE residual breadth exceeds the PIT residual breadth by +2.0457
(19.0007 vs 16.9550). Neither null reproduced a gap larger than about +0.01.
A null whose assumed correlation SHAPE cannot reproduce a known, measurable
feature of the real data has no business correcting that data's numbers.

The project owner authorized ONE more targeted attempt, aimed directly at
that fidelity failure, and explicitly stated it is the LAST attempt at this
sub-question. This script is that attempt. It does two things:

PART A -- DIRECT MEASUREMENT OF REAL FACTOR-LOADING DRIFT (no null at all)
    The prior report SPECULATED that the fidelity failure is caused by real
    factor loadings drifting over time while the null's are held constant.
    That was an inference from a null's failure, never a measurement. Here
    the real walk-forward top-k eigenvector subspace is recomputed at every
    21-day refit boundary and compared to its own predecessor and to the
    first refit, using principal angles between subspaces. This is a direct,
    real fact about the data.

    A raw drift number alone is not interpretable, because a walk-forward
    estimate wobbles from pure sampling noise even when the truth is
    perfectly constant. So the identical drift measurement is ALSO run on
    synthetic panels whose true loadings are CONSTANT BY CONSTRUCTION. The
    difference between real drift and constant-truth drift is the part that
    cannot be sampling noise.

PART B -- EMPIRICALLY-CALIBRATED NULL
    Instead of assuming a stylized residual-correlation shape, the null's
    idiosyncratic correlation is calibrated to the REAL in-sample residual
    correlation matrix itself. That matrix's aggregate breadth is inflated by
    the orthogonality identity and is not trustworthy as a bias-free estimate
    of the truth -- but its SHAPE (the pattern of which instruments retain
    correlation with which) is the best empirical information available, and
    is what the two prior stylized shapes were guessing at.

    The pre-declared decision rule, written before the numbers were seen:
      - If this null reproduces the real +2.0457 in-sample-minus-PIT gap
        (tolerance below), its calibration ladder may be inverted and the
        resulting bias-corrected breadth reported as trustworthy.
      - If it does NOT, the conclusion is that the mismatch is about
        correlation DYNAMICS, not cross-sectional shape -- a static-DGP null
        structurally cannot reproduce drifting loadings no matter how well
        its cross-section is calibrated. Combined with Part A's direct
        measurement, that is a CONCLUSIVE end to this line of inquiry rather
        than another inconclusive shrug.

    Either way this is the last attempt. No further shape variations.

WHAT IS REUSED VERSUS WHAT IS NEW
====================================================================
REUSED, IMPORTED, NOT MODIFIED (this is what keeps every number comparable
to the merged 10.0081 / 16.9550 / 19.0007 figures):
  - app/services/research_lab/futures_effective_breadth.py
  - app/services/risk/rmt_denoising.py (reached through the above chain)
  - run_tsmom_factor_decomposition_2026_09_07.py -- `residualize_pit`,
    `residualize_in_sample`, `measure`, `spectrum`, `_standardize`,
    `_import_gate_script`. The walk-forward procedure under test is literally
    the merged code, not a re-implementation.
  - run_tsmom_breadth_bias_quantification_2026_09_08.py -- `TrueStructure`
    (the real fitted 6-factor structure) and `residualize_disjoint`.
  - measure_futures_breadth_2026_09_07.py -- reached through the above, so
    the return panel comes from the same loader that produced 10.0081.

NEW HERE: the principal-angle drift measurement (Part A), the
constant-truth drift baseline, the empirical-shape correlation family and
its ladder (Part B).

THE EMPIRICAL SHAPE FAMILY (L3)
====================================================================
Let R_hat be the correlation matrix of the real in-sample k=6 residual panel
(31 x 31, unit diagonal, breadth 19.0007 by construction). Eigendecompose
R_hat = V diag(lambda) V'. The family is

    R(g) = normalize( V diag(lambda ** g) V' )          (L3)

where `normalize` rescales to unit diagonal. Properties, all checked in code
rather than asserted:
  - g = 1 returns R_hat exactly, so the real empirical shape is ON the ladder,
    not merely near it.
  - The EIGENVECTORS -- i.e. the shape, which instrument correlates with
    which -- are identical at every g. Only the spectrum is sharpened (g > 1,
    more concentrated, lower breadth) or flattened (g < 1, higher breadth).
    So a ladder in g is a ladder in breadth that holds shape fixed, which is
    exactly what a calibration ladder must do.
  - lambda >= 0 for all g > 0, so every R(g) is PSD.
  - The true breadth of each rung is computed exactly by eigendecomposition
    of a matrix known in closed form, so "known true breadth" is exact.

R_hat is RANK DEFICIENT: in-sample residualization against k factors plus an
intercept annihilates 7 dimensions exactly, so R_hat has 7 zero eigenvalues.
This is not a defect to be patched away -- it IS the orthogonality identity
the prior report named. Two consequences, both handled explicitly:
  - Sampling from a singular covariance is done by the eigen route
    (X = Z diag(sqrt(lambda^g)) V'), which is exact for rank-deficient
    matrices, rather than by Cholesky, which would fail.
  - As g -> 0+ the nonzero eigenvalues all approach 1 while the zeros stay 0,
    so the family's breadth ceiling is the RANK, not n. The ladder therefore
    cannot reach 31 under the pure empirical shape. A second, "de-degenerated"
    variant (L4) floors the zero eigenvalues at a small epsilon before the
    family is built, which restores the full range and tests whether the exact
    rank deficiency is doing the work.

JUDGMENT CALLS (all flagged, none hidden)
====================================================================
  L1. Gaussian innovations, i.i.d. in time, matching K2 of the prior script
      so the two are comparable. Real returns are fat-tailed and
      vol-clustered.
  L2. Monte-Carlo draws per rung and the ladder of target breadths are
      ordinary choices, not from any source. Set below as N_SEEDS /
      B_TRUE_LADDER.
  L3. The eigenvalue-power family above is THIS SCRIPT'S OWN construction,
      not a technique quoted from any paper. It is chosen because it is the
      only simple family that holds the empirical eigenvector shape EXACTLY
      fixed while moving breadth in both directions.
  L4. The epsilon used to de-degenerate R_hat in the robustness variant is an
      arbitrary small number; results are reported for both variants.
  L5. Fidelity tolerance: the null is judged to reproduce the real
      in-sample-minus-PIT gap if it lands within FIDELITY_TOL of +2.0457.
      The same 1.0 threshold the prior merged script used, kept identical so
      this attempt is not graded on a softer curve than the one it follows.
      PRE-DECLARED before any number here was computed.
  L6. Drift is measured as the largest principal angle between consecutive
      top-k eigenvector SUBSPACES, plus the mean cosine similarity of the
      matched directions. Subspace angles are used rather than raw
      eigenvector comparisons because eigenvectors have arbitrary sign and
      can swap order when eigenvalues are close, which would manufacture
      fake drift. Principal angles are invariant to both.
  L7. Everything inherits the merged report's J1/J3/J4 (burn_in=504,
      refit_every=21, correlation PCA, k=6). Changing them would break
      comparability with 16.9550.
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

_HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str) -> Any:
    path = _HERE / filename
    if not path.exists():
        raise SystemExit(f"required merged script not found at {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DECOMP = _load("_tsmom_decomp", "run_tsmom_factor_decomposition_2026_09_07.py")
BIASQ = _load("_tsmom_biasq", "run_tsmom_breadth_bias_quantification_2026_09_08.py")

# Figures under audit, from the merged reports (b8880c8 / 4ecd429).
PUBLISHED_FUTURES_BREADTH = DECOMP.PUBLISHED_FUTURES_BREADTH
PUBLISHED_PIT_RESIDUAL_BREADTH = 16.9550
PUBLISHED_IN_SAMPLE_RESIDUAL_BREADTH = 19.0007

K_FACTORS = DECOMP.K_SWEEP_MAX  # 6 (L7)
BURN_IN_DAYS = DECOMP.BURN_IN_DAYS  # 504 (L7)
REFIT_EVERY_DAYS = DECOMP.REFIT_EVERY_DAYS  # 21 (L7)

N_SEEDS = 40  # L2
B_TRUE_LADDER = (24.0, 22.0, 20.0, 19.0, 17.0, 15.0, 13.0, 11.0)  # L2
DEGENERACY_EPS = 1e-3  # L4
FIDELITY_TOL = 1.0  # L5, pre-declared, identical to the prior script's threshold
N_DRIFT_SEEDS = 12  # L2, constant-truth drift baseline draws

OUT_TXT = _BACKEND / "data" / "research_runs" / "tsmom_breadth_loading_drift_2026-09-08.txt"
OUT_JSON = _BACKEND / "data" / "research_runs" / "tsmom_breadth_loading_drift_2026-09-08.json"


# --------------------------------------------------------------------------
# PART A -- principal-angle drift measurement (L6)
# --------------------------------------------------------------------------
def principal_angles(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Principal angles (radians, ascending) between the column spaces of two
    matrices with orthonormal columns.

    Bjorck & Golub (1973), "Numerical Methods for Computing Angles Between
    Linear Subspaces", Math. Comp. 27(123), 579-594 -- the SVD formulation:
    the singular values of A'B are the cosines of the principal angles. Used
    here for its sign- and order-invariance (L6), and machine-checked below
    against cases with known answers rather than trusted from memory.
    """
    s = np.linalg.svd(a.T @ b, compute_uv=False)
    return np.arccos(np.clip(s, -1.0, 1.0))


def verify_principal_angles() -> list[dict[str, Any]]:
    """Self-check the angle routine against constructions with KNOWN answers.
    If this fails every drift number below is meaningless."""
    checks: list[dict[str, Any]] = []
    rng = np.random.default_rng(11)
    n, k = 31, 6
    q, _ = np.linalg.qr(rng.standard_normal((n, k)))

    # 1. A subspace against itself: all angles zero.
    ang = principal_angles(q, q)
    checks.append(
        {
            "case": "identical_subspace_angles_are_zero",
            "max_angle_deg": float(np.degrees(ang).max()),
            "holds": bool(np.degrees(ang).max() < 1e-6),
        }
    )
    # 2. Sign flips and column reordering must change NOTHING (this is the
    #    whole reason principal angles are used instead of raw eigenvectors).
    q2 = q.copy()
    q2[:, 0] *= -1.0
    q2 = q2[:, ::-1]
    ang = principal_angles(q, q2)
    checks.append(
        {
            "case": "sign_flip_and_reorder_invariance",
            "max_angle_deg": float(np.degrees(ang).max()),
            "holds": bool(np.degrees(ang).max() < 1e-6),
        }
    )
    # 3. A known 30-degree rotation of one basis direction out of the subspace.
    theta = np.radians(30.0)
    q_full, _ = np.linalg.qr(rng.standard_normal((n, k + 1)))
    a = q_full[:, :k]
    b = a.copy()
    b[:, 0] = np.cos(theta) * q_full[:, 0] + np.sin(theta) * q_full[:, k]
    b, _ = np.linalg.qr(b)
    ang = principal_angles(a, b)
    checks.append(
        {
            "case": "known_30_degree_rotation",
            "expected_max_angle_deg": 30.0,
            "max_angle_deg": float(np.degrees(ang).max()),
            "holds": bool(abs(np.degrees(ang).max() - 30.0) < 1e-6),
        }
    )
    # 4. Orthogonal subspaces: 90 degrees.
    base3 = q_full[:, :3]
    ang = principal_angles(base3, _orth_complement(base3, 3, rng))
    checks.append(
        {
            "case": "orthogonal_subspaces_are_90_deg",
            "min_angle_deg": float(np.degrees(ang).min()),
            "holds": bool(abs(np.degrees(ang).min() - 90.0) < 1e-6),
        }
    )
    return checks


def _orth_complement(basis: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    n = basis.shape[0]
    x = rng.standard_normal((n, k))
    x = x - basis @ (basis.T @ x)
    q, _ = np.linalg.qr(x)
    return q


def walk_forward_loadings(
    common: pd.DataFrame,
    k: int,
    burn_in: int = BURN_IN_DAYS,
    refit_every: int = REFIT_EVERY_DAYS,
) -> list[dict[str, Any]]:
    """Recompute, at every refit boundary, exactly the loadings that
    `DECOMP.residualize_pit` uses internally.

    This deliberately MIRRORS the merged `residualize_pit` estimation block
    line for line (expanding prior window, z-score on prior moments, corrcoef,
    eigh, sort descending, take top-k) rather than editing that function to
    return them, because the merged file must stay byte-identical. The mirror
    is verified against the merged function's own output downstream: the
    residuals rebuilt from these loadings must equal `residualize_pit`'s to
    machine precision, or this function is wrong and the script aborts.
    """
    values = common.to_numpy()
    n_obs, _n_inst = values.shape
    out: list[dict[str, Any]] = []

    start = burn_in
    while start < n_obs:
        stop = min(start + refit_every, n_obs)
        prior = values[:start]
        mean = prior.mean(axis=0)
        std = prior.std(axis=0, ddof=1)
        if np.any(std <= 0) or not np.all(np.isfinite(std)):
            start = stop
            continue
        z_prior = (prior - mean) / std
        corr_prior = np.corrcoef(z_prior, rowvar=False)
        eigvals, eigvecs = np.linalg.eigh(corr_prior)
        order = np.argsort(eigvals)[::-1]
        out.append(
            {
                "row_start": int(start),
                "row_stop": int(stop),
                "date": str(common.index[start].date()),
                "n_prior_obs": int(start),
                "loadings": eigvecs[:, order][:, :k],
                "eigenvalues_topk": eigvals[order][:k].copy(),
            }
        )
        start = stop
    return out


def verify_loading_mirror(common: pd.DataFrame, k: int) -> dict[str, Any]:
    """Rebuild the PIT residual panel from `walk_forward_loadings` and require
    it to match the MERGED `residualize_pit` output to machine precision.

    If this holds, the loadings measured for drift really are the loadings the
    published 16.9550 was produced with -- not a lookalike."""
    values = common.to_numpy()
    n_obs, n_inst = values.shape
    out = np.full((n_obs, n_inst), np.nan)
    for fit in walk_forward_loadings(common, k):
        start, stop = fit["row_start"], fit["row_stop"]
        prior = values[:start]
        mean = prior.mean(axis=0)
        std = prior.std(axis=0, ddof=1)
        z_prior = (prior - mean) / std
        loadings = fit["loadings"]
        factors_prior = z_prior @ loadings
        design_prior = np.column_stack([np.ones(len(z_prior)), factors_prior])
        coef, *_ = np.linalg.lstsq(design_prior, z_prior, rcond=None)
        block = (values[start:stop] - mean) / std
        design_block = np.column_stack([np.ones(len(block)), block @ loadings])
        out[start:stop] = block - design_block @ coef

    mirrored = pd.DataFrame(out, index=common.index, columns=common.columns).dropna(
        how="all"
    )
    merged = DECOMP.residualize_pit(common, k)
    aligned = merged.loc[mirrored.index, mirrored.columns]
    delta = float(np.abs(mirrored.to_numpy() - aligned.to_numpy()).max())
    return {
        "max_abs_delta_vs_merged_residualize_pit": delta,
        "holds": bool(delta < 1e-10),
        "n_rows_compared": len(mirrored),
    }


def drift_summary(fits: list[dict[str, Any]], k: int) -> dict[str, Any]:
    """Quantify how much the top-k subspace moves across refits."""
    consecutive_max: list[float] = []
    consecutive_mean_cos: list[float] = []
    vs_first_max: list[float] = []

    first = fits[0]["loadings"]
    for i in range(1, len(fits)):
        ang = principal_angles(fits[i - 1]["loadings"], fits[i]["loadings"])
        consecutive_max.append(float(np.degrees(ang).max()))
        consecutive_mean_cos.append(float(np.cos(ang).mean()))
        vs_first_max.append(float(np.degrees(principal_angles(first, fits[i]["loadings"])).max()))

    first_vs_last = principal_angles(first, fits[-1]["loadings"])
    return {
        "n_refits": len(fits),
        "k": k,
        "consecutive_max_principal_angle_deg": {
            "mean": float(np.mean(consecutive_max)),
            "median": float(np.median(consecutive_max)),
            "p95": float(np.percentile(consecutive_max, 95)),
            "max": float(np.max(consecutive_max)),
        },
        "consecutive_mean_cosine_similarity": {
            "mean": float(np.mean(consecutive_mean_cos)),
            "min": float(np.min(consecutive_mean_cos)),
        },
        "first_vs_last_principal_angles_deg": [
            float(v) for v in np.degrees(first_vs_last)
        ],
        "first_vs_last_max_angle_deg": float(np.degrees(first_vs_last).max()),
        "first_vs_last_mean_cosine": float(np.cos(first_vs_last).mean()),
        "cumulative_vs_first_max_angle_deg_final": vs_first_max[-1],
        "cumulative_vs_first_max_angle_deg_path": vs_first_max,
    }


# --------------------------------------------------------------------------
# PART B -- the empirical-shape correlation family (L3)
# --------------------------------------------------------------------------
def _normalize_to_unit_diagonal(mat: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.diag(mat))
    return mat / np.outer(d, d)


class EmpiricalShape:
    """Idiosyncratic correlation calibrated to the REAL in-sample residual
    correlation matrix (L3).

        R(g) = normalize( V diag(lambda ** g) V' ),  R(1) == R_hat exactly.

    Eigenvectors -- the shape -- are identical at every g; only the spectrum
    is sharpened or flattened. This is the whole point: the two prior nulls
    were GUESSING at this shape, and both guesses failed the fidelity check.
    """

    def __init__(self, r_hat: np.ndarray, eps: float | None = None):
        self.n = r_hat.shape[0]
        self.r_hat = r_hat
        lam, vec = np.linalg.eigh(r_hat)
        lam = np.clip(lam, 0.0, None)
        self.eps = eps
        if eps is not None:
            # L4: de-degenerated variant -- floor the exact zeros so the family
            # can reach breadths above the rank ceiling.
            lam = np.clip(lam, eps, None)
        self.lam = lam
        self.vec = vec
        self.rank = int((lam > 1e-9).sum())

    def corr(self, g: float) -> np.ndarray:
        powered = np.where(self.lam > 0, self.lam ** g, 0.0)
        mat = (self.vec * powered) @ self.vec.T
        mat = 0.5 * (mat + mat.T)
        return _normalize_to_unit_diagonal(mat)

    def factor_root(self, g: float) -> np.ndarray:
        """A matrix S with S S' == R(g), valid even when R(g) is singular.

        Used for sampling instead of Cholesky, which fails on a rank-deficient
        matrix. Machine-checked in `verify_shape_family`.
        """
        powered = np.where(self.lam > 0, self.lam ** g, 0.0)
        raw = self.vec * np.sqrt(powered)
        d = np.sqrt(np.diag((self.vec * powered) @ self.vec.T))
        return raw / d[:, None]

    def breadth(self, g: float) -> float:
        lam = np.linalg.eigvalsh(self.corr(g))
        lam = np.clip(lam, 0.0, None)
        return float(lam.sum() ** 2 / (lam**2).sum())

    def breadth_ceiling(self) -> float:
        return self.breadth(1e-6)

    def g_for_breadth(self, target: float) -> float | None:
        """Root-find g. Returns None when the target is outside the family's
        reachable range -- reported rather than silently clamped."""
        lo, hi = 1e-6, 1.0
        if self.breadth(lo) < target:
            return None  # above the family's ceiling
        while self.breadth(hi) > target:
            hi *= 1.5
            if hi > 1e4:
                return None
        return float(brentq(lambda g: self.breadth(g) - target, lo, hi))


def verify_shape_family(shape: EmpiricalShape, r_hat: np.ndarray) -> dict[str, Any]:
    """Self-checks the empirical family must pass or nothing below is valid."""
    r1 = shape.corr(1.0)
    recovers = float(np.abs(r1 - r_hat).max())
    s = shape.factor_root(1.0)
    root_ok = float(np.abs(s @ s.T - r1).max())
    diag_ok = float(np.abs(np.diag(r1) - 1.0).max())
    lam_mid = np.linalg.eigvalsh(shape.corr(2.0))
    psd_ok = float(lam_mid.min())
    # Breadth must be strictly decreasing in g for the root-find to be valid.
    gs = [0.25, 0.5, 1.0, 2.0, 4.0]
    bs = [shape.breadth(g) for g in gs]
    monotone = all(bs[i] > bs[i + 1] for i in range(len(bs) - 1))
    return {
        "R(1)_recovers_R_hat_max_delta": recovers,
        "factor_root_SS'_equals_R_max_delta": root_ok,
        "unit_diagonal_max_delta": diag_ok,
        "min_eigenvalue_at_g2": psd_ok,
        "breadth_monotone_decreasing_in_g": monotone,
        "breadth_at_g": dict(zip([str(g) for g in gs], bs, strict=True)),
        "rank_of_R_hat": shape.rank,
        "n": shape.n,
        "breadth_ceiling_of_family": shape.breadth_ceiling(),
        "holds": bool(
            recovers < 1e-9
            and root_ok < 1e-9
            and diag_ok < 1e-9
            and psd_ok > -1e-9
            and monotone
        ),
    }


def simulate_with_shape(
    truth: Any,
    root: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Same DGP as the prior script's `TrueStructure.simulate`, but sampling
    the idiosyncratic block through an explicit factor root so a SINGULAR
    target correlation is handled exactly (Cholesky cannot be used here).

    observed = F L' + diag(s) * (Z S')      with F ~ N(0, diag(lambda_topk))
    """
    t, n, k = truth.t, truth.n, truth.k
    factors = rng.standard_normal((t, k)) * np.sqrt(truth.factor_var)
    idio = (rng.standard_normal((t, n)) @ root.T) * np.sqrt(truth.idio_var)
    observed = factors @ truth.loadings.T + idio
    return observed, idio


def _breadth(panel: pd.DataFrame) -> float:
    return float(DECOMP.measure(panel)["breadth_eigenvalue"])


def _as_frame(values: np.ndarray, index: pd.Index, columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(values, index=index, columns=columns)


def _interp_invert(ladder: list[tuple[float, float]], measured: float) -> dict[str, Any]:
    """Invert a monotone (B_true -> mean B_measured) ladder by linear
    interpolation. Same routine as the prior script's K5."""
    xs = [b for b, _ in ladder]
    ys = [m for _, m in ladder]
    monotone = all(ys[i] < ys[i + 1] for i in range(len(ys) - 1))
    if measured <= ys[0]:
        return {
            "b_true_implied": None,
            "note": (
                f"measured {measured:.4f} is at or below the lowest rung's mean "
                f"measured value {ys[0]:.4f}; outside the ladder"
            ),
            "calibration_is_monotone": monotone,
        }
    if measured >= ys[-1]:
        return {
            "b_true_implied": None,
            "note": (
                f"measured {measured:.4f} is at or above the highest rung's mean "
                f"measured value {ys[-1]:.4f}; outside the ladder"
            ),
            "calibration_is_monotone": monotone,
        }
    return {
        "b_true_implied": float(np.interp(measured, ys, xs)),
        "note": "linear interpolation on the calibration ladder",
        "calibration_is_monotone": monotone,
    }


# --------------------------------------------------------------------------
def main() -> None:
    started = datetime.now(UTC)
    gate = DECOMP._import_gate_script()
    panel = gate.load_return_panel()
    common = panel.dropna(how="any")
    n = common.shape[1]
    columns = list(common.columns)
    index = common.index
    print(f"common window {common.shape[0]} x {n}: "
          f"{index.min().date()} .. {index.max().date()}")

    # ---- TRIPWIRES: reproduce the merged figures before anything else ------
    raw_breadth = _breadth(panel)
    if abs(raw_breadth - PUBLISHED_FUTURES_BREADTH) > 1e-9:
        raise SystemExit(
            f"REFUSING TO CONTINUE: raw breadth {raw_breadth} != published "
            f"{PUBLISHED_FUTURES_BREADTH}"
        )
    real_pit = DECOMP.residualize_pit(common, K_FACTORS)
    real_pit_breadth = _breadth(real_pit)
    real_in_sample = DECOMP.residualize_in_sample(common, K_FACTORS)
    real_in_sample_breadth = _breadth(real_in_sample)
    if abs(real_pit_breadth - PUBLISHED_PIT_RESIDUAL_BREADTH) > 5e-4:
        raise SystemExit(
            f"REFUSING TO CONTINUE: PIT residual breadth {real_pit_breadth} does "
            f"not reproduce the published {PUBLISHED_PIT_RESIDUAL_BREADTH}"
        )
    if abs(real_in_sample_breadth - PUBLISHED_IN_SAMPLE_RESIDUAL_BREADTH) > 5e-4:
        raise SystemExit(
            f"REFUSING TO CONTINUE: in-sample residual breadth "
            f"{real_in_sample_breadth} does not reproduce the published "
            f"{PUBLISHED_IN_SAMPLE_RESIDUAL_BREADTH}"
        )
    real_gap = real_in_sample_breadth - real_pit_breadth
    print(f"tripwires OK: raw {raw_breadth:.6f}, PIT {real_pit_breadth:.4f}, "
          f"IS {real_in_sample_breadth:.4f}, gap {real_gap:+.4f}")

    # ======================================================================
    # PART A -- DIRECT MEASUREMENT OF REAL FACTOR-LOADING DRIFT
    # ======================================================================
    angle_checks = verify_principal_angles()
    if not all(c["holds"] for c in angle_checks):
        raise SystemExit(f"principal-angle routine failed self-check: {angle_checks}")
    mirror = verify_loading_mirror(common, K_FACTORS)
    if not mirror["holds"]:
        raise SystemExit(
            f"loading mirror does not reproduce merged residualize_pit: {mirror}"
        )
    print(f"self-checks OK: principal angles + loading mirror "
          f"(delta {mirror['max_abs_delta_vs_merged_residualize_pit']:.2e})")

    real_fits = walk_forward_loadings(common, K_FACTORS)
    real_drift = drift_summary(real_fits, K_FACTORS)
    print(f"PART A real drift: {real_drift['n_refits']} refits, consecutive max "
          f"angle mean {real_drift['consecutive_max_principal_angle_deg']['mean']:.2f} deg, "
          f"first-vs-last max {real_drift['first_vs_last_max_angle_deg']:.2f} deg")

    # Drift for individual factors (k=1..6 subspaces) -- is the drift in the
    # dominant factor or only in the weak, nearly-degenerate ones?
    drift_by_k = []
    for kk in range(1, K_FACTORS + 1):
        fits_k = [
            {**f, "loadings": f["loadings"][:, :kk]} for f in real_fits
        ]
        d = drift_summary(fits_k, kk)
        drift_by_k.append(
            {
                "k": kk,
                "consecutive_max_angle_deg_mean": d[
                    "consecutive_max_principal_angle_deg"
                ]["mean"],
                "first_vs_last_max_angle_deg": d["first_vs_last_max_angle_deg"],
                "first_vs_last_mean_cosine": d["first_vs_last_mean_cosine"],
            }
        )

    # ---- CONSTANT-TRUTH DRIFT BASELINE ------------------------------------
    # A walk-forward estimate wobbles even when the truth never moves. Measure
    # that wobble on synthetic panels whose loadings are CONSTANT by
    # construction, so real drift can be compared against pure sampling noise.
    truth = BIASQ.TrueStructure(common, K_FACTORS)
    identity = truth.identity_check(common)
    if not identity["holds"]:
        raise SystemExit(f"factor-variance identity failed: {identity}")

    r_hat = real_in_sample.corr().to_numpy()
    shape = EmpiricalShape(r_hat)
    shape_checks = verify_shape_family(shape, r_hat)
    if not shape_checks["holds"]:
        raise SystemExit(f"empirical shape family failed self-check: {shape_checks}")
    print(f"empirical shape OK: rank {shape.rank}/{n}, family breadth ceiling "
          f"{shape_checks['breadth_ceiling_of_family']:.4f}, R(1)==R_hat")

    root_g1 = shape.factor_root(1.0)
    const_drift_runs = []
    for seed in range(N_DRIFT_SEEDS):
        rng = np.random.default_rng(90260908 + seed)
        observed, _idio = simulate_with_shape(truth, root_g1, rng)
        obs_df = _as_frame(observed, index, columns)
        fits = walk_forward_loadings(obs_df, K_FACTORS)
        d = drift_summary(fits, K_FACTORS)
        const_drift_runs.append(
            {
                "consecutive_max_angle_deg_mean": d[
                    "consecutive_max_principal_angle_deg"
                ]["mean"],
                "first_vs_last_max_angle_deg": d["first_vs_last_max_angle_deg"],
                "first_vs_last_mean_cosine": d["first_vs_last_mean_cosine"],
            }
        )

    def _agg(key: str) -> dict[str, float]:
        arr = np.array([r[key] for r in const_drift_runs])
        return {
            "mean": float(arr.mean()),
            "sd": float(arr.std(ddof=1)),
            "p05": float(np.percentile(arr, 5)),
            "p95": float(np.percentile(arr, 95)),
            "max": float(arr.max()),
        }

    const_drift = {
        "n_draws": N_DRIFT_SEEDS,
        "note": (
            "synthetic panels whose TRUE loadings never move; any measured "
            "angle here is pure walk-forward sampling noise"
        ),
        "consecutive_max_angle_deg_mean": _agg("consecutive_max_angle_deg_mean"),
        "first_vs_last_max_angle_deg": _agg("first_vs_last_max_angle_deg"),
        "first_vs_last_mean_cosine": _agg("first_vs_last_mean_cosine"),
    }
    drift_excess_consecutive = (
        real_drift["consecutive_max_principal_angle_deg"]["mean"]
        - const_drift["consecutive_max_angle_deg_mean"]["mean"]
    )
    drift_excess_first_last = (
        real_drift["first_vs_last_max_angle_deg"]
        - const_drift["first_vs_last_max_angle_deg"]["mean"]
    )
    real_exceeds_noise_envelope = bool(
        real_drift["first_vs_last_max_angle_deg"]
        > const_drift["first_vs_last_max_angle_deg"]["max"]
    )
    print(f"PART A baseline: constant-truth first-vs-last max angle "
          f"{const_drift['first_vs_last_max_angle_deg']['mean']:.2f} deg "
          f"(max over draws {const_drift['first_vs_last_max_angle_deg']['max']:.2f}); "
          f"real excess {drift_excess_first_last:+.2f} deg")

    # ======================================================================
    # PART B -- EMPIRICALLY-CALIBRATED NULL
    # ======================================================================
    def build_ladder(shape_obj: EmpiricalShape, label: str, seed_offset: int) -> list[dict[str, Any]]:
        rungs: list[dict[str, Any]] = []
        for b_true in B_TRUE_LADDER:
            g = shape_obj.g_for_breadth(b_true)
            if g is None:
                rungs.append(
                    {
                        "b_true_population": b_true,
                        "g": None,
                        "unreachable": True,
                        "note": "target breadth outside this family's reachable range",
                    }
                )
                print(f"  [{label}] B_true={b_true:5.1f} UNREACHABLE")
                continue
            corr_e = shape_obj.corr(g)
            root = shape_obj.factor_root(g)
            lam1 = float(np.linalg.eigvalsh(corr_e).max())
            panel_units = lam1 * float(truth.idio_var.mean())
            sixth = float(truth.factor_var[K_FACTORS - 1])
            true_v, pit_v, is_v = [], [], []
            for seed in range(N_SEEDS):
                rng = np.random.default_rng(seed_offset + 1000 * int(b_true * 10) + seed)
                observed, idio = simulate_with_shape(truth, root, rng)
                obs_df = _as_frame(observed, index, columns)
                true_v.append(_breadth(_as_frame(idio, index, columns)))
                pit_v.append(_breadth(DECOMP.residualize_pit(obs_df, K_FACTORS)))
                is_v.append(_breadth(DECOMP.residualize_in_sample(obs_df, K_FACTORS)))

            def summ(vals: list[float]) -> dict[str, float]:
                arr = np.array(vals)
                return {
                    "mean": float(arr.mean()),
                    "sd": float(arr.std(ddof=1)),
                    "p05": float(np.percentile(arr, 5)),
                    "p95": float(np.percentile(arr, 95)),
                }

            rr = {
                "b_true_population": b_true,
                "g": g,
                "unreachable": False,
                "idio_top_eigenvalue": lam1,
                "idio_top_eigenvalue_in_panel_variance_units": panel_units,
                "sixth_real_factor_eigenvalue": sixth,
                "contaminated": bool(panel_units > sixth),
                "b_true_realized": summ(true_v),
                "pit_measured": summ(pit_v),
                "in_sample_measured": summ(is_v),
            }
            rr["pit_bias_vs_realized_truth"] = (
                rr["pit_measured"]["mean"] - rr["b_true_realized"]["mean"]
            )
            rr["in_sample_minus_pit"] = (
                rr["in_sample_measured"]["mean"] - rr["pit_measured"]["mean"]
            )
            rungs.append(rr)
            print(
                f"  [{label}] B_true={b_true:5.1f} g={g:6.3f} realized="
                f"{rr['b_true_realized']['mean']:7.4f}  PIT="
                f"{rr['pit_measured']['mean']:7.4f} (bias "
                f"{rr['pit_bias_vs_realized_truth']:+.4f})  IS="
                f"{rr['in_sample_measured']['mean']:7.4f}  IS-PIT="
                f"{rr['in_sample_minus_pit']:+.4f}  contam={rr['contaminated']}"
            )
        return rungs

    print("PART B ladder -- empirical shape (R(1) == real in-sample residual corr):")
    rungs = build_ladder(shape, "empirical", 20260908)

    shape_eps = EmpiricalShape(r_hat, eps=DEGENERACY_EPS)
    shape_eps_checks = verify_shape_family(shape_eps, r_hat)
    print(f"PART B ladder -- de-degenerated variant (eps={DEGENERACY_EPS}, L4):")
    rungs_eps = build_ladder(shape_eps, "empirical-eps", 60260908)

    # ---- THE FIDELITY CHECK (L5, pre-declared) ----------------------------
    usable = [r for r in rungs if not r["unreachable"]]
    ladder_sorted = sorted(usable, key=lambda r: r["b_true_realized"]["mean"])
    pit_ladder = [
        (r["b_true_realized"]["mean"], r["pit_measured"]["mean"]) for r in ladder_sorted
    ]
    is_ladder = [
        (r["b_true_realized"]["mean"], r["in_sample_measured"]["mean"])
        for r in ladder_sorted
    ]
    inversion = _interp_invert(pit_ladder, real_pit_breadth)
    pit_implied = inversion["b_true_implied"]

    predicted_in_sample = (
        float(np.interp(pit_implied, [x for x, _ in is_ladder], [y for _, y in is_ladder]))
        if pit_implied is not None
        else None
    )
    null_gap = (
        predicted_in_sample - real_pit_breadth if predicted_in_sample is not None else None
    )
    # If the inversion lands outside the ladder, the fidelity question is still
    # answerable directly: take the rung whose measured PIT is closest to the
    # real 16.9550 and read its own IS-PIT gap.
    nearest_rung = min(
        usable, key=lambda r: abs(r["pit_measured"]["mean"] - real_pit_breadth)
    )
    nearest_gap = nearest_rung["in_sample_minus_pit"]

    fidelity_gap_used = null_gap if null_gap is not None else nearest_gap
    fidelity_error = abs(fidelity_gap_used - real_gap)
    fidelity_passes = bool(fidelity_error <= FIDELITY_TOL)

    # Same question asked of the de-degenerated variant.
    usable_eps = [r for r in rungs_eps if not r["unreachable"]]
    nearest_rung_eps = (
        min(usable_eps, key=lambda r: abs(r["pit_measured"]["mean"] - real_pit_breadth))
        if usable_eps
        else None
    )
    eps_gap = nearest_rung_eps["in_sample_minus_pit"] if nearest_rung_eps else None
    eps_fidelity_passes = (
        bool(abs(eps_gap - real_gap) <= FIDELITY_TOL) if eps_gap is not None else None
    )

    # Best gap ANY rung of either ladder achieves -- so the conclusion is about
    # the family as a whole, not one interpolation point.
    all_gaps = [r["in_sample_minus_pit"] for r in usable + usable_eps]
    best_gap = max(all_gaps) if all_gaps else None

    print(f"FIDELITY: real IS-PIT gap {real_gap:+.4f}; empirical null "
          f"{fidelity_gap_used:+.4f} (error {fidelity_error:.4f}, "
          f"tol {FIDELITY_TOL}) -> passes={fidelity_passes}")

    # ---- VERDICT ----------------------------------------------------------
    reasons: list[str] = []
    if fidelity_passes:
        verdict = "RESOLVED_TRUSTWORTHY_CORRECTION" if pit_implied is not None else "PARTIALLY_RESOLVED"
        reasons.append(
            "The empirically-calibrated null REPRODUCES the real data's "
            f"in-sample-minus-PIT gap ({fidelity_gap_used:+.4f} vs real "
            f"{real_gap:+.4f}, within the pre-declared tolerance of "
            f"{FIDELITY_TOL}). Unlike the two stylized shapes of the prior "
            "attempt, this null's correction can be taken seriously."
        )
    else:
        verdict = "IRRESOLVABLE_BY_STATIC_NULL"
        reasons.append(
            "FIDELITY FAILS AGAIN, AND THIS TIME IT IS INFORMATIVE. The null's "
            "cross-sectional correlation shape is no longer an assumption -- it "
            "IS the real in-sample residual correlation matrix, exactly, and the "
            "self-check confirms R(1) == R_hat to machine precision. Its "
            f"in-sample-minus-PIT gap is {fidelity_gap_used:+.4f} against the "
            f"real {real_gap:+.4f} (error {fidelity_error:.4f} > tolerance "
            f"{FIDELITY_TOL}); the best gap ANY rung of either ladder achieves "
            f"is {best_gap:+.4f}. Since the shape is now correct by "
            "construction, the residual mismatch cannot be a shape-calibration "
            "problem. It is a DYNAMICS problem: the real factor loadings move "
            "over the sample, and a null whose loadings are constant cannot "
            "reproduce that no matter how its cross-section is calibrated."
        )
    if real_exceeds_noise_envelope:
        reasons.append(
            "PART A CONFIRMS THAT DIRECTLY, WITHOUT ANY NULL INVERSION: the real "
            "top-6 eigenvector subspace rotates "
            f"{real_drift['first_vs_last_max_angle_deg']:.2f} degrees "
            "(largest principal angle) between the first and last walk-forward "
            "refit, while constant-loading synthetic panels put the same "
            "statistic at "
            f"{const_drift['first_vs_last_max_angle_deg']['mean']:.2f} degrees on "
            f"average and never above "
            f"{const_drift['first_vs_last_max_angle_deg']['max']:.2f} across "
            f"{N_DRIFT_SEEDS} draws. The real loadings genuinely drift; the "
            "excess is not sampling noise."
        )
    else:
        reasons.append(
            "PART A does NOT find real drift beyond the sampling-noise envelope: "
            f"real first-vs-last max angle "
            f"{real_drift['first_vs_last_max_angle_deg']:.2f} degrees sits within "
            "the constant-truth range (max over draws "
            f"{const_drift['first_vs_last_max_angle_deg']['max']:.2f}). The "
            "drift explanation for the fidelity failure is therefore NOT "
            "supported by direct measurement, and the cause remains unidentified."
        )

    payload: dict[str, Any] = {
        "generated_utc": started.isoformat(),
        "what_this_is": (
            "Last authorized attempt at the TSMOM residual-breadth bias "
            "sub-question, plus a direct measurement of real factor-loading "
            "drift. Measurement only."
        ),
        "tripwires": {
            "raw_universe_breadth_published": PUBLISHED_FUTURES_BREADTH,
            "raw_universe_breadth_reproduced": raw_breadth,
            "pit_residual_breadth_published": PUBLISHED_PIT_RESIDUAL_BREADTH,
            "pit_residual_breadth_reproduced": real_pit_breadth,
            "in_sample_residual_breadth_published": PUBLISHED_IN_SAMPLE_RESIDUAL_BREADTH,
            "in_sample_residual_breadth_reproduced": real_in_sample_breadth,
            "real_in_sample_minus_pit_gap": real_gap,
        },
        "self_checks": {
            "principal_angle_routine": angle_checks,
            "walk_forward_loading_mirror_vs_merged_code": mirror,
            "factor_variance_identity": identity,
            "empirical_shape_family": shape_checks,
            "empirical_shape_family_de_degenerated": shape_eps_checks,
        },
        "part_a_loading_drift": {
            "real": real_drift,
            "real_by_k": drift_by_k,
            "constant_truth_baseline": const_drift,
            "excess_consecutive_angle_deg": drift_excess_consecutive,
            "excess_first_vs_last_angle_deg": drift_excess_first_last,
            "real_exceeds_constant_truth_envelope": real_exceeds_noise_envelope,
        },
        "part_b_empirical_null": {
            "ladder_empirical_shape": rungs,
            "ladder_de_degenerated": rungs_eps,
            "inversion_of_real_pit": inversion,
            "b_true_implied": pit_implied,
            "null_predicted_in_sample_at_inverted_truth": predicted_in_sample,
            "null_predicted_in_sample_minus_real_pit": null_gap,
            "nearest_rung_in_sample_minus_pit": nearest_gap,
            "nearest_rung_b_true_realized": nearest_rung["b_true_realized"]["mean"],
            "de_degenerated_nearest_rung_gap": eps_gap,
            "de_degenerated_fidelity_passes": eps_fidelity_passes,
            "best_gap_any_rung": best_gap,
            "fidelity_tolerance_pre_declared": FIDELITY_TOL,
            "fidelity_gap_used": fidelity_gap_used,
            "fidelity_error": fidelity_error,
            "fidelity_passes": fidelity_passes,
        },
        "verdict": verdict,
        "verdict_reasons": reasons,
        "floor": EFFECTIVE_BREADTH_FLOOR,
        "judgment_calls": {
            "L1_gaussian_iid": "Gaussian i.i.d.-in-time innovations, matching K2 of the prior script for comparability. Real returns are fat-tailed and vol-clustered.",
            "L2_ladder_and_seeds": f"B_true ladder {list(B_TRUE_LADDER)}, {N_SEEDS} Monte-Carlo draws per rung, {N_DRIFT_SEEDS} draws for the constant-truth drift baseline. Ordinary choices, not from any source.",
            "L3_empirical_shape_family": "R(g) = normalize(V diag(lambda**g) V') built from the REAL in-sample residual correlation matrix. This script's own construction, not quoted from a paper. Chosen because it holds the empirical eigenvector shape EXACTLY fixed while moving breadth; R(1) == R_hat is machine-checked.",
            "L4_degeneracy_epsilon": f"R_hat is exactly rank-deficient (7 zero eigenvalues from removing 6 factors plus an intercept). The headline ladder keeps that degeneracy; a variant floors the zeros at eps={DEGENERACY_EPS} to test whether the exact rank deficiency drives the result. Both reported.",
            "L5_fidelity_tolerance": f"Null must land within {FIDELITY_TOL} of the real in-sample-minus-PIT gap of {real_gap:+.4f}. PRE-DECLARED, and identical to the threshold the prior merged script used, so this attempt is not graded on a softer curve.",
            "L6_principal_angles": "Drift measured by principal angles between top-k eigenvector SUBSPACES (Bjorck & Golub 1973, SVD formulation), not raw eigenvector comparison, because eigenvectors carry arbitrary sign and can swap order when eigenvalues are close -- both of which would manufacture fake drift. Routine self-checked against four cases with known answers.",
            "L7_inherited": "burn_in=504, refit_every=21, correlation PCA, k=6 held fixed at the merged report's values; changing them would break comparability with 16.9550.",
        },
        "explicitly_not_done": [
            "no TSMOM signal built",
            "no DSR, no preservation_score, no mechanism-fidelity review",
            "no registration, no live-registration status change",
            "futures_effective_breadth.py and rmt_denoising.py NOT modified",
            "prior merged research scripts NOT modified (imported)",
            "nothing pushed to origin",
        ],
    }

    OUT_JSON.write_text(json.dumps(payload, indent=2, default=float))
    OUT_TXT.write_text(render(payload))
    print(f"\nwrote {OUT_TXT}")
    print(f"wrote {OUT_JSON}")
    print(f"VERDICT: {verdict}")


def render(p: dict[str, Any]) -> str:
    L: list[str] = []
    w = L.append
    bar = "=" * 78
    sub = "-" * 78
    w(bar)
    w("TSMOM RESIDUAL-BREADTH: EMPIRICALLY-CALIBRATED NULL + LOADING-DRIFT MEASUREMENT")
    w(f"generated {p['generated_utc']}")
    w(bar)
    w("")
    w("MEASUREMENT ONLY. No TSMOM signal, no DSR, no preservation_score, no")
    w("mechanism-fidelity review, no registration, nothing pushed.")
    w("")
    w("THIS IS THE LAST AUTHORIZED ATTEMPT AT THIS SUB-QUESTION.")
    w("")
    w("WHAT IS BEING ATTEMPTED")
    w(sub)
    w("  The prior attempt (tsmom_breadth_bias_quantification_2026-09-08, merged")
    w("  4ecd429) returned UNRESOLVED: two stylized idiosyncratic-correlation")
    w("  shapes disagreed on the SIGN of the bias, and -- decisively -- BOTH")
    w("  failed a fidelity check. The real data's in-sample residual breadth")
    w("  exceeds its PIT residual breadth by +2.0457, and neither null could")
    w("  reproduce a gap above +0.01.")
    w("")
    w("  This attempt removes the guesswork from the null's correlation SHAPE by")
    w("  calibrating it to the real in-sample residual correlation matrix itself,")
    w("  and separately MEASURES the factor-loading drift that the prior report")
    w("  only speculated about.")
    w("")
    t = p["tripwires"]
    w("TRIPWIRES (nothing below means anything if these fail)")
    w(sub)
    w(f"  raw universe breadth       published {t['raw_universe_breadth_published']:.12f}")
    w(f"                             reproduced {t['raw_universe_breadth_reproduced']:.12f}")
    w(f"  PIT residual breadth       published {t['pit_residual_breadth_published']:.4f}")
    w(f"                             reproduced {t['pit_residual_breadth_reproduced']:.4f}")
    w(f"  in-sample residual breadth published {t['in_sample_residual_breadth_published']:.4f}")
    w(f"                             reproduced {t['in_sample_residual_breadth_reproduced']:.4f}")
    w(f"  real in-sample minus PIT gap          {t['real_in_sample_minus_pit_gap']:+.4f}")
    w("")
    sc = p["self_checks"]
    w("SELF-CHECKS")
    w(sub)
    for c in sc["principal_angle_routine"]:
        w(f"  principal angles: {c['case']}  holds={c['holds']}")
    m = sc["walk_forward_loading_mirror_vs_merged_code"]
    w("  walk-forward loadings reproduce MERGED residualize_pit exactly:")
    w(f"    max abs delta {m['max_abs_delta_vs_merged_residualize_pit']:.3e} over "
      f"{m['n_rows_compared']} rows  holds={m['holds']}")
    w(f"  factor-variance identity max delta "
      f"{sc['factor_variance_identity']['max_delta']:.3e}  "
      f"holds={sc['factor_variance_identity']['holds']}")
    f = sc["empirical_shape_family"]
    root_key = "factor_root_SS'_equals_R_max_delta"
    w("  empirical shape family: R(1) recovers R_hat to "
      f"{f['R(1)_recovers_R_hat_max_delta']:.3e}")
    w(f"    factor root SS' == R max delta {f[root_key]:.3e}")
    w(f"    rank of R_hat {f['rank_of_R_hat']} / {f['n']}  "
      f"(7 dimensions annihilated by k=6 factors + intercept)")
    w(f"    family breadth ceiling {f['breadth_ceiling_of_family']:.4f}  "
      f"monotone in g: {f['breadth_monotone_decreasing_in_g']}")
    w("")
    w("PART A -- DIRECT MEASUREMENT OF REAL FACTOR-LOADING DRIFT")
    w(bar)
    w("")
    w("  No synthetic null is needed for this section's real numbers. The")
    w("  walk-forward top-6 eigenvector subspace is recomputed at every 21-day")
    w("  refit and compared by principal angles (L6).")
    w("")
    a = p["part_a_loading_drift"]
    r = a["real"]
    w(f"  refits measured: {r['n_refits']}  (k={r['k']}, burn-in 504, refit 21)")
    w("")
    w("  REAL DATA, consecutive-refit largest principal angle (degrees):")
    ca = r["consecutive_max_principal_angle_deg"]
    w(f"    mean {ca['mean']:.4f}   median {ca['median']:.4f}   "
      f"p95 {ca['p95']:.4f}   max {ca['max']:.4f}")
    cc = r["consecutive_mean_cosine_similarity"]
    w(f"    consecutive mean cosine similarity: mean {cc['mean']:.6f}  "
      f"min {cc['min']:.6f}")
    w("")
    w("  REAL DATA, first refit vs last refit:")
    w(f"    principal angles (deg): "
      f"{', '.join(f'{v:.2f}' for v in r['first_vs_last_principal_angles_deg'])}")
    w(f"    largest {r['first_vs_last_max_angle_deg']:.4f} deg   "
      f"mean cosine {r['first_vs_last_mean_cosine']:.6f}")
    w("")
    w("  DRIFT BY SUBSPACE DIMENSION (is it the dominant factor or the weak ones?)")
    w("     k   consec-max-angle-mean   first-vs-last-max   first-vs-last-cos")
    for row in a["real_by_k"]:
        w(f"    {row['k']:2d}        {row['consecutive_max_angle_deg_mean']:8.4f}"
          f"           {row['first_vs_last_max_angle_deg']:8.4f}"
          f"            {row['first_vs_last_mean_cosine']:.6f}")
    w("")
    w("  CONSTANT-TRUTH BASELINE (the control that makes the above readable)")
    w(sub)
    cb = a["constant_truth_baseline"]
    w(f"  {cb['n_draws']} synthetic panels whose TRUE loadings never move. Any")
    w("  angle measured on these is pure walk-forward sampling noise.")
    cm = cb["consecutive_max_angle_deg_mean"]
    w(f"    consecutive max angle mean : {cm['mean']:.4f} deg "
      f"(sd {cm['sd']:.4f}, max over draws {cm['max']:.4f})")
    fl = cb["first_vs_last_max_angle_deg"]
    w(f"    first-vs-last max angle    : {fl['mean']:.4f} deg "
      f"(sd {fl['sd']:.4f}, max over draws {fl['max']:.4f})")
    w("")
    w("  EXCESS OF REAL OVER CONSTANT-TRUTH NOISE:")
    w(f"    consecutive  {a['excess_consecutive_angle_deg']:+.4f} deg")
    w(f"    first-vs-last {a['excess_first_vs_last_angle_deg']:+.4f} deg")
    w(f"    real exceeds the entire constant-truth envelope: "
      f"{a['real_exceeds_constant_truth_envelope']}")
    w("")
    w("PART B -- EMPIRICALLY-CALIBRATED NULL")
    w(bar)
    w("")
    w("  The null's idiosyncratic correlation is R(g) = normalize(V diag(lam**g) V')")
    w("  built from the REAL in-sample residual correlation matrix R_hat, so that")
    w("  R(1) IS R_hat exactly (machine-checked above) and every rung shares the")
    w("  real empirical eigenvector shape. Common-factor loadings and variances")
    w("  and per-instrument residual variance shares are the real fitted ones, as")
    w("  in the prior attempt. Only the idiosyncratic SHAPE has changed -- which")
    w("  is precisely the thing the prior attempt was guessing at.")
    w("")
    b = p["part_b_empirical_null"]
    w("  LADDER -- empirical shape (headline)")
    w("   B_true      g     realized      PIT   PIT bias       IS   IS-PIT  contam")
    for rr in b["ladder_empirical_shape"]:
        if rr.get("unreachable"):
            w(f"   {rr['b_true_population']:5.1f}   ---   UNREACHABLE "
              f"({rr['note']})")
            continue
        w(f"   {rr['b_true_population']:5.1f}  {rr['g']:6.3f}  "
          f"{rr['b_true_realized']['mean']:8.4f} {rr['pit_measured']['mean']:8.4f}  "
          f"{rr['pit_bias_vs_realized_truth']:+8.4f} "
          f"{rr['in_sample_measured']['mean']:8.4f} "
          f"{rr['in_sample_minus_pit']:+8.4f}   {rr['contaminated']}")
    w("")
    w("  LADDER -- de-degenerated variant (L4, zero eigenvalues floored)")
    w("   B_true      g     realized      PIT   PIT bias       IS   IS-PIT  contam")
    for rr in b["ladder_de_degenerated"]:
        if rr.get("unreachable"):
            w(f"   {rr['b_true_population']:5.1f}   ---   UNREACHABLE")
            continue
        w(f"   {rr['b_true_population']:5.1f}  {rr['g']:6.3f}  "
          f"{rr['b_true_realized']['mean']:8.4f} {rr['pit_measured']['mean']:8.4f}  "
          f"{rr['pit_bias_vs_realized_truth']:+8.4f} "
          f"{rr['in_sample_measured']['mean']:8.4f} "
          f"{rr['in_sample_minus_pit']:+8.4f}   {rr['contaminated']}")
    w("")
    w("  THE FIDELITY CHECK (pre-declared, L5 -- this decides everything)")
    w(sub)
    w(f"    real   in-sample {t['in_sample_residual_breadth_reproduced']:.4f} vs PIT "
      f"{t['pit_residual_breadth_reproduced']:.4f}   gap "
      f"{t['real_in_sample_minus_pit_gap']:+.4f}")
    w(f"    null   gap used for the check                    "
      f"{b['fidelity_gap_used']:+.4f}")
    w(f"    absolute error {b['fidelity_error']:.4f}  vs tolerance "
      f"{b['fidelity_tolerance_pre_declared']}")
    w(f"    best gap ANY rung of EITHER ladder achieves      "
      f"{b['best_gap_any_rung']:+.4f}")
    w(f"    de-degenerated variant nearest-rung gap          "
      f"{b['de_degenerated_nearest_rung_gap']:+.4f}"
      if b["de_degenerated_nearest_rung_gap"] is not None
      else "    de-degenerated variant nearest-rung gap          n/a")
    w(f"    FIDELITY PASSES: {b['fidelity_passes']}")
    w("")
    w("  INVERSION (reportable ONLY if fidelity passes)")
    w(sub)
    inv = b["inversion_of_real_pit"]
    if b["b_true_implied"] is not None:
        w(f"    observed PIT {t['pit_residual_breadth_reproduced']:.4f} inverts to "
          f"true breadth {b['b_true_implied']:.4f}")
    else:
        w(f"    inversion not available: {inv['note']}")
    w(f"    ladder monotone: {inv['calibration_is_monotone']}")
    w(f"    nearest rung's realized true breadth: "
      f"{b['nearest_rung_b_true_realized']:.4f}")
    w("")
    w("VERDICT")
    w(bar)
    w("")
    w(f"  FLOOR = {p['floor']}")
    w(f"  VERDICT: {p['verdict']}")
    w("")
    for reason in p["verdict_reasons"]:
        for line in _wrap(reason, 74):
            w(f"    {line}")
        w("")
    w("JUDGMENT CALLS")
    w(bar)
    for key, text in p["judgment_calls"].items():
        w(f"  {key}:")
        for line in _wrap(text, 72):
            w(f"    {line}")
    w("")
    w("EXPLICITLY NOT DONE")
    w(bar)
    for item in p["explicitly_not_done"]:
        w(f"  - {item}")
    w("")
    return "\n".join(L)


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        if len(cur) + len(word) + 1 > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


if __name__ == "__main__":
    main()
