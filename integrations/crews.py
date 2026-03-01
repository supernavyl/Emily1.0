"""
CrewAI-style multi-agent orchestration for Emily.

Defines reusable Agent roles that collaborate on complex tasks.
Each agent has a role, goal, and backstory that shape its LLM system prompt.
Agents execute Tasks sequentially or in parallel, passing context forward.

Uses Emily's native LLM fleet (fast/smart/reasoning tiers) and tool system
instead of an external framework — so crews can access Emily's memory,
knowledge graph, and all 14+ built-in tools.

Usage::

    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, write_task],
        fleet=fleet,
    )
    result = await crew.kickoff(topic="quantum computing")
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


class ExecutionMode(Enum):
    """How tasks are executed within a crew."""

    SEQUENTIAL = auto()  # Each task gets the output of the previous
    PARALLEL = auto()  # All tasks run concurrently, no context passing


@dataclass
class CrewAgent:
    """An agent role within a crew.

    Each agent becomes a system prompt persona when executing tasks.
    The LLM tier controls which model handles this agent's work.
    """

    role: str  # e.g. "Senior Research Analyst"
    goal: str  # e.g. "Find the most relevant and accurate information"
    backstory: str  # e.g. "You have 20 years of experience in data analysis..."
    llm_tier: str = "smart"  # fast|smart|reasoning — maps to Emily's fleet tiers
    tools: list[str] = field(default_factory=list)  # tool names from PluginRegistry
    max_retries: int = 2
    verbose: bool = False

    def build_agent_persona(self) -> str:
        """Build the LLM system prompt from this agent's persona."""
        parts = [
            f"You are a {self.role}.",
            f"Your goal: {self.goal}",
        ]
        if self.backstory:
            parts.append(f"Background: {self.backstory}")
        parts.append(
            "Provide clear, actionable output. "
            "Do not include preamble or meta-commentary about your role."
        )
        return "\n".join(parts)


@dataclass
class CrewTask:
    """A task to be executed by an agent within a crew."""

    description: str  # What to do — can include {variables}
    agent: CrewAgent  # Who executes this task
    expected_output: str = ""  # Description of what good output looks like
    context_from: list[str] = field(default_factory=list)  # task IDs to pull context from
    task_id: str = ""  # Auto-assigned if empty

    def render(self, variables: dict[str, Any]) -> str:
        """Render the task description with variable substitution."""
        text = self.description
        for key, value in variables.items():
            text = text.replace(f"{{{key}}}", str(value))
        return text


@dataclass
class TaskResult:
    """Result from a single task execution."""

    task_id: str
    output: str
    agent_role: str
    model_used: str
    latency_ms: float
    success: bool = True
    error: str | None = None


@dataclass
class CrewResult:
    """Aggregate result from a full crew execution."""

    task_results: list[TaskResult]
    total_latency_ms: float
    final_output: str  # Output from the last task (sequential) or combined (parallel)

    @property
    def success(self) -> bool:
        return all(r.success for r in self.task_results)


class Crew:
    """Orchestrates multiple agents executing tasks.

    Sequential mode: each task receives the output of all previous tasks as context.
    Parallel mode: all tasks run independently and results are merged.
    """

    def __init__(
        self,
        agents: list[CrewAgent],
        tasks: list[CrewTask],
        fleet: Any,  # LLMFleet instance
        plugin_registry: Any | None = None,  # PluginRegistry for tool execution
        mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
        memory: Any | None = None,  # MemoryManager for context injection
    ) -> None:
        self._agents = {a.role: a for a in agents}
        self._tasks = tasks
        self._fleet = fleet
        self._registry = plugin_registry
        self._mode = mode
        self._memory = memory

        # Auto-assign task IDs
        for i, task in enumerate(self._tasks):
            if not task.task_id:
                task.task_id = f"task_{i}"

    async def kickoff(self, **variables: Any) -> CrewResult:
        """Execute all tasks and return the aggregate result.

        Args:
            **variables: Variables substituted into task descriptions via {key}.

        Returns:
            CrewResult with all task outputs and timing.
        """
        t0 = time.monotonic()
        log.info("crew_kickoff", n_tasks=len(self._tasks), mode=self._mode.name)

        if self._mode == ExecutionMode.SEQUENTIAL:
            results = await self._run_sequential(variables)
        else:
            results = await self._run_parallel(variables)

        total_ms = (time.monotonic() - t0) * 1000
        final_output = results[-1].output if results else ""

        if self._mode == ExecutionMode.PARALLEL:
            final_output = "\n\n---\n\n".join(
                f"**{r.agent_role}**:\n{r.output}" for r in results if r.success
            )

        log.info("crew_complete", total_ms=f"{total_ms:.0f}", n_results=len(results))
        return CrewResult(
            task_results=results,
            total_latency_ms=total_ms,
            final_output=final_output,
        )

    async def _run_sequential(self, variables: dict[str, Any]) -> list[TaskResult]:
        """Execute tasks one by one, passing context forward."""
        results: list[TaskResult] = []
        context_map: dict[str, str] = {}

        for task in self._tasks:
            # Build context from previous task outputs
            context_parts: list[str] = []
            if task.context_from:
                for ref_id in task.context_from:
                    if ref_id in context_map:
                        context_parts.append(context_map[ref_id])
            elif results:
                # Default: use the previous task's output
                context_parts.append(results[-1].output)

            result = await self._execute_task(task, variables, context_parts)
            results.append(result)
            context_map[task.task_id] = result.output

            if not result.success:
                log.warning("crew_task_failed", task_id=task.task_id, error=result.error)
                break

        return results

    async def _run_parallel(self, variables: dict[str, Any]) -> list[TaskResult]:
        """Execute all tasks concurrently."""
        coros = [self._execute_task(task, variables, []) for task in self._tasks]
        return list(await asyncio.gather(*coros))

    async def _execute_task(
        self,
        task: CrewTask,
        variables: dict[str, Any],
        context: list[str],
    ) -> TaskResult:
        """Execute a single task via the LLM fleet."""
        agent = task.agent
        t0 = time.monotonic()

        rendered = task.render(variables)
        agent_persona = agent.build_agent_persona()

        # Build the user message with context
        user_parts: list[str] = []
        if context:
            user_parts.append("## Context from previous work\n" + "\n\n".join(context))
        user_parts.append(f"## Task\n{rendered}")
        if task.expected_output:
            user_parts.append(f"## Expected Output Format\n{task.expected_output}")

        user_message = "\n\n".join(user_parts)

        # Inject memory context if available
        if self._memory:
            try:
                mem_context = await self._memory.get_working_context()
                if mem_context:
                    agent_persona += f"\n\n## Your Memory\n{mem_context}"
            except Exception:
                pass

        model_used = ""
        for attempt in range(agent.max_retries + 1):
            try:
                response = await self._fleet.generate(
                    agent_persona=agent_persona,
                    user_message=user_message,
                    tier=agent.llm_tier,
                )
                model_used = getattr(response, "model", agent.llm_tier)
                output = response.content if hasattr(response, "content") else str(response)

                latency_ms = (time.monotonic() - t0) * 1000
                log.info(
                    "crew_task_done",
                    task_id=task.task_id,
                    agent=agent.role,
                    model=model_used,
                    latency_ms=f"{latency_ms:.0f}",
                    output_len=len(output),
                )

                return TaskResult(
                    task_id=task.task_id,
                    output=output,
                    agent_role=agent.role,
                    model_used=model_used,
                    latency_ms=latency_ms,
                )

            except Exception as exc:
                if attempt < agent.max_retries:
                    log.warning(
                        "crew_task_retry",
                        task_id=task.task_id,
                        attempt=attempt + 1,
                        error=str(exc)[:200],
                    )
                    await asyncio.sleep(1)
                    continue

                latency_ms = (time.monotonic() - t0) * 1000
                return TaskResult(
                    task_id=task.task_id,
                    output="",
                    agent_role=agent.role,
                    model_used=model_used,
                    latency_ms=latency_ms,
                    success=False,
                    error=str(exc),
                )

        # Unreachable but satisfies type checker
        latency_ms = (time.monotonic() - t0) * 1000
        return TaskResult(
            task_id=task.task_id,
            output="",
            agent_role=agent.role,
            model_used="",
            latency_ms=latency_ms,
            success=False,
            error="Exhausted retries",
        )


# ── Pre-built agent templates ─────────────────────────────────────────

RESEARCHER = CrewAgent(
    role="Senior Research Analyst",
    goal="Find the most relevant, accurate, and up-to-date information",
    backstory="Expert at synthesizing information from multiple sources into clear findings.",
    llm_tier="smart",
    tools=["web_search", "web_fetch"],
)

WRITER = CrewAgent(
    role="Content Writer",
    goal="Create clear, engaging, well-structured content",
    backstory="Skilled at turning complex information into accessible prose.",
    llm_tier="fast",
)

CODER = CrewAgent(
    role="Software Engineer",
    goal="Write clean, efficient, well-tested code",
    backstory="Full-stack developer experienced in Python, TypeScript, and system design.",
    llm_tier="smart",
    tools=["code_executor", "file_ops"],
)

ANALYST = CrewAgent(
    role="Data Analyst",
    goal="Extract actionable insights from data and present clear conclusions",
    backstory="Expert in statistical analysis, data visualization, and business intelligence.",
    llm_tier="reasoning",
)

PLANNER = CrewAgent(
    role="Project Manager",
    goal="Break complex projects into actionable tasks with clear priorities",
    backstory="Experienced in agile methodologies and cross-team coordination.",
    llm_tier="smart",
)
