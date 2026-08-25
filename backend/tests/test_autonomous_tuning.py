import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.experiment_run import ExperimentRun
from app.models.forward_validation import ForwardValidationRegistration
from app.schemas.research_lab import (
    EquityCurvePointOut,
    PairsBacktestResponse,
    SearchContextOut,
)
from app.services.research_lab import autonomous_tuning, metrics, momentum, ou_pairs
from app.services.research_lab.deflated_sharpe import MIN_TRIALS_FOR_DSR
from app.services.risk.errors import MissingTickerDataError


def _session_local(test_db_engine):
    return sessionmaker(bind=test_db_engine)


def _returns_with_exact_sharpe(n: int, annualized_sharpe: float, seed: int) -> np.ndarray:
    """A seeded return series whose realized (not expected) annualized
    Sharpe is exactly `annualized_sharpe` — the noise draw is standardized
    to mean 0 / sd 1 first, so the test's expected values are exact rather
    than approximate."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    z = (z - z.mean()) / z.std(ddof=1)
    sigma = 0.01
    mu = annualized_sharpe / np.sqrt(252) * sigma
    return mu + sigma * z


def _fake_response(
    *, strategy_name: str, ticker_a: str, ticker_b: str, config, n_obs: int, annualized_sharpe: float, seed: int
) -> PairsBacktestResponse:
    returns = _returns_with_exact_sharpe(n_obs, annualized_sharpe, seed)
    equity = np.cumprod(1 + returns)
    return PairsBacktestResponse(
        status="ok",
        strategy_name=strategy_name,
        as_of="2026-08-25",
        ticker_a=ticker_a,
        ticker_b=ticker_b,
        fit_window_days=config.fit_window_days,
        entry_z=config.entry_z,
        exit_z=config.exit_z,
        cost_bps=config.cost_bps,
        lookback_years=5,
        n_trading_days=n_obs + config.fit_window_days,
        n_out_of_sample_days=n_obs,
        total_return_net=float(equity[-1] - 1.0),
        annualized_return_net=float(returns.mean() * 252),
        annualized_volatility_net=float(returns.std(ddof=1) * np.sqrt(252)),
        sharpe_net=metrics.sharpe_ratio(pd.Series(returns)),
        sharpe_gross=metrics.sharpe_ratio(pd.Series(returns)),
        max_drawdown_net=0.1,
        num_trades=10,
        win_rate=0.5,
        exposure_pct=0.5,
        total_cost_drag=0.01,
        pct_days_mean_reverting=0.5,
        fit_quality_distribution={},
        equity_curve=[
            EquityCurvePointOut(date=f"2020-01-{(i % 28) + 1:02d}", equity=float(e), position=0, z_score=None)
            for i, e in enumerate(equity)
        ],
        trade_log=[],
        search_context=SearchContextOut(configurations_tested=1, note="test"),
        methodology_note="test",
        cached=False,
    )


def _patch_momentum_backtest(monkeypatch, db_factory, plan: dict[int, tuple[int, float]]):
    """Replaces the real momentum backtest with a deterministic stand-in that
    still does the one thing the selection logic depends on: storing an
    ExperimentRun row, so sibling_trial_stats sees the grid's own trials.
    `plan` maps fit_window_days -> (n_out_of_sample_obs, annualized_sharpe)."""
    calls = []

    def fake(db, provider, *, ticker, fit_window_days, entry_z, exit_z, cost_bps, lookback_years):
        calls.append(
            {"ticker": ticker, "fit_window_days": fit_window_days, "entry_z": entry_z, "cost_bps": cost_bps}
        )
        n_obs, sharpe = plan[fit_window_days]
        config = autonomous_tuning.StrategyConfig(
            fit_window_days=fit_window_days, entry_z=entry_z, exit_z=exit_z, cost_bps=cost_bps
        )
        response = _fake_response(
            strategy_name=momentum.STRATEGY_NAME,
            ticker_a=ticker,
            ticker_b=ticker,
            config=config,
            n_obs=n_obs,
            annualized_sharpe=sharpe,
            seed=fit_window_days * 100 + int(entry_z * 10),
        )
        db.add(
            ExperimentRun(
                strategy_name=momentum.STRATEGY_NAME,
                ticker_a=ticker,
                ticker_b=ticker,
                input_hash=f"{ticker}-{fit_window_days}-{entry_z}-{exit_z}-{cost_bps}",
                results_json=response.model_dump_json(),
                status="ok",
                fit_window_days=fit_window_days,
                entry_z=entry_z,
                exit_z=exit_z,
                cost_bps=cost_bps,
                lookback_years=lookback_years,
                num_trades=response.num_trades,
                sharpe_net=response.sharpe_net,
                sharpe_gross=response.sharpe_gross,
                max_drawdown_net=response.max_drawdown_net,
                win_rate=response.win_rate,
                configurations_tested=1,
            )
        )
        db.commit()
        return response

    monkeypatch.setattr(autonomous_tuning, "run_and_store_momentum_backtest", fake)
    del db_factory
    return calls


# --- grid shape ---------------------------------------------------------------


@pytest.mark.parametrize("strategy_name", [momentum.STRATEGY_NAME, ou_pairs.STRATEGY_NAME])
def test_grid_is_small_and_always_contains_the_strategy_default(strategy_name):
    grid = autonomous_tuning.build_tuning_grid(strategy_name)

    # 3 fit windows x 3 entry_z x 1 exit_z x 1 cost_bps. Small enough to run
    # daily, above MIN_TRIALS_FOR_DSR with headroom for failing combinations.
    assert len(grid) == 9
    assert len(grid) > MIN_TRIALS_FOR_DSR

    # The defaults compete on equal footing, so tuning can never pick
    # something the deflated Sharpe ranked BELOW the default.
    assert autonomous_tuning.default_config(strategy_name) in grid

    # cost_bps is an assumption about the world and lookback_years is the
    # evaluation window — neither is searched. exit_z is pinned purely to
    # bound the grid.
    default = autonomous_tuning.default_config(strategy_name)
    assert {c.cost_bps for c in grid} == {default.cost_bps}
    assert {c.exit_z for c in grid} == {default.exit_z}
    assert len({c.fit_window_days for c in grid}) == 3
    assert len({c.entry_z for c in grid}) == 3


def test_grid_respects_the_sweep_invariant_exit_z_below_entry_z():
    for strategy_name in (momentum.STRATEGY_NAME, ou_pairs.STRATEGY_NAME):
        for combo in autonomous_tuning.build_tuning_grid(strategy_name):
            assert combo.exit_z < combo.entry_z


def test_unknown_strategy_is_rejected():
    with pytest.raises(ValueError):
        autonomous_tuning.build_tuning_grid("nope_v1")
    with pytest.raises(ValueError):
        autonomous_tuning.default_config("nope_v1")


# --- DSR-based selection ------------------------------------------------------


def test_selection_prefers_deflated_sharpe_over_raw_sharpe(test_db_engine, monkeypatch):
    """The whole point of this module. The shortest-out-of-sample
    configuration has the highest RAW Sharpe (1.30) but the fewest
    observations; a longer-sampled configuration at Sharpe 1.10 wins on
    DSR. Numbers verified directly against compute_deflated_sharpe this
    session: at n_trials=9 the 60-observation/1.30 case deflates to
    DSR~=0.64 while the 600-observation/1.10 case deflates to DSR~=0.81."""
    plan = {
        180: (60, 1.30),   # highest raw Sharpe, thinnest evidence
        90: (600, 1.10),   # lower raw Sharpe, far more out-of-sample days
        60: (600, 0.40),
    }
    _patch_momentum_backtest(monkeypatch, None, plan)

    with _session_local(test_db_engine)() as db:
        outcome = autonomous_tuning.select_tuned_config(
            db, provider=None, strategy_name=momentum.STRATEGY_NAME, ticker_a="AAPL", ticker_b="AAPL"
        )
        runs = db.execute(select(ExperimentRun)).scalars().all()

    assert outcome.source == "tuned"
    assert outcome.config.fit_window_days == 90  # NOT 180, which had the best raw Sharpe
    assert outcome.n_trials == len(runs) == 9
    assert outcome.dsr is not None

    # Sanity: the losing configuration really did have the better raw Sharpe.
    best_raw = max(runs, key=lambda r: r.sharpe_net)
    assert best_raw.fit_window_days == 180


def test_falls_back_to_defaults_when_too_few_trials_survive(test_db_engine, monkeypatch):
    """Below MIN_TRIALS_FOR_DSR there is no honest multiple-comparisons
    benchmark, so selecting on uncorrected Sharpe would be worse than not
    tuning at all. A documented fallback, not a failure."""
    calls = []

    def fake(db, provider, *, ticker, fit_window_days, entry_z, exit_z, cost_bps, lookback_years):
        calls.append(fit_window_days)
        raise MissingTickerDataError([ticker], label="ticker")

    monkeypatch.setattr(autonomous_tuning, "run_and_store_momentum_backtest", fake)

    with _session_local(test_db_engine)() as db:
        outcome = autonomous_tuning.select_tuned_config(
            db, provider=None, strategy_name=momentum.STRATEGY_NAME, ticker_a="AAPL", ticker_b="AAPL"
        )

    assert len(calls) == 9  # every combination was attempted, none survived
    assert outcome.source == "strategy_default"
    assert outcome.config == autonomous_tuning.default_config(momentum.STRATEGY_NAME)
    assert outcome.dsr is None
    assert str(MIN_TRIALS_FOR_DSR) in outcome.note


def test_a_single_failing_combination_does_not_take_down_the_grid(test_db_engine, monkeypatch):
    plan = {180: (600, 0.9), 90: (600, 1.1), 60: (600, 0.4)}
    real_calls = []

    def fake(db, provider, *, ticker, fit_window_days, entry_z, exit_z, cost_bps, lookback_years):
        if fit_window_days == 180:
            raise MissingTickerDataError([ticker], label="ticker")
        real_calls.append(fit_window_days)
        n_obs, sharpe = plan[fit_window_days]
        config = autonomous_tuning.StrategyConfig(
            fit_window_days=fit_window_days, entry_z=entry_z, exit_z=exit_z, cost_bps=cost_bps
        )
        response = _fake_response(
            strategy_name=momentum.STRATEGY_NAME,
            ticker_a=ticker,
            ticker_b=ticker,
            config=config,
            n_obs=n_obs,
            annualized_sharpe=sharpe,
            seed=fit_window_days * 100 + int(entry_z * 10),
        )
        db.add(
            ExperimentRun(
                strategy_name=momentum.STRATEGY_NAME,
                ticker_a=ticker,
                ticker_b=ticker,
                input_hash=f"{ticker}-{fit_window_days}-{entry_z}",
                results_json=response.model_dump_json(),
                status="ok",
                fit_window_days=fit_window_days,
                entry_z=entry_z,
                exit_z=exit_z,
                cost_bps=cost_bps,
                lookback_years=lookback_years,
                num_trades=0,
                sharpe_net=response.sharpe_net,
                sharpe_gross=response.sharpe_gross,
                max_drawdown_net=0.1,
                win_rate=0.5,
                configurations_tested=1,
            )
        )
        db.commit()
        return response

    monkeypatch.setattr(autonomous_tuning, "run_and_store_momentum_backtest", fake)

    with _session_local(test_db_engine)() as db:
        outcome = autonomous_tuning.select_tuned_config(
            db, provider=None, strategy_name=momentum.STRATEGY_NAME, ticker_a="AAPL", ticker_b="AAPL"
        )

    assert len(real_calls) == 6  # 9 minus the 3 entry_z variants of the 180d window
    assert outcome.source == "tuned"
    assert outcome.config.fit_window_days == 90


# --- reuse-first --------------------------------------------------------------


def test_existing_registration_config_is_reused_without_running_any_backtest(test_db_engine, monkeypatch):
    """Re-tuning a candidate that is already being forward-validated would
    open a brand-new registration at day 0 every time the winner shifted,
    so nothing would ever reach MIN_FORWARD_VALIDATION_TRADING_DAYS."""

    def explode(*args, **kwargs):
        raise AssertionError("no backtest may run when an existing registration is reused")

    monkeypatch.setattr(autonomous_tuning, "run_and_store_momentum_backtest", explode)

    with _session_local(test_db_engine)() as db:
        db.add(
            ForwardValidationRegistration(
                user_id=1,
                strategy_name=momentum.STRATEGY_NAME,
                ticker_a="AAPL",
                ticker_b="AAPL",
                fit_window_days=180,
                entry_z=2.5,
                exit_z=0.0,
                cost_bps=momentum.DEFAULT_COST_BPS,
                config_hash="abc",
                status="in_progress",
                min_trading_days_threshold=126,
                n_forward_trading_days=42,
                started_at=pd.Timestamp("2026-01-02").date(),
                carry_state_json="{}",
                day_results_json="[]",
                trades_json="[]",
            )
        )
        db.commit()

        outcome = autonomous_tuning.resolve_candidate_config(
            db,
            provider=None,
            user_id=1,
            strategy_name=momentum.STRATEGY_NAME,
            ticker_a="AAPL",
            ticker_b="AAPL",
        )

    assert outcome.source == "existing_registration"
    assert outcome.config == autonomous_tuning.StrategyConfig(
        fit_window_days=180, entry_z=2.5, exit_z=0.0, cost_bps=momentum.DEFAULT_COST_BPS
    )


def test_another_users_registration_is_not_reused(test_db_engine, monkeypatch):
    plan = {180: (600, 0.9), 90: (600, 1.1), 60: (600, 0.4)}
    _patch_momentum_backtest(monkeypatch, None, plan)

    with _session_local(test_db_engine)() as db:
        db.add(
            ForwardValidationRegistration(
                user_id=99,
                strategy_name=momentum.STRATEGY_NAME,
                ticker_a="AAPL",
                ticker_b="AAPL",
                fit_window_days=180,
                entry_z=2.5,
                exit_z=0.0,
                cost_bps=momentum.DEFAULT_COST_BPS,
                config_hash="abc",
                status="in_progress",
                min_trading_days_threshold=126,
                n_forward_trading_days=42,
                started_at=pd.Timestamp("2026-01-02").date(),
                carry_state_json="{}",
                day_results_json="[]",
                trades_json="[]",
            )
        )
        db.commit()

        outcome = autonomous_tuning.resolve_candidate_config(
            db,
            provider=None,
            user_id=1,  # a different owner
            strategy_name=momentum.STRATEGY_NAME,
            ticker_a="AAPL",
            ticker_b="AAPL",
        )

    assert outcome.source == "tuned"


def test_tuning_budget_exhausted_falls_back_to_defaults_without_running_the_grid(
    test_db_engine, monkeypatch
):
    def explode(*args, **kwargs):
        raise AssertionError("no backtest may run once the per-job tuning budget is spent")

    monkeypatch.setattr(autonomous_tuning, "run_and_store_momentum_backtest", explode)

    with _session_local(test_db_engine)() as db:
        outcome = autonomous_tuning.resolve_candidate_config(
            db,
            provider=None,
            user_id=1,
            strategy_name=momentum.STRATEGY_NAME,
            ticker_a="AAPL",
            ticker_b="AAPL",
            allow_tuning=False,
        )

    assert outcome.source == "strategy_default"
    assert outcome.config == autonomous_tuning.default_config(momentum.STRATEGY_NAME)


# --- sibling stats ------------------------------------------------------------


def test_sibling_trial_stats_matches_the_detail_endpoints_own_population(test_db_engine):
    """Same filter get_experiment_run_detail uses: exact strategy/ticker
    match, status 'ok', non-null sharpe_net. Anything else must not count
    as a trial this candidate was selected out of."""
    with _session_local(test_db_engine)() as db:
        for i, (strategy, a, b, status, sharpe) in enumerate(
            [
                (momentum.STRATEGY_NAME, "AAPL", "AAPL", "ok", 0.5),
                (momentum.STRATEGY_NAME, "AAPL", "AAPL", "ok", 1.5),
                (momentum.STRATEGY_NAME, "AAPL", "AAPL", "not_trending", 9.0),  # excluded
                (momentum.STRATEGY_NAME, "MSFT", "MSFT", "ok", 9.0),  # different ticker
                (ou_pairs.STRATEGY_NAME, "AAPL", "AAPL", "ok", 9.0),  # different strategy
            ]
        ):
            db.add(
                ExperimentRun(
                    strategy_name=strategy,
                    ticker_a=a,
                    ticker_b=b,
                    input_hash=f"h{i}",
                    results_json="{}",
                    status=status,
                    fit_window_days=90,
                    entry_z=2.0,
                    exit_z=0.0,
                    cost_bps=5.0,
                    lookback_years=5,
                    num_trades=0,
                    sharpe_net=sharpe,
                    configurations_tested=1,
                )
            )
        db.commit()

        n_trials, sigma_sr = autonomous_tuning.sibling_trial_stats(
            db, momentum.STRATEGY_NAME, "AAPL", "AAPL"
        )

    assert n_trials == 2
    assert sigma_sr == pytest.approx(float(np.std([0.5, 1.5], ddof=1)))
