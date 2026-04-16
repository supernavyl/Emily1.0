"""Breath injector — inserts natural breath sounds between TTS sentences.

Sits between SentenceCollector and TTS synthesis. Scores sentences for breath
placement via heuristics, splits them into SpeechSegment/BreathSegment lists,
and the pipeline synthesizes speech segments while passing breath audio through.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from observability.logger import get_logger

if TYPE_CHECKING:
    from config import BreathInjectorConfig

logger = get_logger(__name__)

SAMPLE_RATE = 24000

# ── Segment types ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    """A text segment to be synthesized by TTS."""

    text: str


@dataclass(frozen=True, slots=True)
class BreathSegment:
    """A pre-rendered breath or silence audio segment."""

    audio: np.ndarray
    duration_ms: int


AudioSegment = SpeechSegment | BreathSegment

# ── Breath token regex ────────────────────────────────────────────────

_BREATH_TOKEN_RE = re.compile(r"<breath>", re.IGNORECASE)
_PAUSE_TOKEN_RE = re.compile(r"<pause:(\d+)ms>", re.IGNORECASE)

# Duration categories mapped to filename prefixes
_DURATION_CATEGORIES: dict[str, tuple[int, int]] = {
    "short": (80, 150),
    "medium": (150, 350),
    "long": (350, 500),
}

# ── Sample library ────────────────────────────────────────────────────


class BreathSampleLibrary:
    """Loads and serves pre-recorded breath WAV samples."""

    def __init__(self, sample_dir: Path) -> None:
        self._samples: dict[str, list[np.ndarray]] = {
            "short": [],
            "medium": [],
            "long": [],
        }
        self._load(sample_dir)

    def _load(self, sample_dir: Path) -> None:
        if not sample_dir.is_dir():
            logger.warning("breath_sample_dir_missing", path=str(sample_dir))
            return
        from scipy.io import wavfile

        for wav_path in sorted(sample_dir.glob("*.wav")):
            try:
                rate, data = wavfile.read(str(wav_path))
                if data.dtype != np.float32:
                    data = data.astype(np.float32) / 32768.0
                if rate != SAMPLE_RATE:
                    logger.warning("breath_sample_wrong_rate", path=wav_path.name, rate=rate)
                    continue
                name = wav_path.stem.lower()
                if "short" in name:
                    self._samples["short"].append(data)
                elif "long" in name:
                    self._samples["long"].append(data)
                else:
                    self._samples["medium"].append(data)
                logger.debug("breath_sample_loaded", path=wav_path.name, samples=len(data))
            except Exception:
                logger.warning("breath_sample_load_failed", path=wav_path.name, exc_info=True)

        total = sum(len(v) for v in self._samples.values())
        if total > 0:
            logger.info("breath_samples_ready", count=total)

    def has_samples(self) -> bool:
        """Return True if any samples were successfully loaded."""
        return any(len(v) > 0 for v in self._samples.values())

    def pick(self, category: str) -> np.ndarray:
        """Pick a random sample from the given category, falling back to silence."""
        candidates = self._samples.get(category, [])
        if not candidates:
            for samples in self._samples.values():
                if samples:
                    candidates = samples
                    break
        if candidates:
            return random.choice(candidates).copy()
        dur_range = _DURATION_CATEGORIES.get(category, (150, 350))
        dur_ms = random.randint(*dur_range)
        return np.zeros(int(SAMPLE_RATE * dur_ms / 1000), dtype=np.float32)


# ── Heuristic scoring ─────────────────────────────────────────────────


def score_breath(
    prev_sentence_len: int,
    prev_end_char: str,
    cumulative_speech_s: float,
) -> float:
    """Score how strongly a breath is needed before the next sentence.

    Args:
        prev_sentence_len: Character length of the previous sentence.
        prev_end_char: Last punctuation character of the previous sentence.
        cumulative_speech_s: Total seconds of speech produced so far this turn.

    Returns:
        A score in [0, ~1.5] — higher means stronger need for a breath.
    """
    score = prev_sentence_len / 120.0
    if prev_end_char in ("?", "!"):
        score += 0.3
    if cumulative_speech_s > 3.0:
        score += 0.2
    return score


def should_breathe(score: float, density: float) -> bool:
    """Decide whether to insert a breath given the score and density config.

    Args:
        score: Output of score_breath().
        density: User-configured breath density [0.0, 1.0].

    Returns:
        True if a breath should be inserted.
    """
    if density <= 0.0:
        return False
    if density >= 1.0:
        return True
    threshold = 1.0 - density
    return score > threshold


# ── Main injector ─────────────────────────────────────────────────────

_DEFAULT_SAMPLE_DIR = Path("assets/breaths")


class BreathInjector:
    """Splits sentences into speech + breath segments based on heuristics."""

    def __init__(
        self,
        config: BreathInjectorConfig,
        sample_dir: Path | None = None,
    ) -> None:
        self._config = config
        self._library = BreathSampleLibrary(sample_dir or _DEFAULT_SAMPLE_DIR)

    def process(
        self,
        sentence: str,
        prev_sentence_len: int,
        cumulative_speech_s: float,
    ) -> list[AudioSegment]:
        """Split a sentence into speech and breath segments.

        Args:
            sentence: The sentence text to process (may include LLM tokens).
            prev_sentence_len: Character length of the immediately preceding sentence.
                               Pass 0 for the very first sentence in a turn.
            cumulative_speech_s: Total seconds of speech produced before this sentence.

        Returns:
            Ordered list of SpeechSegment and BreathSegment items. The caller
            is responsible for synthesising SpeechSegments via TTS and passing
            BreathSegments through as raw audio.
        """
        if not self._config.enabled:
            return [SpeechSegment(text=sentence)]

        segments: list[AudioSegment] = []

        # 1. Inter-sentence breath (before this sentence)
        if prev_sentence_len > 0:
            score = score_breath(
                prev_sentence_len=prev_sentence_len,
                prev_end_char=".",
                cumulative_speech_s=cumulative_speech_s,
            )
            if self._config.emotional_modulation:
                score = self._apply_emotional_modulation(score)
            if should_breathe(score, self._config.density):
                breath = self._make_inter_sentence_breath(prev_sentence_len)
                segments.append(breath)

        # 2. Process LLM tokens within the sentence
        if self._config.respect_llm_tokens and (
            _BREATH_TOKEN_RE.search(sentence) or _PAUSE_TOKEN_RE.search(sentence)
        ):
            segments.extend(self._split_on_tokens(sentence))
        else:
            segments.append(SpeechSegment(text=sentence))

        return segments

    def _make_inter_sentence_breath(self, prev_len: int) -> BreathSegment:
        """Create a breath segment sized to the previous sentence length."""
        if prev_len > 100:
            category = "long"
        elif prev_len > 50:
            category = "medium"
        else:
            category = "short"
        audio = self._library.pick(category)
        pad = self._make_silence(self._config.min_silence_ms)
        padded = np.concatenate([pad, audio, pad])
        duration_ms = int(len(padded) / SAMPLE_RATE * 1000)
        duration_ms = min(duration_ms, self._config.max_breath_ms)
        max_samples = int(SAMPLE_RATE * self._config.max_breath_ms / 1000)
        if len(padded) > max_samples:
            padded = padded[:max_samples]
            duration_ms = self._config.max_breath_ms
        return BreathSegment(audio=padded, duration_ms=duration_ms)

    def _split_on_tokens(self, sentence: str) -> list[AudioSegment]:
        """Split sentence on <breath> and <pause:Nms> tokens."""
        segments: list[AudioSegment] = []
        combined_re = re.compile(r"(<breath>|<pause:\d+ms>)", re.IGNORECASE)
        parts = combined_re.split(sentence)

        for part in parts:
            if not part:
                continue
            if _BREATH_TOKEN_RE.fullmatch(part):
                audio = self._library.pick("medium")
                pad = self._make_silence(self._config.min_silence_ms)
                padded = np.concatenate([pad, audio, pad])
                segments.append(
                    BreathSegment(
                        audio=padded,
                        duration_ms=int(len(padded) / SAMPLE_RATE * 1000),
                    )
                )
            elif m := _PAUSE_TOKEN_RE.fullmatch(part):
                dur_ms = int(m.group(1))
                silence = self._make_silence(dur_ms)
                segments.append(BreathSegment(audio=silence, duration_ms=dur_ms))
            else:
                text = part.strip()
                if text:
                    segments.append(SpeechSegment(text=text))

        return segments

    def _apply_emotional_modulation(self, score: float) -> float:
        """Adjust breath score based on emotional state."""
        try:
            from persona.emotional_state import get_emotional_state

            emo = get_emotional_state().state
            arousal = (emo.enthusiasm + emo.engagement) / 2.0
            modulator = 1.0 + (0.5 - arousal) * 0.4
            return score * modulator
        except Exception:
            return score

    @staticmethod
    def _make_silence(duration_ms: int) -> np.ndarray:
        """Generate a silence array of the given duration."""
        return np.zeros(int(SAMPLE_RATE * duration_ms / 1000), dtype=np.float32)
