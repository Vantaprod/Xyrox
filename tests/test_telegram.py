"""Xyrox — Telegram Tests (Phase 7.1)"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models.models import Base
from app.backend.services import auth_service
from app.backend.main import app
from app.backend.config import settings
from app.backend.integrations import telegram as tg
from app.backend.tools import build_default_registry
from app.backend.tools.base import ToolValidationError


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "tg_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    from app.backend.api import telegram as tg_api
    from app.backend.tools import telegram_tools

    monkeypatch.setattr(auth_service, "SessionLocal", TestSession)
    monkeypatch.setattr(tg_api, "SessionLocal", TestSession)
    monkeypatch.setattr(telegram_tools, "SessionLocal", TestSession)

    yield TestSession

    engine.dispose()


@pytest.fixture
def no_token(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")


@pytest.fixture
def with_token(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "fake:token")
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_CHAT_IDS", "")


def _auth():
    r = client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={
            "username": "telegram_tester",
            "email": "telegram_tester@example.com",
            "password": "securepass123",
        },
    )
    assert r.status_code == 201, r.text
    r = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"username": "telegram_tester", "password": "securepass123"},
    )
    token = r.json()["token"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# REGISTRATION
# ============================================================
def test_telegram_tools_registered():
    r = build_default_registry()
    assert "send_telegram_message" in r
    assert "read_telegram_updates" in r


# ============================================================
# NOT CONFIGURED BEHAVIOR
# ============================================================
def test_status_reports_not_configured(no_token):
    headers = _auth()
    r = client.get(
        f"{settings.API_V1_STR}/telegram/status", headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["configured"] is False


def test_send_returns_503_when_not_configured(no_token):
    headers = _auth()
    r = client.post(
        f"{settings.API_V1_STR}/telegram/send",
        json={"chat_id": 1, "text": "hi", "require_approval": True},
        headers=headers,
    )
    assert r.status_code == 503
    assert "NOT CONFIGURED" in r.json()["detail"]


# ============================================================
# AUTH
# ============================================================
def test_status_requires_auth():
    r = client.get(f"{settings.API_V1_STR}/telegram/status")
    assert r.status_code == 401


def test_tool_rejects_when_not_configured(no_token):
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("send_telegram_message", {"chat_id": 1, "text": "hi"})


# ============================================================
# QUEUE-AND-APPROVE FLOW
# ============================================================
def test_draft_queues_message(with_token):
    headers = _auth()
    r = client.post(
        f"{settings.API_V1_STR}/telegram/send",
        json={"chat_id": 100, "text": "hello", "require_approval": True},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "pending"
    assert data["draft_id"] > 0


def test_list_pending(with_token):
    headers = _auth()
    client.post(
        f"{settings.API_V1_STR}/telegram/send",
        json={"chat_id": 100, "text": "hello", "require_approval": True},
        headers=headers,
    )
    r = client.get(
        f"{settings.API_V1_STR}/telegram/pending", headers=headers,
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["text"] == "hello"


def test_approve_missing_draft_returns_404(with_token):
    headers = _auth()
    r = client.post(
        f"{settings.API_V1_STR}/telegram/approve/99999", headers=headers,
    )
    assert r.status_code == 404


# ============================================================
# WHITELIST
# ============================================================
def test_whitelist_blocks_unauthorized_chat(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "fake:token")
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_CHAT_IDS", "111,222")
    headers = _auth()
    r = client.post(
        f"{settings.API_V1_STR}/telegram/send",
        json={"chat_id": 999, "text": "hi", "require_approval": True},
        headers=headers,
    )
    assert r.status_code == 403


def test_whitelist_allows_authorized_chat(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "fake:token")
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_CHAT_IDS", "111")
    headers = _auth()
    r = client.post(
        f"{settings.API_V1_STR}/telegram/send",
        json={"chat_id": 111, "text": "hi", "require_approval": True},
        headers=headers,
    )
    assert r.status_code == 200


# ============================================================
# WHITELIST HELPERS
# ============================================================
def test_is_authorized_empty_whitelist_allows_all(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_CHAT_IDS", "")
    assert tg.is_authorized(999) is True


def test_is_authorized_with_whitelist(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_CHAT_IDS", "1,2,3")
    assert tg.is_authorized(2) is True
    assert tg.is_authorized(4) is False


def test_is_configured_false_without_token(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    assert tg.is_configured() is False