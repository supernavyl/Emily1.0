"""Asynchronous microphone input stream using sounddevice."""

from __future__ import annotations

import asyncio
import logging
import math

import numpy as np

try:
    from scipy.signal import resample_poly as _resample_poly
except ImportError:
    _resample_poly = None

import contextlib
from typing import TYPE_CHECKING

from voice_engine.audio.noise_reduction import NoiseReducer

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import TracebackType

logger = logging.getLogger(__name__)

MIC_SAMPLE_RATE = 16000
MIC_FRAME_SIZE = 512  # 32 ms at 16 kHz — matches Silero VAD expectation
MIC_CHANNELS = 1
MIC_DTYPE = "float32"

# Capture in larger batches to amortise the resample FIR cost.
# 4096 samples at 44100 Hz ≈ 93 ms — small enough for low latency.
_HW_BLOCKSIZE_HINT = 4096


class MicrophoneStream:
    """Async context manager that yields float32 audio chunks from the microphone.

    Opens the hardware at its native sample rate and resamples to the target
    rate (default 16 kHz) so that VAD and STT always receive consistent audio.

    Usage::

        async with MicrophoneStream() as mic:
            async for chunk in mic.stream():
                process(chunk)
    """

    def __init__(
        self,
        sample_rate: int = MIC_SAMPLE_RATE,
        frame_size: int = MIC_FRAME_SIZE,
        channels: int = MIC_CHANNELS,
        device: int | str | None = None,
    ) -> None:
        self._target_rate = sample_rate
        self._frame_size = frame_size
        self._channels = channels
        self._device = device
        self._hw_rate: int = sample_rate  # resolved in __aenter__
        self._needs_resample: bool = False
        self._resample_up: int = 1
        self._resample_down: int = 1
        self._queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue(maxsize=100)
        self._sd_stream: object | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._noise_reducer = NoiseReducer()
        logger.info(
            "MicrophoneStream configured: target_rate=%d frame=%d ch=%d",
            sample_rate,
            frame_size,
            channels,
        )

    def _enqueue(self, chunk: np.ndarray) -> None:
        """Put a chunk on the queue, dropping the oldest frame if full."""
        if self._queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            logger.warning("Mic queue full — dropped oldest frame (STT falling behind)")
        self._queue.put_nowait(chunk)

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        """Called from the sounddevice audio thread — resample and push to async queue.

        Resampling is done here in the callback thread to keep the async loop
        free for VAD / STT processing.
        """
        if status:
            logger.warning("Sounddevice status: %s", status)

        chunk = indata[:, 0].copy() if self._channels == 1 else indata.copy()

        if self._needs_resample and _resample_poly is not None:
            chunk = _resample_poly(chunk, self._resample_up, self._resample_down).astype(np.float32)

        # Noise reduction (passthrough if DeepFilterNet unavailable)
        chunk = self._noise_reducer.process(chunk, self._target_rate)

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._enqueue, chunk)

    async def __aenter__(self) -> MicrophoneStream:
        """Open the sounddevice input stream, auto-detecting hardware sample rate."""
        import sounddevice as sd  # type: ignore[import-untyped]

        self._loop = asyncio.get_running_loop()

        # Detect the device's native sample rate
        dev_info = sd.query_devices(self._device or sd.default.device[0], "input")
        self._hw_rate = int(dev_info["default_samplerate"])  # type: ignore[index]
        self._needs_resample = self._hw_rate != self._target_rate

        if self._needs_resample:
            if _resample_poly is None:
                logger.warning(
                    "Mic needs resample %d→%d Hz but scipy is not installed. "
                    "Audio will be at wrong sample rate — VAD/STT may degrade.",
                    self._hw_rate,
                    self._target_rate,
                )
                self._needs_resample = False
                hw_blocksize = self._frame_size
            else:
                g = math.gcd(self._target_rate, self._hw_rate)
                self._resample_up = self._target_rate // g
                self._resample_down = self._hw_rate // g
                hw_blocksize = _HW_BLOCKSIZE_HINT
                logger.info(
                    "Mic hardware rate %d Hz → resample (%d/%d) → %d Hz",
                    self._hw_rate,
                    self._resample_up,
                    self._resample_down,
                    self._target_rate,
                )
        else:
            hw_blocksize = self._frame_size

        self._sd_stream = sd.InputStream(
            samplerate=self._hw_rate,
            blocksize=hw_blocksize,
            channels=self._channels,
            dtype=MIC_DTYPE,
            device=self._device,
            callback=self._audio_callback,
        )
        self._sd_stream.start()  # type: ignore[union-attr]
        logger.info(
            "Microphone stream opened at %d Hz (blocksize=%d).", self._hw_rate, hw_blocksize
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the sounddevice stream."""
        if self._sd_stream is not None:
            self._sd_stream.stop()  # type: ignore[union-attr]
            self._sd_stream.close()  # type: ignore[union-attr]
            self._sd_stream = None
            logger.info("Microphone stream closed.")
        # Signal the stream iterator to stop
        await self._queue.put(None)

    async def stream(self) -> AsyncIterator[np.ndarray]:
        """Yield float32 audio chunks of exactly ``frame_size`` samples.

        Chunks from the callback may be larger (after resampling a big batch),
        so we buffer and yield exact-size frames for VAD.
        """
        buf = np.empty(0, dtype=np.float32)

        while True:
            raw = await self._queue.get()
            if raw is None:
                break

            buf = np.concatenate((buf, raw))
            while len(buf) >= self._frame_size:
                yield buf[: self._frame_size]
                buf = buf[self._frame_size :]

    @property
    def sample_rate(self) -> int:
        """The target sample rate of the audio stream (after resampling)."""
        return self._target_rate
