"""Gemini embedding wrapper for vector memory and RAG."""

from __future__ import annotations

import asyncio

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config import settings


class GeminiEmbedder:
    """Async-friendly facade over LangChain Gemini embeddings."""

    def __init__(self) -> None:
        self._lc = GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single string."""
        return await asyncio.to_thread(self._lc.embed_query, text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed many strings in batches (max 100 per API call)."""
        if not texts:
            return []
        batch_size = 100
        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            vectors = await asyncio.to_thread(self._lc.embed_documents, batch)
            all_vectors.extend(vectors)
        return all_vectors

    def get_langchain_embeddings(self) -> GoogleGenerativeAIEmbeddings:
        """Expose the underlying LangChain embeddings client."""
        return self._lc


embedder = GeminiEmbedder()
