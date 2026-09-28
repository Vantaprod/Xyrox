"""
Xyrox — Work Log Tools (Phase 4, File 1)

Real work logging. Every write is verified by re-read.
Every query reads the real database. No fabrication, no caching.

Tools registered:
    log_work(...)       → insert a work log row
    get_work_logs(...)  → query work logs with filters

Design rules:
- All timestamps are stored timezone-aware in UTC.
- Inputs are validated strictly (status enums, positive durations,
  ISO 8601 dates).
- If a named project does not exist, project_id stays NULL rather
  than inventing a project.
- Any error is raised, never silently swallowed.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.backend.database.db import SessionLocal
from app.backend.models.models import WorkLog, Project
from app.backend.tools.base import Tool, ToolValidationError
from app.backend.tools.registry import ToolRegistry
from app.backend.tools.tasks import _get_or_create_default_user


VALID_STATUSES = {
    "completed",
    "in_progress",
    "pending",
    "blocked",
    "cancelled",
    "unknown",
}

MAX_ACTIVITY_LEN = 2000
MAX_NOTES_LEN = 4000
MAX_RESULT_LEN = 2000
MAX_CUSTOMER_LEN = 255


# ============================================================
# HELPERS
# ============================================================
def _parse_iso_datetime(value, field_name: str) -> Optional[datetime]:
    """
    Accept None, a tz-aware datetime, or an ISO 8601 string.
    Return a tz-aware datetime in UTC, or None.

    Raises ToolValidationError on garbage input.
    """
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ToolValidationError(
                f"{field_name} is not a valid ISO 8601 datetime: {value!r}"
            ) from exc
    else:
        raise ToolValidationError(
            f"{field_name} must be a string or datetime, got "
            f"{type(value).__name__}."
        )

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_project_id(db: Session, project_name: Optional[str]) -> Optional[int]:
    """
    Look up a project by exact case-insensitive name for the default user.
    Returns None if project_name is falsy or no match exists.
    Does NOT create projects as a side effect.
    """
    if not project_name:
        return None
    name = project_name.strip().lower()
    if not name:
        return None
    user = _get_or_create_default_user(db)
    project = (
        db.query(Project)
        .filter(Project.user_id == user.id)
        .filter(Project.name.ilike(project_name.strip()))
        .first()
    )
    return project.id if project else None


def _validate_str_length(value: Optional[str], name: str, max_len: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolValidationError(f"{name} must be a string or None.")
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) > max_len:
        raise ToolValidationError(
            f"{name} must be at most {max_len} characters."
        )
    return stripped


# ============================================================
# TOOL: log_work
# ============================================================
def log_work(
    activity: str,
    work_date: Optional[str] = None,
    customer: Optional[str] = None,
    project: Optional[str] = None,
    result: Optional[str] = None,
    status: str = "completed",
    duration_minutes: Optional[int] = None,
    notes: Optional[str] = None,
    source: str = "chat",
    ai_confidence: str = "high",
) -> dict:
    """
    Record a work log entry. Returns the created record (with id).

    Raises ToolValidationError on any invalid input.
    """
    # ---- validate activity ----
    if not isinstance(activity, str) or not activity.strip():
        raise ToolValidationError("activity must be a non-empty string.")
    activity_clean = activity.strip()
    if len(activity_clean) > MAX_ACTIVITY_LEN:
        raise ToolValidationError(
            f"activity must be at most {MAX_ACTIVITY_LEN} characters."
        )

    # ---- validate status ----
    status_clean = (status or "completed").strip().lower()
    if status_clean not in VALID_STATUSES:
        raise ToolValidationError(
            f"status must be one of {sorted(VALID_STATUSES)}, "
            f"got {status!r}."
        )

    # ---- validate duration ----
    if duration_minutes is not None:
        if not isinstance(duration_minutes, int):
            raise ToolValidationError("duration_minutes must be an integer.")
        if duration_minutes < 0:
            raise ToolValidationError("duration_minutes must be >= 0.")
        if duration_minutes > 24 * 60:
            raise ToolValidationError(
                "duration_minutes cannot exceed 1440 (24 hours)."
            )

    # ---- validate strings ----
    customer_clean = _validate_str_length(customer, "customer", MAX_CUSTOMER_LEN)
    result_clean = _validate_str_length(result, "result", MAX_RESULT_LEN)
    notes_clean = _validate_str_length(notes, "notes", MAX_NOTES_LEN)

    # ---- validate source / confidence ----
    source_clean = (source or "chat").strip().lower()
    if source_clean not in {"chat", "voice", "whatsapp", "email", "manual"}:
        raise ToolValidationError(
            f"source must be one of chat/voice/whatsapp/email/manual, "
            f"got {source!r}."
        )
    confidence_clean = (ai_confidence or "high").strip().lower()
    if confidence_clean not in {"high", "medium", "low"}:
        raise ToolValidationError(
            "ai_confidence must be high/medium/low."
        )

    # ---- parse date ----
    when = _parse_iso_datetime(work_date, "work_date")
    if when is None:
        when = datetime.now(timezone.utc)

    # ---- database write ----
    db: Session = SessionLocal()
    try:
        user = _get_or_create_default_user(db)
        project_id = _resolve_project_id(db, project)

        entry = WorkLog(
            work_date=when,
            activity=activity_clean,
            customer=customer_clean,
            result=result_clean,
            status=status_clean,
            duration_minutes=duration_minutes,
            notes=notes_clean,
            source=source_clean,
            ai_confidence=confidence_clean,
            user_id=user.id,
            project_id=project_id,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        # Verify the row exists
        verified = db.query(WorkLog).filter_by(id=entry.id).first()
        if verified is None:
            raise RuntimeError(
                f"WorkLog id={entry.id} committed but not found on re-read."
            )

        return {
            "id": verified.id,
            "work_date": verified.work_date.isoformat()
                if verified.work_date else None,
            "activity": verified.activity,
            "customer": verified.customer,
            "project_id": verified.project_id,
            "result": verified.result,
            "status": verified.status,
            "duration_minutes": verified.duration_minutes,
            "notes": verified.notes,
            "source": verified.source,
        }
    finally:
        db.close()


# ============================================================
# TOOL: get_work_logs
# ============================================================
def get_work_logs(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    customer: Optional[str] = None,
    project: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """
    Query work logs with optional filters.

    from_date / to_date are ISO 8601 datetimes (inclusive lower,
    exclusive upper). customer is a substring match. status is exact.
    project is exact (case-insensitive) project name.
    """
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        raise ToolValidationError("limit must be between 1 and 1000.")

    when_from = _parse_iso_datetime(from_date, "from_date")
    when_to = _parse_iso_datetime(to_date, "to_date")

    if when_from and when_to and when_to < when_from:
        raise ToolValidationError("to_date cannot be before from_date.")

    if status is not None:
        status_clean = status.strip().lower()
        if status_clean not in VALID_STATUSES:
            raise ToolValidationError(
                f"status must be one of {sorted(VALID_STATUSES)}."
            )
    else:
        status_clean = None

    db: Session = SessionLocal()
    try:
        user = _get_or_create_default_user(db)
        q = db.query(WorkLog).filter(WorkLog.user_id == user.id)

        if when_from is not None:
            q = q.filter(WorkLog.work_date >= when_from)
        if when_to is not None:
            q = q.filter(WorkLog.work_date < when_to)
        if customer:
            q = q.filter(WorkLog.customer.ilike(f"%{customer.strip()}%"))
        if status_clean:
            q = q.filter(WorkLog.status == status_clean)
        if project:
            project_id = _resolve_project_id(db, project)
            if project_id is None:
                # Named project does not exist → empty result, not an error
                return {"count": 0, "logs": []}
            q = q.filter(WorkLog.project_id == project_id)

        q = q.order_by(WorkLog.work_date.desc()).limit(limit)
        rows = q.all()

        return {
            "count": len(rows),
            "logs": [
                {
                    "id": r.id,
                    "work_date": r.work_date.isoformat()
                        if r.work_date else None,
                    "activity": r.activity,
                    "customer": r.customer,
                    "project_id": r.project_id,
                    "result": r.result,
                    "status": r.status,
                    "duration_minutes": r.duration_minutes,
                    "notes": r.notes,
                    "source": r.source,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


# ============================================================
# REGISTRATION
# ============================================================
def register_work_log_tools(registry: ToolRegistry) -> None:
    """Register work-log tools in the given registry."""

    registry.register(Tool(
        name="log_work",
        description=(
            "Record a work log entry. Use when the user says what they "
            "did — 'I edited three videos today', 'Finished Promise's "
            "installation', 'Spent 2 hours on the weekly report'. "
            "Extract the activity verbatim; set customer if mentioned; "
            "set work_date if the user specifies a day other than now; "
            "set duration_minutes only if the user gives a duration; "
            "set status based on what the user says (completed, "
            "in_progress, pending, blocked). Do not invent values."
        ),
        parameters={
            "type": "object",
            "properties": {
                "activity": {
                    "type": "string",
                    "description": "What was done. Clear, concise.",
                },
                "work_date": {
                    "type": "string",
                    "description": (
                        "ISO 8601 datetime when the work happened. "
                        "Omit if today."
                    ),
                },
                "customer": {
                    "type": "string",
                    "description": "Customer or client name if mentioned.",
                },
                "project": {
                    "type": "string",
                    "description": (
                        "Project name if mentioned. Must match an "
                        "existing project; otherwise omitted."
                    ),
                },
                "result": {
                    "type": "string",
                    "description": "Outcome if specified.",
                },
                "status": {
                    "type": "string",
                    "enum": sorted(VALID_STATUSES),
                    "description": "Default: completed.",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Duration in minutes if stated.",
                },
                "notes": {
                    "type": "string",
                    "description": "Additional context.",
                },
            },
            "required": ["activity"],
        },
        func=log_work,
    ))

    registry.register(Tool(
        name="get_work_logs",
        description=(
            "Query the user's work logs. Use for 'what did I do today?', "
            "'show me my week', 'how much time on Lura?', 'what's pending?'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "from_date": {
                    "type": "string",
                    "description": "ISO 8601 lower bound (inclusive).",
                },
                "to_date": {
                    "type": "string",
                    "description": "ISO 8601 upper bound (exclusive).",
                },
                "customer": {
                    "type": "string",
                    "description": "Substring match on customer name.",
                },
                "project": {
                    "type": "string",
                    "description": "Exact project name.",
                },
                "status": {
                    "type": "string",
                    "enum": sorted(VALID_STATUSES),
                    "description": "Filter by status.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return. Default 100.",
                },
            },
            "required": [],
        },
        func=get_work_logs,
    ))