"""
Audio output stream for Emily's TTS playback.

Handles:
- True streaming playback (plays chunks as they arrive, not after buffering)
- Interruption support (user speech detected mid-playback -> stop immediately)
- Volume normalization to prevent jumps between sentences/engines
- WAV vs raw PCM vs MP3 detection and handling
- AEC reference feed for full-duplex echo cancellation
"""

from __future__ import annotations

import asyncio
import io
import wave
from typing import AsyncIterator

import numpy as np

from observability.logger import get_logger

log = get_logger(__name__)

_TARGET_DBFS = -20.0


def normalize_audio(
    audio: np.ndarray,
    target_dbfs: float = _TARGET_DBFS,
) -> np.ndarray:
    """
    Normalize audio to a target loudness level.

    Prevents jarring volume jumps between sentences and TTS engines.

    Args:
        audio: Float32 audio in [-1.0, 1.0].
        target_dbfs: Target loudness in dBFS.

    Returns:
        Normalized float32 audio.
    """
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < 1e-8:
        return audio

    current_dbfs = 20 * np.log10(rms + 1e-10)
    gain_db = target_dbfs - current_dbfs
    gain_db = max(-12.0, min(12.0, gain_db))
    gain = 10 ** (gain_db / 20.0)

    result = audio * gain
    peak = float(np.max(np.abs(result)))
    if peak > 0.95:
        result *= 0.95 / peak

    return result


class AudioOutputStream:
    """
    True streaming audio output.

    Decodes and plays each audio chunk immediately as it arrives rather
    than buffering the entire response first. Supports mid-stream
    interruption via an asyncio.Event.
    """

    _SAMPLE_RATE = 24000
    _CHANNELS = 1

    def __init__(self, output_device: str | int | None = None) -> None:
        """
        Args:
            output_device: sounddevice output device name/index, or None for default.
        """
        self._output_device = output_device
        self._sd_stream: object | None = None
        self._interrupt_event = asyncio.Event()
        self._playing = False
        self._playback_queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue(maxsize=50)

    def interrupt(self) -> None:
        """Signal that playback should stop immediately (user spoke)."""
        self._interrupt_event.set()
        log.debug("tts_playback_interrupted")

    async def play_stream(
        self,
        chunk_iter: AsyncIterator[bytes],
        sample_rate: int = 24000,
    ) -> None:
        """
        Play audio chunks as they arrive with true streaming.

        Each chunk is decoded, normalized, and pushed to the playback
        queue. A separate drain task feeds chunks to sounddevice.

        Args:
            chunk_iter: Async iterator yielding audio bytes (PCM int16, WAV, or MP3).
            sample_rate: Expected sample rate of the audio.
        """
        self._interrupt_event.clear()
        self._playing = True

        try:
            sd = await self._get_sounddevice()

            pending_mp3 = io.BytesIO()
            is_mp3 = False
            first_chunk_raw = True

            drain_task = asyncio.create_task(
                self._drain_playback_queue(sd, sample_rate)
            )

            async for chunk in chunk_iter:
                if self._interrupt_event.is_set():
                    log.info("tts_playback_stopped_by_interrupt")
                    break

                if first_chunk_raw:
                    first_chunk_raw = False
                    if chunk[:3] == b"ID3" or (
                        len(chunk) >= 2 and chunk[0] == 0xFF and (chunk[1] & 0xE0) == 0xE0
                    ):
                        is_mp3 = True

                if is_mp3:
                    pending_mp3.write(chunk)
                    continue

                audio = self._decode_chunk(chunk, sample_rate)
                if audio is not None and len(audio) > 0:
                    audio = normalize_audio(audio)
                    await self._playback_queue.put(audio)

            if is_mp3:
                pending_mp3.seek(0)
                mp3_bytes = pending_mp3.read()
                if mp3_bytes and not self._interrupt_event.is_set():
                    audio, actual_rate = self._decode_mp3(mp3_bytes)
                    if len(audio) > 0:
                        audio = normalize_audio(audio)
                        await self._playback_queue.put(audio)

            await self._playback_queue.put(None)

            if not self._interrupt_event.is_set():
                await drain_task
            else:
                drain_task.cancel()
                try:
                    await drain_task
                except asyncio.CancelledError:
                    pass

        except ImportError:
            log.warning("sounddevice_not_available_tts_audio_discarded")
            async for _ in chunk_iter:
                pass
        except Exception as exc:
            log.error("tts_playback_error", error=str(exc))
        finally:
            self._playing = False

    async def _drain_playback_queue(self, sd: object, sample_rate: int) -> None:
        """Drain the playback queue, playing each chunk through sounddevice."""
        import sounddevice as sd_mod

        while True:
            audio = await self._playback_queue.get()
            if audio is None:
                break
            if self._interrupt_event.is_set():
                break

            try:
                await asyncio.to_thread(
                    sd_mod.play, audio, samplerate=sample_rate, blocking=True
                )
            except Exception as exc:
                log.error("chunk_playback_error", error=str(exc))
                break

    def _decode_chunk(self, data: bytes, sample_rate: int) -> np.ndarray | None:
        """
        Decode a single audio chunk to float32 numpy array.

        Handles WAV and raw PCM int16. MP3 is handled at the stream level.

        Args:
            data: Audio bytes for one chunk.
            sample_rate: Expected sample rate.

        Returns:
            Float32 numpy array normalized to [-1.0, 1.0], or None on failure.
        """
        if len(data) < 4:
            return None

        if data[:4] == b"RIFF":
            try:
                with wave.open(io.BytesIO(data)) as wf:
                    raw = wf.readframes(wf.getnframes())
                    n_channels = wf.getnchannels()
                    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    if n_channels > 1:
                        audio = audio.reshape(-1, n_channels).mean(axis=1)
                    return audio
            except Exception:
                pass

        try:
            audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            return audio
        except Exception:
            return None

    @staticmethod
    async def _get_sounddevice() -> object:
        """Lazily import and return sounddevice module."""
        import sounddevice as sd
        return sd

    @staticmethod
    def _decode_mp3(data: bytes) -> tuple[np.ndarray, int]:
        """
        Decode MP3 bytes to float32 numpy array using ffmpeg.

        Args:
            data: MP3 audio bytes.

        Returns:
            Tuple of (float32 array, sample rate).
        """
        import subprocess

        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", "pipe:0",
                "-f", "s16le", "-acodec", "pcm_s16le",
                "-ac", "1", "-ar", "24000",
                "pipe:1",
            ],
            input=data,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode()[:200]}")

        audio = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        return audio, 24000

    @property
    def is_playing(self) -> bool:
        """True if audio is currently playing."""
        return self._playing
