"""Comprehensive unit tests for the Emily agent system.

Tests all agent classes:
- BaseAgent (via concrete subclass)
- PlannerAgent
- MemoryAgent
- ReflectionAgent
- OnboardingAgent
- MonitorAgent
- ResearchAgent
- CodeAgent

All I/O and external dependencies are mocked.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from core.bus import Message, Priority

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeLLMResult:
    """Mimics the result object returned by LLMFleet.chat()."""

    content: str


def _make_message(
    msg_type: str,
    payload: dict[str, Any] | None = None,
    sender: str = "TestSender",
    recipient: str = "TestRecipient",
    priority: Priority = Priority.ACTIVE,
    task_id: str = "task-001",
) -> Message:
    """Build a Message with sensible defaults for testing.

    Args:
        msg_type: Message type string.
        payload: Optional payload dict.
        sender: Sender agent name.
        recipient: Recipient agent name.
        priority: Message priority.
        task_id: Correlation ID.

    Returns:
        A pre-populated Message.
    """
    return Message(
        type=msg_type,
        payload=payload or {},
        sender=sender,
        recipient=recipient,
        priority=priority,
        task_id=task_id,
    )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_bus() -> MagicMock:
    """Create a mock AgentBus with async helpers.

    Returns:
        MagicMock standing in for AgentBus.
    """
    bus = MagicMock()
    bus.register_handler = MagicMock()
    bus.send_to = AsyncMock(return_value="task-id-generated")
    return bus


@pytest.fixture()
def mock_fleet() -> MagicMock:
    """Create a mock LLMFleet with async chat().

    Returns:
        MagicMock standing in for LLMFleet.
    """
    fleet = MagicMock()
    fleet.chat = AsyncMock(return_value=FakeLLMResult(content="default response"))
    return fleet


@pytest.fixture()
def mock_memory() -> MagicMock:
    """Create a mock MemoryManager with all required sub-managers.

    Returns:
        MagicMock standing in for MemoryManager.
    """
    memory = MagicMock()

    memory.working = MagicMock()
    memory.working.to_dict_list.return_value = [{"role": "user", "content": "hello"}]
    memory.working.pin.return_value = True
    memory.working.entry_count = 5

    memory.episodic = MagicMock()
    memory.episodic.search_by_topic = AsyncMock(return_value=[])
    memory.episodic.get_recent_episodes = AsyncMock(return_value=[])

    memory.procedural = MagicMock()
    memory.procedural.self_model = {"curiosity": 0.8, "warmth": 0.9}
    memory.procedural.set_user_fact = AsyncMock()
    memory.procedural.update_self_model = AsyncMock()
    memory.procedural.get_user_fact.return_value = "Alice"
    memory.procedural.update_user_profile = AsyncMock()
    memory.procedural.user_profile = {"facts": {"name": "Alice"}}

    memory.get_context_for_llm = AsyncMock(return_value={"context": "test"})
    memory.end_session = AsyncMock()

    return memory


# ===================================================================
# BaseAgent tests
# ===================================================================


class TestBaseAgent:
    """Tests for agents.base.BaseAgent via a concrete stub subclass."""

    @pytest.fixture()
    def agent(
        self,
        mock_bus: MagicMock,
        mock_fleet: MagicMock,
        mock_memory: MagicMock,
    ) -> Any:
        """Create a concrete BaseAgent subclass for testing.

        Returns:
            _StubAgent instance.
        """
        from agents.base import BaseAgent

        class _StubAgent(BaseAgent):
            name = "StubAgent"
            description = "A stub for testing BaseAgent."

            def __init__(self, bus: Any, fleet: Any, memory: Any) -> None:
                super().__init__(bus, fleet, memory)
                self.handled_messages: list[Message] = []

            async def handle(self, message: Message) -> None:
                """Record the message."""
                self.handled_messages.append(message)

        return _StubAgent(mock_bus, mock_fleet, mock_memory)

    @pytest.mark.asyncio
    async def test_start_registers_handler(
        self,
        agent: Any,
        mock_bus: MagicMock,
    ) -> None:
        """start() registers the agent's _dispatch on the bus."""
        with patch("agents.base.ACTIVE_AGENTS"):
            await agent.start()

        mock_bus.register_handler.assert_called_once_with(
            "StubAgent",
            agent._dispatch,
        )
        agent._task.cancel()

    @pytest.mark.asyncio
    async def test_start_creates_heartbeat_task(self, agent: Any) -> None:
        """start() creates a background heartbeat asyncio.Task."""
        with patch("agents.base.ACTIVE_AGENTS"):
            await agent.start()

        assert agent._task is not None
        assert not agent._task.done()
        agent._task.cancel()

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self, agent: Any) -> None:
        """start() flips _running to True."""
        with patch("agents.base.ACTIVE_AGENTS"):
            await agent.start()

        assert agent._running is True
        agent._task.cancel()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, agent: Any) -> None:
        """stop() cancels the heartbeat task."""
        with patch("agents.base.ACTIVE_AGENTS"):
            await agent.start()
            task = agent._task
            await agent.stop()

        assert agent._running is False
        # Task may be in "cancelling" state; give the loop a tick to finalise
        await asyncio.sleep(0)
        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_dispatch_calls_handle(self, agent: Any) -> None:
        """_dispatch() forwards the message to handle() with timing."""
        msg = _make_message("test.event", {"data": 1})
        with patch("agents.base.AGENT_TASK_LATENCY") as m:
            m.labels.return_value.observe = MagicMock()
            await agent._dispatch(msg)

        assert len(agent.handled_messages) == 1
        assert agent.handled_messages[0] is msg

    @pytest.mark.asyncio
    async def test_dispatch_records_latency(self, agent: Any) -> None:
        """_dispatch() observes latency on the Prometheus histogram."""
        msg = _make_message("test.event")
        with patch("agents.base.AGENT_TASK_LATENCY") as m:
            observer = MagicMock()
            m.labels.return_value.observe = observer
            await agent._dispatch(msg)

        m.labels.assert_called_with(agent_name="StubAgent")
        observer.assert_called_once()
        assert observer.call_args[0][0] >= 0

    @pytest.mark.asyncio
    async def test_dispatch_catches_handler_exception(
        self,
        mock_bus: MagicMock,
        mock_fleet: MagicMock,
        mock_memory: MagicMock,
    ) -> None:
        """_dispatch() logs but does not raise if handle() throws."""
        from agents.base import BaseAgent

        class _BrokenAgent(BaseAgent):
            name = "BrokenAgent"
            description = "Always raises."

            async def handle(self, message: Message) -> None:
                """Raise unconditionally."""
                raise ValueError("boom")

        broken = _BrokenAgent(mock_bus, mock_fleet, mock_memory)
        msg = _make_message("test.event")
        with patch("agents.base.AGENT_TASK_LATENCY") as m:
            m.labels.return_value.observe = MagicMock()
            await broken._dispatch(msg)  # should not propagate

    @pytest.mark.asyncio
    async def test_send_delegates_to_bus(
        self,
        agent: Any,
        mock_bus: MagicMock,
    ) -> None:
        """send() forwards to bus.send_to with correct arguments."""
        await agent.send(
            "TargetAgent",
            "msg.type",
            {"x": 1},
            Priority.REALTIME,
            "tid",
        )

        mock_bus.send_to.assert_called_once_with(
            recipient="TargetAgent",
            msg_type="msg.type",
            payload={"x": 1},
            sender="StubAgent",
            priority=Priority.REALTIME,
            task_id="tid",
        )

    @pytest.mark.asyncio
    async def test_send_uses_default_priority(
        self,
        agent: Any,
        mock_bus: MagicMock,
    ) -> None:
        """send() defaults to ACTIVE priority."""
        await agent.send("X", "y", {})
        _, kwargs = mock_bus.send_to.call_args
        assert kwargs["priority"] == Priority.ACTIVE

    @pytest.mark.asyncio
    async def test_send_returns_task_id(
        self,
        agent: Any,
        mock_bus: MagicMock,
    ) -> None:
        """send() returns the task_id produced by bus.send_to."""
        result = await agent.send("A", "b", {})
        assert result == "task-id-generated"


# ===================================================================
# PlannerAgent tests
# ===================================================================


class TestPlannerAgent:
    """Tests for agents.planner.PlannerAgent."""

    @pytest.fixture()
    def planner(
        self,
        mock_bus: MagicMock,
        mock_fleet: MagicMock,
        mock_memory: MagicMock,
    ) -> Any:
        """Create a PlannerAgent with mocked dependencies.

        Returns:
            PlannerAgent instance.
        """
        with patch("agents.planner.PromptBuilder"):
            from agents.planner import PlannerAgent

            return PlannerAgent(mock_bus, mock_fleet, mock_memory)

    @pytest.mark.asyncio
    async def test_handle_ignores_unknown_type(self, planner: Any) -> None:
        """handle() silently ignores unrecognized message types."""
        msg = _make_message("unknown.type")
        await planner.handle(msg)

    @pytest.mark.asyncio
    async def test_plan_request_dispatches_root_steps(
        self,
        planner: Any,
        mock_fleet: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """_handle_plan_request dispatches only root steps (no dependencies)."""
        steps = [
            {"step": 1, "agent": "ResearchAgent", "task": "Research X", "depends_on": []},
            {"step": 2, "agent": "CodeAgent", "task": "Code Y", "depends_on": [1]},
        ]
        mock_fleet.chat.return_value = FakeLLMResult(content="{}")

        with patch("agents.planner.extract_json", return_value={"steps": steps}):
            msg = _make_message("planner.plan_request", {"task": "Build a widget"})
            await planner.handle(msg)

        assert mock_bus.send_to.call_count == 1
        sent = mock_bus.send_to.call_args
        assert sent.kwargs["recipient"] == "ResearchAgent"
        assert sent.kwargs["msg_type"] == "agent.task"
        assert sent.kwargs["payload"]["step_index"] == 1

    @pytest.mark.asyncio
    async def test_plan_request_dispatches_multiple_roots(
        self,
        planner: Any,
        mock_fleet: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """Root steps with no deps are all dispatched in parallel."""
        steps = [
            {"step": 1, "agent": "ResearchAgent", "task": "A", "depends_on": []},
            {"step": 2, "agent": "CodeAgent", "task": "B", "depends_on": []},
            {"step": 3, "agent": "ResearchAgent", "task": "C", "depends_on": [1, 2]},
        ]
        mock_fleet.chat.return_value = FakeLLMResult(content="{}")

        with patch("agents.planner.extract_json", return_value={"steps": steps}):
            msg = _make_message("planner.plan_request", {"task": "parallel roots"})
            await planner.handle(msg)

        task_calls = [
            c for c in mock_bus.send_to.call_args_list if c.kwargs.get("msg_type") == "agent.task"
        ]
        assert len(task_calls) == 2

    @pytest.mark.asyncio
    async def test_plan_request_fallback_on_bad_plan(
        self,
        planner: Any,
        mock_fleet: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """Falls back to ConversationAgent when plan generation returns None."""
        mock_fleet.chat.return_value = FakeLLMResult(content="gibberish")

        with patch("agents.planner.extract_json", return_value=None):
            msg = _make_message("planner.plan_request", {"task": "Do stuff"})
            await planner.handle(msg)

        sent = mock_bus.send_to.call_args
        assert sent.kwargs["recipient"] == "ConversationAgent"
        assert sent.kwargs["msg_type"] == "text.input"

    @pytest.mark.asyncio
    async def test_plan_request_fallback_on_missing_steps_key(
        self,
        planner: Any,
        mock_fleet: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """Falls back when JSON lacks a 'steps' key."""
        mock_fleet.chat.return_value = FakeLLMResult(content="{}")

        with patch("agents.planner.extract_json", return_value={"no_steps": True}):
            msg = _make_message("planner.plan_request", {"task": "X"})
            await planner.handle(msg)

        sent = mock_bus.send_to.call_args
        assert sent.kwargs["recipient"] == "ConversationAgent"

    @pytest.mark.asyncio
    async def test_subtask_result_records_completion(
        self,
        planner: Any,
        mock_bus: MagicMock,
    ) -> None:
        """All steps complete → final synthesis sent to ConversationAgent."""
        plan_id = "plan-abc"
        planner._pending_tasks[plan_id] = {
            "task": "Build widget",
            "steps": [
                {"step": 1, "agent": "ResearchAgent", "task": "R", "depends_on": []},
            ],
            "completed": {},
            "requester_task_id": "rtid",
            "total_steps": 1,
            "_dispatched": {1},
        }

        msg = _make_message(
            "planner.subtask_result",
            {
                "plan_id": plan_id,
                "step_index": 1,
                "result": "Done researching",
            },
        )
        await planner.handle(msg)

        assert plan_id not in planner._pending_tasks
        sent = mock_bus.send_to.call_args
        assert sent.kwargs["recipient"] == "ConversationAgent"

    @pytest.mark.asyncio
    async def test_subtask_result_ignores_unknown_plan(
        self,
        planner: Any,
        mock_bus: MagicMock,
    ) -> None:
        """Results for unknown plan IDs are silently dropped."""
        msg = _make_message(
            "planner.subtask_result",
            {
                "plan_id": "nonexistent",
                "step_index": 1,
                "result": "done",
            },
        )
        await planner.handle(msg)
        mock_bus.send_to.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_unblocked_steps(
        self,
        planner: Any,
        mock_bus: MagicMock,
    ) -> None:
        """Completing a dep dispatches the dependent step."""
        plan_id = "plan-dep"
        planner._pending_tasks[plan_id] = {
            "task": "Multi-step",
            "steps": [
                {"step": 1, "agent": "ResearchAgent", "task": "S1", "depends_on": []},
                {"step": 2, "agent": "CodeAgent", "task": "S2", "depends_on": [1]},
            ],
            "completed": {},
            "requester_task_id": "rtid",
            "total_steps": 2,
            "_dispatched": {1},
        }

        msg = _make_message(
            "planner.subtask_result",
            {
                "plan_id": plan_id,
                "step_index": 1,
                "result": "Step 1 done",
            },
        )
        await planner.handle(msg)

        task_calls = [
            c for c in mock_bus.send_to.call_args_list if c.kwargs.get("msg_type") == "agent.task"
        ]
        assert len(task_calls) == 1
        assert task_calls[0].kwargs["recipient"] == "CodeAgent"
        assert task_calls[0].kwargs["payload"]["step_index"] == 2

    @pytest.mark.asyncio
    async def test_dispatch_unblocked_skips_already_dispatched(
        self,
        planner: Any,
        mock_bus: MagicMock,
    ) -> None:
        """Already-dispatched steps are not re-dispatched."""
        plan_id = "plan-dup"
        planner._pending_tasks[plan_id] = {
            "task": "Multi-step",
            "steps": [
                {"step": 1, "agent": "R", "task": "S1", "depends_on": []},
                {"step": 2, "agent": "C", "task": "S2", "depends_on": [1]},
            ],
            "completed": {1: "done"},
            "requester_task_id": "rtid",
            "total_steps": 2,
            "_dispatched": {1, 2},
        }

        await planner._dispatch_unblocked_steps(
            plan_id,
            planner._pending_tasks[plan_id],
        )
        mock_bus.send_to.assert_not_called()

    @pytest.mark.asyncio
    async def test_unblocked_waits_for_all_deps(
        self,
        planner: Any,
        mock_bus: MagicMock,
    ) -> None:
        """Step with multiple deps is not dispatched until ALL deps complete."""
        plan_id = "plan-multi-dep"
        planner._pending_tasks[plan_id] = {
            "task": "Multi-dep",
            "steps": [
                {"step": 1, "agent": "R", "task": "S1", "depends_on": []},
                {"step": 2, "agent": "R", "task": "S2", "depends_on": []},
                {"step": 3, "agent": "C", "task": "S3", "depends_on": [1, 2]},
            ],
            "completed": {1: "done"},
            "requester_task_id": "rtid",
            "total_steps": 3,
            "_dispatched": {1, 2},
        }

        await planner._dispatch_unblocked_steps(
            plan_id,
            planner._pending_tasks[plan_id],
        )
        # Step 3 depends on both 1 and 2; only 1 is complete → no dispatch
        mock_bus.send_to.assert_not_called()


# ===================================================================
# MemoryAgent tests
# ===================================================================


class TestMemoryAgent:
    """Tests for agents.memory_agent.MemoryAgent."""

    @pytest.fixture()
    def mem_agent(
        self,
        mock_bus: MagicMock,
        mock_fleet: MagicMock,
        mock_memory: MagicMock,
    ) -> Any:
        """Create a MemoryAgent with mocked dependencies.

        Returns:
            MemoryAgent instance.
        """
        from agents.memory_agent import MemoryAgent

        return MemoryAgent(mock_bus, mock_fleet, mock_memory)

    @pytest.mark.asyncio
    async def test_search_queries_episodic(
        self,
        mem_agent: Any,
        mock_memory: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """memory.search queries episodic memory and returns results."""
        msg = _make_message("memory.search", {"query": "favorite color"}, sender="Conv")
        await mem_agent.handle(msg)

        mock_memory.episodic.search_by_topic.assert_awaited_once_with(
            "favorite color",
            limit=3,
        )
        sent = mock_bus.send_to.call_args
        assert sent.kwargs["msg_type"] == "memory.search_result"
        assert sent.kwargs["recipient"] == "Conv"

    @pytest.mark.asyncio
    async def test_search_uses_reply_to(
        self,
        mem_agent: Any,
        mock_bus: MagicMock,
    ) -> None:
        """memory.search respects 'reply_to' payload over sender."""
        msg = _make_message(
            "memory.search",
            {"query": "q", "reply_to": "SpecificAgent"},
            sender="Other",
        )
        await mem_agent.handle(msg)
        assert mock_bus.send_to.call_args.kwargs["recipient"] == "SpecificAgent"

    @pytest.mark.asyncio
    async def test_search_handles_episodic_error(
        self,
        mem_agent: Any,
        mock_memory: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """memory.search still sends results when episodic search raises."""
        mock_memory.episodic.search_by_topic.side_effect = RuntimeError("db down")
        msg = _make_message("memory.search", {"query": "test"}, sender="X")
        await mem_agent.handle(msg)

        sent = mock_bus.send_to.call_args
        assert sent.kwargs["payload"]["results"]["episodic"] == []

    @pytest.mark.asyncio
    async def test_write_fact(
        self,
        mem_agent: Any,
        mock_memory: MagicMock,
    ) -> None:
        """memory.write_fact persists a fact to procedural memory."""
        msg = _make_message("memory.write_fact", {"key": "color", "value": "blue"})
        await mem_agent.handle(msg)
        mock_memory.procedural.set_user_fact.assert_awaited_once_with("color", "blue")

    @pytest.mark.asyncio
    async def test_write_fact_skips_empty_key(
        self,
        mem_agent: Any,
        mock_memory: MagicMock,
    ) -> None:
        """memory.write_fact is a no-op when key is empty."""
        msg = _make_message("memory.write_fact", {"key": "", "value": "blue"})
        await mem_agent.handle(msg)
        mock_memory.procedural.set_user_fact.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_write_fact_skips_none_value(
        self,
        mem_agent: Any,
        mock_memory: MagicMock,
    ) -> None:
        """memory.write_fact is a no-op when value is None (missing)."""
        msg = _make_message("memory.write_fact", {"key": "color"})
        await mem_agent.handle(msg)
        mock_memory.procedural.set_user_fact.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pin_entry(
        self,
        mem_agent: Any,
        mock_memory: MagicMock,
    ) -> None:
        """memory.pin_entry pins a working memory entry."""
        msg = _make_message("memory.pin_entry", {"entry_id": "entry-42"})
        await mem_agent.handle(msg)
        mock_memory.working.pin.assert_called_once_with("entry-42")

    @pytest.mark.asyncio
    async def test_pin_entry_skips_empty_id(
        self,
        mem_agent: Any,
        mock_memory: MagicMock,
    ) -> None:
        """memory.pin_entry is a no-op when entry_id is empty."""
        msg = _make_message("memory.pin_entry", {"entry_id": ""})
        await mem_agent.handle(msg)
        mock_memory.working.pin.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_context(
        self,
        mem_agent: Any,
        mock_memory: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """memory.get_context returns full LLM context to reply_to."""
        msg = _make_message(
            "memory.get_context",
            {"reply_to": "LLMAgent"},
            sender="Conv",
        )
        await mem_agent.handle(msg)

        mock_memory.get_context_for_llm.assert_awaited_once()
        sent = mock_bus.send_to.call_args
        assert sent.kwargs["recipient"] == "LLMAgent"
        assert sent.kwargs["msg_type"] == "memory.context_result"

    @pytest.mark.asyncio
    async def test_consolidate_ends_session_when_many_entries(
        self,
        mem_agent: Any,
        mock_memory: MagicMock,
    ) -> None:
        """memory.consolidate calls end_session when entry_count > 20."""
        mock_memory.working.entry_count = 25
        msg = _make_message("memory.consolidate")
        await mem_agent.handle(msg)
        mock_memory.end_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_consolidate_skips_when_few_entries(
        self,
        mem_agent: Any,
        mock_memory: MagicMock,
    ) -> None:
        """memory.consolidate does not end session when entry_count <= 20."""
        mock_memory.working.entry_count = 10
        msg = _make_message("memory.consolidate")
        await mem_agent.handle(msg)
        mock_memory.end_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_type_ignored(
        self,
        mem_agent: Any,
        mock_bus: MagicMock,
    ) -> None:
        """MemoryAgent silently ignores unknown message types."""
        msg = _make_message("memory.unknown_op")
        await mem_agent.handle(msg)
        mock_bus.send_to.assert_not_called()


# ===================================================================
# ReflectionAgent tests
# ===================================================================


class TestReflectionAgent:
    """Tests for agents.reflection.ReflectionAgent."""

    @pytest.fixture()
    def reflector(
        self,
        mock_bus: MagicMock,
        mock_fleet: MagicMock,
        mock_memory: MagicMock,
    ) -> Any:
        """Create a ReflectionAgent with mocked dependencies.

        Returns:
            ReflectionAgent instance.
        """
        with patch("agents.reflection.PromptBuilder"):
            from agents.reflection import ReflectionAgent

            return ReflectionAgent(mock_bus, mock_fleet, mock_memory)

    @staticmethod
    def _fake_episode(**overrides: Any) -> MagicMock:
        """Build a mock episode with standard attributes.

        Returns:
            MagicMock mimicking an Episode dataclass.
        """
        ep = MagicMock()
        ep.id = overrides.get("id", "ep-1")
        ep.topics = overrides.get("topics", ["coding"])
        ep.emotional_tone = overrides.get("emotional_tone", "engaged")
        ep.summary = overrides.get("summary", "Discussed Python async.")
        ep.key_decisions = overrides.get("key_decisions", ["use asyncio"])
        return ep

    @pytest.mark.asyncio
    async def test_handle_ignores_unknown_type(self, reflector: Any) -> None:
        """handle() silently ignores unrecognized types."""
        msg = _make_message("reflection.unknown")
        await reflector.handle(msg)

    @pytest.mark.asyncio
    async def test_run_reflection_skips_no_episodes(
        self,
        reflector: Any,
        mock_fleet: MagicMock,
    ) -> None:
        """_run_reflection skips LLM call when there are no recent episodes."""
        msg = _make_message("reflection.trigger")
        await reflector.handle(msg)
        mock_fleet.chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_reflection_calls_llm(
        self,
        reflector: Any,
        mock_memory: MagicMock,
        mock_fleet: MagicMock,
    ) -> None:
        """_run_reflection calls the LLM when episodes are available."""
        mock_memory.episodic.get_recent_episodes.return_value = [self._fake_episode()]
        mock_fleet.chat.return_value = FakeLLMResult(content="{}")

        with patch(
            "agents.reflection.extract_json",
            return_value={
                "insights": [],
                "self_model_updates": {},
                "capability_gaps": [],
            },
        ):
            msg = _make_message("reflection.trigger")
            await reflector.handle(msg)

        # 3 calls: reflection analysis + ghostwriter characterization + autobiography synthesis
        assert mock_fleet.chat.await_count == 3

    @pytest.mark.asyncio
    async def test_run_reflection_updates_self_model(
        self,
        reflector: Any,
        mock_memory: MagicMock,
        mock_fleet: MagicMock,
    ) -> None:
        """_run_reflection updates the self-model when insights include updates."""
        mock_memory.episodic.get_recent_episodes.return_value = [self._fake_episode()]
        mock_fleet.chat.return_value = FakeLLMResult(content="{}")

        with patch(
            "agents.reflection.extract_json",
            return_value={
                "insights": ["user likes async"],
                "self_model_updates": {"curiosity": 0.95},
                "capability_gaps": [],
            },
        ):
            msg = _make_message("reflection.trigger")
            await reflector.handle(msg)

        mock_memory.procedural.update_self_model.assert_awaited_once_with(
            {"curiosity": 0.95},
        )

    @pytest.mark.asyncio
    async def test_run_reflection_logs_capability_gaps(
        self,
        reflector: Any,
        mock_memory: MagicMock,
        mock_fleet: MagicMock,
    ) -> None:
        """_run_reflection calls _log_capability_gap for each gap."""
        mock_memory.episodic.get_recent_episodes.return_value = [self._fake_episode()]
        mock_fleet.chat.return_value = FakeLLMResult(content="{}")
        gaps = ["needs calendar integration", "needs email access"]

        with (
            patch(
                "agents.reflection.extract_json",
                return_value={
                    "insights": [],
                    "self_model_updates": {},
                    "capability_gaps": gaps,
                },
            ),
            patch.object(
                reflector,
                "_log_capability_gap",
                new_callable=AsyncMock,
            ) as mock_log,
        ):
            msg = _make_message("reflection.trigger")
            await reflector.handle(msg)

        assert mock_log.await_count == 2
        mock_log.assert_any_await("needs calendar integration")
        mock_log.assert_any_await("needs email access")

    @pytest.mark.asyncio
    async def test_run_reflection_handles_parse_failure(
        self,
        reflector: Any,
        mock_memory: MagicMock,
        mock_fleet: MagicMock,
    ) -> None:
        """_run_reflection returns early when JSON extraction fails."""
        mock_memory.episodic.get_recent_episodes.return_value = [self._fake_episode()]
        mock_fleet.chat.return_value = FakeLLMResult(content="not json")

        with patch("agents.reflection.extract_json", return_value=None):
            msg = _make_message("reflection.trigger")
            await reflector.handle(msg)

        mock_memory.procedural.update_self_model.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_reflection_updates_last_reflection_timestamp(
        self,
        reflector: Any,
        mock_memory: MagicMock,
    ) -> None:
        """_run_reflection updates _last_reflection to current time."""
        mock_memory.episodic.get_recent_episodes.return_value = []
        before = time.time()
        msg = _make_message("reflection.trigger")
        await reflector.handle(msg)

        assert reflector._last_reflection >= before

    @pytest.mark.asyncio
    async def test_schedule_reflection_is_non_blocking(
        self,
        reflector: Any,
    ) -> None:
        """_schedule_reflection returns immediately (asyncio.create_task)."""
        msg = _make_message("reflection.schedule", {"delay_minutes": 999})

        with patch.object(reflector, "_run_reflection", new_callable=AsyncMock):
            t0 = asyncio.get_event_loop().time()
            await reflector.handle(msg)
            elapsed = asyncio.get_event_loop().time() - t0

        assert elapsed < 1.0
        assert hasattr(reflector, "_scheduled_task")
        reflector._scheduled_task.cancel()

    @pytest.mark.asyncio
    async def test_log_capability_gap_writes_jsonl(
        self,
        reflector: Any,
    ) -> None:
        """_log_capability_gap writes a JSON-lines entry."""
        m = mock_open()
        with patch("pathlib.Path.open", m):
            await reflector._log_capability_gap("needs web scraping")

        m.assert_called_once_with("a")
        handle = m()
        handle.write.assert_called_once()
        written = handle.write.call_args[0][0]
        entry = json.loads(written.strip())
        assert entry["gap"] == "needs web scraping"
        assert entry["source"] == "reflection"
        assert "timestamp" in entry


# ===================================================================
# OnboardingAgent tests
# ===================================================================


class TestOnboardingAgent:
    """Tests for agents.onboarding.OnboardingAgent."""

    @pytest.fixture()
    def onboarder(
        self,
        mock_bus: MagicMock,
        mock_fleet: MagicMock,
        mock_memory: MagicMock,
    ) -> Any:
        """Create an OnboardingAgent with mocked dependencies.

        Returns:
            OnboardingAgent instance.
        """
        with patch("agents.onboarding.PromptBuilder"):
            from agents.onboarding import OnboardingAgent

            return OnboardingAgent(mock_bus, mock_fleet, mock_memory)

    @pytest.mark.asyncio
    async def test_handle_dispatches_onboarding_start(
        self,
        onboarder: Any,
    ) -> None:
        """handle() invokes run_onboarding when type is 'onboarding.start'."""
        speak = AsyncMock()
        listen = AsyncMock(return_value="hi")

        with patch(
            "agents.onboarding.run_onboarding",
            new_callable=AsyncMock,
        ) as mock_run:
            msg = _make_message(
                "onboarding.start",
                {
                    "speak": speak,
                    "listen": listen,
                },
            )
            await onboarder.handle(msg)

        mock_run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_warns_on_missing_callbacks(
        self,
        onboarder: Any,
    ) -> None:
        """handle() does not raise when speak/listen are missing."""
        msg = _make_message("onboarding.start", {})
        await onboarder.handle(msg)  # logs warning, does not crash

    @pytest.mark.asyncio
    async def test_handle_ignores_unknown_type(self, onboarder: Any) -> None:
        """handle() is a no-op for unrecognized types."""
        msg = _make_message("onboarding.unknown")
        await onboarder.handle(msg)


class TestOnboardingHelpers:
    """Tests for standalone helper functions in agents.onboarding."""

    def test_extract_json_block_valid(self) -> None:
        """_extract_json_block extracts valid JSON from a fenced block."""
        from agents.onboarding import _extract_json_block

        text = 'Context.\n```json\n{"facts": {"name": "Bob"}}\n```\nMore.'
        result = _extract_json_block(text)
        assert result == {"facts": {"name": "Bob"}}

    def test_extract_json_block_no_block(self) -> None:
        """_extract_json_block returns None when no JSON block is present."""
        from agents.onboarding import _extract_json_block

        assert _extract_json_block("plain text only") is None

    def test_extract_json_block_invalid_json(self) -> None:
        """_extract_json_block returns None for malformed JSON."""
        from agents.onboarding import _extract_json_block

        assert _extract_json_block("```json\n{broken\n```") is None

    def test_strip_json_block(self) -> None:
        """_strip_json_block removes the JSON fence from text."""
        from agents.onboarding import _strip_json_block

        text = 'Hello!\n```json\n{"facts": {}}\n```\nGoodbye.'
        result = _strip_json_block(text)
        assert "```json" not in result
        assert "Hello!" in result
        assert "Goodbye." in result

    @pytest.mark.asyncio
    async def test_save_extracted_facts(self) -> None:
        """_save_extracted_facts persists facts and profile updates."""
        from agents.onboarding import _save_extracted_facts

        memory = MagicMock()
        memory.procedural.set_user_fact = AsyncMock()
        memory.procedural.update_user_profile = AsyncMock()

        data = {
            "facts": {"name": "Alice", "hobby": "painting"},
            "profile_updates": {"warmth": 0.9},
        }
        await _save_extracted_facts(memory, data)

        assert memory.procedural.set_user_fact.await_count == 2
        memory.procedural.update_user_profile.assert_awaited_once_with({"warmth": 0.9})

    @pytest.mark.asyncio
    async def test_save_extracted_facts_skips_empty_values(self) -> None:
        """_save_extracted_facts skips facts with falsy values."""
        from agents.onboarding import _save_extracted_facts

        memory = MagicMock()
        memory.procedural.set_user_fact = AsyncMock()
        memory.procedural.update_user_profile = AsyncMock()

        data = {"facts": {"name": "Alice", "empty_field": ""}, "profile_updates": {}}
        await _save_extracted_facts(memory, data)

        memory.procedural.set_user_fact.assert_awaited_once_with("name", "Alice")
        memory.procedural.update_user_profile.assert_not_awaited()


# ===================================================================
# MonitorAgent tests
# ===================================================================


class TestMonitorAgent:
    """Tests for agents.monitor.MonitorAgent."""

    @pytest.fixture()
    def monitor(
        self,
        mock_bus: MagicMock,
        mock_fleet: MagicMock,
        mock_memory: MagicMock,
    ) -> Any:
        """Create a MonitorAgent with mocked dependencies.

        Returns:
            MonitorAgent instance.
        """
        from agents.monitor import MonitorAgent

        return MonitorAgent(mock_bus, mock_fleet, mock_memory)

    @pytest.mark.asyncio
    async def test_heartbeat_tracks_agent(self, monitor: Any) -> None:
        """agent.heartbeat stores a timestamp keyed by agent name."""
        before = time.time()
        msg = _make_message(
            "agent.heartbeat",
            {
                "agent": "PlannerAgent",
                "timestamp": 1000.0,
            },
        )
        await monitor.handle(msg)

        assert "PlannerAgent" in monitor._heartbeats
        assert monitor._heartbeats["PlannerAgent"] >= before

    @pytest.mark.asyncio
    async def test_heartbeat_multiple_agents(self, monitor: Any) -> None:
        """Heartbeats from multiple agents are tracked independently."""
        for name in ("AgentA", "AgentB", "AgentC"):
            msg = _make_message("agent.heartbeat", {"agent": name})
            await monitor.handle(msg)

        assert set(monitor._heartbeats.keys()) == {"AgentA", "AgentB", "AgentC"}

    @pytest.mark.asyncio
    async def test_heartbeat_updates_existing(self, monitor: Any) -> None:
        """Repeated heartbeats update the stored timestamp."""
        msg = _make_message("agent.heartbeat", {"agent": "A"})
        await monitor.handle(msg)
        first_ts = monitor._heartbeats["A"]

        await asyncio.sleep(0.01)
        await monitor.handle(msg)
        assert monitor._heartbeats["A"] >= first_ts

    @pytest.mark.asyncio
    async def test_status_request_sends_report(
        self,
        monitor: Any,
        mock_bus: MagicMock,
    ) -> None:
        """monitor.status_request sends a status report to the requester."""
        monitor._heartbeats = {"AgentA": time.time()}

        with patch("agents.monitor.psutil") as mock_psutil:
            mock_ram = MagicMock()
            mock_ram.used = 32e9
            mock_ram.total = 64e9
            mock_psutil.virtual_memory.return_value = mock_ram
            mock_psutil.cpu_percent.return_value = 42.5

            msg = _make_message("monitor.status_request", sender="Dashboard")
            await monitor.handle(msg)

        sent = mock_bus.send_to.call_args
        assert sent.kwargs["recipient"] == "Dashboard"
        assert sent.kwargs["msg_type"] == "monitor.status_report"
        payload = sent.kwargs["payload"]
        assert payload["cpu_percent"] == 42.5
        assert "ram_used_gb" in payload
        assert "agent_heartbeats" in payload

    @pytest.mark.asyncio
    async def test_unknown_type_ignored(
        self,
        monitor: Any,
        mock_bus: MagicMock,
    ) -> None:
        """MonitorAgent ignores unrecognized message types."""
        msg = _make_message("monitor.unknown_op")
        await monitor.handle(msg)
        mock_bus.send_to.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_creates_monitoring_loop(
        self,
        monitor: Any,
        mock_bus: MagicMock,
    ) -> None:
        """start() creates an additional monitoring loop task."""
        with patch("agents.base.ACTIVE_AGENTS"), patch("asyncio.create_task") as mock_create_task:
            await monitor.start()

        # BaseAgent.start creates heartbeat, MonitorAgent.start creates monitoring loop
        assert mock_create_task.call_count >= 1
        monitor._running = False
        if monitor._task:
            monitor._task.cancel()


# ===================================================================
# ResearchAgent tests
# ===================================================================


class TestResearchAgent:
    """Tests for agents.research.ResearchAgent."""

    @pytest.fixture()
    def researcher(
        self,
        mock_bus: MagicMock,
        mock_fleet: MagicMock,
        mock_memory: MagicMock,
    ) -> Any:
        """Create a ResearchAgent with mocked dependencies.

        Returns:
            ResearchAgent instance.
        """
        with patch("agents.research.PromptBuilder"):
            from agents.research import ResearchAgent

            return ResearchAgent(mock_bus, mock_fleet, mock_memory)

    @pytest.mark.asyncio
    async def test_handle_dispatches_agent_task(
        self,
        researcher: Any,
        mock_fleet: MagicMock,
    ) -> None:
        """handle() dispatches 'agent.task' to _research."""
        mock_fleet.chat.return_value = FakeLLMResult(content="findings")

        with (
            patch.object(
                researcher,
                "_retrieve_rag_context",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch.object(researcher, "_web_search", new_callable=AsyncMock, return_value=""),
        ):
            msg = _make_message("agent.task", {"task": "Explain quantum"})
            await researcher.handle(msg)

        mock_fleet.chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_ignores_unknown_type(self, researcher: Any) -> None:
        """handle() ignores non-'agent.task' messages."""
        msg = _make_message("research.custom")
        await researcher.handle(msg)

    @pytest.mark.asyncio
    async def test_research_sends_result_to_planner(
        self,
        researcher: Any,
        mock_fleet: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """_research sends planner.subtask_result when plan_id is present."""
        mock_fleet.chat.return_value = FakeLLMResult(content="synthesis")

        with (
            patch.object(
                researcher,
                "_retrieve_rag_context",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch.object(researcher, "_web_search", new_callable=AsyncMock, return_value=""),
        ):
            msg = _make_message(
                "agent.task",
                {
                    "task": "topic",
                    "plan_id": "plan-xyz",
                    "step_index": 3,
                },
            )
            await researcher.handle(msg)

        sent = mock_bus.send_to.call_args
        assert sent.kwargs["recipient"] == "PlannerAgent"
        assert sent.kwargs["msg_type"] == "planner.subtask_result"
        assert sent.kwargs["payload"]["plan_id"] == "plan-xyz"
        assert sent.kwargs["payload"]["step_index"] == 3

    @pytest.mark.asyncio
    async def test_research_no_planner_msg_without_plan_id(
        self,
        researcher: Any,
        mock_fleet: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """_research does not send to PlannerAgent when no plan_id."""
        mock_fleet.chat.return_value = FakeLLMResult(content="result")

        with (
            patch.object(
                researcher,
                "_retrieve_rag_context",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch.object(researcher, "_web_search", new_callable=AsyncMock, return_value=""),
        ):
            msg = _make_message("agent.task", {"task": "standalone"})
            await researcher.handle(msg)

        mock_bus.send_to.assert_not_called()

    @pytest.mark.asyncio
    async def test_research_runs_rag_and_web_in_parallel(
        self,
        researcher: Any,
        mock_fleet: MagicMock,
    ) -> None:
        """_research runs RAG retrieval and web search concurrently."""
        rag_mock = AsyncMock(return_value="RAG context")
        web_mock = AsyncMock(return_value="Web results")
        mock_fleet.chat.return_value = FakeLLMResult(content="synthesized")

        with (
            patch.object(researcher, "_retrieve_rag_context", rag_mock),
            patch.object(researcher, "_web_search", web_mock),
        ):
            msg = _make_message("agent.task", {"task": "topic"})
            await researcher.handle(msg)

        rag_mock.assert_awaited_once()
        web_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retrieve_rag_context_no_retriever(
        self,
        researcher: Any,
        mock_memory: MagicMock,
    ) -> None:
        """_retrieve_rag_context returns empty string when retriever is None."""
        del mock_memory._retriever
        result = await researcher._retrieve_rag_context("query")
        assert result == ""

    @pytest.mark.asyncio
    async def test_research_handles_rag_exception(
        self,
        researcher: Any,
        mock_fleet: MagicMock,
    ) -> None:
        """_research handles RAG exceptions via return_exceptions in gather."""
        mock_fleet.chat.return_value = FakeLLMResult(content="fallback")

        with (
            patch.object(
                researcher,
                "_retrieve_rag_context",
                new_callable=AsyncMock,
                side_effect=RuntimeError("RAG failed"),
            ),
            patch.object(
                researcher,
                "_web_search",
                new_callable=AsyncMock,
                return_value="",
            ),
        ):
            msg = _make_message("agent.task", {"task": "research"})
            await researcher.handle(msg)

        mock_fleet.chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_research_includes_context_in_prompt(
        self,
        researcher: Any,
        mock_fleet: MagicMock,
    ) -> None:
        """_research prepends RAG and web context to the prompt when available."""
        mock_fleet.chat.return_value = FakeLLMResult(content="answer")
        # PromptBuilder is mocked; give build_research_prompt a real string
        # so string concatenation in _research produces a real str.
        researcher._prompts.build_research_prompt.return_value = "RESEARCH_PROMPT"

        with (
            patch.object(
                researcher,
                "_retrieve_rag_context",
                new_callable=AsyncMock,
                return_value="RAG data",
            ),
            patch.object(
                researcher,
                "_web_search",
                new_callable=AsyncMock,
                return_value="Web data",
            ),
        ):
            msg = _make_message("agent.task", {"task": "query"})
            await researcher.handle(msg)

        call_kwargs = mock_fleet.chat.call_args.kwargs
        prompt_content = call_kwargs["messages"][0].content
        assert "KNOWLEDGE BASE RESULTS" in prompt_content
        assert "WEB SEARCH RESULTS" in prompt_content


# ===================================================================
# CodeAgent tests
# ===================================================================


class TestCodeAgent:
    """Tests for agents.code_agent.CodeAgent."""

    @pytest.fixture()
    def coder(
        self,
        mock_bus: MagicMock,
        mock_fleet: MagicMock,
        mock_memory: MagicMock,
    ) -> Any:
        """Create a CodeAgent with mocked dependencies.

        Returns:
            CodeAgent instance.
        """
        with patch("agents.code_agent.PromptBuilder"):
            from agents.code_agent import CodeAgent

            return CodeAgent(mock_bus, mock_fleet, mock_memory)

    # -- _extract_code_blocks (static method) --

    def test_extract_code_blocks_python(self) -> None:
        """Extracts a single Python fenced code block."""
        from agents.code_agent import CodeAgent

        text = 'Code:\n```python\nprint("hello")\n```\nDone.'
        blocks = CodeAgent._extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0] == 'print("hello")'

    def test_extract_code_blocks_multiple(self) -> None:
        """Extracts multiple Python code blocks."""
        from agents.code_agent import CodeAgent

        text = "```python\nx = 1\n```\ntext\n```python\ny = 2\n```"
        blocks = CodeAgent._extract_code_blocks(text)
        assert len(blocks) == 2
        assert blocks[0] == "x = 1"
        assert blocks[1] == "y = 2"

    def test_extract_code_blocks_no_language_tag(self) -> None:
        """Extracts blocks without an explicit language tag."""
        from agents.code_agent import CodeAgent

        blocks = CodeAgent._extract_code_blocks("```\nimport os\n```")
        assert len(blocks) == 1
        assert blocks[0] == "import os"

    def test_extract_code_blocks_empty_result(self) -> None:
        """Returns empty list when no fenced blocks are found."""
        from agents.code_agent import CodeAgent

        assert CodeAgent._extract_code_blocks("no code here") == []

    def test_extract_code_blocks_custom_language(self) -> None:
        """Extracts blocks with a non-python language tag."""
        from agents.code_agent import CodeAgent

        text = '```javascript\nconsole.log("hi")\n```'
        blocks = CodeAgent._extract_code_blocks(text, language="javascript")
        assert len(blocks) == 1
        assert 'console.log("hi")' in blocks[0]

    def test_extract_code_blocks_strips_whitespace(self) -> None:
        """Extracted blocks have leading/trailing whitespace stripped."""
        from agents.code_agent import CodeAgent

        text = "```python\n  \n  x = 1\n  \n```"
        blocks = CodeAgent._extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0] == "x = 1"

    # -- handle() dispatch --

    @pytest.mark.asyncio
    async def test_handle_agent_task(
        self,
        coder: Any,
        mock_fleet: MagicMock,
    ) -> None:
        """handle() dispatches 'agent.task' to _handle_code_task."""
        mock_fleet.chat.return_value = FakeLLMResult(content="```python\nprint(1)\n```")

        with patch.object(coder, "_run_sandboxed", new_callable=AsyncMock, return_value="1\n"):
            msg = _make_message("agent.task", {"task": "print 1"})
            await coder.handle(msg)

        mock_fleet.chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_code_request(
        self,
        coder: Any,
        mock_fleet: MagicMock,
    ) -> None:
        """handle() dispatches 'code.request' to _handle_code_task."""
        mock_fleet.chat.return_value = FakeLLMResult(content="no code")

        msg = _make_message("code.request", {"task": "explain async"})
        await coder.handle(msg)
        mock_fleet.chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_ignores_unknown_type(self, coder: Any) -> None:
        """handle() is a no-op for unrecognized types."""
        msg = _make_message("code.unknown")
        await coder.handle(msg)

    # -- _handle_code_task --

    @pytest.mark.asyncio
    async def test_code_task_sends_result_to_planner(
        self,
        coder: Any,
        mock_fleet: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """Sends result to PlannerAgent when plan_id is present."""
        mock_fleet.chat.return_value = FakeLLMResult(content="```python\nx=1\n```")

        with patch.object(coder, "_run_sandboxed", new_callable=AsyncMock, return_value="ok"):
            msg = _make_message(
                "agent.task",
                {
                    "task": "compute",
                    "plan_id": "plan-code",
                    "step_index": 2,
                },
            )
            await coder.handle(msg)

        sent = mock_bus.send_to.call_args
        assert sent.kwargs["recipient"] == "PlannerAgent"
        assert sent.kwargs["payload"]["plan_id"] == "plan-code"
        assert sent.kwargs["payload"]["step_index"] == 2

    @pytest.mark.asyncio
    async def test_code_task_no_planner_without_plan_id(
        self,
        coder: Any,
        mock_fleet: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """Does not send to PlannerAgent when plan_id is absent."""
        mock_fleet.chat.return_value = FakeLLMResult(content="```python\nx=1\n```")

        with patch.object(coder, "_run_sandboxed", new_callable=AsyncMock, return_value="ok"):
            msg = _make_message("agent.task", {"task": "just generate"})
            await coder.handle(msg)

        mock_bus.send_to.assert_not_called()

    @pytest.mark.asyncio
    async def test_code_task_skips_sandbox_when_execute_false(
        self,
        coder: Any,
        mock_fleet: MagicMock,
    ) -> None:
        """Skips sandbox execution when execute=False."""
        mock_fleet.chat.return_value = FakeLLMResult(content="```python\nprint(1)\n```")

        with patch.object(coder, "_run_sandboxed", new_callable=AsyncMock) as mock_sb:
            msg = _make_message("agent.task", {"task": "gen", "execute": False})
            await coder.handle(msg)

        mock_sb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_code_task_skips_sandbox_for_non_python(
        self,
        coder: Any,
        mock_fleet: MagicMock,
    ) -> None:
        """Skips sandbox for non-Python languages."""
        mock_fleet.chat.return_value = FakeLLMResult(
            content="```javascript\nconsole.log(1)\n```",
        )

        with patch.object(coder, "_run_sandboxed", new_callable=AsyncMock) as mock_sb:
            msg = _make_message(
                "agent.task",
                {
                    "task": "JS code",
                    "language": "javascript",
                },
            )
            await coder.handle(msg)

        mock_sb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_code_task_appends_execution_output(
        self,
        coder: Any,
        mock_fleet: MagicMock,
        mock_bus: MagicMock,
    ) -> None:
        """Execution output is appended to the final result."""
        mock_fleet.chat.return_value = FakeLLMResult(content="```python\nprint(42)\n```")

        with patch.object(
            coder,
            "_run_sandboxed",
            new_callable=AsyncMock,
            return_value="42\n",
        ):
            msg = _make_message(
                "agent.task",
                {
                    "task": "compute",
                    "plan_id": "p",
                    "step_index": 1,
                },
            )
            await coder.handle(msg)

        result_text = mock_bus.send_to.call_args.kwargs["payload"]["result"]
        assert "Execution Output" in result_text
        assert "42" in result_text

    @pytest.mark.asyncio
    async def test_run_sandboxed_handles_import_error(
        self,
        coder: Any,
    ) -> None:
        """_run_sandboxed returns an error string when sandbox is unavailable."""
        with patch.dict(
            "sys.modules",
            {"plugins.sandbox": None},
        ):
            result = await coder._run_sandboxed("print(1)")

        assert "failed" in result.lower() or "error" in result.lower()
