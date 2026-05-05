"""HTTP client tool with a domain allowlist."""

from __future__ import annotations

import json
from urllib.parse import urlparse

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from config import settings


class APICallInput(BaseModel):
    url: str = Field(description="Full HTTPS URL to call")
    method: str = Field(default="GET", description="HTTP method")
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict | None = Field(default=None, description="Optional JSON body for POST/PUT/PATCH")


class APICallerTool(BaseTool):
    """Perform whitelisted HTTP requests."""

    name: str = "api_call"
    description: str = (
        "Make HTTP requests to external APIs. "
        'Provide url, method, optional headers, optional JSON body in the "body" field. '
        "Only whitelisted domains are allowed."
    )
    args_schema: type[BaseModel] = APICallInput

    def _domain_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        allowed = [d.lower() for d in settings.ALLOWED_API_DOMAINS]
        return host in allowed

    def _run(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> str:
        hdrs = headers or {}
        if not self._domain_allowed(url):
            return f"Domain not whitelisted. Allowed: {settings.ALLOWED_API_DOMAINS}"
        try:
            m = method.upper()
            with httpx.Client(timeout=30.0) as client:
                if m in ("POST", "PUT", "PATCH") and body is not None:
                    resp = client.request(m, url, headers=hdrs, json=body)
                else:
                    resp = client.request(m, url, headers=hdrs)
            text = resp.text
            if len(text) > 2000:
                text = text[:2000] + "…"
            return f"Status: {resp.status_code}\nResponse: {text}"
        except httpx.HTTPError as exc:
            return f"Request failed: {exc!s}"

    async def _arun(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> str:
        hdrs = headers or {}
        if not self._domain_allowed(url):
            return f"Domain not whitelisted. Allowed: {settings.ALLOWED_API_DOMAINS}"
        try:
            m = method.upper()
            async with httpx.AsyncClient(timeout=30.0) as client:
                if m in ("POST", "PUT", "PATCH") and body is not None:
                    resp = await client.request(m, url, headers=hdrs, json=body)
                else:
                    resp = await client.request(m, url, headers=hdrs)
            text = resp.text
            if len(text) > 2000:
                text = text[:2000] + "…"
            return f"Status: {resp.status_code}\nResponse: {text}"
        except httpx.HTTPError as exc:
            return f"Request failed: {exc!s}"
