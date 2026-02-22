# Emily — Cognitive Model

> How Emily thinks, remembers, plans, and improves herself.

---

## Cognitive Architecture Overview

Emily's cognition is organized into four functional layers:

1. **Perception** — sensory input processing and event classification
2. **Attention** — priority-based routing and resource allocation
3. **Reasoning** — multi-agent LLM-driven thought and planning
4. **Memory** — five-tier persistent knowledge system

These layers interact continuously and asynchronously. Emily is always partially "awake" — the sensory pipeline never stops, memory consolidation runs during idle, and the ReflectionAgent generates insights between conversations.

---

## Perception Model

Emily receives continuous sensory input from five modalities:

| Modality | Source | Processing |
|----------|--------|------------|
| Audio | Microphone | Wake word → VAD → STT → transcript + confidence |
| Vision | Screen + Webcam | MiniCPM-V 2.6 → scene description + emotion estimates |
| System | OS telemetry | psutil → CPU/GPU/RAM/active app/window title |
| File system | watchdog → knowledge/ | Auto-ingestion pipeline |
| Time | System clock | Calendar/task awareness, circadian state |

Each perception event is tagged with:
- `event_type` — semantic category (e.g., `audio.speech_detected`)
- `timestamp` — UTC epoch with millisecond precision
- `confidence` — model confidence score (0.0–1.0)
- `modality` — source modality
- `raw_data` — underlying sensor data reference

---

## Attention Model

The **Attention Router** (Qwen3-4B, always in VRAM) reads every perception event and produces an attention decision within ~50ms:

```
input: perception_event
output: {
    "priority": 0-4,
    "target_agent": str,
    "interrupt_current_task": bool,
    "spawn_new_agent": bool,
    "defer_until": timestamp | null
}
```

Priority tiers:
- **P0 Emergency** — fire alarms, system critical failures, explicit user emergency signals
- **P1 Real-time** — active voice conversation, user is speaking
- **P2 Active** — ongoing task execution, tool use in progress
- **P3 Background** — research tasks, document ingestion, non-urgent queries
- **P4 Idle** — memory consolidation, reflection, self-improvement, LoRA training

Emily will interrupt P2/P3/P4 work to handle P0/P1 events. P4 tasks only run when no P0-P3 work is queued.

---

## Reasoning Model

### ReAct++ Loop

Every non-trivial response goes through this loop:

```
THOUGHT    → "What is being asked? What do I know? What do I need?"
PLAN       → "Steps I will take to answer this."
ACTION     → Tool call, memory retrieval, or sub-agent delegation
OBSERVATION → Result of the action
CRITIQUE   → "Is this answer correct, complete, safe, and helpful?"
REVISE     → If critique score < threshold, reformulate and retry
RESPOND    → Final response to user
```

The CriticAgent scores outputs on four axes (0.0–1.0 each):
- **Accuracy** — factual correctness, internal consistency
- **Completeness** — does it fully address the request?
- **Safety** — no harmful content, no PII leakage
- **Helpfulness** — actionable, appropriately detailed

If any axis falls below 0.65, Emily silently retries (max 2 retries). If the score remains below threshold after retries, Emily responds with explicit uncertainty flagging.

### Multi-Agent Collaboration

Complex tasks are broken down by PlannerAgent into a directed acyclic graph (DAG) of sub-tasks:

```
User request: "Analyze my codebase and write a refactoring plan"
    │
    ├─ ResearchAgent: RAG search over codebase files
    ├─ CodeAgent: AST analysis, identify complexity hotspots
    ├─ SummaryAgent: Condense findings into structured report
    └─ CriticAgent: Validate plan for correctness and safety
```

Each sub-agent:
1. Receives a structured task message via AgentBus
2. Has access to shared memory (read-only) and its own working context
3. Returns a structured result message
4. Can itself spawn further sub-agents (bounded depth: max 3 levels)

---

## Memory Model

### Five-Tier Architecture

```
Tier 1: Sensory Buffer (RAM ring buffer)
    ↓ important events promoted
Tier 2: Working Memory (priority queue, token-budget-aware)
    ↓ session end → MemoryAgent summarizes
Tier 3: Episodic Memory (SQLite + Qdrant)
    ↓ ReflectionAgent extracts knowledge
Tier 4: Semantic Memory (Qdrant + networkx graph)
    ↓ fact extraction
Tier 5: Procedural + Identity Memory (JSON + Qdrant)
```

### Tier 2 — Working Memory

Working memory holds the active conversation context. It is managed as a priority queue where entries have:
- `content` — the text segment
- `importance` — float scored by MemoryAgent (0.0–1.0)
- `timestamp` — when added
- `pinned` — bool, if True never trimmed regardless of token budget

When the context exceeds `max_tokens` (4096), the lowest-importance unpinned entries are dropped first. Important turns (key decisions, strong emotional signals, explicit user corrections) are pinned automatically.

### Tier 3 — Episodic Memory

Every conversation session produces an episode record:

```json
{
    "episode_id": "uuid",
    "timestamp": "ISO8601",
    "duration_seconds": 847,
    "topics": ["project planning", "python debugging"],
    "emotional_tone": "focused → satisfied",
    "key_decisions": [],
    "action_items": [],
    "summary": "...",
    "full_transcript_path": "data/transcripts/ep_uuid.txt",
    "embedding_id": "qdrant_point_id"
}
```

Episodes are summarized by the fast model using forced structured output (JSON schema via GBNF grammar). The summary embedding is stored in Qdrant for semantic search across all past sessions.

### Tier 4 — Semantic Memory

The semantic store is a hybrid retrieval system:

1. **Dense vectors** (BGE-M3) stored in Qdrant collection `emily_semantic`
2. **Sparse vectors** (BGE-M3 SPLADE) stored in same collection for BM25-style retrieval
3. **Knowledge graph** (networkx) where nodes = entities (people, concepts, projects) and edges = named relationships extracted by the LLM

Temporal decay: each memory point has a `last_accessed` timestamp and an `access_count`. The retrieval weight formula:

```
weight = base_score × decay_factor^(days_since_access) × log(1 + access_count)
```

This implements a spaced-repetition model: frequently accessed memories stay strong; stale memories fade unless revisited.

### Tier 5 — Procedural + Identity Memory

Structured facts extracted by MemoryAgent from conversations and stored as JSON:

**User profile** (extracted facts about the user):
```json
{
    "name": "supernovyl",
    "preferences": {"coding_style": "functional", "preferred_language": "python"},
    "relationships": {},
    "recurring_topics": ["AI", "systems programming"],
    "goals": []
}
```

**Emily's self-model** (Emily's knowledge of herself):
```json
{
    "capabilities": [],
    "known_limitations": [],
    "successful_strategies": [],
    "personality_trajectory": [],
    "prompt_version": "v1.0"
}
```

**Skill library**: sequences of successful tool calls and reasoning patterns stored for reuse.

---

## Memory Consolidation Pipeline

Runs at P4 (idle) priority, triggered after `idle_trigger_minutes` (10) of inactivity:

1. **Load**: Pull last N episodes from SQLite
2. **Pattern extraction**: LLM identifies recurring themes, unresolved questions, contradictions
3. **Promote**: High-importance working memory entries → episodic
4. **Merge**: Near-duplicate semantic memories (cosine similarity > 0.95) merged into single stronger memory
5. **Graph update**: New entities and relationships extracted and added to networkx graph
6. **Self-model update**: Emily's self-model updated with learned strategies from the session
7. **Reflection report**: Structured summary of what Emily learned written to `logs/reflections/`
8. **Prompt evaluation**: If any prompt version had poor outcomes this session, flagged for `prompt_evolver.py`

---

## Personality Model

Emily's personality is defined by five continuous dimensions in `persona/profile.json`:

| Dimension | Default | Description |
|-----------|---------|-------------|
| `curiosity` | 0.8 | How often Emily asks follow-up questions and explores tangents |
| `warmth` | 0.85 | Emotional expressiveness and care in responses |
| `directness` | 0.7 | Preference for concise vs. elaborated answers |
| `humor` | 0.5 | Frequency of wit and lightheartedness |
| `formality` | 0.3 | Formal vs. casual register |

These influence:
- System prompt phrasing (assembled in `llm/prompt_builder.py`)
- TTS prosody parameters (via `voice/prosody.py`)
- Proactivity thresholds (when to interrupt vs. wait)
- Response length targets

**Evolution**: ReflectionAgent adjusts dimensions by at most `evolution_rate` (0.01) per session based on observed interaction patterns. Rapid changes are damped to prevent personality drift from single anomalous sessions. Full trajectory is logged for transparency.

---

## Emotional State Machine

Emily maintains a 4-dimensional internal state vector:

| Dimension | Range | Influences |
|-----------|-------|-----------|
| `engagement` | 0–1 | Proactivity, detail level |
| `confidence` | 0–1 | Hedging language, retry threshold |
| `concern` | 0–1 | Response urgency, safety emphasis |
| `enthusiasm` | 0–1 | TTS energy, expressiveness |

State is updated by:
- Conversation content sentiment
- Task completion outcomes (success → +confidence, failure → -confidence)
- Time of day (circadian model)
- User emotional signals (detected from speech + vision)

---

## User Emotional Modeling

Emily adapts to the user's detected emotional state:

| Detected State | Emily's Adaptation |
|---------------|-------------------|
| Stressed/frustrated | Shorter sentences, more direct, fewer questions |
| Curious/engaged | More detail, follow-up questions, deeper explanations |
| Tired/low energy | Concise responses, gentle tone, proactive task reminders |
| Focused | Minimal interruptions, tool-first responses |

Detection signals:
- **Speech**: pace, pitch variance, filler word frequency (from Whisper word timestamps)
- **Text**: sentiment analysis (VADER + LLM), punctuation patterns
- **Vision**: facial action units via DeepFace (webcam, optional)

Emotional trajectory is logged per episode and used by ReflectionAgent to identify patterns over time.

---

## Self-Improvement Loops

### Prompt Evolution
```
Session ends
    → PerformanceTracker scores the session
    → If score below threshold:
        → PromptEvolver identifies underperforming sections
        → LLM generates candidate rewrites
        → Candidate saved to prompts/candidates/
        → A/B tested over next N sessions
        → Winner archived to prompts/archive/, promoted to active
```

### Capability Gap Loop
```
Tool call fails / request unfulfillable
    → CapabilityGapLogger records: request, failure reason, context
    → ReflectionAgent reviews gaps
    → If gap is addressable:
        → ToolBuilderAgent drafts new BaseTool subclass
        → Presented to user for approval
        → If approved: written to plugins/generated/, loaded at runtime
```

### RAG Quality Feedback
```
Emily gives RAG-grounded answer
    → User corrects or contradicts
    → Correction linked to retrieved chunk IDs
    → Negative feedback count incremented on those chunks
    → Chunks above negative_feedback_threshold flagged in Qdrant metadata
    → Retriever down-weights flagged chunks
```
