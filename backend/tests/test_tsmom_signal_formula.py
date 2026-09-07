"""SYNTHETIC VALIDATION HARNESS for the TSMOM signal formula.

This is the gate CLAUDE.md requires before a published formula may be
trusted on real data: every case below has an analytically-known correct
answer, derived by hand in the test's own docstring, so the implementation
is checked against arithmetic rather than against itself.

NO REAL MARKET DATA APPEARS IN THIS FILE. Every series is constructed.

The cases, in the order the task framed them:
  * a pure deterministic uptrend must always signal LONG;
  * a pure deterministic downtrend must always signal SHORT;
  * a known constant-vol series must produce a position size matching the
    target-vol scaling exactly, computable by hand;
plus the properties that would silently break a real backtest: no lookahead
in the volatility estimate, exact reproduction of Eq. (1)'s weights on a
hand-computed short series, and scale invariance of the vol-targeted return.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.tsmom_signal import (
    MOP_ANNUALIZATION_DAYS,
    MOP_DELTA,
    MOP_HOLDING_MONTHS,
    MOP_LOOKBACK_MONTHS,
    MOP_VOLATILITY_CENTER_OF_MASS_DAYS,
    MOP_VOLATILITY_TARGET,
    diversified_tsmom_return,
    ex_ante_volatility,
    mop_delta_from_center_of_mass,
    position_size,
    trailing_return,
    tsmom_sign,
    tsmom_strategy_return,
)


def _monthly(values, start="2013-01-31") -> pd.Series:
    return pd.Series(
        list(values), index=pd.date_range(start, periods=len(values), freq="ME")
    )


def _daily(values, start="2013-01-02") -> pd.Series:
    return pd.Series(list(values), index=pd.bdate_range(start, periods=len(values)))


# ---------------------------------------------------------------------------
# CONSTANTS -- transcription check against the quoted source
# ---------------------------------------------------------------------------


def test_constants_match_the_paper_verbatim():
    """MOP 2012: 261 annualization (Eq. 1, p.233), 60-day center of mass
    (Eq. 1), 40% vol target (p.236), k=12/h=1 (p.236)."""
    assert MOP_ANNUALIZATION_DAYS == 261, "MOP say 261, not 252"
    assert MOP_VOLATILITY_CENTER_OF_MASS_DAYS == 60
    assert MOP_VOLATILITY_TARGET == 0.40
    assert MOP_LOOKBACK_MONTHS == 12
    assert MOP_HOLDING_MONTHS == 1


def test_delta_is_derived_from_the_center_of_mass_condition():
    """MOP Eq. (1): delta/(1-delta) = 60, so delta = 60/61.

    Checked in BOTH directions: the derived delta must reproduce the stated
    center of mass exactly."""
    assert MOP_DELTA == pytest.approx(60.0 / 61.0, rel=1e-15)
    assert MOP_DELTA == pytest.approx(0.9836065573770492, rel=1e-15)
    # invert: delta/(1-delta) must be 60
    assert MOP_DELTA / (1.0 - MOP_DELTA) == pytest.approx(60.0, rel=1e-12)


@pytest.mark.parametrize("com", [1.0, 10.0, 60.0, 252.0])
def test_center_of_mass_inversion_round_trips(com):
    delta = mop_delta_from_center_of_mass(com)
    assert delta / (1.0 - delta) == pytest.approx(com, rel=1e-12)


def test_center_of_mass_weights_really_have_that_center_of_mass():
    """Independently confirm the identity sum_i (1-d) d^i i = d/(1-d) by
    summing the series numerically -- so the closed form is checked against
    the weights it claims to describe, not just against itself."""
    delta = MOP_DELTA
    i = np.arange(0, 200_000)
    weights = (1.0 - delta) * delta**i
    assert weights.sum() == pytest.approx(1.0, abs=1e-9)
    assert (weights * i).sum() == pytest.approx(60.0, rel=1e-6)


# ---------------------------------------------------------------------------
# THE THREE HEADLINE CASES
# ---------------------------------------------------------------------------


def test_pure_deterministic_uptrend_always_signals_long():
    """A series that rises by the same amount every month has a strictly
    positive trailing 12-month return at every point where the lookback is
    defined, so sign() must be +1 everywhere. Hand-derived: with a constant
    monthly return of +1%, the trailing 12-month return is
    1.01^12 - 1 = +12.68% > 0 at every t."""
    returns = _monthly([0.01] * 40)
    signal = tsmom_sign(returns, MOP_LOOKBACK_MONTHS)

    defined = signal.dropna()
    assert len(defined) == 40 - MOP_LOOKBACK_MONTHS + 1
    assert (defined == 1.0).all()

    # and the trailing return itself matches the hand-derived value
    assert trailing_return(returns, 12).dropna().iloc[0] == pytest.approx(
        1.01**12 - 1.0, rel=1e-12
    )


def test_pure_deterministic_downtrend_always_signals_short():
    """Constant monthly return of -1%: trailing 12-month return is
    0.99^12 - 1 = -11.36% < 0 at every t, so sign() must be -1 everywhere."""
    returns = _monthly([-0.01] * 40)
    signal = tsmom_sign(returns, MOP_LOOKBACK_MONTHS)

    defined = signal.dropna()
    assert len(defined) == 40 - MOP_LOOKBACK_MONTHS + 1
    assert (defined == -1.0).all()

    assert trailing_return(returns, 12).dropna().iloc[0] == pytest.approx(
        0.99**12 - 1.0, rel=1e-12
    )


def test_known_constant_vol_series_produces_the_exact_target_scaling():
    """THE position-sizing case, computable by hand.

    Take a deterministic series that alternates +c, -c, +c, ... For a long
    enough run the exponentially weighted mean of a strictly alternating
    series tends to a tiny residual and the weighted mean of the SQUARES is
    exactly c^2 (every squared value is c^2, and the weights sum to one).
    So the weighted variance -> c^2 - (approximately 0)^2 = c^2, and

        sigma_annual = sqrt(261 * c^2) = c * sqrt(261)

    Choose c so that sigma_annual is exactly 20%:

        c = 0.20 / sqrt(261)

    Then the position size must be 40%/20% = 2.0 exactly.
    """
    target_vol = 0.20
    c = target_vol / np.sqrt(MOP_ANNUALIZATION_DAYS)
    returns = _daily([c if k % 2 == 0 else -c for k in range(4000)])

    vol = ex_ante_volatility(returns)
    measured = float(vol.iloc[-1])

    # The alternating mean residual is bounded by c*(1-delta)/(1+delta),
    # which for delta=60/61 is ~c/121 -- utterly negligible against c.
    assert measured == pytest.approx(target_vol, rel=1e-3)

    size = position_size(vol).iloc[-1]
    assert size == pytest.approx(MOP_VOLATILITY_TARGET / target_vol, rel=1e-3)
    assert size == pytest.approx(2.0, rel=1e-3)


@pytest.mark.parametrize(
    ("annual_vol", "expected_size"),
    [(0.10, 4.0), (0.20, 2.0), (0.40, 1.0), (0.80, 0.5)],
)
def test_position_size_is_exactly_target_over_sigma(annual_vol, expected_size):
    """40%/sigma, checked directly against hand arithmetic."""
    assert position_size(annual_vol) == pytest.approx(expected_size, rel=1e-15)


# ---------------------------------------------------------------------------
# Eq. (1) -- exact hand computation on a short series
# ---------------------------------------------------------------------------


def test_ex_ante_volatility_matches_a_fully_hand_computed_value():
    """Re-derive Eq. (1) by hand on a 4-observation series.

    Returns r = [0.01, -0.02, 0.03, 0.005]. sigma_t uses r_{t-1-i}, so at
    the LAST observation the inputs are the first three returns, most-recent
    first: [0.03, -0.02, 0.01].

    With adjust=True the finite-sample weights are proportional to
    d^0, d^1, d^2 (most recent first), normalized to sum to one:

        w_i = d^i / (1 + d + d^2)

    Then rbar = sum w_i r_i, E[r^2] = sum w_i r_i^2, variance = E[r^2] -
    rbar^2, and sigma = sqrt(261 * variance). Computed here with plain
    Python floats, independently of pandas' ewm machinery.
    """
    d = MOP_DELTA
    returns = _daily([0.01, -0.02, 0.03, 0.005])

    lagged_most_recent_first = [0.03, -0.02, 0.01]
    raw_weights = [d**0, d**1, d**2]
    total = sum(raw_weights)
    weights = [w / total for w in raw_weights]

    mean = sum(w * r for w, r in zip(weights, lagged_most_recent_first))
    mean_of_squares = sum(w * r * r for w, r in zip(weights, lagged_most_recent_first))
    variance = mean_of_squares - mean**2
    expected = np.sqrt(MOP_ANNUALIZATION_DAYS * variance)

    measured = ex_ante_volatility(returns).iloc[-1]
    assert measured == pytest.approx(expected, rel=1e-12)


def test_ex_ante_volatility_of_a_constant_series_is_exactly_zero():
    """A constant return has zero dispersion, so Eq. (1)'s weighted variance
    is exactly zero and sigma is exactly zero -- the cleanest analytic
    check that the MEAN is being subtracted. An implementation that dropped
    rbar_t and used E[r^2] alone would report sqrt(261)*0.01 = 16.2% here."""
    returns = _daily([0.01] * 500)
    vol = ex_ante_volatility(returns)
    assert float(vol.iloc[-1]) == pytest.approx(0.0, abs=1e-12)

    # prove the naive (mean-less) alternative really would have differed
    naive = np.sqrt(MOP_ANNUALIZATION_DAYS * 0.01**2)
    assert naive == pytest.approx(0.1616, abs=1e-3)


def test_position_size_is_nan_not_infinite_when_volatility_is_zero():
    returns = _daily([0.01] * 200)
    vol = ex_ante_volatility(returns)
    size = position_size(vol)
    assert np.isnan(size.iloc[-1])
    assert not np.isinf(size.dropna()).any()


# ---------------------------------------------------------------------------
# NO LOOKAHEAD -- the property whose failure is invisible but fatal
# ---------------------------------------------------------------------------


def test_ex_ante_volatility_does_not_use_the_current_return():
    """Eq. (1) sums over r_{t-1-i}. Changing ONLY the last return must leave
    every volatility value unchanged, including the last one -- if it moves,
    sigma_t is peeking at r_t."""
    base = list(np.random.default_rng(2).normal(0.0, 0.01, 300))
    original = ex_ante_volatility(_daily(base))

    perturbed_values = list(base)
    perturbed_values[-1] = 0.99  # an enormous shock in the final period
    perturbed = ex_ante_volatility(_daily(perturbed_values))

    pd.testing.assert_series_equal(original, perturbed, check_names=False)


def test_ex_ante_volatility_is_truncation_invariant():
    """A past sigma must not change when future data is appended."""
    rng = np.random.default_rng(9)
    full = _daily(rng.normal(0.0, 0.012, 600))
    truncated = ex_ante_volatility(full.iloc[:400])
    complete = ex_ante_volatility(full).iloc[:400]
    pd.testing.assert_series_equal(truncated, complete, check_names=False)


def test_first_volatility_values_are_nan_not_fabricated():
    returns = _daily([0.01, -0.01, 0.02, -0.02, 0.015])
    vol = ex_ante_volatility(returns, min_periods=2)
    # r_{t-1} only exists from the 2nd observation, and min_periods=2 needs
    # two lagged points, so the first two entries cannot be estimated.
    assert np.isnan(vol.iloc[0])
    assert np.isnan(vol.iloc[1])
    assert np.isfinite(vol.iloc[2])


def test_trailing_return_uses_only_the_trailing_window():
    """rolling(12) is inclusive of t and reaches back 11 periods; nothing
    after t may enter."""
    returns = _monthly([0.01] * 24)
    trailing = trailing_return(returns, 12)
    assert np.isnan(trailing.iloc[10])
    assert np.isfinite(trailing.iloc[11])

    perturbed = _monthly([0.01] * 24)
    perturbed.iloc[20] = 0.5
    assert trailing_return(perturbed, 12).iloc[11] == pytest.approx(
        trailing.iloc[11], rel=1e-15
    )


# ---------------------------------------------------------------------------
# SCALE INVARIANCE -- what volatility targeting is FOR
# ---------------------------------------------------------------------------


def test_vol_targeting_makes_the_strategy_return_scale_invariant():
    """If every return is multiplied by k, Eq. (1)'s sigma scales by k and
    the position size 40%/sigma scales by 1/k, so the product
    (size * return) is unchanged. A vol-targeted strategy must be
    indifferent to how volatile the underlying instrument is -- that is the
    entire point of the 40% scaling, and it is a strong analytic invariant
    that a subtly wrong annualization or a dropped mean would break.
    """
    rng = np.random.default_rng(123)
    base = _daily(rng.normal(0.0005, 0.01, 1500))

    for k in (0.5, 2.0, 10.0):
        scaled = base * k
        vol_base = ex_ante_volatility(base)
        vol_scaled = ex_ante_volatility(scaled)

        # sigma scales exactly linearly
        ratio = (vol_scaled / vol_base).dropna()
        assert np.allclose(ratio.to_numpy(), k, rtol=1e-10)

        # so the vol-targeted position return is identical
        pos_base = position_size(vol_base) * base
        pos_scaled = position_size(vol_scaled) * scaled
        pd.testing.assert_series_equal(
            pos_base.dropna(), pos_scaled.dropna(), check_names=False, rtol=1e-10
        )


def test_targeting_delivers_approximately_the_target_volatility():
    """On an iid series with constant true vol, the vol-targeted position's
    realized annualized volatility should land near the 40% target. Loose
    bounds -- this is a calibration sanity check, not an identity."""
    rng = np.random.default_rng(321)
    returns = _daily(rng.normal(0.0, 0.01, 8000))
    vol = ex_ante_volatility(returns)
    position_returns = (position_size(vol) * returns).dropna()

    realized_annual_vol = position_returns.std(ddof=1) * np.sqrt(MOP_ANNUALIZATION_DAYS)
    assert 0.30 < realized_annual_vol < 0.52


# ---------------------------------------------------------------------------
# Eq. (5) end to end, with hand-derived values
# ---------------------------------------------------------------------------


def test_equation_5_composes_exactly_as_written():
    """r^TSMOM = sign(trailing 12m) * (40%/sigma) * r_{t,t+1}, checked
    element by element against hand arithmetic on constructed inputs."""
    signal_returns = _monthly([0.01] * 20)  # uptrend -> sign +1
    realized = _monthly([0.02] * 20)
    vol = _monthly([0.20] * 20)  # -> size 2.0

    result = tsmom_strategy_return(signal_returns, realized, vol)
    defined = result.dropna()

    # +1 * (0.40/0.20) * 0.02 = 0.04
    assert (np.abs(defined - 0.04) < 1e-15).all()
    assert len(defined) == 20 - MOP_LOOKBACK_MONTHS + 1


def test_equation_5_goes_short_in_a_downtrend_and_profits_when_price_falls():
    """Downtrend -> sign -1. A further fall of -2% then yields
    (-1) * 2.0 * (-0.02) = +0.04."""
    signal_returns = _monthly([-0.01] * 20)
    realized = _monthly([-0.02] * 20)
    vol = _monthly([0.20] * 20)

    defined = tsmom_strategy_return(signal_returns, realized, vol).dropna()
    assert (np.abs(defined - 0.04) < 1e-15).all()


def test_a_flat_trailing_return_takes_no_position():
    """sign(0) == 0. MOP give no tie-break, so a flat lookback must produce
    a zero position rather than a silently-long one."""
    signal_returns = _monthly([0.0] * 20)
    realized = _monthly([0.05] * 20)
    vol = _monthly([0.20] * 20)

    defined = tsmom_strategy_return(signal_returns, realized, vol).dropna()
    assert (defined == 0.0).all()


def test_diversified_return_is_the_equal_weighted_average_of_available_names():
    """MOP p.236: (1/S_t) sum over "the St securities that are available at
    time t" -- so an unavailable instrument reduces S_t rather than
    contributing a zero."""
    frame = pd.DataFrame(
        {
            "a": [0.10, 0.10, 0.10],
            "b": [0.20, 0.20, np.nan],
            "c": [np.nan, 0.30, np.nan],
        },
        index=pd.date_range("2013-01-31", periods=3, freq="ME"),
    )
    result = diversified_tsmom_return(frame)
    assert result.iloc[0] == pytest.approx(0.15)  # (0.10+0.20)/2
    assert result.iloc[1] == pytest.approx(0.20)  # (0.10+0.20+0.30)/3
    assert result.iloc[2] == pytest.approx(0.10)  # only 'a' available


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_ex_ante_volatility_rejects_a_bad_delta():
    returns = _daily([0.01, 0.02, 0.03])
    for bad in (0.0, 1.0, -0.5, 1.5):
        with pytest.raises(ValueError):
            ex_ante_volatility(returns, delta=bad)


def test_ex_ante_volatility_rejects_non_series():
    with pytest.raises(TypeError):
        ex_ante_volatility([0.01, 0.02])  # type: ignore[arg-type]


def test_trailing_return_rejects_a_non_positive_lookback():
    with pytest.raises(ValueError):
        trailing_return(_monthly([0.01] * 5), 0)


def test_center_of_mass_rejects_non_positive_input():
    with pytest.raises(ValueError):
        mop_delta_from_center_of_mass(0.0)
