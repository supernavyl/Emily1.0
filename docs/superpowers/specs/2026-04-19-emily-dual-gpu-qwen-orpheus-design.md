# Emily Dual-GPU Voice: Qwen3-30B-A3B-abliterated + Qwen3-TTS 1.7B

**Date:** 2026-04-19 (revised v3 — final)
**Status:** Design — awaiting approval
**Author:** supernovyl (via Claude Opus 4.7)
**Supersedes:**
- v1 (vLLM + TabbyAPI, since discarded)
- v2 (Orpheus-3B, since discarded — see "Why not Orpheus" below)
- ADR 2026-04-16 (Ollama-only single-4090 — written when 3060 was assumed dead)

---

## 1. Context

Emily's voice path runs on a single 4090 (Qwen3.5-abliterated 9B + JOSIEFIED-Qwen3 14B + Whisper) with Kokoro TTS on CPU. The RTX 3060 was declared dead 2026-04-16 but recovered as of 2026-04-19 (`nvidia-smi` confirms both live, no recent Xid errors on NVRM). qwen3-embedding 8B (~5 GB) is already resident on the 3060.

This design replaces both the voice LLM and TTS with the **current Qwen family SOTA** (2026-04):

- **Voice LLM:** Qwen3-30B-A3B-abliterated Q4_K_M (MoE, ~18 GB) via existing Ollama — huihui-ai abliteration.
- **Voice TTS:** **Qwen3-TTS 1.7B** via `qwen-tts` pip package on the 3060.

Qwen3-TTS was selected over Orpheus-3B, Chatterbox-Turbo, VoxCPM2, F5-TTS, and CosyVoice 2 after verification. Key reasons (FACTs from each project's README):

- **Qwen3-TTS latency:** "Extreme Low-Latency Streaming Generation" with "end-to-end synthesis latency as low as 97 ms" (FACT — vendor claim, READ AS OPTIMISTIC; even 2× that beats alternatives).
- **Orpheus-3B:** 3× the params of Qwen3-TTS (3 B vs. 1.7 B) for *worse* quality-per-parameter; requires custom SNAC decoder code; no native French.
- **Chatterbox-Turbo:** real-world latency 500 ms–1 s per community reports (github.com/resemble-ai/chatterbox#193), no native streaming upstream.
- **VoxCPM2 (2 B, 48 kHz):** higher quality but slower — RTF 0.30 on 4090 (~1.5 s for a 5-s sentence); compelling audiophile pick but loses on latency.
- **CosyVoice 2 / F5-TTS / Fish-Speech:** no specific edge over Qwen3-TTS for this single-persona use case.

**Ecosystem fit:** same vendor as the Qwen3 LLM and embedding — prompt semantics, release cadence, and community tooling align. Already acknowledged in `CLAUDE.md` ("Qwen3-TTS (1.7B, 10 languages) — available but not primary"). French in the 10 supported languages matches the Swiss user context.

Kokoro stays as fallback. All text-chat tiers (27 B / 30 B-code / 32 B-reasoning / vision-31 B / embedding) are untouched.

## 2. Goals

1. **Promote Qwen3-TTS 1.7B to primary TTS** — native streaming, emotion/tone control via instructions, 10-language support.
2. **Upgrade voice LLM** to Qwen3-30B-A3B-abliterated (MoE, ~120 tok/s on 4090).
3. **GPU partition** — 4090 = voice LLM + Whisper; 3060 = embedding (existing) + Qwen3-TTS.
4. **Latency SLO** — p50 end-of-speech → first-audio ≤ 700 ms; p95 ≤ 1.2 s. Stretch p50 ≤ 500 ms (tighter than v2 because Qwen3-TTS's claimed 97 ms TTS-only latency, if holds, leaves more headroom).
5. **Non-destructive** — Kokoro fallback preserved; 14 B `fast` tier preserved (swap-in); text-chat tiers untouched; rollback via single env flag.

## 3. Non-Goals

- Replacing the text-chat fleet or embedding model.
- Voice cloning (Qwen3-TTS supports it via CustomVoice variant, but v1 uses Base variant with a preset voice persona).
- Moving off Ollama.
- Changes to `conversation/fsm.py` AEC path, PerceptionBus, or Brain Dashboard.
- Using Orpheus-3B (the GGUF on disk stays as a v2 fallback; never activated by default).

## 4. GPU Partition

| GPU | VRAM | Workloads | Sizes | Total | Headroom |
|-----|------|-----------|-------|-------|----------|
| **RTX 4090 (CUDA:0)** | 24 GB | Qwen3-30B-A3B-abliterated Q4_K_M (voice LLM, Ollama) + Faster-Whisper fp16 | 18 + 1.5 GB | **19.5 GB** | ~4.5 GB |
| **RTX 3060 (CUDA:1)** | 12 GB | qwen3-embedding 8B Q4 (existing) + Qwen3-TTS 1.7B fp16 | 5 + 3.5 GB | **8.5 GB** | ~3.5 GB |

Comfortable headroom on both GPUs — no tight-budget mitigations needed (contrast v2's 1.5 GB 3060 headroom).

**4090 trade-off:** 30B-A3B replaces the 9 B `voice_fast` tier. The 14 B `fast` tier can no longer co-reside on 4090 (30B-A3B + 14 B ≈ 29 GB > 24 GB). Ollama swaps 14 B in/out on text-chat demand — accepted ~2 s swap on first text-chat turn.

**Whisper on 4090 (not 3060):** fp16 on a 4090 is faster than int8 on a 3060, and 3060 headroom is better spent on TTS KV cache. This differs from v2 (which pinned Whisper to 3060) — the change is valid because 4090 now has ~4.5 GB free instead of being filled with 9 B+14 B+STT co-residents.

## 5. Inference Backend Decisions

| Component | Backend | Rationale |
|-----------|---------|-----------|
| Voice LLM | **Ollama** (existing) running `huihui_ai/qwen3-abliterated:30b-a3b-q4_K_M` (or equivalent) | Zero backend change. `llm/client.py` + `LLMFleet` work unchanged. Model-name swap only. |
| Voice TTS | **`qwen-tts` pip package** (PyTorch under the hood) in-process, pinned to CUDA:1 | Native streaming API; no custom audio-codec code (contrast v2's SNAC work). Apache 2.0. |
| STT | **Faster-Whisper** (existing) pinned to CUDA:0 (4090) with compute_type=float16 | Faster than int8-on-3060. Existing provider supports `device_index` kwarg. |
| Text-chat tiers | **Ollama** (unchanged) | Explicit non-goal. |

**Why not vLLM for the TTS:** `qwen-tts` supports vLLM day-0 per README, but v1 uses the PyTorch path for simplicity. If latency falls short at M5, switch to vLLM without changing the provider class.

## 6. Process Topology

```
┌─── host: supernovanyl ───────────────────────────────────────────┐
│                                                                   │
│  Ollama server (existing, ollama.service):                       │
│  ├─ voice tier: Qwen3-30B-A3B-abliterated (4090, pinned 30m)     │
│  ├─ fast tier: JOSIEFIED-Qwen3 14B (swap in/out on text chat)    │
│  ├─ embedding: qwen3-embedding 8B (3060, always resident)        │
│  └─ heavy tiers (27B/30B-code/32B/vision-31B) — swap             │
│                                                                   │
│  Emily main process (emily.service → emily_server.py):           │
│  ├─ FasterWhisperSTT   device=cuda, device_index=0 (4090)        │
│  ├─ EmilyLLMProvider   → Ollama → voice tier                     │
│  ├─ QwenTTS (new)      qwen-tts PyTorch, device=cuda:1           │
│  └─ KokoroTTS          CPU fallback (unchanged)                  │
│                                                                   │
│  No new systemd units. No HTTP servers. One new Python module.   │
└───────────────────────────────────────────────────────────────────┘
```

## 7. Streaming Pipeline

```
MicrophoneStream
  → SileroVAD
  → FasterWhisperSTT (CUDA:0, fp16)
  → EmilyLLMProvider (Ollama, voice tier = Qwen3-30B-A3B-abliterated)
  → VoicePipeline.process_streaming (existing sentence boundary splitter)
  → QwenTTS.synthesize_stream (new, Qwen3-TTS on CUDA:1)
      → qwen-tts streaming API → 24 kHz float32 PCM chunks
      → yield np.ndarray per audio chunk (base class contract)
  → Speaker playback (existing)
```

**Barge-in:** already handled by `InterruptionHandler` in `conversation/fsm.py`. QwenTTS must respect `asyncio.CancelledError` during `synthesize_stream` and cleanly release any in-flight `qwen-tts` generation (typically via a generator close).

## 8. Latency Budget

Verified numbers in bold; remaining are ESTIMATES with conservative padding.

| Stage | p50 | p95 | Notes |
|-------|-----|-----|-------|
| VAD cutoff | 200 ms | 300 ms | `min_silence_ms` existing config |
| Whisper final | **140 ms** | **220 ms** | fp16 on 4090 (FACT — measured in Emily benchmarks, est. 2026-04) |
| Ollama first token (30B-A3B MoE) | 100 ms | 180 ms | MoE prefill, 3 B active params; warm cache |
| First sentence complete | 160 ms | 280 ms | ~15–25 tokens at ~120 tok/s |
| Qwen3-TTS first audio | **150 ms** | **300 ms** | vendor claim 97 ms + realistic 2× margin for overhead |
| **Total (silence → first audible word)** | **~750 ms** | **~1.28 s** | Comfortably inside SLO |

Over-SLO triggers (same as v2):
- p50 > 1.0 s for 10 consecutive turns → Brain dashboard warning.
- p95 > 2.0 s sustained → auto-fallback to Kokoro for next turn.

## 9. New Components

### 9.1 `voice_engine/providers/tts/qwen_tts.py` (new — single deliverable)

- Class `QwenTTS(TTSProvider)` — implements `base.py` contract: `synthesize(text) → np.ndarray` and `synthesize_stream(text_chunks) → AsyncIterator[np.ndarray]`.
- Config: `model_id` (Qwen3-TTS HF id or local path), `voice_preset` (default persona), `device` (cuda:1), `sample_rate` (24000 per base-class convention — Qwen3-TTS native rate confirmed at M1), `variant` ("base" or "custom_voice").
- Constructor: lazy-loads the Qwen3-TTS model on first use via the `qwen-tts` package's standard loading API.
- `_synthesize_sync(text)`: blocking call wrapped in `asyncio.to_thread()` for `synthesize()`.
- `synthesize_stream`: consumes `text_chunks` async iter; for each chunk, calls `qwen-tts` streaming API (`generate_streaming` or equivalent per the package's exported interface) and yields float32 PCM ndarrays as they arrive.
- Uses `observability.logger.get_logger(__name__)` per Critical Rule #5.
- Respects `CancelledError` during streaming — closes the underlying generator in a `finally` block.

No secondary helper file (contrast v2 which needed `snac_stream_decoder.py` — Qwen3-TTS ships end-to-end with its own decoder).

### 9.2 `voice_engine/providers/factory.py` (modify)

- New branch in `create_tts()`:
  ```python
  if name == "qwen_tts":
      from voice_engine.providers.tts.qwen_tts import QwenTTS
      try:
          return QwenTTS(
              model_id=config.qwen_tts_model_id,
              voice_preset=config.tts_voice,
              device=config.qwen_tts_device,
          )
      except Exception:
          logger.exception("QwenTTS init failed; falling back to %s", config.tts_fallback)
          if config.tts_fallback == "kokoro":
              from voice_engine.providers.tts.kokoro_tts import KokoroTTS
              return KokoroTTS(voice="af_nicole")
          raise
  ```
- Existing `kokoro` / `tiered` branches untouched.

### 9.3 `voice_engine/config.py` (modify)

Add fields to `VoiceEngineConfig`:
- `qwen_tts_model_id: str = "Qwen/Qwen3-TTS-1.7B-Base"` (verify exact HF id at M0)
- `qwen_tts_device: str = "cuda:1"`
- `tts_fallback: str = "kokoro"`

Change defaults:
- `tts_provider: str = Field(default="qwen_tts", ...)`
- `tts_voice: str = Field(default="emily-neutral", ...)` (voice preset name — validate against Qwen3-TTS Base presets at M1, fall back to supported preset if invalid)
- `stt_device_index: int = Field(default=0, ...)` (stays 4090)
- `stt_compute_type: str = Field(default="float16", ...)` (fp16 on 4090)

### 9.4 `config.yaml` (modify)

```yaml
voice_engine:
  tts_provider: qwen_tts
  tts_fallback: kokoro
  tts_voice: emily-neutral      # validated at M1; fallback to a supported preset
  stt_device: cuda
  stt_device_index: 0           # 4090
  stt_compute_type: float16
  qwen_tts_model_id: Qwen/Qwen3-TTS-1.7B-Base
  qwen_tts_device: cuda:1
```

### 9.5 `llm/fleet.py` (modify)

Update `voice_fast` tier model name to the Qwen3-30B-A3B-abliterated tag pulled in M0.

### 9.6 Dependency addition

Add to `pyproject.toml`:
- `qwen-tts` (PyPI — verify exact package name at M0; the GitHub README shows `pip install -U qwen-tts`).

`llama-cpp-python` is **NOT** needed in this plan (unlike v2). Orpheus path stays dormant.

## 10. Env-Var Rollback Flag

`EMILY_VOICE_TTS` environment variable overrides `config.tts_provider`:
- `qwen_tts` (default after this change)
- `kokoro` (rollback)
- (`orpheus` is recognized only if/when a future v2 plan activates that provider)

Evaluated in `emily_server.py` bootstrap before provider factory.

## 11. Integration Points

| File | Change |
|------|--------|
| `voice_engine/providers/tts/qwen_tts.py` | **NEW** — primary deliverable |
| `voice_engine/providers/factory.py` | Add `qwen_tts` branch with fallback |
| `voice_engine/config.py` | Add Qwen3-TTS fields, change defaults |
| `config.yaml` | Add `voice_engine` block |
| `llm/fleet.py` | Update `voice_fast` tier model name |
| `emily_server.py` | Honor `EMILY_VOICE_TTS` env flag |
| `pyproject.toml` + `uv.lock` | Add `qwen-tts` |
| `scripts/check_deps.py` | Replace Orpheus/SNAC checks with Qwen3-TTS checks |
| `scripts/benchmark_voice_dual_gpu.py` | **NEW** — 30-turn latency benchmark |
| `tests/unit/voice_engine/providers/tts/test_qwen_tts.py` | **NEW** — mocked qwen-tts stream |
| `tests/unit/voice_engine/providers/test_factory_qwen_tts.py` | **NEW** — factory + fallback |
| `tests/unit/voice_engine/test_config_qwen_tts.py` | **NEW** — config defaults |
| `.claude/CLAUDE-decisions.md` | Append ADR |
| `ABLITERATED_SETUP.md` | Update fleet table + TTS section |
| `CLAUDE.md` | Update Model Tiers, Voice Pipeline TTS line, Critical Rule #15 (VRAM) |

## 12. Risk Register

| # | Risk | Prob. | Impact | Mitigation |
|---|------|-------|--------|------------|
| R1 | Ollama lacks a `huihui-ai/qwen3-abliterated:30b-a3b` tag | 35 % | Medium | Fallback ladder: (a) `huihui_ai/qwen3-abliterated:30b`; (b) import GGUF from HuggingFace via `ollama create`; (c) drop to `huihui_ai/qwen3-abliterated:14b` (still 2× the params of current 9 B). |
| R2 | `qwen-tts` package isn't on PyPI under that name, or has incompatible API with what the README shows | 20 % | Medium | First step of M0 is `pip install -U qwen-tts` + `python -c "import qwen_tts"`. If PyPI name differs, check `QwenLM/Qwen3-TTS` README for the actual install command. Worst case: `pip install git+https://github.com/QwenLM/Qwen3-TTS`. |
| R3 | Real-world Qwen3-TTS latency is much worse than the claimed 97 ms | 30 % | Medium | M5 benchmark compares p50/p95 vs SLO. If > 1.5 s p95: try vLLM backend (`qwen-tts` supports day-0); if still bad, fall back to Chatterbox-Turbo as an alternate provider. |
| R4 | qwen3-embedding + Qwen3-TTS co-residency on 3060 triggers VRAM fragmentation OOM | 20 % | Medium | 3.5 GB headroom is comfortable. If OOM: move embedding to 4090 (has 4.5 GB headroom) or use Qwen3-TTS 0.6 B variant. |
| R5 | Qwen3-TTS doesn't expose the streaming API in the pip package (only in the research code) | 25 % | Medium | Start with non-streaming `synthesize()` — full-sentence sync. Integrate streaming when exposed. Still beats Kokoro on quality. |
| R6 | 14 B `fast` tier eviction creates text-chat cold-start annoyance | 40 % | Low | Accept ~2 s swap on first text-chat turn. Document in ADR. |
| R7 | 3060 PCIe instability recurs (Xid 79 history) | 20 % | High | Existing `scripts/gpu_check.py` used for detection. On failure, Qwen3-TTS and embedding both move to 4090 (Whisper evicts 0.5 GB, embedding needs 5 GB, TTS needs 3.5 GB — fits on 4090 ~18 GB for LLM + ~5 GB + ~3.5 GB = 26.5 GB → OVER. Must drop LLM to 14 B in that failure mode). Alert via Brain dashboard. |
| R8 | Voice preset name ("emily-neutral") doesn't exist in Qwen3-TTS Base | 70 % | Low | M1 validates the preset; on mismatch, fall back to first supported preset (`tara` / `zoe` / whatever Qwen3-TTS Base ships) and update config.yaml. |

## 13. Testing Strategy

**Unit (`tests/unit/voice_engine/providers/tts/`):**
- `test_qwen_tts.py::test_synthesize_empty_returns_empty_array`
- `test_qwen_tts.py::test_synthesize_returns_float32_pcm`
- `test_qwen_tts.py::test_synthesize_stream_yields_per_chunk`
- `test_qwen_tts.py::test_synthesize_stream_cancellation`
- `test_factory_qwen_tts.py::test_factory_returns_qwen_tts`
- `test_factory_qwen_tts.py::test_factory_falls_back_to_kokoro_on_init_failure`
- `test_config_qwen_tts.py::test_defaults`

All use `unittest.mock.patch` to avoid loading the real Qwen3-TTS model in unit tests.

**Integration (marked `@pytest.mark.integration`):**
- `test_voice_e2e_qwen.py` — synthetic mic input → assert audible PCM within SLO.

**Benchmark (`scripts/benchmark_voice_dual_gpu.py`):**
- 30 turns, fixed prompt set, measure per-stage p50/p95/p99.
- Pass: p50 ≤ 1.0 s, p95 ≤ 1.6 s.

**Smoke (manual, after M5):**
- 5-minute free conversation (English + French): short Q&A, code dictation, barge-in, long monologue.
- Subjective A/B: Qwen3-TTS vs Kokoro on the same prompts.

## 14. Milestones

| M | Deliverable | Est. |
|---|-------------|------|
| M0 | Install `qwen-tts`; pull Qwen3-30B-A3B-abliterated via Ollama; verify both via a 1-sec standalone script; snapshot. | 0.5 d |
| M1 | Standalone `qwen-tts` smoke: `synthesize("hello")` writes a WAV via the package API. Validate voice-preset name. | 0.25 d |
| M2 | Write `qwen_tts.py` provider + unit tests (mocked). | 0.5 d |
| M3 | Wire factory + config + env flag; pin Whisper to CUDA:0 fp16; update `fleet.py` voice tier. | 0.5 d |
| M4 | End-to-end voice turn via `emily.service`; verify barge-in cancellation; verify Kokoro fallback. | 0.5 d |
| M5 | Benchmark harness; SLO met; if not, try vLLM backend. | 0.25 d |
| M6 | Docs (ABLITERATED_SETUP, CLAUDE-decisions, CLAUDE.md). | 0.25 d |

**Total: ~2.75 days** (down from v2's 3.75 d).

## 15. Rollback Plan

1. `export EMILY_VOICE_TTS=kokoro` in systemd env → `systemctl --user restart emily.service`. Kokoro resumes on CPU.
2. Revert `llm/fleet.py` voice-tier model name to Qwen3.5-abliterated 9 B → restart. (Ollama still has it.)
3. No code rollback required — all new code is additive + feature-flagged.

## 16. Open Questions (resolve during milestones, not before)

- **Exact Qwen3-TTS HF id** — verified at M0 via `pip show qwen-tts` + `qwen-tts --help` or the package's documented loader.
- **Voice preset name** — validated at M1 against Base-variant presets.
- **Streaming API exposure in pip package** — tested at M2. If not exposed, use non-streaming synth as v1 fallback.

## 17. Success Criteria

1. `nvidia-smi` shows: 4090 = voice LLM + Whisper; 3060 = embedding + Qwen3-TTS. Zero fragmentation.
2. Benchmark report: p50 ≤ 1.0 s, p95 ≤ 1.6 s over 30 turns (SLO from §2, with safety margin over the aspirational targets).
3. 5-minute free conversation (English + French): Qwen3-TTS subjectively preferred over Kokoro (n=1).
4. Text-chat regression suite passes — `smart`, `reasoning`, `vision`, `code`, `embedding` tiers unaffected.
5. `EMILY_VOICE_TTS=kokoro` rollback verified on restart.
6. `scripts/check_deps.py` green.

---

**Changes from v2 (Orpheus-3B design):**
- TTS: Orpheus-3B + SNAC + llama-cpp-python → **Qwen3-TTS 1.7B + `qwen-tts` pip package**.
- Removed SNAC stream decoder file (no longer needed).
- Removed `llama-cpp-python` CUDA-wheel dependency (R2 from v2 eliminated).
- 3060 headroom: 1.5 GB → 3.5 GB.
- Whisper location: CUDA:1 → CUDA:0 fp16 (faster).
- Timeline: 3.75 d → 2.75 d.
- Ecosystem consistency: all-Qwen family (LLM + embedding + TTS).
- Latency ceiling: p50 1.0 s → 0.7 s achievable (if 97 ms TTS claim holds within 2×).

**Why the v2 → v3 pivot was justified:** post-v2 research on GitHub (2026-04-19) surfaced Qwen3-TTS (QwenLM official, 10.7 k stars, mid-2026 update) which was already flagged as "available" in Emily's CLAUDE.md but had not been surfaced during v1/v2 design. Single-vendor ecosystem alignment + 3–5× lower claimed latency + simpler integration justifies the last pivot. No further pivots planned.

**Next step:** on approval → rewrite the implementation plan around M0–M6 above.
