"""
Xyrox — Personal AI Operations Agent
Backend Entry Point (Phase 1)

This file:
1. Creates the SQLite database and all tables on startup.
2. Boots the FastAPI application.
3. Registers the /  and /health endpoints.
4. Exposes the interactive API docs at /docs.

Run with:
    uvicorn app.backend.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.backend.config import settings
from app.backend.database.db import engine, Base

# IMPORTANT: Importing the models module is what tells SQLAlchemy
# which tables exist. Without this import, create_all() would
# create nothing. Do not remove.
from app.backend.models import models  # noqa: F401


# ------------------------------------------------------------
# Create all database tables (idempotent — safe to run every startup)
# ------------------------------------------------------------
Base.metadata.create_all(bind=engine)


# ------------------------------------------------------------
# FastAPI application
# ------------------------------------------------------------
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Xyrox — Personal AI Operations Agent. Real system, not a demo.",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ------------------------------------------------------------
# CORS — allow the future frontend to talk to this backend.
# We will tighten this in a later phase.
# ------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------
# Root endpoint — quick status check
# ------------------------------------------------------------
@app.get("/", tags=["system"])
def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "ai_provider": settings.AI_PROVIDER,
        "ai_model": settings.AI_MODEL,
        "timezone": settings.TZ,
        "database": "SQLite (data/app.db)",
    }


# ------------------------------------------------------------
# Health check — used by tests and future monitoring
# ------------------------------------------------------------
@app.get("/health", tags=["system"])
def health_check():
    return {"status": "healthy"}