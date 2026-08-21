import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    # Fresh client per test so the cookie jar doesn't leak sessions
    # between tests.
    return TestClient(app)


def test_register_creates_user_and_session(client):
    response = client.post(
        "/api/auth/register", json={"email": "new@example.com", "password": "supersecret123"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert "id" in body
    assert "aladdin2_session" in response.cookies


def test_register_duplicate_email_conflicts(client):
    client.post("/api/auth/register", json={"email": "dup@example.com", "password": "supersecret123"})
    response = client.post(
        "/api/auth/register", json={"email": "dup@example.com", "password": "anotherpassword"}
    )
    assert response.status_code == 409


def test_register_rejects_short_password(client):
    response = client.post(
        "/api/auth/register", json={"email": "short@example.com", "password": "short"}
    )
    assert response.status_code == 422


def test_login_with_correct_credentials(client):
    client.post("/api/auth/register", json={"email": "login@example.com", "password": "correcthorse"})
    response = client.post(
        "/api/auth/login", json={"email": "login@example.com", "password": "correcthorse"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "login@example.com"


def test_login_with_wrong_password_rejected(client):
    client.post("/api/auth/register", json={"email": "wrongpw@example.com", "password": "correcthorse"})
    response = client.post(
        "/api/auth/login", json={"email": "wrongpw@example.com", "password": "incorrect"}
    )
    assert response.status_code == 401


def test_login_with_unknown_email_rejected(client):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}
    )
    assert response.status_code == 401


def test_me_without_session_is_401(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_valid_session_returns_user(client):
    client.post("/api/auth/register", json={"email": "me@example.com", "password": "supersecret123"})
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_logout_clears_session(client):
    client.post("/api/auth/register", json={"email": "logout@example.com", "password": "supersecret123"})
    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 204

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 401


def test_logout_without_session_requires_auth(client):
    response = client.post("/api/auth/logout")
    assert response.status_code == 401
