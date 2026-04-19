# Emily Dual-GPU Voice: Qwen3-Abliterated + Orpheus TTS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Emily's voice path to Qwen3-30B-A3B-abliterated MoE (via Ollama, 4090-resident) with Orpheus-3B-0.1-ft TTS (in-process via `llama-cpp-python` + SNAC, 3060-resident) while preserving Kokoro fallback and all text-chat tiers.

**Architecture:** Single new TTS provider `OrpheusTTS` implementing the existing `TTSProvider` base contract. No new services, no HTTP servers for TTS — Orpheus GGUF loads in-process via `llama-cpp-python` pinned to `main_gpu=1`, SNAC decodes audio token codes to 24 kHz float32 PCM. Voice LLM swap is an Ollama tag change in `llm/fleet.py`. Whisper moves to CUDA:1 via config only (`stt_device_index=1`). Kokoro stays registered; env flag `EMILY_VOICE_TTS=kokoro` reverts TTS path.

**Tech Stack:** Python 3.11 + asyncio, `llama-cpp-python` (CUDA 12.4 wheel), `snac 1.2.1` (already installed), Ollama, Faster-Whisper (CTranslate2), pytest + pytest-asyncio (auto mode), uv, systemd --user.

**Spec:** `docs/superpowers/specs/2026-04-19-emily-dual-gpu-qwen-orpheus-design.md`

---

## Milestone M0 — Preparation & Dependencies

### Task 1: Snapshot the current state

**Files:**
- Create: `docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md`

- [ ] **Step 1: Capture GPU + model state**

Run:
```bash
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv > /tmp/emily-baseline-gpu.txt
ollama list > /tmp/emily-baseline-ollama.txt
ls -la ~/Emily1.0/models/orpheus-3b-0.1-ft-q4_k_m.gguf >> /tmp/emily-baseline-gpu.txt
~/Emily1.0/.venv/bin/python -c "import snac; print('snac', snac.__version__)" >> /tmp/emily-baseline-gpu.txt 2>&1
~/Emily1.0/.venv/bin/python -c "import llama_cpp; print('llama_cpp', llama_cpp.__version__)" >> /tmp/emily-baseline-gpu.txt 2>&1 || echo "llama_cpp MISSING" >> /tmp/emily-baseline-gpu.txt
```

- [ ] **Step 2: Write snapshot doc**

Create `docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md` containing the captured text plus today's date. Used for rollback reference.

- [ ] **Step 3: Commit**

```bash
cd ~/Emily1.0
git add docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/
git commit -m "docs: baseline snapshot for dual-GPU voice upgrade"
```

---

### Task 2: Install `llama-cpp-python` with CUDA wheel

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] **Step 1: Check current CUDA version on host**

Run:
```bash
nvidia-smi | grep -i "CUDA Version"
```
Expected: `CUDA Version: 12.x`. Note the major/minor — it selects the wheel index (`cu124`, `cu125`, etc.).

- [ ] **Step 2: Install llama-cpp-python with matching CUDA wheel**

Run (substitute `cu124` with the matching version from Step 1):
```bash
cd ~/Emily1.0
uv add llama-cpp-python \
  --index https://abetlen.github.io/llama-cpp-python/whl/cu124 \
  --index-strategy unsafe-best-match
```

Expected: `uv.lock` updates; `.venv/lib/python3.11/site-packages/llama_cpp/` exists.

- [ ] **Step 3: Verify CUDA support in the installed wheel**

Run:
```bash
~/Emily1.0/.venv/bin/python -c "
from llama_cpp import Llama, llama_supports_gpu_offload
print('GPU offload:', llama_supports_gpu_offload())
"
```
Expected: `GPU offload: True`. If False, the CPU-only wheel got picked — rerun Step 2 with an explicit `--reinstall`.

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add pyproject.toml uv.lock
git commit -m "deps: add llama-cpp-python with CUDA wheel for Orpheus TTS"
```

---

### Task 3: Pull Qwen3-30B-A3B-abliterated via Ollama (fallback ladder)

**Files:**
- Modify: `docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md` (append chosen tag)

- [ ] **Step 1: Try primary tag**

Run:
```bash
ollama pull huihui_ai/qwen3-abliterated:30b-a3b-q4_K_M
```
Expected: successful pull OR 404. If 404, continue to Step 2.

- [ ] **Step 2: Try alternate tags (R1 fallback ladder)**

If Step 1 failed, try in order until one succeeds:
```bash
ollama pull huihui_ai/qwen3-abliterated:30b
ollama pull qwen3-abliterated:30b-a3b
# As last resort:
ollama pull huihui_ai/qwen3-abliterated:14b
```

Record which tag succeeded.

- [ ] **Step 3: Verify model runs on 4090 only**

Run:
```bash
ollama run <chosen-tag> "Say hello in one short sentence." --verbose
```
While it runs, in another terminal:
```bash
nvidia-smi --query-compute-apps=gpu_uuid,process_name,used_memory --format=csv
```
Expected: model process appears only on GPU 0 (4090). If it spans GPUs, that's fine — Ollama manages layer placement.

- [ ] **Step 4: Append chosen tag to baseline snapshot**

Edit `docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md`: add a line `Chosen voice LLM tag: <tag>`.

- [ ] **Step 5: Commit**

```bash
cd ~/Emily1.0
git add docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md
git commit -m "docs: record chosen Qwen3-abliterated Ollama tag"
```

---

## Milestone M1 — SNAC Stream Decoder

### Task 4: Write failing test for `SNACStreamDecoder`

**Files:**
- Create: `tests/unit/voice_engine/providers/tts/__init__.py` (if missing)
- Create: `tests/unit/voice_engine/providers/tts/test_snac_stream_decoder.py`

- [ ] **Step 1: Ensure test package dirs exist**

Run:
```bash
cd ~/Emily1.0
mkdir -p tests/unit/voice_engine/providers/tts
touch tests/unit/voice_engine/providers/tts/__init__.py
```

- [ ] **Step 2: Write the test file**

Create `tests/unit/voice_engine/providers/tts/test_snac_stream_decoder.py`:

```python
"""Tests for the SNAC streaming decoder used by Orpheus TTS."""

from __future__ import annotations

import numpy as np
import pytest

from voice_engine.providers.tts.snac_stream_decoder import SNACStreamDecoder

SNAC_SAMPLE_RATE = 24000


def _fake_codes() -> list[list[int]]:
    """Return one Orpheus frame: 7 code positions, values in SNAC codebook range [0, 4095]."""
    # Small deterministic values that stay inside the codebook.
    return [[100 + i * 13 for i in range(7)]]


def test_decoder_initializes_on_cpu() -> None:
    decoder = SNACStreamDecoder(device="cpu")

    assert decoder.sample_rate == SNAC_SAMPLE_RATE
    assert decoder.device == "cpu"


def test_decode_frame_returns_nonempty_float32_pcm() -> None:
    decoder = SNACStreamDecoder(device="cpu")

    pcm = decoder.decode_frame(_fake_codes())

    assert isinstance(pcm, np.ndarray)
    assert pcm.dtype == np.float32
    assert pcm.ndim == 1
    assert pcm.size > 0
    assert np.all(np.abs(pcm) <= 1.5)  # SNAC usually outputs within [-1, 1]; small margin for numerical slack


def test_reset_clears_state_without_error() -> None:
    decoder = SNACStreamDecoder(device="cpu")
    decoder.decode_frame(_fake_codes())

    decoder.reset()  # must not raise

    pcm2 = decoder.decode_frame(_fake_codes())
    assert pcm2.size > 0


@pytest.mark.integration
def test_decoder_on_cuda1_if_available() -> None:
    import torch

    if not torch.cuda.is_available() or torch.cuda.device_count() < 2:
        pytest.skip("CUDA:1 not available")

    decoder = SNACStreamDecoder(device="cuda:1")
    pcm = decoder.decode_frame(_fake_codes())

    assert pcm.dtype == np.float32
    assert pcm.size > 0
```

- [ ] **Step 3: Run test — expect collection/import failure**

Run:
```bash
cd ~/Emily1.0
uv run pytest tests/unit/voice_engine/providers/tts/test_snac_stream_decoder.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'voice_engine.providers.tts.snac_stream_decoder'`.

- [ ] **Step 4: Commit the failing test**

```bash
cd ~/Emily1.0
git add tests/unit/voice_engine/providers/tts/
git commit -m "test: failing tests for SNAC stream decoder"
```

---

### Task 5: Implement `SNACStreamDecoder`

**Files:**
- Create: `voice_engine/providers/tts/snac_stream_decoder.py`

- [ ] **Step 1: Implement the decoder**

Create `voice_engine/providers/tts/snac_stream_decoder.py`:

```python
"""SNAC neural codec wrapper for streaming Orpheus TTS audio decoding.

Orpheus emits 7 SNAC code tokens per audio frame across 3 hierarchical
codebooks. We accept one full frame at a time, feed it to the SNAC model,
and return float32 PCM samples at 24 kHz.
"""

from __future__ import annotations

import numpy as np
import torch
from snac import SNAC  # type: ignore[import-untyped]

from observability.logger import get_logger

logger = get_logger(__name__)

SNAC_SAMPLE_RATE = 24000
SNAC_MODEL_ID = "hubertsiuzdak/snac_24khz"


class SNACStreamDecoder:
    """Decode Orpheus SNAC audio token frames to 24 kHz float32 PCM."""

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self.sample_rate = SNAC_SAMPLE_RATE
        logger.info("Loading SNAC model '%s' on %s ...", SNAC_MODEL_ID, device)
        self._model = SNAC.from_pretrained(SNAC_MODEL_ID).to(device).eval()
        logger.info("SNAC model ready on %s.", device)

    def decode_frame(self, codes: list[list[int]]) -> np.ndarray:
        """Decode one or more 7-token SNAC frames to PCM.

        Args:
            codes: A list of frames; each frame is a list of 7 integers from
                the SNAC codebook (as emitted by Orpheus).

        Returns:
            Float32 1-D PCM array at 24 kHz.
        """
        if not codes:
            return np.empty(0, dtype=np.float32)

        # Orpheus packing: 7 codes per frame map to 3 SNAC hierarchies [1, 2, 4] codes.
        level_0: list[int] = []  # coarse
        level_1: list[int] = []  # mid
        level_2: list[int] = []  # fine
        for frame in codes:
            if len(frame) != 7:
                msg = f"expected 7 codes per frame, got {len(frame)}"
                raise ValueError(msg)
            level_0.append(frame[0])
            level_1.extend([frame[1], frame[4]])
            level_2.extend([frame[2], frame[3], frame[5], frame[6]])

        t0 = torch.tensor([level_0], dtype=torch.int32, device=self.device)
        t1 = torch.tensor([level_1], dtype=torch.int32, device=self.device)
        t2 = torch.tensor([level_2], dtype=torch.int32, device=self.device)

        with torch.inference_mode():
            audio = self._model.decode([t0, t1, t2])  # shape: [1, 1, N]

        pcm = audio.squeeze().detach().cpu().numpy().astype(np.float32)
        return pcm

    def reset(self) -> None:
        """Reset any decoder state between sentences. SNAC itself is stateless; placeholder for future streaming state."""
        # SNAC has no persistent stream state; kept for API symmetry.
        return
```

- [ ] **Step 2: Run tests — expect pass**

Run:
```bash
cd ~/Emily1.0
uv run pytest tests/unit/voice_engine/providers/tts/test_snac_stream_decoder.py -v -m "not integration"
```
Expected: 3 passing tests. (The CUDA:1 test is marked `integration` and runs later.)

If SNAC's decode_frame packing is wrong for this Orpheus version, inspect the Canopy Labs example decoder in the `orpheus_tts` GitHub org and adjust the level split. Known alternate packing: `level_0=[c[0]]`, `level_1=[c[1], c[4]]`, `level_2=[c[2], c[3], c[5], c[6]]` (what's implemented). If Canopy's uses different, swap.

- [ ] **Step 3: Commit**

```bash
cd ~/Emily1.0
git add voice_engine/providers/tts/snac_stream_decoder.py
git commit -m "feat: SNAC stream decoder for Orpheus TTS"
```

---

## Milestone M2 — Orpheus TTS Provider

### Task 6: Write failing tests for `OrpheusTTS`

**Files:**
- Create: `tests/unit/voice_engine/providers/tts/test_orpheus_tts.py`

- [ ] **Step 1: Write the test file**

Create `tests/unit/voice_engine/providers/tts/test_orpheus_tts.py`:

```python
"""Tests for the Orpheus TTS provider (llama-cpp-python + SNAC)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice_engine.providers.tts.orpheus_tts import OrpheusTTS

ORPHEUS_SAMPLE_RATE = 24000


def _fake_orpheus_stream_chunks() -> list[dict]:
    """Mimic llama-cpp-python streaming output: a handful of audio-code tokens, then EOS."""
    # Orpheus emits special token IDs; llama-cpp yields dicts with 'choices'[0]['text'] = "<|audio_code:{n}|>"
    codes = [1234, 2345, 3456, 987, 654, 321, 1111]  # 7 codes = 1 SNAC frame
    chunks = [{"choices": [{"text": f"<|audio_code:{c}|>"}]} for c in codes]
    chunks.append({"choices": [{"text": "<|eot|>"}]})
    return chunks


def _install_llama_mock() -> MagicMock:
    mock_llama_instance = MagicMock()
    mock_llama_instance.create_completion.return_value = iter(_fake_orpheus_stream_chunks())
    return mock_llama_instance


@pytest.mark.asyncio
async def test_synthesize_empty_text_returns_empty_array() -> None:
    with patch("voice_engine.providers.tts.orpheus_tts.Llama") as mock_llama_cls, \
         patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder") as mock_decoder_cls:
        mock_llama_cls.return_value = _install_llama_mock()
        mock_decoder_cls.return_value.decode_frame.return_value = np.zeros(512, dtype=np.float32)
        mock_decoder_cls.return_value.sample_rate = ORPHEUS_SAMPLE_RATE

        tts = OrpheusTTS(model_path="/fake/path.gguf", voice="tara")
        audio = await tts.synthesize("   ")

    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.size == 0


@pytest.mark.asyncio
async def test_synthesize_returns_float32_pcm_24khz() -> None:
    with patch("voice_engine.providers.tts.orpheus_tts.Llama") as mock_llama_cls, \
         patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder") as mock_decoder_cls:
        mock_llama_cls.return_value = _install_llama_mock()
        mock_decoder_cls.return_value.decode_frame.return_value = np.linspace(-0.5, 0.5, 2048, dtype=np.float32)
        mock_decoder_cls.return_value.sample_rate = ORPHEUS_SAMPLE_RATE

        tts = OrpheusTTS(model_path="/fake/path.gguf", voice="tara")
        audio = await tts.synthesize("hello world")

    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert audio.size > 0


@pytest.mark.asyncio
async def test_synthesize_stream_yields_per_chunk() -> None:
    async def _text_chunks() -> AsyncIterator[str]:
        yield "First sentence."
        yield "Second one."

    with patch("voice_engine.providers.tts.orpheus_tts.Llama") as mock_llama_cls, \
         patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder") as mock_decoder_cls:
        # Return a fresh iterator per call so both sentences produce audio.
        def _new_stream(*_a, **_k):
            return iter(_fake_orpheus_stream_chunks())
        mock_llama_cls.return_value = MagicMock(create_completion=_new_stream)
        mock_decoder_cls.return_value.decode_frame.return_value = np.ones(1024, dtype=np.float32) * 0.1
        mock_decoder_cls.return_value.sample_rate = ORPHEUS_SAMPLE_RATE

        tts = OrpheusTTS(model_path="/fake/path.gguf", voice="tara")
        audios: list[np.ndarray] = []
        async for chunk in tts.synthesize_stream(_text_chunks()):
            audios.append(chunk)

    assert len(audios) == 2
    for a in audios:
        assert a.dtype == np.float32
        assert a.size > 0


@pytest.mark.asyncio
async def test_synthesize_stream_honors_cancellation() -> None:
    async def _text_chunks() -> AsyncIterator[str]:
        yield "this should be cancelled"
        await asyncio.sleep(1.0)  # never reached

    with patch("voice_engine.providers.tts.orpheus_tts.Llama") as mock_llama_cls, \
         patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder") as mock_decoder_cls:
        mock_llama_cls.return_value = _install_llama_mock()
        mock_decoder_cls.return_value.decode_frame.return_value = np.zeros(512, dtype=np.float32)
        mock_decoder_cls.return_value.sample_rate = ORPHEUS_SAMPLE_RATE

        tts = OrpheusTTS(model_path="/fake/path.gguf", voice="tara")

        async def _consume() -> None:
            async for _ in tts.synthesize_stream(_text_chunks()):
                pass

        task = asyncio.create_task(_consume())
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
```

- [ ] **Step 2: Run tests — expect import failure**

Run:
```bash
cd ~/Emily1.0
uv run pytest tests/unit/voice_engine/providers/tts/test_orpheus_tts.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'voice_engine.providers.tts.orpheus_tts'`.

- [ ] **Step 3: Commit failing tests**

```bash
cd ~/Emily1.0
git add tests/unit/voice_engine/providers/tts/test_orpheus_tts.py
git commit -m "test: failing tests for Orpheus TTS provider"
```

---

### Task 7: Implement `OrpheusTTS` provider

**Files:**
- Create: `voice_engine/providers/tts/orpheus_tts.py`

- [ ] **Step 1: Implement the provider**

Create `voice_engine/providers/tts/orpheus_tts.py`:

```python
"""Orpheus TTS provider — llama-cpp-python + SNAC, in-process, GPU-pinned."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import numpy as np
from llama_cpp import Llama  # type: ignore[import-untyped]

from observability.logger import get_logger
from voice_engine.providers.base import TTSProvider
from voice_engine.providers.tts.snac_stream_decoder import SNACStreamDecoder

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = get_logger(__name__)

ORPHEUS_SAMPLE_RATE = 24000
_AUDIO_CODE_RE = re.compile(r"<\|audio_code:(\d+)\|>")
_EOT_TOKEN = "<|eot|>"
_VALID_VOICES = {"tara", "leah", "jess", "leo", "dan", "mia", "zac", "zoe"}
_CODES_PER_FRAME = 7


class OrpheusTTS(TTSProvider):
    """Orpheus 3B GGUF inference (llama-cpp-python) with SNAC decoding."""

    def __init__(
        self,
        model_path: str,
        voice: str = "tara",
        main_gpu: int = 1,
        n_gpu_layers: int = -1,
        temperature: float = 0.6,
        top_p: float = 0.9,
        repetition_penalty: float = 1.1,
        max_tokens: int = 1200,
        snac_device: str = "cuda:1",
        n_ctx: int = 2048,
    ) -> None:
        if voice not in _VALID_VOICES:
            logger.warning("Unknown Orpheus voice %r; falling back to 'tara'", voice)
            voice = "tara"

        self._model_path = model_path
        self._voice = voice
        self._main_gpu = main_gpu
        self._n_gpu_layers = n_gpu_layers
        self._temperature = temperature
        self._top_p = top_p
        self._repetition_penalty = repetition_penalty
        self._max_tokens = max_tokens
        self._snac_device = snac_device
        self._n_ctx = n_ctx

        self._llm: Llama | None = None
        self._decoder: SNACStreamDecoder | None = None
        logger.info(
            "OrpheusTTS configured: voice=%s main_gpu=%d snac=%s model=%s",
            voice, main_gpu, snac_device, model_path,
        )

    def set_voice(self, voice: str) -> None:
        if voice in _VALID_VOICES:
            self._voice = voice
            logger.info("OrpheusTTS voice changed to %s", voice)
        else:
            logger.warning("Ignoring unknown Orpheus voice: %s", voice)

    def _ensure_loaded(self) -> tuple[Llama, SNACStreamDecoder]:
        if self._llm is None:
            logger.info("Loading Orpheus GGUF: %s (main_gpu=%d)", self._model_path, self._main_gpu)
            self._llm = Llama(
                model_path=self._model_path,
                n_gpu_layers=self._n_gpu_layers,
                main_gpu=self._main_gpu,
                n_ctx=self._n_ctx,
                logits_all=False,
                verbose=False,
            )
            logger.info("Orpheus GGUF loaded.")
        if self._decoder is None:
            self._decoder = SNACStreamDecoder(device=self._snac_device)
        return self._llm, self._decoder

    def _build_prompt(self, text: str) -> str:
        # Canopy Labs Orpheus prompt format.
        return f"<custom_token_3><|audio|>{self._voice}: {text}<|eot|>"

    def _synthesize_sync(self, text: str) -> np.ndarray:
        text = text.strip()
        if not text:
            return np.empty(0, dtype=np.float32)

        llm, decoder = self._ensure_loaded()
        prompt = self._build_prompt(text)

        stream = llm.create_completion(
            prompt=prompt,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            top_p=self._top_p,
            repeat_penalty=self._repetition_penalty,
            stream=True,
            stop=[_EOT_TOKEN],
        )

        pcm_parts: list[np.ndarray] = []
        code_buffer: list[int] = []
        for chunk in stream:
            piece = chunk["choices"][0]["text"] or ""
            if _EOT_TOKEN in piece:
                break
            for match in _AUDIO_CODE_RE.finditer(piece):
                code_buffer.append(int(match.group(1)))
                if len(code_buffer) == _CODES_PER_FRAME:
                    pcm_parts.append(decoder.decode_frame([code_buffer]))
                    code_buffer = []

        if not pcm_parts:
            logger.warning("Orpheus produced no audio for: %s", text[:60])
            return np.empty(0, dtype=np.float32)

        return np.concatenate(pcm_parts)

    async def synthesize(self, text: str) -> np.ndarray:
        if not text.strip():
            return np.empty(0, dtype=np.float32)
        loop = asyncio.get_running_loop()
        audio = await loop.run_in_executor(None, self._synthesize_sync, text)
        logger.debug("Orpheus synthesized %d samples for: %s", len(audio), text[:60])
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
```

- [ ] **Step 2: Run the unit tests**

Run:
```bash
cd ~/Emily1.0
uv run pytest tests/unit/voice_engine/providers/tts/test_orpheus_tts.py -v
```
Expected: 4 passing tests.

- [ ] **Step 3: Standalone smoke test (real model)**

Create and run:
```bash
cat > /tmp/orpheus_smoke.py <<'EOF'
import asyncio
import wave
import numpy as np
from voice_engine.providers.tts.orpheus_tts import OrpheusTTS

async def main() -> None:
    tts = OrpheusTTS(
        model_path="models/orpheus-3b-0.1-ft-q4_k_m.gguf",
        voice="tara",
        main_gpu=1,
        snac_device="cuda:1",
    )
    pcm = await tts.synthesize("Hello, this is Emily speaking through Orpheus.")
    print(f"Got {len(pcm)} samples ({len(pcm)/24000:.2f}s)")
    pcm16 = np.clip(pcm * 32767, -32768, 32767).astype(np.int16)
    with wave.open("/tmp/orpheus_smoke.wav", "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000)
        f.writeframes(pcm16.tobytes())
    print("wrote /tmp/orpheus_smoke.wav")

asyncio.run(main())
EOF
cd ~/Emily1.0
uv run python /tmp/orpheus_smoke.py
aplay /tmp/orpheus_smoke.wav  # or any 24 kHz-capable player
```
Expected: audible speech saying "Hello, this is Emily speaking through Orpheus." If garbled, the SNAC frame packing (Task 5) may need adjustment.

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add voice_engine/providers/tts/orpheus_tts.py
git commit -m "feat: Orpheus TTS provider (llama-cpp-python + SNAC)"
```

---

## Milestone M3 — Config, Factory, Whisper Pin, LLM Swap

### Task 8: Extend `VoiceEngineConfig` with Orpheus fields

**Files:**
- Modify: `voice_engine/config.py:55-57`
- Modify: `voice_engine/config.py:40-45`
- Create: `tests/unit/voice_engine/test_config_orpheus.py`

- [ ] **Step 1: Write failing config test**

Create `tests/unit/voice_engine/test_config_orpheus.py`:

```python
"""Tests for Orpheus-related config fields."""

from __future__ import annotations

from voice_engine.config import VoiceEngineConfig


def test_default_tts_provider_is_orpheus() -> None:
    cfg = VoiceEngineConfig()

    assert cfg.tts_provider == "orpheus"
    assert cfg.tts_fallback == "kokoro"
    assert cfg.tts_voice == "tara"


def test_default_orpheus_model_path_points_to_shipped_gguf() -> None:
    cfg = VoiceEngineConfig()

    assert cfg.orpheus_model_path.endswith("orpheus-3b-0.1-ft-q4_k_m.gguf")
    assert cfg.orpheus_main_gpu == 1
    assert cfg.orpheus_snac_device == "cuda:1"


def test_stt_defaults_pin_whisper_to_cuda1_int8() -> None:
    cfg = VoiceEngineConfig()

    assert cfg.stt_device == "cuda"
    assert cfg.stt_device_index == 1
    assert cfg.stt_compute_type == "int8"
```

Run (expect FAIL):
```bash
uv run pytest tests/unit/voice_engine/test_config_orpheus.py -v
```

- [ ] **Step 2: Update `voice_engine/config.py`**

Replace lines 40–57 (the STT and TTS blocks). Apply this exact edit:

OLD STT block (lines 40–45):
```python
    # ── STT ────────────────────────────────────────
    stt_provider: str = Field(default="faster_whisper", description="STT provider name")
    stt_model: str = Field(default="distil-large-v3", description="STT model identifier")
    stt_device: str = Field(default="cuda", description="STT device: 'cuda' or 'cpu'")
    stt_device_index: int = Field(default=0, description="CUDA device index: 0=4090, 1=3060")
    stt_compute_type: str = Field(default="float16", description="STT compute type: 'float16', 'int8', 'int8_float16'")
```

NEW STT block:
```python
    # ── STT ────────────────────────────────────────
    stt_provider: str = Field(default="faster_whisper", description="STT provider name")
    stt_model: str = Field(default="distil-large-v3", description="STT model identifier")
    stt_device: str = Field(default="cuda", description="STT device: 'cuda' or 'cpu'")
    stt_device_index: int = Field(default=1, description="CUDA device index: 0=4090, 1=3060 (dual-GPU partition)")
    stt_compute_type: str = Field(default="int8", description="STT compute type: 'float16', 'int8', 'int8_float16'")
```

OLD TTS block (lines 55–57):
```python
    # ── TTS (Kokoro only) ─────────────────────────
    tts_provider: str = Field(default="kokoro", description="TTS provider (kokoro)")
    tts_voice: str = Field(default="af_nicole", description="Kokoro voice identifier")
```

NEW TTS block:
```python
    # ── TTS (Orpheus primary, Kokoro fallback) ────
    tts_provider: str = Field(default="orpheus", description="TTS provider: 'orpheus' or 'kokoro'")
    tts_fallback: str = Field(default="kokoro", description="TTS provider used if primary fails to load")
    tts_voice: str = Field(default="tara", description="Voice identifier (Orpheus: tara/leah/jess/leo/dan/mia/zac/zoe; Kokoro: af_nicole etc.)")
    orpheus_model_path: str = Field(
        default="models/orpheus-3b-0.1-ft-q4_k_m.gguf",
        description="Path to the Orpheus GGUF file (relative to Emily root)",
    )
    orpheus_main_gpu: int = Field(default=1, description="CUDA device index for Orpheus GGUF (1 = 3060)")
    orpheus_snac_device: str = Field(
        default="cuda:1",
        description="Torch device for SNAC decoding ('cuda:1' or 'cpu')",
    )
```

- [ ] **Step 3: Run tests — expect pass**

Run:
```bash
cd ~/Emily1.0
uv run pytest tests/unit/voice_engine/test_config_orpheus.py -v
```
Expected: 3 passing.

- [ ] **Step 4: Check `config.yaml` doesn't override the new defaults**

Run:
```bash
cd ~/Emily1.0
/usr/bin/grep -nE "tts_provider|tts_voice|stt_device_index|stt_compute_type|orpheus" config.yaml
```

If `config.yaml` has an explicit `voice_engine.tts_provider: kokoro` or similar: update those values to match the new defaults (or remove the overrides to let defaults apply). Add the new keys:

```yaml
voice_engine:
  tts_provider: orpheus
  tts_fallback: kokoro
  tts_voice: tara
  stt_device: cuda
  stt_device_index: 1
  stt_compute_type: int8
  orpheus_model_path: models/orpheus-3b-0.1-ft-q4_k_m.gguf
  orpheus_main_gpu: 1
  orpheus_snac_device: cuda:1
```

If `config.yaml` has no `voice_engine` section or no TTS keys, skip this edit — defaults will apply.

- [ ] **Step 5: Commit**

```bash
cd ~/Emily1.0
git add voice_engine/config.py tests/unit/voice_engine/test_config_orpheus.py config.yaml
git commit -m "feat: voice config defaults for Orpheus TTS and CUDA:1 Whisper"
```

---

### Task 9: Wire `orpheus` into `ProviderFactory`

**Files:**
- Modify: `voice_engine/providers/factory.py:95-105`
- Create: `tests/unit/voice_engine/providers/test_factory_orpheus.py`

- [ ] **Step 1: Write failing factory test**

Create `tests/unit/voice_engine/providers/test_factory_orpheus.py`:

```python
"""Tests that ProviderFactory returns OrpheusTTS for the orpheus config."""

from __future__ import annotations

from unittest.mock import patch

from voice_engine.config import VoiceEngineConfig
from voice_engine.providers.factory import ProviderFactory


def test_factory_returns_orpheus_tts_for_orpheus_config() -> None:
    cfg = VoiceEngineConfig(tts_provider="orpheus")

    # We don't want to actually load llama-cpp + SNAC in this unit test.
    with patch("voice_engine.providers.tts.orpheus_tts.Llama"), \
         patch("voice_engine.providers.tts.orpheus_tts.SNACStreamDecoder"):
        provider = ProviderFactory.create_tts(cfg)

    assert provider.__class__.__name__ == "OrpheusTTS"


def test_factory_still_returns_kokoro_for_kokoro_config() -> None:
    cfg = VoiceEngineConfig(tts_provider="kokoro")
    provider = ProviderFactory.create_tts(cfg)

    assert provider.__class__.__name__ == "KokoroTTS"


def test_factory_raises_on_unknown_tts() -> None:
    cfg = VoiceEngineConfig(tts_provider="wav2voice_9000")

    try:
        ProviderFactory.create_tts(cfg)
    except ValueError as e:
        assert "wav2voice_9000" in str(e)
    else:
        msg = "ValueError not raised for unknown TTS"
        raise AssertionError(msg)
```

Run (expect FAIL):
```bash
uv run pytest tests/unit/voice_engine/providers/test_factory_orpheus.py -v
```

- [ ] **Step 2: Modify `voice_engine/providers/factory.py`**

Replace the `create_tts` body (lines 95–105). Apply:

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

        if name == "orpheus":
            from voice_engine.providers.tts.orpheus_tts import OrpheusTTS

            return OrpheusTTS(
                model_path=config.orpheus_model_path,
                voice=config.tts_voice,
                main_gpu=config.orpheus_main_gpu,
                snac_device=config.orpheus_snac_device,
            )

        if name in ("kokoro", "tiered"):
            from voice_engine.providers.tts.kokoro_tts import KokoroTTS

            return KokoroTTS(voice=config.tts_voice)

        raise ValueError(f"Unknown TTS provider: {name!r}. Supported: 'orpheus', 'kokoro'.")
```

- [ ] **Step 3: Run tests — expect pass**

Run:
```bash
cd ~/Emily1.0
uv run pytest tests/unit/voice_engine/providers/test_factory_orpheus.py -v
```
Expected: 3 passing.

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add voice_engine/providers/factory.py tests/unit/voice_engine/providers/test_factory_orpheus.py
git commit -m "feat: wire Orpheus TTS into ProviderFactory"
```

---

### Task 10: Honor `EMILY_VOICE_TTS` env flag in `emily_server.py`

**Files:**
- Modify: `emily_server.py` (near the TTS provider creation site — grep for `create_tts` or `VoiceEngineConfig`)

- [ ] **Step 1: Locate the provider instantiation in `emily_server.py`**

Run:
```bash
cd ~/Emily1.0
/usr/bin/grep -n "create_tts\|tts_provider\|VoiceEngineConfig" emily_server.py | head -20
```

Note the line numbers where TTS config / provider creation happens.

- [ ] **Step 2: Add env flag override**

Find the location where `VoiceEngineConfig()` is instantiated (or where `config.tts_provider` is first consulted). Before that point, apply:

```python
import os

_tts_override = os.environ.get("EMILY_VOICE_TTS", "").strip().lower()
if _tts_override in ("orpheus", "kokoro"):
    # Let pydantic-settings pick it up via env.
    os.environ["tts_provider"] = _tts_override
    logger.info("EMILY_VOICE_TTS override active: %s", _tts_override)
```

(The `VoiceEngineConfig` already uses `env_file=".env"` with pydantic-settings — setting `os.environ["tts_provider"]` at process start before the first `VoiceEngineConfig()` call propagates it.)

If `emily_server.py` uses `from config import get_settings` (the Pydantic v2 settings) instead of `VoiceEngineConfig` directly, the same override approach works — just ensure it runs before `get_settings()`.

- [ ] **Step 3: Smoke test the override**

```bash
cd ~/Emily1.0
EMILY_VOICE_TTS=kokoro uv run python -c "
from voice_engine.config import VoiceEngineConfig
import os
os.environ['tts_provider'] = os.environ.get('EMILY_VOICE_TTS', '')
cfg = VoiceEngineConfig()
print('tts_provider =', cfg.tts_provider)
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

### Task 11: Update `llm/fleet.py` voice_fast tier model name

**Files:**
- Modify: `llm/fleet.py` (find `voice_fast` tier definition)

- [ ] **Step 1: Locate voice_fast tier**

Run:
```bash
cd ~/Emily1.0
/usr/bin/grep -n "voice_fast\|VOICE_FAST\|qwen3.*9\|qwen3.5" llm/fleet.py | head -20
```

Note the exact line(s) defining the model name for the voice_fast tier.

- [ ] **Step 2: Swap in the Qwen3-30B-A3B-abliterated tag**

Edit the tier definition — replace the current Qwen3.5-abliterated 9B tag with the tag you pulled in Task 3 (e.g., `huihui_ai/qwen3-abliterated:30b-a3b-q4_K_M` or whichever succeeded in the fallback ladder). Keep `keep_alive=30m` and all other tier params unchanged.

- [ ] **Step 3: Verify tier loads**

Run:
```bash
cd ~/Emily1.0
uv run python -c "
from llm.fleet import LLMFleet
fleet = LLMFleet()
print('voice_fast tier →', fleet.tier_model('voice_fast') if hasattr(fleet, 'tier_model') else 'inspect fleet object directly')
"
```
(Adjust to the actual fleet API; intent is to print the configured model for voice_fast.)

Then run:
```bash
ollama ps
```
Expected: the new tag appears or can be warmed on first request.

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add llm/fleet.py
git commit -m "feat: voice_fast tier → Qwen3-30B-A3B-abliterated (MoE, 4090)"
```

---

## Milestone M4 — End-to-End Integration & Fallback

### Task 12: End-to-end voice turn smoke test

**Files:** (no code changes — validation only)

- [ ] **Step 1: Restart Emily**

```bash
systemctl --user restart emily.service
sleep 5
systemctl --user status emily.service --no-pager
```
Expected: active (running). No crash loop.

- [ ] **Step 2: Monitor logs for provider init**

```bash
journalctl --user -u emily.service -n 200 --no-pager | /usr/bin/grep -iE "orpheus|snac|whisper|voice_fast|qwen3"
```
Expected: `OrpheusTTS configured`, `Loading Orpheus GGUF`, `SNAC model ready on cuda:1`, `FasterWhisperSTT configured: model=distil-large-v3 device=cuda:1`, voice_fast tier model = the new tag.

- [ ] **Step 3: Verify GPU allocation**

```bash
nvidia-smi --query-compute-apps=gpu_uuid,process_name,used_memory --format=csv
```
Expected:
- GPU 0 (4090): ollama with the large MoE model (~18 GB)
- GPU 1 (3060): ollama (embedding, ~5 GB) + Emily python (Orpheus + Whisper, ~5–6 GB)
- Zero unintended fragmentation.

- [ ] **Step 4: Trigger a voice turn (manual)**

Say into the echo-cancelled mic: "Emily, say hello."

Watch logs:
```bash
journalctl --user -u emily.service -f
```
Expected: STT → LLM stream → Orpheus synthesize → audible response.

If no audio: check `output_device` in `config.yaml` (see CLAUDE.md audio device setup).

- [ ] **Step 5: Record outcome in session notes**

Append result to `docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md`:
```
## M4 smoke result (YYYY-MM-DD)
- Emily voice turn end-to-end: PASS/FAIL
- Observed first-audio latency (eyeballed): ~N seconds
- Notes: ...
```

- [ ] **Step 6: Commit**

```bash
cd ~/Emily1.0
git add docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md
git commit -m "docs: M4 end-to-end smoke result"
```

---

### Task 13: Fallback to Kokoro if Orpheus init fails

**Files:**
- Modify: `voice_engine/providers/factory.py` (add try/except around Orpheus construction)

- [ ] **Step 1: Write failing test**

Append to `tests/unit/voice_engine/providers/test_factory_orpheus.py`:

```python
def test_factory_falls_back_to_kokoro_on_orpheus_init_failure() -> None:
    from unittest.mock import patch

    cfg = VoiceEngineConfig(tts_provider="orpheus", tts_fallback="kokoro")

    with patch(
        "voice_engine.providers.tts.orpheus_tts.OrpheusTTS.__init__",
        side_effect=RuntimeError("simulated model load failure"),
    ):
        provider = ProviderFactory.create_tts(cfg)

    assert provider.__class__.__name__ == "KokoroTTS"
```

Run (expect FAIL):
```bash
uv run pytest tests/unit/voice_engine/providers/test_factory_orpheus.py::test_factory_falls_back_to_kokoro_on_orpheus_init_failure -v
```

- [ ] **Step 2: Add fallback in factory**

Edit `voice_engine/providers/factory.py`. Replace the `orpheus` branch inside `create_tts`:

OLD:
```python
        if name == "orpheus":
            from voice_engine.providers.tts.orpheus_tts import OrpheusTTS

            return OrpheusTTS(
                model_path=config.orpheus_model_path,
                voice=config.tts_voice,
                main_gpu=config.orpheus_main_gpu,
                snac_device=config.orpheus_snac_device,
            )
```

NEW:
```python
        if name == "orpheus":
            from voice_engine.providers.tts.orpheus_tts import OrpheusTTS

            try:
                return OrpheusTTS(
                    model_path=config.orpheus_model_path,
                    voice=config.tts_voice,
                    main_gpu=config.orpheus_main_gpu,
                    snac_device=config.orpheus_snac_device,
                )
            except Exception:
                logger.exception(
                    "OrpheusTTS failed to initialize; falling back to %s",
                    config.tts_fallback,
                )
                if config.tts_fallback == "kokoro":
                    from voice_engine.providers.tts.kokoro_tts import KokoroTTS

                    return KokoroTTS(voice="af_nicole")
                raise
```

- [ ] **Step 3: Run tests — expect pass**

Run:
```bash
cd ~/Emily1.0
uv run pytest tests/unit/voice_engine/providers/test_factory_orpheus.py -v
```
Expected: 4 passing.

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add voice_engine/providers/factory.py tests/unit/voice_engine/providers/test_factory_orpheus.py
git commit -m "feat: fall back to Kokoro when Orpheus init fails"
```

---

### Task 14: Barge-in cancellation smoke test

**Files:** (manual validation only)

- [ ] **Step 1: Trigger barge-in manually**

Restart Emily:
```bash
systemctl --user restart emily.service
```

Say: "Emily, tell me a long story about a dragon who..."

While Emily is responding, interrupt her mid-sentence with: "Stop."

- [ ] **Step 2: Verify clean cancellation in logs**

```bash
journalctl --user -u emily.service -n 300 --no-pager | /usr/bin/grep -iE "interrupt|cancel|barge"
```
Expected: `InterruptionHandler` fires, Orpheus synthesis task gets `CancelledError`, pipeline returns to `LISTENING`.

Unexpected: Orpheus process hangs or Emily keeps speaking over the user — indicates the cancellation path isn't reaching the llama-cpp thread. In that case, wrap `_synthesize_sync` calls in `asyncio.shield`-aware cleanup (future work, out of scope here).

- [ ] **Step 3: Record outcome**

Append to baseline-snapshot doc. Commit.

```bash
cd ~/Emily1.0
git add docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md
git commit -m "docs: M4 barge-in smoke result"
```

---

## Milestone M5 — Benchmark & SLO

### Task 15: Write `scripts/benchmark_voice_dual_gpu.py`

**Files:**
- Create: `scripts/benchmark_voice_dual_gpu.py`

- [ ] **Step 1: Create the benchmark script**

```python
"""End-to-end voice-pipeline latency benchmark for the dual-GPU setup.

Measures per-stage timings over a fixed prompt set and writes a JSON report
to benchmarks/voice-dual-gpu-YYYY-MM-DD.json.

NOTE: This drives the TTS+LLM stages directly; STT is simulated by handing
pre-transcribed prompts to the pipeline. Measure STT separately via
scripts/benchmark_stt.py (existing) if needed.
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
    ("medium", "Explain how a transformer model works in two sentences."),
    ("medium", "What's the difference between HTTP/2 and HTTP/3?"),
    ("code", "Write a Python function that reverses a string."),
    ("code", "How do you open a file in binary mode in Rust?"),
    ("emotional", "I had a really hard day. Can you say something kind?"),
    ("emotional", "I just got amazing news and I want to celebrate!"),
    ("long", "Summarize the plot of Hamlet in four sentences."),
    ("long", "Describe the architecture of the Linux kernel's scheduler."),
]
TURNS_PER_PROMPT = 3  # 10 prompts × 3 = 30 turns


async def run() -> dict:
    cfg = VoiceEngineConfig()
    llm = ProviderFactory.create_llm(cfg)
    tts = ProviderFactory.create_tts(cfg)

    results: list[dict] = []
    system_prompt = cfg.get_system_prompt()

    for _ in range(TURNS_PER_PROMPT):
        for category, text in PROMPTS:
            t_user_end = time.perf_counter()

            # LLM first-token + full stream + sentence split
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

            # TTS first-audio latency — synthesize the full response as one piece.
            t_tts_start = time.perf_counter()
            audio = await tts.synthesize(full_response[:300])
            t_first_audio = time.perf_counter()

            results.append({
                "category": category,
                "prompt": text,
                "response_chars": len(full_response),
                "audio_samples": int(audio.size),
                "ms_first_token": ((first_tok_t or t_llm_end) - t_user_end) * 1000,
                "ms_llm_complete": (t_llm_end - t_user_end) * 1000,
                "ms_first_audio": (t_first_audio - t_tts_start) * 1000,
                "ms_total_end_to_end": (t_first_audio - t_user_end) * 1000,
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
    out_path = out_dir / f"voice-dual-gpu-{today}.json"

    report = asyncio.run(run())
    out_path.write_text(json.dumps(report, indent=2))
    print(f"Wrote {out_path}")
    print(f"p50 total: {report['summary']['p50_ms_total']:.0f} ms")
    print(f"p95 total: {report['summary']['p95_ms_total']:.0f} ms")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the benchmark**

```bash
cd ~/Emily1.0
uv run python scripts/benchmark_voice_dual_gpu.py
```
Expected: creates `benchmarks/voice-dual-gpu-YYYY-MM-DD.json`, prints p50 and p95.

- [ ] **Step 3: Verify SLO**

Open the report. Required for pass:
- `p50_ms_total` ≤ 1000
- `p95_ms_total` ≤ 1600

If the SLO fails:
- Check if the LLM model is loaded and warm (`ollama ps`, keep_alive=30m).
- Check if SNAC is actually on CUDA:1 (`nvidia-smi` during run).
- Try switching `orpheus_snac_device` to `cpu`; re-run. Pick the faster.

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add scripts/benchmark_voice_dual_gpu.py benchmarks/
git commit -m "feat: dual-GPU voice benchmark harness + first report"
```

---

### Task 16: Lock SNAC device choice (CUDA:1 vs CPU)

**Files:**
- Modify: `voice_engine/config.py` (only if CPU wins)

- [ ] **Step 1: Re-run benchmark with CPU SNAC**

Run:
```bash
cd ~/Emily1.0
EMILY__ORPHEUS_SNAC_DEVICE=cpu uv run python scripts/benchmark_voice_dual_gpu.py
```
(Name of the env override depends on pydantic-settings env_prefix — verify. If needed, edit `config.yaml` temporarily and restart.)

- [ ] **Step 2: Compare p50/p95 with Task 15 report**

If CPU is ≥ 10% faster: change default in `voice_engine/config.py`:

```python
orpheus_snac_device: str = Field(default="cpu", description="...")
```

If CUDA:1 is better or within noise (≤10%): leave `cuda:1` default.

- [ ] **Step 3: Record decision**

Append to baseline-snapshot doc: `SNAC device chosen: cuda:1 | cpu. Rationale: ...`

- [ ] **Step 4: Commit (if config changed)**

```bash
cd ~/Emily1.0
git add voice_engine/config.py docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus/baseline-snapshot.md
git commit -m "perf: lock SNAC device based on benchmark"
```

---

## Milestone M6 — Documentation

### Task 17: Update `ABLITERATED_SETUP.md`

**Files:**
- Modify: `ABLITERATED_SETUP.md`

- [ ] **Step 1: Update the fleet table**

Edit the "Model Fleet (All Abliterated)" table. Change the `voice_fast` row to reference Qwen3-30B-A3B-abliterated Q4_K_M on Ollama, VRAM ~18 GB, and note co-residency with 14B is no longer possible on 4090.

- [ ] **Step 2: Add Orpheus TTS section**

After the model fleet table, add:

```markdown
## Voice Output — Orpheus TTS (primary)

Emily's voice path uses Orpheus-3B-0.1-ft (Canopy Labs) as the primary TTS,
Kokoro as fallback. Orpheus runs in-process via `llama-cpp-python` on CUDA:1
(RTX 3060), SNAC decodes audio tokens to 24 kHz PCM.

- Model: `models/orpheus-3b-0.1-ft-q4_k_m.gguf` (Q4_K_M, ~2.4 GB on disk, ~3.5 GB VRAM)
- Voices: tara (default), leah, jess, leo, dan, mia, zac, zoe
- Rollback: `EMILY_VOICE_TTS=kokoro` → restart `emily.service`
```

- [ ] **Step 3: Commit**

```bash
cd ~/Emily1.0
git add ABLITERATED_SETUP.md
git commit -m "docs: ABLITERATED_SETUP reflects Qwen3-30B-A3B voice + Orpheus TTS"
```

---

### Task 18: Append ADR to `.claude/CLAUDE-decisions.md`

**Files:**
- Modify: `.claude/CLAUDE-decisions.md`

- [ ] **Step 1: Append an ADR block**

Add at the bottom:

```markdown
## ADR 2026-04-19 — Dual-GPU Voice: Qwen3-30B-A3B Abliterated + Orpheus TTS

**Decision:** Voice LLM is Qwen3-30B-A3B-abliterated (MoE Q4_K_M) via Ollama
on the RTX 4090. Voice TTS is Orpheus-3B-0.1-ft via llama-cpp-python on the
RTX 3060, alongside the existing qwen3-embedding 8B and Faster-Whisper
(distil-large-v3 int8, also pinned to CUDA:1). Kokoro remains as fallback.

**Why:** 3060 recovered from Xid 79 (confirmed 2026-04-19). Partitioning the
LLM off the TTS+STT GPU removes SM contention, enables MoE voice model with
30B quality at ~3B active-params latency, and upgrades voice prosody via
Orpheus's emotional token support. Tradeoff: 14B `fast` tier can no longer
co-reside with the voice LLM on 4090 — accepted as ~2s cold-start on text
chat first use.

**Rollback:** `EMILY_VOICE_TTS=kokoro` + revert `llm/fleet.py` voice_fast
model name. All new code is additive + feature-flagged.

**Spec:** `docs/superpowers/specs/2026-04-19-emily-dual-gpu-qwen-orpheus-design.md`
**Plan:** `docs/superpowers/plans/2026-04-19-emily-dual-gpu-qwen-orpheus.md`
```

- [ ] **Step 2: Commit**

```bash
cd ~/Emily1.0
git add .claude/CLAUDE-decisions.md
git commit -m "docs: ADR for dual-GPU voice with Qwen3-30B-A3B + Orpheus"
```

---

### Task 19: Update `CLAUDE.md` fleet table and VRAM rule

**Files:**
- Modify: `CLAUDE.md` (Model Tiers table + Critical Rule #15)

- [ ] **Step 1: Update the Model Tiers table**

Edit the `voice_fast` and `fast` rows to reflect the new arrangement. Add an "Orpheus" entry to the TTS description in the Voice Pipeline section, promoting it from "available" to primary.

- [ ] **Step 2: Rewrite Critical Rule #15 (VRAM)**

Replace the current rule with:

```markdown
15. **VRAM budget**: 36 GB total (4090 24GB + 3060 12GB).
    - **4090** (LLM-only): voice LLM Qwen3-30B-A3B-abliterated Q4_K_M ~18 GB resident; 14B `fast` tier swaps in/out on text-chat demand (~2 s cold start). Heavy tiers (27B/30B-code/32B-reasoning/vision-31B) evict the voice model on use.
    - **3060** (embed + TTS + STT): qwen3-embedding 8B ~5 GB always resident; Orpheus-3B Q4_K_M ~3.5 GB resident during voice path; Faster-Whisper int8 ~2 GB resident. Total ~10.5 GB / 12 GB — 1.5 GB headroom. If OOM: first mitigation is moving embedding to 4090.
    - Do NOT set `CUDA_VISIBLE_DEVICES` on Ollama globally; the 27B/32B text-chat tiers still need both GPUs for layer offload.
    - Kokoro stays on CPU (fallback only).
```

- [ ] **Step 3: Update the Voice Pipeline → STT/TTS Providers paragraph**

Change the TTS line to:
```
TTS: Orpheus-3B-0.1-ft via llama-cpp-python + SNAC on CUDA:1 (primary, tara voice default), Kokoro af_nicole on CPU (fallback). Sample rate: 24000 Hz across all TTS providers. Rollback flag: EMILY_VOICE_TTS=kokoro.
```

- [ ] **Step 4: Commit**

```bash
cd ~/Emily1.0
git add CLAUDE.md
git commit -m "docs: CLAUDE.md reflects dual-GPU voice upgrade"
```

---

### Task 20: Close the loop — update `scripts/check_deps.py` if needed

**Files:**
- Modify: `scripts/check_deps.py` (only if the current output misrepresents Orpheus readiness)

- [ ] **Step 1: Run the checker**

```bash
cd ~/Emily1.0
uv run python scripts/check_deps.py
```
Expected: all ✓ for Orpheus deps (snac, llama-cpp-python, GGUF file present).

- [ ] **Step 2: Fix any false-negatives**

If the checker reports Orpheus as unavailable despite being live, trace the import it's trying. Patch the check to match the actual import path (`voice_engine.providers.tts.orpheus_tts`).

- [ ] **Step 3: Commit (only if changes made)**

```bash
cd ~/Emily1.0
git add scripts/check_deps.py
git commit -m "fix: check_deps correctly detects Orpheus readiness"
```

---

## Verification Checklist (after M6)

- [ ] `uv run pytest tests/unit/voice_engine/ -v` — all tests pass
- [ ] `systemctl --user status emily.service` — active (running)
- [ ] `nvidia-smi` — 4090 shows voice LLM; 3060 shows embedding + Orpheus + Whisper
- [ ] `benchmarks/voice-dual-gpu-YYYY-MM-DD.json` — p50 ≤ 1000 ms, p95 ≤ 1600 ms
- [ ] Spoken voice turn end-to-end: Emily responds with Orpheus voice
- [ ] `EMILY_VOICE_TTS=kokoro systemctl --user restart emily.service` → Kokoro path resumes
- [ ] `scripts/check_deps.py` — green
- [ ] `git log --oneline` shows ~20 small commits mapping to Tasks 1–20

---

**Rollback (if mid-plan disaster):**
1. `git reset --hard <baseline-commit-hash-from-Task-1>` (consult `baseline-snapshot.md`)
2. `systemctl --user restart emily.service`
3. Verify Kokoro + 9B voice path functional.
