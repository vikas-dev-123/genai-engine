# isort: skip_file
"""Shared fixtures: isolated SQLite DB, fake Redis, fake embeddings, fake agent.

Nothing here touches the network or needs a real Gemini key.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable
from typing import Any

# Configure the app before any application module is imported.
_TMP = tempfile.mkdtemp(prefix="genai-engine-tests-")
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "GEMINI_API_KEY": "test-key",
        "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-0123456789",
        "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP}/test.db",
        "USE_FAKE_REDIS": "true",
        "FAISS_INDEX_DIR": os.path.join(_TMP, "faiss"),
        "WORKSPACE_DIR": os.path.join(_TMP, "workspace"),
        "RATE_LIMIT_REQUESTS": "10000",
    },
)

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from config import settings  # noqa: E402
from db.base import Base  # noqa: E402
from db.session import engine  # noqa: E402
from main import app  # noqa: E402
import redis_client  # noqa: E402
from redis_client import get_shared_redis  # noqa: E402
from services.llm_service import llm_service  # noqa: E402
from utils.embedder import embedder  # noqa: E402

EMBED_DIM = 64


def fake_embedding(text: str) -> list[float]:
    """Deterministic bag-of-words vector: texts sharing words are similar."""
    vec = np.zeros(EMBED_DIM, dtype="float32")
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBED_DIM
        vec[bucket] += 1.0
    return vec.tolist()


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    async def embed_text(text: str) -> list[float]:
        return fake_embedding(text)

    async def embed_batch(texts: list[str]) -> list[list[float]]:
        return [fake_embedding(t) for t in texts]

    monkeypatch.setattr(embedder, "embed_text", embed_text)
    monkeypatch.setattr(embedder, "embed_batch", embed_batch)


@pytest.fixture(autouse=True)
async def _clean_state() -> AsyncIterator[None]:
    """Fresh schema, empty Redis and empty data dirs for every test.

    Each test runs on its own event loop, so loop-bound singletons (the Redis
    client and pooled DB connections) are recreated per test as well.
    """
    redis_client._client = None
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    redis = await get_shared_redis()
    await redis.flushall()
    for path in (settings.FAISS_INDEX_DIR, settings.WORKSPACE_DIR):
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)
    yield
    await redis_client.close_shared_redis()
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def register(client: AsyncClient, email: str = "ada@example.com") -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "name": "Ada"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture
async def auth(client: AsyncClient) -> dict[str, str]:
    """Authorization header for a freshly registered user."""
    tokens = await register(client)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


class FakeAgent:
    """Stands in for LangChain's AgentExecutor; replays scripted stream events."""

    def __init__(self, events: list[dict[str, Any]], fail_after: int | None = None) -> None:
        self.events = events
        self.fail_after = fail_after
        self.inputs: dict[str, Any] | None = None

    async def astream_events(self, inputs: dict[str, Any], version: str) -> AsyncIterator[dict]:
        self.inputs = inputs
        for i, event in enumerate(self.events):
            if self.fail_after is not None and i == self.fail_after:
                raise RuntimeError("model exploded")
            yield event


def token(text: str) -> dict[str, Any]:
    class Chunk:
        content = text

    return {"event": "on_chat_model_stream", "data": {"chunk": Chunk()}}


@pytest.fixture
def fake_agent(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeAgent]:
    """Install a FakeAgent for the next chat turn(s) and return it."""

    def install(events: list[dict[str, Any]], fail_after: int | None = None) -> FakeAgent:
        agent = FakeAgent(events, fail_after)
        monkeypatch.setattr(llm_service, "_build_agent", lambda user_id: agent)
        return agent

    return install


def parse_sse(body: str) -> list[dict[str, Any]]:
    import json

    return [
        json.loads(line[len("data:") :].strip())
        for line in body.split("\n\n")
        if line.strip().startswith("data:")
    ]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    shutil.rmtree(_TMP, ignore_errors=True)
