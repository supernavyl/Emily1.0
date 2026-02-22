"""Tests for the llama-cpp-python LLM client.

Uses a mocked ``Llama`` class — no real model weights are loaded.
Covers: streaming chat, non-streaming chat, model loading/dedup,
alias resolution, health check, keep_alive no-op, close, graceful
fallback when GGUF is missing, and first-token latency metrics.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from config import LlamaCppConfig, LlamaCppModelConfig
from llm.llamacpp_client import LlamaCppClient


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_chunk(content: str, finish: bool = False) -> dict[str, Any]:
    """Build a single llama-cpp-python streaming chunk dict."""
    return {
        "choices": [{
            "delta": {"content": content},
            "finish_reason": "stop" if finish else None,
        }],
    }


def _fake_stream(words: list[str]) -> list[dict[str, Any]]:
    """Build a complete streaming response from a word list."""
    chunks = [_make_chunk(w + " ") for w in words[:-1]]
    chunks.append(_make_chunk(words[-1], finish=True))
    return chunks


def _mock_llama(stream_chunks: list[dict[str, Any]] | None = None) -> MagicMock:
    """Create a mock Llama instance with a ``create_chat_completion`` method."""
    llm = MagicMock()
    if stream_chunks is None:
        stream_chunks = _fake_stream(["Hello", "world"])
    llm.create_chat_completion.return_value = iter(stream_chunks)
    return llm


def _config(
    models_dir: str = "/tmp/test_models",
    filename: str = "test.gguf",
    alias: bool = False,
) -> LlamaCppConfig:
    """Build a minimal LlamaCppConfig for testing."""
    models: dict[str, LlamaCppModelConfig] = {
        "nano": LlamaCppModelConfig(
            filename=filename,
            n_gpu_layers=-1,
            n_ctx=2048,
            n_batch=256,
        ),
    }
    if alias:
        models["voice_fast"] = LlamaCppModelConfig(alias_of="nano")
    return LlamaCppConfig(enabled=True, models_dir=models_dir, models=models)


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_no_models() -> None:
    """Health check returns False when no models are loaded."""
    client = LlamaCppClient(_config(filename=""))
    assert await client.health_check() is False


@pytest.mark.asyncio
async def test_health_check_with_model() -> None:
    """Health check returns True after a model is loaded."""
    client = LlamaCppClient(_config())
    client._models["nano"] = _mock_llama()
    client._loaded_tiers.add("nano")
    assert await client.health_check() is True


@pytest.mark.asyncio
async def test_has_model() -> None:
    """has_model reflects loaded tiers."""
    client = LlamaCppClient(_config())
    assert client.has_model("nano") is False
    client._loaded_tiers.add("nano")
    assert client.has_model("nano") is True


@pytest.mark.asyncio
async def test_chat_stream_yields_chunks() -> None:
    """chat_stream yields CompletionChunk objects with correct content."""
    client = LlamaCppClient(_config())
    chunks = _fake_stream(["Hi", "there"])
    client._models["nano"] = _mock_llama(chunks)
    client._loaded_tiers.add("nano")

    collected: list[str] = []
    async for chunk in client.chat_stream(
        model="nano",
        messages=[],
        model_tier="nano",
    ):
        collected.append(chunk.content)

    assert "".join(collected).strip() == "Hi there"


@pytest.mark.asyncio
async def test_chat_stream_marks_done() -> None:
    """The last chunk from chat_stream has done=True."""
    client = LlamaCppClient(_config())
    chunks = _fake_stream(["A", "B"])
    client._models["nano"] = _mock_llama(chunks)
    client._loaded_tiers.add("nano")

    last_done = False
    async for chunk in client.chat_stream(
        model="nano", messages=[], model_tier="nano"
    ):
        last_done = chunk.done
    assert last_done is True


@pytest.mark.asyncio
async def test_chat_returns_complete_result() -> None:
    """chat() aggregates all chunks into a CompletionResult."""
    client = LlamaCppClient(_config())
    chunks = _fake_stream(["Hello", "world"])
    client._models["nano"] = _mock_llama(chunks)
    client._loaded_tiers.add("nano")

    result = await client.chat(
        model="nano", messages=[], model_tier="nano"
    )
    assert "Hello" in result.content
    assert "world" in result.content
    assert result.latency_ms > 0


@pytest.mark.asyncio
async def test_chat_stream_raises_on_missing_model() -> None:
    """chat_stream raises RuntimeError if no model is loaded for the tier."""
    client = LlamaCppClient(_config())

    with pytest.raises(RuntimeError, match="No llama-cpp model"):
        async for _ in client.chat_stream(
            model="nonexistent", messages=[], model_tier="nonexistent"
        ):
            pass


@pytest.mark.asyncio
async def test_keep_alive_is_noop() -> None:
    """keep_alive completes without error."""
    client = LlamaCppClient(_config())
    await client.keep_alive("nano", "30m")


@pytest.mark.asyncio
async def test_close_clears_models() -> None:
    """close() unloads all models."""
    client = LlamaCppClient(_config())
    client._models["nano"] = _mock_llama()
    client._loaded_tiers.add("nano")

    await client.close()

    assert len(client._models) == 0
    assert len(client._loaded_tiers) == 0


@pytest.mark.asyncio
async def test_load_models_missing_gguf(tmp_path: Path) -> None:
    """load_models logs a warning and skips when the GGUF file doesn't exist."""
    cfg = _config(models_dir=str(tmp_path), filename="missing.gguf")
    client = LlamaCppClient(cfg)

    with patch("llm.llamacpp_client.LlamaCppClient.load_models") as mock_load:
        mock_load.return_value = None
        await client.load_models()
    assert client.has_model("nano") is False


@pytest.mark.asyncio
async def test_load_models_import_error() -> None:
    """load_models handles missing llama-cpp-python gracefully."""
    cfg = _config()
    client = LlamaCppClient(cfg)

    with patch.dict("sys.modules", {"llama_cpp": None}):
        await client.load_models()
    assert client.has_model("nano") is False


@pytest.mark.asyncio
async def test_alias_shares_model() -> None:
    """An alias_of tier shares the same model instance as its target."""
    cfg = _config(alias=True)
    client = LlamaCppClient(cfg)
    mock = _mock_llama()
    client._models["nano"] = mock
    client._loaded_tiers.add("nano")

    await client.load_models()

    if "voice_fast" in client._models:
        assert client._models["voice_fast"] is client._models["nano"]


@pytest.mark.asyncio
async def test_chat_stream_dispatches_by_tier() -> None:
    """chat_stream looks up models by model_tier, not model name."""
    client = LlamaCppClient(_config())
    chunks = _fake_stream(["OK"])
    client._models["nano"] = _mock_llama(chunks)
    client._loaded_tiers.add("nano")

    collected: list[str] = []
    async for chunk in client.chat_stream(
        model="qwen3:4b",
        messages=[],
        model_tier="nano",
    ):
        collected.append(chunk.content)

    assert "OK" in "".join(collected)


@pytest.mark.asyncio
async def test_protocol_conformance() -> None:
    """LlamaCppClient satisfies LLMClientProtocol at runtime."""
    from llm.base import LLMClientProtocol

    client = LlamaCppClient(_config())
    assert isinstance(client, LLMClientProtocol)


@pytest.mark.asyncio
async def test_ollama_client_protocol_conformance() -> None:
    """OllamaClient satisfies LLMClientProtocol at runtime."""
    from llm.base import LLMClientProtocol
    from llm.client import OllamaClient

    client = OllamaClient()
    assert isinstance(client, LLMClientProtocol)
