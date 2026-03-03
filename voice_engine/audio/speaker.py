"""Async audio playback via sounddevice."""

from __future__ import annotations

import asyncio
import logging
import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

try:
    from scipy.signal import resample_poly as _resample_poly
except ImportError:
    _resample_poly = None

logger = logging.getLogger(__name__)


def _resample_for_device(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Resample audio from src_rate to dst_rate using polyphase filtering."""
    if src_rate == dst_rate:
        return audio
    if _resample_poly is None:
        logger.warning(
            "scipy not available — cannot resample %d→%d Hz. Audio may sound wrong.",
            src_rate,
            dst_rate,
        )
        return audio
    g = math.gcd(dst_rate, src_rate)
    return _resample_poly(audio, dst_rate // g, src_rate // g).astype(np.float32)


class Speaker:
    """Plays float32 audio buffers through the default output device.

    Automatically resamples to the hardware's native rate if it differs
    from the requested sample rate.
    """

    def __init__(self, device: int | str | None = None) -> None:
        self._device = device
        self._cancelled = asyncio.Event()
        self._hw_rate: int | None = None
        logger.info("Speaker initialised (device=%s).", device or "default")

    def _detect_hw_rate(self) -> int:
        """Detect and cache the default output device's native sample rate."""
        if self._hw_rate is None:
            import sounddevice as sd  # type: ignore[import-untyped]

            dev = self._device if self._device is not None else sd.default.device[1]
            info = sd.query_devices(dev, "output")
            self._hw_rate = int(info["default_samplerate"])  # type: ignore[index]
            logger.info("Speaker output device rate: %d Hz", self._hw_rate)
        return self._hw_rate

    @property
    def cancelled(self) -> asyncio.Event:
        """Event that can be set externally to cancel playback."""
        return self._cancelled

    def cancel(self) -> None:
        """Signal cancellation — any in-progress playback will stop."""
        self._cancelled.set()
        logger.debug("Speaker playback cancelled.")

    def reset(self) -> None:
        """Clear the cancellation flag so the speaker can be reused."""
        self._cancelled.clear()

    async def play(self, audio: np.ndarray, sample_rate: int) -> None:
        """Play a complete float32 audio buffer asynchronously.

        Playback runs in a thread executor so it does not block the event loop.
        """
        import sounddevice as sd  # type: ignore[import-untyped]

        if len(audio) == 0:
            return

        if self._cancelled.is_set():
            return

        hw_rate = self._detect_hw_rate()
        play_audio = _resample_for_device(audio, sample_rate, hw_rate)

        loop = asyncio.get_running_loop()
        done = asyncio.Event()

        def _play() -> None:
            try:
                sd.play(play_audio.astype(np.float32), samplerate=hw_rate, device=self._device)
                sd.wait()
            finally:
                loop.call_soon_threadsafe(done.set)

        loop.run_in_executor(None, _play)
        # Wait for playback to complete or cancellation
        cancel_task = asyncio.create_task(self._cancelled.wait())
        done_task = asyncio.create_task(done.wait())

        finished, pending = await asyncio.wait(
            {cancel_task, done_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        if self._cancelled.is_set():
            sd.stop()
            logger.debug("Playback stopped due to cancellation.")

    async def play_stream(
        self,
        audio_chunks: AsyncIterator[np.ndarray],
        sample_rate: int,
    ) -> None:
        """Stream audio chunks to the speaker, stopping on cancellation."""
        import sounddevice as sd  # type: ignore[import-untyped]

        hw_rate = self._detect_hw_rate()

        stream = sd.OutputStream(
            samplerate=hw_rate,
            channels=1,
            dtype="float32",
            device=self._device,
        )
        stream.start()

        try:
            async for chunk in audio_chunks:
                if self._cancelled.is_set():
                    logger.debug("Stream playback cancelled.")
                    break

                if len(chunk) == 0:
                    continue

                resampled = _resample_for_device(chunk, sample_rate, hw_rate)
                audio_f32 = resampled.astype(np.float32)
                if audio_f32.ndim == 1:
                    audio_f32 = audio_f32.reshape(-1, 1)

                # Write in blocks to allow checking for cancellation
                block_size = hw_rate  # ~1 second blocks
                offset = 0
                while offset < len(audio_f32):
                    if self._cancelled.is_set():
                        break
                    end = min(offset + block_size, len(audio_f32))
                    stream.write(audio_f32[offset:end])
                    offset = end
                    await asyncio.sleep(0)
        finally:
            stream.stop()
            stream.close()
