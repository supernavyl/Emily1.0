"""
TTS streaming engine for Emily.

Implements a multi-tier TTS system driven by ``config.yaml``:
  - CSM    — Sesame Conversational Speech Model, highest conversational quality
  - Kokoro  — ultra-fast (<50ms), high quality preset voices
  - XTTS v2 — expressive, supports voice cloning, ~200ms first-audio

Engine priority is determined by ``tts.primary`` and ``tts.fallback`` in
config.  All engines yield **raw int16 PCM at 24 kHz** so downstream code
never needs to care about format differences.

Architecture:
    text → ProsodyController → per-sentence TTSEngine.stream() → PCM bytes → speaker
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np

from observability.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from config import TTSConfig
from observability.metrics import TTS_FIRST_AUDIO_LATENCY
from voice.breath_injector import BreathInjector
from voice.expressive_engine import AudioSegment, ExpressiveEngine, TextSegment
from voice.prosody import ProsodyController, ProsodyParams

log = get_logger(__name__)


def crossfade(
    prev: np.ndarray,
    curr: np.ndarray,
    overlap_samples: int = 480,
) -> np.ndarray:
    """
    Cross-fade between two audio segments to eliminate clicks/pops.

    Args:
        prev: Previous audio chunk (float32).
        curr: Current audio chunk (float32).
        overlap_samples: Number of samples in the fade region.

    Returns:
        Combined audio with smooth transition.
    """
    if len(prev) == 0:
        return curr
    if len(curr) == 0:
        return prev

    overlap = min(overlap_samples, len(prev), len(curr))
    if overlap < 2:
        return np.concatenate([prev, curr])

    fade_out = np.linspace(1.0, 0.0, overlap, dtype=np.float32)
    fade_in = np.linspace(0.0, 1.0, overlap, dtype=np.float32)

    result = np.empty(len(prev) + len(curr) - overlap, dtype=np.float32)
    result[: len(prev) - overlap] = prev[:-overlap]
    result[len(prev) - overlap : len(prev)] = prev[-overlap:] * fade_out + curr[:overlap] * fade_in
    result[len(prev) :] = curr[overlap:]
    return result


class TTSEngine(ABC):
    """Abstract base class for TTS engines."""

    @abstractmethod
    async def stream(
        self,
        text: str,
        prosody: ProsodyParams,
    ) -> AsyncIterator[bytes]:
        """
        Stream audio chunks for the given text.

        Args:
            text: Text to synthesize.
            prosody: Prosody parameters.

        Yields:
            Raw PCM or WAV bytes chunks as they're generated.
        """
        ...

    @abstractmethod
    async def load(self) -> None:
        """Load the TTS model into memory."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine name for logging and metrics."""
        ...


class XTTSv2Engine(TTSEngine):
    """
    XTTS v2 TTS engine with streaming support.

    Uses TTS library from Coqui. Model is loaded on demand and cached.
    Supports voice cloning via speaker_wav parameter.
    """

    def __init__(self, config: TTSConfig) -> None:
        self._config = config
        self._tts: object | None = None
        self._available = False

    @property
    def name(self) -> str:
        return "xtts_v2"

    async def load(self) -> None:
        """Load XTTS v2 model into GPU memory."""
        try:
            from TTS.api import TTS  # type: ignore[import-untyped]

            self._tts = await asyncio.to_thread(
                TTS,
                model_name=self._config.xtts.model_name,
                gpu=True,
            )
            self._available = True
            log.info("xtts_v2_loaded", model=self._config.xtts.model_name)
        except ImportError:
            log.warning("coqui_tts_not_installed")
        except Exception as exc:
            log.error("xtts_v2_load_failed", error=str(exc))

    async def stream(self, text: str, prosody: ProsodyParams) -> AsyncIterator[bytes]:
        """Stream XTTS v2 audio output."""
        if not self._available or self._tts is None:
            raise RuntimeError("XTTS v2 not available")

        t0 = time.monotonic()

        def _synthesize() -> bytes:
            buf = io.BytesIO()
            self._tts.tts_to_file(  # type: ignore[union-attr]
                text=text,
                speaker_wav=self._config.xtts.speaker_wav,
                language=self._config.xtts.language,
                file_path=buf,
                speed=prosody.speed,
            )
            buf.seek(0)
            return buf.read()

        audio_bytes = await asyncio.to_thread(_synthesize)

        latency_ms = (time.monotonic() - t0) * 1000.0
        TTS_FIRST_AUDIO_LATENCY.labels(engine="xtts_v2").observe(latency_ms / 1000.0)
        log.info("xtts_v2_synthesized", text_len=len(text), latency_ms=f"{latency_ms:.0f}")

        chunk_size = self._config.streaming_chunk_size * 1024
        for i in range(0, len(audio_bytes), chunk_size):
            yield audio_bytes[i : i + chunk_size]
            await asyncio.sleep(0)


class KokoroEngine(TTSEngine):
    """
    Kokoro TTS engine — ultra-fast, CPU/GPU, no voice cloning.

    Splits input into sentences and yields each sentence's audio
    independently for lower first-audio latency.
    """

    def __init__(self, config: TTSConfig) -> None:
        self._config = config
        self._pipeline: object | None = None
        self._available = False

    @property
    def name(self) -> str:
        return "kokoro"

    async def load(self) -> None:
        """Load the Kokoro TTS pipeline.

        Tries the default KPipeline (requires spacy for English G2P).
        If spacy is broken (e.g. Python 3.14 pydantic-v1 incompatibility)
        falls back to a minimal espeak-only pipeline that bypasses
        kokoro's __init__.py import chain entirely.
        """
        try:
            from kokoro import KPipeline  # type: ignore[import-untyped]

            self._pipeline = await asyncio.to_thread(KPipeline, lang_code="a")
            self._available = True
            log.info("kokoro_loaded", voice=self._config.kokoro.voice)
        except ImportError:
            log.warning("kokoro_not_installed")
        except Exception as exc:
            log.warning("kokoro_default_g2p_failed_trying_espeak", error=str(exc)[:120])
            await self._try_espeak_pipeline()

    async def _try_espeak_pipeline(self) -> None:
        """Build a minimal Kokoro pipeline using espeak-only G2P.

        Bypasses ``kokoro/__init__.py`` (which triggers a broken spacy
        import on Python 3.14) by loading ``kokoro.model`` via
        ``importlib`` and constructing a self-contained pipeline object.
        """
        try:
            import types

            import torch
            from huggingface_hub import hf_hub_download  # type: ignore[import-untyped]
            from misaki.espeak import EspeakG2P  # type: ignore[import-untyped]

            def _build() -> object:
                import importlib.util

                kokoro_pkg = (
                    "/".join(
                        __import__("kokoro.model", fromlist=[""]).__spec__.origin.split("/")[:-1]
                    )
                    if "kokoro" in sys.modules
                    else None
                )

                if kokoro_pkg is None:
                    import importlib.metadata

                    dist = importlib.metadata.distribution("kokoro")
                    kokoro_pkg = str(dist._path.parent / "kokoro")  # type: ignore[union-attr]

                fake_pkg = types.ModuleType("kokoro")
                fake_pkg.__path__ = [kokoro_pkg]  # type: ignore[attr-defined]
                fake_pkg.__package__ = "kokoro"
                sys.modules.setdefault("kokoro", fake_pkg)

                spec = importlib.util.spec_from_file_location(
                    "kokoro.model", f"{kokoro_pkg}/model.py"
                )
                assert spec and spec.loader
                mod = importlib.util.module_from_spec(spec)
                sys.modules["kokoro.model"] = mod
                spec.loader.exec_module(mod)

                kmodel_cls = mod.KModel
                device = "cuda" if torch.cuda.is_available() else "cpu"
                model = kmodel_cls().to(device).eval()
                g2p = EspeakG2P(language="en-us")
                repo_id = kmodel_cls.REPO_ID

                class _EspeakPipeline:
                    """Minimal Kokoro pipeline using espeak G2P only."""

                    def __init__(self) -> None:
                        self.model = model
                        self.g2p = g2p
                        self.voices: dict[str, torch.Tensor] = {}

                    def _load_voice(self, voice: str) -> torch.Tensor:
                        if voice not in self.voices:
                            path = hf_hub_download(
                                repo_id=repo_id,
                                filename=f"voices/{voice}.pt",
                            )
                            self.voices[voice] = torch.load(path, weights_only=True)
                        return self.voices[voice]

                    def __call__(
                        self,
                        text: str,
                        voice: str = "af_heart",
                        speed: float = 1.0,
                        split_pattern: str | None = r"\n+",
                    ):
                        """Yield (graphemes, phonemes, audio) tuples."""
                        import re

                        pack = self._load_voice(voice).to(self.model.device)
                        segments = (
                            re.split(split_pattern, text.strip()) if split_pattern else [text]
                        )
                        for segment in segments:
                            ps = self.g2p(segment)
                            if not ps:
                                continue
                            if len(ps) > 510:
                                ps = ps[:510]
                            out = self.model(ps, pack[len(ps) - 1], speed, return_output=True)
                            yield segment, ps, out.audio

                return _EspeakPipeline()

            self._pipeline = await asyncio.to_thread(_build)
            self._available = True
            log.info("kokoro_loaded_espeak_g2p", voice=self._config.kokoro.voice)
        except Exception as exc:
            log.warning(
                "kokoro_espeak_fallback_failed",
                error=str(exc)[:120],
                hint="Install espeak-ng: sudo pacman -S espeak-ng",
            )

    def set_voice(self, voice: str) -> None:
        """Switch the active Kokoro voice at runtime."""
        self._config.kokoro.voice = voice
        log.info("kokoro_voice_changed", voice=voice)

    async def stream(self, text: str, prosody: ProsodyParams) -> AsyncIterator[bytes]:
        """
        Stream Kokoro audio, yielding per-sentence chunks for low latency.

        Instead of synthesizing the whole text at once and returning all
        audio, we yield each sentence segment as it completes.
        """
        if not self._available or self._pipeline is None:
            raise RuntimeError("Kokoro not available")

        t0 = time.monotonic()

        def _synthesize_one(segment: str, spd: float) -> np.ndarray | None:
            """Synthesize a single segment and return the audio array."""
            for _graphemes, _phonemes, audio in self._pipeline(  # type: ignore[union-attr]
                segment,
                voice=self._config.kokoro.voice,
                speed=spd,
                split_pattern=r"\n+",
            ):
                return audio
            return None

        sentences = ProsodyController.split_into_sentences(text)
        if not sentences:
            sentences = [text]

        first = True
        for sentence in sentences:
            audio = await asyncio.to_thread(_synthesize_one, sentence, prosody.speed)
            if audio is None or len(audio) == 0:
                continue

            if first:
                latency_ms = (time.monotonic() - t0) * 1000.0
                TTS_FIRST_AUDIO_LATENCY.labels(engine="kokoro").observe(latency_ms / 1000.0)
                log.info("kokoro_first_chunk", latency_ms=f"{latency_ms:.0f}")
                first = False

            audio_np = np.asarray(audio, dtype=np.float32)
            audio_int16 = (np.clip(audio_np, -1.0, 1.0) * 32767).astype(np.int16)
            yield audio_int16.tobytes()
            await asyncio.sleep(0)


class CSMEngine(TTSEngine):
    """Sesame CSM (Conversational Speech Model) TTS engine.

    Uses HuggingFace ``transformers`` with ``CsmForConditionalGeneration``.
    Produces highly natural conversational speech at 24 kHz.  Requires
    a CUDA GPU with sufficient VRAM (~4-6 GB for the 1B model in fp16).
    """

    def __init__(self, config: TTSConfig) -> None:
        self._config = config
        self._model: object | None = None
        self._processor: object | None = None
        self._available = False

    @property
    def name(self) -> str:
        return "csm"

    async def load(self) -> None:
        """Load the CSM model and processor from HuggingFace."""
        try:
            import torch
            from transformers import (  # type: ignore[import-untyped]
                AutoProcessor,
                CsmForConditionalGeneration,
            )

            csm_cfg = self._config.csm
            dtype_map = {"float16": torch.float16, "bfloat16": torch.bfloat16}
            dtype = dtype_map.get(csm_cfg.dtype, torch.float16)

            def _load() -> tuple[object, object]:
                processor = AutoProcessor.from_pretrained(csm_cfg.model_id)
                model = CsmForConditionalGeneration.from_pretrained(
                    csm_cfg.model_id,
                    torch_dtype=dtype,
                    device_map="cuda",
                    low_cpu_mem_usage=True,
                )
                # Compile for faster inference on CUDA (first call is slow, rest are fast)
                if hasattr(torch, "compile"):
                    try:
                        model = torch.compile(model, mode="reduce-overhead")
                        log.info("csm_torch_compiled")
                    except Exception:
                        pass  # torch.compile not supported on all setups
                return model, processor

            self._model, self._processor = await asyncio.to_thread(_load)
            self._available = True
            log.info(
                "csm_loaded",
                model_id=csm_cfg.model_id,
                dtype=csm_cfg.dtype,
            )
        except ImportError:
            log.warning("csm_transformers_not_available")
        except Exception as exc:
            log.error("csm_load_failed", error=str(exc)[:200])

    async def stream(self, text: str, prosody: ProsodyParams) -> AsyncIterator[bytes]:
        """Synthesize speech with CSM, yielding per-sentence PCM chunks.

        Splits text into sentences and generates audio for each one
        independently to keep first-audio latency low.
        """
        if not self._available or self._model is None or self._processor is None:
            raise RuntimeError("CSM not available")

        import torch

        t0 = time.monotonic()
        speaker_id = self._config.csm.speaker_id
        max_len = self._config.csm.max_audio_length

        def _synthesize_one(sentence: str) -> np.ndarray | None:
            prompt = f"[{speaker_id}]{sentence}"
            inputs = self._processor(  # type: ignore[misc]
                prompt, add_special_tokens=True
            ).to(self._model.device)  # type: ignore[union-attr]

            with torch.inference_mode():
                audio_tensor = self._model.generate(  # type: ignore[union-attr]
                    **inputs,
                    output_audio=True,
                    max_length=max_len,
                )
            if audio_tensor is None:
                return None

            audio_np = audio_tensor.squeeze().cpu().float().numpy()
            if audio_np.size == 0:
                return None
            return audio_np

        sentences = ProsodyController.split_into_sentences(text)
        if not sentences:
            sentences = [text]

        first = True
        for sentence in sentences:
            audio = await asyncio.to_thread(_synthesize_one, sentence)
            if audio is None or len(audio) == 0:
                continue

            if first:
                latency_ms = (time.monotonic() - t0) * 1000.0
                TTS_FIRST_AUDIO_LATENCY.labels(engine="csm").observe(latency_ms / 1000.0)
                log.info("csm_first_chunk", latency_ms=f"{latency_ms:.0f}")
                first = False

            audio_np = np.asarray(audio, dtype=np.float32)
            audio_int16 = (np.clip(audio_np, -1.0, 1.0) * 32767).astype(np.int16)
            yield audio_int16.tobytes()
            await asyncio.sleep(0)


_ENGINE_CLASSES: dict[str, type[TTSEngine]] = {
    "csm": CSMEngine,
    "xtts_v2": XTTSv2Engine,
    "kokoro": KokoroEngine,
}


class TTSManager:
    """TTS manager with config-driven engine priority and per-sentence prosody.

    Engine order is built from ``tts.primary`` and ``tts.fallback`` in
    config, plus any remaining registered engines as extra fallbacks.
    All engines yield raw int16 PCM at 24 kHz.

    Integrates breath injection between sentences for natural speech rhythm.
    """

    def __init__(self, config: TTSConfig) -> None:
        """
        Args:
            config: TTS configuration.
        """
        self._config = config
        self._prosody = ProsodyController()
        self._breather: BreathInjector | None = None
        self._expressive = ExpressiveEngine(voice_pitch_hz=210.0)

        seen: set[str] = set()
        self._engine_list: list[TTSEngine] = []
        for name in (config.primary, config.fallback):
            if name in seen:
                continue
            seen.add(name)
            cls = _ENGINE_CLASSES.get(name)
            if cls is None:
                log.warning("unknown_tts_engine", name=name)
                continue
            self._engine_list.append(cls(config))

        # Only load configured primary + fallback — skip unused engines
        # (avoids loading CSM which requires gated HF access)

    async def load(self) -> None:
        """Load all TTS engines and the breath injector concurrently."""
        self._breather = BreathInjector()
        await asyncio.gather(
            *(eng.load() for eng in self._engine_list),
            self._breather.load(),
            return_exceptions=True,
        )
        log.info(
            "tts_manager_ready",
            primary_available=self._engine_list[0]._available if self._engine_list else False,
            fallback_available=(
                self._engine_list[1]._available if len(self._engine_list) > 1 else False
            ),
            breath_injector="loaded",
        )

    @property
    def _engines(self) -> list[TTSEngine]:
        """All engines in config-driven priority order."""
        return self._engine_list

    async def speak(
        self,
        text: str,
        emotional_state: dict[str, float] | None = None,
        whisper_mode: bool = False,
        force_engine: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Synthesize speech with per-sentence prosody.

        All engines now yield **raw int16 PCM at 24 kHz**, so callers can
        always treat the output uniformly.

        Args:
            text: Text to speak.
            emotional_state: Emily's emotional state for prosody computation.
            whisper_mode: If True, reduces volume for quiet environments.
            force_engine: Engine name to force, or None for auto.

        Returns:
            Async iterator of raw PCM int16 bytes chunks.
        """
        if not text.strip():
            return

        self._prosody.reset_position()

        engine = self._select_engine(force_engine)

        sentences = ProsodyController.split_into_sentences(text)
        if not sentences:
            sentences = [text]

        _EMOTIONAL_WORDS = {
            "love",
            "hate",
            "miss",
            "sorry",
            "afraid",
            "worried",
            "excited",
            "amazing",
            "terrible",
            "beautiful",
            "hurt",
        }

        for idx, sentence in enumerate(sentences):
            prosody = self._prosody.compute(sentence, emotional_state, whisper_mode)
            log.info(
                "tts_speaking",
                engine=engine.name,
                text_len=len(sentence),
                speed=prosody.speed,
                pitch=prosody.pitch,
                energy=prosody.energy,
            )

            # --- Breath injection before sentence ---
            is_emotional = bool(set(sentence.lower().split()) & _EMOTIONAL_WORDS)
            if self._breather:
                breath_evt = self._breather.should_breathe(
                    sentence,
                    position="before",
                    is_emotional=is_emotional,
                    sentence_index=idx,
                )
                if breath_evt:
                    breath_pcm = self._breather.inject(
                        breath_evt,
                        np.array([], dtype=np.float32),
                    )
                    breath_int16 = (np.clip(breath_pcm, -1.0, 1.0) * 32767).astype(np.int16)
                    yield breath_int16.tobytes()

            if prosody.pause_before_ms > 0:
                silence_samples = int(24000 * prosody.pause_before_ms / 1000)
                yield np.zeros(silence_samples, dtype=np.int16).tobytes()

            # --- Expressive processing: split sentence into text + audio segments ---
            segments = self._expressive.process(sentence)
            has_expressives = any(isinstance(s, AudioSegment) for s in segments)

            if has_expressives:
                for seg in segments:
                    if isinstance(seg, AudioSegment) and len(seg.audio) > 0:
                        # Yield pre-rendered expressive audio directly (float32 → int16)
                        expr_int16 = (np.clip(seg.audio, -1.0, 1.0) * 32767).astype(np.int16)
                        yield expr_int16.tobytes()
                        log.info("expressive_played", label=seg.label, samples=len(seg.audio))
                    elif isinstance(seg, TextSegment) and seg.text.strip():
                        # Synthesize remaining text through the TTS engine
                        async for chunk in self._synth_with_fallback(engine, seg.text, prosody):
                            yield chunk
            else:
                # No expressives — pass entire sentence to TTS as before
                async for chunk in self._synth_with_fallback(engine, sentence, prosody):
                    yield chunk

            # --- Breath injection after sentence ---
            if self._breather:
                breath_evt = self._breather.should_breathe(
                    sentence,
                    position="after",
                    is_emotional=is_emotional,
                    sentence_index=idx,
                )
                if breath_evt:
                    breath_pcm = self._breather.inject(
                        breath_evt,
                        np.array([], dtype=np.float32),
                    )
                    breath_int16 = (np.clip(breath_pcm, -1.0, 1.0) * 32767).astype(np.int16)
                    yield breath_int16.tobytes()

    def set_voice(self, voice: str) -> None:
        """Switch the active voice on all engines that support it."""
        for eng in self._engine_list:
            if hasattr(eng, "set_voice"):
                eng.set_voice(voice)
        log.info("tts_manager_voice_changed", voice=voice)

    async def _synth_with_fallback(
        self, engine: TTSEngine, text: str, prosody: ProsodyParams
    ) -> AsyncIterator[bytes]:
        """Synthesize text with the given engine, falling back on error."""
        try:
            async for chunk in engine.stream(text, prosody):
                yield chunk
        except Exception as exc:
            log.error("tts_engine_failed", engine=engine.name, error=str(exc)[:200])
            for fallback in self._engines:
                if fallback is engine or not fallback._available:
                    continue
                log.info("tts_falling_back", to=fallback.name)
                try:
                    async for chunk in fallback.stream(text, prosody):
                        yield chunk
                    break
                except Exception:
                    continue

    def _select_engine(self, force: str | None) -> TTSEngine:
        """Select the appropriate TTS engine."""
        if force:
            for eng in self._engines:
                if eng.name == force:
                    return eng
        for eng in self._engines:
            if eng._available:
                return eng
        raise RuntimeError(
            "No TTS engine available. Install one of: transformers (csm), TTS (coqui), or kokoro."
        )
