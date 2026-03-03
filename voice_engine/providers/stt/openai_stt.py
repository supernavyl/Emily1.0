"""OpenAI Whisper API STT provider."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING

import numpy as np

from voice_engine.providers.base import STTProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class OpenAISTT(STTProvider):
    """Transcription via the OpenAI Whisper API (``whisper-1``)."""

    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        self._api_key = api_key
        self._model = model
        self._client: object | None = None
        logger.info("OpenAISTT configured: model=%s", model)

    def _get_client(self) -> object:
        """Lazy-load the async OpenAI client."""
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    @staticmethod
    def _audio_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
        """Convert a float32 numpy array to in-memory WAV bytes."""
        import soundfile as sf  # type: ignore[import-untyped]

        buf = io.BytesIO()
        audio_f32 = audio.astype(np.float32) if audio.dtype != np.float32 else audio
        sf.write(buf, audio_f32, sample_rate, format="WAV", subtype="FLOAT")
        buf.seek(0)
        return buf.read()

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcribe a complete audio buffer via the Whisper API."""
        client = self._get_client()
        wav_bytes = await asyncio.get_running_loop().run_in_executor(
            None, self._audio_to_wav_bytes, audio, sample_rate
        )

        response = await client.audio.transcriptions.create(  # type: ignore[union-attr]
            model=self._model,
            file=("audio.wav", wav_bytes, "audio/wav"),
            language="en",
        )
        transcript = response.text.strip()
        logger.info("OpenAI STT transcript: %s", transcript)
        return transcript

    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[np.ndarray],
        sample_rate: int,
    ) -> AsyncIterator[str]:
        """Collect all audio chunks, then transcribe as a single request.

        The OpenAI Whisper API does not support true streaming input, so we
        accumulate all chunks first.
        """
        collected: list[np.ndarray] = []
        async for chunk in audio_chunks:
            collected.append(chunk)

        if not collected:
            return

        full_audio = np.concatenate(collected)
        transcript = await self.transcribe(full_audio, sample_rate)
        if transcript:
            yield transcript
