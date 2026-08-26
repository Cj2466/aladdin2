import logging
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    DEFAULT_FINANCING_BPS_PER_YEAR,
    DEFAULT_IMPUTED_DELISTING_RETURN,
    FINANCING_DAYS_PER_YEAR,
    MAX_WEIGHT_MULTIPLE,
    SHUMWAY_NASDAQ_DELISTING_RETURN,
    SHUMWAY_NYSE_AMEX_DELISTING_RETURN,
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    EmptyEligibleUniverseError,
    _apply_weight_cap,
    _compute_delisting_positions,
    _leg_weighted_return,
    _leg_weights,
    fixed_universe_membership,
    run_cross_sectional_backtest,
    screen_cross_sectional_universe,
    select_leg_tickers,
    validate_cross_sectional_data,
)
from app.services.research_lab.sp500_membership_history import was_member

# Membership stub for pure-mechanics tests — every ticker always eligible,
# so nothing here depends on the vendored S&P data EXCEPT the point-in-time
# tests below, which deliberately use the real was_member.
ALWAYS_MEMBER = lambda _ticker, _on: True


def _close_frame(returns_by_ticker: dict[str, float], start: str, n_days: int) -> pd.DataFrame:
    """Deterministic multiplicative price paths: each ticker compounds at a
    constant daily return, so every day's realized pct_change is exactly
    that constant — hand-checkable leg means."""
    index = pd.bdate_range(start, periods=n_days)
    data = {
        ticker: 100.0 * np.cumprod(np.full(n_days, 1.0 + r))
        for ticker, r in returns_by_ticker.items()
    }
    return pd.DataFrame(data, index=index)


def _last_close_signal(view: CrossSectionalData) -> pd.Series:
    return view.close.iloc[-1]


def _spec(**overrides) -> CrossSectionalSpec:
    defaults = {
        "pattern_id": "test_spec",
        "family": "test",
        "citation": "test fixture, not a real citation",
        "signal_fn": _last_close_signal,
        "lookback_days": 10,
        "holding_days": 5,
        "portfolio": "long_short",
        "rank_fraction": 0.5,
    }
    defaults.update(overrides)
    return CrossSectionalSpec(**defaults)


def _config(**overrides) -> CrossSectionalConfig:
    defaults = {"cost_bps": 5.0, "min_names_per_leg": 1}
    defaults.update(overrides)
    return CrossSectionalConfig(**defaults)


# --- select_leg_tickers -------------------------------------------------


def test_select_leg_tickers_takes_top_and_bottom_fraction():
    signal = pd.Series({"A": 10.0, "B": 9.0, "C": 8.0, "D": 7.0, "E": 6.0,
                        "F": 5.0, "G": 4.0, "H": 3.0, "I": 2.0, "J": 1.0})
    top, bottom = select_leg_tickers(signal, 0.2)
    assert top == ["A", "B"]
    assert bottom == ["I", "J"]


def test_select_leg_tickers_drops_nan_signals():
    signal = pd.Series({"A": 3.0, "B": np.nan, "C": 2.0, "D": 1.0})
    top, bottom = select_leg_tickers(signal, 0.25)
    assert top == ["A"]
    assert bottom == ["D"]


def test_select_leg_tickers_is_deterministic_under_ties():
    # All-equal signals: the stable sort's alphabetical pre-order decides,
    # so a re-run always forms the identical portfolio.
    signal = pd.Series({"D": 1.0, "B": 1.0, "C": 1.0, "A": 1.0})
    top, bottom = select_leg_tickers(signal, 0.25)
    assert top == ["A"]
    assert bottom == ["D"]


def test_select_leg_tickers_minimum_leg_of_one():
    signal = pd.Series({"A": 2.0, "B": 1.0})
    top, bottom = select_leg_tickers(signal, 0.1)
    assert top == ["A"]
    assert bottom == ["B"]


# --- _leg_weights / _leg_weighted_return (magnitude-weighted sizing) -----


def test_leg_weights_single_member_is_always_full_weight():
    signal = pd.Series({"A": 123.0})
    assert _leg_weights(["A"], signal, higher_is_stronger=True) == {"A": 1.0}
    assert _leg_weights(["A"], signal, higher_is_stronger=False) == {"A": 1.0}


def test_leg_weights_falls_back_to_equal_when_tied():
    signal = pd.Series({"A": 5.0, "B": 5.0, "C": 5.0})
    weights = _leg_weights(["A", "B", "C"], signal, higher_is_stronger=True)
    assert weights == pytest.approx({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})


def test_leg_weights_boundary_member_gets_only_the_floor_share():
    # A(10) is the marginal (weakest, boundary) member of a long leg — its
    # excess above the boundary is 0, so its raw weight is the floor
    # (MIN_RELATIVE_WEIGHT_FRACTION * spread), not a full equal share; B(20)
    # is the leg's only source of excess, so it gets the rest.
    # raw_A = 0.1*10 = 1.0, raw_B = 10.0, total = 11.0.
    signal = pd.Series({"A": 10.0, "B": 20.0})
    weights = _leg_weights(["A", "B"], signal, higher_is_stronger=True)
    assert weights == pytest.approx({"A": 1.0 / 11.0, "B": 10.0 / 11.0})
    assert weights["A"] + weights["B"] == pytest.approx(1.0)
    assert weights["B"] > weights["A"]  # the more extreme member is weighted more


def test_leg_weights_short_leg_weights_the_smallest_value_most():
    signal = pd.Series({"A": 10.0, "B": -50.0})
    weights = _leg_weights(["A", "B"], signal, higher_is_stronger=False)
    assert weights["B"] > weights["A"]  # B (smaller/most negative) is the extreme short


def test_leg_weights_caps_an_extreme_outlier():
    # D is wildly more extreme than A/B/C — uncapped it would dominate the
    # leg; the cap must hold every weight to MAX_WEIGHT_MULTIPLE * equal
    # share, with the excess redistributed among the rest.
    signal = pd.Series({"A": 10.0, "B": 10.1, "C": 10.2, "D": 10_000.0})
    weights = _leg_weights(["A", "B", "C", "D"], signal, higher_is_stronger=True)
    equal_share = 0.25
    assert weights["D"] == pytest.approx(MAX_WEIGHT_MULTIPLE * equal_share)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert all(w <= MAX_WEIGHT_MULTIPLE * equal_share + 1e-9 for w in weights.values())


def test_leg_weighted_return_reduces_to_plain_mean_at_equal_weights():
    day = pd.Series({"A": 0.03, "B": -0.01})
    assert _leg_weighted_return(day, {"A": 0.5, "B": 0.5}) == pytest.approx(0.01)


def test_leg_weighted_return_renormalizes_over_survivors():
    day = pd.Series({"A": np.nan, "B": 0.02})
    assert _leg_weighted_return(day, {"A": 0.7, "B": 0.3}) == pytest.approx(0.02)


def test_leg_weighted_return_empty_leg_is_zero():
    assert _leg_weighted_return(pd.Series({"A": 0.05}), {}) == 0.0


# --- _apply_weight_cap convergence (regression for a real bug found by an
# independent-verify pass, 2026-08-26 — a member clamped to exactly `cap`
# was still counted as "under" on the next pass and could be pushed back
# over cap by further redistribution) ---------------------------------


def test_apply_weight_cap_two_simultaneous_over_cap_outliers_both_converge():
    # Two members simultaneously and severely over cap forces a real
    # multi-member redistribution the original single-outlier test never
    # exercised — exactly the shape the bug needed to manifest.
    raw = {"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0, "E": 1.0, "F": 1.0, "G": 1.0, "H": 1.0, "I": 10_000.0, "J": 9_000.0}
    weights = _apply_weight_cap(raw)
    equal_share = 1.0 / len(weights)
    cap = MAX_WEIGHT_MULTIPLE * equal_share
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["I"] == pytest.approx(cap)
    assert weights["J"] == pytest.approx(cap)
    assert all(w <= cap + 1e-9 for w in weights.values())


def test_apply_weight_cap_never_exceeds_cap_across_randomized_fat_tailed_legs():
    # The exact stress test the independent-verify pass used to find the
    # bug (2,000 randomized fat-tailed leg compositions, ~23% violated
    # under the old code by up to 36 percentage points) — now a permanent
    # regression guard, seeded for determinism.
    rng = np.random.default_rng(42)
    for _ in range(500):
        n = int(rng.integers(5, 20))
        raw = {f"t{i}": float(rng.lognormal(mean=0.0, sigma=rng.uniform(1.5, 3.0))) for i in range(n)}
        weights = _apply_weight_cap(raw)
        equal_share = 1.0 / len(weights)
        cap = MAX_WEIGHT_MULTIPLE * equal_share
        assert sum(weights.values()) == pytest.approx(1.0)
        assert all(w <= cap + 1e-9 for w in weights.values())


# --- formation schedule and return realization ---------------------------


def test_long_short_daily_returns_and_first_day_cost():
    # A compounds at +1%/day, B at -1%/day; ranking on last close puts A
    # long and B short from the first formation on. Gross daily return is
    # exactly 0.02; the first realization day also carries the formation
    # cost of (5bps) * turnover 2.0 (buy 1.0 long, sell 1.0 short from
    # flat) = 0.001. Later formations re-form the identical book, so
    # turnover — and cost — is zero.
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 40))
    result = run_cross_sectional_backtest(data, _spec(), _config(), ALWAYS_MEMBER)

    assert result.status == "ok"
    first = result.daily_returns.iloc[0]
    assert first == pytest.approx(0.02 - 0.001)
    assert result.daily_returns.iloc[1] == pytest.approx(0.02)
    # Reformation day (5 trading days after formation) carries no cost:
    assert result.daily_returns.iloc[5] == pytest.approx(0.02)
    assert result.total_cost == pytest.approx(0.001)
    formed = [f for f in result.formations if f.skipped_reason is None]
    assert formed[0].long_tickers == ["A"]
    assert formed[0].short_tickers == ["B"]
    assert formed[0].turnover == pytest.approx(2.0)
    assert formed[1].turnover == pytest.approx(0.0)


def test_formations_occur_on_schedule_and_returns_start_next_day():
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 30))
    spec = _spec(lookback_days=10, holding_days=5)
    result = run_cross_sectional_backtest(data, spec, _config(), ALWAYS_MEMBER)

    index = data.close.index
    expected_formation_dates = [index[i] for i in range(10, len(index) - 1, 5)]
    assert [f.date for f in result.formations] == expected_formation_dates
    # First realized return is the day AFTER the first formation — the
    # formation date's own move is never realized (formation at that
    # day's close).
    assert result.daily_returns.index[0] == index[11]


def test_full_book_flip_charges_double_turnover():
    # Signal flips which name ranks on top partway through: the book goes
    # long A/short B -> long B/short A, trading gross notional 4.0
    # (2.0 out, 2.0 in), so the reformation costs 4 * 5bps = 0.002.
    close = _close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 30)
    flip_date = close.index[12]

    def flip_signal(view: CrossSectionalData) -> pd.Series:
        if view.close.index[-1] <= flip_date:
            return pd.Series({"A": 2.0, "B": 1.0})
        return pd.Series({"A": 1.0, "B": 2.0})

    data = CrossSectionalData(close=close)
    spec = _spec(signal_fn=flip_signal, lookback_days=10, holding_days=5)
    result = run_cross_sectional_backtest(data, spec, _config(), ALWAYS_MEMBER)

    formed = [f for f in result.formations if f.skipped_reason is None]
    assert formed[0].long_tickers == ["A"]
    assert formed[1].long_tickers == ["B"]
    assert formed[1].turnover == pytest.approx(4.0)
    assert result.total_cost == pytest.approx((5.0 / 10_000.0) * (2.0 + 4.0))


def test_long_universe_hedged_return_is_top_minus_universe_mean():
    # Four names at +4%/+2%/0%/-2% daily; top-quarter long leg is A alone,
    # hedged against the equal-weighted universe (mean +1%): gross 3%/day.
    data = CrossSectionalData(
        close=_close_frame({"A": 0.04, "B": 0.02, "C": 0.0, "D": -0.02}, "2024-01-01", 30)
    )
    spec = _spec(portfolio="long_universe_hedged", rank_fraction=0.25)
    result = run_cross_sectional_backtest(data, spec, _config(), ALWAYS_MEMBER)

    assert result.daily_returns.iloc[1] == pytest.approx(0.04 - 0.01)
    formed = [f for f in result.formations if f.skipped_reason is None]
    assert formed[0].long_tickers == ["A"]
    assert sorted(formed[0].short_tickers) == ["A", "B", "C", "D"]


def test_delisted_mid_hold_ticker_drops_out_of_leg_mean():
    # A's prices stop mid-replay (delisting): from the first NaN return
    # onward the long leg's return is computed over the remaining name's
    # own weight only, renormalized — the liquidate-at-last-price
    # convention, not a fabricated 0% for A.
    #
    # A(+2%)/B(+1%) rank above C(-1%)/D(-2%) by last-close signal, and A's
    # faster compounding makes it the more extreme (higher-weighted) long
    # member, D the more extreme short member — magnitude-weighted, not
    # equal, per _leg_weights. Expected values below are exact by
    # construction (verified via a direct run of _leg_weights /
    # _leg_weighted_return against this fixture's real formation-date
    # signal, not hand-approximated): long/short weights are 10/11-1/11 at
    # this fixture's spread (the marginal member carries only the
    # MIN_RELATIVE_WEIGHT_FRACTION floor, the extreme member the rest).
    close = _close_frame({"A": 0.02, "B": 0.01, "C": -0.01, "D": -0.02}, "2024-01-01", 30)
    close.loc[close.index[15]:, "A"] = np.nan
    data = CrossSectionalData(close=close)
    spec = _spec(rank_fraction=0.5, lookback_days=10, holding_days=10)
    result = run_cross_sectional_backtest(data, spec, _config(), ALWAYS_MEMBER)

    # Before the delisting: long/short legs both weighted 10/11 (extreme
    # member: A long, D short) / 1/11 (marginal member: B long, C short).
    assert result.daily_returns.loc[close.index[12]] == pytest.approx(
        (10 / 11 * 0.02 + 1 / 11 * 0.01) - (10 / 11 * -0.02 + 1 / 11 * -0.01)
    )
    # After: long leg is B alone (weight 1.0, A dropped and renormalized);
    # short leg weights are unaffected by A's delisting (A was never a
    # short-leg member).
    assert result.daily_returns.loc[close.index[17]] == pytest.approx(
        0.01 - (10 / 11 * -0.02 + 1 / 11 * -0.01)
    )


# --- opt-in Shumway-style imputed delisting return (Build D2) ------------


def test_default_imputed_delisting_return_is_the_shumway_blend():
    assert SHUMWAY_NYSE_AMEX_DELISTING_RETURN == pytest.approx(-0.30)
    assert SHUMWAY_NASDAQ_DELISTING_RETURN == pytest.approx(-0.55)
    assert DEFAULT_IMPUTED_DELISTING_RETURN == pytest.approx(
        (SHUMWAY_NYSE_AMEX_DELISTING_RETURN + SHUMWAY_NASDAQ_DELISTING_RETURN) / 2.0
    )


def test_compute_delisting_positions_flags_only_a_permanent_stop():
    # A: stops at row 15 and never trades again -> flagged at 15 (the first
    # missing row). B: NaN for two rows then recovers -> NOT flagged, a
    # data gap. C: trades right through the last row -> NOT flagged, the
    # data simply ends, which is not evidence of a delisting.
    close = _close_frame({"A": 0.01, "B": 0.01, "C": 0.01}, "2024-01-01", 30)
    close.loc[close.index[15]:, "A"] = np.nan
    close.loc[close.index[15]:close.index[16], "B"] = np.nan
    positions = _compute_delisting_positions(close)
    assert positions == {"A": 15}


def test_delisting_imputation_off_by_default_matches_pre_existing_behavior():
    # Literal proof the new option changes nothing when left off: rerun the
    # pre-existing delisted-mid-hold fixture above through an EXPLICIT
    # impute_delisting_returns=False config (not just the implicit default)
    # and assert the exact same numbers the harness produced before this
    # option existed.
    close = _close_frame({"A": 0.02, "B": 0.01, "C": -0.01, "D": -0.02}, "2024-01-01", 30)
    close.loc[close.index[15]:, "A"] = np.nan  # permanently stops -- would be flagged if the option were on
    data = CrossSectionalData(close=close)
    spec = _spec(rank_fraction=0.5, lookback_days=10, holding_days=10)
    result = run_cross_sectional_backtest(
        data, spec, _config(impute_delisting_returns=False), ALWAYS_MEMBER
    )
    assert result.daily_returns.loc[close.index[12]] == pytest.approx(
        (10 / 11 * 0.02 + 1 / 11 * 0.01) - (10 / 11 * -0.02 + 1 / 11 * -0.01)
    )
    assert result.daily_returns.loc[close.index[17]] == pytest.approx(
        0.01 - (10 / 11 * -0.02 + 1 / 11 * -0.01)
    )


def test_delisting_imputation_charges_the_loss_once_on_the_transition_day():
    # Same fixture as the always-drop test, but with imputation switched on:
    # A's last valid close is row 14, so row 15 is its precomputed
    # delisting day (see test_compute_delisting_positions_flags_only_a_
    # permanent_stop). The formation's fixed long/short weights (10/11
    # extreme member, 1/11 marginal, same construction as the always-drop
    # test) are unchanged by this option -- only what A's OWN return
    # resolves to on day 15 changes: the imputed loss instead of NaN.
    close = _close_frame({"A": 0.02, "B": 0.01, "C": -0.01, "D": -0.02}, "2024-01-01", 30)
    close.loc[close.index[15]:, "A"] = np.nan
    data = CrossSectionalData(close=close)
    spec = _spec(rank_fraction=0.5, lookback_days=10, holding_days=10)
    config = _config(impute_delisting_returns=True, imputed_delisting_return=-0.4)
    result = run_cross_sectional_backtest(data, spec, config, ALWAYS_MEMBER)

    short_leg = 10 / 11 * -0.02 + 1 / 11 * -0.01
    # Transition day: A's imputed -40% enters the long leg mean at its own
    # fixed formation weight, exactly like a real return would.
    assert result.daily_returns.loc[close.index[15]] == pytest.approx(
        (10 / 11 * -0.4 + 1 / 11 * 0.01) - short_leg
    )
    # The very next day: the imputed loss already fired once: A is simply
    # gone now (its return is NaN again), long leg is B alone -- identical
    # to the always-drop convention's post-delisting value.
    assert result.daily_returns.loc[close.index[16]] == pytest.approx(0.01 - short_leg)
    # And it stays that way for the rest of the hold -- no repeat charge.
    assert result.daily_returns.loc[close.index[19]] == pytest.approx(0.01 - short_leg)


def test_delisting_imputation_uses_the_default_shumway_blend_when_unset():
    close = _close_frame({"A": 0.02, "B": 0.01, "C": -0.01, "D": -0.02}, "2024-01-01", 30)
    close.loc[close.index[15]:, "A"] = np.nan
    data = CrossSectionalData(close=close)
    spec = _spec(rank_fraction=0.5, lookback_days=10, holding_days=10)
    result = run_cross_sectional_backtest(
        data, spec, _config(impute_delisting_returns=True), ALWAYS_MEMBER
    )
    short_leg = 10 / 11 * -0.02 + 1 / 11 * -0.01
    assert result.daily_returns.loc[close.index[15]] == pytest.approx(
        (10 / 11 * DEFAULT_IMPUTED_DELISTING_RETURN + 1 / 11 * 0.01) - short_leg
    )


def test_delisting_imputation_does_not_fire_on_a_transient_data_gap():
    # A's price is missing for two days but REAPPEARS later in the loaded
    # frame -- a data gap (halt, provider hiccup), not a real delisting.
    # Even with an extreme imputed value configured, it must never fire:
    # the gap days fall back to the ordinary drop-and-renormalize
    # convention, and once A's return is measurable again (pct_change needs
    # a valid PRIOR row too, so that is one row after prices resume) it
    # re-enters the leg mean completely unmodified.
    close = _close_frame({"A": 0.02, "B": 0.01, "C": -0.01, "D": -0.02}, "2024-01-01", 30)
    close.loc[close.index[15]:close.index[16], "A"] = np.nan
    data = CrossSectionalData(close=close)
    spec = _spec(rank_fraction=0.5, lookback_days=10, holding_days=10)
    config = _config(impute_delisting_returns=True, imputed_delisting_return=-0.99)
    result = run_cross_sectional_backtest(data, spec, config, ALWAYS_MEMBER)

    short_leg = 10 / 11 * -0.02 + 1 / 11 * -0.01
    assert result.daily_returns.loc[close.index[15]] == pytest.approx(0.01 - short_leg)
    assert result.daily_returns.loc[close.index[16]] == pytest.approx(0.01 - short_leg)
    # Row 17: A's price is real again, but pct_change from row 16 (NaN) is
    # still NaN for exactly this one day -- still the drop convention.
    assert result.daily_returns.loc[close.index[17]] == pytest.approx(0.01 - short_leg)
    # Row 18: A's return is a genuine, valid +2% again -- full recovery,
    # back to the original two-member long leg.
    assert result.daily_returns.loc[close.index[18]] == pytest.approx(
        (10 / 11 * 0.02 + 1 / 11 * 0.01) - short_leg
    )


# --- opt-in overlapping (Jegadeesh-Titman-style) cohorts (Build D2) ------


def test_cohort_formation_days_unset_matches_pre_existing_behavior():
    # Explicit proof the new option changes nothing when left unset: the
    # SAME fixture/assertions as test_long_short_daily_returns_and_first_
    # day_cost, run with cohort_formation_days left at its default (None).
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 40))
    result = run_cross_sectional_backtest(data, _spec(), _config(), ALWAYS_MEMBER)
    assert result.status == "ok"
    assert result.daily_returns.iloc[0] == pytest.approx(0.02 - 0.001)
    assert result.daily_returns.iloc[1] == pytest.approx(0.02)
    assert result.total_cost == pytest.approx(0.001)


def test_cohort_formation_days_equal_to_holding_days_is_equivalent_to_unset():
    close = _close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 40)
    data = CrossSectionalData(close=close)
    baseline = run_cross_sectional_backtest(data, _spec(), _config(), ALWAYS_MEMBER)
    explicit = run_cross_sectional_backtest(
        data, _spec(cohort_formation_days=5), _config(), ALWAYS_MEMBER  # _spec()'s holding_days default is 5
    )
    pd.testing.assert_series_equal(baseline.daily_returns, explicit.daily_returns)
    assert baseline.total_cost == pytest.approx(explicit.total_cost)
    assert [f.date for f in baseline.formations] == [f.date for f in explicit.formations]


def test_invalid_cohort_formation_days_is_rejected():
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 40))
    with pytest.raises(ValueError, match="cohort_formation_days"):
        run_cross_sectional_backtest(
            data, _spec(cohort_formation_days=0), _config(), ALWAYS_MEMBER
        )
    with pytest.raises(ValueError, match="cohort_formation_days"):
        # holding_days default is 5 -- a cadence larger than the hold isn't
        # an overlap, it's a different (and here, nonsensical) schedule.
        run_cross_sectional_backtest(
            data, _spec(cohort_formation_days=6), _config(), ALWAYS_MEMBER
        )


def test_overlapping_cohorts_blend_two_staggered_sleeves_across_a_signal_flip():
    # A compounds at +1%/day, B at -1%/day, so A's raw price rises above
    # B's from day 1 and a last-close-price signal ranks A long/B short --
    # UNTIL flip_date, after which the ranking (and hence which name is
    # long vs short) flips. holding_days=8, cohort_formation_days=4 ->
    # n_sleeves=2: sleeve 0 starts at first_formation=5 (BEFORE flip_date),
    # sleeve 1 starts at first_formation+4=9 (AFTER flip_date). Both sleeves
    # are simultaneously active on days 10-13 (sleeve 0's first hold runs
    # through day 13; sleeve 1's first hold starts at day 10) but hold
    # OPPOSITE books, so their gross returns are +0.02 and -0.02
    # respectively -- a clean, hand-verifiable blended prediction.
    close = _close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 30)
    flip_date = close.index[7]

    def flip_signal(view: CrossSectionalData) -> pd.Series:
        if view.close.index[-1] <= flip_date:
            return pd.Series({"A": 2.0, "B": 1.0})
        return pd.Series({"A": 1.0, "B": 2.0})

    data = CrossSectionalData(close=close)
    spec = _spec(
        signal_fn=flip_signal, lookback_days=5, holding_days=8, cohort_formation_days=4
    )
    result = run_cross_sectional_backtest(data, spec, _config(), ALWAYS_MEMBER)
    assert result.status == "ok"

    # Sleeve 0 formed at position 5 (index[5] <= flip_date=index[7]): A long
    # / B short, held through day 13. Sleeve 1 formed at position 9
    # (index[9] > flip_date): B long / A short, held through day 17.
    formed = [f for f in result.formations if f.skipped_reason is None]
    by_date = {f.date: f for f in formed}
    assert by_date[close.index[5]].long_tickers == ["A"]
    assert by_date[close.index[9]].long_tickers == ["B"]

    # Day 10 is sleeve 1's first realization day, so it alone carries
    # sleeve 1's formation cost (going from flat to a full book: turnover
    # 2.0 -> 5bps * 2.0 = 0.001).
    sleeve0_gross = 0.02   # A long (+1%) minus B short (-1%)
    sleeve1_gross = -0.02  # B long (-1%) minus A short (+1%)
    sleeve1_cost = 0.001
    assert result.daily_returns.loc[close.index[10]] == pytest.approx(
        (sleeve0_gross + (sleeve1_gross - sleeve1_cost)) / 2.0
    )
    # Days 11-13: both sleeves active, no further cost -- clean cancellation.
    for day_pos in (11, 12, 13):
        assert result.daily_returns.loc[close.index[day_pos]] == pytest.approx(
            (sleeve0_gross + sleeve1_gross) / 2.0
        )

    # More formations exist than the non-overlapping schedule would produce
    # (two staggered sleeves each reforming across the same replay window).
    non_overlapping = run_cross_sectional_backtest(
        data, _spec(signal_fn=flip_signal, lookback_days=5, holding_days=8), _config(), ALWAYS_MEMBER
    )
    assert len(formed) > len([f for f in non_overlapping.formations if f.skipped_reason is None])


def test_min_names_per_leg_skips_formation():
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 30))
    result = run_cross_sectional_backtest(
        data, _spec(), _config(min_names_per_leg=5), ALWAYS_MEMBER
    )
    assert result.status == "no_valid_formations"
    assert all(f.skipped_reason is not None for f in result.formations)
    assert (result.daily_returns == 0.0).all()
    assert result.total_cost == 0.0


def test_overlapping_legs_are_rejected():
    # 3 ranked names at rank_fraction 0.5 -> legs of 1 each is fine; but a
    # fraction that forces 2*leg > n must skip, not double-count a name.
    data = CrossSectionalData(
        close=_close_frame({"A": 0.01, "B": 0.0, "C": -0.01}, "2024-01-01", 30)
    )
    result = run_cross_sectional_backtest(
        data, _spec(rank_fraction=0.67), _config(), ALWAYS_MEMBER
    )
    assert result.status == "no_valid_formations"
    assert all("overlap" in (f.skipped_reason or "") for f in result.formations)


def test_insufficient_history_status():
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 8))
    result = run_cross_sectional_backtest(data, _spec(lookback_days=10), _config(), ALWAYS_MEMBER)
    assert result.status == "insufficient_history"
    assert result.daily_returns.empty


def test_formation_start_pins_first_formation():
    close = _close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 60)
    start = close.index[30].date()
    data = CrossSectionalData(close=close)
    result = run_cross_sectional_backtest(
        data, _spec(), _config(formation_start=start), ALWAYS_MEMBER
    )
    assert all(f.date.date() >= start for f in result.formations)
    assert result.formations[0].date == close.index[30]


def test_requires_open_and_volume_are_enforced():
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 30))
    with pytest.raises(ValueError, match="requires daily Open"):
        run_cross_sectional_backtest(data, _spec(requires_open=True), _config(), ALWAYS_MEMBER)
    with pytest.raises(ValueError, match="requires daily Volume"):
        run_cross_sectional_backtest(data, _spec(requires_volume=True), _config(), ALWAYS_MEMBER)


def test_validate_rejects_misaligned_frames():
    close = _close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 10)
    misaligned_open = close.iloc[:5]
    with pytest.raises(ValueError, match="not aligned"):
        validate_cross_sectional_data(CrossSectionalData(close=close, open=misaligned_open))


# --- look-ahead impossibility -------------------------------------------
# The cross-sectional analogue of test_research_lab's walk-forward
# look-ahead test: perturbing every price AFTER a cutoff date must leave
# all formations dated on or before the cutoff — and every return realized
# before the cutoff — bit-identical.


def test_future_prices_cannot_affect_past_formations_or_returns():
    rng = np.random.default_rng(7)
    index = pd.bdate_range("2024-01-01", periods=80)
    tickers = list("ABCDEFGH")
    walks = {
        t: 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, len(index))) for t in tickers
    }
    close = pd.DataFrame(walks, index=index)

    def trailing_mean_signal(view: CrossSectionalData) -> pd.Series:
        return view.close.iloc[-5:].mean()

    spec = _spec(signal_fn=trailing_mean_signal, rank_fraction=0.25, lookback_days=10, holding_days=5)
    cutoff = index[40]

    baseline = run_cross_sectional_backtest(
        CrossSectionalData(close=close), spec, _config(), ALWAYS_MEMBER
    )

    perturbed_close = close.copy()
    perturbed_close.loc[perturbed_close.index > cutoff] *= rng.uniform(
        0.5, 1.5, (int((index > cutoff).sum()), len(tickers))
    )
    perturbed = run_cross_sectional_backtest(
        CrossSectionalData(close=perturbed_close), spec, _config(), ALWAYS_MEMBER
    )

    for base_f, pert_f in zip(baseline.formations, perturbed.formations, strict=True):
        if base_f.date <= cutoff:
            assert base_f.long_tickers == pert_f.long_tickers
            assert base_f.short_tickers == pert_f.short_tickers
    base_before = baseline.daily_returns[baseline.daily_returns.index <= cutoff]
    pert_before = perturbed.daily_returns[perturbed.daily_returns.index <= cutoff]
    pd.testing.assert_series_equal(base_before, pert_before)


# --- POINT-IN-TIME UNIVERSE CORRECTNESS ---------------------------------
# The highest-risk-of-silent-bug property in this module, tested against
# REAL index events from sp500_membership_history's own hand-verified
# change log (its module docstring lists both among the thirteen
# independently confirmed events):
#   * TWTR removed 2022-11-01 (Musk take-private closed 2022-10-27)
#   * PLTR added   2024-09-23
# Price data is synthetic and deliberately spans BOTH sides of each event
# for BOTH tickers — the harness must exclude them by membership alone,
# never because data happens to be absent.

_PIT_TICKERS = ["AAPL", "JPM", "KO", "MSFT", "PG", "PLTR", "TWTR", "XOM"]
# Constants chosen so TWTR ranks first and PLTR second whenever eligible —
# if either leaks into a formation it lands in the LONG leg, where the
# assertions below cannot miss it.
_PIT_RANKS = {"TWTR": 100.0, "PLTR": 99.0, "AAPL": 98.0, "MSFT": 97.0,
              "JPM": 96.0, "XOM": 95.0, "KO": 94.0, "PG": 93.0}

TWTR_REMOVAL = date(2022, 11, 1)
PLTR_ADDITION = date(2024, 9, 23)


def _pit_rank_signal(view: CrossSectionalData) -> pd.Series:
    return pd.Series({t: _PIT_RANKS[t] for t in view.close.columns})


def _pit_backtest() -> tuple[pd.DatetimeIndex, list]:
    index = pd.bdate_range("2022-06-01", "2025-01-31")
    rng = np.random.default_rng(11)
    close = pd.DataFrame(
        {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, len(index))) for t in _PIT_TICKERS},
        index=index,
    )
    spec = _spec(signal_fn=_pit_rank_signal, rank_fraction=0.2, lookback_days=10, holding_days=21)
    # membership_fn deliberately omitted: the default IS the real
    # point-in-time was_member — that composition is what's under test.
    result = run_cross_sectional_backtest(CrossSectionalData(close=close), spec, _config())
    assert result.status == "ok"
    return index, result.formations


def test_membership_ground_truth_matches_the_verified_change_log():
    # Anchor this file's assumptions directly to the hand-verified events
    # before testing the harness on top of them.
    assert was_member("TWTR", date(2022, 10, 31))
    assert not was_member("TWTR", TWTR_REMOVAL)
    assert not was_member("PLTR", date(2024, 9, 20))
    assert was_member("PLTR", PLTR_ADDITION)


def test_departed_member_is_held_before_and_never_after_its_real_removal():
    _index, formations = _pit_backtest()
    before = [f for f in formations if f.date.date() < TWTR_REMOVAL]
    after = [f for f in formations if f.date.date() >= TWTR_REMOVAL]
    assert before and after  # the replay genuinely straddles the event

    # While a member, TWTR's top-ranked constant puts it in the long leg
    # every single formation:
    assert all("TWTR" in f.long_tickers for f in before)
    # From the removal date on, it must never appear anywhere — leg or
    # eligible count — even though its (synthetic) prices keep existing:
    for f in after:
        assert "TWTR" not in f.long_tickers
        assert "TWTR" not in f.short_tickers


def test_future_member_does_not_leak_into_past_formations():
    # THE survivorship/leak direction: PLTR has price data and the
    # second-highest rank constant for the whole replay, but joined the
    # index only on 2024-09-23 — every formation before that date must
    # exclude it, and formations after must include it.
    _index, formations = _pit_backtest()
    before = [f for f in formations if f.date.date() < PLTR_ADDITION]
    after = [f for f in formations if f.date.date() >= PLTR_ADDITION]
    assert before and after

    for f in before:
        assert "PLTR" not in f.long_tickers
        assert "PLTR" not in f.short_tickers
    assert all("PLTR" in f.long_tickers for f in after)


def test_eligible_count_tracks_real_membership_through_both_events():
    _index, formations = _pit_backtest()
    for f in formations:
        d = f.date.date()
        expected = sum(1 for t in _PIT_TICKERS if was_member(t, d))
        assert f.n_eligible == expected


def test_signal_fn_is_never_shown_an_ineligible_ticker():
    # Structural guarantee: the history view's COLUMNS are already
    # membership-filtered before the signal function runs — a buggy or
    # adversarial signal could not rank an ineligible name even on purpose.
    seen: list[tuple[date, list[str]]] = []

    def spy_signal(view: CrossSectionalData) -> pd.Series:
        seen.append((view.close.index[-1].date(), list(view.close.columns)))
        return _pit_rank_signal(view)

    index = pd.bdate_range("2024-08-01", "2024-11-29")
    rng = np.random.default_rng(3)
    close = pd.DataFrame(
        {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, len(index))) for t in _PIT_TICKERS},
        index=index,
    )
    spec = _spec(signal_fn=spy_signal, rank_fraction=0.2, lookback_days=5, holding_days=10)
    run_cross_sectional_backtest(CrossSectionalData(close=close), spec, _config())

    assert seen
    for formation_day, columns in seen:
        assert "TWTR" not in columns  # long gone by 2024
        if formation_day < PLTR_ADDITION:
            assert "PLTR" not in columns
        else:
            assert "PLTR" in columns


# --- screen_cross_sectional_universe ------------------------------------


def test_screening_counts_the_declared_family_size_as_n_trials():
    close = _close_frame(
        {"A": 0.012, "B": 0.008, "C": 0.002, "D": -0.002, "E": -0.008, "F": -0.012},
        "2023-01-02",
        200,
    )
    data = CrossSectionalData(close=close)
    specs = [
        _spec(pattern_id="alpha", rank_fraction=0.34, holding_days=5),
        _spec(pattern_id="beta", rank_fraction=0.34, holding_days=21),
        # Deliberately unrunnable (needs open data that isn't there is an
        # error, so instead: lookback longer than the data) — it must STILL
        # count toward n_trials, or the correction would be gameable by
        # defining specs expected to fail.
        _spec(pattern_id="gamma", lookback_days=500),
    ]
    results = screen_cross_sectional_universe(data, specs, _config(), ALWAYS_MEMBER)

    assert {r.pattern_id for r in results} == {"alpha", "beta"}
    for r in results:
        assert r.deflated_sharpe.n_trials == 3
        assert r.n_trading_days >= 60
        assert np.isfinite(r.sharpe_annualized)
    # Sorted by Sharpe, best first.
    sharpes = [r.sharpe_annualized for r in results]
    assert sharpes == sorted(sharpes, reverse=True)


def test_screening_drops_replays_below_the_min_trading_days_floor():
    close = _close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 50)  # < 60 realized days
    results = screen_cross_sectional_universe(
        CrossSectionalData(close=close), [_spec()], _config(), ALWAYS_MEMBER
    )
    assert results == []


def test_screening_reports_formation_diagnostics():
    close = _close_frame(
        {"A": 0.012, "B": 0.008, "C": -0.008, "D": -0.012}, "2023-01-02", 150
    )
    results = screen_cross_sectional_universe(
        CrossSectionalData(close=close), [_spec(rank_fraction=0.5, holding_days=10)], _config(), ALWAYS_MEMBER
    )
    assert len(results) == 1
    r = results[0]
    assert r.n_formations > 0
    assert r.n_skipped_formations == 0
    assert r.avg_names_per_leg == pytest.approx(2.0)
    assert r.total_cost_drag > 0.0


# --- NON-EQUITY UNIVERSES: fixed_universe_membership ---------------------
# A bond/FX/commodity/crypto basket has no point-in-time index-membership
# concept, so was_member (the default gate) answers False for every one of
# its tickers. These lock in the named alternative.

# Deliberately real non-S&P instruments: every one of them is False under
# was_member on every date, which is the whole problem.
_BOND_ETFS = ["AGG", "BND", "LQD", "HYG", "TLT", "IEF", "SHY", "TIP", "EMB", "MUB"]


def test_fixed_universe_membership_admits_every_listed_ticker_on_every_date():
    is_member = fixed_universe_membership(_BOND_ETFS)
    # Dates spanning far outside any index-membership data window, in both
    # directions — "always eligible" must mean always, with no coverage
    # boundary of its own to silently answer False at.
    for on in (date(1990, 1, 1), date(2015, 1, 7), date(2024, 6, 3), date(2099, 12, 31)):
        for ticker in _BOND_ETFS:
            assert is_member(ticker, on) is True


def test_fixed_universe_membership_excludes_anything_not_in_the_basket():
    is_member = fixed_universe_membership(_BOND_ETFS)
    assert is_member("AAPL", date(2024, 6, 3)) is False
    assert is_member("agg", date(2024, 6, 3)) is False  # exact match, no case folding
    assert is_member("", date(2024, 6, 3)) is False


def test_fixed_universe_membership_rejects_an_empty_basket():
    # An empty basket would rebuild, exactly, the silent all-ineligible
    # failure this helper exists to prevent — so it fails at construction.
    with pytest.raises(ValueError, match="at least one ticker"):
        fixed_universe_membership([])


def test_fixed_universe_membership_makes_a_non_equity_family_actually_run():
    # End-to-end proof on the real reported blocker's shape: the SAME data
    # and spec that produce a fake-empty result under the default gate
    # (next test) produce a genuine replay under fixed_universe_membership.
    close = _close_frame(
        {t: 0.001 * (5 - i) for i, t in enumerate(_BOND_ETFS)}, "2023-01-02", 200
    )
    data = CrossSectionalData(close=close)
    spec = _spec(rank_fraction=0.3, lookback_days=20, holding_days=21)
    result = run_cross_sectional_backtest(
        data, spec, _config(min_names_per_leg=2), fixed_universe_membership(_BOND_ETFS)
    )
    assert result.status == "ok"
    assert result.n_zero_eligible_formations == 0
    assert all(f.n_eligible == len(_BOND_ETFS) for f in result.formations)
    formed = [f for f in result.formations if f.skipped_reason is None]
    assert formed and all(len(f.long_tickers) == 3 for f in formed)


# --- THE LOUD FAILURE MODE -----------------------------------------------
# Before this, a non-equity universe under the default was_member gate gave
# n_eligible=0 on every formation, status "no_valid_formations", a long
# series of exact 0.0 returns, and a bare [] from screening — visually
# identical to "ran fine, found nothing interesting". Confirmed live on a
# bond-ETF family 2026-08-26.


def _bond_family_under_the_default_gate():
    close = _close_frame(
        {t: 0.001 * (5 - i) for i, t in enumerate(_BOND_ETFS)}, "2023-01-02", 200
    )
    return CrossSectionalData(close=close), _spec(rank_fraction=0.3, lookback_days=20, holding_days=21)


def test_zero_eligible_on_every_formation_gets_its_own_status_and_count(caplog):
    data, spec = _bond_family_under_the_default_gate()
    with caplog.at_level(logging.ERROR, logger="app.services.research_lab.cross_sectional"):
        # membership_fn deliberately omitted — this IS the reported bug's
        # exact call shape.
        result = run_cross_sectional_backtest(data, spec, _config(min_names_per_leg=2))

    assert result.status == "no_eligible_universe"  # NOT "no_valid_formations"
    assert result.formations
    assert result.n_zero_eligible_formations == len(result.formations)
    assert all(f.n_eligible == 0 for f in result.formations)
    # And it is unmissable in the log, naming the actual fix.
    assert any(
        rec.levelno == logging.ERROR and "fixed_universe_membership" in rec.getMessage()
        for rec in caplog.records
    )


def test_screening_raises_when_the_whole_run_saw_no_eligible_universe():
    data, spec = _bond_family_under_the_default_gate()
    with pytest.raises(EmptyEligibleUniverseError, match="fixed_universe_membership"):
        screen_cross_sectional_universe(data, [spec], _config(min_names_per_leg=2))


def test_the_same_family_screens_normally_once_the_membership_gate_is_right():
    # The other half of the loud-failure contract: the fix makes the
    # exception go away rather than merely being loud about everything.
    data, spec = _bond_family_under_the_default_gate()
    results = screen_cross_sectional_universe(
        data, [spec], _config(min_names_per_leg=2), fixed_universe_membership(_BOND_ETFS)
    )
    assert len(results) == 1
    assert results[0].n_formations > 0


def test_legitimate_zero_formation_runs_stay_quiet_and_unchanged():
    # The judgment call, pinned: a universe that WAS eligible and simply
    # could not form legs is a real answer about a real universe, so it
    # keeps its old quiet "no_valid_formations" + empty list — no new status,
    # no exception. (These mirror test_min_names_per_leg_skips_formation and
    # test_overlapping_legs_are_rejected above, at screening level.)
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 200))

    too_few_names = run_cross_sectional_backtest(
        data, _spec(), _config(min_names_per_leg=5), ALWAYS_MEMBER
    )
    assert too_few_names.status == "no_valid_formations"
    assert too_few_names.n_zero_eligible_formations == 0
    assert screen_cross_sectional_universe(data, [_spec()], _config(min_names_per_leg=5), ALWAYS_MEMBER) == []

    # Three ranked names at rank_fraction 0.67 forces legs of 2 that would
    # overlap (same construction as test_overlapping_legs_are_rejected).
    three = CrossSectionalData(
        close=_close_frame({"A": 0.01, "B": 0.0, "C": -0.01}, "2024-01-01", 200)
    )
    overlapping = run_cross_sectional_backtest(
        three, _spec(rank_fraction=0.67), _config(), ALWAYS_MEMBER
    )
    assert overlapping.status == "no_valid_formations"
    assert overlapping.n_zero_eligible_formations == 0
    assert screen_cross_sectional_universe(
        three, [_spec(rank_fraction=0.67)], _config(), ALWAYS_MEMBER
    ) == []

    # Too little history to reach even one formation: no formations were
    # attempted, so the run-wide check must not fire either.
    thin = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 8))
    assert screen_cross_sectional_universe(thin, [_spec(lookback_days=10)], _config(), ALWAYS_MEMBER) == []


def test_a_partially_empty_universe_is_counted_but_does_not_raise():
    # Some formation dates eligible, some not — a real, non-fatal condition
    # (e.g. formations running off the front of membership coverage). It must
    # be COUNTED, but it is not the all-empty configuration error, so the
    # replay still runs and screening still returns results.
    close = _close_frame({"A": 0.012, "B": 0.008, "C": -0.008, "D": -0.012}, "2023-01-02", 200)
    cutover = close.index[80].date()
    half_gate = lambda _ticker, on: on >= cutover

    result = run_cross_sectional_backtest(
        CrossSectionalData(close=close), _spec(rank_fraction=0.5, holding_days=10), _config(), half_gate
    )
    assert result.status == "ok"
    assert 0 < result.n_zero_eligible_formations < len(result.formations)


def test_a_partially_empty_universe_that_never_forms_warns_without_raising(caplog):
    # The middle case: SOME formations had an eligible cross-section and none
    # of them could form legs. Not the all-empty configuration error (so no
    # new status and no exception), but the zero-eligible dates are still
    # counted and logged rather than vanishing.
    close = _close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 200)
    cutover = close.index[80].date()
    half_gate = lambda _ticker, on: on >= cutover
    with caplog.at_level(logging.WARNING, logger="app.services.research_lab.cross_sectional"):
        result = run_cross_sectional_backtest(
            CrossSectionalData(close=close), _spec(), _config(min_names_per_leg=5), half_gate
        )
    assert result.status == "no_valid_formations"
    assert 0 < result.n_zero_eligible_formations < len(result.formations)
    assert any(
        rec.levelno == logging.WARNING and "zero" in rec.getMessage() for rec in caplog.records
    )


# --- financing / borrow / carry cost (bps per YEAR held) -----------------
# The second, structurally distinct cost component: config.cost_bps is paid
# per unit of notional TRADED and scales with turnover; financing is paid
# per unit of notional HELD and scales with time.


def test_financing_cost_defaults_to_zero():
    assert DEFAULT_FINANCING_BPS_PER_YEAR == 0.0
    assert CrossSectionalConfig().financing_bps_per_year == 0.0
    assert FINANCING_DAYS_PER_YEAR == 365.0


def test_financing_unset_is_byte_identical_to_before_the_field_existed():
    # The critical no-regression constraint, asserted the same way the
    # delisting/cohort options were: the SAME fixture and expected values as
    # test_long_short_daily_returns_and_first_day_cost, run through an
    # EXPLICIT financing_bps_per_year=0.0 config as well as the implicit
    # default, must reproduce the pre-change numbers exactly.
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 40))
    implicit = run_cross_sectional_backtest(data, _spec(), _config(), ALWAYS_MEMBER)
    explicit = run_cross_sectional_backtest(
        data, _spec(), _config(financing_bps_per_year=0.0), ALWAYS_MEMBER
    )

    pd.testing.assert_series_equal(implicit.daily_returns, explicit.daily_returns)
    assert implicit.daily_returns.iloc[0] == pytest.approx(0.02 - 0.001)
    assert implicit.daily_returns.iloc[1] == pytest.approx(0.02)
    assert implicit.total_cost == pytest.approx(0.001)
    assert implicit.total_financing_cost == 0.0
    assert explicit.total_financing_cost == 0.0
    # Not approx: 0.0 financing must be a literal no-op on the return
    # stream, not a floating-point subtraction that happens to round back.
    assert implicit.daily_returns.to_list() == explicit.daily_returns.to_list()


def test_financing_cost_is_hand_computed_per_calendar_day_held():
    # Exactly one formation, hand-checkable end to end.
    # bdate_range("2024-01-01", 16): index[10] = Mon 2024-01-15 (the only
    # formation, lookback_days=10), hold runs to index[15] = Mon 2024-01-22.
    # Book: A long (w=1.0), B short (w=1.0) -> GROSS notional held = 2.0.
    # Rate 100 bps/yr -> 0.01 per unit of gross notional per YEAR.
    # Realized days 11,12,13,14 are one calendar day each; day 15 is a
    # Monday, three calendar days after Friday's close. 4*1 + 3 = 7 calendar
    # days, which is exactly index[15] - index[10].
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 16))
    result = run_cross_sectional_backtest(
        data, _spec(), _config(financing_bps_per_year=100.0), ALWAYS_MEMBER
    )
    index = data.close.index
    assert [f.date for f in result.formations] == [index[10]]

    per_calendar_day = 0.01 * 2.0 / 365.0  # rate * gross notional / days per year

    # First realized day: gross 2% minus the 5bps * turnover-2.0 trade cost
    # (0.001) minus ONE calendar day of financing.
    assert result.daily_returns.loc[index[11]] == pytest.approx(0.02 - 0.001 - per_calendar_day)
    # An ordinary mid-week day: no trade cost, one day of financing.
    assert result.daily_returns.loc[index[13]] == pytest.approx(0.02 - per_calendar_day)
    # Monday: THREE calendar days of financing — a book held over a weekend
    # really does pay weekend borrow.
    assert result.daily_returns.loc[index[15]] == pytest.approx(0.02 - 3.0 * per_calendar_day)

    # Total over the hold == rate * gross * (calendar days held) / 365.
    assert (index[15] - index[10]).days == 7
    assert result.total_financing_cost == pytest.approx(0.01 * 2.0 * 7.0 / 365.0)
    assert result.total_financing_cost == pytest.approx(0.00038356164383561645)
    # ...and it is reported SEPARATELY, never folded into the trade cost.
    assert result.total_cost == pytest.approx(0.001)


def test_financing_cost_scales_linearly_with_the_holding_period():
    # Same single formation at index[10] = Mon 2024-01-15 and the same
    # 2.0 gross book, held twice as long: holding_days=5 runs to index[15]
    # (Mon 2024-01-22, 7 calendar days), holding_days=10 runs to index[20]
    # (Mon 2024-01-29, 14 calendar days). Double the time held -> exactly
    # double the financing, while the ONE-OFF trade cost is unchanged.
    short_hold = run_cross_sectional_backtest(
        CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 16)),
        _spec(holding_days=5),
        _config(financing_bps_per_year=100.0),
        ALWAYS_MEMBER,
    )
    long_hold = run_cross_sectional_backtest(
        CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 21)),
        _spec(holding_days=10),
        _config(financing_bps_per_year=100.0),
        ALWAYS_MEMBER,
    )
    assert len(short_hold.formations) == len(long_hold.formations) == 1

    assert short_hold.total_financing_cost == pytest.approx(0.01 * 2.0 * 7.0 / 365.0)
    assert long_hold.total_financing_cost == pytest.approx(0.01 * 2.0 * 14.0 / 365.0)
    assert long_hold.total_financing_cost == pytest.approx(2.0 * short_hold.total_financing_cost)
    # Time-based, not trade-based: the trade cost is identical either way.
    assert short_hold.total_cost == pytest.approx(long_hold.total_cost) == pytest.approx(0.001)


def test_financing_scales_linearly_with_the_rate_too():
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 16))
    base = run_cross_sectional_backtest(
        data, _spec(), _config(financing_bps_per_year=100.0), ALWAYS_MEMBER
    )
    tripled = run_cross_sectional_backtest(
        data, _spec(), _config(financing_bps_per_year=300.0), ALWAYS_MEMBER
    )
    assert tripled.total_financing_cost == pytest.approx(3.0 * base.total_financing_cost)


def test_financing_and_trade_costs_move_in_opposite_directions_as_holds_lengthen():
    # The reason the two cannot be collapsed into one number. Over the SAME
    # data, a longer hold reforms less often (fewer turnover charges) but
    # finances for the same wall-clock time — so per calendar day held, the
    # financing rate is identical while the trade cost falls.
    rng = np.random.default_rng(17)
    index = pd.bdate_range("2023-01-02", periods=260)
    close = pd.DataFrame(
        {t: 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.012, len(index))) for t in "ABCDEFGH"},
        index=index,
    )
    data = CrossSectionalData(close=close)

    def trailing(view: CrossSectionalData) -> pd.Series:
        return view.close.iloc[-10:].mean()

    config = _config(financing_bps_per_year=200.0)
    quick = run_cross_sectional_backtest(
        data, _spec(signal_fn=trailing, lookback_days=20, holding_days=5, rank_fraction=0.25),
        config, ALWAYS_MEMBER,
    )
    slow = run_cross_sectional_backtest(
        data, _spec(signal_fn=trailing, lookback_days=20, holding_days=40, rank_fraction=0.25),
        config, ALWAYS_MEMBER,
    )

    # Trading 8x more often costs far more in turnover...
    assert quick.total_cost > slow.total_cost
    # ...but financing per calendar day actually held is the same rate on
    # the same 2.0 gross book, whatever the holding period.
    quick_days = (quick.daily_returns.index[-1] - quick.formations[0].date).days
    slow_days = (slow.daily_returns.index[-1] - slow.formations[0].date).days
    assert quick.total_financing_cost / quick_days == pytest.approx(
        slow.total_financing_cost / slow_days
    )
    assert quick.total_financing_cost / quick_days == pytest.approx(0.02 * 2.0 / 365.0)


def test_financing_is_not_charged_on_a_flat_book():
    # A skipped formation holds nothing, so it finances nothing — even at an
    # absurd rate. (Gross notional held is 0.0, see _replay_sleeve.)
    data = CrossSectionalData(close=_close_frame({"A": 0.01, "B": -0.01}, "2024-01-01", 40))
    result = run_cross_sectional_backtest(
        data, _spec(), _config(min_names_per_leg=5, financing_bps_per_year=10_000.0), ALWAYS_MEMBER
    )
    assert result.status == "no_valid_formations"
    assert all(f.skipped_reason is not None for f in result.formations)
    assert result.total_financing_cost == 0.0
    assert (result.daily_returns == 0.0).all()


def test_financing_charges_the_real_gross_notional_of_a_hedged_book():
    # long_universe_hedged nets a long leg against an equal-weighted short of
    # the whole universe, so a name in BOTH sides nets down and the book's
    # gross notional is genuinely below 2.0. Financing must charge what is
    # actually held, not a presumed 2.0.
    # A/B/C/D, top-quarter long leg = A alone (w=+1.0), universe hedge =
    # -0.25 each: net A = +0.75, B/C/D = -0.25 -> gross = 0.75 + 3*0.25 = 1.5.
    data = CrossSectionalData(
        close=_close_frame({"A": 0.04, "B": 0.02, "C": 0.0, "D": -0.02}, "2024-01-01", 16)
    )
    result = run_cross_sectional_backtest(
        data,
        _spec(portfolio="long_universe_hedged", rank_fraction=0.25),
        _config(financing_bps_per_year=100.0),
        ALWAYS_MEMBER,
    )
    assert len(result.formations) == 1
    assert result.total_financing_cost == pytest.approx(0.01 * 1.5 * 7.0 / 365.0)


def test_screening_reports_financing_drag_separately_from_trade_cost():
    close = _close_frame({"A": 0.012, "B": 0.008, "C": -0.008, "D": -0.012}, "2023-01-02", 150)
    data = CrossSectionalData(close=close)
    spec = _spec(rank_fraction=0.5, holding_days=10)

    free = screen_cross_sectional_universe(data, [spec], _config(), ALWAYS_MEMBER)
    financed = screen_cross_sectional_universe(
        data, [spec], _config(financing_bps_per_year=250.0), ALWAYS_MEMBER
    )
    assert len(free) == len(financed) == 1

    # Unset: exactly zero, and every other reported number is untouched.
    assert free[0].total_financing_drag == 0.0
    # Set: a positive drag of its own, the turnover cost UNCHANGED (the two
    # are never collapsed), and a strictly worse Sharpe for paying it.
    assert financed[0].total_financing_drag > 0.0
    assert financed[0].total_cost_drag == pytest.approx(free[0].total_cost_drag)
    assert financed[0].sharpe_annualized < free[0].sharpe_annualized
