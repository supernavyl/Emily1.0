"""Tests for RAG retrieval and web search wiring in ConversationAgent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.conversation import ConversationAgent
from llm.router import TaskType
from plugins.base import BaseTool, ExecutionContext, ToolResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# ── lightweight fakes ───────────────────────────────────────────


@dataclass
class _FakeCriticScore:
    overall: float = 0.9


@dataclass
class _FakeRouting:
    tier: MagicMock = field(default_factory=lambda: MagicMock(value="fast"))
    model_name: str = "Qwen2.5-14B-Instruct-abliterated"
    complexity_score: int = 3
    task_type: TaskType = TaskType.CHAT


class _FakeWorkingMemory:
    session_id: str = "test-session"
    total_tokens: int = 0

    def to_dict_list(self) -> list[dict[str, str]]:
        return []

    def add(self, **kwargs: Any) -> None:
        pass

    def get_transcript(self) -> str:
        return ""

    def clear(self) -> None:
        pass


class _FakeProcedural:
    user_profile: ClassVar[dict[str, Any]] = {}
    self_model: ClassVar[dict[str, Any]] = {}


class _FakeMemory:
    working = _FakeWorkingMemory()
    procedural = _FakeProcedural()

    async def add_user_turn(
        self,
        text: str,
        importance: float = 0.5,
        metadata: Any = None,
    ) -> None:
        pass

    async def add_assistant_turn(
        self,
        text: str,
        importance: float = 0.5,
        metadata: Any = None,
    ) -> None:
        pass

    async def retrieve_context(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return [
            {"content": "Retrieved fact about AI.", "source": "knowledge/ai.md", "score": 0.88},
        ]


class _FakeMemoryNoRetriever(_FakeMemory):
    async def retrieve_context(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return []


class _FakeStreamProcessor:
    async def iter_sentences(self, token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
        yield "Hello world."


class _FakeWebSearch(BaseTool):
    name = "web_search"
    description = "test"
    parameters: ClassVar[dict[str, Any]] = {}

    def __init__(self) -> None:
        pass

    async def dry_run(self, params: dict[str, Any]) -> str:
        return "would search"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        return ToolResult.ok(
            [
                {
                    "title": "Breaking News",
                    "url": "https://example.com",
                    "snippet": "Something happened.",
                },
            ]
        )


# ── fixtures ────────────────────────────────────────────────────


def _make_agent(
    memory: Any = None,
    web_search: BaseTool | None = None,
    complexity_score: int = 3,
) -> ConversationAgent:
    bus = AsyncMock()
    bus.send_to = AsyncMock()

    fleet = MagicMock()
    routing = _FakeRouting()
    routing.complexity_score = complexity_score
    fleet.route = MagicMock(return_value=routing)

    fleet._config.routing.voice_fast_complexity_threshold = 5
    fleet._config.routing.voice_skip_rag_below = 5
    fleet._config.routing.voice_skip_critic = True

    async def _fake_stream(*args: Any, **kwargs: Any) -> AsyncIterator[str]:
        yield "Hello world."

    fleet.chat_stream = MagicMock(side_effect=_fake_stream)

    mem = memory or _FakeMemory()

    agent = ConversationAgent(
        bus=bus,
        fleet=fleet,
        memory=mem,
        web_search=web_search,
    )
    agent._stream_processor = _FakeStreamProcessor()
    agent._critic = AsyncMock()
    agent._critic.evaluate_and_retry = AsyncMock(
        return_value=("Hello world.", _FakeCriticScore()),
    )
    return agent


# ── tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rag_context_injected() -> None:
    """RAG chunks should be passed as context_block to build_messages."""
    agent = _make_agent()

    with patch.object(agent._prompts, "build_messages", wraps=agent._prompts.build_messages) as spy:
        await agent._generate_response("What is AI?", "task-1")
        spy.assert_called_once()
        _, kwargs = spy.call_args
        assert kwargs.get("context_block") or (spy.call_args[0] and len(spy.call_args[0]) > 3)
        call_kwargs = kwargs if "context_block" in kwargs else {}
        if call_kwargs:
            assert "retrieved_context" in call_kwargs["context_block"]


@pytest.mark.asyncio
async def test_web_search_triggered_for_recency() -> None:
    """Web search should fire for recency-sensitive queries."""
    ws = _FakeWebSearch()
    agent = _make_agent(web_search=ws)

    with patch.object(ws, "execute", wraps=ws.execute) as spy:
        await agent._generate_response("What's the latest news today?", "task-2")
        spy.assert_called_once()


@pytest.mark.asyncio
async def test_web_search_skipped_for_factual() -> None:
    """Web search should NOT fire for timeless factual queries."""
    ws = _FakeWebSearch()
    agent = _make_agent(web_search=ws)

    with patch.object(ws, "execute", wraps=ws.execute) as spy:
        await agent._generate_response("What is 2+2?", "task-3")
        spy.assert_not_called()


@pytest.mark.asyncio
async def test_no_web_search_when_tool_absent() -> None:
    """When no web_search tool is provided, no errors should occur."""
    agent = _make_agent(web_search=None)
    await agent._generate_response("What's the latest news today?", "task-4")


@pytest.mark.asyncio
async def test_empty_retriever_produces_no_context() -> None:
    """When the retriever returns nothing, context_block should be empty."""
    agent = _make_agent(memory=_FakeMemoryNoRetriever())

    with patch.object(agent._prompts, "build_messages", wraps=agent._prompts.build_messages) as spy:
        await agent._generate_response("Hello", "task-5")
        spy.assert_called_once()
        _, kwargs = spy.call_args
        context = kwargs.get("context_block", "")
        assert context == ""


@pytest.mark.asyncio
async def test_voice_mode_uses_voice_fast_for_simple_turns() -> None:
    """Voice mode should force VOICE_FAST only for low complexity turns."""
    agent = _make_agent(complexity_score=2)

    await agent._generate_response("hey there", "task-voice-simple", voice_mode=True)

    force_tier = agent._fleet.chat_stream.call_args.kwargs["force_tier"]
    assert force_tier is not None
    assert force_tier.value == "voice_fast"


@pytest.mark.asyncio
async def test_voice_mode_allows_escalation_for_complex_turns() -> None:
    """Voice mode should not force VOICE_FAST for high complexity turns."""
    agent = _make_agent(complexity_score=9)

    await agent._generate_response(
        "compare two designs and explain tradeoffs in detail",
        "task-voice-complex",
        voice_mode=True,
    )

    force_tier = agent._fleet.chat_stream.call_args.kwargs["force_tier"]
    assert force_tier is None
