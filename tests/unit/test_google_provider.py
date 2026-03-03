"""Tests for the Google Gemini provider, registry entries, and streaming engine integration.

Uses ``respx`` to mock httpx requests — no real API key is needed.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from emily_chat.emily.persona import EmilyPersonaEngine
from emily_chat.models.cost_tracker import estimate_cost
from emily_chat.models.providers.google import GoogleProvider, _convert_messages, _parse_sse_line
from emily_chat.models.registry import (
    EMILY_MODEL_REGISTRY,
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

_GEMINI_3_PRO_SPEC = EMILY_MODEL_REGISTRY["gemini-3-pro"]
_GEMINI_3_FLASH_SPEC = EMILY_MODEL_REGISTRY["gemini-3-flash"]
_GEMINI_2_5_PRO_SPEC = EMILY_MODEL_REGISTRY["gemini-2-5-pro"]

_GEMINI_3_PRO_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
    "/models/gemini-3-pro-preview:streamGenerateContent"
)
_GEMINI_3_FLASH_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash:streamGenerateContent"
)
_GEMINI_2_5_PRO_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
    "/models/gemini-2.5-pro-preview:streamGenerateContent"
)


def _sse(payload: str) -> str:
    """Wrap a JSON payload as an SSE data line."""
    return f"data: {payload}\n\n"


def _text_event(text: str) -> str:
    """Build an SSE line for a text-only part."""
    return _sse(
        json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": text}],
                            "role": "model",
                        }
                    }
                ],
            }
        )
    )


def _thinking_event(text: str) -> str:
    """Build an SSE line for a thinking/thought part."""
    return _sse(
        json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": text, "thought": True}],
                            "role": "model",
                        }
                    }
                ],
            }
        )
    )


def _usage_event(
    prompt: int = 100,
    candidates: int = 50,
    thoughts: int = 0,
) -> str:
    """Build an SSE line with usage metadata (no candidates)."""
    usage: dict = {
        "promptTokenCount": prompt,
        "candidatesTokenCount": candidates,
        "totalTokenCount": prompt + candidates + thoughts,
    }
    if thoughts:
        usage["thoughtsTokenCount"] = thoughts
    return _sse(json.dumps({"usageMetadata": usage}))


def _full_text_stream(text: str = "Hello from Emily") -> str:
    """Compose a complete SSE stream with text-only parts."""
    parts = [_text_event(word + " ") for word in text.split()]
    parts.append(_usage_event(prompt=120, candidates=len(text.split())))
    return "".join(parts)


def _full_thinking_stream(
    thinking: str = "Let me reason about this",
    answer: str = "The answer is 42",
) -> str:
    """Compose a complete SSE stream with thinking parts then text parts."""
    parts: list[str] = []
    for word in thinking.split():
        parts.append(_thinking_event(word + " "))
    for word in answer.split():
        parts.append(_text_event(word + " "))
    parts.append(
        _usage_event(
            prompt=80,
            candidates=len(answer.split()),
            thoughts=len(thinking.split()),
        )
    )
    return "".join(parts)


# ------------------------------------------------------------------
# Message conversion
# ------------------------------------------------------------------


class TestMessageConversion:
    """Tests for _convert_messages."""

    def test_user_message(self) -> None:
        msgs = [{"role": "user", "content": "hello"}]
        result = _convert_messages(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["parts"] == [{"text": "hello"}]

    def test_assistant_mapped_to_model(self) -> None:
        msgs = [{"role": "assistant", "content": "hi there"}]
        result = _convert_messages(msgs)
        assert result[0]["role"] == "model"

    def test_system_messages_skipped(self) -> None:
        msgs = [
            {"role": "system", "content": "be nice"},
            {"role": "user", "content": "hi"},
        ]
        result = _convert_messages(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_multi_turn(self) -> None:
        msgs = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ]
        result = _convert_messages(msgs)
        assert len(result) == 3
        assert [r["role"] for r in result] == ["user", "model", "user"]


# ------------------------------------------------------------------
# SSE parsing
# ------------------------------------------------------------------


class TestSSEParsing:
    """Tests for _parse_sse_line."""

    def test_text_part(self) -> None:
        line = _text_event("hello").strip()
        usage: dict = {}
        chunks = _parse_sse_line(line, usage)
        assert len(chunks) == 1
        assert chunks[0].type == ChunkType.TEXT
        assert chunks[0].content == "hello"

    def test_thinking_part(self) -> None:
        line = _thinking_event("reasoning...").strip()
        usage: dict = {}
        chunks = _parse_sse_line(line, usage)
        assert len(chunks) == 1
        assert chunks[0].type == ChunkType.THINKING
        assert chunks[0].content == "reasoning..."

    def test_usage_metadata_extracted(self) -> None:
        line = _usage_event(prompt=200, candidates=80, thoughts=50).strip()
        usage: dict = {}
        _parse_sse_line(line, usage)
        assert usage["prompt_tokens"] == 200
        assert usage["completion_tokens"] == 80
        assert usage["reasoning_tokens"] == 50

    def test_usage_without_thoughts(self) -> None:
        line = _usage_event(prompt=100, candidates=40).strip()
        usage: dict = {}
        _parse_sse_line(line, usage)
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 40
        assert "reasoning_tokens" not in usage

    def test_empty_line_ignored(self) -> None:
        usage: dict = {}
        assert _parse_sse_line("", usage) == []

    def test_comment_line_ignored(self) -> None:
        usage: dict = {}
        assert _parse_sse_line(": keep-alive", usage) == []

    def test_malformed_json_ignored(self) -> None:
        usage: dict = {}
        assert _parse_sse_line("data: {bad json", usage) == []

    def test_mixed_parts_in_single_event(self) -> None:
        """A single SSE event with both thinking and text parts."""
        event_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "thought", "thought": True},
                            {"text": "answer"},
                        ],
                        "role": "model",
                    }
                }
            ],
        }
        line = f"data: {json.dumps(event_data)}"
        usage: dict = {}
        chunks = _parse_sse_line(line, usage)
        assert len(chunks) == 2
        assert chunks[0].type == ChunkType.THINKING
        assert chunks[0].content == "thought"
        assert chunks[1].type == ChunkType.TEXT
        assert chunks[1].content == "answer"

    def test_empty_text_part_skipped(self) -> None:
        event_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": ""}],
                        "role": "model",
                    }
                }
            ],
        }
        line = f"data: {json.dumps(event_data)}"
        usage: dict = {}
        chunks = _parse_sse_line(line, usage)
        assert len(chunks) == 0


# ------------------------------------------------------------------
# Model registry
# ------------------------------------------------------------------


class TestGoogleRegistry:
    """Tests for Google model registry entries."""

    def test_three_google_models_present(self) -> None:
        google = get_models_for_provider("google")
        assert len(google) == 3
        assert "gemini-3-pro" in google
        assert "gemini-3-flash" in google
        assert "gemini-2-5-pro" in google

    def test_gemini_3_pro_spec(self) -> None:
        spec = get_model("gemini-3-pro")
        assert spec is not None
        assert spec.provider == "google"
        assert spec.model_id == "gemini-3-pro-preview"
        assert spec.context == 2_000_000
        assert spec.thinking is True
        assert spec.vision is True
        assert spec.video is True
        assert spec.audio is True

    def test_gemini_3_flash_spec(self) -> None:
        spec = get_model("gemini-3-flash")
        assert spec is not None
        assert spec.provider == "google"
        assert spec.model_id == "gemini-3-flash"
        assert spec.context == 1_000_000
        assert spec.thinking is True
        assert spec.vision is True

    def test_gemini_2_5_pro_spec(self) -> None:
        spec = get_model("gemini-2-5-pro")
        assert spec is not None
        assert spec.provider == "google"
        assert spec.model_id == "gemini-2.5-pro-preview"
        assert spec.context == 1_000_000
        assert spec.thinking is True
        assert spec.vision is True

    def test_all_google_models_have_thinking(self) -> None:
        for spec in get_models_for_provider("google").values():
            assert spec.thinking is True

    def test_all_google_models_have_positive_pricing(self) -> None:
        for spec in get_models_for_provider("google").values():
            assert spec.input_usd >= 0
            assert spec.output_usd >= 0

    def test_google_models_not_default(self) -> None:
        for spec in get_models_for_provider("google").values():
            assert spec.default is False


# ------------------------------------------------------------------
# Gemini text streaming (integration with respx)
# ------------------------------------------------------------------


class TestGeminiTextStreaming:
    """Full streaming through the provider with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_text_stream(self) -> None:
        stream_body = _full_text_stream("Hello world")

        with respx.mock:
            respx.post(_GEMINI_3_PRO_URL).mock(return_value=httpx.Response(200, text=stream_body))

            provider = GoogleProvider(api_key="test-key")
            settings = GenerationSettings(temperature=0.5)
            texts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "You are Emily.",
                settings,
                _GEMINI_3_PRO_SPEC,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            combined = "".join(texts).strip()
            assert "Hello" in combined
            assert "world" in combined

            await provider.close()

    @pytest.mark.asyncio
    async def test_stop_chunk_emitted(self) -> None:
        stream_body = _full_text_stream("ok")

        with respx.mock:
            respx.post(_GEMINI_3_FLASH_URL).mock(return_value=httpx.Response(200, text=stream_body))

            provider = GoogleProvider(api_key="test-key")
            settings = GenerationSettings()
            chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                settings,
                _GEMINI_3_FLASH_SPEC,
            ):
                chunks.append(chunk)

            assert chunks[-1].type == ChunkType.STOP

            await provider.close()

    @pytest.mark.asyncio
    async def test_usage_chunk_emitted(self) -> None:
        stream_body = _full_text_stream("response")

        with respx.mock:
            respx.post(_GEMINI_3_PRO_URL).mock(return_value=httpx.Response(200, text=stream_body))

            provider = GoogleProvider(api_key="test-key")
            settings = GenerationSettings()
            usage_chunks = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                settings,
                _GEMINI_3_PRO_SPEC,
            ):
                if chunk.type == ChunkType.USAGE:
                    usage_chunks.append(chunk)

            assert len(usage_chunks) == 1
            assert usage_chunks[0].metadata["prompt_tokens"] > 0

            await provider.close()

    @pytest.mark.asyncio
    async def test_request_body_structure(self) -> None:
        """Verify the request body includes systemInstruction, generationConfig."""
        stream_body = _full_text_stream("ok")

        with respx.mock:
            route = respx.post(_GEMINI_3_PRO_URL).mock(
                return_value=httpx.Response(200, text=stream_body)
            )

            provider = GoogleProvider(api_key="test-key")
            settings = GenerationSettings(temperature=0.7, max_tokens=4096)

            async for _ in provider.stream(
                [{"role": "user", "content": "test"}],
                "Emily system prompt",
                settings,
                _GEMINI_3_PRO_SPEC,
            ):
                pass

            request = route.calls.last.request
            body = json.loads(request.content)

            assert body["systemInstruction"]["parts"][0]["text"] == "Emily system prompt"
            assert body["generationConfig"]["temperature"] == 0.7
            assert body["generationConfig"]["maxOutputTokens"] == 4096
            assert body["contents"][0]["role"] == "user"

            await provider.close()

    @pytest.mark.asyncio
    async def test_api_error_yields_error_chunk(self) -> None:
        with respx.mock:
            respx.post(_GEMINI_3_PRO_URL).mock(return_value=httpx.Response(403, text="Forbidden"))

            provider = GoogleProvider(api_key="bad-key")
            settings = GenerationSettings()
            chunks: list[StreamChunk] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "hi"}],
                "sys",
                settings,
                _GEMINI_3_PRO_SPEC,
            ):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert chunks[0].type == ChunkType.ERROR
            assert "403" in chunks[0].content

            await provider.close()


# ------------------------------------------------------------------
# Thinking / reasoning streaming
# ------------------------------------------------------------------


class TestGeminiThinkingStreaming:
    """Tests for thinking part extraction."""

    @pytest.mark.asyncio
    async def test_thinking_and_text_separated(self) -> None:
        stream_body = _full_thinking_stream(
            thinking="Step 1 Step 2",
            answer="Result here",
        )

        with respx.mock:
            respx.post(_GEMINI_3_PRO_URL).mock(return_value=httpx.Response(200, text=stream_body))

            provider = GoogleProvider(api_key="test-key")
            settings = GenerationSettings(thinking_budget=8000)
            thinking_parts: list[str] = []
            text_parts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "explain quantum mechanics"}],
                "You are Emily.",
                settings,
                _GEMINI_3_PRO_SPEC,
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

            await provider.close()

    @pytest.mark.asyncio
    async def test_thinking_budget_in_request(self) -> None:
        """thinkingConfig should be included when thinking_budget > 0."""
        stream_body = _full_thinking_stream()

        with respx.mock:
            route = respx.post(_GEMINI_3_PRO_URL).mock(
                return_value=httpx.Response(200, text=stream_body)
            )

            provider = GoogleProvider(api_key="test-key")
            settings = GenerationSettings(thinking_budget=16000)

            async for _ in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                settings,
                _GEMINI_3_PRO_SPEC,
            ):
                pass

            body = json.loads(route.calls.last.request.content)
            tc = body["generationConfig"]["thinkingConfig"]
            assert tc["thinkingBudget"] == 16000
            assert tc["includeThoughts"] is True

            await provider.close()

    @pytest.mark.asyncio
    async def test_no_thinking_config_when_budget_zero(self) -> None:
        """thinkingConfig should be absent when thinking_budget is 0."""
        stream_body = _full_text_stream("ok")

        with respx.mock:
            route = respx.post(_GEMINI_3_PRO_URL).mock(
                return_value=httpx.Response(200, text=stream_body)
            )

            provider = GoogleProvider(api_key="test-key")
            settings = GenerationSettings(thinking_budget=0)

            async for _ in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                settings,
                _GEMINI_3_PRO_SPEC,
            ):
                pass

            body = json.loads(route.calls.last.request.content)
            assert "thinkingConfig" not in body["generationConfig"]

            await provider.close()

    @pytest.mark.asyncio
    async def test_usage_includes_thinking_tokens(self) -> None:
        stream_body = _full_thinking_stream()

        with respx.mock:
            respx.post(_GEMINI_3_PRO_URL).mock(return_value=httpx.Response(200, text=stream_body))

            provider = GoogleProvider(api_key="test-key")
            settings = GenerationSettings(thinking_budget=8000)
            usage_meta: dict | None = None

            async for chunk in provider.stream(
                [{"role": "user", "content": "test"}],
                "sys",
                settings,
                _GEMINI_3_PRO_SPEC,
            ):
                if chunk.type == ChunkType.USAGE:
                    usage_meta = chunk.metadata

            assert usage_meta is not None
            assert usage_meta["reasoning_tokens"] > 0
            assert usage_meta["prompt_tokens"] > 0

            await provider.close()


# ------------------------------------------------------------------
# Key validation
# ------------------------------------------------------------------


class TestKeyValidation:
    """Tests for validate_key."""

    @pytest.mark.asyncio
    async def test_valid_key(self) -> None:
        with respx.mock:
            respx.get("https://generativelanguage.googleapis.com/v1beta/models").mock(
                return_value=httpx.Response(200, json={"models": []})
            )

            provider = GoogleProvider(api_key="test-key")
            assert await provider.validate_key("test-key") is True
            await provider.close()

    @pytest.mark.asyncio
    async def test_invalid_key(self) -> None:
        with respx.mock:
            respx.get("https://generativelanguage.googleapis.com/v1beta/models").mock(
                return_value=httpx.Response(401, json={"error": "invalid"})
            )

            provider = GoogleProvider(api_key="bad-key")
            assert await provider.validate_key("bad-key") is False
            await provider.close()


# ------------------------------------------------------------------
# Cost tracking for Google models
# ------------------------------------------------------------------


class TestGoogleCostTracking:
    """Tests for cost estimation with Google pricing."""

    def test_gemini_3_pro_cost(self) -> None:
        cost = estimate_cost(_GEMINI_3_PRO_SPEC, tokens_in=1000, tokens_out=500)
        expected = (1000 / 1e6) * 2.50 + (500 / 1e6) * 15.00
        assert abs(cost - expected) < 1e-9

    def test_gemini_3_flash_cost(self) -> None:
        cost = estimate_cost(_GEMINI_3_FLASH_SPEC, tokens_in=10000, tokens_out=2000)
        expected = (10000 / 1e6) * 0.10 + (2000 / 1e6) * 0.40
        assert abs(cost - expected) < 1e-9

    def test_gemini_cost_with_thinking(self) -> None:
        cost = estimate_cost(
            _GEMINI_3_PRO_SPEC,
            tokens_in=100,
            tokens_out=50,
            tokens_thinking=200,
        )
        expected = (100 / 1e6) * 2.50 + ((50 + 200) / 1e6) * 15.00
        assert abs(cost - expected) < 1e-9


# ------------------------------------------------------------------
# Streaming engine integration (identity filter)
# ------------------------------------------------------------------


class TestStreamingEngineGoogle:
    """Tests that the streaming engine applies the identity filter correctly."""

    @pytest.mark.asyncio
    async def test_identity_filter_applied_to_text(self) -> None:
        """Text chunks containing 'I'm Gemini' should be replaced."""
        stream_body = (
            _text_event("I'm Gemini ")
            + _text_event("and I help")
            + _usage_event(prompt=50, candidates=6)
        )

        with respx.mock:
            respx.post(_GEMINI_3_PRO_URL).mock(return_value=httpx.Response(200, text=stream_body))

            provider = GoogleProvider(api_key="test-key")
            persona = EmilyPersonaEngine()
            engine = EmilyStreamingEngine(persona)

            texts: list[str] = []
            done_stats: list[UsageStats] = []

            await engine.stream(
                provider,
                _GEMINI_3_PRO_SPEC,
                [{"role": "user", "content": "who are you"}],
                "You are Emily.",
                GenerationSettings(),
                on_text=texts.append,
                on_done=done_stats.append,
            )

            combined = "".join(texts)
            assert "Gemini" not in combined
            assert "Emily" in combined
            assert len(done_stats) == 1
            assert done_stats[0].provider == "google"

            await provider.close()

    @pytest.mark.asyncio
    async def test_thinking_chunks_not_filtered(self) -> None:
        """Thinking chunks must pass through WITHOUT identity filtering."""
        stream_body = _full_thinking_stream(
            thinking="As Gemini I consider the options",
            answer="Here is the result",
        )

        with respx.mock:
            respx.post(_GEMINI_3_PRO_URL).mock(return_value=httpx.Response(200, text=stream_body))

            provider = GoogleProvider(api_key="test-key")
            persona = EmilyPersonaEngine()
            engine = EmilyStreamingEngine(persona)

            thinking_parts: list[str] = []

            await engine.stream(
                provider,
                _GEMINI_3_PRO_SPEC,
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(),
                on_thinking=thinking_parts.append,
            )

            thinking = "".join(thinking_parts)
            assert "Gemini" in thinking

            await provider.close()

    @pytest.mark.asyncio
    async def test_interrupt_stops_stream(self) -> None:
        """Calling interrupt() should stop generation."""
        long_stream = "".join(_text_event(f"word{i} ") for i in range(100))
        long_stream += _usage_event()

        with respx.mock:
            respx.post(_GEMINI_3_FLASH_URL).mock(return_value=httpx.Response(200, text=long_stream))

            provider = GoogleProvider(api_key="test-key")
            persona = EmilyPersonaEngine()
            engine = EmilyStreamingEngine(persona)

            count = 0

            def on_text(t: str) -> None:
                nonlocal count
                count += 1
                if count >= 3:
                    engine.interrupt()

            done_called: list = []
            await engine.stream(
                provider,
                _GEMINI_3_FLASH_SPEC,
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
            respx.post(_GEMINI_3_PRO_URL).mock(
                return_value=httpx.Response(500, text="Internal Server Error")
            )

            provider = GoogleProvider(api_key="test-key")
            persona = EmilyPersonaEngine()
            engine = EmilyStreamingEngine(persona)

            errors: list[Exception] = []

            await engine.stream(
                provider,
                _GEMINI_3_PRO_SPEC,
                [{"role": "user", "content": "test"}],
                "sys",
                GenerationSettings(),
                on_error=errors.append,
            )

            assert len(errors) == 1
            assert "500" in str(errors[0])

            await provider.close()


# ------------------------------------------------------------------
# Multi-model (gemini-3-flash and gemini-2-5-pro)
# ------------------------------------------------------------------


class TestGeminiFlashAndTwoFivePro:
    """Ensure flash and 2.5-pro models work through the same provider."""

    @pytest.mark.asyncio
    async def test_flash_streaming(self) -> None:
        stream_body = _full_text_stream("fast answer")

        with respx.mock:
            respx.post(_GEMINI_3_FLASH_URL).mock(return_value=httpx.Response(200, text=stream_body))

            provider = GoogleProvider(api_key="test-key")
            settings = GenerationSettings()
            texts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "quick"}],
                "sys",
                settings,
                _GEMINI_3_FLASH_SPEC,
            ):
                if chunk.type == ChunkType.TEXT:
                    texts.append(chunk.content)

            assert "fast" in "".join(texts)

            await provider.close()

    @pytest.mark.asyncio
    async def test_two_five_pro_streaming(self) -> None:
        stream_body = _full_thinking_stream(
            thinking="deep analysis",
            answer="conclusion",
        )

        with respx.mock:
            respx.post(_GEMINI_2_5_PRO_URL).mock(return_value=httpx.Response(200, text=stream_body))

            provider = GoogleProvider(api_key="test-key")
            settings = GenerationSettings(thinking_budget=8000)
            thinking_parts: list[str] = []
            text_parts: list[str] = []

            async for chunk in provider.stream(
                [{"role": "user", "content": "analyze"}],
                "sys",
                settings,
                _GEMINI_2_5_PRO_SPEC,
            ):
                if chunk.type == ChunkType.THINKING:
                    thinking_parts.append(chunk.content)
                elif chunk.type == ChunkType.TEXT:
                    text_parts.append(chunk.content)

            assert "deep" in "".join(thinking_parts)
            assert "conclusion" in "".join(text_parts)

            await provider.close()
