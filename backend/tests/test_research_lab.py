import time

import numpy as np
import pandas as pd
import pytest

from app import dependencies
from app.services.research_lab import metrics
from app.services.research_lab.engine import (
    DayResult,
    Trade,
    WalkForwardConfig,
    WalkForwardState,
    apply_zscore_threshold_rule,
    run_walk_forward,
    step_one_day,
)
from app.services.research_lab.ou_pairs import (
    build_pairs_raw_data,
    fit_ou_pairs_window,
    realize_pairs_return,
    run_pairs_backtest,
)
from app.services.risk.errors import MissingTickerDataError


def _prices_fn_from_frame(frame: pd.DataFrame):
    def prices_fn(tickers, start, end):
        present = [t for t in tickers if t in frame.columns]
        missing = [t for t in tickers if t not in frame.columns]
        return frame[present], missing

    return prices_fn


def _simulate_ou_spread(n: int, theta: float, mu: float, sigma: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    spread = np.empty(n)
    spread[0] = mu
    for t in range(1, n):
        spread[t] = spread[t - 1] + theta * (mu - spread[t - 1]) + sigma * rng.normal()
    return spread


# --- Unit: threshold state machine ------------------------------------------


@pytest.mark.parametrize(
    "z_score,is_valid,prev_position,entry_z,exit_z,expected",
    [
        (None, False, 0, 2.0, 0.0, 0),
        (0.0, False, 1, 2.0, 0.0, 0),  # invalid fit forces flat regardless of prior position
        (-2.5, True, 0, 2.0, 0.0, 1),  # enter long spread
        (2.5, True, 0, 2.0, 0.0, -1),  # enter short spread
        (0.5, True, 0, 2.0, 0.0, 0),  # no entry signal, stay flat
        (-0.5, True, 1, 2.0, 0.0, 1),  # still below exit threshold, stay long
        (0.5, True, 1, 2.0, 0.0, 0),  # crossed exit threshold, close long
        (0.5, True, -1, 2.0, 0.0, -1),  # still above exit threshold, stay short
        (-0.5, True, -1, 2.0, 0.0, 0),  # crossed exit threshold, close short
    ],
)
def test_apply_zscore_threshold_rule(z_score, is_valid, prev_position, entry_z, exit_z, expected):
    assert apply_zscore_threshold_rule(z_score, is_valid, prev_position, entry_z, exit_z) == expected


# --- Unit: metrics ------------------------------------------------------------


def test_sharpe_ratio_hand_computed():
    returns = pd.Series([0.01, -0.005, 0.02, 0.0, -0.01])
    expected = returns.mean() / returns.std(ddof=1) * np.sqrt(252)
    assert metrics.sharpe_ratio(returns) == pytest.approx(expected)


def test_sharpe_ratio_zero_std_returns_zero():
    assert metrics.sharpe_ratio(pd.Series([0.0, 0.0, 0.0])) == 0.0


def test_max_drawdown_hand_computed():
    equity = pd.Series([1.0, 1.1, 0.9, 1.05, 0.8])
    expected = (0.8 / 1.1) - 1.0
    assert metrics.max_drawdown(equity) == pytest.approx(expected)


def test_hit_rate_only_counts_closed_trades():
    trades = [
        Trade(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-05"), "long_spread", 4, 0.02, False),
        Trade(pd.Timestamp("2020-02-01"), pd.Timestamp("2020-02-05"), "short_spread", 4, -0.01, False),
        Trade(pd.Timestamp("2020-03-01"), None, "long_spread", 2, 0.05, True),  # open — excluded
    ]
    assert metrics.hit_rate(trades) == pytest.approx(0.5)


def test_hit_rate_no_closed_trades_returns_none():
    trades = [Trade(pd.Timestamp("2020-01-01"), None, "long_spread", 1, 0.0, True)]
    assert metrics.hit_rate(trades) is None


def test_exposure_pct_hand_computed():
    day_results = [
        DayResult(pd.Timestamp("2020-01-01"), 0, None, 0.0, 0.0, 0.0, 1.0),
        DayResult(pd.Timestamp("2020-01-02"), 1, 1.0, 0.01, 0.001, 0.009, 1.009),
        DayResult(pd.Timestamp("2020-01-03"), 1, 0.5, 0.0, 0.0, 0.0, 1.009),
        DayResult(pd.Timestamp("2020-01-04"), 0, 0.0, 0.0, 0.001, -0.001, 1.008),
    ]
    assert metrics.exposure_pct(day_results) == pytest.approx(0.5)


def test_total_cost_drag_hand_computed():
    day_results = [
        DayResult(pd.Timestamp("2020-01-01"), 1, 1.0, 0.01, 0.001, 0.009, 1.009),
        DayResult(pd.Timestamp("2020-01-02"), 0, 0.0, 0.0, 0.001, -0.001, 1.008),
    ]
    assert metrics.total_cost_drag(day_results) == pytest.approx(0.002)


# --- Unit: fit_ou_pairs_window degenerate handling ----------------------------


def test_fit_ou_pairs_window_flat_series_is_invalid():
    window = pd.DataFrame({"log_a": [1.0] * 70, "log_b": [2.0] * 70})
    fit = fit_ou_pairs_window(window)
    assert fit.is_valid is False
    assert fit.z_score is None


# --- run_pairs_backtest error/status semantics --------------------------------


def test_missing_ticker_raises():
    def prices_fn(tickers, start, end):
        return pd.DataFrame({"A": [100.0] * 300}), ["B"]

    config = WalkForwardConfig(fit_window_days=60, entry_z=2.0, exit_z=0.0, cost_bps=10.0)
    with pytest.raises(MissingTickerDataError):
        run_pairs_backtest("A", "B", 5, prices_fn, config)


def test_insufficient_history_returns_status_not_error():
    n = 50
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    frame = pd.DataFrame({"A": np.linspace(100, 105, n), "B": np.linspace(200, 210, n)}, index=dates)
    config = WalkForwardConfig(fit_window_days=60, entry_z=2.0, exit_z=0.0, cost_bps=10.0)

    result = run_pairs_backtest("A", "B", 5, _prices_fn_from_frame(frame), config)
    assert result.status == "insufficient_history"
    assert result.day_results == []


# --- A: look-ahead-bias proof (the most important test) ----------------------


def test_day_n_decision_is_blind_to_day_n_shock():
    n = 500
    fit_window_days = 60
    shock_index = 300

    rng = np.random.default_rng(7)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    price_a = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    price_b = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))

    frame_v1 = pd.DataFrame({"A": price_a, "B": price_b}, index=dates)
    frame_v2 = frame_v1.copy()
    shock_date = dates[shock_index]
    frame_v2.loc[shock_date, "B"] *= 1.5  # a single day's price shock, only in v2

    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=10.0)
    result_v1 = run_pairs_backtest("A", "B", 5, _prices_fn_from_frame(frame_v1), config)
    result_v2 = run_pairs_backtest("A", "B", 5, _prices_fn_from_frame(frame_v2), config)

    v1_by_date = {d.date: d for d in result_v1.day_results}
    v2_by_date = {d.date: d for d in result_v2.day_results}
    dates_through_shock = sorted(d for d in v1_by_date if d <= shock_date)
    assert len(dates_through_shock) > 10  # sanity: the shock day is actually reached by the walk-forward loop

    for d in dates_through_shock:
        r1, r2 = v1_by_date[d], v2_by_date[d]
        assert r1.position == r2.position, f"position differs at {d} — day-N decision saw day-N's own shock"
        if r1.z_score is None:
            assert r2.z_score is None
        else:
            assert r2.z_score == pytest.approx(r1.z_score)

    # The shock DOES flow through once realized — proves the test isn't vacuous.
    assert v1_by_date[shock_date].raw_return != pytest.approx(v2_by_date[shock_date].raw_return)


# --- step_one_day regression: proves the WalkForwardState refactor is a pure
# restructuring, not a behavior change. run_walk_forward's shock test above
# only calls run_pairs_backtest, never step_one_day directly — this is what
# actually proves the two give identical per-day results. ------------------


def _drive_step_one_day_manually(raw_data, config, fit_fn, return_fn):
    """Mirrors what a resumable forward-validation tick does — one
    step_one_day call per day, state threaded through by hand — as an
    independent path to compare against run_walk_forward's own loop."""
    state = WalkForwardState()
    day_results = []
    trades = []
    n = len(raw_data)
    for t in range(config.fit_window_days, n):
        window = raw_data.iloc[t - config.fit_window_days : t]
        day_row = raw_data.iloc[t]
        state, day_result, closed_trade = step_one_day(window, day_row, fit_fn, return_fn, state, config)
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
        assert d1.cost == pytest.approx(d2.cost)
        assert d1.net_return == pytest.approx(d2.net_return)
        assert d1.equity == pytest.approx(d2.equity)


def _assert_trades_equal(a: list, b: list):
    assert len(a) == len(b)
    for t1, t2 in zip(a, b, strict=True):
        assert t1.entry_date == t2.entry_date
        assert t1.exit_date == t2.exit_date
        assert t1.direction == t2.direction
        assert t1.holding_days == t2.holding_days
        assert t1.trade_return == pytest.approx(t2.trade_return)
        assert t1.still_open == t2.still_open


def test_step_one_day_matches_run_walk_forward_on_ou_process():
    n = 1000
    fit_window_days = 100
    rng = np.random.default_rng(123)
    log_a = np.cumsum(rng.normal(0, 0.01, n))
    spread = _simulate_ou_spread(n, 0.05, 0.2, 0.01, seed=456)
    log_b = 1.5 * log_a + spread
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    frame = pd.DataFrame({"A": 100 * np.exp(log_a), "B": 100 * np.exp(log_b)}, index=dates)
    raw_data = build_pairs_raw_data(frame, "A", "B")
    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=10.0)

    batch_result = run_walk_forward(raw_data, config, fit_ou_pairs_window, realize_pairs_return)
    manual_days, manual_trades = _drive_step_one_day_manually(raw_data, config, fit_ou_pairs_window, realize_pairs_return)

    _assert_day_results_equal(batch_result.day_results, manual_days)
    # Manual driving never calls finalize_open_trade, so it never emits a
    # still_open=True trade — compare only the closed trades in common.
    closed_batch_trades = [t for t in batch_result.trades if not t.still_open]
    _assert_trades_equal(closed_batch_trades, manual_trades)


def test_step_one_day_matches_run_walk_forward_on_random_walk():
    n = 750
    fit_window_days = 100
    rng = np.random.default_rng(2024)
    log_a = np.cumsum(rng.normal(0, 0.01, n))
    log_b = np.cumsum(rng.normal(0, 0.01, n))
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    frame = pd.DataFrame({"A": 100 * np.exp(log_a), "B": 100 * np.exp(log_b)}, index=dates)
    raw_data = build_pairs_raw_data(frame, "A", "B")
    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=10.0)

    batch_result = run_walk_forward(raw_data, config, fit_ou_pairs_window, realize_pairs_return)
    manual_days, manual_trades = _drive_step_one_day_manually(raw_data, config, fit_ou_pairs_window, realize_pairs_return)

    _assert_day_results_equal(batch_result.day_results, manual_days)
    closed_batch_trades = [t for t in batch_result.trades if not t.still_open]
    _assert_trades_equal(closed_batch_trades, manual_trades)


# --- B: synthetic known-parameter OU sanity check -----------------------------


def test_synthetic_ou_process_produces_positive_out_of_sample_sharpe():
    n = 1000
    fit_window_days = 100
    hedge_ratio_true = 1.5
    theta_true = 0.05  # half-life ~ ln(2)/0.05 ~ 13.9 days
    mu_true = 0.2
    sigma_true = 0.01

    rng = np.random.default_rng(123)
    log_a = np.cumsum(rng.normal(0, 0.01, n))
    spread = _simulate_ou_spread(n, theta_true, mu_true, sigma_true, seed=456)
    log_b = hedge_ratio_true * log_a + spread

    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    frame = pd.DataFrame({"A": 100 * np.exp(log_a), "B": 100 * np.exp(log_b)}, index=dates)

    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=10.0)
    result = run_pairs_backtest("A", "B", 5, _prices_fn_from_frame(frame), config)

    assert result.status == "ok"
    assert result.pct_days_mean_reverting > 0.5
    assert len(result.trades) > 0

    net_returns = pd.Series([d.net_return for d in result.day_results])
    assert metrics.sharpe_ratio(net_returns) > 0


# --- C: independent-random-walk honesty check ---------------------------------


def test_independent_random_walks_do_not_systematically_profit():
    """Operationalizes the numerically-verified finding that a naive
    single-window fit-quality check passes independent random walks
    ~97-100% of the time — this test proves the *walk-forward, realized*
    result is not fooled the same way."""
    n = 750
    fit_window_days = 100
    config = WalkForwardConfig(fit_window_days=fit_window_days, entry_z=2.0, exit_z=0.0, cost_bps=10.0)

    sharpes = []
    for seed in range(20):
        rng = np.random.default_rng(1000 + seed)
        log_a = np.cumsum(rng.normal(0, 0.01, n))
        log_b = np.cumsum(rng.normal(0, 0.01, n))  # independent — no true relationship
        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
        frame = pd.DataFrame({"A": 100 * np.exp(log_a), "B": 100 * np.exp(log_b)}, index=dates)

        result = run_pairs_backtest("A", "B", 5, _prices_fn_from_frame(frame), config)
        if not result.day_results:
            continue
        net_returns = pd.Series([d.net_return for d in result.day_results])
        sharpes.append(metrics.sharpe_ratio(net_returns))

    assert len(sharpes) >= 15  # most trials produced a real result to test against
    positive_fraction = sum(1 for s in sharpes if s > 0) / len(sharpes)
    assert positive_fraction < 0.85, "walk-forward evaluation looks systematically fooled by noise"
    assert np.mean(sharpes) < 1.0, "no wild systematic positive bias on pure noise"


# --- E: timing -----------------------------------------------------------------


def test_backtest_completes_quickly_for_a_decade_of_data():
    n = 2520  # ~10 years
    rng = np.random.default_rng(99)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    log_a = np.cumsum(rng.normal(0, 0.01, n))
    log_b = np.cumsum(rng.normal(0, 0.01, n))
    frame = pd.DataFrame({"A": 100 * np.exp(log_a), "B": 100 * np.exp(log_b)}, index=dates)
    config = WalkForwardConfig(fit_window_days=252, entry_z=2.0, exit_z=0.0, cost_bps=10.0)

    start = time.monotonic()
    result = run_pairs_backtest("A", "B", 10, _prices_fn_from_frame(frame), config)
    elapsed = time.monotonic() - start

    assert result.status in ("ok", "not_mean_reverting")
    assert elapsed < 3.0


# --- Endpoint --------------------------------------------------------------


def test_pairs_backtest_requires_auth(client):
    response = client.post("/api/research-lab/pairs-backtest", json={"ticker_a": "AAPL", "ticker_b": "MSFT"})
    assert response.status_code == 401


def test_pairs_backtest_endpoint_caches_repeat_request(client, register_and_verify, canned_prices, monkeypatch):
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)
    register_and_verify(client)

    payload = {"ticker_a": "AAPL", "ticker_b": "MSFT", "fit_window_days": 100}
    response1 = client.post("/api/research-lab/pairs-backtest", json=payload)
    assert response1.status_code == 200, response1.text
    assert response1.json()["cached"] is False

    response2 = client.post("/api/research-lab/pairs-backtest", json=payload)
    assert response2.status_code == 200
    assert response2.json()["cached"] is True


def test_pairs_backtest_same_ticker_rejected(client, register_and_verify):
    register_and_verify(client)
    response = client.post(
        "/api/research-lab/pairs-backtest", json={"ticker_a": "AAPL", "ticker_b": "AAPL"}
    )
    assert response.status_code == 422
