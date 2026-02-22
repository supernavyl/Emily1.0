"""
Tier 1: Sensory Buffer — RAM ring buffer for raw perception events.

Holds the most recent N perception events in memory. Events older than
the buffer capacity are automatically discarded. No disk persistence.

Purpose: prevent data loss during high-throughput perception periods
         (e.g., rapid speech segments during fast conversation).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class PerceptionEvent:
    """A raw perception event in the sensory buffer."""

    event_type: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    modality: str = "unknown"


class SensoryBuffer:
    """
    Fixed-capacity ring buffer for perception events.

    Thread-safe for single-producer / single-consumer use within asyncio.
    Overflow drops the oldest event.
    """

    def __init__(self, capacity: int = 1000) -> None:
        """
        Args:
            capacity: Maximum number of events to hold.
        """
        self._buffer: deque[PerceptionEvent] = deque(maxlen=capacity)
        self._capacity = capacity

    def push(self, event: PerceptionEvent) -> None:
        """
        Add an event to the buffer.

        If the buffer is at capacity, the oldest event is silently dropped.

        Args:
            event: The perception event to add.
        """
        self._buffer.append(event)

    def drain(self, n: int | None = None) -> list[PerceptionEvent]:
        """
        Remove and return up to n events from the buffer (FIFO).

        Args:
            n: Max events to drain. None = drain all.

        Returns:
            List of PerceptionEvent objects.
        """
        if n is None:
            events = list(self._buffer)
            self._buffer.clear()
            return events
        events = []
        for _ in range(min(n, len(self._buffer))):
            events.append(self._buffer.popleft())
        return events

    def peek(self, n: int = 10) -> list[PerceptionEvent]:
        """
        Return the n most recent events without removing them.

        Args:
            n: Number of recent events to return.

        Returns:
            List of the n most recent PerceptionEvent objects.
        """
        items = list(self._buffer)
        return items[-n:]

    def events_since(self, timestamp: float) -> list[PerceptionEvent]:
        """
        Return all events that occurred after the given timestamp.

        Args:
            timestamp: UTC epoch timestamp.

        Returns:
            List of matching PerceptionEvent objects.
        """
        return [e for e in self._buffer if e.timestamp > timestamp]

    @property
    def size(self) -> int:
        """Current number of events in the buffer."""
        return len(self._buffer)

    @property
    def capacity(self) -> int:
        """Maximum buffer capacity."""
        return self._capacity

    def clear(self) -> None:
        """Discard all buffered events."""
        self._buffer.clear()
