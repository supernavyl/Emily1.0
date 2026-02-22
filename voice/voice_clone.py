"""
Voice cloning support for Emily's TTS (Phase 3 stub, full in Phase 17).

Provides utilities for:
- Collecting and validating voice sample recordings
- Computing speaker embeddings from samples
- Exporting speaker embedding for XTTS v2 use

This is a stub implementation that sets up the interface.
Full voice cloning is activated in Phase 17 (Persona system).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from observability.logger import get_logger

log = get_logger(__name__)


class VoiceCloner:
    """
    Voice cloning manager.

    Manages the speaker reference audio used by XTTS v2 for voice cloning.
    In Phase 3, this is a stub that validates files exist and are the right format.
    """

    _MIN_DURATION_S = 10  # Minimum clean audio needed for cloning
    _SUPPORTED_FORMATS = {".wav", ".mp3", ".flac", ".m4a"}

    def __init__(self, samples_dir: str = "data/voice_samples") -> None:
        """
        Args:
            samples_dir: Directory containing voice sample audio files.
        """
        self._samples_dir = Path(samples_dir)
        self._speaker_wav: str | None = None

    async def prepare(self) -> str | None:
        """
        Prepare the speaker reference file for XTTS v2.

        Returns:
            Path to the speaker WAV file, or None if no samples available.
        """
        if not self._samples_dir.exists():
            log.info("voice_clone_no_samples_dir", path=str(self._samples_dir))
            return None

        samples = [
            f for f in self._samples_dir.iterdir()
            if f.suffix.lower() in self._SUPPORTED_FORMATS
        ]

        if not samples:
            log.info("voice_clone_no_samples_found")
            return None

        # Use the first valid sample as speaker reference
        sample_path = samples[0]
        log.info("voice_clone_using_sample", path=str(sample_path))
        self._speaker_wav = str(sample_path)
        return self._speaker_wav

    @property
    def speaker_wav(self) -> str | None:
        """Path to the prepared speaker WAV file."""
        return self._speaker_wav
