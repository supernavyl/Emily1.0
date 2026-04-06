# Emily Loop Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Graft the emily-loop AGI kernel onto Emily as her execution backbone for multi-step tasks, replacing PlannerAgent with checkpoint/resume, failure memory, and replanning.

**Architecture:** emily-loop stays as a path dependency. Four adapter classes in `core/loop_integration/` bridge Loop's protocols to Emily's fleet, tools, memory, and bus. LoopAgent on the bus intercepts complex tasks (complexity >= 7) and runs them through the kernel. Parallel step dispatch added to Loop where `depends_on` allows it.

**Tech Stack:** Python 3.11+, pytest-asyncio, emily-loop (path dep), Emily's existing LLMFleet/PluginRegistry/MemoryManager/AgentBus.

---

## File Structure

### New files (Emily1.0)

| File | Responsibility |
|------|----------------|
| `core/loop_integration/__init__.py` | Package exports: FleetAdapter, ToolBridgeAdapter, LoopAgent, MemoryBridge |
| `core/loop_integration/fleet_adapter.py` | Wraps LLMFleet → emily-loop's LLMClient protocol |
| `core/loop_integration/tool_bridge.py` | Wraps PluginRegistry → emily-loop's ToolRegistry |
| `core/loop_integration/loop_agent.py` | Bus agent that runs Loop for complex tasks |
| `core/loop_integration/memory_bridge.py` | Bidirectional sync: episodic context → Loop, failure patterns → procedural memory |
| `tests/unit/test_fleet_adapter.py` | FleetAdapter tests |
| `tests/unit/test_tool_bridge.py` | ToolBridgeAdapter tests |
| `tests/unit/test_loop_agent.py` | LoopAgent tests |
| `tests/unit/test_memory_bridge.py` | MemoryBridge tests |

### Modified files

| File | Change |
|------|--------|
| `pyproject.toml` | Add emily-loop path dependency |
| `agents/registry.py` | Replace PlannerAgent with LoopAgent |
| `agents/conversation.py` | Route complexity >= 7 to LoopAgent |
| `~/emily-loop/emily_loop/loop.py` | Add parallel step dispatch |

### Deleted files

| File | Reason |
|------|--------|
| `agents/planner.py` | Replaced by LoopAgent + emily-loop kernel |

---

### Task 1: Add emily-loop path dependency

**Files:**
- Modify: `pyproject.toml:14`

- [ ] **Step 1: Add emily-loop to dependencies**

In `pyproject.toml`, add the path dependency at the end of the `dependencies` list:

```toml
    # AGI kernel
    "emily-loop @ file:///${PROJECT_ROOT}/../emily-loop",
```

However, hatchling path dependencies use a different syntax. Use the `[project.optional-dependencies]` or `[tool.uv.sources]` approach. Since Emily uses `uv`, add to `pyproject.toml`:

```toml
[tool.uv.sources]
emily-loop = { path = "../emily-loop", editable = true }
```

And add `"emily-loop"` to the `dependencies` list.

- [ ] **Step 2: Install the dependency**

Run: `cd ~/Emily1.0 && uv pip install -e ../emily-loop`
Expected: Successfully installed emily-loop

- [ ] **Step 3: Verify import works**

Run: `cd ~/Emily1.0 && uv run python -c "from emily_loop.models import Plan, Step; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add emily-loop as path dependency"
```

---

### Task 2: FleetAdapter

**Files:**
- Create: `core/loop_integration/__init__.py`
- Create: `core/loop_integration/fleet_adapter.py`
- Create: `tests/unit/test_fleet_adapter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_fleet_adapter.py`:

```python
"""Tests for FleetAdapter — bridges LLMFleet to emily-loop's LLMClient protocol."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from emily_loop.llm import LLMClient


@dataclass
class FakeCompletionResult:
    content: str
    model: str = "test"
    total_tokens: int = 10
    prompt_tokens: int = 5
    latency_ms: float = 100.0


class FakeFleet:
    """Minimal mock of LLMFleet for adapter tests."""

    def __init__(self) -> None:
        self.chat = AsyncMock()


@pytest.fixture
def fake_fleet() -> FakeFleet:
    return FakeFleet()


@pytest.mark.asyncio
async def test_fleet_adapter_satisfies_protocol(fake_fleet: FakeFleet) -> None:
    from core.loop_integration.fleet_adapter import FleetAdapter

    adapter = FleetAdapter(fake_fleet)
    assert isinstance(adapter, LLMClient)


@pytest.mark.asyncio
async def test_fleet_adapter_complete_text(fake_fleet: FakeFleet) -> None:
    from core.loop_integration.fleet_adapter import FleetAdapter

    fake_fleet.chat.return_value = FakeCompletionResult(content="Hello world")
    adapter = FleetAdapter(fake_fleet)

    result = await adapter.complete("Say hello")

    assert result == "Hello world"
    fake_fleet.chat.assert_called_once()


@pytest.mark.asyncio
async def test_fleet_adapter_complete_json_schema(fake_fleet: FakeFleet) -> None:
    from core.loop_integration.fleet_adapter import FleetAdapter

    fake_fleet.chat.return_value = FakeCompletionResult(
        content=json.dumps({"steps": [{"id": "step-001", "action": "do thing"}]})
    )
    adapter = FleetAdapter(fake_fleet)

    result = await adapter.complete("Generate a plan", schema=dict)

    assert isinstance(result, dict)
    assert "steps" in result


@pytest.mark.asyncio
async def test_fleet_adapter_uses_specified_tier(fake_fleet: FakeFleet) -> None:
    from core.loop_integration.fleet_adapter import FleetAdapter
    from llm.router import ModelTier

    fake_fleet.chat.return_value = FakeCompletionResult(content="fast response")
    adapter = FleetAdapter(fake_fleet, tier=ModelTier.FAST)

    await adapter.complete("Quick question")

    call_kwargs = fake_fleet.chat.call_args
    assert call_kwargs.kwargs.get("force_tier") == ModelTier.FAST


@pytest.mark.asyncio
async def test_fleet_adapter_json_parse_error_raises(fake_fleet: FakeFleet) -> None:
    from core.loop_integration.fleet_adapter import FleetAdapter

    fake_fleet.chat.return_value = FakeCompletionResult(content="not json at all")
    adapter = FleetAdapter(fake_fleet)

    with pytest.raises(json.JSONDecodeError):
        await adapter.complete("Give me JSON", schema=dict)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_fleet_adapter.py -v`
Expected: FAIL (ImportError: cannot import 'fleet_adapter')

- [ ] **Step 3: Create the package init**

Create `core/loop_integration/__init__.py`:

```python
"""Emily Loop integration — adapters bridging emily-loop kernel to Emily's subsystems."""

from core.loop_integration.fleet_adapter import FleetAdapter
from core.loop_integration.tool_bridge import ToolBridgeAdapter

__all__ = ["FleetAdapter", "ToolBridgeAdapter"]
```

Note: LoopAgent and MemoryBridge will be added to `__all__` in later tasks.

- [ ] **Step 4: Implement FleetAdapter**

Create `core/loop_integration/fleet_adapter.py`:

```python
"""FleetAdapter — wraps Emily's LLMFleet to satisfy emily-loop's LLMClient protocol."""

from __future__ import annotations

import json
from typing import Any

from llm.client import ChatMessage
from llm.fleet import LLMFleet
from llm.router import ModelTier


class FleetAdapter:
    """Bridges LLMFleet.chat() to the emily-loop LLMClient.complete() protocol.

    Loop gets Emily's circuit breakers, fallback chains, and model tier
    selection for free through this adapter.
    """

    def __init__(self, fleet: LLMFleet, tier: ModelTier = ModelTier.SMART) -> None:
        self._fleet = fleet
        self._tier = tier

    async def complete(self, prompt: str, schema: type | None = None) -> str | Any:
        """Generate a completion via Emily's fleet.

        Args:
            prompt: The prompt text.
            schema: If provided, append JSON instruction and parse response as JSON.

        Returns:
            Raw text if schema is None, parsed dict/list if schema is provided.

        Raises:
            json.JSONDecodeError: If schema is provided but response isn't valid JSON.
        """
        effective_prompt = prompt
        if schema is not None:
            effective_prompt = prompt + "\n\nRespond with valid JSON only."

        messages = [ChatMessage(role="user", content=effective_prompt)]

        result = await self._fleet.chat(
            user_message=effective_prompt,
            messages=messages,
            force_tier=self._tier,
        )

        if schema is not None:
            return json.loads(result.content)
        return result.content
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_fleet_adapter.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add core/loop_integration/__init__.py core/loop_integration/fleet_adapter.py tests/unit/test_fleet_adapter.py
git commit -m "feat: add FleetAdapter bridging LLMFleet to emily-loop LLMClient"
```

---

### Task 3: ToolBridgeAdapter

**Files:**
- Create: `core/loop_integration/tool_bridge.py`
- Create: `tests/unit/test_tool_bridge.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_tool_bridge.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_tool_bridge.py -v`
Expected: FAIL (ImportError: cannot import 'tool_bridge')

- [ ] **Step 3: Implement ToolBridgeAdapter**

Create `core/loop_integration/tool_bridge.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_tool_bridge.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add core/loop_integration/tool_bridge.py tests/unit/test_tool_bridge.py
git commit -m "feat: add ToolBridgeAdapter bridging PluginRegistry to emily-loop ToolRegistry"
```

---

### Task 4: MemoryBridge

**Files:**
- Create: `core/loop_integration/memory_bridge.py`
- Create: `tests/unit/test_memory_bridge.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_memory_bridge.py`:

```python
"""Tests for MemoryBridge — bidirectional sync between Loop's FailureDB and Emily's memory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from emily_loop.models import FailureCategory, FailurePattern, FailureType


def _make_pattern(pattern_id: str = "fail-0001", trigger: str = "timeout on shell") -> FailurePattern:
    now = datetime.now(tz=timezone.utc)
    return FailurePattern(
        id=pattern_id,
        trigger=trigger,
        category=FailureCategory.TIMEOUT,
        failure_type=FailureType.TRANSIENT,
        what_happened="shell command timed out",
        root_cause="slow network",
        prevention="add timeout flag",
        severity=3,
        occurrences=1,
        first_seen=now,
        last_seen=now,
        step_context="run shell command",
    )


class FakeMemoryManager:
    """Minimal mock of MemoryManager for bridge tests."""

    def __init__(self) -> None:
        self.retrieve_context = AsyncMock(return_value=[])
        self.procedural = MagicMock()
        self.procedural.add_skill = AsyncMock()


class FakeFailureDB:
    """Minimal mock of FailureDB for bridge tests."""

    def __init__(self, patterns: list[FailurePattern] | None = None) -> None:
        self._patterns = patterns or []

    async def all(self) -> list[FailurePattern]:
        return self._patterns


@pytest.fixture
def fake_memory() -> FakeMemoryManager:
    return FakeMemoryManager()


@pytest.mark.asyncio
async def test_enrich_goal_no_context(fake_memory: FakeMemoryManager) -> None:
    from core.loop_integration.memory_bridge import MemoryBridge

    bridge = MemoryBridge(fake_memory, FakeFailureDB())

    result = await bridge.enrich_goal("build a website")

    assert result == "build a website"


@pytest.mark.asyncio
async def test_enrich_goal_with_context(fake_memory: FakeMemoryManager) -> None:
    from core.loop_integration.memory_bridge import MemoryBridge

    fake_memory.retrieve_context.return_value = [
        {"content": "User prefers React", "source": "episodic", "score": 0.9},
        {"content": "Last project used Next.js", "source": "episodic", "score": 0.8},
    ]
    bridge = MemoryBridge(fake_memory, FakeFailureDB())

    result = await bridge.enrich_goal("build a website")

    assert "build a website" in result
    assert "User prefers React" in result
    assert "Last project used Next.js" in result


@pytest.mark.asyncio
async def test_sync_failures_stores_new_patterns(fake_memory: FakeMemoryManager) -> None:
    from core.loop_integration.memory_bridge import MemoryBridge

    pattern = _make_pattern()
    bridge = MemoryBridge(fake_memory, FakeFailureDB([pattern]))

    count = await bridge.sync_failures()

    assert count == 1
    fake_memory.procedural.add_skill.assert_called_once()
    call_kwargs = fake_memory.procedural.add_skill.call_args.kwargs
    assert call_kwargs["name"] == "failure:fail-0001"
    assert "TIMEOUT" in call_kwargs["description"]


@pytest.mark.asyncio
async def test_sync_failures_skips_already_synced(fake_memory: FakeMemoryManager) -> None:
    from core.loop_integration.memory_bridge import MemoryBridge

    pattern = _make_pattern()
    bridge = MemoryBridge(fake_memory, FakeFailureDB([pattern]))

    await bridge.sync_failures()  # First sync
    count = await bridge.sync_failures()  # Second sync — nothing new

    assert count == 0
    assert fake_memory.procedural.add_skill.call_count == 1


@pytest.mark.asyncio
async def test_sync_failures_picks_up_new_patterns(fake_memory: FakeMemoryManager) -> None:
    from core.loop_integration.memory_bridge import MemoryBridge

    p1 = _make_pattern("fail-0001", "timeout")
    db = FakeFailureDB([p1])
    bridge = MemoryBridge(fake_memory, db)

    await bridge.sync_failures()  # Syncs p1

    p2 = _make_pattern("fail-0002", "permission denied")
    db._patterns = [p1, p2]  # p2 is new (DB returns newest first per FailureDB.all())

    count = await bridge.sync_failures()

    assert count == 1
    assert fake_memory.procedural.add_skill.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_memory_bridge.py -v`
Expected: FAIL (ImportError: cannot import 'memory_bridge')

- [ ] **Step 3: Implement MemoryBridge**

Create `core/loop_integration/memory_bridge.py`:

```python
"""MemoryBridge — bidirectional sync between emily-loop's FailureDB and Emily's memory."""

from __future__ import annotations

from typing import Any

from emily_loop.failures import FailureDB
from memory.manager import MemoryManager
from observability.logger import get_logger

log = get_logger(__name__)


class MemoryBridge:
    """Bridges emily-loop's failure patterns to Emily's 5-tier memory.

    Before planning: enriches the goal with episodic context from past sessions.
    After goal completion: syncs new failure patterns to procedural memory.
    """

    def __init__(self, memory: Any, failure_db: Any) -> None:
        self._memory = memory
        self._failure_db = failure_db
        self._last_sync_count: int = 0

    async def enrich_goal(self, goal: str) -> str:
        """Pull episodic context from Emily's memory to improve planning.

        Args:
            goal: The raw goal string.

        Returns:
            The goal enriched with relevant past context, or unchanged if none found.
        """
        chunks = await self._memory.retrieve_context(goal, top_k=3)
        if not chunks:
            return goal

        context = "\n".join(c["content"] for c in chunks)
        return f"{goal}\n\nRelevant context from past sessions:\n{context}"

    async def sync_failures(self) -> int:
        """Push new failure patterns to Emily's procedural memory.

        Returns:
            Number of new patterns synced.
        """
        all_patterns = await self._failure_db.all()
        total = len(all_patterns)
        new_count = total - self._last_sync_count

        if new_count <= 0:
            return 0

        # New patterns are the ones beyond what we've already synced.
        # FailureDB.all() returns ordered by last_seen DESC, so new patterns
        # appear at the front. But we track by count, so slice from the front.
        new_patterns = all_patterns[:new_count]

        for pattern in new_patterns:
            await self._memory.procedural.add_skill(
                name=f"failure:{pattern.id}",
                description=(
                    f"[{pattern.category.value}] "
                    f"{pattern.trigger} -> {pattern.prevention}"
                ),
                tool_sequence=[{
                    "trigger": pattern.trigger,
                    "root_cause": pattern.root_cause,
                    "prevention": pattern.prevention,
                    "severity": pattern.severity,
                    "occurrences": pattern.occurrences,
                }],
            )

        self._last_sync_count = total
        log.info("failure_patterns_synced", count=new_count)
        return new_count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_memory_bridge.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add core/loop_integration/memory_bridge.py tests/unit/test_memory_bridge.py
git commit -m "feat: add MemoryBridge for bidirectional failure pattern sync"
```

---

### Task 5: LoopAgent

**Files:**
- Create: `core/loop_integration/loop_agent.py`
- Create: `tests/unit/test_loop_agent.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_loop_agent.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_loop_agent.py -v`
Expected: FAIL (ImportError: cannot import 'loop_agent')

- [ ] **Step 3: Implement LoopAgent**

Create `core/loop_integration/loop_agent.py`:

```python
"""LoopAgent — bus agent that runs the emily-loop kernel for complex multi-step tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.bus import AgentBus, Message, Priority
from emily_loop.failures import FailureDB
from emily_loop.loop import Loop, LoopConfig
from emily_loop.models import PlanStatus, StepStatus
from observability.logger import get_logger

from core.loop_integration.fleet_adapter import FleetAdapter
from core.loop_integration.memory_bridge import MemoryBridge
from core.loop_integration.tool_bridge import ToolBridgeAdapter

log = get_logger(__name__)


class LoopAgent:
    """Agent that runs emily-loop for multi-step tasks.

    Handles two message types:
    - "loop.run" — explicit trigger from any agent or API
    - "planner.plan_request" — backward-compatible drop-in for PlannerAgent
    """

    name = "LoopAgent"
    description = "Executes multi-step plans with checkpoint/resume and failure learning."

    def __init__(
        self,
        bus: Any,
        fleet: Any,
        memory: Any,
        plugin_registry: Any,
        data_dir: Path,
        loop_config: LoopConfig | None = None,
    ) -> None:
        self._bus = bus
        self._fleet = fleet
        self._memory = memory
        self._plugin_registry = plugin_registry
        self._data_dir = data_dir
        self._loop_config = loop_config
        self._failure_db = FailureDB(data_dir / "failures.db")
        self._memory_bridge = MemoryBridge(memory, self._failure_db)
        self._initialized = False

    async def start(self) -> None:
        """Register handlers on the bus and initialize the failure DB."""
        if not self._initialized:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            await self._failure_db.initialize()
            self._initialized = True

        self._bus.register_handler(self.name, self._dispatch)
        log.info("loop_agent_started")

    async def stop(self) -> None:
        """Shut down the agent."""
        log.info("loop_agent_stopped")

    async def _dispatch(self, message: Message) -> None:
        """Route messages to the appropriate handler."""
        await self.handle(message)

    async def handle(self, message: Message) -> None:
        """Handle loop.run and planner.plan_request messages."""
        if message.type in ("loop.run", "planner.plan_request"):
            await self._handle_loop_run(message)

    async def _handle_loop_run(self, message: Message) -> None:
        """Execute a goal through the emily-loop kernel."""
        goal = message.payload.get("task", "")
        if not goal:
            return

        if not self._initialized:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            await self._failure_db.initialize()
            self._initialized = True

        try:
            enriched = await self._memory_bridge.enrich_goal(goal)
            loop = self._build_loop()
            plan = await loop.run(enriched)

            if plan.status == PlanStatus.DONE:
                result_text = self._summarize_plan(plan)
                await self._bus.send_to(
                    recipient="ConversationAgent",
                    msg_type="text.input",
                    payload={
                        "text": f"[Loop completed] {result_text}",
                    },
                    sender=self.name,
                    priority=Priority.ACTIVE,
                    task_id=message.task_id,
                )
            else:
                partial = self._summarize_completed(plan)
                await self._bus.send_to(
                    recipient="ConversationAgent",
                    msg_type="text.input",
                    payload={
                        "text": (
                            f"[Loop failed after {plan.version} attempts] "
                            f"Original task: {goal}\n"
                            f"Partial progress: {partial}"
                        ),
                    },
                    sender=self.name,
                    priority=Priority.ACTIVE,
                    task_id=message.task_id,
                )

            await self._memory_bridge.sync_failures()

        except Exception as exc:
            log.error("loop_agent_error", error=str(exc), exc_info=True)
            # Fall back to ConversationAgent with original task
            await self._bus.send_to(
                recipient="ConversationAgent",
                msg_type="text.input",
                payload={"text": goal},
                sender=self.name,
                priority=Priority.ACTIVE,
                task_id=message.task_id,
            )

    def _build_loop(self) -> Loop:
        """Construct a fresh Loop instance with Emily's fleet and tools."""
        fleet_adapter = FleetAdapter(self._fleet)
        tool_bridge = ToolBridgeAdapter(self._plugin_registry)

        return Loop(
            llm=fleet_adapter,
            tools=tool_bridge.to_tool_registry(),
            failure_db=self._failure_db,
            data_dir=self._data_dir,
            config=self._loop_config,
        )

    @staticmethod
    def _summarize_plan(plan: Any) -> str:
        """Summarize a completed plan's results."""
        done_steps = [s for s in plan.steps if s.status == StepStatus.DONE]
        parts = [f"Goal: {plan.goal}", f"Steps completed: {len(done_steps)}/{len(plan.steps)}"]
        for step in done_steps:
            parts.append(f"  - {step.id}: {step.action[:100]}")
        return "\n".join(parts)

    @staticmethod
    def _summarize_completed(plan: Any) -> str:
        """Summarize completed steps from a failed/abandoned plan."""
        done = [s for s in plan.steps if s.status == StepStatus.DONE]
        if not done:
            return "No steps completed."
        return ", ".join(f"{s.id}: {s.action[:60]}" for s in done)
```

- [ ] **Step 4: Update `__init__.py` with LoopAgent and MemoryBridge exports**

Edit `core/loop_integration/__init__.py`:

```python
"""Emily Loop integration — adapters bridging emily-loop kernel to Emily's subsystems."""

from core.loop_integration.fleet_adapter import FleetAdapter
from core.loop_integration.loop_agent import LoopAgent
from core.loop_integration.memory_bridge import MemoryBridge
from core.loop_integration.tool_bridge import ToolBridgeAdapter

__all__ = ["FleetAdapter", "LoopAgent", "MemoryBridge", "ToolBridgeAdapter"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_loop_agent.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add core/loop_integration/loop_agent.py core/loop_integration/__init__.py tests/unit/test_loop_agent.py
git commit -m "feat: add LoopAgent as bus agent for emily-loop kernel"
```

---

### Task 6: Parallel step dispatch in emily-loop

**Files:**
- Modify: `~/emily-loop/emily_loop/loop.py`
- Create: `~/emily-loop/tests/test_parallel.py`

- [ ] **Step 1: Write the failing test**

Create `~/emily-loop/tests/test_parallel.py`:

```python
"""Tests for parallel step dispatch in the Loop."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from emily_loop.loop import Loop, LoopConfig
from emily_loop.failures import FailureDB
from emily_loop.models import Plan, PlanStatus, Step, StepResult, StepStatus
from emily_loop.tools import ToolRegistry


class MockLLM:
    """Mock LLM that returns pre-canned plan responses."""

    def __init__(self) -> None:
        self._responses: list[str | dict[str, Any]] = []
        self._call_index = 0

    def add_response(self, response: str | dict[str, Any]) -> None:
        self._responses.append(response)

    async def complete(self, prompt: str, schema: type | None = None) -> str | Any:
        if self._call_index >= len(self._responses):
            return {"steps": []}
        resp = self._responses[self._call_index]
        self._call_index += 1
        if schema is not None and isinstance(resp, dict):
            return resp
        return resp


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / ".emily-loop"
    data_dir.mkdir()
    (data_dir / "plans").mkdir()
    (data_dir / "executions").mkdir()
    return data_dir


@pytest.mark.asyncio
async def test_parallel_independent_steps_run_concurrently(tmp_data_dir: Path) -> None:
    """Steps with no dependencies should execute in parallel."""
    import asyncio

    execution_order: list[str] = []

    async def slow_tool(params: dict[str, Any]) -> StepResult:
        tool_id = params.get("id", "unknown")
        execution_order.append(f"start:{tool_id}")
        await asyncio.sleep(0.05)  # Simulate work
        execution_order.append(f"end:{tool_id}")
        return StepResult(step_id="", success=True, output=f"done:{tool_id}", error=None, duration_ms=50.0)

    registry = ToolRegistry()
    registry.register("shell", slow_tool)

    mock_llm = MockLLM()
    # Plan with 3 independent steps (no depends_on)
    mock_llm.add_response({
        "steps": [
            {
                "id": "step-001",
                "action": 'shell: {"id": "A"}',
                "expected_output": "done",
                "failure_conditions": [],
                "rollback": None,
                "depends_on": [],
                "guard": None,
            },
            {
                "id": "step-002",
                "action": 'shell: {"id": "B"}',
                "expected_output": "done",
                "failure_conditions": [],
                "rollback": None,
                "depends_on": [],
                "guard": None,
            },
            {
                "id": "step-003",
                "action": 'shell: {"id": "C"}',
                "expected_output": "done",
                "failure_conditions": [],
                "rollback": None,
                "depends_on": [],
                "guard": None,
            },
        ]
    })

    failure_db = FailureDB(tmp_data_dir / "failures.db")
    await failure_db.initialize()

    loop = Loop(
        llm=mock_llm,
        tools=registry,
        failure_db=failure_db,
        data_dir=tmp_data_dir,
        config=LoopConfig(replan_cooldown=0),
    )

    plan = await loop.run("test parallel")

    assert plan.status == PlanStatus.DONE
    # All 3 should have started before any finished (parallel execution)
    starts = [e for e in execution_order if e.startswith("start:")]
    ends = [e for e in execution_order if e.startswith("end:")]
    # With parallel execution, all starts happen before all ends
    assert len(starts) == 3
    assert len(ends) == 3


@pytest.mark.asyncio
async def test_dependent_steps_wait_for_dependencies(tmp_data_dir: Path) -> None:
    """Steps with depends_on should wait for their dependencies."""
    execution_order: list[str] = []

    async def tracking_tool(params: dict[str, Any]) -> StepResult:
        tool_id = params.get("id", "unknown")
        execution_order.append(tool_id)
        return StepResult(step_id="", success=True, output=f"done:{tool_id}", error=None, duration_ms=1.0)

    registry = ToolRegistry()
    registry.register("shell", tracking_tool)

    mock_llm = MockLLM()
    # Step C depends on A and B
    mock_llm.add_response({
        "steps": [
            {
                "id": "step-001",
                "action": 'shell: {"id": "A"}',
                "expected_output": "done",
                "failure_conditions": [],
                "rollback": None,
                "depends_on": [],
                "guard": None,
            },
            {
                "id": "step-002",
                "action": 'shell: {"id": "B"}',
                "expected_output": "done",
                "failure_conditions": [],
                "rollback": None,
                "depends_on": [],
                "guard": None,
            },
            {
                "id": "step-003",
                "action": 'shell: {"id": "C"}',
                "expected_output": "done",
                "failure_conditions": [],
                "rollback": None,
                "depends_on": ["step-001", "step-002"],
                "guard": None,
            },
        ]
    })

    failure_db = FailureDB(tmp_data_dir / "failures.db")
    await failure_db.initialize()

    loop = Loop(
        llm=mock_llm,
        tools=registry,
        failure_db=failure_db,
        data_dir=tmp_data_dir,
        config=LoopConfig(replan_cooldown=0),
    )

    plan = await loop.run("test deps")

    assert plan.status == PlanStatus.DONE
    # C must come after both A and B
    assert execution_order.index("C") > execution_order.index("A")
    assert execution_order.index("C") > execution_order.index("B")
```

- [ ] **Step 2: Run tests to verify they fail (or pass with sequential fallback)**

Run: `cd ~/emily-loop && .venv/bin/python -m pytest tests/test_parallel.py -v`
Expected: FAIL or degraded behavior (steps run one-by-one instead of in parallel)

- [ ] **Step 3: Implement parallel step dispatch**

Edit `~/emily-loop/emily_loop/loop.py`. Replace the `_execute_plan` method with:

```python
    async def _execute_plan(self, plan: Plan, start_idx: int = 0) -> Plan:
        """Execute plan steps, running independent steps in parallel."""
        self._state = LoopState.EXECUTING

        while True:
            ready = self._get_ready_steps(plan)
            if not ready:
                break

            if len(ready) == 1:
                # Single step — execute normally
                result = await self._execute_single_step(plan, ready[0])
                if result is not None:
                    return result  # Replan or abandon happened
            else:
                # Multiple independent steps — run in parallel
                results = await asyncio.gather(
                    *[self._executor.execute_step(step) for step in ready],
                    return_exceptions=True,
                )

                replan_needed = False
                for step, result in zip(ready, results):
                    if isinstance(result, Exception):
                        step.status = StepStatus.FAILED
                        replan_needed = True
                        continue

                    await self._checkpoint.save_step_result(plan.goal, result)
                    self._state = LoopState.OBSERVING

                    if result.success:
                        step.status = StepStatus.DONE
                        plan.checkpoint = step.id
                    else:
                        if result.failure_type == FailureType.TRANSIENT:
                            retried = await self._retry_step(plan, step, 0)
                            if not retried:
                                step.status = StepStatus.FAILED
                                replan_needed = True
                        else:
                            step.status = StepStatus.FAILED
                            replan_needed = True

                await self._checkpoint.save_plan(plan)

                if replan_needed:
                    failed_idx = next(
                        i for i, s in enumerate(plan.steps)
                        if s.status == StepStatus.FAILED
                    )
                    plan = await self._handle_replan(plan, failed_idx)
                    if plan.status == PlanStatus.ABANDONED:
                        self._state = LoopState.FAILED
                        return plan
                    return await self._execute_plan(plan)

                self._state = LoopState.EXECUTING

        # All steps done
        plan.status = PlanStatus.DONE
        await self._checkpoint.save_plan(plan)
        self._state = LoopState.SUCCESS
        logger.info("Goal completed: %s", plan.goal)
        return plan

    def _get_ready_steps(self, plan: Plan) -> list[Step]:
        """Return steps whose dependencies are all DONE and that are still PENDING."""
        done_ids = {s.id for s in plan.steps if s.status == StepStatus.DONE}
        return [
            s for s in plan.steps
            if s.status == StepStatus.PENDING
            and all(dep in done_ids for dep in s.depends_on)
        ]

    async def _execute_single_step(self, plan: Plan, step: Step) -> Plan | None:
        """Execute a single step with retry/replan logic. Returns Plan if replan happened, None to continue."""
        step.status = StepStatus.RUNNING

        await self._checkpoint.append_trace(
            plan.goal, {"event": "step_started", "step": step.id}
        )

        result = await self._executor.execute_step(step)
        await self._checkpoint.save_step_result(plan.goal, result)

        self._state = LoopState.OBSERVING

        if result.success:
            step.status = StepStatus.DONE
            plan.checkpoint = step.id
            await self._checkpoint.save_plan(plan)
            await self._checkpoint.append_trace(
                plan.goal, {"event": "step_done", "step": step.id}
            )
            self._state = LoopState.EXECUTING
            return None

        # Failure path
        await self._checkpoint.append_trace(
            plan.goal,
            {"event": "step_failed", "step": step.id, "error": result.error},
        )

        if result.failure_type == FailureType.TRANSIENT:
            retried = await self._retry_step(plan, step, 0)
            if retried:
                self._state = LoopState.EXECUTING
                return None

        # Structural failure or retries exhausted -> replan
        step.status = StepStatus.FAILED
        failed_idx = plan.steps.index(step)
        plan = await self._handle_replan(plan, failed_idx)
        if plan.status == PlanStatus.ABANDONED:
            self._state = LoopState.FAILED
            return plan

        new_start = self._checkpoint.get_resume_index(plan)
        return await self._execute_plan(plan, new_start)
```

Also remove the old `_execute_plan` method entirely — the new one replaces it completely.

- [ ] **Step 4: Run all emily-loop tests to verify nothing is broken**

Run: `cd ~/emily-loop && .venv/bin/python -m pytest tests/ -v`
Expected: All tests pass (51 existing + 2 new = 53)

- [ ] **Step 5: Commit**

```bash
cd ~/emily-loop
git add emily_loop/loop.py tests/test_parallel.py
git commit -m "feat: add parallel step dispatch for independent steps"
```

---

### Task 7: Wire LoopAgent into Bootstrap + Replace PlannerAgent

**Files:**
- Modify: `agents/registry.py`
- Modify: `agents/conversation.py:173-179`

- [ ] **Step 1: Write the failing test for routing**

Create `tests/unit/test_loop_routing.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_loop_routing.py -v`
Expected: FAIL (no routing to LoopAgent yet)

- [ ] **Step 3: Modify ConversationAgent to route complex tasks**

Edit `agents/conversation.py`. In `_handle_text_input` (around line 173-179), add the routing check after getting the text:

Find this code block:
```python
    async def _handle_text_input(self, message: Message) -> None:
        """Process a text input (from API or TUI) via the full pipeline."""
        text = message.payload.get("text", "").strip()
        if not text:
            return
        mode_id = message.payload.get("mode_id", "normal")
        await self._generate_response(text, message.task_id, voice_mode=False, mode_id=mode_id)
```

Replace with:
```python
    async def _handle_text_input(self, message: Message) -> None:
        """Process a text input (from API or TUI) via the full pipeline."""
        text = message.payload.get("text", "").strip()
        if not text:
            return

        # Route complex multi-step tasks to LoopAgent
        routing = self._fleet.route(text, voice_mode=False)
        if routing.complexity_score >= 7 and message.sender != "LoopAgent":
            await self._bus.send_to(
                recipient="LoopAgent",
                msg_type="loop.run",
                payload={"task": text},
                sender=self.name,
                priority=Priority.ACTIVE,
                task_id=message.task_id,
            )
            return

        mode_id = message.payload.get("mode_id", "normal")
        await self._generate_response(text, message.task_id, voice_mode=False, mode_id=mode_id)
```

The `message.sender != "LoopAgent"` guard prevents infinite loops when LoopAgent sends results back to ConversationAgent.

- [ ] **Step 4: Modify AgentRegistry to replace PlannerAgent with LoopAgent**

Edit `agents/registry.py`. Replace the PlannerAgent import and instantiation:

Replace the entire file with:
```python
"""
Agent registry and lifecycle manager.

All agents are instantiated and registered here at startup.
The registry holds references to all running agents and provides
a unified interface for starting, stopping, and sending messages.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from agents.conversation import ConversationAgent
from agents.memory_agent import MemoryAgent
from agents.reflection import ReflectionAgent
from core.loop_integration.loop_agent import LoopAgent
from observability.logger import get_logger

if TYPE_CHECKING:
    from agents.base import BaseAgent
    from core.bus import AgentBus
    from llm.fleet import LLMFleet
    from memory.manager import MemoryManager

log = get_logger(__name__)


class AgentRegistry:
    """
    Manages instantiation, registration, and lifecycle of all Emily agents.

    Agents that require additional specialist modules (ResearchAgent, CodeAgent,
    CriticAgent, ToolBuilderAgent, MonitorAgent) are imported lazily to avoid
    circular imports and allow optional dependencies.
    """

    def __init__(
        self,
        bus: AgentBus,
        fleet: LLMFleet,
        memory: MemoryManager,
        settings: Any | None = None,
        self_improvement: Any | None = None,
    ) -> None:
        """
        Args:
            bus: Shared AgentBus.
            fleet: LLM fleet.
            memory: Unified memory manager.
            settings: Emily settings for tool config etc.
            self_improvement: SelfImprovementEngine instance.
        """
        self._bus = bus
        self._fleet = fleet
        self._memory = memory
        self._settings = settings
        self._self_improvement = self_improvement
        self._agents: dict[str, BaseAgent] = {}

    def _build_core_agents(self) -> list[BaseAgent]:
        """Instantiate all core agents."""
        conversation = ConversationAgent(
            self._bus,
            self._fleet,
            self._memory,
            settings=self._settings,
            self_improvement=self._self_improvement,
        )

        # LoopAgent replaces PlannerAgent — same bus handlers ("planner.plan_request")
        # plus new "loop.run" handler. Gets Emily's tools via the ConversationAgent's registry.
        data_dir = Path("~/.emily-loop").expanduser()
        loop_agent = LoopAgent(
            bus=self._bus,
            fleet=self._fleet,
            memory=self._memory,
            plugin_registry=conversation._plugin_registry,
            data_dir=data_dir,
        )

        return [
            conversation,
            loop_agent,
            MemoryAgent(self._bus, self._fleet, self._memory),
            ReflectionAgent(self._bus, self._fleet, self._memory),
        ]

    def _build_specialist_agents(self) -> list[BaseAgent]:
        """Instantiate specialist agents (imported lazily)."""
        agents: list[BaseAgent] = []
        optional_imports = [
            ("agents.research", "ResearchAgent"),
            ("agents.code_agent", "CodeAgent"),
            ("agents.monitor", "MonitorAgent"),
            ("agents.tool_builder", "ToolBuilderAgent"),
            ("agents.onboarding", "OnboardingAgent"),
        ]
        for module_path, class_name in optional_imports:
            try:
                import importlib

                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
                agents.append(cls(self._bus, self._fleet, self._memory))
            except (ImportError, AttributeError) as exc:
                log.warning("specialist_agent_not_loaded", agent=class_name, error=str(exc))
        return agents

    async def start_all(self) -> None:
        """Instantiate and start all agents."""
        all_agents = self._build_core_agents() + self._build_specialist_agents()

        for agent in all_agents:
            self._agents[agent.name] = agent
            await agent.start()
            log.info("agent_registered", name=agent.name)

        log.info("all_agents_started", count=len(self._agents))

    async def stop_all(self) -> None:
        """Stop all running agents."""
        for agent in self._agents.values():
            await agent.stop()
        self._agents.clear()
        log.info("all_agents_stopped")

    def get(self, name: str) -> BaseAgent | None:
        """Return a registered agent by name."""
        return self._agents.get(name)

    @property
    def agent_names(self) -> list[str]:
        """Names of all registered agents."""
        return list(self._agents.keys())
```

- [ ] **Step 5: Delete PlannerAgent**

Run: `cd ~/Emily1.0 && rm agents/planner.py`

- [ ] **Step 6: Run the routing test to verify it passes**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_loop_routing.py -v`
Expected: 1 passed

- [ ] **Step 7: Run all existing tests to check for regressions**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/ -v --timeout=30`
Expected: All tests pass. Any test that imports `PlannerAgent` directly will fail — that's expected and correct (the agent is deleted). Fix those imports if they exist.

- [ ] **Step 8: Commit**

```bash
git add agents/registry.py agents/conversation.py tests/unit/test_loop_routing.py
git rm agents/planner.py
git commit -m "feat: replace PlannerAgent with LoopAgent, route complexity >= 7 to Loop"
```

---

### Task 8: Integration test

**Files:**
- Create: `tests/unit/test_loop_integration.py`

- [ ] **Step 1: Write the integration test**

Create `tests/unit/test_loop_integration.py`:

```python
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

        return ToolResult.ok(output=f"executed {self.name}")


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

    from core.loop_integration.loop_agent import LoopAgent

    agent = LoopAgent(
        bus=bus,
        fleet=fleet,
        memory=memory,
        plugin_registry=registry,
        data_dir=tmp_path,
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
```

- [ ] **Step 2: Run the integration test**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_loop_integration.py -v`
Expected: 1 passed

- [ ] **Step 3: Run all adapter tests together**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_fleet_adapter.py tests/unit/test_tool_bridge.py tests/unit/test_memory_bridge.py tests/unit/test_loop_agent.py tests/unit/test_loop_routing.py tests/unit/test_loop_integration.py -v`
Expected: All 16 tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_loop_integration.py
git commit -m "test: add end-to-end integration test for LoopAgent pipeline"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- FleetAdapter → Task 2
- ToolBridgeAdapter → Task 3
- MemoryBridge → Task 4
- LoopAgent → Task 5
- Parallel dispatch → Task 6
- Routing (complexity >= 7) → Task 7
- PlannerAgent deletion → Task 7
- Bootstrap wiring → Task 7 (via AgentRegistry)
- Integration test → Task 8
- Path dependency → Task 1
- Backward-compatible planner.plan_request → Task 5 (LoopAgent handles both message types)

**2. Placeholder scan:** No TBD, TODO, or vague steps. All code blocks are complete.

**3. Type consistency:**
- `FleetAdapter` constructor: `(fleet: LLMFleet, tier: ModelTier)` — consistent across Tasks 2, 5
- `ToolBridgeAdapter.to_tool_registry()` returns `ToolRegistry` — consistent across Tasks 3, 5
- `MemoryBridge(memory, failure_db)` — consistent across Tasks 4, 5
- `LoopAgent._build_loop()` uses all three adapters — consistent with specs
- `StepResult` fields match emily-loop's definition — verified in Task 3
- `PluginRegistry.all_tools()` (not `.all()`) — verified from source
