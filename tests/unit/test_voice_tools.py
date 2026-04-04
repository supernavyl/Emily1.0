"""Tests for voice tool orchestrator.

Covers:
- Regex intent matching (true positives, true negatives, known false positives)
- Schema filtering (only voice-safe tools)
- Intent classification (mocked fleet)
- Tool execution (mocked registry)
- Error paths (timeout, bad JSON, unknown tool)
- Full handle_voice_tool flow
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plugins.base import BaseTool, ExecutionContext, ToolResult
from voice_engine.processing.voice_tools import (
    FIRE_AND_FORGET,
    QUERY_AND_SUMMARIZE,
    VOICE_SAFE,
    VoiceToolOrchestrator,
    _TOOL_TRIGGER_RE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakeCompletionResult:
    content: str
    model: str = "test"
    total_tokens: int = 10
    prompt_tokens: int = 5
    latency_ms: float = 50.0


class FakeTool(BaseTool):
    name = "computer_open"
    description = "Open stuff"
    parameters = {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}
    requires_approval = False

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        return ToolResult.ok(f"Opened {params.get('target', 'unknown')}")

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Would open {params.get('target', '')}"


class FakeQueryTool(BaseTool):
    name = "calculator"
    description = "Calculate stuff"
    parameters = {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}
    requires_approval = False

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        return ToolResult.ok("714")

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Would compute {params.get('expression', '')}"


class FakeSlowTool(BaseTool):
    name = "web_search"
    description = "Search the web"
    parameters = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    requires_approval = False

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        await asyncio.sleep(100)  # Will timeout
        return ToolResult.ok("should not reach")

    async def dry_run(self, params: dict[str, Any]) -> str:
        return "would search"


@pytest.fixture()
def mock_fleet() -> MagicMock:
    fleet = MagicMock()
    fleet.chat = AsyncMock()
    fleet.chat_stream = AsyncMock()
    return fleet


@pytest.fixture()
def mock_prompt_builder() -> MagicMock:
    pb = MagicMock()
    pb.build_voice_tool_classification_prompt.return_value = "classify this"
    pb.build_voice_tool_result_prompt.return_value = "summarize this"
    return pb


@pytest.fixture()
def mock_registry() -> MagicMock:
    registry = MagicMock()
    fake_open = FakeTool()
    fake_calc = FakeQueryTool()
    registry.all_tools.return_value = [fake_open, fake_calc]
    registry.get.side_effect = lambda name: {"computer_open": fake_open, "calculator": fake_calc}.get(name)
    registry.__len__ = lambda self: 2
    return registry


@pytest.fixture()
def orchestrator(mock_fleet: MagicMock, mock_prompt_builder: MagicMock, mock_registry: MagicMock) -> VoiceToolOrchestrator:
    return VoiceToolOrchestrator(
        fleet=mock_fleet,
        prompt_builder=mock_prompt_builder,
        registry=mock_registry,
    )


# ---------------------------------------------------------------------------
# Regex matching
# ---------------------------------------------------------------------------


class TestToolTriggerRegex:
    """Test the intent-detection regex."""

    @pytest.mark.parametrize(
        "text",
        [
            "open Firefox",
            "launch Spotify",
            "start a new terminal",
            "search for Arch Linux news",
            "calculate 42 times 17",
            "how much is 100 divided by 3",
            "what's running right now",
            "turn on the lights",
            "what's on my calendar today",
            "show me recent files",
            "system info please",
            "how much is 5 plus 3",
            "look up the weather",
            "notify me in 10 minutes",
            "close this application",
            "clipboard contents",
        ],
    )
    def test_matches_tool_commands(self, text: str) -> None:
        assert _TOOL_TRIGGER_RE.search(text), f"Should match: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "how are you doing",
            "tell me about yourself",
            "what do you think about AI",
            "good morning Emily",
            "I had a great day",
            "let's talk about philosophy",
            "that's interesting",
            "thanks for your help",
        ],
    )
    def test_no_match_conversation(self, text: str) -> None:
        assert not _TOOL_TRIGGER_RE.search(text), f"Should NOT match: {text!r}"

    def test_known_false_positive_handled(self) -> None:
        """'I'm open to suggestions' triggers the regex but should be classified as conversation."""
        # The regex will match "open" — that's by design (false positives are cheap).
        # The LLM classification step handles this case.
        assert _TOOL_TRIGGER_RE.search("I'm open to suggestions")


# ---------------------------------------------------------------------------
# Schema filtering
# ---------------------------------------------------------------------------


class TestSchemaFiltering:
    def test_voice_safe_sets_are_disjoint(self) -> None:
        assert FIRE_AND_FORGET & QUERY_AND_SUMMARIZE == frozenset()

    def test_voice_safe_is_union(self) -> None:
        assert VOICE_SAFE == FIRE_AND_FORGET | QUERY_AND_SUMMARIZE

    def test_get_voice_schemas_filters_correctly(self, orchestrator: VoiceToolOrchestrator) -> None:
        schemas = orchestrator._get_voice_schemas()
        names = {s["name"] for s in schemas}
        assert "computer_open" in names
        assert "calculator" in names

    def test_schemas_cached(self, orchestrator: VoiceToolOrchestrator) -> None:
        s1 = orchestrator._get_voice_schemas()
        s2 = orchestrator._get_voice_schemas()
        assert s1 is s2


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------


class TestClassifyIntent:
    @pytest.mark.asyncio()
    async def test_classify_tool_command(self, orchestrator: VoiceToolOrchestrator, mock_fleet: MagicMock) -> None:
        mock_fleet.chat.return_value = FakeCompletionResult(
            content='{"action": "computer_open", "parameters": {"target": "firefox"}, "acknowledgment": "Opening Firefox."}'
        )

        result = await orchestrator.classify_intent("open Firefox", [])

        assert result is not None
        assert result["action"] == "computer_open"
        assert result["parameters"]["target"] == "firefox"
        assert result["acknowledgment"] == "Opening Firefox."

    @pytest.mark.asyncio()
    async def test_classify_conversation(self, orchestrator: VoiceToolOrchestrator, mock_fleet: MagicMock) -> None:
        mock_fleet.chat.return_value = FakeCompletionResult(
            content='{"action": "conversation"}'
        )

        result = await orchestrator.classify_intent("I'm open to suggestions", [])

        assert result is not None
        assert result["action"] == "conversation"

    @pytest.mark.asyncio()
    async def test_classify_bad_json_returns_none(self, orchestrator: VoiceToolOrchestrator, mock_fleet: MagicMock) -> None:
        mock_fleet.chat.return_value = FakeCompletionResult(content="not json at all")

        result = await orchestrator.classify_intent("open Firefox", [])

        assert result is None

    @pytest.mark.asyncio()
    async def test_classify_unsafe_tool_falls_to_conversation(self, orchestrator: VoiceToolOrchestrator, mock_fleet: MagicMock) -> None:
        mock_fleet.chat.return_value = FakeCompletionResult(
            content='{"action": "shell", "parameters": {"command": "rm -rf /"}}'
        )

        result = await orchestrator.classify_intent("run a shell command", [])

        assert result is not None
        assert result["action"] == "conversation"

    @pytest.mark.asyncio()
    async def test_classify_fleet_error_returns_none(self, orchestrator: VoiceToolOrchestrator, mock_fleet: MagicMock) -> None:
        mock_fleet.chat.side_effect = RuntimeError("backend down")

        result = await orchestrator.classify_intent("open Firefox", [])

        assert result is None


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


class TestExecuteTool:
    @pytest.mark.asyncio()
    async def test_execute_known_tool(self, orchestrator: VoiceToolOrchestrator) -> None:
        result = await orchestrator.execute_tool("computer_open", {"target": "firefox"})

        assert result.success
        assert "firefox" in result.output.lower()

    @pytest.mark.asyncio()
    async def test_execute_unknown_tool(self, orchestrator: VoiceToolOrchestrator) -> None:
        result = await orchestrator.execute_tool("nonexistent_tool", {})

        assert not result.success
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio()
    async def test_execute_timeout(self) -> None:
        """Tool that sleeps should be killed by timeout."""
        registry = MagicMock()
        slow_tool = FakeSlowTool()
        registry.get.return_value = slow_tool
        registry.all_tools.return_value = [slow_tool]
        registry.__len__ = lambda self: 1

        orch = VoiceToolOrchestrator(
            fleet=MagicMock(),
            prompt_builder=MagicMock(),
            registry=registry,
        )

        # Patch the timeout to something very short
        with patch("voice_engine.processing.voice_tools._TOOL_TIMEOUT_S", 0.01):
            result = await orch.execute_tool("web_search", {"query": "test"})

        assert not result.success
        assert "timed out" in result.error.lower()


# ---------------------------------------------------------------------------
# Full handle_voice_tool flow
# ---------------------------------------------------------------------------


class TestHandleVoiceTool:
    @pytest.mark.asyncio()
    async def test_returns_none_for_conversation(self, orchestrator: VoiceToolOrchestrator, mock_fleet: MagicMock) -> None:
        mock_fleet.chat.return_value = FakeCompletionResult(content='{"action": "conversation"}')

        result = await orchestrator.handle_voice_tool("I'm open to suggestions", [])

        assert result is None

    @pytest.mark.asyncio()
    async def test_fire_and_forget_yields_acknowledgment(self, orchestrator: VoiceToolOrchestrator, mock_fleet: MagicMock) -> None:
        mock_fleet.chat.return_value = FakeCompletionResult(
            content='{"action": "computer_open", "parameters": {"target": "firefox"}, "acknowledgment": "Opening Firefox."}'
        )

        stream = await orchestrator.handle_voice_tool("open Firefox", [])
        assert stream is not None

        tokens = []
        async for token in stream:
            tokens.append(token)

        assert tokens[0] == "Opening Firefox."
        # Fire-and-forget: only the acknowledgment, no summary
        assert len(tokens) == 1

    @pytest.mark.asyncio()
    async def test_query_tool_yields_acknowledgment_and_summary(self, orchestrator: VoiceToolOrchestrator, mock_fleet: MagicMock) -> None:
        mock_fleet.chat.return_value = FakeCompletionResult(
            content='{"action": "calculator", "parameters": {"expression": "42 * 17"}, "acknowledgment": "Let me calculate that."}'
        )

        # Mock the streaming summary
        async def fake_stream(*args: Any, **kwargs: Any):
            for tok in [" 42", " times", " 17", " is", " 714."]:
                yield tok

        mock_fleet.chat_stream.side_effect = fake_stream

        stream = await orchestrator.handle_voice_tool("what's 42 times 17", [])
        assert stream is not None

        tokens = []
        async for token in stream:
            tokens.append(token)

        assert tokens[0] == "Let me calculate that."
        # Should have summary tokens after the acknowledgment
        assert len(tokens) > 1

    @pytest.mark.asyncio()
    async def test_tool_failure_yields_error(self, orchestrator: VoiceToolOrchestrator, mock_fleet: MagicMock) -> None:
        # Return a tool that will fail — must clear side_effect before setting return_value
        failing_tool = MagicMock(spec=BaseTool)
        failing_tool.name = "computer_open"
        failing_tool.safe_execute = AsyncMock(return_value=ToolResult.fail("permission denied"))
        orchestrator._registry.get.side_effect = None
        orchestrator._registry.get.return_value = failing_tool

        mock_fleet.chat.return_value = FakeCompletionResult(
            content='{"action": "computer_open", "parameters": {"target": "firefox"}, "acknowledgment": "Opening Firefox."}'
        )

        stream = await orchestrator.handle_voice_tool("open Firefox", [])
        assert stream is not None

        tokens = []
        async for token in stream:
            tokens.append(token)

        full = "".join(tokens)
        assert "couldn't" in full.lower()
        assert "permission denied" in full.lower()


# ---------------------------------------------------------------------------
# matches_tool_intent
# ---------------------------------------------------------------------------


class TestMatchesToolIntent:
    def test_matches_returns_true(self, orchestrator: VoiceToolOrchestrator) -> None:
        assert orchestrator.matches_tool_intent("open Firefox") is True

    def test_matches_returns_false(self, orchestrator: VoiceToolOrchestrator) -> None:
        assert orchestrator.matches_tool_intent("how are you") is False
