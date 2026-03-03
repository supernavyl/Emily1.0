"""
Perception Fusion Bus Router.

This module ties together all sensory streams and routes typed perception
events onto the ZeroMQ PerceptionBus for the attention router to consume.

Each perception source registers a producer function that generates events.
The FusionRouter runs all producers concurrently and forwards their output.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

from core.bus import PerceptionBus, Priority
from observability.logger import get_logger

log = get_logger(__name__)

PerceptionProducer = Callable[[], AsyncIterator[tuple[str, dict, Priority]]]


class FusionRouter:
    """
    Aggregates all perception producers and routes events to the PerceptionBus.

    Producers are registered at startup. Each runs as an independent async task.
    Failures in one producer don't affect others.
    """

    def __init__(self, bus: PerceptionBus) -> None:
        """
        Args:
            bus: The shared PerceptionBus instance.
        """
        self._bus = bus
        self._producers: list[PerceptionProducer] = []
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

    def register(self, producer: PerceptionProducer) -> None:
        """
        Register a perception producer coroutine generator.

        Args:
            producer: Callable that returns an async generator yielding
                      (event_type, payload, priority) tuples.
        """
        self._producers.append(producer)
        log.debug("perception_producer_registered", producer=producer.__name__)

    async def _run_producer(self, producer: PerceptionProducer) -> None:
        """Run a single producer, forwarding its events to the bus."""
        name = producer.__name__
        while self._running:
            try:
                async for event_type, payload, priority in producer():
                    if not self._running:
                        return
                    await self._bus.publish(event_type, payload, priority)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.error("perception_producer_error", producer=name, error=str(exc))
                await asyncio.sleep(1.0)  # Back off before restarting

    async def start(self) -> None:
        """Start all registered producers as background tasks."""
        self._running = True
        for producer in self._producers:
            task = asyncio.create_task(
                self._run_producer(producer),
                name=f"perception_{producer.__name__}",
            )
            self._tasks.append(task)
        log.info("fusion_router_started", n_producers=len(self._producers))

    def stop(self) -> None:
        """Stop all producer tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        log.info("fusion_router_stopped")
