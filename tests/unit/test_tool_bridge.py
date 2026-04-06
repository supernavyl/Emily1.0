"""Tests for ToolBridgeAdapter — bridges PluginRegistry to emily-loop's ToolRegistry."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from emily_loop.models import StepResult
from emily_loop.tools import ToolRegistry
from plugins.base import ExecutionContext, ToolResult


class FakeTool:
    """Minimal mock of BaseTool."""

    def __init__(self, name: str, output: Any = "ok", success: bool = True) -> None:
        self.name = name
        self.description = f"Fake {name} tool"
        self.parameters: dict[str, Any] = {}
        self.requires_approval = False
        self.safe_execute = AsyncMock(
            return_value=ToolResult(
                success=success,
                output=output,
                error=None if success else "tool failed",
                execution_time_ms=42.0,
            )
        )


class FakeRegistry:
    """Minimal mock of PluginRegistry."""

    def __init__(self, tools: list[FakeTool] | None = None) -> None:
        self._tools = tools or []

    def all_tools(self) -> list[FakeTool]:
        return self._tools


@pytest.fixture
def registry_with_tools() -> FakeRegistry:
    return FakeRegistry([
        FakeTool("shell", output="hello world"),
        FakeTool("calculator", output="42"),
    ])


def test_to_tool_registry_returns_registry(registry_with_tools: FakeRegistry) -> None:
    from core.loop_integration.tool_bridge import ToolBridgeAdapter

    adapter = ToolBridgeAdapter(registry_with_tools)
    result = adapter.to_tool_registry()

    assert isinstance(result, ToolRegistry)
    assert sorted(result.list_tools()) == ["calculator", "shell"]


@pytest.mark.asyncio
async def test_wrapped_tool_returns_step_result(registry_with_tools: FakeRegistry) -> None:
    from core.loop_integration.tool_bridge import ToolBridgeAdapter

    adapter = ToolBridgeAdapter(registry_with_tools)
    loop_registry = adapter.to_tool_registry()

    fn = loop_registry.get("shell")
    assert fn is not None

    result = await fn({"cmd": "echo hello"})

    assert isinstance(result, StepResult)
    assert result.success is True
    assert result.output == "hello world"
    assert result.duration_ms == 42.0


@pytest.mark.asyncio
async def test_wrapped_tool_failure_propagates() -> None:
    from core.loop_integration.tool_bridge import ToolBridgeAdapter

    registry = FakeRegistry([FakeTool("bad_tool", output=None, success=False)])
    adapter = ToolBridgeAdapter(registry)
    loop_registry = adapter.to_tool_registry()

    fn = loop_registry.get("bad_tool")
    assert fn is not None

    result = await fn({})

    assert result.success is False
    assert result.error == "tool failed"


def test_empty_registry_produces_empty_tool_registry() -> None:
    from core.loop_integration.tool_bridge import ToolBridgeAdapter

    adapter = ToolBridgeAdapter(FakeRegistry([]))
    loop_registry = adapter.to_tool_registry()

    assert loop_registry.list_tools() == []
