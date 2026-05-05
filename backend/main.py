"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import redis.asyncio as redis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config import settings
from db.base import Base
from db.session import engine
from middleware.logging_middleware import LoggingMiddleware
from middleware.rate_limiter import RateLimiterMiddleware
from routers import auth_router, chat_router, rag_router, voice_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configure logging, schema, and local data paths."""
    _ = app
    timestamper = structlog.processors.TimeStamper(fmt="iso")
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
    ]
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    if settings.ENVIRONMENT.lower() == "production":
        structlog.configure(
            processors=shared + [structlog.processors.JSONRenderer()],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        structlog.configure(
            processors=shared + [structlog.dev.ConsoleRenderer()],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    os.makedirs(settings.FAISS_INDEX_DIR, exist_ok=True)
    os.makedirs(settings.WORKSPACE_DIR, exist_ok=True)

    logger = structlog.get_logger("jarvis")
    logger.info("Jarvis AI started.", model=settings.GEMINI_MODEL)

    yield

    logger.info("Jarvis AI shutting down")
    await engine.dispose()


app = FastAPI(
    title="Jarvis AI",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimiterMiddleware)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(voice_router)
app.include_router(rag_router)


@app.get("/health")
async def health() -> dict:
    """Liveness probe with dependency checks."""
    db_state = "connected"
    redis_state = "connected"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_state = "error"

    client: redis.Redis | None = None
    try:
        client = redis.from_url(settings.REDIS_URL)
        await client.ping()
    except Exception:
        redis_state = "error"
    finally:
        if client is not None:
            await client.aclose()

    return {
        "status": "healthy" if db_state == "connected" and redis_state == "connected" else "degraded",
        "version": "1.0.0",
        "model": settings.GEMINI_MODEL,
        "db": db_state,
        "redis": redis_state,
    }
