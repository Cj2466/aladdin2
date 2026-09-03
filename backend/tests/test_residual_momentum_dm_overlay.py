"""Tests for the Daniel-Moskowitz crash-mitigation overlay.

The load-bearing ones are named for what they would catch rather than for what
they call: an indicator that has drifted off the paper's definition, a
look-ahead in the weight, a warmup that does not actually hold the base, and a
Sharpe that could be moved by choosing a leverage level.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.market_data.fama_french_provider import load_fama_french_monthly
from app.services.research_lab.cross_sectional_residual_momentum_dm_overlay import (
    DM_BASE_SPECS,
    DM_OVERLAY_ARMS,
    DM_OVERLAY_N_NEW_SPECS,
    DM_OVERLAY_N_TRIALS,
    DM_OVERLAY_PRIOR_TRIALS,
    DM_REGISTRABLE_SPEC_IDS,
    _expanding_mean_forecast,
    apply_overlay,
    bear_market_indicator,
    build_dm_overlay_grid,
    build_overlay,
    month_end_positions,
    monthly_overlay_weights,
    normalization_constant,
    overlay_pattern_id,
    trailing_annualized_variance,
)
from app.services.research_lab.metrics import sharpe_ratio


def _daily_index(n: int, start: str = "2015-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _series(n: int, seed: int = 0, scale: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0.0002, scale, n), index=_daily_index(n))


def _market_inputs(index: pd.DatetimeIndex, seed: int = 7, *, with_bear: bool = False):
    """A monthly market series long enough to form the 24-month indicator
    before the strategy's own history starts, plus a daily market series on the
    strategy's own index.

    `with_bear=True` plants a real bear stretch — a run of monthly losses deep
    enough to turn the trailing 24-month cumulative return negative — because
    the `dyn` arm's interaction coefficient is UNIDENTIFIABLE without one, and
    a test that never triggers a bear month would exercise only the refusal
    path."""
    months = pd.date_range(end=index[-1], periods=200, freq="ME")
    rng = np.random.default_rng(seed)
    values = rng.normal(0.007, 0.04, len(months))
    if with_bear:
        # A drawdown placed EARLY in the strategy's own window and deep enough
        # that the trailing 24-month cumulative return stays negative for a
        # stretch of months. It has to land inside the strategy's window and
        # early within it, because the expanding regression needs at least 36
        # (return, lagged-state) pairs of which at least one carries IB = 1.
        values[-58:-44] = -0.06
    monthly = pd.Series(values, index=months)
    daily = pd.Series(rng.normal(0.0004, 0.01, len(index)), index=index)
    return monthly, daily


# --- the indicator IS the paper's ------------------------------------------


def test_bear_indicator_reproduces_daniel_moskowitz_own_footnote_count():
    """THE test that this module implements D&M's indicator and not something
    that merely resembles it.

    Daniel & Moskowitz (JFE 122(2), 2016) footnote 6, p. 228: "Of the 1,035
    months in the 1927:01-2013:03 period, IB,t-1 = 1 in 183". Their IB is one
    when the cumulative CRSP VW index return over the past 24 months is
    negative, and Ken French's market factor IS that index return (mkt_rf + rf),
    so running this module's indicator over exactly their window must return
    exactly their two numbers.

    If someone later "improves" the indicator — an excess return instead of a
    total one, a 12- or 36-month window, a drawdown instead of a cumulative
    return, a <= instead of a < — this test fails and says so. Nothing else in
    the suite would notice."""
    factors = load_fama_french_monthly()
    market = factors.frame["mkt_rf"] + factors.frame["rf"]
    indicator = bear_market_indicator(market)
    window = indicator[
        (indicator.index >= pd.Timestamp("1927-01-01"))
        & (indicator.index <= pd.Timestamp("2013-03-31"))
    ]
    assert len(window) == 1035, f"D&M report 1,035 months in 1927:01-2013:03, got {len(window)}"
    assert int(window.sum()) == 183, f"D&M report IB=1 in 183 of them, got {int(window.sum())}"


def test_bear_indicator_is_the_sign_of_the_trailing_cumulative_return():
    months = pd.date_range("2000-01-31", periods=30, freq="ME")
    # A 24-month run of -1% then a run of +5%: the trailing window is negative
    # while losses dominate it and turns positive once enough gains enter.
    values = [-0.01] * 24 + [0.05] * 6
    indicator = bear_market_indicator(pd.Series(values, index=months))
    assert indicator.iloc[:23].isna().all(), "an incomplete 24-month window must be NaN"
    assert indicator.iloc[23] == 1.0
    assert indicator.iloc[-1] == 0.0


def test_bear_indicator_uses_a_strict_inequality_at_zero():
    months = pd.date_range("2000-01-31", periods=24, freq="ME")
    flat = bear_market_indicator(pd.Series([0.0] * 24, index=months))
    assert flat.iloc[-1] == 0.0, "a cumulative return of exactly zero is NOT a bear market"


def test_bear_indicator_refuses_a_nonsense_lookback():
    with pytest.raises(ValueError, match="must be >= 1"):
        bear_market_indicator(pd.Series(dtype=float), lookback_months=0)


# --- the level of the weight cannot buy anything ----------------------------


def test_sharpe_is_exactly_invariant_to_the_weight_level():
    """The module docstring's central honesty claim, pinned rather than
    asserted: leverage LEVEL — D&M's lambda, the volatility target, the k
    normalization — cannot move any Sharpe this module reports. Everything a
    Sharpe here says comes from the TIME VARIATION of the weight."""
    base = _series(600, seed=3)
    weights = pd.Series(np.linspace(0.4, 2.0, len(base)), index=base.index)
    plain, _gross, _cost = apply_overlay(base, weights, cost_bps=0.0)
    scaled, _g, _c = apply_overlay(base, weights * 7.5, cost_bps=0.0, initial_weight=7.5)
    assert sharpe_ratio(scaled) == pytest.approx(sharpe_ratio(plain), abs=1e-12)


def test_normalization_constant_matches_the_base_volatility():
    base = _series(800, seed=11)
    weights = pd.Series(np.linspace(0.2, 3.0, len(base)), index=base.index)
    k = normalization_constant(base, weights)
    assert float((k * weights * base).std(ddof=1)) == pytest.approx(
        float(base.std(ddof=1)), rel=1e-12
    )


# --- no look-ahead ----------------------------------------------------------


def test_a_months_weight_cannot_depend_on_that_months_own_returns():
    """The one bug in this module that would produce a better-looking result
    while remaining completely invisible in the output.

    Rewriting the base's returns for one month must leave that month's own
    weight — and every earlier month's — untouched. Only LATER months may
    react, because the weight for month m+1 is allowed to read month m."""
    base = _series(900, seed=5)
    market_monthly, market_daily = _market_inputs(base.index)
    perturbed = base.copy()
    target = pd.Timestamp("2017-06-01")
    mask = (perturbed.index.year == target.year) & (perturbed.index.month == target.month)
    perturbed[mask] = perturbed[mask] * 10.0 + 0.05

    for arm in DM_OVERLAY_ARMS:
        original, _ = monthly_overlay_weights(
            arm, base, market_monthly_returns=market_monthly, market_daily_returns=market_daily
        )
        moved, _ = monthly_overlay_weights(
            arm, perturbed, market_monthly_returns=market_monthly, market_daily_returns=market_daily
        )
        upto = original.index <= original.index[mask][-1]
        assert np.allclose(
            original[upto].to_numpy(), moved[upto].to_numpy(), equal_nan=True
        ), f"arm {arm!r} let a month's own returns leak into its own weight"


def test_extra_lag_cannot_be_negative():
    base = _series(400, seed=6)
    market_monthly, market_daily = _market_inputs(base.index)
    with pytest.raises(ValueError, match="look-ahead"):
        monthly_overlay_weights(
            "cvol",
            base,
            market_monthly_returns=market_monthly,
            market_daily_returns=market_daily,
            extra_lag_months=-1,
        )


def test_expanding_forecast_regresses_on_the_lagged_regressor():
    """D&M's Eq. (4) pairs month t's return with the state at t-1. An earlier
    draft of this module paired them contemporaneously, which silently
    estimated a co-movement coefficient and used it as a forecasting one.

    Built so the two specifications cannot agree: y is an exact linear function
    of the PREVIOUS month's x, so the lagged regression recovers the true
    coefficients and a contemporaneous one cannot."""
    months = pd.date_range("2000-01-31", periods=90, freq="ME")
    rng = np.random.default_rng(2)
    x = pd.Series(rng.uniform(0.0, 1.0, len(months)), index=months)
    y = pd.Series(np.nan, index=months)
    y.iloc[1:] = 0.004 - 0.05 * x.to_numpy()[:-1]

    forecast, n_unidentified = _expanding_mean_forecast(y, x, min_months=36)
    assert n_unidentified > 0, "the first months cannot be identified and must say so"
    last = forecast.dropna().iloc[-1]
    assert last == pytest.approx(0.004 - 0.05 * x.iloc[-1], abs=1e-9)


def test_expanding_forecast_refuses_rather_than_falling_back_to_an_intercept():
    """With no bear month ever, g_int is unidentified. Returning an
    intercept-only forecast would turn `dyn` silently into `vscale` while still
    being reported as the paper's dynamic strategy."""
    months = pd.date_range("2000-01-31", periods=80, freq="ME")
    y = pd.Series(np.linspace(-0.01, 0.01, len(months)), index=months)
    x = pd.Series(0.0, index=months)  # IB never fires, so IB * sigma^2 is constant
    forecast, n_unidentified = _expanding_mean_forecast(y, x, min_months=36)
    assert forecast.isna().all()
    assert n_unidentified == len(months)


# --- warmup really holds the base -------------------------------------------


def test_warmup_holds_the_base_exactly_and_not_k_times_the_base():
    """The bug this test exists for: k is applied to the weight, so filling
    warmup months with 1.0 BEFORE normalizing leaves them at k — about 0.03 for
    the `vscale` arm, i.e. very nearly flat rather than "the base". The warmup
    lands on the sample's first months, so that silently deletes whatever
    happened there."""
    base = _series(400, seed=9)  # well under the 126-day window + a month
    market_monthly, market_daily = _market_inputs(base.index)
    overlay = build_overlay(
        "ff3", "rm_ff3_residual_ls_h21", "vscale", base,
        market_monthly_returns=market_monthly, market_daily_returns=market_daily, cost_bps=5.0,
    )
    warmup_months = overlay.diagnostics.n_warmup_months
    assert warmup_months >= 1
    first_month = overlay.weights.index.to_period("M") == overlay.weights.index[0].to_period("M")
    assert np.allclose(overlay.weights[first_month].to_numpy(), 1.0), (
        "warmup must hold the base at exactly 1.0, not at the normalization constant"
    )


def test_overlay_shares_the_bases_day_set_exactly():
    # Long enough that the `dyn` arm's 36-month regression floor can be met
    # inside the strategy's own window; ~1,500 business days is about 69 months.
    base = _series(1500, seed=13)
    market_monthly, market_daily = _market_inputs(base.index, with_bear=True)
    for arm in DM_OVERLAY_ARMS:
        overlay = build_overlay(
            "ff3", "rm_ff3_residual_ls_h21", arm, base,
            market_monthly_returns=market_monthly, market_daily_returns=market_daily, cost_bps=5.0,
        )
        assert overlay.returns.index.equals(base.index)
        assert overlay.weights.notna().all(), "no weight may be left undefined"
        if arm == "dyn":
            assert overlay.diagnostics.n_unidentified_months < overlay.diagnostics.n_months, (
                "this fixture must actually exercise dyn, not just its refusal path"
            )


def test_dyn_refuses_loudly_when_no_month_is_ever_identified():
    """A `dyn` arm whose regression is never identified over the WHOLE sample
    is not "the dynamic strategy that happened to sit at weight 1" — it is the
    un-overlaid base wearing D&M's citation. Returning it silently is the one
    way this module could report a result that is not the strategy it names,
    so it raises instead."""
    base = _series(1500, seed=13)
    months = pd.date_range(end=base.index[-1], periods=200, freq="ME")
    # A market that never has a losing two-year stretch, so IB is never 1.
    market_monthly = pd.Series(0.01, index=months)
    market_daily = pd.Series(0.0004, index=base.index)
    assert float(bear_market_indicator(market_monthly).fillna(0.0).sum()) == 0.0
    with pytest.raises(ValueError, match="no active weights"):
        build_overlay(
            "ff3", "rm_ff3_residual_ls_h21", "dyn", base,
            market_monthly_returns=market_monthly, market_daily_returns=market_daily, cost_bps=5.0,
        )


# --- the overlay's own cost is charged --------------------------------------


def test_apply_overlay_charges_every_leverage_change_on_both_legs():
    index = _daily_index(4)
    base = pd.Series([0.0, 0.0, 0.0, 0.0], index=index)
    weights = pd.Series([1.0, 1.0, 1.5, 1.5], index=index)
    net, gross, total = apply_overlay(base, weights, cost_bps=5.0)
    # One 0.5 leverage change, on 2.0 of gross notional per unit, at 5 bps.
    expected = 0.5 * 2.0 * 5.0 / 10_000.0
    assert total == pytest.approx(expected)
    assert net.iloc[2] == pytest.approx(-expected)
    assert gross.abs().sum() == 0.0


def test_apply_overlay_refuses_a_mismatched_index():
    base = _series(20, seed=1)
    with pytest.raises(ValueError, match="index exactly"):
        apply_overlay(base, base.iloc[:-1], cost_bps=5.0)


# --- the grid and its denominator -------------------------------------------


def test_grid_is_twelve_cells_under_a_thirty_trial_denominator():
    cells = build_dm_overlay_grid()
    assert len(cells) == DM_OVERLAY_N_NEW_SPECS == 12
    assert DM_OVERLAY_PRIOR_TRIALS == 18
    assert DM_OVERLAY_N_TRIALS == 30
    assert len({overlay_pattern_id(b, a) for b, _p, a in cells}) == 12


def test_registrable_set_excludes_every_pre_declined_combination():
    """Pre-registration section 7, pinned so it cannot quietly widen after the
    numbers are in: only the BHM-faithful base paired with a fully-powered
    volatility arm may be proposed. The industry-neutral base was declined in
    dd288f9; the total-return base is BHM's comparison baseline; the two
    bear-conditioned arms fire on 8 of 138 months."""
    assert DM_REGISTRABLE_SPEC_IDS == {"dm_ff3_cvol_h21", "dm_ff3_vscale_h21"}
    for base_key, _pattern_id, arm in build_dm_overlay_grid():
        eligible = overlay_pattern_id(base_key, arm) in DM_REGISTRABLE_SPEC_IDS
        assert eligible == (base_key == "ff3" and arm in {"cvol", "vscale"})


def test_base_specs_are_all_h21():
    assert all(pattern_id.endswith("_h21") for _key, pattern_id in DM_BASE_SPECS)


# --- small helpers ----------------------------------------------------------


def test_month_end_positions_picks_the_last_trading_day_of_each_month():
    index = _daily_index(70)
    positions = month_end_positions(index)
    for p in positions:
        day = index[p]
        later = index[(index > day) & (index.to_period("M") == day.to_period("M"))]
        assert len(later) == 0


def test_trailing_variance_is_nan_until_the_window_is_full():
    series = _series(200, seed=4)
    variance = trailing_annualized_variance(series, window_days=126)
    assert variance.iloc[:125].isna().all()
    assert np.isfinite(variance.iloc[125])
    expected = float(series.iloc[:126].var(ddof=1)) * 252.0
    assert variance.iloc[125] == pytest.approx(expected)


def test_bear_arm_treats_an_unformed_indicator_as_unknown_not_as_calm():
    """A NaN indicator must not become "not a bear market". The warmup rule
    then holds the base, which is a disclosed no-op; silently reading NaN as
    calm would instead be an undisclosed all-clear."""
    base = _series(700, seed=17)
    months = pd.date_range(end=base.index[-1], periods=6, freq="ME")  # far too few
    market_monthly = pd.Series(0.01, index=months)
    market_daily = pd.Series(0.0004, index=base.index)
    _weights, diagnostics = monthly_overlay_weights(
        "bear", base, market_monthly_returns=market_monthly, market_daily_returns=market_daily
    )
    assert diagnostics.n_bear_months == 0
    assert diagnostics.n_warmup_months == diagnostics.n_months
