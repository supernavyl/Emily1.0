"""Interruption handling for barge-in support during voice conversations."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

T = TypeVar("T")


class InterruptionHandler:
    """Manages interruption signaling for the voice pipeline.

    When the user starts speaking while the assistant is responding (barge-in),
    the conversation loop sets the interrupt event. Any stream wrapped with
    ``wrap_stream`` will then raise ``asyncio.CancelledError`` on the next
    iteration, allowing the pipeline to abort gracefully.
    """

    def __init__(self) -> None:
        self._interrupt_event = asyncio.Event()

    @property
    def interrupt_event(self) -> asyncio.Event:
        """The underlying asyncio Event."""
        return self._interrupt_event

    def signal_interrupt(self) -> None:
        """Signal that an interruption has occurred."""
        if not self._interrupt_event.is_set():
            logger.info("Interruption signalled.")
        self._interrupt_event.set()

    def clear(self) -> None:
        """Clear the interruption flag."""
        self._interrupt_event.clear()

    def is_interrupted(self) -> bool:
        """Return True if the interrupt flag is currently set."""
        return self._interrupt_event.is_set()

    async def wrap_stream(self, stream: AsyncIterator[T]) -> AsyncIterator[T]:
        """Wrap an async iterator so it stops when interrupted.

        Yields items from *stream* until either the stream is exhausted or
        ``signal_interrupt()`` is called, in which case
        ``asyncio.CancelledError`` is raised.
        """
        async for item in stream:
            if self._interrupt_event.is_set():
                logger.debug("Stream interrupted — aborting iteration.")
                raise asyncio.CancelledError("Interrupted by user speech")
            yield item
