"""Structured HTTP access logging with request IDs."""

from __future__ import annotations

import time
import uuid
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class LoggingMiddleware(BaseHTTPMiddleware):
    """Emits one structured log line per HTTP request and tags it with a request ID.

    The ID is bound into structlog's context, so every log line written while the
    request is handled carries it, and it is echoed back in the response header.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled_error", method=request.method, path=request.url.path)
            raise
        duration_ms = (time.perf_counter() - start) * 1000.0
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
        return response
