"""ResearchAgent — deep-dive RAG + web search + synthesis."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from core.bus import Message, Priority
from llm.client import ChatMessage
from llm.prompt_builder import PromptBuilder
from llm.router import ModelTier


class ResearchAgent(BaseAgent):
    """Performs deep research combining RAG retrieval and web search."""

    name = "ResearchAgent"
    description = "Deep research via RAG, web search, and synthesis."

    def __init__(self, bus: Any, fleet: Any, memory: Any) -> None:
        super().__init__(bus, fleet, memory)
        self._prompts = PromptBuilder()

    async def handle(self, message: Message) -> None:
        """Handle research task requests."""
        if message.type == "agent.task":
            await self._research(message)

    async def _research(self, message: Message) -> None:
        """
        Perform research on a topic and return synthesized findings.

        Args:
            message: Contains "task" and optional "plan_id", "step_index".
        """
        task = message.payload.get("task", "")
        plan_id = message.payload.get("plan_id")
        step_index = message.payload.get("step_index", 0)

        # Use smart model for research synthesis
        research_prompt = (
            f"You are a research specialist. Provide a comprehensive, factual answer to:\n"
            f"{task}\n\n"
            "Include key facts, relevant context, and note any uncertainties."
        )

        result = await self._fleet.chat(
            user_message=task,
            messages=[ChatMessage(role="user", content=research_prompt)],
            force_tier=ModelTier.SMART,
        )

        self._log.info("research_complete", task=task[:60])

        if plan_id:
            await self.send(
                "PlannerAgent",
                "planner.subtask_result",
                {
                    "plan_id": plan_id,
                    "step_index": step_index,
                    "result": result.content,
                    "task": task,
                },
                priority=Priority.ACTIVE,
                task_id=message.task_id,
            )
