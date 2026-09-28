"""
Xyrox — Task Tools (Phase 2, File 6)

The first real tool the AI can invoke. It writes to the SQLite
database through SQLAlchemy. No fabrication, no fake success.

Design rules:
- Tool functions receive **arguments (from the AI or from tests)
  and return a plain dict that is JSON-serializable.
- All database work happens inside a session that is always closed.
- Any error is raised, not swallowed. The ToolRegistry wraps it.
- No tool claims success without a real DB write and verification.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.backend.database.db import SessionLocal
from app.backend.models.models import Task, User
from app.backend.tools.base import Tool, ToolValidationError
from app.backend.tools.registry import ToolRegistry


# ============================================================
# HELPERS
# ============================================================
VALID_STATUSES = {"pending", "in_progress", "completed", "blocked", "cancelled", "unknown"}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}


def _get_or_create_default_user(db: Session) -> User:
    """
    For Phase 2 we operate as a single user ("Joseph"). Later this
    becomes real authentication. Until then, this ensures a user row
    exists so tasks have a valid foreign key.
    """
    user = db.query(User).filter_by(username="joseph").first()
    if user is None:
        user = User(
            username="joseph",
            email="joseph@xyrox.local",
            full_name="Joseph",
            hashed_password="__no_login_yet__",  # not a real password
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _parse_due_date(value) -> Optional[datetime]:
    """
    Accept None, an ISO 8601 string, or a datetime. Return a
    timezone-aware datetime or None. Raise ToolValidationError
    on garbage input (never silently ignore).
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            # Python 3.11+ accepts the trailing 'Z'
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ToolValidationError(
                f"due_date is not a valid ISO 8601 datetime: {value!r}"
            ) from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    raise ToolValidationError(
        f"due_date must be a string or datetime, got {type(value).__name__}."
    )


# ============================================================
# TOOL: create_task
# ============================================================
def create_task(
    title: str,
    description: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: str = "medium",
    status: str = "pending",
    source: str = "chat",
    ai_confidence: str = "high",
) -> dict:
    """
    Create a task in the Xyrox database.

    Returns a dict with the new task's id and fields — proof of a real write.
    Raises ToolValidationError on bad input.
    """
    # ---- validation ----
    if not isinstance(title, str) or not title.strip():
        raise ToolValidationError("title must be a non-empty string.")

    priority = (priority or "medium").lower().strip()
    if priority not in VALID_PRIORITIES:
        raise ToolValidationError(
            f"priority must be one of {sorted(VALID_PRIORITIES)}, got {priority!r}."
        )

    status = (status or "pending").lower().strip()
    if status not in VALID_STATUSES:
        raise ToolValidationError(
            f"status must be one of {sorted(VALID_STATUSES)}, got {status!r}."
        )

    parsed_due = _parse_due_date(due_date)

    # ---- database write ----
    db: Session = SessionLocal()
    try:
        user = _get_or_create_default_user(db)

        task = Task(
            title=title.strip(),
            description=description,
            due_date=parsed_due,
            priority=priority,
            status=status,
            source=source,
            ai_confidence=ai_confidence,
            user_id=user.id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # Verify the row actually exists (no false positives)
        verified = db.query(Task).filter_by(id=task.id).first()
        if verified is None:
            raise RuntimeError(
                f"Task id={task.id} was committed but not found on re-read."
            )

        return {
            "id": verified.id,
            "title": verified.title,
            "description": verified.description,
            "status": verified.status,
            "priority": verified.priority,
            "due_date": verified.due_date.isoformat() if verified.due_date else None,
            "created_at": verified.created_at.isoformat(),
            "source": verified.source,
        }
    finally:
        db.close()


# ============================================================
# TOOL: list_tasks
# ============================================================
def list_tasks(
    status: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """
    Return the user's tasks, optionally filtered by status.
    Real DB read. No cached or hardcoded values.
    """
    if limit < 1 or limit > 500:
        raise ToolValidationError("limit must be between 1 and 500.")

    if status is not None:
        status = status.lower().strip()
        if status not in VALID_STATUSES:
            raise ToolValidationError(
                f"status must be one of {sorted(VALID_STATUSES)}."
            )

    db: Session = SessionLocal()
    try:
        user = _get_or_create_default_user(db)
        query = db.query(Task).filter_by(user_id=user.id)
        if status is not None:
            query = query.filter_by(status=status)
        tasks = query.order_by(Task.created_at.desc()).limit(limit).all()

        return {
            "count": len(tasks),
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                }
                for t in tasks
            ],
        }
    finally:
        db.close()


# ============================================================
# TOOL: complete_task
# ============================================================
def complete_task(task_id: int) -> dict:
    """
    Mark a task as completed. Real DB update. Verifies the change.
    """
    if not isinstance(task_id, int) or task_id < 1:
        raise ToolValidationError("task_id must be a positive integer.")

    db: Session = SessionLocal()
    try:
        task = db.query(Task).filter_by(id=task_id).first()
        if task is None:
            raise ToolValidationError(f"Task id={task_id} not found.")

        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(task)

        # Verify the update
        if task.status != "completed":
            raise RuntimeError(f"Task id={task_id} did not update correctly.")

        return {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }
    finally:
        db.close()


# ============================================================
# REGISTRATION
# ============================================================
def register_task_tools(registry: ToolRegistry) -> None:
    """
    Register all task-related tools in the given registry.
    Called by the global registry builder.
    """
    registry.register(Tool(
        name="create_task",
        description=(
            "Create a new task. Use when the user wants to record a to-do, "
            "a follow-up, a deadline, or anything they need to do later. "
            "Extract a clear title from the user's message. If the user "
            "mentions a date, convert it to an ISO 8601 due_date."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short, clear title of the task.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional longer description.",
                },
                "due_date": {
                    "type": "string",
                    "description": "Optional ISO 8601 datetime, e.g. 2026-09-30T17:00:00Z.",
                },
                "priority": {
                    "type": "string",
                    "enum": sorted(VALID_PRIORITIES),
                    "description": "Task priority. Default: medium.",
                },
                "status": {
                    "type": "string",
                    "enum": sorted(VALID_STATUSES),
                    "description": "Task status. Default: pending.",
                },
            },
            "required": ["title"],
        },
        func=create_task,
    ))

    registry.register(Tool(
        name="list_tasks",
        description=(
            "List the user's tasks. Use when the user asks what they have to do, "
            "what is outstanding, what is pending, or what is completed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": sorted(VALID_STATUSES),
                    "description": "Optional filter by status.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum tasks to return. Default 20.",
                },
            },
            "required": [],
        },
        func=list_tasks,
    ))

    registry.register(Tool(
        name="complete_task",
        description=(
            "Mark an existing task as completed. Use when the user says they "
            "finished, did, or completed something. Requires the task id."
        ),
        parameters={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The id of the task to mark as completed.",
                },
            },
            "required": ["task_id"],
        },
        func=complete_task,
    ))