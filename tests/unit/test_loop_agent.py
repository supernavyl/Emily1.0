"""Tests for LoopAgent — bus agent that runs emily-loop kernel for complex tasks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.bus import Message, Priority
from emily_loop.models import Plan, PlanStatus, Step, StepStatus


def _make_done_plan(goal: str = "test goal") -> Plan:
    from datetime import datetime, timezone

    return Plan(
        goal=goal,
        steps=[
            Step(
                id="step-001",
                action="do thing",
                expected_output="done",
                failure_conditions=[],
                rollback=None,
                depends_on=[],
                status=StepStatus.DONE,
                guard=None,
            ),
        ],
        version=1,
        created_at=datetime.now(tz=timezone.utc),
        checkpoint="step-001",
        status=PlanStatus.DONE,
    )


def _make_abandoned_plan(goal: str = "test goal") -> Plan:
    from datetime import datetime, timezone

    return Plan(
        goal=goal,
        steps=[
            Step(
                id="step-001",
                action="do thing",
                expected_output="done",
                failure_conditions=[],
                rollback=None,
                depends_on=[],
                status=StepStatus.FAILED,
                guard=None,
            ),
        ],
        version=3,
        created_at=datetime.now(tz=timezone.utc),
        checkpoint=None,
        status=PlanStatus.ABANDONED,
    )


class FakeBus:
    """Minimal mock of AgentBus."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self._handlers: dict[str, Any] = {}

    def register_handler(self, name: str, handler: Any) -> None:
        self._handlers[name] = handler

    async def send_to(self, **kwargs: Any) -> str:
        self.sent.append(kwargs)
        return "task-id"

    async def start(self) -> None:
        pass

    async def run(self) -> None:
        pass


class FakeFleet:
    def __init__(self) -> None:
        self.chat = AsyncMock()


class FakeMemory:
    def __init__(self) -> None:
        self.retrieve_context = AsyncMock(return_value=[])
        self.procedural = MagicMock()
        self.procedural.add_skill = AsyncMock()


class FakePluginRegistry:
    def all_tools(self) -> list:
        return []


@pytest.fixture
def bus() -> FakeBus:
    return FakeBus()


@pytest.fixture
def fleet() -> FakeFleet:
    return FakeFleet()


@pytest.fixture
def memory() -> FakeMemory:
    return FakeMemory()


@pytest.mark.asyncio
async def test_loop_agent_handles_loop_run(
    bus: FakeBus, fleet: FakeFleet, memory: FakeMemory, tmp_path: Path,
) -> None:
    from core.loop_integration.loop_agent import LoopAgent

    agent = LoopAgent(
        bus=bus,
        fleet=fleet,
        memory=memory,
        plugin_registry=FakePluginRegistry(),
        data_dir=tmp_path,
    )

    done_plan = _make_done_plan("build a website")

    with patch.object(agent, "_build_loop") as mock_build:
        mock_loop = AsyncMock()
        mock_loop.run.return_value = done_plan
        mock_build.return_value = mock_loop

        msg = Message(
            type="loop.run",
            payload={"task": "build a website"},
            sender="ConversationAgent",
            recipient="LoopAgent",
        )
        await agent.handle(msg)

    # Should have sent result to ConversationAgent
    assert any(
        s.get("recipient") == "ConversationAgent" and s.get("msg_type") == "text.input"
        for s in bus.sent
    )


@pytest.mark.asyncio
async def test_loop_agent_handles_planner_plan_request(
    bus: FakeBus, fleet: FakeFleet, memory: FakeMemory, tmp_path: Path,
) -> None:
    from core.loop_integration.loop_agent import LoopAgent

    agent = LoopAgent(
        bus=bus,
        fleet=fleet,
        memory=memory,
        plugin_registry=FakePluginRegistry(),
        data_dir=tmp_path,
    )

    done_plan = _make_done_plan("research topic")

    with patch.object(agent, "_build_loop") as mock_build:
        mock_loop = AsyncMock()
        mock_loop.run.return_value = done_plan
        mock_build.return_value = mock_loop

        msg = Message(
            type="planner.plan_request",
            payload={"task": "research topic"},
            sender="ConversationAgent",
            recipient="LoopAgent",
        )
        await agent.handle(msg)

    assert any(s.get("recipient") == "ConversationAgent" for s in bus.sent)


@pytest.mark.asyncio
async def test_loop_agent_abandoned_sends_partial_progress(
    bus: FakeBus, fleet: FakeFleet, memory: FakeMemory, tmp_path: Path,
) -> None:
    from core.loop_integration.loop_agent import LoopAgent

    agent = LoopAgent(
        bus=bus,
        fleet=fleet,
        memory=memory,
        plugin_registry=FakePluginRegistry(),
        data_dir=tmp_path,
    )

    abandoned_plan = _make_abandoned_plan("impossible task")

    with patch.object(agent, "_build_loop") as mock_build:
        mock_loop = AsyncMock()
        mock_loop.run.return_value = abandoned_plan
        mock_build.return_value = mock_loop

        msg = Message(
            type="loop.run",
            payload={"task": "impossible task"},
            sender="test",
            recipient="LoopAgent",
        )
        await agent.handle(msg)

    sent_payloads = [s["payload"]["text"] for s in bus.sent if "payload" in s]
    assert any("failed" in t.lower() or "abandoned" in t.lower() for t in sent_payloads)


@pytest.mark.asyncio
async def test_loop_agent_exception_falls_back_to_react(
    bus: FakeBus, fleet: FakeFleet, memory: FakeMemory, tmp_path: Path,
) -> None:
    from core.loop_integration.loop_agent import LoopAgent

    agent = LoopAgent(
        bus=bus,
        fleet=fleet,
        memory=memory,
        plugin_registry=FakePluginRegistry(),
        data_dir=tmp_path,
    )

    with patch.object(agent, "_build_loop") as mock_build:
        mock_loop = AsyncMock()
        mock_loop.run.side_effect = RuntimeError("LLM exploded")
        mock_build.return_value = mock_loop

        msg = Message(
            type="loop.run",
            payload={"task": "do something"},
            sender="test",
            recipient="LoopAgent",
        )
        await agent.handle(msg)

    # Should fall back — send original task to ConversationAgent
    assert any(
        s.get("recipient") == "ConversationAgent"
        for s in bus.sent
    )
