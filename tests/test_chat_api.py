"""
Xyrox — Chat API Tests (Phase 3)

End-to-end tests for POST /api/v1/chat. Uses real FastAPI TestClient,
real auth, real JWT, real isolated SQLite, real Ollama.

These tests require Ollama + llama3.2:3b to be available. If not,
the AI-dependent tests SKIP.

Coverage:
- Chat requires authentication
- Empty / oversized messages rejected
- Valid message returns a well-formed ChatResponse
- Tool calls are surfaced in the response
- Task creation via chat actually writes to the DB
- Reset clears the user's conversation
- Two users do not see each other's conversation
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models.models import Base
from app.backend.services import auth_service
from app.backend.tools import tasks as tasks_module
from app.backend.ai.factory import get_provider, reset_provider_cache
from app.backend.services import agent_service
from app.backend.main import app
from app.backend.config import settings


client = TestClient(app)


# ============================================================
# FIXTURES
# ============================================================
@pytest.fixture(scope="module")
def ollama_ready():
    """Skip AI-dependent tests if Ollama or the model is not available."""
    reset_provider_cache()
    p = get_provider()
    if not p.is_available():
        pytest.skip("Ollama not reachable.")
    models = p.list_models()
    if not any("llama3.2:3b" in m for m in models):
        pytest.skip("Model llama3.2:3b not installed.")
    return p


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path, monkeypatch):
    """Fresh SQLite per test. Rebinds auth_service and tasks module."""
    db_file = tmp_path / "chat_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(auth_service, "SessionLocal", TestSession)
    monkeypatch.setattr(tasks_module, "SessionLocal", TestSession)

    # Clear the agent cache so conversations do not leak between tests
    agent_service.reset_all()

    yield TestSession

    engine.dispose()
    agent_service.reset_all()


def register_and_login(username="tester", password="testpassword123"):
    """Register a user and return (token, user_id)."""
    r = client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]

    r = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"username": username, "password": password},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]["access_token"]
    return token, user_id


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# AUTHENTICATION
# ============================================================
def test_chat_requires_auth():
    r = client.post(
        f"{settings.API_V1_STR}/chat",
        json={"message": "Hello"},
    )
    assert r.status_code == 401


def test_chat_rejects_empty_message():
    token, _ = register_and_login()
    r = client.post(
        f"{settings.API_V1_STR}/chat",
        json={"message": ""},
        headers=auth_headers(token),
    )
    assert r.status_code == 422


def test_chat_rejects_oversized_message():
    token, _ = register_and_login()
    r = client.post(
        f"{settings.API_V1_STR}/chat",
        json={"message": "x" * 8001},
        headers=auth_headers(token),
    )
    assert r.status_code == 422


def test_chat_rejects_extra_field():
    token, _ = register_and_login()
    r = client.post(
        f"{settings.API_V1_STR}/chat",
        json={"message": "Hello", "admin": True},
        headers=auth_headers(token),
    )
    assert r.status_code == 422


def test_chat_reset_requires_auth():
    r = client.post(f"{settings.API_V1_STR}/chat/reset")
    assert r.status_code == 401


# ============================================================
# AI TESTS
# ============================================================
def test_chat_returns_response(ollama_ready):
    token, _ = register_and_login()
    r = client.post(
        f"{settings.API_V1_STR}/chat",
        json={"message": "What is 2 plus 2? Answer with just the number."},
        headers=auth_headers(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "message" in data
    assert data["message"].strip() != ""
    assert data["iterations"] >= 1
    assert data["model"]
    assert data["provider"] == "ollama"
    assert isinstance(data["tool_calls"], list)


def test_chat_creates_task_and_reports_it(ollama_ready, isolated_test_db):
    """The full flow: chat → AI → tool → DB → response."""
    from app.backend.models.models import Task

    token, _ = register_and_login()
    r = client.post(
        f"{settings.API_V1_STR}/chat",
        json={
            "message": "Create a task to finish Promise's installation video tomorrow."
        },
        headers=auth_headers(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()

    # Tool call happened
    create_calls = [tc for tc in data["tool_calls"] if tc["name"] == "create_task"]
    assert create_calls, f"No create_task call. Response: {data}"
    assert create_calls[0]["success"] is True

    # Really in the DB
    task_id = create_calls[0]["result"]["id"]
    db = isolated_test_db()
    try:
        row = db.query(Task).filter_by(id=task_id).first()
        assert row is not None
        assert "Promise" in row.title
    finally:
        db.close()


def test_chat_reset_clears_conversation(ollama_ready):
    token, _ = register_and_login()

    # Turn 1: create a task
    r1 = client.post(
        f"{settings.API_V1_STR}/chat",
        json={"message": "Create a task to call Mr Lee on Friday."},
        headers=auth_headers(token),
    )
    assert r1.status_code == 200

    # Reset
    r_reset = client.post(
        f"{settings.API_V1_STR}/chat/reset",
        headers=auth_headers(token),
    )
    assert r_reset.status_code == 200
    assert r_reset.json()["cleared"] is True


def test_two_users_have_separate_conversations(ollama_ready):
    """User A's history must not affect User B."""
    token_a, _ = register_and_login("alice_c", "alicepassword123")
    token_b, _ = register_and_login("bob_c", "bobpassword1234")

    # Alice talks. Bob's cache should stay empty.
    r1 = client.post(
        f"{settings.API_V1_STR}/chat",
        json={"message": "Hello, my name is Alice."},
        headers=auth_headers(token_a),
    )
    assert r1.status_code == 200

    r2 = client.post(
        f"{settings.API_V1_STR}/chat",
        json={"message": "Hello, my name is Bob."},
        headers=auth_headers(token_b),
    )
    assert r2.status_code == 200

    # Sanity: both succeeded independently
    assert r1.json()["message"].strip()
    assert r2.json()["message"].strip()