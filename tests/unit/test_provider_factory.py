"""Tests for the provider factory and streaming engine async generator.

Covers provider resolution, caching, missing-key errors, Ollama
always-available semantics, and the ``stream_chunks`` async generator
on :class:`EmilyStreamingEngine`.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import httpx
import pytest
import respx

from emily_chat.models.provider_factory import (
    ProviderUnavailableError,
    _cache,  # pyright: ignore[reportPrivateUsage]
    close_all,
    get_provider,
)
from emily_chat.models.providers.ollama import OllamaProvider
from emily_chat.models.providers.openai import OpenAIProvider
from emily_chat.models.providers.tabbyapi import TabbyAPIProvider
from emily_chat.models.registry import EMILY_MODEL_REGISTRY, ModelSpec
from emily_chat.models.streaming_engine import (
    ChunkType,
    EmilyStreamingEngine,
    GenerationSettings,
    StreamChunk,
)

_LOCAL_SPEC = ModelSpec(
    display="Emily — Test Fast",
    provider="tabbyapi",
    model_id="Qwen2.5-14B-Instruct-abliterated",
    context=131_072,
    thinking=True,
)
_OLLAMA_SPEC = ModelSpec(
    display="Emily — Test Vision",
    provider="ollama",
    model_id="minicpm-v:latest",
    context=8_192,
    vision=True,
)
_OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"


def _json_line(content: str, done: bool = False, **kwargs: int) -> str:
    """Build a single Ollama JSON-line response."""
    obj: dict[str, object] = {"message": {"content": content}, "done": done}
    obj.update(kwargs)
    return json.dumps(obj) + "\n"


def _plain_stream(text: str = "Hello from Emily") -> str:
    """Build a complete JSON-line stream for plain text."""
    lines: list[str] = []
    for word in text.split():
        lines.append(_json_line(word + " "))
    lines.append(_json_line("", done=True, eval_count=20, prompt_eval_count=10))
    return "".join(lines)


@pytest.fixture(autouse=True)
async def _clear_cache():  # pyright: ignore[reportUnusedFunction]
    """Ensure the provider cache is empty and providers are closed."""
    _cache.clear()
    yield
    await close_all()


# ------------------------------------------------------------------
# Provider factory: get_provider
# ------------------------------------------------------------------


class TestGetProvider:
    """Provider resolution and caching."""

    def test_ollama_no_key_required(self) -> None:
        """Ollama should always be available without an API key (vision tier)."""
        provider = get_provider(_OLLAMA_SPEC)
        assert isinstance(provider, OllamaProvider)

    def test_tabbyapi_no_key_required(self) -> None:
        """TabbyAPI should always be available without an API key."""
        provider = get_provider(_LOCAL_SPEC)
        assert isinstance(provider, TabbyAPIProvider)

    def test_ollama_cached(self) -> None:
        """Repeat calls should return the same instance."""
        p1 = get_provider(_LOCAL_SPEC)
        p2 = get_provider(_LOCAL_SPEC)
        assert p1 is p2

    def test_missing_key_raises(self) -> None:
        """Requesting a cloud provider without API key should raise."""
        spec = EMILY_MODEL_REGISTRY.get("claude-sonnet-4-6")
        if spec is None:
            pytest.skip("claude-sonnet-4-6 not in registry")
        assert spec is not None
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False),
            pytest.raises(ProviderUnavailableError, match="ANTHROPIC_API_KEY"),
        ):
            get_provider(spec)

    def test_openai_with_key(self) -> None:
        """OpenAI provider should be created when key is set."""
        openai_spec = EMILY_MODEL_REGISTRY.get("gpt-5")
        if openai_spec is None:
            pytest.skip("gpt-5 not in registry")
        assert openai_spec is not None
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
            provider = get_provider(openai_spec)
            assert isinstance(provider, OpenAIProvider)

    def test_unknown_provider_raises(self) -> None:
        """An unknown provider name should raise."""
        fake_spec = ModelSpec(
            display="Fake",
            provider="nonexistent",
            model_id="fake-1",
            input_usd=0.0,
            output_usd=0.0,
        )
        with pytest.raises(ProviderUnavailableError, match="Unknown provider"):
            get_provider(fake_spec)


class TestCloseAll:
    """Provider cleanup."""

    @pytest.mark.asyncio
    async def test_close_all_clears_cache(self) -> None:
        """close_all should close providers and clear the cache."""
        get_provider(_LOCAL_SPEC)
        assert len(_cache) == 1
        await close_all()
        assert len(_cache) == 0


# ------------------------------------------------------------------
# Streaming engine: stream_chunks
# ------------------------------------------------------------------


class TestStreamChunks:
    """The async-generator wrapper on EmilyStreamingEngine."""

    @pytest.mark.asyncio
    async def test_text_passthrough(self) -> None:
        """Text chunks should be yielded with persona filter applied."""
        from emily_chat.emily.persona import EmilyPersonaEngine

        persona = EmilyPersonaEngine()
        engine = EmilyStreamingEngine(persona)

        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream("Hello world"))
            )
            provider = OllamaProvider()
            settings = GenerationSettings(temperature=0.5)

            texts: list[str] = []
            chunk_types: list[ChunkType] = []

            async for chunk in engine.stream_chunks(
                provider,
                _LOCAL_SPEC,
                [{"role": "user", "content": "hi"}],
                "You are Emily.",
                settings,
            ):
                chunk_types.append(chunk.type)
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            combined = "".join(texts)
            assert "Hello" in combined
            assert "world" in combined
            assert ChunkType.STOP in chunk_types
            assert ChunkType.USAGE in chunk_types
            await provider.close()

    @pytest.mark.asyncio
    async def test_usage_includes_cost(self) -> None:
        """The final USAGE chunk should include cost and timing info."""
        from emily_chat.emily.persona import EmilyPersonaEngine

        persona = EmilyPersonaEngine()
        engine = EmilyStreamingEngine(persona)

        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream())
            )
            provider = OllamaProvider()
            settings = GenerationSettings()

            usage_chunks: list[StreamChunk] = []
            async for chunk in engine.stream_chunks(
                provider,
                _LOCAL_SPEC,
                [{"role": "user", "content": "hi"}],
                "sys",
                settings,
            ):
                if chunk.type == ChunkType.USAGE:
                    usage_chunks.append(chunk)

            # Provider emits one USAGE, engine emits a second with cost/timing
            assert len(usage_chunks) >= 1
            final = usage_chunks[-1]
            assert "cost_usd" in final.metadata
            assert "latency_ms" in final.metadata
            # Ollama is free
            assert final.metadata["cost_usd"] == 0.0
            await provider.close()

    @pytest.mark.asyncio
    async def test_error_chunk_on_failure(self) -> None:
        """Connection errors should yield an ERROR chunk."""
        from emily_chat.emily.persona import EmilyPersonaEngine

        persona = EmilyPersonaEngine()
        engine = EmilyStreamingEngine(persona)

        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(side_effect=httpx.ConnectError("refused"))
            provider = OllamaProvider()
            settings = GenerationSettings()

            chunks: list[StreamChunk] = []
            async for chunk in engine.stream_chunks(
                provider,
                _LOCAL_SPEC,
                [{"role": "user", "content": "hi"}],
                "sys",
                settings,
            ):
                chunks.append(chunk)

            error_chunks = [c for c in chunks if c.type == ChunkType.ERROR]
            assert len(error_chunks) >= 1
            assert "Cannot connect" in error_chunks[0].content
            await provider.close()

    @pytest.mark.asyncio
    async def test_identity_filter_applied(self) -> None:
        """Text containing 'I'm Claude' in a single chunk should be filtered."""
        from emily_chat.emily.persona import EmilyPersonaEngine

        persona = EmilyPersonaEngine()
        engine = EmilyStreamingEngine(persona)

        # Send the leak phrase as a single token so the regex can match
        lines = [
            _json_line("I'm Claude and I help"),
            _json_line("", done=True, eval_count=5, prompt_eval_count=3),
        ]
        stream_data = "".join(lines)

        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(return_value=httpx.Response(200, text=stream_data))
            provider = OllamaProvider()
            settings = GenerationSettings()

            texts: list[str] = []
            async for chunk in engine.stream_chunks(
                provider,
                _LOCAL_SPEC,
                [{"role": "user", "content": "who are you?"}],
                "You are Emily.",
                settings,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            combined = "".join(texts)
            assert "Claude" not in combined
            assert "Emily" in combined
            await provider.close()

    @pytest.mark.asyncio
    async def test_interrupt_stops_generation(self) -> None:
        """Setting the interrupt event should stop chunk yielding."""
        from emily_chat.emily.persona import EmilyPersonaEngine

        persona = EmilyPersonaEngine()
        engine = EmilyStreamingEngine(persona)

        long_text = " ".join(f"word{i}" for i in range(50))
        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream(long_text))
            )
            provider = OllamaProvider()
            settings = GenerationSettings()

            count = 0
            async for _chunk in engine.stream_chunks(
                provider,
                _LOCAL_SPEC,
                [{"role": "user", "content": "test"}],
                "sys",
                settings,
            ):
                count += 1
                if count >= 3:
                    engine.interrupt()

            # Should have stopped early (well under the 50+ chunks)
            assert count < 50
            await provider.close()
