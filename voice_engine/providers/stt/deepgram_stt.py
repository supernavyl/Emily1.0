"""Deepgram STT provider — prerecorded and live streaming transcription."""

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


class DeepgramSTT(STTProvider):
    """Transcription via the Deepgram SDK (prerecorded + live websocket)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        logger.info("DeepgramSTT configured.")

    def _make_client(self) -> object:
        """Create a new Deepgram async client."""
        from deepgram import DeepgramClient  # type: ignore[import-untyped]

        return DeepgramClient(self._api_key)

    @staticmethod
    def _audio_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
        """Convert float32 numpy array to in-memory WAV bytes."""
        import soundfile as sf  # type: ignore[import-untyped]

        buf = io.BytesIO()
        audio_f32 = audio.astype(np.float32) if audio.dtype != np.float32 else audio
        sf.write(buf, audio_f32, sample_rate, format="WAV", subtype="FLOAT")
        buf.seek(0)
        return buf.read()

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcribe a complete audio buffer using Deepgram prerecorded API."""
        from deepgram import PrerecordedOptions  # type: ignore[import-untyped]

        client = self._make_client()
        wav_bytes = await asyncio.get_running_loop().run_in_executor(
            None, self._audio_to_wav_bytes, audio, sample_rate
        )

        options = PrerecordedOptions(
            model="nova-2",
            language="en",
            smart_format=True,
        )

        payload = {"buffer": wav_bytes, "mimetype": "audio/wav"}
        response = await client.listen.asyncrest.v("1").transcribe_file(  # type: ignore[union-attr]
            payload, options
        )

        transcript = (
            response.results.channels[0].alternatives[0].transcript  # type: ignore[union-attr]
        )
        logger.info("Deepgram transcript: %s", transcript)
        return transcript.strip()

    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[np.ndarray],
        sample_rate: int,
    ) -> AsyncIterator[str]:
        """Stream audio chunks to Deepgram via live websocket, yielding transcripts."""
        from deepgram import LiveOptions, LiveTranscriptionEvents  # type: ignore[import-untyped]

        client = self._make_client()
        transcript_queue: asyncio.Queue[str] = asyncio.Queue()
        done_event = asyncio.Event()

        options = LiveOptions(
            model="nova-2",
            language="en",
            encoding="linear16",
            sample_rate=sample_rate,
            channels=1,
            smart_format=True,
            interim_results=False,
        )

        connection = client.listen.asyncwebsocket.v("1")  # type: ignore[union-attr]

        async def on_transcript(_self: object, result: object, **_kwargs: object) -> None:
            """Handle incoming transcription results."""
            sentence = result.channel.alternatives[0].transcript  # type: ignore[union-attr]
            if sentence.strip():  # type: ignore[union-attr]
                await transcript_queue.put(sentence.strip())  # type: ignore[union-attr]

        async def on_error(_self: object, error: object, **_kwargs: object) -> None:
            logger.error("Deepgram live error: %s", error)

        async def on_close(_self: object, _close: object, **_kwargs: object) -> None:
            logger.debug("Deepgram live connection closed.")
            done_event.set()

        connection.on(LiveTranscriptionEvents.Transcript, on_transcript)  # type: ignore[union-attr]
        connection.on(LiveTranscriptionEvents.Error, on_error)  # type: ignore[union-attr]
        connection.on(LiveTranscriptionEvents.Close, on_close)  # type: ignore[union-attr]

        started = await connection.start(options)  # type: ignore[union-attr]
        if not started:
            logger.error("Failed to start Deepgram live connection.")
            return

        try:
            async for chunk in audio_chunks:
                audio_int16 = (chunk * 32767).astype(np.int16)
                await connection.send(audio_int16.tobytes())  # type: ignore[union-attr]

            await connection.finish()  # type: ignore[union-attr]
            await done_event.wait()

            while not transcript_queue.empty():
                yield await transcript_queue.get()
        except Exception:
            logger.exception("Error during Deepgram live transcription")
            await connection.finish()  # type: ignore[union-attr]
