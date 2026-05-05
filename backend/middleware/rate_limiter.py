"""Sliding-window Redis rate limiting."""

from __future__ import annotations

import time
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

        window = int(time.time() / settings.RATE_LIMIT_WINDOW_SECONDS)
        key = f"ratelimit:{identifier}:{window}"
        client = await get_shared_redis()
        try:
            count = await client.incr(key)
            if int(count) == 1:
                await client.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)
        except redis.RedisError:
            return await call_next(request)

        if int(count) > settings.RATE_LIMIT_REQUESTS:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )
        return await call_next(request)
