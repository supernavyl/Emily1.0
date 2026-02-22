"""
Emily Finite State Machine.

Tracks the system's high-level operational state and enforces valid
state transitions. All state changes are logged and observable.

States:
  IDLE         → waiting for input, memory consolidation may run
  LISTENING    → wake word detected, VAD active
  PROCESSING   → STT + LLM inference in progress
  RESPONDING   → TTS synthesis and playback
  TOOL_USE     → executing one or more tools
  REFLECTING   → ReflectionAgent consolidation cycle
  ERROR        → unrecoverable error, waiting for reset
  SHUTDOWN     → graceful shutdown in progress
"""

from __future__ import annotations

import asyncio
from enum import Enum, auto
from typing import Callable, Coroutine, Any

from observability.logger import get_logger

log = get_logger(__name__)

StateChangeCallback = Callable[["SystemState", "SystemState"], Coroutine[Any, Any, None]]


class SystemState(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    RESPONDING = auto()
    TOOL_USE = auto()
    REFLECTING = auto()
    ERROR = auto()
    SHUTDOWN = auto()


_VALID_TRANSITIONS: dict[SystemState, set[SystemState]] = {
    SystemState.IDLE: {
        SystemState.LISTENING,
        SystemState.PROCESSING,
        SystemState.REFLECTING,
        SystemState.SHUTDOWN,
        SystemState.ERROR,
    },
    SystemState.LISTENING: {
        SystemState.PROCESSING,
        SystemState.IDLE,
        SystemState.ERROR,
        SystemState.SHUTDOWN,
    },
    SystemState.PROCESSING: {
        SystemState.RESPONDING,
        SystemState.TOOL_USE,
        SystemState.IDLE,
        SystemState.ERROR,
        SystemState.SHUTDOWN,
    },
    SystemState.RESPONDING: {
        SystemState.IDLE,
        SystemState.LISTENING,
        SystemState.ERROR,
        SystemState.SHUTDOWN,
    },
    SystemState.TOOL_USE: {
        SystemState.PROCESSING,
        SystemState.RESPONDING,
        SystemState.IDLE,
        SystemState.ERROR,
        SystemState.SHUTDOWN,
    },
    SystemState.REFLECTING: {
        SystemState.IDLE,
        SystemState.ERROR,
        SystemState.SHUTDOWN,
    },
    SystemState.ERROR: {
        SystemState.IDLE,
        SystemState.SHUTDOWN,
    },
    SystemState.SHUTDOWN: set(),
}


class FSMError(Exception):
    """Raised when an invalid state transition is attempted."""


class SystemFSM:
    """
    Thread-safe finite state machine for Emily's operational state.

    Observers registered via `on_transition` are called asynchronously
    after every valid state change.
    """

    def __init__(self, initial: SystemState = SystemState.IDLE) -> None:
        """
        Args:
            initial: Starting state. Defaults to IDLE.
        """
        self._state = initial
        self._lock = asyncio.Lock()
        self._observers: list[StateChangeCallback] = []
        self._history: list[tuple[SystemState, SystemState]] = []
        log.info("fsm_initialized", state=initial.name)

    @property
    def state(self) -> SystemState:
        """Current system state (read-only)."""
        return self._state

    def on_transition(self, callback: StateChangeCallback) -> None:
        """
        Register an async callback invoked on every state transition.

        Args:
            callback: async callable(old_state, new_state) → None
        """
        self._observers.append(callback)

    async def transition(self, new_state: SystemState) -> None:
        """
        Attempt a state transition.

        Args:
            new_state: The desired next state.

        Raises:
            FSMError: If the transition is not permitted.
        """
        async with self._lock:
            allowed = _VALID_TRANSITIONS.get(self._state, set())
            if new_state not in allowed:
                raise FSMError(
                    f"Invalid transition: {self._state.name} → {new_state.name}. "
                    f"Allowed: {[s.name for s in allowed]}"
                )
            old_state = self._state
            self._state = new_state
            self._history.append((old_state, new_state))
            log.info("fsm_transition", from_state=old_state.name, to_state=new_state.name)

        for observer in self._observers:
            try:
                await observer(old_state, new_state)
            except Exception as exc:
                log.error("fsm_observer_error", error=str(exc))

    async def force_transition(self, new_state: SystemState) -> None:
        """
        Force a state transition, bypassing validation (emergency use only).

        Args:
            new_state: Target state regardless of current state.
        """
        async with self._lock:
            old_state = self._state
            self._state = new_state
            self._history.append((old_state, new_state))
            log.warning(
                "fsm_force_transition",
                from_state=old_state.name,
                to_state=new_state.name,
            )

        for observer in self._observers:
            try:
                await observer(old_state, new_state)
            except Exception as exc:
                log.error("fsm_observer_error", error=str(exc))

    def is_in(self, *states: SystemState) -> bool:
        """Return True if the current state is any of the given states."""
        return self._state in states

    def history(self, n: int = 20) -> list[tuple[str, str]]:
        """
        Return the last N state transitions as (from, to) name pairs.

        Args:
            n: Maximum number of transitions to return.
        """
        return [(a.name, b.name) for a, b in self._history[-n:]]
