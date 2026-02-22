"""OpenAI provider — GPT-5 series, GPT-4o, o3, and o4-mini.

Streams completions via direct ``httpx`` SSE (no ``openai`` SDK dependency)
so that every provider uses the same HTTP stack and the dependency surface
stays minimal.

Key behaviours:
* GPT-5 / GPT-4o: standard ``delta.content`` streaming.
* o3 / o4-mini: ``delta.reasoning_content`` emitted as *thinking* chunks,
  ``delta.content`` as *text* chunks.  ``reasoning_effort`` is sent
  instead of ``temperature``.
* Vision: images passed as ``image_url`` content-parts.
* Usage: ``prompt_tokens``, ``completion_tokens``, and
  ``completion_tokens_details.reasoning_tokens`` extracted from the final
  chunk.
"""

from __future__ import annotations

from typing import Any

from emily_chat.models.providers._openai_compat import OpenAICompatibleProvider
from emily_chat.models.registry import ModelSpec
from emily_chat.models.streaming_engine import GenerationSettings

_BASE_URL = "https://api.openai.com/v1"

_REASONING_MODEL_PREFIXES = ("o3", "o4", "o1")


def _is_reasoning_model(model_id: str) -> bool:
    """Return True if *model_id* belongs to OpenAI's o-series.

    Args:
        model_id: The provider-side model identifier.

    Returns:
        ``True`` for o1, o3, o4 prefix models.
    """
    return any(model_id.startswith(p) for p in _REASONING_MODEL_PREFIXES)


class OpenAIProvider(OpenAICompatibleProvider):
    """Async streaming provider for all OpenAI chat-completion models.

    Extends :class:`OpenAICompatibleProvider` with o-series reasoning
    support and vision message helpers.

    Args:
        api_key: The OpenAI API key.
        base_url: Override the API base (useful for proxies / Azure).
        timeout: Per-request timeout in seconds.
    """

    _provider_name = "OpenAI"

    def __init__(
        self,
        api_key: str,
        base_url: str = _BASE_URL,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(api_key=api_key, base_url=base_url, timeout=timeout)

    def supports_thinking(self) -> bool:
        """OpenAI o-series models emit reasoning tokens."""
        return True

    def supports_vision(self) -> bool:
        """GPT-4o, GPT-5 series support image inputs."""
        return True

    # ── request building (o-series override) ──────────────────

    def _build_request_body(
        self,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        model_spec: ModelSpec,
    ) -> dict[str, Any]:
        """Assemble the JSON body for the chat-completions endpoint.

        For o-series models ``temperature`` is omitted and
        ``reasoning_effort`` is added instead.

        Args:
            messages: Conversation messages.
            system_prompt: System prompt string.
            settings: Generation settings.
            model_spec: Model specification.

        Returns:
            The request body dict.
        """
        full_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        body: dict[str, Any] = {
            "model": model_spec.model_id,
            "messages": full_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        is_reasoning = _is_reasoning_model(model_spec.model_id)

        if is_reasoning:
            effort = settings.reasoning_effort
            if effort not in ("low", "medium", "high"):
                effort = "medium"
            body["reasoning_effort"] = effort
        else:
            body["temperature"] = settings.temperature
            body["top_p"] = settings.top_p
            if settings.max_tokens > 0:
                body["max_completion_tokens"] = settings.max_tokens

        if settings.stop:
            body["stop"] = settings.stop

        return body

    # ── vision helpers ───────────────────────────────────────

    @staticmethod
    def build_vision_message(
        text: str,
        image_urls: list[str],
        detail: str = "auto",
    ) -> dict[str, Any]:
        """Build a user message with inline image content parts.

        Args:
            text: The text portion of the user message.
            image_urls: Base64 data-URIs or HTTPS URLs for images.
            detail: Image detail level (``"auto"``, ``"low"``, ``"high"``).

        Returns:
            A message dict with a content list suitable for the
            chat-completions API.
        """
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for url in image_urls:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": url, "detail": detail},
                }
            )
        return {"role": "user", "content": content}
