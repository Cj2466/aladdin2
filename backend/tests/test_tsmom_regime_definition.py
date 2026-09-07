"""Tests for the PRE-REGISTERED TSMOM regime definition.

These are deliberately heavy on the no-lookahead property, because that is
the one property whose failure would silently invalidate the whole
pre-registration while every number still looked plausible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.tsmom_regime_definition import (
    MIN_PRIOR_QUARTERS,
    MOP_EXTREME_TAIL_FRACTION,
    PRIMARY_RULE,
    SECONDARY_DRAWDOWN_THRESHOLD,
    assert_not_used_as_a_timing_signal,
    classify_drawdown_regime,
    classify_extreme_market_quarters,
    quarterly_price_returns,
    trailing_drawdown,
)


def _daily_index(n: int, start: str = "2000-01-03") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _prices_from_daily_returns(returns: np.ndarray, start: str = "2000-01-03") -> pd.Series:
    prices = 100.0 * np.cumprod(1.0 + returns)
    return pd.Series(prices, index=_daily_index(len(returns), start))


# ---------------------------------------------------------------------------
# Pre-declared constants must not drift
# ---------------------------------------------------------------------------


def test_pre_declared_constants_match_their_cited_sources():
    """MOP 2012 p.240's own convention is the top 20%; the burn-in and the
    secondary drawdown threshold are the values pre-registered on
    2026-09-07. A change here is a change to the pre-registration and must
    fail loudly."""
    assert MOP_EXTREME_TAIL_FRACTION == 0.20
    assert MIN_PRIOR_QUARTERS == 40
    assert SECONDARY_DRAWDOWN_THRESHOLD == 0.20
    assert PRIMARY_RULE == "mop_extreme_absolute_quarterly_market_return"


# ---------------------------------------------------------------------------
# quarterly_price_returns
# ---------------------------------------------------------------------------


def test_quarterly_returns_are_non_overlapping_and_hand_checkable():
    """A price series that is exactly 100 on every quarter end except one
    gives a return that can be derived by hand."""
    dates = pd.to_datetime(
        ["2020-01-02", "2020-03-31", "2020-06-30", "2020-09-30", "2020-12-31"]
    )
    prices = pd.Series([100.0, 100.0, 110.0, 110.0, 99.0], index=dates)
    returns = quarterly_price_returns(prices)

    # Q1 has no prior quarter-end to measure from, so pct_change drops it.
    assert len(returns) == 3
    assert returns.loc["2020-06-30"] == pytest.approx(0.10)
    assert returns.loc["2020-09-30"] == pytest.approx(0.0)
    assert returns.loc["2020-12-31"] == pytest.approx(99.0 / 110.0 - 1.0)


def test_quarterly_returns_use_last_observed_price_not_calendar_last_day():
    """2020-12-31 was a trading day but 2021-01-01 was not; a series whose
    final December print is the 30th must still anchor on the 30th."""
    dates = pd.to_datetime(["2020-09-30", "2020-12-30"])
    prices = pd.Series([100.0, 120.0], index=dates)
    returns = quarterly_price_returns(prices)
    assert len(returns) == 1
    assert returns.iloc[0] == pytest.approx(0.20)


def test_quarterly_returns_handles_too_short_input():
    assert quarterly_price_returns(pd.Series(dtype=float)).empty
    single = pd.Series([100.0], index=pd.to_datetime(["2020-01-02"]))
    assert quarterly_price_returns(single).empty


def test_quarterly_returns_rejects_non_series():
    with pytest.raises(TypeError):
        quarterly_price_returns([100.0, 101.0])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The primary rule: burn-in, tail fraction, and NO LOOKAHEAD
# ---------------------------------------------------------------------------


def test_burn_in_emits_unclassified_and_never_silently_calls_them_normal():
    """Quarters inside the burn-in must be UNCLASSIFIED, not dumped into the
    out-of-regime bucket -- otherwise the normal bucket would be
    contaminated by periods the rule never actually judged."""
    rng = np.random.default_rng(0)
    prices = _prices_from_daily_returns(rng.normal(0.0003, 0.01, 4000))
    result = classify_extreme_market_quarters(prices)

    labelled = result.labels
    assert (labelled.iloc[:MIN_PRIOR_QUARTERS] == "unclassified").all()
    assert (labelled.iloc[MIN_PRIOR_QUARTERS:] != "unclassified").all()
    assert result.n_unclassified == MIN_PRIOR_QUARTERS
    # thresholds are NaN exactly where unclassified
    assert result.thresholds.iloc[:MIN_PRIOR_QUARTERS].isna().all()
    assert result.thresholds.iloc[MIN_PRIOR_QUARTERS:].notna().all()


def test_n_prior_counts_are_strictly_prior():
    rng = np.random.default_rng(1)
    prices = _prices_from_daily_returns(rng.normal(0.0, 0.01, 4000))
    result = classify_extreme_market_quarters(prices)
    assert list(result.n_prior) == list(range(len(result.n_prior)))


def test_no_lookahead_truncating_the_future_cannot_change_a_past_label():
    """THE decisive property. Classify the full history, then re-classify
    progressively truncated histories. Every label that both runs share must
    be identical -- if a future observation could change a past label, the
    rule leaks the future and the pre-registration is worthless."""
    rng = np.random.default_rng(7)
    daily = rng.normal(0.0002, 0.011, 6000)
    # inject a violent late crash so a full-sample percentile would differ
    # sharply from the expanding one
    daily[5200:5230] = -0.05
    full_prices = _prices_from_daily_returns(daily)
    full = classify_extreme_market_quarters(full_prices)

    for cut in (3000, 4000, 5000, 5500):
        truncated = classify_extreme_market_quarters(full_prices.iloc[:cut])
        shared = truncated.labels.index.intersection(full.labels.index)
        # drop the final shared quarter: a truncation mid-quarter changes
        # that quarter's own realized return, which is a different input,
        # not a leak.
        shared = shared[:-1]
        assert len(shared) > MIN_PRIOR_QUARTERS
        pd.testing.assert_series_equal(
            truncated.labels.loc[shared],
            full.labels.loc[shared],
            check_names=False,
        )


def test_full_sample_percentile_would_have_leaked_so_the_test_above_has_teeth():
    """Guards the guard: confirm the expanding threshold actually differs
    from a full-sample threshold on this data, so the no-lookahead test is
    not passing vacuously."""
    rng = np.random.default_rng(7)
    daily = rng.normal(0.0002, 0.011, 6000)
    daily[5200:5230] = -0.05
    prices = _prices_from_daily_returns(daily)
    result = classify_extreme_market_quarters(prices)

    magnitudes = result.period_returns.abs()
    full_sample_cutoff = float(np.quantile(magnitudes.to_numpy(), 0.80))
    first_real = result.thresholds.dropna().iloc[0]
    assert first_real != pytest.approx(full_sample_cutoff)


def test_rule_is_two_sided_a_large_up_quarter_is_extreme_too():
    """MOP's claim is about large UP and DOWN moves. A big rally must be
    flagged, or the rule is silently testing the one-sided crisis claim
    instead of the paper's actual claim."""
    rng = np.random.default_rng(3)
    daily = list(rng.normal(0.0, 0.004, 4000))
    prices = _prices_from_daily_returns(np.array(daily))
    # append one explosive up quarter
    boom = pd.Series(
        prices.iloc[-1] * np.cumprod(1.0 + np.full(64, 0.01)),
        index=pd.bdate_range(start=prices.index[-1] + pd.Timedelta(days=1), periods=64),
    )
    extended = pd.concat([prices, boom])
    result = classify_extreme_market_quarters(extended)

    tail_labels = result.labels.iloc[-2:]
    assert (tail_labels == "extreme").any(), "a >80% up quarter must classify as extreme"


def test_extreme_fraction_is_approximately_the_declared_tail_on_iid_data():
    """On stationary iid data an expanding 80th-percentile rule should flag
    roughly 20% of classified quarters. Loose bounds: the expanding window
    is noisy early on, and this is a sanity check, not a calibration."""
    rng = np.random.default_rng(11)
    prices = _prices_from_daily_returns(rng.normal(0.0, 0.01, 12000))
    result = classify_extreme_market_quarters(prices)
    classified = result.n_in_regime + result.n_out_of_regime
    assert classified > 100
    share = result.n_in_regime / classified
    assert 0.10 < share < 0.32


def test_threshold_is_recomputed_each_quarter_and_can_be_rederived_by_hand():
    """Re-derive one threshold from primitives with numpy, independently of
    the implementation's own loop."""
    rng = np.random.default_rng(5)
    prices = _prices_from_daily_returns(rng.normal(0.0, 0.01, 5000))
    result = classify_extreme_market_quarters(prices)

    probe = MIN_PRIOR_QUARTERS + 5
    prior_magnitudes = result.period_returns.abs().iloc[:probe].to_numpy()
    expected = float(np.quantile(prior_magnitudes, 0.80))
    assert result.thresholds.iloc[probe] == pytest.approx(expected)

    expected_label = (
        "extreme" if abs(result.period_returns.iloc[probe]) >= expected else "normal"
    )
    assert result.labels.iloc[probe] == expected_label


def test_empty_input_returns_empty_classification():
    result = classify_extreme_market_quarters(pd.Series(dtype=float))
    assert result.labels.empty
    assert result.n_in_regime == 0
    assert result.n_out_of_regime == 0


# ---------------------------------------------------------------------------
# Secondary drawdown rule
# ---------------------------------------------------------------------------


def test_trailing_drawdown_is_hand_checkable_and_causal():
    dates = _daily_index(5)
    prices = pd.Series([100.0, 120.0, 90.0, 96.0, 150.0], index=dates)
    dd = trailing_drawdown(prices)
    assert dd.iloc[0] == pytest.approx(0.0)
    assert dd.iloc[1] == pytest.approx(0.0)
    assert dd.iloc[2] == pytest.approx(1 - 90.0 / 120.0)  # 25%
    assert dd.iloc[3] == pytest.approx(1 - 96.0 / 120.0)  # 20%
    assert dd.iloc[4] == pytest.approx(0.0)  # new high


def test_drawdown_rule_flags_at_and_below_the_threshold():
    dates = _daily_index(4)
    prices = pd.Series([100.0, 100.0, 80.0, 81.0], index=dates)
    result = classify_drawdown_regime(prices)
    assert list(result.labels) == ["normal", "normal", "extreme", "normal"]


def test_drawdown_rule_is_exact_at_its_own_boundary():
    """Regression test for a real float defect found 2026-09-07: testing
    (1 - price/peak) >= 0.20 misses an exact 20% drawdown because
    1 - 80/100 == 0.19999999999999996 in double precision. The rule must
    trigger AT its stated threshold, not epsilon past it."""
    dates = _daily_index(2)
    exactly_twenty = pd.Series([100.0, 80.0], index=dates)
    assert list(classify_drawdown_regime(exactly_twenty).labels)[-1] == "extreme"

    # and the naive formulation really would have failed -- guards the guard
    assert (1.0 - 80.0 / 100.0) < SECONDARY_DRAWDOWN_THRESHOLD

    just_inside = pd.Series([100.0, 80.5], index=dates)
    assert list(classify_drawdown_regime(just_inside).labels)[-1] == "normal"


def test_drawdown_rule_is_causal_under_truncation():
    rng = np.random.default_rng(13)
    prices = _prices_from_daily_returns(rng.normal(0.0, 0.012, 3000))
    full = classify_drawdown_regime(prices)
    truncated = classify_drawdown_regime(prices.iloc[:1500])
    pd.testing.assert_series_equal(
        truncated.labels, full.labels.iloc[:1500], check_names=False
    )


def test_drawdown_rule_emits_no_unclassified_labels():
    rng = np.random.default_rng(17)
    prices = _prices_from_daily_returns(rng.normal(0.0, 0.01, 800))
    result = classify_drawdown_regime(prices)
    assert result.n_unclassified == 0


def test_secondary_rule_is_labelled_as_non_mop():
    rng = np.random.default_rng(19)
    prices = _prices_from_daily_returns(rng.normal(0.0, 0.01, 500))
    assert "non_mop" in classify_drawdown_regime(prices).rule_name


# ---------------------------------------------------------------------------
# The anti-misuse guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "purpose",
    ["timing overlay", "position sizing", "a filter on returns", "regime GATE"],
)
def test_guard_rejects_lookahead_purposes(purpose):
    with pytest.raises(ValueError, match="CONTEMPORANEOUS"):
        assert_not_used_as_a_timing_signal(purpose)


@pytest.mark.parametrize(
    "purpose",
    ["split DSR reporting", "partition realized returns", "descriptive disclosure"],
)
def test_guard_allows_legitimate_purposes(purpose):
    assert assert_not_used_as_a_timing_signal(purpose) is None
