"""Tests for the Together AI provider.

Uses ``respx`` to mock httpx requests — no real API calls are made.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from emily_chat.models.providers.together import TogetherProvider
from emily_chat.models.registry import EMILY_MODEL_REGISTRY, get_models_for_provider
from emily_chat.models.streaming_engine import ChunkType, GenerationSettings, StreamChunk

_QWEN_SPEC = EMILY_MODEL_REGISTRY["qwen3-235b"]
_MAVERICK_SPEC = EMILY_MODEL_REGISTRY["llama-4-maverick"]
_TOGETHER_CHAT_URL = "https://api.together.xyz/v1/chat/completions"
_TOGETHER_MODELS_URL = "https://api.together.xyz/v1/models"


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


def _usage_chunk(prompt: int = 60, completion: int = 25) -> str:
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


def _full_stream(text: str = "Together works") -> str:
    parts = [_text_chunk(w + " ") for w in text.split()]
    parts += [_finish_chunk(), _usage_chunk(), _done_line()]
    return "".join(parts)


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------


class TestTogetherRegistry:
    """Verify Together AI models are registered."""

    def test_models_present(self) -> None:
        tog = get_models_for_provider("together")
        assert "qwen3-235b" in tog
        assert "llama-4-maverick" in tog

    def test_qwen_spec(self) -> None:
        assert _QWEN_SPEC.provider == "together"
        assert _QWEN_SPEC.model_id == "Qwen/Qwen3-235B-Instruct"
        assert _QWEN_SPEC.thinking is True

    def test_maverick_vision(self) -> None:
        assert _MAVERICK_SPEC.vision is True


# ------------------------------------------------------------------
# Streaming
# ------------------------------------------------------------------


class TestTogetherStreaming:
    """Standard text streaming."""

    @pytest.mark.asyncio
    async def test_text_stream(self) -> None:
        with respx.mock:
            respx.post(_TOGETHER_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_full_stream("multilingual output"))
            )
            provider = TogetherProvider(api_key="tog-test")
            texts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "translate"}],
                "You are Emily.",
                GenerationSettings(),
                _QWEN_SPEC,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            assert "multilingual" in "".join(texts)
            await provider.close()

    @pytest.mark.asyncio
    async def test_request_body(self) -> None:
        with respx.mock:
            route = respx.post(_TOGETHER_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_full_stream())
            )
            provider = TogetherProvider(api_key="tog-test")

            async for _ in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(temperature=0.7),
                _MAVERICK_SPEC,
            ):
                pass

            body = json.loads(route.calls.last.request.content)
            assert body["model"] == "meta-llama/llama-4-maverick"
            assert body["temperature"] == 0.7
            await provider.close()

    @pytest.mark.asyncio
    async def test_usage_chunk(self) -> None:
        with respx.mock:
            respx.post(_TOGETHER_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_full_stream())
            )
            provider = TogetherProvider(api_key="tog-test")
            usage_meta = None

            async for chunk in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(),
                _QWEN_SPEC,
            ):
                if chunk.type == ChunkType.USAGE:
                    usage_meta = chunk.metadata

            assert usage_meta is not None
            assert usage_meta["prompt_tokens"] == 60
            await provider.close()


# ------------------------------------------------------------------
# Errors & validation
# ------------------------------------------------------------------


class TestTogetherErrors:
    """Error handling."""

    @pytest.mark.asyncio
    async def test_api_error(self) -> None:
        with respx.mock:
            respx.post(_TOGETHER_CHAT_URL).mock(
                return_value=httpx.Response(502, text="Bad Gateway")
            )
            provider = TogetherProvider(api_key="tog-test")
            chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "sys",
                GenerationSettings(),
                _QWEN_SPEC,
            ):
                chunks.append(chunk)

            assert chunks[0].type == ChunkType.ERROR
            assert "502" in chunks[0].content
            await provider.close()


class TestTogetherKeyValidation:
    """Key validation."""

    @pytest.mark.asyncio
    async def test_valid_key(self) -> None:
        with respx.mock:
            respx.get(_TOGETHER_MODELS_URL).mock(return_value=httpx.Response(200, json=[]))
            provider = TogetherProvider(api_key="tog-test")
            assert await provider.validate_key("tog-test") is True
            await provider.close()

    @pytest.mark.asyncio
    async def test_invalid_key(self) -> None:
        with respx.mock:
            respx.get(_TOGETHER_MODELS_URL).mock(
                return_value=httpx.Response(401, json={"error": "bad"})
            )
            provider = TogetherProvider(api_key="tog-bad")
            assert await provider.validate_key("tog-bad") is False
            await provider.close()


class TestTogetherCapabilities:
    """Capability flags."""

    def test_supports_vision(self) -> None:
        provider = TogetherProvider(api_key="tog-test")
        assert provider.supports_vision() is True

    def test_no_think_tags(self) -> None:
        provider = TogetherProvider(api_key="tog-test")
        assert provider._uses_think_tags("meta-llama/llama-4-maverick") is False
