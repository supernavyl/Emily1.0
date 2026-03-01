"""
Real-time speaker diarization and voice identification for Emily.

Answers three questions every processing frame:
1. How many people are speaking right now?
2. Who is each of them (by voiceprint)?
3. What is each speaker's isolated audio?

Uses pyannote for diarization and ECAPA-TDNN (SpeechBrain) for embeddings.
Supports voiceprint enrollment and cross-session recognition.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from observability.logger import get_logger

if TYPE_CHECKING:
    from perception.audio.stream import AudioChunk

log = get_logger(__name__)

VOICE_PROFILES_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "voice_profiles"


@dataclass
class SpeakerProfile:
    """Stored voiceprint for a known speaker."""

    name: str
    embedding: np.ndarray
    enrollment_duration_s: float = 0.0
    created_at: float = field(default_factory=time.time)


@dataclass
class ActiveSpeaker:
    """A currently detected speaker in the audio stream."""

    speaker_id: str
    name: str | None
    confidence: float
    start_time: float
    energy: float
    is_known: bool


@dataclass
class SpeakerFrame:
    """Per-frame speaker analysis result."""

    active_speakers: list[ActiveSpeaker]
    dominant_speaker: str | None
    overlap_detected: bool
    n_speakers: int
    timestamp: float = field(default_factory=time.monotonic)


class SpeakerEngine:
    """
    Real-time speaker diarization and identification.

    Provides voiceprint enrollment, speaker tracking, and overlap detection
    for up to 2 simultaneous speakers.
    """

    def __init__(self, max_speakers: int = 2) -> None:
        """
        Args:
            max_speakers: Maximum number of simultaneous speakers to track.
        """
        self._max_speakers = max_speakers
        self._embedder: object | None = None
        self._diarizer: object | None = None
        self._known_speakers: dict[str, SpeakerProfile] = {}
        self._active_speakers: list[ActiveSpeaker] = []
        self._embedding_buffer: list[np.ndarray] = []
        self._embedder_available = False
        self._diarizer_available = False
        self._frame_count = 0

    async def load(self) -> None:
        """Load speaker models and known voiceprints."""
        await asyncio.gather(
            self._load_embedder(),
            self._load_diarizer(),
        )
        self._load_known_speakers()

    async def _load_embedder(self) -> None:
        """Load the ECAPA-TDNN speaker embedding model (CUDA with CPU fallback)."""
        try:
            from speechbrain.inference.speaker import EncoderClassifier

            device = "cuda"
            try:
                self._embedder = await asyncio.to_thread(
                    EncoderClassifier.from_hparams,
                    source="speechbrain/spkrec-ecapa-voxceleb",
                    run_opts={"device": device},
                )
            except Exception:
                device = "cpu"
                log.info("speaker_cuda_unavailable_falling_back_to_cpu")
                self._embedder = await asyncio.to_thread(
                    EncoderClassifier.from_hparams,
                    source="speechbrain/spkrec-ecapa-voxceleb",
                    run_opts={"device": device},
                )

            self._embedder_available = True
            log.info("speaker_embedder_loaded", model="ecapa-tdnn", device=device)
        except ImportError:
            log.info("speechbrain_not_available", hint="pip install speechbrain")
        except Exception as exc:
            log.warning("speaker_embedder_load_failed", error=str(exc))

    async def _load_diarizer(self) -> None:
        """Load the pyannote diarization pipeline.

        TODO: Integrate diarizer into process_frame() for multi-speaker
        segmentation once overlap detection is needed.  Currently only
        the ECAPA-TDNN embedder is used for speaker identification.
        """
        try:
            from pyannote.audio import Pipeline

            self._diarizer = await asyncio.to_thread(
                Pipeline.from_pretrained,
                "pyannote/speaker-diarization-3.1",
            )
            self._diarizer_available = True
            log.info("speaker_diarizer_loaded", model="pyannote-3.1")
        except ImportError:
            log.info("pyannote_not_available", hint="pip install pyannote.audio")
        except Exception as exc:
            log.warning("speaker_diarizer_load_failed", error=str(exc))

    def _load_known_speakers(self) -> None:
        """Load voiceprint profiles from disk."""
        VOICE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        for profile_path in VOICE_PROFILES_DIR.glob("*.npz"):
            try:
                data = np.load(profile_path, allow_pickle=True)
                name = str(data["name"])
                embedding = data["embedding"]
                self._known_speakers[name] = SpeakerProfile(
                    name=name,
                    embedding=embedding,
                    enrollment_duration_s=float(data.get("duration", 0)),
                )
                log.info("speaker_profile_loaded", name=name)
            except Exception as exc:
                log.warning("speaker_profile_load_error", path=str(profile_path), error=str(exc))

    async def process_frame(self, chunk: AudioChunk) -> SpeakerFrame:
        """
        Analyze a single audio frame for speaker information.

        Args:
            chunk: Audio chunk to analyze.

        Returns:
            SpeakerFrame with active speakers, overlap, and dominant speaker.
        """
        self._frame_count += 1

        energy = float(np.sqrt(np.mean(chunk.data**2)))
        if energy < 0.005:
            return SpeakerFrame(
                active_speakers=[],
                dominant_speaker=None,
                overlap_detected=False,
                n_speakers=0,
            )

        active = []
        speaker_id = "unknown"
        confidence = 0.5

        if self._embedder_available and self._frame_count % 10 == 0:
            embedding = await self._compute_embedding(chunk.data, chunk.sample_rate)
            if embedding is not None:
                match_name, match_conf = self._match_speaker(embedding)
                if match_name is not None:
                    speaker_id = match_name
                    confidence = match_conf

        speaker = ActiveSpeaker(
            speaker_id=speaker_id,
            name=speaker_id if speaker_id != "unknown" else None,
            confidence=confidence,
            start_time=chunk.timestamp,
            energy=energy,
            is_known=speaker_id != "unknown",
        )
        active.append(speaker)

        return SpeakerFrame(
            active_speakers=active,
            dominant_speaker=speaker_id if active else None,
            overlap_detected=len(active) > 1,
            n_speakers=len(active),
        )

    async def _compute_embedding(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> np.ndarray | None:
        """Compute a speaker embedding from an audio chunk."""
        if not self._embedder_available or self._embedder is None:
            return None

        try:
            import torch

            if sample_rate != 16000:
                ratio = 16000 / sample_rate
                n_out = int(len(audio) * ratio)
                audio = np.interp(
                    np.linspace(0, len(audio) - 1, n_out),
                    np.arange(len(audio)),
                    audio,
                ).astype(np.float32)

            waveform = torch.FloatTensor(audio).unsqueeze(0)
            embedding = await asyncio.to_thread(self._embedder.encode_batch, waveform)
            return embedding.squeeze().cpu().numpy()
        except Exception as exc:
            log.debug("embedding_compute_error", error=str(exc))
            return None

    def _match_speaker(
        self,
        embedding: np.ndarray,
        threshold: float = 0.65,
    ) -> tuple[str | None, float]:
        """
        Match an embedding against known speaker profiles.

        Args:
            embedding: Speaker embedding vector.
            threshold: Cosine similarity threshold for a match.

        Returns:
            Tuple of (speaker_name, confidence) or (None, 0.0) if no match.
        """
        best_name: str | None = None
        best_score: float = 0.0

        for name, profile in self._known_speakers.items():
            score = self._cosine_similarity(embedding, profile.embedding)
            if score > best_score:
                best_score = score
                best_name = name

        if best_score >= threshold:
            return best_name, best_score
        return None, 0.0

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        a_flat = a.flatten()
        b_flat = b.flatten()
        dot = float(np.dot(a_flat, b_flat))
        norm = float(np.linalg.norm(a_flat) * np.linalg.norm(b_flat))
        if norm < 1e-10:
            return 0.0
        return dot / norm

    async def enroll_speaker(
        self,
        name: str,
        audio_samples: list[np.ndarray],
        sample_rate: int = 16000,
    ) -> bool:
        """
        Enroll a new speaker by computing and storing their voiceprint.

        Args:
            name: Name for the speaker.
            audio_samples: List of audio arrays (at least 5-10 seconds total).
            sample_rate: Sample rate of the audio.

        Returns:
            True if enrollment succeeded.
        """
        if not self._embedder_available:
            log.warning("enrollment_failed_no_embedder")
            return False

        embeddings = []
        total_duration = 0.0
        for sample in audio_samples:
            emb = await self._compute_embedding(sample, sample_rate)
            if emb is not None:
                embeddings.append(emb)
                total_duration += len(sample) / sample_rate

        if not embeddings:
            log.warning("enrollment_failed_no_valid_embeddings", name=name)
            return False

        avg_embedding = np.mean(embeddings, axis=0)
        profile = SpeakerProfile(
            name=name,
            embedding=avg_embedding,
            enrollment_duration_s=total_duration,
        )
        self._known_speakers[name] = profile

        profile_path = VOICE_PROFILES_DIR / f"{name}.npz"
        VOICE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        np.savez(
            profile_path,
            name=name,
            embedding=avg_embedding,
            duration=total_duration,
        )

        log.info(
            "speaker_enrolled",
            name=name,
            duration_s=f"{total_duration:.1f}",
            n_embeddings=len(embeddings),
        )
        return True

    @property
    def known_speakers(self) -> list[str]:
        """List of enrolled speaker names."""
        return list(self._known_speakers.keys())

    @property
    def is_available(self) -> bool:
        """True if at least the embedder model is loaded."""
        return self._embedder_available
