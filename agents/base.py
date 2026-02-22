"""
BaseAgent abstract class for all Emily agents.

All agents share:
- A name and description
- Access to the AgentBus for inter-agent communication
- Access to the LLM fleet for inference
- A lifecycle: start() → handle_message() loop → stop()
- Heartbeat emission for the monitor

Agents are registered in agents/registry.py and discovered at startup.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any

from core.bus import AgentBus, Message, Priority
from llm.fleet import LLMFleet
from memory.manager import MemoryManager
from observability.logger import get_logger
from observability.metrics import ACTIVE_AGENTS, AGENT_TASK_LATENCY

log = get_logger(__name__)


class BaseAgent(ABC):
    """
    Abstract base for all Emily cognitive agents.

    Subclasses implement handle() for their specific message types.
    All agents run as asyncio Tasks and communicate via AgentBus.
    """

    name: str = ""
    description: str = ""

    def __init__(
        self,
        bus: AgentBus,
        fleet: LLMFleet,
        memory: MemoryManager,
    ) -> None:
        """
        Args:
            bus: Shared AgentBus for inter-agent communication.
            fleet: LLM fleet for inference requests.
            memory: Unified memory manager.
        """
        self._bus = bus
        self._fleet = fleet
        self._memory = memory
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._log = get_logger(f"agents.{self.name}")

    async def start(self) -> None:
        """Register with the bus and start the message handling loop."""
        self._running = True
        self._bus.register_handler(self.name, self._dispatch)
        self._task = asyncio.create_task(self._heartbeat_loop(), name=f"{self.name}_heartbeat")
        ACTIVE_AGENTS.inc()
        self._log.info("agent_started")

    async def stop(self) -> None:
        """Shut down the agent gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
        ACTIVE_AGENTS.dec()
        self._log.info("agent_stopped")

    async def _dispatch(self, message: Message) -> None:
        """
        Dispatch an incoming message to the handle() method with timing.

        Args:
            message: Incoming Message from the AgentBus.
        """
        t0 = time.monotonic()
        try:
            await self.handle(message)
        except Exception as exc:
            self._log.error(
                "agent_handle_error",
                msg_type=message.type,
                error=str(exc),
                exc_info=True,
            )
        finally:
            elapsed = time.monotonic() - t0
            AGENT_TASK_LATENCY.labels(agent_name=self.name).observe(elapsed)

    @abstractmethod
    async def handle(self, message: Message) -> None:
        """
        Handle an incoming message.

        Args:
            message: The incoming Message to process.
        """
        ...

    async def _heartbeat_loop(self) -> None:
        """Emit periodic heartbeat messages so MonitorAgent can track liveness."""
        while self._running:
            await asyncio.sleep(30)
            await self._bus.send_to(
                recipient="MonitorAgent",
                msg_type="agent.heartbeat",
                payload={"agent": self.name, "timestamp": time.time()},
                sender=self.name,
                priority=Priority.IDLE,
            )

    async def send(
        self,
        recipient: str,
        msg_type: str,
        payload: dict[str, Any],
        priority: Priority = Priority.ACTIVE,
        task_id: str | None = None,
    ) -> str:
        """
        Send a message to another agent.

        Args:
            recipient: Target agent name.
            msg_type: Message type string.
            payload: Message payload.
            priority: Message priority.
            task_id: Optional task correlation ID.

        Returns:
            Generated task_id.
        """
        return await self._bus.send_to(
            recipient=recipient,
            msg_type=msg_type,
            payload=payload,
            sender=self.name,
            priority=priority,
            task_id=task_id,
        )
