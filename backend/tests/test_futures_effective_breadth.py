"""Tests for the futures effective-breadth measurement module.

Structure, in the order that matters:
  1. ANALYTIC cases -- matrices whose true effective breadth is derivable by
     hand, so the implementation is checked against arithmetic rather than
     against itself.
  2. The Frobenius cross-check agreeing with the eigenvalue route.
  3. Staggered-inception handling.
  4. REGRESSION against the published 7.10 / 8.11 baselines, from committed
     correlation-matrix fixtures (no network).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.futures_effective_breadth import (
    EFFECTIVE_BREADTH_FLOOR,
    MIN_OVERLAP_TRADING_DAYS,
    PUBLISHED_STEP1_BREADTH,
    PUBLISHED_STEP1B_BREADTH,
    RECENT_REGIME_WINDOW_TRADING_DAYS,
    common_window_correlation,
    conservative_correlation_matrix,
    conservative_pair_correlation,
    effective_breadth_frobenius,
    effective_breadth_from_correlation,
    inception_table,
    measure_futures_effective_breadth,
    minimum_eigenvalue,
    pairwise_complete_correlation,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# 1. ANALYTIC CASES -- true answers derived by hand
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [2, 3, 5, 11, 31])
def test_identity_matrix_has_breadth_exactly_n(n):
    """n mutually uncorrelated instruments are n independent bets.
    Eigenvalues are all 1, so sum(l)^2/sum(l^2) = n^2/n = n."""
    corr = np.eye(n)
    assert effective_breadth_from_correlation(corr) == pytest.approx(n, abs=1e-12)
    assert effective_breadth_frobenius(corr) == pytest.approx(n, abs=1e-12)


@pytest.mark.parametrize("n", [2, 3, 5, 11, 31])
def test_all_ones_matrix_has_breadth_exactly_one(n):
    """n perfect copies of one series are one bet. Eigenvalues are n and
    n-1 zeros, so n^2/n^2 = 1."""
    corr = np.ones((n, n))
    assert effective_breadth_from_correlation(corr) == pytest.approx(1.0, abs=1e-12)
    assert effective_breadth_frobenius(corr) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize(("n_blocks", "block_size"), [(2, 3), (3, 4), (5, 2), (4, 8)])
def test_perfect_blocks_give_breadth_equal_to_the_number_of_blocks(n_blocks, block_size):
    """k blocks of m perfectly-correlated instruments, blocks mutually
    uncorrelated, is exactly k independent bets.

    By hand: each block contributes one eigenvalue m and (m-1) zeros.
    sum(l) = k*m = n; sum(l^2) = k*m^2. So breadth = (km)^2/(km^2) = k.
    """
    block = np.ones((block_size, block_size))
    corr = np.zeros((n_blocks * block_size, n_blocks * block_size))
    for b in range(n_blocks):
        lo = b * block_size
        corr[lo : lo + block_size, lo : lo + block_size] = block

    assert effective_breadth_from_correlation(corr) == pytest.approx(n_blocks, abs=1e-10)
    assert effective_breadth_frobenius(corr) == pytest.approx(n_blocks, abs=1e-10)


@pytest.mark.parametrize("n", [3, 8, 31])
@pytest.mark.parametrize("rho", [0.0, 0.1, 0.35, 0.6, 0.9])
def test_equicorrelated_matrix_matches_its_closed_form(n, rho):
    """An equicorrelated matrix has eigenvalues 1+(n-1)rho once and 1-rho
    (n-1) times, so the closed form is

        n^2 / [ (1+(n-1)rho)^2 + (n-1)(1-rho)^2 ]

    computed here independently of the implementation.
    """
    corr = np.full((n, n), rho)
    np.fill_diagonal(corr, 1.0)

    expected = n**2 / ((1 + (n - 1) * rho) ** 2 + (n - 1) * (1 - rho) ** 2)
    assert effective_breadth_from_correlation(corr) == pytest.approx(expected, rel=1e-12)
    assert effective_breadth_frobenius(corr) == pytest.approx(expected, rel=1e-12)


def test_breadth_is_bounded_between_one_and_n():
    rng = np.random.default_rng(0)
    for _ in range(25):
        n = int(rng.integers(3, 20))
        data = rng.normal(size=(400, n))
        corr = pd.DataFrame(data).corr()
        breadth = effective_breadth_from_correlation(corr)
        assert 1.0 - 1e-9 <= breadth <= n + 1e-9


def test_adding_a_duplicate_column_does_not_increase_breadth():
    """The property that makes this metric worth using: nominal count can be
    inflated by duplication, effective breadth cannot."""
    rng = np.random.default_rng(4)
    panel = pd.DataFrame(rng.normal(size=(800, 5)), columns=list("abcde"))
    before = effective_breadth_from_correlation(panel.corr())
    panel["a_copy"] = panel["a"]
    after = effective_breadth_from_correlation(panel.corr())
    assert after <= before + 1e-9


# ---------------------------------------------------------------------------
# 2. THE CROSS-CHECK
# ---------------------------------------------------------------------------


def test_frobenius_and_eigenvalue_routes_agree_on_random_correlation_matrices():
    """They are the same quantity via different identities; disagreement
    beyond floating point means one is broken."""
    rng = np.random.default_rng(99)
    for _ in range(50):
        n = int(rng.integers(3, 25))
        data = rng.normal(size=(300, n))
        corr = pd.DataFrame(data).corr()
        eigen = effective_breadth_from_correlation(corr)
        frob = effective_breadth_frobenius(corr)
        assert abs(eigen - frob) < 1e-9


def test_frobenius_route_uses_no_eigendecomposition(monkeypatch):
    """Guards the independence of the cross-check: if the Frobenius route
    secretly called an eigen routine it would not be an independent check
    at all."""
    import numpy.linalg as npl

    def explode(*_args, **_kwargs):
        raise AssertionError("Frobenius route must not call an eigen routine")

    monkeypatch.setattr(npl, "eigvalsh", explode)
    monkeypatch.setattr(npl, "eigh", explode)
    monkeypatch.setattr(npl, "eig", explode)

    corr = np.eye(6)
    assert effective_breadth_frobenius(corr) == pytest.approx(6.0)


def test_square_input_is_required():
    with pytest.raises(ValueError):
        effective_breadth_from_correlation(np.ones((3, 4)))
    with pytest.raises(ValueError):
        effective_breadth_frobenius(np.ones((3, 4)))


def test_non_finite_input_returns_nan_rather_than_a_wrong_number():
    corr = np.eye(4)
    corr[0, 1] = np.nan
    assert np.isnan(effective_breadth_from_correlation(corr))
    assert np.isnan(effective_breadth_frobenius(corr))


# ---------------------------------------------------------------------------
# 3. STAGGERED INCEPTION
# ---------------------------------------------------------------------------


def _staggered_panel(seed: int = 1) -> pd.DataFrame:
    """Five instruments; the fifth starts late, mimicking RTY (2017) inside
    a 2013-start universe."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2013-01-01", periods=1800)
    panel = pd.DataFrame(
        rng.normal(0.0, 0.01, size=(len(index), 5)),
        index=index,
        columns=["a", "b", "c", "d", "late"],
    )
    panel.loc[panel.index[:1100], "late"] = np.nan
    return panel


def test_common_window_discards_history_and_pairwise_does_not():
    panel = _staggered_panel()
    common = common_window_correlation(panel)
    pairwise, overlaps = pairwise_complete_correlation(panel)

    assert common.shape == pairwise.shape == (5, 5)
    # the a/b pair has the full 1800 days pairwise, but only 700 in common
    assert overlaps.loc["a", "b"] == 1800
    assert overlaps.loc["a", "late"] == 700
    assert len(panel.dropna(how="any")) == 700


def test_pairwise_leaves_nan_rather_than_fabricating_a_thin_correlation():
    panel = _staggered_panel()
    # make 'late' start so late that its overlap is under the minimum
    panel.loc[panel.index[: len(panel) - 50], "late"] = np.nan
    pairwise, overlaps = pairwise_complete_correlation(panel)
    assert overlaps.loc["a", "late"] == 50
    assert np.isnan(pairwise.loc["a", "late"])


def test_measurement_flags_a_non_psd_pairwise_matrix_rather_than_hiding_it():
    panel = _staggered_panel()
    result = measure_futures_effective_breadth(panel)
    # whichever way it lands, the diagnostic must be present and honest
    assert np.isfinite(result.pairwise.min_eigenvalue) or result.pairwise.n_missing_pairs
    if not result.pairwise.is_positive_semidefinite:
        assert any("not positive semi-definite" in n for n in result.notes)


def test_measurement_notes_when_the_common_window_discards_history():
    panel = _staggered_panel()
    result = measure_futures_effective_breadth(panel)
    assert any("staggered inception" in n for n in result.notes)


def test_inception_table_reports_the_real_start_dates():
    panel = _staggered_panel()
    table = inception_table(panel)
    assert table.loc["a", "n_observations"] == 1800
    assert table.loc["late", "n_observations"] == 700
    assert table.loc["late", "first_observation"] > table.loc["a", "first_observation"]


def test_measurement_agrees_with_the_shared_commodities_implementation():
    """measure_futures_effective_breadth raises if it has drifted from
    cross_sectional_commodities.effective_breadth; this exercises that
    path on a real panel."""
    panel = _staggered_panel()
    result = measure_futures_effective_breadth(panel)
    from app.services.research_lab.cross_sectional_commodities import effective_breadth

    assert result.common_window.breadth_eigenvalue == pytest.approx(
        effective_breadth(panel), abs=1e-9
    )


# ---------------------------------------------------------------------------
# The max(full, trailing) redundancy rule
# ---------------------------------------------------------------------------


def test_conservative_pair_correlation_takes_the_higher_of_the_two_windows():
    """Reproduces the shape of the PCY/EMB confound: two series that are
    nearly unrelated early and nearly identical recently. A full-window
    correlation alone would understate their redundancy."""
    rng = np.random.default_rng(21)
    n_early, n_recent = 2000, 1260
    index = pd.bdate_range("2010-01-01", periods=n_early + n_recent)

    a = rng.normal(size=n_early + n_recent)
    b = np.empty_like(a)
    b[:n_early] = rng.normal(size=n_early)  # unrelated early
    b[n_early:] = a[n_early:] + rng.normal(0.0, 0.05, n_recent)  # near-identical late

    series_a = pd.Series(a, index=index)
    series_b = pd.Series(b, index=index)

    stats = conservative_pair_correlation(series_a, series_b)
    assert stats is not None
    assert stats["recent_window_correlation"] > 0.9
    assert stats["full_window_correlation"] < 0.6
    assert stats["operative_correlation"] == stats["recent_window_correlation"]
    assert stats["recent_window_days_used"] == RECENT_REGIME_WINDOW_TRADING_DAYS


def test_conservative_pair_correlation_returns_none_on_a_short_overlap():
    index = pd.bdate_range("2020-01-01", periods=100)
    a = pd.Series(np.arange(100.0), index=index)
    b = pd.Series(np.arange(100.0), index=index)
    assert conservative_pair_correlation(a, b) is None


def test_conservative_matrix_is_never_below_the_common_window_matrix():
    """The rule is 'more conservative', i.e. it can only raise a measured
    correlation, never lower it."""
    rng = np.random.default_rng(31)
    index = pd.bdate_range("2010-01-01", periods=3000)
    panel = pd.DataFrame(rng.normal(size=(3000, 6)), index=index, columns=list("abcdef"))

    conservative = conservative_correlation_matrix(panel)
    full = panel.corr()
    off_diagonal = ~np.eye(6, dtype=bool)
    assert (
        conservative.to_numpy()[off_diagonal] >= full.to_numpy()[off_diagonal] - 1e-12
    ).all()


def test_conservative_matrix_diagonal_is_exactly_one():
    rng = np.random.default_rng(33)
    index = pd.bdate_range("2010-01-01", periods=2000)
    panel = pd.DataFrame(rng.normal(size=(2000, 4)), index=index, columns=list("abcd"))
    conservative = conservative_correlation_matrix(panel)
    assert np.allclose(np.diag(conservative.to_numpy()), 1.0)


# ---------------------------------------------------------------------------
# 4. REGRESSION AGAINST THE PUBLISHED BASELINES
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / name, index_col=0)


def test_reproduces_step1_published_effective_breadth_exactly():
    """The 43-ticker pooled ETF/cash universe published 7.098862632956790 on
    2026-09-05. This fixture is that run's own pooled correlation matrix,
    regenerated on 2026-09-07 through the same loaders (which reproduced the
    published figure to 3e-15 and matched its window and 3560-row count
    exactly). If this drifts, the methodology this module reuses is no
    longer the methodology that produced the number the 15 floor was applied
    to."""
    corr = _load_fixture("tsmom_step1_pooled_correlation_43.csv")
    assert corr.shape == (43, 43)

    eigen = effective_breadth_from_correlation(corr)
    frobenius = effective_breadth_frobenius(corr)

    assert eigen == pytest.approx(PUBLISHED_STEP1_BREADTH, abs=1e-9)
    assert frobenius == pytest.approx(PUBLISHED_STEP1_BREADTH, abs=1e-9)
    assert abs(eigen - frobenius) < 1e-9
    assert eigen == pytest.approx(7.10, abs=0.005)


def test_reproduces_step1b_published_effective_breadth_exactly():
    """The 68-ticker expanded universe published 8.107830637943762."""
    corr = _load_fixture("tsmom_step1b_pooled_correlation_68.csv")
    assert corr.shape == (68, 68)

    eigen = effective_breadth_from_correlation(corr)
    frobenius = effective_breadth_frobenius(corr)

    assert eigen == pytest.approx(PUBLISHED_STEP1B_BREADTH, abs=1e-9)
    assert frobenius == pytest.approx(PUBLISHED_STEP1B_BREADTH, abs=1e-9)
    assert abs(eigen - frobenius) < 1e-9
    assert eigen == pytest.approx(8.11, abs=0.005)


def test_both_published_baselines_fail_the_floor_as_recorded():
    """Sanity: the whole reason a futures universe is being sourced is that
    both ETF attempts failed the 15 floor. If this ever passes, something
    about the floor or the baselines has been changed."""
    assert PUBLISHED_STEP1_BREADTH < EFFECTIVE_BREADTH_FLOOR
    assert PUBLISHED_STEP1B_BREADTH < EFFECTIVE_BREADTH_FLOOR


def test_published_fixtures_are_genuine_correlation_matrices():
    """Guards the fixtures themselves against silent corruption."""
    for name, n in (
        ("tsmom_step1_pooled_correlation_43.csv", 43),
        ("tsmom_step1b_pooled_correlation_68.csv", 68),
    ):
        corr = _load_fixture(name).to_numpy()
        assert corr.shape == (n, n)
        assert np.allclose(np.diag(corr), 1.0)
        assert np.allclose(corr, corr.T)
        assert minimum_eigenvalue(corr) > 0  # a real sample correlation matrix is PD
        assert np.all(np.abs(corr) <= 1.0 + 1e-12)


# ---------------------------------------------------------------------------
# Gate / verdict behaviour
# ---------------------------------------------------------------------------


def test_floor_is_fifteen():
    assert EFFECTIVE_BREADTH_FLOOR == 15.0
    assert MIN_OVERLAP_TRADING_DAYS == 252


def test_a_wide_independent_universe_passes_the_floor():
    """31 near-independent instruments should clear 15 comfortably -- proves
    the gate can actually pass, so a later FAILS_FLOOR is informative rather
    than structural."""
    rng = np.random.default_rng(77)
    index = pd.bdate_range("2013-01-02", periods=3000)
    panel = pd.DataFrame(
        rng.normal(0.0, 0.01, size=(3000, 31)),
        index=index,
        columns=[f"i{k}" for k in range(31)],
    )
    result = measure_futures_effective_breadth(panel)
    assert result.common_window.breadth_eigenvalue > EFFECTIVE_BREADTH_FLOOR
    assert result.passes_floor
    assert result.verdict() == "PASSES_FLOOR"
    assert result.common_window.is_safely_interpretable


def test_a_redundant_universe_fails_the_floor():
    rng = np.random.default_rng(78)
    index = pd.bdate_range("2013-01-02", periods=3000)
    driver = rng.normal(0.0, 0.01, size=3000)
    panel = pd.DataFrame(
        {f"i{k}": driver + rng.normal(0.0, 0.001, 3000) for k in range(31)}, index=index
    )
    result = measure_futures_effective_breadth(panel)
    assert result.common_window.breadth_eigenvalue < EFFECTIVE_BREADTH_FLOOR
    assert not result.passes_floor
    assert result.verdict() == "FAILS_FLOOR"


def test_disagreement_between_estimates_is_surfaced_as_unresolved():
    """A universe engineered so the two estimates straddle the floor must
    report UNRESOLVED rather than quietly picking one."""
    rng = np.random.default_rng(4242)
    index = pd.bdate_range("2013-01-02", periods=3000)
    # 20 independent instruments over the full window...
    panel = pd.DataFrame(
        rng.normal(0.0, 0.01, size=(3000, 20)),
        index=index,
        columns=[f"i{k}" for k in range(20)],
    )
    # ...plus late-starting near-duplicates that collapse the common window
    driver = panel["i0"]
    for k in range(6):
        col = pd.Series(np.nan, index=index)
        col.iloc[2600:] = (driver.iloc[2600:] * 0.99).to_numpy()
        panel[f"dup{k}"] = col

    result = measure_futures_effective_breadth(panel)
    # not asserting which way each lands -- asserting the machinery reports
    # disagreement rather than silently resolving it
    if result.estimates_disagree_materially:
        assert result.verdict() == "UNRESOLVED_ESTIMATES_DISAGREE"
    else:
        assert result.verdict() in {"PASSES_FLOOR", "FAILS_FLOOR"}


def test_cross_check_delta_is_tiny_on_a_real_measurement():
    rng = np.random.default_rng(55)
    index = pd.bdate_range("2013-01-02", periods=2000)
    panel = pd.DataFrame(
        rng.normal(0.0, 0.01, size=(2000, 12)),
        index=index,
        columns=[f"i{k}" for k in range(12)],
    )
    result = measure_futures_effective_breadth(panel)
    assert result.common_window.cross_check_delta < 1e-9
    assert result.common_window.is_safely_interpretable
