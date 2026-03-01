"""Tests for the Ollama provider.

Uses ``respx`` to mock httpx requests — no real API calls are made.
Covers: JSON-line streaming (not SSE), auto-discovery via ``/api/tags``,
``<think>`` tag extraction for local DeepSeek R1 / Qwen3, connectivity
checks, error handling, and the local spec factory.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from emily_chat.models.providers.ollama import OllamaProvider
from emily_chat.models.registry import (
    EMILY_MODEL_REGISTRY,
    get_models_for_provider,
    register_dynamic_model,
)
from emily_chat.models.streaming_engine import ChunkType, GenerationSettings, StreamChunk

_LOCAL_SPEC = EMILY_MODEL_REGISTRY["emily-ollama"]
_OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
_OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"


@pytest.fixture
async def provider():
    """Create an OllamaProvider and ensure it is closed after the test."""
    p = OllamaProvider()
    yield p
    await p.close()


# ------------------------------------------------------------------
# JSON-line helpers (Ollama does NOT use SSE)
# ------------------------------------------------------------------


def _json_line(content: str, done: bool = False, **kwargs: int) -> str:
    """Build a single Ollama JSON-line response."""
    obj: dict = {"message": {"content": content}, "done": done}
    obj.update(kwargs)
    return json.dumps(obj) + "\n"


def _plain_stream(text: str = "Hello from Ollama") -> str:
    """Build a complete JSON-line stream for plain text."""
    lines: list[str] = []
    for word in text.split():
        lines.append(_json_line(word + " "))
    lines.append(_json_line("", done=True, eval_count=30, prompt_eval_count=15))
    return "".join(lines)


def _think_stream(
    thinking: str = "Let me reason",
    answer: str = "The result",
) -> str:
    """Build a JSON-line stream with <think> tags in content."""
    full = f"<think>{thinking}</think>{answer}"
    lines = [_json_line(ch) for ch in full]
    lines.append(_json_line("", done=True, eval_count=50, prompt_eval_count=20))
    return "".join(lines)


def _discovery_response(models: list[str] | None = None) -> dict:
    """Build a mock /api/tags response."""
    if models is None:
        models = ["llama3.3:70b", "qwen3:72b", "deepseek-r1:32b"]
    return {
        "models": [
            {
                "name": name,
                "size": 40_000_000_000,
                "modified_at": "2025-12-01T00:00:00Z",
            }
            for name in models
        ]
    }


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------


class TestOllamaRegistry:
    """Verify Emily's local fleet models are registered."""

    def test_emily_fast_present(self) -> None:
        """Emily's default local brain should exist in the registry."""
        ollama = get_models_for_provider("ollama")
        assert "emily-ollama" in ollama

    def test_emily_fleet_present(self) -> None:
        """All Emily fleet models should be registered."""
        ollama = get_models_for_provider("ollama")
        assert "emily-ollama" in ollama
        assert "emily-vision" in ollama

    def test_ollama_spec(self) -> None:
        """Emily-ollama spec should have zero cost and correct provider."""
        assert _LOCAL_SPEC.provider == "ollama"
        assert _LOCAL_SPEC.input_usd == 0.0
        assert _LOCAL_SPEC.output_usd == 0.0

    def test_register_dynamic_model(self) -> None:
        """Dynamic registration should add a model to the registry."""
        spec = OllamaProvider.create_local_spec("test-model:7b")
        key = "ollama-test-model:7b"
        register_dynamic_model(key, spec)
        try:
            assert key in EMILY_MODEL_REGISTRY
        finally:
            EMILY_MODEL_REGISTRY.pop(key, None)


# ------------------------------------------------------------------
# JSON-line streaming
# ------------------------------------------------------------------


class TestOllamaStreaming:
    """Ollama streams newline-delimited JSON, not SSE."""

    @pytest.mark.asyncio
    async def test_text_stream(self) -> None:
        """Text tokens should be yielded from JSON-line responses."""
        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream("Hello world"))
            )
            provider = OllamaProvider()
            settings = GenerationSettings(temperature=0.7)
            texts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "You are Emily.",
                settings,
                _LOCAL_SPEC,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            combined = "".join(texts)
            assert "Hello" in combined
            assert "world" in combined
            await provider.close()

    @pytest.mark.asyncio
    async def test_usage_emitted(self) -> None:
        """A USAGE chunk should be emitted from the done=true line."""
        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream())
            )
            provider = OllamaProvider()
            usage_chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(),
                _LOCAL_SPEC,
            ):
                if chunk.type == ChunkType.USAGE:
                    usage_chunks.append(chunk)

            assert len(usage_chunks) == 1
            assert usage_chunks[0].metadata["completion_tokens"] == 30
            assert usage_chunks[0].metadata["prompt_tokens"] == 15
            await provider.close()

    @pytest.mark.asyncio
    async def test_stop_emitted(self) -> None:
        """A STOP chunk should follow the USAGE chunk."""
        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream())
            )
            provider = OllamaProvider()
            types: list[ChunkType] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(),
                _LOCAL_SPEC,
            ):
                types.append(chunk.type)

            assert types[-1] == ChunkType.STOP
            assert types[-2] == ChunkType.USAGE
            await provider.close()

    @pytest.mark.asyncio
    async def test_request_body_format(self) -> None:
        """The request body should use Ollama's format, not OpenAI's."""
        with respx.mock:
            route = respx.post(_OLLAMA_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream())
            )
            provider = OllamaProvider()
            settings = GenerationSettings(temperature=0.3, max_tokens=100)

            async for _ in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                settings,
                _LOCAL_SPEC,
            ):
                pass

            body = json.loads(route.calls.last.request.content)
            assert body["model"] == _LOCAL_SPEC.model_id
            assert body["stream"] is True
            assert body["options"]["temperature"] == 0.3
            assert body["options"]["num_predict"] == 100
            assert "stream_options" not in body
            await provider.close()


# ------------------------------------------------------------------
# Think-tag streaming (local DeepSeek R1, Qwen3)
# ------------------------------------------------------------------


class TestOllamaThinkTags:
    """Local models with <think> tag support."""

    @pytest.mark.asyncio
    async def test_deepseek_r1_thinking(self) -> None:
        """DeepSeek R1 reasoning should be separated from content."""
        r1_spec = OllamaProvider.create_local_spec("deepseek-r1:32b")
        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(
                return_value=httpx.Response(
                    200,
                    text=_think_stream("Step 1 Step 2", "Final answer"),
                )
            )
            provider = OllamaProvider()
            thinking: list[str] = []
            text: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "solve"}],
                "sys",
                GenerationSettings(),
                r1_spec,
            ):
                if chunk.type == ChunkType.THINKING:
                    thinking.append(chunk.content)
                elif chunk.type == ChunkType.TEXT:
                    text.append(chunk.content)

            assert "Step 1" in "".join(thinking)
            assert "Final answer" in "".join(text)
            await provider.close()

    @pytest.mark.asyncio
    async def test_qwen3_thinking(self) -> None:
        """Qwen3 reasoning should be separated from content."""
        qwen_spec = OllamaProvider.create_local_spec("qwen3:72b")
        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(
                return_value=httpx.Response(
                    200,
                    text=_think_stream("Qwen reasoning", "Qwen result"),
                )
            )
            provider = OllamaProvider()
            thinking: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "think"}],
                "sys",
                GenerationSettings(),
                qwen_spec,
            ):
                if chunk.type == ChunkType.THINKING:
                    thinking.append(chunk.content)

            assert "Qwen reasoning" in "".join(thinking)
            await provider.close()

    def test_think_tag_detection_r1(self) -> None:
        """deepseek-r1 model names should trigger think-tag extraction."""
        assert OllamaProvider._uses_think_tags("deepseek-r1:32b") is True

    def test_think_tag_detection_qwen3(self) -> None:
        """qwen3 model names should trigger think-tag extraction."""
        assert OllamaProvider._uses_think_tags("qwen3:72b") is True

    def test_think_tag_detection_qwq(self) -> None:
        """qwq model names should trigger think-tag extraction."""
        assert OllamaProvider._uses_think_tags("qwq:32b") is True

    def test_plain_model_no_think_tags(self) -> None:
        """Llama models should not trigger think-tag extraction."""
        assert OllamaProvider._uses_think_tags("llama3.3:70b") is False


# ------------------------------------------------------------------
# Auto-discovery
# ------------------------------------------------------------------


class TestOllamaDiscovery:
    """Model discovery via GET /api/tags."""

    @pytest.mark.asyncio
    async def test_discover_models(self) -> None:
        """Should return locally installed model info."""
        with respx.mock:
            respx.get(_OLLAMA_TAGS_URL).mock(
                return_value=httpx.Response(200, json=_discovery_response())
            )
            provider = OllamaProvider()
            models = await provider.discover_models()

            assert len(models) == 3
            names = [m["name"] for m in models]
            assert "llama3.3:70b" in names
            assert "qwen3:72b" in names
            assert "deepseek-r1:32b" in names
            await provider.close()

    @pytest.mark.asyncio
    async def test_discover_empty(self) -> None:
        """Should return empty list when no models installed."""
        with respx.mock:
            respx.get(_OLLAMA_TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
            provider = OllamaProvider()
            models = await provider.discover_models()
            assert models == []
            await provider.close()

    @pytest.mark.asyncio
    async def test_discover_unreachable(self) -> None:
        """Should return empty list when Ollama is not running."""
        with respx.mock:
            respx.get(_OLLAMA_TAGS_URL).mock(side_effect=httpx.ConnectError("refused"))
            provider = OllamaProvider()
            models = await provider.discover_models()
            assert models == []
            await provider.close()


# ------------------------------------------------------------------
# Connectivity / key validation
# ------------------------------------------------------------------


class TestOllamaConnectivity:
    """Ollama uses no auth — validate_key just checks connectivity."""

    @pytest.mark.asyncio
    async def test_reachable(self) -> None:
        """Should return True when Ollama is running."""
        with respx.mock:
            respx.get(_OLLAMA_TAGS_URL).mock(
                return_value=httpx.Response(200, json=_discovery_response())
            )
            provider = OllamaProvider()
            assert await provider.validate_key("") is True
            await provider.close()

    @pytest.mark.asyncio
    async def test_unreachable(self) -> None:
        """Should return False when Ollama is not running."""
        with respx.mock:
            respx.get(_OLLAMA_TAGS_URL).mock(side_effect=httpx.ConnectError("refused"))
            provider = OllamaProvider()
            assert await provider.validate_key("") is False
            await provider.close()


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------


class TestOllamaErrors:
    """Error conditions yield ERROR chunks."""

    @pytest.mark.asyncio
    async def test_api_error(self) -> None:
        """Non-200 responses should yield an ERROR chunk."""
        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(
                return_value=httpx.Response(500, text="Internal error")
            )
            provider = OllamaProvider()
            chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "sys",
                GenerationSettings(),
                _LOCAL_SPEC,
            ):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert chunks[0].type == ChunkType.ERROR
            assert "500" in chunks[0].content
            await provider.close()

    @pytest.mark.asyncio
    async def test_connect_error(self) -> None:
        """Connection failure should yield a helpful ERROR chunk."""
        with respx.mock:
            respx.post(_OLLAMA_CHAT_URL).mock(side_effect=httpx.ConnectError("Connection refused"))
            provider = OllamaProvider()
            chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "sys",
                GenerationSettings(),
                _LOCAL_SPEC,
            ):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert chunks[0].type == ChunkType.ERROR
            assert "Cannot connect" in chunks[0].content
            assert "ollama serve" in chunks[0].content
            await provider.close()


# ------------------------------------------------------------------
# Local spec factory
# ------------------------------------------------------------------


class TestOllamaLocalSpec:
    """Dynamic ModelSpec creation for discovered models."""

    def test_create_local_spec(self) -> None:
        """Factory should produce a valid ModelSpec."""
        spec = OllamaProvider.create_local_spec("qwen3:72b")
        assert spec.provider == "ollama"
        assert spec.model_id == "qwen3:72b"
        assert spec.input_usd == 0.0
        assert spec.output_usd == 0.0
        assert "qwen3:72b" in spec.display

    def test_create_local_spec_thinking(self) -> None:
        """Thinking models should have the thinking flag set."""
        spec = OllamaProvider.create_local_spec("deepseek-r1:32b")
        assert spec.thinking is True

    def test_create_local_spec_no_thinking(self) -> None:
        """Non-thinking models should not have the thinking flag."""
        spec = OllamaProvider.create_local_spec("llama3.3:70b")
        assert spec.thinking is False

    def test_create_local_spec_no_colon(self) -> None:
        """Model names without a tag should still work."""
        spec = OllamaProvider.create_local_spec("some-model")
        assert spec.model_id == "some-model"
        assert "some-model" in spec.display
