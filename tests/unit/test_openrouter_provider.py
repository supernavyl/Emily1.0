"""Tests for the OpenRouter provider.

Uses ``respx`` to mock httpx requests — no real API calls are made.
Covers: standard SSE text streaming, ``<think>`` tag extraction for
Kimi K2 / GLM 4.7, extra attribution headers, custom spec factory,
error handling, and key validation.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from emily_chat.models.providers.openrouter import OpenRouterProvider
from emily_chat.models.registry import EMILY_MODEL_REGISTRY, get_models_for_provider
from emily_chat.models.streaming_engine import ChunkType, GenerationSettings, StreamChunk

_KIMI_SPEC = EMILY_MODEL_REGISTRY["kimi-k2-thinking"]
_GLM_SPEC = EMILY_MODEL_REGISTRY["glm-4-7-thinking"]
_OR_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
_OR_MODELS_URL = "https://openrouter.ai/api/v1/models"


# ------------------------------------------------------------------
# SSE helpers
# ------------------------------------------------------------------

def _sse(payload: str) -> str:
    """Wrap a JSON payload as an SSE data line."""
    return f"data: {payload}\n\n"


def _text_chunk(content: str) -> str:
    """Build an SSE text delta chunk."""
    return _sse(json.dumps({
        "choices": [{"delta": {"content": content}, "finish_reason": None}],
    }))


def _usage_chunk(prompt: int = 50, completion: int = 20) -> str:
    """Build an SSE usage chunk."""
    return _sse(json.dumps({
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }))


def _done_line() -> str:
    """Build the SSE [DONE] sentinel."""
    return "data: [DONE]\n\n"


def _finish_chunk() -> str:
    """Build an SSE finish_reason chunk."""
    return _sse(json.dumps({
        "choices": [{"delta": {}, "finish_reason": "stop"}],
    }))


def _plain_stream(text: str = "Hello from OpenRouter") -> str:
    """Build a complete SSE stream for plain text."""
    parts = [_text_chunk(w + " ") for w in text.split()]
    parts += [_finish_chunk(), _usage_chunk(), _done_line()]
    return "".join(parts)


def _think_stream(
    thinking: str = "Let me reason",
    answer: str = "The result",
) -> str:
    """Build an SSE stream where reasoning is inside <think> tags."""
    full = f"<think>{thinking}</think>{answer}"
    parts = [_text_chunk(ch) for ch in full]
    parts += [_finish_chunk(), _usage_chunk(), _done_line()]
    return "".join(parts)


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------


class TestOpenRouterRegistry:
    """Verify OpenRouter models are registered correctly."""

    def test_openrouter_models_present(self) -> None:
        """Both static entries should be in the registry."""
        or_models = get_models_for_provider("openrouter")
        assert "kimi-k2-thinking" in or_models
        assert "glm-4-7-thinking" in or_models

    def test_kimi_spec(self) -> None:
        """Kimi K2 should have correct provider, thinking, and context."""
        assert _KIMI_SPEC.provider == "openrouter"
        assert _KIMI_SPEC.thinking is True
        assert _KIMI_SPEC.context == 200_000

    def test_glm_spec(self) -> None:
        """GLM 4.7 should have correct provider and thinking flag."""
        assert _GLM_SPEC.provider == "openrouter"
        assert _GLM_SPEC.thinking is True
        assert _GLM_SPEC.context == 128_000


# ------------------------------------------------------------------
# Plain text streaming
# ------------------------------------------------------------------


class TestOpenRouterStreaming:
    """Standard SSE text streaming via OpenRouter."""

    @pytest.mark.asyncio
    async def test_text_stream(self) -> None:
        """Text chunks should be yielded for a simple response."""
        with respx.mock:
            respx.post(_OR_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream("Hello world"))
            )
            provider = OpenRouterProvider(api_key="sk-or-test")
            settings = GenerationSettings(temperature=0.5)
            texts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "You are Emily.",
                settings,
                _KIMI_SPEC,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            combined = "".join(texts)
            assert "Hello" in combined
            assert "world" in combined
            await provider.close()

    @pytest.mark.asyncio
    async def test_usage_chunk_emitted(self) -> None:
        """A USAGE chunk should be yielded with token counts."""
        with respx.mock:
            respx.post(_OR_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream())
            )
            provider = OpenRouterProvider(api_key="sk-or-test")
            usage_chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(),
                _GLM_SPEC,
            ):
                if chunk.type == ChunkType.USAGE:
                    usage_chunks.append(chunk)

            assert len(usage_chunks) == 1
            assert usage_chunks[0].metadata["prompt_tokens"] == 50
            assert usage_chunks[0].metadata["completion_tokens"] == 20
            await provider.close()


# ------------------------------------------------------------------
# Think-tag streaming (Kimi K2, GLM 4.7)
# ------------------------------------------------------------------


class TestOpenRouterThinkTags:
    """Models routed through OpenRouter that use <think> tags."""

    @pytest.mark.asyncio
    async def test_kimi_thinking_separated(self) -> None:
        """Kimi K2 reasoning should be split into THINKING chunks."""
        with respx.mock:
            respx.post(_OR_CHAT_URL).mock(
                return_value=httpx.Response(
                    200,
                    text=_think_stream("Kimi reasoning here", "Final answer"),
                )
            )
            provider = OpenRouterProvider(api_key="sk-or-test")
            thinking: list[str] = []
            text: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "solve"}],
                "sys",
                GenerationSettings(),
                _KIMI_SPEC,
            ):
                if chunk.type == ChunkType.THINKING:
                    thinking.append(chunk.content)
                elif chunk.type == ChunkType.TEXT:
                    text.append(chunk.content)

            assert "Kimi reasoning" in "".join(thinking)
            assert "Final answer" in "".join(text)
            await provider.close()

    @pytest.mark.asyncio
    async def test_glm_thinking_separated(self) -> None:
        """GLM 4.7 reasoning should be split into THINKING chunks."""
        with respx.mock:
            respx.post(_OR_CHAT_URL).mock(
                return_value=httpx.Response(
                    200,
                    text=_think_stream("GLM reasoning", "GLM result"),
                )
            )
            provider = OpenRouterProvider(api_key="sk-or-test")
            thinking: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "think"}],
                "sys",
                GenerationSettings(),
                _GLM_SPEC,
            ):
                if chunk.type == ChunkType.THINKING:
                    thinking.append(chunk.content)

            assert "GLM reasoning" in "".join(thinking)
            await provider.close()

    def test_think_tag_detection_kimi(self) -> None:
        """Kimi K2 model ID should trigger think-tag extraction."""
        provider = OpenRouterProvider(api_key="sk-or-test")
        assert provider._uses_think_tags("moonshotai/kimi-k2-thinking") is True

    def test_think_tag_detection_glm(self) -> None:
        """GLM 4.7 model ID should trigger think-tag extraction."""
        provider = OpenRouterProvider(api_key="sk-or-test")
        assert provider._uses_think_tags("z-ai/glm-4.7-thinking") is True

    def test_think_tag_detection_deepseek(self) -> None:
        """DeepSeek R1 via OpenRouter should trigger think-tag extraction."""
        provider = OpenRouterProvider(api_key="sk-or-test")
        assert provider._uses_think_tags("deepseek/deepseek-r1") is True

    def test_plain_model_no_think_tags(self) -> None:
        """A plain model should not trigger think-tag extraction."""
        provider = OpenRouterProvider(api_key="sk-or-test")
        assert provider._uses_think_tags("meta-llama/llama-3.3-70b") is False


# ------------------------------------------------------------------
# Extra headers
# ------------------------------------------------------------------


class TestOpenRouterHeaders:
    """OpenRouter-specific attribution headers."""

    @pytest.mark.asyncio
    async def test_headers_present(self) -> None:
        """Requests should include HTTP-Referer and X-Title headers."""
        with respx.mock:
            route = respx.post(_OR_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream())
            )
            provider = OpenRouterProvider(api_key="sk-or-test")

            async for _ in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(),
                _KIMI_SPEC,
            ):
                pass

            request = route.calls.last.request
            assert request.headers["HTTP-Referer"] == "https://emily-chat.app"
            assert request.headers["X-Title"] == "Emily Chat"
            await provider.close()


# ------------------------------------------------------------------
# Custom spec factory
# ------------------------------------------------------------------


class TestOpenRouterCustomSpec:
    """Dynamic ModelSpec creation for arbitrary model strings."""

    def test_create_custom_spec(self) -> None:
        """Factory should produce a valid ModelSpec."""
        spec = OpenRouterProvider.create_custom_spec("meta-llama/llama-3.3-70b-instruct")
        assert spec.provider == "openrouter"
        assert spec.model_id == "meta-llama/llama-3.3-70b-instruct"
        assert "llama-3.3-70b-instruct" in spec.display

    def test_create_custom_spec_with_display(self) -> None:
        """Factory should accept a custom display name."""
        spec = OpenRouterProvider.create_custom_spec(
            "custom/model", display="My Custom Model"
        )
        assert spec.display == "My Custom Model"

    def test_create_custom_spec_no_slash(self) -> None:
        """Model IDs without a slash should still work."""
        spec = OpenRouterProvider.create_custom_spec("some-model-id")
        assert "some-model-id" in spec.display


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------


class TestOpenRouterErrors:
    """Error conditions yield ERROR chunks."""

    @pytest.mark.asyncio
    async def test_api_error(self) -> None:
        """Non-200 responses should yield an ERROR chunk."""
        with respx.mock:
            respx.post(_OR_CHAT_URL).mock(
                return_value=httpx.Response(429, text="Rate limited")
            )
            provider = OpenRouterProvider(api_key="sk-or-test")
            chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "sys",
                GenerationSettings(),
                _KIMI_SPEC,
            ):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert chunks[0].type == ChunkType.ERROR
            assert "429" in chunks[0].content
            await provider.close()


# ------------------------------------------------------------------
# Key validation
# ------------------------------------------------------------------


class TestOpenRouterKeyValidation:
    """Key validation against the models endpoint."""

    @pytest.mark.asyncio
    async def test_valid_key(self) -> None:
        """A 200 response from /models should return True."""
        with respx.mock:
            respx.get(_OR_MODELS_URL).mock(
                return_value=httpx.Response(200, json={"data": []})
            )
            provider = OpenRouterProvider(api_key="sk-or-test")
            assert await provider.validate_key("sk-or-test") is True
            await provider.close()

    @pytest.mark.asyncio
    async def test_invalid_key(self) -> None:
        """A 401 response from /models should return False."""
        with respx.mock:
            respx.get(_OR_MODELS_URL).mock(
                return_value=httpx.Response(401, json={"error": "invalid"})
            )
            provider = OpenRouterProvider(api_key="sk-or-bad")
            assert await provider.validate_key("sk-or-bad") is False
            await provider.close()
