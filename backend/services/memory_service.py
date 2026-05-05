"""Conversation memory: Redis short-term buffer and FAISS long-term recall."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import datetime, timezone

import faiss
import numpy as np
import redis.asyncio as redis
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from config import settings
from utils.embedder import embedder

SHORT_TERM_TTL_SECONDS = 24 * 3600
SHORT_TERM_MAX_MESSAGES = 20
LONG_TERM_TOP_K = 5
LONG_TERM_SCORE_THRESHOLD = 0.75


def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize rows for inner-product ↔ cosine similarity."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return vectors / norms


class MemoryService:
    """Hybrid memory layer for chat context."""

    def __init__(self) -> None:
        self._redis_pool: redis.ConnectionPool | None = None

    def _get_pool(self) -> redis.ConnectionPool:
        if self._redis_pool is None:
            self._redis_pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
        return self._redis_pool

    async def _redis(self) -> redis.Redis:
        return redis.Redis(connection_pool=self._get_pool())

    def _memory_key(self, user_id: str, conversation_id: str) -> str:
        return f"memory:{user_id}:{conversation_id}"

    async def get_short_term(self, user_id: str, conversation_id: str) -> list[dict]:
        """Return recent messages as role/content dicts."""
        key = self._memory_key(user_id, conversation_id)
        client = await self._redis()
        raw = await client.get(key)
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []

    async def summarize_and_reset(
        self,
        user_id: str,
        conversation_id: str,
        messages: list[dict],
    ) -> None:
        """Compress the buffer into a single system summary message."""
        key = self._memory_key(user_id, conversation_id)
        transcript = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in messages
        )
        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.3,
        )
        prompt = (
            "Summarize this conversation in 3-5 bullet points, "
            "preserving key facts and decisions:\n"
            f"{transcript}"
        )
        try:
            result = await asyncio.to_thread(llm.invoke, [HumanMessage(content=prompt)])
            summary_text = getattr(result, "content", str(result))
        except Exception:
            summary_text = transcript[:2000]
        summary_message = [
            {
                "role": "system",
                "content": f"Conversation summary:\n{summary_text}",
            },
        ]
        client = await self._redis()
        await client.set(key, json.dumps(summary_message), ex=SHORT_TERM_TTL_SECONDS)

    async def add_to_short_term(
        self,
        user_id: str,
        conversation_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Append an exchange and roll up when the buffer grows too large."""
        key = self._memory_key(user_id, conversation_id)
        client = await self._redis()
        raw = await client.get(key)
        messages: list[dict]
        if raw:
            try:
                messages = json.loads(raw)
                if not isinstance(messages, list):
                    messages = []
            except json.JSONDecodeError:
                messages = []
        else:
            messages = []
        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "assistant", "content": assistant_msg})
        if len(messages) > SHORT_TERM_MAX_MESSAGES:
            await self.summarize_and_reset(user_id, conversation_id, messages)
        else:
            await client.set(key, json.dumps(messages), ex=SHORT_TERM_TTL_SECONDS)

    def _ensure_memory_dir(self, user_id: str) -> str:
        path = os.path.join(settings.FAISS_INDEX_DIR, user_id, "memory")
        os.makedirs(path, exist_ok=True)
        return path

    def _memory_paths(self, user_id: str) -> tuple[str, str, str]:
        base = self._ensure_memory_dir(user_id)
        return (
            os.path.join(base, "index.faiss"),
            os.path.join(base, "meta.json"),
            base,
        )

    async def add_long_term(
        self,
        user_id: str,
        user_msg: str,
        assistant_msg: str,
        conversation_id: str,
    ) -> None:
        """Persist a conversational exchange in FAISS-backed long-term memory."""
        text = f"User: {user_msg}\nJarvis: {assistant_msg}"
        vector = await embedder.embed_text(text)
        arr = np.array([vector], dtype="float32")
        arr = _normalize_vectors(arr)
        index_path, meta_path, _base = self._memory_paths(str(user_id))
        if os.path.exists(index_path):
            index = faiss.read_index(index_path)
        else:
            index = faiss.IndexFlatIP(arr.shape[1])
        index.add(arr)
        faiss.write_index(index, index_path)
        meta: list[dict]
        if os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                if not isinstance(meta, list):
                    meta = []
            except (OSError, json.JSONDecodeError):
                meta = []
        else:
            meta = []
        meta.append(
            {
                "content": text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "conversation_id": str(conversation_id),
            },
        )
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    async def search_long_term(
        self,
        user_id: str,
        query: str,
        k: int = LONG_TERM_TOP_K,
    ) -> list[dict]:
        """Retrieve top similar memories above a similarity threshold."""
        index_path, meta_path, _base = self._memory_paths(str(user_id))
        if not os.path.exists(index_path) or not os.path.exists(meta_path):
            return []
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
        if not meta:
            return []
        q = np.array([await embedder.embed_text(query)], dtype="float32")
        q = _normalize_vectors(q)
        index = faiss.read_index(index_path)
        limit = min(index.ntotal, max(k * 4, k))
        scores, ids = index.search(q, limit)
        results: list[dict] = []
        for rank, idx in enumerate(ids[0]):
            if idx < 0:
                continue
            score = float(scores[0][rank])
            if score < LONG_TERM_SCORE_THRESHOLD:
                continue
            if 0 <= idx < len(meta):
                row = meta[idx]
                content = str(row.get("content", ""))
                results.append(
                    {
                        "content": content,
                        "score": score,
                        "timestamp": str(row.get("timestamp", "")),
                    },
                )
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:k]

    async def delete_all(self, user_id: str) -> None:
        """Remove all short-term keys and on-disk long-term index for a user."""
        client = await self._redis()
        prefix = f"memory:{user_id}:"
        async for key in client.scan_iter(f"{prefix}*"):
            await client.delete(key)
        _, _, base = self._memory_paths(str(user_id))
        if os.path.isdir(base):
            shutil.rmtree(base, ignore_errors=True)

    async def format_for_prompt(
        self,
        short_term: list[dict],
        long_term: list[dict],
    ) -> tuple[str, str]:
        """Render memory sections for the system prompt."""
        short_lines: list[str] = []
        for m in short_term:
            role = m.get("role", "")
            content = m.get("content", "")
            short_lines.append(f"{role}: {content}")
        short_term_str = "\n".join(short_lines) if short_lines else "None"

        if not long_term:
            long_term_str = "None"
        else:
            bullets = []
            for item in long_term:
                bullets.append(f"- ({item.get('score', 0):.2f}) {item.get('content', '')}")
            long_term_str = "\n".join(bullets)
        return short_term_str, long_term_str


memory_service = MemoryService()
