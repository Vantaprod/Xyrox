"""
Xyrox — Calculation Tests (Phase 4.2)

Proves that every number is computed from the real database and
never from the AI. Uses isolated SQLite per test.
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models.models import Base
from app.backend.services import calculations as calc
from app.backend.tools import tasks as tasks_module
from app.backend.tools import work_logs as wl_module


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "calc_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(calc, "SessionLocal", TestSession)
    monkeypatch.setattr(tasks_module, "SessionLocal", TestSession)
    monkeypatch.setattr(wl_module, "SessionLocal", TestSession)

    yield TestSession

    engine.dispose()


def _log(activity, days_ago=0, status="completed", minutes=None, customer=None):
    """Insert a work log directly into the test DB."""
    db = calc.SessionLocal()
    try:
        user = calc._get_default_user(db)
        from app.backend.models.models import WorkLog
        wl = WorkLog(
            work_date=datetime.now(timezone.utc) - timedelta(days=days_ago),
            activity=activity,
            status=status,
            duration_minutes=minutes,
            customer=customer,
            user_id=user.id,
            source="chat",
            ai_confidence="high",
        )
        db.add(wl)
        db.commit()
        return wl.id
    finally:
        db.close()


def _task(title, status="pending", priority="medium", due_days_ago=None):
    db = calc.SessionLocal()
    try:
        user = calc._get_default_user(db)
        from app.backend.models.models import Task
        t = Task(
            title=title,
            status=status,
            priority=priority,
            user_id=user.id,
            source="chat",
            ai_confidence="high",
        )
        if due_days_ago is not None:
            t.due_date = datetime.now(timezone.utc) - timedelta(days=due_days_ago)
        db.add(t)
        db.commit()
        return t.id
    finally:
        db.close()


# ============================================================
# WORK LOG TOTALS
# ============================================================
def test_work_log_totals_empty():
    now = datetime.now(timezone.utc)
    result = calc.work_log_totals(
        (now - timedelta(days=1)).isoformat(),
        (now + timedelta(days=1)).isoformat(),
    )
    assert result["total_logs"] == 0
    assert result["total_minutes"] == 0
    assert result["total_hours"] == 0.0
    assert result["status_breakdown"] == {}
    assert result["distinct_customers"] == []
    assert result["distinct_customer_count"] == 0


def test_work_log_totals_counts_real_rows():
    _log("A", days_ago=0)
    _log("B", days_ago=0)
    _log("C", days_ago=1)

    now = datetime.now(timezone.utc)
    result = calc.work_log_totals(
        (now - timedelta(days=2)).isoformat(),
        (now + timedelta(days=1)).isoformat(),
    )
    assert result["total_logs"] == 3


def test_work_log_totals_date_filter():
    _log("Recent", days_ago=0)
    _log("Old", days_ago=10)

    now = datetime.now(timezone.utc)
    result = calc.work_log_totals(
        (now - timedelta(days=2)).isoformat(),
        (now + timedelta(days=1)).isoformat(),
    )
    assert result["total_logs"] == 1


def test_work_log_totals_sums_durations():
    _log("A", days_ago=0, minutes=30)
    _log("B", days_ago=0, minutes=45)
    _log("C", days_ago=0, minutes=90)

    now = datetime.now(timezone.utc)
    result = calc.work_log_totals(
        (now - timedelta(days=1)).isoformat(),
        (now + timedelta(days=1)).isoformat(),
    )
    assert result["total_minutes"] == 165
    assert result["total_hours"] == 2.75


def test_work_log_totals_status_breakdown():
    _log("A", status="completed")
    _log("B", status="completed")
    _log("C", status="in_progress")

    now = datetime.now(timezone.utc)
    result = calc.work_log_totals(
        (now - timedelta(days=1)).isoformat(),
        (now + timedelta(days=1)).isoformat(),
    )
    assert result["status_breakdown"]["completed"] == 2
    assert result["status_breakdown"]["in_progress"] == 1


def test_work_log_totals_distinct_customers():
    _log("A", customer="Promise")
    _log("B", customer="Promise")
    _log("C", customer="Seun")
    _log("D", customer=None)

    now = datetime.now(timezone.utc)
    result = calc.work_log_totals(
        (now - timedelta(days=1)).isoformat(),
        (now + timedelta(days=1)).isoformat(),
    )
    assert result["distinct_customer_count"] == 2
    assert set(result["distinct_customers"]) == {"promise", "seun"}


def test_work_log_totals_rejects_inverted_range():
    now = datetime.now(timezone.utc)
    with pytest.raises(calc.CalculationError):
        calc.work_log_totals(
            now.isoformat(),
            (now - timedelta(days=1)).isoformat(),
        )


def test_work_log_totals_rejects_bad_iso():
    with pytest.raises(calc.CalculationError):
        calc.work_log_totals("not-a-date", "2026-09-30T00:00:00+00:00")


# ============================================================
# DAILY / WEEKLY / MONTHLY WRAPPERS
# ============================================================
def test_daily_summary_defaults_to_today():
    _log("Today's work")
    result = calc.work_log_daily_summary()
    assert result["total_logs"] >= 1
    assert "day" in result


def test_weekly_summary_has_week_bounds():
    result = calc.work_log_weekly_summary()
    assert "week_start" in result
    assert "week_end" in result


def test_monthly_summary_has_month_name():
    result = calc.work_log_monthly_summary(year=2026, month=9)
    assert result["month_name"] == "September"
    assert result["year"] == 2026
    assert result["month"] == 9


def test_monthly_summary_rejects_bad_month():
    with pytest.raises(calc.CalculationError):
        calc.work_log_monthly_summary(year=2026, month=13)


# ============================================================
# TASK TOTALS
# ============================================================
def test_task_totals_empty():
    result = calc.task_totals()
    assert result["total"] == 0
    assert result["by_status"] == {}
    assert result["by_priority"] == {}
    assert result["overdue"] == 0


def test_task_totals_by_status():
    _task("A", status="pending")
    _task("B", status="pending")
    _task("C", status="completed")

    result = calc.task_totals()
    assert result["total"] == 3
    assert result["by_status"]["pending"] == 2
    assert result["by_status"]["completed"] == 1


def test_task_totals_by_priority():
    _task("A", priority="high")
    _task("B", priority="high")
    _task("C", priority="low")

    result = calc.task_totals()
    assert result["by_priority"]["high"] == 2
    assert result["by_priority"]["low"] == 1


def test_task_totals_overdue():
    _task("Overdue", due_days_ago=5, status="pending")
    _task("Future", due_days_ago=-5, status="pending")   # due in 5 days
    _task("Done overdue", due_days_ago=5, status="completed")

    result = calc.task_totals()
    assert result["overdue"] == 1


# ============================================================
# COMBINED REPORT DATA
# ============================================================
def test_combined_report_data_shape():
    _log("A", days_ago=0, minutes=30)
    _task("Task A")

    now = datetime.now(timezone.utc)
    result = calc.combined_report_data(
        (now - timedelta(days=1)).isoformat(),
        (now + timedelta(days=1)).isoformat(),
    )
    assert "period" in result
    assert "work" in result
    assert "tasks" in result
    assert result["work"]["total_logs"] == 1
    assert result["tasks"]["total"] == 1


# ============================================================
# MASTER COMMAND §53, TEST 6 — "How many installation videos..."
# ============================================================
def test_acceptance_test6_verified_count():
    """
    Master Command §53, Test 6:
    'How many installation videos did I complete this week?'
    System queries the database. It must NOT guess.
    """
    # Insert 5 completed installation video logs today
    for i in range(5):
        _log(f"Installation video {i+1}", status="completed", customer="Promise")

    now = datetime.now(timezone.utc)
    result = calc.work_log_totals(
        (now - timedelta(days=1)).isoformat(),
        (now + timedelta(days=1)).isoformat(),
    )
    assert result["total_logs"] == 5
    assert result["status_breakdown"]["completed"] == 5


# ============================================================
# MASTER COMMAND §48 — DETERMINISTIC VERIFICATION
# ============================================================
def test_calculations_are_deterministic():
    """Same DB → same numbers. Always."""
    _log("A", days_ago=0, minutes=30)
    _log("B", days_ago=0, minutes=45)

    now = datetime.now(timezone.utc)
    a = calc.work_log_totals(
        (now - timedelta(days=1)).isoformat(),
        (now + timedelta(days=1)).isoformat(),
    )
    b = calc.work_log_totals(
        (now - timedelta(days=1)).isoformat(),
        (now + timedelta(days=1)).isoformat(),
    )
    assert a["total_minutes"] == b["total_minutes"] == 75
    assert a["total_logs"] == b["total_logs"] == 2