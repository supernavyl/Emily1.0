# Emily — Voice Engine Timing Model

> Exact latency budget breakdown per component.

---

## Target

**500ms** from end of user turn to first Emily audio output.

This is generous compared to human response latency (200-350ms) and allows
speculative pre-generation to bring effective latency below 300ms.

## Budget Breakdown

| Stage | Budget | Fallback if exceeded |
|-------|--------|----------------------|
| AEC + Noise suppress | <= 5ms | Skip noise suppression |
| VAD decision | <= 5ms | Use raw speech probability |
| Speaker ID | <= 20ms | Label as "unknown" |
| Turn detection fusion | <= 10ms | Use silence-only signal |
| STT partial → final commit | <= 50ms | Use partial hypothesis |
| Filler audio start | <= 50ms | Skip filler |
| LLM first token | <= 300ms | Switch to fast model |
| TTS first chunk render | <= 100ms | Use Kokoro fallback |
| Audio output start | <= 10ms | Direct buffer flush |
| **Total worst case** | **~450ms** | |

## Speculative Pre-generation

When turn completion probability reaches 0.65 (below the 0.85 response threshold),
the LLM begins generating speculatively with the partial transcript.

- If turn ends and full transcript matches speculation: use cached tokens
- If transcript diverges > 20% edit distance: discard and regenerate
- Expected latency saving: 100-200ms per response

With speculation active, effective perceived latency drops to **250-350ms**.

## Processing Timeline (typical response)

```
t=0ms    User stops speaking (turn detected at 0.85 confidence)
t=5ms    AEC + noise suppress complete
t=10ms   Turn detection fusion confirms RESPOND action
t=15ms   STT commits final transcript
t=50ms   Filler audio begins playing (breath intake or "hmm")
t=150ms  LLM first token arrives (may be from speculative cache)
t=250ms  First sentence complete, TTS begins synthesis
t=350ms  First TTS audio chunk reaches output buffer
t=360ms  Emily's voice starts playing
```

## Processing Timeline (with speculation)

```
t=-200ms Turn probability reaches 0.65, speculative generation starts
t=0ms    User stops speaking
t=5ms    AEC + noise suppress
t=10ms   Turn detection confirms RESPOND
t=15ms   STT commits final transcript, matches speculation
t=50ms   Filler plays while TTS renders first sentence
t=150ms  First TTS audio chunk ready (sentence was pre-generated)
t=160ms  Emily's voice starts playing
```

## Real-time Constraints

- Audio capture thread: `SCHED_FIFO` priority, zero disk/network I/O
- 10ms processing loop (100 Hz) for all perception and conversation modules
- Ring buffers for both input (30s) and output to absorb processing spikes
- All ML inference runs in thread pools to avoid blocking the event loop

## Monitoring

- Per-stage P50/P95/P99 latency tracked via Prometheus histograms
- Latency budget violations logged with `structlog` at WARNING level
- Automated regression test suite: any commit that increases P95 by > 10% fails

## Fallback Cascade

When a stage exceeds its budget:

1. Log warning with stage name, actual latency, budget
2. Return graceful fallback (see table above)
3. If a stage exceeds budget 3x in 60 seconds, disable it for 30s and use fallback exclusively
4. Alert user via UI status indicator
