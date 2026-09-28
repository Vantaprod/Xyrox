"""
Xyrox — Work Log Tests (Phase 4, File 2)

Isolated-DB tests for log_work and get_work_logs.
Same rigor as Phase 2 tool tests.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models.models import Base
from app.backend.tools import work_logs as wl_module
from app.backend.tools import tasks as tasks_module
from app.backend.tools import build_default_registry
from app.backend.tools.base import ToolValidationError


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "worklogs_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(wl_module, "SessionLocal", TestSession)
    monkeypatch.setattr(tasks_module, "SessionLocal", TestSession)

    yield TestSession

    engine.dispose()


# ============================================================
# REGISTRATION
# ============================================================
def test_registry_contains_work_log_tools():
    r = build_default_registry()
    assert "log_work" in r
    assert "get_work_logs" in r


def test_registry_schema_includes_work_log_tools():
    r = build_default_registry()
    names = {t["function"]["name"] for t in r.to_ai_schema()}
    assert {"log_work", "get_work_logs", "create_task", "list_tasks", "complete_task"} <= names


# ============================================================
# log_work — happy paths
# ============================================================
def test_log_work_minimal():
    r = build_default_registry()
    result = r.execute("log_work", {"activity": "Edited three videos"})
    assert result["id"] >= 1
    assert result["activity"] == "Edited three videos"
    assert result["status"] == "completed"
    assert result["work_date"] is not None


def test_log_work_with_all_fields():
    r = build_default_registry()
    result = r.execute("log_work", {
        "activity": "Shot Promise installation video",
        "customer": "Promise",
        "result": "Raw footage delivered",
        "status": "in_progress",
        "duration_minutes": 90,
        "notes": "Needs color grade",
        "work_date": "2026-09-27T15:00:00+00:00",
    })
    assert result["customer"] == "Promise"
    assert result["status"] == "in_progress"
    assert result["duration_minutes"] == 90
    assert result["notes"] == "Needs color grade"
    assert "2026-09-27" in result["work_date"]


def test_log_work_defaults_to_today():
    r = build_default_registry()
    result = r.execute("log_work", {"activity": "Reviewed footage"})
    assert result["work_date"] is not None
    assert "T" in result["work_date"]  # ISO format


# ============================================================
# log_work — validation
# ============================================================
def test_log_work_rejects_empty_activity():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("log_work", {"activity": ""})


def test_log_work_rejects_whitespace_activity():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("log_work", {"activity": "    "})


def test_log_work_rejects_invalid_status():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("log_work", {"activity": "X", "status": "almost"})


def test_log_work_rejects_negative_duration():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("log_work", {"activity": "X", "duration_minutes": -5})


def test_log_work_rejects_oversized_duration():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("log_work", {"activity": "X", "duration_minutes": 2000})


def test_log_work_rejects_invalid_date():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("log_work", {"activity": "X", "work_date": "yesterday"})


def test_log_work_rejects_invalid_source():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("log_work", {"activity": "X", "source": "telepathy"})


def test_log_work_persists_to_real_database():
    from app.backend.models.models import WorkLog
    from app.backend.tools.work_logs import SessionLocal as TestSession

    r = build_default_registry()
    result = r.execute("log_work", {"activity": "Persistent log"})

    db = TestSession()
    try:
        row = db.query(WorkLog).filter_by(id=result["id"]).first()
        assert row is not None
        assert row.activity == "Persistent log"
    finally:
        db.close()


# ============================================================
# get_work_logs
# ============================================================
def test_get_work_logs_empty():
    r = build_default_registry()
    result = r.execute("get_work_logs", {})
    assert result["count"] == 0
    assert result["logs"] == []


def test_get_work_logs_returns_logs():
    r = build_default_registry()
    r.execute("log_work", {"activity": "A"})
    r.execute("log_work", {"activity": "B"})
    result = r.execute("get_work_logs", {})
    assert result["count"] == 2
    assert {log["activity"] for log in result["logs"]} == {"A", "B"}


def test_get_work_logs_filters_by_customer():
    r = build_default_registry()
    r.execute("log_work", {"activity": "A", "customer": "Promise"})
    r.execute("log_work", {"activity": "B", "customer": "Seun"})
    result = r.execute("get_work_logs", {"customer": "Promise"})
    assert result["count"] == 1
    assert result["logs"][0]["customer"] == "Promise"


def test_get_work_logs_filters_by_status():
    r = build_default_registry()
    r.execute("log_work", {"activity": "A", "status": "completed"})
    r.execute("log_work", {"activity": "B", "status": "in_progress"})
    result = r.execute("get_work_logs", {"status": "in_progress"})
    assert result["count"] == 1
    assert result["logs"][0]["status"] == "in_progress"


def test_get_work_logs_filters_by_date_range():
    r = build_default_registry()
    r.execute("log_work", {"activity": "Old", "work_date": "2026-09-01T10:00:00+00:00"})
    r.execute("log_work", {"activity": "New", "work_date": "2026-09-27T10:00:00+00:00"})
    result = r.execute("get_work_logs", {
        "from_date": "2026-09-20T00:00:00+00:00",
        "to_date": "2026-09-30T00:00:00+00:00",
    })
    assert result["count"] == 1
    assert result["logs"][0]["activity"] == "New"


def test_get_work_logs_rejects_bad_limit():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("get_work_logs", {"limit": 0})


def test_get_work_logs_rejects_bad_status():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("get_work_logs", {"status": "fictional"})


def test_get_work_logs_rejects_inverted_date_range():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("get_work_logs", {
            "from_date": "2026-09-30T00:00:00+00:00",
            "to_date": "2026-09-01T00:00:00+00:00",
        })


def test_get_work_logs_nonexistent_project_returns_empty():
    r = build_default_registry()
    r.execute("log_work", {"activity": "A"})
    result = r.execute("get_work_logs", {"project": "Does Not Exist"})
    assert result["count"] == 0
    assert result["logs"] == []


# ============================================================
# MASTER COMMAND §53, TEST 3 — acceptance
# ============================================================
def test_acceptance_log_five_installation_videos():
    """
    Master Command §53, Test 3:
    'User says: I completed five installation videos this week.'
    System records the actual work.
    """
    r = build_default_registry()
    result = r.execute("log_work", {
        "activity": "Completed five installation videos",
        "status": "completed",
        "source": "voice",
    })
    assert result["id"] >= 1
    assert "five installation videos" in result["activity"]

    # And it is retrievable
    listed = r.execute("get_work_logs", {"status": "completed"})
    assert any(log["id"] == result["id"] for log in listed["logs"])