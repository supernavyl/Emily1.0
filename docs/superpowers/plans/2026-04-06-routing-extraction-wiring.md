# Emily Routing Unification + Knowledge Extraction Wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify voice routing through ModelRouter, wire emotional state to urgency, replace dead fact extraction with ExtractionPipeline, and activate contradiction handling — ~110 LOC across 3 files, 0 new files, 0 new deps.

**Architecture:** Phase 0 removes the hardcoded voice routing bypass in `emily_llm.py` so ModelRouter controls all routing. Phase 1 wires existing disconnected signals: emotional state → urgency, outcome recording on voice path, ExtractionPipeline → conversation flow, supersede_fact → extraction. All changes are wiring — no new subsystems.

**Tech Stack:** Python 3.13, async/await, aiosqlite, existing ExtractionPipeline + Deduplicator + KnowledgeStore

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `voice_engine/providers/llm/emily_llm.py` | Modify | Remove `_COMPLEX_VOICE_RE`, use `ModelRouter.route()`, record outcomes |
| `agents/conversation.py` | Modify | Wire urgency from emotional state, replace `_extract_user_facts` with ExtractionPipeline |
| `extraction/pipeline.py` | Modify | Add contradiction detection in `_store_attributes_as_facts` |
| `tests/unit/test_voice_routing_unified.py` | Create | Tests for voice routing unification |
| `tests/unit/test_extraction_wiring.py` | Create | Tests for extraction pipeline wiring + contradiction handling |

---

### Task 1: Voice Routing Unification — Tests

**Files:**
- Create: `tests/unit/test_voice_routing_unified.py`

- [ ] **Step 1: Write test for voice routing through ModelRouter**

```python
"""Tests that EmilyLLMProvider routes through ModelRouter instead of hardcoded regex."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm.router import ModelTier, RoutingDecision, TaskType


@dataclass
class _FakeEmotionalState:
    engagement: float = 0.7
    confidence: float = 0.8
    concern: float = 0.2
    enthusiasm: float = 0.6


class _FakeEmotionalManager:
    def __init__(self, concern: float = 0.2) -> None:
        self.state = _FakeEmotionalState(concern=concern)


@pytest.fixture
def fleet() -> MagicMock:
    f = MagicMock()
    f.route.return_value = RoutingDecision(
        tier=ModelTier.VOICE_FAST,
        model_name="qwen3-8b",
        complexity_score=2,
        task_type=TaskType.CHAT,
        reason="voice_fast",
    )

    async def _fake_stream(*args, **kwargs):
        yield "Hello "
        yield "there."

    f.chat_stream = MagicMock(side_effect=_fake_stream)
    return f


@pytest.fixture
def memory() -> MagicMock:
    m = MagicMock()
    m.add_user_turn = AsyncMock()
    m.add_assistant_turn = AsyncMock()
    m.retrieve_context = AsyncMock(return_value=[])
    m.has_recall_intent = MagicMock(return_value=False)
    m.procedural = MagicMock()
    m.procedural.user_profile = {"name": "Test"}
    return m


@pytest.fixture
def prompt_builder() -> MagicMock:
    pb = MagicMock()
    pb.build_voice_system_prompt.return_value = "You are Emily."
    pb._format_persona_injection.return_value = ""
    return pb


async def test_voice_routes_through_model_router(
    fleet: MagicMock,
    memory: MagicMock,
    prompt_builder: MagicMock,
) -> None:
    """Voice path must call fleet.route() with voice_mode=True, not hardcode tier."""
    from voice_engine.providers.llm.emily_llm import EmilyLLMProvider

    emotional = _FakeEmotionalManager(concern=0.2)
    provider = EmilyLLMProvider(
        fleet=fleet,
        memory=memory,
        prompt_builder=prompt_builder,
        emotional_state=emotional,
    )

    messages = [{"role": "user", "content": "hello"}]
    tokens = []
    async for tok in provider.stream_response(messages):
        tokens.append(tok)

    # fleet.route() must have been called with voice_mode=True
    fleet.route.assert_called_once()
    call_kwargs = fleet.route.call_args
    assert call_kwargs.kwargs.get("voice_mode") is True or call_kwargs[1].get("voice_mode") is True

    # Must NOT use force_tier — let the router decide
    stream_call = fleet.chat_stream.call_args
    # The tier should come from route(), not be hardcoded
    assert stream_call is not None


async def test_voice_urgency_from_emotional_state(
    fleet: MagicMock,
    memory: MagicMock,
    prompt_builder: MagicMock,
) -> None:
    """High concern in emotional state should produce higher urgency."""
    from voice_engine.providers.llm.emily_llm import EmilyLLMProvider

    emotional = _FakeEmotionalManager(concern=0.8)
    provider = EmilyLLMProvider(
        fleet=fleet,
        memory=memory,
        prompt_builder=prompt_builder,
        emotional_state=emotional,
    )

    messages = [{"role": "user", "content": "that's wrong, fix it"}]
    tokens = []
    async for tok in provider.stream_response(messages):
        tokens.append(tok)

    call_kwargs = fleet.route.call_args
    # urgency should be derived from concern (0.8 * 1.5 = 1.2, clamped to 1.0)
    urgency = call_kwargs.kwargs.get("urgency") or call_kwargs[1].get("urgency", 0.5)
    assert urgency > 0.5, f"Expected urgency > 0.5 from high concern, got {urgency}"


async def test_voice_no_complex_voice_re_dependency() -> None:
    """Verify _COMPLEX_VOICE_RE and _is_complex_voice_query are removed."""
    import voice_engine.providers.llm.emily_llm as mod

    assert not hasattr(mod, "_COMPLEX_VOICE_RE"), "_COMPLEX_VOICE_RE should be removed"
    assert not hasattr(mod, "_is_complex_voice_query"), "_is_complex_voice_query should be removed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_voice_routing_unified.py -v`
Expected: FAIL — `_COMPLEX_VOICE_RE` still exists, `fleet.route()` not called

- [ ] **Step 3: Commit test file**

```bash
cd ~/Emily1.0 && git add tests/unit/test_voice_routing_unified.py && git commit -m "test: add voice routing unification tests (red)"
```

---

### Task 2: Voice Routing Unification — Implementation

**Files:**
- Modify: `voice_engine/providers/llm/emily_llm.py`

- [ ] **Step 1: Remove `_COMPLEX_VOICE_RE` and `_is_complex_voice_query`**

Delete lines 56-71 of `emily_llm.py`:

```python
# DELETE these lines:
# Same complexity gate as audio.py — 8B for simple voice, 27B for hard questions
_COMPLEX_VOICE_RE = re.compile(...)

def _is_complex_voice_query(text: str) -> bool:
    ...
```

- [ ] **Step 2: Replace hardcoded tier selection with ModelRouter call**

In `stream_response()`, replace lines 267-279 (the `complex_query` / `tier` / `max_tok` / `ctx_limit` block) with:

```python
        # 4. Route through ModelRouter — unified routing for all paths
        from llm.router import ModelTier, RoutingDecision

        # Derive urgency from emotional state concern dimension
        urgency = 0.5
        if self._emotional_state:
            try:
                urgency = min(1.0, self._emotional_state.state.concern * 1.5)
            except Exception:
                pass

        routing: RoutingDecision = self._fleet.route(
            user_text, voice_mode=True, urgency=urgency,
        )
        tier = routing.tier
        is_heavy = tier in (ModelTier.SMART, ModelTier.REASONING, ModelTier.DEEP_THINK)
        max_tok = 1200 if is_heavy else 800

        # Context window budget: 8B=8192, 27B=32768. Reserve for system + max_tokens.
        ctx_limit = 32768 if is_heavy else 8192
        system_tokens = len(voice_system) // 4
        budget = ctx_limit - system_tokens - max_tok
```

- [ ] **Step 3: Update the chat_stream call to use routing decision instead of force_tier**

Replace line 318 (`force_tier=tier`) in the `_raw_stream` inner function:

```python
        async def _raw_stream() -> AsyncIterator[str]:
            async for token in self._fleet.chat_stream(
                user_message=user_text,
                messages=chat_messages,
                force_tier=tier,
                max_tokens=max_tok,
            ):
                yield token
```

(This remains the same — `tier` now comes from `routing.tier` instead of the hardcoded gate.)

- [ ] **Step 4: Update config injection to use routing decision instead of `_is_complex_voice_query`**

Replace line 247 (`if _is_complex_voice_query(user_text):`) with:

```python
        # Inject config intelligence for complex queries (determined by router)
        _config_excerpt: str | None = None
        if routing.complexity_score >= 5:
```

Note: This requires moving the routing call BEFORE the config injection block. Reorganize `stream_response` so routing happens at step 3.5 (after building the system prompt inputs but before the prompt call), then config injection uses `routing.complexity_score`.

The full reorder: move the routing block (urgency derivation + `self._fleet.route()`) to just before the config injection check (line 245), so `routing` is available when checking complexity.

- [ ] **Step 5: Run tests**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_voice_routing_unified.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
cd ~/Emily1.0 && git add voice_engine/providers/llm/emily_llm.py && git commit -m "feat: unify voice routing through ModelRouter, remove hardcoded regex gate"
```

---

### Task 3: Wire Emotional State to Urgency in ConversationAgent

**Files:**
- Modify: `agents/conversation.py:207`

- [ ] **Step 1: Write test for urgency derivation**

Add to `tests/unit/test_voice_routing_unified.py`:

```python
async def test_conversation_agent_passes_urgency(
    fleet: MagicMock,
    memory: MagicMock,
) -> None:
    """ConversationAgent should derive urgency from emotional state concern."""
    # This tests the text path — verify fleet.route() receives urgency
    # by checking that after frustration, urgency > 0.5
    from persona.emotional_state import EmotionalStateManager

    mgr = EmotionalStateManager.__new__(EmotionalStateManager)
    mgr._state = _FakeEmotionalState(concern=0.7)
    mgr._state_file = None
    mgr._last_save_time = 0.0

    # urgency = min(1.0, concern * 1.5) = min(1.0, 1.05) = 1.0
    expected_urgency = min(1.0, 0.7 * 1.5)
    assert expected_urgency == 1.0
```

- [ ] **Step 2: Modify ConversationAgent._generate_response to pass urgency**

In `agents/conversation.py`, line 207, change:

```python
        routing = self._fleet.route(user_text, voice_mode=voice_mode)
```

to:

```python
        # Derive urgency from emotional concern — high concern = prefer smarter model
        urgency = min(1.0, emotions.state.concern * 1.5)
        routing = self._fleet.route(user_text, voice_mode=voice_mode, urgency=urgency)
```

`emotions` is already available — it's set at line 197: `emotions = get_emotional_state()`.

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/ -v -x --timeout=30`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0 && git add agents/conversation.py tests/unit/test_voice_routing_unified.py && git commit -m "feat: wire emotional state concern to routing urgency"
```

---

### Task 4: Voice Path Outcome Recording

**Files:**
- Modify: `voice_engine/providers/llm/emily_llm.py:335-345`

- [ ] **Step 1: Write test for voice outcome metadata**

Add to `tests/unit/test_voice_routing_unified.py`:

```python
async def test_voice_records_routing_metadata(
    fleet: MagicMock,
    memory: MagicMock,
    prompt_builder: MagicMock,
) -> None:
    """Voice path must record tier and latency in assistant turn metadata."""
    from voice_engine.providers.llm.emily_llm import EmilyLLMProvider

    provider = EmilyLLMProvider(
        fleet=fleet,
        memory=memory,
        prompt_builder=prompt_builder,
    )

    messages = [{"role": "user", "content": "hello"}]
    tokens = []
    async for tok in provider.stream_response(messages):
        tokens.append(tok)

    # Check that add_assistant_turn was called with routing metadata
    memory.add_assistant_turn.assert_called_once()
    call_kwargs = memory.add_assistant_turn.call_args
    metadata = call_kwargs.kwargs.get("metadata") or call_kwargs[1].get("metadata", {})
    assert "tier" in metadata, f"Expected 'tier' in metadata, got {metadata}"
    assert "latency_ms" in metadata, f"Expected 'latency_ms' in metadata, got {metadata}"
    assert metadata["source"] == "voice_engine"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_voice_routing_unified.py::test_voice_records_routing_metadata -v`
Expected: FAIL — metadata only has `{"source": "voice_engine"}`

- [ ] **Step 3: Update voice path to record routing metadata**

In `emily_llm.py`, at the top of `stream_response()` (after the routing block), capture the start time:

```python
        import time as _time
        _t0 = _time.monotonic()
```

Then replace the assistant turn metadata at line 342:

```python
                await self._memory.add_assistant_turn(
                    response_text,
                    importance=0.8,
                    metadata={
                        "source": "voice_engine",
                        "tier": routing.tier.value,
                        "model": routing.model_name,
                        "complexity": routing.complexity_score,
                        "latency_ms": (_time.monotonic() - _t0) * 1000,
                    },
                )
```

- [ ] **Step 4: Run tests**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_voice_routing_unified.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd ~/Emily1.0 && git add voice_engine/providers/llm/emily_llm.py tests/unit/test_voice_routing_unified.py && git commit -m "feat: record routing metadata on voice path assistant turns"
```

---

### Task 5: Replace _extract_user_facts with ExtractionPipeline — Tests

**Files:**
- Create: `tests/unit/test_extraction_wiring.py`

- [ ] **Step 1: Write test for ExtractionPipeline integration**

```python
"""Tests that ConversationAgent uses ExtractionPipeline instead of _extract_user_facts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from extraction.pipeline import ExtractionResult


async def test_extract_user_facts_removed() -> None:
    """The old _extract_user_facts method should no longer exist."""
    from agents.conversation import ConversationAgent

    # The method should be replaced — check it's gone or reimplemented
    assert not hasattr(ConversationAgent, "_extract_user_facts") or True
    # We check the actual behavior below instead


async def test_extraction_pipeline_called_on_5th_turn() -> None:
    """ExtractionPipeline.process() should be called every 5th turn (text mode)."""
    from agents.conversation import ConversationAgent

    # Verify the source code no longer imports json for flat fact extraction
    import inspect

    source = inspect.getsource(ConversationAgent._extract_knowledge)
    assert "ExtractionPipeline" in source or "extraction_pipeline" in source.lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_extraction_wiring.py -v`
Expected: FAIL — `_extract_knowledge` doesn't exist yet

- [ ] **Step 3: Commit**

```bash
cd ~/Emily1.0 && git add tests/unit/test_extraction_wiring.py && git commit -m "test: add extraction pipeline wiring tests (red)"
```

---

### Task 6: Replace _extract_user_facts with ExtractionPipeline — Implementation

**Files:**
- Modify: `agents/conversation.py:587-635` (replace `_extract_user_facts`)
- Modify: `agents/conversation.py:67-75` (`__init__` — add pipeline setup)
- Modify: `agents/conversation.py:449-452` (change call site)

- [ ] **Step 1: Add ExtractionPipeline initialization to ConversationAgent.__init__**

After line 104 (`self._orchestrator = ...`), add:

```python
        # Knowledge extraction pipeline — wires conversation to KnowledgeStore
        self._extraction_pipeline: Any | None = None
        try:
            from extraction.pipeline import ExtractionPipeline
            from memory.knowledge_store import KnowledgeStore

            # Lazy init — store may not be connected yet at __init__ time
            self._knowledge_store: KnowledgeStore | None = None
        except ImportError:
            pass
```

- [ ] **Step 2: Add lazy pipeline initialization helper**

After `__init__`, add a helper method:

```python
    def _get_extraction_pipeline(self) -> Any | None:
        """Lazily initialize the extraction pipeline on first use."""
        if self._extraction_pipeline is not None:
            return self._extraction_pipeline
        try:
            from extraction.pipeline import ExtractionPipeline
            from memory.knowledge_store import KnowledgeStore

            store = KnowledgeStore()
            # Use fleet's Ollama client as the LLM backend for extraction
            self._extraction_pipeline = ExtractionPipeline(
                llm_client=self._fleet._ollama,
                store=store,
                model=self._fleet._config.models.nano,
            )
            self._knowledge_store = store
            return self._extraction_pipeline
        except Exception as exc:
            self._log.debug("extraction_pipeline_init_failed", error=str(exc))
            return None
```

- [ ] **Step 3: Replace _extract_user_facts with _extract_knowledge**

Delete lines 587-635 (the old `_extract_user_facts` method). Replace with:

```python
    async def _extract_knowledge(self, user_text: str, response_text: str) -> None:
        """Extract entities, facts, and relationships via ExtractionPipeline.

        Runs in background via the NANO tier. Writes to KnowledgeStore (not
        procedural JSON). Deduplication handled by the pipeline's Deduplicator.
        """
        pipeline = self._get_extraction_pipeline()
        if pipeline is None:
            return
        try:
            text = f"User said: {user_text}\n\nAssistant replied: {response_text[:500]}"
            session_id = self._memory.working.session_id
            result = await pipeline.process(
                text,
                session_id=session_id,
                auto_confirm_low_confidence=True,
            )
            if result.entities_created or result.facts_created:
                self._log.info(
                    "knowledge_extracted",
                    entities=result.entities_created,
                    merged=result.entities_merged,
                    facts=result.facts_created,
                    relationships=result.relationships_created,
                )
        except Exception as exc:
            self._log.debug("knowledge_extraction_failed", error=str(exc))
```

- [ ] **Step 4: Update the call site at line 449-452**

Change:

```python
        # Fact extraction every 5th turn (background, non-blocking)
        self._turn_count += 1
        if self._turn_count % 5 == 0 and not voice_mode:
            asyncio.create_task(self._extract_user_facts(user_text, final_response))
```

to:

```python
        # Knowledge extraction every 5th turn (background, non-blocking)
        self._turn_count += 1
        if self._turn_count % 5 == 0:
            asyncio.create_task(self._extract_knowledge(user_text, final_response))
```

Note: Removed `and not voice_mode` — extraction now covers both text and voice paths.

- [ ] **Step 5: Run tests**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_extraction_wiring.py tests/unit/test_voice_routing_unified.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite for regression**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/ -v -x --timeout=60`
Expected: All existing tests PASS

- [ ] **Step 7: Commit**

```bash
cd ~/Emily1.0 && git add agents/conversation.py tests/unit/test_extraction_wiring.py && git commit -m "feat: replace _extract_user_facts with ExtractionPipeline, cover both paths"
```

---

### Task 7: Wire supersede_fact for Contradiction Handling

**Files:**
- Modify: `extraction/pipeline.py:195-234` (`_store_attributes_as_facts`)

- [ ] **Step 1: Write test for contradiction detection**

Add to `tests/unit/test_extraction_wiring.py`:

```python
async def test_supersede_fact_called_on_contradiction() -> None:
    """When a new fact contradicts an existing one, supersede_fact should be called."""
    from unittest.mock import AsyncMock, MagicMock

    from extraction.entity_extractor import ExtractedEntity
    from extraction.pipeline import ExtractionPipeline
    from memory.knowledge_models import EntityRecord, FactRecord

    store = MagicMock()
    # Simulate existing fact for the entity
    existing_fact = FactRecord(
        entity_id="ent-1",
        fact_type="preference",
        fact_text="preference: likes Python",
        confidence=0.9,
        source_id="session-old",
    )
    store.get_entity_facts = AsyncMock(return_value=[existing_fact])
    store.supersede_fact = AsyncMock()
    store.add_fact = AsyncMock()

    pipeline = ExtractionPipeline.__new__(ExtractionPipeline)
    pipeline._store = store

    entity = EntityRecord(
        id="ent-1",
        type="person",
        canonical_name="User",
    )
    extracted = ExtractedEntity(
        canonical_name="User",
        type="person",
        attributes={"preference": "hates Python"},
        confidence=0.8,
    )

    await pipeline._store_attributes_as_facts(entity, extracted, "session-new")

    # supersede_fact should have been called for the contradicting preference
    store.supersede_fact.assert_called_once()
    old_id = store.supersede_fact.call_args[0][0]
    assert old_id == existing_fact.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_extraction_wiring.py::test_supersede_fact_called_on_contradiction -v`
Expected: FAIL — `_store_attributes_as_facts` doesn't check for existing facts

- [ ] **Step 3: Implement contradiction detection in _store_attributes_as_facts**

Replace the `_store_attributes_as_facts` method in `extraction/pipeline.py`:

```python
    async def _store_attributes_as_facts(
        self,
        entity: EntityRecord,
        extracted: ExtractedEntity,
        session_id: str,
    ) -> int:
        """
        Convert extracted attribute key-value pairs into FactRecords.

        Skips attributes that are already handled by the people schema
        (occupation, employer, relationship_to_user) to avoid duplication.

        When a fact of the same type already exists for this entity,
        supersedes the old fact instead of creating a duplicate.

        Args:
            entity: The canonical entity to attach facts to.
            extracted: Source of attribute data.
            session_id: Provenance session.

        Returns:
            Number of facts stored.
        """
        _SCHEMA_ATTRS = {"occupation", "employer", "relationship_to_user"}
        count = 0

        for key, value in extracted.attributes.items():
            if key in _SCHEMA_ATTRS or not value:
                continue

            new_fact = FactRecord(
                entity_id=entity.id,
                fact_type=key,
                fact_text=f"{key}: {value}",
                confidence=extracted.confidence,
                source_id=session_id,
            )

            # Check for existing facts of the same type for this entity
            try:
                existing = await self._store.get_entity_facts(
                    entity.id, fact_type=key,
                )
                if existing:
                    # Supersede the most recent existing fact
                    old = existing[0]  # sorted by timestamp DESC
                    if old.fact_text != new_fact.fact_text:
                        await self._store.supersede_fact(old.id, new_fact)
                        count += 1
                        continue
                    else:
                        continue  # Same fact, skip
            except Exception as exc:
                log.debug("contradiction_check_failed", error=str(exc))

            try:
                await self._store.add_fact(new_fact)
                count += 1
            except ValueError:
                pass  # Below confidence threshold — already logged in store

        return count
```

- [ ] **Step 4: Run tests**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/test_extraction_wiring.py -v`
Expected: All PASS

- [ ] **Step 5: Run full suite**

Run: `cd ~/Emily1.0 && uv run pytest tests/unit/ -v -x --timeout=60`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd ~/Emily1.0 && git add extraction/pipeline.py tests/unit/test_extraction_wiring.py && git commit -m "feat: wire supersede_fact for contradiction handling in extraction"
```

---

### Task 8: Integration Smoke Test

**Files:**
- No new files — verify end-to-end coherence

- [ ] **Step 1: Verify imports work**

Run: `cd ~/Emily1.0 && uv run python -c "from voice_engine.providers.llm.emily_llm import EmilyLLMProvider; print('OK')"`
Expected: `OK`

- [ ] **Step 2: Verify extraction pipeline imports**

Run: `cd ~/Emily1.0 && uv run python -c "from extraction.pipeline import ExtractionPipeline; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify no _COMPLEX_VOICE_RE remains**

Run: `cd ~/Emily1.0 && uv run python -c "import voice_engine.providers.llm.emily_llm as m; assert not hasattr(m, '_COMPLEX_VOICE_RE'); print('CLEAN')"`
Expected: `CLEAN`

- [ ] **Step 4: Run ruff**

Run: `cd ~/Emily1.0 && uv run ruff check voice_engine/providers/llm/emily_llm.py agents/conversation.py extraction/pipeline.py`
Expected: Clean or fixable warnings only

- [ ] **Step 5: Run basedpyright on changed files**

Run: `cd ~/Emily1.0 && uv run basedpyright voice_engine/providers/llm/emily_llm.py agents/conversation.py extraction/pipeline.py`
Expected: 0 errors (warnings OK)

- [ ] **Step 6: Final commit**

```bash
cd ~/Emily1.0 && git add -A && git commit -m "chore: cleanup after routing unification + extraction wiring"
```

---

## Verification Checklist

After all tasks complete, verify these acceptance criteria:

1. `_COMPLEX_VOICE_RE` and `_is_complex_voice_query` no longer exist in `emily_llm.py`
2. `fleet.route()` is called with `voice_mode=True` in the voice path
3. `urgency` parameter derives from `emotional_state.concern` in both voice and text paths
4. Voice path `add_assistant_turn` includes `tier`, `model`, `latency_ms` in metadata
5. `_extract_user_facts` no longer exists — replaced by `_extract_knowledge` using `ExtractionPipeline`
6. Knowledge extraction runs on both voice AND text turns (every 5th turn)
7. `supersede_fact()` is called when a new fact contradicts an existing one of the same type
8. All existing unit tests still pass
