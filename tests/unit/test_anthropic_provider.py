"""Unit tests for the Anthropic provider and streaming engine.

All Anthropic SDK calls are mocked — no real API key is needed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from emily_chat.models.base import GenerationSettings, StreamChunk
from emily_chat.models.registry import get_model, get_default_model, list_models


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestModelRegistry:
    """Tests for the model registry lookup functions."""

    def test_get_model_found(self) -> None:
        """Known model IDs return a ModelSpec."""
        spec = get_model("claude-sonnet-4-5")
        assert spec is not None
        assert spec.provider == "anthropic"
        assert spec.default is True

    def test_get_model_not_found(self) -> None:
        """Unknown model IDs return None."""
        assert get_model("nonexistent-model-99") is None

    def test_get_default_model(self) -> None:
        """get_default_model returns the default spec."""
        key, spec = get_default_model()
        assert key == "claude-sonnet-4-5"
        assert spec.default is True

    def test_list_models_all(self) -> None:
        """list_models without filter returns all registered models."""
        models = list_models()
        assert len(models) >= 3

    def test_list_models_by_provider(self) -> None:
        """list_models('anthropic') returns only Anthropic models."""
        models = list_models(provider="anthropic")
        assert all(m.provider == "anthropic" for m in models)
        assert len(models) == 3

    def test_list_models_unknown_provider(self) -> None:
        """list_models with an unregistered provider returns empty list."""
        assert list_models(provider="nonexistent") == []


# ---------------------------------------------------------------------------
# Fake Anthropic SDK objects for mocking
# ---------------------------------------------------------------------------


@dataclass
class _FakeDelta:
    type: str
    thinking: str = ""
    text: str = ""


@dataclass
class _FakeEvent:
    type: str
    delta: _FakeDelta | None = None


@dataclass
class _FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class _FakeMessage:
    usage: _FakeUsage


class _FakeStream:
    """Simulates the Anthropic SDK's async stream context manager."""

    def __init__(self, events: list[_FakeEvent], final_message: _FakeMessage) -> None:
        self._events = events
        self._final = final_message

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def __aiter__(self) -> _FakeStream:
        self._idx = 0
        return self

    async def __anext__(self) -> _FakeEvent:
        if self._idx >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._idx]
        self._idx += 1
        return event

    async def get_final_message(self) -> _FakeMessage:
        return self._final


# ---------------------------------------------------------------------------
# Anthropic provider tests
# ---------------------------------------------------------------------------


def _build_fake_stream(
    thinking_chunks: list[str] | None = None,
    text_chunks: list[str] | None = None,
    input_tokens: int = 120,
    output_tokens: int = 60,
) -> _FakeStream:
    """Assemble a fake stream with thinking and text events."""
    events: list[_FakeEvent] = []

    for chunk in (thinking_chunks or []):
        events.append(
            _FakeEvent(
                type="content_block_delta",
                delta=_FakeDelta(type="thinking_delta", thinking=chunk),
            )
        )

    for chunk in (text_chunks or []):
        events.append(
            _FakeEvent(
                type="content_block_delta",
                delta=_FakeDelta(type="text_delta", text=chunk),
            )
        )

    return _FakeStream(
        events=events,
        final_message=_FakeMessage(
            usage=_FakeUsage(input_tokens=input_tokens, output_tokens=output_tokens)
        ),
    )


class TestAnthropicProvider:
    """Tests for AnthropicProvider.stream()."""

    @pytest.fixture(autouse=True)
    def _patch_anthropic(self) -> Any:
        """Patch the anthropic import so the provider can be instantiated."""
        mock_module = MagicMock()
        mock_client_instance = MagicMock()
        mock_module.AsyncAnthropic.return_value = mock_client_instance
        self._mock_client = mock_client_instance
        with patch.dict("sys.modules", {"anthropic": mock_module}):
            yield

    def _make_provider(self) -> Any:
        from emily_chat.models.providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key="test-key-123")

    @pytest.mark.asyncio
    async def test_thinking_chunks_emitted(self) -> None:
        """Thinking deltas produce StreamChunk(type='thinking')."""
        provider = self._make_provider()
        stream = _build_fake_stream(
            thinking_chunks=["Let me think...", " Step 1."],
            text_chunks=["Hello!"],
        )
        self._mock_client.messages.stream.return_value = stream

        settings = GenerationSettings(thinking_budget=8000)
        chunks = [
            c async for c in provider.stream(
                "claude-sonnet-4-5-20260101", [], "system", settings
            )
        ]

        thinking = [c for c in chunks if c.type == "thinking"]
        assert len(thinking) == 2
        assert thinking[0].content == "Let me think..."
        assert thinking[1].content == " Step 1."

    @pytest.mark.asyncio
    async def test_text_chunks_emitted(self) -> None:
        """Text deltas produce StreamChunk(type='text')."""
        provider = self._make_provider()
        stream = _build_fake_stream(text_chunks=["Hello", " world!"])
        self._mock_client.messages.stream.return_value = stream

        settings = GenerationSettings(thinking_budget=0)
        chunks = [
            c async for c in provider.stream(
                "claude-sonnet-4-5-20260101", [], "system", settings
            )
        ]

        text = [c for c in chunks if c.type == "text"]
        assert len(text) == 2
        assert text[0].content == "Hello"
        assert text[1].content == " world!"

    @pytest.mark.asyncio
    async def test_usage_chunk_emitted(self) -> None:
        """A usage chunk with token counts is emitted after the stream."""
        provider = self._make_provider()
        stream = _build_fake_stream(
            text_chunks=["Hi"],
            input_tokens=200,
            output_tokens=80,
        )
        self._mock_client.messages.stream.return_value = stream

        settings = GenerationSettings(thinking_budget=0)
        chunks = [
            c async for c in provider.stream(
                "claude-sonnet-4-5-20260101", [], "system", settings
            )
        ]

        usage = [c for c in chunks if c.type == "usage"]
        assert len(usage) == 1
        assert usage[0].usage["input_tokens"] == 200
        assert usage[0].usage["output_tokens"] == 80

    @pytest.mark.asyncio
    async def test_stop_chunk_emitted(self) -> None:
        """A stop chunk is the final item in every stream."""
        provider = self._make_provider()
        stream = _build_fake_stream(text_chunks=["Done."])
        self._mock_client.messages.stream.return_value = stream

        settings = GenerationSettings(thinking_budget=0)
        chunks = [
            c async for c in provider.stream(
                "claude-sonnet-4-5-20260101", [], "system", settings
            )
        ]

        assert chunks[-1].type == "stop"

    @pytest.mark.asyncio
    async def test_chunk_order_thinking_then_text(self) -> None:
        """Thinking chunks come before text chunks in the stream."""
        provider = self._make_provider()
        stream = _build_fake_stream(
            thinking_chunks=["think1", "think2"],
            text_chunks=["text1", "text2"],
        )
        self._mock_client.messages.stream.return_value = stream

        settings = GenerationSettings(thinking_budget=8000)
        chunks = [
            c async for c in provider.stream(
                "claude-sonnet-4-5-20260101", [], "system", settings
            )
        ]

        types = [c.type for c in chunks]
        think_end = max(i for i, t in enumerate(types) if t == "thinking")
        text_start = min(i for i, t in enumerate(types) if t == "text")
        assert think_end < text_start

    @pytest.mark.asyncio
    async def test_no_api_key_raises(self) -> None:
        """Instantiating without an API key and calling stream raises ValueError."""
        from emily_chat.models.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="")
        settings = GenerationSettings()
        with pytest.raises(ValueError, match="No Anthropic API key"):
            async for _ in provider.stream("model", [], "sys", settings):
                pass


# ---------------------------------------------------------------------------
# Streaming engine tests
# ---------------------------------------------------------------------------


class TestStreamingEngine:
    """Tests for the unified StreamingEngine."""

    @pytest.fixture(autouse=True)
    def _patch_provider(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        """Patch the Anthropic provider so the streaming engine can be tested."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-for-streaming-engine")
        mock_module = MagicMock()
        mock_client = MagicMock()
        mock_module.AsyncAnthropic.return_value = mock_client
        self._mock_client = mock_client
        with patch.dict("sys.modules", {"anthropic": mock_module}):
            # Clear the provider cache so each test gets a fresh one
            from emily_chat.models import streaming_engine
            streaming_engine._PROVIDERS.clear()
            yield
            streaming_engine._PROVIDERS.clear()

    @pytest.mark.asyncio
    async def test_persona_filter_applied_to_text(self) -> None:
        """Text chunks pass through the persona filter; thinking chunks do not."""
        from emily_chat.models.streaming_engine import StreamingEngine

        stream = _build_fake_stream(
            thinking_chunks=["I'm Claude, thinking..."],
            text_chunks=["I'm Claude, the assistant"],
        )
        self._mock_client.messages.stream.return_value = stream

        spec = get_model("claude-sonnet-4-5")
        assert spec is not None

        def fake_filter(text: str) -> str:
            return text.replace("Claude", "Emily")

        engine = StreamingEngine()
        settings = GenerationSettings(thinking_budget=8000)
        chunks = [
            c async for c in engine.stream(
                spec, [], "system", settings, persona_filter=fake_filter
            )
        ]

        thinking = [c for c in chunks if c.type == "thinking"]
        assert any("Claude" in c.content for c in thinking), (
            "Thinking chunks must NOT be filtered"
        )

        text = [c for c in chunks if c.type == "text"]
        assert all("Claude" not in c.content for c in text), (
            "Text chunks must be filtered"
        )
        assert any("Emily" in c.content for c in text)

    @pytest.mark.asyncio
    async def test_usage_includes_timing(self) -> None:
        """Usage chunk includes latency_ms, first_token_ms, and cost_usd."""
        from emily_chat.models.streaming_engine import StreamingEngine

        stream = _build_fake_stream(text_chunks=["Hi"], input_tokens=100, output_tokens=50)
        self._mock_client.messages.stream.return_value = stream

        spec = get_model("claude-sonnet-4-5")
        assert spec is not None

        engine = StreamingEngine()
        settings = GenerationSettings(thinking_budget=0)
        chunks = [
            c async for c in engine.stream(spec, [], "system", settings)
        ]

        usage = [c for c in chunks if c.type == "usage"]
        assert len(usage) == 1
        assert "latency_ms" in usage[0].usage
        assert "first_token_ms" in usage[0].usage
        assert "cost_usd" in usage[0].usage
        assert usage[0].usage["cost_usd"] >= 0

    @pytest.mark.asyncio
    async def test_interrupt_stops_stream(self) -> None:
        """Setting the interrupt event stops generation early."""
        from emily_chat.models.streaming_engine import StreamingEngine

        stream = _build_fake_stream(text_chunks=["a", "b", "c", "d", "e"])
        self._mock_client.messages.stream.return_value = stream

        spec = get_model("claude-sonnet-4-5")
        assert spec is not None

        interrupt = asyncio.Event()

        engine = StreamingEngine()
        settings = GenerationSettings(thinking_budget=0)
        result: list[StreamChunk] = []
        count = 0
        async for c in engine.stream(
            spec, [], "system", settings, interrupt=interrupt
        ):
            result.append(c)
            count += 1
            if count >= 2:
                interrupt.set()

        assert result[-1].type == "stop"
        assert len([c for c in result if c.type == "text"]) <= 3
