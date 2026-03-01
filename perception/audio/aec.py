"""
Acoustic Echo Cancellation for Emily's full-duplex voice pipeline.

Subtracts Emily's own voice (output) from the microphone input in real time
so Emily doesn't hear herself speaking and create feedback loops.

Uses an adaptive NLMS filter with double-talk detection. Falls back to
spectral subtraction when the adaptive filter isn't converged.

Design constraints:
- AEC reference signal taken AFTER the DAC (output loopback)
- Calibration runs at session start to estimate loudspeaker-to-mic delay
- Double-talk detection freezes filter adaptation to prevent divergence
- Total latency budget: <= 5ms
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class AECConfig:
    """AEC configuration parameters."""

    tail_length_ms: int = 100
    adaptation_rate: float = 0.02
    sample_rate: int = 48000
    double_talk_threshold: float = 0.6
    min_convergence_frames: int = 100
    spectral_floor_db: float = -40.0

    def __post_init__(self) -> None:
        """Compute derived parameters."""
        self.filter_length: int = int(self.sample_rate * self.tail_length_ms / 1000)


class DoubleTalkDetector:
    """
    Detects when the user speaks simultaneously with Emily.

    Uses cross-correlation between the reference signal and the error signal.
    High correlation = echo only. Low correlation with high mic energy = double-talk.
    """

    def __init__(self, threshold: float = 0.6) -> None:
        """
        Args:
            threshold: Cross-correlation threshold below which double-talk is declared.
        """
        self._threshold = threshold
        self._ref_energy_ema: float = 1e-8
        self._mic_energy_ema: float = 1e-8
        self._alpha: float = 0.05

    def update(
        self,
        mic_signal: npt.NDArray[np.float32],
        reference: npt.NDArray[np.float32],
        error: npt.NDArray[np.float32],
    ) -> bool:
        """
        Determine if double-talk is occurring.

        Args:
            mic_signal: Raw microphone input.
            reference: What the speaker is playing (AEC reference).
            error: Mic signal after echo subtraction.

        Returns:
            True if double-talk detected (user speaking during Emily's output).
        """
        mic_energy = float(np.mean(mic_signal**2))
        ref_energy = float(np.mean(reference**2))

        self._mic_energy_ema = (1 - self._alpha) * self._mic_energy_ema + self._alpha * mic_energy
        self._ref_energy_ema = (1 - self._alpha) * self._ref_energy_ema + self._alpha * ref_energy

        if self._ref_energy_ema < 1e-8:
            return mic_energy > 1e-6

        err_energy = float(np.mean(error**2))
        if mic_energy < 1e-8:
            return False

        suppression_ratio = 1.0 - (err_energy / max(mic_energy, 1e-10))
        return (
            suppression_ratio < self._threshold
            and self._mic_energy_ema > self._ref_energy_ema * 0.3
        )


class AcousticEchoCanceller:
    """
    Adaptive echo canceller using Normalized LMS (NLMS) filter.

    Continuously subtracts the output signal from the input signal.
    Falls back to spectral subtraction when the filter hasn't converged.
    """

    def __init__(self, config: AECConfig | None = None) -> None:
        """
        Args:
            config: AEC configuration. Uses defaults if None.
        """
        self.config = config or AECConfig()

        self._filter = np.zeros(self.config.filter_length, dtype=np.float32)
        self._ref_buffer = np.zeros(self.config.filter_length, dtype=np.float32)

        self._double_talk = DoubleTalkDetector(self.config.double_talk_threshold)
        self._convergence_count = 0
        self._is_converged = False
        self._delay_samples: int = 0
        self._calibrated = False

    async def calibrate(
        self,
        mic_chunk: npt.NDArray[np.float32],
        ref_chunk: npt.NDArray[np.float32],
    ) -> int:
        """
        Estimate loudspeaker-to-microphone delay via cross-correlation.

        Should be called at session start with a known test signal.

        Args:
            mic_chunk: Microphone audio containing the played-back test tone.
            ref_chunk: The test tone that was played.

        Returns:
            Estimated delay in samples.
        """
        correlation = np.correlate(mic_chunk, ref_chunk, mode="full")
        center = len(ref_chunk) - 1
        peak_idx = int(np.argmax(np.abs(correlation)))
        self._delay_samples = abs(peak_idx - center)
        self._calibrated = True
        log.info(
            "aec_calibrated",
            delay_samples=self._delay_samples,
            delay_ms=f"{self._delay_samples / self.config.sample_rate * 1000:.1f}",
        )
        return self._delay_samples

    def process(
        self,
        mic_chunk: npt.NDArray[np.float32],
        reference_chunk: npt.NDArray[np.float32],
    ) -> npt.NDArray[np.float32]:
        """
        Remove echo from microphone signal using the reference (speaker output).

        Uses Block NLMS: a Toeplitz-like tap matrix built via stride tricks
        enables vectorized echo estimation (single matmul) and a single
        filter update per chunk instead of per sample.

        Args:
            mic_chunk: Raw microphone audio (float32).
            reference_chunk: What the speaker is currently playing (float32).

        Returns:
            Echo-cancelled microphone audio.
        """
        if reference_chunk is None or len(reference_chunk) == 0:
            return mic_chunk

        ref_energy = float(np.mean(reference_chunk**2))
        if ref_energy < 1e-10:
            return mic_chunk

        n = len(mic_chunk)
        flen = self.config.filter_length

        history = np.concatenate([self._ref_buffer, reference_chunk[:n]])

        # Build (n, flen) tap matrix — each row is the reversed reference
        # window for that sample position.  Stride tricks give a zero-copy
        # windowed view; the contiguous copy ensures BLAS-friendly layout.
        taps_fwd = np.lib.stride_tricks.as_strided(
            history,
            shape=(n, flen),
            strides=(history.strides[0], history.strides[0]),
        )
        taps = np.ascontiguousarray(taps_fwd[:, ::-1])

        # Vectorized echo estimation — single matmul replaces n dot products
        echo_estimates = taps @ self._filter
        output = (mic_chunk[:n] - echo_estimates).astype(np.float32)

        is_double_talk = self._double_talk.update(
            mic_chunk,
            reference_chunk,
            output,
        )

        if not is_double_talk:
            # Block NLMS: gradient averaged over the chunk
            gradient = taps.T @ output / n
            avg_power = float(np.einsum("ij,ij->", taps, taps) / n) + 1e-8
            step = self.config.adaptation_rate / avg_power
            self._filter = (self._filter + step * gradient).astype(np.float32)
            self._convergence_count += 1

        self._ref_buffer = history[-flen:]

        if self._convergence_count > self.config.min_convergence_frames:
            self._is_converged = True

        if not self._is_converged:
            output = self._spectral_subtraction(mic_chunk, reference_chunk)

        return output

    def _spectral_subtraction(
        self,
        mic: npt.NDArray[np.float32],
        ref: npt.NDArray[np.float32],
    ) -> npt.NDArray[np.float32]:
        """
        Fallback echo reduction using spectral subtraction.

        Less precise than adaptive filtering but works immediately without convergence.

        Args:
            mic: Microphone signal.
            ref: Reference signal.

        Returns:
            Echo-reduced signal.
        """
        n = max(len(mic), len(ref))
        nfft = 1
        while nfft < n:
            nfft *= 2

        mic_fft = np.fft.rfft(mic, n=nfft)
        ref_fft = np.fft.rfft(ref, n=nfft)

        mic_mag = np.abs(mic_fft)
        ref_mag = np.abs(ref_fft)

        floor_linear = 10 ** (self.config.spectral_floor_db / 20.0)
        suppressed_mag = np.maximum(mic_mag - ref_mag * 0.8, mic_mag * floor_linear)

        phase = np.angle(mic_fft)
        result_fft = suppressed_mag * np.exp(1j * phase)
        result = np.fft.irfft(result_fft, n=nfft)[: len(mic)]

        return result.astype(np.float32)

    def reset(self) -> None:
        """Reset the adaptive filter state."""
        self._filter[:] = 0
        self._ref_buffer[:] = 0
        self._convergence_count = 0
        self._is_converged = False
        log.info("aec_filter_reset")

    @property
    def is_converged(self) -> bool:
        """True if the adaptive filter has converged."""
        return self._is_converged

    @property
    def is_calibrated(self) -> bool:
        """True if the delay calibration has been performed."""
        return self._calibrated

    @property
    def convergence_time_s(self) -> float:
        """Estimated seconds for the adaptive filter to converge from cold start.

        Based on the configured min_convergence_frames at 10ms per chunk.
        Used by the FSM to set the post-speech STT hold-off duration.
        """
        return self.config.min_convergence_frames * 0.01
