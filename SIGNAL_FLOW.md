# Emily — Voice Engine Signal Flow

> Complete audio signal chain with sample rates, buffer sizes, and data formats.

---

## Full-Duplex Audio Bus

Input and output streams run as independent async pipelines on separate threads.
They never block each other. The AEC reference signal is the only coupling point.

```
                    ┌─────── INPUT PATH ────────┐
                    │                            │
    Microphone      │    48 kHz / float32        │
        │           │    10ms chunks (480 smp)   │
        ▼           │    Ring buffer: 30s        │
    ┌────────┐      │                            │
    │  ADC   │──────┘                            │
    └────┬───┘                                   │
         │ 48 kHz float32                        │
         ▼                                       │
    ┌────────────┐                               │
    │ Ring Buffer │  2,880 chunks (30s @ 10ms)   │
    │ (lock-free) │                              │
    └────┬───────┘                               │
         │                                       │
         ▼                 ┌──────────┐          │
    ┌─────────┐            │  AEC Ref  │◄────────┼──── from Output Path
    │   AEC   │◄───────────┤  (loopback)│         │
    └────┬────┘            └──────────┘          │
         │ 48 kHz float32 (echo-cancelled)       │
         ▼                                       │
    ┌──────────────┐                             │
    │ Noise Suppress│                            │
    │ RNNoise (CPU) │  < 1ms latency             │
    │ +DeepFilter   │  ~ 5ms (GPU, if SNR < 15) │
    └────┬─────────┘                             │
         │ 48 kHz float32                        │
         ▼                                       │
    ┌──────┐                                     │
    │ AGC  │  Normalize to -20 dBFS target       │
    └──┬───┘                                     │
       │ 48 kHz float32                          │
       ▼                                         │
    ┌────────────┐                               │
    │ Downsample │  48 kHz → 16 kHz              │
    │  (for STT) │  Anti-aliasing filter         │
    └────┬───────┘                               │
         │ 16 kHz float32                        │
         ▼                                       │
    ┌───────────────┐                            │
    │ Speaker Engine │  pyannote + ECAPA-TDNN    │
    │   (20ms)       │  Who is speaking?         │
    └────┬──────────┘                            │
         │ 16 kHz float32 (per-speaker)          │
         ├──────────────────────┐                │
         ▼                      ▼                │
    ┌──────────┐          ┌──────────┐           │
    │ Silero   │          │ Streaming│           │
    │ VAD      │          │ STT      │           │
    │ (< 1ms)  │          │ (50ms)   │           │
    └────┬─────┘          └────┬─────┘           │
         │ speech prob         │ partial text    │
         ▼                     ▼                 │
    ┌──────────────────────────────────┐         │
    │        Prosody Analyzer          │         │
    │  F0, energy, rate, voice quality │         │
    │  parselmouth (< 5ms)             │         │
    └────┬─────────────────────────────┘         │
         │                                       │
         ▼                                       │
    ┌──────────────────────────────────┐         │
    │       Emotion Detector           │         │
    │  Prosody → valence/arousal       │         │
    │  (< 10ms)                        │         │
    └────┬─────────────────────────────┘         │
         │                                       │
         ▼                                       │
    ┌──────────────────────────────────┐         │
    │    Turn Detection Fusion         │         │
    │  14 signals → RESPOND/LISTEN/    │         │
    │  BACKCHANNEL (< 10ms)            │         │
    └────┬─────────────────────────────┘         │
         │ TurnSignal                            │
         └───────────────────────────────────────┘


                    ┌─────── CONVERSATION ENGINE ───────┐
                    │                                    │
    TurnSignal ─────┤                                    │
                    │  ┌──────────────┐                  │
                    ├─►│ Turn Manager  │                  │
                    │  └──────┬───────┘                  │
                    │         │                          │
                    │  ┌──────┴──────────────────────┐   │
                    │  │                             │   │
                    │  ▼                             ▼   │
                    │  ┌────────────┐  ┌─────────────┐  │
                    │  │ Interrupt  │  │ Backchannel  │  │
                    │  │ Handler    │  │ Generator    │  │
                    │  └────────────┘  └──────┬──────┘  │
                    │                          │         │
                    │  ┌────────────┐          │         │
                    │  │ Rhythm Sync│          │         │
                    │  └────────────┘          │         │
                    │                          │         │
                    │  ┌──────────────────┐    │         │
                    │  │ LLM Orchestrator │    │         │
                    │  │ (streaming)      │    │         │
                    │  └───────┬──────────┘    │         │
                    │          │ tokens         │         │
                    │          ▼                │         │
                    │  ┌────────────────┐       │         │
                    │  │Sentence Chunker│       │         │
                    │  └───────┬────────┘       │         │
                    │          │ sentences       │         │
                    │          ▼                │         │
                    │  ┌───────────────┐        │         │
                    │  │Prosody Planner│        │         │
                    │  └───────┬───────┘        │         │
                    │          │ annotated       │         │
                    │          │ sentences       │         │
                    │          │                │         │
                    └──────────┼────────────────┼─────────┘
                               │                │
                               ▼                ▼

                    ┌─────── OUTPUT PATH ────────┐
                    │                            │
                    │  ┌──────────────┐          │
                    │  │ TTS Engine   │          │
                    │  │ XTTS/Kokoro  │          │
                    │  │ 24 kHz int16 │          │
                    │  └──────┬───────┘          │
                    │         │                  │
                    │         ▼                  │
                    │  ┌──────────────┐          │
                    │  │Breath Inject │          │
                    │  └──────┬───────┘          │
                    │         │                  │
                    │         ▼                  │
                    │  ┌──────────────┐          │
                    │  │Filler Engine │          │
                    │  │(pre-rendered)│          │
                    │  └──────┬───────┘          │
                    │         │                  │
                    │         ▼                  │
                    │  ┌──────────────┐          │
                    │  │Output Buffer │          │
                    │  │ Ring buffer   │          │
                    │  │ 24 kHz int16 │          │
                    │  └──────┬───────┘          │
                    │         │                  │
                    │         ▼                  │
                    │  ┌──────────────┐          │
                    │  │   DAC        │──────────┼──► AEC Reference
                    │  │  Speaker     │          │    (loopback)
                    │  └──────────────┘          │
                    │                            │
                    └────────────────────────────┘
```

## Sample Rate Summary

| Stage | Sample Rate | Format | Justification |
|-------|-------------|--------|---------------|
| Mic ADC | 48 kHz | float32 | Maximum quality capture |
| AEC processing | 48 kHz | float32 | Must match capture rate |
| Noise suppress | 48 kHz | float32 | Operates on full-bandwidth |
| STT input | 16 kHz | float32 | Whisper native rate |
| Prosody analysis | 16 kHz | float32 | Sufficient for F0 extraction |
| TTS output | 24 kHz | int16 | XTTS v2 / Kokoro native rate |
| Speaker output | 24 kHz | int16 | Matches TTS |
| AEC reference | 24 kHz → 48 kHz | float32 | Upsampled to match input |

## Buffer Sizes

| Buffer | Size | Duration | Purpose |
|--------|------|----------|---------|
| Input ring | 144,000 samples | 30s @ 48 kHz | Absorb processing spikes |
| Output ring | 72,000 samples | 3s @ 24 kHz | Smooth playback |
| AEC reference | 7,200 samples | 150ms @ 48 kHz | Room echo tail |
| STT partial | 16,000 samples | 1s @ 16 kHz | Sliding window |
| Prosody window | 8,000 samples | 500ms @ 16 kHz | F0 trajectory |

## Thread Model

| Thread | Priority | CPU Affinity | Role |
|--------|----------|-------------|------|
| Audio capture | SCHED_FIFO | Core 0 | sounddevice callback |
| Audio output | SCHED_FIFO | Core 1 | Playback ring drain |
| AEC + noise | Normal | Any | Signal processing |
| Perception | Normal | Any | VAD, STT, prosody |
| Conversation | Normal | Any | FSM, turn detection |
| LLM inference | Normal | Any | Ollama HTTP calls |
| TTS synthesis | Normal | Any | XTTS/Kokoro inference |

## Data Types

All internal audio processing uses **numpy float32** normalized to [-1.0, 1.0].
Conversion to int16 happens only at the DAC output stage.

```python
AudioChunk:
    data: np.ndarray    # float32, shape (samples,)
    timestamp: float    # time.monotonic()
    sample_rate: int    # Hz
    channels: int       # 1 (mono after processing)
```
