"""
Xyrox — Database Models (Phase 7.1)

Tables: users, projects, tasks, work_logs, reports, pending_outbound.
Every table inherits from Base. All timestamps are timezone-aware.
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.backend.database.db import Base


def utcnow():
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

    tasks = relationship("Task", back_populates="owner", cascade="all, delete-orphan")
    work_logs = relationship("WorkLog", back_populates="owner", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="owner", cascade="all, delete-orphan")

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
    status = Column(String(32), default="active", nullable=False)

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
    status = Column(String(32), default="pending", nullable=False)
    priority = Column(String(16), default="medium", nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(String(32), default="manual", nullable=False)
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
    work_date = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    activity = Column(Text, nullable=False)
    customer = Column(String(255), nullable=True)
    result = Column(Text, nullable=True)
    status = Column(String(32), default="completed", nullable=False)
    duration_minutes = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    source = Column(String(32), default="chat", nullable=False)
    ai_confidence = Column(String(16), default="high", nullable=False)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)

    owner = relationship("User", back_populates="work_logs")
    project = relationship("Project", back_populates="work_logs")

    def __repr__(self):
        return f"<WorkLog id={self.id} activity={self.activity[:40]!r}>"


# ============================================================
# REPORTS
# ============================================================
class Report(Base):
    """
    A generated report (daily, weekly, or monthly).

    status: draft | approved | finalized
    data:   JSON structure of verified numbers + raw entries
    content: the polished prose (filled by the AI or the user)
    """
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    report_type = Column(String(32), nullable=False, index=True)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    status = Column(String(32), default="draft", nullable=False, index=True)
    data = Column(JSON, nullable=True)
    content = Column(Text, nullable=True)
    version = Column(Integer, default=1, nullable=False)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    owner = relationship("User", back_populates="reports")

    def __repr__(self):
        return f"<Report id={self.id} type={self.report_type!r} status={self.status!r}>"


# ============================================================
# PENDING OUTBOUND (Phase 7.1)
# ============================================================
class PendingOutbound(Base):
    """
    Outbound messages awaiting user approval. Used by Telegram
    (and later Email / Telephony) to enforce human-in-the-loop.

    channel:   telegram | email | sms | call
    recipient: chat_id (str) / email / phone number
    content:   text body OR a JSON description (for calls)
    status:    pending | sent | error | cancelled
    """
    __tablename__ = "pending_outbound"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String(32), nullable=False, index=True)
    recipient = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(32), default="pending", nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)

    def __repr__(self):
        return (
            f"<PendingOutbound id={self.id} channel={self.channel!r} "
            f"status={self.status!r}>"
        )