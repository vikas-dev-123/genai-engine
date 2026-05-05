"""Retrieval-Augmented Generation: ingest, index, and search user documents."""

from __future__ import annotations

import io
import json
import os
import uuid
from typing import Any

import docx
import faiss
import fitz
import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.document import Document as DocumentORM
from schemas.document import ChunkResult, DocumentResponse
from utils.chunker import chunker
from utils.embedder import embedder


def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return vectors / norms


def _meta_for_vector_id(metas: list[dict[str, Any]], faiss_id: int) -> dict[str, Any] | None:
    for m in metas:
        if int(m.get("faiss_index", -1)) == faiss_id:
            return m
    if 0 <= faiss_id < len(metas):
        return metas[faiss_id]
    return None


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
                float(np.dot(candidate_embeddings[r], candidate_embeddings[s]))
                for s in selected
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

    def _ensure_docs_dir(self, user_id: str) -> str:
        path = os.path.join(settings.FAISS_INDEX_DIR, str(user_id), "docs")
        os.makedirs(path, exist_ok=True)
        return path

    def _paths(self, user_id: str) -> tuple[str, str]:
        base = self._ensure_docs_dir(user_id)
        return os.path.join(base, "index.faiss"), os.path.join(base, "meta.json")

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
            pages = self._extract_pages(file_bytes, file_type)
            chunks = chunker.chunk_by_page(pages)
            uid_s = str(user_id)
            for i, ch in enumerate(chunks):
                md = ch.metadata or {}
                md.update(
                    {
                        "filename": filename,
                        "doc_id": str(doc_uuid),
                        "user_id": uid_s,
                        "chunk_index": i,
                    },
                )
                ch.metadata = md
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
            vectors = np.array(embeddings, dtype="float32")
            vectors = _normalize_vectors(vectors)

            index_path, meta_path = self._paths(uid_s)
            if os.path.exists(index_path):
                index = faiss.read_index(index_path)
            else:
                index = faiss.IndexFlatIP(vectors.shape[1])
            metas: list[dict[str, Any]] = []
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, encoding="utf-8") as f:
                        loaded = json.load(f)
                    metas = loaded if isinstance(loaded, list) else []
                except (OSError, json.JSONDecodeError):
                    metas = []
            start_idx = index.ntotal
            if vectors.shape[0] > 0:
                if index.d != vectors.shape[1]:
                    raise RuntimeError("Embedding dimension mismatch for existing index.")
                index.add(vectors)
            new_metas: list[dict[str, Any]] = []
            for i, ch in enumerate(chunks):
                md = ch.metadata or {}
                new_metas.append(
                    {
                        "content": ch.page_content,
                        "filename": md.get("filename", filename),
                        "page_number": md.get("page_number"),
                        "doc_id": str(doc_uuid),
                        "user_id": uid_s,
                        "chunk_index": int(md.get("chunk_index", i)),
                        "faiss_index": start_idx + i,
                    },
                )
            metas.extend(new_metas)
            if vectors.shape[0] > 0:
                faiss.write_index(index, index_path)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metas, f, indent=2)

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
        index_path, meta_path = self._paths(str(user_id))
        if not os.path.exists(index_path) or not os.path.exists(meta_path):
            return []
        try:
            with open(meta_path, encoding="utf-8") as f:
                metas = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
        if not metas:
            return []
        index = faiss.read_index(index_path)
        q = np.array([await embedder.embed_text(query)], dtype="float32")
        q = _normalize_vectors(q)
        nprobe = min(index.ntotal, max(k * 2, k))
        scores, ids = index.search(q, nprobe)
        candidates: list[tuple[int, float, dict[str, Any]]] = []
        for rank, idx in enumerate(ids[0]):
            if idx < 0:
                continue
            score = float(scores[0][rank])
            if score < 0.70:
                continue
            meta = _meta_for_vector_id(metas, int(idx))
            if meta is None:
                continue
            candidates.append((idx, score, meta))
        if not candidates:
            return []
        cand_indices = [c[0] for c in candidates]
        cand_scores = [c[1] for c in candidates]
        cand_matrix = np.vstack([index.reconstruct(int(i)) for i in cand_indices])
        mmr_rows = _mmr_select_rows(cand_matrix, cand_scores, k)
        out: list[ChunkResult] = []
        for row_i in mmr_rows:
            _faiss_i, score, meta = candidates[row_i]
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
        index_path, meta_path = self._paths(uid)
        if os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    metas = json.load(f)
            except (OSError, json.JSONDecodeError):
                metas = []
        else:
            metas = []
        keep = [m for m in metas if str(m.get("doc_id")) != str(doc_id)]
        if os.path.exists(index_path) and os.path.exists(meta_path):
            try:
                old_index = faiss.read_index(index_path)
                dim = old_index.d
                new_index = faiss.IndexFlatIP(dim)
                new_vectors: list[np.ndarray] = []
                for m in keep:
                    idx = int(m.get("faiss_index", -1))
                    if 0 <= idx < old_index.ntotal:
                        new_vectors.append(old_index.reconstruct(idx))
                if new_vectors:
                    mat = np.vstack(new_vectors).astype("float32")
                    new_index.add(mat)
                faiss.write_index(new_index, index_path)
                for i, m in enumerate(keep):
                    m["faiss_index"] = i
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(keep, f, indent=2)
            except Exception:
                if os.path.exists(index_path):
                    os.remove(index_path)
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump([], f)
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
