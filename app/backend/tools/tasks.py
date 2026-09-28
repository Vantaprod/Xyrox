"""
Xyrox — Task Tools (Phase 4, revised)

Same tools as Phase 2, plus explicit **extra rejection so that when
a model mixes up fields between tools (e.g. passes "customer" to
create_task), the error message is clear and structured.

Design rules:
- No silent acceptance of unknown kwargs (Master Command §18).
- Every failure path returns a specific, actionable error.
- All DB writes are verified by re-read.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.backend.database.db import SessionLocal
from app.backend.models.models import Task, User
from app.backend.tools.base import Tool, ToolValidationError
from app.backend.tools.registry import ToolRegistry


VALID_STATUSES = {"pending", "in_progress", "completed", "blocked", "cancelled", "unknown"}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}


def _reject_extra(tool_name: str, extra: dict) -> None:
    """Raise a clear error listing unexpected arguments."""
    if extra:
        keys = ", ".join(sorted(extra.keys()))
        raise ToolValidationError(
            f"Tool '{tool_name}' received unexpected argument(s): {keys}. "
            f"These fields do not belong to this tool."
        )


def _get_or_create_default_user(db: Session) -> User:
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


def _parse_due_date(value) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
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
    **extra,
) -> dict:
    _reject_extra("create_task", extra)

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
    **extra,
) -> dict:
    _reject_extra("list_tasks", extra)

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
def complete_task(task_id: int, **extra) -> dict:
    _reject_extra("complete_task", extra)

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
    registry.register(Tool(
        name="create_task",
        description=(
            "Create a new task. Use ONLY when the user wants to record "
            "a to-do, follow-up, or deadline. This tool accepts ONLY: "
            "title (required), description, due_date, priority, status. "
            "Do NOT pass customer, project, notes, or duration — those "
            "belong to log_work, not create_task."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short, clear title."},
                "description": {"type": "string", "description": "Optional longer description."},
                "due_date": {"type": "string", "description": "ISO 8601 datetime."},
                "priority": {"type": "string", "enum": sorted(VALID_PRIORITIES)},
                "status": {"type": "string", "enum": sorted(VALID_STATUSES)},
            },
            "required": ["title"],
        },
        func=create_task,
    ))

    registry.register(Tool(
        name="list_tasks",
        description=(
            "List the user's tasks. Use when the user asks what they "
            "have to do, what is outstanding, or what is completed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": sorted(VALID_STATUSES)},
                "limit": {"type": "integer"},
            },
            "required": [],
        },
        func=list_tasks,
    ))

    registry.register(Tool(
        name="complete_task",
        description=(
            "Mark an existing task as completed. Requires the task id. "
            "Use ONLY when the user says a task is finished."
        ),
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
            },
            "required": ["task_id"],
        },
        func=complete_task,
    ))