"""Gemini + LangChain agent orchestration and streaming."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import anyio
import structlog
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.session import AsyncSessionLocal
from models.conversation import Conversation, Message
from services.memory_service import memory_service
from services.rag_service import rag_service
from tools.api_caller import APICallerTool
from tools.file_ops import FileReadTool, FileWriteTool
from tools.system_tool import SystemTool
from tools.web_search import WebSearchTool
from utils.streaming import format_sse_event

logger = structlog.get_logger(__name__)

INTERRUPTED_SUFFIX = "\n\n_[response interrupted]_"

SYSTEM_PROMPT = """You are GenAI Engine, a highly capable AI assistant.
You are precise, helpful, and always cite sources when using documents.

## User context
Name: {user_name}
Current time: {current_datetime}
Timezone: {user_timezone}

## Relevant memories from past conversations
{long_term_memory}

## Relevant document context
{rag_context}

## Document sources
{source_citations}

## Rules
- When document context is available, prefer it over training knowledge
- Always cite documents as [Source: filename, page N]
- When you need current information, use the web_search tool
- Before deleting files or running system commands, confirm with the user
- Always respond in the same language the user writes in
- Be concise but thorough"""


def _extract_text_from_chunk(chunk: object) -> str:
    """Normalize streamed content from Gemini/LangChain chunks."""
    if chunk is None:
        return ""
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


class LLMService:
    """Builds per-user agents and streams SSE-formatted events."""

    def __init__(self) -> None:
        self._llm: ChatGoogleGenerativeAI | None = None
        self._llm_loop: asyncio.AbstractEventLoop | None = None
        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad"),
            ],
        )

    def _get_tools(self, user_id: str) -> list:
        return [
            WebSearchTool(),
            FileReadTool(user_id=user_id),
            FileWriteTool(user_id=user_id),
            APICallerTool(),
            SystemTool(user_id=user_id),
        ]

    def _get_llm(self) -> ChatGoogleGenerativeAI:
        """Return the chat model, created inside the running event loop.

        langchain-google-genai only builds its async (streaming) gRPC client when the
        model is constructed while an event loop is running, and that client is bound
        to the loop. Creating it at import time leaves ``async_client`` as None, so it
        is built lazily here and once per loop (one per worker process in production).
        """
        loop = asyncio.get_running_loop()
        if self._llm is None or self._llm_loop is not loop:
            self._llm = ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=settings.GEMINI_TEMPERATURE,
                streaming=True,
                convert_system_message_to_human=True,
            )
            self._llm_loop = loop
        return self._llm

    def _build_agent(self, user_id: str) -> AgentExecutor:
        tools = self._get_tools(user_id)
        agent = create_tool_calling_agent(self._get_llm(), tools, self._prompt)
        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,
            max_iterations=5,
            handle_parsing_errors=True,
        )

    async def astream(
        self,
        message: str,
        user_id: str,
        conversation_id: str | None,
        user_name: str,
        user_timezone: str,
        rag_enabled: bool = True,
    ) -> AsyncIterator[str]:
        """Run the agent and stream SSE frames.

        Opens its own database session: a request-scoped session from a FastAPI
        dependency is closed before a StreamingResponse finishes sending.
        """
        async with AsyncSessionLocal() as db:
            async for frame in self._astream(
                db, message, user_id, conversation_id, user_name, user_timezone, rag_enabled
            ):
                yield frame

    async def _astream(
        self,
        db: AsyncSession,
        message: str,
        user_id: str,
        conversation_id: str | None,
        user_name: str,
        user_timezone: str,
        rag_enabled: bool,
    ) -> AsyncIterator[str]:
        uid = str(user_id)
        log = logger.bind(user_id=uid)
        conversation = await self._get_or_create_conversation(db, uid, conversation_id, message)
        if conversation is None:
            yield format_sse_event("error", "Conversation not found")
            return
        conv_id = conversation.id
        log = log.bind(conversation_id=str(conv_id))

        # Persist the user's message first so it survives agent errors and disconnects.
        db.add(Message(conversation_id=conv_id, role="user", content=message))
        conversation.updated_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            inputs = await self._build_inputs(
                uid, str(conv_id), message, user_name, user_timezone, rag_enabled
            )
        except Exception:
            log.exception("context_build_failed")
            yield format_sse_event("error", "Failed to prepare context. Please try again.")
            return

        full_response = ""
        tool_events: list[dict] = []
        tool_run_map: dict[str, dict] = {}
        completed = False
        assistant_id: uuid.UUID | None = None
        try:
            async for event in self._build_agent(uid).astream_events(inputs, version="v1"):
                event_name = event.get("event")
                data = event.get("data") or {}
                if event_name == "on_chat_model_stream":
                    text = _extract_text_from_chunk(data.get("chunk"))
                    if text:
                        full_response += text
                        yield format_sse_event("token", text)
                elif event_name == "on_tool_start":
                    name = event.get("name") or data.get("name") or ""
                    run_id = str(event.get("run_id", ""))
                    tool_input = data.get("input")
                    if tool_input is None:
                        tool_input = {}
                    if isinstance(tool_input, str):
                        try:
                            tool_input = json.loads(tool_input)
                        except json.JSONDecodeError:
                            tool_input = {"raw": tool_input}
                    tool_run_map[run_id] = {"name": name, "input": tool_input, "output": ""}
                    tool_events.append(tool_run_map[run_id])
                    yield format_sse_event("tool_call", {"name": name, "input": tool_input})
                elif event_name == "on_tool_end":
                    name = event.get("name") or data.get("name") or ""
                    output = data.get("output")
                    out_str = output if isinstance(output, str) else str(output)
                    run_id = str(event.get("run_id", ""))
                    if run_id in tool_run_map:
                        tool_run_map[run_id]["output"] = out_str
                    yield format_sse_event("tool_result", {"name": name, "output": out_str[:500]})
            completed = True
        except Exception:
            log.exception("agent_failed")
        finally:
            # Runs on success, on agent errors, and when the client disconnects mid-stream;
            # shielded so a cancelled request still records what was generated.
            with anyio.CancelScope(shield=True):
                assistant_id = await self._save_assistant(
                    db, conversation, full_response, tool_events, completed
                )

        if not completed:
            yield format_sse_event("error", "The assistant failed to respond. Please try again.")
            return

        try:
            await memory_service.add_to_short_term(uid, str(conv_id), message, full_response)
            await memory_service.add_long_term(uid, message, full_response, str(conv_id))
        except Exception:
            log.exception("memory_update_failed")

        yield format_sse_event(
            "done",
            {"conversation_id": str(conv_id), "message_id": str(assistant_id)},
        )

    async def _get_or_create_conversation(
        self,
        db: AsyncSession,
        uid: str,
        conversation_id: str | None,
        first_message: str,
    ) -> Conversation | None:
        if conversation_id:
            result = await db.execute(
                select(Conversation).where(
                    Conversation.id == uuid.UUID(conversation_id),
                    Conversation.user_id == uuid.UUID(uid),
                ),
            )
            return result.scalar_one_or_none()
        conversation = Conversation(
            user_id=uuid.UUID(uid),
            title=first_message.strip()[:50] or "New Conversation",
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return conversation

    async def _build_inputs(
        self,
        uid: str,
        conv_id: str,
        message: str,
        user_name: str,
        user_timezone: str,
        rag_enabled: bool,
    ) -> dict:
        short_term = await memory_service.get_short_term(uid, conv_id)
        long_term = await memory_service.search_long_term(uid, message)
        _short_str, long_str = await memory_service.format_for_prompt(short_term, long_term)

        if rag_enabled:
            chunks = await rag_service.retrieve_context(uid, message)
            rag_context, citations = rag_service.format_rag_context(chunks)
        else:
            rag_context = "None"
            citations = "None"

        # Recent turns go to the model as real chat messages (not duplicated in the system prompt).
        chat_history = []
        for m in short_term:
            role = m.get("role")
            content = m.get("content", "")
            if role == "user":
                chat_history.append(HumanMessage(content=content))
            elif role == "assistant":
                chat_history.append(AIMessage(content=content))
            elif role == "system":
                chat_history.append(SystemMessage(content=content))

        return {
            "input": message,
            "chat_history": chat_history,
            "user_name": user_name,
            "current_datetime": datetime.now(timezone.utc).isoformat(),
            "user_timezone": user_timezone,
            "long_term_memory": long_str,
            "rag_context": rag_context,
            "source_citations": citations,
        }

    async def _save_assistant(
        self,
        db: AsyncSession,
        conversation: Conversation,
        full_response: str,
        tool_events: list[dict],
        completed: bool,
    ) -> uuid.UUID | None:
        if not completed and not full_response:
            return None
        content = full_response if completed else full_response + INTERRUPTED_SUFFIX
        row = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=content,
            tool_calls=tool_events or None,
        )
        db.add(row)
        conversation.updated_at = datetime.now(timezone.utc)
        try:
            await db.commit()
        except Exception:
            logger.exception("assistant_persist_failed", conversation_id=str(conversation.id))
            await db.rollback()
            return None
        return row.id


llm_service = LLMService()
