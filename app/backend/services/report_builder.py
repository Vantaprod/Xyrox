"""
Xyrox — Report Builder (Phase 4.3)

Assembles report drafts by combining:
  1. Verified numbers from the deterministic calculation layer.
  2. Raw work logs and tasks from the database.

Nothing in this module invents data. If a section has no data,
it is reported as empty or "NOT PROVIDED". The AI receives the
structured draft and writes prose around it.

Master Command §18, §20, §21, §22, §24, §48.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.backend.database.db import SessionLocal
from app.backend.models.models import Report, Task, WorkLog
from app.backend.services.calculations import (
    CalculationError,
    _default_day_range,
    _default_month_range,
    _default_week_range,
    _get_default_user,
    task_totals,
    work_log_totals,
)


VALID_REPORT_TYPES = {"daily", "weekly", "monthly"}


# ============================================================
# HELPERS
# ============================================================
def _serialize_work_log(wl: WorkLog) -> dict:
    return {
        "id": wl.id,
        "work_date": wl.work_date.isoformat() if wl.work_date else None,
        "activity": wl.activity,
        "customer": wl.customer,
        "result": wl.result,
        "status": wl.status,
        "duration_minutes": wl.duration_minutes,
        "notes": wl.notes,
        "source": wl.source,
    }


def _serialize_task(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "due_date": t.due_date.isoformat() if t.due_date else None,
    }


def _fetch_work_logs_in_range(db: Session, user_id: int, start, end):
    return (
        db.query(WorkLog)
        .filter(
            WorkLog.user_id == user_id,
            WorkLog.work_date >= start,
            WorkLog.work_date < end,
        )
        .order_by(WorkLog.work_date.asc())
        .all()
    )


def _fetch_outstanding_tasks(db: Session, user_id: int):
    return (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.status.notin_(["completed", "cancelled"]),
        )
        .order_by(Task.due_date.asc().nulls_last(), Task.created_at.asc())
        .all()
    )


def _group_logs_by_status(logs: list[WorkLog]) -> dict:
    """Return {'completed': [...], 'in_progress': [...], ...}."""
    buckets: dict[str, list[dict]] = {}
    for wl in logs:
        buckets.setdefault(wl.status or "unknown", []).append(_serialize_work_log(wl))
    return buckets


def _build_draft(
    db: Session,
    report_type: str,
    start: datetime,
    end: datetime,
    period_label: dict,
) -> dict:
    """
    Build the structured draft. Same shape for all report types.
    """
    user = _get_default_user(db)

    # Verified numbers
    work_numbers = work_log_totals(start.isoformat(), end.isoformat())
    tasks_numbers = task_totals()

    # Raw entries
    logs = _fetch_work_logs_in_range(db, user.id, start, end)
    outstanding = _fetch_outstanding_tasks(db, user.id)

    buckets = _group_logs_by_status(logs)

    # Which sections does the user have data for? Everything else is
    # explicitly marked missing — never invented.
    sections_have_data = {
        "work_completed": bool(buckets.get("completed")),
        "work_in_progress": bool(buckets.get("in_progress")),
        "blocked": bool(buckets.get("blocked")),
        "outstanding_tasks": bool(outstanding),
    }

    missing_sections = [
        "challenges",
        "important_communications",
        "key_achievements",
        "tomorrow_priorities",
        "next_week_priorities",
    ]

    draft = {
        "report_type": report_type,
        "period": {
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            **period_label,
        },
        "verified_numbers": work_numbers,
        "tasks_summary": tasks_numbers,
        "sections": {
            "work_completed": buckets.get("completed", []),
            "work_in_progress": buckets.get("in_progress", []),
            "blocked": buckets.get("blocked", []),
            "outstanding_tasks": [_serialize_task(t) for t in outstanding],
        },
        "sections_have_data": sections_have_data,
        "missing_sections": missing_sections,
        "honesty_reminder": (
            "Do not invent numbers. Use verified_numbers exactly as provided. "
            "For any section listed in missing_sections, write 'NOT PROVIDED' "
            "rather than guessing. Do not claim achievements the user did not "
            "report."
        ),
    }
    return draft


def _persist_draft(db: Session, user_id: int, draft: dict) -> Report:
    """Store the draft in the reports table."""
    start = datetime.fromisoformat(draft["period"]["from_date"])
    end = datetime.fromisoformat(draft["period"]["to_date"])
    report = Report(
        user_id=user_id,
        report_type=draft["report_type"],
        period_start=start,
        period_end=end,
        status="draft",
        data=draft,
        content=None,
        version=1,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


# ============================================================
# PUBLIC BUILDERS
# ============================================================
def build_daily_report(day: Optional[str] = None) -> dict:
    start, end = _default_day_range(day)
    db = SessionLocal()
    try:
        user = _get_default_user(db)
        draft = _build_draft(
            db, "daily", start, end,
            {"display_date": start.date().isoformat()},
        )
        report = _persist_draft(db, user.id, draft)
        draft["report_id"] = report.id
        draft["status"] = report.status
        return draft
    finally:
        db.close()


def build_weekly_report(week_start: Optional[str] = None) -> dict:
    start, end = _default_week_range(week_start)
    db = SessionLocal()
    try:
        user = _get_default_user(db)
        draft = _build_draft(
            db, "weekly", start, end,
            {
                "week_start": start.date().isoformat(),
                "week_end": (end - timedelta(seconds=1)).date().isoformat(),
            },
        )
        report = _persist_draft(db, user.id, draft)
        draft["report_id"] = report.id
        draft["status"] = report.status
        return draft
    finally:
        db.close()


def build_monthly_report(
    year: Optional[int] = None, month: Optional[int] = None
) -> dict:
    start, end = _default_month_range(year, month)
    db = SessionLocal()
    try:
        user = _get_default_user(db)
        draft = _build_draft(
            db, "monthly", start, end,
            {
                "year": start.year,
                "month": start.month,
                "month_name": start.strftime("%B"),
            },
        )
        report = _persist_draft(db, user.id, draft)
        draft["report_id"] = report.id
        draft["status"] = report.status
        return draft
    finally:
        db.close()


# ============================================================
# LOOKUP
# ============================================================
def get_report(report_id: int) -> Optional[dict]:
    """Fetch a stored report as a plain dict. Returns None if not found."""
    db = SessionLocal()
    try:
        r = db.query(Report).filter_by(id=report_id).first()
        if r is None:
            return None
        return {
            "id": r.id,
            "report_type": r.report_type,
            "period_start": r.period_start.isoformat(),
            "period_end": r.period_end.isoformat(),
            "status": r.status,
            "version": r.version,
            "data": r.data,
            "content": r.content,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
    finally:
        db.close()