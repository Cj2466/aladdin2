"""TSMOM factor decomposition: split the real 31-instrument CME futures
universe's return structure into a COMMON (systematic) component and an
IDIOSYNCRATIC (residual) component, and re-measure effective breadth on the
residual panel.

WHY THIS EXISTS
====================================================================
The pre-declared TSMOM universe gate is "effective breadth >= 15". The real
31-instrument CME futures universe measured 10.0081 and FAILED
(data/research_runs/futures_effective_breadth_2026-09-07.json, merged at
da504d2). Progression of every universe measured with the identical
methodology: ETF/cash 43 -> 7.10, ETF/cash 68 -> 8.11, real futures 31 ->
10.01. All fail.

The project owner's observation, which this script tests: low effective
breadth means the instruments share a common factor (a "global
risk-on/risk-off" factor is economically expected across asset classes).
If that shared factor is REGRESSED OUT, the residual panel might have much
lower pairwise correlation and therefore much higher effective breadth --
possibly clearing 15. That would make a diversified multi-bet TSMOM on the
RESIDUAL series feasible even though it is not feasible on raw returns, and
would additionally isolate the common factor itself as a separate,
low-breadth, single-bet candidate signal.

This script MEASURES. It builds NO TSMOM signal: no lookback return, no
volatility target, no position sizing, no DSR, no preservation_score, no
mechanism-fidelity review, no registration.

WHAT IS REUSED VERSUS WHAT IS NEW
====================================================================
REUSED, UNMODIFIED (this is what keeps 7.10 / 8.11 / 10.01 / the residual
number mutually comparable):
  - app/services/research_lab/futures_effective_breadth.py
    (`measure_futures_effective_breadth`) -- not edited, not copied, not
    re-implemented. Imported and called.
  - data/research_runs/measure_futures_breadth_2026_09_07.py
    (`load_return_panel`, `mask_cl_negative_price_dates`) -- imported so the
    return panel is constructed by the SAME code that produced 10.0081,
    rather than a second loader that could silently differ. Only the
    module's CONTINUOUS path constant is redirected at the CSVs on disk.
  - app/services/risk/rmt_denoising.py (`marchenko_pastur_bounds`,
    `fit_marchenko_pastur`, `count_signal_eigenvalues`) -- the in-repo,
    already source-verified Random Matrix Theory implementation, used to
    decide HOW MANY eigenvalues are statistically distinguishable from
    noise. Its own docstring carries the primary-source citations ([A]
    Laloux et al. arXiv:cond-mat/9810255, [B] Plerou et al.
    arXiv:cond-mat/0108023, [C] Lopez de Prado MLAM Ch.2). Using it means
    the eigenvalue-significance cutoff here is NOT a formula typed from
    memory.

NEW HERE: the PCA orthogonalization itself and the breadth-shortfall
algebra below.

THE BREADTH-SHORTFALL ALGEBRA -- DERIVED HERE, NOT QUOTED
====================================================================
FLAGGED EXPLICITLY: the following is exact algebra derived in this file. It
is NOT taken from any paper and is NOT cited to one. It needs no citation
because it is an identity, and it is machine-checked below
(`verify_shortfall_identity`) rather than asserted.

Effective breadth of a correlation matrix C of size n, as this project
defines it everywhere (sum(lambda)^2 / sum(lambda^2)):

    B = (sum_i lambda_i)^2 / (sum_i lambda_i^2)

For a CORRELATION matrix the diagonal is unit, so sum_i lambda_i =
trace(C) = n exactly. Therefore

    B = n^2 / sum_i lambda_i^2                                       (1)

so breadth is driven entirely by sum(lambda^2), and B = n if and only if
every lambda_i = 1 (the identity matrix, n genuinely independent bets).
Any concentration of the spectrum raises sum(lambda^2) and lowers B.

Split the spectrum into the k largest eigenvalues and the remaining n-k:

    sum_i lambda_i^2 = S_k + R_k,  S_k = sum_{i<=k} lambda_i^2         (2)

The "excess" that the top-k eigenvalues contribute BEYOND what they would
contribute if they were ordinary unit eigenvalues is

    E_k = S_k - k                                                      (3)

and the breadth that WOULD obtain if the top-k factors were removed and
their variance redistributed as unit eigenvalues is n^2 / (k + R_k). The
fraction of the total shortfall (n - B) attributable to the top k
eigenvalues is reported directly from these quantities. All of this is
descriptive accounting of the observed spectrum -- it is NOT a prediction
of what the residual breadth will be, because removing a factor changes
the residual correlations themselves. The residual breadth is MEASURED in
Job 2, not inferred from this algebra. That distinction is the whole point
of running Job 2 empirically.

THE LOOK-AHEAD TRAP IN JOB 2 -- THE MOST IMPORTANT CAVEAT IN THIS FILE
====================================================================
If the eigenvectors are estimated on the FULL sample and each instrument's
return is then residualized against them over that same full sample, the
residuals are orthogonal to the factors BY CONSTRUCTION. The measured
correlation among residuals is then mechanically deflated and the breadth
mechanically inflated. Reporting only that number would be manufacturing a
passed gate out of an in-sample identity -- precisely the failure mode this
project treats as worse than an honest negative.

So BOTH are computed and BOTH are reported:

  IN_SAMPLE   Full-sample PCA, full-sample residualization. An UPPER BOUND
              / best case. Not achievable by any real strategy. Never the
              gating number.

  PIT         Point-in-time. Eigenvectors and betas re-estimated on an
              EXPANDING window using only data strictly BEFORE each block,
              refit every REFIT_EVERY_DAYS trading days after a
              BURN_IN_DAYS burn-in, and applied forward. This is what a
              real residual-TSMOM could actually have traded, so THIS is
              the number the 15 floor is evaluated against.

If PIT clears 15 but IN_SAMPLE does not, something is wrong. If IN_SAMPLE
clears 15 and PIT does not, the resolution attempt has failed and the
honest report is that it failed.

JUDGMENT CALLS MADE HERE (all flagged, none hidden)
====================================================================
  J1. BURN_IN_DAYS = 504 (~2 years) and REFIT_EVERY_DAYS = 21 (~1 month)
      for the PIT variant. Chosen as ordinary conventions, NOT taken from
      any source. The k-sweep and the burn-in sensitivity below exist so a
      reader can see how much these choices matter.
  J2. The asset-class labels attached to the 31 roots are for ECONOMIC
      NARRATIVE ONLY -- no number in this report depends on them. 27 of 31
      were verified this session against a published futures-symbol
      reference (traderbytes.com/support/futuressymbols.php). BZ, PA, PL
      were NOT on that table and are assigned from standard NYMEX product
      naming (Brent crude, palladium, platinum); RTY was confirmed
      separately as CME E-mini Russell 2000. cmegroup.com's own symbol
      guide timed out twice this session and was NOT read.
  J3. Standardization uses each instrument's own mean/std (z-scores), which
      is what makes the PCA a correlation-matrix PCA rather than a
      covariance one. Correlation PCA is the right choice here because the
      breadth statistic itself is defined on the correlation matrix.
  J4. The number of factors k removed in the headline is the RMT signal
      count from Job 1, not a hand-picked k. A full sweep over
      k = 1..K_SWEEP_MAX is reported alongside so the choice is visible.
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

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

import app

if Path(app.__file__).resolve().parent.parent != _BACKEND:
    raise SystemExit(
        f"REFUSING TO RUN: `app` resolved to {app.__file__}, not inside {_BACKEND}"
    )

from app.services.research_lab.futures_effective_breadth import (
    EFFECTIVE_BREADTH_FLOOR,
    PUBLISHED_STEP1_BREADTH,
    PUBLISHED_STEP1B_BREADTH,
    measure_futures_effective_breadth,
)
from app.services.risk.rmt_denoising import (
    count_signal_eigenvalues,
    fit_marchenko_pastur,
    marchenko_pastur_bounds,
)

# --------------------------------------------------------------------------
# Where the real chained continuous CSVs live. They are gitignored DATA, and
# they physically sit in the futures-span-full-pull worktree that produced
# them. Resolved relative to the repo root so this is not a machine-specific
# absolute path.
# --------------------------------------------------------------------------
_REPO_ROOT = _BACKEND.parent
_CONTINUOUS_CANDIDATES = [
    _BACKEND / "data" / "futures_daily" / "cme_span" / "continuous",
    _REPO_ROOT
    / ".claude"
    / "worktrees"
    / "futures-span-full-pull"
    / "backend"
    / "data"
    / "futures_daily"
    / "cme_span"
    / "continuous",
    # When this file itself runs from inside a worktree, the repo root is two
    # levels further up (<repo>/.claude/worktrees/<name>/backend).
    _REPO_ROOT.parent.parent.parent
    / ".claude"
    / "worktrees"
    / "futures-span-full-pull"
    / "backend"
    / "data"
    / "futures_daily"
    / "cme_span"
    / "continuous",
]

#: The gating figure this script must reproduce before anything else it says
#: can be trusted. From futures_effective_breadth_2026-09-07.json.
PUBLISHED_FUTURES_BREADTH = 10.008142587700915

BURN_IN_DAYS = 504  # J1
REFIT_EVERY_DAYS = 21  # J1
K_SWEEP_MAX = 6  # J4
MIN_PIT_OBS = 252

#: J2 -- narrative only, no number depends on these labels.
ASSET_CLASS = {
    "ES": "equity_index", "NQ": "equity_index", "YM": "equity_index",
    "RTY": "equity_index",
    "ZT": "rates", "ZF": "rates", "ZN": "rates", "ZB": "rates",
    "6A": "fx", "6B": "fx", "6C": "fx", "6E": "fx", "6J": "fx", "6S": "fx",
    "CL": "energy", "BZ": "energy", "NG": "energy", "HO": "energy",
    "RB": "energy",
    "GC": "metals", "SI": "metals", "HG": "metals", "PA": "metals",
    "PL": "metals",
    "ZC": "grains", "ZS": "grains", "ZW": "grains", "ZL": "grains",
    "ZM": "grains",
    "LE": "livestock", "HE": "livestock",
}

PRODUCT_NAME = {
    "6A": "Australian Dollar", "6B": "British Pound", "6C": "Canadian Dollar",
    "6E": "Euro FX", "6J": "Japanese Yen", "6S": "Swiss Franc",
    "BZ": "Brent Crude (UNVERIFIED label, J2)", "CL": "Crude Oil (WTI)",
    "ES": "E-mini S&P 500", "GC": "Gold", "HE": "Lean Hogs",
    "HG": "High Grade Copper", "HO": "Heating Oil", "LE": "Live Cattle",
    "NG": "Natural Gas", "NQ": "E-mini Nasdaq 100",
    "PA": "Palladium (UNVERIFIED label, J2)",
    "PL": "Platinum (UNVERIFIED label, J2)", "RB": "Gasoline RBOB",
    "RTY": "E-mini Russell 2000", "SI": "Silver",
    "YM": "Mid-Sized Dow Industrials", "ZB": "30 Year T-Bond", "ZC": "Corn",
    "ZF": "5 Year T-Note", "ZL": "Soybean Oil", "ZM": "Soybean Meal",
    "ZN": "10 Year T-Note", "ZS": "Soybeans", "ZT": "2 Year T-Note",
    "ZW": "Wheat",
}

OUT_TXT = _BACKEND / "data" / "research_runs" / "tsmom_factor_decomposition_2026-09-07.txt"
OUT_JSON = _BACKEND / "data" / "research_runs" / "tsmom_factor_decomposition_2026-09-07.json"


# --------------------------------------------------------------------------
# Panel loading -- via the EXACT loader that produced 10.0081
# --------------------------------------------------------------------------
def _import_gate_script() -> Any:
    """Import measure_futures_breadth_2026_09_07.py as a module and point its
    CONTINUOUS constant at wherever the CSVs actually are."""
    path = Path(__file__).resolve().parent / "measure_futures_breadth_2026_09_07.py"
    if not path.exists():
        raise SystemExit(f"gate script not found at {path}")
    spec = importlib.util.spec_from_file_location("_gate_breadth_script", path)
    if spec is None or spec.loader is None:
        raise SystemExit("could not load the gate script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for candidate in _CONTINUOUS_CANDIDATES:
        if candidate.is_dir() and list(candidate.glob("*.csv")):
            module.CONTINUOUS = candidate
            return module
    raise SystemExit(
        "no chained continuous CSV directory found. Looked in:\n  "
        + "\n  ".join(str(c) for c in _CONTINUOUS_CANDIDATES)
    )


# --------------------------------------------------------------------------
# Job 1 -- PCA / spectrum
# --------------------------------------------------------------------------
def spectrum(corr: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Eigenvalues DESCENDING and matching eigenvectors (columns)."""
    values, vectors = np.linalg.eigh(corr.to_numpy())
    order = np.argsort(values)[::-1]
    return values[order], vectors[:, order]


def verify_shortfall_identity(
    eigenvalues: np.ndarray, breadth: float, n: int
) -> dict[str, Any]:
    """Machine-check identity (1): B == n^2 / sum(lambda^2) and
    sum(lambda) == n. Asserted, not assumed."""
    lam_sum = float(eigenvalues.sum())
    lam_sq = float((eigenvalues**2).sum())
    implied = n**2 / lam_sq
    return {
        "sum_lambda": lam_sum,
        "sum_lambda_equals_n": bool(abs(lam_sum - n) < 1e-9),
        "sum_lambda_squared": lam_sq,
        "breadth_from_identity_1": implied,
        "breadth_reported_by_module": breadth,
        "identity_1_delta": abs(implied - breadth),
        "identity_1_holds": bool(abs(implied - breadth) < 1e-9),
    }


def shortfall_accounting(eigenvalues: np.ndarray, n: int) -> list[dict[str, Any]]:
    """Descriptive decomposition of the breadth shortfall by top-k
    eigenvalues, per equations (2)-(3) in the module docstring.

    NOT a prediction of residual breadth. See docstring."""
    lam_sq_total = float((eigenvalues**2).sum())
    breadth = n**2 / lam_sq_total
    shortfall = n - breadth
    rows = []
    for k in range(1, min(K_SWEEP_MAX, n) + 1):
        top = eigenvalues[:k]
        s_k = float((top**2).sum())
        r_k = lam_sq_total - s_k
        excess = s_k - k
        breadth_if_top_k_were_unit = n**2 / (k + r_k)
        recovered = breadth_if_top_k_were_unit - breadth
        rows.append(
            {
                "k": k,
                "eigenvalues": [float(v) for v in top],
                "sum_lambda_sq_top_k": s_k,
                "excess_E_k": excess,
                "share_of_sum_lambda_sq": s_k / lam_sq_total,
                "variance_share_top_k": float(top.sum()) / n,
                "breadth_if_top_k_collapsed_to_unit": breadth_if_top_k_were_unit,
                "shortfall_accounted_fraction": (
                    recovered / shortfall if shortfall > 0 else float("nan")
                ),
            }
        )
    return rows


def loadings_table(
    vectors: np.ndarray, columns: list[str], eigenvalues: np.ndarray, k: int
) -> list[dict[str, Any]]:
    """Per-instrument loadings on PC1..PCk.

    Sign convention: each eigenvector is flipped so that its largest-absolute
    loading is POSITIVE. Eigenvector sign is arbitrary in any eigensolver, so
    fixing it is required for the economic read to be reproducible -- this is
    a presentation convention, not a computation.
    """
    rows = []
    fixed = vectors[:, :k].copy()
    for j in range(k):
        col = fixed[:, j]
        if col[np.argmax(np.abs(col))] < 0:
            fixed[:, j] = -col
    for i, name in enumerate(columns):
        row: dict[str, Any] = {
            "instrument": name,
            "product": PRODUCT_NAME.get(name, "?"),
            "asset_class": ASSET_CLASS.get(name, "unmapped"),
        }
        for j in range(k):
            row[f"pc{j + 1}_loading"] = float(fixed[i, j])
            # Correlation of the instrument with the (unit-variance) PC:
            # loading * sqrt(eigenvalue), the standard correlation-PCA
            # "component correlation".
            row[f"pc{j + 1}_corr"] = float(fixed[i, j] * np.sqrt(eigenvalues[j]))
        rows.append(row)
    return rows, fixed


# --------------------------------------------------------------------------
# Job 2 -- residualization
# --------------------------------------------------------------------------
def _standardize(frame: pd.DataFrame) -> pd.DataFrame:
    return (frame - frame.mean()) / frame.std(ddof=1)


def residualize_in_sample(common: pd.DataFrame, k: int) -> pd.DataFrame:
    """Full-sample PCA + full-sample OLS residual. UPPER BOUND ONLY."""
    z = _standardize(common)
    corr = common.corr()
    _values, vectors = spectrum(corr)
    loadings = vectors[:, :k]
    factors = z.to_numpy() @ loadings  # T x k factor scores

    design = np.column_stack([np.ones(len(z)), factors])
    target = z.to_numpy()
    coef, *_ = np.linalg.lstsq(design, target, rcond=None)
    residual = target - design @ coef

    # Cross-check: for correlation-PCA with orthonormal loadings the OLS
    # residual must equal the direct projection Z - F V'. Different route,
    # same answer, or something is wrong.
    projection = z.to_numpy() - factors @ loadings.T
    delta = float(np.abs(residual - projection).max())
    if delta > 1e-8:
        raise AssertionError(
            f"in-sample residual routes disagree by {delta:.3e} (OLS vs projection)"
        )
    return pd.DataFrame(residual, index=common.index, columns=common.columns)


def residualize_pit(
    common: pd.DataFrame,
    k: int,
    burn_in: int = BURN_IN_DAYS,
    refit_every: int = REFIT_EVERY_DAYS,
) -> pd.DataFrame:
    """Point-in-time residualization.

    At each refit boundary t0 (>= burn_in), estimate the standardization
    moments, the top-k eigenvectors, and each instrument's alpha/beta using
    ONLY rows strictly before t0. Apply them to rows [t0, t0+refit_every).
    Nothing from row t or later ever touches row t's residual.
    """
    values = common.to_numpy()
    n_obs, n_inst = values.shape
    out = np.full((n_obs, n_inst), np.nan)

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
        loadings = eigvecs[:, order][:, :k]

        factors_prior = z_prior @ loadings
        design_prior = np.column_stack([np.ones(len(z_prior)), factors_prior])
        coef, *_ = np.linalg.lstsq(design_prior, z_prior, rcond=None)

        block = (values[start:stop] - mean) / std
        factors_block = block @ loadings
        design_block = np.column_stack([np.ones(len(block)), factors_block])
        out[start:stop] = block - design_block @ coef

        start = stop

    frame = pd.DataFrame(out, index=common.index, columns=common.columns)
    return frame.dropna(how="all")


# --------------------------------------------------------------------------
# Measurement helper
# --------------------------------------------------------------------------
def measure(panel: pd.DataFrame) -> dict[str, Any]:
    """Run the UNMODIFIED shared module and summarize."""
    result = measure_futures_effective_breadth(panel)
    cw = result.common_window
    return {
        "breadth_eigenvalue": float(cw.breadth_eigenvalue),
        "breadth_frobenius": float(cw.breadth_frobenius),
        "cross_check_delta": float(cw.cross_check_delta),
        "n_instruments": int(cw.n_instruments),
        "n_observations": int(cw.n_observations),
        "min_eigenvalue": float(cw.min_eigenvalue),
        "is_positive_semidefinite": bool(cw.is_positive_semidefinite),
        "is_safely_interpretable": bool(cw.is_safely_interpretable),
        "pairwise_breadth": float(result.pairwise.breadth_eigenvalue),
        "conservative_breadth": float(result.conservative.breadth_eigenvalue),
        "passes_floor": bool(result.passes_floor),
        "verdict": result.verdict(),
        "notes": list(result.notes),
    }


def mean_abs_offdiag(frame: pd.DataFrame) -> float:
    corr = frame.dropna(how="any").corr().to_numpy()
    n = corr.shape[0]
    mask = ~np.eye(n, dtype=bool)
    return float(np.abs(corr[mask]).mean())


def mean_offdiag(frame: pd.DataFrame) -> float:
    corr = frame.dropna(how="any").corr().to_numpy()
    n = corr.shape[0]
    mask = ~np.eye(n, dtype=bool)
    return float(corr[mask].mean())


# --------------------------------------------------------------------------
def main() -> None:
    gate = _import_gate_script()
    print(f"continuous CSVs: {gate.CONTINUOUS}")

    panel = gate.load_return_panel()
    common = panel.dropna(how="any")
    n = common.shape[1]
    columns = list(common.columns)
    print(f"panel {panel.shape[0]}x{panel.shape[1]}; common window {common.shape[0]} rows")
    print(f"common window {common.index.min().date()} .. {common.index.max().date()}")

    # ---- REGRESSION CHECK: reproduce the published gating number ----------
    raw = measure(panel)
    reproduced = raw["breadth_eigenvalue"]
    repro_delta = abs(reproduced - PUBLISHED_FUTURES_BREADTH)
    print(f"reproduced published breadth {reproduced:.15f} (delta {repro_delta:.3e})")
    if repro_delta > 1e-9:
        raise SystemExit(
            "REFUSING TO CONTINUE: could not reproduce the published 10.0081 "
            f"gate number (got {reproduced}). The data or the module has moved; "
            "every comparison below would be meaningless."
        )

    # ================== JOB 1: PCA ========================================
    corr = common.corr()
    eigenvalues, eigenvectors = spectrum(corr)
    identity = verify_shortfall_identity(eigenvalues, reproduced, n)
    if not (identity["identity_1_holds"] and identity["sum_lambda_equals_n"]):
        raise SystemExit(f"breadth identity failed self-check: {identity}")

    # RMT significance -- how many eigenvalues are distinguishable from noise.
    t_obs = common.shape[0]
    q = t_obs / n
    _lo_unit, hi_unit = marchenko_pastur_bounds(q, 1.0)
    fit = fit_marchenko_pastur(eigenvalues, q)
    k_rmt_unit = count_signal_eigenvalues(eigenvalues, hi_unit)
    k_rmt_fitted = count_signal_eigenvalues(eigenvalues, fit.lambda_plus)

    # Kaiser-Guttman (eigenvalue >= 1) -- a SECOND, independently-sourced
    # stopping criterion, used here only as a cross-check on the RMT count.
    # Source read this session: Polakow & Gebbie, "How many independent bets
    # are there in an emerging market?", arXiv:physics/0601166v3, Sec 1.2:
    # "we utilize the Keiser-Gutman [4] stopping criterion to select those
    # eigenvectors with eigenvalues greater than or equal to one, the number
    # of such eigenvalues corresponds to an estimation of the effective
    # dimensions of the subspace". Their ref [4] is Jackson, D. A. (1993),
    # Ecology 74, 2204-2214 -- NOT read here, so cited only as their citation.
    k_kaiser_guttman = int((eigenvalues >= 1.0).sum())

    # Headline k: the FITTED-sigma2 count, which is the convention the
    # in-repo rmt_denoising module implements and documents (sigma^2 is
    # fitted to the bulk, not assumed to be 1).
    k_headline = max(1, int(k_rmt_fitted))

    shortfall = shortfall_accounting(eigenvalues, n)
    loadings, _fixed_vectors = loadings_table(
        eigenvectors, columns, eigenvalues, min(K_SWEEP_MAX, n)
    )

    # Asset-class average loadings, for the economic read (J2: labels only).
    class_loadings: dict[str, dict[str, float]] = {}
    for cls in sorted(set(ASSET_CLASS.get(c, "unmapped") for c in columns)):
        members = [r for r in loadings if r["asset_class"] == cls]
        class_loadings[cls] = {
            "n_members": len(members),
            **{
                f"mean_pc{j + 1}_corr": float(
                    np.mean([m[f"pc{j + 1}_corr"] for m in members])
                )
                for j in range(min(4, K_SWEEP_MAX))
            },
        }

    # ---- Structural facts underpinning the economic read -----------------
    # These are CHECKS, not prose: if the data ever changes so that one of
    # them stops holding, the narrative below is automatically contradicted
    # in the report instead of silently going stale.
    by_name = {r["instrument"]: r for r in loadings}

    def pc(name: str, j: int) -> float:
        return float(by_name[name][f"pc{j}_corr"])

    fx_roots = [c for c in columns if ASSET_CLASS.get(c) == "fx"]
    eq_roots = [c for c in columns if ASSET_CLASS.get(c) == "equity_index"]
    rate_roots = [c for c in columns if ASSET_CLASS.get(c) == "rates"]

    structure = {
        "pc1_all_fx_load_positive": bool(all(pc(c, 1) > 0 for c in fx_roots)),
        "pc1_all_equity_load_positive": bool(all(pc(c, 1) > 0 for c in eq_roots)),
        "pc1_gold_and_equity_same_sign": bool(
            pc("GC", 1) > 0 and all(pc(c, 1) > 0 for c in eq_roots)
        ),
        "pc1_gold_corr": pc("GC", 1),
        "pc1_mean_abs_rates_corr": float(
            np.mean([abs(pc(c, 1)) for c in rate_roots])
        ),
        "pc2_all_rates_load_positive": bool(all(pc(c, 2) > 0 for c in rate_roots)),
        "pc2_all_equity_load_negative": bool(all(pc(c, 2) < 0 for c in eq_roots)),
        "pc2_jpy_corr": pc("6J", 2),
        "pc2_chf_corr": pc("6S", 2),
        "pc3_all_grains_load_positive": bool(
            all(pc(c, 3) > 0 for c in columns if ASSET_CLASS.get(c) == "grains")
        ),
    }
    structure["interpretation"] = {
        "pc1": (
            "NOT a risk-on/risk-off factor. Every one of the 6 CME FX "
            "contracts (quoted USD-per-foreign-unit, so a positive return is "
            "USD weakness) loads POSITIVELY, and gold loads positively "
            "ALONGSIDE equities rather than against them -- the opposite of "
            "what a flight-to-safety factor produces. Rates load near zero. "
            "Best read as a US-DOLLAR / GLOBAL-REFLATION factor. "
            "INTERPRETATION, flagged as a judgment call; the sign facts above "
            "are the verifiable part."
        ),
        "pc2": (
            "THIS is the risk-off / flight-to-quality factor: all four "
            "Treasury contracts load strongly positive, JPY and CHF (the "
            "classic funding/haven currencies) load positive, and all four "
            "equity indices plus energy load negative. INTERPRETATION."
        ),
        "pc3": (
            "An agricultural-complex factor: all five grain/oilseed contracts "
            "load positive together, against equities. INTERPRETATION."
        ),
        "overall": (
            "The universe is NOT dominated by one global risk factor. It has "
            "several distinct ones, and PC1 explains only "
            f"{eigenvalues[0] / n:.1%} of variance. The pattern -- a broad "
            "leading component followed by recognisable sector/asset-class "
            "components -- is the shape Plerou et al. "
            "(arXiv:cond-mat/0108023) describe for equity panels (largest "
            "eigenvalue market-wide, next few sector-like), here with asset "
            "classes playing the role of sectors. Citing the shape as "
            "documented; the mapping onto asset classes is this report's own "
            "reading."
        ),
    }

    # ================== JOB 2: residual breadth ===========================
    raw_mean_abs_corr = mean_abs_offdiag(common)
    raw_mean_corr = mean_offdiag(common)

    sweep: list[dict[str, Any]] = []
    for k in range(1, min(K_SWEEP_MAX, n - 1) + 1):
        in_sample = residualize_in_sample(common, k)
        pit = residualize_pit(common, k)
        # Apples-to-apples: also measure in-sample on the PIT window only.
        in_sample_pit_window = in_sample.loc[pit.index]
        sweep.append(
            {
                "k_factors_removed": k,
                "in_sample": measure(in_sample),
                "in_sample_on_pit_window": measure(in_sample_pit_window),
                "pit": measure(pit),
                "in_sample_mean_abs_offdiag_corr": mean_abs_offdiag(in_sample),
                "pit_mean_abs_offdiag_corr": mean_abs_offdiag(pit),
                "pit_mean_offdiag_corr": mean_offdiag(pit),
                "pit_n_observations": len(pit),
                "pit_first_date": str(pit.index.min().date()),
            }
        )

    headline = next(s for s in sweep if s["k_factors_removed"] == k_headline)

    # Burn-in sensitivity on the headline k (J1 is a judgment call; show it).
    burn_in_sensitivity = []
    for burn in (252, 504, 756, 1008):
        if burn >= len(common) - MIN_PIT_OBS:
            continue
        p = residualize_pit(common, k_headline, burn_in=burn)
        burn_in_sensitivity.append(
            {
                "burn_in_days": burn,
                "pit_breadth": measure(p)["breadth_eigenvalue"],
                "n_observations": len(p),
            }
        )
    refit_sensitivity = []
    for every in (5, 21, 63, 126):
        p = residualize_pit(common, k_headline, refit_every=every)
        refit_sensitivity.append(
            {
                "refit_every_days": every,
                "pit_breadth": measure(p)["breadth_eigenvalue"],
            }
        )

    # CL negative-price sensitivity, same judgment call the gate run made.
    cl_masked_panel = gate.mask_cl_negative_price_dates(panel)
    cl_common = cl_masked_panel.dropna(how="any")
    cl_pit = residualize_pit(cl_common, k_headline)
    cl_sensitivity = {
        "raw_breadth": measure(cl_masked_panel)["breadth_eigenvalue"],
        "pit_residual_breadth": measure(cl_pit)["breadth_eigenvalue"],
    }

    # ---- Feasibility arithmetic for Job 3 --------------------------------
    # PIT residuals are expressed in units of the PRIOR-window z-score, so
    # each column's variance is directly its residual variance share (the
    # raw standardized series has unit variance by construction). 1 - that
    # is the share of each instrument's risk explained by the k factors.
    pit_headline_panel = residualize_pit(common, k_headline)
    residual_var_share = pit_headline_panel.var(ddof=1)
    feasibility = {
        "k_factors_removed": k_headline,
        "mean_residual_variance_share": float(residual_var_share.mean()),
        "mean_variance_explained_by_factors": float(1 - residual_var_share.mean()),
        "per_instrument_residual_variance_share": {
            k: float(v) for k, v in residual_var_share.items()
        },
        "gross_leverage_multiple_to_restore_raw_risk": float(
            1.0 / np.sqrt(residual_var_share.mean())
        ),
        "note": (
            "A residual series carries less risk than the raw series, so "
            "matching a given volatility target on residuals requires this "
            "much more gross exposure -- while spreads and commissions are "
            "charged on gross notional and are unchanged. Cost per unit of "
            "residual risk is therefore roughly this multiple higher, BEFORE "
            "counting the extra turnover of the factor-hedge legs. This is "
            "arithmetic, not a cost model; a real cost model is required "
            "before any DSR, per CLAUDE.md."
        ),
    }

    pit_breadth = headline["pit"]["breadth_eigenvalue"]
    in_sample_breadth = headline["in_sample"]["breadth_eigenvalue"]
    gate_passes = bool(pit_breadth >= EFFECTIVE_BREADTH_FLOOR)

    k_pass = [
        s["k_factors_removed"]
        for s in sweep
        if s["pit"]["breadth_eigenvalue"] >= EFFECTIVE_BREADTH_FLOOR
    ]
    k_fail = [
        s["k_factors_removed"]
        for s in sweep
        if s["pit"]["breadth_eigenvalue"] < EFFECTIVE_BREADTH_FLOOR
    ]

    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "what_this_is": (
            "PCA factor decomposition of the real 31-instrument CME futures "
            "universe, and effective-breadth re-measurement of the residual "
            "(idiosyncratic) panel. Measurement only -- no TSMOM signal, no "
            "DSR, no preservation_score, no registration."
        ),
        "universe": columns,
        "n_instruments": n,
        "panel_first_date": str(panel.index.min().date()),
        "panel_last_date": str(panel.index.max().date()),
        "common_window_first_date": str(common.index.min().date()),
        "common_window_last_date": str(common.index.max().date()),
        "common_window_n_observations": int(common.shape[0]),
        "floor": float(EFFECTIVE_BREADTH_FLOOR),
        "baselines": {
            "step1_etf_cash_43": PUBLISHED_STEP1_BREADTH,
            "step1b_etf_cash_68": PUBLISHED_STEP1B_BREADTH,
            "step2_real_futures_31_published": PUBLISHED_FUTURES_BREADTH,
            "step2_reproduced_here": reproduced,
            "reproduction_delta": repro_delta,
        },
        "job1_pca": {
            "eigenvalues_desc": [float(v) for v in eigenvalues],
            "variance_share_desc": [float(v / n) for v in eigenvalues],
            "cumulative_variance_share": [
                float(x) for x in np.cumsum(eigenvalues) / n
            ],
            "breadth_identity_self_check": identity,
            "rmt": {
                "q_T_over_N": q,
                "T_observations": int(t_obs),
                "N_instruments": n,
                "lambda_plus_sigma2_equals_1": float(hi_unit),
                "fitted_sigma2": float(fit.sigma2),
                "fitted_lambda_plus": float(fit.lambda_plus),
                "n_signal_eigenvalues_sigma2_1": int(k_rmt_unit),
                "n_signal_eigenvalues_fitted_sigma2": int(k_rmt_fitted),
                "k_used_as_headline": k_headline,
                "kaiser_guttman_count_eigenvalue_ge_1": k_kaiser_guttman,
                "kaiser_guttman_source": (
                    "Polakow & Gebbie, arXiv:physics/0601166v3 Sec 1.2 (read "
                    "this session); their ref [4] Jackson (1993) Ecology 74, "
                    "2204-2214 NOT read here"
                ),
                "source_note": (
                    "computed via app/services/risk/rmt_denoising.py, whose "
                    "docstring carries the primary sources (Laloux et al. "
                    "arXiv:cond-mat/9810255 eq.(3); Plerou et al. "
                    "arXiv:cond-mat/0108023 eq.(6)-(7); Lopez de Prado MLAM "
                    "ch.2 snippets). No formula was typed from memory here."
                ),
            },
            "shortfall_accounting": shortfall,
            "loadings": loadings,
            "asset_class_mean_component_correlations": class_loadings,
            "economic_structure": structure,
        },
        "job2_residual_breadth": {
            "raw_mean_abs_offdiag_correlation": raw_mean_abs_corr,
            "raw_mean_offdiag_correlation": raw_mean_corr,
            "k_sweep": sweep,
            "headline_k": k_headline,
            "headline_in_sample_breadth_UPPER_BOUND": in_sample_breadth,
            "headline_pit_breadth_GATING": pit_breadth,
            "floor": float(EFFECTIVE_BREADTH_FLOOR),
            "gate_passes_on_pit": gate_passes,
            "burn_in_sensitivity": burn_in_sensitivity,
            "refit_frequency_sensitivity": refit_sensitivity,
            "cl_negative_price_sensitivity": cl_sensitivity,
            "feasibility_arithmetic": feasibility,
            "k_values_that_pass_floor_on_pit": k_pass,
            "k_values_that_fail_floor_on_pit": k_fail,
            "pass_is_robust_to_k": bool(len(k_fail) == 0),
            "k_robustness_note": (
                "The gate passes on PIT only for k in "
                f"{k_pass} and fails for k in {k_fail}. The headline k="
                f"{k_headline} is the RMT-determined signal count, not "
                "hand-picked, but this dependence on k is a live weakness and "
                "is disclosed rather than smoothed over."
            ),
        },
        "judgment_calls": {
            "J1_burn_in_and_refit": (
                f"burn_in={BURN_IN_DAYS}d, refit_every={REFIT_EVERY_DAYS}d for "
                "the PIT variant -- ordinary conventions chosen here, not from "
                "any source; sensitivities reported."
            ),
            "J2_asset_class_labels": (
                "narrative only, no number depends on them; 27/31 verified "
                "against a published symbol reference this session; BZ/PA/PL "
                "assigned from standard NYMEX product naming and NOT verified "
                "against a CME-hosted document (cmegroup.com timed out)."
            ),
            "J3_correlation_pca": (
                "z-scored returns => correlation-matrix PCA, matching the "
                "correlation-matrix definition of the breadth statistic itself."
            ),
            "J4_k_choice": (
                "headline k is the RMT fitted-sigma2 signal count, not "
                "hand-picked; full k=1..%d sweep reported." % min(K_SWEEP_MAX, n - 1)
            ),
            "J5_in_sample_is_not_a_result": (
                "the in-sample residual breadth is an upper bound produced by "
                "an orthogonality identity, not an achievable number; the gate "
                "is evaluated on the PIT figure only."
            ),
        },
        "job3_two_signal_proposal": {
            "triggered": gate_passes,
            "status": "DESIGN PROPOSAL ONLY -- nothing built, run, scored or registered",
            "signal_a_factor_momentum": {
                "what": (
                    f"trend-following applied to the {k_headline} extracted "
                    "factor return series (each eigenvector is itself a "
                    "tradable long/short weight vector over the 31 instruments)"
                ),
                "n_bets": k_headline,
                "pc1_variance_share": float(eigenvalues[0] / n),
                "statistical_distinction": (
                    "few bets -> the law-of-large-numbers multi-bet argument "
                    "does not apply; credibility must come from effect size and "
                    "history length, and its DSR needs a MORE conservative "
                    "(smaller) effective-N than a multi-bet family. A small "
                    "n_local is not a licence for a lenient denominator."
                ),
                "recommended_default_verdict": (
                    "treat any pass as UNRESOLVED unless it clears the most "
                    "conservative rung of the existing {n_local,37,362,1031} ladder"
                ),
                "honest_prior": (
                    "momentum on the dominant PC of a futures panel is close to "
                    "the CTA industry's core product; prior that it is "
                    "un-arbitraged is LOW"
                ),
            },
            "signal_b_idiosyncratic_tsmom": {
                "what": "standard multi-bet TSMOM on the 31 residual series",
                "pit_effective_breadth": pit_breadth,
                "floor": float(EFFECTIVE_BREADTH_FLOOR),
                "clears_floor": gate_passes,
                "statistical_distinction": (
                    "breadth now (conditionally) clears the floor, so the "
                    "project's standard multi-bet DSR treatment applies"
                ),
                "conditions_before_treating_as_unblocked": [
                    "cost realism must feed the DSR: residual retains "
                    f"{feasibility['mean_residual_variance_share']:.3f} of variance, "
                    f"needing ~{feasibility['gross_leverage_multiple_to_restore_raw_risk']:.2f}x "
                    "gross exposure at unchanged per-notional cost, plus the "
                    "extra turnover of re-hedging the factor legs",
                    f"the floor is cleared only for k in {k_pass}, not for {k_fail}",
                    "high residual breadth is a precondition for a meaningful "
                    "test, NOT evidence that trend-following works on residuals",
                ],
            },
            "citations": {
                "polakow_gebbie_2008": (
                    "arXiv:physics/0601166v3, 'How many independent bets are "
                    "there in an emerging market?' -- READ DIRECTLY this "
                    "session; Lemma 1.1 (independence != separateness) and "
                    "Sec 1.2 (breadth from the correlation eigenspectrum)"
                ),
                "grinold_1989": (
                    "Journal of Portfolio Management 15, 30-37 -- NOT READ; "
                    "quoted as it appears in Polakow & Gebbie's bibliography "
                    "(their ref [3]). Second-hand citation, flagged as such."
                ),
                "fundamental_law_form_verification": (
                    "IR = IC*sqrt(BR) was NOT taken from memory: it was checked "
                    "against Polakow & Gebbie Sec 1.1's own worked example "
                    "(IC=0.2 -> printed IR 0.2 / 0.45 / 0.90 for 1 / 5 / 20 "
                    "bets; computed 0.2000 / 0.4472 / 0.8944)"
                ),
                "breadth_units_caveat": (
                    "Grinold's BR is independent decisions PER YEAR; the "
                    "statistic measured here is cross-sectional (instruments). "
                    "No numeric IR forecast is made because of this ambiguity; "
                    "it must be resolved before any DSR N assumption."
                ),
            },
        },
        "explicitly_not_done": [
            "no TSMOM signal built (no lookback, no vol target, no sizing)",
            "no DSR, no preservation_score, no mechanism-fidelity review",
            "no registration, no live-registration status change",
            "futures_effective_breadth.py NOT modified (imported unchanged)",
            "nothing pushed to origin; no Databento work",
        ],
    }
    OUT_JSON.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    # ---------------- human-readable report -------------------------------
    L: list[str] = []
    a = L.append
    a("=" * 78)
    a("TSMOM FACTOR DECOMPOSITION -- common vs idiosyncratic breadth")
    a(f"generated {report['generated_at_utc']}")
    a("=" * 78)
    a("")
    a("MEASUREMENT ONLY. No TSMOM signal, no DSR, no preservation_score, no")
    a("mechanism-fidelity review, no registration, nothing pushed.")
    a("")
    a(f"Universe: {n} real chained CME futures, "
      f"{report['panel_first_date']}..{report['panel_last_date']}")
    a(f"Common window (the gating window): {report['common_window_first_date']}"
      f"..{report['common_window_last_date']}, {t_obs} observations")
    a("")
    a("REGRESSION CHECK against the merged gate result")
    a("-" * 78)
    a(f"  published (da504d2)      {PUBLISHED_FUTURES_BREADTH:.15f}")
    a(f"  reproduced here          {reproduced:.15f}")
    a(f"  delta                    {repro_delta:.3e}  -> reproduced exactly")
    a("")
    a("JOB 1 -- PCA OF THE 31x31 CORRELATION MATRIX")
    a("=" * 78)
    a("")
    a("Spectrum (eigenvalue, share of total variance, cumulative):")
    for i, v in enumerate(eigenvalues):
        cum = float(np.cumsum(eigenvalues)[i] / n)
        marker = ""
        if v > fit.lambda_plus:
            marker = "  <-- above fitted RMT noise bound (signal)"
        a(f"  PC{i + 1:<3} {v:9.4f}   {v / n:7.2%}   {cum:7.2%}{marker}")
    a("")
    a("How many factors are real, not noise (Random Matrix Theory)")
    a("-" * 78)
    a(f"  q = T/N = {t_obs}/{n} = {q:.4f}")
    a(f"  lambda_plus with sigma^2 = 1 (assumed):  {hi_unit:.6f}")
    a(f"    -> {k_rmt_unit} eigenvalues above it")
    a(f"  sigma^2 FITTED to the bulk:              {fit.sigma2:.6f}")
    a(f"  lambda_plus with fitted sigma^2:         {fit.lambda_plus:.6f}")
    a(f"    -> {k_rmt_fitted} eigenvalues above it   [HEADLINE k = {k_headline}]")
    a("")
    a(f"  Cross-check, Kaiser-Guttman (eigenvalue >= 1): {k_kaiser_guttman}")
    a("    (criterion as used by Polakow & Gebbie arXiv:physics/0601166v3")
    a("     Sec 1.2, read this session. Reported as a second opinion only --")
    a("     the headline k stays the RMT count.)")
    a("")
    a("  Computed with app/services/risk/rmt_denoising.py -- the in-repo,")
    a("  source-verified implementation (Laloux et al. arXiv:cond-mat/9810255")
    a("  eq.(3); Plerou et al. arXiv:cond-mat/0108023 eq.(6)-(7); Lopez de")
    a("  Prado MLAM ch.2). No RMT formula was typed from memory in this file.")
    a("")
    a("Breadth-shortfall accounting  [DERIVED HERE, NOT QUOTED -- see docstring]")
    a("-" * 78)
    a(f"  identity check: sum(lambda) = {identity['sum_lambda']:.10f} = n = {n}  OK")
    a(f"  identity check: n^2/sum(lambda^2) = "
      f"{identity['breadth_from_identity_1']:.12f}")
    a(f"                  module breadth    = "
      f"{identity['breadth_reported_by_module']:.12f}   OK")
    a("")
    a("  k   sum(l^2) top-k   excess E_k   var share   breadth if top-k were")
    a("                                                unit eigenvalues")
    for row in shortfall:
        a(f"  {row['k']:<3} {row['sum_lambda_sq_top_k']:>13.4f}   "
          f"{row['excess_E_k']:>10.4f}   {row['variance_share_top_k']:>8.2%}   "
          f"{row['breadth_if_top_k_collapsed_to_unit']:>10.4f}")
    a("")
    a("  This is descriptive accounting of the OBSERVED spectrum. It does NOT")
    a("  predict the residual breadth: removing a factor changes the residual")
    a("  correlations themselves. Job 2 measures that empirically.")
    a("")
    a("What the dominant factors look like economically")
    a("-" * 78)
    a("  (correlation of each instrument with each principal component;")
    a("   eigenvector signs fixed so the largest-magnitude loading is positive)")
    a("")
    a(f"  {'inst':<5} {'asset class':<13} {'product':<34} "
      + " ".join(f"{'PC' + str(j + 1):>7}" for j in range(4)))
    for cls in sorted(set(r["asset_class"] for r in loadings)):
        for r in [x for x in loadings if x["asset_class"] == cls]:
            a(f"  {r['instrument']:<5} {r['asset_class']:<13} {r['product']:<34} "
              + " ".join(f"{r[f'pc{j + 1}_corr']:>7.3f}" for j in range(4)))
    a("")
    a("  Asset-class means:")
    a(f"  {'class':<13} {'n':>3} " + " ".join(f"{'PC' + str(j + 1):>8}" for j in range(4)))
    for cls, vals in class_loadings.items():
        a(f"  {cls:<13} {vals['n_members']:>3} "
          + " ".join(f"{vals[f'mean_pc{j + 1}_corr']:>8.3f}" for j in range(4)))
    a("")
    a("  WHAT THE FACTORS ARE, ECONOMICALLY")
    a("  " + "-" * 74)
    a("  Verifiable sign facts (asserted from the data, not prose):")
    a(f"    all 6 FX load positive on PC1 ............ {structure['pc1_all_fx_load_positive']}")
    a(f"    all 4 equity indices positive on PC1 ..... {structure['pc1_all_equity_load_positive']}")
    a(f"    gold same sign as equities on PC1 ........ "
      f"{structure['pc1_gold_and_equity_same_sign']} (gold {structure['pc1_gold_corr']:.3f})")
    a(f"    mean |rates| loading on PC1 .............. {structure['pc1_mean_abs_rates_corr']:.3f}")
    a(f"    all 4 Treasuries positive on PC2 ......... {structure['pc2_all_rates_load_positive']}")
    a(f"    all 4 equity indices negative on PC2 ..... {structure['pc2_all_equity_load_negative']}")
    a(f"    JPY / CHF on PC2 ......................... "
      f"{structure['pc2_jpy_corr']:.3f} / {structure['pc2_chf_corr']:.3f}")
    a(f"    all 5 grains positive on PC3 ............. {structure['pc3_all_grains_load_positive']}")
    a("")
    for key in ("pc1", "pc2", "pc3", "overall"):
        a(f"  {key.upper()}:")
        text = structure["interpretation"][key]
        line = "    "
        for word in text.split():
            if len(line) + len(word) + 1 > 76:
                a(line)
                line = "    "
            line += word + " "
        a(line.rstrip())
        a("")
    a("JOB 2 -- RESIDUAL PANEL BREADTH")
    a("=" * 78)
    a("")
    a(f"  raw panel mean |off-diagonal correlation|: {raw_mean_abs_corr:.4f}")
    a(f"  raw panel mean  off-diagonal correlation : {raw_mean_corr:.4f}")
    a("")
    a("  IN_SAMPLE = full-sample PCA + full-sample residualization. This is an")
    a("  UPPER BOUND ONLY: the residuals are orthogonal to the factors BY")
    a("  CONSTRUCTION, so its breadth is mechanically inflated and no real")
    a("  strategy could have traded it. It is NOT the gating number.")
    a("")
    a("  PIT = eigenvectors and betas re-estimated on an expanding window from")
    a("  strictly-prior data only, refit every " f"{REFIT_EVERY_DAYS} days after a "
      f"{BURN_IN_DAYS}-day burn-in. THIS is the gating number.")
    a("")
    a(f"  {'k':<3} {'IN_SAMPLE':>10} {'IS(pit win)':>12} {'PIT':>10} "
      f"{'PIT |corr|':>11} {'PIT n':>7}")
    for s in sweep:
        mark = "  <-- headline k" if s["k_factors_removed"] == k_headline else ""
        a(f"  {s['k_factors_removed']:<3} "
          f"{s['in_sample']['breadth_eigenvalue']:>10.4f} "
          f"{s['in_sample_on_pit_window']['breadth_eigenvalue']:>12.4f} "
          f"{s['pit']['breadth_eigenvalue']:>10.4f} "
          f"{s['pit_mean_abs_offdiag_corr']:>11.4f} "
          f"{s['pit_n_observations']:>7}{mark}")
    a("")
    a(f"  FLOOR = {EFFECTIVE_BREADTH_FLOOR}")
    a(f"  raw (no factor removed)         {reproduced:.4f}   FAILS")
    a(f"  in-sample, k={k_headline} (upper bound)   {in_sample_breadth:.4f}   "
      f"{'>= floor' if in_sample_breadth >= EFFECTIVE_BREADTH_FLOOR else '< floor'}"
      "  [NOT a result]")
    a(f"  PIT, k={k_headline} (GATING)              {pit_breadth:.4f}   "
      f"{'PASSES' if gate_passes else 'FAILS'}")
    a("")
    a("  Burn-in sensitivity (PIT, headline k):")
    for row in burn_in_sensitivity:
        a(f"    burn_in={row['burn_in_days']:>5}d  breadth "
          f"{row['pit_breadth']:.4f}  (n={row['n_observations']})")
    a("  Refit-frequency sensitivity (PIT, headline k):")
    for row in refit_sensitivity:
        a(f"    refit every {row['refit_every_days']:>4}d  breadth "
          f"{row['pit_breadth']:.4f}")
    a("  CL negative-price sensitivity (same judgment call the gate run made):")
    a(f"    raw breadth CL-masked            {cl_sensitivity['raw_breadth']:.4f}")
    a(f"    PIT residual breadth CL-masked   "
      f"{cl_sensitivity['pit_residual_breadth']:.4f}")
    a("")
    a(f"  k values PASSING the floor on PIT: {k_pass}")
    a(f"  k values FAILING the floor on PIT: {k_fail}")
    a("  -> the pass is NOT robust to the choice of k. Disclosed, not smoothed.")
    a("")

    if gate_passes:
        a("")
        a("JOB 3 -- TWO-SIGNAL FRAMEWORK PROPOSAL (DESIGN ONLY, NOT BUILT)")
        a("=" * 78)
        a("")
        a("  Triggered only because Job 2's PIT number cleared the floor.")
        a("  NOTHING below has been built, run, scored or registered. No DSR,")
        a("  no preservation_score, no mechanism-fidelity review. This is a")
        a("  feasibility proposal for the project owner to accept or reject.")
        a("")
        a("  SOURCES ACTUALLY READ THIS SESSION (sourcing limits stated)")
        a("  " + "-" * 74)
        a("   [P] Polakow, D. and T. Gebbie, 'How many independent bets are")
        a("       there in an emerging market?', arXiv:physics/0601166v3")
        a("       (11 Jan 2008). Downloaded and read this session.")
        a("       Its Lemma 1.1 is the exact point this whole job turns on:")
        a("       'Independence is not separateness ... The square root of N in")
        a("       mathematical statistics implies <independence> amongst")
        a("       statistical units (here bets) rather than simply the notion")
        a("       of <separate bets> as is most often implied.'")
        a("       Its Sec 1.2 estimates breadth from the eigenvalue spectrum of")
        a("       the return correlation matrix -- the same idea this project")
        a("       already uses, though [P] uses the integer Kaiser-Guttman")
        a("       count while this project uses sum(l)^2/sum(l^2). NOT adopting")
        a("       their estimator; citing the concept only.")
        a("")
        a("   [G] Grinold, R. C. (1989), 'The fundamental law of active")
        a("       management', Journal of Portfolio Management 15, 30-37.")
        a("       SOURCING LIMIT, STATED PLAINLY: Grinold (1989) itself was NOT")
        a("       read. This reference is quoted as it appears in [P]'s own")
        a("       bibliography (ref [3]). Treat as a second-hand citation.")
        a("")
        a("   THE FORMULA, AND HOW IT WAS VERIFIED WITHOUT READING [G]:")
        a("       IR = IC * sqrt(BR)")
        a("       [P] does not print this equation in its extractable text, but")
        a("       it gives a worked example in Sec 1.1: 'assume we have a 60%")
        a("       chance of getting equity bets correct. A bet on one underlying")
        a("       will yield an IR of 0.2, a bet on five underlying securities,")
        a("       an IR of 0.45 and a bet on 20 underlying securities, an IR of")
        a("       0.90.'  Checking against IR = IC*sqrt(BR) with IC = 0.2:")
        a(f"         sqrt(1)*0.2  = {0.2 * np.sqrt(1):.4f}  vs printed 0.2")
        a(f"         sqrt(5)*0.2  = {0.2 * np.sqrt(5):.4f}  vs printed 0.45")
        a(f"         sqrt(20)*0.2 = {0.2 * np.sqrt(20):.4f}  vs printed 0.90")
        a("       The form is therefore CONFIRMED numerically against a real")
        a("       source's own printed numbers, not recalled from memory.")
        a("")
        a("   CAVEAT ON BR THAT MUST NOT BE GLOSSED: in [G]'s formulation BR is")
        a("   the number of independent bets PER YEAR (decisions), whereas the")
        a("   effective-breadth statistic measured here is CROSS-SECTIONAL")
        a("   (instruments). [P] itself treats N cross-sectionally. Conflating")
        a("   the two is a known ambiguity in the literature and NO numeric IR")
        a("   forecast is produced here because of it. Resolving it is a")
        a("   prerequisite of any DSR N assumption, not a detail.")
        a("")
        a("  (a) FACTOR-MOMENTUM SIGNAL on the extracted common factor(s)")
        a("  " + "-" * 74)
        a(f"      Trade trend on the {k_headline} extracted factor return series")
        a("      themselves (each factor is a real, tradable long/short")
        a("      portfolio of the 31 instruments -- the eigenvector IS a weight")
        a("      vector, which is what makes this implementable at all).")
        a("")
        a("      STATISTICAL REQUIREMENT -- WHY IT IS DIFFERENT:")
        a(f"      This is a {k_headline}-bet strategy at most, and PC1 alone")
        a(f"      carries {eigenvalues[0] / n:.1%} of total variance, so it is")
        a("      closer to a 1-2 bet strategy in practice. The multi-bet")
        a("      law-of-large-numbers argument that CLAUDE.md's whole approach")
        a("      rests on DOES NOT APPLY to it. Per [P] Lemma 1.1 the sqrt(N)")
        a("      benefit requires independence, and these factors are few.")
        a("      Consequence: it cannot borrow statistical credibility from")
        a("      diversification and must instead earn it from EFFECT SIZE and")
        a("      LENGTH OF HISTORY. Its DSR must therefore be run at a MORE")
        a("      CONSERVATIVE (smaller) effective-N than a multi-bet family --")
        a("      a small n_local is NOT a licence for a lenient denominator,")
        a("      because the trials are few AND the bets are few.")
        a("      RECOMMENDATION: treat a pass here as UNRESOLVED by default")
        a("      under the project's existing two-tier rule unless it clears")
        a("      the most conservative rung of the {n_local,37,362,1031} ladder.")
        a("")
        a("      HONEST PRIOR: 'momentum on the first principal component of a")
        a("      futures panel' is close to what the CTA industry already sells")
        a("      as its core product. The prior that this is un-arbitraged is")
        a("      LOW. Flagged now rather than discovered after a build.")
        a("")
        a("  (b) IDIOSYNCRATIC TSMOM on the residual panel")
        a("  " + "-" * 74)
        a(f"      31 residual series, PIT effective breadth {pit_breadth:.4f} >=")
        a(f"      {EFFECTIVE_BREADTH_FLOOR}. This one CAN use the standard")
        a("      multi-bet approach and the project's normal DSR treatment,")
        a("      because the gate it was blocked on is now (conditionally) met.")
        a("")
        a("      BUT THREE CONDITIONS BEFORE IT IS TREATED AS UNBLOCKED:")
        a("      1. COST. The residual retains "
          f"{feasibility['mean_residual_variance_share']:.1%} of each")
        a("         instrument's variance on average, so restoring the raw risk")
        a("         target needs about "
          f"{feasibility['gross_leverage_multiple_to_restore_raw_risk']:.2f}x gross exposure, while")
        a("         spread and commission are charged on gross notional and do")
        a("         not shrink. Cost per unit of risk is therefore roughly that")
        a("         multiple higher BEFORE the extra turnover of continuously")
        a("         re-hedging 6 factor legs as the eigenvectors drift. Per")
        a("         CLAUDE.md cost realism must feed the DSR itself, not sit as")
        a("         a side note -- so this is a gating input, not a caveat.")
        a("      2. K-DEPENDENCE. The floor is cleared only for k in "
          f"{k_pass}. A")
        a("         design whose feasibility depends on removing exactly the")
        a("         RMT-chosen number of factors is fragile; the owner should")
        a("         decide whether that is acceptable.")
        a("      3. THE BREADTH IS OF THE RESIDUAL, NOT OF A STRATEGY. A high")
        a("         effective breadth says the residual series are close to")
        a("         independent. It says NOTHING about whether trend-following")
        a("         works on them. The gate was only ever a precondition for")
        a("         the test to be meaningful, never evidence of an edge.")
        a("")
        a("  WHAT THE OWNER IS BEING ASKED TO DECIDE")
        a("  " + "-" * 74)
        a("      Whether to authorise building (b) as a normal candidate family,")
        a("      and whether (a) is worth building at all given its low prior")
        a("      and its weaker statistical footing. Neither is started.")
        a("")

    a("JUDGMENT CALLS")
    a("=" * 78)
    for key, text in report["judgment_calls"].items():
        a(f"  {key}: {text}")
    a("")
    a("EXPLICITLY NOT DONE")
    a("=" * 78)
    for item in report["explicitly_not_done"]:
        a(f"  - {item}")
    a("")

    OUT_TXT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {OUT_TXT}")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
