"""TabbyAPI provider — ExLlamaV2-based local inference (OpenAI-compatible).

TabbyAPI (https://github.com/therealconceptual/tabbyAPI) exposes the standard
OpenAI ``/v1/chat/completions`` SSE protocol backed by ExLlamaV2, making it
the fastest quantized-model backend on RTX-class hardware.

Key behaviours:
* Streaming via ``POST /v1/chat/completions`` SSE (identical to OpenAI wire
  format).  Inherits the full SSE + ThinkTagExtractor logic from
  :class:`~emily_chat.models.providers._openai_compat.OpenAICompatibleProvider`.
* Auth via ``x-api-key`` header.  For local deployments with auth disabled
  in TabbyAPI's ``config.yml``, leave *api_key* empty.
* Auto-discovery via ``GET /v1/models``.
* All inference is free (``cost = $0``).
* Think-tag extraction active for abliterated Qwen2.5 / QwQ models.

Recommended abliterated EXL2 models for RTX 4090 (24 GB VRAM):
  fast tier   Qwen2.5-14B-Instruct-abliterated-4.65bpw-EXL2   (~8.5 GB VRAM)
  smart tier  QwQ-32B-abliterated-4.0bpw-EXL2                 (~17 GB VRAM)
"""

from __future__ import annotations

import logging
from typing import Any

from emily_chat.models.providers._openai_compat import OpenAICompatibleProvider
from emily_chat.models.registry import ModelSpec
from emily_chat.models.streaming_engine import GenerationSettings

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:5000/v1"

# Model name fragments that emit <think>…</think> blocks
_THINK_TAG_PATTERNS = (
    "qwen2.5",
    "qwen3",
    "qwq",
    "abliterated",
    "deepseek-r1",
    "deepseek-r2",
)


class TabbyAPIProvider(OpenAICompatibleProvider):
    """Async streaming provider for locally running TabbyAPI (ExLlamaV2).

    Args:
        base_url: TabbyAPI ``/v1`` endpoint URL.
        api_key: ``x-api-key`` value.  Leave empty if auth is disabled.
        timeout: Per-request timeout in seconds.
    """

    _provider_name = "TabbyAPI"

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        api_key: str = "",
        timeout: float = 300.0,
    ) -> None:
        # OpenAICompatibleProvider expects api_key and base_url; it sends
        # "Authorization: Bearer <api_key>".  TabbyAPI also accepts that header
        # (in addition to x-api-key), so this works for both auth modes.
        super().__init__(api_key=api_key or "tabbyapi", base_url=base_url, timeout=timeout)

    def supports_thinking(self) -> bool:
        """TabbyAPI with Qwen/QwQ abliterated models emits think blocks."""
        return True

    def supports_vision(self) -> bool:
        return False

    def _uses_think_tags(self, model_id: str) -> bool:
        """Return True for model IDs that emit ``<think>…</think>`` blocks."""
        lower = model_id.lower()
        return any(p in lower for p in _THINK_TAG_PATTERNS)

    def _build_request_body(
        self,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        model_spec: ModelSpec,
    ) -> dict[str, Any]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        body: dict[str, Any] = {
            "model": model_spec.model_id,
            "messages": full_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": settings.temperature,
        }
        if settings.top_p != 1.0:
            body["top_p"] = settings.top_p
        if settings.max_tokens > 0:
            body["max_tokens"] = settings.max_tokens
        if settings.stop:
            body["stop"] = settings.stop
        return body

    # ── Discovery ────────────────────────────────────────────────────────────

    async def discover_models(self) -> list[dict]:
        """Query TabbyAPI for loaded / available models.

        Returns:
            List of ``{"name": model_id, ...}`` dicts (same shape as
            :meth:`~emily_chat.models.providers.ollama.OllamaProvider.discover_models`
            for compatibility with the controller's discovery loop).
        """
        try:
            resp = await self._client.get("/models")
            if resp.status_code != 200:
                return []
            data = resp.json()
            return [
                {"name": m.get("id", ""), "size": 0, "modified_at": ""}
                for m in data.get("data", [])
                if m.get("id")
            ]
        except Exception as exc:
            logger.debug("tabbyapi_discover_failed", exc_info=exc)
            return []

    @staticmethod
    def create_local_spec(model_id: str) -> ModelSpec:
        """Build a :class:`ModelSpec` for a dynamically discovered TabbyAPI model.

        Args:
            model_id: Model directory name as reported by ``GET /v1/models``.

        Returns:
            A :class:`ModelSpec` wired to the ``tabbyapi`` provider.
        """
        lower = model_id.lower()
        is_thinking = any(p in lower for p in _THINK_TAG_PATTERNS)
        return ModelSpec(
            display=f"TabbyAPI — {model_id}",
            provider="tabbyapi",
            model_id=model_id,
            context=131_072,
            thinking=is_thinking,
            input_usd=0.0,
            output_usd=0.0,
            speed="ultra-fast",
            tier="excellent",
            open_weights=True,
            best_for=("conversation", "private", "zero-cost", "abliterated"),
            notes=f"ExLlamaV2 via TabbyAPI. Abliterated model. Model dir: {model_id}",
        )
