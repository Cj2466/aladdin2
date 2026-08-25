import time

import numpy as np
import pandas as pd
import pytest

from app import dependencies
from app.services.research_lab import metrics
from app.services.research_lab.engine import (
    WalkForwardConfig,
    WalkForwardState,
    apply_zscore_threshold_rule,
    run_walk_forward,
    step_one_day,
)
from app.services.research_lab.momentum import (
    apply_momentum_threshold_rule,
    build_momentum_raw_data,
    fit_momentum_window,
    realize_momentum_return,
    run_momentum_backtest,
)
from app.services.risk.errors import MissingTickerDataError


def _prices_fn_from_frame(frame: pd.DataFrame):
    def prices_fn(tickers, start, end):
        present = [t for t in tickers if t in frame.columns]
        missing = [t for t in tickers if t not in frame.columns]
        return frame[present], missing

    return prices_fn


def _simulate_trend_price(n: int, drift: float, noise_std: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    log_price = np.cumsum(rng.normal(drift, noise_std, n))
    return 100 * np.exp(log_price)


# --- Engine widening regression: proves decide_position_fn/direction_labels
# are additive, not breaking — every existing OU-pairs caller/test needs
# zero changes. -----------------------------------------------------------


def test_step_one_day_defaults_to_zscore_threshold_rule_when_no_decide_fn_given():
    n = 300
    fit_window_days = 100
    rng = np.random.default_rng(11)
    log_a = np.cumsum(rng.normal(0, 0.01, n))
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    raw_data = pd.DataFrame({"log_a": log_a, "log_b": log_a}, index=dates)  # unused fields here, just shape

    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=10.0)
    state = WalkForwardState()
    window = raw_data.iloc[0:fit_window_days]
    day_row = raw_data.iloc[fit_window_days]

    def dummy_fit(_window):
        from app.services.research_lab.engine import StrategyFit

        return StrategyFit(is_valid=True, z_score=-2.5, fit_quality="strong", params={})

    def dummy_return(_row, _fit):
        return 0.01

    state_default, day_result_default, _ = step_one_day(window, day_row, dummy_fit, dummy_return, state, config)
    state_explicit, day_result_explicit, _ = step_one_day(
        window, day_row, dummy_fit, dummy_return, state, config, apply_zscore_threshold_rule, ("long_spread", "short_spread")
    )
    assert day_result_default.position == day_result_explicit.position == 1  # z=-2.5 -> mean-reversion long
    assert state_default == state_explicit


def test_step_one_day_uses_custom_decide_position_fn_when_given():
    from app.services.research_lab.engine import StrategyFit

    n = 300
    fit_window_days = 100
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    raw_data = pd.DataFrame({"x": np.zeros(n)}, index=dates)
    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=10.0)
    state = WalkForwardState()
    window = raw_data.iloc[0:fit_window_days]
    day_row = raw_data.iloc[fit_window_days]

    def dummy_fit(_window):
        return StrategyFit(is_valid=True, z_score=0.1, fit_quality="strong", params={})

    def dummy_return(_row, _fit):
        return 0.0

    def always_long(*_args):
        return 1

    _state, day_result, _trade = step_one_day(
        window, day_row, dummy_fit, dummy_return, state, config, always_long, ("long", "short")
    )
    assert day_result.position == 1  # would be 0 under the default mean-reversion rule (z=0.1 is below entry_z)


# --- Unit: fit_momentum_window --------------------------------------------


def test_fit_momentum_window_flat_series_is_invalid():
    window = pd.DataFrame({"log_price": [4.6] * 90})
    fit = fit_momentum_window(window)
    assert fit.is_valid is False
    assert fit.z_score is None


def test_fit_momentum_window_significant_uptrend_is_valid_and_positive():
    log_price = np.cumsum(np.random.default_rng(42).normal(0.003, 0.0005, 90))
    fit = fit_momentum_window(pd.DataFrame({"log_price": log_price}))
    assert fit.is_valid is True
    assert fit.z_score is not None and fit.z_score > 0
    assert fit.fit_quality == "strong"


def test_fit_momentum_window_significant_downtrend_is_valid_and_negative():
    log_price = np.cumsum(np.random.default_rng(43).normal(-0.003, 0.0005, 90))
    fit = fit_momentum_window(pd.DataFrame({"log_price": log_price}))
    assert fit.is_valid is True
    assert fit.z_score is not None and fit.z_score < 0
    assert fit.fit_quality == "strong"


def test_fit_momentum_window_weak_trend_is_invalid():
    # Pure i.i.d. noise around a flat mean, no real drift — seed=2 verified
    # to reliably land p > 0.05 (r^2 ~ 0.0004).
    log_price = 4.6 + np.random.default_rng(2).normal(0, 0.01, 90)
    fit = fit_momentum_window(pd.DataFrame({"log_price": log_price}))
    assert fit.is_valid is False
    assert fit.z_score is None
    assert fit.fit_quality == "weak"


# --- Unit: apply_momentum_threshold_rule — hand-derived truth table,
# structural mirror of test_apply_zscore_threshold_rule but every
# comparison direction flipped (trend-following bets WITH the signal). ----


@pytest.mark.parametrize(
    "momentum_z,is_valid,prev_position,entry_z,exit_z,expected",
    [
        (None, False, 0, 2.0, 0.0, 0),
        (0.0, False, 1, 2.0, 0.0, 0),
        (2.5, True, 0, 2.0, 0.0, 1),  # strong positive momentum -> enter LONG (opposite of OU's -2.5->long)
        (-2.5, True, 0, 2.0, 0.0, -1),  # strong negative momentum -> enter SHORT (opposite of OU's 2.5->short)
        (0.5, True, 0, 2.0, 0.0, 0),
        (0.5, True, 1, 2.0, 0.0, 1),  # still trending up, stay long
        (-0.5, True, 1, 2.0, 0.0, 0),  # trend weakened past zero, close long
        (-0.5, True, -1, 2.0, 0.0, -1),  # still trending down, stay short
        (0.5, True, -1, 2.0, 0.0, 0),  # trend weakened past zero, close short
    ],
)
def test_apply_momentum_threshold_rule(momentum_z, is_valid, prev_position, entry_z, exit_z, expected):
    assert apply_momentum_threshold_rule(momentum_z, is_valid, prev_position, entry_z, exit_z) == expected


# --- The sign-convention P&L proof: the test a naive "it traded" check
# would miss. A backwards implementation shows negative realized P&L on
# BOTH trends (systematically fading real trends) instead of positive on
# both. ----------------------------------------------------------------


def test_momentum_sign_convention_is_not_inverted():
    n = 300
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    config = WalkForwardConfig(fit_window_days=90, entry_z=2.0, exit_z=0.0, cost_bps=5.0)

    price_up = _simulate_trend_price(n, drift=0.003, noise_std=0.001, seed=42)
    frame_up = pd.DataFrame({"TICK": price_up}, index=dates)
    result_up = run_momentum_backtest("TICK", 5, _prices_fn_from_frame(frame_up), config)
    assert result_up.status == "ok"
    positions_up = [d.position for d in result_up.day_results]
    raw_returns_up = [d.raw_return for d in result_up.day_results]
    assert np.mean(positions_up) > 0.5, "uptrend should be predominantly held LONG"
    assert np.mean(raw_returns_up) > 0, "long exposure to an uptrend must realize positive P&L"

    price_down = _simulate_trend_price(n, drift=-0.003, noise_std=0.001, seed=43)
    frame_down = pd.DataFrame({"TICK": price_down}, index=dates)
    result_down = run_momentum_backtest("TICK", 5, _prices_fn_from_frame(frame_down), config)
    assert result_down.status == "ok"
    positions_down = [d.position for d in result_down.day_results]
    raw_returns_down = [d.raw_return for d in result_down.day_results]
    assert np.mean(positions_down) < -0.5, "downtrend should be predominantly held SHORT"
    # The critical assertion: NOT negative. A backwards sign would short
    # the downtrend's price moves in the wrong direction, realizing
    # negative P&L here exactly like it would on the uptrend above.
    assert np.mean(raw_returns_down) > 0, "short exposure to a downtrend must realize positive P&L, not negative"


# --- Look-ahead-bias proof — structural mirror of
# test_day_n_decision_is_blind_to_day_n_shock. --------------------------


def test_momentum_day_n_decision_is_blind_to_day_n_shock():
    n = 500
    fit_window_days = 90
    shock_index = 300

    rng = np.random.default_rng(7)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    price = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))

    frame_v1 = pd.DataFrame({"TICK": price}, index=dates)
    frame_v2 = frame_v1.copy()
    shock_date = dates[shock_index]
    frame_v2.loc[shock_date, "TICK"] *= 1.5

    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=5.0)
    result_v1 = run_momentum_backtest("TICK", 5, _prices_fn_from_frame(frame_v1), config)
    result_v2 = run_momentum_backtest("TICK", 5, _prices_fn_from_frame(frame_v2), config)

    v1_by_date = {d.date: d for d in result_v1.day_results}
    v2_by_date = {d.date: d for d in result_v2.day_results}
    dates_through_shock = sorted(d for d in v1_by_date if d <= shock_date)
    assert len(dates_through_shock) > 10

    for d in dates_through_shock:
        r1, r2 = v1_by_date[d], v2_by_date[d]
        assert r1.position == r2.position, f"position differs at {d} — day-N decision saw day-N's own shock"
        if r1.z_score is None:
            assert r2.z_score is None
        else:
            assert r2.z_score == pytest.approx(r1.z_score)

    assert v1_by_date[shock_date].raw_return != pytest.approx(v2_by_date[shock_date].raw_return)


# --- step_one_day vs run_walk_forward regression, momentum-flavored ------


def _drive_step_one_day_manually_momentum(raw_data, config):
    state = WalkForwardState()
    day_results = []
    trades = []
    n = len(raw_data)
    for t in range(config.fit_window_days, n):
        window = raw_data.iloc[t - config.fit_window_days : t]
        day_row = raw_data.iloc[t]
        state, day_result, closed_trade = step_one_day(
            window,
            day_row,
            fit_momentum_window,
            realize_momentum_return,
            state,
            config,
            apply_momentum_threshold_rule,
            ("long", "short"),
        )
        day_results.append(day_result)
        if closed_trade is not None:
            trades.append(closed_trade)
    return day_results, trades


def _assert_day_results_equal(a: list, b: list):
    assert len(a) == len(b)
    for d1, d2 in zip(a, b, strict=True):
        assert d1.date == d2.date
        assert d1.position == d2.position
        assert d1.z_score == d2.z_score or (d1.z_score is None and d2.z_score is None)
        assert d1.raw_return == pytest.approx(d2.raw_return)
        assert d1.net_return == pytest.approx(d2.net_return)
        assert d1.equity == pytest.approx(d2.equity)


def test_step_one_day_matches_run_walk_forward_on_trend():
    n = 400
    fit_window_days = 90
    price = _simulate_trend_price(n, drift=0.001, noise_std=0.005, seed=123)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    raw_data = build_momentum_raw_data(pd.DataFrame({"TICK": price}, index=dates), "TICK")
    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=5.0)

    batch_result = run_walk_forward(
        raw_data, config, fit_momentum_window, realize_momentum_return,
        decide_position_fn=apply_momentum_threshold_rule, direction_labels=("long", "short"),
    )
    manual_days, manual_trades = _drive_step_one_day_manually_momentum(raw_data, config)

    _assert_day_results_equal(batch_result.day_results, manual_days)
    closed_batch_trades = [t for t in batch_result.trades if not t.still_open]
    assert len(closed_batch_trades) == len(manual_trades)


def test_step_one_day_matches_run_walk_forward_on_random_walk_momentum():
    n = 400
    fit_window_days = 90
    rng = np.random.default_rng(2024)
    price = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    raw_data = build_momentum_raw_data(pd.DataFrame({"TICK": price}, index=dates), "TICK")
    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=5.0)

    batch_result = run_walk_forward(
        raw_data, config, fit_momentum_window, realize_momentum_return,
        decide_position_fn=apply_momentum_threshold_rule, direction_labels=("long", "short"),
    )
    manual_days, manual_trades = _drive_step_one_day_manually_momentum(raw_data, config)

    _assert_day_results_equal(batch_result.day_results, manual_days)
    closed_batch_trades = [t for t in batch_result.trades if not t.still_open]
    assert len(closed_batch_trades) == len(manual_trades)


# --- Honesty checks --------------------------------------------------------


def test_synthetic_trend_produces_positive_out_of_sample_sharpe():
    n = 300
    config = WalkForwardConfig(fit_window_days=90, entry_z=2.0, exit_z=0.0, cost_bps=5.0)
    price = _simulate_trend_price(n, drift=0.003, noise_std=0.001, seed=42)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    frame = pd.DataFrame({"TICK": price}, index=dates)

    result = run_momentum_backtest("TICK", 5, _prices_fn_from_frame(frame), config)
    assert result.status == "ok"
    assert result.pct_days_mean_reverting > 0.5
    assert len(result.trades) > 0

    net_returns = pd.Series([d.net_return for d in result.day_results])
    assert metrics.sharpe_ratio(net_returns) > 0


def test_independent_random_walks_do_not_systematically_profit_momentum():
    """Mirrors the pairs strategy's identical honesty check — momentum has
    its own significance gate (unlike pairs' structural gate), but that
    gate alone doesn't guarantee zero spurious "significant" windows on a
    750-day series; the walk-forward realized result must still not be
    systematically fooled into profit."""
    n = 750
    config = WalkForwardConfig(fit_window_days=90, entry_z=2.0, exit_z=0.0, cost_bps=5.0)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)

    sharpes = []
    for seed in range(20):
        rng = np.random.default_rng(2000 + seed)
        price = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        frame = pd.DataFrame({"TICK": price}, index=dates)
        result = run_momentum_backtest("TICK", 5, _prices_fn_from_frame(frame), config)
        if not result.day_results:
            continue
        net_returns = pd.Series([d.net_return for d in result.day_results])
        sharpes.append(metrics.sharpe_ratio(net_returns))

    assert len(sharpes) >= 15
    positive_fraction = sum(1 for s in sharpes if s > 0) / len(sharpes)
    assert positive_fraction < 0.85, "walk-forward evaluation looks systematically fooled by noise"
    assert np.mean(sharpes) < 1.0, "no wild systematic positive bias on pure noise"


# --- Error/status semantics ------------------------------------------------


def test_momentum_missing_ticker_raises():
    def prices_fn(tickers, start, end):
        return pd.DataFrame({"OTHER": [100.0] * 300}), ["TICK"]

    config = WalkForwardConfig(fit_window_days=60, entry_z=2.0, exit_z=0.0, cost_bps=5.0)
    with pytest.raises(MissingTickerDataError):
        run_momentum_backtest("TICK", 5, prices_fn, config)


def test_momentum_insufficient_history_returns_status_not_error():
    n = 50
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    frame = pd.DataFrame({"TICK": np.linspace(100, 105, n)}, index=dates)
    config = WalkForwardConfig(fit_window_days=60, entry_z=2.0, exit_z=0.0, cost_bps=5.0)

    result = run_momentum_backtest("TICK", 5, _prices_fn_from_frame(frame), config)
    assert result.status == "insufficient_history"
    assert result.day_results == []


def test_momentum_backtest_completes_quickly_for_a_decade_of_data():
    n = 2520
    rng = np.random.default_rng(99)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    price = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    frame = pd.DataFrame({"TICK": price}, index=dates)
    config = WalkForwardConfig(fit_window_days=90, entry_z=2.0, exit_z=0.0, cost_bps=5.0)

    start = time.monotonic()
    result = run_momentum_backtest("TICK", 10, _prices_fn_from_frame(frame), config)
    elapsed = time.monotonic() - start

    assert result.status in ("ok", "not_trending")
    assert elapsed < 3.0


# --- Point-in-time S&P 500 membership disclosure. Synthetic prices under a
# REAL ticker symbol: the membership lookup is a pure function of the symbol
# and the replayed dates, so no network or real price data is needed to
# prove the wiring works. ----------------------------------------------------


def test_momentum_backtest_warns_when_the_replay_predates_index_membership():
    # PLTR really joined the S&P 500 on 2024-09-23. A 5-year replay is
    # therefore mostly a period this system's own screening universe could
    # never have surfaced it in — the survivorship/inclusion bias that
    # SCREENING_UNIVERSE's today-only snapshot otherwise hides.
    n = 900
    dates = pd.bdate_range(end=pd.Timestamp("2026-06-01"), periods=n)
    frame = pd.DataFrame({"PLTR": _simulate_trend_price(n, 0.001, 0.01, seed=7)}, index=dates)
    config = WalkForwardConfig(fit_window_days=90, entry_z=2.0, exit_z=0.0, cost_bps=5.0)

    result = run_momentum_backtest("PLTR", 5, _prices_fn_from_frame(frame), config)
    assert any("PLTR joined the S&P 500 on 2024-09-23" in w for w in result.warnings)


def test_momentum_backtest_emits_no_membership_warning_for_a_continuous_member():
    # Same construction, a ticker that was an index member across the whole
    # replay — proves the warning is data-driven, not emitted for every run.
    n = 400
    dates = pd.bdate_range(end=pd.Timestamp("2026-06-01"), periods=n)
    frame = pd.DataFrame({"AAPL": _simulate_trend_price(n, 0.001, 0.01, seed=7)}, index=dates)
    config = WalkForwardConfig(fit_window_days=90, entry_z=2.0, exit_z=0.0, cost_bps=5.0)

    result = run_momentum_backtest("AAPL", 5, _prices_fn_from_frame(frame), config)
    assert result.warnings == []


def test_momentum_membership_warning_survives_the_insufficient_history_path():
    # The early return must carry the disclosure too — a too-short result is
    # still a result a user reads. This window straddles PLTR's 2024-09-23
    # addition while being too thin to score.
    n = 50
    dates = pd.bdate_range(end=pd.Timestamp("2024-10-01"), periods=n)
    frame = pd.DataFrame({"PLTR": np.linspace(100, 105, n)}, index=dates)
    config = WalkForwardConfig(fit_window_days=10, entry_z=2.0, exit_z=0.0, cost_bps=5.0)

    result = run_momentum_backtest("PLTR", 5, _prices_fn_from_frame(frame), config)
    assert result.status == "insufficient_history"
    assert any("PLTR joined the S&P 500 on 2024-09-23" in w for w in result.warnings)


# --- Endpoint ---------------------------------------------------------------


def test_momentum_backtest_requires_auth(client):
    response = client.post("/api/research-lab/momentum-backtest", json={"ticker": "AAPL"})
    assert response.status_code == 401


def test_momentum_backtest_endpoint_caches_repeat_request(client, register_and_verify, canned_prices, monkeypatch):
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)
    register_and_verify(client)

    payload = {"ticker": "AAPL", "fit_window_days": 100}
    response1 = client.post("/api/research-lab/momentum-backtest", json=payload)
    assert response1.status_code == 200, response1.text
    assert response1.json()["cached"] is False
    assert response1.json()["strategy_name"] == "momentum_v1"
    assert response1.json()["ticker_a"] == response1.json()["ticker_b"] == "AAPL"

    response2 = client.post("/api/research-lab/momentum-backtest", json=payload)
    assert response2.status_code == 200
    assert response2.json()["cached"] is True


def test_momentum_backtest_ticker_normalized_and_validated(client, register_and_verify):
    register_and_verify(client)
    response = client.post("/api/research-lab/momentum-backtest", json={"ticker": ""})
    assert response.status_code == 422
