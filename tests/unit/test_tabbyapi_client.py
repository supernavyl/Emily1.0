"""Unit tests for TabbyAPIClient.

Uses ``respx`` to mock HTTP at the transport layer — no real network required.
Mirrors the test patterns from ``tests/unit/test_ollama_provider.py``.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from llm.client import ChatMessage
from llm.tabbyapi_client import TabbyAPIClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client() -> TabbyAPIClient:  # type: ignore[misc]
    c = TabbyAPIClient(base_url="http://localhost:5000", api_key="test-key")
    yield c
    await c.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sse(*payloads: dict, done: bool = True) -> bytes:
    """Build a complete SSE response body from a list of chunk dicts."""
    lines: list[str] = []
    for p in payloads:
        lines.append(f"data: {json.dumps(p)}")
        lines.append("")
    if done:
        lines.append("data: [DONE]")
        lines.append("")
    return "\n".join(lines).encode()


def _chunk(content: str, finish: str | None = None) -> dict:
    return {
        "choices": [{"delta": {"content": content}, "finish_reason": finish}],
        "usage": None,
    }


def _usage_chunk(prompt: int, completion: int) -> dict:
    return {
        "choices": [{"delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_ok(client: TabbyAPIClient) -> None:
    with respx.mock:
        respx.get("http://localhost:5000/v1/models").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "QwQ-32B-abliterated"}]},
            )
        )
        assert await client.health_check() is True


@pytest.mark.asyncio
async def test_health_check_no_model(client: TabbyAPIClient) -> None:
    with respx.mock:
        respx.get("http://localhost:5000/v1/models").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        assert await client.health_check() is False


@pytest.mark.asyncio
async def test_health_check_unreachable(client: TabbyAPIClient) -> None:
    with respx.mock:
        respx.get("http://localhost:5000/v1/models").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        assert await client.health_check() is False


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models(client: TabbyAPIClient) -> None:
    with respx.mock:
        respx.get("http://localhost:5000/v1/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "Qwen2.5-14B-Instruct-abliterated"},
                        {"id": "QwQ-32B-abliterated"},
                    ]
                },
            )
        )
        models = await client.list_models()
        assert models == ["Qwen2.5-14B-Instruct-abliterated", "QwQ-32B-abliterated"]


# ---------------------------------------------------------------------------
# chat_stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_basic(client: TabbyAPIClient) -> None:
    sse_body = _sse(
        _chunk("Hello"),
        _chunk(", world"),
        _usage_chunk(10, 5),
    )

    with respx.mock:
        respx.post("http://localhost:5000/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, content=sse_body, headers={"content-type": "text/event-stream"}
            )
        )
        messages = [ChatMessage(role="user", content="Hi")]
        chunks = []
        async for chunk in client.chat_stream(
            model="Qwen2.5-14B-Instruct-abliterated",
            messages=messages,
        ):
            chunks.append(chunk)

    text = "".join(c.content for c in chunks)
    assert "Hello" in text
    assert ", world" in text


@pytest.mark.asyncio
async def test_chat_stream_done_signal(client: TabbyAPIClient) -> None:
    sse_body = _sse(_chunk("Hi"), _usage_chunk(5, 2))

    with respx.mock:
        respx.post("http://localhost:5000/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, content=sse_body, headers={"content-type": "text/event-stream"}
            )
        )
        chunks = []
        async for chunk in client.chat_stream(
            model="Qwen2.5-14B-Instruct-abliterated",
            messages=[ChatMessage(role="user", content="hello")],
        ):
            chunks.append(chunk)

    assert any(c.done for c in chunks)


# ---------------------------------------------------------------------------
# chat (non-streaming)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_collects_stream(client: TabbyAPIClient) -> None:
    sse_body = _sse(_chunk("Hello"), _chunk("!"), _usage_chunk(3, 2))

    with respx.mock:
        respx.post("http://localhost:5000/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, content=sse_body, headers={"content-type": "text/event-stream"}
            )
        )
        result = await client.chat(
            model="Qwen2.5-14B-Instruct-abliterated",
            messages=[ChatMessage(role="user", content="Hey")],
        )

    assert result.content == "Hello!"
    assert result.model == "Qwen2.5-14B-Instruct-abliterated"


# ---------------------------------------------------------------------------
# embed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed(client: TabbyAPIClient) -> None:
    vec = [0.1, 0.2, 0.3]
    with respx.mock:
        respx.post("http://localhost:5000/v1/embeddings").mock(
            return_value=httpx.Response(200, json={"data": [{"embedding": vec}]})
        )
        result = await client.embed(model="bge-m3", text="hello")

    assert result.embedding == vec
    assert result.model == "bge-m3"


@pytest.mark.asyncio
async def test_embed_batch(client: TabbyAPIClient) -> None:
    vec = [0.1, 0.2]
    with respx.mock:
        respx.post("http://localhost:5000/v1/embeddings").mock(
            return_value=httpx.Response(200, json={"data": [{"embedding": vec}]})
        )
        results = await client.embed_batch(model="bge-m3", texts=["a", "b"])

    assert len(results) == 2
    assert results[0].embedding == vec


# ---------------------------------------------------------------------------
# keep_alive (no-op)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keep_alive_noop(client: TabbyAPIClient) -> None:
    """keep_alive must not raise and must not make any HTTP calls."""
    with respx.mock:
        await client.keep_alive(model="QwQ-32B-abliterated")
        assert len(respx.calls) == 0


# ---------------------------------------------------------------------------
# Auth header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_key_sent_as_header() -> None:
    c = TabbyAPIClient(base_url="http://localhost:5000", api_key="secret-key")
    try:
        with respx.mock:
            route = respx.get("http://localhost:5000/v1/models").mock(
                return_value=httpx.Response(200, json={"data": [{"id": "model"}]})
            )
            await c.health_check()
            request = route.calls[0].request
            # TabbyAPIClient sends x-api-key header
            assert request.headers.get("x-api-key") == "secret-key"
    finally:
        await c.close()


@pytest.mark.asyncio
async def test_no_auth_header_when_key_empty() -> None:
    c = TabbyAPIClient(base_url="http://localhost:5000", api_key="")
    try:
        with respx.mock:
            route = respx.get("http://localhost:5000/v1/models").mock(
                return_value=httpx.Response(200, json={"data": [{"id": "model"}]})
            )
            await c.health_check()
            request = route.calls[0].request
            assert "x-api-key" not in request.headers
    finally:
        await c.close()


# ---------------------------------------------------------------------------
# LLMClientProtocol conformance
# ---------------------------------------------------------------------------


def test_protocol_conformance() -> None:
    from llm.base import LLMClientProtocol

    assert isinstance(TabbyAPIClient(), LLMClientProtocol)
