"""Tests for the OpenAI provider and supporting infrastructure.

Uses ``respx`` to mock httpx requests — no real API calls are made.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from emily_chat.emily.persona import EmilyPersonaEngine
from emily_chat.models.cost_tracker import estimate_cost, format_cost
from emily_chat.models.providers.openai import OpenAIProvider, _is_reasoning_model
from emily_chat.models.registry import (
    EMILY_MODEL_REGISTRY,
    ModelSpec,
    get_model,
    get_models_for_provider,
)
from emily_chat.models.streaming_engine import (
    ChunkType,
    EmilyStreamingEngine,
    GenerationSettings,
    StreamChunk,
    UsageStats,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_GPT5_SPEC = EMILY_MODEL_REGISTRY["gpt-5"]
_O3_SPEC = EMILY_MODEL_REGISTRY["o3"]
_O4_MINI_SPEC = EMILY_MODEL_REGISTRY["o4-mini"]


def _sse(payload: str) -> str:
    """Wrap a JSON payload as an SSE data line."""
    return f"data: {payload}\n\n"


def _text_chunk(content: str, idx: int = 0) -> str:
    """Build an SSE line for a text delta."""
    return _sse(
        json.dumps(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "choices": [
                    {"index": idx, "delta": {"content": content}, "finish_reason": None}
                ],
            }
        )
    )


def _reasoning_chunk(content: str, idx: int = 0) -> str:
    """Build an SSE line for a reasoning_content delta (o-series)."""
    return _sse(
        json.dumps(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "choices": [
                    {
                        "index": idx,
                        "delta": {"reasoning_content": content},
                        "finish_reason": None,
                    }
                ],
            }
        )
    )


def _finish_chunk(reason: str = "stop") -> str:
    """Build an SSE line for a finish_reason delta."""
    return _sse(
        json.dumps(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "choices": [
                    {"index": 0, "delta": {}, "finish_reason": reason}
                ],
            }
        )
    )


def _usage_chunk(
    prompt: int = 100,
    completion: int = 50,
    reasoning: int = 0,
) -> str:
    """Build an SSE line carrying the usage summary."""
    usage: dict = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
    }
    if reasoning:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning}
    return _sse(
        json.dumps(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "choices": [],
                "usage": usage,
            }
        )
    )


def _done_line() -> str:
    return "data: [DONE]\n\n"


def _full_gpt5_stream(text: str = "Hello from Emily") -> str:
    """Compose a complete SSE stream for a GPT-5 text response."""
    parts = [_text_chunk(word + " ") for word in text.split()]
    parts.append(_finish_chunk())
    parts.append(_usage_chunk(prompt=120, completion=len(text.split())))
    parts.append(_done_line())
    return "".join(parts)


def _full_o3_stream(
    thinking: str = "Let me reason about this",
    answer: str = "The answer is 42",
) -> str:
    """Compose a complete SSE stream for an o3 reasoning response."""
    parts: list[str] = []
    for word in thinking.split():
        parts.append(_reasoning_chunk(word + " "))
    for word in answer.split():
        parts.append(_text_chunk(word + " "))
    parts.append(_finish_chunk())
    parts.append(
        _usage_chunk(
            prompt=80,
            completion=len(answer.split()),
            reasoning=len(thinking.split()),
        )
    )
    parts.append(_done_line())
    return "".join(parts)


# ------------------------------------------------------------------
# _is_reasoning_model
# ------------------------------------------------------------------


class TestIsReasoningModel:
    """Tests for the o-series detection helper."""

    def test_o3_detected(self) -> None:
        assert _is_reasoning_model("o3") is True

    def test_o4_mini_detected(self) -> None:
        assert _is_reasoning_model("o4-mini") is True

    def test_o1_detected(self) -> None:
        assert _is_reasoning_model("o1-preview") is True

    def test_gpt5_not_reasoning(self) -> None:
        assert _is_reasoning_model("gpt-5") is False

    def test_gpt4o_not_reasoning(self) -> None:
        assert _is_reasoning_model("gpt-4o") is False


# ------------------------------------------------------------------
# SSE parsing (unit-level)
# ------------------------------------------------------------------


class TestSSEParsing:
    """Tests for OpenAIProvider._parse_sse_line."""

    def test_text_delta(self) -> None:
        line = f'data: {json.dumps({"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]})}'
        chunk = OpenAIProvider._parse_sse_line(line, "gpt-5")
        assert chunk is not None
        assert chunk.type == ChunkType.TEXT
        assert chunk.content == "hi"

    def test_reasoning_delta(self) -> None:
        line = f'data: {json.dumps({"choices": [{"delta": {"reasoning_content": "hmm"}, "finish_reason": None}]})}'
        chunk = OpenAIProvider._parse_sse_line(line, "o3")
        assert chunk is not None
        assert chunk.type == ChunkType.THINKING
        assert chunk.content == "hmm"

    def test_done_sentinel(self) -> None:
        chunk = OpenAIProvider._parse_sse_line("data: [DONE]", "gpt-5")
        assert chunk is not None
        assert chunk.type == ChunkType.STOP

    def test_usage_chunk(self) -> None:
        usage_data = {
            "usage": {
                "prompt_tokens": 42,
                "completion_tokens": 10,
                "completion_tokens_details": {"reasoning_tokens": 5},
            }
        }
        line = f"data: {json.dumps(usage_data)}"
        chunk = OpenAIProvider._parse_sse_line(line, "o3")
        assert chunk is not None
        assert chunk.type == ChunkType.USAGE
        assert chunk.metadata["prompt_tokens"] == 42
        assert chunk.metadata["reasoning_tokens"] == 5

    def test_empty_line_ignored(self) -> None:
        assert OpenAIProvider._parse_sse_line("", "gpt-5") is None

    def test_comment_line_ignored(self) -> None:
        assert OpenAIProvider._parse_sse_line(": keep-alive", "gpt-5") is None

    def test_malformed_json_ignored(self) -> None:
        assert OpenAIProvider._parse_sse_line("data: {bad json", "gpt-5") is None

    def test_finish_reason_only(self) -> None:
        line = f'data: {json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]})}'
        chunk = OpenAIProvider._parse_sse_line(line, "gpt-5")
        assert chunk is None


# ------------------------------------------------------------------
# GPT-5 streaming (integration with respx)
# ------------------------------------------------------------------


class TestGPT5Streaming:
    """Full streaming through the provider with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_text_stream(self) -> None:
        stream_body = _full_gpt5_stream("Hello world")

        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, text=stream_body)
            )

            provider = OpenAIProvider(api_key="sk-test")
            settings = GenerationSettings(temperature=0.5)
            texts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "You are Emily.",
                settings,
                _GPT5_SPEC,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            combined = "".join(texts).strip()
            assert "Hello" in combined
            assert "world" in combined

            await provider.close()

    @pytest.mark.asyncio
    async def test_request_body_has_temperature(self) -> None:
        """GPT-5 requests must include temperature, not reasoning_effort."""
        stream_body = _full_gpt5_stream("ok")

        with respx.mock:
            route = respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, text=stream_body)
            )

            provider = OpenAIProvider(api_key="sk-test")
            settings = GenerationSettings(temperature=0.7)

            async for _ in provider.stream(
                [{"role": "user", "content": "test"}],
                "You are Emily.",
                settings,
                _GPT5_SPEC,
            ):
                pass

            request = route.calls.last.request
            body = json.loads(request.content)
            assert "temperature" in body
            assert body["temperature"] == 0.7
            assert "reasoning_effort" not in body

            await provider.close()

    @pytest.mark.asyncio
    async def test_api_error_yields_error_chunk(self) -> None:
        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(401, text="Unauthorized")
            )

            provider = OpenAIProvider(api_key="sk-bad")
            settings = GenerationSettings()
            chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "sys",
                settings,
                _GPT5_SPEC,
            ):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert chunks[0].type == ChunkType.ERROR
            assert "401" in chunks[0].content

            await provider.close()


# ------------------------------------------------------------------
# o3 / o4-mini reasoning streaming
# ------------------------------------------------------------------


class TestReasoningStreaming:
    """Tests for o-series reasoning_content separation."""

    @pytest.mark.asyncio
    async def test_thinking_and_text_separated(self) -> None:
        stream_body = _full_o3_stream(
            thinking="Step 1 Step 2",
            answer="Result here",
        )

        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, text=stream_body)
            )

            provider = OpenAIProvider(api_key="sk-test")
            settings = GenerationSettings(reasoning_effort="high")
            thinking_parts: list[str] = []
            text_parts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "prove P=NP"}],
                "You are Emily.",
                settings,
                _O3_SPEC,
            ):
                if chunk.type == ChunkType.THINKING:
                    thinking_parts.append(chunk.content)
                elif chunk.type == ChunkType.TEXT:
                    text_parts.append(chunk.content)

            thinking = "".join(thinking_parts).strip()
            text = "".join(text_parts).strip()

            assert "Step 1" in thinking
            assert "Step 2" in thinking
            assert "Result" in text
            assert "here" in text

            await provider.close()

    @pytest.mark.asyncio
    async def test_reasoning_effort_in_body(self) -> None:
        """o3 requests must include reasoning_effort, not temperature."""
        stream_body = _full_o3_stream()

        with respx.mock:
            route = respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, text=stream_body)
            )

            provider = OpenAIProvider(api_key="sk-test")
            settings = GenerationSettings(reasoning_effort="high")

            async for _ in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                settings,
                _O3_SPEC,
            ):
                pass

            body = json.loads(route.calls.last.request.content)
            assert body["reasoning_effort"] == "high"
            assert "temperature" not in body

            await provider.close()

    @pytest.mark.asyncio
    async def test_usage_includes_reasoning_tokens(self) -> None:
        stream_body = _full_o3_stream()

        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, text=stream_body)
            )

            provider = OpenAIProvider(api_key="sk-test")
            settings = GenerationSettings()
            usage_meta: dict | None = None

            async for chunk in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                settings,
                _O3_SPEC,
            ):
                if chunk.type == ChunkType.USAGE:
                    usage_meta = chunk.metadata

            assert usage_meta is not None
            assert usage_meta["reasoning_tokens"] > 0
            assert usage_meta["prompt_tokens"] > 0

            await provider.close()

    @pytest.mark.asyncio
    async def test_o4_mini_reasoning_effort_default(self) -> None:
        """Invalid reasoning_effort falls back to 'medium'."""
        stream_body = _full_o3_stream()

        with respx.mock:
            route = respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, text=stream_body)
            )

            provider = OpenAIProvider(api_key="sk-test")
            settings = GenerationSettings(reasoning_effort="invalid_value")

            async for _ in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                settings,
                _O4_MINI_SPEC,
            ):
                pass

            body = json.loads(route.calls.last.request.content)
            assert body["reasoning_effort"] == "medium"

            await provider.close()


# ------------------------------------------------------------------
# Vision
# ------------------------------------------------------------------


class TestVisionMessages:
    """Tests for the vision message builder."""

    def test_build_vision_message(self) -> None:
        msg = OpenAIProvider.build_vision_message(
            "What is this?",
            ["https://example.com/cat.jpg"],
            detail="high",
        )
        assert msg["role"] == "user"
        assert isinstance(msg["content"], list)
        assert msg["content"][0]["type"] == "text"
        assert msg["content"][0]["text"] == "What is this?"
        assert msg["content"][1]["type"] == "image_url"
        assert msg["content"][1]["image_url"]["url"] == "https://example.com/cat.jpg"
        assert msg["content"][1]["image_url"]["detail"] == "high"

    def test_multiple_images(self) -> None:
        msg = OpenAIProvider.build_vision_message(
            "Compare these",
            ["https://example.com/a.jpg", "data:image/png;base64,abc123"],
        )
        assert len(msg["content"]) == 3  # 1 text + 2 images


# ------------------------------------------------------------------
# Key validation
# ------------------------------------------------------------------


class TestKeyValidation:
    """Tests for validate_key."""

    @pytest.mark.asyncio
    async def test_valid_key(self) -> None:
        with respx.mock:
            respx.get("https://api.openai.com/v1/models").mock(
                return_value=httpx.Response(200, json={"data": []})
            )
            provider = OpenAIProvider(api_key="sk-test")
            assert await provider.validate_key("sk-test") is True
            await provider.close()

    @pytest.mark.asyncio
    async def test_invalid_key(self) -> None:
        with respx.mock:
            respx.get("https://api.openai.com/v1/models").mock(
                return_value=httpx.Response(401, json={"error": "invalid"})
            )
            provider = OpenAIProvider(api_key="sk-bad")
            assert await provider.validate_key("sk-bad") is False
            await provider.close()


# ------------------------------------------------------------------
# Cost tracking
# ------------------------------------------------------------------


class TestCostTracker:
    """Tests for cost estimation and formatting."""

    def test_gpt5_cost(self) -> None:
        cost = estimate_cost(_GPT5_SPEC, tokens_in=1000, tokens_out=500)
        expected = (1000 / 1e6) * 8.0 + (500 / 1e6) * 32.0
        assert abs(cost - expected) < 1e-9

    def test_o3_cost_includes_thinking(self) -> None:
        cost = estimate_cost(
            _O3_SPEC, tokens_in=100, tokens_out=50, tokens_thinking=200
        )
        expected = (100 / 1e6) * 10.0 + ((50 + 200) / 1e6) * 40.0
        assert abs(cost - expected) < 1e-9

    def test_format_cost_normal(self) -> None:
        assert format_cost(0.0124) == "$0.0124"

    def test_format_cost_tiny(self) -> None:
        assert format_cost(0.00001) == "< $0.0001"


# ------------------------------------------------------------------
# Model registry
# ------------------------------------------------------------------


class TestModelRegistry:
    """Tests for the registry helpers."""

    def test_openai_models_present(self) -> None:
        openai = get_models_for_provider("openai")
        assert "gpt-5" in openai
        assert "o3" in openai
        assert "o4-mini" in openai
        assert "gpt-4o" in openai

    def test_get_model(self) -> None:
        spec = get_model("gpt-5")
        assert spec is not None
        assert spec.provider == "openai"
        assert spec.model_id == "gpt-5"

    def test_get_model_missing(self) -> None:
        assert get_model("nonexistent-model") is None

    def test_reasoning_model_property(self) -> None:
        assert _O3_SPEC.is_reasoning_model is True
        assert _O4_MINI_SPEC.is_reasoning_model is True
        assert _GPT5_SPEC.is_reasoning_model is False


# ------------------------------------------------------------------
# Streaming engine (identity filter integration)
# ------------------------------------------------------------------


class TestStreamingEngine:
    """Tests that the streaming engine applies identity filter correctly."""

    @pytest.mark.asyncio
    async def test_identity_filter_applied_to_text(self) -> None:
        """Text chunks containing 'I'm ChatGPT' should be replaced."""
        # Send as multi-token chunks (realistic: APIs often send several
        # tokens per SSE event, not single words).
        stream_body = (
            _text_chunk("I'm ChatGPT ")
            + _text_chunk("and I help")
            + _finish_chunk()
            + _usage_chunk(prompt=50, completion=6)
            + _done_line()
        )

        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, text=stream_body)
            )

            provider = OpenAIProvider(api_key="sk-test")
            persona = EmilyPersonaEngine()
            engine = EmilyStreamingEngine(persona)

            texts: list[str] = []
            done_stats: list[UsageStats] = []

            await engine.stream(
                provider,
                _GPT5_SPEC,
                [{"role": "user", "content": "who are you"}],
                "You are Emily.",
                GenerationSettings(),
                on_text=texts.append,
                on_done=done_stats.append,
            )

            combined = "".join(texts)
            assert "ChatGPT" not in combined
            assert "Emily" in combined
            assert len(done_stats) == 1
            assert done_stats[0].provider == "openai"

            await provider.close()

    @pytest.mark.asyncio
    async def test_thinking_chunks_not_filtered(self) -> None:
        """Thinking chunks must pass through WITHOUT identity filtering."""
        stream_body = _full_o3_stream(
            thinking="As Claude I think about this",
            answer="Here is the result",
        )

        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, text=stream_body)
            )

            provider = OpenAIProvider(api_key="sk-test")
            persona = EmilyPersonaEngine()
            engine = EmilyStreamingEngine(persona)

            thinking_parts: list[str] = []

            await engine.stream(
                provider,
                _O3_SPEC,
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(),
                on_thinking=thinking_parts.append,
            )

            thinking = "".join(thinking_parts)
            # Thinking must NOT be filtered — "Claude" stays
            assert "Claude" in thinking

            await provider.close()

    @pytest.mark.asyncio
    async def test_interrupt_stops_stream(self) -> None:
        """Calling interrupt() should stop generation."""
        long_stream = "".join(_text_chunk(f"word{i} ") for i in range(100))
        long_stream += _finish_chunk() + _usage_chunk() + _done_line()

        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, text=long_stream)
            )

            provider = OpenAIProvider(api_key="sk-test")
            persona = EmilyPersonaEngine()
            engine = EmilyStreamingEngine(persona)

            count = 0

            def on_text(t: str) -> None:
                nonlocal count
                count += 1
                if count >= 3:
                    engine.interrupt()

            done_called = []
            await engine.stream(
                provider,
                _GPT5_SPEC,
                [{"role": "user", "content": "long"}],
                "sys",
                GenerationSettings(),
                on_text=on_text,
                on_done=done_called.append,
            )

            assert count < 100
            assert len(done_called) == 1

            await provider.close()

    @pytest.mark.asyncio
    async def test_error_callback(self) -> None:
        """API errors should route to on_error."""
        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(500, text="Internal Server Error")
            )

            provider = OpenAIProvider(api_key="sk-test")
            persona = EmilyPersonaEngine()
            engine = EmilyStreamingEngine(persona)

            errors: list[Exception] = []

            await engine.stream(
                provider,
                _GPT5_SPEC,
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(),
                on_error=errors.append,
            )

            assert len(errors) == 1
            assert "500" in str(errors[0])

            await provider.close()
