"""Chat-related Pydantic schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat message request."""

    message: str = Field(min_length=1, max_length=10000)
    conversation_id: UUID | None = None
    rag_enabled: bool = True
    voice_mode: bool = False


class StreamChunk(BaseModel):
    """SSE event payload shape."""

    type: Literal["token", "tool_call", "tool_result", "done", "error"]
    data: str | dict[str, Any]


class MessageResponse(BaseModel):
    """Serialized chat message."""

    id: UUID
    role: str
    content: str
    tool_calls: list[Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    """Conversation summary for listings."""

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime | None
    message_count: int = 0

    model_config = {"from_attributes": True}
