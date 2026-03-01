"""
Multi-model LLM fleet manager for Emily.

Manages the lifecycle of the model fleet:
- Health checking Ollama server and llama-cpp-python models
- Tracking which models are loaded (warm) vs. cold
- Providing a unified inference interface that routes to the correct model
- Dispatching each tier to the configured backend (Ollama or llama-cpp-python)
- Monitoring VRAM usage and adjusting model selection accordingly
- Extracting <think>...</think> blocks from QwQ/Qwen3 reasoning models

The fleet manager is the single point of entry for all LLM inference.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from llm.anthropic_client import AnthropicFleetClient
from llm.client import ChatMessage, CompletionResult, EmbeddingResult, OllamaClient
from llm.llamacpp_client import LlamaCppClient
from llm.router import ModelRouter, ModelTier, RoutingDecision, TaskType
from llm.tabbyapi_client import TabbyAPIClient
from observability.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from config import LLMConfig
    from llm.base import LLMClientProtocol

log = get_logger(__name__)

# Matches <think>…</think> blocks emitted by QwQ-32B and Qwen3 thinking models
_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def extract_thinking(text: str) -> tuple[str, str]:
    """
    Split a model response into (thinking_content, visible_content).

    QwQ-32B and Qwen3 models wrap their reasoning in <think>…</think> tags.
    This strips the thinking block so TTS and the chat bubble only get the
    clean response, while the reasoning panel shows the thinking content.

    Args:
        text: Raw model output, possibly containing <think>…</think>.

    Returns:
        Tuple of (thinking_text, clean_response_text).
    """
    thinking_parts: list[str] = []
    clean = _THINK_RE.sub(
        lambda m: thinking_parts.append(m.group(1)) or "",
        text,
    )
    return "\n\n".join(thinking_parts).strip(), clean.strip()


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
        self._tabbyapi = TabbyAPIClient(
            base_url=config.tabbyapi_base_url,
            api_key=config.tabbyapi_api_key,
        )
        self._llamacpp = LlamaCppClient(config.llamacpp)
        self._anthropic: AnthropicFleetClient | None = None
        self._router = ModelRouter(config)
        self._available_models: set[str] = set()
        self._healthy = False
        self._tabbyapi_healthy = False
        self._brain_hub = brain_hub

    def _client_for_tier(self, tier: ModelTier) -> LLMClientProtocol:
        """Return the backend client configured for *tier*."""
        backend = getattr(self._config.tier_backend, tier.value, "ollama")
        if backend == "anthropic":
            return self._get_anthropic_client(tier)
        if backend == "llamacpp" and self._llamacpp.has_model(tier.value):
            return self._llamacpp
        if backend == "tabbyapi":
            return self._tabbyapi
        return self._ollama

    def _get_anthropic_client(self, tier: ModelTier) -> AnthropicFleetClient:
        """Return (lazily create) the Anthropic fleet client.

        Uses a single shared instance — the client is stateless and thread-safe.
        The thinking budget comes from tier_inference config for the requested tier.
        """
        if self._anthropic is None:
            tier_cfg = self._config.tier_inference.for_tier("cloud_best")
            budget = tier_cfg.thinking_budget if tier_cfg.thinking_budget is not None else 16_000
            import os

            self._anthropic = AnthropicFleetClient(
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
                default_thinking_budget=budget,
            )
        return self._anthropic

    async def startup(self) -> None:
        """
        Start all backends: check Ollama health, discover available models,
        and load llama-cpp-python GGUF models if enabled.
        """
        # --- TabbyAPI (text tiers) ---
        self._tabbyapi_healthy = await self._tabbyapi.health_check()
        if not self._tabbyapi_healthy:
            log.warning(
                "tabbyapi_not_reachable",
                url=self._config.tabbyapi_base_url,
                hint="Start TabbyAPI and load your abliterated EXL2 model",
            )
        else:
            tabbyapi_tiers = {
                tier: getattr(self._config.models, tier)
                for tier in ("nano", "voice_fast", "fast", "smart", "reasoning", "embedding")
                if getattr(self._config.tier_backend, tier, "ollama") == "tabbyapi"
            }
            loaded = await self._tabbyapi.list_models()
            for tier, model in tabbyapi_tiers.items():
                if model not in loaded:
                    log.warning(
                        "tabbyapi_model_not_loaded",
                        tier=tier,
                        model=model,
                        loaded=loaded,
                        hint=(
                            f"Load '{model}' in TabbyAPI or update "
                            f"config.yaml llm.models.{tier} to match your model dir name"
                        ),
                    )

        # --- Ollama (non-Tabby capability tiers) ---
        ollama_tiers = {
            tier: getattr(self._config.models, tier)
            for tier in ("nano", "voice_fast", "fast", "smart", "reasoning", "vision", "embedding")
            if getattr(self._config.tier_backend, tier, "ollama") == "ollama"
        }
        if ollama_tiers:
            self._healthy = await self._ollama.health_check()
            if not self._healthy:
                log.error(
                    "ollama_not_reachable",
                    url=self._config.ollama_base_url,
                    required_tiers=sorted(ollama_tiers.keys()),
                )
            else:
                available = await self._ollama.list_models()
                self._available_models = set(available)
                log.info("ollama_healthy", n_models=len(available))
                for tier, model in ollama_tiers.items():
                    if not any(model in m for m in available):
                        log.warning(
                            "model_not_found_in_ollama",
                            tier=tier,
                            model=model,
                            hint=f"Run: ollama pull {model}",
                        )
        else:
            self._healthy = True
            log.info("ollama_skipped_no_required_tiers")

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

        any_backend_up = (
            self._healthy or self._tabbyapi_healthy or await self._llamacpp.health_check()
        )
        if not any_backend_up:
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

        <think>…</think> blocks from QwQ/Qwen3 are intercepted here:
        - Thinking content is emitted to brain-hub as ``"thinking_token"`` events
          (shown in the Reasoning panel in the UI).
        - The yielded stream contains only the clean visible response
          (safe to pipe directly to TTS).

        Args:
            user_message: The current user message (used for routing).
            messages: Full message list including system prompt and history.
            task_type: Task type hint for routing.
            force_tier: Override model selection.
            urgency: Urgency level [0.0, 1.0] affecting model selection.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.

        Yields:
            Clean text token strings (thinking stripped).
        """
        decision = self._router.route(
            user_message, task_type=task_type, force_tier=force_tier, urgency=urgency
        )
        cfg = self._config.inference
        tier_cfg = self._config.tier_inference.for_tier(decision.tier.value)

        effective_temp = temperature or tier_cfg.temperature or cfg.temperature
        effective_max_tokens = max_tokens or tier_cfg.max_tokens or cfg.max_tokens
        enable_thinking = tier_cfg.enable_thinking
        thinking_budget = tier_cfg.thinking_budget  # None for local tiers, int for cloud

        if self._brain_hub is not None:
            await self._brain_hub.emit(
                "llm",
                "token_start",
                {
                    "model": decision.model_name,
                    "tier": decision.tier.value,
                    "task_type": task_type.value if hasattr(task_type, "value") else str(task_type),
                    "thinking": enable_thinking,
                },
            )

        client = self._client_for_tier(decision.tier)
        token_count = 0
        buffer = ""
        in_think = False

        stream_kwargs: dict = {
            "model": decision.model_name,
            "messages": messages,
            "temperature": effective_temp,
            "top_p": cfg.top_p,
            "max_tokens": effective_max_tokens,
            "repeat_penalty": cfg.repeat_penalty,
            "model_tier": decision.tier.value,
            "enable_thinking": enable_thinking,
        }
        if thinking_budget is not None:
            stream_kwargs["thinking_budget"] = thinking_budget

        async for chunk in client.chat_stream(**stream_kwargs):
            if not chunk.content:
                continue
            buffer += chunk.content

            # Route <think> content to brain-hub only; yield clean text to callers
            while True:
                if not in_think:
                    start = buffer.find("<think>")
                    if start == -1:
                        safe, buffer = buffer, ""
                        if safe:
                            token_count += 1
                            if self._brain_hub is not None:
                                await self._brain_hub.emit(
                                    "llm",
                                    "token",
                                    {"text": safe, "model": decision.model_name, "n": token_count},
                                )
                            yield safe
                        break
                    else:
                        before, buffer = buffer[:start], buffer[start + len("<think>") :]
                        in_think = True
                        if before:
                            token_count += 1
                            yield before
                else:
                    end = buffer.find("</think>")
                    if end == -1:
                        if self._brain_hub is not None:
                            await self._brain_hub.emit(
                                "llm",
                                "thinking_token",
                                {"text": buffer, "model": decision.model_name},
                            )
                        buffer = ""
                        break
                    else:
                        think_chunk, buffer = buffer[:end], buffer[end + len("</think>") :]
                        in_think = False
                        if think_chunk and self._brain_hub is not None:
                            await self._brain_hub.emit(
                                "llm",
                                "thinking_token",
                                {"text": think_chunk, "model": decision.model_name},
                            )

        if buffer and not in_think:
            yield buffer

        if self._brain_hub is not None:
            await self._brain_hub.emit(
                "llm",
                "token_end",
                {"model": decision.model_name, "total_tokens": token_count},
            )

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

        Thinking content is stripped from the returned CompletionResult.content
        and stored in CompletionResult.thinking_content instead.

        Args:
            user_message: Current user message for routing.
            messages: Full message list.
            task_type: Task type for routing.
            force_tier: Override model selection.
            urgency: Urgency level for routing.
            temperature: Temperature override.
            max_tokens: Max tokens override.

        Returns:
            CompletionResult with clean response (thinking stored separately).
        """
        decision = self._router.route(
            user_message, task_type=task_type, force_tier=force_tier, urgency=urgency
        )
        cfg = self._config.inference
        tier_cfg = self._config.tier_inference.for_tier(decision.tier.value)

        effective_temp = temperature or tier_cfg.temperature or cfg.temperature
        effective_max_tokens = max_tokens or tier_cfg.max_tokens or cfg.max_tokens
        enable_thinking = tier_cfg.enable_thinking
        thinking_budget = tier_cfg.thinking_budget

        if self._brain_hub is not None:
            await self._brain_hub.emit(
                "llm",
                "request",
                {"model": decision.model_name, "tier": decision.tier.value},
            )

        client = self._client_for_tier(decision.tier)

        import time as _time

        t0 = _time.monotonic()

        chat_kwargs: dict = {
            "model": decision.model_name,
            "messages": messages,
            "temperature": effective_temp,
            "top_p": cfg.top_p,
            "max_tokens": effective_max_tokens,
            "repeat_penalty": cfg.repeat_penalty,
            "model_tier": decision.tier.value,
            "enable_thinking": enable_thinking,
        }
        if thinking_budget is not None:
            chat_kwargs["thinking_budget"] = thinking_budget

        result = await client.chat(**chat_kwargs)

        if self._brain_hub is not None:
            await self._brain_hub.emit(
                "llm",
                "response",
                {
                    "model": decision.model_name,
                    "content_len": len(result.content),
                    "latency_ms": round((_time.monotonic() - t0) * 1000),
                },
            )

        # Extract <think>…</think> blocks from the raw response
        thinking_text, clean_text = extract_thinking(result.content)
        result.content = clean_text
        if thinking_text:
            result.thinking_content = thinking_text
            if self._brain_hub is not None:
                await self._brain_hub.emit(
                    "llm",
                    "thinking",
                    {"model": decision.model_name, "content": thinking_text},
                )

        return result

    async def embed(self, text: str) -> EmbeddingResult:
        """
        Generate an embedding using the configured embedding model.

        Args:
            text: Text to embed.

        Returns:
            EmbeddingResult with the embedding vector.
        """
        backend = getattr(self._config.tier_backend, "embedding", "ollama")
        if backend == "tabbyapi":
            return await self._tabbyapi.embed(
                model=self._config.models.embedding,
                text=text,
            )
        if backend == "llamacpp":
            raise RuntimeError("Embedding backend 'llamacpp' is not supported.")
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
        backend = getattr(self._config.tier_backend, "embedding", "ollama")
        if backend == "tabbyapi":
            return await self._tabbyapi.embed_batch(
                model=self._config.models.embedding,
                texts=texts,
            )
        if backend == "llamacpp":
            raise RuntimeError("Embedding backend 'llamacpp' is not supported.")
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
        vision_backend = getattr(self._config.tier_backend, "vision", "ollama")
        if vision_backend != "ollama":
            raise RuntimeError(
                "Vision chat is currently Ollama-only. Disable vision or set "
                "llm.tier_backend.vision to 'ollama'."
            )

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
            text,
            task_type=task_type,
            force_tier=force_tier,
            urgency=urgency,
            voice_mode=voice_mode,
        )

    @property
    def is_healthy(self) -> bool:
        """True if at least one backend is operational."""
        return self._healthy or self._tabbyapi_healthy or bool(self._llamacpp._loaded_tiers)

    async def shutdown(self) -> None:
        """Close all backend clients."""
        await self._ollama.close()
        await self._tabbyapi.close()
        await self._llamacpp.close()
