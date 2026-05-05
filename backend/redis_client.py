"""Shared async Redis: real server or in-memory (local dev)."""

from __future__ import annotations

import redis.asyncio as redis

from config import settings

_client: redis.Redis | None = None


async def get_shared_redis() -> redis.Redis:
    """Return a singleton Redis-compatible client."""
    global _client
    if _client is None:
        if settings.USE_FAKE_REDIS:
            from fakeredis import FakeAsyncRedis

            _client = FakeAsyncRedis(decode_responses=False)
        else:
            _client = redis.from_url(settings.REDIS_URL, decode_responses=False)
    return _client


async def close_shared_redis() -> None:
    """Dispose the shared client (call from app shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
