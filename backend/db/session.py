"""Async SQLAlchemy session factory."""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings

_sqlite = settings.DATABASE_URL.startswith("sqlite")

_engine_kw: dict = {
    "echo": False,
    "pool_pre_ping": not _sqlite,
}
if _sqlite:
    _engine_kw["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(settings.DATABASE_URL, **_engine_kw)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

__all__ = ["engine", "AsyncSessionLocal"]
