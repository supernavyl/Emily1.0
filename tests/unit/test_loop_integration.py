"""Integration test — LoopAgent + FleetAdapter + ToolBridge + FailureDB end-to-end."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.bus import Message, Priority
from emily_loop.models import PlanStatus


class FakeBus:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_to(self, **kwargs: Any) -> str:
        self.sent.append(kwargs)
        return "task-id"

    def register_handler(self, name: str, handler: Any) -> None:
        pass


class FakeCompletionResult:
    def __init__(self, content: str) -> None:
        self.content = content
        self.model = "test"
        self.total_tokens = 10
        self.prompt_tokens = 5
        self.latency_ms = 100.0


class FakeFleet:
    """Fleet that returns a plan then step observations."""

    def __init__(self, plan_json: dict[str, Any]) -> None:
        self._call_count = 0
        self._plan_json = plan_json

    async def chat(self, **kwargs: Any) -> FakeCompletionResult:
        self._call_count += 1
        if self._call_count == 1:
            # First call: planner generates plan
            return FakeCompletionResult(json.dumps(self._plan_json))
        # Subsequent calls: failure analysis (shouldn't happen in success path)
        return FakeCompletionResult('{"failure_type": "TRANSIENT"}')


class FakeMemory:
    def __init__(self) -> None:
        self.retrieve_context = AsyncMock(return_value=[])
        self.procedural = MagicMock()
        self.procedural.add_skill = AsyncMock()


class FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = f"Fake {name}"
        self.parameters: dict[str, Any] = {}
        self.requires_approval = False

    async def safe_execute(self, params: Any, ctx: Any) -> Any:
        from plugins.base import ToolResult

        return ToolResult(success=True, output=f"executed {self.name}", error=None, execution_time_ms=10.0)


class FakePluginRegistry:
    def __init__(self) -> None:
        self._tools = [FakeTool("shell"), FakeTool("read_file")]

    def all_tools(self) -> list[FakeTool]:
        return self._tools


@pytest.mark.asyncio
async def test_full_loop_agent_execution(tmp_path: Path) -> None:
    """End-to-end: LoopAgent receives task, Loop plans + executes, result sent to ConversationAgent."""
    plan_json = {
        "steps": [
            {
                "id": "step-001",
                "action": 'shell: {"cmd": "echo hello"}',
                "expected_output": "hello",
                "failure_conditions": [],
                "rollback": None,
                "depends_on": [],
                "guard": None,
            },
            {
                "id": "step-002",
                "action": 'read_file: {"path": "/tmp/test.txt"}',
                "expected_output": "file contents",
                "failure_conditions": [],
                "rollback": None,
                "depends_on": ["step-001"],
                "guard": None,
            },
        ]
    }

    bus = FakeBus()
    fleet = FakeFleet(plan_json)
    memory = FakeMemory()
    registry = FakePluginRegistry()

    from emily_loop.loop import LoopConfig

    from core.loop_integration.loop_agent import LoopAgent

    agent = LoopAgent(
        bus=bus,
        fleet=fleet,
        memory=memory,
        plugin_registry=registry,
        data_dir=tmp_path,
        loop_config=LoopConfig(replan_cooldown=0.0),
    )
    await agent.start()

    msg = Message(
        type="loop.run",
        payload={"task": "create and read a file"},
        sender="ConversationAgent",
        recipient="LoopAgent",
    )
    await agent.handle(msg)

    # Verify result was sent to ConversationAgent
    conv_msgs = [s for s in bus.sent if s.get("recipient") == "ConversationAgent"]
    assert len(conv_msgs) >= 1
    assert "Loop completed" in conv_msgs[0]["payload"]["text"]

    # Verify checkpoint files were created
    assert (tmp_path / "failures.db").exists()
