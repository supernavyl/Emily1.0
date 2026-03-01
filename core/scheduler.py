"""
Emily Priority Task Scheduler.

A min-heap asyncio priority queue that accepts tasks at 5 priority levels
(P0 Emergency → P4 Idle) and dispatches them to registered worker coroutines.

Workers run in their own asyncio Tasks. The scheduler enforces a concurrency
cap per priority tier to prevent lower-priority work from starving higher-priority
work during resource contention.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from core.bus import Priority
from observability.logger import get_logger
from observability.metrics import AGENT_QUEUE_DEPTH

log = get_logger(__name__)

WorkerFn = Callable[..., Awaitable[Any]]


@dataclass(order=True)
class ScheduledTask:
    """A prioritized task waiting for dispatch."""

    priority: int
    enqueue_time: float = field(compare=False)
    task_id: str = field(compare=False)
    fn: WorkerFn = field(compare=False)
    args: tuple[Any, ...] = field(compare=False, default_factory=tuple)
    kwargs: dict[str, Any] = field(compare=False, default_factory=dict)
    deadline_ms: int | None = field(compare=False, default=None)


class Scheduler:
    """
    Priority queue scheduler with per-tier concurrency limits.

    Concurrency caps (default):
      P0 Emergency:  unbounded (always runs immediately)
      P1 Realtime:   8 concurrent workers
      P2 Active:     4 concurrent workers
      P3 Background: 2 concurrent workers
      P4 Idle:       1 concurrent worker
    """

    _DEFAULT_CONCURRENCY: ClassVar[dict[Priority, int]] = {
        Priority.EMERGENCY: 999,
        Priority.REALTIME: 8,
        Priority.ACTIVE: 4,
        Priority.BACKGROUND: 2,
        Priority.IDLE: 1,
    }

    def __init__(
        self,
        concurrency: dict[Priority, int] | None = None,
    ) -> None:
        """
        Args:
            concurrency: Override default per-priority concurrency limits.
        """
        self._concurrency = concurrency or dict(self._DEFAULT_CONCURRENCY)
        self._queue: asyncio.PriorityQueue[ScheduledTask] = asyncio.PriorityQueue()
        self._active: dict[Priority, int] = dict.fromkeys(Priority, 0)
        self._semaphores: dict[Priority, asyncio.Semaphore] = {
            p: asyncio.Semaphore(self._concurrency.get(p, 4)) for p in Priority
        }
        self._running = False
        self._dispatch_task: asyncio.Task[None] | None = None
        self._workers: set[asyncio.Task[None]] = set()

    async def submit(
        self,
        fn: WorkerFn,
        *args: Any,
        priority: Priority = Priority.ACTIVE,
        task_id: str | None = None,
        deadline_ms: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Submit a coroutine function for scheduled execution.

        Args:
            fn: Async callable to execute.
            *args: Positional arguments for fn.
            priority: Task priority level.
            task_id: Optional identifier; generated if not provided.
            deadline_ms: Max execution time in ms before cancellation.
            **kwargs: Keyword arguments for fn.

        Returns:
            The task_id assigned to this task.
        """
        tid = task_id or str(uuid.uuid4())
        task = ScheduledTask(
            priority=int(priority),
            enqueue_time=time.monotonic(),
            task_id=tid,
            fn=fn,
            args=args,
            kwargs=kwargs,
            deadline_ms=deadline_ms,
        )
        await self._queue.put(task)
        AGENT_QUEUE_DEPTH.inc()
        log.debug("task_queued", task_id=tid, priority=priority.name)
        return tid

    async def _run_task(self, task: ScheduledTask) -> None:
        """Execute a single task, gated by a per-priority semaphore."""
        priority = Priority(task.priority)
        sem = self._semaphores[priority]

        async with sem:
            self._active[priority] += 1
            try:
                coro = task.fn(*task.args, **task.kwargs)
                if task.deadline_ms:
                    await asyncio.wait_for(coro, timeout=task.deadline_ms / 1000)
                else:
                    await coro
            except TimeoutError:
                log.warning(
                    "task_deadline_exceeded",
                    task_id=task.task_id,
                    deadline_ms=task.deadline_ms,
                )
            except asyncio.CancelledError:
                log.debug("task_cancelled", task_id=task.task_id)
            except Exception as exc:
                log.error("task_error", task_id=task.task_id, error=str(exc), exc_info=True)
            finally:
                self._active[priority] -= 1
                AGENT_QUEUE_DEPTH.dec()

    async def _dispatch_loop(self) -> None:
        """Main loop: pull tasks from the priority queue and dispatch them."""
        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                worker = asyncio.create_task(self._run_task(task))
                self._workers.add(worker)
                worker.add_done_callback(self._workers.discard)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("scheduler_dispatch_error", error=str(exc))

    async def start(self) -> None:
        """Start the scheduler dispatch loop as a background task."""
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        log.info("scheduler_started")

    async def stop(self) -> None:
        """Stop the scheduler and cancel the dispatch task."""
        self._running = False
        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dispatch_task
            self._dispatch_task = None
        log.info("scheduler_stopped")

    def queue_depth(self) -> int:
        """Return the current number of queued tasks."""
        return self._queue.qsize()

    def active_count(self) -> dict[str, int]:
        """Return active worker counts per priority tier."""
        return {p.name: c for p, c in self._active.items()}
