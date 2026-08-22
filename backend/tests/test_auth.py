import re


def test_register_does_not_auto_login_and_sends_verification_email(client, monkeypatch):
    sent = []

    def fake_send_email(to_email: str, subject: str, body_text: str) -> bool:
        sent.append({"to": to_email, "subject": subject, "body": body_text})
        return True

    from app.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "send_email", fake_send_email)

    response = client.post(
        "/api/auth/register", json={"email": "new@example.com", "password": "supersecret123"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert "id" not in body  # RegisterResponse, not UserOut — no session implied
    assert "aladdin2_session" not in response.cookies

    assert len(sent) == 1
    assert sent[0]["to"] == "new@example.com"
    assert "verify_token=" in sent[0]["body"]


def test_register_duplicate_email_conflicts(client, register_and_verify):
    register_and_verify(client, email="dup@example.com")
    other_client_response = client.post(
        "/api/auth/register", json={"email": "dup@example.com", "password": "anotherpassword"}
    )
    assert other_client_response.status_code == 409


def test_register_rejects_short_password(client):
    response = client.post(
        "/api/auth/register", json={"email": "short@example.com", "password": "short"}
    )
    assert response.status_code == 422


def test_login_blocked_when_unverified(client, monkeypatch):
    from app.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "send_email", lambda *a, **k: True)
    client.post(
        "/api/auth/register", json={"email": "unverified@example.com", "password": "correcthorse"}
    )
    response = client.post(
        "/api/auth/login", json={"email": "unverified@example.com", "password": "correcthorse"}
    )
    assert response.status_code == 403
    assert "aladdin2_session" not in response.cookies


def test_login_with_correct_credentials(client, register_and_verify):
    register_and_verify(client, email="login@example.com", password="correcthorse")
    # A fresh client (register_and_verify's own client is now logged in via
    # verify-email) confirms /login itself, independent of that side effect.
    from fastapi.testclient import TestClient

    from app.main import app

    fresh_client = TestClient(app)
    response = fresh_client.post(
        "/api/auth/login", json={"email": "login@example.com", "password": "correcthorse"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "login@example.com"
    assert "aladdin2_session" in response.cookies


def test_login_with_wrong_password_rejected(client, register_and_verify):
    register_and_verify(client, email="wrongpw@example.com", password="correcthorse")
    from fastapi.testclient import TestClient

    from app.main import app

    fresh_client = TestClient(app)
    response = fresh_client.post(
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


def test_me_with_valid_session_returns_user(client, register_and_verify):
    register_and_verify(client, email="me@example.com")
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_logout_clears_session(client, register_and_verify):
    register_and_verify(client, email="logout@example.com")
    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 204

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 401


def test_logout_without_session_requires_auth(client):
    response = client.post("/api/auth/logout")
    assert response.status_code == 401


def test_verify_email_invalid_token_is_400(client):
    response = client.post("/api/auth/verify-email", json={"token": "not-a-real-token"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired token"


def test_verify_email_token_is_single_use(client, monkeypatch):
    sent = []
    from app.routers import auth as auth_router

    monkeypatch.setattr(
        auth_router, "send_email", lambda to, subject, body: sent.append(body) or True
    )
    client.post(
        "/api/auth/register", json={"email": "singleuse@example.com", "password": "supersecret123"}
    )
    token = re.search(r"verify_token=(\S+)", sent[0]).group(1)

    first = client.post("/api/auth/verify-email", json={"token": token})
    assert first.status_code == 200

    second = client.post("/api/auth/verify-email", json={"token": token})
    assert second.status_code == 400
    assert second.json()["detail"] == "Invalid or expired token"


def test_forgot_password_always_returns_200(client, register_and_verify):
    register_and_verify(client, email="hasaccount@example.com")

    existing = client.post("/api/auth/forgot-password", json={"email": "hasaccount@example.com"})
    nonexistent = client.post("/api/auth/forgot-password", json={"email": "nobody2@example.com"})

    assert existing.status_code == 200
    assert nonexistent.status_code == 200
    assert existing.json() == nonexistent.json()


def test_reset_password_flow_invalidates_sessions(client, monkeypatch):
    sent = []
    from app.routers import auth as auth_router

    monkeypatch.setattr(
        auth_router, "send_email", lambda to, subject, body: sent.append(body) or True
    )

    client.post(
        "/api/auth/register", json={"email": "resetme@example.com", "password": "oldpassword1"}
    )
    verify_token = re.search(r"verify_token=(\S+)", sent[0]).group(1)
    client.post("/api/auth/verify-email", json={"token": verify_token})
    assert "aladdin2_session" in client.cookies

    sent.clear()
    client.post("/api/auth/forgot-password", json={"email": "resetme@example.com"})
    reset_token = re.search(r"reset_token=(\S+)", sent[0]).group(1)

    reset_response = client.post(
        "/api/auth/reset-password", json={"token": reset_token, "new_password": "newpassword2"}
    )
    assert reset_response.status_code == 204

    # The session created by verify-email must be dead now.
    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 401

    # Old password no longer works; new one does.
    from fastapi.testclient import TestClient

    from app.main import app

    fresh_client = TestClient(app)
    old_login = fresh_client.post(
        "/api/auth/login", json={"email": "resetme@example.com", "password": "oldpassword1"}
    )
    assert old_login.status_code == 401
    new_login = fresh_client.post(
        "/api/auth/login", json={"email": "resetme@example.com", "password": "newpassword2"}
    )
    assert new_login.status_code == 200


def test_reset_password_invalid_token_is_400(client):
    response = client.post(
        "/api/auth/reset-password", json={"token": "bogus", "new_password": "whatever123"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired token"


def test_resend_verification_always_returns_200(client, monkeypatch):
    from app.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "send_email", lambda *a, **k: True)
    client.post(
        "/api/auth/register", json={"email": "resend@example.com", "password": "supersecret123"}
    )

    existing = client.post("/api/auth/resend-verification", json={"email": "resend@example.com"})
    nonexistent = client.post("/api/auth/resend-verification", json={"email": "nobody3@example.com"})

    assert existing.status_code == 200
    assert nonexistent.status_code == 200
    assert existing.json() == nonexistent.json()
