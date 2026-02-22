# Emily — System Architecture

> **Emily** is a self-evolving, multi-agent local AI voice operating system.
> She is not an assistant — she is a persistent cognitive entity that learns,
> plans, reasons, and improves herself over time, running entirely on local hardware.

---

## Hardware Baseline

| Component | Spec |
|-----------|------|
| CPU | Intel i9-14900K (24 cores / 32 threads, up to 6.0 GHz) |
| RAM | 62 GB DDR5 |
| GPU | NVIDIA RTX 4090 (24 GB VRAM, CUDA 12.x) |
| Storage | NVMe, ~762 GB free |
| OS | Arch Linux 6.18.9-arch1-2, bare metal |
| Network | Local LAN + internet access |

---

## System Layers

### Layer 0 — Sensory Input Bus

Emily perceives the world through multiple simultaneous modalities:

- **Audio**: Continuous always-on stream → 3-stage pipeline:
  - Stage 1: openWakeWord ("Hey Emily") — custom ONNX model
  - Stage 2: Silero VAD with adaptive noise-floor learning
  - Stage 3: Faster-Whisper large-v3 (CUDA, float16) — word-level timestamps, confidence scores
- **Vision**: Screenshot capture (mss) + webcam feed (OpenCV) → MiniCPM-V 2.6 for scene/emotion understanding
- **System telemetry**: psutil-based CPU/GPU/RAM/process monitoring, window title, clipboard
- **File system events**: watchdog monitors `knowledge/` for auto-ingestion
- **Calendar/tasks**: reads local iCal/JSON task files

All sensory streams publish to the **Perception Bus** (ZeroMQ PUSH/PULL), which timestamps, tags, and routes events to the attention router.

### Layer 1 — Attention & Routing Engine

Qwen3-4B (nano model, always in VRAM) acts as the fast attention router:
- Classifies incoming events by urgency and type
- Assigns one of 5 priority levels (P0 Emergency → P4 Idle)
- Routes to the appropriate agent or subsystem
- Determines whether multi-agent spawning is needed

Priority queue managed by `core/scheduler.py` with per-tier concurrency caps.

### Layer 2 — Multi-Agent Cognitive Core

**Primary agents** (always running, registered on the AgentBus):

| Agent | Role |
|-------|------|
| `ConversationAgent` | Real-time dialogue, persona, conversational flow |
| `PlannerAgent` | Task decomposition, sub-agent delegation, completion tracking |
| `MemoryAgent` | All memory tier reads/writes, importance scoring |
| `ReflectionAgent` | Idle-time insight generation, self-model updates |

**On-demand agents** (spawned as needed):

| Agent | Role |
|-------|------|
| `ResearchAgent` | Deep-dive RAG + reasoning chains |
| `CodeAgent` | Write, test, debug code in sandboxed executor |
| `SummaryAgent` | Condense documents and conversations |
| `CriticAgent` | Score outputs, trigger silent retry below threshold |
| `ToolBuilderAgent` | Write new BaseTool subclasses at runtime |
| `MonitorAgent` | System resource monitoring, anomaly alerts |

Inter-agent communication uses `core/bus.py` (AgentBus) with a structured JSON envelope:
```json
{
  "sender": "PlannerAgent",
  "recipient": "CodeAgent",
  "task_id": "uuid",
  "type": "task_delegation",
  "payload": {},
  "priority": 2,
  "deadline_ms": 5000,
  "context_refs": ["memory_id_1"]
}
```

### Layer 3 — LLM Orchestration Engine

**Model fleet** (served via Ollama and llama-cpp-python, per-tier):

| Tier | Model | Backend | VRAM | Use Case |
|------|-------|---------|------|----------|
| nano | Qwen3-4B | llamacpp (GGUF) | ~3 GB | Routing, classification, <100ms |
| voice_fast | Qwen3-4B | llamacpp (alias of nano) | shared | Voice fast path |
| fast | Qwen3-14B Q4_K_M | ollama | ~10 GB | Standard conversation, <2s |
| smart | QwQ-32B Q4_K_M | ollama | ~20 GB | Complex reasoning, planning, <15s |
| reasoning | QwQ-32B Q4_K_M | ollama | shared | Chain-of-thought, math, logic |
| (alt smart) | Qwen3-32B Q4_K_M | ollama | ~20 GB | Hybrid thinking mode, inactive by default |
| vision | MiniCPM-V 2.6 | ollama | ~8 GB | Screen + webcam understanding |
| embedding | BGE-M3 | ollama | ~2 GB | All embedding tasks (8k context) |

The nano model is permanently resident in VRAM. Fast and smart models are hot-swapped based on the router's complexity score. With 24 GB VRAM: nano + fast can co-reside; smart/reasoning displaces fast when needed.

**Intelligent model router** (`llm/router.py`) selects model based on:
- Task complexity score (0-10, scored by nano model)
- Available VRAM headroom
- Whether streaming is required
- User urgency level

**ReAct++ reasoning loop** (every non-trivial task):
```
THOUGHT → PLAN → ACTION → OBSERVATION → CRITIQUE → REVISE → RESPOND
```

### Layer 4 — Pentagonal Memory Architecture

Five interconnected memory tiers:

| Tier | Name | Duration | Implementation |
|------|------|----------|---------------|
| 1 | Sensory Buffer | ms–s | RAM ring buffer |
| 2 | Working Memory | s–min | Priority queue + token-budget trimming |
| 3 | Episodic Memory | min–years | SQLite + Qdrant embedding |
| 4 | Semantic Memory | permanent | Qdrant + networkx knowledge graph |
| 5 | Procedural + Identity | permanent | JSON + Qdrant |

**Memory consolidation** runs during idle (P4):
- ReflectionAgent reviews recent episodes
- Promotes important working memories to episodic
- Merges near-duplicate semantic memories
- Updates knowledge graph edges
- Updates Emily's self-model

### Layer 5 — Knowledge & RAG System

Ingestion pipeline supports: `.pdf`, `.docx`, `.epub`, `.md`, `.txt`, `.html`, `.py`, `.ipynb`, `.csv`, `.json`, `.yaml`, `.pptx`, `.mp3`, `.mp4`

Chunking strategy:
- Child chunks: 256 tokens (for precise retrieval)
- Parent chunks: 2048 tokens (returned to LLM for rich context)
- Semantic boundaries respected via sentence transformers

Retrieval pipeline:
1. Query expansion (LLM generates 3 alternative phrasings)
2. BM25 sparse search on child chunks
3. BGE-M3 dense vector search on child chunks
4. Reciprocal Rank Fusion of BM25 + dense results
5. Parent chunk promotion for matched children
6. Cross-encoder reranking (ms-marco-MiniLM)
7. Knowledge graph neighbor expansion

### Layer 6 — Tool & Plugin Ecosystem

All tools inherit from `BaseTool` (`plugins/base.py`):
- `name`, `description`, `parameters` (JSON Schema)
- `requires_approval: bool` — human-in-the-loop gate
- `async execute(params, context) -> ToolResult`
- `async dry_run(params) -> str` — explains what it would do (mandatory)
- `async validate(params) -> ValidationResult`

Built-in tools: calculator, code_executor, file_reader, file_writer, web_search, web_fetch, shell, memory_search, calendar, home_assistant, git_tool, process_manager, email_reader, knowledge_ingest, clipboard, notification, image_analyzer.

`ToolBuilderAgent` extends the system at runtime: writes new `BaseTool` subclasses, presents for user approval, loads from `plugins/generated/`.

### Layer 7 — Voice Persona & Emotional Engine

- **TTS**: CSM (highest conversational quality) + Kokoro (ultra-fast, <50ms) + XTTS v2 (voice cloning) — config-driven priority
- **Persona**: persistent `persona/profile.json`, 5 personality dimensions (curiosity, warmth, directness, humor, formality), evolves via ReflectionAgent at rate 0.01/session
- **Emily's emotional state**: 4-dimensional continuous vector (engagement, confidence, concern, enthusiasm), influences TTS prosody and response style
- **User emotional modeling**: speech tone + facial expression analysis, adapts Emily's communication style

### Layer 8 — Self-Improvement Engine

- Performance tracking: STT error rate, task completion, user satisfaction signals
- Prompt evolution: ReflectionAgent rewrites underperforming system prompt sections, A/B tests variants across sessions, archives old versions in `prompts/archive/`
- RAG feedback: corrections associated with retrieved chunks, poor chunks down-weighted
- Capability gap logging: failed requests logged to `data/capability_gaps.jsonl` for ToolBuilderAgent review
- LoRA pipeline: overnight fine-tuning on conversation transcripts (optional)

### Layer 9 — Security & Privacy

- Zero-egress by default (firewall rules for LAN-only operation)
- Encryption at rest: `age` encryption for all memory databases and logs
- PII scrubber: NER scan before any disk write
- Tamper-evident audit log: append-only, signed entries
- Tool sandboxing: `bubblewrap` container, no network, path allowlist
- Consent gate: `requires_approval=True` tools need explicit confirmation
- Dead man's switch: auto-wipe if device leaves home network for >30 days

### Layer 10 — Interfaces & Deployment

- **Textual TUI**: split-pane — FSM state/agents (left), conversation (center), memory retrieval (right), tool feed (bottom)
- **FastAPI web UI**: WebSocket audio streaming, memory explorer, knowledge base manager, agent dashboard, session playback
- **REST API**: `/api/v1/` — chat, voice, memory CRUD, ingest, tools, metrics, persona
- **Docker Compose**: emily-core, qdrant, searxng, jaeger, prometheus, grafana

---

## Data Flow (Voice Conversation)

```
Microphone
    ↓ (PCM stream)
openWakeWord ("Hey Emily" detected)
    ↓
Silero VAD (speech segment isolated)
    ↓
Faster-Whisper (transcript + confidence)
    ↓ (PerceptionBus: audio.transcript event)
Attention Router (Qwen3-4B classifies complexity)
    ↓ (AgentBus: task to ConversationAgent)
ConversationAgent
    ↓ (AgentBus: retrieve working + episodic memory)
MemoryAgent → Working Memory + Episodic Memory
    ↓ (AgentBus: RAG query if needed)
RAG retriever → Qdrant + BM25 + reranker
    ↓ (prompt assembled in prompt_builder.py)
LLM Fleet (Phi-4 fast or QwQ-32B smart)
    ↓ (ReAct++ loop if tool use needed)
CriticAgent (score < 0.65 → silent retry)
    ↓ (final response text)
TTS Engine (CSM / Kokoro / XTTS v2 — config-driven)
    ↓ (audio stream)
Speaker output (with interruption support)
    ↓ (background)
MemoryAgent → persist episode
```

---

## Directory Structure

See the project root for the full `nova/` layout as specified in the design document.
All modules are importable from Phase 1 forward.
