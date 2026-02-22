"""Tests for the DeepSeek provider.

Uses ``respx`` to mock httpx requests — no real API calls are made.
Covers: V3.2 plain streaming, R2 ``<think>`` tag extraction, errors.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from emily_chat.models.providers.deepseek import DeepSeekProvider
from emily_chat.models.registry import EMILY_MODEL_REGISTRY, get_models_for_provider
from emily_chat.models.streaming_engine import ChunkType, GenerationSettings, StreamChunk

_V3_SPEC = EMILY_MODEL_REGISTRY["deepseek-v3-2"]
_R2_SPEC = EMILY_MODEL_REGISTRY["deepseek-r2"]
_DS_CHAT_URL = "https://api.deepseek.com/chat/completions"
_DS_MODELS_URL = "https://api.deepseek.com/models"


def _sse(payload: str) -> str:
    return f"data: {payload}\n\n"


def _text_chunk(content: str) -> str:
    return _sse(json.dumps({
        "choices": [{"delta": {"content": content}, "finish_reason": None}],
    }))


def _usage_chunk(prompt: int = 40, completion: int = 30) -> str:
    return _sse(json.dumps({
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }))


def _done_line() -> str:
    return "data: [DONE]\n\n"


def _finish_chunk() -> str:
    return _sse(json.dumps({
        "choices": [{"delta": {}, "finish_reason": "stop"}],
    }))


def _plain_stream(text: str = "DeepSeek V3 says hi") -> str:
    parts = [_text_chunk(w + " ") for w in text.split()]
    parts += [_finish_chunk(), _usage_chunk(), _done_line()]
    return "".join(parts)


def _think_stream(thinking: str, answer: str) -> str:
    full = f"<think>{thinking}</think>{answer}"
    parts = [_text_chunk(ch) for ch in full]
    parts += [_finish_chunk(), _usage_chunk(), _done_line()]
    return "".join(parts)


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------


class TestDeepSeekRegistry:
    """Verify DeepSeek models are registered."""

    def test_models_present(self) -> None:
        ds = get_models_for_provider("deepseek")
        assert "deepseek-v3-2" in ds
        assert "deepseek-r2" in ds

    def test_v3_spec(self) -> None:
        assert _V3_SPEC.provider == "deepseek"
        assert _V3_SPEC.thinking is False
        assert _V3_SPEC.open_weights is True

    def test_r2_thinking(self) -> None:
        assert _R2_SPEC.thinking is True


# ------------------------------------------------------------------
# V3.2 streaming (plain text)
# ------------------------------------------------------------------


class TestV3Streaming:
    """DeepSeek V3.2 streams plain text."""

    @pytest.mark.asyncio
    async def test_text_stream(self) -> None:
        with respx.mock:
            respx.post(_DS_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream("code result"))
            )
            provider = DeepSeekProvider(api_key="sk-ds-test")
            texts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "write code"}],
                "You are Emily.",
                GenerationSettings(),
                _V3_SPEC,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            assert "code" in "".join(texts)
            await provider.close()


# ------------------------------------------------------------------
# R2 streaming (think tags)
# ------------------------------------------------------------------


class TestR2ThinkingStream:
    """DeepSeek R2 embeds reasoning in <think> tags."""

    @pytest.mark.asyncio
    async def test_thinking_separated(self) -> None:
        with respx.mock:
            respx.post(_DS_CHAT_URL).mock(
                return_value=httpx.Response(
                    200,
                    text=_think_stream("Analyzing the problem", "Solution is X"),
                )
            )
            provider = DeepSeekProvider(api_key="sk-ds-test")
            thinking: list[str] = []
            text: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "solve"}],
                "sys",
                GenerationSettings(),
                _R2_SPEC,
            ):
                if chunk.type == ChunkType.THINKING:
                    thinking.append(chunk.content)
                elif chunk.type == ChunkType.TEXT:
                    text.append(chunk.content)

            assert "Analyzing" in "".join(thinking)
            assert "Solution" in "".join(text)
            await provider.close()

    def test_v3_no_think_tags(self) -> None:
        provider = DeepSeekProvider(api_key="sk-ds-test")
        assert provider._uses_think_tags(_V3_SPEC.model_id) is False

    def test_r2_uses_think_tags(self) -> None:
        provider = DeepSeekProvider(api_key="sk-ds-test")
        assert provider._uses_think_tags(_R2_SPEC.model_id) is True


# ------------------------------------------------------------------
# Errors & validation
# ------------------------------------------------------------------


class TestDeepSeekErrors:
    """Error handling."""

    @pytest.mark.asyncio
    async def test_api_error(self) -> None:
        with respx.mock:
            respx.post(_DS_CHAT_URL).mock(
                return_value=httpx.Response(403, text="Forbidden")
            )
            provider = DeepSeekProvider(api_key="sk-ds-bad")
            chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "sys",
                GenerationSettings(),
                _V3_SPEC,
            ):
                chunks.append(chunk)

            assert chunks[0].type == ChunkType.ERROR
            assert "403" in chunks[0].content
            await provider.close()


class TestDeepSeekKeyValidation:
    """Key validation."""

    @pytest.mark.asyncio
    async def test_valid_key(self) -> None:
        with respx.mock:
            respx.get(_DS_MODELS_URL).mock(
                return_value=httpx.Response(200, json={"data": []})
            )
            provider = DeepSeekProvider(api_key="sk-ds-test")
            assert await provider.validate_key("sk-ds-test") is True
            await provider.close()

    @pytest.mark.asyncio
    async def test_invalid_key(self) -> None:
        with respx.mock:
            respx.get(_DS_MODELS_URL).mock(
                return_value=httpx.Response(401, json={"error": "invalid"})
            )
            provider = DeepSeekProvider(api_key="sk-ds-bad")
            assert await provider.validate_key("sk-ds-bad") is False
            await provider.close()
