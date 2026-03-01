"""
Breath sound injection for Emily's TTS output.

Inserts realistic breath sounds at natural locations in Emily's speech:
- Before sentences with > 8 words: natural inhale
- After emotionally significant sentences: audible exhale
- Before long lists: preparation breath
- Random micro-breaths every 15-25 seconds

Breath sound library: 20+ recorded samples, varied depth/speed,
matched to speaking energy level.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import numpy as np

from observability.logger import get_logger

log = get_logger(__name__)

BREATH_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "breaths"


class BreathType(Enum):
    """Types of breath sounds."""

    INHALE_DEEP = auto()
    INHALE_SHALLOW = auto()
    INHALE_QUICK = auto()
    EXHALE_SETTLING = auto()
    EXHALE_RELIEF = auto()
    MICRO_BREATH = auto()


@dataclass
class BreathEvent:
    """A breath to be injected at a specific point."""

    breath_type: BreathType
    position: str  # "before" or "after" the sentence
    volume_scale: float = 0.2
    duration_ms: float = 300


class BreathInjector:
    """
    Injects realistic breath sounds at natural locations.

    Volume: 15-25% of speech level.
    Applied with 10ms fade in/out to be imperceptible.
    """

    _DEFAULT_MIN_BREATH_INTERVAL_S = 10.0
    _DEFAULT_MAX_BREATH_INTERVAL_S = 20.0
    _JITTER_S = 4.0
    _SENTENCE_WORD_THRESHOLD = 6

    def __init__(self) -> None:
        self._library: dict[BreathType, list[np.ndarray]] = {bt: [] for bt in BreathType}
        self._last_breath_time: float = 0.0
        self._breath_interval_s: float = (
            self._DEFAULT_MIN_BREATH_INTERVAL_S + self._DEFAULT_MAX_BREATH_INTERVAL_S
        ) / 2.0
        self._next_micro_breath_s: float = self._jittered_interval()
        self._sentence_count = 0

    def _jittered_interval(self) -> float:
        """Return the configured breath interval with +/- jitter."""
        return self._breath_interval_s + random.uniform(
            -self._JITTER_S,
            self._JITTER_S,
        )

    def set_breath_interval(self, interval_s: float) -> None:
        """
        Update the micro-breath interval from rhythm entrainment targets.

        Args:
            interval_s: Target breath interval in seconds (typically 10-30).
        """
        self._breath_interval_s = max(10.0, min(30.0, interval_s))

    async def load(self) -> None:
        """Load pre-recorded breath samples from assets."""
        BREATH_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

        for wav_path in BREATH_ASSETS_DIR.glob("*.wav"):
            try:
                import wave

                with wave.open(str(wav_path)) as wf:
                    raw = wf.readframes(wf.getnframes())
                    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    bt = self._classify_breath_file(wav_path.stem)
                    self._library[bt].append(audio)
            except Exception as exc:
                log.warning("breath_load_error", path=str(wav_path), error=str(exc))

        self._generate_synthetic_breaths()
        total = sum(len(v) for v in self._library.values())
        log.info("breath_library_loaded", total=total)

    def _generate_synthetic_breaths(self) -> None:
        """Generate synthetic breath sounds if no pre-recorded ones exist."""
        for bt in BreathType:
            if self._library[bt]:
                continue

            for _ in range(5):
                audio = self._synthesize_breath(bt)
                self._library[bt].append(audio)

    @staticmethod
    def _synthesize_breath(bt: BreathType) -> np.ndarray:
        """Synthesize a breath sound using filtered noise."""
        sr = 24000
        durations = {
            BreathType.INHALE_DEEP: 0.5,
            BreathType.INHALE_SHALLOW: 0.3,
            BreathType.INHALE_QUICK: 0.15,
            BreathType.EXHALE_SETTLING: 0.4,
            BreathType.EXHALE_RELIEF: 0.6,
            BreathType.MICRO_BREATH: 0.1,
        }
        dur = durations.get(bt, 0.3) + random.uniform(-0.05, 0.05)
        n = int(sr * max(dur, 0.05))
        noise = np.random.randn(n).astype(np.float32) * 0.015

        try:
            from scipy.signal import butter, lfilter

            if bt in (BreathType.INHALE_DEEP, BreathType.INHALE_SHALLOW, BreathType.INHALE_QUICK):
                b, a = butter(3, [150, 3000], btype="band", fs=sr)
            else:
                b, a = butter(3, [100, 2000], btype="band", fs=sr)
            breath = lfilter(b, a, noise).astype(np.float32)
        except ImportError:
            breath = noise

        fade = int(sr * 0.01)
        breath[:fade] *= np.linspace(0, 1, fade)
        breath[-fade:] *= np.linspace(1, 0, fade)

        vol = {
            BreathType.INHALE_DEEP: 0.2,
            BreathType.INHALE_SHALLOW: 0.12,
            BreathType.INHALE_QUICK: 0.08,
            BreathType.EXHALE_SETTLING: 0.1,
            BreathType.EXHALE_RELIEF: 0.15,
            BreathType.MICRO_BREATH: 0.05,
        }
        breath *= vol.get(bt, 0.1)
        return breath

    @staticmethod
    def _classify_breath_file(name: str) -> BreathType:
        """Classify a breath file by its name."""
        lower = name.lower()
        if "deep" in lower or "inhale_deep" in lower:
            return BreathType.INHALE_DEEP
        if "shallow" in lower:
            return BreathType.INHALE_SHALLOW
        if "quick" in lower:
            return BreathType.INHALE_QUICK
        if "exhale" in lower and "relief" in lower:
            return BreathType.EXHALE_RELIEF
        if "exhale" in lower:
            return BreathType.EXHALE_SETTLING
        if "micro" in lower:
            return BreathType.MICRO_BREATH
        return BreathType.INHALE_SHALLOW

    def should_breathe(
        self,
        sentence: str,
        position: str = "before",
        is_emotional: bool = False,
        sentence_index: int = 0,
        whisper_mode: bool = False,
    ) -> BreathEvent | None:
        """
        Determine if a breath should be injected.

        Args:
            sentence: The sentence being spoken.
            position: "before" or "after" the sentence.
            is_emotional: Whether the sentence has emotional content.
            sentence_index: Index of this sentence in the response.
            whisper_mode: Whether the voice is in whisper/quiet mode.

        Returns:
            BreathEvent if breath should occur, else None.
        """
        self._sentence_count += 1
        now = time.monotonic()

        # Whisper mode = softer breaths, but more frequent (feels intimate)
        vol_mult = 0.5 if whisper_mode else 1.0

        if position == "before":
            words = len(sentence.split())

            # Ellipsis or trailing off = soft breath before
            if sentence.strip().endswith("..."):
                return BreathEvent(
                    breath_type=BreathType.INHALE_SHALLOW,
                    position="before",
                    volume_scale=0.1 * vol_mult,
                )

            if words >= self._SENTENCE_WORD_THRESHOLD:
                return BreathEvent(
                    breath_type=BreathType.INHALE_DEEP if words > 12 else BreathType.INHALE_SHALLOW,
                    position="before",
                    volume_scale=0.18 * vol_mult,
                )

            if sentence_index == 0:
                return BreathEvent(
                    breath_type=BreathType.INHALE_QUICK,
                    position="before",
                    volume_scale=0.12 * vol_mult,
                )

            # Every 2-3 sentences, take a small breath even for short ones
            if self._sentence_count % 3 == 0 and words > 3:
                return BreathEvent(
                    breath_type=BreathType.MICRO_BREATH,
                    position="before",
                    volume_scale=0.08 * vol_mult,
                )

        elif position == "after":
            if is_emotional:
                # Heavier exhale for emotional content — like a real sigh
                return BreathEvent(
                    breath_type=BreathType.EXHALE_RELIEF
                    if whisper_mode
                    else BreathType.EXHALE_SETTLING,
                    position="after",
                    volume_scale=0.14 * vol_mult,
                )

            # Trailing off sentences get a settling exhale
            if sentence.strip().endswith("...") or sentence.strip().endswith("—"):
                return BreathEvent(
                    breath_type=BreathType.EXHALE_SETTLING,
                    position="after",
                    volume_scale=0.08 * vol_mult,
                )

            time_since_breath = now - self._last_breath_time
            if time_since_breath > self._next_micro_breath_s:
                self._last_breath_time = now
                self._next_micro_breath_s = self._jittered_interval()
                return BreathEvent(
                    breath_type=BreathType.MICRO_BREATH,
                    position="after",
                    volume_scale=0.06 * vol_mult,
                )

        return None

    def inject(self, breath_event: BreathEvent, audio: np.ndarray) -> np.ndarray:
        """
        Inject a breath sound into the audio stream.

        Args:
            breath_event: The breath event to inject.
            audio: The speech audio to inject the breath into/around.

        Returns:
            Audio with breath injected at the specified position.
        """
        samples = self._library.get(breath_event.breath_type, [])
        if not samples:
            return audio

        breath = random.choice(samples).copy()
        breath *= breath_event.volume_scale

        if breath_event.position == "before":
            silence = np.zeros(int(24000 * 0.02), dtype=np.float32)
            return np.concatenate([breath, silence, audio])
        else:
            silence = np.zeros(int(24000 * 0.02), dtype=np.float32)
            return np.concatenate([audio, silence, breath])

    @property
    def sentence_count(self) -> int:
        """Total sentences processed this session."""
        return self._sentence_count
