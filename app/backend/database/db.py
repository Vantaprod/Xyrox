"""
Xyrox — Database Engine & Session (Phase 1, corrected)

This version automatically creates the parent folder of the SQLite
database file if it does not already exist. That prevents the
"unable to open database file" error from ever happening again,
even if the data/ folder is accidentally deleted.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.backend.config import settings


# ------------------------------------------------------------
# Ensure the data/ directory exists before SQLAlchemy tries
# to open the SQLite file.
# ------------------------------------------------------------
def _ensure_sqlite_dir(database_url: str) -> None:
    if not database_url.startswith("sqlite"):
        return

    # Expected form: sqlite:///./data/app.db  or  sqlite:///C:/path/file.db
    # Strip the scheme prefix.
    path_part = database_url.replace("sqlite:///", "", 1)

    # If it's a relative path, resolve it against the project root
    # (the folder you run uvicorn / pytest from).
    db_path = Path(path_part).expanduser()
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(settings.DATABASE_URL)


# ------------------------------------------------------------
# Engine & session factory
# ------------------------------------------------------------
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite + FastAPI
    echo=False,  # set True temporarily to see raw SQL
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency: yields a session, guarantees it is closed.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()