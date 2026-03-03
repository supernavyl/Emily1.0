"""Tiered TTS router — Kokoro for neutral speech, Chatterbox for emotional."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from voice_engine.providers.base import TTSProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import numpy as np

logger = logging.getLogger(__name__)

# Paralinguistic markers that Chatterbox handles natively
_PARALINGUISTIC_RE = re.compile(
    r"\[(?:laughs?|sighs?|gasps?|whispers?|cries|yawns?|groans?|hums?)\]",
    re.IGNORECASE,
)


class TieredTTS(TTSProvider):
    """Routes to a fast TTS (Kokoro) or expressive TTS (Chatterbox) per utterance.

    Routing logic:
    - If any emotional dimension exceeds ``emotion_threshold`` → expressive
    - If text contains paralinguistic markers (``[laughs]``, etc.) → expressive
    - Otherwise → fast
    """

    def __init__(
        self,
        fast: TTSProvider,
        expressive: TTSProvider,
        emotion_threshold: float = 0.6,
    ) -> None:
        self._fast = fast
        self._expressive = expressive
        self._threshold = emotion_threshold
        logger.info(
            "TieredTTS initialised: fast=%s, expressive=%s, threshold=%.2f",
            type(fast).__name__,
            type(expressive).__name__,
            emotion_threshold,
        )

    def set_voice(self, voice: str) -> None:
        """Forward voice switch to both inner providers."""
        self._fast.set_voice(voice)
        self._expressive.set_voice(voice)

    def _should_use_expressive(self, text: str) -> bool:
        """Decide whether to route to the expressive provider."""
        if _PARALINGUISTIC_RE.search(text):
            return True

        try:
            from persona.emotional_state import get_emotional_state

            emo = get_emotional_state().state
            if (
                emo.enthusiasm > self._threshold
                or emo.engagement > self._threshold
                or emo.concern > self._threshold
            ):
                return True
        except Exception:
            pass

        return False

    async def synthesize(self, text: str) -> np.ndarray:
        """Route to the appropriate TTS provider and synthesize."""
        if self._should_use_expressive(text):
            logger.debug("TieredTTS → expressive for: %s", text[:60])
            return await self._expressive.synthesize(text)
        logger.debug("TieredTTS → fast for: %s", text[:60])
        return await self._fast.synthesize(text)

    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
    ) -> AsyncIterator[np.ndarray]:
        """Route each text chunk to the appropriate TTS provider."""
        async for text in text_chunks:
            if not text.strip():
                continue
            audio = await self.synthesize(text)
            if len(audio) > 0:
                yield audio
