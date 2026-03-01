"""
Two-stage adaptive noise suppression for Emily.

Stage 1: noisereduce (CPU, <5ms) — always active
Stage 2: DeepFilterNet (GPU, ~5ms) — activates when SNR < threshold

Critically preserves speech naturalness markers:
- Breath sounds (crucial for turn detection)
- Lip smacks (disfluency markers)
- Hesitation sounds ("uh", "um")
- Emotional voice quality (crying, laughing, excitement)

These are NOT noise and must never be suppressed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from observability.logger import get_logger
from perception.audio.stream import AudioChunk

log = get_logger(__name__)


@dataclass
class NoiseConfig:
    """Noise suppression configuration."""

    adaptive_threshold_db: float = 15.0
    cpu_suppress_stationary: bool = True
    cpu_prop_decrease: float = 0.6
    speech_protect_band_low_hz: int = 80
    speech_protect_band_high_hz: int = 8000
    breath_band_low_hz: int = 200
    breath_band_high_hz: int = 2500


class SNRMonitor:
    """
    Continuous SNR estimation using a dual-buffer approach.

    Tracks noise floor during silence and speech energy during speech.
    """

    def __init__(self) -> None:
        self._noise_floor_rms: float = 0.005
        self._speech_rms: float = 0.05
        self._alpha: float = 0.02

    def estimate(self, audio: np.ndarray, is_speech: bool = False) -> float:
        """
        Estimate current SNR in dB.

        Args:
            audio: Audio chunk (float32).
            is_speech: Whether this chunk contains speech.

        Returns:
            Estimated SNR in dB.
        """
        rms = float(np.sqrt(np.mean(audio**2) + 1e-10))

        if not is_speech:
            self._noise_floor_rms = (1 - self._alpha) * self._noise_floor_rms + self._alpha * rms
        else:
            self._speech_rms = (1 - self._alpha) * self._speech_rms + self._alpha * rms

        if self._noise_floor_rms < 1e-8:
            return 60.0
        snr = 20 * np.log10(self._speech_rms / max(self._noise_floor_rms, 1e-10))
        return float(np.clip(snr, -10, 60))


class SpeechFeatureProtector:
    """
    Protects speech naturalness markers from noise suppression.

    Creates a frequency-domain mask that preserves energy in bands
    containing breath sounds, fricatives, and voice quality markers.
    """

    def __init__(self, config: NoiseConfig) -> None:
        self.config = config

    def create_protection_mask(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> np.ndarray:
        """
        Create a frequency-domain protection mask for speech features.

        Args:
            audio: Audio chunk.
            sample_rate: Sample rate in Hz.

        Returns:
            Boolean mask over FFT bins that should be protected from suppression.
        """
        n_fft = len(audio)
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
        spectrum = np.abs(np.fft.rfft(audio))

        speech_band = (freqs >= self.config.speech_protect_band_low_hz) & (
            freqs <= self.config.speech_protect_band_high_hz
        )
        breath_band = (freqs >= self.config.breath_band_low_hz) & (
            freqs <= self.config.breath_band_high_hz
        )

        speech_energy = float(np.mean(spectrum[speech_band] ** 2)) if np.any(speech_band) else 0
        total_energy = float(np.mean(spectrum**2)) + 1e-10
        speech_ratio = speech_energy / total_energy

        mask = np.ones(len(freqs), dtype=np.float32)
        if speech_ratio > 0.3:
            mask[breath_band] = np.maximum(mask[breath_band], 0.8)
            mask[speech_band] = np.maximum(mask[speech_band], 0.6)

        return mask

    def apply_protection(
        self,
        original: np.ndarray,
        cleaned: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Blend original and cleaned audio using the protection mask.

        Args:
            original: Original audio (before noise suppression).
            cleaned: Noise-suppressed audio.
            mask: Protection mask (1.0 = use original, 0.0 = use cleaned).

        Returns:
            Blended audio preserving speech features.
        """
        n_fft = max(len(original), len(cleaned))
        orig_fft = np.fft.rfft(original, n=n_fft)
        clean_fft = np.fft.rfft(cleaned, n=n_fft)

        n_bins = len(orig_fft)
        if len(mask) < n_bins:
            extended = np.ones(n_bins, dtype=np.float32)
            extended[: len(mask)] = mask
            mask = extended
        elif len(mask) > n_bins:
            mask = mask[:n_bins]

        protection = mask * 0.3
        blended_fft = clean_fft * (1 - protection) + orig_fft * protection
        result = np.fft.irfft(blended_fft, n=n_fft)[: len(original)]
        return result.astype(np.float32)


class NoiseSuppressionEngine:
    """
    Two-stage adaptive noise suppression.

    Stage 1: noisereduce — CPU-based spectral gating, always active
    Stage 2: DeepFilterNet — GPU neural denoiser, only when SNR is poor
    """

    def __init__(self, config: NoiseConfig | None = None) -> None:
        """
        Args:
            config: Noise suppression configuration. Uses defaults if None.
        """
        self.config = config or NoiseConfig()
        self.snr_monitor = SNRMonitor()
        self._protector = SpeechFeatureProtector(self.config)
        self._noisereduce_available = False
        self._deepfilter_available = False
        self._deepfilter_model: object | None = None
        self._deepfilter_state: object | None = None
        self._noise_profile: np.ndarray | None = None

    async def load(self) -> None:
        """Load noise suppression engines."""
        try:
            import noisereduce  # noqa: F401

            self._noisereduce_available = True
            log.info("noisereduce_loaded")
        except ImportError:
            log.warning("noisereduce_not_available", hint="pip install noisereduce")

        try:
            from df import init_df

            self._deepfilter_model, self._deepfilter_state, _ = init_df()
            self._deepfilter_available = True
            log.info("deepfilternet_loaded")
        except ImportError:
            log.info("deepfilternet_not_available", hint="pip install deepfilternet")
        except Exception as exc:
            log.warning("deepfilternet_load_failed", error=str(exc))

    def process(
        self,
        chunk: AudioChunk,
        is_speech: bool = False,
    ) -> AudioChunk:
        """
        Apply noise suppression while protecting speech features.

        Args:
            chunk: Input audio chunk.
            is_speech: Whether this chunk is likely speech (from VAD).

        Returns:
            Noise-suppressed AudioChunk.
        """
        audio = chunk.data.copy()
        snr = self.snr_monitor.estimate(audio, is_speech)

        if float(np.mean(audio**2)) < 1e-10:
            return chunk

        protection_mask = self._protector.create_protection_mask(audio, chunk.sample_rate)

        if snr < self.config.adaptive_threshold_db and self._deepfilter_available:
            cleaned = self._apply_deepfilter(audio, chunk.sample_rate)
        elif self._noisereduce_available:
            cleaned = self._apply_noisereduce(audio, chunk.sample_rate)
        else:
            return chunk

        result = self._protector.apply_protection(audio, cleaned, protection_mask)

        return AudioChunk(
            data=result,
            sample_rate=chunk.sample_rate,
            channels=chunk.channels,
        )

    def _apply_noisereduce(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Apply CPU-based spectral gating noise reduction."""
        import noisereduce as nr

        return nr.reduce_noise(
            y=audio,
            sr=sr,
            stationary=self.config.cpu_suppress_stationary,
            prop_decrease=self.config.cpu_prop_decrease,
            n_fft=512,
            hop_length=128,
        ).astype(np.float32)

    def _apply_deepfilter(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Apply GPU neural noise suppression via DeepFilterNet."""
        try:
            import torch
            from df import enhance

            audio_tensor = torch.from_numpy(audio).unsqueeze(0)
            enhanced = enhance(self._deepfilter_model, self._deepfilter_state, audio_tensor)
            return enhanced.squeeze().numpy().astype(np.float32)
        except Exception as exc:
            log.debug("deepfilter_process_error", error=str(exc))
            if self._noisereduce_available:
                return self._apply_noisereduce(audio, sr)
            return audio

    def update_noise_profile(self, silence_audio: np.ndarray) -> None:
        """
        Update the noise profile from a known silence segment.

        Args:
            silence_audio: Audio known to contain only background noise.
        """
        self._noise_profile = silence_audio.copy()
        log.debug("noise_profile_updated", samples=len(silence_audio))
