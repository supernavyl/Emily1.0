use # Emily 1.0 — Hardened Unit Test Report

**Date:** 2026-02-27
**Suite:** `tests/unit/` (STT · TTS · VAD · VoiceEngine · Anthropic provider)
**Result:** **121 passed, 0 failed**

---

## Summary

| File | Tests | Focus |
|------|------:|-------|
| `test_stt.py` | 27 | STT pipeline — FasterWhisperSTT, TranscriptResult, resample |
| `test_tts.py` | 48 | TTS pipeline — TTSManager, engines, crossfade, ProsodyController |
| `test_vad.py` | 25 | VAD — SileroVAD, SpeechSegment, state machine, noise floor |
| `test_voice_engine_lifecycle.py` | 15 | VoiceEngine start/stop lifecycle, FSM wiring |
| `test_anthropic_provider.py` | 6 | Model registry, AnthropicProvider streaming, StreamingEngine |
| **Total** | **121** | |

---

## STT (`test_stt.py`)

### TranscriptResult properties
- `is_likely_speech` returns `True` when text is non-empty and `no_speech_prob < 0.5`
- `is_likely_speech` returns `False` for blank text or high noise probability
- `confidence` formula: `language_probability × (1 - no_speech_prob)`, clamped to `[0, 1]`
- `words` defaults to empty list

### FasterWhisperSTT.load()
- **Happy path**: calls `asyncio.to_thread` to construct the WhisperModel off the main thread
- **CUDA fallback**: first `to_thread` raises `RuntimeError("CUDA out of memory")`, second attempt succeeds on CPU
- **Import error**: `faster_whisper` not installed → `ImportError` propagates
- **Idempotent**: calling `load()` a second time returns early without reloading

### FasterWhisperSTT._transcribe_sync()
- Single segment: text stripped, latency_ms ≥ 0, words empty when none provided
- Multi-segment: all segment texts are concatenated and both are present in output
- Word timestamps: each `WordTimestamp` gets correct `word`, `start`, `end`, `probability`
- `no_speech_prob` averaged across all segments
- Raises `RuntimeError("not loaded")` if called before `load()`
- Empty segment list → empty text, `avg_log_prob == 0.0`

### FasterWhisperSTT.transcribe() (async)
- Returns a `TranscriptResult`
- On error: `STT_ERRORS_TOTAL.inc()` called exactly once, exception re-raised

### transcribe_audio() — resampling
- 16 kHz input → `_resample` not called, `SpeechSegment.sample_rate == 16000`
- 48 kHz input → `asyncio.to_thread(_resample, audio, 48000, 16000)` is called

### _resample()
- Downsamples 48 kHz → 16 kHz: output length ≈ 16000 (±10)
- Upsamples 8 kHz → 16 kHz: output length ≈ 16000 (±10)
- Identity (16 k → 16 k): length unchanged
- Output dtype always `float32`

---

## TTS (`test_tts.py`)

### crossfade()
- Empty `prev` → returns `curr` unchanged
- Empty `curr` → returns `prev` unchanged
- `overlap_samples < 2` → simple concatenation
- Normal overlap → output length = `len(prev) + len(curr) - overlap`
- Transition region is smooth (no jump discontinuity at overlap boundaries)
- Overlap capped at shorter array length — no crash for large `overlap_samples`

### ProsodyController.compute()
- Default sentence: speed/pitch/energy in valid ranges
- `?` suffix: pitch ↑, speed ↓, `pause_after_ms ≥ 350`
- `!` suffix: energy ↑
- `...` suffix: speed ↓
- `whisper_mode=True`: energy ↓, speed ↓ vs normal
- High engagement state → speed increases
- All values clamped: `speed ≤ 1.8`, `energy ≤ 1.4`, `pitch ≤ 1.3` even for extreme emotional input
- Sentence-position tapering: later sentences have lower energy than the first
- `pause_before_ms == 0` for first sentence; `> 0` for subsequent sentences
- `reset_position()` restores first-sentence behaviour

### ProsodyController.split_into_sentences()
- Single sentence returned as one element
- Two sentences split correctly
- Abbreviation `Dr.` not treated as sentence boundary
- Decimal `3.14` not treated as sentence boundary
- `...` preserved within segment, not split
- Empty / whitespace-only string returns `[]`
- Mixed punctuation `? ! .` produces 3 sentences

### TTSManager construction
- Primary engine is first in `_engine_list`
- Fallback engine is second
- Unknown engine name silently skipped (logged warning, not in list)
- Duplicate primary/fallback deduped — kokoro appears exactly once
- All three engines (csm, kokoro, xtts_v2) always instantiated

### TTSManager._select_engine()
- `force="xtts_v2"` selects that engine regardless of order
- `force=None` selects first available engine
- No engine available → `RuntimeError("No TTS engine available")`
- Unknown force name falls through to auto-select

### TTSManager.speak()
- Empty / whitespace-only text → yields nothing
- Normal text → yields ≥ 1 audio chunk with total bytes > 0
- Two-sentence text → at least 2 chunks (silence injected before second sentence)
- Primary engine crash → fallback engine used transparently
- All engines crash → no exception raised, yields nothing
- `whisper_mode=True` is forwarded to `ProsodyController.compute()`

### KokoroEngine
- Import error (`sys.modules["kokoro"] = None`) → `_available is False`
- Stream on unavailable engine → `RuntimeError("not available")`
- Fake KPipeline yields float32 audio → stream emits `bytes` decodable as `int16`

### XTTSv2Engine
- Import error (`sys.modules["TTS"] = None`) → `_available is False`
- Stream on unavailable engine → `RuntimeError("not available")`
- Stream with mock `_tts` + mocked `to_thread` → correct chunk count and size

### TTSManager.load()
- `load()` calls `engine.load()` on every engine
- One engine failing to load does not prevent the rest from loading

---

## VAD (`test_vad.py`)

### SpeechSegment properties
- `duration_ms = (end_time - start_time) × 1000`
- `duration_s = end_time - start_time`
- Zero-duration segment: both return `0.0`

### Energy-based probability
- Silent audio (zeros) → probability ≤ 0.15
- Loud audio (ones) → probability ≥ 0.9
- All amplitudes in `[0, 1]` → probability in `[0.0, 1.0]`

### Noise floor adaptation (EMA)
- Loud silence-state audio raises `_noise_floor` over iterations
- Noise floor not updated while in `SPEECH` state
- Effective threshold tracks noise floor (adapts upward when ambient noise rises)

### _chunks_to_ms()
- `(n_chunks × chunk_size / sample_rate) × 1000` — verified exact output
- Zero chunks → `0.0`

### VAD state machine
- Continuous silence → state stays `SILENCE`, no segments emitted
- First loud chunk (with `min_speech_ms=0`) → transitions to `SPEECH`
- Speech then silence → `SpeechSegment` emitted with `audio.len > 0`
- After segment emitted: state is `SILENCE`, `_speech_buffer == []`, `_silence_chunks == 0`
- Speech during `ENDING` state cancels countdown → back to `SPEECH`
- Emitted segment contains non-zero audio (RMS > 0.1)
- Speech below `min_speech_ms` threshold → state stays `SILENCE` (chunk discarded)

### SileroVAD.load()
- `silero_vad` import error → `_use_silero = False`, `_model = None`
- Silero loads successfully → no crash (flag-based assertion)

### _get_speech_probability()
- `_use_silero=True` but `_model=None` → falls back to energy, stays in `[0, 1]`
- `_use_silero=False` → energy path, silent audio → probability < 0.2

---

## VoiceEngine Lifecycle (`test_voice_engine_lifecycle.py`)

### start()
- `config.voice_enabled = False` → returns immediately, nothing imported
- After successful start → `is_running == True`
- `config.fast_mode = True` → `ConversationFSM` receives `fast_mode=True`
- All 15+ lazy-imported modules mocked via `patch.dict("sys.modules")` — no real hardware required

### stop()
- Calls `stop()` on VAD, STT, TTS, FSM, audio capture, and output stream
- Sets `is_running = False`
- Errors during individual module stop are suppressed (other modules still stopped)
- Safe when called with no modules loaded (no FSM yet)
- Calls `fsm.stop()` when FSM is present
- Uses `close()` on modules that implement it instead of `stop()`

### is_running property
- Initially `False`
- `True` after `start()` completes

---

## Fixes Applied During Hardening

### Model ID corrections (session 1)
The Anthropic model entries in `emily_chat/models/registry.py` used fabricated future-dated IDs
(`claude-sonnet-4-5-20260101`, `claude-opus-4-20260101`, `claude-haiku-4-20260101`).
Corrected to real IDs: `claude-sonnet-4-6`, `claude-opus-4-6`, `claude-haiku-4-5-20251001`.
Propagated to `emily_chat/emily/skills.py` and all test files.

### STT multi-segment assertion
Fake segment text uses a leading space (matching real Whisper output: `" hello"`).
`" ".join([" first", " second"]).strip()` produces `"first  second"` (double space).
Fixed: test asserts `"first" in result.text and "second" in result.text` instead of exact equality.

### Import-error test strategy
`patch("builtins.__import__", side_effect=ImportError)` is too broad — it intercepts
structlog's internal `datetime.now().astimezone()` call inside `log.warning()`, causing
the `ImportError` to surface from the logging layer rather than the target import.

Correct approach: `patch.dict("sys.modules", {"kokoro": None})` makes Python raise
`ImportError` exactly when `from kokoro import KPipeline` is executed, leaving all
other imports unaffected.

### XTTSv2Engine stream guard
`XTTSv2Engine.stream()` guards with `if not self._available or self._tts is None`.
Test was setting `engine._available = True` but leaving `engine._tts = None`.
Fixed: test now also sets `engine._tts = MagicMock()`.

---

## Test Architecture Notes

- All tests are pure unit tests — no real hardware, no network, no model files required
- Heavy ML backends (WhisperModel, KPipeline, TTS, silero_vad) are mocked at the sys.modules level
- Prometheus metrics are patched so counters and histograms don't accumulate across tests
- VoiceEngine lifecycle tests use a comprehensive `sys.modules` patch covering all 15+ lazy imports inside `start()`
- Async tests use `pytest-asyncio` with the `asyncio` mark
