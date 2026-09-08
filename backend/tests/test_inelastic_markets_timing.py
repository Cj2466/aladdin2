"""Tests for the Inelastic-Markets family (Gabaix & Koijen 2021, candidate #16).

The most important test here is test_pipeline_reproduces_the_closed_form_oracle_instrument:
CLAUDE.md requires that a published formula be validated against synthetic data
with a KNOWN true answer before being trusted on real data. The GIV estimator is
exactly the kind of thing that can look plausible while silently estimating the
wrong quantity -- which already happened once in this family (the first
implementation was built from the main text instead of Appendix B.2 and produced
a multiplier about a third of the paper's).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.inelastic_markets_timing import (
    AVAILABILITY_LAG_QUARTERS,
    CORPORATE_SECTOR_SERIES,
    GK_TABLE2_MULTIPLIERS,
    INELASTIC_N_TRIALS,
    PSEUDO_EQUAL_CAP_MULTIPLE,
    apply_holding,
    build_giv,
    giv_instrument,
    instrument_sectors,
    panel_residuals,
    position_from_zscore,
    pseudo_equal_weights,
    replay_spec,
    spec_grid,
    standardize,
    verdict_from_dsr,
)


def _periods(n: int, start: str = "1993Q1") -> pd.PeriodIndex:
    return pd.period_range(start, periods=n, freq="Q")


# ---------------------------------------------------------------------------
# B.2 step 1 -- the pseudo-equal weights
# ---------------------------------------------------------------------------
def test_pseudo_equal_weights_sum_to_one_and_respect_the_cap():
    rng = np.random.default_rng(0)
    idx = _periods(120)
    # deliberately heterogeneous volatilities so the cap actually binds
    panel = pd.DataFrame(
        {f"s{i}": rng.normal(0, scale, len(idx)) for i, scale in enumerate([0.01, 0.02, 0.05, 0.1, 0.2])},
        index=idx,
    )
    w = pseudo_equal_weights(panel)
    assert w.sum() == pytest.approx(1.0, abs=1e-9)
    cap = PSEUDO_EQUAL_CAP_MULTIPLE / len(w)
    assert w.max() <= cap + 1e-12
    # the lowest-variance sector must not be below the highest-variance one
    assert w["s0"] > w["s4"]


def test_pseudo_equal_weights_are_equal_when_variances_are_equal():
    rng = np.random.default_rng(1)
    idx = _periods(200)
    panel = pd.DataFrame({f"s{i}": rng.normal(0, 0.05, len(idx)) for i in range(4)}, index=idx)
    w = pseudo_equal_weights(panel)
    # With equal TRUE variances, sample variances still differ, so the weights
    # are near -- not exactly -- 1/N. The tolerance is set from the sampling
    # noise, not tightened until it happens to pass.
    assert w.max() - w.min() < 0.10
    assert w.min() > 0.5 / len(w)


# ---------------------------------------------------------------------------
# B.2 step 2 -- eq. (67)
# ---------------------------------------------------------------------------
def test_panel_residuals_are_weighted_mean_zero_each_quarter():
    """The eq. (67) TIME fixed effect forces this; it is what the main text's
    simple cross-sectional demeaning was standing in for."""
    rng = np.random.default_rng(2)
    idx = _periods(80)
    panel = pd.DataFrame({f"s{i}": rng.normal(0, 0.05, len(idx)) for i in range(6)}, index=idx)
    gdp = pd.Series(rng.normal(0.005, 0.01, len(idx)), index=idx)
    w = pseudo_equal_weights(panel)
    resid = panel_residuals(panel, gdp, w)
    weighted_mean = (resid * w).sum(axis=1)
    assert weighted_mean.abs().max() < 1e-8


def test_panel_residuals_remove_a_sector_specific_trend():
    """eq. (67) carries gamma_i * t, so a pure per-sector linear trend must be
    absorbed into the fit and leave essentially nothing in the residual."""
    idx = _periods(80)
    t = np.arange(len(idx), dtype=float)
    panel = pd.DataFrame(
        {"a": 0.001 * t, "b": -0.002 * t, "c": 0.0005 * t, "d": 0.0 * t}, index=idx
    )
    gdp = pd.Series(np.zeros(len(idx)), index=idx)
    w = pseudo_equal_weights(panel + 1e-9 * np.random.default_rng(3).normal(size=panel.shape))
    resid = panel_residuals(panel, gdp, w)
    assert np.abs(resid.to_numpy()).max() < 1e-8


# ---------------------------------------------------------------------------
# B.2 step 1 -- the corporate-sector exclusion
# ---------------------------------------------------------------------------
def test_corporate_sector_is_excluded_from_the_instrument():
    """B.2 step 1 verbatim: 'We exclude the corporate sector in constructing
    the instrument.'"""
    sectors = ["LM153064105.Q", CORPORATE_SECTOR_SERIES, "LM653064100.Q"]
    assert CORPORATE_SECTOR_SERIES not in instrument_sectors(sectors)
    assert len(instrument_sectors(sectors)) == 2


# ---------------------------------------------------------------------------
# B.2 step 4 -- eq. (68)
# ---------------------------------------------------------------------------
def test_giv_instrument_is_the_size_weighted_sum_of_residuals():
    idx = _periods(3)
    resid = pd.DataFrame({"a": [0.1, 0.2, -0.1], "b": [-0.1, 0.0, 0.3]}, index=idx)
    shares = pd.DataFrame({"a": [0.25, 0.5, 0.75], "b": [0.75, 0.5, 0.25]}, index=idx)
    z = giv_instrument(resid, shares)
    expected = [
        0.25 * 0.1 + 0.75 * -0.1,
        0.5 * 0.2 + 0.5 * 0.0,
        0.75 * -0.1 + 0.25 * 0.3,
    ]
    assert list(z.round(12)) == [round(e, 12) for e in expected]


def test_giv_instrument_renormalises_shares_to_sum_to_one():
    """Shares arrive normalised over ALL admitted sectors; dropping the
    corporate sector must renormalise, not leave them summing to <1."""
    idx = _periods(2)
    resid = pd.DataFrame({"a": [1.0, 1.0], "b": [1.0, 1.0]}, index=idx)
    shares = pd.DataFrame({"a": [0.2, 0.4], "b": [0.2, 0.4]}, index=idx)
    z = giv_instrument(resid, shares)
    # every residual is 1.0 and the weights renormalise to 1, so Z must be 1.0
    assert z.tolist() == pytest.approx([1.0, 1.0])


# ---------------------------------------------------------------------------
# THE KNOWN-ANSWER SYNTHETIC VALIDATION (CLAUDE.md requirement)
# ---------------------------------------------------------------------------
def _synthetic_market(seed: int, zeta: float, n_q: int = 400):
    """[GK21]'s own model as a data-generating process:

        dq_it = -zeta * dp_t + u_it                     (eq. 28)
        market clearing dq_St = 0  =>  dp_t = (1/zeta) * u_St

    Sector sizes are deliberately GRANULAR (one dominant sector) because
    [GK21] Section 4.1 requires it: "we need large idiosyncratic shocks, and a
    few large institutions, so that the market is 'granular'".
    """
    rng = np.random.default_rng(seed)
    n_sec = 8
    idx = _periods(n_q)
    shares_vec = np.array([0.45, 0.20, 0.12, 0.08, 0.06, 0.04, 0.03, 0.02])
    m_true = 1.0 / zeta
    u = rng.normal(0, 0.05, size=(n_q, n_sec))
    dp = m_true * (u @ shares_vec)
    dq = -zeta * dp[:, None] + u
    cols = [f"s{i}" for i in range(n_sec)]
    return (
        pd.DataFrame(dq, index=idx, columns=cols),
        pd.DataFrame(np.tile(shares_vec, (n_q, 1)), index=idx, columns=cols),
        pd.Series(np.zeros(n_q), index=idx),
        pd.Series(dp, index=idx),
        u,
        shares_vec,
        m_true,
    )


def _slope(z: pd.Series, dp: pd.Series) -> float:
    f = pd.concat([z.rename("z"), dp.rename("dp")], axis=1).dropna()
    d = np.column_stack([np.ones(len(f)), f["z"].to_numpy()])
    b, *_ = np.linalg.lstsq(d, f["dp"].to_numpy(), rcond=None)
    return float(b[1])


def test_pipeline_reproduces_the_closed_form_oracle_instrument():
    """THE known-answer validation required by CLAUDE.md.

    On the [GK21] DGP with no common factor, the eq. (67) residual is exactly
    u_it minus its E~-weighted cross-sectional mean, so eq. (68) reduces to the
    closed form

        Z_t = u_St - u_E~t

    which can be written down directly from the true shocks u. This asserts the
    whole B.2 pipeline reproduces that oracle -- a far sharper check than "the
    multiplier is roughly right", and the one that would have caught the
    original main-text implementation instantly (that version correlated far
    less than this with the oracle).

    The agreement is very close but NOT exact, and the tolerance below is the
    MEASURED gap rather than a number tuned until it passed: eq. (67) also fits
    sector fixed effects and sector-specific trends, which absorb a little more
    than the pure time-demeaning the closed form assumes. That residual
    difference is ~1% of the instrument's own standard deviation.
    """
    dq_df, shares_df, gdp, _dp, u, shares_vec, _ = _synthetic_market(20260908, 0.2)
    z_pipeline, _ = build_giv(dq_df, shares_df, gdp, n_pcs=1)
    w = pseudo_equal_weights(dq_df)
    oracle = pd.Series(
        (u @ shares_vec) - (u * w.to_numpy()[None, :]).sum(axis=1), index=dq_df.index
    )
    assert float(z_pipeline.corr(oracle)) > 0.999
    assert float((z_pipeline - oracle).std() / z_pipeline.std()) < 0.02


def test_estimated_multiplier_is_proportional_to_the_true_one():
    """The GIV slope must scale ONE-FOR-ONE with the true multiplier.

    MEASURED AND DISCLOSED, not assumed: on this synthetic size distribution
    the slope is a constant ~1.25x the true M, and an oracle instrument built
    from the true shocks gives the SAME 1.25x -- so the factor is a property of
    the estimator under this invented size distribution, NOT an implementation
    error. ([GK21] Appendix D.1 calibrates its simulated size distribution to
    the real one and reports the estimator recovers M accurately there; this
    test does not attempt to reproduce that calibration.)

    What must hold regardless, and is what this asserts, is PROPORTIONALITY:
    double the true multiplier and the estimate must double.
    """
    ratios = []
    for zeta in (0.5, 0.2, 0.125):  # M_true = 2, 5, 8
        dq_df, shares_df, gdp, dp, _, _, m_true = _synthetic_market(7, zeta)
        z, _ = build_giv(dq_df, shares_df, gdp, n_pcs=1)
        ratios.append(_slope(z, dp) / m_true)
    # every true multiplier must map to the SAME scale factor
    assert max(ratios) - min(ratios) < 0.02, f"scale factor is not constant: {ratios}"
    assert 1.0 < np.mean(ratios) < 1.5, f"unexpected scale factor {np.mean(ratios)}"


def test_the_scale_factor_is_not_an_implementation_artefact():
    """Guards the claim made in the docstring above: the closed-form oracle
    instrument produces the same slope as the pipeline, so no step of the B.2
    implementation is introducing the factor."""
    dq_df, shares_df, gdp, dp, u, shares_vec, _ = _synthetic_market(3, 0.2)
    z_pipeline, _ = build_giv(dq_df, shares_df, gdp, n_pcs=1)
    w = pseudo_equal_weights(dq_df)
    oracle = pd.Series(
        (u @ shares_vec) - (u * w.to_numpy()[None, :]).sum(axis=1), index=dq_df.index
    )
    assert _slope(z_pipeline, dp) == pytest.approx(_slope(oracle, dp), rel=0.02)


# ---------------------------------------------------------------------------
# the availability lag -- the whole no-look-ahead contract
# ---------------------------------------------------------------------------
def test_availability_lag_is_two_full_quarters():
    """Z.1 for quarter t is released 72 days after t ends, i.e. ~79% of the way
    into t+1, so the first fully tradable quarter is t+2."""
    assert AVAILABILITY_LAG_QUARTERS == 2


def test_position_cannot_use_a_signal_published_after_the_quarter_began():
    """Behavioural check: change ONLY the last quarter's signal and no earlier
    position may move; and the weight applied in quarter t must equal the rule
    evaluated on the signal from quarter t-2."""
    idx = _periods(60)
    rng = np.random.default_rng(11)
    z = pd.Series(rng.normal(0, 1, len(idx)), index=idx)
    mkt = pd.Series(rng.normal(0.01, 0.08, len(idx)), index=idx)

    base = replay_spec(z, mkt, "expanding", "binary", "1q", 0.0)
    bumped = z.copy()
    bumped.iloc[-1] += 100.0
    after = replay_spec(bumped, mkt, "expanding", "binary", "1q", 0.0)

    shared = base["weight"].index.intersection(after["weight"].index)
    assert (base["weight"].loc[shared] == after["weight"].loc[shared]).all()


def test_weight_in_quarter_t_equals_rule_applied_to_signal_at_t_minus_2():
    idx = _periods(60)
    rng = np.random.default_rng(12)
    z = pd.Series(rng.normal(0, 1, len(idx)), index=idx)
    mkt = pd.Series(rng.normal(0.01, 0.08, len(idx)), index=idx)
    out = replay_spec(z, mkt, "expanding", "binary", "1q", 0.0)
    expected = position_from_zscore(standardize(z, "expanding"), "binary").shift(2)
    for period, w in out["weight"].items():
        assert w == expected.loc[period]


# ---------------------------------------------------------------------------
# position rules and holding
# ---------------------------------------------------------------------------
def test_position_rules_stay_long_flat():
    idx = _periods(40)
    z = pd.Series(np.linspace(-3, 3, len(idx)), index=idx)
    for rule in ("binary", "linear_clip", "tertile"):
        w = position_from_zscore(z, rule).dropna()
        assert w.min() >= 0.0 and w.max() <= 1.0, rule


def test_two_quarter_holding_changes_at_most_every_other_quarter():
    idx = _periods(20)
    w = pd.Series([float(i % 2) for i in range(len(idx))], index=idx)
    held = apply_holding(w, "2q")
    changes = (held.diff().fillna(0) != 0).sum()
    assert changes <= len(idx) // 2


def test_one_quarter_holding_is_a_passthrough():
    idx = _periods(10)
    w = pd.Series(np.arange(10, dtype=float), index=idx)
    pd.testing.assert_series_equal(apply_holding(w, "1q"), w)


# ---------------------------------------------------------------------------
# grid and verdict
# ---------------------------------------------------------------------------
def test_the_grid_is_exactly_the_24_pre_registered_specs():
    grid = spec_grid()
    assert len(grid) == INELASTIC_N_TRIALS == 24
    assert len(set(grid)) == 24


def test_verdict_is_two_tier():
    assert verdict_from_dsr({24: 0.10, 37: 0.05, 362: 0.01, 1031: 0.001}) == "DEFINITE_NEGATIVE"
    assert verdict_from_dsr({24: 0.99, 37: 0.98, 362: 0.97, 1031: 0.96}) == "PASS"
    assert verdict_from_dsr({24: 0.99, 37: 0.98, 362: 0.60, 1031: 0.10}) == "UNRESOLVED"


def test_a_missing_dsr_at_the_lenient_rung_is_not_a_pass():
    assert verdict_from_dsr({24: None, 37: 0.99, 362: 0.99, 1031: 0.99}) == "DEFINITE_NEGATIVE"


def test_paper_table2_targets_are_recorded_verbatim():
    """Guards the citation constants against silent drift."""
    assert GK_TABLE2_MULTIPLIERS == {1: 7.08, 2: 5.28}


# ---------------------------------------------------------------------------
# costs
# ---------------------------------------------------------------------------
def test_costs_reduce_the_overlay_return():
    idx = _periods(60)
    rng = np.random.default_rng(13)
    z = pd.Series(rng.normal(0, 1, len(idx)), index=idx)
    mkt = pd.Series(rng.normal(0.01, 0.08, len(idx)), index=idx)
    free = replay_spec(z, mkt, "expanding", "binary", "1q", 0.0)
    costly = replay_spec(z, mkt, "expanding", "binary", "1q", 10.0)
    assert costly["overlay"].sum() < free["overlay"].sum()
    assert costly["cost_drag"] > free["cost_drag"] == 0.0
