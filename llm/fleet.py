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

import os
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from emily_chat.models.registry import ModelSpec, register_dynamic_model
from llm.anthropic_client import AnthropicFleetClient
from llm.cache import LLMCache
from llm.client import ChatMessage, CompletionResult, EmbeddingResult, OllamaClient
from llm.llamacpp_client import LlamaCppClient
from llm.router import ModelRouter, ModelTier, RoutingDecision, TaskType
from llm.tabbyapi_client import TabbyAPIClient
from observability.logger import get_logger
from observability.metrics import LLM_FIRST_TOKEN_LATENCY, LLM_REQUESTS_TOTAL

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


# ---------------------------------------------------------------------------
# Circuit breaker for per-backend health tracking
# ---------------------------------------------------------------------------

_CIRCUIT_FAILURE_WINDOW = 300  # 5 minutes
_CIRCUIT_OPEN_DURATION = 60  # 60 seconds
_CIRCUIT_FAILURE_THRESHOLD = 3

_TRANSIENT_MARKERS = ("connection", "reset", "timeout", "503", "502", "unavailable")


@dataclass
class _BackendState:
    """Per-backend circuit breaker state."""

    failures: int = 0
    last_failure: float = 0.0
    unhealthy_until: float = 0.0

    def record_failure(self) -> None:
        now = time.monotonic()
        # Reset counter if last failure was outside the window
        if now - self.last_failure > _CIRCUIT_FAILURE_WINDOW:
            self.failures = 0
        self.failures += 1
        self.last_failure = now
        if self.failures >= _CIRCUIT_FAILURE_THRESHOLD:
            self.unhealthy_until = now + _CIRCUIT_OPEN_DURATION

    def record_success(self) -> None:
        self.failures = 0
        self.last_failure = 0.0
        self.unhealthy_until = 0.0

    @property
    def is_healthy(self) -> bool:
        return time.monotonic() >= self.unhealthy_until


def _is_transient(exc: Exception) -> bool:
    """Return True if *exc* looks transient (worth retrying once)."""
    msg = str(exc).lower()
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


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
        self._cache = LLMCache(
            cache_dir=config.cache.dir,
            max_size_bytes=int(config.cache.max_size_gb * 1024**3),
            enabled=config.cache.enabled,
        )
        self._available_models: set[str] = set()
        self._healthy = False
        self._tabbyapi_healthy = False
        self._brain_hub = brain_hub
        self._backend_states: dict[str, _BackendState] = {
            "ollama": _BackendState(),
            "tabbyapi": _BackendState(),
            "llamacpp": _BackendState(),
            "anthropic": _BackendState(),
        }

    # ── dynamic model registration from config ──────────────────

    _TIER_DISPLAY: dict[str, str] = {
        "nano": "Quick",
        "voice_fast": "Voice",
        "fast": "Fast",
        "smart": "Smart",
        "reasoning": "Reasoning",
        "deep_think": "Deep Think",
        "code": "Coder",
        "vision": "Vision",
        "embedding": "Embedding",
    }

    _THINK_MODEL_PATTERNS = ("deepseek-r1", "deepseek-r2", "qwen3", "qwq")

    async def _register_config_models(self) -> None:
        """Build ModelSpec entries from config.yaml tiers and register them.

        For Ollama models, queries ``POST /api/show`` to discover the
        context window.  Falls back to sensible defaults if the query fails.
        The ``fast`` tier model is marked as the default.
        """
        models = self._config.models
        tier_backend = self._config.tier_backend

        for tier_name in (
            "nano",
            "voice_fast",
            "fast",
            "smart",
            "reasoning",
            "deep_think",
            "code",
            "vision",
            "embedding",
        ):
            model_id: str = getattr(models, tier_name, "")
            if not model_id:
                continue

            backend: str = getattr(tier_backend, tier_name, "ollama")
            context = 32_768  # safe default
            is_vision = tier_name == "vision"
            lower_id = model_id.lower()
            has_thinking = any(p in lower_id for p in self._THINK_MODEL_PATTERNS)

            # Query Ollama for actual context window
            if backend == "ollama" and self._healthy:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as http:
                        resp = await http.post(
                            f"{self._config.ollama_base_url}/api/show",
                            json={"name": model_id},
                        )
                        if resp.status_code == 200:
                            info = resp.json()
                            # Ollama returns model_info with context length
                            model_info = info.get("model_info", {})
                            for key, val in model_info.items():
                                if "context_length" in key and isinstance(val, int):
                                    context = val
                                    break
                except Exception:
                    pass  # use default context

            label = model_id.split("/")[-1] if "/" in model_id else model_id
            display = (
                f"Emily \u2014 {self._TIER_DISPLAY.get(tier_name, tier_name.title())} ({label})"
            )
            key = f"emily-{tier_name.replace('_', '-')}"

            spec = ModelSpec(
                display=display,
                provider=backend,
                model_id=model_id,
                context=context,
                thinking=has_thinking,
                vision=is_vision,
                input_usd=0.0,
                output_usd=0.0,
                speed="fast",
                tier="local",
                default=(tier_name == "fast"),
                open_weights=True,
                notes=f"Config tier '{tier_name}' via {backend}. 100% private, zero-cost.",
            )
            register_dynamic_model(key, spec)
            log.info(
                "config_model_registered",
                key=key,
                model_id=model_id,
                context=context,
                backend=backend,
            )

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
            self._anthropic = AnthropicFleetClient(
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
                default_thinking_budget=budget,
            )
        return self._anthropic

    def _clients_for_tier(self, tier: ModelTier) -> list[tuple[str, LLMClientProtocol, str]]:
        """Return ``(backend_name, client, model_name)`` tuples in fallback order.

        The configured backend is first, followed by alternatives. The last-resort
        fallback is Anthropic cloud_fast (requires ``ANTHROPIC_API_KEY``).
        """
        configured = getattr(self._config.tier_backend, tier.value, "ollama")
        model_name: str = getattr(self._config.models, tier.value)

        # Primary: configured backend
        primary = self._client_for_tier(tier)
        result: list[tuple[str, LLMClientProtocol, str]] = [(configured, primary, model_name)]

        # Fallback 1: Ollama (if not already primary)
        if configured != "ollama":
            result.append(("ollama", self._ollama, model_name))

        # Fallback 2: TabbyAPI (if not already primary)
        if configured != "tabbyapi":
            result.append(("tabbyapi", self._tabbyapi, model_name))

        # Fallback 3: Anthropic cloud_fast (universal last resort)
        if configured != "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            cloud_model: str = self._config.models.cloud_fast
            result.append(("anthropic", self._get_anthropic_client(tier), cloud_model))

        return result

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
            for tier in (
                "nano",
                "voice_fast",
                "fast",
                "smart",
                "reasoning",
                "deep_think",
                "code",
                "vision",
                "embedding",
            )
            if getattr(self._config.tier_backend, tier, "ollama") == "ollama"
            and getattr(self._config.models, tier, "")
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

        # --- Register config-driven models into the global registry ---
        await self._register_config_models()

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
        import time as _time

        decision = self._router.route(
            user_message, task_type=task_type, force_tier=force_tier, urgency=urgency
        )
        _t0 = _time.monotonic()
        _first_token_recorded = False

        LLM_REQUESTS_TOTAL.labels(
            model_tier=decision.tier.value,
            status="started",
        ).inc()

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

        # Fallback chain: try backends in priority order with circuit breaker
        clients = self._clients_for_tier(decision.tier)
        last_error: Exception | None = None
        succeeded = False
        token_count = 0

        for backend_name, client, fallback_model in clients:
            state = self._backend_states[backend_name]
            if not state.is_healthy:
                log.info("llm_backend_circuit_open", backend=backend_name, tier=decision.tier.value)
                continue

            kwargs = {**stream_kwargs, "model": fallback_model}

            for retry in range(2):  # 1 retry for transient errors
                token_count = 0
                buffer = ""
                in_think = False
                any_yielded = False

                try:
                    async for chunk in client.chat_stream(**kwargs):
                        if not chunk.content:
                            continue
                        buffer += chunk.content

                        # Route <think> content to brain-hub; yield clean text
                        while True:
                            if not in_think:
                                start = buffer.find("<think>")
                                if start == -1:
                                    safe, buffer = buffer, ""
                                    if safe:
                                        token_count += 1
                                        any_yielded = True
                                        if self._brain_hub is not None:
                                            await self._brain_hub.emit(
                                                "llm",
                                                "token",
                                                {
                                                    "text": safe,
                                                    "model": fallback_model,
                                                    "n": token_count,
                                                },
                                            )
                                        if not _first_token_recorded:
                                            LLM_FIRST_TOKEN_LATENCY.labels(
                                                model_tier=decision.tier.value,
                                            ).observe(_time.monotonic() - _t0)
                                            _first_token_recorded = True
                                        yield safe
                                    break
                                else:
                                    before, buffer = (
                                        buffer[:start],
                                        buffer[start + len("<think>") :],
                                    )
                                    in_think = True
                                    if before:
                                        token_count += 1
                                        any_yielded = True
                                        yield before
                            else:
                                end = buffer.find("</think>")
                                if end == -1:
                                    if self._brain_hub is not None:
                                        await self._brain_hub.emit(
                                            "llm",
                                            "thinking_token",
                                            {"text": buffer, "model": fallback_model},
                                        )
                                    buffer = ""
                                    break
                                else:
                                    think_chunk, buffer = (
                                        buffer[:end],
                                        buffer[end + len("</think>") :],
                                    )
                                    in_think = False
                                    if think_chunk and self._brain_hub is not None:
                                        await self._brain_hub.emit(
                                            "llm",
                                            "thinking_token",
                                            {"text": think_chunk, "model": fallback_model},
                                        )

                    if buffer and not in_think:
                        any_yielded = True
                        yield buffer

                    state.record_success()
                    succeeded = True
                    break  # break retry loop

                except Exception as exc:
                    if any_yielded:
                        # Partial content already sent — can't cleanly retry
                        log.error(
                            "llm_stream_partial_failure",
                            backend=backend_name,
                            error=str(exc)[:200],
                        )
                        succeeded = True
                        break

                    if retry == 0 and _is_transient(exc):
                        log.warning(
                            "llm_stream_transient_retry",
                            backend=backend_name,
                            tier=decision.tier.value,
                        )
                        continue  # retry same backend

                    state.record_failure()
                    last_error = exc
                    log.warning(
                        "llm_stream_backend_failed",
                        backend=backend_name,
                        tier=decision.tier.value,
                        error=str(exc)[:200],
                    )
                    if self._brain_hub is not None:
                        await self._brain_hub.emit(
                            "llm",
                            "fallback_triggered",
                            {
                                "failed_backend": backend_name,
                                "tier": decision.tier.value,
                                "error": str(exc)[:200],
                            },
                        )
                    break  # break retry loop, try next backend

            if succeeded:
                break  # break backend loop

        if not succeeded:
            LLM_REQUESTS_TOTAL.labels(
                model_tier=decision.tier.value,
                status="error",
            ).inc()
            log.error(
                "llm_all_backends_failed",
                tier=decision.tier.value,
                error=str(last_error)[:200] if last_error else "unknown",
            )
        else:
            LLM_REQUESTS_TOTAL.labels(
                model_tier=decision.tier.value,
                status="ok",
            ).inc()

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

        # ── Cache lookup ──────────────────────────────────────────────
        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
        cached = self._cache.get(
            model=decision.model_name,
            messages=msg_dicts,
            temperature=effective_temp,
            max_tokens=effective_max_tokens,
        )
        if cached is not None:
            log.info("llm_cache_hit", model=decision.model_name, tier=decision.tier.value)
            thinking_text, clean_text = extract_thinking(cached)
            result = CompletionResult(content=clean_text)
            if thinking_text:
                result.thinking_content = thinking_text
            return result

        if self._brain_hub is not None:
            await self._brain_hub.emit(
                "llm",
                "request",
                {"model": decision.model_name, "tier": decision.tier.value},
            )

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

        # Fallback chain with circuit breaker and retry
        clients = self._clients_for_tier(decision.tier)
        last_error: Exception | None = None

        for backend_name, client, fallback_model in clients:
            state = self._backend_states[backend_name]
            if not state.is_healthy:
                log.info("llm_chat_circuit_open", backend=backend_name, tier=decision.tier.value)
                continue

            kwargs = {**chat_kwargs, "model": fallback_model}

            for retry in range(2):  # 1 retry for transient errors
                t0 = time.monotonic()
                try:
                    result = await client.chat(**kwargs)

                    if self._brain_hub is not None:
                        await self._brain_hub.emit(
                            "llm",
                            "response",
                            {
                                "model": fallback_model,
                                "content_len": len(result.content),
                                "latency_ms": round((time.monotonic() - t0) * 1000),
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
                                {"model": fallback_model, "content": thinking_text},
                            )

                    state.record_success()

                    # ── Cache store ──────────────────────────────────
                    self._cache.set(
                        model=fallback_model,
                        messages=msg_dicts,
                        temperature=effective_temp,
                        max_tokens=effective_max_tokens,
                        response=result.content,
                    )

                    return result

                except Exception as exc:
                    if retry == 0 and _is_transient(exc):
                        log.warning(
                            "llm_chat_transient_retry",
                            backend=backend_name,
                            tier=decision.tier.value,
                        )
                        continue

                    state.record_failure()
                    last_error = exc
                    log.warning(
                        "llm_chat_backend_failed",
                        backend=backend_name,
                        tier=decision.tier.value,
                        error=str(exc)[:200],
                    )
                    if self._brain_hub is not None:
                        await self._brain_hub.emit(
                            "llm",
                            "fallback_triggered",
                            {
                                "failed_backend": backend_name,
                                "tier": decision.tier.value,
                                "error": str(exc)[:200],
                            },
                        )
                    break  # break retry loop, try next backend

        # All backends exhausted
        raise RuntimeError(f"All LLM backends failed for tier {decision.tier.value}: {last_error}")

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
        self._cache.close()
