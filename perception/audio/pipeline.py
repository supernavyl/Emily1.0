"""
Audio perception pipeline orchestrator.

Connects AudioStream → WakeWordDetector + SileroVAD → FasterWhisperSTT
and emits transcription events to the PerceptionBus.

Usage (as a background task):
    pipeline = AudioPipeline(settings, bus)
    await pipeline.start()
    # Runs until stopped
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

import numpy as np

from config import EmilySettings
from core.bus import PerceptionBus, Priority
from observability.logger import get_logger
from perception.audio.stt import FasterWhisperSTT, TranscriptResult
from perception.audio.stream import AudioStream
from perception.audio.vad import SileroVAD, SpeechSegment
from perception.audio.wake_word import WakeWordDetector, WakeWordEvent

log = get_logger(__name__)


class AudioPipeline:
    """
    Full audio perception pipeline: capture → wake word → VAD → STT.

    Operates in two modes:
    1. Wake-word gated: only processes speech after "Hey Emily" detected
    2. Continuous: always-on VAD + STT (when wake word model unavailable)

    Emits events to PerceptionBus:
    - `audio.wake_word_detected` — when wake word fires
    - `audio.speech_segment` — VAD-gated speech segment
    - `audio.transcript` — STT result
    """

    def __init__(self, settings: EmilySettings, bus: PerceptionBus) -> None:
        """
        Args:
            settings: Global Emily settings.
            bus: PerceptionBus to publish events onto.
        """
        self.settings = settings
        self.bus = bus
        self.stream = AudioStream(settings.audio)
        self.vad = SileroVAD(settings.vad)
        self.stt = FasterWhisperSTT(settings.stt)
        self.wake_word = WakeWordDetector(settings.wake_word)
        self._running = False
        self._wake_word_active = False
        self._wake_word_cooldown_s = 8.0  # How long to stay active after detection

    async def load(self) -> None:
        """Load all ML models (VAD, STT, wake word) concurrently."""
        log.info("audio_pipeline_loading_models")
        await asyncio.gather(
            self.vad.load(),
            self.stt.load(),
            self.wake_word.load(),
        )
        log.info("audio_pipeline_models_ready")

    async def start(self) -> None:
        """Start the audio capture and processing pipeline."""
        self._running = True
        await self.stream.start()
        log.info("audio_pipeline_started")
        await self._process_loop()

    async def _process_loop(self) -> None:
        """Main processing loop: read chunks, detect wake word and speech."""
        wake_active_until: float = 0.0

        while self._running:
            try:
                chunk = await self.stream.read()

                # Wake word detection (runs on every chunk)
                wake_event = await self.wake_word.process_async(chunk)
                if wake_event is not None:
                    wake_active_until = time.monotonic() + self._wake_word_cooldown_s
                    await self.bus.publish(
                        "audio.wake_word_detected",
                        {
                            "keyword": wake_event.keyword,
                            "score": wake_event.score,
                            "timestamp": wake_event.timestamp,
                        },
                        Priority.REALTIME,
                    )

                # VAD runs continuously (wake-word mode gates STT, not VAD)
                segment = self.vad.process(chunk)

                if segment is not None:
                    await self.bus.publish(
                        "audio.speech_segment",
                        {
                            "duration_ms": segment.duration_ms,
                            "sample_rate": segment.sample_rate,
                            "peak_probability": segment.peak_probability,
                        },
                        Priority.REALTIME,
                    )

                    # Only run STT if wake word was recently detected
                    # (or if wake word detection is disabled/unavailable)
                    wake_word_armed = time.monotonic() < wake_active_until
                    if wake_word_armed or not self.wake_word._use_oww:
                        asyncio.create_task(self._transcribe_and_emit(segment))

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("audio_pipeline_loop_error", error=str(exc))
                await asyncio.sleep(0.1)

    async def _transcribe_and_emit(self, segment: SpeechSegment) -> None:
        """
        Run STT on a segment and publish the transcript event.

        Args:
            segment: VAD-gated speech segment to transcribe.
        """
        try:
            result = await self.stt.transcribe(segment)
            if not result.is_likely_speech:
                log.debug("stt_non_speech_segment", no_speech_prob=result.no_speech_prob)
                return

            await self.bus.publish(
                "audio.transcript",
                {
                    "text": result.text,
                    "language": result.language,
                    "language_probability": result.language_probability,
                    "confidence": result.confidence,
                    "latency_ms": result.latency_ms,
                    "words": [
                        {
                            "word": w.word,
                            "start": w.start,
                            "end": w.end,
                            "probability": w.probability,
                        }
                        for w in result.words
                    ],
                    "duration_ms": segment.duration_ms,
                },
                Priority.REALTIME,
            )
            # Print live for Phase 2 verification
            print(f"\n[Emily heard]: {result.text}")

        except Exception as exc:
            log.error("transcription_failed", error=str(exc))

    def stop(self) -> None:
        """Stop the audio pipeline and release all resources."""
        self._running = False
        self.stream.stop()
        log.info("audio_pipeline_stopped")
