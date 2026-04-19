# Emily Dual-GPU Voice: Qwen3-Abliterated + Orpheus TTS

**Date:** 2026-04-19 (revised)
**Status:** Design — awaiting approval (v2, reality-synced)
**Author:** supernovyl (via Claude Opus 4.7)
**Supersedes:** ADR 2026-04-16 (Ollama-only single-4090 — written when 3060 was assumed dead)

---

## 1. Context

Emily's voice path currently runs on a single 4090 with two resident models — Qwen3.5-abliterated 9B (`voice_fast`, pinned) and JOSIEFIED-Qwen3 14B (`fast`, co-resident) — plus Faster-Whisper STT and Kokoro TTS on CPU. The RTX 3060 was declared dead 2026-04-16 (Xid 79) but **has recovered** as of 2026-04-19: `nvidia-smi` confirms both GPUs live, no recent Xid errors, embedding model (qwen3-embedding 8B, ~5GB) already resident on it.

Emily has all Orpheus pre-requisites staged but unused: `orpheus-3b-0.1-ft-q4_k_m.gguf` (2.4GB GGUF) is on disk in `models/`, `snac 1.2.1` is installed in the venv, and the TTS factory architecture is in place — but no `OrpheusTTS` provider class exists yet. `llama-cpp-python` is not installed. Kokoro is currently primary.

This design:
1. Makes Orpheus the primary voice TTS via a new `orpheus_tts.py` provider using **llama-cpp-python + SNAC in-process** (no separate server).
2. Upgrades the voice LLM to **Qwen3-30B-A3B-abliterated Q4_K_M MoE** via existing Ollama — huihui-ai publishes this model and Ollama is the already-functioning backend. MoE gives 30B quality at ~3B active-params inference cost (~120 tok/s on 4090).
3. Partitions the GPUs: 4090 = voice LLM only; 3060 = embedding (existing) + Orpheus + Whisper.

Kokoro stays as fallback. 14B `fast` tier and all text-chat tiers (27B/30B code/32B reasoning) are untouched.

## 2. Goals

1. **Promote Orpheus to primary TTS** — emotional, prosodic voice; sentence-level streaming.
2. **Upgrade voice LLM** to Qwen3-30B-A3B-abliterated (MoE, ~120 tok/s on 4090).
3. **GPU partition** — voice LLM alone on 4090, STT + TTS on 3060 alongside the already-resident embedding model.
4. **Latency SLO** — p50 end-of-speech → first-audio ≤ 1.0 s; p95 ≤ 1.6 s. Stretch p50 ≤ 800 ms on cache-warm paths.
5. **Non-destructive** — Kokoro fallback preserved; 14B `fast` tier preserved; text-chat tiers untouched; rollback via single env flag.

## 3. Non-Goals

- Replacing the text-chat fleet or embedding model.
- Voice cloning / speaker enrollment (v2).
- Multilingual tuning (English-first; other languages work but aren't tuned).
- Moving off Ollama. TabbyAPI remains "available but not running" per current CLAUDE.md.
- Changes to `conversation/fsm.py` AEC path, PerceptionBus, or Brain Dashboard.

## 4. GPU Partition

| GPU | VRAM | Workloads | Sizes | Total | Headroom |
|-----|------|-----------|-------|-------|----------|
| **RTX 4090 (CUDA:0)** | 24 GB | Qwen3-30B-A3B-abliterated Q4_K_M via Ollama (voice LLM) | ~18 GB | 18 GB | ~6 GB |
| **RTX 3060 (CUDA:1)** | 12 GB | qwen3-embedding 8B Q4 (existing) + Orpheus-3B-0.1-ft Q4_K_M + Faster-Whisper large-v3 int8 | 5 + 3.5 + 2 GB | **10.5 GB** | **1.5 GB** |

**3060 budget is tight.** Mitigations:
- Orpheus KV cache capped by short TTS context (sentences, not prompts). Peak usage well under theoretical.
- Whisper int8 is modest (~1.6–2.0 GB). Can downshift to `distil-large-v3 int8` (~1 GB) if tight.
- If 3060 OOMs in production: first mitigation is moving embedding back to 4090 (embedding use is sparse, VRAM cost ~5 GB but 4090 has headroom). Documented fallback in Risk R3.

**4090 trade-off:** 30B-A3B replaces the 9B `voice_fast` tier. The 14B `fast` tier **cannot stay co-resident** (30B-A3B + 14B ≈ 29 GB > 24 GB). Ollama will swap 14B in/out when text chat needs it; voice path stays hot. This is an acceptable ~1–2 s swap on text-chat-first-use.

## 5. Inference Backend Decisions

| Component | Backend | Rationale |
|-----------|---------|-----------|
| Voice LLM | **Ollama** (existing) running `huihui_ai/qwen3-abliterated:30b-a3b-q4_K_M` (or equivalent published tag) | Zero backend change. Already integrated via `llm/client.py`. ModelRouter + LLMFleet work unchanged. Just swap the tier model name. |
| Orpheus TTS | **llama-cpp-python** (in-process) + **SNAC** (in-process, CPU or CUDA:1) | GGUF is already on disk. `snac` already installed. Single Python process, no HTTP hop, simpler than vLLM/llama-server for this workload. Streams tokens → decoder → PCM frames. |
| STT | **Faster-Whisper** (existing) pinned to CUDA:1 via `device_index=1` | Existing `faster_whisper.py` provider already supports this param. Config-only change. |
| Text-chat tiers | **Ollama** (unchanged) | Explicit non-goal. |

**Why not vLLM / TabbyAPI / llama-server:**
- vLLM: GGUF support limited; needs HF-format weights; adds a new service. Not worth it for one model.
- TabbyAPI: Not running per CLAUDE.md. Adding it is a separate project.
- llama-server: Extra HTTP hop vs. in-process. Only a win if we need to share the model across processes — we don't.

**Why llama-cpp-python vs. using Ollama to serve Orpheus:**
Ollama doesn't expose raw token logits or custom audio-token streaming — it's text-only. Orpheus emits SNAC audio tokens that must be routed to the SNAC decoder, not detokenized to text. llama-cpp-python gives us the raw stream.

## 6. Process Topology

```
┌──── host: supernovanyl ─────────────────────────────────────────────┐
│                                                                      │
│  Ollama server (existing, systemd ollama.service):                  │
│  ├─ voice_fast tier: huihui Qwen3-30B-A3B abliterated (4090, pin)   │
│  ├─ fast tier: JOSIEFIED-Qwen3 14B (swap in/out)                    │
│  ├─ embedding tier: qwen3-embedding 8B (3060, always resident)      │
│  └─ (unchanged heavy tiers: 27B/30B-code/32B-reasoning on swap)     │
│                                                                      │
│  Emily main process (emily.service → emily_server.py):              │
│  ├─ FasterWhisperSTT     device_index=1  (CUDA:1)                   │
│  ├─ EmilyLLMProvider     → Ollama HTTP → voice_fast tier            │
│  ├─ OrpheusTTS (new)     llama-cpp-python + SNAC, main_gpu=1        │
│  └─ KokoroTTS            CPU fallback (unchanged)                   │
│                                                                      │
│  No new systemd units. No new services. One new Python module.      │
└──────────────────────────────────────────────────────────────────────┘
```

## 7. Streaming Pipeline (existing path, minimal changes)

```
MicrophoneStream
  → SileroVAD
  → FasterWhisperSTT (CUDA:1 pinned)
  → EmilyLLMProvider (Ollama, voice tier = Qwen3-30B-A3B-abliterated)
  → VoicePipeline.process_streaming (existing sentence boundary splitter)
  → OrpheusTTS.synthesize_stream  (new)
      → llama-cpp-python: text → Orpheus SNAC audio token codes
      → SNAC decoder: 7 codes/frame → 24 kHz float32 PCM
      → yield np.ndarray per sentence (base class contract)
  → Speaker playback (existing)
```

**Barge-in:** already handled by `InterruptionHandler` in `conversation/fsm.py`. OrpheusTTS must respect `asyncio.CancelledError` during `synthesize_stream` and flush any in-flight llama-cpp generation.

## 8. Latency Budget (conservative first)

| Stage | p50 | p95 | Notes |
|-------|-----|-----|-------|
| VAD cutoff | 200 ms | 300 ms | `min_silence_ms` existing config |
| Whisper final | 180 ms | 280 ms | distil-large-v3 int8 on 3060 |
| Ollama first token | 100 ms | 180 ms | 30B-A3B MoE prefill — 3B active, very fast |
| First sentence complete | 160 ms | 300 ms | ~15–25 tokens @ ~120 tok/s |
| Orpheus first audio | 300 ms | 450 ms | llama-cpp-python first token + SNAC decode on 3060 |
| **Total (silence → first audible word)** | **~940 ms** | **~1.5 s** | |

Over-SLO triggers:
- p50 > 1.0 s for 10 consecutive turns → log warning + Brain dashboard alert
- p95 > 2.0 s sustained → auto-fallback to Kokoro for next turn

## 9. New Components (minimal surface area)

### 9.1 `voice_engine/providers/tts/orpheus_tts.py` (new — primary deliverable)

- Class `OrpheusTTS(TTSProvider)` — implements `base.py` contract exactly: `synthesize(text) → np.ndarray` and `synthesize_stream(text_chunks) → AsyncIterator[np.ndarray]`.
- Config: `model_path`, `voice` (e.g., `tara`), `main_gpu` (1), `n_gpu_layers` (-1), `temperature` (0.6), `top_p` (0.9), `repetition_penalty` (1.1), `max_tokens` (1200).
- Constructor: lazy-loads `llama_cpp.Llama(model_path, n_gpu_layers=-1, main_gpu=1, logits_all=False, verbose=False)`. Lazy-load matches Kokoro's pattern.
- Loads SNAC once: `SNAC.from_pretrained("hubertsiuzdak/snac_24khz").to("cuda:1")` (or CPU fallback — benchmark at M5).
- Orpheus prompt format: `"<custom_token_3><|audio|>{voice}: {text}<|eot|>"` (per Canopy Labs card).
- Token → audio: accumulate SNAC codes in buffers of 7 (Orpheus frame size), decode on each full frame, convert to int16 PCM, then float32 for base class.
- Uses `observability.logger.get_logger(__name__)` per Critical Rule #5.
- No blocking I/O in async hot path: llama-cpp calls wrapped in `asyncio.to_thread()` per Rule #3.

### 9.2 `voice_engine/providers/tts/snac_stream_decoder.py` (new — helper)

- Thin wrapper around SNAC.
- Method: `decode_frame(codes: list[list[int]]) → np.ndarray` — takes 7 SNAC codes per call, returns PCM samples.
- Method: `reset()` — clear any internal state between sentences.
- Device selection: `torch.device("cuda:1")` if available and VRAM permits, else CPU. Benchmark in M5 picks final default.

### 9.3 `voice_engine/providers/factory.py` (modify)

- Register new branch in `create_tts()`:
  ```python
  if name == "orpheus":
      from voice_engine.providers.tts.orpheus_tts import OrpheusTTS
      return OrpheusTTS(
          model_path=config.orpheus_model_path,
          voice=config.tts_voice,
          main_gpu=config.orpheus_main_gpu,
      )
  ```
- Keep existing `kokoro` / `tiered` branches untouched.

### 9.4 `voice_engine/config.py` (modify)

- Add fields to `VoiceEngineConfig`:
  - `orpheus_model_path: str = "models/orpheus-3b-0.1-ft-q4_k_m.gguf"`
  - `orpheus_main_gpu: int = 1`
  - `orpheus_snac_device: str = "cuda:1"`  (or `"cpu"`)
  - `tts_fallback: str = "kokoro"`
- Keep `tts_provider` default behavior; provider chosen via env flag.

### 9.5 `config.yaml` (modify)

- Add:
  ```yaml
  voice_engine:
    tts_provider: orpheus      # was: kokoro
    tts_fallback: kokoro
    tts_voice: tara
    stt_device: cuda
    stt_device_index: 1        # pin Whisper to 3060
    stt_compute_type: int8     # lighter than float16 on 3060
    orpheus_model_path: models/orpheus-3b-0.1-ft-q4_k_m.gguf
    orpheus_main_gpu: 1
    orpheus_snac_device: cuda:1
  ```

### 9.6 `llm/fleet.py` (modify)

- Update `voice_fast` tier model name to the new Qwen3-30B-A3B abliterated tag.
- Keep 30m `keep_alive`.
- Exact tag confirmed at M0 (see R1).

### 9.7 Dependency addition

- Add `llama-cpp-python` with CUDA wheel to `pyproject.toml`:
  - `uv add llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124 --index-strategy unsafe-best-match` (CUDA 12.4; match host).
  - Verify `CUDA_HOME` during build or use pre-built wheels.
- Existing: `snac 1.2.1` already present.

## 10. Env-Var Rollback Flag

- `EMILY_VOICE_TTS=kokoro` → factory returns `KokoroTTS` regardless of config.
- `EMILY_VOICE_TTS=orpheus` → new path (default after this change).
- Evaluated in `emily_server.py` bootstrap, before factory call.

## 11. Integration Points

| File | Change |
|------|--------|
| `voice_engine/providers/tts/orpheus_tts.py` | **NEW** — primary deliverable |
| `voice_engine/providers/tts/snac_stream_decoder.py` | **NEW** — helper |
| `voice_engine/providers/factory.py:95–105` | Add `orpheus` branch |
| `voice_engine/config.py` | Add Orpheus fields |
| `config.yaml` | Add `voice_engine` keys |
| `llm/fleet.py` | Update `voice_fast` model name to Qwen3-30B-A3B abliterated |
| `emily_server.py` | Honor `EMILY_VOICE_TTS` env flag before provider creation |
| `pyproject.toml` | Add `llama-cpp-python` CUDA build |
| `scripts/check_deps.py` | Update — now expected to PASS |
| `scripts/benchmark_voice_dual_gpu.py` | **NEW** — 30-turn latency benchmark |
| `tests/unit/voice_engine/providers/tts/test_orpheus_tts.py` | **NEW** — mocked llama-cpp stream |
| `tests/unit/voice_engine/providers/tts/test_snac_stream_decoder.py` | **NEW** — round-trip on fixture codes |
| `.claude/CLAUDE-decisions.md` | Append ADR for this change |
| `ABLITERATED_SETUP.md` | Update model fleet table |

## 12. Risk Register

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R1 | Ollama doesn't have a `huihui-ai/qwen3-abliterated:30b-a3b` tag — only non-MoE abliterations exist | 35% | Medium | Fallback ladder: (a) pull any `qwen3-abliterated:30b-a3b` variant from Ollama library; (b) manually import GGUF from HuggingFace `bartowski` or `mradermacher` via `ollama create`; (c) drop to `huihui-ai/qwen3-abliterated:14b` (≈11 GB) — still a big voice quality upgrade over current 9B. |
| R2 | `llama-cpp-python` CUDA build fails on Arch (toolchain mismatch) | 25% | High | Use prebuilt CUDA wheel index (abetlen.github.io/llama-cpp-python/whl). If prebuilt missing for Python 3.11+: build from source with `CMAKE_ARGS="-DGGML_CUDA=on"`. Document in M0. |
| R3 | 3060 OOM under combined embedding + Orpheus + Whisper + KV cache spikes | 30% | High | Tight budget (1.5 GB headroom). Move embedding tier to 4090 if OOM seen — 4090 has ~6 GB headroom. Emit dashboard alert on VRAM >90%. |
| R4 | SNAC decode latency on CUDA:1 too high (competing with Orpheus) | 20% | Medium | CPU SNAC path on 7800X3D 16 threads measured against CUDA:1. Pick faster path at M5 via benchmark. |
| R5 | Orpheus prompt format / voice tag regressions between model versions | 15% | Low | Pin exact model file (already present). Voice names validated against Canopy Labs card (`tara`, `leah`, `jess`, `leo`, `dan`, `mia`, `zac`, `zoe`). |
| R6 | 14B `fast` tier eviction creates text-chat cold-start annoyance | 40% | Low | Accept ~2 s swap on first text-chat turn. Swap cost hidden by user typing time. Document in ADR. |
| R7 | 3060 PCIe instability recurs (Xid 79 history) | 20% | High | `scripts/gpu_check.py` already exists. Add 60s poll with auto-fallback: TTS and STT both move to 4090 + CPU. Alert surfaced via Brain dashboard. |
| R8 | Existing `check_deps.py` gating prevents boot if llama-cpp missing | 10% | Low | Install as part of M0 before flipping default. Gate TTS init failure → fallback to Kokoro, not hard crash. |

## 13. Testing Strategy

**Unit (`tests/unit/`):**
- `test_orpheus_tts.py`: mock `llama_cpp.Llama.__call__` returning a fixture token stream; assert `synthesize()` returns non-empty float32 ndarray at 24 kHz.
- `test_orpheus_tts.py::test_stream_cancellation`: cancel mid-synthesis, verify clean asyncio cleanup (no stuck threads).
- `test_snac_stream_decoder.py`: decode a fixture of known SNAC codes; assert PCM length and value range (`[-1, 1]` float32).
- `test_orpheus_tts.py::test_empty_text`: empty/whitespace input → empty ndarray (matches Kokoro).

**Integration (`tests/integration/`, marked `@pytest.mark.integration`):**
- `test_voice_e2e_orpheus.py`: synthetic 3-sec mic input → end-to-end loop → assert audible PCM emitted within SLO.

**Benchmark (`scripts/benchmark_voice_dual_gpu.py`, REQUIRED before merge):**
- 30 turns, fixed prompt set (short, medium, code-heavy, emotional).
- Log per-stage timings to `benchmarks/voice-dual-gpu-YYYY-MM-DD.json`.
- Pass criteria: p50 ≤ 1.0 s, p95 ≤ 1.6 s.

**Smoke (manual, after M5):**
- 5-minute free conversation. Coverage: short Q&A, code dictation, interruption (barge-in), long monologue (>30 s), French↔English switch.
- Subjective A/B: Orpheus vs. Kokoro, same prompts.

## 14. Milestones

| M | Deliverable | Est. |
|---|-------------|------|
| M0 | Install `llama-cpp-python` CUDA wheel; pull Qwen3-30B-A3B-abliterated via Ollama (or fallback); `check_deps.py` green; `nvidia-smi` shows 30B-A3B on 4090. | 0.5 d |
| M1 | Write `snac_stream_decoder.py` + tests; round-trip fixture codes → PCM. | 0.5 d |
| M2 | Write `orpheus_tts.py` + unit tests; standalone `synthesize("hello world")` produces audible WAV. | 1.0 d |
| M3 | Wire factory + config + env flag; pin Whisper to CUDA:1; end-to-end voice turn through `emily_server.py`. | 0.5 d |
| M4 | Barge-in cancellation verified; Kokoro fallback on Orpheus failure; VRAM alert hook. | 0.5 d |
| M5 | `benchmark_voice_dual_gpu.py` runs; SLO met; CPU vs CUDA SNAC decision locked. | 0.5 d |
| M6 | Update `ABLITERATED_SETUP.md`, `.claude/CLAUDE-decisions.md`, `CLAUDE.md` (model fleet table, Critical Rule #15 VRAM budget). | 0.25 d |

**Total:** ~3.75 days of focused work (down from 5.5 in v1 — Orpheus weights already on disk, no new services needed).

## 15. Rollback Plan

1. `export EMILY_VOICE_TTS=kokoro` in systemd env → `systemctl --user restart emily.service`.
2. Kokoro TTS resumes on CPU. Whisper stays on CUDA:1 (no revert needed — device is a config).
3. Revert `llm/fleet.py` voice_fast tier name to previous Qwen3.5-abliterated 9B → restart. (Ollama already has this model.)
4. No code rollback required — all new code is additive + feature-flagged.

## 16. Open Questions

- **SNAC device:** CUDA:1 or CPU? Decided at M5 via benchmark. Default placeholder: CUDA:1.
- **Orpheus voice:** `tara` (default) or user preference post-M5 listening test.
- **Ollama tag availability** for Qwen3-30B-A3B-abliterated: confirmed at M0 or triggers R1 fallback ladder.

## 17. Success Criteria

1. `nvidia-smi` shows: 4090 = only the new voice LLM (+ any leftover 14B swap); 3060 = embedding + Orpheus + Whisper. Zero unintended fragmentation.
2. Benchmark report: p50 ≤ 1.0 s, p95 ≤ 1.6 s over 30 turns.
3. 5-minute free conversation: Orpheus subjectively preferred over Kokoro (n=1 listener).
4. Text-chat regression suite passes — `smart`, `reasoning`, `vision`, `code`, `embedding` tiers unaffected.
5. `EMILY_VOICE_TTS=kokoro` rollback verified on fresh restart.
6. `check_deps.py` green.

---

**Changes from v1:**
- Dropped TabbyAPI migration (Ollama stays).
- Dropped vLLM Orpheus server (in-process llama-cpp-python).
- Dropped new systemd units (no services to add).
- Added explicit 3060 VRAM accounting with embedding model.
- Acknowledged Orpheus GGUF is already on disk + SNAC already installed.
- Added fallback ladder for Qwen3-30B-A3B-abliterated Ollama tag availability.
- Timeline 5.5 d → 3.75 d.

**Next step:** on approval → invoke `superpowers:writing-plans` to produce the task plan mapped to M0–M6.
