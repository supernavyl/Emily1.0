"""ToolBridgeAdapter — wraps Emily's PluginRegistry into emily-loop's ToolRegistry."""

from __future__ import annotations

from typing import Any

from emily_loop.models import StepResult
from emily_loop.tools import ToolFn, ToolRegistry
from plugins.base import BaseTool, ExecutionContext


class ToolBridgeAdapter:
    """Converts Emily's PluginRegistry tools into emily-loop ToolFn callables.

    Each Emily BaseTool is wrapped in an async function that calls
    safe_execute() and converts the ToolResult into a StepResult.
    Approval-gated tools keep their approval checks.
    """

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    def to_tool_registry(self) -> ToolRegistry:
        """Build a Loop ToolRegistry from all Emily tools.

        Returns:
            A ToolRegistry with all Emily tools wrapped as ToolFn callables.
        """
        loop_registry = ToolRegistry()
        for tool in self._registry.all_tools():
            loop_registry.register(tool.name, self._wrap(tool))
        return loop_registry

    @staticmethod
    def _wrap(tool: BaseTool) -> ToolFn:
        """Wrap a single BaseTool as a ToolFn."""

        async def fn(params: dict[str, Any]) -> StepResult:
            ctx = ExecutionContext(session_id="loop", sandbox_enabled=True)
            result = await tool.safe_execute(params, ctx)
            return StepResult(
                step_id="",
                success=result.success,
                output=str(result.output) if result.output is not None else "",
                error=result.error,
                duration_ms=result.execution_time_ms,
            )

        return fn
