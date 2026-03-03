"""
In-process LLM client using llama-cpp-python for Emily.

Eliminates HTTP/JSON overhead for latency-critical model tiers by calling
llama.cpp directly via its Python bindings.  Implements the same
:class:`~llm.base.LLMClientProtocol` as :class:`~llm.client.OllamaClient`
so the rest of the system is backend-agnostic.

Key design points:
- Async streaming via ``asyncio.Queue`` + ``run_in_executor`` bridging the
  synchronous ``create_chat_completion(stream=True)`` iterator.
- Model deduplication: multiple tiers that reference the same GGUF (e.g.
  nano and voice_fast) share a single loaded ``Llama`` instance.
- Graceful fallback: if llama-cpp-python is not installed or a GGUF file is
  missing, :meth:`load_models` logs a warning and the fleet routes those
  tiers to Ollama instead.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from config import LlamaCppConfig
from llm.client import ChatMessage, CompletionChunk, CompletionResult, EmbeddingResult
from observability.logger import get_logger
from observability.metrics import LLM_FIRST_TOKEN_LATENCY, LLM_REQUESTS_TOTAL

log = get_logger(__name__)

_SENTINEL = object()


class LlamaCppClient:
    """
    Direct in-process inference via llama-cpp-python.

    Satisfies :class:`~llm.base.LLMClientProtocol`.
    """

    def __init__(self, config: LlamaCppConfig) -> None:
        """
        Args:
            config: llama-cpp-python configuration with model paths and params.
        """
        self._config = config
        self._models: dict[str, Any] = {}
        self._loaded_tiers: set[str] = set()

    async def load_models(self) -> None:
        """Load all configured GGUF models into memory.

        Models linked via ``alias_of`` share the same ``Llama`` instance.
        """
        try:
            from llama_cpp import Llama  # type: ignore[import-untyped]
        except ImportError:
            log.warning(
                "llamacpp_not_installed",
                hint="pip install 'llama-cpp-python>=0.3.0'",
            )
            return

        models_dir = Path(self._config.models_dir)
        loaded_by_filename: dict[str, Any] = {}

        for tier_name, model_cfg in self._config.models.items():
            if model_cfg.alias_of:
                alias_target = model_cfg.alias_of
                if alias_target in self._models:
                    self._models[tier_name] = self._models[alias_target]
                    self._loaded_tiers.add(tier_name)
                    log.info(
                        "llamacpp_model_alias",
                        tier=tier_name,
                        alias_of=alias_target,
                    )
                else:
                    log.warning(
                        "llamacpp_alias_target_missing",
                        tier=tier_name,
                        alias_of=alias_target,
                    )
                continue

            if not model_cfg.filename:
                continue

            gguf_path = models_dir / model_cfg.filename
            if not gguf_path.exists():
                log.warning(
                    "llamacpp_gguf_not_found",
                    tier=tier_name,
                    path=str(gguf_path),
                    hint=f"Download the GGUF to {gguf_path}",
                )
                continue

            if model_cfg.filename in loaded_by_filename:
                self._models[tier_name] = loaded_by_filename[model_cfg.filename]
                self._loaded_tiers.add(tier_name)
                log.info(
                    "llamacpp_model_shared",
                    tier=tier_name,
                    filename=model_cfg.filename,
                )
                continue

            log.info(
                "llamacpp_loading_model",
                tier=tier_name,
                path=str(gguf_path),
                n_gpu_layers=model_cfg.n_gpu_layers,
                n_ctx=model_cfg.n_ctx,
            )
            try:
                model = await asyncio.to_thread(
                    Llama,
                    model_path=str(gguf_path),
                    n_gpu_layers=model_cfg.n_gpu_layers,
                    n_ctx=model_cfg.n_ctx,
                    n_batch=model_cfg.n_batch,
                    verbose=False,
                )
                self._models[tier_name] = model
                loaded_by_filename[model_cfg.filename] = model
                self._loaded_tiers.add(tier_name)
                log.info("llamacpp_model_loaded", tier=tier_name)
            except Exception as exc:
                log.error(
                    "llamacpp_load_failed",
                    tier=tier_name,
                    error=str(exc),
                )

    def has_model(self, tier: str) -> bool:
        """Return True if *tier* has a loaded in-process model."""
        return tier in self._loaded_tiers

    async def health_check(self) -> bool:
        """Return True if at least one model is loaded."""
        return bool(self._loaded_tiers)

    async def chat_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        repeat_penalty: float = 1.1,
        model_tier: str = "fast",
    ) -> AsyncIterator[CompletionChunk]:
        """
        Stream a chat completion from an in-process GGUF model.

        The synchronous llama-cpp iterator runs in a thread-pool executor;
        chunks are bridged to async via an :class:`asyncio.Queue`.

        Args:
            model: Tier name key (not an Ollama model tag).
            messages: Conversation messages.
            temperature: Sampling temperature.
            top_p: Top-p nucleus sampling.
            max_tokens: Maximum tokens to generate.
            repeat_penalty: Repetition penalty.
            model_tier: Logical tier label for metrics.

        Yields:
            CompletionChunk objects as tokens arrive.
        """
        llm = self._models.get(model_tier) or self._models.get(model)
        if llm is None:
            raise RuntimeError(
                f"No llama-cpp model loaded for tier={model_tier!r} / model={model!r}"
            )

        msgs = [{"role": m.role, "content": m.content} for m in messages]

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=64)

        t0 = time.monotonic()
        first_token = True
        LLM_REQUESTS_TOTAL.labels(model_tier=model_tier, status="started").inc()

        exc_holder: list[BaseException] = []

        def _run() -> None:
            try:
                for chunk in llm.create_chat_completion(
                    messages=msgs,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    repeat_penalty=repeat_penalty,
                    stream=True,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except BaseException as e:
                exc_holder.append(e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

        fut = loop.run_in_executor(None, _run)

        try:
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break

                delta = item.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                finish = item.get("choices", [{}])[0].get("finish_reason")

                if first_token and content:
                    latency = time.monotonic() - t0
                    LLM_FIRST_TOKEN_LATENCY.labels(model_tier=model_tier).observe(latency)
                    log.debug(
                        "llm_first_token",
                        model=model,
                        tier=model_tier,
                        latency_ms=f"{latency * 1000:.0f}",
                        backend="llamacpp",
                    )
                    first_token = False

                yield CompletionChunk(
                    content=content,
                    done=finish is not None,
                    model=model,
                )

            await fut

            if exc_holder:
                LLM_REQUESTS_TOTAL.labels(model_tier=model_tier, status="error").inc()
                raise exc_holder[0]

            LLM_REQUESTS_TOTAL.labels(model_tier=model_tier, status="success").inc()

        except Exception as exc:
            LLM_REQUESTS_TOTAL.labels(model_tier=model_tier, status="error").inc()
            log.error("llamacpp_stream_error", model=model, error=str(exc))
            raise

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        repeat_penalty: float = 1.1,
        model_tier: str = "fast",
    ) -> CompletionResult:
        """
        Non-streaming chat completion via the in-process model.

        Args:
            model: Tier name or model key.
            messages: Conversation messages.
            temperature: Sampling temperature.
            top_p: Top-p sampling.
            max_tokens: Max tokens to generate.
            repeat_penalty: Repetition penalty.
            model_tier: Logical tier for metrics.

        Returns:
            CompletionResult with the full response.
        """
        t0 = time.monotonic()
        full_content = ""
        last_chunk: CompletionChunk | None = None

        async for chunk in self.chat_stream(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            repeat_penalty=repeat_penalty,
            model_tier=model_tier,
        ):
            full_content += chunk.content
            last_chunk = chunk

        latency_ms = (time.monotonic() - t0) * 1000.0
        return CompletionResult(
            content=full_content,
            model=model,
            total_tokens=last_chunk.eval_count if last_chunk else 0,
            prompt_tokens=last_chunk.prompt_eval_count if last_chunk else 0,
            latency_ms=latency_ms,
        )

    async def embed(self, model: str, text: str) -> EmbeddingResult:
        """
        Generate an embedding from the in-process model.

        Falls back to raising if no embedding-capable model is loaded.

        Args:
            model: Model/tier key.
            text: Text to embed.

        Returns:
            EmbeddingResult with the embedding vector.
        """
        llm = self._models.get(model)
        if llm is None:
            raise RuntimeError(f"No llama-cpp model loaded for embedding model={model!r}")
        result = await asyncio.to_thread(llm.embed, text)
        vec = result if isinstance(result, list) else list(result)
        if vec and isinstance(vec[0], list):
            vec = vec[0]
        return EmbeddingResult(embedding=vec, model=model)

    async def keep_alive(self, model: str, duration: str = "30m") -> None:
        """No-op — in-process models are always resident."""
        log.debug("llamacpp_keep_alive_noop", model=model)

    async def close(self) -> None:
        """Unload all models and free resources."""
        for tier, llm in self._models.items():
            try:
                if hasattr(llm, "close"):
                    llm.close()
            except Exception:
                pass
            log.debug("llamacpp_model_unloaded", tier=tier)
        self._models.clear()
        self._loaded_tiers.clear()
