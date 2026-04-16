# emily-memory: Event-Sourced Memory Library for Emily

**Date:** 2026-04-16
**Status:** Approved
**Approach:** Layered Engine + Event-Sourced Storage Core (A+B hybrid)

## Overview

A standalone Python library extracted from Emily's `memory/` directory into `packages/emily-memory/`. Emily imports it as her memory engine. The library owns all storage, provides rich query/edit/segmentation operations, and includes a full experimentation framework for researching memory strategies.

**Goals:**
- Clean separation of concerns — memory system is independently testable
- Event-sourced core — full audit trail, time-travel, replay with different configs
- Rich operations — temporal/semantic/graph queries, surgical editing, composable segmentation
- Experiment engine — snapshots, replay, A/B framework, benchmarks, always-on metrics
- Pluggable backends — protocols for storage, vectors, graph, embeddings
- Zero-change frontend — emily-brain still hits the same FastAPI endpoints

**Non-goals:**
- Network serving (HTTP/gRPC) — Emily's FastAPI layer handles that
- Building new frontend UI — emily-brain already exists
- Changing the 5-tier architecture — tiers stay, engine underneath improves

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  MemoryEngine                                        │
│  (top-level orchestrator, public API)                │
├─────────────────────────────────────────────────────┤
│  Layer 3: Experiment Engine                          │
│  snapshot, replay, A/B, metrics, benchmarks          │
├─────────────────────────────────────────────────────┤
│  Layer 2: Operations                                 │
│  query, edit, segment, link, retrieval pipeline      │
├─────────────────────────────────────────────────────┤
│  Layer 1: Storage Core (event-sourced)               │
│  events, event store, materializer, lifecycle,       │
│  backend protocols (SQLite, Qdrant, graph)           │
├─────────────────────────────────────────────────────┤
│  Embedding Subsystem                                 │
│  protocol + BGE-M3 default + injection support       │
└─────────────────────────────────────────────────────┘
```

**Data flow:**

```
Write path:  caller → engine.write() → EventStore.append(MemoryCreated) → Materializer → TierView
Edit path:   caller → engine.edit()  → EventStore.append(MemoryUpdated) → Materializer → TierView patched
Read path:   caller → engine.query() → TierView (fast read, no event replay)
```

## Package Structure

```
Emily1.0/
├── packages/
│   └── emily-memory/
│       ├── pyproject.toml
│       ├── src/
│       │   └── emily_memory/
│       │       ├── __init__.py              # Public API surface
│       │       ├── engine.py                # MemoryEngine orchestrator
│       │       ├── config.py                # Pydantic settings
│       │       │
│       │       ├── core/                    # Layer 1: Storage Core
│       │       │   ├── events.py            # Immutable event types
│       │       │   ├── event_store.py       # Append-only event log (SQLite WAL)
│       │       │   ├── tiers.py             # MemoryTier enum + tier protocols
│       │       │   ├── models.py            # Memory, Episode, Fact, Relation
│       │       │   ├── materializer.py      # Event → materialized tier view
│       │       │   ├── lifecycle.py         # Consolidation, decay, promotion, GC
│       │       │   └── backends/
│       │       │       ├── protocol.py      # StorageBackend, VectorBackend, GraphBackend
│       │       │       ├── sqlite.py        # SQLite implementation
│       │       │       ├── qdrant.py        # Qdrant vector implementation
│       │       │       └── graph.py         # SQLite-backed graph (replaces networkx)
│       │       │
│       │       ├── ops/                     # Layer 2: Operations
│       │       │   ├── query.py             # Temporal, Semantic, Graph, CrossTier, And, Or, TagFilter
│       │       │   ├── edit.py              # Surgical edit, patch, promote, merge, split, delete, purge
│       │       │   ├── segment.py           # Segmentation pipeline (auto + manual)
│       │       │   ├── link.py              # Tag, link, relate, discover_links
│       │       │   └── retrieval.py         # Hybrid retrieval (BM25 + dense + RRF + reranker)
│       │       │
│       │       ├── experiment/              # Layer 3: Experiment Engine
│       │       │   ├── snapshot.py          # Snapshot/restore/fork memory state
│       │       │   ├── replay.py            # Replay events with config overrides
│       │       │   ├── ab.py                # A/B experiment framework
│       │       │   ├── metrics.py           # Always-on instrumentation
│       │       │   └── bench.py             # Benchmark harness
│       │       │
│       │       ├── embedding/               # Embedding subsystem
│       │       │   ├── protocol.py          # Embedder protocol
│       │       │   ├── bge.py               # BGE-M3 default (Ollama or sentence-transformers)
│       │       │   └── cache.py             # Embedding cache
│       │       │
│       │       └── migration.py             # migrate_from_legacy() — one-time import from current Emily
│       │
│       └── tests/
│           ├── conftest.py                  # Fixtures, factories, tmp engine instances
│           ├── test_core/
│           │   ├── test_events.py
│           │   ├── test_event_store.py
│           │   ├── test_materializer.py
│           │   ├── test_lifecycle.py
│           │   └── test_backends/
│           ├── test_ops/
│           │   ├── test_query.py
│           │   ├── test_edit.py
│           │   ├── test_segment.py
│           │   ├── test_link.py
│           │   └── test_retrieval.py
│           └── test_experiment/
│               ├── test_snapshot.py
│               ├── test_replay.py
│               ├── test_ab.py
│               └── test_bench.py
```

## Core Types

### MemoryTier

```python
class MemoryTier(str, Enum):
    SENSORY = "sensory"         # Ring buffer, milliseconds–seconds
    WORKING = "working"         # Token-budget context, seconds–minutes
    EPISODIC = "episodic"       # Session-level, minutes–years
    SEMANTIC = "semantic"       # Knowledge/facts, long-term
    PROCEDURAL = "procedural"   # Skills, identity, meta-knowledge
```

### Memory

```python
class Memory(BaseModel):
    id: str                              # UUID
    tier: MemoryTier
    content: str
    embedding: list[float] | None
    importance: float                    # 0.0–1.0
    created_at: float                    # Unix timestamp
    updated_at: float
    decay_rate: float                    # Per-tier default, adjustable
    tags: list[str]
    links: list[str]                     # IDs of related memories
    metadata: dict[str, Any]
    source_events: list[str]             # Event IDs that produced this state
```

### EventType

```python
class EventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    PROMOTED = "promoted"
    DECAYED = "decayed"
    DELETED = "deleted"
    MERGED = "merged"
    SPLIT = "split"
    LINKED = "linked"
    TAGGED = "tagged"
    TIER_SNAPSHOT = "tier_snapshot"
```

### MemoryEvent

```python
class MemoryEvent(BaseModel):
    id: str                              # UUID
    timestamp: float
    event_type: EventType
    memory_id: str
    tier: MemoryTier
    payload: dict[str, Any]              # Event-specific data
    actor: str                           # "system" | "user" | "agent:{name}"
```

## Layer 1: Storage Core (Event-Sourced)

### Event Store

Append-only SQLite database with WAL mode. Source of truth for all memory state.

**Schema:**

```sql
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    payload TEXT NOT NULL,           -- JSON
    actor TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX idx_events_memory ON events(memory_id);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_timestamp ON events(timestamp);
CREATE INDEX idx_events_tier ON events(tier);
```

### Event Types Detail

| Event | Payload | Trigger |
|-------|---------|---------|
| `CREATED` | content, tier, importance, embedding, tags, metadata | New memory |
| `UPDATED` | patch (changed fields dict), reason | Edit or auto-enrichment |
| `PROMOTED` | old_tier, new_tier, reason | Threshold crossed or manual |
| `DECAYED` | old_importance, new_importance | Lifecycle tick |
| `DELETED` | reason, soft (bool) | Manual or GC |
| `MERGED` | source_ids, merged_content, strategy | Fusion of 2+ memories |
| `SPLIT` | source_id, resulting_ids, split_points | Segmentation |
| `LINKED` | source_id, target_id, relation_type | Manual or auto-detected |
| `TAGGED` | tags_added, tags_removed | Manual or classifier |
| `TIER_SNAPSHOT` | tier, memory_count, checksum | Periodic checkpoint |

### Materializer

Subscribes to events, updates tier-specific storage:

| Tier | Materialized Into |
|------|-------------------|
| Sensory | In-memory `deque` (ring buffer, configurable capacity) |
| Working | In-memory list with token budget (tiktoken cl100k_base) |
| Episodic | SQLite table + Qdrant vectors |
| Semantic | SQLite metadata + Qdrant vectors + BM25 index |
| Procedural | SQLite structured facts table |

**Key rule:** Event log = source of truth. Materialized views = caches. If a view corrupts, replay events from last `TIER_SNAPSHOT` to rebuild.

### Lifecycle Engine

Runs on configurable tick (default 60s):

```python
class LifecycleEngine:
    async def tick(self) -> list[MemoryEvent]:
        events = []
        events += self._apply_decay()          # importance *= exp(-decay_rate * elapsed)
        events += self._check_promotions()     # Working → Episodic if importance > threshold
        events += self._run_consolidation()    # Merge similar episodic memories
        events += self._garbage_collect()      # Soft-delete below importance floor
        return events
```

Configurable parameters:
- `decay_rate` per tier (default: sensory=0.5, working=0.1, episodic=0.01, semantic=0.001, procedural=0.0)
- `promotion_threshold` (default: 0.6)
- `consolidation_similarity` (default: 0.85)
- `gc_importance_floor` (default: 0.05)
- `tick_interval_seconds` (default: 60)

### Backend Protocols

```python
class StorageBackend(Protocol):
    async def store(self, memory: Memory) -> None: ...
    async def get(self, memory_id: str) -> Memory | None: ...
    async def delete(self, memory_id: str) -> None: ...
    async def list(self, tier: MemoryTier, limit: int, offset: int) -> list[Memory]: ...
    async def update(self, memory_id: str, patch: dict[str, Any]) -> None: ...

class VectorBackend(Protocol):
    async def upsert(self, memory_id: str, vector: list[float], metadata: dict) -> None: ...
    async def search(self, vector: list[float], top_k: int, filters: dict | None) -> list[ScoredResult]: ...
    async def delete(self, memory_id: str) -> None: ...

class GraphBackend(Protocol):
    async def add_node(self, node_id: str, labels: list[str], properties: dict) -> None: ...
    async def add_edge(self, source: str, target: str, relation: str, properties: dict) -> None: ...
    async def query(self, pattern: GraphPattern) -> list[dict]: ...  # Typed pattern object, not a query string
    async def neighbors(self, node_id: str, depth: int, relation_filter: str | None) -> list[dict]: ...
```

Default implementations: `SqliteBackend`, `QdrantVectorBackend`, `SqliteGraphBackend`.

## Layer 2: Operations

### Query System

Composable query objects that work across tiers:

```python
# Temporal
TemporalQuery(after=timestamp, before=timestamp, tiers=[EPISODIC])

# Semantic
SemanticQuery(text="conversation about Rust async", top_k=10)

# Graph traversal
GraphQuery(start=memory_id, relation="related_to", depth=3)

# Cross-tier join
CrossTierQuery(
    anchor=SemanticQuery(text="machine learning"),
    join_tiers=[EPISODIC, PROCEDURAL],
    join_on="links"  # or "embedding_similarity" or "temporal_proximity"
)

# Compound
And(TemporalQuery(...), SemanticQuery(...), TagFilter(tags=["debugging"]))
Or(SemanticQuery(...), GraphQuery(...))
```

### Retrieval Pipeline

Composable chain of `RetrievalStep` protocol implementations:

```python
class RetrievalStep(Protocol):
    async def execute(self, context: RetrievalContext) -> RetrievalContext: ...
```

Default pipeline (matches Emily's current behavior):
1. `QueryExpander` — LLM rewrites query 3 ways
2. `BM25Search` — sparse retrieval, top_k=50
3. `DenseSearch` — Qdrant dense vector retrieval, top_k=50
4. `RRFMerge` — Reciprocal Rank Fusion, k=60
5. `ParentChunkPromoter` — promote to parent chunks (2048 tokens)
6. `CrossEncoderReranker` — BGE-reranker-v2-m3
7. `TemporalDecayScorer` — recency bias, half_life_days=30

Steps are swappable, reorderable, removable. The experiment engine tests pipeline variants.

### Edit Operations

```python
engine.edit(memory_id, content=str, reason=str)         # → MemoryUpdated event
engine.patch(memory_id, fields=dict)                     # → MemoryUpdated event
engine.promote(memory_id, to_tier=MemoryTier, reason=str)# → MemoryPromoted event
engine.merge(ids=list[str], strategy=str)                # → MemoryMerged event
engine.split(memory_id, at_turns=list[int])              # → MemorySplit event
engine.delete(memory_id, soft=True)                      # → MemoryDeleted event (recoverable)
engine.purge(memory_id)                                  # Hard delete (irreversible)
```

Merge strategies: `"llm_summarize"`, `"concatenate"`, `"pick_best"`.

### Segmentation Pipeline

Composable chain of `SegmentationStep` protocol implementations:

```python
class SegmentationStep(Protocol):
    async def execute(self, turns: list[Turn]) -> list[Segment]: ...
```

Default auto-segmentation:
1. `TopicBoundaryDetector` — embedding cosine distance, threshold=0.3
2. `EmotionalShiftDetector` — tone change detection, window=5
3. `SilenceGapDetector` — 2min silence = new segment
4. `ImportanceScorer` — score each segment
5. `TierAssigner` — assign to appropriate tier

Manual operations: `engine.resegment(episode_id, pipeline=custom)`.

### Linking

```python
engine.link(source_id, target_id, relation=str)          # Explicit link
engine.discover_links(memory_id, min_similarity=0.8)     # Auto-discover proposals
engine.accept_links(proposed_links)                       # Accept proposals
engine.tag(memory_id, tags=list[str])                     # Tag memory
```

## Layer 3: Experiment Engine

### Snapshots

```python
engine.experiment.snapshot(name=str) -> str               # Freeze state (event log position + checksums)
engine.experiment.restore(snapshot_id=str)                 # Rebuild materialized views to that point
engine.experiment.list_snapshots() -> list[Snapshot]
engine.experiment.fork(name=str, from_snapshot=str) -> str # Isolated copy for experimentation
```

Fork creates a new SQLite database + Qdrant collection. Fully isolated.

### Replay

```python
# Replay with different lifecycle config
engine.experiment.replay(
    from_snapshot=str,
    config_overrides=dict,
) -> ReplayResult  # Final state, tier distribution, memories lost/kept

# Replay retrieval with different pipelines
engine.experiment.replay_retrieval(
    queries=list[str],
    pipelines=dict[str, RetrievalPipeline],
) -> RetrievalComparisonResult  # Per-query ranked results, overlap analysis
```

### A/B Framework

```python
exp = engine.experiment.create(
    name=str,
    hypothesis=str,
    variants=dict[str, dict],              # Config overrides per variant
    metric=str,                            # "recall@10", "precision@5", "mrr", "latency_p95"
    queries=list[Query],                   # Gold query set with known-good results
)
report = engine.experiment.run(exp.id)
# Report: per-variant metrics, bootstrap confidence intervals, winner, raw diff
```

### Metrics (Always-On)

```python
class MemoryMetrics:
    # Tier health
    tier_distribution: dict[MemoryTier, int]
    tier_avg_importance: dict[MemoryTier, float]
    decay_rate_effective: float                      # Memories lost/day

    # Query performance
    query_latency_p50: float
    query_latency_p95: float
    retrieval_hit_rate: float

    # Lifecycle
    promotions_per_day: float
    consolidations_per_day: float
    gc_deletions_per_day: float

    # Storage
    event_log_size_bytes: int
    materialized_size_bytes: int
    vector_count: int
```

`engine.metrics.current()` for point-in-time, `engine.metrics.history(days=30)` for trends.

### Benchmark Harness

```python
engine.experiment.bench(
    name=str,
    setup=Callable,
    operation=Callable,
    iterations=int,
    warmup=int,
) -> BenchResult  # min, max, mean, p50, p95, p99, ops/sec
```

## Embedding Subsystem

### Protocol

```python
class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dimension(self) -> int: ...
```

### Default: BGE-M3 via Ollama

Ships with `OllamaEmbedder(model="bge-m3")` for standalone use.

### Injection

Emily passes her fleet's embedder at init:

```python
class EmilyFleetEmbedder(Embedder):
    def __init__(self, fleet: LLMFleet):
        self._fleet = fleet
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._fleet.embed_batch(texts)
    @property
    def dimension(self) -> int:
        return 1024  # BGE-M3
```

### Embedding Cache

Disk-backed cache (diskcache) keyed on `hash(text + model_name)`. Avoids recomputation on replay/experiments.

## Public API Surface

```python
# Core
MemoryEngine, MemoryConfig, Memory, MemoryTier, MemoryEvent, EventType

# Querying
TemporalQuery, SemanticQuery, GraphQuery, CrossTierQuery, And, Or, TagFilter

# Pipelines
RetrievalPipeline, RetrievalStep, SegmentationPipeline, SegmentationStep

# Experiment
ExperimentEngine, Snapshot, Replay, ABExperiment, MemoryMetrics, BenchResult

# Protocols
StorageBackend, VectorBackend, GraphBackend, Embedder
```

## Emily Integration

### What Changes

| Current | New |
|---------|-----|
| `memory/manager.py` (MemoryManager) | `from emily_memory import MemoryEngine` |
| `memory/episodic.py` | `emily_memory.core.backends.sqlite` |
| `memory/semantic/` (retriever, vector_store, bm25, reranker) | `emily_memory.ops.retrieval` + `emily_memory.core.backends.qdrant` |
| `memory/working.py` | `emily_memory.core.materializer` (working tier) |
| `memory/sensory_buffer.py` | `emily_memory.core.materializer` (sensory tier) |
| `memory/procedural.py` | `emily_memory.core.backends.sqlite` (structured table) |
| `memory/interaction_logger.py` | `emily_memory.core.event_store` (write-through) |
| `data/procedural.json` | SQLite (migrated on first start) |
| networkx graph | `emily_memory.core.backends.graph` (SQLite-backed) |

### What Does NOT Change

- emily-brain frontend — same FastAPI endpoints
- Voice loop — still calls memory agent
- LLM fleet — injects embedder via protocol
- RAG ingestion — feeds into `engine.write()` instead of direct tier writes
- `agents/memory_agent.py` — rewired to engine methods, same behavior

### Migration

`emily_memory.migration.migrate_from_legacy()`:
1. Reads current SQLite databases (interactions.db, episodes.db, knowledge.db)
2. Reads procedural.json
3. Reads Qdrant collections
4. Replays everything as events into the new event store
5. Materializes all tier views
6. Idempotent (safe to run multiple times), reversible (old files untouched)

## Dependencies

### Runtime

| Package | Purpose |
|---------|---------|
| `pydantic>=2.0` | Config, models, validation |
| `aiosqlite>=0.20` | Event store, materialized views, graph backend |
| `qdrant-client>=1.9` | Vector backend |
| `rank-bm25>=0.2` | Sparse retrieval |
| `numpy>=1.26` | Vector operations, RRF |
| `tiktoken>=0.7` | Token counting (working memory) |
| `diskcache>=5.6` | Embedding cache |
| `httpx>=0.27` | Ollama client for default embedder |

### Optional

| Package | Purpose |
|---------|---------|
| `sentence-transformers>=3.0` | Local BGE-M3 (alternative to Ollama) |
| `scipy>=1.12` | Advanced distance metrics |

### Dev

| Package | Purpose |
|---------|---------|
| `pytest>=8.0` | Testing |
| `pytest-asyncio>=0.23` | Async test support |
| `pytest-benchmark>=4.0` | Performance benchmarks |

## Testing Strategy

- **Unit tests per layer:** Core (event store, materializer, lifecycle), Ops (query, edit, segment), Experiment (snapshot, replay, A/B)
- **Integration tests:** Full engine workflows (write → query → edit → verify event log)
- **Property-based tests:** Event replay always produces identical materialized state
- **Benchmark tests:** Retrieval latency at 1K / 10K / 100K memories
- **Fixtures:** Factory functions for `Memory`, `MemoryEvent`, pre-seeded engine instances via `conftest.py`
- **No mocks on storage:** Tests use real SQLite (`:memory:`) and a lightweight Qdrant test collection

## Design Decisions

| Decision | Rationale | Rejected Alternative |
|----------|-----------|---------------------|
| Event-sourced core | Time-travel, replay, audit trail needed for experiments | Direct mutation (no history) |
| SQLite for graph | Durable, no serialization, survives restart | networkx (in-memory, lost on crash) |
| Procedural → SQLite | Data integrity, concurrent access | JSON file (corruption risk, no transactions) |
| Workspace package | Iterate fast alongside Emily, extract later | Separate repo (too much friction during development) |
| Protocols not ABCs | Structural subtyping, no inheritance required | ABC (forces inheritance, less flexible) |
| Materialized views | Fast reads without replaying events | Pure event replay (too slow for queries) |
| TierSnapshot events | Fast restore without replaying from genesis | Full replay every time (O(n) startup) |
