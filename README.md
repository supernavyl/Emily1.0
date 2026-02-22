# Emily — Cognitive AI Operating System

Emily is a self-evolving, multi-agent, neuromorphic-inspired AI voice OS that runs
entirely on local hardware. She is a persistent cognitive entity that learns, plans,
reasons, and improves herself over time — with zero cloud dependency and zero data egress.

---

## Hardware Requirements

| Component | Minimum | Emily's Machine |
|-----------|---------|-----------------|
| CPU | 8-core | Intel i9-14900K (32 threads) |
| RAM | 32 GB | 64 GB DDR5 |
| GPU | RTX 3080 10GB | RTX 4090 24GB VRAM |
| Storage | 200 GB NVMe | 739 GB free |
| OS | Linux (systemd) | Arch Linux |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        PERCEPTION BUS (ZeroMQ)                   │
│  Audio Pipeline → VAD → STT → WakeWord                          │
│  Vision Pipeline → Screen Capture → Webcam → Presence           │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    MULTI-AGENT COGNITIVE CORE                    │
│  ConversationAgent │ PlannerAgent │ ResearchAgent │ CodeAgent    │
│  MemoryAgent │ ReflectionAgent │ MonitorAgent │ ToolBuilderAgent │
│  CriticAgent (via ReAct++ loop)                                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    LLM FLEET (via Ollama)                        │
│  nano: Qwen3-4B            │ fast: Qwen3-14B Q4_K_M              │
│  smart/reasoning: QwQ-32B Q4_K_M  │ (alt: Qwen3-32B, inactive) │
│  vision: MiniCPM-V 2.6    │ embedding: BGE-M3                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│               PENTAGONAL MEMORY ARCHITECTURE                     │
│  Sensory Buffer │ Working Memory │ Episodic (SQLite)             │
│  Semantic (Qdrant + BM25 + NetworkX) │ Procedural (JSON)        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Install dependencies

```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install
cd ~/Emily1.0
uv sync --extra gpu-cuda --extra dev --extra desktop

# Download spaCy model for PII scrubbing
.venv/bin/python -m spacy download en_core_web_sm
```

### 2. Install Ollama and models

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull required models
ollama pull qwen3:4b             # nano — routing, classification (~3 GB)
ollama pull qwen3:14b            # fast — conversation, code (~10 GB)
ollama pull qwq:latest           # smart/reasoning — complex tasks (~19 GB)
ollama pull minicpm-v:latest     # vision — screenshots, OCR (~5.5 GB)
ollama pull bge-m3               # embedding — RAG retrieval (~1.2 GB)
# Optional: ollama pull qwen3:32b  # alt smart — hybrid thinking (~20 GB, inactive by default)
```

### 3. Start infrastructure services

```bash
docker compose up -d
```

Services started:
- **Qdrant** vector store → http://localhost:6333
- **SearXNG** local search → http://localhost:8888
- **Prometheus** metrics → http://localhost:9090
- **Grafana** dashboards → http://localhost:3000 (admin / `emily_local_only`)
- **Jaeger** tracing → http://localhost:16686

### 4. Configure Emily

```bash
cp .env.example .env
# Edit .env for your setup (Home Assistant token, etc.)
```

### 5. Run Emily

```bash
# Voice mode (primary — full system with all agents)
.venv/bin/python main.py

# Desktop chat app (Qt)
.venv/bin/python -m emily_chat.main

# Web dashboard + API only
.venv/bin/uvicorn api.app:app --host 127.0.0.1 --port 8080

# Terminal UI
.venv/bin/python -m ui.terminal.app
```

---

## Operations Guide

### Model tiers and backends

| Tier | Ollama/Registry model | Backend | Use case |
|------|------------------------|---------|----------|
| nano | qwen3:4b | llamacpp (GGUF) | Routing, classification, <100ms |
| voice_fast | qwen3:4b | llamacpp (alias of nano) | Voice fast path |
| fast | qwen3:14b | ollama | Standard conversation, <2s |
| smart | qwq:latest | ollama | Complex reasoning, planning |
| reasoning | qwq:latest | ollama | Chain-of-thought, math |
| vision | minicpm-v:latest | ollama | Screen + webcam |
| embedding | bge-m3 | ollama | Embeddings |

For nano/voice_fast with llamacpp, place the Qwen3 4B GGUF in `models/` (see `config.yaml` `llm.llamacpp.models.nano.filename`, e.g. `qwen3-4b-instruct-q4_k_m.gguf`).

### Checking System Status

```bash
# Verify Ollama is running and models are loaded
ollama list

# Verify Qdrant is healthy
curl -s http://localhost:6333/healthz

# Check Emily API (if web dashboard is running)
curl -s http://localhost:8080/health

# GPU status
nvidia-smi
```

### VRAM Co-residency

With the RTX 4090 (24 GB), models are loaded on demand:

| Model | VRAM | Residency |
|-------|------|-----------|
| qwen3:4b (nano) | ~3 GB | Always resident |
| bge-m3 (embedding) | ~1.2 GB | Always resident |
| Whisper large-v3-turbo (STT) | ~1.5 GB | Always resident |
| qwen3:14b (fast) | ~10 GB | Loaded for conversations |
| qwq (smart) | ~19 GB | Loaded for hard tasks, evicts fast |
| qwen3:32b (alt smart) | ~20 GB | Inactive by default, swap in via config |
| minicpm-v (vision) | ~5.5 GB | Loaded on demand |

Ollama handles model swapping automatically. With 64 GB RAM, offloading to
CPU RAM is seamless when VRAM is full.

### Updating Models

```bash
# Pull newer versions (Ollama checks for updates)
ollama pull qwen3:4b
ollama pull qwen3:14b
ollama pull qwq:latest
ollama pull minicpm-v:latest
ollama pull bge-m3

# After changing the embedding model, re-embed Qdrant collections:
.venv/bin/python scripts/migrations/migrate_embeddings.py \
    --new-model bge-m3 --new-dim 1024 --dry-run
# Remove --dry-run to execute
```

### Updating Emily Code

```bash
cd ~/Emily1.0

# Update dependencies
uv sync --extra gpu-cuda --extra dev --extra desktop

# Run tests to verify nothing is broken
.venv/bin/pytest tests/unit/ -v

# Check for lint issues
.venv/bin/ruff check .
```

### Running Tests

```bash
# All unit tests
.venv/bin/pytest tests/unit/ -v

# Specific test file
.venv/bin/pytest tests/unit/test_pii_scrubber.py -v

# With coverage
.venv/bin/pytest tests/unit/ --cov --cov-report=term-missing

# Benchmarks (requires Ollama running)
.venv/bin/pytest tests/benchmarks/ -v -s -m benchmark
```

### Troubleshooting

| Problem | Solution |
|---------|----------|
| `ollama list` shows no models | Run the `ollama pull` commands above |
| Qdrant connection refused | `docker start emily-qdrant` or re-run `docker compose up -d` |
| STT not working | Check `nvidia-smi` — Whisper needs ~1.5 GB free VRAM |
| Slow LLM responses | QwQ (19 GB) may be loading from disk; wait ~5s for first response |
| "No module named X" | Run `uv sync --extra gpu-cuda --extra dev --extra desktop` |
| PII scrubber regex-only | Run `.venv/bin/python -m spacy download en_core_web_sm` |
| Permission denied on audio | Add user to `audio` group: `sudo usermod -aG audio $USER` |

### Key Config Files

| File | Purpose |
|------|---------|
| `config.yaml` | All runtime settings (models, latency, memory, RAG, etc.) |
| `.env` | Secrets (API keys, tokens) — never committed |
| `persona/profile.json` | Emily's personality traits (evolves over time) |
| `data/procedural.json` | User model + Emily's self-model |
| `prompts/` | Overridable prompt templates |

---

## Project Structure

```
Emily1.0/
├── main.py                     # CLI entry point
├── config.py                   # Pydantic settings (loaded from config.yaml)
├── config.yaml                 # All runtime configuration
├── pyproject.toml              # Dependencies (uv + hatchling)
├── docker-compose.yml          # Infrastructure services
│
├── core/
│   ├── bootstrap.py            # Root composition + startup/shutdown
│   ├── bus.py                  # PerceptionBus + AgentBus (ZeroMQ)
│   ├── fsm.py                  # System FSM (IDLE → LISTENING → etc.)
│   └── scheduler.py            # Priority queue task scheduler
│
├── perception/
│   ├── audio/
│   │   ├── pipeline.py         # Audio orchestrator
│   │   ├── stream.py           # Microphone capture (sounddevice)
│   │   ├── vad.py              # Silero VAD + adaptive threshold
│   │   ├── stt.py              # Faster-Whisper large-v3 (CUDA)
│   │   └── wake_word.py        # openWakeWord "Hey Emily"
│   ├── vision/
│   │   ├── pipeline.py         # Vision orchestrator
│   │   ├── screen_capture.py   # mss periodic screenshot
│   │   ├── webcam.py           # OpenCV webcam + DeepFace emotions
│   │   ├── presence.py         # User presence detection
│   │   └── vision_llm.py       # MiniCPM-V scene analysis
│   └── fusion.py               # Multi-modal event router
│
├── llm/
│   ├── client.py               # Async Ollama REST client
│   ├── router.py               # Model tier selection
│   ├── fleet.py                # Unified LLM interface
│   ├── prompt_builder.py       # Centralized prompt assembly
│   ├── react_loop.py           # ReAct++ (THOUGHT→PLAN→ACT→OBSERVE→CRITIQUE→REVISE)
│   ├── critic_loop.py          # CriticAgent quality scoring + retry
│   ├── streaming.py            # Token stream → sentence splitter
│   └── structured_output.py   # JSON extraction from LLM responses
│
├── memory/
│   ├── manager.py              # Unified memory interface
│   ├── sensory_buffer.py       # Ring buffer (raw events)
│   ├── working.py              # Active context (token-budgeted)
│   ├── episodic.py             # Session summaries (SQLite)
│   ├── procedural.py           # User/self model (JSON)
│   └── semantic/
│       ├── vector_store.py     # Qdrant dense vector store
│       ├── bm25.py             # BM25 sparse retrieval
│       ├── retriever.py        # Hybrid retrieval (RRF fusion)
│       ├── graph_store.py      # NetworkX knowledge graph
│       └── reranker.py         # CrossEncoder reranker
│
├── rag/
│   ├── ingestor.py             # Document ingestion pipeline
│   ├── chunker.py              # Semantic chunking (parent + child)
│   ├── watcher.py              # watchdog file system monitor
│   └── parsers/                # PDF, DOCX, code, audio, video, EPUB
│
├── agents/
│   ├── base.py                 # BaseAgent with heartbeat + bus access
│   ├── conversation.py         # Real-time dialogue handler
│   ├── planner.py              # Task decomposition + delegation
│   ├── memory_agent.py         # Cross-tier memory search + consolidation
│   ├── reflection.py           # Idle-time insight generation
│   ├── research.py             # RAG + web search synthesis
│   ├── code_agent.py           # Code generation + sandboxed execution
│   ├── monitor.py              # System resource monitoring
│   ├── tool_builder.py         # Dynamic tool generation (with approval)
│   └── registry.py             # Agent lifecycle management
│
├── plugins/
│   ├── base.py                 # BaseTool abstract class
│   ├── sandbox.py              # bubblewrap sandboxing
│   ├── registry.py             # Tool discovery + registration
│   └── builtin/                # 14 built-in tools
│       ├── calculator.py, code_executor.py, file_ops.py
│       ├── web_search.py, web_fetch.py, shell.py, git_tool.py
│       ├── notification.py, home_assistant.py, calendar.py
│       ├── image_analyzer.py, process_manager.py, email_reader.py
│       └── singing.py          # Music generation + singing voice conversion
│
├── voice/
│   ├── tts.py                  # XTTS v2 + Kokoro TTS manager
│   ├── singing.py              # MusicGen + RVC + Suno singing engine
│   ├── prosody.py              # Emotion-aware prosody control
│   ├── output_stream.py        # Audio playback + interrupt
│   └── voice_clone.py          # Voice cloning (stub)
│
├── persona/
│   ├── emotional_state.py      # 4D emotional state (EMA-smoothed)
│   ├── profile.py              # 5D personality trait vector (evolving)
│   └── user_model.py           # User mood inference + adaptation
│
├── security/
│   ├── manager.py              # Root security object
│   ├── encryption.py           # age encryption at rest
│   ├── pii_scrubber.py         # spaCy NER + regex PII redaction
│   ├── audit_log.py            # SHA-256 hash-chained audit log
│   ├── consent.py              # Interactive consent gate
│   └── dead_man_switch.py      # Auto-wipe after N days inactivity
│
├── self_improvement/
│   ├── engine.py               # Self-improvement coordinator
│   ├── performance_tracker.py  # JSONL performance metrics log
│   ├── prompt_evolver.py       # A/B prompt testing (epsilon-greedy)
│   ├── rag_feedback.py         # Retrieval quality feedback loop
│   └── capability_gap_logger.py # Gap detection + resolution tracking
│
├── observability/
│   ├── logger.py               # structlog JSON + colored console
│   ├── metrics.py              # Prometheus metrics definitions
│   └── tracing.py              # OpenTelemetry + Jaeger
│
├── api/
│   └── app.py                  # FastAPI + WebSocket + HTMX web UI
│
├── ui/
│   └── terminal/
│       └── app.py              # Textual TUI
│
├── tests/
│   ├── unit/                   # pytest unit tests
│   └── benchmarks/             # LLM + RAG benchmark suite
│
└── scripts/
    ├── prometheus.yml           # Prometheus scrape config
    ├── searxng_settings.yml     # SearXNG engine config
    └── grafana_provisioning/    # Grafana datasource provisioning
```

---

## Cognitive Model

Emily uses a **ReAct++ loop** for non-trivial tasks:

```
THOUGHT → PLAN → ACTION → OBSERVATION → CRITIQUE → REVISE → RESPOND
```

The **CriticAgent** scores every response (accuracy, completeness, safety, helpfulness)
and silently retries if the score falls below the configured threshold.

### Memory Architecture

| Layer | Technology | TTL |
|-------|-----------|-----|
| Sensory Buffer | In-memory deque | 30s |
| Working Memory | In-memory (token-budgeted) | Session |
| Episodic Memory | SQLite | Permanent |
| Semantic Memory | Qdrant + BM25 + NetworkX | Permanent |
| Procedural Memory | JSON file | Permanent |

---

## Security

See [THREAT_MODEL.md](THREAT_MODEL.md) for a full analysis. Summary:

- **Zero egress**: No data leaves the machine (all models and services run locally)
- **API auth**: Set `EMILY_API_SECRET` in `.env` (or environment); all API endpoints require Bearer token when set. Rate limiting and configurable CORS are enabled.
- **Encryption at rest**: `age` (X25519) encrypts sensitive data files; when enabled, no plaintext fallback (pyrage or age CLI required)
- **PII scrubbing**: spaCy NER + regex redacts personal data from logs/memory
- **Audit log**: SHA-256 hash-chained JSONL; optional retention via `security.audit_retention_days`
- **Consent gate**: Interactive approval required for privileged tool execution
- **Sandbox**: bubblewrap isolates code execution; Python builtins restricted in code executor
- **Dead man's switch**: Auto-wipes data after configurable inactivity; heartbeat path is configurable

**Dependency scanning**: Run `pip-audit` (or `uv pip audit` if using uv) periodically or in CI to check for known vulnerabilities.

---

## Self-Improvement

Emily improves herself during idle time:

1. **Performance tracking**: Latency, quality, and retrieval scores are logged
2. **Prompt evolution**: A/B tests prompt variants with epsilon-greedy selection
3. **RAG feedback**: Low-quality documents are flagged for re-ingestion
4. **Capability gaps**: Missing skills are logged and surfaced to ToolBuilderAgent
5. **Reflection**: ReflectionAgent generates insights from recent episodes

---

## Development

```bash
# Run tests
.venv/bin/pytest tests/unit/ -v

# Run benchmarks (requires Ollama running)
.venv/bin/pytest tests/benchmarks/ -v -s -m benchmark

# Check linting
.venv/bin/ruff check .
.venv/bin/mypy . --ignore-missing-imports

# Format
.venv/bin/ruff format .

# Dependency audit (security)
pip install pip-audit && pip-audit
# Or with uv: uv pip audit
```

---

## Configuration

All configuration lives in `config.yaml`. Override any value with environment variables
using the prefix `EMILY_` (e.g., `EMILY_LOG_LEVEL=DEBUG`).

See `.env.example` for all available overrides.

---

## License

Private use only. Emily is a personal AI system — not for redistribution.
