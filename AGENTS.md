# AGENTS.md — Emily Architecture & AI Agent Context

> This file provides background context for AI agents, background models, and coding assistants
> working in this repository. Keep it up to date as the architecture evolves.

---

## Project Overview

**Emily** is a self-evolving, multi-agent local AI voice operating system. She is not an assistant — she is a persistent cognitive entity that learns, plans, reasons, and improves herself over time, running entirely on local hardware (Intel i9-14900K, 64 GB DDR5, NVIDIA RTX 4090, Arch Linux).

Emily is **Python-only** — no React, no Node frontend. She uses PySide6 for a desktop chat app, Textual for terminal dashboards, and FastAPI for a web API.

---

## Repository Layout

```
Emily1.0/
├── agents/                # Multi-agent cognitive core
│   ├── base.py            #   BaseAgent — all agents inherit from this
│   ├── registry.py        #   Agent registration and discovery
│   ├── conversation.py    #   ConversationAgent — real-time dialogue
│   ├── planner.py         #   PlannerAgent — task decomposition, delegation
│   ├── memory_agent.py    #   MemoryAgent — memory tier reads/writes
│   ├── reflection.py      #   ReflectionAgent — idle-time insights, self-model updates
│   ├── research.py        #   ResearchAgent — deep-dive RAG + reasoning
│   ├── code_agent.py      #   CodeAgent — sandboxed code writing/debugging
│   ├── monitor.py         #   MonitorAgent — system resource monitoring
│   ├── tool_builder.py    #   ToolBuilderAgent — runtime tool creation
│   └── onboarding.py      #   OnboardingAgent — first-run user setup
│
├── api/                   # FastAPI HTTP/WebSocket layer
│   ├── app.py             #   FastAPI application factory
│   ├── auth.py            #   Authentication middleware
│   └── routes/            #   Route modules (audio, graph, people, query, vault, voice_engine)
│
├── core/                  # Central runtime and coordination
│   ├── bootstrap.py       #   System startup orchestration
│   ├── brain_hub.py       #   Central cognitive coordinator
│   ├── bus.py             #   AgentBus — inter-agent messaging (JSON envelopes)
│   ├── fsm.py             #   Finite state machine (system-wide state)
│   └── scheduler.py       #   Priority queue scheduler (P0-P4 tiers)
│
├── llm/                   # LLM orchestration engine
│   ├── fleet.py           #   LLMFleet — multi-model management (nano/fast/smart/vision/embedding)
│   ├── router.py          #   Intelligent model router (complexity scoring → tier selection)
│   ├── prompt_builder.py  #   ALL prompts live here — the single source of truth
│   ├── react_loop.py      #   ReAct++ loop (THOUGHT→PLAN→ACTION→OBSERVATION→CRITIQUE→REVISE→RESPOND)
│   ├── critic_loop.py     #   CriticAgent scoring (accuracy, completeness, safety, helpfulness)
│   ├── streaming.py       #   Token streaming infrastructure
│   ├── structured_output.py # JSON-schema-constrained generation
│   ├── client.py          #   Ollama HTTP client
│   ├── llamacpp_client.py #   llama-cpp-python in-process client (nano/voice_fast tiers)
│   ├── orchestrator.py    #   High-level LLM task orchestration
│   ├── speculative.py     #   Speculative decoding experiments
│   └── recency_detector.py #  Temporal relevance detection
│
├── memory/                # 5-tier pentagonal memory architecture
│   ├── manager.py         #   MemoryManager — unified memory access layer
│   ├── sensory_buffer.py  #   Tier 1: RAM ring buffer (ms-s)
│   ├── working.py         #   Tier 2: Priority queue with token-budget trimming (s-min)
│   ├── episodic.py        #   Tier 3: SQLite + Qdrant embeddings (min-years)
│   ├── knowledge_store.py #   Tier 4: Qdrant + networkx knowledge graph (permanent)
│   ├── procedural.py      #   Tier 5: JSON + Qdrant for skills/self-model (permanent)
│   ├── query_engine.py    #   Cross-tier memory query interface
│   ├── knowledge_models.py #  Pydantic models for knowledge entities
│   └── semantic/          #   Hybrid retrieval subsystem
│       ├── vector_store.py #    Qdrant dense vector operations
│       ├── bm25.py         #    BM25 sparse search
│       ├── reranker.py     #    BGE-reranker-v2-m3 cross-encoder
│       ├── retriever.py    #    HybridRetriever (BM25 + dense + rerank + graph expansion)
│       ├── graph_store.py  #    networkx knowledge graph
│       └── knowledge_vectors.py # Embedding pipeline
│
├── perception/            # Sensory input bus
│   ├── fusion.py          #   Multi-modal perception fusion
│   ├── audio/             #   Audio pipeline
│   │   ├── wake_word.py   #     openWakeWord ("Hey Emily") — custom ONNX model
│   │   ├── vad.py         #     Silero VAD v5 with adaptive noise floor
│   │   ├── stt.py         #     Faster-Whisper large-v3-turbo (CUDA, float16)
│   │   ├── streaming_stt.py #   Real-time streaming STT
│   │   ├── capture.py     #     Audio device capture
│   │   ├── stream.py      #     Audio stream management
│   │   ├── pipeline.py    #     Full audio processing pipeline
│   │   ├── aec.py         #     Acoustic echo cancellation
│   │   ├── noise_suppress.py #  Noise suppression
│   │   ├── emotion_detector.py # Speech emotion analysis
│   │   ├── prosody_analyzer.py # Prosody feature extraction
│   │   └── speaker_engine.py #  Speaker identification
│   ├── vision/            #   Vision pipeline
│   │   ├── screen_capture.py #  mss screenshot capture
│   │   ├── webcam.py      #     OpenCV webcam feed
│   │   ├── vision_llm.py  #     MiniCPM-V 2.6 scene/emotion understanding
│   │   ├── presence.py    #     User presence detection
│   │   └── pipeline.py    #     Vision processing pipeline
│   └── system/            #   System telemetry (psutil)
│
├── plugins/               # Tool & plugin ecosystem
│   ├── base.py            #   BaseTool — all tools inherit from this
│   ├── registry.py        #   Tool discovery and registration
│   ├── sandbox.py         #   bubblewrap sandboxing (no network, path allowlist)
│   ├── builtin/           #   Built-in tools (calculator, code_executor, file_ops, git_tool,
│   │                      #     home_assistant, image_analyzer, notification, process_manager,
│   │                      #     shell, web_fetch, web_search, calendar, email_reader, singing)
│   └── generated/         #   Runtime-generated tools (require explicit user approval to load)
│
├── voice/                 # Voice persona & output engine
│   ├── tts.py             #   TTS engine manager (CSM → Kokoro → XTTS v2 → Edge TTS)
│   ├── prosody.py         #   Prosody parameter computation
│   ├── prosody_planner.py #   Prosody planning from emotional state
│   ├── voice_clone.py     #   XTTS v2 voice cloning
│   ├── breath_injector.py #   Natural breath insertion
│   ├── filler_engine.py   #   Filler word engine ("um", "hmm")
│   ├── output_stream.py   #   Audio output streaming with interruption support
│   └── singing.py         #   Singing synthesis engine
│
├── conversation/          # Real-time conversation engine
│   ├── voice_engine.py    #   Full duplex voice conversation coordinator
│   ├── turn_detector.py   #   Turn-taking detection
│   ├── interrupt_handler.py #  Interruption handling
│   ├── backchannel.py     #   Backchannel responses ("mhm", "right")
│   ├── rhythm_sync.py     #   Conversational rhythm synchronization
│   ├── emotion_sync.py    #   Emotional state synchronization
│   └── fsm.py             #   Conversation state machine
│
├── persona/               # Personality & emotional modeling
│   ├── profile.py         #   5-dimension personality (curiosity, warmth, directness, humor, formality)
│   ├── emotional_state.py #   4-dimension emotional state (engagement, confidence, concern, enthusiasm)
│   └── user_model.py      #   User emotional modeling and adaptation
│
├── self_improvement/      # Self-improvement engine
│   ├── engine.py          #   Self-improvement coordinator
│   ├── prompt_evolver.py  #   Prompt A/B testing and evolution
│   ├── performance_tracker.py # Session performance scoring
│   ├── capability_gap_logger.py # Failed request logging for ToolBuilderAgent
│   └── rag_feedback.py    #   RAG quality feedback loop
│
├── security/              # Security & privacy layer
│   ├── manager.py         #   Security manager (coordinates all security subsystems)
│   ├── encryption.py      #   age encryption at rest
│   ├── pii_scrubber.py    #   NER-based PII detection before disk writes
│   ├── audit_log.py       #   Append-only tamper-evident audit log
│   ├── consent.py         #   User consent gate for tool approval
│   ├── dead_man_switch.py #   Auto-wipe if device leaves home network >30 days
│   └── vault/             #   Secrets vault (crypto, TOTP, health checks)
│
├── rag/                   # RAG ingestion & chunking pipeline
│   ├── ingestor.py        #   Document ingestion coordinator
│   ├── chunker.py         #   Parent/child chunking (256/2048 tokens, semantic boundaries)
│   ├── watcher.py         #   watchdog file system monitor for knowledge/
│   └── parsers/           #   Format parsers (pdf, docx, epub, text, code, audio, video)
│
├── ingestion/             # Structured data ingestion
│   ├── coordinator.py     #   Ingestion coordinator
│   └── parsers/           #   vCard, iCal, conversation, PDF parsers
│
├── extraction/            # Entity/relation extraction pipeline
│   ├── pipeline.py        #   Extraction pipeline coordinator
│   ├── entity_extractor.py #  Named entity extraction
│   ├── relation_extractor.py # Relationship extraction
│   └── deduplicator.py    #   Entity deduplication
│
├── observability/         # Logging, metrics, tracing
│   ├── logger.py          #   structlog JSON logging
│   ├── metrics.py         #   prometheus-client metrics
│   ├── tracing.py         #   OpenTelemetry → Jaeger
│   └── brain_tap.py       #   Real-time brain state inspection
│
├── timing/                # Latency budget enforcement
│   ├── latency_budget.py  #   Per-tier latency budgets
│   └── metrics.py         #   Timing metrics collection
│
├── emily_chat/            # PySide6 desktop chat application
│   ├── main.py            #   Entry point
│   ├── app.py             #   QApplication setup
│   ├── controller.py      #   UI controller (business logic)
│   ├── config.py          #   Desktop app settings
│   ├── profiles.py        #   Chat profile management
│   ├── emily/             #   Emily identity (persona, skills, response filters)
│   ├── models/            #   LLM provider layer (ollama, anthropic, openai, groq, deepseek,
│   │                      #     google, mistral, openrouter, together, xai, llamacpp)
│   │   ├── auto_router.py #     Automatic provider selection
│   │   ├── cost_tracker.py #    Per-provider cost tracking
│   │   └── streaming_engine.py # Streaming response engine
│   ├── storage/           #   SQLite conversation storage + migrations
│   ├── export/            #   Conversation export engine
│   ├── ui/                #   Qt widgets (main_window, input_panel, conversation_stream,
│   │                      #     left_sidebar, right_panel, markdown_renderer, code_block_widget,
│   │                      #     custom_titlebar, search_overlay, skill_editor, theme_engine, etc.)
│   └── assets/            #   Fonts (Inter, JetBrains Mono), icons, QSS themes (dark/light)
│
├── ui/                    # Textual TUI dashboards
│   ├── brain/dashboard.py #   Brain state dashboard (FSM, agents, memory)
│   ├── voice/dashboard.py #   Voice pipeline dashboard (audio, TTS)
│   ├── terminal/app.py    #   Interactive conversation terminal
│   └── web/               #   Web UI stubs
│
├── tests/                 # Test suite
│   ├── unit/              #   Unit tests (mirrors source structure, 50+ test files)
│   ├── integration/       #   Integration tests
│   ├── e2e/               #   End-to-end tests
│   └── benchmarks/        #   Performance benchmarks (LLM latency, RAG throughput)
│
├── scripts/               # Infrastructure and migration scripts
│   ├── migrations/        #   Memory schema migrations (NNN_description.py)
│   ├── prometheus.yml     #   Prometheus scrape config
│   ├── searxng_settings.yml # SearXNG engine config
│   └── grafana_provisioning/ # Auto-provisioned dashboards and datasources
│
├── prompts/archive/       # Archived prompt versions (self-improvement audit trail)
├── knowledge/             # Drop folder for auto-ingestion (watchdog monitors this)
├── data/                  # Runtime data (episodes.db, knowledge.db, vault.db, qdrant_storage/)
├── models/                # Local model files (.gguf) and HuggingFace cache
├── logs/                  # Runtime logs (emily.log, audit.log, vault_audit.log)
├── users/profiles/        # User profile data
├── proactive/engine.py    # Proactive engagement engine
│
├── config.yaml            # System configuration (model fleet, latency budgets, memory settings)
├── config.py              # Pydantic Settings v2 config loader
├── main.py                # System entry point
├── pyproject.toml         # uv/hatchling project definition
├── docker-compose.yml     # Supporting services (Qdrant, SearXNG, Prometheus, Grafana, Jaeger)
├── .cursorrules           # Workspace-level AI agent rules (15 rules)
└── .cursor/rules/         # File-pattern-specific AI rules (.mdc files)
```

---

## Key Architectural Decisions

### System Architecture
- **Nature**: Multi-agent cognitive AI voice OS — not a chatbot, not an assistant
- **Runtime**: Bare-metal Python on Arch Linux for GPU access; Docker Compose for supporting services only
- **Package Manager**: uv + hatchling (not pip, not conda)
- **Config**: Pydantic Settings v2 + YAML (`config.yaml`)
- **Message Bus**: ZeroMQ (pyzmq async) for inter-agent and perception event routing

### LLM Fleet (local models, Ollama + llama-cpp-python)
- **nano** (Qwen3-4B, ~3 GB, always in VRAM): routing, classification, <100ms
- **fast** (Qwen3-14B Q4_K_M, ~10 GB): conversation, <2s
- **smart/reasoning** (QwQ-32B Q4_K_M, ~20 GB): complex reasoning, <15s
- **vision** (MiniCPM-V 2.6, ~8 GB): screen + webcam understanding
- **embedding** (BGE-M3, ~2 GB): all embedding tasks (dense + sparse + multi-vector)
- Model router (`llm/router.py`) selects tier based on complexity score and VRAM headroom

### Agent System
- All agents inherit from `BaseAgent` (`agents/base.py`)
- Agents register in `agents/registry.py` — always verify registration after implementing
- 4 primary agents (always running): ConversationAgent, PlannerAgent, MemoryAgent, ReflectionAgent
- 6+ on-demand agents (spawned as needed): ResearchAgent, CodeAgent, ToolBuilderAgent, MonitorAgent, etc.
- Inter-agent communication via `AgentBus` (`core/bus.py`) with structured JSON envelopes

### Memory System (5-tier pentagonal)
1. Sensory Buffer (RAM ring buffer, ms-s)
2. Working Memory (priority queue + token-budget trimming, s-min)
3. Episodic Memory (SQLite + Qdrant, min-years)
4. Semantic Memory (Qdrant + networkx knowledge graph, permanent)
5. Procedural + Identity Memory (JSON + Qdrant, permanent)
- All access through `MemoryManager` (`memory/manager.py`)
- Schema changes require migration scripts in `scripts/migrations/`

### Tool System
- All tools inherit from `BaseTool` (`plugins/base.py`)
- Every tool must implement `execute()` and `dry_run()` (mandatory)
- Sandboxed via `bubblewrap` — no network, path allowlist
- Generated tools (`plugins/generated/`) require explicit user approval before loading

### Voice Pipeline
- STT: Faster-Whisper large-v3-turbo (CUDA, float16) — <300ms budget
- TTS: CSM (quality) → Kokoro (speed) → XTTS v2 (cloning) → Edge TTS (fallback)
- Wake word: openWakeWord with custom ONNX model
- VAD: Silero VAD v5 with adaptive noise floor
- Real-time conversation engine with turn-taking, interruption, backchannel

### Prompt System
- ALL prompts assembled in `llm/prompt_builder.py` — the single source of truth
- Inline prompt strings anywhere else are bugs
- Old versions archived in `prompts/archive/` when self-improvement modifies them

### Security
- Zero-egress by default (LAN-only)
- Encryption at rest (age)
- PII scrubbing before disk writes (NER scan)
- Tool sandboxing (bubblewrap)
- Tamper-evident audit log
- Changes to `security/` require explicit user approval

### Observability
- structlog for structured JSON logging
- prometheus-client for metrics (exported on :8000/metrics)
- OpenTelemetry → Jaeger for distributed tracing

---

## What NOT to Do

- Don't put prompt strings outside `llm/prompt_builder.py`
- Don't do blocking I/O inside async functions — use `asyncio.to_thread`
- Don't auto-load generated tools from `plugins/generated/` — require user approval
- Don't skip `dry_run()` when implementing a new tool
- Don't change memory schemas without a migration script in `scripts/migrations/`
- Don't modify `security/` modules without explicit user approval
- Don't refer to Emily as "NOVA", "assistant", "bot", or "chatbot"
- Don't add dependencies without checking if an existing one covers the need
- Don't commit `.env`, secrets, model weights, or `data/` directory contents
- Don't write functions without type hints, docstrings, and at least one unit test

---

## Infrastructure Services (Docker Compose)

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| qdrant | `qdrant/qdrant:v1.9.2` | 6333, 6334 | Vector database (semantic memory + RAG) |
| searxng | `searxng/searxng:latest` | 8888 | Private metasearch engine |
| prometheus | `prom/prometheus:v2.52.0` | 9090 | Metrics collection |
| grafana | `grafana/grafana:11.1.0` | 3000 | Dashboards and alerting |
| jaeger | `jaegertracing/all-in-one:1.57` | 16686, 4317, 4318 | Distributed tracing |

Emily herself runs bare-metal (not in Docker) for direct GPU access.

---

## Latency Budgets

| Stage | Target |
|-------|--------|
| Wake word detection | <50ms |
| VAD (speech segment isolation) | <1ms per chunk |
| STT (Faster-Whisper) | <300ms |
| LLM first token (fast model) | <1s |
| LLM first token (nano model) | <100ms |
| TTS first audio byte | <200ms |
| End-to-end voice response | <2s |

---

## Testing Conventions

- Framework: pytest + pytest-asyncio (auto mode)
- Tests live in `tests/unit/` mirroring source structure
- HTTP mocking: `respx`
- Time control: `time-machine`
- Mark slow tests with `@pytest.mark.integration`
- Every function needs at least one unit test

---

## Key Files for Context

| File | What It Contains |
|------|-----------------|
| `ARCHITECTURE.md` | Full 10-layer system architecture |
| `COGNITIVE_MODEL.md` | How Emily thinks, remembers, and improves |
| `DECISIONS.md` | Every technology choice with rationale and rejected alternatives |
| `config.yaml` | Runtime configuration for all subsystems |
| `.cursorrules` | 15 workspace-level rules for AI agents |
| `MEMORY_LOG.md` | Append-only log of every significant change |
