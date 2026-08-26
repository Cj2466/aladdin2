"""Build D1's harness-level additions to cross_sectional.py: pluggable
CrossSectionalSpec.leg_weighting ("magnitude" vs "value"), _apply_weight_cap
(factored out of _leg_weights so both weighting schemes share the identical
MAX_WEIGHT_MULTIPLE cap), _resolve_leg_weights (the dispatcher, including its
market-cap-unusable fallback to the original magnitude scheme), and the
FormationRecord / CrossSectionalScreeningResult fallback-accounting fields.

Deliberately a SEPARATE file from test_cross_sectional.py (which already
covers _leg_weights, run_cross_sectional_backtest, and
screen_cross_sectional_universe's pre-existing magnitude-only behavior in
full — untouched and unaffected by this build, per
cross_sectional.CrossSectionalSpec.leg_weighting's own default) rather than
appended to it, purely to avoid touching a file under concurrent edit by
another build in this same worktree tonight; there is no dependency either
way and this file imports only from cross_sectional.py itself."""

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    MAX_WEIGHT_MULTIPLE,
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    _apply_weight_cap,
    _leg_weights,
    _resolve_leg_weights,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
)

ALWAYS_MEMBER = lambda _ticker, _on: True


def _close_frame(returns_by_ticker: dict[str, float], start: str, n_days: int) -> pd.DataFrame:
    index = pd.bdate_range(start, periods=n_days)
    data = {
        ticker: 100.0 * np.cumprod(np.full(n_days, 1.0 + r)) for ticker, r in returns_by_ticker.items()
    }
    return pd.DataFrame(data, index=index)


def _const_frame(value_by_ticker_and_date, index, columns) -> pd.DataFrame:
    return pd.DataFrame(value_by_ticker_and_date, index=index, columns=columns)


def _last_close_signal(view: CrossSectionalData) -> pd.Series:
    return view.close.iloc[-1]


def _spec(**overrides) -> CrossSectionalSpec:
    defaults = {
        "pattern_id": "test_value_spec",
        "family": "test",
        "citation": "test fixture, not a real citation",
        "signal_fn": _last_close_signal,
        "lookback_days": 10,
        "holding_days": 5,
        "portfolio": "long_short",
        "rank_fraction": 0.5,
        "leg_weighting": "value",
        "requires_market_cap": True,
    }
    defaults.update(overrides)
    return CrossSectionalSpec(**defaults)


def _config(**overrides) -> CrossSectionalConfig:
    defaults = {"cost_bps": 5.0, "min_names_per_leg": 1}
    defaults.update(overrides)
    return CrossSectionalConfig(**defaults)


# --- _apply_weight_cap ------------------------------------------------------


def test_apply_weight_cap_normalizes_to_sum_one_with_no_capping_needed():
    weights = _apply_weight_cap({"A": 10.0, "B": 30.0, "C": 60.0})
    assert weights == pytest.approx({"A": 0.10, "B": 0.30, "C": 0.60})
    assert sum(weights.values()) == pytest.approx(1.0)


def test_apply_weight_cap_caps_and_redistributes_an_outlier():
    # D dwarfs A/B/C — uncapped it would take ~99.7% of the leg; capped at
    # MAX_WEIGHT_MULTIPLE * equal_share (4 members -> equal_share=0.25).
    raw = {"A": 10.0, "B": 10.0, "C": 10.0, "D": 10_000.0}
    weights = _apply_weight_cap(raw)
    equal_share = 0.25
    cap = MAX_WEIGHT_MULTIPLE * equal_share
    assert weights["D"] == pytest.approx(cap)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert all(w <= cap + 1e-9 for w in weights.values())
    # The excess D lost is redistributed proportionally among A/B/C, which
    # started tied, so they stay tied after redistribution.
    assert weights["A"] == pytest.approx(weights["B"]) == pytest.approx(weights["C"])


# --- _resolve_leg_weights: dispatch + value-weighting + fallback -----------


def test_resolve_leg_weights_magnitude_mode_is_identical_to_leg_weights():
    signal = pd.Series({"A": 10.0, "B": 20.0})
    expected = _leg_weights(["A", "B"], signal, higher_is_stronger=True)
    weights, used_fallback = _resolve_leg_weights(
        ["A", "B"], signal, higher_is_stronger=True, leg_weighting="magnitude", market_cap=None
    )
    assert weights == pytest.approx(expected)
    assert used_fallback is False


def test_resolve_leg_weights_value_mode_reduces_correctly_when_market_caps_are_equal():
    # Hand-computed case #1 (Build D1 requirement): every ticker in the leg
    # has the SAME market cap -> value weighting must reduce to plain equal
    # weight, exactly like _leg_weights' own tied-signal degenerate case.
    signal = pd.Series({"A": 5.0, "B": 5.0, "C": 5.0})  # irrelevant under "value" mode
    market_cap = pd.Series({"A": 2_000_000_000.0, "B": 2_000_000_000.0, "C": 2_000_000_000.0})
    weights, used_fallback = _resolve_leg_weights(
        ["A", "B", "C"], signal, higher_is_stronger=True, leg_weighting="value", market_cap=market_cap
    )
    assert weights == pytest.approx({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})
    assert used_fallback is False


def test_resolve_leg_weights_value_mode_weights_proportionally_to_real_market_cap():
    # Hand-computed case #2: unequal, uncapped market caps -> weights are
    # exactly proportional (10:30:60 caps -> 0.10/0.30/0.60 weights) and sum
    # to 1.0.
    signal = pd.Series({"A": 1.0, "B": 1.0, "C": 1.0})
    market_cap = pd.Series({"A": 10.0e9, "B": 30.0e9, "C": 60.0e9})
    weights, used_fallback = _resolve_leg_weights(
        ["A", "B", "C"], signal, higher_is_stronger=True, leg_weighting="value", market_cap=market_cap
    )
    assert weights == pytest.approx({"A": 0.10, "B": 0.30, "C": 0.60})
    assert sum(weights.values()) == pytest.approx(1.0)
    assert used_fallback is False


def test_resolve_leg_weights_value_mode_caps_a_mega_cap_outlier():
    signal = pd.Series({"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0})
    market_cap = pd.Series({"A": 1.0e9, "B": 1.0e9, "C": 1.0e9, "D": 3_000.0e9})
    weights, used_fallback = _resolve_leg_weights(
        ["A", "B", "C", "D"], signal, higher_is_stronger=True, leg_weighting="value", market_cap=market_cap
    )
    equal_share = 0.25
    assert weights["D"] == pytest.approx(MAX_WEIGHT_MULTIPLE * equal_share)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert used_fallback is False


def test_resolve_leg_weights_falls_back_to_magnitude_when_a_ticker_has_no_market_cap():
    # Hand-computed case #3 (Build D1 requirement): B's market cap is
    # missing (NaN — no share-count history resolved for it at this
    # formation) -> the WHOLE leg must fall back to _leg_weights' original
    # magnitude scheme, not silently drop or zero-weight just B.
    signal = pd.Series({"A": 10.0, "B": 20.0})
    market_cap = pd.Series({"A": 5.0e9, "B": np.nan})
    weights, used_fallback = _resolve_leg_weights(
        ["A", "B"], signal, higher_is_stronger=True, leg_weighting="value", market_cap=market_cap
    )
    expected = _leg_weights(["A", "B"], signal, higher_is_stronger=True)
    assert used_fallback is True
    assert weights == pytest.approx(expected)
    assert weights != pytest.approx({"A": 5.0e9 / 5.0e9, "B": 0.0})  # not a naive zero-out of B


def test_resolve_leg_weights_falls_back_when_a_ticker_has_non_positive_market_cap():
    signal = pd.Series({"A": 10.0, "B": 20.0})
    market_cap = pd.Series({"A": 5.0e9, "B": -1.0})  # a data error, not a real cap
    weights, used_fallback = _resolve_leg_weights(
        ["A", "B"], signal, higher_is_stronger=True, leg_weighting="value", market_cap=market_cap
    )
    expected = _leg_weights(["A", "B"], signal, higher_is_stronger=True)
    assert used_fallback is True
    assert weights == pytest.approx(expected)


def test_resolve_leg_weights_falls_back_when_market_cap_row_is_entirely_absent():
    signal = pd.Series({"A": 10.0, "B": 20.0})
    weights, used_fallback = _resolve_leg_weights(
        ["A", "B"], signal, higher_is_stronger=True, leg_weighting="value", market_cap=None
    )
    expected = _leg_weights(["A", "B"], signal, higher_is_stronger=True)
    assert used_fallback is True
    assert weights == pytest.approx(expected)


def test_resolve_leg_weights_single_member_leg_never_counts_as_fallback():
    signal = pd.Series({"A": 10.0})
    weights, used_fallback = _resolve_leg_weights(
        ["A"], signal, higher_is_stronger=True, leg_weighting="value", market_cap=None
    )
    assert weights == {"A": 1.0}
    assert used_fallback is False


def test_resolve_leg_weights_short_leg_uses_smallest_market_cap_member_the_same_way():
    # Direction (higher_is_stronger) must not matter for VALUE weighting —
    # market cap sizes a position regardless of whether it's the long or
    # short leg.
    signal = pd.Series({"A": 10.0, "B": -50.0})
    market_cap = pd.Series({"A": 10.0e9, "B": 30.0e9})
    weights, used_fallback = _resolve_leg_weights(
        ["A", "B"], signal, higher_is_stronger=False, leg_weighting="value", market_cap=market_cap
    )
    assert weights == pytest.approx({"A": 0.25, "B": 0.75})
    assert used_fallback is False


# --- run_cross_sectional_backtest: end-to-end value weighting -------------


def test_value_weighted_backtest_matches_hand_computed_market_cap_split():
    # A(+2%/day) long, B(-2%/day) short by last-close signal, 4 names total
    # so the median split is a 2-name leg each. Market caps: A vs the OTHER
    # long-side name C are 1:3 (weights 0.25/0.75); B vs D are 1:1 (equal,
    # 0.5/0.5) on the short side.
    close = _close_frame({"A": 0.02, "C": 0.02, "B": -0.02, "D": -0.02}, "2024-01-01", 40)
    market_cap = pd.DataFrame(
        {"A": 10.0e9, "C": 30.0e9, "B": 5.0e9, "D": 5.0e9}, index=close.index
    )
    data = CrossSectionalData(close=close, market_cap=market_cap)
    spec = _spec(rank_fraction=0.5)
    result = run_cross_sectional_backtest(data, spec, _config(), ALWAYS_MEMBER)

    assert result.status == "ok"
    formed = [f for f in result.formations if f.skipped_reason is None]
    assert sorted(formed[0].long_tickers) == ["A", "C"]
    assert sorted(formed[0].short_tickers) == ["B", "D"]
    assert formed[0].long_leg_value_weight_fallback is False
    assert formed[0].short_leg_value_weight_fallback is False

    # Second realized day (no cost): long leg = 0.25*0.02 + 0.75*0.02 =
    # 0.02 exactly (A and C compound identically, so the split doesn't even
    # matter here) — use unequal per-ticker RETURNS instead so the weight
    # split is actually load-bearing in the assertion below.
    second_day_return = result.daily_returns.iloc[1]
    assert second_day_return == pytest.approx(0.02 - (-0.02))


def test_value_weighted_backtest_load_bearing_split_matches_hand_calc():
    # Distinct per-ticker returns so the 0.25/0.75 market-cap split is
    # actually load-bearing, not coincidentally equal to an equal-weighted
    # result.
    close = _close_frame({"A": 0.04, "C": 0.00, "B": -0.01, "D": -0.03}, "2024-01-01", 40)
    market_cap = pd.DataFrame(
        {"A": 10.0e9, "C": 30.0e9, "B": 5.0e9, "D": 5.0e9}, index=close.index
    )
    data = CrossSectionalData(close=close, market_cap=market_cap)
    spec = _spec(rank_fraction=0.5)
    result = run_cross_sectional_backtest(data, spec, _config(), ALWAYS_MEMBER)

    expected_long = 0.25 * 0.04 + 0.75 * 0.00
    expected_short = 0.5 * -0.01 + 0.5 * -0.03
    assert result.daily_returns.iloc[1] == pytest.approx(expected_long - expected_short)


def test_value_weighted_backtest_falls_back_and_flags_when_a_formation_has_no_market_cap_row():
    # market_cap is entirely NaN for the whole replay (e.g. every ticker has
    # no resolvable share-count history anywhere) -> every formation's legs
    # must fall back to magnitude weighting and be flagged as such, never
    # silently produce a degenerate/empty book. Uses 2-member legs (4
    # tickers, rank_fraction=0.5) deliberately — a 1-member leg never counts
    # as a fallback by design (see _resolve_leg_weights' own docstring: "no
    # value vs magnitude question to ask about a single name's own
    # weight"), so this must have a genuine >=2-member leg to exercise the
    # path at all.
    close = _close_frame({"A": 0.02, "C": 0.02, "B": -0.02, "D": -0.02}, "2024-01-01", 30)
    market_cap = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    data = CrossSectionalData(close=close, market_cap=market_cap)
    spec = _spec(rank_fraction=0.5)
    result = run_cross_sectional_backtest(data, spec, _config(), ALWAYS_MEMBER)

    assert result.status == "ok"
    formed = [f for f in result.formations if f.skipped_reason is None]
    assert formed  # the backtest still forms real positions via the fallback
    assert all(f.long_leg_value_weight_fallback for f in formed)
    assert all(f.short_leg_value_weight_fallback for f in formed)
    # Fallback weights are exactly _leg_weights' own result on a tied
    # (A == C, B == D) signal at this rank_fraction — equal weight each,
    # same as any magnitude-weighted spec would produce here.
    assert result.daily_returns.iloc[1] == pytest.approx(0.02 - (-0.02))


def test_value_weighted_spec_requires_market_cap_data():
    close = _close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 30)
    data = CrossSectionalData(close=close)  # market_cap left None
    spec = _spec()
    with pytest.raises(ValueError, match="market cap"):
        run_cross_sectional_backtest(data, spec, _config(), ALWAYS_MEMBER)


def test_long_universe_hedged_hedge_side_stays_equal_weighted_under_value_mode():
    # The universe-hedge side of long_universe_hedged is never value
    # weighted (see _target_weights) — only the ranked long leg is.
    close = _close_frame({"A": 0.04, "B": 0.02, "C": 0.0, "D": -0.02}, "2024-01-01", 30)
    market_cap = pd.DataFrame(
        {"A": 100.0e9, "B": 1.0e9, "C": 1.0e9, "D": 1.0e9}, index=close.index
    )
    data = CrossSectionalData(close=close, market_cap=market_cap)
    spec = _spec(portfolio="long_universe_hedged", rank_fraction=0.25)
    result = run_cross_sectional_backtest(data, spec, _config(), ALWAYS_MEMBER)

    assert result.daily_returns.iloc[1] == pytest.approx(0.04 - 0.01)  # A alone vs equal-weighted mean
    formed = [f for f in result.formations if f.skipped_reason is None]
    assert formed[0].long_tickers == ["A"]
    assert sorted(formed[0].short_tickers) == ["A", "B", "C", "D"]


# --- screen_cross_sectional_universe: fallback accounting -----------------


def test_screening_reports_zero_value_weight_fallbacks_for_a_magnitude_spec():
    close = _close_frame(
        {"A": 0.012, "B": 0.008, "C": -0.008, "D": -0.012}, "2023-01-02", 150
    )
    spec = CrossSectionalSpec(
        pattern_id="magnitude_spec",
        family="test",
        citation="test fixture",
        signal_fn=_last_close_signal,
        lookback_days=10,
        holding_days=10,
        portfolio="long_short",
        rank_fraction=0.5,
    )
    results = screen_cross_sectional_universe(
        CrossSectionalData(close=close), [spec], _config(), ALWAYS_MEMBER
    )
    assert len(results) == 1
    assert results[0].n_value_weighted_legs == 0
    assert results[0].n_value_weight_fallbacks == 0


def test_screening_counts_value_weight_fallbacks_across_formations():
    # 200 rows: some formations land on days where B's market cap is NaN
    # (forcing a fallback), others where every name has a real cap.
    close = _close_frame(
        {"A": 0.012, "B": 0.008, "C": -0.008, "D": -0.012}, "2023-01-02", 200
    )
    market_cap = pd.DataFrame(10.0e9, index=close.index, columns=close.columns)
    # Knock out B's market cap for the back half of the replay only.
    market_cap.loc[market_cap.index[100]:, "B"] = np.nan
    data = CrossSectionalData(close=close, market_cap=market_cap)
    spec = _spec(rank_fraction=0.5, holding_days=10)
    results = screen_cross_sectional_universe(data, [spec], _config(), ALWAYS_MEMBER)

    assert len(results) == 1
    r = results[0]
    assert r.n_value_weighted_legs > 0
    assert 0 < r.n_value_weight_fallbacks < r.n_value_weighted_legs  # some, not all, not none


# --- validate_cross_sectional_data: market_cap alignment ------------------


def test_validate_rejects_misaligned_market_cap():
    from app.services.research_lab.cross_sectional import validate_cross_sectional_data

    close = _close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 10)
    misaligned_cap = close.iloc[:5]
    with pytest.raises(ValueError, match="not aligned"):
        validate_cross_sectional_data(CrossSectionalData(close=close, market_cap=misaligned_cap))
