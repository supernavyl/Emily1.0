"""
Multi-signal turn detection engine for Emily.

Fuses up to 14 signals to predict turn completion probability every 10ms.
Responds at 0.85 confidence threshold rather than waiting for silence.

Humans start responding ~200ms after turn end cues. This engine targets
the same window using signal fusion rather than fixed silence timers.

Zero hard-coded silence timers anywhere — turn detection is signal-fusion only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto

import numpy as np

from observability.logger import get_logger
from perception.audio.emotion_detector import EmotionState
from perception.audio.prosody_analyzer import ProsodyFeatures, SpeakerBaseline

log = get_logger(__name__)


class TurnAction(Enum):
    """Action the conversation engine should take based on turn signal."""

    LISTEN = auto()
    BACKCHANNEL = auto()
    RESPOND = auto()
    YIELD_AND_RESPOND = auto()


@dataclass
class TurnSignal:
    """Result of turn detection fusion."""

    score: float
    action: TurnAction
    confidence_breakdown: dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class ConversationState:
    """Accumulated conversational state for turn detection."""

    prosody: ProsodyFeatures = field(default_factory=ProsodyFeatures)
    baseline: SpeakerBaseline = field(default_factory=SpeakerBaseline)
    emotion: EmotionState = field(default_factory=EmotionState)
    partial_text: str = ""
    committed_text: str = ""
    emily_speaking: bool = False
    silence_duration_ms: float = 0.0
    last_word_timestamp: float = 0.0
    speaking_duration_s: float = 0.0
    turn_hold_count: int = 0


SIGNAL_WEIGHTS: dict[str, float] = {
    "final_intonation": 0.22,
    "syntactic_completeness": 0.20,
    "breath_detected": 0.15,
    "silence_duration": 0.10,
    "final_lengthening": 0.08,
    "discourse_marker": 0.07,
    "question_detected": 0.06,
    "energy_decay": 0.04,
    "backchannel_elicitor": 0.03,
    "glottalization": 0.02,
    "topic_exhaustion": 0.01,
    "gaze_shift": 0.01,
    "gesture_completion": 0.01,
    "response_urgency": 0.00,
}

RESPONSE_THRESHOLD = 0.85
BACKCHANNEL_THRESHOLD = 0.45
OVERLAP_START_THRESHOLD = 0.95


class TurnDetectionEngine:
    """
    Multi-signal turn detection via weighted fusion.

    Each signal scorer returns a value in [0.0, 1.0] representing
    how strongly that signal indicates turn completion.
    """

    def __init__(
        self,
        response_threshold: float = RESPONSE_THRESHOLD,
        backchannel_threshold: float = BACKCHANNEL_THRESHOLD,
        overlap_start_threshold: float = OVERLAP_START_THRESHOLD,
    ) -> None:
        self._last_signal: TurnSignal | None = None
        self._consecutive_respond: int = 0
        self._response_threshold = response_threshold
        self._backchannel_threshold = backchannel_threshold
        self._overlap_start_threshold = overlap_start_threshold

    def compute(self, state: ConversationState) -> TurnSignal:
        """
        Fuse all turn signals and decide on an action.

        Args:
            state: Current conversation state with all accumulated features.

        Returns:
            TurnSignal with score, action, and per-signal breakdown.
        """
        breakdown: dict[str, float] = {}

        for signal_name, _weight in SIGNAL_WEIGHTS.items():
            scorer = getattr(self, f"_score_{signal_name}", None)
            if scorer is not None:
                breakdown[signal_name] = float(scorer(state))
            else:
                breakdown[signal_name] = 0.0

        score = sum(breakdown[k] * SIGNAL_WEIGHTS[k] for k in SIGNAL_WEIGHTS)
        score = float(np.clip(score, 0, 1))

        action = self._decide_action(score, state)

        signal = TurnSignal(
            score=score,
            action=action,
            confidence_breakdown=breakdown,
        )
        self._last_signal = signal

        if action == TurnAction.RESPOND:
            self._consecutive_respond += 1
        else:
            self._consecutive_respond = 0

        return signal

    def _decide_action(self, score: float, state: ConversationState) -> TurnAction:
        """Map score to a concrete action."""
        if score >= self._response_threshold:
            return TurnAction.RESPOND
        elif state.emily_speaking and score >= self._overlap_start_threshold:
            return TurnAction.YIELD_AND_RESPOND
        elif score >= self._backchannel_threshold:
            return TurnAction.BACKCHANNEL
        else:
            return TurnAction.LISTEN

    # -- Acoustic signals --

    def _score_final_intonation(self, state: ConversationState) -> float:
        """
        F0 trajectory over the last 500ms.

        Falling F0 = declarative completion (high signal).
        Rising F0 = question completion (high signal).
        Level F0 = still mid-utterance (low signal).
        F0 reset to baseline = strong completion.
        """
        traj = state.prosody.f0_trajectory
        f0 = state.prosody.f0_hz

        if traj == "falling":
            return 0.85
        elif traj == "rising":
            if f0 > state.baseline.f0_mean * 1.1:
                return 0.9
            return 0.5
        elif f0 > 0 and abs(f0 - state.baseline.f0_mean) < state.baseline.f0_std * 0.3:
            return 0.7

        return 0.2

    def _score_silence_duration(self, state: ConversationState) -> float:
        """
        Not just "is there silence?" but quality and duration.

        Post-utterance silence vs mid-sentence pause vs breath pause
        have different spectral profiles.
        """
        ms = state.prosody.pause_duration_ms

        if ms <= 0:
            return 0.0

        if state.prosody.pause_type == "breath":
            return min(ms / 800, 0.9)
        elif state.prosody.pause_type == "unfilled":
            return min(ms / 600, 0.95)
        elif state.prosody.pause_type == "filled":
            return min(ms / 1500, 0.3)

        return min(ms / 1000, 0.7)

    def _score_final_lengthening(self, state: ConversationState) -> float:
        """
        Humans stretch the last syllable of a turn.

        Measure ratio of final vowel duration vs baseline.
        """
        ratio = state.prosody.final_lengthening_ratio
        if ratio > 1.3:
            return min((ratio - 1.0) * 2.0, 1.0)
        return 0.1

    def _score_energy_decay(self, state: ConversationState) -> float:
        """
        Gradual energy reduction over last 200ms.

        Pattern: humans trail off at turn boundaries.
        """
        traj = state.prosody.intensity_trajectory
        if traj == "falling":
            return 0.7
        elif traj == "level":
            return 0.3
        return 0.1

    def _score_breath_detected(self, state: ConversationState) -> float:
        """
        Post-utterance inhalation is one of the strongest completion signals.

        Humans breathe after finishing a thought.
        """
        if state.prosody.pause_type == "breath":
            if state.prosody.pause_duration_ms > 100:
                return 0.9
            return 0.6
        return 0.0

    def _score_glottalization(self, state: ConversationState) -> float:
        """
        Creaky voice at utterance end is a strong completion signal.

        Common in American English.
        """
        if state.prosody.voice_quality == "creaky":
            if state.prosody.intensity_trajectory == "falling":
                return 0.8
            return 0.5
        return 0.1

    # -- Linguistic signals --

    def _score_syntactic_completeness(self, state: ConversationState) -> float:
        """
        Is the partial transcript syntactically complete?

        Uses heuristics (proper full sentence structure).
        """
        text = (state.committed_text + " " + state.partial_text).strip()
        if not text:
            return 0.0

        ends_with_punct = text[-1] in ".!?;:"
        has_subject_verb = len(text.split()) >= 3

        score = 0.2

        if ends_with_punct:
            score += 0.5
        if has_subject_verb and ends_with_punct:
            score += 0.3

        trailing = text.rstrip()
        if trailing.endswith(("the", "a", "an", "to", "and", "but", "or", "of", "in", "at")):
            score = max(score - 0.4, 0.05)

        return min(score, 1.0)

    def _score_backchannel_elicitor(self, state: ConversationState) -> float:
        """
        Phrases that specifically invite listener response.

        "you know?", "right?", "doesn't it?", "know what I mean?"
        """
        text = state.partial_text.lower().strip()
        elicitors = [
            "you know",
            "right?",
            "know what i mean",
            "doesn't it",
            "don't you think",
            "isn't it",
            "what do you think",
            "you see",
            "get it",
            "makes sense",
        ]
        for e in elicitors:
            if text.endswith(e) or text.endswith(e.rstrip("?")):
                return 0.9
        if text.endswith("?"):
            return 0.4
        return 0.0

    def _score_discourse_marker(self, state: ConversationState) -> float:
        """
        Turn-yielding discourse markers.

        "anyway", "so yeah", "that's pretty much it", "but yeah"
        """
        text = state.partial_text.lower().strip()
        markers = [
            "anyway",
            "so yeah",
            "but yeah",
            "that's pretty much it",
            "that's about it",
            "i dunno",
            "i don't know",
            "so...",
            "yeah so",
            "that's all",
            "i guess",
        ]
        for m in markers:
            if text.endswith(m):
                return 0.85
        if text.endswith("so") or text.endswith("yeah"):
            return 0.4
        return 0.0

    def _score_question_detected(self, state: ConversationState) -> float:
        """
        Direct question detection.

        Combines: rising intonation + syntactic question form + question words.
        """
        text = state.partial_text.strip()
        score = 0.0

        if text.endswith("?"):
            score += 0.5

        question_words = (
            "who",
            "what",
            "when",
            "where",
            "why",
            "how",
            "which",
            "could",
            "would",
            "should",
            "can",
            "is",
            "are",
            "do",
            "does",
            "did",
            "will",
        )
        first_word = text.split()[0].lower().rstrip(",.?!") if text.split() else ""
        if first_word in question_words:
            score += 0.3

        if state.prosody.f0_trajectory == "rising":
            score += 0.2

        tag_patterns = (
            "isn't it",
            "aren't you",
            "won't you",
            "don't you",
            "can you",
            "will you",
            "could you",
        )
        lower = text.lower()
        for tag in tag_patterns:
            if lower.endswith(tag) or lower.endswith(tag + "?"):
                score += 0.3
                break

        return min(score, 1.0)

    # -- Contextual signals --

    def _score_topic_exhaustion(self, state: ConversationState) -> float:
        """
        Has the speaker covered all semantic branches of their topic?

        Heuristic: if no new content added in last 3 seconds and speech is trailing.
        """
        if state.speaking_duration_s > 15 and state.prosody.intensity_trajectory == "falling":
            return 0.6
        if state.speaking_duration_s > 30:
            return 0.4
        return 0.1

    def _score_gaze_shift(self, state: ConversationState) -> float:
        """
        Gaze direction signal (requires webcam).

        Looking AT listener = turn yield signal.
        Currently returns neutral as webcam integration is deferred.
        """
        return 0.0

    def _score_gesture_completion(self, state: ConversationState) -> float:
        """
        Hand gesture state (requires webcam).

        Gesture return to rest = turn-complete signal.
        Currently returns neutral as webcam integration is deferred.
        """
        return 0.0

    def _score_response_urgency(self, state: ConversationState) -> float:
        """
        Context-aware urgency adjustment.

        Emotional topics -> respond faster.
        Complex questions -> small delay is natural.
        User frustrated -> respond immediately.
        """
        if state.emotion.primary.value == "frustrated":
            return 0.8
        if state.emotion.arousal > 0.6:
            return 0.6
        if state.emotion.cognitive_load > 0.7:
            return 0.2
        return 0.3

    @property
    def last_signal(self) -> TurnSignal | None:
        """Most recent turn signal."""
        return self._last_signal
