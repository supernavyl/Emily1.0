"""
Emotional synchronization engine for Emily.

Adapts Emily's emotional expression to match the user's detected state.

Rules:
- Mirror positive emotions (user excited → Emily warmer)
- Calm negative emotions (user anxious → Emily steadier)
- Never amplify negative emotions (user angry → Emily stays calm)
- Match energy level within ±20%
- Adapt vocabulary complexity to cognitive load
- Adapt sentence length to user's state
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from observability.logger import get_logger
from perception.audio.emotion_detector import EmotionState, UserEmotion

log = get_logger(__name__)


@dataclass
class ResponseStyleParameters:
    """Style parameters that drive TTS prosody and LLM generation."""

    speaking_rate_modifier: float = 1.0
    pitch_range_modifier: float = 1.0
    energy_modifier: float = 1.0
    warmth_level: float = 0.7
    pause_frequency: float = 0.5
    sentence_length_target: int = 12
    vocabulary_complexity: float = 0.6


_STYLE_RULES: dict[UserEmotion, dict[str, float]] = {
    UserEmotion.NEUTRAL: {
        "rate_mod": 1.0,
        "pitch_mod": 1.0,
        "energy_mod": 1.0,
        "warmth": 0.7,
        "pause_freq": 0.5,
        "sent_len": 12,
        "vocab": 0.6,
    },
    UserEmotion.HAPPY: {
        "rate_mod": 1.05,
        "pitch_mod": 1.15,
        "energy_mod": 1.1,
        "warmth": 0.85,
        "pause_freq": 0.4,
        "sent_len": 14,
        "vocab": 0.6,
    },
    UserEmotion.EXCITED: {
        "rate_mod": 1.1,
        "pitch_mod": 1.2,
        "energy_mod": 1.15,
        "warmth": 0.9,
        "pause_freq": 0.3,
        "sent_len": 10,
        "vocab": 0.5,
    },
    UserEmotion.ANXIOUS: {
        "rate_mod": 0.9,
        "pitch_mod": 0.9,
        "energy_mod": 0.85,
        "warmth": 0.85,
        "pause_freq": 0.6,
        "sent_len": 8,
        "vocab": 0.4,
    },
    UserEmotion.FRUSTRATED: {
        "rate_mod": 0.95,
        "pitch_mod": 0.95,
        "energy_mod": 0.9,
        "warmth": 0.8,
        "pause_freq": 0.5,
        "sent_len": 8,
        "vocab": 0.4,
    },
    UserEmotion.SAD: {
        "rate_mod": 0.85,
        "pitch_mod": 0.85,
        "energy_mod": 0.8,
        "warmth": 0.9,
        "pause_freq": 0.7,
        "sent_len": 8,
        "vocab": 0.4,
    },
    UserEmotion.CONFUSED: {
        "rate_mod": 0.9,
        "pitch_mod": 1.0,
        "energy_mod": 0.95,
        "warmth": 0.8,
        "pause_freq": 0.6,
        "sent_len": 8,
        "vocab": 0.3,
    },
    UserEmotion.CURIOUS: {
        "rate_mod": 1.0,
        "pitch_mod": 1.1,
        "energy_mod": 1.05,
        "warmth": 0.8,
        "pause_freq": 0.5,
        "sent_len": 12,
        "vocab": 0.7,
    },
    UserEmotion.BORED: {
        "rate_mod": 1.05,
        "pitch_mod": 1.1,
        "energy_mod": 1.1,
        "warmth": 0.85,
        "pause_freq": 0.4,
        "sent_len": 8,
        "vocab": 0.5,
    },
    UserEmotion.TIRED: {
        "rate_mod": 0.85,
        "pitch_mod": 0.9,
        "energy_mod": 0.8,
        "warmth": 0.9,
        "pause_freq": 0.6,
        "sent_len": 6,
        "vocab": 0.3,
    },
}


class EmotionSynchronizer:
    """
    Maps detected user emotion to Emily's response style parameters.

    Applies the mirror/calm/never-amplify rules to produce natural
    emotional adaptation.
    """

    _SMOOTHING_ALPHA = 0.2

    def __init__(self) -> None:
        self._current_style = ResponseStyleParameters()
        self._emotion_history: deque[UserEmotion] = deque(maxlen=100)

    def compute_response_style(
        self,
        user_emotion: EmotionState,
        topic_context: str = "",
    ) -> ResponseStyleParameters:
        """
        Compute Emily's response style based on user emotion.

        Args:
            user_emotion: Detected user emotional state.
            topic_context: Optional topic for fine-tuning.

        Returns:
            ResponseStyleParameters for TTS and LLM.
        """
        emotion = user_emotion.primary
        confidence = user_emotion.confidence
        rules = _STYLE_RULES.get(emotion, _STYLE_RULES[UserEmotion.NEUTRAL])

        scaled_rules: dict[str, float] = {}
        neutral = _STYLE_RULES[UserEmotion.NEUTRAL]
        for key, val in rules.items():
            neutral_val = neutral[key]
            scaled_rules[key] = neutral_val + (val - neutral_val) * confidence

        new_style = ResponseStyleParameters(
            speaking_rate_modifier=float(scaled_rules["rate_mod"]),
            pitch_range_modifier=float(scaled_rules["pitch_mod"]),
            energy_modifier=float(scaled_rules["energy_mod"]),
            warmth_level=float(scaled_rules["warmth"]),
            pause_frequency=float(scaled_rules["pause_freq"]),
            sentence_length_target=int(scaled_rules["sent_len"]),
            vocabulary_complexity=float(scaled_rules["vocab"]),
        )

        if user_emotion.cognitive_load > 0.6:
            new_style.speaking_rate_modifier *= 0.9
            new_style.sentence_length_target = min(new_style.sentence_length_target, 8)
            new_style.vocabulary_complexity *= 0.8

        self._current_style = self._smooth_style(self._current_style, new_style)
        self._emotion_history.append(emotion)

        return self._current_style

    def _smooth_style(
        self,
        prev: ResponseStyleParameters,
        new: ResponseStyleParameters,
    ) -> ResponseStyleParameters:
        """EMA smoothing to prevent jarring style jumps."""
        a = self._SMOOTHING_ALPHA
        b = 1 - a
        return ResponseStyleParameters(
            speaking_rate_modifier=b * prev.speaking_rate_modifier + a * new.speaking_rate_modifier,
            pitch_range_modifier=b * prev.pitch_range_modifier + a * new.pitch_range_modifier,
            energy_modifier=b * prev.energy_modifier + a * new.energy_modifier,
            warmth_level=b * prev.warmth_level + a * new.warmth_level,
            pause_frequency=b * prev.pause_frequency + a * new.pause_frequency,
            sentence_length_target=int(
                b * prev.sentence_length_target + a * new.sentence_length_target,
            ),
            vocabulary_complexity=b * prev.vocabulary_complexity + a * new.vocabulary_complexity,
        )

    def get_llm_style_instructions(self, style: ResponseStyleParameters) -> str:
        """
        Generate natural language style instructions for the LLM.

        Args:
            style: Current response style parameters.

        Returns:
            Instructions to include in the LLM prompt.
        """
        instructions: list[str] = []

        if style.warmth_level > 0.8:
            instructions.append("Be warm and empathetic in your response.")
        if style.sentence_length_target < 8:
            instructions.append("Keep sentences short and direct.")
        elif style.sentence_length_target > 12:
            instructions.append("You can use longer, more detailed sentences.")
        if style.vocabulary_complexity < 0.4:
            instructions.append("Use simple, clear language.")
        if style.pause_frequency > 0.6:
            instructions.append("Use natural pauses between thoughts.")
        if style.energy_modifier > 1.1:
            instructions.append("Be enthusiastic and engaged.")
        elif style.energy_modifier < 0.85:
            instructions.append("Be calm and steady in your delivery.")

        return " ".join(instructions) if instructions else ""

    @property
    def current_style(self) -> ResponseStyleParameters:
        """Current smoothed response style."""
        return self._current_style

    @property
    def dominant_emotion_trend(self) -> str:
        """The most common user emotion in recent history."""
        if not self._emotion_history:
            return "neutral"
        from collections import Counter

        recent = list(self._emotion_history)[-20:]
        most_common = Counter(recent).most_common(1)
        return most_common[0][0].value if most_common else "neutral"
