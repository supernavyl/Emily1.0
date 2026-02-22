"""Tests for the Mistral provider.

Uses ``respx`` to mock httpx requests — no real API calls are made.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from emily_chat.models.providers.mistral import MistralProvider
from emily_chat.models.registry import EMILY_MODEL_REGISTRY, get_models_for_provider
from emily_chat.models.streaming_engine import ChunkType, GenerationSettings, StreamChunk

_LARGE_SPEC = EMILY_MODEL_REGISTRY["mistral-large-3"]
_CODESTRAL_SPEC = EMILY_MODEL_REGISTRY["codestral-2"]
_SMALL_SPEC = EMILY_MODEL_REGISTRY["mistral-small-3"]
_MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODELS_URL = "https://api.mistral.ai/v1/models"


def _sse(payload: str) -> str:
    return f"data: {payload}\n\n"


def _text_chunk(content: str) -> str:
    return _sse(json.dumps({
        "choices": [{"delta": {"content": content}, "finish_reason": None}],
    }))


def _usage_chunk(prompt: int = 55, completion: int = 35) -> str:
    return _sse(json.dumps({
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }))


def _done_line() -> str:
    return "data: [DONE]\n\n"


def _finish_chunk() -> str:
    return _sse(json.dumps({
        "choices": [{"delta": {}, "finish_reason": "stop"}],
    }))


def _full_stream(text: str = "Mistral responds") -> str:
    parts = [_text_chunk(w + " ") for w in text.split()]
    parts += [_finish_chunk(), _usage_chunk(), _done_line()]
    return "".join(parts)


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------


class TestMistralRegistry:
    """Verify Mistral models are registered."""

    def test_models_present(self) -> None:
        mist = get_models_for_provider("mistral")
        assert "mistral-large-3" in mist
        assert "codestral-2" in mist
        assert "mistral-small-3" in mist

    def test_large_spec(self) -> None:
        assert _LARGE_SPEC.provider == "mistral"
        assert _LARGE_SPEC.vision is True
        assert _LARGE_SPEC.model_id == "mistral-large-latest"

    def test_codestral_context(self) -> None:
        assert _CODESTRAL_SPEC.context == 256_000

    def test_small_open_weights(self) -> None:
        assert _SMALL_SPEC.open_weights is True
        assert _SMALL_SPEC.license == "Apache-2.0"


# ------------------------------------------------------------------
# Streaming
# ------------------------------------------------------------------


class TestMistralStreaming:
    """Standard text streaming for Mistral models."""

    @pytest.mark.asyncio
    async def test_text_stream(self) -> None:
        with respx.mock:
            respx.post(_MISTRAL_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_full_stream("Bonjour monde"))
            )
            provider = MistralProvider(api_key="mist-test")
            texts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hello"}],
                "You are Emily.",
                GenerationSettings(),
                _LARGE_SPEC,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            assert "Bonjour" in "".join(texts)
            await provider.close()

    @pytest.mark.asyncio
    async def test_codestral_request(self) -> None:
        with respx.mock:
            route = respx.post(_MISTRAL_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_full_stream("code"))
            )
            provider = MistralProvider(api_key="mist-test")

            async for _ in provider.stream(
                [{"role": "user", "content": "write python"}],
                "sys",
                GenerationSettings(temperature=0.1),
                _CODESTRAL_SPEC,
            ):
                pass

            body = json.loads(route.calls.last.request.content)
            assert body["model"] == "codestral-latest"
            assert body["temperature"] == 0.1
            await provider.close()

    @pytest.mark.asyncio
    async def test_small_model_stream(self) -> None:
        with respx.mock:
            respx.post(_MISTRAL_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_full_stream("fast"))
            )
            provider = MistralProvider(api_key="mist-test")
            texts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "quick"}],
                "sys",
                GenerationSettings(),
                _SMALL_SPEC,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            assert "fast" in "".join(texts)
            await provider.close()


# ------------------------------------------------------------------
# Errors & validation
# ------------------------------------------------------------------


class TestMistralErrors:
    """Error handling."""

    @pytest.mark.asyncio
    async def test_api_error(self) -> None:
        with respx.mock:
            respx.post(_MISTRAL_CHAT_URL).mock(
                return_value=httpx.Response(401, text="Unauthorized")
            )
            provider = MistralProvider(api_key="mist-bad")
            chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "sys",
                GenerationSettings(),
                _LARGE_SPEC,
            ):
                chunks.append(chunk)

            assert chunks[0].type == ChunkType.ERROR
            assert "401" in chunks[0].content
            await provider.close()


class TestMistralKeyValidation:
    """Key validation."""

    @pytest.mark.asyncio
    async def test_valid_key(self) -> None:
        with respx.mock:
            respx.get(_MISTRAL_MODELS_URL).mock(
                return_value=httpx.Response(200, json={"data": []})
            )
            provider = MistralProvider(api_key="mist-test")
            assert await provider.validate_key("mist-test") is True
            await provider.close()

    @pytest.mark.asyncio
    async def test_invalid_key(self) -> None:
        with respx.mock:
            respx.get(_MISTRAL_MODELS_URL).mock(
                return_value=httpx.Response(403, json={"error": "forbidden"})
            )
            provider = MistralProvider(api_key="mist-bad")
            assert await provider.validate_key("mist-bad") is False
            await provider.close()


class TestMistralCapabilities:
    """Capability flags."""

    def test_supports_vision(self) -> None:
        provider = MistralProvider(api_key="mist-test")
        assert provider.supports_vision() is True

    def test_no_think_tags(self) -> None:
        provider = MistralProvider(api_key="mist-test")
        assert provider._uses_think_tags("mistral-large-latest") is False
