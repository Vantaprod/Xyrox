"""
Xyrox — Phase 1 Tests

These tests verify the backend is genuinely working:
- The API responds.
- The database file is created.
- The models import correctly.

Run with:
    python -m pytest tests/ -v
"""

from fastapi.testclient import TestClient

from app.backend.main import app
from app.backend.config import settings

client = TestClient(app)


# ============================================================
# API TESTS
# ============================================================
def test_root_endpoint():
    """The root endpoint should return Xyrox status info."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Xyrox"
    assert data["status"] == "online"
    assert data["ai_provider"] == "local"
    assert "version" in data
    assert "database" in data


def test_health_endpoint():
    """The health endpoint should always report healthy."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


# ============================================================
# CONFIG TESTS
# ============================================================
def test_config_loads():
    """Configuration must load with correct defaults."""
    assert settings.PROJECT_NAME == "Xyrox"
    assert settings.API_V1_STR == "/api/v1"
    assert settings.DATABASE_URL.startswith("sqlite")
    assert settings.TZ == "Africa/Lagos"


# ============================================================
# DATABASE TESTS
# ============================================================
def test_database_tables_exist():
    """
    Verify the four Phase-1 tables were actually created
    inside the SQLite database. This proves the models module
    was imported correctly and create_all() ran.
    """
    from app.backend.database.db import engine
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    assert "users" in tables, "users table was not created"
    assert "projects" in tables, "projects table was not created"
    assert "tasks" in tables, "tasks table was not created"
    assert "work_logs" in tables, "work_logs table was not created"


def test_models_import():
    """All model classes must be importable."""
    from app.backend.models.models import User, Project, Task, WorkLog

    # Basic sanity — these classes must exist and be mapped to tables
    assert User.__tablename__ == "users"
    assert Project.__tablename__ == "projects"
    assert Task.__tablename__ == "tasks"
    assert WorkLog.__tablename__ == "work_logs"


def test_create_and_read_user():
    """
    End-to-end database check:
    Insert a user, read it back, then delete it.
    Proves the DB session and schema actually work.
    """
    from app.backend.database.db import SessionLocal
    from app.backend.models.models import User

    db = SessionLocal()
    try:
        # Create
        test_user = User(
            username="__test_xyrox__",
            email="__test_xyrox__@example.invalid",
            hashed_password="not_a_real_hash",
            full_name="Test User",
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        assert test_user.id is not None

        # Read back
        fetched = db.query(User).filter_by(username="__test_xyrox__").first()
        assert fetched is not None
        assert fetched.email == "__test_xyrox__@example.invalid"

        # Cleanup (so we never pollute the real database)
        db.delete(fetched)
        db.commit()
    finally:
        db.close()