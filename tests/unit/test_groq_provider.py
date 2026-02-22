"""Tests for the Groq provider.

Uses ``respx`` to mock httpx requests — no real API calls are made.
Covers: plain-text Llama streaming, ``<think>`` tag extraction for
R1-distill and Qwen3 models, error handling, and key validation.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from emily_chat.models.providers.groq import GroqProvider
from emily_chat.models.registry import EMILY_MODEL_REGISTRY, get_models_for_provider
from emily_chat.models.streaming_engine import ChunkType, GenerationSettings, StreamChunk

_LLAMA_SPEC = EMILY_MODEL_REGISTRY["groq-llama-70b"]
_R1_SPEC = EMILY_MODEL_REGISTRY["groq-deepseek-r1"]
_QWEN_SPEC = EMILY_MODEL_REGISTRY["qwen3-72b"]
_SCOUT_SPEC = EMILY_MODEL_REGISTRY["llama-4-scout"]
_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"


# ------------------------------------------------------------------
# SSE helpers
# ------------------------------------------------------------------

def _sse(payload: str) -> str:
    return f"data: {payload}\n\n"


def _text_chunk(content: str) -> str:
    return _sse(json.dumps({
        "choices": [{"delta": {"content": content}, "finish_reason": None}],
    }))


def _usage_chunk(prompt: int = 50, completion: int = 20) -> str:
    return _sse(json.dumps({
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }))


def _done_line() -> str:
    return "data: [DONE]\n\n"


def _finish_chunk() -> str:
    return _sse(json.dumps({
        "choices": [{"delta": {}, "finish_reason": "stop"}],
    }))


def _plain_stream(text: str = "Hello from Groq") -> str:
    parts = [_text_chunk(w + " ") for w in text.split()]
    parts += [_finish_chunk(), _usage_chunk(), _done_line()]
    return "".join(parts)


def _think_stream(
    thinking: str = "Let me reason",
    answer: str = "The result",
) -> str:
    """Build a stream where thinking is inside <think> tags in content."""
    full = f"<think>{thinking}</think>{answer}"
    parts = [_text_chunk(ch) for ch in full]
    parts += [_finish_chunk(), _usage_chunk(), _done_line()]
    return "".join(parts)


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------


class TestGroqRegistry:
    """Verify Groq models are registered correctly."""

    def test_groq_models_present(self) -> None:
        groq = get_models_for_provider("groq")
        assert "groq-llama-70b" in groq
        assert "groq-deepseek-r1" in groq
        assert "qwen3-72b" in groq
        assert "llama-4-scout" in groq

    def test_llama_spec(self) -> None:
        assert _LLAMA_SPEC.provider == "groq"
        assert _LLAMA_SPEC.speed == "blazing"

    def test_r1_thinking_flag(self) -> None:
        assert _R1_SPEC.thinking is True

    def test_scout_context(self) -> None:
        assert _SCOUT_SPEC.context == 10_000_000


# ------------------------------------------------------------------
# Plain text streaming (Llama)
# ------------------------------------------------------------------


class TestLlamaStreaming:
    """Llama models stream plain text with no think tags."""

    @pytest.mark.asyncio
    async def test_text_stream(self) -> None:
        with respx.mock:
            respx.post(_GROQ_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream("Hello world"))
            )
            provider = GroqProvider(api_key="gsk-test")
            settings = GenerationSettings(temperature=0.5)
            texts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "You are Emily.",
                settings,
                _LLAMA_SPEC,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            combined = "".join(texts)
            assert "Hello" in combined
            assert "world" in combined
            await provider.close()

    @pytest.mark.asyncio
    async def test_request_has_temperature(self) -> None:
        with respx.mock:
            route = respx.post(_GROQ_CHAT_URL).mock(
                return_value=httpx.Response(200, text=_plain_stream())
            )
            provider = GroqProvider(api_key="gsk-test")
            settings = GenerationSettings(temperature=0.3)

            async for _ in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                settings,
                _LLAMA_SPEC,
            ):
                pass

            body = json.loads(route.calls.last.request.content)
            assert body["temperature"] == 0.3
            assert body["model"] == "llama-3.3-70b-versatile"
            await provider.close()


# ------------------------------------------------------------------
# Think-tag streaming (R1-distill, Qwen3)
# ------------------------------------------------------------------


class TestThinkTagStreaming:
    """R1-distill and Qwen3 models embed thinking in <think> tags."""

    @pytest.mark.asyncio
    async def test_r1_thinking_separated(self) -> None:
        with respx.mock:
            respx.post(_GROQ_CHAT_URL).mock(
                return_value=httpx.Response(
                    200,
                    text=_think_stream("Step A Step B", "Final answer"),
                )
            )
            provider = GroqProvider(api_key="gsk-test")
            thinking: list[str] = []
            text: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "solve"}],
                "sys",
                GenerationSettings(),
                _R1_SPEC,
            ):
                if chunk.type == ChunkType.THINKING:
                    thinking.append(chunk.content)
                elif chunk.type == ChunkType.TEXT:
                    text.append(chunk.content)

            thinking_combined = "".join(thinking)
            text_combined = "".join(text)
            assert "Step A" in thinking_combined
            assert "Step B" in thinking_combined
            assert "Final answer" in text_combined
            await provider.close()

    @pytest.mark.asyncio
    async def test_qwen3_uses_think_tags(self) -> None:
        with respx.mock:
            respx.post(_GROQ_CHAT_URL).mock(
                return_value=httpx.Response(
                    200,
                    text=_think_stream("Qwen reasoning", "Qwen result"),
                )
            )
            provider = GroqProvider(api_key="gsk-test")
            thinking: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "think"}],
                "sys",
                GenerationSettings(),
                _QWEN_SPEC,
            ):
                if chunk.type == ChunkType.THINKING:
                    thinking.append(chunk.content)

            assert "Qwen reasoning" in "".join(thinking)
            await provider.close()

    def test_llama_does_not_use_think_tags(self) -> None:
        provider = GroqProvider(api_key="gsk-test")
        assert provider._uses_think_tags(_LLAMA_SPEC.model_id) is False

    def test_r1_uses_think_tags(self) -> None:
        provider = GroqProvider(api_key="gsk-test")
        assert provider._uses_think_tags(_R1_SPEC.model_id) is True


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------


class TestGroqErrors:
    """Error conditions yield ERROR chunks."""

    @pytest.mark.asyncio
    async def test_api_error(self) -> None:
        with respx.mock:
            respx.post(_GROQ_CHAT_URL).mock(
                return_value=httpx.Response(429, text="Rate limited")
            )
            provider = GroqProvider(api_key="gsk-test")
            chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "sys",
                GenerationSettings(),
                _LLAMA_SPEC,
            ):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert chunks[0].type == ChunkType.ERROR
            assert "429" in chunks[0].content
            await provider.close()


# ------------------------------------------------------------------
# Key validation
# ------------------------------------------------------------------


class TestGroqKeyValidation:
    """Key validation against the models endpoint."""

    @pytest.mark.asyncio
    async def test_valid_key(self) -> None:
        with respx.mock:
            respx.get(_GROQ_MODELS_URL).mock(
                return_value=httpx.Response(200, json={"data": []})
            )
            provider = GroqProvider(api_key="gsk-test")
            assert await provider.validate_key("gsk-test") is True
            await provider.close()

    @pytest.mark.asyncio
    async def test_invalid_key(self) -> None:
        with respx.mock:
            respx.get(_GROQ_MODELS_URL).mock(
                return_value=httpx.Response(401, json={"error": "invalid"})
            )
            provider = GroqProvider(api_key="gsk-bad")
            assert await provider.validate_key("gsk-bad") is False
            await provider.close()
