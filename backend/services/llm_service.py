"""Gemini + LangChain agent orchestration and streaming."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.conversation import Conversation, Message
from services.memory_service import memory_service
from services.rag_service import rag_service
from tools.api_caller import APICallerTool
from tools.file_ops import FileReadTool, FileWriteTool
from tools.system_tool import SystemTool
from tools.web_search import WebSearchTool
from utils.streaming import format_sse_event

SYSTEM_PROMPT = """You are Jarvis, a highly capable AI assistant.
You are precise, helpful, and always cite sources when using documents.

## User context
Name: {user_name}
Current time: {current_datetime}
Timezone: {user_timezone}

## Recent conversation
{short_term_memory}

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
        self.llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=settings.GEMINI_TEMPERATURE,
            streaming=True,
            convert_system_message_to_human=True,
        )
        self._tool_cache: dict[str, list] = {}
        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad"),
            ],
        )

    def _get_tools(self, user_id: str) -> list:
        if user_id in self._tool_cache:
            return self._tool_cache[user_id]
        tools = [
            WebSearchTool(),
            FileReadTool(user_id=user_id),
            FileWriteTool(user_id=user_id),
            APICallerTool(),
            SystemTool(),
        ]
        self._tool_cache[user_id] = tools
        return tools

    def _build_agent(self, user_id: str) -> AgentExecutor:
        tools = self._get_tools(user_id)
        agent = create_tool_calling_agent(self.llm, tools, self._prompt)
        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
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
        db: AsyncSession,
        rag_enabled: bool = True,
    ) -> AsyncIterator[str]:
        """Run the agent and stream SSE frames."""
        uid = str(user_id)
        conv_uuid = uuid.UUID(conversation_id) if conversation_id else None
        if conv_uuid:
            result = await db.execute(
                select(Conversation).where(
                    Conversation.id == conv_uuid,
                    Conversation.user_id == uuid.UUID(uid),
                ),
            )
            conversation = result.scalar_one_or_none()
            if conversation is None:
                yield format_sse_event("error", "Conversation not found")
                return
        else:
            conversation = Conversation(
                user_id=uuid.UUID(uid),
                title="New Conversation",
            )
            db.add(conversation)
            await db.commit()
            await db.refresh(conversation)
        conv_id = conversation.id

        short_term = await memory_service.get_short_term(uid, str(conv_id))
        long_term = await memory_service.search_long_term(uid, message)
        short_str, long_str = await memory_service.format_for_prompt(short_term, long_term)

        if rag_enabled:
            chunks = await rag_service.retrieve_context(uid, message)
            rag_context, citations = rag_service.format_rag_context(chunks)
        else:
            rag_context = "None"
            citations = "None"

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

        agent = self._build_agent(uid)
        inputs = {
            "input": message,
            "chat_history": chat_history,
            "user_name": user_name,
            "current_datetime": datetime.now(timezone.utc).isoformat(),
            "user_timezone": user_timezone,
            "short_term_memory": short_str,
            "long_term_memory": long_str,
            "rag_context": rag_context,
            "source_citations": citations,
        }

        full_response = ""
        tool_events: list[dict] = []
        tool_run_map: dict[str, dict] = {}
        try:
            async for event in agent.astream_events(inputs, version="v1"):
                event_name = event.get("event")
                data = event.get("data") or {}
                if event_name == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    text = _extract_text_from_chunk(chunk)
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
                    payload = {"name": name, "input": tool_input}
                    tool_run_map[run_id] = {"name": name, "input": tool_input, "output": ""}
                    tool_events.append(tool_run_map[run_id])
                    yield format_sse_event("tool_call", payload)
                elif event_name == "on_tool_end":
                    name = event.get("name") or data.get("name") or ""
                    output = data.get("output")
                    out_str = output if isinstance(output, str) else str(output)
                    run_id = str(event.get("run_id", ""))
                    if run_id in tool_run_map:
                        tool_run_map[run_id]["output"] = out_str
                    yield format_sse_event(
                        "tool_result",
                        {"name": name, "output": out_str[:500]},
                    )
        except Exception as exc:
            yield format_sse_event("error", str(exc))
            return

        user_row = Message(
            conversation_id=conv_id,
            role="user",
            content=message,
            tool_calls=None,
        )
        db.add(user_row)

        stored_tools = tool_events if tool_events else None
        assistant_row = Message(
            conversation_id=conv_id,
            role="assistant",
            content=full_response,
            tool_calls=stored_tools,
        )
        db.add(assistant_row)

        if conversation.title in ("", "New Conversation"):
            conversation.title = (message.strip()[:50] or "New Conversation")
        conversation.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(assistant_row)

        await memory_service.add_to_short_term(uid, str(conv_id), message, full_response)
        await memory_service.add_long_term(uid, message, full_response, str(conv_id))

        yield format_sse_event(
            "done",
            {
                "conversation_id": str(conv_id),
                "message_id": str(assistant_row.id),
            },
        )


llm_service = LLMService()
