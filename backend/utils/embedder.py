"""Gemini embedding wrapper for vector memory and RAG."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

import google.generativeai as genai
import structlog

from config import settings

T = TypeVar("T")

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 30
# Gemini accepts at most 100 texts per batch embedding request.
BATCH_SIZE = 100

logger = structlog.get_logger(__name__)


class GeminiEmbedder:
    """Async-friendly facade over the Gemini embeddings API.

    Calls ``google.generativeai.embed_content`` directly rather than going through
    ``langchain_google_genai.GoogleGenerativeAIEmbeddings``: the pinned LangChain
    wrapper uses its own gRPC client, whose requests to ``gemini-embedding-001``
    time out (504 after 60s) while the SDK call answers in about a second.
    """

    def __init__(self) -> None:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._model = settings.EMBEDDING_MODEL

    def _embed(self, content: str | list[str], task_type: str) -> list:
        result = genai.embed_content(
            model=self._model,
            content=content,
            task_type=task_type,
            request_options={"timeout": REQUEST_TIMEOUT_SECONDS},
        )
        return result["embedding"]

    async def _with_retry(self, fn: Callable[..., T], *args: object) -> T:
        """Run a blocking embedding call off the event loop, retrying transient failures."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await asyncio.to_thread(fn, *args)
            except Exception as exc:
                if attempt == MAX_ATTEMPTS:
                    raise
                logger.warning("embedding_retry", attempt=attempt, error=str(exc)[:200])
                await asyncio.sleep(BACKOFF_SECONDS * 2 ** (attempt - 1))
        raise AssertionError("unreachable")

    async def embed_text(self, text: str) -> list[float]:
        """Embed a search query."""
        return await self._with_retry(self._embed, text, "retrieval_query")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed documents to be stored, in batches of up to 100 per API call."""
        if not texts:
            return []
        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            all_vectors.extend(await self._with_retry(self._embed, batch, "retrieval_document"))
        return all_vectors


embedder = GeminiEmbedder()
