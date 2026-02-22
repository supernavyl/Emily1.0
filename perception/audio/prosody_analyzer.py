"""
Continuous prosody feature extraction for Emily.

Extracts real-time prosodic features from user speech every processing cycle:
- F0 (fundamental frequency / pitch) and its trajectory
- Energy (loudness) and trajectory
- Speaking rate (syllables per second)
- Voice quality (modal, creaky, breathy)
- Final lengthening ratio
- Pause type classification

These features feed: turn detector, emotion engine, rhythm tracker, response planner.
Uses parselmouth (Praat bindings) for acoustic analysis.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

import numpy as np

from observability.logger import get_logger
from perception.audio.stream import AudioChunk

log = get_logger(__name__)


@dataclass
class ProsodyFeatures:
    """Extracted prosodic features for a single frame."""

    f0_hz: float = 0.0
    f0_trajectory: str = "level"
    f0_range_semitones: float = 0.0
    intensity_db: float = 0.0
    intensity_trajectory: str = "level"
    speaking_rate_syl_s: float = 0.0
    final_lengthening_ratio: float = 1.0
    voice_quality: str = "modal"
    articulation_precision: float = 0.5
    pause_duration_ms: float = 0.0
    pause_type: str = "none"
    stress_pattern: list[float] = field(default_factory=list)
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class SpeakerBaseline:
    """Per-speaker prosodic baseline, updated continuously."""

    f0_mean: float = 150.0
    f0_std: float = 30.0
    intensity_mean: float = 65.0
    rate_mean: float = 4.0
    n_frames: int = 0


class ProsodyAnalyzer:
    """
    Real-time prosody extraction engine.

    Maintains a sliding window of audio and extracts acoustic features
    using Praat (via parselmouth) or numpy-based fallbacks.
    Tracks per-speaker baselines that adapt over the conversation.
    """

    _WINDOW_S = 0.5
    _HOP_S = 0.01

    def __init__(self, sample_rate: int = 16000) -> None:
        """
        Args:
            sample_rate: Expected audio sample rate.
        """
        self._sample_rate = sample_rate
        self._window_samples = int(self._WINDOW_S * sample_rate)
        self._buffer: deque[np.ndarray] = deque()
        self._buffer_samples = 0
        self._baselines: dict[str, SpeakerBaseline] = {}
        self._f0_history: deque[float] = deque(maxlen=50)
        self._intensity_history: deque[float] = deque(maxlen=50)
        self._parselmouth_available = False
        self._last_f0: float = 0.0
        self._silence_start: float | None = None

        try:
            import parselmouth  # noqa: F401
            self._parselmouth_available = True
        except ImportError:
            log.info("parselmouth_not_available", hint="pip install praat-parselmouth")

    def process(
        self,
        chunk: AudioChunk,
        speaker_id: str = "default",
    ) -> ProsodyFeatures:
        """
        Extract prosodic features from an audio chunk.

        Args:
            chunk: Audio chunk (16kHz float32).
            speaker_id: Who is speaking (for per-speaker baselines).

        Returns:
            ProsodyFeatures with all extracted values.
        """
        self._buffer.append(chunk.data.copy())
        self._buffer_samples += len(chunk.data)

        while self._buffer_samples > self._window_samples:
            removed = self._buffer.popleft()
            self._buffer_samples -= len(removed)

        if self._buffer_samples < self._sample_rate * 0.05:
            return ProsodyFeatures()

        audio = np.concatenate(list(self._buffer))[-self._window_samples:]
        energy = float(np.sqrt(np.mean(audio ** 2)))

        if energy < 0.005:
            if self._silence_start is None:
                self._silence_start = time.monotonic()
            pause_ms = (time.monotonic() - self._silence_start) * 1000
            return ProsodyFeatures(
                pause_duration_ms=pause_ms,
                pause_type=self._classify_pause(pause_ms, audio),
                intensity_db=max(20 * np.log10(energy + 1e-10), -80),
            )
        else:
            self._silence_start = None

        f0 = self._extract_f0(audio)
        intensity_db = 20 * np.log10(energy + 1e-10) + 80
        f0_traj = self._compute_trajectory(self._f0_history, f0)
        int_traj = self._compute_trajectory(self._intensity_history, intensity_db)
        voice_quality = self._estimate_voice_quality(audio, f0)
        final_length = self._estimate_final_lengthening(audio, f0)
        rate = self._estimate_speaking_rate(audio)

        self._f0_history.append(f0)
        self._intensity_history.append(intensity_db)

        baseline = self._baselines.setdefault(speaker_id, SpeakerBaseline())
        self._update_baseline(baseline, f0, intensity_db, rate)

        f0_range = 0.0
        if len(self._f0_history) > 5:
            f0_vals = [v for v in self._f0_history if v > 0]
            if len(f0_vals) >= 2:
                f0_range = 12 * np.log2(max(f0_vals) / max(min(f0_vals), 1)) if min(f0_vals) > 0 else 0

        return ProsodyFeatures(
            f0_hz=f0,
            f0_trajectory=f0_traj,
            f0_range_semitones=float(f0_range),
            intensity_db=float(intensity_db),
            intensity_trajectory=int_traj,
            speaking_rate_syl_s=rate,
            final_lengthening_ratio=final_length,
            voice_quality=voice_quality,
            articulation_precision=self._estimate_articulation(audio),
            pause_duration_ms=0.0,
            pause_type="none",
        )

    def _extract_f0(self, audio: np.ndarray) -> float:
        """Extract fundamental frequency using parselmouth or autocorrelation."""
        if self._parselmouth_available:
            try:
                import parselmouth
                snd = parselmouth.Sound(audio, sampling_frequency=self._sample_rate)
                pitch = snd.to_pitch(time_step=0.01)
                f0_values = pitch.selected_array["frequency"]
                voiced = f0_values[f0_values > 0]
                if len(voiced) > 0:
                    self._last_f0 = float(np.median(voiced))
                    return self._last_f0
            except Exception:
                pass

        return self._autocorrelation_f0(audio)

    def _autocorrelation_f0(self, audio: np.ndarray) -> float:
        """Simple autocorrelation-based F0 estimation."""
        min_lag = int(self._sample_rate / 500)  # 500 Hz max
        max_lag = int(self._sample_rate / 60)   # 60 Hz min

        if len(audio) < max_lag * 2:
            return self._last_f0

        corr = np.correlate(audio[max_lag:], audio[max_lag:], mode="full")
        corr = corr[len(corr) // 2:]

        if len(corr) <= max_lag:
            return self._last_f0

        search = corr[min_lag:max_lag]
        if len(search) == 0:
            return self._last_f0

        peak = int(np.argmax(search)) + min_lag
        if corr[peak] > 0.3 * corr[0]:
            f0 = self._sample_rate / peak
            self._last_f0 = f0
            return f0

        return self._last_f0

    def _compute_trajectory(self, history: deque, current: float) -> str:
        """Classify the trajectory of a feature as rising/falling/level/reset."""
        if len(history) < 5:
            return "level"

        recent = list(history)[-10:]
        if current <= 0:
            return "level"

        trend = np.polyfit(range(len(recent)), recent, 1)[0]

        if abs(trend) < 0.5:
            return "level"
        elif trend > 2.0:
            return "rising"
        elif trend < -2.0:
            return "falling"
        elif trend > 0:
            return "rising"
        else:
            return "falling"

    def _estimate_voice_quality(self, audio: np.ndarray, f0: float) -> str:
        """
        Estimate voice quality from spectral characteristics.

        Returns one of: modal, creaky, breathy, pressed
        """
        if f0 <= 0:
            return "modal"

        spectral_tilt = self._compute_spectral_tilt(audio)
        jitter = self._estimate_jitter(audio, f0)

        if jitter > 0.05 and f0 < 100:
            return "creaky"
        elif spectral_tilt < -6:
            return "breathy"
        elif spectral_tilt > 2:
            return "pressed"
        return "modal"

    def _compute_spectral_tilt(self, audio: np.ndarray) -> float:
        """Compute spectral tilt (dB/octave) as a voice quality indicator."""
        spectrum = np.abs(np.fft.rfft(audio * np.hanning(len(audio))))
        if len(spectrum) < 10:
            return 0.0

        freqs = np.fft.rfftfreq(len(audio), d=1.0 / self._sample_rate)
        valid = freqs > 50
        if not np.any(valid):
            return 0.0

        log_freqs = np.log2(freqs[valid] + 1e-10)
        log_spec = 20 * np.log10(spectrum[valid] + 1e-10)

        if len(log_freqs) < 2:
            return 0.0

        slope = np.polyfit(log_freqs, log_spec, 1)[0]
        return float(slope)

    def _estimate_jitter(self, audio: np.ndarray, f0: float) -> float:
        """Estimate pitch period jitter (cycle-to-cycle variation)."""
        if f0 <= 0:
            return 0.0

        period_samples = int(self._sample_rate / f0)
        if period_samples < 4 or len(audio) < period_samples * 3:
            return 0.0

        periods = []
        for i in range(0, len(audio) - period_samples * 2, period_samples):
            segment = audio[i:i + period_samples * 2]
            corr = np.correlate(segment[:period_samples], segment[period_samples:])
            if len(corr) > 0:
                periods.append(float(corr[0]))

        if len(periods) < 2:
            return 0.0

        diffs = np.diff(periods)
        jitter = float(np.mean(np.abs(diffs)) / (np.mean(np.abs(periods)) + 1e-10))
        return jitter

    def _estimate_final_lengthening(self, audio: np.ndarray, f0: float) -> float:
        """
        Estimate whether the final syllable is lengthened relative to baseline.

        Returns ratio: >1.0 means lengthened, ~1.0 means normal.
        """
        n = len(audio)
        if n < self._sample_rate * 0.1:
            return 1.0

        quarter = n // 4
        final_energy = float(np.sqrt(np.mean(audio[-quarter:] ** 2)))
        earlier_energy = float(np.sqrt(np.mean(audio[:quarter] ** 2)))

        if earlier_energy < 1e-8:
            return 1.0

        ratio = final_energy / earlier_energy
        if ratio > 0.7:
            return max(1.0, ratio * 1.3)
        return 1.0

    def _estimate_speaking_rate(self, audio: np.ndarray) -> float:
        """Estimate syllables per second from energy envelope peaks."""
        frame_len = int(self._sample_rate * 0.025)
        hop = int(self._sample_rate * 0.01)

        n_frames = max(1, (len(audio) - frame_len) // hop)
        envelope = np.zeros(n_frames)
        for i in range(n_frames):
            start = i * hop
            frame = audio[start:start + frame_len]
            envelope[i] = float(np.sqrt(np.mean(frame ** 2)))

        if len(envelope) < 3:
            return 4.0

        threshold = np.mean(envelope) * 0.5
        peaks = 0
        above = False
        for val in envelope:
            if val > threshold and not above:
                peaks += 1
                above = True
            elif val <= threshold:
                above = False

        duration_s = len(audio) / self._sample_rate
        if duration_s < 0.1:
            return 4.0

        rate = peaks / duration_s
        return float(np.clip(rate, 1.0, 10.0))

    def _estimate_articulation(self, audio: np.ndarray) -> float:
        """Estimate articulation precision (spectral clarity)."""
        spectrum = np.abs(np.fft.rfft(audio))
        if len(spectrum) < 10:
            return 0.5

        spectral_entropy = float(-np.sum(
            (spectrum / (np.sum(spectrum) + 1e-10)) *
            np.log2(spectrum / (np.sum(spectrum) + 1e-10) + 1e-10)
        ))
        max_entropy = np.log2(len(spectrum))
        return float(np.clip(1.0 - spectral_entropy / max(max_entropy, 1), 0, 1))

    def _classify_pause(self, duration_ms: float, audio: np.ndarray) -> str:
        """Classify silence type based on spectral content."""
        energy = float(np.sqrt(np.mean(audio ** 2)))
        if energy < 0.001:
            return "unfilled"

        spectrum = np.abs(np.fft.rfft(audio))
        freqs = np.fft.rfftfreq(len(audio), d=1.0 / self._sample_rate)
        breath_band = (freqs >= 200) & (freqs <= 2500)
        breath_energy = float(np.mean(spectrum[breath_band] ** 2)) if np.any(breath_band) else 0
        total_energy = float(np.mean(spectrum ** 2)) + 1e-10

        if breath_energy / total_energy > 0.4:
            return "breath"
        return "filled"

    def _update_baseline(
        self,
        baseline: SpeakerBaseline,
        f0: float,
        intensity: float,
        rate: float,
    ) -> None:
        """Update a speaker's prosodic baseline using EMA."""
        alpha = 0.01
        baseline.n_frames += 1

        if f0 > 0:
            baseline.f0_mean = (1 - alpha) * baseline.f0_mean + alpha * f0
            baseline.f0_std = (1 - alpha) * baseline.f0_std + alpha * abs(f0 - baseline.f0_mean)

        baseline.intensity_mean = (1 - alpha) * baseline.intensity_mean + alpha * intensity
        baseline.rate_mean = (1 - alpha) * baseline.rate_mean + alpha * rate

    def get_baseline(self, speaker_id: str = "default") -> SpeakerBaseline:
        """Get the prosodic baseline for a speaker."""
        return self._baselines.get(speaker_id, SpeakerBaseline())
