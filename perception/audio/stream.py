"""
Continuous audio capture for Emily.

Opens the system microphone and yields raw PCM chunks into an asyncio queue.
Designed to run as a background task for the lifetime of the process.

Architecture:
- Synchronous PyAudio/sounddevice callback runs in a C thread
- Each chunk is put() into an asyncio.Queue via run_coroutine_threadsafe
- Downstream consumers (VAD, wake word) pull from the queue
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import Deque

import numpy as np

from config import AudioConfig
from observability.logger import get_logger

log = get_logger(__name__)


class AudioChunk:
    """A single chunk of raw PCM audio data."""

    __slots__ = ("data", "timestamp", "sample_rate", "channels")

    def __init__(
        self,
        data: np.ndarray,
        sample_rate: int,
        channels: int,
    ) -> None:
        """
        Args:
            data: Raw PCM data as float32 numpy array, shape (samples,) or (samples, channels).
            sample_rate: Sample rate in Hz.
            channels: Number of audio channels.
        """
        self.data = data
        self.timestamp = time.monotonic()
        self.sample_rate = sample_rate
        self.channels = channels

    @property
    def duration_ms(self) -> float:
        """Duration of this chunk in milliseconds."""
        n_samples = self.data.shape[0]
        return (n_samples / self.sample_rate) * 1000.0


class AudioStream:
    """
    Continuous microphone capture stream.

    Wraps sounddevice for cross-platform audio input. Falls back to
    a silence generator when no audio device is available (useful in
    testing / CI environments).
    """

    def __init__(self, config: AudioConfig) -> None:
        """
        Args:
            config: Audio configuration (sample_rate, channels, chunk_size, device).
        """
        self.config = config
        self._queue: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=100)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stream: object | None = None
        self._running = False
        self._device_available = False

    async def start(self) -> None:
        """
        Start capturing audio from the microphone.

        If no audio device is found, starts a silence generator for testing.
        """
        self._loop = asyncio.get_running_loop()
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
            self._start_sounddevice(sd)
            self._device_available = True
            log.info(
                "audio_stream_started",
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                device=self.config.input_device or "default",
            )
        except Exception as exc:
            log.warning(
                "audio_device_unavailable",
                error=str(exc),
                fallback="silence_generator",
            )
            self._device_available = False
            asyncio.create_task(self._silence_generator())

    def _start_sounddevice(self, sd: object) -> None:
        """Open a sounddevice InputStream with a callback."""
        import sounddevice as sd_mod  # type: ignore[import-untyped]

        def callback(
            indata: np.ndarray,
            frames: int,
            time_info: object,
            status: object,
        ) -> None:
            if status:
                log.debug("audio_stream_status", status=str(status))
            if not self._running or self._loop is None:
                return
            chunk = AudioChunk(
                data=indata[:, 0].copy() if indata.ndim > 1 else indata.copy(),
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
            )
            asyncio.run_coroutine_threadsafe(
                self._enqueue_chunk(chunk), self._loop
            )

        self._stream = sd_mod.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="float32",
            blocksize=self.config.chunk_size,
            device=self.config.input_device,
            callback=callback,
        )
        self._running = True
        self._stream.start()  # type: ignore[union-attr]

    async def _silence_generator(self) -> None:
        """Generate silence chunks when no audio device is available."""
        chunk_duration_s = self.config.chunk_size / self.config.sample_rate
        while self._running:
            silence = np.zeros(self.config.chunk_size, dtype=np.float32)
            chunk = AudioChunk(
                data=silence,
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
            )
            await self._enqueue_chunk(chunk)
            await asyncio.sleep(chunk_duration_s)

    async def _enqueue_chunk(self, chunk: AudioChunk) -> None:
        """Put a chunk onto the queue, dropping oldest if full."""
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self._queue.put(chunk)

    async def read(self) -> AudioChunk:
        """
        Read the next audio chunk from the stream.

        Returns:
            The next AudioChunk from the capture queue.
        """
        return await self._queue.get()

    def stop(self) -> None:
        """Stop audio capture and release the device."""
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()  # type: ignore[union-attr]
                self._stream.close()  # type: ignore[union-attr]
            except Exception as exc:
                log.warning("audio_stream_stop_error", error=str(exc))
        log.info("audio_stream_stopped")

    @property
    def is_running(self) -> bool:
        """True if the audio capture is active."""
        return self._running
