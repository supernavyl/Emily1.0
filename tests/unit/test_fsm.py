"""Unit tests for the SystemFSM."""

from __future__ import annotations

import pytest

from core.fsm import FSMError, SystemFSM, SystemState


@pytest.mark.asyncio
async def test_initial_state_is_idle() -> None:
    """FSM starts in IDLE state."""
    fsm = SystemFSM()
    assert fsm.state == SystemState.IDLE


@pytest.mark.asyncio
async def test_valid_transition_idle_to_listening() -> None:
    """IDLE → LISTENING is a valid transition."""
    fsm = SystemFSM()
    await fsm.transition(SystemState.LISTENING)
    assert fsm.state == SystemState.LISTENING


@pytest.mark.asyncio
async def test_invalid_transition_raises() -> None:
    """IDLE → RESPONDING is invalid and raises FSMError."""
    fsm = SystemFSM()
    with pytest.raises(FSMError):
        await fsm.transition(SystemState.RESPONDING)


@pytest.mark.asyncio
async def test_full_conversation_cycle() -> None:
    """A complete conversation cycle transitions cleanly."""
    fsm = SystemFSM()
    await fsm.transition(SystemState.LISTENING)
    await fsm.transition(SystemState.PROCESSING)
    await fsm.transition(SystemState.RESPONDING)
    await fsm.transition(SystemState.IDLE)
    assert fsm.state == SystemState.IDLE


@pytest.mark.asyncio
async def test_observer_called_on_transition() -> None:
    """Observers are called with correct old/new states."""
    fsm = SystemFSM()
    calls: list[tuple[SystemState, SystemState]] = []

    async def observer(old: SystemState, new: SystemState) -> None:
        calls.append((old, new))

    fsm.on_transition(observer)
    await fsm.transition(SystemState.LISTENING)
    assert len(calls) == 1
    assert calls[0] == (SystemState.IDLE, SystemState.LISTENING)


@pytest.mark.asyncio
async def test_force_transition_bypasses_validation() -> None:
    """force_transition can make any transition."""
    fsm = SystemFSM()
    await fsm.force_transition(SystemState.RESPONDING)
    assert fsm.state == SystemState.RESPONDING


@pytest.mark.asyncio
async def test_history_records_transitions() -> None:
    """History records all valid transitions."""
    fsm = SystemFSM()
    await fsm.transition(SystemState.LISTENING)
    await fsm.transition(SystemState.PROCESSING)
    hist = fsm.history()
    assert ("IDLE", "LISTENING") in hist
    assert ("LISTENING", "PROCESSING") in hist


def test_is_in_returns_true_for_current_state() -> None:
    """is_in() returns True when current state is in the given set."""
    fsm = SystemFSM()
    assert fsm.is_in(SystemState.IDLE)
    assert not fsm.is_in(SystemState.PROCESSING)
