import itertools

import numpy as np
from sqlalchemy.orm import sessionmaker

from app.models.experiment_run import ExperimentRun
from app.schemas.research_lab import PairsBacktestResponse

_hash_counter = itertools.count()


def _synthetic_equity_curve(n: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0005, 0.01, n)
    equity = np.cumprod(1 + returns)
    return [
        {"date": f"2026-01-{(i % 28) + 1:02d}", "equity": float(e), "position": 1, "z_score": None}
        for i, e in enumerate(equity)
    ]


def _full_response_json(**overrides) -> str:
    payload = {
        "status": "ok",
        "strategy_name": "ou_pairs_v1",
        "as_of": "2026-08-23",
        "ticker_a": "AAPL",
        "ticker_b": "MSFT",
        "fit_window_days": 252,
        "entry_z": 2.0,
        "exit_z": 0.0,
        "cost_bps": 10.0,
        "lookback_years": 5,
        "n_trading_days": 1000,
        "n_out_of_sample_days": 748,
        "total_return_net": 0.1,
        "annualized_return_net": 0.05,
        "annualized_volatility_net": 0.1,
        "sharpe_net": 0.5,
        "sharpe_gross": 0.6,
        "max_drawdown_net": -0.1,
        "num_trades": 5,
        "win_rate": 0.6,
        "exposure_pct": 0.3,
        "total_cost_drag": 0.01,
        "pct_days_mean_reverting": 0.8,
        "fit_quality_distribution": {"weak": 0.1, "moderate": 0.2, "strong": 0.7},
        "equity_curve": [],
        "trade_log": [],
        "search_context": {"configurations_tested": 1, "note": "test"},
        "methodology_note": "note",
        "warnings": [],
        "cached": False,
    }
    payload.update(overrides)
    return PairsBacktestResponse(**payload).model_dump_json()


def _create_run(db, **kwargs) -> ExperimentRun:
    defaults = {
        "strategy_name": "ou_pairs_v1",
        "ticker_a": "AAPL",
        "ticker_b": "MSFT",
        "status": "ok",
        "fit_window_days": 252,
        "entry_z": 2.0,
        "exit_z": 0.0,
        "cost_bps": 10.0,
        "lookback_years": 5,
        "num_trades": 5,
        "sharpe_net": 0.5,
        "sharpe_gross": 0.6,
        "max_drawdown_net": -0.1,
        "win_rate": 0.6,
        "sweep_id": None,
        "configurations_tested": 1,
    }
    defaults.update(kwargs)
    results_json = defaults.pop("results_json", None) or _full_response_json(
        ticker_a=defaults["ticker_a"],
        ticker_b=defaults["ticker_b"],
        status=defaults["status"],
        sharpe_net=defaults["sharpe_net"],
    )
    run = ExperimentRun(input_hash=f"test-hash-{next(_hash_counter)}", results_json=results_json, **defaults)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def test_leaderboard_requires_auth(client):
    response = client.get("/api/research-lab/experiment-runs")
    assert response.status_code == 401


def test_leaderboard_sorts_desc_with_nulls_last(test_db_engine, register_and_verify, client):
    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        _create_run(db, sharpe_net=1.0)
        _create_run(db, sharpe_net=None, status="insufficient_history", win_rate=None, sharpe_gross=None, max_drawdown_net=None)
        _create_run(db, sharpe_net=0.5)
        _create_run(db, sharpe_net=-0.2)

    response = client.get("/api/research-lab/experiment-runs", params={"sort_by": "sharpe_net", "sort_dir": "desc"})
    assert response.status_code == 200
    sharpe_values = [r["sharpe_net"] for r in response.json()["results"]]
    assert sharpe_values == [1.0, 0.5, -0.2, None]  # nulls always last, even sorting desc


def test_leaderboard_filters_by_ticker_and_sweep_id(test_db_engine, register_and_verify, client):
    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        _create_run(db, ticker_a="AAPL", ticker_b="MSFT", sweep_id=None)
        _create_run(db, ticker_a="KO", ticker_b="PEP", sweep_id=7)
        _create_run(db, ticker_a="KO", ticker_b="PEP", sweep_id=7)

    by_ticker = client.get("/api/research-lab/experiment-runs", params={"ticker_a": "ko"})
    assert by_ticker.status_code == 200
    assert by_ticker.json()["total_matching"] == 2
    assert all(r["ticker_a"] == "KO" for r in by_ticker.json()["results"])

    by_sweep = client.get("/api/research-lab/experiment-runs", params={"sweep_id": 7})
    assert by_sweep.json()["total_matching"] == 2


def test_leaderboard_pagination_is_honest(test_db_engine, register_and_verify, client):
    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        for i in range(5):
            _create_run(db, sharpe_net=float(i))

    response = client.get("/api/research-lab/experiment-runs", params={"limit": 2})
    body = response.json()
    assert body["total_matching"] == 5
    assert len(body["results"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0


def test_experiment_run_detail_returns_full_response(test_db_engine, register_and_verify, client):
    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        run = _create_run(db, ticker_a="GLD", ticker_b="SLV", sharpe_net=1.23)
        run_id = run.id

    response = client.get(f"/api/research-lab/experiment-runs/{run_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["ticker_a"] == "GLD"
    assert body["ticker_b"] == "SLV"
    assert body["sharpe_net"] == 1.23


def test_experiment_run_detail_404_for_unknown_id(client, register_and_verify):
    register_and_verify(client)
    response = client.get("/api/research-lab/experiment-runs/999999")
    assert response.status_code == 404


# --- n_trials_same_setup (leaderboard) ---------------------------------------


def test_leaderboard_includes_n_trials_same_setup(test_db_engine, register_and_verify, client):
    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        _create_run(db, ticker_a="AAPL", ticker_b="MSFT", sharpe_net=0.3)
        _create_run(db, ticker_a="AAPL", ticker_b="MSFT", sharpe_net=0.5)
        _create_run(db, ticker_a="AAPL", ticker_b="MSFT", sharpe_net=0.7)
        _create_run(db, ticker_a="KO", ticker_b="PEP", sharpe_net=0.2)

    response = client.get("/api/research-lab/experiment-runs")
    assert response.status_code == 200
    by_tickers = {(r["ticker_a"], r["ticker_b"]): r["n_trials_same_setup"] for r in response.json()["results"]}
    assert by_tickers[("AAPL", "MSFT")] == 3
    assert by_tickers[("KO", "PEP")] == 1


def test_n_trials_same_setup_excludes_non_ok_status(test_db_engine, register_and_verify, client):
    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        _create_run(db, ticker_a="AAPL", ticker_b="MSFT", sharpe_net=0.3)
        _create_run(db, ticker_a="AAPL", ticker_b="MSFT", sharpe_net=0.5)
        _create_run(
            db,
            ticker_a="AAPL",
            ticker_b="MSFT",
            status="insufficient_history",
            sharpe_net=None,
            win_rate=None,
            sharpe_gross=None,
            max_drawdown_net=None,
        )

    response = client.get("/api/research-lab/experiment-runs")
    results = response.json()["results"]
    assert all(r["n_trials_same_setup"] == 2 for r in results if r["ticker_a"] == "AAPL")


# --- deflated_sharpe (detail) -------------------------------------------------


def test_experiment_run_detail_includes_deflated_sharpe_above_floor(test_db_engine, register_and_verify, client):
    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        run_ids = []
        for i in range(5):
            run = _create_run(
                db,
                ticker_a="AAPL",
                ticker_b="MSFT",
                sharpe_net=0.3 + i * 0.1,
                results_json=_full_response_json(
                    ticker_a="AAPL",
                    ticker_b="MSFT",
                    sharpe_net=0.3 + i * 0.1,
                    equity_curve=_synthetic_equity_curve(80, seed=i),
                ),
            )
            run_ids.append(run.id)

    response = client.get(f"/api/research-lab/experiment-runs/{run_ids[0]}")
    assert response.status_code == 200
    ds = response.json()["deflated_sharpe"]
    assert ds is not None
    assert ds["n_trials"] == 5
    assert ds["dsr_floor_met"] is True
    assert ds["dsr"] is not None
    assert 0 <= ds["dsr"] <= 1
    assert 0 <= ds["psr_vs_zero"] <= 1


def test_experiment_run_detail_deflated_sharpe_below_floor(test_db_engine, register_and_verify, client):
    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        run_ids = []
        for i in range(2):
            run = _create_run(
                db,
                ticker_a="AAPL",
                ticker_b="MSFT",
                sharpe_net=0.3 + i * 0.1,
                results_json=_full_response_json(
                    ticker_a="AAPL",
                    ticker_b="MSFT",
                    sharpe_net=0.3 + i * 0.1,
                    equity_curve=_synthetic_equity_curve(80, seed=i),
                ),
            )
            run_ids.append(run.id)

    response = client.get(f"/api/research-lab/experiment-runs/{run_ids[0]}")
    ds = response.json()["deflated_sharpe"]
    assert ds["dsr_floor_met"] is False
    assert ds["dsr"] is None
    assert ds["psr_vs_zero"] is not None


def test_experiment_run_detail_deflated_sharpe_none_for_non_ok_status(test_db_engine, register_and_verify, client):
    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        run = _create_run(
            db,
            status="insufficient_history",
            sharpe_net=None,
            win_rate=None,
            sharpe_gross=None,
            max_drawdown_net=None,
        )
        run_id = run.id

    response = client.get(f"/api/research-lab/experiment-runs/{run_id}")
    assert response.json()["deflated_sharpe"] is None


def test_experiment_run_detail_deflated_sharpe_none_for_empty_equity_curve(test_db_engine, register_and_verify, client):
    register_and_verify(client)
    session_local = sessionmaker(bind=test_db_engine)
    with session_local() as db:
        run = _create_run(db)  # default fixture has equity_curve=[]
        run_id = run.id

    response = client.get(f"/api/research-lab/experiment-runs/{run_id}")
    body = response.json()
    assert body["deflated_sharpe"] is not None
    assert body["deflated_sharpe"]["psr_vs_zero"] is None
    assert body["deflated_sharpe"]["dsr"] is None
