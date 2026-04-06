"""LoopAgent — bus agent that runs the emily-loop kernel for complex multi-step tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from core.bus import AgentBus, Message, Priority
from emily_loop.failures import FailureDB
from emily_loop.loop import Loop, LoopConfig
from emily_loop.models import PlanStatus, StepStatus

from core.loop_integration.fleet_adapter import FleetAdapter
from core.loop_integration.memory_bridge import MemoryBridge
from core.loop_integration.tool_bridge import ToolBridgeAdapter


class LoopAgent(BaseAgent):
    """Agent that runs emily-loop for multi-step tasks.

    Handles three message types:
    - "loop.run" — explicit trigger from any agent or API
    - "planner.plan_request" — backward-compatible drop-in for PlannerAgent
    - "planner.subtask_result" — subtask results from ResearchAgent/CodeAgent
    """

    name = "LoopAgent"
    description = "Executes multi-step plans with checkpoint/resume and failure learning."

    def __init__(
        self,
        bus: Any,
        fleet: Any,
        memory: Any,
        plugin_registry: Any,
        data_dir: Path,
        loop_config: LoopConfig | None = None,
    ) -> None:
        super().__init__(bus, fleet, memory)
        self._plugin_registry = plugin_registry
        self._data_dir = data_dir
        self._loop_config = loop_config
        self._failure_db = FailureDB(data_dir / "failures.db")
        self._memory_bridge = MemoryBridge(memory, self._failure_db)
        self._initialized = False

    async def start(self) -> None:
        """Register handlers on the bus, initialize failure DB, start heartbeat."""
        if not self._initialized:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            await self._failure_db.initialize()
            self._initialized = True

        await super().start()

    async def stop(self) -> None:
        """Shut down the agent."""
        await super().stop()

    async def handle(self, message: Message) -> None:
        """Handle loop.run, planner.plan_request, and planner.subtask_result messages."""
        if message.type in ("loop.run", "planner.plan_request"):
            await self._handle_loop_run(message)
        elif message.type == "planner.subtask_result":
            self._log.info(
                "subtask_result_received",
                plan_id=message.payload.get("plan_id"),
                step_index=message.payload.get("step_index"),
            )

    async def _handle_loop_run(self, message: Message) -> None:
        """Execute a goal through the emily-loop kernel."""
        goal = message.payload.get("task", "")
        if not goal:
            return

        if not self._initialized:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            await self._failure_db.initialize()
            self._initialized = True

        try:
            enriched = await self._memory_bridge.enrich_goal(goal)
            loop = self._build_loop()
            plan = await loop.run(enriched)

            if plan.status == PlanStatus.DONE:
                result_text = self._summarize_plan(plan)
                await self._bus.send_to(
                    recipient="ConversationAgent",
                    msg_type="text.input",
                    payload={
                        "text": f"[Loop completed] {result_text}",
                    },
                    sender=self.name,
                    priority=Priority.ACTIVE,
                    task_id=message.task_id,
                )
            else:
                partial = self._summarize_completed(plan)
                await self._bus.send_to(
                    recipient="ConversationAgent",
                    msg_type="text.input",
                    payload={
                        "text": (
                            f"[Loop failed after {plan.version} attempts] "
                            f"Original task: {goal}\n"
                            f"Partial progress: {partial}"
                        ),
                    },
                    sender=self.name,
                    priority=Priority.ACTIVE,
                    task_id=message.task_id,
                )

            await self._memory_bridge.sync_failures()

        except Exception as exc:
            self._log.error("loop_agent_error", error=str(exc), exc_info=True)
            # Fall back to ConversationAgent with original task
            await self._bus.send_to(
                recipient="ConversationAgent",
                msg_type="text.input",
                payload={"text": goal},
                sender=self.name,
                priority=Priority.ACTIVE,
                task_id=message.task_id,
            )

    def _build_loop(self) -> Loop:
        """Construct a fresh Loop instance with Emily's fleet and tools."""
        fleet_adapter = FleetAdapter(self._fleet)
        tool_bridge = ToolBridgeAdapter(self._plugin_registry)

        return Loop(
            llm=fleet_adapter,
            tools=tool_bridge.to_tool_registry(),
            failure_db=self._failure_db,
            data_dir=self._data_dir,
            config=self._loop_config,
        )

    @staticmethod
    def _summarize_plan(plan: Any) -> str:
        """Summarize a completed plan's results."""
        done_steps = [s for s in plan.steps if s.status == StepStatus.DONE]
        parts = [f"Goal: {plan.goal}", f"Steps completed: {len(done_steps)}/{len(plan.steps)}"]
        for step in done_steps:
            parts.append(f"  - {step.id}: {step.action[:100]}")
        return "\n".join(parts)

    @staticmethod
    def _summarize_completed(plan: Any) -> str:
        """Summarize completed steps from a failed/abandoned plan."""
        done = [s for s in plan.steps if s.status == StepStatus.DONE]
        if not done:
            return "No steps completed."
        return ", ".join(f"{s.id}: {s.action[:60]}" for s in done)
