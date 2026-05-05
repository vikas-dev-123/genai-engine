"""Document upload and retrieval endpoints."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import AsyncSessionLocal
from dependencies import get_current_user, get_db
from models.document import Document as DocumentORM
from models.user import User
from schemas.document import DocumentResponse, RAGSearchResponse
from services.rag_service import rag_service

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_EXTS = frozenset({".pdf", ".txt", ".docx", ".md"})


async def _ingest_background(user_id: str, doc_id: uuid.UUID, filename: str, data: bytes) -> None:
    async with AsyncSessionLocal() as session:
        await rag_service.ingest_document(
            user_id,
            data,
            filename,
            session,
            doc_id=doc_id,
        )


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Accept a document and index it asynchronously."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF, TXT, DOCX, or MD uploads are supported.",
        )
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File exceeds 50MB limit.",
        )
    doc = DocumentORM(
        user_id=current.id,
        filename=file.filename or f"document{suffix}",
        file_type=suffix.lstrip("."),
        file_size_bytes=len(data),
        status="processing",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    background_tasks.add_task(
        _ingest_background,
        str(current.id),
        doc.id,
        doc.filename,
        data,
    )
    return DocumentResponse.model_validate(doc)


@router.get("/documents", response_model=list[DocumentResponse])
async def list_docs(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    """List uploaded knowledge-base documents."""
    return await rag_service.list_documents(str(current.id), db)


@router.delete("/document/{doc_id}")
async def remove_document(
    doc_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Delete a document and its vectors."""
    result = await db.execute(
        select(DocumentORM).where(
            DocumentORM.id == doc_id,
            DocumentORM.user_id == current.id,
        ),
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await rag_service.delete_document(str(current.id), str(doc_id), db)
    return {"deleted": True}


@router.get("/search", response_model=RAGSearchResponse)
async def search_kb(
    q: str,
    current: User = Depends(get_current_user),
) -> RAGSearchResponse:
    """Search the user's knowledge base."""
    chunks = await rag_service.retrieve_context(str(current.id), q)
    return RAGSearchResponse(query=q, chunks=chunks, total_found=len(chunks))
