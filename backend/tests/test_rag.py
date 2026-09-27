"""Document chunking, ingestion, retrieval, deletion, and concurrent writers."""

from __future__ import annotations

import asyncio
import os
import uuid

import numpy as np
from httpx import AsyncClient

from config import settings
from db.session import AsyncSessionLocal
from services.rag_service import _mmr_select_rows, rag_service
from utils.chunker import chunker
from utils.faiss_store import FaissStore

PHOTOSYNTHESIS = (
    "Photosynthesis converts sunlight water and carbon dioxide into glucose and oxygen "
    "inside the chloroplasts of green plant leaves."
)
VOLCANO = (
    "Volcanoes erupt when magma pressure beneath the crust forces molten rock ash and gas "
    "through vents in the earth surface."
)


async def _user_id(client: AsyncClient, auth: dict) -> str:
    return (await client.get("/api/v1/auth/me", headers=auth)).json()["id"]


async def _ingest(user_id: str, text: str, filename: str = "notes.txt"):
    async with AsyncSessionLocal() as db:
        return await rag_service.ingest_document(user_id, text.encode(), filename, db)


def test_chunker_splits_long_pages_and_keeps_page_numbers() -> None:
    long_page = " ".join(f"sentence number {i}." for i in range(400))
    chunks = chunker.chunk_by_page([(1, "short first page"), (2, long_page)])
    assert chunks[0].metadata["page_number"] == 1
    later = [c for c in chunks if c.metadata["page_number"] == 2]
    assert len(later) > 1
    assert all(len(c.page_content) <= settings.CHUNK_SIZE for c in chunks)


def test_mmr_prefers_diverse_results() -> None:
    a = np.array([1.0, 0.0])
    near_a = np.array([0.99, 0.14])
    b = np.array([0.0, 1.0])
    rows = _mmr_select_rows(np.vstack([a, near_a, b]), [0.95, 0.94, 0.80], k=2)
    assert rows == [0, 2]


async def test_ingest_then_retrieve_relevant_chunk(client: AsyncClient, auth: dict) -> None:
    uid = await _user_id(client, auth)
    doc = await _ingest(uid, PHOTOSYNTHESIS, "plants.txt")
    await _ingest(uid, VOLCANO, "volcano.txt")
    assert doc.status == "ready"
    assert doc.num_chunks == 1

    # The fake embedder is bag-of-words, so the query shares most of the chunk's words.
    hits = await rag_service.retrieve_context(uid, "How does " + PHOTOSYNTHESIS)
    assert [h.filename for h in hits] == ["plants.txt"]
    assert hits[0].page_number == 1


async def test_irrelevant_query_returns_nothing(client: AsyncClient, auth: dict) -> None:
    uid = await _user_id(client, auth)
    await _ingest(uid, PHOTOSYNTHESIS)
    assert await rag_service.retrieve_context(uid, "quarterly revenue forecast spreadsheet") == []


async def test_user_indexes_are_isolated(client: AsyncClient, auth: dict) -> None:
    uid = await _user_id(client, auth)
    await _ingest(uid, PHOTOSYNTHESIS)
    other = str(uuid.uuid4())
    assert await rag_service.retrieve_context(other, PHOTOSYNTHESIS) == []


async def test_upload_endpoint_indexes_in_background(client: AsyncClient, auth: dict) -> None:
    resp = await client.post(
        "/api/v1/rag/upload",
        files={"file": ("bio.md", PHOTOSYNTHESIS.encode(), "text/markdown")},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"

    docs = (await client.get("/api/v1/rag/documents", headers=auth)).json()
    assert docs[0]["status"] == "ready"

    search = await client.get(
        "/api/v1/rag/search",
        params={"q": PHOTOSYNTHESIS},
        headers=auth,
    )
    assert search.json()["total_found"] >= 1


async def test_upload_rejects_unsupported_type(client: AsyncClient, auth: dict) -> None:
    resp = await client.post(
        "/api/v1/rag/upload",
        files={"file": ("run.exe", b"MZ", "application/octet-stream")},
        headers=auth,
    )
    assert resp.status_code == 400


async def test_invalid_utf8_marks_document_failed(client: AsyncClient, auth: dict) -> None:
    uid = await _user_id(client, auth)
    async with AsyncSessionLocal() as db:
        doc = await rag_service.ingest_document(uid, b"\xff\xfe\xfa", "bad.txt", db)
    assert doc.status == "failed"


async def test_delete_document_removes_only_its_vectors(client: AsyncClient, auth: dict) -> None:
    uid = await _user_id(client, auth)
    plants = await _ingest(uid, PHOTOSYNTHESIS, "plants.txt")
    await _ingest(uid, VOLCANO, "volcano.txt")

    resp = await client.delete(f"/api/v1/rag/document/{plants.id}", headers=auth)
    assert resp.status_code == 200

    assert await rag_service.retrieve_context(uid, PHOTOSYNTHESIS) == []
    remaining = await rag_service.retrieve_context(uid, VOLCANO)
    assert remaining and remaining[0].filename == "volcano.txt"
    docs = (await client.get("/api/v1/rag/documents", headers=auth)).json()
    assert [d["filename"] for d in docs] == ["volcano.txt"]


async def test_cannot_delete_another_users_document(client: AsyncClient, auth: dict) -> None:
    from tests.conftest import register

    uid = await _user_id(client, auth)
    doc = await _ingest(uid, PHOTOSYNTHESIS)
    eve = await register(client, "eve@example.com")
    resp = await client.delete(
        f"/api/v1/rag/document/{doc.id}",
        headers={"Authorization": f"Bearer {eve['access_token']}"},
    )
    assert resp.status_code == 404


async def test_concurrent_ingests_keep_index_and_metadata_consistent(
    client: AsyncClient, auth: dict
) -> None:
    uid = await _user_id(client, auth)
    texts = [f"document {i} about topic{i} with unique words alpha{i} beta{i}" for i in range(8)]
    docs = await asyncio.gather(*(_ingest(uid, t, f"doc{i}.txt") for i, t in enumerate(texts)))
    assert all(d.status == "ready" for d in docs)

    store = FaissStore(os.path.join(settings.FAISS_INDEX_DIR, uid, "docs"))
    index, metas = store._load()
    assert index is not None
    assert index.ntotal == len(metas) == sum(d.num_chunks for d in docs)
    assert sorted(m["faiss_index"] for m in metas) == list(range(index.ntotal))
