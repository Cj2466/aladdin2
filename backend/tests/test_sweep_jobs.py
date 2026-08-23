from app import dependencies


def _patch_provider(monkeypatch, canned_prices):
    def fake_get_price_history(tickers, start, end):
        present = [t for t in tickers if t in canned_prices.columns]
        missing = [t for t in tickers if t not in canned_prices.columns]
        return canned_prices[present], missing

    monkeypatch.setattr(dependencies.provider, "get_price_history", fake_get_price_history)


def _valid_payload():
    return {
        "ticker_a": "AAPL",
        "ticker_b": "MSFT",
        "grid": {
            "fit_window_days": [100, 150],
            "entry_z": [1.5, 2.0],
            "exit_z": [0.0],
            "cost_bps": [10.0],
        },
    }


def test_create_sweep_requires_auth(client):
    response = client.post("/api/research-lab/sweeps", json=_valid_payload())
    assert response.status_code == 401


def test_create_sweep_valid_grid_returns_correct_total(client, register_and_verify, canned_prices, monkeypatch):
    _patch_provider(monkeypatch, canned_prices)
    register_and_verify(client)

    response = client.post("/api/research-lab/sweeps", json=_valid_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["total_configurations"] == 4  # 2 fit_window_days x 2 entry_z x 1 exit_z x 1 cost_bps
    assert body["status"] == "queued"
    assert body["configurations_completed"] == 0


def test_create_sweep_over_cap_grid_rejected(client, register_and_verify, canned_prices, monkeypatch):
    _patch_provider(monkeypatch, canned_prices)
    register_and_verify(client)

    payload = _valid_payload()
    # 26 x 21 x 1 x 1 = 546 raw combos, all valid (exit_z=0 < every entry_z) — above the 500 cap.
    payload["grid"] = {
        "fit_window_days": [100 + i for i in range(26)],
        "entry_z": [1.0 + i * 0.1 for i in range(21)],
        "exit_z": [0.0],
        "cost_bps": [10.0],
    }
    response = client.post("/api/research-lab/sweeps", json=payload)
    assert response.status_code == 422


def test_create_sweep_all_combos_invalid_rejected(client, register_and_verify, canned_prices, monkeypatch):
    _patch_provider(monkeypatch, canned_prices)
    register_and_verify(client)

    payload = _valid_payload()
    payload["grid"] = {
        "fit_window_days": [100],
        "entry_z": [1.0],
        "exit_z": [1.0, 2.0],  # exit_z >= entry_z for every combo
        "cost_bps": [10.0],
    }
    response = client.post("/api/research-lab/sweeps", json=payload)
    assert response.status_code == 422


def test_create_sweep_unknown_ticker_rejected(client, register_and_verify, canned_prices, monkeypatch):
    _patch_provider(monkeypatch, canned_prices)
    register_and_verify(client)

    payload = _valid_payload()
    payload["ticker_a"] = "ZZZZ"
    response = client.post("/api/research-lab/sweeps", json=payload)
    assert response.status_code == 422


def test_create_sweep_out_of_bounds_value_rejected(client, register_and_verify, canned_prices, monkeypatch):
    _patch_provider(monkeypatch, canned_prices)
    register_and_verify(client)

    payload = _valid_payload()
    payload["grid"]["entry_z"] = [10.0]  # above the 5.0 bound the single-backtest endpoint also enforces
    response = client.post("/api/research-lab/sweeps", json=payload)
    assert response.status_code == 422


def test_list_sweeps_requires_auth(client):
    response = client.get("/api/research-lab/sweeps")
    assert response.status_code == 401


def test_list_sweeps_is_user_scoped(client, register_and_verify, canned_prices, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    _patch_provider(monkeypatch, canned_prices)
    register_and_verify(client, email="sweep_user_a@example.com")
    created = client.post("/api/research-lab/sweeps", json=_valid_payload())
    assert created.status_code == 201

    other_client = TestClient(app)
    register_and_verify(other_client, email="sweep_user_b@example.com")
    listed = other_client.get("/api/research-lab/sweeps")
    assert listed.status_code == 200
    assert listed.json() == []

    own_listed = client.get("/api/research-lab/sweeps")
    assert own_listed.status_code == 200
    assert len(own_listed.json()) == 1
