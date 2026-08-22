import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rate_limit import limiter


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def rate_limiting_enabled():
    """conftest.py disables the limiter globally so unrelated functional
    tests don't fail once earlier tests exhaust the quota — re-enable it
    just for this test, and reset counters after so nothing leaks into
    later tests."""
    limiter.enabled = True
    yield
    limiter.reset()
    limiter.enabled = False


def test_login_rate_limit_returns_429_after_quota_exhausted(client, rate_limiting_enabled):
    payload = {"email": "doesnotexist@example.com", "password": "wrongpassword"}

    statuses = [client.post("/api/auth/login", json=payload).status_code for _ in range(11)]

    # First 10 requests hit the real handler (401, invalid credentials);
    # the 11th exceeds the 10/minute cap on this endpoint and gets a 429
    # without ever reaching the login logic.
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
