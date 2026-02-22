# Emily — Voice Engine Architecture

> Full-duplex, human-like conversational voice system.

---

## Overview

Emily's voice engine transforms a half-duplex walkie-talkie pipeline into a full-duplex
telephone where input and output run simultaneously, backchannels play while the user speaks,
turn completion is detected via multi-signal fusion, and Emily's speech rhythm synchronizes
with the user's.

## Hardware Profile

| Component | Spec |
|-----------|------|
| Mic | Single USB/analog + headset (auto-detect) |
| Speakers | Mono desktop + stereo (configurable) |
| Same device | Yes (AEC mandatory) |
| Room | Small untreated office (~100ms RT60) |
| Noise floor | < 30 dB SPL |
| GPU | RTX 4090, 24 GB VRAM |
| CPU | i9-14900K, 24c/32t |
| RAM | 62 GB DDR5 |

## System Layers

### Layer 0 — Full-Duplex Audio Bus

Input and output run as independent async streams on separate real-time threads
with `SCHED_FIFO` priority. Ring buffers guarantee zero frame drops under any load.

- **Input**: 48 kHz capture → downsample to 16 kHz for STT
- **Output**: 24 kHz for TTS playback
- **AEC reference**: output signal fed back to cancel echo from input
- **Chunk size**: 10ms (480 samples at 48 kHz)

### Layer 1 — Input Processing Chain

```
Mic → Ring Buffer → AEC → Noise Suppress → AGC
    → Speaker Engine → VAD → Streaming STT
    → Prosody Analyzer → Emotion Detector
    → Turn Detection Fusion
```

Each stage runs as an async pipeline element. The AEC module is the most critical —
without it, Emily hears herself and creates feedback spirals.

**Noise Suppression**: Two-stage adaptive.
- Stage 1: RNNoise (CPU, <1ms) — always active
- Stage 2: DeepFilterNet2 (GPU, ~5ms) — activates when SNR < 15 dB

Speech naturalness markers (breaths, lip smacks, hesitation sounds, emotional
voice quality) are protected from suppression.

**Speaker Engine**: pyannote 3.1 diarization + ECAPA-TDNN voiceprints.
Supports 2 simultaneous speakers with individual stream isolation.

### Layer 2 — Perception Analysis

**Streaming STT**: Faster-Whisper large-v3 with dual output:
- Partial hypothesis (updated every chunk) — feeds turn detector and interrupt handler
- Final transcript (committed at turn end) — feeds LLM

**Prosody Analyzer**: Continuous extraction via Praat (parselmouth):
- F0 (pitch), energy, speaking rate, voice quality
- Final lengthening, glottalization, stress patterns
- Per-speaker baselines tracked over sessions

**Emotion Detector**: Prosody-based classification into 10 emotion categories
with valence/arousal/cognitive-load derived signals.

### Layer 3 — Conversation Engine

**Turn Detection**: Multi-signal fusion engine combining up to 14 signals:
- Acoustic: silence quality, intonation, final lengthening, energy decay, breath, glottalization
- Linguistic: syntactic completeness, backchannel elicitors, discourse markers, questions
- Contextual: topic exhaustion, gaze, gesture, response urgency

Weighted fusion with 0.85 response threshold, 0.45 backchannel threshold.

**Interrupt Handler**: Six interrupt types with graceful trail-off:
- Cooperative overlap, content interrupt, clarification, correction, urgency, disengagement
- Finds word boundary within 300ms lookahead, 20ms audio fade
- Preserves response context for resumption

**Backchannel Engine**: Six types (continuer, acknowledgment, agreement, empathy, surprise, completion).
Max 1 per 4 seconds, 30-40% volume, timed to inter-pausal units.

**Rhythm Synchronizer**: Entrainment degree 0.4 — tracks user speaking rate,
pause patterns, response latency. Cross-session memory via episodic store.

**Emotion Sync**: Mirrors positive emotions, calms negative ones. Drives TTS
style parameters (rate, pitch range, energy, warmth, vocabulary complexity).

### Layer 4 — Output Pipeline

```
LLM tokens → Sentence Chunker → Prosody Planner
    → TTS Engine → Breath Injector → Filler Engine
    → Output Buffer → DAC → Speaker
    → AEC Reference (fed back to input)
```

**Filler Engine**: Pre-rendered thinking sounds cover LLM latency.
Categorized by expected processing time (immediate/short/medium/long).
Crossfaded into response start for imperceptible transition.

**Breath Injector**: Realistic breath sounds at natural locations.
20+ breath samples matched to speaking energy level.

**Streaming TTS**: Sentence-level synthesis with full prosody control.
First audio within 100ms of sentence completion.

### Layer 5 — Timing Infrastructure

Every pipeline stage wrapped in a latency budget enforcer.
Exceeded budgets trigger graceful fallbacks, never pipeline freezes.

Target: 500ms perceived response latency (human average: 200-350ms).

## Conversation State Machine

```
IDLE ──► LISTENING ──► PROCESSING ──► SPEAKING
  ▲          │              │              │
  │          ▼              ▼              ▼
  │     BACKCHANNELING  FILLING       INTERRUPTED
  │          │              │              │
  └──────────┴──────────────┴──────────────┘
```

## Integration with Emily Core

The voice engine replaces the linear `_perception_tts_bridge` in `core/bootstrap.py`
with the conversation FSM. The existing perception bus, agent bus, memory system,
LLM fleet, and persona system are reused. The old bridge remains as a fallback
if the voice engine fails to initialize.
