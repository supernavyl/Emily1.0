"""
PlannerAgent — task decomposition and multi-agent delegation.

Breaks complex user requests into a DAG of sub-tasks and delegates
each sub-task to the appropriate specialist agent. Tracks completion
status and aggregates results.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from agents.base import BaseAgent
from core.bus import Message, Priority
from llm.prompt_builder import PromptBuilder
from llm.router import ModelTier, TaskType
from llm.structured_output import extract_json
from observability.logger import get_logger

log = get_logger(__name__)


class PlannerAgent(BaseAgent):
    """
    Decomposes complex tasks into sub-tasks and delegates to specialist agents.

    When a task is flagged as requiring planning (complexity > 7), the
    PlannerAgent:
    1. Uses the smart model to generate a step-by-step plan
    2. Assigns each step to an appropriate agent
    3. Tracks completion and assembles the final response
    """

    name = "PlannerAgent"
    description = "Breaks complex tasks into sub-tasks and coordinates agents."

    def __init__(self, bus: Any, fleet: Any, memory: Any) -> None:
        super().__init__(bus, fleet, memory)
        self._prompts = PromptBuilder()
        self._pending_tasks: dict[str, dict[str, Any]] = {}

    async def handle(self, message: Message) -> None:
        """Handle planning requests and sub-task results."""
        handlers = {
            "planner.plan_request": self._handle_plan_request,
            "planner.subtask_result": self._handle_subtask_result,
        }
        handler = handlers.get(message.type)
        if handler:
            await handler(message)

    async def _handle_plan_request(self, message: Message) -> None:
        """
        Decompose a complex task into a plan and delegate sub-tasks.

        Args:
            message: Contains "task" in payload.
        """
        task = message.payload.get("task", "")
        requester_task_id = message.task_id

        plan_prompt = (
            f"Break this complex task into 2-5 concrete sub-tasks, each assignable to a specialist:\n"
            f"TASK: {task}\n\n"
            f"AVAILABLE AGENTS: ResearchAgent, CodeAgent, ToolBuilderAgent\n\n"
            "Respond with JSON:\n"
            '{"steps": [{"step": 1, "agent": "AgentName", "task": "...", "depends_on": []}]}'
        )

        from llm.client import ChatMessage
        result = await self._fleet.chat(
            user_message=plan_prompt,
            messages=[ChatMessage(role="user", content=plan_prompt)],
            force_tier=ModelTier.SMART,
            temperature=0.3,
        )

        plan = extract_json(result.content)
        if not plan or "steps" not in plan:
            self._log.warning("plan_generation_failed", task=task[:80])
            await self.send(
                "ConversationAgent",
                "text.input",
                {"text": task},
                priority=Priority.ACTIVE,
                task_id=requester_task_id,
            )
            return

        steps = plan["steps"]
        self._log.info("plan_created", task=task[:80], n_steps=len(steps))

        # Track this plan's pending sub-tasks
        plan_id = str(uuid.uuid4())
        self._pending_tasks[plan_id] = {
            "task": task,
            "steps": steps,
            "completed": {},
            "requester_task_id": requester_task_id,
            "total_steps": len(steps),
        }

        # Delegate to agents (topological order via depends_on)
        for step in steps:
            if not step.get("depends_on"):  # Run root steps immediately
                await self.send(
                    step["agent"],
                    "agent.task",
                    {
                        "task": step["task"],
                        "plan_id": plan_id,
                        "step_index": step["step"],
                    },
                    priority=Priority.ACTIVE,
                )

    async def _handle_subtask_result(self, message: Message) -> None:
        """
        Process a completed sub-task result and check if the plan is done.

        Args:
            message: Contains "plan_id", "step_index", "result" in payload.
        """
        plan_id = message.payload.get("plan_id", "")
        step_index = message.payload.get("step_index", 0)
        result = message.payload.get("result", "")

        if plan_id not in self._pending_tasks:
            return

        plan = self._pending_tasks[plan_id]
        plan["completed"][step_index] = result

        self._log.info(
            "subtask_complete",
            plan_id=plan_id,
            step=step_index,
            completed=len(plan["completed"]),
            total=plan["total_steps"],
        )

        if len(plan["completed"]) == plan["total_steps"]:
            # All steps done — assemble final answer
            results_text = "\n".join(
                f"Step {k}: {v}" for k, v in sorted(plan["completed"].items())
            )
            await self.send(
                "ConversationAgent",
                "text.input",
                {"text": f"Synthesize these research results into a final answer for: {plan['task']}\n\n{results_text}"},
                priority=Priority.ACTIVE,
                task_id=plan["requester_task_id"],
            )
            del self._pending_tasks[plan_id]
