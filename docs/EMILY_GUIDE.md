# Emily -- The Complete Guide

> Everything you need to know to operate, configure, and understand Emily.

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Starting, Stopping, and Restarting](#2-starting-stopping-and-restarting)
3. [Web API and Dashboard](#3-web-api-and-dashboard)
4. [Dashboards](#4-dashboards)
5. [Models and Providers](#5-models-and-providers)
6. [Skills System](#6-skills-system)
7. [Profiles](#7-profiles)
8. [Personality and Emotions](#8-personality-and-emotions)
9. [Voice System](#9-voice-system)
10. [Memory System](#10-memory-system)
11. [Agents](#11-agents)
12. [Plugins and Tools](#12-plugins-and-tools)
13. [Configuration Reference](#13-configuration-reference)
14. [Security](#14-security)
15. [Observability](#15-observability)
16. [Testing and Development](#16-testing-and-development)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Quick Start

### Hardware Requirements

| Component | Minimum |
|-----------|---------|
| GPU | NVIDIA RTX 4090 (24 GB VRAM) |
| RAM | 64 GB DDR5 |
| CPU | Intel i9-14900K (or equivalent) |
| OS | Arch Linux (bare-metal, not in Docker) |
| Storage | 100+ GB SSD for models and data |

### Installation

```bash
# Clone the repo
git clone <repo-url> Emily1.0 && cd Emily1.0

# Install with uv (recommended)
uv pip install -e ".[gpu-cuda,dev,desktop]"

# Or specific extras only
uv pip install -e ".[gpu-cuda]"   # GPU inference only
uv pip install -e ".[cpu-only]"   # No GPU
uv pip install -e ".[desktop]"    # PySide6 chat app + cloud provider SDKs
uv pip install -e ".[dev]"        # pytest, mypy, ruff
```

### Pull Ollama Models

```bash
ollama pull qwen3:14b        # emily-fast  (default brain, ~10 GB)
ollama pull qwq:32b          # emily-think (deep reasoning, ~20 GB)
ollama pull qwen3:4b          # emily-nano  (quick routing, ~3 GB)
ollama pull minicpm-v:latest  # emily-vision (screen/image, ~8 GB)
ollama pull bge-m3            # embeddings
```

### Start Infrastructure Services

```bash
docker compose up -d
```

This launches Qdrant, SearXNG, Prometheus, Grafana, and Jaeger (see [Dashboards](#4-dashboards)).

### First Launch

```bash
# Full system with GUI dashboards
python main.py

# Or via installed console script
emily
```

Emily will bootstrap all agents, load models, start the voice engine, and open the Brain and Voice dashboards.

---

## 2. Starting, Stopping, and Restarting

### Five Launch Modes

| Mode | Command | What It Does |
|------|---------|--------------|
| Full GUI | `python main.py` or `emily` | Brain + Voice dashboards, full agent system, voice engine |
| Headless | `python main.py --no-gui` or `emily --no-gui` | Voice-only, no desktop GUI. Falls back here if PySide6 is missing |
| Desktop Chat | `python -m emily_chat.main` or `emily-chat` | Standalone PySide6 chat window (no voice, no agents) |
| Web API | `uvicorn api.app:app --host 0.0.0.0 --port 8080` | FastAPI server with web dashboard and REST/WebSocket API |
| Terminal TUI | `python -m ui.terminal.app` | Textual-based terminal chat with memory/log tabs |

Use `--config /path/to/custom.yaml` with the full system to override the default `config.yaml`.

### Docker Compose Services

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart a single service
docker compose restart qdrant
docker compose restart searxng
docker compose restart prometheus
docker compose restart grafana
docker compose restart jaeger

# View logs (follow mode)
docker compose logs -f
docker compose logs -f qdrant    # single service

# Check service health
docker compose ps
```

| Service | Container | Image | Ports | Purpose |
|---------|-----------|-------|-------|---------|
| Qdrant | `emily-qdrant` | `qdrant/qdrant:v1.9.2` | 6333, 6334 | Vector database for semantic memory and RAG |
| SearXNG | `emily-searxng` | `searxng/searxng:latest` | 8888 | Private metasearch engine |
| Prometheus | `emily-prometheus` | `prom/prometheus:v2.52.0` | 9090 | Metrics collection (30-day retention) |
| Grafana | `emily-grafana` | `grafana/grafana:11.1.0` | 3000 | Dashboards and alerting |
| Jaeger | `emily-jaeger` | `jaegertracing/all-in-one:1.57` | 16686, 4317, 4318 | Distributed tracing |

### Killing and Restarting Components

```bash
# Kill the FastAPI server (find PID first)
lsof -i :8080
kill <pid>

# Restart Ollama
systemctl restart ollama

# Kill the desktop chat app
pkill -f "emily_chat.main"

# Kill the full system
pkill -f "main.py"
```

---

## 3. Web API and Dashboard

### Access

- **Dashboard**: http://localhost:8080
- **Voice Dashboard**: http://localhost:8080/voice-dashboard
- **Swagger docs**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

### Authentication

Set `EMILY_API_SECRET` in your `.env` file. All API requests must include this secret.

### API Endpoints

**System:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/status` | System status (FSM, resources, metrics) |
| GET | `/agents` | List all agents |
| GET | `/config` | Current configuration (sanitized) |

**Chat:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat` | Non-streaming chat |
| POST | `/api/v1/chat/stream` | SSE streaming chat (multi-provider) |
| GET | `/chat/voice-transcript` | SSE voice transcript stream |
| WS | `/ws` | WebSocket (chat, status, logs) |

**Memory:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/memory/working` | Working memory contents |
| GET | `/memory/episodic` | Episodic memory search |
| GET | `/memory/procedural` | Procedural memory |

**Other:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/metrics/summary` | Prometheus metrics snapshot |
| GET | `/logs/recent` | Recent log entries |
| GET | `/security/audit` | Audit log |
| GET | `/self-improvement` | Performance stats and capability gaps |

### WebSocket

Connect to `ws://localhost:8080/ws` for real-time streaming of chat responses, system status updates, and log entries.

---

## 4. Dashboards

### Brain Dashboard (PySide6)

Auto-launched by `python main.py` in GUI mode. Displays:

- FSM state transitions
- LLM token stream
- Agent Bus activity
- Perception feed (audio, vision, system)
- Memory operations
- ReAct reasoning chain (Thought -> Plan -> Action -> Observation -> Critique -> Revise -> Respond)
- Full event log (color-coded, filterable)

Not independently launchable -- requires the bootstrap process from `main.py`.

### Voice Dashboard (PySide6)

Also auto-launched with GUI mode. Displays:

- Voice engine state orb and TTS test controls
- TTS, STT, wake word, and speaker cards
- Audio level waveform and SNR
- Live transcript
- Emotion, turn detection, and rhythm sync panels
- Session stats, speaker list, device selector

### Terminal TUI (Textual)

```bash
python -m ui.terminal.app
```

| Key | Action |
|-----|--------|
| F1 | Chat tab |
| F2 | Memory tab |
| F3 | Logs tab |
| Ctrl+L | Clear |
| Ctrl+C | Quit |

### Grafana

- URL: http://localhost:3000
- Login: `admin` / `emily_local_only`
- Auto-provisioned dashboards for Emily metrics
- Datasource: Prometheus at `http://emily-prometheus:9090`

### Jaeger Tracing

- URL: http://localhost:16686
- Browse distributed traces across Emily subsystems
- Receives data via OTLP gRPC on port 4317

---

## 5. Models and Providers

### Provider API Keys

Set these in your `.env` file. Only set the ones you need.

| Provider | Environment Variable |
|----------|---------------------|
| Ollama | `OLLAMA_HOST` (default: `http://localhost:11434`) |
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Google | `GOOGLE_API_KEY` |
| Groq | `GROQ_API_KEY` |
| xAI | `XAI_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| Together | `TOGETHER_API_KEY` |
| Mistral | `MISTRAL_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |

### Complete Model Registry

#### Local (Ollama) -- Free, 100% Private

| Key | Display | Model | Context | Speed | Notes |
|-----|---------|-------|---------|-------|-------|
| `emily-fast` | Emily -- Local Brain | qwen3:14b | 128K | fast | **Default.** ~10 GB VRAM |
| `emily-think` | Emily -- Deep Think | qwq:32b | 128K | medium | ~20 GB VRAM. ReAct++ loop |
| `emily-nano` | Emily -- Quick | qwen3:4b | 32K | blazing | ~3 GB VRAM. Always resident |
| `emily-vision` | Emily -- Vision | minicpm-v:latest | 8K | medium | ~8 GB VRAM. Screen + webcam |

#### Anthropic

| Key | Model | Context | Thinking | Vision | Input $/M | Output $/M |
|-----|-------|---------|----------|--------|-----------|------------|
| `claude-sonnet-4-5` | claude-sonnet-4-5-20260101 | 200K | Yes | Yes | $3.00 | $15.00 |
| `claude-opus-4` | claude-opus-4-20260101 | 200K | Yes | Yes | $15.00 | $75.00 |
| `claude-haiku-4` | claude-haiku-4-20260101 | 200K | -- | Yes | $0.80 | $4.00 |

#### OpenAI

| Key | Model | Context | Thinking | Vision | Input $/M | Output $/M |
|-----|-------|---------|----------|--------|-----------|------------|
| `gpt-5-2` | gpt-5.2 | 256K | -- | Yes | $15.00 | $60.00 |
| `gpt-5` | gpt-5 | 256K | -- | Yes | $8.00 | $32.00 |
| `gpt-4o` | gpt-4o | 128K | -- | Yes | $2.50 | $10.00 |
| `o3` | o3 | 200K | Yes | -- | $10.00 | $40.00 |
| `o4-mini` | o4-mini | 200K | Yes | -- | $1.10 | $4.40 |

#### Google Gemini

| Key | Model | Context | Thinking | Vision | Input $/M | Output $/M |
|-----|-------|---------|----------|--------|-----------|------------|
| `gemini-3-pro` | gemini-3-pro-preview | 2M | Yes | Yes | $2.50 | $15.00 |
| `gemini-3-flash` | gemini-3-flash | 1M | Yes | Yes | $0.10 | $0.40 |
| `gemini-2-5-pro` | gemini-2.5-pro-preview | 1M | Yes | Yes | $1.25 | $10.00 |

#### Groq (Ultra-Low Latency)

| Key | Model | Context | Thinking | Input $/M | Output $/M |
|-----|-------|---------|----------|-----------|------------|
| `groq-llama-70b` | llama-3.3-70b-versatile | 128K | -- | $0.59 | $0.79 |
| `groq-deepseek-r1` | deepseek-r1-distill-llama-70b | 128K | Yes | $0.75 | $0.99 |
| `qwen3-72b` | qwen3-72b | 128K | Yes | $0.29 | $0.39 |
| `llama-4-scout` | llama-4-scout-17b-16e | 10M | -- | $0.11 | $0.34 |

#### xAI

| Key | Model | Context | Vision | Input $/M | Output $/M |
|-----|-------|---------|--------|-----------|------------|
| `grok-4-1` | grok-4.1 | 256K | Yes | $5.00 | $15.00 |

#### DeepSeek

| Key | Model | Context | Thinking | Input $/M | Output $/M |
|-----|-------|---------|----------|-----------|------------|
| `deepseek-v3-2` | deepseek-v3.2-special | 128K | -- | $0.27 | $1.10 |
| `deepseek-r2` | deepseek-r2 | 128K | Yes | $0.55 | $2.19 |

#### Together AI

| Key | Model | Context | Thinking | Vision | Input $/M | Output $/M |
|-----|-------|---------|----------|--------|-----------|------------|
| `qwen3-235b` | Qwen/Qwen3-235B-Instruct | 128K | Yes | -- | $1.30 | $4.00 |
| `llama-4-maverick` | meta-llama/llama-4-maverick | 1M | -- | Yes | $0.50 | $1.50 |

#### Mistral

| Key | Model | Context | Vision | Input $/M | Output $/M |
|-----|-------|---------|--------|-----------|------------|
| `mistral-large-3` | mistral-large-latest | 128K | Yes | $2.00 | $6.00 |
| `codestral-2` | codestral-latest | 256K | -- | $0.30 | $0.90 |
| `mistral-small-3` | mistral-small-latest | 32K | -- | $0.10 | $0.30 |

#### OpenRouter (Paid)

| Key | Model | Context | Thinking | Input $/M | Output $/M |
|-----|-------|---------|----------|-----------|------------|
| `kimi-k2-thinking` | moonshotai/kimi-k2-thinking | 200K | Yes | $0.85 | $2.50 |
| `glm-4-7-thinking` | z-ai/glm-4.7-thinking | 128K | Yes | $0.50 | $1.50 |

#### OpenRouter FREE Tier -- Zero Cost

These require only an `OPENROUTER_API_KEY` (no billing, no credit card). Rate limits: 20 requests/minute, 200 requests/day per model.

| Key | Model ID | Context | Thinking | Vision | Best For |
|-----|----------|---------|----------|--------|----------|
| `or-free-deepseek-r1` | deepseek/deepseek-r1-0528:free | 164K | Yes | -- | Reasoning, math, science |
| `or-free-qwen3-235b` | qwen/qwen3-235b-a22b:free | 131K | Yes | -- | Coding, multilingual, reasoning |
| `or-free-llama-70b` | meta-llama/llama-3.3-70b-instruct:free | 128K | -- | -- | General chat, balanced |
| `or-free-gpt-oss-120b` | openai/gpt-oss-120b:free | 131K | Yes | -- | Agentic tasks, tool use |
| `or-free-qwen3-vl-235b` | qwen/qwen3-vl-235b-a22b:free | 131K | Yes | Yes | Vision, multimodal reasoning |

### How Model Selection Works

Models can be selected three ways:

1. **Top bar dropdown** -- In the desktop app, click the model selector to pick from categorized groups (Local Brain, Thinking, Balanced, Fast, Code, Free, etc.)

2. **Profiles** -- Assign models to roles (core, coding, research, writing, reasoning, fast). When you switch skills, the profile's role mapping determines the model.

3. **Auto-routing** -- Set the model to `auto` and Emily's `EmilyAutoRouter` picks the best available model based on your request. The decision tree:

```
context > 500K tokens  -->  Gemini 3 Pro / Flash / Llama Scout
has video              -->  Gemini 3 Pro / GPT-5.2
has image              -->  Gemini 3 Pro / GPT-5 / Qwen3 VL (free)
thinking + math        -->  o3 / DeepSeek R2 / DeepSeek R1 (free)
math/logic             -->  o4-mini / o3 / DeepSeek R1 (free)
code                   -->  Codestral / DeepSeek V3 / Qwen3 235B (free)
creative               -->  Grok 4.1 / GPT-5.2
non-English            -->  Qwen3 235B / Mistral
EU/GDPR                -->  Mistral Large / Small
agentic (5+ tools)     -->  Kimi K2 / GLM 4.7
priority: speed        -->  Groq Llama 70B / Gemini Flash
priority: cost         -->  Free models first, then Gemini Flash
priority: quality      -->  GPT-5.2 / Gemini 3 Pro / o3
balanced default       -->  GPT-5 / Gemini Flash / Llama 70B (free) / emily-fast
```

The router only considers models whose API key is configured. Free OpenRouter models appear in cost-priority and as last-resort fallbacks.

---

## 6. Skills System

Skills change Emily's behavior, system prompt, temperature, and preferred models. Switch skills in the desktop app's top bar dropdown or set `active_skill_id` in settings.

### Built-in Skills

| Skill ID | Name | Temp | What It Does |
|----------|------|------|--------------|
| `normal` | Normal | 0.5 | Default balanced mode |
| `deep_think` | Deep Think | 0.3 | Step-by-step reasoning with thinking enabled |
| `code` | Code | 0.1 | Write, review, debug, and execute code |
| `research` | Research | 0.2 | Web search with source citation |
| `writing` | Writing | 0.8 | Writing and editing with style guidance |
| `concise` | Concise | 0.3 | 1-3 sentence answers, no preamble |
| `analyst` | Analyst | 0.2 | Systematic analysis with frameworks |
| `tutor` | Tutor | 0.6 | Socratic method teaching |
| `brainstorm` | Brainstorm | 1.0 | Diverse idea generation, high creativity |
| `debate` | Devil's Advocate | 0.7 | Strongest opposing arguments |
| `translate` | Translate | 0.1 | Natural idiomatic translation |
| `eli5` | Simple (ELI5) | 0.6 | Explain like you're 12 |
| `compare` | Compare Models | -- | Send same message to multiple models side-by-side |

### Preferred Models Per Skill

| Skill | Preferred Models (in order) |
|-------|-----------------------------|
| Deep Think | claude-opus-4, o3, deepseek-r2, groq-deepseek-r1 |
| Code | claude-opus-4, codestral-2, deepseek-v3-2, o4-mini |
| Research | claude-sonnet-4-5, gemini-3-pro, gpt-5, groq-deepseek-r1 |
| Writing | grok-4-1, gpt-5-2, claude-opus-4 |
| Concise | claude-haiku-4, gpt-4o, groq-llama-70b, gemini-3-flash |
| Analyst | claude-opus-4, o3, gemini-3-pro, gpt-5 |
| Translate | qwen3-235b, gpt-5, mistral-large-3, gemini-3-flash |

### Custom Skills

Create custom skills in the desktop app's skill editor. They are saved to `~/.emily-chat/custom_skills.json` and persist across sessions. Each custom skill has a name, icon, system prompt addition, temperature, and optional preferred models.

---

## 7. Profiles

Profiles let you build specialized "Emily systems" by assigning a model to each role.

### Roles

| Role Key | Display Name | Mapped from Skill |
|----------|-------------|-------------------|
| `core` | Core (default) | normal, translate |
| `coding` | Coding | code |
| `research` | Research | research |
| `writing` | Writing | writing |
| `reasoning` | Reasoning | deep_think |
| `fast` | Fast | concise |

### How It Works

When you send a message:

1. Emily looks up the active profile
2. Finds the role mapped to the current skill (e.g., skill `code` -> role `coding`)
3. Returns the model assigned to that role
4. If the role is set to `auto`, the auto-router takes over

### Default Profile

The built-in `Default` profile sets every role to `auto`.

### Creating and Editing Profiles

Profiles are stored at `~/.emily-chat/profiles.json`. Example:

```json
{
  "profiles": [
    {
      "id": "default",
      "name": "Default",
      "roles": {
        "core": "auto",
        "coding": "codestral-2",
        "research": "gemini-3-pro",
        "writing": "grok-4-1",
        "reasoning": "o3",
        "fast": "groq-llama-70b"
      }
    },
    {
      "id": "free-only",
      "name": "Free Only",
      "roles": {
        "core": "or-free-llama-70b",
        "coding": "or-free-qwen3-235b",
        "research": "or-free-deepseek-r1",
        "writing": "or-free-llama-70b",
        "reasoning": "or-free-deepseek-r1",
        "fast": "emily-nano"
      }
    }
  ]
}
```

---

## 8. Personality and Emotions

### Personality Vector (5 Dimensions)

Emily's personality is defined as five floats in [0, 1], stored in `persona/profile.json` and configurable in `config.yaml` under `persona`:

| Dimension | Default | Interpretation |
|-----------|---------|----------------|
| `curiosity` | 0.80 | > 0.6 = high (asks follow-ups, explores tangents) |
| `warmth` | 0.85 | > 0.7 = high (empathetic, encouraging) |
| `directness` | 0.70 | > 0.7 = high (gets to the point, no filler) |
| `humor` | 0.50 | > 0.6 = frequent humor, else occasional |
| `formality` | 0.30 | < 0.4 = casual tone, else professional |

To adjust, edit `config.yaml`:

```yaml
persona:
  curiosity: 0.90    # more exploratory
  warmth: 0.60       # less emotional, more neutral
  directness: 0.90   # very terse
  humor: 0.80        # more jokes
  formality: 0.10    # very casual
```

Personality evolves slowly over sessions (rate: 0.01 per session per dimension). Every change is logged with a timestamp and reason in `persona/profile.json`.

### Emotional State (4 Dimensions)

Emily maintains a real-time emotional state that affects TTS prosody, response style, and proactivity:

| Dimension | Default | Neutral Rest | Range |
|-----------|---------|-------------|-------|
| `engagement` | 0.70 | 0.50 | [0.05, 0.95] |
| `confidence` | 0.80 | 0.80 | [0.05, 0.95] |
| `concern` | 0.20 | 0.20 | [0.05, 0.95] |
| `enthusiasm` | 0.60 | 0.60 | [0.05, 0.95] |

Emotions are smoothed via exponential moving average (alpha = 0.15) and decay toward neutral at 2%/hour.

**Event triggers:**

| Event | Effect |
|-------|--------|
| Successful task | confidence +0.1, engagement +0.05, concern -0.05 |
| Failed task | confidence -0.1, concern +0.05 |
| User positive signal | engagement +0.1, enthusiasm +0.1, confidence +0.05 |
| User frustration | concern +0.15, confidence -0.05, enthusiasm -0.1 |
| Idle | engagement -0.02, enthusiasm -0.01 |
| Complex task | engagement +0.1, enthusiasm -0.05 |

### User Mood Detection

Emily detects the user's mood from speech and text signals and adapts her response style:

| Detected Mood | Response Style | TTS Speed | Prosody Energy |
|---------------|---------------|-----------|----------------|
| Stressed | Concise and clear | 0.9x | 0.8 |
| Frustrated | Patient and empathetic | 0.85x | 0.75 |
| Tired | Brief and supportive | 0.85x | 0.7 |
| Focused | Technical and direct | 1.05x | 0.95 |
| Engaged | Detailed and exploratory | 1.0x | 1.0 |

Mood is classified from filler word ratio, speech pace (words per minute), and sentiment word counts.

### Identity Contract

Emily always identifies as Emily regardless of the underlying model. A response filter scrubs every outbound text chunk with 17 regex patterns, replacing any self-identification as Claude, GPT, Gemini, Grok, DeepSeek, Qwen, Kimi, Mistral, or Llama with Emily-safe equivalents. Identity probes ("what model are you", "are you Claude", etc.) trigger reinforcement of her identity.

---

## 9. Voice System

### Pipeline Overview

```
Microphone -> VAD -> STT -> LLM -> TTS -> Speaker
              |               |
         Wake Word       Prosody Engine
```

### Wake Word

- Trigger phrase: **"Hey Emily"**
- Engine: openWakeWord with custom ONNX model
- Detection latency target: < 50ms
- Config: `config.yaml` -> `wake_word.threshold` (default 0.5)

### Voice Activity Detection (VAD)

- Engine: Silero VAD v5
- Adaptive noise floor
- Config: `config.yaml` -> `vad.threshold` (0.5), `min_silence_ms` (500), `min_speech_ms` (250)

### Speech-to-Text (STT)

- Engine: Faster-Whisper large-v3-turbo
- CUDA float16, beam size 5
- Latency target: < 300ms
- Config: `config.yaml` -> `stt.model`, `stt.device`, `stt.compute_type`

### Text-to-Speech (TTS)

Four engines in priority fallback order:

| Engine | Characteristics | VRAM | Latency |
|--------|----------------|------|---------|
| **CSM** (Sesame) | Highest quality conversational speech | ~4-6 GB | Medium |
| **Kokoro** | Ultra-fast, high quality preset voices | Minimal | < 50ms |
| **XTTS v2** (Coqui) | Expressive, supports voice cloning | ~2 GB | ~200ms |

Configure primary and fallback in `config.yaml`:

```yaml
tts:
  primary: kokoro
  fallback: xtts_v2
  kokoro:
    voice: af_heart
  xtts_v2:
    speaker_wav: null    # set to a .wav path for voice cloning
  csm:
    model: sesame/csm-1b
  edge:
    voice: en-US-AvaMultilingualNeural
```

All TTS engines output raw int16 PCM at 24 kHz.

### Voice Cloning

XTTS v2 supports voice cloning from a reference audio file:

```yaml
tts:
  primary: xtts_v2
  xtts_v2:
    speaker_wav: /path/to/reference-voice.wav
```

### Latency Budgets

| Stage | Target |
|-------|--------|
| Wake word detection | < 50ms |
| VAD per chunk | < 1ms |
| STT | < 300ms |
| LLM first token (fast) | < 1s |
| LLM first token (nano) | < 100ms |
| TTS first audio byte | < 200ms |
| End-to-end voice response | < 2s |

### Conversation Features

The voice engine supports full-duplex conversation with:

- **Turn-taking detection** -- knows when you've finished speaking
- **Interruption handling** -- stop Emily mid-sentence by speaking
- **Backchannels** -- Emily says "mhm", "right" to show she's listening
- **Filler words** -- "um", "hmm" for natural speech flow
- **Breath injection** -- natural breathing sounds between sentences
- **Rhythm synchronization** -- matches conversational pace

---

## 10. Memory System

### Five-Tier Pentagonal Architecture

| Tier | Name | Storage | Retention | Purpose |
|------|------|---------|-----------|---------|
| 1 | Sensory Buffer | RAM ring buffer | ms -- seconds | Raw perception events (audio, vision, system) |
| 2 | Working Memory | Priority queue | seconds -- minutes | Active context with token-budget trimming |
| 3 | Episodic Memory | SQLite + Qdrant | minutes -- years | Conversation episodes, searchable by embedding |
| 4 | Knowledge Store | SQLite + Qdrant + networkx | Permanent | Entities, people, relationships, facts, events |
| 5 | Procedural Memory | JSON + Qdrant | Permanent | Skills, self-model, learned behaviors |

All access goes through `MemoryManager` (in `memory/manager.py`), which routes reads/writes to the correct tier, coordinates cross-tier promotion, and enforces access control.

### Inspecting Memory

Via the web API:

```bash
curl http://localhost:8080/memory/working
curl http://localhost:8080/memory/episodic
curl http://localhost:8080/memory/procedural
```

Or via the Terminal TUI (F2 key for Memory tab).

### Knowledge Ingestion

Drop files into the `knowledge/` folder. A file watcher (`rag/watcher.py`) auto-ingests them through the RAG pipeline:

```
File -> Parser -> Chunker -> Deduplicator -> Embedder -> Vector Store
```

**Supported formats:**

| Parser | Extensions |
|--------|-----------|
| PDF | `.pdf` |
| Word | `.docx`, `.doc` |
| eBook | `.epub` |
| Text | `.md`, `.txt`, `.html`, `.htm`, `.csv`, `.json`, `.yaml`, `.yml`, `.pptx` |
| Code | `.py`, `.js`, `.ts`, `.rs`, `.go`, `.java`, `.ipynb` |
| Audio | `.mp3`, `.wav`, `.m4a` (transcribed via STT) |
| Video | `.mp4`, `.mkv` (transcribed via STT) |

Chunking: parent chunks of 2048 tokens with child chunks of 256 tokens at semantic boundaries.

Retrieval: hybrid search using BM25 (sparse) + Qdrant (dense vectors) + BGE-reranker-v2-m3 (cross-encoder) + knowledge graph expansion.

### Memory Configuration

```yaml
memory:
  sensory_buffer_size: 1000
  working_memory_tokens: 4096
  episodic:
    db_path: data/episodes.db
  semantic:
    qdrant_host: localhost
    qdrant_port: 6333
  procedural:
    path: data/procedural.json
  consolidation:
    idle_minutes: 10    # consolidate after 10 min idle
```

---

## 11. Agents

### Core Agents (Always Running)

| Agent | Purpose |
|-------|---------|
| **ConversationAgent** | Real-time dialogue management, turn coordination |
| **PlannerAgent** | Task decomposition and delegation to specialist agents |
| **MemoryAgent** | Memory tier reads/writes, consolidation scheduling |
| **ReflectionAgent** | Idle-time insights, self-model updates, performance reflection |

### Specialist Agents (On-Demand)

| Agent | Purpose |
|-------|---------|
| **ResearchAgent** | Deep-dive RAG + reasoning for complex questions |
| **CodeAgent** | Sandboxed code writing, debugging, execution |
| **MonitorAgent** | System resource monitoring (CPU, RAM, VRAM, disk) |
| **ToolBuilderAgent** | Runtime tool creation from capability gap logs |
| **OnboardingAgent** | First-run user setup and personalization |

### Communication

Agents communicate via `AgentBus` (`core/bus.py`) using ZeroMQ with structured JSON envelopes. Default port: 5555, heartbeat interval: 5 seconds, task timeout: 60 seconds.

### Agent Lifecycle

All agents inherit from `BaseAgent` (`agents/base.py`) and register in `agents/registry.py`. Core agents are eagerly instantiated at startup. Specialist agents are lazily imported when first needed by the PlannerAgent.

---

## 12. Plugins and Tools

### Built-in Tools

| Tool | Description |
|------|-------------|
| `calculator` | Math expression evaluation |
| `code_executor` | Sandboxed code execution |
| `file_ops` | File read/write/search operations |
| `web_search` | Web search via SearXNG |
| `web_fetch` | Fetch and parse web pages |
| `shell` | Shell command execution (requires approval) |
| `git_tool` | Git operations |
| `calendar` | Calendar management |
| `home_assistant` | Home automation integration |
| `image_analyzer` | Image analysis via vision model |
| `notification` | System notifications |
| `process_manager` | Process management (requires approval) |
| `email_reader` | Email inbox access |
| `singing` | Singing synthesis (MusicGen + RVC) |

### Creating New Tools

Every tool must subclass `BaseTool` and implement:

```python
from plugins.base import BaseTool, ToolResult

class MyTool(BaseTool):
    name = "my_tool"
    description = "What it does"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "..."}
        },
        "required": ["input"]
    }

    async def execute(self, context, **params) -> ToolResult:
        """Run the tool."""
        ...

    async def dry_run(self, context, **params) -> ToolResult:
        """Preview what the tool would do without side effects."""
        ...
```

Place the file in `plugins/builtin/`, add a test in `tests/unit/`, and update the README plugin table.

### Generated Tools

The `ToolBuilderAgent` can create tools at runtime based on capability gaps. Generated tools are saved in `plugins/generated/` and require explicit user approval before loading. They are never auto-loaded at startup.

### Sandbox

All tool execution is sandboxed via bubblewrap (`bwrap`):
- No network access by default
- Path allowlist restricts filesystem access
- Configurable via `config.yaml` -> `tools.sandbox`

Tools like `shell` and `process_manager` require human-in-the-loop approval via the consent gate.

---

## 13. Configuration Reference

### config.yaml

The main configuration file. Override the path with `EMILY_CONFIG=/path/to/custom.yaml`. Environment variable overrides follow the pattern `EMILY__SECTION__KEY=value` (double underscore for nesting, case-insensitive).

#### Top-Level

```yaml
name: Emily
version: 1.0.0
log_level: INFO          # DEBUG, INFO, WARNING, ERROR, CRITICAL
data_dir: data
logs_dir: logs
knowledge_dir: knowledge
prompts_dir: prompts
```

#### LLM

```yaml
llm:
  backend: ollama
  ollama_base_url: http://localhost:11434
  models:
    nano: qwen3:4b
    voice_fast: qwen3:4b
    fast: qwen3:14b
    smart: qwq:latest
    reasoning: qwq:latest
    vision: minicpm-v:latest
    embedding: bge-m3
  routing:
    complexity_thresholds:
      fast: 3
      smart: 7
    vram_headroom_gb: 2.0
  inference:
    temperature: 0.7
    top_p: 0.9
    max_tokens: 4096
    context_window: 8192
  critic:
    enabled: true
    min_confidence: 0.65
    max_retries: 2
```

#### Audio, VAD, STT, TTS

```yaml
audio:
  sample_rate: 16000
  channels: 1
  chunk_size: 1024

wake_word:
  model: hey_emily
  threshold: 0.5

vad:
  threshold: 0.5
  min_silence_ms: 500
  min_speech_ms: 250
  adaptive: true

stt:
  model: large-v3-turbo
  device: cuda
  compute_type: float16
  language: en
  beam_size: 5

tts:
  primary: kokoro
  fallback: xtts_v2
```

#### Persona

```yaml
persona:
  curiosity: 0.8
  warmth: 0.85
  directness: 0.7
  humor: 0.5
  formality: 0.3
```

#### Memory

```yaml
memory:
  sensory_buffer_size: 1000
  working_memory_tokens: 4096
  episodic:
    db_path: data/episodes.db
  semantic:
    qdrant_host: localhost
    qdrant_port: 6333
  procedural:
    path: data/procedural.json
  consolidation:
    idle_minutes: 10
```

#### Agents, Tools, RAG

```yaml
agents:
  bus_port: 5555
  heartbeat_interval: 5
  task_timeout: 60
  reflection_interval: 600

tools:
  sandbox:
    enabled: true
    allowed_paths: [...]
  web_search:
    url: http://localhost:8888

rag:
  watch_dir: knowledge
  child_chunk_tokens: 256
  parent_chunk_tokens: 2048
  rerank_top_n: 20
  final_top_n: 5
```

#### API

```yaml
api:
  host: 127.0.0.1
  port: 8000
  rate_limit: 100
  rate_limit_window: 60
  max_body_bytes: 1048576
  cors_origins:
    - http://localhost:8000
    - http://localhost:3000
```

#### Security, Observability

```yaml
security:
  encryption_at_rest: true
  pii_scrub: true
  audit_log: true
  dead_man_switch_days: 30
  approval_required_tools:
    - shell
    - process_manager
    - file_writer

observability:
  otlp_endpoint: localhost:4317
  metrics_port: 9091
  json_logging: true
  tracing_enabled: true
```

### Desktop App Settings

Stored at `~/.emily-chat/settings.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `theme` | `"dark"` | `"dark"` or `"light"` |
| `font_size` | 14 | UI font size |
| `window_width` | 1440 | Window width in pixels |
| `window_height` | 900 | Window height |
| `maximized` | false | Start maximized |
| `left_panel_width` | 260 | Sidebar width |
| `right_panel_width` | 320 | Right panel width |
| `right_panel_visible` | true | Show right panel |
| `default_model` | `"emily-fast"` | Model registry key |
| `active_skill_id` | `"normal"` | Current skill |
| `active_profile_id` | `"default"` | Current profile |

---

## 14. Security

### Encryption at Rest

All sensitive data is encrypted using `age` encryption before writing to disk. Configure in `config.yaml` -> `security.encryption_at_rest`.

### PII Scrubbing

Named Entity Recognition scans all text before disk writes. Detected PII (names, emails, phone numbers, addresses) is scrubbed or replaced with placeholders. Configure via `security.pii_scrub`.

### Audit Log

Append-only tamper-evident log at `logs/audit.log`. Records every sensitive operation: tool executions, memory writes, security events. Browse via the web API at `/security/audit`.

### Consent Gate

Privileged tools require explicit user approval before execution. Tools requiring approval are listed in `security.approval_required_tools` (default: `shell`, `process_manager`, `file_writer`).

### Dead Man's Switch

If the device leaves the home network for more than 30 days, sensitive data is automatically wiped. Configure the threshold with `security.dead_man_switch_days`.

### Secrets Vault

Encrypted secrets storage with TOTP support. Located in `security/vault/`. Includes health checks to verify vault integrity.

### Privacy Boundaries

Emily has 5 privacy categories that require explicit per-session grants:
- `contacts` -- address book access
- `files` -- local file system access
- `calendar` -- calendar data
- `knowledge_base` -- ingested knowledge
- `passwords` -- secrets vault

---

## 15. Observability

### Logging

Emily uses structlog for structured JSON logging. All modules use `get_logger(__name__)`.

- Production: JSON format to `logs/emily.log`
- Development: colored console output
- Log level: set via `config.yaml` -> `log_level` or `EMILY__LOG_LEVEL=DEBUG`

### Prometheus Metrics

Metrics are served on port 9091 (configurable). Scraped by Prometheus at `localhost:9090`.

**Latency histograms:**
- `emily_stt_latency_seconds`
- `emily_llm_first_token_latency_seconds` (label: `model_tier`)
- `emily_tts_first_audio_latency_seconds` (label: `engine`)
- `emily_rag_retrieval_latency_seconds`
- `emily_agent_task_latency_seconds` (label: `agent_name`)
- `emily_tool_execution_latency_seconds` (label: `tool_name`)

**Counters:**
- `emily_conversations_total`
- `emily_llm_requests_total` (labels: `model_tier`, `status`)
- `emily_tool_calls_total` (labels: `tool_name`, `status`)
- `emily_memory_writes_total` / `emily_memory_reads_total` (label: `tier`)
- `emily_rag_documents_ingested_total` (label: `file_type`)
- `emily_critic_retries_total`
- `emily_wake_words_detected_total`
- `emily_stt_errors_total`

**Gauges:**
- `emily_active_agents`
- `emily_agent_queue_depth`
- `emily_working_memory_tokens`
- `emily_vram_used_gb`
- `emily_ram_used_gb`
- `emily_emotional_state` (label: `dimension`)

### Tracing

OpenTelemetry with OTLP gRPC export to Jaeger. View traces at http://localhost:16686.

### Brain Tap

A structlog processor that mirrors log events to the Brain Dashboard GUI in real-time. Zero overhead when the dashboard is not active.

---

## 16. Testing and Development

### Running Tests

```bash
# All tests
pytest

# With coverage report
pytest --cov

# Verbose output
pytest -v

# Specific test file
pytest tests/unit/test_auto_router.py

# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/ -m integration
```

Test configuration: `asyncio_mode = "auto"`, default options: `--cov-report=term-missing -q`.

### Linting

```bash
# Check for issues
ruff check .

# Auto-fix
ruff check --fix .
```

Config: line length 100, Python 3.11 target.

### Type Checking

```bash
mypy . --strict
```

### Test Organization

```
tests/
  unit/          # Fast, isolated tests (mirrors source structure)
  integration/   # Tests requiring external services (marked @pytest.mark.integration)
  e2e/           # End-to-end system tests
  benchmarks/    # Performance benchmarks (LLM latency, RAG throughput)
```

HTTP mocking: `respx`. Time control: `time-machine`.

---

## 17. Troubleshooting

### Missing API Keys

**Symptom:** `ProviderUnavailableError: No API key for <provider>`

**Fix:** Add the API key to your `.env` file:

```bash
echo 'OPENROUTER_API_KEY=sk-or-...' >> .env
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env
```

Restart the app after editing `.env`.

### VRAM Exhaustion

**Symptom:** CUDA out of memory errors, models fail to load.

**Fix:** Check VRAM usage with `nvidia-smi`. The local fleet needs:
- emily-nano: ~3 GB (always resident)
- emily-fast: ~10 GB
- emily-think: ~20 GB
- emily-vision: ~8 GB

You cannot run all four simultaneously on a 24 GB GPU. The model router manages VRAM headroom (default 2 GB buffer). Reduce by using fewer local models or lowering `llm.routing.vram_headroom_gb`.

### Port Conflicts

| Port | Service | Check |
|------|---------|-------|
| 8080 | FastAPI | `lsof -i :8080` |
| 11434 | Ollama | `lsof -i :11434` |
| 6333 | Qdrant | `docker compose ps qdrant` |
| 8888 | SearXNG | `docker compose ps searxng` |
| 9090 | Prometheus | `docker compose ps prometheus` |
| 3000 | Grafana | `docker compose ps grafana` |
| 16686 | Jaeger | `docker compose ps jaeger` |
| 5555 | AgentBus | `lsof -i :5555` |
| 5556 | Perception Bus | `lsof -i :5556` |
| 9091 | Metrics | `lsof -i :9091` |

### Service Health

```bash
# Docker services
docker compose ps

# Ollama
curl http://localhost:11434/api/tags

# Qdrant
curl http://localhost:6333/health

# FastAPI
curl http://localhost:8080/health

# Prometheus
curl http://localhost:9090/-/healthy
```

### Log Files

| Log | Location | Contents |
|-----|----------|----------|
| Main | `logs/emily.log` | All system events (structured JSON) |
| Audit | `logs/audit.log` | Security events, tool executions |
| Vault | `logs/vault_audit.log` | Secrets vault operations |

Tail logs in real-time:

```bash
tail -f logs/emily.log | python -m json.tool
```

### CSM TTS Not Loading

**Symptom:** `csm_load_failed: You are trying to access a gated repo`

**Fix:** The CSM model (`sesame/csm-1b`) is gated on HuggingFace. Either:
1. Request access at https://huggingface.co/sesame/csm-1b and set `HF_TOKEN`
2. Or just use Kokoro as primary TTS (default, works without HF token)

### Wake Word Not Triggering

Check that:
1. The correct audio input device is selected (`config.yaml` -> `audio.input_device`)
2. VAD threshold isn't too high (`vad.threshold`, default 0.5)
3. Wake word threshold isn't too high (`wake_word.threshold`, default 0.5)
4. Microphone permissions are granted
5. No other app is capturing the microphone exclusively

---

## Quick Reference Card

| Action | Command |
|--------|---------|
| Start Emily (GUI) | `python main.py` or `emily` |
| Start Emily (headless) | `python main.py --no-gui` |
| Start desktop chat | `python -m emily_chat.main` or `emily-chat` |
| Start web API | `uvicorn api.app:app --host 0.0.0.0 --port 8080` |
| Start terminal TUI | `python -m ui.terminal.app` |
| Start Docker services | `docker compose up -d` |
| Stop Docker services | `docker compose down` |
| Run tests | `pytest` |
| Lint | `ruff check .` |
| Type check | `mypy .` |
| View web dashboard | http://localhost:8080 |
| View Grafana | http://localhost:3000 |
| View Jaeger traces | http://localhost:16686 |
| View API docs | http://localhost:8080/docs |
| Ingest knowledge | Drop files into `knowledge/` |
| Edit personality | `config.yaml` -> `persona` section |
| Edit profiles | `~/.emily-chat/profiles.json` |
| Edit desktop settings | `~/.emily-chat/settings.json` |
| Check VRAM | `nvidia-smi` |
| Tail logs | `tail -f logs/emily.log` |
