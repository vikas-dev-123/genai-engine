"""Chat and streaming endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_user, get_db
from models.conversation import Conversation, Message
from models.user import User
from schemas.chat import ChatRequest, ConversationResponse, MessageResponse
from services.llm_service import llm_service

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/stream")
async def stream_chat(
    body: ChatRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream assistant output as Server-Sent Events."""

    async def event_generator():
        conversation_id = str(body.conversation_id) if body.conversation_id else None
        async for chunk in llm_service.astream(
            message=body.message,
            user_id=str(current.id),
            conversation_id=conversation_id,
            user_name=current.name,
            user_timezone=current.timezone,
            db=db,
            rag_enabled=body.rag_enabled,
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationResponse]:
    """List conversations for the authenticated user."""
    counts = (
        select(Message.conversation_id.label("cid"), func.count(Message.id).label("cnt"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    result = await db.execute(
        select(Conversation, counts.c.cnt)
        .outerjoin(counts, Conversation.id == counts.c.cid)
        .where(Conversation.user_id == current.id)
        .order_by(Conversation.updated_at.desc().nullslast(), Conversation.created_at.desc()),
    )
    out: list[ConversationResponse] = []
    for conv, cnt in result.all():
        out.append(
            ConversationResponse(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at or conv.created_at,
                message_count=int(cnt or 0),
            ),
        )
    return out


@router.get("/history/{conversation_id}", response_model=list[MessageResponse])
async def conversation_history(
    conversation_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    """Return ordered messages for a conversation."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current.id,
        ),
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    msgs = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc()),
    )
    rows = list(msgs.scalars().all())
    return [MessageResponse.model_validate(m) for m in rows]


@router.delete("/conversation/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Delete a conversation and its messages."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current.id,
        ),
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    await db.execute(
        delete(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current.id,
        ),
    )
    await db.commit()
    return {"deleted": True}
