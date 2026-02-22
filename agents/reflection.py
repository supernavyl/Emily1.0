"""
ReflectionAgent — idle-time insight generation and self-model updates.

Runs at P4 (idle) priority when Emily has been quiet for a configured
number of minutes. Generates insights from recent episodes, updates
Emily's self-model, and triggers prompt evolution if needed.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from agents.base import BaseAgent
from core.bus import Message, Priority
from llm.client import ChatMessage
from llm.prompt_builder import PromptBuilder
from llm.router import ModelTier
from llm.structured_output import extract_json
from observability.logger import get_logger

log = get_logger(__name__)


class ReflectionAgent(BaseAgent):
    """
    Performs idle-time reflection to generate insights and update self-model.

    Triggered by:
    - Timer: runs every N minutes of inactivity
    - Manual trigger: "Emily, reflect on today"
    """

    name = "ReflectionAgent"
    description = "Generates insights from recent episodes and updates the self-model."

    def __init__(self, bus: Any, fleet: Any, memory: Any) -> None:
        super().__init__(bus, fleet, memory)
        self._prompts = PromptBuilder()
        self._last_reflection = 0.0

    async def handle(self, message: Message) -> None:
        """Handle reflection triggers."""
        handlers = {
            "reflection.trigger": self._run_reflection,
            "reflection.schedule": self._schedule_reflection,
        }
        handler = handlers.get(message.type)
        if handler:
            await handler(message)

    async def _run_reflection(self, message: Message) -> None:
        """
        Run a full reflection cycle.

        Retrieves recent episodes, generates insights using the smart model,
        and updates Emily's self-model and persona.
        """
        self._log.info("reflection_starting")
        now = time.time()
        self._last_reflection = now

        try:
            recent_episodes = await self._memory.episodic.get_recent_episodes(n=5)
            self_model = self._memory.procedural.self_model

            if not recent_episodes:
                self._log.info("reflection_skipped_no_episodes")
                return

            prompt = self._prompts.build_reflection_prompt(
                episodes=[
                    {
                        "id": ep.id,
                        "topics": ep.topics,
                        "emotional_tone": ep.emotional_tone,
                        "summary": ep.summary,
                        "key_decisions": ep.key_decisions,
                    }
                    for ep in recent_episodes
                ],
                self_model=self_model,
            )

            result = await self._fleet.chat(
                user_message=prompt,
                messages=[ChatMessage(role="user", content=prompt)],
                force_tier=ModelTier.SMART,
                temperature=0.4,
            )

            insights = extract_json(result.content)
            if insights is None:
                self._log.warning("reflection_parse_failed")
                return

            # Update self-model
            self_updates = insights.get("self_model_updates", {})
            if self_updates:
                await self._memory.procedural.update_self_model(self_updates)

            # Log capability gaps for ToolBuilderAgent
            for gap in insights.get("capability_gaps", []):
                await self._log_capability_gap(gap)

            self._log.info(
                "reflection_complete",
                n_insights=len(insights.get("insights", [])),
                n_gaps=len(insights.get("capability_gaps", [])),
            )

        except Exception as exc:
            self._log.error("reflection_error", error=str(exc))

    async def _log_capability_gap(self, gap: str) -> None:
        """
        Log a detected capability gap for the self-improvement engine.

        Args:
            gap: Description of the capability gap.
        """
        import json
        from pathlib import Path
        gap_log = Path("data/capability_gaps.jsonl")
        entry = json.dumps({"gap": gap, "timestamp": time.time(), "source": "reflection"})
        with gap_log.open("a") as f:
            f.write(entry + "\n")

    async def _schedule_reflection(self, message: Message) -> None:
        """Schedule a future reflection cycle."""
        delay_minutes = message.payload.get("delay_minutes", 10)
        await asyncio.sleep(delay_minutes * 60)
        await self._run_reflection(message)
