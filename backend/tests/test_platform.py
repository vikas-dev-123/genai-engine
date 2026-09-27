"""Health, rate limiting, request IDs, production config guards, and migrations."""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import create_engine

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from config import Settings, settings
from db.base import Base

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def test_health_reports_dependencies(client: AsyncClient) -> None:
    body = (await client.get("/health")).json()
    assert body["status"] == "healthy"
    assert body["db"] == "connected" and body["redis"] == "connected"


async def test_responses_carry_request_id(client: AsyncClient) -> None:
    resp = await client.get("/health", headers={"X-Request-ID": "abc123"})
    assert resp.headers["X-Request-ID"] == "abc123"
    assert (await client.get("/health")).headers["X-Request-ID"]


async def test_rate_limit_returns_429_with_retry_after(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS", 3)
    codes = [(await client.get("/api/v1/auth/me")).status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]
    limited = await client.get("/api/v1/auth/me")
    assert limited.headers["Retry-After"] == str(settings.RATE_LIMIT_WINDOW_SECONDS)


async def test_health_is_not_rate_limited(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS", 1)
    codes = [(await client.get("/health")).status_code for _ in range(3)]
    assert codes == [200, 200, 200]


def _prod(**overrides: object) -> Settings:
    values = {
        "ENVIRONMENT": "production",
        "GEMINI_API_KEY": "k",
        "JWT_SECRET_KEY": "a" * 64,
        "USE_FAKE_REDIS": False,
        "CORS_ORIGINS": "https://app.example.com",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_accepts_safe_config() -> None:
    assert _prod().is_production


@pytest.mark.parametrize(
    "overrides",
    [
        {"JWT_SECRET_KEY": "short"},
        {"JWT_SECRET_KEY": "your_256_bit_secret_here_padding_padding"},
        {"USE_FAKE_REDIS": True},
        {"CORS_ORIGINS": "*"},
    ],
)
def test_production_rejects_unsafe_config(overrides: dict) -> None:
    with pytest.raises(ValidationError, match="Unsafe production configuration"):
        _prod(**overrides)


def test_migrations_match_models_and_downgrade_cleanly(tmp_path) -> None:
    db_file = tmp_path / "migrated.db"
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_file}")

    command.upgrade(cfg, "head")
    sync_engine = create_engine(f"sqlite:///{db_file}")
    with sync_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Models changed without a migration: {diff}"

    command.downgrade(cfg, "base")
    with sync_engine.connect() as conn:
        tables = set(sync_engine.dialect.get_table_names(conn)) - {"alembic_version"}
    assert tables == set()
    sync_engine.dispose()


async def test_embedder_retries_transient_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    import utils.embedder as embedder_module
    from utils.embedder import GeminiEmbedder

    monkeypatch.setattr(embedder_module, "BACKOFF_SECONDS", 0)
    calls = {"n": 0}

    def flaky(content: str, task_type: str) -> list[float]:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("504 Deadline Exceeded")
        return [0.1, 0.2]

    emb = GeminiEmbedder()
    assert await emb._with_retry(flaky, "q", "retrieval_query") == [0.1, 0.2]
    assert calls["n"] == 3

    calls["n"] = -10  # keeps failing past MAX_ATTEMPTS
    with pytest.raises(RuntimeError):
        await emb._with_retry(flaky, "q", "retrieval_query")
