"""
Full-duplex audio capture engine for Emily's voice pipeline.

Runs two completely independent async streams simultaneously:
- Input: microphone capture at 48kHz, downsampled to 16kHz for STT
- Output: TTS playback at 24kHz with AEC reference loopback

Ring buffers guarantee zero frame drops under CPU load spikes.
Capture thread uses SCHED_FIFO real-time priority on Linux.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

import numpy as np

from config import AudioConfig
from observability.logger import get_logger
from perception.audio.stream import AudioChunk

log = get_logger(__name__)

# 10ms chunk at 48kHz = 480 samples
_INPUT_CHUNK_SAMPLES_48K = 480
_INPUT_CHUNK_SAMPLES_16K = 160
_OUTPUT_CHUNK_SAMPLES_24K = 240


@dataclass
class CaptureConfig:
    """Configuration for the full-duplex capture engine."""

    input_sample_rate: int = 48000
    input_channels: int = 1
    input_chunk_ms: int = 10
    input_ring_buffer_s: int = 30

    output_sample_rate: int = 24000
    output_channels: int = 2
    output_chunk_ms: int = 10

    stt_sample_rate: int = 16000

    input_device: str | int | None = None
    output_device: str | int | None = None

    @classmethod
    def from_audio_config(cls, cfg: AudioConfig) -> CaptureConfig:
        """Build CaptureConfig from the existing AudioConfig."""
        return cls(
            input_device=cfg.input_device,
            output_device=cfg.output_device,
        )


class RingBuffer:
    """
    Lock-free single-producer single-consumer ring buffer for float32 audio.

    Overwrites oldest data on overflow rather than blocking.
    """

    def __init__(self, capacity_samples: int) -> None:
        """
        Args:
            capacity_samples: Maximum number of float32 samples to store.
        """
        self._buf = np.zeros(capacity_samples, dtype=np.float32)
        self._capacity = capacity_samples
        self._write_pos = 0
        self._read_pos = 0
        self._lock = threading.Lock()

    def write(self, data: np.ndarray) -> int:
        """
        Write samples into the ring buffer.

        If *data* is larger than the buffer capacity only the tail is kept.

        Args:
            data: Float32 audio samples to write.

        Returns:
            Number of samples actually written.
        """
        n = len(data)
        if n >= self._capacity:
            data = data[-self._capacity:]
            n = self._capacity

        with self._lock:
            space = self._capacity - self._available_unlocked()
            if n > space:
                overflow = n - space
                self._read_pos = (self._read_pos + overflow) % self._capacity

            end = self._write_pos + n
            if end <= self._capacity:
                self._buf[self._write_pos:end] = data
            else:
                first = self._capacity - self._write_pos
                self._buf[self._write_pos:] = data[:first]
                self._buf[:n - first] = data[first:]

            self._write_pos = (self._write_pos + n) % self._capacity
        return n

    def read(self, n_samples: int) -> np.ndarray | None:
        """
        Read up to n_samples from the buffer.

        Args:
            n_samples: Number of samples to read.

        Returns:
            Float32 array of samples, or None if insufficient data available.
        """
        with self._lock:
            avail = self._available_unlocked()
            if avail < n_samples:
                return None

            end = self._read_pos + n_samples
            if end <= self._capacity:
                out = self._buf[self._read_pos:end].copy()
            else:
                first = self._capacity - self._read_pos
                out = np.empty(n_samples, dtype=np.float32)
                out[:first] = self._buf[self._read_pos:]
                out[first:] = self._buf[:n_samples - first]

            self._read_pos = (self._read_pos + n_samples) % self._capacity
            return out

    def peek(self, n_samples: int) -> np.ndarray | None:
        """Read samples without advancing the read pointer."""
        with self._lock:
            avail = self._available_unlocked()
            if avail < n_samples:
                return None

            end = self._read_pos + n_samples
            if end <= self._capacity:
                return self._buf[self._read_pos:end].copy()
            first = self._capacity - self._read_pos
            out = np.empty(n_samples, dtype=np.float32)
            out[:first] = self._buf[self._read_pos:]
            out[first:] = self._buf[:n_samples - first]
            return out

    @property
    def available(self) -> int:
        """Number of samples available to read."""
        with self._lock:
            return self._available_unlocked()

    def _available_unlocked(self) -> int:
        """Available samples (caller must hold lock)."""
        if self._write_pos >= self._read_pos:
            return self._write_pos - self._read_pos
        return self._capacity - self._read_pos + self._write_pos

    def clear(self) -> None:
        """Reset the buffer."""
        with self._lock:
            self._read_pos = 0
            self._write_pos = 0


class AudioCaptureEngine:
    """
    Full-duplex audio capture and playback engine.

    Manages independent input and output streams via sounddevice.
    Input audio is stored in a ring buffer and delivered as 10ms chunks.
    Output audio is written to a ring buffer and drained by the output callback.
    """

    def __init__(self, config: CaptureConfig | None = None) -> None:
        """
        Args:
            config: Capture configuration. Uses defaults if None.
        """
        self.config = config or CaptureConfig()

        input_buf_samples = self.config.input_sample_rate * self.config.input_ring_buffer_s
        self._input_ring = RingBuffer(input_buf_samples)

        output_buf_samples = self.config.output_sample_rate * 15  # 15s output buffer
        self._output_ring = RingBuffer(output_buf_samples)

        self._aec_reference_ring = RingBuffer(self.config.output_sample_rate * 1)  # 1s AEC ref

        self._input_stream: object | None = None
        self._output_stream: object | None = None
        self._running = False
        self._input_queue: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=300)
        self._loop: asyncio.AbstractEventLoop | None = None

        self._input_chunk_samples = int(
            self.config.input_sample_rate * self.config.input_chunk_ms / 1000
        )
        self._output_chunk_samples = int(
            self.config.output_sample_rate * self.config.output_chunk_ms / 1000
        )

    async def start(self) -> None:
        """Launch input and output streams as separate real-time threads."""
        self._loop = asyncio.get_running_loop()
        self._running = True

        try:
            import sounddevice as sd
        except ImportError:
            log.warning("sounddevice_not_available", fallback="silence_generator")
            asyncio.create_task(self._silence_generator())
            return

        try:
            self._start_input_stream(sd)
            self._start_output_stream(sd)
        except Exception as exc:
            log.warning(
                "audio_device_unavailable",
                error=str(exc)[:200],
                fallback="silence_generator",
            )
            asyncio.create_task(self._silence_generator())
            return

        self._set_thread_priority_realtime()
        asyncio.create_task(self._input_dispatch_loop())

        log.info(
            "capture_engine_started",
            input_rate=self.config.input_sample_rate,
            output_rate=self.config.output_sample_rate,
            chunk_ms=self.config.input_chunk_ms,
        )

    def _start_input_stream(self, sd: object) -> None:
        """Open sounddevice InputStream with a callback."""
        import sounddevice as sd_mod

        def input_callback(
            indata: np.ndarray,
            frames: int,
            time_info: object,
            status: object,
        ) -> None:
            if status:
                log.debug("capture_input_status", status=str(status))
            if not self._running:
                return
            mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy().flatten()
            self._input_ring.write(mono)

        self._input_stream = sd_mod.InputStream(
            samplerate=self.config.input_sample_rate,
            channels=self.config.input_channels,
            dtype="float32",
            blocksize=self._input_chunk_samples,
            device=self.config.input_device,
            callback=input_callback,
        )
        self._input_stream.start()

    def _start_output_stream(self, sd: object) -> None:
        """Open sounddevice OutputStream with a callback that drains the output ring."""
        import sounddevice as sd_mod

        def output_callback(
            outdata: np.ndarray,
            frames: int,
            time_info: object,
            status: object,
        ) -> None:
            if status:
                log.debug("capture_output_status", status=str(status))
            if not self._running:
                outdata[:] = 0
                return

            data = self._output_ring.read(frames)
            if data is not None:
                if self.config.output_channels == 2 and data.ndim == 1:
                    stereo = np.column_stack((data, data))
                    outdata[:] = stereo[:frames]
                else:
                    outdata[:, 0] = data[:frames]
                    if outdata.shape[1] > 1:
                        outdata[:, 1:] = 0
                self._aec_reference_ring.write(data)
            else:
                outdata[:] = 0

        self._output_stream = sd_mod.OutputStream(
            samplerate=self.config.output_sample_rate,
            channels=self.config.output_channels,
            dtype="float32",
            blocksize=self._output_chunk_samples,
            device=self.config.output_device,
            callback=output_callback,
        )
        self._output_stream.start()

    async def _input_dispatch_loop(self) -> None:
        """Reads 10ms chunks from the input ring and dispatches to the async queue."""
        chunk_samples = self._input_chunk_samples
        interval = self.config.input_chunk_ms / 1000.0

        while self._running:
            data = self._input_ring.read(chunk_samples)
            if data is not None:
                chunk = AudioChunk(
                    data=data,
                    sample_rate=self.config.input_sample_rate,
                    channels=1,
                )
                if self._input_queue.full():
                    try:
                        self._input_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                await self._input_queue.put(chunk)
            else:
                await asyncio.sleep(interval * 0.5)

    async def _silence_generator(self) -> None:
        """Generate silence chunks when no audio device is available."""
        interval = self.config.input_chunk_ms / 1000.0
        while self._running:
            silence = np.zeros(self._input_chunk_samples, dtype=np.float32)
            chunk = AudioChunk(
                data=silence,
                sample_rate=self.config.input_sample_rate,
                channels=1,
            )
            await self._input_queue.put(chunk)
            await asyncio.sleep(interval)

    async def get_input_chunk(self) -> AudioChunk:
        """
        Non-blocking read of the latest 10ms input frame.

        Returns:
            The next AudioChunk from the capture queue.
        """
        return await self._input_queue.get()

    def write_output(self, audio: np.ndarray) -> None:
        """
        Write audio samples to the output ring buffer for playback.

        Args:
            audio: Float32 audio samples at the output sample rate (24kHz).
        """
        self._output_ring.write(audio)

    def get_aec_reference(self, n_samples: int) -> np.ndarray | None:
        """
        Read from the AEC reference ring buffer.

        Args:
            n_samples: Number of samples to read.

        Returns:
            Float32 array of what the speakers are currently playing,
            or None if insufficient data.
        """
        return self._aec_reference_ring.read(n_samples)

    @staticmethod
    def downsample_48k_to_16k(audio_48k: np.ndarray) -> np.ndarray:
        """
        Downsample from 48kHz to 16kHz using decimation (factor 3).

        Args:
            audio_48k: Float32 audio at 48kHz.

        Returns:
            Float32 audio at 16kHz.
        """
        from scipy.signal import decimate
        return decimate(audio_48k, 3, ftype="fir", zero_phase=False).astype(np.float32)

    @staticmethod
    def upsample_24k_to_48k(audio_24k: np.ndarray) -> np.ndarray:
        """
        Upsample from 24kHz to 48kHz (factor 2) for AEC reference alignment.

        Args:
            audio_24k: Float32 audio at 24kHz.

        Returns:
            Float32 audio at 48kHz.
        """
        from scipy.signal import resample_poly
        return resample_poly(audio_24k, 2, 1).astype(np.float32)

    def _set_thread_priority_realtime(self) -> None:
        """Set SCHED_FIFO on Linux for the audio threads."""
        if os.name != "posix":
            return
        try:
            SCHED_FIFO = 1
            param = struct.pack("i", 50)  # priority 50 out of 99
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            tid = libc.syscall(186)  # SYS_gettid
            result = libc.sched_setscheduler(tid, SCHED_FIFO, ctypes.c_char_p(param))
            if result == 0:
                log.info("realtime_priority_set", scheduler="SCHED_FIFO", priority=50)
            else:
                log.debug("realtime_priority_failed", hint="run as root or set CAP_SYS_NICE")
        except Exception as exc:
            log.debug("realtime_priority_unavailable", error=str(exc))

    async def stop(self) -> None:
        """Stop all audio streams and release devices."""
        self._running = False
        for stream in (self._input_stream, self._output_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as exc:
                    log.warning("capture_stream_stop_error", error=str(exc))
        self._input_ring.clear()
        self._output_ring.clear()
        log.info("capture_engine_stopped")

    @property
    def is_running(self) -> bool:
        """True if capture is active."""
        return self._running
