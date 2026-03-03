"""
Dynamic prosody control for Emily's TTS output.

Prosody parameters (speed, pitch, energy) are computed per-sentence based on:
- Emily's current emotional state
- The semantic content of the text (question, exclamation, statement, list, hesitation)
- Ambient noise floor (whisper mode in quiet environments)
- User's detected emotional state
- Position within a multi-sentence response (emphasis tapers naturally)

Outputs a ProsodyParams object consumed by the TTS engines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ProsodyParams:
    """TTS prosody parameters for a single utterance."""

    speed: float = 1.0
    pitch: float = 1.0
    energy: float = 1.0
    pause_before_ms: int = 0
    pause_after_ms: int = 200


_ABBREV = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Prof|Sr|Jr|vs|etc|e\.g|i\.e|St)\.")
_LIST_PATTERN = re.compile(r"^\s*(?:\d+[.)]|-|\*)\s+")
_PARENTHETICAL = re.compile(r"\(.*?\)")
_EMPHASIS_WORDS = {"very", "really", "extremely", "absolutely", "incredibly"}
_HEDGING_WORDS = {"maybe", "perhaps", "might", "possibly", "somewhat", "kind of"}


class ProsodyController:
    """
    Computes prosody parameters from text content and emotional state.

    Maps semantic and emotional signals to prosody parameters. Tracks
    sentence position within a response for natural emphasis tapering.
    """

    def __init__(self) -> None:
        self._sentence_index = 0

    def reset_position(self) -> None:
        """Reset sentence counter for a new response."""
        self._sentence_index = 0

    def compute(
        self,
        text: str,
        emotional_state: dict[str, float] | None = None,
        whisper_mode: bool = False,
    ) -> ProsodyParams:
        """
        Compute prosody parameters for the given text.

        Args:
            text: The text to be spoken.
            emotional_state: Emily's current emotional state vector.
            whisper_mode: If True, reduces volume and speed.

        Returns:
            ProsodyParams with computed values.
        """
        state = emotional_state or {}
        engagement = state.get("engagement", 0.7)
        confidence = state.get("confidence", 0.8)
        concern = state.get("concern", 0.1)
        enthusiasm = state.get("enthusiasm", 0.6)
        warmth = state.get("warmth", 0.6)

        # --- Base emotional mapping (continuous) ---
        speed = 0.88 + 0.12 * engagement + 0.06 * enthusiasm
        pitch = 1.0 + 0.05 * enthusiasm - 0.03 * concern + 0.02 * warmth
        energy = 0.9 + 0.15 * confidence + 0.08 * engagement
        pause_after_ms = 200
        pause_before_extra = 0

        # --- Emotional threshold modulations ---
        # High enthusiasm (>0.7): speaking rate +10%, pitch variation +15%
        if enthusiasm > 0.7:
            boost = (enthusiasm - 0.7) / 0.3  # 0→1 over threshold range
            speed *= 1.0 + 0.10 * boost
            pitch *= 1.0 + 0.15 * boost

        # Low confidence (<0.4): speaking rate -5%, longer pauses
        if confidence < 0.4:
            deficit = (0.4 - confidence) / 0.4  # 0→1 below threshold
            speed *= 1.0 - 0.05 * deficit
            pause_after_ms += int(150 * deficit)

        # High concern (>0.6): lower pitch, slower pace
        if concern > 0.6:
            level = (concern - 0.6) / 0.4  # 0→1 over threshold
            pitch *= 1.0 - 0.08 * level
            speed *= 1.0 - 0.07 * level

        # High engagement (>0.8): more dynamic intonation range
        if engagement > 0.8:
            dynamic = (engagement - 0.8) / 0.2  # 0→1
            energy *= 1.0 + 0.10 * dynamic

        # Thoughtful pauses when concern > 0.5
        if concern > 0.5:
            pause_before_extra = int(120 * (concern - 0.5) / 0.5)
            pause_after_ms += int(100 * (concern - 0.5) / 0.5)

        stripped = text.strip()
        lower_text = stripped.lower()

        if stripped.endswith("?"):
            pitch *= 1.08
            speed *= 0.93
            pause_after_ms = 350
        elif stripped.endswith("!"):
            energy *= 1.12
            speed *= 1.05
            pause_after_ms = 250
        elif stripped.endswith("...") or stripped.endswith("—") or stripped.endswith("–"):
            speed *= 0.85
            pitch *= 0.97
            pause_after_ms = 500
        elif stripped.endswith(":"):
            speed *= 0.95
            pause_after_ms = 300
        elif _LIST_PATTERN.match(stripped):
            speed *= 0.95
            pause_after_ms = 150

        if _PARENTHETICAL.search(stripped):
            speed *= 0.92
            energy *= 0.9

        words_lower = set(lower_text.split())
        if words_lower & _EMPHASIS_WORDS:
            energy *= 1.08
            pitch *= 1.03
        if words_lower & _HEDGING_WORDS:
            speed *= 0.95
            energy *= 0.92

        if self._sentence_index == 0:
            energy *= 1.05
        elif self._sentence_index > 4:
            taper = max(0.9, 1.0 - (self._sentence_index - 4) * 0.02)
            energy *= taper
            speed *= 1.0 + (1.0 - taper) * 0.5

        self._sentence_index += 1

        speed = max(0.7, min(1.8, speed))
        pitch = max(0.8, min(1.3, pitch))
        energy = max(0.6, min(1.4, energy))

        if whisper_mode:
            energy *= 0.5
            speed *= 0.85

        base_pause_before = 50 if self._sentence_index > 1 else 0
        return ProsodyParams(
            speed=round(speed, 3),
            pitch=round(pitch, 3),
            energy=round(energy, 3),
            pause_before_ms=base_pause_before + pause_before_extra,
            pause_after_ms=pause_after_ms,
        )

    @staticmethod
    def split_into_sentences(text: str) -> list[str]:
        """
        Split text into sentences for per-sentence prosody control.

        Handles common abbreviations, decimal numbers, and ellipses to
        avoid false splits.

        Args:
            text: The full text to split.

        Returns:
            List of sentence strings.
        """
        masked = _ABBREV.sub(lambda m: m.group().replace(".", "\x00"), text)
        masked = re.sub(r"(\d)\.(\d)", lambda m: m.group(1) + "\x00" + m.group(2), masked)
        masked = masked.replace("...", "\x01")

        parts = re.split(r"(?<=[.!?])\s+", masked)

        result = []
        for part in parts:
            restored = part.replace("\x00", ".").replace("\x01", "...")
            cleaned = restored.strip()
            if cleaned:
                result.append(cleaned)

        return result
