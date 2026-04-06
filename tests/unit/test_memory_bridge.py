"""Tests for MemoryBridge — bidirectional sync between Loop's FailureDB and Emily's memory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from emily_loop.models import FailureCategory, FailurePattern, FailureType


def _make_pattern(pattern_id: str = "fail-0001", trigger: str = "timeout on shell") -> FailurePattern:
    now = datetime.now(tz=timezone.utc)
    return FailurePattern(
        id=pattern_id,
        trigger=trigger,
        category=FailureCategory.TIMEOUT,
        failure_type=FailureType.TRANSIENT,
        what_happened="shell command timed out",
        root_cause="slow network",
        prevention="add timeout flag",
        severity=3,
        occurrences=1,
        first_seen=now,
        last_seen=now,
        step_context="run shell command",
    )


class FakeMemoryManager:
    """Minimal mock of MemoryManager for bridge tests."""

    def __init__(self) -> None:
        self.retrieve_context = AsyncMock(return_value=[])
        self.procedural = MagicMock()
        self.procedural.add_skill = AsyncMock()


class FakeFailureDB:
    """Minimal mock of FailureDB for bridge tests."""

    def __init__(self, patterns: list[FailurePattern] | None = None) -> None:
        self._patterns = patterns or []

    async def all(self) -> list[FailurePattern]:
        return self._patterns


@pytest.fixture
def fake_memory() -> FakeMemoryManager:
    return FakeMemoryManager()


@pytest.mark.asyncio
async def test_enrich_goal_no_context(fake_memory: FakeMemoryManager) -> None:
    from core.loop_integration.memory_bridge import MemoryBridge

    bridge = MemoryBridge(fake_memory, FakeFailureDB())

    result = await bridge.enrich_goal("build a website")

    assert result == "build a website"


@pytest.mark.asyncio
async def test_enrich_goal_with_context(fake_memory: FakeMemoryManager) -> None:
    from core.loop_integration.memory_bridge import MemoryBridge

    fake_memory.retrieve_context.return_value = [
        {"content": "User prefers React", "source": "episodic", "score": 0.9},
        {"content": "Last project used Next.js", "source": "episodic", "score": 0.8},
    ]
    bridge = MemoryBridge(fake_memory, FakeFailureDB())

    result = await bridge.enrich_goal("build a website")

    assert "build a website" in result
    assert "User prefers React" in result
    assert "Last project used Next.js" in result


@pytest.mark.asyncio
async def test_sync_failures_stores_new_patterns(fake_memory: FakeMemoryManager) -> None:
    from core.loop_integration.memory_bridge import MemoryBridge

    pattern = _make_pattern()
    bridge = MemoryBridge(fake_memory, FakeFailureDB([pattern]))

    count = await bridge.sync_failures()

    assert count == 1
    fake_memory.procedural.add_skill.assert_called_once()
    call_kwargs = fake_memory.procedural.add_skill.call_args.kwargs
    assert call_kwargs["name"] == "failure:fail-0001"
    assert "TIMEOUT" in call_kwargs["description"]


@pytest.mark.asyncio
async def test_sync_failures_skips_already_synced(fake_memory: FakeMemoryManager) -> None:
    from core.loop_integration.memory_bridge import MemoryBridge

    pattern = _make_pattern()
    bridge = MemoryBridge(fake_memory, FakeFailureDB([pattern]))

    await bridge.sync_failures()  # First sync
    count = await bridge.sync_failures()  # Second sync — nothing new

    assert count == 0
    assert fake_memory.procedural.add_skill.call_count == 1


@pytest.mark.asyncio
async def test_sync_failures_picks_up_new_patterns(fake_memory: FakeMemoryManager) -> None:
    from core.loop_integration.memory_bridge import MemoryBridge

    p1 = _make_pattern("fail-0001", "timeout")
    db = FakeFailureDB([p1])
    bridge = MemoryBridge(fake_memory, db)

    await bridge.sync_failures()  # Syncs p1

    p2 = _make_pattern("fail-0002", "permission denied")
    db._patterns = [p1, p2]  # p2 is new

    count = await bridge.sync_failures()

    assert count == 1
    assert fake_memory.procedural.add_skill.call_count == 2
