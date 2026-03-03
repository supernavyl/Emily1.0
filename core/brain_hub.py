"""
Central event hub for Emily's Brain Dashboard.

BrainEventHub collects events from every subsystem (LLM, agents, memory,
perception, FSM, logs) and delivers them to the PySide6 GUI via Qt signals.
The hub lives in the asyncio thread; signals cross into the Qt main thread
automatically through Qt's queued connection mechanism.

When no GUI is attached (headless mode), the hub is never instantiated and
all subsystem taps are no-ops (they check ``if hub is not None``).
"""

from __future__ import annotations

import collections
import contextlib
import threading
import time
from typing import Any

_hub_instance: BrainEventHub | None = None
_hub_lock = threading.Lock()

_MAX_RING = 1000
_LOG_RATE_LIMIT = 50  # max log events per second


def get_brain_hub() -> BrainEventHub | None:
    """Return the global hub singleton, or None in headless mode."""
    return _hub_instance


def set_brain_hub(hub: BrainEventHub) -> None:
    """Install the global hub singleton (called once at startup)."""
    global _hub_instance
    with _hub_lock:
        _hub_instance = hub


class BrainEventHub:
    """
    Collects events from all Emily subsystems and broadcasts them via Qt signals.

    Thread-safe: ``emit_sync`` can be called from any thread (used by the
    structlog processor).  ``emit`` is the async-friendly variant for use
    inside the asyncio event loop.

    Attributes:
        signals: A ``_BrainSignals`` QObject whose signals are safe to connect
                 from the Qt main thread.
    """

    def __init__(self) -> None:
        self._ring: collections.deque[dict[str, Any]] = collections.deque(maxlen=_MAX_RING)
        self._lock = threading.Lock()
        self._log_timestamps: collections.deque[float] = collections.deque(maxlen=_LOG_RATE_LIMIT)
        self._signals: Any = None  # set by attach_signals() — primary
        self._extra_signals: list[Any] = []
        self._recorders: list[Any] = []  # persistent recorder callbacks

    def attach_recorder(self, callback: Any) -> None:
        """Attach a persistent event recorder callback.

        The callback receives the event dict for every ``emit_sync`` call
        (including events that pass log rate-limiting).  Used by
        :class:`observability.event_recorder.EventRecorder`.

        Args:
            callback: ``Callable[[dict], None]`` — must be thread-safe.
        """
        self._recorders.append(callback)

    def attach_signals(self, signals: Any) -> None:
        """
        Attach a ``_BrainSignals`` QObject for cross-thread delivery.

        Called from the GUI thread during dashboard startup.

        Args:
            signals: QObject with Qt signals (event_emitted, llm_event, etc.).
        """
        if self._signals is None:
            self._signals = signals
        else:
            self._extra_signals.append(signals)

    def backfill(self) -> list[dict[str, Any]]:
        """
        Return a snapshot of the ring buffer for late-joining panels.

        Returns:
            List of recent events (oldest first).
        """
        with self._lock:
            return list(self._ring)

    async def emit(self, cat: str, kind: str, data: dict[str, Any] | None = None) -> None:
        """
        Emit a brain event (async variant).

        Args:
            cat: Event category (llm, react, agent, perception, fsm, memory, log).
            kind: Event kind within the category (e.g., token, state_change).
            data: Arbitrary event payload.
        """
        self.emit_sync(cat, kind, data)

    def emit_sync(self, cat: str, kind: str, data: dict[str, Any] | None = None) -> None:
        """
        Emit a brain event (thread-safe, synchronous).

        Args:
            cat: Event category.
            kind: Event kind.
            data: Arbitrary event payload.
        """
        if cat == "log" and not self._allow_log():
            return

        event: dict[str, Any] = {
            "ts": time.time(),
            "cat": cat,
            "kind": kind,
            "data": data or {},
        }

        with self._lock:
            self._ring.append(event)

        # Persistent recorders (e.g. EventRecorder for replay debugger)
        for recorder in self._recorders:
            with contextlib.suppress(Exception):
                recorder(event)

        all_signals = []
        if self._signals is not None:
            all_signals.append(self._signals)
        all_signals.extend(self._extra_signals)
        if not all_signals:
            return

        for signals_obj in all_signals:
            try:
                ev_sig = getattr(signals_obj, "event_emitted", None)
                if ev_sig is not None:
                    ev_sig.emit(event)
                cat_sig = getattr(signals_obj, f"{cat}_event", None)
                if cat_sig is not None:
                    cat_sig.emit(event)
            except RuntimeError:
                pass

    def _allow_log(self) -> bool:
        """Rate-limit log events to avoid flooding the UI."""
        now = time.time()
        with self._lock:
            if len(self._log_timestamps) < _LOG_RATE_LIMIT:
                self._log_timestamps.append(now)
                return True
            oldest = self._log_timestamps[0]
            if now - oldest >= 1.0:
                self._log_timestamps.append(now)
                return True
        return False
