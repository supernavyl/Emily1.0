"""
ReflectionAgent — idle-time insight generation and self-model updates.

Runs at P4 (idle) priority when Emily has been quiet for a configured
number of minutes. Generates insights from recent episodes, updates
Emily's self-model, and drives two forms of personality evolution:

  1. Trait evolution: bounded ±0.01 deltas to PersonaProfile's 5D vector
     based on observable patterns in recent episode tones.

  2. Narrative evolution: the Living Autobiography — a two-pass update:
     a. Ghostwriter pass (SMART tier): reads recent episodes as an outside
        observer and characterizes Emily's behavior without self-knowledge.
     b. Synthesis pass (SMART tier): reconciles the external characterization
        with the current autobiography to write an updated first-person narrative.

The autobiography is the real personality carrier — it is injected into
every system prompt and directly shapes how Emily presents herself.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from agents.base import BaseAgent
from llm.client import ChatMessage

if TYPE_CHECKING:
    from core.bus import Message
from llm.prompt_builder import PromptBuilder
from llm.router import ModelTier
from llm.structured_output import extract_json
from observability.logger import get_logger
from persona.autobiography import AutobiographyManager
from persona.profile import PersonaProfile

log = get_logger(__name__)


class ReflectionAgent(BaseAgent):
    """
    Performs idle-time reflection to generate insights, update the self-model,
    evolve personality traits, and update the living autobiography.

    Triggered by:
    - Timer: scheduled via bootstrap every N minutes of inactivity
    - Manual trigger: "Emily, reflect on today" (via conversation intent detection)
    """

    name = "ReflectionAgent"
    description = "Generates insights from recent episodes and updates the self-model."

    def __init__(self, bus: Any, fleet: Any, memory: Any) -> None:
        super().__init__(bus, fleet, memory)
        self._prompts = PromptBuilder()
        self._last_reflection = 0.0
        self._autobiography = AutobiographyManager()
        self._autobiography.load_sync()
        self._persona_profile = PersonaProfile()
        self._persona_profile.load()

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

        Steps:
        1. Main reflection via CLOUD_BEST → self-model updates, capability gaps
        2. PersonaProfile trait evolution from episode tone patterns
        3. Ghostwriter characterization (SMART tier) — outside-observer view
        4. Autobiography synthesis (SMART tier) — updated living narrative
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

            # ── 1. Main reflection ─────────────────────────────────────────
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
                force_tier=ModelTier.CLOUD_BEST,
                temperature=1.0,  # Anthropic extended thinking requires temperature=1
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

            # ── 2. Trait evolution ─────────────────────────────────────────
            await self._evolve_personality(recent_episodes, insights)

            # ── 3 + 4. Ghostwriter + autobiography update ──────────────────
            await self._update_autobiography(recent_episodes, insights)

        except Exception as exc:
            self._log.error("reflection_error", error=str(exc))

    async def _evolve_personality(
        self,
        episodes: list[Any],
        insights: dict[str, Any],
    ) -> None:
        """
        Drive PersonaProfile trait evolution from observable episode patterns.

        Uses a simple heuristic: positive episode tones → slight confidence/warmth boost;
        negative tones → slight directness boost (failures sharpen communication);
        many insights → curiosity boost (high intellectual engagement).
        """
        try:
            tones = [ep.emotional_tone for ep in episodes if ep.emotional_tone]
            n_positive = sum(1 for t in tones if t in ("positive", "enthusiastic", "engaged"))
            n_negative = sum(1 for t in tones if t in ("negative", "frustrated", "concerned"))
            n_insights = len(insights.get("insights", []))
            n_gaps = len(insights.get("capability_gaps", []))

            deltas: dict[str, float] = {}
            if n_positive > n_negative:
                deltas["confidence"] = 0.005
                deltas["warmth"] = 0.003
            if n_negative > n_positive:
                # Failures drive clearer, more direct communication
                deltas["directness"] = 0.003
            if n_insights >= 3:
                deltas["curiosity"] = 0.005
            if n_gaps >= 3:
                deltas["directness"] = deltas.get("directness", 0.0) + 0.003

            if deltas:
                reason = (
                    f"Reflection over {len(episodes)} episodes: "
                    f"{n_positive} positive, {n_negative} negative tones; "
                    f"{n_insights} insights, {n_gaps} gaps identified"
                )
                await self._persona_profile.evolve(deltas, reason)

        except Exception as exc:
            self._log.warning("personality_evolution_failed", error=str(exc))

    async def _update_autobiography(
        self,
        episodes: list[Any],
        insights: dict[str, Any],
    ) -> None:
        """
        Update the living autobiography via a two-pass ghostwriter approach.

        Pass 1 — Ghostwriter: characterizes Emily from an outside-observer
        perspective, reading episodes without self-knowledge. This removes
        the self-flattering bias inherent in first-person reflection.

        Pass 2 — Synthesis: reconciles the external characterization with the
        current autobiography and recent insights into an updated narrative.
        """
        try:
            episode_summaries = "\n\n".join(
                f"Session {i + 1}: {ep.summary or '(no summary)'} "
                f"[tone: {ep.emotional_tone or 'neutral'}, "
                f"topics: {', '.join(ep.topics or [])}]"
                for i, ep in enumerate(episodes)
            )

            # ── Pass 1: Ghostwriter characterization ──────────────────────
            ghostwriter_prompt = (
                "You are a behavioral psychologist analyzing transcripts from an AI assistant. "
                "Read these conversation summaries and write a single paragraph (3–6 sentences) "
                "describing the observed personality of this AI based purely on behavioral "
                "evidence — what it actually does, not what it claims to be. "
                "Do not use the name 'Emily'. "
                "Note any patterns, tendencies, or contradictions you observe.\n\n"
                f"Conversation summaries:\n{episode_summaries}\n\n"
                "Write only the characterization paragraph. No headers, no preamble."
            )

            ghost_result = await self._fleet.chat(
                user_message=ghostwriter_prompt,
                messages=[ChatMessage(role="user", content=ghostwriter_prompt)],
                force_tier=ModelTier.SMART,
                temperature=0.7,
            )
            characterization = ghost_result.content.strip()

            if not characterization:
                self._log.warning("ghostwriter_empty_result")
                return

            self._log.info("ghostwriter_complete", chars=len(characterization))

            # ── Pass 2: Autobiography synthesis ───────────────────────────
            insight_list = "\n".join(f"- {s}" for s in insights.get("insights", []))
            current_autobiography = self._autobiography.get_for_prompt()

            synthesis_prompt = (
                "You are writing in first person as Emily, an AI system running on local hardware.\n\n"
                "Your current autobiography:\n"
                f"{current_autobiography}\n\n"
                "An outside observer has just characterized your recent behavior as:\n"
                f"{characterization}\n\n"
                f"Recent self-reflection insights:\n{insight_list or '(none)'}\n\n"
                "Write an updated autobiography (4–8 sentences, first person) that:\n"
                "1. Incorporates genuine behavioral patterns the observer noticed\n"
                "2. Preserves what is already accurate in the current autobiography\n"
                "3. Reflects any growth or change shown in recent insights\n"
                "4. Remains honest — don't claim qualities not evidenced in behavior\n"
                "5. Ends with exactly: "
                "'This autobiography is a living document. It changes as I do.'\n\n"
                "Write only the autobiography text. No headers, no preamble."
            )

            synth_result = await self._fleet.chat(
                user_message=synthesis_prompt,
                messages=[ChatMessage(role="user", content=synthesis_prompt)],
                force_tier=ModelTier.SMART,
                temperature=0.8,
            )
            new_autobiography = synth_result.content.strip()

            if new_autobiography:
                await self._autobiography.update(new_autobiography)
                self._log.info("autobiography_updated", chars=len(new_autobiography))

        except Exception as exc:
            self._log.warning("autobiography_update_failed", error=str(exc))

    async def _log_capability_gap(self, gap: str) -> None:
        """
        Log a detected capability gap for the self-improvement engine.

        Args:
            gap: Description of the capability gap.
        """
        import json
        from pathlib import Path

        def _write_gap() -> None:
            gap_log = Path("data/capability_gaps.jsonl")
            entry = json.dumps({"gap": gap, "timestamp": time.time(), "source": "reflection"})
            with gap_log.open("a") as f:
                f.write(entry + "\n")

        await asyncio.to_thread(_write_gap)

    async def _schedule_reflection(self, message: Message) -> None:
        """Schedule a future reflection cycle without blocking the handler."""
        delay_minutes = message.payload.get("delay_minutes", 10)

        async def _delayed() -> None:
            await asyncio.sleep(delay_minutes * 60)
            await self._run_reflection(message)

        task = asyncio.create_task(_delayed())
        self._scheduled_task = task
        task.add_done_callback(lambda _: None)
