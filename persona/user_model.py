"""
User emotional modeling and interaction style adaptation.

Emily adapts her communication style based on detected emotional signals:
- Speech analysis: pace, filler words, tone (from STT word timestamps)
- Text analysis: sentiment, punctuation patterns
- Vision: facial expression via DeepFace (optional)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


class UserMood(Enum):
    NEUTRAL = auto()
    ENGAGED = auto()
    STRESSED = auto()
    FRUSTRATED = auto()
    TIRED = auto()
    FOCUSED = auto()
    HAPPY = auto()


@dataclass
class UserEmotionalState:
    """Detected emotional state of the user."""

    mood: UserMood = UserMood.NEUTRAL
    confidence: float = 0.5
    timestamp: float = field(default_factory=time.time)
    signals: dict[str, Any] = field(default_factory=dict)


_ADAPTATION_MAP: dict[UserMood, dict[str, Any]] = {
    UserMood.STRESSED: {
        "response_style": "concise and clear",
        "avoid": "lengthy explanations",
        "tts_speed": 0.9,
        "prosody_energy": 0.8,
    },
    UserMood.FRUSTRATED: {
        "response_style": "patient and empathetic",
        "avoid": "complex jargon",
        "tts_speed": 0.85,
        "prosody_energy": 0.75,
    },
    UserMood.TIRED: {
        "response_style": "brief and supportive",
        "avoid": "demanding tasks",
        "tts_speed": 0.85,
        "prosody_energy": 0.7,
    },
    UserMood.FOCUSED: {
        "response_style": "technical and direct",
        "avoid": "small talk",
        "tts_speed": 1.05,
        "prosody_energy": 0.95,
    },
    UserMood.ENGAGED: {
        "response_style": "detailed and exploratory",
        "avoid": "nothing",
        "tts_speed": 1.0,
        "prosody_energy": 1.0,
    },
}


class UserModelingEngine:
    """
    Infers user emotional state from available signals and provides
    style adaptation guidance to the ConversationAgent.
    """

    _FILLER_WORDS = {"um", "uh", "er", "hmm", "like", "you know", "kind of", "sort of"}

    def __init__(self) -> None:
        self._current_state = UserEmotionalState()
        self._history: list[UserEmotionalState] = []

    def analyze_speech(
        self,
        text: str,
        word_timestamps: list[dict[str, Any]] | None = None,
    ) -> UserEmotionalState:
        """
        Infer user mood from speech text and optional word timestamps.

        Args:
            text: Transcript text.
            word_timestamps: Optional list of {word, start, end, probability} dicts.

        Returns:
            Updated UserEmotionalState.
        """
        signals: dict[str, Any] = {}
        words = text.lower().split()

        # Filler word frequency
        filler_count = sum(1 for w in words if w in self._FILLER_WORDS)
        filler_ratio = filler_count / max(len(words), 1)
        signals["filler_ratio"] = filler_ratio

        # Speech pace (from timestamps)
        if word_timestamps and len(word_timestamps) >= 2:
            duration = word_timestamps[-1].get("end", 0) - word_timestamps[0].get("start", 0)
            pace_wpm = (len(word_timestamps) / max(duration, 0.1)) * 60
            signals["pace_wpm"] = pace_wpm
        else:
            pace_wpm = 120  # Default assumed pace

        # Simple sentiment signals
        negative_words = {
            "angry",
            "frustrated",
            "annoyed",
            "confused",
            "wrong",
            "bad",
            "hate",
            "stupid",
        }
        positive_words = {"great", "thanks", "perfect", "excellent", "love", "amazing"}
        neg_count = sum(1 for w in words if w in negative_words)
        pos_count = sum(1 for w in words if w in positive_words)
        signals["negative_words"] = neg_count
        signals["positive_words"] = pos_count

        # Determine mood
        mood, confidence = self._classify_mood(
            filler_ratio, pace_wpm, neg_count, pos_count, signals
        )

        state = UserEmotionalState(mood=mood, confidence=confidence, signals=signals)
        self._current_state = state
        self._history.append(state)
        return state

    def _classify_mood(
        self,
        filler_ratio: float,
        pace_wpm: float,
        neg_count: int,
        pos_count: int,
        signals: dict[str, Any],
    ) -> tuple[UserMood, float]:
        """Rule-based mood classification."""
        if neg_count >= 2:
            return UserMood.FRUSTRATED, 0.7
        if filler_ratio > 0.15 and pace_wpm < 100:
            return UserMood.TIRED, 0.6
        if filler_ratio > 0.1:
            return UserMood.STRESSED, 0.55
        if pace_wpm > 160 and pos_count > 0:
            return UserMood.ENGAGED, 0.65
        if pos_count >= 2:
            return UserMood.HAPPY, 0.7
        return UserMood.NEUTRAL, 0.5

    def get_style_adaptation(self) -> dict[str, Any]:
        """
        Return communication style adaptation based on current user mood.

        Returns:
            Dict with style guidance for the ConversationAgent.
        """
        return _ADAPTATION_MAP.get(self._current_state.mood, {})

    @property
    def current_state(self) -> UserEmotionalState:
        """Current detected user emotional state."""
        return self._current_state
