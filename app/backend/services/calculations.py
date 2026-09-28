"""
Xyrox — Deterministic Calculation Layer (Phase 4.2)

Every number that appears in a report comes from this module. The AI
is NEVER allowed to compute totals, counts, percentages, or sums.
The AI receives verified numbers from here and only phrases them.

This is Master Command §48 enforced:
    DATABASE
        ↓
    DETERMINISTIC CALCULATION (this file)
        ↓
    VERIFIED RESULT
        ↓
    AI explains it in prose.

Design rules:
- All functions read from the database.
- All functions return plain dicts (JSON-serializable).
- All inputs are validated. Bad input raises CalculationError.
- No function silently returns 0 for a missing table — it returns
  0 only when the query genuinely matches nothing.
- Timezones: all comparisons are in UTC.
- The default user is the single-user "joseph" account (same
  convention as tasks.py and work_logs.py).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.backend.database.db import SessionLocal
from app.backend.models.models import Task, WorkLog, Project, User


class CalculationError(Exception):
    """Raised when a calculation receives invalid input."""
    pass


# ============================================================
# INTERNAL HELPERS
# ============================================================
def _get_default_user(db: Session) -> User:
    """Same default-user convention as tools/tasks.py."""
    user = db.query(User).filter_by(username="joseph").first()
    if user is None:
        user = User(
            username="joseph",
            email="joseph@xyrox.local",
            full_name="Joseph",
            hashed_password="__no_login_yet__",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _parse_dt(value, field: str, default: Optional[datetime] = None) -> Optional[datetime]:
    """Accept None, datetime, or ISO 8601 string. Return tz-aware UTC or None."""
    if value is None or value == "":
        return default
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CalculationError(
                f"{field} is not valid ISO 8601: {value!r}"
            ) from exc
    else:
        raise CalculationError(
            f"{field} must be ISO 8601 string or datetime."
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _default_day_range(day: Optional[str]) -> tuple[datetime, datetime]:
    """If `day` is None, return [today 00:00 UTC, tomorrow 00:00 UTC)."""
    if day is None:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = _parse_dt(day, "day")
        if start is None:
            raise CalculationError("day could not be parsed.")
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _default_week_range(week_start: Optional[str]) -> tuple[datetime, datetime]:
    """
    Return a Monday-to-Monday range.
    If week_start is None, uses the Monday of the current week (UTC).
    """
    if week_start is None:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        start = _parse_dt(week_start, "week_start")
        if start is None:
            raise CalculationError("week_start could not be parsed.")
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=7)


def _default_month_range(year: Optional[int], month: Optional[int]) -> tuple[datetime, datetime]:
    """Return [first of month, first of next month) in UTC."""
    now = datetime.now(timezone.utc)
    y = year if year is not None else now.year
    m = month if month is not None else now.month
    if not (1 <= m <= 12):
        raise CalculationError("month must be between 1 and 12.")
    if not (1970 <= y <= 2100):
        raise CalculationError("year must be between 1970 and 2100.")
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    if m == 12:
        end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(y, m + 1, 1, tzinfo=timezone.utc)
    return start, end


# ============================================================
# PUBLIC — WORK LOG CALCULATIONS
# ============================================================
def work_log_totals(from_date: str, to_date: str) -> dict:
    """
    Return verified totals from the work_logs table for a time range.

    from_date (inclusive), to_date (exclusive) — both ISO 8601.
    """
    start = _parse_dt(from_date, "from_date")
    end = _parse_dt(to_date, "to_date")
    if start is None or end is None:
        raise CalculationError("from_date and to_date are required.")
    if end < start:
        raise CalculationError("to_date cannot be before from_date.")

    db = SessionLocal()
    try:
        user = _get_default_user(db)
        base = db.query(WorkLog).filter(
            WorkLog.user_id == user.id,
            WorkLog.work_date >= start,
            WorkLog.work_date < end,
        )

        total = base.count()

        # Status breakdown
        status_rows = (
            db.query(WorkLog.status, func.count(WorkLog.id))
            .filter(
                WorkLog.user_id == user.id,
                WorkLog.work_date >= start,
                WorkLog.work_date < end,
            )
            .group_by(WorkLog.status)
            .all()
        )
        status_breakdown = {s or "unknown": c for s, c in status_rows}

        # Duration sum (only entries that have a duration)
        duration_row = (
            db.query(func.coalesce(func.sum(WorkLog.duration_minutes), 0))
            .filter(
                WorkLog.user_id == user.id,
                WorkLog.work_date >= start,
                WorkLog.work_date < end,
            )
            .scalar()
        )
        total_minutes = int(duration_row or 0)

        # Distinct customers (case-insensitive, non-null)
        customers = (
            db.query(func.lower(WorkLog.customer))
            .filter(
                WorkLog.user_id == user.id,
                WorkLog.work_date >= start,
                WorkLog.work_date < end,
                WorkLog.customer.isnot(None),
            )
            .distinct()
            .all()
        )
        distinct_customers = sorted({c[0] for c in customers if c[0]})

        return {
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            "total_logs": total,
            "total_minutes": total_minutes,
            "total_hours": round(total_minutes / 60.0, 2),
            "status_breakdown": status_breakdown,
            "distinct_customers": distinct_customers,
            "distinct_customer_count": len(distinct_customers),
        }
    finally:
        db.close()


def work_log_daily_summary(day: Optional[str] = None) -> dict:
    """Verified totals for a single day (defaults to today, UTC)."""
    start, end = _default_day_range(day)
    totals = work_log_totals(start.isoformat(), end.isoformat())
    totals["day"] = start.date().isoformat()
    return totals


def work_log_weekly_summary(week_start: Optional[str] = None) -> dict:
    """Verified totals for a Monday-to-Monday week (defaults to this week)."""
    start, end = _default_week_range(week_start)
    totals = work_log_totals(start.isoformat(), end.isoformat())
    totals["week_start"] = start.date().isoformat()
    totals["week_end"] = (end - timedelta(seconds=1)).date().isoformat()
    return totals


def work_log_monthly_summary(
    year: Optional[int] = None, month: Optional[int] = None
) -> dict:
    """Verified totals for a calendar month (defaults to current month)."""
    start, end = _default_month_range(year, month)
    totals = work_log_totals(start.isoformat(), end.isoformat())
    totals["year"] = start.year
    totals["month"] = start.month
    totals["month_name"] = start.strftime("%B")
    return totals


# ============================================================
# PUBLIC — TASK CALCULATIONS
# ============================================================
def task_totals(status: Optional[str] = None) -> dict:
    """
    Return verified counts of tasks, optionally filtered by status.

    Example: task_totals() → {"total": 12, "by_status": {...}}
    """
    db = SessionLocal()
    try:
        user = _get_default_user(db)

        base = db.query(Task).filter(Task.user_id == user.id)
        if status:
            base = base.filter(Task.status == status)
        total = base.count()

        # Group by status
        status_rows = (
            db.query(Task.status, func.count(Task.id))
            .filter(Task.user_id == user.id)
            .group_by(Task.status)
            .all()
        )
        by_status = {s or "unknown": c for s, c in status_rows}

        # Group by priority
        priority_rows = (
            db.query(Task.priority, func.count(Task.id))
            .filter(Task.user_id == user.id)
            .group_by(Task.priority)
            .all()
        )
        by_priority = {p or "unknown": c for p, c in priority_rows}

        # Overdue: due_date < now AND status not in (completed, cancelled)
        now = datetime.now(timezone.utc)
        overdue = (
            db.query(Task)
            .filter(
                Task.user_id == user.id,
                Task.due_date.isnot(None),
                Task.due_date < now,
                Task.status.notin_(["completed", "cancelled"]),
            )
            .count()
        )

        return {
            "total": total,
            "by_status": by_status,
            "by_priority": by_priority,
            "overdue": overdue,
        }
    finally:
        db.close()


# ============================================================
# PUBLIC — COMBINED (for reports)
# ============================================================
def combined_report_data(
    from_date: str, to_date: str
) -> dict:
    """
    Everything a report needs for a given date range, already
    calculated and verified. The AI receives this dict and only
    writes prose around it.
    """
    return {
        "period": {
            "from_date": _parse_dt(from_date, "from_date").isoformat(),
            "to_date": _parse_dt(to_date, "to_date").isoformat(),
        },
        "work": work_log_totals(from_date, to_date),
        "tasks": task_totals(),
    }