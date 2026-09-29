"""
Xyrox — Tool Tests (Phase 2, File 8)

These tests hit a REAL SQLite database — but a TEST database, not
the production one. Test isolation (Master Command §40) is enforced
by a pytest fixture that rebinds SessionLocal to a temporary file
for each test. Production data is never touched.

Coverage:
- Registry construction, duplicate rejection, schema generation
- create_task — real DB write + verification
- list_tasks — real DB read, filtering
- complete_task — real DB update
- Input validation for all tools
- Master Command §53, Test 1 (acceptance test)
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models.models import Base
from app.backend.tools import tasks as tasks_module
from app.backend.tools import build_default_registry
from app.backend.tools.base import (
    Tool,
    ToolError,
    ToolNotFoundError,
    ToolValidationError,
)
from app.backend.tools.registry import ToolRegistry


# ============================================================
# FIXTURE: isolated test database for every test
# ============================================================
@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path, monkeypatch):
    """
    For each test, create a fresh SQLite file in a temp folder and
    rebind the SessionLocal used by tools.tasks. Production
    data/app.db is never touched (Master Command §40).
    """
    db_file = tmp_path / "xyrox_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(bind=engine)

    # Redirect the tools module to this test DB
    monkeypatch.setattr(tasks_module, "SessionLocal", TestSession)

    yield

    engine.dispose()


# ============================================================
# REGISTRY TESTS
# ============================================================
def test_build_default_registry_has_expected_tools():
    r = build_default_registry()
    assert isinstance(r, ToolRegistry)
    assert "create_task" in r
    assert "list_tasks" in r
    assert "complete_task" in r


def test_registry_schema_is_openai_format():
    r = build_default_registry()
    schema = r.to_ai_schema()
    assert isinstance(schema, list)
    # Phase 5.4: 3 task + 2 work_log + 4 report + 1 export + 3 excel = 13 tools
    assert len(schema) == 16
    for entry in schema:
        assert entry["type"] == "function"
        assert "name" in entry["function"]
        assert "description" in entry["function"]
        assert "parameters" in entry["function"]
        assert entry["function"]["parameters"]["type"] == "object"


def test_registry_rejects_duplicate_registration():
    r = ToolRegistry()
    from app.backend.tools.tasks import create_task

    t = Tool(name="dup", description="x", parameters={}, func=create_task)
    r.register(t)
    with pytest.raises(ToolError):
        r.register(t)


def test_registry_execute_unknown_tool_raises():
    r = build_default_registry()
    with pytest.raises(ToolNotFoundError):
        r.execute("this_tool_does_not_exist", {})


def test_registry_execute_wraps_unexpected_errors():
    """A tool whose function raises RuntimeError must be wrapped."""
    def boom(**kwargs):
        raise RuntimeError("boom")

    r = ToolRegistry()
    r.register(Tool(name="boom", description="x", parameters={}, func=boom))
    with pytest.raises(ToolError):
        r.execute("boom", {})


def test_registry_execute_rejects_non_dict_arguments():
    r = build_default_registry()
    with pytest.raises(ToolError):
        r.execute("create_task", "not a dict")  # type: ignore


# ============================================================
# create_task
# ============================================================
def test_create_task_minimal():
    r = build_default_registry()
    result = r.execute("create_task", {
        "title": "Finish Promise's installation video",
    })
    assert result["id"] >= 1
    assert result["title"] == "Finish Promise's installation video"
    assert result["status"] == "pending"
    assert result["priority"] == "medium"


def test_create_task_with_due_date_and_priority():
    r = build_default_registry()
    result = r.execute("create_task", {
        "title": "Deliver weekly report",
        "due_date": "2026-10-01T17:00:00+00:00",
        "priority": "high",
    })
    assert result["priority"] == "high"
    assert result["due_date"] is not None
    assert "2026-10-01" in result["due_date"]


def test_create_task_rejects_empty_title():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("create_task", {"title": ""})


def test_create_task_rejects_whitespace_title():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("create_task", {"title": "   "})


def test_create_task_rejects_invalid_priority():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("create_task", {"title": "X", "priority": "super_urgent"})


def test_create_task_rejects_invalid_status():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("create_task", {"title": "X", "status": "almost_done"})


def test_create_task_rejects_invalid_due_date():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("create_task", {"title": "X", "due_date": "not-a-real-date"})


def test_create_task_persists_to_real_database():
    """End-to-end proof: task actually persists in SQLite."""
    from app.backend.tools.tasks import SessionLocal as TestSession
    from app.backend.models.models import Task

    r = build_default_registry()
    result = r.execute("create_task", {"title": "Persistent task"})

    db = TestSession()
    try:
        row = db.query(Task).filter_by(id=result["id"]).first()
        assert row is not None, "Task was not written to the database."
        assert row.title == "Persistent task"
        assert row.status == "pending"
    finally:
        db.close()


# ============================================================
# list_tasks
# ============================================================
def test_list_tasks_empty():
    r = build_default_registry()
    result = r.execute("list_tasks", {})
    assert result["count"] == 0
    assert result["tasks"] == []


def test_list_tasks_returns_created_tasks():
    r = build_default_registry()
    r.execute("create_task", {"title": "Task A"})
    r.execute("create_task", {"title": "Task B"})
    result = r.execute("list_tasks", {})
    assert result["count"] == 2
    titles = {t["title"] for t in result["tasks"]}
    assert titles == {"Task A", "Task B"}


def test_list_tasks_filter_by_status():
    r = build_default_registry()
    r.execute("create_task", {"title": "Task A", "status": "pending"})
    r.execute("create_task", {"title": "Task B", "status": "in_progress"})
    result = r.execute("list_tasks", {"status": "in_progress"})
    assert result["count"] == 1
    assert result["tasks"][0]["title"] == "Task B"


def test_list_tasks_rejects_bad_limit():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("list_tasks", {"limit": 0})


def test_list_tasks_rejects_bad_status():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("list_tasks", {"status": "fictional_status"})


# ============================================================
# complete_task
# ============================================================
def test_complete_task_updates_status():
    r = build_default_registry()
    created = r.execute("create_task", {"title": "Do me"})
    result = r.execute("complete_task", {"task_id": created["id"]})
    assert result["id"] == created["id"]
    assert result["status"] == "completed"
    assert result["completed_at"] is not None


def test_complete_task_rejects_missing_task():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("complete_task", {"task_id": 999999})


def test_complete_task_rejects_negative_id():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("complete_task", {"task_id": -1})


def test_complete_task_persists_to_real_database():
    """End-to-end proof: status change actually persists."""
    from app.backend.tools.tasks import SessionLocal as TestSession
    from app.backend.models.models import Task

    r = build_default_registry()
    created = r.execute("create_task", {"title": "Persist completion"})
    r.execute("complete_task", {"task_id": created["id"]})

    db = TestSession()
    try:
        row = db.query(Task).filter_by(id=created["id"]).first()
        assert row is not None
        assert row.status == "completed"
        assert row.completed_at is not None
    finally:
        db.close()


# ============================================================
# MASTER COMMAND §53 — ACCEPTANCE TEST 1
# ============================================================
def test_acceptance_create_task_from_natural_language():
    """
    Master Command §53, Test 1:
    'User types: Create a task to finish Promise's installation video tomorrow.'
    Result: Real database task created.'

    We simulate the tool call that the AI would produce from that
    sentence. The tool writes to the real (test) database.
    """
    r = build_default_registry()
    result = r.execute("create_task", {
        "title": "Finish Promise's installation video",
        "due_date": "2026-09-29T17:00:00+00:00",
        "priority": "high",
    })

    assert result["id"] >= 1
    assert result["title"] == "Finish Promise's installation video"
    assert result["priority"] == "high"
    assert "2026-09-29" in result["due_date"]

    # Confirm it is retrievable through the real read path
    listed = r.execute("list_tasks", {})
    assert any(t["id"] == result["id"] for t in listed["tasks"])