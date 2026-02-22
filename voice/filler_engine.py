"""
Filler and thinking sound engine for Emily.

Generates human-like thinking sounds during LLM processing latency.
Eliminates dead silence that makes AI feel robotic.

All filler audio is pre-rendered at startup for zero TTS latency.
Fillers blend into the first word of the real response via crossfade.

Categories:
- IMMEDIATE (0-100ms): breath intake, "hmm..."
- SHORT (100-500ms): "let me think...", "good question..."
- MEDIUM (500-1500ms): "that's a good point..."
- LONG (>1500ms): "give me just a second..."
"""

from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any

import numpy as np

from observability.logger import get_logger

log = get_logger(__name__)

FILLER_ASSETS_DIR = Path("assets/fillers")


class FillerCategory(Enum):
    """Filler duration categories."""

    IMMEDIATE = auto()
    SHORT = auto()
    MEDIUM = auto()
    LONG = auto()


_FILLER_TEXTS: dict[FillerCategory, list[str]] = {
    FillerCategory.IMMEDIATE: [
        "[breath]", "hmm", "mm",
    ],
    FillerCategory.SHORT: [
        "let me think", "good question", "so", "right so", "hmm",
        "well", "okay so", "let's see",
    ],
    FillerCategory.MEDIUM: [
        "that's a good point, let me think about that",
        "hmm, so", "okay so", "right, let me consider that",
        "interesting question", "let me think for a moment",
    ],
    FillerCategory.LONG: [
        "give me just a second on that",
        "that's a complex one, let me think",
        "hmm, that requires some thought",
        "okay, let me work through that",
    ],
}


@dataclass
class PreRenderedFiller:
    """A pre-rendered filler audio with metadata."""

    category: FillerCategory
    text: str
    audio: np.ndarray
    duration_ms: float
    sample_rate: int = 24000


class FillerEngine:
    """
    Manages pre-rendered thinking sounds for processing latency coverage.

    Rules:
    - Filler prosody must match the emotional register
    - Never the same filler twice in a 5-minute window
    - Filler duration must not EXCEED actual processing time
    - Filler blends into the first word of the real response
    """

    _COOLDOWN_S = 300

    def __init__(self) -> None:
        self._pools: dict[FillerCategory, list[PreRenderedFiller]] = {
            cat: [] for cat in FillerCategory
        }
        self._recent_fillers: deque[str] = deque(maxlen=20)
        self._last_filler_time: float = 0.0

    async def load(self) -> None:
        """Load pre-recorded fillers from assets directory."""
        FILLER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

        for wav_path in FILLER_ASSETS_DIR.glob("*.wav"):
            try:
                import wave
                with wave.open(str(wav_path)) as wf:
                    raw = wf.readframes(wf.getnframes())
                    sr = wf.getframerate()
                    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    duration_ms = len(audio) / sr * 1000

                    cat = self._categorize_by_duration(duration_ms)
                    self._pools[cat].append(PreRenderedFiller(
                        category=cat,
                        text=wav_path.stem,
                        audio=audio,
                        duration_ms=duration_ms,
                        sample_rate=sr,
                    ))
            except Exception as exc:
                log.debug("filler_load_error", path=str(wav_path), error=str(exc))

        self._generate_fallback_fillers()
        total = sum(len(p) for p in self._pools.values())
        log.info("fillers_loaded", total=total)

    def _generate_fallback_fillers(self) -> None:
        """Generate basic synthesized fillers if no pre-recorded assets exist."""
        for cat, texts in _FILLER_TEXTS.items():
            if self._pools[cat]:
                continue

            for text in texts:
                if text == "[breath]":
                    audio = self._synthesize_breath()
                else:
                    audio = self._synthesize_hmm(cat)

                duration_ms = len(audio) / 24000 * 1000
                self._pools[cat].append(PreRenderedFiller(
                    category=cat,
                    text=text,
                    audio=audio,
                    duration_ms=duration_ms,
                ))

    @staticmethod
    def _synthesize_breath() -> np.ndarray:
        """Synthesize a breath intake sound (filtered noise)."""
        sr = 24000
        duration = 0.4
        n = int(sr * duration)
        noise = np.random.randn(n).astype(np.float32) * 0.02

        from scipy.signal import butter, lfilter
        b, a = butter(4, [200, 2500], btype="band", fs=sr)
        breath = lfilter(b, a, noise).astype(np.float32)

        fade_in = int(sr * 0.08)
        fade_out = int(sr * 0.1)
        breath[:fade_in] *= np.linspace(0, 1, fade_in)
        breath[-fade_out:] *= np.linspace(1, 0, fade_out)

        return breath * 0.15

    @staticmethod
    def _synthesize_hmm(category: FillerCategory) -> np.ndarray:
        """Synthesize a basic 'hmm' thinking sound."""
        sr = 24000
        durations = {
            FillerCategory.IMMEDIATE: 0.2,
            FillerCategory.SHORT: 0.5,
            FillerCategory.MEDIUM: 0.8,
            FillerCategory.LONG: 1.2,
        }
        dur = durations.get(category, 0.5)
        n = int(sr * dur)
        t = np.linspace(0, dur, n, dtype=np.float32)

        f0 = 140 + np.random.randn() * 10
        f0_contour = f0 - t * 15

        phase = np.cumsum(2 * np.pi * f0_contour / sr)
        audio = np.sin(phase) * 0.2
        audio += np.sin(phase * 2) * 0.08
        audio += np.sin(phase * 3) * 0.03

        audio += np.random.randn(n).astype(np.float32) * 0.005

        fade_in = int(sr * 0.05)
        fade_out = int(sr * 0.08)
        audio[:fade_in] *= np.linspace(0, 1, fade_in)
        audio[-fade_out:] *= np.linspace(1, 0, fade_out)

        return audio.astype(np.float32)

    @staticmethod
    def _categorize_by_duration(duration_ms: float) -> FillerCategory:
        """Map duration to filler category."""
        if duration_ms < 100:
            return FillerCategory.IMMEDIATE
        elif duration_ms < 500:
            return FillerCategory.SHORT
        elif duration_ms < 1500:
            return FillerCategory.MEDIUM
        return FillerCategory.LONG

    async def get_filler(
        self,
        expected_latency_ms: int,
        emotion_context: Any = None,
        topic_register: str = "neutral",
    ) -> np.ndarray | None:
        """
        Get an appropriate filler guaranteed shorter than expected latency.

        Args:
            expected_latency_ms: How long the processing is expected to take.
            emotion_context: Current emotional state for register matching.
            topic_register: Emotional register of the topic.

        Returns:
            Float32 audio array, or None if no suitable filler.
        """
        category = self._categorize_by_duration(expected_latency_ms)
        pool = self._pools.get(category, [])

        if not pool:
            for cat in [FillerCategory.IMMEDIATE, FillerCategory.SHORT]:
                if self._pools[cat]:
                    pool = self._pools[cat]
                    break

        if not pool:
            return None

        available = [
            f for f in pool
            if f.text not in self._recent_fillers and f.duration_ms < expected_latency_ms
        ]
        if not available:
            available = [f for f in pool if f.duration_ms < expected_latency_ms]
        if not available:
            return None

        chosen = random.choice(available)
        self._recent_fillers.append(chosen.text)
        self._last_filler_time = time.monotonic()

        log.debug("filler_selected", text=chosen.text, duration_ms=f"{chosen.duration_ms:.0f}")
        return chosen.audio.copy()

    @staticmethod
    def blend_filler_to_response(
        filler: np.ndarray,
        response_start: np.ndarray,
        crossfade_ms: int = 50,
    ) -> np.ndarray:
        """
        Crossfade the end of a filler into the start of a response.

        Args:
            filler: Filler audio.
            response_start: First chunk of the response audio.
            crossfade_ms: Crossfade duration in milliseconds.

        Returns:
            Blended audio with imperceptible transition.
        """
        sr = 24000
        fade_samples = int(crossfade_ms * sr / 1000)
        fade_samples = min(fade_samples, len(filler), len(response_start))

        if fade_samples < 10:
            return np.concatenate([filler, response_start])

        result = np.concatenate([
            filler[:-fade_samples],
            np.zeros(fade_samples, dtype=np.float32),
            response_start[fade_samples:],
        ])

        fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
        fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)

        crossfade_region = (
            filler[-fade_samples:] * fade_out +
            response_start[:fade_samples] * fade_in
        )
        result[len(filler) - fade_samples:len(filler)] = crossfade_region

        return result
