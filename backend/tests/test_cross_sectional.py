from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.cross_sectional import (
    MAX_WEIGHT_MULTIPLE,
    CrossSectionalConfig,
    CrossSectionalData,
    CrossSectionalSpec,
    _leg_weighted_return,
    _leg_weights,
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
