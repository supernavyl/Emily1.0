"""
Multi-model LLM fleet manager for Emily.

Manages the lifecycle of the model fleet:
- Health checking Ollama server and llama-cpp-python models
- Tracking which models are loaded (warm) vs. cold
- Providing a unified inference interface that routes to the correct model
- Dispatching each tier to the configured backend (Ollama or llama-cpp-python)
- Monitoring VRAM usage and adjusting model selection accordingly

The fleet manager is the single point of entry for all LLM inference.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from config import LLMConfig
from llm.base import LLMClientProtocol
from llm.client import ChatMessage, CompletionResult, EmbeddingResult, OllamaClient
from llm.llamacpp_client import LlamaCppClient
from llm.router import ModelRouter, ModelTier, RoutingDecision, TaskType
from observability.logger import get_logger
from observability.metrics import VRAM_USED_GB

log = get_logger(__name__)


class LLMFleet:
    """
    Unified interface to Emily's multi-model LLM fleet.

    All agents and tools call this class — never a backend client directly.
    Dispatches each tier to the backend specified in ``config.tier_backend``.
    """

    def __init__(self, config: LLMConfig, brain_hub: Any | None = None) -> None:
        """
        Args:
            config: LLM configuration with model names and inference defaults.
            brain_hub: Optional BrainEventHub for live event streaming to the dashboard.
        """
        self._config = config
        self._ollama = OllamaClient(base_url=config.ollama_base_url)
        self._llamacpp = LlamaCppClient(config.llamacpp)
        self._router = ModelRouter(config)
        self._available_models: set[str] = set()
        self._healthy = False
        self._brain_hub = brain_hub

    def _client_for_tier(self, tier: ModelTier) -> LLMClientProtocol:
        """Return the backend client configured for *tier*."""
        backend = getattr(self._config.tier_backend, tier.value, "ollama")
        if backend == "llamacpp" and self._llamacpp.has_model(tier.value):
            return self._llamacpp
        return self._ollama

    async def startup(self) -> None:
        """
        Start all backends: check Ollama health, discover available models,
        and load llama-cpp-python GGUF models if enabled.
        """
        # --- Ollama ---
        self._healthy = await self._ollama.health_check()
        if not self._healthy:
            log.error("ollama_not_reachable", url=self._config.ollama_base_url)
        else:
            available = await self._ollama.list_models()
            self._available_models = set(available)
            log.info("ollama_healthy", n_models=len(available))

            ollama_tiers = {
                tier: getattr(self._config.models, tier)
                for tier in ("nano", "voice_fast", "fast", "smart", "embedding")
                if getattr(self._config.tier_backend, tier, "ollama") == "ollama"
            }
            for tier, model in ollama_tiers.items():
                if not any(model in m for m in available):
                    log.warning(
                        "model_not_found_in_ollama",
                        tier=tier,
                        model=model,
                        hint=f"Run: ollama pull {model}",
                    )

        # --- llama-cpp-python ---
        if self._config.llamacpp.enabled:
            await self._llamacpp.load_models()
            llamacpp_healthy = await self._llamacpp.health_check()
            if llamacpp_healthy:
                log.info(
                    "llamacpp_healthy",
                    tiers=sorted(self._llamacpp._loaded_tiers),
                )
            elif any(
                getattr(self._config.tier_backend, t, "ollama") == "llamacpp"
                for t in ("nano", "voice_fast", "fast", "smart", "reasoning")
            ):
                log.warning(
                    "llamacpp_no_models_loaded",
                    hint="Tiers configured for llamacpp will fall back to Ollama",
                )

        if not self._healthy and not await self._llamacpp.health_check():
            log.error("no_llm_backend_available")

    async def chat_stream(
        self,
        user_message: str,
        messages: list[ChatMessage],
        task_type: TaskType = TaskType.CHAT,
        force_tier: ModelTier | None = None,
        urgency: float = 0.5,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream a chat completion, automatically routing to the best model.

        Args:
            user_message: The current user message (used for routing).
            messages: Full message list including system prompt and history.
            task_type: Task type hint for routing.
            force_tier: Override model selection.
            urgency: Urgency level [0.0, 1.0] affecting model selection.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.

        Yields:
            Text token strings as they stream from the model.
        """
        decision = self._router.route(
            user_message, task_type=task_type, force_tier=force_tier, urgency=urgency
        )
        cfg = self._config.inference

        if self._brain_hub is not None:
            await self._brain_hub.emit("llm", "token_start", {
                "model": decision.model_name,
                "tier": decision.tier.value,
                "task_type": task_type.value if hasattr(task_type, "value") else str(task_type),
            })

        client = self._client_for_tier(decision.tier)
        token_count = 0
        async for chunk in client.chat_stream(
            model=decision.model_name,
            messages=messages,
            temperature=temperature or cfg.temperature,
            top_p=cfg.top_p,
            max_tokens=max_tokens or cfg.max_tokens,
            repeat_penalty=cfg.repeat_penalty,
            model_tier=decision.tier.value,
        ):
            if chunk.content:
                token_count += 1
                if self._brain_hub is not None:
                    await self._brain_hub.emit("llm", "token", {
                        "text": chunk.content,
                        "model": decision.model_name,
                        "n": token_count,
                    })
                yield chunk.content

        if self._brain_hub is not None:
            await self._brain_hub.emit("llm", "token_end", {
                "model": decision.model_name,
                "total_tokens": token_count,
            })

    async def chat(
        self,
        user_message: str,
        messages: list[ChatMessage],
        task_type: TaskType = TaskType.CHAT,
        force_tier: ModelTier | None = None,
        urgency: float = 0.5,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        """
        Non-streaming chat completion.

        Args:
            user_message: Current user message for routing.
            messages: Full message list.
            task_type: Task type for routing.
            force_tier: Override model selection.
            urgency: Urgency level for routing.
            temperature: Temperature override.
            max_tokens: Max tokens override.

        Returns:
            CompletionResult with full response.
        """
        decision = self._router.route(
            user_message, task_type=task_type, force_tier=force_tier, urgency=urgency
        )
        cfg = self._config.inference

        if self._brain_hub is not None:
            await self._brain_hub.emit("llm", "request", {
                "model": decision.model_name,
                "tier": decision.tier.value,
            })

        client = self._client_for_tier(decision.tier)

        import time as _time
        t0 = _time.monotonic()

        result = await client.chat(
            model=decision.model_name,
            messages=messages,
            temperature=temperature or cfg.temperature,
            top_p=cfg.top_p,
            max_tokens=max_tokens or cfg.max_tokens,
            repeat_penalty=cfg.repeat_penalty,
            model_tier=decision.tier.value,
        )

        if self._brain_hub is not None:
            await self._brain_hub.emit("llm", "response", {
                "model": decision.model_name,
                "content_len": len(result.content),
                "latency_ms": round((_time.monotonic() - t0) * 1000),
            })

        return result

    async def embed(self, text: str) -> EmbeddingResult:
        """
        Generate an embedding using the configured embedding model.

        Args:
            text: Text to embed.

        Returns:
            EmbeddingResult with the embedding vector.
        """
        return await self._ollama.embed(
            model=self._config.models.embedding,
            text=text,
        )

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """
        Embed multiple texts.

        Args:
            texts: List of strings to embed.

        Returns:
            List of EmbeddingResult objects.
        """
        return await self._ollama.embed_batch(
            model=self._config.models.embedding,
            texts=texts,
        )

    async def vision_chat(
        self,
        prompt: str,
        image_b64: str,
        messages: list[ChatMessage] | None = None,
    ) -> CompletionResult:
        """
        Send an image + text prompt to the vision model.

        Args:
            prompt: Text prompt.
            image_b64: Base64-encoded image string.
            messages: Optional conversation history.

        Returns:
            CompletionResult with vision model response.
        """
        vision_messages = messages or []
        vision_messages.append(
            ChatMessage(
                role="user",
                content=prompt,
                images=[image_b64],
            )
        )
        return await self._ollama.chat(
            model=self._config.models.vision,
            messages=vision_messages,
            model_tier="vision",
        )

    def route(
        self,
        text: str,
        task_type: TaskType = TaskType.CHAT,
        force_tier: ModelTier | None = None,
        urgency: float = 0.5,
        voice_mode: bool = False,
    ) -> RoutingDecision:
        """
        Expose the router for inspection without running inference.

        Args:
            text: Input text to score.
            task_type: Task type hint.
            force_tier: Optional override.
            urgency: Urgency level.
            voice_mode: When True, biases toward VOICE_FAST for simple queries.

        Returns:
            RoutingDecision showing which model would be selected.
        """
        return self._router.route(
            text, task_type=task_type, force_tier=force_tier,
            urgency=urgency, voice_mode=voice_mode,
        )

    @property
    def is_healthy(self) -> bool:
        """True if at least one backend is operational."""
        return self._healthy or bool(self._llamacpp._loaded_tiers)

    async def shutdown(self) -> None:
        """Close all backend clients."""
        await self._ollama.close()
        await self._llamacpp.close()
