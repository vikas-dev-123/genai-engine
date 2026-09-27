"""Conversation memory: Redis short-term buffer and FAISS long-term recall."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import datetime, timezone

import numpy as np
import redis.asyncio as redis
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from config import settings
from redis_client import get_shared_redis
from utils.embedder import embedder
from utils.faiss_store import FaissStore, normalize_vectors

SHORT_TERM_TTL_SECONDS = 24 * 3600
SHORT_TERM_MAX_MESSAGES = 20
LONG_TERM_TOP_K = 5
LONG_TERM_SCORE_THRESHOLD = 0.75


class MemoryService:
    """Hybrid memory layer for chat context."""

    async def _redis(self) -> redis.Redis:
        return await get_shared_redis()

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

    def _memory_dir(self, user_id: str) -> str:
        return os.path.join(settings.FAISS_INDEX_DIR, str(user_id), "memory")

    def _store(self, user_id: str) -> FaissStore:
        return FaissStore(self._memory_dir(user_id))

    async def add_long_term(
        self,
        user_id: str,
        user_msg: str,
        assistant_msg: str,
        conversation_id: str,
    ) -> None:
        """Persist a conversational exchange in FAISS-backed long-term memory."""
        text = f"User: {user_msg}\nAssistant: {assistant_msg}"
        vector = normalize_vectors(np.array(await embedder.embed_batch([text]), dtype="float32"))
        meta = {
            "content": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "conversation_id": str(conversation_id),
        }
        await asyncio.to_thread(self._store(user_id).add, vector, [meta])

    async def search_long_term(
        self,
        user_id: str,
        query: str,
        k: int = LONG_TERM_TOP_K,
    ) -> list[dict]:
        """Retrieve top similar memories above a similarity threshold."""
        store = self._store(user_id)
        if not os.path.exists(store.index_path):
            return []
        q = normalize_vectors(np.array([await embedder.embed_text(query)], dtype="float32"))
        hits = await asyncio.to_thread(store.search, q, k * 4, LONG_TERM_SCORE_THRESHOLD)
        results = [
            {
                "content": str(meta.get("content", "")),
                "score": score,
                "timestamp": str(meta.get("timestamp", "")),
            }
            for score, meta, _vector in hits
        ]
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:k]

    async def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        """Forget one conversation: its Redis buffer and its long-term memories."""
        client = await self._redis()
        await client.delete(self._memory_key(user_id, conversation_id))
        store = self._store(user_id)
        if os.path.exists(store.index_path):
            await asyncio.to_thread(
                store.remove_where,
                lambda m: m.get("conversation_id") == str(conversation_id),
            )

    async def delete_all(self, user_id: str) -> None:
        """Remove all short-term keys and on-disk long-term index for a user."""
        client = await self._redis()
        prefix = f"memory:{user_id}:"
        async for key in client.scan_iter(f"{prefix}*"):
            await client.delete(key)
        base = self._memory_dir(user_id)
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
