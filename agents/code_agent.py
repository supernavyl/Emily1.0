"""CodeAgent — code generation, execution, debugging."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from core.bus import Message, Priority
from llm.client import ChatMessage
from llm.prompt_builder import PromptBuilder
from llm.react_loop import ReActLoop
from llm.router import ModelTier, TaskType


class CodeAgent(BaseAgent):
    """Handles code generation, execution, analysis, and debugging tasks."""

    name = "CodeAgent"
    description = "Writes, tests, and debugs code in a sandboxed executor."

    def __init__(self, bus: Any, fleet: Any, memory: Any) -> None:
        super().__init__(bus, fleet, memory)
        self._prompts = PromptBuilder()
        self._react = ReActLoop(fleet, self._prompts)

    async def handle(self, message: Message) -> None:
        """Handle code tasks."""
        if message.type in ("agent.task", "code.request"):
            await self._handle_code_task(message)

    async def _handle_code_task(self, message: Message) -> None:
        """
        Generate and optionally execute code for a given task.

        Args:
            message: Contains "task" with code-related request.
        """
        task = message.payload.get("task", "")
        plan_id = message.payload.get("plan_id")
        step_index = message.payload.get("step_index", 0)
        language = message.payload.get("language", "python")

        code_prompt = (
            f"You are an expert {language} programmer. "
            f"Write clean, well-documented code to solve:\n{task}\n\n"
            "Provide the complete, runnable code. "
            "Include brief inline comments for non-obvious logic."
        )

        result = await self._fleet.chat(
            user_message=task,
            messages=[ChatMessage(role="user", content=code_prompt)],
            force_tier=ModelTier.SMART,
            task_type=TaskType.CODE,
        )

        self._log.info("code_generated", task=task[:60], language=language)

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
