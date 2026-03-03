"""
Expressive sound engine for Emily's voice.

Detects expressive markers in LLM output text (laughter, hesitation,
sighs) and replaces them with synthesized audio that sounds natural —
because TTS engines read "haha" as a flat word, not as actual laughter.

Architecture:
    LLM text → ExpressiveEngine.process(sentence) → list[Segment]
    Each Segment is either:
      - TextSegment: clean text for normal TTS synthesis
      - AudioSegment: pre-rendered expressive audio (laugh, hmm, sigh)

The TTSManager splices these together: TTS for text, raw PCM for audio.

Synthesis approach:
    - Laughter: pitch-modulated glottal pulses with aspiration noise bursts
    - Hesitation (hmm/hm): nasal formant resonance with gentle pitch contour
    - Chuckle (heh/hehe): short breathy voiced burst
    - Filler (um/uh): mid-vowel with nasal onset
    - Sigh: breathy noise with slow pitch descent
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from enum import Enum, auto

import numpy as np
import numpy.typing as npt

from observability.logger import get_logger

log = get_logger(__name__)

# ── Segment types ───────────────────────────────────────────────────


class SegmentType(Enum):
    TEXT = auto()
    AUDIO = auto()


@dataclass
class TextSegment:
    """Clean text to be synthesized by the normal TTS engine."""

    type: SegmentType = field(default=SegmentType.TEXT, init=False)
    text: str = ""


@dataclass
class AudioSegment:
    """Pre-rendered expressive audio (float32, 24 kHz mono)."""

    type: SegmentType = field(default=SegmentType.AUDIO, init=False)
    audio: npt.NDArray[np.float32] = field(default_factory=lambda: np.empty(0, dtype=np.float32))
    label: str = ""  # For logging: "laugh", "hmm", "sigh", etc.


Segment = TextSegment | AudioSegment

# ── Expressive types ────────────────────────────────────────────────


class ExpressiveType(Enum):
    LAUGH = auto()  # haha, hahaha
    CHUCKLE = auto()  # ha, heh, hehe
    HESITATION = auto()  # hmm, hm, mm
    FILLER = auto()  # um, uh, umm, uhh
    SIGH = auto()  # hhhh, *sigh-like patterns*
    GIGGLE = auto()  # hehe, hihi, teehee


# ── Pattern detection ───────────────────────────────────────────────

# Order matters — longer patterns first to prevent partial matches.
_EXPRESSIVE_PATTERNS: list[tuple[re.Pattern[str], ExpressiveType]] = [
    # Multi-syllable laughs: hahaha, hahahaha, etc.
    (re.compile(r"\b(?:ha\s*){3,}\b", re.I), ExpressiveType.LAUGH),
    # Standard laugh: haha
    (re.compile(r"\bhaha\b", re.I), ExpressiveType.LAUGH),
    # Giggle: hehe, hihi, teehee
    (re.compile(r"\b(?:he\s*he|hi\s*hi|tee\s*hee)\b", re.I), ExpressiveType.GIGGLE),
    # Chuckle: single ha, heh
    (re.compile(r"\bheh\b", re.I), ExpressiveType.CHUCKLE),
    (re.compile(r"\bha\b(?!\w)", re.I), ExpressiveType.CHUCKLE),
    # Hesitation: hmm, hm, mm, mmm
    (re.compile(r"\bh?mm+\b", re.I), ExpressiveType.HESITATION),
    # Filler: um, uh, umm, uhh, er
    (re.compile(r"\bu[hm]+\b", re.I), ExpressiveType.FILLER),
    (re.compile(r"\ber+\b", re.I), ExpressiveType.FILLER),
    # Sigh: hhhh (3+ h's), or explicit "sigh" written out
    (re.compile(r"\bh{3,}\b", re.I), ExpressiveType.SIGH),
]

_SR = 24000  # All expressive audio is 24 kHz to match Kokoro output


class ExpressiveEngine:
    """Detects and synthesizes expressive sounds in LLM output text.

    Usage::

        engine = ExpressiveEngine()
        segments = engine.process("So yeah haha that's really funny")
        # → [TextSegment("So yeah "), AudioSegment(laugh), TextSegment(" that's really funny")]
    """

    def __init__(self, voice_pitch_hz: float = 210.0) -> None:
        """
        Args:
            voice_pitch_hz: Base pitch for expressive synthesis.
                Higher for feminine voices (~200-220 Hz),
                lower for masculine (~100-130 Hz).
        """
        self._base_pitch = voice_pitch_hz
        self._cache: dict[str, npt.NDArray[np.float32]] = {}
        log.info("ExpressiveEngine initialised (base_pitch=%.0fHz)", voice_pitch_hz)

    def process(self, text: str) -> list[Segment]:
        """Split text into text and audio segments.

        Scans for expressive patterns, synthesizes audio for each match,
        and returns interleaved TextSegment / AudioSegment list.

        Args:
            text: Raw sentence from the LLM.

        Returns:
            Ordered list of Segment objects.
        """
        if not text.strip():
            return [TextSegment(text=text)]

        # Find all expressive matches with their positions
        matches: list[tuple[int, int, ExpressiveType, str]] = []
        for pattern, expr_type in _EXPRESSIVE_PATTERNS:
            for m in pattern.finditer(text):
                # Check this match doesn't overlap with an existing one
                overlaps = any(not (m.end() <= s or m.start() >= e) for s, e, _, _ in matches)
                if not overlaps:
                    matches.append((m.start(), m.end(), expr_type, m.group()))

        if not matches:
            return [TextSegment(text=text)]

        # Sort by position
        matches.sort(key=lambda x: x[0])

        segments: list[Segment] = []
        prev_end = 0

        for start, end, expr_type, matched_text in matches:
            # Text before this expressive
            if start > prev_end:
                before = text[prev_end:start]
                if before.strip():
                    segments.append(TextSegment(text=before))
                elif before:
                    # Preserve whitespace-only segments as pauses
                    segments.append(TextSegment(text=before))

            # Synthesize the expressive audio
            audio = self._synthesize(expr_type, matched_text)
            label = expr_type.name.lower()
            segments.append(AudioSegment(audio=audio, label=label))
            log.debug("expressive_detected", type=label, text=matched_text)

            prev_end = end

        # Text after the last expressive
        if prev_end < len(text):
            after = text[prev_end:]
            if after.strip():
                segments.append(TextSegment(text=after))

        return segments

    # ── Audio synthesis ──────────────────────────────────────────────

    def _synthesize(self, expr_type: ExpressiveType, matched_text: str) -> npt.NDArray[np.float32]:
        """Route to the appropriate synthesizer based on expressive type."""
        cache_key = f"{expr_type.name}:{matched_text.lower().strip()}"
        if cache_key in self._cache:
            # Return a copy with slight variation so it doesn't sound identical
            return self._add_micro_variation(self._cache[cache_key])

        if expr_type == ExpressiveType.LAUGH:
            audio = self._synth_laugh(matched_text)
        elif expr_type == ExpressiveType.GIGGLE:
            audio = self._synth_giggle(matched_text)
        elif expr_type == ExpressiveType.CHUCKLE:
            audio = self._synth_chuckle(matched_text)
        elif expr_type == ExpressiveType.HESITATION:
            audio = self._synth_hesitation(matched_text)
        elif expr_type == ExpressiveType.FILLER:
            audio = self._synth_filler(matched_text)
        elif expr_type == ExpressiveType.SIGH:
            audio = self._synth_sigh()
        else:
            audio = np.zeros(int(_SR * 0.1), dtype=np.float32)

        self._cache[cache_key] = audio.copy()
        return audio

    def _synth_laugh(self, text: str) -> npt.NDArray[np.float32]:
        """Synthesize laughter: pitch-modulated glottal pulses + aspiration.

        Real laughter is rapid voiced bursts ("ha") separated by breathy
        aspiration noise. Each burst has descending pitch. The number of
        syllables is inferred from the text length.
        """
        # Count syllables from "ha" repetitions
        syllables = max(2, text.lower().count("ha"))
        syllables = min(syllables, 8)  # Cap at 8

        burst_dur = 0.07 + random.uniform(-0.01, 0.01)
        gap_dur = 0.04 + random.uniform(-0.01, 0.01)

        # Pitch starts high and descends across syllables
        start_pitch = self._base_pitch * 1.6 + random.uniform(-10, 10)
        end_pitch = self._base_pitch * 1.1

        parts: list[npt.NDArray[np.float32]] = []

        for i in range(syllables):
            # Interpolated pitch for this syllable (descending)
            t_ratio = i / max(syllables - 1, 1)
            syllable_pitch = start_pitch + (end_pitch - start_pitch) * t_ratio
            # Add per-syllable jitter
            syllable_pitch += random.uniform(-5, 5)

            # Voiced burst (glottal pulse train + harmonics)
            n_burst = int(_SR * burst_dur)
            t = np.arange(n_burst, dtype=np.float32) / _SR

            # Glottal pulse with harmonics
            phase = 2 * np.pi * syllable_pitch * t
            burst = (
                np.sin(phase) * 0.25
                + np.sin(phase * 2) * 0.12
                + np.sin(phase * 3) * 0.06
                + np.sin(phase * 4) * 0.03
            )

            # Amplitude envelope: sharp attack, quick decay
            env = np.exp(-t * 18).astype(np.float32)
            env[: int(_SR * 0.005)] *= np.linspace(0, 1, int(_SR * 0.005))
            burst = (burst * env).astype(np.float32)

            # Add aspiration noise (breathy quality)
            aspiration = np.random.randn(n_burst).astype(np.float32) * 0.04
            aspiration = self._bandpass(aspiration, 800, 4000)
            burst += aspiration * env * 0.5

            parts.append(burst)

            # Gap between syllables: pure aspiration noise
            if i < syllables - 1:
                n_gap = int(_SR * gap_dur)
                gap_noise = np.random.randn(n_gap).astype(np.float32) * 0.02
                gap_noise = self._bandpass(gap_noise, 500, 3000)
                # Fade the gap
                gap_env = np.ones(n_gap, dtype=np.float32)
                fade = int(_SR * 0.008)
                if fade > 0 and fade < n_gap:
                    gap_env[:fade] *= np.linspace(0, 1, fade)
                    gap_env[-fade:] *= np.linspace(1, 0, fade)
                parts.append(gap_noise * gap_env)

        audio = np.concatenate(parts)

        # Overall volume envelope: slight crescendo then decrescendo
        total_env = np.ones(len(audio), dtype=np.float32)
        ramp_up = int(len(audio) * 0.1)
        ramp_down = int(len(audio) * 0.25)
        if ramp_up > 0:
            total_env[:ramp_up] *= np.linspace(0.3, 1.0, ramp_up)
        if ramp_down > 0:
            total_env[-ramp_down:] *= np.linspace(1.0, 0.0, ramp_down)

        audio *= total_env * 0.3  # Overall volume
        return self._fade_edges(audio)

    def _synth_giggle(self, text: str) -> npt.NDArray[np.float32]:
        """Synthesize a giggle: higher-pitched, faster, lighter than a laugh."""
        syllables = max(2, text.lower().count("he") + text.lower().count("hi"))
        syllables = min(syllables, 6)

        burst_dur = 0.05
        gap_dur = 0.025

        pitch = self._base_pitch * 1.8 + random.uniform(-5, 5)
        parts: list[npt.NDArray[np.float32]] = []

        for i in range(syllables):
            n = int(_SR * burst_dur)
            t = np.arange(n, dtype=np.float32) / _SR
            p = pitch - i * 8  # Slight descent

            phase = 2 * np.pi * p * t
            burst = np.sin(phase).astype(np.float32) * 0.15
            burst += np.sin(phase * 2).astype(np.float32) * 0.08

            env = np.exp(-t * 25).astype(np.float32)
            burst *= env

            # More breathy than a full laugh
            noise = np.random.randn(n).astype(np.float32) * 0.05
            noise = self._bandpass(noise, 1000, 5000)
            burst += noise * env * 0.6

            parts.append(burst)

            if i < syllables - 1:
                n_gap = int(_SR * gap_dur)
                gap = np.random.randn(n_gap).astype(np.float32) * 0.01
                parts.append(self._bandpass(gap, 800, 3500))

        audio = np.concatenate(parts) * 0.25
        return self._fade_edges(audio)

    def _synth_chuckle(self, text: str) -> npt.NDArray[np.float32]:
        """Synthesize a short chuckle: single 'heh' or 'ha' burst."""
        dur = 0.12 + random.uniform(-0.02, 0.02)
        n = int(_SR * dur)
        t = np.arange(n, dtype=np.float32) / _SR

        pitch = self._base_pitch * 1.3 + random.uniform(-8, 8)
        phase = 2 * np.pi * pitch * t

        # Single voiced burst
        audio = (np.sin(phase) * 0.2 + np.sin(phase * 2) * 0.1 + np.sin(phase * 3) * 0.04).astype(
            np.float32
        )

        # Sharp attack, moderate decay
        env = np.exp(-t * 12).astype(np.float32)
        attack = int(_SR * 0.008)
        if attack > 0:
            env[:attack] *= np.linspace(0, 1, attack)
        audio *= env

        # Aspiration overlay
        noise = np.random.randn(n).astype(np.float32) * 0.03
        noise = self._bandpass(noise, 600, 3500)
        audio += noise * env * 0.4

        return self._fade_edges(audio * 0.28)

    def _synth_hesitation(self, text: str) -> npt.NDArray[np.float32]:
        """Synthesize 'hmm'/'hm': nasal resonance with gentle pitch contour.

        Real nasal murmur has:
        - Low fundamental (~base pitch)
        - Strong nasal formant around 250-300 Hz
        - Anti-resonance around 1000 Hz (nasal zero)
        - Gentle pitch movement (slight rise then fall)
        """
        # Duration based on how many m's
        m_count = text.lower().count("m")
        dur = 0.25 + m_count * 0.08 + random.uniform(-0.03, 0.03)
        dur = min(dur, 0.8)
        n = int(_SR * dur)
        np.arange(n, dtype=np.float32) / _SR

        # Pitch contour: slight rise then gentle fall (questioning hum)
        pitch_start = self._base_pitch * 0.95
        pitch_mid = self._base_pitch * 1.05
        pitch_end = self._base_pitch * 0.9

        # Two-phase contour
        mid_point = int(n * 0.35)
        pitch_contour = np.empty(n, dtype=np.float32)
        pitch_contour[:mid_point] = np.linspace(pitch_start, pitch_mid, mid_point)
        pitch_contour[mid_point:] = np.linspace(pitch_mid, pitch_end, n - mid_point)

        # Generate voiced signal with harmonics
        phase = np.cumsum(2 * np.pi * pitch_contour / _SR)
        audio = (
            np.sin(phase) * 0.22
            + np.sin(phase * 2) * 0.09
            + np.sin(phase * 3) * 0.04
            + np.sin(phase * 4) * 0.02
        ).astype(np.float32)

        # Add nasal quality via formant filtering
        audio = self._apply_nasal_formant(audio)

        # Gentle amplitude envelope
        env = np.ones(n, dtype=np.float32)
        attack = int(_SR * 0.04)
        release = int(_SR * 0.06)
        if attack > 0:
            env[:attack] = np.linspace(0, 1, attack)
        if release > 0:
            env[-release:] = np.linspace(1, 0, release)

        audio *= env * 0.3
        return audio

    def _synth_filler(self, text: str) -> npt.NDArray[np.float32]:
        """Synthesize 'um'/'uh': mid vowel with nasal onset.

        'Um' = nasal /m/ onset → open mid vowel /ʌ/
        'Uh' = glottal onset → open mid vowel /ʌ/
        """
        dur = 0.2 + random.uniform(-0.03, 0.03)
        n = int(_SR * dur)
        t = np.arange(n, dtype=np.float32) / _SR

        pitch = self._base_pitch * 0.95 + random.uniform(-5, 5)
        # Slight downward drift
        pitch_contour = pitch - t * 20

        phase = np.cumsum(2 * np.pi * pitch_contour / _SR)
        audio = (np.sin(phase) * 0.2 + np.sin(phase * 2) * 0.1 + np.sin(phase * 3) * 0.05).astype(
            np.float32
        )

        has_nasal = "m" in text.lower()
        if has_nasal:
            # Nasal onset (first 30%)
            nasal_end = int(n * 0.3)
            nasal_part = audio[:nasal_end].copy()
            nasal_part = self._apply_nasal_formant(nasal_part)
            audio[:nasal_end] = nasal_part

        # Vowel body: slight breathiness
        noise = np.random.randn(n).astype(np.float32) * 0.01
        audio += self._bandpass(noise, 300, 2500)

        env = np.ones(n, dtype=np.float32)
        attack = int(_SR * 0.02)
        release = int(_SR * 0.05)
        if attack > 0:
            env[:attack] = np.linspace(0, 1, attack)
        if release > 0:
            env[-release:] = np.linspace(1, 0, release)

        return audio * env * 0.25

    def _synth_sigh(self) -> npt.NDArray[np.float32]:
        """Synthesize a sigh: breathy voicing with slow pitch descent.

        A sigh is mostly noise with a hint of voicing, exhaled slowly.
        Pitch starts mid-range and drifts down.
        """
        dur = 0.5 + random.uniform(-0.05, 0.05)
        n = int(_SR * dur)
        t = np.arange(n, dtype=np.float32) / _SR

        # Very breathy — mostly noise with slight voicing
        pitch = self._base_pitch * 0.85
        pitch_contour = pitch - t * 30  # Descending

        phase = np.cumsum(2 * np.pi * pitch_contour / _SR)
        voicing = np.sin(phase).astype(np.float32) * 0.05

        # Dominant breathy noise
        noise = np.random.randn(n).astype(np.float32) * 0.04
        noise = self._bandpass(noise, 150, 2500)

        audio = voicing + noise

        # Envelope: gradual onset, long tail
        env = np.ones(n, dtype=np.float32)
        attack = int(_SR * 0.08)
        release = int(_SR * 0.15)
        if attack > 0:
            env[:attack] = np.linspace(0, 1, attack)
        if release > 0:
            env[-release:] = np.linspace(1, 0, release)

        return audio * env * 0.2

    # ── Audio utilities ──────────────────────────────────────────────

    @staticmethod
    def _bandpass(
        audio: npt.NDArray[np.float32],
        low_hz: float,
        high_hz: float,
        order: int = 3,
    ) -> npt.NDArray[np.float32]:
        """Apply a bandpass filter. Falls back to identity if scipy unavailable."""
        try:
            from scipy.signal import butter, lfilter

            b, a = butter(order, [low_hz, high_hz], btype="band", fs=_SR)
            return lfilter(b, a, audio).astype(np.float32)
        except ImportError:
            return audio

    @staticmethod
    def _apply_nasal_formant(audio: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
        """Shape audio to sound nasal (boost ~250Hz, attenuate ~1000Hz)."""
        try:
            from scipy.signal import butter, lfilter

            # Boost nasal formant (250 Hz region)
            b1, a1 = butter(2, [200, 350], btype="band", fs=_SR)
            nasal_boost = lfilter(b1, a1, audio).astype(np.float32)

            # Attenuate anti-resonance (1000 Hz region)
            b2, a2 = butter(2, [800, 1200], btype="band", fs=_SR)
            anti_resonance = lfilter(b2, a2, audio).astype(np.float32)

            return (audio + nasal_boost * 0.8 - anti_resonance * 0.3).astype(np.float32)
        except ImportError:
            return audio

    @staticmethod
    def _fade_edges(
        audio: npt.NDArray[np.float32],
        fade_ms: float = 5.0,
    ) -> npt.NDArray[np.float32]:
        """Apply short fade-in and fade-out to prevent clicks."""
        fade = int(_SR * fade_ms / 1000)
        if fade <= 0 or len(audio) < fade * 2:
            return audio
        audio = audio.copy()
        audio[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
        audio[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
        return audio

    @staticmethod
    def _add_micro_variation(
        audio: npt.NDArray[np.float32],
    ) -> npt.NDArray[np.float32]:
        """Add subtle pitch/timing variation so cached audio doesn't repeat identically."""
        # Tiny speed variation (±3%) via resampling
        speed_factor = 1.0 + random.uniform(-0.03, 0.03)
        n_out = int(len(audio) / speed_factor)
        if n_out < 10:
            return audio.copy()
        indices = np.linspace(0, len(audio) - 1, n_out)
        varied = np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

        # Tiny volume variation (±5%)
        varied *= 1.0 + random.uniform(-0.05, 0.05)
        return varied
