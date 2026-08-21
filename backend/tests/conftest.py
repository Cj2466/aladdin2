import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — registers every model on Base.metadata
from app.db import Base, get_db
from app.main import app as fastapi_app


@pytest.fixture
def test_db_engine(tmp_path):
    """Fresh SQLite file per test — used directly by tests that need a
    Session (e.g. price cache tests) and indirectly by the autouse
    `test_db` fixture below (FastAPI's get_db override)."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def test_db(test_db_engine):
    """Wires test_db_engine into every request the FastAPI test client
    makes, via a get_db override. Autouse so every test — including ones
    that don't touch the DB directly — gets a clean, isolated database and
    never accidentally shares state or hits the real dev DB (aladdin2.db)."""
    TestingSessionLocal = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield
    fastapi_app.dependency_overrides.pop(get_db, None)


def _make_price_series(start_price: float, n_days: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    daily_returns = rng.normal(loc=0.0003, scale=0.012, size=n_days)
    return start_price * np.cumprod(1 + daily_returns)


@pytest.fixture
def canned_prices() -> pd.DataFrame:
    """Deterministic synthetic ~3-year daily price series for four tickers.
    No network calls — tests must never depend on live yfinance data."""
    n_days = 756  # ~3 trading years
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    data = {
        "AAPL": _make_price_series(150.0, n_days, seed=1),
        "MSFT": _make_price_series(300.0, n_days, seed=2),
        "GLD": _make_price_series(180.0, n_days, seed=3),
        "SPY": _make_price_series(400.0, n_days, seed=4),
    }
    return pd.DataFrame(data, index=dates)
