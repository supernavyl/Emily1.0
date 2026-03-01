"""
Speech emotion recognition for Emily.

Detects user emotional state from prosodic features and lexical content.
Maps to a 10-category emotion model with continuous valence/arousal dimensions.

Feeds: conversation emotion sync, response style adaptation, rhythm tracker.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

from observability.logger import get_logger

if TYPE_CHECKING:
    from perception.audio.prosody_analyzer import ProsodyFeatures, SpeakerBaseline

log = get_logger(__name__)


class UserEmotion(Enum):
    """Detectable emotion categories."""

    NEUTRAL = "neutral"
    HAPPY = "happy"
    EXCITED = "excited"
    ANXIOUS = "anxious"
    FRUSTRATED = "frustrated"
    SAD = "sad"
    CONFUSED = "confused"
    CURIOUS = "curious"
    BORED = "bored"
    TIRED = "tired"


@dataclass
class EmotionState:
    """Complete emotional state of a speaker."""

    primary: UserEmotion = UserEmotion.NEUTRAL
    confidence: float = 0.5
    valence: float = 0.0
    arousal: float = 0.0
    cognitive_load: float = 0.3
    engagement: float = 0.5
    timestamp: float = field(default_factory=time.monotonic)


# Emotion profiles: (f0_delta, energy_delta, rate_delta, quality_hint)
# Deltas are relative to speaker baseline
_EMOTION_PROFILES: dict[UserEmotion, dict[str, tuple[float, float]]] = {
    UserEmotion.NEUTRAL: {"f0": (-0.1, 0.1), "energy": (-0.1, 0.1), "rate": (-0.1, 0.1)},
    UserEmotion.HAPPY: {"f0": (0.05, 0.3), "energy": (0.05, 0.3), "rate": (0.0, 0.2)},
    UserEmotion.EXCITED: {"f0": (0.15, 0.5), "energy": (0.2, 0.5), "rate": (0.1, 0.4)},
    UserEmotion.ANXIOUS: {"f0": (0.05, 0.25), "energy": (-0.1, 0.1), "rate": (0.1, 0.3)},
    UserEmotion.FRUSTRATED: {"f0": (-0.1, 0.2), "energy": (0.15, 0.4), "rate": (0.0, 0.2)},
    UserEmotion.SAD: {"f0": (-0.3, -0.05), "energy": (-0.3, -0.1), "rate": (-0.3, -0.05)},
    UserEmotion.CONFUSED: {"f0": (0.0, 0.2), "energy": (-0.1, 0.1), "rate": (-0.2, 0.0)},
    UserEmotion.CURIOUS: {"f0": (0.1, 0.3), "energy": (0.0, 0.15), "rate": (-0.05, 0.1)},
    UserEmotion.BORED: {"f0": (-0.2, 0.0), "energy": (-0.2, -0.05), "rate": (-0.1, 0.05)},
    UserEmotion.TIRED: {"f0": (-0.25, -0.05), "energy": (-0.3, -0.1), "rate": (-0.3, -0.1)},
}

_VALENCE_MAP = {
    UserEmotion.NEUTRAL: 0.0,
    UserEmotion.HAPPY: 0.7,
    UserEmotion.EXCITED: 0.8,
    UserEmotion.ANXIOUS: -0.4,
    UserEmotion.FRUSTRATED: -0.6,
    UserEmotion.SAD: -0.7,
    UserEmotion.CONFUSED: -0.2,
    UserEmotion.CURIOUS: 0.3,
    UserEmotion.BORED: -0.3,
    UserEmotion.TIRED: -0.2,
}

_AROUSAL_MAP = {
    UserEmotion.NEUTRAL: 0.0,
    UserEmotion.HAPPY: 0.5,
    UserEmotion.EXCITED: 0.9,
    UserEmotion.ANXIOUS: 0.6,
    UserEmotion.FRUSTRATED: 0.7,
    UserEmotion.SAD: -0.5,
    UserEmotion.CONFUSED: 0.2,
    UserEmotion.CURIOUS: 0.4,
    UserEmotion.BORED: -0.6,
    UserEmotion.TIRED: -0.7,
}


class EmotionDetector:
    """
    Prosody-based emotion classification with per-speaker adaptation.

    Compares current prosodic features against speaker baselines to
    detect deviations that indicate emotional state changes.
    """

    _HISTORY_SIZE = 30
    _SMOOTHING_ALPHA = 0.15

    def __init__(self) -> None:
        self._history: deque[EmotionState] = deque(maxlen=self._HISTORY_SIZE)
        self._current: EmotionState = EmotionState()

    def detect(
        self,
        prosody: ProsodyFeatures,
        baseline: SpeakerBaseline,
        partial_text: str = "",
    ) -> EmotionState:
        """
        Detect emotion from prosodic features and optional text.

        Args:
            prosody: Current prosody features.
            baseline: Speaker's prosodic baseline.
            partial_text: Partial transcript for lexical cues.

        Returns:
            EmotionState with primary emotion, confidence, and dimensions.
        """
        f0_delta = self._compute_delta(prosody.f0_hz, baseline.f0_mean, baseline.f0_std)
        energy_delta = self._compute_delta(prosody.intensity_db, baseline.intensity_mean, 10.0)
        rate_delta = self._compute_delta(prosody.speaking_rate_syl_s, baseline.rate_mean, 1.5)

        scores: dict[UserEmotion, float] = {}
        for emotion, profile in _EMOTION_PROFILES.items():
            score = 0.0
            for feat, (low, high) in profile.items():
                if feat == "f0":
                    delta = f0_delta
                elif feat == "energy":
                    delta = energy_delta
                else:
                    delta = rate_delta

                if low <= delta <= high:
                    mid = (low + high) / 2
                    span = (high - low) / 2 + 1e-6
                    score += 1.0 - abs(delta - mid) / span
                else:
                    dist = min(abs(delta - low), abs(delta - high))
                    score -= dist * 0.5

            scores[emotion] = score

        if prosody.voice_quality == "creaky":
            scores[UserEmotion.TIRED] = scores.get(UserEmotion.TIRED, 0) + 0.3
            scores[UserEmotion.BORED] = scores.get(UserEmotion.BORED, 0) + 0.2

        if prosody.f0_trajectory == "rising":
            scores[UserEmotion.CURIOUS] = scores.get(UserEmotion.CURIOUS, 0) + 0.2
            scores[UserEmotion.EXCITED] = scores.get(UserEmotion.EXCITED, 0) + 0.1

        lexical_boost = self._lexical_cues(partial_text)
        for emotion, boost in lexical_boost.items():
            scores[emotion] = scores.get(emotion, 0) + boost

        best = max(scores, key=lambda e: scores[e])
        best_score = scores[best]
        total = sum(max(0, s) for s in scores.values()) + 1e-10
        confidence = max(0, best_score) / total

        cognitive_load = self._estimate_cognitive_load(prosody, baseline)

        new_state = EmotionState(
            primary=best,
            confidence=float(np.clip(confidence, 0, 1)),
            valence=_VALENCE_MAP[best] * confidence,
            arousal=_AROUSAL_MAP[best] * confidence,
            cognitive_load=cognitive_load,
            engagement=self._estimate_engagement(prosody, baseline),
        )

        self._current = self._smooth(self._current, new_state)
        self._history.append(self._current)
        return self._current

    def _compute_delta(self, current: float, baseline_mean: float, baseline_std: float) -> float:
        """Compute normalized deviation from baseline."""
        if baseline_std < 1e-6:
            return 0.0
        return (current - baseline_mean) / max(baseline_std, 1e-6)

    def _lexical_cues(self, text: str) -> dict[UserEmotion, float]:
        """Extract emotion boosts from text content."""
        boosts: dict[UserEmotion, float] = {}
        lower = text.lower()

        positive_words = {"great", "awesome", "love", "wonderful", "fantastic", "excited", "happy"}
        negative_words = {"terrible", "awful", "hate", "frustrated", "annoyed", "angry"}
        confused_words = {"confused", "don't understand", "what do you mean", "huh"}
        curious_words = {"interesting", "curious", "wonder", "how does", "why does"}

        for w in positive_words:
            if w in lower:
                boosts[UserEmotion.HAPPY] = boosts.get(UserEmotion.HAPPY, 0) + 0.3
        for w in negative_words:
            if w in lower:
                boosts[UserEmotion.FRUSTRATED] = boosts.get(UserEmotion.FRUSTRATED, 0) + 0.3
        for w in confused_words:
            if w in lower:
                boosts[UserEmotion.CONFUSED] = boosts.get(UserEmotion.CONFUSED, 0) + 0.3
        for w in curious_words:
            if w in lower:
                boosts[UserEmotion.CURIOUS] = boosts.get(UserEmotion.CURIOUS, 0) + 0.3

        return boosts

    def _estimate_cognitive_load(
        self, prosody: ProsodyFeatures, baseline: SpeakerBaseline
    ) -> float:
        """
        Estimate cognitive load from prosodic cues.

        High cognitive load indicators: slower speech, more pauses, lower F0 range.
        """
        load = 0.3

        if prosody.speaking_rate_syl_s < baseline.rate_mean * 0.8:
            load += 0.2
        if prosody.pause_type == "filled":
            load += 0.15
        if prosody.f0_range_semitones < 3:
            load += 0.1

        return float(np.clip(load, 0, 1))

    def _estimate_engagement(self, prosody: ProsodyFeatures, baseline: SpeakerBaseline) -> float:
        """
        Estimate user engagement level.

        High engagement: wider pitch range, higher energy, active response patterns.
        """
        engagement = 0.5

        if prosody.f0_range_semitones > 6:
            engagement += 0.2
        if prosody.intensity_db > baseline.intensity_mean + 5:
            engagement += 0.15
        if prosody.speaking_rate_syl_s > baseline.rate_mean * 1.1:
            engagement += 0.1

        if prosody.voice_quality == "creaky":
            engagement -= 0.1
        if prosody.pause_duration_ms > 2000:
            engagement -= 0.2

        return float(np.clip(engagement, 0, 1))

    def _smooth(self, prev: EmotionState, new: EmotionState) -> EmotionState:
        """Apply EMA smoothing to prevent emotion flickering."""
        a = self._SMOOTHING_ALPHA
        return EmotionState(
            primary=new.primary if new.confidence > prev.confidence * 0.8 else prev.primary,
            confidence=(1 - a) * prev.confidence + a * new.confidence,
            valence=(1 - a) * prev.valence + a * new.valence,
            arousal=(1 - a) * prev.arousal + a * new.arousal,
            cognitive_load=(1 - a) * prev.cognitive_load + a * new.cognitive_load,
            engagement=(1 - a) * prev.engagement + a * new.engagement,
        )

    @property
    def current(self) -> EmotionState:
        """Current smoothed emotion state."""
        return self._current

    @property
    def emotion_trend(self) -> str:
        """General emotion trajectory over recent history."""
        if len(self._history) < 5:
            return "stable"
        recent_valence = [s.valence for s in list(self._history)[-10:]]
        trend = np.polyfit(range(len(recent_valence)), recent_valence, 1)[0]
        if trend > 0.05:
            return "improving"
        elif trend < -0.05:
            return "declining"
        return "stable"
