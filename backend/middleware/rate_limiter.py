"""Sliding-window Redis rate limiting (per user, or per client IP when anonymous)."""

from __future__ import annotations

import time
import uuid
from typing import Callable

import redis.asyncio as redis
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from redis_client import get_shared_redis
from services.auth_service import decode_token


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Per-user or per-IP request throttling."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        path = request.url.path
        if path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        identifier: str | None = None
        auth = request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            try:
                payload = decode_token(token)
                if payload.get("type") == "access":
                    identifier = str(payload.get("sub"))
            except Exception:
                identifier = None
        if identifier is None:
            identifier = request.client.host if request.client else "anonymous"

        # Sliding-window log: one sorted-set member per request, scored by timestamp.
        now = time.time()
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        key = f"ratelimit:{identifier}"
        member = f"{now}:{uuid.uuid4().hex}"
        client = await get_shared_redis()
        try:
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zadd(key, {member: now})
            pipe.zcard(key)
            pipe.expire(key, window)
            _, _, count, _ = await pipe.execute()
        except redis.RedisError:
            # Fail open: an unavailable limiter must not take the API down with it.
            return await call_next(request)

        if int(count) > settings.RATE_LIMIT_REQUESTS:
            # Rejected requests do not consume quota.
            await client.zrem(key, member)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": str(window)},
            )
        return await call_next(request)
