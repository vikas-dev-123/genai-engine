"""Server-Sent Events formatting helpers."""

from __future__ import annotations

import json
from typing import Any


def format_sse_event(event_type: str, data: str | dict[str, Any]) -> str:
    """Format a single SSE `data:` frame."""
    payload = {"type": event_type, "data": data}
    return f"data: {json.dumps(payload)}\n\n"


async def token_event(text: str) -> str:
    """SSE event for a streamed model token."""
    return format_sse_event("token", text)


async def tool_call_event(name: str, input_data: dict[str, Any]) -> str:
    """SSE event when a tool starts."""
    return format_sse_event("tool_call", {"name": name, "input": input_data})


async def tool_result_event(name: str, output: str) -> str:
    """SSE event when a tool completes."""
    return format_sse_event("tool_result", {"name": name, "output": output})


async def done_event(conversation_id: str, message_id: str) -> str:
    """SSE event marking completion."""
    return format_sse_event(
        "done",
        {"conversation_id": str(conversation_id), "message_id": str(message_id)},
    )


async def error_event(message: str) -> str:
    """SSE event for errors."""
    return format_sse_event("error", message)
