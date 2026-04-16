"""Generate synthetic breath WAV samples for the breath injector."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.io import wavfile

SAMPLE_RATE = 24000
OUTPUT_DIR = Path("assets/breaths")


def _pink_noise(n: int) -> np.ndarray:
    """Generate approximate pink noise via the Voss-McCartney algorithm."""
    n_rows = 16
    array = np.empty((n, n_rows))
    array.fill(np.nan)
    array[0, :] = np.random.randn(n_rows)
    cols = np.random.geometric(0.5, n) - 1
    cols[cols >= n_rows] = 0
    rows = np.arange(n)
    array[rows, cols] = np.random.randn(n)
    for col_idx in range(n_rows):
        col = array[:, col_idx]
        mask = np.isnan(col)
        idx = np.where(~mask, np.arange(n), 0)
        np.maximum.accumulate(idx, out=idx)
        array[:, col_idx] = col[idx]
    total = np.nansum(array, axis=1)
    mx = np.max(np.abs(total))
    if mx > 0:
        total /= mx
    return total


def _bandpass(signal: np.ndarray, low_hz: int, high_hz: int) -> np.ndarray:
    """Simple FFT bandpass filter."""
    fft = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), d=1.0 / SAMPLE_RATE)
    mask = (freqs >= low_hz) & (freqs <= high_hz)
    fft[~mask] = 0
    return np.fft.irfft(fft, n=len(signal))


def _make_breath(duration_ms: int, attack_ms: int = 20, release_ms: int = 40) -> np.ndarray:
    """Synthesize a single breath sound."""
    n_samples = int(SAMPLE_RATE * duration_ms / 1000)
    noise = _pink_noise(n_samples)
    filtered = _bandpass(noise, 200, 2500)
    envelope = np.ones(n_samples)
    attack_n = int(SAMPLE_RATE * attack_ms / 1000)
    release_n = int(SAMPLE_RATE * release_ms / 1000)
    if attack_n > 0:
        envelope[:attack_n] = np.linspace(0, 1, attack_n)
    if release_n > 0:
        envelope[-release_n:] = np.linspace(1, 0, release_n)
    result = (filtered * envelope).astype(np.float32)
    mx = np.max(np.abs(result))
    if mx > 0:
        result = result * (0.15 / mx)
    return result


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    specs = [
        ("inhale_short_1.wav", 100),
        ("inhale_short_2.wav", 120),
        ("inhale_medium_1.wav", 250),
        ("inhale_medium_2.wav", 300),
        ("inhale_long_1.wav", 400),
    ]
    for filename, dur_ms in specs:
        audio = _make_breath(dur_ms)
        path = OUTPUT_DIR / filename
        wavfile.write(str(path), SAMPLE_RATE, audio)
        print(f"  {path} — {dur_ms}ms, {len(audio)} samples")
    print(f"Done. {len(specs)} breath samples in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
