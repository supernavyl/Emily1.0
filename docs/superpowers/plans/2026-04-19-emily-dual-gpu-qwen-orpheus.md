# Emily Dual-GPU Voice: Qwen3-30B-A3B-abliterated + Qwen3-TTS 1.7B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Emily's voice path to Qwen3-30B-A3B-abliterated MoE (via Ollama, 4090-resident) with Qwen3-TTS 1.7 B (via `qwen-tts` pip package, 3060-resident) while preserving Kokoro fallback and all text-chat tiers.

**Architecture:** Single new TTS provider `QwenTTS` implementing the existing `TTSProvider` base contract. No new services. `qwen-tts` runs in-process on CUDA:1. Voice-LLM swap is an Ollama tag change in `llm/fleet.py`. Whisper stays on CUDA:0 in fp16 (faster than 3060 int8). Kokoro stays registered; env flag `EMILY_VOICE_TTS=kokoro` reverts the TTS path.

**Tech Stack:** Python 3.11 + asyncio, `qwen-tts` (PyTorch backend), Ollama, Faster-Whisper (CTranslate2), pytest + pytest-asyncio (auto mode), uv, systemd --user.

**Spec:** `docs/superpowers/specs/2026-04-19-emily-dual-gpu-qwen-orpheus-design.md` (v3)

---

## Milestone M0 — Preparation & Dependencies

### Task 1: Snapshot the current state

**Files:**
- Create: `docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md`

- [ ] **Step 1: Capture GPU + model + dep state**

Run:
```bash
mkdir -p ~/Emily1.0/docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus
cd ~/Emily1.0
{
  echo "# Baseline snapshot — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "## GPU"
  nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv
  echo
  echo "## Ollama models"
  ollama list
  echo
  echo "## Current voice_fast tier"
  /usr/bin/grep -nE "voice_fast|VOICE_FAST" llm/fleet.py | head -20
  echo
  echo "## Current TTS provider config"
  /usr/bin/grep -nE "tts_provider|tts_voice" voice_engine/config.py config.yaml 2>/dev/null
  echo
  echo "## Python packages of interest"
  ~/Emily1.0/.venv/bin/python -c "
for pkg in ['qwen_tts', 'kokoro', 'snac', 'llama_cpp', 'faster_whisper', 'torch']:
    try:
        mod = __import__(pkg)
        v = getattr(mod, '__version__', 'unknown')
        print(f'  {pkg}: {v}')
    except ImportError:
        print(f'  {pkg}: NOT INSTALLED')
"
  echo
  echo "## Orpheus GGUF (dormant, kept as fallback)"
  ls -la models/orpheus-3b-0.1-ft-q4_k_m.gguf 2>/dev/null || echo "  missing"
  echo
  echo "## Git HEAD"
  git rev-parse HEAD
  git status --short | head -5
} > docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md
cat docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md
```

- [ ] **Step 2: Commit**

```bash
cd ~/Emily1.0
git add docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md
git commit -m "docs: baseline snapshot for Qwen3-TTS voice upgrade"
```

---

### Task 2: Install `qwen-tts` package

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] **Step 1: Try PyPI install**

```bash
cd ~/Emily1.0
uv add qwen-tts
```

Expected: `uv.lock` updates; `.venv/lib/python3.11/site-packages/qwen_tts/` exists. If PyPI rejects (package not published under that name), continue to Step 2.

- [ ] **Step 2: Fallback — install from GitHub**

```bash
cd ~/Emily1.0
uv add "qwen-tts @ git+https://github.com/QwenLM/Qwen3-TTS"
```

- [ ] **Step 3: Verify import and GPU availability**

```bash
cd ~/Emily1.0
~/Emily1.0/.venv/bin/python -c "
import qwen_tts
print('qwen_tts version:', getattr(qwen_tts, '__version__', 'unknown'))
print('top-level names:', [n for n in dir(qwen_tts) if not n.startswith('_')][:20])
import torch
print('CUDA available:', torch.cuda.is_available(), 'devices:', torch.cuda.device_count())
"
```

Expected: module imports; CUDA available; ≥ 2 devices.

If import fails, consult the Qwen3-TTS README for the actual package layout and adjust. Do not proceed until import works.

- [ ] **Step 4: Record the installed package layout**

Append to `baseline-snapshot.md`:
```
## qwen_tts package
(output of the python -c command above)
```

- [ ] **Step 5: Commit**

```bash
cd ~/Emily1.0
git add pyproject.toml uv.lock docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md
git commit -m "deps: add qwen-tts for Qwen3-TTS 1.7B voice synthesis"
```

---

### Task 3: Pull Qwen3-30B-A3B-abliterated via Ollama

**Files:**
- Modify: `docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md` (append chosen tag)

- [ ] **Step 1: Try primary tag**

```bash
ollama pull huihui_ai/qwen3-abliterated:30b-a3b-q4_K_M
```
Expected: pull succeeds OR 404.

- [ ] **Step 2: Try fallback tags**

If Step 1 fails, try in order until one works:
```bash
ollama pull huihui_ai/qwen3-abliterated:30b
ollama pull qwen3-abliterated:30b-a3b
# last resort:
ollama pull huihui_ai/qwen3-abliterated:14b
```

- [ ] **Step 3: Smoke run the model**

```bash
ollama run <chosen-tag> "Reply with one short sentence." --verbose
```

In a second terminal:
```bash
nvidia-smi --query-compute-apps=gpu_uuid,process_name,used_memory --format=csv
```
Expected: model process resident on GPU 0 (4090). Fragmentation across both GPUs is acceptable — Ollama manages.

- [ ] **Step 4: Append chosen tag to snapshot**

Edit `baseline-snapshot.md`, add: `Chosen voice LLM tag: <tag>`.

- [ ] **Step 5: Commit**

```bash
cd ~/Emily1.0
git add docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md
git commit -m "docs: record chosen Qwen3-abliterated Ollama tag"
```

---

## Milestone M1 — Qwen3-TTS Standalone Smoke

### Task 4: Standalone synth sanity check

**Files:**
- Create: `/tmp/qwen_tts_smoke.py` (not committed)

- [ ] **Step 1: Write the smoke script**

Create `/tmp/qwen_tts_smoke.py`:

```python
"""One-off Qwen3-TTS smoke. Not committed to repo."""
from __future__ import annotations

import wave

import numpy as np

# NOTE: The exact import + loader for qwen-tts is discovered at Task 2. The
# block below assumes the most common shape — a `QwenTTSModel` or similar class
# loaded from a HF model id. Adjust based on `dir(qwen_tts)` output.
import qwen_tts  # type: ignore[import-untyped]

MODEL_ID = "Qwen/Qwen3-TTS-1.7B-Base"


def main() -> None:
    # Try common loader patterns; use whichever is real.
    load_fn = (
        getattr(qwen_tts, "from_pretrained", None)
        or getattr(qwen_tts, "load", None)
        or getattr(getattr(qwen_tts, "model", None), "from_pretrained", None)
    )
    if load_fn is None:
        msg = "Could not find a loader in qwen_tts; inspect dir(qwen_tts) and fix."
        raise RuntimeError(msg)

    model = load_fn(MODEL_ID, device="cuda:1")

    text = "Hello. This is Emily speaking through Qwen three T T S."
    audio, sample_rate = model.synthesize(text)  # adjust signature as needed

    pcm = np.asarray(audio, dtype=np.float32).flatten()
    pcm16 = np.clip(pcm * 32767, -32768, 32767).astype(np.int16)
    with wave.open("/tmp/qwen_tts_smoke.wav", "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(int(sample_rate))
        f.writeframes(pcm16.tobytes())

    print(f"wrote /tmp/qwen_tts_smoke.wav ({len(pcm)/sample_rate:.2f}s @ {sample_rate} Hz)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
cd ~/Emily1.0
.venv/bin/python /tmp/qwen_tts_smoke.py
aplay /tmp/qwen_tts_smoke.wav  # or any 24-48 kHz-capable player
```

Expected: audible speech of the text. Note the reported sample rate — likely 24000 Hz.

If the loader or `synthesize` signature differs, fix the script to match the real `qwen_tts` API. Do not proceed until audio plays.

- [ ] **Step 3: Record working loader pattern**

Append to `baseline-snapshot.md` under `## qwen_tts package`:
```
Loader used: <e.g. qwen_tts.from_pretrained(model_id, device=...)>
Synthesize call: <e.g. audio, sr = model.synthesize(text)>
Sample rate observed: <N> Hz
Voice presets found: <names or "no presets in Base variant">
```

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md
git commit -m "docs: record Qwen3-TTS loader + sample rate from smoke test"
```

---

## Milestone M2 — `QwenTTS` Provider

### Task 5: Failing tests for `QwenTTS`

**Files:**
- Create: `tests/unit/voice_engine/providers/tts/__init__.py` (if missing)
- Create: `tests/unit/voice_engine/providers/tts/test_qwen_tts.py`

- [ ] **Step 1: Ensure test dirs exist**

```bash
cd ~/Emily1.0
mkdir -p tests/unit/voice_engine/providers/tts
touch tests/unit/voice_engine/providers/tts/__init__.py
```

- [ ] **Step 2: Write the test file**

Create `tests/unit/voice_engine/providers/tts/test_qwen_tts.py`:

```python
"""Tests for the Qwen3-TTS provider.

The real qwen_tts model is never loaded here — we patch the loader and
the synthesize call. The contract under test is the TTSProvider base:
synthesize(text) -> np.ndarray; synthesize_stream(text_chunks) -> AsyncIterator.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice_engine.providers.tts.qwen_tts import QwenTTS


def _fake_audio(samples: int = 2048, sample_rate: int = 24000) -> tuple[np.ndarray, int]:
    return (np.linspace(-0.5, 0.5, samples, dtype=np.float32), sample_rate)


@pytest.mark.asyncio
async def test_synthesize_empty_text_returns_empty_array() -> None:
    with patch("voice_engine.providers.tts.qwen_tts._load_qwen_tts_model") as mock_load:
        mock_load.return_value = MagicMock(synthesize=MagicMock(return_value=_fake_audio()))

        tts = QwenTTS(model_id="fake/id", voice_preset="default", device="cuda:1")
        out = await tts.synthesize("   ")

    assert isinstance(out, np.ndarray)
    assert out.dtype == np.float32
    assert out.size == 0


@pytest.mark.asyncio
async def test_synthesize_returns_float32_pcm() -> None:
    with patch("voice_engine.providers.tts.qwen_tts._load_qwen_tts_model") as mock_load:
        mock_load.return_value = MagicMock(synthesize=MagicMock(return_value=_fake_audio()))

        tts = QwenTTS(model_id="fake/id", voice_preset="default", device="cuda:1")
        out = await tts.synthesize("hello world")

    assert isinstance(out, np.ndarray)
    assert out.dtype == np.float32
    assert out.ndim == 1
    assert out.size > 0


@pytest.mark.asyncio
async def test_synthesize_stream_yields_per_chunk() -> None:
    async def _chunks() -> AsyncIterator[str]:
        yield "First sentence."
        yield "Second one."

    with patch("voice_engine.providers.tts.qwen_tts._load_qwen_tts_model") as mock_load:
        mock_load.return_value = MagicMock(synthesize=MagicMock(return_value=_fake_audio(1024)))

        tts = QwenTTS(model_id="fake/id", voice_preset="default", device="cuda:1")
        out_chunks: list[np.ndarray] = []
        async for chunk in tts.synthesize_stream(_chunks()):
            out_chunks.append(chunk)

    assert len(out_chunks) == 2
    for c in out_chunks:
        assert c.dtype == np.float32
        assert c.size > 0


@pytest.mark.asyncio
async def test_synthesize_stream_honors_cancellation() -> None:
    async def _chunks() -> AsyncIterator[str]:
        yield "start"
        await asyncio.sleep(1.0)
        yield "never reached"

    with patch("voice_engine.providers.tts.qwen_tts._load_qwen_tts_model") as mock_load:
        mock_load.return_value = MagicMock(synthesize=MagicMock(return_value=_fake_audio(512)))

        tts = QwenTTS(model_id="fake/id", voice_preset="default", device="cuda:1")

        async def _consume() -> None:
            async for _ in tts.synthesize_stream(_chunks()):
                pass

        task = asyncio.create_task(_consume())
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
```

- [ ] **Step 3: Run — expect import error**

```bash
cd ~/Emily1.0
uv run pytest tests/unit/voice_engine/providers/tts/test_qwen_tts.py -v
```
Expected: `ModuleNotFoundError: No module named 'voice_engine.providers.tts.qwen_tts'`.

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add tests/unit/voice_engine/providers/tts/
git commit -m "test: failing tests for Qwen3-TTS provider"
```

---

### Task 6: Implement `QwenTTS`

**Files:**
- Create: `voice_engine/providers/tts/qwen_tts.py`

- [ ] **Step 1: Implement the provider**

Create `voice_engine/providers/tts/qwen_tts.py`. Adjust the internal `_load_qwen_tts_model` to match whatever loader pattern was recorded in M1's snapshot.

```python
"""Qwen3-TTS provider — runs the `qwen-tts` package in-process on a chosen CUDA device.

The exact loader and call signature of the `qwen-tts` package are indirected
through a private `_load_qwen_tts_model` function so unit tests can patch it
and so the real signature can evolve without touching the provider contract.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import numpy as np

from observability.logger import get_logger
from voice_engine.providers.base import TTSProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = get_logger(__name__)

QWEN_TTS_DEFAULT_SAMPLE_RATE = 24000


def _load_qwen_tts_model(model_id: str, device: str) -> Any:
    """Load the qwen-tts model. Swap body to match the real package loader.

    Recorded at M1 (see baseline-snapshot.md). Common patterns:
      - qwen_tts.from_pretrained(model_id, device=device)
      - qwen_tts.Model.from_pretrained(model_id, device=device)
    """
    import qwen_tts  # type: ignore[import-untyped]

    if hasattr(qwen_tts, "from_pretrained"):
        return qwen_tts.from_pretrained(model_id, device=device)
    if hasattr(qwen_tts, "Model") and hasattr(qwen_tts.Model, "from_pretrained"):
        return qwen_tts.Model.from_pretrained(model_id, device=device)
    if hasattr(qwen_tts, "load"):
        return qwen_tts.load(model_id, device=device)

    msg = (
        "No known loader on qwen_tts. Update _load_qwen_tts_model "
        "to match the package's actual API."
    )
    raise RuntimeError(msg)


class QwenTTS(TTSProvider):
    """Text-to-speech via Qwen3-TTS (in-process, GPU-pinned)."""

    def __init__(
        self,
        model_id: str,
        voice_preset: str = "default",
        device: str = "cuda:1",
        sample_rate: int = QWEN_TTS_DEFAULT_SAMPLE_RATE,
    ) -> None:
        self._model_id = model_id
        self._voice_preset = voice_preset
        self._device = device
        self._sample_rate = sample_rate
        self._model: Any | None = None
        logger.info(
            "QwenTTS configured: model=%s voice=%s device=%s sr=%d",
            model_id, voice_preset, device, sample_rate,
        )

    def set_voice(self, voice: str) -> None:
        self._voice_preset = voice
        logger.info("QwenTTS voice changed to %s", voice)

    def _ensure_loaded(self) -> Any:
        if self._model is None:
            logger.info("Loading Qwen3-TTS model %s on %s ...", self._model_id, self._device)
            self._model = _load_qwen_tts_model(self._model_id, self._device)
            logger.info("Qwen3-TTS model ready.")
        return self._model

    def _synthesize_sync(self, text: str) -> np.ndarray:
        text = text.strip()
        if not text:
            return np.empty(0, dtype=np.float32)

        model = self._ensure_loaded()

        # Real call signature is validated in M1; the pattern is (audio, sample_rate).
        result = model.synthesize(text, voice=self._voice_preset) \
            if _accepts_voice_kwarg(model) \
            else model.synthesize(text)

        audio, sr = _unpack_audio_result(result)
        pcm = np.asarray(audio, dtype=np.float32).flatten()
        if sr != self._sample_rate:
            logger.debug("Qwen3-TTS returned sr=%d (expected %d)", sr, self._sample_rate)
            self._sample_rate = int(sr)
        return pcm

    async def synthesize(self, text: str) -> np.ndarray:
        if not text.strip():
            return np.empty(0, dtype=np.float32)
        loop = asyncio.get_running_loop()
        audio = await loop.run_in_executor(None, self._synthesize_sync, text)
        logger.debug("Qwen3-TTS synthesized %d samples for: %s", len(audio), text[:60])
        return audio

    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
    ) -> AsyncIterator[np.ndarray]:
        async for text in text_chunks:
            if not text.strip():
                continue
            audio = await self.synthesize(text)
            if len(audio) > 0:
                yield audio


def _accepts_voice_kwarg(model: Any) -> bool:
    try:
        import inspect
        sig = inspect.signature(model.synthesize)
        return "voice" in sig.parameters
    except Exception:
        return False


def _unpack_audio_result(result: Any) -> tuple[np.ndarray, int]:
    """Handle common return shapes from TTS packages: (audio, sr), {'audio':..., 'sr':...}, bare array."""
    if isinstance(result, tuple) and len(result) == 2:
        return result[0], int(result[1])
    if isinstance(result, dict):
        audio = result.get("audio") or result.get("waveform") or result.get("pcm")
        sr = result.get("sample_rate") or result.get("sr") or QWEN_TTS_DEFAULT_SAMPLE_RATE
        if audio is None:
            msg = f"qwen-tts returned dict without audio key: {list(result.keys())}"
            raise RuntimeError(msg)
        return audio, int(sr)
    return np.asarray(result), QWEN_TTS_DEFAULT_SAMPLE_RATE
```

- [ ] **Step 2: Run unit tests**

```bash
cd ~/Emily1.0
uv run pytest tests/unit/voice_engine/providers/tts/test_qwen_tts.py -v
```
Expected: 4 passing tests.

- [ ] **Step 3: Integration smoke — real model**

Create `/tmp/qwen_tts_provider_smoke.py`:

```python
import asyncio
import wave
import numpy as np
from voice_engine.providers.tts.qwen_tts import QwenTTS

async def main() -> None:
    tts = QwenTTS(
        model_id="Qwen/Qwen3-TTS-1.7B-Base",
        voice_preset="default",
        device="cuda:1",
    )
    pcm = await tts.synthesize("Emily speaking through Qwen three T T S, the provider class.")
    print(f"{len(pcm)} samples (~{len(pcm)/tts._sample_rate:.2f}s)")
    pcm16 = np.clip(pcm * 32767, -32768, 32767).astype(np.int16)
    with wave.open("/tmp/qwen_tts_provider.wav", "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(tts._sample_rate)
        f.writeframes(pcm16.tobytes())
    print("wrote /tmp/qwen_tts_provider.wav")

asyncio.run(main())
```

Run:
```bash
cd ~/Emily1.0
.venv/bin/python /tmp/qwen_tts_provider_smoke.py
aplay /tmp/qwen_tts_provider.wav
```
Expected: audible speech.

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add voice_engine/providers/tts/qwen_tts.py
git commit -m "feat: QwenTTS provider (Qwen3-TTS via qwen-tts, 3060-pinned)"
```

---

## Milestone M3 — Config, Factory, Whisper Pin, LLM Swap

### Task 7: Extend `VoiceEngineConfig` with Qwen3-TTS fields

**Files:**
- Modify: `voice_engine/config.py` (STT block lines ~40-45; TTS block lines ~55-57)
- Modify: `config.yaml`
- Create: `tests/unit/voice_engine/test_config_qwen_tts.py`

- [ ] **Step 1: Failing config test**

Create `tests/unit/voice_engine/test_config_qwen_tts.py`:

```python
"""Tests for Qwen3-TTS config defaults."""

from __future__ import annotations

from voice_engine.config import VoiceEngineConfig


def test_default_tts_provider_is_qwen_tts() -> None:
    cfg = VoiceEngineConfig()
    assert cfg.tts_provider == "qwen_tts"
    assert cfg.tts_fallback == "kokoro"


def test_default_qwen_tts_config() -> None:
    cfg = VoiceEngineConfig()
    assert cfg.qwen_tts_model_id.startswith("Qwen/Qwen3-TTS")
    assert cfg.qwen_tts_device == "cuda:1"


def test_stt_defaults_pin_whisper_to_cuda0_fp16() -> None:
    cfg = VoiceEngineConfig()
    assert cfg.stt_device == "cuda"
    assert cfg.stt_device_index == 0
    assert cfg.stt_compute_type == "float16"
```

Run (expect fail):
```bash
uv run pytest tests/unit/voice_engine/test_config_qwen_tts.py -v
```

- [ ] **Step 2: Update `voice_engine/config.py`**

Replace the STT block (currently lines ~40-45). Apply:

OLD:
```python
    # ── STT ────────────────────────────────────────
    stt_provider: str = Field(default="faster_whisper", description="STT provider name")
    stt_model: str = Field(default="distil-large-v3", description="STT model identifier")
    stt_device: str = Field(default="cuda", description="STT device: 'cuda' or 'cpu'")
    stt_device_index: int = Field(default=0, description="CUDA device index: 0=4090, 1=3060")
    stt_compute_type: str = Field(default="float16", description="STT compute type: 'float16', 'int8', 'int8_float16'")
```

NEW:
```python
    # ── STT ────────────────────────────────────────
    stt_provider: str = Field(default="faster_whisper", description="STT provider name")
    stt_model: str = Field(default="distil-large-v3", description="STT model identifier")
    stt_device: str = Field(default="cuda", description="STT device: 'cuda' or 'cpu'")
    stt_device_index: int = Field(default=0, description="CUDA device index: 0=4090 (with voice LLM), 1=3060 (with embedding+TTS)")
    stt_compute_type: str = Field(default="float16", description="STT compute type: fp16 on 4090 is faster than int8 on 3060")
```

Replace the TTS block (currently lines ~55-57):

OLD:
```python
    # ── TTS (Kokoro only) ─────────────────────────
    tts_provider: str = Field(default="kokoro", description="TTS provider (kokoro)")
    tts_voice: str = Field(default="af_nicole", description="Kokoro voice identifier")
```

NEW:
```python
    # ── TTS (Qwen3-TTS primary, Kokoro fallback) ──
    tts_provider: str = Field(default="qwen_tts", description="TTS provider: 'qwen_tts' or 'kokoro'")
    tts_fallback: str = Field(default="kokoro", description="TTS provider used if primary fails to load")
    tts_voice: str = Field(default="default", description="Voice preset name (validate against the provider's preset list)")
    qwen_tts_model_id: str = Field(
        default="Qwen/Qwen3-TTS-1.7B-Base",
        description="Hugging Face model id (or local path) for Qwen3-TTS",
    )
    qwen_tts_device: str = Field(default="cuda:1", description="Torch device for Qwen3-TTS inference")
```

- [ ] **Step 3: Run config tests — expect pass**

```bash
cd ~/Emily1.0
uv run pytest tests/unit/voice_engine/test_config_qwen_tts.py -v
```
Expected: 3 passing.

- [ ] **Step 4: Reconcile `config.yaml`**

Run:
```bash
cd ~/Emily1.0
/usr/bin/grep -nE "tts_provider|tts_voice|stt_device_index|stt_compute_type|qwen_tts" config.yaml
```

If `config.yaml` has a `voice_engine:` section with TTS overrides, update to:

```yaml
voice_engine:
  tts_provider: qwen_tts
  tts_fallback: kokoro
  tts_voice: default
  stt_device: cuda
  stt_device_index: 0
  stt_compute_type: float16
  qwen_tts_model_id: Qwen/Qwen3-TTS-1.7B-Base
  qwen_tts_device: cuda:1
```

If no such section exists, skip — defaults apply.

- [ ] **Step 5: Commit**

```bash
cd ~/Emily1.0
git add voice_engine/config.py tests/unit/voice_engine/test_config_qwen_tts.py config.yaml
git commit -m "feat: voice config defaults for Qwen3-TTS + CUDA:0 fp16 Whisper"
```

---

### Task 8: Wire `qwen_tts` into `ProviderFactory` (with fallback)

**Files:**
- Modify: `voice_engine/providers/factory.py:95-105`
- Create: `tests/unit/voice_engine/providers/test_factory_qwen_tts.py`

- [ ] **Step 1: Failing factory tests**

Create `tests/unit/voice_engine/providers/test_factory_qwen_tts.py`:

```python
"""Factory returns QwenTTS, falls back to Kokoro on init failure."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from voice_engine.config import VoiceEngineConfig
from voice_engine.providers.factory import ProviderFactory


def test_factory_returns_qwen_tts_for_qwen_tts_config() -> None:
    cfg = VoiceEngineConfig(tts_provider="qwen_tts")

    with patch("voice_engine.providers.tts.qwen_tts._load_qwen_tts_model"):
        provider = ProviderFactory.create_tts(cfg)

    assert provider.__class__.__name__ == "QwenTTS"


def test_factory_still_returns_kokoro_for_kokoro_config() -> None:
    cfg = VoiceEngineConfig(tts_provider="kokoro")
    provider = ProviderFactory.create_tts(cfg)
    assert provider.__class__.__name__ == "KokoroTTS"


def test_factory_falls_back_to_kokoro_when_qwen_tts_init_fails() -> None:
    cfg = VoiceEngineConfig(tts_provider="qwen_tts", tts_fallback="kokoro")

    with patch(
        "voice_engine.providers.tts.qwen_tts.QwenTTS.__init__",
        side_effect=RuntimeError("simulated load failure"),
    ):
        provider = ProviderFactory.create_tts(cfg)

    assert provider.__class__.__name__ == "KokoroTTS"


def test_factory_raises_on_unknown_tts() -> None:
    cfg = VoiceEngineConfig(tts_provider="nonexistent_tts_provider")
    with pytest.raises(ValueError, match="nonexistent_tts_provider"):
        ProviderFactory.create_tts(cfg)
```

Run (expect fail):
```bash
uv run pytest tests/unit/voice_engine/providers/test_factory_qwen_tts.py -v
```

- [ ] **Step 2: Update `voice_engine/providers/factory.py`**

Replace the `create_tts` body. Apply:

OLD:
```python
    @staticmethod
    def create_tts(config: VoiceEngineConfig) -> TTSProvider:
        """Create and return a TTS provider based on ``config.tts_provider``."""
        name = config.tts_provider.lower().strip()
        logger.info("Creating TTS provider: %s (voice=%s)", name, config.tts_voice)

        if name in ("kokoro", "tiered"):
            from voice_engine.providers.tts.kokoro_tts import KokoroTTS

            return KokoroTTS(voice=config.tts_voice)

        raise ValueError(f"Unknown TTS provider: {name!r}. Only 'kokoro' is supported.")
```

NEW:
```python
    @staticmethod
    def create_tts(config: VoiceEngineConfig) -> TTSProvider:
        """Create and return a TTS provider based on ``config.tts_provider``."""
        name = config.tts_provider.lower().strip()
        logger.info("Creating TTS provider: %s (voice=%s)", name, config.tts_voice)

        if name == "qwen_tts":
            from voice_engine.providers.tts.qwen_tts import QwenTTS

            try:
                return QwenTTS(
                    model_id=config.qwen_tts_model_id,
                    voice_preset=config.tts_voice,
                    device=config.qwen_tts_device,
                )
            except Exception:
                logger.exception(
                    "QwenTTS failed to initialize; falling back to %s",
                    config.tts_fallback,
                )
                if config.tts_fallback == "kokoro":
                    from voice_engine.providers.tts.kokoro_tts import KokoroTTS

                    return KokoroTTS(voice="af_nicole")
                raise

        if name in ("kokoro", "tiered"):
            from voice_engine.providers.tts.kokoro_tts import KokoroTTS

            return KokoroTTS(voice=config.tts_voice if config.tts_voice.startswith("af_") else "af_nicole")

        raise ValueError(f"Unknown TTS provider: {name!r}. Supported: 'qwen_tts', 'kokoro'.")
```

- [ ] **Step 3: Run factory tests**

```bash
cd ~/Emily1.0
uv run pytest tests/unit/voice_engine/providers/test_factory_qwen_tts.py -v
```
Expected: 4 passing.

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add voice_engine/providers/factory.py tests/unit/voice_engine/providers/test_factory_qwen_tts.py
git commit -m "feat: wire Qwen3-TTS into ProviderFactory with Kokoro fallback"
```

---

### Task 9: `EMILY_VOICE_TTS` env flag in `emily_server.py`

**Files:**
- Modify: `emily_server.py` (near the TTS provider creation site)

- [ ] **Step 1: Locate TTS instantiation**

```bash
cd ~/Emily1.0
/usr/bin/grep -n "create_tts\|tts_provider\|VoiceEngineConfig" emily_server.py | head -20
```

- [ ] **Step 2: Insert env-flag override**

Before the first `VoiceEngineConfig()` (or `get_settings()`) call, add:

```python
import os

_tts_override = os.environ.get("EMILY_VOICE_TTS", "").strip().lower()
if _tts_override in ("qwen_tts", "kokoro"):
    os.environ["tts_provider"] = _tts_override
    logger.info("EMILY_VOICE_TTS override active: %s", _tts_override)
```

- [ ] **Step 3: Verify**

```bash
cd ~/Emily1.0
EMILY_VOICE_TTS=kokoro .venv/bin/python -c "
import os
os.environ['tts_provider'] = os.environ.get('EMILY_VOICE_TTS', '')
from voice_engine.config import VoiceEngineConfig
print('tts_provider =', VoiceEngineConfig().tts_provider)
"
```
Expected: `tts_provider = kokoro`.

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add emily_server.py
git commit -m "feat: EMILY_VOICE_TTS env flag for TTS rollback"
```

---

### Task 10: Update `llm/fleet.py` voice tier model name

**Files:**
- Modify: `llm/fleet.py` (voice_fast tier definition)

- [ ] **Step 1: Find the tier**

```bash
cd ~/Emily1.0
/usr/bin/grep -n "voice_fast\|VOICE_FAST\|qwen3\.5\|qwen3-abliterated" llm/fleet.py | head -20
```

- [ ] **Step 2: Swap the tag**

Replace the current Qwen3.5-abliterated 9 B tag with the Qwen3-30B-A3B-abliterated tag chosen in Task 3. Keep `keep_alive=30m` and all other tier params unchanged.

- [ ] **Step 3: Verify**

```bash
cd ~/Emily1.0
.venv/bin/python -c "
from llm.fleet import LLMFleet
fleet = LLMFleet()
print(fleet)  # or the appropriate inspection API
"
ollama ps
```

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add llm/fleet.py
git commit -m "feat: voice_fast tier → Qwen3-30B-A3B-abliterated (MoE, 4090)"
```

---

## Milestone M4 — End-to-End & Fallback

### Task 11: End-to-end voice turn smoke

**Files:** (validation only)

- [ ] **Step 1: Restart Emily**

```bash
systemctl --user restart emily.service
sleep 5
systemctl --user status emily.service --no-pager
```

- [ ] **Step 2: Check logs for provider init**

```bash
journalctl --user -u emily.service -n 200 --no-pager | /usr/bin/grep -iE "qwen|whisper|voice_fast|ollama"
```
Expected: `QwenTTS configured`, `Loading Qwen3-TTS`, `FasterWhisperSTT configured: model=... device=cuda:0`, voice_fast tier = new tag.

- [ ] **Step 3: Check GPU split**

```bash
nvidia-smi --query-compute-apps=gpu_uuid,process_name,used_memory --format=csv
```
Expected:
- GPU 0 (4090): ollama with the MoE LLM + python (Whisper, ~1.5 GB)
- GPU 1 (3060): ollama (embedding ~5 GB) + python (Qwen3-TTS ~3.5 GB)

- [ ] **Step 4: Voice turn**

Say: "Emily, say hello."

```bash
journalctl --user -u emily.service -f
```
Expected: STT → LLM stream → Qwen3-TTS → audible response.

- [ ] **Step 5: Record outcome**

Append to `baseline-snapshot.md`:
```
## M4 smoke result (YYYY-MM-DD)
- End-to-end: PASS/FAIL
- Observed eyeball latency: ~N s
- Notes: ...
```

Commit.

---

### Task 12: Barge-in cancellation check

**Files:** (manual)

- [ ] **Step 1: Trigger**

Restart Emily. Say: "Tell me a long story about..." Interrupt mid-sentence with "Stop."

- [ ] **Step 2: Verify logs**

```bash
journalctl --user -u emily.service -n 300 --no-pager | /usr/bin/grep -iE "interrupt|cancel|barge"
```
Expected: cancellation fires, `QwenTTS.synthesize_stream` gets `CancelledError`, pipeline returns to LISTENING.

- [ ] **Step 3: Commit snapshot update**

---

### Task 13: Kokoro fallback verification

**Files:** (manual)

- [ ] **Step 1: Break Qwen3-TTS**

Temporarily set `EMILY_VOICE_TTS=kokoro`:
```bash
systemctl --user edit emily.service
# add: Environment="EMILY_VOICE_TTS=kokoro"
systemctl --user restart emily.service
```

- [ ] **Step 2: Verify Kokoro path**

Voice turn → Kokoro speaks. Check logs: `KokoroTTS configured`. No Qwen3-TTS loading.

- [ ] **Step 3: Revert**

Remove the env override. Restart. Verify Qwen3-TTS resumes.

- [ ] **Step 4: Commit snapshot update**

---

## Milestone M5 — Benchmark

### Task 14: Write `scripts/benchmark_voice_dual_gpu.py`

**Files:**
- Create: `scripts/benchmark_voice_dual_gpu.py`

- [ ] **Step 1: Create the benchmark**

```python
"""End-to-end voice latency benchmark for the dual-GPU Qwen setup.

Drives LLM + TTS directly (STT simulated via pre-transcribed prompts).
Writes benchmarks/voice-dual-gpu-YYYY-MM-DD.json.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import statistics
import time
from pathlib import Path

from voice_engine.config import VoiceEngineConfig
from voice_engine.providers.factory import ProviderFactory

PROMPTS = [
    ("short", "What's the weather like?"),
    ("short", "Tell me a joke."),
    ("medium", "Explain transformers in two sentences."),
    ("medium", "What's the difference between HTTP/2 and HTTP/3?"),
    ("code", "Write a Python function that reverses a string."),
    ("code", "How do you open a file in binary mode in Rust?"),
    ("emotional", "I had a really hard day. Can you say something kind?"),
    ("emotional", "I just got amazing news and I want to celebrate!"),
    ("long", "Summarize Hamlet in four sentences."),
    ("long", "Describe the Linux kernel scheduler."),
]
TURNS_PER_PROMPT = 3


async def run() -> dict:
    cfg = VoiceEngineConfig()
    llm = ProviderFactory.create_llm(cfg)
    tts = ProviderFactory.create_tts(cfg)

    system_prompt = cfg.get_system_prompt()
    results: list[dict] = []

    for _ in range(TURNS_PER_PROMPT):
        for category, text in PROMPTS:
            t_user_end = time.perf_counter()

            first_tok_t: float | None = None
            full_response = ""
            async for tok in llm.stream_response(
                messages=[{"role": "user", "content": text}],
                system=system_prompt,
            ):
                if first_tok_t is None:
                    first_tok_t = time.perf_counter()
                full_response += tok
            t_llm_end = time.perf_counter()

            t_tts_start = time.perf_counter()
            audio = await tts.synthesize(full_response[:300])
            t_first_audio = time.perf_counter()

            results.append({
                "category": category,
                "prompt": text,
                "ms_first_token": ((first_tok_t or t_llm_end) - t_user_end) * 1000,
                "ms_llm_complete": (t_llm_end - t_user_end) * 1000,
                "ms_tts": (t_first_audio - t_tts_start) * 1000,
                "ms_total_end_to_end": (t_first_audio - t_user_end) * 1000,
                "audio_samples": int(audio.size),
            })

    values = [r["ms_total_end_to_end"] for r in results]
    summary = {
        "n": len(results),
        "p50_ms_total": statistics.median(values),
        "p95_ms_total": statistics.quantiles(values, n=20)[18] if len(values) >= 20 else max(values),
        "mean_ms_total": statistics.mean(values),
    }
    return {"summary": summary, "results": results}


def main() -> None:
    today = dt.date.today().isoformat()
    out_dir = Path("benchmarks")
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"voice-dual-gpu-{today}.json"
    report = asyncio.run(run())
    out.write_text(json.dumps(report, indent=2))
    print(f"Wrote {out}")
    print(f"p50 total: {report['summary']['p50_ms_total']:.0f} ms")
    print(f"p95 total: {report['summary']['p95_ms_total']:.0f} ms")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run**

```bash
cd ~/Emily1.0
uv run python scripts/benchmark_voice_dual_gpu.py
```

- [ ] **Step 3: Verify SLO**

Open the JSON. Required:
- `p50_ms_total` ≤ 1000
- `p95_ms_total` ≤ 1600

If fail: verify Ollama keep_alive, verify Qwen3-TTS is on CUDA:1 (`nvidia-smi`), try `qwen-tts` vLLM backend (see spec §5 note).

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add scripts/benchmark_voice_dual_gpu.py benchmarks/
git commit -m "feat: dual-GPU voice benchmark + first report"
```

---

## Milestone M6 — Documentation

### Task 15: Update `ABLITERATED_SETUP.md`

**Files:**
- Modify: `ABLITERATED_SETUP.md`

- [ ] **Step 1: Update fleet table**

Change `voice_fast` row: Qwen3-30B-A3B-abliterated Q4_K_M via Ollama on 4090 (~18 GB). Note 14 B no longer co-resident.

- [ ] **Step 2: Add Qwen3-TTS section**

After the fleet table:

```markdown
## Voice Output — Qwen3-TTS 1.7B (primary)

Emily's primary TTS is Qwen3-TTS 1.7 B via the `qwen-tts` pip package,
running in-process on CUDA:1 (RTX 3060) alongside the embedding model.
Kokoro (CPU) is the fallback.

- Model: Qwen/Qwen3-TTS-1.7B-Base (~3.5 GB fp16 VRAM)
- Sample rate: 24 kHz (verified at M1 of the implementation plan)
- Claimed latency: 97 ms end-to-end (vendor); observed at M5 benchmark
- Rollback: `EMILY_VOICE_TTS=kokoro` + restart `emily.service`
- Dormant fallback: Orpheus-3B GGUF still on disk, provider path not wired
```

- [ ] **Step 3: Commit**

```bash
cd ~/Emily1.0
git add ABLITERATED_SETUP.md
git commit -m "docs: ABLITERATED_SETUP reflects Qwen3-TTS + 30B-A3B voice"
```

---

### Task 16: Append ADR to `.claude/CLAUDE-decisions.md`

**Files:**
- Modify: `.claude/CLAUDE-decisions.md`

- [ ] **Step 1: Append**

```markdown
## ADR 2026-04-19 — Dual-GPU Voice: Qwen3-30B-A3B-abliterated + Qwen3-TTS 1.7B

**Decision:** Voice LLM = Qwen3-30B-A3B-abliterated (MoE Q4_K_M) on 4090 via
Ollama. Voice TTS = Qwen3-TTS 1.7 B via `qwen-tts` on 3060, alongside
qwen3-embedding 8 B. Whisper pinned to CUDA:0 fp16 on 4090. Kokoro remains
as fallback.

**Why:** Qwen3-TTS's claimed 97 ms synthesis latency + same-family ecosystem
alignment with the LLM and embedding beat Orpheus-3B (v2 candidate),
Chatterbox-Turbo, and VoxCPM2 on the latency/simplicity axes. 3060 recovered
from Xid 79 (2026-04-19). Partitioning LLM off TTS/embedding removes SM
contention. 30B-A3B MoE gives 30 B-class quality at ~3 B active-params
inference cost.

**Trade-off:** 14 B `fast` tier no longer co-resides on 4090 — accepted
~2 s swap on first text-chat turn.

**Rollback:** `EMILY_VOICE_TTS=kokoro` + revert `llm/fleet.py` voice tier.

**Spec:** docs/superpowers/specs/2026-04-19-emily-dual-gpu-qwen-orpheus-design.md
**Plan:** docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus.md
```

- [ ] **Step 2: Commit**

```bash
cd ~/Emily1.0
git add .claude/CLAUDE-decisions.md
git commit -m "docs: ADR for Qwen3-TTS + Qwen3-30B-A3B voice upgrade"
```

---

### Task 17: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` (Model Tiers table, Voice Pipeline STT/TTS line, Critical Rule #15)

- [ ] **Step 1: Update fleet table `voice_fast` and `fast` rows**

Reflect 30B-A3B as voice tier; note 14 B swaps in/out.

- [ ] **Step 2: Rewrite Critical Rule #15 (VRAM)**

```markdown
15. **VRAM budget**: 36 GB total (4090 24GB + 3060 12GB).
    - **4090** (LLM + STT): voice LLM Qwen3-30B-A3B-abliterated Q4_K_M ~18 GB + Faster-Whisper fp16 ~1.5 GB = ~19.5 GB. 14 B `fast` tier swaps in/out on text-chat demand (~2 s cold start). Heavy tiers (27 B / 30 B-code / 32 B-reasoning / vision-31 B) evict the voice LLM on use.
    - **3060** (embed + TTS): qwen3-embedding 8 B ~5 GB always resident + Qwen3-TTS 1.7 B fp16 ~3.5 GB when voice path active = ~8.5 GB. ~3.5 GB headroom.
    - Do NOT set `CUDA_VISIBLE_DEVICES` on Ollama globally; heavy tiers still span GPUs.
    - Kokoro stays on CPU (fallback only).
```

- [ ] **Step 3: Update Voice Pipeline → STT/TTS Providers line**

```
STT: FasterWhisperSTT (CTranslate2, CUDA:0 fp16, distil-large-v3, ~140 ms).
TTS: Qwen3-TTS 1.7 B via qwen-tts on CUDA:1 (primary, 24 kHz, native streaming, 10 languages), Kokoro af_nicole CPU (fallback). Rollback: EMILY_VOICE_TTS=kokoro. Orpheus-3B GGUF on disk (dormant).
```

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add CLAUDE.md
git commit -m "docs: CLAUDE.md reflects dual-GPU Qwen voice upgrade"
```

---

### Task 18: Update `scripts/check_deps.py`

**Files:**
- Modify: `scripts/check_deps.py`

- [ ] **Step 1: Replace Orpheus checks with Qwen3-TTS**

Find the Orpheus block in `check_deps.py`. Replace `snac` and `llama_cpp` import checks with:

```python
def check_qwen_tts() -> bool:
    print("\n" + "=" * 60)
    print("4. TTS — Qwen3-TTS 1.7B (primary) + Kokoro (fallback)")
    print("=" * 60)
    ok = True
    try:
        import qwen_tts  # noqa: F401
        print("  ✓ qwen-tts installed")
    except ImportError:
        print("  ✗ qwen-tts not installed")
        print("    Install: uv add qwen-tts")
        ok = False
    try:
        import kokoro  # noqa: F401
        print("  ✓ kokoro installed (fallback)")
    except ImportError:
        print("  ✗ kokoro not installed (fallback unavailable)")
        ok = False
    return ok
```

Wire into the existing check sequence. Remove (or mark dormant) the Orpheus-specific snac/llama-cpp block.

- [ ] **Step 2: Run**

```bash
cd ~/Emily1.0
uv run python scripts/check_deps.py
```
Expected: all green.

- [ ] **Step 3: Commit**

```bash
cd ~/Emily1.0
git add scripts/check_deps.py
git commit -m "fix: check_deps reflects Qwen3-TTS primary, Orpheus dormant"
```

---

## Verification Checklist

- [ ] `uv run pytest tests/unit/voice_engine/ -v` — all pass
- [ ] `systemctl --user status emily.service` — active (running)
- [ ] `nvidia-smi` — 4090: voice LLM + Whisper; 3060: embedding + Qwen3-TTS
- [ ] `benchmarks/voice-dual-gpu-YYYY-MM-DD.json` — p50 ≤ 1000 ms, p95 ≤ 1600 ms
- [ ] Voice turn end-to-end: Emily responds in Qwen3-TTS voice
- [ ] `EMILY_VOICE_TTS=kokoro` + restart → Kokoro speaks
- [ ] `scripts/check_deps.py` green
- [ ] Git log shows ~18 small commits mapping to Tasks 1-18

---

**Rollback (mid-plan disaster):**
1. `git reset --hard <baseline-commit-from-Task-1>` (from `baseline-snapshot.md`)
2. `systemctl --user restart emily.service`
3. Verify Kokoro + 9 B voice path functional.
