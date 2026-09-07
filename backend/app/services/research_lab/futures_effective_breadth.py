"""Effective-breadth measurement for the real futures universe (TSMOM
universe-validation prep, step 4).

WHAT THIS IS FOR
====================================================================
The TSMOM universe-validation plan gates on "effective breadth >= 15"
before any TSMOM pass/fail verdict is treated as trustworthy. Two ETF/cash
universes have already been measured against that floor and both failed:

    Step 1  (43 nominal tickers)  ->  7.098862632956790
    Step 1b (68 nominal tickers)  ->  8.107830637943762

Both are recorded in backend/data/research_runs/*_2026-09-05.json. Those
failures are what motivated sourcing real futures data. This module is the
instrument that will measure the futures universe against the same floor,
with the same methodology, so the three numbers are actually comparable.

METHODOLOGY IS REUSED, NOT REIMPLEMENTED
====================================================================
`cross_sectional_commodities.effective_breadth` is IMPORTED and called, not
copied. Re-typing sum(lambda)^2 / sum(lambda^2) here would create a second
implementation that could silently drift from the one that produced 7.10
and 8.11, making the comparison to the floor meaningless. The regression
test (tests/test_futures_effective_breadth.py) pins reproduction of both
published figures from committed correlation-matrix fixtures.

THE INDEPENDENT CROSS-CHECK, AND WHY IT IS EXACT
====================================================================
This project's established pattern for this specific calculation is to
verify the number a second time through a different mathematical identity.
For a correlation matrix C of size n there is an exact one that needs no
eigendecomposition at all:

    sum_i lambda_i   = trace(C)  = n          (unit diagonal)
    sum_i lambda_i^2 = trace(C^2) = ||C||_F^2 = sum_ij C_ij^2

    =>  effective breadth = n^2 / sum_ij C_ij^2

Both identities hold for ANY symmetric matrix: trace equals the eigenvalue
sum, and the squared Frobenius norm equals the sum of squared eigenvalues
(via C = Q L Q^T with Q orthogonal). So the Frobenius route is not an
approximation of the eigenvalue route -- the two agree to floating-point
rounding, and a disagreement beyond that means one of them is broken.

Note carefully: the Frobenius identity is well-defined for any symmetric
matrix, INCLUDING one that is not positive semi-definite. That is a trap,
not a convenience: the INTERPRETATION of the ratio as "effective number of
independent bets" requires non-negative eigenvalues. So the minimum
eigenvalue is always reported alongside, and a materially negative one is
flagged rather than silently swallowed (see StaggeredInceptionHandling).

STAGGERED INCEPTION -- THE REAL COMPLICATION HERE
====================================================================
The ETF universes of Steps 1 and 1b were measured on one common window via
dropna(how="any"), which was right for them. It is NOT automatically right
for the futures universe: not all 31 roots have data from 2013 (RTY starts
2017, per the chaining script's own inception table). A strict common
window would silently discard 2013-2016 for all 31 instruments to
accommodate the latest-starting one -- throwing away roughly a third of the
history to gain one instrument.

Both answers are therefore computed and BOTH are reported:

  COMMON_WINDOW    dropna(how="any"). Byte-identical in methodology to
                   Steps 1 and 1b, so it is the number that is strictly
                   comparable to 7.10 and 8.11, and it is the one the gate
                   is evaluated on by default. Always positive
                   semi-definite (it is a genuine sample correlation matrix
                   of a complete panel).

  PAIRWISE         Each pair uses its own overlap (min_overlap_days
                   enforced). Uses all available history and does not let
                   one late arrival truncate everyone, but the result is
                   NOT guaranteed positive semi-definite, because the
                   entries come from different samples. Reported with its
                   minimum eigenvalue so the reader can see how far from
                   PSD it is.

Reporting both, and reporting when they disagree, is the honest handling.
Picking whichever is higher would be exactly the kind of quiet choice that
turns a failed gate into a passed one.

THE max(full, trailing-1260) RULE
====================================================================
Step 1b found a real confound (PCY/EMB): thin, stale early-history trading
depressed a full-window correlation to 0.61 for a pair that has measured
0.93-0.97 in every complete recent year. A single full-window correlation
would have wrongly accepted them as distinct. The fix adopted there, and
reused here unchanged, is to take the MORE CONSERVATIVE (higher) of the
full-window correlation and the correlation over the trailing 1260 trading
days (~5 years).

That rule is applied here in two places, with different status:

  REDUNDANCY SCREENING (`conservative_pair_correlation`) -- this is the
  rule's home use, the one Step 1b established, and it is applied exactly
  as Step 1b applied it.

  A CONSERVATIVE BREADTH VARIANT (`conservative_correlation_matrix`) --
  reported as a ROBUSTNESS number, never as the headline. An elementwise
  max of two correlation matrices is generally NOT positive semi-definite
  (the operation is not PSD-preserving), so this variant's breadth can be
  distorted in ways the eigenvalue interpretation does not support. It is
  computed because the task calls for the redundancy rule to be honoured
  everywhere a correlation is computed, and it is labelled with its
  minimum eigenvalue so nobody mistakes it for the primary measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# Imported, never re-typed -- see module docstring.
from app.services.research_lab.cross_sectional_commodities import effective_breadth

# ---------------------------------------------------------------------------
# PRE-DECLARED CONSTANTS
# ---------------------------------------------------------------------------

#: The gate the TSMOM universe-validation plan pre-declared. The plan's
#: wording was "15-25+"; 15 is the floor, and the floor is what gates.
EFFECTIVE_BREADTH_FLOOR = 15.0

#: ~5 years. This project's standing "recent regime" window -- the same
#: constant Step 1b used (RECENT_REGIME_WINDOW_TRADING_DAYS) and the same
#: window cross_sectional_commodities uses for long-run reversal.
RECENT_REGIME_WINDOW_TRADING_DAYS = 1260

#: A pair whose overlap is shorter than this is not trusted to yield a
#: correlation at all. Matches Step 1b's redundancy-screen minimum.
MIN_OVERLAP_TRADING_DAYS = 252

#: How far below zero the smallest eigenvalue may drift before the result is
#: flagged as not-safely-interpretable. Sampling noise on a genuine PSD
#: matrix lands at ~1e-12; anything at 1e-8 or worse is structural.
PSD_TOLERANCE = 1e-8

#: Published baselines this module's regression test must reproduce.
PUBLISHED_STEP1_BREADTH = 7.098862632956790
PUBLISHED_STEP1B_BREADTH = 8.107830637943762


def effective_breadth_from_correlation(corr: np.ndarray | pd.DataFrame) -> float:
    """sum(lambda)^2 / sum(lambda^2) over a correlation matrix's spectrum.

    The eigenvalue route. Kept as a thin wrapper so callers that already
    hold a correlation matrix (rather than a return panel) go through the
    same formula as `cross_sectional_commodities.effective_breadth`, which
    takes a return panel and computes the correlation itself.
    """
    matrix = np.asarray(
        corr.to_numpy() if isinstance(corr, pd.DataFrame) else corr, dtype=float
    )
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("correlation matrix must be square")
    if matrix.shape[0] < 2:
        return float("nan")
    if not np.all(np.isfinite(matrix)):
        return float("nan")
    eigenvalues = np.linalg.eigvalsh(matrix)
    denominator = float((eigenvalues**2).sum())
    if denominator <= 0.0:
        return float("nan")
    return float(eigenvalues.sum() ** 2 / denominator)


def effective_breadth_frobenius(corr: np.ndarray | pd.DataFrame) -> float:
    """The SAME quantity via trace/Frobenius, with no eigendecomposition.

        breadth = trace(C)^2 / ||C||_F^2 = n^2 / sum_ij C_ij^2

    Independent of `effective_breadth_from_correlation` in implementation
    (no call to any eigen routine) while being mathematically identical for
    a symmetric matrix. This is the cross-check, not a second opinion.

    trace(C)^2 is used rather than hard-coding n^2 so the identity still
    holds if a caller ever passes a covariance-like matrix without a unit
    diagonal -- in which case the eigenvalue route and this route still
    agree with each other, even though neither is "effective breadth".
    """
    matrix = np.asarray(
        corr.to_numpy() if isinstance(corr, pd.DataFrame) else corr, dtype=float
    )
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("correlation matrix must be square")
    if matrix.shape[0] < 2:
        return float("nan")
    if not np.all(np.isfinite(matrix)):
        return float("nan")
    trace = float(np.trace(matrix))
    frobenius_squared = float((matrix**2).sum())
    if frobenius_squared <= 0.0:
        return float("nan")
    return float(trace**2 / frobenius_squared)


def minimum_eigenvalue(corr: np.ndarray | pd.DataFrame) -> float:
    """Smallest eigenvalue -- the PSD diagnostic reported next to every
    breadth number produced from a matrix that is not a straightforward
    complete-panel sample correlation."""
    matrix = np.asarray(
        corr.to_numpy() if isinstance(corr, pd.DataFrame) else corr, dtype=float
    )
    if matrix.shape[0] < 2 or not np.all(np.isfinite(matrix)):
        return float("nan")
    return float(np.linalg.eigvalsh(matrix).min())


def common_window_correlation(daily_returns: pd.DataFrame) -> pd.DataFrame:
    """Sample correlation on the strict common window -- dropna(how="any"),
    exactly as Steps 1 and 1b did. Always PSD."""
    usable = daily_returns.dropna(how="any")
    return usable.corr()


def pairwise_complete_correlation(
    daily_returns: pd.DataFrame,
    min_overlap_days: int = MIN_OVERLAP_TRADING_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Correlation where every pair uses its own overlap, so a late-starting
    instrument (RTY from 2017) does not truncate the whole panel.

    Returns (correlation, overlap_day_counts). A pair whose overlap is
    shorter than `min_overlap_days` gets NaN rather than a correlation
    computed from too few days; callers must decide what to do about it
    rather than having a fabricated number handed to them.
    """
    columns = list(daily_returns.columns)
    n = len(columns)
    corr = np.full((n, n), np.nan, dtype=float)
    overlaps = np.zeros((n, n), dtype=int)

    values = {c: daily_returns[c] for c in columns}
    for i in range(n):
        corr[i, i] = 1.0
        series_i = values[columns[i]]
        overlaps[i, i] = int(series_i.notna().sum())
        for j in range(i + 1, n):
            joined = pd.concat([series_i, values[columns[j]]], axis=1).dropna()
            overlaps[i, j] = overlaps[j, i] = len(joined)
            if len(joined) < min_overlap_days:
                continue
            value = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))
            corr[i, j] = corr[j, i] = value

    return (
        pd.DataFrame(corr, index=columns, columns=columns),
        pd.DataFrame(overlaps, index=columns, columns=columns),
    )


def conservative_pair_correlation(
    series_a: pd.Series,
    series_b: pd.Series,
    min_overlap_days: int = MIN_OVERLAP_TRADING_DAYS,
    recent_window_days: int = RECENT_REGIME_WINDOW_TRADING_DAYS,
) -> dict[str, Any] | None:
    """Step 1b's redundancy statistic, reused unchanged: the MORE
    CONSERVATIVE (higher) of the full-overlap correlation and the
    correlation over the trailing `recent_window_days` of that same overlap.

    Rationale (Step 1b, PCY/EMB): thin or stale early history can depress a
    full-window correlation far below what the same pair shows in its
    current mature trading regime, so a single full-window number can
    wrongly certify two near-identical instruments as distinct.

    Returns None when the overlap is too short to trust at all.
    """
    joined = pd.concat([series_a, series_b], axis=1).dropna()
    if len(joined) < min_overlap_days:
        return None
    full_corr = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))
    recent = joined.iloc[-recent_window_days:]
    recent_corr = (
        float(recent.iloc[:, 0].corr(recent.iloc[:, 1]))
        if len(recent) >= min_overlap_days
        else None
    )
    operative = max(full_corr, recent_corr) if recent_corr is not None else full_corr
    return {
        "operative_correlation": operative,
        "full_window_correlation": full_corr,
        "recent_window_correlation": recent_corr,
        "recent_window_days_used": len(recent) if recent_corr is not None else None,
        "overlap_days": len(joined),
    }


def conservative_correlation_matrix(
    daily_returns: pd.DataFrame,
    min_overlap_days: int = MIN_OVERLAP_TRADING_DAYS,
    recent_window_days: int = RECENT_REGIME_WINDOW_TRADING_DAYS,
) -> pd.DataFrame:
    """Elementwise max(full-overlap corr, trailing-window corr) for every
    pair -- the Step 1b rule applied across the whole matrix.

    ROBUSTNESS VARIANT ONLY. An elementwise max of two correlation matrices
    is not in general positive semi-definite, so the breadth computed from
    this matrix must always be reported with its minimum eigenvalue and
    must never be the headline number. See the module docstring.
    """
    columns = list(daily_returns.columns)
    n = len(columns)
    corr = np.full((n, n), np.nan, dtype=float)
    values = {c: daily_returns[c] for c in columns}
    for i in range(n):
        corr[i, i] = 1.0
        for j in range(i + 1, n):
            stats = conservative_pair_correlation(
                values[columns[i]], values[columns[j]], min_overlap_days, recent_window_days
            )
            if stats is not None:
                corr[i, j] = corr[j, i] = float(stats["operative_correlation"])
    return pd.DataFrame(corr, index=columns, columns=columns)


def inception_table(daily_returns: pd.DataFrame) -> pd.DataFrame:
    """First/last valid observation and usable count per instrument -- the
    staggered-inception picture, so a reader can see exactly how much
    history a strict common window is discarding and why."""
    rows = []
    for column in daily_returns.columns:
        series = daily_returns[column].dropna()
        rows.append(
            {
                "instrument": column,
                "first_observation": series.index.min() if len(series) else pd.NaT,
                "last_observation": series.index.max() if len(series) else pd.NaT,
                "n_observations": len(series),
            }
        )
    return pd.DataFrame(rows).set_index("instrument")


@dataclass(frozen=True)
class BreadthMeasurement:
    """One breadth number plus everything needed to trust or distrust it."""

    label: str
    breadth_eigenvalue: float
    breadth_frobenius: float
    n_instruments: int
    n_observations: int
    min_eigenvalue: float
    n_missing_pairs: int = 0

    @property
    def cross_check_delta(self) -> float:
        """|eigenvalue route - Frobenius route|. Must be ~0 to floating
        point; a material value means one route is broken."""
        if not np.isfinite(self.breadth_eigenvalue) or not np.isfinite(
            self.breadth_frobenius
        ):
            return float("nan")
        return abs(self.breadth_eigenvalue - self.breadth_frobenius)

    @property
    def is_positive_semidefinite(self) -> bool:
        return bool(np.isfinite(self.min_eigenvalue)) and (
            self.min_eigenvalue >= -PSD_TOLERANCE
        )

    @property
    def is_safely_interpretable(self) -> bool:
        """Whether this number may be read as 'effective number of
        independent bets' at all."""
        return (
            self.is_positive_semidefinite
            and np.isfinite(self.cross_check_delta)
            and self.cross_check_delta < 1e-6
            and self.n_missing_pairs == 0
        )


@dataclass(frozen=True)
class FuturesBreadthResult:
    """The full measurement. `common_window` is the gating number."""

    common_window: BreadthMeasurement
    pairwise: BreadthMeasurement
    conservative: BreadthMeasurement
    inception: pd.DataFrame
    common_window_start: pd.Timestamp | None
    common_window_end: pd.Timestamp | None
    floor: float = EFFECTIVE_BREADTH_FLOOR
    notes: list[str] = field(default_factory=list)

    @property
    def passes_floor(self) -> bool:
        """Evaluated on the COMMON-WINDOW number -- the one methodologically
        comparable to the 7.10 and 8.11 the floor was applied to before."""
        return bool(
            np.isfinite(self.common_window.breadth_eigenvalue)
            and self.common_window.breadth_eigenvalue >= self.floor
        )

    @property
    def estimates_disagree_materially(self) -> bool:
        """Common-window vs pairwise landing on opposite sides of the floor
        is the case that must never be resolved silently."""
        a = self.common_window.breadth_eigenvalue
        b = self.pairwise.breadth_eigenvalue
        if not (np.isfinite(a) and np.isfinite(b)):
            return True
        return (a >= self.floor) != (b >= self.floor)

    def verdict(self) -> str:
        if self.estimates_disagree_materially:
            return "UNRESOLVED_ESTIMATES_DISAGREE"
        return "PASSES_FLOOR" if self.passes_floor else "FAILS_FLOOR"


def _measure(label: str, corr: pd.DataFrame, n_observations: int) -> BreadthMeasurement:
    n_missing = int(corr.isna().to_numpy().sum())
    if n_missing:
        return BreadthMeasurement(
            label=label,
            breadth_eigenvalue=float("nan"),
            breadth_frobenius=float("nan"),
            n_instruments=int(corr.shape[0]),
            n_observations=n_observations,
            min_eigenvalue=float("nan"),
            n_missing_pairs=n_missing,
        )
    return BreadthMeasurement(
        label=label,
        breadth_eigenvalue=effective_breadth_from_correlation(corr),
        breadth_frobenius=effective_breadth_frobenius(corr),
        n_instruments=int(corr.shape[0]),
        n_observations=n_observations,
        min_eigenvalue=minimum_eigenvalue(corr),
        n_missing_pairs=0,
    )


def measure_futures_effective_breadth(
    daily_returns: pd.DataFrame,
    min_overlap_days: int = MIN_OVERLAP_TRADING_DAYS,
    recent_window_days: int = RECENT_REGIME_WINDOW_TRADING_DAYS,
) -> FuturesBreadthResult:
    """Measure a futures return panel's effective breadth three ways.

    `daily_returns` is a DataFrame of DAILY RETURNS (not prices), one column
    per continuous-contract instrument, indexed by date, with NaN wherever
    an instrument had not yet started. Chaining prices into returns is the
    caller's job (see chain_cme_span_continuous.py) -- this module measures,
    it does not construct.
    """
    notes: list[str] = []

    common_corr = common_window_correlation(daily_returns)
    common_panel = daily_returns.dropna(how="any")
    common = _measure("common_window", common_corr, len(common_panel))

    # Headline sanity: the shared implementation must agree with this
    # module's matrix-level route on the very same panel. If it does not,
    # the two have drifted and every comparison to 7.10/8.11 is void.
    shared_value = effective_breadth(daily_returns)
    if np.isfinite(shared_value) and np.isfinite(common.breadth_eigenvalue):
        drift = abs(shared_value - common.breadth_eigenvalue)
        if drift > 1e-9:
            raise AssertionError(
                "futures_effective_breadth has drifted from "
                f"cross_sectional_commodities.effective_breadth: {shared_value} vs "
                f"{common.breadth_eigenvalue} (delta {drift})"
            )

    pairwise_corr, _overlaps = pairwise_complete_correlation(
        daily_returns, min_overlap_days
    )
    pairwise = _measure("pairwise_complete", pairwise_corr, len(daily_returns))

    conservative_corr = conservative_correlation_matrix(
        daily_returns, min_overlap_days, recent_window_days
    )
    conservative = _measure(
        "conservative_max_rule", conservative_corr, len(daily_returns)
    )

    if not pairwise.is_positive_semidefinite:
        notes.append(
            "pairwise-complete correlation matrix is not positive semi-definite "
            f"(min eigenvalue {pairwise.min_eigenvalue:.6g}); its breadth is not "
            "safely interpretable as an independent-bet count"
        )
    if not conservative.is_positive_semidefinite:
        notes.append(
            "conservative max-rule matrix is not positive semi-definite "
            f"(min eigenvalue {conservative.min_eigenvalue:.6g}) -- expected, since "
            "an elementwise max of correlation matrices is not PSD-preserving; "
            "robustness only, never the headline"
        )
    if pairwise.n_missing_pairs:
        notes.append(
            f"{pairwise.n_missing_pairs} pairwise cells had under {min_overlap_days} "
            "overlapping days and were left NaN rather than fabricated"
        )

    total_rows = len(daily_returns)
    if total_rows and len(common_panel) < total_rows:
        notes.append(
            f"strict common window keeps {len(common_panel)} of {total_rows} rows "
            f"({len(common_panel) / total_rows:.1%}) -- staggered inception is "
            "discarding history; compare against the pairwise estimate"
        )

    return FuturesBreadthResult(
        common_window=common,
        pairwise=pairwise,
        conservative=conservative,
        inception=inception_table(daily_returns),
        common_window_start=(
            common_panel.index.min() if len(common_panel) else None
        ),
        common_window_end=(common_panel.index.max() if len(common_panel) else None),
        notes=notes,
    )
