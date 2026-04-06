# Emily Loop Integration — Design Spec

**Date:** 2026-04-06
**Status:** Approved
**Location:** Adapters in `~/Emily1.0/core/loop_integration/`, kernel at `~/emily-loop/` (path dependency)
**Approach:** Adapter Layer — thin wrappers bridge emily-loop's protocols to Emily's subsystems

## Problem

Emily's execution engine has two critical gaps:

1. **No persistence.** Process dies → all progress lost. No checkpoint, no resume.
2. **No failure learning.** Errors feed back as text and the LLM guesses. No classification, no pattern storage, no prevention injection.

The emily-loop kernel (standalone prototype at `~/emily-loop/`) solves both: checkpoint/resume across restarts, SQLite+FTS5 failure memory queried before every step, TRANSIENT/STRUCTURAL failure classification, and replanning from current state.

Emily's existing PlannerAgent has additional bugs: no step timeout, stuck sub-tasks hang forever, no retry/replan, no failure memory.

This spec grafts the kernel onto Emily as a path dependency with adapter classes, replacing PlannerAgent entirely.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where Loop lives | Path dependency (`../emily-loop`) | Loop stays testable in isolation, clean separation |
| Routing | Complexity >= 7 auto-routes + explicit `"loop.run"` | Best coverage with minimal false positives |
| PlannerAgent | Replaced entirely | Loop subsumes all Planner capabilities + adds checkpoint/failures/replan. Planner's parallel dispatch stolen (added to Loop) |
| Failure memory | Bidirectional bridge | Loop keeps fast SQLite for operations, syncs to Emily's procedural memory for long-term learning |

## Architecture

```
User/Agent sends task
        |
        v
   +----------+   complexity < 7    +--------------------+
   | AgentBus | ------------------> | ConversationAgent  | (normal ReAct path)
   +----+-----+                     +--------------------+
        | complexity >= 7
        | OR "loop.run" message
        v
   +-----------+
   | LoopAgent |
   +-----+-----+
         |
         v
   +-------------------------------------------+
   |  emily-loop kernel (path dependency)      |
   |                                           |
   |  FleetAdapter  <-- LLMFleet               |
   |  ToolBridge    <-- PluginRegistry         |
   |  FailureDB     (own SQLite)               |
   |  Checkpoint    (own JSON files)           |
   |                                           |
   |  Loop.run(goal) -> Plan                   |
   |    +- Planner.generate()                  |
   |    +- Executor.execute_step() --parallel  |
   |    +- Retry (TRANSIENT) / Replan (STRUCTURAL)
   |    +- Checkpoint after every step         |
   +------------------+------------------------+
                      | on goal complete
                      v
   +---------------+     +-------------------+
   | MemoryBridge  |---->| Procedural Memory | (failure patterns synced)
   +---------------+     +-------------------+
```

## Components

### 1. FleetAdapter (`core/loop_integration/fleet_adapter.py`, ~40 LOC)

Wraps Emily's `LLMFleet` to satisfy emily-loop's `LLMClient` protocol.

```python
class FleetAdapter:
    def __init__(self, fleet: LLMFleet, tier: ModelTier = ModelTier.SMART) -> None:
        self._fleet = fleet
        self._tier = tier

    async def complete(self, prompt: str, schema: type | None = None) -> str | Any:
        messages = [ChatMessage(role="user", content=prompt)]
        if schema is not None:
            prompt += "\n\nRespond with valid JSON only."
        result = await self._fleet.chat(
            user_message=prompt,
            messages=messages,
            force_tier=self._tier,
        )
        if schema is not None:
            return json.loads(result.content)
        return result.content
```

Loop inherits Emily's circuit breakers, 4-backend fallback chain, and 11 model tiers for free. Planning uses SMART tier. Failure analysis uses FAST tier.

### 2. ToolBridgeAdapter (`core/loop_integration/tool_bridge.py`, ~60 LOC)

Wraps Emily's `PluginRegistry` into Loop's `ToolRegistry`.

```python
class ToolBridgeAdapter:
    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    def to_tool_registry(self) -> ToolRegistry:
        loop_registry = ToolRegistry()
        for tool in self._registry.all():
            loop_registry.register(tool.name, self._wrap(tool))
        return loop_registry

    def _wrap(self, tool: BaseTool) -> ToolFn:
        async def fn(params: dict[str, Any]) -> StepResult:
            ctx = ExecutionContext(session_id="loop", sandbox_enabled=True)
            result = await tool.safe_execute(params, ctx)
            return StepResult(
                step_id="",
                success=result.success,
                output=str(result.output),
                error=result.error,
                duration_ms=result.execution_time_ms,
            )
        return fn
```

All 23 of Emily's tools become available to Loop. Approval-gated tools keep their approval checks via `safe_execute()`.

### 3. LoopAgent (`core/loop_integration/loop_agent.py`, ~120 LOC)

New agent on `AgentBus`. Replaces PlannerAgent.

**Registered message handlers:**
- `"loop.run"` — explicit trigger from any agent or API
- `"planner.plan_request"` — backward-compatible, drop-in for PlannerAgent callers

**Flow:**
1. Receive task
2. Pull episodic context via `MemoryBridge.enrich_goal()`
3. Construct `Loop` with `FleetAdapter` + `ToolBridgeAdapter` + `FailureDB`
4. Call `loop.run(enriched_goal)`
5. On SUCCESS: summarize results, send to ConversationAgent via bus
6. On ABANDONED: fall back to ConversationAgent with partial progress context
7. On exception: fall back to ConversationAgent with original task (degrades to ReAct)
8. Sync failure patterns via `MemoryBridge.sync_failures()`

**Graceful degradation:** Loop failure is never silent. ABANDONED plans include partial progress. Total exceptions fall back to normal ReAct as last resort.

### 4. MemoryBridge (`core/loop_integration/memory_bridge.py`, ~80 LOC)

Bidirectional bridge between Loop's failure DB and Emily's 5-tier memory.

**Before planning — enrich goal:**
```python
async def enrich_goal(self, goal: str) -> str:
    chunks = await self._memory.retrieve_context(goal, top_k=3)
    if not chunks:
        return goal
    context = "\n".join(c["content"] for c in chunks)
    return f"{goal}\n\nRelevant context from past sessions:\n{context}"
```

**After goal completion — sync failures:**
```python
async def sync_failures(self) -> int:
    all_patterns = await self._failure_db.all()
    new_patterns = all_patterns[: len(all_patterns) - self._last_sync_count]
    for pattern in new_patterns:
        await self._memory.procedural.add_skill(
            name=f"failure:{pattern.id}",
            description=f"[{pattern.category.value}] {pattern.trigger} -> {pattern.prevention}",
            tool_sequence=[{
                "trigger": pattern.trigger,
                "root_cause": pattern.root_cause,
                "prevention": pattern.prevention,
                "severity": pattern.severity,
                "occurrences": pattern.occurrences,
            }],
        )
    self._last_sync_count = len(all_patterns)
    return len(new_patterns)
```

Emily's ReflectionAgent and self-improvement engine see failure patterns during idle cycles. Loop plans with episodic context from past conversations.

### 5. Parallel Step Dispatch (emily-loop modification, ~30 LOC)

Modify `Loop._execute_plan()` to gather independent steps:

```python
def _get_ready_steps(self, plan: Plan) -> list[Step]:
    done_ids = {s.id for s in plan.steps if s.status == StepStatus.DONE}
    return [
        s for s in plan.steps
        if s.status == StepStatus.PENDING
        and all(dep in done_ids for dep in s.depends_on)
    ]
```

When multiple steps are ready (all dependencies DONE), execute them with `asyncio.gather()`. Single ready step executes normally. Checkpoint after each batch.

This subsumes PlannerAgent's DAG dispatch with added checkpoint/resume and failure handling.

## File Changes

### New files (Emily1.0)

| File | LOC | Purpose |
|------|-----|---------|
| `core/loop_integration/__init__.py` | 5 | Package exports |
| `core/loop_integration/fleet_adapter.py` | 40 | LLMFleet -> LLMClient adapter |
| `core/loop_integration/tool_bridge.py` | 60 | PluginRegistry -> ToolRegistry adapter |
| `core/loop_integration/loop_agent.py` | 120 | Bus agent, routing, graceful degradation |
| `core/loop_integration/memory_bridge.py` | 80 | Bidirectional failure/episodic sync |
| **Total new** | **~305** | |

### Modified files

| File | Change | LOC delta |
|------|--------|-----------|
| `Emily1.0/pyproject.toml` | Add `emily-loop` path dependency | +1 |
| `Emily1.0/core/bootstrap.py` | Wire LoopAgent, remove PlannerAgent | ~10 |
| `Emily1.0/agents/conversation.py` | Route complexity >= 7 to LoopAgent | ~10 |
| `emily-loop/emily_loop/loop.py` | Parallel step dispatch | ~30 |
| **Total modified** | | **~51** |

### Deleted files

| File | Reason |
|------|--------|
| `Emily1.0/agents/planner.py` | Replaced by LoopAgent + emily-loop kernel |

## What Doesn't Change

- ConversationAgent's ReAct loop (complexity < 7) — untouched
- CriticLoop — still scores all responses
- Fleet circuit breakers and fallback chain — Loop inherits via adapter
- 5-tier memory — works as before, plus receives failure patterns
- Self-improvement engine — works as before, sees new pattern data
- All 23 tools — available to both Loop and ReAct paths
- Voice pipeline — untouched (voice is always low complexity)
- ReasoningOrchestrator — untouched (handles reasoning strategy selection)
- All 8 remaining agents — untouched

## Routing Logic

```
Task arrives at ConversationAgent
    |
    +-- complexity < 7 --> Normal ReAct path (unchanged)
    |
    +-- complexity >= 7 --> send "loop.run" to LoopAgent
    |
    +-- explicit "loop.run" message --> LoopAgent handles directly
```

Voice mode always takes the fast path (complexity threshold not reached). API/text input goes through routing.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Loop completes successfully | Results sent to ConversationAgent for synthesis |
| Loop ABANDONED (max replans) | Partial progress + failure context sent to ConversationAgent |
| Loop throws exception | Original task sent to ConversationAgent (falls back to ReAct) |
| Fleet all-backends-failed | Loop's FleetAdapter raises, caught by LoopAgent, falls back to ReAct |
| Individual step timeout | Step marked FAILED, classified TRANSIENT, retried up to 2x |
| Structural failure | Replan from current state, max 3 replans, 30s cooldown |

## Testing Strategy

- **Adapter unit tests:** FleetAdapter with MockFleet, ToolBridge with mock tools
- **LoopAgent unit tests:** Mock Loop, verify bus message routing and fallback paths
- **MemoryBridge unit tests:** Mock MemoryManager, verify sync logic
- **Integration test:** Real LoopAgent + FleetAdapter + ToolBridge + in-memory SQLite, execute a 3-step goal
- **emily-loop's existing 51 tests remain unchanged** (standalone MockLLM path)

## Constraints

- Zero new pip dependencies (emily-loop already uses httpx + pyyaml + sqlite3)
- ~305 LOC new code in Emily, ~51 LOC modified — well under budget
- Single process — Loop runs in LoopAgent's asyncio task, no subprocess
- Config-driven — Loop uses Emily's settings for data_dir and limits
- Backward-compatible — `"planner.plan_request"` messages still work

## Non-Goals

- Replacing ReAct for simple queries (< complexity 7)
- Adding new tools to Loop (it gets Emily's existing 23)
- Modifying the voice pipeline
- Real-time UI for Loop execution (trace files + bus events are the interface)
- Multi-Loop concurrency (one goal at a time, queue if needed)

## Success Criteria

1. A complexity >= 7 task auto-routes to Loop, executes multi-step plan with checkpoint, and returns result through ConversationAgent
2. Process kill during Loop execution → restart → resumes from last checkpoint
3. A failure pattern from one goal prevents the same failure in a subsequent goal (via FTS5 query + prompt injection)
4. Structural failure triggers replan that succeeds via different approach
5. Failure patterns appear in Emily's procedural memory after goal completion
6. All existing Emily tests pass (no regression)
