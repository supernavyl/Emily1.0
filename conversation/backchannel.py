"""
Backchannel generation engine for Emily.

Generates listener vocalizations ("mmhm", "right", "yeah", "I see") while
the user is still speaking. These run on the output stream simultaneously
with input processing and create the perception of active listening.

Six backchannel types with timing, volume, and diversity rules.
Pre-recorded samples preferred for naturalness; TTS fallback available.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt

from observability.logger import get_logger

if TYPE_CHECKING:
    from perception.audio.prosody_analyzer import ProsodyFeatures

log = get_logger(__name__)

BACKCHANNEL_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "backchannels"


class BackchannelType(Enum):
    """Categories of listener vocalizations."""

    CONTINUER = auto()
    ACKNOWLEDGMENT = auto()
    AGREEMENT = auto()
    EMPATHY = auto()
    SURPRISE = auto()
    COMPLETION = auto()


@dataclass
class BackchannelEvent:
    """A backchannel to be rendered and played."""

    bc_type: BackchannelType
    token: str
    volume_scale: float = 0.35
    timestamp: float = field(default_factory=time.monotonic)


_TOKEN_POOLS: dict[BackchannelType, list[str]] = {
    BackchannelType.CONTINUER: [
        "mmhm",
        "mhm",
        "yeah",
        "uh-huh",
        "mm",
        "right",
        "yep",
        "uh huh",
        "mmm",
        "yup",
    ],
    BackchannelType.ACKNOWLEDGMENT: [
        "I see",
        "got it",
        "okay",
        "right",
        "ah",
        "understood",
        "sure",
        "alright",
        "I hear you",
        "gotcha",
    ],
    BackchannelType.AGREEMENT: [
        "exactly",
        "absolutely",
        "definitely",
        "totally",
        "for sure",
        "that's right",
        "indeed",
        "precisely",
        "true",
        "yes",
    ],
    BackchannelType.EMPATHY: [
        "oh wow",
        "of course",
        "that makes sense",
        "oh no",
        "I understand",
        "oh",
        "that's tough",
        "I can imagine",
        "oh man",
        "I hear you",
    ],
    BackchannelType.SURPRISE: [
        "oh really?",
        "huh",
        "wait",
        "no way",
        "wow",
        "seriously?",
        "oh?",
        "whoa",
        "interesting",
        "is that right?",
    ],
    BackchannelType.COMPLETION: [
        "right",
        "yeah",
        "exactly",
        "of course",
        "sure",
        "makes sense",
        "naturally",
        "obviously",
        "clearly",
        "got it",
    ],
}

_MIN_INTERVAL_S = 4.0
_VOLUME_SCALE = 0.35


class BackchannelEngine:
    """
    Generates context-appropriate listener vocalizations with timing rules.

    Rules:
    - Max 1 backchannel per 4 seconds
    - Volume: 30-40% of normal speaking volume
    - Never overlap stressed syllables
    - Never the same token twice consecutively
    - Prosody: upspeak on continuers, flat on acknowledgments
    """

    def __init__(self) -> None:
        self._last_bc_time: float = 0.0
        self._last_tokens: list[str] = []
        self._prerecorded: dict[str, npt.NDArray[np.float32]] = {}
        self._session_bc_count = 0

    async def load_prerecorded(self) -> None:
        """Load pre-recorded backchannel audio samples from assets."""
        BACKCHANNEL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        for wav_path in BACKCHANNEL_ASSETS_DIR.glob("*.wav"):
            try:
                import wave

                with wave.open(str(wav_path)) as wf:
                    raw = wf.readframes(wf.getnframes())
                    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    self._prerecorded[wav_path.stem] = audio
            except Exception as exc:
                log.debug("backchannel_load_error", path=str(wav_path), error=str(exc))

        if self._prerecorded:
            log.info("backchannels_loaded", count=len(self._prerecorded))

    def is_safe_to_insert(self, prosody: ProsodyFeatures | None) -> bool:
        """
        Check whether it is safe to insert a backchannel right now.

        A backchannel should only fire at inter-pausal unit boundaries
        (pause_type is breath / filled / silence) and must never overlap
        a stressed syllable (last stress_pattern value <= 0.7).

        Args:
            prosody: Current prosody features, or None to skip the check.

        Returns:
            True if the current moment is a safe insertion point.
        """
        if prosody is None:
            return True

        safe_pause_types = ("breath", "filled", "silence")
        if prosody.pause_type not in safe_pause_types:
            return False

        return not (prosody.stress_pattern and prosody.stress_pattern[-1] > 0.7)

    async def should_backchannel(
        self,
        partial_text: str = "",
        emotion: Any = None,
        turn_signal: Any = None,
        prosody: ProsodyFeatures | None = None,
        completion_prediction_score: float = 0.0,
    ) -> BackchannelEvent | None:
        """
        Decide whether a backchannel is appropriate right now.

        Args:
            partial_text: Current partial STT text.
            emotion: Current detected user emotion.
            turn_signal: Current turn detection signal.
            prosody: Current prosody features (for phrase-boundary safety).
            completion_prediction_score: Syntactic completeness score from
                the turn detector (0.0-1.0).  When > 0.90, a COMPLETION
                backchannel may be selected.

        Returns:
            BackchannelEvent if appropriate, else None.
        """
        now = time.monotonic()
        if now - self._last_bc_time < _MIN_INTERVAL_S:
            return None

        if not self.is_safe_to_insert(prosody):
            return None

        bc_type = self._select_type(
            partial_text,
            emotion,
            completion_prediction_score,
        )
        if bc_type is None:
            return None

        token = self._select_token(bc_type)
        if token is None:
            return None

        self._last_bc_time = now
        self._last_tokens.append(token)
        if len(self._last_tokens) > 10:
            self._last_tokens = self._last_tokens[-5:]
        self._session_bc_count += 1

        return BackchannelEvent(
            bc_type=bc_type,
            token=token,
            volume_scale=_VOLUME_SCALE,
        )

    def _select_type(
        self,
        text: str,
        emotion: Any,
        completion_prediction_score: float = 0.0,
    ) -> BackchannelType | None:
        """
        Select the appropriate backchannel type based on context.

        Args:
            text: Current partial transcript.
            emotion: Detected user emotion state.
            completion_prediction_score: Syntactic completeness score (0-1).
                When > 0.90 a COMPLETION backchannel is attempted.
        """
        if completion_prediction_score > 0.90:
            log.debug(
                "completion_backchannel_candidate",
                score=f"{completion_prediction_score:.2f}",
            )
            return BackchannelType.COMPLETION

        lower = text.lower().strip()

        elicitors = ("you know", "right?", "know what i mean", "get it?", "makes sense?", "you see")
        for e in elicitors:
            if lower.endswith(e) or lower.endswith(e.rstrip("?")):
                return BackchannelType.CONTINUER

        if emotion is not None:
            valence = getattr(emotion, "valence", 0.0)
            arousal = getattr(emotion, "arousal", 0.0)
            if valence < -0.3:
                return BackchannelType.EMPATHY
            if arousal > 0.5 and valence > 0.3:
                return BackchannelType.AGREEMENT

        emotional_words = ("terrible", "amazing", "awful", "wonderful", "sad", "angry")
        if any(w in lower for w in emotional_words):
            return BackchannelType.EMPATHY

        surprise_indicators = (
            "you won't believe",
            "guess what",
            "surprisingly",
            "turns out",
            "actually,",
        )
        if any(w in lower for w in surprise_indicators):
            return BackchannelType.SURPRISE

        if len(lower.split()) > 10:
            return BackchannelType.ACKNOWLEDGMENT

        if len(lower.split()) > 5:
            return BackchannelType.CONTINUER

        return None

    def _select_token(self, bc_type: BackchannelType) -> str | None:
        """Select a specific token, avoiding recent repetitions."""
        pool = _TOKEN_POOLS.get(bc_type, [])
        if not pool:
            return None

        available = [t for t in pool if t not in self._last_tokens[-2:]]
        if not available:
            available = pool

        return random.choice(available)

    async def render_backchannel(self, event: BackchannelEvent) -> npt.NDArray[np.float32] | None:
        """
        Render a backchannel event to audio.

        Uses pre-recorded samples if available, otherwise generates
        a simple tone placeholder.

        Args:
            event: The backchannel event to render.

        Returns:
            Float32 audio array at 24kHz, or None if rendering failed.
        """
        token_key = event.token.replace(" ", "_").replace("?", "").replace("!", "")

        if token_key in self._prerecorded:
            audio = self._prerecorded[token_key].copy()
            audio *= event.volume_scale
            return audio

        audio = self._generate_placeholder(event.token, event.volume_scale)
        return audio

    @staticmethod
    def _generate_placeholder(token: str, volume: float) -> npt.NDArray[np.float32]:
        """
        Generate a short audio placeholder for a backchannel token.

        This is a simple synthesized "hmm" sound used when no pre-recorded
        samples are available.
        """
        sr = 24000
        duration_s = 0.3
        t = np.linspace(0, duration_s, int(sr * duration_s), dtype=np.float32)

        f0 = 180 if "?" in token else 150
        audio = np.sin(2 * np.pi * f0 * t) * 0.3

        # Add harmonics for naturalness
        audio += np.sin(2 * np.pi * f0 * 2 * t) * 0.1
        audio += np.sin(2 * np.pi * f0 * 3 * t) * 0.05

        fade_len = int(sr * 0.05)
        audio[:fade_len] *= np.linspace(0, 1, fade_len)
        audio[-fade_len:] *= np.linspace(1, 0, fade_len)

        audio *= volume
        return audio

    @property
    def session_count(self) -> int:
        """Total backchannels generated this session."""
        return self._session_bc_count
