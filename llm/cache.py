"""Persistent LLM response cache backed by diskcache.

Caches non-streaming completions keyed on (model, messages, temperature,
max_tokens).  Streaming responses are *not* cached — only the full response
from ``LLMFleet.chat()`` goes through the cache.

TTL strategy:
- temp == 0  → 24 hours (deterministic output)
- temp > 0   → 1 hour  (non-deterministic, but still saves repeated queries)
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TTL_DETERMINISTIC = 86_400  # 24 hours
_TTL_NON_DETERMINISTIC = 3_600  # 1 hour


def _make_key(
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> str:
    """Build a deterministic cache key from request parameters."""
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class LLMCache:
    """Persistent LLM response cache using diskcache.

    Args:
        cache_dir: Directory for the diskcache database.
        max_size_bytes: Maximum cache size in bytes (default 2 GB).
        enabled: Master toggle — when False, all operations are no-ops.
    """

    def __init__(
        self,
        cache_dir: str = "data/llm_cache",
        max_size_bytes: int = 2 * 1024**3,
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._cache: Any | None = None

        if not enabled:
            logger.info("llm_cache_disabled")
            return

        try:
            import diskcache  # type: ignore[import-untyped]

            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            self._cache = diskcache.Cache(cache_dir, size_limit=max_size_bytes)
            logger.info("llm_cache_ready", dir=cache_dir, max_gb=round(max_size_bytes / 1024**3, 1))
        except ImportError:
            logger.warning("llm_cache_unavailable (diskcache not installed)")
            self._enabled = False
        except Exception as exc:
            logger.warning("llm_cache_init_failed: %s", exc)
            self._enabled = False

    def get(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str | None:
        """Look up a cached response.

        Returns:
            The cached response string, or None on miss.
        """
        if not self._enabled or self._cache is None:
            return None

        key = _make_key(model, messages, temperature, max_tokens)
        value = self._cache.get(key)
        if value is not None:
            logger.debug("llm_cache_hit", model=model, key=key[:12])
        return value  # type: ignore[return-value]

    def set(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response: str,
    ) -> None:
        """Store a response in the cache."""
        if not self._enabled or self._cache is None:
            return

        key = _make_key(model, messages, temperature, max_tokens)
        ttl = _TTL_DETERMINISTIC if temperature == 0 else _TTL_NON_DETERMINISTIC
        try:
            self._cache.set(key, response, expire=ttl)
            logger.debug("llm_cache_set", model=model, key=key[:12], ttl=ttl)
        except Exception as exc:
            logger.debug("llm_cache_set_error: %s", exc)

    def clear(self) -> None:
        """Clear all cached entries."""
        if self._cache is not None:
            self._cache.clear()
            logger.info("llm_cache_cleared")

    def close(self) -> None:
        """Close the diskcache database."""
        if self._cache is not None:
            self._cache.close()
