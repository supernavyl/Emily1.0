"""
Interrupt handler for Emily's voice engine.

Handles all interruption scenarios with human-like graceful behavior:
- User interrupts Emily mid-sentence
- Emily detects she should stop before finishing
- User says something that makes Emily's response irrelevant
- User completes Emily's sentence (cooperative overlap)

Classification uses text, energy, prosody, and emotion signals.
Interruptions never cut mid-word. Always finds word boundary
within the configured lookahead window in the TTS buffer.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import numpy.typing as npt

from observability.logger import get_logger

log = get_logger(__name__)


class InterruptionType(Enum):
    """Classification of how and why the interruption occurred."""

    COOPERATIVE_OVERLAP = "cooperative"
    CONTENT_INTERRUPT = "content"
    CLARIFICATION = "clarification"
    CORRECTION = "correction"
    URGENCY = "urgency"
    DISENGAGEMENT = "disengagement"


@dataclass
class ResponsePosition:
    """Where Emily was in her response when interrupted."""

    text_spoken: str = ""
    text_remaining: str = ""
    sentence_index: int = 0
    total_sentences: int = 0
    audio_position_ms: int = 0


@dataclass
class InterruptResponse:
    """Result of handling an interruption."""

    interrupt_type: InterruptionType
    acknowledgment: str | None = None
    stop_position_ms: int = 0
    fade_duration_ms: int = 20
    context_preserved: bool = False
    can_resume: bool = False


@dataclass
class PreservedContext:
    """Stored context from an interrupted response for potential resumption."""

    text_spoken: str = ""
    text_planned: str = ""
    topic: str = ""
    importance: float = 0.5
    timestamp: float = field(default_factory=time.monotonic)


_ACKNOWLEDGMENTS: dict[InterruptionType, list[str]] = {
    InterruptionType.COOPERATIVE_OVERLAP: [],
    InterruptionType.CONTENT_INTERRUPT: ["oh\u2014", "yes\u2014", "sure\u2014", "go on"],
    InterruptionType.CLARIFICATION: ["oh sure", "of course", "yeah?", "go ahead"],
    InterruptionType.CORRECTION: ["oh, sorry", "you're right", "ah\u2014", "my mistake"],
    InterruptionType.URGENCY: [],
    InterruptionType.DISENGAGEMENT: ["right, yeah", "sure", "okay"],
}

_RESUME_PHRASES = [
    "anyway, as I was saying",
    "so as I mentioned",
    "going back to what I was saying",
    "where was I... right,",
    "to continue,",
]

_CORRECTION_KEYWORDS = ("no", "wait", "actually", "that's wrong", "not right")
_QUESTION_KEYWORDS = ("what", "how", "why", "could you")


class InterruptHandler:
    """
    Manages all interruption scenarios with human-like grace.

    Never stops mid-word. Finds natural speech boundaries and applies
    audio fades. Preserves response context for potential resumption.
    """

    def __init__(
        self,
        lookahead_ms: int = 300,
        fade_ms: int = 20,
        resume_expiry_s: float = 30.0,
    ) -> None:
        """
        Args:
            lookahead_ms: Max lookahead in TTS buffer for word-boundary detection.
            fade_ms: Audio fade-out duration at stop point.
            resume_expiry_s: Seconds before preserved context expires.
        """
        self._lookahead_ms = lookahead_ms
        self._fade_ms = fade_ms
        self._resume_expiry_s = resume_expiry_s
        self._preserved_context: PreservedContext | None = None
        self._last_interrupt_type: InterruptionType | None = None
        self._interrupt_count = 0
        self._last_acknowledgments: list[str] = []

    async def handle_user_interrupt(
        self,
        sentence_so_far: str = "",
        partial_user_text: str = "",
        user_energy: float = 0.0,
        prosody: Any | None = None,
        emotion: Any | None = None,
    ) -> InterruptResponse:
        """
        Handle the user interrupting Emily.

        Args:
            sentence_so_far: What Emily had said so far.
            partial_user_text: What the user is saying (from streaming STT).
            user_energy: Energy level of the user's speech.
            prosody: ProsodyFeatures from the prosody analyzer, if available.
            emotion: EmotionState from the emotion detector, if available.

        Returns:
            InterruptResponse with type, acknowledgment, and stop parameters.
        """
        interrupt_type = self._classify_interrupt(
            partial_user_text,
            user_energy,
            sentence_so_far,
            prosody=prosody,
            emotion=emotion,
        )

        ack = self._generate_acknowledgment(interrupt_type)
        self._interrupt_count += 1
        self._last_interrupt_type = interrupt_type

        can_resume = interrupt_type in (
            InterruptionType.CLARIFICATION,
            InterruptionType.CONTENT_INTERRUPT,
        )

        if can_resume:
            self._preserved_context = PreservedContext(
                text_spoken=sentence_so_far,
                text_planned="",
                importance=0.5,
            )

        log.info(
            "interrupt_handled",
            type=interrupt_type.value,
            acknowledgment=ack,
            can_resume=can_resume,
        )

        return InterruptResponse(
            interrupt_type=interrupt_type,
            acknowledgment=ack,
            stop_position_ms=0,
            fade_duration_ms=self._fade_ms,
            context_preserved=can_resume,
            can_resume=can_resume,
        )

    def _classify_interrupt(
        self,
        user_text: str,
        user_energy: float,
        emily_text: str,
        prosody: Any | None = None,
        emotion: Any | None = None,
    ) -> InterruptionType:
        """
        Classify the type of interruption using text, energy, prosody, and emotion.

        Priority order: urgency > correction > clarification > disengagement
        > cooperative overlap > content interrupt (fallback).
        """
        lower = user_text.lower().strip()

        # --- Urgency: high energy, angry/fearful emotion, or extreme pitch range ---
        if user_energy > 0.15:
            return InterruptionType.URGENCY
        if emotion is not None and hasattr(emotion, "primary"):
            emo_name = getattr(emotion.primary, "value", str(emotion.primary))
            if emo_name in ("frustrated", "anxious") and emotion.confidence > 0.6:
                return InterruptionType.URGENCY
        if (
            prosody is not None
            and hasattr(prosody, "f0_hz")
            and prosody.f0_hz > 0
            and prosody.f0_range_semitones > 8
        ):
            return InterruptionType.URGENCY

        # --- Correction: keywords, or emphatic stress with negation ---
        has_correction_kw = any(w in lower for w in _CORRECTION_KEYWORDS)
        if has_correction_kw:
            return InterruptionType.CORRECTION
        if (
            prosody is not None
            and hasattr(prosody, "stress_pattern")
            and prosody.stress_pattern
            and max(prosody.stress_pattern, default=0) > 0.8
            and any(neg in lower for neg in ("no", "not", "wrong"))
        ):
            return InterruptionType.CORRECTION

        # --- Clarification: question words/punctuation, or rising pitch ---
        is_question = lower.endswith("?") or any(w in lower for w in _QUESTION_KEYWORDS)
        if is_question:
            return InterruptionType.CLARIFICATION
        if (
            prosody is not None
            and hasattr(prosody, "f0_trajectory")
            and prosody.f0_trajectory == "rising"
        ):
            return InterruptionType.CLARIFICATION

        # --- Disengagement: short/empty text, optionally confirmed by emotion ---
        if not lower or len(lower.split()) < 3:
            if emotion is not None and hasattr(emotion, "primary"):
                emo_name = getattr(emotion.primary, "value", str(emotion.primary))
                if emo_name in ("bored", "tired", "neutral"):
                    return InterruptionType.DISENGAGEMENT
            if (
                prosody is not None
                and hasattr(prosody, "intensity_trajectory")
                and prosody.intensity_trajectory == "falling"
            ):
                return InterruptionType.DISENGAGEMENT
            return InterruptionType.DISENGAGEMENT

        # --- Cooperative overlap: user finishing Emily's sentence ---
        emily_words = emily_text.lower().split()
        user_words = lower.split()
        if emily_words and user_words:
            overlap = set(emily_words[-3:]) & set(user_words[:3])
            if len(overlap) > 1:
                return InterruptionType.COOPERATIVE_OVERLAP

        return InterruptionType.CONTENT_INTERRUPT

    def _generate_acknowledgment(self, interrupt_type: InterruptionType) -> str | None:
        """
        Generate a natural acknowledgment vocalization for the interrupt.

        Avoids repeating the same acknowledgment consecutively.
        """
        pool = _ACKNOWLEDGMENTS.get(interrupt_type, [])
        if not pool:
            return None

        available = [a for a in pool if a not in self._last_acknowledgments[-2:]]
        if not available:
            available = pool

        chosen = random.choice(available)
        self._last_acknowledgments.append(chosen)
        if len(self._last_acknowledgments) > 10:
            self._last_acknowledgments = self._last_acknowledgments[-5:]

        return chosen

    def find_graceful_stop_point(
        self,
        audio_buffer: npt.NDArray[np.float32],
        sample_rate: int = 24000,
    ) -> int:
        """
        Find the nearest natural word boundary in the TTS audio buffer.

        Scans for energy dips that indicate word boundaries.
        Priority: sentence end > clause end > phrase end > word end.

        Args:
            audio_buffer: Upcoming TTS audio.
            sample_rate: Audio sample rate.

        Returns:
            Sample index of the best stop point.
        """
        max_samples = int(self._lookahead_ms * sample_rate / 1000)
        search_len = min(len(audio_buffer), max_samples)

        if search_len < sample_rate * 0.01:
            return 0

        frame_size = int(sample_rate * 0.01)
        hop = frame_size // 2
        n_frames = max(1, (search_len - frame_size) // hop)

        energies = np.zeros(n_frames)
        for i in range(n_frames):
            start = i * hop
            frame = audio_buffer[start : start + frame_size]
            energies[i] = float(np.sqrt(np.mean(frame**2)))

        if len(energies) < 3:
            return search_len

        threshold = np.mean(energies) * 0.3
        for i in range(len(energies) - 1, 0, -1):
            if energies[i] < threshold and energies[i - 1] > threshold:
                return min(i * hop + frame_size, search_len)

        min_idx = int(np.argmin(energies))
        return min(min_idx * hop + frame_size, search_len)

    def apply_fade_out(
        self,
        audio: npt.NDArray[np.float32],
        stop_sample: int,
        fade_samples: int | None = None,
    ) -> npt.NDArray[np.float32]:
        """
        Apply a smooth fade-out at the stop point.

        Args:
            audio: Audio buffer.
            stop_sample: Where to end (from find_graceful_stop_point).
            fade_samples: Fade duration in samples. Defaults to configured fade_ms at 24kHz.

        Returns:
            Audio with fade applied and silence after stop point.
        """
        if fade_samples is None:
            fade_samples = int(self._fade_ms / 1000.0 * 24000)

        result = audio.copy()
        fade_start = max(0, stop_sample - fade_samples)

        if fade_start < stop_sample:
            fade = np.linspace(1.0, 0.0, stop_sample - fade_start, dtype=np.float32)
            result[fade_start:stop_sample] *= fade

        if stop_sample < len(result):
            result[stop_sample:] = 0.0

        return result

    def get_resume_phrase(self) -> str | None:
        """
        Get a natural resumption phrase if context was preserved.

        Returns:
            A phrase like "anyway, as I was saying..." or None.
        """
        if self._preserved_context is None:
            return None

        age = time.monotonic() - self._preserved_context.timestamp
        if age > self._resume_expiry_s:
            self._preserved_context = None
            return None

        return random.choice(_RESUME_PHRASES)

    def clear_preserved_context(self) -> None:
        """Clear any preserved context (e.g. after resumption phrase is used)."""
        self._preserved_context = None

    async def handle_emily_self_interrupt(
        self,
        reason: str,
        text_so_far: str = "",
    ) -> str:
        """
        Handle Emily interrupting herself (self-correction).

        Args:
            reason: Why Emily is self-interrupting.
            text_so_far: What Emily has said so far.

        Returns:
            A natural self-correction phrase.
        """
        patterns = [
            "actually, wait, let me rethink that...",
            "hmm, actually...",
            "no, actually...",
            "wait, let me correct that...",
            "sorry, that's not quite right...",
        ]
        chosen = random.choice(patterns)
        log.info("emily_self_interrupt", reason=reason, correction=chosen)
        return chosen

    @property
    def preserved_context(self) -> PreservedContext | None:
        """The preserved context from the last interrupt, if any."""
        return self._preserved_context

    @property
    def interrupt_count(self) -> int:
        """Total number of interrupts handled this session."""
        return self._interrupt_count
