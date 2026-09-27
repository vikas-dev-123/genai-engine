"""Retrieval-Augmented Generation: ingest, index, and search user documents."""

from __future__ import annotations

import asyncio
import io
import os
import uuid
from typing import Any

import docx
import fitz
import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.document import Document as DocumentORM
from schemas.document import ChunkResult, DocumentResponse
from utils.chunker import chunker
from utils.embedder import embedder
from utils.faiss_store import FaissStore, normalize_vectors

MIN_RELEVANCE_SCORE = 0.70


def _mmr_select_rows(
    candidate_embeddings: np.ndarray,
    candidate_scores: list[float],
    k: int,
    lambda_mult: float = 0.5,
) -> list[int]:
    """Return row indices into the candidate list using MMR."""
    n = candidate_embeddings.shape[0]
    if n == 0 or k <= 0:
        return []
    selected: list[int] = []
    remaining = set(range(n))
    first = int(np.argmax(candidate_scores))
    selected.append(first)
    remaining.remove(first)
    while remaining and len(selected) < k:
        best_row = -1
        best_mmr = -1e9
        for r in remaining:
            rel = candidate_scores[r]
            sims = [
                float(np.dot(candidate_embeddings[r], candidate_embeddings[s])) for s in selected
            ]
            max_sim = max(sims) if sims else 0.0
            mmr = lambda_mult * rel - (1.0 - lambda_mult) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_row = r
        if best_row >= 0:
            selected.append(best_row)
            remaining.remove(best_row)
    return selected


class RAGService:
    """FAISS + Gemini embeddings RAG pipeline per user."""

    def __init__(self) -> None:
        pass

    def _store(self, user_id: str) -> FaissStore:
        return FaissStore(os.path.join(settings.FAISS_INDEX_DIR, str(user_id), "docs"))

    def _detect_type(self, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext not in ("pdf", "txt", "docx", "md"):
            raise ValueError(f"Unsupported file type: {ext}")
        return ext

    def _extract_pages(self, file_bytes: bytes, file_type: str) -> list[tuple[int, str]]:
        if file_type == "pdf":
            try:
                doc = fitz.open(stream=file_bytes, filetype="pdf")
            except Exception as exc:
                raise ValueError("Failed to open PDF") from exc
            pages: list[tuple[int, str]] = []
            for i, page in enumerate(doc):
                try:
                    text = page.get_text()
                except Exception:
                    text = ""
                pages.append((i + 1, text))
            return pages
        if file_type == "docx":
            try:
                document = docx.Document(io.BytesIO(file_bytes))
            except Exception as exc:
                raise ValueError("Failed to read DOCX") from exc
            paragraphs = [p.text for p in document.paragraphs]
            return [(1, "\n".join(paragraphs))]
        if file_type in ("txt", "md"):
            try:
                text = file_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("File is not valid UTF-8") from exc
            return [(1, text)]
        raise ValueError(f"Unsupported type {file_type}")

    async def ingest_document(
        self,
        user_id: str,
        file_bytes: bytes,
        filename: str,
        db: AsyncSession,
        doc_id: uuid.UUID | None = None,
    ) -> DocumentResponse:
        """Parse a document, chunk, embed, and append to the user's FAISS index."""
        file_type = self._detect_type(filename)
        doc_uuid = doc_id or uuid.uuid4()
        if doc_id is None:
            orm_doc = DocumentORM(
                id=doc_uuid,
                user_id=uuid.UUID(str(user_id)),
                filename=filename,
                file_type=file_type,
                file_size_bytes=len(file_bytes),
                status="processing",
            )
            db.add(orm_doc)
            await db.commit()
            await db.refresh(orm_doc)
        else:
            existing = await db.execute(
                select(DocumentORM).where(DocumentORM.id == doc_uuid),
            )
            if existing.scalar_one_or_none() is None:
                raise ValueError("Document record not found for ingest")
        try:
            pages = await asyncio.to_thread(self._extract_pages, file_bytes, file_type)
            chunks = chunker.chunk_by_page(pages)
            uid_s = str(user_id)
            texts = [c.page_content for c in chunks]
            if not texts:
                result = await db.execute(select(DocumentORM).where(DocumentORM.id == doc_uuid))
                row = result.scalar_one()
                row.status = "ready"
                row.num_chunks = 0
                row.error_message = None
                await db.commit()
                await db.refresh(row)
                return DocumentResponse.model_validate(row)

            embeddings = await embedder.embed_batch(texts)
            vectors = normalize_vectors(np.array(embeddings, dtype="float32"))
            new_metas: list[dict[str, Any]] = [
                {
                    "content": ch.page_content,
                    "filename": filename,
                    "page_number": (ch.metadata or {}).get("page_number"),
                    "doc_id": str(doc_uuid),
                    "user_id": uid_s,
                    "chunk_index": i,
                }
                for i, ch in enumerate(chunks)
            ]
            await asyncio.to_thread(self._store(uid_s).add, vectors, new_metas)

            result = await db.execute(select(DocumentORM).where(DocumentORM.id == doc_uuid))
            row = result.scalar_one()
            row.status = "ready"
            row.num_chunks = len(chunks)
            row.error_message = None
            await db.commit()
            await db.refresh(row)
            return DocumentResponse.model_validate(row)
        except Exception as exc:
            result = await db.execute(select(DocumentORM).where(DocumentORM.id == doc_uuid))
            row = result.scalar_one_or_none()
            if row:
                row.status = "failed"
                row.error_message = str(exc)[:2000]
                await db.commit()
                await db.refresh(row)
                return DocumentResponse.model_validate(row)
            raise

    async def retrieve_context(
        self,
        user_id: str,
        query: str,
        k: int | None = None,
    ) -> list[ChunkResult]:
        """Search the user's knowledge index with embedding + MMR."""
        k = k or settings.MAX_RAG_RESULTS
        store = self._store(str(user_id))
        if not os.path.exists(store.index_path):
            return []
        q = normalize_vectors(np.array([await embedder.embed_text(query)], dtype="float32"))
        candidates = await asyncio.to_thread(store.search, q, k * 2, MIN_RELEVANCE_SCORE)
        if not candidates:
            return []
        cand_scores = [c[0] for c in candidates]
        cand_matrix = np.vstack([c[2] for c in candidates])
        mmr_rows = _mmr_select_rows(cand_matrix, cand_scores, k)
        out: list[ChunkResult] = []
        for row_i in mmr_rows:
            score, meta, _vector = candidates[row_i]
            out.append(
                ChunkResult(
                    content=str(meta.get("content", "")),
                    filename=str(meta.get("filename", "")),
                    page_number=meta.get("page_number"),
                    similarity_score=float(score),
                    chunk_index=int(meta.get("chunk_index", 0)),
                ),
            )
        return out

    def format_rag_context(self, chunks: list[ChunkResult]) -> tuple[str, str]:
        """Build context block and numeric citation line for the prompt."""
        if not chunks:
            return "None", "None"
        blocks: list[str] = []
        cites: list[str] = []
        for i, ch in enumerate(chunks, start=1):
            page = ch.page_number if ch.page_number is not None else "?"
            blocks.append(f"[{i}] (Source: {ch.filename}, page {page})\n{ch.content}")
            cites.append(f"[{i}] {ch.filename} p.{page}")
        return "\n\n".join(blocks), ", ".join(cites)

    async def delete_document(
        self,
        user_id: str,
        doc_id: str,
        db: AsyncSession,
    ) -> None:
        """Remove all chunks for a document and delete the database row."""
        uid = str(user_id)
        await asyncio.to_thread(
            self._store(uid).remove_where,
            lambda m: str(m.get("doc_id")) == str(doc_id),
        )
        await db.execute(
            delete(DocumentORM).where(
                DocumentORM.id == uuid.UUID(str(doc_id)),
                DocumentORM.user_id == uuid.UUID(uid),
            ),
        )
        await db.commit()

    async def list_documents(
        self,
        user_id: str,
        db: AsyncSession,
    ) -> list[DocumentResponse]:
        """List documents owned by the user."""
        result = await db.execute(
            select(DocumentORM)
            .where(DocumentORM.user_id == uuid.UUID(str(user_id)))
            .order_by(DocumentORM.created_at.desc()),
        )
        rows = result.scalars().all()
        return [DocumentResponse.model_validate(r) for r in rows]


rag_service = RAGService()
