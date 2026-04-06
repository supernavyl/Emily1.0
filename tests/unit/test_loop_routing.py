"""Tests for complexity-based routing to LoopAgent in ConversationAgent."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.bus import Message


class FakeBus:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_to(self, **kwargs: Any) -> str:
        self.sent.append(kwargs)
        return "task-id"

    def register_handler(self, name: str, handler: Any) -> None:
        pass


class FakeRoutingDecision:
    def __init__(self, complexity: int) -> None:
        self.complexity_score = complexity
        self.tier = MagicMock()
        self.tier.value = "smart"
        self.model_name = "test-model"
        self.task_type = MagicMock()
        self.task_type.name = "CHAT"


class FakeFleet:
    def __init__(self, complexity: int = 8) -> None:
        self._config = MagicMock()
        self._config.routing.voice_skip_rag_below = 5
        self._config.routing.voice_fast_complexity_threshold = 5
        self._config.routing.voice_skip_critic = True
        self.route = MagicMock(return_value=FakeRoutingDecision(complexity))
        self.chat = AsyncMock()
        self.chat_stream = AsyncMock()

    def set_complexity(self, c: int) -> None:
        self.route.return_value = FakeRoutingDecision(c)


@pytest.mark.asyncio
async def test_high_complexity_routes_to_loop_agent() -> None:
    """Complexity >= 7 should send loop.run to LoopAgent instead of generating inline."""
    bus = FakeBus()
    fleet = FakeFleet(complexity=8)
    memory = MagicMock()
    memory.add_user_turn = AsyncMock()
    memory.retrieve_context = AsyncMock(return_value=[])
    memory.has_recall_intent = MagicMock(return_value=False)
    memory.working = MagicMock()
    memory.working.session_id = "test-session"
    memory.working.to_dict_list = MagicMock(return_value=[])
    memory.procedural = MagicMock()
    memory.procedural.user_profile = {}

    from agents.conversation import ConversationAgent

    agent = ConversationAgent(bus, fleet, memory, settings=None)

    msg = Message(
        type="text.input",
        payload={"text": "Build a complex multi-step system"},
        sender="test",
        recipient="ConversationAgent",
    )
    await agent.handle(msg)

    # Should have sent to LoopAgent
    loop_msgs = [s for s in bus.sent if s.get("recipient") == "LoopAgent"]
    assert len(loop_msgs) == 1
    assert loop_msgs[0]["msg_type"] == "loop.run"
    assert loop_msgs[0]["payload"]["task"] == "Build a complex multi-step system"
