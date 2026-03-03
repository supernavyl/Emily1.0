"""Tests for the xAI (Grok) provider.

Uses ``respx`` to mock httpx requests — no real API calls are made.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from emily_chat.models.providers.xai import XAIProvider
from emily_chat.models.registry import EMILY_MODEL_REGISTRY, get_models_for_provider
from emily_chat.models.streaming_engine import ChunkType, GenerationSettings, StreamChunk

_GROK_SPEC = EMILY_MODEL_REGISTRY["grok-4-1"]
_XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"
_XAI_MODELS_URL = "https://api.x.ai/v1/models"


def _sse(payload: str) -> str:
    return f"data: {payload}\n\n"


def _text_chunk(content: str) -> str:
    return _sse(
        json.dumps(
            {
                "choices": [{"delta": {"content": content}, "finish_reason": None}],
            }
        )
    )


def _usage_chunk(prompt: int = 50, completion: int = 20) -> str:
    return _sse(
        json.dumps(
            {
                "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
            }
        )
    )


def _done_line() -> str:
    return "data: [DONE]\n\n"


def _finish_chunk() -> str:
    return _sse(
        json.dumps(
            {
                "choices": [{"delta": {}, "finish_reason": "stop"}],
            }
        )
    )


def _full_stream(text: str = "Grok says hello") -> str:
    parts = [_text_chunk(w + " ") for w in text.split()]
    parts += [_finish_chunk(), _usage_chunk(), _done_line()]
    return "".join(parts)


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------


class TestXAIRegistry:
    """Verify xAI models are registered."""

    def test_grok_present(self) -> None:
        xai = get_models_for_provider("xai")
        assert "grok-4-1" in xai

    def test_grok_spec(self) -> None:
        assert _GROK_SPEC.provider == "xai"
        assert _GROK_SPEC.model_id == "grok-4.1"
        assert _GROK_SPEC.vision is True
        assert _GROK_SPEC.context == 256_000


# ------------------------------------------------------------------
# Streaming
# ------------------------------------------------------------------


class TestGrokStreaming:
    """Standard text streaming for Grok."""

    @pytest.mark.asyncio
    async def test_text_stream(self) -> None:
        with respx.mock:
            respx.post(_XAI_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_full_stream("Creative output"))
            )
            provider = XAIProvider(api_key="xai-test")
            texts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "write a joke"}],
                "You are Emily.",
                GenerationSettings(temperature=0.8),
                _GROK_SPEC,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            assert "Creative" in "".join(texts)
            await provider.close()

    @pytest.mark.asyncio
    async def test_request_body(self) -> None:
        with respx.mock:
            route = respx.post(_XAI_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_full_stream())
            )
            provider = XAIProvider(api_key="xai-test")

            async for _ in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(temperature=0.9),
                _GROK_SPEC,
            ):
                pass

            body = json.loads(route.calls.last.request.content)
            assert body["model"] == "grok-4.1"
            assert body["temperature"] == 0.9
            assert body["stream"] is True
            await provider.close()

    @pytest.mark.asyncio
    async def test_usage_chunk(self) -> None:
        with respx.mock:
            respx.post(_XAI_CHAT_URL).mock(return_value=httpx.Response(200, text=_full_stream()))
            provider = XAIProvider(api_key="xai-test")
            usage_meta = None

            async for chunk in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(),
                _GROK_SPEC,
            ):
                if chunk.type == ChunkType.USAGE:
                    usage_meta = chunk.metadata

            assert usage_meta is not None
            assert usage_meta["prompt_tokens"] == 50
            await provider.close()


# ------------------------------------------------------------------
# Errors & validation
# ------------------------------------------------------------------


class TestXAIErrors:
    """Error handling."""

    @pytest.mark.asyncio
    async def test_api_error(self) -> None:
        with respx.mock:
            respx.post(_XAI_CHAT_URL).mock(return_value=httpx.Response(500, text="Internal Error"))
            provider = XAIProvider(api_key="xai-test")
            chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "sys",
                GenerationSettings(),
                _GROK_SPEC,
            ):
                chunks.append(chunk)

            assert chunks[0].type == ChunkType.ERROR
            assert "500" in chunks[0].content
            await provider.close()


class TestXAIKeyValidation:
    """Key validation."""

    @pytest.mark.asyncio
    async def test_valid_key(self) -> None:
        with respx.mock:
            respx.get(_XAI_MODELS_URL).mock(return_value=httpx.Response(200, json={"data": []}))
            provider = XAIProvider(api_key="xai-test")
            assert await provider.validate_key("xai-test") is True
            await provider.close()

    @pytest.mark.asyncio
    async def test_invalid_key(self) -> None:
        with respx.mock:
            respx.get(_XAI_MODELS_URL).mock(
                return_value=httpx.Response(401, json={"error": "nope"})
            )
            provider = XAIProvider(api_key="xai-bad")
            assert await provider.validate_key("xai-bad") is False
            await provider.close()


class TestXAICapabilities:
    """Capability flags."""

    def test_supports_vision(self) -> None:
        provider = XAIProvider(api_key="xai-test")
        assert provider.supports_vision() is True

    def test_no_think_tags(self) -> None:
        provider = XAIProvider(api_key="xai-test")
        assert provider._uses_think_tags("grok-4.1") is False
