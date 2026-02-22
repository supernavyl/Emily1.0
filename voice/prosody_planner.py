"""
Full prosody planning for Emily's TTS output.

Maps content, context, and emotional state to detailed prosody parameters.
All prosody assembly happens in this module only (per .cursorrules rule 4).

Rules:
- Questions: rising terminal contour
- Lists: falling-rising on each item, final fall on last
- Emphasis: pitch peak on content words
- Parentheticals: faster, lower, quieter
- Emotional content: wider pitch range
- Technical content: slower, more level
- Closing utterances: final lowering + deceleration
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from observability.logger import get_logger
from conversation.emotion_sync import ResponseStyleParameters

log = get_logger(__name__)


@dataclass
class SentenceProsody:
    """Full prosody parameters for a single sentence."""

    speaking_rate: float = 1.0
    pitch_level_st: float = 0.0
    pitch_range_st: float = 3.0
    energy: float = 1.0
    voice_quality: str = "modal"
    pause_before_ms: int = 0
    pause_after_ms: int = 200
    emphasis_words: list[str] = field(default_factory=list)
    terminal_contour: str = "falling"
    whisper_mode: bool = False


class ProsodyPlanner:
    """
    Plans detailed prosody parameters for each sentence in Emily's response.

    Takes into account sentence content, position in the response,
    emotional style parameters, and rhythm synchronization targets.
    """

    def plan_sentence(
        self,
        sentence: str,
        style: ResponseStyleParameters | None = None,
        position: str = "middle",
        sentence_index: int = 0,
        total_sentences: int = 1,
        whisper_mode: bool = False,
    ) -> SentenceProsody:
        """
        Compute prosody parameters for a sentence.

        Args:
            sentence: The sentence text.
            style: Emotional style parameters from EmotionSynchronizer.
            position: "opening", "middle", or "closing".
            sentence_index: Index in the response (0-based).
            total_sentences: Total sentences in the response.
            whisper_mode: Whether to use whisper register.

        Returns:
            SentenceProsody with all planned parameters.
        """
        style = style or ResponseStyleParameters()
        stripped = sentence.strip()

        rate = style.speaking_rate_modifier
        pitch = 0.0
        pitch_range = 3.0
        energy = style.energy_modifier
        pause_before = 0
        pause_after = 200
        terminal = "falling"
        emphasis = []

        if stripped.endswith("?"):
            terminal = "rising"
            rate *= 0.95
            pitch += 1.0
        elif stripped.endswith("!"):
            energy *= 1.1
            pitch_range *= 1.3
            rate *= 1.03
        elif stripped.endswith("...") or stripped.endswith("—"):
            rate *= 0.9
            pause_after = 400
            terminal = "level"

        if self._is_list(stripped):
            pitch_range *= 1.2
            rate *= 0.95

        if self._is_parenthetical(stripped):
            rate *= 1.1
            pitch -= 1.5
            energy *= 0.85

        if self._is_technical(stripped):
            rate *= 0.9
            pitch_range *= 0.7

        if position == "opening":
            pause_before = 50
            pitch += 0.5
            energy *= 1.05
        elif position == "closing":
            pitch -= 1.0
            rate *= 0.95
            pause_after = 300
            terminal = "falling"

        if sentence_index == 0:
            pause_before = 0

        emphasis = self._find_emphasis_words(stripped)

        pitch_range *= style.pitch_range_modifier

        rate = float(np.clip(rate, 0.7, 1.5))
        pitch = float(np.clip(pitch, -3, 5))
        pitch_range = float(np.clip(pitch_range, 1, 8))
        energy = float(np.clip(energy, 0.5, 1.5))

        return SentenceProsody(
            speaking_rate=rate,
            pitch_level_st=pitch,
            pitch_range_st=pitch_range,
            energy=energy,
            voice_quality="breathy" if whisper_mode else "modal",
            pause_before_ms=pause_before,
            pause_after_ms=pause_after,
            emphasis_words=emphasis,
            terminal_contour=terminal,
            whisper_mode=whisper_mode,
        )

    @staticmethod
    def _is_list(text: str) -> bool:
        """Check if the sentence contains a list."""
        comma_count = text.count(",")
        and_or = " and " in text or " or " in text
        return comma_count >= 2 and and_or

    @staticmethod
    def _is_parenthetical(text: str) -> bool:
        """Check for parenthetical content."""
        return bool(re.search(r"[—–\-]\s.*\s[—–\-]", text) or "(" in text)

    @staticmethod
    def _is_technical(text: str) -> bool:
        """Heuristic for technical content."""
        technical_markers = (
            "function", "method", "class", "API", "algorithm",
            "database", "server", "config", "parameter",
        )
        lower = text.lower()
        return any(m.lower() in lower for m in technical_markers)

    @staticmethod
    def _find_emphasis_words(text: str) -> list[str]:
        """Find words that should receive prosodic emphasis."""
        emphasis = []
        words = text.split()
        emphasis_markers = {
            "very", "really", "absolutely", "definitely",
            "never", "always", "most", "best", "worst",
            "important", "critical", "essential",
        }
        for w in words:
            clean = w.lower().strip(".,!?;:'\"")
            if clean in emphasis_markers:
                emphasis.append(w)
            elif w.isupper() and len(w) > 1:
                emphasis.append(w)
        return emphasis

    def plan_response(
        self,
        sentences: list[str],
        style: ResponseStyleParameters | None = None,
        whisper_mode: bool = False,
    ) -> list[SentenceProsody]:
        """
        Plan prosody for an entire response.

        Args:
            sentences: List of sentences.
            style: Emotional style parameters.
            whisper_mode: Whether to use whisper register.

        Returns:
            List of SentenceProsody, one per sentence.
        """
        total = len(sentences)
        planned = []

        for i, sent in enumerate(sentences):
            if i == 0:
                pos = "opening"
            elif i == total - 1:
                pos = "closing"
            else:
                pos = "middle"

            prosody = self.plan_sentence(
                sentence=sent,
                style=style,
                position=pos,
                sentence_index=i,
                total_sentences=total,
                whisper_mode=whisper_mode,
            )
            planned.append(prosody)

        return planned
