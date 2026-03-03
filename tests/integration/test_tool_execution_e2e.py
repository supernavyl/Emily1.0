"""Integration test: Tool execution pipeline.

Verify that the plugin registry loads builtin tools and that
tool execution works end-to-end via safe_execute.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_plugin_registry_loads_builtins():
    """PluginRegistry.load_builtins() should register multiple tools."""
    from plugins.registry import PluginRegistry

    registry = PluginRegistry()
    registry.load_builtins()

    schemas = registry.all_schemas()
    assert len(schemas) > 0, "No builtin tools registered"

    # Check that each schema has required fields
    for schema in schemas:
        assert "name" in schema
        assert "description" in schema


@pytest.mark.asyncio
async def test_calculator_tool_execution():
    """The calculator tool should evaluate simple expressions."""
    from plugins.base import ExecutionContext
    from plugins.registry import PluginRegistry

    registry = PluginRegistry()
    registry.load_builtins()

    calc = registry.get("calculator")
    if calc is None:
        pytest.skip("Calculator tool not in builtins")

    ctx = ExecutionContext(
        user_id="test",
        session_id="test-session",
        allowed_paths=["/tmp"],
    )

    result = await calc.safe_execute({"expression": "2 + 2"}, ctx)
    assert result.success
    assert "4" in str(result.output)


@pytest.mark.asyncio
async def test_tool_approval_gate():
    """Tools with requires_approval=True should be identifiable."""
    from plugins.registry import PluginRegistry

    registry = PluginRegistry()
    registry.load_builtins()

    schemas = registry.all_schemas()
    # Verify the schema exposes the requires_approval field
    for schema in schemas:
        assert "requires_approval" in schema
