"""Bridge between PySide6's event loop and asyncio for non-blocking calls.

``AsyncRunner`` spins up a dedicated asyncio event loop on a ``QThread`` so that
coroutines (e.g. database queries, LLM streaming) never block the Qt UI thread.
Results are delivered back to the main thread via Qt signals.

Usage::

    runner = AsyncRunner()
    runner.start()

    # One-shot coroutine — result arrives on ``result_ready``
    token = runner.submit(db.get_all_conversations())
    runner.result_ready.connect(lambda tok, val: ...)

    # Streaming async iterator — chunks arrive on ``chunk_received``
    token = runner.submit_streaming(my_async_gen_coro())
    runner.chunk_received.connect(lambda tok, val: ...)
    runner.stream_done.connect(lambda tok: ...)

    # On shutdown
    runner.shutdown()
"""

from __future__ import annotations

import asyncio
import traceback
import uuid
from typing import Any, Coroutine

from PySide6.QtCore import QThread, Signal, QObject


class _Signals(QObject):
    """Carrier for cross-thread Qt signals (must inherit QObject)."""

    result_ready = Signal(str, object)   # (token, result)
    error_occurred = Signal(str, str)    # (token, traceback_str)
    chunk_received = Signal(str, object) # (token, chunk)
    stream_done = Signal(str)            # (token,)
    loop_ready = Signal()                # emitted when event loop is running


class AsyncRunner(QThread):
    """Background thread owning a private asyncio event loop.

    Coroutines are scheduled via :meth:`submit` and results/errors
    emitted on the Qt signal thread.  Streaming async iterators are
    scheduled via :meth:`submit_streaming`.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._signals = _Signals()
        self._started_event = asyncio.Event()
        self._active_tasks: dict[str, asyncio.Task[None]] = {}

    # Expose signals as properties so callers don't need to know about _Signals
    @property
    def result_ready(self) -> Signal:
        """Emitted with ``(token, result)`` when a coroutine completes."""
        return self._signals.result_ready

    @property
    def error_occurred(self) -> Signal:
        """Emitted with ``(token, traceback_str)`` when a coroutine raises."""
        return self._signals.error_occurred

    @property
    def chunk_received(self) -> Signal:
        """Emitted with ``(token, chunk)`` for each item from a streaming async iterator."""
        return self._signals.chunk_received

    @property
    def stream_done(self) -> Signal:
        """Emitted with ``(token,)`` when a streaming iterator is exhausted."""
        return self._signals.stream_done

    @property
    def loop_ready(self) -> Signal:
        """Emitted when the background event loop is running and accept submissions."""
        return self._signals.loop_ready

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Create and run the asyncio event loop (called on the QThread)."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._signals.loop_ready.emit()
        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()
            self._loop = None

    # ------------------------------------------------------------------
    # Public API (called from the main Qt thread)
    # ------------------------------------------------------------------

    def _require_loop(self) -> asyncio.AbstractEventLoop:
        """Return the running loop or raise."""
        if self._loop is None or self._loop.is_closed():
            raise RuntimeError("AsyncRunner loop is not running — call start() first")
        return self._loop

    def submit(self, coro: Coroutine[Any, Any, Any]) -> str:
        """Schedule *coro* on the background loop.  Returns a unique token.

        Connect to :attr:`result_ready` / :attr:`error_occurred` using the
        token to match responses.
        """
        loop = self._require_loop()
        token = uuid.uuid4().hex

        async def _wrapper() -> None:
            try:
                result = await coro
                self._signals.result_ready.emit(token, result)
            except Exception:
                self._signals.error_occurred.emit(token, traceback.format_exc())

        asyncio.run_coroutine_threadsafe(_wrapper(), loop)
        return token

    def submit_streaming(self, coro: Coroutine[Any, Any, Any]) -> str:
        """Schedule an async-iterator-producing coroutine on the background loop.

        The coroutine should be an ``async for``-able object.  Each yielded
        item is emitted on :attr:`chunk_received`.  When the iterator is
        exhausted, :attr:`stream_done` fires.  Errors emit on
        :attr:`error_occurred`.

        Returns a unique token that identifies this stream.
        """
        loop = self._require_loop()
        token = uuid.uuid4().hex

        async def _wrapper() -> None:
            try:
                async for item in coro:  # type: ignore[union-attr]
                    self._signals.chunk_received.emit(token, item)
                self._signals.stream_done.emit(token)
            except Exception:
                self._signals.error_occurred.emit(token, traceback.format_exc())
            finally:
                self._active_tasks.pop(token, None)

        future = asyncio.run_coroutine_threadsafe(_wrapper(), loop)
        task_placeholder = future  # keep a reference so it can be cancelled
        self._active_tasks[token] = task_placeholder  # type: ignore[assignment]
        return token

    def cancel_stream(self, token: str) -> None:
        """Cancel a running streaming task by token.

        Args:
            token: The token returned by :meth:`submit_streaming`.
        """
        future = self._active_tasks.pop(token, None)
        if future is not None:
            future.cancel()

    def shutdown(self) -> None:
        """Stop the background loop and wait for the thread to finish."""
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.wait(5000)
