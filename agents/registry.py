"""
Agent registry and lifecycle manager.

All agents are instantiated and registered here at startup.
The registry holds references to all running agents and provides
a unified interface for starting, stopping, and sending messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agents.conversation import ConversationAgent
from agents.memory_agent import MemoryAgent
from agents.planner import PlannerAgent
from agents.reflection import ReflectionAgent
from observability.logger import get_logger

if TYPE_CHECKING:
    from agents.base import BaseAgent
    from core.bus import AgentBus
    from llm.fleet import LLMFleet
    from memory.manager import MemoryManager

log = get_logger(__name__)


class AgentRegistry:
    """
    Manages instantiation, registration, and lifecycle of all Emily agents.

    Agents that require additional specialist modules (ResearchAgent, CodeAgent,
    CriticAgent, ToolBuilderAgent, MonitorAgent) are imported lazily to avoid
    circular imports and allow optional dependencies.
    """

    def __init__(
        self,
        bus: AgentBus,
        fleet: LLMFleet,
        memory: MemoryManager,
    ) -> None:
        """
        Args:
            bus: Shared AgentBus.
            fleet: LLM fleet.
            memory: Unified memory manager.
        """
        self._bus = bus
        self._fleet = fleet
        self._memory = memory
        self._agents: dict[str, BaseAgent] = {}

    def _build_core_agents(self) -> list[BaseAgent]:
        """Instantiate all core agents."""
        return [
            ConversationAgent(self._bus, self._fleet, self._memory),
            PlannerAgent(self._bus, self._fleet, self._memory),
            MemoryAgent(self._bus, self._fleet, self._memory),
            ReflectionAgent(self._bus, self._fleet, self._memory),
        ]

    def _build_specialist_agents(self) -> list[BaseAgent]:
        """Instantiate specialist agents (imported lazily)."""
        agents: list[BaseAgent] = []
        optional_imports = [
            ("agents.research", "ResearchAgent"),
            ("agents.code_agent", "CodeAgent"),
            ("agents.monitor", "MonitorAgent"),
            ("agents.tool_builder", "ToolBuilderAgent"),
            ("agents.onboarding", "OnboardingAgent"),
        ]
        for module_path, class_name in optional_imports:
            try:
                import importlib

                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
                agents.append(cls(self._bus, self._fleet, self._memory))
            except (ImportError, AttributeError) as exc:
                log.warning("specialist_agent_not_loaded", agent=class_name, error=str(exc))
        return agents

    async def start_all(self) -> None:
        """Instantiate and start all agents."""
        all_agents = self._build_core_agents() + self._build_specialist_agents()

        for agent in all_agents:
            self._agents[agent.name] = agent
            await agent.start()
            log.info("agent_registered", name=agent.name)

        log.info("all_agents_started", count=len(self._agents))

    async def stop_all(self) -> None:
        """Stop all running agents."""
        for agent in self._agents.values():
            await agent.stop()
        self._agents.clear()
        log.info("all_agents_stopped")

    def get(self, name: str) -> BaseAgent | None:
        """Return a registered agent by name."""
        return self._agents.get(name)

    @property
    def agent_names(self) -> list[str]:
        """Names of all registered agents."""
        return list(self._agents.keys())
