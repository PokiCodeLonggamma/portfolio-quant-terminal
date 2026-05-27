"""Phase 4 — auth endpoints + JWT helpers."""
from __future__ import annotations

import os

import bcrypt
import pytest
from fastapi.testclient import TestClient

# Set test creds BEFORE importing the app — _settings() reads env at call time
# but importing api.auth triggers `from api.auth import ...` paths in routes.
TEST_EMAIL = "user@test.dev"
TEST_PWD = "correct-horse-staple"  # bcrypt has 72-byte limit
TEST_HASH = bcrypt.hashpw(TEST_PWD.encode("utf-8"), bcrypt.gensalt(rounds=4)).decode("utf-8")


@pytest.fixture(autouse=True)
def _env():
    """Patch env vars for each test, restore after."""
    old = {
        k: os.environ.get(k)
        for k in ("QT_ADMIN_EMAIL", "QT_ADMIN_PASSWORD_HASH", "JWT_SECRET")
    }
    os.environ["QT_ADMIN_EMAIL"] = TEST_EMAIL
    os.environ["QT_ADMIN_PASSWORD_HASH"] = TEST_HASH
    os.environ["JWT_SECRET"] = "test-secret-32-bytes-ok-for-tests"
    yield
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture
def client():
    from api.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/auth/login
# ---------------------------------------------------------------------------
def test_login_with_correct_creds_sets_cookie(client):
    r = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PWD})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["email"] == TEST_EMAIL
    # Cookie present
    cookies = r.cookies
    assert "qt_auth" in cookies
    assert len(cookies["qt_auth"]) > 20  # JWT


def test_login_with_wrong_password_returns_401(client):
    r = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": "nope"})
    assert r.status_code == 401
    assert "qt_auth" not in r.cookies


def test_login_with_unknown_email_returns_401(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "other@test.dev", "password": TEST_PWD},
    )
    assert r.status_code == 401


def test_login_with_bad_email_format_returns_422(client):
    r = client.post("/api/auth/login", json={"email": "not-an-email", "password": TEST_PWD})
    assert r.status_code == 422  # Pydantic EmailStr rejects


# ---------------------------------------------------------------------------
# /api/auth/me
# ---------------------------------------------------------------------------
def test_me_without_cookie_returns_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_valid_cookie_returns_payload(client):
    # Login first to get the cookie set on the TestClient session
    r = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PWD})
    assert r.status_code == 200
    r2 = client.get("/api/auth/me")
    assert r2.status_code == 200
    body = r2.json()
    assert body["email"] == TEST_EMAIL


def test_me_with_garbage_cookie_returns_401(client):
    client.cookies.set("qt_auth", "garbage.not.a.jwt")
    r = client.get("/api/auth/me")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# /api/auth/logout
# ---------------------------------------------------------------------------
def test_logout_clears_cookie(client):
    client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PWD})
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    # Subsequent /me without cookie → 401
    client.cookies.clear()
    r2 = client.get("/api/auth/me")
    assert r2.status_code == 401
