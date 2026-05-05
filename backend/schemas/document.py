"""Document and RAG Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    """Uploaded document metadata."""

    id: UUID
    filename: str
    file_type: str
    file_size_bytes: int | None
    num_chunks: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChunkResult(BaseModel):
    """Single retrieved RAG chunk."""

    content: str
    filename: str
    page_number: int | None
    similarity_score: float
    chunk_index: int


class RAGSearchResponse(BaseModel):
    """RAG search API response."""

    query: str
    chunks: list[ChunkResult]
    total_found: int
