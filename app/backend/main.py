"""
Xyrox — Personal AI Operations Agent
Backend Entry Point (Phase 3, sub-phase 3)

Registers the auth and chat routers under /api/v1.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.backend.config import settings
from app.backend.database.db import engine, Base

# Ensure models are imported so tables are created
from app.backend.models import models  # noqa: F401

# Routers
from app.backend.api import auth as auth_router
from app.backend.api import chat as chat_router


Base.metadata.create_all(bind=engine)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Xyrox — Personal AI Operations Agent. Real system, not a demo.",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in a later phase
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "healthy"}


# API v1
app.include_router(auth_router.router, prefix=settings.API_V1_STR)
app.include_router(chat_router.router, prefix=settings.API_V1_STR)