"""Chat streaming, persistence, failure handling, and conversation lifecycle."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable

from httpx import AsyncClient

from config import settings
from redis_client import get_shared_redis
from services.llm_service import INTERRUPTED_SUFFIX
from services.memory_service import memory_service
from tests.conftest import FakeAgent, parse_sse, register, token

STREAM = "/api/v1/chat/stream"


async def _history(client: AsyncClient, auth: dict, conv_id: str) -> list[dict]:
    resp = await client.get(f"/api/v1/chat/history/{conv_id}", headers=auth)
    assert resp.status_code == 200
    return resp.json()


async def test_stream_creates_conversation_and_persists_turn(
    client: AsyncClient, auth: dict, fake_agent: Callable[..., FakeAgent]
) -> None:
    fake_agent([token("Hello"), token(", Ada!")])
    resp = await client.post(STREAM, json={"message": "Say hello"}, headers=auth)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(resp.text)
    assert [e["type"] for e in events] == ["token", "token", "done"]
    conv_id = events[-1]["data"]["conversation_id"]

    history = await _history(client, auth, conv_id)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "Say hello"),
        ("assistant", "Hello, Ada!"),
    ]
    assert history[1]["id"] == events[-1]["data"]["message_id"]

    convs = (await client.get("/api/v1/chat/conversations", headers=auth)).json()
    assert convs[0]["title"] == "Say hello"
    assert convs[0]["message_count"] == 2


async def test_tool_events_are_streamed_and_stored(
    client: AsyncClient, auth: dict, fake_agent: Callable[..., FakeAgent]
) -> None:
    fake_agent(
        [
            {
                "event": "on_tool_start",
                "name": "web_search",
                "run_id": "r1",
                "data": {"input": {"query": "weather"}},
            },
            {
                "event": "on_tool_end",
                "name": "web_search",
                "run_id": "r1",
                "data": {"output": "Sunny"},
            },
            token("It is sunny."),
        ],
    )
    events = parse_sse((await client.post(STREAM, json={"message": "Weather?"}, headers=auth)).text)
    assert [e["type"] for e in events] == ["tool_call", "tool_result", "token", "done"]
    assert events[0]["data"] == {"name": "web_search", "input": {"query": "weather"}}

    history = await _history(client, auth, events[-1]["data"]["conversation_id"])
    assert history[1]["tool_calls"] == [
        {"name": "web_search", "input": {"query": "weather"}, "output": "Sunny"}
    ]


async def test_follow_up_turn_receives_history_once(
    client: AsyncClient, auth: dict, fake_agent: Callable[..., FakeAgent]
) -> None:
    fake_agent([token("Nice to meet you")])
    first = parse_sse((await client.post(STREAM, json={"message": "I am Ada"}, headers=auth)).text)
    conv_id = first[-1]["data"]["conversation_id"]

    agent = fake_agent([token("You are Ada")])
    await client.post(
        STREAM, json={"message": "Who am I?", "conversation_id": conv_id}, headers=auth
    )

    assert agent.inputs is not None
    history = [m.content for m in agent.inputs["chat_history"]]
    assert history == ["I am Ada", "Nice to meet you"]
    # Recent turns are passed as messages only, not duplicated into the system prompt.
    assert "short_term_memory" not in agent.inputs


async def test_agent_failure_keeps_user_message_and_partial_reply(
    client: AsyncClient, auth: dict, fake_agent: Callable[..., FakeAgent]
) -> None:
    fake_agent([token("Partial "), token("answer"), token("never sent")], fail_after=2)
    events = parse_sse((await client.post(STREAM, json={"message": "Explain"}, headers=auth)).text)

    assert events[-1]["type"] == "error"
    assert "model exploded" not in events[-1]["data"]  # internals are not leaked to clients

    convs = (await client.get("/api/v1/chat/conversations", headers=auth)).json()
    history = await _history(client, auth, convs[0]["id"])
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "Explain"),
        ("assistant", "Partial answer" + INTERRUPTED_SUFFIX),
    ]


async def test_agent_failure_before_output_keeps_user_message(
    client: AsyncClient, auth: dict, fake_agent: Callable[..., FakeAgent]
) -> None:
    fake_agent([token("x")], fail_after=0)
    events = parse_sse((await client.post(STREAM, json={"message": "Hi"}, headers=auth)).text)
    assert events[-1]["type"] == "error"

    convs = (await client.get("/api/v1/chat/conversations", headers=auth)).json()
    history = await _history(client, auth, convs[0]["id"])
    assert [(m["role"], m["content"]) for m in history] == [("user", "Hi")]


async def test_cannot_access_another_users_conversation(
    client: AsyncClient, auth: dict, fake_agent: Callable[..., FakeAgent]
) -> None:
    fake_agent([token("secret")])
    events = parse_sse((await client.post(STREAM, json={"message": "mine"}, headers=auth)).text)
    conv_id = events[-1]["data"]["conversation_id"]

    other = await register(client, "eve@example.com")
    eve = {"Authorization": f"Bearer {other['access_token']}"}
    assert (await client.get(f"/api/v1/chat/history/{conv_id}", headers=eve)).status_code == 404
    assert (
        await client.delete(f"/api/v1/chat/conversation/{conv_id}", headers=eve)
    ).status_code == 404
    resp = await client.post(STREAM, json={"message": "x", "conversation_id": conv_id}, headers=eve)
    assert resp.status_code == 404
    assert (await client.get("/api/v1/chat/conversations", headers=eve)).json() == []


async def test_unknown_conversation_is_404(client: AsyncClient, auth: dict) -> None:
    resp = await client.post(
        STREAM, json={"message": "x", "conversation_id": str(uuid.uuid4())}, headers=auth
    )
    assert resp.status_code == 404


async def test_delete_conversation_removes_messages_and_memories(
    client: AsyncClient, auth: dict, fake_agent: Callable[..., FakeAgent]
) -> None:
    fake_agent([token("Paris is the capital of France")])
    events = parse_sse(
        (await client.post(STREAM, json={"message": "capital of France"}, headers=auth)).text
    )
    conv_id = events[-1]["data"]["conversation_id"]
    user_id = (await client.get("/api/v1/auth/me", headers=auth)).json()["id"]

    redis = await get_shared_redis()
    assert await redis.get(f"memory:{user_id}:{conv_id}") is not None
    assert await memory_service.search_long_term(user_id, "capital of France Paris")

    resp = await client.delete(f"/api/v1/chat/conversation/{conv_id}", headers=auth)
    assert resp.json() == {"deleted": True}
    assert (await client.get(f"/api/v1/chat/history/{conv_id}", headers=auth)).status_code == 404
    assert await redis.get(f"memory:{user_id}:{conv_id}") is None
    assert await memory_service.search_long_term(user_id, "capital of France Paris") == []


async def test_short_term_memory_is_summarized_when_full(
    client: AsyncClient, auth: dict, fake_agent: Callable[..., FakeAgent], monkeypatch
) -> None:
    async def fake_summary(user_id: str, conversation_id: str, messages: list[dict]) -> None:
        redis = await get_shared_redis()
        import json

        await redis.set(
            f"memory:{user_id}:{conversation_id}",
            json.dumps([{"role": "system", "content": f"summary of {len(messages)}"}]),
        )

    monkeypatch.setattr(memory_service, "summarize_and_reset", fake_summary)
    fake_agent([token("ok")])
    conv_id = None
    for i in range(11):  # 11 turns = 22 messages > 20
        body = {"message": f"turn {i}", "conversation_id": conv_id}
        conv_id = parse_sse((await client.post(STREAM, json=body, headers=auth)).text)[-1]["data"][
            "conversation_id"
        ]
    user_id = (await client.get("/api/v1/auth/me", headers=auth)).json()["id"]
    short = await memory_service.get_short_term(user_id, conv_id)
    assert short == [{"role": "system", "content": "summary of 22"}]


async def test_stream_requires_auth(client: AsyncClient) -> None:
    assert (await client.post(STREAM, json={"message": "hi"})).status_code == 401


async def test_long_term_memory_lives_under_user_dir(
    client: AsyncClient, auth: dict, fake_agent: Callable[..., FakeAgent]
) -> None:
    fake_agent([token("noted")])
    await client.post(STREAM, json={"message": "remember this"}, headers=auth)
    user_id = (await client.get("/api/v1/auth/me", headers=auth)).json()["id"]
    assert os.path.exists(os.path.join(settings.FAISS_INDEX_DIR, user_id, "memory", "index.faiss"))


async def test_client_disconnect_mid_stream_saves_partial_reply(
    client: AsyncClient, auth: dict, fake_agent: Callable[..., FakeAgent]
) -> None:
    from services.llm_service import llm_service

    user = (await client.get("/api/v1/auth/me", headers=auth)).json()
    fake_agent([token("first "), token("second"), token("third")])
    stream = llm_service.astream(
        message="tell me a story",
        user_id=user["id"],
        conversation_id=None,
        user_name="Ada",
        user_timezone="UTC",
    )
    first = await stream.__anext__()
    assert '"token"' in first
    await stream.aclose()  # what Starlette does when the browser goes away

    convs = (await client.get("/api/v1/chat/conversations", headers=auth)).json()
    history = await _history(client, auth, convs[0]["id"])
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "tell me a story"),
        ("assistant", "first " + INTERRUPTED_SUFFIX),
    ]
