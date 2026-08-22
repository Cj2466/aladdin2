import re

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — registers every model on Base.metadata
from app.db import Base, get_db
from app.main import app as fastapi_app
from app.rate_limit import limiter
from app.routers import auth as auth_router

# Rate limiting is a real production concern (see app/rate_limit.py) but has
# no place in functional tests — its in-memory counters persist across the
# whole test session (all requests share the same test-client "IP"), so
# without this, unrelated tests fail once enough earlier tests have called
# /api/auth/register or /login. This mirrors slowapi's own documented
# testing guidance.
limiter.enabled = False


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


@pytest.fixture
def client():
    # Fresh client per test so the cookie jar doesn't leak sessions
    # between tests.
    return TestClient(fastapi_app)


@pytest.fixture
def register_and_verify(monkeypatch):
    """Registration no longer auto-logs-in (a new account must verify its
    email before it can log in at all). Most tests just need a logged-in
    client, so this registers, captures the emailed verification token by
    monkeypatching resend_client.send_email (never touches the real Resend
    API — same technique test_alerts.py already uses for fetch_quote_snapshot),
    verifies it, and returns the resulting UserOut body. verify-email itself
    starts a session, so the passed-in `client` ends this call already
    authenticated — no separate /login call is needed."""
    sent = []

    def fake_send_email(to_email: str, subject: str, body_text: str) -> bool:
        sent.append({"to": to_email, "subject": subject, "body": body_text})
        return True

    # auth.py does `from app.services.email.resend_client import send_email`
    # — a direct-name import binds its own reference in auth.py's module
    # namespace, so patching the source module's attribute wouldn't affect
    # it. Patch the binding auth.py actually calls (same technique already
    # used for fetch_quote_snapshot in test_alerts.py).
    monkeypatch.setattr(auth_router, "send_email", fake_send_email)

    def _do(client, email="user@example.com", password="supersecret123"):
        response = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "accepted_terms": True},
        )
        assert response.status_code == 201, response.text

        email_sent = next(e for e in sent if e["to"] == email)
        match = re.search(r"verify_token=(\S+)", email_sent["body"])
        assert match, f"no verify_token in email body: {email_sent['body']}"

        verify_response = client.post("/api/auth/verify-email", json={"token": match.group(1)})
        assert verify_response.status_code == 200, verify_response.text
        return verify_response.json()

    return _do


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
