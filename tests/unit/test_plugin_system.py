"""Unit tests for plugins.registry and plugins.base."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from plugins.base import BaseTool, ExecutionContext, ToolResult, ValidationResult
from plugins.registry import PluginRegistry

# ---------------------------------------------------------------------------
# Concrete tool for testing
# ---------------------------------------------------------------------------


class FakeTool(BaseTool):
    name = "fake_tool"
    description = "A fake tool for testing"
    parameters = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    requires_approval = False

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        return ToolResult.ok(f"got {params.get('x')}")

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Would process {params.get('x')}"


class FailingTool(BaseTool):
    name = "failing_tool"
    description = "Always fails"
    parameters = {}

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        raise RuntimeError("boom")

    async def dry_run(self, params: dict[str, Any]) -> str:
        return "Would fail"


# ---------------------------------------------------------------------------
# PluginRegistry tests
# ---------------------------------------------------------------------------


class TestPluginRegistry:
    def test_register_and_get(self):
        reg = PluginRegistry()
        tool = FakeTool()
        reg.register(tool)

        assert reg.get("fake_tool") is tool
        assert "fake_tool" in reg
        assert len(reg) == 1

    def test_get_missing_returns_none(self):
        reg = PluginRegistry()
        assert reg.get("nonexistent") is None

    def test_duplicate_overwrites(self):
        reg = PluginRegistry()
        tool1 = FakeTool()
        tool2 = FakeTool()
        reg.register(tool1)
        reg.register(tool2)

        assert reg.get("fake_tool") is tool2
        assert len(reg) == 1

    def test_all_tools(self):
        reg = PluginRegistry()
        reg.register(FakeTool())
        reg.register(FailingTool())

        tools = reg.all_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"fake_tool", "failing_tool"}

    def test_all_schemas(self):
        reg = PluginRegistry()
        reg.register(FakeTool())

        schemas = reg.all_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "fake_tool"
        assert "parameters" in schemas[0]

    def test_contains_and_len(self):
        reg = PluginRegistry()
        assert len(reg) == 0
        assert "fake_tool" not in reg

        reg.register(FakeTool())
        assert len(reg) == 1
        assert "fake_tool" in reg

    def test_load_generated_bad_path(self):
        reg = PluginRegistry()
        result = reg.load_generated("/nonexistent/path.py")
        assert result is False

    def test_load_generated_from_file(self, tmp_path: Path):
        reg = PluginRegistry()

        # Write a valid tool module to a temp file
        tool_file = tmp_path / "my_tool.py"
        tool_file.write_text("""
from plugins.base import BaseTool, ExecutionContext, ToolResult

class MyGeneratedTool(BaseTool):
    name = "generated_hello"
    description = "Says hello"
    parameters = {}

    async def execute(self, params, context):
        return ToolResult.ok("hello")

    async def dry_run(self, params):
        return "Would say hello"
""")

        result = reg.load_generated(str(tool_file))
        assert result is True
        assert "generated_hello" in reg


# ---------------------------------------------------------------------------
# BaseTool.safe_execute tests
# ---------------------------------------------------------------------------


class TestSafeExecute:
    @pytest.fixture()
    def context(self):
        return ExecutionContext(session_id="test-session", user_id="test-user")

    @pytest.mark.asyncio
    @patch("plugins.base.is_tool_enabled", return_value=True, create=True)
    async def test_successful_execution(self, _mock_enabled, context):
        tool = FakeTool()
        # Patch the import inside safe_execute to not fail
        with patch.dict(
            "sys.modules",
            {"api.routes.settings": type("M", (), {"is_tool_enabled": lambda name: True})},
        ):
            result = await tool.safe_execute({"x": "hello"}, context)

        assert result.success
        assert result.output == "got hello"
        assert result.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_validation_failure(self, context):
        tool = FakeTool()
        # Missing required param 'x'
        with patch.dict(
            "sys.modules",
            {"api.routes.settings": type("M", (), {"is_tool_enabled": lambda name: True})},
        ):
            result = await tool.safe_execute({}, context)

        assert not result.success
        assert "Missing required" in (result.error or "")

    @pytest.mark.asyncio
    async def test_exception_during_execute(self, context):
        tool = FailingTool()
        with patch.dict(
            "sys.modules",
            {"api.routes.settings": type("M", (), {"is_tool_enabled": lambda name: True})},
        ):
            result = await tool.safe_execute({}, context)

        assert not result.success
        assert "boom" in (result.error or "")
        assert result.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_disabled_tool_returns_message(self, context):
        tool = FakeTool()
        with patch.dict(
            "sys.modules",
            {"api.routes.settings": type("M", (), {"is_tool_enabled": lambda name: False})},
        ):
            result = await tool.safe_execute({"x": "test"}, context)

        assert not result.success
        assert "disabled" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# ToolResult helpers
# ---------------------------------------------------------------------------


class TestToolResult:
    def test_ok(self):
        r = ToolResult.ok("output", execution_time_ms=42.0, key="val")
        assert r.success
        assert r.output == "output"
        assert r.execution_time_ms == 42.0
        assert r.metadata == {"key": "val"}

    def test_fail(self):
        r = ToolResult.fail("something broke", execution_time_ms=10.0)
        assert not r.success
        assert r.output is None
        assert r.error == "something broke"

    def test_validation_ok(self):
        v = ValidationResult.ok()
        assert v.valid
        assert v.errors == []

    def test_validation_fail(self):
        v = ValidationResult.fail("bad input", "also bad")
        assert not v.valid
        assert len(v.errors) == 2
