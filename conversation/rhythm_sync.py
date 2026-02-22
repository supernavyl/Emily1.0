"""
Rhythm synchronization / entrainment engine for Emily.

Tracks the user's speech rhythm patterns and makes Emily's speech
subtly synchronize with them. This creates unconscious rapport.

Research basis: Communication Accommodation Theory — speakers who
entrain are perceived as more likable, trustworthy, and intelligent.

Synchronizes: speaking rate, pause durations, prosodic phrase length,
inter-turn gap, breathing rhythm.

Entrainment degree: 0.0 (no sync) to 1.0 (full mirror). Default: 0.4.
Cross-session memory stores per-user rhythm profiles.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

import numpy as np

from observability.logger import get_logger
from perception.audio.prosody_analyzer import ProsodyFeatures

log = get_logger(__name__)


@dataclass
class RhythmProfile:
    """A user's conversational rhythm characteristics."""

    speaking_rate_syl_s: float = 4.0
    pause_duration_ms: float = 300.0
    phrase_length_words: int = 8
    response_latency_ms: float = 350.0
    breath_interval_s: float = 20.0
    n_samples: int = 0
    last_updated: float = field(default_factory=time.monotonic)


@dataclass
class RhythmTargets:
    """Target rhythm parameters for Emily's next utterance."""

    speaking_rate_syl_s: float = 4.0
    pause_duration_ms: float = 300.0
    phrase_length_words: int = 8
    response_latency_ms: float = 350.0
    breath_interval_s: float = 20.0


class RhythmSynchronizer:
    """
    Tracks user rhythm and generates Emily's speech timing targets.

    The entrainment degree controls how strongly Emily mirrors the user.
    At 0.4, synchronization is noticeable but not uncanny.
    """

    _WINDOW_S = 60
    _EMA_ALPHA = 0.05

    def __init__(self, entrainment_degree: float = 0.4) -> None:
        """
        Args:
            entrainment_degree: How strongly to mirror the user (0.0-1.0).
        """
        self._degree = np.clip(entrainment_degree, 0.0, 1.0)
        self._user_profile = RhythmProfile()
        self._emily_baseline = RhythmProfile(
            speaking_rate_syl_s=4.2,
            pause_duration_ms=250.0,
            phrase_length_words=10,
            response_latency_ms=300.0,
        )
        self._rate_history: deque[float] = deque(maxlen=100)
        self._pause_history: deque[float] = deque(maxlen=100)
        self._response_gap_history: deque[float] = deque(maxlen=50)

    def update_from_prosody(self, prosody: ProsodyFeatures) -> None:
        """
        Update the user's rhythm profile from new prosody data.

        Args:
            prosody: Current prosody features from the user.
        """
        if prosody.speaking_rate_syl_s > 0:
            self._rate_history.append(prosody.speaking_rate_syl_s)
            self._user_profile.speaking_rate_syl_s = (
                (1 - self._EMA_ALPHA) * self._user_profile.speaking_rate_syl_s
                + self._EMA_ALPHA * prosody.speaking_rate_syl_s
            )

        if prosody.pause_duration_ms > 50:
            self._pause_history.append(prosody.pause_duration_ms)
            self._user_profile.pause_duration_ms = (
                (1 - self._EMA_ALPHA) * self._user_profile.pause_duration_ms
                + self._EMA_ALPHA * prosody.pause_duration_ms
            )

        self._user_profile.n_samples += 1
        self._user_profile.last_updated = time.monotonic()

    def record_response_gap(self, gap_ms: float) -> None:
        """
        Record the time gap between user's turn end and Emily's response start.

        Args:
            gap_ms: Inter-turn gap in milliseconds.
        """
        self._response_gap_history.append(gap_ms)
        self._user_profile.response_latency_ms = (
            (1 - self._EMA_ALPHA) * self._user_profile.response_latency_ms
            + self._EMA_ALPHA * gap_ms
        )

    def get_targets(self) -> RhythmTargets:
        """
        Compute target rhythm parameters for Emily's next utterance.

        Blends Emily's baseline with the user's profile based on
        the entrainment degree.

        Returns:
            RhythmTargets for TTS and response timing.
        """
        d = self._degree
        user = self._user_profile
        base = self._emily_baseline

        rate = base.speaking_rate_syl_s * (1 - d) + user.speaking_rate_syl_s * d
        rate = float(np.clip(rate, 2.0, 7.0))

        pause = base.pause_duration_ms * (1 - d) + user.pause_duration_ms * d
        pause = float(np.clip(pause, 100, 800))

        phrase = int(base.phrase_length_words * (1 - d) + user.phrase_length_words * d)
        phrase = max(4, min(20, phrase))

        latency = base.response_latency_ms * (1 - d) + user.response_latency_ms * d
        latency = float(np.clip(latency, 100, 700))

        breath = base.breath_interval_s * (1 - d) + user.breath_interval_s * d
        breath = float(np.clip(breath, 10.0, 30.0))

        return RhythmTargets(
            speaking_rate_syl_s=rate,
            pause_duration_ms=pause,
            phrase_length_words=phrase,
            response_latency_ms=latency,
            breath_interval_s=breath,
        )

    def get_target_speaking_rate(self) -> float:
        """Convenience: target syllables/second for Emily's next utterance."""
        return self.get_targets().speaking_rate_syl_s

    def get_target_response_latency_ms(self) -> float:
        """Convenience: ideal inter-turn gap in ms."""
        return self.get_targets().response_latency_ms

    def get_target_pause_duration(self) -> float:
        """Convenience: target pause duration in ms."""
        return self.get_targets().pause_duration_ms

    def get_target_phrase_length(self) -> int:
        """Convenience: target words per phrase."""
        return self.get_targets().phrase_length_words

    def export_profile(self) -> dict:
        """
        Export the user's rhythm profile for cross-session storage.

        Returns:
            Dict serializable for episodic memory.
        """
        p = self._user_profile
        return {
            "speaking_rate_syl_s": p.speaking_rate_syl_s,
            "pause_duration_ms": p.pause_duration_ms,
            "phrase_length_words": p.phrase_length_words,
            "response_latency_ms": p.response_latency_ms,
            "breath_interval_s": p.breath_interval_s,
            "n_samples": p.n_samples,
        }

    def import_profile(self, data: dict) -> None:
        """
        Import a previously stored rhythm profile.

        Args:
            data: Dict from export_profile().
        """
        self._user_profile = RhythmProfile(
            speaking_rate_syl_s=data.get("speaking_rate_syl_s", 4.0),
            pause_duration_ms=data.get("pause_duration_ms", 300.0),
            phrase_length_words=data.get("phrase_length_words", 8),
            response_latency_ms=data.get("response_latency_ms", 350.0),
            breath_interval_s=data.get("breath_interval_s", 20.0),
            n_samples=data.get("n_samples", 0),
        )
        log.info("rhythm_profile_imported", samples=self._user_profile.n_samples)

    @property
    def user_profile(self) -> RhythmProfile:
        """Current user rhythm profile."""
        return self._user_profile

    @property
    def entrainment_degree(self) -> float:
        """Current entrainment strength."""
        return self._degree

    @entrainment_degree.setter
    def entrainment_degree(self, value: float) -> None:
        """Set the entrainment degree (0.0-1.0)."""
        self._degree = float(np.clip(value, 0.0, 1.0))
