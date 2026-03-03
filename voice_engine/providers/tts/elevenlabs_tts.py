"""ElevenLabs TTS provider — premium neural text-to-speech."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from voice_engine.providers.base import TTSProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

ELEVENLABS_SAMPLE_RATE = 24000


class ElevenLabsTTS(TTSProvider):
    """Text-to-speech via the ElevenLabs SDK."""

    def __init__(
        self,
        api_key: str,
        voice: str = "Rachel",
        model_id: str = "eleven_multilingual_v2",
    ) -> None:
        self._api_key = api_key
        self._voice = voice
        self._model_id = model_id
        self._client: object | None = None
        logger.info("ElevenLabsTTS configured: voice=%s model=%s", voice, model_id)

    def _get_client(self) -> object:
        """Lazy-load the async ElevenLabs client."""
        if self._client is None:
            from elevenlabs import AsyncElevenLabs  # type: ignore[import-untyped]

            self._client = AsyncElevenLabs(api_key=self._api_key)
        return self._client

    @staticmethod
    def _pcm_bytes_to_ndarray(pcm_bytes: bytes) -> np.ndarray:
        """Convert raw PCM s16le bytes to a float32 numpy array."""
        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        return audio_int16.astype(np.float32) / 32768.0

    async def synthesize(self, text: str) -> np.ndarray:
        """Synthesize speech and return a float32 audio array."""
        if not text.strip():
            return np.empty(0, dtype=np.float32)

        client = self._get_client()

        try:
            audio_iterator = await client.text_to_speech.convert(  # type: ignore[union-attr]
                voice_id=self._voice,
                text=text,
                model_id=self._model_id,
                output_format="pcm_24000",
            )

            pcm_chunks: list[bytes] = []
            async for chunk in audio_iterator:
                pcm_chunks.append(chunk)

            if not pcm_chunks:
                logger.warning("ElevenLabs produced no audio for: %s", text[:80])
                return np.empty(0, dtype=np.float32)

            pcm_data = b"".join(pcm_chunks)
            audio = self._pcm_bytes_to_ndarray(pcm_data)
            logger.debug("ElevenLabs synthesized %d samples for: %s", len(audio), text[:60])
            return audio
        except Exception:
            logger.exception("ElevenLabs synthesis error")
            raise

    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
    ) -> AsyncIterator[np.ndarray]:
        """Synthesize each incoming text chunk and yield audio arrays."""
        async for text in text_chunks:
            if not text.strip():
                continue
            audio = await self.synthesize(text)
            if len(audio) > 0:
                yield audio
