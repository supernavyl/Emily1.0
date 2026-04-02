# Emily 1.0 — Complete Configuration Guide

> **Single source of truth**: `config.yaml` in the project root.  
> **Schema / validation**: `config.py` (Pydantic Settings v2).  
> **Env overrides**: `EMILY__<SECTION>__<KEY>=value` (double-underscore separators).  
> **Never commit** `.env`, secrets, or model weights.

---

## How It Works

```
config.yaml          ← primary source (human-editable)
    ↓
config.py            ← validates, type-checks, provides defaults
    ↓
get_settings()       ← singleton, cached; call anywhere with:
                        from config import get_settings
                        s = get_settings()
```

**Env var override example** (overrides `config.yaml` at runtime, no restart needed):
```bash
EMILY__STT__MODEL=large-v3 python main.py
EMILY__TTS__PRIMARY=xtts python main.py
EMILY__LLM__TABBYAPI_BASE_URL=http://10.0.0.5:5000 python main.py
```

---

## Table of Contents

1. [Core / Identity](#1-core--identity)
2. [LLM — Models](#2-llm--models)
3. [LLM — Routing](#3-llm--routing)
4. [LLM — Inference Defaults](#4-llm--inference-defaults)
5. [LLM — Per-Tier Overrides](#5-llm--per-tier-overrides)
6. [LLM — Backends](#6-llm--backends)
7. [LLM — Critic Loop](#7-llm--critic-loop)
8. [Audio Devices](#8-audio-devices)
9. [Wake Word](#9-wake-word)
10. [VAD (Voice Activity Detection)](#10-vad-voice-activity-detection)
11. [STT (Speech-to-Text)](#11-stt-speech-to-text)
12. [TTS (Text-to-Speech)](#12-tts-text-to-speech)
13. [Voice Engine](#13-voice-engine)
14. [Singing / Music Generation](#14-singing--music-generation)
15. [Memory — All Tiers](#15-memory--all-tiers)
16. [RAG (Retrieval-Augmented Generation)](#16-rag-retrieval-augmented-generation)
17. [Agents & Message Bus](#17-agents--message-bus)
18. [Tools & Sandbox](#18-tools--sandbox)
19. [Vision](#19-vision)
20. [Persona](#20-persona)
21. [Owner & Privacy](#21-owner--privacy)
22. [Security](#22-security)
23. [Self-Improvement](#23-self-improvement)
24. [API Server](#24-api-server)
25. [Observability](#25-observability)
26. [Quick-Change Recipes](#26-quick-change-recipes)

---

## 1. Core / Identity

```yaml
emily:
  name: "Emily"
  version: "1.0.0"
  log_level: "INFO"      # DEBUG | INFO | WARNING | ERROR | CRITICAL
  data_dir: "data"
  logs_dir: "logs"
  knowledge_dir: "knowledge"
  prompts_dir: "prompts"
```

| Key | What it does |
|-----|-------------|
| `name` | Display name used in all UI/logs. Do NOT change to bot/assistant/NOVA. |
| `log_level` | Global log verbosity. Use `DEBUG` to troubleshoot, `WARNING` for production. |
| `data_dir` | Root for all databases, episodic memory, interaction logs, etc. |
| `logs_dir` | Where structlog + audit logs are written. |
| `knowledge_dir` | Documents watched by the RAG ingestion pipeline. |
| `prompts_dir` | Directory for prompt templates (source of truth is `llm/prompt_builder.py`). |

---

## 2. LLM — Models

```yaml
llm:
  backend: "ollama"
  ollama_base_url: "http://localhost:11434"
  tabbyapi_base_url: "http://localhost:5000"   # optional, only needed if using TabbyAPI
  tabbyapi_api_key: ""
  models:
    nano:       "goekdenizguelmez/JOSIEFIED-Qwen3:8b"      # routing & classification
    voice_fast: "goekdenizguelmez/JOSIEFIED-Qwen3:8b"      # real-time voice (<1 s)
    fast:       "goekdenizguelmez/JOSIEFIED-Qwen3:14b"     # standard conversation
    smart:      "huihui_ai/qwen3.5-abliterated:27b"        # complex reasoning
    reasoning:  "huihui_ai/qwen3.5-abliterated:27b"        # deep thinking
    vision:     "minicpm-v:latest"                         # screen / webcam
    embedding:  "bge-m3"                                   # Qdrant + BM25
    cloud_best: "claude-opus-4-6"                          # Anthropic — reflection, planning
    cloud_fast: "claude-sonnet-4-6"                        # Anthropic — fast cloud
```

### Model Tiers

| Tier | Model | Role | Approx VRAM | Change when… |
|------|-------|------|-------------|--------------|
| `nano` | JOSIEFIED-Qwen3:8b | Routing, classification, quick tasks | ~5 GB | You want a faster routing model |
| `voice_fast` | JOSIEFIED-Qwen3:8b | Real-time voice replies (<1 s) | ~5 GB | You want a different voice model |
| `fast` | JOSIEFIED-Qwen3:14b | Standard conversation, most queries | ~9 GB | You upgrade to a better 14B model |
| `smart` | Qwen3.5-abliterated:27b | Complex reasoning, multi-step | ~17 GB | You swap to a different large model |
| `reasoning` | Qwen3.5-abliterated:27b | Deep chain-of-thought with thinking | ~17 GB | Usually same as `smart` |
| `vision` | minicpm-v:latest | Screen + webcam understanding | ~8 GB | You switch to another vision model |
| `embedding` | bge-m3 | Qdrant + BM25 semantic search | ~2 GB | You change embedding dimensions (needs migration!) |
| `cloud_best` | claude-opus-4-6 | Deep reasoning, agents, reflection | cloud | Use for tasks needing maximum quality |
| `cloud_fast` | claude-sonnet-4-6 | Fast cloud with extended thinking | cloud | Use when local GPU is busy / unavailable |

> **Note**: JOSIEFIED = abliterated + fine-tuned to preserve tool-use and instruction-following.
> `vision` and `embedding` always use Ollama. `cloud_best`/`cloud_fast` require `ANTHROPIC_API_KEY`.

### Backend URLs

| Key | Purpose |
|-----|---------|
| `ollama_base_url` | Ollama server — all local text, vision, and embedding models. |
| `tabbyapi_base_url` | ExLlamaV2 server — only needed if you re-enable TabbyAPI tiers. |
| `tabbyapi_api_key` | Only set if you enabled auth in TabbyAPI's `config.yml`. |

---

## 3. LLM — Routing

```yaml
llm:
  routing:
    complexity_threshold_fast: 3     # score 0-10 → below this = nano tier
    complexity_threshold_smart: 7    # score 0-10 → above this = smart tier
    voice_fast_complexity_threshold: 5  # voice below this → voice_fast tier
    voice_skip_rag_below: 5          # skip RAG for simple voice queries
    voice_skip_critic: true          # disable critic loop for voice (saves latency)
    vram_headroom_gb: 2.0            # keep this much VRAM free before loading model
    default_stream: true             # stream tokens by default
```

| Key | Effect |
|-----|--------|
| `complexity_threshold_fast` | Raise to send more queries to `nano` (cheaper/faster). Lower = more to `fast`. |
| `complexity_threshold_smart` | Raise to send fewer queries to `smart` (saves VRAM). Lower = more reasoning. |
| `voice_fast_complexity_threshold` | Tune voice latency. Higher = more voice queries use `voice_fast` (faster). |
| `voice_skip_rag_below` | Skip expensive vector search for simple voice queries. |
| `voice_skip_critic` | `true` = no critic pass on voice turns (big latency saving). |
| `vram_headroom_gb` | Safety buffer. Increase on systems with less VRAM. |

---

## 4. LLM — Inference Defaults

```yaml
llm:
  inference:
    temperature: 0.7       # creativity (0.0 = deterministic, 1.0+ = chaotic)
    top_p: 0.9             # nucleus sampling cutoff
    repeat_penalty: 1.1    # penalise repeated tokens
    max_tokens: 4096       # max output length (tokens)
    context_window: 8192   # input context length (tokens)
```

These are the **baseline** values. Per-tier overrides below take precedence.

| Key | Tweak guide |
|-----|------------|
| `temperature` | Lower for factual/code tasks (0.3–0.5), higher for creative (0.8–1.0). |
| `top_p` | Usually leave at 0.9. Lower to restrict vocabulary diversity. |
| `repeat_penalty` | Increase (1.15–1.2) if model repeats itself. |
| `max_tokens` | Increase for long-form writing; decrease to cap costs/latency. |
| `context_window` | Must not exceed the loaded model's actual context. |

---

## 5. LLM — Per-Tier Overrides

```yaml
llm:
  tier_inference:
    nano:
      temperature: 0.3
      max_tokens: 512
      enable_thinking: false
    voice_fast:
      temperature: 0.7
      max_tokens: 1024
      enable_thinking: false   # MUST be false for <1s voice latency
    fast:
      temperature: 0.7
      max_tokens: 4096
      enable_thinking: true
    smart:
      temperature: 0.6
      max_tokens: 8192
      enable_thinking: true
    reasoning:
      temperature: 0.6
      max_tokens: 16384
      enable_thinking: true    # ALWAYS true for Qwen3.5-27B reasoning
    cloud_best:
      temperature: 1.0         # Anthropic requires temp=1 for extended thinking
      max_tokens: 16384
      enable_thinking: true
      thinking_budget: 16000   # Claude Opus 4.6 extended thinking token budget
    cloud_fast:
      temperature: 1.0
      max_tokens: 8192
      enable_thinking: true
      thinking_budget: 8000    # Claude Sonnet 4.6 extended thinking token budget
```

`enable_thinking` controls Qwen3/Qwen3.5 `<think>` blocks (and Claude extended thinking).
- `false` on `nano` + `voice_fast` = fastest possible responses.
- `true` on `smart`/`reasoning` = better accuracy at cost of latency.
- Cloud tiers always use extended thinking; set `thinking_budget` to control token spend.

---

## 6. LLM — Backends

```yaml
llm:
  tier_backend:
    nano:       "ollama"      # JOSIEFIED-Qwen3 8B
    voice_fast: "ollama"      # JOSIEFIED-Qwen3 8B — same model, no-think mode
    fast:       "ollama"      # JOSIEFIED-Qwen3 14B
    smart:      "ollama"      # Qwen3.5-abliterated 27B
    reasoning:  "ollama"      # Qwen3.5-abliterated 27B
    vision:     "ollama"      # MiniCPM-V — always ollama
    embedding:  "ollama"      # BGE-M3 — always ollama
    cloud_best: "anthropic"   # Claude Opus 4.6 — requires ANTHROPIC_API_KEY
    cloud_fast: "anthropic"   # Claude Sonnet 4.6 — requires ANTHROPIC_API_KEY
```

Valid values: `ollama` | `anthropic` | `tabbyapi` | `llamacpp`

```yaml
llm:
  llamacpp:
    enabled: false           # set true to use llama-cpp-python as fallback
    models_dir: "models"
    models:
      nano:
        filename: "qwen3-4b-abliterated-q4_k_m.gguf"
        n_gpu_layers: -1     # -1 = all layers on GPU
        n_ctx: 32768
        n_batch: 512
```

---

## 7. LLM — Critic Loop

```yaml
llm:
  critic:
    enabled: true
    min_confidence: 0.65   # retry if LLM confidence below this
    max_retries: 2
```

The critic re-evaluates LLM output and retries if quality is too low.
- Disable (`enabled: false`) to reduce latency at the cost of output quality.
- Raise `min_confidence` for stricter self-review.

---

## 8. Audio Devices

```yaml
audio:
  sample_rate: 16000      # Hz — Whisper expects 16 kHz
  channels: 1             # mono for STT
  chunk_size: 1024        # audio buffer chunk
  input_device: 10        # device index (see below to find yours)
  output_device: 41       # device index
```

### Finding Your Device Index

```bash
python find_usb_audio.py
# or
python -c "import sounddevice as sd; print(sd.query_devices())"
```

Set `input_device`/`output_device` to the integer index shown.

---

## 9. Wake Word

```yaml
wake_word:
  model: "hey_emily"          # model name in assets/voice_profiles/ or openWakeWord built-in
  threshold: 0.5              # detection confidence (0.0–1.0); lower = more sensitive
  inference_framework: "onnx" # onnx | tflite
  custom_model_path: null     # path to custom .onnx model file
```

| Key | Guide |
|-----|-------|
| `threshold` | Lower (0.3) = more false positives but fewer missed wake words. Raise (0.7) for quiet environments. |
| `custom_model_path` | Point to a trained `.onnx` file to use a completely custom wake word. |

---

## 10. VAD (Voice Activity Detection)

```yaml
vad:
  model: "silero"         # silero is the only supported model currently
  threshold: 0.1          # speech probability cutoff (0.0–1.0)
  min_silence_ms: 600     # ms of silence before end-of-speech
  min_speech_ms: 0        # minimum ms of speech to count as valid utterance
  adaptive: true          # auto-adjust threshold based on ambient noise
  noise_floor_update_rate: 0.005  # how fast adaptive threshold tracks noise
```

| Key | Tuning guide |
|-----|-------------|
| `threshold` | Lower (0.05) in noisy environments. Raise (0.2–0.3) to reduce false triggers. |
| `min_silence_ms` | How long Emily waits after you stop speaking. Increase for slow speakers. |
| `min_speech_ms` | Raise to ignore short sounds (coughs, clicks). |
| `adaptive` | Keep `true` unless you have a very consistent microphone level. |

---

## 11. STT (Speech-to-Text)

```yaml
stt:
  profile: "accurate"         # fast | accurate — switches beam sizes automatically
  model: "large-v3-turbo"     # Whisper model size
  device: "cuda"              # cuda | cpu | mps
  compute_type: "float16"     # float16 | int8 | float32
  language: "en"              # ISO 639-1 code, or null for auto-detect
  word_timestamps: true
  beam_size: 5                # manual beam size (overridden by profile)
  voice_fast_beam_size: 1     # used when profile=fast
  voice_accurate_beam_size: 3 # used when profile=accurate
```

### Whisper Model Sizes

| `model` | Speed | Accuracy | VRAM |
|---------|-------|----------|------|
| `tiny` | Fastest | Lowest | ~0.5 GB |
| `base` | Very fast | Low | ~0.7 GB |
| `small` | Fast | Medium | ~1.5 GB |
| `medium` | Medium | Good | ~3 GB |
| `large-v3` | Slow | Best | ~6 GB |
| `large-v3-turbo` | Medium-fast | Best | ~6 GB ✓ recommended |

### Streaming STT Settings

```yaml
stt:
  streaming_window_duration_s: 4.0      # audio window sent to Whisper
  streaming_process_interval_s: 0.12    # how often streaming re-processes
  streaming_min_buffer_s: 0.25          # minimum audio before first processing
  streaming_commit_skip_threshold_s: 0.2
  streaming_rms_gate_threshold: 0.0045  # silence gate (lower = more sensitive)
  streaming_commit_confidence: 0.8      # confidence to commit transcript
  streaming_reject_low_confidence: 0.74 # below this = discard transcript
  streaming_min_final_words: 5
  streaming_min_unique_ratio: 0.6
  streaming_max_repeat_ratio: 0.5
  streaming_short_utterance_confidence: 0.92

  use_whisper_vad: false          # use Whisper's built-in VAD (vs Silero)
  whisper_vad_threshold: 0.1
  whisper_vad_min_speech_ms: 0
  whisper_vad_min_silence_ms: 300
  no_speech_threshold: 0.6        # probability above this = silence, ignore
```

**Common STT changes:**

- Faster (lower accuracy): `profile: "fast"`, `model: "small"`, `compute_type: "int8"`
- Better accuracy: `profile: "accurate"`, `model: "large-v3-turbo"`, `compute_type: "float16"`
- Multilingual: set `language: null` (auto-detect) or e.g. `language: "fr"`
- Fix cut-off speech: raise `min_silence_ms` in `vad` section (e.g. 800–1200)

---

## 12. TTS (Text-to-Speech)

```yaml
tts:
  primary: "kokoro"         # kokoro | csm | xtts
  fallback: "csm"           # used if primary fails
  voice_preset: "en_US_female_1"  # legacy preset label (see per-engine voice below)
  streaming_chunk_size: 100 # characters per TTS chunk in streaming mode
```

### Kokoro (Default — Recommended)

```yaml
tts:
  kokoro:
    voice: "af_heart"   # voice ID (see full list below)
    speed: 0.88         # playback speed (0.5–2.0)
```

**Kokoro voice IDs** — female voices start with `af_`/`bf_`, male with `am_`/`bm_`:

| ID | Description |
|----|-------------|
| `af_heart` | American female, warm (default) |
| `af_sky` | American female, bright |
| `af_nova` | American female, neutral |
| `af_bella` | American female, gentle |
| `am_adam` | American male, deep |
| `am_michael` | American male, neutral |
| `bf_emma` | British female, formal |
| `bf_isabella` | British female, warm |
| `bm_george` | British male, deep |
| `bm_lewis` | British male, neutral |

### CSM (Sesame Conversational Speech Model)

```yaml
tts:
  csm:
    model_id: "sesame/csm-1b"
    speaker_id: 0          # 0 = default speaker; change for different voices
    max_audio_length: 150  # max seconds of audio per generation
    dtype: "bfloat16"      # bfloat16 | float16 | float32
```

### XTTS v2 (Multilingual, Clone)

```yaml
tts:
  xtts:
    model_name: "tts_models/multilingual/multi-dataset/xtts_v2"
    speaker_wav: null      # path to .wav file for voice cloning (null = default)
    language: "en"         # language code
    speed: 1.0
```

To **clone a voice**: record a clean 10–30 s WAV clip, set `speaker_wav: "path/to/clip.wav"`.

**Switching TTS providers:**

```yaml
tts:
  primary: "xtts"     # switch to XTTS
  fallback: "kokoro"
```

---

## 13. Voice Engine

```yaml
voice_engine:
  enabled: true
  stt_provider: "faster_whisper"   # faster_whisper | whisper | deepgram
  llm_provider: "ollama"           # uses TabbyAPI internally; this is legacy
  tts_provider: "kokoro"           # kokoro | csm | xtts
  vad_threshold: 0.5
  min_speech_ms: 200
  min_silence_ms: 800
```

The `voice_engine` section controls the high-level pipeline selection.  
Detailed STT config is in the `stt:` section; TTS config in `tts:`.

---

## 14. Singing / Music Generation

```yaml
singing:
  enabled: true
  primary: "musicgen"    # musicgen | rvc | suno
  fallback: "suno"
  output_dir: "data/singing_output"
```

### MusicGen (Local, AudioCraft)

```yaml
singing:
  musicgen:
    enabled: true
    model_size: "small"    # small | medium | large
    duration_seconds: 30
    device: "cuda:0"
```

### RVC (Voice Conversion)

```yaml
singing:
  rvc:
    enabled: true
    model_path: null       # path to .pth RVC model
    index_path: null       # path to .index file
    device: "cuda:0"
    f0_method: "rmvpe"     # rmvpe | crepe | harvest | pm | dio
    transpose: 0           # semitone shift
```

### Suno (Cloud API)

```yaml
singing:
  suno:
    enabled: true
    api_url: "https://api.sunoapi.org"
    api_key: null          # set via SUNO_API_KEY env var
    model_version: "v4"
    timeout_seconds: 120
```

---

## 15. Memory — All Tiers

```yaml
memory:
  sensory_buffer_size: 1000    # max items in RAM ring buffer (~30s window)
```

### Working Memory (per-session)

```yaml
memory:
  working:
    max_tokens: 4096                # token budget for active context window
    pin_important_threshold: 0.8    # importance score to always keep in window
```

### Episodic Memory (SQLite)

```yaml
memory:
  episodic:
    db_path: "data/episodes.db"
    auto_summarize: true                    # summarise old episodes automatically
    summary_model: "fast"                   # which LLM tier summarises
    save_all_interactions: true             # persist every turn immediately
    interactions_db_path: "data/interactions.db"
    auto_backup_interval_minutes: 30
```

### Semantic Memory (Qdrant + BM25)

```yaml
memory:
  semantic:
    qdrant_url: "http://localhost:6333"
    collection_name: "emily_semantic"
    bm25_index_path: "data/bm25_index"
    temporal_decay_days: 365      # memories older than this lose relevance faster
    decay_factor: 0.95
```

### Procedural Memory (JSON)

```yaml
memory:
  procedural:
    path: "data/procedural.json"    # user profile, learned skills, preferences
```

### Consolidation (background compaction)

```yaml
memory:
  consolidation:
    idle_trigger_minutes: 10        # compact after this many idle minutes
    max_episodes_per_run: 20        # max episodes consolidated per pass
    reflection_model: "smart"       # LLM tier used for reflection
```

---

## 16. RAG (Retrieval-Augmented Generation)

```yaml
rag:
  watch_dirs:
    - "knowledge"             # directories watched for new documents
  chunk_size_child: 256       # small chunk size for retrieval
  chunk_size_parent: 2048     # larger context chunk returned with result
  chunk_overlap: 32           # overlap between adjacent chunks
  embedding_batch_size: 32    # embeddings computed per batch
  query_expansion_count: 3    # number of query variations generated
  rerank_top_k: 20            # candidates before reranking
  final_top_k: 5              # final results passed to LLM
```

To add a knowledge source: drop files into `knowledge/` (PDF, TXT, MD, DOCX supported).

---

## 17. Agents & Message Bus

```yaml
agents:
  message_bus_port: 5555          # ZeroMQ PUB/SUB port
  heartbeat_interval_s: 5         # agent liveness ping frequency
  task_timeout_s: 60              # max seconds per agent task
  reflection_interval_minutes: 10 # how often ReflectionAgent runs
  monitor_interval_s: 30          # MonitorAgent polling interval
```

---

## 18. Tools & Sandbox

```yaml
tools:
  sandbox: "bubblewrap"    # bubblewrap | none
  allowed_paths:
    - "/home/supernovyl/Emily1.0"
    - "/tmp/emily_sandbox"
  web_search_url: "http://localhost:8888"  # SearXNG instance
  home_assistant:
    url: "http://localhost:8123"
    token: null            # set in .env as HOME_ASSISTANT_TOKEN
```

> ⚠️ Adding paths to `allowed_paths` expands Emily's file access. Be careful.

---

## 19. Vision

```yaml
vision:
  enabled: true
  screen_capture_interval_s: 5    # seconds between screen grabs
  webcam_device: 0                # /dev/video index
  emotion_detection: true         # detect emotion from webcam
```

Set `enabled: false` to disable all vision processing and free ~8 GB VRAM.

---

## 20. Persona

```yaml
persona:
  profile_path: "persona/profile.json"
  curiosity: 0.5        # 0.0 = incurious, 1.0 = extremely curious
  warmth: 0.5           # 0.0 = cold/formal, 1.0 = very warm
  directness: 0.5       # 0.0 = indirect/hedging, 1.0 = blunt
  humor: 0.2            # 0.0 = serious, 1.0 = very playful
  formality: 0.5        # 0.0 = casual, 1.0 = formal
  evolution_rate: 0.0   # how fast traits drift via self-improvement (0 = locked)
```

All values are floats `0.0–1.0`. Set `evolution_rate: 0.0` to lock personality permanently.

---

## 21. Owner & Privacy

```yaml
owner:
  enabled: true
  identity_file: "data/owner_identity.json"
  require_verification: true          # ask for passphrase at session start
  verification_timeout_minutes: 60    # re-verify after this idle period
  guest_mode_enabled: true            # allow non-owner access with limited scope
  share_personal_with_guests: false   # NEVER change to true
  lockout_after_failed_attempts: 3
  lockout_duration_minutes: 5
```

> 🔒 `share_personal_with_guests` must always be `false`. Personal data is never shared.

---

## 22. Security

> ⚠️ Changes to this section require **explicit user approval** per project rules.

```yaml
security:
  encrypt_at_rest: true
  key_file: "~/.emily_key"         # AES encryption key location
  pii_scrub: true                  # scrub PII from logs
  audit_log_path: "logs/audit.log"
  dead_man_switch_days: 30         # wipe data if Emily not used for N days
  require_approval_tools:
    - "shell"
    - "process_manager"
    - "file_writer"
```

---

## 23. Self-Improvement

```yaml
self_improvement:
  track_performance: true
  evolve_prompts: true                              # allow prompt A/B testing
  prompt_ab_test_sessions: 10                       # sessions per A/B trial
  capability_gap_log: "data/capability_gaps.jsonl"
  performance_log: "data/performance_log.jsonl"
```

Set `evolve_prompts: false` to freeze all prompt evolution (stable/production mode).

---

## 24. API Server

```yaml
api:
  host: "127.0.0.1"    # change to "0.0.0.0" to expose on network (security risk)
  port: 8001            # 8000 may be taken by other services; web UI proxies here
  reload: true          # set true in development (auto-reload on file change)
  secret_key: null      # set in .env as EMILY__API__SECRET_KEY
```

The web UI (Vite) runs on **port 1420** and proxies:
- `/api/v1/*` → `http://localhost:8001/api/v1/` (unchanged path)
- `/api/*` → `http://localhost:8001/` (prefix stripped → Emily routes)

Run the API: `uv run uvicorn api.app:app --host 127.0.0.1 --port 8001 --reload`

---

## 25. Observability

```yaml
observability:
  otlp_endpoint: "http://localhost:4317"   # Jaeger / OpenTelemetry collector
  metrics_port: 9091                        # Prometheus scrape port
  log_format: "json"                        # json | text
  tracing_enabled: true
```

---

## 26. Quick-Change Recipes

### Switch TTS voice to British male

```yaml
tts:
  kokoro:
    voice: "bm_george"
    speed: 0.9
```

### Use XTTS with voice cloning

```yaml
tts:
  primary: "xtts"
  fallback: "kokoro"
  xtts:
    speaker_wav: "assets/voice_profiles/my_voice.wav"
    language: "en"
    speed: 1.0
```

### Use a smaller/faster Whisper model

```yaml
stt:
  model: "medium"
  profile: "fast"
  compute_type: "int8"
```

### Use a different smart model

```yaml
llm:
  models:
    smart: "huihui_ai/qwen3.5-abliterated:72b"
    reasoning: "huihui_ai/qwen3.5-abliterated:72b"
  tier_backend:
    smart: "ollama"
    reasoning: "ollama"
```

### Use Claude for complex tasks only

```yaml
llm:
  routing:
    complexity_threshold_smart: 8  # raise to keep most queries local
  tier_backend:
    smart: "anthropic"    # only highest-complexity queries hit Claude
    reasoning: "anthropic"
  models:
    smart: "claude-opus-4-6"
    reasoning: "claude-opus-4-6"
```

### Disable vision to free VRAM

```yaml
vision:
  enabled: false
```

### Disable critic loop for maximum speed

```yaml
llm:
  critic:
    enabled: false
  routing:
    voice_skip_critic: true
```

### Enable all language auto-detection (multilingual)

```yaml
stt:
  language: null    # auto-detect per utterance
tts:
  xtts:
    language: "auto"
```

### Increase memory context window

```yaml
llm:
  inference:
    context_window: 32768
  tier_inference:
    smart:
      max_tokens: 16384
```

### Make Emily warmer and more playful

```yaml
persona:
  warmth: 0.9
  humor: 0.7
  formality: 0.2
  directness: 0.4
```

### Change wake word sensitivity

```yaml
wake_word:
  threshold: 0.35    # lower = more sensitive, more false positives
vad:
  threshold: 0.08
```

---

## Environment Variable Reference

Any `config.yaml` key can be overridden at runtime:

```
EMILY__<SECTION>__<KEY>=value
```

Examples:
```bash
EMILY__TTS__PRIMARY=csm
EMILY__STT__MODEL=medium
EMILY__LLM__MODELS__FAST=bartowski/Llama-3.1-8B-Instruct-exl2
EMILY__LLM__TABBYAPI_API_KEY=your_key_here
EMILY__MEMORY__WORKING__MAX_TOKENS=8192
EMILY__PERSONA__WARMTH=0.9
EMILY__VISION__ENABLED=false
EMILY__API__HOST=0.0.0.0
```

Nested keys use `__` (double underscore) as separator.

---

*Last updated: 2026-03-01*
