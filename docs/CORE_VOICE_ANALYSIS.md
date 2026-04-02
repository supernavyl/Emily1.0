# Emily Core & Voice System Analysis

**Generated:** February 28, 2026  
**Scan Depth:** Complete architecture review of core/ and voice/ + voice_engine/ subsystems

---

## 🧠 CORE SYSTEM ARCHITECTURE

### 1. **Bootstrap & Dependency Injection** (`core/bootstrap.py`)

**Purpose:** Root composition object managing all Emily subsystems

**Key Features:**
- **Startup Order:** Observability → Buses → Scheduler → LLM Fleet → Memory → Agents → Voice
- **Voice Mode Selection:** Auto-detects VoiceEngine 1.3 availability, falls back to legacy pipeline
- **Graceful Degradation:** Vision pipeline non-critical, continues if it fails
- **Signal Handlers:** SIGINT/SIGTERM for graceful shutdown (skips on non-main thread for Qt GUI)
- **Background Tasks:** Manages asyncio task lifecycle with proper cancellation

**Integration Points:**
```python
# Voice Engine 1.3 (preferred)
- EmilyLLMProvider: Routes voice LLM through Emily's fleet + memory
- EmilyTTSProvider: Reuses Emily's Kokoro TTS instance
- Full-duplex conversation with barge-in

# Legacy Mode (fallback)
- Half-duplex pipeline + perception-TTS bridge
```

---

### 2. **Message Bus System** (`core/bus.py`)

**Two Buses:**

#### **PerceptionBus (ZeroMQ PUB/SUB)**
- **Ports:** 5556 (publish), 5557 (subscribe)
- **Purpose:** Sensory events → Attention router
- **Transport:** MessagePack with JSON fallback
- **Priority Levels:** 0-4 (Emergency → Idle)

#### **AgentBus (ZeroMQ PUSH/PULL)**
- **Port:** 5555
- **Purpose:** Inter-agent task delegation
- **Message Envelope:**
```python
{
    "id": UUID4,
    "sender": str,
    "recipient": str | "broadcast",
    "type": str,
    "payload": dict,
    "priority": 0-4,
    "timestamp": float,
    "task_id": str | None,
    "deadline_ms": int | None,
    "context_refs": list[str]
}
```

**Brain Dashboard Integration:** All messages mirrored to BrainEventHub for live monitoring

---

### 3. **Priority Scheduler** (`core/scheduler.py`)

**Architecture:** Min-heap asyncio priority queue with per-tier concurrency limits

**Concurrency Caps:**
```python
P0 Emergency:  999 (unbounded)
P1 Realtime:   8 concurrent
P2 Active:     4 concurrent
P3 Background: 2 concurrent
P4 Idle:       1 concurrent
```

**Features:**
- **Deadline Enforcement:** Auto-cancellation if `deadline_ms` exceeded
- **Backpressure:** Queue depth tracked via Prometheus metric
- **Worker Isolation:** Each priority tier has dedicated semaphore

---

### 4. **Finite State Machine** (`core/fsm.py`)

**System States:**
```
IDLE → LISTENING → PROCESSING → RESPONDING
         ↕            ↕             ↕
   REFLECTING    TOOL_USE      ERROR → SHUTDOWN
```

**Transition Rules:**
- Hard-coded valid transition matrix prevents illegal states
- All transitions logged and broadcast to observers
- `FSMError` raised on invalid transitions
- Thread-safe with asyncio.Lock

**Observer Pattern:** Async callbacks fired on every state change

---

### 5. **Brain Event Hub** (`core/brain_hub.py`)

**Purpose:** Central event collector for PySide6 GUI dashboard

**Event Categories:**
- `llm`: Token streams, model swaps
- `react`: Agent reasoning steps
- `agent`: Task delegation, results
- `perception`: Audio/vision events
- `fsm`: State changes
- `memory`: Retrievals, consolidations
- `log`: Structured logs (rate-limited to 50/sec)

**Ring Buffer:** 1000 recent events for late-joining panels (backfill)

**Thread Safety:** `emit_sync()` callable from any thread, uses Qt signals for cross-thread delivery

---

## 🎙️ VOICE SYSTEM ARCHITECTURE

### 1. **TTS Engine** (`voice/tts.py`)

**Multi-Tier Strategy:**

#### **Kokoro (Primary, Ultra-Fast)**
- **Latency:** <50ms first-audio
- **Quality:** High preset voices
- **Fallback:** espeak-only pipeline if spacy broken (Python 3.14 pydantic-v1 workaround)

#### **XTTS v2 (Expressive)**
- **Latency:** ~200ms
- **Features:** Voice cloning, emotional prosody
- **GPU:** Required, Coqui TTS library

#### **CSM (Sesame, Experimental)**
- **Quality:** Highest conversational realism
- **Status:** Config mentions, implementation pending

**Streaming Architecture:**
```
text → ProsodyController → per-sentence TTSEngine.stream() → PCM bytes → speaker
```

**Audio Format:** All engines yield **int16 PCM @ 24kHz** for downstream uniformity

**Crossfade:** 480-sample overlap between chunks eliminates clicks/pops

---

### 2. **Prosody Controller** (`voice/prosody.py`)

**Inputs:**
- Emily's emotional state (engagement, confidence, concern, enthusiasm, warmth)
- Sentence semantics (question, exclamation, list, parenthetical)
- Position within response (emphasis tapers after 4 sentences)

**Outputs:**
```python
@dataclass
class ProsodyParams:
    speed: float = 1.0       # 0.7-1.8
    pitch: float = 1.0       # 0.8-1.3
    energy: float = 1.0      # 0.6-1.4
    pause_before_ms: int = 0
    pause_after_ms: int = 200
```

**Semantic Rules:**
- Questions: +8% pitch, -7% speed, 350ms pause
- Exclamations: +12% energy, +5% speed
- Ellipses/em-dashes: -15% speed, 500ms pause
- Lists: -5% speed, 150ms pause
- Emphasis words ("very", "really"): +8% energy, +3% pitch
- Hedging words ("maybe", "perhaps"): -5% speed, -8% energy

**Whisper Mode:** 50% energy, 85% speed for quiet environments

---

### 3. **Audio Output Stream** (`voice/output_stream.py`)

**True Streaming:** Plays chunks as they arrive, not after buffering entire response

**Features:**
- **Format Detection:** Auto-detects WAV / raw PCM int16 / MP3
- **Volume Normalization:** Target -20 dBFS to prevent jumps between sentences/engines
- **Interruption Support:** `interrupt()` stops playback mid-stream
- **AEC Reference Feed:** For full-duplex echo cancellation
- **Playback Queue:** 50-chunk asyncio.Queue with separate drain task

**Normalization Algorithm:**
```python
1. Compute RMS of chunk
2. Calculate gain_db to reach -20 dBFS
3. Clamp gain_db to ±12 dB
4. Apply gain with limiter at 0.95 peak
```

---

### 4. **Breath Injection** (`voice/breath_injector.py`)

**Breath Types:**
- `INHALE_DEEP`: Before long sentences (>8 words)
- `INHALE_SHALLOW`: Before emotional sentences
- `INHALE_QUICK`: Before lists
- `EXHALE_SETTLING`: After significant statements
- `EXHALE_RELIEF`: After emotional content
- `MICRO_BREATH`: Random every 15-25 seconds

**Synthesis:**
- **Recorded samples:** 20+ from `assets/breaths/`
- **Fallback:** Filtered noise (150-3000 Hz bandpass for inhale, 100-2000 Hz for exhale)
- **Volume:** 15-25% of speech level
- **Fade:** 10ms in/out for imperceptibility

**Timing Rules:**
- Minimum 15s between micro-breaths
- Jitter: ±5s to avoid robotic periodicity
- Syncs with rhythm entrainment targets

---

### 5. **Filler Engine** (`voice/filler_engine.py`)

**Purpose:** Eliminate dead silence during LLM processing latency

**Categories:**
- **IMMEDIATE (0-100ms):** Breath intake, "hmm..."
- **SHORT (100-500ms):** "let me think", "good question"
- **MEDIUM (500-1.5s):** "that's a good point, let me think"
- **LONG (>1.5s):** "give me just a second on that"

**Pre-rendered at startup:** Zero TTS latency during conversation

**Rules:**
- Never same filler twice in 5-minute window
- Duration must not exceed actual processing time
- Blends into first word of real response via crossfade
- 20-filler recent history deque

**Synthesis Fallback:**
- Breath: 0.4s filtered noise, 200-2500 Hz bandpass
- "Hmm": Fundamental 140 Hz with harmonics, 15 Hz/s downward contour

---

### 6. **Voice Engine Pipeline** (`voice_engine/pipeline.py`)

**Flow:**
```
Audio (16kHz mono) → STT → LLM streaming → Sentence collector → TTS → Audio (24kHz)
```

**Streaming Architecture:**
- **Token-level:** LLM tokens collected by `SentenceCollector`
- **Sentence-level TTS:** Each sentence synthesized immediately
- **No buffering:** First sentence plays while LLM still generating rest

**Interruption Handling:**
- `InterruptionHandler.wrap_stream()` monitors for barge-in
- Raises `asyncio.CancelledError` on interrupt
- Partial response still committed to history

**Conversation History:**
```python
[
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
]
```

---

### 7. **Voice Conversation FSM** (`voice_engine/conversation.py`)

**States:**
```
IDLE → LISTENING → PROCESSING → RESPONDING
```

**Components:**
- **VAD:** Silero (threshold configurable)
- **Microphone:** 16kHz streaming via `MicrophoneStream`
- **Speaker:** sounddevice output with device selection
- **Interruption:** Barge-in detection while PROCESSING/RESPONDING

**Barge-in Behavior:**
```python
if speech_detected and state in (PROCESSING, RESPONDING):
    interrupt_response()
    cancel_speaker()
    cancel_process_task()
    transition_to(LISTENING)
    clear_buffers()
```

**Speech Accumulation:**
- **Min speech:** `min_speech_ms` samples (default 500ms)
- **Min silence:** `min_silence_ms` samples (default 700ms)
- **Fire-and-forget processing:** Mic loop continues during LLM+TTS

---

## 🎯 CONVERSATION ORCHESTRATION

### 1. **Turn Detection Engine** (`conversation/turn_detector.py`)

**Multi-Signal Fusion (14 signals):**

| Signal | Weight | Purpose |
|--------|--------|---------|
| `final_intonation` | 0.22 | F0 trajectory (falling/rising/level) |
| `syntactic_completeness` | 0.20 | Grammar parse completion |
| `breath_detected` | 0.15 | Post-utterance breath pause |
| `silence_duration` | 0.10 | Pause quality (breath/unfilled/filled) |
| `final_lengthening` | 0.08 | Last syllable duration stretch |
| `discourse_marker` | 0.07 | "so", "anyway", "right" |
| `question_detected` | 0.06 | Interrogative syntax + rising F0 |
| `energy_decay` | 0.04 | Volume drop at utterance end |
| `backchannel_elicitor` | 0.03 | Phrases inviting "mmhm" |
| `glottalization` | 0.02 | Creaky voice at phrase end |
| `topic_exhaustion` | 0.01 | Repetition / summarization |
| `gaze_shift` | 0.01 | (Reserved for vision) |
| `gesture_completion` | 0.01 | (Reserved for vision) |

**Actions:**
- **RESPOND** (score ≥ 0.85): Full turn taken
- **BACKCHANNEL** (0.45-0.85): "mmhm", "right"
- **YIELD_AND_RESPOND** (≥0.95 while Emily speaking): Cooperative overlap
- **LISTEN** (<0.45): Continue listening

**Zero hard-coded silence timers** — all timing via signal fusion

---

### 2. **Interrupt Handler** (`conversation/interrupt_handler.py`)

**Interruption Types:**
- `COOPERATIVE_OVERLAP`: User completing Emily's sentence
- `CONTENT_INTERRUPT`: User has new topic
- `CLARIFICATION`: "wait, what do you mean..."
- `CORRECTION`: "no, that's wrong"
- `URGENCY`: High energy, short latency
- `DISENGAGEMENT`: Low energy, discourse markers

**Graceful Behavior:**
- **Never cuts mid-word:** Finds word boundary in 300ms lookahead
- **Audio fade:** 20ms fade-out at stop point
- **Acknowledgments:** "oh—", "sure—", "my mistake" (type-dependent)
- **Context preservation:** Stores interrupted response for potential resumption

**Resumption Phrases:**
- "anyway, as I was saying"
- "so as I mentioned"
- "going back to what I was saying"

**Expiry:** 30s (configurable)

---

### 3. **Rhythm Synchronization** (`conversation/rhythm_sync.py`)

**Tracked Parameters:**
- Speaking rate (syllables/sec)
- Pause duration (ms)
- Phrase length (words)
- Response latency (inter-turn gap)
- Breathing rhythm (seconds)

**Entrainment Algorithm:**
```python
target = baseline * (1 - degree) + user_profile * degree
# degree = 0.4 by default (40% mirroring)
```

**Research Basis:** Communication Accommodation Theory — entrainment increases perceived likability, trust, intelligence

**Cross-Session Memory:** Export/import rhythm profiles per user

**EMA Smoothing:** Alpha = 0.05, 60s window

---

### 4. **Backchannel Engine** (`conversation/backchannel.py`)

**Types:**
- `CONTINUER`: "mmhm", "yeah", "right" (upspeak prosody)
- `ACKNOWLEDGMENT`: "I see", "got it", "okay" (flat)
- `AGREEMENT`: "exactly", "absolutely", "for sure"
- `EMPATHY`: "oh wow", "that makes sense", "I understand"
- `SURPRISE`: "oh really?", "huh", "no way"
- `COMPLETION`: "right", "makes sense", "naturally"

**Rules:**
- Max 1 per 4 seconds
- Volume: 30-40% of normal speech
- **Never overlap stressed syllables** (prosody.stress_pattern check)
- Must fire at phrase boundaries (pause_type in {breath, filled, silence})
- No token repetition in last 10 backchannels

**Synthesis:**
- Pre-recorded samples from `assets/backchannels/`
- TTS fallback with appropriate prosody

---

### 5. **Master Conversation FSM** (`conversation/fsm.py`)

**100Hz Main Loop** coordinating:
- Audio capture (AEC, noise suppression)
- VAD (Silero)
- Streaming STT
- Prosody analysis
- Emotion detection
- Turn detection
- Backchannel generation
- LLM orchestration
- TTS streaming
- Interrupt handling
- Rhythm/emotion synchronization

**Speaking Gate:**
```python
_emily_speaking: bool          # True while TTS active
_post_speech_holdoff_until: float  # AEC convergence delay

# Suppress STT input and IDLE→LISTENING transitions
# until AEC filter converges post-TTS
```

**Interrupt Detection:**
```python
if user_energy > adaptive_threshold and emily_speaking:
    if time.monotonic() > last_interrupt + cooldown_s:
        interrupt_response()
```

**Adaptive Threshold:** Tracks noise floor with EMA (alpha=0.01, 100-sample warmup)

**Cooldown:** 300ms post-interrupt to prevent re-trigger on fading audio

---

## 🔧 KEY INTEGRATIONS

### **LLM Fleet → Voice**
```python
EmilyLLMProvider(fleet, memory, prompt_builder)
# Routes voice LLM calls through Emily's main brain
# Includes persona, memory retrieval, tool access
```

### **TTS Manager → Voice Engine**
```python
EmilyTTSProvider(tts_manager)
# Reuses already-loaded Kokoro instance
# Shares warm GPU models between REST API and voice
```

### **Agent Bus → TTS**
```python
agent_bus.register_handler("tts", _handle_tts_message)
# Agents can send TTS requests via message bus
# {"type": "speak", "payload": {"text": "..."}}
```

### **Brain Hub → Dashboard**
```python
# All voice events mirrored to GUI:
hub.emit("perception", "audio.speech_detected", {...})
hub.emit("fsm", "state_change", {"old": "IDLE", "new": "LISTENING"})
hub.emit("llm", "token", {"text": "hello", "model": "llama3.2"})
```

---

## 📊 PERFORMANCE CHARACTERISTICS

### **Latency Budget**
- **STT:** <100ms (Whisper Turbo / Distil-Whisper)
- **LLM First Token:** <200ms (speculative sampling, KV cache)
- **TTS First Audio:** <50ms (Kokoro) / 200ms (XTTS)
- **Turn Detection:** 10ms inference per signal fusion
- **Total Pipeline:** 350-500ms (competitive with human response time)

### **Concurrency**
- Mic loop: 100Hz (10ms chunks)
- State machine: 100Hz
- LLM streaming: Token-by-token
- TTS streaming: Sentence-by-sentence
- All pipelines concurrent via asyncio

### **Resource Constraints**
- Memory: Ring buffer 1000 events, deques limited (20-100 samples)
- CPU: scipy filters (breath/filler), prosody analysis
- GPU: XTTS optional, Kokoro can run CPU

---

## 🎯 DESIGN PATTERNS

### 1. **Composition Root**
- Bootstrap owns all subsystems
- Dependency injection via `configure(**modules)`
- No global singletons except BrainHub (optional)

### 2. **Async-First**
- All I/O async (ZMQ, LLM, TTS, audio)
- asyncio.Queue for inter-task communication
- Fire-and-forget tasks for non-blocking operations

### 3. **Observer Pattern**
- FSM transition callbacks
- Brain Hub event mirroring
- Agent bus message routing

### 4. **Strategy Pattern**
- TTSEngine abstract base
- Multiple engines (Kokoro, XTTS, CSM) with fallback priority

### 5. **State Machine**
- Explicit state transitions with validation
- Event-driven state changes
- History tracking for debugging

### 6. **Message Bus**
- ZeroMQ PUB/SUB for fan-out (perception)
- ZeroMQ PUSH/PULL for load-balancing (agents)
- Priority queue for task scheduling

---

## 🚨 FAILURE MODES & RESILIENCE

### **Graceful Degradation**
1. **Vision pipeline failure** → Logs warning, continues without vision
2. **TTS engine failure** → Falls back to next priority engine
3. **Spacy import failure** → Kokoro uses espeak-only pipeline
4. **sounddevice unavailable** → Logs warning, discards audio
5. **Signal handlers fail** (non-main thread) → Qt handles quit instead

### **Error Recovery**
- FSM has ERROR state with valid transitions back to IDLE
- Agent message handlers wrapped in try/except
- Perception bus `iter_events()` catches exceptions, logs, sleeps 100ms
- Scheduler deadline enforcement cancels hung tasks

### **Backpressure**
- AudioOutputStream playback queue max 50 chunks
- Scheduler concurrency caps per priority tier
- Agent queue depth tracked in metrics

---

## 📈 OBSERVABILITY

### **Metrics (Prometheus)**
- `agent_queue_depth`: Current tasks in agent bus
- `tts_first_audio_latency`: Per-engine histogram
- All via `observability/metrics.py`

### **Logging (structlog)**
- Contextual fields on every log line
- Configurable level and format
- Rate-limited logs (50/sec) to BrainHub

### **Tracing (OpenTelemetry)**
- Service name: "emily"
- OTLP endpoint configurable
- Can be disabled

---

## 🎯 SUMMARY

**Emily's core is a distributed async event-driven architecture:**
- **ZeroMQ buses** for perception and agent communication
- **Priority scheduler** with concurrency limits
- **FSM** enforcing valid state transitions
- **Brain Hub** mirroring all events to GUI

**Emily's voice is a human-mirroring conversational engine:**
- **Multi-signal turn detection** (no hard-coded silence timers)
- **Rhythm entrainment** (speaking rate, pause, breath sync)
- **Graceful interruption** (never cuts mid-word, acknowledges context)
- **Backchannel generation** (active listening vocalizations)
- **Dynamic prosody** (emotion, semantics, position-aware)
- **True streaming** (plays first sentence while LLM generates rest)

**The two systems integrate seamlessly:**
- Voice LLM calls route through Emily's brain (memory, tools, persona)
- TTS instances shared between API and voice
- All voice events mirrored to dashboard
- Agent bus enables TTS requests from any agent

**Zero hard-coded AI behaviors** — everything driven by signal fusion, learned patterns, and adaptive thresholds.

---

**Next Recommended Actions:**
1. Profile latency under load (100Hz FSM + concurrent LLM)
2. Tune adaptive interrupt threshold per environment
3. Add vision integration to turn detector (gaze, gesture)
4. Benchmark Kokoro vs XTTS quality with A/B tests
5. Cross-session rhythm profile persistence (user ID → episodic memory)
