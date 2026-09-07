"""INDEPENDENT re-derivation of the headline numbers in
run_tsmom_factor_decomposition_2026_09_07.py.

Per CLAUDE.md workflow rule 2 ("re-derive key numbers by hand from
primitives"), this script deliberately shares NO code with the script it is
checking and NO code with app/services/research_lab/futures_effective_breadth.py:

  - It re-reads the chained CSVs itself with a freshly written loader.
  - It computes the correlation matrix with numpy alone (np.corrcoef), not
    pandas .corr().
  - It computes effective breadth via the FROBENIUS identity
    n^2 / sum_ij C_ij^2, which needs no eigendecomposition at all -- a
    different mathematical route from the eigenvalue formula
    sum(l)^2/sum(l^2) the module uses. (The two are equal for any symmetric
    matrix, so agreement is a real check, not a tautology of shared code.)
  - It re-implements the point-in-time residualization from scratch with an
    explicit per-instrument loop and np.polyfit-free normal equations,
    rather than the vectorized lstsq the main script uses.

If any number disagrees beyond floating-point tolerance, the main report is
wrong and must not be trusted.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

_BACKEND = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND.parent

CANDIDATES = [
    _BACKEND / "data" / "futures_daily" / "cme_span" / "continuous",
    _REPO_ROOT / ".claude" / "worktrees" / "futures-span-full-pull" / "backend"
    / "data" / "futures_daily" / "cme_span" / "continuous",
    _REPO_ROOT.parent.parent.parent / ".claude" / "worktrees"
    / "futures-span-full-pull" / "backend" / "data" / "futures_daily"
    / "cme_span" / "continuous",
]

EXPECT_RAW_BREADTH = 10.008142587700915
EXPECT_PIT_BREADTH_K6 = 16.954956365235905
EXPECT_IN_SAMPLE_K6 = 19.000660966769626
BURN_IN = 504
REFIT = 21
K = 6
FLOOR = 15.0


def find_dir() -> Path:
    for c in CANDIDATES:
        if c.is_dir() and list(c.glob("*.csv")):
            return c
    raise SystemExit("no continuous CSV directory found")


def load_panel(directory: Path) -> tuple[list[str], list[str], np.ndarray]:
    """Hand-rolled loader: csv module only, no pandas."""
    per_root: dict[str, dict[str, float]] = {}
    for path in sorted(directory.glob("*.csv")):
        root = path.stem
        rows: dict[str, float] = {}
        with path.open(newline="", encoding="utf-8") as handle:
            for record in csv.DictReader(handle):
                raw = record["chained_daily_return"]
                if raw == "" or raw is None:
                    continue
                try:
                    value = float(raw)
                except ValueError:
                    continue
                if np.isfinite(value):
                    rows[record["trade_date"][:10]] = value
        per_root[root] = rows

    roots = sorted(per_root)
    all_dates = sorted(set().union(*(set(v) for v in per_root.values())))
    matrix = np.full((len(all_dates), len(roots)), np.nan)
    index = {d: i for i, d in enumerate(all_dates)}
    for j, root in enumerate(roots):
        for date, value in per_root[root].items():
            matrix[index[date], j] = value
    return roots, all_dates, matrix


def breadth_frobenius(block: np.ndarray) -> float:
    """n^2 / sum_ij C_ij^2 -- no eigendecomposition anywhere."""
    corr = np.corrcoef(block, rowvar=False)
    n = corr.shape[0]
    return float(n**2 / (corr**2).sum())


def pit_residuals(common: np.ndarray, k: int, burn_in: int, refit: int) -> np.ndarray:
    """From-scratch PIT residualization, explicit per-instrument normal
    equations rather than a batched lstsq."""
    n_obs, n_inst = common.shape
    out = np.full((n_obs, n_inst), np.nan)
    start = burn_in
    while start < n_obs:
        stop = min(start + refit, n_obs)
        prior = common[:start]
        mu = prior.mean(axis=0)
        sd = prior.std(axis=0, ddof=1)
        zp = (prior - mu) / sd
        corr = np.corrcoef(zp, rowvar=False)
        vals, vecs = np.linalg.eigh(corr)
        loadings = vecs[:, np.argsort(vals)[::-1]][:, :k]
        fp = zp @ loadings

        block = (common[start:stop] - mu) / sd
        fb = block @ loadings
        xp = np.column_stack([np.ones(len(fp)), fp])
        xb = np.column_stack([np.ones(len(fb)), fb])
        gram = xp.T @ xp
        for i in range(n_inst):
            beta = np.linalg.solve(gram, xp.T @ zp[:, i])
            out[start:stop, i] = block[:, i] - xb @ beta
        start = stop
    return out[burn_in:]


def in_sample_residuals(common: np.ndarray, k: int) -> np.ndarray:
    z = (common - common.mean(axis=0)) / common.std(axis=0, ddof=1)
    corr = np.corrcoef(z, rowvar=False)
    vals, vecs = np.linalg.eigh(corr)
    loadings = vecs[:, np.argsort(vals)[::-1]][:, :k]
    return z - (z @ loadings) @ loadings.T


def main() -> None:
    directory = find_dir()
    roots, dates, matrix = load_panel(directory)
    print(f"independent loader: {matrix.shape[0]} dates x {len(roots)} roots")
    print(f"roots: {' '.join(roots)}")

    complete = ~np.isnan(matrix).any(axis=1)
    common = matrix[complete]
    common_dates = [d for d, keep in zip(dates, complete, strict=True) if keep]
    print(f"common window: {len(common)} rows, "
          f"{common_dates[0]} .. {common_dates[-1]}")

    checks: list[tuple[str, float, float]] = []

    raw = breadth_frobenius(common)
    checks.append(("raw universe breadth", raw, EXPECT_RAW_BREADTH))

    ins = breadth_frobenius(in_sample_residuals(common, K))
    checks.append((f"in-sample residual breadth k={K}", ins, EXPECT_IN_SAMPLE_K6))

    pit = breadth_frobenius(pit_residuals(common, K, BURN_IN, REFIT))
    checks.append((f"PIT residual breadth k={K}", pit, EXPECT_PIT_BREADTH_K6))

    print()
    ok = True
    for label, got, expected in checks:
        delta = abs(got - expected)
        agrees = delta < 1e-9
        ok = ok and agrees
        print(f"  {label:<34} independent {got:.12f}  "
              f"main {expected:.12f}  delta {delta:.2e}  "
              f"{'OK' if agrees else 'MISMATCH'}")

    print()
    print(f"  floor {FLOOR}: raw {'PASSES' if raw >= FLOOR else 'FAILS'}, "
          f"PIT residual {'PASSES' if pit >= FLOOR else 'FAILS'}")

    out = _BACKEND / "data" / "research_runs" / "tsmom_factor_decomposition_verification_2026-09-07.json"
    out.write_text(
        json.dumps(
            {
                "method": (
                    "independent re-derivation: hand-rolled csv loader (no "
                    "pandas), np.corrcoef, Frobenius identity n^2/sum(C_ij^2) "
                    "instead of the eigenvalue formula, from-scratch PIT "
                    "residualization with explicit normal equations"
                ),
                "n_common_observations": int(len(common)),
                "common_window": [common_dates[0], common_dates[-1]],
                "checks": [
                    {
                        "label": label,
                        "independent": got,
                        "main_script": expected,
                        "delta": abs(got - expected),
                        "agrees": bool(abs(got - expected) < 1e-9),
                    }
                    for label, got, expected in checks
                ],
                "all_agree": bool(ok),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"wrote {out}")
    if not ok:
        sys.exit("INDEPENDENT VERIFICATION FAILED")


if __name__ == "__main__":
    main()
