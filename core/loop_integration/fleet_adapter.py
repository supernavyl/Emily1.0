"""FleetAdapter — wraps Emily's LLMFleet to satisfy emily-loop's LLMClient protocol."""

from __future__ import annotations

import json
from typing import Any

from llm.client import ChatMessage
from llm.fleet import LLMFleet
from llm.router import ModelTier


class FleetAdapter:
    """Bridges LLMFleet.chat() to the emily-loop LLMClient.complete() protocol.

    Loop gets Emily's circuit breakers, fallback chains, and model tier
    selection for free through this adapter.
    """

    def __init__(self, fleet: LLMFleet, tier: ModelTier = ModelTier.SMART) -> None:
        self._fleet = fleet
        self._tier = tier

    async def complete(self, prompt: str, schema: type | None = None) -> str | Any:
        """Generate a completion via Emily's fleet.

        Args:
            prompt: The prompt text.
            schema: If provided, append JSON instruction and parse response as JSON.

        Returns:
            Raw text if schema is None, parsed dict/list if schema is provided.

        Raises:
            json.JSONDecodeError: If schema is provided but response isn't valid JSON.
        """
        effective_prompt = prompt
        if schema is not None:
            effective_prompt = prompt + "\n\nRespond with valid JSON only."

        messages = [ChatMessage(role="user", content=effective_prompt)]

        result = await self._fleet.chat(
            user_message=effective_prompt,
            messages=messages,
            force_tier=self._tier,
        )

        if schema is not None:
            return json.loads(result.content)
        return result.content
