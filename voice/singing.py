"""
Singing and music generation engine for Emily.

Multi-engine system mirroring the TTS pipeline (``voice/tts.py``):
  - MusicGen  — local text-to-music via Meta AudioCraft
  - RVC       — local singing voice conversion (Retrieval-based Voice Conversion)
  - Suno API  — cloud-based full song generation (fallback)

Engine priority is driven by ``singing.primary`` and ``singing.fallback``
in config.  All engines produce **raw int16 PCM at 24 kHz** so
downstream code can treat the output uniformly.

Architecture:
    prompt / audio → SingingManager.sing() → engine.generate() → PCM bytes
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, AsyncIterator

import numpy as np

from config import SingingConfig
from observability.logger import get_logger

log = get_logger(__name__)

TARGET_SR = 24_000


def _resample_to_target(audio: np.ndarray, source_sr: int) -> np.ndarray:
    """Resample float32 audio to TARGET_SR using linear interpolation.

    Args:
        audio: Source audio array (float32, mono).
        source_sr: Source sample rate in Hz.

    Returns:
        Resampled float32 audio at TARGET_SR.
    """
    if source_sr == TARGET_SR:
        return audio
    ratio = TARGET_SR / source_sr
    n_out = int(len(audio) * ratio)
    indices = np.linspace(0, len(audio) - 1, n_out)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


def _decode_audio_to_pcm(data: bytes) -> bytes:
    """Decode arbitrary audio bytes to raw int16 PCM at 24 kHz mono via ffmpeg.

    Returns:
        Raw int16 PCM bytes.
    """
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0",
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ac", "1", "-ar", str(TARGET_SR),
            "pipe:1",
        ],
        input=data,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {proc.stderr.decode()[:200]}")
    return proc.stdout


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class SingingEngineBase(ABC):
    """Abstract base for all singing/music engines."""

    @abstractmethod
    async def generate(
        self,
        *,
        prompt: str,
        style: str | None = None,
        duration_seconds: int = 30,
        input_audio_path: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Generate audio and yield raw int16 PCM chunks at 24 kHz.

        Args:
            prompt: Text description or lyrics.
            style: Optional music style hint.
            duration_seconds: Target duration.
            input_audio_path: Path to reference audio (used by RVC).

        Yields:
            Raw int16 PCM bytes chunks.
        """
        ...

    @abstractmethod
    async def load(self) -> None:
        """Load the underlying model into memory."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine identifier for logging and config lookup."""
        ...

    @property
    def available(self) -> bool:
        """Whether the engine is loaded and ready."""
        return self._available

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

    _available: bool = False


# ---------------------------------------------------------------------------
# MusicGen (AudioCraft)
# ---------------------------------------------------------------------------


class MusicGenEngine(SingingEngineBase):
    """Text-to-music generation via Meta AudioCraft MusicGen.

    Generates instrumental music (or simple vocal tracks) from a text prompt.
    Requires the ``audiocraft`` package and a GPU with sufficient VRAM.
    """

    def __init__(self, config: SingingConfig) -> None:
        self._config = config
        self._model: object | None = None
        self._available = False

    @property
    def name(self) -> str:
        return "musicgen"

    async def load(self) -> None:
        """Load the MusicGen model."""
        if not self._config.musicgen.enabled:
            log.info("musicgen_disabled")
            return
        try:
            from audiocraft.models import MusicGen as _MusicGen  # type: ignore[import-untyped]

            def _load() -> object:
                return _MusicGen.get_pretrained(
                    f"facebook/musicgen-{self._config.musicgen.model_size}",
                    device=self._config.musicgen.device,
                )

            self._model = await asyncio.to_thread(_load)
            self._available = True
            log.info(
                "musicgen_loaded",
                model_size=self._config.musicgen.model_size,
                device=self._config.musicgen.device,
            )
        except ImportError:
            log.warning("audiocraft_not_installed", hint="pip install audiocraft")
        except Exception as exc:
            log.error("musicgen_load_failed", error=str(exc)[:200])

    async def generate(
        self,
        *,
        prompt: str,
        style: str | None = None,
        duration_seconds: int = 30,
        input_audio_path: str | None = None,
    ) -> AsyncIterator[bytes]:
        if not self._available or self._model is None:
            raise RuntimeError("MusicGen not available")

        t0 = time.monotonic()
        full_prompt = f"{style} {prompt}" if style else prompt

        def _synthesize() -> np.ndarray:
            self._model.set_generation_params(duration=duration_seconds)  # type: ignore[union-attr]
            wav = self._model.generate([full_prompt])  # type: ignore[union-attr]
            return wav[0, 0].cpu().numpy()  # (samples,)

        audio_f32 = await asyncio.to_thread(_synthesize)
        model_sr = self._model.sample_rate  # type: ignore[union-attr]
        audio_f32 = _resample_to_target(audio_f32, model_sr)
        audio_int16 = (np.clip(audio_f32, -1.0, 1.0) * 32767).astype(np.int16)

        latency_ms = (time.monotonic() - t0) * 1000.0
        log.info(
            "musicgen_generated",
            prompt_len=len(full_prompt),
            duration_s=duration_seconds,
            latency_ms=f"{latency_ms:.0f}",
        )

        chunk_bytes = 24_000 * 2  # 1 second of int16 PCM at 24 kHz
        raw = audio_int16.tobytes()
        for i in range(0, len(raw), chunk_bytes):
            yield raw[i : i + chunk_bytes]
            await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# RVC (Retrieval-based Voice Conversion)
# ---------------------------------------------------------------------------


class RVCEngine(SingingEngineBase):
    """Singing voice conversion via RVC.

    Converts an input audio file (singing) into Emily's voice using a
    pre-trained RVC model.  Requires the ``rvc-python`` package.
    """

    def __init__(self, config: SingingConfig) -> None:
        self._config = config
        self._rvc: object | None = None
        self._available = False

    @property
    def name(self) -> str:
        return "rvc"

    async def load(self) -> None:
        """Load the RVC inference engine and model."""
        if not self._config.rvc.enabled:
            log.info("rvc_disabled")
            return
        if not self._config.rvc.model_path:
            log.warning("rvc_no_model_path", hint="Set singing.rvc.model_path in config.yaml")
            return
        try:
            from rvc_python.infer import RVCInference  # type: ignore[import-untyped]

            def _load() -> object:
                rvc = RVCInference(device=self._config.rvc.device)
                rvc.load_model(self._config.rvc.model_path)
                if self._config.rvc.index_path:
                    rvc.set_params(index_path=self._config.rvc.index_path)
                return rvc

            self._rvc = await asyncio.to_thread(_load)
            self._available = True
            log.info("rvc_loaded", model=self._config.rvc.model_path)
        except ImportError:
            log.warning("rvc_python_not_installed", hint="pip install rvc-python")
        except Exception as exc:
            log.error("rvc_load_failed", error=str(exc)[:200])

    async def generate(
        self,
        *,
        prompt: str,
        style: str | None = None,
        duration_seconds: int = 30,
        input_audio_path: str | None = None,
    ) -> AsyncIterator[bytes]:
        if not self._available or self._rvc is None:
            raise RuntimeError("RVC not available")
        if not input_audio_path or not Path(input_audio_path).exists():
            raise ValueError("RVC requires a valid input_audio_path to convert")

        t0 = time.monotonic()
        output_dir = Path(self._config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"rvc_{int(time.time())}.wav"

        def _convert() -> None:
            self._rvc.infer_file(  # type: ignore[union-attr]
                str(input_audio_path),
                str(output_path),
            )

        await asyncio.to_thread(_convert)

        latency_ms = (time.monotonic() - t0) * 1000.0
        log.info(
            "rvc_converted",
            input=input_audio_path,
            output=str(output_path),
            latency_ms=f"{latency_ms:.0f}",
        )

        raw_audio = output_path.read_bytes()
        pcm = await asyncio.to_thread(_decode_audio_to_pcm, raw_audio)

        chunk_bytes = TARGET_SR * 2
        for i in range(0, len(pcm), chunk_bytes):
            yield pcm[i : i + chunk_bytes]
            await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Suno API (cloud)
# ---------------------------------------------------------------------------


class SunoEngine(SingingEngineBase):
    """Cloud-based full song generation via the Suno REST API.

    Generates complete songs with vocals, lyrics, and instrumentation.
    Requires an API key (set ``singing.suno.api_key`` or ``SUNO_API_KEY`` env).
    """

    def __init__(self, config: SingingConfig) -> None:
        self._config = config
        self._api_key: str | None = None
        self._available = False

    @property
    def name(self) -> str:
        return "suno"

    async def load(self) -> None:
        """Validate that the Suno API key is available."""
        if not self._config.suno.enabled:
            log.info("suno_disabled")
            return

        self._api_key = (
            self._config.suno.api_key or os.environ.get("SUNO_API_KEY")
        )
        if not self._api_key:
            log.warning("suno_no_api_key", hint="Set SUNO_API_KEY or singing.suno.api_key")
            return

        self._available = True
        log.info("suno_ready", api_url=self._config.suno.api_url)

    async def generate(
        self,
        *,
        prompt: str,
        style: str | None = None,
        duration_seconds: int = 30,
        input_audio_path: str | None = None,
    ) -> AsyncIterator[bytes]:
        if not self._available or not self._api_key:
            raise RuntimeError("Suno API not available (missing API key)")

        import httpx

        t0 = time.monotonic()
        base = self._config.suno.api_url.rstrip("/")
        timeout = self._config.suno.timeout_seconds

        payload: dict[str, Any] = {
            "prompt": prompt,
            "model": self._config.suno.model_version,
            "custom": bool(style),
        }
        if style:
            payload["style"] = style
            payload["title"] = prompt[:80]

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base}/suno-api/generate-music",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            resp.raise_for_status()
            result = resp.json()

            audio_url: str | None = None
            if isinstance(result, dict):
                audio_url = result.get("audio_url") or result.get("url")
            elif isinstance(result, list) and result:
                audio_url = result[0].get("audio_url") or result[0].get("url")

            if not audio_url:
                raise RuntimeError("Suno API did not return an audio URL")

            audio_resp = await client.get(audio_url)
            audio_resp.raise_for_status()

        pcm = await asyncio.to_thread(_decode_audio_to_pcm, audio_resp.content)

        latency_ms = (time.monotonic() - t0) * 1000.0
        log.info(
            "suno_generated",
            prompt_len=len(prompt),
            latency_ms=f"{latency_ms:.0f}",
        )

        output_dir = Path(self._config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"suno_{int(time.time())}.wav"
        await asyncio.to_thread(out_path.write_bytes, audio_resp.content)

        chunk_bytes = TARGET_SR * 2
        for i in range(0, len(pcm), chunk_bytes):
            yield pcm[i : i + chunk_bytes]
            await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


_ENGINE_CLASSES: dict[str, type[SingingEngineBase]] = {
    "musicgen": MusicGenEngine,
    "rvc": RVCEngine,
    "suno": SunoEngine,
}


class SingingManager:
    """Orchestrates singing engines with config-driven priority and fallback.

    Mirrors :class:`voice.tts.TTSManager`.  The engine order is built from
    ``singing.primary`` and ``singing.fallback`` in config, with all
    remaining engines appended as last-resort fallbacks.
    """

    def __init__(self, config: SingingConfig) -> None:
        self._config = config
        seen: set[str] = set()
        self._engine_list: list[SingingEngineBase] = []
        for name in (config.primary, config.fallback):
            if name in seen:
                continue
            seen.add(name)
            cls = _ENGINE_CLASSES.get(name)
            if cls is None:
                log.warning("unknown_singing_engine", name=name)
                continue
            self._engine_list.append(cls(config))

        for name, cls in _ENGINE_CLASSES.items():
            if name not in seen:
                self._engine_list.append(cls(config))

    async def load(self) -> None:
        """Load all singing engines concurrently."""
        await asyncio.gather(
            *(eng.load() for eng in self._engine_list),
            return_exceptions=True,
        )
        available = [e.name for e in self._engine_list if e.available]
        log.info("singing_manager_ready", available_engines=available)

    def _select_engine(
        self, mode: str | None = None
    ) -> SingingEngineBase:
        """Select the best available engine, optionally forced by mode.

        Args:
            mode: ``"generate"`` → MusicGen, ``"voice_convert"`` → RVC,
                  ``"full_song"`` → Suno, ``None`` → first available.

        Returns:
            A ready :class:`SingingEngineBase`.
        """
        mode_map: dict[str, str] = {
            "generate": "musicgen",
            "voice_convert": "rvc",
            "full_song": "suno",
        }
        preferred = mode_map.get(mode or "")
        if preferred:
            for eng in self._engine_list:
                if eng.name == preferred and eng.available:
                    return eng

        for eng in self._engine_list:
            if eng.available:
                return eng

        raise RuntimeError(
            "No singing engine available. "
            "Install audiocraft or rvc-python, or set a Suno API key."
        )

    async def sing(
        self,
        prompt: str,
        *,
        style: str | None = None,
        duration_seconds: int = 30,
        mode: str | None = None,
        input_audio_path: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Generate music / singing and yield raw int16 PCM at 24 kHz.

        Args:
            prompt: Text description, lyrics, or generation prompt.
            style: Music style hint (pop, jazz, lo-fi, etc.).
            duration_seconds: Target duration in seconds.
            mode: ``"generate"`` | ``"voice_convert"`` | ``"full_song"`` | None.
            input_audio_path: Reference audio file for RVC voice conversion.

        Yields:
            Raw int16 PCM bytes chunks at 24 kHz.
        """
        engine = self._select_engine(mode)
        log.info("singing_start", engine=engine.name, mode=mode, prompt_len=len(prompt))

        try:
            async for chunk in engine.generate(
                prompt=prompt,
                style=style,
                duration_seconds=duration_seconds,
                input_audio_path=input_audio_path,
            ):
                yield chunk
        except Exception as exc:
            log.error(
                "singing_engine_failed",
                engine=engine.name,
                error=str(exc)[:200],
            )
            for fallback in self._engine_list:
                if fallback is engine or not fallback.available:
                    continue
                log.info("singing_falling_back", to=fallback.name)
                try:
                    async for chunk in fallback.generate(
                        prompt=prompt,
                        style=style,
                        duration_seconds=duration_seconds,
                        input_audio_path=input_audio_path,
                    ):
                        yield chunk
                    return
                except Exception:
                    continue
            raise
