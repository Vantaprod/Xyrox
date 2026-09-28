"""
Xyrox — Report Tests (Phase 4.3)

Tests the report builder and report tools. Uses isolated SQLite.
Proves that reports use verified numbers, never invent data, and
persist as drafts.
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models.models import Base
from app.backend.services import report_builder
from app.backend.services import calculations as calc
from app.backend.tools import tasks as tasks_module
from app.backend.tools import work_logs as wl_module
from app.backend.tools import reports as reports_module
from app.backend.tools import build_default_registry
from app.backend.tools.base import ToolValidationError


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "reports_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Rebind SessionLocal everywhere it lives
    monkeypatch.setattr(calc, "SessionLocal", TestSession)
    monkeypatch.setattr(tasks_module, "SessionLocal", TestSession)
    monkeypatch.setattr(wl_module, "SessionLocal", TestSession)
    monkeypatch.setattr(report_builder, "SessionLocal", TestSession)

    yield TestSession

    engine.dispose()


def _log(activity, days_ago=0, status="completed", customer=None, minutes=None):
    db = report_builder.SessionLocal()
    try:
        user = calc._get_default_user(db)
        from app.backend.models.models import WorkLog
        wl = WorkLog(
            work_date=datetime.now(timezone.utc) - timedelta(days=days_ago),
            activity=activity,
            status=status,
            customer=customer,
            duration_minutes=minutes,
            user_id=user.id,
            source="chat",
            ai_confidence="high",
        )
        db.add(wl)
        db.commit()
        return wl.id
    finally:
        db.close()


def _task(title, status="pending", priority="medium"):
    db = report_builder.SessionLocal()
    try:
        user = calc._get_default_user(db)
        from app.backend.models.models import Task
        t = Task(
            title=title, status=status, priority=priority,
            user_id=user.id, source="chat", ai_confidence="high",
        )
        db.add(t)
        db.commit()
        return t.id
    finally:
        db.close()


# ============================================================
# REGISTRATION
# ============================================================
def test_registry_contains_report_tools():
    r = build_default_registry()
    assert "create_daily_report" in r
    assert "create_weekly_report" in r
    assert "create_monthly_report" in r
    assert "get_report" in r


def test_registry_schema_includes_report_tools():
    r = build_default_registry()
    names = {t["function"]["name"] for t in r.to_ai_schema()}
    assert {
        "create_task", "list_tasks", "complete_task",
        "log_work", "get_work_logs",
        "create_daily_report", "create_weekly_report",
        "create_monthly_report", "get_report",
    } <= names


# ============================================================
# DAILY REPORT
# ============================================================
def test_daily_report_empty_day():
    r = build_default_registry()
    result = r.execute("create_daily_report", {})
    assert result["report_type"] == "daily"
    assert result["verified_numbers"]["total_logs"] == 0
    assert result["verified_numbers"]["total_hours"] == 0.0
    assert result["sections"]["work_completed"] == []
    assert result["report_id"] >= 1
    assert result["status"] == "draft"


def test_daily_report_with_work():
    _log("Edited three videos", customer="Promise")
    _log("Installed system at client", customer="Seun", status="in_progress")

    r = build_default_registry()
    result = r.execute("create_daily_report", {})
    assert result["verified_numbers"]["total_logs"] == 2
    assert len(result["sections"]["work_completed"]) == 1
    assert len(result["sections"]["work_in_progress"]) == 1
    assert result["sections"]["work_completed"][0]["customer"] == "Promise"


def test_daily_report_verified_numbers_match_calculations():
    """The report's numbers must come from the calculation layer."""
    _log("A", minutes=30)
    _log("B", minutes=45)

    r = build_default_registry()
    result = r.execute("create_daily_report", {})

    now = datetime.now(timezone.utc)
    direct = calc.work_log_daily_summary()

    assert result["verified_numbers"]["total_logs"] == direct["total_logs"]
    assert result["verified_numbers"]["total_minutes"] == direct["total_minutes"]
    assert result["verified_numbers"]["total_minutes"] == 75


def test_daily_report_flags_missing_sections():
    """The report must tell the AI which sections lack data."""
    r = build_default_registry()
    result = r.execute("create_daily_report", {})
    assert "challenges" in result["missing_sections"]
    assert "tomorrow_priorities" in result["missing_sections"]


def test_daily_report_persists_in_database():
    from app.backend.models.models import Report

    r = build_default_registry()
    result = r.execute("create_daily_report", {})
    report_id = result["report_id"]

    db = report_builder.SessionLocal()
    try:
        row = db.query(Report).filter_by(id=report_id).first()
        assert row is not None
        assert row.report_type == "daily"
        assert row.status == "draft"
        assert row.data is not None
    finally:
        db.close()


# ============================================================
# WEEKLY / MONTHLY
# ============================================================
def test_weekly_report_shape():
    _log("A", days_ago=0)
    r = build_default_registry()
    result = r.execute("create_weekly_report", {})
    assert result["report_type"] == "weekly"
    assert "week_start" in result["period"]
    assert "week_end" in result["period"]
    assert result["verified_numbers"]["total_logs"] >= 1


def test_monthly_report_shape():
    r = build_default_registry()
    result = r.execute("create_monthly_report", {"year": 2026, "month": 9})
    assert result["report_type"] == "monthly"
    assert result["period"]["month_name"] == "September"
    assert result["period"]["year"] == 2026


def test_monthly_report_rejects_bad_month():
    r = build_default_registry()
    with pytest.raises(Exception):
        r.execute("create_monthly_report", {"year": 2026, "month": 13})


# ============================================================
# GET REPORT
# ============================================================
def test_get_report_by_id():
    r = build_default_registry()
    created = r.execute("create_daily_report", {})
    fetched = r.execute("get_report", {"report_id": created["report_id"]})
    assert fetched["id"] == created["report_id"]
    assert fetched["report_type"] == "daily"


def test_get_report_missing():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("get_report", {"report_id": 999999})


def test_get_report_rejects_bad_id():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("get_report", {"report_id": -5})


# ============================================================
# EXTRA ARGS REJECTION
# ============================================================
def test_create_daily_report_rejects_extra_args():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("create_daily_report", {"bogus": True})


# ============================================================
# MASTER COMMAND §53, TEST 4 — report from real records
# ============================================================
def test_acceptance_test4_weekly_report_from_real_records():
    """
    'Generate my weekly report.'
    System collects real records, calculates real totals,
    generates a report draft, flags missing info.
    """
    for i in range(5):
        _log(f"Installation video {i+1}", status="completed", customer="Promise", minutes=60)
    _log("Reviewed client feedback", status="in_progress", customer="Seun")
    _task("Follow up with Mr Lee", status="pending", priority="high")

    r = build_default_registry()
    result = r.execute("create_weekly_report", {})

    # Real verified numbers
    assert result["verified_numbers"]["total_logs"] == 6
    assert result["verified_numbers"]["total_minutes"] == 300
    assert result["verified_numbers"]["total_hours"] == 5.0
    assert result["verified_numbers"]["status_breakdown"]["completed"] == 5
    assert result["verified_numbers"]["status_breakdown"]["in_progress"] == 1

    # Sections reflect real data
    assert len(result["sections"]["work_completed"]) == 5
    assert len(result["sections"]["work_in_progress"]) == 1
    assert len(result["sections"]["outstanding_tasks"]) == 1

    # Missing sections flagged, not invented
    assert "challenges" in result["missing_sections"]
    assert "next_week_priorities" in result["missing_sections"]

    # Persisted
    assert result["report_id"] >= 1
    assert result["status"] == "draft"


# ============================================================
# HONESTY: NO FABRICATION
# ============================================================
def test_report_honesty_reminder_present():
    """Every draft must contain a reminder to the AI not to invent."""
    r = build_default_registry()
    result = r.execute("create_daily_report", {})
    assert "honesty_reminder" in result
    assert "Do not invent" in result["honesty_reminder"] or \
           "do not invent" in result["honesty_reminder"].lower()


def test_report_with_no_data_produces_zeroes_not_placeholders():
    """Empty day → empty numbers. No fake numbers, no fake sections."""
    r = build_default_registry()
    result = r.execute("create_daily_report", {})
    assert result["verified_numbers"]["total_logs"] == 0
    assert result["verified_numbers"]["total_minutes"] == 0
    assert result["verified_numbers"]["status_breakdown"] == {}
    assert result["sections"]["work_completed"] == []