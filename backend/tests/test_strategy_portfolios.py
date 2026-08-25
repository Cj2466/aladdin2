import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import dependencies
from app.main import app
from app.models.experiment_run import ExperimentRun
from app.models.strategy_portfolio import StrategyPortfolio
from app.models.strategy_portfolio_allocation import StrategyPortfolioAllocation
from app.services.research_lab.backtest_result import run_and_store_momentum_backtest
from app.services.research_lab.strategy_portfolio_returns import (
    MissingExperimentRunError,
    build_returns_frame,
)
from app.services.risk.errors import InsufficientHistoryError

BASE = "/api/research-lab/strategy-portfolios"

# 5 tickers so an optimize request clears the optimizer's own
# n * DEFAULT_MAX_WEIGHT >= 1.0 feasibility floor with room to spare.
SEED_TICKERS = ["AAA", "BBB", "CCC", "DDD", "EEE"]


def _trending_frame(n_days: int = 700) -> pd.DataFrame:
    """Deterministic synthetic prices with genuinely different drift per
    ticker, so the momentum strategy produces distinct, non-degenerate
    equity curves (and the optimizer has something real to prefer)."""
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    data = {}
    for i, ticker in enumerate(SEED_TICKERS):
        rng = np.random.default_rng(100 + i)
        drift = 0.0016 - 0.0006 * i
        log_price = np.cumsum(rng.normal(drift, 0.004 + 0.001 * i, n_days))
        data[ticker] = 100.0 * np.exp(log_price)
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def seeded_runs(test_db_engine, monkeypatch) -> list[int]:
    """Real ExperimentRun rows produced by the real backtest pipeline
    (run_and_store_momentum_backtest) against synthetic prices — not
    hand-written JSON, so the stored equity curves have exactly the shape
    build_returns_frame reads in production."""
    frame = _trending_frame()

    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in frame.columns]
        return frame[present], [t for t in tickers if t not in frame.columns]

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)

    session_local = sessionmaker(bind=test_db_engine)
    run_ids = []
    with session_local() as db:
        for ticker in SEED_TICKERS:
            response = run_and_store_momentum_backtest(
                db,
                dependencies.provider,
                ticker=ticker,
                fit_window_days=90,
                entry_z=2.0,
                exit_z=0.0,
                cost_bps=5.0,
                lookback_years=2,
            )
            assert response.status == "ok", f"{ticker}: {response.status}"
        run_ids = [
            r.id for r in db.execute(select(ExperimentRun).order_by(ExperimentRun.id)).scalars().all()
        ]
    assert len(run_ids) == len(SEED_TICKERS)
    return run_ids


def _payload(run_ids: list[int], name: str = "My strategy portfolio") -> dict:
    weight = round(1.0 / len(run_ids), 4)
    allocations = [{"experiment_run_id": rid, "weight": weight} for rid in run_ids]
    allocations[0]["weight"] = round(1.0 - weight * (len(run_ids) - 1), 4)
    return {"name": name, "allocations": allocations}


# --- auth ------------------------------------------------------------------


def test_all_endpoints_require_auth(client):
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, json={"name": "x", "allocations": []}).status_code == 401
    assert client.post(f"{BASE}/analyze", json={"allocations": []}).status_code == 401
    assert client.post(f"{BASE}/optimize", json={"allocations": []}).status_code == 401


# --- CRUD ------------------------------------------------------------------


def test_create_list_get_update_delete_round_trip(client, register_and_verify, seeded_runs):
    register_and_verify(client, email="sp_crud@example.com")

    created = client.post(BASE, json=_payload(seeded_runs))
    assert created.status_code == 201, created.text
    body = created.json()
    portfolio_id = body["id"]
    assert len(body["allocations"]) == len(seeded_runs)
    assert body["is_system"] is False
    assert body["last_optimized_at"] is None
    # Metadata is resolved from the referenced ExperimentRun at read time.
    assert {a["strategy_name"] for a in body["allocations"]} == {"momentum_v1"}
    assert {a["ticker_a"] for a in body["allocations"]} == set(SEED_TICKERS)
    assert all(a["status"] == "ok" for a in body["allocations"])

    listed = client.get(BASE)
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [portfolio_id]
    assert listed.json()[0]["allocation_count"] == len(seeded_runs)

    fetched = client.get(f"{BASE}/{portfolio_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "My strategy portfolio"

    updated = client.put(
        f"{BASE}/{portfolio_id}",
        json={
            "name": "Renamed",
            "allocations": [
                {"experiment_run_id": seeded_runs[0], "weight": 0.6},
                {"experiment_run_id": seeded_runs[1], "weight": 0.4},
            ],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Renamed"
    assert len(updated.json()["allocations"]) == 2

    assert client.delete(f"{BASE}/{portfolio_id}").status_code == 204
    assert client.get(f"{BASE}/{portfolio_id}").status_code == 404
    assert client.get(BASE).json() == []


def test_another_users_portfolio_is_404_not_403(client, register_and_verify, seeded_runs):
    register_and_verify(client, email="sp_owner@example.com")
    portfolio_id = client.post(BASE, json=_payload(seeded_runs)).json()["id"]

    other = TestClient(app)
    register_and_verify(other, email="sp_intruder@example.com")
    assert other.get(f"{BASE}/{portfolio_id}").status_code == 404
    assert other.put(f"{BASE}/{portfolio_id}", json=_payload(seeded_runs)).status_code == 404
    assert other.delete(f"{BASE}/{portfolio_id}").status_code == 404
    assert other.get(f"{BASE}/{portfolio_id}/analyze").status_code == 404
    assert other.get(f"{BASE}/{portfolio_id}/optimize").status_code == 404
    assert other.get(BASE).json() == []


def test_delete_cascades_allocations(client, register_and_verify, seeded_runs, test_db_engine):
    register_and_verify(client, email="sp_cascade@example.com")
    portfolio_id = client.post(BASE, json=_payload(seeded_runs)).json()["id"]
    client.delete(f"{BASE}/{portfolio_id}")

    with sessionmaker(bind=test_db_engine)() as db:
        remaining = db.execute(select(StrategyPortfolioAllocation)).scalars().all()
    assert remaining == []


# --- validation -------------------------------------------------------------


def test_weights_must_sum_to_one(client, register_and_verify, seeded_runs):
    register_and_verify(client, email="sp_weights@example.com")
    response = client.post(
        BASE,
        json={
            "name": "bad",
            "allocations": [
                {"experiment_run_id": seeded_runs[0], "weight": 0.5},
                {"experiment_run_id": seeded_runs[1], "weight": 0.6},
            ],
        },
    )
    assert response.status_code == 422


def test_duplicate_experiment_run_id_is_rejected(client, register_and_verify, seeded_runs):
    register_and_verify(client, email="sp_dupe@example.com")
    response = client.post(
        BASE,
        json={
            "name": "dupe",
            "allocations": [
                {"experiment_run_id": seeded_runs[0], "weight": 0.5},
                {"experiment_run_id": seeded_runs[0], "weight": 0.5},
            ],
        },
    )
    assert response.status_code == 422


def test_db_unique_constraint_blocks_duplicate_allocation(
    client, register_and_verify, seeded_runs, test_db_engine
):
    """The Pydantic validator catches this at the API boundary; the DB
    constraint is the backstop for any other write path (e.g. the
    autonomous runner)."""
    user = register_and_verify(client, email="sp_uq@example.com")
    with sessionmaker(bind=test_db_engine)() as db:
        portfolio = StrategyPortfolio(user_id=user["id"], name="uq")
        portfolio.allocations = [
            StrategyPortfolioAllocation(experiment_run_id=seeded_runs[0], weight=0.5),
            StrategyPortfolioAllocation(experiment_run_id=seeded_runs[0], weight=0.5),
        ]
        db.add(portfolio)
        with pytest.raises(IntegrityError):
            db.commit()


# --- analyze ----------------------------------------------------------------


def _patch_benchmark(monkeypatch, frame: pd.DataFrame):
    """Only the benchmark ticker is ever fetched by the analyze path — every
    strategy's returns already live in results_json."""
    n = len(frame)
    rng = np.random.default_rng(999)
    bench = pd.DataFrame(
        {"SPY": 400.0 * np.cumprod(1 + rng.normal(0.0004, 0.01, n))}, index=frame.index
    )

    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in bench.columns]
        return bench[present], [t for t in tickers if t not in bench.columns]

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)


def test_analyze_stateless_returns_expected_shape(client, register_and_verify, seeded_runs, monkeypatch):
    register_and_verify(client, email="sp_analyze@example.com")
    _patch_benchmark(monkeypatch, _trending_frame())

    payload = _payload(seeded_runs)
    response = client.post(f"{BASE}/analyze", json={"allocations": payload["allocations"]})
    assert response.status_code == 200, response.text
    body = response.json()

    expected_keys = {
        "as_of",
        "volatility_annualized",
        "var_historical_95",
        "var_parametric_95",
        "cvar_95",
        "beta",
        "hhi",
        "avg_pairwise_correlation",
        "correlation_matrix",
        "warnings",
    }
    assert expected_keys.issubset(body.keys())
    assert body["hhi"] == pytest.approx(
        sum(a["weight"] ** 2 for a in payload["allocations"]), abs=1e-6
    )
    # Keys are opaque run-id strings, not tickers — the frontend maps them.
    corr = body["correlation_matrix"]
    assert set(corr.keys()) == {str(rid) for rid in seeded_runs}
    for key in corr:
        assert corr[key][key] == pytest.approx(1.0, abs=1e-3)


def test_analyze_saved_portfolio(client, register_and_verify, seeded_runs, monkeypatch):
    register_and_verify(client, email="sp_analyze_saved@example.com")
    _patch_benchmark(monkeypatch, _trending_frame())

    portfolio_id = client.post(BASE, json=_payload(seeded_runs)).json()["id"]
    response = client.get(f"{BASE}/{portfolio_id}/analyze")
    assert response.status_code == 200, response.text
    assert response.json()["strategy_portfolio_id"] == portfolio_id


def test_analyze_with_unknown_experiment_run_is_422(client, register_and_verify, seeded_runs, monkeypatch):
    register_and_verify(client, email="sp_badrun@example.com")
    _patch_benchmark(monkeypatch, _trending_frame())

    response = client.post(
        f"{BASE}/analyze",
        json={
            "allocations": [
                {"experiment_run_id": seeded_runs[0], "weight": 0.5},
                {"experiment_run_id": 999_999, "weight": 0.5},
            ]
        },
    )
    assert response.status_code == 422
    assert "999999" in response.json()["detail"]


def test_analyze_with_non_ok_experiment_run_is_422(
    client, register_and_verify, seeded_runs, test_db_engine, monkeypatch
):
    register_and_verify(client, email="sp_notok@example.com")
    _patch_benchmark(monkeypatch, _trending_frame())

    with sessionmaker(bind=test_db_engine)() as db:
        run = db.get(ExperimentRun, seeded_runs[1])
        run.status = "not_trending"
        db.commit()

    response = client.post(
        f"{BASE}/analyze",
        json={
            "allocations": [
                {"experiment_run_id": seeded_runs[0], "weight": 0.5},
                {"experiment_run_id": seeded_runs[1], "weight": 0.5},
            ]
        },
    )
    assert response.status_code == 422


# --- optimize ---------------------------------------------------------------


def test_optimize_stateless_needs_no_provider(client, register_and_verify, seeded_runs, monkeypatch):
    """The strategy optimizer makes no network call at all, unlike the
    ticker one — a provider that raises on any use proves it."""
    register_and_verify(client, email="sp_optimize@example.com")

    def exploding_get_price_history(tickers, start, end):
        raise AssertionError("Strategy-portfolio optimize must not fetch prices")

    monkeypatch.setattr(dependencies.provider, "get_price_history", exploding_get_price_history)

    payload = _payload(seeded_runs)
    response = client.post(f"{BASE}/optimize", json={"allocations": payload["allocations"]})
    assert response.status_code == 200, response.text
    body = response.json()

    total = sum(h["weight"] for h in body["optimized_weights"])
    assert total == pytest.approx(1.0, abs=1e-2)
    assert all(h["weight"] <= 0.4 + 1e-6 for h in body["optimized_weights"])
    assert body["max_weight_cap"] == pytest.approx(0.4)
    # lookback_years reports the MEASURED overlap window, not a request
    # parameter (there isn't one) — ~700 business days of synthetic prices
    # minus the fit window, over a 2-year backtest lookback.
    assert body["lookback_years"] >= 1
    assert {h["ticker"] for h in body["optimized_weights"]} == {str(r) for r in seeded_runs}


def test_optimize_saved_portfolio(client, register_and_verify, seeded_runs):
    register_and_verify(client, email="sp_optimize_saved@example.com")
    portfolio_id = client.post(BASE, json=_payload(seeded_runs)).json()["id"]
    response = client.get(f"{BASE}/{portfolio_id}/optimize")
    assert response.status_code == 200, response.text
    assert response.json()["strategy_portfolio_id"] == portfolio_id


def test_optimize_with_too_few_strategies_is_422(client, register_and_verify, seeded_runs):
    register_and_verify(client, email="sp_infeasible@example.com")
    response = client.post(
        f"{BASE}/optimize",
        json={
            "allocations": [
                {"experiment_run_id": seeded_runs[0], "weight": 0.5},
                {"experiment_run_id": seeded_runs[1], "weight": 0.5},
            ]
        },
    )
    assert response.status_code == 422
    assert "cap" in response.json()["detail"].lower()


# --- build_returns_frame ------------------------------------------------------


def _seed_curve(db, run_id_hint: str, dates: list[str], equities: list[float]) -> int:
    import json

    payload = {
        "equity_curve": [
            {"date": d, "equity": e, "position": 0, "z_score": None}
            for d, e in zip(dates, equities, strict=True)
        ]
    }
    run = ExperimentRun(
        strategy_name="momentum_v1",
        ticker_a=run_id_hint,
        ticker_b=run_id_hint,
        input_hash=f"hash-{run_id_hint}",
        results_json=json.dumps(payload),
        status="ok",
        fit_window_days=90,
        entry_z=2.0,
        exit_z=0.0,
        cost_bps=5.0,
        lookback_years=2,
        num_trades=0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run.id


def test_build_returns_frame_inner_joins_on_date(test_db_engine):
    with sessionmaker(bind=test_db_engine)() as db:
        # 5 days vs 4 days, overlapping on exactly 3 (2026-01-02..2026-01-06).
        a = _seed_curve(
            db,
            "AAA",
            ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"],
            [1.01, 1.02, 1.03, 1.04, 1.05],
        )
        b = _seed_curve(
            db,
            "BBB",
            ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-08"],
            [0.99, 0.98, 0.97, 0.96],
        )
        frame, runs = build_returns_frame(db, [a, b])

    assert list(frame.columns) == [str(a), str(b)]
    assert len(frame) == 3  # hand-computed intersection, not a union/ffill
    assert str(frame.index.min().date()) == "2026-01-02"
    assert str(frame.index.max().date()) == "2026-01-06"
    assert set(runs.keys()) == {a, b}
    # derive_returns_from_equity_curve prepends the engine's implicit 1.0
    # base, so A's first stored return is 1.01/1.0 - 1 and its 2026-01-02
    # value is 1.02/1.01 - 1.
    assert frame[str(a)].iloc[0] == pytest.approx(1.02 / 1.01 - 1.0)
    assert frame[str(b)].iloc[0] == pytest.approx(0.99 / 1.0 - 1.0)


def test_build_returns_frame_zero_overlap_is_empty_not_an_error(test_db_engine):
    with sessionmaker(bind=test_db_engine)() as db:
        a = _seed_curve(db, "AAA", ["2026-01-01", "2026-01-02"], [1.01, 1.02])
        b = _seed_curve(db, "BBB", ["2026-06-01", "2026-06-02"], [0.99, 0.98])
        frame, _runs = build_returns_frame(db, [a, b])
    assert frame.empty


def test_zero_overlap_analyze_raises_insufficient_history(test_db_engine, monkeypatch):
    with sessionmaker(bind=test_db_engine)() as db:
        a = _seed_curve(db, "AAA", ["2026-01-01", "2026-01-02"], [1.01, 1.02])
        b = _seed_curve(db, "BBB", ["2026-06-01", "2026-06-02"], [0.99, 0.98])

        from app.services.research_lab.strategy_portfolio_returns import (
            compute_strategy_portfolio_risk,
        )

        with pytest.raises(InsufficientHistoryError) as excinfo:
            compute_strategy_portfolio_risk(db, dependencies.provider, {a: 0.5, b: 0.5}, "SPY")
    assert "selected strategies" in str(excinfo.value)


def test_build_returns_frame_rejects_missing_run(test_db_engine):
    with sessionmaker(bind=test_db_engine)() as db:
        a = _seed_curve(db, "AAA", ["2026-01-01", "2026-01-02"], [1.01, 1.02])
        with pytest.raises(MissingExperimentRunError):
            build_returns_frame(db, [a, 424242])
