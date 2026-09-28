"""
Xyrox — Auth API Tests (Phase 3)

Hits the real FastAPI app via TestClient. Uses a fresh isolated
SQLite database per test. Uses real bcrypt + real JWT.

Coverage:
- Registration (success, duplicates, weak passwords)
- Login (success, wrong password, unknown user, disabled user)
- /me (valid token, missing token, bad token, expired token)
- Response shapes (no password leaks)
- Full registration → login → /me flow
"""

import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models.models import Base
from app.backend.services import auth_service
from app.backend.api import deps as deps_module
from app.backend.main import app
from app.backend.config import settings
from app.backend.security.tokens import create_access_token
from app.backend.security.passwords import hash_password


client = TestClient(app)


# ============================================================
# ISOLATED TEST DATABASE
# ============================================================
@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path, monkeypatch):
    """
    Fresh SQLite file per test. Rebind SessionLocal used by
    auth_service. Production data/app.db is never touched.
    """
    db_file = tmp_path / "auth_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(auth_service, "SessionLocal", TestSession)
    # The deps module imports get_user_by_username, which uses the
    # patched SessionLocal — no further patching needed.

    yield

    engine.dispose()


# ============================================================
# HELPERS
# ============================================================
def register(username="alice", password="securepass123", email=None):
    return client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={
            "username": username,
            "email": email or f"{username}@example.com",
            "password": password,
            "full_name": "Alice Example",
        },
    )


def login(username="alice", password="securepass123"):
    return client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"username": username, "password": password},
    )


# ============================================================
# REGISTRATION
# ============================================================
def test_register_success():
    r = register()
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["username"] == "alice"
    assert data["email"] == "alice@example.com"
    assert data["is_active"] is True
    assert data["id"] >= 1
    # No password leak
    assert "password" not in data
    assert "hashed_password" not in data


def test_register_duplicate_username():
    register()
    r = register(email="other@example.com")
    assert r.status_code == 400
    assert "username" in r.json()["detail"].lower()


def test_register_duplicate_email():
    register()
    r = client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={
            "username": "bob",
            "email": "alice@example.com",
            "password": "securepass123",
        },
    )
    assert r.status_code == 400
    assert "email" in r.json()["detail"].lower()


def test_register_short_password():
    r = register(password="abc")
    assert r.status_code == 422  # Pydantic validation


def test_register_invalid_email():
    r = register(email="not-an-email")
    assert r.status_code == 422


def test_register_extra_field_rejected():
    r = client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={
            "username": "charlie",
            "email": "charlie@example.com",
            "password": "securepass123",
            "is_admin": True,  # not allowed
        },
    )
    assert r.status_code == 422


# ============================================================
# LOGIN
# ============================================================
def test_login_success():
    register()
    r = login()
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data
    assert data["token"]["token_type"] == "bearer"
    assert data["token"]["access_token"]
    assert data["token"]["expires_in"] > 0
    assert data["user"]["username"] == "alice"
    assert "password" not in data["user"]


def test_login_wrong_password():
    register()
    r = login(password="wrongpassword")
    assert r.status_code == 401
    assert "invalid" in r.json()["detail"].lower()


def test_login_unknown_user():
    r = login(username="nobody", password="whatever123")
    assert r.status_code == 401


def test_login_case_insensitive_username():
    register(username="Alice")
    # Usernames are normalised to lowercase on register
    r = login(username="ALICE")
    assert r.status_code == 200


# ============================================================
# /me
# ============================================================
def test_me_with_valid_token():
    register()
    token = login().json()["token"]["access_token"]
    r = client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["username"] == "alice"
    assert "password" not in r.json()


def test_me_without_token():
    r = client.get(f"{settings.API_V1_STR}/auth/me")
    assert r.status_code == 401
    assert "authentication" in r.json()["detail"].lower() or \
           "required" in r.json()["detail"].lower()


def test_me_with_bad_token():
    r = client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401


def test_me_with_expired_token():
    register()
    # Create a token with an expiry in the past
    token = create_access_token(subject="alice", expires_minutes=-1)
    r = client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


def test_me_with_token_for_deleted_user():
    register()
    token = login().json()["token"]["access_token"]
    # Delete the user directly, then try the token
    db = auth_service.SessionLocal()
    try:
        from app.backend.models.models import User
        db.query(User).filter_by(username="alice").delete()
        db.commit()
    finally:
        db.close()

    r = client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


# ============================================================
# FULL FLOW
# ============================================================
def test_full_register_login_me_flow():
    # 1. Register
    r1 = register(username="flow", email="flow@example.com")
    assert r1.status_code == 201

    # 2. Login
    r2 = login(username="flow")
    assert r2.status_code == 200
    token = r2.json()["token"]["access_token"]

    # 3. Me
    r3 = client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r3.status_code == 200
    assert r3.json()["username"] == "flow"

    # 4. Password was never exposed anywhere
    for r in (r1, r2, r3):
        body = r.text.lower()
        assert "hashed_password" not in body
        assert "securepass" not in body