"""
Xyrox — Database Models (Phase 1)

These are the core tables for the Xyrox AI Operations Agent.
Every table inherits from Base (defined in app/backend/database/db.py).

Design principles:
- Timestamps on every table (created_at, updated_at).
- Foreign keys for relationships.
- Explicit status/priority fields (never rely on AI to guess).
- No fabrication: unknowns stay NULL, not "completed".
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    ForeignKey, Float
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.backend.database.db import Base


def utcnow():
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# ============================================================
# USERS
# ============================================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(128), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    timezone = Column(String(64), default="Africa/Lagos", nullable=False)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    tasks = relationship("Task", back_populates="owner", cascade="all, delete-orphan")
    work_logs = relationship("WorkLog", back_populates="owner", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User id={self.id} username={self.username!r}>"


# ============================================================
# PROJECTS
# ============================================================
class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    customer = Column(String(255), nullable=True)
    status = Column(String(32), default="active", nullable=False)  # active, paused, completed, cancelled

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="projects")

    tasks = relationship("Task", back_populates="project")
    work_logs = relationship("WorkLog", back_populates="project")

    def __repr__(self):
        return f"<Project id={self.id} name={self.name!r}>"


# ============================================================
# TASKS
# ============================================================
class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Status must be one of:
    # pending | in_progress | completed | blocked | cancelled | unknown
    status = Column(String(32), default="pending", nullable=False)

    # Priority must be one of:
    # low | medium | high | urgent
    priority = Column(String(16), default="medium", nullable=False)

    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Provenance — where did this task come from?
    # chat | voice | whatsapp | email | manual | document
    source = Column(String(32), default="manual", nullable=False)

    # AI confidence in the interpretation that created this task
    # high | medium | low
    ai_confidence = Column(String(16), default="high", nullable=False)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)

    owner = relationship("User", back_populates="tasks")
    project = relationship("Project", back_populates="tasks")

    def __repr__(self):
        return f"<Task id={self.id} title={self.title!r} status={self.status!r}>"


# ============================================================
# WORK LOGS
# ============================================================
class WorkLog(Base):
    __tablename__ = "work_logs"

    id = Column(Integer, primary_key=True, index=True)

    # When the work actually happened (not when it was logged)
    work_date = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    activity = Column(Text, nullable=False)          # e.g. "Edited 3 installation videos"
    customer = Column(String(255), nullable=True)     # e.g. "Promise"
    result = Column(Text, nullable=True)              # e.g. "Delivered final cut"

    # Status: completed | in_progress | pending | blocked | cancelled | unknown
    status = Column(String(32), default="completed", nullable=False)

    duration_minutes = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    # Provenance
    source = Column(String(32), default="chat", nullable=False)  # chat | voice | manual
    ai_confidence = Column(String(16), default="high", nullable=False)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)

    owner = relationship("User", back_populates="work_logs")
    project = relationship("Project", back_populates="work_logs")

    def __repr__(self):
        return f"<WorkLog id={self.id} activity={self.activity[:40]!r}>"