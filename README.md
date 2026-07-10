# Emily — Cognitive AI Operating System

> [!NOTE]
> **Archived prototype (frozen April 2026).** Emily was built and run locally through
> early 2026, then frozen; its successor projects continued elsewhere. Published as a
> reference architecture for a fully local voice-first assistant — not maintained,
> issues won't be triaged. Everything documented below reflects the state at freeze.


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
│                    LLM FLEET (TabbyAPI + Ollama)                 │
│  Text Generation (TabbyAPI :5000, ExLlamaV2, abliterated):      │
│    nano/voice_fast/fast: Qwen2.5-14B-Instruct (4.65bpw EXL2)     │
│    smart/reasoning: QwQ-32B (4.0bpw EXL2)                       │
│  Vision+Embedding (Ollama :11434):                              │
│    vision: MiniCPM-V 2.6  │  embedding: BGE-M3                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│               PENTAGONAL MEMORY ARCHITECTURE                     │
│  Sensory Buffer │ Working Memory │ Episodic (SQLite)             │
│  Semantic (Qdrant + BM25 + NetworkX) │ Procedural (JSON)        │
└─────────────────────────────────────────────────────────────────┘
```

**Key change**: All text generation now runs on **TabbyAPI** (ExLlamaV2-based inference server) with fully **abliterated** models for uncensored reasoning. Vision and embedding remain on Ollama.

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

### 2. Install LLM backends

#### TabbyAPI (text generation — abliterated models)

```bash
# Install TabbyAPI ExLlamaV2 inference server
cd ~/
git clone https://github.com/therealownage/TabbyAPI.git
cd TabbyAPI
python3.11 -m venv venv
source venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt

# Configure
cp config_sample.yml config.yml
# Edit config.yml → set model_dir, disable auth for local-only use

# Download abliterated EXL2 models
mkdir -p ~/models/tabby
cd ~/models/tabby

# Qwen2.5-14B-Instruct-abliterated (4.65bpw EXL2, ~8.5 GB VRAM)
huggingface-cli download bartowski/Qwen2.5-14B-Instruct-abliterated-exl2 \
  --revision 4.65bpw \
  --local-dir Qwen2.5-14B-Instruct-abliterated \
  --local-dir-use-symlinks False

# QwQ-32B-abliterated (4.0bpw EXL2, ~17 GB VRAM)
huggingface-cli download huihui-ai/QwQ-32B-abliterated-exl2 \
  --revision 4.0bpw \
  --local-dir QwQ-32B-abliterated \
  --local-dir-use-symlinks False

# Start TabbyAPI (will auto-start via scripts/start-emily.sh)
cd ~/TabbyAPI
source venv/bin/activate
python main.py --model Qwen2.5-14B-Instruct-abliterated
```

**Full setup guide**: [docs/TABBYAPI_SETUP.md](docs/TABBYAPI_SETUP.md)

#### Ollama (vision + embedding)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull vision and embedding models (text models now on TabbyAPI)
ollama pull minicpm-v:latest     # vision — screenshots, OCR (~5.5 GB)
ollama pull bge-m3               # embedding — RAG retrieval (~1.2 GB)
```

### 3. Start infrastructure + model backends

```bash
cd ~/Emily1.0
source .venv/bin/activate

# Starts Docker infra + TabbyAPI + Ollama checks
./scripts/start-emily.sh infra
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
# Full stack (infra + model backends + API + core)
./scripts/start-emily.sh all

# Voice core only (no GUI)
./scripts/start-emily.sh core

# Voice core with Brain + Voice dashboards
./scripts/start-emily.sh dashboards

# Desktop chat app (Qt)
./scripts/start-emily.sh chat

# API only
./scripts/start-emily.sh api

# React web frontend only
./scripts/start-emily.sh web

# Status / shutdown
./scripts/start-emily.sh status
./scripts/start-emily.sh stop
```

### 6. Optional: Enable Vision (Camera + Screen Access)

Emily's vision system provides screen capture and webcam capabilities for visual context awareness.

**Quick setup:**

```bash
# Run automated setup (checks dependencies, permissions, tests)
./scripts/setup-vision.sh

# Test vision system
python scripts/test-vision.py

# Vision is already enabled in config.yaml
# If you need to disable: set vision.enabled = false
```

**What vision enables:**
- 📹 **Webcam**: Presence detection and facial expression analysis
- 🖥️ **Screen capture**: Screenshot understanding via MiniCPM-V
- 💬 **Ask Emily**: "What's on my screen?" or "Can you see me?"

**Full guide**: [docs/VISION_SETUP.md](docs/VISION_SETUP.md)

---

## Operations Guide

### Model tiers and backends

| Tier | Model | Backend | VRAM | Use case |
|------|-------|---------|------|----------|
| nano | Qwen2.5-14B-Instruct-abliterated | TabbyAPI (EXL2) | ~8.5 GB | Routing, classification, <1s |
| voice_fast | Qwen2.5-14B-Instruct-abliterated | TabbyAPI (EXL2) | ~8.5 GB | Voice fast path, <500ms |
| fast | Qwen2.5-14B-Instruct-abliterated | TabbyAPI (EXL2) | ~8.5 GB | Standard conversation, <2s |
| smart | QwQ-32B-abliterated | TabbyAPI (EXL2) | ~17 GB | Complex reasoning, planning, <15s |
| reasoning | QwQ-32B-abliterated | TabbyAPI (EXL2) | ~17 GB | Chain-of-thought, math |
| vision | minicpm-v:latest | Ollama | ~8 GB | Screen + webcam understanding |
| embedding | bge-m3 | Ollama | ~2 GB | Dense + sparse embeddings |

**Backend routing** (configured in `config.yaml` → `llm.tier_backend`):
- Text generation tiers → TabbyAPI (:5000) with abliterated EXL2 models
- Vision + embedding → Ollama (:11434)

**Why abliterated models?**
No refusals, no alignment tax, native `<think>...</think>` reasoning blocks for transparent CoT.

**Multilingual support:**
Emily's Qwen3 text models support **119 languages** natively, and Whisper STT handles **99 languages**. See [MODELS_AND_LANGUAGES.md](MODELS_AND_LANGUAGES.md) for full language details.

### Checking System Status

```bash
# Verify TabbyAPI is running and model is loaded
curl -s http://localhost:5000/v1/models | jq

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

With the RTX 4090 (24 GB), TabbyAPI + Ollama split the workload:

| Model | Backend | VRAM | Residency |
|-------|---------|------|-----------|
| Qwen2.5-14B-Instruct-abliterated | TabbyAPI | ~8.5 GB | Default (fast tier, 80%+ of queries) |
| QwQ-32B-abliterated | TabbyAPI | ~17 GB | Hot-swap for smart/reasoning tier |
| MiniCPM-V 2.6 | Ollama | ~8 GB | Loaded on-demand for vision |
| BGE-M3 | Ollama | ~2 GB | Always resident (embedding) |
| Whisper large-v3-turbo | Pipeline | ~1.5 GB | Always resident (STT) |

**Typical VRAM usage:**
- Qwen2.5-14B (fast tier) + BGE-M3 + Whisper: **~12 GB** (plenty of headroom)
- QwQ-32B (smart tier) + BGE-M3 + Whisper: **~20.5 GB** (near max, auto-evicts fast tier)

TabbyAPI supports hot model swapping via `POST /v1/model/load`. Emily's router auto-selects the right tier; you can manually load QwQ-32B before a reasoning session:

```bash
curl -X POST http://localhost:5000/v1/model/load \
  -H "Content-Type: application/json" \
  -d '{"name": "QwQ-32B-abliterated"}'
```

With 64 GB system RAM, offloading to CPU is seamless when VRAM is full.

### Updating Models

```bash
# TabbyAPI models: re-download from HuggingFace if new quantizations are released
cd ~/models/tabby
huggingface-cli download bartowski/Qwen2.5-14B-Instruct-abliterated-exl2 \
  --revision 4.65bpw \
  --local-dir Qwen2.5-14B-Instruct-abliterated \
  --local-dir-use-symlinks False

# Ollama models: pull newer versions (auto-checks for updates)
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

| Layer | Technology | TTL | Persistence |
|-------|-----------|-----|-------------|
| Sensory Buffer | In-memory deque | 30s | None |
| Working Memory | In-memory (token-budgeted) | Session | **✅ Every turn saved** |
| Episodic Memory | SQLite | Permanent | Session summaries |
| Semantic Memory | Qdrant + BM25 + NetworkX | Permanent | Documents + embeddings |
| Procedural Memory | JSON file | Permanent | Skills + user profile |

**⚡ New: Every single interaction (user input + Emily response) is immediately saved to `data/interactions.db` with crash-safe durability.** See [INTERACTION_PERSISTENCE.md](INTERACTION_PERSISTENCE.md) for details.

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
